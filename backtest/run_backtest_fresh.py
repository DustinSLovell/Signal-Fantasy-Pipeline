"""
run_backtest_fresh.py
======================
Fresh 2022-2025 backtest for both hitter and pitcher models.
Re-runs from raw Statcast cache — no result caching read.

Produces:
  • Full accuracy tables (signal × year, with n= and avg Δ)
  • data/backtest_audit_hitters.csv   — row-level hitter results
  • data/backtest_audit_pitchers.csv  — row-level pitcher results
  • Diagnostic flags (wrong + large magnitude, weak tiers)

Model versions tested:
  Hitters: v7 logic — L1(xwoba+babip) + L2(sweet-spot) + L3(EV) +
           L4(OAA-BABIP) + L5(seasonal patterns) + disc/bb-k filter
  Pitchers: v7 logic — ERA-FIP gap + BABIP luck + stuff+ modifier +
            volatility dampening + FIP- override (v7 addition)

Constraints: scoring logic UNCHANGED — read-only audit.
"""

import io
import json
import math
import os
import sys
import numpy as np
import pandas as pd
from pathlib import Path

# ── path + imports ────────────────────────────────────────────────────────────
BASE_DIR  = Path(os.path.dirname(os.path.abspath(__file__))).parent  # project root
CACHE_DIR = BASE_DIR / "backtest_cache"
DATA_DIR  = BASE_DIR / "data"
sys.path.insert(0, str(BASE_DIR))

from backtest_pitcher_within_season import compute_pitcher_stats as _pitcher_stats_orig
if isinstance(sys.stdout, io.TextIOWrapper):
    _buf = sys.stdout.detach()
else:
    _buf = getattr(sys.stdout, "buffer", sys.stdout)
sys.stdout = io.TextIOWrapper(_buf, encoding="utf-8", errors="replace")

# ══════════════════════════════════════════════════════════════════════════════
# CONSTANTS  (verbatim from backtest_multi_year_v7.py — do not change)
# ══════════════════════════════════════════════════════════════════════════════
MIN_APRIL_PA       = 80
MIN_OUTCOME_PA     = 100
FLAT_THRESHOLD     = 0.015
RTM_BASELINE       = 0.682          # naïve "predict everyone improves" baseline
LEAGUE_AVG_BABIP   = 0.300
EV_THRESHOLD       = 1.0
SELL_HIGH_THRESH   = -0.065
SLIGHT_SELL_THRESH = -0.040

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
    'vshape_buy':  1.20,
    'slow_buy':    1.10,
    'summer_buy':  1.10,
    'fader_sell':  1.15,
    'fader_buy':   0.90,
}

# Pitcher constants
MIN_START_IP_P     = 2.0
MIN_APRIL_IP_P     = 15.0
MIN_OUTCOME_IP_P   = 30.0
ERA_FLAT_P         = 0.40
FIP_CONST          = 3.10
LEAGUE_AVG_BABIP_P = 0.300
P_BUY_LOW_THRESH   =  1.20
P_SLIGHT_BUY_THRESH=  0.60
P_SELL_HIGH_THRESH = -1.20
P_SLIGHT_SELL_THRESH= -0.60
DISASTER_ERA_P     = 10.0
DISASTER_RATE_P    = 0.30
START_VAR_P        = 4.0
VOL_DAMP           = 0.90
LG_XWOBA_P         = 0.320
LG_ERA_P           = 4.00
XERA_SCALE_P       = 33.0

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

DISPLAY = {
    'BUY_LOW':    'Buy Low',
    'SLIGHT_BUY': 'Slight Buy',
    'NEUTRAL':    'Neutral',
    'SLIGHT_SELL':'Slight Sell',
    'SELL_HIGH':  'Sell High',
}

YEARS = [2022, 2023, 2024, 2025]

# ══════════════════════════════════════════════════════════════════════════════
# SHARED UTILITIES
# ══════════════════════════════════════════════════════════════════════════════

def _babip_age_mult(age: int) -> float:
    if age >= 39: return 0.88
    if age >= 37: return 0.91
    if age >= 35: return 0.94
    if age >= 32: return 0.97
    return 1.0


def build_pitcher_name_lookup() -> dict[int, str]:
    result = {}
    for yr in YEARS:
        p = CACHE_DIR / f"pitcher_statcast_april_{yr}.parquet"
        if not p.exists():
            continue
        df = pd.read_parquet(p, columns=["pitcher", "player_name"])
        df = df[df["player_name"].notna() & df["pitcher"].notna()].copy()
        df["pitcher"] = df["pitcher"].astype(int)
        for pid, name in df.groupby("pitcher")["player_name"].first().items():
            parts = str(name).split(", ", 1)
            result[int(pid)] = (f"{parts[1]} {parts[0]}".strip()
                                if len(parts) == 2 else parts[0])
    return result


def build_hitter_name_lookup() -> dict[int, str]:
    all_ids = set()
    for yr in YEARS:
        p = CACHE_DIR / f"v4_april_{yr}.csv"
        if p.exists():
            df = pd.read_csv(p, usecols=["batter"])
            all_ids.update(df["batter"].dropna().astype(int).tolist())
    if not all_ids:
        return {}
    try:
        from pybaseball import playerid_reverse_lookup
        lu = playerid_reverse_lookup(sorted(all_ids), key_type="mlbam")
        result = {}
        if lu is not None and not lu.empty:
            for _, row in lu.iterrows():
                mid = int(row.get("key_mlbam", 0) or 0)
                fn  = str(row.get("name_first", "") or "").strip().title()
                ln  = str(row.get("name_last",  "") or "").strip().title()
                if mid > 0:
                    result[mid] = f"{fn} {ln}".strip() if fn else ln
        print(f"  Hitter names resolved: {len(result)}/{len(all_ids)}")
        return result
    except Exception as ex:
        print(f"  WARNING: name lookup failed: {ex}")
        return {}


# ══════════════════════════════════════════════════════════════════════════════
# HITTER MODULE
# ══════════════════════════════════════════════════════════════════════════════

def classify_h(score: float) -> str:
    if score >= 0.040:              return "BUY_LOW"
    if score >= 0.020:              return "SLIGHT_BUY"
    if score <= SELL_HIGH_THRESH:   return "SELL_HIGH"
    if score <= SLIGHT_SELL_THRESH: return "SLIGHT_SELL"
    return "NEUTRAL"


def run_hitter_year(year: int, career_stats: dict, patterns: dict,
                    career_babip: dict, opp_oaa: dict,
                    name_lut: dict) -> pd.DataFrame | None:
    """
    Fresh computation for one hitter year from raw Statcast cache.
    Returns row-level DataFrame (all players, eval-flagged).
    """
    april_path   = CACHE_DIR / f"v4_april_{year}.csv"
    outcome_path = CACHE_DIR / f"statcast_{year}_may_july.csv"
    team_path    = CACHE_DIR / f"team_map_{year}.csv"
    if not april_path.exists() or not outcome_path.exists():
        print(f"  {year}: SKIPPED — cache missing")
        return None

    april   = pd.read_csv(april_path)
    outcome = pd.read_csv(outcome_path)
    if team_path.exists():
        april = april.merge(pd.read_csv(team_path), on="batter", how="left")
    april["park_factor"] = (april["team"].map(PARK_FACTORS_H).fillna(1.0)
                            if "team" in april.columns else 1.0)

    # ── BIP / BBE / discipline aggregation ────────────────────────────────
    batted = april[april["bb_type"].notna() & (april["bb_type"] != "")].copy()
    batted["is_bip"] = batted["events"].isin(BIP_EVENTS_H).astype(int)
    batted["is_hit"] = batted["events"].isin({"single","double","triple"}).astype(int)
    batted["is_gb"]  = (batted["bb_type"] == "ground_ball").astype(int)
    bip_agg = batted.groupby("batter").agg(
        bip=("is_bip","sum"), hits_bip=("is_hit","sum"), gb=("is_gb","sum")
    ).reset_index()

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
        bb_count=("is_bb","sum"), k_count=("is_k","sum")
    ).reset_index()

    has_xwoba = "estimated_woba_using_speedangle" in april.columns
    pa_agg = april.groupby("batter").agg(
        april_pa=("woba_value","count"),
        april_actual_woba=("woba_value","mean"),
        **({ "april_xwoba": ("estimated_woba_using_speedangle","mean") } if has_xwoba else {}),
        park_factor=("park_factor","first"),
    ).reset_index()
    if not has_xwoba:
        pa_agg["april_xwoba"] = np.nan

    sig = pa_agg.merge(bip_agg, on="batter", how="left")
    if has_bbe:
        sig = sig.merge(bbe_agg, on="batter", how="left")
    else:
        for c in ["sweet_spot_count","bbe_total","avg_exit_velocity"]:
            sig[c] = np.nan
    sig = sig.merge(disc_agg, on="batter", how="left")

    sig["babip"]           = np.where(sig["bip"]>0, sig["hits_bip"]/sig["bip"], np.nan)
    sig["gb_rate"]         = np.where(sig["bip"]>0, sig["gb"]/sig["bip"], np.nan)
    sig["sweet_spot_rate"] = np.where(sig["bbe_total"]>0,
                                       sig["sweet_spot_count"]/sig["bbe_total"], np.nan)
    sig["bb_rate"] = sig["bb_count"] / sig["april_pa"]
    sig["k_rate"]  = sig["k_count"]  / sig["april_pa"]
    sig["xwoba_gap"] = sig["april_xwoba"] - sig["april_actual_woba"]

    # ── BABIP baseline (career + age adj + park adj + OAA) ────────────────
    sig["babip_baseline"] = sig["batter"].map(
        lambda bid: career_babip.get(int(bid), LEAGUE_AVG_BABIP))

    def _age_babip(row) -> float:
        bid  = int(row["batter"])
        base = row["babip_baseline"]
        if base == LEAGUE_AVG_BABIP:
            return base
        byr = int((career_stats.get(bid) or {}).get("birth_year") or 0)
        return round(base * _babip_age_mult(year - byr), 4) if byr else base

    sig["babip_baseline"] = sig.apply(_age_babip, axis=1)
    sig["babip_expected"] = (sig["babip_baseline"] - (sig["park_factor"] - 1.0) * 0.10).round(4)

    if opp_oaa:
        sig["oaa_babip_adj"] = sig["batter"].apply(lambda b: opp_oaa.get(int(b), 0.0))
        sig["babip_expected"] = (sig["babip_expected"] + sig["oaa_babip_adj"]).round(4)

    if sig["gb_rate"].notna().any():
        sig.loc[sig["gb_rate"] > 0.50, "babip_expected"] -= 0.010
        sig.loc[sig["gb_rate"] < 0.35, "babip_expected"] += 0.008

    sig["babip_luck"] = sig["babip_expected"] - sig["babip"]
    sig = sig[sig["april_pa"] >= MIN_APRIL_PA].copy()

    # ── L1 core score ─────────────────────────────────────────────────────
    sig["luck_score"] = (sig["xwoba_gap"] * 0.60 + sig["babip_luck"] * 0.40).round(4)

    # ── L2 sweet-spot modifier ────────────────────────────────────────────
    if sig["sweet_spot_rate"].notna().any():
        buy = sig["luck_score"] > 0
        sig.loc[buy & (sig["sweet_spot_rate"] > 0.12), "luck_score"] = \
            (sig.loc[buy & (sig["sweet_spot_rate"] > 0.12), "luck_score"] * 1.05).round(4)
        sig.loc[buy & (sig["sweet_spot_rate"] < 0.06), "luck_score"] = \
            (sig.loc[buy & (sig["sweet_spot_rate"] < 0.06), "luck_score"] * 0.95).round(4)

    # ── L3 EV trend ───────────────────────────────────────────────────────
    if sig["avg_exit_velocity"].notna().any():
        for idx, row in sig.iterrows():
            if row["luck_score"] <= 0:
                continue
            career_ev = (career_stats.get(int(row["batter"])) or {}).get("avg_exit_velocity")
            if career_ev is None or pd.isna(row["avg_exit_velocity"]):
                continue
            ev_below = (row["avg_exit_velocity"] - career_ev) < -EV_THRESHOLD
            ss       = row["sweet_spot_rate"]
            low_ss   = pd.notna(ss) and ss < 0.08
            if ev_below and low_ss:
                sig.at[idx, "luck_score"] = round(row["luck_score"] * 0.85, 4)
            elif ev_below or low_ss:
                sig.at[idx, "luck_score"] = round(row["luck_score"] * 0.93, 4)

    # ── L5 discipline filter ──────────────────────────────────────────────
    if sig["bb_rate"].notna().any():
        buy_m = sig["luck_score"] > 0
        elite = buy_m & (sig["bb_rate"] > 0.10) & (sig["k_rate"] < 0.18)
        poor  = buy_m & ((sig["bb_rate"] < 0.06) | (sig["k_rate"] > 0.28))
        sig.loc[elite, "luck_score"] = (sig.loc[elite, "luck_score"] * 1.08).round(4)
        sig.loc[poor,  "luck_score"] = (sig.loc[poor,  "luck_score"] * 0.88).round(4)

    # ── L6 seasonal patterns ──────────────────────────────────────────────
    if patterns:
        for idx, row in sig.iterrows():
            pid = int(row["batter"]); raw = row["luck_score"]
            if pid not in patterns:
                continue
            p = patterns[pid]
            slow = p.get("slow_starter", False)
            fader = p.get("second_half_fader", False)
            summer = p.get("summer_performer", False)
            mult = 1.0
            is_buy = raw > 0; is_sell = raw < 0
            if slow and summer:
                if is_buy: mult = PHASE_C["vshape_buy"]
            elif slow:
                if is_buy: mult = PHASE_C["slow_buy"]
            elif summer:
                if is_buy: mult = PHASE_C["summer_buy"]
            if fader:
                if is_sell:   mult = max(mult, PHASE_C["fader_sell"])
                elif is_buy:  mult = min(mult, PHASE_C["fader_buy"])
            if mult != 1.0:
                sig.at[idx, "luck_score"] = round(raw * mult, 4)

    sig["signal"] = sig["luck_score"].apply(classify_h)

    # ── Outcomes ──────────────────────────────────────────────────────────
    may_july = outcome.groupby("batter").agg(
        outcome_pa=("woba_value","count"),
        outcome_woba=("woba_value","mean"),
    ).reset_index()

    merged = sig.merge(may_july, on="batter", how="inner")
    merged = merged[merged["outcome_pa"] >= MIN_OUTCOME_PA].copy()
    merged["woba_change"] = merged["outcome_woba"] - merged["april_actual_woba"]
    merged["outcome"] = np.where(
        merged["woba_change"] >=  FLAT_THRESHOLD, "IMPROVED",
        np.where(merged["woba_change"] <= -FLAT_THRESHOLD, "DECLINED", "FLAT")
    )

    merged["predicted_direction"] = merged["signal"].map(SIGNAL_MAP_H).fillna("")
    merged["in_eval"] = merged["signal"].isin(SIGNAL_MAP_H) & (merged["outcome"] != "FLAT")
    eval_df = merged[merged["in_eval"]].copy()
    eval_df["correct"] = eval_df.apply(
        lambda r: r["outcome"] == SIGNAL_MAP_H[r["signal"]], axis=1)
    merged = merged.merge(eval_df[["batter","correct"]], on="batter", how="left")

    # ── Build output rows ─────────────────────────────────────────────────
    rows = []
    for _, r in merged.iterrows():
        bid = int(r["batter"])
        rows.append({
            "player_name":       name_lut.get(bid, f"ID_{bid}"),
            "mlbam_id":          bid,
            "year":              year,
            "signal":            DISPLAY.get(r["signal"], r["signal"]),
            "luck_score":        round(float(r["luck_score"]), 4),
            "woba_actual":       round(float(r["april_actual_woba"]), 4),
            "xwoba_actual":      round(float(r["april_xwoba"]), 4) if pd.notna(r.get("april_xwoba")) else None,
            "predicted_direction": r["predicted_direction"],
            "actual_woba_change": round(float(r["woba_change"]), 4),
            "outcome":           r["outcome"],
            "in_eval":           bool(r["in_eval"]),
            "correct":           bool(r["correct"]) if pd.notna(r.get("correct")) else None,
        })
    result = pd.DataFrame(rows)
    n_eval = int(result["in_eval"].sum())
    n_corr = int(result[result["in_eval"]]["correct"].sum())
    pct    = n_corr / n_eval if n_eval > 0 else float("nan")
    print(f"  {year}: {len(merged):>3} players  |  {n_eval:>3} eval  |  {n_corr:>3} correct  ({pct:.1%})")
    return result


# ══════════════════════════════════════════════════════════════════════════════
# PITCHER MODULE
# ══════════════════════════════════════════════════════════════════════════════

def _prep_pitcher_sc(sc: pd.DataFrame) -> pd.DataFrame:
    sc = sc.copy()
    sc["pitcher"] = pd.to_numeric(sc["pitcher"], errors="coerce")
    sc = sc[sc["pitcher"].notna()].copy()
    sc["pitcher"] = sc["pitcher"].astype(int)
    ev = sc["events"].notna() & (sc["events"] != "")
    sc["is_out"] = (sc["events"].isin(P_OUT_EVENTS) & ev).astype(int)
    sc["is_dp"]  = (sc["events"].isin({"grounded_into_double_play","double_play",
                                         "strikeout_double_play"}) & ev).astype(int)
    return sc


def compute_per_start(sc: pd.DataFrame) -> pd.DataFrame:
    if "game_pk" not in sc.columns:
        return pd.DataFrame(columns=["pitcher","game_pk","start_ip","start_ra",
                                     "start_era","qualifying","is_qs","is_disaster"])
    sc = _prep_pitcher_sc(sc)
    ev = sc[sc["events"].notna() & (sc["events"] != "")].copy()

    outs_s = ev.groupby(["pitcher","game_pk"]).agg(
        outs=("is_out","sum"), dp=("is_dp","sum")).reset_index()
    outs_s["start_ip"] = (outs_s["outs"] + outs_s["dp"]) / 3.0

    if "post_bat_score" in ev.columns and "bat_score" in ev.columns:
        re = ev[ev["post_bat_score"].notna() & ev["bat_score"].notna()].copy()
        re["runs"] = (re["post_bat_score"] - re["bat_score"]).clip(lower=0)
        runs_s = re.groupby(["pitcher","game_pk"])["runs"].sum().reset_index()
        runs_s.rename(columns={"runs":"start_ra"}, inplace=True)
    else:
        runs_s = outs_s[["pitcher","game_pk"]].copy(); runs_s["start_ra"] = 0.0

    starts = outs_s.merge(runs_s, on=["pitcher","game_pk"], how="left")
    starts["start_ra"] = starts["start_ra"].fillna(0.0)
    starts["start_era"] = np.where(
        starts["start_ip"] > 0, (starts["start_ra"] / starts["start_ip"]) * 9, np.nan
    ).round(2)
    starts["qualifying"]  = starts["start_ip"] >= MIN_START_IP_P
    starts["is_qs"]       = (starts["start_ip"] >= 6.0) & (starts["start_ra"] <= 3)
    starts["is_disaster"] = (starts["start_era"] > DISASTER_ERA_P) & starts["qualifying"]
    return starts[["pitcher","game_pk","start_ip","start_ra","start_era",
                   "qualifying","is_qs","is_disaster"]]


def compute_volatility(start_stats: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for pid, grp in start_stats.groupby("pitcher"):
        total = len(grp)
        dr    = int(grp["is_disaster"].sum()) / total if total > 0 else 0.0
        qual  = grp.loc[grp["qualifying"],"start_era"].dropna()
        sv    = float(qual.std()) if len(qual) >= 2 else float("nan")
        rows.append({
            "pitcher": int(pid),
            "disaster_rate": round(dr, 3),
            "start_variance": round(sv, 2) if not math.isnan(sv) else None,
            "volatility_flag": dr > DISASTER_RATE_P or (not math.isnan(sv) and sv > START_VAR_P),
        })
    return pd.DataFrame(rows)


def compute_pitcher_stats_v7(sc: pd.DataFrame, start_stats: pd.DataFrame) -> pd.DataFrame:
    """
    ERA/FIP/BABIP with 2 IP per-start filter + xERA from xwOBA.
    Adds xera column for audit output.
    """
    sc = _prep_pitcher_sc(sc)
    ev = sc[sc["events"].notna() & (sc["events"] != "")].copy()

    # Qualifying-start subset
    if "game_pk" in start_stats.columns and not start_stats.empty:
        qp = start_stats[start_stats["qualifying"]][["pitcher","game_pk"]].assign(_q=True)
        sc_mq = sc.merge(qp, on=["pitcher","game_pk"], how="left") if "game_pk" in sc.columns else sc.assign(_q=False)
        sc_q  = sc[sc_mq["_q"].fillna(False).values].copy()
        ev_q  = sc_q[sc_q["events"].notna() & (sc_q["events"] != "")].copy()
    else:
        sc_q = sc.copy(); ev_q = ev.copy()

    def _ip(df):
        a = df.groupby("pitcher").agg(outs=("is_out","sum"), dp=("is_dp","sum")).reset_index()
        a["ip"] = (a["outs"] + a["dp"]) / 3.0
        return a.set_index("pitcher")["ip"]

    ip_q   = _ip(ev_q)
    ip_all = _ip(ev)

    # ERA
    if "post_bat_score" in ev_q.columns and "bat_score" in ev_q.columns:
        re = ev_q[ev_q["post_bat_score"].notna() & ev_q["bat_score"].notna()].copy()
        re["runs"] = (re["post_bat_score"] - re["bat_score"]).clip(lower=0)
        ra_q = re.groupby("pitcher")["runs"].sum()
    else:
        ra_q = pd.Series(dtype=float)
    era_q = (ra_q / (ip_q / 9)).where(ip_q > 0).round(2)

    if "post_bat_score" in ev.columns and "bat_score" in ev.columns:
        re2 = ev[ev["post_bat_score"].notna() & ev["bat_score"].notna()].copy()
        re2["runs"] = (re2["post_bat_score"] - re2["bat_score"]).clip(lower=0)
        ra_all = re2.groupby("pitcher")["runs"].sum()
        era_all = (ra_all / (ip_all / 9)).where(ip_all > 0).round(2)
    else:
        era_all = pd.Series(dtype=float)
    era_final = era_q.combine_first(era_all)

    # FIP
    ev_q["is_k"]  = ev_q["events"].isin({"strikeout","strikeout_double_play"}).astype(int)
    ev_q["is_bb"] = ev_q["events"].isin({"walk","intent_walk"}).astype(int)
    ev_q["is_hr"] = (ev_q["events"] == "home_run").astype(int)
    fip_agg = ev_q.groupby("pitcher").agg(k=("is_k","sum"), bb=("is_bb","sum"), hr=("is_hr","sum"))
    fip_s = ((13*fip_agg["hr"] + 3*fip_agg["bb"] - 2*fip_agg["k"]) / ip_q + FIP_CONST
             ).where(ip_q > 0).round(2)

    # BABIP
    ev_q["is_bip"] = ev_q["events"].isin(P_BIP_EVENTS).astype(int)
    ev_q["is_hit"] = ev_q["events"].isin({"single","double","triple"}).astype(int)
    b_agg = ev_q.groupby("pitcher").agg(bip=("is_bip","sum"), hits=("is_hit","sum"))
    babip_q = (b_agg["hits"] / b_agg["bip"]).where(b_agg["bip"] > 0).round(3)
    ev["is_bip"] = ev["events"].isin(P_BIP_EVENTS).astype(int)
    ev["is_hit"] = ev["events"].isin({"single","double","triple"}).astype(int)
    b2 = ev.groupby("pitcher").agg(bip=("is_bip","sum"), hits=("is_hit","sum"))
    babip_all = (b2["hits"] / b2["bip"]).where(b2["bip"] > 0).round(3)
    babip_final = babip_q.combine_first(babip_all)

    # xERA from xwOBA allowed (using all appearances, same as process_pitcher_stats.py)
    xera_s = pd.Series(dtype=float, name="xera")
    if "estimated_woba_using_speedangle" in sc.columns:
        pa_ev = sc[sc["events"].notna() & ~sc["events"].isin({"truncated_pa"})].copy()
        pa_ev["xwoba_val"] = np.where(
            pa_ev["estimated_woba_using_speedangle"].notna(),
            pa_ev["estimated_woba_using_speedangle"],
            pa_ev["woba_value"]
        )
        xwoba_agg = pa_ev.groupby("pitcher")["xwoba_val"].mean()
        xera_s = ((xwoba_agg - LG_XWOBA_P) * XERA_SCALE_P + LG_ERA_P).round(2).rename("xera")

    # Team / Name
    team_s = pd.Series(dtype=str, name="team")
    name_s = pd.Series(dtype=str, name="name")
    if {"home_team","away_team","inning_topbot"}.issubset(sc.columns):
        sc["p_team"] = sc.apply(
            lambda r: r["away_team"] if r["inning_topbot"]=="Top" else r["home_team"], axis=1)
        team_s = sc.groupby("pitcher")["p_team"].agg(lambda x: x.mode().iloc[0])
    if "player_name" in sc.columns:
        name_s = sc.groupby("pitcher")["player_name"].first()

    agg = pd.DataFrame({"ip": ip_all, "era": era_final, "fip": fip_s,
                         "babip": babip_final})
    agg = agg.join(xera_s, how="left").join(team_s, how="left").join(name_s, how="left")
    return agg.reset_index().rename(columns={"index":"pitcher"})


def classify_p(gap: float) -> str:
    if gap >= P_BUY_LOW_THRESH:      return "BUY_LOW"
    if gap >= P_SLIGHT_BUY_THRESH:   return "SLIGHT_BUY"
    if gap <= P_SELL_HIGH_THRESH:    return "SELL_HIGH"
    if gap <= P_SLIGHT_SELL_THRESH:  return "SLIGHT_SELL"
    return "NEUTRAL"


def run_pitcher_year(year: int, stuff_plus: dict, career_babip: dict,
                     name_lut: dict) -> pd.DataFrame | None:
    """
    Fresh computation for one pitcher year. Returns row-level DataFrame.
    Includes xera_actual column.
    """
    april_path   = CACHE_DIR / f"pitcher_statcast_april_{year}.parquet"
    outcome_path = CACHE_DIR / f"pitcher_statcast_mayjuly_{year}.parquet"
    if not april_path.exists() or not outcome_path.exists():
        print(f"  {year}: SKIPPED — cache missing")
        return None

    april_sc  = pd.read_parquet(april_path)
    out_sc    = pd.read_parquet(outcome_path)
    if april_sc.empty or out_sc.empty:
        print(f"  {year}: SKIPPED — empty")
        return None

    apr_starts = compute_per_start(april_sc)
    out_starts = compute_per_start(out_sc)

    apr = compute_pitcher_stats_v7(april_sc,  apr_starts)
    out = compute_pitcher_stats_v7(out_sc,    out_starts)

    apr = apr[apr["ip"] >= MIN_APRIL_IP_P].copy()
    out = out[out["ip"] >= MIN_OUTCOME_IP_P].copy()

    sig = apr.copy()
    sig["park_factor"]   = sig["team"].map(PARK_FACTORS_H).fillna(1.0) if "team" in sig.columns else 1.0
    sig["career_babip"]  = sig["pitcher"].map(career_babip).fillna(LEAGUE_AVG_BABIP_P)
    sig["babip_expected"]= sig["career_babip"] * sig["park_factor"]
    sig["babip_luck"]    = sig["babip_expected"] - sig["babip"]
    sig["era_fip_gap"]   = sig["era"] - sig["fip"]

    sig["stuff_plus"]     = sig["pitcher"].map(stuff_plus)
    sig["luck_score_raw"] = (sig["era_fip_gap"] * 0.70 + sig["babip_luck"] * 0.30 * 9).round(3)

    # FIP- override (v7)
    q_fip   = sig[sig["ip"] >= 15]["fip"].dropna()
    lg_fip  = q_fip.mean() if len(q_fip) > 0 else sig["fip"].dropna().mean()
    sig["fip_minus"] = (sig["fip"] / lg_fip * (1.0 / sig["park_factor"]) * 100).where(
        sig["fip"].notna(), other=float("nan"))

    def _stuff(row):
        score = row["luck_score_raw"]
        sp = row["stuff_plus"]
        if pd.isna(sp):
            return score
        fip_m = row["fip_minus"]
        ok    = not (isinstance(fip_m, float) and math.isnan(fip_m))
        if ok and fip_m < 85  and sp < 95:
            return round(score * 0.85, 3) if score < 0 else score
        if ok and fip_m > 115 and sp > 105:
            return round(score * 1.15, 3) if score < 0 else score
        if sp >= 115 and score > 0: return round(score * 1.15, 3)
        if sp < 90   and score < 0: return round(score * 1.15, 3)
        if sp >= 115 and score < 0: return round(score * 0.85, 3)
        if sp < 90   and score > 0: return round(score * 0.85, 3)
        return score

    sig["luck_score"] = sig.apply(_stuff, axis=1)

    # Volatility
    if not apr_starts.empty:
        vol = compute_volatility(apr_starts)
        vol["pitcher"] = vol["pitcher"].astype(int)
        sig = sig.merge(vol[["pitcher","disaster_rate","start_variance","volatility_flag"]],
                        on="pitcher", how="left")
        sig["volatility_flag"] = sig["volatility_flag"].fillna(False)
        buy_vol = sig["volatility_flag"] & (sig["luck_score"] > 0)
        sig.loc[buy_vol, "luck_score"] = (sig.loc[buy_vol, "luck_score"] * VOL_DAMP).round(3)
    else:
        sig["volatility_flag"] = False

    sig["signal"] = sig["era_fip_gap"].apply(classify_p)

    # Outcomes
    merged = sig.merge(
        out[["pitcher","era","fip","ip","xera"]].rename(columns={
            "era":"outcome_era","fip":"outcome_fip","ip":"outcome_ip","xera":"outcome_xera"}),
        on="pitcher", how="inner"
    )
    merged["era_change"] = merged["outcome_era"] - merged["era"]
    merged["outcome"] = np.where(
        merged["era_change"] <= -ERA_FLAT_P, "IMPROVED",
        np.where(merged["era_change"] >=  ERA_FLAT_P, "DECLINED", "FLAT")
    )
    merged["predicted_direction"] = merged["signal"].map(SIGNAL_MAP_P).fillna("")
    merged["in_eval"] = merged["signal"].isin(SIGNAL_MAP_P) & (merged["outcome"] != "FLAT")
    eval_df = merged[merged["in_eval"]].copy()
    eval_df["correct"] = eval_df.apply(
        lambda r: r["outcome"] == SIGNAL_MAP_P[r["signal"]], axis=1)
    merged = merged.merge(eval_df[["pitcher","correct"]], on="pitcher", how="left")

    rows = []
    for _, r in merged.iterrows():
        pid = int(r["pitcher"])
        raw_name = r.get("name", "")
        if raw_name and pd.notna(raw_name):
            parts = str(raw_name).split(", ", 1)
            disp = f"{parts[1]} {parts[0]}".strip() if len(parts) == 2 else parts[0]
        else:
            disp = name_lut.get(pid, f"ID_{pid}")
        rows.append({
            "player_name":       disp,
            "mlbam_id":          pid,
            "year":              year,
            "signal":            DISPLAY.get(r["signal"], r["signal"]),
            "luck_score":        round(float(r["luck_score"]), 3),
            "era_actual":        round(float(r["era"]), 2) if pd.notna(r["era"]) else None,
            "fip_actual":        round(float(r["fip"]), 2) if pd.notna(r["fip"]) else None,
            "xera_actual":       round(float(r["xera"]), 2) if pd.notna(r.get("xera")) else None,
            "predicted_direction": r["predicted_direction"],
            "actual_era_change": round(float(r["era_change"]), 2),
            "outcome":           r["outcome"],
            "in_eval":           bool(r["in_eval"]),
            "correct":           bool(r["correct"]) if pd.notna(r.get("correct")) else None,
        })
    result = pd.DataFrame(rows)
    n_eval = int(result["in_eval"].sum())
    n_corr = int(result[result["in_eval"]]["correct"].sum())
    pct    = n_corr / n_eval if n_eval > 0 else float("nan")
    print(f"  {year}: {len(merged):>3} pitchers  |  {n_eval:>3} eval  |  {n_corr:>3} correct  ({pct:.1%})")
    return result


# ══════════════════════════════════════════════════════════════════════════════
# ACCURACY TABLE PRINTER
# ══════════════════════════════════════════════════════════════════════════════

TIER_ORDER_H = ["BUY_LOW","SLIGHT_BUY","SELL_HIGH","SLIGHT_SELL"]
TIER_ORDER_P = ["BUY_LOW","SLIGHT_BUY","SELL_HIGH","SLIGHT_SELL"]
TIER_DISPLAY  = {
    "BUY_LOW":    "Buy Low",
    "SLIGHT_BUY": "Slight Buy",
    "SELL_HIGH":  "Sell High",
    "SLIGHT_SELL":"Slight Sell",
    "OVERALL":    "Overall",
}


def accuracy_table(df: pd.DataFrame, kind: str, change_col: str) -> None:
    """
    Print accuracy × year table with n= and avg Δ.
    kind: 'hitter' or 'pitcher'
    change_col: 'actual_woba_change' or 'actual_era_change'
    """
    eval_df   = df[df["in_eval"] == True].copy()
    sigs_disp = ["Buy Low","Slight Buy","Sell High","Slight Sell"]
    delta_lbl = "Avg wOBA Δ" if kind == "hitter" else "Avg ERA Δ"

    # Build per-year stats per tier
    stats: dict[str, dict] = {}   # signal → {year → (n, correct, accuracy, avg_delta)}
    for sig in sigs_disp + ["Overall"]:
        stats[sig] = {}
        for yr in YEARS:
            grp = eval_df[(eval_df["year"] == yr) &
                          (eval_df["signal"] == sig if sig != "Overall"
                           else pd.Series([True]*len(eval_df), index=eval_df.index))]
            n   = len(grp)
            c   = int(grp["correct"].sum()) if n > 0 else 0
            acc = c / n if n > 0 else float("nan")
            avg_d = grp[change_col].mean() if n > 0 else float("nan")
            stats[sig][yr] = (n, c, acc, avg_d)

    # 4yr aggregates
    def _agg(sig):
        n_all = sum(stats[sig][yr][0] for yr in YEARS)
        c_all = sum(stats[sig][yr][1] for yr in YEARS)
        acc   = c_all / n_all if n_all > 0 else float("nan")
        avg_d = eval_df[
            (eval_df["signal"] == sig if sig != "Overall"
             else pd.Series([True]*len(eval_df), index=eval_df.index))
        ][change_col].mean()
        return (n_all, c_all, acc, avg_d)

    agg = {sig: _agg(sig) for sig in sigs_disp + ["Overall"]}

    # Print
    YW = 14         # year column width
    SEP = "+" + "-"*14 + "+" + ("-"*YW+"+") * len(YEARS) + "-"*14 + "+" + "-"*12 + "+"
    print(SEP)
    hdr = f"| {'Signal':<12} |"
    for yr in YEARS:
        hdr += f" {yr:^{YW-2}} |"
    hdr += f" {'4-Yr Avg':^12} |"
    hdr += f" {delta_lbl:^10} |"
    print(hdr)
    print(SEP)

    for sig in sigs_disp:
        if sig == "Sell High":
            print(SEP)
        row = f"| {sig:<12} |"
        for yr in YEARS:
            n, c, acc, _ = stats[sig][yr]
            if n == 0:
                row += f" {'n/a':^{YW-2}} |"
            else:
                cell = f"{acc:.0%} (n={n})"
                row += f" {cell:^{YW-2}} |"
        n4, c4, acc4, avg_d4 = agg[sig]
        if n4 > 0:
            row += f" {acc4:.1%} (n={n4}) |"
            row += f" {avg_d4:>+.3f}     |"
        else:
            row += f" {'n/a':^12} | {'n/a':^10} |"
        print(row)

    print(SEP)
    sig = "Overall"
    row = f"| {'Overall':<12} |"
    for yr in YEARS:
        n, c, acc, _ = stats[sig][yr]
        cell = f"{acc:.0%} (n={n})" if n > 0 else "n/a"
        row += f" {cell:^{YW-2}} |"
    n4, c4, acc4, avg_d4 = agg[sig]
    row += f" {acc4:.1%} (n={n4}) |"
    row += f" {avg_d4:>+.3f}     |"
    print(row)

    # vs Do Nothing
    do_nothing = RTM_BASELINE
    n_all = agg["Overall"][0]
    dn_row = f"| {'vs Do Nothing':<12} |"
    for yr in YEARS:
        n, c, acc, _ = stats["Overall"][yr]
        delta_pp = (acc - do_nothing) * 100 if n > 0 else float("nan")
        cell = f"{delta_pp:>+.1f}pp" if not math.isnan(delta_pp) else "n/a"
        dn_row += f" {cell:^{YW-2}} |"
    delta_4yr = (acc4 - do_nothing) * 100
    dn_row += f" {delta_4yr:>+.1f}pp (RTM={do_nothing:.1%}) |"
    dn_row += f" {'':^10} |"
    print(dn_row)
    print(SEP)


# ══════════════════════════════════════════════════════════════════════════════
# DIAGNOSTIC FLAGS
# ══════════════════════════════════════════════════════════════════════════════

def run_diagnostics(h_df: pd.DataFrame, p_df: pd.DataFrame) -> None:
    print("\n" + "═"*72)
    print("DIAGNOSTIC FLAGS")
    print("═"*72)

    # ── Hitter: large wrong calls ─────────────────────────────────────────
    print("\nHITTER: Wrong calls with |wOBA change| > 0.030")
    h_eval  = h_df[h_df["in_eval"] == True].copy()
    h_wrong = h_eval[h_eval["correct"] == False].copy()
    h_wrong["abs_change"] = h_wrong["actual_woba_change"].abs()
    h_large = h_wrong[h_wrong["abs_change"] > 0.030].sort_values("abs_change", ascending=False)
    if h_large.empty:
        print("  None — model was never wrong by > 0.030 wOBA")
    else:
        print(f"  {len(h_large)} large misses:")
        for _, r in h_large.head(15).iterrows():
            print(f"    {r['player_name']:<22} {r['year']}  "
                  f"{r['signal']:<12}  predicted={r['predicted_direction']:<9}  "
                  f"wOBA_chg={r['actual_woba_change']:>+.3f}  "
                  f"luck={r['luck_score']:>+.3f}")

    # ── Pitcher: large wrong calls ────────────────────────────────────────
    print(f"\nPITCHER: Wrong calls with |ERA change| > 1.5")
    p_eval  = p_df[p_df["in_eval"] == True].copy()
    p_wrong = p_eval[p_eval["correct"] == False].copy()
    p_wrong["abs_change"] = p_wrong["actual_era_change"].abs()
    p_large = p_wrong[p_wrong["abs_change"] > 1.5].sort_values("abs_change", ascending=False)
    if p_large.empty:
        print("  None")
    else:
        print(f"  {len(p_large)} large misses:")
        for _, r in p_large.head(15).iterrows():
            print(f"    {r['player_name']:<22} {r['year']}  "
                  f"{r['signal']:<12}  predicted={r['predicted_direction']:<9}  "
                  f"ERA_chg={r['actual_era_change']:>+.2f}  "
                  f"luck={r['luck_score']:>+.3f}")

    # ── Tiers below 70% ──────────────────────────────────────────────────
    print("\nWEAK TIERS (accuracy < 70% in any year):")
    found_any = False
    for df, kind, change_col in [(h_eval, "HITTER", "actual_woba_change"),
                                  (p_eval, "PITCHER", "actual_era_change")]:
        for sig in ["Buy Low","Slight Buy","Sell High","Slight Sell"]:
            for yr in YEARS:
                grp = df[(df["year"]==yr) & (df["signal"]==sig)]
                n = len(grp)
                if n < 3:
                    continue
                acc = grp["correct"].mean()
                if acc < 0.70:
                    found_any = True
                    avg_d = grp[change_col].mean()
                    print(f"  ⚠  {kind:<8} {sig:<12} {yr}  n={n:>3}  acc={acc:.1%}  "
                          f"avg_Δ={avg_d:>+.3f}  ← BELOW 70%")
    if not found_any:
        print("  None — all tiers ≥ 70% in every year")

    # ── Pitcher Slight Buy deep dive ─────────────────────────────────────
    print("\nPITCHER Slight Buy deep dive (flagged as weak tier):")
    sb = p_eval[p_eval["signal"] == "Slight Buy"].copy()
    for yr in YEARS:
        g = sb[sb["year"]==yr]
        n = len(g)
        if n == 0:
            print(f"  {yr}: no players"); continue
        c = int(g["correct"].sum())
        acc = c/n
        avg_chg = g["actual_era_change"].mean()
        flag = "  ⚠ WEAK" if acc < 0.70 else ""
        print(f"  {yr}: n={n:>2}  correct={c:>2}  acc={acc:.1%}  avg ERA chg={avg_chg:>+.2f}{flag}")
    sb_all = sb.copy()
    if len(sb_all) > 0:
        print(f"  4yr: n={len(sb_all)}  correct={int(sb_all['correct'].sum())}  "
              f"acc={sb_all['correct'].mean():.1%}  "
              f"avg ERA chg={sb_all['actual_era_change'].mean():>+.2f}")
        print(f"\n  Slight Buy misses (wrong direction):")
        sb_wrong = sb_all[sb_all["correct"]==False].sort_values("actual_era_change", ascending=False)
        for _, r in sb_wrong.head(10).iterrows():
            print(f"    {r['player_name']:<22} {r['year']}  "
                  f"ERA={r['era_actual']:.2f}  FIP={r['fip_actual']:.2f}  "
                  f"ERA_chg={r['actual_era_change']:>+.2f}  luck={r['luck_score']:>+.3f}")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 72)
    print("FRESH BACKTEST — HITTER + PITCHER MODELS  (2022–2025)")
    print("Signal scoring: v7 logic | Data: Statcast cache | Mode: READ-ONLY")
    print("=" * 72)

    # ── Shared data ───────────────────────────────────────────────────────
    print("\nLoading shared data...")
    career_path  = BASE_DIR / "data" / "career_stats.json"
    seasonal_path= BASE_DIR / "data" / "seasonal_patterns.json"
    babip_h_path = BASE_DIR / "data" / "hitter_career_babip.json"
    babip_p_path = BASE_DIR / "data" / "pitcher_career_babip.json"
    stuff_path   = BASE_DIR / "data" / "pitcher_stuff_plus_2025.csv"
    oaa_path     = BASE_DIR / "data" / "team_oaa_2025.csv"

    career_stats = {}
    if career_path.exists():
        career_stats = {int(k): v for k, v in json.loads(career_path.read_text()).items()}

    patterns = {}
    if seasonal_path.exists():
        rec = json.loads(seasonal_path.read_text())
        patterns = {int(r["player_id"]): r for r in rec} if isinstance(rec, list) else {}

    career_babip_h = {}
    if babip_h_path.exists():
        for pid, rec in json.loads(babip_h_path.read_text()).items():
            cb = rec.get("career_babip")
            if cb is not None:
                career_babip_h[int(pid)] = float(cb)

    career_babip_p = {}
    if babip_p_path.exists():
        for pid, rec in json.loads(babip_p_path.read_text()).items():
            cb = rec.get("career_babip_allowed")
            if cb is not None:
                career_babip_p[int(pid)] = float(cb)

    stuff_plus = {}
    if stuff_path.exists():
        sdf = pd.read_csv(stuff_path)
        id_c  = "pitcher_id" if "pitcher_id" in sdf.columns else sdf.columns[0]
        val_c = "stuff_plus_avg" if "stuff_plus_avg" in sdf.columns else sdf.columns[2]
        stuff_plus = dict(zip(sdf[id_c].astype(int), sdf[val_c].astype(float)))

    oaa_adj = {}
    if oaa_path.exists():
        od = pd.read_csv(oaa_path, usecols=["team_abbr","babip_adj"])
        oaa_adj = dict(zip(od["team_abbr"], od["babip_adj"]))

    print(f"  career={len(career_stats):,}  patterns={len(patterns):,}  "
          f"babip_h={len(career_babip_h):,}  babip_p={len(career_babip_p):,}  "
          f"stuff+={len(stuff_plus):,}")

    print("\nBuilding name lookups...")
    pitcher_names = build_pitcher_name_lookup()
    hitter_names  = build_hitter_name_lookup()
    print(f"  Pitchers: {len(pitcher_names)}  |  Hitters: {len(hitter_names)}")

    # ══ HITTER BACKTEST ═══════════════════════════════════════════════════
    print("\n" + "═"*72)
    print("HITTER BACKTEST  (2022–2025)")
    print("═"*72)

    oaa_cache = CACHE_DIR / "opponent_oaa_april_2024.csv"
    opp_oaa_2024 = {}
    if oaa_cache.exists():
        oc = pd.read_csv(oaa_cache)
        opp_oaa_2024 = dict(zip(oc.iloc[:,0].astype(int), oc.iloc[:,1].astype(float)))

    h_frames = []
    for yr in YEARS:
        opp = opp_oaa_2024 if yr == 2024 else {}   # OAA cache only for 2024
        frame = run_hitter_year(yr, career_stats, patterns, career_babip_h, opp, hitter_names)
        if frame is not None:
            h_frames.append(frame)

    if not h_frames:
        print("ERROR: no hitter data"); return

    h_df = pd.concat(h_frames, ignore_index=True)

    print(f"\n{'='*72}")
    print(f"HITTER ACCURACY TABLE  ({len(h_df)} total player-seasons, "
          f"{int(h_df['in_eval'].sum())} in eval)")
    print(f"{'='*72}")
    accuracy_table(h_df, "hitter", "actual_woba_change")

    # ══ PITCHER BACKTEST ══════════════════════════════════════════════════
    print("\n" + "═"*72)
    print("PITCHER BACKTEST  (2022–2025)")
    print("═"*72)

    p_frames = []
    for yr in YEARS:
        frame = run_pitcher_year(yr, stuff_plus, career_babip_p, pitcher_names)
        if frame is not None:
            p_frames.append(frame)

    if not p_frames:
        print("ERROR: no pitcher data"); return

    p_df = pd.concat(p_frames, ignore_index=True)

    print(f"\n{'='*72}")
    print(f"PITCHER ACCURACY TABLE  ({len(p_df)} total player-seasons, "
          f"{int(p_df['in_eval'].sum())} in eval)")
    print(f"{'='*72}")
    accuracy_table(p_df, "pitcher", "actual_era_change")

    # ══ DIAGNOSTICS ═══════════════════════════════════════════════════════
    run_diagnostics(h_df, p_df)

    # ══ SAVE CSVs ════════════════════════════════════════════════════════
    print("\n" + "═"*72)
    print("SAVING ROW-LEVEL AUDIT FILES")
    print("═"*72)

    h_out_cols = ["player_name","mlbam_id","year","signal","luck_score",
                  "woba_actual","xwoba_actual","predicted_direction",
                  "actual_woba_change","correct"]
    p_out_cols = ["player_name","mlbam_id","year","signal","luck_score",
                  "era_actual","fip_actual","xera_actual","predicted_direction",
                  "actual_era_change","correct"]

    # Export only eval-set rows for the required columns
    h_eval = h_df[h_df["in_eval"] == True][h_out_cols].copy()
    p_eval = p_df[p_df["in_eval"] == True][p_out_cols].copy()

    h_path = DATA_DIR / "backtest_audit_hitters.csv"
    p_path = DATA_DIR / "backtest_audit_pitchers.csv"
    h_eval.to_csv(h_path, index=False)
    p_eval.to_csv(p_path, index=False)
    print(f"\n  {h_path.name}: {len(h_eval)} rows (eval set only)")
    print(f"  {p_path.name}: {len(p_eval)} rows (eval set only)")

    # ══ HEADLINE NUMBERS ══════════════════════════════════════════════════
    print("\n" + "═"*72)
    print("HEADLINE NUMBERS  (authoritative, fresh computation)")
    print("═"*72)

    def _nums(df, change_col):
        ev = df[df["in_eval"]==True].copy()
        out = {}
        for sig in ["Buy Low","Slight Buy","Sell High","Slight Sell"]:
            g = ev[ev["signal"]==sig]
            n = len(g); c = int(g["correct"].sum())
            out[sig] = (n, c/n if n>0 else float("nan"))
        g = ev; n = len(g); c = int(g["correct"].sum())
        out["Overall"] = (n, c/n if n>0 else float("nan"))
        return out

    h_nums = _nums(h_df, "actual_woba_change")
    p_nums = _nums(p_df, "actual_era_change")
    rtm    = RTM_BASELINE

    print(f"\n  MODEL          SELL HIGH    BUY LOW     OVERALL    vs Do-Nothing")
    print(f"  {'-'*62}")
    h_sh = h_nums["Sell High"]
    h_bl = h_nums["Buy Low"]
    h_ov = h_nums["Overall"]
    print(f"  Hitters        {h_sh[1]:.1%} (n={h_sh[0]:>2})  "
          f"{h_bl[1]:.1%} (n={h_bl[0]:>2})  "
          f"{h_ov[1]:.1%} (n={h_ov[0]:>3})  "
          f"+{(h_ov[1]-rtm)*100:.1f}pp")
    p_sh = p_nums["Sell High"]
    p_bl = p_nums["Buy Low"]
    p_ov = p_nums["Overall"]
    print(f"  Pitchers       {p_sh[1]:.1%} (n={p_sh[0]:>2})  "
          f"{p_bl[1]:.1%} (n={p_bl[0]:>2})  "
          f"{p_ov[1]:.1%} (n={p_ov[0]:>3})  "
          f"+{(p_ov[1]-rtm)*100:.1f}pp")

    print(f"\n  Hitter Slight Buy:  {h_nums['Slight Buy'][1]:.1%} (n={h_nums['Slight Buy'][0]})")
    print(f"  Hitter Slight Sell: {h_nums['Slight Sell'][1]:.1%} (n={h_nums['Slight Sell'][0]})")
    print(f"  Pitcher Slight Buy: {p_nums['Slight Buy'][1]:.1%} (n={p_nums['Slight Buy'][0]})")
    print(f"  Pitcher Slight Sell:{p_nums['Slight Sell'][1]:.1%} (n={p_nums['Slight Sell'][0]})")

    print(f"\n  Row counts vs prior v7 backtest:")
    print(f"  Hitters: {int(h_df['in_eval'].sum())} eval player-seasons  (prior: 305)")
    print(f"  Pitchers: {int(p_df['in_eval'].sum())} eval player-seasons  (prior: 284)")
    print()


if __name__ == "__main__":
    main()
