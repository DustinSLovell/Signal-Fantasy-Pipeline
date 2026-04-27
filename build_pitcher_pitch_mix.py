"""
build_pitcher_pitch_mix.py
Builds pitcher pitch mix baselines and computes current-season pitch mix.
Enriches pitcher_luck_scores.csv with evolution-detection columns.

Historical baseline source:
  data/pitcher_arsenal_2025.csv   — 2025 per-pitch-type: usage, whiff%
  data/pitcher_career_stuff.json  — career SwStr%, FB velo (2022-2025)

Current source:
  pitchers_statcast.csv           — 2026 season pitch-by-pitch

Outputs:
  data/pitcher_career_pitch_mix.json  — 2025 per-pitch-type career baseline
  data/pitcher_current_pitch_mix.json — 2026 current per-pitch-type mix
  pitcher_luck_scores.csv             — enriched with 9 evolution columns

Usage:
  python build_pitcher_pitch_mix.py
"""

import json
from pathlib import Path

import pandas as pd

BASE_DIR     = Path(__file__).parent
ARSENAL_CSV  = BASE_DIR / "data" / "pitcher_arsenal_2025.csv"
STUFF_JSON   = BASE_DIR / "data" / "pitcher_career_stuff.json"
STATCAST_CSV = BASE_DIR / "pitchers_statcast.csv"
LUCK_CSV     = BASE_DIR / "pitcher_luck_scores.csv"
OUT_CAREER   = BASE_DIR / "data" / "pitcher_career_pitch_mix.json"
OUT_CURRENT  = BASE_DIR / "data" / "pitcher_current_pitch_mix.json"

# Minimum pitch counts for inclusion
MIN_CAREER_PITCHES = 100   # per pitch type in 2025 arsenal (already filtered by file)
MIN_CURR_PITCHES   = 50    # per pitcher total in 2026

# Swinging strike description codes
SWSTR_DESCS = {"swinging_strike", "swinging_strike_blocked"}


# ---------------------------------------------------------------------------
# Build career baseline from pitcher_arsenal_2025.csv + pitcher_career_stuff
# ---------------------------------------------------------------------------

def build_career_pitch_mix() -> dict:
    """Build per-pitcher career pitch mix from 2025 arsenal data."""
    if not ARSENAL_CSV.exists():
        print(f"  WARNING: {ARSENAL_CSV} not found — career pitch mix unavailable")
        return {}

    ar = pd.read_csv(ARSENAL_CSV)
    # Rename the awkward first column
    name_col = ar.columns[0]   # 'last_name, first_name'
    ar = ar.rename(columns={name_col: "player_name"})

    # Load career stuff for overall swstr/velo
    career_stuff: dict = {}
    if STUFF_JSON.exists():
        career_stuff = json.loads(STUFF_JSON.read_text(encoding="utf-8"))

    result = {}
    for pid, grp in ar.groupby("player_id"):
        pid = int(pid)
        name = str(grp["player_name"].iloc[0])

        pitch_types  = grp["pitch_type"].tolist()
        career_usage = {}
        career_swstr = {}
        total_pitches = 0

        for _, row in grp.iterrows():
            pt = str(row["pitch_type"])
            usage   = float(row["pitch_usage"]) / 100.0   # convert % to fraction
            whiff   = float(row["whiff_percent"]) / 100.0 if pd.notna(row["whiff_percent"]) else float("nan")
            pitches = int(row["pitches"]) if pd.notna(row["pitches"]) else 0

            career_usage[pt] = round(usage, 4)
            if whiff == whiff:   # not nan
                career_swstr[pt] = round(whiff, 4)
            total_pitches += pitches

        # Overall SwStr and velo from career stuff JSON (multi-year 2022-2025)
        stuff = career_stuff.get(str(pid), {})
        career_swstr_overall = stuff.get("career_swstr_pct", float("nan"))
        career_fb_velo       = stuff.get("career_fb_velo",   float("nan"))
        n_seasons            = stuff.get("n_seasons", 1)

        result[pid] = {
            "name":                 name,
            "career_pitch_types":   pitch_types,
            "career_usage":         career_usage,
            "career_swstr":         career_swstr,
            "career_swstr_overall": career_swstr_overall,
            "career_primary_velo":  career_fb_velo,
            "n_seasons":            n_seasons,
            "career_pitches":       total_pitches,
        }

    return result


# ---------------------------------------------------------------------------
# Compute current 2026 pitch mix from pitchers_statcast.csv
# ---------------------------------------------------------------------------

def build_current_pitch_mix() -> dict:
    """Build per-pitcher current 2026 pitch mix from Statcast data."""
    if not STATCAST_CSV.exists():
        print(f"  WARNING: {STATCAST_CSV} not found — current pitch mix unavailable")
        return {}

    sc = pd.read_csv(STATCAST_CSV, usecols=[
        "pitcher", "pitch_type", "release_speed", "description"
    ])
    sc = sc.dropna(subset=["pitcher", "pitch_type"])
    sc["is_swstr"] = sc["description"].isin(SWSTR_DESCS).astype(int)

    result = {}
    for pid, grp in sc.groupby("pitcher"):
        pid = int(pid)
        total = len(grp)
        if total < MIN_CURR_PITCHES:
            continue

        curr_usage  = {}
        curr_swstr  = {}
        curr_velo   = {}
        pitch_counts = grp["pitch_type"].value_counts()

        for pt, count in pitch_counts.items():
            pt = str(pt)
            sub = grp[grp["pitch_type"] == pt]
            curr_usage[pt]  = round(count / total, 4)
            curr_swstr[pt]  = round(sub["is_swstr"].mean(), 4)
            velo_vals = sub["release_speed"].dropna()
            curr_velo[pt]   = round(float(velo_vals.mean()), 1) if len(velo_vals) > 0 else float("nan")

        # Overall current swstr
        curr_swstr_overall = round(float(grp["is_swstr"].mean()), 4)

        # Primary pitch = highest usage
        primary_pt = max(curr_usage, key=curr_usage.get)
        curr_primary_velo = curr_velo.get(primary_pt, float("nan"))

        # Also compute FB velo (FF or SI) for comparison with career_stuff fb_velo
        fb_types = {"FF", "SI", "FA"}
        fb_velo_vals = []
        for pt in fb_types:
            if pt in curr_velo and curr_velo[pt] == curr_velo[pt]:
                n = int(pitch_counts.get(pt, 0))
                fb_velo_vals.extend([curr_velo[pt]] * n)
        curr_fb_velo = round(sum(fb_velo_vals) / len(fb_velo_vals), 1) if fb_velo_vals else float("nan")

        result[pid] = {
            "curr_pitch_types":    list(curr_usage.keys()),
            "curr_usage":          curr_usage,
            "curr_swstr":          curr_swstr,
            "curr_velo":           curr_velo,
            "curr_swstr_overall":  curr_swstr_overall,
            "curr_primary_velo":   curr_primary_velo,
            "curr_fb_velo":        curr_fb_velo,
            "total_pitches_2026":  total,
        }

    return result


# ---------------------------------------------------------------------------
# Compute new/dropped pitches and gaps
# ---------------------------------------------------------------------------

def _pitch_evolution_cols(pid: int, career: dict, current: dict) -> dict:
    """Return evolution column values for one pitcher."""
    car = career.get(pid, {})
    cur = current.get(pid, {})

    career_types = set(car.get("career_pitch_types", []))
    curr_types   = set(cur.get("curr_pitch_types",   []))

    new_pitches     = sorted(curr_types - career_types)
    dropped_pitches = sorted(career_types - curr_types)

    curr_swstr_overall  = cur.get("curr_swstr_overall",  float("nan"))
    career_swstr_overall = car.get("career_swstr_overall", float("nan"))
    if curr_swstr_overall == curr_swstr_overall and career_swstr_overall == career_swstr_overall:
        swstr_gap = round(curr_swstr_overall - career_swstr_overall, 4)
    else:
        swstr_gap = float("nan")

    curr_primary_velo  = cur.get("curr_fb_velo",         float("nan"))
    career_primary_velo = car.get("career_primary_velo", float("nan"))
    if curr_primary_velo == curr_primary_velo and career_primary_velo == career_primary_velo:
        velo_gap = round(curr_primary_velo - career_primary_velo, 2)
    else:
        velo_gap = float("nan")

    return {
        "curr_pitch_types":     ",".join(sorted(curr_types)) if curr_types else "",
        "new_pitches":          ",".join(new_pitches),
        "dropped_pitches":      ",".join(dropped_pitches),
        "curr_swstr_overall":   curr_swstr_overall,
        "career_swstr_overall": career_swstr_overall,
        "swstr_gap":            swstr_gap,
        "curr_primary_velo":    curr_primary_velo,
        "career_primary_velo":  career_primary_velo,
        "velo_gap":             velo_gap,
    }


# ---------------------------------------------------------------------------
# Enrich pitcher_luck_scores.csv
# ---------------------------------------------------------------------------

def enrich_luck_scores(career: dict, current: dict) -> int:
    """Add evolution columns to pitcher_luck_scores.csv. Returns row count."""
    if not LUCK_CSV.exists():
        print(f"  WARNING: {LUCK_CSV} not found — skipping enrichment")
        return 0

    df = pd.read_csv(LUCK_CSV)
    new_col_names = [
        "curr_pitch_types", "new_pitches", "dropped_pitches",
        "curr_swstr_overall", "career_swstr_overall", "swstr_gap",
        "curr_primary_velo", "career_primary_velo", "velo_gap",
    ]
    # Drop old versions of these columns if present (idempotent)
    df = df.drop(columns=[c for c in new_col_names if c in df.columns], errors="ignore")

    rows = []
    for _, r in df.iterrows():
        pid = int(r.get("pitcher", 0))
        cols = _pitch_evolution_cols(pid, career, current)
        rows.append(cols)

    for col in new_col_names:
        df[col] = [row[col] for row in rows]

    df.to_csv(LUCK_CSV, index=False)
    return len(df)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("Building pitcher pitch mix baselines...")

    career  = build_career_pitch_mix()
    current = build_current_pitch_mix()

    # Save JSONs
    OUT_CAREER.parent.mkdir(exist_ok=True)
    OUT_CAREER.write_text(
        json.dumps(career,  indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    OUT_CURRENT.write_text(
        json.dumps(current, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"  Career pitch mix:  {len(career):,} pitchers -> {OUT_CAREER.name}")
    print(f"  Current pitch mix: {len(current):,} pitchers -> {OUT_CURRENT.name}")

    # Report coverage
    if LUCK_CSV.exists():
        import pandas as pd
        luck_ids = set(pd.read_csv(LUCK_CSV)["pitcher"].tolist())
        career_ids  = set(career.keys())
        current_ids = set(current.keys())
        print(f"  Coverage vs luck_scores.csv ({len(luck_ids)} pitchers):")
        print(f"    Career baseline:  {len(luck_ids & career_ids):,} matched "
              f"({len(luck_ids & career_ids)/len(luck_ids)*100:.0f}%)")
        print(f"    Current mix:      {len(luck_ids & current_ids):,} matched "
              f"({len(luck_ids & current_ids)/len(luck_ids)*100:.0f}%)")

    # Report pitch type stats
    if career:
        n_types = [len(v["career_pitch_types"]) for v in career.values()]
        print(f"  Mean career pitch types per pitcher: {sum(n_types)/len(n_types):.1f}")

    # Enrich luck scores CSV
    n_rows = enrich_luck_scores(career, current)
    print(f"  Enriched pitcher_luck_scores.csv ({n_rows} rows) with 9 evolution columns")


if __name__ == "__main__":
    main()
