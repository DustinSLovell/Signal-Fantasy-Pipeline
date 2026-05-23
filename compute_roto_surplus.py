"""
Roto surplus model for Signal Fantasy — Category Breadth + Elite Architecture.

Two-stage scoring:
  Stage 1: Global percentile ranking per category (rank/N = percentile).
  Stage 2: Percentile-based breadth multiplier + additive category elite bonus.

Hitter categories (5x5 roto):
  HR x1.6 | R x1.0 | RBI x1.0 | SB x1.2 | AVG x1.3

  Breadth multiplier (# categories at p70+):
    5 cats → x1.25 | 4 → x1.15 | 3 → x1.05 | 2 → x1.00 | 1 → x0.95 | 0 → x0.90

  Category elite bonus (additive, capped at +0.40):
    EXTREME (p97+):  +0.15 × scarcity_weight
    STRONG  (p93-97): +0.10 × scarcity_weight
    MILD    (p90-93): +0.05 × scarcity_weight
    Scarcity weights: SB=1.35 | AVG=1.15 | HR=1.05 | R=1.00 | RBI=1.00

  Formula: h_score = base × breadth_mult + category_elite_bonus

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

# ── Percentile-based breadth + category elite constants ───────────────────────
# Breadth: count categories where player is p70+ → lookup table for multiplier
_CAT_BREADTH_THRESH = 0.70
_BREADTH_MULT_TABLE = {5: 1.25, 4: 1.15, 3: 1.05, 2: 1.00, 1: 0.95, 0: 0.90}

# Elite tiers (percentile thresholds)
_CAT_ELITE_EXTREME = 0.97   # top ~14 of 462 hitters
_CAT_ELITE_STRONG  = 0.93   # top ~32 of 462 hitters
_CAT_ELITE_MILD    = 0.90   # top ~46 of 462 hitters

# Scarcity weights per category (for elite bonus calculation)
_CAT_SCARCITY: dict[str, float] = {
    'SB':  1.35,   # most scarce — fewest elite producers
    'AVG': 1.15,
    'HR':  1.05,
    'R':   1.00,
    'RBI': 1.00,
}

# Elite bonus per tier (× scarcity_weight × scarcity_premium), additive, capped at +0.40
_ELITE_EXTREME_BONUS = 0.15
_ELITE_STRONG_BONUS  = 0.10
_ELITE_MILD_BONUS    = 0.05
_ELITE_BONUS_CAP     = 0.40

# Scarcity liquidity premium per category × tier (applied on top of scarcity_weight)
# SB: cliff curve — irreplaceable at elite level.  AVG: gradual.  HR/R/RBI: no premium.
_CAT_SCARCITY_PREMIUM: dict[str, dict[str, float]] = {
    'SB':  {'EXTREME': 1.25, 'STRONG': 1.15, 'MILD': 1.10},
    'AVG': {'EXTREME': 1.05, 'STRONG': 1.00, 'MILD': 1.00},
    'HR':  {'EXTREME': 1.00, 'STRONG': 1.00, 'MILD': 1.00},
    'R':   {'EXTREME': 1.00, 'STRONG': 1.00, 'MILD': 1.00},
    'RBI': {'EXTREME': 1.00, 'STRONG': 1.00, 'MILD': 1.00},
}

# Tiered scarcity tier boundaries (percentile of raw h_score across all hitters)
_SCARCITY_TOP_PCT      = 0.85
_SCARCITY_MID_LOW_PCT  = 0.40
_SCARCITY_TOP_DAMP     = 0.25   # compress scarcity at elite tier
_SCARCITY_BOT_AMP      = 1.40   # amplify scarcity at bottom tier

_SP_BREADTH_THRESH  = 0.55
_SP_BREADTH_BASE    = 1.15      # 1.15^pitcher_breadth (fractional exponent)
_SP_WIN_PCT_GATE    = 0.520     # min team win% for W to count as a contribution

# FP rank tiered gate
_FP_EXCLUDE_GATE    = 200       # primary gate: fp_rank > this -> excluded
_FP_TIER2_GATE      = 150       # fp_rank 151-200 -> scored normally, capped post-scoring
_FP_ELITE_GATE      = 350       # elite pathway: fp_rank 201-350 (requires PA≥300 + cat≥p90)
_PA_ELITE_GATE      = 300       # elite pathway min PA projection
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

    # ── ROS fraction (used for projection overrides only) ────────────────────
    _ros = next((float(p['ros_fraction']) for p in players
                 if p.get('ros_fraction') is not None), 1.0)
    print(f"  Roto model (percentile-based breadth+elite, ros={_ros:.3f})")

    # ── Gate players + separate pools ─────────────────────────────────────────
    hitters: list[tuple[dict, str]] = []
    sp_pool: list[dict] = []
    rp_pool: list[dict] = []
    excluded_ids: set[int] = set()
    tier2_ids:    set[int] = set()
    _seen_ids:    set[int] = set()
    _hitter_candidates: list[tuple[dict, str]] = []   # all hitter-eligible, not yet gated

    for p in players:
        if p['id'] in _seen_ids:
            continue
        _seen_ids.add(p['id'])
        fpos = FPOS_MAP.get(p.get('pos', ''))
        if fpos in HITTER_FPOS:
            _hitter_candidates.append((p, fpos))
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

    # Hitter gate — Pass 1: primary qualification (fp_rank ≤ 200, PA_proj ≥ 400)
    _fringe_candidates: list[tuple[dict, str]] = []
    for p, fpos in _hitter_candidates:
        pa = float(p.get('PA_proj') or 0)
        fp = int(p.get('fp_rank') or 9999)
        if pa >= 400 and fp <= _FP_EXCLUDE_GATE:
            hitters.append((p, fpos))
            if fp > _FP_TIER2_GATE:
                tier2_ids.add(p['id'])
        elif pa >= _PA_ELITE_GATE and fp <= _FP_ELITE_GATE:
            _fringe_candidates.append((p, fpos))   # eligible for elite pathway
        else:
            excluded_ids.add(p['id'])

    # Global SB p90 — computed from ALL hitters PA≥300 regardless of fp_rank.
    # Used for (a) elite pathway SB gate and (b) scarce_sb_flag on all scored hitters.
    _global_hitters = [
        p for p in players
        if FPOS_MAP.get(p.get('pos', '')) in HITTER_FPOS
        and float(p.get('PA_proj') or 0) >= _PA_ELITE_GATE
    ]
    _global_sb_vals = sorted(float((p.get('proj') or {}).get('SB', 0)) for p in _global_hitters)
    _global_p90_sb_idx = max(0, int(0.90 * len(_global_sb_vals)) - 1)
    _global_p90_sb: float = _global_sb_vals[_global_p90_sb_idx] if _global_sb_vals else 9999.0

    # Hitter gate — Pass 2: elite category pathway (fp 201-350, PA ≥ 300, SB ≥ global p90)
    # SB-only gate: only SB specialists benefit from the fringe pathway; other category
    # elites in this fp range are adequately captured by the primary pool ranking.
    if _fringe_candidates:
        _elite_admitted = 0
        for p, fpos in _fringe_candidates:
            _proj = p.get('proj') or {}
            if float(_proj.get('SB', 0)) >= _global_p90_sb:
                hitters.append((p, fpos))
                tier2_ids.add(p['id'])    # fringe elites always get Tier 2 surplus cap
                _elite_admitted += 1
            else:
                excluded_ids.add(p['id'])

        if _elite_admitted:
            print(f"  Elite pathway: +{_elite_admitted} fringe hitters admitted "
                  f"(fp 201-350, PA≥300, SB≥global p90={_global_p90_sb:.1f})")

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
            # career_avg counting stats scaled by ros_fraction so they match
            # the already-scaled proj_stat from score_value.py
            _override_proj[_ov_id] = {
                'HR':  _w * (_ca['HR']  * _ros) + (1 - _w) * float(_op.get('HR')  or 0),
                'R':   _w * (_ca['R']   * _ros) + (1 - _w) * float(_op.get('R')   or 0),
                'RBI': _w * (_ca['RBI'] * _ros) + (1 - _w) * float(_op.get('RBI') or 0),
                'SB':  _w * (_ca['SB']  * _ros) + (1 - _w) * float(_op.get('SB')  or 0),
                'AVG': _w * _ca['AVG']           + (1 - _w) * float(_op.get('AVG') or 0),
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

    # ── Hitter breadth + category elite scores ───────────────────────────────
    h_scores: dict[int, float] = {}

    for p, _fpos in hitters:
        pid   = p['id']
        pcts  = h_percentiles[pid]

        # Breadth: count categories at p70+
        breadth_score = sum(
            1 for cat, _, _ in HITTER_CATS if pcts.get(cat, 0.0) >= _CAT_BREADTH_THRESH
        )
        breadth_mult = _BREADTH_MULT_TABLE[breadth_score]

        # Category elite flags (additive bonus, capped)
        cat_elite_bonus: float = 0.0
        cat_elite_flags: list[dict] = []
        for cat, _, _ in HITTER_CATS:
            pct = pcts.get(cat, 0.0)
            sc  = _CAT_SCARCITY.get(cat, 1.00)
            if pct >= _CAT_ELITE_EXTREME:
                tier_label = 'EXTREME'
                sp = _CAT_SCARCITY_PREMIUM.get(cat, {}).get(tier_label, 1.00)
                bonus = _ELITE_EXTREME_BONUS * sc * sp
                cat_elite_flags.append({'cat': cat, 'tier': tier_label,
                                        'pct': round(pct * 100, 1), 'bonus': round(bonus, 3),
                                        'scarcity_premium': sp})
                cat_elite_bonus += bonus
            elif pct >= _CAT_ELITE_STRONG:
                tier_label = 'STRONG'
                sp = _CAT_SCARCITY_PREMIUM.get(cat, {}).get(tier_label, 1.00)
                bonus = _ELITE_STRONG_BONUS * sc * sp
                cat_elite_flags.append({'cat': cat, 'tier': tier_label,
                                        'pct': round(pct * 100, 1), 'bonus': round(bonus, 3),
                                        'scarcity_premium': sp})
                cat_elite_bonus += bonus
            elif pct >= _CAT_ELITE_MILD:
                tier_label = 'MILD'
                sp = _CAT_SCARCITY_PREMIUM.get(cat, {}).get(tier_label, 1.00)
                bonus = _ELITE_MILD_BONUS * sc * sp
                cat_elite_flags.append({'cat': cat, 'tier': tier_label,
                                        'pct': round(pct * 100, 1), 'bonus': round(bonus, 3),
                                        'scarcity_premium': sp})
                cat_elite_bonus += bonus
        cat_elite_bonus = min(cat_elite_bonus, _ELITE_BONUS_CAP)

        base = sum(pcts.get(cat, 0.0) * w for cat, w, _ in HITTER_CATS)
        h_scores[pid] = base * breadth_mult + cat_elite_bonus

        _p_sb = float((_override_proj.get(pid) or (p.get('proj') or {})).get('SB', 0))
        extras[pid] = {
            'breadth_score':        breadth_score,
            'breadth_mult':         round(breadth_mult, 3),
            'orig_proj':            _orig_proj.get(pid),
            'category_elite_flags': cat_elite_flags,
            'category_elite_bonus': round(cat_elite_bonus, 3),
            'elite_count':          len(cat_elite_flags),   # backward compat
            'elite_bonus':          round(cat_elite_bonus, 3),  # backward compat
            'cat_pcts':             {cat: round(pcts.get(cat, 0.0) * 100, 1) for cat, _, _ in HITTER_CATS},
            'c_HR':  pcts.get('HR',  0.0) >= _CAT_BREADTH_THRESH,
            'c_R':   pcts.get('R',   0.0) >= _CAT_BREADTH_THRESH,
            'c_RBI': pcts.get('RBI', 0.0) >= _CAT_BREADTH_THRESH,
            'c_SB':  pcts.get('SB',  0.0) >= _CAT_BREADTH_THRESH,
            'c_AVG': pcts.get('AVG', 0.0) >= _CAT_BREADTH_THRESH,
            'scarce_sb_flag':       _p_sb >= _global_p90_sb,
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

    print(f"\n-- Pool calibration ({N} qualified hitters, percentile thresholds) --")
    print(f"  SB  (breadth>=p70 | mild>=p90 | strong>=p93 | extreme>=p97)")
    for pct in (0.70, 0.90, 0.93, 0.97):
        v = _pct_val(sb_vals, pct)
        label = {0.70: 'breadth', 0.90: 'mild', 0.93: 'strong', 0.97: 'extreme'}[pct]
        print(f"    p{pct:.0%}: {v:5.1f} SB  <- {label}")
    print(f"  HR  (breadth>=p70 | mild>=p90 | strong>=p93 | extreme>=p97)")
    for pct in (0.70, 0.90, 0.93, 0.97):
        v = _pct_val(hr_vals, pct)
        label = {0.70: 'breadth', 0.90: 'mild', 0.93: 'strong', 0.97: 'extreme'}[pct]
        print(f"    p{pct:.0%}: {v:5.1f} HR  <- {label}")
    print(f"  AVG (breadth>=p70 | mild>=p90 | strong>=p93 | extreme>=p97)")
    for pct in (0.70, 0.90, 0.93, 0.97):
        v = _pct_val(avg_vals, pct)
        label = {0.70: 'breadth', 0.90: 'mild', 0.93: 'strong', 0.97: 'extreme'}[pct]
        print(f"    p{pct:.0%}: {v:.3f} AVG <- {label}")
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
        p['roto_surplus_l1']      = rs
        ex = extras.get(pid, {})
        p['roto_breadth_count']   = ex.get('breadth_score')
        p['roto_breadth_mult']    = ex.get('breadth_mult')
        p['roto_elite_count']     = ex.get('elite_count')
        p['roto_elite_bonus']     = ex.get('category_elite_bonus')
        p['category_elite_flags'] = ex.get('category_elite_flags', [])
        p['scarce_sb_flag']       = ex.get('scarce_sb_flag', False)
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

    # ── Category elite breakdown for key validation players ───────────────────
    _validate_names = ['Nasim', 'Corbin Carroll', 'Yordan', 'Bobby Witt', 'Elly De']
    print("\nCategory elite breakdown (validation):")
    for p in players:
        if any(v.lower() in p['name'].lower() for v in _validate_names):
            ex   = extras.get(p['id'], {})
            rs   = surpluses.get(p['id'], 0.0)
            flags   = ex.get('category_elite_flags', [])
            cat_p   = ex.get('cat_pcts', {})
            flag_str = ', '.join(
                f"{f['cat']} {f['tier']} (p{f['pct']}, +{f['bonus']:.3f}, sp×{f.get('scarcity_premium',1.0):.2f})"
                for f in flags) if flags else 'none'
            scarce = '⚡' if ex.get('scarce_sb_flag') else ''
            print(f"  {p['name']:28s}  breadth={ex.get('breadth_score','?')}  "
                  f"mult={ex.get('breadth_mult','?')}  "
                  f"elite_bonus={ex.get('category_elite_bonus','?')}  "
                  f"roto_surplus={rs:+.1f}  {scarce}")
            print(f"    flags: {flag_str}")
            if cat_p:
                print(f"    pcts:  HR={cat_p.get('HR','?')}  R={cat_p.get('R','?')}  "
                      f"RBI={cat_p.get('RBI','?')}  SB={cat_p.get('SB','?')}  "
                      f"AVG={cat_p.get('AVG','?')}")

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
