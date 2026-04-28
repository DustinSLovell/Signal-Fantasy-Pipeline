"""
backtest_pitcher_sb_gate.py
Diagnostic: Slight Buy confirmation gate for pitcher buy score.

Hypothesis: requiring a second independent signal before SB fires will improve
SB accuracy without hurting Buy Low or overall accuracy.

Version E = current production (no gate)
Version G_<combo> = gated SB: same as E but SB requires at least one
  confirmation signal to be present. Gated-out pitchers return NEUTRAL.

Confirmation gates (SB must pass at least one):
  A: lob_pct < career_lob - 0.050  (stranding fewer runners than career)
  B: hr_fb_rate - career_hr_fb > 0.030  (HR/FB above career = inflated ERA)
  C: babip > career_babip + 0.025  (BABIP above career = balls dropping in)
  D: xwoba_gap > 0.015  (contact quality confirms ERA mislead)

Tests all 15 OR-combinations of A/B/C/D.
Also tests whether applying same gate to Buy Low helps or hurts.

Guard rails:
  SB n >= 8 (train total)       — must have enough signal
  SB OOS acc >= 70%             — target SB accuracy
  Overall OOS acc >= 72.2%      — must not regress vs baseline
  BL OOS acc >= 75.0%           — must not hurt Buy Low
"""

import json, math, os, sys, numpy as np, pandas as pd
from itertools import combinations
from pathlib import Path

_SCRIPT_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, str(_SCRIPT_DIR / "archive"))
sys.path.insert(0, str(_SCRIPT_DIR))

from _pitcher_tier_audit import (
    per_start_stats, pitcher_stats, compute_volatility, load_or_fetch,
    CACHE_DIR, ERA_FLAT, MIN_APRIL_IP, MIN_OUTCOME_IP, career_babip_p,
)
from archive.backtest_pitcher_composite import (
    _add_composite_scores, _april_conf_scale, _classify_split_calibrated,
    _is_buy_qualified, compute_extra_stats, _load_full_parquet,
    _BIRTH_YEARS, _CAREER_IP,
    E_BUY_LOW_ERA_FLOOR, E_SLIGHT_BUY_ERA_FLOOR, E_ERA_FLOOR,
    E_MIN_BUY_IP, E_BUY_LOW_LS, E_SLIGHT_BUY_LS,
)

TRAIN_YEARS = [2022, 2023, 2024]
OOS_YEAR    = 2025
ALL_YEARS   = TRAIN_YEARS + [OOS_YEAR]
LG_LOB_PCT  = 0.724
LG_HRFB     = 0.115   # approximate MLB-average HR/FB rate

DIVIDER = "=" * 80

# Guard rails
GUARD_SB_N_TRAIN  = 8      # minimum SB train signals total
GUARD_SB_OOS      = 0.700  # SB OOS accuracy target
GUARD_OVERALL_OOS = 0.722  # must not drop below baseline
GUARD_BL_OOS      = 0.750  # must not hurt Buy Low


# ── Step 0: Career LOB% baselines ────────────────────────────────────────────

print("Precomputing career LOB% and HR/FB baselines from parquets...")

def _compute_lob_for_year(year: int) -> pd.Series:
    path = CACHE_DIR / f"pitcher_statcast_april_{year}.parquet"
    if not path.exists():
        return pd.Series(dtype=float)
    sc = _load_full_parquet(path)
    if sc.empty:
        return pd.Series(dtype=float)
    sc = sc.copy()
    sc["pitcher"] = pd.to_numeric(sc["pitcher"], errors="coerce")
    sc = sc.dropna(subset=["pitcher"]).copy()
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
    return (num / den).replace([np.inf, -np.inf], np.nan).clip(0, 1)

def _compute_hrfb_for_year(year: int) -> pd.Series:
    """HR/FB per pitcher: HR events / (fly_ball bb_type events incl HR)."""
    path = CACHE_DIR / f"pitcher_statcast_april_{year}.parquet"
    if not path.exists():
        return pd.Series(dtype=float)
    sc = _load_full_parquet(path)
    if sc.empty:
        return pd.Series(dtype=float)
    sc = sc.copy()
    sc["pitcher"] = pd.to_numeric(sc["pitcher"], errors="coerce")
    sc = sc.dropna(subset=["pitcher"]).copy()
    sc["pitcher"] = sc["pitcher"].astype(int)
    fb = sc[sc["bb_type"] == "fly_ball"].copy()
    if fb.empty:
        return pd.Series(dtype=float)
    g   = fb.groupby("pitcher")
    hr  = g["events"].apply(lambda s: (s == "home_run").sum())
    tot = g.size()
    rate = hr / tot
    return rate.replace([np.inf, -np.inf], np.nan).clip(0, 1)

lob_by_year  = {y: _compute_lob_for_year(y)  for y in ALL_YEARS}
hrfb_by_year = {y: _compute_hrfb_for_year(y) for y in ALL_YEARS}

for y in ALL_YEARS:
    print(f"  {y}: LOB%={lob_by_year[y].notna().sum()} | HR/FB={hrfb_by_year[y].notna().sum()} pitchers")


def career_baseline(pitcher_id: int, signal_year: int, by_year_dict: dict, fallback: float) -> float:
    records = [by_year_dict[y][pitcher_id]
               for y in ALL_YEARS if y < signal_year
               and pitcher_id in by_year_dict[y].index
               and pd.notna(by_year_dict[y][pitcher_id])]
    return float(np.mean(records)) if records else fallback


# ── Step 1: Load parquets ─────────────────────────────────────────────────────

def load_year(year: int):
    apr_c = CACHE_DIR / f"pitcher_statcast_april_{year}.parquet"
    out_c = CACHE_DIR / f"pitcher_statcast_mayjuly_{year}.parquet"
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
    r = load_year(y)
    if r:
        raw_data[y] = r
        print(f"  {y}: loaded")
    else:
        print(f"  {y}: MISSING — skipped")


# ── Step 2: Build signal DataFrames with gate features ───────────────────────

def build_sig(year: int):
    if year not in raw_data:
        return None
    apr_stats, out_stats, vol_df, extra = raw_data[year]
    sig = apr_stats.copy()
    sig["era_fip_gap"] = sig["era"] - sig["fip"]
    sig["career_ip_g"] = sig["pitcher"].map(_CAREER_IP).fillna(0.0)
    sig = _add_composite_scores(sig, extra, year)

    if "xwoba_allowed" in sig.columns:
        sig["xera_g"] = (3.7083 * sig["xwoba_allowed"] - 0.3305).round(3)
    else:
        sig["xera_g"] = float("nan")

    if not vol_df.empty and "volatility_flag" in vol_df.columns:
        sig = sig.merge(vol_df[["pitcher","volatility_flag"]], on="pitcher", how="left")
        sig["volatility_flag"] = sig["volatility_flag"].fillna(False)
    else:
        sig["volatility_flag"] = False

    # Career baselines per pitcher
    pid = sig["pitcher"].astype(int)
    sig["career_lob"]  = pid.apply(lambda p: career_baseline(p, year, lob_by_year,  LG_LOB_PCT))
    sig["career_hrfb"] = pid.apply(lambda p: career_baseline(p, year, hrfb_by_year, LG_HRFB))
    sig["career_babip"] = pid.map(career_babip_p).fillna(0.295)

    # Current values (from extra stats merged in by _add_composite_scores)
    sig["curr_lob"]    = sig["lob_pct"].fillna(LG_LOB_PCT)
    sig["curr_hrfb"]   = sig["hr_fb_rate"].fillna(LG_HRFB)
    sig["curr_babip"]  = sig["babip"].fillna(0.295)

    # Gate feature columns
    # A: current LOB% < career LOB% - 0.05  (stranding fewer runners, unlucky)
    sig["gate_A"] = sig["curr_lob"] < (sig["career_lob"] - 0.050)
    # B: HR/FB rate above career by > 0.03
    sig["gate_B"] = (sig["curr_hrfb"] - sig["career_hrfb"]) > 0.030
    # C: BABIP above career by > 0.025
    sig["gate_C"] = (sig["curr_babip"] - sig["career_babip"]) > 0.025
    # D: xwOBA_gap > 0.015
    xwoba_g = sig["xwoba_gap"].fillna(0.0) if "xwoba_gap" in sig.columns else pd.Series(0.0, index=sig.index)
    sig["gate_D"] = xwoba_g > 0.015

    # Merge outcome
    merged = sig.merge(
        out_stats[["pitcher","era","ip"]].rename(
            columns={"era":"outcome_era","ip":"outcome_ip"}),
        on="pitcher", how="inner"
    )
    merged["era_change"] = merged["outcome_era"] - merged["era"]
    merged["outcome"] = np.where(
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
        print(f"  {y}: {len(df)} pitchers")


# ── Step 3: Gate fire rate summary ────────────────────────────────────────────

train_dfs = [sig_dfs[y] for y in TRAIN_YEARS if y in sig_dfs]
oos_dfs   = [sig_dfs[OOS_YEAR]] if OOS_YEAR in sig_dfs else []
train_all = pd.concat(train_dfs, ignore_index=True)

print()
print(DIVIDER)
print("  GATE FIRE RATES (training buy signals = current SB pitchers, 2022-2024)")
print(DIVIDER)

# Get training SB pitchers (Version E baseline signals)
sb_train = train_all[train_all["_buy_d_raw"].notna()].copy()
# Re-run E classify inline to identify actual SB rows
def _e_classify_row(row) -> str:
    bs  = float(row.get("_buy_d_raw") or 0.0)
    ss  = float(row.get("_sell_d_raw") or 0.0)
    ip  = float(row.get("ip") or 0.0)
    era = float(row.get("era") or 0.0)
    fip_r = float(row.get("fip", float("nan")))
    if bs > 0 and ss >= 0:
        dominant = bs >= 1.50
        if ip < E_MIN_BUY_IP and not dominant:
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
        xera_f = float(xera_r) if xera_r is not None and not pd.isna(xera_r) else float("nan")
        if (not dominant and not math.isnan(xera_f) and not pd.isna(fip_r)
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

train_all["sig_E"] = train_all.apply(_e_classify_row, axis=1)
sb_e_train = train_all[train_all["sig_E"] == "SLIGHT_BUY"]
bl_e_train = train_all[train_all["sig_E"] == "BUY_LOW"]

print(f"\n  Training SB pitchers (n={len(sb_e_train)}):")
for gate in ["A", "B", "C", "D"]:
    col = f"gate_{gate}"
    n_fire = sb_e_train[col].sum()
    pct    = n_fire / len(sb_e_train) if len(sb_e_train) > 0 else 0
    correct_all = sb_e_train["outcome"].isin(["IMPROVED"]).mean()
    correct_gate = sb_e_train[sb_e_train[col]]["outcome"].isin(["IMPROVED"]).mean() if n_fire > 0 else float("nan")
    correct_nogat = sb_e_train[~sb_e_train[col]]["outcome"].isin(["IMPROVED"]).mean() if (len(sb_e_train)-n_fire) > 0 else float("nan")
    print(f"  Gate {gate}: fires on {n_fire}/{len(sb_e_train)} ({pct:.0%}) | "
          f"acc when fires={correct_gate:.1%} | acc when silent={correct_nogat:.1%} | overall={correct_all:.1%}")

print(f"\n  Training BL pitchers (n={len(bl_e_train)}):")
for gate in ["A", "B", "C", "D"]:
    col = f"gate_{gate}"
    n_fire = bl_e_train[col].sum()
    pct    = n_fire / len(bl_e_train) if len(bl_e_train) > 0 else 0
    print(f"  Gate {gate}: fires on {n_fire}/{len(bl_e_train)} ({pct:.0%})")


# ── Step 4: Gated classifier ───────────────────────────────────────────────────

def _classify_gated(row, gate_cols: list[str], gate_buy_low: bool = False) -> str:
    """Version E with optional SB (and optionally BL) confirmation gate."""
    bs  = float(row.get("_buy_d_raw") or 0.0)
    ss  = float(row.get("_sell_d_raw") or 0.0)
    ip  = float(row.get("ip") or 0.0)
    era = float(row.get("era") or 0.0)
    fip_r = float(row.get("fip", float("nan")))

    if bs > 0 and ss >= 0:
        dominant = bs >= 1.50
        if ip < E_MIN_BUY_IP and not dominant:
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
        xera_f = float(xera_r) if xera_r is not None and not pd.isna(xera_r) else float("nan")
        if (not dominant and not math.isnan(xera_f) and not pd.isna(fip_r)
                and abs(fip_r - xera_f) > 1.50 and xera_f > 4.50
                and float(row.get("era_fip_gap", 0.0)) < 2.50):
            return "NEUTRAL"

        scaled = bs * _april_conf_scale(ip)
        gate_passes = any(bool(row.get(c, False)) for c in gate_cols)

        if scaled >= E_BUY_LOW_LS:
            if era < E_BUY_LOW_ERA_FLOOR:
                return "NEUTRAL"
            if gate_buy_low and not gate_passes:
                return "NEUTRAL"
            return "BUY_LOW"
        if scaled >= E_SLIGHT_BUY_LS:
            if era < E_SLIGHT_BUY_ERA_FLOOR:
                return "NEUTRAL"
            if not gate_passes:
                return "NEUTRAL"
            return "SLIGHT_BUY"

    return _classify_split_calibrated(row["composite_d"])


# ── Step 5: Build all 15 OR-combinations ─────────────────────────────────────

GATES = ["A", "B", "C", "D"]
combos = []
for r in range(1, 5):
    for combo in combinations(GATES, r):
        combos.append(combo)

version_defs = {"E": ([], False)}   # baseline
for combo in combos:
    label = "OR".join(combo)
    cols  = [f"gate_{g}" for g in combo]
    version_defs[label] = (cols, False)

# Apply all versions to all years
print()
print(DIVIDER)
print("  Classifying all versions × all years...")
print(DIVIDER)
for y, df in sig_dfs.items():
    for vname, (cols, gate_bl) in version_defs.items():
        if vname == "E":
            df[f"sig_{vname}"] = df.apply(_e_classify_row, axis=1)
        else:
            df[f"sig_{vname}"] = df.apply(
                lambda row, c=cols, g=gate_bl: _classify_gated(row, c, g), axis=1)
    print(f"  {y}: {len(version_defs)} versions done")


# ── Step 6: Accuracy helpers ──────────────────────────────────────────────────

def tier_acc(df: pd.DataFrame, sig_col: str, tier: str):
    sub = df[df[sig_col] == tier]
    if len(sub) == 0:
        return 0, float("nan")
    good = {"BUY_LOW","SLIGHT_BUY"}
    correct = sub["outcome"].isin(["IMPROVED"] if tier in good else ["DECLINED","FLAT"]).mean()
    return len(sub), correct

def buy_acc(df: pd.DataFrame, sig_col: str):
    buy = df[df[sig_col].isin(["BUY_LOW","SLIGHT_BUY"])]
    return (len(buy),
            buy["outcome"].isin(["IMPROVED"]).mean() if len(buy) > 0 else float("nan"))

def fmt(v): return f"{v:.1%}" if not math.isnan(v) else "  n/a"


# ── Step 7: Full results table ────────────────────────────────────────────────

train_all_df = pd.concat([sig_dfs[y] for y in TRAIN_YEARS if y in sig_dfs], ignore_index=True)
oos_all_df   = pd.concat(oos_dfs, ignore_index=True) if oos_dfs else pd.DataFrame()

print()
print(DIVIDER)
print("  FULL RESULTS TABLE (all 15 gate combinations)")
print(DIVIDER)
print()
hdr = (f"  {'Version':<16}  {'SBtr':>5} {'SBacc_tr':>9}  {'BL_tr':>5} {'BLacc_tr':>9}  "
       f"{'Buy_tr':>5} {'All_tr':>7}  |  "
       f"{'SBoos':>5} {'SBacc_oos':>10}  {'BL_oos':>5} {'BLacc_oos':>10}  "
       f"{'Buy_oos':>6} {'All_oos':>7}  {'Flags'}")
print(hdr)
print(f"  {'-'*150}")

results_list = []

for vname, (cols, gate_bl) in version_defs.items():
    col = f"sig_{vname}"

    # Train
    sb_tr_n, sb_tr_a   = tier_acc(train_all_df, col, "SLIGHT_BUY")
    bl_tr_n, bl_tr_a   = tier_acc(train_all_df, col, "BUY_LOW")
    buy_tr_n, buy_tr_a = buy_acc(train_all_df, col)

    # OOS
    if not oos_all_df.empty:
        sb_os_n, sb_os_a   = tier_acc(oos_all_df, col, "SLIGHT_BUY")
        bl_os_n, bl_os_a   = tier_acc(oos_all_df, col, "BUY_LOW")
        buy_os_n, buy_os_a = buy_acc(oos_all_df, col)
    else:
        sb_os_n, sb_os_a   = 0, float("nan")
        bl_os_n, bl_os_a   = 0, float("nan")
        buy_os_n, buy_os_a = 0, float("nan")

    # Guard checks
    flags = []
    if sb_tr_n < GUARD_SB_N_TRAIN:   flags.append(f"SBn<{GUARD_SB_N_TRAIN}")
    if not math.isnan(sb_os_a) and sb_os_a < GUARD_SB_OOS:  flags.append(f"SBoos<{GUARD_SB_OOS:.0%}")
    if not math.isnan(buy_os_a) and buy_os_a < GUARD_OVERALL_OOS: flags.append("OOS<base")
    if not math.isnan(bl_os_a) and bl_os_a < GUARD_BL_OOS:   flags.append("BL<75%")
    flag_str = " | ".join(flags) if flags else "PASS"

    row = dict(
        vname=vname, cols=cols,
        sb_tr_n=sb_tr_n, sb_tr_a=sb_tr_a,
        bl_tr_n=bl_tr_n, bl_tr_a=bl_tr_a,
        buy_tr_n=buy_tr_n, buy_tr_a=buy_tr_a,
        sb_os_n=sb_os_n, sb_os_a=sb_os_a,
        bl_os_n=bl_os_n, bl_os_a=bl_os_a,
        buy_os_n=buy_os_n, buy_os_a=buy_os_a,
        flags=flag_str, passes=(flag_str == "PASS"),
    )
    results_list.append(row)

    print(f"  {vname:<16}  {sb_tr_n:>5} {fmt(sb_tr_a):>9}  {bl_tr_n:>5} {fmt(bl_tr_a):>9}  "
          f"{buy_tr_n:>5} {fmt(buy_tr_a):>7}  |  "
          f"{sb_os_n:>5} {fmt(sb_os_a):>10}  {bl_os_n:>5} {fmt(bl_os_a):>10}  "
          f"{buy_os_n:>6} {fmt(buy_os_a):>7}  {flag_str}")

results_df = pd.DataFrame(results_list)


# ── Step 8: Top combinations by SB OOS accuracy ──────────────────────────────

print()
print(DIVIDER)
print("  TOP 3 BY SLIGHT BUY OOS ACCURACY (all guards considered)")
print(DIVIDER)
top3 = (results_df[results_df["sb_os_n"] > 0]
        .sort_values("sb_os_a", ascending=False)
        .head(3))

print()
print(f"  {'Rank':<5}  {'Version':<16}  {'SB OOS':>8}  {'SB n OOS':>9}  "
      f"{'Overall OOS':>12}  {'BL OOS':>8}  {'Flags'}")
print(f"  {'-'*80}")
for i, (_, r) in enumerate(top3.iterrows(), 1):
    print(f"  {i:<5}  {r['vname']:<16}  {fmt(r['sb_os_a']):>8}  {r['sb_os_n']:>9}  "
          f"{fmt(r['buy_os_a']):>12}  {fmt(r['bl_os_a']):>8}  {r['flags']}")


# ── Step 9: Combinations that pass ALL guards ─────────────────────────────────

print()
print(DIVIDER)
print("  COMBINATIONS THAT PASS ALL GUARDS")
print(DIVIDER)
passing = results_df[results_df["passes"] & (results_df["vname"] != "E")]
if len(passing) == 0:
    print("\n  None — no combination passes all four guard rails.")
else:
    print(f"\n  {len(passing)} combination(s) pass all guards:\n")
    for _, r in passing.sort_values("sb_os_a", ascending=False).iterrows():
        print(f"  {r['vname']:<16}  SB OOS={fmt(r['sb_os_a'])} (n={r['sb_os_n']})  "
              f"Overall OOS={fmt(r['buy_os_a'])}  BL OOS={fmt(r['bl_os_a'])}")

# Which combos improve overall OOS vs baseline?
print()
print(DIVIDER)
print("  COMBINATIONS THAT IMPROVE OVERALL OOS vs BASELINE (72.2%)")
print(DIVIDER)
baseline_oos = results_df[results_df["vname"] == "E"]["buy_os_a"].iloc[0]
improvers = results_df[(results_df["buy_os_a"] > baseline_oos) & (results_df["vname"] != "E")]
if len(improvers) == 0:
    print(f"\n  None — no gated combination improves overall OOS above {baseline_oos:.1%}.")
else:
    for _, r in improvers.sort_values("buy_os_a", ascending=False).iterrows():
        delta = r["buy_os_a"] - baseline_oos
        print(f"  {r['vname']:<16}  Overall OOS={fmt(r['buy_os_a'])} ({delta:+.1%})  "
              f"SB OOS={fmt(r['sb_os_a'])}  BL OOS={fmt(r['bl_os_a'])}  {r['flags']}")


# ── Step 10: Buy Low gate test (best passing combo applied to BL too) ─────────

print()
print(DIVIDER)
print("  BUY LOW GATE TEST — apply same confirmation to BL (best combinations)")
print(DIVIDER)

# Pick best passing combo, or best overall if none pass
best_combos = (passing.sort_values("sb_os_a", ascending=False).head(3)
               if len(passing) > 0
               else results_df[results_df["vname"] != "E"].sort_values("sb_os_a", ascending=False).head(3))

print()
print(f"  {'Version (BL-gated)':<22}  {'SBtr':>5} {'SBacc_tr':>9}  {'BL_tr':>5} {'BLacc_tr':>9}  "
      f"{'All_tr':>7}  |  "
      f"{'SBoos':>5} {'SBacc_oos':>10}  {'BL_oos':>5} {'BLacc_oos':>10}  "
      f"{'All_oos':>7}  {'Note'}")
print(f"  {'-'*140}")

for _, r in best_combos.iterrows():
    cols     = r["cols"]
    vname_bl = r["vname"] + "_BLgated"

    for y, df in sig_dfs.items():
        df[f"sig_{vname_bl}"] = df.apply(
            lambda row, c=cols: _classify_gated(row, c, gate_buy_low=True), axis=1)

    tr_df_bl = pd.concat([sig_dfs[y] for y in TRAIN_YEARS if y in sig_dfs], ignore_index=True)
    os_df_bl = pd.concat([sig_dfs[OOS_YEAR]], ignore_index=True) if OOS_YEAR in sig_dfs else pd.DataFrame()
    sb_tr_n, sb_tr_a   = tier_acc(tr_df_bl, f"sig_{vname_bl}", "SLIGHT_BUY")
    bl_tr_n, bl_tr_a   = tier_acc(tr_df_bl, f"sig_{vname_bl}", "BUY_LOW")
    buy_tr_n, buy_tr_a = buy_acc(tr_df_bl,  f"sig_{vname_bl}")
    if not os_df_bl.empty:
        sb_os_n, sb_os_a   = tier_acc(os_df_bl, f"sig_{vname_bl}", "SLIGHT_BUY")
        bl_os_n, bl_os_a   = tier_acc(os_df_bl, f"sig_{vname_bl}", "BUY_LOW")
        buy_os_n, buy_os_a = buy_acc(os_df_bl,  f"sig_{vname_bl}")
    else:
        sb_os_n=sb_os_a=bl_os_n=bl_os_a=buy_os_n=buy_os_a = float("nan")

    note = "PASS" if (not math.isnan(bl_os_a) and bl_os_a >= GUARD_BL_OOS and
                      not math.isnan(buy_os_a) and buy_os_a >= GUARD_OVERALL_OOS) else "FAIL"

    print(f"  {vname_bl:<22}  {sb_tr_n:>5} {fmt(sb_tr_a):>9}  {bl_tr_n:>5} {fmt(bl_tr_a):>9}  "
          f"{fmt(buy_tr_a):>7}  |  "
          f"{sb_os_n:>5} {fmt(sb_os_a):>10}  {bl_os_n:>5} {fmt(bl_os_a):>10}  "
          f"{fmt(buy_os_a):>7}  {note}")


# ── Step 11: Per-year breakdown for best combo ────────────────────────────────

print()
print(DIVIDER)
print("  PER-YEAR BREAKDOWN: E vs best combination")
print(DIVIDER)

# Best = highest SB OOS that passes overall OOS guard, else highest SB OOS overall
candidates = (results_df[(results_df["vname"] != "E") &
                          (~results_df["buy_os_a"].isna()) &
                          (results_df["buy_os_a"] >= GUARD_OVERALL_OOS)]
              .sort_values("sb_os_a", ascending=False))
if len(candidates) == 0:
    candidates = results_df[results_df["vname"] != "E"].sort_values("sb_os_a", ascending=False)

best_vname = candidates.iloc[0]["vname"] if len(candidates) > 0 else None

print()
if best_vname:
    print(f"  Showing E vs {best_vname} (best SB OOS that meets overall OOS guard)\n")
    print(f"  {'Year':<5}  {'V':>12}  {'BL acc':>7}  {'BL n':>5}  {'SB acc':>7}  {'SB n':>5}  {'Buy acc':>8}  Label")
    print(f"  {'-'*65}")
    for y, df in sorted(sig_dfs.items()):
        for vn in ["E", best_vname]:
            col = f"sig_{vn}"
            bn, ba = buy_acc(df, col)
            bl_n, bl_a  = tier_acc(df, col, "BUY_LOW")
            sb_n, sb_a  = tier_acc(df, col, "SLIGHT_BUY")
            label = "*OOS*" if y == OOS_YEAR else "train"
            print(f"  {y:<5}  {vn:>12}  {fmt(bl_a):>7}  {bl_n:>5}  "
                  f"{fmt(sb_a):>7}  {sb_n:>5}  {fmt(ba):>8}  {label}")
        print()


# ── Step 12: Verdict ──────────────────────────────────────────────────────────

print()
print(DIVIDER)
print("  VERDICT")
print(DIVIDER)
print()

e_row = results_df[results_df["vname"] == "E"].iloc[0]
print(f"  Baseline E: SB OOS={fmt(e_row['sb_os_a'])} (n={e_row['sb_os_n']})  "
      f"Overall OOS={fmt(e_row['buy_os_a'])} (n={e_row['buy_os_n']})  "
      f"BL OOS={fmt(e_row['bl_os_a'])} (n={e_row['bl_os_n']})")
print()

if len(passing) > 0:
    best = passing.sort_values("sb_os_a", ascending=False).iloc[0]
    print(f"  RECOMMENDED GATE: {best['vname']}")
    print(f"    SB OOS:       {fmt(best['sb_os_a'])} (n={best['sb_os_n']})  "
          f"[baseline: {fmt(e_row['sb_os_a'])}]")
    print(f"    Overall OOS:  {fmt(best['buy_os_a'])}  [baseline: {fmt(e_row['buy_os_a'])}]")
    print(f"    BL OOS:       {fmt(best['bl_os_a'])}  [baseline: {fmt(e_row['bl_os_a'])}]")
    print(f"    All guards:   PASS")
else:
    best_sb = results_df[results_df["vname"] != "E"].sort_values("sb_os_a", ascending=False).iloc[0]
    print(f"  NO COMBINATION PASSES ALL GUARDS.")
    print(f"  Best SB OOS: {best_sb['vname']} = {fmt(best_sb['sb_os_a'])} but {best_sb['flags']}")
    print(f"  Recommendation: retain current architecture (no gate).")
print()
print(DIVIDER)
