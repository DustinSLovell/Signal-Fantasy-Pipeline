"""
backtest_pitcher_lob_swap.py
Authoritative single-swap test: replace xwOBA_gap (β=0.25) with LOB_gap
in the pitcher buy score formula. No other changes.

Version E = current production:
  raw_buy = ERA_minus_FIP × 0.60 + xwOBA_gap × 0.25 + BABIP_gap × 0.15

Version L = LOB swap:
  raw_buy = ERA_minus_FIP × 0.60 + LOB_gap × 0.25 + BABIP_gap × 0.15

LOB_gap = career_lob_pct − current_april_lob_pct
  (positive = pitcher below career strand rate = unlucky = buy-confirming direction)

All other architecture identical:
  - Same confidence scaling (_april_conf_scale)
  - Same ERA floors (≥3.50 global, ≥3.75 BL, ≥4.00 SB)
  - Same buy qualification gates
  - Same sell-side composite
  - Same thresholds (E_BUY_LOW_LS=0.150, E_SLIGHT_BUY_LS=0.065)

Ablations (Version L):
  L_noLOB:  ERA_FIP × 0.80 + BABIP_gap × 0.20  (LOB removed, others rescaled)
  L_noBABIP: ERA_FIP × 0.706 + LOB_gap × 0.294  (BABIP removed, others rescaled)
  L_noERA:   LOB_gap × 0.625 + BABIP_gap × 0.375 (ERA-FIP removed)

Guard rail: OOS Buy Low ≥ 75.0% (authoritative E baseline from prior run)
"""

import json
import math
import os
import sys
import numpy as np
import pandas as pd
from pathlib import Path

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

LG_LOB_PCT  = 0.724
OOS_GUARD   = 0.750   # authoritative E baseline BL OOS

DIVIDER = "=" * 78


# ── Step 0: Precompute career LOB% baselines from prior-year parquets ──────────

print("Precomputing career LOB% baselines from parquets...")

def _compute_lob_for_year(year: int) -> pd.Series:
    """April LOB% per pitcher for one year."""
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
    g   = ev.groupby("pitcher")
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
    return (num / den).replace([np.inf, -np.inf], np.nan).clip(0, 1).rename("lob_pct_april")

lob_by_year = {y: _compute_lob_for_year(y) for y in ALL_YEARS}
for y, s in lob_by_year.items():
    print(f"  {y}: {s.notna().sum()} pitchers with LOB%")

def career_lob_baseline(pitcher_id: int, signal_year: int) -> float:
    """Simple mean of prior-year LOB%. Falls back to league average."""
    records = []
    for y in ALL_YEARS:
        if y >= signal_year:
            continue
        s = lob_by_year[y]
        if pitcher_id in s.index and pd.notna(s[pitcher_id]):
            records.append(s[pitcher_id])
    if not records:
        return LG_LOB_PCT
    return float(np.mean(records))


# ── Step 1: Load parquets ──────────────────────────────────────────────────────

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


# ── Step 2: Build signal DataFrames with LOB_gap ───────────────────────────────

def build_sig(year: int):
    if year not in raw_data:
        return None
    apr_stats, out_stats, vol_df, extra = raw_data[year]
    sig = apr_stats.copy()
    sig["era_fip_gap"] = sig["era"] - sig["fip"]
    sig["career_ip_g"] = sig["pitcher"].map(_CAREER_IP).fillna(0.0)

    sig = _add_composite_scores(sig, extra, year)

    if "xwoba_allowed" in sig.columns:
        COEF, INTCPT = 3.7083, -0.3305
        sig["april_xera"] = (COEF * sig["xwoba_allowed"] + INTCPT).round(3)
    else:
        sig["april_xera"] = float("nan")
    sig["xera_g"] = sig["april_xera"]

    if not vol_df.empty and "volatility_flag" in vol_df.columns:
        sig = sig.merge(vol_df[["pitcher","volatility_flag"]], on="pitcher", how="left")
        sig["volatility_flag"] = sig["volatility_flag"].fillna(False)
    else:
        sig["volatility_flag"] = False

    # Career LOB baseline and gap
    sig["_career_lob"] = sig["pitcher"].apply(
        lambda pid: career_lob_baseline(int(pid), year))
    # Current April LOB from the per-year series
    lob_curr = lob_by_year[year].rename("_curr_lob")
    sig = sig.merge(lob_curr.reset_index().rename(columns={"pitcher":"pitcher"}),
                    on="pitcher", how="left")
    sig["_curr_lob"] = sig["_curr_lob"].fillna(LG_LOB_PCT)
    sig["lob_gap"] = sig["_career_lob"] - sig["_curr_lob"]

    # Version L raw score (algebraic substitution — babip_gap unchanged)
    # raw_E = era_fip_gap × 0.60 + xwoba_gap × 0.25 + babip_gap × 0.15
    # raw_L = era_fip_gap × 0.60 + lob_gap   × 0.25 + babip_gap × 0.15
    #       = raw_E − xwoba_gap × 0.25 + lob_gap × 0.25
    xwoba_g = sig["xwoba_gap"].fillna(0.0) if "xwoba_gap" in sig.columns else pd.Series(0.0, index=sig.index)
    sig["_raw_L"] = sig["_buy_d_raw"] - xwoba_g * 0.25 + sig["lob_gap"] * 0.25

    # Ablation raw scores
    # L_noLOB:   ERA × 0.80 + BABIP × 0.20 = raw_E − xwoba × 0.25 + (−lob × 0) rescaled
    #   = era_fip_gap × 0.80 + babip_gap × 0.20
    #   Algebraically: raw_E − xwoba_gap × 0.25 − lob_gap × 0 + reweight
    #   Simplest: babip_gap × 0.15 = raw_E − era_fip_gap × 0.60 − xwoba_gap × 0.25
    babip_g_015 = sig["_buy_d_raw"] - sig["era_fip_gap"] * 0.60 - xwoba_g * 0.25
    era_fip_g   = sig["era_fip_gap"]
    sig["_raw_L_noLOB"]   = era_fip_g * 0.80 + babip_g_015 * (0.20 / 0.15)
    sig["_raw_L_noBABIP"] = era_fip_g * 0.706 + sig["lob_gap"] * 0.294
    sig["_raw_L_noERA"]   = sig["lob_gap"] * 0.625 + babip_g_015 * (0.375 / 0.15)

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


# ── Step 3: Component leverage (mean weighted contribution, buy signals) ───────

train_dfs  = [sig_dfs[y] for y in TRAIN_YEARS if y in sig_dfs]
oos_dfs    = [sig_dfs[OOS_YEAR]] if OOS_YEAR in sig_dfs else []
train_all  = pd.concat(train_dfs, ignore_index=True)

print()
print(DIVIDER)
print("  COMPONENT LEVERAGE (raw values, all training pitchers 2022-2024)")
print(DIVIDER)
xwoba_g_tr = (train_all["xwoba_gap"].fillna(0.0)
              if "xwoba_gap" in train_all.columns else pd.Series(0.0, index=train_all.index))
babip_g_tr = (train_all["_buy_d_raw"] - train_all["era_fip_gap"] * 0.60
              - xwoba_g_tr * 0.25) / 0.15

for label, col, weight in [
    ("ERA_minus_FIP", "era_fip_gap", 0.60),
    ("xwOBA_gap  (E)", "xwoba_gap",   0.25),
    ("LOB_gap    (L)", "lob_gap",     0.25),
    ("BABIP_gap",      None,          0.15),
]:
    if label == "BABIP_gap":
        vals = babip_g_tr
    elif label == "xwOBA_gap  (E)":
        vals = xwoba_g_tr
    else:
        vals = train_all[col].fillna(0.0)
    wmean = vals.mean() * weight
    print(f"  {label:<20}  raw mean={vals.mean():+.4f}  ×{weight:.2f} = {wmean:+.5f}")

print()
total_e = (train_all["era_fip_gap"].mean() * 0.60
           + xwoba_g_tr.mean() * 0.25 + babip_g_tr.mean() * 0.15)
total_l = (train_all["era_fip_gap"].mean() * 0.60
           + train_all["lob_gap"].mean() * 0.25 + babip_g_tr.mean() * 0.15)

def pct(component_contrib, total):
    if abs(total) < 1e-9:
        return float("nan")
    return component_contrib / total

era_e = train_all["era_fip_gap"].mean() * 0.60
xw_e  = xwoba_g_tr.mean() * 0.25
bab_e = babip_g_tr.mean() * 0.15
lob_l = train_all["lob_gap"].mean() * 0.25

if abs(total_e) > 1e-9:
    print(f"  Version E leverage:  ERA-FIP={era_e/total_e:.1%}  xwOBA={xw_e/total_e:.1%}  BABIP={bab_e/total_e:.1%}  (total={total_e:+.4f})")
if abs(total_l) > 1e-9:
    print(f"  Version L leverage:  ERA-FIP={era_e/total_l:.1%}  LOB={lob_l/total_l:.1%}  BABIP={bab_e/total_l:.1%}  (total={total_l:+.4f})")


# ── Step 4: Classification functions ─────────────────────────────────────────

def _classify_buy_raw(row, raw_key: str) -> str:
    """Apply buy gates using a pre-computed raw score."""
    raw  = float(row.get(raw_key) or 0.0)
    ss   = float(row.get("_sell_d_raw") or 0.0)
    ip   = float(row.get("ip") or 0.0)
    era  = float(row.get("era") or 0.0)
    fip_r = float(row.get("fip", float("nan")))

    if raw > 0 and ss >= 0:
        dominant_buy = raw >= 1.50
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
        scaled = raw * _april_conf_scale(ip)
        if scaled >= E_BUY_LOW_LS:
            if era < E_BUY_LOW_ERA_FLOOR:
                return "NEUTRAL"
            return "BUY_LOW"
        if scaled >= E_SLIGHT_BUY_LS:
            if era < E_SLIGHT_BUY_ERA_FLOOR:
                return "NEUTRAL"
            return "SLIGHT_BUY"
    return _classify_split_calibrated(row["composite_d"])

def _e_classify(row) -> str:
    return _classify_buy_raw(row, "_buy_d_raw")

def _l_classify(row) -> str:
    return _classify_buy_raw(row, "_raw_L")

def _l_nolob_classify(row) -> str:
    return _classify_buy_raw(row, "_raw_L_noLOB")

def _l_nobabip_classify(row) -> str:
    return _classify_buy_raw(row, "_raw_L_noBABIP")

def _l_noera_classify(row) -> str:
    return _classify_buy_raw(row, "_raw_L_noERA")

versions = {
    "E":         _e_classify,
    "L":         _l_classify,
    "L_noLOB":   _l_nolob_classify,
    "L_noBABIP": _l_nobabip_classify,
    "L_noERA":   _l_noera_classify,
}

print()
print(DIVIDER)
print("  Classifying all years...")
print(DIVIDER)
for y, df in sig_dfs.items():
    for vname, fn in versions.items():
        df[f"sig_{vname}"] = df.apply(fn, axis=1)
    print(f"  {y}: done")


# ── Step 5: Signal counts ──────────────────────────────────────────────────────

print()
print(DIVIDER)
print("  SIGNAL COUNTS PER VERSION (all years)")
print(DIVIDER)
print(f"\n  {'Year':<5}  {'Version':<12}  {'BL':>5}  {'SB':>5}  {'SS':>5}  {'SH':>5}  {'N':>5}")
print(f"  {'-'*52}")
for y, df in sorted(sig_dfs.items()):
    for vname in versions:
        col = f"sig_{vname}"
        bl = (df[col] == "BUY_LOW").sum()
        sb = (df[col] == "SLIGHT_BUY").sum()
        ss = (df[col] == "SLIGHT_SELL").sum()
        sh = (df[col] == "SELL_HIGH").sum()
        n  = (df[col] == "NEUTRAL").sum()
        print(f"  {y:<5}  {vname:<12}  {bl:>5}  {sb:>5}  {ss:>5}  {sh:>5}  {n:>5}")


# ── Step 6: Accuracy helpers ──────────────────────────────────────────────────

def accuracy_table(df: pd.DataFrame, sig_col: str):
    results = {}
    for t in ["BUY_LOW", "SLIGHT_BUY", "SLIGHT_SELL", "SELL_HIGH"]:
        sub = df[df[sig_col] == t]
        if len(sub) == 0:
            results[t] = (0, float("nan"))
            continue
        correct = sub["outcome"].apply(
            lambda o: o in ("IMPROVED" if t in ("BUY_LOW","SLIGHT_BUY") else ("DECLINED","FLAT"))
        ).mean()
        results[t] = (len(sub), correct)
    buy = df[df[sig_col].isin(["BUY_LOW","SLIGHT_BUY"])]
    buy_acc = buy["outcome"].isin(["IMPROVED"]).mean() if len(buy) > 0 else float("nan")
    return results, (len(buy), buy_acc)

def buy_acc(df, col):
    buy = df[df[col].isin(["BUY_LOW","SLIGHT_BUY"])]
    return (buy["outcome"].isin(["IMPROVED"]).mean() if len(buy) > 0 else float("nan")), len(buy)


# ── Step 7: Main accuracy table ───────────────────────────────────────────────

train_all_df = pd.concat(train_dfs, ignore_index=True)
oos_all_df   = pd.concat(oos_dfs,   ignore_index=True) if oos_dfs else pd.DataFrame()

print()
print(DIVIDER)
print("  ACCURACY: TRAIN (2022-2024) vs OOS (2025)")
print(DIVIDER)
print()
print(f"  {'Version':<12}  {'BL tr':>7}  {'BL n':>5}  {'SB tr':>7}  {'SB n':>5}  "
      f"{'Buy tr':>7}  |  {'BL OOS':>7}  {'BL n':>5}  {'SB OOS':>7}  {'SB n':>5}  "
      f"{'Buy OOS':>8}  {'Guard'}")
print(f"  {'-'*105}")

for vname, fn in versions.items():
    col = f"sig_{vname}"
    tr_t, (tr_bn, tr_ba) = accuracy_table(train_all_df, col)
    os_t, (os_bn, os_ba) = accuracy_table(oos_all_df,  col) if not oos_all_df.empty else ({t:(0,float("nan")) for t in ["BUY_LOW","SLIGHT_BUY","SLIGHT_SELL","SELL_HIGH"]}, (0, float("nan")))

    bl_tr = tr_t["BUY_LOW"];   sb_tr = tr_t["SLIGHT_BUY"]
    bl_os = os_t["BUY_LOW"];   sb_os = os_t["SLIGHT_BUY"]

    guard_val = bl_os[1]
    guard = "PASS" if (not math.isnan(guard_val) and guard_val >= OOS_GUARD) else (
        f"FAIL ({guard_val:.1%})" if not math.isnan(guard_val) else "n/a")

    def fmt(v): return f"{v:.1%}" if not math.isnan(v) else "  n/a"

    print(f"  {vname:<12}  {fmt(bl_tr[1]):>7}  {bl_tr[0]:>5}  {fmt(sb_tr[1]):>7}  {sb_tr[0]:>5}  "
          f"{fmt(tr_ba):>7}  |  {fmt(bl_os[1]):>7}  {bl_os[0]:>5}  {fmt(sb_os[1]):>7}  {sb_os[0]:>5}  "
          f"{fmt(os_ba):>8}  {guard}")

print()
print("  Legend: E=current production | L=LOB swap | ablations show component contribution")


# ── Step 8: Per-year breakdown ────────────────────────────────────────────────

print()
print(DIVIDER)
print("  PER-YEAR BREAKDOWN — BUY SIGNALS (Version E vs L)")
print(DIVIDER)
print(f"\n  {'Year':<5}  {'V':>2}  {'BL acc':>7}  {'BL n':>5}  {'SB acc':>7}  {'SB n':>5}  {'Buy acc':>8}  {'Label'}")
print(f"  {'-'*58}")

for y, df in sorted(sig_dfs.items()):
    for vname in ["E", "L"]:
        col = f"sig_{vname}"
        res, (bn, ba) = accuracy_table(df, col)
        bl = res["BUY_LOW"]; sb = res["SLIGHT_BUY"]
        def fmt(v): return f"{v:.1%}" if not math.isnan(v) else "  n/a"
        label = "*OOS*" if y == OOS_YEAR else "train"
        print(f"  {y:<5}  {vname:>2}  {fmt(bl[1]):>7}  {bl[0]:>5}  "
              f"{fmt(sb[1]):>7}  {sb[0]:>5}  {fmt(ba):>8}  {label}")
    print()


# ── Step 9: Ablation ─────────────────────────────────────────────────────────

print(DIVIDER)
print("  ABLATION — CONTRIBUTION OF EACH COMPONENT (Version L)")
print(DIVIDER)

l_tr_acc, l_tr_n   = buy_acc(train_all_df, "sig_L")
l_oos_acc, l_oos_n = buy_acc(oos_all_df,   "sig_L") if not oos_all_df.empty else (float("nan"), 0)

def fmt(v): return f"{v:.1%}" if not math.isnan(v) else "  n/a"

print(f"\n  Full L model (ERA×0.60 + LOB×0.25 + BABIP×0.15): "
      f"train={fmt(l_tr_acc)} (n={l_tr_n}) | OOS={fmt(l_oos_acc)} (n={l_oos_n})\n")

print(f"  {'Ablation':<40}  {'Train acc':>10}  {'Δ train':>8}  {'OOS acc':>10}  {'Δ OOS':>8}  {'Verdict'}")
print(f"  {'-'*90}")

ablation_map = {
    "L_noLOB":   "Remove LOB  → ERA×0.80 + BABIP×0.20",
    "L_noBABIP": "Remove BABIP → ERA×0.706 + LOB×0.294",
    "L_noERA":   "Remove ERA_FIP → LOB×0.625 + BABIP×0.375",
}

for vname, label in ablation_map.items():
    col = f"sig_{vname}"
    tr_a, tr_n   = buy_acc(train_all_df, col)
    oos_a, oos_n = buy_acc(oos_all_df,   col) if not oos_all_df.empty else (float("nan"), 0)
    dt = tr_a  - l_tr_acc  if not math.isnan(tr_a)  and not math.isnan(l_tr_acc)  else float("nan")
    do = oos_a - l_oos_acc if not math.isnan(oos_a) and not math.isnan(l_oos_acc) else float("nan")
    if math.isnan(do):
        verdict = "n/a"
    elif do < -0.010:
        verdict = "CONTRIBUTING (removing hurts)"
    elif do > 0.010:
        verdict = "DRAG (removing helps)"
    else:
        verdict = "neutral"
    dt_s = f"{dt:>+7.1%}" if not math.isnan(dt) else "   n/a"
    do_s = f"{do:>+7.1%}" if not math.isnan(do) else "   n/a"
    print(f"  {label:<40}  {fmt(tr_a):>10}  {dt_s}  {fmt(oos_a):>10}  {do_s}  {verdict}")


# ── Step 10: Verdict switches — which pitchers changed signal? ────────────────

print()
print(DIVIDER)
print("  SIGNAL CHANGES: E → L (buy side only, OOS 2025)")
print(DIVIDER)

if oos_dfs:
    oos = oos_all_df.copy()
    changes = oos[(oos["sig_E"] != oos["sig_L"]) &
                  (oos["sig_E"].isin(["BUY_LOW","SLIGHT_BUY"]) |
                   oos["sig_L"].isin(["BUY_LOW","SLIGHT_BUY"]))]
    if len(changes) == 0:
        print("\n  No buy-side signal changes in OOS 2025.")
    else:
        print(f"\n  {'Name':<28}  {'E signal':<12}  {'L signal':<12}  "
              f"{'ERA':>5}  {'FIP':>5}  {'LOB_gap':>8}  {'xwOBA_gap':>10}  {'Outcome'}")
        print(f"  {'-'*90}")
        for _, r in changes.iterrows():
            name = str(r.get("pitcher_name", r["pitcher"]))[:27]
            xg   = r["xwoba_gap"] if "xwoba_gap" in r.index else float("nan")
            print(f"  {name:<28}  {r['sig_E']:<12}  {r['sig_L']:<12}  "
                  f"{r['era']:>5.2f}  {r['fip']:>5.2f}  {r['lob_gap']:>+8.3f}  "
                  f"{xg:>+10.3f}  {r['outcome']}")


# ── Step 11: Final verdict ────────────────────────────────────────────────────

print()
print(DIVIDER)
print("  FINAL VERDICT")
print(DIVIDER)

e_tr_acc, e_tr_n   = buy_acc(train_all_df, "sig_E")
e_oos_acc, e_oos_n = buy_acc(oos_all_df,   "sig_E") if not oos_all_df.empty else (float("nan"), 0)

bl_e_oos = accuracy_table(oos_all_df, "sig_E")[0]["BUY_LOW"][1] if not oos_all_df.empty else float("nan")
bl_l_oos = accuracy_table(oos_all_df, "sig_L")[0]["BUY_LOW"][1] if not oos_all_df.empty else float("nan")

dt_buy  = l_tr_acc  - e_tr_acc  if not (math.isnan(l_tr_acc)  or math.isnan(e_tr_acc))  else float("nan")
do_buy  = l_oos_acc - e_oos_acc if not (math.isnan(l_oos_acc) or math.isnan(e_oos_acc)) else float("nan")

print(f"\n  Version E (xwOBA_gap): train={fmt(e_tr_acc)} (n={e_tr_n})  "
      f"OOS={fmt(e_oos_acc)} (n={e_oos_n})  BL OOS={fmt(bl_e_oos)}")
print(f"  Version L (LOB_gap):   train={fmt(l_tr_acc)} (n={l_tr_n})  "
      f"OOS={fmt(l_oos_acc)} (n={l_oos_n})  BL OOS={fmt(bl_l_oos)}")
print()

dt_s = f"{dt_buy:+.1%}" if not math.isnan(dt_buy) else "n/a"
do_s = f"{do_buy:+.1%}" if not math.isnan(do_buy) else "n/a"
guard_pass = (not math.isnan(bl_l_oos)) and bl_l_oos >= OOS_GUARD

print(f"  Δ train = {dt_s}  |  Δ OOS = {do_s}  |  Guard = {'PASS' if guard_pass else 'FAIL'}")
print()

if not math.isnan(dt_buy) and not math.isnan(do_buy):
    if dt_buy >= 0.010 and do_buy >= 0.005 and guard_pass:
        print(f"  VERDICT: IMPROVEMENT — Train +{dt_buy:.1%}, OOS +{do_buy:.1%}, guard PASS.")
        print(f"  Recommend production adoption. Run validate_formulas.py 37/37 before wiring.")
    elif dt_buy >= 0.010 and not guard_pass:
        print(f"  VERDICT: OVERFIT — Train +{dt_buy:.1%} but BL OOS guard FAIL ({bl_l_oos:.1%} < {OOS_GUARD:.1%}).")
        print(f"  Do not adopt.")
    elif abs(dt_buy) < 0.005 and abs(do_buy) < 0.005 and guard_pass:
        print(f"  VERDICT: VERDICT-NEUTRAL — no meaningful change. Guard PASS.")
        print(f"  LOB_gap substitution is equivalent to xwOBA_gap in this context.")
    elif do_buy >= 0.005 and guard_pass:
        print(f"  VERDICT: MARGINAL IMPROVEMENT — OOS +{do_buy:.1%}, guard PASS.")
        print(f"  Below 1pp adoption threshold. Hold for further evidence.")
    else:
        print(f"  VERDICT: NO IMPROVEMENT — Train {dt_s}, OOS {do_s}.")
        if not guard_pass:
            print(f"  Guard FAIL ({bl_l_oos:.1%} < {OOS_GUARD:.1%}). Do not adopt.")
        else:
            print(f"  Guard PASS but no accuracy gain. Retain xwOBA_gap.")
