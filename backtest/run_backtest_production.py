# NOTE: This script produces approximate results
# (71.7% Buy Low vs validated 82.1% from
# backtest_pitcher_composite.py). Gap is due to
# simplified conflict resolution vs Version E's
# 8-component composite. Do not use for published
# accuracy numbers. Use backtest_pitcher_composite.py
# results as authoritative.

"""
run_backtest_production.py
==========================
Feeds historical April player-seasons (2022-2025) through the PRODUCTION
scorers (score_luck.py v5 and score_pitcher_luck.py v2.0) rather than
reimplementing scoring logic inline.

Root cause of prior discrepancy:
  run_backtest_fresh.py reimplemented v7 scoring (hitter thresholds 0.020/0.040,
  pitcher threshold ERA-FIP gap 0.60/1.20) instead of calling production code.
  Production thresholds: hitter 0.065/0.150; pitcher composite buy_score/sell_score
  with ERA floor gates (< 3.50 all buys, < 4.00 Slight Buy).

Approach:
  1. Aggregate historical raw Statcast into hitter_luck_input / pitcher_luck_input format
  2. Import production scoring functions (NOT main()) — read-only, no file writes
  3. Run the full production pipeline for each year (2022-2025)
  4. Compare to May-July outcomes; report accuracy tables

Caveats:
  - career_quality.json, career_babip.json use 2026 data (3yr rolling averages are
    stable; small bias expected but acceptable for methodology validation)
  - Stuff+ override skipped for pitchers (historical pitch data not cached per-year)
  - OAA BABIP adjustment skipped (no historical team OAA data by year)
  - Platoon modifier skipped (needs same-season splits file)
  - season_day=30 used for all years (consistent end-of-April scoring)

Output:
  data/backtest_audit_hitters_v2.csv   — row-level, 2022-2025
  data/backtest_audit_pitchers_v2.csv  — row-level, 2022-2025
"""

import io
import json
import math
import os
import sys

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # project root
CACHE_DIR = os.path.join(BASE_DIR, "backtest_cache")
DATA_DIR  = os.path.join(BASE_DIR, "data")

# ── Import production scorer functions (read-only — no main() calls) ──────────
sys.path.insert(0, BASE_DIR)
from score_luck import (
    assign_verdict         as assign_verdict_h,
    confidence_scale       as conf_scale_h,
    _chase_modifier,
    _zcon_babip_modifier,
    _pull_modifier,
    _park_factor           as park_factor_h,
    _quality_tier,
    _playing_time_scale,
    _amplification_cap     as amp_cap_h,
    _hitter_babip_age_mult,
    _load_career_quality,
    _load_seasonal_patterns,
    _seasonal_modifier,
    LEAGUE_AVG_BABIP,
    LEAGUE_AVG_HRFB,
    LEAGUE_AVG_XWOBA,
)
from score_pitcher_luck import (
    assign_verdict         as assign_verdict_p,
    confidence_scale_ip,
    hrfb_component         as hrfb_comp_p,
    _park_factor           as park_factor_p,
    _pitcher_quality_tier,
    _amplification_cap     as amp_cap_p,
    _pitcher_babip_age_mult,
    is_buy_qualified,
    LEAGUE_AVG_BABIP_P,
    MIN_BUY_IP,
    NON_PA_EVENTS,
    PRIMARY_COMPONENTS,
    VALIDATOR_COMPONENTS,
)
from backtest_pitcher_within_season import compute_pitcher_stats as _pitcher_agg

print("Production scorer functions imported OK")

# ── Constants ─────────────────────────────────────────────────────────────────
SEASON_DAY      = 30          # end-of-April scoring phase for all years
MIN_APRIL_PA    = 80          # minimum April PA for hitters
MIN_OUTCOME_PA  = 100         # minimum May-July PA for hitters to enter eval
MIN_PITCHER_IP  = 15.0        # minimum April IP to appear in eval
MIN_OUTCOME_IP  = 20.0        # minimum May-July IP for pitchers to enter eval
FLAT_THRESHOLD  = 0.015       # wOBA change below this = Flat (not evaluated)

SWING_DESCRIPTIONS = frozenset({
    "swinging_strike", "swinging_strike_blocked", "foul", "foul_bunt",
    "foul_tip", "hit_into_play", "hit_into_play_no_out", "hit_into_play_score",
    "missed_bunt",
})
CONTACT_DESCRIPTIONS = frozenset({
    "foul", "foul_bunt", "foul_tip",
    "hit_into_play", "hit_into_play_no_out", "hit_into_play_score",
})
BIP_BB_TYPES = frozenset({"ground_ball", "fly_ball", "line_drive", "popup"})

# ── Support data (2026 vintage — stable across years for methodology test) ────
_career_stats: dict = {}
_career_quality: dict = {}
_career_babip_h: dict = {}
_career_hh_h:   dict = {}
_career_babip_p: dict = {}
_career_hh_p:   dict = {}
_career_barrel_p: dict = {}
_seasonal_patterns: dict = {}

def _load_support_data():
    global _career_stats, _career_quality, _career_babip_h, _career_hh_h
    global _career_babip_p, _career_hh_p, _career_barrel_p, _seasonal_patterns

    p_cs = os.path.join(DATA_DIR, "career_stats.json")
    if os.path.exists(p_cs):
        with open(p_cs) as f:
            _career_stats = {int(k): v for k, v in json.load(f).items()}
        print(f"  career_stats.json: {len(_career_stats):,} records")

    p_cq = os.path.join(DATA_DIR, "career_quality.json")
    if os.path.exists(p_cq):
        with open(p_cq, encoding="utf-8", errors="replace") as f:
            _cq_records = json.load(f)
        _career_quality = {int(r["player_id"]): r for r in _cq_records}
    print(f"  career_quality.json: {len(_career_quality):,} records")

    p_hbabip = os.path.join(DATA_DIR, "hitter_career_babip.json")
    if os.path.exists(p_hbabip):
        with open(p_hbabip) as f:
            raw = json.load(f)
        for k, v in raw.items():
            if isinstance(v, dict):
                if v.get("career_babip") is not None:
                    _career_babip_h[str(k)] = float(v["career_babip"])
                if v.get("career_hard_hit") is not None:
                    _career_hh_h[int(k)] = float(v["career_hard_hit"])
        print(f"  hitter_career_babip.json: {len(_career_babip_h):,} records")

    p_pbabip = os.path.join(DATA_DIR, "pitcher_career_babip.json")
    if os.path.exists(p_pbabip):
        with open(p_pbabip) as f:
            raw = json.load(f)
        for k, v in raw.items():
            if isinstance(v, dict):
                if v.get("career_babip_allowed") is not None:
                    _career_babip_p[str(k)] = float(v["career_babip_allowed"])
                if v.get("career_hard_hit_allowed") is not None:
                    _career_hh_p[int(k)] = float(v["career_hard_hit_allowed"])
                if v.get("career_barrel_allowed") is not None:
                    _career_barrel_p[int(k)] = float(v["career_barrel_allowed"])
        print(f"  pitcher_career_babip.json: {len(_career_babip_p):,} records")

    p_sp = os.path.join(DATA_DIR, "seasonal_patterns.json")
    _seasonal_patterns = _load_seasonal_patterns(p_sp)
    print(f"  seasonal_patterns.json: {len(_seasonal_patterns):,} records")


# ══════════════════════════════════════════════════════════════════════════════
# HITTER MODULE
# ══════════════════════════════════════════════════════════════════════════════

def _agg_hitters_from_statcast(april: pd.DataFrame, team_map: dict) -> pd.DataFrame:
    """
    Aggregate pitch-level April Statcast into per-player stats matching
    the hitter_luck_input.csv format required by production scorer.
    """
    # PA-ending events only (woba_value non-null)
    pa = april[april["woba_value"].notna()].copy()
    pa_agg = pa.groupby("batter").agg(
        PA=("woba_value", "count"),
        wOBA=("woba_value", "mean"),
    ).reset_index()

    if "estimated_woba_using_speedangle" in april.columns:
        xw = pa[pa["estimated_woba_using_speedangle"].notna()].groupby("batter")[
            "estimated_woba_using_speedangle"
        ].mean().reset_index()
        xw.columns = ["batter", "xwOBA"]
        pa_agg = pa_agg.merge(xw, on="batter", how="left")
    else:
        pa_agg["xwOBA"] = np.nan

    # BIP aggregation
    bip = april[april["bb_type"].isin(BIP_BB_TYPES)].copy()
    bip["is_hit"]  = bip["events"].isin({"single","double","triple"}).astype(int)
    bip["is_gb"]   = (bip["bb_type"] == "ground_ball").astype(int)
    bip["is_fb"]   = (bip["bb_type"] == "fly_ball").astype(int)
    bip_agg = bip.groupby("batter").agg(
        bip_n=("bb_type", "count"),
        hits_bip=("is_hit", "sum"),
        gb=("is_gb", "sum"),
        fb=("is_fb", "sum"),
    ).reset_index()

    # HR for HR/FB
    hr_agg = (
        april[april["events"] == "home_run"]
        .groupby("batter")
        .size()
        .reset_index(name="hr_count")
    )

    # BBE (batted ball events with launch data)
    bbe = april[april["launch_speed"].notna() & april["launch_angle"].notna()].copy()
    bbe["is_hard"]   = (bbe["launch_speed"] >= 95).astype(int)
    bbe["is_barrel"] = (bbe.get("launch_speed_angle", pd.Series(dtype=float)) == 6).astype(int) \
                       if "launch_speed_angle" in bbe.columns else 0
    bbe["is_ss"]     = bbe["launch_angle"].between(8, 32).astype(int)
    bbe_agg = bbe.groupby("batter").agg(
        bbe_n=("launch_speed", "count"),
        hard=("is_hard", "sum"),
        barrel=("is_barrel", "sum"),
        sweet_spot=("is_ss", "sum"),
        avg_exit_velocity=("launch_speed", "mean"),
    ).reset_index()

    # Discipline (BB, K)
    april["is_bb"] = april["events"].isin({"walk", "intent_walk"}).astype(int)
    april["is_k"]  = april["events"].isin({"strikeout","strikeout_double_play"}).astype(int)
    disc = april.groupby("batter").agg(bb_count=("is_bb","sum"), k_count=("is_k","sum")).reset_index()

    # Zone discipline (z_contact, o_swing) — requires zone + description columns
    z_contact_map: dict = {}
    o_swing_map: dict   = {}
    if "zone" in april.columns and "description" in april.columns:
        pitches = april[april["zone"].notna() & april["description"].notna()].copy()
        pitches["is_swing"]   = pitches["description"].isin(SWING_DESCRIPTIONS).astype(int)
        pitches["is_contact"] = pitches["description"].isin(CONTACT_DESCRIPTIONS).astype(int)
        pitches["in_zone"]    = pitches["zone"].between(1, 9).astype(int)
        pitches["out_zone"]   = pitches["zone"].between(11, 14).astype(int)

        for bid, grp in pitches.groupby("batter"):
            z_sw  = (grp["is_swing"] * grp["in_zone"]).sum()
            z_con = (grp["is_contact"] * grp["in_zone"]).sum()
            o_sw  = (grp["is_swing"] * grp["out_zone"]).sum()
            o_tot = grp["out_zone"].sum()
            z_contact_map[bid] = z_con / z_sw   if z_sw  > 0 else np.nan
            o_swing_map[bid]   = o_sw  / o_tot  if o_tot > 0 else np.nan

    # Pull rate (requires hc_x, hc_y, stand)
    pull_map: dict = {}
    if "hc_x" in april.columns and "stand" in april.columns:
        bip_pull = bip[bip["hc_x"].notna() & bip["stand"].notna()].copy()
        bip_pull["is_pull"] = np.where(
            bip_pull["stand"] == "R",
            (bip_pull["hc_x"] < 100).astype(int),
            (bip_pull["hc_x"] > 150).astype(int),
        )
        for bid, grp in bip_pull.groupby("batter"):
            pull_map[bid] = grp["is_pull"].mean()

    # Team map
    team_series = pd.Series(team_map, name="team").rename_axis("batter")

    # Assemble final DataFrame
    df = pa_agg.merge(bip_agg,  on="batter", how="left")
    df = df.merge(hr_agg,   on="batter", how="left")
    df = df.merge(bbe_agg,  on="batter", how="left")
    df = df.merge(disc,     on="batter", how="left")
    df = df.merge(team_series.reset_index(), on="batter", how="left")

    df["hr_count"] = df["hr_count"].fillna(0)

    # Derived rates
    df["BABIP"]            = np.where(df["bip_n"] > 0, df["hits_bip"] / df["bip_n"], np.nan)
    df["gb_rate"]          = np.where(df["bip_n"] > 0, df["gb"] / df["bip_n"], np.nan)
    df["fb_rate"]          = np.where(df["bip_n"] > 0, df["fb"] / df["bip_n"], np.nan)
    df["hr_fb_rate"]       = np.where(df["fb"] > 0,    df["hr_count"] / df["fb"], np.nan)
    df["hard_hit_rate"]    = np.where(df["bbe_n"] > 0, df["hard"]       / df["bbe_n"], np.nan)
    df["barrel_rate"]      = np.where(df["bbe_n"] > 0, df["barrel"]     / df["bbe_n"], np.nan)
    df["sweet_spot_rate"]  = np.where(df["bbe_n"] > 0, df["sweet_spot"] / df["bbe_n"], np.nan)
    df["bb_rate"]          = df["bb_count"] / df["PA"]
    df["k_rate"]           = df["k_count"]  / df["PA"]
    df["bb_k_ratio"]       = np.where(df["k_count"] > 0, df["bb_count"] / df["k_count"], np.nan)

    df["z_contact_rate"] = df["batter"].map(z_contact_map)
    df["o_swing_rate"]   = df["batter"].map(o_swing_map)
    df["pull_rate"]      = df["batter"].map(pull_map)

    return df


def score_hitters_production(df: pd.DataFrame, year: int) -> pd.DataFrame:
    """
    Run the full production scoring pipeline (score_luck.py v5) on a
    pre-aggregated hitter DataFrame. Returns df with luck_score and verdict.
    """
    df = df.copy()

    # ── xwOBA gap ────────────────────────────────────────────────────────────
    df["xwOBA_gap"] = (df["xwOBA"] - df["wOBA"]).fillna(0.0).round(4)

    # ── Park factor ──────────────────────────────────────────────────────────
    df["park_factor"] = df["team"].map(park_factor_h).fillna(1.0)

    # ── Career BABIP + age adjustment ────────────────────────────────────────
    df["career_babip"] = df["batter"].apply(
        lambda b: _career_babip_h.get(str(int(b))) if pd.notna(b) else None
    )
    df["babip_baseline"] = df["career_babip"].fillna(LEAGUE_AVG_BABIP)

    _byr = {k: int(v.get("birth_year") or 0) for k, v in _career_stats.items()}
    df["_age"] = df["batter"].apply(lambda b: year - _byr[int(b)] if int(b) in _byr and _byr[int(b)] > 0 else 0)
    df["age_adj_career_babip"] = df.apply(
        lambda r: round(r["babip_baseline"] * _hitter_babip_age_mult(int(r["_age"])), 4)
        if pd.notna(r["career_babip"]) and r["_age"] > 0
        else r["babip_baseline"],
        axis=1,
    )
    df["park_adj_babip_expected"] = (df["age_adj_career_babip"] * df["park_factor"]).round(4)
    df["park_adj_hrfb_expected"]  = (LEAGUE_AVG_HRFB * df["park_factor"]).round(4)

    # GB rate BABIP adjustment
    if "gb_rate" in df.columns:
        df.loc[df["gb_rate"] > 0.50, "park_adj_babip_expected"] -= 0.010
        df.loc[df["gb_rate"] < 0.35, "park_adj_babip_expected"] += 0.008

    # ── Component 1: BABIP with contextual modifiers ──────────────────────────
    has_hhr = "hard_hit_rate" in df.columns
    babip_comp = (df["BABIP"] - df["park_adj_babip_expected"]) * -3.000

    if "o_swing_rate" in df.columns:
        babip_comp = babip_comp * df.apply(
            lambda r: _chase_modifier(r["o_swing_rate"], r["BABIP"], int(r["PA"])), axis=1
        )
    babip_comp = babip_comp * df.apply(
        lambda r: _zcon_babip_modifier(
            r["z_contact_rate"] if "z_contact_rate" in df.columns else float("nan"),
            r["BABIP"],
            r["hard_hit_rate"] if has_hhr else float("nan"),
            int(r["PA"]),
            _career_hh_h.get(int(r["batter"]), 0.370),
        ),
        axis=1,
    )

    # ── Component 2: HR/FB with pull modifier ────────────────────────────────
    hrfb_comp = (df["hr_fb_rate"].fillna(LEAGUE_AVG_HRFB) - df["park_adj_hrfb_expected"]) * -0.150
    if "pull_rate" in df.columns:
        hrfb_comp = hrfb_comp * df.apply(
            lambda r: _pull_modifier(
                r["pull_rate"] if pd.notna(r.get("pull_rate")) else float("nan"),
                r["hard_hit_rate"] if has_hhr else float("nan"),
                int(r["PA"]),
                _career_hh_h.get(int(r["batter"]), 0.370),
            ),
            axis=1,
        )

    # ── Component 3: Z-contact ────────────────────────────────────────────────
    if "z_contact_rate" in df.columns:
        zcon_comp = (df["z_contact_rate"].fillna(0.880) - 0.880) * -0.030
    else:
        zcon_comp = pd.Series(0.0, index=df.index)

    # ── Component 4: xwOBA gap ───────────────────────────────────────────────
    xwoba_comp = df["xwOBA_gap"] * 1.000

    df["luck_score"] = (babip_comp + hrfb_comp + zcon_comp + xwoba_comp).round(4)

    # ── Confidence scale by PA ───────────────────────────────────────────────
    df["luck_score"] = df.apply(
        lambda r: round(r["luck_score"] * conf_scale_h(int(r["PA"])), 4), axis=1
    )

    # ── Playing time discount ────────────────────────────────────────────────
    p90_pa = float(df["PA"].quantile(0.90))
    df["luck_score"] = df.apply(
        lambda r: round(r["luck_score"] * _playing_time_scale(int(r["PA"]), p90_pa), 4), axis=1
    )

    # ── Sweet spot modifier ──────────────────────────────────────────────────
    if "sweet_spot_rate" in df.columns:
        buy = df["luck_score"] > 0
        df.loc[buy & (df["sweet_spot_rate"] > 0.12), "luck_score"] = \
            (df.loc[buy & (df["sweet_spot_rate"] > 0.12), "luck_score"] * 1.05).round(4)
        df.loc[buy & (df["sweet_spot_rate"] < 0.06), "luck_score"] = \
            (df.loc[buy & (df["sweet_spot_rate"] < 0.06), "luck_score"] * 0.95).round(4)

    # ── EV trend modifier ────────────────────────────────────────────────────
    if "avg_exit_velocity" in df.columns:
        for idx, row in df.iterrows():
            if row["luck_score"] <= 0:
                continue
            career_ev = (_career_stats.get(int(row["batter"])) or {}).get("avg_exit_velocity")
            if career_ev is None or pd.isna(row["avg_exit_velocity"]):
                continue
            ev_below = (row["avg_exit_velocity"] - career_ev) < -1.0
            ss = row.get("sweet_spot_rate")
            low_ss = pd.notna(ss) and ss < 0.08
            if ev_below and low_ss:
                df.at[idx, "luck_score"] = round(row["luck_score"] * 0.85, 4)
            elif ev_below or low_ss:
                df.at[idx, "luck_score"] = round(row["luck_score"] * 0.93, 4)

    # ── Plate discipline modifier ────────────────────────────────────────────
    if "bb_rate" in df.columns and "k_rate" in df.columns:
        buy = df["luck_score"] > 0
        elite = buy & (df["bb_rate"] > 0.10) & (df["k_rate"] < 0.18)
        poor  = buy & ((df["bb_rate"] < 0.06) | (df["k_rate"] > 0.28))
        df.loc[elite, "luck_score"] = (df.loc[elite, "luck_score"] * 1.08).round(4)
        df.loc[poor,  "luck_score"] = (df.loc[poor,  "luck_score"] * 0.88).round(4)

    # ── Age rise boost ───────────────────────────────────────────────────────
    rising = (df["_age"] > 0) & (df["_age"] < 28) & (df["luck_score"] > 0)
    df.loc[rising, "luck_score"] = (df.loc[rising, "luck_score"] + 0.02).round(4)

    # ── Seasonal patterns ────────────────────────────────────────────────────
    if _seasonal_patterns:
        for idx, row in df.iterrows():
            bid = int(row["batter"])
            if bid not in _seasonal_patterns:
                continue
            ls, adj = _seasonal_modifier(bid, row["luck_score"], _seasonal_patterns)
            df.at[idx, "luck_score"] = ls

    # ── Career quality / wRC+ ────────────────────────────────────────────────
    df["xwoba_3yr"]  = df["batter"].map(
        lambda b: float(_career_quality[int(b)]["xwoba_3yr"])
        if int(b) in _career_quality and not pd.isna(_career_quality[int(b)].get("xwoba_3yr", float("nan")))
        else float("nan")
    )
    df["wrc_plus_3yr"] = df.apply(
        lambda r: round((r["xwoba_3yr"] / LEAGUE_AVG_XWOBA) * r["park_factor"] * 100, 1)
        if not math.isnan(r["xwoba_3yr"]) else 100.0,
        axis=1,
    )

    # ── Quality tier multiplier (buy signals only) ────────────────────────────
    df["_luck_raw_for_cap"] = df["luck_score"].copy()
    df["luck_score"] = df.apply(
        lambda r: round(r["luck_score"] * _quality_tier(r["wrc_plus_3yr"])[0], 4)
        if r["luck_score"] > 0 else r["luck_score"],
        axis=1,
    )

    # ── RTM integration ──────────────────────────────────────────────────────
    df["rtm_signal"] = df.apply(
        lambda r: round(float(r["xwoba_3yr"]) - float(r["wOBA"]), 4)
        if not math.isnan(r["xwoba_3yr"]) and pd.notna(r["wOBA"]) else 0.0,
        axis=1,
    )
    def _rtm_combine_h(row) -> float:
        ls = row["luck_score"]
        rt = row["rtm_signal"]
        combined = ls * 0.75 + (rt * 10) * 0.25
        if (ls > 0 and rt > 0) or (ls < 0 and rt < 0):
            combined *= 1.15
        return round(combined, 4)
    df["luck_score"] = df.apply(_rtm_combine_h, axis=1)

    # ── Amplification cap ────────────────────────────────────────────────────
    cap_results = df.apply(
        lambda r: amp_cap_h(r["luck_score"], r["_luck_raw_for_cap"]), axis=1
    )
    df["luck_score"] = cap_results.apply(lambda t: t[0])
    df.drop(columns=["_luck_raw_for_cap"], inplace=True)

    # ── Verdict ──────────────────────────────────────────────────────────────
    df["verdict"] = df["luck_score"].apply(assign_verdict_h)

    # Slight buy confidence gate: xwOBA gap near-zero = BABIP-only signal
    sb_mask = (df["verdict"] == "Slight buy") & (df["xwOBA_gap"].fillna(0.0) < 0.015)
    df.loc[sb_mask, "verdict"] = "Neutral"

    return df


def run_hitter_year(year: int, name_lut: dict) -> pd.DataFrame | None:
    april_path   = os.path.join(CACHE_DIR, f"v4_april_{year}.csv")
    outcome_path = os.path.join(CACHE_DIR, f"statcast_{year}_may_july.csv")
    team_path    = os.path.join(CACHE_DIR, f"team_map_{year}.csv")

    if not os.path.exists(april_path) or not os.path.exists(outcome_path):
        print(f"  {year}: SKIPPED — cache file missing")
        return None

    print(f"\n── HITTER {year} ──────────────────────────────")
    april = pd.read_csv(april_path)
    print(f"  April Statcast: {len(april):,} rows")

    team_map: dict = {}
    if os.path.exists(team_path):
        tm = pd.read_csv(team_path)
        team_map = dict(zip(tm["batter"], tm["team"]))
        print(f"  Team map: {len(team_map):,} entries")

    # Aggregate into hitter_luck_input format
    df = _agg_hitters_from_statcast(april, team_map)
    df = df[df["PA"] >= MIN_APRIL_PA].copy()
    print(f"  After PA >= {MIN_APRIL_PA} filter: {len(df):,} hitters")

    # Run production scoring
    df = score_hitters_production(df, year)
    print(f"  Verdict distribution:\n{df['verdict'].value_counts().to_string()}")

    # Outcomes
    outcome = pd.read_csv(outcome_path)
    may_july = outcome.groupby("batter").agg(
        outcome_pa=("woba_value", "count"),
        outcome_woba=("woba_value", "mean"),
    ).reset_index()

    merged = df.merge(may_july, on="batter", how="inner")
    merged = merged[merged["outcome_pa"] >= MIN_OUTCOME_PA].copy()
    merged["woba_change"] = merged["outcome_woba"] - merged["wOBA"]
    merged["outcome"] = np.where(
        merged["woba_change"] >=  FLAT_THRESHOLD, "IMPROVED",
        np.where(merged["woba_change"] <= -FLAT_THRESHOLD, "DECLINED", "FLAT"),
    )

    SIGNAL_MAP = {"Buy low": "IMPROVED", "Slight buy": "IMPROVED",
                  "Sell high": "DECLINED", "Slight sell": "DECLINED"}
    merged["predicted_direction"] = merged["verdict"].map(SIGNAL_MAP).fillna("")
    merged["in_eval"] = (
        merged["verdict"].isin(SIGNAL_MAP) & (merged["outcome"] != "FLAT")
    )
    eval_df = merged[merged["in_eval"]].copy()
    eval_df["correct"] = eval_df.apply(
        lambda r: r["outcome"] == SIGNAL_MAP[r["verdict"]], axis=1
    )
    merged = merged.merge(eval_df[["batter", "correct"]], on="batter", how="left")

    rows = []
    for _, r in merged.iterrows():
        bid = int(r["batter"])
        rows.append({
            "player_name":         name_lut.get(bid, f"ID_{bid}"),
            "mlbam_id":            bid,
            "year":                year,
            "signal":              r["verdict"],
            "luck_score":          round(float(r["luck_score"]), 4),
            "woba_actual":         round(float(r["wOBA"]),  4),
            "xwoba_actual":        round(float(r["xwOBA"]), 4) if pd.notna(r.get("xwOBA")) else None,
            "predicted_direction": r["predicted_direction"],
            "actual_woba_change":  round(float(r["woba_change"]), 4),
            "outcome":             r["outcome"],
            "in_eval":             bool(r["in_eval"]),
            "correct":             bool(r["correct"]) if pd.notna(r.get("correct")) else None,
        })
    result = pd.DataFrame(rows)
    n_eval = int(result["in_eval"].sum())
    n_corr = int(result[result["in_eval"]]["correct"].sum())
    pct = n_corr / n_eval if n_eval > 0 else float("nan")
    print(f"  Eval: {n_eval:>3} players | {n_corr:>3} correct | {pct:.1%}")
    return result


# ══════════════════════════════════════════════════════════════════════════════
# PITCHER MODULE
# ══════════════════════════════════════════════════════════════════════════════

COMPONENTS_P = PRIMARY_COMPONENTS + VALIDATOR_COMPONENTS


def _agg_pitchers_from_statcast(sc: pd.DataFrame, year: int) -> pd.DataFrame:
    """
    Extend backtest_pitcher_within_season.compute_pitcher_stats() output
    with additional columns required by production scorer:
    lob_pct, hr_fb_rate, hard_hit_rate_allowed, barrel_rate_allowed, swstr_rate,
    k_pct, bb_pct, xwoba_gap, gb_pct, xERA, FIP, ERA_minus_FIP, ERA_minus_xERA
    """
    base = _pitcher_agg(sc)  # pitcher, outs, k, bb, hr, hits, pa, runs_allowed, ip, era, fip,
                               # babip, xwoba_allowed, woba_allowed, xera, team, name

    # Override xERA with production formula (all-PA xwOBA, not contact-only).
    # backtest_pitcher_within_season uses BBE-only xwOBA which inflates xERA for
    # high-K pitchers (Eovaldi 2023: BBE-xERA=4.51 vs all-PA xERA=2.22), causing
    # the FIP/xERA conflict gate to incorrectly block Buy Low signals.
    # process_pitcher_stats.py: xERA = (xwoba_pa_mean - 0.320) * 33.0 + 4.00
    # NOTE: xwoba_allowed (for xwoba_gap) intentionally left as contact-only —
    # changing it would shrink xwoba_gap for all pitchers and kill sell signals.
    _pa_ev = sc[sc["events"].notna() & ~sc["events"].isin(NON_PA_EVENTS)].copy()
    if "woba_value" in _pa_ev.columns and "estimated_woba_using_speedangle" in _pa_ev.columns:
        _pa_ev["xwoba_pa"] = _pa_ev["estimated_woba_using_speedangle"].fillna(_pa_ev["woba_value"])
        _xwoba_pa  = _pa_ev.groupby("pitcher")["xwoba_pa"].mean()
        _xera_prod = ((_xwoba_pa - 0.320) * 33.0 + 4.00).round(3)
        base = base.merge(_xera_prod.rename("_xera_prod").reset_index(), on="pitcher", how="left")
        base["xera"] = base["_xera_prod"].fillna(base["xera"])
        base.drop(columns=["_xera_prod"], inplace=True)

    # LOB% = (H + BB - R) / (H + BB - 1.4*HR)  [ignoring HBP — small effect]
    H  = base["hits"]
    BB = base["bb"]
    HR = base["hr"]
    R  = base["runs_allowed"]
    denom = H + BB - 1.4 * HR
    base["lob_pct"] = np.where(denom > 0, (H + BB - R) / denom, 0.724)
    base["lob_pct"] = base["lob_pct"].clip(0, 1)

    # HR/FB rate — need fly ball counts from bb_type
    sc_bbe = sc[sc["bb_type"].notna()].copy()
    fb_agg = sc_bbe[sc_bbe["bb_type"] == "fly_ball"].groupby("pitcher").size().rename("fb_count")
    base = base.merge(fb_agg.reset_index(), on="pitcher", how="left")
    base["fb_count"] = base["fb_count"].fillna(0)
    base["hr_fb_rate"] = np.where(base["fb_count"] > 0, base["hr"] / base["fb_count"], np.nan)

    # BBE stats: hard_hit_rate, barrel_rate
    bbe = sc[sc["launch_speed"].notna() & sc["launch_angle"].notna()].copy()
    bbe["is_hard"]   = (bbe["launch_speed"] >= 95).astype(int)
    if "launch_speed_angle" in bbe.columns:
        bbe["is_barrel"] = (bbe["launch_speed_angle"].fillna(0) == 6).astype(int)
    else:
        bbe["is_barrel"] = 0
    bbe_agg = bbe.groupby("pitcher").agg(
        bbe_n=("launch_speed", "count"),
        hard=("is_hard", "sum"),
        barrel=("is_barrel", "sum"),
    ).reset_index()
    base = base.merge(bbe_agg, on="pitcher", how="left")
    bbe_n = base["bbe_n"].fillna(0)
    base["hard_hit_rate_allowed"] = np.where(bbe_n > 0, base["hard"].fillna(0) / bbe_n, np.nan)
    base["barrel_rate_allowed"]   = np.where(bbe_n > 0, base["barrel"].fillna(0) / bbe_n, np.nan)

    # SwStr rate
    if "description" in sc.columns:
        sc["is_swstr"] = sc["description"].isin({"swinging_strike","swinging_strike_blocked"}).astype(int)
        p_pitches = sc.groupby("pitcher").size().rename("pitch_count")
        swstr_agg = sc.groupby("pitcher")["is_swstr"].sum().rename("swstr_count")
        swstr_df = pd.concat([p_pitches, swstr_agg], axis=1).reset_index()
        swstr_df["swstr_rate"] = swstr_df["swstr_count"] / swstr_df["pitch_count"]
        base = base.merge(swstr_df[["pitcher","swstr_rate"]], on="pitcher", how="left")
    else:
        base["swstr_rate"] = np.nan

    # K%, BB%
    base["k_pct"] = base["k"] / base["pa"]
    base["bb_pct"] = base["bb"] / base["pa"]

    # xwOBA gap = woba_allowed - xwoba_allowed (positive = pitcher unlucky)
    base["xwoba_gap"] = (base["woba_allowed"] - base["xwoba_allowed"]).round(4)

    # GB pct (from bb_type)
    gb_agg = sc_bbe[sc_bbe["bb_type"] == "ground_ball"].groupby("pitcher").size().rename("gb_count")
    bip_agg2 = sc_bbe.groupby("pitcher").size().rename("bip_count")
    gb_df = pd.concat([gb_agg, bip_agg2], axis=1).fillna(0).reset_index()
    gb_df["gb_pct"] = gb_df["gb_count"] / gb_df["bip_count"]
    base = base.merge(gb_df[["pitcher","gb_pct"]], on="pitcher", how="left")

    # Rename to match production column names
    base.rename(columns={
        "era":    "ERA",
        "fip":    "FIP",
        "babip":  "BABIP_allowed",
        "xera":   "xERA",
        "ip":     "IP",
        "team":   "Team",
        "name":   "name",
    }, inplace=True)

    base["ERA_minus_FIP"]  = (base["ERA"] - base["FIP"]).round(4)
    base["ERA_minus_xERA"] = (base["ERA"] - base["xERA"]).round(4)

    return base


def score_pitchers_production(df: pd.DataFrame, year: int) -> pd.DataFrame:
    """
    Run the full production scoring pipeline (score_pitcher_luck.py v2.0).
    Replicates main() logic including pre-scaling ERA floor gates.
    """
    df = df.copy()

    # ── Team / park factor ───────────────────────────────────────────────────
    df["pitcher"] = df["pitcher"].astype("Int64")
    if "Team" not in df.columns:
        df["Team"] = "UNK"
    df["park_factor"] = df["Team"].map(park_factor_p).fillna(1.0)

    # ── Career BABIP + age adjustment ────────────────────────────────────────
    df["career_babip_allowed"] = df["pitcher"].apply(
        lambda p: _career_babip_p.get(str(int(p))) if pd.notna(p) else None
    )
    df["career_hh_allowed"]    = df["pitcher"].apply(
        lambda p: _career_hh_p.get(int(p)) if pd.notna(p) else None
    )
    df["career_barrel_allowed"] = df["pitcher"].apply(
        lambda p: _career_barrel_p.get(int(p)) if pd.notna(p) else None
    )
    df["babip_baseline"] = df["career_babip_allowed"].fillna(LEAGUE_AVG_BABIP_P)

    _byr = {k: int(v.get("birth_year") or 0) for k, v in _career_stats.items()}
    df["_age_babip"] = df["pitcher"].apply(
        lambda p: year - _byr[int(p)] if pd.notna(p) and int(p) in _byr and _byr[int(p)] > 0 else 0
    )
    df["age_adj_career_babip"] = df.apply(
        lambda r: round(r["babip_baseline"] * _pitcher_babip_age_mult(int(r["_age_babip"])), 4)
        if pd.notna(r["career_babip_allowed"]) and r["_age_babip"] > 0
        else r["babip_baseline"],
        axis=1,
    )
    df["park_adj_babip_expected"] = (df["age_adj_career_babip"] * df["park_factor"]).round(4)

    # ── Build sell and buy component scores ──────────────────────────────────
    component_cols = []

    for col, avg, weight, _label in COMPONENTS_P:
        if col not in df.columns:
            continue
        comp_col = f"_comp_{col}"
        if col == "BABIP_allowed":
            df[comp_col] = (df[col] - df["park_adj_babip_expected"]) * weight
        elif col == "hard_hit_rate_allowed":
            baseline = df["career_hh_allowed"].where(df["career_hh_allowed"].notna(), avg)
            df[comp_col] = (df[col] - baseline) * weight
        elif col == "barrel_rate_allowed":
            baseline = df["career_barrel_allowed"].where(df["career_barrel_allowed"].notna(), avg)
            df[comp_col] = (df[col] - baseline) * weight
        else:
            df[comp_col] = (df[col] - avg) * weight
        component_cols.append(comp_col)

    # HR/FB component
    if "hr_fb_rate" in df.columns:
        hh_col = "hard_hit_rate_allowed" if "hard_hit_rate_allowed" in df.columns else None
        df["_comp_hrfb"] = df.apply(
            lambda r: hrfb_comp_p(r["hr_fb_rate"], r[hh_col] if hh_col else float("nan")),
            axis=1,
        )
        component_cols.append("_comp_hrfb")

    # xwOBA gap component
    if "xwoba_gap" in df.columns:
        df["_comp_xwoba_gap"] = df["xwoba_gap"].fillna(0.0) * 1.5
        component_cols.append("_comp_xwoba_gap")

    # Split scorer
    sell_comp_names = ["_comp_BABIP_allowed", "_comp_lob_pct",
                       "_comp_ERA_minus_FIP", "_comp_ERA_minus_xERA",
                       "_comp_hrfb", "_comp_hard_hit_rate_allowed",
                       "_comp_barrel_rate_allowed", "_comp_swstr_rate"]
    sell_cols = [c for c in sell_comp_names if c in df.columns]
    df["_sell_score"] = df[sell_cols].sum(axis=1)

    df["_buy_era_fip"] = df["ERA_minus_FIP"].fillna(0.0) * 0.60
    df["_buy_xwoba"]   = df["xwoba_gap"].fillna(0.0) * 0.25 if "xwoba_gap" in df.columns else 0.0
    if "park_adj_babip_expected" in df.columns and "BABIP_allowed" in df.columns:
        df["_buy_babip"] = (df["BABIP_allowed"] - df["park_adj_babip_expected"]).fillna(0.0) * 0.15
    else:
        df["_buy_babip"] = 0.0
    df["_buy_score"] = df[["_buy_era_fip", "_buy_xwoba", "_buy_babip"]].sum(axis=1)

    def _split_luck(r):
        ss, bs = r["_sell_score"], r["_buy_score"]
        if ss < 0 and bs > 0:
            return float(r.get("ERA_minus_FIP") or 0.0) * 0.15
        if ss < 0:
            return ss
        if bs > 0:
            return bs
        return 0.0

    df["luck_score"] = df.apply(_split_luck, axis=1)
    df.drop(columns=component_cols + ["_buy_era_fip", "_buy_xwoba", "_buy_babip"], inplace=True)

    # ── Confidence scale by IP ───────────────────────────────────────────────
    df["luck_score"] = df.apply(
        lambda r: round(r["luck_score"] * confidence_scale_ip(r["IP"], SEASON_DAY), 4),
        axis=1,
    )

    # ── Career ip / birth year / age ─────────────────────────────────────────
    df["career_ip"]  = df["pitcher"].apply(lambda p: float((_career_stats.get(int(p)) or {}).get("career_ip") or 0))
    df["birth_year"] = df["pitcher"].apply(lambda p: int((_career_stats.get(int(p)) or {}).get("birth_year") or 0))
    df["age"]        = df["birth_year"].apply(lambda by: year - by if by > 0 else 0)

    # ── FIP- (park-adjusted) ─────────────────────────────────────────────────
    qualified_fip = df[df["IP"] >= 20]["FIP"].dropna() if "FIP" in df.columns else df["FIP"].dropna()
    if len(qualified_fip) == 0 and "FIP" in df.columns:
        qualified_fip = df["FIP"].dropna()
    if len(qualified_fip) > 0:
        league_avg_fip = float(qualified_fip.mean())
        df["fip_minus"] = df.apply(
            lambda r: round((float(r["FIP"]) / league_avg_fip) * (1.0 / r["park_factor"]) * 100, 1)
            if pd.notna(r.get("FIP")) else float("nan"),
            axis=1,
        )
    else:
        df["fip_minus"] = float("nan")

    # ── Quality tier multiplier ──────────────────────────────────────────────
    df["_luck_raw_for_cap"] = df["luck_score"].copy()
    df["luck_score"] = df.apply(
        lambda r: round(r["luck_score"] * _pitcher_quality_tier(
            r["fip_minus"] if not pd.isna(r["fip_minus"]) else float("nan")
        )[0], 4) if r["luck_score"] > 0 else r["luck_score"],
        axis=1,
    )

    # ── RTM integration ──────────────────────────────────────────────────────
    if "FIP" in df.columns and "xERA" in df.columns:
        df["rtm_signal"] = df.apply(
            lambda r: round(float(r["FIP"]) - float(r["xERA"]), 4)
            if pd.notna(r.get("FIP")) and pd.notna(r.get("xERA")) else 0.0,
            axis=1,
        )
    else:
        df["rtm_signal"] = 0.0

    def _combine_pitcher_rtm(row):
        ls, rt = row["luck_score"], row["rtm_signal"]
        combined = ls * 0.75 + (rt * 0.15) * 0.25
        if (ls > 0 and rt < 0) or (ls < 0 and rt > 0):
            combined *= 1.15
        return round(combined, 4)
    df["luck_score"] = df.apply(_combine_pitcher_rtm, axis=1)

    # ── Amplification cap ────────────────────────────────────────────────────
    cap = df.apply(lambda r: amp_cap_p(r["luck_score"], r["_luck_raw_for_cap"]), axis=1)
    df["luck_score"] = cap.apply(lambda t: t[0])
    df.drop(columns=["_luck_raw_for_cap"], inplace=True)

    # ── Pre-scaling verdict with ERA floor gates (production v2.0 logic) ─────
    def _verdict_prescore(row):
        bs  = float(row.get("_buy_score") or 0.0)
        ss  = float(row.get("_sell_score") or 0.0)
        ls  = float(row.get("luck_score") or 0.0)
        ip  = float(row.get("IP") or 0.0)
        era = float(row.get("ERA") or 0.0)
        fip = float(row.get("FIP") or float("nan"))
        xera_raw = row.get("xERA")
        xera = float(xera_raw) if pd.notna(xera_raw) else float("nan")

        if bs > 0 and ss >= 0 and ls > 0:
            dominant_buy = bs >= 1.50
            if ip < MIN_BUY_IP and not dominant_buy:
                return "Neutral"
            if ip < MIN_BUY_IP and not pd.isna(fip) and fip < 1.50:
                return "Neutral"
            if era < 3.50:
                return "Neutral"
            if (not dominant_buy and not pd.isna(xera) and not pd.isna(fip)
                    and abs(fip - xera) > 1.50 and xera > 4.50):
                return "Neutral"
            if bs >= 0.50:
                return "Buy low"
            if bs >= 0.30:
                if era < 4.00:
                    return "Neutral"
                return "Slight buy"
        return assign_verdict_p(ls)

    df["verdict"] = df.apply(_verdict_prescore, axis=1)

    # ── Buy qualification gate ───────────────────────────────────────────────
    df["buy_qualified"] = df.apply(
        lambda r: is_buy_qualified(
            r.get("FIP",       float("nan")),
            r.get("xERA",      float("nan")),
            r.get("swstr_rate",float("nan")),
            r["career_ip"],
            r.get("gb_pct",    float("nan")),
        ) if r["verdict"] in ("Buy low", "Slight buy") else True,
        axis=1,
    )
    disq = ~df["buy_qualified"] & df["verdict"].isin(["Buy low", "Slight buy"])
    if disq.sum():
        print(f"  Buy qualification: {disq.sum()} disqualified → Neutral")
        df.loc[disq, "verdict"] = "Neutral"

    df.drop(columns=["_buy_score", "_sell_score"], inplace=True, errors="ignore")
    return df


_P_OUT_EVENTS = frozenset({
    "field_out","force_out","grounded_into_double_play","double_play",
    "triple_play","fielders_choice_out","strikeout","strikeout_double_play",
    "caught_stealing_2b","caught_stealing_3b","caught_stealing_home",
    "pickoff_1b","pickoff_2b","pickoff_3b",
    "pickoff_caught_stealing_2b","pickoff_caught_stealing_3b","pickoff_caught_stealing_home",
    "other_out",
})
_P_DP_EVENTS = frozenset({
    "grounded_into_double_play","double_play","strikeout_double_play",
})

def _pitcher_outcome_only(sc: pd.DataFrame) -> pd.DataFrame:
    """
    Compute pitcher IP and ERA from the limited outcome parquet
    (only events, post_bat_score, bat_score, game_pk columns guaranteed).
    """
    sc = sc.copy()
    sc["pitcher"] = pd.to_numeric(sc["pitcher"], errors="coerce")
    sc = sc[sc["pitcher"].notna()].copy()
    sc["pitcher"] = sc["pitcher"].astype(int)

    ev = sc[sc["events"].notna() & (sc["events"] != "")].copy()
    ev["is_out"] = ev["events"].isin(_P_OUT_EVENTS).astype(int)
    ev["is_dp"]  = ev["events"].isin(_P_DP_EVENTS).astype(int)

    outs_df = ev.groupby("pitcher").agg(outs=("is_out","sum"), dp=("is_dp","sum")).reset_index()
    outs_df["ip_outcome"] = (outs_df["outs"] + outs_df["dp"]) / 3.0

    # Runs from score delta
    if "post_bat_score" in sc.columns and "bat_score" in sc.columns:
        sc2 = sc[sc["post_bat_score"].notna() & sc["bat_score"].notna()].copy()
        sc2["runs"] = (sc2["post_bat_score"] - sc2["bat_score"]).clip(lower=0)
        runs_df = sc2.groupby("pitcher")["runs"].sum().reset_index(name="runs_allowed")
    else:
        runs_df = outs_df[["pitcher"]].copy()
        runs_df["runs_allowed"] = 0.0

    result = outs_df.merge(runs_df, on="pitcher", how="left")
    result["runs_allowed"] = result["runs_allowed"].fillna(0)
    result["era_outcome"] = np.where(
        result["ip_outcome"] > 0,
        result["runs_allowed"] / result["ip_outcome"] * 9,
        float("nan"),
    )
    return result[["pitcher","ip_outcome","era_outcome"]]


def run_pitcher_year(year: int, name_lut: dict) -> pd.DataFrame | None:
    april_path    = os.path.join(CACHE_DIR, f"pitcher_statcast_april_{year}.parquet")
    outcome_path  = os.path.join(CACHE_DIR, f"pitcher_statcast_mayjuly_{year}.parquet")

    if not os.path.exists(april_path) or not os.path.exists(outcome_path):
        print(f"  {year}: SKIPPED — pitcher cache missing")
        return None

    print(f"\n── PITCHER {year} ─────────────────────────────")
    sc_april  = pq.read_table(april_path).to_pandas()
    sc_outcome= pq.read_table(outcome_path).to_pandas()
    print(f"  April: {len(sc_april):,} rows | Outcome: {len(sc_outcome):,} rows")

    df = _agg_pitchers_from_statcast(sc_april, year)
    df = df[df["IP"] >= MIN_PITCHER_IP].copy()
    print(f"  After IP >= {MIN_PITCHER_IP} filter: {len(df):,} pitchers")

    df = score_pitchers_production(df, year)
    print(f"  Verdict distribution:\n{df['verdict'].value_counts().to_string()}")

    # ── Outcomes (simplified — only IP and ERA needed) ────────────────────────
    outcome_stats = _pitcher_outcome_only(sc_outcome)
    outcome_stats = outcome_stats[outcome_stats["ip_outcome"] >= MIN_OUTCOME_IP]

    merged = df.merge(outcome_stats[["pitcher","era_outcome","ip_outcome"]], on="pitcher", how="inner")
    merged["era_change"] = merged["era_outcome"] - merged["ERA"]

    SIGNAL_MAP = {"Buy low": "IMPROVED", "Slight buy": "IMPROVED",
                  "Sell high": "DECLINED", "Slight sell": "DECLINED"}
    merged["predicted_direction"] = merged["verdict"].map(SIGNAL_MAP).fillna("")
    merged["in_eval"] = merged["verdict"].isin(SIGNAL_MAP)
    eval_df = merged[merged["in_eval"]].copy()
    eval_df["correct"] = eval_df.apply(
        lambda r: (r["predicted_direction"] == "IMPROVED" and r["era_change"] < 0) or
                  (r["predicted_direction"] == "DECLINED" and r["era_change"] > 0),
        axis=1,
    )
    merged = merged.merge(eval_df[["pitcher","correct"]], on="pitcher", how="left")

    rows = []
    for _, r in merged.iterrows():
        pid = int(r["pitcher"])
        rows.append({
            "player_name":         name_lut.get(pid, r.get("name", f"ID_{pid}")),
            "mlbam_id":            pid,
            "year":                year,
            "signal":              r["verdict"],
            "luck_score":          round(float(r["luck_score"]), 4),
            "era_actual":          round(float(r["ERA"]),   2),
            "fip_actual":          round(float(r["FIP"]),   2) if pd.notna(r.get("FIP"))  else None,
            "xera_actual":         round(float(r["xERA"]),  2) if pd.notna(r.get("xERA")) else None,
            "predicted_direction": r["predicted_direction"],
            "actual_era_change":   round(float(r["era_change"]), 2),
            "in_eval":             bool(r["in_eval"]),
            "correct":             bool(r["correct"]) if pd.notna(r.get("correct")) else None,
        })
    result = pd.DataFrame(rows)
    n_eval = int(result["in_eval"].sum())
    n_corr = int(result[result["in_eval"]]["correct"].sum())
    pct = n_corr / n_eval if n_eval > 0 else float("nan")
    print(f"  Eval: {n_eval:>3} pitchers | {n_corr:>3} correct | {pct:.1%}")
    return result


# ══════════════════════════════════════════════════════════════════════════════
# ACCURACY TABLE + MAIN
# ══════════════════════════════════════════════════════════════════════════════

def accuracy_table(df: pd.DataFrame, label: str, tier_order: list):
    print(f"\n{'='*64}")
    print(f"  {label} — ACCURACY TABLE (production scorer)")
    print(f"{'='*64}")
    eval_df = df[df["in_eval"] == True].copy()

    years = sorted(eval_df["year"].unique())
    print(f"{'Signal':<14}", end="")
    for y in years:
        print(f"  {y}", end="")
    print(f"  {'4yr avg':>8}  {'n':>5}")
    print("-" * 62)

    for tier in tier_order:
        sub = eval_df[eval_df["signal"] == tier]
        if len(sub) == 0:
            continue
        print(f"{tier:<14}", end="")
        yr_accs = []
        for y in years:
            s = sub[sub["year"] == y]
            acc = s["correct"].mean() if len(s) > 0 else float("nan")
            yr_accs.append(acc)
            print(f"  {'n/a':>5}" if math.isnan(acc) else f"  {acc:.0%}", end="")
        overall = sub["correct"].mean()
        print(f"  {overall:>7.1%}  {len(sub):>5}")

    print("-" * 62)
    total_acc = eval_df["correct"].mean()
    print(f"{'Overall':<14}", end="")
    for y in years:
        s = eval_df[eval_df["year"] == y]
        acc = s["correct"].mean() if len(s) > 0 else float("nan")
        print(f"  {'n/a':>5}" if math.isnan(acc) else f"  {acc:.0%}", end="")
    print(f"  {total_acc:>7.1%}  {len(eval_df):>5}")


def main():
    print("=" * 64)
    print("  run_backtest_production.py")
    print("  Production scorer backtest — 2022-2025")
    print("=" * 64)

    # Load support data
    print("\nLoading support data...")
    _load_support_data()

    # Name lookup (best-effort)
    name_lut_h: dict = {}
    name_lut_p: dict = {}
    for year in [2022, 2023, 2024, 2025]:
        p = os.path.join(CACHE_DIR, f"pitcher_statcast_april_{year}.parquet")
        if os.path.exists(p):
            sc = pq.read_table(p, columns=["pitcher","player_name"]).to_pandas()
            sc["pitcher"] = pd.to_numeric(sc["pitcher"], errors="coerce")
            for _, r in sc.dropna(subset=["pitcher"]).iterrows():
                name_lut_p[int(r["pitcher"])] = r["player_name"]
    print(f"  Name LUT (pitchers): {len(name_lut_p):,} entries")

    # ── Hitter years ─────────────────────────────────────────────────────────
    print("\n" + "=" * 64)
    print("  HITTER BACKTEST")
    print("=" * 64)
    h_frames = []
    for year in [2022, 2023, 2024, 2025]:
        frame = run_hitter_year(year, name_lut_h)
        if frame is not None:
            h_frames.append(frame)

    if h_frames:
        h_all = pd.concat(h_frames, ignore_index=True)
        accuracy_table(
            h_all, "HITTERS",
            ["Buy low", "Slight buy", "Slight sell", "Sell high"],
        )
        out_h = os.path.join(DATA_DIR, "backtest_audit_hitters_v2.csv")
        h_all.to_csv(out_h, index=False)
        print(f"\n  Saved: {out_h} ({len(h_all):,} rows)")

    # ── Pitcher years ─────────────────────────────────────────────────────────
    print("\n" + "=" * 64)
    print("  PITCHER BACKTEST")
    print("=" * 64)
    p_frames = []
    for year in [2022, 2023, 2024, 2025]:
        frame = run_pitcher_year(year, name_lut_p)
        if frame is not None:
            p_frames.append(frame)

    if p_frames:
        p_all = pd.concat(p_frames, ignore_index=True)
        accuracy_table(
            p_all, "PITCHERS",
            ["Buy low", "Slight buy", "Sell high", "Slight sell"],
        )
        out_p = os.path.join(DATA_DIR, "backtest_audit_pitchers_v2.csv")
        p_all.to_csv(out_p, index=False)
        print(f"\n  Saved: {out_p} ({len(p_all):,} rows)")


if __name__ == "__main__":
    main()
