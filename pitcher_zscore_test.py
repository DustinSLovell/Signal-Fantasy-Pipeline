"""
pitcher_zscore_test.py
Diagnostic: z-score normalization of pitcher buy score components.
DOES NOT modify production code.

Formula under test:
  raw_buy = z_ERA_FIP × α + z_xwOBA × β + z_LOB_gap × γ
  where z_X = (X - μ_X_train) / σ_X_train

Population stats: 2022-2024 ALL-pitcher training rows (not just buy signals).
This gives proper "how unusual is this value" context for each component.

Thresholds: calibrated to preserve similar buy signal counts as current model.
  Current training buy signals: ~108 (95 BL + 13 SB)
"""

import pandas as pd
import json
import numpy as np
from itertools import product

YEARS = [2022, 2023, 2024, 2025]
REACH_EVENTS = ["single", "double", "triple", "walk", "hit_by_pitch"]
LG_LOB_PCT = 0.730
LG_SWSTR   = 0.115
LG_HR_FB   = 0.135

# ── Step 0: Recompute all components (same logic as pitcher_component_test.py) ──

def compute_year_metrics(year):
    df = pd.read_parquet(f"backtest_cache/pitcher_statcast_april_{year}.parquet")
    grp = df.groupby("pitcher")
    total_pitches = grp.size()
    pa_count      = df[df["woba_denom"] == 1].groupby("pitcher").size()

    swstr_num = df[df["description"].isin(
        ["swinging_strike", "swinging_strike_blocked"])].groupby("pitcher").size()
    swstr_pct = (swstr_num / total_pitches).fillna(LG_SWSTR)

    hr_count  = df[df["events"] == "home_run"].groupby("pitcher").size()
    fb_count  = df[df["bb_type"] == "fly_ball"].groupby("pitcher").size()
    hr_fb     = (hr_count / fb_count).clip(0, 1)

    runners   = df[df["events"].isin(REACH_EVENTS)].groupby("pitcher").size()
    df["runs_pa"] = (df["post_bat_score"] - df["bat_score"]).clip(lower=0)
    runs      = grp["runs_pa"].sum()
    hr_ct2    = hr_count.reindex(runners.index, fill_value=0)
    lob_num   = runners - runs + hr_ct2
    lob_den   = runners + hr_ct2 * 0.4
    lob_pct   = (lob_num / lob_den).clip(0, 1)

    out = pd.DataFrame({
        "swstr_pct": swstr_pct, "hr_fb": hr_fb,
        "lob_pct":   lob_pct,   "pa":    pa_count,
        "total_pitches": total_pitches,
    })
    out.index.name = "mlbam_id"
    out["year"] = year
    return out.reset_index()

print("Computing per-year metrics...")
year_metrics = {y: compute_year_metrics(y) for y in YEARS}
for y, df in year_metrics.items():
    print(f"  {y}: {len(df)} pitchers")

def career_baseline(pitcher_id, signal_year):
    prior_rows = []
    for y in YEARS:
        if y >= signal_year:
            continue
        row = year_metrics[y][year_metrics[y]["mlbam_id"] == pitcher_id]
        if len(row) > 0:
            prior_rows.append(row.iloc[0])
    if not prior_rows:
        return {"career_lob": LG_LOB_PCT}
    total_pa = sum(r["pa"] for r in prior_rows if pd.notna(r["pa"]))
    if total_pa == 0:
        return {"career_lob": LG_LOB_PCT}
    def wavg(field):
        vals = [(r[field], r["pa"]) for r in prior_rows
                if pd.notna(r.get(field)) and pd.notna(r.get("pa")) and r["pa"] > 0]
        return sum(v * p for v, p in vals) / sum(p for _, p in vals) if vals else None
    return {"career_lob": wavg("lob_pct") or LG_LOB_PCT}

# Load audit + components
audit = pd.read_csv("data/backtest_audit_pitchers.csv")
audit["era_minus_fip"] = audit["era_actual"] - audit["fip_actual"]
comp  = pd.read_csv("data/pitcher_backtest_components.csv")
with open("data/pitcher_career_babip.json", encoding="utf-8", errors="replace") as f:
    cbj = json.load(f)
career_df = pd.DataFrame([{"mlbam_id": int(k), "career_babip": v["career_babip_allowed"]}
                           for k, v in cbj.items()])

merged = (audit
    .merge(comp[["mlbam_id","year","xwoba_gap","babip_allowed","pa"]], on=["mlbam_id","year"], how="left")
    .merge(career_df, on="mlbam_id", how="left"))
merged["career_babip"] = merged["career_babip"].fillna(0.295)
merged["babip_gap"]    = merged["babip_allowed"] - merged["career_babip"]
for c in ["era_minus_fip","xwoba_gap","babip_gap"]:
    merged[c] = merged[c].fillna(0.0)

print("\nComputing LOB_gap for all 284 rows...")
rows = []
for _, row in merged.iterrows():
    cb  = career_baseline(int(row["mlbam_id"]), int(row["year"]))
    ym  = year_metrics[int(row["year"])]
    cur = ym[ym["mlbam_id"] == int(row["mlbam_id"])]
    curr_lob = cur.iloc[0]["lob_pct"] if len(cur) > 0 and pd.notna(cur.iloc[0]["lob_pct"]) else LG_LOB_PCT
    lob_gap  = cb["career_lob"] - curr_lob    # positive = below career LOB = unlucky
    rows.append({**row.to_dict(), "curr_lob": curr_lob, "career_lob": cb["career_lob"], "lob_gap": lob_gap})

df = pd.DataFrame(rows)
print(f"  Done. {len(df)} rows.")

# ── Step 1: Population stats from 2022-2024 ALL rows ──────────────────────────

DIVIDER = "=" * 72
train_all = df[df["year"].isin([2022, 2023, 2024])].copy()
oos_all   = df[df["year"] == 2025].copy()

print()
print(DIVIDER)
print("  STEP 1: POPULATION STATISTICS (all 2022-2024 rows, n=213)")
print(DIVIDER)

pop_stats = {}
for col, label in [("era_minus_fip","ERA_minus_FIP"), ("xwoba_gap","xwOBA_gap"), ("lob_gap","LOB_gap")]:
    μ = train_all[col].mean()
    σ = train_all[col].std()
    pop_stats[col] = (μ, σ)
    print(f"  {label:<18}  μ={μ:+.4f}  σ={σ:.4f}  "
          f"range=[{train_all[col].min():.3f}, {train_all[col].max():.3f}]")

print()
print("  [These μ/σ values would be hardcoded in production as constants.]")

# ── Step 2: Apply z-score normalization ───────────────────────────────────────

for col in ["era_minus_fip","xwoba_gap","lob_gap"]:
    μ, σ = pop_stats[col]
    train_all[f"z_{col}"] = (train_all[col] - μ) / σ
    oos_all[f"z_{col}"]   = (oos_all[col]   - μ) / σ   # SAME constants — no OOS leakage

print(DIVIDER)
print("  STEP 2: Z-SCORE DISTRIBUTIONS (2022-2024, all rows)")
print(DIVIDER)
print(f"\n  {'Component':<22}  {'z_mean':>8}  {'z_std':>8}  {'z_min':>8}  {'z_max':>8}")
for col in ["era_minus_fip","xwoba_gap","lob_gap"]:
    zc = f"z_{col}"
    print(f"  {zc:<22}  {train_all[zc].mean():>8.3f}  {train_all[zc].std():>8.3f}  "
          f"{train_all[zc].min():>8.3f}  {train_all[zc].max():>8.3f}")

# Z-scores for buy signal subset
train_buy = train_all[train_all["signal"].isin(["Buy Low","Slight Buy"])].copy()
print(f"\n  Buy signal subset (n={len(train_buy)}), z-score means:")
for col in ["era_minus_fip","xwoba_gap","lob_gap"]:
    zc = f"z_{col}"
    print(f"  {zc:<22}  buy_mean={train_buy[zc].mean():+.3f}  "
          f"(vs all-pitcher mean 0.000)")

# ── Step 3: Component leverage analysis ───────────────────────────────────────

print()
print(DIVIDER)
print("  STEP 3: COMPONENT LEVERAGE (buy signals, baseline coefficients 0.60/0.25/0.15)")
print(DIVIDER)

# Old (unnormalized)
old_contrib = {
    "ERA_minus_FIP × 0.60": train_buy["era_minus_fip"].mean() * 0.60,
    "xwOBA_gap     × 0.25": train_buy["xwoba_gap"].mean()    * 0.25,
    "BABIP_gap     × 0.15": train_buy["babip_gap"].mean()    * 0.15,
}
total_old = sum(old_contrib.values())
print(f"\n  BEFORE normalization (mean weighted contribution to raw_buy_score):")
for k, v in old_contrib.items():
    print(f"    {k} = {v:.4f}  ({v/total_old*100:.1f}% of total)")

# New (z-score normalized)
new_contrib = {
    "z_ERA_FIP × 0.60": train_buy["z_era_minus_fip"].mean() * 0.60,
    "z_xwOBA   × 0.25": train_buy["z_xwoba_gap"].mean()    * 0.25,
    "z_LOB_gap × 0.15": train_buy["z_lob_gap"].mean()      * 0.15,
}
total_new = sum(new_contrib.values())
print(f"\n  AFTER normalization (mean weighted contribution to z-scored raw_buy_score):")
for k, v in new_contrib.items():
    print(f"    {k} = {v:.4f}  ({v/total_new*100:.1f}% of total)")

# Correlation check
print(f"\n  Correlation with correct outcome (z-scored, buy signals only):")
for col in ["era_minus_fip","xwoba_gap","lob_gap"]:
    r_raw = train_buy[col].corr(train_buy["correct"].astype(float))
    r_z   = train_buy[f"z_{col}"].corr(train_buy["correct"].astype(float))
    print(f"    z_{col:<18}  r={r_z:+.3f}  (raw r={r_raw:+.3f} — z-scoring preserves correlation)")

# ── Step 4: Threshold calibration ────────────────────────────────────────────

print()
print(DIVIDER)
print("  STEP 4: THRESHOLD CALIBRATION (target ~95 BL + ~13 SB in training)")
print(DIVIDER)

def classify_z(z_era, z_xwoba, z_lob, alpha, beta, gamma, t_bl, t_sb):
    score = z_era * alpha + z_xwoba * beta + z_lob * gamma
    if score >= t_bl:   return "Buy Low"
    if score >= t_sb:   return "Slight Buy"
    return "Neutral_or_Sell"

# Current training counts
current_bl = (train_all["signal"] == "Buy Low").sum()
current_sb = (train_all["signal"] == "Slight Buy").sum()
print(f"\n  Current training signal counts: BL={current_bl}, SB={current_sb}, total={current_bl+current_sb}")

# Compute z-scored buy scores at baseline coefficients and find natural thresholds
train_all["z_buy_base"] = (
    train_all["z_era_minus_fip"] * 0.60
    + train_all["z_xwoba_gap"]   * 0.25
    + train_all["z_lob_gap"]     * 0.15
)

# Sort and find percentile thresholds
scores_sorted = train_all["z_buy_base"].sort_values(ascending=False)
n_train       = len(train_all)

print(f"\n  z-buy score distribution (baseline α=0.60, β=0.25, γ=0.15):")
for pct in [10, 15, 20, 25, 30, 35, 40, 45, 50]:
    threshold = np.percentile(train_all["z_buy_base"], 100 - pct)
    n_above   = (train_all["z_buy_base"] >= threshold).sum()
    print(f"    Top {pct:2d}% threshold: {threshold:+.3f}  →  {n_above} pitchers above")

# Find BL threshold (top ~45% = 95/213)
target_bl_pct = current_bl / n_train * 100
target_sb_pct = (current_bl + current_sb) / n_train * 100
T_BL = np.percentile(train_all["z_buy_base"], 100 - target_bl_pct)
T_SB = np.percentile(train_all["z_buy_base"], 100 - target_sb_pct)
print(f"\n  Calibrated thresholds (preserving current signal counts):")
print(f"    T_BL = {T_BL:+.3f}  (top {target_bl_pct:.1f}% → ~{current_bl} pitchers)")
print(f"    T_SB = {T_SB:+.3f}  (top {target_sb_pct:.1f}% → ~{current_bl+current_sb} pitchers)")

# Verify
n_bl_cal = (train_all["z_buy_base"] >= T_BL).sum()
n_sb_cal = ((train_all["z_buy_base"] >= T_SB) & (train_all["z_buy_base"] < T_BL)).sum()
print(f"    Verification: BL={n_bl_cal}, SB={n_sb_cal}")

# ── Step 5: Accuracy at calibrated thresholds (baseline coefficients) ─────────

def eval_z(data, alpha, beta, gamma, t_bl, t_sb):
    d = data.copy()
    d["z_buy_score"] = (
        d["z_era_minus_fip"] * alpha
        + d["z_xwoba_gap"]   * beta
        + d["z_lob_gap"]     * gamma
    )
    bl_mask  = d["z_buy_score"] >= t_bl
    sb_mask  = (d["z_buy_score"] >= t_sb) & (d["z_buy_score"] < t_bl)
    buy_mask = bl_mask | sb_mask

    bl_rows   = d[bl_mask]
    sb_rows   = d[sb_mask]
    buy_rows  = d[buy_mask]

    return dict(
        alpha=alpha, beta=beta, gamma=gamma,
        t_bl=t_bl, t_sb=t_sb,
        n_buy=len(buy_rows), n_bl=len(bl_rows), n_sb=len(sb_rows),
        acc_overall=buy_rows["correct"].mean()  if len(buy_rows) > 0 else float("nan"),
        acc_bl=bl_rows["correct"].mean()        if len(bl_rows)  > 0 else float("nan"),
        acc_sb=sb_rows["correct"].mean()        if len(sb_rows)  > 0 else float("nan"),
    )

print()
print(DIVIDER)
print("  STEP 5: BASELINE Z-SCORE ACCURACY (α=0.60, β=0.25, γ=0.15)")
print(DIVIDER)

# Apply z-score columns to OOS (using training μ/σ — no leakage)
base_train_z = eval_z(train_all, 0.60, 0.25, 0.15, T_BL, T_SB)
base_oos_z   = eval_z(oos_all,   0.60, 0.25, 0.15, T_BL, T_SB)

# Current model baseline (unnormalized, from prior sweep)
def classify_raw(score):
    if score >= 0.50: return "Buy Low"
    if score >= 0.30: return "Slight Buy"
    return "Neutral"

train_all["cur_score"]  = train_all["era_minus_fip"]*0.60 + train_all["xwoba_gap"]*0.25 + train_all["babip_gap"]*0.15
train_all["cur_signal"] = train_all["cur_score"].apply(classify_raw)
oos_all["cur_score"]    = oos_all["era_minus_fip"]*0.60 + oos_all["xwoba_gap"]*0.25 + oos_all["babip_gap"]*0.15
oos_all["cur_signal"]   = oos_all["cur_score"].apply(classify_raw)

def eval_raw(data):
    bl  = data[data["cur_signal"] == "Buy Low"]
    sb  = data[data["cur_signal"] == "Slight Buy"]
    buy = data[data["cur_signal"].isin(["Buy Low","Slight Buy"])]
    return dict(n_buy=len(buy), n_bl=len(bl), n_sb=len(sb),
                acc_overall=buy["correct"].mean() if len(buy) > 0 else float("nan"),
                acc_bl=bl["correct"].mean()       if len(bl)  > 0 else float("nan"),
                acc_sb=sb["correct"].mean()       if len(sb)  > 0 else float("nan"))

cur_train = eval_raw(train_all)
cur_oos   = eval_raw(oos_all)

print(f"\n  {'Model':<35}  {'Train n':>7}  {'Train acc':>10}  {'BL acc':>8}  {'SB acc':>8}")
print(f"  {'-'*75}")
print(f"  {'Current (raw, BABIP_gap)':<35}  {cur_train['n_buy']:>7}  "
      f"{cur_train['acc_overall']:>9.1%}  {cur_train['acc_bl']:>7.1%}  {cur_train['acc_sb']:>7.1%}")
print(f"  {'Z-score (LOB_gap, baseline coefs)':<35}  {base_train_z['n_buy']:>7}  "
      f"{base_train_z['acc_overall']:>9.1%}  {base_train_z['acc_bl']:>7.1%}  {base_train_z['acc_sb']:>7.1%}")
print()
print(f"  {'Model':<35}  {'OOS n':>7}  {'OOS acc':>10}  {'BL acc':>8}  {'SB acc':>8}  {'Δ vs current'}")
print(f"  {'-'*80}")
print(f"  {'Current (raw, BABIP_gap)':<35}  {cur_oos['n_buy']:>7}  "
      f"{cur_oos['acc_overall']:>9.1%}  {cur_oos['acc_bl']:>7.1%}  {cur_oos['acc_sb']:>7.1%}")
d_acc = base_oos_z["acc_overall"] - cur_oos["acc_overall"]
d_bl  = base_oos_z["acc_bl"]      - cur_oos["acc_bl"]
print(f"  {'Z-score (LOB_gap, baseline coefs)':<35}  {base_oos_z['n_buy']:>7}  "
      f"{base_oos_z['acc_overall']:>9.1%}  {base_oos_z['acc_bl']:>7.1%}  {base_oos_z['acc_sb']:>7.1%}  "
      f"{d_acc:+.1%}")

# ── Step 6: Coefficient sweep on z-scored inputs ──────────────────────────────

print()
print(DIVIDER)
print("  STEP 6: COEFFICIENT SWEEP (z-score space, train 2022-2024)")
print(DIVIDER)
print(f"  Thresholds fixed: T_BL={T_BL:+.3f}, T_SB={T_SB:+.3f}")
print()

alpha_vals = [0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75]
beta_vals  = [0.15, 0.20, 0.25, 0.30, 0.35]
gamma_vals = [0.05, 0.10, 0.15, 0.20, 0.25]

results = []
for a, b, g in product(alpha_vals, beta_vals, gamma_vals):
    if abs(a + b + g - 1.0) > 0.001:
        continue
    r = eval_z(train_all, a, b, g, T_BL, T_SB)
    results.append(r)

results_df = pd.DataFrame(results).dropna(subset=["acc_overall"])
results_df = results_df.sort_values("acc_overall", ascending=False)

print(f"  Valid combinations: {len(results_df)}")
print()
print(f"  TOP 10 by training accuracy:")
print(f"  {'α':>6}  {'β':>6}  {'γ':>6}  {'n_buy':>7}  {'Train acc':>10}  {'BL acc':>8}  {'SB acc':>8}")
print(f"  {'-'*62}")
for _, row in results_df.head(10).iterrows():
    marker = " ← BASELINE" if (abs(row['alpha']-0.60) < 0.001 and
                                abs(row['beta']-0.25)  < 0.001 and
                                abs(row['gamma']-0.15) < 0.001) else ""
    print(f"  {row['alpha']:>6.2f}  {row['beta']:>6.2f}  {row['gamma']:>6.2f}  "
          f"{row['n_buy']:>7.0f}  {row['acc_overall']:>9.1%}  "
          f"{row['acc_bl']:>7.1%}  {row['acc_sb']:>7.1%}{marker}")

print()
print(f"  BOTTOM 5 by training accuracy:")
print(f"  {'α':>6}  {'β':>6}  {'γ':>6}  {'n_buy':>7}  {'Train acc':>10}  {'BL acc':>8}  {'SB acc':>8}")
for _, row in results_df.tail(5).iterrows():
    print(f"  {row['alpha']:>6.2f}  {row['beta']:>6.2f}  {row['gamma']:>6.2f}  "
          f"{row['n_buy']:>7.0f}  {row['acc_overall']:>9.1%}  "
          f"{row['acc_bl']:>7.1%}  {row['acc_sb']:>7.1%}")

# ── Step 7: OOS validation of best combination ───────────────────────────────

best = results_df.iloc[0]
opt_a, opt_b, opt_g = best["alpha"], best["beta"], best["gamma"]

print()
print(DIVIDER)
print("  STEP 7: OOS VALIDATION (2025)")
print(DIVIDER)

# Guard rail: Buy Low OOS >= 85.7% (current pitcher model OOS)
OOS_GUARD = 0.857

oos_cur  = eval_raw(oos_all)
oos_base = eval_z(oos_all, 0.60, 0.25, 0.15, T_BL, T_SB)
oos_opt  = eval_z(oos_all, opt_a, opt_b, opt_g, T_BL, T_SB)

print(f"\n  Guard rail: BL OOS accuracy >= {OOS_GUARD:.1%}\n")
print(f"  {'Model':<42}  {'OOS n':>6}  {'OOS acc':>9}  {'BL acc':>8}  {'SB acc':>8}  {'Guard'}")
print(f"  {'-'*85}")

for label, r in [
    ("Current (raw, BABIP_gap)",             oos_cur),
    ("Z-score, baseline (0.60/0.25/0.15)",   oos_base),
    (f"Z-score, optimal ({opt_a:.2f}/{opt_b:.2f}/{opt_g:.2f})", oos_opt),
]:
    guard = "PASS" if r["acc_bl"] >= OOS_GUARD else f"FAIL ({r['acc_bl']:.1%} < {OOS_GUARD:.1%})"
    print(f"  {label:<42}  {r['n_buy']:>6}  {r['acc_overall']:>8.1%}  "
          f"{r['acc_bl']:>7.1%}  {r['acc_sb']:>7.1%}  {guard}")

# ── Step 8: Component leverage AFTER normalization ────────────────────────────

print()
print(DIVIDER)
print("  STEP 8: COMPONENT LEVERAGE AFTER NORMALIZATION")
print(DIVIDER)

buy_train_z = train_all[
    (train_all["z_buy_base"] >= T_SB)
].copy()

buy_train_z["z_buy_opt"] = (
    buy_train_z["z_era_minus_fip"] * opt_a
    + buy_train_z["z_xwoba_gap"]   * opt_b
    + buy_train_z["z_lob_gap"]     * opt_g
)

old_comp = {
    "ERA_FIP × 0.60 (raw)":  train_buy["era_minus_fip"].mean() * 0.60,
    "xwOBA   × 0.25 (raw)":  train_buy["xwoba_gap"].mean()    * 0.25,
    "BABIP   × 0.15 (raw)":  train_buy["babip_gap"].mean()    * 0.15,
}
new_comp = {
    f"z_ERA_FIP × {opt_a:.2f}": buy_train_z["z_era_minus_fip"].mean() * opt_a,
    f"z_xwOBA   × {opt_b:.2f}": buy_train_z["z_xwoba_gap"].mean()    * opt_b,
    f"z_LOB_gap × {opt_g:.2f}": buy_train_z["z_lob_gap"].mean()      * opt_g,
}

print(f"\n  BEFORE (raw, buy signals only):")
old_total = sum(old_comp.values())
for k, v in old_comp.items():
    print(f"    {k:<28} = {v:.4f}  ({v/old_total*100:.1f}%)")

print(f"\n  AFTER z-score (optimal, z-buy >= T_SB signals only):")
new_total = sum(new_comp.values())
for k, v in new_comp.items():
    pct = v/new_total*100 if new_total != 0 else 0
    print(f"    {k:<28} = {v:.4f}  ({pct:.1f}%)")

# Also compute for baseline coefs
base_comp = {
    "z_ERA_FIP × 0.60": buy_train_z["z_era_minus_fip"].mean() * 0.60,
    "z_xwOBA   × 0.25": buy_train_z["z_xwoba_gap"].mean()    * 0.25,
    "z_LOB_gap × 0.15": buy_train_z["z_lob_gap"].mean()      * 0.15,
}
base_total = sum(base_comp.values())
print(f"\n  AFTER z-score (baseline 0.60/0.25/0.15):")
for k, v in base_comp.items():
    pct = v/base_total*100 if base_total != 0 else 0
    print(f"    {k:<28} = {v:.4f}  ({pct:.1f}%)")

# ── Final verdict ─────────────────────────────────────────────────────────────

print()
print(DIVIDER)
print("  FINAL VERDICT")
print(DIVIDER)

train_delta = best["acc_overall"] - cur_train["acc_overall"]
oos_delta   = oos_opt["acc_overall"] - cur_oos["acc_overall"]
oos_bl_ok   = oos_opt["acc_bl"] >= OOS_GUARD

print(f"\n  Current model:     train={cur_train['acc_overall']:.1%}  OOS={cur_oos['acc_overall']:.1%}  OOS BL={cur_oos['acc_bl']:.1%}")
print(f"  Z-score baseline:  train={base_train_z['acc_overall']:.1%}  OOS={base_oos_z['acc_overall']:.1%}  OOS BL={base_oos_z['acc_bl']:.1%}")
print(f"  Z-score optimal:   train={best['acc_overall']:.1%}  OOS={oos_opt['acc_overall']:.1%}  OOS BL={oos_opt['acc_bl']:.1%}")
print(f"  Train delta vs current:   {train_delta:+.1%}")
print(f"  OOS delta vs current:     {oos_delta:+.1%}")
print(f"  OOS Buy Low guard (≥85.7%): {'PASS' if oos_bl_ok else 'FAIL'}")

print()
if train_delta >= 0.010 and oos_delta >= 0.005 and oos_bl_ok:
    print(f"  VERDICT: PROMISING — train +{train_delta:.1%}, OOS +{oos_delta:.1%}, guard PASS.")
    print(f"  Recommend full ablation before production adoption.")
    print(f"  Optimal: α={opt_a:.2f}, β={opt_b:.2f}, γ={opt_g:.2f}")
    print(f"  Constants to hardcode: T_BL={T_BL:+.4f}, T_SB={T_SB:+.4f}")
    for col in ["era_minus_fip","xwoba_gap","lob_gap"]:
        μ, σ = pop_stats[col]
        print(f"  {col}: μ={μ:+.4f}, σ={σ:.4f}")
elif train_delta >= 0.010 and not oos_bl_ok:
    print(f"  VERDICT: OVERFIT — train +{train_delta:.1%} but OOS BL guard FAIL.")
    print(f"  Do not adopt z-score architecture.")
elif abs(train_delta) < 0.005 and abs(oos_delta) < 0.005:
    print(f"  VERDICT: VERDICT-NEUTRAL — normalization gives components equal leverage")
    print(f"  but does not improve accuracy. ERA-FIP dominance is correct by design,")
    print(f"  not a scale artifact. Current architecture is optimal.")
else:
    print(f"  VERDICT: MARGINAL — train {train_delta:+.1%}, OOS {oos_delta:+.1%}.")
    print(f"  Improvement too small to justify architectural change.")
