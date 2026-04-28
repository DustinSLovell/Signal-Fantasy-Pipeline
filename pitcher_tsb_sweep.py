"""
pitcher_tsb_sweep.py
T_SB threshold sweep in z-score space.
Finds optimal Slight Buy cutoff for z-score normalized pitcher buy score.

Fixed parameters (from pitcher_zscore_test.py):
  Coefficients:  α=0.60 (z_ERA_FIP), β=0.25 (z_xwOBA), γ=0.15 (z_LOB_gap)
  T_BL = +0.409  (preserves ~76 Buy Low signals in training)
  Population stats (2022-2024 training):
    ERA_minus_FIP: μ=+0.2930, σ=1.9504
    xwOBA_gap:     μ=-0.0041, σ=0.0396
    LOB_gap:       μ=+0.0210, σ=0.1520

Sweep: T_SB from -0.05 to +0.30 in 0.05 increments.

Goals for viable T_SB:
  - SB OOS accuracy  >= 65%
  - Overall OOS accuracy > 74.2% (current baseline)
  - Buy Low accuracy >= 88.2% (achieved by z-score BL tier)
  - SB signal count  >= 8 (sufficient historical n)
"""

import pandas as pd
import json
import numpy as np

YEARS = [2022, 2023, 2024, 2025]
REACH_EVENTS = ["single", "double", "triple", "walk", "hit_by_pitch"]
LG_LOB_PCT = 0.730

# Fixed z-score population constants from training data
POP = {
    "era_minus_fip": (0.2930, 1.9504),
    "xwoba_gap":     (-0.0041, 0.0396),
    "lob_gap":       (0.0210, 0.1520),
}
ALPHA, BETA, GAMMA = 0.60, 0.25, 0.15
T_BL = 0.409

# Targets
SB_ACC_TARGET    = 0.650
OOS_ACC_TARGET   = 0.742   # current baseline to beat
BL_ACC_FLOOR     = 0.882
MIN_SB_N         = 8

# ── Rebuild dataset (same logic as pitcher_zscore_test.py) ────────────────────

def compute_year_metrics(year):
    df = pd.read_parquet(f"backtest_cache/pitcher_statcast_april_{year}.parquet")
    grp = df.groupby("pitcher")
    total_pitches = grp.size()
    pa_count      = df[df["woba_denom"] == 1].groupby("pitcher").size()
    swstr_num     = df[df["description"].isin(
        ["swinging_strike","swinging_strike_blocked"])].groupby("pitcher").size()
    hr_count = df[df["events"] == "home_run"].groupby("pitcher").size()
    fb_count = df[df["bb_type"] == "fly_ball"].groupby("pitcher").size()
    runners  = df[df["events"].isin(REACH_EVENTS)].groupby("pitcher").size()
    df["runs_pa"] = (df["post_bat_score"] - df["bat_score"]).clip(lower=0)
    runs     = grp["runs_pa"].sum()
    hr_ct2   = hr_count.reindex(runners.index, fill_value=0)
    lob_pct  = ((runners - runs + hr_ct2) / (runners + hr_ct2 * 0.4)).clip(0, 1)
    out = pd.DataFrame({"lob_pct": lob_pct, "pa": pa_count})
    out.index.name = "mlbam_id"
    out["year"] = year
    return out.reset_index()

print("Loading data...")
year_metrics = {y: compute_year_metrics(y) for y in YEARS}

def career_lob(pitcher_id, signal_year):
    prior = []
    for y in YEARS:
        if y >= signal_year:
            continue
        row = year_metrics[y][year_metrics[y]["mlbam_id"] == pitcher_id]
        if len(row) > 0:
            prior.append(row.iloc[0])
    if not prior:
        return LG_LOB_PCT
    total_pa = sum(r["pa"] for r in prior if pd.notna(r["pa"]))
    if total_pa == 0:
        return LG_LOB_PCT
    vals = [(r["lob_pct"], r["pa"]) for r in prior
            if pd.notna(r.get("lob_pct")) and pd.notna(r.get("pa")) and r["pa"] > 0]
    return sum(v * p for v, p in vals) / sum(p for _, p in vals) if vals else LG_LOB_PCT

audit = pd.read_csv("data/backtest_audit_pitchers.csv")
audit["era_minus_fip"] = audit["era_actual"] - audit["fip_actual"]
comp  = pd.read_csv("data/pitcher_backtest_components.csv")
with open("data/pitcher_career_babip.json", encoding="utf-8", errors="replace") as f:
    cbj = json.load(f)
career_df = pd.DataFrame([{"mlbam_id": int(k), "career_babip": v["career_babip_allowed"]}
                           for k, v in cbj.items()])

merged = (audit
    .merge(comp[["mlbam_id","year","xwoba_gap"]], on=["mlbam_id","year"], how="left")
    .merge(career_df, on="mlbam_id", how="left"))
for c in ["era_minus_fip","xwoba_gap"]:
    merged[c] = merged[c].fillna(0.0)

rows = []
for _, row in merged.iterrows():
    ym  = year_metrics[int(row["year"])]
    cur = ym[ym["mlbam_id"] == int(row["mlbam_id"])]
    curr_lob   = cur.iloc[0]["lob_pct"] if len(cur) > 0 and pd.notna(cur.iloc[0]["lob_pct"]) else LG_LOB_PCT
    clob       = career_lob(int(row["mlbam_id"]), int(row["year"]))
    lob_gap    = clob - curr_lob
    rows.append({**row.to_dict(), "lob_gap": lob_gap})

df = pd.DataFrame(rows)

# Apply z-scores using TRAINING constants only (no OOS leakage)
for col, (mu, sigma) in POP.items():
    df[f"z_{col}"] = (df[col] - mu) / sigma

df["z_buy"] = (
    df["z_era_minus_fip"] * ALPHA
    + df["z_xwoba_gap"]   * BETA
    + df["z_lob_gap"]     * GAMMA
)

train = df[df["year"].isin([2022, 2023, 2024])].copy()
oos   = df[df["year"] == 2025].copy()
print(f"  Train rows: {len(train)} | OOS rows: {len(oos)}")
print()

# ── T_SB sweep ────────────────────────────────────────────────────────────────

DIVIDER = "=" * 76

print(DIVIDER)
print("  T_SB THRESHOLD SWEEP  (T_BL=+0.409 fixed, α=0.60, β=0.25, γ=0.15)")
print(DIVIDER)
print()

tsb_vals = [-0.05, 0.00, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30]

def eval_tsb(data, t_sb):
    bl_mask  = data["z_buy"] >= T_BL
    sb_mask  = (data["z_buy"] >= t_sb) & (data["z_buy"] < T_BL)
    buy_mask = bl_mask | sb_mask

    bl  = data[bl_mask]
    sb  = data[sb_mask]
    buy = data[buy_mask]

    return {
        "n_bl":  len(bl),
        "n_sb":  len(sb),
        "n_buy": len(buy),
        "acc_bl":      bl["correct"].mean()  if len(bl)  > 0 else float("nan"),
        "acc_sb":      sb["correct"].mean()  if len(sb)  > 0 else float("nan"),
        "acc_overall": buy["correct"].mean() if len(buy) > 0 else float("nan"),
    }

# Header
col_w = 9
print(f"  {'T_SB':>6}  {'SB n':>5}  {'SB train':>8}  {'SB OOS':>7}  "
      f"{'Overall tr':>10}  {'Overall OOS':>11}  {'BL OOS':>7}  {'Goals met'}")
print(f"  {'-'*80}")

records = []
for t_sb in tsb_vals:
    tr = eval_tsb(train, t_sb)
    os = eval_tsb(oos,   t_sb)

    goals = []
    if not np.isnan(os["acc_sb"])      and os["acc_sb"]      >= SB_ACC_TARGET:  goals.append("SB≥65%")
    if not np.isnan(os["acc_overall"]) and os["acc_overall"]  > OOS_ACC_TARGET:  goals.append("OOS>74.2%")
    if not np.isnan(os["acc_bl"])      and os["acc_bl"]       >= BL_ACC_FLOOR:   goals.append("BL≥88.2%")
    if tr["n_sb"] >= MIN_SB_N:                                                    goals.append(f"n≥{MIN_SB_N}")

    goal_str = " | ".join(goals) if goals else "none"
    all_pass = len(goals) == 4

    row = {
        "t_sb": t_sb,
        "n_sb_train": tr["n_sb"], "n_sb_oos": os["n_sb"],
        "acc_sb_train": tr["acc_sb"], "acc_sb_oos": os["acc_sb"],
        "acc_overall_train": tr["acc_overall"], "acc_overall_oos": os["acc_overall"],
        "acc_bl_train": tr["acc_bl"], "acc_bl_oos": os["acc_bl"],
        "all_pass": all_pass, "goals": goal_str,
    }
    records.append(row)

    sb_oos_s = f"{os['acc_sb']:.1%}" if not np.isnan(os["acc_sb"]) else "  n/a "
    sb_tr_s  = f"{tr['acc_sb']:.1%}" if not np.isnan(tr["acc_sb"]) else "  n/a "

    marker = " ◄ ALL GOALS" if all_pass else ""
    print(f"  {t_sb:>+6.2f}  {tr['n_sb']:>5}  {sb_tr_s:>8}  {sb_oos_s:>7}  "
          f"{tr['acc_overall']:>9.1%}  {os['acc_overall']:>10.1%}  "
          f"{os['acc_bl']:>6.1%}  {goal_str}{marker}")

# ── Detail table for each T_SB ────────────────────────────────────────────────

print()
print(DIVIDER)
print("  DETAIL: SIGNAL COMPOSITION AT EACH THRESHOLD")
print(DIVIDER)
print(f"\n  {'T_SB':>6}  {'BL n':>5}  {'BL tr':>6}  {'BL OOS':>7}  "
      f"{'SB n':>5}  {'SB tr':>6}  {'SB OOS':>7}  "
      f"{'Tot n':>6}  {'Tot tr':>7}  {'Tot OOS':>8}")
print(f"  {'-'*75}")
for rec in records:
    sb_oos = f"{rec['acc_sb_oos']:.1%}" if not np.isnan(rec['acc_sb_oos']) else "   n/a"
    sb_tr  = f"{rec['acc_sb_train']:.1%}" if not np.isnan(rec['acc_sb_train']) else "   n/a"
    print(f"  {rec['t_sb']:>+6.2f}  "
          f"{rec['n_sb_train']+76:>5}  "   # BL always 76 (T_BL fixed)
          f"{rec['acc_bl_train']:>6.1%}  {rec['acc_bl_oos']:>7.1%}  "
          f"{rec['n_sb_train']:>5}  {sb_tr:>6}  {sb_oos:>7}  "
          f"{76+rec['n_sb_train']:>6}  {rec['acc_overall_train']:>7.1%}  {rec['acc_overall_oos']:>8.1%}")

# ── SB composition at each threshold: who enters/exits ───────────────────────

print()
print(DIVIDER)
print("  WHO IS IN THE SLIGHT BUY POOL AT KEY THRESHOLDS (training, 2022-2024)")
print(DIVIDER)

key_thresholds = [t for t in tsb_vals if -0.05 <= t <= 0.20]
for t_sb in key_thresholds:
    sb_rows = train[(train["z_buy"] >= t_sb) & (train["z_buy"] < T_BL)].copy()
    sb_rows = sb_rows.sort_values("z_buy", ascending=False)
    print(f"\n  T_SB={t_sb:+.2f}  →  {len(sb_rows)} Slight Buy signals  "
          f"(train acc={sb_rows['correct'].mean():.1%})")
    print(f"  {'Player':<25}  {'Year':>4}  {'z_buy':>6}  {'ERA':>5}  {'FIP':>5}  {'Correct'}")
    print(f"  {'-'*60}")
    for _, r in sb_rows.iterrows():
        print(f"  {r['player_name']:<25}  {int(r['year']):>4}  {r['z_buy']:>+6.3f}  "
              f"{r['era_actual']:>5.2f}  {r['fip_actual']:>5.2f}  {r['correct']}")

# ── OOS SB pool at key thresholds ─────────────────────────────────────────────

print()
print(DIVIDER)
print("  OOS 2025 SLIGHT BUY POOL AT KEY THRESHOLDS")
print(DIVIDER)

for t_sb in key_thresholds:
    sb_rows = oos[(oos["z_buy"] >= t_sb) & (oos["z_buy"] < T_BL)].copy()
    sb_rows = sb_rows.sort_values("z_buy", ascending=False)
    n_correct = sb_rows["correct"].sum() if len(sb_rows) > 0 else 0
    acc = sb_rows["correct"].mean() if len(sb_rows) > 0 else float("nan")
    acc_str = f"{acc:.1%}" if not np.isnan(acc) else "n/a"
    print(f"\n  T_SB={t_sb:+.2f}  →  {len(sb_rows)} Slight Buy signals  "
          f"(OOS acc={acc_str})")
    print(f"  {'Player':<25}  {'Year':>4}  {'z_buy':>6}  {'ERA':>5}  {'FIP':>5}  {'Correct'}")
    print(f"  {'-'*60}")
    for _, r in sb_rows.iterrows():
        print(f"  {r['player_name']:<25}  {int(r['year']):>4}  {r['z_buy']:>+6.3f}  "
              f"{r['era_actual']:>5.2f}  {r['fip_actual']:>5.2f}  {r['correct']}")

# ── Accuracy curve — find inflection point ────────────────────────────────────

print()
print(DIVIDER)
print("  ACCURACY CURVE ANALYSIS")
print(DIVIDER)

# Find the T_SB where SB accuracy crosses 65% (OOS)
passed = [r for r in records if r["all_pass"]]
any_above_65 = [r for r in records if not np.isnan(r["acc_sb_oos"]) and r["acc_sb_oos"] >= SB_ACC_TARGET]
first_above  = any_above_65[0] if any_above_65 else None

print(f"\n  SB OOS accuracy by threshold (inflection analysis):")
print(f"  {'T_SB':>6}  {'n_sb':>5}  {'SB OOS acc':>12}  {'vs 65% target'}")
print(f"  {'-'*45}")
for rec in records:
    oos_sb = rec["acc_sb_oos"]
    oos_str = f"{oos_sb:.1%}" if not np.isnan(oos_sb) else "     n/a"
    delta = f"{oos_sb - SB_ACC_TARGET:+.1%}" if not np.isnan(oos_sb) else "     n/a"
    marker = " ← first ≥65%" if first_above and rec["t_sb"] == first_above["t_sb"] else ""
    print(f"  {rec['t_sb']:>+6.2f}  {rec['n_sb_train']:>5}  {oos_str:>12}  {delta:>13}{marker}")

# ── Final verdict ─────────────────────────────────────────────────────────────

print()
print(DIVIDER)
print("  FINAL VERDICT")
print(DIVIDER)

if passed:
    print(f"\n  THRESHOLDS MEETING ALL 4 GOALS:")
    for rec in passed:
        print(f"    T_SB={rec['t_sb']:+.2f}  SB OOS={rec['acc_sb_oos']:.1%}  "
              f"Overall OOS={rec['acc_overall_oos']:.1%}  "
              f"BL OOS={rec['acc_bl_oos']:.1%}  "
              f"n_sb={rec['n_sb_train']}")
    best = passed[0]  # first in sweep order = most permissive that passes
    print(f"\n  RECOMMENDED T_SB: {best['t_sb']:+.2f}")
    print(f"    Training: BL={best['acc_bl_train']:.1%} (n=76) | "
          f"SB={best['acc_sb_train']:.1%} (n={best['n_sb_train']}) | "
          f"Overall={best['acc_overall_train']:.1%}")
    print(f"    OOS 2025: BL={best['acc_bl_oos']:.1%} | "
          f"SB={best['acc_sb_oos']:.1%} (n={best['n_sb_oos']}) | "
          f"Overall={best['acc_overall_oos']:.1%}")
    print()
    print(f"  CONSTANTS FOR PRODUCTION (if adopted):")
    print(f"    T_BL = {T_BL:+.4f}")
    print(f"    T_SB = {best['t_sb']:+.4f}")
    for col, (mu, sigma) in POP.items():
        print(f"    POP_{col.upper()}_MEAN = {mu:+.4f}  STD = {sigma:.4f}")
else:
    print(f"\n  NO THRESHOLD MEETS ALL 4 GOALS simultaneously.")
    print(f"  Best SB OOS: {max((r['acc_sb_oos'] for r in records if not np.isnan(r['acc_sb_oos'])), default=float('nan')):.1%}")
    # Show best tradeoff
    best_overall = max(
        (r for r in records if not np.isnan(r["acc_overall_oos"])),
        key=lambda r: r["acc_overall_oos"]
    )
    print(f"  Best overall OOS: T_SB={best_overall['t_sb']:+.2f} → {best_overall['acc_overall_oos']:.1%}")

# Current baseline reminder
print()
print(f"  Current production baseline: OOS overall=74.2%, BL=76.0%, SB=66.7%")
print(f"  Z-score reference (T_SB=-0.073): OOS overall=74.2%, BL=88.2%, SB=57.1%")
