"""
build_backtest_audit.py
=======================
Re-runs the v7 backtest logic (read-only — no scoring changes) and exports
row-level prediction+outcome data for every player-season.

Outputs:
  data/backtest_audit_hitters.csv   — 4yr hitter player-seasons
  data/backtest_audit_pitchers.csv  — 4yr pitcher player-seasons

Columns (hitters):
  player_name, mlbam_id, year, signal, woba_actual, xwoba_actual,
  luck_score, predicted_direction, actual_woba_change, correct,
  tier_accuracy_contribution

Columns (pitchers):
  player_name, mlbam_id, year, signal, era_actual, fip_actual,
  luck_score, predicted_direction, actual_era_change, correct,
  tier_accuracy_contribution

Validation: recomputes accuracy from row-level data and compares to published.
"""

import io
import json
import math
import os
import sys
import numpy as np
import pandas as pd
from pathlib import Path

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

# ── Constants (copied verbatim from backtest_multi_year_v7.py) ────────────────
MIN_APRIL_PA       = 80
MIN_OUTCOME_PA     = 100
FLAT_THRESHOLD     = 0.015
LEAGUE_AVG_BABIP   = 0.300
EV_THRESHOLD       = 1.0
SELL_HIGH_THRESH   = -0.065
SLIGHT_SELL_THRESH = -0.040
RTM_BASELINE       = 0.682

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

MIN_START_IP_P     = 2.0
MIN_APRIL_IP_P     = 15.0
MIN_OUTCOME_IP_P   = 30.0
ERA_FLAT_P         = 0.40
FIP_CONST          = 3.10
LEAGUE_AVG_ERA     = 4.20
LEAGUE_AVG_BABIP_P = 0.300
P_BUY_LOW_THRESH   =  1.20
P_SLIGHT_BUY_THRESH=  0.60
P_SELL_HIGH_THRESH = -1.20
P_SLIGHT_SELL_THRESH= -0.60
DISASTER_ERA_P     = 10.0
DISASTER_RATE_P    = 0.30
START_VAR_P        = 4.0
VOL_DAMP           = 0.90

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

SIGNAL_DISPLAY = {
    'BUY_LOW':    'Buy Low',
    'SLIGHT_BUY': 'Slight Buy',
    'NEUTRAL':    'Neutral',
    'SLIGHT_SELL':'Slight Sell',
    'SELL_HIGH':  'Sell High',
}

# ── Name lookup ───────────────────────────────────────────────────────────────

def build_name_lookup(all_ids: set[int]) -> dict[int, str]:
    """Map MLBAM ID → player name using pybaseball reverse lookup."""
    try:
        from pybaseball import playerid_reverse_lookup
        ids_list = sorted(all_ids)
        print(f"  Reverse-looking up {len(ids_list)} player IDs ...")
        lu = playerid_reverse_lookup(ids_list, key_type="mlbam")
        if lu is not None and not lu.empty:
            result = {}
            for _, row in lu.iterrows():
                mid = int(row.get("key_mlbam", 0) or 0)
                fn  = str(row.get("name_first", "") or "").strip().title()
                ln  = str(row.get("name_last",  "") or "").strip().title()
                if mid > 0:
                    result[mid] = f"{fn} {ln}".strip() if fn else ln
            print(f"  Resolved {len(result)} names")
            return result
    except Exception as ex:
        print(f"  WARNING: playerid_reverse_lookup failed: {ex}")
    return {}


def pitcher_name_from_parquets(years=(2022, 2023, 2024, 2025)) -> dict[int, str]:
    """Extract pitcher MLBAM→name from the april parquets (player_name is pitcher)."""
    result = {}
    for yr in years:
        p = CACHE_DIR / f"pitcher_statcast_april_{yr}.parquet"
        if not p.exists():
            continue
        df = pd.read_parquet(p, columns=["pitcher", "player_name"])
        df = df[df["player_name"].notna() & df["pitcher"].notna()].copy()
        df["pitcher"] = df["pitcher"].astype(int)
        for pid, name in df.groupby("pitcher")["player_name"].first().items():
            # Format is "LastName, FirstName" → "FirstName LastName"
            parts = str(name).split(", ", 1)
            result[int(pid)] = (f"{parts[1]} {parts[0]}".strip()
                                if len(parts) == 2 else parts[0])
    return result


# ── Hitter helpers (verbatim from v7, returns row-level eval_df) ───────────────

def _babip_age_mult(age: int) -> float:
    if age >= 39: return 0.88
    if age >= 37: return 0.91
    if age >= 35: return 0.94
    if age >= 32: return 0.97
    return 1.0


def classify_h(score: float) -> str:
    if score >= 0.040:              return "BUY_LOW"
    if score >= 0.020:              return "SLIGHT_BUY"
    if score <= SELL_HIGH_THRESH:   return "SELL_HIGH"
    if score <= SLIGHT_SELL_THRESH: return "SLIGHT_SELL"
    return "NEUTRAL"


def run_year_h_rows(year, career_stats, patterns, career_babip, opp_oaa,
                    name_lookup: dict) -> pd.DataFrame | None:
    """
    Identical logic to backtest_multi_year_v7.run_year_h(), but returns a
    DataFrame of every player-season with signal + outcome columns.
    """
    april_path   = CACHE_DIR / f"v4_april_{year}.csv"
    outcome_path = CACHE_DIR / f"statcast_{year}_may_july.csv"
    team_path    = CACHE_DIR / f"team_map_{year}.csv"
    if not april_path.exists() or not outcome_path.exists():
        print(f"  {year}: SKIPPED — missing cache")
        return None

    april   = pd.read_csv(april_path)
    outcome = pd.read_csv(outcome_path)
    if team_path.exists():
        team_map = pd.read_csv(team_path)
        april = april.merge(team_map, on="batter", how="left")
    april["park_factor"] = (april["team"].map(PARK_FACTORS_H).fillna(1.0)
                            if "team" in april.columns else 1.0)

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

    if opp_oaa:
        signals["oaa_babip_adj"] = signals["batter"].apply(lambda b: opp_oaa.get(int(b), 0.0))
        signals["babip_expected"] = (signals["babip_expected"] + signals["oaa_babip_adj"]).round(4)
    else:
        signals["oaa_babip_adj"] = 0.0

    if signals["gb_rate"].notna().any():
        gb_high = signals["gb_rate"] > 0.50
        gb_low  = signals["gb_rate"] < 0.35
        signals.loc[gb_high, "babip_expected"] -= 0.010
        signals.loc[gb_low,  "babip_expected"] += 0.008

    signals["babip_luck"] = signals["babip_expected"] - signals["babip"]
    signals = signals[signals["april_pa"] >= MIN_APRIL_PA].copy()
    signals["luck_score"] = (
        signals["xwoba_gap"]  * 0.60 +
        signals["babip_luck"] * 0.40
    ).round(4)

    if signals["sweet_spot_rate"].notna().any():
        buy     = signals["luck_score"] > 0
        high_ss = buy & (signals["sweet_spot_rate"] > 0.12)
        low_ss  = buy & (signals["sweet_spot_rate"] < 0.06)
        signals.loc[high_ss, "luck_score"] = (signals.loc[high_ss,"luck_score"] * 1.05).round(4)
        signals.loc[low_ss,  "luck_score"] = (signals.loc[low_ss, "luck_score"] * 0.95).round(4)

    if signals["avg_exit_velocity"].notna().any():
        for idx, row in signals.iterrows():
            if row["luck_score"] <= 0:
                continue
            career_ev = (career_stats.get(int(row["batter"])) or {}).get("avg_exit_velocity")
            if career_ev is None or pd.isna(row["avg_exit_velocity"]):
                continue
            ev_below = (row["avg_exit_velocity"] - career_ev) < -EV_THRESHOLD
            ss       = row["sweet_spot_rate"]
            low_ss_ev = pd.notna(ss) and ss < 0.08
            if ev_below and low_ss_ev:
                signals.at[idx, "luck_score"] = round(row["luck_score"] * 0.85, 4)
            elif ev_below or low_ss_ev:
                signals.at[idx, "luck_score"] = round(row["luck_score"] * 0.93, 4)

    if signals["bb_rate"].notna().any() and signals["k_rate"].notna().any():
        buy_mask   = signals["luck_score"] > 0
        elite_disc = buy_mask & (signals["bb_rate"] > 0.10) & (signals["k_rate"] < 0.18)
        poor_disc  = buy_mask & ((signals["bb_rate"] < 0.06) | (signals["k_rate"] > 0.28))
        signals.loc[elite_disc, "luck_score"] = (signals.loc[elite_disc,"luck_score"] * 1.08).round(4)
        signals.loc[poor_disc,  "luck_score"] = (signals.loc[poor_disc, "luck_score"] * 0.88).round(4)

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

    signals["signal"] = signals["luck_score"].apply(classify_h)

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

    # Keep ALL players in the audit (including NEUTRAL and FLAT); mark eval-only for accuracy
    merged["predicted_direction"] = merged["signal"].map(SIGNAL_MAP_H).fillna("")
    merged["in_eval_set"] = (
        merged["signal"].isin(SIGNAL_MAP_H) & (merged["outcome"] != "FLAT")
    )
    eval_df = merged[merged["in_eval_set"]].copy()
    eval_df["correct"] = eval_df.apply(
        lambda r: r["outcome"] == SIGNAL_MAP_H[r["signal"]], axis=1)

    # Merge correct back onto merged for audit rows
    merged = merged.merge(
        eval_df[["batter","correct"]].rename(columns={"batter":"batter"}),
        on="batter", how="left"
    )

    # tier_accuracy_contribution: correct/n_tier (0 for non-eval rows)
    tier_sizes = eval_df.groupby("signal").size().to_dict()
    def _tier_contrib(row):
        if not row.get("in_eval_set", False):
            return 0.0
        n = tier_sizes.get(row["signal"], 0)
        correct_val = row.get("correct", False)
        if isinstance(correct_val, float) and math.isnan(correct_val):
            return 0.0
        return round(1.0 / n, 6) if (n > 0 and bool(correct_val)) else 0.0

    merged["tier_accuracy_contribution"] = merged.apply(_tier_contrib, axis=1)

    # Build final audit rows
    rows = []
    for _, r in merged.iterrows():
        bid = int(r["batter"])
        rows.append({
            "player_name":              name_lookup.get(bid, f"ID_{bid}"),
            "mlbam_id":                 bid,
            "year":                     year,
            "signal":                   SIGNAL_DISPLAY.get(r["signal"], r["signal"]),
            "woba_actual":              round(float(r["april_actual_woba"]), 4),
            "xwoba_actual":             round(float(r["april_xwoba"]), 4) if pd.notna(r["april_xwoba"]) else None,
            "luck_score":               round(float(r["luck_score"]), 4),
            "predicted_direction":      r["predicted_direction"],
            "actual_woba_change":       round(float(r["woba_change"]), 4),
            "outcome":                  r["outcome"],
            "in_eval_set":              bool(r["in_eval_set"]),
            "correct":                  bool(r["correct"]) if pd.notna(r.get("correct")) else None,
            "tier_accuracy_contribution": r["tier_accuracy_contribution"],
        })

    result = pd.DataFrame(rows)
    print(f"  {year}: {len(merged)} total players, "
          f"{len(eval_df)} in eval, "
          f"{int(eval_df['correct'].sum())} correct "
          f"({eval_df['correct'].mean():.1%})")
    return result


# ── Pitcher helpers ───────────────────────────────────────────────────────────

def _prep_pitcher_sc(sc: pd.DataFrame) -> pd.DataFrame:
    sc = sc.copy()
    sc["pitcher"] = pd.to_numeric(sc["pitcher"], errors="coerce")
    sc = sc[sc["pitcher"].notna()].copy()
    sc["pitcher"] = sc["pitcher"].astype(int)
    ev_mask = sc["events"].notna() & (sc["events"] != "")
    sc["is_out"] = (sc["events"].isin(P_OUT_EVENTS) & ev_mask).astype(int)
    sc["is_dp"]  = (sc["events"].isin({"grounded_into_double_play","double_play",
                                         "strikeout_double_play"}) & ev_mask).astype(int)
    return sc


def compute_per_start_pitcher(sc: pd.DataFrame) -> pd.DataFrame:
    if "game_pk" not in sc.columns:
        return pd.DataFrame(columns=["pitcher","game_pk","start_ip","start_ra",
                                     "start_era","qualifying","is_qs","is_disaster"])
    sc = _prep_pitcher_sc(sc)
    ev = sc[sc["events"].notna() & (sc["events"] != "")].copy()

    outs_s = ev.groupby(["pitcher","game_pk"]).agg(
        outs=("is_out","sum"), dp_outs=("is_dp","sum")).reset_index()
    outs_s["start_ip"] = (outs_s["outs"] + outs_s["dp_outs"]) / 3.0

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
    results = []
    for pid, grp in start_stats.groupby("pitcher"):
        total      = len(grp)
        disaster_n = int(grp["is_disaster"].sum())
        qs_n       = int(grp["is_qs"].sum())
        d_rate     = disaster_n / total if total > 0 else 0.0
        qual_eras  = grp.loc[grp["qualifying"],"start_era"].dropna()
        start_var  = float(qual_eras.std()) if len(qual_eras) >= 2 else float("nan")
        flagged    = (d_rate > DISASTER_RATE_P
                      or (not math.isnan(start_var) and start_var > START_VAR_P))
        results.append({
            "pitcher":        int(pid),
            "total_starts":   total,
            "disaster_rate":  round(d_rate, 3),
            "qs_rate":        round(qs_n / total, 3) if total > 0 else 0.0,
            "start_variance": round(start_var, 2) if not math.isnan(start_var) else None,
            "volatility_flag": flagged,
        })
    return pd.DataFrame(results)


def compute_pitcher_stats_v6(sc: pd.DataFrame, start_stats: pd.DataFrame) -> pd.DataFrame:
    sc = _prep_pitcher_sc(sc)
    ev = sc[sc["events"].notna() & (sc["events"] != "")].copy()

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

    if "post_bat_score" in ev_qual.columns and "bat_score" in ev_qual.columns:
        re = ev_qual[ev_qual["post_bat_score"].notna() & ev_qual["bat_score"].notna()].copy()
        re["runs_scored"] = (re["post_bat_score"] - re["bat_score"]).clip(lower=0)
        ra_qual = re.groupby("pitcher")["runs_scored"].sum()
    else:
        ra_qual = pd.Series(dtype=float)

    era_qual = (ra_qual / (ip_qual / 9)).where(ip_qual > 0).round(2)
    if "post_bat_score" in ev.columns and "bat_score" in ev.columns:
        re_all = ev[ev["post_bat_score"].notna() & ev["bat_score"].notna()].copy()
        re_all["runs_scored"] = (re_all["post_bat_score"] - re_all["bat_score"]).clip(lower=0)
        ra_all = re_all.groupby("pitcher")["runs_scored"].sum()
        era_all = (ra_all / (ip_all / 9)).where(ip_all > 0).round(2)
    else:
        era_all = pd.Series(dtype=float)

    era_final = era_qual.combine_first(era_all)

    ev_qual["is_k"]  = ev_qual["events"].isin({"strikeout","strikeout_double_play"}).astype(int)
    ev_qual["is_bb"] = ev_qual["events"].isin({"walk","intent_walk"}).astype(int)
    ev_qual["is_hr"] = (ev_qual["events"] == "home_run").astype(int)
    fip_agg = ev_qual.groupby("pitcher").agg(
        k=("is_k","sum"), bb=("is_bb","sum"), hr=("is_hr","sum")).reset_index()
    fip_agg = fip_agg.set_index("pitcher")
    fip_series = ((13 * fip_agg["hr"] + 3 * fip_agg["bb"] - 2 * fip_agg["k"]) / ip_qual + FIP_CONST
                  ).where(ip_qual > 0).round(2)

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

    pa_agg = ev.groupby("pitcher").size().rename("pa")

    team_s = pd.Series(dtype=str, name="team")
    if "home_team" in sc.columns and "away_team" in sc.columns and "inning_topbot" in sc.columns:
        sc["p_team"] = sc.apply(
            lambda r: r["away_team"] if r["inning_topbot"]=="Top" else r["home_team"], axis=1)
        team_s = sc.groupby("pitcher")["p_team"].agg(lambda x: x.mode().iloc[0])

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
    p = BASE_DIR / "data" / "pitcher_stuff_plus_2025.csv"
    if not p.exists():
        return {}
    df = pd.read_csv(p)
    id_col  = "pitcher_id" if "pitcher_id"  in df.columns else df.columns[0]
    val_col = "stuff_plus_avg" if "stuff_plus_avg" in df.columns else df.columns[2]
    return dict(zip(df[id_col].astype(int), df[val_col].astype(float)))


def load_career_babip_p() -> dict:
    p = BASE_DIR / "data" / "pitcher_career_babip.json"
    if not p.exists():
        return {}
    with open(p) as f:
        raw = json.load(f)
    return {int(k): float(v["career_babip_allowed"])
            for k, v in raw.items()
            if v.get("career_babip_allowed") is not None}


def run_year_p_rows(year: int, stuff_plus: dict, career_babip: dict,
                    name_lookup: dict) -> pd.DataFrame | None:
    """
    v7 pitcher backtest for a single year, returns row-level DataFrame.
    Applies: 2 IP per-start min, volatility dampening, FIP- override.
    """
    april_path   = CACHE_DIR / f"pitcher_statcast_april_{year}.parquet"
    outcome_path = CACHE_DIR / f"pitcher_statcast_mayjuly_{year}.parquet"
    if not april_path.exists() or not outcome_path.exists():
        print(f"  {year}: SKIPPED — missing pitcher cache")
        return None

    april_sc   = pd.read_parquet(april_path)
    outcome_sc = pd.read_parquet(outcome_path)
    if april_sc.empty or outcome_sc.empty:
        print(f"  {year}: SKIPPED — empty data")
        return None

    april_starts   = compute_per_start_pitcher(april_sc)
    outcome_starts = compute_per_start_pitcher(outcome_sc)

    apr_stats = compute_pitcher_stats_v6(april_sc,   april_starts)
    out_stats = compute_pitcher_stats_v6(outcome_sc, outcome_starts)

    apr_stats = apr_stats[apr_stats["ip"] >= MIN_APRIL_IP_P].copy()
    out_stats = out_stats[out_stats["ip"] >= MIN_OUTCOME_IP_P].copy()

    sig = apr_stats.copy()
    sig["park_factor"]   = sig["team"].map(PARK_FACTORS_H).fillna(1.0) if "team" in sig.columns else 1.0
    sig["career_babip"]  = sig["pitcher"].map(career_babip).fillna(LEAGUE_AVG_BABIP_P)
    sig["babip_expected"]= sig["career_babip"] * sig["park_factor"]
    sig["babip_luck"]    = sig["babip_expected"] - sig["babip"]
    sig["era_fip_gap"]   = sig["era"] - sig["fip"]

    sig["stuff_plus"]     = sig["pitcher"].map(stuff_plus)
    sig["luck_score_raw"] = (
        sig["era_fip_gap"]  * 0.70 +
        sig["babip_luck"]   * 0.30 * 9
    ).round(3)

    # FIP- override (v7 addition)
    qualified_fip = sig[sig["ip"] >= 15]["fip"].dropna()
    lg_fip = qualified_fip.mean() if len(qualified_fip) > 0 else sig["fip"].dropna().mean()
    sig["fip_minus"] = (sig["fip"] / lg_fip * (1.0 / sig["park_factor"]) * 100).where(
        sig["fip"].notna(), other=float("nan")
    )

    def _apply_stuff(row):
        score = row["luck_score_raw"]
        sp    = row["stuff_plus"]
        if pd.isna(sp):
            return score
        fip_m    = row["fip_minus"]
        fip_m_ok = not (isinstance(fip_m, float) and math.isnan(fip_m))
        is_elite_ovr = fip_m_ok and fip_m < 85  and sp < 95
        is_poor_ovr  = fip_m_ok and fip_m > 115 and sp > 105
        if is_elite_ovr:
            if score < 0: return round(score * 0.85, 3)
            return score
        if is_poor_ovr:
            if score > 0: return score
            return round(score * 1.15, 3)
        if sp >= 115 and score > 0: return round(score * 1.15, 3)
        if sp < 90   and score < 0: return round(score * 1.15, 3)
        if sp >= 115 and score < 0: return round(score * 0.85, 3)
        if sp < 90   and score > 0: return round(score * 0.85, 3)
        return score

    sig["luck_score"] = sig.apply(_apply_stuff, axis=1)

    # Volatility dampening
    if not april_starts.empty:
        vol_df = compute_volatility_p(april_starts)
        vol_df["pitcher"] = vol_df["pitcher"].astype(int)
        sig = sig.merge(vol_df[["pitcher","disaster_rate","start_variance","volatility_flag"]],
                        on="pitcher", how="left")
        sig["volatility_flag"] = sig["volatility_flag"].fillna(False)
        buy_vol = sig["volatility_flag"] & (sig["luck_score"] > 0)
        sig.loc[buy_vol, "luck_score"] = (sig.loc[buy_vol, "luck_score"] * VOL_DAMP).round(3)
    else:
        sig["volatility_flag"] = False

    sig["signal"] = sig["era_fip_gap"].apply(classify_p)

    merged = sig.merge(
        out_stats[["pitcher","era","fip","ip"]].rename(columns={
            "era":"outcome_era","fip":"outcome_fip","ip":"outcome_ip"}),
        on="pitcher", how="inner"
    )
    merged["era_change"] = merged["outcome_era"] - merged["era"]
    merged["outcome"] = np.where(
        merged["era_change"] <= -ERA_FLAT_P, "IMPROVED",
        np.where(merged["era_change"] >= ERA_FLAT_P, "DECLINED", "FLAT")
    )

    merged["predicted_direction"] = merged["signal"].map(SIGNAL_MAP_P).fillna("")
    merged["in_eval_set"] = (
        merged["signal"].isin(SIGNAL_MAP_P) & (merged["outcome"] != "FLAT")
    )
    eval_df = merged[merged["in_eval_set"]].copy()
    eval_df["correct"] = eval_df.apply(
        lambda r: r["outcome"] == SIGNAL_MAP_P[r["signal"]], axis=1)

    merged = merged.merge(
        eval_df[["pitcher","correct"]],
        on="pitcher", how="left"
    )

    tier_sizes = eval_df.groupby("signal").size().to_dict()
    def _tier_contrib_p(row):
        if not row.get("in_eval_set", False):
            return 0.0
        n = tier_sizes.get(row["signal"], 0)
        correct_val = row.get("correct", False)
        if isinstance(correct_val, float) and math.isnan(correct_val):
            return 0.0
        return round(1.0 / n, 6) if (n > 0 and bool(correct_val)) else 0.0

    merged["tier_accuracy_contribution"] = merged.apply(_tier_contrib_p, axis=1)

    rows = []
    for _, r in merged.iterrows():
        pid = int(r["pitcher"])
        # Prefer name from statcast data; fall back to lookup dict
        raw_name = r.get("name", "")
        if raw_name and pd.notna(raw_name):
            parts = str(raw_name).split(", ", 1)
            disp_name = f"{parts[1]} {parts[0]}".strip() if len(parts) == 2 else parts[0]
        else:
            disp_name = name_lookup.get(pid, f"ID_{pid}")

        rows.append({
            "player_name":              disp_name,
            "mlbam_id":                 pid,
            "year":                     year,
            "signal":                   SIGNAL_DISPLAY.get(r["signal"], r["signal"]),
            "era_actual":               round(float(r["era"]), 2) if pd.notna(r["era"]) else None,
            "fip_actual":               round(float(r["fip"]), 2) if pd.notna(r["fip"]) else None,
            "luck_score":               round(float(r["luck_score"]), 3),
            "predicted_direction":      r["predicted_direction"],
            "actual_era_change":        round(float(r["era_change"]), 2),
            "outcome":                  r["outcome"],
            "in_eval_set":              bool(r["in_eval_set"]),
            "correct":                  bool(r["correct"]) if pd.notna(r.get("correct")) else None,
            "tier_accuracy_contribution": r["tier_accuracy_contribution"],
        })

    result = pd.DataFrame(rows)
    print(f"  {year}: {len(merged)} pitchers, "
          f"{len(eval_df)} in eval, "
          f"{int(eval_df['correct'].sum())} correct "
          f"({eval_df['correct'].mean():.1%})")
    return result


# ── Accuracy recomputation ────────────────────────────────────────────────────

def recompute_accuracy(df: pd.DataFrame, kind: str) -> dict:
    """Recompute accuracy by tier from eval-set rows."""
    eval_rows = df[df["in_eval_set"] == True].copy()
    result = {}
    signal_col_map = {
        "Buy Low": "BUY_LOW", "Slight Buy": "SLIGHT_BUY",
        "Sell High": "SELL_HIGH", "Slight Sell": "SLIGHT_SELL",
    }
    for display, internal in signal_col_map.items():
        grp = eval_rows[eval_rows["signal"] == display]
        n   = len(grp)
        c   = int(grp["correct"].sum()) if n > 0 else 0
        result[internal] = {"n": n, "correct": c, "accuracy": c/n if n > 0 else float("nan")}
    n_all = len(eval_rows)
    c_all = int(eval_rows["correct"].sum())
    result["OVERALL"] = {"n": n_all, "correct": c_all,
                          "accuracy": c_all/n_all if n_all > 0 else float("nan")}
    return result


def print_accuracy_table(stats: dict, label: str, published: dict):
    print(f"\n  {label} — Accuracy Validation")
    print(f"  {'Tier':<14} {'N':>5} {'Correct':>8} {'Recomputed':>11} {'Published':>10} {'Match':>6}")
    print(f"  {'-'*58}")
    for tier in ["BUY_LOW","SLIGHT_BUY","SELL_HIGH","SLIGHT_SELL","OVERALL"]:
        if tier == "OVERALL":
            print(f"  {'-'*58}")
        s   = stats.get(tier, {})
        n   = s.get("n", 0)
        c   = s.get("correct", 0)
        acc = s.get("accuracy", float("nan"))
        pub = published.get(tier, float("nan"))
        if math.isnan(acc):
            acc_str = "   n/a"
        else:
            acc_str = f"{acc:>10.1%}"
        if math.isnan(pub):
            pub_str = "   n/a"
        else:
            pub_str = f"{pub:>9.1%}"
        match_str = ""
        if not math.isnan(acc) and not math.isnan(pub):
            match_str = "  OK" if abs(acc - pub) < 0.005 else f"  OFF by {(acc-pub)*100:+.1f}pp"
        print(f"  {tier:<14} {n:>5} {c:>8} {acc_str} {pub_str} {match_str}")


def flag_large_errors(df: pd.DataFrame, kind: str, threshold: float = 0.05) -> pd.DataFrame:
    """Flag player-seasons where model was wrong by large margin."""
    eval_rows = df[df["in_eval_set"] == True].copy()
    wrong = eval_rows[eval_rows["correct"] == False].copy()
    change_col = "actual_woba_change" if kind == "hitter" else "actual_era_change"
    if change_col not in wrong.columns:
        return pd.DataFrame()
    # Large error: wrong direction AND magnitude > threshold
    wrong["abs_change"] = wrong[change_col].abs()
    large = wrong[wrong["abs_change"] > threshold].sort_values("abs_change", ascending=False)
    return large[["player_name","mlbam_id","year","signal","predicted_direction",
                   change_col,"luck_score"]].copy()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 68)
    print("BACKTEST AUDIT LOG BUILDER — v7 (read-only, row-level export)")
    print("=" * 68)

    # Published accuracy numbers for validation
    PUBLISHED_H = {
        "BUY_LOW":    0.943,
        "SELL_HIGH":  0.941,
        "OVERALL":    0.862,
        "SLIGHT_BUY": float("nan"),
        "SLIGHT_SELL":float("nan"),
    }
    PUBLISHED_P = {
        "BUY_LOW":    0.865,
        "SELL_HIGH":  0.913,
        "OVERALL":    0.824,
        "SLIGHT_BUY": float("nan"),
        "SLIGHT_SELL":float("nan"),
    }

    # ── Load shared data ──────────────────────────────────────────────────────
    print("\nLoading shared data...")
    career_path  = BASE_DIR / "data" / "career_stats.json"
    seasonal_path= BASE_DIR / "data" / "seasonal_patterns.json"
    babip_path   = BASE_DIR / "data" / "hitter_career_babip.json"
    oaa_path     = BASE_DIR / "data" / "team_oaa_2025.csv"

    career_stats  = json.loads(career_path.read_text())  if career_path.exists()  else {}
    career_stats  = {int(k): v for k, v in career_stats.items()}
    patterns_raw  = json.loads(seasonal_path.read_text()) if seasonal_path.exists() else []
    patterns      = {int(r["player_id"]): r for r in patterns_raw} if isinstance(patterns_raw, list) else {}
    career_babip_h= {}
    if babip_path.exists():
        raw = json.loads(babip_path.read_text())
        for pid_str, rec in raw.items():
            cb = rec.get("career_babip")
            if cb is not None:
                career_babip_h[int(pid_str)] = float(cb)

    oaa_adj = {}
    if oaa_path.exists():
        oaa_df  = pd.read_csv(oaa_path, usecols=["team_abbr","babip_adj"])
        oaa_adj = dict(zip(oaa_df["team_abbr"], oaa_df["babip_adj"]))

    stuff_plus   = load_stuff_plus()
    career_babip_p = load_career_babip_p()
    print(f"  career_stats={len(career_stats):,}  patterns={len(patterns):,}  "
          f"babip_h={len(career_babip_h):,}  stuff+={len(stuff_plus):,}  "
          f"babip_p={len(career_babip_p):,}")

    # ── Build name lookup ─────────────────────────────────────────────────────
    print("\nBuilding player name lookup...")
    pitcher_names = pitcher_name_from_parquets()
    print(f"  Pitcher names from parquets: {len(pitcher_names)}")

    # Collect all hitter IDs to resolve in one batch
    all_batter_ids = set()
    for yr in [2022, 2023, 2024, 2025]:
        p = CACHE_DIR / f"v4_april_{yr}.csv"
        if p.exists():
            df = pd.read_csv(p, usecols=["batter"])
            all_batter_ids.update(df["batter"].dropna().astype(int).tolist())
    hitter_names = build_name_lookup(all_batter_ids)

    # ════════════════════════════════════════════════════════════════════════
    print("\n" + "═"*68)
    print("SECTION 1: HITTER BACKTEST  (2022–2025)")
    print("═"*68)

    h_frames = []
    for year in [2022, 2023, 2024, 2025]:
        print(f"\nRunning hitter {year}...")
        opp_oaa_yr = {}
        oaa_cache  = CACHE_DIR / f"opponent_oaa_april_{year}.csv"
        if oaa_cache.exists():
            oc = pd.read_csv(oaa_cache)
            opp_oaa_yr = dict(zip(oc.iloc[:,0].astype(int), oc.iloc[:,1].astype(float)))
        frame = run_year_h_rows(year, career_stats, patterns, career_babip_h,
                                opp_oaa_yr, hitter_names)
        if frame is not None:
            h_frames.append(frame)

    if not h_frames:
        print("ERROR: no hitter data produced"); return

    h_audit = pd.concat(h_frames, ignore_index=True)
    h_stats = recompute_accuracy(h_audit, "hitter")

    print(f"\n{'='*68}")
    print(f"HITTER RESULTS  ({len(h_audit)} total player-seasons, "
          f"{h_audit['in_eval_set'].sum()} in eval)")
    print_accuracy_table(h_stats, "Hitters", PUBLISHED_H)

    # Large errors
    h_errors = flag_large_errors(h_audit, "hitter", threshold=0.05)
    if not h_errors.empty:
        print(f"\n  Large errors (wrong + |wOBA change| > 0.050): {len(h_errors)}")
        for _, r in h_errors.head(10).iterrows():
            chg = r["actual_woba_change"]
            print(f"    {r['player_name']:<22} {r['year']}  signal={r['signal']:<12}  "
                  f"predicted={r['predicted_direction']:<10}  woba_chg={chg:>+.3f}  "
                  f"luck={r['luck_score']:>+.3f}")

    # By year
    print(f"\n  Accuracy by year (eval set):")
    for yr, grp in h_audit[h_audit["in_eval_set"]].groupby("year"):
        c = int(grp["correct"].sum()); n = len(grp)
        print(f"    {yr}: {n:>3} eval  {c:>3} correct  {c/n:.1%}")

    # Save
    out_h = DATA_DIR / "backtest_audit_hitters.csv"
    h_audit.to_csv(out_h, index=False)
    print(f"\n  Saved: {out_h}  ({len(h_audit)} rows)")

    # ════════════════════════════════════════════════════════════════════════
    print("\n" + "═"*68)
    print("SECTION 2: PITCHER BACKTEST  (2022–2025)")
    print("═"*68)

    p_frames = []
    for year in [2022, 2023, 2024, 2025]:
        print(f"\nRunning pitcher {year}...")
        frame = run_year_p_rows(year, stuff_plus, career_babip_p, pitcher_names)
        if frame is not None:
            p_frames.append(frame)

    if not p_frames:
        print("ERROR: no pitcher data produced"); return

    p_audit = pd.concat(p_frames, ignore_index=True)
    p_stats = recompute_accuracy(p_audit, "pitcher")

    print(f"\n{'='*68}")
    print(f"PITCHER RESULTS  ({len(p_audit)} total player-seasons, "
          f"{p_audit['in_eval_set'].sum()} in eval)")
    print_accuracy_table(p_stats, "Pitchers", PUBLISHED_P)

    # Large errors
    p_errors = flag_large_errors(p_audit, "pitcher", threshold=0.75)
    if not p_errors.empty:
        print(f"\n  Large errors (wrong + |ERA change| > 0.75): {len(p_errors)}")
        for _, r in p_errors.head(10).iterrows():
            chg = r["actual_era_change"]
            print(f"    {r['player_name']:<22} {r['year']}  signal={r['signal']:<12}  "
                  f"predicted={r['predicted_direction']:<10}  ERA_chg={chg:>+.2f}  "
                  f"luck={r['luck_score']:>+.3f}")

    # By year
    print(f"\n  Accuracy by year (eval set):")
    for yr, grp in p_audit[p_audit["in_eval_set"]].groupby("year"):
        c = int(grp["correct"].sum()); n = len(grp)
        print(f"    {yr}: {n:>3} eval  {c:>3} correct  {c/n:.1%}")

    # Save
    out_p = DATA_DIR / "backtest_audit_pitchers.csv"
    p_audit.to_csv(out_p, index=False)
    print(f"\n  Saved: {out_p}  ({len(p_audit)} rows)")

    # ════════════════════════════════════════════════════════════════════════
    print(f"\n{'═'*68}")
    print("SUMMARY")
    print("═"*68)
    h_ov = h_stats["OVERALL"]["accuracy"]
    h_bl = h_stats["BUY_LOW"]["accuracy"]
    h_sh = h_stats["SELL_HIGH"]["accuracy"]
    p_ov = p_stats["OVERALL"]["accuracy"]
    p_bl = p_stats["BUY_LOW"]["accuracy"]
    p_sh = p_stats["SELL_HIGH"]["accuracy"]

    print(f"\n  Hitter overall:      {h_ov:.1%}  (published 86.2%)")
    print(f"  Hitter buy low:      {h_bl:.1%}  (published 94.3%)")
    print(f"  Hitter sell high:    {h_sh:.1%}  (published 94.1%)")
    print(f"  Pitcher overall:     {p_ov:.1%}  (published 82.4%)")
    print(f"  Pitcher buy low:     {p_bl:.1%}  (published 86.5%)")
    print(f"  Pitcher sell high:   {p_sh:.1%}  (published 91.3%)")
    print(f"\n  Hitter player-seasons: {len(h_audit)}  (eval: {int(h_audit['in_eval_set'].sum())})")
    print(f"  Pitcher player-seasons: {len(p_audit)}  (eval: {int(p_audit['in_eval_set'].sum())})")
    print(f"\n  Files saved:")
    print(f"    {out_h}")
    print(f"    {out_p}")
    print(f"\n{'='*68}")


if __name__ == "__main__":
    main()
