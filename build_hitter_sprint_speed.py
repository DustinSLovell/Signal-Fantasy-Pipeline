"""
build_hitter_sprint_speed.py

Fetches Statcast sprint speed for 2022-2025 via pybaseball.statcast_sprint_speed.
Computes year-over-year trend and flags speed cliff (drop > 0.3 ft/sec YoY).

Output: data/hitter_sprint_speed.json
  {
    batter_id: {
      "speeds":         {year: speed, ...},   # ft/sec per year available
      "latest_speed":   float,                # most recent year's speed
      "prev_speed":     float | null,         # prior year's speed (for YoY delta)
      "yoy_delta":      float | null,         # latest - prev (negative = slower)
      "trend_3yr":      float | null,         # avg annual change over 3 years
      "speed_flag":     bool,                 # YoY drop > SPEED_CLIFF_THRESH
    }
  }
"""

import json
import math
import os
from pathlib import Path

import pandas as pd
import pybaseball

BASE_DIR  = Path(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR  = BASE_DIR / "data"
OUT_PATH  = DATA_DIR / "hitter_sprint_speed.json"

FETCH_YEARS       = [2022, 2023, 2024, 2025]
MIN_OPP           = 10        # minimum sprint opportunities to include
SPEED_CLIFF_THRESH = 0.3      # ft/sec YoY drop → speed cliff flag


def main():
    print("=== build_hitter_sprint_speed.py ===\n")
    pybaseball.cache.enable()

    # ── Fetch all years ───────────────────────────────────────────────────────
    all_rows = []
    for year in FETCH_YEARS:
        try:
            df = pybaseball.statcast_sprint_speed(year, min_opp=MIN_OPP)
            df["year"] = year
            all_rows.append(df)
            print(f"  {year}: {len(df):,} players fetched")
        except Exception as e:
            print(f"  WARNING: {year} fetch failed — {e}")

    if not all_rows:
        print("ERROR: No data fetched. Aborting.")
        return

    combined = pd.concat(all_rows, ignore_index=True)
    combined = combined.dropna(subset=["player_id", "sprint_speed"])
    combined["player_id"] = combined["player_id"].astype(int)

    # ── Build per-player year dict ────────────────────────────────────────────
    accum = {}
    for _, row in combined.iterrows():
        pid   = int(row["player_id"])
        yr    = int(row["year"])
        spd   = round(float(row["sprint_speed"]), 2)
        accum.setdefault(pid, {})[yr] = spd

    # ── Compute YoY delta and flag ────────────────────────────────────────────
    result = {}
    n_flagged = 0
    for pid, speeds in accum.items():
        years_sorted = sorted(speeds.keys())
        latest_yr    = years_sorted[-1]
        latest_spd   = speeds[latest_yr]

        prev_spd  = None
        yoy_delta = None
        if len(years_sorted) >= 2:
            prev_yr   = years_sorted[-2]
            prev_spd  = speeds[prev_yr]
            yoy_delta = round(latest_spd - prev_spd, 3)

        trend_3yr = None
        if len(years_sorted) >= 3:
            first_spd = speeds[years_sorted[-3]]
            n_steps   = len(years_sorted) - 1
            trend_3yr = round((latest_spd - first_spd) / n_steps, 3)

        speed_flag = (
            yoy_delta is not None
            and yoy_delta < -SPEED_CLIFF_THRESH
        )
        if speed_flag:
            n_flagged += 1

        result[pid] = {
            "speeds":       speeds,
            "latest_speed": latest_spd,
            "prev_speed":   prev_spd,
            "yoy_delta":    yoy_delta,
            "trend_3yr":    trend_3yr,
            "speed_flag":   speed_flag,
        }

    # ── Save ──────────────────────────────────────────────────────────────────
    with open(OUT_PATH, "w") as f:
        json.dump({str(k): v for k, v in result.items()}, f, indent=2)
    print(f"\nSaved: {OUT_PATH}  ({len(result):,} players)")
    print(f"Speed cliff flags (YoY drop > {SPEED_CLIFF_THRESH} ft/s): {n_flagged}")

    # ── Top declines ──────────────────────────────────────────────────────────
    decline_rows = [
        (pid, rec["latest_speed"], rec["prev_speed"], rec["yoy_delta"])
        for pid, rec in result.items()
        if rec["yoy_delta"] is not None and rec["yoy_delta"] < 0
    ]
    decline_rows.sort(key=lambda x: x[3])
    print(f"\n── Top 15 speed declines (YoY) ─────────────────────────────")
    print(f"  {'ID':>8}  {'Prev':>6}  {'Now':>6}  {'Delta':>7}")
    for pid, latest, prev, delta in decline_rows[:15]:
        print(f"  {pid:>8}  {prev:>6.1f}  {latest:>6.1f}  {delta:>+6.2f} ft/s")

    print("\nDone.")


if __name__ == "__main__":
    os.chdir(str(BASE_DIR))
    main()
