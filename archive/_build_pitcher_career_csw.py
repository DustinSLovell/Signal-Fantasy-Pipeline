"""
_build_pitcher_career_csw.py
Build career CSW% baselines from historical April parquet cache.
Saves to data/pitcher_career_csw.json.
"""
import io, sys, json, warnings
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
warnings.filterwarnings("ignore")

import pandas as pd
from pathlib import Path

CACHE = Path("backtest_cache")
YEARS = [2022, 2023, 2024, 2025]
CSW_DESCS = {"called_strike", "swinging_strike", "swinging_strike_blocked", "foul_tip"}
MIN_PITCHES = 100

# Load name lookup from pitcher_luck_scores.csv
pdf = pd.read_csv("pitcher_luck_scores.csv")
name_lk = dict(zip(pdf["pitcher"].astype(int), pdf["name"])) if "pitcher" in pdf.columns else {}

per_pitcher = {}

for year in YEARS:
    path = CACHE / f"pitcher_statcast_april_{year}.parquet"
    if not path.exists():
        print(f"  SKIP {year}: {path.name} not found")
        continue
    df = pd.read_parquet(path, columns=["pitcher", "description"])
    df = df[~df["description"].isin({"automatic_ball", "pitchout"})]
    df["is_csw"] = df["description"].isin(CSW_DESCS).astype(int)

    agg = df.groupby("pitcher").agg(
        csw_count=("is_csw", "sum"),
        total_pitches=("is_csw", "count"),
    ).reset_index()
    agg = agg[agg["total_pitches"] >= MIN_PITCHES].copy()
    agg["csw"] = (agg["csw_count"] / agg["total_pitches"]).round(4)
    agg["year"] = year

    for _, row in agg.iterrows():
        pid = int(row["pitcher"])
        if pid not in per_pitcher:
            per_pitcher[pid] = []
        per_pitcher[pid].append({
            "year": year,
            "csw": float(row["csw"]),
            "n_pitches": int(row["total_pitches"]),
        })
    print(f"  {year}: {len(agg)} pitchers with >= {MIN_PITCHES} pitches")

# Build weighted career average
career_csw = {}
for pid, seasons in per_pitcher.items():
    total_w = sum(s["n_pitches"] for s in seasons)
    if total_w < 200:
        continue
    w_csw = sum(s["csw"] * s["n_pitches"] for s in seasons) / total_w
    career_csw[pid] = {
        "name": name_lk.get(pid, ""),
        "career_csw": round(w_csw, 4),
        "n_seasons": len(seasons),
        "career_pitches": total_w,
        "seasons": {str(s["year"]): s["csw"] for s in seasons},
    }

print(f"\nCareer CSW baselines: {len(career_csw)} pitchers")

import numpy as np
vals = [v["career_csw"] for v in career_csw.values()]
print(f"Mean career CSW: {np.mean(vals):.3f}, std: {np.std(vals):.3f}")

Path("data/pitcher_career_csw.json").write_text(json.dumps(career_csw, indent=2))
print("Saved: data/pitcher_career_csw.json")
