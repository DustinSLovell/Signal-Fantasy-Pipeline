"""
replacement_level.py — Positional replacement level for CBS FPTS trade valuation.

Replacement player = Nth-best player at a position where N = roster_spots × league_size.
Surplus value = projected CBS FPTS - replacement level FPTS at that position.

Position pools are built from projections_2026.csv (projected stats) cross-referenced
with player_values.json (fantasy position assignments from score_value.py output).

Two-ruler note: surplus is computed on CBS FPTS scale, not the luck score scale.
It answers "how much value above replacement does this player project?" — a separate
question from the luck model's "how much regression risk does this player carry?"
"""

from pathlib import Path
from typing import Optional

import json
import pandas as pd

from config import (
    CBS_H_COEF_R, CBS_H_COEF_HR, CBS_H_COEF_RBI, CBS_H_COEF_SB,
    CBS_H_COEF_AVG, CBS_H_INTERCEPT,
    CBS_P_COEF_W, CBS_P_COEF_ERA, CBS_P_COEF_WHIP,
    CBS_P_COEF_K, CBS_P_COEF_SV, CBS_P_INTERCEPT,
)

BASE_DIR    = Path(__file__).parent
PROJ_CSV    = BASE_DIR / "data" / "projections_2026.csv"
VALUES_JSON = BASE_DIR / "data" / "player_values.json"

# Raw MLB/CBS position → fantasy roster slot
# Multi-position eligibility is not modeled here; primary position only.
FANTASY_POS_MAP: dict[str, str] = {
    "C":  "C",
    "1B": "1B", "DH": "1B",
    "2B": "2B", "IF": "2B",
    "3B": "3B",
    "SS": "SS",
    "LF": "OF", "RF": "OF", "CF": "OF", "OF": "OF",
    "SP": "SP",
    "RP": "RP",
}

# N = total starter slots across a 12-team standard CBS league.
# Includes main slots + distributed flex slot allocation:
#   CI (1B/3B): 12 extra split between 1B and 3B → +12 each
#   MI (2B/SS): 12 extra split between 2B and SS → +6 each (SS typically fills MI)
#   UTIL: 12 extra spread across all hitters, negligible per position
DEFAULT_ROSTER_N: dict[str, int] = {
    "C":  12,   # 1 per team
    "1B": 24,   # 1 main + 1 CI per team × 12
    "2B": 18,   # 1 main + 0.5 MI per team × 12
    "3B": 24,   # 1 main + 1 CI per team × 12
    "SS": 18,   # 1 main + 0.5 MI per team × 12
    "OF": 36,   # 3 per team
    "SP": 60,   # 5 per team
    "RP": 36,   # 3 per team
}


def _safe(val) -> Optional[float]:
    try:
        v = float(val)
        return v if v == v else None  # NaN check
    except (TypeError, ValueError):
        return None


def compute_fpts(row: pd.Series) -> Optional[float]:
    """Compute CBS-model projected FPTS from a projections_2026.csv row."""
    ptype = row.get("type", "hitter")
    if ptype == "hitter":
        r, hr, rbi, sb, avg = (
            _safe(row.get("proj_r")), _safe(row.get("proj_hr")),
            _safe(row.get("proj_rbi")), _safe(row.get("proj_sb")),
            _safe(row.get("proj_avg")),
        )
        if any(v is None for v in (r, hr, rbi, sb, avg)):
            return None
        return (CBS_H_COEF_R * r + CBS_H_COEF_HR * hr + CBS_H_COEF_RBI * rbi
                + CBS_H_COEF_SB * sb + CBS_H_COEF_AVG * avg + CBS_H_INTERCEPT)
    else:
        w, era, whip, k, sv = (
            _safe(row.get("proj_w")), _safe(row.get("proj_era")),
            _safe(row.get("proj_whip")), _safe(row.get("proj_k")),
            _safe(row.get("proj_sv_h")),
        )
        if any(v is None for v in (w, era, whip, k, sv)):
            return None
        return (CBS_P_COEF_W * w + CBS_P_COEF_ERA * era + CBS_P_COEF_WHIP * whip
                + CBS_P_COEF_K * k + CBS_P_COEF_SV * sv + CBS_P_INTERCEPT)


def load_position_map() -> dict[int, str]:
    """Returns {mlbam_id: fantasy_position} from player_values.json."""
    if not VALUES_JSON.exists():
        return {}
    with open(VALUES_JSON) as f:
        pv = json.load(f)
    result = {}
    for p in pv.get("players", []):
        pid = p.get("id")
        raw_pos = p.get("pos", "")
        fpos = FANTASY_POS_MAP.get(raw_pos)
        if pid and fpos:
            result[int(pid)] = fpos
    return result


def load_replacement_levels(
    roster_n: Optional[dict[str, int]] = None,
) -> dict[str, float]:
    """
    Compute replacement-level FPTS for each fantasy position.

    Returns dict like {'SP': 221.5, '1B': 275.7, 'C': 289.8, ...}
    Replacement player = Nth-best at position, N from roster_n (default: 12-team standard).
    """
    n_map = roster_n or DEFAULT_ROSTER_N
    if not PROJ_CSV.exists():
        return {}

    proj = pd.read_csv(PROJ_CSV)
    pos_map = load_position_map()

    proj["fpts"] = proj.apply(compute_fpts, axis=1)

    def _assign_fpos(row):
        # Try by MLBAM id first (most reliable)
        fpos = None
        if row.get("type") == "hitter":
            # luck_scores.csv batter ID isn't in projections_2026; use name fallback
            pass
        elif row.get("type") == "pitcher":
            fpos = "SP"   # default; will be corrected below
        return fpos

    # Build name→fpos from player_values.json (name lookup for projections CSV)
    if VALUES_JSON.exists():
        with open(VALUES_JSON) as f:
            pv = json.load(f)
        name_fpos: dict[str, str] = {}
        for p in pv.get("players", []):
            raw = p.get("pos", "")
            fpos = FANTASY_POS_MAP.get(raw)
            if fpos:
                name_fpos[p["name"]] = fpos
    else:
        name_fpos = {}

    proj["fpos"] = proj["name"].map(name_fpos)
    # Fallback: pitchers without a name match default to RP (conservative)
    proj.loc[proj["type"] == "pitcher", "fpos"] = (
        proj.loc[proj["type"] == "pitcher", "fpos"]
        .fillna(proj.loc[proj["type"] == "pitcher", "name"]
                .map(lambda n: name_fpos.get(n, "RP")))
    )
    proj.loc[proj["type"] == "hitter", "fpos"] = (
        proj.loc[proj["type"] == "hitter", "fpos"].fillna("OF")
    )

    result: dict[str, float] = {}
    pools: dict[str, pd.DataFrame] = {}

    for pos, n in n_map.items():
        pool = (
            proj[proj["fpos"] == pos]
            .dropna(subset=["fpts"])
            .sort_values("fpts", ascending=False)
            .reset_index(drop=True)
        )
        pools[pos] = pool
        if len(pool) == 0:
            result[pos] = 0.0
            continue
        idx = min(n - 1, len(pool) - 1)
        result[pos] = float(pool.loc[idx, "fpts"])

    return result


def get_surplus(
    fpts: Optional[float],
    fantasy_pos: Optional[str],
    replacement_levels: dict[str, float],
) -> Optional[float]:
    """Return surplus FPTS above replacement, or None if data missing."""
    if fpts is None or fantasy_pos is None:
        return None
    repl = replacement_levels.get(fantasy_pos)
    if repl is None:
        return None
    return fpts - repl


def build_replacement_table(roster_n: Optional[dict[str, int]] = None) -> str:
    """Return a formatted string table of replacement levels for display."""
    n_map = roster_n or DEFAULT_ROSTER_N
    levels = load_replacement_levels(roster_n)

    if not PROJ_CSV.exists() or not VALUES_JSON.exists():
        return "  (replacement level data unavailable)"

    proj = pd.read_csv(PROJ_CSV)
    if VALUES_JSON.exists():
        with open(VALUES_JSON) as f:
            pv = json.load(f)
        name_fpos = {
            p["name"]: FANTASY_POS_MAP.get(p.get("pos", ""), None)
            for p in pv.get("players", [])
        }
    else:
        name_fpos = {}

    proj["fpts"] = proj.apply(compute_fpts, axis=1)
    proj["fpos"] = proj["name"].map(name_fpos)
    proj.loc[proj["type"] == "pitcher", "fpos"] = proj.loc[
        proj["type"] == "pitcher", "fpos"
    ].fillna("RP")
    proj.loc[proj["type"] == "hitter", "fpos"] = proj.loc[
        proj["type"] == "hitter", "fpos"
    ].fillna("OF")

    lines = []
    lines.append(f"  {'Pos':4s}  {'N':>4s}  {'Repl Player':26s}  {'Repl FPTS':>9s}")
    lines.append("  " + "-" * 55)
    for pos in ("C", "1B", "2B", "3B", "SS", "OF", "SP", "RP"):
        n = n_map.get(pos, 0)
        pool = (
            proj[proj["fpos"] == pos]
            .dropna(subset=["fpts"])
            .sort_values("fpts", ascending=False)
            .reset_index(drop=True)
        )
        if len(pool) == 0:
            lines.append(f"  {pos:4s}  {n:4d}  {'(no data)':26s}  {'N/A':>9s}")
            continue
        idx = min(n - 1, len(pool) - 1)
        repl_name  = pool.loc[idx, "name"]
        repl_fpts  = pool.loc[idx, "fpts"]
        lines.append(
            f"  {pos:4s}  {n:4d}  {repl_name[:26]:26s}  {repl_fpts:9.1f}"
        )
    return "\n".join(lines)
