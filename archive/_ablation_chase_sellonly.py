"""
_ablation_chase_sellonly.py
Ablation: sell-side-only chase rate modifier (Task 2).
Two-tier thresholds: gap>0.040 -> x1.10, gap>0.060 -> x1.15.
No modification to buy or neutral signals.
"""
import io, sys, json, warnings
import numpy as np, pandas as pd
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
warnings.filterwarnings("ignore")

CACHE = Path("backtest_cache")
YEARS = [2022, 2023, 2024, 2025]

SWING_DESCS = {
    "swinging_strike", "swinging_strike_blocked", "foul", "foul_tip",
    "foul_bunt", "missed_bunt", "bunt_foul_tip", "hit_into_play",
}
BIP_EVENTS = {
    "single", "double", "triple", "field_out", "force_out",
    "grounded_into_double_play", "double_play", "fielders_choice",
    "fielders_choice_out", "field_error", "sac_fly", "sac_fly_double_play",
}
SLIGHT_BUY_T, BUY_LOW_T    =  0.025,  0.050
SELL_HIGH_T, SLIGHT_SELL_T = -0.075, -0.045
MIN_APRIL_PA, MIN_OUT_PA, FLAT = 80, 100, 0.015

CHASE_STRONG   = 0.060
CHASE_MODERATE = 0.040

CORRECT = {
    "BUY_LOW": "IMPROVED", "SLIGHT_BUY": "IMPROVED",
    "SELL_HIGH": "DECLINED", "SLIGHT_SELL": "DECLINED",
}

# ── Load career data ──────────────────────────────────────────────────────────
with open("data/hitter_career_babip.json") as f:
    raw = json.load(f)
career_babip_h = {
    int(k): float(v["career_babip"])
    for k, v in raw.items()
    if isinstance(v, dict) and v.get("career_babip") is not None
}

# Pre-build per-year per-batter O-swing from April cache
all_osw_rows = []
for _yr in YEARS:
    _path = CACHE / f"v4_april_{_yr}.csv"
    if not _path.exists():
        continue
    _df = pd.read_csv(_path)
    _oop = _df[_df["zone"].isin([11, 12, 13, 14])].copy()
    _sw  = _oop.groupby("batter")["description"].apply(
        lambda s: s.isin(SWING_DESCS).sum())
    _tot = _oop.groupby("batter").size()
    _yr_df = pd.DataFrame({"o_swing": _sw / _tot, "n_oop": _tot}).reset_index()
    _yr_df["year"] = _yr
    all_osw_rows.append(_yr_df)
all_osw = pd.concat(all_osw_rows, ignore_index=True)


def career_o_swing(bid, curr_year, min_pitches=30):
    prior = all_osw[(all_osw["batter"] == bid) & (all_osw["year"] < curr_year)]
    if prior.empty:
        return float("nan")
    tw = prior["n_oop"].sum()
    if tw < min_pitches:
        return float("nan")
    return float((prior["o_swing"] * prior["n_oop"]).sum() / tw)


def classify(s):
    if s >= BUY_LOW_T:     return "BUY_LOW"
    if s >= SLIGHT_BUY_T:  return "SLIGHT_BUY"
    if s <= SELL_HIGH_T:   return "SELL_HIGH"
    if s <= SLIGHT_SELL_T: return "SLIGHT_SELL"
    return "NEUTRAL"


def score_year(year, use_chase=False):
    ap = CACHE / f"v4_april_{year}.csv"
    ou = CACHE / f"statcast_{year}_may_july.csv"
    tm = CACHE / f"team_map_{year}.csv"
    if not ap.exists() or not ou.exists():
        return None

    april   = pd.read_csv(ap)
    outcome = pd.read_csv(ou)
    if tm.exists():
        april = april.merge(pd.read_csv(tm), on="batter", how="left")

    batted = april[april["bb_type"].notna() & (april["bb_type"] != "")].copy()
    batted["is_bip"] = batted["events"].isin(BIP_EVENTS).astype(int)
    batted["is_hit"] = batted["events"].isin({"single", "double", "triple"}).astype(int)
    bip_agg = batted.groupby("batter").agg(
        bip=("is_bip", "sum"), hits_bip=("is_hit", "sum")).reset_index()

    bbe = april[april["launch_speed"].notna() & april["launch_angle"].notna()].copy()
    if len(bbe):
        bbe_agg = bbe.groupby("batter").apply(lambda s: pd.Series({
            "ss":  int(((s["launch_speed"] >= 98) & s["launch_angle"].between(8, 32)).sum()),
            "bbe": len(s),
        })).reset_index()
    else:
        bbe_agg = pd.DataFrame(columns=["batter", "ss", "bbe"])

    april["is_bb"] = april["events"].isin({"walk", "intent_walk"}).astype(int)
    april["is_k"]  = april["events"].isin({"strikeout", "strikeout_double_play"}).astype(int)
    disc = april.groupby("batter").agg(
        bb_count=("is_bb", "sum"), k_count=("is_k", "sum")).reset_index()

    pa_agg = april.groupby("batter").agg(
        april_pa=("woba_value", "count"),
        april_woba=("woba_value", "mean"),
        april_xwoba=("estimated_woba_using_speedangle", "mean"),
    ).reset_index()

    sig = (pa_agg
           .merge(bip_agg,  on="batter", how="left")
           .merge(bbe_agg,  on="batter", how="left")
           .merge(disc,     on="batter", how="left"))

    sig["babip"]     = np.where(sig["bip"] > 0, sig["hits_bip"] / sig["bip"], np.nan)
    sig["ss_rate"]   = np.where(sig["bbe"].fillna(0) > 0,
                                 sig["ss"].fillna(0) / sig["bbe"].fillna(1), np.nan)
    sig["bb_rate"]   = sig["bb_count"] / sig["april_pa"]
    sig["k_rate"]    = sig["k_count"]  / sig["april_pa"]
    sig["xwoba_gap"] = sig["april_xwoba"] - sig["april_woba"]
    sig["career_babip"] = sig["batter"].map(lambda b: career_babip_h.get(int(b), 0.300))
    sig["babip_luck"]   = sig["career_babip"] - sig["babip"]

    sig = sig[sig["april_pa"] >= MIN_APRIL_PA].copy()
    sig["luck_score"] = (sig["xwoba_gap"] * 0.60 + sig["babip_luck"] * 0.40).round(4)

    buy = sig["luck_score"] > 0
    sig.loc[buy & (sig["ss_rate"] > 0.12), "luck_score"] = (
        sig.loc[buy & (sig["ss_rate"] > 0.12), "luck_score"] * 1.05).round(4)
    sig.loc[buy & (sig["ss_rate"] < 0.06), "luck_score"] = (
        sig.loc[buy & (sig["ss_rate"] < 0.06), "luck_score"] * 0.95).round(4)
    buy = sig["luck_score"] > 0
    elite = buy & (sig["bb_rate"] > 0.10) & (sig["k_rate"] < 0.18)
    poor  = buy & ((sig["bb_rate"] < 0.06) | (sig["k_rate"] > 0.28))
    sig.loc[elite, "luck_score"] = (sig.loc[elite, "luck_score"] * 1.08).round(4)
    sig.loc[poor,  "luck_score"] = (sig.loc[poor,  "luck_score"] * 0.88).round(4)

    # Classify BEFORE modifier so production-matched behavior (verdict locked pre-modifier)
    sig["signal"] = sig["luck_score"].apply(classify)

    # ── Sell-side ONLY chase modifier ────────────────────────────────────────
    # Applied after classification — mirrors production score_luck.py where
    # verdict is assigned before the modifier runs and NOT re-assigned after.
    if use_chase and year >= 2023:
        oop = april[april["zone"].isin([11, 12, 13, 14])].copy()
        sw  = oop.groupby("batter")["description"].apply(lambda s: s.isin(SWING_DESCS).sum())
        tot = oop.groupby("batter").size()
        osw = pd.DataFrame({"curr_o_swing": sw / tot}).reset_index()
        sig = sig.merge(osw, on="batter", how="left")
        sig["career_oswing"] = sig["batter"].apply(lambda b: career_o_swing(b, year))
        sig["chase_gap"] = (sig["curr_o_swing"] - sig["career_oswing"]).fillna(0.0)

        sell_sig = sig["signal"].isin(["SELL_HIGH", "SLIGHT_SELL"])
        strong   = sig["chase_gap"] > CHASE_STRONG
        moderate = (sig["chase_gap"] > CHASE_MODERATE) & ~strong
        # Sell-side only — no buy modification, no reclassification
        sig.loc[sell_sig & strong,   "luck_score"] = (
            sig.loc[sell_sig & strong,   "luck_score"] * 1.15).round(4)
        sig.loc[sell_sig & moderate, "luck_score"] = (
            sig.loc[sell_sig & moderate, "luck_score"] * 1.10).round(4)

    may_july = outcome.groupby("batter").agg(
        out_pa=("woba_value", "count"),
        out_woba=("woba_value", "mean")).reset_index()
    merged = sig.merge(may_july, on="batter", how="inner")
    merged = merged[merged["out_pa"] >= MIN_OUT_PA].copy()
    merged["woba_change"] = merged["out_woba"] - merged["april_woba"]
    merged["outcome"] = np.where(
        merged["woba_change"] >=  FLAT, "IMPROVED",
        np.where(merged["woba_change"] <= -FLAT, "DECLINED", "FLAT"))
    merged["year"] = year
    return merged


def accuracy_table(df):
    rows = {}
    for sig, exp in CORRECT.items():
        sub = df[(df["signal"] == sig) & (df["outcome"] != "FLAT")]
        n = len(sub)
        c = (sub["outcome"] == exp).sum()
        rows[sig] = (c, n, c / n if n else 0.0)
    in_sig = df[(df["outcome"] != "FLAT") & df["signal"].isin(CORRECT)]
    tc = in_sig.apply(
        lambda r: r["outcome"] == CORRECT.get(r["signal"], "?"), axis=1).sum()
    rows["OVERALL"] = (tc, len(in_sig), tc / len(in_sig) if len(in_sig) else 0.0)
    return rows


# ── Run ───────────────────────────────────────────────────────────────────────
base  = pd.concat([d for d in [score_year(y, False) for y in YEARS] if d is not None],
                  ignore_index=True)
chase = pd.concat([d for d in [score_year(y, True)  for y in YEARS] if d is not None],
                  ignore_index=True)
tb = accuracy_table(base)
tc = accuracy_table(chase)

print("TASK 2 — SELL-SIDE ONLY CHASE ABLATION")
print("  Thresholds: gap>0.040 -> x1.10 | gap>0.060 -> x1.15")
print("  No buy-signal modification")
print("=" * 65)
print(f"  {'Bucket':<14} {'Baseline':>12} {'w/Chase Sell':>13} {'Delta':>8}")
print(f"  {'-'*52}")
for sig, label in [
    ("BUY_LOW",    "Buy low"),
    ("SLIGHT_BUY", "Slight buy"),
    ("SELL_HIGH",  "Sell high"),
    ("SLIGHT_SELL","Slight sell"),
    ("OVERALL",    "Overall"),
]:
    b_c, b_n, b_acc = tb[sig]
    c_c, c_n, c_acc = tc[sig]
    print(f"  {label:<14} {b_acc*100:>7.1f}% n={b_n:<4} {c_acc*100:>7.1f}% n={c_n:<4} {(c_acc-b_acc)*100:>+7.1f}pp")

sh_base  = tb["SELL_HIGH"][2] * 100
sh_chase = tc["SELL_HIGH"][2] * 100
ov_base  = tb["OVERALL"][2] * 100
ov_chase = tc["OVERALL"][2] * 100
print()
print(f"  Sell high: {sh_base:.1f}% -> {sh_chase:.1f}%")

# How many sell signals were modified?
if "chase_gap" in chase.columns:
    mods = chase[chase["chase_gap"].fillna(0) > CHASE_MODERATE]
    print(f"  Chase modifier fired: {len(mods)} player-seasons (strong: "
          f"{(chase['chase_gap'].fillna(0) > CHASE_STRONG).sum()}, "
          f"moderate: {((chase['chase_gap'].fillna(0) > CHASE_MODERATE) & (chase['chase_gap'].fillna(0) <= CHASE_STRONG)).sum()})")
print()
if sh_chase >= 99.0 and ov_chase >= 88.0:
    print("  CHASE SELL-SIDE: KEPT")
elif sh_chase < 99.0:
    print(f"  CHASE SELL-SIDE: REVERTED -- sell high dropped to {sh_chase:.1f}%")
else:
    print(f"  CHASE SELL-SIDE: REVERTED -- overall {ov_chase:.1f}% < 88.0%")
