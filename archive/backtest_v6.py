"""
backtest_v6.py

Full out-of-sample backtest comparing v4, v5 (Phase A), and v6 (Phase B).

Methodology:
  Scoring years : 2022, 2023, 2024  (April Statcast → luck scores)
  Outcome years : 2023, 2024, 2025  (full-season wOBA delta)
  Qualification : >= 300 PA scoring year (full season) AND >= 300 PA outcome year

  v4  — BABIP + HR/FB + Z-contact + xwOBA gap + contextual modifiers (park-agnostic)
  v5  — Phase A: park factors + wRC+ quality gate + RTM + PT discount + amp cap
  v6  — Phase B: v5 × per-player consistency multiplier

Component breakdown (cumulative):
  park     — v4 + park factor only
  quality  — park + wRC+ quality gate
  v5       — quality + RTM + PT discount + amp cap
  v6       — v5 + consistency multiplier

Usage:
  python backtest_v6.py          # print results, save report (no CSV)
  python backtest_v6.py --write  # also write backtest_v6_raw.csv
"""

import io
import json
import math
import os
import sys
import time

import numpy as np
import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

try:
    import pybaseball
    from pybaseball import statcast, statcast_batter_expected_stats, playerid_reverse_lookup
    pybaseball.cache.enable()
except ImportError:
    sys.exit("pybaseball not installed")

try:
    from scipy import stats as scipy_stats
except ImportError:
    sys.exit("scipy not installed")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR   = os.path.join(BASE_DIR, "backtest_cache")
DATA_DIR    = os.path.join(BASE_DIR, "data")
RAW_OUTPUT  = os.path.join(BASE_DIR, "backtest_v6_raw.csv")
REPORT_PATH = os.path.join(BASE_DIR, "backtest_results_v6.md")
os.makedirs(CACHE_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SCORING_YEARS     = [2022, 2023, 2024]
MIN_SCORING_PA    = 300
MIN_OUTCOME_PA    = 300
LEAGUE_AVG_WOBA   = 0.315
LEAGUE_AVG_BABIP  = 0.300
LEAGUE_AVG_HRFB   = 0.145
LEAGUE_AVG_XWOBA  = 0.315

APRIL_DATES = {
    2022: ("2022-04-07", "2022-04-30"),
    2023: ("2023-03-30", "2023-04-30"),
    2024: ("2024-03-20", "2024-04-30"),
}

PARK_FACTORS = {
    "COL": 1.18, "CIN": 1.08, "PHI": 1.06, "TEX": 1.05,
    "SF":  0.91, "TB":  0.94, "NYM": 0.95, "MIA": 0.95, "ATH": 0.96,
}

KEEP_COLS = [
    "game_date", "batter", "stand",
    "events", "description", "bb_type",
    "launch_speed", "launch_angle", "launch_speed_angle",
    "zone", "hc_x", "hc_y",
    "woba_value", "estimated_woba_using_speedangle",
]

# ---------------------------------------------------------------------------
# Event sets
# ---------------------------------------------------------------------------
CONTACT_DESCS    = {"hit_into_play","foul","foul_tip","foul_bunt","bunt_foul_tip"}
SWING_MISS_DESCS = {"swinging_strike","swinging_strike_blocked","missed_bunt"}
SWING_DESCS      = CONTACT_DESCS | SWING_MISS_DESCS
BIP_EVENTS       = {"single","double","triple","field_out","force_out",
                    "grounded_into_double_play","double_play","fielders_choice",
                    "fielders_choice_out","field_error","sac_fly","sac_fly_double_play"}
HIT_BIP_EVENTS   = {"single","double","triple"}
FAIR_BIP_EVENTS  = BIP_EVENTS | {"home_run"}
NON_PA_EVENTS    = {"truncated_pa"}
TRUE_OUTCOME_EVENTS = {"home_run","strikeout","strikeout_double_play",
                       "walk","intent_walk","hit_by_pitch"}
HP_X, HP_Y          = 125.42, 198.27
PULL_ANGLE_THRESHOLD = 20.0

# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def _v4_cache_path(year): return os.path.join(CACHE_DIR, f"v4_april_{year}.csv")
def _team_cache_path(year): return os.path.join(CACHE_DIR, f"team_map_{year}.csv")
def _exp_cache_path(year): return os.path.join(CACHE_DIR, f"expected_stats_{year}.csv")


def fetch_april(year: int) -> pd.DataFrame:
    path = _v4_cache_path(year)
    if os.path.exists(path):
        print(f"  Loading cached v4 April {year}")
        return pd.read_csv(path, low_memory=False)
    start_dt, end_dt = APRIL_DATES[year]
    print(f"  Downloading {year} April ({start_dt}→{end_dt}) ...")
    t0 = time.time()
    df = statcast(start_dt=start_dt, end_dt=end_dt)
    print(f"    -> {len(df):,} rows in {time.time()-t0:.0f}s")
    cols = [c for c in KEEP_COLS if c in df.columns]
    df = df[cols].copy()
    df.to_csv(path, index=False)
    return df


def fetch_team_map(year: int) -> dict:
    """
    Returns {batter_id: team_code} for April of scoring year.
    Caches to team_map_{year}.csv.
    """
    path = _team_cache_path(year)
    if os.path.exists(path):
        df = pd.read_csv(path)
        return dict(zip(df["batter"].astype(int), df["team"].astype(str)))
    start_dt, end_dt = APRIL_DATES[year]
    print(f"  Fetching team map for {year} (reusing pybaseball cache)...")
    t0 = time.time()
    raw = statcast(start_dt=start_dt, end_dt=end_dt)
    print(f"    -> done in {time.time()-t0:.0f}s")
    if "home_team" not in raw.columns or "inning_topbot" not in raw.columns:
        print(f"    WARNING: team columns not found — using DEFAULT park factor")
        return {}
    raw = raw[raw["batter"].notna()].copy()
    raw["batter"] = raw["batter"].astype(int)
    raw["batter_team"] = raw.apply(
        lambda r: r["home_team"] if r["inning_topbot"] == "Bot" else r["away_team"], axis=1
    )
    team_map = raw.groupby("batter")["batter_team"].agg(lambda x: x.mode().iloc[0])
    team_df = team_map.reset_index()
    team_df.columns = ["batter", "team"]
    team_df.to_csv(path, index=False)
    return dict(zip(team_df["batter"].astype(int), team_df["team"].astype(str)))


def fetch_full_season_stats(years: list) -> pd.DataFrame:
    frames = []
    for yr in years:
        path = _exp_cache_path(yr)
        if os.path.exists(path):
            print(f"  Loading cached {yr} expected stats")
            df = pd.read_csv(path)
        else:
            print(f"  Fetching {yr} expected stats ...")
            raw = statcast_batter_expected_stats(yr)
            keep = [c for c in ["player_id","est_woba","woba","pa"] if c in raw.columns]
            df = raw[keep].copy().rename(columns={"est_woba": "xwoba"})
            df["year"] = yr
            df.to_csv(path, index=False)
        if "year" not in df.columns:
            df["year"] = yr
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------------------
# Metric aggregation
# ---------------------------------------------------------------------------

def _safe_div(n, d):
    return n.div(d).where(d > 0, other=float("nan"))

def _agg_pa(df):
    return df[df["events"].notna() & ~df["events"].isin(NON_PA_EVENTS)].groupby("batter").size().rename("PA")

def _agg_babip(df):
    bip = df[df["events"].isin(BIP_EVENTS | HIT_BIP_EVENTS)]
    g = bip.groupby("batter")
    return _safe_div(
        g["events"].apply(lambda s: s.isin(HIT_BIP_EVENTS).sum()),
        g["events"].apply(lambda s: s.isin(BIP_EVENTS | HIT_BIP_EVENTS).sum()),
    ).rename("BABIP")

def _agg_hard_hit(df):
    bbe = df[df["launch_speed"].notna()]
    g = bbe.groupby("batter")
    return _safe_div(g["launch_speed"].apply(lambda s: (s >= 95).sum()), g["launch_speed"].count()).rename("hard_hit_rate")

def _agg_barrel(df):
    bbe = df[df["launch_speed"].notna()]
    g = bbe.groupby("batter")
    return _safe_div(g["launch_speed_angle"].apply(lambda s: (s == 6).sum()), g["launch_speed"].count()).rename("barrel_rate")

def _agg_z_contact(df):
    iz = df[df["zone"].between(1, 9)]
    sw = iz[iz["description"].isin(SWING_DESCS)]
    g = sw.groupby("batter")
    return _safe_div(g["description"].apply(lambda s: s.isin(CONTACT_DESCS).sum()), g["description"].count()).rename("z_contact_rate")

def _agg_hr_fb(df):
    pa = df[df["events"].notna()]
    g = pa.groupby("batter")
    return _safe_div(g["events"].apply(lambda s: (s == "home_run").sum()),
                     g["bb_type"].apply(lambda s: (s == "fly_ball").sum())).rename("hr_fb_rate")

def _agg_pull_rate(df):
    if "hc_x" not in df.columns or "stand" not in df.columns:
        return pd.Series(dtype=float, name="pull_rate")
    fair = df[df["events"].isin(FAIR_BIP_EVENTS) & df["hc_x"].notna() & df["hc_y"].notna()].copy()
    if fair.empty:
        return pd.Series(dtype=float, name="pull_rate")
    angle = np.degrees(np.arctan2(fair["hc_x"] - HP_X, HP_Y - fair["hc_y"]))
    fair["pulled"] = (
        ((fair["stand"] == "R") & (angle < -PULL_ANGLE_THRESHOLD))
        | ((fair["stand"] == "L") & (angle > PULL_ANGLE_THRESHOLD))
    )
    g = fair.groupby("batter")
    return _safe_div(g["pulled"].sum(), g["pulled"].count()).rename("pull_rate")

def _agg_o_swing(df):
    oz = df[df["zone"].isin([11, 12, 13, 14])]
    g = oz.groupby("batter")
    return _safe_div(g["description"].apply(lambda s: s.isin(SWING_DESCS).sum()), g["description"].count()).rename("o_swing_rate")

def _agg_woba(df):
    pa = df[df["events"].notna() & ~df["events"].isin(NON_PA_EVENTS)]
    g = pa.groupby("batter")
    return _safe_div(g["woba_value"].sum(), g.size()).rename("wOBA")

def _agg_xwoba(df):
    if "estimated_woba_using_speedangle" not in df.columns:
        return _agg_woba(df).rename("xwOBA")
    pa = df[df["events"].notna() & ~df["events"].isin(NON_PA_EVENTS)].copy()
    pa["xw"] = pa["estimated_woba_using_speedangle"]
    fb = pa["xw"].isna() | pa["events"].isin(TRUE_OUTCOME_EVENTS)
    pa.loc[fb, "xw"] = pa.loc[fb, "woba_value"]
    g = pa.groupby("batter")
    return _safe_div(g["xw"].sum(), g.size()).rename("xwOBA")

def aggregate_april(df: pd.DataFrame) -> pd.DataFrame:
    parts = [
        _agg_pa(df), _agg_babip(df), _agg_hard_hit(df), _agg_barrel(df),
        _agg_z_contact(df), _agg_hr_fb(df), _agg_pull_rate(df), _agg_o_swing(df),
        _agg_woba(df), _agg_xwoba(df),
    ]
    return pd.concat(parts, axis=1)


# ---------------------------------------------------------------------------
# Shared modifier functions (v3/v4, same in v4 and v5)
# ---------------------------------------------------------------------------

def _nan(x):
    try:
        v = float(x); return float("nan") if math.isnan(v) else v
    except (TypeError, ValueError): return float("nan")

def _chase_mod(o_swing, babip, pa):
    if math.isnan(o_swing): return 1.0
    factor = 1.25 if o_swing > 0.40 else (1.15 if o_swing > 0.35 else None)
    if factor is None: return 1.0
    if babip > 0.300: return factor
    return 1.0 if pa < 75 else 2.0 - factor

def _zcon_mod(z_contact, babip, hhr=float("nan"), pa=0):
    if math.isnan(z_contact): return 1.0
    if z_contact > 0.92: base = 0.75
    elif z_contact > 0.88: base = 0.85
    else: return 1.0
    if babip > 0.300: return base
    if pa < 75: return 1.0
    h = 0.0 if math.isnan(hhr) else hhr
    if h > 0.35: return 2.0 - base
    if h > 0.28: return 1.10 if base == 0.75 else 1.05
    return 1.0

def _pull_mod(pull, hhr=float("nan"), pa=0):
    if math.isnan(pull) or pa < 75: return 1.0
    if pull > 0.45: base = 0.65
    elif pull > 0.40: base = 0.80
    else: return 1.0
    h = 0.0 if math.isnan(hhr) else hhr
    if h > 0.35: return base
    if h > 0.28: return base + 0.30 * (1.0 - base)
    return 1.0

def _conf_scale(pa): return min(1.0, max(0.0, (pa - 30) / 70))

def _quality_mult(wrc_plus):
    if wrc_plus >= 130: return 1.15
    if wrc_plus >= 120: return 1.10
    if wrc_plus >= 100: return 1.00
    if wrc_plus >= 95:  return 0.80
    if wrc_plus >= 85:  return 0.60
    return 0.40

def _quality_mult_no_superstar(wrc_plus):
    """Elite tier capped at 120+ (×1.10), no separate Superstar ×1.15."""
    if wrc_plus >= 120: return 1.10
    if wrc_plus >= 100: return 1.00
    if wrc_plus >= 95:  return 0.80
    if wrc_plus >= 85:  return 0.60
    return 0.40

def _pt_scale(pa, p90_pa):
    if p90_pa <= 0: return 1.0
    rate = min(1.0, pa / p90_pa)
    if rate >= 0.65: return 1.00
    if rate >= 0.45: return 0.80
    return 0.60

def _amp_cap(combined, raw):
    if abs(raw) < 1e-6: return 0.0, False
    cap_fired = False
    if abs(combined) > 2.0 * abs(raw):
        combined = math.copysign(2.0 * abs(raw), raw); cap_fired = True
    elif abs(combined) < 0.25 * abs(raw):
        combined = math.copysign(0.25 * abs(raw), raw); cap_fired = True
    return round(combined, 4), cap_fired


# ---------------------------------------------------------------------------
# V4 scoring
# ---------------------------------------------------------------------------

def compute_v4_luck(agg: pd.DataFrame) -> pd.Series:
    scores = []
    for _, r in agg.iterrows():
        pa    = int(r.get("PA", 0) or 0)
        babip = _nan(r.get("BABIP")); hrfb  = _nan(r.get("hr_fb_rate"))
        zcon  = _nan(r.get("z_contact_rate")); hhr   = _nan(r.get("hard_hit_rate"))
        pull  = _nan(r.get("pull_rate")); oswing = _nan(r.get("o_swing_rate"))
        woba  = _nan(r.get("wOBA")); xwoba = _nan(r.get("xwOBA"))

        xgap = (xwoba - woba) if not (math.isnan(xwoba) or math.isnan(woba)) else 0.0

        babip_c = 0.0
        if not math.isnan(babip):
            babip_c = (babip - 0.300) * -3.000
            babip_c *= _chase_mod(oswing, babip, pa)
            babip_c *= _zcon_mod(zcon, babip, hhr, pa)

        hrfb_c = 0.0
        if not math.isnan(hrfb):
            hrfb_c = (hrfb - 0.145) * -0.150
            hrfb_c *= _pull_mod(pull, hhr, pa)

        zcon_c  = (zcon - 0.880) * -0.030 if not math.isnan(zcon) else 0.0
        xwoba_c = xgap * 1.000

        score = (babip_c + hrfb_c + zcon_c + xwoba_c) * _conf_scale(pa)
        scores.append(round(score, 4))
    return pd.Series(scores, index=agg.index, name="luck_score_v4")


# ---------------------------------------------------------------------------
# V5 scoring (Phase A: park + quality + RTM + PT + amp cap)
# ---------------------------------------------------------------------------

def compute_v5_luck(
    agg: pd.DataFrame,
    team_map: dict,
    prior_xwoba: dict,
    birth_years: dict,
    scoring_year: int,
    variant: str = "full",
) -> pd.Series:
    """
    variant options:
      'full'       — complete v5 (park + quality + RTM + PT + amp cap)
      'park_only'  — v4 + park factor only
      'park_quality' — v4 + park + quality gate (no RTM, PT, amp)
    """
    p90_pa = float(agg["PA"].quantile(0.90)) if len(agg) > 10 else 100.0

    scores = []
    for batter_id, r in agg.iterrows():
        pa     = int(r.get("PA", 0) or 0)
        babip  = _nan(r.get("BABIP")); hrfb   = _nan(r.get("hr_fb_rate"))
        zcon   = _nan(r.get("z_contact_rate")); hhr    = _nan(r.get("hard_hit_rate"))
        pull   = _nan(r.get("pull_rate")); oswing = _nan(r.get("o_swing_rate"))
        woba   = _nan(r.get("wOBA")); xwoba  = _nan(r.get("xwOBA"))

        xgap = (xwoba - woba) if not (math.isnan(xwoba) or math.isnan(woba)) else 0.0

        # Park factor
        team = team_map.get(int(batter_id), "UNK")
        pf = PARK_FACTORS.get(str(team), 1.0)
        babip_exp = LEAGUE_AVG_BABIP * pf
        hrfb_exp  = LEAGUE_AVG_HRFB  * pf

        # Components 1-4
        babip_c = 0.0
        if not math.isnan(babip):
            babip_c = (babip - babip_exp) * -3.000
            babip_c *= _chase_mod(oswing, babip, pa)
            babip_c *= _zcon_mod(zcon, babip, hhr, pa)

        hrfb_c = 0.0
        if not math.isnan(hrfb):
            hrfb_c = (hrfb - hrfb_exp) * -0.150
            hrfb_c *= _pull_mod(pull, hhr, pa)

        zcon_c  = (zcon - 0.880) * -0.030 if not math.isnan(zcon) else 0.0
        xwoba_c = xgap * 1.000

        score = (babip_c + hrfb_c + zcon_c + xwoba_c) * _conf_scale(pa)

        if variant == "park_only":
            scores.append(round(score, 4))
            continue

        # PT discount
        if variant in ("park_quality", "full"):
            score = round(score * _pt_scale(pa, p90_pa), 4)

        # Prior xwOBA → wRC+
        xw3 = prior_xwoba.get(int(batter_id), float("nan"))
        wrc = (xw3 / LEAGUE_AVG_XWOBA) * pf * 100 if not math.isnan(xw3) else 100.0

        # Quality gate (buy signals only)
        raw_for_cap = score  # cap reference is pre-quality/RTM
        if score > 0:
            score = round(score * _quality_mult(wrc), 4)

        if variant == "park_quality":
            scores.append(round(score, 4))
            continue

        # RTM integration
        rtm = (xw3 - woba) if not (math.isnan(xw3) or math.isnan(woba)) else 0.0
        combined = score * 0.75 + (rtm * 10) * 0.25
        if (score > 0 and rtm > 0) or (score < 0 and rtm < 0):
            combined *= 1.15
        score = round(combined, 4)

        # Amp cap
        score, _ = _amp_cap(score, raw_for_cap)

        scores.append(score)

    return pd.Series(scores, index=agg.index, name=f"luck_score_v5_{variant}")


# ---------------------------------------------------------------------------
# V6 scoring (Phase B: v5 × consistency multiplier)
# ---------------------------------------------------------------------------

VARIANCE_TIERS = [
    (8.0,  "Very Consistent", 1.10),
    (15.0, "Consistent",      1.00),
    (25.0, "Inconsistent",    0.80),
    (35.0, "Volatile",        0.60),
    (float("inf"), "Extreme", 0.40),
]

AGE_MODIFIERS = [
    (26, 0.40), (32, 1.00), (35, 1.20), (float("inf"), 1.40),
]

def _variance_tier(std):
    for upper, label, mult in VARIANCE_TIERS:
        if std < upper: return mult, label
    return 0.40, "Extreme"

def _age_mod(age):
    for upper, mod in AGE_MODIFIERS:
        if age < upper: return mod
    return 1.40

def _cons_mult(base_mult, age, wrc_plus):
    if base_mult >= 1.0:
        return round(base_mult, 4) if wrc_plus > 120 else 1.0
    penalty = (base_mult - 1.0) * _age_mod(age)
    return round(max(0.50, 1.0 + penalty), 4)


def compute_v6_luck(
    agg: pd.DataFrame,
    v5_scores: pd.Series,
    all_xwoba: pd.DataFrame,
    birth_years: dict,
    scoring_year: int,
) -> tuple:
    """
    Returns (v6_scores, consistency_df) where consistency_df has per-player metadata.

    For variance: uses full 2022-2024 window (production-like; slight look-ahead for
    2022/2023 scoring years — acknowledged in report).
    """
    # Build variance map from full 2022-2024 window
    full_window = all_xwoba[all_xwoba["pa"] >= 300].copy()
    full_window["pseudo_wrc"] = (full_window["xwoba"] / LEAGUE_AVG_XWOBA) * 100

    def _var_agg(grp):
        seasons = grp["year"].nunique()
        if seasons < 2:
            return pd.Series({"variance_std": float("nan"), "seasons": seasons,
                              "wrc_mean": grp["pseudo_wrc"].mean()})
        return pd.Series({"variance_std": grp["pseudo_wrc"].std(ddof=1), "seasons": seasons,
                          "wrc_mean": grp["pseudo_wrc"].mean()})

    var_df = full_window.groupby("player_id").apply(_var_agg).reset_index()
    var_map = {int(row["player_id"]): row for _, row in var_df.iterrows()}

    v6_scores = []
    cons_rows = []
    for batter_id, v5_score in v5_scores.items():
        age = scoring_year - birth_years.get(int(batter_id), 0) if birth_years.get(int(batter_id), 0) > 0 else 30.0

        var_rec = var_map.get(int(batter_id))
        if var_rec is None or pd.isna(var_rec["variance_std"]):
            tier_label = "Insufficient data"
            mult = 1.0
            std_val = float("nan")
            wrc_m = float("nan")
        else:
            std_val = float(var_rec["variance_std"])
            wrc_m = float(var_rec["wrc_mean"])
            base_mult, tier_label = _variance_tier(std_val)
            mult = _cons_mult(base_mult, age, wrc_m)

        v6 = round(float(v5_score) * mult, 4)
        v6_scores.append(v6)
        cons_rows.append({
            "batter": int(batter_id),
            "variance_std": round(std_val, 2) if not math.isnan(std_val) else float("nan"),
            "variance_tier": tier_label,
            "consistency_multiplier": mult,
            "wrc_plus_for_gate": round(wrc_m, 1) if not math.isnan(wrc_m) else float("nan"),
        })

    v6_series = pd.Series(v6_scores, index=v5_scores.index, name="luck_score_v6")
    return v6_series, pd.DataFrame(cons_rows).set_index("batter")


# ---------------------------------------------------------------------------
# V1 baseline
# ---------------------------------------------------------------------------

def compute_v1_luck(agg: pd.DataFrame) -> pd.Series:
    V1 = [
        ("BABIP",          0.300, -5.000),
        ("hr_fb_rate",     0.145, -0.040),
        ("hard_hit_rate",  0.390,  0.025),
        ("barrel_rate",    0.080,  0.030),
        ("z_contact_rate", 0.880, -0.010),
    ]
    score = pd.Series(0.0, index=agg.index)
    for col, avg, w in V1:
        if col in agg.columns:
            score += (agg[col].fillna(avg) - avg) * w
    return score.round(4).rename("luck_score_v1")


# ---------------------------------------------------------------------------
# Analysis helpers
# ---------------------------------------------------------------------------

def assign_verdict(score: float) -> str:
    if score > 0.12:  return "Buy low"
    if score > 0.05:  return "Slight buy"
    if score < -0.12: return "Sell high"
    if score < -0.05: return "Slight sell"
    return "Neutral"

def pearson(x, y):
    mask = x.notna() & y.notna()
    if mask.sum() < 5: return float("nan"), float("nan"), 0
    r, p = scipy_stats.pearsonr(x[mask], y[mask])
    return r, p, int(mask.sum())

def dir_accuracy(scores, deltas, threshold=0.05):
    mask = scores.notna() & deltas.notna() & (scores.abs() > threshold)
    n = int(mask.sum())
    if n == 0: return float("nan"), 0
    correct = ((scores[mask] > 0) & (deltas[mask] > 0)) | ((scores[mask] < 0) & (deltas[mask] < 0))
    return float(correct.mean()), n

def verdict_stats(scores, deltas):
    tiers = [
        ("Buy low",    lambda s: s > 0.12),
        ("Slight buy", lambda s: (s > 0.05) & (s <= 0.12)),
        ("Neutral",    lambda s: (s >= -0.05) & (s <= 0.05)),
        ("Slight sell",lambda s: (s >= -0.12) & (s < -0.05)),
        ("Sell high",  lambda s: s < -0.12),
    ]
    out = {}
    for label, fn in tiers:
        mask = fn(scores) & deltas.notna()
        n = int(mask.sum())
        if n == 0: continue
        sub_d = deltas[mask]
        if label in ("Buy low", "Slight buy"): n_cor = int((sub_d > 0).sum())
        elif label in ("Sell high", "Slight sell"): n_cor = int((sub_d < 0).sum())
        else: n_cor = None
        out[label] = {"n": n, "mean_delta": float(sub_d.mean()),
                      "n_correct": n_cor, "pct_correct": (n_cor/n) if n_cor is not None else None}
    return out

def rtm_accuracy(full_woba, outcome_woba, league_avg=LEAGUE_AVG_WOBA):
    mask = full_woba.notna() & outcome_woba.notna()
    n = int(mask.sum())
    if n == 0: return float("nan"), 0
    pred_dir = np.sign(league_avg - full_woba[mask])
    actual_dir = np.sign(outcome_woba[mask] - full_woba[mask])
    correct = (pred_dir == actual_dir) & (pred_dir != 0)
    valid = pred_dir != 0
    return float(correct.sum() / valid.sum()) if valid.sum() > 0 else float("nan"), n

def stars(p):
    if p < 0.001: return "***"
    if p < 0.01:  return "**"
    if p < 0.05:  return "*"
    if p < 0.10:  return "†"
    return ""

def pct(n, total): return f"{n}/{total} ({100*n/total:.0f}%)" if total else "—"

def add_names(df):
    ids = list(df.index.unique())
    try:
        lu = playerid_reverse_lookup(ids, key_type="mlbam")
        lu["name"] = lu["name_first"].str.capitalize() + " " + lu["name_last"].str.capitalize()
        id_map = {row["key_mlbam"]: row["name"] for _, row in lu.iterrows()}
    except Exception:
        id_map = {}
    df["name"] = df.index.map(lambda i: id_map.get(i, f"Player {i}"))
    cols = ["name"] + [c for c in df.columns if c != "name"]
    return df[cols]


# ---------------------------------------------------------------------------
# Build backtest dataset
# ---------------------------------------------------------------------------

def build_backtest() -> pd.DataFrame:
    print("\n" + "="*65)
    print(" BACKTEST V6 — Fetching data")
    print("="*65)

    fs_years = [2022, 2023, 2024, 2025]
    fs = fetch_full_season_stats(fs_years)
    fs["player_id"] = fs["player_id"].astype(int)

    # Birth years from career_stats.json
    birth_years = {}
    career_stats_path = os.path.join(DATA_DIR, "career_stats.json")
    if os.path.exists(career_stats_path):
        with open(career_stats_path) as f:
            cs = json.load(f)
        birth_years = {int(k): int(v.get("birth_year", 0)) for k, v in cs.items() if v.get("birth_year")}
    print(f"  Loaded {len(birth_years)} birth years from career_stats.json")

    all_rows = []

    for scoring_yr in SCORING_YEARS:
        outcome_yr = scoring_yr + 1
        print(f"\n{'='*65}")
        print(f" SCORING YEAR: {scoring_yr}  →  OUTCOME YEAR: {outcome_yr}")
        print("="*65)

        # Qualification filter
        sc_fs = fs[fs["year"] == scoring_yr][["player_id","pa","woba"]].rename(
            columns={"pa":"sc_pa","woba":"sc_woba"})
        oc_fs = fs[fs["year"] == outcome_yr][["player_id","pa","woba"]].rename(
            columns={"pa":"oc_pa","woba":"oc_woba"})
        qualified = sc_fs.merge(oc_fs, on="player_id", how="inner")
        qualified = qualified[(qualified["sc_pa"] >= MIN_SCORING_PA) & (qualified["oc_pa"] >= MIN_OUTCOME_PA)].copy()
        print(f"  Qualified players: {len(qualified)}")

        if len(qualified) == 0:
            print("  WARNING: No qualified players — skipping"); continue

        # April Statcast
        raw = fetch_april(scoring_yr)
        agg = aggregate_april(raw)
        agg = agg[agg.index.isin(qualified["player_id"])].copy()
        print(f"  After qualification filter: {len(agg)} players with April data")

        # Team map for park factors
        print(f"  Loading team map for park factors...")
        team_map = fetch_team_map(scoring_yr)

        # Prior-year xwOBA for quality gate + RTM (strict — no look-ahead)
        prior_years = fs[fs["year"] < scoring_yr]
        if prior_years.empty:
            # Fall back to same-year for 2022 (no prior data available)
            prior_years = fs[fs["year"] == scoring_yr]
            print(f"  NOTE: No prior xwOBA data for {scoring_yr}; using same-year as proxy for quality gate / RTM.")
        prior_xwoba_map = prior_years.groupby("player_id")["xwoba"].mean().to_dict()
        prior_xwoba_map = {int(k): float(v) for k, v in prior_xwoba_map.items()}

        # Scores
        print("  Computing v4, v5 variants, v6 luck scores...")
        v4  = compute_v4_luck(agg)
        v1  = compute_v1_luck(agg)
        v5_park      = compute_v5_luck(agg, team_map, prior_xwoba_map, birth_years, scoring_yr, variant="park_only")
        v5_pk_qual   = compute_v5_luck(agg, team_map, prior_xwoba_map, birth_years, scoring_yr, variant="park_quality")
        v5_full      = compute_v5_luck(agg, team_map, prior_xwoba_map, birth_years, scoring_yr, variant="full")
        v6_scores, cons_meta = compute_v6_luck(agg, v5_full, fs, birth_years, scoring_yr)

        # Merge all
        df = agg.copy()
        df["luck_score_v1"]          = v1
        df["luck_score_v4"]          = v4
        df["luck_score_v5_park"]     = v5_park
        df["luck_score_v5_pkq"]      = v5_pk_qual
        df["luck_score_v5"]          = v5_full
        df["luck_score_v6"]          = v6_scores

        # Consistency metadata
        df["variance_tier"]           = df.index.map(lambda i: cons_meta.loc[int(i), "variance_tier"] if int(i) in cons_meta.index else "Insufficient data")
        df["consistency_multiplier"]  = df.index.map(lambda i: cons_meta.loc[int(i), "consistency_multiplier"] if int(i) in cons_meta.index else 1.0)

        # Park factor flag
        df["park_factor"] = df.index.map(lambda i: PARK_FACTORS.get(team_map.get(int(i), ""), 1.0))
        df["non_neutral_park"] = df["park_factor"] != 1.0

        q_indexed = qualified.set_index("player_id")
        df["sc_woba"]     = df.index.map(q_indexed["sc_woba"])
        df["oc_woba"]     = df.index.map(q_indexed["oc_woba"])
        df["sc_pa"]       = df.index.map(q_indexed["sc_pa"])
        df["oc_pa"]       = df.index.map(q_indexed["oc_pa"])
        df["delta_woba"]  = (df["oc_woba"] - df["sc_woba"]).round(4)
        df["scoring_year"] = scoring_yr
        df["outcome_year"] = outcome_yr

        all_rows.append(df)
        print(f"  Built {len(df)} player-seasons for {scoring_yr}→{outcome_yr}")

    if not all_rows:
        sys.exit("ERROR: No player-seasons built.")

    combined = pd.concat(all_rows)
    combined.index.name = "batter"
    print(f"\nTotal player-seasons: {len(combined)}")
    print("  Adding player names...")
    combined = add_names(combined)
    return combined


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def md_table(headers, rows):
    sep = ["-"*max(len(h), 4) for h in headers]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(sep) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)


def generate_report(df: pd.DataFrame) -> str:
    from datetime import date

    n_total = len(df)
    yr_cnts = df["scoring_year"].value_counts().sort_index()

    # Core stats for all versions
    versions = ["v1", "v4", "v5_park", "v5_pkq", "v5", "v6"]
    stats = {}
    for v in versions:
        col = f"luck_score_{v}"
        if col not in df.columns: continue
        r, p, n   = pearson(df[col], df["delta_woba"])
        acc, acc_n = dir_accuracy(df[col], df["delta_woba"])
        vb        = verdict_stats(df[col], df["delta_woba"])
        bl_acc    = vb.get("Buy low", {}).get("pct_correct")
        sh_acc    = vb.get("Sell high", {}).get("pct_correct")
        stats[v]  = {"r": r, "p": p, "n": n, "acc": acc, "acc_n": acc_n,
                     "buy_low": bl_acc, "sell_high": sh_acc, "vb": vb}

    rtm_acc, rtm_n = rtm_accuracy(df["sc_woba"], df["oc_woba"])

    # ── Format comparison table ─────────────────────────────────────────────
    def _r(v): return f"{stats[v]['r']:+.4f}{stars(stats[v]['p'])}" if v in stats else "—"
    def _acc(v): return f"{stats[v]['acc']:.1%}" if v in stats and not math.isnan(stats[v]['acc']) else "—"
    def _bl(v): return f"{stats[v]['buy_low']:.1%}" if v in stats and stats[v]['buy_low'] is not None else "—"
    def _sh(v): return f"{stats[v]['sell_high']:.1%}" if v in stats and stats[v]['sell_high'] is not None else "—"
    def _n(v): return str(stats[v]['n']) if v in stats else "—"

    summary_table = md_table(
        ["Metric", "RTM Baseline", "v4", "v5 (Phase A)", "v6 (Phase B)"],
        [
            ["Correlation (r vs Δ wOBA)", "—",
             _r("v4"), _r("v5"), _r("v6")],
            ["Directional accuracy", f"{rtm_acc:.1%} (n={rtm_n})",
             _acc("v4"), _acc("v5"), _acc("v6")],
            ["Buy Low accuracy", "—", _bl("v4"), _bl("v5"), _bl("v6")],
            ["Sell High accuracy", "—", _sh("v4"), _sh("v5"), _sh("v6")],
            ["Sample size", str(rtm_n), _n("v4"), _n("v5"), _n("v6")],
        ]
    )

    # ── Phase A component breakdown ─────────────────────────────────────────
    def _delta_acc(va, vb_key):
        if va not in stats or vb_key not in stats: return "—"
        da = stats[va]["acc"]
        db = stats[vb_key]["acc"]
        if math.isnan(da) or math.isnan(db): return "—"
        return f"{db-da:+.1%}"

    component_table = md_table(
        ["Step", "Version", "Dir. Accuracy", "Δ vs previous", "Pearson r"],
        [
            ["v4 baseline",           "v4",      _acc("v4"),      "—",                    _r("v4")],
            ["+ Park factor",         "v4+park",  _acc("v5_park"), _delta_acc("v4","v5_park"), _r("v5_park")],
            ["+ wRC+ quality gate",   "v4+pk+q",  _acc("v5_pkq"),  _delta_acc("v5_park","v5_pkq"), _r("v5_pkq")],
            ["+ RTM + PT + amp cap",  "v5 (full)", _acc("v5"),     _delta_acc("v5_pkq","v5"),      _r("v5")],
            ["+ Consistency (Phase B)","v6",       _acc("v6"),     _delta_acc("v5","v6"),          _r("v6")],
        ]
    )

    # ── Consistency tier breakdown ───────────────────────────────────────────
    tier_counts = df["variance_tier"].value_counts()
    tier_rows = []
    for tier in ["Very Consistent","Consistent","Inconsistent","Volatile","Extreme","Insufficient data"]:
        n_t = int(tier_counts.get(tier, 0))
        if n_t == 0: continue
        sub = df[df["variance_tier"] == tier]
        r_t, _, _ = pearson(sub["luck_score_v5"], sub["delta_woba"]) if len(sub) >= 5 else (float("nan"), None, None)
        r6, _, _  = pearson(sub["luck_score_v6"], sub["delta_woba"]) if len(sub) >= 5 else (float("nan"), None, None)
        tier_rows.append([
            tier, n_t,
            f"{r_t:+.3f}" if not math.isnan(r_t) else "—",
            f"{r6:+.3f}" if not math.isnan(r6) else "—",
        ])

    # ── Park factor impact ───────────────────────────────────────────────────
    park_df = df[df["non_neutral_park"] == True]
    default_df = df[df["non_neutral_park"] == False]
    r_park_v4, _, _ = pearson(park_df["luck_score_v4"], park_df["delta_woba"])
    r_park_v5, _, _ = pearson(park_df["luck_score_v5"], park_df["delta_woba"])
    r_def_v4,  _, _ = pearson(default_df["luck_score_v4"], default_df["delta_woba"])
    r_def_v5,  _, _ = pearson(default_df["luck_score_v5"], default_df["delta_woba"])

    # ── Verdict breakdown v4/v5/v6 ───────────────────────────────────────────
    VORD = ["Buy low","Slight buy","Neutral","Slight sell","Sell high"]
    def _fmt_vb(v):
        rows = []
        for ver in VORD:
            if ver not in stats.get(v, {}).get("vb", {}): continue
            info = stats[v]["vb"][ver]
            dir_s = pct(info["n_correct"], info["n"]) if info["n_correct"] is not None else "N/A"
            rows.append([ver, info["n"], f"{info['mean_delta']:+.4f}", dir_s])
        return rows

    today = date.today().isoformat()
    lines = [
        f"# Fantasy Baseball Luck Model — Backtest Report v6",
        f"",
        f"**Generated:** {today}",
        f"**Models compared:** v4 (current baseline) · v5 (Phase A) · v6 (Phase B)",
        f"**Significance:** `***` p<0.001  `**` p<0.01  `*` p<0.05  `†` p<0.10  _(blank)_ ns",
        f"",
        f"---",
        f"",
        f"## 1. Backtest Design",
        f"",
        md_table(
            ["Parameter", "Value"],
            [
                ["Scoring years",          "2022, 2023, 2024"],
                ["Outcome years",          "2023, 2024, 2025"],
                ["Min PA (scoring year)",  f"{MIN_SCORING_PA} (full season)"],
                ["Min PA (outcome year)",  f"{MIN_OUTCOME_PA} (full season)"],
                ["Total player-seasons",   f"{n_total} ({'; '.join(f'{y}: {c}' for y, c in yr_cnts.items())})"],
                ["v4 model",               "BABIP + HR/FB + Z-contact + xwOBA gap + contextual modifiers"],
                ["v5 model (Phase A)",     "v4 + park factor adjustment + wRC+ quality gate + RTM + PT discount + amp cap"],
                ["v6 model (Phase B)",     "v5 × per-player consistency multiplier (variance-based)"],
            ]
        ),
        f"",
        f"**Prior-year xwOBA note:** For the quality gate and RTM integration, only full-season",
        f"xwOBA from years *prior* to the scoring year is used (strict no-look-ahead):",
        f"- Scoring 2022: same-year 2022 xwOBA used as proxy (no prior data available).",
        f"- Scoring 2023: 2022 full-season xwOBA.",
        f"- Scoring 2024: average of 2022–2023 full-season xwOBA.",
        f"",
        f"**Phase B variance note:** Consistency multipliers use the full 2022–2024 expected-stats",
        f"window (matching production behavior). This is slightly look-ahead for 2022/2023 scoring",
        f"years but gives Phase B a fair test with the same data it uses in practice.",
        f"",
        f"---",
        f"",
        f"## 2. Summary Comparison Table",
        f"",
        summary_table,
        f"",
        f"> **Methodology note:** This is a cross-season out-of-sample test (April luck score →",
        f"> following *full season* wOBA delta, 300/300 PA thresholds). This is strictly harder",
        f"> than the original v1 backtest (April → May-July intra-season, 50/100 PA), which",
        f"> showed r=0.506 and 71% accuracy. The cross-season window introduces macro factors",
        f"> (injuries, position changes, park moves) that no luck model can predict.",
        f"",
        f"---",
        f"",
        f"## 3. Phase A Component Breakdown",
        f"",
        f"Each component added cumulatively to v4 to show incremental accuracy impact:",
        f"",
        component_table,
        f"",
        f"**Park factor analysis — players on extreme-park teams vs neutral parks:**",
        f"",
        md_table(
            ["Group", "N", "v4 Pearson r", "v5 Pearson r", "Δ r"],
            [
                ["Extreme park teams (PF ≠ 1.0)", len(park_df),
                 f"{r_park_v4:+.3f}" if not math.isnan(r_park_v4) else "—",
                 f"{r_park_v5:+.3f}" if not math.isnan(r_park_v5) else "—",
                 f"{r_park_v5-r_park_v4:+.3f}" if not (math.isnan(r_park_v4) or math.isnan(r_park_v5)) else "—"],
                ["Neutral park teams (PF = 1.0)", len(default_df),
                 f"{r_def_v4:+.3f}" if not math.isnan(r_def_v4) else "—",
                 f"{r_def_v5:+.3f}" if not math.isnan(r_def_v5) else "—",
                 f"{r_def_v5-r_def_v4:+.3f}" if not (math.isnan(r_def_v4) or math.isnan(r_def_v5)) else "—"],
            ]
        ),
        f"",
        f"---",
        f"",
        f"## 4. Phase B Component Breakdown",
        f"",
        f"**Consistency tier distribution across all player-seasons:**",
        f"",
        md_table(
            ["Variance Tier", "N (player-seasons)", "v5 Pearson r", "v6 Pearson r"],
            tier_rows if tier_rows else [["No data", "—", "—", "—"]]
        ),
        f"",
        f"**Interpretation:** Tiers where v6 r > v5 r show the consistency multiplier is",
        f"adding genuine signal. If v6 ≈ v5 overall, Phase B is not materially impacting",
        f"the cross-season test — consistent with the expectation that ~58% of players",
        f"receive multiplier=1.00 due to insufficient variance history.",
        f"",
        f"---",
        f"",
        f"## 5. Verdict Bucket Analysis",
        f"",
        f"### v4",
        f"",
        md_table(["Verdict","N","Mean Δ wOBA","% Correct Direction"], _fmt_vb("v4")),
        f"",
        f"### v5 (Phase A)",
        f"",
        md_table(["Verdict","N","Mean Δ wOBA","% Correct Direction"], _fmt_vb("v5")),
        f"",
        f"### v6 (Phase B)",
        f"",
        md_table(["Verdict","N","Mean Δ wOBA","% Correct Direction"], _fmt_vb("v6")),
        f"",
        f"---",
        f"",
        f"## 6. RTM Baseline Comparison",
        f"",
        md_table(
            ["Model", "Directional Accuracy", "Pearson r", "Notes"],
            [
                ["RTM baseline (Steamer proxy)", f"{rtm_acc:.1%} (n={rtm_n})", "—",
                 "Pure regression to mean"],
                ["v4 (current)",    _acc("v4"),  _r("v4"), "Phase 0 baseline"],
                ["v5 (Phase A)",    _acc("v5"),  _r("v5"), "Park + quality + RTM + PT + amp"],
                ["v6 (Phase B)",    _acc("v6"),  _r("v6"), "v5 + consistency multiplier"],
                ["Random guess",    "50.0%",     "—",      "Theoretical floor"],
            ]
        ),
        f"",
        f"---",
        f"",
        f"## 7. Top Retrospective Calls (v6)",
        f"",
        f"### Top 10 Buy-Low Calls",
        f"",
    ]

    top_buy = (df[df["luck_score_v6"] > 0.12]
               .nlargest(10, "luck_score_v6")[["name","scoring_year","luck_score_v4","luck_score_v5","luck_score_v6","xwOBA","BABIP","delta_woba"]])
    if len(top_buy) > 0:
        rows_b = []
        for _, r in top_buy.iterrows():
            rows_b.append([r["name"], int(r["scoring_year"]),
                           f"{r['luck_score_v4']:+.3f}", f"{r['luck_score_v5']:+.3f}", f"{r['luck_score_v6']:+.3f}",
                           f"{r.get('xwOBA',float('nan')):.3f}" if not math.isnan(r.get('xwOBA',float('nan'))) else "—",
                           f"{r.get('BABIP',float('nan')):.3f}" if not math.isnan(r.get('BABIP',float('nan'))) else "—",
                           f"{r['delta_woba']:+.3f}", "✓" if r["delta_woba"] > 0 else "✗"])
        lines.append(md_table(["Player","Year","v4 Score","v5 Score","v6 Score","April xwOBA","April BABIP","Δ wOBA","Correct?"], rows_b))
    else:
        lines.append("_No strong buy-low calls in dataset._")

    lines += [f"", f"### Top 10 Sell-High Calls", f""]
    top_sell = (df[df["luck_score_v6"] < -0.12]
                .nsmallest(10, "luck_score_v6")[["name","scoring_year","luck_score_v4","luck_score_v5","luck_score_v6","xwOBA","BABIP","delta_woba"]])
    if len(top_sell) > 0:
        rows_s = []
        for _, r in top_sell.iterrows():
            rows_s.append([r["name"], int(r["scoring_year"]),
                           f"{r['luck_score_v4']:+.3f}", f"{r['luck_score_v5']:+.3f}", f"{r['luck_score_v6']:+.3f}",
                           f"{r.get('xwOBA',float('nan')):.3f}" if not math.isnan(r.get('xwOBA',float('nan'))) else "—",
                           f"{r.get('BABIP',float('nan')):.3f}" if not math.isnan(r.get('BABIP',float('nan'))) else "—",
                           f"{r['delta_woba']:+.3f}", "✓" if r["delta_woba"] < 0 else "✗"])
        lines.append(md_table(["Player","Year","v4 Score","v5 Score","v6 Score","April xwOBA","April BABIP","Δ wOBA","Correct?"], rows_s))
    else:
        lines.append("_No strong sell-high calls in dataset._")

    lines += [
        f"",
        f"---",
        f"",
        f"## 8. Key Findings",
        f"",
        f"**Overall model trajectory (v4 → v5 → v6):**",
        f"",
        f"| Version | r | Dir. Accuracy | Buy Low | Sell High |",
        f"| --- | --- | --- | --- | --- |",
        f"| v4 | {_r('v4')} | {_acc('v4')} | {_bl('v4')} | {_sh('v4')} |",
        f"| v5 (Phase A) | {_r('v5')} | {_acc('v5')} | {_bl('v5')} | {_sh('v5')} |",
        f"| v6 (Phase B) | {_r('v6')} | {_acc('v6')} | {_bl('v6')} | {_sh('v6')} |",
        f"",
        f"**Phase A component impact (incremental accuracy):**",
        f"",
        f"- Park factor adjustment: {_delta_acc('v4','v5_park')}",
        f"- wRC+ quality gate: {_delta_acc('v5_park','v5_pkq')}",
        f"- RTM + PT discount + amp cap: {_delta_acc('v5_pkq','v5')}",
        f"- All Phase A combined (v4→v5): {_delta_acc('v4','v5')}",
        f"",
        f"**Phase B impact (v5→v6):** {_delta_acc('v5','v6')} directional accuracy",
        f"",
        f"---",
        f"",
        f"*Report generated by `backtest_v6.py` · Fantasy Baseball Statcast Pipeline*",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    write_mode = "--write" in sys.argv

    print("Fantasy Baseball Luck Model — Backtest v6")
    print(f"Scoring years: {SCORING_YEARS} → Outcome years: {[y+1 for y in SCORING_YEARS]}")
    print(f"Qualification: ≥{MIN_SCORING_PA} PA scoring year, ≥{MIN_OUTCOME_PA} PA outcome year")

    df = build_backtest()

    # Terminal summary
    print(f"\n{'='*65}")
    print(" BACKTEST V6 — RESULTS SUMMARY")
    print("="*65)

    rtm_acc, rtm_n = rtm_accuracy(df["sc_woba"], df["oc_woba"])
    print(f"\n  Player-seasons: {len(df)}")
    print(f"  By year: {df['scoring_year'].value_counts().sort_index().to_dict()}")

    for label, col in [("v4", "luck_score_v4"), ("v5 (Phase A)", "luck_score_v5"), ("v6 (Phase B)", "luck_score_v6")]:
        if col not in df.columns: continue
        r, p, n = pearson(df[col], df["delta_woba"])
        acc, acc_n = dir_accuracy(df[col], df["delta_woba"])
        print(f"\n  [{label}]")
        print(f"    Pearson r:  {r:+.4f}  p={p:.4f}  {stars(p) or 'ns'}")
        print(f"    Dir acc:    {acc:.1%}  (n={acc_n})")
        vb = verdict_stats(df[col], df["delta_woba"])
        for v, info in vb.items():
            nc = pct(info["n_correct"], info["n"]) if info["n_correct"] is not None else "N/A"
            print(f"    {v:<14} n={info['n']:>3}  mean Δ={info['mean_delta']:+.4f}  correct: {nc}")

    print(f"\n  RTM baseline: {rtm_acc:.1%}  (n={rtm_n})")

    # Component breakdown
    print(f"\n  === Phase A Component Breakdown ===")
    v4_acc, _ = dir_accuracy(df["luck_score_v4"], df["delta_woba"])
    vp_acc, _ = dir_accuracy(df["luck_score_v5_park"], df["delta_woba"])
    vq_acc, _ = dir_accuracy(df["luck_score_v5_pkq"], df["delta_woba"])
    v5_acc, _ = dir_accuracy(df["luck_score_v5"], df["delta_woba"])
    v6_acc, _ = dir_accuracy(df["luck_score_v6"], df["delta_woba"])
    print(f"    v4 baseline:              {v4_acc:.1%}")
    print(f"    + Park factor:            {vp_acc:.1%}  (Δ {vp_acc-v4_acc:+.1%})")
    print(f"    + Quality gate:           {vq_acc:.1%}  (Δ {vq_acc-vp_acc:+.1%})")
    print(f"    + RTM + PT + amp cap:     {v5_acc:.1%}  (Δ {v5_acc-vq_acc:+.1%})")
    print(f"    + Consistency (Phase B):  {v6_acc:.1%}  (Δ {v6_acc-v5_acc:+.1%})")

    # Consistency tier
    print(f"\n  === Phase B Variance Tier Distribution ===")
    tc = df["variance_tier"].value_counts()
    for tier in ["Very Consistent","Consistent","Inconsistent","Volatile","Extreme","Insufficient data"]:
        n_t = int(tc.get(tier, 0))
        if n_t > 0:
            sub = df[df["variance_tier"] == tier]
            r5, _, _ = pearson(sub["luck_score_v5"], sub["delta_woba"])
            r6, _, _ = pearson(sub["luck_score_v6"], sub["delta_woba"])
            r5_str = f"{r5:+.3f}" if not math.isnan(r5) else "  n/a"
            r6_str = f"{r6:+.3f}" if not math.isnan(r6) else "  n/a"
            print(f"    {tier:<22} n={n_t:>4}  v5 r={r5_str}  v6 r={r6_str}  mult_mean={sub['consistency_multiplier'].mean():.3f}")

    # Generate and save report
    print(f"\nGenerating report...")
    report_md = generate_report(df)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report_md)
    print(f"Report written to: {REPORT_PATH}")

    if write_mode:
        save_cols = ["name", "scoring_year", "outcome_year",
                     "luck_score_v1", "luck_score_v4", "luck_score_v5_park", "luck_score_v5_pkq",
                     "luck_score_v5", "luck_score_v6",
                     "variance_tier", "consistency_multiplier", "park_factor",
                     "BABIP", "hr_fb_rate", "xwOBA", "wOBA", "xwOBA_gap" if "xwOBA_gap" in df.columns else None,
                     "sc_woba", "oc_woba", "sc_pa", "oc_pa", "delta_woba"]
        save_cols = [c for c in save_cols if c and c in df.columns]
        df.reset_index()[["batter"] + save_cols].to_csv(RAW_OUTPUT, index=False)
        print(f"Raw data written to: {RAW_OUTPUT}")
    else:
        print(f"\n[dry run] Use --write to save {RAW_OUTPUT}")


if __name__ == "__main__":
    main()
