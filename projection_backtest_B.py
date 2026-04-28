#!/usr/bin/env python3
"""
projection_backtest_B.py
Signal-Informed Projection Accuracy (2025 OOS validation).

Extends Backtest A by applying 2025 April luck signals as post-projection
multipliers, then measuring whether signals improve accuracy.

Four methods compared:
  Naive         — April per-game rate projected forward
  RTM           — 50% regression to league average
  Model         — stat_projections.py output (no signal adjustment)
  Signal-adj    — Model output modified by luck signal tier

Signal adjustment multipliers (v2 — cleaned per Backtest B findings):
  Buy Low:     wOBA×1.08  HR×1.05   (AVG removed — overshoots career-BA anchor)
  Slight Buy:  wOBA×1.04  HR×1.02   (AVG removed)
  Sell High:   wOBA×0.92            (AVG removed; HR sell removed — overcorrects)
  Slight Sell: wOBA×0.96            (AVG removed; HR sell removed)
  Neutral:     no adjustment

Pitcher adjustments (v2):
  Buy Low:   WHIP×0.95  K×1.05      (ERA removed — n=7, 28.6% win rate)
  Sell High: ERA×1.10  WHIP×1.05  K×0.95

Inputs (pre-built by projection_backtest_A.py):
  data/backtest_A_hitters_2025.csv
  data/backtest_A_pitchers_2025.csv

Signal sources (backtest v7 logic, 2025 signals):
  data/backtest_audit_hitters_v2.csv
  data/backtest_audit_pitchers_v2.csv

Do not modify any production files.
"""

import csv
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
HITTER_A_CSV     = "data/backtest_A_hitters_2025.csv"
PITCHER_A_CSV    = "data/backtest_A_pitchers_2025.csv"
HITTER_SIG_CSV   = "data/backtest_audit_hitters_v2.csv"
PITCHER_SIG_CSV  = "data/backtest_audit_pitchers_v2.csv"
OUT_HITTER_B     = "data/backtest_B_hitters_2025.csv"
OUT_PITCHER_B    = "data/backtest_B_pitchers_2025.csv"

# ---------------------------------------------------------------------------
# Signal tier adjustments — hitters
# ---------------------------------------------------------------------------
HITTER_ADJ = {
    "buy low":    {"woba": 1.08, "avg": 1.00, "hr": 1.05},
    "slight buy": {"woba": 1.04, "avg": 1.00, "hr": 1.02},
    "sell high":  {"woba": 0.92, "avg": 1.00, "hr": 1.00},
    "slight sell":{"woba": 0.96, "avg": 1.00, "hr": 1.00},
    "neutral":    {"woba": 1.00, "avg": 1.00, "hr": 1.00},
}

PITCHER_ADJ = {
    "buy low":    {"era": 1.00, "whip": 0.95, "k": 1.05},
    "slight buy": {"era": 1.00, "whip": 1.00, "k": 1.00},
    "sell high":  {"era": 1.10, "whip": 1.05, "k": 0.95},
    "slight sell":{"era": 1.00, "whip": 1.00, "k": 1.00},
    "neutral":    {"era": 1.00, "whip": 1.00, "k": 1.00},
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _f(val):
    try:
        v = float(val)
        return v if math.isfinite(v) else float("nan")
    except (TypeError, ValueError):
        return float("nan")


def _mae(vals):
    v = [x for x in vals if math.isfinite(x)]
    return sum(abs(x) for x in v) / len(v) if v else float("nan"), len(v)


def _bias(vals):
    v = [x for x in vals if math.isfinite(x)]
    return sum(v) / len(v) if v else float("nan")


def _win_rate(model_errs, rtm_errs):
    wins = sum(1 for m, r in zip(model_errs, rtm_errs)
               if math.isfinite(m) and math.isfinite(r) and abs(m) < abs(r))
    total = sum(1 for m, r in zip(model_errs, rtm_errs)
                if math.isfinite(m) and math.isfinite(r))
    return wins / total if total else float("nan"), total


def _normalize_signal(s: str) -> str:
    return s.strip().lower()


# ---------------------------------------------------------------------------
# Load signal data
# ---------------------------------------------------------------------------
def load_signals(path: str, year: str = "2025") -> dict:
    """Return {mlbam_id: signal_str} for the given year."""
    out = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("year", "").strip() == year:
                bid = row.get("mlbam_id", "").strip()
                sig = row.get("signal", "neutral").strip()
                if bid:
                    out[bid] = sig
    return out


# ---------------------------------------------------------------------------
# Load Backtest A results
# ---------------------------------------------------------------------------
def load_backtest_a(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# Apply signal adjustments — hitters
# ---------------------------------------------------------------------------
def apply_hitter_signals(rows: list[dict], signals: dict) -> list[dict]:
    out = []
    for row in rows:
        row = dict(row)
        bid = str(row.get("mlbam_id", "")).strip()
        raw_sig = signals.get(bid, "neutral")
        norm_sig = _normalize_signal(raw_sig)
        adj = HITTER_ADJ.get(norm_sig, HITTER_ADJ["neutral"])

        model_hr   = _f(row.get("model_hr"))
        model_avg  = _f(row.get("model_avg"))
        model_woba = _f(row.get("model_woba"))

        row["signal"] = raw_sig
        row["signal_norm"] = norm_sig
        row["signal_hr"]   = model_hr  * adj["hr"]   if math.isfinite(model_hr)   else float("nan")
        row["signal_avg"]  = model_avg * adj["avg"]  if math.isfinite(model_avg)  else float("nan")
        row["signal_woba"] = model_woba * adj["woba"] if math.isfinite(model_woba) else float("nan")
        out.append(row)
    return out


# ---------------------------------------------------------------------------
# Apply signal adjustments — pitchers
# ---------------------------------------------------------------------------
def apply_pitcher_signals(rows: list[dict], signals: dict) -> list[dict]:
    out = []
    for row in rows:
        row = dict(row)
        bid = str(row.get("mlbam_id", "")).strip()
        raw_sig = signals.get(bid, "neutral")
        norm_sig = _normalize_signal(raw_sig)
        adj = PITCHER_ADJ.get(norm_sig, PITCHER_ADJ["neutral"])

        model_era  = _f(row.get("model_era"))
        model_whip = _f(row.get("model_whip"))
        model_k    = _f(row.get("model_k"))

        row["signal"] = raw_sig
        row["signal_norm"] = norm_sig
        row["signal_era"]  = model_era  * adj["era"]  if math.isfinite(model_era)  else float("nan")
        row["signal_whip"] = model_whip * adj["whip"] if math.isfinite(model_whip) else float("nan")
        row["signal_k"]    = model_k    * adj["k"]    if math.isfinite(model_k)    else float("nan")
        out.append(row)
    return out


# ---------------------------------------------------------------------------
# Print helpers
# ---------------------------------------------------------------------------
SEP = "=" * 72

def _print_mae_row(label, n, naive_mae, rtm_mae, model_mae, signal_mae):
    if not math.isfinite(signal_mae):
        print(f"  {label:<8} n={n:<4} Naive={naive_mae:6.4f}  RTM={rtm_mae:6.4f}  "
              f"Model={model_mae:6.4f}  Signal=   N/A")
        return
    sig_vs_model = "✓" if signal_mae < model_mae else "✗"
    sig_vs_rtm   = "✓" if signal_mae < rtm_mae   else " "
    print(f"  {label:<8} n={n:<4} Naive={naive_mae:6.4f}  RTM={rtm_mae:6.4f}  "
          f"Model={model_mae:6.4f}  Signal={signal_mae:6.4f}  "
          f"vs.Model={sig_vs_model} vs.RTM={sig_vs_rtm}")


def _tier_mae_row(tier, n, model_mae, signal_mae, bias_model, bias_signal):
    if n == 0:
        return
    delta = signal_mae - model_mae
    direction = "better" if delta < 0 else "worse "
    print(f"  {tier:<12} n={n:<4} Model={model_mae:6.4f}  Signal={signal_mae:6.4f}  "
          f"Δ={delta:+.4f} ({direction})")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print(SEP)
    print("Backtest B — Signal-Informed Projection Accuracy (2025 OOS)")
    print(SEP)

    # --- Load inputs -------------------------------------------------------
    print("\n[1] Loading Backtest A results...")
    hitters = load_backtest_a(HITTER_A_CSV)
    pitchers = load_backtest_a(PITCHER_A_CSV)
    print(f"  Hitters: {len(hitters)} rows  |  Pitchers: {len(pitchers)} rows")

    print("\n[2] Loading 2025 luck signals...")
    h_sigs = load_signals(HITTER_SIG_CSV)
    p_sigs = load_signals(PITCHER_SIG_CSV)
    print(f"  Hitter signals: {len(h_sigs)} players in 2025")
    print(f"  Pitcher signals: {len(p_sigs)} players in 2025")

    # --- Apply signals -----------------------------------------------------
    print("\n[3] Applying signal adjustments...")
    hitters = apply_hitter_signals(hitters, h_sigs)
    pitchers = apply_pitcher_signals(pitchers, p_sigs)

    h_matched   = sum(1 for r in hitters if r["signal_norm"] != "neutral")
    h_buy_low   = sum(1 for r in hitters if r["signal_norm"] == "buy low")
    h_sl_buy    = sum(1 for r in hitters if r["signal_norm"] == "slight buy")
    h_sell_high = sum(1 for r in hitters if r["signal_norm"] == "sell high")
    h_sl_sell   = sum(1 for r in hitters if r["signal_norm"] == "slight sell")
    h_neutral   = sum(1 for r in hitters if r["signal_norm"] == "neutral")

    p_buy_low   = sum(1 for r in pitchers if r["signal_norm"] == "buy low")
    p_sell_high = sum(1 for r in pitchers if r["signal_norm"] == "sell high")
    p_neutral   = sum(1 for r in pitchers if r["signal_norm"] == "neutral")

    print(f"  Hitters — Buy Low: {h_buy_low}  Slight Buy: {h_sl_buy}  "
          f"Neutral: {h_neutral}  Slight Sell: {h_sl_sell}  Sell High: {h_sell_high}")
    print(f"  Pitchers — Buy Low: {p_buy_low}  Neutral: {p_neutral}  Sell High: {p_sell_high}")

    # -----------------------------------------------------------------------
    # TABLE 1 — Overall MAE: all four methods
    # -----------------------------------------------------------------------
    print(f"\n{SEP}")
    print("TABLE 1 — Overall MAE: Naive vs RTM vs Model vs Signal-Adj")
    print(SEP)
    print()
    print("  Hitters:")

    # wOBA subset (≥150 ROS PA)
    woba_rows = [r for r in hitters if _f(r.get("actual_ros_woba")) == _f(r.get("actual_ros_woba"))]

    for label, actual_col, model_col, rtm_col, naive_col, signal_col, pool in [
        ("HR",    "actual_hr",       "model_hr",   "rtm_hr",   "naive_hr",   "signal_hr",   hitters),
        ("AVG",   "actual_avg",      "model_avg",  "rtm_avg",  "naive_avg",  "signal_avg",  hitters),
        ("R",     "actual_r",        "model_r",    "rtm_r",    "naive_r",    None,          hitters),
        ("RBI",   "actual_rbi",      "model_rbi",  "rtm_rbi",  "naive_rbi",  None,          hitters),
        ("wOBA",  "actual_ros_woba", "model_woba", "rtm_woba", "naive_woba", "signal_woba", woba_rows),
    ]:
        naive_errs  = [_f(r[naive_col])  - _f(r[actual_col]) for r in pool]
        rtm_errs    = [_f(r[rtm_col])   - _f(r[actual_col]) for r in pool]
        model_errs  = [_f(r[model_col]) - _f(r[actual_col]) for r in pool]
        n_mae, n = _mae(naive_errs)
        r_mae, _ = _mae(rtm_errs)
        m_mae, _ = _mae(model_errs)

        if signal_col:
            sig_errs = [_f(r[signal_col]) - _f(r[actual_col]) for r in pool]
            s_mae, _ = _mae(sig_errs)
        else:
            s_mae = float("nan")

        _print_mae_row(label, n, n_mae, r_mae, m_mae, s_mae)

    print()
    print("  Pitchers:")
    for label, actual_col, model_col, rtm_col, naive_col, signal_col in [
        ("ERA",  "actual_era",  "model_era",  "rtm_era",  "naive_era",  "signal_era"),
        ("WHIP", "actual_whip", "model_whip", "rtm_whip", "naive_whip", "signal_whip"),
        ("K",    "actual_k",    "model_k",    "rtm_k",    "naive_k",    "signal_k"),
    ]:
        naive_errs = [_f(r[naive_col])  - _f(r[actual_col]) for r in pitchers]
        rtm_errs   = [_f(r[rtm_col])   - _f(r[actual_col]) for r in pitchers]
        model_errs = [_f(r[model_col]) - _f(r[actual_col]) for r in pitchers]
        sig_errs   = [_f(r[signal_col])- _f(r[actual_col]) for r in pitchers]
        n_mae, n = _mae(naive_errs)
        r_mae, _ = _mae(rtm_errs)
        m_mae, _ = _mae(model_errs)
        s_mae, _ = _mae(sig_errs)
        _print_mae_row(label, n, n_mae, r_mae, m_mae, s_mae)

    # -----------------------------------------------------------------------
    # TABLE 2 — MAE by signal tier
    # -----------------------------------------------------------------------
    print(f"\n{SEP}")
    print("TABLE 2 — MAE by Signal Tier (Model vs Signal-Adj)")
    print(SEP)
    print()
    print("  Hitters — wOBA:")
    tiers_h = ["buy low", "slight buy", "neutral", "slight sell", "sell high"]
    tier_labels = {
        "buy low": "Buy Low",
        "slight buy": "Sl.Buy",
        "neutral": "Neutral",
        "slight sell": "Sl.Sell",
        "sell high": "Sell High",
    }

    for pool, actual_col, model_col, signal_col, metric_label in [
        (woba_rows, "actual_ros_woba", "model_woba", "signal_woba", "wOBA"),
        (hitters,   "actual_hr",       "model_hr",   "signal_hr",   "HR"),
        (hitters,   "actual_avg",      "model_avg",  "signal_avg",  "AVG"),
    ]:
        print(f"\n  {metric_label}:")
        for tier in tiers_h:
            subset = [r for r in pool if r["signal_norm"] == tier]
            if not subset:
                continue
            m_errs = [_f(r[model_col])  - _f(r[actual_col]) for r in subset]
            s_errs = [_f(r[signal_col]) - _f(r[actual_col]) for r in subset]
            m_mae, n = _mae(m_errs)
            s_mae, _ = _mae(s_errs)
            m_bias = _bias(m_errs)
            s_bias = _bias(s_errs)
            _tier_mae_row(tier_labels[tier], n, m_mae, s_mae, m_bias, s_bias)

    print()
    print("  Pitchers — ERA:")
    for tier in ["buy low", "slight buy", "neutral", "slight sell", "sell high"]:
        subset = [r for r in pitchers if r["signal_norm"] == tier]
        if not subset:
            continue
        m_errs = [_f(r["model_era"])  - _f(r["actual_era"]) for r in subset]
        s_errs = [_f(r["signal_era"]) - _f(r["actual_era"]) for r in subset]
        m_mae, n = _mae(m_errs)
        s_mae, _ = _mae(s_errs)
        _tier_mae_row(tier_labels.get(tier, tier), n, m_mae, s_mae, 0, 0)

    # -----------------------------------------------------------------------
    # TABLE 3 — Signal accuracy check (do buy low players actually improve?)
    # -----------------------------------------------------------------------
    print(f"\n{SEP}")
    print("TABLE 3 — Signal Direction Accuracy")
    print("  Does actual wOBA change vs April signal direction match prediction?")
    print(SEP)
    print()

    # For buy low: did actual wOBA rise (positive change)?
    # Use actual_ros_woba vs April wOBA approximation from backtest signal data
    # We'll use woba_actual from v2 file as the April wOBA baseline
    h_sig_lookup: dict = {}
    with open(HITTER_SIG_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("year", "").strip() == "2025":
                bid = row.get("mlbam_id", "").strip()
                h_sig_lookup[bid] = row

    print("  Hitters — % who improved wOBA (May-July vs April) by signal tier:")
    print(f"  {'Tier':<12} {'n':>4} {'n_matched':>10} {'% improved':>12} {'avg Δwoba':>12}")
    print(f"  {'-'*12} {'-'*4} {'-'*10} {'-'*12} {'-'*12}")

    for tier in ["buy low", "slight buy", "neutral", "slight sell", "sell high"]:
        subset = [r for r in hitters if r["signal_norm"] == tier
                  and _f(r.get("actual_ros_woba")) == _f(r.get("actual_ros_woba"))]
        improved = []
        for r in subset:
            bid = str(r.get("mlbam_id","")).strip()
            sig_row = h_sig_lookup.get(bid)
            if not sig_row:
                continue
            april_woba = _f(sig_row.get("woba_actual"))
            ros_woba   = _f(r.get("actual_ros_woba"))
            if math.isfinite(april_woba) and math.isfinite(ros_woba):
                improved.append(ros_woba - april_woba)

        n_total = len(subset)
        n_matched = len(improved)
        if n_matched == 0:
            print(f"  {tier_labels.get(tier,tier):<12} {n_total:>4} {'—':>10} {'—':>12} {'—':>12}")
            continue
        pct_improved = sum(1 for d in improved if d > 0) / n_matched
        avg_delta = sum(improved) / n_matched
        arrow = "↑" if tier in ("buy low", "slight buy") else ("↓" if tier in ("sell high", "slight sell") else "—")
        direction_correct = (tier in ("buy low", "slight buy") and pct_improved > 0.50) or \
                            (tier in ("sell high", "slight sell") and pct_improved < 0.50)
        dc_str = "✓" if direction_correct else "✗"
        if tier == "neutral":
            dc_str = " "
        print(f"  {tier_labels.get(tier,tier):<12} {n_total:>4} {n_matched:>10} "
              f"{pct_improved:>11.1%} {avg_delta:>+12.4f}  {dc_str}")

    print()
    print("  Pitchers — % whose ERA improved (declined) by signal tier:")
    print(f"  {'Tier':<12} {'n':>4} {'% improved ERA':>15} {'avg ΔERA':>12}")
    print(f"  {'-'*12} {'-'*4} {'-'*15} {'-'*12}")

    p_sig_lookup: dict = {}
    with open(PITCHER_SIG_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("year", "").strip() == "2025":
                bid = row.get("mlbam_id", "").strip()
                p_sig_lookup[bid] = row

    for tier in ["buy low", "neutral", "sell high"]:
        subset = [r for r in pitchers if r["signal_norm"] == tier]
        deltas = []
        for r in subset:
            bid = str(r.get("mlbam_id","")).strip()
            sig_row = p_sig_lookup.get(bid)
            if not sig_row:
                continue
            april_era  = _f(sig_row.get("era_actual"))
            actual_era = _f(r.get("actual_era"))
            if math.isfinite(april_era) and math.isfinite(actual_era):
                # negative delta = ERA improved (lower is better)
                deltas.append(actual_era - april_era)

        n_total = len(subset)
        n_matched = len(deltas)
        if n_matched == 0:
            print(f"  {tier_labels.get(tier,tier):<12} {n_total:>4} {'—':>15} {'—':>12}")
            continue
        pct_improved = sum(1 for d in deltas if d < 0) / n_matched  # ERA went down = good for buy low
        avg_delta = sum(deltas) / n_matched
        direction_correct = (tier == "buy low" and pct_improved > 0.50) or \
                            (tier == "sell high" and pct_improved < 0.50)
        dc_str = "✓" if direction_correct else ("✗" if tier != "neutral" else " ")
        print(f"  {tier_labels.get(tier,tier):<12} {n_total:>4} "
              f"{pct_improved:>14.1%} {avg_delta:>+12.4f}  {dc_str}")

    # -----------------------------------------------------------------------
    # TABLE 4 — Signal adjustment win rate vs Model-only
    # -----------------------------------------------------------------------
    print(f"\n{SEP}")
    print("TABLE 4 — Signal Adjustment Win Rate vs Model-Only")
    print("  (% of individual players where adding signal reduces absolute error)")
    print(SEP)
    print()
    print("  Hitters:")
    for label, actual_col, model_col, signal_col, pool in [
        ("wOBA",  "actual_ros_woba", "model_woba", "signal_woba", woba_rows),
        ("HR",    "actual_hr",       "model_hr",   "signal_hr",   hitters),
        ("AVG",   "actual_avg",      "model_avg",  "signal_avg",  hitters),
    ]:
        print(f"\n  {label}:")
        for tier in tiers_h:
            subset = [r for r in pool if r["signal_norm"] == tier]
            if not subset:
                continue
            wins = sum(1 for r in subset
                       if math.isfinite(_f(r.get(signal_col)))
                       and math.isfinite(_f(r.get(actual_col)))
                       and abs(_f(r[signal_col]) - _f(r[actual_col])) <
                           abs(_f(r[model_col])  - _f(r[actual_col])))
            n_eval = sum(1 for r in subset
                         if math.isfinite(_f(r.get(signal_col)))
                         and math.isfinite(_f(r.get(actual_col))))
            pct = wins / n_eval if n_eval else float("nan")
            beat = "✓" if pct > 0.50 else " "
            print(f"    {tier_labels.get(tier,tier):<12} n={n_eval:<4} win_rate={pct:>6.1%}  {beat}")

    print()
    print("  Pitchers — ERA:")
    for tier in ["buy low", "neutral", "sell high"]:
        subset = [r for r in pitchers if r["signal_norm"] == tier]
        wins = sum(1 for r in subset
                   if math.isfinite(_f(r.get("signal_era")))
                   and math.isfinite(_f(r.get("actual_era")))
                   and abs(_f(r["signal_era"]) - _f(r["actual_era"])) <
                       abs(_f(r["model_era"])  - _f(r["actual_era"])))
        n_eval = sum(1 for r in subset
                     if math.isfinite(_f(r.get("signal_era")))
                     and math.isfinite(_f(r.get("actual_era"))))
        pct = wins / n_eval if n_eval else float("nan")
        beat = "✓" if pct > 0.50 else " "
        print(f"    {tier_labels.get(tier,tier):<12} n={n_eval:<4} win_rate={pct:>6.1%}  {beat}")

    # -----------------------------------------------------------------------
    # TABLE 5 — Cases where signal hurt accuracy
    # -----------------------------------------------------------------------
    print(f"\n{SEP}")
    print("TABLE 5 — Worst Signal Calls (wOBA — signal made error larger)")
    print(SEP)
    print()

    rows_with_sig = [r for r in woba_rows
                     if r["signal_norm"] not in ("neutral",)
                     and math.isfinite(_f(r.get("signal_woba")))
                     and math.isfinite(_f(r.get("actual_ros_woba")))]

    hurt = []
    for r in rows_with_sig:
        actual   = _f(r["actual_ros_woba"])
        model_e  = abs(_f(r["model_woba"])  - actual)
        signal_e = abs(_f(r["signal_woba"]) - actual)
        delta = signal_e - model_e
        if delta > 0:
            hurt.append((delta, r))

    hurt.sort(key=lambda x: -x[0])
    print(f"  {'Name':<28} {'Signal':<12} {'Actual':>7} {'Model':>7} {'Sig-Adj':>8} {'Model_Err':>10} {'Sig_Err':>8} {'Δ':>6}")
    print(f"  {'-'*28} {'-'*12} {'-'*7} {'-'*7} {'-'*8} {'-'*10} {'-'*8} {'-'*6}")
    for delta, r in hurt[:10]:
        name = r.get("name","")[:27]
        actual   = _f(r["actual_ros_woba"])
        model_e  = _f(r["model_woba"]) - actual
        signal_e = _f(r["signal_woba"]) - actual
        print(f"  {name:<28} {r['signal']:<12} {actual:>7.4f} {_f(r['model_woba']):>7.4f} "
              f"{_f(r['signal_woba']):>8.4f} {model_e:>+10.4f} {signal_e:>+8.4f} {delta:>+6.4f}")

    if not hurt:
        print("  No cases where signal hurt accuracy (signal adjustment was universally helpful).")

    print()
    print("  Summary:")
    n_total_sig = len(rows_with_sig)
    n_hurt = len(hurt)
    n_helped = n_total_sig - n_hurt
    print(f"  Signal improved accuracy: {n_helped}/{n_total_sig} ({100*n_helped/n_total_sig:.1f}%) "
          f"| Hurt accuracy: {n_hurt}/{n_total_sig} ({100*n_hurt/n_total_sig:.1f}%)")

    # -----------------------------------------------------------------------
    # Success criteria check
    # -----------------------------------------------------------------------
    print(f"\n{SEP}")
    print("SUCCESS CRITERIA")
    print(SEP)
    print()

    # Criterion 1: Signal-adj MAE < Model MAE for Buy Low
    bl_h = [r for r in woba_rows if r["signal_norm"] == "buy low"]
    if bl_h:
        bl_m_mae, _ = _mae([_f(r["model_woba"])  - _f(r["actual_ros_woba"]) for r in bl_h])
        bl_s_mae, _ = _mae([_f(r["signal_woba"]) - _f(r["actual_ros_woba"]) for r in bl_h])
        c1 = bl_s_mae < bl_m_mae
        print(f"  [{'PASS' if c1 else 'FAIL'}] Signal-adj MAE < Model MAE for Buy Low (wOBA):  "
              f"Model={bl_m_mae:.4f}  Signal={bl_s_mae:.4f}")
    else:
        print("  [N/A ] No Buy Low hitters in wOBA comparison pool")

    # Criterion 2: Signal-adj MAE < Model MAE for Sell High
    sh_h = [r for r in woba_rows if r["signal_norm"] == "sell high"]
    if sh_h:
        sh_m_mae, _ = _mae([_f(r["model_woba"])  - _f(r["actual_ros_woba"]) for r in sh_h])
        sh_s_mae, _ = _mae([_f(r["signal_woba"]) - _f(r["actual_ros_woba"]) for r in sh_h])
        c2 = sh_s_mae < sh_m_mae
        print(f"  [{'PASS' if c2 else 'FAIL'}] Signal-adj MAE < Model MAE for Sell High (wOBA): "
              f"Model={sh_m_mae:.4f}  Signal={sh_s_mae:.4f}")
    else:
        print("  [N/A ] No Sell High hitters in wOBA comparison pool")

    # Criterion 3: Buy Low players outperform April stats ≥ 60%
    bl_improve = []
    for r in [row for row in hitters if row["signal_norm"] == "buy low"]:
        bid = str(r.get("mlbam_id","")).strip()
        sig_row = h_sig_lookup.get(bid)
        if not sig_row:
            continue
        april_woba = _f(sig_row.get("woba_actual"))
        ros_woba   = _f(r.get("actual_ros_woba"))
        if math.isfinite(april_woba) and math.isfinite(ros_woba):
            bl_improve.append(ros_woba > april_woba)
    if bl_improve:
        bl_pct = sum(bl_improve) / len(bl_improve)
        c3 = bl_pct >= 0.60
        print(f"  [{'PASS' if c3 else 'FAIL'}] Buy Low players outperform April wOBA ≥60%:      "
              f"{bl_pct:.1%} ({sum(bl_improve)}/{len(bl_improve)})")

    # Criterion 4: Sell High players underperform April stats ≥ 60%
    sh_under = []
    for r in [row for row in hitters if row["signal_norm"] == "sell high"]:
        bid = str(r.get("mlbam_id","")).strip()
        sig_row = h_sig_lookup.get(bid)
        if not sig_row:
            continue
        april_woba = _f(sig_row.get("woba_actual"))
        ros_woba   = _f(r.get("actual_ros_woba"))
        if math.isfinite(april_woba) and math.isfinite(ros_woba):
            sh_under.append(ros_woba < april_woba)
    if sh_under:
        sh_pct = sum(sh_under) / len(sh_under)
        c4 = sh_pct >= 0.60
        print(f"  [{'PASS' if c4 else 'FAIL'}] Sell High players underperform April wOBA ≥60%:  "
              f"{sh_pct:.1%} ({sum(sh_under)}/{len(sh_under)})")

    # -----------------------------------------------------------------------
    # Save outputs
    # -----------------------------------------------------------------------
    print(f"\n{SEP}")
    print("Saving outputs...")

    h_fields = list(hitters[0].keys()) if hitters else []
    with open(OUT_HITTER_B, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=h_fields)
        w.writeheader()
        w.writerows(hitters)
    print(f"  Saved: {OUT_HITTER_B}  ({len(hitters)} rows)")

    p_fields = list(pitchers[0].keys()) if pitchers else []
    with open(OUT_PITCHER_B, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=p_fields)
        w.writeheader()
        w.writerows(pitchers)
    print(f"  Saved: {OUT_PITCHER_B}  ({len(pitchers)} rows)")


if __name__ == "__main__":
    main()
