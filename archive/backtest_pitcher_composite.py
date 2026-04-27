"""
backtest_pitcher_composite.py  (v2 — full 118-column Statcast schema)

Ablation backtest across 2022-2025. Three versions:
  Version A — ERA-FIP signal only  (baseline; reproduces _pitcher_tier_audit.py)
  Version B — Full 8-component composite, flat league-avg baselines
  Version C — Full 8-component composite, per-pitcher career baselines

Components (all from April Statcast — clean, no data leakage):
  1. BABIP allowed vs expected                weight  5.0
  2. LOB% vs 72.4%                            weight -3.0
  3. ERA-FIP gap                              weight  0.15
  4. xwOBA gap (woba - xwoba per PA)          weight  1.5
  5. Hard-hit rate allowed vs baseline        weight -1.5
  6. Barrel rate vs baseline                  weight -1.5
  7. SwStr% vs 11%                            weight  2.0
  8. HR/FB (non-linear, fires above 14%)

Flat baselines (Version B):  BABIP=0.300, HH=0.360, barrel=0.080
Career baselines (Version C): from data/pitcher_career_babip.json

Thresholds (mirrors score_pitcher_luck.py):
  BUY_LOW >= 0.15  |  SLIGHT_BUY >= 0.07
  SELL_HIGH <= -0.15  |  SLIGHT_SELL <= -0.07

IP gates: April >=15 IP, May-Jul >=30 IP  |  ERA_FLAT = 0.40
"""
import json, math, os, sys
import numpy as np
import pandas as pd
from pathlib import Path

# Allow import of _pitcher_tier_audit from archive/ when running from project root
_SCRIPT_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, str(_SCRIPT_DIR))

# ── Imports from _pitcher_tier_audit ─────────────────────────────────────────
from _pitcher_tier_audit import (
    per_start_stats, pitcher_stats, compute_volatility, load_or_fetch,
    CACHE_DIR, P_YEARS, PARK_FACTORS, SIGNAL_MAP, _TIER_DISPLAY,
    ERA_FLAT, MIN_APRIL_IP, MIN_OUTCOME_IP, LEAGUE_AVG_BABIP,
    VOL_DAMP, career_babip_p, career_hh_p, career_barrel_p,
)

BASE_DIR = _SCRIPT_DIR.parent  # project root — data/ and backtest_cache/ live here

# ── Component constants ───────────────────────────────────────────────────────
BABIP_WEIGHT    =  5.0
LOB_WEIGHT      = -3.0
ERA_FIP_WEIGHT  =  0.15
XWOBA_WEIGHT    =  1.5
HH_WEIGHT       = -1.5
BARREL_WEIGHT   = -1.5
SWSTR_WEIGHT    =  2.0

LOB_AVG         = 0.724
SWSTR_AVG       = 0.110
HH_FLAT         = 0.360
BARREL_FLAT     = 0.080

COMP_BUY_LOW    =  0.15
COMP_SLIGHT_BUY =  0.07
COMP_SLIGHT_SELL= -0.07
COMP_SELL_HIGH  = -0.15

TIERS      = ["BUY_LOW", "SLIGHT_BUY", "SLIGHT_SELL", "SELL_HIGH"]
RTM_BASELINE = 0.70

# xwOBA -> xERA linear conversion (fitted from FG data >=200 PA, R2=0.98)
XWOBA_TO_XERA_COEF      = 28.3336
XWOBA_TO_XERA_INTERCEPT = -4.7463


# ── Age adjustment ────────────────────────────────────────────────────────────
def _babip_age_mult(age: int) -> float:
    if age >= 38: return 1.06
    if age >= 36: return 1.04
    if age >= 33: return 1.02
    return 1.0


def _load_birth_years() -> dict:
    path = BASE_DIR / "data" / "career_stats.json"
    if not path.exists():
        return {}
    with open(path) as f:
        cs = json.load(f)
    return {int(k): int(v.get("birth_year") or 0) for k, v in cs.items()}


_BIRTH_YEARS = _load_birth_years()


def _load_career_ip() -> dict:
    """Returns {mlbam_id: career_ip} for pitchers in career_stats.json."""
    path = BASE_DIR / "data" / "career_stats.json"
    if not path.exists():
        return {}
    with open(path) as f:
        cs = json.load(f)
    return {int(k): float(v.get("career_ip") or 0)
            for k, v in cs.items() if v.get("career_ip")}


def _load_fg_xera(year: int) -> dict:
    """
    Returns {mlbam_id: xera} from fg_pitching_{year}.csv.
    pitcher_id in these files is the MLBAM ID (confirmed).
    Full-season proxy — used only as a quality gate, not a scored component.
    """
    path = BASE_DIR / "data" / f"fg_pitching_{year}.csv"
    if not path.exists():
        return {}
    df = pd.read_csv(path)
    if "pitcher_id" not in df.columns or "xera" not in df.columns:
        return {}
    return {int(r["pitcher_id"]): float(r["xera"])
            for _, r in df.iterrows()
            if pd.notna(r.get("xera"))}


_CAREER_IP = _load_career_ip()


def _is_buy_qualified(fip: float, xera: float, swstr: float,
                      career_ip: float, gb_pct: float = float("nan")) -> bool:
    """
    Replicates score_pitcher_luck.py is_buy_qualified().
    Gates: FIP <= 4.50, xERA <= 4.75, SwStr% >= 8%, career_ip >= 100.
    Carve-outs: FIP <= 3.50 waives xERA gate; GB% > 52% waives SwStr% gate.
    """
    try:
        fip_f   = float(fip)
        xera_f  = float(xera)
        swstr_f = float(swstr)
    except (TypeError, ValueError):
        return False
    if math.isnan(fip_f) or fip_f > 4.50:
        return False
    fip_carveout = fip_f <= 3.50
    if not fip_carveout:
        if math.isnan(xera_f) or xera_f > 4.75:
            return False
    try:
        gb_f = float(gb_pct)
        gb_carveout = not math.isnan(gb_f) and gb_f > 0.52
    except (TypeError, ValueError):
        gb_carveout = False
    if not gb_carveout:
        if math.isnan(swstr_f) or swstr_f < 0.08:
            return False
    return float(career_ip) >= 100


# ── HR/FB component (non-linear, from score_pitcher_luck.py) ─────────────────
def _hrfb_component(hr_fb: float, hard_hit: float) -> float:
    try:
        hrf = float(hr_fb)
    except (TypeError, ValueError):
        return 0.0
    if pd.isna(hrf) or hrf <= 0.14:
        return 0.0
    base = (hrf - 0.12) * 2.0
    try:
        hh = float(hard_hit)
    except (TypeError, ValueError):
        hh = 0.33
    if pd.isna(hh): hh = 0.33
    if hh > 0.38:   base *= 0.65
    elif hh < 0.28: base *= 1.25
    return base


# ── Signal classifiers ────────────────────────────────────────────────────────
def _classify_era_fip(gap: float) -> str:
    if gap >=  1.20: return "BUY_LOW"
    if gap >=  0.60: return "SLIGHT_BUY"
    if gap <= -1.20: return "SELL_HIGH"
    if gap <= -0.60: return "SLIGHT_SELL"
    return "NEUTRAL"


def _classify_composite(score: float) -> str:
    if score >=  COMP_BUY_LOW:     return "BUY_LOW"
    if score >=  COMP_SLIGHT_BUY:  return "SLIGHT_BUY"
    if score <=  COMP_SELL_HIGH:   return "SELL_HIGH"
    if score <=  COMP_SLIGHT_SELL: return "SLIGHT_SELL"
    return "NEUTRAL"


# Version E: production-aligned gates (3-mismatch alignment fix, April 24 2026)
# MISMATCH 1: separate ERA floors — 3.50 all buys, 4.00 Slight Buy only
# MISMATCH 2: confidence-scaled score (luck_score thresholds 0.065/0.150)
# MISMATCH 3: buy_qualification gate fires before ERA gate (inside prescore)
# Apr 25 2026: Buy Low ERA floor raised 3.50 → 3.75 (sensitivity confirmed +7.3pp OOS)
E_BUY_LOW    =  0.50    # raw fallback threshold (_classify_split_calibrated only)
E_SLIGHT_BUY =  0.30    # raw fallback threshold (_classify_split_calibrated only)
E_MIN_BUY_IP =  20.0
E_ERA_FLOOR            =  3.50   # all buys: ERA must be above true talent
E_BUY_LOW_ERA_FLOOR    =  3.75   # Buy Low additionally requires ERA >= 3.75
E_SLIGHT_BUY_ERA_FLOOR =  4.00   # Slight Buy additionally requires ERA >= 4.00
E_BUY_LOW_LS           =  0.150  # post-confidence Buy Low threshold
E_SLIGHT_BUY_LS        =  0.065  # post-confidence Slight Buy threshold


def _april_conf_scale(ip: float) -> float:
    """April (season_day=30) confidence scale: floor 0.25 for IP >= 15."""
    if ip < 15.0:
        return 0.0
    return min(1.0, max(0.25, (ip - 15.0) / 40.0))


def _classify_split_calibrated(score: float) -> str:
    if score >=  E_BUY_LOW:        return "BUY_LOW"
    if score >=  E_SLIGHT_BUY:     return "SLIGHT_BUY"
    if score <=  COMP_SELL_HIGH:   return "SELL_HIGH"
    if score <=  COMP_SLIGHT_SELL: return "SLIGHT_SELL"
    return "NEUTRAL"


# ── Extra stats from full-schema Statcast ────────────────────────────────────
def compute_extra_stats(sc: pd.DataFrame) -> pd.DataFrame:
    """
    Computes per-pitcher validator components from 118-column Statcast.
    Returns DataFrame indexed by pitcher with columns:
      swstr_rate, lob_pct, hh_rate, barrel_rate, xwoba_gap, gb_pct, hr_fb_rate
    Returns empty DataFrame if required columns are absent.
    """
    required = {"description", "launch_speed", "bb_type", "woba_value",
                "estimated_woba_using_speedangle", "events",
                "post_bat_score", "bat_score"}
    missing = required - set(sc.columns)
    if missing:
        return pd.DataFrame()

    sc = sc.copy()
    sc["pitcher"] = pd.to_numeric(sc["pitcher"], errors="coerce")
    sc = sc[sc["pitcher"].notna()].copy()
    sc["pitcher"] = sc["pitcher"].astype(int)

    results = {}

    # ── SwStr% (all pitches) ──────────────────────────────────────────────────
    total_pitches = sc.groupby("pitcher").size()
    swstr_mask    = sc["description"].isin({"swinging_strike", "swinging_strike_blocked"})
    swstr_count   = sc[swstr_mask].groupby("pitcher").size()
    results["swstr_rate"] = (swstr_count / total_pitches).fillna(0).round(4)

    # ── HH% and Barrel% (batted balls with launch_speed) ────────────────────
    bip = sc[sc["launch_speed"].notna() & (sc["launch_speed"] > 0)].copy()
    bip_count = bip.groupby("pitcher").size().rename("bip_count")

    hh = bip[bip["launch_speed"] >= 95]
    results["hh_rate"] = (
        hh.groupby("pitcher").size() / bip_count
    ).fillna(0).round(4)

    if "launch_speed_angle" in sc.columns:
        barrel_mask = sc["launch_speed_angle"] == 6
        barrel_bip  = sc[barrel_mask & sc["launch_speed"].notna()]
        results["barrel_rate"] = (
            barrel_bip.groupby("pitcher").size() / bip_count
        ).fillna(0).round(4)
    else:
        # Approximate barrel: EV >= 98 AND launch_angle 26-30
        if "launch_angle" in sc.columns:
            barrel_approx = bip[
                (bip["launch_speed"] >= 98) &
                (bip["launch_angle"] >= 26) & (bip["launch_angle"] <= 30)
            ]
            results["barrel_rate"] = (
                barrel_approx.groupby("pitcher").size() / bip_count
            ).fillna(0).round(4)
        else:
            results["barrel_rate"] = pd.Series(dtype=float)

    # ── GB% ───────────────────────────────────────────────────────────────────
    bb_type_valid = sc[sc["bb_type"].notna()]
    bb_count = bb_type_valid.groupby("pitcher").size()
    gb_count = bb_type_valid[bb_type_valid["bb_type"] == "ground_ball"].groupby("pitcher").size()
    results["gb_pct"] = (gb_count / bb_count).fillna(0).round(4)

    # ── HR/FB rate ────────────────────────────────────────────────────────────
    # In Statcast, HRs have bb_type = 'fly_ball'; fly balls include HRs
    fb_mask = bb_type_valid["bb_type"] == "fly_ball"
    fb_count = bb_type_valid[fb_mask].groupby("pitcher").size()
    ev_valid = sc[sc["events"].notna() & (sc["events"] != "")]
    hr_count = ev_valid[ev_valid["events"] == "home_run"].groupby("pitcher").size()
    results["hr_fb_rate"] = (hr_count / fb_count).fillna(0).clip(upper=1.0).round(4)

    # ── xwOBA gap (woba_value - estimated_woba per qualifying PA) ─────────────
    if "woba_denom" in sc.columns:
        pa = sc[sc["woba_denom"] == 1].copy()
    else:
        NON_PA = {"pickoff_1b","pickoff_2b","pickoff_3b",
                  "caught_stealing_2b","caught_stealing_3b","caught_stealing_home",
                  "stolen_base_2b","stolen_base_3b","stolen_base_home",
                  "other_out","game_advisory","balk","passed_ball","wild_pitch",
                  "pitchout"}
        pa = sc[sc["events"].notna() & ~sc["events"].isin(NON_PA)].copy()

    pa["xwoba_pa"] = pa["estimated_woba_using_speedangle"].fillna(pa["woba_value"])
    xwoba_allowed  = pa.groupby("pitcher")["xwoba_pa"].mean()
    woba_allowed   = pa.groupby("pitcher")["woba_value"].mean()
    results["xwoba_allowed"] = xwoba_allowed.round(4)
    results["xwoba_gap"] = (woba_allowed - xwoba_allowed).round(4)

    # ── LOB%  = (H + BB + HBP - RA) / (H + BB + HBP - 1.4*HR) ──────────────
    ev = sc[sc["events"].notna() & (sc["events"] != "")].copy()
    ev_g = ev.groupby("pitcher")

    H   = ev_g.apply(lambda d: d["events"].isin(
          {"single","double","triple","home_run"}).sum()).rename("H")
    BB  = ev_g.apply(lambda d: d["events"].isin(
          {"walk","intent_walk"}).sum()).rename("BB")
    HBP = ev_g.apply(lambda d: (d["events"] == "hit_by_pitch").sum()).rename("HBP")
    HR  = ev_g.apply(lambda d: (d["events"] == "home_run").sum()).rename("HR")

    re       = ev[ev["post_bat_score"].notna() & ev["bat_score"].notna()].copy()
    re["runs"] = (re["post_bat_score"] - re["bat_score"]).clip(lower=0)
    RA = re.groupby("pitcher")["runs"].sum().rename("RA")

    lob_df    = pd.concat([H, BB, HBP, HR, RA], axis=1).fillna(0)
    numerator = lob_df["H"] + lob_df["BB"] + lob_df["HBP"] - lob_df["RA"]
    denominator = lob_df["H"] + lob_df["BB"] + lob_df["HBP"] - 1.4 * lob_df["HR"]
    lob_raw   = (numerator / denominator).replace([np.inf, -np.inf], np.nan)
    results["lob_pct"] = lob_raw.clip(0.0, 1.0).round(4)

    out = pd.DataFrame(results)
    out.index.name = "pitcher"
    return out.reset_index()


# ── Full-schema Statcast loader (bypasses NEEDED_COLS filter) ─────────────────
def _load_full_parquet(path: Path) -> pd.DataFrame:
    """Read parquet without any column filtering."""
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


# ── Per-year data loader ──────────────────────────────────────────────────────
def _load_year_data(year: int):
    apr_cache = CACHE_DIR / f"pitcher_statcast_april_{year}.parquet"
    out_cache = CACHE_DIR / f"pitcher_statcast_mayjuly_{year}.parquet"
    if not apr_cache.exists() or not out_cache.exists():
        print(f"  {year}: missing parquet(s) — skip")
        return None

    # Load raw full-schema for extra stats; load_or_fetch gives filtered 10-col for ERA/FIP/BABIP
    apr_sc_full = _load_full_parquet(apr_cache)
    out_sc_full = _load_full_parquet(out_cache)

    # Use load_or_fetch for the 10-col subset (ERA/FIP/BABIP computation)
    apr_sc = load_or_fetch(apr_cache, f"{year}-04-01", f"{year}-04-30", f"April {year}")
    out_sc = load_or_fetch(out_cache, f"{year}-05-01", f"{year}-07-31", f"May-Jul {year}")

    if apr_sc.empty or out_sc.empty:
        return None

    apr_starts = per_start_stats(apr_sc)
    apr_stats  = pitcher_stats(apr_sc, apr_starts)
    out_stats  = pitcher_stats(out_sc, per_start_stats(out_sc))

    apr_stats = apr_stats[apr_stats["ip"] >= MIN_APRIL_IP].copy()
    out_stats = out_stats[out_stats["ip"] >= MIN_OUTCOME_IP].copy()

    vol_df = compute_volatility(apr_starts) if not apr_starts.empty else pd.DataFrame()

    # Extra stats from full-schema
    col_count = len(apr_sc_full.columns)
    if col_count >= 100:
        extra = compute_extra_stats(apr_sc_full)
        print(f"  Extra stats computed from {col_count}-col parquet "
              f"({extra['pitcher'].nunique() if not extra.empty else 0} pitchers)")
    else:
        extra = pd.DataFrame()
        print(f"  WARNING: {year} parquet has only {col_count} cols — extra stats skipped")

    return apr_stats, out_stats, vol_df, extra


# ── Composite score computation ───────────────────────────────────────────────
def _add_composite_scores(sig: pd.DataFrame, extra: pd.DataFrame, year: int) -> pd.DataFrame:
    """
    Adds composite_b and composite_c to sig.
    extra: per-pitcher DataFrame from compute_extra_stats (may be empty).
    """
    sig = sig.copy()

    park     = sig["p_team"].map(PARK_FACTORS).fillna(1.0) if "p_team" in sig.columns else pd.Series(1.0, index=sig.index)
    sig["_park"] = park

    def _age_mult(pid):
        by = _BIRTH_YEARS.get(int(pid), 0)
        return _babip_age_mult(year - by) if by > 0 else 1.0

    sig["_age_mult"] = sig["pitcher"].apply(_age_mult)

    # Merge extra validator components if available
    has_extra = not extra.empty and "pitcher" in extra.columns
    if has_extra:
        merge_cols = ["pitcher","swstr_rate","lob_pct","hh_rate",
                      "barrel_rate","xwoba_allowed","xwoba_gap","hr_fb_rate"]
        sig = sig.merge(extra[[c for c in merge_cols if c in extra.columns]],
                        on="pitcher", how="left")
    else:
        for col in ["swstr_rate","lob_pct","hh_rate","barrel_rate",
                    "xwoba_allowed","xwoba_gap","hr_fb_rate"]:
            sig[col] = float("nan")

    # ── BABIP component ───────────────────────────────────────────────────────
    babip_expected_b = LEAGUE_AVG_BABIP  * sig["_park"] * sig["_age_mult"]
    career_babip_vals= sig["pitcher"].map(career_babip_p).fillna(LEAGUE_AVG_BABIP)
    babip_expected_c = career_babip_vals * sig["_park"] * sig["_age_mult"]

    babip_comp_b = (sig["babip"] - babip_expected_b) * BABIP_WEIGHT
    babip_comp_c = (sig["babip"] - babip_expected_c) * BABIP_WEIGHT

    # ── LOB% component ────────────────────────────────────────────────────────
    lob_comp = (sig["lob_pct"].fillna(LOB_AVG) - LOB_AVG) * LOB_WEIGHT

    # ── ERA-FIP component ─────────────────────────────────────────────────────
    era_fip_comp = sig["era_fip_gap"] * ERA_FIP_WEIGHT

    # ── xwOBA gap component ───────────────────────────────────────────────────
    xwoba_comp = sig["xwoba_gap"].fillna(0.0) * XWOBA_WEIGHT

    # ── HH% component (B: flat baseline, C: career baseline) ─────────────────
    hh_baseline_b = HH_FLAT
    hh_baseline_c = sig["pitcher"].map(career_hh_p).fillna(HH_FLAT)
    hh_comp_b = (sig["hh_rate"].fillna(hh_baseline_b) - hh_baseline_b) * HH_WEIGHT
    hh_comp_c = (sig["hh_rate"].fillna(hh_baseline_c) - hh_baseline_c) * HH_WEIGHT

    # ── Barrel% component (B: flat, C: career) ───────────────────────────────
    barrel_baseline_b = BARREL_FLAT
    barrel_baseline_c = sig["pitcher"].map(career_barrel_p).fillna(BARREL_FLAT)
    barrel_comp_b = (sig["barrel_rate"].fillna(barrel_baseline_b) - barrel_baseline_b) * BARREL_WEIGHT
    barrel_comp_c = (sig["barrel_rate"].fillna(barrel_baseline_c) - barrel_baseline_c) * BARREL_WEIGHT

    # ── SwStr% component ─────────────────────────────────────────────────────
    swstr_comp = (sig["swstr_rate"].fillna(SWSTR_AVG) - SWSTR_AVG) * SWSTR_WEIGHT

    # ── HR/FB non-linear component ────────────────────────────────────────────
    hrfb_comp = sig.apply(
        lambda r: _hrfb_component(r.get("hr_fb_rate", float("nan")),
                                   r.get("hh_rate", float("nan"))),
        axis=1
    )

    sig["composite_b"] = (
        babip_comp_b + lob_comp + era_fip_comp + xwoba_comp
        + hh_comp_b + barrel_comp_b + swstr_comp + hrfb_comp
    ).round(4)

    sig["composite_c"] = (
        babip_comp_c + lob_comp + era_fip_comp + xwoba_comp
        + hh_comp_c + barrel_comp_c + swstr_comp + hrfb_comp
    ).round(4)

    # ── Version D: split scorer (mirrors score_pitcher_luck.py split logic) ──
    # sell_score: full 8-component (career baselines, no xwOBA gap per spec)
    # buy_score:  ERA-FIP dominant 3-component
    sell_d = (babip_comp_c + lob_comp + era_fip_comp
              + hh_comp_c + barrel_comp_c + swstr_comp + hrfb_comp)
    buy_d  = (sig["era_fip_gap"] * 0.60
              + sig["xwoba_gap"].fillna(0.0) * 0.25
              + (sig["babip"] - babip_expected_c) * 0.15)
    era_fip_tie = sig["era_fip_gap"] * ERA_FIP_WEIGHT
    conflict = (sell_d < 0) & (buy_d > 0)

    composite_d = pd.Series(0.0, index=sig.index)
    composite_d = composite_d.where(~(buy_d > 0), buy_d)
    composite_d = composite_d.where(~(sell_d < 0), sell_d)
    composite_d = composite_d.where(~conflict, era_fip_tie)
    sig["composite_d"] = composite_d.round(4)
    # Save raw components for Version E pre-scaling classification
    sig["_buy_d_raw"]  = buy_d.round(4)
    sig["_sell_d_raw"] = sell_d.round(4)

    sig.drop(columns=["_park", "_age_mult"], inplace=True)
    return sig


# ── Per-year ablation runner ──────────────────────────────────────────────────
def run_year(year: int):
    result = _load_year_data(year)
    if result is None:
        return None
    apr_stats, out_stats, vol_df, extra = result

    sig = apr_stats.copy()
    sig["era_fip_gap"] = sig["era"] - sig["fip"]

    sig["career_hh_allowed"]     = sig["pitcher"].map(career_hh_p)
    sig["career_barrel_allowed"] = sig["pitcher"].map(career_barrel_p)

    if not vol_df.empty:
        sig = sig.merge(vol_df[["pitcher","volatility_flag"]], on="pitcher", how="left")
        sig["volatility_flag"] = sig["volatility_flag"].fillna(False)
    else:
        sig["volatility_flag"] = False

    sig["signal_a"] = sig["era_fip_gap"].apply(_classify_era_fip)

    sig = _add_composite_scores(sig, extra, year)

    # Volatility dampen on composite buy signals
    for col in ["composite_b", "composite_c"]:
        mask = sig["volatility_flag"] & (sig[col] > 0)
        sig.loc[mask, col] = (sig.loc[mask, col] * VOL_DAMP).round(4)

    sig["signal_b"] = sig["composite_b"].apply(_classify_composite)
    sig["signal_c"] = sig["composite_c"].apply(_classify_composite)
    sig["signal_d"] = sig["composite_d"].apply(_classify_composite)

    # Pre-compute qualification fields before _e_prescore so MISMATCH 3 fix
    # (buy_qualification before ERA gate) can be applied inside the prescore function.
    if "xwoba_allowed" in sig.columns:
        sig["april_xera"] = (
            XWOBA_TO_XERA_COEF * sig["xwoba_allowed"] + XWOBA_TO_XERA_INTERCEPT
        ).round(3)
    else:
        sig["april_xera"] = float("nan")
    sig["career_ip_g"] = sig["pitcher"].map(_CAREER_IP).fillna(0.0)
    sig["xera_g"]      = sig["april_xera"]

    # Version E: production-aligned scoring with all 3 mismatch fixes applied.
    def _e_prescore(row):
        bs  = float(row.get("_buy_d_raw") or 0.0)
        ss  = float(row.get("_sell_d_raw") or 0.0)
        ip  = float(row.get("ip") or 0.0)
        era = float(row.get("era") or 0.0)
        fip_r = float(row.get("fip") or float("nan"))
        if bs > 0 and ss >= 0:
            dominant_buy = bs >= 1.50
            # FIX 1: IP floor for buy signals
            if ip < E_MIN_BUY_IP and not dominant_buy:
                return "NEUTRAL"
            if ip < E_MIN_BUY_IP and not pd.isna(fip_r) and fip_r < 1.50:
                return "NEUTRAL"
            # MISMATCH 3: buy_qualification gate fires before ERA gate
            xera_r    = row.get("xera_g",    float("nan"))
            swstr_r   = row.get("swstr_rate", float("nan"))
            gb_r      = row.get("gb_pct",     float("nan"))
            career_ip = float(row.get("career_ip_g", 0.0))
            if not _is_buy_qualified(fip_r, xera_r, swstr_r, career_ip, gb_r):
                return "NEUTRAL"
            # FIX 2: ERA floor for all buys
            if era < E_ERA_FLOOR:
                return "NEUTRAL"
            # FIX 3: FIP/xERA confluence (moved inside prescore; waived for dominant buys)
            xera_f = float(xera_r) if (xera_r is not None and not pd.isna(xera_r)) else float("nan")
            if (not dominant_buy and not math.isnan(xera_f) and not pd.isna(fip_r)
                    and abs(fip_r - xera_f) > 1.50 and xera_f > 4.50
                    and float(row.get("era_fip_gap", 0.0)) < 2.50):
                return "NEUTRAL"
            # MISMATCH 2: confidence-scaled classification using luck_score thresholds
            scaled = bs * _april_conf_scale(ip)
            if scaled >= E_BUY_LOW_LS:
                # Buy Low requires ERA >= 3.75 (sensitivity confirmed +7.3pp OOS, Apr 25 2026)
                if era < E_BUY_LOW_ERA_FLOOR:
                    return "NEUTRAL"
                return "BUY_LOW"
            if scaled >= E_SLIGHT_BUY_LS:
                # MISMATCH 1: Slight Buy requires ERA >= 4.00
                if era < E_SLIGHT_BUY_ERA_FLOOR:
                    return "NEUTRAL"
                return "SLIGHT_BUY"
        return _classify_split_calibrated(row["composite_d"])

    sig["signal_e"] = sig.apply(_e_prescore, axis=1)

    # ── Buy qualification gate (Versions B, C, D — Version E handles internally) ──
    # april_xera, career_ip_g, xera_g already computed above for _e_prescore.
    # FIX 3 for Version E is now inside _e_prescore; no external pass needed.
    buy_signals = {"BUY_LOW", "SLIGHT_BUY"}

    swstr_col = "swstr_rate" if "swstr_rate" in sig.columns else None
    gb_col    = "gb_pct"    if "gb_pct"    in sig.columns else None

    def _gate(row) -> bool:
        return _is_buy_qualified(
            fip      = row.get("fip", float("nan")),
            xera     = row.get("xera_g", float("nan")),
            swstr    = row.get(swstr_col, float("nan")) if swstr_col else float("nan"),
            career_ip= row["career_ip_g"],
            gb_pct   = row.get(gb_col, float("nan")) if gb_col else float("nan"),
        )

    qualified = sig.apply(_gate, axis=1)

    for sig_col in ("signal_b", "signal_c", "signal_d"):
        is_buy   = sig[sig_col].isin(buy_signals)
        override = is_buy & ~qualified
        sig.loc[override, sig_col] = "NEUTRAL"
        n_override = override.sum()
        if n_override:
            print(f"  Buy gate ({sig_col}): {n_override} overridden to NEUTRAL")

    sig.drop(columns=["career_ip_g", "xera_g", "april_xera",
                      "_buy_d_raw", "_sell_d_raw"], inplace=True, errors="ignore")

    merged = sig.merge(
        out_stats[["pitcher","era","ip"]].rename(
            columns={"era":"outcome_era","ip":"outcome_ip"}),
        on="pitcher", how="inner"
    )
    merged["era_change"] = merged["outcome_era"] - merged["era"]
    merged["outcome"] = np.where(
        merged["era_change"] <= -ERA_FLAT, "IMPROVED",
        np.where(merged["era_change"] >= ERA_FLAT, "DECLINED", "FLAT")
    )
    merged["year"] = year
    return merged


# ── Table printing ────────────────────────────────────────────────────────────
def _print_version_table(all_df: pd.DataFrame, signal_col: str, label: str):
    years = sorted(all_df["year"].unique())
    col_w, sig_w, delta_w = 18, 13, 10

    header = " | ".join(
        [f"{'Signal':<{sig_w}}"]
        + [f"{str(y):^{col_w}}" for y in years]
        + [f"{'4-Yr Avg':^{col_w}}", f"{'Avg ERA d':^{delta_w}}"]
    )
    sep = "-" * len(header)
    print(f"\n{label}")
    print(sep); print(header); print(sep)

    for tier_key in TIERS:
        display = _TIER_DISPLAY[tier_key]
        row = [f"{display:<{sig_w}}"]
        for y in years:
            sub_e = all_df[(all_df["year"] == y) & (all_df[signal_col] == tier_key)
                           & (all_df["outcome"] != "FLAT")]
            if len(sub_e) == 0:
                row.append(f"{'—':^{col_w}}"); continue
            expected = SIGNAL_MAP[tier_key]
            corr = (sub_e["outcome"] == expected).sum()
            row.append(f"{corr/len(sub_e)*100:.1f}% (n={len(sub_e)})".center(col_w))

        sub4e = all_df[(all_df[signal_col] == tier_key) & (all_df["outcome"] != "FLAT")]
        if len(sub4e):
            expected = SIGNAL_MAP[tier_key]
            corr4 = (sub4e["outcome"] == expected).sum()
            d4    = sub4e[sub4e["outcome"] == expected]["era_change"].mean()
            row.append(f"{corr4/len(sub4e)*100:.1f}%".center(col_w))
            row.append(f"{d4:+.2f}".center(delta_w))
        else:
            row.append(f"{'—':^{col_w}}"); row.append(f"{'—':^{delta_w}}")
        print(" | ".join(row))

    print(sep)
    yr_accs = {}
    ov_row = [f"{'Overall':<{sig_w}}"]
    for y in years:
        sub = all_df[(all_df["year"] == y) & all_df[signal_col].isin(SIGNAL_MAP)
                     & (all_df["outcome"] != "FLAT")].copy()
        sub["correct"] = sub.apply(lambda r: r["outcome"] == SIGNAL_MAP.get(r[signal_col],""), axis=1)
        if len(sub) == 0:
            ov_row.append(f"{'—':^{col_w}}"); yr_accs[y] = None; continue
        acc = sub["correct"].sum() / len(sub)
        yr_accs[y] = acc
        ov_row.append(f"{acc*100:.1f}% (n={len(sub)})".center(col_w))

    ov4 = all_df[all_df[signal_col].isin(SIGNAL_MAP) & (all_df["outcome"] != "FLAT")].copy()
    ov4["correct"] = ov4.apply(lambda r: r["outcome"] == SIGNAL_MAP.get(r[signal_col],""), axis=1)
    ov4_acc = ov4["correct"].sum() / len(ov4) if len(ov4) > 0 else float("nan")
    ov_row += [f"{ov4_acc*100:.1f}%".center(col_w), f"{'':^{delta_w}}"]
    print(" | ".join(ov_row))

    rtm_row = [f"{'vs. RTM':^{sig_w}}"]
    for y in years:
        a = yr_accs.get(y)
        rtm_row.append(f"{(a - RTM_BASELINE)*100:+.1f}pp".center(col_w) if a else f"{'—':^{col_w}}")
    rtm_row += [f"{(ov4_acc - RTM_BASELINE)*100:+.1f}pp".center(col_w), f"{'':^{delta_w}}"]
    print(" | ".join(rtm_row))
    print(sep)


# ── Soft-contact cohort (Task 7) ──────────────────────────────────────────────
def print_softcontact_table(all_df: pd.DataFrame, signal_col: str = "signal_c",
                             hh_thresh: float = 0.35):
    sub = all_df[all_df["career_hh_allowed"] < hh_thresh].copy()
    years = sorted(sub["year"].unique())
    col_w, sig_w, delta_w = 18, 13, 10
    header = " | ".join(
        [f"{'Signal':<{sig_w}}"]
        + [f"{str(y):^{col_w}}" for y in years]
        + [f"{'4-Yr Avg':^{col_w}}", f"{'Avg ERA d':^{delta_w}}"]
    )
    sep = "-" * len(header)
    print(f"\nSoft-Contact Cohort (career HH% < {hh_thresh:.0%}) | Version C")
    print(f"  {sub['pitcher'].nunique()} unique pitchers | {len(sub)} player-seasons")
    print(sep); print(header); print(sep)

    for tier_key in TIERS:
        display = _TIER_DISPLAY[tier_key]
        row = [f"{display:<{sig_w}}"]
        for y in years:
            sub_e = sub[(sub["year"] == y) & (sub[signal_col] == tier_key)
                        & (sub["outcome"] != "FLAT")]
            if len(sub_e) == 0:
                row.append(f"{'—':^{col_w}}"); continue
            expected = SIGNAL_MAP[tier_key]
            corr = (sub_e["outcome"] == expected).sum()
            row.append(f"{corr/len(sub_e)*100:.1f}% (n={len(sub_e)})".center(col_w))

        t4e = sub[(sub[signal_col] == tier_key) & (sub["outcome"] != "FLAT")]
        if len(t4e):
            expected = SIGNAL_MAP[tier_key]
            corr4 = (t4e["outcome"] == expected).sum()
            d4    = t4e[t4e["outcome"] == expected]["era_change"].mean()
            row += [f"{corr4/len(t4e)*100:.1f}%".center(col_w), f"{d4:+.2f}".center(delta_w)]
        else:
            row += [f"{'—':^{col_w}}", f"{'—':^{delta_w}}"]
        print(" | ".join(row))
    print(sep)


# ── CSV saving ────────────────────────────────────────────────────────────────
def save_csvs(all_df: pd.DataFrame):
    DATA_DIR = BASE_DIR / "data"
    version_map = {"A": "signal_a", "B": "signal_b", "C": "signal_c", "D": "signal_d", "E": "signal_e"}
    rows = []
    for ver, sig_col in version_map.items():
        for year in sorted(all_df["year"].unique()):
            yr = all_df[all_df["year"] == year]
            for tier_key in TIERS:
                display = _TIER_DISPLAY[tier_key]
                sub = yr[(yr[sig_col] == tier_key) & (yr["outcome"] != "FLAT")]
                n   = len(sub)
                if n == 0:
                    rows.append({"year": year, "version": ver, "tier": display,
                                 "n": 0, "correct": 0, "accuracy": float("nan"),
                                 "era_delta": float("nan")}); continue
                expected = SIGNAL_MAP[tier_key]
                correct  = int((sub["outcome"] == expected).sum())
                era_d    = sub[sub["outcome"] == expected]["era_change"].mean()
                rows.append({"year": year, "version": ver, "tier": display,
                             "n": n, "correct": correct,
                             "accuracy": round(correct / n, 4),
                             "era_delta": round(float(era_d), 3) if pd.notna(era_d) else float("nan")})

    df_out = pd.DataFrame(rows)
    p1 = DATA_DIR / "backtest_composite_pitcher.csv"
    df_out.to_csv(p1, index=False)
    print(f"Saved: {p1} ({len(df_out)} rows)")

    summary_rows = []
    for ver, sig_col in version_map.items():
        ov = all_df[all_df[sig_col].isin(SIGNAL_MAP) & (all_df["outcome"] != "FLAT")].copy()
        ov["correct"] = ov.apply(lambda r: r["outcome"] == SIGNAL_MAP.get(r[sig_col],""), axis=1)
        ov_acc = ov["correct"].sum() / len(ov) if len(ov) > 0 else float("nan")
        for tier_key in TIERS:
            display = _TIER_DISPLAY[tier_key]
            sub = all_df[(all_df[sig_col] == tier_key) & (all_df["outcome"] != "FLAT")]
            if len(sub) == 0:
                summary_rows.append({"version": ver, "tier": display,
                                     "4yr_weighted_accuracy": float("nan"),
                                     "avg_era_delta": float("nan"),
                                     "vs_donothing_pp": float("nan")}); continue
            expected = SIGNAL_MAP[tier_key]
            corr  = (sub["outcome"] == expected).sum()
            acc   = corr / len(sub)
            era_d = sub[sub["outcome"] == expected]["era_change"].mean()
            summary_rows.append({"version": ver, "tier": display,
                                  "4yr_weighted_accuracy": round(acc, 4),
                                  "avg_era_delta": round(float(era_d), 3) if pd.notna(era_d) else float("nan"),
                                  "vs_donothing_pp": round((acc - RTM_BASELINE) * 100, 1)})
        summary_rows.append({"version": ver, "tier": "Overall",
                              "4yr_weighted_accuracy": round(ov_acc, 4),
                              "avg_era_delta": float("nan"),
                              "vs_donothing_pp": round((ov_acc - RTM_BASELINE) * 100, 1)})

    p2 = DATA_DIR / "backtest_composite_summary.csv"
    pd.DataFrame(summary_rows).to_csv(p2, index=False)
    print(f"Saved: {p2}")


# ── Comparison table (Task 8) ─────────────────────────────────────────────────
def print_comparison_table(all_df: pd.DataFrame):
    version_map = {"A": "signal_a", "B": "signal_b", "C": "signal_c", "D": "signal_d", "E": "signal_e"}
    col_w = 20

    stats = {}
    for ver, sig_col in version_map.items():
        d = {}
        for tier_key in TIERS:
            display = _TIER_DISPLAY[tier_key]
            sub = all_df[(all_df[sig_col] == tier_key) & (all_df["outcome"] != "FLAT")]
            if len(sub) == 0:
                d[display] = float("nan"); continue
            expected = SIGNAL_MAP[tier_key]
            d[display] = (sub["outcome"] == expected).sum() / len(sub)
        ov = all_df[all_df[sig_col].isin(SIGNAL_MAP) & (all_df["outcome"] != "FLAT")].copy()
        ov["correct"] = ov.apply(lambda r: r["outcome"] == SIGNAL_MAP.get(r[sig_col],""), axis=1)
        d["Overall"] = ov["correct"].sum() / len(ov) if len(ov) > 0 else float("nan")
        stats[ver] = d

    row_defs = [
        ("Buy low 4yr",     "Buy low"),
        ("Slight buy 4yr",  "Slight buy"),
        ("Slight sell 4yr", "Slight sell"),
        ("Sell high 4yr",   "Sell high"),
        ("Overall",         "Overall"),
        ("vs. do nothing",  None),
    ]

    div = "-" * (24 + 3 * (col_w + 3))
    print("\n" + "=" * 88)
    print("COMPOSITE ABLATION -- 4-YEAR WEIGHTED ACCURACY (2022-2025)")
    print("=" * 88)
    print("Version D: sell=full 8-comp (career baselines), buy=ERA-FIP dominant (0.60/0.25/0.15)")
    print(div)
    print(f"{'Metric':<24} | {'Version A':^{col_w}} | {'Version D':^{col_w}} | {'Version E':^{col_w}}")
    print(f"{'':24} | {'ERA-FIP only':^{col_w}} | {'Split scorer':^{col_w}} | {'Split+Calibrated':^{col_w}}")
    print(div)

    for label, tier_display in row_defs:
        cells = []
        for ver in ("A", "D", "E"):
            if tier_display is None:
                acc = stats[ver]["Overall"]
                val = f"{(acc - RTM_BASELINE)*100:+.1f}pp" if not math.isnan(acc) else "-"
            else:
                acc = stats[ver].get(tier_display, float("nan"))
                val = f"{acc*100:.1f}%" if not math.isnan(acc) else "-"
            cells.append(f"{val:^{col_w}}")
        print(f"{label:<24} | {' | '.join(cells)}")

    print(div)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("\n" + "=" * 70)
    print("COMPOSITE PITCHER BACKTEST v2 — FULL 8-COMPONENT (2022-2025)")
    print("=" * 70)

    frames = []
    for year in P_YEARS:
        print(f"\n{'='*60}\nYear {year}\n{'='*60}")
        merged = run_year(year)
        if merged is None:
            print(f"  SKIP {year}"); continue
        frames.append(merged)
        imp = int((merged["outcome"] == "IMPROVED").sum())
        dec = int((merged["outcome"] == "DECLINED").sum())
        flt = int((merged["outcome"] == "FLAT").sum())
        print(f"  Eval set: {len(merged)} pitchers | IMPROVED={imp} DECLINED={dec} FLAT={flt}")
        for sig_col, lbl in [("signal_a","A"),("signal_d","D"),("signal_e","E")]:
            counts = merged[sig_col].value_counts()
            print(f"  Version {lbl}: BUY_LOW={counts.get('BUY_LOW',0)}  "
                  f"SELL_HIGH={counts.get('SELL_HIGH',0)}  "
                  f"NEUTRAL={counts.get('NEUTRAL',0)}")

    if not frames:
        print("\nERROR: no data loaded"); return

    all_df = pd.concat(frames, ignore_index=True)
    print(f"\nTotal: {len(all_df)} pitcher-seasons")

    print("\n" + "=" * 70 + "\nRESULTS\n" + "=" * 70)
    _print_version_table(all_df, "signal_a",
                         "VERSION A — ERA-FIP Signal Only")
    _print_version_table(all_df, "signal_b",
                         "VERSION B — Full Composite (flat baselines)")
    _print_version_table(all_df, "signal_c",
                         "VERSION C — Full Composite (career baselines)")
    _print_version_table(all_df, "signal_d",
                         "VERSION D — Split Scorer (sell=full composite, buy=ERA-FIP dominant)")
    _print_version_table(all_df, "signal_e",
                         "VERSION E — Split + Production-Aligned (conf-scaled ls, ERA 4.00 SB, qual-first)")

    print("\n" + "=" * 70 + "\nSOFT-CONTACT COHORT\n" + "=" * 70)
    print_softcontact_table(all_df)

    print("\n" + "=" * 70 + "\nSAVING CSVs\n" + "=" * 70)
    save_csvs(all_df)

    print_comparison_table(all_df)


if __name__ == "__main__":
    main()
