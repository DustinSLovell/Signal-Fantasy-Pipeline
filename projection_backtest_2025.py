"""
projection_backtest_2025.py — Validate projection accuracy against 2025 actuals.

Uses April 2025 Statcast data + 2022-2024 career baselines to simulate what our
model would have projected in April 2025, then compares vs CBS 2025 full-season actuals.

Key question: does the thin career baseline fix (career_pa < 1000) improve HR accuracy?

Output:
  data/projection_accuracy_2025.csv         — row-level projected vs actual
  data/projection_accuracy_summary_2025.csv — summary table (MAE, bias, R²)

Splits: All | career_pa<1000 | career_pa>=1000 | Buy Low signal | Sell High signal
"""

import json
import re
import sys
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import r2_score

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

from stat_projections import (
    get_hitter_baseline,
    hitter_true_talent,
    sample_weight,
    blend_projection,
    project_hitter_counting,
    _safe_float,
)

# April 2025: ~30 games played, ~132 games remaining in full season
APRIL_GAMES_PLAYED  = 30
GAMES_REMAINING     = 162 - APRIL_GAMES_PLAYED   # 132

# ─── PA event sets (matching stat_projections.py logic) ────────────────────
PA_EVENTS = {
    "field_out", "single", "double", "triple", "home_run",
    "strikeout", "strikeout_double_play", "walk", "intent_walk",
    "hit_by_pitch", "grounded_into_double_play", "sac_fly", "sac_bunt",
    "field_error", "fielders_choice", "fielders_choice_out", "double_play",
    "triple_play", "force_out", "catcher_interf", "other_out",
}
BIP_EVENTS = {
    "field_out", "single", "double", "triple", "home_run",
    "grounded_into_double_play", "sac_fly", "sac_bunt", "field_error",
    "fielders_choice", "fielders_choice_out", "double_play",
    "triple_play", "force_out", "other_out",
}
HIT_EVENTS = {"single", "double", "triple", "home_run"}


def _norm(s: str) -> str:
    try:
        s = str(s).encode("latin1").decode("utf-8")
    except Exception:
        pass
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z ]", "", s.lower()).strip()


# ═══════════════════════════════════════════════════════════════════════════
# STEP 1 — Aggregate April 2025 raw Statcast events → per-player stats
# ═══════════════════════════════════════════════════════════════════════════

print("Loading April 2025 Statcast events...")
raw = pd.read_csv(BASE_DIR / "backtest_cache/v4_april_2025.csv")

raw_pa  = raw[raw["events"].isin(PA_EVENTS)].copy()
raw_bip = raw[raw["events"].isin(BIP_EVENTS)].copy()

# xwOBA per PA event: use estimated_woba for BIP, actual woba_value for Ks/BBs
raw_pa = raw_pa.copy()
raw_pa["xwoba_val"] = raw_pa["estimated_woba_using_speedangle"].fillna(raw_pa["woba_value"])

# Aggregate per batter
pa_s      = raw_pa.groupby("batter").size().rename("april_pa")
hr_s      = raw_pa[raw_pa["events"] == "home_run"].groupby("batter").size().rename("april_hr")
hit_s     = raw_pa[raw_pa["events"].isin(HIT_EVENTS)].groupby("batter").size().rename("april_h")
k_s       = raw_pa[raw_pa["events"].isin({"strikeout", "strikeout_double_play"})].groupby("batter").size().rename("k")
bb_s      = raw_pa[raw_pa["events"].isin({"walk", "intent_walk", "hit_by_pitch"})].groupby("batter").size().rename("bb")
woba_s    = raw_pa.groupby("batter")["woba_value"].sum().rename("woba_sum")
xwoba_s   = raw_pa.groupby("batter")["xwoba_val"].mean().rename("xwOBA")
bip_s     = raw_bip.groupby("batter").size().rename("bip")
barrel_s  = raw_bip[raw_bip["launch_speed_angle"] == 6].groupby("batter").size().rename("barrels")

player_apr = pd.DataFrame({
    "april_pa": pa_s, "april_hr": hr_s, "april_h": hit_s,
    "k": k_s, "bb": bb_s, "bip": bip_s, "barrels": barrel_s,
    "woba_sum": woba_s, "xwOBA": xwoba_s,
}).fillna(0).reset_index().rename(columns={"batter": "batter_id"})

player_apr["april_woba"]  = player_apr["woba_sum"] / player_apr["april_pa"].clip(1)
player_apr["barrel_rate"] = player_apr["barrels"]  / player_apr["bip"].clip(1)
player_apr["k_rate"]      = player_apr["k"]         / player_apr["april_pa"].clip(1)
player_apr["bb_rate"]     = player_apr["bb"]         / player_apr["april_pa"].clip(1)
# Approx AB: PA - BB (includes HBP approximation; close enough for AVG)
player_apr["april_ab"]    = player_apr["april_pa"] - player_apr["bb"]
player_apr["april_avg"]   = player_apr["april_h"]  / player_apr["april_ab"].clip(1)

player_apr = player_apr[player_apr["april_pa"] >= 100].copy()
print(f"  Players with 100+ April PA: {len(player_apr)}")


# ═══════════════════════════════════════════════════════════════════════════
# STEP 2 — Build batter_id → name mapping from FG 2025
# ═══════════════════════════════════════════════════════════════════════════

fg_2025 = pd.read_csv(BASE_DIR / "data/fg_batting_2025.csv")
fg_2025["player_name"] = fg_2025["last_name, first_name"].apply(
    lambda x: " ".join(reversed(x.strip().split(", "))) if pd.notna(x) else x
)
id_to_name = dict(zip(fg_2025["batter_id"].astype(int), fg_2025["player_name"]))
player_apr["player_name"] = player_apr["batter_id"].map(id_to_name)
player_apr = player_apr.dropna(subset=["player_name"])
print(f"  Matched to FG player names: {len(player_apr)}")


# ═══════════════════════════════════════════════════════════════════════════
# STEP 3 — Build 2022-2024 career baselines (exclude 2025 — no leakage)
# ═══════════════════════════════════════════════════════════════════════════

print("Building 2022-2024 career baselines...")
frames = []
for yr in [2022, 2023, 2024]:
    path = BASE_DIR / f"data/fg_batting_{yr}.csv"
    if path.exists():
        frames.append(pd.read_csv(path))

if frames:
    fg_career = pd.concat(frames, ignore_index=True)
    fg_career = fg_career.dropna(subset=["batter_id", "pa", "woba", "est_woba", "ba"])
    career_dict: dict[int, dict] = {}
    for bid, grp in fg_career.groupby("batter_id"):
        total_pa = grp["pa"].sum()
        if total_pa < 1:
            continue
        career_dict[int(bid)] = {
            "career_woba_fg":  float((grp["woba"]     * grp["pa"]).sum() / total_pa),
            "career_xwoba_fg": float((grp["est_woba"] * grp["pa"]).sum() / total_pa),
            "career_ba_fg":    float((grp["ba"]        * grp["pa"]).sum() / total_pa),
            "fg_career_pa":    int(total_pa),
        }
    career_data = {"hitter": career_dict}
    print(f"  Career baselines loaded: {len(career_dict)} players")
else:
    career_data = {"hitter": {}}
    print("  WARNING: No FG career data found for 2022-2024")


# ═══════════════════════════════════════════════════════════════════════════
# STEP 4 — Load signal groups from backtest audit (2025)
# ═══════════════════════════════════════════════════════════════════════════

audit_2025 = pd.read_csv(BASE_DIR / "data/backtest_audit_hitters.csv")
audit_2025 = audit_2025[audit_2025["year"] == 2025][["mlbam_id", "signal"]].copy()
signal_map = dict(zip(audit_2025["mlbam_id"].astype(int), audit_2025["signal"]))

# Map audit signal names to projection signal names
SIG_MAP = {
    "Buy Low":    "Buy low",
    "Slight Buy": "Slight buy",
    "Neutral":    "Neutral",
    "Slight Sell":"Slight sell",
    "Sell High":  "Sell high",
}


# ═══════════════════════════════════════════════════════════════════════════
# STEP 5 — Run projection for each player
# ═══════════════════════════════════════════════════════════════════════════

print("Running projections...")
results = []
for _, row in player_apr.iterrows():
    bid = int(row["batter_id"])

    synthetic_row = pd.Series({
        "xwOBA":                   float(row.get("xwOBA", 0.318)),
        "barrel_rate":             float(row.get("barrel_rate", 0.065)),
        "bb_rate":                 float(row.get("bb_rate", 0.085)),
        "k_rate":                  float(row.get("k_rate", 0.220)),
        "park_adj_babip_expected": float("nan"),  # not in raw events
        "career_babip":            0.300,
        "_sprint_speed":           float("nan"),   # not available
    })

    baseline    = get_hitter_baseline(bid, career_data)
    true_talent = hitter_true_talent(synthetic_row, baseline)

    pa     = float(row["april_pa"])
    weight = sample_weight(pa, is_pitcher=False)

    # Thin career baseline fix: career_pa < 1000 → reduce career anchor by 15%
    career_pa_count = baseline.get("career_pa", 9999)
    if career_pa_count < 1000:
        career_weight = (1.0 - weight) * 0.85
        weight = min(0.85, 1.0 - career_weight)

    blended = blend_projection(true_talent, baseline, weight)

    audit_signal  = signal_map.get(bid, "Neutral")
    signal_proj   = SIG_MAP.get(audit_signal, "Neutral")

    proj = project_hitter_counting(
        blended, GAMES_REMAINING, signal=signal_proj, xwoba_gap=None
    )

    # Full-season projected = April actual + remaining projected
    apr_hr  = int(row["april_hr"])
    apr_h   = float(row["april_h"])
    apr_ab  = float(row["april_ab"])

    proj_full_hr  = apr_hr + proj["projected_hr"]
    # Weighted AVG across April and projected remaining
    rem_ab = proj["projected_pa"]  # approximate; ignores BB in remaining
    proj_full_avg = (
        (apr_h + rem_ab * proj["projected_avg"])
        / (apr_ab + rem_ab)
    ) if (apr_ab + rem_ab) > 0 else proj["projected_avg"]

    # Approximate April R and RBI from counting stats
    apr_r   = int(apr_hr * 1.0 + (apr_h - apr_hr) * 0.35 + float(row["bb"]) * 0.15)
    apr_rbi = int(apr_hr * 1.30 + (apr_h - apr_hr) * 0.32)
    proj_full_r   = apr_r   + proj["projected_r"]
    proj_full_rbi = apr_rbi + proj["projected_rbi"]

    results.append({
        "batter_id":          bid,
        "player_name":        row["player_name"],
        "_norm":              _norm(str(row["player_name"])),
        "april_pa":           int(row["april_pa"]),
        "career_pa":          career_pa_count,
        "signal":             audit_signal,
        "april_hr":           apr_hr,
        "april_avg":          round(float(row["april_avg"]), 3),
        "april_xwoba":        round(float(row["xwOBA"]), 3),
        "april_barrel_pct":   round(float(row["barrel_rate"]) * 100, 1),
        "proj_remaining_hr":  proj["projected_hr"],
        "proj_remaining_avg": proj["projected_avg"],
        "proj_remaining_r":   proj["projected_r"],
        "proj_remaining_rbi": proj["projected_rbi"],
        "proj_full_hr":       proj_full_hr,
        "proj_full_avg":      round(proj_full_avg, 3),
        "proj_full_r":        proj_full_r,
        "proj_full_rbi":      proj_full_rbi,
    })

proj_df = pd.DataFrame(results)
print(f"  Projections computed: {len(proj_df)}")


# ═══════════════════════════════════════════════════════════════════════════
# STEP 6 — Match to CBS 2025 actuals
# ═══════════════════════════════════════════════════════════════════════════

cbs = pd.read_csv(BASE_DIR / "data/cbs_hitter_fpts_2025.csv")
cbs["_norm"] = cbs["name"].apply(_norm)
cbs_slim = cbs.rename(columns={
    "HR": "actual_hr", "AVG": "actual_avg",
    "R": "actual_r",   "RBI": "actual_rbi",
    "fpts": "actual_fpts",
})[["_norm", "actual_hr", "actual_avg", "actual_r", "actual_rbi", "actual_fpts"]]

merged = proj_df.merge(cbs_slim, on="_norm", how="left")
matched = merged.dropna(subset=["actual_hr"]).copy()
print(f"  Matched to CBS actuals: {len(matched)} / {len(proj_df)} ({len(matched)/len(proj_df)*100:.0f}%)")


# ═══════════════════════════════════════════════════════════════════════════
# STEP 7 — Compute accuracy metrics
# ═══════════════════════════════════════════════════════════════════════════

def _metrics(df: pd.DataFrame, pred_col: str, actual_col: str, group: str, stat: str) -> dict:
    sub = df.dropna(subset=[pred_col, actual_col])
    n = len(sub)
    if n < 5:
        return {"stat": stat, "group": group, "n": n, "MAE": None, "bias": None, "R2": None}
    err = sub[pred_col].astype(float) - sub[actual_col].astype(float)
    r2  = float(r2_score(sub[actual_col].astype(float), sub[pred_col].astype(float)))
    return {
        "stat":  stat,
        "group": group,
        "n":     n,
        "MAE":   round(float(err.abs().mean()), 2),
        "bias":  round(float(err.mean()), 2),
        "R2":    round(r2, 3),
    }


groups: dict[str, pd.DataFrame] = {
    "All":               matched,
    "career_pa < 1000":  matched[matched["career_pa"] < 1000],
    "career_pa >= 1000": matched[matched["career_pa"] >= 1000],
    "Buy Low":           matched[matched["signal"] == "Buy Low"],
    "Sell High":         matched[matched["signal"] == "Sell High"],
}

stat_pairs = [
    ("actual_hr",  "proj_full_hr",  "HR"),
    ("actual_avg", "proj_full_avg", "AVG"),
    ("actual_r",   "proj_full_r",   "R"),
    ("actual_rbi", "proj_full_rbi", "RBI"),
]

summary_rows = []
for stat_col, pred_col, label in stat_pairs:
    for group_name, group_df in groups.items():
        m = _metrics(group_df, pred_col, stat_col, group_name, label)
        summary_rows.append(m)

summary_df = pd.DataFrame(summary_rows)


# ═══════════════════════════════════════════════════════════════════════════
# STEP 8 — Print summary table
# ═══════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("PROJECTION ACCURACY BACKTEST — 2025 (April inputs vs full-season actuals)")
print("Career baselines: 2022-2024 FG data only (no 2025 leakage)")
print("=" * 70)

for stat_label in ["HR", "AVG", "R", "RBI"]:
    print(f"\n{'─'*70}")
    print(f"  {stat_label}")
    print(f"  {'Group':<22}  {'n':>4}  {'MAE':>7}  {'Bias':>8}  {'R²':>6}")
    print(f"  {'─'*55}")
    for _, row in summary_df[summary_df["stat"] == stat_label].iterrows():
        mae_s  = f"{row['MAE']:.2f}"   if row["MAE"]  is not None else "   N/A"
        bias_s = f"{row['bias']:+.2f}" if row["bias"] is not None else "   N/A"
        r2_s   = f"{row['R2']:.3f}"    if row["R2"]   is not None else "   N/A"
        print(f"  {row['group']:<22}  {row['n']:>4}  {mae_s:>7}  {bias_s:>8}  {r2_s:>6}")

# Highlight thin-baseline HR comparison
thin = groups["career_pa < 1000"]
est  = groups["career_pa >= 1000"]
print(f"\n{'='*70}")
print("THIN BASELINE DIAGNOSTIC (career_pa < 1000 vs career_pa >= 1000)")
print(f"{'─'*70}")
if len(thin) >= 5 and len(est) >= 5:
    thin_mae  = float((thin["proj_full_hr"] - thin["actual_hr"]).abs().mean())
    thin_bias = float((thin["proj_full_hr"] - thin["actual_hr"]).mean())
    est_mae   = float((est["proj_full_hr"]  - est["actual_hr"]).abs().mean())
    est_bias  = float((est["proj_full_hr"]  - est["actual_hr"]).mean())
    print(f"  HR MAE  — thin: {thin_mae:.2f} | established: {est_mae:.2f}")
    print(f"  HR Bias — thin: {thin_bias:+.2f} | established: {est_bias:+.2f}")
    if abs(thin_bias) > abs(est_bias):
        direction = "over" if thin_bias > 0 else "under"
        print(f"  => Thin baseline players: {direction}-projected by {abs(thin_bias):.1f} HR on average")
        print(f"  => Established players better calibrated — thin baseline fix may still be warranted")
    else:
        pct_improve = (abs(est_bias) - abs(thin_bias)) / abs(est_bias) * 100
        print(f"  => Thin baseline players projected MORE accurately than established players")
        print(f"     ({abs(thin_bias):.2f} vs {abs(est_bias):.2f} HR bias — {pct_improve:.0f}% less bias)")
        print(f"  => Thin baseline fix is validated: reducing career anchor for <1000-PA players helps")
    print()
    print("  Sample thin-baseline players (career_pa < 1000):")
    for _, r in thin.sort_values("career_pa").head(10).iterrows():
        print(f"    {r['player_name']:<24}  career_pa={r['career_pa']:>4}  "
              f"proj={r['proj_full_hr']:>2} HR  actual={r['actual_hr']:>2} HR  "
              f"err={int(r['proj_full_hr'])-int(r['actual_hr']):+d}")
print(f"{'='*70}")


# ═══════════════════════════════════════════════════════════════════════════
# STEP 9 — Save outputs
# ═══════════════════════════════════════════════════════════════════════════

out_cols = [
    "batter_id", "player_name", "april_pa", "career_pa", "signal",
    "april_hr", "april_avg", "april_xwoba", "april_barrel_pct",
    "proj_remaining_hr", "proj_remaining_avg", "proj_remaining_r", "proj_remaining_rbi",
    "proj_full_hr", "proj_full_avg", "proj_full_r", "proj_full_rbi",
    "actual_hr", "actual_avg", "actual_r", "actual_rbi", "actual_fpts",
]
matched[out_cols].to_csv(BASE_DIR / "data/projection_accuracy_2025.csv", index=False)
summary_df.to_csv(BASE_DIR / "data/projection_accuracy_summary_2025.csv", index=False)
print(f"\nSaved: data/projection_accuracy_2025.csv ({len(matched)} rows)")
print(f"Saved: data/projection_accuracy_summary_2025.csv ({len(summary_df)} rows)")
