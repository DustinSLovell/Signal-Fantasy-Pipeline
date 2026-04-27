"""
fetch_stats.py
Pulls current-season hitter Statcast data from Baseball Savant via pybaseball
and saves it to hitters_statcast.csv.
"""

import os
from datetime import date, timedelta

try:
    import pandas as pd
    from pybaseball import statcast
    from pybaseball import cache
except ImportError as e:
    raise SystemExit(
        f"Missing dependency: {e}\n"
        "Install with:  pip install pybaseball pandas"
    )

# Enable pybaseball's local cache so repeat runs don't re-download everything
cache.enable()

# ---------------------------------------------------------------------------
# Season date range
# Adjust SEASON_START if needed (2026 Opening Day was March 27 2026).
# SEASON_END defaults to yesterday so we only request data that exists.
# ---------------------------------------------------------------------------
SEASON_START = date(2026, 3, 27)
SEASON_END = date.today() - timedelta(days=1)

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.join(OUTPUT_DIR, "hitters_statcast.csv")


def fetch_hitter_statcast(start: date, end: date) -> pd.DataFrame:
    """Return pitch-level Statcast rows for all batters between start and end."""
    print(f"Fetching Statcast data from {start} to {end} …")
    df = statcast(
        start_dt=start.strftime("%Y-%m-%d"),
        end_dt=end.strftime("%Y-%m-%d"),
    )

    if df is None or df.empty:
        raise ValueError("No data returned — the season may not have started yet "
                         "or the date range is invalid.")

    print(f"  Raw rows fetched: {len(df):,}")

    # ------------------------------------------------------------------
    # Keep only batter-relevant columns and rows where a plate appearance
    # outcome exists (filters out mid-PA pitches with no result recorded
    # for the batter beyond the pitch itself is fine to keep — Statcast
    # is pitch-level, so every row has batter context).
    # ------------------------------------------------------------------
    batter_cols = [
        # Identifiers
        "game_date", "game_pk", "at_bat_number", "pitch_number",
        "batter", "batter_name" if "batter_name" in df.columns else None,
        "stand",        # batter handedness
        "pitcher",
        "p_throws",     # pitcher handedness
        "home_team", "away_team", "inning", "inning_topbot",
        # Pitch info
        "pitch_type", "pitch_name", "release_speed", "release_spin_rate",
        "release_extension", "release_pos_x", "release_pos_z",
        "pfx_x", "pfx_z", "plate_x", "plate_z",
        "effective_speed", "spin_axis",
        # Outcome
        "events", "description", "zone",
        "type",         # B/S/X
        "bb_type",      # batted ball type
        # Batted-ball metrics
        "launch_speed", "launch_angle", "launch_speed_angle",
        "hc_x", "hc_y",
        "hit_distance_sc",
        "estimated_ba_using_speedangle",
        "estimated_woba_using_speedangle",
        "woba_value", "woba_denom",
        "babip_value",
        "iso_value",
        # Context
        "balls", "strikes", "outs_when_up",
        "on_1b", "on_2b", "on_3b",
        "bat_score", "fld_score",
        "if_fielding_alignment", "of_fielding_alignment",
        # Statcast extras
        "delta_home_win_exp", "delta_run_exp",
    ]

    # Drop any columns that don't exist in this pull (API can vary slightly)
    batter_cols = [c for c in batter_cols if c and c in df.columns]
    df = df[batter_cols].copy()

    # Normalise game_date to a proper date type
    df["game_date"] = pd.to_datetime(df["game_date"]).dt.date

    # Sort chronologically
    df.sort_values(["game_date", "game_pk", "at_bat_number", "pitch_number"],
                   inplace=True)
    df.reset_index(drop=True, inplace=True)

    return df


def main():
    if SEASON_END < SEASON_START:
        raise SystemExit(
            f"SEASON_END ({SEASON_END}) is before SEASON_START ({SEASON_START}). "
            "Check the date constants at the top of this script."
        )

    df = fetch_hitter_statcast(SEASON_START, SEASON_END)

    print(f"Saving {len(df):,} rows to {OUTPUT_PATH} …")
    df.to_csv(OUTPUT_PATH, index=False)
    print("Done.")
    print(f"\nDate range covered : {df['game_date'].min()} to {df['game_date'].max()}")
    print(f"Unique batters      : {df['batter'].nunique():,}")
    print(f"Unique games        : {df['game_pk'].nunique():,}")


if __name__ == "__main__":
    main()
