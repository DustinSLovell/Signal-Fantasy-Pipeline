"""
backtest_trend_signals_proper.py
True rolling-window trend backtest using 2025 Statcast game logs.

Architecture:
  Cutoff:         May 17, 2025
  Recent window:  Apr 26 - May 17 (21 days) — real xwOBA from game logs
  Prior window:   Apr 5  - Apr 25 (21 days) — real xwOBA from game logs
  Validation:     May 18 - Aug 31  — actual_ros_woba from backtest_A_hitters_2025.csv

Signal layers:
  Luck signal:   backtest_audit_hitters.csv (year=2025, signal + correct columns)
  Trend signal:  computed from statcast_gamelogs_2025/hitter_{id}.csv
  Combined:      luck verdict × trend direction

No forward-looking leakage — all windows use dates <= May 17, 2025.
"""
import csv
import os
from datetime import date
from pathlib import Path
from collections import defaultdict

# ── date windows ────────────────────────────────────────────────────────────
RECENT_START = date(2025, 4, 26)
RECENT_END   = date(2025, 5, 17)
PRIOR_START  = date(2025, 4, 5)
PRIOR_END    = date(2025, 4, 25)

# ── thresholds ───────────────────────────────────────────────────────────────
TREND_HOT_THRESH   =  0.020   # xwOBA delta to call Hot
TREND_COLD_THRESH  = -0.020   # xwOBA delta to call Cold
MIN_PA_RECENT      = 20
MIN_PA_PRIOR       = 15

GAMELOG_DIR = Path("data/statcast_gamelogs_2025")
AUDIT_CSV   = "data/backtest_audit_hitters.csv"
BT_A_CSV    = "data/backtest_A_hitters_2025.csv"


# ── helpers ──────────────────────────────────────────────────────────────────

def _safe_float(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _weighted_xwoba(rows, start: date, end: date) -> tuple[float | None, int]:
    """Weighted average xwOBA for rows within [start, end]. Returns (xwoba, total_pa)."""
    total_pa   = 0
    total_wxw  = 0.0
    for r in rows:
        try:
            gd = date.fromisoformat(r["game_date"])
        except (KeyError, ValueError):
            continue
        if not (start <= gd <= end):
            continue
        pa  = _safe_float(r.get("pa"), 0)
        xw  = _safe_float(r.get("xwoba"))
        if pa and pa > 0 and xw is not None:
            total_pa   += int(pa)
            total_wxw  += xw * pa
    if total_pa == 0:
        return None, 0
    return total_wxw / total_pa, total_pa


def load_gamelogs(mlbam_id: int) -> list[dict]:
    path = GAMELOG_DIR / f"hitter_{mlbam_id}.csv"
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        content = f.read().lstrip("﻿")
    rows = list(csv.DictReader(content.splitlines()))
    return rows


def classify_trend(delta: float | None) -> str:
    if delta is None:
        return "Neutral"
    if delta >= TREND_HOT_THRESH:
        return "Hot"
    if delta <= TREND_COLD_THRESH:
        return "Cold"
    return "Neutral"


def combined_signal(luck: str, trend: str) -> str:
    is_buy  = "Buy" in luck
    is_sell = "Sell" in luck
    if   is_buy  and trend == "Hot":  return "Strong Buy"
    elif is_buy  and trend == "Cold": return "Conflicted Buy"
    elif is_sell and trend == "Cold": return "Strong Sell"
    elif is_sell and trend == "Hot":  return "Conflicted Sell"
    elif is_buy:                      return "Buy (Neutral trend)"
    elif is_sell:                     return "Sell (Neutral trend)"
    elif trend == "Hot":              return "Emerging Buy"
    elif trend == "Cold":             return "Fading Sell"
    else:                             return "Neutral"


# ── load reference data ──────────────────────────────────────────────────────

def load_audit_2025() -> dict[int, dict]:
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
                "xwoba_april":   _safe_float(r["xwoba_actual"]),  # April xwOBA (luck baseline)
                "audit_correct": r.get("correct", "").lower() == "true",
                "woba_change":   _safe_float(r.get("actual_woba_change")),
            }
    return out


def load_ros_woba() -> dict[int, float]:
    out = {}
    with open(BT_A_CSV, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            mid = _safe_float(r.get("mlbam_id"))
            ros = _safe_float(r.get("actual_ros_woba"))
            if mid is not None and ros is not None:
                out[int(mid)] = ros
    return out


# ── analysis ─────────────────────────────────────────────────────────────────

def group_stats(players: list[dict]) -> dict:
    if not players:
        return {"n": 0, "mean_ros_woba": None, "acc": None, "mean_delta": None}
    n          = len(players)
    ros_wobas  = [p["ros_woba"] for p in players if p["ros_woba"] is not None]
    corrects   = [p["audit_correct"] for p in players]
    deltas     = [p["trend_delta"] for p in players if p["trend_delta"] is not None]
    return {
        "n":             n,
        "mean_ros_woba": sum(ros_wobas) / len(ros_wobas) if ros_wobas else None,
        "acc":           sum(corrects) / n if n else None,
        "mean_delta":    sum(deltas) / len(deltas) if deltas else None,
    }


def fmt_pct(v):
    return f"{v*100:.1f}%" if v is not None else "n/a"


def fmt_woba(v):
    return f".{round(v*1000):03d}" if v is not None else "n/a"


def main():
    print("=" * 65)
    print("TREND SIGNAL BACKTEST — PROPER ROLLING WINDOW (2025)")
    print("=" * 65)
    print(f"Recent:     {RECENT_START} → {RECENT_END}  (real xwOBA from game logs)")
    print(f"Prior:      {PRIOR_START} → {PRIOR_END}  (real xwOBA from game logs)")
    print(f"Validation: May 18 - Aug 31, 2025  (actual_ros_woba)")
    print()

    audit   = load_audit_2025()
    ros_map = load_ros_woba()
    gamelog_dir_files = list(GAMELOG_DIR.glob("hitter_*.csv"))
    print(f"Audit 2025 players:   {len(audit)}")
    print(f"ROS wOBA available:   {len(ros_map)}")
    print(f"Game log files:       {len(gamelog_dir_files)}")
    print()

    records       = []
    skipped_nolog = 0
    skipped_minpa = 0
    skipped_noros = 0

    for mid, a in audit.items():
        # ── game log rolling windows ────────────────────────────────────────
        rows = load_gamelogs(mid)
        if not rows:
            skipped_nolog += 1
            continue

        recent_xw, recent_pa = _weighted_xwoba(rows, RECENT_START, RECENT_END)
        prior_xw,  prior_pa  = _weighted_xwoba(rows, PRIOR_START,  PRIOR_END)

        if recent_pa < MIN_PA_RECENT or prior_pa < MIN_PA_PRIOR:
            skipped_minpa += 1
            continue

        trend_delta = (recent_xw - prior_xw) if (recent_xw is not None and prior_xw is not None) else None
        trend_dir   = classify_trend(trend_delta)
        combo       = combined_signal(a["luck_signal"], trend_dir)

        # ── validation target ───────────────────────────────────────────────
        ros_woba = ros_map.get(mid)
        if ros_woba is None:
            skipped_noros += 1
            # Still include; acc uses audit_correct which doesn't need ros_woba
            pass

        records.append({
            "name":          a["name"],
            "mlbam_id":      mid,
            "luck_signal":   a["luck_signal"],
            "luck_score":    a["luck_score"],
            "prior_xwoba":   prior_xw,
            "prior_pa":      prior_pa,
            "recent_xwoba":  recent_xw,
            "recent_pa":     recent_pa,
            "trend_delta":   trend_delta,
            "trend_dir":     trend_dir,
            "combined":      combo,
            "xwoba_april":   a["xwoba_april"],
            "ros_woba":      ros_woba,
            "audit_correct": a["audit_correct"],
            "woba_change":   a["woba_change"],
        })

    print(f"Qualified players:  {len(records)}")
    print(f"  Skipped (no log): {skipped_nolog}")
    print(f"  Skipped (min PA): {skipped_minpa}")
    print(f"  No ROS wOBA:      {skipped_noros}")
    print()

    # ── group by combined signal ─────────────────────────────────────────────
    groups = defaultdict(list)
    for p in records:
        groups[p["combined"]].append(p)
    # Also build luck-only groups for baseline comparison
    luck_groups = defaultdict(list)
    for p in records:
        luck_groups[p["luck_signal"]].append(p)

    # ── print individual records ─────────────────────────────────────────────
    print("-" * 65)
    print(f"{'PLAYER':<25} {'LUCK':<12} {'TREND':<7} {'DELTA':>7} {'COMBINED':<22} {'CORRECT'}")
    print("-" * 65)
    for p in sorted(records, key=lambda x: (x["combined"], -abs(x["trend_delta"] or 0))):
        delta_str = f"{p['trend_delta']:+.3f}" if p["trend_delta"] is not None else " n/a"
        correct_str = "✓" if p["audit_correct"] else "✗"
        print(f"{p['name']:<25} {p['luck_signal']:<12} {p['trend_dir']:<7} "
              f"{delta_str:>7} {p['combined']:<22} {correct_str}")

    # ── combined signal summary ──────────────────────────────────────────────
    print()
    print("=" * 65)
    print("COMBINED SIGNAL ACCURACY")
    print("=" * 65)

    DISPLAY_ORDER = [
        "Strong Buy", "Buy (Neutral trend)", "Conflicted Buy",
        "Strong Sell", "Sell (Neutral trend)", "Conflicted Sell",
        "Emerging Buy", "Fading Sell", "Neutral",
    ]
    for combo in DISPLAY_ORDER:
        if combo not in groups:
            continue
        ps  = groups[combo]
        st  = group_stats(ps)
        ros_str = fmt_woba(st["mean_ros_woba"])
        acc_str = fmt_pct(st["acc"])
        dlt_str = f"{st['mean_delta']:+.3f}" if st["mean_delta"] is not None else " n/a"
        print(f"  {combo:<22}  n={st['n']:<3}  ROS wOBA={ros_str}  acc={acc_str}  "
              f"avg Δ={dlt_str}")

    # ── luck-only baseline ───────────────────────────────────────────────────
    print()
    print("=" * 65)
    print("LUCK-ONLY BASELINE (same players, trend ignored)")
    print("=" * 65)
    for sig in ["Buy Low", "Slight Buy", "Slight Sell", "Sell High"]:
        if sig not in luck_groups:
            continue
        ps  = luck_groups[sig]
        st  = group_stats(ps)
        ros_str = fmt_woba(st["mean_ros_woba"])
        acc_str = fmt_pct(st["acc"])
        print(f"  {sig:<12}  n={st['n']:<3}  ROS wOBA={ros_str}  acc={acc_str}")

    # ── key findings ─────────────────────────────────────────────────────────
    print()
    print("=" * 65)
    print("KEY COMPARISONS")
    print("=" * 65)

    def _acc(label):
        ps = groups.get(label, [])
        st = group_stats(ps)
        return st["acc"], st["n"], st["mean_ros_woba"]

    def _lacc(label):
        ps = luck_groups.get(label, [])
        st = group_stats(ps)
        return st["acc"], st["n"], st["mean_ros_woba"]

    sb_acc, sb_n, sb_ros  = _acc("Strong Buy")
    cb_acc, cb_n, cb_ros  = _acc("Conflicted Buy")
    bl_acc, bl_n, bl_ros  = _lacc("Buy Low")

    ss_acc, ss_n, ss_ros  = _acc("Strong Sell")
    cs_acc, cs_n, cs_ros  = _acc("Conflicted Sell")
    sh_acc, sh_n, sh_ros  = _lacc("Sell High")

    if sb_acc is not None and bl_acc is not None:
        print(f"  Strong Buy vs Buy Low alone:")
        print(f"    Strong Buy:      {fmt_pct(sb_acc)} (n={sb_n}, ROS wOBA={fmt_woba(sb_ros)})")
        print(f"    Buy Low alone:   {fmt_pct(bl_acc)} (n={bl_n}, ROS wOBA={fmt_woba(bl_ros)})")
        if sb_acc is not None and bl_acc is not None:
            delta = sb_acc - bl_acc
            print(f"    Delta:           {delta*100:+.1f}pp")

    if cb_acc is not None and bl_acc is not None:
        print()
        print(f"  Conflicted Buy vs Buy Low alone:")
        print(f"    Conflicted Buy:  {fmt_pct(cb_acc)} (n={cb_n}, ROS wOBA={fmt_woba(cb_ros)})")
        print(f"    Buy Low alone:   {fmt_pct(bl_acc)} (n={bl_n}, ROS wOBA={fmt_woba(bl_ros)})")
        if cb_acc is not None and bl_acc is not None:
            delta = cb_acc - bl_acc
            print(f"    Delta:           {delta*100:+.1f}pp")

    if ss_acc is not None and sh_acc is not None:
        print()
        print(f"  Strong Sell vs Sell High alone:")
        print(f"    Strong Sell:     {fmt_pct(ss_acc)} (n={ss_n}, ROS wOBA={fmt_woba(ss_ros)})")
        print(f"    Sell High alone: {fmt_pct(sh_acc)} (n={sh_n}, ROS wOBA={fmt_woba(sh_ros)})")
        if ss_acc is not None and sh_acc is not None:
            delta = ss_acc - sh_acc
            print(f"    Delta:           {delta*100:+.1f}pp")

    # ── wOBA separation by trend ─────────────────────────────────────────────
    print()
    print("=" * 65)
    print("MEAN ROS WOBA SEPARATION")
    print("=" * 65)
    print("(Best measure of whether trend direction predicts future performance)")
    hot_buys  = [p["ros_woba"] for p in records if p["combined"] == "Strong Buy" and p["ros_woba"]]
    cold_buys = [p["ros_woba"] for p in records if p["combined"] == "Conflicted Buy" and p["ros_woba"]]
    hot_sells = [p["ros_woba"] for p in records if p["combined"] == "Strong Sell" and p["ros_woba"]]
    cold_sells= [p["ros_woba"] for p in records if p["combined"] == "Conflicted Sell" and p["ros_woba"]]

    for label, vals in [("Strong Buy", hot_buys), ("Conflicted Buy", cold_buys),
                        ("Strong Sell", hot_sells), ("Conflicted Sell", cold_sells)]:
        mean = sum(vals)/len(vals) if vals else None
        print(f"  {label:<22} n={len(vals):<3}  mean ROS wOBA = {fmt_woba(mean)}")

    if hot_buys and cold_buys:
        sep = sum(hot_buys)/len(hot_buys) - sum(cold_buys)/len(cold_buys)
        print(f"\n  Strong Buy vs Conflicted Buy separation: {sep*1000:+.1f} wOBA points")
    if hot_sells and cold_sells:
        sep = sum(cold_sells)/len(cold_sells) - sum(hot_sells)/len(hot_sells)
        print(f"  Strong Sell vs Conflicted Sell separation: {sep*1000:+.1f} wOBA points")

    # ── save results ─────────────────────────────────────────────────────────
    out_path = Path("data/trend_signal_backtest_proper_2025.csv")
    fieldnames = ["name", "mlbam_id", "luck_signal", "luck_score",
                  "prior_xwoba", "prior_pa", "recent_xwoba", "recent_pa",
                  "trend_delta", "trend_dir", "combined",
                  "xwoba_april", "ros_woba", "audit_correct", "woba_change"]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for p in records:
            w.writerow({k: (f"{p[k]:.4f}" if isinstance(p[k], float) else p[k])
                        for k in fieldnames})
    print(f"\nResults saved: {out_path} ({len(records)} rows)")


if __name__ == "__main__":
    main()
