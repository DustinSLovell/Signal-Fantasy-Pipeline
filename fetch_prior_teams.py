"""
fetch_prior_teams.py
Fetches 2025 team assignments for all hitters and pitchers from Baseball Savant
Statcast data and saves to data/prior_teams_2025.json.

Used by score_luck.py and score_pitcher_luck.py to detect park changes between
a player's 2025 context and their current 2026 team. When park factor delta > 0.03,
the seasonal pattern signal is reduced by 50% (career baseline less reliable).

Usage:
    python fetch_prior_teams.py
"""

import json
import os
from datetime import date
from pathlib import Path

import pandas as pd

try:
    from pybaseball import statcast
    from pybaseball import cache as pb_cache
    pb_cache.enable()
except ImportError:
    raise SystemExit("Missing dependency: pip install pybaseball pandas")

BASE_DIR  = Path(__file__).parent
OUT_PATH  = BASE_DIR / "data" / "prior_teams_2025.json"

# Pull a mid-season window from 2025 — good team coverage, minimal splits
SAMPLE_START = "2025-06-01"
SAMPLE_END   = "2025-06-30"

# Team abbreviation normalization — Baseball Savant uses different codes in some years
_TEAM_ALIASES = {
    "ANA": "LAA",
    "FLA": "MIA",
    "MON": "WSH",
}


def _normalize_team(t: str) -> str:
    return _TEAM_ALIASES.get(str(t).upper(), str(t).upper())


def _derive_batter_teams(df: pd.DataFrame) -> dict:
    """Returns {batter_id (int): team_abbr (str)}."""
    sc = df.dropna(subset=["batter", "home_team", "away_team", "inning_topbot"])
    sc = sc.copy()
    sc["batter_team"] = sc.apply(
        lambda r: r["home_team"] if r["inning_topbot"] == "Bot" else r["away_team"],
        axis=1,
    )
    teams = (
        sc.groupby("batter")["batter_team"]
        .agg(lambda x: x.mode()[0])
    )
    return {int(k): _normalize_team(v) for k, v in teams.items()}


def _derive_pitcher_teams(df: pd.DataFrame) -> dict:
    """Returns {pitcher_id (int): team_abbr (str)}."""
    sc = df.dropna(subset=["pitcher", "home_team", "away_team", "inning_topbot"])
    sc = sc.copy()
    sc["pitcher_team"] = sc.apply(
        lambda r: r["home_team"] if r["inning_topbot"] == "Top" else r["away_team"],
        axis=1,
    )
    teams = (
        sc.groupby("pitcher")["pitcher_team"]
        .agg(lambda x: x.mode()[0])
    )
    return {int(k): _normalize_team(v) for k, v in teams.items()}


def main() -> None:
    print(f"Fetching 2025 Statcast data ({SAMPLE_START} to {SAMPLE_END})...")
    df = statcast(start_dt=SAMPLE_START, end_dt=SAMPLE_END)

    if df is None or df.empty:
        raise SystemExit("No data returned from Baseball Savant.")

    print(f"  {len(df):,} pitches fetched")

    batter_teams  = _derive_batter_teams(df)
    pitcher_teams = _derive_pitcher_teams(df)

    # Merge: batter entries take precedence, pitcher entries fill remaining slots
    combined: dict[str, str] = {}
    for pid, team in pitcher_teams.items():
        combined[str(pid)] = team
    for pid, team in batter_teams.items():
        combined[str(pid)] = team   # overwrite if same player plays both roles

    combined["_comment"]   = "MLBAM player ID -> 2025 team (mid-season June snapshot)"
    combined["_populated"] = True
    combined["_fetched"]   = date.today().isoformat()
    combined["_n_players"] = len(combined) - 3  # exclude meta keys

    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text(json.dumps(combined, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"  {len(batter_teams):,} batter teams + {len(pitcher_teams):,} pitcher teams")
    print(f"  {len(combined) - 3:,} total entries -> {OUT_PATH.name}")


if __name__ == "__main__":
    main()
