"""
fetch_pitcher_stats.py
Pulls current-season pitcher Statcast data from Baseball Savant and pitching
stats from FanGraphs. Saves both to disk for process_pitcher_stats.py to consume.

Outputs:
  pitchers_statcast.csv  — pitch-level Statcast data (one row per pitch)
  pitchers_fangraphs.csv — FanGraphs per-pitcher stats (ERA, FIP, xFIP, LOB%, etc.)
"""

import os
from datetime import date, timedelta

try:
    import pandas as pd
    from pybaseball import statcast, pitching_stats
    from pybaseball import cache
except ImportError as e:
    raise SystemExit(
        f"Missing dependency: {e}\n"
        "Install with:  pip install pybaseball pandas"
    )

# Enable pybaseball's local cache so repeat runs don't re-download everything
cache.enable()

# ---------------------------------------------------------------------------
# Season date range — same as fetch_stats.py; pybaseball cache means no
# extra download time when both scripts are run in the same session.
# ---------------------------------------------------------------------------
SEASON_START = date(2026, 3, 26)
SEASON_END   = date.today()
SEASON_YEAR  = SEASON_START.year

OUTPUT_DIR     = os.path.dirname(os.path.abspath(__file__))
STATCAST_PATH  = os.path.join(OUTPUT_DIR, "pitchers_statcast.csv")
FANGRAPHS_PATH = os.path.join(OUTPUT_DIR, "pitchers_fangraphs.csv")


# ---------------------------------------------------------------------------
# Statcast pull
# ---------------------------------------------------------------------------

def fetch_pitcher_statcast(start: date, end: date) -> pd.DataFrame:
    """Return pitch-level Statcast rows for all pitchers between start and end."""
    print(f"Fetching Statcast data from {start} to {end} …")
    df = statcast(
        start_dt=start.strftime("%Y-%m-%d"),
        end_dt=end.strftime("%Y-%m-%d"),
    )

    if df is None or df.empty:
        raise ValueError(
            "No data returned — the season may not have started yet "
            "or the date range is invalid."
        )

    print(f"  Raw rows fetched: {len(df):,}")

    pitcher_cols = [
        # Identifiers
        "game_date", "game_pk", "at_bat_number", "pitch_number",
        "pitcher", "p_throws",
        "batter", "stand",
        "home_team", "away_team", "inning", "inning_topbot",
        # Pitch metrics
        "pitch_type", "pitch_name", "release_speed", "release_spin_rate",
        "release_extension", "pfx_x", "pfx_z", "plate_x", "plate_z",
        "effective_speed", "spin_axis",
        # Outcome
        "events", "description", "zone",
        "type",       # B/S/X
        "bb_type",    # batted ball type
        # Batted-ball metrics
        "launch_speed", "launch_angle", "launch_speed_angle",
        "hit_distance_sc",
        "estimated_ba_using_speedangle",
        "estimated_woba_using_speedangle",  # null for HR — see process script
        "woba_value", "woba_denom",
        "babip_value",
        # Context
        "balls", "strikes", "outs_when_up",
        "on_1b", "on_2b", "on_3b",
        "bat_score", "fld_score",
        "delta_home_win_exp", "delta_run_exp",
    ]

    # Drop any columns absent from this pull (API surface can vary slightly)
    pitcher_cols = [c for c in pitcher_cols if c in df.columns]
    df = df[pitcher_cols].copy()

    df["game_date"] = pd.to_datetime(df["game_date"]).dt.date

    df.sort_values(
        ["game_date", "game_pk", "at_bat_number", "pitch_number"],
        inplace=True,
    )
    df.reset_index(drop=True, inplace=True)

    return df


# ---------------------------------------------------------------------------
# FanGraphs pull
# ---------------------------------------------------------------------------

def fetch_fangraphs_pitching(year: int) -> pd.DataFrame:
    """
    Pull FanGraphs pitching leaderboard for the given season.

    Key notes:
      - qual=0 returns all pitchers, not just qualified ones; we apply our
        own 10-IP filter in process_pitcher_stats.py.
      - FanGraphs pitcher ID column is 'IDfg' (not 'playerid').
      - Rate columns (LOB%, SwStr%, HR/FB, K%, BB%) are returned as 0-1
        decimals by pybaseball (e.g. 0.752 = 75.2% LOB).
      - IP uses baseball notation: 9.2 means 9 and 2/3 innings (29 outs).
    """
    print(f"Fetching FanGraphs pitching stats for {year} …")
    df = pitching_stats(year, year, qual=0)

    if df is None or df.empty:
        raise ValueError(f"No FanGraphs pitching data returned for {year}.")

    print(f"  Pitchers fetched: {len(df):,}")

    # Strip any accidental whitespace from column headers
    df.columns = [c.strip() for c in df.columns]

    keep = [
        "Name", "Team", "IDfg",   # IDfg is the FanGraphs player ID for joins
        "G", "GS", "IP", "TBF",
        "ERA", "FIP", "xFIP",
        "LOB%",    # strand rate (0-1 decimal)
        "SwStr%",  # swinging-strike rate (0-1 decimal)
        "HR/FB",   # HR per fly ball (0-1 decimal)
        "K%", "BB%",
    ]
    keep = [c for c in keep if c in df.columns]
    df = df[keep].copy()

    return df


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if SEASON_END < SEASON_START:
        raise SystemExit(
            f"SEASON_END ({SEASON_END}) is before SEASON_START ({SEASON_START}). "
            "Check the date constants at the top of this script."
        )

    # --- Statcast ---
    sc_df = fetch_pitcher_statcast(SEASON_START, SEASON_END)
    print(f"Saving {len(sc_df):,} rows to {STATCAST_PATH} …")
    sc_df.to_csv(STATCAST_PATH, index=False)
    print(f"  Date range     : {sc_df['game_date'].min()} to {sc_df['game_date'].max()}")
    print(f"  Unique pitchers: {sc_df['pitcher'].nunique():,}")
    print(f"  Unique games   : {sc_df['game_pk'].nunique():,}")

    # --- FanGraphs (optional — pipeline continues if blocked) ---
    try:
        fg_df = fetch_fangraphs_pitching(SEASON_YEAR)
        print(f"Saving {len(fg_df):,} rows to {FANGRAPHS_PATH} …")
        fg_df.to_csv(FANGRAPHS_PATH, index=False)
    except Exception as exc:
        print(f"  WARNING: FanGraphs fetch failed ({exc})")
        print("  Saving empty FanGraphs file — Statcast fallbacks will be used in processing.")
        pd.DataFrame().to_csv(FANGRAPHS_PATH, index=False)
    print("Done.")


if __name__ == "__main__":
    main()
