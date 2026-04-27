"""
_build_sprint_speed.py
Pull sprint speed data 2022-2025, build career baselines,
save to data/hitter_career_sprint.json.
"""
import io, sys, json, warnings
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np
from pathlib import Path

try:
    import pybaseball as pb
    pb.cache.enable()
except ImportError:
    print("ERROR: pybaseball not installed")
    sys.exit(1)

YEARS = [2022, 2023, 2024, 2025]
MIN_OPP = 10

# Load name lookup
ls = pd.read_csv("luck_scores.csv")
name_lk = dict(zip(ls["batter"].astype(int), ls["name"]))

per_player = {}

for year in YEARS:
    print(f"  Pulling sprint speed {year}...")
    try:
        df = pb.statcast_sprint_speed(year, min_opp=MIN_OPP)
        if df is None or df.empty:
            print(f"    {year}: no data")
            continue
        # Columns: player_id, sprint_speed, hp_to_1b, competitive_runs, ...
        df = df[df["player_id"].notna()].copy()
        df["player_id"] = df["player_id"].astype(int)
        for _, row in df.iterrows():
            pid = int(row["player_id"])
            spd = float(row.get("sprint_speed", float("nan")))
            if np.isnan(spd): continue
            opp = int(row.get("competitive_runs", 0))
            if pid not in per_player:
                per_player[pid] = []
            per_player[pid].append({"year": year, "speed": spd, "opp": opp})
        print(f"    {year}: {len(df)} players")
    except Exception as e:
        print(f"    {year} ERROR: {e}")

print(f"\nTotal players with sprint data: {len(per_player)}")

# Build career baselines and trend
career_sprint = {}
for pid, seasons in per_player.items():
    if len(seasons) < 1:
        continue
    seasons_sorted = sorted(seasons, key=lambda s: s["year"])
    total_opp = sum(s["opp"] for s in seasons_sorted)
    if total_opp < 20:
        continue
    # Weighted career average
    career_avg = sum(s["speed"] * s["opp"] for s in seasons_sorted) / total_opp
    by_year = {s["year"]: s["speed"] for s in seasons_sorted}

    # Trend: compare last 2 seasons
    speeds = [s["speed"] for s in seasons_sorted[-2:]]
    if len(speeds) >= 2:
        delta = speeds[-1] - speeds[-2]
        trend = "declining" if delta < -0.5 else ("improving" if delta > 0.5 else "stable")
    else:
        trend = "stable"

    career_sprint[pid] = {
        "name": name_lk.get(pid, ""),
        "career_sprint_speed": round(career_avg, 2),
        "trend": trend,
        "n_seasons": len(seasons_sorted),
        "total_opp": total_opp,
        "seasons": by_year,
    }

print(f"Career sprint baselines (>= 20 opp): {len(career_sprint)}")
vals = [v["career_sprint_speed"] for v in career_sprint.values()]
print(f"Mean career sprint: {np.mean(vals):.2f} ft/s, range {min(vals):.1f}-{max(vals):.1f}")
trend_counts = {}
for v in career_sprint.values():
    trend_counts[v["trend"]] = trend_counts.get(v["trend"],0) + 1
print(f"Trend distribution: {trend_counts}")

Path("data/hitter_career_sprint.json").write_text(json.dumps(career_sprint, indent=2))
print("Saved: data/hitter_career_sprint.json")
