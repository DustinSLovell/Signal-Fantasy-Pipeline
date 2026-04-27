"""
Extract named player examples from v4 backtest for Substack article.
Re-runs same logic as backtest_multi_year_v4.py and exports per-player rows.
"""

import io, json, sys, os
import numpy as np
import pandas as pd
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE_DIR          = Path(os.path.dirname(os.path.abspath(__file__))).parent  # project root
CACHE_DIR         = BASE_DIR / "backtest_cache"
CAREER_PATH       = BASE_DIR / "data" / "career_stats.json"
CAREER_BABIP_PATH = BASE_DIR / "data" / "hitter_career_babip.json"
SEASONAL_PATH     = BASE_DIR / "data" / "seasonal_patterns.json"

YEARS            = [2022, 2023, 2024, 2025]
MIN_APRIL_PA     = 80
MIN_OUTCOME_PA   = 100
FLAT_THRESHOLD   = 0.015
LEAGUE_AVG_BABIP = 0.300
EV_THRESHOLD     = 1.0
RTM_BASELINE     = 0.682
SLIGHT_SELL_THRESH = -0.026

PARK_FACTORS = {
    'COL': 1.12, 'CIN': 1.08, 'TEX': 1.06, 'HOU': 1.05,
    'BAL': 1.04, 'BOS': 1.04, 'PHI': 1.03, 'MIL': 1.02,
    'ATL': 1.02, 'NYY': 1.01, 'TOR': 1.01, 'WSH': 1.00,
    'CHC': 1.00, 'STL': 1.00, 'LAD': 0.99, 'NYM': 0.99,
    'ARI': 0.99, 'MIN': 0.98, 'DET': 0.98, 'CLE': 0.98,
    'PIT': 0.98, 'SEA': 0.97, 'SDP': 0.97, 'SFG': 0.97,
    'OAK': 0.97, 'KCR': 0.97, 'TBR': 0.97, 'CHW': 0.97,
    'MIA': 0.96, 'LAA': 0.96,
}

BIP_EVENTS = {
    'single', 'double', 'triple', 'field_out', 'grounded_into_double_play',
    'force_out', 'double_play', 'fielders_choice',
}

PHASE_C = {
    'vshape_buy':  1.20, 'vshape_sell': None,
    'slow_buy':    1.10, 'summer_buy':  1.10,
    'fader_sell':  1.15, 'fader_buy':   0.90,
}

SIGNAL_MAP = {
    'BUY_LOW': 'IMPROVED', 'SLIGHT_BUY': 'IMPROVED',
    'SELL_HIGH': 'DECLINED', 'SLIGHT_SELL': 'DECLINED',
}


def _babip_age_mult(age):
    if age >= 39: return 0.88
    if age >= 37: return 0.91
    if age >= 35: return 0.94
    if age >= 32: return 0.97
    return 1.0


def classify(score):
    if score >= 0.040:              return "BUY_LOW"
    if score >= 0.020:              return "SLIGHT_BUY"
    if score <= -0.040:             return "SELL_HIGH"
    if score <= SLIGHT_SELL_THRESH: return "SLIGHT_SELL"
    return "NEUTRAL"


def load_names():
    dfs = []
    for yr in YEARS:
        p = BASE_DIR / "data" / f"fg_batting_{yr}.csv"
        if p.exists():
            df = pd.read_csv(p, usecols=["last_name, first_name", "batter_id"])
            dfs.append(df)
    if not dfs:
        return {}
    combined = pd.concat(dfs).drop_duplicates("batter_id")
    # Format as "First Last"
    def fmt(s):
        parts = [p.strip() for p in s.split(",")]
        if len(parts) == 2:
            return f"{parts[1]} {parts[0]}"
        return s
    combined["name"] = combined["last_name, first_name"].apply(fmt)
    return dict(zip(combined["batter_id"], combined["name"]))


def run_year_rows(year, career_stats, patterns, career_babip):
    april_path   = CACHE_DIR / f"v4_april_{year}.csv"
    outcome_path = CACHE_DIR / f"statcast_{year}_may_july.csv"
    team_path    = CACHE_DIR / f"team_map_{year}.csv"
    if not april_path.exists() or not outcome_path.exists():
        return None

    april   = pd.read_csv(april_path)
    outcome = pd.read_csv(outcome_path)

    if team_path.exists():
        team_map = pd.read_csv(team_path)
        april = april.merge(team_map, on="batter", how="left")
    april["park_factor"] = april["team"].map(PARK_FACTORS).fillna(1.0) if "team" in april.columns else 1.0

    batted = april[april["bb_type"].notna() & (april["bb_type"] != "")].copy()
    batted["is_bip"] = batted["events"].isin(BIP_EVENTS).astype(int)
    batted["is_hit"] = batted["events"].isin({"single", "double", "triple"}).astype(int)
    batted["is_gb"]  = (batted["bb_type"] == "ground_ball").astype(int)
    bip_agg = batted.groupby("batter").agg(
        bip=("is_bip", "sum"), hits_bip=("is_hit", "sum"), gb=("is_gb", "sum")
    ).reset_index()

    bbe = april[april["launch_speed"].notna() & april["launch_angle"].notna()].copy()
    bbe_agg = bbe.groupby("batter").apply(
        lambda s: pd.Series({
            "sweet_spot_count": int(((s["launch_speed"] >= 98) & s["launch_angle"].between(8, 32)).sum()),
            "bbe_total": len(s),
            "avg_exit_velocity": float(s["launch_speed"].mean()),
        })
    ).reset_index()

    april["is_bb"] = april["events"].isin({"walk", "intent_walk"}).astype(int)
    april["is_k"]  = april["events"].isin({"strikeout", "strikeout_double_play"}).astype(int)
    disc_agg = april.groupby("batter").agg(
        bb_count=("is_bb", "sum"), k_count=("is_k", "sum")
    ).reset_index()

    has_xwoba = "estimated_woba_using_speedangle" in april.columns
    pa_agg = april.groupby("batter").agg(
        april_pa=("woba_value", "count"),
        april_woba=("woba_value", "mean"),
        **({ "april_xwoba": ("estimated_woba_using_speedangle", "mean") } if has_xwoba else {}),
        park_factor=("park_factor", "first"),
    ).reset_index()
    if not has_xwoba:
        pa_agg["april_xwoba"] = np.nan

    signals = pa_agg.merge(bip_agg, on="batter", how="left")
    signals = signals.merge(bbe_agg, on="batter", how="left")
    signals = signals.merge(disc_agg, on="batter", how="left")

    signals["babip"]           = np.where(signals["bip"] > 0, signals["hits_bip"] / signals["bip"], np.nan)
    signals["gb_rate"]         = np.where(signals["bip"] > 0, signals["gb"] / signals["bip"], np.nan)
    signals["sweet_spot_rate"] = np.where(signals["bbe_total"] > 0,
                                           signals["sweet_spot_count"] / signals["bbe_total"], np.nan)
    signals["bb_rate"]   = signals["bb_count"] / signals["april_pa"]
    signals["k_rate"]    = signals["k_count"]  / signals["april_pa"]
    signals["xwoba_gap"] = signals["april_xwoba"] - signals["april_woba"]

    # v4: Career BABIP + age adjustment
    signals["babip_baseline"] = signals["batter"].map(
        lambda bid: career_babip.get(int(bid), LEAGUE_AVG_BABIP)
    )

    def _age_adj_babip(row):
        bid  = int(row["batter"])
        base = row["babip_baseline"]
        if base == LEAGUE_AVG_BABIP:
            return base
        byr = int((career_stats.get(bid) or {}).get("birth_year") or 0)
        if byr == 0:
            return base
        age = year - byr
        return round(base * _babip_age_mult(age), 4)

    signals["babip_baseline"] = signals.apply(_age_adj_babip, axis=1)
    park_adj = (signals["park_factor"] - 1.0) * 0.10
    signals["babip_expected"] = (signals["babip_baseline"] - park_adj).round(4)

    # L4: GB rate
    if signals["gb_rate"].notna().any():
        signals.loc[signals["gb_rate"] > 0.50, "babip_expected"] -= 0.010
        signals.loc[signals["gb_rate"] < 0.35, "babip_expected"] += 0.008

    signals["babip_luck"] = signals["babip_expected"] - signals["babip"]
    signals = signals[signals["april_pa"] >= MIN_APRIL_PA].copy()

    signals["luck_score"] = (
        signals["xwoba_gap"] * 0.60 + signals["babip_luck"] * 0.40
    ).round(4)

    # L2: Sweet spot
    if signals["sweet_spot_rate"].notna().any():
        buy = signals["luck_score"] > 0
        signals.loc[buy & (signals["sweet_spot_rate"] > 0.12), "luck_score"] = \
            (signals.loc[buy & (signals["sweet_spot_rate"] > 0.12), "luck_score"] * 1.05).round(4)
        signals.loc[buy & (signals["sweet_spot_rate"] < 0.06), "luck_score"] = \
            (signals.loc[buy & (signals["sweet_spot_rate"] < 0.06), "luck_score"] * 0.95).round(4)

    # L3: EV
    if signals["avg_exit_velocity"].notna().any():
        for idx, row in signals.iterrows():
            if row["luck_score"] <= 0:
                continue
            career_ev = (career_stats.get(int(row["batter"])) or {}).get("avg_exit_velocity")
            if career_ev is None or pd.isna(row["avg_exit_velocity"]):
                continue
            ev_below  = (row["avg_exit_velocity"] - career_ev) < -EV_THRESHOLD
            ss        = row["sweet_spot_rate"]
            low_ss_ev = pd.notna(ss) and ss < 0.08
            if ev_below and low_ss_ev:
                signals.at[idx, "luck_score"] = round(row["luck_score"] * 0.85, 4)
            elif ev_below or low_ss_ev:
                signals.at[idx, "luck_score"] = round(row["luck_score"] * 0.93, 4)

    # L5: Plate discipline
    if signals["bb_rate"].notna().any():
        buy_mask = signals["luck_score"] > 0
        elite = buy_mask & (signals["bb_rate"] > 0.10) & (signals["k_rate"] < 0.18)
        poor  = buy_mask & ((signals["bb_rate"] < 0.06) | (signals["k_rate"] > 0.28))
        signals.loc[elite, "luck_score"] = (signals.loc[elite, "luck_score"] * 1.08).round(4)
        signals.loc[poor,  "luck_score"] = (signals.loc[poor,  "luck_score"] * 0.88).round(4)

    # L6: Seasonal patterns
    if patterns:
        for idx, row in signals.iterrows():
            pid = int(row["batter"])
            raw = row["luck_score"]
            if pid not in patterns:
                continue
            p = patterns[pid]
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

    signals["signal"] = signals["luck_score"].apply(classify)

    # Outcomes
    may_july = outcome.groupby("batter").agg(
        outcome_pa=("woba_value", "count"),
        outcome_woba=("woba_value", "mean"),
    ).reset_index()

    merged = signals.merge(may_july, on="batter", how="inner")
    merged = merged[merged["outcome_pa"] >= MIN_OUTCOME_PA].copy()
    merged["woba_change"] = merged["outcome_woba"] - merged["april_woba"]
    merged["outcome"] = np.where(
        merged["woba_change"] >=  FLAT_THRESHOLD, "IMPROVED",
        np.where(merged["woba_change"] <= -FLAT_THRESHOLD, "DECLINED", "FLAT")
    )
    merged["correct"] = merged.apply(
        lambda r: r["outcome"] == SIGNAL_MAP.get(r["signal"], "")
        if r["signal"] in SIGNAL_MAP else False, axis=1
    )
    merged["year"] = year
    return merged


def main():
    with open(CAREER_PATH) as f:
        career_stats = {int(k): v for k, v in json.load(f).items()}

    with open(CAREER_BABIP_PATH) as f:
        career_babip = {int(k): float(v["career_babip"])
                        for k, v in json.load(f).items()
                        if v.get("career_babip") is not None}

    patterns = {}
    if SEASONAL_PATH.exists():
        with open(SEASONAL_PATH) as f:
            for r in json.load(f):
                patterns[int(r["player_id"])] = r

    names = load_names()

    all_rows = []
    for year in YEARS:
        rows = run_year_rows(year, career_stats, patterns, career_babip)
        if rows is not None:
            all_rows.append(rows)
            print(f"  {year}: {len(rows)} evaluated rows")

    df = pd.concat(all_rows, ignore_index=True)
    df["name"] = df["batter"].map(names).fillna(df["batter"].astype(str))

    cols = ["year", "batter", "name", "signal", "luck_score",
            "april_woba", "april_xwoba", "outcome_woba", "woba_change",
            "outcome", "correct", "april_pa", "outcome_pa", "team"]
    out = df[[c for c in cols if c in df.columns]].copy()
    out = out.sort_values(["year", "luck_score"], ascending=[True, False])

    print(f"\nTotal rows: {len(out)}")

    # ──────────────────────────────────────────────────────────────────
    # CATEGORY 1 — MARQUEE HITS
    # ──────────────────────────────────────────────────────────────────
    buy_hits  = out[(out["luck_score"] > 0.08) & (out["woba_change"] > 0.040)].copy()
    sell_hits = out[(out["luck_score"] < -0.08) & (out["woba_change"] < -0.040)].copy()
    marquee   = pd.concat([buy_hits, sell_hits]).sort_values("woba_change", key=abs, ascending=False)

    print(f"\n{'='*90}")
    print("CATEGORY 1 — MARQUEE HITS (strong correct calls, |luck|>0.08, |woba_change|>0.040)")
    print(f"{'='*90}")
    print(f"  Buy-low hits : {len(buy_hits)}   Sell-high hits: {len(sell_hits)}")
    print()
    print(f"  {'Player':<24} {'Yr':>4}  {'Signal':<12} {'Apr wOBA':>9} {'Apr xwOBA':>10} {'May-Jul wOBA':>13} {'Change':>8} {'Luck':>8}")
    print(f"  {'-'*95}")
    shown = 0
    for _, r in marquee.head(25).iterrows():
        print(f"  {r['name']:<24} {int(r['year']):>4}  {r['signal']:<12} "
              f"{r['april_woba']:>9.3f} {r['april_xwoba']:>10.3f} {r['outcome_woba']:>13.3f} "
              f"{r['woba_change']:>+8.3f} {r['luck_score']:>+8.4f}")
        shown += 1
        if shown >= 25:
            break

    # ──────────────────────────────────────────────────────────────────
    # CATEGORY 2 — NEAR MISSES
    # ──────────────────────────────────────────────────────────────────
    slight_buy_hits  = out[
        (out["luck_score"].between(0.025, 0.060)) &
        (out["woba_change"].between(0.020, 0.040))
    ].copy()
    slight_sell_hits = out[
        (out["luck_score"].between(-0.060, -0.025)) &
        (out["woba_change"].between(-0.040, -0.020))
    ].copy()
    near_miss = pd.concat([slight_buy_hits, slight_sell_hits]).sort_values("woba_change", key=abs, ascending=False)

    print(f"\n{'='*90}")
    print("CATEGORY 2 — NEAR MISSES (mild signals that still worked)")
    print(f"{'='*90}")
    print(f"  Slight-buy hits : {len(slight_buy_hits)}   Slight-sell hits: {len(slight_sell_hits)}")
    print()
    print(f"  {'Player':<24} {'Yr':>4}  {'Signal':<12} {'Apr wOBA':>9} {'Apr xwOBA':>10} {'May-Jul wOBA':>13} {'Change':>8} {'Luck':>8}")
    print(f"  {'-'*95}")
    for _, r in near_miss.head(15).iterrows():
        print(f"  {r['name']:<24} {int(r['year']):>4}  {r['signal']:<12} "
              f"{r['april_woba']:>9.3f} {r['april_xwoba']:>10.3f} {r['outcome_woba']:>13.3f} "
              f"{r['woba_change']:>+8.3f} {r['luck_score']:>+8.4f}")

    # ──────────────────────────────────────────────────────────────────
    # CATEGORY 3 — HONEST MISSES
    # ──────────────────────────────────────────────────────────────────
    buy_misses  = out[(out["luck_score"] > 0.08) & (out["woba_change"] < -0.020)].copy()
    sell_misses = out[(out["luck_score"] < -0.08) & (out["woba_change"] > 0.020)].copy()
    misses = pd.concat([buy_misses, sell_misses]).sort_values("luck_score", key=abs, ascending=False)

    print(f"\n{'='*90}")
    print("CATEGORY 3 — HONEST MISSES (model was wrong, |luck|>0.08)")
    print(f"{'='*90}")
    print(f"  Buy-low misses : {len(buy_misses)}   Sell-high misses: {len(sell_misses)}")
    print()
    print(f"  {'Player':<24} {'Yr':>4}  {'Signal':<12} {'Apr wOBA':>9} {'Apr xwOBA':>10} {'May-Jul wOBA':>13} {'Change':>8} {'Luck':>8}")
    print(f"  {'-'*95}")
    for _, r in misses.head(20).iterrows():
        print(f"  {r['name']:<24} {int(r['year']):>4}  {r['signal']:<12} "
              f"{r['april_woba']:>9.3f} {r['april_xwoba']:>10.3f} {r['outcome_woba']:>13.3f} "
              f"{r['woba_change']:>+8.3f} {r['luck_score']:>+8.4f}")

    # ──────────────────────────────────────────────────────────────────
    # SKENES-LIKE: biggest negative luck in 2024/2025
    # ──────────────────────────────────────────────────────────────────
    recent = out[out["year"].isin([2024, 2025])].copy()
    luckiest = recent.sort_values("luck_score").head(30)

    print(f"\n{'='*90}")
    print("SKENES-LIKE — Most negative luck_score (luckiest performers) in 2024-2025")
    print(f"{'='*90}")
    print()
    print(f"  {'Player':<24} {'Yr':>4}  {'Signal':<12} {'Apr wOBA':>9} {'Apr xwOBA':>10} {'May-Jul wOBA':>13} {'Change':>8} {'Luck':>8}")
    print(f"  {'-'*95}")
    for _, r in luckiest.head(20).iterrows():
        print(f"  {r['name']:<24} {int(r['year']):>4}  {r['signal']:<12} "
              f"{r['april_woba']:>9.3f} {r['april_xwoba']:>10.3f} {r['outcome_woba']:>13.3f} "
              f"{r['woba_change']:>+8.3f} {r['luck_score']:>+8.4f}")

    # Export full CSV for reference
    out.to_csv(BASE_DIR / "backtest_v4_player_rows.csv", index=False)
    print(f"\n[exported backtest_v4_player_rows.csv]")


if __name__ == "__main__":
    main()
