"""
backtest_pitcher_zscore.py
Authoritative ablation: z-score normalized buy score through the full
backtest engine with all production gates applied.

Version E  = current production (BABIP_gap, raw score, confidence scaling)
Version Z  = z-normalized (LOB_gap replaces BABIP_gap, direct threshold comparison)
  raw_buy_z = z_ERA_FIP × 0.60 + z_xwOBA × 0.25 + z_LOB_gap × 0.15
  z_X = (X - μ_train) / σ_train
  μ/σ computed from 2022-2024 ALL-pitcher training data (no OOS leakage)
  T_BL = +0.409 | T_SB = +0.200

All Version E gates preserved in Version Z:
  - ERA >= 3.50 global floor
  - ERA >= 3.75 for Buy Low
  - ERA >= 4.00 for Slight Buy
  - Buy qualification (FIP, SwStr%, career IP, GB%)
  - FIP/xERA confluence check

Ablation (Version Z):
  - Z_noLOB:   z_ERA_FIP × 0.706 + z_xwOBA × 0.294  (LOB removed, others rescaled)
  - Z_noxwOBA: z_ERA_FIP × 0.800 + z_LOB × 0.200     (xwOBA removed)
  - Z_noERA:   z_xwOBA × 0.625   + z_LOB × 0.375     (ERA-FIP removed)

Guard rail: OOS 2025 Buy Low accuracy >= 85.7%
"""

import json
import math
import os
import sys
import numpy as np
import pandas as pd
from pathlib import Path

# ── Resolve directories ───────────────────────────────────────────────────────

_SCRIPT_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, str(_SCRIPT_DIR / "archive"))
sys.path.insert(0, str(_SCRIPT_DIR))

from _pitcher_tier_audit import (
    per_start_stats, pitcher_stats, compute_volatility, load_or_fetch,
    CACHE_DIR, P_YEARS, ERA_FLAT, MIN_APRIL_IP, MIN_OUTCOME_IP,
    career_babip_p,
)
from archive.backtest_pitcher_composite import (
    _add_composite_scores, _april_conf_scale, _classify_split_calibrated,
    _is_buy_qualified, compute_extra_stats, _load_full_parquet,
    _BIRTH_YEARS, _CAREER_IP, _babip_age_mult,
    PARK_FACTORS, LEAGUE_AVG_BABIP, VOL_DAMP,
    E_BUY_LOW_ERA_FLOOR, E_SLIGHT_BUY_ERA_FLOOR, E_ERA_FLOOR,
    E_MIN_BUY_IP, E_BUY_LOW_LS, E_SLIGHT_BUY_LS,
    TIERS,
)

TRAIN_YEARS = [2022, 2023, 2024]
OOS_YEAR    = 2025
ALL_YEARS   = TRAIN_YEARS + [OOS_YEAR]

REACH_EVENTS = {"single", "double", "triple", "walk", "hit_by_pitch"}
LG_LOB_PCT   = 0.724   # from backtest_pitcher_composite LOB_AVG

# ── Z-score thresholds (from pitcher_tsb_sweep.py) ───────────────────────────
T_BL = 0.409
T_SB = 0.200

OOS_GUARD = 0.857   # Buy Low OOS floor

# ── Step 0: Precompute career LOB% baselines from prior-year parquets ─────────

print("Precomputing career LOB% baselines from parquets...")

def _compute_lob_for_year(year: int) -> pd.Series:
    """Returns Series: pitcher → LOB% for that April."""
    path = CACHE_DIR / f"pitcher_statcast_april_{year}.parquet"
    if not path.exists():
        return pd.Series(dtype=float, name="lob_pct")
    sc = _load_full_parquet(path)
    if sc.empty:
        return pd.Series(dtype=float, name="lob_pct")
    sc = sc.copy()
    sc["pitcher"] = pd.to_numeric(sc["pitcher"], errors="coerce")
    sc = sc.dropna(subset=["pitcher"])
    sc["pitcher"] = sc["pitcher"].astype(int)
    ev = sc[sc["events"].notna() & (sc["events"] != "")].copy()
    g  = ev.groupby("pitcher")
    H   = g["events"].apply(lambda s: s.isin({"single","double","triple","home_run"}).sum())
    BB  = g["events"].apply(lambda s: s.isin({"walk","intent_walk"}).sum())
    HBP = g["events"].apply(lambda s: (s == "hit_by_pitch").sum())
    HR  = g["events"].apply(lambda s: (s == "home_run").sum())
    sc2 = sc[sc["post_bat_score"].notna() & sc["bat_score"].notna()].copy()
    sc2["runs"] = (sc2["post_bat_score"] - sc2["bat_score"]).clip(lower=0)
    RA  = sc2.groupby("pitcher")["runs"].sum()
    df  = pd.concat([H, BB, HBP, HR, RA], axis=1, keys=["H","BB","HBP","HR","RA"]).fillna(0)
    num = df["H"] + df["BB"] + df["HBP"] - df["RA"]
    den = df["H"] + df["BB"] + df["HBP"] - 1.4 * df["HR"]
    return (num / den).replace([np.inf, -np.inf], np.nan).clip(0, 1).rename("lob_pct")

lob_by_year = {y: _compute_lob_for_year(y) for y in ALL_YEARS}
for y, s in lob_by_year.items():
    print(f"  {y}: {s.notna().sum()} pitchers with LOB%")

def career_lob_baseline(pitcher_id: int, signal_year: int) -> float:
    """PA-weighted career LOB% from all prior years. Falls back to LG_LOB_PCT."""
    records = []
    for y in ALL_YEARS:
        if y >= signal_year:
            continue
        s = lob_by_year[y]
        if pitcher_id in s.index and pd.notna(s[pitcher_id]):
            records.append(s[pitcher_id])
    if not records:
        return LG_LOB_PCT
    return float(np.mean(records))   # simple mean (no PA weight at this level)


# ── Step 1: Run per-year data pipeline, collect raw components ────────────────

def load_year(year: int):
    apr_c  = CACHE_DIR / f"pitcher_statcast_april_{year}.parquet"
    out_c  = CACHE_DIR / f"pitcher_statcast_mayjuly_{year}.parquet"
    if not apr_c.exists() or not out_c.exists():
        return None
    apr_full = _load_full_parquet(apr_c)
    apr_sc   = load_or_fetch(apr_c, f"{year}-04-01", f"{year}-04-30", f"April {year}")
    out_sc   = load_or_fetch(out_c, f"{year}-05-01", f"{year}-07-31", f"May-Jul {year}")
    if apr_sc.empty or out_sc.empty:
        return None
    apr_starts = per_start_stats(apr_sc)
    apr_stats  = pitcher_stats(apr_sc, apr_starts)
    out_stats  = pitcher_stats(out_sc, per_start_stats(out_sc))
    apr_stats  = apr_stats[apr_stats["ip"] >= MIN_APRIL_IP].copy()
    out_stats  = out_stats[out_stats["ip"] >= MIN_OUTCOME_IP].copy()
    vol_df     = compute_volatility(apr_starts) if not apr_starts.empty else pd.DataFrame()
    extra      = compute_extra_stats(apr_full) if len(apr_full.columns) >= 100 else pd.DataFrame()
    return apr_stats, out_stats, vol_df, extra


print("\nLoading all years...")
raw_data = {}
for y in ALL_YEARS:
    result = load_year(y)
    if result:
        raw_data[y] = result
        print(f"  {y}: loaded")
    else:
        print(f"  {y}: MISSING — skipped")


# ── Step 2: Compute raw components per year (add lob_gap, keep era_fip_gap, xwoba_gap) ──

def build_sig(year: int) -> pd.DataFrame | None:
    if year not in raw_data:
        return None
    apr_stats, out_stats, vol_df, extra = raw_data[year]
    sig = apr_stats.copy()
    sig["era_fip_gap"] = sig["era"] - sig["fip"]
    sig["career_ip_g"] = sig["pitcher"].map(_CAREER_IP).fillna(0.0)

    # Merge extra stats (includes lob_pct, xwoba_gap, swstr_rate, gb_pct, etc.)
    sig = _add_composite_scores(sig, extra, year)

    # career xERA for gates
    if "xwoba_allowed" in sig.columns:
        COEF, INTCPT = 3.7083, -0.3305   # from backtest_pitcher_composite
        sig["april_xera"] = (COEF * sig["xwoba_allowed"] + INTCPT).round(3)
    else:
        sig["april_xera"] = float("nan")
    sig["xera_g"] = sig["april_xera"]

    # Volatility dampen
    if not vol_df.empty and "volatility_flag" in vol_df.columns:
        sig = sig.merge(vol_df[["pitcher","volatility_flag"]], on="pitcher", how="left")
        sig["volatility_flag"] = sig["volatility_flag"].fillna(False)
    else:
        sig["volatility_flag"] = False

    # Compute LOB_gap for each pitcher
    sig["_career_lob"] = sig["pitcher"].apply(
        lambda pid: career_lob_baseline(int(pid), year))
    sig["lob_gap"] = sig["_career_lob"] - sig["lob_pct"].fillna(LG_LOB_PCT)

    # Merge outcome
    merged = sig.merge(
        out_stats[["pitcher","era","ip"]].rename(
            columns={"era":"outcome_era","ip":"outcome_ip"}),
        on="pitcher", how="inner"
    )
    merged["era_change"] = merged["outcome_era"] - merged["era"]
    merged["outcome"]    = np.where(
        merged["era_change"] <= -ERA_FLAT, "IMPROVED",
        np.where(merged["era_change"] >= ERA_FLAT, "DECLINED", "FLAT"))
    merged["year"] = year
    return merged


print("\nBuilding signal DataFrames...")
sig_dfs = {}
for y in ALL_YEARS:
    df = build_sig(y)
    if df is not None:
        sig_dfs[y] = df
        print(f"  {y}: {len(df)} pitchers with outcomes")


# ── Step 3: Compute population stats from 2022-2024 training data ─────────────

train_all = pd.concat([sig_dfs[y] for y in TRAIN_YEARS if y in sig_dfs], ignore_index=True)

POP = {}
for col in ["era_fip_gap", "xwoba_gap", "lob_gap"]:
    mu = train_all[col].mean()
    sd = train_all[col].std()
    POP[col] = (mu, sd)

DIVIDER = "=" * 72
print()
print(DIVIDER)
print("  POPULATION STATISTICS (2022-2024 all qualifying pitchers)")
print(DIVIDER)
for col, (mu, sd) in POP.items():
    print(f"  {col:<18}  μ={mu:+.4f}  σ={sd:.4f}")
print()
print("  [Diagnostic constants were: ERA_FIP μ=+0.2930/σ=1.9504, "
      "xwOBA μ=−0.0041/σ=0.0396, LOB μ=+0.0210/σ=0.1520]")

# Apply z-scores to all years using TRAINING constants only
for y, df in sig_dfs.items():
    for col, (mu, sd) in POP.items():
        df[f"z_{col}"] = (df[col] - mu) / sd


# ── Step 4: Classification functions ─────────────────────────────────────────

def _e_classify(row) -> str:
    """Version E: production-aligned (current model)."""
    bs  = float(row.get("_buy_d_raw") or 0.0)
    ss  = float(row.get("_sell_d_raw") or 0.0)
    ip  = float(row.get("ip") or 0.0)
    era = float(row.get("era") or 0.0)
    fip_r = float(row.get("fip", float("nan")))
    if bs > 0 and ss >= 0:
        dominant_buy = bs >= 1.50
        if ip < E_MIN_BUY_IP and not dominant_buy:
            return "NEUTRAL"
        if ip < E_MIN_BUY_IP and not pd.isna(fip_r) and fip_r < 1.50:
            return "NEUTRAL"
        xera_r    = row.get("xera_g", float("nan"))
        swstr_r   = row.get("swstr_rate", float("nan"))
        gb_r      = row.get("gb_pct", float("nan"))
        career_ip = float(row.get("career_ip_g", 0.0))
        if not _is_buy_qualified(fip_r, xera_r, swstr_r, career_ip, gb_r):
            return "NEUTRAL"
        if era < E_ERA_FLOOR:
            return "NEUTRAL"
        xera_f = float(xera_r) if (xera_r is not None and not pd.isna(xera_r)) else float("nan")
        if (not dominant_buy and not math.isnan(xera_f) and not pd.isna(fip_r)
                and abs(fip_r - xera_f) > 1.50 and xera_f > 4.50
                and float(row.get("era_fip_gap", 0.0)) < 2.50):
            return "NEUTRAL"
        scaled = bs * _april_conf_scale(ip)
        if scaled >= E_BUY_LOW_LS:
            if era < E_BUY_LOW_ERA_FLOOR:
                return "NEUTRAL"
            return "BUY_LOW"
        if scaled >= E_SLIGHT_BUY_LS:
            if era < E_SLIGHT_BUY_ERA_FLOOR:
                return "NEUTRAL"
            return "SLIGHT_BUY"
    return _classify_split_calibrated(row["composite_d"])


def _z_classify(row, a_era=0.60, b_xwoba=0.25, g_lob=0.15) -> str:
    """Version Z: z-score normalized buy score, all gates preserved."""
    # Compute z-scored buy signal
    z_era  = float(row.get("z_era_fip_gap", 0.0) or 0.0)
    z_xw   = float(row.get("z_xwoba_gap",  0.0) or 0.0)
    z_lob  = float(row.get("z_lob_gap",    0.0) or 0.0)
    z_buy  = z_era * a_era + z_xw * b_xwoba + z_lob * g_lob

    # Only fire buy side when z_buy is positive AND sell side isn't dominant
    ss = float(row.get("_sell_d_raw") or 0.0)
    if z_buy <= 0 or ss < 0:
        return _classify_split_calibrated(row["composite_d"])

    # All gates identical to Version E
    ip  = float(row.get("ip", 0.0))
    era = float(row.get("era", 0.0))
    fip_r = float(row.get("fip", float("nan")))
    dominant_buy = z_buy >= 1.50   # same conceptual threshold in z-space

    if ip < E_MIN_BUY_IP and not dominant_buy:
        return "NEUTRAL"
    if ip < E_MIN_BUY_IP and not pd.isna(fip_r) and fip_r < 1.50:
        return "NEUTRAL"

    xera_r    = row.get("xera_g", float("nan"))
    swstr_r   = row.get("swstr_rate", float("nan"))
    gb_r      = row.get("gb_pct", float("nan"))
    career_ip = float(row.get("career_ip_g", 0.0))
    if not _is_buy_qualified(fip_r, xera_r, swstr_r, career_ip, gb_r):
        return "NEUTRAL"

    if era < E_ERA_FLOOR:
        return "NEUTRAL"

    xera_f = float(xera_r) if (xera_r is not None and not pd.isna(xera_r)) else float("nan")
    if (not dominant_buy and not math.isnan(xera_f) and not pd.isna(fip_r)
            and abs(fip_r - xera_f) > 1.50 and xera_f > 4.50
            and float(row.get("era_fip_gap", 0.0)) < 2.50):
        return "NEUTRAL"

    # Z-score tier thresholds (no confidence scaling — z-score already normalized)
    if z_buy >= T_BL:
        if era < E_BUY_LOW_ERA_FLOOR:
            return "NEUTRAL"
        return "BUY_LOW"
    if z_buy >= T_SB:
        if era < E_SLIGHT_BUY_ERA_FLOOR:
            return "NEUTRAL"
        return "SLIGHT_BUY"

    return _classify_split_calibrated(row["composite_d"])


# ── Step 5: Apply all signal versions ────────────────────────────────────────

versions = {
    "E":        lambda r: _e_classify(r),
    "Z":        lambda r: _z_classify(r, 0.60, 0.25, 0.15),
    "Z_noLOB":  lambda r: _z_classify(r, 0.706, 0.294, 0.000),
    "Z_noxwOBA":lambda r: _z_classify(r, 0.800, 0.000, 0.200),
    "Z_noERA":  lambda r: _z_classify(r, 0.000, 0.625, 0.375),
}

for y, df in sig_dfs.items():
    for vname, fn in versions.items():
        df[f"sig_{vname}"] = df.apply(fn, axis=1)

print(DIVIDER)
print("  SIGNAL COUNTS PER VERSION (all years)")
print(DIVIDER)
print(f"\n  {'Year':<5}  {'Version':<12}  {'BL':>5}  {'SB':>5}  {'SS':>5}  {'SH':>5}  {'N':>5}")
print(f"  {'-'*50}")
for y, df in sorted(sig_dfs.items()):
    for vname in versions:
        col = f"sig_{vname}"
        bl = (df[col] == "BUY_LOW").sum()
        sb = (df[col] == "SLIGHT_BUY").sum()
        ss = (df[col] == "SLIGHT_SELL").sum()
        sh = (df[col] == "SELL_HIGH").sum()
        n  = (df[col] == "NEUTRAL").sum()
        print(f"  {y:<5}  {vname:<12}  {bl:>5}  {sb:>5}  {ss:>5}  {sh:>5}  {n:>5}")


# ── Step 6: Accuracy reporting ────────────────────────────────────────────────

def accuracy_table(all_df: pd.DataFrame, sig_col: str):
    tiers = ["BUY_LOW", "SLIGHT_BUY", "SLIGHT_SELL", "SELL_HIGH"]
    results = {}
    for t in tiers:
        sub = all_df[all_df[sig_col] == t]
        if len(sub) == 0:
            results[t] = (0, float("nan"))
            continue
        correct = sub["outcome"].apply(
            lambda o: o in ("IMPROVED" if t in ("BUY_LOW","SLIGHT_BUY") else ("DECLINED","FLAT"))
        ).mean()
        results[t] = (len(sub), correct)
    # Overall buy
    buy = all_df[all_df[sig_col].isin(["BUY_LOW","SLIGHT_BUY"])]
    if len(buy) > 0:
        buy_correct = buy["outcome"].isin(["IMPROVED"]).mean()
    else:
        buy_correct = float("nan")
    return results, (len(buy), buy_correct)


def print_version_comparison(label: str, train_dfs, oos_dfs):
    print()
    print(DIVIDER)
    print(f"  {label}")
    print(DIVIDER)
    print()
    print(f"  {'Version':<12}  {'BL tr':>7}  {'BL n':>5}  {'SB tr':>7}  {'SB n':>5}  "
          f"{'Buy tr':>7}  |  {'BL OOS':>7}  {'BL n':>5}  {'SB OOS':>7}  {'SB n':>5}  "
          f"{'Buy OOS':>8}  {'Guard'}")
    print(f"  {'-'*100}")

    train_all_df = pd.concat(train_dfs, ignore_index=True)
    oos_all_df   = pd.concat(oos_dfs,   ignore_index=True)

    for vname in versions:
        col  = f"sig_{vname}"
        tr_t, (tr_bn, tr_ba)  = accuracy_table(train_all_df, col)
        os_t, (os_bn, os_ba)  = accuracy_table(oos_all_df,   col)

        bl_tr = tr_t["BUY_LOW"]
        sb_tr = tr_t["SLIGHT_BUY"]
        bl_os = os_t["BUY_LOW"]
        sb_os = os_t["SLIGHT_BUY"]

        bl_tr_acc = bl_tr[1]
        sb_tr_acc = sb_tr[1]
        bl_os_acc = bl_os[1]
        sb_os_acc = sb_os[1]

        guard = "PASS" if (not math.isnan(bl_os_acc) and bl_os_acc >= OOS_GUARD) else (
            f"FAIL ({bl_os_acc:.1%})" if not math.isnan(bl_os_acc) else "n/a")

        bl_tr_s  = f"{bl_tr_acc:.1%}" if not math.isnan(bl_tr_acc) else "  n/a"
        sb_tr_s  = f"{sb_tr_acc:.1%}" if not math.isnan(sb_tr_acc) else "  n/a"
        bl_os_s  = f"{bl_os_acc:.1%}" if not math.isnan(bl_os_acc) else "  n/a"
        sb_os_s  = f"{sb_os_acc:.1%}" if not math.isnan(sb_os_acc) else "  n/a"
        tr_ba_s  = f"{tr_ba:.1%}"     if not math.isnan(tr_ba)     else "  n/a"
        os_ba_s  = f"{os_ba:.1%}"     if not math.isnan(os_ba)     else "  n/a"

        print(f"  {vname:<12}  {bl_tr_s:>7}  {bl_tr[0]:>5}  {sb_tr_s:>7}  {sb_tr[0]:>5}  "
              f"{tr_ba_s:>7}  |  {bl_os_s:>7}  {bl_os[0]:>5}  {sb_os_s:>7}  {sb_os[0]:>5}  "
              f"{os_ba_s:>8}  {guard}")
    print()
    print("  Legend: E=current, Z=z-score full, Z_noLOB/noxwOBA/noERA=ablations")


train_list = [sig_dfs[y] for y in TRAIN_YEARS if y in sig_dfs]
oos_list   = [sig_dfs[OOS_YEAR]] if OOS_YEAR in sig_dfs else []

print_version_comparison(
    "ACCURACY: TRAIN (2022-2024) vs OOS (2025)",
    train_list, oos_list
)


# ── Step 7: Per-year breakdown ────────────────────────────────────────────────

print(DIVIDER)
print("  PER-YEAR BREAKDOWN — BUY SIGNALS ONLY (Version E vs Z)")
print(DIVIDER)
print(f"\n  {'Year':<5}  {'V':>2}  {'BL acc':>7}  {'BL n':>5}  {'SB acc':>7}  {'SB n':>5}  {'Buy acc':>8}")
print(f"  {'-'*55}")

for y, df in sorted(sig_dfs.items()):
    for vname in ["E", "Z"]:
        col = f"sig_{vname}"
        res, (bn, ba) = accuracy_table(df, col)
        bl = res["BUY_LOW"];  sb = res["SLIGHT_BUY"]
        bl_s = f"{bl[1]:.1%}" if not math.isnan(bl[1]) else "  n/a"
        sb_s = f"{sb[1]:.1%}" if not math.isnan(sb[1]) else "  n/a"
        ba_s = f"{ba:.1%}"    if not math.isnan(ba)    else "  n/a"
        label = "*OOS*" if y == OOS_YEAR else "train"
        print(f"  {y:<5}  {vname:>2}  {bl_s:>7}  {bl[0]:>5}  "
              f"{sb_s:>7}  {sb[0]:>5}  {ba_s:>8}  {label}")
    print()


# ── Step 8: Ablation summary ──────────────────────────────────────────────────

print(DIVIDER)
print("  ABLATION — CONTRIBUTION OF EACH COMPONENT")
print(DIVIDER)

train_all_df = pd.concat(train_list, ignore_index=True)
oos_all_df   = pd.concat(oos_list,   ignore_index=True) if oos_list else pd.DataFrame()

def buy_acc(df, col):
    buy = df[df[col].isin(["BUY_LOW","SLIGHT_BUY"])]
    return buy["outcome"].isin(["IMPROVED"]).mean() if len(buy) > 0 else float("nan"), len(buy)

z_tr_acc,  z_tr_n  = buy_acc(train_all_df, "sig_Z")
z_oos_acc, z_oos_n = buy_acc(oos_all_df,   "sig_Z") if not oos_all_df.empty else (float("nan"), 0)

print(f"\n  Full Z model (0.60/0.25/0.15): train={z_tr_acc:.1%} (n={z_tr_n}) | "
      f"OOS={z_oos_acc:.1%} (n={z_oos_n})\n")
print(f"  {'Ablation':<14}  {'Train acc':>10}  {'Δ train':>8}  {'OOS acc':>10}  {'Δ OOS':>8}  {'Verdict'}")
print(f"  {'-'*65}")

ablation_map = {
    "Z_noLOB":   "Remove LOB_gap  (0.706/0.294/0.00)",
    "Z_noxwOBA": "Remove xwOBA   (0.800/0.000/0.200)",
    "Z_noERA":   "Remove ERA_FIP  (0.000/0.625/0.375)",
}

for vname, label in ablation_map.items():
    col = f"sig_{vname}"
    tr_a, tr_n   = buy_acc(train_all_df, col)
    oos_a, oos_n = buy_acc(oos_all_df,   col) if not oos_all_df.empty else (float("nan"), 0)
    dt = tr_a  - z_tr_acc
    do = oos_a - z_oos_acc
    if math.isnan(oos_a) or math.isnan(z_oos_acc):
        verdict = "n/a"
    elif do < -0.010:
        verdict = "CONTRIBUTING (removing hurts)"
    elif do > 0.010:
        verdict = "DRAG (removing helps)"
    else:
        verdict = "neutral"
    tr_s  = f"{tr_a:.1%}"  if not math.isnan(tr_a)  else "   n/a"
    oos_s = f"{oos_a:.1%}" if not math.isnan(oos_a) else "   n/a"
    print(f"  {label:<36}  {tr_s:>10}  {dt:>+7.1%}  {oos_s:>10}  {do:>+7.1%}  {verdict}")


# ── Step 9: Final verdict ─────────────────────────────────────────────────────

print()
print(DIVIDER)
print("  FINAL VERDICT")
print(DIVIDER)

e_tr,  e_tr_n  = buy_acc(train_all_df, "sig_E")
e_oos, e_oos_n = buy_acc(oos_all_df,   "sig_E") if not oos_all_df.empty else (float("nan"), 0)
bl_oos_e = accuracy_table(oos_all_df, "sig_E")[0]["BUY_LOW"][1] if not oos_all_df.empty else float("nan")
bl_oos_z = accuracy_table(oos_all_df, "sig_Z")[0]["BUY_LOW"][1] if not oos_all_df.empty else float("nan")

print(f"\n  Version E (current): train={e_tr:.1%} (n={e_tr_n})  OOS={e_oos:.1%} (n={e_oos_n})  "
      f"BL OOS={bl_oos_e:.1%}")
print(f"  Version Z (z-score): train={z_tr_acc:.1%} (n={z_tr_n})  OOS={z_oos_acc:.1%} (n={z_oos_n})  "
      f"BL OOS={bl_oos_z:.1%}")
print()

dt = z_tr_acc  - e_tr
do = z_oos_acc - e_oos

guard_pass = (not math.isnan(bl_oos_z)) and bl_oos_z >= OOS_GUARD

if dt >= 0.010 and do >= 0.005 and guard_pass:
    print(f"  VERDICT: IMPROVEMENT — Train +{dt:.1%}, OOS +{do:.1%}, guard PASS.")
    print(f"  Recommend production adoption after validate_formulas.py 37/37.")
    print(f"  Constants: T_BL={T_BL}, T_SB={T_SB}")
    for col, (mu, sd) in POP.items():
        print(f"    {col}: μ={mu:+.4f}, σ={sd:.4f}")
elif dt >= 0.010 and not guard_pass:
    print(f"  VERDICT: OVERFIT — Train +{dt:.1%} but BL OOS guard FAIL "
          f"({bl_oos_z:.1%} < {OOS_GUARD:.1%}).")
    print(f"  Do not adopt.")
elif abs(dt) < 0.005 and abs(do) < 0.005:
    print(f"  VERDICT: VERDICT-NEUTRAL — no meaningful accuracy change.")
    print(f"  Normalization resolves leverage imbalance but not accuracy improvement.")
else:
    print(f"  VERDICT: MARGINAL — Train {dt:+.1%}, OOS {do:+.1%}.")
    if guard_pass:
        print(f"  Guard PASS. Improvement below 1pp threshold for architectural change.")
    else:
        print(f"  Guard FAIL. Do not adopt.")
