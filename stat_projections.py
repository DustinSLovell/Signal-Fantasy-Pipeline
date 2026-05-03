"""
stat_projections.py
Stat translation and projection engine for Signal Fantasy trade analyzer.

Importable module — no code runs at import time.
All data loading is lazy (called explicitly or on first use of project_player/compare_trade).

Public API:
  load_all_career_data()                   -> dict  (call once, pass to project_player)
  get_hitter_baseline(batter_id, career)   -> dict
  get_pitcher_baseline(pitcher_id, career) -> dict
  hitter_true_talent(row, baseline)        -> dict
  pitcher_true_talent(row, baseline)       -> dict
  sample_weight(pa_or_ip, is_pitcher)      -> float
  blend_projection(current, hist, weight)  -> dict
  project_hitter_counting(blended, games)  -> dict
  project_pitcher_counting(blended, games) -> dict
  project_player(name, h_df, p_df, career) -> dict
  compare_trade(giving, getting, dropping) -> dict
"""

import csv
import json
import math
import re
import unicodedata
from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd

try:
    from lineup_context import compute_lineup_multipliers as _compute_lineup_mult
except Exception:
    def _compute_lineup_mult(mlbam_id: int, team: str) -> tuple:
        return 1.0, 1.0

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR         = Path(__file__).parent
HITTER_CSV       = BASE_DIR / "luck_scores.csv"
PITCHER_CSV      = BASE_DIR / "pitcher_luck_scores.csv"
STATCAST_CSV     = BASE_DIR / "pitchers_statcast.csv"
SPRINT_JSON      = BASE_DIR / "data" / "hitter_career_sprint.json"
CAREER_JSON      = BASE_DIR / "data" / "career_stats.json"
CAREER_MIX_JSON  = BASE_DIR / "data" / "pitcher_career_pitch_mix.json"
CURRENT_MIX_JSON = BASE_DIR / "data" / "pitcher_current_pitch_mix.json"
STEAMER_BAT_CSV  = BASE_DIR / "Steamers 2025 batters.csv"
STEAMER_PIT_CSV  = BASE_DIR / "Steamers 2025 pitchers.csv"
OWNERSHIP_CSV    = BASE_DIR / "data" / "player_ownership_2026.csv"
HS_STATCAST_CSV  = BASE_DIR / "hitters_statcast.csv"

FG_BAT_GLOB   = "data/fg_batting_{year}.csv"
FG_PITCH_GLOB = "data/fg_pitching_{year}.csv"
FG_YEARS      = [2022, 2023, 2024, 2025]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SEASON_END_2026   = date(2026, 10, 1)
BARREL_TO_HR      = 0.42
SWSTR_TO_K9       = 77.3   # swstr_rate is decimal (0.110 = 11%); 0.110 × 77.3 ≈ 8.5 K/9
WHIP_ERA_SLOPE    = 0.20
WHIP_ERA_INTERCEPT = 0.55
FIP_CONST         = 3.10    # standard FIP constant
LG_H9             = 8.8     # league avg H/9 (2022-2024 era)
LG_BB9            = 3.1     # league avg BB/9 (2022-2024 era)
CAREER_BA_WEIGHT  = 0.65    # AVG blend: career BA anchor weight
APRIL_AVG_WEIGHT  = 0.35    # AVG blend: xwOBA-derived current-season weight
MIN_CAREER_PA_BA  = 200     # minimum career PA before trusting career_ba anchor

# Luck signal multipliers — applied after all blending to inject signal into counts
LUCK_MULTIPLIERS: dict = {
    "Buy low":    {"avg": 1.06, "hr": 1.08, "sb": 1.05},
    "Slight buy": {"avg": 1.03, "hr": 1.04, "sb": 1.02},
    "Neutral":    {"avg": 1.00, "hr": 1.00, "sb": 1.00},
    "Slight sell":{"avg": 0.97, "hr": 0.96, "sb": 0.98},
    "Sell high":  {"avg": 0.94, "hr": 0.92, "sb": 0.95},
}
PITCHER_LUCK_MULTIPLIERS: dict = {
    "Buy low":    {"era": 0.92, "whip": 0.95, "k": 1.05},
    "Slight buy": {"era": 0.96, "whip": 0.98, "k": 1.02},
    "Neutral":    {"era": 1.00, "whip": 1.00, "k": 1.00},
    "Slight sell":{"era": 1.04, "whip": 1.02, "k": 0.98},
    "Sell high":  {"era": 1.08, "whip": 1.05, "k": 0.95},
}

LEAGUE_AVG_HITTER = {
    "career_avg":     0.248,
    "career_hr_rate": 0.033,
    "career_sb_rate": 0.0,
    "career_bb_pct":  0.085,
    "career_k_pct":   0.220,
    "career_woba":    0.318,
    "career_pa":      500,
    "n_seasons":      1,
}
LEAGUE_AVG_PITCHER = {
    "career_era":          4.20,
    "career_whip":         1.30,
    "career_k_per9":       8.50,
    "career_bb_per9":      3.00,
    "career_hr9":          1.20,
    "career_ip_per_start": 5.60,
    "career_ip":           200.0,
    "n_seasons":           1,
}

# Park factor table — mirrors score_luck.py PARK_FACTORS (3-year FanGraphs, all 30 teams).
# Used to adjust proj_hr/avg/r/rbi for players who changed parks.
# Keep in sync with score_luck.py when updating park factors.
PARK_FACTORS_PROJ = {
    "COL": 1.18, "CIN": 1.08, "PHI": 1.06, "BOS": 1.05, "TEX": 1.05,
    "AZ":  1.02, "BAL": 1.01,
    "ATL": 1.00, "CHC": 1.00, "LAD": 1.00, "NYY": 1.00, "STL": 1.00,
    "MIL": 0.99, "HOU": 0.99, "DET": 0.99,
    "CLE": 0.98, "MIN": 0.98, "PIT": 0.98, "CWS": 0.98, "WSH": 0.98,
    "SEA": 0.97, "SD":  0.97, "LAA": 0.97, "KC":  0.97, "TOR": 0.97,
    "MIA": 0.95, "NYM": 0.95, "ATH": 0.96, "OAK": 0.96,
    "TB":  0.94, "SF":  0.91,
}
_PF_ADJ_THRESHOLD = 0.02   # minimum |pf_delta| before applying adjustment

# Module-level lazy cache (populated on first call to _get_cache)
_CACHE: dict = {}

# Playing-time module lookups (populated on first call to _blend_pa / _blend_ip)
_STEAMER_PA:  dict = {}   # str(mlbam_id) → full-season PA float
_STEAMER_G:   dict = {}   # str(mlbam_id) → full-season G float (for stale-projection detection)
_STEAMER_IP:  dict = {}   # str(mlbam_id) → {"IP": float, "GS": float}
_IL_STATUS:   dict = {}   # int(mlbam_id) → "ACTIVE" | "INJURY_RESERVE" | "DAY_TO_DAY"
_HITTER_GP:   dict = {}   # int(batter_id) → games_played (unique game_pk count)
_PT_LOADED:   bool = False
# Side-effect flag: set True for any player where _blend_pa fires the stale-Steamer override.
# Consumed by project_player() to tag the steamer_pt_override column.
_STEAMER_PT_OVERRIDE_FLAGS: dict = {}  # int(mlbam_id) → True

# ---------------------------------------------------------------------------
# Name normalisation (mirrors trade_analyzer.py)
# ---------------------------------------------------------------------------

def _norm(s: str) -> str:
    try:
        s = str(s).encode("latin1").decode("utf-8")
    except Exception:
        pass
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z ]", "", s.lower()).strip()


def _fuzzy_find(name_input: str, df: pd.DataFrame) -> pd.DataFrame:
    query = _norm(name_input)
    exact = df[df["_norm"] == query]
    if not exact.empty:
        return exact
    words = query.split()
    mask = df["_norm"].apply(lambda n: all(w in n for w in words))
    return df[mask]


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------

def _load_fg_batting_career() -> dict:
    """Build career wOBA/BA/xwOBA from multi-year FanGraphs batting data.
    Returns {batter_mlbam_id: {career_woba_fg, career_xwoba_fg, career_ba_fg, fg_career_pa}}
    """
    frames = []
    for yr in FG_YEARS:
        path = BASE_DIR / FG_BAT_GLOB.format(year=yr)
        if path.exists():
            frames.append(pd.read_csv(path))
    if not frames:
        return {}
    fg = pd.concat(frames, ignore_index=True)
    fg = fg.dropna(subset=["batter_id", "pa", "woba", "est_woba", "ba"])

    result = {}
    for bid, grp in fg.groupby("batter_id"):
        total_pa = grp["pa"].sum()
        if total_pa < 1:
            continue
        result[int(bid)] = {
            "career_woba_fg":  float((grp["woba"]  * grp["pa"]).sum() / total_pa),
            "career_xwoba_fg": float((grp["est_woba"] * grp["pa"]).sum() / total_pa),
            "career_ba_fg":    float((grp["ba"]    * grp["pa"]).sum() / total_pa),
            "fg_career_pa":    int(total_pa),
        }
    return result


def _load_fg_pitching_career() -> dict:
    """Build career ERA/xERA from multi-year FanGraphs pitching data.
    Returns {pitcher_mlbam_id: {career_era_fg, career_xera_fg, career_pa_fg}}
    """
    frames = []
    for yr in FG_YEARS:
        path = BASE_DIR / FG_PITCH_GLOB.format(year=yr)
        if path.exists():
            frames.append(pd.read_csv(path))
    if not frames:
        return {}
    fg = pd.concat(frames, ignore_index=True)
    fg = fg.dropna(subset=["pitcher_id", "pa", "era", "xera"])

    result = {}
    for pid, grp in fg.groupby("pitcher_id"):
        total_pa = grp["pa"].sum()
        if total_pa < 1:
            continue
        result[int(pid)] = {
            "career_era_fg":  float((grp["era"]  * grp["pa"]).sum() / total_pa),
            "career_xera_fg": float((grp["xera"] * grp["pa"]).sum() / total_pa),
            "career_pa_fg":   int(total_pa),
        }
    return result


def _load_statcast_pitcher_rates() -> dict:
    """Compute K/9, BB/9, WHIP from Statcast pitch-by-pitch data.
    Returns {pitcher_mlbam_id: {k_per9, bb_per9, whip_raw}}
    """
    if not STATCAST_CSV.exists():
        return {}
    sc = pd.read_csv(STATCAST_CSV, usecols=["pitcher", "events"])
    pa_events = {
        "strikeout", "strikeout_double_play", "walk", "intent_walk",
        "field_out", "single", "double", "triple", "home_run",
        "force_out", "grounded_into_double_play", "hit_by_pitch",
        "sac_fly", "sac_bunt", "field_error", "fielders_choice",
        "fielders_choice_out", "double_play", "catcher_interf", "other_out",
    }
    pa = sc[sc["events"].isin(pa_events)].copy()
    pa["is_k"]  = pa["events"].isin({"strikeout", "strikeout_double_play"}).astype(int)
    pa["is_bb"] = pa["events"].isin({"walk", "intent_walk"}).astype(int)
    pa["is_h"]  = pa["events"].isin({"single", "double", "triple", "home_run"}).astype(int)

    agg = pa.groupby("pitcher").agg(
        pa_count=("is_k", "count"),
        k_count=("is_k", "sum"),
        bb_count=("is_bb", "sum"),
        h_count=("is_h", "sum"),
    ).reset_index()

    # Read IP from pitcher CSV for WHIP/rate calculations
    if PITCHER_CSV.exists():
        p_ip = pd.read_csv(PITCHER_CSV, usecols=["pitcher", "IP"])
        agg = agg.merge(p_ip, on="pitcher", how="left")
        agg = agg[agg["IP"].notna() & (agg["IP"] > 0)]
        agg["k_per9"]  = (agg["k_count"]  / agg["IP"] * 9).round(2)
        agg["bb_per9"] = (agg["bb_count"] / agg["IP"] * 9).round(2)
        agg["whip_raw"] = ((agg["h_count"] + agg["bb_count"]) / agg["IP"]).round(3)
    else:
        return {}

    result = {}
    for _, row in agg.iterrows():
        result[int(row["pitcher"])] = {
            "k_per9":   float(row["k_per9"]),
            "bb_per9":  float(row["bb_per9"]),
            "whip_raw": float(row["whip_raw"]),
        }
    return result


def _load_sprint_data() -> dict:
    """Returns {batter_mlbam_id: career_sprint_speed_mph}"""
    if not SPRINT_JSON.exists():
        return {}
    raw = json.loads(SPRINT_JSON.read_text(encoding="utf-8"))
    result = {}
    for k, v in raw.items():
        speed = v.get("career_sprint_speed")
        if speed is not None:
            try:
                result[int(k)] = float(speed)
            except (ValueError, TypeError):
                pass
    return result


def _load_career_pitch_mix() -> dict:
    """Load career (2025 arsenal) pitch mix baseline.
    Returns {pitcher_mlbam_id: {career_pitch_types, career_usage, career_swstr, ...}}
    """
    if not CAREER_MIX_JSON.exists():
        return {}
    raw = json.loads(CAREER_MIX_JSON.read_text(encoding="utf-8"))
    return {int(k): v for k, v in raw.items()}


def _load_current_pitch_mix() -> dict:
    """Load current 2026 pitch mix from Statcast.
    Returns {pitcher_mlbam_id: {curr_pitch_types, curr_usage, curr_swstr, ...}}
    """
    if not CURRENT_MIX_JSON.exists():
        return {}
    raw = json.loads(CURRENT_MIX_JSON.read_text(encoding="utf-8"))
    return {int(k): v for k, v in raw.items()}


def load_all_career_data() -> dict:
    """Load and return all career data needed for projections.
    Returns:
      {
        "hitter":  {mlbam_id: {career_woba_fg, career_xwoba_fg, career_ba_fg, fg_career_pa}},
        "pitcher": {mlbam_id: {career_era_fg, career_xera_fg, career_pa_fg}},
        "pitcher_rates": {mlbam_id: {k_per9, bb_per9, whip_raw}},
        "sprint":  {mlbam_id: career_sprint_speed},
      }
    """
    return {
        "hitter":              _load_fg_batting_career(),
        "pitcher":             _load_fg_pitching_career(),
        "pitcher_rates":       _load_statcast_pitcher_rates(),
        "sprint":              _load_sprint_data(),
        "career_pitch_mix":    _load_career_pitch_mix(),
        "current_pitch_mix":   _load_current_pitch_mix(),
    }


def _load_pt_lookups() -> None:
    """Lazy-load Steamer PA/IP, IL status, and hitter games-played lookups."""
    global _STEAMER_PA, _STEAMER_G, _STEAMER_IP, _IL_STATUS, _HITTER_GP, _PT_LOADED
    if _PT_LOADED:
        return

    if STEAMER_BAT_CSV.exists():
        with open(STEAMER_BAT_CSV, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                mid = str(row.get("MLBAMID", "") or "").strip()
                try:
                    pa = float(row["PA"])
                except (KeyError, ValueError, TypeError):
                    pa = float("nan")
                try:
                    g = float(row["G"])
                except (KeyError, ValueError, TypeError):
                    g = float("nan")
                if mid and math.isfinite(pa) and pa > 0:
                    _STEAMER_PA[mid] = pa
                if mid and math.isfinite(g):
                    _STEAMER_G[mid] = g

    if STEAMER_PIT_CSV.exists():
        with open(STEAMER_PIT_CSV, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                mid = str(row.get("MLBAMID", "") or "").strip()
                try:
                    ip = float(row["IP"])
                except (KeyError, ValueError, TypeError):
                    ip = float("nan")
                try:
                    gs = float(row["GS"])
                except (KeyError, ValueError, TypeError):
                    gs = float("nan")
                if mid and math.isfinite(ip) and ip > 0:
                    _STEAMER_IP[mid] = {"IP": ip, "GS": gs if math.isfinite(gs) else 0.0}

    if OWNERSHIP_CSV.exists():
        try:
            own_df = pd.read_csv(OWNERSHIP_CSV)
            if "injury_status" in own_df.columns:
                for _, r in own_df.iterrows():
                    try:
                        mid = int(float(r["mlbam_id"]))
                        status = str(r["injury_status"]) if pd.notna(r["injury_status"]) else "ACTIVE"
                        _IL_STATUS[mid] = status
                    except (ValueError, TypeError):
                        pass
        except Exception:
            pass

    if HS_STATCAST_CSV.exists():
        try:
            hs = pd.read_csv(HS_STATCAST_CSV, usecols=["batter", "game_pk"])
            gp = hs.groupby("batter")["game_pk"].nunique()
            _HITTER_GP = {int(k): int(v) for k, v in gp.items()}
        except Exception:
            pass

    _PT_LOADED = True


def _blend_pa(
    mlbam_id: Optional[int],
    games_rem: int,
    pa_so_far: int,
    games_played: int,
) -> Optional[int]:
    """Return blended projected PA, or None to fall back to slot formula.

    Weights Steamer full-season PA (scaled to ROS) against current pace,
    shifting weight toward pace as games_played increases.
    IL penalty reduces games_rem_adj if player is on the IL.
    """
    if not _PT_LOADED:
        _load_pt_lookups()

    if mlbam_id is None:
        return None

    status = _IL_STATUS.get(mlbam_id, "ACTIVE")
    il_penalty = {"DAY_TO_DAY": 5, "INJURY_RESERVE": 12}.get(status, 0)
    games_rem_adj = max(0, games_rem - il_penalty)

    # When the GP lookup returns 0 (ESPN endpoint limitation) but we have PA data,
    # estimate games played from PA at ~4.0 PA/game. This prevents Steamer
    # projections from dominating for breakout players whose 2025 Steamer role
    # (backup) no longer reflects their 2026 usage (starter).
    gp_eff = games_played
    if (gp_eff is None or gp_eff < 5) and pa_so_far >= 5:
        gp_eff = max(int(pa_so_far / 4.0), 5)

    if gp_eff < 20:
        w_s, w_p = 0.70, 0.30
    elif gp_eff < 50:
        w_s, w_p = 0.60, 0.40
    else:
        w_s, w_p = 0.40, 0.60

    steamer_full = _STEAMER_PA.get(str(mlbam_id))
    steamer_ros  = steamer_full * (games_rem / 162) if steamer_full else None

    pace_ros = (
        (pa_so_far / gp_eff) * games_rem_adj * 0.90
        if gp_eff >= 5 else None
    )

    # Stale-Steamer override: Steamer projected the player as a part-time/backup
    # (G in [40, 80)) but current pace says significantly more playing time (pace
    # > 1.5× steamer_ros) AND player has accumulated ≥80 PA to confirm the role.
    # G >= 40 floor: avoids fringe bench players (Steamer G=20-39) who are merely
    # getting opportunistic at-bats rather than a genuine role change. The G=20
    # floor was too permissive — audit showed 97/120 triggers were noise (deep bench,
    # <1% owned, CBS rank >250). G >= 40 preserves all 9 legitimate cases from audit.
    # PA >= 80 gate: prevents firing on injured/optioned players with <25 PA who
    # happen to have Steamer G in range. Requires sustained usage evidence first.
    if (steamer_ros is not None and pace_ros is not None
            and pace_ros > steamer_ros * 1.5
            and pa_so_far >= 80):
        steamer_games = _STEAMER_G.get(str(mlbam_id), 999.0)
        if 40.0 <= steamer_games < 80.0:
            w_s, w_p = 0.30, 0.70
            _STEAMER_PT_OVERRIDE_FLAGS[mlbam_id] = True

    if steamer_ros and pace_ros:
        return int(w_s * steamer_ros + w_p * pace_ros)
    if steamer_ros:
        return int(steamer_ros)
    if pace_ros:
        return int(pace_ros)
    return None


def _blend_ip(
    mlbam_id: Optional[int],
    games_rem: int,
    current_ip: float,
    current_gs: int,
    current_games: int,
) -> Optional[float]:
    """Return blended projected IP, or None to fall back to existing formula.

    Uses Steamer GS to classify SP vs RP.
    Relievers are capped at 70 IP and lean heavily on Steamer.
    Returns None when no Steamer data is available.
    """
    if not _PT_LOADED:
        _load_pt_lookups()

    if mlbam_id is None:
        return None

    steamer_data = _STEAMER_IP.get(str(mlbam_id))
    if not steamer_data:
        return None

    steamer_full_ip = steamer_data["IP"]
    steamer_gs      = steamer_data["GS"]
    steamer_ros_ip  = steamer_full_ip * (games_rem / 162)

    is_starter = steamer_gs >= 10

    # SP conversion fallback: actual 2026 starts override Steamer RP classification.
    # Mirrors role_override gates in score_pitcher_luck.py (total_starts>=5, IP>=20,
    # IP/start>=4.0). current_gs receives total_starts at the call site.
    _role_overridden = False
    if not is_starter and current_gs >= 5 and current_ip >= 20:
        if current_ip / current_gs >= 4.0:
            is_starter = True
            _role_overridden = True

    if is_starter:
        if _role_overridden:
            # Steamer's ip/start is unreliable (projected as RP); use actual 2026
            # ip/start as pace. Blend flipped: 0.45 Steamer + 0.55 actual pace
            # because Steamer's IP forecast is wrong for this pitcher's real role.
            ip_per_start = current_ip / current_gs
            starts_rem   = int(games_rem / 5 * 0.85)
            pace_ros     = starts_rem * ip_per_start
            blended      = 0.45 * steamer_ros_ip + 0.55 * pace_ros
            blended      = min(blended, 110.0)  # cap: unproven SP converts
        else:
            ip_per_start = steamer_full_ip / max(steamer_gs, 1)
            starts_rem   = int(games_rem / 5 * 0.85)
            pace_ros     = starts_rem * ip_per_start
            blended      = 0.55 * steamer_ros_ip + 0.45 * pace_ros
    else:
        if current_ip >= 15 and current_games > 0:
            ip_per_app   = current_ip / current_games
            appearances  = int(games_rem * 0.45 * 0.85)
            pace_ros     = appearances * ip_per_app
            blended      = 0.80 * steamer_ros_ip + 0.20 * pace_ros
        else:
            blended = steamer_ros_ip
        blended = min(blended, 70.0)

    return round(blended, 1)


def _get_cache() -> dict:
    """Lazy-load and cache all data."""
    if not _CACHE:
        _CACHE["hitters"]  = _add_norm_col(pd.read_csv(HITTER_CSV))  if HITTER_CSV.exists()  else pd.DataFrame()
        _CACHE["pitchers"] = _add_norm_col(pd.read_csv(PITCHER_CSV)) if PITCHER_CSV.exists() else pd.DataFrame()
        career = load_all_career_data()
        _CACHE.update(career)
        # Pitch mix is loaded as part of career data above; also cache directly
        _CACHE.setdefault("career_pitch_mix",  {})
        _CACHE.setdefault("current_pitch_mix", {})
    return _CACHE


def _add_norm_col(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["_norm"] = df["name"].apply(_norm)
    return df


# ---------------------------------------------------------------------------
# SECTION A — Historical baseline functions
# ---------------------------------------------------------------------------

def get_hitter_baseline(batter_id: int, career_data: dict) -> dict:
    """Return career baseline for a hitter.
    Falls back to league averages when data is unavailable.
    """
    hitter_career = career_data.get("hitter", {})
    entry = hitter_career.get(int(batter_id), {})

    career_woba = entry.get("career_woba_fg", LEAGUE_AVG_HITTER["career_woba"])
    career_ba   = entry.get("career_ba_fg",   LEAGUE_AVG_HITTER["career_avg"])
    fg_pa       = entry.get("fg_career_pa",   LEAGUE_AVG_HITTER["career_pa"])
    n_seasons   = max(1, round(fg_pa / 550))

    # HR rate proxy from career wOBA (no direct career HR/FB data for hitters)
    # Calibrated: wOBA .318 ≈ 3.3% HR/PA; wOBA .400 ≈ 6%
    career_hr_rate = max(0.010, min(0.090, (career_woba - 0.25) * 0.10 + 0.020))

    # BB% and K% — no reliable multi-year data; use league averages
    career_bb_pct = LEAGUE_AVG_HITTER["career_bb_pct"]
    career_k_pct  = LEAGUE_AVG_HITTER["career_k_pct"]

    return {
        "career_avg":     round(career_ba, 4),
        "career_hr_rate": round(career_hr_rate, 4),
        "career_sb_rate": 0.0,
        "career_bb_pct":  career_bb_pct,
        "career_k_pct":   career_k_pct,
        "career_woba":    round(career_woba, 4),
        "career_pa":      int(fg_pa),
        "n_seasons":      n_seasons,
    }


def get_pitcher_baseline(pitcher_id: int, career_data: dict) -> dict:
    """Return career baseline for a pitcher.
    Falls back to league averages when data is unavailable.
    """
    pitcher_career = career_data.get("pitcher", {})
    entry = pitcher_career.get(int(pitcher_id), {})

    career_era  = entry.get("career_era_fg",  LEAGUE_AVG_PITCHER["career_era"])
    # Cap extreme small-sample career ERAs — FG weighted ERA can reach 135.00
    # for pitchers with 1-2 IP of terrible MLB work; treat as replacement level
    if career_era > 6.50:
        career_era = 5.50
    career_xera = entry.get("career_xera_fg", career_era)  # use ERA as fallback
    fg_pa       = entry.get("career_pa_fg",   0)
    n_seasons   = max(1, round(fg_pa / 700))

    # WHIP estimated from career ERA (empirical: WHIP ≈ ERA × 0.20 + 0.55)
    career_whip = round(max(0.90, min(1.70, career_era * WHIP_ERA_SLOPE + WHIP_ERA_INTERCEPT)), 3)
    if career_whip > 1.80:
        career_whip = 1.55

    # K/9 and BB/9 — no career data available; use league averages
    career_k9 = LEAGUE_AVG_PITCHER["career_k_per9"]
    career_bb9 = LEAGUE_AVG_PITCHER["career_bb_per9"]

    return {
        "career_era":          round(career_era, 3),
        "career_whip":         career_whip,
        "career_k_per9":       career_k9,
        "career_bb_per9":      career_bb9,
        "career_hr9":          LEAGUE_AVG_PITCHER["career_hr9"],
        "career_ip_per_start": LEAGUE_AVG_PITCHER["career_ip_per_start"],
        "career_ip":           float(fg_pa / 4.3) if fg_pa > 0 else LEAGUE_AVG_PITCHER["career_ip"],
        "n_seasons":           n_seasons,
    }


# ---------------------------------------------------------------------------
# SECTION B — True talent functions
# ---------------------------------------------------------------------------

def _safe_float(val, fallback: float = float("nan")) -> float:
    try:
        v = float(val)
        return v if not (v != v) else fallback  # nan check
    except (TypeError, ValueError):
        return fallback


def hitter_true_talent(row: pd.Series, baseline: dict) -> dict:
    """Compute luck-adjusted true talent from current season data + career baseline.
    Returns rate-based dict; use blend_projection() + project_hitter_counting() for counts.
    """
    # TRUE_TALENT_BABIP — already park/OAA/age adjusted in luck_scores.csv
    true_babip = _safe_float(row.get("park_adj_babip_expected"),
                             _safe_float(row.get("career_babip"), 0.300))

    # TRUE_TALENT_CONTACT — career BA anchor blended with xwOBA-derived estimate
    xwoba    = _safe_float(row.get("xwOBA"), _safe_float(row.get("career_woba"), 0.318))
    woba     = _safe_float(row.get("wOBA"), xwoba)
    xwoba_gap = xwoba - woba  # positive = unlucky on contact; negative = lucky

    # xwOBA formula: expected BA from current April contact quality
    formula_avg = (xwoba - 0.050) / 1.057  # lg-avg xwOBA .320 → .255 AVG

    career_ba = baseline.get("career_avg", float("nan"))
    career_pa = baseline.get("career_pa",  0)

    # Primary blend: career BA anchors against April xwOBA swings.
    # Backtest A finding: pure xwOBA formula over-projects AVG for high-xwOBA hitters
    # whose career BA lags — career data is a better stabilizer at small April samples.
    if career_ba == career_ba and career_pa >= MIN_CAREER_PA_BA:
        true_avg = career_ba * CAREER_BA_WEIGHT + formula_avg * APRIL_AVG_WEIGHT
    else:
        true_avg = formula_avg  # sparse career data — fall back to xwOBA formula

    # Contact-luck nudge: small adjustment when xwOBA and wOBA diverge meaningfully
    if xwoba_gap > 0.030:
        true_avg += 0.008   # unlucky hitter — nudge AVG up toward contact quality
    elif xwoba_gap < -0.030:
        true_avg -= 0.008   # lucky hitter — nudge AVG down toward true contact

    true_avg = max(0.195, min(0.375, true_avg))

    # TRUE_TALENT_POWER — barrel rate × BARREL_TO_HR adjusted for BBE rate
    barrel_rate = _safe_float(row.get("barrel_rate"), 0.065)
    bb_rate     = _safe_float(row.get("bb_rate"),     baseline["career_bb_pct"])
    k_rate      = _safe_float(row.get("k_rate"),      baseline["career_k_pct"])
    bip_rate    = max(0.0, 1.0 - k_rate - bb_rate)
    true_hr_rate = min(0.090, barrel_rate * bip_rate * BARREL_TO_HR)

    # TRUE_TALENT_SPEED — sprint speed → SB attempts tier
    sprint_data   = {}  # populated by project_player when sprint available
    sprint_speed  = _safe_float(row.get("_sprint_speed"), float("nan"))
    if sprint_speed >= 28.0:
        sb_attempts_per_game = 25.0 / 150.0   # high tier
        sb_success = 0.75
    elif sprint_speed >= 26.5:
        sb_attempts_per_game = 12.0 / 150.0   # medium tier
        sb_success = 0.70
    elif sprint_speed > 0:
        sb_attempts_per_game = 4.0 / 150.0    # low tier
        sb_success = 0.65
    else:
        sb_attempts_per_game = 6.0 / 150.0    # unknown — league avg
        sb_success = 0.70
    true_sb_per_game = sb_attempts_per_game * sb_success

    # TRUE_TALENT_BB and K — current season rates are relatively reliable
    true_bb_pct = _safe_float(row.get("bb_rate"), baseline["career_bb_pct"])
    true_k_pct  = _safe_float(row.get("k_rate"),  baseline["career_k_pct"])

    # wOBA from xwOBA (forward-looking)
    true_woba = _safe_float(row.get("xwOBA"), baseline["career_woba"])

    return {
        "true_babip":      round(true_babip, 4),
        "true_avg":        round(true_avg,   4),
        "true_hr_rate":    round(true_hr_rate, 4),
        "true_woba":       round(true_woba,  4),
        "true_sb_per_game":round(true_sb_per_game, 5),
        "true_bb_pct":     round(true_bb_pct, 4),
        "true_k_pct":      round(true_k_pct,  4),
    }


def pitcher_true_talent(row: pd.Series, baseline: dict,
                        pitcher_rates: Optional[dict] = None) -> dict:
    """Compute luck-adjusted true talent for a pitcher.
    pitcher_rates: dict from _load_statcast_pitcher_rates(), keyed by pitcher_id.
    """
    fip   = _safe_float(row.get("FIP"),  float("nan"))
    xera  = _safe_float(row.get("xERA"), float("nan"))
    # Guard negative/impossible xERA values (e.g. Kilian -2.355, Seymour -3.287)
    if xera != xera or xera < 0 or xera > 15:
        xera = float("nan")
    career_era = baseline["career_era"]

    # TRUE_TALENT_ERA
    fip_xera_gap = abs(fip - xera) if not (fip != fip or xera != xera) else float("nan")
    if not (fip != fip) and not (xera != xera):
        if fip_xera_gap < 0.50:
            true_era = fip * 0.60 + xera * 0.40
        else:
            true_era = fip * 0.40 + xera * 0.40 + career_era * 0.20
    elif not (fip != fip):
        true_era = fip * 0.85 + career_era * 0.15
    elif not (xera != xera):
        true_era = xera * 0.80 + career_era * 0.20
    else:
        true_era = career_era
    true_era = round(max(1.50, min(7.00, true_era)), 3)

    # TRUE_TALENT_WHIP — component-rate approach: (proj_H9 + proj_BB9) / 9
    # Backtest A finding: ERA-derived WHIP (ERA × 0.20 + 0.55) regresses too slowly
    # toward league average. H/9 and BB/9 are more independent and stabilize faster.
    current_bb9 = float("nan")
    current_h9  = float("nan")
    if pitcher_rates and "pitcher" in row.index:
        rates = pitcher_rates.get(int(row.get("pitcher", -1)), {})
        whip_raw    = rates.get("whip_raw", float("nan"))
        current_bb9 = rates.get("bb_per9",  float("nan"))
        # Derive H/9 from observed WHIP and BB/9 (both already in pitcher_rates)
        if whip_raw == whip_raw and current_bb9 == current_bb9:
            current_h9 = max(0.0, whip_raw * 9 - current_bb9)

    # Career H/9 derived from career WHIP and career BB/9 (no new data source needed)
    career_bb9 = baseline["career_bb_per9"]
    career_h9  = max(3.0, baseline["career_whip"] * 9 - career_bb9)

    proj_h9  = (career_h9  * 0.60
                + (current_h9  if current_h9  == current_h9  else LG_H9)  * 0.40)
    proj_bb9 = (career_bb9 * 0.60
                + (current_bb9 if current_bb9 == current_bb9 else LG_BB9) * 0.40)

    proj_h9  = max(3.0, min(14.0, proj_h9))
    proj_bb9 = max(0.5, min(7.0,  proj_bb9))

    true_whip = round(max(0.80, min(2.00, (proj_h9 + proj_bb9) / 9)), 3)

    # TRUE_TALENT_K
    swstr = _safe_float(row.get("swstr_rate"), float("nan"))
    if pitcher_rates and "pitcher" in row.index:
        rates = pitcher_rates.get(int(row.get("pitcher", -1)), {})
        curr_k9 = rates.get("k_per9", float("nan"))
    else:
        curr_k9 = float("nan")

    if swstr == swstr:  # not nan
        swstr_k9 = swstr * SWSTR_TO_K9
    elif curr_k9 == curr_k9:
        swstr_k9 = curr_k9
    else:
        swstr_k9 = baseline["career_k_per9"]

    if curr_k9 == curr_k9:
        true_k9 = round(curr_k9 * 0.70 + baseline["career_k_per9"] * 0.30, 2)
    else:
        true_k9 = round(swstr_k9 * 0.70 + baseline["career_k_per9"] * 0.30, 2)
    true_k9 = max(3.0, min(16.0, true_k9))

    # TRUE_TALENT_BB
    if pitcher_rates and "pitcher" in row.index:
        rates = pitcher_rates.get(int(row.get("pitcher", -1)), {})
        curr_bb9 = rates.get("bb_per9", float("nan"))
    else:
        curr_bb9 = float("nan")
    true_bb9 = curr_bb9 if (curr_bb9 == curr_bb9) else baseline["career_bb_per9"]
    true_bb9 = round(max(0.5, min(7.0, true_bb9)), 2)

    # TRUE_TALENT_IP per start
    ip = _safe_float(row.get("IP"), 0.0)
    apps = _safe_float(row.get("total_starts"), 1.0)
    if ip > 0 and apps > 0:
        curr_ip_per_start = ip / apps
    else:
        curr_ip_per_start = baseline["career_ip_per_start"]
    true_ip_per_start = round(
        max(3.5, min(7.5,
            curr_ip_per_start * 0.60 + baseline["career_ip_per_start"] * 0.40)),
        2
    )

    return {
        "true_era":          true_era,
        "true_whip":         true_whip,
        "true_k_per9":       round(true_k9, 2),
        "true_bb_per9":      round(true_bb9, 2),
        "true_ip_per_start": true_ip_per_start,
    }


# ---------------------------------------------------------------------------
# SECTION C — Sample size weighting
# ---------------------------------------------------------------------------

def sample_weight(pa_or_ip: float, is_pitcher: bool = False) -> float:
    """Return weight (0-1) to give current-season true-talent vs career baseline.
    Thresholds calibrated for early season (April). Revisit monthly.
    """
    v = float(pa_or_ip) if pa_or_ip is not None else 0.0
    if is_pitcher:
        if v < 20:  return 0.15   # Low — first 2-3 weeks
        if v < 40:  return 0.30   # Medium — 3-6 weeks
        return 0.45               # High — 6+ weeks
    else:
        if v < 50:  return 0.15   # Low — first 2-3 weeks
        if v < 100: return 0.30   # Medium — 3-6 weeks
        return 0.45               # High — 6+ weeks


def blend_projection(true_talent_current: dict,
                     historical_baseline: dict,
                     current_weight: float) -> dict:
    """Blend current true talent with historical baseline using sample weight.
    Keys present in both dicts are blended; others passed through unchanged.
    """
    hist_weight = 1.0 - current_weight
    result = {}

    # Map true_talent keys to baseline keys
    _key_map = {
        "true_avg":        "career_avg",
        "true_hr_rate":    "career_hr_rate",
        "true_bb_pct":     "career_bb_pct",
        "true_k_pct":      "career_k_pct",
        "true_woba":       "career_woba",
        "true_sb_per_game": None,           # no baseline equivalent
        "true_era":        "career_era",
        "true_whip":       "career_whip",
        "true_k_per9":     "career_k_per9",
        "true_bb_per9":    "career_bb_per9",
        "true_ip_per_start": "career_ip_per_start",
    }

    for curr_key, hist_key in _key_map.items():
        if curr_key not in true_talent_current:
            continue
        curr_val = true_talent_current[curr_key]
        if hist_key and hist_key in historical_baseline:
            hist_val = historical_baseline[hist_key]
            blended  = curr_val * current_weight + hist_val * hist_weight
        else:
            blended  = curr_val  # no baseline — keep current as-is
        result[curr_key] = round(blended, 5)

    # Pass through any keys not in map
    for k, v in true_talent_current.items():
        if k not in result:
            result[k] = v
    return result


# ---------------------------------------------------------------------------
# SECTION D — Counting stat translators
# ---------------------------------------------------------------------------

def _games_remaining(today: Optional[date] = None) -> int:
    ref = today or date.today()
    if ref >= SEASON_END_2026:
        return 0
    delta = (SEASON_END_2026 - ref).days
    # Approximate remaining games from remaining days
    # MLB season: ~25 days between games (including off days) → 162/187 days ≈ 0.87 games/day
    games = int(delta * 0.87)
    return max(0, min(games, 162))


def _sample_confidence_label(pa_or_ip: float, is_pitcher: bool = False) -> str:
    v = float(pa_or_ip)
    if is_pitcher:
        if v < 20: return "Low (<20 IP)"
        if v < 40: return "Medium (20-40 IP)"
        return "High (40+ IP)"
    else:
        if v < 50:  return "Low (<50 PA)"
        if v < 100: return "Medium (50-100 PA)"
        return "High (100+ PA)"


def project_hitter_counting(blended: dict,
                             games_remaining: int,
                             batting_order_pos: int = 4,
                             signal: str = "Neutral",
                             xwoba_gap: float = None,
                             r_mult: float = 1.0,
                             rbi_mult: float = 1.0,
                             mlbam_id: Optional[int] = None,
                             pa_so_far: int = 0,
                             games_played: int = 0) -> dict:
    """Convert blended rate stats to rest-of-season counting stats."""
    health_factor = 0.85
    # Playing time: blended Steamer/pace when available; slot formula as fallback
    blended_pa_val = _blend_pa(mlbam_id, games_remaining, pa_so_far, games_played)
    if blended_pa_val is not None:
        projected_pa = max(0, blended_pa_val)
    else:
        pa_per_game = {1: 4.4, 2: 4.4, 3: 4.2, 4: 4.2, 5: 4.2}.get(
            batting_order_pos, 4.1 if batting_order_pos >= 6 else 4.1
        )
        if batting_order_pos >= 6:
            pa_per_game = 3.9
        projected_pa = max(0, int(pa_per_game * games_remaining * health_factor))

    avg     = blended.get("true_avg",     0.248)
    hr_rate = blended.get("true_hr_rate", 0.033)
    bb_pct  = blended.get("true_bb_pct",  0.085)
    k_pct   = blended.get("true_k_pct",   0.220)
    sb_pg   = blended.get("true_sb_per_game", 0.0)

    HR  = max(0, int(projected_pa * hr_rate))
    BB  = max(0, int(projected_pa * bb_pct))
    H   = max(0, int(projected_pa * avg * (1 - bb_pct)))
    if H < HR:
        H = HR  # HR is a subset of hits

    R_per_HR = 1.0
    R_per_H  = 0.35
    R   = max(0, int(HR * R_per_HR + (H - HR) * R_per_H + BB * 0.15))

    RBI_per_HR = 1.30
    RBI_per_H  = 0.32
    RBI = max(0, int(HR * RBI_per_HR + (H - HR) * RBI_per_H))

    SB  = max(0, int(sb_pg * games_remaining * health_factor))

    # Apply luck signal multiplier — injects buy/sell direction into counting stats
    mult = LUCK_MULTIPLIERS.get(signal, LUCK_MULTIPLIERS["Neutral"])

    # For sell signals where xwOBA ≈ wOBA (gap > -0.020), the sell verdict is
    # BABIP-driven, not contact-quality-driven. The player's barrel rate is real —
    # suppress only the AVG/run-scoring penalty, not the HR rate.
    hr_mult = mult["hr"]
    if (signal in ("Sell high", "Slight sell")
            and xwoba_gap is not None
            and xwoba_gap > -0.020):
        hr_mult = 1.0

    avg  = round(avg  * mult["avg"], 3)
    HR   = round(HR   * hr_mult)
    SB   = round(SB   * mult["sb"])
    R    = round(R    * mult["avg"])
    RBI  = round(RBI  * mult["avg"])

    # Lineup context multipliers (backtest-validated; default 1.0 = no change)
    R   = max(0, round(R   * r_mult))
    RBI = max(0, round(RBI * rbi_mult))

    return {
        "projected_avg":  avg,
        "projected_hr":   int(HR),
        "projected_r":    int(R),
        "projected_rbi":  int(RBI),
        "projected_sb":   int(SB),
        "projected_pa":   projected_pa,
        "games_remaining": games_remaining,
        "sample_confidence": "",   # filled by caller
    }


def project_pitcher_counting(blended: dict,
                              games_remaining: int,
                              is_starter: bool = True,
                              signal: str = "Neutral",
                              mlbam_id: Optional[int] = None,
                              current_ip: float = 0.0,
                              current_gs: int = 0,
                              current_games: int = 0,
                              role_overridden: bool = False) -> dict:
    """Convert blended pitcher rate stats to rest-of-season counting stats."""
    health_factor = 0.85

    # Playing time: blended Steamer/pace when available; role-based formula as fallback
    blended_ip_val = _blend_ip(mlbam_id, games_remaining, current_ip, current_gs, current_games)
    if blended_ip_val is not None:
        projected_ip = blended_ip_val
        if is_starter:
            starts_remaining = max(0, int(games_remaining / 5 * health_factor))
        else:
            starts_remaining = 0
    elif is_starter:
        starts_remaining = max(0, int(games_remaining / 5 * health_factor))
        ip_per_start = blended.get("true_ip_per_start", 5.60)
        projected_ip = round(starts_remaining * ip_per_start, 1)
        if role_overridden:
            projected_ip = min(projected_ip, 110.0)
    else:
        # Reliever: ~1.0 IP per appearance, ~4 app per 5 games
        appearances = max(0, int(games_remaining * 0.80 * health_factor))
        starts_remaining = 0
        projected_ip = round(appearances * 1.0, 1)

    era   = blended.get("true_era",   4.20)
    whip  = blended.get("true_whip",  1.30)
    k_per9 = blended.get("true_k_per9", 8.50)

    K  = max(0, int(k_per9 / 9.0 * projected_ip))
    W  = max(0, int(starts_remaining * 0.33)) if is_starter else 0
    SV_H = 0  # starters get 0; relievers would need separate logic

    # Hard clamp — safety net after all blending; Tasks 1+2 handle root causes
    era  = max(1.80, min(7.00, era))
    whip = max(0.85, min(2.00, whip))

    # Apply luck signal multiplier — ERA > 1 means worse (sell high gets higher ERA)
    mult = PITCHER_LUCK_MULTIPLIERS.get(signal, PITCHER_LUCK_MULTIPLIERS["Neutral"])
    era  = round(era  * mult["era"],  2)
    whip = round(whip * mult["whip"], 2)
    K    = round(K    * mult["k"])

    # Re-clamp after multiplier
    era  = max(1.80, min(7.00, era))
    whip = max(0.85, min(2.00, whip))

    return {
        "projected_era":      era,
        "projected_whip":     whip,
        "projected_k":        int(K),
        "projected_w":        W,
        "projected_sv_h":     SV_H,
        "projected_ip":       projected_ip,
        "starts_remaining":   starts_remaining,
        "games_remaining":    games_remaining,
        "sample_confidence":  "",  # filled by caller
    }


# ---------------------------------------------------------------------------
# SECTION E1 — Pitcher evolution detector
# ---------------------------------------------------------------------------

def detect_pitcher_evolution(
    pitcher_id: int,
    current_stats: dict,
    career_pitch_mix: dict,
    current_pitch_mix: dict,
) -> dict:
    """Score how much a pitcher has materially changed vs their career baseline.

    Returns:
      evolution_score:      int  (higher = more changed; negative = declining)
      flags:                list[str]
      career_weight_adj:    float  (negative = trust current more)
      is_different_pitcher: bool   (score >= 3)
      summary:              str
    """
    evolution_score = 0
    flags: list = []

    # ── Pitch mix changes ────────────────────────────────────────────────
    career_types  = set(career_pitch_mix.get("career_pitch_types", []))
    curr_types    = set(current_pitch_mix.get("curr_pitch_types",  []))
    pitch_swstr   = current_pitch_mix.get("curr_swstr", {})
    curr_usage    = current_pitch_mix.get("curr_usage",  {})

    # Require career data to detect "new" pitches; without a baseline every pitch
    # looks new (e.g. pitcher returning from injury with no 2025 arsenal entry)
    if career_types:
        # Only flag pitches that are prominent in current season (≥10% usage)
        # — prevents rare repertoire pitches from triggering false positives
        new_pitches = sorted(
            pt for pt in (curr_types - career_types)
            if curr_usage.get(pt, 0.0) >= 0.10
        )
        if new_pitches:
            for pitch in new_pitches:
                ps = pitch_swstr.get(pitch, 0.0)
                if ps >= 0.30:
                    evolution_score += 3
                    flags.append(f"Elite new pitch: {pitch} ({ps:.1%} whiff)")
                elif ps >= 0.15:
                    # Threshold lowered from 0.20 — captures splitters/curves
                    # that are legitimate weapons below the elite cutoff
                    evolution_score += 2
                    flags.append(f"New pitch: {pitch} ({ps:.1%} whiff)")
                elif ps >= 0.10:
                    evolution_score += 1
                    flags.append(f"New pitch (low whiff): {pitch} ({ps:.1%} whiff)")
            # Arsenal expansion bonus — adding 2+ prominent new pitch types
            if len(new_pitches) >= 2:
                evolution_score += 1
                flags.append(f"Arsenal expansion: {len(new_pitches)} new pitch types added")

        # Major usage shift on existing pitch
        career_usage = career_pitch_mix.get("career_usage", {})
        for pitch_type in career_types:
            c_usage = career_usage.get(pitch_type, 0.0)
            n_usage = curr_usage.get(pitch_type, 0.0)
            delta   = n_usage - c_usage
            if abs(delta) >= 0.15:
                evolution_score += 1
                direction = "up" if delta > 0 else "down"
                flags.append(f"{pitch_type} usage {direction} {abs(delta):.0%} vs career")

    # ── Stuff quality changes ────────────────────────────────────────────
    swstr_gap = _safe_float(current_stats.get("swstr_gap"), float("nan"))
    if swstr_gap == swstr_gap:   # not nan
        if swstr_gap >= 0.040:
            evolution_score += 2
            flags.append(f"SwStr% up {swstr_gap:.1%} vs career")
        elif swstr_gap >= 0.025:
            evolution_score += 1
            flags.append(f"SwStr% improving {swstr_gap:.1%}")
        elif swstr_gap <= -0.030:
            evolution_score -= 1
            flags.append(f"SwStr% declining {swstr_gap:.1%}")

    # Velocity change (FB velo vs career)
    velo_gap = _safe_float(current_stats.get("velo_gap"), float("nan"))
    if velo_gap == velo_gap:    # not nan
        if velo_gap >= 1.5:
            evolution_score += 2
            flags.append(f"Velocity up {velo_gap:.1f} mph vs career")
        elif velo_gap >= 0.8:
            evolution_score += 1
            flags.append(f"Velocity slightly up {velo_gap:.1f} mph")
        elif velo_gap <= -1.5:
            evolution_score -= 2
            flags.append(f"Velocity down {abs(velo_gap):.1f} mph vs career")
        elif velo_gap <= -0.8:
            evolution_score -= 1
            flags.append(f"Velocity slightly down {abs(velo_gap):.1f} mph")

    # CSW improvement (already computed in scorer)
    csw_gap = _safe_float(current_stats.get("csw_gap"), float("nan"))
    if csw_gap == csw_gap:    # not nan
        if csw_gap >= 0.025:
            evolution_score += 1
            flags.append(f"CSW% up {csw_gap:.1%} vs career")
        elif csw_gap <= -0.025:
            evolution_score -= 1
            flags.append(f"CSW% declining {csw_gap:.1%}")

    # K% improvement vs league average (0.220 default when no career data)
    curr_k = _safe_float(current_stats.get("k_pct"), float("nan"))
    career_k = 0.220   # league average default — career K% data not in current files
    if curr_k == curr_k:   # not nan
        k_gap = curr_k - career_k
        if k_gap >= 0.050:
            evolution_score += 1
            flags.append(f"K% {curr_k:.1%} vs avg baseline {career_k:.1%}")
        elif k_gap <= -0.040:
            evolution_score -= 1
            flags.append(f"K% declining vs avg baseline {k_gap:.1%}")

    # ── Career weight adjustment ──────────────────────────────────────────
    def _career_weight_adj(score: int) -> float:
        if score >= 5:  return -0.40   # treat as different pitcher
        if score >= 4:  return -0.35
        if score >= 3:  return -0.25
        if score >= 2:  return -0.15
        if score >= 1:  return -0.05
        if score <= -2: return +0.10   # declining — trust career more
        if score <= -1: return +0.05
        return 0.0

    career_wt_adj    = _career_weight_adj(evolution_score)
    is_diff_pitcher  = evolution_score >= 3

    return {
        "evolution_score":      evolution_score,
        "flags":                flags,
        "career_weight_adj":    career_wt_adj,
        "is_different_pitcher": is_diff_pitcher,
        "summary": (
            "Significant evolution detected — career baseline discounted"
            if is_diff_pitcher
            else "No material evolution detected"
        ),
    }


# ---------------------------------------------------------------------------
# SECTION E — Sanity checks
# ---------------------------------------------------------------------------

def _sanity_check_hitter(proj: dict, row: pd.Series) -> list[str]:
    warnings = []
    verdict = str(row.get("verdict", "Neutral"))
    avg = proj.get("projected_avg", 0.0)
    hr  = proj.get("projected_hr",  0)
    gr  = proj.get("games_remaining", 0)

    if avg < 0.200 or avg > 0.340:
        warnings.append(f"AVG projection {avg:.3f} outside .200-.340 range")
    if hr > 40:
        warnings.append(f"HR projection {hr} > 40 rest of season")
    if proj.get("projected_r", 0) < 0 or proj.get("projected_rbi", 0) < 0:
        warnings.append("Negative R or RBI projection")
    if verdict in ("Buy low", "Slight buy"):
        # Check projected avg is not absurdly below career level
        career_babip = _safe_float(row.get("career_babip"), 0.300)
        if proj.get("projected_avg", 0.248) < 0.190:
            warnings.append("Buy low player projects avg below .190 floor — xwOBA may be insufficient signal")
    return warnings


def _sanity_check_pitcher(proj: dict, row: pd.Series) -> list[str]:
    warnings = []
    era  = proj.get("projected_era", 0.0)
    whip = proj.get("projected_whip", 0.0)
    verdict = str(row.get("verdict", "Neutral"))

    if era < 2.00 or era > 6.00:
        warnings.append(f"ERA projection {era:.2f} outside 2.00-6.00 range")
    if whip < 0.80 or whip > 2.00:
        warnings.append(f"WHIP projection {whip:.3f} outside 0.80-2.00 range")
    if proj.get("projected_k", 0) < 0:
        warnings.append("Negative K projection")
    if verdict == "Sell high":
        curr_era = _safe_float(row.get("ERA"), float("nan"))
        if curr_era == curr_era and proj.get("projected_era", 99) < curr_era:
            warnings.append("Sell high pitcher projects better ERA than current — check signal")
    if verdict in ("Buy low", "Slight buy"):
        curr_era = _safe_float(row.get("ERA"), float("nan"))
        if curr_era == curr_era and proj.get("projected_era", 0) > curr_era:
            warnings.append("Buy low pitcher projects worse ERA than current — check FIP/xERA gap")
    return warnings


# ---------------------------------------------------------------------------
# SECTION F — Main project_player() function
# ---------------------------------------------------------------------------

def _is_starter(row: pd.Series) -> bool:
    ip   = _safe_float(row.get("IP"), 0.0)
    apps = _safe_float(row.get("total_starts"), 1.0)
    if apps > 0:
        return (ip / apps) >= 4.0
    return False


def project_player(name: str,
                   hitters_df: Optional[pd.DataFrame] = None,
                   pitchers_df: Optional[pd.DataFrame] = None,
                   career_data: Optional[dict] = None,
                   sprint_data: Optional[dict] = None,
                   mlbam_id: Optional[int] = None) -> dict:
    """Run full projection pipeline for one player.
    Pass hitters_df/pitchers_df/career_data to avoid repeated loading;
    omit to use lazy-loaded cache.
    """
    cache = _get_cache()
    if hitters_df is None:
        hitters_df = cache["hitters"]
    if pitchers_df is None:
        pitchers_df = cache["pitchers"]
    if career_data is None:
        career_data = {
            "hitter":            cache.get("hitter", {}),
            "pitcher":           cache.get("pitcher", {}),
            "pitcher_rates":     cache.get("pitcher_rates", {}),
            "career_pitch_mix":  cache.get("career_pitch_mix", {}),
            "current_pitch_mix": cache.get("current_pitch_mix", {}),
        }
    if sprint_data is None:
        sprint_data = cache.get("sprint", {})

    # Ensure _norm column
    for df in (hitters_df, pitchers_df):
        if "_norm" not in df.columns:
            df["_norm"] = df["name"].apply(_norm)

    # Find player
    ptype = None
    row   = None
    for df, pt, id_col in ((hitters_df, "hitter", "batter"),
                           (pitchers_df, "pitcher", "pitcher")):
        if df.empty:
            continue
        matches = _fuzzy_find(name, df)
        if not matches.empty:
            # Disambiguate by MLBAM ID when provided (handles duplicate names like Max Muncy)
            if mlbam_id is not None and id_col in matches.columns:
                id_match = matches[matches[id_col] == mlbam_id]
                if not id_match.empty:
                    matches = id_match
            row   = matches.iloc[0]
            ptype = pt
            break

    if row is None:
        return {"error": f"Player not found: '{name}'", "name": name}

    player_name = str(row.get("name", name))
    team        = str(row.get("Team", row.get("team", "?")))
    verdict     = str(row.get("verdict", "Neutral"))
    luck_score  = _safe_float(row.get("luck_score"), 0.0)
    owned_pct   = _safe_float(row.get("owned_pct"), float("nan"))

    games_rem = _games_remaining()

    if ptype == "hitter":
        batter_id = int(row.get("batter", 0))
        # Attach sprint speed to row for hitter_true_talent
        speed = sprint_data.get(batter_id)
        row_with_sprint = row.copy()
        if speed is not None:
            row_with_sprint["_sprint_speed"] = speed

        pa  = _safe_float(row.get("PA"), 0.0)
        baseline      = get_hitter_baseline(batter_id, career_data)
        true_talent   = hitter_true_talent(row_with_sprint, baseline)
        weight        = sample_weight(pa, is_pitcher=False)

        # Thin career baseline: < 1000 career PA (~1.5 seasons) means one average
        # year is pulling too hard against a demonstrably strong current barrel rate.
        # Reduce career weight by 15% and shift that mass to current-season signal.
        career_pa_count = baseline.get("career_pa", 9999)
        if career_pa_count < 1000:
            career_weight = (1.0 - weight) * 0.85
            weight = min(0.85, 1.0 - career_weight)

        blended       = blend_projection(true_talent, baseline, weight)
        xwoba_gap_val = _safe_float(row.get("xwOBA_gap"), None)

        # Lineup context multipliers — adjust R and RBI for batting slot/team quality
        r_mult, rbi_mult = _compute_lineup_mult(batter_id, team)
        # Sell High players are already overperforming — don't amplify with favorable context
        if verdict == "Sell high":
            rbi_mult = min(rbi_mult, 1.05)

        gp = _HITTER_GP.get(batter_id) or 0
        if not _PT_LOADED:
            _load_pt_lookups()
            gp = _HITTER_GP.get(batter_id) or 0

        proj_counting = project_hitter_counting(
            blended, games_rem, signal=verdict, xwoba_gap=xwoba_gap_val,
            r_mult=r_mult, rbi_mult=rbi_mult,
            mlbam_id=batter_id, pa_so_far=int(pa), games_played=gp,
        )
        proj_counting["sample_confidence"] = _sample_confidence_label(pa)
        proj_counting["pf_adj_applied"] = False
        proj_counting["steamer_pt_override"] = _STEAMER_PT_OVERRIDE_FLAGS.get(batter_id, False)

        # Park factor adjustment — only for hitters who changed parks this offseason.
        # Scales proj_hr/avg/r/rbi by the ratio of new park to old park.
        # Amplifiers: HR 1.5x (most sensitive), AVG 0.5x, R/RBI 0.7x.
        # Threshold: |pf_delta| >= 0.02 filters trivial moves (e.g. LAD->ATL = 0.00).
        if str(row.get("park_change", "False")).lower() in ("true", "1"):
            _label = str(row.get("park_change_label", ""))
            _m = re.search(r"\((\w+)->", _label)
            if _m:
                _prior_team = _m.group(1)
                _prior_pf   = PARK_FACTORS_PROJ.get(_prior_team, 1.00)
                _curr_pf    = PARK_FACTORS_PROJ.get(team, 1.00)
                _pf_delta   = _curr_pf - _prior_pf
                if abs(_pf_delta) >= _PF_ADJ_THRESHOLD:
                    proj_counting["projected_hr"]  = max(0, round(
                        proj_counting["projected_hr"]  * (1 + _pf_delta * 1.5)))
                    proj_counting["projected_avg"]  = round(min(0.370, max(0.150,
                        proj_counting["projected_avg"] * (1 + _pf_delta * 0.5))), 3)
                    proj_counting["projected_r"]   = max(0, round(
                        proj_counting["projected_r"]   * (1 + _pf_delta * 0.7)))
                    proj_counting["projected_rbi"] = max(0, round(
                        proj_counting["projected_rbi"] * (1 + _pf_delta * 0.7)))
                    proj_counting["pf_adj_applied"] = True

        warnings      = _sanity_check_hitter(proj_counting, row)

        current_stats = {
            "PA":    int(pa),
            "wOBA":  round(_safe_float(row.get("wOBA"),  float("nan")), 3),
            "xwOBA": round(_safe_float(row.get("xwOBA"), float("nan")), 3),
            "BABIP": round(_safe_float(row.get("BABIP"), float("nan")), 3),
            "bb_pct": round(_safe_float(row.get("bb_rate"), float("nan")), 3),
            "k_pct":  round(_safe_float(row.get("k_rate"),  float("nan")), 3),
        }

    else:  # pitcher
        pitcher_id    = int(row.get("pitcher", 0))
        ip            = _safe_float(row.get("IP"), 0.0)
        baseline      = get_pitcher_baseline(pitcher_id, career_data)
        pitcher_rates = career_data.get("pitcher_rates", {})
        true_talent   = pitcher_true_talent(row, baseline, pitcher_rates)
        weight        = sample_weight(ip, is_pitcher=True)

        # Evolution detection — check if pitcher has materially changed since career baseline
        evo_stats = {
            "swstr_gap": _safe_float(row.get("swstr_gap"),  float("nan")),
            "velo_gap":  _safe_float(row.get("velo_gap"),   float("nan")),
            "csw_gap":   _safe_float(row.get("csw_gap"),    float("nan")),
            "k_pct":     _safe_float(row.get("k_pct"),      float("nan")),
        }
        career_pm  = career_data.get("career_pitch_mix",  {}).get(pitcher_id, {})
        current_pm = career_data.get("current_pitch_mix", {}).get(pitcher_id, {})
        evolution  = detect_pitcher_evolution(pitcher_id, evo_stats, career_pm, current_pm)

        # Adjust career weight based on evolution score
        adj = evolution["career_weight_adj"]
        if adj < 0:
            # Discount career — trust current data more
            weight = min(0.85, weight + abs(adj))
        elif adj > 0:
            # Pitcher is declining — trust career baseline more
            weight = max(0.10, weight - adj)

        blended       = blend_projection(true_talent, baseline, weight)
        is_sp         = _is_starter(row)
        current_gs_val    = int(_safe_float(row.get("total_starts", row.get("GS", 0)), 0))
        current_games_val = int(_safe_float(row.get("G", 0), 0))
        _role_overridden  = bool(row.get("role_override", False))
        proj_counting = project_pitcher_counting(
            blended, games_rem, is_sp, signal=verdict,
            mlbam_id=pitcher_id, current_ip=ip,
            current_gs=current_gs_val, current_games=current_games_val,
            role_overridden=_role_overridden,
        )
        proj_counting["sample_confidence"] = _sample_confidence_label(ip, is_pitcher=True)
        warnings      = _sanity_check_pitcher(proj_counting, row)

        current_stats = {
            "IP":    round(ip, 1),
            "ERA":   round(_safe_float(row.get("ERA"),  float("nan")), 2),
            "FIP":   round(_safe_float(row.get("FIP"),  float("nan")), 2),
            "xERA":  round(_safe_float(row.get("xERA"), float("nan")), 2),
            "WHIP":  round(_safe_float(pitcher_rates.get(pitcher_id, {}).get("whip_raw"), float("nan")), 3)
                     if pitcher_rates else float("nan"),
            "swstr_gap":  round(_safe_float(evo_stats["swstr_gap"], float("nan")), 4),
            "velo_gap":   round(_safe_float(evo_stats["velo_gap"],  float("nan")), 2),
        }

    evo_out = evolution if ptype == "pitcher" else {}
    return {
        "name":               player_name,
        "team":               team,
        "type":               ptype,
        "signal":             verdict,
        "luck_score":         round(luck_score, 4),
        "ownership_pct":      round(owned_pct, 1) if owned_pct == owned_pct else float("nan"),
        "current_stats":      current_stats,
        "projected_stats":    proj_counting,
        "confidence":         proj_counting.get("sample_confidence", ""),
        "games_remaining":    games_rem,
        "sanity_warnings":    warnings,
        "evolution_score":    evo_out.get("evolution_score",      0),
        "evolution_flags":    evo_out.get("flags",                []),
        "is_different_pitcher": evo_out.get("is_different_pitcher", False),
        "career_weight_used": weight if ptype == "pitcher" else float("nan"),
    }


# ---------------------------------------------------------------------------
# SECTION G — Net stat comparison for trades
# ---------------------------------------------------------------------------

def _sum_hitter_side(projections: list[dict]) -> dict:
    """Sum counting stats across all hitters on one side.
    Returns None for projected_avg when no hitters are present.
    """
    totals = {k: 0 for k in ["projected_hr", "projected_r", "projected_rbi", "projected_sb"]}
    avg_values = []
    pa_values  = []
    for p in projections:
        if p.get("type") != "hitter" or "projected_stats" not in p:
            continue
        ps = p["projected_stats"]
        for k in totals:
            totals[k] += ps.get(k, 0)
        avg_values.append(ps.get("projected_avg", 0.248))
        pa_values.append(ps.get("projected_pa", 0))

    if not avg_values:
        totals["projected_avg"] = None   # no hitters — not applicable
        return totals

    total_pa = sum(pa_values)
    if total_pa > 0:
        totals["projected_avg"] = round(
            sum(a * p for a, p in zip(avg_values, pa_values)) / total_pa, 3)
    else:
        totals["projected_avg"] = round(sum(avg_values) / len(avg_values), 3)
    return totals


def _sum_pitcher_side(projections: list[dict]) -> dict:
    """Sum/average counting stats across all pitchers on one side."""
    totals = {k: 0 for k in ["projected_k", "projected_w", "projected_sv_h"]}
    era_vals  = []
    whip_vals = []
    ip_vals   = []
    for p in projections:
        if p.get("type") != "pitcher" or "projected_stats" not in p:
            continue
        ps = p["projected_stats"]
        for k in totals:
            totals[k] += ps.get(k, 0)
        era_vals.append(ps.get("projected_era", 4.20))
        whip_vals.append(ps.get("projected_whip", 1.30))
        ip_vals.append(ps.get("projected_ip", 0.0))

    total_ip = sum(ip_vals)
    if total_ip > 0 and era_vals:
        totals["projected_era"]  = round(
            sum(e * i for e, i in zip(era_vals, ip_vals)) / total_ip, 2)
        totals["projected_whip"] = round(
            sum(w * i for w, i in zip(whip_vals, ip_vals)) / total_ip, 3)
    elif era_vals:
        totals["projected_era"]  = round(sum(era_vals)  / len(era_vals), 2)
        totals["projected_whip"] = round(sum(whip_vals) / len(whip_vals), 3)
    else:
        totals["projected_era"]  = float("nan")
        totals["projected_whip"] = float("nan")
    totals["projected_ip"] = round(total_ip, 1)
    return totals


def _signal_summary(projections: list[dict]) -> str:
    counts = {}
    for p in projections:
        sig = p.get("signal", "Neutral")
        counts[sig] = counts.get(sig, 0) + 1
    parts = [f"{v} {k}" for k, v in counts.items() if v > 0]
    return ", ".join(parts) if parts else "N/A"


def _categories_won_lost(net: dict, league_categories: dict
                         ) -> tuple[list[str], list[str]]:
    """Determine which categories favor getting vs giving based on net stats.
    Positive net = getting side wins (except ERA, WHIP where lower = better).
    """
    won, lost = [], []
    reverse_cats = {"projected_era", "projected_whip"}
    for ptype, cats in league_categories.items():
        for cat in cats:
            key = f"projected_{cat.lower().replace('/','_')}"
            val = net.get(key)
            if val is None or (val != val):
                continue
            if key in reverse_cats:
                # Lower ERA/WHIP is better; negative net means getting side has lower ERA
                if val < -0.05:
                    won.append(cat)
                elif val > 0.05:
                    lost.append(cat)
            else:
                if isinstance(val, float):
                    threshold = 0.005
                elif val == 0:
                    pass
                else:
                    threshold = 0
                if isinstance(val, float) and abs(val) < 0.005:
                    pass
                elif val > 0:
                    won.append(cat)
                elif val < 0:
                    lost.append(cat)
    return won, lost


DEFAULT_CATEGORIES = {
    "hitter":  ["AVG", "HR", "R", "RBI", "SB"],
    "pitcher": ["ERA", "WHIP", "K", "W", "SV_H"],
}


def compare_trade(giving_players: list[str],
                  getting_players: list[str],
                  dropping_players: Optional[list[str]] = None,
                  league_categories: Optional[dict] = None) -> dict:
    """Project all players on both sides and compute net stat comparison.
    Dropped players count as a penalty on the get side.
    """
    if league_categories is None:
        league_categories = DEFAULT_CATEGORIES

    cache = _get_cache()

    def _project_all(names: list[str]) -> list[dict]:
        return [project_player(n) for n in names]

    give_proj  = _project_all(giving_players)
    get_proj   = _project_all(getting_players)
    drop_proj  = _project_all(dropping_players) if dropping_players else []

    give_h = _sum_hitter_side(give_proj)
    get_h  = _sum_hitter_side(get_proj)
    drop_h = _sum_hitter_side(drop_proj)

    give_p = _sum_pitcher_side(give_proj)
    get_p  = _sum_pitcher_side(get_proj)
    drop_p = _sum_pitcher_side(drop_proj)

    # Net: getting - giving - drop_penalty (drop = lose their production)
    net = {}
    hitter_count_keys = ["projected_hr", "projected_r", "projected_rbi",
                         "projected_sb", "projected_avg"]
    pitcher_count_keys = ["projected_era", "projected_whip", "projected_k",
                          "projected_w", "projected_sv_h", "projected_ip"]

    for k in hitter_count_keys:
        gv = get_h.get(k)
        gi = give_h.get(k)
        dp = drop_h.get(k) or 0
        # Skip net calc when both sides have no hitters (None means N/A)
        if gv is None and gi is None:
            net[k] = None
            continue
        gv = gv or 0
        gi = gi or 0
        if k == "projected_avg":
            # Weighted by PA; when one side has no hitters treat as neutral
            if gv is None or gi is None:
                net[k] = None
            else:
                net[k] = round(float(gv) - float(gi) - (float(dp) if dp is not None else 0), 4)
        else:
            net[k] = round((gv or 0) - (gi or 0) - (dp or 0), 1)

    for k in pitcher_count_keys:
        gv = get_p.get(k, float("nan"))
        gi = give_p.get(k, float("nan"))
        dp = drop_p.get(k, float("nan"))
        if gv != gv or gi != gi:
            net[k] = float("nan")
        elif k in ("projected_era", "projected_whip"):
            # Rate stats: getting side has an ERA, giving side has an ERA
            # "net" = getting_ERA - giving_ERA; negative = getting has lower ERA = better
            net[k] = round((gv if gv == gv else 4.20) -
                            (gi if gi == gi else 4.20), 3)
        else:
            net[k] = round((gv or 0) - (gi or 0) - (dp or 0), 1)

    won, lost = _categories_won_lost(net, league_categories)

    # Signal verdict (from trade_analyzer logic)
    give_score = sum(p.get("luck_score", 0.0) for p in give_proj) / max(1, len(give_proj))
    get_score  = sum(p.get("luck_score", 0.0) for p in get_proj)  / max(1, len(get_proj))
    delta = get_score - give_score

    if delta >= 0.25:
        signal_verdict = "STRONG TRADE (signal) — clear luck advantage incoming"
    elif delta >= 0.10:
        signal_verdict = "FAVORABLE (signal)"
    elif delta >= 0.03:
        signal_verdict = "SLIGHTLY FAVORABLE (signal)"
    elif delta <= -0.25:
        signal_verdict = "AVOID (signal) — significant luck disadvantage"
    elif delta <= -0.10:
        signal_verdict = "UNFAVORABLE (signal)"
    elif delta <= -0.03:
        signal_verdict = "SLIGHTLY UNFAVORABLE (signal)"
    else:
        signal_verdict = "NEUTRAL (signal)"

    # Projection verdict
    n_won  = len(won)
    n_lost = len(lost)
    total_cats = n_won + n_lost
    if total_cats == 0:
        proj_verdict = "NEUTRAL (projections)"
    elif n_won >= total_cats * 0.65:
        proj_verdict = f"FAVORABLE (projections) — win {n_won}/{total_cats} categories"
    elif n_won <= total_cats * 0.35:
        proj_verdict = f"UNFAVORABLE (projections) — win {n_won}/{total_cats} categories"
    else:
        proj_verdict = f"MIXED (projections) — win {n_won}/{total_cats} categories"

    # Combined verdict
    if "STRONG TRADE" in signal_verdict or "FAVORABLE" in signal_verdict:
        signal_weight = 1
    elif "AVOID" in signal_verdict or "UNFAVORABLE" in signal_verdict:
        signal_weight = -1
    else:
        signal_weight = 0

    if "FAVORABLE" in proj_verdict and "UN" not in proj_verdict:
        proj_weight = 1
    elif "UNFAVORABLE" in proj_verdict:
        proj_weight = -1
    else:
        proj_weight = 0

    combined_score = signal_weight + proj_weight
    if combined_score >= 2:
        combined_verdict = "STRONG TRADE — signal AND projections favor getting side"
    elif combined_score == 1:
        combined_verdict = "FAVORABLE — one dimension favors getting side"
    elif combined_score == -2:
        combined_verdict = "AVOID — signal AND projections favor giving side"
    elif combined_score == -1:
        combined_verdict = "UNFAVORABLE — one dimension favors giving side"
    else:
        combined_verdict = "NEUTRAL — mixed or balanced signals"

    return {
        "giving": {
            "players":        give_proj,
            "total_h_stats":  give_h,
            "total_p_stats":  give_p,
            "signal_summary": _signal_summary(give_proj),
        },
        "getting": {
            "players":        get_proj,
            "total_h_stats":  get_h,
            "total_p_stats":  get_p,
            "signal_summary": _signal_summary(get_proj),
        },
        "dropping": {
            "players":        drop_proj,
            "total_h_stats":  drop_h,
            "total_p_stats":  drop_p,
            "penalty_applied": bool(drop_proj),
        },
        "net_stats":          net,
        "categories_won":     won,
        "categories_lost":    lost,
        "signal_verdict":     signal_verdict,
        "projection_verdict": proj_verdict,
        "combined_verdict":   combined_verdict,
    }
