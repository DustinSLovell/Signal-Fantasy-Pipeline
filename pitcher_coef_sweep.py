"""
pitcher_coef_sweep.py
Sensitivity sweep on pitcher buy score coefficients.
Uses ONLY 2022-2024 training data to find optimal weights.
Validates against 2025 OOS only after optimal is identified.

Current formula:
  raw_buy_score = ERA_minus_FIP * 0.60
                + xwOBA_gap    * 0.25
                + BABIP_gap    * 0.15

Rules: coefficients must sum to 1.0.
Sweep: each component independently, others scaled proportionally.
Also runs exhaustive grid within reasonable ranges.

Thresholds (raw_buy_score, pre-confidence-scaling):
  >= 0.50  → Buy Low
  >= 0.30  → Slight Buy
  <  0.30  → Neutral (buy side)
"""

import pandas as pd
import json
import numpy as np
from itertools import product

# ── Data loading ─────────────────────────────────────────────────────────────

audit = pd.read_csv("data/backtest_audit_pitchers.csv")
audit["era_minus_fip"] = audit["era_actual"] - audit["fip_actual"]

comp = pd.read_csv("data/pitcher_backtest_components.csv")

with open("data/pitcher_career_babip.json", encoding="utf-8", errors="replace") as f:
    career_babip_raw = json.load(f)
career_df = pd.DataFrame([
    {"mlbam_id": int(k), "career_babip": v["career_babip_allowed"]}
    for k, v in career_babip_raw.items()
])

LG_BABIP = 0.295

merged = audit.merge(
    comp[["mlbam_id", "year", "xwoba_gap", "babip_allowed", "pa"]],
    on=["mlbam_id", "year"], how="left"
).merge(career_df, on="mlbam_id", how="left")

merged["career_babip"] = merged["career_babip"].fillna(LG_BABIP)
merged["babip_gap"]    = merged["babip_allowed"] - merged["career_babip"]

# Fill NaN components with 0 (conservative — no signal)
for col in ["era_minus_fip", "xwoba_gap", "babip_gap"]:
    merged[col] = merged[col].fillna(0.0)

# ── Threshold constants ───────────────────────────────────────────────────────

BUY_LOW_THRESH   = 0.50
SLIGHT_BUY_THRESH = 0.30

def classify_buy(score):
    if score >= BUY_LOW_THRESH:
        return "Buy Low"
    if score >= SLIGHT_BUY_THRESH:
        return "Slight Buy"
    return "Neutral"

def eval_accuracy(df_eval, alpha, beta, gamma):
    """Compute accuracy for a coefficient combo on a given dataframe."""
    df = df_eval.copy()
    df["new_score"] = (
        df["era_minus_fip"] * alpha
        + df["xwoba_gap"]   * beta
        + df["babip_gap"]   * gamma
    )
    df["new_signal"] = df["new_score"].apply(classify_buy)

    # Only evaluate pitchers that the model classifies as a buy signal
    buy_rows = df[df["new_signal"].isin(["Buy Low", "Slight Buy"])]
    bl_rows  = df[df["new_signal"] == "Buy Low"]
    sb_rows  = df[df["new_signal"] == "Slight Buy"]

    n_total  = len(buy_rows)
    n_bl     = len(bl_rows)
    n_sb     = len(sb_rows)

    acc_overall = buy_rows["correct"].mean()  if n_total > 0 else float("nan")
    acc_bl      = bl_rows["correct"].mean()   if n_bl    > 0 else float("nan")
    acc_sb      = sb_rows["correct"].mean()   if n_sb    > 0 else float("nan")

    return dict(
        alpha=alpha, beta=beta, gamma=gamma,
        n_buy=n_total, n_bl=n_bl, n_sb=n_sb,
        acc_overall=acc_overall, acc_bl=acc_bl, acc_sb=acc_sb,
    )

# ── Split train / OOS ────────────────────────────────────────────────────────

# Evaluate all rows (buy + sell) but accuracy only computed on buy-classified rows
train = merged[merged["year"].isin([2022, 2023, 2024])].copy()
oos   = merged[merged["year"] == 2025].copy()

# ── Baseline ─────────────────────────────────────────────────────────────────

BASE_ALPHA, BASE_BETA, BASE_GAMMA = 0.60, 0.25, 0.15
baseline_train = eval_accuracy(train, BASE_ALPHA, BASE_BETA, BASE_GAMMA)
baseline_oos   = eval_accuracy(oos,   BASE_ALPHA, BASE_BETA, BASE_GAMMA)

DIVIDER = "=" * 70

print(DIVIDER)
print("  PITCHER BUY SCORE COEFFICIENT SENSITIVITY SWEEP")
print(DIVIDER)
print()
print(f"BASELINE (α=0.60, β=0.25, γ=0.15):")
print(f"  TRAIN 2022-24: overall={baseline_train['acc_overall']:.1%} (n={baseline_train['n_buy']}) | "
      f"BL={baseline_train['acc_bl']:.1%} (n={baseline_train['n_bl']}) | "
      f"SB={baseline_train['acc_sb']:.1%} (n={baseline_train['n_sb']})")
print(f"  OOS  2025:     overall={baseline_oos['acc_overall']:.1%} (n={baseline_oos['n_buy']}) | "
      f"BL={baseline_oos['acc_bl']:.1%} (n={baseline_oos['n_bl']}) | "
      f"SB={baseline_oos['acc_sb']:.1%} (n={baseline_oos['n_sb']})")
print()

# ── Per-component sweeps (others scaled proportionally) ──────────────────────

def proportional_scale(fixed_val, other_a, other_b):
    """Scale other_a and other_b proportionally so all three sum to 1."""
    remaining = 1.0 - fixed_val
    total_other = other_a + other_b
    if total_other == 0:
        return other_a, other_b
    return (other_a / total_other) * remaining, (other_b / total_other) * remaining

print("-" * 70)
print("  SWEEP 1: ERA_minus_FIP coefficient (α), others scaled proportionally")
print("-" * 70)
print(f"  {'α':>6}  {'β':>6}  {'γ':>6}  {'n_buy':>6}  {'Train acc':>10}  {'BL acc':>8}  {'SB acc':>8}")
for a in [0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75]:
    b, g = proportional_scale(a, BASE_BETA, BASE_GAMMA)
    r = eval_accuracy(train, round(a,3), round(b,4), round(g,4))
    marker = " <-- BASELINE" if abs(a - 0.60) < 0.001 else ""
    print(f"  {a:>6.2f}  {b:>6.3f}  {g:>6.3f}  {r['n_buy']:>6}  "
          f"{r['acc_overall']:>9.1%}  {r['acc_bl']:>7.1%}  {r['acc_sb']:>7.1%}{marker}")

print()
print("-" * 70)
print("  SWEEP 2: xwOBA_gap coefficient (β), others scaled proportionally")
print("-" * 70)
print(f"  {'α':>6}  {'β':>6}  {'γ':>6}  {'n_buy':>6}  {'Train acc':>10}  {'BL acc':>8}  {'SB acc':>8}")
for b in [0.15, 0.20, 0.25, 0.30, 0.35]:
    a, g = proportional_scale(b, BASE_ALPHA, BASE_GAMMA)
    r = eval_accuracy(train, round(a,4), round(b,3), round(g,4))
    marker = " <-- BASELINE" if abs(b - 0.25) < 0.001 else ""
    print(f"  {a:>6.3f}  {b:>6.2f}  {g:>6.3f}  {r['n_buy']:>6}  "
          f"{r['acc_overall']:>9.1%}  {r['acc_bl']:>7.1%}  {r['acc_sb']:>7.1%}{marker}")

print()
print("-" * 70)
print("  SWEEP 3: BABIP_gap coefficient (γ), others scaled proportionally")
print("-" * 70)
print(f"  {'α':>6}  {'β':>6}  {'γ':>6}  {'n_buy':>6}  {'Train acc':>10}  {'BL acc':>8}  {'SB acc':>8}")
for g in [0.05, 0.10, 0.15, 0.20, 0.25]:
    a, b = proportional_scale(g, BASE_ALPHA, BASE_BETA)
    r = eval_accuracy(train, round(a,4), round(b,4), round(g,3))
    marker = " <-- BASELINE" if abs(g - 0.15) < 0.001 else ""
    print(f"  {a:>6.3f}  {b:>6.3f}  {g:>6.2f}  {r['n_buy']:>6}  "
          f"{r['acc_overall']:>9.1%}  {r['acc_bl']:>7.1%}  {r['acc_sb']:>7.1%}{marker}")

# ── Exhaustive grid search ────────────────────────────────────────────────────

print()
print("-" * 70)
print("  EXHAUSTIVE GRID SEARCH (all combos summing to 1.0, train 2022-24)")
print("-" * 70)

alpha_vals = [0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75]
beta_vals  = [0.15, 0.20, 0.25, 0.30, 0.35]
gamma_vals = [0.05, 0.10, 0.15, 0.20, 0.25]

results = []
for a, b, g in product(alpha_vals, beta_vals, gamma_vals):
    if abs(a + b + g - 1.0) < 0.001:
        r = eval_accuracy(train, a, b, g)
        results.append(r)

results_df = pd.DataFrame(results).dropna(subset=["acc_overall"])
results_df = results_df.sort_values("acc_overall", ascending=False)

print(f"  Valid combinations (sum=1.0): {len(results_df)}")
print()
print("  TOP 10 by training accuracy:")
print(f"  {'α':>6}  {'β':>6}  {'γ':>6}  {'n_buy':>6}  {'Train acc':>10}  {'BL acc':>8}  {'SB acc':>8}")
for _, row in results_df.head(10).iterrows():
    marker = " <-- BASELINE" if (abs(row['alpha']-0.60) < 0.001 and
                                  abs(row['beta']-0.25)  < 0.001 and
                                  abs(row['gamma']-0.15) < 0.001) else ""
    print(f"  {row['alpha']:>6.2f}  {row['beta']:>6.2f}  {row['gamma']:>6.2f}  {row['n_buy']:>6.0f}  "
          f"{row['acc_overall']:>9.1%}  {row['acc_bl']:>7.1%}  {row['acc_sb']:>7.1%}{marker}")

print()
print("  BOTTOM 5 by training accuracy:")
print(f"  {'α':>6}  {'β':>6}  {'γ':>6}  {'n_buy':>6}  {'Train acc':>10}  {'BL acc':>8}  {'SB acc':>8}")
for _, row in results_df.tail(5).iterrows():
    print(f"  {row['alpha']:>6.2f}  {row['beta']:>6.2f}  {row['gamma']:>6.2f}  {row['n_buy']:>6.0f}  "
          f"{row['acc_overall']:>9.1%}  {row['acc_bl']:>7.1%}  {row['acc_sb']:>7.1%}")

# ── Optimal combo: apply to OOS ──────────────────────────────────────────────

best_row = results_df.iloc[0]
opt_a, opt_b, opt_g = best_row["alpha"], best_row["beta"], best_row["gamma"]
opt_oos = eval_accuracy(oos, opt_a, opt_b, opt_g)

print()
print(DIVIDER)
print("  OOS VALIDATION (2025)")
print(DIVIDER)
print()
print(f"Baseline  (α=0.60, β=0.25, γ=0.15):")
print(f"  OOS: overall={baseline_oos['acc_overall']:.1%} (n={baseline_oos['n_buy']}) | "
      f"BL={baseline_oos['acc_bl']:.1%} (n={baseline_oos['n_bl']}) | "
      f"SB={baseline_oos['acc_sb']:.1%} (n={baseline_oos['n_sb']})")
print()
print(f"Optimal   (α={opt_a:.2f}, β={opt_b:.2f}, γ={opt_g:.2f}):")
print(f"  Train: overall={best_row['acc_overall']:.1%} (n={int(best_row['n_buy'])}) | "
      f"BL={best_row['acc_bl']:.1%} | SB={best_row['acc_sb']:.1%}")
print(f"  OOS:   overall={opt_oos['acc_overall']:.1%} (n={opt_oos['n_buy']}) | "
      f"BL={opt_oos['acc_bl']:.1%} (n={opt_oos['n_bl']}) | "
      f"SB={opt_oos['acc_sb']:.1%} (n={opt_oos['n_sb']})")
delta_oos = opt_oos["acc_overall"] - baseline_oos["acc_overall"]
print(f"  OOS delta vs baseline: {delta_oos:+.1%}")

# ── Component importance analysis ─────────────────────────────────────────────

print()
print(DIVIDER)
print("  COMPONENT IMPORTANCE ANALYSIS")
print(DIVIDER)
train_buy = train[train["signal"].isin(["Buy Low", "Slight Buy"])].copy()
print(f"\nMean component values (training buy signals, n={len(train_buy)}):")
print(f"  ERA_minus_FIP:  mean={train_buy['era_minus_fip'].mean():.3f}  "
      f"std={train_buy['era_minus_fip'].std():.3f}")
print(f"  xwOBA_gap:      mean={train_buy['xwoba_gap'].mean():.3f}  "
      f"std={train_buy['xwoba_gap'].std():.3f}")
print(f"  BABIP_gap:      mean={train_buy['babip_gap'].mean():.3f}  "
      f"std={train_buy['babip_gap'].std():.3f}")
print()

# Weighted contribution at baseline
print("Mean weighted contribution to raw_buy_score (baseline coefficients):")
print(f"  ERA_minus_FIP × 0.60: {train_buy['era_minus_fip'].mean() * 0.60:.4f}")
print(f"  xwOBA_gap     × 0.25: {train_buy['xwoba_gap'].mean()    * 0.25:.4f}")
print(f"  BABIP_gap     × 0.15: {train_buy['babip_gap'].mean()    * 0.15:.4f}")
print()

# Correlation of each component with correct outcome
print("Component → outcome correlation (buy signals only):")
for col in ["era_minus_fip", "xwoba_gap", "babip_gap"]:
    corr = train_buy[col].corr(train_buy["correct"].astype(float))
    print(f"  {col:<18}: r={corr:.3f}")

print()
print(DIVIDER)
print("  VERDICT")
print(DIVIDER)
train_delta = best_row["acc_overall"] - baseline_train["acc_overall"]
print(f"  Baseline train:   {baseline_train['acc_overall']:.1%}")
print(f"  Best combo train: {best_row['acc_overall']:.1%}  (Δ={train_delta:+.1%})")
print(f"  Baseline OOS:     {baseline_oos['acc_overall']:.1%}")
print(f"  Optimal OOS:      {opt_oos['acc_overall']:.1%}    (Δ={delta_oos:+.1%})")
if abs(train_delta) < 0.010:
    print()
    print("  VERDICT: VERDICT-NEUTRAL. Current coefficients are near-optimal.")
    print("  Training improvement < 1pp. Do not change production coefficients.")
elif delta_oos >= 0.010:
    print()
    print(f"  VERDICT: POTENTIAL IMPROVEMENT. Train +{train_delta:.1%}, OOS +{delta_oos:.1%}.")
    print(f"  Recommend running ablation before adopting (α={opt_a:.2f}, β={opt_b:.2f}, γ={opt_g:.2f}).")
else:
    print()
    print(f"  VERDICT: OVERFIT. Train delta {train_delta:+.1%} but OOS delta {delta_oos:+.1%}.")
    print("  Do not change production coefficients.")
