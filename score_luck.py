"""
score_luck.py — v5
Reads hitter_luck_input.csv and calculates a luck score for each batter.

Luck score formula (positive = unlucky/buy low, negative = lucky/sell high):

  Phase A additions (v5): park factor adjustment, wRC+ quality gate,
  RTM integration, playing time discount, amplification cap.

  Component 1 — BABIP luck (with contextual modifiers):
    babip_comp = (BABIP - park_adj_expected_babip) * -3.000
                 × chase_modifier(o_swing_rate, babip, pa)
                 × zcon_babip_modifier(z_contact_rate, babip, hard_hit_rate, pa)

    park_adj_expected_babip = league_avg_babip (0.300) × park_factor

  Component 2 — HR/FB luck (with pull-rate modifier):
    hrfb_comp = (hr_fb_rate - park_adj_expected_hrfb) * -0.150
                × pull_modifier(pull_rate, hard_hit_rate, pa)

    park_adj_expected_hrfb = league_avg_hrfb (0.145) × park_factor

  Component 3 — Z-contact vs league average (unchanged):
    zcon_comp = (z_contact_rate - 0.880) * -0.030

  Component 4 — xwOBA gap (unchanged):
    xwoba_comp = xwOBA_gap * 1.000   where xwOBA_gap = xwOBA - wOBA

  raw_luck = babip_comp + hrfb_comp + zcon_comp + xwoba_comp

  Confidence multiplier (unchanged):
    raw_luck *= min(1, max(0, (PA - 30) / 70))

  Playing time discount (v5):
    Compares player PA to P90 of dataset (proxy for full-starter PA at
    current date). Players well below P90 are likely platoon/part-time
    and receive a mild actionability discount.
      rate = player_PA / p90_pa (capped at 1.0)
      rate >= 0.65: x1.00 (starter)
      rate 0.45-0.65: x0.80 (part-time/platoon)
      rate < 0.45: x0.60 (spot/bench)

  Rising boost (+0.02): age < 28, buy-signal players only (unchanged).

  Quality tier multiplier (buy signals only, v5):
    Based on pseudo wRC+ = (xwOBA_3yr / 0.315) x park_factor x 100
      wRC+ >= 130: x1.15 (superstar — Judge/Ohtani/Ramírez tier)
      wRC+ 120-129: x1.10 (elite)
      wRC+ 100-119: x1.00 (above avg)
      wRC+ 95-99: x0.80 (average)
      wRC+ 85-94: x0.60 (below avg)
      wRC+ < 85: x0.40 (poor)

  RTM integration (v5):
    rtm_signal = xwOBA_3yr - current_wOBA
      (positive = underperforming career avg = buy confirmation)
    combined = luck_after_quality * 0.75 + (rtm_signal * 10) * 0.25
    Confluence bonus x1.15 when luck and RTM agree direction.

  Amplification cap (v5):
    Applied after RTM. Clamps result to [0.25x, 2.0x] relative to raw luck.
    Prevents overconfidence when all signals align. Cap fires flag stored
    in amplification_cap_applied column.

Verdict thresholds:
   > 0.12  -> Buy low
   > 0.05  -> Slight buy
   < -0.12 -> Sell high
   < -0.065 -> Slight sell
   else    -> Neutral

Weight history (backtest-validated on 551 player-seasons, 2023-2024):
    BABIP weight:       -5.000  ->  -3.000  (v2)
    HR/FB weight:       -0.040  ->  -0.150  (v2)
    Hard-hit weight:    +0.025  ->  removed (v2; subsumed by xwOBA gap)
    Barrel weight:      +0.030  ->  removed (v2; subsumed by xwOBA gap)
    Z-contact weight:   -0.010  ->  -0.030  (v2)
    xwOBA gap:          (new)       +1.000  (v2; r=+0.40 vs delta wOBA)
    Contextual modifiers:           (new)   (v3; pull/chase/z-contact)
    Min PA gate + hard_hit% quality:        (v4; gates buy-side amplifiers)
    Phase A: park factors, wRC+ gate, RTM, PT discount, amp cap  (v5)
"""

import json
import math
import os
import re
import sys
import unicodedata

import pandas as pd

from config import (
    H_PROD_BUY_LOW, H_PROD_SLIGHT_BUY, H_PROD_SELL_HIGH, H_PROD_SLIGHT_SELL,
    H_PROD_SB_MIN_XWOBA_GAP, H_PROD_SB_MAX_XWOBA,
    H_KP_K_PENALTY, H_KP_PULL_PENALTY, H_HH_PENALTY,
    H_SPEED_PENALTY, H_CHASE_PENALTY, H_MAX_COMBINED_PEN,
    H_CHASE_AGE_WEIGHT_U25, H_CHASE_AGE_WEIGHT_26_27,
)

BASE_DIR              = os.path.dirname(os.path.abspath(__file__))
INPUT_PATH            = os.path.join(BASE_DIR, "hitter_luck_input.csv")
OUTPUT_PATH           = os.path.join(BASE_DIR, "luck_scores.csv")
CAREER_CACHE          = os.path.join(BASE_DIR, "data", "career_stats.json")
CAREER_QUALITY_CACHE  = os.path.join(BASE_DIR, "data", "career_quality.json")
SEASONAL_PATTERNS_CACHE = os.path.join(BASE_DIR, "data", "seasonal_patterns.json")
STATCAST_PATH         = os.path.join(BASE_DIR, "hitters_statcast.csv")
TEAM_OAA_PATH         = os.path.join(BASE_DIR, "data", "team_oaa_2025.csv")
CAREER_BABIP_H_PATH       = os.path.join(BASE_DIR, "data", "hitter_career_babip.json")
CAREER_DISCIPLINE_H_PATH  = os.path.join(BASE_DIR, "data", "hitter_career_discipline.json")
CAREER_K_PULL_PATH        = os.path.join(BASE_DIR, "data", "hitter_career_k_pull.json")
SPRINT_SPEED_PATH         = os.path.join(BASE_DIR, "data", "hitter_sprint_speed.json")
LAUNCH_ANGLE_PATH         = os.path.join(BASE_DIR, "data", "hitter_launch_angle.json")
CAREER_PLATOON_PATH       = os.path.join(BASE_DIR, "data", "hitter_career_platoon.json")
CONTRACT_YEAR_PATH        = os.path.join(BASE_DIR, "data", "contract_year_2026.csv")
FANTASY_RANKINGS_H_PATH   = os.path.join(BASE_DIR, "data", "fantasy_rankings_hitters_2026.csv")
OWNERSHIP_PATH            = os.path.join(BASE_DIR, "data", "player_ownership_2026.csv")
PRIOR_TEAMS_PATH          = os.path.join(BASE_DIR, "data", "prior_teams_2025.json")
SEASON_YEAR               = 2026

# ---------------------------------------------------------------------------
# Park factor table (hardcoded — FanGraphs + Baseball Reference blocked)
# Codes match Baseball Savant home_team / Statcast team codes
# ---------------------------------------------------------------------------
PARK_FACTORS = {
    # Hitter friendly
    "COL": 1.18,   # Coors Field
    "CIN": 1.08,   # Great American Ballpark
    "PHI": 1.06,   # Citizens Bank Park
    "BOS": 1.05,   # Fenway Park
    "TEX": 1.05,   # Globe Life Field
    "AZ":  1.02,   # Chase Field
    "BAL": 1.01,   # Camden Yards
    # Neutral
    "ATL": 1.00,   # Truist Park
    "CHC": 1.00,   # Wrigley Field
    "LAD": 1.00,   # Dodger Stadium
    "NYY": 1.00,   # Yankee Stadium
    "STL": 1.00,   # Busch Stadium
    # Slightly pitcher friendly
    "MIL": 0.99,   # American Family Field
    "HOU": 0.99,   # Minute Maid Park
    "DET": 0.99,   # Comerica Park
    "CLE": 0.98,   # Progressive Field
    "MIN": 0.98,   # Target Field
    "PIT": 0.98,   # PNC Park
    "CWS": 0.98,   # Guaranteed Rate Field
    "WSH": 0.98,   # Nationals Park
    "SEA": 0.97,   # T-Mobile Park
    "SD":  0.97,   # Petco Park
    "LAA": 0.97,   # Angel Stadium
    "KC":  0.97,   # Kauffman Stadium
    "TOR": 0.97,   # Rogers Centre
    # Pitcher friendly
    "MIA": 0.95,   # LoanDepot Park
    "NYM": 0.95,   # Citi Field
    "ATH": 0.96,   # Sacramento / Oakland Coliseum era
    "OAK": 0.96,   # (same as ATH)
    "TB":  0.94,   # Tropicana Field
    "SF":  0.91,   # Oracle Park
}
DEFAULT_PARK_FACTOR  = 1.00
LEAGUE_AVG_BABIP     = 0.300
LEAGUE_AVG_HRFB      = 0.145
LEAGUE_AVG_XWOBA     = 0.315   # MLB average xwOBA; denominator for pseudo wRC+


# ---------------------------------------------------------------------------
# Contextual modifier functions (v3, unchanged)
# ---------------------------------------------------------------------------

def _chase_modifier(o_swing: float, babip: float, pa: int = 0) -> float:
    """
    Directional chase-rate modifier on the BABIP luck component.

    Sell side (BABIP > .300): high O-Swing% means the elevated BABIP is
      less likely to be pure sequencing luck — amplify the sell signal.
    Buy side (BABIP <= .300): high O-Swing% means the low BABIP is partly
      skill-driven — dampen the buy signal.
      Requires PA >= 75 (v4 minimum sample gate).
    """
    if math.isnan(o_swing):
        return 1.0
    if o_swing > 0.40:
        factor = 1.25
    elif o_swing > 0.35:
        factor = 1.15
    else:
        return 1.0
    if babip > 0.300:
        return factor
    if pa < 75:
        return 1.0
    return 2.0 - factor   # 0.75 or 0.85


def _zcon_babip_modifier(
    z_contact: float, babip: float,
    hard_hit_rate: float = float("nan"), pa: int = 0,
    career_hh_thresh: float = 0.370,
) -> float:
    """
    Directional Z-contact modifier on the BABIP luck component.

    Sell side (BABIP > .300): high Z-contact% means consistent zone
      contact sustains a higher BABIP — reduce the sell signal.
    Buy side (BABIP <= .300): high Z-contact% + good hard contact makes
      the low BABIP more anomalous — amplify the buy signal.
      Requires PA >= 75 AND hard_hit% quality gate.

    career_hh_thresh: per-player career BBE hard-hit rate (default 0.370 ≈ slightly
      below league mean). Strong gate = career baseline; moderate = baseline - 0.060.
    """
    if math.isnan(z_contact):
        return 1.0
    if z_contact > 0.92:
        base_factor = 0.75
    elif z_contact > 0.88:
        base_factor = 0.85
    else:
        return 1.0

    if babip > 0.300:
        return base_factor
    if pa < 75:
        return 1.0

    hhr = 0.0 if math.isnan(hard_hit_rate) else hard_hit_rate
    if hhr >= career_hh_thresh:
        return 2.0 - base_factor
    elif hhr >= career_hh_thresh - 0.060:
        return 1.10 if base_factor == 0.75 else 1.05
    else:
        return 1.0


def _pull_modifier(
    pull_rate: float, hard_hit_rate: float = float("nan"), pa: int = 0,
    career_hh_thresh: float = 0.370,
) -> float:
    """
    Reduces the HR/FB luck component for strong pull hitters with adequate
    hard contact. Requires PA >= 75 (v4 minimum sample gate).

    career_hh_thresh: per-player career BBE hard-hit rate (default 0.370).
      Strong gate = career baseline; moderate = baseline - 0.060.
    """
    if math.isnan(pull_rate):
        return 1.0
    if pa < 75:
        return 1.0
    if pull_rate > 0.45:
        base = 0.65
    elif pull_rate > 0.40:
        base = 0.80
    else:
        return 1.0

    hhr = 0.0 if math.isnan(hard_hit_rate) else hard_hit_rate
    if hhr >= career_hh_thresh:
        return base
    elif hhr >= career_hh_thresh - 0.060:
        return base + 0.30 * (1.0 - base)
    else:
        return 1.0


# ---------------------------------------------------------------------------
# v5: Park factor helpers
# ---------------------------------------------------------------------------
def _park_factor(team: str) -> float:
    return PARK_FACTORS.get(str(team), DEFAULT_PARK_FACTOR)


def _quality_tier(wrc_plus: float) -> tuple:
    """Returns (multiplier, label) from pseudo wRC+. Buy signals only."""
    if wrc_plus >= 130: return 1.15, "Superstar (130+)"
    if wrc_plus >= 120: return 1.10, "Elite (120-129)"
    if wrc_plus >= 100: return 1.00, "Above Avg (100-119)"
    if wrc_plus >= 95:  return 0.80, "Average (95-99)"
    if wrc_plus >= 85:  return 0.60, "Below Avg (85-94)"
    return 0.40, "Poor (<85)"


def _playing_time_scale(pa: int, p90_pa: float) -> float:
    """
    Actionability discount for part-time players.
    Compares current PA to P90 of the full dataset (proxy for full-starter
    accumulation at this point in the season).
      rate >= 0.65 -> 1.00 (starter)
      rate 0.45-0.65 -> 0.80 (platoon/part-time)
      rate < 0.45 -> 0.60 (spot/bench)
    """
    if p90_pa <= 0:
        return 1.0
    rate = min(1.0, pa / p90_pa)
    if rate >= 0.65:
        return 1.00
    if rate >= 0.45:
        return 0.80
    return 0.60


def _amplification_cap(combined: float, raw: float) -> tuple:
    """
    Clamps |combined| to [0.25x, 2.0x] of |raw|.
    When raw == 0 (confidence-muted), returns (0.0, False).
    Preserves sign direction. Returns (capped_score, cap_fired_bool).
    """
    if abs(raw) < 1e-6:
        return 0.0, False
    cap_fired = False
    if abs(combined) > 2.0 * abs(raw):
        combined = math.copysign(2.0 * abs(raw), raw)
        cap_fired = True
    elif abs(combined) < 0.25 * abs(raw):
        combined = math.copysign(0.25 * abs(raw), raw)
        cap_fired = True
    return round(combined, 4), cap_fired


# ---------------------------------------------------------------------------
# v5: Data loading helpers
# ---------------------------------------------------------------------------
def _derive_batter_teams(sc_path: str) -> pd.Series:
    """
    Derives each batter's team from Statcast pitch data.
    Batter is on home team when inning_topbot == Bot, away when Top.
    Returns most common team per batter MLBAM ID.
    """
    if not os.path.exists(sc_path):
        return pd.Series(dtype=str)
    sc = pd.read_csv(
        sc_path,
        usecols=["batter", "home_team", "away_team", "inning_topbot"],
        low_memory=False,
    )
    sc["batter_team"] = sc.apply(
        lambda r: r["home_team"] if r["inning_topbot"] == "Bot" else r["away_team"],
        axis=1,
    )
    return sc.groupby("batter")["batter_team"].agg(lambda x: x.mode()[0])


def _load_oaa_adj(oaa_path: str) -> dict:
    """Returns dict: team_abbr -> babip_adj float (-0.008 / 0.0 / +0.008)."""
    if not os.path.exists(oaa_path):
        return {}
    df = pd.read_csv(oaa_path, usecols=["team_abbr", "babip_adj"])
    return dict(zip(df["team_abbr"], df["babip_adj"].astype(float)))


def _derive_opponent_oaa_adj(sc_path: str, oaa_adj: dict) -> pd.Series:
    """
    For each batter, computes the PA-weighted mean BABIP adjustment of opponents faced.
    Opponent = the fielding team (opposite of batter's team per PA).
    Returns Series: batter_id -> mean_oaa_babip_adj.
    """
    if not os.path.exists(sc_path) or not oaa_adj:
        return pd.Series(dtype=float)
    sc = pd.read_csv(
        sc_path,
        usecols=["batter", "home_team", "away_team", "inning_topbot"],
        low_memory=False,
    )
    sc["opponent_team"] = sc.apply(
        lambda r: r["away_team"] if r["inning_topbot"] == "Bot" else r["home_team"],
        axis=1,
    )
    sc["oaa_adj"] = sc["opponent_team"].map(oaa_adj).fillna(0.0)
    return sc.groupby("batter")["oaa_adj"].mean()


def _load_career_quality(path: str) -> dict:
    """Returns dict: player_id (int) -> record dict (includes xwoba_3yr)."""
    if not os.path.exists(path):
        return {}
    with open(path, encoding="cp1252") as f:
        records = json.load(f)
    return {int(r["player_id"]): r for r in records}


def _load_seasonal_patterns(path: str) -> dict:
    """
    Returns dict: player_id (int) -> pattern dict
    Keys: slow_starter, second_half_fader, summer_performer (all bool)

    V-shape pattern = slow_starter AND summer_performer combined.
    This is the strongest buy signal amplifier — player historically
    starts cold AND finishes hot. Both patterns pointing same direction.
    """
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        records = json.load(f)
    return {int(r["player_id"]): r for r in records}


def _seasonal_modifier(
    batter_id: int,
    luck_score: float,
    patterns: dict,
    weight: float = 1.0,
) -> tuple:
    """
    Applies seasonal pattern modifier to luck score.
    Only fires on directional signals (not neutral).

    Returns (modified_score, pattern_label)

    Modifier logic:
      V-shape (slow starter + summer performer):
        Buy signal  -> x1.20 (strongest amplifier — both signals agree)
        Sell signal -> no modifier (empirically: 4/5 times these players improved)

      Slow starter only:
        Buy signal  -> x1.10 (amplify — 100% accurate in backtest, structural buy)

      Summer performer only:
        Buy signal  -> x1.10 (amplify — player historically peaks late)

      Second half fader:
        Sell signal -> x1.15 (amplify — player historically fades)
        Buy signal  -> x0.90 (dampen — may not sustain recovery)
    """
    if batter_id not in patterns:
        return round(luck_score, 4), None

    p = patterns[batter_id]
    slow   = p.get("slow_starter", False)
    fader  = p.get("second_half_fader", False)
    summer = p.get("summer_performer", False)

    is_buy  = luck_score > 0
    is_sell = luck_score < 0

    modifier = 1.0
    label = None

    # V-shape: slow starter + summer performer
    if slow and summer:
        if is_buy:
            modifier = 1.20
            label = "V-shape seasonal (strong buy)"
        # sell: no modifier — empirically V-shape players recover even when signals are negative

    # Slow starter only (no summer surge)
    elif slow and not summer:
        if is_buy:
            modifier = 1.10
            label = "Slow starter (amplified)"

    # Summer performer only (not a slow starter)
    elif summer and not slow:
        if is_buy:
            modifier = 1.10
            label = "Summer performer (amplified)"

    # Second half fader (independent of slow/summer — stacks)
    if fader:
        if is_sell:
            modifier = max(modifier, 1.15)
            label = (label + " + fader" if label else "Second half fader (amplified)")
        elif is_buy:
            modifier = min(modifier, 0.90)
            label = (label + " + fader conflict" if label else "Fader conflict (dampened)")

    # Park change: scale the excess above 1.0 by weight (0.5 = 50% of seasonal signal)
    scaled_modifier = 1.0 + (modifier - 1.0) * weight
    modified = round(luck_score * scaled_modifier, 4)
    return modified, label


# ---------------------------------------------------------------------------
# Park change detection
# ---------------------------------------------------------------------------

def _load_prior_teams(path: str) -> dict:
    """Returns {player_id (int): prior_team (str)} or {} if file absent."""
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {int(k): str(v) for k, v in data.items() if k.lstrip('-').isdigit()}


def _detect_park_change(player_id: int, curr_team: str, prior_teams: dict) -> tuple:
    """
    Returns (park_change: bool, label: str | None).
    Fires only when prior team data is available AND |PF_curr - PF_prior| > 0.03.
    """
    if not prior_teams or player_id not in prior_teams:
        return False, None
    prior_team = prior_teams[player_id]
    if prior_team == curr_team or prior_team == "UNK":
        return False, None
    curr_pf  = PARK_FACTORS.get(curr_team,  DEFAULT_PARK_FACTOR)
    prior_pf = PARK_FACTORS.get(prior_team, DEFAULT_PARK_FACTOR)
    if abs(curr_pf - prior_pf) > 0.03:
        return True, f"Park change ({prior_team}->{curr_team}) - career baseline less reliable"
    return False, None


# ---------------------------------------------------------------------------
# Platoon modifier (Layer 7)
# ---------------------------------------------------------------------------
_PLATOON_MIN_PA    = 30     # minimum current-season PA vs each hand (raised from 15)
_PLATOON_THRESHOLD = 0.040  # delta from career gap required to trigger modifier
_PLATOON_DAMPEN    = 0.90   # multiplier when current is more platoon-skewed than career
_PLATOON_AMPLIFY   = 1.05   # multiplier when current is less platoon-skewed than career
# Fallback static expected gaps used when no career baseline exists.
_PLATOON_FALLBACK_GAP = {"L": -0.019, "R": -0.019}  # from career data mean=-0.019


def _build_platoon_splits(sc_path: str) -> dict:
    """
    Read hitters_statcast.csv and return per-batter dict:
      { batter_id: {"stand": "L"|"R"|"S",
                    "woba_same":  float|None,
                    "woba_opp":   float|None,
                    "xwoba_same": float|None,
                    "xwoba_opp":  float|None,
                    "pa_same": int, "pa_opp": int} }
    Switch hitters and insufficient-PA entries return None split values.
    """
    if not os.path.exists(sc_path):
        return {}
    load_cols = ["batter", "stand", "p_throws", "woba_value", "woba_denom"]
    has_xwoba_col = False
    try:
        peek = pd.read_csv(sc_path, nrows=0)
        if "estimated_woba_using_speedangle" in peek.columns:
            load_cols.append("estimated_woba_using_speedangle")
            has_xwoba_col = True
    except Exception:
        pass

    sc = pd.read_csv(sc_path, usecols=load_cols)
    sc = sc[sc["woba_denom"] > 0].copy()

    result = {}
    for bid, grp in sc.groupby("batter"):
        stand = grp["stand"].iloc[0]
        if stand == "S":
            result[int(bid)] = {"stand": "S", "woba_same": None, "woba_opp": None,
                                "xwoba_same": None, "xwoba_opp": None,
                                "pa_same": 0, "pa_opp": 0}
            continue

        same_rows = grp[grp["p_throws"] == stand]
        opp_rows  = grp[grp["p_throws"] != stand]

        pa_same = int(same_rows["woba_denom"].sum())
        pa_opp  = int(opp_rows["woba_denom"].sum())

        def _mean_or_none(rows, col, min_pa, pa_rows):
            if pa_rows < min_pa:
                return None
            vals = rows[col].dropna()
            return float(vals.mean()) if len(vals) > 0 else None

        woba_same  = _mean_or_none(same_rows, "woba_value",  _PLATOON_MIN_PA, pa_same)
        woba_opp   = _mean_or_none(opp_rows,  "woba_value",  _PLATOON_MIN_PA, pa_opp)
        if has_xwoba_col:
            xwoba_same = _mean_or_none(same_rows, "estimated_woba_using_speedangle",
                                       _PLATOON_MIN_PA, pa_same)
            xwoba_opp  = _mean_or_none(opp_rows,  "estimated_woba_using_speedangle",
                                       _PLATOON_MIN_PA, pa_opp)
        else:
            xwoba_same = xwoba_opp = None

        result[int(bid)] = {
            "stand":      stand,
            "woba_same":  woba_same,
            "woba_opp":   woba_opp,
            "xwoba_same": xwoba_same,
            "xwoba_opp":  xwoba_opp,
            "pa_same":    pa_same,
            "pa_opp":     pa_opp,
        }
    return result


def _platoon_modifier(
    luck_score:     float,
    batter_id:      int,
    platoon_splits: dict,
    career_platoon: dict,
) -> tuple[float, str | None]:
    """
    Returns (modified_luck_score, label|None).

    Compares current-season split gap to player's career baseline gap.
    Uses xwOBA splits when both current and career have them; falls back to wOBA.
    Career baseline from hitter_career_platoon.json; static fallback when missing.
    """
    if luck_score == 0.0:
        return luck_score, None

    info = platoon_splits.get(int(batter_id))
    if not info or info["stand"] == "S":
        return luck_score, None

    # Prefer xwOBA for current-season split (more stable, less BABIP noise)
    x_same = info.get("xwoba_same")
    x_opp  = info.get("xwoba_opp")
    w_same = info.get("woba_same")
    w_opp  = info.get("woba_opp")

    # Use xwOBA if both sides available; fall back to wOBA
    if x_same is not None and x_opp is not None:
        curr_gap = x_same - x_opp
        use_metric = "xwOBA"
    elif w_same is not None and w_opp is not None:
        curr_gap = w_same - w_opp
        use_metric = "wOBA"
    else:
        return luck_score, None  # insufficient current-season PA

    # Career baseline gap for this player
    career_rec = career_platoon.get(int(batter_id))
    if career_rec:
        # Use xwOBA career gap when available and current uses xwOBA
        if use_metric == "xwOBA" and career_rec.get("career_gap_xwoba") is not None:
            career_gap = float(career_rec["career_gap_xwoba"])
        else:
            career_gap = float(career_rec["career_gap_woba"])
    else:
        # No career data — fall back to static league average gap
        stand = info["stand"]
        career_gap = _PLATOON_FALLBACK_GAP.get(stand, -0.019)

    # Delta: how much MORE negative is the current gap vs career?
    # Negative delta = current MORE platoon-dependent than career
    # Positive delta = current LESS platoon-dependent than career
    gap_delta = curr_gap - career_gap

    is_buy  = luck_score > 0
    is_sell = luck_score < 0
    mult    = 1.0
    label   = None

    if gap_delta < -_PLATOON_THRESHOLD:
        # More platoon-skewed than career — luck may be matchup-driven
        if is_buy:
            mult, label = _PLATOON_DAMPEN, "Platoon-driven (dampened)"
        else:
            mult, label = _PLATOON_DAMPEN, "Platoon-strength sell (dampened)"
    elif gap_delta > _PLATOON_THRESHOLD:
        # Less platoon-dependent than career — genuine improvement vs same-hand
        if is_buy:
            mult, label = _PLATOON_AMPLIFY, "Anti-platoon luck (amplified)"
        else:
            mult, label = _PLATOON_AMPLIFY, "Platoon-weak overperformance (amplified)"

    return round(luck_score * mult, 4), label


# ---------------------------------------------------------------------------
# Sample-size confidence multiplier
# ---------------------------------------------------------------------------
def confidence_scale(pa: int, min_pa: int = 30, target_pa: int = 100) -> float:
    """
    Returns a [0, 1] multiplier that fades luck scores toward zero for small
    samples.  pa <= 30 -> 0.0;  pa == 65 -> 0.5;  pa >= 100 -> 1.0
    """
    return min(1.0, max(0.0, (pa - min_pa) / (target_pa - min_pa)))


# ---------------------------------------------------------------------------
# Verdict thresholds
# ---------------------------------------------------------------------------
def assign_verdict(score: float) -> str:
    if score > H_PROD_BUY_LOW:     return "Buy low"
    if score > H_PROD_SLIGHT_BUY:  return "Slight buy"
    if score < H_PROD_SELL_HIGH:   return "Sell high"
    if score < H_PROD_SLIGHT_SELL: return "Slight sell"
    return "Neutral"


# ---------------------------------------------------------------------------
# "This Is Real" — confirmed performers backed by underlying contact quality
# ---------------------------------------------------------------------------
def assign_this_is_real(woba, xwoba, babip, career_babip_val, luck_score, pa) -> str | None:
    """
    Returns 'Confirmed', 'Monitor', or None.
    Confirmed: strong wOBA, contact quality matches, BABIP not inflated, no sell signal.
    Monitor:   strong wOBA but one flag raised (elevated BABIP or weak contact backing).
    """
    try:
        pa = int(pa)
    except (TypeError, ValueError):
        return None
    if pa < 60:
        return None
    try:
        w = float(woba)
        xw = float(xwoba)
    except (TypeError, ValueError):
        return None
    if w < 0.370:
        return None

    try:
        b = float(babip)
    except (TypeError, ValueError):
        b = float("nan")
    try:
        cb = float(career_babip_val)
    except (TypeError, ValueError):
        cb = 0.300
    try:
        ls = float(luck_score)
    except (TypeError, ValueError):
        ls = 0.0

    babip_elevated = (not math.isnan(b)) and (b > cb + 0.020)
    contact_confirmed = xw >= 0.350
    no_sell = ls > -0.050

    if contact_confirmed and not babip_elevated and no_sell:
        return "Confirmed"
    return "Monitor"


# ---------------------------------------------------------------------------
# "This Is Actually Bad" — confirmed underperformers backed by weak contact
# ---------------------------------------------------------------------------
def assign_this_is_actually_bad(
    woba, xwoba, babip, career_babip_val, luck_score, pa, verdict
) -> str | None:
    """
    Returns 'Confirmed', 'Monitor', or None.
    Confirmed: wOBA<=.280, xwOBA<=.300, BABIP at career norm (not luck-suppressed),
               no strong buy signal, PA>=60.
    Monitor:   wOBA<=.300, xwOBA<=.320, BABIP within .020 of career, no buy signal.
    Mutual exclusion: Buy low / Slight buy always return None.
    """
    try:
        pa = int(pa)
    except (TypeError, ValueError):
        return None
    if pa < 60:
        return None
    if verdict in ("Buy low", "Slight buy"):
        return None
    try:
        w  = float(woba)
        xw = float(xwoba)
    except (TypeError, ValueError):
        return None
    if w > 0.300:
        return None
    try:
        b = float(babip)
    except (TypeError, ValueError):
        return None
    if math.isnan(b):
        return None
    try:
        cb = float(career_babip_val)
        if math.isnan(cb):
            cb = 0.300
    except (TypeError, ValueError):
        cb = 0.300
    try:
        ls = float(luck_score)
    except (TypeError, ValueError):
        ls = 0.0

    # True if BABIP is being suppressed by bad luck (>0.030 below career baseline)
    babip_luck_suppressed = b < cb - 0.030

    if w <= 0.280 and xw <= 0.300 and not babip_luck_suppressed and ls > -0.100:
        return "Confirmed"

    if w <= 0.300 and xw <= 0.320 and abs(b - cb) <= 0.020 and ls > -0.080:
        return "Monitor"

    return None


# ---------------------------------------------------------------------------
# Name normalization helper (for ranking file lookup)
# ---------------------------------------------------------------------------
def _norm_name(s: str) -> str:
    try:
        s = str(s).encode("latin1").decode("utf-8")
    except Exception:
        pass
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^a-z ]", "", s.lower()).strip()
    return re.sub(r" +", " ", s)   # collapse "J. P." spacing artifacts


def _squeeze_initials(s: str) -> str:
    """'j p crawford' -> 'jp crawford' — collapse adjacent single-char initials."""
    parts = s.split()
    out, acc = [], ""
    for p in parts:
        if len(p) == 1:
            acc += p
        else:
            if acc:
                out.append(acc)
                acc = ""
            out.append(p)
    if acc:
        out.append(acc)
    return " ".join(out)


# ---------------------------------------------------------------------------
# Ownership tier helpers
# ---------------------------------------------------------------------------
_SUFFIX_RE_OWN = re.compile(r"\b(jr|sr|ii|iii|iv)\b")


def _tier_from_pct(pct: float) -> str:
    if pct >= 60: return "Widely rostered"
    if pct >= 40: return "Commonly rostered"
    if pct >= 20: return "Deep league relevant"
    return "Fringe"


def _tier_from_rank(rank) -> str:
    if rank is None or (isinstance(rank, float) and math.isnan(rank)):
        return "Fringe"
    r = int(rank)
    if r <= 150: return "Widely rostered"
    if r <= 300: return "Commonly rostered"
    if r <= 500: return "Deep league relevant"
    return "Fringe"


# ---------------------------------------------------------------------------
# Age-adjusted BABIP helper
# ---------------------------------------------------------------------------
def _hitter_babip_age_mult(age: int) -> float:
    """Career BABIP decay multiplier for hitters. Contact quality degrades with age."""
    if age >= 39: return 0.88
    if age >= 37: return 0.91
    if age >= 35: return 0.94
    if age >= 32: return 0.97
    return 1.0


# ---------------------------------------------------------------------------
# Tier assignment (sell signals only)
# ---------------------------------------------------------------------------
def assign_tier(luck_score: float, xwoba_gap, verdict: str, career_pa: float, age: int):
    """
    Returns (tier_sell, age_flag).
    Buy/neutral -> (None, None). Slight sell -> Tier 3.

    Tier hierarchy for Sell high:
      Base tier (all ages):
        Veteran Regression:      career_pa > 2000, xwOBA gap > -0.020, luck in [-0.30, -0.15]
        Sell High on Perception: xwOBA gap >= -0.020
        Sell and Move On:        xwOBA gap < -0.020
      Age 35+ override (applied after base tier):
        luck <= -0.20 -> Sell and Move On + "Lucky + age risk"
        luck <= -0.12 -> Sell High on Perception + "Age concern"
        else          -> base tier + "Age 35+ — monitor second half"
    """
    if pd.isna(xwoba_gap):
        xwoba_gap = 0.0
    if verdict in ("Buy low", "Slight buy") or "neutral" in verdict.lower():
        return None, None
    if verdict == "Slight sell":
        return "Slight Regression Expected", None
    if verdict != "Sell high":
        return None, None
    # Compute base tier without age override
    if (career_pa > 2000
            and xwoba_gap > -0.020
            and -0.30 <= luck_score <= -0.15):
        tier, base_flag = "Veteran Regression", ("Age concern" if age in (33, 34) else None)
    elif xwoba_gap >= -0.020:
        tier, base_flag = "Sell High on Perception", None
    else:
        tier, base_flag = "Sell and Move On", None
    if age >= 35:
        if luck_score <= -0.20:
            return "Sell and Move On", "Lucky + age risk"
        elif luck_score <= -0.12:
            return "Sell High on Perception", "Age concern"
        else:
            return tier, "Age 35+ — monitor second half"
    return tier, base_flag


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    dry_run = "--dry-run" in sys.argv
    df = pd.read_csv(INPUT_PATH)

    # ── xwOBA gap ────────────────────────────────────────────────────────────
    if "xwOBA" in df.columns and "wOBA" in df.columns:
        df["xwOBA_gap"] = (df["xwOBA"] - df["wOBA"]).round(4)
    else:
        df["xwOBA_gap"] = 0.0
        print("  Warning: wOBA/xwOBA columns not found — re-run process_stats.py. "
              "xwOBA_gap set to 0 for this run.")

    # ── v5: Derive team and park factor ─────────────────────────────────────
    print("  Deriving batter teams from Statcast data...")
    team_map = _derive_batter_teams(STATCAST_PATH)
    df["team"] = df["batter"].map(team_map).fillna("UNK")
    df["park_factor"] = df["team"].apply(_park_factor)

    # ── Park change detection ────────────────────────────────────────────────
    prior_teams_h = _load_prior_teams(PRIOR_TEAMS_PATH)
    df["park_change"]       = False
    df["park_change_label"] = None
    if prior_teams_h:
        _park_results = df.apply(
            lambda r: _detect_park_change(int(r["batter"]), r["team"], prior_teams_h),
            axis=1,
        )
        df["park_change"]       = _park_results.apply(lambda t: t[0])
        df["park_change_label"] = _park_results.apply(lambda t: t[1])
        n_park = int(df["park_change"].sum())
        print(f"  Park change detection: {n_park} hitters flagged")
    else:
        print("  Park change detection: prior_teams_2025.json not found — skipped")

    # Load career stats early — needed for age-adjusted BABIP baseline
    career_stats: dict = {}
    if os.path.exists(CAREER_CACHE):
        with open(CAREER_CACHE) as f:
            career_stats = {int(k): v for k, v in json.load(f).items()}

    # Career BABIP baseline — individual hitter baseline replaces flat 0.300
    # Also loads career_hard_hit and career_barrel for HH% trend modifier
    _career_babip_h:   dict = {}
    _career_hh_h:      dict = {}
    _career_barrel_h:  dict = {}
    if os.path.exists(CAREER_BABIP_H_PATH):
        with open(CAREER_BABIP_H_PATH) as _f:
            _career_babip_h = json.load(_f)
        for _k, _v in _career_babip_h.items():
            if isinstance(_v, dict):
                if _v.get("career_hard_hit") is not None:
                    _career_hh_h[int(_k)]     = float(_v["career_hard_hit"])
                if _v.get("career_barrel") is not None:
                    _career_barrel_h[int(_k)] = float(_v["career_barrel"])
        print(f"  Career hitter BABIP loaded: {len(_career_babip_h):,} hitters")

    # Career O-swing baseline — for sell-side chase confirmation modifier
    _career_oswing_h: dict = {}
    if os.path.exists(CAREER_DISCIPLINE_H_PATH):
        with open(CAREER_DISCIPLINE_H_PATH) as _df_disc:
            _raw_disc = json.load(_df_disc)
        for _k, _v in _raw_disc.items():
            if isinstance(_v, dict) and _v.get("career_o_swing") is not None:
                _career_oswing_h[int(_k)] = float(_v["career_o_swing"])
        print(f"  Career O-swing loaded: {len(_career_oswing_h):,} hitters")

    # Career K% / pull rate baselines — informational + conservative buy dampener
    _career_k_pull: dict = {}
    if os.path.exists(CAREER_K_PULL_PATH):
        with open(CAREER_K_PULL_PATH) as _kp_f:
            _career_k_pull = {int(k): v for k, v in json.load(_kp_f).items()}
        print(f"  Career K%/pull loaded: {len(_career_k_pull):,} hitters")

    # Sprint speed trajectory (2022-2025 YoY delta)
    _sprint_speed_h: dict = {}
    if os.path.exists(SPRINT_SPEED_PATH):
        with open(SPRINT_SPEED_PATH) as _ss_f:
            _sprint_speed_h = {int(k): v for k, v in json.load(_ss_f).items()}
        print(f"  Sprint speed loaded: {len(_sprint_speed_h):,} players")

    # Launch angle baselines (display-only — no model weight)
    _launch_angle_h: dict = {}
    if os.path.exists(LAUNCH_ANGLE_PATH):
        with open(LAUNCH_ANGLE_PATH) as _la_f:
            _launch_angle_h = {int(k): v for k, v in json.load(_la_f).items()}
        print(f"  Launch angle loaded: {len(_launch_angle_h):,} players")

    # Financial motivation cohort data (display only — no model weight)
    # Columns: batter_id, annual_salary_m, years_remaining, prove_it, cohort_override
    _contract_data: dict = {}
    if os.path.exists(CONTRACT_YEAR_PATH):
        try:
            _cy_df = pd.read_csv(CONTRACT_YEAR_PATH, comment="#")
            for _, _cr in _cy_df.iterrows():
                _bid = int(_cr["batter_id"]) if pd.notna(_cr.get("batter_id")) else None
                if _bid is None:
                    continue
                _contract_data[_bid] = {
                    "annual_salary_m": float(_cr["annual_salary_m"])
                        if pd.notna(_cr.get("annual_salary_m")) else None,
                    "years_remaining": int(_cr["years_remaining"])
                        if pd.notna(_cr.get("years_remaining")) else None,
                    "prove_it":        bool(int(_cr["prove_it"]))
                        if pd.notna(_cr.get("prove_it")) else False,
                    "cohort_override": str(_cr["cohort_override"]).strip()
                        if pd.notna(_cr.get("cohort_override")) else None,
                }
            print(f"  Contract data: {len(_contract_data):,} players loaded")
        except Exception as _ce:
            print(f"  Contract data: load error ({_ce})")

    df["career_babip"] = df["batter"].apply(
        lambda bid: (
            float(_career_babip_h[str(int(bid))]["career_babip"])
            if pd.notna(bid) and str(int(bid)) in _career_babip_h
               and _career_babip_h[str(int(bid))]["career_babip"] is not None
            else None
        )
    )
    n_with_career_h = df["career_babip"].notna().sum()
    n_fallback_h    = df["career_babip"].isna().sum()
    print(f"  Career BABIP: {n_with_career_h} hitters with individual baseline, "
          f"{n_fallback_h} using flat {LEAGUE_AVG_BABIP}")
    df["babip_baseline"] = df["career_babip"].fillna(LEAGUE_AVG_BABIP)

    # Age-adjusted career BABIP: older hitters' contact quality declines
    _byr_h = {k: int(v.get("birth_year") or 0) for k, v in career_stats.items()}
    df["_age_babip"] = df["batter"].apply(
        lambda i: SEASON_YEAR - _byr_h[i] if i in _byr_h and _byr_h[i] > 0 else 0
    )
    df["age_adj_career_babip"] = df.apply(
        lambda r: round(r["babip_baseline"] * _hitter_babip_age_mult(int(r["_age_babip"])), 4)
        if pd.notna(r["career_babip"]) and r["_age_babip"] > 0
        else r["babip_baseline"],
        axis=1,
    )
    n_age_adj_h = int((df["age_adj_career_babip"] != df["babip_baseline"]).sum())
    print(f"  Age-adjusted BABIP: {n_age_adj_h} hitters adjusted (age 32+)")
    df["park_adj_babip_expected"] = (df["age_adj_career_babip"] * df["park_factor"]).round(4)
    df["park_adj_hrfb_expected"]  = (LEAGUE_AVG_HRFB  * df["park_factor"]).round(4)

    # ── OAA defensive adjustment to expected BABIP ───────────────────────────
    oaa_adj_map = _load_oaa_adj(TEAM_OAA_PATH)
    if oaa_adj_map:
        opp_oaa = _derive_opponent_oaa_adj(STATCAST_PATH, oaa_adj_map)
        df["oaa_babip_adj"] = df["batter"].map(opp_oaa).fillna(0.0)
        df["park_adj_babip_expected"] = (
            df["park_adj_babip_expected"] + df["oaa_babip_adj"]
        ).round(4)
        affected = (df["oaa_babip_adj"] != 0.0).sum()
        top_n    = (df["oaa_babip_adj"] < 0).sum()
        bot_n    = (df["oaa_babip_adj"] > 0).sum()
        print(f"  OAA BABIP adj: {affected} players affected "
              f"({top_n} reduced vs elite D, {bot_n} raised vs poor D)")
    else:
        df["oaa_babip_adj"] = 0.0
        print("  OAA BABIP adj: skipped (team_oaa_2025.csv not found)")

    # ── v5: Load career quality for 3yr xwOBA and pseudo wRC+ ───────────────
    cq_dict = _load_career_quality(CAREER_QUALITY_CACHE)
    df["xwoba_3yr"] = df["batter"].map(
        lambda i: float(cq_dict[i]["xwoba_3yr"])
        if i in cq_dict and not pd.isna(cq_dict[i].get("xwoba_3yr", float("nan")))
        else float("nan")
    )
    df["wrc_plus_3yr"] = df.apply(
        lambda r: round(
            (r["xwoba_3yr"] / LEAGUE_AVG_XWOBA) * r["park_factor"] * 100, 1
        ) if not math.isnan(r["xwoba_3yr"]) else 100.0,
        axis=1,
    )
    df["quality_tier"] = df["wrc_plus_3yr"].apply(lambda w: _quality_tier(w)[1])

    # ── GB rate adjustment to expected BABIP ─────────────────────────────────
    if "gb_rate" in df.columns:
        gb_high = df["gb_rate"] > 0.50
        gb_low  = df["gb_rate"] < 0.35
        df.loc[gb_high, "park_adj_babip_expected"] = (
            df.loc[gb_high, "park_adj_babip_expected"] - 0.010
        ).round(4)
        df.loc[gb_low, "park_adj_babip_expected"] = (
            df.loc[gb_low, "park_adj_babip_expected"] + 0.008
        ).round(4)
        print(f"  GB rate BABIP adj: {gb_high.sum()} high-GB (-0.010), "
              f"{gb_low.sum()} low-GB (+0.008)")

    # ── Component 1: BABIP with park-adjusted expected + contextual mods ─────
    has_hhr = "hard_hit_rate" in df.columns
    babip_comp = (df["BABIP"] - df["park_adj_babip_expected"]) * -3.000
    if "o_swing_rate" in df.columns:
        babip_comp = babip_comp * df.apply(
            lambda r: _chase_modifier(r["o_swing_rate"], r["BABIP"], int(r["PA"])),
            axis=1,
        )
    babip_comp = babip_comp * df.apply(
        lambda r: _zcon_babip_modifier(
            r["z_contact_rate"], r["BABIP"],
            r["hard_hit_rate"] if has_hhr else float("nan"),
            int(r["PA"]),
            _career_hh_h.get(int(r["batter"]), 0.370),
        ),
        axis=1,
    )

    # ── Component 2: HR/FB with park-adjusted expected + pull modifier ────────
    hrfb_comp = (df["hr_fb_rate"] - df["park_adj_hrfb_expected"]) * -0.150
    if "pull_rate" in df.columns:
        hrfb_comp = hrfb_comp * df.apply(
            lambda r: _pull_modifier(
                r["pull_rate"],
                r["hard_hit_rate"] if has_hhr else float("nan"),
                int(r["PA"]),
                _career_hh_h.get(int(r["batter"]), 0.370),
            ),
            axis=1,
        )

    # ── Component 3: Z-contact vs league average (unchanged) ─────────────────
    zcon_comp = (df["z_contact_rate"] - 0.880) * -0.030

    # ── Component 4: xwOBA gap (unchanged) ───────────────────────────────────
    xwoba_comp = df["xwOBA_gap"] * 1.000

    df["luck_score"] = babip_comp + hrfb_comp + zcon_comp + xwoba_comp

    # ── Sample-size confidence multiplier ────────────────────────────────────
    df["luck_score"] = (
        df.apply(lambda r: r["luck_score"] * confidence_scale(int(r["PA"])), axis=1)
        .round(4)
    )

    # ── v5: Playing time discount ─────────────────────────────────────────────
    p90_pa = float(df["PA"].quantile(0.90))
    df["luck_score"] = df.apply(
        lambda r: round(r["luck_score"] * _playing_time_scale(int(r["PA"]), p90_pa), 4),
        axis=1,
    )

    # ── Quality validators: sweet spot + exit velo trend (buy signals only) ──
    buy_mask = df["luck_score"] > 0

    # Sweet spot modifier
    if "sweet_spot_rate" in df.columns:
        high_ss = buy_mask & (df["sweet_spot_rate"] > 0.12)
        low_ss  = buy_mask & (df["sweet_spot_rate"] < 0.06)
        df.loc[high_ss, "luck_score"] = (df.loc[high_ss, "luck_score"] * 1.05).round(4)
        df.loc[low_ss,  "luck_score"] = (df.loc[low_ss,  "luck_score"] * 0.95).round(4)
        print(f"  Sweet spot: {high_ss.sum()} buy signals boosted x1.05, "
              f"{low_ss.sum()} dampened x0.95")

    # Exit velo trend modifier: current EV vs career baseline
    if "avg_exit_velocity" in df.columns:
        def _ev_mult(row):
            if row["luck_score"] <= 0:
                return 1.0
            career_ev = (career_stats.get(int(row["batter"])) or {}).get("avg_exit_velocity")
            if career_ev is None or pd.isna(row["avg_exit_velocity"]):
                return 1.0
            ev_below = (row["avg_exit_velocity"] - career_ev) < -1.0
            low_ss   = pd.notna(row.get("sweet_spot_rate")) and row["sweet_spot_rate"] < 0.08
            if ev_below and low_ss:
                return 0.85   # both signals: full dampener
            elif ev_below or low_ss:
                return 0.93   # one signal: mild dampener
            return 1.0

        ev_mults = df.apply(_ev_mult, axis=1)
        ev_full    = (ev_mults == 0.85).sum()
        ev_mild    = (ev_mults == 0.93).sum()
        ev_neither = (ev_mults == 1.0).sum()
        df["luck_score"] = (df["luck_score"] * ev_mults).round(4)
        print(f"  Exit velo trend: {ev_full} both conditions x0.85 | "
              f"{ev_mild} one condition x0.93 | {ev_neither} no dampener")

    # ── Plate discipline modifier (buy signals only) ──────────────────────────
    if "bb_rate" in df.columns and "k_rate" in df.columns:
        buy_mask = df["luck_score"] > 0
        elite_disc = buy_mask & (df["bb_rate"] > 0.10) & (df["k_rate"] < 0.18)
        poor_disc  = buy_mask & ((df["bb_rate"] < 0.06) | (df["k_rate"] > 0.28))
        df.loc[elite_disc, "luck_score"] = (df.loc[elite_disc, "luck_score"] * 1.08).round(4)
        df.loc[poor_disc,  "luck_score"] = (df.loc[poor_disc,  "luck_score"] * 0.88).round(4)
        print(f"  Plate discipline: {elite_disc.sum()} elite x1.08, "
              f"{poor_disc.sum()} poor x0.88 (buy signals only)")

    # ── K% / pull rate evolution modifier (buy signals only) ────────────────────
    # Additive penalty Version D: each flag subtracts a calibrated flat amount.
    # k_flag (K spike): -H_KP_K_PENALTY  |  pull_flag (pull drop): -H_KP_PULL_PENALTY
    # Penalties accumulate in _buy_penalty and are applied in a combined pass below.
    df["_buy_penalty"] = 0.0  # accumulator for all additive buy-side penalties
    if _career_k_pull:
        buy_mask = df["luck_score"] > 0
        _kp_k_flag    = df["batter"].apply(lambda b: _career_k_pull.get(int(b), {}).get("k_flag",    False))
        _kp_pull_flag = df["batter"].apply(lambda b: _career_k_pull.get(int(b), {}).get("pull_flag", False))
        _kp_delta_k   = df["batter"].apply(lambda b: _career_k_pull.get(int(b), {}).get("k_pct_delta"))
        _kp_delta_pull = df["batter"].apply(lambda b: _career_k_pull.get(int(b), {}).get("pull_pct_delta"))

        df.loc[buy_mask & _kp_k_flag,    "_buy_penalty"] += H_KP_K_PENALTY
        df.loc[buy_mask & _kp_pull_flag, "_buy_penalty"] += H_KP_PULL_PENALTY

        df["k_pct_delta"]  = _kp_delta_k
        df["pull_pct_delta"] = _kp_delta_pull
        df["k_flag"]       = _kp_k_flag
        df["pull_flag"]    = _kp_pull_flag

        n_k    = int((buy_mask & _kp_k_flag).sum())
        n_pull = int((buy_mask & _kp_pull_flag).sum())
        print(f"  K%/pull flags (additive -D): {n_k} K-flag (-{H_KP_K_PENALTY}) | "
              f"{n_pull} pull-flag (-{H_KP_PULL_PENALTY}) (buy signals only)")
    else:
        df["k_pct_delta"]   = float("nan")
        df["pull_pct_delta"] = float("nan")
        df["k_flag"]        = False
        df["pull_flag"]     = False
        print("  K%/pull modifier: skipped (hitter_career_k_pull.json not found)")

    # ── Hard hit rate delta modifier (buy signals only) ───────────────────────
    # Flag: curr hard_hit_rate < career - 3pp AND PA >= 50.
    # Additive penalty Version D: -H_HH_PENALTY added to _buy_penalty accumulator.
    HH_DROP_THRESH   = 0.030
    HH_MIN_PA        = 50
    _hh_eligible = (
        df["luck_score"] > 0
        & df["batter"].apply(lambda b: int(b) in _career_hh_h)
        & df["hard_hit_rate"].notna()
        & (df["PA"] >= HH_MIN_PA)
    )
    df["hh_rate_delta"] = float("nan")
    df["hh_flag"]       = False
    if _hh_eligible.any() and "hard_hit_rate" in df.columns:
        _hh_career = df["batter"].apply(lambda b: _career_hh_h.get(int(b), float("nan")))
        _hh_delta  = df["hard_hit_rate"] - _hh_career
        df["hh_rate_delta"] = _hh_delta.where(df["batter"].apply(lambda b: int(b) in _career_hh_h)).round(4)
        _hh_flag_mask = _hh_eligible & (_hh_delta < -HH_DROP_THRESH)
        df.loc[_hh_flag_mask, "_buy_penalty"] += H_HH_PENALTY
        df.loc[_hh_flag_mask, "hh_flag"]      = True
        n_hh = int(_hh_flag_mask.sum())
        print(f"  Hard hit rate flag (additive -D): {n_hh} buy signals flagged -"
              f"{H_HH_PENALTY} (curr < career - {HH_DROP_THRESH*100:.0f}pp, PA >= {HH_MIN_PA})")
    else:
        print("  Hard hit rate modifier: no eligible buy signals or career data missing")

    # ── Sprint speed cliff modifier (buy signals only) ────────────────────────
    # Year-over-year sprint speed decline > 0.3 ft/sec signals athleticism regression.
    # Additive penalty Version D: -H_SPEED_PENALTY added to _buy_penalty accumulator.
    SPEED_CLIFF_THRESH = 0.3
    df["speed_flag"]  = False
    df["speed_trend"] = float("nan")
    if _sprint_speed_h:
        _buy_mask_spd = df["luck_score"] > 0
        for _idx, _row in df[_buy_mask_spd].iterrows():
            _bid = int(_row["batter"])
            if _bid not in _sprint_speed_h:
                continue
            _srec = _sprint_speed_h[_bid]
            _yoy  = _srec.get("yoy_delta")
            df.at[_idx, "speed_trend"] = _yoy if _yoy is not None else float("nan")
            if _srec.get("speed_flag"):  # YoY drop > 0.3 ft/s
                df.at[_idx, "_buy_penalty"] += H_SPEED_PENALTY
                df.at[_idx, "speed_flag"]   = True
        n_spd = int(df["speed_flag"].sum())
        print(f"  Sprint speed flag (additive -D): {n_spd} buy signals flagged "
              f"-{H_SPEED_PENALTY} (YoY drop > {SPEED_CLIFF_THRESH} ft/s)")
    else:
        print("  Sprint speed modifier: skipped (hitter_sprint_speed.json not found)")

    # ── Chase rate rise — buy-side dampener ───────────────────────────────────
    # Elevated chase rate vs career baseline signals contact deterioration.
    # Threshold 3pp rise. Only fires when PA >= 50 for stability.
    # Additive penalty Version D: -H_CHASE_PENALTY added to _buy_penalty accumulator.
    CHASE_BUY_THRESH = 0.030
    CHASE_MIN_PA_BUY = 50
    df["chase_flag"]  = False
    df["chase_delta"] = float("nan")
    if "o_swing_rate" in df.columns and _career_oswing_h:
        _buy_mask_chase = (df["luck_score"] > 0) & (df["PA"] >= CHASE_MIN_PA_BUY)
        for _idx, _row in df[_buy_mask_chase].iterrows():
            _bid = int(_row["batter"])
            if _bid not in _career_oswing_h:
                continue
            _curr_os = float(_row["o_swing_rate"]) if pd.notna(_row["o_swing_rate"]) else float("nan")
            if math.isnan(_curr_os):
                continue
            _os_gap = _curr_os - _career_oswing_h[_bid]
            df.at[_idx, "chase_delta"] = round(_os_gap, 4)
            if _os_gap > CHASE_BUY_THRESH:
                # AGE WEIGHTS — estimated priors, not empirically calibrated.
                # Young hitters often show chase spikes as normal development noise.
                _age_chase = SEASON_YEAR - _byr_h.get(_bid, 0) if _byr_h.get(_bid, 0) else 0
                if 0 < _age_chase <= 25:
                    _chase_weight = H_CHASE_AGE_WEIGHT_U25
                elif _age_chase in (26, 27):
                    _chase_weight = H_CHASE_AGE_WEIGHT_26_27
                else:
                    _chase_weight = 1.0
                df.at[_idx, "_buy_penalty"] += H_CHASE_PENALTY * _chase_weight
                df.at[_idx, "chase_flag"]   = True
        n_chase = int(df["chase_flag"].sum())
        print(f"  Chase rise flag (additive -D, age-weighted): {n_chase} buy signals flagged "
              f"(curr > career + {CHASE_BUY_THRESH*100:.0f}pp, PA >= {CHASE_MIN_PA_BUY})")
    else:
        print("  Chase rise modifier: skipped (o_swing_rate or career O-swing not available)")

    # ── Apply combined additive buy penalty (Version D architecture) ──────────
    # All flag-based buy dampeners have accumulated in _buy_penalty.
    # Apply capped total in one pass to avoid order-dependency.
    _buy_active = (df["luck_score"] > 0) & (df["_buy_penalty"] > 0)
    if _buy_active.any():
        _capped_pen = df.loc[_buy_active, "_buy_penalty"].clip(upper=H_MAX_COMBINED_PEN)
        df.loc[_buy_active, "luck_score"] = (
            df.loc[_buy_active, "luck_score"] - _capped_pen
        ).round(4)
        n_modified  = int(_buy_active.sum())
        n_capped    = int((df.loc[_buy_active, "_buy_penalty"] > H_MAX_COMBINED_PEN).sum())
        total_flags = int(df[["k_flag","pull_flag","hh_flag","speed_flag","chase_flag"]].any(axis=1).sum())
        print(f"  Combined additive penalty applied: {n_modified} buy signals dampened"
              f"  ({n_capped} capped at -{H_MAX_COMBINED_PEN})")
        print(f"  Total flagged (any flag): {total_flags}")

    # ── Financial motivation cohort classification (display only — no model weight) ─
    # Five cohorts based on financial incentive structure, not simple contract year binary.
    # Requires data from contract_year_2026.csv (annual_salary_m, years_remaining, prove_it).
    # Falls back to age-only heuristics when contract data is unavailable.
    #
    # Cohort 1 — Generational Payday Window:
    #   Age 25-31, approaching FA (years_remaining <= 2 OR pre-arb with no data).
    #   Maximum financial motivation — first big contract approaching.
    # Cohort 2 — Prove-It:
    #   Any age, manually flagged prove_it=1 (1-2yr deal after injury or down year).
    #   Rebuilding market value under pressure.
    # Cohort 3 — Already Secured:
    #   annual_salary_m >= 20.0 AND years_remaining >= 3.
    #   Financial security essentially complete; marginal value of great season lower.
    # Cohort 4 — Post-Prime Any Contract:
    #   Age 33+, not Cohort 2 or 3. Physical decline may override financial motivation.
    # Cohort 5 — Comfortable Mid-Contract (baseline):
    #   Age 28-32, multi-year deal active, not FA-bound. Neutral motivation assumption.

    # contract_year = True when years_remaining == 0 (final year of deal)
    df["contract_year"] = df["batter"].apply(
        lambda b: _contract_data.get(int(b), {}).get("years_remaining") == 0
        if pd.notna(b) else False
    )

    def _assign_cohort(row) -> str:
        age = int(row.get("age", 0))
        if age <= 0:
            return "unknown"
        bid = int(row["batter"]) if pd.notna(row.get("batter")) else -1
        cd  = _contract_data.get(bid, {})

        # Manual override wins
        override = cd.get("cohort_override")
        if override:
            return override

        salary  = cd.get("annual_salary_m")   # float or None
        yr_rem  = cd.get("years_remaining")   # int or None
        prove_it = bool(cd.get("prove_it", False))

        # Cohort 2 — Prove-It (manual flag, any age)
        if prove_it:
            return "2-prove-it"

        # Cohort 3 — Already Secured (salary data required)
        if salary is not None and yr_rem is not None:
            if salary >= 20.0 and yr_rem >= 3:
                return "3-secured"

        # Cohort 4 — Post-Prime (age alone, no data needed)
        if age >= 33:
            return "4-post-prime"

        # Cohort 1 — Generational Payday (age 25-31, approaching FA)
        if 25 <= age <= 31:
            if yr_rem is not None and yr_rem <= 2:
                return "1-payday"
            if yr_rem is None and age < 28:
                return "1-payday"  # pre-arb — always within 2yr of FA eligibility
        elif age < 25:
            return "1-payday"  # definitely pre-arb

        # Cohort 5 — Comfortable Mid-Contract (default for 28-32 with data or no signal)
        return "5-mid-contract"

    # contract_cohort applied after age is computed — see below

    # ── Platoon modifier (Layer 7) ────────────────────────────────────────────
    # Uses career baseline from hitter_career_platoon.json (built by
    # build_hitter_career_platoon.py). Compares current split gap to career gap.
    # PA minimum raised to 30 vs each hand. Prefers xwOBA over wOBA.
    sc_path_h = os.path.join(BASE_DIR, "hitters_statcast.csv")
    platoon_splits  = _build_platoon_splits(sc_path_h)
    career_platoon  = {}
    if os.path.exists(CAREER_PLATOON_PATH):
        with open(CAREER_PLATOON_PATH) as _f:
            career_platoon = {int(k): v for k, v in json.load(_f).items()}
        print(f"  Career platoon loaded: {len(career_platoon):,} batters")
    else:
        print(f"  Career platoon: {CAREER_PLATOON_PATH} not found — using static fallback gaps")

    if platoon_splits:
        plat_results = df.apply(
            lambda r: _platoon_modifier(
                r["luck_score"], r["batter"], platoon_splits, career_platoon
            ),
            axis=1,
        )
        df["luck_score"]       = plat_results.apply(lambda t: t[0])
        df["platoon_modifier"] = plat_results.apply(lambda t: t[1])
        plat_dampened  = df["platoon_modifier"].str.contains("dampened",  na=False).sum()
        plat_amplified = df["platoon_modifier"].str.contains("amplified", na=False).sum()
        n_career_used  = sum(
            1 for bid in df["batter"]
            if int(bid) in career_platoon and platoon_splits.get(int(bid)) is not None
        )
        print(f"  Platoon modifier: {plat_dampened} dampened, {plat_amplified} amplified"
              f"  ({n_career_used} using career baseline, {len(platoon_splits)-n_career_used} fallback)")
    else:
        df["platoon_modifier"] = None
        print("  Platoon modifier: hitters_statcast.csv not found — skipped")

    df["career_pa"]  = df["batter"].map(lambda i: float((career_stats.get(i) or {}).get("career_pa") or 0))
    df["birth_year"] = df["batter"].map(lambda i: int((career_stats.get(i) or {}).get("birth_year") or 0))
    df["age"] = df["birth_year"].apply(lambda by: SEASON_YEAR - by if by > 0 else 0)

    # ── Financial motivation cohort (needs age — apply after age is set) ──────
    df["contract_cohort"] = df.apply(_assign_cohort, axis=1)
    n_cy = int(df["contract_year"].sum())
    coh_counts = df["contract_cohort"].value_counts().sort_index().to_dict()
    print(f"  Contract cohorts: {coh_counts} | contract_year (final yr): {n_cy}")

    # ── Rising boost (+0.02): age < 28 buy-signal players only ───────────────
    rising_mask = (df["age"] > 0) & (df["age"] < 28) & (df["luck_score"] > 0)
    df.loc[rising_mask, "luck_score"] = (df.loc[rising_mask, "luck_score"] + 0.02).round(4)

    # ── Phase C: Seasonal pattern modifier ─────────────────────────────────
    seasonal_patterns = _load_seasonal_patterns(SEASONAL_PATTERNS_CACHE)

    if seasonal_patterns:
        seasonal_results = df.apply(
            lambda r: _seasonal_modifier(
                int(r["batter"]),
                r["luck_score"],
                seasonal_patterns,
                weight=0.50 if r.get("park_change") else 1.0,
            ),
            axis=1,
        )
        df["luck_score"]       = seasonal_results.apply(lambda t: t[0])
        df["seasonal_pattern"] = seasonal_results.apply(lambda t: t[1])

        pattern_count = df["seasonal_pattern"].notna().sum()
        vshape_count  = df["seasonal_pattern"].str.contains("V-shape", na=False).sum()
        print(f"  Seasonal patterns applied: {pattern_count} players affected")
        print(f"  V-shape amplifications:    {vshape_count}")
    else:
        df["seasonal_pattern"] = None
        print("  Warning: seasonal_patterns.json not found -- Phase C skipped")

    # ── v5: Quality tier multiplier (buy signals only) ────────────────────────
    # Raw score after confidence + PT scale is the reference for the cap.
    df["_luck_raw_for_cap"] = df["luck_score"].copy()

    df["luck_score"] = df.apply(
        lambda r: round(r["luck_score"] * _quality_tier(r["wrc_plus_3yr"])[0], 4)
        if r["luck_score"] > 0 else r["luck_score"],
        axis=1,
    )

    # ── v5: Amplification cap (relative to pre-quality raw) ─────────────────
    cap_results = df.apply(
        lambda r: _amplification_cap(r["luck_score"], r["_luck_raw_for_cap"]),
        axis=1,
    )
    df["luck_score"]              = cap_results.apply(lambda t: t[0])
    df["amplification_cap_applied"] = cap_results.apply(lambda t: t[1])
    df.drop(columns=["_luck_raw_for_cap"], inplace=True)

    df["verdict"] = df["luck_score"].apply(assign_verdict)

    # Slight buy confidence gates (updated thresholds — backtest analysis Apr 25 2026):
    #   1. xwOBA gap < 0.030: BABIP-only signal with no contact quality support
    #   2. xwOBA >= 0.380: already-good hitter, no upside regression target
    #   Both gates confirmed by outcome distribution: 16.7% acc (low gap) / 25% acc (high xwOBA)
    _sb_mask = (
        (df["verdict"] == "Slight buy")
        & (
            (df["xwOBA_gap"].fillna(0.0) < H_PROD_SB_MIN_XWOBA_GAP)
            | (df["xwOBA"].fillna(0.0) >= H_PROD_SB_MAX_XWOBA)
        )
    )
    if _sb_mask.any():
        df.loc[_sb_mask, "verdict"] = "Neutral"

    # ── Sell-side chase confirmation modifier ─────────────────────────────────
    # Elevated chase vs career baseline confirms sell signal (sustained luck via
    # weak contact, not true quality). Only modifies Sell high / Slight sell.
    # No effect on buy or neutral signals.
    # gap > 0.060: ×1.15 (high spike — strong confirmation)
    # gap > 0.040: ×1.10 (moderate elevation — confirmed)
    df["chase_signal"] = None
    if "o_swing_rate" in df.columns and _career_oswing_h:
        _sell_mask = df["verdict"].isin(["Sell high", "Slight sell"])
        for _idx, _row in df[_sell_mask].iterrows():
            _bid = int(_row["batter"])
            if _bid not in _career_oswing_h:
                continue
            _curr  = float(_row["o_swing_rate"]) if pd.notna(_row["o_swing_rate"]) else float("nan")
            if math.isnan(_curr):
                continue
            _chase_gap = _curr - _career_oswing_h[_bid]
            if _chase_gap > 0.060:
                df.at[_idx, "luck_score"]   = round(df.at[_idx, "luck_score"] * 1.15, 4)
                df.at[_idx, "chase_signal"] = "High chase spike — strong sell"
            elif _chase_gap > 0.040:
                df.at[_idx, "luck_score"]   = round(df.at[_idx, "luck_score"] * 1.10, 4)
                df.at[_idx, "chase_signal"] = "Elevated chase — sell confirmed"
        _n_confirmed = df["chase_signal"].notna().sum()
        print(f"  Chase sell-side: {_n_confirmed} sell signals confirmed/amplified")

    # ── This Is Real — confirmed performers backed by contact quality ─────────
    df["this_is_real"] = df.apply(
        lambda r: assign_this_is_real(
            r["wOBA"], r["xwOBA"], r["BABIP"],
            r.get("career_babip", float("nan")),
            r["luck_score"], r["PA"],
        ),
        axis=1,
    )

    # ── This Is Actually Bad — poor stats backed by weak contact quality ──────
    df["this_is_actually_bad"] = df.apply(
        lambda r: assign_this_is_actually_bad(
            r["wOBA"], r["xwOBA"], r["BABIP"],
            r.get("career_babip", float("nan")),
            r["luck_score"], r["PA"],
            r["verdict"],
        ),
        axis=1,
    )
    _n_bad_conf = (df["this_is_actually_bad"] == "Confirmed").sum()
    _n_bad_mon  = (df["this_is_actually_bad"] == "Monitor").sum()
    print(f"  This Is Actually Bad: {_n_bad_conf} confirmed, {_n_bad_mon} monitor")

    # ── fp_rank: live FP ROS rank preferred; stale manual CSV as fallback ──────
    # Primary: fp_ros_rank from player_ownership_2026.csv (scraped by
    #          fetch_fantasypros_ownership.py — hitter rank among all hitters)
    # Fallback: data/fantasy_rankings_hitters_2026.csv (40-row manual export)
    _fp_rank_lk: dict = {}
    _fp_rank_source = "none"
    if os.path.exists(OWNERSHIP_PATH):
        _own_rank_df = pd.read_csv(OWNERSHIP_PATH)
        if "fp_ros_rank" in _own_rank_df.columns:
            for _, _rr in _own_rank_df.iterrows():
                _rv = _rr.get("fp_ros_rank")
                if pd.notna(_rv) and str(_rv).strip():
                    try:
                        _fp_rank_lk[_norm_name(str(_rr["player_name"]))] = int(float(_rv))
                    except (ValueError, TypeError):
                        pass
            if _fp_rank_lk:
                _fp_rank_source = f"fp_ros_rank ({len(_fp_rank_lk)} players)"
    if not _fp_rank_lk and os.path.exists(FANTASY_RANKINGS_H_PATH):
        _rankings_df = pd.read_csv(FANTASY_RANKINGS_H_PATH)
        for _, _rr in _rankings_df.iterrows():
            _fp_rank_lk[_norm_name(str(_rr["Player Name"]))] = int(_rr["Rank"])
        _fp_rank_source = f"manual CSV ({len(_fp_rank_lk)} players)"
    print(f"  fp_rank source: {_fp_rank_source}")
    df["fp_rank"] = df["name"].apply(
        lambda n: _fp_rank_lk.get(_norm_name(str(n)), None)
    )

    # ── Ownership tier — live ESPN data preferred, fp_rank proxy as fallback ──
    if os.path.exists(OWNERSHIP_PATH):
        _own_df = pd.read_csv(OWNERSHIP_PATH)
        _own_pct_map: dict = {}
        for _, _or in _own_df.iterrows():
            _onorm = _norm_name(str(_or["player_name"]))
            _opct  = float(_or["owned_pct"])
            _own_pct_map[_onorm] = _opct
            _stripped = _SUFFIX_RE_OWN.sub("", _onorm).strip()
            if _stripped != _onorm and _stripped not in _own_pct_map:
                _own_pct_map[_stripped] = _opct
        def _lookup_pct(name: str) -> float | None:
            norm = _norm_name(str(name))
            pct = _own_pct_map.get(norm)
            if pct is None:
                pct = _own_pct_map.get(_squeeze_initials(norm))
            return pct

        df["owned_pct"] = df["name"].apply(_lookup_pct)
        df["ownership_tier"] = df["owned_pct"].apply(
            lambda p: _tier_from_pct(float(p)) if p is not None and not pd.isna(p) else "Fringe"
        )
        _n_live = df["owned_pct"].notna().sum()
        _n_wide = (df["ownership_tier"] == "Widely rostered").sum()
        print(f"  Ownership data loaded: {len(_own_pct_map):,} players "
              f"(fetched {_own_df['fetched_date'].iloc[0]})")
        print(f"  Matched {_n_live} hitters | Widely rostered: {_n_wide}")
    else:
        print("  Ownership data not found — using rank proxy")
        df["owned_pct"] = None
        df["ownership_tier"] = df["fp_rank"].apply(_tier_from_rank)
        _n_rostered = (df["ownership_tier"] != "Fringe").sum()
        print(f"  Rank proxy: {_n_rostered} players ranked "
              f"(rankings file has {len(_fp_rank_lk)} entries)")

    # ── Tier assignment ───────────────────────────────────────────────────────
    tiers = df.apply(
        lambda r: assign_tier(r["luck_score"], r["xwOBA_gap"], r["verdict"], r["career_pa"], r["age"]),
        axis=1,
    )
    df["tier_sell"] = tiers.apply(lambda t: t[0])
    df["age_flag"]  = tiers.apply(lambda t: t[1])

    df.sort_values("luck_score", ascending=False, inplace=True)
    df.reset_index(drop=True, inplace=True)
    df.drop(columns=["_buy_penalty"], errors="ignore", inplace=True)

    # ── Launch Angle YoY Delta (display-only — no effect on luck_score) ─────────
    # Signals whether a player is hitting the ball higher or lower than career norm.
    # Positive = elevated angle (more air contact); Negative = flatter/ground contact.
    LA_UP_THRESH   = 3.0   # degrees above career avg to flag trending_up
    LA_DOWN_THRESH = -3.0  # degrees below career avg to flag trending_down

    df["la_delta"]        = float("nan")
    df["current_la_avg"]  = float("nan")
    df["career_la_avg"]   = float("nan")
    df["la_trending_up"]  = False
    df["la_trending_down"] = False
    df["la_display"]      = ""

    if _launch_angle_h:
        n_la_up, n_la_down = 0, 0
        for idx, row in df.iterrows():
            pid = int(row["batter"])
            rec = _launch_angle_h.get(pid)
            if not rec:
                continue
            curr_la  = rec.get("current_la_avg")
            curr_n   = rec.get("current_la_n", 0)
            car_la   = rec.get("career_la_avg")
            la_delta = rec.get("la_delta")

            if curr_la is not None:
                df.at[idx, "current_la_avg"] = round(curr_la, 1)
            if car_la is not None:
                df.at[idx, "career_la_avg"] = round(car_la, 1)
            if la_delta is not None and curr_n >= 50:
                df.at[idx, "la_delta"] = round(la_delta, 1)
                if la_delta > LA_UP_THRESH:
                    df.at[idx, "la_trending_up"]  = True
                    df.at[idx, "la_display"] = f"Launch angle trending up +{la_delta:.1f}°"
                    n_la_up += 1
                elif la_delta < LA_DOWN_THRESH:
                    df.at[idx, "la_trending_down"] = True
                    df.at[idx, "la_display"] = f"Launch angle trending down {la_delta:.1f}°"
                    n_la_down += 1
        print(f"  Launch angle: {n_la_up} trending up (>+{LA_UP_THRESH}°), "
              f"{n_la_down} trending down (<{LA_DOWN_THRESH}°)")
    else:
        print("  Launch angle: skipped (hitter_launch_angle.json not found)")

    # ── Worry Index / Confidence Meter (display-only — no effect on luck_score) ─
    # Flags players where model SILENCE is itself meaningful context.
    # Requires fp_rank (preseason expectation proxy) and xwoba_3yr (expected baseline).
    WORRY_LUCK_BAND = 0.085    # "no signal" zone: luck between -0.085 and +0.085
    WORRY_WOBA_GAP  = 0.040    # how far wOBA must deviate from 3yr xwOBA to flag
    df["worry_flag"]    = False
    df["breakout_flag"] = False
    df["worry_label"]   = ""
    _has_fp = df["fp_rank"].notna().any()
    _has_3yr = "xwoba_3yr" in df.columns and df["xwoba_3yr"].notna().any()
    if _has_fp and _has_3yr:
        _no_signal  = df["luck_score"].abs() < WORRY_LUCK_BAND
        _woba_valid = df["wOBA"].notna() & df["xwoba_3yr"].notna()
        # CONCERN: high-pedigree player struggling with no luck explanation
        _concern = (
            _no_signal & _woba_valid
            & df["fp_rank"].notna()
            & (df["fp_rank"] < 50)
            & ((df["xwoba_3yr"] - df["wOBA"]) > WORRY_WOBA_GAP)
        )
        df.loc[_concern, "worry_flag"]  = True
        df.loc[_concern, "worry_label"] = "No luck signal detected — struggle may be real, not random"
        # BREAKOUT: surprise performer with no regression signal
        _breakout = (
            _no_signal & _woba_valid
            & df["fp_rank"].notna()
            & (df["fp_rank"] > 100)
            & ((df["wOBA"] - df["xwoba_3yr"]) > WORRY_WOBA_GAP)
        )
        df.loc[_breakout, "breakout_flag"] = True
        df.loc[_breakout, "worry_label"]   = "No regression signal detected — breakout may be real"
        n_worry    = int(_concern.sum())
        n_breakout = int(_breakout.sum())
        print(f"  Worry Index: {n_worry} concern flags, {n_breakout} breakout flags")
    else:
        print("  Worry Index: skipped (fp_rank or xwoba_3yr not available)")

    if dry_run:
        print(f"[dry-run] Scores computed; {OUTPUT_PATH} not written.")
    else:
        df.to_csv(OUTPUT_PATH, index=False)

    # ── Terminal output (min 30 PA; full data still saved to CSV) ────────────
    MIN_DISPLAY_PA = 30

    display_cols = [
        "name", "team", "PA", "luck_score", "verdict", "tier_sell", "age_flag",
        "park_factor", "wrc_plus_3yr", "quality_tier",
        "amplification_cap_applied",
        "seasonal_pattern",
        "park_change", "park_change_label",
        "BABIP", "hr_fb_rate", "xwOBA_gap",
        "z_contact_rate", "pull_rate", "o_swing_rate",
        "hard_hit_rate", "barrel_rate",
    ]
    display_cols = [c for c in display_cols if c in df.columns]

    qualified = df[df["PA"] >= MIN_DISPLAY_PA]
    buy_low   = qualified[qualified["verdict"].isin(["Buy low", "Slight buy"])].head(10)
    sell_high = qualified[qualified["verdict"].isin(["Sell high", "Slight sell"])].tail(10).iloc[::-1]

    divider = "-" * 120

    print("\n" + divider)
    print(" TOP 10 BUY-LOW CANDIDATES  (unlucky -- underlying metrics better than results)")
    print(divider)
    print(buy_low[display_cols].to_string(index=False))

    print("\n" + divider)
    print(" TOP 10 SELL-HIGH CANDIDATES  (lucky -- underlying metrics worse than results)")
    print(divider)
    print(sell_high[display_cols].to_string(index=False))

    saved_note = "[dry-run] not written" if dry_run else f"saved to {OUTPUT_PATH}"
    print(f"\nFull results {saved_note}")
    print(f"Total batters scored: {len(df):,}  |  "
          f"Buy low: {(df['verdict'] == 'Buy low').sum()}  |  "
          f"Slight buy: {(df['verdict'] == 'Slight buy').sum()}  |  "
          f"Neutral: {(df['verdict'] == 'Neutral').sum()}  |  "
          f"Slight sell: {(df['verdict'] == 'Slight sell').sum()}  |  "
          f"Sell high: {(df['verdict'] == 'Sell high').sum()}")


if __name__ == "__main__":
    main()
