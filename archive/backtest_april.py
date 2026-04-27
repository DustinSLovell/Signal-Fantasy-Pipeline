"""
backtest_april.py

Pulls 2023 and 2024 Statcast data to backtest the fantasy baseball luck model.

Steps:
  1. Pull April Statcast data for 2023 and 2024 (Opening Day through April 30)
  2. Aggregate per-player April metrics: BABIP, hard-hit rate, barrel rate,
     Z-contact rate, HR/FB rate, BA, wOBA, xBA, xwOBA
  3. Compute April luck scores using the current model weights
  4. Pull May-July Statcast data for those same years
  5. Aggregate May-July performance: BABIP, BA, wOBA, HR rate
  6. Merge, filter to qualified players (>= 50 April PA, >= 100 May-July PA)
  7. Compute performance deltas (May-July minus April)
  8. Save raw backtest data to backtest_raw.csv

Usage:
    python backtest_april.py

Intermediate Statcast downloads are cached in backtest_cache/
to avoid re-downloading on subsequent runs.
"""

import json
import os
import time
import urllib.request

import numpy as np
import pandas as pd

try:
    import pybaseball
    from pybaseball import statcast, playerid_reverse_lookup
    pybaseball.cache.enable()
except ImportError:
    raise SystemExit("pybaseball not found. Run: pip install pybaseball pandas scipy")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR   = os.path.join(BASE_DIR, "backtest_cache")
OUTPUT_PATH = os.path.join(BASE_DIR, "backtest_raw.csv")

os.makedirs(CACHE_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Date ranges
# ---------------------------------------------------------------------------
YEARS = [2023, 2024]

APRIL_DATES = {
    2023: ("2023-03-30", "2023-04-30"),  # Opening Day 2023: March 30
    2024: ("2024-03-20", "2024-04-30"),  # Opening Day 2024: March 20
}

MAY_JULY_DATES = {
    2023: ("2023-05-01", "2023-07-31"),
    2024: ("2024-05-01", "2024-07-31"),
}

MIN_APRIL_PA   = 50
MIN_MAY_JULY_PA = 100

# ---------------------------------------------------------------------------
# Current model weights  (col, league_avg, weight)
# Positive luck_score = unlucky = buy low
# ---------------------------------------------------------------------------
COMPONENTS = [
    ("BABIP",          0.300,  -5.000),
    ("hr_fb_rate",     0.145,  -0.040),
    ("hard_hit_rate",  0.390,   0.025),
    ("barrel_rate",    0.080,   0.030),
    ("z_contact_rate", 0.880,  -0.010),
]

# ---------------------------------------------------------------------------
# Event / description sets
# ---------------------------------------------------------------------------
CONTACT_DESCS    = {"hit_into_play", "foul", "foul_tip", "foul_bunt", "bunt_foul_tip"}
SWING_MISS_DESCS = {"swinging_strike", "swinging_strike_blocked", "missed_bunt"}
SWING_DESCS      = CONTACT_DESCS | SWING_MISS_DESCS

BIP_EVENTS = {
    "single", "double", "triple",
    "field_out", "force_out", "grounded_into_double_play",
    "double_play", "fielders_choice", "fielders_choice_out",
    "field_error", "sac_fly", "sac_fly_double_play",
}
HIT_BIP_EVENTS = {"single", "double", "triple"}
HIT_EVENTS     = {"single", "double", "triple", "home_run"}
NON_PA_EVENTS  = {"truncated_pa"}
NON_AB_EVENTS  = {
    "walk", "hit_by_pitch", "sac_fly", "sac_bunt",
    "catcher_interf", "sac_fly_double_play",
}
# True-outcome events where xwOBA from Statcast is not applicable
TRUE_OUTCOME_EVENTS = {
    "home_run", "strikeout", "strikeout_double_play",
    "walk", "intent_walk", "hit_by_pitch",
}

# Statcast columns we need (keeps memory usage down)
KEEP_COLS = [
    "game_date", "batter",
    "events", "description", "bb_type",
    "launch_speed", "launch_angle", "launch_speed_angle",
    "zone",
    "woba_value", "babip_value",
    "estimated_ba_using_speedangle",
    "estimated_woba_using_speedangle",
]


# ---------------------------------------------------------------------------
# Data fetching with file-based caching
# ---------------------------------------------------------------------------

def cache_path(year: int, period: str) -> str:
    return os.path.join(CACHE_DIR, f"statcast_{year}_{period}.csv")


def fetch_statcast(start_dt: str, end_dt: str, year: int, period: str) -> pd.DataFrame:
    """Pull Statcast data, using a local cache file to skip re-downloads."""
    path = cache_path(year, period)
    if os.path.exists(path):
        print(f"  Loading cached {year} {period} data from {path} ...")
        df = pd.read_csv(path, low_memory=False)
        print(f"    -> {len(df):,} rows, {df['batter'].nunique():,} unique batters")
        return df

    print(f"  Downloading {year} {period} Statcast ({start_dt} to {end_dt}) ...")
    t0 = time.time()
    df = statcast(start_dt=start_dt, end_dt=end_dt)
    elapsed = time.time() - t0
    print(f"    -> {len(df):,} rows, {df['batter'].nunique():,} unique batters ({elapsed:.0f}s)")

    # Keep only needed columns (gracefully handle missing ones)
    cols = [c for c in KEEP_COLS if c in df.columns]
    df = df[cols].copy()

    df.to_csv(path, index=False)
    print(f"    Cached to {path}")
    return df


# ---------------------------------------------------------------------------
# Metric computation helpers (vectorized)
# ---------------------------------------------------------------------------

def pa_series(df: pd.DataFrame) -> pd.Series:
    mask = df["events"].notna() & ~df["events"].isin(NON_PA_EVENTS)
    return df[mask].groupby("batter").size().rename("PA")


def babip_series(df: pd.DataFrame) -> pd.Series:
    bip = df[df["events"].isin(BIP_EVENTS | HIT_BIP_EVENTS)].copy()
    bip["is_hit"] = bip["events"].isin(HIT_BIP_EVENTS)
    g = bip.groupby("batter")["is_hit"].agg(["sum", "count"])
    return (g["sum"] / g["count"].replace(0, np.nan)).rename("BABIP")


def hard_hit_series(df: pd.DataFrame) -> pd.Series:
    bbe = df[df["launch_speed"].notna()].copy()
    bbe["hard"] = bbe["launch_speed"] >= 95
    g = bbe.groupby("batter")["hard"].agg(["sum", "count"])
    return (g["sum"] / g["count"].replace(0, np.nan)).rename("hard_hit_rate")


def barrel_series(df: pd.DataFrame) -> pd.Series:
    bbe = df[df["launch_speed"].notna()].copy()
    bbe["is_barrel"] = bbe["launch_speed_angle"] == 6
    g = bbe.groupby("batter")["is_barrel"].agg(["sum", "count"])
    return (g["sum"] / g["count"].replace(0, np.nan)).rename("barrel_rate")


def z_contact_series(df: pd.DataFrame) -> pd.Series:
    swings = df[
        df["zone"].between(1, 9) & df["description"].isin(SWING_DESCS)
    ].copy()
    swings["is_contact"] = swings["description"].isin(CONTACT_DESCS)
    g = swings.groupby("batter")["is_contact"].agg(["sum", "count"])
    return (g["sum"] / g["count"].replace(0, np.nan)).rename("z_contact_rate")


def hr_fb_series(df: pd.DataFrame) -> pd.Series:
    pa = df[df["events"].notna()].copy()
    pa["is_hr"] = pa["events"] == "home_run"
    pa["is_fb"] = pa["bb_type"] == "fly_ball"
    g = pa.groupby("batter")[["is_hr", "is_fb"]].sum()
    return (g["is_hr"] / g["is_fb"].replace(0, np.nan)).rename("hr_fb_rate")


def ba_series(df: pd.DataFrame) -> pd.Series:
    pa = df[df["events"].notna() & ~df["events"].isin(NON_PA_EVENTS)].copy()
    pa["is_hit"] = pa["events"].isin(HIT_EVENTS)
    pa["is_ab"]  = ~pa["events"].isin(NON_AB_EVENTS | NON_PA_EVENTS)
    g = pa.groupby("batter")[["is_hit", "is_ab"]].sum()
    return (g["is_hit"] / g["is_ab"].replace(0, np.nan)).rename("BA")


def woba_series(df: pd.DataFrame) -> pd.Series:
    pa = df[df["events"].notna() & ~df["events"].isin(NON_PA_EVENTS)].copy()
    g = pa.groupby("batter").agg(woba_sum=("woba_value", "sum"), pa_count=("events", "count"))
    return (g["woba_sum"] / g["pa_count"].replace(0, np.nan)).rename("wOBA")


def hr_rate_series(df: pd.DataFrame) -> pd.Series:
    pa = df[df["events"].notna() & ~df["events"].isin(NON_PA_EVENTS)].copy()
    pa["is_hr"] = pa["events"] == "home_run"
    g = pa.groupby("batter")["is_hr"].agg(["sum", "count"])
    return (g["sum"] / g["count"].replace(0, np.nan)).rename("HR_rate")


def xba_series(df: pd.DataFrame) -> pd.Series:
    """Mean xBA on batted-ball events where Statcast provides an estimate."""
    if "estimated_ba_using_speedangle" not in df.columns:
        return pd.Series(dtype=float, name="xBA")
    bbe = df[df["estimated_ba_using_speedangle"].notna()]
    return bbe.groupby("batter")["estimated_ba_using_speedangle"].mean().rename("xBA")


def xwoba_series(df: pd.DataFrame) -> pd.Series:
    """
    Mean xwOBA per PA:
      - BIP (non-HR): use estimated_woba_using_speedangle
      - HR, K, BB, HBP, or where estimate is null: use actual woba_value
    """
    if "estimated_woba_using_speedangle" not in df.columns:
        return woba_series(df).rename("xwOBA")

    pa = df[df["events"].notna() & ~df["events"].isin(NON_PA_EVENTS)].copy()
    pa["xw"] = pa["estimated_woba_using_speedangle"]
    # Fall back to actual woba_value where xwOBA is unavailable or for true outcomes
    fallback = pa["xw"].isna() | pa["events"].isin(TRUE_OUTCOME_EVENTS)
    pa.loc[fallback, "xw"] = pa.loc[fallback, "woba_value"]
    g = pa.groupby("batter").agg(xw_sum=("xw", "sum"), pa_count=("events", "count"))
    return (g["xw_sum"] / g["pa_count"].replace(0, np.nan)).rename("xwOBA")


# ---------------------------------------------------------------------------
# Full aggregation
# ---------------------------------------------------------------------------

def aggregate_april(df: pd.DataFrame) -> pd.DataFrame:
    """All April metrics: contact quality + outcomes + estimators."""
    parts = [
        pa_series(df),
        babip_series(df),
        hard_hit_series(df),
        barrel_series(df),
        z_contact_series(df),
        hr_fb_series(df),
        ba_series(df),
        woba_series(df),
        hr_rate_series(df),
        xba_series(df),
        xwoba_series(df),
    ]
    return pd.concat(parts, axis=1)


def aggregate_may_july(df: pd.DataFrame) -> pd.DataFrame:
    """May-July outcome metrics used as validation targets."""
    parts = [
        pa_series(df),
        babip_series(df),
        ba_series(df),
        woba_series(df),
        hr_rate_series(df),
    ]
    return pd.concat(parts, axis=1)


# ---------------------------------------------------------------------------
# Luck score
# ---------------------------------------------------------------------------

def compute_luck_scores(agg: pd.DataFrame) -> pd.DataFrame:
    score = pd.Series(0.0, index=agg.index)
    for col, avg, weight in COMPONENTS:
        if col in agg.columns:
            score += (agg[col] - avg) * weight
    agg["luck_score"] = score.round(4)
    agg["verdict"]    = agg["luck_score"].map(_verdict)
    return agg


def _verdict(score: float) -> str:
    if score > 0.12:
        return "Buy low"
    if score > 0.05:
        return "Slight buy"
    if score < -0.12:
        return "Sell high"
    if score < -0.05:
        return "Slight sell"
    return "Neutral"


# ---------------------------------------------------------------------------
# Player name lookup
# ---------------------------------------------------------------------------

def _mlb_api_name(mlbam_id: int) -> str | None:
    try:
        url = f"https://statsapi.mlb.com/api/v1/people/{mlbam_id}"
        with urllib.request.urlopen(url, timeout=5) as r:
            data = json.loads(r.read())
        return data["people"][0]["fullName"]
    except Exception:
        return None


def add_names(df: pd.DataFrame) -> pd.DataFrame:
    """Two-tier name lookup: Chadwick Bureau → MLB Stats API fallback."""
    ids = df.index.tolist()

    try:
        lookup = playerid_reverse_lookup(ids, key_type="mlbam")
        lookup["name"] = (
            lookup["name_first"].str.capitalize()
            + " "
            + lookup["name_last"].str.capitalize()
        )
        id_map = lookup[["key_mlbam", "name"]].rename(columns={"key_mlbam": "batter"})
    except Exception as exc:
        print(f"  Chadwick Bureau lookup failed ({exc}), falling back to MLB API for all IDs")
        id_map = pd.DataFrame(columns=["batter", "name"])

    found   = set(id_map["batter"].tolist())
    missing = [pid for pid in ids if pid not in found]
    if missing:
        print(f"  {len(missing)} ID(s) not in Chadwick Bureau — querying MLB Stats API ...")
        rows = []
        for pid in missing:
            name = _mlb_api_name(pid)
            rows.append({"batter": pid, "name": name or f"Unknown ({pid})"})
        id_map = pd.concat([id_map, pd.DataFrame(rows)], ignore_index=True)

    out = df.reset_index().merge(id_map, on="batter", how="left").set_index("batter")
    cols = ["name"] + [c for c in out.columns if c != "name"]
    return out[cols]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def process_year(year: int) -> pd.DataFrame:
    print(f"\n{'='*60}")
    print(f"  Year: {year}")
    print("="*60)

    # ── April ────────────────────────────────────────────────────────────────
    apr_start, apr_end = APRIL_DATES[year]
    apr_raw = fetch_statcast(apr_start, apr_end, year, "april")

    print(f"  Aggregating April metrics ...")
    apr_agg = aggregate_april(apr_raw)
    before = len(apr_agg)
    apr_agg = apr_agg[apr_agg["PA"] >= MIN_APRIL_PA].copy()
    print(f"    {before} batters total -> {len(apr_agg)} with >= {MIN_APRIL_PA} April PA")

    apr_agg = compute_luck_scores(apr_agg)

    # ── May-July ─────────────────────────────────────────────────────────────
    mj_start, mj_end = MAY_JULY_DATES[year]
    mj_raw = fetch_statcast(mj_start, mj_end, year, "may_july")

    print(f"  Aggregating May-July metrics ...")
    mj_agg = aggregate_may_july(mj_raw)
    # Only keep players who had April data
    mj_agg = mj_agg[mj_agg.index.isin(apr_agg.index)].copy()
    mj_agg = mj_agg[mj_agg["PA"] >= MIN_MAY_JULY_PA].copy()
    print(f"    {mj_agg.shape[0]} batters with >= {MIN_MAY_JULY_PA} May-July PA")

    # ── Merge ─────────────────────────────────────────────────────────────────
    apr_renamed = apr_agg.add_prefix("apr_").rename(columns={
        "apr_luck_score": "luck_score",
        "apr_verdict":    "verdict",
    })
    mj_renamed = mj_agg.add_prefix("mj_")

    merged = apr_renamed.join(mj_renamed, how="inner")
    merged["year"] = year

    n = len(merged)
    print(f"  {n} players qualified (>= {MIN_APRIL_PA} Apr PA, >= {MIN_MAY_JULY_PA} May-Jul PA)")

    # ── Performance deltas ────────────────────────────────────────────────────
    merged["delta_BABIP"]   = (merged["mj_BABIP"]   - merged["apr_BABIP"]).round(4)
    merged["delta_BA"]      = (merged["mj_BA"]       - merged["apr_BA"]).round(4)
    merged["delta_wOBA"]    = (merged["mj_wOBA"]     - merged["apr_wOBA"]).round(4)
    merged["delta_HR_rate"] = (merged["mj_HR_rate"]  - merged["apr_HR_rate"]).round(4)

    # xwOBA / xBA gaps (positive = player underperformed their contact quality = unlucky)
    if "apr_xwOBA" in merged.columns and "apr_wOBA" in merged.columns:
        merged["xwOBA_gap"] = (merged["apr_xwOBA"] - merged["apr_wOBA"]).round(4)
    if "apr_xBA" in merged.columns and "apr_BA" in merged.columns:
        merged["xBA_gap"] = (merged["apr_xBA"] - merged["apr_BA"]).round(4)

    return merged


def main():
    print("Fantasy Baseball Luck Model — Backtesting Engine")
    print("Periods: April vs May-July for 2023 and 2024")
    print(f"Qualification: >= {MIN_APRIL_PA} April PA, >= {MIN_MAY_JULY_PA} May-July PA")

    all_years = []
    for year in YEARS:
        df = process_year(year)
        all_years.append(df)

    combined = pd.concat(all_years)

    print(f"\nLooking up player names for {len(combined)} player-seasons ...")
    combined = add_names(combined)

    # Round rate columns for readability
    rate_cols = [c for c in combined.columns
                 if any(c.startswith(p) for p in ["apr_", "mj_", "delta_", "xwOBA", "xBA"])]
    for col in rate_cols:
        if combined[col].dtype == float:
            combined[col] = combined[col].round(4)

    combined.to_csv(OUTPUT_PATH)
    print(f"\nSaved {len(combined)} player-seasons to {OUTPUT_PATH}")

    # Quick summary
    for year in YEARS:
        sub = combined[combined["year"] == year]
        print(f"\n{year}: {len(sub)} qualified players")
        print(f"  Verdict breakdown: {sub['verdict'].value_counts().to_dict()}")

    print("\nSample output (first 10 rows):")
    display_cols = [
        "name", "year", "apr_PA", "mj_PA",
        "luck_score", "verdict",
        "apr_BABIP", "mj_BABIP", "delta_BABIP",
        "apr_wOBA",  "mj_wOBA",  "delta_wOBA",
    ]
    avail = [c for c in display_cols if c in combined.columns]
    print(combined[avail].head(10).to_string())


if __name__ == "__main__":
    main()
