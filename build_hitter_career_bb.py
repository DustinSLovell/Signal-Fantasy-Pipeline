"""
Build hitter career BB% baseline from Steamer 2025 projections.
Output: data/hitter_career_bb.json  →  {mlbam_id: career_bb_pct}

Steamer BB% is the best career-talent-level walk rate anchor:
  - Calibrated on full career history, not just April sample
  - Already used by pipeline for SB, PA, and IP projections
  - Covers ~4,140 players (all MLB-rostered + notable MiLB)

Used in score_value.py:  PA-weighted blend toward career walk rate
  when |april_bb_pct - career_bb_pct| > 0.020.
"""

import json
import os

import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STEAMER_PATH = os.path.join(BASE_DIR, "Steamers 2025 batters.csv")
OUTPUT_PATH  = os.path.join(BASE_DIR, "data", "hitter_career_bb.json")

BB_MIN = 0.00
BB_MAX = 0.30   # 30% BB rate is a hard ceiling (even the most patient hitters top ~20%)


def build_career_bb() -> dict:
    df = pd.read_csv(STEAMER_PATH, usecols=["MLBAMID", "BB%"])
    result = {}
    for _, row in df.iterrows():
        try:
            mid = int(float(row["MLBAMID"]))
            bb  = float(row["BB%"])
        except (ValueError, TypeError):
            continue
        if BB_MIN <= bb <= BB_MAX:
            result[mid] = round(bb, 4)
    return result


if __name__ == "__main__":
    if not os.path.exists(STEAMER_PATH):
        print(f"ERROR: Steamer CSV not found at {STEAMER_PATH}")
        raise SystemExit(1)

    career_bb = build_career_bb()
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(career_bb, f)
    print(f"Saved {len(career_bb):,} entries  →  {OUTPUT_PATH}")

    # Sanity checks against known players
    test_cases = [
        (607208, "Trea Turner",     "exp ~0.061"),
        (663728, "Willy Adames",    "exp ~0.103"),
        (660271, "Shohei Ohtani",   "exp ~0.085"),
        (665487, "Gary Sanchez",    "exp ~0.090"),
        (518626, "Brandon Marsh",   "exp ~0.102"),
    ]
    print("\nSanity checks:")
    for mid, name, note in test_cases:
        val = career_bb.get(mid, "MISSING")
        print(f"  {name:20s} ({note}): {val}")
