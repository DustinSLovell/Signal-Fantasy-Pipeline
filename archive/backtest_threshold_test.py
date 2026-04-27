"""
backtest_threshold_test.py
===========================
Runs hitter backtest pipeline once per year to collect final luck_score +
outcome for each player-season, then tests all 4 threshold options without
re-running the full scoring pipeline each time.

Threshold options (in backtest scale):
  Current:  BUY_LOW>=0.040 SLIGHT_BUY>=0.020 SELL_HIGH<=-0.065 SLIGHT_SELL<=-0.040
  Option 1: BUY_LOW>=0.055 SLIGHT_BUY>=0.025 SELL_HIGH<=-0.080 SLIGHT_SELL<=-0.050
  Option 2: BUY_LOW>=0.070 SLIGHT_BUY>=0.035 SELL_HIGH<=-0.095 SLIGHT_SELL<=-0.060
  Option 3: BUY_LOW>=0.050 SLIGHT_BUY>=0.025 SELL_HIGH<=-0.075 SLIGHT_SELL<=-0.045
"""

import io
import sys
import os
import json
import numpy as np
import pandas as pd
from pathlib import Path

# Handle stdout encoding
if isinstance(sys.stdout, io.TextIOWrapper):
    _buf = sys.stdout.detach()
else:
    _buf = getattr(sys.stdout, "buffer", sys.stdout)
sys.stdout = io.TextIOWrapper(_buf, encoding="utf-8", errors="replace")

BASE_DIR  = Path(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = BASE_DIR / "backtest_cache"

# ── Threshold options ──────────────────────────────────────────────────────────
THRESHOLD_OPTIONS = {
    "Current":  dict(buy_low=0.040, slight_buy=0.020, sell_high=-0.065, slight_sell=-0.040),
    "Option 1": dict(buy_low=0.055, slight_buy=0.025, sell_high=-0.080, slight_sell=-0.050),
    "Option 2": dict(buy_low=0.070, slight_buy=0.035, sell_high=-0.095, slight_sell=-0.060),
    "Option 3": dict(buy_low=0.050, slight_buy=0.025, sell_high=-0.075, slight_sell=-0.045),
}

# ── Constants (match backtest_multi_year_v7) ───────────────────────────────────
H_YEARS         = [2022, 2023, 2024, 2025]
MIN_APRIL_PA    = 80
MIN_OUTCOME_PA  = 100
FLAT_THRESHOLD  = 0.015
LEAGUE_AVG_BABIP = 0.300
EV_THRESHOLD    = 1.0
SELL_HIGH_THRESH  = -0.065   # used in layer logic, not classification
SLIGHT_SELL_THRESH= -0.040

PARK_FACTORS_H = {
    'COL': 1.12, 'CIN': 1.08, 'TEX': 1.06, 'HOU': 1.05,
    'BAL': 1.04, 'BOS': 1.04, 'PHI': 1.03, 'MIL': 1.02,
    'ATL': 1.02, 'NYY': 1.01, 'TOR': 1.01, 'WSH': 1.00,
    'CHC': 1.00, 'STL': 1.00, 'LAD': 0.99, 'NYM': 0.99,
    'ARI': 0.99, 'MIN': 0.98, 'DET': 0.98, 'CLE': 0.98,
    'CWS': 0.97, 'SEA': 0.97, 'SF':  0.96, 'MIA': 0.96,
    'TB':  0.96, 'PIT': 0.96, 'KC':  0.96, 'LAA': 0.95,
    'SD':  0.95, 'OAK': 0.94,
}

BIP_EVENTS_H = {
    'single', 'double', 'triple', 'field_out', 'grounded_into_double_play',
    'force_out', 'double_play', 'fielders_choice',
}

PHASE_C = {
    'vshape_buy':  1.20, 'vshape_sell': None,
    'slow_buy':    1.10, 'summer_buy':  1.10,
    'fader_sell':  1.15, 'fader_buy':   0.90,
}

SIGNAL_MAP_H = {
    'BUY_LOW':    'IMPROVED',
    'SLIGHT_BUY': 'IMPROVED',
    'SELL_HIGH':  'DECLINED',
    'SLIGHT_SELL':'DECLINED',
}


def _babip_age_mult(age: int) -> float:
    if age <= 25: return 1.02
    if age <= 27: return 1.01
    if age <= 30: return 1.00
    if age <= 32: return 0.99
    if age <= 35: return 0.98
    return 0.97


def load_support_data():
    career_path = BASE_DIR / "data" / "career_stats.json"
    career_babip_path = BASE_DIR / "data" / "hitter_career_babip.json"
    seasonal_path = BASE_DIR / "data" / "seasonal_patterns.json"
    team_oaa_path = BASE_DIR / "data" / "team_oaa_2025.csv"

    career = {}
    if career_path.exists():
        with open(career_path) as f:
            raw = json.load(f)
        career = {int(k): v for k, v in raw.items()}

    career_babip = {}
    if career_babip_path.exists():
        with open(career_babip_path) as f:
            raw = json.load(f)
        for k, v in raw.items():
            if isinstance(v, dict):
                career_babip[int(k)] = float(v.get("career_babip", LEAGUE_AVG_BABIP))
            else:
                career_babip[int(k)] = float(v)

    patterns = {}
    if seasonal_path.exists():
        with open(seasonal_path) as f:
            raw = json.load(f)
        if isinstance(raw, list):
            for item in raw:
                pid = item.get("player_id") or item.get("batter")
                if pid is not None:
                    patterns[int(pid)] = item
        else:
            patterns = {int(k): v for k, v in raw.items()}

    opp_oaa = {}
    if team_oaa_path.exists():
        oaa_df = pd.read_csv(team_oaa_path)
        if "team" in oaa_df.columns and "oaa" in oaa_df.columns:
            oaa_vals = oaa_df.set_index("team")["oaa"].to_dict()
            opp_oaa = {t: -float(v) * 0.005 for t, v in oaa_vals.items()}

    return career, career_babip, patterns, opp_oaa


def score_year(year: int, career: dict, career_babip: dict,
               patterns: dict, opp_oaa: dict) -> pd.DataFrame | None:
    """
    Run the full hitter scoring pipeline for one year.
    Returns DataFrame with columns: batter, luck_score, woba_change, outcome
    (outcome is IMPROVED / DECLINED / FLAT, excluding FLAT from eval).
    """
    april_path   = CACHE_DIR / f"v4_april_{year}.csv"
    outcome_path = CACHE_DIR / f"statcast_{year}_may_july.csv"
    team_path    = CACHE_DIR / f"team_map_{year}.csv"

    if not april_path.exists() or not outcome_path.exists():
        print(f"  SKIP {year}: missing cache files")
        return None

    april   = pd.read_csv(april_path)
    outcome = pd.read_csv(outcome_path)

    if team_path.exists():
        team_map = pd.read_csv(team_path)
        april = april.merge(team_map, on="batter", how="left")
    april["park_factor"] = april["team"].map(PARK_FACTORS_H).fillna(1.0) if "team" in april.columns else 1.0

    # BIP / BABIP
    batted = april[april["bb_type"].notna() & (april["bb_type"] != "")].copy()
    batted["is_bip"] = batted["events"].isin(BIP_EVENTS_H).astype(int)
    batted["is_hit"] = batted["events"].isin({"single","double","triple"}).astype(int)
    batted["is_gb"]  = (batted["bb_type"] == "ground_ball").astype(int)
    bip_agg = batted.groupby("batter").agg(
        bip=("is_bip","sum"), hits_bip=("is_hit","sum"), gb=("is_gb","sum")).reset_index()

    # Exit velo / sweet spot
    bbe = april[april["launch_speed"].notna() & april["launch_angle"].notna()].copy()
    bbe_agg = bbe.groupby("batter").apply(
        lambda s: pd.Series({
            "sweet_spot_count": int(((s["launch_speed"]>=98) & s["launch_angle"].between(8,32)).sum()),
            "bbe_total":         len(s),
            "avg_exit_velocity": float(s["launch_speed"].mean()),
        })
    ).reset_index() if len(bbe) > 0 else pd.DataFrame(
        columns=["batter","sweet_spot_count","bbe_total","avg_exit_velocity"])

    # BB / K
    april["is_bb"] = april["events"].isin({"walk","intent_walk"}).astype(int)
    april["is_k"]  = april["events"].isin({"strikeout","strikeout_double_play"}).astype(int)
    disc_agg = april.groupby("batter").agg(
        bb_count=("is_bb","sum"), k_count=("is_k","sum")).reset_index()

    has_xwoba = "estimated_woba_using_speedangle" in april.columns
    pa_agg = april.groupby("batter").agg(
        april_pa=("woba_value","count"),
        april_actual_woba=("woba_value","mean"),
        **({ "april_xwoba": ("estimated_woba_using_speedangle","mean") } if has_xwoba else {}),
        park_factor=("park_factor","first"),
    ).reset_index()
    if not has_xwoba:
        pa_agg["april_xwoba"] = np.nan

    signals = pa_agg.merge(bip_agg, on="batter", how="left")
    has_bbe = len(bbe_agg) > 0
    if has_bbe:
        signals = signals.merge(bbe_agg, on="batter", how="left")
    else:
        for col in ["sweet_spot_count","bbe_total","avg_exit_velocity"]:
            signals[col] = np.nan
    signals = signals.merge(disc_agg, on="batter", how="left")

    signals["babip"]           = np.where(signals["bip"]>0, signals["hits_bip"]/signals["bip"], np.nan)
    signals["gb_rate"]         = np.where(signals["bip"]>0, signals["gb"]/signals["bip"], np.nan)
    signals["sweet_spot_rate"] = np.where(signals["bbe_total"]>0,
                                           signals["sweet_spot_count"]/signals["bbe_total"], np.nan)
    signals["bb_rate"] = signals["bb_count"] / signals["april_pa"]
    signals["k_rate"]  = signals["k_count"]  / signals["april_pa"]
    signals["xwoba_gap"] = signals["april_xwoba"] - signals["april_actual_woba"]

    signals["babip_baseline"] = signals["batter"].map(
        lambda bid: career_babip.get(int(bid), LEAGUE_AVG_BABIP))

    def _age_adj_babip(row) -> float:
        bid  = int(row["batter"])
        base = row["babip_baseline"]
        if base == LEAGUE_AVG_BABIP:
            return base
        byr = int((career.get(bid) or {}).get("birth_year") or 0)
        if byr == 0:
            return base
        age = year - byr
        return round(base * _babip_age_mult(age), 4)

    signals["babip_baseline"] = signals.apply(_age_adj_babip, axis=1)
    park_adj = (signals["park_factor"] - 1.0) * 0.10
    signals["babip_expected"] = (signals["babip_baseline"] - park_adj).round(4)

    if opp_oaa:
        signals["oaa_babip_adj"] = signals["batter"].apply(lambda b: opp_oaa.get(int(b), 0.0))
        signals["babip_expected"] = (signals["babip_expected"] + signals["oaa_babip_adj"]).round(4)

    if signals["gb_rate"].notna().any():
        signals.loc[signals["gb_rate"] > 0.50, "babip_expected"] -= 0.010
        signals.loc[signals["gb_rate"] < 0.35, "babip_expected"] += 0.008

    signals["babip_luck"] = signals["babip_expected"] - signals["babip"]
    signals = signals[signals["april_pa"] >= MIN_APRIL_PA].copy()
    signals["luck_score"] = (
        signals["xwoba_gap"]  * 0.60 +
        signals["babip_luck"] * 0.40
    ).round(4)

    # L2: sweet spot amplifier
    if signals["sweet_spot_rate"].notna().any():
        buy     = signals["luck_score"] > 0
        high_ss = buy & (signals["sweet_spot_rate"] > 0.12)
        low_ss  = buy & (signals["sweet_spot_rate"] < 0.06)
        signals.loc[high_ss, "luck_score"] = (signals.loc[high_ss,"luck_score"] * 1.05).round(4)
        signals.loc[low_ss,  "luck_score"] = (signals.loc[low_ss, "luck_score"] * 0.95).round(4)

    # L3: EV quality dampener
    if signals["avg_exit_velocity"].notna().any():
        for idx, row in signals.iterrows():
            if row["luck_score"] <= 0:
                continue
            career_ev = (career.get(int(row["batter"])) or {}).get("avg_exit_velocity")
            if career_ev is None or pd.isna(row["avg_exit_velocity"]):
                continue
            ev_below  = (row["avg_exit_velocity"] - career_ev) < -EV_THRESHOLD
            ss        = row["sweet_spot_rate"]
            low_ss_ev = pd.notna(ss) and ss < 0.08
            if ev_below and low_ss_ev:
                signals.at[idx, "luck_score"] = round(row["luck_score"] * 0.85, 4)
            elif ev_below or low_ss_ev:
                signals.at[idx, "luck_score"] = round(row["luck_score"] * 0.93, 4)

    # L5: discipline modifier
    if signals["bb_rate"].notna().any() and signals["k_rate"].notna().any():
        buy_mask   = signals["luck_score"] > 0
        elite_disc = buy_mask & (signals["bb_rate"] > 0.10) & (signals["k_rate"] < 0.18)
        poor_disc  = buy_mask & ((signals["bb_rate"] < 0.06) | (signals["k_rate"] > 0.28))
        signals.loc[elite_disc, "luck_score"] = (signals.loc[elite_disc,"luck_score"] * 1.08).round(4)
        signals.loc[poor_disc,  "luck_score"] = (signals.loc[poor_disc, "luck_score"] * 0.88).round(4)

    # L6: Phase C seasonal pattern
    if patterns:
        for idx, row in signals.iterrows():
            pid   = int(row["batter"])
            raw   = row["luck_score"]
            if pid not in patterns:
                continue
            p     = patterns[pid]
            slow   = p.get("slow_starter", False)
            fader  = p.get("second_half_fader", False)
            summer = p.get("summer_performer", False)
            is_buy  = raw > 0
            is_sell = raw < 0
            mult = 1.0
            if slow and summer:
                if is_buy: mult = PHASE_C["vshape_buy"]
            elif slow and not summer:
                if is_buy: mult = PHASE_C["slow_buy"]
            elif summer and not slow:
                if is_buy: mult = PHASE_C["summer_buy"]
            if fader:
                if is_sell:   mult = max(mult, PHASE_C["fader_sell"])
                elif is_buy:  mult = min(mult, PHASE_C["fader_buy"])
            if mult != 1.0:
                signals.at[idx, "luck_score"] = round(raw * mult, 4)

    # Outcomes
    may_july = outcome.groupby("batter").agg(
        outcome_pa=("woba_value","count"),
        outcome_woba=("woba_value","mean"),
    ).reset_index()

    merged = signals.merge(may_july, on="batter", how="inner")
    merged = merged[merged["outcome_pa"] >= MIN_OUTCOME_PA].copy()
    merged["woba_change"] = merged["outcome_woba"] - merged["april_actual_woba"]
    merged["outcome"] = np.where(
        merged["woba_change"] >=  FLAT_THRESHOLD, "IMPROVED",
        np.where(merged["woba_change"] <= -FLAT_THRESHOLD, "DECLINED", "FLAT")
    )

    return merged[["batter", "luck_score", "woba_change", "outcome", "april_pa"]].copy()


def classify_with_thresh(score: float, thresholds: dict) -> str:
    if score >= thresholds["buy_low"]:    return "BUY_LOW"
    if score >= thresholds["slight_buy"]: return "SLIGHT_BUY"
    if score <= thresholds["sell_high"]:  return "SELL_HIGH"
    if score <= thresholds["slight_sell"]:return "SLIGHT_SELL"
    return "NEUTRAL"


def bucket_stats(eval_df: pd.DataFrame) -> dict:
    stats = {}
    for sig in ["BUY_LOW","SLIGHT_BUY","SELL_HIGH","SLIGHT_SELL"]:
        grp = eval_df[eval_df["signal"] == sig]
        n   = len(grp)
        c   = int(grp["correct"].sum()) if n > 0 else 0
        stats[sig] = (n, c, c / n if n > 0 else float("nan"))
    ov_n = len(eval_df)
    ov_c = int(eval_df["correct"].sum())
    stats["OVERALL"] = (ov_n, ov_c, ov_c / ov_n if ov_n > 0 else float("nan"))
    return stats


def evaluate_thresholds(all_scored: pd.DataFrame, thresholds: dict) -> dict:
    df = all_scored.copy()
    df["signal"] = df["luck_score"].apply(lambda s: classify_with_thresh(s, thresholds))
    eval_df = df[df["signal"].isin(SIGNAL_MAP_H) & (df["outcome"] != "FLAT")].copy()
    eval_df["correct"] = eval_df.apply(lambda r: r["outcome"] == SIGNAL_MAP_H[r["signal"]], axis=1)
    return bucket_stats(eval_df)


def main():
    print("Loading support data...")
    career, career_babip, patterns, opp_oaa = load_support_data()
    print(f"  career_stats: {len(career):,}")
    print(f"  career_babip: {len(career_babip):,}")
    print(f"  seasonal_patterns: {len(patterns):,}")

    all_scored_parts = []
    for year in H_YEARS:
        print(f"\nScoring {year}...")
        scored = score_year(year, career, career_babip, patterns, opp_oaa)
        if scored is not None:
            scored["year"] = year
            all_scored_parts.append(scored)
            print(f"  {len(scored):,} players scored")

    if not all_scored_parts:
        print("\nNo data available.")
        return

    all_scored = pd.concat(all_scored_parts, ignore_index=True)
    print(f"\nTotal player-seasons scored: {len(all_scored):,}")

    # ── Results table ──────────────────────────────────────────────────────────
    print("\n" + "="*78)
    print(f"{'HITTER THRESHOLD BACKTEST — 2022-2025':^78}")
    print("="*78)

    results = {}
    for opt_name, thresholds in THRESHOLD_OPTIONS.items():
        results[opt_name] = evaluate_thresholds(all_scored, thresholds)

    # Header
    sigs = ["BUY_LOW", "SLIGHT_BUY", "SELL_HIGH", "SLIGHT_SELL", "OVERALL"]
    sig_labels = {
        "BUY_LOW":     "Buy low",
        "SLIGHT_BUY":  "Slight buy",
        "SELL_HIGH":   "Sell high",
        "SLIGHT_SELL": "Slight sell",
        "OVERALL":     "Overall",
    }
    opt_names = list(THRESHOLD_OPTIONS.keys())

    # Print accuracy table
    print(f"\n{'Signal':<14}", end="")
    for name in opt_names:
        print(f"  {name:>12}", end="")
    print()
    print("-" * (14 + 14 * len(opt_names)))

    for sig in sigs:
        print(f"{sig_labels[sig]:<14}", end="")
        for name in opt_names:
            n, c, acc = results[name][sig]
            if np.isnan(acc):
                print(f"  {'N/A (n=0)':>12}", end="")
            else:
                print(f"  {acc*100:>8.1f}% ({n:>3}n)", end="")
        print()

    # Print n changes summary
    print(f"\n{'Signal':<14}", end="")
    for name in opt_names:
        print(f"  {name:>12}", end="")
    print()
    print(f"  (n = number of evaluated player-seasons per bucket)")
    print()

    # Detailed breakdown: accuracy + n per option
    print("\n" + "="*78)
    print("DETAIL BY OPTION")
    print("="*78)
    for name, thresholds in THRESHOLD_OPTIONS.items():
        stats = results[name]
        t = thresholds
        print(f"\n  {name}: buy_low>={t['buy_low']:.3f}  slight_buy>={t['slight_buy']:.3f}"
              f"  sell_high<={t['sell_high']:.3f}  slight_sell<={t['slight_sell']:.3f}")
        for sig in sigs:
            n, c, acc = stats[sig]
            bar = "  ← " if sig == "OVERALL" else "     "
            if np.isnan(acc):
                print(f"    {sig_labels[sig]:<14}: N/A")
            else:
                print(f"    {sig_labels[sig]:<14}: {acc*100:>6.1f}%  n={n:>4}{bar}")

    # Signal count shift — how many players move between buckets
    print("\n" + "="*78)
    print("SIGNAL COUNT SHIFT (vs Current)")
    print("="*78)
    base_thresholds = THRESHOLD_OPTIONS["Current"]
    all_scored["signal_current"] = all_scored["luck_score"].apply(
        lambda s: classify_with_thresh(s, base_thresholds))
    cnt_current = all_scored["signal_current"].value_counts()

    print(f"\n  {'Bucket':<14}  {'Current':>8}", end="")
    for name in opt_names[1:]:
        print(f"  {name:>10}", end="")
    print()
    print(f"  {'-'*14}  {'-'*8}", end="")
    for _ in opt_names[1:]:
        print(f"  {'-'*10}", end="")
    print()

    for sig in ["BUY_LOW","SLIGHT_BUY","NEUTRAL","SLIGHT_SELL","SELL_HIGH"]:
        c_n = int(cnt_current.get(sig, 0))
        print(f"  {sig:<14}  {c_n:>8}", end="")
        for name in opt_names[1:]:
            all_scored[f"signal_{name}"] = all_scored["luck_score"].apply(
                lambda s, t=THRESHOLD_OPTIONS[name]: classify_with_thresh(s, t))
            cnt = all_scored[f"signal_{name}"].value_counts()
            n = int(cnt.get(sig, 0))
            delta = n - c_n
            arrow = f"({delta:+d})" if delta != 0 else ""
            print(f"  {n:>5} {arrow:>5}", end="")
        print()


if __name__ == "__main__":
    main()
