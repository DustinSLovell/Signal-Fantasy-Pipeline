"""
Roto surplus model for Signal Fantasy — Category Breadth Architecture.

Two-stage scoring:
  Stage 1: Global percentile ranking per category (rank/N = percentile).
  Stage 2: Exponential breadth multiplier based on how many categories
           the player contributes to meaningfully (fixed raw stat floors).

Hitter categories (5x5 roto):
  HR x1.6 | R x1.0 | RBI x1.0 | SB x1.2 | AVG x1.3
  breadth_mult = 1.20 ^ breadth_count (0–5 contributing categories)
  SB independence bonus x1.10 when contributes_SB + (contributes_HR or RBI)
  AVG three-state: AVG>=0.255 -> +1 breadth | 0.220-0.254 -> neutral | <0.220 -> -1 breadth + x0.92
  Contribution floors (fixed, pool-size-stable):
    HR>=22 | R>=85 | RBI>=80 | SB>=15 | AVG>=0.255
  Elite floors: HR>=35 | R>=120 | RBI>=105 | SB>=35 | AVG>=0.285

SP categories (breadth model):
  ERA x1.0 (inv) | WHIP x0.5 (inv, corr w/ ERA) | K x1.0 | W x0.5
  pitcher_breadth is fractional; breadth_mult = 1.15 ^ pitcher_breadth
  W contribution gated on team_win_pct >= 0.520

RP categories (flat within-pool ranking, unchanged):
  SVH x1.0 | K x1.0 | ERA x1.0 (inv) | WHIP x1.0 (inv)

Demand-based scarcity multipliers (13-team, 5 OF slots):
  OF 1.183 | C 1.173 | 1B 1.148 | SS 1.130 | 3B 1.127 | 2B 1.118 | DH 0.90 (penalty)

Gates:
  Tier 1 (fp_rank <= 150): full scoring, no cap
  Tier 2 (fp_rank 151-200): scored normally, surplus capped at median Tier 1/3 surplus
  Excluded (proj_PA < 400 OR fp_rank > 200): roto_surplus = 0
  SP:      proj_IP < 100 → roto_surplus = 0
  RP:      proj_IP < 40  → roto_surplus = 0
"""

from __future__ import annotations

import json
import os
from collections import defaultdict

_DIR = os.path.dirname(os.path.abspath(__file__))
PLAYER_VALUES_PATH   = os.path.join(_DIR, 'data', 'player_values.json')
_PITCHER_LUCK_PATH   = os.path.join(_DIR, 'pitcher_luck_scores.csv')
_TEAM_WIN_PCTS_PATH  = os.path.join(_DIR, 'data', 'team_win_pcts_2026.json')

FPOS_MAP: dict[str, str] = {
    'C': 'C', '1B': '1B', '2B': '2B', '3B': '3B', 'SS': 'SS',
    'LF': 'OF', 'CF': 'OF', 'RF': 'OF', 'OF': 'OF',
    'DH': 'DH', 'IF': '2B',
    'SP': 'SP', 'RP': 'RP',
}

HITTER_FPOS = {'C', '1B', '2B', '3B', 'SS', 'OF', 'DH'}

# (proj_field, weight, higher_is_better)
# HR weight 1.6 — reduced from 2.0 to balance with breadth multiplier
HITTER_CATS = [
    ('HR',  1.6, True),
    ('R',   1.0, True),
    ('RBI', 1.0, True),
    ('SB',  1.2, True),
    ('AVG', 1.3, True),
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

# Demand-based scarcity multipliers: starters / pool_size, normalized
# OF: 65/178  C: 26/75  1B: 13/44  SS: 13/50  3B: 13/51  2B: 13/55  DH: 13/~20
SCARCITY_MULT: dict[str, float] = {
    'OF': 1.183,
    'C':  1.173,
    '1B': 1.148,
    'SS': 1.130,
    '3B': 1.127,
    '2B': 1.118,
    'DH': 0.90,   # DH is non-scarce; penalty offset by dominance bonus at elite tier
}

# Null fill for inverted categories (bad stat = nulls rank last)
_NULL_FILL: dict[str, float] = {
    'ERA':  99.0,
    'WHIP':  5.0,
}

# ── Breadth model constants (fixed raw stat floors — pool-size-stable) ───────
# Contribution floors: must reach this raw projected stat to count breadth
_C_HR_THRESH        = 22      # proj_HR >= 22 → c_HR = True
_C_R_THRESH         = 85      # proj_R  >= 85 → c_R  = True
_C_RBI_THRESH       = 80      # proj_RBI >= 80 → c_RBI = True
_SB_HARD_FLOOR      = 15      # proj_SB >= 15 → c_SB = True
_AVG_CONTRIB_THRESH = 0.255   # proj_AVG >= 0.255 → c_AVG = +1
_AVG_NEUTRAL_THRESH = 0.220   # proj_AVG >= 0.220 (and < 0.255) → c_AVG = 0; else -1

_HITTER_BREADTH_BASE   = 1.20   # multiplier base: 1.20^breadth_count
_SB_POWER_BONUS        = 1.10   # extra bonus: SB + (HR or RBI) together
_AVG_PENALTY_MULT      = 0.92   # score multiplier when c_AVG == -1

# Elite dominance floors (fixed raw stats)
_E_HR_THRESH    = 35      # proj_HR >= 35  → elite HR
_E_R_THRESH     = 120     # proj_R  >= 120 → elite R
_E_RBI_THRESH   = 105     # proj_RBI >= 105 → elite RBI
_E_SB_THRESH    = 35      # proj_SB >= 35  → elite SB
_E_AVG_THRESH   = 0.285   # proj_AVG >= 0.285 → elite AVG
_ELITE_BASE     = 1.05    # 1.05^elite_count

# Tiered scarcity tier boundaries (percentile of raw h_score across all hitters)
_SCARCITY_TOP_PCT      = 0.85
_SCARCITY_MID_LOW_PCT  = 0.40
_SCARCITY_TOP_DAMP     = 0.25   # compress scarcity at elite tier
_SCARCITY_BOT_AMP      = 1.40   # amplify scarcity at bottom tier

_SP_BREADTH_THRESH  = 0.55
_SP_BREADTH_BASE    = 1.15      # 1.15^pitcher_breadth (fractional exponent)
_SP_WIN_PCT_GATE    = 0.520     # min team win% for W to count as a contribution

# FP rank tiered gate
_FP_EXCLUDE_GATE    = 200       # fp_rank > this -> excluded (roto_surplus = 0)
_FP_TIER2_GATE      = 150       # fp_rank 151-200 -> scored but capped at median surplus
_C_SCARCITY_CAP     = 1.02      # max effective scarcity mult for catchers


def _load_team_win_pcts() -> dict[str, float]:
    """Load team win percentages from data/team_win_pcts_2026.json.
    Returns empty dict (all teams default to 0.500) if file absent."""
    if not os.path.exists(_TEAM_WIN_PCTS_PATH):
        return {}
    try:
        with open(_TEAM_WIN_PCTS_PATH, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _load_pitcher_teams() -> dict[int, str]:
    """Load pitcher_id → team abbreviation from pitcher_luck_scores.csv."""
    if not os.path.exists(_PITCHER_LUCK_PATH):
        return {}
    try:
        import csv
        result: dict[int, str] = {}
        with open(_PITCHER_LUCK_PATH, encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    pid = int(row.get('pitcher', '') or 0)
                    team = (row.get('Team') or row.get('team') or '').strip()
                    if pid and team:
                        result[pid] = team
                except (ValueError, TypeError):
                    pass
        return result
    except Exception:
        return {}


def _w_team_mult(win_pct: float) -> float:
    """Map team win% to W-category multiplier."""
    if win_pct >= 0.580:
        return 1.15
    if win_pct >= 0.520:
        return 1.07
    if win_pct >= 0.500:
        return 1.00
    if win_pct >= 0.450:
        return 0.85
    return 0.75


def compute_roto_surpluses(
    players: list[dict],
    roster_n: dict[str, int],
) -> tuple[dict[int, float], dict[int, dict]]:  # (surplus, extras)
    """
    Returns (surplus_dict, extras_dict).

    surplus_dict: player_id -> roto_surplus_l1 (scaled to CBS-equivalent FPTS).
    extras_dict:  player_id -> {breadth_count, breadth_mult, sb_bonus, ...}

    Hitter algorithm (Category Breadth model):
    1. Rank all hitters globally per category → percentile = rank/N_h.
    2. breadth_count = # categories where percentile >= 0.55.
    3. breadth_mult  = 1.20 ^ breadth_count.
    4. sb_bonus      = 1.10 if contributes_SB AND (contributes_HR OR contributes_RBI).
    5. base_score    = sum(percentile × weight) across all categories.
    6. h_score       = base_score × breadth_mult × sb_bonus.
    7. adjusted      = h_score × SCARCITY_MULT[position].
    8. surplus       = adjusted − position_replacement_level (Nth adjusted score).

    SP algorithm (Category Breadth model):
    1. Rank within SP pool per category → percentile.
    2. pitcher_breadth = ERA×1.0 + WHIP×0.5 + K×1.0 + W×0.5
       (W counts only if team_win_pct >= 0.520).
    3. breadth_mult = 1.15 ^ pitcher_breadth.
    4. W percentile scaled by w_team_mult before base_score.
    5. surplus = (base_score × breadth_mult) − replacement_level.

    RP algorithm: flat weighted-percentile within RP pool (unchanged).
    """
    team_win_pcts  = _load_team_win_pcts()
    pitcher_teams  = _load_pitcher_teams()

    # ── Gate players + separate pools ────────────────────────────────────────
    hitters: list[tuple[dict, str]] = []
    sp_pool: list[dict] = []
    rp_pool: list[dict] = []
    excluded_ids: set[int] = set()
    tier2_ids:    set[int] = set()   # fp_rank 151-200: scored normally, capped post-scoring
    _seen_ids:    set[int] = set()   # dedup: first entry wins (DH before SP for Ohtani)

    for p in players:
        if p['id'] in _seen_ids:
            continue
        _seen_ids.add(p['id'])
        fpos = FPOS_MAP.get(p.get('pos', ''))
        if fpos in HITTER_FPOS:
            pa = p.get('PA_proj') or 0
            fp = int(p.get('fp_rank') or 9999)
            if float(pa) < 400 or fp > _FP_EXCLUDE_GATE:
                excluded_ids.add(p['id'])
            else:
                hitters.append((p, fpos))
                if fp > _FP_TIER2_GATE:
                    tier2_ids.add(p['id'])
        elif fpos == 'SP':
            ip = p.get('IP_proj') or 0
            if float(ip) < 100:
                excluded_ids.add(p['id'])
            else:
                sp_pool.append(p)
        elif fpos == 'RP':
            ip = p.get('IP_proj') or 0
            if float(ip) < 40:
                excluded_ids.add(p['id'])
            else:
                rp_pool.append(p)

    result: dict[int, float] = {pid: 0.0 for pid in excluded_ids}
    extras: dict[int, dict]  = {}

    # ── Projection overrides: blend career avg + current projection ───────────
    _override_proj: dict[int, dict] = {}     # mlbam_id -> blended proj dict
    _orig_proj:     dict[int, dict] = {}     # mlbam_id -> original proj (for display)
    try:
        _ov_path = os.path.join(_DIR, 'data', 'projection_overrides.json')
        with open(_ov_path, encoding='utf-8') as _ov_f:
            _overrides_data = json.load(_ov_f)
        _id_to_p = {p['id']: p for p, _ in hitters}
        for _ov in _overrides_data.get('hitters', []):
            _ov_id = _ov['mlbam_id']
            if _ov_id not in _id_to_p:
                continue
            _op = _id_to_p[_ov_id].get('proj') or {}
            _w  = float(_ov['blend_weight'])
            _ca = _ov['career_avg']
            _orig_proj[_ov_id] = dict(_op)
            _override_proj[_ov_id] = {
                'HR':  _w * _ca['HR']  + (1 - _w) * float(_op.get('HR')  or 0),
                'R':   _w * _ca['R']   + (1 - _w) * float(_op.get('R')   or 0),
                'RBI': _w * _ca['RBI'] + (1 - _w) * float(_op.get('RBI') or 0),
                'SB':  _w * _ca['SB']  + (1 - _w) * float(_op.get('SB')  or 0),
                'AVG': _w * _ca['AVG'] + (1 - _w) * float(_op.get('AVG') or 0),
            }
            print(f"  Override applied: {_ov['name']} -- blended projections")
    except FileNotFoundError:
        pass
    except Exception as _ov_err:
        print(f"  WARNING: projection_overrides.json load failed: {_ov_err}")

    # ── Hitters: global percentile ranking ───────────────────────────────────
    N_h = len(hitters)
    h_percentiles: dict[int, dict[str, float]] = {p['id']: {} for p, _ in hitters}

    if N_h > 0:
        for cat, _weight, higher_is_better in HITTER_CATS:
            null_fill = _NULL_FILL.get(cat, 0.0)
            vals: list[tuple[int, float]] = []
            for p, _ in hitters:
                _pj = _override_proj.get(p['id']) or (p.get('proj') or {})
                v = _pj.get(cat)
                vals.append((p['id'], float(v) if v is not None else null_fill))

            sorted_asc = sorted(vals, key=lambda x: x[1], reverse=not higher_is_better)
            for rank, (pid, _) in enumerate(sorted_asc):
                h_percentiles[pid][cat] = rank / N_h

    # ── Hitter breadth + dominance scores ────────────────────────────────────
    h_scores: dict[int, float] = {}

    for p, _fpos in hitters:
        pid  = p['id']
        pcts = h_percentiles[pid]
        _proj = _override_proj.get(pid) or (p.get('proj') or {})

        # Breadth flags: fixed raw stat floors (pool-size-stable)
        c_HR  = float(_proj.get('HR')  or 0) >= _C_HR_THRESH
        c_R   = float(_proj.get('R')   or 0) >= _C_R_THRESH
        c_RBI = float(_proj.get('RBI') or 0) >= _C_RBI_THRESH
        c_SB  = float(_proj.get('SB')  or 0) >= _SB_HARD_FLOOR
        avg_v = float(_proj.get('AVG') or 0)
        if avg_v >= _AVG_CONTRIB_THRESH:
            c_AVG = 1      # contributes breadth
        elif avg_v >= _AVG_NEUTRAL_THRESH:
            c_AVG = 0      # neutral
        else:
            c_AVG = -1     # AVG liability: reduces breadth + penalty mult

        breadth_count = max(0, int(c_HR) + int(c_R) + int(c_RBI) + int(c_SB) + c_AVG)
        breadth_mult  = _HITTER_BREADTH_BASE ** breadth_count
        avg_penalty_mult = _AVG_PENALTY_MULT if c_AVG == -1 else 1.0

        sb_bonus = _SB_POWER_BONUS if (c_SB and (c_HR or c_RBI)) else 1.0

        # Elite dominance bonus: 1.05 ^ (# categories at fixed elite floor)
        elite_HR  = float(_proj.get('HR')  or 0) >= _E_HR_THRESH
        elite_R   = float(_proj.get('R')   or 0) >= _E_R_THRESH
        elite_RBI = float(_proj.get('RBI') or 0) >= _E_RBI_THRESH
        elite_SB  = float(_proj.get('SB')  or 0) >= _E_SB_THRESH
        elite_AVG = float(_proj.get('AVG') or 0) >= _E_AVG_THRESH
        elite_count = int(elite_HR) + int(elite_R) + int(elite_RBI) + int(elite_SB) + int(elite_AVG)
        elite_bonus = _ELITE_BASE ** elite_count

        base = sum(pcts.get(cat, 0.0) * w for cat, w, _ in HITTER_CATS)
        h_scores[pid] = base * breadth_mult * sb_bonus * elite_bonus * avg_penalty_mult

        extras[pid] = {
            'breadth_count':    breadth_count,
            'breadth_mult':     round(breadth_mult, 3),
            'orig_proj':        _orig_proj.get(pid),   # None if not overridden
            'sb_bonus':         sb_bonus,
            'elite_count':      elite_count,
            'elite_bonus':      round(elite_bonus, 3),
            'avg_penalty_mult': avg_penalty_mult,
            'c_HR': c_HR, 'c_R': c_R, 'c_RBI': c_RBI, 'c_SB': c_SB, 'c_AVG': c_AVG,
        }

    # ── Tiered positional scarcity multiplier ────────────────────────────────
    # Tier boundaries computed from global h_score distribution
    _all_scores_sorted = sorted(h_scores.values())
    _N_sc = len(_all_scores_sorted)
    _tier_top = _all_scores_sorted[min(int(_SCARCITY_TOP_PCT  * _N_sc), _N_sc - 1)] if _N_sc else 0.0
    _tier_mid = _all_scores_sorted[min(int(_SCARCITY_MID_LOW_PCT * _N_sc), _N_sc - 1)] if _N_sc else 0.0

    h_adjusted: dict[int, float] = {}

    for p, fpos in hitters:
        pid      = p['id']
        base_sc  = SCARCITY_MULT.get(fpos, 1.00)
        for ep in (p.get('eligible_positions') or []):
            efpos   = FPOS_MAP.get(ep, '')
            base_sc = max(base_sc, SCARCITY_MULT.get(efpos, 1.00))

        score = h_scores[pid]
        if score >= _tier_top:
            sc = 1.0 + (base_sc - 1.0) * _SCARCITY_TOP_DAMP   # dampened at top
        elif score >= _tier_mid:
            sc = base_sc                                          # full scarcity mid
        else:
            sc = 1.0 + (base_sc - 1.0) * _SCARCITY_BOT_AMP    # amplified at bottom

        if fpos == 'C':
            sc = min(sc, _C_SCARCITY_CAP)   # catcher scarcity hard cap
        h_adjusted[pid] = score * sc

    # ── Position-specific replacement levels ──────────────────────────────────
    fpos_adj: dict[str, list[float]] = defaultdict(list)
    for p, fpos in hitters:
        fpos_adj[fpos].append(h_adjusted[p['id']])

    h_repl: dict[str, float] = {}
    for fpos, adj_vals in fpos_adj.items():
        sorted_desc = sorted(adj_vals, reverse=True)
        n   = max(1, roster_n.get(fpos, 12))
        idx = min(n - 1, len(sorted_desc) - 1)
        h_repl[fpos] = sorted_desc[idx]

    for p, fpos in hitters:
        result[p['id']] = h_adjusted[p['id']] - h_repl.get(fpos, 0.0)

    # ── SP: Category Breadth model ────────────────────────────────────────────
    N_sp = len(sp_pool)
    if N_sp > 0:
        sp_percentiles: dict[int, dict[str, float]] = {p['id']: {} for p in sp_pool}

        for cat, _weight, higher_is_better in SP_CATS:
            null_fill = _NULL_FILL.get(cat, 0.0)
            vals = []
            for p in sp_pool:
                v = (p.get('proj') or {}).get(cat)
                vals.append((p['id'], float(v) if v is not None else null_fill))
            sorted_asc = sorted(vals, key=lambda x: x[1], reverse=not higher_is_better)
            for rank, (pid, _) in enumerate(sorted_asc):
                sp_percentiles[pid][cat] = rank / N_sp

        sp_scores: dict[int, float] = {}

        for p in sp_pool:
            pid  = p['id']
            pcts = sp_percentiles[pid]

            team  = pitcher_teams.get(pid, '')
            wp    = team_win_pcts.get(team, 0.500)
            wt_m  = _w_team_mult(wp)

            w_pct     = pcts.get('W', 0.0)
            w_pct_adj = w_pct * wt_m

            c_ERA  = pcts.get('ERA',  0.0) >= _SP_BREADTH_THRESH
            c_WHIP = pcts.get('WHIP', 0.0) >= _SP_BREADTH_THRESH
            c_K    = pcts.get('K',    0.0) >= _SP_BREADTH_THRESH
            c_W    = (w_pct >= _SP_BREADTH_THRESH) and (wp >= _SP_WIN_PCT_GATE)

            pitcher_breadth = 1.0*c_ERA + 0.5*c_WHIP + 1.0*c_K + 0.5*c_W
            breadth_mult    = _SP_BREADTH_BASE ** pitcher_breadth

            base = (pcts.get('ERA',  0.0) * 1.0 +
                    pcts.get('WHIP', 0.0) * 1.0 +
                    pcts.get('K',    0.0) * 1.0 +
                    w_pct_adj            * 1.0)

            sp_scores[pid] = base * breadth_mult
            extras[pid] = {
                'breadth_count': round(pitcher_breadth, 2),
                'breadth_mult':  round(breadth_mult, 3),
                'team':          team,
                'team_win_pct':  wp,
                'w_team_mult':   wt_m,
                'c_ERA': c_ERA, 'c_WHIP': c_WHIP, 'c_K': c_K, 'c_W': c_W,
            }

        sorted_desc = sorted(sp_scores.values(), reverse=True)
        n   = max(1, roster_n.get('SP', 60))
        idx = min(n - 1, len(sorted_desc) - 1)
        repl = sorted_desc[idx]
        for p in sp_pool:
            result[p['id']] = sp_scores[p['id']] - repl

    # ── RP: flat within-pool ranking (unchanged) ──────────────────────────────
    N_rp = len(rp_pool)
    if N_rp > 0:
        rp_scores: dict[int, float] = {p['id']: 0.0 for p in rp_pool}
        for cat, weight, higher_is_better in RP_CATS:
            null_fill = _NULL_FILL.get(cat, 0.0)
            vals = []
            for p in rp_pool:
                v = (p.get('proj') or {}).get(cat)
                vals.append((p['id'], float(v) if v is not None else null_fill))
            sorted_asc = sorted(vals, key=lambda x: x[1], reverse=not higher_is_better)
            for rank, (pid, _) in enumerate(sorted_asc):
                rp_scores[pid] += (rank / N_rp) * weight

        sorted_desc = sorted(rp_scores.values(), reverse=True)
        n   = max(1, roster_n.get('RP', 36))
        idx = min(n - 1, len(sorted_desc) - 1)
        repl = sorted_desc[idx]
        for p in rp_pool:
            result[p['id']] = rp_scores[p['id']] - repl

    # ── Scale to match CBS surplus magnitude ──────────────────────────────────
    pos_cbs = sorted(
        p['surplus_l1'] for p in players
        if isinstance(p.get('surplus_l1'), (int, float)) and p['surplus_l1'] > 10
    )
    if not pos_cbs:
        pos_cbs = sorted(
            p['proj_fpts'] for p in players
            if isinstance(p.get('proj_fpts'), (int, float)) and p['proj_fpts'] > 50
        )

    pos_raw = sorted(v for v in result.values() if v > 0)

    if pos_cbs and pos_raw:
        med_cbs = pos_cbs[len(pos_cbs) // 2]
        med_raw = pos_raw[len(pos_raw) // 2]
        scale   = med_cbs / med_raw if med_raw > 0 else 1.0
    else:
        scale = 1.0

    surplus = {pid: round(v * scale, 1) for pid, v in result.items()}

    # Tier 2 cap: fp_rank 151-200 capped at median positive surplus of Tier 1/3 players
    _tier1_pos = sorted(v for pid, v in surplus.items()
                        if v > 0 and pid not in tier2_ids and pid not in excluded_ids)
    if _tier1_pos and tier2_ids:
        _median_cap = _tier1_pos[len(_tier1_pos) // 2]
        for pid in tier2_ids:
            if pid in surplus and surplus[pid] > _median_cap:
                surplus[pid] = round(_median_cap, 1)

    return surplus, extras


def _print_pool_percentiles(players: list[dict], roster_n: dict[str, int]) -> None:
    """Print raw stat values at key percentiles for the qualified hitter pool."""
    qualified = []
    for p in players:
        fpos = FPOS_MAP.get(p.get('pos', ''))
        if fpos not in HITTER_FPOS:
            continue
        pa = p.get('PA_proj') or 0
        fp = int(p.get('fp_rank') or 9999)
        if float(pa) >= 400 and fp <= _FP_EXCLUDE_GATE:
            qualified.append(p.get('proj') or {})

    def _pct_val(vals_sorted: list[float], pct: float) -> float:
        idx = min(int(pct * len(vals_sorted)), len(vals_sorted) - 1)
        return vals_sorted[idx]

    sb_vals  = sorted(float(q.get('SB')  or 0) for q in qualified)
    hr_vals  = sorted(float(q.get('HR')  or 0) for q in qualified)
    avg_vals = sorted(float(q.get('AVG') or 0) for q in qualified)
    N = len(qualified)

    print(f"\n-- Pool calibration ({N} qualified hitters, fixed thresholds) ----")
    print(f"  SB  (floor: raw>=15)")
    for pct in (0.40, 0.50, 0.60, 0.75, 0.90):
        v = _pct_val(sb_vals, pct)
        marker = ' <- FLOOR ~' if abs(v - 15) <= 2 else ''
        print(f"    {pct:.0%}: {v:5.1f} SB{marker}")
    print(f"  HR  (floor: raw>=22 | elite: raw>=35)")
    for pct in (0.40, 0.50, 0.60, 0.75, 0.90):
        v = _pct_val(hr_vals, pct)
        marker = ' <- CONTRIB ~' if abs(v - 22) <= 2 else (' <- ELITE ~' if abs(v - 35) <= 2 else '')
        print(f"    {pct:.0%}: {v:5.1f} HR{marker}")
    print(f"  AVG (liability: <0.220 | neutral: 0.220-0.254 | contrib: >=0.255 | elite: >=0.285)")
    for pct in (0.20, 0.35, 0.50, 0.65, 0.80):
        v = _pct_val(avg_vals, pct)
        print(f"    {pct:.0%}: {v:.3f} AVG")
    print()


def main() -> None:
    with open(PLAYER_VALUES_PATH, encoding='utf-8') as f:
        data = json.load(f)

    players: list[dict] = data['players']

    # 13-team league roster slots
    try:
        from replacement_level import DEFAULT_ROSTER_N as _base
        sp_n = _base.get('SP', 60)
        rp_n = _base.get('RP', 36)
    except ImportError:
        sp_n, rp_n = 60, 36

    roster_n = {
        'C':  26,
        '1B': 13,
        '2B': 13,
        '3B': 13,
        'SS': 13,
        'OF': 65,
        'DH': 13,
        'SP': sp_n,
        'RP': rp_n,
    }

    surpluses, extras = compute_roto_surpluses(players, roster_n)

    # ── Pool calibration display ───────────────────────────────────────────────
    _print_pool_percentiles(players, roster_n)

    updated = 0
    for p in players:
        pid = p['id']
        rs  = surpluses.get(pid)
        p['roto_surplus_l1']    = rs
        ex = extras.get(pid, {})
        p['roto_breadth_count'] = ex.get('breadth_count')
        p['roto_breadth_mult']  = ex.get('breadth_mult')
        p['roto_elite_count']   = ex.get('elite_count')
        p['roto_elite_bonus']   = ex.get('elite_bonus')
        if rs is not None:
            updated += 1

    data['players'] = players

    with open(PLAYER_VALUES_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"[roto] {updated}/{len(players)} players updated with roto_surplus_l1")

    # Sanity check: top 3 per position
    by_fpos: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for p in players:
        rs   = p.get('roto_surplus_l1')
        fpos = FPOS_MAP.get(p.get('pos', ''))
        if fpos and rs is not None:
            by_fpos[fpos].append((p['name'], rs))

    print("\nTop 3 per position (roto surplus):")
    for fpos in ['C', '1B', '2B', '3B', 'SS', 'OF', 'DH', 'SP', 'RP']:
        if fpos in by_fpos:
            top3 = sorted(by_fpos[fpos], key=lambda x: x[1], reverse=True)[:3]
            print(f"  {fpos}: {', '.join(f'{n} ({v:+.0f})' for n, v in top3)}")

    # Gate players verification
    print("\nGate players:")
    gate_names = ['Aaron Judge', 'Yordan Alvarez', 'Gary Sánchez', 'Drake Baldwin',
                  'William Contreras', 'Cal Raleigh', 'Oneil Cruz', 'Michael Harris']
    for p in players:
        if any(g.lower() in p['name'].lower() for g in gate_names):
            sl   = p.get('surplus_l1')
            rs   = p.get('roto_surplus_l1')
            bc   = p.get('roto_breadth_count')
            sl_s = f"{sl:+7.1f}" if isinstance(sl, (int, float)) else "    N/A"
            rs_s = f"{rs:+7.1f}" if isinstance(rs, (int, float)) else "    N/A"
            bc_s = f"{bc}" if bc is not None else "N/A"
            print(f"  {p['name']:28s}  CBS surplus: {sl_s}  Roto surplus: {rs_s}  breadth: {bc_s}")


if __name__ == '__main__':
    main()
