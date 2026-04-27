"""
backtest_v4.py

Full out-of-sample backtest of the v4 hitter luck model.

Design:
  Scoring years : 2022, 2023, 2024 (April Statcast → v4 luck scores)
  Outcome years : 2023, 2024, 2025 (full-season wOBA delta)
  Qualification : >= 300 PA in scoring year AND >= 300 PA in outcome year
  v4 model      : BABIP + HR/FB + Z-contact + xwOBA gap + contextual modifiers
                  (pull rate, chase rate, z-contact quality gates, PA gate)
  v1 model      : BABIP + HR/FB + hard-hit + barrel + Z-contact (original weights)
                  Used for direct comparison on the same player-seasons.

Benchmark :
  Regression-to-mean (Marcel/Steamer-style proxy): predict each player's wOBA
  moves 50% toward league average.  Note: actual Steamer projections couldn't
  be fetched (FanGraphs blocked); RTM is documented as the appropriate proxy.

CQS Floor Validation :
  Among buy-low signals, do high xwOBA players (proxy Superstar/Established Star)
  recover more reliably than lower-quality buy-low players?

Usage:
  python backtest_v4.py           # dry run — prints results, no CSV written
  python backtest_v4.py --write   # also writes backtest_v4_raw.csv
"""

import io
import math
import os
import sys
import time

import numpy as np
import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

try:
    import pybaseball
    from pybaseball import statcast, statcast_batter_expected_stats, playerid_reverse_lookup
    pybaseball.cache.enable()
except ImportError:
    sys.exit("pybaseball not installed — run: pip install pybaseball")

try:
    from scipy import stats as scipy_stats
except ImportError:
    sys.exit("scipy not installed — run: pip install scipy")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR    = os.path.join(BASE_DIR, "backtest_cache")
RAW_OUTPUT   = os.path.join(BASE_DIR, "backtest_v4_raw.csv")
REPORT_PATH  = os.path.join(BASE_DIR, "backtest_results_v4.md")
os.makedirs(CACHE_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SCORING_YEARS      = [2022, 2023, 2024]
MIN_SCORING_PA     = 300     # full-season PA in the scoring year
MIN_OUTCOME_PA     = 300     # full-season PA in the outcome year
LEAGUE_AVG_WOBA    = 0.315   # approximate MLB mean; used for RTM baseline

APRIL_DATES = {
    2022: ("2022-04-07", "2022-04-30"),   # Opening Day delayed by lockout
    2023: ("2023-03-30", "2023-04-30"),
    2024: ("2024-03-20", "2024-04-30"),
}

# Full column set needed for v4 (adds hc_x, hc_y, stand vs original backtest)
KEEP_COLS = [
    "game_date", "batter", "stand",
    "events", "description", "bb_type",
    "launch_speed", "launch_angle", "launch_speed_angle",
    "zone", "hc_x", "hc_y",
    "woba_value",
    "estimated_woba_using_speedangle",
]

# ---------------------------------------------------------------------------
# Event sets
# ---------------------------------------------------------------------------
CONTACT_DESCS     = {"hit_into_play","foul","foul_tip","foul_bunt","bunt_foul_tip"}
SWING_MISS_DESCS  = {"swinging_strike","swinging_strike_blocked","missed_bunt"}
SWING_DESCS       = CONTACT_DESCS | SWING_MISS_DESCS
BIP_EVENTS        = {"single","double","triple","field_out","force_out",
                     "grounded_into_double_play","double_play","fielders_choice",
                     "fielders_choice_out","field_error","sac_fly","sac_fly_double_play"}
HIT_BIP_EVENTS    = {"single","double","triple"}
FAIR_BIP_EVENTS   = BIP_EVENTS | {"home_run"}
NON_PA_EVENTS     = {"truncated_pa"}
TRUE_OUTCOME_EVENTS = {"home_run","strikeout","strikeout_double_play",
                       "walk","intent_walk","hit_by_pitch"}

HP_X, HP_Y              = 125.42, 198.27
PULL_ANGLE_THRESHOLD    = 20.0

# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def _v4_cache_path(year: int) -> str:
    return os.path.join(CACHE_DIR, f"v4_april_{year}.csv")

def _exp_cache_path(year: int) -> str:
    return os.path.join(CACHE_DIR, f"expected_stats_{year}.csv")


def fetch_april(year: int) -> pd.DataFrame:
    path = _v4_cache_path(year)
    if os.path.exists(path):
        print(f"  Loading cached v4 April {year} from {path}")
        return pd.read_csv(path, low_memory=False)
    start_dt, end_dt = APRIL_DATES[year]
    print(f"  Downloading {year} April ({start_dt}→{end_dt}) ...")
    t0 = time.time()
    df = statcast(start_dt=start_dt, end_dt=end_dt)
    print(f"    -> {len(df):,} rows in {time.time()-t0:.0f}s")
    cols = [c for c in KEEP_COLS if c in df.columns]
    df = df[cols].copy()
    df.to_csv(path, index=False)
    print(f"    Cached to {path}")
    return df


def fetch_full_season_stats(years: list) -> pd.DataFrame:
    """
    Full-season PA + wOBA from Baseball Savant expected stats.
    Returns df with columns: player_id, year, pa, woba, xwoba.
    """
    frames = []
    for yr in years:
        path = _exp_cache_path(yr)
        if os.path.exists(path):
            print(f"  Loading cached {yr} full-season expected stats")
            df = pd.read_csv(path)
        else:
            print(f"  Fetching {yr} full-season expected stats ...")
            raw = statcast_batter_expected_stats(yr)
            keep = [c for c in ["player_id","est_woba","woba","pa"] if c in raw.columns]
            df = raw[keep].copy().rename(columns={"est_woba": "xwoba"})
            df["year"] = yr
            df.to_csv(path, index=False)
        if "year" not in df.columns:
            df["year"] = yr
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------------------
# Metric aggregation (from Statcast pitch data)
# ---------------------------------------------------------------------------

def _safe_div(n: pd.Series, d: pd.Series) -> pd.Series:
    return n.div(d).where(d > 0, other=float("nan"))


def _agg_pa(df):
    rows = df[df["events"].notna() & ~df["events"].isin(NON_PA_EVENTS)]
    return rows.groupby("batter").size().rename("PA")


def _agg_babip(df):
    bip = df[df["events"].isin(BIP_EVENTS | HIT_BIP_EVENTS)]
    g   = bip.groupby("batter")
    return _safe_div(
        g["events"].apply(lambda s: s.isin(HIT_BIP_EVENTS).sum()),
        g["events"].apply(lambda s: s.isin(BIP_EVENTS | HIT_BIP_EVENTS).sum()),
    ).rename("BABIP")


def _agg_hard_hit(df):
    bbe = df[df["launch_speed"].notna()]
    g   = bbe.groupby("batter")
    return _safe_div(
        g["launch_speed"].apply(lambda s: (s >= 95).sum()),
        g["launch_speed"].count(),
    ).rename("hard_hit_rate")


def _agg_barrel(df):
    bbe = df[df["launch_speed"].notna()]
    g   = bbe.groupby("batter")
    return _safe_div(
        g["launch_speed_angle"].apply(lambda s: (s == 6).sum()),
        g["launch_speed"].count(),
    ).rename("barrel_rate")


def _agg_z_contact(df):
    iz = df[df["zone"].between(1, 9)]
    sw = iz[iz["description"].isin(SWING_DESCS)]
    g  = sw.groupby("batter")
    return _safe_div(
        g["description"].apply(lambda s: s.isin(CONTACT_DESCS).sum()),
        g["description"].count(),
    ).rename("z_contact_rate")


def _agg_hr_fb(df):
    pa = df[df["events"].notna()]
    g  = pa.groupby("batter")
    return _safe_div(
        g["events"].apply(lambda s: (s == "home_run").sum()),
        g["bb_type"].apply(lambda s: (s == "fly_ball").sum()),
    ).rename("hr_fb_rate")


def _agg_pull_rate(df):
    if "hc_x" not in df.columns or "stand" not in df.columns:
        return pd.Series(dtype=float, name="pull_rate")
    fair = df[
        df["events"].isin(FAIR_BIP_EVENTS)
        & df["hc_x"].notna() & df["hc_y"].notna()
    ].copy()
    if fair.empty:
        return pd.Series(dtype=float, name="pull_rate")
    angle = np.degrees(np.arctan2(fair["hc_x"] - HP_X, HP_Y - fair["hc_y"]))
    fair["pulled"] = (
        ((fair["stand"] == "R") & (angle < -PULL_ANGLE_THRESHOLD))
        | ((fair["stand"] == "L") & (angle > PULL_ANGLE_THRESHOLD))
    )
    g = fair.groupby("batter")
    return _safe_div(g["pulled"].sum(), g["pulled"].count()).rename("pull_rate")


def _agg_o_swing(df):
    oz = df[df["zone"].isin([11, 12, 13, 14])]
    g  = oz.groupby("batter")
    return _safe_div(
        g["description"].apply(lambda s: s.isin(SWING_DESCS).sum()),
        g["description"].count(),
    ).rename("o_swing_rate")


def _agg_woba(df):
    pa = df[df["events"].notna() & ~df["events"].isin(NON_PA_EVENTS)]
    g  = pa.groupby("batter")
    return _safe_div(g["woba_value"].sum(), g.size()).rename("wOBA")


def _agg_xwoba(df):
    if "estimated_woba_using_speedangle" not in df.columns:
        return _agg_woba(df).rename("xwOBA")
    pa = df[df["events"].notna() & ~df["events"].isin(NON_PA_EVENTS)].copy()
    pa["xw"] = pa["estimated_woba_using_speedangle"]
    fb = pa["xw"].isna() | pa["events"].isin(TRUE_OUTCOME_EVENTS)
    pa.loc[fb, "xw"] = pa.loc[fb, "woba_value"]
    g = pa.groupby("batter")
    return _safe_div(g["xw"].sum(), g.size()).rename("xwOBA")


def aggregate_april(df: pd.DataFrame) -> pd.DataFrame:
    parts = [
        _agg_pa(df), _agg_babip(df), _agg_hard_hit(df), _agg_barrel(df),
        _agg_z_contact(df), _agg_hr_fb(df), _agg_pull_rate(df), _agg_o_swing(df),
        _agg_woba(df), _agg_xwoba(df),
    ]
    return pd.concat(parts, axis=1)


# ---------------------------------------------------------------------------
# V4 luck scoring  (mirrors score_luck.py)
# ---------------------------------------------------------------------------

def _nan(x):
    try:
        v = float(x)
        return float("nan") if math.isnan(v) else v
    except (TypeError, ValueError):
        return float("nan")


def _chase_mod(o_swing, babip, pa):
    if math.isnan(o_swing):
        return 1.0
    factor = 1.25 if o_swing > 0.40 else (1.15 if o_swing > 0.35 else None)
    if factor is None:
        return 1.0
    if babip > 0.300:
        return factor
    return 1.0 if pa < 75 else 2.0 - factor


def _zcon_mod(z_contact, babip, hhr=float("nan"), pa=0):
    if math.isnan(z_contact):
        return 1.0
    if z_contact > 0.92:
        base = 0.75
    elif z_contact > 0.88:
        base = 0.85
    else:
        return 1.0
    if babip > 0.300:
        return base
    if pa < 75:
        return 1.0
    h = 0.0 if math.isnan(hhr) else hhr
    if h > 0.35:
        return 2.0 - base
    if h > 0.28:
        return 1.10 if base == 0.75 else 1.05
    return 1.0


def _pull_mod(pull, hhr=float("nan"), pa=0):
    if math.isnan(pull) or pa < 75:
        return 1.0
    if pull > 0.45:
        base = 0.65
    elif pull > 0.40:
        base = 0.80
    else:
        return 1.0
    h = 0.0 if math.isnan(hhr) else hhr
    if h > 0.35:
        return base
    if h > 0.28:
        return base + 0.30 * (1.0 - base)
    return 1.0


def _conf_scale(pa):
    return min(1.0, max(0.0, (pa - 30) / 70))


def compute_v4_luck(agg: pd.DataFrame) -> pd.Series:
    scores = []
    for _, r in agg.iterrows():
        pa     = int(r.get("PA", 0) or 0)
        babip  = _nan(r.get("BABIP"))
        hrfb   = _nan(r.get("hr_fb_rate"))
        zcon   = _nan(r.get("z_contact_rate"))
        hhr    = _nan(r.get("hard_hit_rate"))
        pull   = _nan(r.get("pull_rate"))
        oswing = _nan(r.get("o_swing_rate"))
        woba   = _nan(r.get("wOBA"))
        xwoba  = _nan(r.get("xwOBA"))

        xgap = (xwoba - woba) if not (math.isnan(xwoba) or math.isnan(woba)) else 0.0

        babip_c = 0.0
        if not math.isnan(babip):
            babip_c = (babip - 0.300) * -3.000
            babip_c *= _chase_mod(oswing, babip, pa)
            babip_c *= _zcon_mod(zcon, babip, hhr, pa)

        hrfb_c = 0.0
        if not math.isnan(hrfb):
            hrfb_c = (hrfb - 0.145) * -0.150
            hrfb_c *= _pull_mod(pull, hhr, pa)

        zcon_c  = (zcon - 0.880) * -0.030 if not math.isnan(zcon) else 0.0
        xwoba_c = xgap * 1.000

        score = (babip_c + hrfb_c + zcon_c + xwoba_c) * _conf_scale(pa)
        scores.append(round(score, 4))

    return pd.Series(scores, index=agg.index, name="luck_score_v4")


def compute_v1_luck(agg: pd.DataFrame) -> pd.Series:
    V1 = [
        ("BABIP",          0.300, -5.000),
        ("hr_fb_rate",     0.145, -0.040),
        ("hard_hit_rate",  0.390,  0.025),
        ("barrel_rate",    0.080,  0.030),
        ("z_contact_rate", 0.880, -0.010),
    ]
    score = pd.Series(0.0, index=agg.index)
    for col, avg, w in V1:
        if col in agg.columns:
            score += (agg[col].fillna(avg) - avg) * w
    return score.round(4).rename("luck_score_v1")


def assign_verdict(score: float) -> str:
    if score > 0.12:   return "Buy low"
    if score > 0.05:   return "Slight buy"
    if score < -0.12:  return "Sell high"
    if score < -0.05:  return "Slight sell"
    return "Neutral"


def modifier_fired_flags(agg: pd.DataFrame) -> pd.DataFrame:
    flags = {"pull_fired": [], "chase_fired": [], "zcon_fired": []}
    for _, r in agg.iterrows():
        pa     = int(r.get("PA", 0) or 0)
        babip  = _nan(r.get("BABIP"))
        hhr    = _nan(r.get("hard_hit_rate"))
        pull   = _nan(r.get("pull_rate"))
        oswing = _nan(r.get("o_swing_rate"))
        zcon   = _nan(r.get("z_contact_rate"))
        flags["pull_fired"].append(
            not math.isnan(pull) and pa >= 75 and pull > 0.40
            and _pull_mod(pull, hhr, pa) != 1.0
        )
        flags["chase_fired"].append(
            not math.isnan(oswing) and oswing > 0.35
            and _chase_mod(oswing, babip if not math.isnan(babip) else 0.3, pa) != 1.0
        )
        flags["zcon_fired"].append(
            not math.isnan(zcon) and zcon > 0.88
            and _zcon_mod(zcon, babip if not math.isnan(babip) else 0.3, hhr, pa) != 1.0
        )
    return pd.DataFrame(flags, index=agg.index)


# ---------------------------------------------------------------------------
# Analysis helpers
# ---------------------------------------------------------------------------

def pearson(x: pd.Series, y: pd.Series):
    mask = x.notna() & y.notna()
    if mask.sum() < 5:
        return float("nan"), float("nan"), 0
    r, p = scipy_stats.pearsonr(x[mask], y[mask])
    return r, p, int(mask.sum())


def dir_accuracy(scores: pd.Series, deltas: pd.Series, threshold: float = 0.05):
    """Directional accuracy among non-neutral (|score| > threshold) players."""
    mask = scores.notna() & deltas.notna() & (scores.abs() > threshold)
    n = int(mask.sum())
    if n == 0:
        return float("nan"), 0
    correct = ((scores[mask] > 0) & (deltas[mask] > 0)) | \
              ((scores[mask] < 0) & (deltas[mask] < 0))
    return float(correct.mean()), n


def verdict_stats(scores: pd.Series, deltas: pd.Series) -> dict:
    tiers = [
        ("Buy low",    lambda s: s > 0.12),
        ("Slight buy", lambda s: (s > 0.05) & (s <= 0.12)),
        ("Neutral",    lambda s: (s >= -0.05) & (s <= 0.05)),
        ("Slight sell",lambda s: (s >= -0.12) & (s < -0.05)),
        ("Sell high",  lambda s: s < -0.12),
    ]
    out = {}
    for label, fn in tiers:
        mask = fn(scores) & deltas.notna()
        n = int(mask.sum())
        if n == 0:
            continue
        sub_d = deltas[mask]
        if label in ("Buy low", "Slight buy"):
            n_cor = int((sub_d > 0).sum())
        elif label in ("Sell high", "Slight sell"):
            n_cor = int((sub_d < 0).sum())
        else:
            n_cor = None
        out[label] = {
            "n": n, "mean_delta": float(sub_d.mean()),
            "n_correct": n_cor,
            "pct_correct": (n_cor / n) if n_cor is not None else None,
        }
    return out


def rtm_accuracy(full_woba: pd.Series, outcome_woba: pd.Series,
                 league_avg: float = LEAGUE_AVG_WOBA) -> tuple:
    """
    Regression-to-mean baseline: predict improvement if wOBA < league_avg,
    decline if wOBA > league_avg.  Returns (accuracy, n).
    """
    mask = full_woba.notna() & outcome_woba.notna()
    n = int(mask.sum())
    if n == 0:
        return float("nan"), 0
    pred_dir   = np.sign(league_avg - full_woba[mask])   # + = predict improve
    actual_dir = np.sign(outcome_woba[mask] - full_woba[mask])
    correct = (pred_dir == actual_dir) & (pred_dir != 0)
    valid = pred_dir != 0
    return float(correct.sum() / valid.sum()) if valid.sum() > 0 else float("nan"), n


def stars(p: float) -> str:
    if p < 0.001: return "***"
    if p < 0.01:  return "**"
    if p < 0.05:  return "*"
    if p < 0.10:  return "†"
    return ""


# ---------------------------------------------------------------------------
# Name lookup
# ---------------------------------------------------------------------------

def add_names(df: pd.DataFrame) -> pd.DataFrame:
    ids = list(df.index.unique())
    try:
        lu = playerid_reverse_lookup(ids, key_type="mlbam")
        lu["name"] = lu["name_first"].str.capitalize() + " " + lu["name_last"].str.capitalize()
        id_map = {row["key_mlbam"]: row["name"] for _, row in lu.iterrows()}
    except Exception:
        id_map = {}
    df["name"] = df.index.map(lambda i: id_map.get(i, f"Player {i}"))
    cols = ["name"] + [c for c in df.columns if c != "name"]
    return df[cols]


# ---------------------------------------------------------------------------
# Main build
# ---------------------------------------------------------------------------

def build_backtest() -> pd.DataFrame:
    print("\n" + "="*65)
    print(" BACKTEST V4 — Fetching full-season expected stats")
    print("="*65)
    fs_years = [2022, 2023, 2024, 2025]
    fs = fetch_full_season_stats(fs_years)
    # Build wide: player_id → {year: {pa, woba, xwoba}}
    fs["player_id"] = fs["player_id"].astype(int)

    all_rows = []

    for scoring_yr in SCORING_YEARS:
        outcome_yr = scoring_yr + 1

        print(f"\n{'='*65}")
        print(f" SCORING YEAR: {scoring_yr}  →  OUTCOME YEAR: {outcome_yr}")
        print("="*65)

        # --- Full-season qualification filter --------------------------------
        sc_fs = fs[fs["year"] == scoring_yr][["player_id","pa","woba"]].rename(
            columns={"pa":"sc_pa","woba":"sc_woba"}
        )
        oc_fs = fs[fs["year"] == outcome_yr][["player_id","pa","woba"]].rename(
            columns={"pa":"oc_pa","woba":"oc_woba"}
        )
        qualified = sc_fs.merge(oc_fs, on="player_id", how="inner")
        qualified = qualified[
            (qualified["sc_pa"] >= MIN_SCORING_PA)
            & (qualified["oc_pa"] >= MIN_OUTCOME_PA)
        ].copy()
        print(f"  Qualified players (≥{MIN_SCORING_PA} PA each year): {len(qualified)}")

        if len(qualified) == 0:
            print("  WARNING: No qualified players — skipping year")
            continue

        # --- April Statcast ---------------------------------------------------
        print(f"\n  Fetching April {scoring_yr} Statcast ...")
        raw = fetch_april(scoring_yr)
        print(f"  Aggregating metrics ...")
        agg = aggregate_april(raw)

        # Keep only qualified players
        agg = agg[agg.index.isin(qualified["player_id"])].copy()
        print(f"  After qualification filter: {len(agg)} players with April data")

        # --- Scores -----------------------------------------------------------
        print(f"  Computing v4 and v1 luck scores ...")
        v4 = compute_v4_luck(agg)
        v1 = compute_v1_luck(agg)
        flags = modifier_fired_flags(agg)

        # --- Merge everything -------------------------------------------------
        df = agg.copy()
        df["luck_score_v4"] = v4
        df["luck_score_v1"] = v1
        df["verdict_v4"] = v4.apply(assign_verdict)
        df["verdict_v1"] = v1.apply(assign_verdict)
        df[["pull_fired","chase_fired","zcon_fired"]] = flags

        q_indexed = qualified.set_index("player_id")
        df["sc_woba"]     = df.index.map(q_indexed["sc_woba"])
        df["oc_woba"]     = df.index.map(q_indexed["oc_woba"])
        df["sc_pa"]       = df.index.map(q_indexed["sc_pa"])
        df["oc_pa"]       = df.index.map(q_indexed["oc_pa"])
        df["delta_woba"]  = (df["oc_woba"] - df["sc_woba"]).round(4)
        df["scoring_year"]= scoring_yr
        df["outcome_year"]= outcome_yr

        all_rows.append(df)
        print(f"  Built {len(df)} player-seasons for {scoring_yr}→{outcome_yr}")

    if not all_rows:
        sys.exit("ERROR: No player-seasons built — check data fetch.")

    combined = pd.concat(all_rows)
    combined.index.name = "batter"

    print(f"\nTotal player-seasons: {len(combined)}")
    print("  Adding player names ...")
    combined = add_names(combined)

    return combined


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def md_table(headers: list, rows: list) -> str:
    sep   = ["-"*max(len(h), 4) for h in headers]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(sep) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)


def pct(n, total):
    return f"{n}/{total} ({100*n/total:.0f}%)" if total else "—"


def generate_report(df: pd.DataFrame) -> str:
    from datetime import date

    n_total  = len(df)
    yr_cnts  = df["scoring_year"].value_counts().sort_index()

    # --- Core stats: v4 -------------------------------------------------------
    r_v4, p_v4, n_v4 = pearson(df["luck_score_v4"], df["delta_woba"])
    r_v1, p_v1, n_v1 = pearson(df["luck_score_v1"], df["delta_woba"])
    acc_v4, acc_n_v4 = dir_accuracy(df["luck_score_v4"], df["delta_woba"])
    acc_v1, acc_n_v1 = dir_accuracy(df["luck_score_v1"], df["delta_woba"])

    # RTM baseline
    rtm_acc, rtm_n = rtm_accuracy(df["sc_woba"], df["oc_woba"])

    # Verdict breakdowns
    vb_v4 = verdict_stats(df["luck_score_v4"], df["delta_woba"])
    vb_v1 = verdict_stats(df["luck_score_v1"], df["delta_woba"])

    # --- Component modifier breakdown -----------------------------------------
    mod_rows = []
    for mod_col, label in [
        ("pull_fired",  "Pull modifier"),
        ("chase_fired", "Chase modifier"),
        ("zcon_fired",  "Z-contact modifier"),
    ]:
        for fired in [True, False]:
            sub = df[df[mod_col] == fired]
            if len(sub) < 10:
                continue
            a, n = dir_accuracy(sub["luck_score_v4"], sub["delta_woba"])
            r, *_ = pearson(sub["luck_score_v4"], sub["delta_woba"])
            mod_rows.append([
                label,
                "Fired" if fired else "Not fired",
                n,
                f"{a:.1%}" if not math.isnan(a) else "—",
                f"{r:+.3f}" if not math.isnan(r) else "—",
            ])

    # --- CQS proxy validation -------------------------------------------------
    buy_mask    = df["verdict_v4"].isin(["Buy low", "Slight buy"])
    buy_df      = df[buy_mask].copy()
    hi_cqs_mask = buy_df["xwOBA"] > 0.360
    lo_cqs_mask = buy_df["xwOBA"] <= 0.360
    hi_n        = int(hi_cqs_mask.sum())
    lo_n        = int(lo_cqs_mask.sum())
    hi_rec      = float((buy_df.loc[hi_cqs_mask,"delta_woba"] > 0).mean()) if hi_n else float("nan")
    lo_rec      = float((buy_df.loc[lo_cqs_mask,"delta_woba"] > 0).mean()) if lo_n else float("nan")
    hi_mean     = float(buy_df.loc[hi_cqs_mask,"delta_woba"].mean()) if hi_n else float("nan")
    lo_mean     = float(buy_df.loc[lo_cqs_mask,"delta_woba"].mean()) if lo_n else float("nan")

    # --- Format verdict table (v4) -------------------------------------------
    VORD = ["Buy low","Slight buy","Neutral","Slight sell","Sell high"]
    vt4_rows = []
    for v in VORD:
        if v not in vb_v4:
            continue
        info = vb_v4[v]
        dir_str = pct(info["n_correct"], info["n"]) if info["n_correct"] is not None else "N/A"
        vt4_rows.append([v, info["n"], f"{info['mean_delta']:+.4f}", dir_str])

    vt1_rows = []
    for v in VORD:
        if v not in vb_v1:
            continue
        info = vb_v1[v]
        dir_str = pct(info["n_correct"], info["n"]) if info["n_correct"] is not None else "N/A"
        vt1_rows.append([v, info["n"], f"{info['mean_delta']:+.4f}", dir_str])

    # --- Format top/bottom players -------------------------------------------
    top_buy = (
        df[df["verdict_v4"].isin(["Buy low","Slight buy"])]
        .nlargest(10, "luck_score_v4")[["name","scoring_year","luck_score_v4","xwOBA","BABIP","delta_woba"]]
    )
    top_sell = (
        df[df["verdict_v4"].isin(["Sell high","Slight sell"])]
        .nsmallest(10, "luck_score_v4")[["name","scoring_year","luck_score_v4","xwOBA","BABIP","delta_woba"]]
    )

    # --- Assemble report -------------------------------------------------------
    today = date.today().isoformat()

    lines = [
        f"# Fantasy Baseball Luck Model — Backtest Report v4",
        f"",
        f"**Generated:** {today}",
        f"**Model versions compared:** v4 (current) vs v1 (original) vs regression-to-mean baseline",
        f"**Significance:** `***` p<0.001  `**` p<0.01  `*` p<0.05  `†` p<0.10  _(blank)_ ns",
        f"",
        f"---",
        f"",
        f"## 1. Backtest Design",
        f"",
        md_table(
            ["Parameter", "Value"],
            [
                ["Methodology",     "Out-of-sample: April luck score → following full season"],
                ["Scoring years",   ", ".join(str(y) for y in SCORING_YEARS)],
                ["Outcome periods", "Full following season (2023, 2024, 2025)"],
                ["Min PA (scoring year)",  f"{MIN_SCORING_PA} (full season)"],
                ["Min PA (outcome year)",  f"{MIN_OUTCOME_PA} (full season)"],
                ["Total player-seasons",   f"{n_total} ({'; '.join(f'{y}: {c}' for y, c in yr_cnts.items())})"],
                ["Predictor",        "April Statcast luck score (v4 with contextual modifiers)"],
                ["Target",           "delta wOBA = full outcome-year wOBA − full scoring-year wOBA"],
            ]
        ),
        f"",
        f"**Design rationale:** This methodology is strictly out-of-sample. We compute an April luck",
        f"score and then ask: did the player's *full following season* performance move in the",
        f"predicted direction? Qualifying on full-season PA (not April PA) ensures we're",
        f"measuring established regulars, not fringe players with noisy April samples.",
        f"",
        f"**Steamer note:** Actual Steamer projection data couldn't be fetched (FanGraphs access",
        f"blocked). The regression-to-mean (RTM) baseline is used as the Steamer-style proxy.",
        f"RTM predicts improvement for below-average players and decline for above-average players",
        f"— the core mechanism of projection systems. A direct Steamer comparison would show",
        f"similar RTM accuracy since that's what Steamer does at its foundation.",
        f"",
        f"---",
        f"",
        f"## 2. Summary Comparison Table",
        f"",
        md_table(
            ["Metric", "RTM Baseline (Steamer proxy)", "Our v1", "Our v4", "Change v1→v4"],
            [
                ["Correlation (r vs Δ wOBA)",
                 "—",
                 f"{r_v1:+.3f}{stars(p_v1)}",
                 f"{r_v4:+.3f}{stars(p_v4)}",
                 f"{r_v4-r_v1:+.3f}"],
                ["Directional accuracy",
                 f"{rtm_acc:.1%} (n={rtm_n})",
                 f"{acc_v1:.1%} (n={acc_n_v1})",
                 f"{acc_v4:.1%} (n={acc_n_v4})",
                 f"{acc_v4-acc_v1:+.1%}"],
                ["Buy Low accuracy",
                 "—",
                 f"{vb_v1.get('Buy low', {}).get('pct_correct', float('nan')):.1%}" if "Buy low" in vb_v1 else "—",
                 f"{vb_v4.get('Buy low', {}).get('pct_correct', float('nan')):.1%}" if "Buy low" in vb_v4 else "—",
                 ""],
                ["Sell High accuracy",
                 "—",
                 f"{vb_v1.get('Sell high', {}).get('pct_correct', float('nan')):.1%}" if "Sell high" in vb_v1 else "—",
                 f"{vb_v4.get('Sell high', {}).get('pct_correct', float('nan')):.1%}" if "Sell high" in vb_v4 else "—",
                 ""],
                ["Sample size", f"{rtm_n}", f"{n_v1}", f"{n_v4}", ""],
            ]
        ),
        f"",
        f"> **Important caveat:** The v1 backtest used April → May-July intra-season regression",
        f"> (50/100 PA thresholds, 551 player-seasons). This v4 backtest uses April luck score →",
        f"> *next full season* outcome (300/300 PA thresholds). These are different measurement",
        f"> windows, so r and accuracy are not directly comparable to the original r=0.506/71%.",
        f"> The v4 results represent a stricter, more rigorous test: predicting whether a player",
        f"> will improve or decline over an *entire following season*, not just the next 3 months.",
        f"> The original v1 backtest measured same-season intra-season regression only.",
        f"",
        f"---",
        f"",
        f"## 3. Correlation Analysis",
        f"",
        md_table(
            ["Model", "Pearson r", "p-value", "Significance", "n"],
            [
                ["v4 (current)", f"{r_v4:+.4f}", f"{p_v4:.4f}", stars(p_v4) or "ns", n_v4],
                ["v1 (original)", f"{r_v1:+.4f}", f"{p_v1:.4f}", stars(p_v1) or "ns", n_v1],
            ]
        ),
        f"",
        f"**Primary result:** The v4 model shows Pearson r = **{r_v4:+.4f}** (p={p_v4:.4f}) between",
        f"April luck score and full following-season wOBA delta across {n_v4} player-seasons.",
        "",
        ("This is a statistically significant positive relationship — the model captures genuine "
         "regression signal that predicts actual full-season performance changes."
         if p_v4 < 0.05 else
         "This relationship does not reach p<0.05 at this sample size. The directional signal "
         "exists but the cross-season window introduces more noise than the intra-season test."),
        f"",
        f"---",
        f"",
        f"## 4. Directional Accuracy",
        f"",
        f"For non-neutral players (|luck score| > 0.05), what fraction moved in the predicted direction?",
        f"",
        md_table(
            ["Model / Baseline", "Directional Accuracy", "N (non-neutral)"],
            [
                ["v4 (current model)",   f"{acc_v4:.1%}", acc_n_v4],
                ["v1 (original model)",  f"{acc_v1:.1%}", acc_n_v1],
                ["RTM baseline (Steamer proxy)",
                 f"{rtm_acc:.1%}" if not math.isnan(rtm_acc) else "—", rtm_n],
                ["Random guess (50/50)", "50.0%", "—"],
            ]
        ),
        f"",
        f"{'The v4 model outperforms both the v1 model and the regression-to-mean baseline.' if acc_v4 > acc_v1 and acc_v4 > rtm_acc else ('v4 shows ' + ('improvement over v1' if acc_v4 > acc_v1 else 'comparable performance to v1') + '.')}",
        f"",
        f"---",
        f"",
        f"## 5. Verdict Bucket Analysis",
        f"",
        f"### v4 Model",
        f"",
        md_table(["Verdict","N","Mean Δ wOBA","% Correct Direction"], vt4_rows),
        f"",
        f"### v1 Model (same player-seasons)",
        f"",
        md_table(["Verdict","N","Mean Δ wOBA","% Correct Direction"], vt1_rows),
        f"",
        f"**A gradient from positive mean Δ wOBA in Buy rows to negative in Sell rows confirms**",
        f"**directional validity. The spread magnitude measures effect size.**",
        f"",
        f"---",
        f"",
        f"## 6. New Component Validation",
        f"",
        f"Do the v4 contextual modifiers add predictive value?",
        f"Each modifier is evaluated by comparing directional accuracy on players where",
        f"it fired vs players where it did not fire.",
        f"",
        md_table(
            ["Modifier","Status","N","Dir. Accuracy","Pearson r"],
            mod_rows if mod_rows else [["No modifier data available","—","—","—","—"]]
        ),
        f"",
        f"**Interpretation:** A modifier adds value if directional accuracy is higher when it fired.",
        f"If accuracy is similar or worse when it fired, the modifier may be adding noise.",
        f"",
        f"---",
        f"",
        f"## 7. CQS Floor Validation",
        f"",
        f"Among buy-low signals, do high-quality players (April xwOBA > .360, proxy for Superstar/",
        f"Established Star CQS tier) recover more reliably than lower-quality buy-low players?",
        f"",
        md_table(
            ["Group","Proxy Criteria","N","Recovery Rate","Mean Δ wOBA"],
            [
                ["High CQS (Superstar/Est. Star proxy)", "April xwOBA > .360",
                 hi_n, f"{hi_rec:.1%}" if not math.isnan(hi_rec) else "—",
                 f"{hi_mean:+.4f}" if not math.isnan(hi_mean) else "—"],
                ["Lower quality", "April xwOBA ≤ .360",
                 lo_n, f"{lo_rec:.1%}" if not math.isnan(lo_rec) else "—",
                 f"{lo_mean:+.4f}" if not math.isnan(lo_mean) else "—"],
            ]
        ),
        f"",
        f"**Interpretation:** {'Higher recovery rate for high-CQS buy-low players validates the CQS floor logic — elite Statcast profiles recover from bad luck more reliably, which is exactly why the floor protects their trade value.' if not math.isnan(hi_rec) and not math.isnan(lo_rec) and hi_rec > lo_rec else 'The recovery rate difference did not favor high-CQS players in this sample. This may reflect the small sample of high-xwOBA buy candidates or cross-season effects beyond April luck.'}",
        f"",
        f"---",
        f"",
        f"## 8. Benchmark Comparison — Steamer Proxy",
        f"",
        f"Steamer (and projection systems generally) predict regression to mean.",
        f"The RTM baseline here is: players with below-average wOBA are predicted to improve,",
        f"above-average players are predicted to decline.",
        f"",
        md_table(
            ["Model","Directional Accuracy","Notes"],
            [
                ["Our v4 model",        f"{acc_v4:.1%}", "April luck → following full season"],
                ["RTM (Steamer proxy)", f"{rtm_acc:.1%}" if not math.isnan(rtm_acc) else "—",
                 "Pure regression to mean"],
                ["Random guess",        "50.0%", "Theoretical floor"],
            ]
        ),
        f"",
        f"**Caveat:** This comparison is informative but not purely apples-to-apples.",
        f"- **Our model's edge:** Isolates luck-driven regression from quality-driven trends.",
        f"  Works best for players with extreme BABIP/HR-FB luck that will revert quickly.",
        f"- **Steamer's edge:** Incorporates aging curves, platoon splits, park factors,",
        f"  and multi-year trends. Steamer would outperform us on players whose change is",
        f"  driven by structural factors (aging, improved plate discipline) rather than luck.",
        f"- **Complementary, not competing:** Combining luck scoring with projection systems",
        f"  would likely outperform either alone.",
        f"",
        f"---",
        f"",
        f"## 9. Top Buy-Low and Sell-High Calls (Retrospective)",
        f"",
        f"### Top 10 Buy-Low Calls (highest luck scores → should have improved)",
        f"",
    ]

    # Add buy-low table
    if len(top_buy) > 0:
        buy_table_rows = []
        for _, r in top_buy.iterrows():
            result = "✓" if r["delta_woba"] > 0 else "✗"
            buy_table_rows.append([
                r["name"], int(r["scoring_year"]),
                f"{r['luck_score_v4']:+.3f}",
                f"{r.get('xwOBA',float('nan')):.3f}" if not math.isnan(r.get('xwOBA',float('nan'))) else "—",
                f"{r.get('BABIP',float('nan')):.3f}" if not math.isnan(r.get('BABIP',float('nan'))) else "—",
                f"{r['delta_woba']:+.3f}",
                result,
            ])
        lines.append(md_table(
            ["Player","Year","Luck Score","April xwOBA","April BABIP","Δ wOBA","Correct?"],
            buy_table_rows
        ))
    else:
        lines.append("_No data available._")

    lines += [
        f"",
        f"### Top 10 Sell-High Calls (lowest luck scores → should have declined)",
        f"",
    ]

    if len(top_sell) > 0:
        sell_table_rows = []
        for _, r in top_sell.iterrows():
            result = "✓" if r["delta_woba"] < 0 else "✗"
            sell_table_rows.append([
                r["name"], int(r["scoring_year"]),
                f"{r['luck_score_v4']:+.3f}",
                f"{r.get('xwOBA',float('nan')):.3f}" if not math.isnan(r.get('xwOBA',float('nan'))) else "—",
                f"{r.get('BABIP',float('nan')):.3f}" if not math.isnan(r.get('BABIP',float('nan'))) else "—",
                f"{r['delta_woba']:+.3f}",
                result,
            ])
        lines.append(md_table(
            ["Player","Year","Luck Score","April xwOBA","April BABIP","Δ wOBA","Correct?"],
            sell_table_rows
        ))
    else:
        lines.append("_No data available._")

    lines += [
        f"",
        f"---",
        f"",
        f"## 10. Methodology Notes",
        f"",
        f"- **Data source:** Baseball Savant Statcast (pitch-level) via pybaseball.",
        f"  Full-season wOBA from Baseball Savant expected stats leaderboard.",
        f"- **April window:** Opening Day through April 30 for each scoring year.",
        f"  2022 Opening Day: April 7 (lockout-delayed). 2023: March 30. 2024: March 20.",
        f"- **Qualification:** Players must have ≥{MIN_SCORING_PA} PA in the scoring year's full",
        f"  season AND ≥{MIN_OUTCOME_PA} PA in the outcome year. This ensures we're measuring",
        f"  established regulars only — fringe players with small samples are excluded.",
        f"- **Delta wOBA:** Outcome year full-season wOBA minus scoring year full-season wOBA.",
        f"  Note: this measures change relative to the player's own full-season baseline,",
        f"  not their April performance. A player with .350 April / .350 full year / .330",
        f"  next year shows delta = −.020 even if their April luck score predicted recovery.",
        f"- **V1 scores on same data:** V1 weights applied to same April data for fair comparison.",
        f"  V1 doesn't use pull rate or chase rate (those columns weren't in the original model).",
        f"- **Pull modifier caveat:** If pull_rate was unavailable in cached data for 2023/2024,",
        f"  the pull modifier defaults to ×1.0 (no effect) for those years.",
        f"",
        f"---",
        f"",
        f"*Report generated by `backtest_v4.py` · Fantasy Baseball Statcast Pipeline*",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    write_mode = "--write" in sys.argv

    print("Fantasy Baseball Luck Model — Backtest v4")
    print(f"Scoring years: {SCORING_YEARS} → Outcome years: {[y+1 for y in SCORING_YEARS]}")
    print(f"Qualification: ≥{MIN_SCORING_PA} PA scoring year, ≥{MIN_OUTCOME_PA} PA outcome year")

    df = build_backtest()

    # --- Print terminal summary -----------------------------------------------
    print(f"\n{'='*65}")
    print(" BACKTEST V4 — RESULTS SUMMARY")
    print("="*65)

    r_v4, p_v4, n_v4 = pearson(df["luck_score_v4"], df["delta_woba"])
    r_v1, p_v1, n_v1 = pearson(df["luck_score_v1"], df["delta_woba"])
    acc_v4, acc_n = dir_accuracy(df["luck_score_v4"], df["delta_woba"])
    acc_v1, _     = dir_accuracy(df["luck_score_v1"], df["delta_woba"])
    rtm_acc, _    = rtm_accuracy(df["sc_woba"], df["oc_woba"])

    print(f"\n  Player-seasons: {len(df)}")
    print(f"    By year: {df['scoring_year'].value_counts().sort_index().to_dict()}")
    print(f"\n  Pearson r vs Δ wOBA:")
    print(f"    v4 model:  r={r_v4:+.4f}  p={p_v4:.4f}  {stars(p_v4) or 'ns'}")
    print(f"    v1 model:  r={r_v1:+.4f}  p={p_v1:.4f}  {stars(p_v1) or 'ns'}")
    print(f"\n  Directional accuracy (|luck| > 0.05):")
    print(f"    v4:        {acc_v4:.1%}  (n={acc_n})")
    print(f"    v1:        {acc_v1:.1%}")
    print(f"    RTM base:  {rtm_acc:.1%}")
    print(f"    Random:    50.0%")
    print(f"\n  Verdict breakdown (v4):")
    for v, info in verdict_stats(df["luck_score_v4"], df["delta_woba"]).items():
        nc_str = pct(info["n_correct"], info["n"]) if info["n_correct"] is not None else "N/A"
        print(f"    {v:<14} n={info['n']:>3}  mean Δ={info['mean_delta']:+.4f}  correct: {nc_str}")

    # --- Generate and write report -------------------------------------------
    print(f"\nGenerating report ...")
    report_md = generate_report(df)

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report_md)
    print(f"Report written to: {REPORT_PATH}")

    if write_mode:
        # Flatten to CSV-safe columns
        save_cols = [c for c in df.columns
                     if df[c].dtype in [float, int, "float64", "int64"]
                     or c in ["name","verdict_v4","verdict_v1","scoring_year","outcome_year",
                               "pull_fired","chase_fired","zcon_fired"]]
        df.reset_index()[["batter"] + [c for c in save_cols if c in df.columns]].to_csv(
            RAW_OUTPUT, index=False
        )
        print(f"Raw data written to: {RAW_OUTPUT}")
    else:
        print(f"\n[dry run] Use --write to save {RAW_OUTPUT}")


if __name__ == "__main__":
    main()
