"""
build_pitcher_phase2_baselines.py — Phase 2 career baseline builder

Builds two files:
  data/pitcher_career_velo_per_pitch.json
    Career average velocity per pitch type per pitcher, from April parquets 2022-2025.
    {pitcher_id: {pitch_type: avg_speed, ...}}

  data/pitcher_career_arsenal_rv.json
    Career average run_value_per_100 per pitch type per pitcher, from
    statcast_pitcher_arsenal_stats 2022-2025.
    {pitcher_id: {pitch_type: rv100_avg, ...}}

Also saves:
  data/pitcher_arsenal_rv_2026.json
    Current 2026 run_value_per_100 per pitch type per pitcher.
    {pitcher_id: {pitch_type: rv100, whiff_pct, pitches}}
"""

import json
import os
import math
import numpy as np
import pandas as pd
from pathlib import Path

BASE_DIR   = Path(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR  = BASE_DIR / "backtest_cache"
DATA_DIR   = BASE_DIR / "data"

ALL_RV_PATH    = DATA_DIR / "pitcher_arsenal_rv_allyears.csv"
CAREER_VELO_PATH = DATA_DIR / "pitcher_career_velo_per_pitch.json"
CAREER_RV_PATH   = DATA_DIR / "pitcher_career_arsenal_rv.json"
CURR_RV_PATH     = DATA_DIR / "pitcher_arsenal_rv_2026.json"

CAREER_YEARS = [2022, 2023, 2024, 2025]
MIN_PITCHES  = 50    # minimum pitches per year-pitcher-type to include in velo avg
MIN_RV_PA    = 10    # minimum PA per year-pitcher-type to include in RV avg


# ── Part A: Career per-pitch velocity from April parquets ────────────────────

def build_career_velo():
    """
    Reads April parquets (release_speed, pitch_type, pitcher) for 2022-2025.
    Averages release_speed per pitcher × pitch_type across years.
    Returns {pitcher_id: {pitch_type: avg_speed}}
    """
    # accum[pid][pt] = list of per-year avg speeds
    accum = {}

    for year in CAREER_YEARS:
        path = CACHE_DIR / f"pitcher_statcast_april_{year}.parquet"
        if not path.exists():
            print(f"  WARNING: {path} not found — skipping {year}")
            continue

        sc = pd.read_parquet(path)
        if "pitch_type" not in sc.columns or "release_speed" not in sc.columns:
            print(f"  WARNING: {year} parquet missing pitch_type or release_speed")
            continue

        sc = sc.copy()
        sc["pitcher"] = pd.to_numeric(sc["pitcher"], errors="coerce")
        sc = sc.dropna(subset=["pitcher", "release_speed", "pitch_type"])
        sc = sc[sc["pitch_type"] != ""]
        sc["pitcher"] = sc["pitcher"].astype(int)
        sc["release_speed"] = sc["release_speed"].astype(float)

        for (pid, pt), grp in sc.groupby(["pitcher", "pitch_type"]):
            if len(grp) < MIN_PITCHES:
                continue
            avg_spd = grp["release_speed"].mean()
            if math.isnan(avg_spd):
                continue
            if pid not in accum:
                accum[pid] = {}
            if pt not in accum[pid]:
                accum[pid][pt] = []
            accum[pid][pt].append(round(avg_spd, 2))

        n_pitchers = sc["pitcher"].nunique()
        print(f"  April {year}: {n_pitchers:,} pitchers processed")

    # Average across years
    career_velo = {}
    for pid, pt_dict in accum.items():
        career_velo[pid] = {}
        for pt, speeds in pt_dict.items():
            career_velo[pid][pt] = round(sum(speeds) / len(speeds), 2)

    return career_velo


# ── Part B: Career per-pitch run value from arsenal stats ────────────────────

def build_career_rv():
    """
    Reads pitcher_arsenal_rv_allyears.csv for years 2022-2025.
    Averages run_value_per_100 per pitcher × pitch_type across years.
    Returns {pitcher_id: {pitch_type: {rv100_avg, whiff_pct_avg, n_years}}}
    """
    if not ALL_RV_PATH.exists():
        print(f"ERROR: {ALL_RV_PATH} not found — run pybaseball fetch first")
        return {}

    all_rv = pd.read_csv(ALL_RV_PATH)
    career = all_rv[all_rv["year"].isin(CAREER_YEARS)].copy()

    career["player_id"] = pd.to_numeric(career["player_id"], errors="coerce")
    career = career.dropna(subset=["player_id", "pitch_type", "run_value_per_100"])
    career["player_id"] = career["player_id"].astype(int)

    # Filter by minimum PA to avoid tiny-sample noise
    career = career[career["pa"] >= MIN_RV_PA]

    accum = {}  # {pid: {pt: {rv100s: [], whiffs: []}}}

    for _, row in career.iterrows():
        pid = int(row["player_id"])
        pt  = row["pitch_type"]
        rv  = float(row["run_value_per_100"])
        wh  = float(row["whiff_percent"]) if pd.notna(row.get("whiff_percent")) else None
        if math.isnan(rv):
            continue
        if pid not in accum:
            accum[pid] = {}
        if pt not in accum[pid]:
            accum[pid][pt] = {"rv100s": [], "whiffs": []}
        accum[pid][pt]["rv100s"].append(rv)
        if wh is not None and not math.isnan(wh):
            accum[pid][pt]["whiffs"].append(wh)

    career_rv = {}
    for pid, pt_dict in accum.items():
        career_rv[pid] = {}
        for pt, vals in pt_dict.items():
            rv100s = vals["rv100s"]
            whiffs = vals["whiffs"]
            career_rv[pid][pt] = {
                "rv100_avg":       round(sum(rv100s) / len(rv100s), 3),
                "whiff_pct_avg":   round(sum(whiffs) / len(whiffs), 2) if whiffs else None,
                "n_years":         len(rv100s),
            }

    return career_rv


def build_current_rv():
    """
    Extracts 2026 run_value_per_100 per pitcher × pitch_type from arsenal stats.
    Returns {pitcher_id: {pitch_type: {rv100, whiff_pct, pitches}}}
    """
    if not ALL_RV_PATH.exists():
        return {}

    all_rv = pd.read_csv(ALL_RV_PATH)
    curr   = all_rv[all_rv["year"] == 2026].copy()

    curr["player_id"] = pd.to_numeric(curr["player_id"], errors="coerce")
    curr = curr.dropna(subset=["player_id", "pitch_type", "run_value_per_100"])
    curr["player_id"] = curr["player_id"].astype(int)

    result = {}
    for _, row in curr.iterrows():
        pid = int(row["player_id"])
        pt  = row["pitch_type"]
        rv  = float(row["run_value_per_100"])
        wh  = float(row["whiff_percent"]) if pd.notna(row.get("whiff_percent")) else None
        pit = int(row["pitches"]) if pd.notna(row.get("pitches")) else 0
        if math.isnan(rv):
            continue
        if pid not in result:
            result[pid] = {}
        result[pid][pt] = {
            "rv100":      round(rv, 3),
            "whiff_pct":  round(wh, 2) if wh is not None else None,
            "pitches":    pit,
        }

    return result


def main():
    print("=== Phase 2 baseline builder ===\n")

    # Part A: Career per-pitch velocity
    print("Part A: Computing career per-pitch velocity from April parquets...")
    career_velo = build_career_velo()
    with open(CAREER_VELO_PATH, "w") as f:
        json.dump({str(k): v for k, v in career_velo.items()}, f, indent=2)
    total_pitch_types = sum(len(v) for v in career_velo.values())
    print(f"  Saved: {CAREER_VELO_PATH}")
    print(f"  Pitchers: {len(career_velo):,} | Total pitch-type entries: {total_pitch_types:,}")

    # Part B: Career per-pitch run value
    print("\nPart B: Building career run value baselines from arsenal stats...")
    career_rv = build_career_rv()
    with open(CAREER_RV_PATH, "w") as f:
        json.dump({str(k): v for k, v in career_rv.items()}, f, indent=2)
    total_rv_entries = sum(len(v) for v in career_rv.values())
    print(f"  Saved: {CAREER_RV_PATH}")
    print(f"  Pitchers: {len(career_rv):,} | Total pitch-type entries: {total_rv_entries:,}")

    # Part C: Current 2026 run value
    print("\nPart C: Extracting 2026 current run values...")
    curr_rv = build_current_rv()
    with open(CURR_RV_PATH, "w") as f:
        json.dump({str(k): v for k, v in curr_rv.items()}, f, indent=2)
    print(f"  Saved: {CURR_RV_PATH}")
    print(f"  Pitchers: {len(curr_rv):,}")

    # Coverage summary
    curr_pm_path = DATA_DIR / "pitcher_current_pitch_mix.json"
    if curr_pm_path.exists():
        with open(curr_pm_path) as f:
            curr_pm = json.load(f)
        ids_curr = set(str(k) for k in curr_pm.keys())
        ids_velo = set(str(k) for k in career_velo.keys())
        ids_rv   = set(str(k) for k in career_rv.keys())
        ids_curr_rv = set(str(k) for k in curr_rv.keys())
        overlap_velo = ids_curr & ids_velo
        overlap_rv   = ids_curr & ids_rv & ids_curr_rv
        print(f"\nCoverage vs 2026 active pitchers ({len(ids_curr)}):")
        print(f"  Velo delta computable: {len(overlap_velo)} ({len(overlap_velo)/len(ids_curr)*100:.0f}%)")
        print(f"  RV delta computable:   {len(overlap_rv)} ({len(overlap_rv)/len(ids_curr)*100:.0f}%)")

    print("\nDone.")


if __name__ == "__main__":
    os.chdir(str(BASE_DIR))
    main()
