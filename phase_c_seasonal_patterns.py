"""
phase_c_seasonal_patterns.py — Phase C Seasonal Pattern Detection

Detects three seasonal patterns per player across 2022-2024:

  Pattern 1 — Slow Starter:
    April wOBA lower than May-July wOBA by 20+ points in 2+ of 3 years

  Pattern 2 — Second Half Fader:
    May-July wOBA higher than Aug-Sep wOBA by 20+ points in 2+ of 3 years

  Pattern 3 — Summer Performer:
    Aug-Sep wOBA higher than April wOBA by 25+ points in 2+ of 3 years

Minimum 60 PA per period per year to qualify that year.
Player must have qualifying data in 2+ of 3 years for any pattern to fire.

Output: data/seasonal_patterns.json
"""

import json
import os
import sys

import numpy as np
import pandas as pd
from pathlib import Path

BASE_DIR  = Path(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = BASE_DIR / "backtest_cache"
DATA_DIR  = BASE_DIR / "data"
OUT_PATH  = DATA_DIR / "seasonal_patterns.json"

# ------------------------------------------------------------------
# Thresholds
# ------------------------------------------------------------------
MIN_PA               = 60
MIN_YEARS            = 2
SLOW_STARTER_DELTA   = 0.020   # may_july - april >= 0.020
FADER_DELTA          = 0.020   # may_july - aug_sep >= 0.020
SUMMER_DELTA         = 0.025   # aug_sep  - april  >= 0.025

# ------------------------------------------------------------------
# File manifest
# ------------------------------------------------------------------
YEARS = [2022, 2023, 2024]

APRIL_FILES = {
    2022: CACHE_DIR / "v4_april_2022.csv",
    2023: CACHE_DIR / "v4_april_2023.csv",
    2024: CACHE_DIR / "v4_april_2024.csv",
}
MAY_JULY_FILES = {
    2022: CACHE_DIR / "statcast_2022_may_july.csv",
    2023: CACHE_DIR / "statcast_2023_may_july.csv",
    2024: CACHE_DIR / "statcast_2024_may_july.csv",
}
AUG_SEP_FILES = {
    2022: CACHE_DIR / "statcast_2022_aug_sep.csv",
    2023: CACHE_DIR / "statcast_2023_aug_sep.csv",
    2024: CACHE_DIR / "statcast_2024_aug_sep.csv",
}

NON_PA_EVENTS = {"truncated_pa"}


# ------------------------------------------------------------------
# Aggregation
# ------------------------------------------------------------------

def agg_woba(path: Path, label: str) -> pd.DataFrame:
    """
    Load pitch-level CSV, filter to PA-ending rows, aggregate per batter.
    Returns: batter, pa, woba
    """
    df = pd.read_csv(path, usecols=["batter", "events", "woba_value"])
    pa_rows = df[df["events"].notna() & ~df["events"].isin(NON_PA_EVENTS)].copy()
    agg = pa_rows.groupby("batter").agg(
        pa=("woba_value", "count"),
        woba_sum=("woba_value", "sum"),
    ).reset_index()
    agg["woba"] = agg["woba_sum"] / agg["pa"]
    n_qual = (agg["pa"] >= MIN_PA).sum()
    print(f"    {label}: {len(agg):,} batters total, {n_qual:,} with >= {MIN_PA} PA")
    return agg[["batter", "pa", "woba"]]


def load_all_periods() -> dict:
    """
    Returns nested dict: period -> year -> DataFrame(batter, pa, woba)
    """
    print("Loading April data...")
    april = {y: agg_woba(APRIL_FILES[y], f"April {y}") for y in YEARS}

    print("Loading May-July data...")
    may_july = {y: agg_woba(MAY_JULY_FILES[y], f"May-Jul {y}") for y in YEARS}

    print("Loading Aug-Sep data...")
    aug_sep = {y: agg_woba(AUG_SEP_FILES[y], f"Aug-Sep {y}") for y in YEARS}

    return {"april": april, "may_july": may_july, "aug_sep": aug_sep}


# ------------------------------------------------------------------
# Pattern detection
# ------------------------------------------------------------------

def detect_patterns(periods: dict) -> pd.DataFrame:
    """
    For each player, count years each pattern fires, then classify.
    A pattern fires in a given year if:
      - Both required periods have >= MIN_PA
      - The wOBA delta meets the threshold
    A pattern is classified True if it fires in >= MIN_YEARS years.
    """
    # Collect all unique batters across all files
    all_batters = set()
    for period in periods.values():
        for df in period.values():
            all_batters.update(df["batter"].tolist())
    print(f"\nTotal unique batters across all periods/years: {len(all_batters):,}")

    rows = []
    for batter in all_batters:
        slow_fires   = 0   # years where may_july - april >= SLOW_STARTER_DELTA
        fader_fires  = 0   # years where may_july - aug_sep >= FADER_DELTA
        summer_fires = 0   # years where aug_sep  - april  >= SUMMER_DELTA

        slow_eligible   = 0   # years with qualifying PA in both periods
        fader_eligible  = 0
        summer_eligible = 0

        april_wobas  = []
        mj_wobas     = []
        as_wobas     = []

        for year in YEARS:
            a_df  = periods["april"][year]
            mj_df = periods["may_july"][year]
            as_df = periods["aug_sep"][year]

            a_row  = a_df[a_df["batter"] == batter]
            mj_row = mj_df[mj_df["batter"] == batter]
            as_row = as_df[as_df["batter"] == batter]

            a_pa   = int(a_row["pa"].iloc[0])  if len(a_row)  > 0 else 0
            mj_pa  = int(mj_row["pa"].iloc[0]) if len(mj_row) > 0 else 0
            as_pa  = int(as_row["pa"].iloc[0]) if len(as_row) > 0 else 0

            a_w    = float(a_row["woba"].iloc[0])  if a_pa  >= MIN_PA else None
            mj_w   = float(mj_row["woba"].iloc[0]) if mj_pa >= MIN_PA else None
            as_w   = float(as_row["woba"].iloc[0]) if as_pa >= MIN_PA else None

            # Pattern 1: Slow Starter (april + may_july)
            if a_w is not None and mj_w is not None:
                slow_eligible += 1
                april_wobas.append(a_w)
                mj_wobas.append(mj_w)
                if mj_w - a_w >= SLOW_STARTER_DELTA:
                    slow_fires += 1

            # Pattern 2: Second Half Fader (may_july + aug_sep)
            if mj_w is not None and as_w is not None:
                fader_eligible += 1
                if mj_w - as_w >= FADER_DELTA:
                    fader_fires += 1

            # Pattern 3: Summer Performer (april + aug_sep)
            if a_w is not None and as_w is not None:
                summer_eligible += 1
                as_wobas.append(as_w)
                if as_w - a_w >= SUMMER_DELTA:
                    summer_fires += 1

        # Require at least MIN_YEARS of eligible data per pattern
        slow_starter     = slow_fires  >= MIN_YEARS and slow_eligible  >= MIN_YEARS
        second_half_fader = fader_fires >= MIN_YEARS and fader_eligible >= MIN_YEARS
        summer_performer  = summer_fires >= MIN_YEARS and summer_eligible >= MIN_YEARS

        years_of_data = max(slow_eligible, fader_eligible, summer_eligible)
        if years_of_data < MIN_YEARS:
            continue

        rows.append({
            "player_id":         int(batter),
            "slow_starter":      slow_starter,
            "second_half_fader": second_half_fader,
            "summer_performer":  summer_performer,
            "years_of_data":     years_of_data,
            "april_woba_avg":    round(float(np.mean(april_wobas)), 4) if april_wobas else None,
            "may_july_woba_avg": round(float(np.mean(mj_wobas)), 4)   if mj_wobas   else None,
            "aug_sept_woba_avg": round(float(np.mean(as_wobas)), 4)   if as_wobas   else None,
        })

    return pd.DataFrame(rows)


# ------------------------------------------------------------------
# Name lookup
# ------------------------------------------------------------------

def load_name_map() -> dict:
    """Load batter_id -> name from luck_scores.csv (current season coverage)."""
    path = BASE_DIR / "luck_scores.csv"
    if not path.exists():
        return {}
    df = pd.read_csv(path, usecols=["batter", "name"])
    return dict(zip(df["batter"], df["name"]))


# ------------------------------------------------------------------
# Summary output
# ------------------------------------------------------------------

def print_summary(df: pd.DataFrame, name_map: dict) -> None:
    n_slow    = df["slow_starter"].sum()
    n_fader   = df["second_half_fader"].sum()
    n_summer  = df["summer_performer"].sum()
    n_multi   = (df[["slow_starter","second_half_fader","summer_performer"]].sum(axis=1) >= 2).sum()
    n_total   = len(df)

    print("\n" + "=" * 60)
    print("PHASE C SEASONAL PATTERN DETECTION RESULTS")
    print("=" * 60)
    print(f"Players with >= {MIN_YEARS} years of qualifying data: {n_total:,}")
    print(f"  Slow Starter       (Apr << May-Jul, >=20pt, 2+ yrs): {n_slow:>4} ({n_slow/n_total:.1%})")
    print(f"  Second Half Fader  (May-Jul >> Aug-Sep, >=20pt, 2+ yrs): {n_fader:>4} ({n_fader/n_total:.1%})")
    print(f"  Summer Performer   (Aug-Sep >> Apr, >=25pt, 2+ yrs): {n_summer:>4} ({n_summer/n_total:.1%})")
    print(f"  Multiple patterns: {n_multi:>4} ({n_multi/n_total:.1%})")

    def show_examples(mask: pd.Series, label: str, cols: list[str]) -> None:
        subset = df[mask].sort_values("years_of_data", ascending=False).head(5)
        if subset.empty:
            print(f"\n  No {label} detected.")
            return
        print(f"\n--- {label} (top 5 by years of data) ---")
        print(f"  {'Name':<24} {'Yrs':>4}  {cols[0]:>10}  {cols[1]:>10}  {'Delta':>8}")
        print(f"  {'-'*65}")
        for _, r in subset.iterrows():
            name = name_map.get(r["player_id"], f"ID:{r['player_id']}")
            v1   = r[cols[0]]
            v2   = r[cols[1]]
            delta = (v2 - v1) if v1 is not None and v2 is not None else float("nan")
            print(f"  {name:<24} {r['years_of_data']:>4}  "
                  f"{v1:>10.4f}  {v2:>10.4f}  {delta:>+8.4f}")

    show_examples(
        df["slow_starter"],
        "SLOW STARTERS",
        ["april_woba_avg", "may_july_woba_avg"],
    )
    show_examples(
        df["second_half_fader"],
        "SECOND HALF FADERS",
        ["may_july_woba_avg", "aug_sept_woba_avg"],
    )
    show_examples(
        df["summer_performer"],
        "SUMMER PERFORMERS",
        ["april_woba_avg", "aug_sept_woba_avg"],
    )

    if n_multi > 0:
        multi_mask = df[["slow_starter","second_half_fader","summer_performer"]].sum(axis=1) >= 2
        print(f"\n--- MULTIPLE PATTERNS ({n_multi} players) ---")
        for _, r in df[multi_mask].head(10).iterrows():
            name = name_map.get(r["player_id"], f"ID:{r['player_id']}")
            flags = []
            if r["slow_starter"]:      flags.append("SlowStart")
            if r["second_half_fader"]: flags.append("Fader")
            if r["summer_performer"]:  flags.append("SummerPerf")
            print(f"  {name:<24} {', '.join(flags)}")


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

def main():
    print("Phase C Seasonal Pattern Detection")
    print("=" * 60)

    periods  = load_all_periods()
    results  = detect_patterns(periods)
    name_map = load_name_map()

    print_summary(results, name_map)

    # Save to JSON
    DATA_DIR.mkdir(exist_ok=True)
    records = results.to_dict(orient="records")
    with open(OUT_PATH, "w") as f:
        json.dump(records, f, indent=2)
    print(f"\nSaved {len(records)} player records -> {OUT_PATH}")

    # Quick cross-tab
    print("\nPattern co-occurrence matrix:")
    for p1 in ["slow_starter", "second_half_fader", "summer_performer"]:
        for p2 in ["slow_starter", "second_half_fader", "summer_performer"]:
            n = (results[p1] & results[p2]).sum()
            print(f"  {p1:<20} & {p2:<20}: {n}")


if __name__ == "__main__":
    main()
