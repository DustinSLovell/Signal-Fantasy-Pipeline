"""
Roto surplus model for Signal Fantasy.

Global-ranking category model with positional scarcity multipliers.
Scales output to CBS-equivalent FPTS range for threshold compatibility.

Run AFTER score_value.py --write.
Reads data/player_values.json, adds roto_surplus_l1 to each player, writes back.

Hitter categories (5x5 roto):
  HR x1.4  |  R x1.0  |  RBI x1.0  |  SB x1.0  |  AVG x1.0

Pitcher categories (within-pool ranking, unchanged):
  SP:  W x1.0  |  K x1.0  |  ERA x1.0 (inverted)  |  WHIP x1.0 (inverted)
  RP:  SVH x1.0  |  K x1.0  |  ERA x1.0 (inverted)  |  WHIP x1.0 (inverted)

Hitter global ranking:
  All hitters ranked globally per category; rank/N_hitters gives a cross-position
  percentile. Positional scarcity multiplier applied after scoring.

Scarcity multipliers (based on roster_slots × 13 teams):
  OF 1.15 (5 slots × 13 = 65 starters)
  SS 1.10 (1 slot  × 13 = 13 starters)
  2B 1.08 (1 slot  × 13 = 13 starters)
  C  1.05 (2 slots × 13 = 26 starters)
  3B 1.03 (1 slot  × 13 = 13 starters)
  1B 1.00 (1 slot  × 13 = 13 starters)

Replacement level: Nth player's (global_score × scarcity_mult) per position.
roto_surplus = (global_score × scarcity_mult) - position_replacement_level.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict

_DIR = os.path.dirname(os.path.abspath(__file__))
PLAYER_VALUES_PATH = os.path.join(_DIR, 'data', 'player_values.json')

FPOS_MAP: dict[str, str] = {
    'C': 'C', '1B': '1B', '2B': '2B', '3B': '3B', 'SS': 'SS',
    'LF': 'OF', 'CF': 'OF', 'RF': 'OF', 'OF': 'OF',
    'DH': '1B', 'IF': '2B',
    'SP': 'SP', 'RP': 'RP',
}

HITTER_FPOS = {'C', '1B', '2B', '3B', 'SS', 'OF'}

# (proj_field, weight, higher_is_better)
HITTER_CATS = [
    ('HR',  1.4, True),
    ('R',   1.0, True),
    ('RBI', 1.0, True),
    ('SB',  1.0, True),
    ('AVG', 1.0, True),
]
SP_CATS = [
    ('W',    1.0, True),
    ('K',    1.0, True),
    ('ERA',  1.0, False),
    ('WHIP', 1.0, False),
]
RP_CATS = [
    ('SVH_L1', 1.0, True),
    ('K',      1.0, True),
    ('ERA',    1.0, False),
    ('WHIP',   1.0, False),
]

# Positional scarcity multipliers
SCARCITY_MULT: dict[str, float] = {
    'OF': 1.15,
    'SS': 1.10,
    '2B': 1.08,
    'C':  1.05,
    '3B': 1.03,
    '1B': 1.00,
}

# Null fill for inverted categories (bad stat = nulls rank last)
_NULL_FILL: dict[str, float] = {
    'ERA':  99.0,
    'WHIP':  5.0,
}


def compute_roto_surpluses(players: list[dict], roster_n: dict[str, int]) -> dict[int, float | None]:
    """
    Returns dict: player_id -> roto_surplus_l1 (scaled to CBS-equivalent FPTS).

    Hitter algorithm:
    1. Rank all hitters globally per category (rank/N_hitters = cross-position percentile).
    2. global_score = sum(percentile × weight) across all categories.
    3. adjusted_score = global_score × SCARCITY_MULT[position].
       Multi-eligible players use highest scarcity multiplier available.
    4. Replacement level per position = Nth player's adjusted_score.
    5. roto_surplus = adjusted_score - replacement_level.
    6. Scale so median positive roto_surplus == median positive CBS surplus.

    Pitcher algorithm (unchanged): within SP/RP pool ranking.
    """
    # Separate hitters and pitchers
    hitters: list[tuple[dict, str]] = []   # (player, fpos)
    sp_pool: list[dict] = []
    rp_pool: list[dict] = []

    for p in players:
        fpos = FPOS_MAP.get(p.get('pos', ''))
        if fpos in HITTER_FPOS:
            hitters.append((p, fpos))
        elif fpos == 'SP':
            sp_pool.append(p)
        elif fpos == 'RP':
            rp_pool.append(p)

    result: dict[int, float] = {}

    # ── Hitters: global ranking ───────────────────────────────────────────────
    N_h = len(hitters)
    h_scores: dict[int, float] = {p['id']: 0.0 for p, _ in hitters}

    if N_h > 0:
        for cat, weight, higher_is_better in HITTER_CATS:
            null_fill = _NULL_FILL.get(cat, 0.0)
            vals: list[tuple[int, float]] = []
            for p, _ in hitters:
                v = (p.get('proj') or {}).get(cat)
                vals.append((p['id'], float(v) if v is not None else null_fill))

            # Index 0 = worst fantasy value, index N_h-1 = best
            sorted_asc = sorted(vals, key=lambda x: x[1], reverse=not higher_is_better)
            for rank, (pid, _) in enumerate(sorted_asc):
                h_scores[pid] += (rank / N_h) * weight

    # ── Apply positional scarcity multiplier ─────────────────────────────────
    h_adjusted: dict[int, float] = {}
    h_fpos: dict[int, str] = {}

    for p, fpos in hitters:
        mult = SCARCITY_MULT.get(fpos, 1.00)
        # Multi-position eligibility: use highest scarcity multiplier available
        for ep in (p.get('eligible_positions') or []):
            efpos = FPOS_MAP.get(ep, '')
            mult = max(mult, SCARCITY_MULT.get(efpos, 1.00))
        h_adjusted[p['id']] = h_scores[p['id']] * mult
        h_fpos[p['id']] = fpos

    # ── Position-specific replacement levels ──────────────────────────────────
    fpos_adj: dict[str, list[float]] = defaultdict(list)
    for p, fpos in hitters:
        fpos_adj[fpos].append(h_adjusted[p['id']])

    h_repl: dict[str, float] = {}
    for fpos, adj_vals in fpos_adj.items():
        sorted_desc = sorted(adj_vals, reverse=True)
        n = max(1, roster_n.get(fpos, 12))
        idx = min(n - 1, len(sorted_desc) - 1)
        h_repl[fpos] = sorted_desc[idx]

    for p, fpos in hitters:
        result[p['id']] = h_adjusted[p['id']] - h_repl.get(fpos, 0.0)

    # ── Pitchers: within-pool ranking (unchanged) ─────────────────────────────
    for pool, cats, fpos_key in [
        (sp_pool, SP_CATS, 'SP'),
        (rp_pool, RP_CATS, 'RP'),
    ]:
        N = len(pool)
        if N == 0:
            continue
        p_scores: dict[int, float] = {p['id']: 0.0 for p in pool}
        for cat, weight, higher_is_better in cats:
            null_fill = _NULL_FILL.get(cat, 0.0)
            vals = []
            for p in pool:
                v = (p.get('proj') or {}).get(cat)
                vals.append((p['id'], float(v) if v is not None else null_fill))
            sorted_asc = sorted(vals, key=lambda x: x[1], reverse=not higher_is_better)
            for rank, (pid, _) in enumerate(sorted_asc):
                p_scores[pid] += (rank / N) * weight

        sorted_desc = sorted(p_scores.values(), reverse=True)
        n = max(1, roster_n.get(fpos_key, 12))
        idx = min(n - 1, len(sorted_desc) - 1)
        repl = sorted_desc[idx]
        for p in pool:
            result[p['id']] = p_scores[p['id']] - repl

    # ── Scale to match CBS surplus magnitude ──────────────────────────────────
    # Primary: use surplus_l1 (raw FPTS above replacement). Fallback: use
    # proj_fpts spread (median of top-50% proj_fpts vs bottom-50%) if surplus_l1 absent.
    pos_cbs = sorted(
        p['surplus_l1'] for p in players
        if isinstance(p.get('surplus_l1'), (int, float)) and p['surplus_l1'] > 10
    )
    if not pos_cbs:
        # Fallback: median positive proj_fpts as reference magnitude
        pos_cbs = sorted(
            p['proj_fpts'] for p in players
            if isinstance(p.get('proj_fpts'), (int, float)) and p['proj_fpts'] > 50
        )

    pos_raw = sorted(v for v in result.values() if v > 0)

    if pos_cbs and pos_raw:
        med_cbs = pos_cbs[len(pos_cbs) // 2]
        med_raw = pos_raw[len(pos_raw) // 2]
        scale = med_cbs / med_raw if med_raw > 0 else 1.0
    else:
        scale = 1.0

    return {pid: round(v * scale, 1) for pid, v in result.items()}


def main() -> None:
    with open(PLAYER_VALUES_PATH, encoding='utf-8') as f:
        data = json.load(f)

    players: list[dict] = data['players']

    # Use L1 roster N (from replacement_level defaults)
    try:
        from replacement_level import DEFAULT_ROSTER_N
        roster_n = dict(DEFAULT_ROSTER_N)
    except ImportError:
        roster_n = {'C': 12, '1B': 24, '2B': 18, '3B': 24, 'SS': 18, 'OF': 36, 'SP': 60, 'RP': 36}

    surpluses = compute_roto_surpluses(players, roster_n)

    updated = 0
    for p in players:
        rs = surpluses.get(p['id'])
        p['roto_surplus_l1'] = rs
        if rs is not None:
            updated += 1

    data['players'] = players

    with open(PLAYER_VALUES_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"[roto] {updated}/{len(players)} players updated with roto_surplus_l1")

    # Sanity check: top 3 per position
    by_fpos: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for p in players:
        rs = p.get('roto_surplus_l1')
        fpos = FPOS_MAP.get(p.get('pos', ''))
        if fpos and rs is not None:
            by_fpos[fpos].append((p['name'], rs))

    print("\nTop 3 per position (roto surplus):")
    for fpos in ['C', '1B', '2B', '3B', 'SS', 'OF', 'SP', 'RP']:
        if fpos in by_fpos:
            top3 = sorted(by_fpos[fpos], key=lambda x: x[1], reverse=True)[:3]
            print(f"  {fpos}: {', '.join(f'{n} ({v:+.0f})' for n, v in top3)}")

    # Key players for gate verification
    print("\nGate players:")
    gate_names = ['Aaron Judge', 'Yordan Alvarez', 'Gary Sánchez', 'Drake Baldwin',
                  'William Contreras', 'Cal Raleigh', 'Oneil Cruz', 'Michael Harris']
    for p in players:
        if any(g.lower() in p['name'].lower() for g in gate_names):
            sl = p.get('surplus_l1')
            rs = p.get('roto_surplus_l1')
            sl_s = f"{sl:+7.1f}" if isinstance(sl, (int, float)) else "    N/A"
            rs_s = f"{rs:+7.1f}" if isinstance(rs, (int, float)) else "    N/A"
            print(f"  {p['name']:28s}  CBS surplus: {sl_s}  Roto surplus: {rs_s}")


if __name__ == '__main__':
    main()
