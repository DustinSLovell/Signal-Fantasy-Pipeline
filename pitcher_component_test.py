"""
pitcher_component_test.py
Tests three replacement candidates for the BABIP_gap component (γ=0.15)
in the pitcher buy score formula.

Candidates:
  1. LOB% deviation:  career_lob - current_lob    (positive = unlucky = buy)
  2. SwStr% gap:      current_swstr - career_swstr (positive = still has stuff = buy confirmer)
  3. HR/FB deviation: current_hrfb - career_hrfb  (positive = high HR/FB = unlucky = buy)

Career baselines use only prior-year data (no leakage):
  2022 signal: no prior → use league average as baseline
  2023 signal: 2022 career data
  2024 signal: 2022-2023 pooled
  2025 signal: 2022-2024 pooled

Thresholds (raw_buy_score): >= 0.50 Buy Low | >= 0.30 Slight Buy
Fixed: α=0.60 (ERA-FIP), β=0.25 (xwOBA), γ=0.15 (test component)
"""

import pandas as pd
import json
import numpy as np

YEARS = [2022, 2023, 2024, 2025]
REACH_EVENTS = ["single", "double", "triple", "walk", "hit_by_pitch"]
BUY_LOW_THRESH   = 0.50
SLIGHT_BUY_THRESH = 0.30

# ── League averages (fallback when no career data) ────────────────────────────
LG_LOB_PCT  = 0.730   # MLB average strand rate
LG_SWSTR    = 0.115   # MLB average SwStr%
LG_HR_FB    = 0.135   # MLB average HR/FB

# ── Step 1: Compute raw metrics per pitcher per year from parquets ────────────

def compute_year_metrics(year: int) -> pd.DataFrame:
    df = pd.read_parquet(f"backtest_cache/pitcher_statcast_april_{year}.parquet")

    grp = df.groupby("pitcher")
    total_pitches = grp.size()
    pa_count = df[df["woba_denom"] == 1].groupby("pitcher").size()

    # SwStr%
    swstr_num = df[df["description"].isin(
        ["swinging_strike", "swinging_strike_blocked"])].groupby("pitcher").size()
    swstr_pct = (swstr_num / total_pitches).fillna(0.0)

    # HR/FB  (HR / fly_balls; fly_balls only, not popup)
    hr_count = df[df["events"] == "home_run"].groupby("pitcher").size()
    fb_count = df[df["bb_type"] == "fly_ball"].groupby("pitcher").size()
    hr_fb    = (hr_count / fb_count).clip(0, 1)   # cap at 100%

    # LOB% approximation:  1 - (R / (R + LOB))
    # runners_reached = PA ending in reach event
    runners   = df[df["events"].isin(REACH_EVENTS)].groupby("pitcher").size()
    df["runs_pa"] = (df["post_bat_score"] - df["bat_score"]).clip(lower=0)
    runs      = grp["runs_pa"].sum()
    hr_ct2    = hr_count.reindex(runners.index, fill_value=0)
    lob_num   = runners - runs + hr_ct2
    lob_den   = runners + hr_ct2 * 0.4
    lob_pct   = (lob_num / lob_den).clip(0, 1)

    out = pd.DataFrame({
        "swstr_pct": swstr_pct,
        "hr_fb":     hr_fb,
        "lob_pct":   lob_pct,
        "pa":        pa_count,
        "total_pitches": total_pitches,
    })
    out.index.name = "mlbam_id"
    out["year"] = year
    return out.reset_index()

print("Computing per-year metrics from parquets...")
year_metrics = {}
for y in YEARS:
    year_metrics[y] = compute_year_metrics(y)
    print(f"  {y}: {len(year_metrics[y])} pitchers")
print()

# ── Step 2: Build career baselines (prior-years-only) ────────────────────────

def career_baseline(pitcher_id: int, signal_year: int) -> dict:
    """Pool all prior-year data for a pitcher. Fall back to league avg."""
    prior_rows = []
    for y in YEARS:
        if y >= signal_year:
            continue
        df = year_metrics[y]
        row = df[df["mlbam_id"] == pitcher_id]
        if len(row) > 0:
            prior_rows.append(row.iloc[0])

    if not prior_rows:
        return {
            "career_swstr": LG_SWSTR,
            "career_hr_fb": LG_HR_FB,
            "career_lob":   LG_LOB_PCT,
            "career_source": "league_avg",
        }

    # PA-weighted average across prior years
    total_pa = sum(r["pa"] for r in prior_rows if pd.notna(r["pa"]))
    if total_pa == 0:
        return {
            "career_swstr": LG_SWSTR,
            "career_hr_fb": LG_HR_FB,
            "career_lob":   LG_LOB_PCT,
            "career_source": "league_avg",
        }

    def wavg(field, rows, pa_total):
        vals = [(r[field], r["pa"]) for r in rows
                if pd.notna(r.get(field)) and pd.notna(r.get("pa")) and r["pa"] > 0]
        if not vals:
            return None
        return sum(v * p for v, p in vals) / sum(p for _, p in vals)

    return {
        "career_swstr":  wavg("swstr_pct", prior_rows, total_pa),
        "career_hr_fb":  wavg("hr_fb",     prior_rows, total_pa),
        "career_lob":    wavg("lob_pct",   prior_rows, total_pa),
        "career_source": f"prior_{len(prior_rows)}yr",
    }

# ── Step 3: Load backtest audit and xwOBA / ERA components ───────────────────

audit = pd.read_csv("data/backtest_audit_pitchers.csv")
audit["era_minus_fip"] = audit["era_actual"] - audit["fip_actual"]

comp = pd.read_csv("data/pitcher_backtest_components.csv")
with open("data/pitcher_career_babip.json", encoding="utf-8", errors="replace") as f:
    career_babip_raw = json.load(f)
career_babip_df = pd.DataFrame([
    {"mlbam_id": int(k), "career_babip": v["career_babip_allowed"]}
    for k, v in career_babip_raw.items()
])

merged = (
    audit
    .merge(comp[["mlbam_id","year","xwoba_gap","babip_allowed","pa"]], on=["mlbam_id","year"], how="left")
    .merge(career_babip_df, on="mlbam_id", how="left")
)
merged["career_babip"] = merged["career_babip"].fillna(0.295)
merged["babip_gap"]    = merged["babip_allowed"] - merged["career_babip"]
merged["era_minus_fip"] = merged["era_minus_fip"].fillna(0.0)
merged["xwoba_gap"]     = merged["xwoba_gap"].fillna(0.0)
merged["babip_gap"]     = merged["babip_gap"].fillna(0.0)

# ── Step 4: Compute deviations per row ───────────────────────────────────────

print("Computing career baselines (this may take a moment)...")
rows_with_gaps = []
for _, row in merged.iterrows():
    cb = career_baseline(int(row["mlbam_id"]), int(row["year"]))
    ym = year_metrics[int(row["year"])]
    curr = ym[ym["mlbam_id"] == int(row["mlbam_id"])]

    if len(curr) > 0:
        c = curr.iloc[0]
        curr_swstr = c["swstr_pct"] if pd.notna(c["swstr_pct"]) else LG_SWSTR
        curr_hr_fb = c["hr_fb"]     if pd.notna(c["hr_fb"])     else LG_HR_FB
        curr_lob   = c["lob_pct"]   if pd.notna(c["lob_pct"])   else LG_LOB_PCT
    else:
        curr_swstr, curr_hr_fb, curr_lob = LG_SWSTR, LG_HR_FB, LG_LOB_PCT

    career_swstr = cb["career_swstr"] or LG_SWSTR
    career_hr_fb = cb["career_hr_fb"] or LG_HR_FB
    career_lob   = cb["career_lob"]   or LG_LOB_PCT

    # Deviation signs: positive = unlucky / confirming buy signal
    swstr_gap = curr_swstr - career_swstr    # positive = still has stuff (confirmer)
    hr_fb_gap = curr_hr_fb - career_hr_fb    # positive = above career HR/FB (unlucky)
    lob_gap   = career_lob - curr_lob        # positive = below career LOB% (unlucky)

    rows_with_gaps.append({
        **row.to_dict(),
        "curr_swstr": curr_swstr, "career_swstr": career_swstr, "swstr_gap": swstr_gap,
        "curr_hr_fb": curr_hr_fb, "career_hr_fb": career_hr_fb, "hr_fb_gap": hr_fb_gap,
        "curr_lob":   curr_lob,   "career_lob":   career_lob,   "lob_gap":   lob_gap,
        "career_source": cb["career_source"],
    })

df = pd.DataFrame(rows_with_gaps)
print(f"  Done. {len(df)} rows processed.")
print()

# ── Step 5: Diagnostics — component distributions and correlations ────────────

buy_df  = df[df["signal"].isin(["Buy Low", "Slight Buy"])].copy()
train_b = buy_df[buy_df["year"].isin([2022, 2023, 2024])]

DIVIDER = "=" * 72

print(DIVIDER)
print("  COMPONENT DISTRIBUTIONS (training buy signals, 2022-2024)")
print(DIVIDER)
print(f"\n  {'Component':<22}  {'Mean':>8}  {'Std':>8}  {'Min':>8}  {'Max':>8}")
for col, label in [
    ("babip_gap",  "BABIP_gap (current)"),
    ("lob_gap",    "LOB_gap"),
    ("swstr_gap",  "SwStr_gap"),
    ("hr_fb_gap",  "HR/FB_gap"),
]:
    s = train_b[col]
    print(f"  {label:<22}  {s.mean():>8.4f}  {s.std():>8.4f}  {s.min():>8.4f}  {s.max():>8.4f}")

print()
print(DIVIDER)
print("  CORRELATION WITH CORRECT OUTCOME (training buy signals, 2022-2024)")
print(DIVIDER)
print(f"\n  {'Component':<22}  {'r':>8}  {'Note'}")
print(f"  {'-'*60}")

for col, label, note in [
    ("era_minus_fip", "ERA_minus_FIP",  "dominant driver (kept at 0.60)"),
    ("xwoba_gap",     "xwOBA_gap",      "kept at 0.25"),
    ("babip_gap",     "BABIP_gap",      "current γ=0.15 component"),
    ("lob_gap",       "LOB_gap",        "candidate 1"),
    ("swstr_gap",     "SwStr_gap",      "candidate 2"),
    ("hr_fb_gap",     "HR/FB_gap",      "candidate 3"),
]:
    r = train_b[col].corr(train_b["correct"].astype(float))
    print(f"  {label:<22}  {r:>8.3f}  {note}")

# ── Step 6: Accuracy sweep — each candidate vs BABIP_gap ─────────────────────

def classify_buy(score):
    if score >= BUY_LOW_THRESH:   return "Buy Low"
    if score >= SLIGHT_BUY_THRESH: return "Slight Buy"
    return "Neutral"

def eval_component(data, gamma_col, alpha=0.60, beta=0.25, gamma=0.15):
    d = data.copy()
    d["new_score"] = (
        d["era_minus_fip"] * alpha
        + d["xwoba_gap"]   * beta
        + d[gamma_col]     * gamma
    )
    d["new_signal"] = d["new_score"].apply(classify_buy)
    buy_rows = d[d["new_signal"].isin(["Buy Low", "Slight Buy"])]
    bl_rows  = d[d["new_signal"] == "Buy Low"]
    sb_rows  = d[d["new_signal"] == "Slight Buy"]
    return dict(
        n_buy=len(buy_rows), n_bl=len(bl_rows), n_sb=len(sb_rows),
        acc_overall=buy_rows["correct"].mean() if len(buy_rows) > 0 else float("nan"),
        acc_bl=bl_rows["correct"].mean()       if len(bl_rows)  > 0 else float("nan"),
        acc_sb=sb_rows["correct"].mean()       if len(sb_rows)  > 0 else float("nan"),
    )

train = df[df["year"].isin([2022, 2023, 2024])].copy()
oos   = df[df["year"] == 2025].copy()

print()
print(DIVIDER)
print("  ACCURACY COMPARISON (α=0.60, β=0.25, γ=0.15 for each candidate)")
print(DIVIDER)

candidates = [
    ("babip_gap", "BABIP_gap     (current)"),
    ("lob_gap",   "LOB_gap       (candidate 1)"),
    ("swstr_gap", "SwStr_gap     (candidate 2)"),
    ("hr_fb_gap", "HR/FB_gap     (candidate 3)"),
]

print(f"\n  {'Component':<30}  {'Train n':>8}  {'Train acc':>10}  {'BL acc':>8}  {'SB acc':>8}")
print(f"  {'-'*72}")
train_results = {}
for col, label in candidates:
    r = eval_component(train, col)
    train_results[col] = r
    marker = " ← current" if col == "babip_gap" else ""
    print(f"  {label:<30}  {r['n_buy']:>8}  {r['acc_overall']:>9.1%}  "
          f"{r['acc_bl']:>7.1%}  {r['acc_sb']:>7.1%}{marker}")

print()
print(f"  {'Component':<30}  {'OOS n':>8}  {'OOS acc':>10}  {'BL acc':>8}  {'SB acc':>8}  {'Δ vs BABIP'}")
print(f"  {'-'*80}")
baseline_oos = eval_component(oos, "babip_gap")
for col, label in candidates:
    r = eval_component(oos, col)
    delta = r["acc_overall"] - baseline_oos["acc_overall"]
    marker = " ← current" if col == "babip_gap" else ""
    print(f"  {label:<30}  {r['n_buy']:>8}  {r['acc_overall']:>9.1%}  "
          f"{r['acc_bl']:>7.1%}  {r['acc_sb']:>7.1%}  {delta:+.1%}{marker}")

# ── Step 7: Migration analysis — which pitchers change tier ──────────────────

print()
print(DIVIDER)
print("  TIER MIGRATION ANALYSIS (train 2022-2024, vs BABIP_gap baseline)")
print(DIVIDER)

base_scores = train.copy()
base_scores["base_score"]   = base_scores["era_minus_fip"]*0.60 + base_scores["xwoba_gap"]*0.25 + base_scores["babip_gap"]*0.15
base_scores["base_signal"]  = base_scores["base_score"].apply(classify_buy)

for col, label in [("lob_gap","LOB_gap"), ("swstr_gap","SwStr_gap"), ("hr_fb_gap","HR/FB_gap")]:
    base_scores[f"new_{col}"]  = base_scores["era_minus_fip"]*0.60 + base_scores["xwoba_gap"]*0.25 + base_scores[col]*0.15
    base_scores[f"sig_{col}"]  = base_scores[f"new_{col}"].apply(classify_buy)

    changed = base_scores[base_scores["base_signal"] != base_scores[f"sig_{col}"]]
    print(f"\n  {label}: {len(changed)} tier changes vs BABIP_gap baseline")
    if len(changed) > 0:
        for _, row in changed.iterrows():
            print(f"    {row['player_name']:<22} {row['year']}  "
                  f"{row['base_signal']:>10} → {row[f'sig_{col}']:>10}  "
                  f"correct={row['correct']}")

# ── Step 8: Career source distribution (how often was league avg used) ────────

print()
print(DIVIDER)
print("  CAREER BASELINE SOURCE (2022 always uses league avg — no prior data)")
print(DIVIDER)
for yr in YEARS:
    sub = df[df["year"] == yr]
    sources = sub["career_source"].value_counts()
    print(f"  {yr}: {dict(sources)}")

# ── Step 9: Final verdict ─────────────────────────────────────────────────────

print()
print(DIVIDER)
print("  VERDICT")
print(DIVIDER)

baseline_train = train_results["babip_gap"]
print(f"\n  Baseline BABIP_gap — Train: {baseline_train['acc_overall']:.1%} (n={baseline_train['n_buy']})"
      f" | OOS: {baseline_oos['acc_overall']:.1%} (n={baseline_oos['n_buy']})")
print()

for col, label in [("lob_gap","LOB_gap"), ("swstr_gap","SwStr_gap"), ("hr_fb_gap","HR/FB_gap")]:
    rt = train_results[col]
    ro = eval_component(oos, col)
    dt = rt["acc_overall"] - baseline_train["acc_overall"]
    do = ro["acc_overall"] - baseline_oos["acc_overall"]
    r_corr = train_b[col].corr(train_b["correct"].astype(float))
    if abs(dt) < 0.005 and abs(do) < 0.005:
        verdict = "VERDICT-NEUTRAL"
    elif dt > 0.010 and do > 0.010:
        verdict = "POTENTIAL IMPROVEMENT"
    elif dt > 0.010 and do < 0:
        verdict = "OVERFIT (train gains, OOS loses)"
    else:
        verdict = "MARGINAL / NOISE"
    print(f"  {label:<15} r={r_corr:+.3f}  Train Δ={dt:+.1%}  OOS Δ={do:+.1%}  → {verdict}")
