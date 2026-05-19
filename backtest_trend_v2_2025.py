"""
backtest_trend_v2_2025.py
Part A: Recalibrate 2026 trend thresholds using p20/p80 percentiles.
Part B: Apply v2 seven-layer formula to 2025 game logs, validate against ROS wOBA.
Part C: Compare v2 vs v1 within Buy Low and Sell High tiers.

v2 formula mirrors score_trend_signals_v2.py but with 2025 date windows.
Thresholds computed within each year's own distribution (not cross-year).
"""
import csv
from datetime import date
from pathlib import Path
from collections import defaultdict

# ── 2025 backtest date windows (fixed, matching backtest_trend_signals_proper.py) ──
BT_RECENT_START = date(2025, 4, 26)
BT_RECENT_END   = date(2025, 5, 17)
BT_PRIOR_START  = date(2025, 4,  5)
BT_PRIOR_END    = date(2025, 4, 25)

# ── PA gates ──────────────────────────────────────────────────────────────────
MIN_PA_RECENT = 20
MIN_PA_PRIOR  = 15

# ── normalization (same as production model) ──────────────────────────────────
PCT_NORM   = 100.0
SPEED_NORM =  10.0
BAT_SPEED_FLAG_MPH = -1.0

# ── paths ─────────────────────────────────────────────────────────────────────
GAMELOG_2025 = Path("data/statcast_gamelogs_2025")
GAMELOG_2026 = Path("data/statcast_gamelogs_2026")
AUDIT_CSV    = "data/backtest_audit_hitters.csv"
BT_A_CSV     = "data/backtest_A_hitters_2025.csv"
V2_2026_CSV  = Path("data/trend_signals_v2_2026.csv")
OUT_CSV      = Path("data/trend_signal_v2_backtest_stratified_2025.csv")

# ── v1 numbers (from backtest_trend_stratified_2025.csv) for comparison ───────
V1 = {
    ("Buy Low",   "Hot"):  {"n": 11, "acc": 1.000, "ros": 0.355},
    ("Buy Low",   "Cold"): {"n":  7, "acc": 0.857, "ros": 0.345},
    ("Buy Low",   "Flat"): {"n":  5, "acc": 1.000, "ros": 0.336},
    ("Buy Low",   "base"): {"n": 23, "acc": 0.957, "ros": 0.348},
    ("Sell High", "Hot"):  {"n":  4, "acc": 1.000, "ros": 0.322},
    ("Sell High", "Cold"): {"n":  3, "acc": 1.000, "ros": 0.315},
    ("Sell High", "Flat"): {"n":  2, "acc": 1.000, "ros": None},
    ("Sell High", "base"): {"n":  9, "acc": 1.000, "ros": 0.319},
}


# ─────────────────────────────────────────────────────────────────────────────
# Core helpers
# ─────────────────────────────────────────────────────────────────────────────

def _safe_float(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _weighted_avg(rows, field, start, end, norm=1.0):
    total_pa, total_wv = 0, 0.0
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


def _delta(a, b):
    return (a - b) if (a is not None and b is not None) else None


def _score_player_v2(rows, recent_start, recent_end, prior_start, prior_end):
    """Apply v2 seven-layer formula to game log rows with given date windows."""
    R0, R1, P0, P1 = recent_start, recent_end, prior_start, prior_end

    # PA gating via xwoba field
    _, rpa = _weighted_avg(rows, "xwoba", R0, R1)
    _, ppa = _weighted_avg(rows, "xwoba", P0, P1)

    # Layer 1 — xwOBA gap trend (weight 1.0)
    rxw,  _, pxw,  _ = _weighted_avg(rows, "xwoba",  R0, R1)[0], 0, \
                        _weighted_avg(rows, "xwoba",  P0, P1)[0], 0
    rxw  = _weighted_avg(rows, "xwoba",  R0, R1)[0]
    rwob = _weighted_avg(rows, "woba",   R0, R1)[0]
    pxw  = _weighted_avg(rows, "xwoba",  P0, P1)[0]
    pwob = _weighted_avg(rows, "woba",   P0, P1)[0]

    recent_gap = _delta(rxw, rwob)
    prior_gap  = _delta(pxw, pwob)
    gap_delta  = _delta(recent_gap, prior_gap)
    l1 = gap_delta * 1.0 if gap_delta is not None else None

    # Layer 2 — Contact quality composite (weight 0.8)
    rhh  = _weighted_avg(rows, "hardhit_percent",       R0, R1, PCT_NORM)[0]
    phh  = _weighted_avg(rows, "hardhit_percent",       P0, P1, PCT_NORM)[0]
    rbb  = _weighted_avg(rows, "barrels_per_bbe_percent", R0, R1, PCT_NORM)[0]
    pbb  = _weighted_avg(rows, "barrels_per_bbe_percent", P0, P1, PCT_NORM)[0]
    rev  = _weighted_avg(rows, "launch_speed",          R0, R1, SPEED_NORM)[0]
    pev  = _weighted_avg(rows, "launch_speed",          P0, P1, SPEED_NORM)[0]

    hh_d  = _delta(rhh, phh)
    brl_d = _delta(rbb, pbb)
    ev_d  = _delta(rev, pev)

    cq_parts, cq_w = [], 0.0
    if hh_d  is not None: cq_parts.append(0.5 * hh_d);  cq_w += 0.5
    if brl_d is not None: cq_parts.append(0.3 * brl_d); cq_w += 0.3
    if ev_d  is not None: cq_parts.append(0.2 * ev_d);  cq_w += 0.2
    cq_score = (sum(cq_parts) / cq_w) if cq_w > 0 else None
    l2 = cq_score * 0.8 if cq_score is not None else None

    # Layer 3 — BABIP normalization (weight 0.4)
    rbp = _weighted_avg(rows, "babip", R0, R1)[0]
    pbp = _weighted_avg(rows, "babip", P0, P1)[0]
    babip_d = _delta(rbp, pbp)
    l3 = babip_d * 0.4 if babip_d is not None else None

    # Layer 4 — Plate discipline trend (weight 0.5)
    rkp  = _weighted_avg(rows, "k_percent",          R0, R1, PCT_NORM)[0]
    pkp  = _weighted_avg(rows, "k_percent",          P0, P1, PCT_NORM)[0]
    rbbp = _weighted_avg(rows, "bb_percent",         R0, R1, PCT_NORM)[0]
    pbbp = _weighted_avg(rows, "bb_percent",         P0, P1, PCT_NORM)[0]
    rwh  = _weighted_avg(rows, "swing_miss_percent", R0, R1, PCT_NORM)[0]
    pwh  = _weighted_avg(rows, "swing_miss_percent", P0, P1, PCT_NORM)[0]

    kp_d  = _delta(rkp,  pkp)
    bbp_d = _delta(rbbp, pbbp)
    wh_d  = _delta(rwh,  pwh)

    pd_parts, pd_w = [], 0.0
    if kp_d  is not None: pd_parts.append(-0.4 * kp_d);  pd_w += 0.4
    if bbp_d is not None: pd_parts.append( 0.3 * bbp_d); pd_w += 0.3
    if wh_d  is not None: pd_parts.append(-0.3 * wh_d);  pd_w += 0.3
    pd_score = (sum(pd_parts) / pd_w) if pd_w > 0 else None
    l4 = pd_score * 0.5 if pd_score is not None else None

    # Layer 5 — Bat speed / swing health (weight 0.3)
    rbs = _weighted_avg(rows, "bat_speed", R0, R1, SPEED_NORM)[0]
    pbs = _weighted_avg(rows, "bat_speed", P0, P1, SPEED_NORM)[0]
    bs_d   = _delta(rbs, pbs)
    bs_flag = bs_d is not None and bs_d < BAT_SPEED_FLAG_MPH / SPEED_NORM
    l5 = bs_d * 0.3 if bs_d is not None else None

    layers = [l for l in [l1, l2, l3, l4, l5] if l is not None]
    trend_score = sum(layers) if layers else None

    return {
        "trend_score": trend_score,
        "recent_pa": rpa, "prior_pa": ppa,
        "l1": l1, "l2": l2, "l3": l3, "l4": l4, "l5": l5,
        "bs_flag": bs_flag,
        "n_layers": len(layers),
    }


def _load_gamelogs(gamelog_dir, mlbam_id, prefix="hitter"):
    path = gamelog_dir / f"{prefix}_{mlbam_id}.csv"
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        content = f.read().lstrip("﻿")
    return list(csv.DictReader(content.splitlines()))


def _percentile(scores, pct):
    """Simple percentile on sorted list (0-100 scale)."""
    if not scores:
        return None
    s = sorted(scores)
    k = (len(s) - 1) * pct / 100.0
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def _classify_pct(score, p20, p80):
    if score is None:
        return "Flat"
    if score >= p80:
        return "Hot"
    if score <= p20:
        return "Cold"
    return "Flat"


def _group_stats(players):
    if not players:
        return {"n": 0, "acc": None, "ros": None}
    ros    = [p["ros_woba"] for p in players if p["ros_woba"] is not None]
    corrects = [p["audit_correct"] for p in players]
    return {
        "n":   len(players),
        "acc": sum(corrects) / len(corrects) if corrects else None,
        "ros": sum(ros) / len(ros) if ros else None,
    }


def _fmt_row(label, st, v1_key=None):
    acc_s = f"{st['acc']*100:.1f}%" if st["acc"] is not None else "  n/a "
    ros_s = f".{round(st['ros']*1000):03d}" if st["ros"] is not None else " n/a"
    base  = f"  {label:<28}  n={st['n']:<3}  acc={acc_s}  ROS wOBA={ros_s}"
    if v1_key and v1_key in V1:
        v = V1[v1_key]
        v_acc_s = f"{v['acc']*100:.1f}%" if v["acc"] is not None else "  n/a "
        v_ros_s = f".{round(v['ros']*1000):03d}" if v["ros"] is not None else " n/a"
        d_acc = ((st["acc"] or 0) - v["acc"]) * 100 if st["acc"] is not None else None
        d_ros = ((st["ros"] or 0) - (v["ros"] or 0)) * 1000 if (st["ros"] and v["ros"]) else None
        d_acc_s = f"{d_acc:+.1f}pp" if d_acc is not None else "   n/a"
        d_ros_s = f"{d_ros:+.1f}pt" if d_ros is not None else "   n/a"
        base += f"  ||  v1 n={v['n']}  acc={v_acc_s}  ROS={v_ros_s}  Δacc={d_acc_s}  Δros={d_ros_s}"
    return base


# ─────────────────────────────────────────────────────────────────────────────
# PART A — Recalibrate 2026 with p20/p80
# ─────────────────────────────────────────────────────────────────────────────

def part_a():
    if not V2_2026_CSV.exists():
        print("data/trend_signals_v2_2026.csv not found — run score_trend_signals_v2.py first")
        return None, None

    rows_2026 = list(csv.DictReader(open(V2_2026_CSV, encoding="utf-8")))
    scores_2026 = [_safe_float(r["trend_score"]) for r in rows_2026
                   if _safe_float(r["trend_score"]) is not None]

    p20 = _percentile(scores_2026, 20)
    p80 = _percentile(scores_2026, 80)

    print("=" * 70)
    print("PART A — 2026 CALIBRATION  (percentile-based thresholds)")
    print("=" * 70)
    print(f"  n={len(scores_2026)}  "
          f"min={min(scores_2026):.3f}  "
          f"p10={_percentile(scores_2026,10):.3f}  "
          f"p20={p20:.3f}  "
          f"p50={_percentile(scores_2026,50):.3f}  "
          f"p80={p80:.3f}  "
          f"p90={_percentile(scores_2026,90):.3f}  "
          f"max={max(scores_2026):.3f}")
    print(f"\n  New thresholds:  Hot >= p80 = {p80:.3f}   Cold <= p20 = {p20:.3f}")

    # Reclassify
    hot = [r for r in rows_2026 if _safe_float(r["trend_score"], -99) >= p80]
    cold = [r for r in rows_2026 if _safe_float(r["trend_score"],  99) <= p20]
    flat = [r for r in rows_2026
            if p20 < _safe_float(r["trend_score"], 0) < p80]

    n = len(rows_2026)
    print(f"\n  Distribution:  Hot={len(hot)} ({len(hot)/n*100:.0f}%)  "
          f"Cold={len(cold)} ({len(cold)/n*100:.0f}%)  "
          f"Flat={len(flat)} ({len(flat)/n*100:.0f}%)")

    print(f"\n  TOP 10 HOT  (score >= {p80:.3f})")
    print(f"  {'Name':<24} {'Verdict':<12} {'Score':>7}  {'Luck':>7}")
    print(f"  {'-'*60}")
    for r in sorted(hot, key=lambda x: -float(x["trend_score"]))[:10]:
        print(f"  {r['name']:<24} {r['verdict']:<12} "
              f"{float(r['trend_score']):>7.3f}  {float(r['luck_score'] or 0):>7.3f}")

    print(f"\n  TOP 10 COLD  (score <= {p20:.3f})")
    print(f"  {'Name':<24} {'Verdict':<12} {'Score':>7}  {'Luck':>7}")
    print(f"  {'-'*60}")
    for r in sorted(cold, key=lambda x: float(x["trend_score"]))[:10]:
        print(f"  {r['name']:<24} {r['verdict']:<12} "
              f"{float(r['trend_score']):>7.3f}  {float(r['luck_score'] or 0):>7.3f}")

    return p20, p80


# ─────────────────────────────────────────────────────────────────────────────
# PART B — 2025 v2 backtest
# ─────────────────────────────────────────────────────────────────────────────

def part_b_and_c():
    # Load luck signals (2025 cohort)
    audit = {}
    with open(AUDIT_CSV, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("year") != "2025":
                continue
            mid = int(r["mlbam_id"])
            audit[mid] = {
                "name":          r["player_name"],
                "luck_signal":   r["signal"],
                "audit_correct": r.get("correct", "").lower() == "true",
            }

    # Load ROS wOBA validation targets
    ros_map = {}
    with open(BT_A_CSV, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            mid = _safe_float(r.get("mlbam_id"))
            ros = _safe_float(r.get("actual_ros_woba"))
            if mid and ros:
                ros_map[int(mid)] = ros

    # Score each player with v2 formula on 2025 windows
    records = []
    skip_nolog = skip_minpa = 0

    for mid, a in audit.items():
        rows = _load_gamelogs(GAMELOG_2025, mid, "hitter")
        if not rows:
            skip_nolog += 1
            continue

        sc = _score_player_v2(rows, BT_RECENT_START, BT_RECENT_END,
                               BT_PRIOR_START, BT_PRIOR_END)

        if sc["recent_pa"] < MIN_PA_RECENT or sc["prior_pa"] < MIN_PA_PRIOR:
            skip_minpa += 1
            continue

        if sc["trend_score"] is None:
            skip_minpa += 1
            continue

        records.append({
            "mlbam_id":      mid,
            "name":          a["name"],
            "luck_signal":   a["luck_signal"],
            "audit_correct": a["audit_correct"],
            "ros_woba":      ros_map.get(mid),
            "trend_score_v2": sc["trend_score"],
            "recent_pa":     sc["recent_pa"],
            "prior_pa":      sc["prior_pa"],
            "l1": sc["l1"], "l2": sc["l2"], "l3": sc["l3"],
            "l4": sc["l4"], "l5": sc["l5"],
        })

    # Compute p20/p80 from 2025 distribution
    all_scores = sorted(r["trend_score_v2"] for r in records)
    n          = len(all_scores)
    p20_25     = _percentile(all_scores, 20)
    p80_25     = _percentile(all_scores, 80)

    print()
    print("=" * 70)
    print("PART B — 2025 v2 BACKTEST")
    print("=" * 70)
    print(f"  Qualified: {n} players  "
          f"(skipped: {skip_nolog} no log, {skip_minpa} min PA)")
    print(f"  Score range:  min={all_scores[0]:.3f}  "
          f"p20={p20_25:.3f}  median={all_scores[n//2]:.3f}  "
          f"p80={p80_25:.3f}  max={all_scores[-1]:.3f}")
    print(f"  2025 thresholds: Hot >= {p80_25:.3f}   Cold <= {p20_25:.3f}")

    # Classify
    for r in records:
        r["trend_dir_v2"] = _classify_pct(r["trend_score_v2"], p20_25, p80_25)

    hot_n  = sum(1 for r in records if r["trend_dir_v2"] == "Hot")
    cold_n = sum(1 for r in records if r["trend_dir_v2"] == "Cold")
    flat_n = sum(1 for r in records if r["trend_dir_v2"] == "Flat")
    print(f"  Distribution: Hot={hot_n} ({hot_n/n*100:.0f}%)  "
          f"Cold={cold_n} ({cold_n/n*100:.0f}%)  "
          f"Flat={flat_n} ({flat_n/n*100:.0f}%)")

    # ── stratified tables ─────────────────────────────────────────────────────
    print()
    print("=" * 70)
    print("PART C — STRATIFIED COMPARISON  (v2 vs v1)")
    print("=" * 70)
    print(f"  {'Subgroup':<28}  {'n':<4}  {'Acc':<7}  {'ROS wOBA':<9}"
          f"  ||  {'v1 n':<4}  {'v1 Acc':<7}  {'v1 ROS':<7}  {'Δacc':<7}  {'Δros'}")
    print(f"  {'-'*90}")

    by_tier = defaultdict(list)
    for r in records:
        by_tier[r["luck_signal"]].append(r)

    for tier in ["Buy Low", "Sell High"]:
        players = by_tier.get(tier, [])
        if not players:
            print(f"\n  {tier}: no players in qualified set")
            continue

        print(f"\n  ── {tier} (n={len(players)} qualified) ──")

        for trend in ["Hot", "Cold", "Flat"]:
            grp = [p for p in players if p["trend_dir_v2"] == trend]
            st  = _group_stats(grp)
            v1k = (tier, trend)
            print(_fmt_row(f"{tier} + {trend}", st, v1k))

        # Overall baseline
        base_st = _group_stats(players)
        print(_fmt_row(f"{tier} baseline", base_st, (tier, "base")))

    # ── key question: does v2 produce larger separation? ─────────────────────
    print()
    print("=" * 70)
    print("KEY QUESTION: v2 separation vs v1")
    print("=" * 70)

    def _tier_trend(tier, trend):
        grp = [p for p in records
               if p["luck_signal"] == tier and p["trend_dir_v2"] == trend]
        return _group_stats(grp)

    bl_hot  = _tier_trend("Buy Low", "Hot")
    bl_cold = _tier_trend("Buy Low", "Cold")
    bl_flat = _tier_trend("Buy Low", "Flat")
    sh_hot  = _tier_trend("Sell High", "Hot")
    sh_cold = _tier_trend("Sell High", "Cold")

    # BL: Hot vs Cold wOBA separation
    if bl_hot["ros"] and bl_cold["ros"]:
        v2_bl_sep = (bl_hot["ros"] - bl_cold["ros"]) * 1000
        v1_bl_sep = (V1[("Buy Low","Hot")]["ros"] - V1[("Buy Low","Cold")]["ros"]) * 1000
        print(f"\n  Buy Low Hot-vs-Cold wOBA separation:")
        print(f"    v2: {v2_bl_sep:+.1f} wOBA pts  (Hot={bl_hot['ros']:.3f}  Cold={bl_cold['ros']:.3f})")
        print(f"    v1: {v1_bl_sep:+.1f} wOBA pts  (Hot={V1[('Buy Low','Hot')]['ros']:.3f}  Cold={V1[('Buy Low','Cold')]['ros']:.3f})")
        print(f"    Δ: {v2_bl_sep - v1_bl_sep:+.1f} wOBA pts  ({'v2 BETTER' if v2_bl_sep > v1_bl_sep else 'v1 BETTER or EQUAL'})")

    # SH: Hot vs Cold wOBA separation
    if sh_hot["ros"] and sh_cold["ros"]:
        v2_sh_sep = (sh_cold["ros"] - sh_hot["ros"]) * 1000  # lower = better for sell
        v1_sh = V1[("Sell High","Cold")]["ros"]
        v1_hot = V1[("Sell High","Hot")]["ros"]
        if v1_sh and v1_hot:
            v1_sh_sep = (v1_sh - v1_hot) * 1000
            print(f"\n  Sell High Cold-vs-Hot wOBA separation (lower cold = better sell confirm):")
            print(f"    v2: {v2_sh_sep:+.1f} wOBA pts  (Hot={sh_hot['ros']:.3f}  Cold={sh_cold['ros']:.3f})")
            print(f"    v1: {v1_sh_sep:+.1f} wOBA pts  (Hot={v1_hot:.3f}  Cold={v1_sh:.3f})")
            print(f"    Δ: {v2_sh_sep - v1_sh_sep:+.1f} wOBA pts  ({'v2 BETTER' if v2_sh_sep > v1_sh_sep else 'v1 BETTER or EQUAL'})")

    # Accuracy: BL hot vs cold
    if bl_hot["acc"] is not None and bl_cold["acc"] is not None:
        print(f"\n  Buy Low accuracy gap (Hot - Cold):")
        v2_acc_gap = (bl_hot["acc"] - bl_cold["acc"]) * 100
        v1_acc_gap = (V1[("Buy Low","Hot")]["acc"] - V1[("Buy Low","Cold")]["acc"]) * 100
        print(f"    v2: {v2_acc_gap:+.1f}pp  (Hot={bl_hot['acc']*100:.1f}%  Cold={bl_cold['acc']*100:.1f}%)")
        print(f"    v1: {v1_acc_gap:+.1f}pp  (Hot={V1[('Buy Low','Hot')]['acc']*100:.1f}%  Cold={V1[('Buy Low','Cold')]['acc']*100:.1f}%)")

    # ── save CSV ──────────────────────────────────────────────────────────────
    fieldnames = ["mlbam_id", "name", "luck_signal", "audit_correct", "ros_woba",
                  "trend_score_v2", "trend_dir_v2", "recent_pa", "prior_pa",
                  "l1", "l2", "l3", "l4", "l5"]
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in sorted(records, key=lambda x: -x["trend_score_v2"]):
            w.writerow({k: (f"{r[k]:.4f}" if isinstance(r[k], float) else r[k])
                        for k in fieldnames})
    print(f"\nSaved: {OUT_CSV} ({len(records)} rows)")


def main():
    p20_26, p80_26 = part_a()
    part_b_and_c()


if __name__ == "__main__":
    main()
