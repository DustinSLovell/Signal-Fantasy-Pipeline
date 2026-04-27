"""
Multi-Year Within-Season Backtest v6
=====================================
TWO MODULES:

  HITTER MODULE  — identical to v5 (confirms 86.1% holds; no logic changes)
    OAA per-batter opponent adjustment + tightened SLIGHT_SELL threshold (-0.065)

  PITCHER MODULE — enhanced backtest_pitcher_within_season.py with:
    1. 2 IP per-start minimum: exclude starts < 2 IP from ERA/BABIP/FIP signals
    2. Volatility dampening: if disaster_rate > 0.30 OR start_variance > 4.0,
       dampen buy signals ×0.90 before classifying

v5 hitter benchmarks:
  Overall=86.1%  BUY_LOW=92.8%  SLIGHT_SELL=84.1%  SELL_HIGH=94.8%  vs RTM=+17.9pp

Original pitcher benchmark (backtest_pitcher_within_season.py, no filters):
  Overall=82.4%  SELL_HIGH=100.0%  BUY_LOW=83.3%  vs RTM=+14.2pp
"""

import io
import json
import math
import os
import sys
import numpy as np
import pandas as pd
from pathlib import Path

# Import before stdout re-wrap to avoid double-buffer ownership conflict
from backtest_pitcher_within_season import compute_pitcher_stats as _pitcher_stats_orig

# Detach first so the old wrapper doesn't close the buffer when it's GC'd
if isinstance(sys.stdout, io.TextIOWrapper):
    _buf = sys.stdout.detach()
else:
    _buf = getattr(sys.stdout, "buffer", sys.stdout)
sys.stdout = io.TextIOWrapper(_buf, encoding="utf-8", errors="replace")

BASE_DIR          = Path(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR         = BASE_DIR / "backtest_cache"
CACHE_DIR.mkdir(exist_ok=True)

# ─── Shared data paths ────────────────────────────────────────────────────────
SEASONAL_PATH     = BASE_DIR / "data" / "seasonal_patterns.json"
CAREER_PATH       = BASE_DIR / "data" / "career_stats.json"
CAREER_BABIP_PATH = BASE_DIR / "data" / "hitter_career_babip.json"
TEAM_OAA_PATH     = BASE_DIR / "data" / "team_oaa_2025.csv"
STUFF_PATH        = BASE_DIR / "data" / "pitcher_stuff_plus_2025.csv"
PITCHER_BABIP_P   = BASE_DIR / "data" / "pitcher_career_babip.json"

# ─── Hitter constants (v5 identical) ─────────────────────────────────────────
H_YEARS           = [2022, 2023, 2024, 2025]
MIN_APRIL_PA      = 80
MIN_OUTCOME_PA    = 100
FLAT_THRESHOLD    = 0.015
RTM_BASELINE      = 0.682
LEAGUE_AVG_BABIP  = 0.300
EV_THRESHOLD      = 1.0
SELL_HIGH_THRESH  = -0.065
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

SIGNAL_MAP_H = {
    'BUY_LOW':    'IMPROVED',
    'SLIGHT_BUY': 'IMPROVED',
    'SELL_HIGH':  'DECLINED',
    'SLIGHT_SELL':'DECLINED',
}

PHASE_C = {
    'vshape_buy':  1.20, 'vshape_sell': None,
    'slow_buy':    1.10, 'summer_buy':  1.10,
    'fader_sell':  1.15, 'fader_buy':   0.90,
}

# ─── Pitcher constants ────────────────────────────────────────────────────────
MIN_START_IP_P    = 2.0     # per-start floor for ERA/BABIP signal
MIN_APRIL_IP_P    = 15.0    # minimum total April IP (same as original)
MIN_OUTCOME_IP_P  = 30.0    # minimum May-July IP
ERA_FLAT_P        = 0.40    # minimum ERA change to count as outcome
FIP_CONST         = 3.10
LEAGUE_AVG_ERA    = 4.20
LEAGUE_AVG_BABIP_P= 0.300

P_BUY_LOW_THRESH    =  1.20
P_SLIGHT_BUY_THRESH =  0.60
P_SELL_HIGH_THRESH  = -1.20
P_SLIGHT_SELL_THRESH= -0.60

DISASTER_ERA_P   = 10.0
DISASTER_RATE_P  = 0.30
START_VAR_P      = 4.0
VOL_DAMP         = 0.90

SIGNAL_MAP_P = {
    'BUY_LOW':    'IMPROVED',
    'SLIGHT_BUY': 'IMPROVED',
    'SELL_HIGH':  'DECLINED',
    'SLIGHT_SELL':'DECLINED',
}

P_OUT_EVENTS = {
    "field_out","grounded_into_double_play","double_play","force_out",
    "fielders_choice_out","fielders_choice","sac_fly","sac_bunt",
    "strikeout","strikeout_double_play",
}
P_BIP_EVENTS = {
    "single","double","triple","field_out","grounded_into_double_play",
    "force_out","double_play","fielders_choice",
}

# ═══════════════════════════════════════════════════════════════════════════════
# HITTER MODULE — identical to v5
# ═══════════════════════════════════════════════════════════════════════════════

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

def _babip_age_mult(age: int) -> float:
    if age >= 39: return 0.88
    if age >= 37: return 0.91
    if age >= 35: return 0.94
    if age >= 32: return 0.97
    return 1.0

def load_career_babip() -> dict:
    if not CAREER_BABIP_PATH.exists():
        return {}
    with open(CAREER_BABIP_PATH) as f:
        raw = json.load(f)
    result = {}
    for pid_str, rec in raw.items():
        cb = rec.get("career_babip")
        if cb is not None:
            result[int(pid_str)] = float(cb)
    return result

def load_oaa_adj() -> dict:
    if not TEAM_OAA_PATH.exists():
        return {}
    df = pd.read_csv(TEAM_OAA_PATH, usecols=["team_abbr", "babip_adj"])
    return dict(zip(df["team_abbr"], df["babip_adj"]))

def load_opponent_oaa_for_year(year: int, oaa_adj: dict) -> dict:
    if not oaa_adj:
        return {}
    parquet_path = CACHE_DIR / f"april_statcast_{year}.parquet"
    alt_path     = CACHE_DIR / f"pitcher_statcast_april_{year}.parquet"
    if not parquet_path.exists() and alt_path.exists():
        parquet_path = alt_path
    if parquet_path.exists():
        sc = pd.read_parquet(parquet_path,
                             columns=["batter","home_team","away_team","inning_topbot"])
    else:
        print(f"    Fetching April {year} statcast for OAA (will cache)...")
        try:
            import pybaseball as pb
            pb.cache.enable()
            start, end = f"{year}-04-01", f"{year}-04-30"
            dates = pd.date_range(start, end, freq="W-SUN")
            starts_l = [start] + [str(d.date()) for d in dates[:-1]]
            ends_l   = [str(d.date()) for d in dates] + [end]
            frames = []
            for s, e in list(dict.fromkeys(zip(starts_l, ends_l))):
                try:
                    chunk = pb.statcast(start_dt=s, end_dt=e)
                    if chunk is not None and not chunk.empty:
                        frames.append(chunk[["batter","home_team","away_team","inning_topbot"]].copy())
                except Exception:
                    pass
            if not frames:
                return {}
            sc = pd.concat(frames, ignore_index=True)
            sc.to_parquet(parquet_path, index=False)
            print(f"    Cached {len(sc):,} rows → {parquet_path.name}")
        except Exception as ex:
            print(f"    WARNING: could not fetch April {year} statcast: {ex}")
            return {}
    needed = {"batter","home_team","away_team","inning_topbot"}
    if not needed.issubset(sc.columns):
        return {}
    sc = sc[sc["inning_topbot"].isin(["Top","Bot"])].copy()
    sc["opponent_team"] = sc.apply(
        lambda r: r["home_team"] if r["inning_topbot"] == "Top" else r["away_team"], axis=1)
    sc["oaa_adj"] = sc["opponent_team"].map(oaa_adj).fillna(0.0)
    result = sc.groupby("batter")["oaa_adj"].mean().to_dict()
    return {int(k): float(v) for k, v in result.items()}

def classify_h(score: float) -> str:
    if score >= 0.040:              return "BUY_LOW"
    if score >= 0.020:              return "SLIGHT_BUY"
    if score <= SELL_HIGH_THRESH:   return "SELL_HIGH"
    if score <= SLIGHT_SELL_THRESH: return "SLIGHT_SELL"
    return "NEUTRAL"

def bucket_stats_h(eval_df: pd.DataFrame) -> dict:
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

def run_year_h(year, career_stats, patterns, career_babip, opp_oaa) -> dict | None:
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
    april["park_factor"] = april["team"].map(PARK_FACTORS_H).fillna(1.0) if "team" in april.columns else 1.0

    batted = april[april["bb_type"].notna() & (april["bb_type"] != "")].copy()
    batted["is_bip"] = batted["events"].isin(BIP_EVENTS_H).astype(int)
    batted["is_hit"] = batted["events"].isin({"single","double","triple"}).astype(int)
    batted["is_gb"]  = (batted["bb_type"] == "ground_ball").astype(int)
    bip_agg = batted.groupby("batter").agg(
        bip=("is_bip","sum"), hits_bip=("is_hit","sum"), gb=("is_gb","sum")).reset_index()

    bbe = april[april["launch_speed"].notna() & april["launch_angle"].notna()].copy()
    bbe_agg = bbe.groupby("batter").apply(
        lambda s: pd.Series({
            "sweet_spot_count": int(((s["launch_speed"]>=98) & s["launch_angle"].between(8,32)).sum()),
            "bbe_total":         len(s),
            "avg_exit_velocity": float(s["launch_speed"].mean()),
        })
    ).reset_index()
    has_bbe = len(bbe_agg) > 0

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
    n_career   = int((signals["babip_baseline"] != LEAGUE_AVG_BABIP).sum())
    n_fallback = int((signals["babip_baseline"] == LEAGUE_AVG_BABIP).sum())

    def _age_adj_babip(row) -> float:
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

    n_oaa_top = n_oaa_bot = 0
    if opp_oaa:
        signals["oaa_babip_adj"] = signals["batter"].apply(lambda b: opp_oaa.get(int(b), 0.0))
        signals["babip_expected"] = (signals["babip_expected"] + signals["oaa_babip_adj"]).round(4)
        n_oaa_top = int((signals["oaa_babip_adj"] < 0).sum())
        n_oaa_bot = int((signals["oaa_babip_adj"] > 0).sum())
    else:
        signals["oaa_babip_adj"] = 0.0

    l4_gb_high = l4_gb_low = 0
    if signals["gb_rate"].notna().any():
        gb_high = signals["gb_rate"] > 0.50
        gb_low  = signals["gb_rate"] < 0.35
        signals.loc[gb_high, "babip_expected"] -= 0.010
        signals.loc[gb_low,  "babip_expected"] += 0.008
        l4_gb_high = int(gb_high.sum())
        l4_gb_low  = int(gb_low.sum())

    signals["babip_luck"] = signals["babip_expected"] - signals["babip"]
    signals = signals[signals["april_pa"] >= MIN_APRIL_PA].copy()
    signals["luck_score"] = (
        signals["xwoba_gap"]  * 0.60 +
        signals["babip_luck"] * 0.40
    ).round(4)

    l2_amp = l2_damp = 0
    if signals["sweet_spot_rate"].notna().any():
        buy     = signals["luck_score"] > 0
        high_ss = buy & (signals["sweet_spot_rate"] > 0.12)
        low_ss  = buy & (signals["sweet_spot_rate"] < 0.06)
        signals.loc[high_ss, "luck_score"] = (signals.loc[high_ss,"luck_score"] * 1.05).round(4)
        signals.loc[low_ss,  "luck_score"] = (signals.loc[low_ss, "luck_score"] * 0.95).round(4)
        l2_amp, l2_damp = int(high_ss.sum()), int(low_ss.sum())

    l3_both = l3_one = l3_skip = 0
    if signals["avg_exit_velocity"].notna().any():
        for idx, row in signals.iterrows():
            if row["luck_score"] <= 0:
                continue
            career_ev = (career_stats.get(int(row["batter"])) or {}).get("avg_exit_velocity")
            if career_ev is None or pd.isna(row["avg_exit_velocity"]):
                l3_skip += 1; continue
            ev_below  = (row["avg_exit_velocity"] - career_ev) < -EV_THRESHOLD
            ss        = row["sweet_spot_rate"]
            low_ss_ev = pd.notna(ss) and ss < 0.08
            if ev_below and low_ss_ev:
                signals.at[idx, "luck_score"] = round(row["luck_score"] * 0.85, 4); l3_both += 1
            elif ev_below or low_ss_ev:
                signals.at[idx, "luck_score"] = round(row["luck_score"] * 0.93, 4); l3_one  += 1

    l5_elite = l5_poor = 0
    if signals["bb_rate"].notna().any() and signals["k_rate"].notna().any():
        buy_mask   = signals["luck_score"] > 0
        elite_disc = buy_mask & (signals["bb_rate"] > 0.10) & (signals["k_rate"] < 0.18)
        poor_disc  = buy_mask & ((signals["bb_rate"] < 0.06) | (signals["k_rate"] > 0.28))
        signals.loc[elite_disc, "luck_score"] = (signals.loc[elite_disc,"luck_score"] * 1.08).round(4)
        signals.loc[poor_disc,  "luck_score"] = (signals.loc[poor_disc, "luck_score"] * 0.88).round(4)
        l5_elite, l5_poor = int(elite_disc.sum()), int(poor_disc.sum())

    l6_modified = 0
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
                l6_modified += 1

    signals["signal"]   = signals["luck_score"].apply(classify_h)
    sig_counts          = signals["signal"].value_counts().to_dict()

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

    eval_df = merged[merged["signal"].isin(SIGNAL_MAP_H) & (merged["outcome"] != "FLAT")].copy()
    eval_df["correct"] = eval_df.apply(lambda r: r["outcome"] == SIGNAL_MAP_H[r["signal"]], axis=1)
    stats   = bucket_stats_h(eval_df)

    gradient = {
        sig: merged[merged["signal"] == sig]["woba_change"].mean()
        if (merged["signal"] == sig).sum() >= 3 else float("nan")
        for sig in ["BUY_LOW","SLIGHT_BUY","NEUTRAL","SLIGHT_SELL","SELL_HIGH"]
    }

    return {
        "year":       year,
        "stats":      stats,
        "gradient":   gradient,
        "sig_counts": sig_counts,
        "n_signals":  len(signals),
        "n_eval":     stats["OVERALL"][0],
        "n_flat":     int((merged["outcome"] == "FLAT").sum()),
        "l3_both":    l3_both,
        "l3_one":     l3_one,
        "n_career":   n_career,
        "n_fallback": n_fallback,
        "n_oaa_top":  n_oaa_top,
        "n_oaa_bot":  n_oaa_bot,
    }

# ═══════════════════════════════════════════════════════════════════════════════
# PITCHER MODULE — 2 IP minimum + volatility dampening
# ═══════════════════════════════════════════════════════════════════════════════

def _load_pitcher_sc(cache_path: Path, fallback_path: Path) -> pd.DataFrame:
    for p in [cache_path, fallback_path]:
        if p and p.exists():
            print(f"  Loading from cache: {p.name}")
            return pd.read_parquet(p)
    return pd.DataFrame()


def _prep_pitcher_sc(sc: pd.DataFrame) -> pd.DataFrame:
    sc = sc.copy()
    sc["pitcher"] = pd.to_numeric(sc["pitcher"], errors="coerce")
    sc = sc[sc["pitcher"].notna()].copy()
    sc["pitcher"] = sc["pitcher"].astype(int)
    ev_mask = sc["events"].notna() & (sc["events"] != "")
    sc["is_out"]     = (sc["events"].isin(P_OUT_EVENTS) & ev_mask).astype(int)
    sc["is_dp"]      = (sc["events"].isin({"grounded_into_double_play","double_play",
                                             "strikeout_double_play"}) & ev_mask).astype(int)
    return sc


def compute_per_start_pitcher(sc: pd.DataFrame) -> pd.DataFrame:
    """Per-(pitcher, game_pk) stats for 2 IP filtering and volatility analysis."""
    if "game_pk" not in sc.columns:
        return pd.DataFrame(columns=["pitcher","game_pk","start_ip","start_ra",
                                     "start_era","qualifying","is_qs","is_disaster"])
    sc = _prep_pitcher_sc(sc)
    ev = sc[sc["events"].notna() & (sc["events"] != "")].copy()

    # IP per start
    outs_s = ev.groupby(["pitcher","game_pk"]).agg(
        outs=("is_out","sum"), dp_outs=("is_dp","sum")).reset_index()
    outs_s["start_ip"] = (outs_s["outs"] + outs_s["dp_outs"]) / 3.0

    # Runs per start (post_bat_score - bat_score)
    if "post_bat_score" in ev.columns and "bat_score" in ev.columns:
        run_ev = ev[ev["post_bat_score"].notna() & ev["bat_score"].notna()].copy()
        run_ev["runs_scored"] = (run_ev["post_bat_score"] - run_ev["bat_score"]).clip(lower=0)
        runs_s = run_ev.groupby(["pitcher","game_pk"])["runs_scored"].sum().reset_index()
        runs_s.rename(columns={"runs_scored":"start_ra"}, inplace=True)
    else:
        runs_s = outs_s[["pitcher","game_pk"]].copy()
        runs_s["start_ra"] = 0.0

    starts = outs_s.merge(runs_s, on=["pitcher","game_pk"], how="left")
    starts["start_ra"] = starts["start_ra"].fillna(0.0)
    starts["start_era"] = np.where(
        starts["start_ip"] > 0,
        (starts["start_ra"] / starts["start_ip"]) * 9,
        np.nan
    ).round(2)
    starts["qualifying"]  = starts["start_ip"] >= MIN_START_IP_P
    starts["is_qs"]       = (starts["start_ip"] >= 6.0) & (starts["start_ra"] <= 3)
    starts["is_disaster"] = (starts["start_era"] > DISASTER_ERA_P) & starts["qualifying"]
    return starts[["pitcher","game_pk","start_ip","start_ra",
                   "start_era","qualifying","is_qs","is_disaster"]]


def compute_volatility_p(start_stats: pd.DataFrame) -> pd.DataFrame:
    """Per-pitcher volatility metrics from per-start data."""
    results = []
    for pid, grp in start_stats.groupby("pitcher"):
        total       = len(grp)
        disaster_n  = int(grp["is_disaster"].sum())
        qs_n        = int(grp["is_qs"].sum())
        d_rate      = disaster_n / total if total > 0 else 0.0
        qual_eras   = grp.loc[grp["qualifying"],"start_era"].dropna()
        start_var   = float(qual_eras.std()) if len(qual_eras) >= 2 else float("nan")
        flagged     = (d_rate > DISASTER_RATE_P
                       or (not math.isnan(start_var) and start_var > START_VAR_P))
        results.append({
            "pitcher":       int(pid),
            "total_starts":  total,
            "disaster_rate": round(d_rate, 3),
            "qs_rate":       round(qs_n / total, 3) if total > 0 else 0.0,
            "start_variance":round(start_var, 2) if not math.isnan(start_var) else None,
            "volatility_flag": flagged,
        })
    return pd.DataFrame(results)


def compute_pitcher_stats_v6(sc: pd.DataFrame, start_stats: pd.DataFrame) -> pd.DataFrame:
    """
    Pitcher season stats with 2 IP per-start filter applied to ERA/BABIP/FIP.
    Contact quality metrics (hard hit, SwStr) use all appearances.
    Falls back to all-appearances ERA for pure relievers (no qualifying starts).
    """
    sc = _prep_pitcher_sc(sc)
    ev = sc[sc["events"].notna() & (sc["events"] != "")].copy()

    # Build qualifying-start-only subset (for ERA/BABIP)
    qual_pairs = pd.DataFrame()
    if "game_pk" in start_stats.columns and not start_stats.empty:
        qual_pairs = (start_stats[start_stats["qualifying"]][["pitcher","game_pk"]]
                      .assign(_q=True))
        sc_mq  = sc.merge(qual_pairs, on=["pitcher","game_pk"], how="left") if "game_pk" in sc.columns else sc.assign(_q=False)
        sc_qual = sc[sc_mq["_q"].fillna(False).values].copy()
        ev_qual = sc_qual[sc_qual["events"].notna() & (sc_qual["events"] != "")].copy()
    else:
        sc_qual = sc.copy()
        ev_qual = ev.copy()

    def _ip_from_ev(df):
        a = df.groupby("pitcher").agg(
            outs=("is_out","sum"), dp_outs=("is_dp","sum")).reset_index()
        a["ip"] = (a["outs"] + a["dp_outs"]) / 3.0
        return a.set_index("pitcher")["ip"]

    ip_qual = _ip_from_ev(ev_qual)
    ip_all  = _ip_from_ev(ev)

    # Runs from qualifying starts
    if "post_bat_score" in ev_qual.columns and "bat_score" in ev_qual.columns:
        re = ev_qual[ev_qual["post_bat_score"].notna() & ev_qual["bat_score"].notna()].copy()
        re["runs_scored"] = (re["post_bat_score"] - re["bat_score"]).clip(lower=0)
        ra_qual = re.groupby("pitcher")["runs_scored"].sum()
    else:
        ra_qual = pd.Series(dtype=float)

    # ERA from qualifying starts; fallback to all-appearances
    era_qual = (ra_qual / (ip_qual / 9)).where(ip_qual > 0).round(2)
    if "post_bat_score" in ev.columns and "bat_score" in ev.columns:
        re_all = ev[ev["post_bat_score"].notna() & ev["bat_score"].notna()].copy()
        re_all["runs_scored"] = (re_all["post_bat_score"] - re_all["bat_score"]).clip(lower=0)
        ra_all = re_all.groupby("pitcher")["runs_scored"].sum()
        era_all = (ra_all / (ip_all / 9)).where(ip_all > 0).round(2)
    else:
        era_all = pd.Series(dtype=float)

    era_final = era_qual.combine_first(era_all)

    # FIP from qualifying starts
    ev_qual["is_k"]  = ev_qual["events"].isin({"strikeout","strikeout_double_play"}).astype(int)
    ev_qual["is_bb"] = ev_qual["events"].isin({"walk","intent_walk"}).astype(int)
    ev_qual["is_hr"] = (ev_qual["events"] == "home_run").astype(int)
    fip_agg = ev_qual.groupby("pitcher").agg(
        k=("is_k","sum"), bb=("is_bb","sum"), hr=("is_hr","sum")).reset_index()
    fip_agg = fip_agg.set_index("pitcher")
    fip_series = ((13 * fip_agg["hr"] + 3 * fip_agg["bb"] - 2 * fip_agg["k"]) / ip_qual + FIP_CONST
                  ).where(ip_qual > 0).round(2)

    # BABIP from qualifying starts; fallback to all
    ev_qual["is_bip_nh"] = ev_qual["events"].isin(P_BIP_EVENTS).astype(int)
    ev_qual["is_hit_nh"] = ev_qual["events"].isin({"single","double","triple"}).astype(int)
    babip_agg = ev_qual.groupby("pitcher").agg(
        bip=("is_bip_nh","sum"), hits_nh=("is_hit_nh","sum")).reset_index().set_index("pitcher")
    babip_qual = (babip_agg["hits_nh"] / babip_agg["bip"]).where(babip_agg["bip"] > 0).round(3)

    ev["is_bip_nh"] = ev["events"].isin(P_BIP_EVENTS).astype(int)
    ev["is_hit_nh"] = ev["events"].isin({"single","double","triple"}).astype(int)
    babip_all_agg = ev.groupby("pitcher").agg(
        bip=("is_bip_nh","sum"), hits_nh=("is_hit_nh","sum")).reset_index().set_index("pitcher")
    babip_all = (babip_all_agg["hits_nh"] / babip_all_agg["bip"]).where(babip_all_agg["bip"] > 0).round(3)
    babip_final = babip_qual.combine_first(babip_all)

    # PA count (total, for IP filter)
    pa_agg = ev.groupby("pitcher").size().rename("pa")

    # Team
    team_s = pd.Series(dtype=str, name="team")
    if "home_team" in sc.columns and "away_team" in sc.columns and "inning_topbot" in sc.columns:
        sc["p_team"] = sc.apply(
            lambda r: r["away_team"] if r["inning_topbot"]=="Top" else r["home_team"], axis=1)
        team_s = sc.groupby("pitcher")["p_team"].agg(lambda x: x.mode().iloc[0])

    # Name
    name_s = pd.Series(dtype=str, name="name")
    if "player_name" in sc.columns:
        name_s = sc.groupby("pitcher")["player_name"].first()

    agg = pd.DataFrame({
        "ip":    ip_all,
        "era":   era_final,
        "fip":   fip_series,
        "babip": babip_final,
    })
    agg = agg.join(team_s, how="left").join(name_s, how="left")
    agg = agg.reset_index().rename(columns={"index":"pitcher"})
    return agg


def classify_p(gap: float) -> str:
    if gap >= P_BUY_LOW_THRESH:     return "BUY_LOW"
    if gap >= P_SLIGHT_BUY_THRESH:  return "SLIGHT_BUY"
    if gap <= P_SELL_HIGH_THRESH:   return "SELL_HIGH"
    if gap <= P_SLIGHT_SELL_THRESH: return "SLIGHT_SELL"
    return "NEUTRAL"


def load_stuff_plus() -> dict:
    if not STUFF_PATH.exists():
        return {}
    df = pd.read_csv(STUFF_PATH)
    id_col  = "pitcher_id" if "pitcher_id"  in df.columns else df.columns[0]
    val_col = "stuff_plus_avg" if "stuff_plus_avg" in df.columns else df.columns[2]
    return dict(zip(df[id_col].astype(int), df[val_col].astype(float)))


def load_career_babip_p() -> dict:
    if not PITCHER_BABIP_P.exists():
        return {}
    with open(PITCHER_BABIP_P) as f:
        raw = json.load(f)
    return {int(k): float(v["career_babip_allowed"])
            for k, v in raw.items()
            if v.get("career_babip_allowed") is not None}


def run_pitcher_backtest(label: str, use_2ip: bool, use_volatility: bool) -> dict:
    """
    Single pitcher backtest run.  label distinguishes versions in output.
    use_2ip:        apply 2 IP per-start minimum to ERA/BABIP/FIP computation.
    use_volatility: apply ×0.90 dampening to buy signals for flagged pitchers.
    Returns accuracy dict.
    """
    print(f"\n  [{label}] Loading April 2024 pitcher Statcast...")
    april_sc = _load_pitcher_sc(
        CACHE_DIR / "pitcher_statcast_april_2024.parquet",
        CACHE_DIR / "april_statcast_2024.parquet",
    )
    print(f"  [{label}] Loading May-July 2024 pitcher Statcast...")
    outcome_sc = _load_pitcher_sc(
        CACHE_DIR / "pitcher_statcast_mayjuly_2024.parquet",
        None,
    )
    if april_sc.empty or outcome_sc.empty:
        print(f"  [{label}] ERROR: missing data")
        return {}

    # Compute per-start stats (needed for both filtering and volatility)
    april_starts  = compute_per_start_pitcher(april_sc)
    outcome_starts= compute_per_start_pitcher(outcome_sc)

    if use_2ip:
        apr_stats = compute_pitcher_stats_v6(april_sc,  april_starts)
        out_stats = compute_pitcher_stats_v6(outcome_sc, outcome_starts)
    else:
        # Original flat computation (no per-start filter)
        apr_stats = _pitcher_stats_orig(april_sc)
        out_stats = _pitcher_stats_orig(outcome_sc)
        apr_stats = apr_stats.rename(columns={"era":"era","fip":"fip","babip":"babip","ip":"ip","team":"team","name":"name"})
        out_stats = out_stats.rename(columns={"era":"era","fip":"fip","babip":"babip","ip":"ip","team":"team","name":"name"})

    # Minimum IP gate
    apr_stats = apr_stats[apr_stats["ip"] >= MIN_APRIL_IP_P].copy()
    out_stats = out_stats[out_stats["ip"] >= MIN_OUTCOME_IP_P].copy()
    n_excluded_starts = int((~april_starts["qualifying"]).sum()) if use_2ip else 0

    # Load modifiers
    stuff_plus   = load_stuff_plus()
    career_babip = load_career_babip_p()

    # Signal computation
    sig = apr_stats.copy()
    sig["park_factor"] = sig["team"].map(PARK_FACTORS_H).fillna(1.0) if "team" in sig.columns else 1.0
    sig["career_babip"] = sig["pitcher"].map(career_babip).fillna(LEAGUE_AVG_BABIP_P)
    sig["babip_expected"] = sig["career_babip"] * sig["park_factor"]
    sig["babip_luck"]     = sig["babip_expected"] - sig["babip"]
    sig["era_fip_gap"]    = sig["era"] - sig["fip"]

    sig["stuff_plus"] = sig["pitcher"].map(stuff_plus)
    sig["luck_score_raw"] = (
        sig["era_fip_gap"]  * 0.70 +
        sig["babip_luck"]   * 0.30 * 9
    ).round(3)

    def _apply_stuff(row):
        score = row["luck_score_raw"]
        sp    = row["stuff_plus"]
        if pd.isna(sp) or score <= 0:
            return score
        if sp >= 115: return round(score * 1.15, 3)
        if sp < 90:   return round(score * 0.80, 3)
        return score

    sig["luck_score"] = sig.apply(_apply_stuff, axis=1)

    # Volatility dampening
    n_vol_flagged = n_vol_dampened = 0
    if use_volatility and not april_starts.empty:
        vol_df = compute_volatility_p(april_starts)
        vol_df["pitcher"] = vol_df["pitcher"].astype(int)
        sig = sig.merge(vol_df[["pitcher","disaster_rate","start_variance","volatility_flag"]],
                        on="pitcher", how="left")
        sig["volatility_flag"] = sig["volatility_flag"].fillna(False)
        n_vol_flagged = int(sig["volatility_flag"].sum())
        buy_vol = sig["volatility_flag"] & (sig["luck_score"] > 0)
        n_vol_dampened = int(buy_vol.sum())
        sig.loc[buy_vol, "luck_score"] = (sig.loc[buy_vol, "luck_score"] * VOL_DAMP).round(3)
    else:
        sig["volatility_flag"] = False

    sig["signal"] = sig["era_fip_gap"].apply(classify_p)

    # Outcomes
    merged = sig.merge(
        out_stats[["pitcher","era","fip","ip"]].rename(columns={
            "era":"outcome_era","fip":"outcome_fip","ip":"outcome_ip"}),
        on="pitcher", how="inner"
    )
    merged["era_change"] = merged["outcome_era"] - merged["era"]
    merged["outcome"] = np.where(
        merged["era_change"] <= -ERA_FLAT_P, "IMPROVED",
        np.where(merged["era_change"] >=  ERA_FLAT_P, "DECLINED", "FLAT")
    )

    eval_df = merged[
        merged["signal"].isin(SIGNAL_MAP_P) & (merged["outcome"] != "FLAT")
    ].copy()
    eval_df["correct"] = eval_df.apply(
        lambda r: r["outcome"] == SIGNAL_MAP_P[r["signal"]], axis=1)

    stats = {}
    for s in ["BUY_LOW","SLIGHT_BUY","SELL_HIGH","SLIGHT_SELL"]:
        grp  = eval_df[eval_df["signal"] == s]
        n    = len(grp)
        c    = int(grp["correct"].sum()) if n > 0 else 0
        stats[s] = (n, c, c / n if n > 0 else float("nan"))
    ov_n = len(eval_df)
    ov_c = int(eval_df["correct"].sum())
    stats["OVERALL"] = (ov_n, ov_c, ov_c / ov_n if ov_n > 0 else float("nan"))

    sig_dist = sig["signal"].value_counts().to_dict()
    return {
        "label":           label,
        "stats":           stats,
        "sig_dist":        sig_dist,
        "n_signal":        len(sig),
        "n_eval":          ov_n,
        "n_excluded_starts":n_excluded_starts,
        "n_vol_flagged":   n_vol_flagged,
        "n_vol_dampened":  n_vol_dampened,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# DISPLAY HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def fmt_pct(v, w=6):
    return f"{v*100:{w}.1f}%" if not (isinstance(v, float) and math.isnan(v)) else f"{'n/a':>{w}}"

def fmt_pp(v, w=6):
    return f"{v*100:>+{w}.1f}pp" if not (isinstance(v, float) and math.isnan(v)) else f"{'n/a':>{w}}"


def print_hitter_table(results: list):
    yrs  = [r["year"] for r in results]
    SIGS = ["BUY_LOW","SLIGHT_BUY","SELL_HIGH","SLIGHT_SELL","OVERALL"]
    CW   = 8
    sep  = "|"
    top  = "+" + "-"*13 + "+" + ("-"*CW+"+") * len(yrs) + "-"*(CW+1) + "+"
    mid  = top

    print(top)
    hdr = f"{sep} {'Signal':<11} {sep}" + \
          "".join(f" {y:>{CW-2}}  {sep}" for y in yrs) + \
          f" {'4yr Avg':>{CW-1}} {sep}"
    print(hdr); print(mid)

    for sig in SIGS:
        if sig == "OVERALL":
            print(mid)
        accs  = [r["stats"].get(sig,(0,0,float("nan")))[2] for r in results]
        valid = [a for a in accs if not math.isnan(a)]
        avg   = float(np.mean(valid)) if valid else float("nan")
        row   = f"{sep} {sig:<11} {sep}"
        for acc in accs:
            row += f" {fmt_pct(acc,CW-2)}  {sep}"
        row += f" {fmt_pct(avg,CW-1)} {sep}"
        print(row)

    print(mid)
    rtm_row = f"{sep} {'vs RTM':<11} {sep}"
    rtm_vals = []
    for r in results:
        ov_a = r["stats"]["OVERALL"][2]
        vs   = ov_a - RTM_BASELINE if not math.isnan(ov_a) else float("nan")
        rtm_vals.append(vs)
        rtm_row += f" {fmt_pp(vs,CW-2)}  {sep}"
    avg_rtm = float(np.mean([v for v in rtm_vals if not math.isnan(v)]))
    rtm_row += f" {fmt_pp(avg_rtm,CW-1)} {sep}"
    print(rtm_row)

    n_row = f"{sep} {'n eval':<11} {sep}"
    ns = [r["n_eval"] for r in results]
    for n in ns:
        n_row += f" {n:>{CW-2}}  {sep}"
    n_row += f" {sum(ns):>{CW-1}} {sep}"
    print(n_row); print(top)


def print_pitcher_comparison(orig: dict, v6: dict):
    SIGS = ["BUY_LOW","SLIGHT_BUY","SELL_HIGH","SLIGHT_SELL","OVERALL"]
    print(f"\n  {'Signal':<14} {'orig n':>7} {'orig acc':>9} {'v6 n':>7} {'v6 acc':>9} {'delta':>8}")
    print(f"  {'-' * 58}")
    for sig in SIGS:
        if sig == "OVERALL":
            print(f"  {'-' * 58}")
        o = orig["stats"].get(sig, (0,0,float("nan")))
        v = v6["stats"].get(sig,   (0,0,float("nan")))
        delta = v[2] - o[2] if not math.isnan(o[2]) and not math.isnan(v[2]) else float("nan")
        arrow = "" if math.isnan(delta) else (" <-- improved" if delta > 0.01 else
                                               (" <-- worse" if delta < -0.01 else ""))
        print(f"  {sig:<14} {o[0]:>7} {fmt_pct(o[2],8)} {v[0]:>7} {fmt_pct(v[2],8)} "
              f"{fmt_pp(delta,7) if not math.isnan(delta) else '   n/a':>9}{arrow}")
    # RTM
    orig_rtm = orig["stats"]["OVERALL"][2] - RTM_BASELINE
    v6_rtm   = v6["stats"]["OVERALL"][2]   - RTM_BASELINE
    print(f"  {'vs RTM':<14} {'':>7} {fmt_pp(orig_rtm,8)} {'':>7} {fmt_pp(v6_rtm,8)} "
          f"{fmt_pp(v6_rtm-orig_rtm,7):>9}")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    print("Multi-Year Within-Season Backtest v6")
    print("=" * 76)
    print("HITTER MODULE: v5 logic (OAA + tightened thresholds) — confirming stability")
    print("PITCHER MODULE: + 2 IP per-start minimum + volatility dampening")
    print("=" * 76)

    # ── v5 benchmarks ─────────────────────────────────────────────────────────
    V5_OVERALL = 0.861; V5_BL = 0.928; V5_SS = 0.841; V5_SH = 0.948; V5_RTM = 0.179
    ORIG_P_OVERALL = 0.824; ORIG_P_SH = 1.000; ORIG_P_BL = 0.833

    # ══════════════════════════════════════════════════════════════════════════
    print("\n" + "═"*76)
    print("SECTION 1: HITTER MULTI-YEAR BACKTEST  (2022–2025)")
    print("═"*76)

    career_stats = load_career_stats()
    patterns     = load_seasonal_patterns()
    career_babip = load_career_babip()
    oaa_adj      = load_oaa_adj()
    print(f"Career stats: {len(career_stats):,}  |  Seasonal: {len(patterns):,}  "
          f"|  BABIP: {len(career_babip):,}  |  OAA teams: {len(oaa_adj):,}")

    h_results = []
    for year in H_YEARS:
        print(f"\nRunning {year}...")
        opp_oaa = load_opponent_oaa_for_year(year, oaa_adj)
        r = run_year_h(year, career_stats, patterns, career_babip, opp_oaa)
        if r is None:
            print(f"  SKIPPED — missing cache files"); continue
        h_results.append(r)
        ov = r["stats"]["OVERALL"][2]
        bl = r["stats"]["BUY_LOW"][2]
        ss = r["stats"]["SLIGHT_SELL"][2]
        print(f"  {r['n_signals']} sig batters → {r['n_eval']} eval  "
              f"overall={ov:.1%}  BUY_LOW={bl:.1%}  SLIGHT_SELL={ss:.1%}")

    if not h_results:
        print("No hitter results."); return

    print(f"\n{'='*76}")
    print("HITTER ACCURACY TABLE  (v6 = v5: no hitter-side changes)")
    print(f"{'='*76}")
    print_hitter_table(h_results)

    h_ov_accs = [r["stats"]["OVERALL"][2] for r in h_results]
    h_bl_accs = [r["stats"]["BUY_LOW"][2] for r in h_results]
    h_ss_accs = [r["stats"]["SLIGHT_SELL"][2] for r in h_results]
    h_sh_accs = [r["stats"]["SELL_HIGH"][2] for r in h_results]
    h_ov  = float(np.nanmean(h_ov_accs))
    h_bl  = float(np.nanmean(h_bl_accs))
    h_ss  = float(np.nanmean(h_ss_accs))
    h_sh  = float(np.nanmean(h_sh_accs))
    h_rtm = h_ov - RTM_BASELINE

    # ══════════════════════════════════════════════════════════════════════════
    print(f"\n{'═'*76}")
    print("SECTION 2: PITCHER WITHIN-SEASON BACKTEST  (April 2024 → May-July 2024)")
    print("═"*76)

    print("\nRunning ORIGINAL pitcher backtest (no 2 IP filter, no volatility)...")
    orig_p = run_pitcher_backtest("orig", use_2ip=False, use_volatility=False)

    print("\nRunning v6 pitcher backtest (2 IP minimum + volatility dampening)...")
    v6_p   = run_pitcher_backtest("v6",   use_2ip=True,  use_volatility=True)

    if orig_p and v6_p:
        print(f"\n{'='*76}")
        print("PITCHER ACCURACY TABLE  (orig vs v6: 2 IP min + volatility)")
        print(f"{'='*76}")
        print_pitcher_comparison(orig_p, v6_p)

        print(f"\n  Orig: {orig_p['n_signal']} signal pitchers → {orig_p['n_eval']} eval")
        print(f"  v6:   {v6_p['n_signal']} signal pitchers → {v6_p['n_eval']} eval")
        if v6_p.get("n_excluded_starts"):
            print(f"  2 IP filter: {v6_p['n_excluded_starts']} starts excluded")
        if v6_p.get("n_vol_flagged"):
            print(f"  Volatility: {v6_p['n_vol_flagged']} pitchers flagged  |  "
                  f"{v6_p['n_vol_dampened']} buy signals dampened ×{VOL_DAMP}")

    # ══════════════════════════════════════════════════════════════════════════
    print(f"\n{'═'*76}")
    print("v5 vs v6 COMPARISON  (hitters: no change expected; pitchers: new improvements)")
    print("═"*76)

    p_ov_v6 = v6_p["stats"]["OVERALL"][2]  if v6_p  else float("nan")
    p_bl_v6 = v6_p["stats"]["BUY_LOW"][2]  if v6_p  else float("nan")
    p_sh_v6 = v6_p["stats"]["SELL_HIGH"][2] if v6_p else float("nan")
    p_ov_orig= orig_p["stats"]["OVERALL"][2] if orig_p else float("nan")
    p_sh_orig= orig_p["stats"]["SELL_HIGH"][2] if orig_p else float("nan")

    print(f"\n  {'Metric':<32} {'v5':>8} {'v6':>8} {'Delta':>8}")
    print(f"  {'-' * 60}")
    for label, v5_val, v6_val in [
        ("Hitter 4yr overall",       V5_OVERALL,  h_ov),
        ("Hitter BUY_LOW 4yr avg",   V5_BL,       h_bl),
        ("Hitter SLIGHT_SELL 4yr",   V5_SS,       h_ss),
        ("Hitter SELL_HIGH 4yr",     V5_SH,       h_sh),
        ("Hitter vs RTM 4yr",        V5_RTM,      h_rtm),
        ("Pitcher overall (2024)",   ORIG_P_OVERALL, p_ov_v6),
        ("Pitcher BUY_LOW (2024)",   ORIG_P_BL,   p_bl_v6),
        ("Pitcher SELL_HIGH (2024)", ORIG_P_SH,   p_sh_v6),
    ]:
        if math.isnan(v5_val) or math.isnan(v6_val):
            print(f"  {label:<32} {'n/a':>7}  {'n/a':>7}  {'n/a':>7}")
            continue
        delta = v6_val - v5_val
        arrow = " <-- improved" if delta > 0.005 else (" <-- worse" if delta < -0.005 else " (stable)")
        print(f"  {label:<32} {v5_val:>7.1%} {v6_val:>7.1%} {delta:>+7.1%}{arrow}")

    # ══════════════════════════════════════════════════════════════════════════
    print(f"\n{'═'*76}")
    print("KEY QUESTIONS")
    print("═"*76)

    print(f"\n  Q1: Does hitter 4yr avg hold at {V5_OVERALL:.1%}?")
    print(f"      v5={V5_OVERALL:.1%}  v6={h_ov:.1%}  delta={h_ov-V5_OVERALL:>+.1%}")
    ans = "YES — stable" if abs(h_ov - V5_OVERALL) < 0.003 else ("improved" if h_ov > V5_OVERALL else "declined")
    print(f"      Answer: {ans}")

    print(f"\n  Q2: Does SELL_HIGH hold above 94%?")
    print(f"      Hitter SELL_HIGH: {h_sh:.1%}  |  Pitcher SELL_HIGH: {p_sh_v6:.1%}")
    print(f"      Answer: {'YES' if h_sh >= 0.940 else 'NO'} hitters  |  "
          f"{'YES' if p_sh_v6 >= 0.940 else 'NO'} pitchers")

    print(f"\n  Q3: Does pitcher SELL_HIGH 100% record hold?")
    print(f"      orig={p_sh_orig:.1%}  v6={p_sh_v6:.1%}")
    print(f"      Answer: {'HOLDS' if p_sh_v6 >= 0.999 else f'CHANGED to {p_sh_v6:.1%}'}")

    print(f"\n  Q4: Does pitcher BUY_LOW improve with volatility dampening?")
    print(f"      orig BUY_LOW={p_ov_orig:.1%}  v6 BUY_LOW={p_bl_v6:.1%}")
    delta_bl = p_bl_v6 - ORIG_P_BL if not math.isnan(p_bl_v6) else float("nan")
    print(f"      delta={delta_bl:>+.1%}" if not math.isnan(delta_bl) else "      delta=n/a")
    print(f"      Answer: {'IMPROVED' if delta_bl > 0.01 else 'UNCHANGED/WORSE'}")

    print(f"\n  Q5: Is 2025 still the strongest hitter out-of-sample year?")
    yr_ov = [(r["year"], r["stats"]["OVERALL"][2]) for r in h_results]
    best_yr, best_acc = max(yr_ov, key=lambda x: x[1])
    for yr, acc in yr_ov:
        marker = " <-- best" if yr == best_yr else ""
        print(f"      {yr}: {acc:.1%}{marker}")

    # ══════════════════════════════════════════════════════════════════════════
    print(f"\n{'═'*76}")
    print("SUMMARY")
    print("═"*76)
    total_h_eval = sum(r["n_eval"] for r in h_results)
    print(f"  Hitter 4yr overall:     {h_ov:.1%}  (v5={V5_OVERALL:.1%}  Δ={h_ov-V5_OVERALL:>+.1%})")
    print(f"  Hitter BUY_LOW:         {h_bl:.1%}  (v5={V5_BL:.1%}  Δ={h_bl-V5_BL:>+.1%})")
    print(f"  Hitter SLIGHT_SELL:     {h_ss:.1%}  (v5={V5_SS:.1%}  Δ={h_ss-V5_SS:>+.1%})")
    print(f"  Hitter SELL_HIGH:       {h_sh:.1%}  (v5={V5_SH:.1%}  Δ={h_sh-V5_SH:>+.1%})")
    print(f"  Hitter vs RTM:          +{h_rtm:.1%}pp  ({total_h_eval} player-seasons)")
    print()
    if not math.isnan(p_ov_v6):
        p_eval = v6_p.get("n_eval",0)
        print(f"  Pitcher overall (v6):   {p_ov_v6:.1%}  (orig={p_ov_orig:.1%}  Δ={p_ov_v6-p_ov_orig:>+.1%})")
        print(f"  Pitcher SELL_HIGH (v6): {p_sh_v6:.1%}  (orig={p_sh_orig:.1%})")
        print(f"  Pitcher BUY_LOW (v6):   {p_bl_v6:.1%}  (orig={ORIG_P_BL:.1%}  Δ={p_bl_v6-ORIG_P_BL:>+.1%})")
        print(f"  Pitcher vs RTM (v6):    {p_ov_v6-RTM_BASELINE:>+.1%}pp  ({p_eval} pitchers)")

    h_verdict = "STABLE" if abs(h_ov-V5_OVERALL) < 0.003 else ("IMPROVED" if h_ov > V5_OVERALL else "REGRESSED")
    p_verdict = "IMPROVED" if not math.isnan(p_ov_v6) and p_ov_v6 > p_ov_orig else "STABLE/UNCHANGED"
    print(f"\n  Hitter verdict: {h_verdict}  |  Pitcher verdict: {p_verdict}")


if __name__ == "__main__":
    main()
