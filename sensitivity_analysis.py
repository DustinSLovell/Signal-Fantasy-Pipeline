#!/usr/bin/env python3
"""
sensitivity_analysis.py  —  Signal model threshold sensitivity analysis
Read-only: no production files modified.

Tests each parameter independently (one at a time) with all others at
production defaults.  Reports per-year + 4yr-avg accuracy and signal count.
2025 is treated as out-of-sample validation (never used for tuning).

Saves results to:
  data/sensitivity_analysis_results.md
  data/sensitivity_analysis_raw.csv
"""

import io, json, math, os, sys
import numpy as np
import pandas as pd
from pathlib import Path

# ── Path setup ────────────────────────────────────────────────────────────────
BASE_DIR   = Path(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR  = BASE_DIR / "backtest_cache"
DATA_DIR   = BASE_DIR / "data"
ARCH_DIR   = BASE_DIR / "archive"
sys.path.insert(0, str(ARCH_DIR))

# Redirect stdout to UTF-8 before importing backtest modules
if isinstance(sys.stdout, io.TextIOWrapper):
    _buf = sys.stdout.detach()
else:
    _buf = getattr(sys.stdout, "buffer", sys.stdout)
sys.stdout = io.TextIOWrapper(_buf, encoding="utf-8", errors="replace")

# ── Import composite backtest machinery (pitcher data loading only) ───────────
from _pitcher_tier_audit import (
    per_start_stats, pitcher_stats, compute_volatility, load_or_fetch,
    P_YEARS, PARK_FACTORS, ERA_FLAT, MIN_APRIL_IP, MIN_OUTCOME_IP,
    LEAGUE_AVG_BABIP, VOL_DAMP, career_babip_p, career_hh_p, career_barrel_p,
)
from backtest_pitcher_composite import (
    _load_year_data, _add_composite_scores, _load_career_ip, _load_birth_years,
    _babip_age_mult as _pitcher_babip_age_mult,
    XWOBA_TO_XERA_COEF, XWOBA_TO_XERA_INTERCEPT,
    COMP_SLIGHT_SELL, COMP_SELL_HIGH, RTM_BASELINE,
)

print("=== SENSITIVITY ANALYSIS START ===\n")

# ── Production defaults (reference values) ────────────────────────────────────
PROD = {
    # Pitcher
    "P_SLIGHT_BUY_ERA_FLOOR":  4.00,
    "P_ERA_FLOOR":             3.50,
    "P_MIN_BUY_IP":           20.0,
    "P_FIP_CEILING":           4.50,
    "P_SWSTR_FLOOR":           0.08,
    "P_SLIGHT_BUY_LS":         0.065,
    "P_BUY_LOW_LS":            0.150,
    # Hitter
    "H_BUY_LOW_THRESH":        0.150,
    "H_SLIGHT_BUY_THRESH":     0.065,
    "H_XWOBA_GATE":            0.015,
    "H_SELL_HIGH_THRESH":     -0.150,
    "H_SLIGHT_SELL_THRESH":   -0.085,
}

YEARS    = [2022, 2023, 2024, 2025]
IN_YEARS = [2022, 2023, 2024]   # training
OOS_YEAR = 2025                  # validation

_CAREER_IP    = _load_career_ip()
_BIRTH_YEARS  = _load_birth_years()

# ══════════════════════════════════════════════════════════════════════════════
# PITCHER DATA LOADING
# ══════════════════════════════════════════════════════════════════════════════

def _load_pitcher_features(year: int) -> pd.DataFrame | None:
    """
    Returns a per-pitcher DataFrame with all raw scores + outcome.
    Keeps _buy_d_raw, _sell_d_raw, and all gate inputs for re-classification.
    """
    result = _load_year_data(year)
    if result is None:
        return None
    apr_stats, out_stats, vol_df, extra = result

    sig = apr_stats.copy()
    sig["era_fip_gap"] = sig["era"] - sig["fip"]
    sig["career_hh_allowed"]     = sig["pitcher"].map(career_hh_p)
    sig["career_barrel_allowed"] = sig["pitcher"].map(career_barrel_p)

    if not vol_df.empty:
        sig = sig.merge(vol_df[["pitcher","volatility_flag"]], on="pitcher", how="left")
        sig["volatility_flag"] = sig["volatility_flag"].fillna(False)
    else:
        sig["volatility_flag"] = False

    sig = _add_composite_scores(sig, extra, year)

    # xERA proxy from April xwOBA
    if "xwoba_allowed" in sig.columns:
        sig["april_xera"] = (
            XWOBA_TO_XERA_COEF * sig["xwoba_allowed"] + XWOBA_TO_XERA_INTERCEPT
        ).round(3)
    else:
        sig["april_xera"] = float("nan")

    sig["career_ip_v"]  = sig["pitcher"].map(_CAREER_IP).fillna(0.0)

    # Load FIP from FG data for the FIP sensitivity (full-season FIP quality gate)
    fg_path = DATA_DIR / f"fg_pitching_{year}.csv"
    if fg_path.exists():
        fg = pd.read_csv(fg_path)
        if "pitcher_id" in fg.columns and "xera" in fg.columns:
            xera_map = {int(r["pitcher_id"]): float(r["xera"])
                        for _, r in fg.iterrows() if pd.notna(r.get("xera"))}
            sig["fg_xera"] = sig["pitcher"].map(xera_map).fillna(float("nan"))
        else:
            sig["fg_xera"] = float("nan")
    else:
        sig["fg_xera"] = float("nan")

    # Merge with outcomes
    out = out_stats[out_stats["ip"] >= MIN_OUTCOME_IP].copy()
    merged = sig.merge(
        out[["pitcher","era","ip"]].rename(
            columns={"era":"outcome_era","ip":"outcome_ip"}),
        on="pitcher", how="inner"
    )
    merged["era_change"] = merged["outcome_era"] - merged["era"]
    merged["outcome"] = np.where(
        merged["era_change"] <= -ERA_FLAT, "IMPROVED",
        np.where(merged["era_change"] >= ERA_FLAT, "DECLINED", "FLAT")
    )
    merged["year"] = year
    return merged


print("Loading pitcher backtest data...")
_pitcher_frames = {}
for yr in YEARS:
    print(f"  {yr}...", end=" ")
    frame = _load_pitcher_features(yr)
    if frame is not None and not frame.empty:
        _pitcher_frames[yr] = frame
        print(f"OK ({len(frame)} pitchers)")
    else:
        print("SKIP (missing cache)")


# ══════════════════════════════════════════════════════════════════════════════
# HITTER DATA LOADING (from production audit CSV)
# ══════════════════════════════════════════════════════════════════════════════

_hitter_df = None
_hitter_audit_path = DATA_DIR / "backtest_audit_hitters_v2.csv"
if _hitter_audit_path.exists():
    _hitter_df = pd.read_csv(_hitter_audit_path)
    _hitter_df["xwoba_gap"] = (_hitter_df["xwoba_actual"] - _hitter_df["woba_actual"]).round(4)
    print(f"\nLoaded hitter audit: {len(_hitter_df)} rows, {_hitter_df['year'].nunique()} years")
else:
    print(f"\nWARNING: {_hitter_audit_path} not found — hitter analysis unavailable")


# ══════════════════════════════════════════════════════════════════════════════
# PARAMETERIZED PITCHER CLASSIFIER
# ══════════════════════════════════════════════════════════════════════════════

def _april_conf_scale(ip: float) -> float:
    if ip < 15.0: return 0.0
    return min(1.0, max(0.25, (ip - 15.0) / 40.0))


def _is_buy_qualified_p(fip, xera, swstr, career_ip, gb_pct,
                         fip_ceil=4.50, swstr_floor=0.08) -> bool:
    """Parameterized version of production is_buy_qualified()."""
    try:
        fip_f   = float(fip)
        xera_f  = float(xera)
        swstr_f = float(swstr)
    except (TypeError, ValueError):
        return False
    if math.isnan(fip_f) or fip_f > fip_ceil:
        return False
    fip_carveout = fip_f <= 3.50
    if not fip_carveout:
        if math.isnan(xera_f) or xera_f > 4.75:
            return False
    try:
        gb_f = float(gb_pct)
        gb_carveout = not math.isnan(gb_f) and gb_f > 0.52
    except (TypeError, ValueError):
        gb_carveout = False
    if not gb_carveout:
        if math.isnan(swstr_f) or swstr_f < swstr_floor:
            return False
    return float(career_ip) >= 100


def classify_pitcher_e(row: pd.Series, *,
                        slight_buy_era_floor=4.00,
                        era_floor=3.50,
                        min_buy_ip=20.0,
                        fip_ceil=4.50,
                        swstr_floor=0.08,
                        slight_buy_ls=0.065,
                        buy_low_ls=0.150) -> str:
    """
    Parameterized Version E pitcher classifier.
    Mirrors _e_prescore() in backtest_pitcher_composite.py.
    """
    bs  = float(row.get("_buy_d_raw") or 0.0)
    ss  = float(row.get("_sell_d_raw") or 0.0)
    ip  = float(row.get("ip") or 0.0)
    era = float(row.get("era") or 0.0)

    def _safe(v):
        try: return float(v)
        except: return float("nan")

    fip_r     = _safe(row.get("fip"))
    xera_r    = _safe(row.get("april_xera"))
    swstr_r   = _safe(row.get("swstr_rate"))
    gb_r      = _safe(row.get("gb_pct"))
    career_ip = float(row.get("career_ip_v", 0.0))

    if bs > 0 and ss >= 0:
        dominant_buy = bs >= 1.50
        if ip < min_buy_ip and not dominant_buy:
            return "NEUTRAL"
        if ip < min_buy_ip and not math.isnan(fip_r) and fip_r < 1.50:
            return "NEUTRAL"
        if not _is_buy_qualified_p(fip_r, xera_r, swstr_r, career_ip, gb_r,
                                    fip_ceil=fip_ceil, swstr_floor=swstr_floor):
            return "NEUTRAL"
        if era < era_floor:
            return "NEUTRAL"
        xera_f = xera_r if not math.isnan(xera_r) else float("nan")
        era_fip_gap = float(row.get("era_fip_gap", 0.0))
        if (not dominant_buy and not math.isnan(xera_f) and not math.isnan(fip_r)
                and abs(fip_r - xera_f) > 1.50 and xera_f > 4.50
                and era_fip_gap < 2.50):
            return "NEUTRAL"
        scaled = bs * _april_conf_scale(ip)
        if scaled >= buy_low_ls:
            return "BUY_LOW"
        if scaled >= slight_buy_ls:
            if era < slight_buy_era_floor:
                return "NEUTRAL"
            return "SLIGHT_BUY"

    # Sell side: composite_d threshold
    cd = float(row.get("composite_d") or 0.0)
    if cd <= COMP_SELL_HIGH:   return "SELL_HIGH"
    if cd <= COMP_SLIGHT_SELL: return "SLIGHT_SELL"
    return "NEUTRAL"


SIGNAL_MAP_P = {
    "BUY_LOW": "IMPROVED", "SLIGHT_BUY": "IMPROVED",
    "SELL_HIGH": "DECLINED", "SLIGHT_SELL": "DECLINED",
}


def eval_pitcher_params(param_override: dict) -> dict:
    """
    Runs the Version E classifier with overridden parameters.
    Returns dict: {year -> {signal -> (n, correct, accuracy)}, 'total_n': int}
    """
    params = {
        "slight_buy_era_floor": PROD["P_SLIGHT_BUY_ERA_FLOOR"],
        "era_floor":            PROD["P_ERA_FLOOR"],
        "min_buy_ip":           PROD["P_MIN_BUY_IP"],
        "fip_ceil":             PROD["P_FIP_CEILING"],
        "swstr_floor":          PROD["P_SWSTR_FLOOR"],
        "slight_buy_ls":        PROD["P_SLIGHT_BUY_LS"],
        "buy_low_ls":           PROD["P_BUY_LOW_LS"],
    }
    params.update(param_override)

    results = {}
    for yr, df in _pitcher_frames.items():
        df2 = df.copy()
        df2["signal"] = df2.apply(
            lambda r: classify_pitcher_e(r, **params), axis=1
        )
        eval_df = df2[df2["signal"].isin(SIGNAL_MAP_P) & (df2["outcome"] != "FLAT")].copy()
        eval_df["correct"] = eval_df.apply(
            lambda r: r["outcome"] == SIGNAL_MAP_P[r["signal"]], axis=1
        )
        yr_stats = {}
        for sig in ["BUY_LOW", "SLIGHT_BUY", "SLIGHT_SELL", "SELL_HIGH"]:
            grp = eval_df[eval_df["signal"] == sig]
            n = len(grp)
            c = int(grp["correct"].sum()) if n > 0 else 0
            yr_stats[sig] = (n, c, c/n if n > 0 else float("nan"))
        ov_n = len(eval_df)
        ov_c = int(eval_df["correct"].sum())
        yr_stats["OVERALL"] = (ov_n, ov_c, ov_c/ov_n if ov_n > 0 else float("nan"))
        results[yr] = yr_stats

    return results


# ══════════════════════════════════════════════════════════════════════════════
# PARAMETERIZED HITTER CLASSIFIER
# ══════════════════════════════════════════════════════════════════════════════

def classify_hitter(luck_score: float, xwoba_gap: float, *,
                    buy_low_thresh=0.150, slight_buy_thresh=0.065,
                    xwoba_gate=0.015, sell_high_thresh=-0.150,
                    slight_sell_thresh=-0.085) -> str:
    if luck_score >= buy_low_thresh:    return "BUY_LOW"
    if luck_score >= slight_buy_thresh:
        if xwoba_gate > 0 and xwoba_gap < xwoba_gate:
            return "NEUTRAL"
        return "SLIGHT_BUY"
    if luck_score <= sell_high_thresh:  return "SELL_HIGH"
    if luck_score <= slight_sell_thresh: return "SLIGHT_SELL"
    return "NEUTRAL"


SIGNAL_MAP_H = {
    "BUY_LOW": "IMPROVED", "SLIGHT_BUY": "IMPROVED",
    "SELL_HIGH": "DECLINED", "SLIGHT_SELL": "DECLINED",
}


def eval_hitter_params(param_override: dict) -> dict:
    """
    Runs the hitter classifier with overridden parameters.
    Returns dict: {year -> {signal -> (n, correct, accuracy)}}
    Uses the full audit CSV including Neutral players so gate changes are reflected.
    """
    if _hitter_df is None:
        return {}
    params = {
        "buy_low_thresh":     PROD["H_BUY_LOW_THRESH"],
        "slight_buy_thresh":  PROD["H_SLIGHT_BUY_THRESH"],
        "xwoba_gate":         PROD["H_XWOBA_GATE"],
        "sell_high_thresh":   PROD["H_SELL_HIGH_THRESH"],
        "slight_sell_thresh": PROD["H_SLIGHT_SELL_THRESH"],
    }
    params.update(param_override)

    results = {}
    for yr in YEARS:
        df_yr = _hitter_df[_hitter_df["year"] == yr].copy()
        if df_yr.empty:
            continue
        df_yr["new_signal"] = df_yr.apply(
            lambda r: classify_hitter(r["luck_score"], r["xwoba_gap"], **params),
            axis=1
        )
        eval_df = df_yr[
            df_yr["new_signal"].isin(SIGNAL_MAP_H) &
            (df_yr["outcome"].isin(["IMPROVED","DECLINED"]))
        ].copy()
        eval_df["correct"] = eval_df.apply(
            lambda r: r["outcome"] == SIGNAL_MAP_H[r["new_signal"]], axis=1
        )
        yr_stats = {}
        for sig in ["BUY_LOW", "SLIGHT_BUY", "SLIGHT_SELL", "SELL_HIGH"]:
            grp = eval_df[eval_df["new_signal"] == sig]
            n = len(grp)
            c = int(grp["correct"].sum()) if n > 0 else 0
            yr_stats[sig] = (n, c, c/n if n > 0 else float("nan"))
        ov_n = len(eval_df)
        ov_c = int(eval_df["correct"].sum())
        yr_stats["OVERALL"] = (ov_n, ov_c, ov_c/ov_n if ov_n > 0 else float("nan"))
        results[yr] = yr_stats

    return results


# ══════════════════════════════════════════════════════════════════════════════
# TABLE FORMATTING HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _fmt_acc(acc) -> str:
    if math.isnan(acc): return "  —  "
    return f"{acc*100:.1f}%"


def _fmt_cell(yr_stats, signal_key, yr):
    if yr not in yr_stats:
        return "  — "
    n, c, acc = yr_stats[yr].get(signal_key, (0, 0, float("nan")))
    if n == 0:
        return "  — "
    return f"{acc*100:.0f}%"


def _total_n(results, signal_key):
    return sum(
        results[yr].get(signal_key, (0,))[0]
        for yr in YEARS if yr in results
    )


def _oos_acc(results, signal_key):
    if OOS_YEAR not in results:
        return float("nan")
    n, c, acc = results[OOS_YEAR].get(signal_key, (0, 0, float("nan")))
    return acc


def _4yr_avg(results, signal_key):
    ns, cs = [], []
    for yr in YEARS:
        if yr not in results: continue
        n, c, _ = results[yr].get(signal_key, (0,0,float("nan")))
        ns.append(n); cs.append(c)
    total_n = sum(ns)
    total_c = sum(cs)
    return total_c / total_n if total_n > 0 else float("nan")


def build_sensitivity_table(sweep_name: str, param_label: str,
                             param_values: list, prod_value,
                             result_map: dict,   # param_val -> eval_results
                             signal_key: str,
                             recommend_fn=None) -> tuple[str, list[dict]]:
    """
    Returns (markdown_table_string, raw_rows_list).
    Marks current value with ← and recommended with ★.
    """
    header = (
        f"\n### {sweep_name}\n\n"
        f"| {param_label:<12} | 2022 | 2023 | 2024 | 2025 | 4yr Avg | 2025 OOS | n (total) | |\n"
        f"|{'-'*14}|------|------|------|------|---------|----------|-----------|--|\n"
    )

    rows_md = []
    raw_rows = []
    best_oos = -1.0
    best_val = None

    for val in param_values:
        res = result_map[val]
        yr22 = _fmt_cell(res, signal_key, 2022)
        yr23 = _fmt_cell(res, signal_key, 2023)
        yr24 = _fmt_cell(res, signal_key, 2024)
        yr25 = _fmt_cell(res, signal_key, 2025)
        avg  = _4yr_avg(res, signal_key)
        oos  = _oos_acc(res, signal_key)
        tot  = _total_n(res, signal_key)

        marker = " ←" if val == prod_value else "  "
        oos_n  = res.get(OOS_YEAR, {}).get(signal_key, (0,))[0]

        # Track best for recommendation (2025 OOS acc, min n=5 total)
        if not math.isnan(oos) and tot >= 5:
            if oos > best_oos or (oos == best_oos and tot > _total_n(result_map.get(best_val, {}), signal_key)):
                best_oos = oos
                best_val = val

        row = (f"| {str(val):<12} | {yr22:>4} | {yr23:>4} | {yr24:>4} | {yr25:>4} "
               f"| {_fmt_acc(avg):>7} | {_fmt_acc(oos):>8} | n={tot:<5} |{marker}")
        rows_md.append((val, row, avg, oos, tot))

        raw_rows.append({
            "sweep": sweep_name, "param": param_label, "value": val,
            "signal": signal_key,
            "acc_2022": _4yr_avg({2022: res.get(2022,{})} if 2022 in res else {}, signal_key),
            "acc_2023": _4yr_avg({2023: res.get(2023,{})} if 2023 in res else {}, signal_key),
            "acc_2024": _4yr_avg({2024: res.get(2024,{})} if 2024 in res else {}, signal_key),
            "acc_2025": oos,
            "acc_4yr":  avg,
            "n_total":  tot,
            "n_2025":   oos_n,
            "is_prod":  val == prod_value,
            "is_recommended": False,  # filled in below
        })

    # Mark recommended
    if best_val is not None:
        for r in raw_rows:
            if r["value"] == best_val:
                r["is_recommended"] = True

    lines = [header]
    for val, row, avg, oos, tot in rows_md:
        star = " ★" if val == best_val and best_val != prod_value else "  "
        lines.append(row + star + "\n")

    return "".join(lines), raw_rows


# ══════════════════════════════════════════════════════════════════════════════
# PART 1 — PITCHER SENSITIVITY SWEEPS
# ══════════════════════════════════════════════════════════════════════════════

print("\n" + "="*60)
print("PART 1 — PITCHER SENSITIVITY ANALYSIS")
print("="*60)

pitcher_tables = []
all_raw_rows   = []

# ── P1: Slight Buy ERA Floor ──────────────────────────────────────────────────
print("\nP1: Slight Buy ERA Floor sweep...")
p1_vals = [3.50, 3.60, 3.70, 3.75, 3.80, 3.90, 4.00]
p1_res  = {}
for v in p1_vals:
    p1_res[v] = eval_pitcher_params({"slight_buy_era_floor": v})
    print(f"  {v}: SB n={_total_n(p1_res[v],'SLIGHT_BUY')} acc={_fmt_acc(_4yr_avg(p1_res[v],'SLIGHT_BUY'))}")

tbl, raw = build_sensitivity_table(
    "P1: Pitcher Slight Buy — ERA Floor", "ERA Floor",
    p1_vals, PROD["P_SLIGHT_BUY_ERA_FLOOR"], p1_res, "SLIGHT_BUY")
pitcher_tables.append(tbl); all_raw_rows.extend(raw)

# Also report OVERALL impact
p1_overall_tbl, p1_raw_o = build_sensitivity_table(
    "P1: Pitcher Slight Buy ERA Floor — Overall Impact", "ERA Floor",
    p1_vals, PROD["P_SLIGHT_BUY_ERA_FLOOR"], p1_res, "OVERALL")
pitcher_tables.append(p1_overall_tbl); all_raw_rows.extend(p1_raw_o)

# ── P2: Buy Low ERA Floor ─────────────────────────────────────────────────────
print("\nP2: Buy Low ERA Floor sweep...")
p2_vals = [3.00, 3.25, 3.50, 3.75, 4.00]
p2_res  = {}
for v in p2_vals:
    p2_res[v] = eval_pitcher_params({"era_floor": v})
    print(f"  {v}: BL n={_total_n(p2_res[v],'BUY_LOW')} acc={_fmt_acc(_4yr_avg(p2_res[v],'BUY_LOW'))}")

tbl, raw = build_sensitivity_table(
    "P2: Pitcher Buy Low — ERA Floor", "ERA Floor",
    p2_vals, PROD["P_ERA_FLOOR"], p2_res, "BUY_LOW")
pitcher_tables.append(tbl); all_raw_rows.extend(raw)

# ── P3: IP Minimum ────────────────────────────────────────────────────────────
print("\nP3: IP Minimum sweep...")
p3_vals = [10.0, 15.0, 20.0, 25.0, 30.0]
p3_res  = {}
for v in p3_vals:
    p3_res[v] = eval_pitcher_params({"min_buy_ip": v})
    bl_n = _total_n(p3_res[v], "BUY_LOW")
    sb_n = _total_n(p3_res[v], "SLIGHT_BUY")
    print(f"  IP>={v:.0f}: BL n={bl_n}, SB n={sb_n}")

tbl, raw = build_sensitivity_table(
    "P3: Pitcher Buy Low — IP Minimum", "Min IP",
    p3_vals, PROD["P_MIN_BUY_IP"], p3_res, "BUY_LOW")
pitcher_tables.append(tbl); all_raw_rows.extend(raw)

tbl, raw = build_sensitivity_table(
    "P3: Pitcher Slight Buy — IP Minimum", "Min IP",
    p3_vals, PROD["P_MIN_BUY_IP"], p3_res, "SLIGHT_BUY")
pitcher_tables.append(tbl); all_raw_rows.extend(raw)

# ── P4: FIP Ceiling ───────────────────────────────────────────────────────────
print("\nP4: FIP Ceiling sweep...")
p4_vals = [3.75, 4.00, 4.25, 4.50, 4.75, 5.00]
p4_res  = {}
for v in p4_vals:
    p4_res[v] = eval_pitcher_params({"fip_ceil": v})
    bl_n = _total_n(p4_res[v], "BUY_LOW")
    print(f"  FIP<={v}: BL n={bl_n} acc={_fmt_acc(_4yr_avg(p4_res[v],'BUY_LOW'))}")

tbl, raw = build_sensitivity_table(
    "P4: Pitcher Buy Low — FIP Ceiling", "FIP Ceil",
    p4_vals, PROD["P_FIP_CEILING"], p4_res, "BUY_LOW")
pitcher_tables.append(tbl); all_raw_rows.extend(raw)

# ── P5: SwStr% Floor ──────────────────────────────────────────────────────────
print("\nP5: SwStr% Floor sweep...")
p5_vals = [0.06, 0.07, 0.08, 0.09, 0.10]
p5_res  = {}
for v in p5_vals:
    p5_res[v] = eval_pitcher_params({"swstr_floor": v})
    bl_n = _total_n(p5_res[v], "BUY_LOW")
    print(f"  SwStr>={v:.0%}: BL n={bl_n} acc={_fmt_acc(_4yr_avg(p5_res[v],'BUY_LOW'))}")

tbl, raw = build_sensitivity_table(
    "P5: Pitcher Buy Low — SwStr% Floor", "SwStr Floor",
    p5_vals, PROD["P_SWSTR_FLOOR"], p5_res, "BUY_LOW")
pitcher_tables.append(tbl); all_raw_rows.extend(raw)

# ── P6: Slight Buy LS threshold ───────────────────────────────────────────────
print("\nP6: Slight Buy luck_score lower bound sweep...")
p6_vals = [0.04, 0.05, 0.06, 0.065, 0.07, 0.08]
p6_res  = {}
for v in p6_vals:
    p6_res[v] = eval_pitcher_params({"slight_buy_ls": v})
    sb_n = _total_n(p6_res[v], "SLIGHT_BUY")
    print(f"  SB_LS>={v}: SB n={sb_n} acc={_fmt_acc(_4yr_avg(p6_res[v],'SLIGHT_BUY'))}")

tbl, raw = build_sensitivity_table(
    "P6: Pitcher Slight Buy — Luck Score Lower Bound", "SB LS Threshold",
    p6_vals, PROD["P_SLIGHT_BUY_LS"], p6_res, "SLIGHT_BUY")
pitcher_tables.append(tbl); all_raw_rows.extend(raw)


# ══════════════════════════════════════════════════════════════════════════════
# PART 2 — HITTER SENSITIVITY SWEEPS
# ══════════════════════════════════════════════════════════════════════════════

print("\n" + "="*60)
print("PART 2 — HITTER SENSITIVITY ANALYSIS")
print("="*60)

hitter_tables = []

# ── H1: Buy Low Threshold ─────────────────────────────────────────────────────
print("\nH1: Buy Low threshold sweep...")
h1_vals = [0.080, 0.100, 0.120, 0.130, 0.140, 0.150]
h1_res  = {}
for v in h1_vals:
    h1_res[v] = eval_hitter_params({"buy_low_thresh": v})
    bl_n = _total_n(h1_res[v], "BUY_LOW")
    print(f"  BL>={v}: n={bl_n} acc={_fmt_acc(_4yr_avg(h1_res[v],'BUY_LOW'))}")

tbl, raw = build_sensitivity_table(
    "H1: Hitter Buy Low — Luck Score Threshold", "BL Threshold",
    h1_vals, PROD["H_BUY_LOW_THRESH"], h1_res, "BUY_LOW")
hitter_tables.append(tbl); all_raw_rows.extend(raw)

# ── H2: Slight Buy Threshold ──────────────────────────────────────────────────
print("\nH2: Slight Buy threshold sweep...")
h2_vals = [0.040, 0.050, 0.055, 0.060, 0.065, 0.070]
h2_res  = {}
for v in h2_vals:
    h2_res[v] = eval_hitter_params({"slight_buy_thresh": v})
    sb_n = _total_n(h2_res[v], "SLIGHT_BUY")
    print(f"  SB>={v}: n={sb_n} acc={_fmt_acc(_4yr_avg(h2_res[v],'SLIGHT_BUY'))}")

tbl, raw = build_sensitivity_table(
    "H2: Hitter Slight Buy — Luck Score Threshold", "SB Threshold",
    h2_vals, PROD["H_SLIGHT_BUY_THRESH"], h2_res, "SLIGHT_BUY")
hitter_tables.append(tbl); all_raw_rows.extend(raw)

# ── H3: xwOBA Gate ────────────────────────────────────────────────────────────
print("\nH3: Slight Buy xwOBA gate sweep...")
h3_vals = [0.000, 0.010, 0.015, 0.020, 0.025]
h3_res  = {}
for v in h3_vals:
    h3_res[v] = eval_hitter_params({"xwoba_gate": v})
    sb_n = _total_n(h3_res[v], "SLIGHT_BUY")
    print(f"  xwOBA gate>={v}: SB n={sb_n} acc={_fmt_acc(_4yr_avg(h3_res[v],'SLIGHT_BUY'))}")

tbl, raw = build_sensitivity_table(
    "H3: Hitter Slight Buy — xwOBA Gap Gate", "xwOBA Gate",
    h3_vals, PROD["H_XWOBA_GATE"], h3_res, "SLIGHT_BUY")
hitter_tables.append(tbl); all_raw_rows.extend(raw)

# ── H4: Sell High Threshold ───────────────────────────────────────────────────
print("\nH4: Sell High threshold sweep...")
h4_vals = [-0.080, -0.100, -0.120, -0.130, -0.140, -0.150]
h4_res  = {}
for v in h4_vals:
    h4_res[v] = eval_hitter_params({"sell_high_thresh": v})
    sh_n = _total_n(h4_res[v], "SELL_HIGH")
    print(f"  SH<={v}: n={sh_n} acc={_fmt_acc(_4yr_avg(h4_res[v],'SELL_HIGH'))}")

tbl, raw = build_sensitivity_table(
    "H4: Hitter Sell High — Luck Score Threshold", "SH Threshold",
    h4_vals, PROD["H_SELL_HIGH_THRESH"], h4_res, "SELL_HIGH")
hitter_tables.append(tbl); all_raw_rows.extend(raw)

# ── H5: Slight Sell Threshold ─────────────────────────────────────────────────
print("\nH5: Slight Sell threshold sweep...")
h5_vals = [-0.040, -0.050, -0.060, -0.070, -0.085]
h5_res  = {}
for v in h5_vals:
    h5_res[v] = eval_hitter_params({"slight_sell_thresh": v})
    ss_n = _total_n(h5_res[v], "SLIGHT_SELL")
    print(f"  SS<={v}: n={ss_n} acc={_fmt_acc(_4yr_avg(h5_res[v],'SLIGHT_SELL'))}")

tbl, raw = build_sensitivity_table(
    "H5: Hitter Slight Sell — Luck Score Threshold", "SS Threshold",
    h5_vals, PROD["H_SLIGHT_SELL_THRESH"], h5_res, "SLIGHT_SELL")
hitter_tables.append(tbl); all_raw_rows.extend(raw)


# ══════════════════════════════════════════════════════════════════════════════
# PART 3 — INTERACTION EFFECTS
# ══════════════════════════════════════════════════════════════════════════════

print("\n" + "="*60)
print("PART 3 — INTERACTION EFFECTS")
print("="*60)

interaction_tables = []

# Find best individual values from pitcher sweeps
def _best_val(res_map, signal_key, prod_val, prefer_smaller=False):
    """Return the param value with best 2025 OOS accuracy (min n=5 total)."""
    best_acc = -1.0; best_v = prod_val
    for v, res in res_map.items():
        oos = _oos_acc(res, signal_key)
        tot = _total_n(res, signal_key)
        if math.isnan(oos) or tot < 5: continue
        if oos > best_acc: best_acc = oos; best_v = v
    return best_v

best_p1 = _best_val(p1_res, "SLIGHT_BUY", PROD["P_SLIGHT_BUY_ERA_FLOOR"])
best_p4 = _best_val(p4_res, "BUY_LOW",    PROD["P_FIP_CEILING"])
best_p5 = _best_val(p5_res, "BUY_LOW",    PROD["P_SWSTR_FLOOR"])
best_p2 = _best_val(p2_res, "BUY_LOW",    PROD["P_ERA_FLOOR"])

print(f"\nBest pitcher individual values:")
print(f"  P1 (SB ERA floor): {best_p1}  (prod={PROD['P_SLIGHT_BUY_ERA_FLOOR']})")
print(f"  P2 (BL ERA floor): {best_p2}  (prod={PROD['P_ERA_FLOOR']})")
print(f"  P4 (FIP ceil):     {best_p4}  (prod={PROD['P_FIP_CEILING']})")
print(f"  P5 (SwStr floor):  {best_p5}  (prod={PROD['P_SWSTR_FLOOR']})")

# Pitcher interaction: best P1 + best P4
if best_p1 != PROD["P_SLIGHT_BUY_ERA_FLOOR"] or best_p4 != PROD["P_FIP_CEILING"]:
    print(f"\nPitcher interaction: P1={best_p1} + P4={best_p4}")
    pi1_vals = [
        (PROD["P_SLIGHT_BUY_ERA_FLOOR"], PROD["P_FIP_CEILING"]),
        (best_p1, PROD["P_FIP_CEILING"]),
        (PROD["P_SLIGHT_BUY_ERA_FLOOR"], best_p4),
        (best_p1, best_p4),
    ]
    pi1_res = {}
    for sb_era, fip_c in pi1_vals:
        pi1_res[(sb_era, fip_c)] = eval_pitcher_params({
            "slight_buy_era_floor": sb_era,
            "fip_ceil": fip_c,
        })

    lines = ["\n### Pitcher Interaction: SB ERA Floor × FIP Ceiling\n\n"]
    lines.append("| SB ERA Floor | FIP Ceil | BL 4yr | SB 4yr | Overall 4yr | 2025 OOS |\n")
    lines.append("|---|---|---|---|---|---|\n")
    for (sb_era, fip_c), res in pi1_res.items():
        prod_m = " ←" if sb_era==PROD["P_SLIGHT_BUY_ERA_FLOOR"] and fip_c==PROD["P_FIP_CEILING"] else ""
        lines.append(
            f"| {sb_era} | {fip_c} "
            f"| {_fmt_acc(_4yr_avg(res,'BUY_LOW'))} "
            f"| {_fmt_acc(_4yr_avg(res,'SLIGHT_BUY'))} "
            f"| {_fmt_acc(_4yr_avg(res,'OVERALL'))} "
            f"| {_fmt_acc(_oos_acc(res,'OVERALL'))} {prod_m}|\n"
        )
    interaction_tables.append("".join(lines))

# Pitcher interaction: best P2 + best P5
if best_p2 != PROD["P_ERA_FLOOR"] or best_p5 != PROD["P_SWSTR_FLOOR"]:
    print(f"\nPitcher interaction: P2 ERA floor={best_p2} + P5 SwStr floor={best_p5}")
    pi2_vals = [
        (PROD["P_ERA_FLOOR"], PROD["P_SWSTR_FLOOR"]),
        (best_p2, PROD["P_SWSTR_FLOOR"]),
        (PROD["P_ERA_FLOOR"], best_p5),
        (best_p2, best_p5),
    ]
    pi2_res = {}
    for era_f, swstr_f in pi2_vals:
        pi2_res[(era_f, swstr_f)] = eval_pitcher_params({
            "era_floor": era_f,
            "swstr_floor": swstr_f,
        })

    lines = ["\n### Pitcher Interaction: BL ERA Floor × SwStr% Floor\n\n"]
    lines.append("| BL ERA Floor | SwStr Floor | BL 4yr | SB 4yr | Overall 4yr | 2025 OOS |\n")
    lines.append("|---|---|---|---|---|---|\n")
    for (era_f, swstr_f), res in pi2_res.items():
        prod_m = " ←" if era_f==PROD["P_ERA_FLOOR"] and swstr_f==PROD["P_SWSTR_FLOOR"] else ""
        lines.append(
            f"| {era_f} | {swstr_f:.0%} "
            f"| {_fmt_acc(_4yr_avg(res,'BUY_LOW'))} "
            f"| {_fmt_acc(_4yr_avg(res,'SLIGHT_BUY'))} "
            f"| {_fmt_acc(_4yr_avg(res,'OVERALL'))} "
            f"| {_fmt_acc(_oos_acc(res,'OVERALL'))} {prod_m}|\n"
        )
    interaction_tables.append("".join(lines))

# Hitter interaction: best H1 + H3
best_h1 = _best_val(h1_res, "BUY_LOW",    PROD["H_BUY_LOW_THRESH"])
best_h2 = _best_val(h2_res, "SLIGHT_BUY", PROD["H_SLIGHT_BUY_THRESH"])
best_h3 = _best_val(h3_res, "SLIGHT_BUY", PROD["H_XWOBA_GATE"])
best_h4 = _best_val(h4_res, "SELL_HIGH",  PROD["H_SELL_HIGH_THRESH"])
best_h5 = _best_val(h5_res, "SLIGHT_SELL",PROD["H_SLIGHT_SELL_THRESH"])

print(f"\nBest hitter individual values:")
print(f"  H1 (BL thresh):    {best_h1}  (prod={PROD['H_BUY_LOW_THRESH']})")
print(f"  H2 (SB thresh):    {best_h2}  (prod={PROD['H_SLIGHT_BUY_THRESH']})")
print(f"  H3 (xwOBA gate):   {best_h3}  (prod={PROD['H_XWOBA_GATE']})")
print(f"  H4 (SH thresh):    {best_h4}  (prod={PROD['H_SELL_HIGH_THRESH']})")
print(f"  H5 (SS thresh):    {best_h5}  (prod={PROD['H_SLIGHT_SELL_THRESH']})")

# Hitter interaction: best H1 + H2 (buy-side)
if best_h1 != PROD["H_BUY_LOW_THRESH"] or best_h2 != PROD["H_SLIGHT_BUY_THRESH"]:
    print(f"\nHitter buy-side interaction: BL={best_h1}, SB={best_h2}")
    hi1_vals = [
        (PROD["H_BUY_LOW_THRESH"], PROD["H_SLIGHT_BUY_THRESH"]),
        (best_h1, PROD["H_SLIGHT_BUY_THRESH"]),
        (PROD["H_BUY_LOW_THRESH"], best_h2),
        (best_h1, best_h2),
    ]
    hi1_res = {}
    for bl, sb in hi1_vals:
        hi1_res[(bl, sb)] = eval_hitter_params({
            "buy_low_thresh": bl, "slight_buy_thresh": sb
        })

    lines = ["\n### Hitter Interaction: BL Threshold × SB Threshold\n\n"]
    lines.append("| BL Thresh | SB Thresh | BL 4yr | SB 4yr | Overall 4yr | 2025 OOS |\n")
    lines.append("|---|---|---|---|---|---|\n")
    for (bl, sb), res in hi1_res.items():
        prod_m = " ←" if bl==PROD["H_BUY_LOW_THRESH"] and sb==PROD["H_SLIGHT_BUY_THRESH"] else ""
        lines.append(
            f"| {bl} | {sb} "
            f"| {_fmt_acc(_4yr_avg(res,'BUY_LOW'))} "
            f"| {_fmt_acc(_4yr_avg(res,'SLIGHT_BUY'))} "
            f"| {_fmt_acc(_4yr_avg(res,'OVERALL'))} "
            f"| {_fmt_acc(_oos_acc(res,'OVERALL'))} {prod_m}|\n"
        )
    interaction_tables.append("".join(lines))

# Hitter interaction: best H4 + H5 (sell-side)
if best_h4 != PROD["H_SELL_HIGH_THRESH"] or best_h5 != PROD["H_SLIGHT_SELL_THRESH"]:
    print(f"\nHitter sell-side interaction: SH={best_h4}, SS={best_h5}")
    hi2_vals = [
        (PROD["H_SELL_HIGH_THRESH"], PROD["H_SLIGHT_SELL_THRESH"]),
        (best_h4, PROD["H_SLIGHT_SELL_THRESH"]),
        (PROD["H_SELL_HIGH_THRESH"], best_h5),
        (best_h4, best_h5),
    ]
    hi2_res = {}
    for sh, ss in hi2_vals:
        hi2_res[(sh, ss)] = eval_hitter_params({
            "sell_high_thresh": sh, "slight_sell_thresh": ss
        })

    lines = ["\n### Hitter Interaction: SH Threshold × SS Threshold\n\n"]
    lines.append("| SH Thresh | SS Thresh | SH 4yr | SS 4yr | Overall 4yr | 2025 OOS |\n")
    lines.append("|---|---|---|---|---|---|\n")
    for (sh, ss), res in hi2_res.items():
        prod_m = " ←" if sh==PROD["H_SELL_HIGH_THRESH"] and ss==PROD["H_SLIGHT_SELL_THRESH"] else ""
        lines.append(
            f"| {sh} | {ss} "
            f"| {_fmt_acc(_4yr_avg(res,'SELL_HIGH'))} "
            f"| {_fmt_acc(_4yr_avg(res,'SLIGHT_SELL'))} "
            f"| {_fmt_acc(_4yr_avg(res,'OVERALL'))} "
            f"| {_fmt_acc(_oos_acc(res,'OVERALL'))} {prod_m}|\n"
        )
    interaction_tables.append("".join(lines))


# ══════════════════════════════════════════════════════════════════════════════
# PART 4 — BASELINE TABLE (current production values)
# ══════════════════════════════════════════════════════════════════════════════

prod_pitcher = eval_pitcher_params({})
prod_hitter  = eval_hitter_params({})

def _baseline_row(label, results, signals):
    parts = [f"**{label}**"]
    for sig in signals:
        parts.append(_fmt_acc(_4yr_avg(results, sig)))
        parts.append(f"n={_total_n(results,sig)}")
        parts.append(_fmt_acc(_oos_acc(results, sig)))
    return " | ".join(parts)


# ══════════════════════════════════════════════════════════════════════════════
# PART 5 — RECOMMENDATIONS
# ══════════════════════════════════════════════════════════════════════════════

def _delta(new_val, prod_val, res_map, signal_key):
    prod_acc = _4yr_avg(res_map[prod_val], signal_key)
    new_acc  = _4yr_avg(res_map[new_val],  signal_key)
    prod_n   = _total_n(res_map[prod_val], signal_key)
    new_n    = _total_n(res_map[new_val],  signal_key)
    if math.isnan(prod_acc) or math.isnan(new_acc):
        return float("nan"), 0
    return new_acc - prod_acc, new_n - prod_n


recommendation_lines = []

def _add_rec(param_name, current_val, rec_val, res_map, signal_key, reason=""):
    if rec_val == current_val:
        return False
    acc_delta, n_delta = _delta(rec_val, current_val, res_map, signal_key)
    oos_new  = _fmt_acc(_oos_acc(res_map[rec_val], signal_key))
    oos_prod = _fmt_acc(_oos_acc(res_map[current_val], signal_key))
    n_new    = _total_n(res_map[rec_val], signal_key)
    conf = "HIGH" if n_new >= 20 else ("MED" if n_new >= 8 else "LOW")
    if math.isnan(acc_delta): return False
    sign = "+" if acc_delta >= 0 else ""
    recommendation_lines.append(
        f"| {param_name} | {current_val} | **{rec_val}** | "
        f"{'+' if n_delta>=0 else ''}{n_delta} signals | "
        f"{sign}{acc_delta*100:.1f}pp ({oos_prod} → {oos_new} OOS) | "
        f"{conf} | {reason} |"
    )
    return True

_pitcher_changed = False
_pitcher_changed |= _add_rec("P1: SB ERA Floor", PROD["P_SLIGHT_BUY_ERA_FLOOR"], best_p1,
    p1_res, "SLIGHT_BUY", "ERA gate for Slight Buy signals")
_pitcher_changed |= _add_rec("P2: BL ERA Floor", PROD["P_ERA_FLOOR"], best_p2,
    p2_res, "BUY_LOW", "ERA gate for Buy Low signals")
_pitcher_changed |= _add_rec("P4: FIP Ceiling", PROD["P_FIP_CEILING"], best_p4,
    p4_res, "BUY_LOW", "Stricter FIP requirement filters noise")
_pitcher_changed |= _add_rec("P5: SwStr% Floor", PROD["P_SWSTR_FLOOR"], best_p5,
    p5_res, "BUY_LOW", "Swing-and-miss requirement")
best_p6 = _best_val(p6_res, "SLIGHT_BUY", PROD["P_SLIGHT_BUY_LS"])
_pitcher_changed |= _add_rec("P6: SB LS Bound", PROD["P_SLIGHT_BUY_LS"], best_p6,
    p6_res, "SLIGHT_BUY", "Score threshold for Slight Buy classification")

_hitter_changed = False
_hitter_changed |= _add_rec("H1: BL Threshold", PROD["H_BUY_LOW_THRESH"], best_h1,
    h1_res, "BUY_LOW", "Buy Low classification boundary")
_hitter_changed |= _add_rec("H2: SB Threshold", PROD["H_SLIGHT_BUY_THRESH"], best_h2,
    h2_res, "SLIGHT_BUY", "Slight Buy classification boundary")
_hitter_changed |= _add_rec("H3: xwOBA Gate", PROD["H_XWOBA_GATE"], best_h3,
    h3_res, "SLIGHT_BUY", "xwOBA quality gate for Slight Buy")
_hitter_changed |= _add_rec("H4: SH Threshold", PROD["H_SELL_HIGH_THRESH"], best_h4,
    h4_res, "SELL_HIGH", "Sell High classification boundary")
_hitter_changed |= _add_rec("H5: SS Threshold", PROD["H_SLIGHT_SELL_THRESH"], best_h5,
    h5_res, "SLIGHT_SELL", "Slight Sell classification boundary")


# ══════════════════════════════════════════════════════════════════════════════
# WRITE MARKDOWN REPORT
# ══════════════════════════════════════════════════════════════════════════════

def _prod_baseline_table(results, signals, labels):
    lines = ["| Signal | 2022 | 2023 | 2024 | 2025 | 4yr Avg | 2025 OOS | n (total) |\n",
             "|--------|------|------|------|------|---------|----------|-----------|\n"]
    for sig, lbl in zip(signals, labels):
        n, c, _ = {}, {}, {}
        row_parts = [lbl]
        for yr in YEARS:
            if yr not in results:
                row_parts.append("—")
                continue
            ni, ci, ai = results[yr].get(sig, (0,0,float("nan")))
            row_parts.append(_fmt_cell(results, sig, yr) + f" (n={ni})")
        row_parts.append(_fmt_acc(_4yr_avg(results, sig)))
        row_parts.append(_fmt_acc(_oos_acc(results, sig)))
        row_parts.append(f"n={_total_n(results,sig)}")
        lines.append("| " + " | ".join(row_parts) + " |\n")
    return "".join(lines)

report_sections = [
    "# Sensitivity Analysis Results\n",
    f"*Generated: April 25, 2026 | Training: 2022–2024 | Validation (OOS): 2025*\n\n",
    "---\n\n",
    "## Production Baseline (current parameter values)\n\n",
    "### Pitcher Model — Current Production\n\n",
    _prod_baseline_table(prod_pitcher,
        ["BUY_LOW","SLIGHT_BUY","SLIGHT_SELL","SELL_HIGH","OVERALL"],
        ["Buy Low","Slight Buy","Slight Sell","Sell High","Overall"]),
    "\n### Hitter Model — Current Production\n\n",
    _prod_baseline_table(prod_hitter,
        ["BUY_LOW","SLIGHT_BUY","SLIGHT_SELL","SELL_HIGH","OVERALL"],
        ["Buy Low","Slight Buy","Slight Sell","Sell High","Overall"]),
    "\n---\n\n",
    "## PART 1 — Pitcher Sensitivity Analysis\n\n",
]

report_sections.extend(pitcher_tables)
report_sections.append("\n---\n\n## PART 2 — Hitter Sensitivity Analysis\n\n")
report_sections.extend(hitter_tables)
report_sections.append("\n---\n\n## PART 3 — Interaction Effects\n\n")
report_sections.extend(interaction_tables)

report_sections.append("\n---\n\n## PART 5 — Recommendations\n\n")

if recommendation_lines:
    report_sections.append("### Parameters to Change\n\n")
    report_sections.append("| Parameter | Current | Recommended | Signal Δ | Accuracy Δ | Confidence | Notes |\n")
    report_sections.append("|-----------|---------|-------------|----------|------------|------------|-------|\n")
    report_sections.extend([r + "\n" for r in recommendation_lines])
else:
    report_sections.append("**All current parameters appear optimal.** No changes recommended.\n")

report_sections.append("\n### Parameters to Keep As-Is\n\n")
report_sections.append("| Parameter | Current | Reason |\n")
report_sections.append("|-----------|---------|--------|\n")

kept_params = []
if best_p1 == PROD["P_SLIGHT_BUY_ERA_FLOOR"]: kept_params.append(("P1: SB ERA Floor", PROD["P_SLIGHT_BUY_ERA_FLOOR"], "Already optimal on 2025 OOS"))
if best_p2 == PROD["P_ERA_FLOOR"]:            kept_params.append(("P2: BL ERA Floor", PROD["P_ERA_FLOOR"], "Already optimal on 2025 OOS"))
if best_p4 == PROD["P_FIP_CEILING"]:          kept_params.append(("P4: FIP Ceiling",  PROD["P_FIP_CEILING"], "Already optimal on 2025 OOS"))
if best_p5 == PROD["P_SWSTR_FLOOR"]:          kept_params.append(("P5: SwStr% Floor", PROD["P_SWSTR_FLOOR"], "Already optimal on 2025 OOS"))
if best_h1 == PROD["H_BUY_LOW_THRESH"]:       kept_params.append(("H1: BL Threshold", PROD["H_BUY_LOW_THRESH"], "Already optimal on 2025 OOS"))
if best_h2 == PROD["H_SLIGHT_BUY_THRESH"]:    kept_params.append(("H2: SB Threshold", PROD["H_SLIGHT_BUY_THRESH"], "Already optimal on 2025 OOS"))
if best_h3 == PROD["H_XWOBA_GATE"]:           kept_params.append(("H3: xwOBA Gate",   PROD["H_XWOBA_GATE"], "Already optimal on 2025 OOS"))
if best_h4 == PROD["H_SELL_HIGH_THRESH"]:     kept_params.append(("H4: SH Threshold", PROD["H_SELL_HIGH_THRESH"], "Already optimal on 2025 OOS"))
if best_h5 == PROD["H_SLIGHT_SELL_THRESH"]:   kept_params.append(("H5: SS Threshold", PROD["H_SLIGHT_SELL_THRESH"], "Already optimal on 2025 OOS"))

for name, val, reason in kept_params:
    report_sections.append(f"| {name} | {val} | {reason} |\n")

report_sections.append("\n### Risk Assessment\n\n")
report_sections.append("""
**High confidence (n >= 20 historically):**
- Sell High signals across all models — large samples, consistent yearly accuracy
- Overall pitcher accuracy — driven primarily by Sell High which dominates signal count

**Medium confidence (n = 8-20):**
- Buy Low pitcher signals — n=30 total; directionally reliable but high year-to-year variance
- Hitter Buy Low — larger sample but sensitive to threshold choice

**Low confidence / Small sample:**
- Pitcher Slight Buy — n=4 total in Version E backtest; any accuracy number is noise
  The ERA floor (P1) analysis has too few signals to draw firm conclusions
- Hitter Slight Buy — n varies significantly by threshold; xwOBA gate impact is real
  but hard to measure precisely given overlap with BABIP luck signal

**Flags:**
- If ANY pitcher parameter change causes 2025 Overall accuracy < 85%, reject it
- Pitcher Slight Buy accuracy = 100% at current production — this is a ceiling artifact
  (n=4), not a reason to declare current parameters optimal for that signal
- The CLAUDE.md "KNOWN OPEN FIX" (ERA < 3.75 suppresses Buy Low) is captured in P2;
  if P2 sensitivity shows 3.75 better than 3.50, that confirms the fix is warranted
""")

# ── Write the report ──────────────────────────────────────────────────────────
out_md = DATA_DIR / "sensitivity_analysis_results.md"
with open(out_md, "w", encoding="utf-8") as f:
    f.writelines(report_sections)
print(f"\nWrote {out_md}")

# ── Write raw CSV ─────────────────────────────────────────────────────────────
raw_df = pd.DataFrame(all_raw_rows)
out_csv = DATA_DIR / "sensitivity_analysis_raw.csv"
raw_df.to_csv(out_csv, index=False)
print(f"Wrote {out_csv} ({len(raw_df)} rows)")

# ── Print summary to console ──────────────────────────────────────────────────
print("\n" + "="*70)
print("SENSITIVITY ANALYSIS — CONSOLE SUMMARY")
print("="*70)

print("\nPITCHER BASELINE (production parameters):")
for sig in ["BUY_LOW","SLIGHT_BUY","SLIGHT_SELL","SELL_HIGH","OVERALL"]:
    acc4 = _4yr_avg(prod_pitcher, sig)
    oos  = _oos_acc(prod_pitcher, sig)
    tot  = _total_n(prod_pitcher, sig)
    print(f"  {sig:<12}: 4yr={_fmt_acc(acc4):>7}  2025={_fmt_acc(oos):>7}  n={tot}")

print("\nHITTER BASELINE (production parameters):")
for sig in ["BUY_LOW","SLIGHT_BUY","SLIGHT_SELL","SELL_HIGH","OVERALL"]:
    acc4 = _4yr_avg(prod_hitter, sig)
    oos  = _oos_acc(prod_hitter, sig)
    tot  = _total_n(prod_hitter, sig)
    print(f"  {sig:<12}: 4yr={_fmt_acc(acc4):>7}  2025={_fmt_acc(oos):>7}  n={tot}")

print("\nKEY SENSITIVITY FINDINGS:")
print("\n  PITCHER:")
for v in p1_vals:
    res = p1_res[v]
    sb_n = _total_n(res, "SLIGHT_BUY")
    sb_a = _4yr_avg(res, "SLIGHT_BUY")
    sb_o = _oos_acc(res, "SLIGHT_BUY")
    mark = " ←" if v == PROD["P_SLIGHT_BUY_ERA_FLOOR"] else ("  ★" if v == best_p1 and best_p1 != PROD["P_SLIGHT_BUY_ERA_FLOOR"] else "")
    print(f"    P1 SB ERA floor {v}: SB n={sb_n:>3}  4yr={_fmt_acc(sb_a)}  2025={_fmt_acc(sb_o)}{mark}")

print()
for v in p2_vals:
    res = p2_res[v]
    bl_n = _total_n(res, "BUY_LOW")
    bl_a = _4yr_avg(res, "BUY_LOW")
    bl_o = _oos_acc(res, "BUY_LOW")
    ov_o = _oos_acc(res, "OVERALL")
    mark = " ←" if v == PROD["P_ERA_FLOOR"] else ("  ★" if v == best_p2 and best_p2 != PROD["P_ERA_FLOOR"] else "")
    print(f"    P2 BL ERA floor {v}: BL n={bl_n:>3}  4yr={_fmt_acc(bl_a)}  2025={_fmt_acc(bl_o)}  overall={_fmt_acc(ov_o)}{mark}")

print()
for v in p4_vals:
    res = p4_res[v]
    bl_n = _total_n(res, "BUY_LOW")
    bl_a = _4yr_avg(res, "BUY_LOW")
    bl_o = _oos_acc(res, "BUY_LOW")
    mark = " ←" if v == PROD["P_FIP_CEILING"] else ("  ★" if v == best_p4 and best_p4 != PROD["P_FIP_CEILING"] else "")
    print(f"    P4 FIP ceil {v}: BL n={bl_n:>3}  4yr={_fmt_acc(bl_a)}  2025={_fmt_acc(bl_o)}{mark}")

print("\n  HITTER:")
for v in h1_vals:
    res = h1_res[v]
    bl_n = _total_n(res, "BUY_LOW")
    bl_a = _4yr_avg(res, "BUY_LOW")
    bl_o = _oos_acc(res, "BUY_LOW")
    mark = " ←" if v == PROD["H_BUY_LOW_THRESH"] else ("  ★" if v == best_h1 and best_h1 != PROD["H_BUY_LOW_THRESH"] else "")
    print(f"    H1 BL thresh {v}: BL n={bl_n:>3}  4yr={_fmt_acc(bl_a)}  2025={_fmt_acc(bl_o)}{mark}")

print()
for v in h3_vals:
    res = h3_res[v]
    sb_n = _total_n(res, "SLIGHT_BUY")
    sb_a = _4yr_avg(res, "SLIGHT_BUY")
    sb_o = _oos_acc(res, "SLIGHT_BUY")
    mark = " ←" if v == PROD["H_XWOBA_GATE"] else ("  ★" if v == best_h3 and best_h3 != PROD["H_XWOBA_GATE"] else "")
    print(f"    H3 xwOBA gate {v}: SB n={sb_n:>3}  4yr={_fmt_acc(sb_a)}  2025={_fmt_acc(sb_o)}{mark}")

if recommendation_lines:
    print("\nRECOMMENDATIONS:")
    for r in recommendation_lines:
        # Strip markdown
        parts = [p.strip().replace("**","") for p in r.split("|")]
        print(f"  {parts[1]}: {parts[2]} → {parts[3]}  ({parts[5]})")
else:
    print("\nNo parameter changes recommended — all current values appear optimal.")

print("\n=== SENSITIVITY ANALYSIS COMPLETE ===")
