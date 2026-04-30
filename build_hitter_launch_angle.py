#!/usr/bin/env python3
"""
build_hitter_launch_angle.py
Computes per-player average launch angle for the current 2026 season
and a career baseline from April v4 CSVs (2022-2025).

Output: data/hitter_launch_angle.json
  {
    "<mlbam_id>": {
      "current_la_avg":  float,   # 2026 season-to-date mean LA
      "current_la_n":    int,     # BBE count (must be >=50 to flag)
      "career_la_avg":   float,   # weighted mean across 2022-2025 April
      "career_la_n":     int,     # total career BBE (must be >=100 for baseline)
      "la_delta":        float    # current_la_avg - career_la_avg (or null)
    }
  }

Usage:
  python build_hitter_launch_angle.py            # build and save
  python build_hitter_launch_angle.py --check    # print summary, no write
"""

import argparse
import json
import math
import os
import sys
from functools import reduce
from pathlib import Path

import pandas as pd

BASE_DIR    = Path(__file__).parent
CACHE_DIR   = BASE_DIR / "backtest_cache"
CURRENT_CSV = BASE_DIR / "hitters_statcast.csv"
OUT_PATH    = BASE_DIR / "data" / "hitter_launch_angle.json"

CAREER_YEARS       = [2022, 2023, 2024, 2025]
MIN_CURRENT_BBE    = 50    # minimum BBE for current-season LA to be reliable
MIN_CAREER_BBE     = 100   # minimum career BBE for baseline to be trusted
MIN_YEAR_BBE       = 10    # minimum per-year BBE to include in weighted mean

BBE_EVENTS = {
    "field_out", "single", "double", "triple", "home_run", "sac_fly",
    "grounded_into_double_play", "double_play", "field_error", "force_out",
    "fielders_choice", "fielders_choice_out", "sac_fly_double_play", "triple_play",
}


def load_year_la(year: int) -> pd.DataFrame:
    path = CACHE_DIR / f"v4_april_{year}.csv"
    if not path.exists():
        print(f"  [{year}] MISSING — skipping")
        return pd.DataFrame(columns=["batter", f"la_avg_{year}", f"la_n_{year}"])
    df = pd.read_csv(path, usecols=["batter", "launch_angle", "events"])
    bbe = df[df["events"].isin(BBE_EVENTS) & df["launch_angle"].notna()]
    agg = (
        bbe.groupby("batter")["launch_angle"]
        .agg(["mean", "count"])
        .reset_index()
        .rename(columns={"mean": f"la_avg_{year}", "count": f"la_n_{year}"})
    )
    n_qual = (agg[f"la_n_{year}"] >= MIN_YEAR_BBE).sum()
    print(f"  [{year}] {len(bbe):,} BBE rows  |  {len(agg)} players  |  {n_qual} with >={MIN_YEAR_BBE} BBE")
    return agg


def build_career(dfs: list) -> pd.DataFrame:
    merged = reduce(lambda a, b: pd.merge(a, b, on="batter", how="outer"), dfs)

    def weighted_mean(row):
        total_n, total_la = 0, 0.0
        for yr in CAREER_YEARS:
            n  = row.get(f"la_n_{yr}",  float("nan"))
            la = row.get(f"la_avg_{yr}", float("nan"))
            if math.isfinite(n) and math.isfinite(la) and n >= MIN_YEAR_BBE:
                total_n  += n
                total_la += la * n
        if total_n >= MIN_CAREER_BBE:
            return total_la / total_n, int(total_n)
        return float("nan"), int(total_n)

    merged["career_la_avg"] = merged.apply(lambda r: weighted_mean(r)[0], axis=1)
    merged["career_la_n"]   = merged.apply(lambda r: weighted_mean(r)[1], axis=1)
    return merged[["batter", "career_la_avg", "career_la_n"]]


def load_current_la() -> pd.DataFrame:
    if not CURRENT_CSV.exists():
        print(f"  CURRENT: {CURRENT_CSV} not found")
        return pd.DataFrame(columns=["batter", "current_la_avg", "current_la_n"])
    df = pd.read_csv(CURRENT_CSV, usecols=["batter", "launch_angle", "events"])
    bbe = df[df["events"].isin(BBE_EVENTS) & df["launch_angle"].notna()]
    agg = (
        bbe.groupby("batter")["launch_angle"]
        .agg(["mean", "count"])
        .reset_index()
        .rename(columns={"mean": "current_la_avg", "count": "current_la_n"})
    )
    n_qual = (agg["current_la_n"] >= MIN_CURRENT_BBE).sum()
    print(f"  [2026] {len(bbe):,} BBE rows  |  {len(agg)} players  |  {n_qual} with >={MIN_CURRENT_BBE} BBE")
    return agg


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Print summary without writing")
    args = parser.parse_args()

    print("=" * 60)
    print("Build Hitter Launch Angle Baselines")
    print("=" * 60)

    print("\nCareer baselines (April v4 CSVs):")
    year_dfs = [load_year_la(yr) for yr in CAREER_YEARS]
    career_df = build_career(year_dfs)

    qual_career = career_df["career_la_avg"].notna().sum()
    print(f"\n  Career qualified (>={MIN_CAREER_BBE} BBE): {qual_career} players")
    print(f"  Career LA range: {career_df['career_la_avg'].min():.1f} to "
          f"{career_df['career_la_avg'].max():.1f} degrees")
    print(f"  Career LA mean:  {career_df['career_la_avg'].mean():.1f} degrees")

    print("\nCurrent season (hitters_statcast.csv):")
    current_df = load_current_la()

    combined = pd.merge(current_df, career_df, on="batter", how="left")
    combined["la_delta"] = combined.apply(
        lambda r: (r["current_la_avg"] - r["career_la_avg"])
        if math.isfinite(r.get("career_la_avg", float("nan")))
        else float("nan"),
        axis=1,
    )

    qualified_current = combined["current_la_n"] >= MIN_CURRENT_BBE
    has_delta = qualified_current & combined["la_delta"].notna()
    n_up   = (has_delta & (combined["la_delta"] > 3.0)).sum()
    n_down = (has_delta & (combined["la_delta"] < -3.0)).sum()

    print(f"\n  Players with current LA (>={MIN_CURRENT_BBE} BBE): {qualified_current.sum()}")
    print(f"  Players with full delta:    {has_delta.sum()}")
    print(f"  la_trending_up (delta >+3°): {n_up}")
    print(f"  la_trending_down (delta <-3°): {n_down}")

    # Build output dict
    out = {}
    for _, row in combined.iterrows():
        pid = str(int(row["batter"]))
        curr_n  = int(row["current_la_n"]) if math.isfinite(row["current_la_n"]) else 0
        curr_la = round(row["current_la_avg"], 2) if math.isfinite(row["current_la_avg"]) else None
        car_la  = round(row["career_la_avg"],  2) if math.isfinite(row.get("career_la_avg", float("nan"))) else None
        car_n   = int(row["career_la_n"])          if math.isfinite(row.get("career_la_n",  float("nan"))) else 0
        delta   = round(row["la_delta"],       2)  if math.isfinite(row.get("la_delta",      float("nan"))) else None
        out[pid] = {
            "current_la_avg": curr_la,
            "current_la_n":   curr_n,
            "career_la_avg":  car_la,
            "career_la_n":    car_n,
            "la_delta":       delta,
        }

    if args.check:
        print("\n[--check] No file written.")
        return

    with open(OUT_PATH, "w") as f:
        json.dump(out, f, indent=2)

    print(f"\n  Saved: {OUT_PATH}  ({len(out)} records)")


if __name__ == "__main__":
    main()
