"""
lineup_context.py
Computes lineup-context multipliers for R and RBI projections.

  r_mult   — adjusts rest-of-season R projection; driven by SLG of batters behind
  rbi_mult — adjusts RBI projection; driven by OBP of batters ahead

Both multipliers are capped at [0.80, 1.20].
Returns (1.0, 1.0) for unknown players or missing team data.

Usage:
    from lineup_context import compute_lineup_multipliers
    r_mult, rbi_mult = compute_lineup_multipliers(mlbam_id=518692, team="LAD")
"""

import json
from functools import lru_cache

SLOT_JSON    = "data/hitter_batting_slot_2026.json"
CONTEXT_JSON = "data/team_lineup_context_2026.json"

# Sensitivity: how much a 1% deviation in lineup quality moves the multiplier
# Backtest-validated against 2025 actuals (n=141): R=0.8 best, RBI=1.2 best
R_SENSITIVITY   = 0.8   # SLG of batters behind → R scoring opportunity
RBI_SENSITIVITY = 1.2   # OBP of batters ahead  → runners on base

MULT_MIN = 0.80
MULT_MAX = 1.20

# Offsets and weights for batters *behind* this player (drive him in → R)
# offset 1 = next batter in order, etc. (cyclic)
R_OFFSETS: dict[int, float] = {1: 0.35, 2: 0.25, 3: 0.20, 4: 0.20}

# Offsets and weights for batters *ahead* of this player (get on base → RBI)
# offset 1 = batter directly before, etc. (cyclic backward)
RBI_OFFSETS: dict[int, float] = {1: 0.40, 2: 0.35, 3: 0.25}

# Minimum PA threshold before trusting a team/slot OBP or SLG estimate
MIN_PA = 10


@lru_cache(maxsize=1)
def _slots() -> dict:
    with open(SLOT_JSON) as f:
        return json.load(f)


@lru_cache(maxsize=1)
def _context() -> dict:
    with open(CONTEXT_JSON) as f:
        return json.load(f)


def _cyclic(slot: int, offset: int) -> int:
    """Return slot shifted by offset, wrapping 1-9."""
    return ((slot - 1 + offset) % 9) + 1


def _get_obp(team: str, slot: int) -> float:
    ctx = _context()
    d = ctx.get(team, {}).get(str(slot), {})
    if d.get("pa", 0) >= MIN_PA and d.get("obp", 0) > 0:
        return d["obp"]
    lg = ctx.get("_league_avg", {})
    return lg.get("obp", 0.320)


def _get_slg(team: str, slot: int) -> float:
    ctx = _context()
    d = ctx.get(team, {}).get(str(slot), {})
    if d.get("pa", 0) >= MIN_PA and d.get("slg", 0) > 0:
        return d["slg"]
    lg = ctx.get("_league_avg", {})
    return lg.get("slg", 0.410)


def compute_lineup_multipliers(mlbam_id: int, team: str) -> tuple[float, float]:
    """Return (r_mult, rbi_mult) for a player.

    Parameters
    ----------
    mlbam_id : int   MLBAM player ID
    team     : str   Three-letter team abbreviation (e.g. "LAD")

    Returns
    -------
    (r_mult, rbi_mult) — both in [0.80, 1.20], default (1.0, 1.0) if unknown
    """
    slots = _slots()
    ctx   = _context()

    player = slots.get(str(mlbam_id))
    if player is None:
        return 1.0, 1.0

    slot   = player["slot"]
    lg_obp = ctx.get("_league_avg", {}).get("obp", 0.320)
    lg_slg = ctx.get("_league_avg", {}).get("slg", 0.410)

    # R multiplier — SLG of batters who come after this player in the order
    weighted_slg = sum(
        w * _get_slg(team, _cyclic(slot, off))
        for off, w in R_OFFSETS.items()
    )
    r_raw  = 1.0 + R_SENSITIVITY * (weighted_slg / lg_slg - 1.0)
    r_mult = round(min(MULT_MAX, max(MULT_MIN, r_raw)), 4)

    # RBI multiplier — OBP of batters who bat before this player
    weighted_obp = sum(
        w * _get_obp(team, _cyclic(slot, -off))
        for off, w in RBI_OFFSETS.items()
    )
    rbi_raw  = 1.0 + RBI_SENSITIVITY * (weighted_obp / lg_obp - 1.0)
    rbi_mult = round(min(MULT_MAX, max(MULT_MIN, rbi_raw)), 4)

    return r_mult, rbi_mult


if __name__ == "__main__":
    # Quick spot-check table — run after build_lineup_context.py
    CHECKS = [
        ("Freddie Freeman (LAD 4/5)",  518692, "LAD"),
        ("Mookie Betts — leadoff LAD",  605141, "LAD"),
        ("Aaron Judge (NYY cleanup)",   592450, "NYY"),
        ("CWS bottom order (Burger)",   669394, "CWS"),
        ("ATH bottom order (Rooker)",   669093, "ATH"),
    ]
    print(f"{'Player':<35} {'slot':>4} {'R_mult':>7} {'RBI_mult':>9}")
    print("-" * 58)
    slots = _slots()
    for label, bid, team in CHECKS:
        rm, xm = compute_lineup_multipliers(bid, team)
        slot_info = slots.get(str(bid), {})
        slot = slot_info.get("slot", "?")
        print(f"{label:<35} {str(slot):>4} {rm:>7.4f} {xm:>9.4f}")
