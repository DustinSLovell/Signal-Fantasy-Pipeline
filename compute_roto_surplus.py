"""
Roto surplus model for Signal Fantasy.

Category rank contribution model with HR cascade weight x1.4.
Scales output to CBS-equivalent FPTS range for threshold compatibility.

Run AFTER score_value.py --write.
Reads data/player_values.json, adds roto_surplus_l1 to each player, writes back.

Hitter categories (5x5 roto):
  HR x1.4  |  R x1.0  |  RBI x1.0  |  SB x1.0  |  AVG x1.0

Pitcher categories:
  SP:  W x1.0  |  K x1.0  |  ERA x1.0 (inverted)  |  WHIP x1.0 (inverted)
  RP:  SVH x1.0  |  K x1.0  |  ERA x1.0 (inverted)  |  WHIP x1.0 (inverted)

Rank assignment: best player gets rank N-1, worst gets rank 0.
roto_surplus = player_rank_sum - replacement_rank_sum, scaled to CBS units.
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict

_DIR = os.path.dirname(os.path.abspath(__file__))
PLAYER_VALUES_PATH = os.path.join(_DIR, 'data', 'player_values.json')

FPOS_MAP: dict[str, str] = {
    'C': 'C', '1B': '1B', '2B': '2B', '3B': '3B', 'SS': 'SS',
    'LF': 'OF', 'CF': 'OF', 'RF': 'OF', 'OF': 'OF',
    'DH': '1B', 'IF': '2B',
    'SP': 'SP', 'RP': 'RP',
}

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

# Null fill: for bad-stat categories (ERA/WHIP), fill with max-bad so nulls rank last
_NULL_FILL: dict[str, float] = {
    'ERA':  99.0,
    'WHIP':  5.0,
}


def compute_roto_surpluses(players: list[dict], roster_n: dict[str, int]) -> dict[int, float | None]:
    """
    Returns dict: player_id -> roto_surplus_l1 (scaled to CBS-equivalent FPTS).

    Algorithm:
    1. Group players by fantasy position.
    2. Rank each player per category within the pool (best gets rank N-1, worst 0).
    3. roto_score = sum of (rank x weight) across categories.
    4. roto_surplus = roto_score - Nth player roto_score.
    5. Scale so median positive roto_surplus == median positive CBS surplus.
    """
    pools: dict[str, list[dict]] = {}
    for p in players:
        fpos = FPOS_MAP.get(p.get('pos', ''))
        if fpos:
            pools.setdefault(fpos, []).append(p)

    scores: dict[int, float] = {}
    pid_fpos: dict[int, str] = {}

    for fpos, pool in pools.items():
        N = len(pool)
        if fpos == 'SP':
            cats = SP_CATS
        elif fpos == 'RP':
            cats = RP_CATS
        else:
            cats = HITTER_CATS

        for p in pool:
            scores[p['id']] = 0.0
            pid_fpos[p['id']] = fpos

        for cat, weight, higher_is_better in cats:
            null_fill = _NULL_FILL.get(cat, 0.0)
            vals: list[tuple[int, float]] = []
            for p in pool:
                proj = p.get('proj') or {}
                v = proj.get(cat)
                vals.append((p['id'], float(v) if v is not None else null_fill))

            # Sort so index 0 = worst fantasy value, index N-1 = best
            sorted_asc = sorted(vals, key=lambda x: x[1], reverse=not higher_is_better)
            # Normalize rank by pool size so cross-position comparisons are fair.
            # rank/N ranges 0→1 regardless of pool size; no RP inflation vs C.
            for rank, (pid, _) in enumerate(sorted_asc):
                scores[pid] += (rank / N) * weight

    # Build replacement levels
    fpos_groups: dict[str, list[tuple[int, float]]] = defaultdict(list)
    for pid, score in scores.items():
        fpos_groups[pid_fpos[pid]].append((pid, score))

    repl_score: dict[str, float] = {}
    for fpos, pid_scores in fpos_groups.items():
        sorted_desc = sorted(pid_scores, key=lambda x: x[1], reverse=True)
        n = max(1, roster_n.get(fpos, 12))
        idx = min(n - 1, len(sorted_desc) - 1)
        repl_score[fpos] = sorted_desc[idx][1]

    # Raw surplus
    raw: dict[int, float] = {}
    for pid, score in scores.items():
        raw[pid] = score - repl_score.get(pid_fpos[pid], 0.0)

    # Scale to match CBS surplus magnitude
    pos_cbs = sorted(
        p['surplus_l1'] for p in players
        if isinstance(p.get('surplus_l1'), (int, float)) and p['surplus_l1'] > 10
    )
    pos_raw = sorted(v for v in raw.values() if v > 0)

    if pos_cbs and pos_raw:
        med_cbs = pos_cbs[len(pos_cbs) // 2]
        med_raw = pos_raw[len(pos_raw) // 2]
        scale = med_cbs / med_raw if med_raw > 0 else 1.0
    else:
        scale = 1.0

    return {pid: round(v * scale, 1) for pid, v in raw.items()}


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
            print(f"  {p['name']:28s}  CBS surplus: {p.get('surplus_l1'):+7.1f}  "
                  f"Roto surplus: {p.get('roto_surplus_l1'):+7.1f}")


if __name__ == '__main__':
    main()
