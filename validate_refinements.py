"""
validate_refinements.py — Phase A model refinements validation (read-only)
Implements all 4 refinements in-memory and prints validation tables.
Does NOT write any output files.

Refinements:
  1. Park Factor Adjustment
  2. wRC+ Quality Gate (hitters)
  3. FIP- Quality Gate (pitchers)
  4. RTM Integration

Run: python validate_refinements.py
"""

import json
import math
import os
import sys

import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# Park factor table (hardcoded — FanGraphs + Baseball Reference blocked)
# Codes match Baseball Savant home_team / Statcast team codes
# ---------------------------------------------------------------------------
PARK_FACTORS = {
    # Extreme hitter friendly
    "COL": 1.18,   # Coors Field
    "CIN": 1.08,   # Great American
    "PHI": 1.06,   # Citizens Bank
    "TEX": 1.05,   # Globe Life
    # Pitcher friendly
    "SF":  0.91,   # Oracle Park
    "TB":  0.94,   # Tropicana
    "NYM": 0.95,   # Citi Field
    "MIA": 0.95,   # LoanDepot
    "ATH": 0.96,   # Sacramento / Oakland Coliseum era
}
DEFAULT_PARK_FACTOR = 1.00

# League baselines
LEAGUE_AVG_BABIP   = 0.300
LEAGUE_AVG_HRFB    = 0.145
LEAGUE_AVG_XWOBA   = 0.315   # MLB average xwOBA; used for pseudo wRC+ denominator

# ---------------------------------------------------------------------------
# Replicated modifier functions from score_luck.py (unchanged)
# ---------------------------------------------------------------------------

def _chase_modifier(o_swing: float, babip: float, pa: int = 0) -> float:
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
    return 2.0 - factor


def _zcon_babip_modifier(z_contact, babip, hard_hit_rate=float("nan"), pa=0):
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
    if hhr > 0.35:
        return 2.0 - base_factor
    elif hhr > 0.28:
        return 1.10 if base_factor == 0.75 else 1.05
    else:
        return 1.0


def _pull_modifier(pull_rate, hard_hit_rate=float("nan"), pa=0):
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
    if hhr > 0.35:
        return base
    elif hhr > 0.28:
        return base + 0.30 * (1.0 - base)
    else:
        return 1.0


def confidence_scale(pa: int, min_pa: int = 30, target_pa: int = 100) -> float:
    return min(1.0, max(0.0, (pa - min_pa) / (target_pa - min_pa)))


def assign_verdict_hitter(score: float) -> str:
    if score > 0.12:  return "Buy low"
    if score > 0.05:  return "Slight buy"
    if score < -0.12: return "Sell high"
    if score < -0.05: return "Slight sell"
    return "Neutral"


# ---------------------------------------------------------------------------
# New: Quality tier multiplier (buy signals only)
# ---------------------------------------------------------------------------
def quality_tier(wrc_plus: float):
    """Returns (multiplier, tier_label) from pseudo wRC+."""
    if wrc_plus >= 120: return 1.10, "Elite (120+)"
    if wrc_plus >= 100: return 1.00, "Above Avg (100-119)"
    if wrc_plus >= 95:  return 0.80, "Average (95-99)"
    if wrc_plus >= 85:  return 0.60, "Below Avg (85-94)"
    return 0.40, "Poor (<85)"


def sell_quality_flag(wrc_plus: float, existing_tier: str) -> str:
    """Override or supplement sell tier label based on wRC+."""
    if existing_tier:
        return existing_tier   # keep existing logic; wRC+ used for informational flag
    if wrc_plus >= 120:
        return "Sell High on Perception"
    if wrc_plus < 85:
        return "Sell and Move On"
    return None


# ---------------------------------------------------------------------------
# Amplification cap — prevents overconfidence when all signals align
# Max boost: 2.0× raw; Max suppression: 0.25× raw
# Preserves sign direction.
# ---------------------------------------------------------------------------
def apply_amplification_cap(combined: float, raw: float):
    """
    Clamp |combined| to [0.25 × |raw|, 2.0 × |raw|].
    Sign of result always matches sign of raw (or stays near zero if raw ≈ 0).
    Returns (capped_score, cap_fired_bool).
    """
    if abs(raw) < 1e-6:
        # No raw signal → clamp combined to zero (confidence-muted)
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
# Load data
# ---------------------------------------------------------------------------
def load_hitter_data():
    df = pd.read_csv(os.path.join(BASE_DIR, "hitter_luck_input.csv"))
    if "xwOBA" in df.columns and "wOBA" in df.columns:
        df["xwOBA_gap"] = (df["xwOBA"] - df["wOBA"]).round(4)
    else:
        df["xwOBA_gap"] = 0.0
    return df


def derive_batter_teams():
    """Most common Statcast team per batter (home when batting Bot, away when Top)."""
    sc_path = os.path.join(BASE_DIR, "hitters_statcast.csv")
    sc = pd.read_csv(sc_path, usecols=["batter", "home_team", "away_team", "inning_topbot"],
                     low_memory=False)
    sc["batter_team"] = sc.apply(
        lambda r: r["home_team"] if r["inning_topbot"] == "Bot" else r["away_team"], axis=1
    )
    return sc.groupby("batter")["batter_team"].agg(lambda x: x.mode()[0])


def derive_pitcher_teams():
    """Most common Statcast team per pitcher (home when away is batting Top, vice versa)."""
    sc_path = os.path.join(BASE_DIR, "pitchers_statcast.csv")
    sc = pd.read_csv(sc_path, usecols=["pitcher", "home_team", "away_team", "inning_topbot"],
                     low_memory=False)
    sc["pitcher_team"] = sc.apply(
        lambda r: r["home_team"] if r["inning_topbot"] == "Top" else r["away_team"], axis=1
    )
    return sc.groupby("pitcher")["pitcher_team"].agg(lambda x: x.mode()[0])


def load_career_quality():
    """Return dict: player_id (int) → {xwoba_3yr, ...}"""
    path = os.path.join(BASE_DIR, "data", "career_quality.json")
    with open(path) as f:
        records = json.load(f)
    return {int(r["player_id"]): r for r in records}


def load_career_stats():
    path = os.path.join(BASE_DIR, "data", "career_stats.json")
    with open(path) as f:
        return {int(k): v for k, v in json.load(f).items()}


# ---------------------------------------------------------------------------
# HITTER scoring with all 4 refinements
# ---------------------------------------------------------------------------
SEASON_YEAR = 2026

def score_hitters_refined(df, team_map, cq_dict, career_stats):
    """Apply all refinements. Returns df with new columns added."""

    # ── Assign team and park factor ──────────────────────────────────────────
    df["team"] = df["batter"].map(team_map).fillna("UNK")
    df["park_factor"] = df["team"].map(lambda t: PARK_FACTORS.get(t, DEFAULT_PARK_FACTOR))

    # Park-adjusted expected baselines
    df["park_adj_babip_expected"] = (LEAGUE_AVG_BABIP * df["park_factor"]).round(4)
    df["park_adj_hrfb_expected"]  = (LEAGUE_AVG_HRFB  * df["park_factor"]).round(4)

    # ── Load 3yr xwOBA from career_quality ──────────────────────────────────
    df["xwoba_3yr"] = df["batter"].map(
        lambda i: float(cq_dict[i]["xwoba_3yr"]) if i in cq_dict and not pd.isna(cq_dict[i].get("xwoba_3yr")) else float("nan")
    )

    # ── Pseudo wRC+ ─────────────────────────────────────────────────────────
    df["wrc_plus_3yr"] = df.apply(
        lambda r: round(
            (r["xwoba_3yr"] / LEAGUE_AVG_XWOBA) * r["park_factor"] * 100, 1
        ) if not math.isnan(r["xwoba_3yr"]) else 100.0,
        axis=1
    )
    df["quality_tier"] = df["wrc_plus_3yr"].apply(lambda w: quality_tier(w)[1])

    # ── Career stats for age / RTM ───────────────────────────────────────────
    df["career_pa"]  = df["batter"].map(lambda i: float((career_stats.get(i) or {}).get("career_pa") or 0))
    df["birth_year"] = df["batter"].map(lambda i: int((career_stats.get(i) or {}).get("birth_year") or 0))
    df["age"] = df["birth_year"].apply(lambda by: SEASON_YEAR - by if by > 0 else 0)

    # ── RTM signal: xwoba_3yr (true talent proxy) − current wOBA ───────────
    # Positive = currently underperforming career avg → buy confirmation
    # Negative = currently overperforming career avg → sell confirmation
    df["rtm_signal"] = df.apply(
        lambda r: round(r["xwoba_3yr"] - r["wOBA"], 4)
        if not math.isnan(r["xwoba_3yr"]) and not pd.isna(r["wOBA"]) else 0.0,
        axis=1
    )

    # ── Component 1: BABIP with park-adjusted expected baseline ─────────────
    has_hhr = "hard_hit_rate" in df.columns
    babip_comp = (df["BABIP"] - df["park_adj_babip_expected"]) * -3.000
    if "o_swing_rate" in df.columns:
        babip_comp = babip_comp * df.apply(
            lambda r: _chase_modifier(r["o_swing_rate"], r["BABIP"], int(r["PA"])), axis=1
        )
    babip_comp = babip_comp * df.apply(
        lambda r: _zcon_babip_modifier(
            r["z_contact_rate"], r["BABIP"],
            r["hard_hit_rate"] if has_hhr else float("nan"),
            int(r["PA"]),
        ), axis=1,
    )

    # ── Component 2: HR/FB with park-adjusted expected baseline ─────────────
    hrfb_comp = (df["hr_fb_rate"] - df["park_adj_hrfb_expected"]) * -0.150
    if "pull_rate" in df.columns:
        hrfb_comp = hrfb_comp * df.apply(
            lambda r: _pull_modifier(
                r["pull_rate"],
                r["hard_hit_rate"] if has_hhr else float("nan"),
                int(r["PA"]),
            ), axis=1,
        )

    # ── Component 3 & 4: unchanged ───────────────────────────────────────────
    zcon_comp  = (df["z_contact_rate"] - 0.880) * -0.030
    xwoba_comp = df["xwOBA_gap"] * 1.000

    df["luck_score_raw"] = (babip_comp + hrfb_comp + zcon_comp + xwoba_comp).round(4)

    # ── Confidence multiplier ────────────────────────────────────────────────
    df["luck_score_raw"] = (
        df.apply(lambda r: r["luck_score_raw"] * confidence_scale(int(r["PA"])), axis=1)
        .round(4)
    )

    # ── Playing time discount (applied after confidence scale) ───────────────
    # Compares each player's PA to P90 of the dataset (proxy for full-starter PA)
    # at the current point in the season. Players well below P90 are likely
    # platoon/part-time, so their luck signal carries lower actionability.
    p90_pa = float(df["PA"].quantile(0.90))
    def playing_time_scale(pa: int) -> float:
        rate = min(1.0, pa / p90_pa) if p90_pa > 0 else 1.0
        if rate >= 0.65:
            return 1.00   # starter or near-starter
        if rate >= 0.45:
            return 0.80   # part-time / platoon
        return 0.60       # spot / bench
    df["pt_scale"] = df["PA"].apply(lambda pa: playing_time_scale(int(pa)))
    df["luck_score_raw"] = (df["luck_score_raw"] * df["pt_scale"]).round(4)

    # ── Rising boost ────────────────────────────────────────────────────────
    rising_mask = (df["age"] > 0) & (df["age"] < 28) & (df["luck_score_raw"] > 0)
    df.loc[rising_mask, "luck_score_raw"] = (df.loc[rising_mask, "luck_score_raw"] + 0.02).round(4)

    # ── Quality tier multiplier (buy signals only) ───────────────────────────
    # Applied before RTM so cap is relative to quality-adjusted raw
    def apply_quality_mult(row):
        score = row["luck_score_raw"]
        if score <= 0:
            return score   # sell / neutral: no multiplier on score
        mult, _ = quality_tier(row["wrc_plus_3yr"])
        return round(score * mult, 4)

    df["luck_after_quality"] = df.apply(apply_quality_mult, axis=1)

    # ── RTM integration ──────────────────────────────────────────────────────
    rtm_weight  = 0.25
    luck_weight = 0.75

    df["rtm_confluence"] = df.apply(
        lambda r: (
            "Buy confluence"  if r["luck_after_quality"] > 0 and r["rtm_signal"] > 0 else
            "Sell confluence" if r["luck_after_quality"] < 0 and r["rtm_signal"] < 0 else
            "No confluence"
        ), axis=1
    )

    def combine_rtm(row):
        ls = row["luck_after_quality"]
        rt = row["rtm_signal"]
        combined = ls * luck_weight + (rt * 10) * rtm_weight
        # Confluence bonus
        if (ls > 0 and rt > 0) or (ls < 0 and rt < 0):
            combined *= 1.15
        return round(combined, 4)

    df["luck_score_combined"] = df.apply(combine_rtm, axis=1)

    # ── Amplification cap ────────────────────────────────────────────────────
    cap_results = df.apply(
        lambda r: apply_amplification_cap(r["luck_score_combined"], r["luck_score_raw"]),
        axis=1
    )
    df["luck_score_final"] = cap_results.apply(lambda t: t[0])
    df["amplification_cap_applied"] = cap_results.apply(lambda t: t[1])

    df["verdict"] = df["luck_score_final"].apply(assign_verdict_hitter)

    df.sort_values("luck_score_final", ascending=False, inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


# ---------------------------------------------------------------------------
# PITCHER scoring with Refinements 1, 3, 4
# ---------------------------------------------------------------------------
def score_pitchers_refined(pli, plc, pitcher_team_map=None):
    """
    pli: pitcher_luck_input.csv (has FIP, Team, etc.)
    plc: pitcher_luck_scores.csv (has existing luck_score, career_ip, age)
    pitcher_team_map: Series indexed by pitcher MLBAM ID → team code
    Returns merged df with refinement columns.
    """
    # Merge input with existing scores for career_ip / age / buy_qualified
    df = pli.copy()
    for col in ["career_ip", "age", "birth_year", "luck_score", "verdict", "buy_qualified",
                "tier_sell", "xwoba_gap", "gb_pct"]:
        if col in plc.columns and col not in df.columns:
            df = df.merge(plc[["pitcher", col]].drop_duplicates("pitcher"), on="pitcher", how="left")

    # ── Park factor — derive team from Statcast if Team col is blank ─────────
    if pitcher_team_map is not None:
        df["pitcher"] = df["pitcher"].astype("Int64")
        df["Team"] = df["pitcher"].map(pitcher_team_map).fillna("UNK")
    df["park_factor"] = df["Team"].map(lambda t: PARK_FACTORS.get(str(t), DEFAULT_PARK_FACTOR))

    # ── FIP- (park-adjusted) ─────────────────────────────────────────────────
    qualified_fip = df[df["IP"] >= 20]["FIP"].dropna()
    if len(qualified_fip) == 0:
        qualified_fip = df["FIP"].dropna()
    league_avg_fip = qualified_fip.mean()
    print(f"  League avg FIP (>=20 IP pitchers): {league_avg_fip:.3f}")

    # park-adjusted: pitcher in hitter park has inflated FIP → discount it
    # fip_minus_adj = (FIP / league_avg) × (1/park_factor) × 100
    df["fip_minus"] = df.apply(
        lambda r: round(
            (r["FIP"] / league_avg_fip) * (1.0 / r["park_factor"]) * 100, 1
        ) if not pd.isna(r.get("FIP")) else float("nan"),
        axis=1
    )

    def pitcher_quality_tier(fip_m):
        if math.isnan(fip_m): return (1.00, "Unknown")
        if fip_m < 80:   return (1.10, "Elite (FIP-<80)")
        if fip_m <= 95:  return (1.00, "Above Avg (80-95)")
        if fip_m <= 105: return (0.80, "Average (95-105)")
        if fip_m <= 115: return (0.60, "Below Avg (105-115)")
        return (0.40, "Poor (FIP->115)")

    df["pitcher_quality_tier"] = df["fip_minus"].apply(lambda f: pitcher_quality_tier(f)[1])

    # ── RTM signal for pitchers ───────────────────────────────────────────────
    # career_FIP not in pipeline; use xERA vs FIP as a structural proxy:
    # If FIP < xERA → ERA may normalize upward (sell signal strengthened)
    # If FIP > xERA → ERA may normalize downward (buy signal)
    # rtm_signal > 0 = buy confirmation; rtm_signal < 0 = sell confirmation
    if "xERA" in df.columns and "FIP" in df.columns:
        df["rtm_signal"] = df.apply(
            lambda r: round(float(r["FIP"]) - float(r["xERA"]), 4)
            if not pd.isna(r.get("FIP")) and not pd.isna(r.get("xERA")) else 0.0,
            axis=1
        )
    else:
        df["rtm_signal"] = 0.0

    df["rtm_confluence"] = df.apply(
        lambda r: (
            "Buy confluence"  if r["luck_score"] > 0 and r["rtm_signal"] > 0 else
            "Sell confluence" if r["luck_score"] < 0 and r["rtm_signal"] < 0 else
            "No confluence"
        ), axis=1
    )

    # ── Apply park adjustment to luck score ──────────────────────────────────
    # Park factor affects expected BABIP allowed — shift BABIP component
    # Approximation: adjust the raw luck score by (pf - 1.0) * BABIP_weight * BABIP_allowed
    # (Proper re-score would require re-running score_pitcher_luck; this is a quick adjustment)
    if "BABIP_allowed" in df.columns:
        babip_park_adj = (
            (LEAGUE_AVG_BABIP * df["park_factor"] - LEAGUE_AVG_BABIP) * 5.0
        )
        df["luck_score_park_adj"] = (df["luck_score"] - babip_park_adj).round(4)
    else:
        df["luck_score_park_adj"] = df["luck_score"]

    # ── Quality multiplier on buy signals ────────────────────────────────────
    def apply_pitcher_quality(row):
        score = row["luck_score_park_adj"]
        if score <= 0:
            return score
        mult, _ = pitcher_quality_tier(
            row["fip_minus"] if not pd.isna(row["fip_minus"]) else 100.0
        )
        return round(score * mult, 4)

    df["luck_after_quality"] = df.apply(apply_pitcher_quality, axis=1)

    # ── RTM integration ──────────────────────────────────────────────────────
    def combine_pitcher_rtm(row):
        ls = row["luck_after_quality"]
        rt = row["rtm_signal"]
        combined = ls * 0.75 + (rt * 0.15) * 0.25   # xERA gap scaled differently than wOBA
        if (ls > 0 and rt > 0) or (ls < 0 and rt < 0):
            combined *= 1.15
        return round(combined, 4)

    df["luck_score_final"] = df.apply(combine_pitcher_rtm, axis=1)

    cap_results = df.apply(
        lambda r: apply_amplification_cap(r["luck_score_final"], r["luck_score"]),
        axis=1
    )
    df["luck_score_final"] = cap_results.apply(lambda t: t[0])
    df["amplification_cap_applied"] = cap_results.apply(lambda t: t[1])

    df.sort_values("luck_score_final", ascending=False, inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


# ---------------------------------------------------------------------------
# Validation output
# ---------------------------------------------------------------------------
def fmt(val, dec=4):
    if pd.isna(val): return "—"
    if isinstance(val, float): return f"{val:.{dec}f}"
    return str(val)


def print_hitter_table(df, label, n=10, verdict_filter=None, ascending=None):
    if verdict_filter:
        sub = df[df["verdict"].isin(verdict_filter)]
    else:
        sub = df
    if ascending is not None:
        sub = sub.sort_values("luck_score_final", ascending=ascending)
    sub = sub.head(n)

    cols = ["name", "team", "PA", "park_factor", "park_adj_babip_expected",
            "wrc_plus_3yr", "quality_tier", "rtm_signal", "rtm_confluence",
            "amplification_cap_applied", "luck_score_raw", "luck_score_final", "verdict"]
    cols = [c for c in cols if c in sub.columns]

    div = "-" * 130
    print(f"\n{div}")
    print(f" {label}")
    print(div)
    print(sub[cols].to_string(index=False))


def print_pitcher_table(df, label, n=5, verdict_filter=None, ascending=False):
    if verdict_filter:
        sub = df[df["verdict"].isin(verdict_filter)]
    else:
        sub = df
    sub = sub.sort_values("luck_score_final", ascending=ascending).head(n)

    cols = ["name", "Team", "IP", "park_factor", "fip_minus", "pitcher_quality_tier",
            "rtm_signal", "rtm_confluence", "amplification_cap_applied",
            "luck_score", "luck_score_final", "verdict"]
    cols = [c for c in cols if c in sub.columns]

    div = "-" * 130
    print(f"\n{div}")
    print(f" {label}")
    print(div)
    print(sub[cols].to_string(index=False))


def spot_check(df_h, df_p, names_h, names_p):
    div = "-" * 130
    print(f"\n{div}")
    print(" SPOT CHECKS")
    print(div)

    hitter_cols = ["name", "team", "PA", "park_factor", "park_adj_babip_expected",
                   "wrc_plus_3yr", "quality_tier", "rtm_signal", "rtm_confluence",
                   "amplification_cap_applied", "BABIP", "xwOBA_gap",
                   "luck_score_raw", "luck_score_final", "verdict"]
    hitter_cols = [c for c in hitter_cols if c in df_h.columns]

    for name in names_h:
        rows = df_h[df_h["name"].str.contains(name, case=False, na=False)]
        if rows.empty:
            print(f"  {name}: NOT FOUND in hitter data")
        else:
            print(f"\n  {name}:")
            print(rows[hitter_cols].to_string(index=False))

    pitcher_cols = ["name", "Team", "IP", "park_factor", "FIP", "fip_minus",
                    "pitcher_quality_tier", "rtm_signal", "rtm_confluence",
                    "amplification_cap_applied", "luck_score", "luck_score_final", "verdict"]
    pitcher_cols = [c for c in pitcher_cols if c in df_p.columns]

    for name in names_p:
        rows = df_p[df_p["name"].str.contains(name, case=False, na=False)]
        if rows.empty:
            print(f"  {name}: NOT FOUND in pitcher data")
        else:
            print(f"\n  {name}:")
            print(rows[pitcher_cols].to_string(index=False))

    # Rockies and Giants hitters
    for team, label in [("COL", "Rockies hitters"), ("SF", "Giants hitters"),
                        ("COL", "Rockies pitchers"), ("SF", "Giants pitchers")]:
        if label.endswith("hitters"):
            rows = df_h[df_h["team"] == team].head(3)
            cols = hitter_cols
        else:
            rows = df_p[df_p["Team"] == team].head(3)
            cols = pitcher_cols
        if rows.empty:
            print(f"\n  {label}: none in dataset")
        else:
            print(f"\n  {label} (top 3 by luck_score_final):")
            print(rows[cols].to_string(index=False))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("=" * 70)
    print("PHASE A REFINEMENTS VALIDATION — read-only, no files written")
    print("=" * 70)

    print("\nLoading data...")
    df_h       = load_hitter_data()
    team_map   = derive_batter_teams()
    cq_dict    = load_career_quality()
    career_stats = load_career_stats()

    df_p_input  = pd.read_csv(os.path.join(BASE_DIR, "pitcher_luck_input.csv"))
    df_p_scores = pd.read_csv(os.path.join(BASE_DIR, "pitcher_luck_scores.csv"))

    # Need pitcher to be consistent type for merge
    df_p_scores["pitcher"] = df_p_scores["pitcher"].astype("Int64")
    df_p_input["pitcher"]  = df_p_input["pitcher"].astype("Int64")

    print(f"  Hitters: {len(df_h):,}  |  Pitchers input: {len(df_p_input):,}")
    print(f"  Team map: {len(team_map):,} batters  |  CQ records: {len(cq_dict):,}")

    print("\nScoring hitters with refinements...")
    df_h = score_hitters_refined(df_h, team_map, cq_dict, career_stats)
    print(f"  Done. Verdicts — Buy low: {(df_h['verdict']=='Buy low').sum()}  "
          f"Sell high: {(df_h['verdict']=='Sell high').sum()}")

    print("Deriving pitcher teams from pitchers_statcast.csv...")
    pitcher_team_map = derive_pitcher_teams()
    print(f"  Pitcher team map: {len(pitcher_team_map):,} pitchers")

    print("\nScoring pitchers with refinements...")
    df_p = score_pitchers_refined(df_p_input, df_p_scores, pitcher_team_map)
    print(f"  Done.")

    # ── Validation tables ────────────────────────────────────────────────────
    print_hitter_table(
        df_h, "TOP 10 BUY LOW HITTERS (refined)",
        n=10, verdict_filter=["Buy low", "Slight buy"], ascending=False
    )
    print_hitter_table(
        df_h, "TOP 5 SELL HIGH HITTERS (refined)",
        n=5, verdict_filter=["Sell high", "Slight sell"], ascending=True
    )
    print_pitcher_table(
        df_p, "TOP 5 PITCHER BUY LOW (refined)",
        n=5, verdict_filter=["Buy low", "Slight buy"], ascending=False
    )
    print_pitcher_table(
        df_p, "TOP 5 PITCHER SELL HIGH (refined)",
        n=5, verdict_filter=["Sell high", "Slight sell"], ascending=True
    )

    # ── Spot checks ──────────────────────────────────────────────────────────
    spot_check(
        df_h, df_p,
        names_h=["Lindor", "Pasquantino", "Oneil Cruz"],
        names_p=["Luzardo"],
    )

    # ── Distribution comparison: v4 original vs refined ─────────────────────
    print("\n" + "-" * 70)
    print(" SCORE SHIFT SUMMARY (refined vs original v4)")
    print("-" * 70)
    orig = pd.read_csv(os.path.join(BASE_DIR, "luck_scores.csv"))
    merged = df_h[["batter","name","luck_score_final"]].merge(
        orig[["batter","luck_score"]].rename(columns={"luck_score": "luck_v4"}),
        on="batter", how="inner"
    )
    merged["delta"] = merged["luck_score_final"] - merged["luck_v4"]
    print(f"  Mean delta (refined - v4): {merged['delta'].mean():+.4f}")
    print(f"  Std delta:                 {merged['delta'].std():.4f}")
    print(f"  Max boost:                 {merged['delta'].max():+.4f}")
    print(f"  Max suppression:           {merged['delta'].min():+.4f}")
    print(f"  Players w/ score change > 0.05: {(merged['delta'].abs() > 0.05).sum()}")
    print(f"  Players w/ score change > 0.10: {(merged['delta'].abs() > 0.10).sum()}")

    print("\nValidation complete. No files written.")


if __name__ == "__main__":
    main()
