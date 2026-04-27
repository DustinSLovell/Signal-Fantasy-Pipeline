"""
backtest_pitcher_pitch_mix.py

Extends Version E pitcher backtest with pitch mix evolution modifier (Version F, G).

Version E = production-aligned baseline (replicated from archive/backtest_pitcher_composite.py)
Version F = Version E + Phase 1 pitch mix modifier
  - Abandonment: best career pitch losing >10pp usage AND career_swstr > 15% → ×0.90 buy / ×1.10 sell
  - Effectiveness: best pitch SwStr improved >2pp AND curr_swstr >= 12% → ×1.10 buy
  - Career baseline = pooled April parquets for all years BEFORE the target year
  - new_pitch_flag = False (Statcast label noise, Phase 1)
  - swstr_overall_delta excluded (77% of pitchers show decline at early April sample sizes)
  - 2022 excluded from pitch mix modifier (no prior year data for career baseline)

Version G = Version F + Phase 2 signals
  - Per-pitch velo delta from April parquets (best pitch drop > 1.5 mph bearish, gain > 1.0 mph bullish)
  - RV delta from statcast_pitcher_arsenal_stats (best pitch degrade > 3.0 rv/100 bearish, improve > 3.0 bullish)
  - All 6 flags stack multiplicatively (same as live scorer)

Output: training years 2022-2024 vs 2025 OOS comparison
"""

import json, math, os, sys
import numpy as np
import pandas as pd
from pathlib import Path

_SCRIPT_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, str(_SCRIPT_DIR))
sys.path.insert(0, str(_SCRIPT_DIR / "archive"))

from _pitcher_tier_audit import (
    per_start_stats, pitcher_stats, compute_volatility, load_or_fetch,
    CACHE_DIR, P_YEARS, PARK_FACTORS, SIGNAL_MAP, _TIER_DISPLAY,
    ERA_FLAT, MIN_APRIL_IP, MIN_OUTCOME_IP, LEAGUE_AVG_BABIP,
    VOL_DAMP, career_babip_p, career_hh_p, career_barrel_p,
)
from archive.backtest_pitcher_composite import (
    _add_composite_scores, _april_conf_scale, _classify_split_calibrated,
    _is_buy_qualified, _hrfb_component, _load_fg_xera,
    _BIRTH_YEARS, _CAREER_IP,
    BABIP_WEIGHT, LOB_WEIGHT, ERA_FIP_WEIGHT, XWOBA_WEIGHT,
    HH_WEIGHT, BARREL_WEIGHT, SWSTR_WEIGHT,
    LOB_AVG, SWSTR_AVG, HH_FLAT, BARREL_FLAT,
    COMP_BUY_LOW, COMP_SLIGHT_BUY, COMP_SLIGHT_SELL, COMP_SELL_HIGH,
    TIERS, RTM_BASELINE,
    XWOBA_TO_XERA_COEF, XWOBA_TO_XERA_INTERCEPT,
    E_BUY_LOW, E_SLIGHT_BUY, E_MIN_BUY_IP, E_ERA_FLOOR,
    E_BUY_LOW_ERA_FLOOR, E_SLIGHT_BUY_ERA_FLOOR,
    E_BUY_LOW_LS, E_SLIGHT_BUY_LS,
    compute_extra_stats, _load_full_parquet,
)

BASE_DIR = _SCRIPT_DIR

# ── Pitch mix delta thresholds (mirror build_pitch_mix_delta.py) ──────────────
ABANDON_USAGE_THRESH  = 0.10   # >10pp usage drop on best career pitch
ABANDON_SWSTR_FLOOR   = 0.15   # career swstr must exceed this to flag
EFFECT_SWSTR_DELTA    = 0.02   # 2pp SwStr improvement on best pitch
EFFECT_SWSTR_FLOOR    = 0.12   # curr swstr must clear this threshold
MIN_PITCHES           = 50     # minimum pitches per year to include a pitcher
MIN_RV_PA             = 10     # minimum PA per year-pitcher-type for RV baseline
VELO_DROP_THRESH      = 1.5    # mph drop on best pitch (bearish)
VELO_GAIN_THRESH      = 1.0    # mph gain on best pitch (bullish)
RV_DEGRADE_THRESH     = 3.0    # rv/100 worsening (bearish)
RV_IMPROVE_THRESH     = 3.0    # rv/100 improvement (bullish)

ALL_RV_PATH = _SCRIPT_DIR / "data" / "pitcher_arsenal_rv_allyears.csv"


def _compute_pitch_mix_from_parquet(sc: pd.DataFrame) -> dict:
    """
    Computes per-pitcher pitch mix from a full-schema Statcast parquet.
    Returns {pitcher_id: {pitch_type: {usage, swstr}}, overall_swstr}.
    Requires: pitch_type, description, pitcher columns.
    """
    if sc.empty or "pitch_type" not in sc.columns:
        return {}

    sc = sc.copy()
    sc["pitcher"] = pd.to_numeric(sc["pitcher"], errors="coerce")
    sc = sc.dropna(subset=["pitcher"])
    sc["pitcher"] = sc["pitcher"].astype(int)
    sc = sc[sc["pitch_type"].notna() & (sc["pitch_type"] != "")]

    swstr_mask = sc["description"].isin({"swinging_strike", "swinging_strike_blocked"})

    results = {}
    for pid, grp in sc.groupby("pitcher"):
        total = len(grp)
        if total < MIN_PITCHES:
            continue
        overall_swstr = swstr_mask.reindex(grp.index, fill_value=False).sum() / total

        by_type = {}
        for pt, pt_grp in grp.groupby("pitch_type"):
            usage = len(pt_grp) / total
            pt_swstr = swstr_mask.reindex(pt_grp.index, fill_value=False).sum() / len(pt_grp)
            by_type[pt] = {"usage": round(usage, 4), "swstr": round(pt_swstr, 4)}

        results[pid] = {"by_type": by_type, "overall_swstr": round(overall_swstr, 4)}
    return results


def _build_career_baseline(parquets_before_year: list) -> dict:
    """
    Averages pitch mix across all prior-year parquets.
    Returns {pitcher_id: {pitch_type: {career_usage, career_swstr}}}
    """
    accum = {}  # {pid: {pt: {usages: [], swstrs: []}}}

    for sc in parquets_before_year:
        pm = _compute_pitch_mix_from_parquet(sc)
        for pid, rec in pm.items():
            if pid not in accum:
                accum[pid] = {}
            for pt, vals in rec["by_type"].items():
                if pt not in accum[pid]:
                    accum[pid][pt] = {"usages": [], "swstrs": []}
                accum[pid][pt]["usages"].append(vals["usage"])
                accum[pid][pt]["swstrs"].append(vals["swstr"])

    # Average across years
    career = {}
    for pid, pts in accum.items():
        career[pid] = {}
        for pt, vals in pts.items():
            career[pid][pt] = {
                "career_usage": round(sum(vals["usages"]) / len(vals["usages"]), 4),
                "career_swstr": round(sum(vals["swstrs"]) / len(vals["swstrs"]), 4),
            }
    return career


def compute_pitch_mix_signals_for_year(year: int, all_parquets: dict) -> dict:
    """
    Builds pitch mix delta signals for every pitcher in a given year.
    Career baseline = average of all prior years in all_parquets.
    Returns {pitcher_id: {abandonment_flag, effectiveness_flag, pitch_mix_signal}}
    """
    prior_years = sorted(y for y in all_parquets if y < year)
    if not prior_years:
        return {}  # No career baseline for first year

    career = _build_career_baseline([all_parquets[y] for y in prior_years])
    curr   = _compute_pitch_mix_from_parquet(all_parquets[year])

    signals = {}
    for pid in set(career.keys()) & set(curr.keys()):
        c_pm = career[pid]
        n_pm = curr[pid]["by_type"]

        # Best career pitch by SwStr%
        if not c_pm:
            continue
        best_pt = max(c_pm, key=lambda pt: c_pm[pt]["career_swstr"])
        best_career_swstr = c_pm[best_pt]["career_swstr"]

        # Usage delta for best pitch (must be in current year too)
        best_usage_delta = None
        best_swstr_delta = None
        if best_pt in c_pm and best_pt in n_pm:
            best_usage_delta = n_pm[best_pt]["usage"] - c_pm[best_pt]["career_usage"]
            best_swstr_delta = n_pm[best_pt]["swstr"] - c_pm[best_pt]["career_swstr"]

        # Abandonment signal
        abandonment_flag = (
            best_pt in n_pm
            and best_career_swstr > ABANDON_SWSTR_FLOOR
            and best_usage_delta is not None
            and best_usage_delta < -ABANDON_USAGE_THRESH
        )

        # Effectiveness signal
        curr_best_swstr = n_pm.get(best_pt, {}).get("swstr", 0.0) if best_pt in n_pm else 0.0
        effectiveness_flag = (
            best_swstr_delta is not None
            and best_swstr_delta > EFFECT_SWSTR_DELTA
            and curr_best_swstr >= EFFECT_SWSTR_FLOOR
        )

        pitch_mix_signal = 0.0
        if abandonment_flag:
            pitch_mix_signal -= 0.10
        if effectiveness_flag:
            pitch_mix_signal += 0.05

        signals[pid] = {
            "abandonment_flag":   abandonment_flag,
            "effectiveness_flag": effectiveness_flag,
            "pitch_mix_signal":   round(pitch_mix_signal, 4),
        }
    return signals


# ── Phase 2 helpers ───────────────────────────────────────────────────────────

def _compute_pitch_velo_from_parquet(sc: pd.DataFrame) -> dict:
    """Returns {pitcher_id: {pitch_type: avg_release_speed}}."""
    if sc.empty or "release_speed" not in sc.columns:
        return {}
    sc = sc.copy()
    sc["pitcher"] = pd.to_numeric(sc["pitcher"], errors="coerce")
    sc = sc.dropna(subset=["pitcher", "release_speed", "pitch_type"])
    sc = sc[sc["pitch_type"] != ""]
    sc["pitcher"] = sc["pitcher"].astype(int)
    sc["release_speed"] = sc["release_speed"].astype(float)

    result = {}
    for (pid, pt), grp in sc.groupby(["pitcher", "pitch_type"]):
        if len(grp) < MIN_PITCHES:
            continue
        avg = grp["release_speed"].mean()
        if math.isnan(avg):
            continue
        if pid not in result:
            result[pid] = {}
        result[pid][pt] = round(avg, 2)
    return result


def _build_career_velo(parquets_before_year: list) -> dict:
    """
    Average per-pitch velo across prior-year parquets.
    Returns {pitcher_id: {pitch_type: career_avg_velo}}.
    """
    accum = {}
    for sc in parquets_before_year:
        yr_velo = _compute_pitch_velo_from_parquet(sc)
        for pid, pt_dict in yr_velo.items():
            if pid not in accum:
                accum[pid] = {}
            for pt, spd in pt_dict.items():
                if pt not in accum[pid]:
                    accum[pid][pt] = []
                accum[pid][pt].append(spd)
    career = {}
    for pid, pt_dict in accum.items():
        career[pid] = {pt: round(sum(v) / len(v), 2) for pt, v in pt_dict.items()}
    return career


def _build_rv_baselines_from_df(rv_df: pd.DataFrame, prior_years: list) -> tuple:
    """
    Builds career RV and per-year RV from arsenal stats CSV.
    Returns (career_rv, year_rv_map):
      career_rv  = {player_id: {pitch_type: rv100_avg}}   (averaged over prior years)
      year_rv_map = {year: {player_id: {pitch_type: rv100}}}
    """
    career_accum = {}
    year_rv_map  = {}

    for year in prior_years:
        yr_df = rv_df[rv_df["year"] == year].copy()
        yr_rv = {}

        yr_df["player_id"] = pd.to_numeric(yr_df["player_id"], errors="coerce")
        yr_df = yr_df.dropna(subset=["player_id", "pitch_type", "run_value_per_100"])
        yr_df = yr_df[yr_df["pa"] >= MIN_RV_PA]
        yr_df["player_id"] = yr_df["player_id"].astype(int)

        for _, row in yr_df.iterrows():
            pid = int(row["player_id"])
            pt  = row["pitch_type"]
            rv  = float(row["run_value_per_100"])
            if math.isnan(rv):
                continue
            yr_rv.setdefault(pid, {})[pt] = round(rv, 3)

            career_accum.setdefault(pid, {}).setdefault(pt, []).append(rv)

        year_rv_map[year] = yr_rv

    career_rv = {
        pid: {pt: round(sum(v) / len(v), 3) for pt, v in pt_dict.items()}
        for pid, pt_dict in career_accum.items()
    }
    return career_rv, year_rv_map


def compute_pitch_mix_signals_for_year_v2(
    year: int, all_parquets: dict, rv_df: pd.DataFrame
) -> dict:
    """
    Version G pitch mix signals:
      Phase 1: abandonment + effectiveness (from SwStr%)
      Phase 2: per-pitch velo delta + RV delta
    Career baseline = all years < target year.
    """
    prior_years = sorted(y for y in all_parquets if y < year)
    if not prior_years:
        return {}

    # Phase 1 baselines
    career_pm = _build_career_baseline([all_parquets[y] for y in prior_years])
    curr_pm   = _compute_pitch_mix_from_parquet(all_parquets[year])

    # Phase 2 baselines
    career_velo = _build_career_velo([all_parquets[y] for y in prior_years])
    curr_velo   = _compute_pitch_velo_from_parquet(all_parquets[year])

    prior_rv_years = [y for y in prior_years if y in rv_df["year"].values]
    career_rv, _ = _build_rv_baselines_from_df(rv_df, prior_rv_years)
    curr_rv_rows  = rv_df[rv_df["year"] == year].copy()
    curr_rv_rows["player_id"] = pd.to_numeric(curr_rv_rows["player_id"], errors="coerce")
    curr_rv_rows  = curr_rv_rows.dropna(subset=["player_id", "run_value_per_100"])
    curr_rv_rows["player_id"] = curr_rv_rows["player_id"].astype(int)
    curr_rv: dict = {}
    for _, row in curr_rv_rows.iterrows():
        pid = int(row["player_id"])
        pt  = row["pitch_type"]
        rv  = float(row["run_value_per_100"])
        if not math.isnan(rv):
            curr_rv.setdefault(pid, {})[pt] = round(rv, 3)

    signals = {}
    for pid in set(career_pm.keys()) & set(curr_pm.keys()):
        c_pm = career_pm[pid]
        n_pm = curr_pm[pid]["by_type"]
        if not c_pm:
            continue

        best_pt           = max(c_pm, key=lambda pt: c_pm[pt]["career_swstr"])
        best_career_swstr = c_pm[best_pt]["career_swstr"]

        best_usage_delta = None
        best_swstr_delta = None
        if best_pt in n_pm:
            best_usage_delta = n_pm[best_pt]["usage"] - c_pm[best_pt]["career_usage"]
            best_swstr_delta = n_pm[best_pt]["swstr"] - c_pm[best_pt]["career_swstr"]

        # Phase 1 flags
        abandonment_flag = (
            best_pt in n_pm
            and best_career_swstr > ABANDON_SWSTR_FLOOR
            and best_usage_delta is not None
            and best_usage_delta < -ABANDON_USAGE_THRESH
        )
        curr_best_swstr = n_pm.get(best_pt, {}).get("swstr", 0.0)
        effectiveness_flag = (
            best_swstr_delta is not None
            and best_swstr_delta > EFFECT_SWSTR_DELTA
            and curr_best_swstr >= EFFECT_SWSTR_FLOOR
        )

        # Phase 2: velo flags
        velo_drop_flag = False
        velo_gain_flag = False
        c_velo = career_velo.get(pid, {})
        n_velo = curr_velo.get(pid, {})
        if best_pt in c_velo and best_pt in n_velo:
            vd = n_velo[best_pt] - c_velo[best_pt]
            if vd < -VELO_DROP_THRESH:
                velo_drop_flag = True
            elif vd >= VELO_GAIN_THRESH:
                velo_gain_flag = True

        # Phase 2: RV flags
        rv_degrade_flag = False
        rv_improve_flag = False
        c_rv_pid = career_rv.get(pid, {})
        n_rv_pid = curr_rv.get(pid, {})
        if best_pt in c_rv_pid and best_pt in n_rv_pid:
            rv_delta = n_rv_pid[best_pt] - c_rv_pid[best_pt]
            if rv_delta > RV_DEGRADE_THRESH:
                rv_degrade_flag = True
            elif rv_delta < -RV_IMPROVE_THRESH:
                rv_improve_flag = True

        signals[pid] = {
            "abandonment_flag":   abandonment_flag,
            "effectiveness_flag": effectiveness_flag,
            "velo_drop_flag":     velo_drop_flag,
            "velo_gain_flag":     velo_gain_flag,
            "rv_degrade_flag":    rv_degrade_flag,
            "rv_improve_flag":    rv_improve_flag,
        }
    return signals


# ── Load all April parquets upfront ──────────────────────────────────────────
def _load_all_april_parquets() -> dict:
    result = {}
    for year in P_YEARS:
        path = CACHE_DIR / f"pitcher_statcast_april_{year}.parquet"
        if path.exists():
            result[year] = pd.read_parquet(path)
            print(f"  Loaded April {year} parquet: {len(result[year]):,} pitches, "
                  f"{result[year]['pitcher'].nunique()} pitchers")
    return result


# ── Run year ──────────────────────────────────────────────────────────────────
def run_year(year: int, all_parquets: dict, rv_df: pd.DataFrame = None):
    apr_cache = CACHE_DIR / f"pitcher_statcast_april_{year}.parquet"
    out_cache = CACHE_DIR / f"pitcher_statcast_mayjuly_{year}.parquet"
    if not apr_cache.exists() or not out_cache.exists():
        print(f"  {year}: missing parquet(s) — skip")
        return None

    apr_sc_full = _load_full_parquet(apr_cache)
    apr_sc = load_or_fetch(apr_cache, f"{year}-04-01", f"{year}-04-30", f"April {year}")
    out_sc = load_or_fetch(out_cache, f"{year}-05-01", f"{year}-07-31", f"May-Jul {year}")

    if apr_sc.empty or out_sc.empty:
        return None

    apr_starts = per_start_stats(apr_sc)
    apr_stats  = pitcher_stats(apr_sc, apr_starts)
    out_stats  = pitcher_stats(out_sc, per_start_stats(out_sc))

    apr_stats = apr_stats[apr_stats["ip"] >= MIN_APRIL_IP].copy()
    out_stats = out_stats[out_stats["ip"] >= MIN_OUTCOME_IP].copy()

    vol_df = compute_volatility(apr_starts) if not apr_starts.empty else pd.DataFrame()

    col_count = len(apr_sc_full.columns)
    if col_count >= 100:
        extra = compute_extra_stats(apr_sc_full)
    else:
        extra = pd.DataFrame()

    sig = apr_stats.copy()
    sig["era_fip_gap"] = sig["era"] - sig["fip"]
    sig["career_hh_allowed"] = sig["pitcher"].map(career_hh_p)
    sig["career_barrel_allowed"] = sig["pitcher"].map(career_barrel_p)

    if not vol_df.empty:
        sig = sig.merge(vol_df[["pitcher", "volatility_flag"]], on="pitcher", how="left")
        sig["volatility_flag"] = sig["volatility_flag"].fillna(False)
    else:
        sig["volatility_flag"] = False

    sig = _add_composite_scores(sig, extra, year)

    # Volatility dampen on composite buy signals
    for col in ["composite_b", "composite_c"]:
        mask = sig["volatility_flag"] & (sig[col] > 0)
        sig.loc[mask, col] = (sig.loc[mask, col] * VOL_DAMP).round(4)

    if "xwoba_allowed" in sig.columns:
        sig["april_xera"] = (
            XWOBA_TO_XERA_COEF * sig["xwoba_allowed"] + XWOBA_TO_XERA_INTERCEPT
        ).round(3)
    else:
        sig["april_xera"] = float("nan")
    sig["career_ip_g"] = sig["pitcher"].map(_CAREER_IP).fillna(0.0)
    sig["xera_g"] = sig["april_xera"]

    # ── Version E: production-aligned ────────────────────────────────────────
    def _e_prescore(row):
        bs  = float(row.get("_buy_d_raw") or 0.0)
        ss  = float(row.get("_sell_d_raw") or 0.0)
        ip  = float(row.get("ip") or 0.0)
        era = float(row.get("era") or 0.0)
        fip_r = float(row.get("fip") or float("nan"))
        if bs > 0 and ss >= 0:
            dominant_buy = bs >= 1.50
            if ip < E_MIN_BUY_IP and not dominant_buy:
                return "NEUTRAL"
            if ip < E_MIN_BUY_IP and not pd.isna(fip_r) and fip_r < 1.50:
                return "NEUTRAL"
            xera_r    = row.get("xera_g",    float("nan"))
            swstr_r   = row.get("swstr_rate", float("nan"))
            gb_r      = row.get("gb_pct",     float("nan"))
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

    sig["signal_e"] = sig.apply(_e_prescore, axis=1)

    # ── Version F: Version E + Phase 1 pitch mix modifier ────────────────────
    pm_signals_f = compute_pitch_mix_signals_for_year(year, all_parquets)
    n_covered    = sum(1 for pid in sig["pitcher"] if int(pid) in pm_signals_f)
    n_aband      = sum(1 for v in pm_signals_f.values() if v["abandonment_flag"])
    n_effect     = sum(1 for v in pm_signals_f.values() if v["effectiveness_flag"])

    orig_buy  = sig.get("_buy_d_raw",  pd.Series(dtype=float)).copy()
    orig_sell = sig.get("_sell_d_raw", pd.Series(dtype=float)).copy()

    def _apply_pm_v1(row):
        pid = int(row["pitcher"])
        pm  = pm_signals_f.get(pid)
        bd  = float(row.get("_buy_d_raw") or 0.0)
        sd  = float(row.get("_sell_d_raw") or 0.0)
        if pm is None:
            return bd, sd
        if pm["abandonment_flag"]:
            if bd > 0:
                bd = round(bd * 0.90, 4)
            elif sd < 0:
                sd = round(sd * 1.10, 4)
        if pm["effectiveness_flag"]:
            if bd > 0:
                bd = round(bd * 1.10, 4)
        return bd, sd

    pm_f = sig.apply(_apply_pm_v1, axis=1)
    sig["_buy_d_raw"]  = pm_f.apply(lambda t: t[0])
    sig["_sell_d_raw"] = pm_f.apply(lambda t: t[1])
    sig["signal_f"] = sig.apply(_e_prescore, axis=1)

    # ── Version G: Version E + Phase 2 (all 6 flags) ─────────────────────────
    sig["_buy_d_raw"]  = orig_buy
    sig["_sell_d_raw"] = orig_sell

    pm_signals_g = (
        compute_pitch_mix_signals_for_year_v2(year, all_parquets, rv_df)
        if rv_df is not None else {}
    )
    n_covered_g  = sum(1 for pid in sig["pitcher"] if int(pid) in pm_signals_g)
    n_vdrop      = sum(1 for v in pm_signals_g.values() if v["velo_drop_flag"])
    n_vgain      = sum(1 for v in pm_signals_g.values() if v["velo_gain_flag"])
    n_rvdeg      = sum(1 for v in pm_signals_g.values() if v["rv_degrade_flag"])
    n_rvimp      = sum(1 for v in pm_signals_g.values() if v["rv_improve_flag"])

    def _apply_pm_v2(row):
        pid = int(row["pitcher"])
        pm  = pm_signals_g.get(pid)
        bd  = float(row.get("_buy_d_raw") or 0.0)
        sd  = float(row.get("_sell_d_raw") or 0.0)
        if pm is None:
            return bd, sd
        bearish = ["abandonment_flag", "velo_drop_flag", "rv_degrade_flag"]
        bullish = ["effectiveness_flag", "velo_gain_flag"]
        for flag in bearish:
            if pm.get(flag):
                if bd > 0:
                    bd = round(bd * 0.90, 4)
                elif sd < 0:
                    sd = round(sd * 1.10, 4)
        for flag in bullish:
            if pm.get(flag) and bd > 0:
                bd = round(bd * 1.10, 4)
        if pm.get("rv_improve_flag") and bd > 0:
            bd = round(bd * 1.05, 4)
        return bd, sd

    pm_g = sig.apply(_apply_pm_v2, axis=1)
    sig["_buy_d_raw"]  = pm_g.apply(lambda t: t[0])
    sig["_sell_d_raw"] = pm_g.apply(lambda t: t[1])
    sig["signal_g"] = sig.apply(_e_prescore, axis=1)

    # Restore original scores
    sig["_buy_d_raw"]  = orig_buy
    sig["_sell_d_raw"] = orig_sell

    # Save Phase 2 bearish flags for Version H sensitivity sweep
    for _flag in ["abandonment_flag", "velo_drop_flag", "rv_degrade_flag"]:
        sig[_flag] = sig["pitcher"].apply(
            lambda pid, f=_flag: bool(pm_signals_g.get(int(pid), {}).get(f, False))
        )

    # Keep xera_g + career_ip_g through merge (needed by _reclassify_h)
    sig.drop(columns=["april_xera"], inplace=True, errors="ignore")

    merged = sig.merge(
        out_stats[["pitcher", "era", "ip"]].rename(
            columns={"era": "outcome_era", "ip": "outcome_ip"}),
        on="pitcher", how="inner"
    )
    merged["era_change"] = merged["outcome_era"] - merged["era"]
    merged["outcome"] = np.where(
        merged["era_change"] <= -ERA_FLAT, "IMPROVED",
        np.where(merged["era_change"] >= ERA_FLAT, "DECLINED", "FLAT")
    )
    merged["year"] = year
    print(f"  {year}: {len(merged)} pitchers | F: {n_covered} covered ({n_aband} aband, {n_effect} effect) "
          f"| G: {n_covered_g} covered ({n_vdrop} vdrop, {n_vgain} vgain, {n_rvdeg} rvdeg, {n_rvimp} rvimp)")
    return merged


# ── Version H: additive modifier architecture (mirrors hitter Version D) ──────
BEARISH_FLAGS_H = ["abandonment_flag", "velo_drop_flag", "rv_degrade_flag"]
P_MAX_COMBINED_PEN = 0.040


def _overall_acc_df(df, sig_col):
    sub = df[df[sig_col].isin(SIGNAL_MAP) & (df["outcome"] != "FLAT")].copy()
    if len(sub) == 0:
        return float("nan"), 0
    correct = sub.apply(lambda r: r["outcome"] == SIGNAL_MAP.get(r[sig_col], ""), axis=1)
    return correct.mean(), len(sub)


def _reclassify_h(row, penalties):
    """Recompute buy signal using additive penalties instead of multiplicative modifiers."""
    bs = float(row.get("_buy_d_raw") or 0.0)
    ss = float(row.get("_sell_d_raw") or 0.0)
    if not (bs > 0 and ss >= 0):
        return row.get("signal_e", "NEUTRAL")
    ip       = float(row.get("ip")         or 0.0)
    era      = float(row.get("era")        or 0.0)
    fip_r    = float(row.get("fip")        or float("nan"))
    xera_r   = row.get("xera_g",           float("nan"))
    swstr_r  = row.get("swstr_rate",        float("nan"))
    gb_r     = row.get("gb_pct",            float("nan"))
    career_ip = float(row.get("career_ip_g", 0.0))
    dominant_buy = bs >= 1.50
    if ip < E_MIN_BUY_IP and not dominant_buy:
        return "NEUTRAL"
    if ip < E_MIN_BUY_IP and not pd.isna(fip_r) and fip_r < 1.50:
        return "NEUTRAL"
    if not _is_buy_qualified(fip_r, xera_r, swstr_r, career_ip, gb_r):
        return "NEUTRAL"
    if era < E_ERA_FLOOR:
        return "NEUTRAL"
    xera_f = float(xera_r) if (xera_r is not None and not pd.isna(xera_r)) else float("nan")
    if (not dominant_buy and not math.isnan(xera_f) and not pd.isna(fip_r)
            and abs(fip_r - xera_f) > 1.50 and xera_f > 4.50
            and float(row.get("era_fip_gap", 0.0)) < 2.50):
        return "NEUTRAL"
    penalty = sum(penalties.get(f, 0.0) for f in BEARISH_FLAGS_H if row.get(f, False))
    penalty = min(penalty, P_MAX_COMBINED_PEN)
    scaled  = bs * _april_conf_scale(ip) - penalty
    if scaled >= E_BUY_LOW_LS:
        if era < E_BUY_LOW_ERA_FLOOR:
            return "NEUTRAL"
        return "BUY_LOW"
    if scaled >= E_SLIGHT_BUY_LS:
        if era < E_SLIGHT_BUY_ERA_FLOOR:
            return "NEUTRAL"
        return "SLIGHT_BUY"
    return "NEUTRAL"


def sweep_penalties_pitcher(train_df):
    """Sweep each bearish flag penalty 0.002–0.020; return best per-flag penalties."""
    steps   = [round(i * 0.002, 3) for i in range(1, 11)]
    e_acc, e_n = _overall_acc_df(train_df, "signal_e")
    print("\n" + "=" * 70)
    print("VERSION H — PITCHER ADDITIVE PENALTY SWEEP (TRAIN 2022-2024)")
    print("=" * 70)
    print(f"Baseline E: {e_acc*100:.1f}%  (n={e_n})\n")
    print(f"{'Flag':<25} | {'Best Pen':>8} | {'Acc':>8} | {'ΔvE':>8}")
    print("-" * 58)
    best = {}
    for flag in BEARISH_FLAGS_H:
        best_pen = 0.0
        best_acc = e_acc
        for pen in steps:
            tmp = train_df.apply(lambda r: _reclassify_h(r, {flag: pen}), axis=1)
            sub = train_df.copy()
            sub["_h_tmp"] = tmp
            acc, _ = _overall_acc_df(sub, "_h_tmp")
            if not math.isnan(acc) and acc > best_acc:
                best_acc = acc
                best_pen = pen
        best[flag] = best_pen
        delta = (best_acc - e_acc) * 100 if not math.isnan(best_acc) else float("nan")
        print(f"{flag:<25} | {best_pen:>8.3f} | {best_acc*100:>7.1f}% | {delta:>+7.1f}pp")
    tmp_c = train_df.apply(lambda r: _reclassify_h(r, best), axis=1)
    sub_c = train_df.copy()
    sub_c["_h_comb"] = tmp_c
    acc_c, n_c = _overall_acc_df(sub_c, "_h_comb")
    print("-" * 58)
    print(f"{'Combined':<25} | {'':>8} | {acc_c*100:>7.1f}% | "
          f"{(acc_c - e_acc)*100:>+7.1f}pp  (n={n_c})")
    print("=" * 70)
    return best


def add_signal_h(all_df, penalties):
    all_df = all_df.copy()
    all_df["signal_h"] = all_df.apply(lambda r: _reclassify_h(r, penalties), axis=1)
    return all_df


def print_h_comparison(all_df, best_penalties):
    if "signal_h" not in all_df.columns:
        return
    TRAIN_YEARS = [2022, 2023, 2024]
    OOS_YEAR    = 2025
    train_df = all_df[all_df["year"].isin(TRAIN_YEARS)]
    oos_df   = all_df[all_df["year"] == OOS_YEAR]
    tier_labels = {"BUY_LOW": "Buy Low", "SLIGHT_BUY": "Slight Buy",
                   "SLIGHT_SELL": "Slight Sell", "SELL_HIGH": "Sell High"}

    def fmt(acc, n):
        return f"{acc*100:.1f}% (n={n})" if not math.isnan(acc) else "—"
    def fmt_d(a, b):
        return f"{(b-a)*100:+.1f}pp" if not (math.isnan(a) or math.isnan(b)) else "—"

    print("\n" + "=" * 115)
    print("PITCHER VERSION H — ADDITIVE vs E (baseline) vs G (multiplicative)")
    print("=" * 115)
    hdr = (f"\n{'Signal':<14} | {'E Train':>14} | {'G Train':>14} | {'H Train':>14} | "
           f"{'ΔGE Tr':>7} | {'ΔHE Tr':>7} | "
           f"{'E OOS':>12} | {'G OOS':>12} | {'H OOS':>12} | {'ΔHE OOS':>8}")
    print(hdr)
    print("-" * 115)
    for tier, label in tier_labels.items():
        ae_tr, ne_tr = _acc_cell(train_df, "signal_e", tier, TRAIN_YEARS)
        ag_tr, ng_tr = _acc_cell(train_df, "signal_g", tier, TRAIN_YEARS)
        ah_tr, nh_tr = _acc_cell(train_df, "signal_h", tier, TRAIN_YEARS)
        ae_oo, ne_oo = _acc_cell(oos_df,   "signal_e", tier, [OOS_YEAR])
        ag_oo, ng_oo = _acc_cell(oos_df,   "signal_g", tier, [OOS_YEAR])
        ah_oo, nh_oo = _acc_cell(oos_df,   "signal_h", tier, [OOS_YEAR])
        print(f"{label:<14} | {fmt(ae_tr,ne_tr):>14} | {fmt(ag_tr,ng_tr):>14} | "
              f"{fmt(ah_tr,nh_tr):>14} | {fmt_d(ae_tr,ag_tr):>7} | {fmt_d(ae_tr,ah_tr):>7} | "
              f"{fmt(ae_oo,ne_oo):>12} | {fmt(ag_oo,ng_oo):>12} | {fmt(ah_oo,nh_oo):>12} | "
              f"{fmt_d(ae_oo,ah_oo):>8}")
    oe_tr, ne_tr = _overall_acc_df(train_df, "signal_e")
    og_tr, ng_tr = _overall_acc_df(train_df, "signal_g")
    oh_tr, nh_tr = _overall_acc_df(train_df, "signal_h")
    oe_oo, ne_oo = _overall_acc_df(oos_df,   "signal_e")
    og_oo, ng_oo = _overall_acc_df(oos_df,   "signal_g")
    oh_oo, nh_oo = _overall_acc_df(oos_df,   "signal_h")
    print("-" * 115)
    print(f"{'Overall':<14} | {fmt(oe_tr,ne_tr):>14} | {fmt(og_tr,ng_tr):>14} | "
          f"{fmt(oh_tr,nh_tr):>14} | {fmt_d(oe_tr,og_tr):>7} | {fmt_d(oe_tr,oh_tr):>7} | "
          f"{fmt(oe_oo,ne_oo):>12} | {fmt(og_oo,ng_oo):>12} | {fmt(oh_oo,nh_oo):>12} | "
          f"{fmt_d(oe_oo,oh_oo):>8}")
    oos_guard = math.isnan(oh_oo) or oh_oo >= oe_oo - 0.005
    trained_better = not math.isnan(oh_tr) and oh_tr > oe_tr + 0.001
    print(f"\n2025 OOS guard rail (H must not hurt vs E): {'PASS ✓' if oos_guard else 'FAIL ✗'}")
    verdict = ("ADOPT" if (trained_better and oos_guard) else "NEUTRAL")
    print(f"VERDICT: {verdict}")
    print(f"Calibrated penalties: {best_penalties}")
    print("=" * 115)


def _acc_cell(df, sig_col, tier, years):
    sub = df[df[sig_col] == tier]
    sub_eval = sub[sub["outcome"] != "FLAT"]
    if len(sub_eval) == 0:
        return float("nan"), 0
    expected = SIGNAL_MAP[tier]
    return (sub_eval["outcome"] == expected).sum() / len(sub_eval), len(sub_eval)


def print_comparison(all_df: pd.DataFrame):
    TRAIN_YEARS = [2022, 2023, 2024]
    OOS_YEAR    = 2025
    HAS_G       = "signal_g" in all_df.columns

    train_df = all_df[all_df["year"].isin(TRAIN_YEARS)]
    oos_df   = all_df[all_df["year"] == OOS_YEAR]

    tier_labels = {
        "BUY_LOW":     "Buy Low",
        "SLIGHT_BUY":  "Slight Buy",
        "SLIGHT_SELL": "Slight Sell",
        "SELL_HIGH":   "Sell High",
    }

    def fmt(acc, n):
        return f"{acc*100:.1f}% (n={n})" if not math.isnan(acc) else "—"
    def fmt_delta(a, b):
        if math.isnan(a) or math.isnan(b):
            return "—"
        return f"{(b-a)*100:+.1f}pp"
    def overall(df, sig_col):
        sub = df[df[sig_col].isin(SIGNAL_MAP) & (df["outcome"] != "FLAT")].copy()
        if len(sub) == 0:
            return float("nan"), 0
        sub["correct"] = sub.apply(lambda r: r["outcome"] == SIGNAL_MAP.get(r[sig_col], ""), axis=1)
        return sub["correct"].mean(), len(sub)

    # ── E vs F vs G table ──────────────────────────────────────────────────
    print("\n" + "=" * 110)
    print("PITCHER BACKTEST — Version E (baseline) vs F (Phase 1) vs G (Phase 2)")
    print("=" * 110)

    if HAS_G:
        hdr = (f"\n{'Signal':<14} | {'E Train':>14} | {'F Train':>14} | {'ΔEF Tr':>7} | "
               f"{'G Train':>14} | {'ΔEG Tr':>7} | "
               f"{'E OOS':>12} | {'F OOS':>12} | {'ΔEF OOS':>8} | {'G OOS':>12} | {'ΔEG OOS':>8}")
        print(hdr)
        print("-" * 130)
    else:
        hdr = (f"\n{'Signal':<14} | {'E Train 22-24':>14} | {'F Train 22-24':>14} | "
               f"{'Δ Train':>8} | {'E OOS 2025':>12} | {'F OOS 2025':>12} | {'Δ OOS':>8}")
        print(hdr)
        print("-" * 92)

    for tier, label in tier_labels.items():
        ae_tr, ne_tr = _acc_cell(train_df, "signal_e", tier, TRAIN_YEARS)
        af_tr, nf_tr = _acc_cell(train_df, "signal_f", tier, TRAIN_YEARS)
        ae_oo, ne_oo = _acc_cell(oos_df,   "signal_e", tier, [OOS_YEAR])
        af_oo, nf_oo = _acc_cell(oos_df,   "signal_f", tier, [OOS_YEAR])

        if HAS_G:
            ag_tr, ng_tr = _acc_cell(train_df, "signal_g", tier, TRAIN_YEARS)
            ag_oo, ng_oo = _acc_cell(oos_df,   "signal_g", tier, [OOS_YEAR])
            print(f"{label:<14} | {fmt(ae_tr,ne_tr):>14} | {fmt(af_tr,nf_tr):>14} | {fmt_delta(ae_tr,af_tr):>7} | "
                  f"{fmt(ag_tr,ng_tr):>14} | {fmt_delta(ae_tr,ag_tr):>7} | "
                  f"{fmt(ae_oo,ne_oo):>12} | {fmt(af_oo,nf_oo):>12} | {fmt_delta(ae_oo,af_oo):>8} | "
                  f"{fmt(ag_oo,ng_oo):>12} | {fmt_delta(ae_oo,ag_oo):>8}")
        else:
            print(f"{label:<14} | {fmt(ae_tr,ne_tr):>14} | {fmt(af_tr,nf_tr):>14} | "
                  f"{fmt_delta(ae_tr,af_tr):>8} | {fmt(ae_oo,ne_oo):>12} | "
                  f"{fmt(af_oo,nf_oo):>12} | {fmt_delta(ae_oo,af_oo):>8}")

    oe_tr, ne_tr = overall(train_df, "signal_e")
    of_tr, nf_tr = overall(train_df, "signal_f")
    oe_oo, ne_oo = overall(oos_df,   "signal_e")
    of_oo, nf_oo = overall(oos_df,   "signal_f")

    rtm = RTM_BASELINE
    def vs_rtm(acc):
        return f"{(acc-rtm)*100:+.1f}pp" if not math.isnan(acc) else "—"

    if HAS_G:
        og_tr, ng_tr = overall(train_df, "signal_g")
        og_oo, ng_oo = overall(oos_df,   "signal_g")
        print("-" * 130)
        print(f"{'Overall':<14} | {fmt(oe_tr,ne_tr):>14} | {fmt(of_tr,nf_tr):>14} | {fmt_delta(oe_tr,of_tr):>7} | "
              f"{fmt(og_tr,ng_tr):>14} | {fmt_delta(oe_tr,og_tr):>7} | "
              f"{fmt(oe_oo,ne_oo):>12} | {fmt(of_oo,nf_oo):>12} | {fmt_delta(oe_oo,of_oo):>8} | "
              f"{fmt(og_oo,ng_oo):>12} | {fmt_delta(oe_oo,og_oo):>8}")
        print(f"{'vs RTM':<14} | {vs_rtm(oe_tr):>14} | {vs_rtm(of_tr):>14} | {'':>7} | "
              f"{vs_rtm(og_tr):>14} | {'':>7} | "
              f"{vs_rtm(oe_oo):>12} | {vs_rtm(of_oo):>12} | {'':>8} | "
              f"{vs_rtm(og_oo):>12} | {'':>8}")
        print("=" * 110)
        print(f"\n2025 OOS guard rail (G must not hurt vs E): "
              f"{'PASS ✓' if (math.isnan(og_oo) or og_oo >= oe_oo - 0.005) else 'FAIL ✗'}")
    else:
        print("-" * 92)
        print(f"{'Overall':<14} | {fmt(oe_tr,ne_tr):>14} | {fmt(of_tr,nf_tr):>14} | "
              f"{fmt_delta(oe_tr,of_tr):>8} | {fmt(oe_oo,ne_oo):>12} | "
              f"{fmt(of_oo,nf_oo):>12} | {fmt_delta(oe_oo,of_oo):>8}")
        print(f"{'vs RTM':<14} | {vs_rtm(oe_tr):>14} | {vs_rtm(of_tr):>14} | "
              f"{'':>8} | {vs_rtm(oe_oo):>12} | {vs_rtm(of_oo):>12} | {'':>8}")
        print("=" * 78)
        print(f"\n2025 OOS guard rail (F must not hurt vs E): "
              f"{'PASS ✓' if (math.isnan(of_oo) or of_oo >= oe_oo - 0.005) else 'FAIL ✗'}")

    # Per-year breakdown for highest version
    best_ver = "signal_g" if HAS_G else "signal_f"
    ver_name = "G (Phase 2)" if HAS_G else "F (Phase 1)"
    print(f"\n{'VERSION ' + ver_name + ' — Per-year accuracy':}")
    print(f"\n{'Signal':<14} | {'2022':>14} | {'2023':>14} | {'2024':>14} | "
          f"{'3-Yr Train':>14} | {'2025 OOS':>12}")
    print("-" * 85)
    o_tr_best, n_tr_best = overall(train_df, best_ver)
    o_oo_best, n_oo_best = overall(oos_df,   best_ver)
    for tier, label in tier_labels.items():
        row_cells = [f"{label:<14}"]
        for y in [2022, 2023, 2024]:
            yr_df = all_df[all_df["year"] == y]
            a, n  = _acc_cell(yr_df, best_ver, tier, [y])
            row_cells.append(f"{fmt(a,n):>14}")
        a_tr, n_tr = _acc_cell(train_df, best_ver, tier, TRAIN_YEARS)
        a_oo, n_oo = _acc_cell(oos_df,   best_ver, tier, [OOS_YEAR])
        row_cells.append(f"{fmt(a_tr,n_tr):>14}")
        row_cells.append(f"{fmt(a_oo,n_oo):>12}")
        print(" | ".join(row_cells))
    print("-" * 85)
    ov_cells = [f"{'Overall':<14}"]
    for y in [2022, 2023, 2024]:
        yr_df = all_df[all_df["year"] == y]
        a, n  = overall(yr_df, best_ver)
        ov_cells.append(f"{fmt(a,n):>14}")
    ov_cells.append(f"{fmt(o_tr_best,n_tr_best):>14}")
    ov_cells.append(f"{fmt(o_oo_best,n_oo_best):>12}")
    print(" | ".join(ov_cells))
    print("=" * 78)


def main():
    print("Loading April parquets...")
    all_parquets = _load_all_april_parquets()

    rv_df = None
    if ALL_RV_PATH.exists():
        rv_df = pd.read_csv(ALL_RV_PATH)
        print(f"Loaded arsenal RV CSV: {len(rv_df):,} rows, years {sorted(rv_df['year'].unique())}")
    else:
        print(f"WARNING: {ALL_RV_PATH} not found — Version G will be skipped")

    print("\nRunning backtest...")
    yearly = []
    for year in P_YEARS:
        print(f"\n--- Year {year} ---")
        merged = run_year(year, all_parquets, rv_df)
        if merged is not None:
            yearly.append(merged)

    if not yearly:
        print("No data — exiting")
        return

    all_df = pd.concat(yearly, ignore_index=True)

    # Version H: sensitivity sweep on train years, then apply to all
    train_global = all_df[all_df["year"].isin([2022, 2023, 2024])]
    best_penalties = sweep_penalties_pitcher(train_global)
    all_df = add_signal_h(all_df, best_penalties)

    print_comparison(all_df)
    print_h_comparison(all_df, best_penalties)

    # Save row-level output
    out_path = BASE_DIR / "data" / "backtest_pitcher_pitch_mix.csv"
    save_cols = ["pitcher", "year", "era", "fip", "era_fip_gap", "ip",
                 "signal_e", "signal_f", "outcome", "era_change"]
    if "signal_g" in all_df.columns:
        save_cols.insert(save_cols.index("outcome"), "signal_g")
    if "signal_h" in all_df.columns:
        save_cols.insert(save_cols.index("outcome"), "signal_h")
    all_df[save_cols].to_csv(out_path, index=False)
    print(f"\nRow-level results saved: {out_path}")


if __name__ == "__main__":
    os.chdir(str(_SCRIPT_DIR))
    main()
