"""
score_trend_signals_v2.py
Seven-layer rolling trend model for hitters using 2026 Statcast game logs.
Parallel architecture to score_luck.py — applied to 21-day rolling windows.

Layer 1 — xwOBA gap trend          (weight 1.0)
Layer 2 — Contact quality composite (weight 0.8)
Layer 3 — BABIP normalization       (weight 0.4)
Layer 4 — Plate discipline trend    (weight 0.5)
Layer 5 — Bat speed / swing health  (weight 0.3)
Layer 6 — Pitch vulnerability +     (additive modifier, penalty only)
           Batted ball profile shift
           Composite score = sum(L1-L5 * weights) + L6 modifier

Normalization: all percentage fields (hardhit, barrel, k_pct, bb_pct, whiff)
are divided by 100 before scoring to bring them to wOBA scale (~0.0–1.0).
Speed fields (launch_speed, bat_speed) are divided by SPEED_NORM=10 for the
same reason. Without normalization, speed deltas in mph would dominate.

Classification thresholds:
  trend_score >= +HOT_THRESH  : Hot
  trend_score <= -COLD_THRESH : Cold
  else                        : Flat

Save: data/trend_signals_v2_2026.csv

Do NOT deploy to dashboard until backtest v2 vs 2025 validates improvement over v1.
"""
import csv
import json
from datetime import date, timedelta
from pathlib import Path
from collections import defaultdict

# ── date windows (dynamic — 21-day rolling) ──────────────────────────────────
_today        = date.today()
RECENT_END    = _today - timedelta(days=1)       # yesterday (today's game not final)
RECENT_START  = RECENT_END - timedelta(days=20)  # 21-day window
PRIOR_END     = RECENT_START - timedelta(days=1)
PRIOR_START   = PRIOR_END - timedelta(days=20)   # 21-day prior window

# ── PA gates ─────────────────────────────────────────────────────────────────
MIN_PA_RECENT = 20
MIN_PA_PRIOR  = 15

# ── classification thresholds ────────────────────────────────────────────────
HOT_THRESH  =  0.030
COLD_THRESH = -0.030

# ── normalization constants ───────────────────────────────────────────────────
PCT_NORM   = 100.0   # hardhit_percent, barrel, k_pct, bb_pct, whiff → divide by 100
SPEED_NORM =  10.0   # launch_speed and bat_speed (mph) → divide by 10

# ── bat speed decline flag threshold ─────────────────────────────────────────
BAT_SPEED_FLAG_MPH = -1.0   # bs_delta < -1.0 mph → flag

# ── data paths ────────────────────────────────────────────────────────────────
GAMELOG_DIR  = Path("data/statcast_gamelogs_2026")
LUCK_CSV     = "luck_scores.csv"
OUT_PATH     = Path("data/trend_signals_v2_2026.csv")

# ── Layer 6 data paths ────────────────────────────────────────────────────────
PITCH_VALUES_CSV  = Path("data/fg_pitch_values_2024_2026.csv")
BATTED_BALL_CSV   = Path("data/fg_batted_ball_2024_2026.csv")
LA_JSON           = Path("data/hitter_launch_angle.json")
CAREER_BABIP_JSON = Path("data/hitter_career_babip.json")

# ── Layer 6 Sub-Signal A: pitch vulnerability thresholds ─────────────────────
L6_MIN_PITCHES   = 20    # min 2026 pitches of that type to qualify
L6_SEVERE_THRESH = -8.0  # wPT/C delta → severe
L6_MOD_THRESH    = -5.0  # moderate
L6_MILD_THRESH   = -3.0  # mild
L6_SEVERE_MOD    = -0.15
L6_MOD_MOD       = -0.10
L6_MILD_MOD      = -0.05

# ── Layer 6 Sub-Signal B: batted ball profile thresholds ──────────────────────
L6_BB_MIN_BBE    = 30    # min batted ball events for profile signal
L6_LD_DELTA_GATE = -0.04 # LD% must drop >= 4pp below expected
L6_FB_DELTA_GATE =  0.04 # FB% must rise >= 4pp above expected
L6_BB_MOD_BASE   = -0.08 # approach change alone
L6_BB_MOD_NOBRL  = -0.10 # approach change + no barrel support
L6_BARREL_FLOOR  = -0.01 # barrel_delta >= this → barrel is "supported"

# ── League-average LD%/FB% (used when career LA data unavailable) ─────────────
LEAGUE_AVG_LD = 0.200
LEAGUE_AVG_FB = 0.340


# ── helpers ───────────────────────────────────────────────────────────────────

def _safe_float(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _weighted_avg(rows, field: str, start: date, end: date, norm: float = 1.0):
    """PA-weighted average of field over [start, end]. Returns (value, total_pa)."""
    total_pa = 0
    total_wv = 0.0
    for r in rows:
        try:
            gd = date.fromisoformat(r["game_date"])
        except (KeyError, ValueError):
            continue
        if not (start <= gd <= end):
            continue
        pa  = _safe_float(r.get("pa"), 0)
        val = _safe_float(r.get(field))
        if pa and pa > 0 and val is not None:
            total_pa += int(pa)
            total_wv += (val / norm) * pa
    if total_pa == 0:
        return None, 0
    return total_wv / total_pa, total_pa


def _load_gamelogs(mlbam_id: int) -> list[dict]:
    path = GAMELOG_DIR / f"hitter_{mlbam_id}.csv"
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        content = f.read().lstrip("﻿")
    return list(csv.DictReader(content.splitlines()))


def _window_pair(rows, field, start_r, end_r, start_p, end_p, norm=1.0):
    """Returns (recent_val, recent_pa, prior_val, prior_pa) or Nones."""
    rv, rpa = _weighted_avg(rows, field, start_r, end_r, norm)
    pv, ppa = _weighted_avg(rows, field, start_p, end_p, norm)
    return rv, rpa, pv, ppa


def _delta(recent, prior):
    """recent – prior if both exist, else None."""
    if recent is None or prior is None:
        return None
    return recent - prior


def _score_player(rows) -> dict:
    """Compute all six layers. Returns dict of component values and trend_score."""
    R0, R1, P0, P1 = RECENT_START, RECENT_END, PRIOR_START, PRIOR_END

    # ── PA in each window (from xwoba field as proxy — same PA gating logic) ──
    _, rpa = _weighted_avg(rows, "xwoba", R0, R1)
    _, ppa = _weighted_avg(rows, "xwoba", P0, P1)

    # ── Layer 1: xwOBA gap trend ──────────────────────────────────────────────
    rxw,  _, pxw,  _ = _window_pair(rows, "xwoba",  R0, R1, P0, P1)
    rwob, _, pwob, _ = _window_pair(rows, "woba",   R0, R1, P0, P1)

    recent_gap = _delta(rxw, rwob)      # recent (xwOBA - wOBA) per-game
    prior_gap  = _delta(pxw, pwob)
    gap_delta  = _delta(recent_gap, prior_gap)   # positive = luck improving
    l1 = gap_delta * 1.0 if gap_delta is not None else None

    # ── Layer 2: Contact quality composite ───────────────────────────────────
    # hardhit and barrel on 0-100 scale → PCT_NORM; launch_speed in mph → SPEED_NORM
    rhh, _, phh, _ = _window_pair(rows, "hardhit_percent",      R0, R1, P0, P1, PCT_NORM)
    rbb, _, pbb, _ = _window_pair(rows, "barrels_per_bbe_percent", R0, R1, P0, P1, PCT_NORM)
    rev, _, pev, _ = _window_pair(rows, "launch_speed",         R0, R1, P0, P1, SPEED_NORM)

    hh_delta  = _delta(rhh, phh)
    brl_delta = _delta(rbb, pbb)
    ev_delta  = _delta(rev, pev)

    # Build composite only from available components
    cq_parts = []
    if hh_delta  is not None: cq_parts.append(0.5 * hh_delta)
    if brl_delta is not None: cq_parts.append(0.3 * brl_delta)
    if ev_delta  is not None: cq_parts.append(0.2 * ev_delta)

    if cq_parts:
        # Reweight to sum of actual component weights so missing fields don't shrink score
        w_available = (0.5 if hh_delta is not None else 0) + \
                      (0.3 if brl_delta is not None else 0) + \
                      (0.2 if ev_delta  is not None else 0)
        cq_score = sum(cq_parts) / w_available if w_available else None
        l2 = cq_score * 0.8
    else:
        cq_score = l2 = None

    # ── Layer 3: BABIP normalization ──────────────────────────────────────────
    # babip already 0-1 scale
    rbp, _, pbp, _ = _window_pair(rows, "babip", R0, R1, P0, P1)
    babip_delta = _delta(rbp, pbp)
    # Invert: falling BABIP on a buy player is positive (luck correcting)
    # But here we track raw BABIP trend for the composite; sign applied at summary
    l3 = babip_delta * 0.4 if babip_delta is not None else None

    # ── Layer 4: Plate discipline trend ──────────────────────────────────────
    # All pct fields 0-100 → PCT_NORM
    rkp, _, pkp, _ = _window_pair(rows, "k_percent",         R0, R1, P0, P1, PCT_NORM)
    rbp2,_, pbp2,_ = _window_pair(rows, "bb_percent",        R0, R1, P0, P1, PCT_NORM)
    rwh, _, pwh, _ = _window_pair(rows, "swing_miss_percent",R0, R1, P0, P1, PCT_NORM)

    kp_delta  = _delta(rkp,  pkp)
    bbp_delta = _delta(rbp2, pbp2)
    wh_delta  = _delta(rwh,  pwh)

    pd_parts  = []
    pd_w_avail = 0.0
    if kp_delta  is not None: pd_parts.append(-0.4 * kp_delta);  pd_w_avail += 0.4
    if bbp_delta is not None: pd_parts.append( 0.3 * bbp_delta); pd_w_avail += 0.3
    if wh_delta  is not None: pd_parts.append(-0.3 * wh_delta);  pd_w_avail += 0.3

    if pd_parts:
        pd_score = sum(pd_parts) / pd_w_avail if pd_w_avail else None
        l4 = pd_score * 0.5
    else:
        pd_score = l4 = None

    # ── Layer 5: Bat speed / swing health ────────────────────────────────────
    rbs, _, pbs, _ = _window_pair(rows, "bat_speed", R0, R1, P0, P1, SPEED_NORM)
    bs_delta   = _delta(rbs, pbs)
    bs_flag    = (bs_delta is not None and bs_delta < BAT_SPEED_FLAG_MPH / SPEED_NORM)
    l5 = bs_delta * 0.3 if bs_delta is not None else None

    # ── Layer 6: Composite trend score ────────────────────────────────────────
    layers = [l for l in [l1, l2, l3, l4, l5] if l is not None]
    n_layers_used = len(layers)
    trend_score = sum(layers) if layers else None

    return {
        "recent_pa":     rpa,
        "prior_pa":      ppa,
        # L1
        "recent_xwoba_gap": recent_gap,
        "prior_xwoba_gap":  prior_gap,
        "l1_gap_delta":     gap_delta,
        # L2
        "recent_hardhit":   rhh,
        "prior_hardhit":    phh,
        "hh_delta":         hh_delta,
        "brl_delta":        brl_delta,
        "ev_delta":         ev_delta,
        "l2_cq_score":      cq_score,
        # L3
        "recent_babip":  rbp,
        "prior_babip":   pbp,
        "babip_delta":   babip_delta,
        # L4
        "kp_delta":      kp_delta,
        "bbp_delta":     bbp_delta,
        "wh_delta":      wh_delta,
        "l4_pd_score":   pd_score,
        # L5
        "recent_bat_speed": rbs,
        "prior_bat_speed":  pbs,
        "bs_delta":         bs_delta,
        "bs_flag":          bs_flag,
        # composite
        "n_layers_used":  n_layers_used,
        "trend_score":    trend_score,
    }


def _classify(trend_score):
    if trend_score is None:
        return "Flat"
    if trend_score >= HOT_THRESH:
        return "Hot"
    if trend_score <= COLD_THRESH:
        return "Cold"
    return "Flat"


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 6 — Pitch Vulnerability + Batted Ball Profile
# ─────────────────────────────────────────────────────────────────────────────

# FanGraphs-style pitch column names (rate = per-100-pitches seen)
_PITCH_RATE_COLS = ["wFA/C", "wSI/C", "wFC/C", "wSL/C", "wCH/C", "wCU/C", "wFS/C"]
_PITCH_LABELS = {
    "wFA/C": "4-Seam",
    "wSI/C": "Sinker",
    "wFC/C": "Cutter",
    "wSL/C": "Slider",
    "wCH/C": "Changeup",
    "wCU/C": "Curveball",
    "wFS/C": "Splitter",
}


def _load_pitch_values() -> dict[str, dict[int, dict]]:
    """Load pitch values CSV into {player_id: {year: {col: val}}}."""
    if not PITCH_VALUES_CSV.exists():
        return {}
    out: dict[str, dict[int, dict]] = defaultdict(dict)
    with open(PITCH_VALUES_CSV, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            pid  = r.get("player_id", "").strip()
            yr   = _safe_float(r.get("season"))
            if not (pid and yr is not None):
                continue
            out[pid][int(yr)] = r
    return out


def _load_batted_ball() -> dict[str, dict]:
    """Load batted ball CSV into {player_id: row}."""
    if not BATTED_BALL_CSV.exists():
        return {}
    out = {}
    with open(BATTED_BALL_CSV, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            pid = str(r.get("id", "")).strip()
            if pid:
                out[pid] = r
    return out


def _load_la_data() -> dict[str, dict]:
    """Load hitter_launch_angle.json into {str(mlbam_id): row}."""
    if not LA_JSON.exists():
        return {}
    with open(LA_JSON, encoding="utf-8") as f:
        raw = json.load(f)
    return {str(k): v for k, v in raw.items()}


def _load_career_babip() -> dict[str, dict]:
    """Load hitter_career_babip.json into {str(mlbam_id): row}."""
    if not CAREER_BABIP_JSON.exists():
        return {}
    with open(CAREER_BABIP_JSON, encoding="utf-8") as f:
        raw = json.load(f)
    # raw can be list or dict
    if isinstance(raw, list):
        return {str(r.get("player_id", r.get("mlbam_id", ""))): r for r in raw}
    return {str(k): v for k, v in raw.items()}


def _expected_ld_fb_from_la(career_la_avg: float) -> tuple[float, float]:
    """
    Estimate expected LD% and FB% from a player's career average launch angle.
    Based on empirical LA-to-batted-ball-type distribution:
      LA ~12° → LD ≈22%, FB ≈30%
      LA ~16° → LD ≈20%, FB ≈34%
      LA ~20° → LD ≈18%, FB ≈38%
    Returns (expected_ld_pct, expected_fb_pct) as decimals.
    """
    la_diff = career_la_avg - 12.0
    expected_ld = max(0.12, min(0.28, 0.220 - 0.004 * la_diff))
    expected_fb = max(0.18, min(0.50, 0.300 + 0.010 * la_diff))
    return expected_ld, expected_fb


def _sub_signal_a(pitch_values: dict, mlbam_id: str) -> dict:
    """
    Sub-Signal A: Pitch vulnerability.
    Compare wPT/C (run value per 100 pitches) 2026 vs 2025 per pitch type.
    Returns dict with modifier and metadata.
    """
    player_pv = pitch_values.get(str(mlbam_id), {})
    row_2026  = player_pv.get(2026, {})
    row_2025  = player_pv.get(2025, {})

    if not row_2026 or not row_2025:
        return {
            "vulnerability_modifier": 0.0,
            "worst_pitch_type": "",
            "worst_pitch_delta": None,
            "vulnerability_severity": "none",
        }

    worst_delta = None
    worst_col   = ""

    for col in _PITCH_RATE_COLS:
        cnt_col = col.replace("/C", "_pitches")
        cnt_2026 = _safe_float(row_2026.get(cnt_col), 0)
        if cnt_2026 < L6_MIN_PITCHES:
            continue

        v_2026 = _safe_float(row_2026.get(col))
        v_2025 = _safe_float(row_2025.get(col))
        if v_2026 is None or v_2025 is None:
            continue

        delta = v_2026 - v_2025
        if worst_delta is None or delta < worst_delta:
            worst_delta = delta
            worst_col   = col

    if worst_delta is None:
        return {
            "vulnerability_modifier": 0.0,
            "worst_pitch_type": "",
            "worst_pitch_delta": None,
            "vulnerability_severity": "none",
        }

    if worst_delta < L6_SEVERE_THRESH:
        modifier   = L6_SEVERE_MOD
        severity   = "severe"
    elif worst_delta < L6_MOD_THRESH:
        modifier   = L6_MOD_MOD
        severity   = "moderate"
    elif worst_delta < L6_MILD_THRESH:
        modifier   = L6_MILD_MOD
        severity   = "mild"
    else:
        modifier  = 0.0
        severity  = "none"

    return {
        "vulnerability_modifier": modifier,
        "worst_pitch_type": _PITCH_LABELS.get(worst_col, worst_col),
        "worst_pitch_delta": round(worst_delta, 2),
        "vulnerability_severity": severity,
    }


def _sub_signal_b(
    batted_ball: dict,
    la_data: dict,
    career_babip: dict,
    luck_row: dict,
    mlbam_id: str,
) -> dict:
    """
    Sub-Signal B: Batted ball profile shift.
    Compare current LD%/FB% vs career expected, and barrel rate vs career.
    Returns dict with modifier and metadata.
    """
    _null = {
        "batted_ball_modifier": 0.0,
        "approach_change_flag": False,
        "barrel_supported": True,
        "ld_delta_pp": None,
        "fb_delta_pp": None,
        "barrel_delta_pp": None,
    }

    bb_row = batted_ball.get(str(mlbam_id))
    if bb_row is None:
        return _null

    bbe = _safe_float(bb_row.get("bbe"), 0)
    if bbe < L6_BB_MIN_BBE:
        return _null

    ld_2026 = _safe_float(bb_row.get("ld_rate"))
    fb_2026 = _safe_float(bb_row.get("fb_rate"))
    if ld_2026 is None or fb_2026 is None:
        return _null

    # Career LD%/FB% estimated from launch angle profile
    la_row = la_data.get(str(mlbam_id))
    if la_row and _safe_float(la_row.get("career_la_avg")) is not None:
        career_la = _safe_float(la_row["career_la_avg"])
        exp_ld, exp_fb = _expected_ld_fb_from_la(career_la)
    else:
        exp_ld = LEAGUE_AVG_LD
        exp_fb = LEAGUE_AVG_FB

    ld_delta = ld_2026 - exp_ld   # negative = fewer LD than career profile
    fb_delta = fb_2026 - exp_fb   # positive = more FB than career profile

    approach_change = (ld_delta < L6_LD_DELTA_GATE) and (fb_delta > L6_FB_DELTA_GATE)

    # Barrel support: compare current barrel_rate vs career_barrel
    barrel_2026    = _safe_float(luck_row.get("barrel_rate"))
    cr_row         = career_babip.get(str(mlbam_id))
    career_barrel  = _safe_float(cr_row.get("career_barrel") if cr_row else None)
    barrel_delta   = (barrel_2026 - career_barrel) if (barrel_2026 is not None and career_barrel is not None) else None
    barrel_support = (barrel_delta is None) or (barrel_delta >= L6_BARREL_FLOOR)

    if not approach_change:
        modifier = 0.0
    elif barrel_support:
        modifier = L6_BB_MOD_BASE
    else:
        modifier = L6_BB_MOD_NOBRL

    return {
        "batted_ball_modifier": modifier,
        "approach_change_flag": approach_change,
        "barrel_supported": barrel_support,
        "ld_delta_pp": round(ld_delta * 100, 1) if ld_delta is not None else None,
        "fb_delta_pp": round(fb_delta * 100, 1) if fb_delta is not None else None,
        "barrel_delta_pp": round(barrel_delta * 100, 1) if barrel_delta is not None else None,
    }


def calculate_layer6(records: list[dict], luck_rows: dict) -> list[dict]:
    """
    Compute Layer 6 (pitch vulnerability + batted ball profile) for all records.
    Mutates records in-place, adding layer6_* fields and trend_score_final.
    Returns records for chaining.
    """
    print("Loading Layer 6 data sources...")
    pitch_values  = _load_pitch_values()
    batted_ball   = _load_batted_ball()
    la_data       = _load_la_data()
    career_babip  = _load_career_babip()
    print(f"  Pitch values: {len(pitch_values)} players (multi-year)")
    print(f"  Batted ball:  {len(batted_ball)} players (2026 YTD)")
    print(f"  LA data:      {len(la_data)} players")
    print(f"  Career BABIP: {len(career_babip)} players")

    for rec in records:
        mlbam_id = str(rec["mlbam_id"])
        luck_row = luck_rows.get(int(mlbam_id), {})

        sa = _sub_signal_a(pitch_values, mlbam_id)
        sb = _sub_signal_b(batted_ball, la_data, career_babip, luck_row, mlbam_id)

        v_mod = sa["vulnerability_modifier"]
        b_mod = sb["batted_ball_modifier"]

        # Combined modifier: if both fire, cap at -0.15 with extra -0.05 penalty
        if v_mod < 0 and b_mod < 0:
            combined = max(-0.15, min(v_mod, b_mod) - 0.05)
        else:
            combined = v_mod + b_mod

        rec["layer6_modifier"]         = round(combined, 4)
        rec["worst_pitch_vulnerability"] = sa["worst_pitch_type"]
        rec["worst_pitch_delta"]         = sa["worst_pitch_delta"]
        rec["vulnerability_severity"]    = sa["vulnerability_severity"]
        rec["approach_change_flag"]      = sb["approach_change_flag"]
        rec["barrel_supported"]          = sb["barrel_supported"]
        rec["ld_delta_pp"]               = sb["ld_delta_pp"]
        rec["fb_delta_pp"]               = sb["fb_delta_pp"]
        rec["barrel_delta_pp"]           = sb["barrel_delta_pp"]
        rec["trend_score_final"]         = round(
            rec["trend_score"] + combined, 4
        )

        # Human-readable notes
        notes = []
        if sa["vulnerability_severity"] != "none":
            notes.append(
                f"{sa['vulnerability_severity'].capitalize()} {sa['worst_pitch_type']} vulnerability "
                f"(Δ{sa['worst_pitch_delta']:+.1f}/100)"
            )
        if sb["approach_change_flag"]:
            brl_note = "barrel supported" if sb["barrel_supported"] else "no barrel support"
            notes.append(
                f"Approach shift: LD{sb['ld_delta_pp']:+.1f}pp / FB{sb['fb_delta_pp']:+.1f}pp "
                f"vs career profile ({brl_note})"
            )
        rec["layer6_notes"] = "; ".join(notes) if notes else ""

    return records


def main():
    print("=" * 65)
    print("TREND SIGNALS v2 — SEVEN-LAYER ROLLING MODEL (2026)")
    print("=" * 65)
    print(f"Recent window:  {RECENT_START} → {RECENT_END}")
    print(f"Prior window:   {PRIOR_START} → {PRIOR_END}")
    print(f"Hot/Cold:       |trend_score| >= {HOT_THRESH}")
    print(f"Min PA:         recent≥{MIN_PA_RECENT}, prior≥{MIN_PA_PRIOR}")
    print()

    # ── load luck scores for name + verdict context + L6 fields ─────────────
    luck      = {}   # int(mlbam_id) → summary dict for trend scoring
    luck_rows = {}   # int(mlbam_id) → full row dict for Layer 6
    with open(LUCK_CSV, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            bid = _safe_float(r.get("batter"))
            if bid is None:
                continue
            ibid = int(bid)
            luck[ibid] = {
                "name":       r.get("name", ""),
                "verdict":    r.get("verdict", ""),
                "luck_score": _safe_float(r.get("luck_score")),
            }
            luck_rows[ibid] = r

    records = []
    skip_nolog = skip_minpa = skip_noscore = 0

    for mlbam_id, meta in luck.items():
        rows = _load_gamelogs(mlbam_id)
        if not rows:
            skip_nolog += 1
            continue

        sc = _score_player(rows)

        if sc["recent_pa"] < MIN_PA_RECENT or sc["prior_pa"] < MIN_PA_PRIOR:
            skip_minpa += 1
            continue

        if sc["trend_score"] is None:
            skip_noscore += 1
            continue

        trend_dir = _classify(sc["trend_score"])

        records.append({
            "mlbam_id":     mlbam_id,
            "name":         meta["name"],
            "verdict":      meta["verdict"],
            "luck_score":   meta["luck_score"],
            "trend_dir":    trend_dir,
            "trend_score":  sc["trend_score"],
            "n_layers":     sc["n_layers_used"],
            # window sizes
            "recent_pa":    sc["recent_pa"],
            "prior_pa":     sc["prior_pa"],
            # component detail
            "l1_gap_delta":    sc["l1_gap_delta"],
            "l2_cq_score":     sc["l2_cq_score"],
            "babip_delta":     sc["babip_delta"],
            "l4_pd_score":     sc["l4_pd_score"],
            "bs_delta_mph":    (sc["bs_delta"] * SPEED_NORM) if sc["bs_delta"] is not None else None,
            "bs_flag":         sc["bs_flag"],
            # raw windows for audit
            "recent_xwoba_gap": sc["recent_xwoba_gap"],
            "prior_xwoba_gap":  sc["prior_xwoba_gap"],
            "hh_delta_pp":   (sc["hh_delta"] * PCT_NORM) if sc["hh_delta"] is not None else None,
            "brl_delta_pp":  (sc["brl_delta"] * PCT_NORM) if sc["brl_delta"] is not None else None,
            "ev_delta_mph":  (sc["ev_delta"] * SPEED_NORM) if sc["ev_delta"] is not None else None,
            "recent_babip":    sc["recent_babip"],
            "prior_babip":     sc["prior_babip"],
        })

    print(f"Qualified players: {len(records)}")
    print(f"  No game log:   {skip_nolog}")
    print(f"  Min PA fail:   {skip_minpa}")
    print(f"  No score:      {skip_noscore}")
    print()

    # ── Layer 6: pitch vulnerability + batted ball profile ────────────────────
    print("=" * 65)
    print("LAYER 6 — PITCH VULNERABILITY + BATTED BALL PROFILE")
    print("=" * 65)
    records = calculate_layer6(records, luck_rows)
    print()

    # ── distribution ─────────────────────────────────────────────────────────
    by_dir  = defaultdict(list)
    for p in records:
        by_dir[p["trend_dir"]].append(p)

    hot   = sorted(by_dir["Hot"],  key=lambda x: -x["trend_score"])
    cold  = sorted(by_dir["Cold"], key=lambda x:  x["trend_score"])
    flat  = by_dir["Flat"]

    print("=" * 65)
    print(f"TREND DISTRIBUTION")
    print("=" * 65)
    print(f"  Hot:   {len(hot)}")
    print(f"  Cold:  {len(cold)}")
    print(f"  Flat:  {len(flat)}")

    def _score_dist(players):
        scores = [p["trend_score"] for p in players]
        if not scores:
            return "n/a"
        return f"min={min(scores):.3f}  max={max(scores):.3f}  mean={sum(scores)/len(scores):.3f}"

    print(f"  Hot score range:  {_score_dist(hot)}")
    print(f"  Cold score range: {_score_dist(cold)}")

    # ── top 10 hot ────────────────────────────────────────────────────────────
    print()
    print("=" * 65)
    print("TOP 10 HOT PLAYERS")
    print("=" * 65)
    print(f"  {'Name':<24} {'Verdict':<12} {'Score':>7}  {'L1':>6} {'L2':>6} {'L3':>6} {'L4':>6} {'L5':>6}  {'rPA':>4} {'pPA':>4}")
    print(f"  {'-'*85}")
    for p in hot[:10]:
        l1 = f"{p['l1_gap_delta']:.3f}" if p['l1_gap_delta'] is not None else "  n/a"
        l2 = f"{p['l2_cq_score']:.3f}"  if p['l2_cq_score']  is not None else "  n/a"
        l3 = f"{p['babip_delta']:.3f}"  if p['babip_delta']   is not None else "  n/a"
        l4 = f"{p['l4_pd_score']:.3f}"  if p['l4_pd_score']   is not None else "  n/a"
        l5 = f"{p['bs_delta_mph']:.1f}" if p['bs_delta_mph']  is not None else "  n/a"
        print(f"  {p['name']:<24} {p['verdict']:<12} {p['trend_score']:>7.3f}  "
              f"{l1:>6} {l2:>6} {l3:>6} {l4:>6} {l5:>6}  "
              f"{p['recent_pa']:>4} {p['prior_pa']:>4}")

    # ── top 10 cold ───────────────────────────────────────────────────────────
    print()
    print("=" * 65)
    print("TOP 10 COLD PLAYERS")
    print("=" * 65)
    print(f"  {'Name':<24} {'Verdict':<12} {'Score':>7}  {'L1':>6} {'L2':>6} {'L3':>6} {'L4':>6} {'L5':>6}  {'rPA':>4} {'pPA':>4}")
    print(f"  {'-'*85}")
    for p in cold[:10]:
        l1 = f"{p['l1_gap_delta']:.3f}" if p['l1_gap_delta'] is not None else "  n/a"
        l2 = f"{p['l2_cq_score']:.3f}"  if p['l2_cq_score']  is not None else "  n/a"
        l3 = f"{p['babip_delta']:.3f}"  if p['babip_delta']   is not None else "  n/a"
        l4 = f"{p['l4_pd_score']:.3f}"  if p['l4_pd_score']   is not None else "  n/a"
        l5 = f"{p['bs_delta_mph']:.1f}" if p['bs_delta_mph']  is not None else "  n/a"
        print(f"  {p['name']:<24} {p['verdict']:<12} {p['trend_score']:>7.3f}  "
              f"{l1:>6} {l2:>6} {l3:>6} {l4:>6} {l5:>6}  "
              f"{p['recent_pa']:>4} {p['prior_pa']:>4}")

    # ── bat speed flags ───────────────────────────────────────────────────────
    bs_flagged = [p for p in records if p["bs_flag"]]
    print()
    print("=" * 65)
    print(f"BAT SPEED DECLINE FLAGS  (drop > {abs(BAT_SPEED_FLAG_MPH):.1f} mph recent vs prior)")
    print("=" * 65)
    if bs_flagged:
        bs_flagged_sorted = sorted(bs_flagged, key=lambda x: x["bs_delta_mph"] or 0)
        for p in bs_flagged_sorted:
            recent_bs = (p["bs_delta_mph"] or 0) + \
                        ((p["prior_bat_speed"] if hasattr(p, "prior_bat_speed") else 0) or 0)
            print(f"  {p['name']:<24} {p['verdict']:<12} "
                  f"bs_delta={p['bs_delta_mph']:.1f} mph  trend={p['trend_dir']}  score={p['trend_score']:.3f}")
    else:
        print("  None flagged.")

    # ── score distribution (for threshold calibration) ────────────────────────
    all_scores = sorted(p["trend_score"] for p in records)
    if all_scores:
        n = len(all_scores)
        p10 = all_scores[int(n * 0.10)]
        p25 = all_scores[int(n * 0.25)]
        p75 = all_scores[int(n * 0.75)]
        p90 = all_scores[int(n * 0.90)]
        print()
        print("=" * 65)
        print("SCORE DISTRIBUTION (for threshold calibration)")
        print("=" * 65)
        print(f"  n={n}  min={all_scores[0]:.3f}  p10={p10:.3f}  p25={p25:.3f}  "
              f"median={all_scores[n//2]:.3f}  p75={p75:.3f}  p90={p90:.3f}  max={all_scores[-1]:.3f}")
        print(f"  Current threshold ±{HOT_THRESH} → "
              f"Hot={len(hot)}({len(hot)/n*100:.0f}%)  "
              f"Cold={len(cold)}({len(cold)/n*100:.0f}%)  "
              f"Flat={len(flat)}({len(flat)/n*100:.0f}%)")

    # ── Layer 6 summary ───────────────────────────────────────────────────────
    l6_flagged = [p for p in records if p.get("layer6_modifier", 0) < 0]
    l6_flagged_sorted = sorted(l6_flagged, key=lambda x: x.get("layer6_modifier", 0))

    print()
    print("=" * 65)
    print(f"LAYER 6 FLAGS  ({len(l6_flagged)} players penalized)")
    print("=" * 65)
    print(f"  {'Name':<24} {'Verdict':<12} {'Before':>7} {'After':>7} {'L6Mod':>7}  Notes")
    print(f"  {'-'*90}")
    for p in l6_flagged_sorted:
        print(f"  {p['name']:<24} {p['verdict']:<12} "
              f"{p['trend_score']:>7.3f} {p['trend_score_final']:>7.3f} "
              f"{p['layer6_modifier']:>+7.4f}  {p['layer6_notes']}")

    # ── Merrill spotlight ─────────────────────────────────────────────────────
    merrill_list = [p for p in records if "merrill" in p.get("name", "").lower()]
    if merrill_list:
        m = merrill_list[0]
        print()
        print("=" * 65)
        print("JACKSON MERRILL — FULL LAYER 6 BREAKDOWN")
        print("=" * 65)
        print(f"  Name:          {m['name']}")
        print(f"  Verdict:       {m['verdict']}  (luck_score={m.get('luck_score','?')})")
        print(f"  trend_score:   {m['trend_score']:.4f}  (L1-L5 composite)")
        print(f"  layer6_modifier: {m['layer6_modifier']:+.4f}")
        print(f"  trend_score_final: {m['trend_score_final']:.4f}")
        print(f"  --- Sub-Signal A: Pitch Vulnerability ---")
        print(f"  Worst pitch type: {m.get('worst_pitch_vulnerability','n/a')}")
        print(f"  Worst delta (2026-2025 wPT/C): {m.get('worst_pitch_delta','n/a')}")
        print(f"  Severity: {m.get('vulnerability_severity','n/a')}")
        print(f"  --- Sub-Signal B: Batted Ball Profile ---")
        print(f"  Approach change flag: {m.get('approach_change_flag','n/a')}")
        print(f"  LD delta (vs career profile): {m.get('ld_delta_pp','n/a')} pp")
        print(f"  FB delta (vs career profile): {m.get('fb_delta_pp','n/a')} pp")
        print(f"  Barrel delta (vs career): {m.get('barrel_delta_pp','n/a')} pp")
        print(f"  Barrel supported: {m.get('barrel_supported','n/a')}")
        print(f"  Notes: {m.get('layer6_notes','(none)')}")

    # ── save ──────────────────────────────────────────────────────────────────
    fieldnames = [
        "mlbam_id", "name", "verdict", "luck_score",
        "trend_dir", "trend_score", "trend_score_final", "n_layers",
        "recent_pa", "prior_pa",
        "l1_gap_delta", "l2_cq_score", "babip_delta", "l4_pd_score",
        "bs_delta_mph", "bs_flag",
        "recent_xwoba_gap", "prior_xwoba_gap",
        "hh_delta_pp", "brl_delta_pp", "ev_delta_mph",
        "recent_babip", "prior_babip",
        # Layer 6 columns
        "layer6_modifier",
        "worst_pitch_vulnerability", "worst_pitch_delta", "vulnerability_severity",
        "approach_change_flag", "barrel_supported",
        "ld_delta_pp", "fb_delta_pp", "barrel_delta_pp",
        "layer6_notes",
    ]
    with open(OUT_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for p in sorted(records, key=lambda x: -x.get("trend_score_final", x["trend_score"])):
            row = {}
            for k in fieldnames:
                v = p.get(k)
                row[k] = f"{v:.4f}" if isinstance(v, float) else v
            w.writerow(row)
    print(f"\nSaved: {OUT_PATH} ({len(records)} rows)")
    print(f"Windows: recent {RECENT_START}→{RECENT_END}  prior {PRIOR_START}→{PRIOR_END}")


if __name__ == "__main__":
    main()
