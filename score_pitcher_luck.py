"""
score_pitcher_luck.py — v3
Reads pitcher_luck_input.csv and pitchers_statcast.csv, calculates a composite
luck score for each pitcher, and saves results to pitcher_luck_scores.csv.

Luck score formula (positive = unlucky/buy low, negative = lucky/sell high):

  Primary luck signals:
    luck_score += (BABIP_allowed  - 0.300) *  5.0   # above avg = unlucky
    luck_score += (lob_pct        - 0.724) * -3.0   # below avg = unlucky
    luck_score += (ERA_minus_FIP         ) *  0.15  # positive gap = unlucky
    luck_score += (ERA_minus_xERA        ) *  0.10  # positive gap = unlucky

    HR/FB rate (luck indicator; only fires when HR/FB > 0.14):
      base = (hr_fb_rate - 0.12) * 2.0
      If hr_fb_rate > 0.14 AND hard_hit_rate_allowed > 0.38: base *= 0.65
        (hard contact justifies some elevated HR/FB — dampen the luck signal)
      If hr_fb_rate > 0.14 AND hard_hit_rate_allowed < 0.28: base *= 1.25
        (soft contact + high HR/FB = strong regression candidate — amplify)

    xwOBA gap (actual wOBA allowed minus xwOBA allowed):
      xwoba_gap = woba_value_mean - xwoba_pa_mean   [per PA, from Statcast]
      luck_score += xwoba_gap * 1.5
      Positive gap = pitcher giving up more than contact quality warrants = unlucky.
      Mirrors the hitter xwOBA gap in direction and construction.

  Quality validators (modify the luck signal, not drive it):
    luck_score += (hard_hit_rate_allowed - 0.360) * -1.5  # high hard hit reduces buy confidence
    luck_score += (barrel_rate_allowed   - 0.080) * -1.5  # high barrel rate reduces buy confidence
    luck_score += (swstr_rate            - 0.110) *  2.0  # high SwStr supports buy signal

  Confidence multiplier — date-aware, applied after raw component sum:
    Phase is determined from today's date relative to SEASON_START.

    April (season days 1-30):
      IP < 15  -> 0.0  (too small to call)
      IP >= 15 -> max(0.25, (IP - 15) / 40)   floor = 0.25

    May (season days 31-60):
      IP < 18  -> 0.0
      IP >= 18 -> max(0.15, (IP - 18) / 40)   floor = 0.15

    June+ (season days 61+):
      max(0.0, (IP - 20) / 40)               original formula, no floor

    The floor ensures early-season pitchers with qualifying IP generate
    real signal rather than being muted to near-zero by a tiny multiplier.
    A 22-IP pitcher in April gets 0.25 instead of 0.05 under the old formula.

Verdict thresholds:
   > 0.15  -> Buy low
   > 0.07  -> Slight buy
   < -0.15 -> Sell high
   < -0.07 -> Slight sell
   else    -> Neutral

Buy qualification gate (v3 addition):
   A buy signal is only surfaced if the pitcher is both unlucky AND worth owning
   when they normalize. ALL four conditions must hold:
     FIP    <= 4.50  (respectable underlying command/stuff)
     xERA   <= 4.75  (Statcast quality floor)
     SwStr% >= 8%    (generating meaningful whiffs)
     career IP >= 100 (not a complete unknown)
   Pitchers failing any condition are overridden to Neutral with buy_qualified=False.
   Rationale: a large ERA-FIP gap on a pitcher with FIP 8.36 means they're bad,
   not unlucky. Gate prevents the model from recommending genuinely poor pitchers.

# TODO (Session 8): Verdict thresholds (±0.07 / ±0.15) were calibrated for the
# old model where scores rarely exceeded ±0.20. The new model (date-aware
# confidence floor + HR/FB component + xwOBA gap) regularly produces scores in
# the ±0.40–0.65 range in April. After a full season of data, recalibrate these
# thresholds using the backtest framework extended to pitchers.
"""

import json
import math
import os
import pandas as pd
from datetime import date

from config import (
    P_PROD_BUY_LOW, P_PROD_SLIGHT_BUY, P_PROD_SELL_HIGH, P_PROD_SLIGHT_SELL,
)

BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
INPUT_PATH    = os.path.join(BASE_DIR, "pitcher_luck_input.csv")
SC_PATH       = os.path.join(BASE_DIR, "pitchers_statcast.csv")
OUTPUT_PATH   = os.path.join(BASE_DIR, "pitcher_luck_scores.csv")
CAREER_CACHE  = os.path.join(BASE_DIR, "data", "career_stats.json")
STUFF_PLUS_PATH      = os.path.join(BASE_DIR, "data", "pitcher_stuff_plus_2025.csv")
PITCH_MIX_DELTA_PATH = os.path.join(BASE_DIR, "data", "pitcher_pitch_mix_delta.json")
CAREER_BABIP_P_PATH = os.path.join(BASE_DIR, "data", "pitcher_career_babip.json")
CAREER_CSW_P_PATH   = os.path.join(BASE_DIR, "data", "pitcher_career_csw.json")
STARTS_PATH        = os.path.join(BASE_DIR, "pitcher_per_start_stats.csv")
STEAMER_PIT_CSV    = os.path.join(BASE_DIR, "Steamers 2025 pitchers.csv")
PRIOR_TEAMS_PATH          = os.path.join(BASE_DIR, "data", "prior_teams_2025.json")
PITCHER_CONTRACT_YEAR_PATH = os.path.join(BASE_DIR, "data", "pitcher_contract_year_2026.csv")
SEASON_YEAR        = 2026

SEASON_START  = date(2026, 3, 27)
NON_PA_EVENTS = {"truncated_pa"}

# ---------------------------------------------------------------------------
# v5: Park factor table (same as hitters; pitcher park factors inverted in logic)
# ---------------------------------------------------------------------------
PARK_FACTORS = {
    "COL": 1.18, "CIN": 1.08, "PHI": 1.06, "TEX": 1.05,
    "SF":  0.91, "TB":  0.94, "NYM": 0.95, "MIA": 0.95, "ATH": 0.96,
}
DEFAULT_PARK_FACTOR  = 1.00
LEAGUE_AVG_BABIP_P   = 0.300   # expected BABIP allowed in neutral park

# ---------------------------------------------------------------------------
# League-average baselines and weights for linear components
# (column, league_avg, weight, label)
# Gap stats (ERA_minus_FIP, ERA_minus_xERA) have baseline 0 — already deltas.
# HR/FB and xwOBA gap are handled separately (non-linear / from Statcast).
# ---------------------------------------------------------------------------
PRIMARY_COMPONENTS = [
    ("BABIP_allowed",   0.300,      5.0,  "BABIP allowed vs park-adj expected"),
    ("lob_pct",         0.724,     -3.0,  "LOB% vs 72.4%"),
    ("ERA_minus_FIP",   0.000,      0.15, "ERA minus FIP"),
    ("ERA_minus_xERA",  0.000,      0.10, "ERA minus xERA"),
]

VALIDATOR_COMPONENTS = [
    ("hard_hit_rate_allowed", 0.360, -1.5, "Hard hit allowed vs 36%"),
    ("barrel_rate_allowed",   0.080, -1.5, "Barrel allowed vs 8%"),
    ("swstr_rate",            0.110,  2.0, "SwStr% vs 11%"),
]

COMPONENTS = PRIMARY_COMPONENTS + VALIDATOR_COMPONENTS

MIN_DISPLAY_IP = 15.0
MIN_BUY_IP     = 20.0  # tighter IP floor for buy signals only; sell signals use MIN_DISPLAY_IP


# ---------------------------------------------------------------------------
# v5: Park factor helpers
# ---------------------------------------------------------------------------
def _park_factor(team: str) -> float:
    return PARK_FACTORS.get(str(team), DEFAULT_PARK_FACTOR)


def _load_prior_teams(path: str) -> dict:
    """Returns {player_id (int): prior_team (str)} or {} if file absent."""
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {int(k): str(v) for k, v in data.items() if k.lstrip("-").isdigit()}


def _detect_park_change(player_id: int, curr_team: str, prior_teams: dict) -> tuple:
    """
    Returns (park_change: bool, label: str | None).
    Fires only when prior team data available AND |PF_curr - PF_prior| > 0.03.
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


def _derive_pitcher_teams(sc_path: str) -> pd.Series:
    """
    Derives each pitcher's team from Statcast pitch data.
    Pitcher is on home team when inning_topbot == Top (away is batting),
    and away team when inning_topbot == Bot (home is batting).
    Returns most common team per pitcher MLBAM ID.
    """
    if not os.path.exists(sc_path):
        return pd.Series(dtype=str)
    sc = pd.read_csv(
        sc_path,
        usecols=["pitcher", "home_team", "away_team", "inning_topbot"],
        low_memory=False,
    )
    sc["pitcher_team"] = sc.apply(
        lambda r: r["home_team"] if r["inning_topbot"] == "Top" else r["away_team"],
        axis=1,
    )
    result = sc.groupby("pitcher")["pitcher_team"].agg(lambda x: x.mode()[0])
    result.index = result.index.astype("Int64")
    return result


def _pitcher_quality_tier(fip_minus: float) -> tuple:
    """Returns (multiplier, label) from park-adjusted FIP-. Buy signals only."""
    if math.isnan(fip_minus): return 1.00, "Unknown"
    if fip_minus < 80:   return 1.10, "Elite (FIP-<80)"
    if fip_minus <= 95:  return 1.00, "Above Avg (80-95)"
    if fip_minus <= 105: return 0.80, "Average (95-105)"
    if fip_minus <= 115: return 0.60, "Below Avg (105-115)"
    return 0.40, "Poor (FIP->115)"


def _amplification_cap(combined: float, raw: float) -> tuple:
    """
    Clamps |combined| to [0.25x, 2.0x] of |raw|.
    When raw == 0 (confidence-muted), returns (0.0, False).
    Returns (capped_score, cap_fired_bool).
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
# Season phase helpers
# ---------------------------------------------------------------------------
def get_season_day() -> int:
    return (date.today() - SEASON_START).days + 1


def get_conf_phase(season_day: int) -> str:
    if season_day <= 30:
        return "April"
    if season_day <= 60:
        return "May"
    return "June+"


# ---------------------------------------------------------------------------
# Confidence multiplier — date-aware
# ---------------------------------------------------------------------------
def confidence_scale_ip(ip, season_day: int) -> float:
    """
    Returns a [0, 1] multiplier scaled to the current phase of the season.

    April (days 1-30):   floor 0.25 for IP >= 15; zero below 15 IP
    May   (days 31-60):  floor 0.15 for IP >= 18; zero below 18 IP
    June+ (days 61+):    original formula — no floor, zero below 20 IP
    """
    try:
        ip_f = float(ip)
    except (TypeError, ValueError):
        return 0.0
    if season_day <= 30:
        if ip_f < 15.0:
            return 0.0
        return min(1.0, max(0.25, (ip_f - 15.0) / 40.0))
    elif season_day <= 60:
        if ip_f < 18.0:
            return 0.0
        return min(1.0, max(0.15, (ip_f - 18.0) / 40.0))
    else:
        return min(1.0, max(0.0, (ip_f - 20.0) / 40.0))


# ---------------------------------------------------------------------------
# HR/FB luck component with hard-hit contextual modifier
# ---------------------------------------------------------------------------
def hrfb_component(hr_fb, hard_hit) -> float:
    """
    HR/FB luck signal. Only activates when hr_fb_rate > 0.14 (above league avg
    ~12%). Elevated HR/FB mean-reverts strongly — pitcher is likely unlucky.

    Contextual modifier:
      hard_hit > 0.38 -> reduce by 35%  (hard contact partly explains HR/FB)
      hard_hit < 0.28 -> amplify by 25% (soft contact + high HR/FB = regression candidate)
      0.28-0.38       -> no modifier
    """
    try:
        hrf = float(hr_fb)
    except (TypeError, ValueError):
        return 0.0
    if pd.isna(hrf) or hrf <= 0.14:
        return 0.0
    base = (hrf - 0.12) * 2.0
    try:
        hh = float(hard_hit)
    except (TypeError, ValueError):
        hh = 0.33
    if pd.isna(hh):
        hh = 0.33
    if hh > 0.38:
        base *= 0.65
    elif hh < 0.28:
        base *= 1.25
    return base


# ---------------------------------------------------------------------------
# xwOBA gap — computed from Statcast pitch-level data
# ---------------------------------------------------------------------------
def compute_xwoba_gap(sc_path: str) -> pd.Series:
    """
    Pitcher xwOBA gap = actual wOBA allowed − xwOBA allowed (per PA).
    Positive = pitcher is unlucky; giving up more than contact quality warrants.

    Uses estimated_woba_using_speedangle where available (non-HR batted balls),
    falling back to woba_value for HR and true-outcome events (K, BB, HBP).
    This mirrors the xERA construction in process_pitcher_stats.py.

    Returns a Series indexed by pitcher MLBAM ID (Int64).
    """
    if not os.path.exists(sc_path):
        print(f"  WARNING: {sc_path} not found — xwOBA gap component will be skipped")
        return pd.Series(dtype=float, name="xwoba_gap")

    sc = pd.read_csv(
        sc_path,
        low_memory=False,
        usecols=["pitcher", "events", "estimated_woba_using_speedangle", "woba_value"],
    )
    pa = sc[sc["events"].notna() & ~sc["events"].isin(NON_PA_EVENTS)].copy()
    pa["xwoba_pa"] = pa["estimated_woba_using_speedangle"].fillna(pa["woba_value"])

    grp           = pa.groupby("pitcher")
    xwoba_allowed = grp["xwoba_pa"].mean()
    woba_allowed  = grp["woba_value"].mean()

    gap       = (woba_allowed - xwoba_allowed).round(4)
    gap.index = gap.index.astype("Int64")
    return gap.rename("xwoba_gap")


# ---------------------------------------------------------------------------
# Tier assignment (sell signals only — pitchers)
# ---------------------------------------------------------------------------
def assign_pitcher_tier(luck_score: float, xwoba_gap, verdict: str, career_ip: float, age: int):
    """
    Returns (tier_sell, age_flag) for pitchers.
    Buy/neutral → (None, None). Slight sell → Tier 3.

    Tier hierarchy for Sell high:
      Age 35+ sell: luck <= -0.20 → Tier 1 + "Decline risk"
                    luck <= -0.12 → Tier 2 + "Decline risk"
                    luck > -0.12  → original tier + "Age 35+ — monitor second half"
      Age 35+ buy:  original tier unchanged + "Age 35+ — monitor second half"
      Tier 1B Veteran: career_ip > 400, xwOBA gap > -0.020, luck in [-0.30, -0.15]
      Tier 2 Perception: xwOBA gap >= -0.020
      Tier 1 Move On: xwOBA gap deeply negative (< -0.020)
    """
    if pd.isna(xwoba_gap):
        xwoba_gap = 0.0

    if verdict in ("Buy low", "Slight buy") or "neutral" in verdict.lower():
        flag = "Age 35+ — monitor second half" if age >= 35 else None
        return None, flag

    if verdict == "Slight sell":
        flag = "Age 35+ — monitor second half" if age >= 35 else None
        return "Slight Regression Expected", flag

    if verdict != "Sell high":
        return None, None

    # Base tier (age-agnostic)
    if (career_ip > 400
            and xwoba_gap > -0.020
            and -0.30 <= luck_score <= -0.15):
        base_tier = "Veteran Regression"
    elif xwoba_gap >= -0.020:
        base_tier = "Sell High on Perception"
    else:
        base_tier = "Sell and Move On"

    if age >= 35:
        if luck_score <= -0.20:
            return "Sell and Move On", "Decline risk"
        if luck_score <= -0.12:
            return "Sell High on Perception", "Decline risk"
        return base_tier, "Age 35+ — monitor second half"

    flag = "Age concern" if age in (33, 34) else None
    return base_tier, flag


# ---------------------------------------------------------------------------
# GB% — computed from Statcast bb_type (used for SwStr% carve-out)
# ---------------------------------------------------------------------------
def compute_gb_pct(sc_path: str) -> pd.Series:
    """
    Ground ball rate = ground_ball BIP / total BIP per pitcher.
    Used to waive the SwStr% gate for extreme ground ball profiles (GB% > 52%).
    Returns a Series indexed by pitcher MLBAM ID (Int64).
    """
    if not os.path.exists(sc_path):
        return pd.Series(dtype=float, name="gb_pct")
    sc = pd.read_csv(sc_path, low_memory=False, usecols=["pitcher", "bb_type"])
    bip = sc[sc["bb_type"].notna()].copy()
    if bip.empty:
        return pd.Series(dtype=float, name="gb_pct")
    grp = bip.groupby("pitcher")
    gb_pct = grp.apply(lambda g: (g["bb_type"] == "ground_ball").sum() / len(g)).round(3)
    gb_pct.index = gb_pct.index.astype("Int64")
    return gb_pct.rename("gb_pct")


# ---------------------------------------------------------------------------
# Buy qualification gate — are they worth owning when ERA normalizes?
# ---------------------------------------------------------------------------
def is_buy_qualified(fip, xera, swstr, career_ip: float, gb_pct=float("nan")) -> bool:
    """
    Returns True only when a pitcher clears all quality thresholds (with carve-outs).

    Base gates: FIP <= 4.50, xERA <= 4.75, SwStr% >= 8%, career IP >= 100.

    Carve-outs:
      FIP <= 3.50  → waive xERA gate (elite K/BB profile overrides Statcast noise)
      GB%  > 0.52  → waive SwStr% gate (ground ball archetype; low whiffs expected)
    """
    try:
        fip_f   = float(fip)
        xera_f  = float(xera)
        swstr_f = float(swstr)
    except (TypeError, ValueError):
        return False

    import math as _math
    if _math.isnan(fip_f) or fip_f > 4.50:
        return False

    # xERA gate — waived when FIP is elite (≤ 3.50)
    fip_carveout = fip_f <= 3.50
    if not fip_carveout:
        if _math.isnan(xera_f) or xera_f > 4.75:
            return False

    # SwStr% gate — waived for ground ball archetypes (GB% > 52%)
    try:
        gb_f = float(gb_pct)
        gb_carveout = not _math.isnan(gb_f) and gb_f > 0.52
    except (TypeError, ValueError):
        gb_carveout = False
    if not gb_carveout:
        if _math.isnan(swstr_f) or swstr_f < 0.08:
            return False

    return float(career_ip) >= 100


# ---------------------------------------------------------------------------
# Age-adjusted BABIP helper (pitchers)
# ---------------------------------------------------------------------------
def _pitcher_babip_age_mult(age: int) -> float:
    """Career BABIP allowed age inflation. Older pitchers suppress BABIP less effectively."""
    if age >= 38: return 1.06
    if age >= 36: return 1.04
    if age >= 33: return 1.02
    return 1.0


# ---------------------------------------------------------------------------
# Verdict thresholds
# ---------------------------------------------------------------------------
def assign_verdict(score: float) -> str:
    if score > P_PROD_BUY_LOW:     return "Buy low"
    if score > P_PROD_SLIGHT_BUY:  return "Slight buy"
    if score < P_PROD_SELL_HIGH:   return "Sell high"
    if score < P_PROD_SLIGHT_SELL: return "Slight sell"
    return "Neutral"


# ---------------------------------------------------------------------------
# Volatility detection — computed from per-start stats
# ---------------------------------------------------------------------------
def compute_volatility(starts_path: str) -> pd.DataFrame:
    """
    Computes per-pitcher volatility metrics from pitcher_per_start_stats.csv.

    Returns a DataFrame indexed by pitcher MLBAM ID with columns:
        total_starts, disaster_starts, disaster_rate,
        qs_count, qs_rate, start_variance,
        volatility_flag, volatility_label

    disaster_rate  = starts where RA9 > 10 (and IP >= 2) / total starts
    qs_rate        = quality starts (IP>=6, RA<=3) / total starts
    start_variance = std dev of start_era across qualifying starts
    volatility_flag= True if disaster_rate > 0.30 OR start_variance > 4.0
    """
    if not os.path.exists(starts_path):
        print(f"  WARNING: {starts_path} not found — volatility detection skipped")
        return pd.DataFrame(columns=[
            "pitcher", "total_starts", "disaster_rate", "qs_rate",
            "start_variance", "volatility_flag", "volatility_label"
        ])

    df = pd.read_csv(starts_path)
    results = []
    for pid, grp in df.groupby("pitcher"):
        total        = len(grp)
        disaster_n   = int(grp["is_disaster"].sum())
        qs_n         = int(grp["is_qs"].sum())
        disaster_rate = disaster_n / total if total > 0 else 0.0

        qual_eras = grp.loc[grp["qualifying"], "start_era"].dropna()
        start_var = float(qual_eras.std()) if len(qual_eras) >= 2 else float("nan")

        flagged = disaster_rate > 0.30 or (not math.isnan(start_var) and start_var > 4.0)
        label   = "High variance — signals less reliable" if flagged else None

        results.append({
            "pitcher":        int(pid),
            "total_starts":   total,
            "disaster_starts": disaster_n,
            "disaster_rate":  round(disaster_rate, 3),
            "qs_count":       qs_n,
            "qs_rate":        round(qs_n / total, 3) if total > 0 else 0.0,
            "start_variance": round(start_var, 2) if not math.isnan(start_var) else None,
            "volatility_flag":  flagged,
            "volatility_label": label,
        })

    return pd.DataFrame(results)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    if not os.path.exists(INPUT_PATH):
        raise SystemExit(
            f"Input file not found: {INPUT_PATH}\n"
            "Run fetch_pitcher_stats.py and process_pitcher_stats.py first."
        )

    df = pd.read_csv(INPUT_PATH)
    print(f"Loaded {len(df):,} pitchers from {INPUT_PATH}")

    season_day = get_season_day()
    conf_phase = get_conf_phase(season_day)
    print(f"Season day: {season_day}  |  Confidence phase: {conf_phase}")

    # ── v5: Derive pitcher teams from Statcast ───────────────────────────────
    print(f"Deriving pitcher teams from {SC_PATH} ...")
    pitcher_team_map = _derive_pitcher_teams(SC_PATH)
    df["pitcher"] = df["pitcher"].astype("Int64")
    df["Team"] = df["pitcher"].map(pitcher_team_map).fillna("UNK")
    df["park_factor"] = df["Team"].apply(_park_factor)

    # ── Park change detection ────────────────────────────────────────────────
    prior_teams_p = _load_prior_teams(PRIOR_TEAMS_PATH)
    df["park_change"]       = False
    df["park_change_label"] = None
    if prior_teams_p:
        _park_res = df.apply(
            lambda r: _detect_park_change(int(r["pitcher"]), r["Team"], prior_teams_p),
            axis=1,
        )
        df["park_change"]       = _park_res.apply(lambda t: t[0])
        df["park_change_label"] = _park_res.apply(lambda t: t[1])
        n_park_p = int(df["park_change"].sum())
        print(f"  Park change detection: {n_park_p} pitchers flagged")
    else:
        print("  Park change detection: prior_teams_2025.json not found — skipped")

    # Load career stats early — needed for age-adjusted BABIP baseline
    career_stats: dict = {}
    if os.path.exists(CAREER_CACHE):
        with open(CAREER_CACHE) as f:
            career_stats = {int(k): v for k, v in json.load(f).items()}

    # Career BABIP baseline — individual pitcher baseline replaces flat 0.300
    _career_babip_p: dict = {}
    if os.path.exists(CAREER_BABIP_P_PATH):
        with open(CAREER_BABIP_P_PATH) as _f:
            _career_babip_p = json.load(_f)
        print(f"  Career pitcher BABIP loaded: {len(_career_babip_p):,} pitchers")

    df["career_babip_allowed"] = df["pitcher"].apply(
        lambda pid: (
            float(_career_babip_p[str(int(pid))]["career_babip_allowed"])
            if pd.notna(pid) and str(int(pid)) in _career_babip_p
               and _career_babip_p[str(int(pid))]["career_babip_allowed"] is not None
            else None
        )
    )
    df["career_hh_allowed"] = df["pitcher"].apply(
        lambda pid: (
            float(_career_babip_p[str(int(pid))]["career_hard_hit_allowed"])
            if pd.notna(pid) and str(int(pid)) in _career_babip_p
               and _career_babip_p[str(int(pid))]["career_hard_hit_allowed"] is not None
            else None
        )
    )
    df["career_barrel_allowed"] = df["pitcher"].apply(
        lambda pid: (
            float(_career_babip_p[str(int(pid))]["career_barrel_allowed"])
            if pd.notna(pid) and str(int(pid)) in _career_babip_p
               and _career_babip_p[str(int(pid))]["career_barrel_allowed"] is not None
            else None
        )
    )
    n_with_career_p = df["career_babip_allowed"].notna().sum()
    n_fallback_p    = df["career_babip_allowed"].isna().sum()
    print(f"  Career BABIP: {n_with_career_p} pitchers with individual baseline, "
          f"{n_fallback_p} using flat {LEAGUE_AVG_BABIP_P}")
    df["babip_baseline"] = df["career_babip_allowed"].fillna(LEAGUE_AVG_BABIP_P)

    # Age-adjusted career BABIP: older pitchers allow more BABIP
    _byr_p = {k: int(v.get("birth_year") or 0) for k, v in career_stats.items()}
    df["_age_babip"] = df["pitcher"].apply(
        lambda i: SEASON_YEAR - _byr_p[int(i)] if int(i) in _byr_p and _byr_p[int(i)] > 0 else 0
    )
    df["age_adj_career_babip"] = df.apply(
        lambda r: round(r["babip_baseline"] * _pitcher_babip_age_mult(int(r["_age_babip"])), 4)
        if pd.notna(r["career_babip_allowed"]) and r["_age_babip"] > 0
        else r["babip_baseline"],
        axis=1,
    )
    n_age_adj_p = int((df["age_adj_career_babip"] != df["babip_baseline"]).sum())
    print(f"  Age-adjusted BABIP: {n_age_adj_p} pitchers adjusted (age 33+)")
    df["park_adj_babip_expected"] = (df["age_adj_career_babip"] * df["park_factor"]).round(4)
    print(f"  Teams derived for {pitcher_team_map.notna().sum():,} pitchers")

    # ── xwOBA gap (Improvement 3) ────────────────────────────────────────────
    print(f"Computing xwOBA gap from {SC_PATH} ...")
    xwoba_gap = compute_xwoba_gap(SC_PATH)
    if not xwoba_gap.empty:
        xwoba_gap_df    = xwoba_gap.reset_index()
        xwoba_gap_df.columns = ["pitcher", "xwoba_gap"]
        df = df.merge(xwoba_gap_df, on="pitcher", how="left")
        print(f"  xwOBA gap joined for {df['xwoba_gap'].notna().sum():,} pitchers")

    # ── GB% (for ground-ball archetype SwStr% carve-out) ─────────────────────
    print(f"Computing GB% from {SC_PATH} ...")
    gb_pct = compute_gb_pct(SC_PATH)
    if not gb_pct.empty:
        gb_df = gb_pct.reset_index()
        gb_df.columns = ["pitcher", "gb_pct"]
        df = df.merge(gb_df, on="pitcher", how="left")
        print(f"  GB% joined for {df['gb_pct'].notna().sum():,} pitchers")

    # ── Warn about missing linear-component columns ──────────────────────────
    missing = [col for col, *_ in COMPONENTS if col not in df.columns]
    if missing:
        print(f"  WARNING: missing columns will be skipped: {missing}")

    # ── Build component columns ──────────────────────────────────────────────
    component_cols = []

    # v5: BABIP_allowed uses park-adjusted expected instead of fixed 0.300
    # v6: hard_hit_rate_allowed and barrel_rate_allowed use career baselines when available
    for col, avg, weight, _label in COMPONENTS:
        if col not in df.columns:
            continue
        comp_col = f"_comp_{col}"
        if col == "BABIP_allowed":
            df[comp_col] = (df[col] - df["park_adj_babip_expected"]) * weight
        elif col == "hard_hit_rate_allowed":
            baseline = df["career_hh_allowed"].where(df["career_hh_allowed"].notna(), avg)
            df[comp_col] = (df[col] - baseline) * weight
        elif col == "barrel_rate_allowed":
            baseline = df["career_barrel_allowed"].where(df["career_barrel_allowed"].notna(), avg)
            df[comp_col] = (df[col] - baseline) * weight
        else:
            df[comp_col] = (df[col] - avg) * weight
        component_cols.append(comp_col)

    # HR/FB luck component with hard-hit contextual modifier (Improvement 2)
    if "hr_fb_rate" in df.columns:
        hh_col = "hard_hit_rate_allowed" if "hard_hit_rate_allowed" in df.columns else None
        df["_comp_hrfb"] = df.apply(
            lambda r: hrfb_component(
                r["hr_fb_rate"],
                r[hh_col] if hh_col else float("nan"),
            ),
            axis=1,
        )
        component_cols.append("_comp_hrfb")

    # xwOBA gap component (Improvement 3)
    if "xwoba_gap" in df.columns:
        df["_comp_xwoba_gap"] = df["xwoba_gap"].fillna(0.0) * 1.5
        component_cols.append("_comp_xwoba_gap")

    # ── Split scorer ─────────────────────────────────────────────────────────
    # Sell score: full 8-component sum (validated sell signal)
    # Buy score:  ERA-FIP dominant 3-component (ERA-FIP is the proven buy signal)
    sell_comp_names = ["_comp_BABIP_allowed", "_comp_lob_pct",
                       "_comp_ERA_minus_FIP", "_comp_ERA_minus_xERA",
                       "_comp_hrfb", "_comp_hard_hit_rate_allowed",
                       "_comp_barrel_rate_allowed", "_comp_swstr_rate"]
    sell_cols = [c for c in sell_comp_names if c in df.columns]
    df["_sell_score"] = df[sell_cols].sum(axis=1)

    df["_buy_era_fip"] = df["ERA_minus_FIP"].fillna(0.0) * 0.60
    if "xwoba_gap" in df.columns:
        df["_buy_xwoba"] = df["xwoba_gap"].fillna(0.0) * 0.25
    else:
        df["_buy_xwoba"] = 0.0
    if "park_adj_babip_expected" in df.columns and "BABIP_allowed" in df.columns:
        df["_buy_babip"] = (df["BABIP_allowed"] - df["park_adj_babip_expected"]).fillna(0.0) * 0.15
    elif "BABIP_allowed" in df.columns:
        df["_buy_babip"] = (df["BABIP_allowed"] - 0.300).fillna(0.0) * 0.15
    else:
        df["_buy_babip"] = 0.0
    df["_buy_score"] = df[["_buy_era_fip", "_buy_xwoba", "_buy_babip"]].sum(axis=1)

    def _split_luck(r):
        ss, bs = r["_sell_score"], r["_buy_score"]
        if ss < 0 and bs > 0:
            return float(r.get("ERA_minus_FIP") or 0.0) * 0.15
        if ss < 0:
            return ss
        if bs > 0:
            return bs
        return 0.0

    df["luck_score"] = df.apply(_split_luck, axis=1)
    # Keep _buy_score and _sell_score for pre-scaling buy verdict classification (dropped after assign_verdict)
    _split_aux = ["_buy_era_fip", "_buy_xwoba", "_buy_babip"]
    df.drop(columns=component_cols + _split_aux, inplace=True)

    # ── Apply date-aware confidence multiplier ───────────────────────────────
    if "IP" in df.columns:
        df["luck_score"] = (
            df.apply(
                lambda r: round(r["luck_score"] * confidence_scale_ip(r["IP"], season_day), 4),
                axis=1,
            )
        )
    else:
        df["luck_score"] = df["luck_score"].round(4)

    df["conf_phase"] = conf_phase

    # ── Load career ip / birth year from already-loaded career_stats ────────
    df["career_ip"]  = df["pitcher"].map(lambda i: float((career_stats.get(int(i)) or {}).get("career_ip") or 0))
    df["birth_year"] = df["pitcher"].map(lambda i: int((career_stats.get(int(i)) or {}).get("birth_year") or 0))
    df["age"] = df["birth_year"].apply(lambda by: SEASON_YEAR - by if by > 0 else 0)

    # ── v5: FIP- (park-adjusted) ─────────────────────────────────────────────
    if "FIP" in df.columns:
        qualified_fip = df[df["IP"] >= 20]["FIP"].dropna() if "IP" in df.columns else df["FIP"].dropna()
        if len(qualified_fip) == 0:
            qualified_fip = df["FIP"].dropna()
        league_avg_fip = qualified_fip.mean()
        # fip_minus_adj: (FIP / league_avg) x (1/park_factor) x 100
        # Coors pitchers get credit for pitching in an inflated-FIP park
        df["fip_minus"] = df.apply(
            lambda r: round(
                (float(r["FIP"]) / league_avg_fip) * (1.0 / r["park_factor"]) * 100, 1
            ) if not pd.isna(r.get("FIP")) else float("nan"),
            axis=1,
        )
        df["pitcher_quality_tier"] = df["fip_minus"].apply(
            lambda f: _pitcher_quality_tier(f if not pd.isna(f) else float("nan"))[1]
        )
    else:
        df["fip_minus"] = float("nan")
        df["pitcher_quality_tier"] = "Unknown"

    # ── v5: RTM signal (FIP - xERA proxy for career mean regression) ─────────
    # Positive: FIP > xERA → ERA may normalize upward → sell confirmation
    # Negative: FIP < xERA → ERA may normalize downward → buy confirmation
    # Note: career FIP not in pipeline; FIP vs xERA is a same-season proxy.
    if "FIP" in df.columns and "xERA" in df.columns:
        df["rtm_signal"] = df.apply(
            lambda r: round(float(r["FIP"]) - float(r["xERA"]), 4)
            if not pd.isna(r.get("FIP")) and not pd.isna(r.get("xERA")) else 0.0,
            axis=1,
        )
    else:
        df["rtm_signal"] = 0.0

    # ── v5: Save raw luck score as cap reference ──────────────────────────────
    df["_luck_raw_for_cap"] = df["luck_score"].copy()

    # ── v5: Quality tier multiplier (buy signals only) ────────────────────────
    df["luck_score"] = df.apply(
        lambda r: round(
            r["luck_score"] * _pitcher_quality_tier(
                r["fip_minus"] if not pd.isna(r["fip_minus"]) else float("nan")
            )[0], 4
        ) if r["luck_score"] > 0 else r["luck_score"],
        axis=1,
    )

    # ── v5: RTM integration ───────────────────────────────────────────────────
    df["rtm_confluence"] = df.apply(
        lambda r: (
            "Buy confluence"  if r["luck_score"] > 0 and r["rtm_signal"] < 0 else
            "Sell confluence" if r["luck_score"] < 0 and r["rtm_signal"] > 0 else
            "No confluence"
        ),
        axis=1,
    )

    def _combine_pitcher_rtm(row) -> float:
        ls = row["luck_score"]
        rt = row["rtm_signal"]
        # For pitchers: rtm_signal > 0 = sell confirmation; < 0 = buy confirmation
        # Confluence: luck > 0 (unlucky pitcher) AND rtm < 0 (FIP < xERA, may normalize down)
        combined = ls * 0.75 + (rt * 0.15) * 0.25
        if (ls > 0 and rt < 0) or (ls < 0 and rt > 0):
            combined *= 1.15
        return round(combined, 4)

    df["luck_score"] = df.apply(_combine_pitcher_rtm, axis=1)

    # ── v5: Amplification cap ─────────────────────────────────────────────────
    cap_results = df.apply(
        lambda r: _amplification_cap(r["luck_score"], r["_luck_raw_for_cap"]),
        axis=1,
    )
    df["luck_score"]                = cap_results.apply(lambda t: t[0])
    df["amplification_cap_applied"] = cap_results.apply(lambda t: t[1])
    df.drop(columns=["_luck_raw_for_cap"], inplace=True)

    # ── Stuff+ (arsenal quality) modifier ────────────────────────────────────
    df["stuff_plus_avg"]   = float("nan")
    df["best_pitch_type"]  = None
    df["stuff_plus_signal"] = None

    if os.path.exists(STUFF_PLUS_PATH):
        sp_df = pd.read_csv(STUFF_PLUS_PATH)
        sp_map = sp_df.set_index("pitcher_id")[["stuff_plus_avg", "best_pitch_type"]].to_dict("index")
        print(f"  Stuff+ data loaded: {len(sp_map):,} pitchers from {STUFF_PLUS_PATH}")

        def _apply_stuff_modifier(row):
            pid   = int(row["pitcher"])
            rec   = sp_map.get(pid)
            ls    = row["luck_score"]
            fip_m = row.get("fip_minus", float("nan"))
            if rec is None:
                return ls, float("nan"), None, None
            sp  = rec["stuff_plus_avg"]
            bpt = rec["best_pitch_type"]
            signal = None

            # FIP- overrides: fire when outcome quality disagrees with stuff+ proxy.
            # Weak-contact pitchers (low FIP-, modest stuff+) are undercalibrated by
            # the swing-and-miss proxy — don't penalise their buy signals or amplify
            # their sell signals.  Opposite for high-stuff pitchers with poor outcomes.
            fip_m_val = fip_m if not (isinstance(fip_m, float) and math.isnan(fip_m)) else None
            is_elite_override = fip_m_val is not None and fip_m_val < 85  and sp < 95
            is_poor_override  = fip_m_val is not None and fip_m_val > 115 and sp > 105

            if is_elite_override:
                if ls < 0:
                    # FIP- says elite outcomes → dampen sell instead of amplifying
                    ls     = round(ls * 0.85, 4)
                    signal = f"FIP- override: elite contact, dampens sell x0.85 (sp={sp:.0f}, FIP-={fip_m_val:.0f})"
                # buy: skip "poor stuff dampens buy" — no penalty applied
            elif is_poor_override:
                if ls > 0:
                    # FIP- says poor outcomes → skip elite buy bonus
                    signal = f"FIP- override: poor outcomes, skips elite bonus (sp={sp:.0f}, FIP-={fip_m_val:.0f})"
                elif ls < 0:
                    # FIP- confirms sell despite good stuff → amplify sell
                    ls     = round(ls * 1.15, 4)
                    signal = f"FIP- override: poor outcomes, amplifies sell x1.15 (sp={sp:.0f}, FIP-={fip_m_val:.0f})"
            else:
                # Normal stuff+ tiers
                if sp > 110 and ls > 0:
                    ls     = round(ls * 1.15, 4)
                    signal = f"Elite stuff+buy x1.15 (sp={sp:.0f})"
                elif sp < 90 and ls < 0:
                    ls     = round(ls * 1.15, 4)
                    signal = f"Poor stuff+sell x1.15 (sp={sp:.0f})"
                elif sp > 110 and ls < 0:
                    ls     = round(ls * 0.85, 4)
                    signal = f"Elite stuff dampens sell x0.85 (sp={sp:.0f})"
                elif sp < 90 and ls > 0:
                    ls     = round(ls * 0.85, 4)
                    signal = f"Poor stuff dampens buy x0.85 (sp={sp:.0f})"
            return ls, sp, bpt, signal

        results = df.apply(_apply_stuff_modifier, axis=1)
        df["luck_score"]       = results.apply(lambda t: t[0])
        df["stuff_plus_avg"]   = results.apply(lambda t: t[1])
        df["best_pitch_type"]  = results.apply(lambda t: t[2])
        df["stuff_plus_signal"] = results.apply(lambda t: t[3])

        elite_buy       = df["stuff_plus_signal"].str.startswith("Elite stuff+buy",  na=False).sum()
        poor_sell       = df["stuff_plus_signal"].str.startswith("Poor stuff+sell",  na=False).sum()
        elite_damp      = df["stuff_plus_signal"].str.startswith("Elite stuff damp", na=False).sum()
        poor_damp       = df["stuff_plus_signal"].str.startswith("Poor stuff damp",  na=False).sum()
        fip_elite_ovr   = df["stuff_plus_signal"].str.startswith("FIP- override: elite", na=False).sum()
        fip_poor_ovr    = df["stuff_plus_signal"].str.startswith("FIP- override: poor", na=False).sum()
        no_data         = df["stuff_plus_avg"].isna().sum()
        print(f"  Stuff+ modifier applied: {elite_buy} elite-buy x1.15 | "
              f"{poor_sell} poor-sell x1.15 | {elite_damp} elite-dampen-sell x0.85 | "
              f"{poor_damp} poor-dampen-buy x0.85 | {no_data} pitchers with no data")
        print(f"  FIP- overrides: {fip_elite_ovr} elite-contact (dampens sell) | "
              f"{fip_poor_ovr} poor-outcome (skips/amplifies)")
    else:
        print(f"  WARNING: {STUFF_PLUS_PATH} not found -- Stuff+ modifier skipped")

    # ── Volatility detection ─────────────────────────────────────────────────
    print(f"Loading volatility stats from {STARTS_PATH} ...")
    vol_df = compute_volatility(STARTS_PATH)
    if not vol_df.empty:
        vol_df["pitcher"] = vol_df["pitcher"].astype("Int64")
        df = df.merge(
            vol_df[["pitcher", "total_starts", "disaster_starts", "disaster_rate",
                    "qs_count", "qs_rate", "start_variance",
                    "volatility_flag", "volatility_label"]],
            on="pitcher", how="left",
        )
        df["volatility_flag"]  = df["volatility_flag"].fillna(False)
        df["volatility_label"] = df["volatility_label"].where(df["volatility_label"].notna(), None)

        # Dampen buy signals ×0.90 for high-variance pitchers
        # (volatility contextualizes the signal — don't eliminate, just moderate)
        volatile_buy = df["volatility_flag"] & (df["luck_score"] > 0)
        n_dampened = int(volatile_buy.sum())
        df.loc[volatile_buy, "luck_score"] = (df.loc[volatile_buy, "luck_score"] * 0.90).round(4)
        if n_dampened:
            print(f"  Volatility: {n_dampened} buy signals dampened ×0.90 (high-variance pitchers)")

        n_flagged = int(df["volatility_flag"].sum())
        print(f"  Volatility flagged: {n_flagged} pitchers "
              f"(disaster_rate > 30% or start_variance > 4.0)")
        if n_flagged:
            flagged_names = df.loc[df["volatility_flag"], "name"].dropna().tolist()[:8]
            print(f"  Flagged: {', '.join(flagged_names)}")
    else:
        df["total_starts"]    = None
        df["disaster_starts"] = None
        df["disaster_rate"]   = None
        df["qs_count"]        = None
        df["qs_rate"]         = None
        df["start_variance"]  = None
        df["volatility_flag"] = False
        df["volatility_label"]= None

    # ── Pitch mix evolution modifier (Phase 1) ───────────────────────────────
    # Signals: abandonment (high-whiff pitch losing use, bearish regardless of direction)
    #          effectiveness (best pitch SwStr improving >= 2pp above 12% floor, bullish)
    # Phase 1 constraints: no per-pitch velo delta (career file lacks per-pitch baseline);
    #   new_pitch_flag=False until Phase 2 pybaseball fetch resolves Statcast label noise.
    df["pitch_mix_signal"] = float("nan")
    df["pitch_mix_note"]   = None

    if os.path.exists(PITCH_MIX_DELTA_PATH):
        with open(PITCH_MIX_DELTA_PATH) as _pmf:
            _pm_data = json.load(_pmf)
        _pm_by_id = {int(k): v for k, v in _pm_data.items()}

        n_aband, n_effect = 0, 0

        def _apply_pitch_mix(row):
            pid  = int(row["pitcher"])
            rec  = _pm_by_id.get(pid)
            ls   = row["luck_score"]
            if rec is None:
                return ls, float("nan"), None

            sig  = rec.get("pitch_mix_signal", 0.0)
            note = rec.get("pitch_mix_note")

            # Bearish flags — dampen buys (×0.90), amplify sells (×1.10)
            # Phase 1: abandonment (high-whiff pitch losing usage)
            # Phase 2: velo_drop (best pitch losing velocity), rv_degrade (RV worsening)
            bearish = [
                rec.get("abandonment_flag", False),
                rec.get("velo_drop_flag",   False),
                rec.get("rv_degrade_flag",  False),
            ]
            # Bullish flags — amplify buys only (×1.10 or ×1.05)
            # Phase 1: effectiveness (SwStr improving on best pitch)
            # Phase 2: velo_gain (best pitch gaining velo), rv_improve (RV improving),
            #          new_pitch (truly new pitch with distinct velo + whiff gate)
            bullish = [
                rec.get("effectiveness_flag", False),
                rec.get("velo_gain_flag",     False),
                rec.get("new_pitch_flag",     False),
            ]
            # rv_improve slightly discounted (RV more sample-sensitive than velo)
            rv_improve = rec.get("rv_improve_flag", False)

            # Apply bearish multipliers (each active flag applies independently; stacks multiply)
            for flag in bearish:
                if flag:
                    if ls > 0:
                        ls = round(ls * 0.90, 4)
                    elif ls < 0:
                        ls = round(ls * 1.10, 4)

            # Apply bullish multipliers (buy side only)
            for flag in bullish:
                if flag and ls > 0:
                    ls = round(ls * 1.10, 4)
            if rv_improve and ls > 0:
                ls = round(ls * 1.05, 4)

            return ls, sig, note

        results = df.apply(_apply_pitch_mix, axis=1)
        df["luck_score"]      = results.apply(lambda t: t[0])
        df["pitch_mix_signal"] = results.apply(lambda t: t[1])
        df["pitch_mix_note"]   = results.apply(lambda t: t[2])

        n_covered  = df["pitch_mix_signal"].notna().sum()
        n_aband    = df["pitch_mix_note"].str.contains("abandonment", na=False).sum()
        n_vdrop    = df["pitch_mix_note"].str.contains("velo_drop",   na=False).sum()
        n_rvdeg    = df["pitch_mix_note"].str.contains("rv_degrade",  na=False).sum()
        n_effect   = df["pitch_mix_note"].str.contains("effectiveness", na=False).sum()
        n_vgain    = df["pitch_mix_note"].str.contains("velo_gain",   na=False).sum()
        n_rvimpr   = df["pitch_mix_note"].str.contains("rv_improve",  na=False).sum()
        n_newpitch = df["pitch_mix_note"].str.contains("new_pitch",   na=False).sum()
        print(f"  Pitch mix (Phase 2): {n_covered} pitchers covered")
        print(f"    Bearish: {n_aband} abandonment | {n_vdrop} velo drop | {n_rvdeg} rv degrade")
        print(f"    Bullish: {n_effect} effectiveness | {n_vgain} velo gain | "
              f"{n_rvimpr} rv improve | {n_newpitch} new pitch")
    else:
        print(f"  WARNING: {PITCH_MIX_DELTA_PATH} not found -- pitch mix modifier skipped")

    # Pre-scaling buy classification: raw _buy_score is used before confidence dampening
    # so strong ERA-FIP-gap pitchers aren't knocked below threshold by April IP scaling.
    # Sell signals still use scaled luck_score via assign_verdict() — unchanged.
    def _assign_verdict_prescore(row):
        bs  = float(row.get("_buy_score") or 0.0)
        ss  = float(row.get("_sell_score") or 0.0)
        ls  = float(row.get("luck_score") or 0.0)
        ip  = float(row.get("IP") or 0.0)
        era = float(row.get("ERA") or 0.0)
        fip = float(row.get("FIP") or float("nan"))
        xera_raw = row.get("xERA")
        xera = float(xera_raw) if pd.notna(xera_raw) else float("nan")

        # Only use pre-scaling buy classification when:
        #   1. Pure buy direction (sell composite not negative — no conflict)
        #   2. Confidence scale > 0 (IP meets floor — luck_score != 0 after scaling)
        if bs > 0 and ss >= 0 and ls > 0:
            # dominant_buy: raw buy score large enough that ERA-FIP gap overrides
            # sample-size and xERA disagreement concerns (waives FIX 1 and FIX 3)
            dominant_buy = bs >= 1.50
            # FIX 1: tighter IP floor; waived for dominant buys
            if ip < MIN_BUY_IP and not dominant_buy:
                return "Neutral"
            # Implausible peripherals: FIP < 1.50 with IP < 20 always suppressed —
            # dominant_buy waiver does NOT apply (e.g. Pivetta FIP 1.23 in 16 IP)
            if ip < MIN_BUY_IP and not pd.isna(fip) and fip < 1.50:
                return "Neutral"
            # FIX 2: ERA floor always applied — buy thesis requires ERA elevated above true talent
            if era < 3.50:
                return "Neutral"
            # FIX 3: FIP/xERA confluence — suppress when xERA disagrees strongly with FIP;
            # waived for dominant buys (massive ERA-FIP gap overrides xERA disagreement)
            if (not dominant_buy and not pd.isna(xera) and not pd.isna(fip)
                    and abs(fip - xera) > 1.50 and xera > 4.50):
                return "Neutral"
            if bs >= 0.50:
                # Buy Low requires ERA >= 3.75: 89.3% accuracy above vs 29.6% below
                # (sensitivity analysis Apr 25 2026 confirmed +7.3pp 2025 OOS)
                if era < 3.75:
                    return "Neutral"
                return "Buy low"
            if bs >= 0.30:
                # Slight buy requires ERA >= 4.00: elite pitchers (FIP ~2.5-3.0, ERA ~3.5-3.8)
                # don't show enough ERA improvement to register — they need BUY_LOW gap to qualify.
                if era < 4.00:
                    return "Neutral"
                return "Slight buy"
        return assign_verdict(ls)

    df["verdict"] = df.apply(_assign_verdict_prescore, axis=1)
    df["raw_buy_score"] = df["_buy_score"].round(4) if "_buy_score" in df.columns else float("nan")
    df.drop(columns=["_buy_score", "_sell_score"], inplace=True, errors="ignore")

    # ── Buy qualification gate ────────────────────────────────────────────────
    df["buy_qualified"] = df.apply(
        lambda r: is_buy_qualified(
            r.get("FIP",       float("nan")),
            r.get("xERA",      float("nan")),
            r.get("swstr_rate",float("nan")),
            r["career_ip"],
            r.get("gb_pct",    float("nan")),
        ) if r["verdict"] in ("Buy low", "Slight buy") else True,
        axis=1,
    )
    disqualified = ~df["buy_qualified"] & df["verdict"].isin(["Buy low", "Slight buy"])
    n_disqualified = disqualified.sum()
    if n_disqualified:
        print(f"  Buy qualification gate: {n_disqualified} pitchers overridden to Neutral "
              f"(ERA-FIP gap present but underlying metrics don't support a roster recommendation)")
        df.loc[disqualified, "verdict"] = "Neutral"

    # ── LOB% buy-side confluence flag ────────────────────────────────────────
    # LOB% < 0.65 confirms buy signal (bad luck stranding runners)
    # LOB% > 0.80 weakens buy signal (masking true ERA via strand luck)
    # Sell-side LOB% component is unchanged (part of the _comp_lob_pct composite)
    def _lob_confluence(row):
        if row["verdict"] not in ("Buy low", "Slight buy"):
            return ""
        lob = row.get("lob_pct")
        if pd.isna(lob) or lob is None:
            return ""
        lob = float(lob)
        if lob < 0.65:
            return "Low strand rate"
        if lob > 0.80:
            return "High strand rate"
        return ""

    df["lob_confluence_flag"] = df.apply(_lob_confluence, axis=1)

    # ── CSW buy-low modifier ──────────────────────────────────────────────────
    _CSW_DESCS = {"called_strike", "swinging_strike", "swinging_strike_blocked", "foul_tip"}
    _CSW_FIRE  = 0.025
    _CSW_AMP   = 1.10
    _CSW_DAMP  = 0.90
    _MIN_CSW_P = 100

    _career_csw_p: dict = {}
    if os.path.exists(CAREER_CSW_P_PATH):
        with open(CAREER_CSW_P_PATH) as _f:
            _raw_csw = json.load(_f)
        for _k, _v in _raw_csw.items():
            if isinstance(_v, dict) and _v.get("career_csw") is not None:
                _career_csw_p[int(_k)] = float(_v["career_csw"])
        print(f"  Career pitcher CSW loaded: {len(_career_csw_p):,} pitchers")

    if _career_csw_p and os.path.exists(SC_PATH):
        _sc_csw = pd.read_csv(SC_PATH, usecols=["pitcher", "description"], low_memory=False)
        _sc_csw = _sc_csw[~_sc_csw["description"].isin({"automatic_ball", "pitchout"})]
        _sc_csw["is_csw"] = _sc_csw["description"].isin(_CSW_DESCS).astype(int)
        _csw_agg = _sc_csw.groupby("pitcher").agg(
            csw_count=("is_csw", "sum"), total=("is_csw", "count")).reset_index()
        _csw_agg = _csw_agg[_csw_agg["total"] >= _MIN_CSW_P].copy()
        _csw_agg["curr_csw"] = (_csw_agg["csw_count"] / _csw_agg["total"]).round(4)
        _csw_map = dict(zip(_csw_agg["pitcher"], _csw_agg["curr_csw"]))

        df["curr_csw"]     = df["pitcher"].apply(lambda p: _csw_map.get(int(p)))
        df["career_csw_p"] = df["pitcher"].apply(lambda p: _career_csw_p.get(int(p)))
        df["csw_gap"]      = df.apply(
            lambda r: round(float(r["curr_csw"]) - float(r["career_csw_p"]), 4)
            if pd.notna(r["curr_csw"]) and pd.notna(r["career_csw_p"]) else float("nan"),
            axis=1,
        )

        _buy_lo   = df["verdict"] == "Buy low"
        _csw_up   = _buy_lo & (df["csw_gap"].fillna(0) >  _CSW_FIRE)
        _csw_down = _buy_lo & (df["csw_gap"].fillna(0) < -_CSW_FIRE)

        df.loc[_csw_up,   "luck_score"] = (df.loc[_csw_up,   "luck_score"] * _CSW_AMP ).round(4)
        df.loc[_csw_down, "luck_score"] = (df.loc[_csw_down, "luck_score"] * _CSW_DAMP).round(4)

        # Reclassify Buy low only — Slight buy and sells locked
        for _idx in df[_buy_lo].index:
            _ls = df.at[_idx, "luck_score"]
            if _ls > P_PROD_BUY_LOW:
                df.at[_idx, "verdict"] = "Buy low"
            elif _ls > P_PROD_SLIGHT_BUY:
                df.at[_idx, "verdict"] = "Slight buy"
            else:
                df.at[_idx, "verdict"] = "Neutral"

        _n_amp  = int(_csw_up.sum())
        _n_damp = int(_csw_down.sum())
        print(f"  CSW buy-low modifier: {_n_amp} amplified x{_CSW_AMP} | "
              f"{_n_damp} dampened x{_CSW_DAMP}")
    else:
        df["curr_csw"]     = float("nan")
        df["career_csw_p"] = float("nan")
        df["csw_gap"]      = float("nan")
        print("  CSW modifier: skipped (career CSW data or statcast CSV not found)")

    # ── Tier assignment ───────────────────────────────────────────────────────
    tiers = df.apply(
        lambda r: assign_pitcher_tier(
            r["luck_score"],
            r.get("xwoba_gap", float("nan")),
            r["verdict"],
            r["career_ip"],
            r["age"],
        ),
        axis=1,
    )
    df["tier_sell"] = tiers.apply(lambda t: t[0])
    df["age_flag"]  = tiers.apply(lambda t: t[1])

    df.sort_values("luck_score", ascending=False, inplace=True)
    df.reset_index(drop=True, inplace=True)

    # FIP- display cap: null out fip_minus for IP < 15 before writing.
    # Small-sample FIPs (bad relievers, <15 IP) produce wildly extreme FIP- values
    # (e.g. 343) that are misleading in any display context. Signal logic above
    # already used the real value; this only affects the output CSV / dashboard.
    if "IP" in df.columns and "fip_minus" in df.columns:
        low_ip_mask = df["IP"] < MIN_DISPLAY_IP
        n_capped = int(low_ip_mask.sum())
        df.loc[low_ip_mask, "fip_minus"] = float("nan")
        df.loc[low_ip_mask, "pitcher_quality_tier"] = "Unknown"
        if n_capped:
            print(f"  FIP- display cap: nulled fip_minus for {n_capped} pitchers with IP < {MIN_DISPLAY_IP}")

    # ── Merge ownership data from player_ownership_2026.csv ──────────────────
    own_path = os.path.join(BASE_DIR, "data", "player_ownership_2026.csv")
    if os.path.exists(own_path):
        try:
            import unicodedata as _ud
            def _norm_name(s):
                s = _ud.normalize("NFKD", str(s)).encode("ascii", "ignore").decode("ascii").lower()
                return " ".join(s.split())

            own = pd.read_csv(own_path, usecols=["player_name", "owned_pct"])
            own["_nkey"] = own["player_name"].apply(_norm_name)
            own_dedup = own.drop_duplicates("_nkey")[["_nkey", "owned_pct"]]
            df["_nkey"] = df["name"].apply(_norm_name)
            df = df.merge(own_dedup, on="_nkey", how="left")
            df = df.drop(columns=["_nkey"])
            n_matched = df["owned_pct"].notna().sum()
            print(f"  Pitcher ownership matched: {n_matched}/{len(df)} pitchers")
        except Exception as e:
            print(f"  Pitcher ownership merge skipped: {e}")
            if "owned_pct" not in df.columns:
                df["owned_pct"] = float("nan")
    else:
        df["owned_pct"] = float("nan")

    # ── Pitcher contract year flag (display only — no model weight) ──────────
    _p_cy_ids: set = set()
    if os.path.exists(PITCHER_CONTRACT_YEAR_PATH):
        try:
            _p_cy_df = pd.read_csv(PITCHER_CONTRACT_YEAR_PATH, comment="#")
            if "pitcher_id" in _p_cy_df.columns:
                _p_cy_ids = set(_p_cy_df["pitcher_id"].dropna().astype(int).tolist())
        except Exception:
            pass
    df["contract_year"] = df["pitcher"].apply(
        lambda p: int(p) in _p_cy_ids if pd.notna(p) else False
    )
    if _p_cy_ids:
        print(f"  Contract year flag: {int(df['contract_year'].sum())} pitchers flagged (display only)")

    # ── Standardised alias columns (for user queries) ───────────────────────
    # Keep original cols intact; add lowercase/snake_case aliases so that
    # queries using player_name / team / ip / player_type work without a join.
    df["player_name"] = df["name"]
    df["team"]        = df["Team"]
    df["ip"]          = df["IP"]

    # player_type: SP if Steamer projects GS >= 10, else RP
    try:
        _st = pd.read_csv(STEAMER_PIT_CSV, encoding="utf-8-sig",
                          usecols=["MLBAMID", "GS"])
        _st["MLBAMID"] = pd.to_numeric(_st["MLBAMID"], errors="coerce")
        _st["steamer_type"] = _st["GS"].apply(lambda x: "SP" if x >= 10 else "RP")
        _st_map = dict(zip(_st["MLBAMID"], _st["steamer_type"]))
        df["player_type"] = df["pitcher"].map(_st_map).fillna("RP")
    except Exception:
        df["player_type"] = "RP"

    # ── SP conversion override ────────────────────────────────────────────────
    # Pitchers Steamer classified as RP but demonstrably starting in 2026.
    # All four gates must pass: RP classification, >=5 starts, >=20 IP,
    # >=4.0 IP/start (filters openers and bulk relievers).
    df["role_override"] = False
    _ip_per_start = df["IP"] / df["total_starts"].replace(0, float("nan"))
    _sp_override_mask = (
        (df["player_type"] == "RP") &
        (df["total_starts"] >= 5) &
        (df["IP"] >= 20) &
        (_ip_per_start >= 4.0)
    )
    df.loc[_sp_override_mask, "player_type"]   = "SP"
    df.loc[_sp_override_mask, "role_override"] = True

    _n_override = int(_sp_override_mask.sum())
    print(f"  Role override: {_n_override} pitchers reclassified RP->SP")
    if _n_override:
        _names = df.loc[_sp_override_mask, "name"].tolist()
        for _nm in _names:
            print(f"    {_nm}")

    df.to_csv(OUTPUT_PATH, index=False)

    import shutil
    snapshot_path = os.path.join(BASE_DIR, "data", "snapshots",
                                 f"pitcher_luck_scores_april_{SEASON_YEAR}.csv")
    os.makedirs(os.path.dirname(snapshot_path), exist_ok=True)
    shutil.copy(OUTPUT_PATH, snapshot_path)
    print(f"  Snapshot saved: {snapshot_path}")

    # ── Terminal output (min 15 IP; full data still saved to CSV) ────────────
    display_cols = [c for c in [
        "name", "Team", "IP", "conf_phase", "luck_score", "verdict",
        "buy_qualified", "tier_sell", "age_flag",
        "volatility_flag", "volatility_label", "disaster_rate", "start_variance",
        "stuff_plus_avg", "best_pitch_type", "stuff_plus_signal",
        "park_factor", "fip_minus", "pitcher_quality_tier",
        "park_change", "park_change_label",
        "rtm_signal", "rtm_confluence", "amplification_cap_applied",
        "ERA", "FIP", "xERA", "ERA_minus_FIP", "ERA_minus_xERA",
        "BABIP_allowed", "lob_pct", "hr_fb_rate", "xwoba_gap",
        "hard_hit_rate_allowed", "barrel_rate_allowed", "swstr_rate", "gb_pct",
    ] if c in df.columns]

    qualified = df[df["IP"] >= MIN_DISPLAY_IP] if "IP" in df.columns else df

    buy_low  = (
        qualified[qualified["verdict"].isin(["Buy low", "Slight buy"])]
        .sort_values("luck_score", ascending=False)
        .head(10)
    )
    sell_high = (
        qualified[qualified["verdict"].isin(["Sell high", "Slight sell"])]
        .sort_values("luck_score", ascending=True)
        .head(10)
    )

    divider = "-" * 130

    print("\n" + divider)
    print(" TOP 10 BUY-LOW CANDIDATES  (unlucky — ERA running above true talent / results lagging underlying metrics)")
    print(divider)
    print(buy_low[display_cols].to_string(index=False))

    print("\n" + divider)
    print(" TOP 10 SELL-HIGH CANDIDATES  (lucky — ERA running below true talent / results ahead of underlying metrics)")
    print(divider)
    print(sell_high[display_cols].to_string(index=False))

    print(f"\nFull results saved to {OUTPUT_PATH}")
    print(
        f"Total pitchers scored: {len(df):,}  |  "
        f"Buy low: {(df['verdict'] == 'Buy low').sum()}  |  "
        f"Slight buy: {(df['verdict'] == 'Slight buy').sum()}  |  "
        f"Neutral: {(df['verdict'] == 'Neutral').sum()}  |  "
        f"Slight sell: {(df['verdict'] == 'Slight sell').sum()}  |  "
        f"Sell high: {(df['verdict'] == 'Sell high').sum()}"
    )


if __name__ == "__main__":
    main()
