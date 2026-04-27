"""
Within-Season Backtest v9
=========================
Full production signal stack matching current score_luck.py.

Signal window:  April 2024  (v4_april_2024.csv)
Outcome window: May-July 2024  (statcast_2024_may_july.csv)
PA gates:       >= 80 April PA, >= 100 May-July PA
Flat threshold: +/- 0.015
RTM baseline:   68.2%

Layer stack:
  L1: Core         -- xwoba_gap*0.60 + babip_luck*0.40
  L2: Sweet spot   -- >0.12 buy->x1.05 | <0.06 buy->x0.95
  L3: EV trend     -- current EV < career by >1.0 mph buy->x0.85
  L4: Defense BABIP-- opponent OAA adj (+/-0.008) added to expected BABIP
                      re-centers babip_luck before computing luck score
  L5: Seasonal     -- corrected modifiers (slow_starter buy x1.10, V-shape sell removed)

Six output columns:
  C1: L1 baseline
  C2: L1+2 (+sweet spot)
  C3: L1+2+3 (+EV 1.0mph)
  C4: L1+2+3+4 (+defense BABIP)
  C5: L1+2+3+4+5 (full v9)
  C6: Phase C players only

NOTE: team_oaa_2025.csv used as opponent OAA proxy for 2024 games.
April 2024 opponent teams derived from pybaseball (cached to
backtest_cache/opponent_oaa_april_2024.csv after first run).
"""

import json
import os
import numpy as np
import pandas as pd
from pathlib import Path

try:
    import pybaseball
    PYBASEBALL_AVAILABLE = True
except ImportError:
    PYBASEBALL_AVAILABLE = False

# ------------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------------

BASE_DIR      = Path(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR     = BASE_DIR / "backtest_cache"
SEASONAL_PATH = BASE_DIR / "data" / "seasonal_patterns.json"
CAREER_PATH   = BASE_DIR / "data" / "career_stats.json"
OAA_PATH      = BASE_DIR / "data" / "team_oaa_2025.csv"
OPP_OAA_CACHE = CACHE_DIR / "opponent_oaa_april_2024.csv"

MIN_APRIL_PA   = 80
MIN_OUTCOME_PA = 100
FLAT_THRESHOLD = 0.015
RTM_BASELINE   = 0.682
EV_THRESHOLD   = 1.0
LEAGUE_AVG_BABIP = 0.300

PARK_FACTORS = {
    'COL': 1.12, 'CIN': 1.08, 'TEX': 1.06, 'HOU': 1.05,
    'BAL': 1.04, 'BOS': 1.04, 'PHI': 1.03, 'MIL': 1.02,
    'ATL': 1.02, 'NYY': 1.01, 'TOR': 1.01, 'WSH': 1.00,
    'CHC': 1.00, 'STL': 1.00, 'LAD': 0.99, 'NYM': 0.99,
    'ARI': 0.99, 'MIN': 0.98, 'DET': 0.98, 'CLE': 0.98,
    'CWS': 0.97, 'SEA': 0.97, 'SF':  0.96, 'MIA': 0.96,
    'TB':  0.96, 'PIT': 0.96, 'KC':  0.96, 'LAA': 0.95,
    'SD':  0.95, 'OAK': 0.94,
}

BIP_EVENTS = {
    'single', 'double', 'triple', 'field_out', 'grounded_into_double_play',
    'force_out', 'double_play', 'fielders_choice',
}

SIGNAL_MAP = {
    'BUY_LOW':    'IMPROVED',
    'SLIGHT_BUY': 'IMPROVED',
    'SELL_HIGH':  'DECLINED',
    'SLIGHT_SELL':'DECLINED',
}

# Corrected Phase C multipliers (v9)
PHASE_C = {
    # V-shape (slow_starter AND summer_performer)
    'vshape_buy':       1.20,
    'vshape_sell':      None,   # removed — empirically wrong (4/5 improved)
    # Slow starter only
    'slow_buy':         1.10,   # was 0.80 — flipped to amplify (100% accurate)
    # Summer performer only
    'summer_buy':       1.10,
    # Second half fader (stacks)
    'fader_sell':       1.15,
    'fader_buy':        0.90,
}

# ------------------------------------------------------------------
# DATA LOADING
# ------------------------------------------------------------------

def load_data():
    print("Loading 2024 cache data...")
    april       = pd.read_csv(CACHE_DIR / "v4_april_2024.csv")
    outcome_raw = pd.read_csv(CACHE_DIR / "statcast_2024_may_july.csv")
    team_map    = pd.read_csv(CACHE_DIR / "team_map_2024.csv")
    print(f"  April: {len(april):,} rows  |  May-Jul: {len(outcome_raw):,} rows")
    return april, outcome_raw, team_map


def load_career_stats() -> dict:
    if not CAREER_PATH.exists():
        return {}
    with open(CAREER_PATH) as f:
        raw = json.load(f)
    cs = {int(k): v for k, v in raw.items()}
    ev_count = sum(1 for v in cs.values() if v.get("avg_exit_velocity") is not None)
    print(f"  Career stats: {len(cs):,} players  |  {ev_count:,} with EV")
    return cs


def load_seasonal_patterns() -> dict:
    if not SEASONAL_PATH.exists():
        return {}
    with open(SEASONAL_PATH) as f:
        records = json.load(f)
    patterns = {int(r["player_id"]): r for r in records}
    print(f"  Seasonal patterns: {len(patterns):,} players loaded")
    return patterns


def load_oaa_map() -> dict:
    """Returns team_abbr -> babip_adj."""
    if not OAA_PATH.exists():
        print("  WARNING: team_oaa_2025.csv not found -- defense layer skipped")
        return {}
    df = pd.read_csv(OAA_PATH, usecols=["team_abbr", "babip_adj"])
    return dict(zip(df["team_abbr"], df["babip_adj"].astype(float)))


def load_or_build_opponent_oaa(oaa_map: dict) -> pd.Series:
    """
    Returns Series: batter_id -> mean opponent OAA babip_adj across April 2024 PAs.
    Builds and caches from pybaseball if not already cached.
    """
    if not oaa_map:
        return pd.Series(dtype=float)

    if OPP_OAA_CACHE.exists():
        df = pd.read_csv(OPP_OAA_CACHE)
        print(f"  Opponent OAA loaded from cache ({len(df):,} batters)")
        return df.set_index("batter")["oaa_babip_adj"]

    if not PYBASEBALL_AVAILABLE:
        print("  WARNING: pybaseball not available -- defense layer skipped")
        return pd.Series(dtype=float)

    print("  Fetching April 2024 Statcast for opponent team derivation...")
    pybaseball.cache.enable()
    raw = pybaseball.statcast(
        start_dt="2024-03-28", end_dt="2024-04-30",
        verbose=False
    )
    raw = raw[["batter", "home_team", "away_team", "inning_topbot"]].dropna()

    # Opponent = fielding team = the team NOT batting
    raw["opponent_team"] = np.where(
        raw["inning_topbot"] == "Bot",
        raw["away_team"],   # batter is home -> opponent is away
        raw["home_team"],   # batter is away -> opponent is home
    )
    raw["oaa_adj"] = raw["opponent_team"].map(oaa_map).fillna(0.0)
    result = raw.groupby("batter")["oaa_adj"].mean().reset_index()
    result.columns = ["batter", "oaa_babip_adj"]
    result.to_csv(OPP_OAA_CACHE, index=False)
    print(f"  Cached opponent OAA for {len(result):,} batters -> {OPP_OAA_CACHE.name}")

    nonzero = (result["oaa_babip_adj"] != 0).sum()
    print(f"  {nonzero:,} batters faced at least one non-neutral defense team")
    return result.set_index("batter")["oaa_babip_adj"]

# ------------------------------------------------------------------
# LAYER 1 -- CORE SIGNAL
# ------------------------------------------------------------------

def compute_layer1(april_df: pd.DataFrame, team_map_df: pd.DataFrame) -> pd.DataFrame:
    df = april_df.copy()
    df = df.merge(team_map_df, on="batter", how="left")
    df["park_factor"] = df["team"].map(PARK_FACTORS).fillna(1.0)

    batted = df[df["bb_type"].notna() & (df["bb_type"] != "")].copy()
    batted["is_bip"]     = batted["events"].isin(BIP_EVENTS).astype(int)
    batted["is_hit_bip"] = batted["events"].isin({"single", "double", "triple"}).astype(int)
    bip_agg = batted.groupby("batter").agg(
        bip=("is_bip", "sum"), hits_bip=("is_hit_bip", "sum"),
    ).reset_index()

    bbe = df[df["launch_speed"].notna() & df["launch_angle"].notna()].copy()
    bbe_agg = bbe.groupby("batter").apply(
        lambda s: pd.Series({
            "sweet_spot_count": ((s["launch_speed"] >= 98) & s["launch_angle"].between(8, 32)).sum(),
            "bbe_total":         len(s),
            "avg_exit_velocity": s["launch_speed"].mean(),
        })
    ).reset_index()

    pa_agg = df.groupby("batter").agg(
        april_pa=("woba_value", "count"),
        april_actual_woba=("woba_value", "mean"),
        april_xwoba=("estimated_woba_using_speedangle", "mean"),
        park_factor=("park_factor", "first"),
    ).reset_index()

    signals = pa_agg.merge(bip_agg,  on="batter", how="left")
    signals = signals.merge(bbe_agg, on="batter", how="left")
    signals["babip"] = np.where(
        signals["bip"] > 0, signals["hits_bip"] / signals["bip"], np.nan
    )
    signals["xwoba_gap"]  = signals["april_xwoba"] - signals["april_actual_woba"]
    signals["babip_luck"] = LEAGUE_AVG_BABIP - signals["babip"]

    signals["luck_score_L1"] = (
        signals["xwoba_gap"]  * 0.60 +
        signals["babip_luck"] * 0.40
    ).round(4)

    signals["sweet_spot_rate"] = np.where(
        signals["bbe_total"] > 0,
        signals["sweet_spot_count"] / signals["bbe_total"], np.nan
    )
    signals = signals[signals["april_pa"] >= MIN_APRIL_PA].copy()
    return signals

# ------------------------------------------------------------------
# LAYER 2 -- SWEET SPOT MODIFIER
# ------------------------------------------------------------------

def apply_layer2(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["luck_score_L2"] = out["luck_score_L1"].copy()
    buy  = out["luck_score_L2"] > 0
    high_ss = buy & (out["sweet_spot_rate"] > 0.12)
    low_ss  = buy & (out["sweet_spot_rate"] < 0.06)
    out.loc[high_ss, "luck_score_L2"] = (out.loc[high_ss, "luck_score_L2"] * 1.05).round(4)
    out.loc[low_ss,  "luck_score_L2"] = (out.loc[low_ss,  "luck_score_L2"] * 0.95).round(4)
    print(f"  Layer 2 (sweet spot): {high_ss.sum()} amplified x1.05 | {low_ss.sum()} dampened x0.95")
    return out

# ------------------------------------------------------------------
# LAYER 3 -- EV TREND MODIFIER (1.0 mph)
# ------------------------------------------------------------------

def apply_layer3(df: pd.DataFrame, career_stats: dict) -> pd.DataFrame:
    out = df.copy()
    out["luck_score_L3"] = out["luck_score_L2"].copy()
    out["ev_delta"]      = np.nan
    dampened = 0
    for idx, row in out.iterrows():
        if row["luck_score_L3"] <= 0:
            continue
        career_ev = (career_stats.get(int(row["batter"])) or {}).get("avg_exit_velocity")
        if career_ev is None or pd.isna(row["avg_exit_velocity"]):
            continue
        delta = row["avg_exit_velocity"] - career_ev
        out.at[idx, "ev_delta"] = round(delta, 2)
        if delta < -EV_THRESHOLD:
            out.at[idx, "luck_score_L3"] = round(row["luck_score_L3"] * 0.85, 4)
            dampened += 1
    print(f"  Layer 3 (EV trend):   {dampened} buy signals dampened x0.85 "
          f"(EV > {EV_THRESHOLD} mph below career avg)")
    return out

# ------------------------------------------------------------------
# LAYER 4 -- DEFENSE BABIP ADJUSTMENT
# ------------------------------------------------------------------

def apply_layer4(df: pd.DataFrame, opp_oaa: pd.Series) -> pd.DataFrame:
    """
    Adjusts expected BABIP by mean opponent OAA faced in April.
    Recomputes babip_luck with the adjusted baseline, then reweights
    luck_score_L4 to reflect the updated BABIP component.

    Effect:
      - Batter faced elite defense (oaa_adj < 0): expected BABIP lowered ->
        babip_luck reduced -> buy signal slightly weakened (low BABIP partly explained)
      - Batter faced poor defense (oaa_adj > 0): expected BABIP raised ->
        babip_luck increased -> buy signal slightly strengthened

    Additive delta applied after L3 multiplicative modifiers:
      delta = oaa_babip_adj * 0.40
      luck_score_L4 = luck_score_L3 + delta
    """
    out = df.copy()
    out["oaa_babip_adj"] = out["batter"].map(opp_oaa).fillna(0.0)
    # delta to luck score from adjusting the BABIP component
    delta = (out["oaa_babip_adj"] * 0.40).round(4)
    out["luck_score_L4"] = (out["luck_score_L3"] + delta).round(4)

    affected  = (out["oaa_babip_adj"] != 0.0).sum()
    amplified = (delta > 0).sum()   # poor defense -> raised expected BABIP -> higher buy
    dampened  = (delta < 0).sum()   # elite defense -> lowered expected BABIP -> lower buy/sell
    print(f"  Layer 4 (defense BABIP): {affected} players adjusted  "
          f"({dampened} reduced vs elite D | {amplified} raised vs poor D)")
    print(f"    Mean |delta| = {delta.abs().mean():.5f}  "
          f"Max |delta| = {delta.abs().max():.5f}")
    return out

# ------------------------------------------------------------------
# LAYER 5 -- CORRECTED SEASONAL PATTERNS
# ------------------------------------------------------------------

def apply_layer5(df: pd.DataFrame, patterns: dict) -> pd.DataFrame:
    out = df.copy()
    out["luck_score_L5"]     = out["luck_score_L4"].copy()
    out["seasonal_modifier"] = 1.0
    out["seasonal_label"]    = None

    if not patterns:
        print("  Layer 5 (Phase C):   no patterns loaded -- skipped")
        return out

    modified = vshape = slow_amp = 0
    for idx, row in out.iterrows():
        pid    = int(row["batter"])
        raw    = row["luck_score_L5"]
        if pid not in patterns:
            continue
        p      = patterns[pid]
        slow   = p.get("slow_starter", False)
        fader  = p.get("second_half_fader", False)
        summer = p.get("summer_performer", False)
        is_buy  = raw > 0
        is_sell = raw < 0
        mult  = 1.0
        label = None

        # V-shape: slow_starter AND summer_performer
        if slow and summer:
            if is_buy:
                mult, label = PHASE_C["vshape_buy"], "V-shape (strong buy)"
                vshape += 1
            # sell: no modifier (V-shape sell removed — was empirically wrong)

        # Slow starter only
        elif slow and not summer:
            if is_buy:
                mult, label = PHASE_C["slow_buy"], "Slow starter (amplified)"
                slow_amp += 1

        # Summer performer only
        elif summer and not slow:
            if is_buy:
                mult, label = PHASE_C["summer_buy"], "Summer performer (amplified)"

        # Second half fader (stacks with above)
        if fader:
            if is_sell:
                mult  = max(mult, PHASE_C["fader_sell"])
                label = (label + " + fader" if label else "Second half fader (amplified)")
            elif is_buy:
                mult  = min(mult, PHASE_C["fader_buy"])
                label = (label + " + fader conflict" if label else "Fader conflict (dampened)")

        if mult != 1.0:
            out.at[idx, "luck_score_L5"]     = round(raw * mult, 4)
            out.at[idx, "seasonal_modifier"]  = mult
            out.at[idx, "seasonal_label"]     = label
            modified += 1

    print(f"  Layer 5 (Phase C):   {modified} players modified | "
          f"{vshape} V-shape buys | {slow_amp} slow-starter buys amplified")
    return out

# ------------------------------------------------------------------
# OUTCOMES
# ------------------------------------------------------------------

def compute_outcomes(signals_df: pd.DataFrame, outcome_raw_df: pd.DataFrame) -> pd.DataFrame:
    may_july = outcome_raw_df.groupby("batter").agg(
        outcome_pa=("woba_value", "count"),
        outcome_woba=("woba_value", "mean"),
    ).reset_index()
    merged = signals_df.merge(may_july, on="batter", how="inner")
    before = len(merged)
    merged = merged[merged["outcome_pa"] >= MIN_OUTCOME_PA].copy()
    merged["woba_change"] = merged["outcome_woba"] - merged["april_actual_woba"]
    print(f"  {before} matched | {before - len(merged)} excluded (<{MIN_OUTCOME_PA} PA) "
          f"-> {len(merged)} evaluable")
    flat_n = (merged["woba_change"].abs() < FLAT_THRESHOLD).sum()
    print(f"  {flat_n} flat outcomes (|D wOBA| < {FLAT_THRESHOLD})")
    return merged

# ------------------------------------------------------------------
# CLASSIFY + ACCURACY
# ------------------------------------------------------------------

def classify(df: pd.DataFrame, score_col: str) -> pd.DataFrame:
    out = df.copy()
    conds = [
        out[score_col] >= 0.040,
        out[score_col] >= 0.020,
        out[score_col] <= -0.040,
        out[score_col] <= -0.020,
    ]
    out["signal"] = np.select(conds,
        ["BUY_LOW", "SLIGHT_BUY", "SELL_HIGH", "SLIGHT_SELL"], default="NEUTRAL")
    out["outcome"] = np.where(
        out["woba_change"] >=  FLAT_THRESHOLD, "IMPROVED",
        np.where(out["woba_change"] <= -FLAT_THRESHOLD, "DECLINED", "FLAT")
    )
    return out


def bucket_stats(df: pd.DataFrame) -> dict:
    ev = df[df["signal"].isin(SIGNAL_MAP) & (df["outcome"] != "FLAT")].copy()
    ev["correct"] = ev.apply(lambda r: r["outcome"] == SIGNAL_MAP[r["signal"]], axis=1)
    stats = {}
    for sig in ["BUY_LOW", "SLIGHT_BUY", "SELL_HIGH", "SLIGHT_SELL"]:
        grp = ev[ev["signal"] == sig]
        n, c = len(grp), int(grp["correct"].sum()) if len(grp) > 0 else 0
        stats[sig] = (n, c, c / n if n > 0 else float("nan"))
    ov_n = len(ev); ov_c = int(ev["correct"].sum())
    stats["OVERALL"] = (ov_n, ov_c, ov_c / ov_n if ov_n > 0 else float("nan"))
    return stats

# ------------------------------------------------------------------
# REPORT
# ------------------------------------------------------------------

def report(merged_df: pd.DataFrame):
    d1 = classify(merged_df, "luck_score_L1")
    d2 = classify(merged_df, "luck_score_L2")
    d3 = classify(merged_df, "luck_score_L3")
    d4 = classify(merged_df, "luck_score_L4")
    d5 = classify(merged_df, "luck_score_L5")

    s1 = bucket_stats(d1)
    s2 = bucket_stats(d2)
    s3 = bucket_stats(d3)
    s4 = bucket_stats(d4)
    s5 = bucket_stats(d5)

    phase_c_mask = merged_df["seasonal_modifier"] != 1.0
    s5c = bucket_stats(d5[phase_c_mask])

    WIDTH = 148
    print("\n" + "=" * WIDTH)
    print("WITHIN-SEASON BACKTEST v9 -- FULL PRODUCTION STACK")
    print(f"Signal: April 2024 -> May-July 2024 | Flat: +-{FLAT_THRESHOLD} | RTM: {RTM_BASELINE:.1%}")
    print(f"Layers: L1 core | L2 sweet spot | L3 EV 1.0mph | L4 defense BABIP | L5 Phase C (corrected)")
    print("=" * WIDTH)

    # ---- Main accuracy table ----
    hdr = (
        f"\n{'':14}  "
        f"{'--- L1: Core ---':^24}  "
        f"{'--- L1+2: Sweet Spot ---':^24}  "
        f"{'--- L1+2+3: EV 1.0mph ---':^24}  "
        f"{'--- L1+2+3+4: +Defense ---':^24}  "
        f"{'--- Full v9 ---':^24}  "
        f"{'--- Phase C Only ---':^22}"
    )
    sub = (
        f"{'Signal':<14}  "
        + (f"{'N':>4} {'Acc':>7} {'vs RTM':>7}  " * 5)
        + f"{'N':>4} {'Acc':>7} {'vs RTM':>7}"
    )
    div = "-" * WIDTH

    print(hdr)
    print(sub)
    print(div)

    ORDER = ["BUY_LOW", "SLIGHT_BUY", "SELL_HIGH", "SLIGHT_SELL", "OVERALL"]
    for sig in ORDER:
        if sig == "OVERALL":
            print(div)

        v1n, v1c, v1a = s1.get(sig, (0, 0, float("nan")))
        v2n, v2c, v2a = s2.get(sig, (0, 0, float("nan")))
        v3n, v3c, v3a = s3.get(sig, (0, 0, float("nan")))
        v4n, v4c, v4a = s4.get(sig, (0, 0, float("nan")))
        v5n, v5c, v5a = s5.get(sig, (0, 0, float("nan")))
        cn,  cc,  ca  = s5c.get(sig, (0, 0, float("nan")))

        def fmt(a):  return f"{a:>7.1%}" if not pd.isna(a) else "    n/a"
        def fmtd(a): return f"{a:>+7.1%}" if not pd.isna(a) else "    n/a"

        delta2 = v2a - v1a if not (pd.isna(v2a) or pd.isna(v1a)) else float("nan")
        delta3 = v3a - v1a if not (pd.isna(v3a) or pd.isna(v1a)) else float("nan")
        delta4 = v4a - v1a if not (pd.isna(v4a) or pd.isna(v1a)) else float("nan")
        delta5 = v5a - v1a if not (pd.isna(v5a) or pd.isna(v1a)) else float("nan")

        marker  = " <--" if not pd.isna(delta5) and abs(delta5) >= 0.02 else "    "
        pc_col  = f"  {cn:>4} {fmt(ca)} {fmtd(ca - RTM_BASELINE if not pd.isna(ca) else float('nan'))}" \
                  if cn > 0 else "  (none)"

        print(
            f"{sig:<14}  "
            f"{v1n:>4} {fmt(v1a)} {fmtd(v1a - RTM_BASELINE if not pd.isna(v1a) else float('nan'))}  "
            f"{v2n:>4} {fmt(v2a)} {fmtd(delta2)}  "
            f"{v3n:>4} {fmt(v3a)} {fmtd(delta3)}  "
            f"{v4n:>4} {fmt(v4a)} {fmtd(delta4)}  "
            f"{v5n:>4} {fmt(v5a)} {fmtd(delta5)}{marker}"
            f"{pc_col}"
        )

    # ---- Defense BABIP detail ----
    print(f"\n{'=' * WIDTH}")
    print("LAYER 4 -- DEFENSE BABIP DETAIL")
    print(f"{'=' * WIDTH}")
    print(f"  oaa_babip_adj distribution:")
    adj_col = merged_df["oaa_babip_adj"]
    print(f"    mean={adj_col.mean():>+.5f}  std={adj_col.std():.5f}  "
          f"min={adj_col.min():>+.5f}  max={adj_col.max():>+.5f}")
    print(f"    < -0.004 (elite D, strong): {(adj_col < -0.004).sum()}")
    print(f"    -0.004 to 0 (elite D, weak): {((adj_col >= -0.004) & (adj_col < 0)).sum()}")
    print(f"    = 0 (neutral / no data):    {(adj_col == 0).sum()}")
    print(f"    0 to 0.004 (poor D, weak):  {((adj_col > 0) & (adj_col <= 0.004)).sum()}")
    print(f"    > 0.004 (poor D, strong):   {(adj_col > 0.004).sum()}")

    # Accuracy split by OAA tier
    eval4 = d4[d4["signal"].isin(SIGNAL_MAP) & (d4["outcome"] != "FLAT")].copy()
    eval4["correct"] = eval4.apply(lambda r: r["outcome"] == SIGNAL_MAP[r["signal"]], axis=1)
    eval4["oaa_tier"] = pd.cut(
        eval4["oaa_babip_adj"],
        bins=[-1, -0.004, -0.000001, 0.000001, 0.004, 1],
        labels=["Elite D (strong)", "Elite D (mixed)", "Neutral", "Poor D (mixed)", "Poor D (strong)"],
    )
    print(f"\n  {'OAA Tier':<22} {'N':>5} {'Correct':>8} {'Acc':>8} {'vs RTM':>8}")
    print(f"  {'-' * 58}")
    for tier, grp in eval4.groupby("oaa_tier", observed=True):
        n = len(grp)
        if n < 3:
            continue
        c = int(grp["correct"].sum())
        acc = c / n
        print(f"  {str(tier):<22} {n:>5} {c:>8} {acc:>7.1%} {acc - RTM_BASELINE:>+8.1%}")

    # ---- Phase C detail ----
    print(f"\n{'=' * WIDTH}")
    print("LAYER 5 -- PHASE C DETAIL (corrected multipliers)")
    print(f"{'=' * WIDTH}")
    eval5 = d5[d5["signal"].isin(SIGNAL_MAP) & (d5["outcome"] != "FLAT")].copy()
    eval5["correct"] = eval5.apply(lambda r: r["outcome"] == SIGNAL_MAP[r["signal"]], axis=1)
    eval5["label_group"] = eval5["seasonal_label"].fillna("No pattern (baseline)")
    print(f"  {'Pattern':<44} {'N':>5} {'Correct':>8} {'Acc':>8} {'vs RTM':>8}")
    print(f"  {'-' * 74}")
    for label, grp in eval5.groupby("label_group"):
        n = len(grp)
        if n < 3:
            continue
        c   = int(grp["correct"].sum())
        acc = c / n
        print(f"  {label:<44} {n:>5} {c:>8} {acc:>7.1%} {acc - RTM_BASELINE:>+8.1%}")

    # ---- Signal migration L1 -> v9 ----
    print(f"\n{'=' * WIDTH}")
    print("SIGNAL MIGRATION -- L1 baseline to Full v9")
    print(f"{'=' * WIDTH}")
    mig = (
        d1[["batter", "signal"]].rename(columns={"signal": "L1"})
          .merge(d5[["batter", "signal"]].rename(columns={"signal": "L5"}), on="batter")
    )
    changed = mig[mig["L1"] != mig["L5"]]
    print(f"  Players whose signal bucket changed: {len(changed)}")
    if len(changed):
        print(f"\n  {'L1':<16} -> {'v9':<16}  Count")
        print(f"  {'-' * 45}")
        for (l1s, l5s), grp in changed.groupby(["L1", "L5"]):
            print(f"  {l1s:<16} -> {l5s:<16}  {len(grp)}")

    # ---- Mean wOBA change ----
    print(f"\nMEAN wOBA CHANGE BY SIGNAL (full v9):")
    for sig in ["BUY_LOW", "SLIGHT_BUY", "NEUTRAL", "SLIGHT_SELL", "SELL_HIGH"]:
        grp = d5[d5["signal"] == sig]
        if len(grp) < 3:
            continue
        print(f"  {sig:<14} n={len(grp):>3}  mean={grp['woba_change'].mean():>+.4f}  "
              f"median={grp['woba_change'].median():>+.4f}")

    # ---- Layer-by-layer verdict ----
    print(f"\n{'=' * WIDTH}")
    print("VERDICT")
    print(f"{'=' * WIDTH}")
    v2_ov = 0.815   # known v2 result
    v8_ov = 0.807   # known v8 result

    for label, st in [
        ("L1 baseline            ", s1),
        ("L1+2 (+sweet spot)     ", s2),
        ("L1+2+3 (+EV 1.0mph)   ", s3),
        ("L1+2+3+4 (+defense)   ", s4),
        ("L1+2+3+4+5 (full v9)  ", s5),
    ]:
        ov_n, ov_c, ov_a = st["OVERALL"]
        bl_n, bl_c, bl_a = st.get("BUY_LOW", (0, 0, float("nan")))
        sb_n, sb_c, sb_a = st.get("SLIGHT_BUY", (0, 0, float("nan")))
        beat = "BEATS" if ov_a > RTM_BASELINE else "trails"
        pp   = abs(ov_a - RTM_BASELINE) * 100
        vs_l1 = f"  vs L1: {ov_a - s1['OVERALL'][2]:>+.1%}" if st is not s1 else ""
        bl_str = f"  BUY={bl_a:.1%}" if not pd.isna(bl_a) else ""
        sb_str = f"  SB={sb_a:.1%}" if not pd.isna(sb_a) else ""
        print(f"  {label}: {ov_a:.1%} ({beat} RTM by {pp:.1f}pp){vs_l1}{bl_str}{sb_str}")

    v9_ov = s5["OVERALL"][2]
    print(f"\n  Full v9 overall:  {v9_ov:.1%}")
    print(f"  vs v2 baseline:   {v9_ov - v2_ov:>+.1%}  (v2={v2_ov:.1%})")
    print(f"  vs v8:            {v9_ov - v8_ov:>+.1%}  (v8={v8_ov:.1%})")
    print(f"  Beats 81.5% v2?   {'YES' if v9_ov > 0.815 else 'NO'}")

    sl_v9  = s5["SLIGHT_BUY"][2]
    sl_v2  = 0.667   # known v2 SLIGHT_BUY
    if not pd.isna(sl_v9):
        print(f"\n  SLIGHT_BUY accuracy: {sl_v9:.1%}  vs v2: {sl_v9 - sl_v2:>+.1%}  "
              f"(target: >70%)")
        print(f"  Slow starter correction improved SLIGHT_BUY? "
              f"{'YES' if sl_v9 > sl_v2 else 'NO'}")

# ------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------

def main():
    print("Within-Season Backtest v9 -- Full Production Stack")
    print("=" * 70)

    april_df, outcome_raw_df, team_map_df = load_data()

    print("\nLoading enrichment data...")
    career_stats = load_career_stats()
    patterns     = load_seasonal_patterns()
    oaa_map      = load_oaa_map()
    opp_oaa      = load_or_build_opponent_oaa(oaa_map)

    print("\nComputing Layer 1 (core signal)...")
    signals = compute_layer1(april_df, team_map_df)
    print(f"  {len(signals)} batters with >={MIN_APRIL_PA} April PA")
    vc = pd.cut(signals["luck_score_L1"],
                bins=[-99, -0.040, -0.020, 0.020, 0.040, 99],
                labels=["SELL_HIGH", "SLIGHT_SELL", "NEUTRAL", "SLIGHT_BUY", "BUY_LOW"])
    for sig, count in vc.value_counts().sort_index().items():
        print(f"    {sig:<14} {count}")

    print("\nApplying Layer 2 (sweet spot)...")
    signals = apply_layer2(signals)

    print(f"\nApplying Layer 3 (EV trend, threshold={EV_THRESHOLD} mph)...")
    signals = apply_layer3(signals, career_stats)

    print("\nApplying Layer 4 (defense BABIP)...")
    signals = apply_layer4(signals, opp_oaa)

    print("\nApplying Layer 5 (Phase C, corrected)...")
    signals = apply_layer5(signals, patterns)

    print("\nAggregating May-July outcomes...")
    merged = compute_outcomes(signals, outcome_raw_df)

    report(merged)

    out_path = BASE_DIR / "backtest_results_within_season_v9.csv"
    merged.to_csv(out_path, index=False)
    print(f"\nFull results saved -> {out_path}")


if __name__ == "__main__":
    main()
