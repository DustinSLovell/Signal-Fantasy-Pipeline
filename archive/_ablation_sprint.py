"""
_ablation_sprint.py — Component C: Sprint speed BABIP baseline modifier.
Read-only: does not modify any production or backtest files.
"""
import io, sys, json, warnings
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from pathlib import Path

CACHE = Path("backtest_cache")
YEARS = [2022, 2023, 2024, 2025]

BIP_EVENTS_H = {
    "single","double","triple","field_out","force_out",
    "grounded_into_double_play","double_play","fielders_choice",
    "fielders_choice_out","field_error","sac_fly","sac_fly_double_play",
}
SWING_DESCS = {
    "swinging_strike","swinging_strike_blocked","foul","foul_tip",
    "foul_bunt","missed_bunt","bunt_foul_tip","hit_into_play",
}
SLIGHT_BUY_T, BUY_LOW_T     =  0.025,  0.050
SELL_HIGH_T, SLIGHT_SELL_T  = -0.075, -0.045
MIN_APRIL_PA, MIN_OUT_PA, FLAT = 80, 100, 0.015

# Sprint speed BABIP adjustments (applied to babip_expected baseline)
SPRINT_DECLINE_ADJ = -0.008   # slower legs = fewer infield hits
SPRINT_IMPROVE_ADJ = +0.005   # faster legs = more infield hits
SPRINT_MIN_AGE     = 28       # improving only rewarded for younger players
SPRINT_MAX_AGE     = 30       # declining only penalized for older players

with open("data/hitter_career_babip.json") as f:
    raw = json.load(f)
career_babip_h  = {int(k): float(v["career_babip"])
                   for k, v in raw.items() if v.get("career_babip") is not None}
career_meta_h   = {int(k): v for k, v in raw.items()}

with open("data/hitter_career_sprint.json") as f:
    sprint_db = {int(k): v for k, v in json.load(f).items()}


def _classify(s, xg=float("nan")):
    if s >= BUY_LOW_T:      sig = "BUY_LOW"
    elif s >= SLIGHT_BUY_T: sig = "SLIGHT_BUY"
    elif s <= SELL_HIGH_T:  sig = "SELL_HIGH"
    elif s <= SLIGHT_SELL_T:sig = "SLIGHT_SELL"
    else:                    sig = "NEUTRAL"
    if sig == "SLIGHT_BUY" and not np.isnan(xg) and xg < 0.015:
        return "NEUTRAL"
    return sig


def _get_age(batter_id, year):
    meta = career_meta_h.get(int(batter_id), {}) or {}
    byr  = int(meta.get("birth_year", 0) or 0)
    return (year - byr) if byr > 0 else 0


def score_year(year, use_sprint=False):
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
    batted["is_bip"] = batted["events"].isin(BIP_EVENTS_H).astype(int)
    batted["is_hit"] = batted["events"].isin({"single","double","triple"}).astype(int)
    batted["is_gb"]  = (batted["bb_type"] == "ground_ball").astype(int)
    bip_agg = batted.groupby("batter").agg(
        bip=("is_bip","sum"), hits_bip=("is_hit","sum"), gb=("is_gb","sum")).reset_index()

    bbe = april[april["launch_speed"].notna() & april["launch_angle"].notna()].copy()
    if len(bbe):
        bbe_agg = bbe.groupby("batter").apply(lambda s: pd.Series({
            "ss": int(((s["launch_speed"]>=98)&s["launch_angle"].between(8,32)).sum()),
            "bbe": len(s),
        })).reset_index()
    else:
        bbe_agg = pd.DataFrame(columns=["batter","ss","bbe"])

    april["is_bb"] = april["events"].isin({"walk","intent_walk"}).astype(int)
    april["is_k"]  = april["events"].isin({"strikeout","strikeout_double_play"}).astype(int)
    disc = april.groupby("batter").agg(
        bb_count=("is_bb","sum"), k_count=("is_k","sum")).reset_index()

    pa_agg = april.groupby("batter").agg(
        april_pa=("woba_value","count"),
        april_woba=("woba_value","mean"),
        april_xwoba=("estimated_woba_using_speedangle","mean"),
    ).reset_index()

    sig = (pa_agg
           .merge(bip_agg,  on="batter", how="left")
           .merge(bbe_agg,  on="batter", how="left")
           .merge(disc,     on="batter", how="left"))

    sig["babip"]    = np.where(sig["bip"]>0, sig["hits_bip"]/sig["bip"], np.nan)
    sig["gb_rate"]  = np.where(sig["bip"]>0, sig["gb"]/sig["bip"], np.nan)
    sig["ss_rate"]  = np.where(sig["bbe"].fillna(0)>0,
                                sig["ss"].fillna(0)/sig["bbe"].fillna(1), np.nan)
    sig["bb_rate"]  = sig["bb_count"] / sig["april_pa"]
    sig["k_rate"]   = sig["k_count"]  / sig["april_pa"]
    sig["xwoba_gap"] = sig["april_xwoba"] - sig["april_woba"]

    sig["career_babip"] = sig["batter"].map(
        lambda b: career_babip_h.get(int(b), 0.300))
    sig["age"] = sig["batter"].apply(lambda b: _get_age(b, year))

    sig["babip_expected"] = sig["career_babip"].copy()
    sig.loc[sig["gb_rate"] > 0.50, "babip_expected"] -= 0.010
    sig.loc[sig["gb_rate"] < 0.35, "babip_expected"] += 0.008

    # Sprint modifier on babip_expected
    if use_sprint:
        def _sprint_adj(row):
            pid = int(row["batter"])
            rec = sprint_db.get(pid)
            if rec is None:
                return 0.0
            trend = rec.get("trend", "stable")
            age   = int(row["age"])
            # Declining sprint AND age >= SPRINT_MAX_AGE
            if trend == "declining" and age >= SPRINT_MAX_AGE:
                return SPRINT_DECLINE_ADJ
            # Improving sprint AND age <= SPRINT_MIN_AGE
            if trend == "improving" and age <= SPRINT_MIN_AGE:
                return SPRINT_IMPROVE_ADJ
            return 0.0
        sig["sprint_adj"] = sig.apply(_sprint_adj, axis=1)
        sig["babip_expected"] = (sig["babip_expected"] + sig["sprint_adj"]).round(4)
    else:
        sig["sprint_adj"] = 0.0

    sig["babip_luck"] = sig["babip_expected"] - sig["babip"]

    sig = sig[sig["april_pa"] >= MIN_APRIL_PA].copy()
    sig["luck_score"] = (sig["xwoba_gap"]*0.60 + sig["babip_luck"]*0.40).round(4)

    buy = sig["luck_score"] > 0
    sig.loc[buy & (sig["ss_rate"] > 0.12), "luck_score"] = (sig.loc[buy & (sig["ss_rate"]>0.12), "luck_score"] * 1.05).round(4)
    sig.loc[buy & (sig["ss_rate"] < 0.06), "luck_score"] = (sig.loc[buy & (sig["ss_rate"]<0.06), "luck_score"] * 0.95).round(4)
    buy = sig["luck_score"] > 0
    sig.loc[buy & (sig["bb_rate"]>0.10) & (sig["k_rate"]<0.18), "luck_score"] = (sig.loc[buy & (sig["bb_rate"]>0.10) & (sig["k_rate"]<0.18), "luck_score"] * 1.08).round(4)
    sig.loc[buy & ((sig["bb_rate"]<0.06)|(sig["k_rate"]>0.28)), "luck_score"] = (sig.loc[buy & ((sig["bb_rate"]<0.06)|(sig["k_rate"]>0.28)), "luck_score"] * 0.88).round(4)
    sig["luck_score"] = sig["luck_score"].round(4)

    sig["signal"] = sig.apply(
        lambda r: _classify(r["luck_score"], r.get("xwoba_gap", float("nan"))), axis=1)

    may_july = outcome.groupby("batter").agg(
        out_pa=("woba_value","count"), out_woba=("woba_value","mean")).reset_index()
    merged = sig.merge(may_july, on="batter", how="inner")
    merged = merged[merged["out_pa"] >= MIN_OUT_PA].copy()
    merged["woba_change"] = merged["out_woba"] - merged["april_woba"]
    merged["outcome"] = np.where(merged["woba_change"] >=  FLAT, "IMPROVED",
                        np.where(merged["woba_change"] <= -FLAT, "DECLINED", "FLAT"))
    merged["year"] = year
    return merged


CORRECT = {
    "SLIGHT_BUY": "IMPROVED", "BUY_LOW": "IMPROVED",
    "SLIGHT_SELL": "DECLINED", "SELL_HIGH": "DECLINED",
}


def accuracy_table(df):
    rows = {}
    for sig, exp in CORRECT.items():
        sub = df[(df["signal"]==sig) & (df["outcome"]!="FLAT")]
        n = len(sub); c = (sub["outcome"]==exp).sum()
        rows[sig] = (c, n, c/n if n else 0)
    in_sig = df[df["outcome"]!="FLAT"][df[df["outcome"]!="FLAT"]["signal"].isin(CORRECT)]
    tc = in_sig.apply(lambda r: r["outcome"]==CORRECT.get(r["signal"],"?"),axis=1).sum()
    rows["OVERALL"] = (tc, len(in_sig), tc/len(in_sig) if len(in_sig) else 0)
    return rows


rows_base   = [score_year(y, use_sprint=False) for y in YEARS]
rows_sprint = [score_year(y, use_sprint=True)  for y in YEARS]
base   = pd.concat([d for d in rows_base   if d is not None], ignore_index=True)
sprint = pd.concat([d for d in rows_sprint if d is not None], ignore_index=True)

tb = accuracy_table(base)
ts = accuracy_table(sprint)

print("COMPONENT C — SPRINT SPEED BABIP MODIFIER ABLATION TEST")
print("=" * 65)
print(f"{'Signal':14} {'Baseline':>14} {'With Sprint':>14} {'Delta':>8}")
print("-" * 55)
for sig in list(CORRECT.keys()) + ["OVERALL"]:
    b_c, b_n, b_acc = tb[sig]
    s_c, s_n, s_acc = ts[sig]
    delta = s_acc - b_acc
    print(f"{sig:14} {b_c}/{b_n}={b_acc:>6.1%}  {s_c}/{s_n}={s_acc:>6.1%}  {delta:+.1%}")

# Age 30+ sub-analysis
print()
print("AGE 30+ COHORT ANALYSIS:")
sprint_30 = sprint[sprint["age"] >= 30] if "age" in sprint.columns else sprint
base_30   = base[base["age"] >= 30]   if "age" in base.columns else base
t30_b = accuracy_table(base_30)
t30_s = accuracy_table(sprint_30)
for sig in ["SLIGHT_BUY","BUY_LOW","OVERALL"]:
    b_c,b_n,b_acc = t30_b[sig]
    s_c,s_n,s_acc = t30_s[sig]
    print(f"  {sig:14} baseline {b_c}/{b_n}={b_acc:.1%}  sprint {s_c}/{s_n}={s_acc:.1%}  {s_acc-b_acc:+.1%}")

sprint_fired = sprint[(sprint["sprint_adj"].abs().fillna(0) > 0)]
print(f"\nSprint adjustment fired: {len(sprint_fired)} player-seasons")
print(f"  Declining (BABIP lowered -8pts): {(sprint['sprint_adj'].fillna(0)==SPRINT_DECLINE_ADJ).sum()}")
print(f"  Improving (BABIP raised +5pts): {(sprint['sprint_adj'].fillna(0)==SPRINT_IMPROVE_ADJ).sum()}")

delta_overall = ts["OVERALL"][2] - tb["OVERALL"][2]
bl_d = ts["BUY_LOW"][2]  - tb["BUY_LOW"][2]
sh_d = ts["SELL_HIGH"][2] - tb["SELL_HIGH"][2]
print()
if delta_overall >= 0.01 and bl_d >= -0.01 and sh_d >= -0.01:
    print(f"SPRINT SPEED: KEPT")
    print(f"  Overall {delta_overall:+.1%} | Buy_low {bl_d:+.1%} | Sell_high {sh_d:+.1%}")
else:
    reason = []
    if delta_overall < 0.01: reason.append(f"overall delta only {delta_overall:+.1%}")
    if bl_d < -0.01: reason.append(f"buy_low regressed {bl_d:.1%}")
    if sh_d < -0.01: reason.append(f"sell_high regressed {sh_d:.1%}")
    print(f"SPRINT SPEED: REVERTED — {'; '.join(reason)}")
