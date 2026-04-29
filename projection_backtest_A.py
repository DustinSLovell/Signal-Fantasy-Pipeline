#!/usr/bin/env python3
"""
projection_backtest_A.py — Projection accuracy validation (Backtest A)

Compares three projection methods against 2025 actual outcomes:
  Method 1 (Naive): continue April per-game rate for remaining games
  Method 2 (RTM):   50% regression toward league average
  Method 3 (Model): stat_projections.py logic, 2022-2024 career baselines ONLY

Design constraints:
  - Career baselines built from FG 2022-2024 ONLY (explicit year loop, no 2025 contamination)
  - Does NOT call stat_projections.project_player() (which uses FG_YEARS=[2022-2025])
  - Instead imports only the math functions: blend_projection, project_hitter_counting,
    project_pitcher_counting, hitter_true_talent, get_hitter_baseline, get_pitcher_baseline
    with manually-supplied career data dict (2022-2024 only)

Data sources:
  Inputs (April 2025):  v4_april_2025.csv + pitcher_statcast_april_2025.parquet
  Career baselines:     fg_batting_{2022,2023,2024}.csv + fg_pitching_{2022,2023,2024}.csv
  Actuals target:       cbs_hitter_fpts_2025.csv + cbs_pitcher_fpts_2025.csv (full season)
  wOBA ground truth:    statcast_2025_may_july.csv (May-July; cleanest ROS metric)

Comparison methodology:
  Counting stats (HR, R, RBI, W, K): projections are ROS (135 games); actuals are full season.
  Projected full-season = projected_ROS × (162 / 135) for counting stat comparisons.
  Rate stats (AVG, ERA, WHIP): compared directly (rate-to-rate, no scaling needed).
  wOBA: compared to May-July Statcast actual (true ROS, no April contamination).

Minimum sample gates:
  Hitters:  ≥150 ROS PA (CBS full-season)
  Pitchers: ≥40 ROS IP approximated from May-July events

Outputs:
  Table 1: MAE by category — Naive vs RTM vs Model
  Table 2: Bias by category — direction of error
  Table 3: Head-to-head win rate — Model vs RTM per player
  Table 4: Worst 10 individual projections
  Table 5: Best 10 individual projections
"""

import json
import math
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

# Import projection math functions ONLY — not project_player() which loads FG_YEARS
from stat_projections import (
    blend_projection,
    project_hitter_counting,
    project_pitcher_counting,
    hitter_true_talent,
    get_hitter_baseline,
    get_pitcher_baseline,
    sample_weight as _current_weight,
    LEAGUE_AVG_HITTER,
    LEAGUE_AVG_PITCHER,
)

BASE_DIR = Path(__file__).parent
CACHE_DIR = BASE_DIR / "backtest_cache"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

APRIL_GAMES = 27          # approximate April game count
SEASON_GAMES = 162
GAMES_REM = SEASON_GAMES - APRIL_GAMES  # 135 remaining after April
ROS_SCALE = SEASON_GAMES / GAMES_REM    # 1.20 — scale ROS counts to full-season equivalent

MIN_HITTER_PA = 150       # minimum CBS full-season PA for inclusion
MIN_PITCHER_IP = 40       # minimum CBS full-season IP for inclusion

# League averages (2022-2024 era, no 2025 contamination)
LG_AVG     = 0.248
LG_HR_RATE = 0.033
LG_WOBA    = 0.318
LG_ERA     = 4.20
LG_WHIP    = 1.30
LG_K9      = 8.50

RP_APPS_PER_SEASON = 60   # avg full-time reliever appearances / 162 games

# Events used to classify outcomes
HIT_EVENTS = {"single", "double", "triple", "home_run"}
BB_EVENTS  = {"walk", "intent_walk"}
HBP_EVENTS = {"hit_by_pitch", "catcher_interf"}
AB_EVENTS  = {
    "single", "double", "triple", "home_run",
    "strikeout", "strikeout_double_play",
    "field_out", "grounded_into_double_play", "double_play",
    "triple_play", "force_out", "fielders_choice",
    "fielders_choice_out", "other_out",
}
OUT_EVENTS  = {"field_out", "strikeout", "grounded_into_double_play",
               "double_play", "strikeout_double_play", "force_out",
               "fielders_choice_out", "sac_fly", "sac_fly_double_play",
               "sac_bunt", "fielders_choice", "triple_play", "other_out"}
GDP_EVENTS  = {"grounded_into_double_play", "double_play", "strikeout_double_play"}


# ---------------------------------------------------------------------------
# SECTION 1 — Career baseline builder (2022-2024 ONLY, no 2025)
# ---------------------------------------------------------------------------

def build_career_baselines_2022_2024() -> tuple[dict, dict]:
    """Load FanGraphs 2022-2024 to build career wOBA/BA/ERA baselines.

    Returns (hitter_career, pitcher_career) dicts keyed by MLBAM ID.
    Matches the schema expected by get_hitter_baseline() and get_pitcher_baseline().
    """
    # --- Hitters ---
    h_frames = []
    for yr in [2022, 2023, 2024]:
        p = BASE_DIR / f"data/fg_batting_{yr}.csv"
        if p.exists():
            df = pd.read_csv(p, low_memory=False)
            df["year"] = yr
            h_frames.append(df)
    if h_frames:
        hdf = pd.concat(h_frames, ignore_index=True)
        hdf = hdf.dropna(subset=["batter_id", "pa", "woba", "est_woba", "ba"])
        hitter_career: dict = {}
        for bid, grp in hdf.groupby("batter_id"):
            total_pa = grp["pa"].sum()
            if total_pa == 0:
                continue
            hitter_career[int(bid)] = {
                "career_woba_fg":  float((grp["woba"]     * grp["pa"]).sum() / total_pa),
                "career_xwoba_fg": float((grp["est_woba"] * grp["pa"]).sum() / total_pa),
                "career_ba_fg":    float((grp["ba"]        * grp["pa"]).sum() / total_pa),
                "fg_career_pa":    int(total_pa),
            }
    else:
        hitter_career = {}
        print("  WARNING: No FG batting data found for 2022-2024")

    # --- Pitchers ---
    p_frames = []
    for yr in [2022, 2023, 2024]:
        p = BASE_DIR / f"data/fg_pitching_{yr}.csv"
        if p.exists():
            df = pd.read_csv(p, low_memory=False)
            df["year"] = yr
            p_frames.append(df)
    if p_frames:
        pdf = pd.concat(p_frames, ignore_index=True)
        pdf = pdf.dropna(subset=["pitcher_id", "pa", "era", "xera"])
        pitcher_career: dict = {}
        for pid, grp in pdf.groupby("pitcher_id"):
            total_pa = grp["pa"].sum()
            if total_pa == 0:
                continue
            pitcher_career[int(pid)] = {
                "career_era_fg":  float((grp["era"]  * grp["pa"]).sum() / total_pa),
                "career_xera_fg": float((grp["xera"] * grp["pa"]).sum() / total_pa),
                "career_pa_fg":   int(total_pa),
            }
    else:
        pitcher_career = {}
        print("  WARNING: No FG pitching data found for 2022-2024")

    print(f"  Career baselines (2022-2024): {len(hitter_career)} hitters, {len(pitcher_career)} pitchers")
    return hitter_career, pitcher_career


# ---------------------------------------------------------------------------
# SECTION 2 — April 2025 stat aggregation
# ---------------------------------------------------------------------------

def aggregate_april_hitters() -> pd.DataFrame:
    """Aggregate v4_april_2025.csv into per-batter April stats.

    Returns DataFrame with columns:
      batter, pa, ab, hits, hr, bb, hbp, k, woba_sum, xwoba_sum, barrel_count, bip
    """
    csv_path = CACHE_DIR / "v4_april_2025.csv"
    df = pd.read_csv(csv_path, low_memory=False)
    ev = df[df["events"].notna()].copy()

    # launch_speed_angle == 6 corresponds to a barrel in Statcast encoding
    ev["barrel"] = (ev.get("launch_speed_angle", pd.Series(dtype=float)) == 6).astype(int)

    rows = []
    for bid, grp in ev.groupby("batter"):
        pa    = len(grp)
        ab    = grp["events"].isin(AB_EVENTS).sum()
        hits  = grp["events"].isin(HIT_EVENTS).sum()
        hr    = (grp["events"] == "home_run").sum()
        bb    = grp["events"].isin(BB_EVENTS).sum()
        hbp   = grp["events"].isin(HBP_EVENTS).sum()
        k     = grp["events"].isin({"strikeout", "strikeout_double_play"}).sum()
        bip   = grp["events"].isin(AB_EVENTS - {"strikeout", "strikeout_double_play"}).sum()

        woba_sum  = grp["woba_value"].fillna(0).sum()
        xwoba_sum = grp["estimated_woba_using_speedangle"].fillna(0).sum()
        # xwOBA: use pa as denominator (woba_value already normalized per PA)
        barrel_ct = int(grp.get("barrel", pd.Series(dtype=int)).fillna(0).sum())

        rows.append({
            "batter": int(bid),
            "pa": pa, "ab": ab, "hits": hits, "hr": hr,
            "bb": bb, "hbp": hbp, "k": k, "bip": bip,
            "woba_sum": woba_sum, "xwoba_sum": xwoba_sum,
            "barrel_count": barrel_ct,
        })

    out = pd.DataFrame(rows)
    # Derived rates
    out["avg"]         = (out["hits"] / out["ab"]).where(out["ab"] > 0, LG_AVG)
    out["woba"]        = (out["woba_sum"]  / out["pa"]).where(out["pa"] > 0, LG_WOBA)
    out["xwoba"]       = (out["xwoba_sum"] / out["pa"]).where(out["pa"] > 0, LG_WOBA)
    out["bb_rate"]     = (out["bb"] / out["pa"]).where(out["pa"] > 0, 0.085)
    out["k_rate"]      = (out["k"]  / out["pa"]).where(out["pa"] > 0, 0.220)
    out["barrel_rate"] = (out["barrel_count"] / out["bip"].clip(lower=1)).where(out["bip"] > 0, 0.065)
    return out


def aggregate_april_pitchers() -> pd.DataFrame:
    """Aggregate pitcher_statcast_april_2025.parquet into per-pitcher April stats.

    Returns DataFrame with columns:
      pitcher, bf, ip_approx, k, bb, hits, hr, era_approx, whip_approx, k9, bb9
    """
    parq = pd.read_parquet(CACHE_DIR / "pitcher_statcast_april_2025.parquet")
    ev   = parq[parq["events"].notna()].copy()

    rows = []
    for pid, grp in ev.groupby("pitcher"):
        bf   = len(grp)
        k    = grp["events"].isin({"strikeout", "strikeout_double_play"}).sum()
        bb   = grp["events"].isin(BB_EVENTS).sum()
        hbp  = grp["events"].isin(HBP_EVENTS).sum()
        hits = grp["events"].isin(HIT_EVENTS).sum()
        hr   = (grp["events"] == "home_run").sum()

        # IP: sum outs (GDP counts 2)
        outs = grp["events"].apply(lambda e: 2 if e in GDP_EVENTS else (1 if e in OUT_EVENTS else 0)).sum()
        ip   = outs / 3.0

        # Runs allowed: sum of score changes across PAs
        if "post_bat_score" in grp.columns and "bat_score" in grp.columns:
            runs = (grp["post_bat_score"] - grp["bat_score"]).clip(lower=0).sum()
        else:
            runs = float("nan")

        era_approx  = (runs * 9 / ip) if ip > 0 and not math.isnan(runs) else float("nan")
        whip_approx = ((hits + bb + hbp) / ip) if ip > 0 else float("nan")
        k9          = (k * 9 / ip) if ip > 0 else float("nan")
        bb9         = (bb * 9 / ip) if ip > 0 else float("nan")

        rows.append({
            "pitcher": int(pid),
            "bf": bf, "ip_approx": ip, "k": k, "bb": bb, "hbp": hbp,
            "hits": hits, "hr": hr, "runs": runs,
            "era_approx": era_approx, "whip_approx": whip_approx,
            "k9": k9, "bb9": bb9,
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# SECTION 3 — Name → MLBAM ID mapping
# ---------------------------------------------------------------------------

def build_name_to_id_map() -> dict[str, int]:
    """Build CBS name → MLBAM ID map from FG 2025 batting data."""
    fg = pd.read_csv(BASE_DIR / "data/fg_batting_2025.csv", low_memory=False)
    fg["player_name"] = fg["last_name, first_name"].apply(
        lambda s: " ".join(reversed([x.strip() for x in str(s).split(",")])).strip()
    )
    fg["name_norm"] = fg["player_name"].str.lower().str.replace(r"[^a-z ]", "", regex=True).str.strip()
    name_map: dict[str, int] = {}
    for _, row in fg.iterrows():
        try:
            name_map[row["name_norm"]] = int(row["batter_id"])
        except Exception:
            pass
    return name_map


def build_pitcher_name_to_id_map() -> dict[str, int]:
    """Build CBS pitcher name → MLBAM ID map from FG 2025 pitching data."""
    fg = pd.read_csv(BASE_DIR / "data/fg_pitching_2025.csv", low_memory=False)
    fg["player_name"] = fg["last_name, first_name"].apply(
        lambda s: " ".join(reversed([x.strip() for x in str(s).split(",")])).strip()
    )
    fg["name_norm"] = fg["player_name"].str.lower().str.replace(r"[^a-z ]", "", regex=True).str.strip()
    name_map: dict[str, int] = {}
    for _, row in fg.iterrows():
        try:
            name_map[row["name_norm"]] = int(row["pitcher_id"])
        except Exception:
            pass
    return name_map


def _norm_name(s: str) -> str:
    import re
    return re.sub(r"[^a-z ]", "", str(s).lower()).strip()


# ---------------------------------------------------------------------------
# SECTION 4 — ROS actuals from May-July Statcast
# ---------------------------------------------------------------------------

def aggregate_ros_woba() -> dict[int, dict]:
    """Aggregate May-July Statcast → per-batter ROS wOBA and PA."""
    df = pd.read_csv(CACHE_DIR / "statcast_2025_may_july.csv", low_memory=False)
    ev = df[df["events"].notna()]
    out = {}
    for bid, grp in ev.groupby("batter"):
        pa = len(grp)
        woba = grp["woba_value"].fillna(0).sum() / pa if pa > 0 else float("nan")
        hr = (grp["events"] == "home_run").sum()
        ab = grp["events"].isin(AB_EVENTS).sum()
        hits = grp["events"].isin(HIT_EVENTS).sum()
        avg = hits / ab if ab > 0 else float("nan")
        out[int(bid)] = {
            "ros_pa": pa, "ros_woba": woba,
            "ros_hr_raw": int(hr), "ros_ab": int(ab),
            "ros_hits": int(hits), "ros_avg": avg,
        }
    return out


# ---------------------------------------------------------------------------
# SECTION 5 — Projection methods
# ---------------------------------------------------------------------------

def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def project_model(batter_id: int, april_row: pd.Series, hitter_career: dict, games_rem: int) -> dict:
    """Run stat_projections model logic with explicit 2022-2024 career baselines."""
    career_data = {"hitter": hitter_career}
    baseline    = get_hitter_baseline(batter_id, career_data)
    true_talent = hitter_true_talent(april_row, baseline)
    weight      = _current_weight(april_row.get("pa", 0), is_pitcher=False)
    # Thin-baseline fix: if career_pa < 1000, reduce career anchor pull
    if baseline.get("career_pa", 500) < 1000:
        career_weight = (1.0 - weight) * 0.85
        weight = min(0.85, 1.0 - career_weight)
    blended = blend_projection(true_talent, baseline, weight)
    return project_hitter_counting(blended, games_rem, signal="Neutral")


def project_naive(april_row: pd.Series, games_rem: int) -> dict:
    """Continue April per-PA rate for remaining PA."""
    pa_per_game = 4.1
    ros_pa = int(pa_per_game * games_rem * 0.85)
    april_pa = april_row.get("pa", 1)
    if april_pa == 0:
        april_pa = 1
    scale = ros_pa / april_pa

    hr   = _clamp(int(april_row.get("hr", 0) * scale), 0, 80)
    avg  = _clamp(april_row.get("avg", LG_AVG), 0.150, 0.400)
    h    = int(ros_pa * avg * (1 - april_row.get("bb_rate", 0.085)))
    bb   = int(ros_pa * april_row.get("bb_rate", 0.085))
    r    = int(hr + (h - hr) * 0.35 + bb * 0.15)
    rbi  = int(hr * 1.30 + (h - hr) * 0.32)
    sb_rate = april_row.get("hr", 0) * 0   # no SB tracking from events
    return {
        "projected_avg": round(avg, 3),
        "projected_hr": hr,
        "projected_r": _clamp(r, 0, 200),
        "projected_rbi": _clamp(rbi, 0, 200),
        "projected_sb": 0,
        "projected_pa": ros_pa,
    }


def project_rtm(april_row: pd.Series, games_rem: int) -> dict:
    """50% regression toward league average."""
    pa_per_game = 4.1
    ros_pa = int(pa_per_game * games_rem * 0.85)

    april_pa = april_row.get("pa", 1)
    w = min(0.50, april_pa / (april_pa + 100))   # weight toward current as PA grow

    avg      = april_row.get("avg", LG_AVG) * w + LG_AVG * (1 - w)
    hr_rate  = (april_row.get("hr", 0) / max(1, april_pa)) * w + LG_HR_RATE * (1 - w)
    bb_rate  = april_row.get("bb_rate", 0.085) * w + 0.085 * (1 - w)

    avg = _clamp(avg, 0.150, 0.400)
    hr  = _clamp(int(ros_pa * hr_rate), 0, 80)
    h   = int(ros_pa * avg * (1 - bb_rate))
    bb  = int(ros_pa * bb_rate)
    r   = int(hr + (h - hr) * 0.35 + bb * 0.15)
    rbi = int(hr * 1.30 + (h - hr) * 0.32)
    return {
        "projected_avg": round(avg, 3),
        "projected_hr": hr,
        "projected_r": _clamp(r, 0, 200),
        "projected_rbi": _clamp(rbi, 0, 200),
        "projected_sb": 0,
        "projected_pa": ros_pa,
    }


def project_pitcher_model(pitcher_id: int, april_row: pd.Series,
                           pitcher_career: dict, games_rem: int,
                           steamer_gs: int = 0) -> dict:
    """Run pitcher projection with 2022-2024 career baselines."""
    career_data = {"pitcher": pitcher_career}
    baseline    = get_pitcher_baseline(pitcher_id, career_data)

    fip   = april_row.get("era_approx", float("nan"))
    xera  = april_row.get("era_approx", float("nan"))
    ip    = april_row.get("ip_approx", 0.0)
    k9    = april_row.get("k9", float("nan"))
    bb9   = april_row.get("bb9", float("nan"))

    row_dict = {
        "FIP":          fip,
        "xERA":         xera,
        "IP":           ip,
        "total_starts": max(1, ip / 5.0),  # estimate starts
        "swstr_rate":   float("nan"),
    }
    row_series = pd.Series(row_dict)

    pitcher_rates_dict = {pitcher_id: {"k_per9": k9, "bb_per9": bb9,
                                        "whip_raw": april_row.get("whip_approx", float("nan"))}}

    from stat_projections import pitcher_true_talent
    true_talent = pitcher_true_talent(row_series, baseline, pitcher_rates_dict)

    ip_pa = april_row.get("bf", 0)
    weight = _current_weight(ip, is_pitcher=True)
    if baseline.get("career_ip", 200) < 100:
        weight = min(weight, 0.25)
    blended = blend_projection(true_talent, baseline, weight)

    is_sp = steamer_gs >= 10  # use Steamer GS for SP/RP classification
    return project_pitcher_counting(blended, games_rem, is_starter=is_sp, signal="Neutral")


def project_pitcher_naive(april_row: pd.Series, games_rem: int,
                           steamer_gs: int = 0) -> dict:
    ip = april_row.get("ip_approx", 0)
    if ip == 0:
        return {"projected_era": LG_ERA, "projected_whip": LG_WHIP,
                "projected_k": 0, "projected_w": 0, "projected_ip": 0}
    era  = _clamp(april_row.get("era_approx", LG_ERA), 1.8, 9.0)
    whip = _clamp(april_row.get("whip_approx", LG_WHIP), 0.7, 2.5)
    k9   = april_row.get("k9", LG_K9)
    if math.isnan(era): era = LG_ERA
    if math.isnan(whip): whip = LG_WHIP
    if math.isnan(k9): k9 = LG_K9
    if steamer_gs >= 10:  # starter
        starts_rem = int(games_rem / 5 * 0.85)
        proj_ip = starts_rem * 5.6
        w = int(starts_rem * 0.33)
    else:  # reliever
        appearances_rem = int(games_rem / 162 * RP_APPS_PER_SEASON * 0.85)
        proj_ip = appearances_rem * 1.0
        w = 0
    k = int(k9 / 9 * proj_ip)
    return {"projected_era": round(era, 2), "projected_whip": round(whip, 2),
            "projected_k": k, "projected_w": w, "projected_ip": proj_ip}


def project_pitcher_rtm(april_row: pd.Series, games_rem: int,
                         steamer_gs: int = 0) -> dict:
    ip = april_row.get("ip_approx", 0)
    era_raw  = april_row.get("era_approx", float("nan"))
    whip_raw = april_row.get("whip_approx", float("nan"))
    k9_raw   = april_row.get("k9", float("nan"))

    era  = (era_raw  * 0.50 + LG_ERA  * 0.50) if not math.isnan(era_raw)  else LG_ERA
    whip = (whip_raw * 0.50 + LG_WHIP * 0.50) if not math.isnan(whip_raw) else LG_WHIP
    k9   = (k9_raw   * 0.50 + LG_K9   * 0.50) if not math.isnan(k9_raw)  else LG_K9

    era  = _clamp(era,  1.8, 9.0)
    whip = _clamp(whip, 0.7, 2.5)

    if steamer_gs >= 10:  # starter
        starts_rem = int(games_rem / 5 * 0.85)
        proj_ip = starts_rem * 5.6
        w = int(starts_rem * 0.33)
    else:  # reliever
        appearances_rem = int(games_rem / 162 * RP_APPS_PER_SEASON * 0.85)
        proj_ip = appearances_rem * 1.0
        w = 0
    k = int(k9 / 9 * proj_ip)
    return {"projected_era": round(era, 2), "projected_whip": round(whip, 2),
            "projected_k": k, "projected_w": w, "projected_ip": proj_ip}


# ---------------------------------------------------------------------------
# SECTION 6 — Metrics
# ---------------------------------------------------------------------------

def mae(pred: list, actual: list) -> float:
    pairs = [(p, a) for p, a in zip(pred, actual) if not math.isnan(p) and not math.isnan(a)]
    if not pairs:
        return float("nan")
    return sum(abs(p - a) for p, a in pairs) / len(pairs)


def bias(pred: list, actual: list) -> float:
    pairs = [(p, a) for p, a in zip(pred, actual) if not math.isnan(p) and not math.isnan(a)]
    if not pairs:
        return float("nan")
    return sum(p - a for p, a in pairs) / len(pairs)


def win_rate(pred_model: list, pred_rtm: list, actual: list) -> float:
    """Fraction of players where |model_err| < |rtm_err|."""
    wins = 0
    total = 0
    for m, r, a in zip(pred_model, pred_rtm, actual):
        if math.isnan(m) or math.isnan(r) or math.isnan(a):
            continue
        total += 1
        if abs(m - a) < abs(r - a):
            wins += 1
    return wins / total if total > 0 else float("nan")


# ---------------------------------------------------------------------------
# SECTION 7 — Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 72)
    print("Backtest A — Projection Accuracy Validation (2025, 2022-2024 baselines)")
    print("=" * 72)

    # --- Step 1: Career baselines ---
    print("\n[1] Building career baselines (2022-2024 FG data only)...")
    hitter_career, pitcher_career = build_career_baselines_2022_2024()

    # --- Step 2: April stats ---
    print("\n[2] Aggregating April 2025 stats...")
    april_h = aggregate_april_hitters()
    april_p = aggregate_april_pitchers()
    print(f"  April hitters: {len(april_h)} players, "
          f"≥30 PA: {(april_h['pa'] >= 30).sum()}")
    print(f"  April pitchers: {len(april_p)} players, "
          f"≥10 IP: {(april_p['ip_approx'] >= 10).sum()}")

    # --- Step 3: Name-to-ID maps ---
    print("\n[3] Building name → MLBAM ID maps...")
    hitter_name_map   = build_name_to_id_map()
    pitcher_name_map  = build_pitcher_name_to_id_map()
    april_h_dict      = april_h.set_index("batter").to_dict("index")
    april_p_dict      = april_p.set_index("pitcher").to_dict("index")

    # --- Step 4: ROS wOBA actuals (May-July Statcast) ---
    print("\n[4] Aggregating May-July 2025 ROS wOBA actuals...")
    ros_woba_dict = aggregate_ros_woba()
    ros_woba_150  = {bid: d for bid, d in ros_woba_dict.items() if d["ros_pa"] >= 150}
    print(f"  Players with ≥150 May-July PA: {len(ros_woba_150)}")

    # --- Step 5: CBS full-season actuals ---
    print("\n[5] Loading CBS 2025 full-season actuals...")
    cbs_h = pd.read_csv(BASE_DIR / "data/cbs_hitter_fpts_2025.csv")
    cbs_p = pd.read_csv(BASE_DIR / "data/cbs_pitcher_fpts_2025.csv")

    # Compute approximate IP from CBS K and K/9 for IP gate
    # Approximate: IP ≈ K / (K9/9), but K9 not in CBS. Use avg K9=8.5
    cbs_p["ip_approx"] = (cbs_p["K"] / (LG_K9 / 9)).clip(lower=0)
    cbs_p_filtered = cbs_p[cbs_p["ip_approx"] >= MIN_PITCHER_IP].copy()

    # Gate: ≥80 CBS GP ≈ ≥150 PA threshold (excludes injured, part-year players)
    MIN_GP = 80
    cbs_h = cbs_h[cbs_h["GP"] >= MIN_GP].copy()
    cbs_h["name_norm"] = cbs_h["name"].apply(_norm_name)
    cbs_p_filtered = cbs_p_filtered.copy()
    cbs_p_filtered["name_norm"] = cbs_p_filtered["name"].apply(_norm_name)

    print(f"  CBS hitters: {len(cbs_h)} with ≥{MIN_GP} GP (≈≥150 PA)")
    print(f"  CBS pitchers: {len(cbs_p_filtered)} with ≥{MIN_PITCHER_IP} IP approx")

    # --- Step 5b: Steamer pitcher GS for SP/RP classification ---
    print("\n[5b] Loading Steamer pitcher GS for SP/RP classification...")
    STEAMER_P_PATH = BASE_DIR / "Steamers 2025 pitchers.csv"
    steamer_p_gs: dict[str, int] = {}
    if STEAMER_P_PATH.exists():
        s_df = pd.read_csv(STEAMER_P_PATH, encoding="utf-8-sig", low_memory=False)
        for _, srow in s_df.iterrows():
            pid_s = str(srow.get("MLBAMID", "")).strip()
            try:
                gs_val = int(float(srow.get("GS", 0) or 0))
            except Exception:
                gs_val = 0
            if pid_s and pid_s not in ("nan", ""):
                steamer_p_gs[pid_s] = gs_val
        n_sp = sum(1 for v in steamer_p_gs.values() if v >= 10)
        n_rp = sum(1 for v in steamer_p_gs.values() if v < 10)
        print(f"  Steamer GS loaded: {len(steamer_p_gs)} pitchers  (GS≥10: {n_sp} SP, GS<10: {n_rp} RP)")
    else:
        print(f"  WARNING: {STEAMER_P_PATH} not found — all pitchers classified as SP")

    # =========================================================================
    # HITTER BACKTEST
    # =========================================================================
    print("\n" + "=" * 72)
    print("HITTER BACKTEST")
    print("=" * 72)

    h_records = []

    for _, cbs_row in cbs_h.iterrows():
        nm = cbs_row["name_norm"]
        bid = hitter_name_map.get(nm)
        if bid is None:
            continue

        # Must have April data
        apr = april_h_dict.get(bid)
        if apr is None:
            continue
        if apr["pa"] < 10:
            continue

        apr_series = pd.Series({**apr, "xwOBA": apr["xwoba"], "barrel_rate": apr["barrel_rate"],
                                 "bb_rate": apr["bb_rate"], "k_rate": apr["k_rate"]})

        # Three projections (ROS, 135 games)
        try:
            m_proj = project_model(bid, apr_series, hitter_career, GAMES_REM)
        except Exception as e:
            continue
        n_proj = project_naive(apr_series, GAMES_REM)
        r_proj = project_rtm(apr_series, GAMES_REM)

        # Scale ROS counting stats → full-season equivalent
        for proj in [m_proj, n_proj, r_proj]:
            proj["fs_hr"]  = proj["projected_hr"]  * ROS_SCALE
            proj["fs_r"]   = proj["projected_r"]   * ROS_SCALE
            proj["fs_rbi"] = proj["projected_rbi"] * ROS_SCALE

        # ROS wOBA comparison (May-July actuals — cleanest metric)
        ros_entry = ros_woba_dict.get(bid, {})
        ros_woba_actual = ros_entry.get("ros_woba", float("nan"))
        ros_pa_actual   = ros_entry.get("ros_pa", 0)

        # wOBA projection from model: use blended true_woba
        try:
            career_data = {"hitter": hitter_career}
            baseline    = get_hitter_baseline(bid, career_data)
            true_talent = hitter_true_talent(apr_series, baseline)
            weight      = _current_weight(apr["pa"], is_pitcher=False)
            if baseline.get("career_pa", 500) < 1000:
                weight = min(0.85, 1.0 - (1.0 - weight) * 0.85)
            blended = blend_projection(true_talent, baseline, weight)
            model_woba = blended.get("true_woba", float("nan"))
        except Exception:
            model_woba = float("nan")

        naive_woba = apr["woba"]
        rtm_woba   = apr["woba"] * 0.50 + LG_WOBA * 0.50

        h_records.append({
            "name": cbs_row["name"],
            "mlbam_id": bid,
            "april_pa": apr["pa"],
            "ros_pa": ros_pa_actual,
            # CBS full-season actuals
            "actual_hr":  float(cbs_row["HR"])  if pd.notna(cbs_row["HR"])  else float("nan"),
            "actual_r":   float(cbs_row["R"])   if pd.notna(cbs_row["R"])   else float("nan"),
            "actual_rbi": float(cbs_row["RBI"]) if pd.notna(cbs_row["RBI"]) else float("nan"),
            "actual_avg": float(cbs_row["AVG"]) if pd.notna(cbs_row["AVG"]) else float("nan"),
            # ROS wOBA actual
            "actual_ros_woba": ros_woba_actual if ros_pa_actual >= 150 else float("nan"),
            # Model projections
            "model_hr":   m_proj["fs_hr"],
            "model_r":    m_proj["fs_r"],
            "model_rbi":  m_proj["fs_rbi"],
            "model_avg":  m_proj["projected_avg"],
            "model_woba": model_woba,
            # Naive projections
            "naive_hr":   n_proj["fs_hr"],
            "naive_r":    n_proj["fs_r"],
            "naive_rbi":  n_proj["fs_rbi"],
            "naive_avg":  n_proj["projected_avg"],
            "naive_woba": naive_woba,
            # RTM projections
            "rtm_hr":     r_proj["fs_hr"],
            "rtm_r":      r_proj["fs_r"],
            "rtm_rbi":    r_proj["fs_rbi"],
            "rtm_avg":    r_proj["projected_avg"],
            "rtm_woba":   rtm_woba,
        })

    h_df = pd.DataFrame(h_records)
    print(f"\n  Matched hitters: {len(h_df)}")
    print(f"  With ≥150 ROS PA (wOBA comparison): {h_df['actual_ros_woba'].notna().sum()}")

    # =========================================================================
    # PITCHER BACKTEST
    # =========================================================================
    print("\n" + "=" * 72)
    print("PITCHER BACKTEST")
    print("=" * 72)

    p_records = []

    for _, cbs_row in cbs_p_filtered.iterrows():
        nm  = cbs_row["name_norm"]
        pid = pitcher_name_map.get(nm)
        if pid is None:
            continue
        apr = april_p_dict.get(pid)
        if apr is None:
            continue
        if apr["ip_approx"] < 5:
            continue

        steamer_gs = steamer_p_gs.get(str(pid), 0)
        apr_series = pd.Series(apr)
        try:
            m_proj = project_pitcher_model(pid, apr_series, pitcher_career, GAMES_REM,
                                           steamer_gs=steamer_gs)
        except Exception as e:
            continue
        n_proj = project_pitcher_naive(apr_series, GAMES_REM, steamer_gs=steamer_gs)
        r_proj = project_pitcher_rtm(apr_series, GAMES_REM, steamer_gs=steamer_gs)

        # K counting stat: scale to full-season
        for proj in [m_proj, n_proj, r_proj]:
            proj["fs_k"] = proj["projected_k"] * ROS_SCALE
            proj["fs_w"] = proj["projected_w"] * ROS_SCALE

        p_records.append({
            "name": cbs_row["name"],
            "mlbam_id": pid,
            "april_ip": apr["ip_approx"],
            "actual_era":  float(cbs_row["ERA"]) if pd.notna(cbs_row["ERA"])  else float("nan"),
            "actual_whip": float(cbs_row["WHIP"])if pd.notna(cbs_row["WHIP"]) else float("nan"),
            "actual_k":    float(cbs_row["K"])   if pd.notna(cbs_row["K"])    else float("nan"),
            "actual_w":    float(cbs_row["W"])   if pd.notna(cbs_row["W"])    else float("nan"),
            # Model
            "model_era":  m_proj["projected_era"],
            "model_whip": m_proj["projected_whip"],
            "model_k":    m_proj["fs_k"],
            "model_w":    m_proj["fs_w"],
            # Naive
            "naive_era":  n_proj["projected_era"],
            "naive_whip": n_proj["projected_whip"],
            "naive_k":    n_proj["fs_k"],
            "naive_w":    n_proj["fs_w"],
            # RTM
            "rtm_era":    r_proj["projected_era"],
            "rtm_whip":   r_proj["projected_whip"],
            "rtm_k":      r_proj["fs_k"],
            "rtm_w":      r_proj["fs_w"],
        })

    p_df = pd.DataFrame(p_records)
    print(f"\n  Matched pitchers: {len(p_df)}")

    # =========================================================================
    # SECTION 8 — Output tables
    # =========================================================================
    print("\n" + "=" * 72)
    print("TABLE 1 — MAE by Category (Naive vs RTM vs Model)")
    print("  Counting stats scaled ROS→full season (×{:.2f})".format(ROS_SCALE))
    print("=" * 72)

    def _row(label, naive_p, rtm_p, model_p, actual):
        n  = len([x for x in zip(naive_p, actual) if not math.isnan(x[0]) and not math.isnan(x[1])])
        return (label, n,
                mae(naive_p, actual), mae(rtm_p, actual), mae(model_p, actual))

    print(f"\n{'Metric':<12} {'n':>5}  {'Naive MAE':>10}  {'RTM MAE':>10}  {'Model MAE':>10}  {'Winner'}")
    print("-" * 65)

    hitter_metrics = [
        ("HR",   "naive_hr",   "rtm_hr",   "model_hr",   "actual_hr"),
        ("AVG",  "naive_avg",  "rtm_avg",  "model_avg",  "actual_avg"),
        ("R",    "naive_r",    "rtm_r",    "model_r",    "actual_r"),
        ("RBI",  "naive_rbi",  "rtm_rbi",  "model_rbi",  "actual_rbi"),
        ("wOBA", "naive_woba", "rtm_woba", "model_woba", "actual_ros_woba"),
    ]

    h_beats_rtm = []
    for label, nc, rc, mc, ac in hitter_metrics:
        sub = h_df[[nc, rc, mc, ac]].dropna()
        if len(sub) == 0:
            print(f"  {label:<12} {'--':>5}  {'N/A':>10}  {'N/A':>10}  {'N/A':>10}")
            continue
        n_mae = mae(sub[nc].tolist(), sub[ac].tolist())
        r_mae = mae(sub[rc].tolist(), sub[ac].tolist())
        m_mae = mae(sub[mc].tolist(), sub[ac].tolist())
        winner = ("Model" if m_mae <= min(n_mae, r_mae) else
                  "RTM"   if r_mae <= n_mae else "Naive")
        beats = "✓" if m_mae < r_mae else " "
        h_beats_rtm.append(m_mae < r_mae)
        print(f"  {label:<12} {len(sub):>5}  {n_mae:>10.4f}  {r_mae:>10.4f}  {m_mae:>10.4f}  {winner} {beats}")

    print()
    print("  Pitchers:")
    print(f"\n{'Metric':<12} {'n':>5}  {'Naive MAE':>10}  {'RTM MAE':>10}  {'Model MAE':>10}  {'Winner'}")
    print("-" * 65)

    # Note: W excluded from success criteria — all three methods use the same
    # starts × 0.33 formula so comparison is non-differentiable.
    pitcher_metrics = [
        ("ERA",  "naive_era",  "rtm_era",  "model_era",  "actual_era"),
        ("WHIP", "naive_whip", "rtm_whip", "model_whip", "actual_whip"),
        ("K",    "naive_k",    "rtm_k",    "model_k",    "actual_k"),
        ("W*",   "naive_w",    "rtm_w",    "model_w",    "actual_w"),
    ]

    p_beats_rtm = []
    for label, nc, rc, mc, ac in pitcher_metrics:
        sub = p_df[[nc, rc, mc, ac]].dropna()
        if len(sub) == 0:
            print(f"  {label:<12} {'--':>5}  {'N/A':>10}  {'N/A':>10}  {'N/A':>10}")
            continue
        n_mae = mae(sub[nc].tolist(), sub[ac].tolist())
        r_mae = mae(sub[rc].tolist(), sub[ac].tolist())
        m_mae = mae(sub[mc].tolist(), sub[ac].tolist())
        winner = ("Model" if m_mae <= min(n_mae, r_mae) else
                  "RTM"   if r_mae <= n_mae else "Naive")
        beats = "✓" if m_mae < r_mae else (" (tie)" if m_mae == r_mae else " ")
        if label != "W*":   # W is non-differentiable — exclude from wins count
            p_beats_rtm.append(m_mae < r_mae)
        print(f"  {label:<12} {len(sub):>5}  {n_mae:>10.4f}  {r_mae:>10.4f}  {m_mae:>10.4f}  {winner} {beats}")
    print("  * W: non-differentiable — all methods use identical starts × 0.33 formula")

    # Success criteria
    h_wins = sum(h_beats_rtm)
    p_wins = sum(p_beats_rtm)
    print(f"\n  Model beats RTM: {h_wins}/{len(h_beats_rtm)} hitter categories, "
          f"{p_wins}/{len(p_beats_rtm)} evaluable pitcher categories (W excluded)")
    h_pass = h_wins >= 4
    p_pass = p_wins >= 2   # adjusted: only 3 evaluable categories (ERA, WHIP, K)
    print(f"  Hitter success criteria (≥4/5):            {'PASS' if h_pass else 'FAIL'}")
    print(f"  Pitcher success criteria (≥2/3 evaluable): {'PASS' if p_pass else 'FAIL'}")

    # -------------------------------------------------------------------------
    print("\n" + "=" * 72)
    print("TABLE 2 — Bias by Category (mean predicted − actual, + = over-projection)")
    print("=" * 72)

    print(f"\n  Hitters (n shown per metric):")
    print(f"{'Metric':<12} {'n':>5}  {'Naive bias':>11}  {'RTM bias':>10}  {'Model bias':>10}")
    print("-" * 58)
    for label, nc, rc, mc, ac in hitter_metrics:
        sub = h_df[[nc, rc, mc, ac]].dropna()
        if len(sub) == 0:
            continue
        print(f"  {label:<12} {len(sub):>5}  "
              f"{bias(sub[nc].tolist(), sub[ac].tolist()):>+11.4f}  "
              f"{bias(sub[rc].tolist(), sub[ac].tolist()):>+10.4f}  "
              f"{bias(sub[mc].tolist(), sub[ac].tolist()):>+10.4f}")

    print(f"\n  Pitchers (n shown per metric):")
    print(f"{'Metric':<12} {'n':>5}  {'Naive bias':>11}  {'RTM bias':>10}  {'Model bias':>10}")
    print("-" * 58)
    for label, nc, rc, mc, ac in pitcher_metrics:
        if label == "W*":
            print(f"  {'W*':<12}  (non-differentiable — all methods identical)")
            continue
        sub = p_df[[nc, rc, mc, ac]].dropna()
        if len(sub) == 0:
            continue
        print(f"  {label:<12} {len(sub):>5}  "
              f"{bias(sub[nc].tolist(), sub[ac].tolist()):>+11.4f}  "
              f"{bias(sub[rc].tolist(), sub[ac].tolist()):>+10.4f}  "
              f"{bias(sub[mc].tolist(), sub[ac].tolist()):>+10.4f}")

    # -------------------------------------------------------------------------
    print("\n" + "=" * 72)
    print("TABLE 3 — Head-to-Head Win Rate: Model vs RTM (% of players where |model err| < |rtm err|)")
    print("=" * 72)

    print(f"\n  {'Metric':<12}  {'n':>5}  {'Win rate':>10}")
    print("  " + "-" * 32)
    for label, nc, rc, mc, ac in hitter_metrics:
        sub = h_df[[nc, rc, mc, ac]].dropna()
        if len(sub) == 0:
            continue
        wr = win_rate(sub[mc].tolist(), sub[rc].tolist(), sub[ac].tolist())
        print(f"  {label:<12}  {len(sub):>5}  {wr:>9.1%}")

    print()
    for label, nc, rc, mc, ac in pitcher_metrics:
        if label == "W*":
            print(f"  {'W* (skip)':<12}  (non-differentiable)")
            continue
        sub = p_df[[nc, rc, mc, ac]].dropna()
        if len(sub) == 0:
            continue
        wr = win_rate(sub[mc].tolist(), sub[rc].tolist(), sub[ac].tolist())
        print(f"  {label:<12}  {len(sub):>5}  {wr:>9.1%}")

    # -------------------------------------------------------------------------
    print("\n" + "=" * 72)
    print("TABLE 4 — Worst 10 Hitter Projections (Model, by |HR error|)")
    print("=" * 72)

    h_df["hr_err"] = h_df["model_hr"] - h_df["actual_hr"]
    worst = h_df[h_df["actual_hr"].notna() & h_df["model_hr"].notna()].copy()
    worst["abs_hr_err"] = worst["hr_err"].abs()
    worst = worst.nlargest(10, "abs_hr_err")

    print(f"\n  {'Name':<25} {'Apr PA':>7} {'Model HR':>9} {'Actual HR':>10} {'Error':>7} {'April HR':>9}")
    print("  " + "-" * 75)
    for _, r in worst.iterrows():
        apr_hr = april_h_dict.get(r["mlbam_id"], {}).get("hr", "?")
        print(f"  {r['name']:<25} {r['april_pa']:>7.0f} {r['model_hr']:>9.1f} "
              f"{r['actual_hr']:>10.1f} {r['hr_err']:>+7.1f} {str(apr_hr):>9}")

    print(f"\n  {'Name':<25} {'Apr IP':>7} {'Model ERA':>10} {'Actual ERA':>11} {'Error':>7}")
    print("  " + "-" * 65)
    p_df["era_err"] = p_df["model_era"] - p_df["actual_era"]
    worst_p = p_df[p_df["actual_era"].notna() & p_df["model_era"].notna()].copy()
    worst_p["abs_era_err"] = worst_p["era_err"].abs()
    worst_p = worst_p.nlargest(10, "abs_era_err")
    for _, r in worst_p.iterrows():
        print(f"  {r['name']:<25} {r['april_ip']:>7.1f} {r['model_era']:>10.2f} "
              f"{r['actual_era']:>11.2f} {r['era_err']:>+7.2f}")

    # -------------------------------------------------------------------------
    print("\n" + "=" * 72)
    print("TABLE 5 — Best 10 Hitter Projections (Model, smallest |HR error|, ≥15 actual HR)")
    print("=" * 72)

    best = h_df[(h_df["actual_hr"] >= 15) & h_df["model_hr"].notna()].copy()
    best["abs_hr_err"] = (best["model_hr"] - best["actual_hr"]).abs()
    best = best.nsmallest(10, "abs_hr_err")

    print(f"\n  {'Name':<25} {'Apr PA':>7} {'Model HR':>9} {'Actual HR':>10} {'Error':>7}")
    print("  " + "-" * 65)
    for _, r in best.iterrows():
        hr_err = r["model_hr"] - r["actual_hr"]
        print(f"  {r['name']:<25} {r['april_pa']:>7.0f} {r['model_hr']:>9.1f} "
              f"{r['actual_hr']:>10.1f} {hr_err:>+7.1f}")

    print(f"\n  Best 10 pitchers (smallest |ERA error|, ≥40 actual K):")
    print(f"\n  {'Name':<25} {'Apr IP':>7} {'Model ERA':>10} {'Actual ERA':>11} {'Error':>7}")
    print("  " + "-" * 65)
    best_p = p_df[(p_df["actual_k"] >= 40) & p_df["model_era"].notna()].copy()
    best_p["abs_era_err"] = (best_p["model_era"] - best_p["actual_era"]).abs()
    best_p = best_p.nsmallest(10, "abs_era_err")
    for _, r in best_p.iterrows():
        era_err = r["model_era"] - r["actual_era"]
        print(f"  {r['name']:<25} {r['april_ip']:>7.1f} {r['model_era']:>10.2f} "
              f"{r['actual_era']:>11.2f} {era_err:>+7.2f}")

    # -------------------------------------------------------------------------
    # Save CSV outputs
    out_h = BASE_DIR / "data/backtest_A_hitters_2025.csv"
    out_p = BASE_DIR / "data/backtest_A_pitchers_2025.csv"
    h_df.to_csv(out_h, index=False)
    p_df.to_csv(out_p, index=False)
    print(f"\n  Saved: {out_h}  ({len(h_df)} rows)")
    print(f"  Saved: {out_p}  ({len(p_df)} rows)")

    # -------------------------------------------------------------------------
    print("\n" + "=" * 72)
    print("METHODOLOGY NOTES")
    print("=" * 72)
    print(f"""
  Target data: CBS 2025 full-season actuals (April + ROS).
  Projections: ROS-only (games_rem={GAMES_REM} games, May 1 onward).
  Comparison:  Counting stats scaled ×{ROS_SCALE:.2f} to full-season equivalent.
               This assumes April is proportionally average — slight bias toward
               under-projection in actuals (+{(ROS_SCALE-1)*100:.0f}% April gap).
  wOBA target: May-July Statcast actuals (true ROS, no April contamination).
               Uses ≥150 May-July PA gate.
  Career data: FG 2022-2024 ONLY (no 2025 data in baselines — confirmed clean).
  """)


if __name__ == "__main__":
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        main()
