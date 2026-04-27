"""
Standalone per-year, per-tier backtest accuracy audit.
Mirrors the v7 hitter scoring logic exactly (L1-L6 layers).
"""
import json, os, sys
import numpy as np
import pandas as pd
from pathlib import Path

BASE_DIR  = Path(".")
CACHE_DIR = BASE_DIR / "backtest_cache"

H_YEARS            = [2022, 2023, 2024, 2025]
MIN_APRIL_PA       = 80
MIN_OUTCOME_PA     = 100
FLAT_THRESHOLD     = 0.015
LEAGUE_AVG_BABIP   = 0.300
EV_THRESHOLD       = 1.0
SELL_HIGH_THRESH   = -0.065
SLIGHT_SELL_THRESH = -0.040

PARK_FACTORS_H = {
    "COL": 1.12, "CIN": 1.08, "TEX": 1.06, "HOU": 1.05,
    "BAL": 1.04, "BOS": 1.04, "PHI": 1.03, "MIL": 1.02,
    "ATL": 1.02, "NYY": 1.01, "TOR": 1.01, "WSH": 1.00,
    "CHC": 1.00, "STL": 1.00, "LAD": 0.99, "NYM": 0.99,
    "ARI": 0.99, "MIN": 0.98, "DET": 0.98, "CLE": 0.98,
    "CWS": 0.97, "SEA": 0.97, "SF":  0.96, "MIA": 0.96,
    "TB":  0.96, "PIT": 0.96, "KC":  0.96, "LAA": 0.95,
    "SD":  0.95, "OAK": 0.94,
}
BIP_EVENTS_H = {
    "single", "double", "triple", "field_out",
    "grounded_into_double_play", "force_out", "double_play", "fielders_choice",
}
SIGNAL_MAP_H = {
    "BUY_LOW":    "IMPROVED",
    "SLIGHT_BUY": "IMPROVED",
    "SELL_HIGH":  "DECLINED",
    "SLIGHT_SELL":"DECLINED",
}
PHASE_C = {
    "vshape_buy": 1.20, "slow_buy": 1.10, "summer_buy": 1.10,
    "fader_sell": 1.15, "fader_buy": 0.90,
}

def classify_h(score):
    if score >= 0.040:               return "BUY_LOW"
    if score >= 0.020:               return "SLIGHT_BUY"
    if score <= SELL_HIGH_THRESH:    return "SELL_HIGH"
    if score <= SLIGHT_SELL_THRESH:  return "SLIGHT_SELL"
    return "NEUTRAL"

def _babip_age_mult(age):
    if age >= 39: return 0.88
    if age >= 37: return 0.91
    if age >= 35: return 0.94
    if age >= 32: return 0.97
    return 1.0

# ── Load shared data ──────────────────────────────────────────────────────────
with open("data/career_stats.json") as f:
    career_stats = {int(k): v for k, v in json.load(f).items()}

with open("data/hitter_career_babip.json") as f:
    raw_cb = json.load(f)
career_babip = {}
for pid_str, rec in raw_cb.items():
    cb = rec.get("career_babip")
    if cb is not None:
        career_babip[int(pid_str)] = float(cb)

seasonal_path = Path("data/seasonal_patterns.json")
if seasonal_path.exists():
    with open(seasonal_path) as f:
        patterns = {int(r["player_id"]): r for r in json.load(f)}
else:
    patterns = {}

# ── Per-year run ──────────────────────────────────────────────────────────────
all_rows = []

for year in H_YEARS:
    april_path   = CACHE_DIR / f"v4_april_{year}.csv"
    outcome_path = CACHE_DIR / f"statcast_{year}_may_july.csv"
    team_path    = CACHE_DIR / f"team_map_{year}.csv"

    if not april_path.exists() or not outcome_path.exists():
        print(f"{year}: cache missing — skip", file=sys.stderr)
        continue

    april   = pd.read_csv(april_path)
    outcome = pd.read_csv(outcome_path)

    if team_path.exists():
        tmap = pd.read_csv(team_path)
        april = april.merge(tmap, on="batter", how="left")
    april["park_factor"] = april["team"].map(PARK_FACTORS_H).fillna(1.0) if "team" in april.columns else 1.0

    # BIP / BABIP / GB aggregation
    batted = april[april["bb_type"].notna() & (april["bb_type"] != "")].copy()
    batted["is_bip"] = batted["events"].isin(BIP_EVENTS_H).astype(int)
    batted["is_hit"] = batted["events"].isin({"single", "double", "triple"}).astype(int)
    batted["is_gb"]  = (batted["bb_type"] == "ground_ball").astype(int)
    bip_agg = batted.groupby("batter").agg(
        bip=("is_bip", "sum"), hits_bip=("is_hit", "sum"), gb=("is_gb", "sum")
    ).reset_index()

    # EV / sweet-spot aggregation
    bbe = april[april["launch_speed"].notna() & april["launch_angle"].notna()].copy()
    bbe_agg = bbe.groupby("batter").apply(
        lambda s: pd.Series({
            "sweet_spot_count": int(((s["launch_speed"] >= 98) & s["launch_angle"].between(8, 32)).sum()),
            "bbe_total":         len(s),
            "avg_exit_velocity": float(s["launch_speed"].mean()),
        })
    ).reset_index()

    # Walk / K aggregation
    april["is_bb"] = april["events"].isin({"walk", "intent_walk"}).astype(int)
    april["is_k"]  = april["events"].isin({"strikeout", "strikeout_double_play"}).astype(int)
    disc_agg = april.groupby("batter").agg(
        bb_count=("is_bb", "sum"), k_count=("is_k", "sum")
    ).reset_index()

    # PA / wOBA / xwOBA
    has_xwoba = "estimated_woba_using_speedangle" in april.columns
    pa_cols = dict(
        april_pa=("woba_value", "count"),
        april_actual_woba=("woba_value", "mean"),
        park_factor=("park_factor", "first"),
    )
    if has_xwoba:
        pa_cols["april_xwoba"] = ("estimated_woba_using_speedangle", "mean")
    pa_agg = april.groupby("batter").agg(**pa_cols).reset_index()
    if not has_xwoba:
        pa_agg["april_xwoba"] = np.nan

    signals = pa_agg.merge(bip_agg, on="batter", how="left")
    if len(bbe_agg) > 0:
        signals = signals.merge(bbe_agg, on="batter", how="left")
    else:
        for col in ["sweet_spot_count", "bbe_total", "avg_exit_velocity"]:
            signals[col] = np.nan
    signals = signals.merge(disc_agg, on="batter", how="left")

    signals["babip"]          = np.where(signals["bip"] > 0, signals["hits_bip"] / signals["bip"], np.nan)
    signals["gb_rate"]        = np.where(signals["bip"] > 0, signals["gb"] / signals["bip"], np.nan)
    signals["sweet_spot_rate"]= np.where(signals["bbe_total"] > 0,
                                          signals["sweet_spot_count"] / signals["bbe_total"], np.nan)
    signals["bb_rate"] = signals["bb_count"] / signals["april_pa"]
    signals["k_rate"]  = signals["k_count"]  / signals["april_pa"]

    # L1: xwOBA gap (correct sign: xwOBA - actual; positive = unlucky = buy)
    signals["xwoba_gap"] = signals["april_xwoba"] - signals["april_actual_woba"]

    # Career BABIP baseline with age adjustment
    def _age_adj_babip(row):
        bid  = int(row["batter"])
        base = career_babip.get(bid, LEAGUE_AVG_BABIP)
        if base == LEAGUE_AVG_BABIP:
            return base
        byr = int((career_stats.get(bid) or {}).get("birth_year") or 0)
        if byr == 0:
            return base
        age = year - byr
        return round(base * _babip_age_mult(age), 4)

    signals["babip_baseline"] = signals.apply(_age_adj_babip, axis=1)

    # Park factor adjustment to BABIP expected
    park_adj = (signals["park_factor"] - 1.0) * 0.10
    signals["babip_expected"] = (signals["babip_baseline"] - park_adj).round(4)

    # L4: GB rate adjustment to BABIP expected
    if signals["gb_rate"].notna().any():
        signals.loc[signals["gb_rate"] > 0.50, "babip_expected"] -= 0.010
        signals.loc[signals["gb_rate"] < 0.35, "babip_expected"] += 0.008

    # L1: BABIP luck (correct sign: expected - actual; positive = unlucky = buy)
    signals["babip_luck"] = signals["babip_expected"] - signals["babip"]

    signals = signals[signals["april_pa"] >= MIN_APRIL_PA].copy()
    signals["luck_score"] = (
        signals["xwoba_gap"]  * 0.60 +
        signals["babip_luck"] * 0.40
    ).round(4)

    # L2: sweet-spot modifier (buy signals only)
    if signals["sweet_spot_rate"].notna().any():
        buy     = signals["luck_score"] > 0
        high_ss = buy & (signals["sweet_spot_rate"] > 0.12)
        low_ss  = buy & (signals["sweet_spot_rate"] < 0.06)
        signals.loc[high_ss, "luck_score"] = (signals.loc[high_ss, "luck_score"] * 1.05).round(4)
        signals.loc[low_ss,  "luck_score"] = (signals.loc[low_ss,  "luck_score"] * 0.95).round(4)

    # L3: EV gate (buy signals only)
    if signals["avg_exit_velocity"].notna().any():
        for idx, row in signals.iterrows():
            if row["luck_score"] <= 0:
                continue
            career_ev = (career_stats.get(int(row["batter"])) or {}).get("avg_exit_velocity")
            if career_ev is None or pd.isna(row["avg_exit_velocity"]):
                continue
            ev_below  = (row["avg_exit_velocity"] - career_ev) < -EV_THRESHOLD
            ss        = row["sweet_spot_rate"]
            low_ss_ev = pd.notna(ss) and ss < 0.08
            if ev_below and low_ss_ev:
                signals.at[idx, "luck_score"] = round(row["luck_score"] * 0.85, 4)
            elif ev_below or low_ss_ev:
                signals.at[idx, "luck_score"] = round(row["luck_score"] * 0.93, 4)

    # L5: discipline gate (buy signals only)
    if signals["bb_rate"].notna().any() and signals["k_rate"].notna().any():
        buy_mask   = signals["luck_score"] > 0
        elite_disc = buy_mask & (signals["bb_rate"] > 0.10) & (signals["k_rate"] < 0.18)
        poor_disc  = buy_mask & ((signals["bb_rate"] < 0.06) | (signals["k_rate"] > 0.28))
        signals.loc[elite_disc, "luck_score"] = (signals.loc[elite_disc, "luck_score"] * 1.08).round(4)
        signals.loc[poor_disc,  "luck_score"] = (signals.loc[poor_disc,  "luck_score"] * 0.88).round(4)

    # L6: seasonal patterns
    if patterns:
        for idx, row in signals.iterrows():
            pid   = int(row["batter"])
            raw   = row["luck_score"]
            if pid not in patterns:
                continue
            p      = patterns[pid]
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
                if is_sell: mult = max(mult, PHASE_C["fader_sell"])
                if is_buy:  mult = min(mult, PHASE_C["fader_buy"])
            if mult != 1.0:
                signals.at[idx, "luck_score"] = round(raw * mult, 4)

    signals["signal"] = signals["luck_score"].apply(classify_h)

    # Outcomes
    mj = outcome.groupby("batter").agg(
        outcome_pa=("woba_value", "count"),
        outcome_woba=("woba_value", "mean"),
    ).reset_index()

    merged = signals.merge(mj, on="batter", how="inner")
    merged = merged[merged["outcome_pa"] >= MIN_OUTCOME_PA].copy()
    merged["woba_change"] = merged["outcome_woba"] - merged["april_actual_woba"]
    merged["outcome"] = np.where(
        merged["woba_change"] >=  FLAT_THRESHOLD, "IMPROVED",
        np.where(merged["woba_change"] <= -FLAT_THRESHOLD, "DECLINED", "FLAT")
    )
    merged["year"] = year
    all_rows.append(merged)

data = pd.concat(all_rows, ignore_index=True)

# ── Build output table ────────────────────────────────────────────────────────
TIERS = ["BUY_LOW", "SLIGHT_BUY", "SLIGHT_SELL", "SELL_HIGH", "OVERALL"]
YEARS = sorted(data["year"].unique())

rows = []
for year in YEARS:
    yr = data[data["year"] == year]
    for tier in TIERS + ["NEUTRAL"]:
        if tier == "OVERALL":
            sub_all = yr[yr["signal"].isin(SIGNAL_MAP_H)]
            sub     = sub_all[sub_all["outcome"] != "FLAT"].copy()
        elif tier == "NEUTRAL":
            sub_all = yr[yr["signal"] == "NEUTRAL"]
            sub     = sub_all.copy()
        else:
            sub_all = yr[yr["signal"] == tier]
            sub     = sub_all[sub_all["outcome"] != "FLAT"].copy()

        n_total = len(sub_all)
        n_flat  = int((sub_all["outcome"] == "FLAT").sum())
        n_imp   = int((sub_all["outcome"] == "IMPROVED").sum())
        n_dec   = int((sub_all["outcome"] == "DECLINED").sum())

        if tier == "NEUTRAL" or n_total == 0:
            n_eval = 0; n_corr = 0; acc = float("nan")
        else:
            if tier == "OVERALL":
                sub["correct"] = sub.apply(lambda r: r["outcome"] == SIGNAL_MAP_H.get(r["signal"]), axis=1)
            else:
                expected = SIGNAL_MAP_H.get(tier)
                sub["correct"] = (sub["outcome"] == expected) if expected else False
            n_eval = len(sub)
            n_corr = int(sub["correct"].sum()) if n_eval > 0 else 0
            acc    = n_corr / n_eval if n_eval > 0 else float("nan")

        avg_chg = sub_all["woba_change"].mean() if n_total > 0 else float("nan")
        rows.append({
            "year": year, "tier": tier,
            "n_total": n_total, "n_flat": n_flat,
            "n_improved": n_imp, "n_declined": n_dec,
            "n_eval": n_eval, "n_correct": n_corr,
            "accuracy": acc,
            "avg_woba_chg": avg_chg,
        })

df = pd.DataFrame(rows)

# ── Print clean table ─────────────────────────────────────────────────────────
TIER_PRINT = ["BUY_LOW", "SLIGHT_BUY", "NEUTRAL", "SLIGHT_SELL", "SELL_HIGH", "OVERALL"]
TIER_LABEL = {
    "BUY_LOW":    "BUY LOW    ",
    "SLIGHT_BUY": "SLIGHT BUY ",
    "NEUTRAL":    "NEUTRAL    ",
    "SLIGHT_SELL":"SLIGHT SELL",
    "SELL_HIGH":  "SELL HIGH  ",
    "OVERALL":    "OVERALL    ",
}

hdr = f"{'Tier':<13}"
for y in YEARS:
    hdr += f"   {y}"
print(hdr)
print("=" * (13 + len(YEARS) * 25))

for tier in TIER_PRINT:
    print(f"\n{TIER_LABEL[tier]}")
    sub = df[df["tier"] == tier]
    ntot_line = "  n(total) :"
    nacc_line = "  accuracy :"
    nchg_line = "  avg wOBA :"
    for y in YEARS:
        row = sub[sub["year"] == y]
        if row.empty:
            ntot_line += "      —  "; nacc_line += "      —  "; nchg_line += "      —  "
            continue
        r = row.iloc[0]
        if tier == "NEUTRAL":
            ntot_line += f"  n={int(r['n_total']):3d}      "
            nacc_line += f"  (no dir)    "
        elif tier == "OVERALL":
            ntot_line += f"  n={int(r['n_eval']):3d}      "
            acc_s = f"{r['accuracy']:.1%}" if r['n_eval'] > 0 else "—"
            nacc_line += f"  {acc_s:<10}"
        else:
            ntot_line += f"  n={int(r['n_eval']):3d}      "
            acc_s = f"{r['accuracy']:.1%}" if r['n_eval'] > 0 else "—"
            nacc_line += f"  {acc_s:<10}"
        chg_s = f"{r['avg_woba_chg']:+.4f}" if not (isinstance(r['avg_woba_chg'], float) and r['avg_woba_chg'] != r['avg_woba_chg']) else "—"
        nchg_line += f"  {chg_s:<10}"
    print(ntot_line)
    if tier != "NEUTRAL":
        print(nacc_line)
    print(nchg_line)

# ── 4-year combined rollup ─────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("4-YEAR COMBINED (2022-2025)")
print("=" * 60)
for tier in TIER_PRINT:
    sub = df[df["tier"] == tier]
    n_tot  = int(sub["n_total"].sum())
    n_ev   = int(sub["n_eval"].sum())
    n_corr = int(sub["n_correct"].sum())
    acc    = n_corr / n_ev if n_ev > 0 else float("nan")
    avg_chg = (sub["avg_woba_chg"] * sub["n_total"]).sum() / n_tot if n_tot > 0 else float("nan")
    if tier == "NEUTRAL":
        print(f"  {TIER_LABEL[tier]}  n={n_tot:3d}  (no directional)  avg_wOBA_chg={avg_chg:+.4f}")
    else:
        acc_s = f"{acc:.1%}" if n_ev > 0 else "—"
        print(f"  {TIER_LABEL[tier]}  n={n_ev:3d}  acc={acc_s:<7}  avg_wOBA_chg={avg_chg:+.4f}")
