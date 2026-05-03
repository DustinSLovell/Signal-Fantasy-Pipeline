"""
generate_projections.py
Generates data/projections_2026.csv — one row per player (hitters + pitchers).
Called by run_pipeline.py after score_luck.py and score_pitcher_luck.py.

Usage:
    python generate_projections.py
"""

import sys
from pathlib import Path
from datetime import date

import pandas as pd

BASE_DIR = Path(__file__).parent
OUT_PATH = BASE_DIR / "data" / "projections_2026.csv"

# Output columns
COLUMNS = [
    "name", "team", "type", "signal", "luck_score",
    "proj_avg", "proj_hr", "proj_r", "proj_rbi", "proj_sb",
    "proj_era", "proj_whip", "proj_k", "proj_w", "proj_sv_h", "proj_ip",
    "confidence", "games_remaining", "generated_date", "pf_adj_applied",
    "steamer_pt_override",
]


def main() -> None:
    print("Generating player projections...")

    from stat_projections import _get_cache, project_player, load_all_career_data

    cache   = _get_cache()
    hitters = cache["hitters"]
    pitchers = cache["pitchers"]
    career  = load_all_career_data()
    sprint  = career.get("sprint", {})

    rows = []
    total = len(hitters) + len(pitchers)
    n_warn = 0
    today  = date.today().isoformat()

    # Hitters
    for _, hrow in hitters.iterrows():
        name = str(hrow.get("name", ""))
        if not name:
            continue
        proj = project_player(name, hitters, pitchers, career, sprint)
        if "error" in proj:
            continue
        ps = proj["projected_stats"]
        warnings = proj.get("sanity_warnings", [])
        n_warn += len(warnings)
        rows.append({
            "name":            proj["name"],
            "team":            proj["team"],
            "type":            "hitter",
            "signal":          proj["signal"],
            "luck_score":      proj["luck_score"],
            "proj_avg":        ps.get("projected_avg"),
            "proj_hr":         ps.get("projected_hr"),
            "proj_r":          ps.get("projected_r"),
            "proj_rbi":        ps.get("projected_rbi"),
            "proj_sb":         ps.get("projected_sb"),
            "proj_era":        None,
            "proj_whip":       None,
            "proj_k":          None,
            "proj_w":          None,
            "proj_sv_h":       None,
            "proj_ip":         None,
            "confidence":      proj["confidence"],
            "games_remaining": proj["games_remaining"],
            "generated_date":  today,
            "pf_adj_applied":  ps.get("pf_adj_applied", False),
            "steamer_pt_override": ps.get("steamer_pt_override", False),
        })

    # Pitchers
    for _, prow in pitchers.iterrows():
        name = str(prow.get("name", ""))
        if not name:
            continue
        proj = project_player(name, hitters, pitchers, career, sprint)
        if "error" in proj:
            continue
        ps = proj["projected_stats"]
        warnings = proj.get("sanity_warnings", [])
        n_warn += len(warnings)
        rows.append({
            "name":            proj["name"],
            "team":            proj["team"],
            "type":            "pitcher",
            "signal":          proj["signal"],
            "luck_score":      proj["luck_score"],
            "proj_avg":        None,
            "proj_hr":         None,
            "proj_r":          None,
            "proj_rbi":        None,
            "proj_sb":         None,
            "proj_era":        ps.get("projected_era"),
            "proj_whip":       ps.get("projected_whip"),
            "proj_k":          ps.get("projected_k"),
            "proj_w":          ps.get("projected_w"),
            "proj_sv_h":       ps.get("projected_sv_h"),
            "proj_ip":         ps.get("projected_ip"),
            "confidence":      proj["confidence"],
            "games_remaining": proj["games_remaining"],
            "generated_date":  today,
            "pf_adj_applied":  False,
            "steamer_pt_override": False,
        })

    df = pd.DataFrame(rows, columns=COLUMNS)
    OUT_PATH.parent.mkdir(exist_ok=True)
    df.to_csv(OUT_PATH, index=False)

    n_h = (df["type"] == "hitter").sum()
    n_p = (df["type"] == "pitcher").sum()
    print(f"  Projected {n_h} hitters + {n_p} pitchers = {len(df)} total")
    print(f"  Sanity warnings: {n_warn}")
    print(f"  Saved -> {OUT_PATH.name}")


if __name__ == "__main__":
    main()
