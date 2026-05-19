"""
backtest_trend_stratified_2025.py
Tier-stratified trend backtest — same rolling windows as backtest_trend_signals_proper.py.

Groups by (luck_signal, trend_dir) so comparisons stay within-tier.
Produces 4 tables: Sell High, Slight Sell, Buy Low, Slight Buy.
"""
import csv
from datetime import date
from pathlib import Path
from collections import defaultdict

RECENT_START = date(2025, 4, 26)
RECENT_END   = date(2025, 5, 17)
PRIOR_START  = date(2025, 4, 5)
PRIOR_END    = date(2025, 4, 25)

TREND_HOT_THRESH  =  0.020
TREND_COLD_THRESH = -0.020
MIN_PA_RECENT     = 20
MIN_PA_PRIOR      = 15

GAMELOG_DIR = Path("data/statcast_gamelogs_2025")
AUDIT_CSV   = "data/backtest_audit_hitters.csv"
BT_A_CSV    = "data/backtest_A_hitters_2025.csv"


def _safe_float(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _weighted_xwoba(rows, start, end):
    total_pa, total_wxw = 0, 0.0
    for r in rows:
        try:
            gd = date.fromisoformat(r["game_date"])
        except (KeyError, ValueError):
            continue
        if not (start <= gd <= end):
            continue
        pa = _safe_float(r.get("pa"), 0)
        xw = _safe_float(r.get("xwoba"))
        if pa and pa > 0 and xw is not None:
            total_pa  += int(pa)
            total_wxw += xw * pa
    if total_pa == 0:
        return None, 0
    return total_wxw / total_pa, total_pa


def load_gamelogs(mlbam_id):
    path = GAMELOG_DIR / f"hitter_{mlbam_id}.csv"
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        content = f.read().lstrip("﻿")
    return list(csv.DictReader(content.splitlines()))


def classify_trend(delta):
    if delta is None:
        return "Flat"
    if delta >= TREND_HOT_THRESH:
        return "Hot"
    if delta <= TREND_COLD_THRESH:
        return "Cold"
    return "Flat"


def load_audit_2025():
    out = {}
    with open(AUDIT_CSV, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("year") != "2025":
                continue
            mid = int(r["mlbam_id"])
            out[mid] = {
                "name":          r["player_name"],
                "luck_signal":   r["signal"],
                "luck_score":    _safe_float(r["luck_score"]),
                "audit_correct": r.get("correct", "").lower() == "true",
            }
    return out


def load_ros_woba():
    out = {}
    with open(BT_A_CSV, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            mid = _safe_float(r.get("mlbam_id"))
            ros = _safe_float(r.get("actual_ros_woba"))
            if mid is not None and ros is not None:
                out[int(mid)] = ros
    return out


def group_stats(players):
    if not players:
        return {"n": 0, "acc": None, "mean_ros_woba": None}
    ros  = [p["ros_woba"] for p in players if p["ros_woba"] is not None]
    corr = [p["audit_correct"] for p in players]
    return {
        "n":             len(players),
        "acc":           sum(corr) / len(corr) if corr else None,
        "mean_ros_woba": sum(ros) / len(ros) if ros else None,
    }


def fmt_pct(v):
    return f"{v*100:.1f}%" if v is not None else "  n/a "


def fmt_woba(v):
    return f".{round(v*1000):03d}" if v is not None else " n/a"


def print_tier_table(tier_label, records):
    """Print Hot/Cold/Flat breakdown + overall baseline for one luck tier."""
    by_trend = defaultdict(list)
    for p in records:
        by_trend[p["trend_dir"]].append(p)

    overall = group_stats(records)

    print(f"\n  {'Subgroup':<28} {'n':>4}  {'Acc':>7}  {'ROS wOBA':>9}")
    print(f"  {'-'*55}")
    for trend in ["Hot", "Cold", "Flat"]:
        ps  = by_trend.get(trend, [])
        st  = group_stats(ps)
        label = f"{tier_label} + {trend}"
        print(f"  {label:<28} {st['n']:>4}  {fmt_pct(st['acc']):>7}  {fmt_woba(st['mean_ros_woba']):>9}")
    print(f"  {'-'*55}")
    print(f"  {'Baseline (overall)':<28} {overall['n']:>4}  {fmt_pct(overall['acc']):>7}  {fmt_woba(overall['mean_ros_woba']):>9}")
    return by_trend, overall


def main():
    audit   = load_audit_2025()
    ros_map = load_ros_woba()

    records = []
    skip_nolog = skip_minpa = 0

    for mid, a in audit.items():
        rows = load_gamelogs(mid)
        if not rows:
            skip_nolog += 1
            continue

        recent_xw, recent_pa = _weighted_xwoba(rows, RECENT_START, RECENT_END)
        prior_xw,  prior_pa  = _weighted_xwoba(rows, PRIOR_START,  PRIOR_END)

        if recent_pa < MIN_PA_RECENT or prior_pa < MIN_PA_PRIOR:
            skip_minpa += 1
            continue

        delta     = (recent_xw - prior_xw) if (recent_xw is not None and prior_xw is not None) else None
        trend_dir = classify_trend(delta)

        records.append({
            "name":          a["name"],
            "mlbam_id":      mid,
            "luck_signal":   a["luck_signal"],
            "luck_score":    a["luck_score"],
            "prior_xwoba":   prior_xw,
            "prior_pa":      prior_pa,
            "recent_xwoba":  recent_xw,
            "recent_pa":     recent_pa,
            "trend_delta":   delta,
            "trend_dir":     trend_dir,
            "ros_woba":      ros_map.get(mid),
            "audit_correct": a["audit_correct"],
        })

    print("=" * 65)
    print("TREND BACKTEST — TIER-STRATIFIED (2025)")
    print("=" * 65)
    print(f"Recent window:  {RECENT_START} → {RECENT_END}  (Hot/Cold ≥ ±{TREND_HOT_THRESH})")
    print(f"Prior window:   {PRIOR_START} → {PRIOR_END}")
    print(f"Min PA:         recent≥{MIN_PA_RECENT}, prior≥{MIN_PA_PRIOR}")
    print(f"Qualified:      {len(records)} players  (skipped: {skip_nolog} no log, {skip_minpa} min PA)")

    # ── split by luck tier ───────────────────────────────────────────────────
    by_tier = defaultdict(list)
    for p in records:
        by_tier[p["luck_signal"]].append(p)

    TIER_ORDER = ["Sell High", "Slight Sell", "Buy Low", "Slight Buy"]

    tier_bytrend = {}
    tier_overall = {}

    for i, tier in enumerate(TIER_ORDER):
        players = by_tier.get(tier, [])
        print()
        print("=" * 65)
        print(f"TABLE {i+1} — {tier.upper()}")
        print("=" * 65)
        print(f"  Universe: {len(players)} {tier} players who pass PA filter")
        bt, ov = print_tier_table(tier, players)
        tier_bytrend[tier] = bt
        tier_overall[tier] = ov

    # ── direct answers ───────────────────────────────────────────────────────
    print()
    print("=" * 65)
    print("DIRECT ANSWERS")
    print("=" * 65)

    # Q1: Within Sell High — does Cold trend improve?
    sh_cold = group_stats(tier_bytrend["Sell High"].get("Cold", []))
    sh_hot  = group_stats(tier_bytrend["Sell High"].get("Hot",  []))
    sh_flat = group_stats(tier_bytrend["Sell High"].get("Flat", []))
    sh_base = tier_overall["Sell High"]

    print()
    print("Q1. Within Sell High — does Cold trend improve accuracy / lower wOBA?")
    if sh_cold["n"] > 0 and sh_base["acc"] is not None:
        d_acc  = (sh_cold["acc"]  or 0) - sh_base["acc"]
        d_woba = None
        if sh_cold["mean_ros_woba"] is not None and sh_base["mean_ros_woba"] is not None:
            d_woba = sh_cold["mean_ros_woba"] - sh_base["mean_ros_woba"]
        print(f"  SH baseline:      acc={fmt_pct(sh_base['acc'])}  ROS wOBA={fmt_woba(sh_base['mean_ros_woba'])}  n={sh_base['n']}")
        print(f"  SH + Cold:        acc={fmt_pct(sh_cold['acc'])}  ROS wOBA={fmt_woba(sh_cold['mean_ros_woba'])}  n={sh_cold['n']}")
        print(f"  SH + Hot:         acc={fmt_pct(sh_hot['acc'])}  ROS wOBA={fmt_woba(sh_hot['mean_ros_woba'])}  n={sh_hot['n']}")
        print(f"  SH + Flat:        acc={fmt_pct(sh_flat['acc'])}  ROS wOBA={fmt_woba(sh_flat['mean_ros_woba'])}  n={sh_flat['n']}")
        print(f"  Acc delta (Cold vs baseline): {d_acc*100:+.1f}pp")
        if d_woba is not None:
            print(f"  wOBA delta (Cold vs baseline): {d_woba*1000:+.1f} wOBA pts (lower = better sell confirm)")
    else:
        print("  Insufficient data for Sell High + Cold.")

    # Q2: Within Buy Low — does Hot trend improve?
    bl_hot  = group_stats(tier_bytrend["Buy Low"].get("Hot",  []))
    bl_cold = group_stats(tier_bytrend["Buy Low"].get("Cold", []))
    bl_flat = group_stats(tier_bytrend["Buy Low"].get("Flat", []))
    bl_base = tier_overall["Buy Low"]

    print()
    print("Q2. Within Buy Low — does Hot trend improve accuracy?")
    if bl_hot["n"] > 0 and bl_base["acc"] is not None:
        d_acc  = (bl_hot["acc"] or 0) - bl_base["acc"]
        d_woba = None
        if bl_hot["mean_ros_woba"] is not None and bl_base["mean_ros_woba"] is not None:
            d_woba = bl_hot["mean_ros_woba"] - bl_base["mean_ros_woba"]
        print(f"  BL baseline:      acc={fmt_pct(bl_base['acc'])}  ROS wOBA={fmt_woba(bl_base['mean_ros_woba'])}  n={bl_base['n']}")
        print(f"  BL + Hot:         acc={fmt_pct(bl_hot['acc'])}  ROS wOBA={fmt_woba(bl_hot['mean_ros_woba'])}  n={bl_hot['n']}")
        print(f"  BL + Cold:        acc={fmt_pct(bl_cold['acc'])}  ROS wOBA={fmt_woba(bl_cold['mean_ros_woba'])}  n={bl_cold['n']}")
        print(f"  BL + Flat:        acc={fmt_pct(bl_flat['acc'])}  ROS wOBA={fmt_woba(bl_flat['mean_ros_woba'])}  n={bl_flat['n']}")
        print(f"  Acc delta (Hot vs baseline): {d_acc*100:+.1f}pp")
        if d_woba is not None:
            print(f"  wOBA delta (Hot vs baseline): {d_woba*1000:+.1f} wOBA pts (higher = better buy confirm)")
    else:
        print("  Insufficient data for Buy Low + Hot.")

    # Q3: Sample sizes
    print()
    print("Q3. Within-tier sample sizes — are they large enough?")
    print("    Rule of thumb: n<5 = anecdote, n<10 = cautious, n>=10 = preliminary signal")
    for tier in TIER_ORDER:
        bt  = tier_bytrend[tier]
        ov  = tier_overall[tier]
        h_n = len(bt.get("Hot",  []))
        c_n = len(bt.get("Cold", []))
        f_n = len(bt.get("Flat", []))
        verdict = "PRELIMINARY" if min(h_n, c_n) >= 5 else ("CAUTIOUS" if min(h_n, c_n) >= 3 else "ANECDOTE")
        print(f"  {tier:<12}  total={ov['n']}  Hot={h_n}  Cold={c_n}  Flat={f_n}  → {verdict}")

    # ── save CSV ─────────────────────────────────────────────────────────────
    out_path = Path("data/trend_signal_backtest_stratified_2025.csv")
    fieldnames = ["name", "mlbam_id", "luck_signal", "luck_score",
                  "prior_xwoba", "prior_pa", "recent_xwoba", "recent_pa",
                  "trend_delta", "trend_dir", "ros_woba", "audit_correct"]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for p in sorted(records, key=lambda x: (x["luck_signal"], x["trend_dir"])):
            w.writerow({k: (f"{p[k]:.4f}" if isinstance(p[k], float) else p[k])
                        for k in fieldnames})
    print(f"\nSaved: {out_path} ({len(records)} rows)")


if __name__ == "__main__":
    main()
