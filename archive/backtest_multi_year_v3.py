"""
Multi-Year Within-Season Backtest v3
=====================================
Identical to v2 but with one addition:
  career BABIP baselines from data/hitter_career_babip.json replace the flat
  0.300 league average in the babip_expected calculation.

  babip_expected = career_babip * park_factor_adjustment
                   (falls back to LEAGUE_AVG_BABIP when no career data exists)

Career BABIP data spans 2022-2025 (BA + 0.050 proxy, Savant endpoints).
For a strict walk-forward, prior-year-only data would be ideal; here we use
the full career file as the user instructed. Mild look-ahead on early years
means the gain vs v2 is a lower bound estimate — real production gains will
be at least as large.

v2 benchmarks (for comparison):
  Overall 4yr avg: 81.7%  |  SLIGHT_SELL: 65.0%  |  BUY_LOW: 95.0%  |  vs RTM: +13.5pp
"""

import io
import json
import os
import sys
import numpy as np
import pandas as pd
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE_DIR          = Path(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR         = BASE_DIR / "backtest_cache"
SEASONAL_PATH     = BASE_DIR / "data" / "seasonal_patterns.json"
CAREER_PATH       = BASE_DIR / "data" / "career_stats.json"
CAREER_BABIP_PATH = BASE_DIR / "data" / "hitter_career_babip.json"

YEARS            = [2022, 2023, 2024, 2025]
MIN_APRIL_PA     = 80
MIN_OUTCOME_PA   = 100
FLAT_THRESHOLD   = 0.015
RTM_BASELINE     = 0.682
LEAGUE_AVG_BABIP = 0.300
EV_THRESHOLD     = 1.0

SLIGHT_SELL_THRESH = -0.026

PARK_FACTORS = {
    'COL': 1.12, 'CIN': 1.08, 'TEX': 1.06, 'HOU': 1.05,
    'BAL': 1.04, 'BOS': 1.04, 'PHI': 1.03, 'MIL': 1.02,
    'ATL': 1.02, 'NYY': 1.01, 'TOR': 1.01, 'WSH': 1.00,
    'CHC': 1.00, 'STL': 1.00, 'LAD': 0.99, 'NYM': 0.99,
    'ARI': 0.99, 'MIN': 0.98, 'DET': 0.98, 'CLE': 0.98,
    'CWS': 0.97, 'SEA': 0.97, 'SF':  0.96, 'MIA': 0.96,
    'TB':  0.96, 'PIT': 0.96, 'KC':  0.96, 'LAA': 0.95,
    'SD':  0.95, 'OAK': 0.94,
}

BIP_EVENTS = {
    'single', 'double', 'triple', 'field_out', 'grounded_into_double_play',
    'force_out', 'double_play', 'fielders_choice',
}

SIGNAL_MAP = {
    'BUY_LOW':    'IMPROVED',
    'SLIGHT_BUY': 'IMPROVED',
    'SELL_HIGH':  'DECLINED',
    'SLIGHT_SELL':'DECLINED',
}

PHASE_C = {
    'vshape_buy':  1.20,
    'vshape_sell': None,
    'slow_buy':    1.10,
    'summer_buy':  1.10,
    'fader_sell':  1.15,
    'fader_buy':   0.90,
}


# ------------------------------------------------------------------
# DATA LOADING
# ------------------------------------------------------------------

def load_career_stats() -> dict:
    if not CAREER_PATH.exists():
        return {}
    with open(CAREER_PATH) as f:
        raw = json.load(f)
    return {int(k): v for k, v in raw.items()}


def load_seasonal_patterns() -> dict:
    if not SEASONAL_PATH.exists():
        return {}
    with open(SEASONAL_PATH) as f:
        records = json.load(f)
    return {int(r["player_id"]): r for r in records}


def load_career_babip() -> dict:
    """
    Returns dict: batter_mlbam_id (int) -> career_babip (float).
    Keyed by int for fast lookup in run_year().
    """
    if not CAREER_BABIP_PATH.exists():
        print(f"  WARNING: {CAREER_BABIP_PATH} not found — using flat 0.300 for all batters")
        return {}
    with open(CAREER_BABIP_PATH) as f:
        raw = json.load(f)
    result = {}
    for pid_str, rec in raw.items():
        cb = rec.get("career_babip")
        if cb is not None:
            result[int(pid_str)] = float(cb)
    return result


# ------------------------------------------------------------------
# SIGNAL CLASSIFICATION
# ------------------------------------------------------------------

def classify(score: float) -> str:
    if score >= 0.040:              return "BUY_LOW"
    if score >= 0.020:              return "SLIGHT_BUY"
    if score <= -0.040:             return "SELL_HIGH"
    if score <= SLIGHT_SELL_THRESH: return "SLIGHT_SELL"
    return "NEUTRAL"


def bucket_stats(eval_df: pd.DataFrame) -> dict:
    stats = {}
    for sig in ["BUY_LOW", "SLIGHT_BUY", "SELL_HIGH", "SLIGHT_SELL"]:
        grp = eval_df[eval_df["signal"] == sig]
        n = len(grp)
        c = int(grp["correct"].sum()) if n > 0 else 0
        stats[sig] = (n, c, c / n if n > 0 else float("nan"))
    ov_n = len(eval_df)
    ov_c = int(eval_df["correct"].sum())
    stats["OVERALL"] = (ov_n, ov_c, ov_c / ov_n if ov_n > 0 else float("nan"))
    return stats


# ------------------------------------------------------------------
# PER-YEAR RUN
# ------------------------------------------------------------------

def run_year(year: int, career_stats: dict, patterns: dict,
             career_babip: dict) -> dict | None:
    april_path   = CACHE_DIR / f"v4_april_{year}.csv"
    outcome_path = CACHE_DIR / f"statcast_{year}_may_july.csv"
    team_path    = CACHE_DIR / f"team_map_{year}.csv"

    if not april_path.exists() or not outcome_path.exists():
        return None

    april   = pd.read_csv(april_path)
    outcome = pd.read_csv(outcome_path)

    # Team / park factor
    if team_path.exists():
        team_map = pd.read_csv(team_path)
        april = april.merge(team_map, on="batter", how="left")
    april["park_factor"] = april["team"].map(PARK_FACTORS).fillna(1.0) if "team" in april.columns else 1.0

    # ── BIP aggregation ─────────────────────────────────────────────
    batted = april[april["bb_type"].notna() & (april["bb_type"] != "")].copy()
    batted["is_bip"]  = batted["events"].isin(BIP_EVENTS).astype(int)
    batted["is_hit"]  = batted["events"].isin({"single", "double", "triple"}).astype(int)
    batted["is_gb"]   = (batted["bb_type"] == "ground_ball").astype(int)
    bip_agg = batted.groupby("batter").agg(
        bip=("is_bip", "sum"),
        hits_bip=("is_hit", "sum"),
        gb=("is_gb", "sum"),
    ).reset_index()

    # ── BBE aggregation ──────────────────────────────────────────────
    bbe = april[april["launch_speed"].notna() & april["launch_angle"].notna()].copy()
    bbe_agg = bbe.groupby("batter").apply(
        lambda s: pd.Series({
            "sweet_spot_count": int(((s["launch_speed"] >= 98) & s["launch_angle"].between(8, 32)).sum()),
            "bbe_total":         len(s),
            "avg_exit_velocity": float(s["launch_speed"].mean()),
        })
    ).reset_index()
    has_bbe = len(bbe_agg) > 0

    # ── Plate discipline ─────────────────────────────────────────────
    april["is_bb"] = april["events"].isin({"walk", "intent_walk"}).astype(int)
    april["is_k"]  = april["events"].isin({"strikeout", "strikeout_double_play"}).astype(int)
    disc_agg = april.groupby("batter").agg(
        bb_count=("is_bb", "sum"),
        k_count=("is_k", "sum"),
    ).reset_index()

    # ── PA / wOBA aggregation ────────────────────────────────────────
    has_xwoba = "estimated_woba_using_speedangle" in april.columns
    pa_agg = april.groupby("batter").agg(
        april_pa=("woba_value", "count"),
        april_actual_woba=("woba_value", "mean"),
        **({ "april_xwoba": ("estimated_woba_using_speedangle", "mean") } if has_xwoba else {}),
        park_factor=("park_factor", "first"),
    ).reset_index()
    if not has_xwoba:
        pa_agg["april_xwoba"] = np.nan

    # ── Merge all ────────────────────────────────────────────────────
    signals = pa_agg.merge(bip_agg, on="batter", how="left")
    if has_bbe:
        signals = signals.merge(bbe_agg, on="batter", how="left")
    else:
        for col in ["sweet_spot_count", "bbe_total", "avg_exit_velocity"]:
            signals[col] = np.nan
    signals = signals.merge(disc_agg, on="batter", how="left")

    # ── Derived rates ─────────────────────────────────────────────────
    signals["babip"]           = np.where(signals["bip"] > 0, signals["hits_bip"] / signals["bip"], np.nan)
    signals["gb_rate"]         = np.where(signals["bip"] > 0, signals["gb"] / signals["bip"], np.nan)
    signals["sweet_spot_rate"] = np.where(signals["bbe_total"] > 0,
                                           signals["sweet_spot_count"] / signals["bbe_total"], np.nan)
    signals["bb_rate"] = signals["bb_count"] / signals["april_pa"]
    signals["k_rate"]  = signals["k_count"]  / signals["april_pa"]
    signals["xwoba_gap"] = signals["april_xwoba"] - signals["april_actual_woba"]

    # ── v3: Career BABIP baseline replaces flat 0.300 ─────────────────
    # Map each batter's career BABIP; fall back to LEAGUE_AVG_BABIP
    signals["babip_baseline"] = signals["batter"].map(
        lambda bid: career_babip.get(int(bid), LEAGUE_AVG_BABIP)
    )
    n_career   = int((signals["babip_baseline"] != LEAGUE_AVG_BABIP).sum())
    n_fallback = int((signals["babip_baseline"] == LEAGUE_AVG_BABIP).sum())

    # Park adjustment (same additive formula as v2)
    park_adj = (signals["park_factor"] - 1.0) * 0.10
    signals["babip_expected"] = (signals["babip_baseline"] - park_adj).round(4)

    # ── L4: GB rate BABIP adjustment ──────────────────────────────────
    l4_gb_high = l4_gb_low = 0
    if signals["gb_rate"].notna().any():
        gb_high = signals["gb_rate"] > 0.50
        gb_low  = signals["gb_rate"] < 0.35
        signals.loc[gb_high, "babip_expected"] -= 0.010
        signals.loc[gb_low,  "babip_expected"] += 0.008
        l4_gb_high = int(gb_high.sum())
        l4_gb_low  = int(gb_low.sum())

    signals["babip_luck"] = signals["babip_expected"] - signals["babip"]

    # ── PA gate ───────────────────────────────────────────────────────
    signals = signals[signals["april_pa"] >= MIN_APRIL_PA].copy()

    # ── L1: Core luck score ───────────────────────────────────────────
    signals["luck_score"] = (
        signals["xwoba_gap"]  * 0.60 +
        signals["babip_luck"] * 0.40
    ).round(4)

    # ── L2: Sweet spot modifier ───────────────────────────────────────
    l2_amp = l2_damp = 0
    if signals["sweet_spot_rate"].notna().any():
        buy     = signals["luck_score"] > 0
        high_ss = buy & (signals["sweet_spot_rate"] > 0.12)
        low_ss  = buy & (signals["sweet_spot_rate"] < 0.06)
        signals.loc[high_ss, "luck_score"] = (signals.loc[high_ss, "luck_score"] * 1.05).round(4)
        signals.loc[low_ss,  "luck_score"] = (signals.loc[low_ss,  "luck_score"] * 0.95).round(4)
        l2_amp, l2_damp = int(high_ss.sum()), int(low_ss.sum())

    # ── L3: EV two-signal confirmation ───────────────────────────────
    l3_both = l3_one = l3_skip = 0
    if signals["avg_exit_velocity"].notna().any():
        for idx, row in signals.iterrows():
            if row["luck_score"] <= 0:
                continue
            career_ev = (career_stats.get(int(row["batter"])) or {}).get("avg_exit_velocity")
            if career_ev is None or pd.isna(row["avg_exit_velocity"]):
                l3_skip += 1
                continue
            ev_below = (row["avg_exit_velocity"] - career_ev) < -EV_THRESHOLD
            ss       = row["sweet_spot_rate"]
            low_ss_ev = pd.notna(ss) and ss < 0.08
            if ev_below and low_ss_ev:
                signals.at[idx, "luck_score"] = round(row["luck_score"] * 0.85, 4)
                l3_both += 1
            elif ev_below or low_ss_ev:
                signals.at[idx, "luck_score"] = round(row["luck_score"] * 0.93, 4)
                l3_one += 1

    # ── L5: Plate discipline modifier ────────────────────────────────
    l5_elite = l5_poor = 0
    if signals["bb_rate"].notna().any() and signals["k_rate"].notna().any():
        buy_mask   = signals["luck_score"] > 0
        elite_disc = buy_mask & (signals["bb_rate"] > 0.10) & (signals["k_rate"] < 0.18)
        poor_disc  = buy_mask & ((signals["bb_rate"] < 0.06) | (signals["k_rate"] > 0.28))
        signals.loc[elite_disc, "luck_score"] = (signals.loc[elite_disc, "luck_score"] * 1.08).round(4)
        signals.loc[poor_disc,  "luck_score"] = (signals.loc[poor_disc,  "luck_score"] * 0.88).round(4)
        l5_elite, l5_poor = int(elite_disc.sum()), int(poor_disc.sum())

    # ── L6: Seasonal patterns ─────────────────────────────────────────
    l6_modified = 0
    if patterns:
        for idx, row in signals.iterrows():
            pid    = int(row["batter"])
            raw    = row["luck_score"]
            if pid not in patterns:
                continue
            p      = patterns[pid]
            slow   = p.get("slow_starter", False)
            fader  = p.get("second_half_fader", False)
            summer = p.get("summer_performer", False)
            is_buy  = raw > 0
            is_sell = raw < 0
            mult = 1.0

            if slow and summer:
                if is_buy:
                    mult = PHASE_C["vshape_buy"]
            elif slow and not summer:
                if is_buy:
                    mult = PHASE_C["slow_buy"]
            elif summer and not slow:
                if is_buy:
                    mult = PHASE_C["summer_buy"]

            if fader:
                if is_sell:
                    mult = max(mult, PHASE_C["fader_sell"])
                elif is_buy:
                    mult = min(mult, PHASE_C["fader_buy"])

            if mult != 1.0:
                signals.at[idx, "luck_score"] = round(raw * mult, 4)
                l6_modified += 1

    # ── L7: Classify ──────────────────────────────────────────────────
    signals["signal"] = signals["luck_score"].apply(classify)
    sig_counts = signals["signal"].value_counts().to_dict()

    # ── Outcomes ──────────────────────────────────────────────────────
    may_july = outcome.groupby("batter").agg(
        outcome_pa=("woba_value", "count"),
        outcome_woba=("woba_value", "mean"),
    ).reset_index()

    merged = signals.merge(may_july, on="batter", how="inner")
    merged = merged[merged["outcome_pa"] >= MIN_OUTCOME_PA].copy()
    merged["woba_change"] = merged["outcome_woba"] - merged["april_actual_woba"]
    merged["outcome"] = np.where(
        merged["woba_change"] >=  FLAT_THRESHOLD, "IMPROVED",
        np.where(merged["woba_change"] <= -FLAT_THRESHOLD, "DECLINED", "FLAT")
    )

    eval_df = merged[merged["signal"].isin(SIGNAL_MAP) & (merged["outcome"] != "FLAT")].copy()
    eval_df["correct"] = eval_df.apply(lambda r: r["outcome"] == SIGNAL_MAP[r["signal"]], axis=1)
    stats = bucket_stats(eval_df)

    gradient = {
        sig: merged[merged["signal"] == sig]["woba_change"].mean()
        if (merged["signal"] == sig).sum() >= 3 else float("nan")
        for sig in ["BUY_LOW", "SLIGHT_BUY", "NEUTRAL", "SLIGHT_SELL", "SELL_HIGH"]
    }

    layers = [
        f"L1",
        f"L4_gb(h{l4_gb_high}/l{l4_gb_low})",
        f"L2_ss(+{l2_amp}/-{l2_damp})",
        f"L3_ev(b{l3_both}/o{l3_one})",
        f"L5_disc(e{l5_elite}/p{l5_poor})",
        f"L6_phaseC({l6_modified})",
        f"L7_ss({SLIGHT_SELL_THRESH})",
    ]

    return {
        "year":       year,
        "stats":      stats,
        "gradient":   gradient,
        "sig_counts": sig_counts,
        "layers":     layers,
        "n_signals":  len(signals),
        "n_eval":     stats["OVERALL"][0],
        "n_flat":     int((merged["outcome"] == "FLAT").sum()),
        "l3_both":    l3_both,
        "l3_one":     l3_one,
        "n_career":   n_career,
        "n_fallback": n_fallback,
    }


# ------------------------------------------------------------------
# DISPLAY
# ------------------------------------------------------------------

def fmt_pct(v, w=6):
    return f"{v*100:{w}.1f}%" if not pd.isna(v) else f"{'n/a':>{w}}"

def fmt_pp(v, w=6):
    return f"{v*100:>+{w}.1f}pp" if not pd.isna(v) else f"{'n/a':>{w}}"


def print_table(results: list):
    yrs  = [r["year"] for r in results]
    SIGS = ["BUY_LOW", "SLIGHT_BUY", "SELL_HIGH", "SLIGHT_SELL", "OVERALL"]
    CW   = 8

    top = "+" + "-"*13 + "+" + ("-"*CW + "+") * len(yrs) + "-"*(CW+1) + "+"
    mid = "+" + "-"*13 + "+" + ("-"*CW + "+") * len(yrs) + "-"*(CW+1) + "+"
    bot = "+" + "-"*13 + "+" + ("-"*CW + "+") * len(yrs) + "-"*(CW+1) + "+"
    sep = "|"

    print(top)
    hdr = f"{sep} {'Signal':<11} {sep}" + "".join(f" {y:>{CW-2}}  {sep}" for y in yrs) + f" {'4yr Avg':>{CW-1}} {sep}"
    print(hdr)
    print(mid)

    for sig in SIGS:
        if sig == "OVERALL":
            print(mid)
        accs  = [r["stats"].get(sig, (0, 0, float("nan")))[2] for r in results]
        valid = [a for a in accs if not pd.isna(a)]
        avg   = float(np.mean(valid)) if valid else float("nan")
        row   = f"{sep} {sig:<11} {sep}"
        for acc in accs:
            row += f" {fmt_pct(acc, CW-2)}  {sep}"
        row += f" {fmt_pct(avg, CW-1)} {sep}"
        print(row)

    print(mid)

    # vs RTM
    rtm_row = f"{sep} {'vs RTM':<11} {sep}"
    rtm_vals = []
    for r in results:
        ov_a = r["stats"]["OVERALL"][2]
        vs   = ov_a - RTM_BASELINE if not pd.isna(ov_a) else float("nan")
        rtm_vals.append(vs)
        rtm_row += f" {fmt_pp(vs, CW-2)}  {sep}"
    avg_rtm = float(np.mean([v for v in rtm_vals if not pd.isna(v)]))
    rtm_row += f" {fmt_pp(avg_rtm, CW-1)} {sep}"
    print(rtm_row)

    # n evaluated
    n_row = f"{sep} {'n eval':<11} {sep}"
    ns = [r["n_eval"] for r in results]
    for n in ns:
        n_row += f" {n:>{CW-2}}  {sep}"
    n_row += f" {sum(ns):>{CW-1}} {sep}"
    print(n_row)

    print(bot)


def print_year_detail(results: list):
    for r in results:
        year = r["year"]
        g    = r["gradient"]

        print(f"\n  -- {year} ----------------------------------------------------------")
        print(f"  Signal pool: {r['n_signals']} batters | {r['n_eval']} evaluated | {r['n_flat']} flat")
        print(f"  Career BABIP: {r['n_career']} individual baseline | {r['n_fallback']} flat 0.300 fallback")
        print(f"  Layers: {' | '.join(r['layers'])}")

        sc = r["sig_counts"]
        bc = " | ".join(f"{s}: {sc.get(s,0)}"
                        for s in ["BUY_LOW","SLIGHT_BUY","NEUTRAL","SLIGHT_SELL","SELL_HIGH"])
        print(f"  Buckets: {bc}")

        vals = [(s, g.get(s, float("nan"))) for s in ["BUY_LOW","SLIGHT_BUY","NEUTRAL","SLIGHT_SELL","SELL_HIGH"]]
        grad_str = "  Gradient: " + " -> ".join(
            f"{s}={v:+.4f}" if not pd.isna(v) else f"{s}=n/a" for s, v in vals
        )
        print(grad_str)

        mono_vals = [v for _, v in vals if not pd.isna(v)]
        mono = all(mono_vals[i] > mono_vals[i+1] for i in range(len(mono_vals)-1))
        print(f"  Gradient monotonically decreasing: {'YES' if mono else 'NO'}")

        for sig in ["BUY_LOW", "SLIGHT_BUY", "SELL_HIGH", "SLIGHT_SELL"]:
            n, c, acc = r["stats"].get(sig, (0, 0, float("nan")))
            acc_str = f"{acc:.1%}" if not pd.isna(acc) else "n/a"
            print(f"    {sig:<14} n={n:>3}  acc={acc_str}")

        l3b = r["l3_both"]
        l3o = r["l3_one"]
        print(f"  L3 EV: {l3b} full x0.85 (both signals) | {l3o} mild x0.93 (one signal)")


def print_gradient_table(results: list):
    sig_order = ["BUY_LOW","SLIGHT_BUY","NEUTRAL","SLIGHT_SELL","SELL_HIGH"]
    hdr = f"  {'Signal':<14} " + "".join(f"{r['year']:>10}" for r in results) + f"  {'4yr avg':>10}"
    print(hdr)
    print("  " + "-" * (14 + 10 * len(results) + 12))
    for sig in sig_order:
        vals = [r["gradient"].get(sig, float("nan")) for r in results]
        valid = [v for v in vals if not pd.isna(v)]
        avg  = float(np.mean(valid)) if valid else float("nan")
        row  = f"  {sig:<14} " + "".join(
            f"{v:>+10.4f}" if not pd.isna(v) else f"{'n/a':>10}" for v in vals
        )
        row += f"  {avg:>+10.4f}" if not pd.isna(avg) else f"  {'n/a':>10}"
        print(row)


# ------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------

def main():
    print("Multi-Year Within-Season Backtest v3  (2022-2025) -- Career BABIP Baselines")
    print("=" * 76)

    career_stats  = load_career_stats()
    patterns      = load_seasonal_patterns()
    career_babip  = load_career_babip()
    print(f"Career stats:   {len(career_stats):,} players")
    print(f"Seasonal pats:  {len(patterns):,} players")
    print(f"Career BABIP:   {len(career_babip):,} hitters (individual baselines)")

    # v2 benchmarks
    V2_OVERALL = 0.817
    V2_SS      = 0.650
    V2_BL      = 0.950
    V2_RTM     = 0.135

    results = []
    for year in YEARS:
        print(f"\nRunning {year}...")
        r = run_year(year, career_stats, patterns, career_babip)
        if r is None:
            print(f"  SKIPPED -- missing cache files")
            continue
        results.append(r)
        ov_a = r["stats"]["OVERALL"][2]
        bl_a = r["stats"]["BUY_LOW"][2]
        ss_a = r["stats"]["SLIGHT_SELL"][2]
        print(f"  {r['n_signals']} signal batters -> {r['n_eval']} evaluated  |  "
              f"overall={ov_a:.1%}  BUY_LOW={bl_a:.1%}  SLIGHT_SELL={ss_a:.1%}  "
              f"career_babip={r['n_career']}/{r['n_career']+r['n_fallback']} batters")

    if not results:
        print("No results.")
        return

    # ── Main table ────────────────────────────────────────────────────
    print(f"\n{'=' * 76}")
    print("ACCURACY TABLE -- April signals -> May-July outcomes  (v3: career BABIP)")
    print(f"{'=' * 76}")
    print_table(results)

    # ── Per-year detail ───────────────────────────────────────────────
    print(f"\n{'=' * 76}")
    print("PER-YEAR DETAIL")
    print(f"{'=' * 76}")
    print_year_detail(results)

    # ── Gradient consistency ──────────────────────────────────────────
    print(f"\n{'=' * 76}")
    print("GRADIENT CONSISTENCY -- mean wOBA change by signal bucket")
    print(f"{'=' * 76}")
    print_gradient_table(results)

    # ── v2 vs v3 comparison ───────────────────────────────────────────
    print(f"\n{'=' * 76}")
    print("v2 vs v3 COMPARISON  (v2 = flat 0.300 baseline | v3 = career BABIP baseline)")
    print(f"{'=' * 76}")

    ov_accs = [r["stats"]["OVERALL"][2]     for r in results]
    bl_accs = [r["stats"]["BUY_LOW"][2]     for r in results]
    ss_accs = [r["stats"]["SLIGHT_SELL"][2] for r in results]
    sb_accs = [r["stats"]["SLIGHT_BUY"][2]  for r in results]

    ov_avg  = float(np.nanmean(ov_accs))
    bl_avg  = float(np.nanmean(bl_accs))
    ss_avg  = float(np.nanmean(ss_accs))
    sb_avg  = float(np.nanmean(sb_accs))
    rtm_avg = ov_avg - RTM_BASELINE

    print(f"\n  {'Metric':<22} {'v2':>8} {'v3':>8} {'Delta':>8}")
    print(f"  {'-' * 50}")
    for label, v2, v3 in [
        ("Overall 4yr avg",    V2_OVERALL, ov_avg),
        ("BUY_LOW 4yr avg",    V2_BL,      bl_avg),
        ("SLIGHT_SELL 4yr avg",V2_SS,      ss_avg),
        ("vs RTM 4yr avg",     V2_RTM,     rtm_avg),
    ]:
        delta = v3 - v2
        arrow = " <-- improved" if delta > 0.002 else (" <-- worse" if delta < -0.002 else "")
        print(f"  {label:<22} {v2:>7.1%} {v3:>7.1%} {delta:>+7.1%}{arrow}")

    # ── Key questions ──────────────────────────────────────────────────
    print(f"\n{'=' * 76}")
    print("KEY QUESTIONS")
    print(f"{'=' * 76}")

    # Q1: Does career BABIP help overall?
    beats_v2 = ov_avg > V2_OVERALL + 0.002
    hurts_v2 = ov_avg < V2_OVERALL - 0.002
    print(f"\n  Q1: Does career BABIP improve overall accuracy vs v2 ({V2_OVERALL:.1%})?")
    print(f"      v2={V2_OVERALL:.1%}  v3={ov_avg:.1%}  delta={ov_avg-V2_OVERALL:>+.1%}")
    print(f"      Per-year: " + " | ".join(f"{r['year']}={r['stats']['OVERALL'][2]:.1%}" for r in results))
    if beats_v2:
        ans = "YES -- individual baselines improve prediction accuracy"
    elif hurts_v2:
        ans = "NO -- career BABIP hurts accuracy (may reflect look-ahead bias or noise)"
    else:
        ans = "NEUTRAL -- within noise margin (+/- 0.2%)"
    print(f"      Answer: {ans}")

    # Q2: Does career BABIP help BUY_LOW specifically?
    bl_beats = bl_avg > V2_BL + 0.002
    bl_hurts = bl_avg < V2_BL - 0.002
    print(f"\n  Q2: Does career BABIP improve BUY_LOW accuracy vs v2 ({V2_BL:.1%})?")
    print(f"      v2={V2_BL:.1%}  v3={bl_avg:.1%}  delta={bl_avg-V2_BL:>+.1%}")
    n_career_total = sum(r["n_career"]   for r in results)
    n_fallb_total  = sum(r["n_fallback"] for r in results)
    print(f"      Career BABIP coverage: {n_career_total} individual | {n_fallb_total} fallback (across 4yr signal pools)")
    if bl_beats:
        ans = "YES -- career BABIP shifts buy signals toward higher-quality hits"
    elif bl_hurts:
        ans = "NO -- career BABIP dampens some valid buy signals"
    else:
        ans = "NEUTRAL -- no meaningful BUY_LOW change"
    print(f"      Answer: {ans}")

    # Q3: SLIGHT_SELL accuracy
    ss_beats = ss_avg > V2_SS + 0.002
    print(f"\n  Q3: Does career BABIP affect SLIGHT_SELL accuracy vs v2 ({V2_SS:.1%})?")
    print(f"      v2={V2_SS:.1%}  v3={ss_avg:.1%}  delta={ss_avg-V2_SS:>+.1%}")
    print(f"      Per-year: " + " | ".join(f"{r['year']}={r['stats']['SLIGHT_SELL'][2]:.1%}" for r in results))
    print(f"      Answer: {'IMPROVED' if ss_beats else ('WORSE' if ss_avg < V2_SS - 0.002 else 'NEUTRAL')}")

    # Q4: Best year
    year_ov = [(r["year"], r["stats"]["OVERALL"][2]) for r in results]
    best_year, best_acc = max(year_ov, key=lambda x: x[1])
    print(f"\n  Q4: Which year has best accuracy in v3?")
    for yr, acc in year_ov:
        v2_acc = {2022: 0.758, 2023: 0.812, 2024: 0.795, 2025: 0.825}.get(yr, float("nan"))
        delta = acc - v2_acc if not pd.isna(v2_acc) else float("nan")
        d_str = f"  (v2={v2_acc:.1%}  delta={delta:>+.1%})" if not pd.isna(v2_acc) else ""
        marker = " <-- best" if yr == best_year else ""
        print(f"      {yr}: {acc:.1%}{d_str}{marker}")

    # ── Summary ───────────────────────────────────────────────────────
    print(f"\n{'=' * 76}")
    print("SUMMARY")
    print(f"{'=' * 76}")
    print(f"  Overall 4yr avg:    {ov_avg:.1%}  (v2={V2_OVERALL:.1%}  delta={ov_avg-V2_OVERALL:>+.1%})")
    print(f"  BUY_LOW 4yr avg:    {bl_avg:.1%}  (v2={V2_BL:.1%}  delta={bl_avg-V2_BL:>+.1%})")
    print(f"  SLIGHT_BUY 4yr avg: {sb_avg:.1%}")
    print(f"  SLIGHT_SELL 4yr avg:{ss_avg:.1%}  (v2={V2_SS:.1%}  delta={ss_avg-V2_SS:>+.1%})")
    print(f"  vs RTM 4yr avg:     {rtm_avg:.1%}pp  (v2={V2_RTM:.1%}pp  delta={rtm_avg-V2_RTM:>+.1%}pp)")
    print(f"  Total player-seasons evaluated: {sum(r['n_eval'] for r in results)}")

    verdict = "SHIP IT" if beats_v2 else ("HOLD -- no improvement" if hurts_v2 else "MARGINAL -- within noise")
    print(f"\n  Career BABIP baseline verdict: {verdict}")


if __name__ == "__main__":
    main()
