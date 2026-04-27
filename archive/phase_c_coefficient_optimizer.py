"""
Phase C Coefficient Optimizer
==============================
Uses the within-season backtest results (April 2024 signals -> May-July 2024 outcomes)
to compute empirically-derived multipliers for each seasonal pattern type.

Method:
  For each pattern group, compute the mean wOBA change in the outcome window.
  Empirical multiplier = (pattern group mean change) / (no-pattern group mean change).
  Compare vs current placeholder values in score_luck.py / backtest scripts.

Current placeholder multipliers:
  V-shape buy (slow + summer):       1.20
  Slow starter buy (slow only):      0.80
  Summer performer buy (summer only):1.10
  V-shape sell (slow + summer):      0.90
  Second half fader sell:            1.15
  Fader conflict buy (fader + buy):  0.90

Outputs:
  - Empirical multiplier per group
  - Recommended change (keep / update)
  - Sample sizes and confidence note
"""

import numpy as np
import pandas as pd
from pathlib import Path

BASE_DIR     = Path(__file__).parent
RESULTS_PATH = BASE_DIR / "backtest_results_within_season_v8.csv"
PATTERNS_PATH = BASE_DIR / "data" / "seasonal_patterns.json"

# Current placeholder multipliers in the codebase
CURRENT_MULTIPLIERS = {
    "V-shape (buy x1.20)":                    1.20,
    "V-shape (sell x0.90)":                   0.90,
    "Slow starter (buy x0.80)":               0.80,
    "Summer performer (buy x1.10)":           1.10,
    "Fader (sell x1.15)":                     1.15,
    "Fader conflict (buy x0.90)":             0.90,
    "Slow starter (buy x0.80) + fader conflict": 0.90,
    "No pattern (baseline)":                  1.00,
}


def main():
    print("Phase C Coefficient Optimizer")
    print("=" * 70)

    df = pd.read_csv(RESULTS_PATH)
    print(f"Loaded {len(df)} player-season rows from {RESULTS_PATH.name}")

    # Classify outcome direction (ignoring flat)
    FLAT = 0.015
    df["outcome_dir"] = np.where(
        df["woba_change"] >=  FLAT, "IMPROVED",
        np.where(df["woba_change"] <= -FLAT, "DECLINED", "FLAT")
    )

    # Label the group each player falls into
    df["pattern_group"] = df["seasonal_label"].fillna("No pattern (baseline)")

    # Compute group-level stats
    no_pattern = df[df["pattern_group"] == "No pattern (baseline)"].copy()
    no_pattern_buy  = no_pattern[no_pattern["luck_score_L1"] > 0]
    no_pattern_sell = no_pattern[no_pattern["luck_score_L1"] < 0]

    baseline_buy_mean  = no_pattern_buy["woba_change"].mean()
    baseline_sell_mean = no_pattern_sell["woba_change"].mean()

    print(f"\nBaseline (no pattern):")
    print(f"  Buy signals:  n={len(no_pattern_buy):>3}  mean wOBA chg={baseline_buy_mean:>+.4f}")
    print(f"  Sell signals: n={len(no_pattern_sell):>3}  mean wOBA chg={baseline_sell_mean:>+.4f}")

    # ---- Per-group analysis ----
    WIDTH = 100
    print(f"\n{'=' * WIDTH}")
    print("PER-GROUP ANALYSIS -- empirical multiplier vs current placeholder")
    print(f"{'=' * WIDTH}")
    print(f"  {'Group':<48} {'N':>4} {'Mean chg':>9} {'Emp mult':>9} {'Current':>8} {'Delta':>7} {'Rec'}")
    print(f"  {'-' * 90}")

    groups = df.groupby("pattern_group")
    results = []
    for group_label, grp in sorted(groups, key=lambda x: -len(x[1])):
        n = len(grp)
        mean_chg = grp["woba_change"].mean()
        is_buy   = grp["luck_score_L1"].mean() > 0
        baseline = baseline_buy_mean if is_buy else baseline_sell_mean

        if abs(baseline) < 1e-6:
            emp_mult = float("nan")
        else:
            emp_mult = mean_chg / baseline if not pd.isna(mean_chg) else float("nan")

        current = CURRENT_MULTIPLIERS.get(group_label, float("nan"))
        delta   = emp_mult - current if not pd.isna(emp_mult) and not pd.isna(current) else float("nan")

        if n < 5:
            rec = "SKIP (n<5)"
        elif pd.isna(emp_mult):
            rec = "SKIP"
        elif abs(delta) < 0.05:
            rec = "KEEP"
        elif abs(delta) < 0.15:
            rec = "CONSIDER updating"
        else:
            rec = "RECOMMEND updating"

        emp_str = f"{emp_mult:>9.3f}" if not pd.isna(emp_mult) else "      n/a"
        cur_str = f"{current:>8.2f}" if not pd.isna(current) else "     n/a"
        dlt_str = f"{delta:>+7.3f}" if not pd.isna(delta) else "    n/a"
        print(f"  {group_label:<48} {n:>4} {mean_chg:>+9.4f} {emp_str} {cur_str} {dlt_str}  {rec}")
        results.append({
            "group": group_label, "n": n, "mean_woba_chg": mean_chg,
            "empirical_mult": emp_mult, "current_mult": current,
            "delta": delta, "rec": rec,
        })

    # ---- Accuracy by group (non-flat only) ----
    print(f"\n{'=' * WIDTH}")
    print("ACCURACY BY PATTERN GROUP (non-flat outcomes, directional signal only)")
    print(f"{'=' * WIDTH}")
    RTM = 0.682
    SIGNAL_MAP = {
        'BUY_LOW': 'IMPROVED', 'SLIGHT_BUY': 'IMPROVED',
        'SELL_HIGH': 'DECLINED', 'SLIGHT_SELL': 'DECLINED',
    }

    # Classify signal from L4 score
    conds = [
        df["luck_score_L4"] >= 0.040,
        df["luck_score_L4"] >= 0.020,
        df["luck_score_L4"] <= -0.040,
        df["luck_score_L4"] <= -0.020,
    ]
    df["signal"] = np.select(conds,
        ["BUY_LOW", "SLIGHT_BUY", "SELL_HIGH", "SLIGHT_SELL"], default="NEUTRAL")

    eval_df = df[df["signal"].isin(SIGNAL_MAP) & (df["outcome_dir"] != "FLAT")].copy()
    eval_df["correct"] = eval_df.apply(
        lambda r: r["outcome_dir"] == SIGNAL_MAP[r["signal"]], axis=1
    )

    print(f"  {'Group':<48} {'N':>4} {'Correct':>8} {'Acc':>8} {'vs RTM':>8}")
    print(f"  {'-' * 82}")
    for group_label, grp in sorted(eval_df.groupby("pattern_group"), key=lambda x: -len(x[1])):
        n = len(grp)
        if n < 3:
            continue
        c   = int(grp["correct"].sum())
        acc = c / n
        print(f"  {group_label:<48} {n:>4} {c:>8} {acc:>7.1%} {acc - RTM:>+8.1%}")

    # ---- Mean wOBA change: pattern vs no-pattern, split by signal direction ----
    print(f"\n{'=' * WIDTH}")
    print("SIGNAL DIRECTION BREAKDOWN -- mean wOBA change by group and direction")
    print(f"{'=' * WIDTH}")
    print(f"  {'Group':<48} {'Dir':>5}  {'N':>4} {'Mean chg':>9} {'Med chg':>9}")
    print(f"  {'-' * 82}")
    for group_label, grp in sorted(df.groupby("pattern_group"), key=lambda x: -len(x[1])):
        for direction, subgrp in grp.groupby(np.where(grp["luck_score_L1"] > 0, "BUY", "SELL")):
            n = len(subgrp)
            if n < 3:
                continue
            print(f"  {group_label:<48} {direction:>5}  {n:>4} {subgrp['woba_change'].mean():>+9.4f} {subgrp['woba_change'].median():>+9.4f}")

    # ---- Recommendations summary ----
    print(f"\n{'=' * WIDTH}")
    print("RECOMMENDATIONS -- multipliers to update in score_luck.py / backtest scripts")
    print(f"{'=' * WIDTH}")
    updates = [r for r in results if "update" in r["rec"].lower() and r["n"] >= 5]
    keeps   = [r for r in results if r["rec"] == "KEEP"]

    if updates:
        print(f"\n  UPDATE ({len(updates)} groups):")
        for r in sorted(updates, key=lambda x: abs(x["delta"] or 0), reverse=True):
            print(f"    {r['group']:<48}  current={r['current_mult']:.2f}  "
                  f"empirical={r['empirical_mult']:.3f}  delta={r['delta']:>+.3f}")
    else:
        print("\n  No multipliers recommended for update (all within +/- 0.05 or n<5).")

    if keeps:
        print(f"\n  KEEP ({len(keeps)} groups):")
        for r in keeps:
            emp_str = f"{r['empirical_mult']:.3f}" if not pd.isna(r["empirical_mult"]) else "n/a"
            print(f"    {r['group']:<48}  current={r['current_mult']:.2f}  empirical={emp_str}")

    print(f"\n  NOTE: All estimates from n=19-89 players (April 2024 only).")
    print(f"  Multipliers with n<10 should be treated as directional only, not definitive.")
    print(f"  Recommend re-running after adding 2022 and 2023 backtest years for robustness.")


if __name__ == "__main__":
    main()
