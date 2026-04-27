"""
compute_april_pattern_flag.py
==============================
Checks whether current buy/sell pitchers showed the same
April luck pattern in prior years (elevated BABIP allowed
for buys; low BABIP for sells).

For each pitcher in current buy/sell pool:
  - Look up their April BABIP allowed in 2024 and 2025
  - Buy signal confirmed if BABIP > 0.310 in a prior year
    (repeatedly stranding runners above league avg in April)
  - Sell signal confirmed if BABIP < 0.270 in a prior year
    (repeatedly suppressing BABIP below league avg)

Adds column: april_pattern_flag
Values: "Multi-year pattern", "First occurrence",
        "Insufficient history"

Output: updates pitcher_luck_scores.csv in place.
"""

import os
import pandas as pd
from pathlib import Path

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
SCORES_PATH = os.path.join(BASE_DIR, "pitcher_luck_scores.csv")

BABIP_BUY_THRESHOLD  = 0.310   # above this = bad luck BABIP (buy pattern)
BABIP_SELL_THRESHOLD = 0.270   # below this = good luck BABIP (sell pattern)
CHECK_YEARS          = [2024, 2025]
MIN_APRIL_IP         = 15.0


def load_april_babip(years: list[int]) -> pd.DataFrame:
    """Load per-pitcher April BABIP from cached parquets for given years."""
    from _pitcher_tier_audit import (
        load_or_fetch, per_start_stats, pitcher_stats, CACHE_DIR
    )

    rows = []
    for year in years:
        apr_cache = Path(CACHE_DIR) / f"pitcher_statcast_april_{year}.parquet"
        try:
            sc = load_or_fetch(apr_cache, f"{year}-04-01", f"{year}-04-30",
                               f"April {year}")
            if sc.empty:
                continue
            stats = pitcher_stats(sc, per_start_stats(sc))
            stats = stats[stats["ip"] >= MIN_APRIL_IP].copy()
            for _, r in stats.iterrows():
                rows.append({
                    "pitcher": int(r["pitcher"]),
                    "year":    year,
                    "babip":   float(r["babip"]),
                    "ip":      float(r["ip"]),
                })
        except Exception as e:
            print(f"  WARNING: {year} load failed — {e}")

    return pd.DataFrame(rows)


def compute_pattern_flag(scores: pd.DataFrame,
                          historical: pd.DataFrame) -> pd.Series:
    """
    For each row in scores, return an april_pattern_flag string.
    """
    flags = []
    for _, row in scores.iterrows():
        verdict = row.get("verdict", "")
        pid     = row.get("pitcher")

        if verdict not in ("Buy low", "Slight buy", "Sell high", "Slight sell"):
            flags.append("")
            continue

        if historical.empty or pid is None or pd.isna(pid):
            flags.append("Insufficient history")
            continue

        hist = historical[historical["pitcher"] == int(pid)]
        if hist.empty:
            flags.append("Insufficient history")
            continue

        is_buy  = verdict in ("Buy low", "Slight buy")
        is_sell = verdict in ("Sell high", "Slight sell")

        # Check for multi-year pattern
        if is_buy:
            # High BABIP in prior April = recurring bad luck = buy pattern confirmed
            pattern_years = hist[hist["babip"] > BABIP_BUY_THRESHOLD]["year"].tolist()
        else:
            # Low BABIP in prior April = recurring good luck = sell pattern confirmed
            pattern_years = hist[hist["babip"] < BABIP_SELL_THRESHOLD]["year"].tolist()

        if len(pattern_years) >= 1:
            flags.append(f"Multi-year pattern ({', '.join(str(y) for y in sorted(pattern_years))})")
        else:
            flags.append("First occurrence")

    return pd.Series(flags, index=scores.index)


def main():
    if not os.path.exists(SCORES_PATH):
        print(f"MISSING: {SCORES_PATH}")
        return

    scores = pd.read_csv(SCORES_PATH)
    print(f"Loaded {len(scores):,} pitchers from {SCORES_PATH}")

    print(f"Loading April BABIP history for {CHECK_YEARS} ...")
    historical = load_april_babip(CHECK_YEARS)
    print(f"  {len(historical):,} pitcher-season rows loaded")
    print(f"  {historical['pitcher'].nunique():,} unique pitchers")

    # Drop old flag if re-running
    scores.drop(columns=["april_pattern_flag"], inplace=True, errors="ignore")

    scores["april_pattern_flag"] = compute_pattern_flag(scores, historical)

    # Print summary for buy/sell pool
    pool = scores[scores["verdict"].isin(["Buy low", "Slight buy", "Sell high", "Slight sell"])].copy()
    pattern_counts = pool["april_pattern_flag"].value_counts()

    print(f"\n  April pattern flag distribution (buy+sell pool, n={len(pool)}):")
    for val, cnt in pattern_counts.items():
        print(f"    {val:<45} {cnt:>3}")

    # Detail for Buy low
    buys = pool[pool["verdict"] == "Buy low"][["name","verdict","lob_pct","BABIP_allowed","april_pattern_flag"]]
    print(f"\n  BUY LOW multi-year patterns:")
    print(buys.to_string(index=False))

    multi = pool[pool["april_pattern_flag"].str.startswith("Multi-year", na=False)]
    print(f"\n  Multi-year confirmed: {len(multi)} pitchers")

    scores.to_csv(SCORES_PATH, index=False)
    print(f"\nSaved: {SCORES_PATH}")


if __name__ == "__main__":
    main()
