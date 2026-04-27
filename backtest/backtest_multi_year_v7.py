"""
Multi-Year Within-Season Backtest v7
=====================================
MEASUREMENT FRAMEWORK — READ BEFORE MODIFYING THRESHOLDS:

  This backtest uses April-only inputs (~100-150 PA) with a simplified formula:
    luck_score = xwoba_gap * 0.60 + babip_luck * 0.40

  Production score_luck.py uses full-season inputs and a 4-component formula
  with modifiers — scores regularly exceed ±0.150. Backtest scores peak at
  0.080-0.120. The two systems operate on DIFFERENT SCALES.

  Backtest thresholds (H_BT_*/P_BT_* from config.py) are calibrated to the
  backtest score distribution. Production thresholds (H_PROD_*/P_PROD_*) are
  calibrated to the production distribution. They are NOT interchangeable.

  USE THIS BACKTEST FOR:
    - Signal direction validation (do buy signals outperform?)
    - A vs B modifier comparisons (does adding K%/pull improve accuracy?)
  DO NOT USE FOR:
    - Quoting score numbers alongside production signals
    - Setting production thresholds

  Evaluates April-only signals (100-150 PA) against May-August outcomes.
  Training window: 2022-2024 (universal DH + deadened ball standardization).
  OOS validation: 2025.

  Canonical accuracy (305 player-seasons, A vs B vs C all identical):
    Overall:    84.4% train | 89.4% OOS
    Buy Low:    91.2% train | 96.9% OOS
    Sell High:  91.7% train | 100.0% OOS
    vs RTM:     +17.9pp

TWO MODULES:

  HITTER MODULE  — identical to v5/v6 (confirms 86.1% holds; no changes)

  PITCHER MODULE — v6 + FIP- override for stuff+ modifier:
    1. 2 IP per-start minimum (v6)
    2. Volatility dampening (v6)
    3. FIP- override for stuff+ proxy miscalibration
         elite_override: FIP- < 85 AND sp < 95
           → skip "poor stuff dampens buy" penalty
           → apply "elite dampens sell ×0.85" on sell signals
         poor_override: FIP- > 115 AND sp > 105
           → skip "elite stuff+buy ×1.15" bonus
           → apply "poor sell amplify ×1.15" on sell signals

v6 benchmarks:
  Hitter overall=86.1%  BUY_LOW=92.8%  SELL_HIGH=94.8%  vs RTM=+17.9pp
  Pitcher overall=85.7%  BUY_LOW=90.9%  SELL_HIGH=100.0%  vs RTM=+17.5pp
"""

import io
import json
import math
import os
import sys
import numpy as np
import pandas as pd
from pathlib import Path

BASE_DIR          = Path(os.path.dirname(os.path.abspath(__file__))).parent  # project root
sys.path.insert(0, str(BASE_DIR))

from config import (
    H_BT_BUY_LOW, H_BT_SLIGHT_BUY, H_BT_SELL_HIGH, H_BT_SLIGHT_SELL,
    P_BT_BUY_LOW, P_BT_SLIGHT_BUY, P_BT_SELL_HIGH, P_BT_SLIGHT_SELL,
)

# Import before stdout re-wrap to avoid double-buffer ownership conflict
from backtest_pitcher_within_season import compute_pitcher_stats as _pitcher_stats_orig

# Detach first so the old wrapper doesn't close the buffer when it's GC'd
if isinstance(sys.stdout, io.TextIOWrapper):
    _buf = sys.stdout.detach()
else:
    _buf = getattr(sys.stdout, "buffer", sys.stdout)
sys.stdout = io.TextIOWrapper(_buf, encoding="utf-8", errors="replace")
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
# Hitter backtest thresholds — imported from config.py (H_BT_* constants)
# Calibrated to backtest April-only score range. See config.py for rationale.

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

# ─── K%/Pull Rate modifier constants (Version B) ─────────────────────────────
HP_X_KP, HP_Y_KP    = 125.42, 198.27
PULL_ANGLE_KP        = 20.0
K_SPIKE_THRESH_KP    = 0.030
PULL_DROP_THRESH_KP  = 0.050
MIN_PA_CAREER_KP     = 30
NON_PA_EVENTS_KP     = {"truncated_pa"}
FAIR_BIP_EVENTS_KP   = {
    "single","double","triple","field_out","force_out",
    "grounded_into_double_play","double_play","fielders_choice",
    "fielders_choice_out","field_error","sac_fly","sac_fly_double_play","home_run",
}
LUCK_SCORES_PATH     = BASE_DIR / "luck_scores.csv"

# ─── Hard hit rate modifier constants (Version C) ────────────────────────────
# Hard hit rate computed from v4_april: launch_speed >= 95 mph on fair BIP.
# Career baseline = average HH% over CAREER_YEARS with >= MIN_PA_CAREER_KP PA.
# Flag: curr HH% < career - HH_DROP_THRESH_C.
HARD_HIT_SPEED_THRESH = 95.0   # mph — Statcast hard hit threshold
HH_DROP_THRESH_C      = 0.030  # 3pp drop below career → flag
FAIR_BIP_EVENTS_HH    = {      # only fair BIP count for HH%
    "single", "double", "triple", "field_out", "force_out",
    "grounded_into_double_play", "double_play", "fielders_choice",
    "fielders_choice_out", "field_error", "sac_fly", "sac_fly_double_play",
    "home_run",
}

# ─── Pitcher constants ────────────────────────────────────────────────────────
MIN_START_IP_P    = 2.0     # per-start floor for ERA/BABIP signal
MIN_APRIL_IP_P    = 15.0    # minimum total April IP (same as original)
MIN_OUTCOME_IP_P  = 30.0    # minimum May-July IP
ERA_FLAT_P        = 0.40    # minimum ERA change to count as outcome
FIP_CONST         = 3.10
LEAGUE_AVG_ERA    = 4.20
LEAGUE_AVG_BABIP_P= 0.300

# Pitcher backtest thresholds — imported from config.py (P_BT_* constants)
# ERA-FIP gap scale — not production luck score scale. See config.py.

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
    """Thresholds from config.py H_BT_* — calibrated to backtest score range."""
    if score >= H_BT_BUY_LOW:     return "BUY_LOW"
    if score >= H_BT_SLIGHT_BUY:  return "SLIGHT_BUY"
    if score <= H_BT_SELL_HIGH:   return "SELL_HIGH"
    if score <= H_BT_SLIGHT_SELL: return "SLIGHT_SELL"
    return "NEUTRAL"


def _kp_calc_pa(df: pd.DataFrame) -> pd.Series:
    pa_rows = df[df["events"].notna() & ~df["events"].isin(NON_PA_EVENTS_KP)]
    return pa_rows.groupby("batter").size()


def _kp_calc_k_rate(df: pd.DataFrame) -> pd.Series:
    pa_rows = df[df["events"].notna() & ~df["events"].isin(NON_PA_EVENTS_KP)]
    grouped = pa_rows.groupby("batter")
    ks = grouped["events"].apply(
        lambda s: s.isin({"strikeout", "strikeout_double_play"}).sum()
    )
    pa_count = grouped.size()
    return (ks / pa_count).where(pa_count > 0)


def _kp_calc_pull_rate(df: pd.DataFrame) -> pd.Series:
    required = {"stand", "hc_x", "hc_y"}
    if not required.issubset(df.columns):
        return pd.Series(dtype=float)
    fair_bip = df[
        df["events"].isin(FAIR_BIP_EVENTS_KP)
        & df["hc_x"].notna()
        & df["hc_y"].notna()
    ].copy()
    if fair_bip.empty:
        return pd.Series(dtype=float)
    angle = np.degrees(np.arctan2(
        fair_bip["hc_x"] - HP_X_KP,
        HP_Y_KP - fair_bip["hc_y"],
    ))
    fair_bip["pulled"] = (
        ((fair_bip["stand"] == "R") & (angle < -PULL_ANGLE_KP))
        | ((fair_bip["stand"] == "L") & (angle > PULL_ANGLE_KP))
    )
    grouped    = fair_bip.groupby("batter")
    pull_count = grouped["pulled"].sum()
    total      = grouped["pulled"].count()
    return (pull_count / total).where(total > 0)


def _hh_calc_rate(df: pd.DataFrame) -> pd.Series:
    """Hard hit rate per batter: BIP with launch_speed >= 95 / total fair BIP."""
    fair = df[
        df["events"].isin(FAIR_BIP_EVENTS_HH)
        & df["launch_speed"].notna()
    ].copy()
    if fair.empty:
        return pd.Series(dtype=float)
    fair["hard_hit"] = fair["launch_speed"] >= HARD_HIT_SPEED_THRESH
    grouped = fair.groupby("batter")
    return grouped["hard_hit"].sum() / grouped["hard_hit"].count()


def _hh_build_career(year: int, aprils: dict) -> dict:
    """Career HH% from all years < current year with >= MIN_PA_CAREER_KP PA."""
    accum = {}
    pa_fn = _kp_calc_pa
    for yr, df in aprils.items():
        if yr >= year:
            continue
        pa_s = pa_fn(df)
        hh_s = _hh_calc_rate(df)
        hh_d = {int(k): float(v) for k, v in hh_s.dropna().items()}
        for bid_raw in pa_s.index:
            bid = int(bid_raw)
            if pa_s.get(bid_raw, 0) < MIN_PA_CAREER_KP:
                continue
            if bid in hh_d:
                accum.setdefault(bid, []).append(hh_d[bid])
    return {bid: sum(v) / len(v) for bid, v in accum.items()}


def _apply_additive_modifiers(
    records: list[dict],
    k_pen: float,
    pull_pen: float,
    hh_pen: float,
    max_cap: float = 0.040,
) -> dict:
    """
    Apply additive penalties to per-player luck_score_a (buy signals only).
    Each flag independently subtracts its penalty; total capped at max_cap.
    Returns {signal: (n, correct, acc)} plus "OVERALL".
    """
    by_sig: dict[str, list[int]] = {}
    for rec in records:
        if rec["outcome"] == "FLAT":
            continue
        score_a = rec["luck_score_a"]
        if score_a > 0:
            total_pen = (
                (k_pen    if rec["k_flag"]    else 0.0)
                + (pull_pen if rec["pull_flag"] else 0.0)
                + (hh_pen  if rec["hh_flag"]   else 0.0)
            )
            total_pen = min(total_pen, max_cap)
            new_score = score_a - total_pen
        else:
            new_score = score_a
        new_sig = classify_h(new_score)
        if new_sig not in SIGNAL_MAP_H:
            continue
        correct = int(SIGNAL_MAP_H[new_sig] == rec["outcome"])
        entry = by_sig.setdefault(new_sig, [0, 0])
        entry[0] += 1
        entry[1] += correct
    n_tot = c_tot = 0
    result: dict = {}
    for sig, (n, c) in by_sig.items():
        n_tot += n; c_tot += c
        result[sig] = (n, c, c / n if n > 0 else float("nan"))
    result["OVERALL"] = (n_tot, c_tot, c_tot / n_tot if n_tot > 0 else float("nan"))
    return result


def _kp_build_career(year: int, aprils: dict) -> tuple[dict, dict]:
    """Career K% and pull rate from all years < current year with >= MIN_PA_CAREER_KP PA."""
    k_accum    = {}
    pull_accum = {}
    for yr, df in aprils.items():
        if yr >= year:
            continue
        pa_s    = _kp_calc_pa(df)
        k_s     = _kp_calc_k_rate(df)
        pull_s  = _kp_calc_pull_rate(df)
        k_d     = {int(k): float(v) for k, v in k_s.dropna().items()}
        pull_d  = {int(k): float(v) for k, v in pull_s.dropna().items()}
        for bid_raw in pa_s.index:
            bid = int(bid_raw)
            if pa_s.get(bid_raw, 0) < MIN_PA_CAREER_KP:
                continue
            if bid in k_d:
                k_accum.setdefault(bid, []).append(k_d[bid])
            if bid in pull_d:
                pull_accum.setdefault(bid, []).append(pull_d[bid])
    career_k    = {bid: sum(v) / len(v) for bid, v in k_accum.items()}
    career_pull = {bid: sum(v) / len(v) for bid, v in pull_accum.items()}
    return career_k, career_pull


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

def run_year_h(year, career_stats, patterns, career_babip, opp_oaa, aprils_by_year=None) -> dict | None:
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

    # ── Save baseline score before any modifiers (for sensitivity analysis) ───
    signals["luck_score_a"] = signals["luck_score"].copy()

    # ── Version B: K%/pull rate modifier (after all other modifiers) ──────────
    signals["luck_score_b"] = signals["luck_score"].copy()
    signals["_k_flag"]      = False
    signals["_pull_flag"]   = False
    n_kp_both = n_kp_k = n_kp_pull = 0
    if aprils_by_year is not None:
        career_k_kp, career_pull_kp = _kp_build_career(year, aprils_by_year)
        curr_k_d    = {int(k): float(v) for k, v in _kp_calc_k_rate(april).dropna().items()}
        curr_pull_d = {int(k): float(v) for k, v in _kp_calc_pull_rate(april).dropna().items()}

        def _get_k_flag(bid):
            bid = int(bid)
            ck = career_k_kp.get(bid)
            ck_curr = curr_k_d.get(bid)
            if ck is None or ck_curr is None:
                return False
            return ck_curr - ck > K_SPIKE_THRESH_KP

        def _get_pull_flag(bid):
            bid = int(bid)
            cp = career_pull_kp.get(bid)
            cp_curr = curr_pull_d.get(bid)
            if cp is None or cp_curr is None:
                return False
            return cp_curr - cp < -PULL_DROP_THRESH_KP

        buy_mask_b  = signals["luck_score_b"] > 0
        k_flags     = signals["batter"].apply(_get_k_flag)
        pull_flags  = signals["batter"].apply(_get_pull_flag)

        signals["_k_flag"]    = k_flags
        signals["_pull_flag"] = pull_flags

        kp_both   = buy_mask_b & k_flags & pull_flags
        kp_k_only = buy_mask_b & k_flags & ~pull_flags
        kp_p_only = buy_mask_b & ~k_flags & pull_flags

        signals.loc[kp_both,   "luck_score_b"] = (signals.loc[kp_both,   "luck_score_b"] * 0.90).round(4)
        signals.loc[kp_k_only, "luck_score_b"] = (signals.loc[kp_k_only, "luck_score_b"] * 0.95).round(4)
        signals.loc[kp_p_only, "luck_score_b"] = (signals.loc[kp_p_only, "luck_score_b"] * 0.95).round(4)

        n_kp_both  = int(kp_both.sum())
        n_kp_k     = int(kp_k_only.sum())
        n_kp_pull  = int(kp_p_only.sum())

    signals["signal_b"] = signals["luck_score_b"].apply(classify_h)

    # ── Version C: K%/pull + hard hit rate delta ──────────────────────────────
    signals["luck_score_c"] = signals["luck_score_b"].copy()
    signals["_hh_flag"]     = False
    n_hh_c = 0
    if aprils_by_year is not None:
        career_hh_c = _hh_build_career(year, aprils_by_year)
        curr_hh_d   = {int(k): float(v) for k, v in _hh_calc_rate(april).dropna().items()}
        buy_mask_c  = signals["luck_score_c"] > 0
        for idx, row in signals[buy_mask_c].iterrows():
            bid = int(row["batter"])
            career_hh_val = career_hh_c.get(bid)
            curr_hh_val   = curr_hh_d.get(bid)
            if career_hh_val is not None and curr_hh_val is not None:
                if curr_hh_val - career_hh_val < -HH_DROP_THRESH_C:
                    signals.at[idx, "luck_score_c"] = round(signals.at[idx, "luck_score_c"] * 0.95, 4)
                    signals.at[idx, "_hh_flag"]     = True
                    n_hh_c += 1
    signals["signal_c"] = signals["luck_score_c"].apply(classify_h)

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

    eval_df_b = merged[merged["signal_b"].isin(SIGNAL_MAP_H) & (merged["outcome"] != "FLAT")].copy()
    eval_df_b["correct"] = eval_df_b.apply(lambda r: r["outcome"] == SIGNAL_MAP_H[r["signal_b"]], axis=1)
    stats_b = bucket_stats_h(eval_df_b)

    eval_df_c = merged[merged["signal_c"].isin(SIGNAL_MAP_H) & (merged["outcome"] != "FLAT")].copy()
    eval_df_c["correct"] = eval_df_c.apply(lambda r: r["outcome"] == SIGNAL_MAP_H[r["signal_c"]], axis=1)
    stats_c = bucket_stats_h(eval_df_c)

    gradient = {
        sig: merged[merged["signal"] == sig]["woba_change"].mean()
        if (merged["signal"] == sig).sum() >= 3 else float("nan")
        for sig in ["BUY_LOW","SLIGHT_BUY","NEUTRAL","SLIGHT_SELL","SELL_HIGH"]
    }

    # ── Per-player records for sensitivity sweep / Version D ─────────────────
    player_recs = []
    for _, row in merged.iterrows():
        sig_a = classify_h(float(row["luck_score_a"]))
        sig_c = str(row.get("signal_c", sig_a))
        player_recs.append({
            "year":         year,
            "batter":       int(row["batter"]),
            "luck_score_a": float(row["luck_score_a"]),
            "signal_a":     sig_a,
            "signal_c":     sig_c,
            "k_flag":       bool(row.get("_k_flag",    False)),
            "pull_flag":    bool(row.get("_pull_flag", False)),
            "hh_flag":      bool(row.get("_hh_flag",   False)),
            "outcome":      str(row["outcome"]),
        })

    return {
        "year":        year,
        "stats":       stats,
        "stats_b":     stats_b,
        "stats_c":     stats_c,
        "stats_d":     {},
        "gradient":    gradient,
        "sig_counts":  sig_counts,
        "n_signals":   len(signals),
        "n_eval":      stats["OVERALL"][0],
        "n_flat":      int((merged["outcome"] == "FLAT").sum()),
        "l3_both":     l3_both,
        "l3_one":      l3_one,
        "n_career":    n_career,
        "n_fallback":  n_fallback,
        "n_oaa_top":   n_oaa_top,
        "n_oaa_bot":   n_oaa_bot,
        "n_kp_both":   n_kp_both,
        "n_kp_k":      n_kp_k,
        "n_kp_pull":   n_kp_pull,
        "n_hh_c":      n_hh_c,
        "n_d_changes": 0,
        "player_recs": player_recs,
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
    """Thresholds from config.py P_BT_* — ERA-FIP gap scale."""
    if gap >= P_BT_BUY_LOW:     return "BUY_LOW"
    if gap >= P_BT_SLIGHT_BUY:  return "SLIGHT_BUY"
    if gap <= P_BT_SELL_HIGH:   return "SELL_HIGH"
    if gap <= P_BT_SLIGHT_SELL: return "SLIGHT_SELL"
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


def run_pitcher_backtest(label: str, use_2ip: bool, use_volatility: bool,
                         use_fip_override: bool = False) -> dict:
    """
    Single pitcher backtest run.  label distinguishes versions in output.
    use_2ip:          apply 2 IP per-start minimum to ERA/BABIP/FIP computation.
    use_volatility:   apply ×0.90 dampening to buy signals for flagged pitchers.
    use_fip_override: apply FIP- override to stuff+ modifier (v7 addition).
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

    # FIP- for override (park-adjusted; league avg from pitchers with ≥15 IP)
    if use_fip_override and "fip" in sig.columns:
        qualified = sig[sig["ip"] >= 15]["fip"].dropna()
        lg_fip = qualified.mean() if len(qualified) > 0 else sig["fip"].dropna().mean()
        sig["fip_minus"] = (sig["fip"] / lg_fip * (1.0 / sig["park_factor"]) * 100).where(
            sig["fip"].notna(), other=float("nan")
        )
    else:
        sig["fip_minus"] = float("nan")

    def _apply_stuff(row):
        score = row["luck_score_raw"]
        sp    = row["stuff_plus"]
        if pd.isna(sp):
            return score
        fip_m = row["fip_minus"]
        fip_m_ok = not (isinstance(fip_m, float) and math.isnan(fip_m))
        is_elite_ovr = use_fip_override and fip_m_ok and fip_m < 85  and sp < 95
        is_poor_ovr  = use_fip_override and fip_m_ok and fip_m > 115 and sp > 105
        if is_elite_ovr:
            if score < 0: return round(score * 0.85, 3)   # dampen sell
            return score                                    # skip poor-stuff buy penalty
        if is_poor_ovr:
            if score > 0: return score                     # skip elite buy bonus
            return round(score * 1.15, 3)                  # amplify sell
        # Normal stuff+ tiers
        if sp >= 115 and score > 0: return round(score * 1.15, 3)
        if sp < 90   and score < 0: return round(score * 1.15, 3)
        if sp >= 115 and score < 0: return round(score * 0.85, 3)
        if sp < 90   and score > 0: return round(score * 0.85, 3)
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


def print_hitter_abc_comparison(results: list, train_years: list, oos_year: int):
    """Print Version A vs B vs C accuracy comparison with train/OOS split."""
    SIGS = ["BUY_LOW","SLIGHT_BUY","SELL_HIGH","SLIGHT_SELL","OVERALL"]

    train = [r for r in results if r["year"] in train_years]
    oos   = [r for r in results if r["year"] == oos_year]

    def pooled(rlist, key, sig):
        n_tot = c_tot = 0
        for r in rlist:
            s = r[key].get(sig, (0, 0, float("nan")))
            n_tot += s[0]; c_tot += s[1]
        return (n_tot, c_tot, c_tot / n_tot if n_tot > 0 else float("nan"))

    hdr = (f"\n  {'Signal':<12} {'Tr-A':>7} {'Tr-B':>7} {'Tr-C':>7} {'ΔBC':>7}"
           f"   {'OOS-A':>7} {'OOS-B':>7} {'OOS-C':>7} {'ΔBC':>7}")
    sep = "  " + "-" * 78
    print(hdr); print(sep)

    for sig in SIGS:
        if sig == "OVERALL":
            print(sep)
        ta = pooled(train, "stats",   sig)
        tb = pooled(train, "stats_b", sig)
        tc = pooled(train, "stats_c", sig)
        oa = pooled(oos,   "stats",   sig)
        ob = pooled(oos,   "stats_b", sig)
        oc = pooled(oos,   "stats_c", sig)

        def _d(a, b): return f"{(b-a)*100:>+5.1f}pp" if not (math.isnan(a) or math.isnan(b)) else "   n/a"

        print(f"  {sig:<12} {fmt_pct(ta[2],6)} {fmt_pct(tb[2],6)} {fmt_pct(tc[2],6)} {_d(tb[2],tc[2])}"
              f"   {fmt_pct(oa[2],6)} {fmt_pct(ob[2],6)} {fmt_pct(oc[2],6)} {_d(ob[2],oc[2])}")

    # n counts
    print(sep)
    def nn(rlist, key): return sum(r[key]["OVERALL"][0] for r in rlist)
    print(f"  {'n eval':<12} {nn(train,'stats'):>6}  {nn(train,'stats_b'):>6}  {nn(train,'stats_c'):>6}"
          f"         {nn(oos,'stats'):>6}  {nn(oos,'stats_b'):>6}  {nn(oos,'stats_c'):>6}")

    # Modifier activity
    print(f"\n  Modifier activity (buy signals dampened):")
    print(f"  {'Year':<6} {'KP-Both':>8} {'KP-K':>7} {'KP-Pull':>8} {'HH-C':>7}")
    for r in results:
        has_career = r["year"] > min(train_years + [oos_year])
        note = "" if has_career else "  (no prior years — skipped)"
        print(f"  {r['year']:<6} {r['n_kp_both']:>8} {r['n_kp_k']:>7} {r['n_kp_pull']:>8} "
              f"{r['n_hh_c']:>7}{note}")


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


def _print_sensitivity_sweep(all_recs: list[dict], train_years: list[int]) -> dict[str, float]:
    """
    Sweep each flag type independently from -0.002 to -0.020 in steps of -0.002.
    Print accuracy table per flag. Return calibrated penalty values that maximize
    training accuracy for each flag.
    """
    train_recs = [r for r in all_recs if r["year"] in train_years]
    base_stats = _apply_additive_modifiers(train_recs, 0.0, 0.0, 0.0)
    base_acc   = base_stats["OVERALL"][2]
    base_n     = base_stats["OVERALL"][0]
    print(f"\n  Baseline (Version A, no modifiers): {base_acc:.1%}  (train n={base_n})")

    best_vals: dict[str, float] = {}
    FLAG_LABELS = [
        ("k_flag",    "K-rate spike"),
        ("pull_flag", "Pull-rate drop"),
        ("hh_flag",   "Hard-hit drop"),
    ]

    for flag_name, label in FLAG_LABELS:
        print(f"\n  Flag: {label} ({flag_name})")
        print(f"  {'Penalty':>9} {'n_eval':>7} {'Accuracy':>9} {'vs_base':>8} {'Changes':>8}")
        print(f"  " + "-" * 52)

        best_pen  = 0.0
        best_acc  = base_acc
        STEPS = [round(i * 0.002, 4) for i in range(1, 11)]

        for penalty in STEPS:
            k_pen    = penalty if flag_name == "k_flag"    else 0.0
            pull_pen = penalty if flag_name == "pull_flag" else 0.0
            hh_pen   = penalty if flag_name == "hh_flag"   else 0.0

            stats = _apply_additive_modifiers(train_recs, k_pen, pull_pen, hh_pen)
            acc   = stats["OVERALL"][2]
            n_ev  = stats["OVERALL"][0]

            # Verdict changes vs Version A (same player, different signal)
            changes = 0
            for rec in train_recs:
                if rec["outcome"] == "FLAT":
                    continue
                score_a = rec["luck_score_a"]
                if score_a > 0 and rec[flag_name]:
                    new_sig = classify_h(score_a - min(penalty, 0.040))
                    if new_sig != rec["signal_a"]:
                        changes += 1

            delta  = acc - base_acc
            marker = " *BEST" if acc > best_acc else ""
            print(f"  {penalty:>+9.4f} {n_ev:>7} {acc:>9.1%} {delta:>+8.1%} {changes:>8}{marker}")

            if acc > best_acc:
                best_acc = acc
                best_pen = penalty

        if best_pen == 0.0:
            best_pen = 0.008
            print(f"\n  No improvement — using conservative default: {best_pen}")
        else:
            print(f"\n  Best for {label}: penalty={best_pen}  acc={best_acc:.1%}")

        best_vals[flag_name] = best_pen

    return best_vals


def _print_abcd_comparison(results: list, train_years: list, oos_year: int):
    """Print Version A / B / C / D accuracy comparison with train/OOS split."""
    SIGS = ["BUY_LOW", "SLIGHT_BUY", "SELL_HIGH", "SLIGHT_SELL", "OVERALL"]

    train = [r for r in results if r["year"] in train_years]
    oos   = [r for r in results if r["year"] == oos_year]

    def pooled(rlist, key, sig):
        n_tot = c_tot = 0
        for r in rlist:
            s = r.get(key, {}).get(sig, (0, 0, float("nan")))
            n_tot += s[0]; c_tot += s[1]
        return (n_tot, c_tot, c_tot / n_tot if n_tot > 0 else float("nan"))

    def _d(a, b):
        return f"{(b - a) * 100:>+5.1f}pp" if not (math.isnan(a) or math.isnan(b)) else "   n/a"

    hdr = (f"\n  {'Signal':<12} {'Tr-A':>7} {'Tr-B':>7} {'Tr-C':>7} {'Tr-D':>7} {'ΔCD':>7}"
           f"   {'OOS-A':>7} {'OOS-B':>7} {'OOS-C':>7} {'OOS-D':>7} {'ΔCD':>7}")
    sep = "  " + "-" * 90
    print(hdr); print(sep)

    for sig in SIGS:
        if sig == "OVERALL":
            print(sep)
        ta = pooled(train, "stats",   sig)
        tb = pooled(train, "stats_b", sig)
        tc = pooled(train, "stats_c", sig)
        td = pooled(train, "stats_d", sig)
        oa = pooled(oos,   "stats",   sig)
        ob = pooled(oos,   "stats_b", sig)
        oc = pooled(oos,   "stats_c", sig)
        od = pooled(oos,   "stats_d", sig)
        print(
            f"  {sig:<12} {fmt_pct(ta[2],6)} {fmt_pct(tb[2],6)} {fmt_pct(tc[2],6)} "
            f"{fmt_pct(td[2],6)} {_d(tc[2], td[2])}"
            f"   {fmt_pct(oa[2],6)} {fmt_pct(ob[2],6)} {fmt_pct(oc[2],6)} "
            f"{fmt_pct(od[2],6)} {_d(oc[2], od[2])}"
        )

    print(sep)
    def nn(rlist, key): return sum(r.get(key, {}).get("OVERALL", (0,))[0] for r in rlist)
    print(
        f"  {'n eval':<12} {nn(train,'stats'):>6}  {nn(train,'stats_b'):>6}  "
        f"{nn(train,'stats_c'):>6}  {nn(train,'stats_d'):>6}"
        f"          {nn(oos,'stats'):>6}  {nn(oos,'stats_b'):>6}  "
        f"{nn(oos,'stats_c'):>6}  {nn(oos,'stats_d'):>6}"
    )

    # Verdict changes C → D per year
    print(f"\n  Verdict changes (C → D) per year:")
    for r in results:
        tag = "(OOS)" if r["year"] == oos_year else "(train)"
        print(f"  {r['year']} {tag}: {r.get('n_d_changes', 0)} verdict changes")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    print("Multi-Year Within-Season Backtest — Calibrated Backtest Thresholds")
    print("=" * 76)
    print("HITTER thresholds: Buy Low >=0.040 | Slight Buy >=0.020 (backtest scale)")
    print("  NOTE: Production uses >0.150/>0.100 but those are calibrated to the full")
    print("  scoring pipeline range. Backtest thresholds select equivalent confidence")
    print("  tiers from the April-only simplified formula.")
    print("PITCHER MODULE: v6 + FIP- override for stuff+ miscalibration (ERA-FIP scale)")
    print("=" * 76)

    # ── pitcher benchmarks (v6 only — hitter benchmarks retired with old thresholds) ──
    V6_P_OVERALL = 0.857; V6_P_SH = 1.000; V6_P_BL = 0.909; V6_P_RTM = 0.175

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

    print("\nPre-loading April CSVs for K%/pull rate career baselines...")
    aprils_by_year = {}
    for yr in H_YEARS:
        p = CACHE_DIR / f"v4_april_{yr}.csv"
        if p.exists():
            aprils_by_year[yr] = pd.read_csv(p)
            print(f"  Loaded v4_april_{yr}.csv  ({len(aprils_by_year[yr]):,} rows)")
        else:
            print(f"  WARNING: v4_april_{yr}.csv not found")

    h_results = []
    for year in H_YEARS:
        print(f"\nRunning {year}...")
        opp_oaa = load_opponent_oaa_for_year(year, oaa_adj)
        r = run_year_h(year, career_stats, patterns, career_babip, opp_oaa, aprils_by_year)
        if r is None:
            print(f"  SKIPPED — missing cache files"); continue
        h_results.append(r)
        ov   = r["stats"]["OVERALL"][2]
        ov_b = r["stats_b"]["OVERALL"][2]
        bl   = r["stats"]["BUY_LOW"][2]
        ss   = r["stats"]["SLIGHT_SELL"][2]
        nb, nk, np_ = r["n_kp_both"], r["n_kp_k"], r["n_kp_pull"]
        print(f"  {r['n_signals']} sig batters → {r['n_eval']} eval  "
              f"overall A={ov:.1%} B={ov_b:.1%}  BUY_LOW={bl:.1%}  SLIGHT_SELL={ss:.1%}")
        if nb + nk + np_ > 0:
            print(f"  K%/pull: {nb} both×0.90 | {nk} K-only×0.95 | {np_} pull-only×0.95")

    if not h_results:
        print("No hitter results."); return

    print(f"\n{'='*76}")
    print("HITTER ACCURACY TABLE  (Version A — baseline)")
    print(f"{'='*76}")
    print_hitter_table(h_results)

    TRAIN_YEARS = [2022, 2023, 2024]
    OOS_YEAR    = 2025

    print(f"\n{'='*80}")
    print("HITTER ACCURACY TABLE  (Versions A / B / C)")
    print(f"{'='*80}")
    print(f"  Version A = baseline (v7 logic unchanged)")
    print(f"  Version B = + K%/pull modifier (×0.90 both flags, ×0.95 one flag, buy only)")
    print(f"  Version C = + K%/pull + hard hit rate delta (×0.95 if curr < career - 3pp, buy only)")
    print(f"  Train = {TRAIN_YEARS}  |  OOS = {OOS_YEAR}")
    print_hitter_abc_comparison(h_results, TRAIN_YEARS, OOS_YEAR)

    # ── VERSION D: Additive modifier sensitivity sweep & comparison ───────────
    all_recs = []
    for r in h_results:
        all_recs.extend(r.get("player_recs", []))

    if all_recs:
        print(f"\n{'='*80}")
        print("SENSITIVITY SWEEP — Additive modifier calibration  (training years only)")
        print(f"{'='*80}")
        print(f"  Sweep each flag independently -0.002 to -0.020 in -0.002 steps.")
        print(f"  Goal: find penalty that maximizes training accuracy per flag.")
        best_penalties = _print_sensitivity_sweep(all_recs, TRAIN_YEARS)

        k_pen    = best_penalties.get("k_flag",    0.008)
        pull_pen = best_penalties.get("pull_flag", 0.008)
        hh_pen   = best_penalties.get("hh_flag",   0.008)
        print(f"\n  Calibrated penalties: k_flag={k_pen:.4f}  pull_flag={pull_pen:.4f}"
              f"  hh_flag={hh_pen:.4f}  cap=0.040")

        # Compute Version D stats per year and verdict changes C → D
        for r in h_results:
            recs_yr = [rec for rec in all_recs if rec["year"] == r["year"]]
            r["stats_d"] = _apply_additive_modifiers(recs_yr, k_pen, pull_pen, hh_pen)
            changes = 0
            for rec in recs_yr:
                if rec["outcome"] == "FLAT":
                    continue
                score_a = rec["luck_score_a"]
                if score_a > 0:
                    total_pen = (
                        (k_pen    if rec["k_flag"]    else 0.0)
                        + (pull_pen if rec["pull_flag"] else 0.0)
                        + (hh_pen  if rec["hh_flag"]   else 0.0)
                    )
                    total_pen = min(total_pen, 0.040)
                    new_sig_d = classify_h(score_a - total_pen)
                else:
                    new_sig_d = classify_h(score_a)
                if new_sig_d != rec["signal_c"]:
                    changes += 1
            r["n_d_changes"] = changes

        print(f"\n{'='*90}")
        print("HITTER ACCURACY TABLE  (Versions A / B / C / D)")
        print(f"{'='*90}")
        print(f"  Version A = baseline")
        print(f"  Version B = K%/pull multiplicative (×0.90 both, ×0.95 one)")
        print(f"  Version C = B + hard hit rate delta (×0.95 if curr < career - 3pp)")
        print(f"  Version D = all flags additive (calibrated penalties, cap -0.040)")
        print(f"  Train = {TRAIN_YEARS}  |  OOS = {OOS_YEAR}")
        _print_abcd_comparison(h_results, TRAIN_YEARS, OOS_YEAR)

        # Train/OOS split for D
        def _pool_d(rlist):
            n_t = c_t = 0
            for r in rlist:
                s = r.get("stats_d", {}).get("OVERALL", (0, 0, float("nan")))
                n_t += s[0]; c_t += s[1]
            return c_t / n_t if n_t > 0 else float("nan")

        train_d = _pool_d([r for r in h_results if r["year"] in TRAIN_YEARS])
        oos_d   = _pool_d([r for r in h_results if r["year"] == OOS_YEAR])
        print(f"\n  Version D split summary:")
        print(f"  Train 2022-2024:  D={train_d:.1%}")
        print(f"  OOS 2025:         D={oos_d:.1%}")

        oos_guard_d = "PASS" if oos_d >= 0.870 else f"FAIL ({oos_d:.1%} < 87.0%)"
        print(f"  OOS guard (>=87.0%): {oos_guard_d}")

        total_d_changes = sum(r.get("n_d_changes", 0) for r in h_results)
        print(f"\n  ADOPTION DECISION:")
        print(f"  Total verdict changes C -> D across all years: {total_d_changes}")
        if total_d_changes == 0:
            print(f"  VERDICT-NEUTRAL — additive penalties are too small to cross tier gaps.")
            print(f"  Recommendation: DO NOT adopt additive architecture.")
            print(f"  Root cause: same as B/C — 0.002-0.020 range cannot cross the 0.040 tier gap.")
        else:
            train_a_acc = sum(r["stats"]["OVERALL"][1] for r in h_results if r["year"] in TRAIN_YEARS)
            train_a_n   = sum(r["stats"]["OVERALL"][0] for r in h_results if r["year"] in TRAIN_YEARS)
            train_a_pct = train_a_acc / train_a_n if train_a_n > 0 else float("nan")
            if train_d >= train_a_pct - 0.005 and total_d_changes > 0:
                print(f"  ADOPT — additive is equal or better accuracy with real verdict changes.")
            else:
                print(f"  DO NOT ADOPT — additive either hurts accuracy or produces no changes.")

    h_ov_accs   = [r["stats"]["OVERALL"][2]   for r in h_results]
    h_ov_b_accs = [r["stats_b"]["OVERALL"][2] for r in h_results]
    h_bl_accs   = [r["stats"]["BUY_LOW"][2]   for r in h_results]
    h_ss_accs   = [r["stats"]["SLIGHT_SELL"][2] for r in h_results]
    h_sh_accs   = [r["stats"]["SELL_HIGH"][2]  for r in h_results]
    h_ov   = float(np.nanmean(h_ov_accs))
    h_ov_b = float(np.nanmean(h_ov_b_accs))
    h_bl   = float(np.nanmean(h_bl_accs))
    h_ss   = float(np.nanmean(h_ss_accs))
    h_sh   = float(np.nanmean(h_sh_accs))
    h_rtm  = h_ov - RTM_BASELINE

    # ── Train vs OOS split ────────────────────────────────────────────────────
    train_rs = [r for r in h_results if r["year"] in TRAIN_YEARS]
    oos_rs   = [r for r in h_results if r["year"] == OOS_YEAR]

    def _pool(rlist, key):
        n_t = c_t = 0
        for r in rlist:
            s = r[key]["OVERALL"]
            n_t += s[0]; c_t += s[1]
        return c_t / n_t if n_t > 0 else float("nan")

    train_a = _pool(train_rs, "stats")
    train_b = _pool(train_rs, "stats_b")
    oos_a   = _pool(oos_rs,   "stats")
    oos_b   = _pool(oos_rs,   "stats_b")

    print(f"\n  Split summary (production thresholds):")
    print(f"  Train 2022-2024:  A={train_a:.1%}  B={train_b:.1%}  Δ={train_b-train_a:>+.1%}")
    print(f"  OOS 2025:         A={oos_a:.1%}   B={oos_b:.1%}   Δ={oos_b-oos_a:>+.1%}")

    oos_guard = "PASS ✓" if oos_b >= 0.870 else f"FAIL ✗ ({oos_b:.1%} < 87.0%)"
    print(f"\n  OOS guard rail (≥87.0%): {oos_guard}")

    # ── 2026 signal check: which current hitters are flagged? ────────────────
    print(f"\n{'='*76}")
    print("CURRENT 2026 SIGNALS — flagged hitters (k_flag or pull_flag)")
    print(f"{'='*76}")
    if LUCK_SCORES_PATH.exists():
        ls = pd.read_csv(LUCK_SCORES_PATH)
        if "k_flag" in ls.columns and "pull_flag" in ls.columns:
            flagged = ls[(ls["k_flag"] == True) | (ls["pull_flag"] == True)].copy()
            flagged = flagged[flagged["verdict"].isin(
                ["Buy low", "Slight buy", "Neutral", "Slight sell", "Sell high"]
            )]
            buy_flagged  = flagged[flagged["verdict"].isin(["Buy low", "Slight buy"])]
            other_flagged = flagged[~flagged["verdict"].isin(["Buy low", "Slight buy"])]
            print(f"\n  Total flagged hitters: {len(flagged)}"
                  f"  (buy-signal flagged: {len(buy_flagged)}, other: {len(other_flagged)})")
            print(f"\n  Buy-signal hitters with K%/pull flags (modifier is ACTIVE on these):")
            print(f"  {'Name':<22} {'Verdict':<12} {'K flag':>7} {'Pull flag':>10} "
                  f"{'K delta':>8} {'Pull delta':>10} {'luck_score':>11}")
            print("  " + "-" * 82)
            name_col = "name" if "name" in ls.columns else ls.columns[0]
            for _, row in buy_flagged.iterrows():
                kd  = f"{row['k_pct_delta']*100:>+.1f}pp"    if pd.notna(row.get("k_pct_delta"))   else "   n/a"
                pd_ = f"{row['pull_pct_delta']*100:>+.1f}pp"  if pd.notna(row.get("pull_pct_delta")) else "   n/a"
                print(f"  {str(row.get(name_col,'')):<22} {str(row.get('verdict','')):<12} "
                      f"{'YES' if row['k_flag'] else 'no':>7} {'YES' if row['pull_flag'] else 'no':>10} "
                      f"{kd:>8} {pd_:>10} {row.get('luck_score', float('nan')):>11.4f}")
            if buy_flagged.empty:
                print("  None — no buy-signal hitters currently flagged")
            if not other_flagged.empty:
                print(f"\n  Other verdicts with flags (modifier NOT applied — sell-side only):")
                for _, row in other_flagged.head(10).iterrows():
                    kd  = f"{row['k_pct_delta']*100:>+.1f}pp" if pd.notna(row.get("k_pct_delta")) else "n/a"
                    print(f"  {str(row.get(name_col,'')):<22} {str(row.get('verdict','')):<12} "
                          f"k_flag={row['k_flag']}  pull_flag={row['pull_flag']}  "
                          f"K={kd}")
        else:
            print("  k_flag/pull_flag columns not found in luck_scores.csv — run score_luck.py first")
    else:
        print(f"  {LUCK_SCORES_PATH} not found")

    # ══════════════════════════════════════════════════════════════════════════
    print(f"\n{'═'*76}")
    print("SECTION 2: PITCHER WITHIN-SEASON BACKTEST  (April 2024 → May-July 2024)")
    print("═"*76)

    print("\nRunning v6 pitcher backtest (2 IP min + volatility, no FIP- override)...")
    v6_p   = run_pitcher_backtest("v6", use_2ip=True, use_volatility=True, use_fip_override=False)

    print("\nRunning v7 pitcher backtest (v6 + FIP- override for stuff+ miscalibration)...")
    v7_p   = run_pitcher_backtest("v7", use_2ip=True, use_volatility=True, use_fip_override=True)

    if v6_p and v7_p:
        print(f"\n{'='*76}")
        print("PITCHER ACCURACY TABLE  (v6 vs v7: FIP- override addition)")
        print(f"{'='*76}")
        print_pitcher_comparison(v6_p, v7_p)

        print(f"\n  v6: {v6_p['n_signal']} signal pitchers → {v6_p['n_eval']} eval")
        print(f"  v7: {v7_p['n_signal']} signal pitchers → {v7_p['n_eval']} eval")
        if v7_p.get("n_excluded_starts"):
            print(f"  2 IP filter: {v7_p['n_excluded_starts']} starts excluded")
        if v7_p.get("n_vol_flagged"):
            print(f"  Volatility: {v7_p['n_vol_flagged']} pitchers flagged  |  "
                  f"{v7_p['n_vol_dampened']} buy signals dampened ×{VOL_DAMP}")

    # ══════════════════════════════════════════════════════════════════════════
    print(f"\n{'═'*76}")
    print("PITCHER COMPARISON  (v6 vs v7: FIP- override addition)")
    print("═"*76)

    p_ov_v7 = v7_p["stats"]["OVERALL"][2]  if v7_p else float("nan")
    p_bl_v7 = v7_p["stats"]["BUY_LOW"][2]  if v7_p else float("nan")
    p_sh_v7 = v7_p["stats"]["SELL_HIGH"][2] if v7_p else float("nan")
    p_ov_v6 = v6_p["stats"]["OVERALL"][2]  if v6_p else float("nan")
    p_bl_v6 = v6_p["stats"]["BUY_LOW"][2]  if v6_p else float("nan")
    p_sh_v6 = v6_p["stats"]["SELL_HIGH"][2] if v6_p else float("nan")

    print(f"\n  {'Metric':<32} {'v6':>8} {'v7':>8} {'Delta':>8}")
    print(f"  {'-' * 60}")
    for lbl, v6_val, v7_val in [
        ("Pitcher overall (2024)",   p_ov_v6,  p_ov_v7),
        ("Pitcher BUY_LOW (2024)",   p_bl_v6,  p_bl_v7),
        ("Pitcher SELL_HIGH (2024)", p_sh_v6,  p_sh_v7),
    ]:
        if math.isnan(v6_val) or math.isnan(v7_val):
            print(f"  {lbl:<32} {'n/a':>7}  {'n/a':>7}  {'n/a':>7}")
            continue
        delta = v7_val - v6_val
        arrow = " <-- improved" if delta > 0.005 else (" <-- worse" if delta < -0.005 else " (stable)")
        print(f"  {lbl:<32} {v6_val:>7.1%} {v7_val:>7.1%} {delta:>+7.1%}{arrow}")

    print(f"\n  Q: Does pitcher SELL_HIGH 100% record hold with FIP- override?")
    print(f"     v6={p_sh_v6:.1%}  v7={p_sh_v7:.1%}  "
          f"Answer: {'HOLDS' if p_sh_v7 >= 0.999 else f'CHANGED to {p_sh_v7:.1%}'}")

    delta_ov = p_ov_v7 - p_ov_v6 if not math.isnan(p_ov_v7) else float("nan")
    ans_p = ("IMPROVED" if not math.isnan(delta_ov) and delta_ov >  0.01 else
             "HURT"     if not math.isnan(delta_ov) and delta_ov < -0.01 else "NEUTRAL")
    print(f"  Q: Does FIP- override improve pitcher accuracy?  Answer: {ans_p}")

    print(f"\n  Q: Is 2025 the strongest hitter OOS year?")
    yr_ov = [(r["year"], r["stats"]["OVERALL"][2]) for r in h_results]
    best_yr, _ = max(yr_ov, key=lambda x: x[1])
    for yr, acc in yr_ov:
        marker = " <-- best" if yr == best_yr else ""
        n_eval = next(r["n_eval"] for r in h_results if r["year"] == yr)
        print(f"     {yr}: {acc:.1%}  (n={n_eval}){marker}")

    # ══════════════════════════════════════════════════════════════════════════
    print(f"\n{'═'*76}")
    print("CANONICAL ACCURACY NUMBERS  (backtest thresholds, train/OOS split)")
    print("═"*76)
    total_h_eval = sum(r["n_eval"] for r in h_results)
    train_rs2 = [r for r in h_results if r["year"] in [2022, 2023, 2024]]
    oos_rs2   = [r for r in h_results if r["year"] == 2025]

    def _pool_sig(rlist, sig):
        n_t = c_t = 0
        for r in rlist:
            s = r["stats"].get(sig, (0, 0, float("nan")))
            n_t += s[0]; c_t += s[1]
        return (n_t, c_t / n_t if n_t > 0 else float("nan"))

    print(f"\n  Hitter (backtest thresholds: BUY_LOW >=0.040 | SELL_HIGH <=-0.065):")
    print(f"  {'Signal':<14} {'Train 22-24 n':>13} {'Train acc':>10} {'OOS 2025 n':>11} {'OOS acc':>9}")
    print(f"  {'-' * 60}")
    for sig in ["BUY_LOW","SLIGHT_BUY","SELL_HIGH","SLIGHT_SELL","OVERALL"]:
        if sig == "OVERALL":
            print(f"  {'-' * 60}")
        tn, ta = _pool_sig(train_rs2, sig)
        on, oa = _pool_sig(oos_rs2,   sig)
        ta_s = f"{ta:.1%}" if not math.isnan(ta) else "n/a"
        oa_s = f"{oa:.1%}" if not math.isnan(oa) else "n/a"
        print(f"  {sig:<14} {tn:>13}  {ta_s:>9} {on:>11}  {oa_s:>8}")

    print(f"\n  Hitter 4yr pooled overall: {h_ov:.1%}  vs RTM: {h_rtm:>+.1%}pp  ({total_h_eval} player-seasons)")
    print()
    if not math.isnan(p_ov_v7):
        p_eval = v7_p.get("n_eval", 0)
        print(f"  Pitcher overall (v7, 2024):   {p_ov_v7:.1%}  (vs v6={V6_P_OVERALL:.1%}  Δ={p_ov_v7-V6_P_OVERALL:>+.1%})")
        print(f"  Pitcher SELL_HIGH (v7, 2024): {p_sh_v7:.1%}")
        print(f"  Pitcher BUY_LOW (v7, 2024):   {p_bl_v7:.1%}")
        print(f"  Pitcher vs RTM (v7):          {p_ov_v7-RTM_BASELINE:>+.1%}pp  ({p_eval} pitchers)")


if __name__ == "__main__":
    main()
