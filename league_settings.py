"""
league_settings.py
==================
Master league settings loader and utilities for The Signal Fantasy trade analyzer.
Supports any 5x5 roto league via JSON schema files in data/leagues/.

Public API:
    load_league(league_id)                    -> dict
    get_replacement_level(league_id, position) -> float
    get_stat_weight(league_id, stat)           -> float

Not wired into trade_analyzer.py yet — schema and loader only.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

BASE_DIR    = Path(__file__).parent
LEAGUES_DIR = BASE_DIR / "data" / "leagues"

# Required top-level keys for validation
_REQUIRED_KEYS = {
    "league_id", "league_name", "platform", "team_count",
    "format", "categories", "saves_holds_ratio",
    "roster_slots", "max_reserves", "stat_weights",
}

_REQUIRED_CAT_KEYS = {"hitting", "pitching"}

# ---------------------------------------------------------------------------
# Base replacement levels at 12-team standard (from replacement_level.py).
# Scaled by team_count / 12 to adjust for league size.
# ---------------------------------------------------------------------------
_BASE_REPLACEMENT_FPTS: dict[str, float] = {
    "C":  289.8,
    "1B": 275.7,
    "2B": 277.7,
    "3B": 267.0,
    "SS": 293.9,
    "OF": 296.3,
    "SP": 221.5,
    "RP": 157.0,
    # combined slots — use weighted average of component positions
    "MI": 280.0,   # avg 2B/SS
    "CI": 271.0,   # avg 1B/3B
    "UT": 278.0,   # avg all hitter positions
    "P":  195.0,   # avg SP/RP
}

# Roster slots that count toward a position's replacement pool
_POS_SLOT_MAP: dict[str, list[str]] = {
    "C":  ["C"],
    "1B": ["1B", "CI", "UT"],
    "2B": ["2B", "MI", "UT"],
    "3B": ["3B", "CI", "UT"],
    "SS": ["SS", "MI", "UT"],
    "OF": ["OF", "UT"],
    "SP": ["SP", "P"],
    "RP": ["RP", "P"],
}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate(data: dict, league_id: str) -> None:
    missing = _REQUIRED_KEYS - set(data.keys())
    if missing:
        raise ValueError(f"League '{league_id}' missing required keys: {missing}")

    if not isinstance(data["categories"], dict):
        raise ValueError(f"League '{league_id}': 'categories' must be a dict")
    missing_cat = _REQUIRED_CAT_KEYS - set(data["categories"].keys())
    if missing_cat:
        raise ValueError(f"League '{league_id}': 'categories' missing: {missing_cat}")

    if not isinstance(data["team_count"], int) or data["team_count"] < 1:
        raise ValueError(f"League '{league_id}': 'team_count' must be a positive integer")

    if data["format"] not in ("roto", "h2h_cats", "h2h_points"):
        raise ValueError(f"League '{league_id}': unknown format '{data['format']}'")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_league(league_id: str) -> dict:
    """Load and validate a league JSON file. Returns the settings dict."""
    path = LEAGUES_DIR / f"{league_id}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"League file not found: {path}\n"
            f"Available: {[p.stem for p in LEAGUES_DIR.glob('*.json')]}"
        )
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    _validate(data, league_id)
    return data


def get_replacement_level(league_id: str, position: str) -> float:
    """
    Return replacement-level FPTS for a position, adjusted for team count.

    Scales linearly from the 12-team baseline: a 15-team league has
    shallower replacement pools (more players rostered), which means
    replacement-level talent is lower → replacement FPTS increases.

    Args:
        league_id: "league_1", "league_2", etc.
        position:  "C", "1B", "SP", "OF", etc.

    Returns:
        Adjusted replacement-level FPTS (float).
    """
    league   = load_league(league_id)
    n_teams  = league["team_count"]
    slots    = league["roster_slots"]

    pos_upper = position.upper()
    base_fpts = _BASE_REPLACEMENT_FPTS.get(pos_upper)
    if base_fpts is None:
        raise ValueError(f"Unknown position '{position}'. "
                         f"Known: {list(_BASE_REPLACEMENT_FPTS)}")

    # Count how many roster spots this position competes for in the league
    relevant_slots = _POS_SLOT_MAP.get(pos_upper, [pos_upper])
    n_slots = sum(slots.get(s, 0) for s in relevant_slots)

    # Pool size = teams × slots_per_team; ratio vs 12-team baseline
    # 12-team baseline slot counts (standard):
    _baseline_slots = {"C": 2, "1B": 2, "2B": 2, "3B": 2, "SS": 2,
                       "OF": 8, "SP": 6, "RP": 4, "MI": 2, "CI": 2,
                       "UT": 2, "P": 0}
    baseline_n_slots = sum(_baseline_slots.get(s, 1) for s in relevant_slots)

    pool_ratio = (n_teams * n_slots) / max(1, 12 * baseline_n_slots)

    # Deeper pool (ratio > 1) → more players rostered → worse replacement player → FPTS down
    adjusted = base_fpts * (1.10 - 0.10 * pool_ratio)
    return round(adjusted, 1)


def get_stat_weight(league_id: str, stat: str) -> float:
    """
    Return the weight for a stat in this league (1.0 = active, 0.0 = not scored).

    Checks stat_weights dict first (explicit overrides), then checks whether
    the stat appears in the league's hitting or pitching category lists.

    Args:
        league_id: "league_1", "league_2", etc.
        stat:      e.g. "AVG", "OBP", "SV_H", "ERA"

    Returns:
        1.0 if stat is scored in this league, 0.0 if not.
    """
    league = load_league(league_id)

    # Explicit override in stat_weights takes precedence
    weights = league.get("stat_weights", {})
    if stat in weights:
        return float(weights[stat])

    # Check category lists
    all_cats = (league["categories"].get("hitting", []) +
                league["categories"].get("pitching", []))
    return 1.0 if stat in all_cats else 0.0


# ---------------------------------------------------------------------------
# CLI sanity check
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    for lid in ("league_1", "league_2"):
        lg = load_league(lid)
        print(f"\n{'='*55}")
        print(f"  {lg['league_name']}  ({lg['platform']}, {lg['team_count']} teams)")
        print(f"{'='*55}")
        print(f"  Hitting cats : {lg['categories']['hitting']}")
        print(f"  Pitching cats: {lg['categories']['pitching']}")
        print(f"  SV:H ratio   : {lg['saves_holds_ratio']}")
        print(f"  Roster slots : {lg['roster_slots']}")
        print(f"  Reserves     : {lg['max_reserves']}")

        print(f"\n  Stat weights:")
        for stat in ["AVG", "OBP", "SV_H", "ERA", "WHIP", "K", "W"]:
            w = get_stat_weight(lid, stat)
            print(f"    {stat:<8} {w:.1f}")

        print(f"\n  Replacement levels (team_count={lg['team_count']}):")
        for pos in ["C", "1B", "2B", "SS", "OF", "SP", "RP"]:
            try:
                rl = get_replacement_level(lid, pos)
                print(f"    {pos:<4} {rl:.1f} FPTS")
            except Exception as e:
                print(f"    {pos:<4} ERROR: {e}")

    print("\n  Validation test — missing key:")
    try:
        _validate({"league_id": "x"}, "x")
    except ValueError as e:
        print(f"    Caught: {e}")
