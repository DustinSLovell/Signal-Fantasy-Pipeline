"""
_ablation_chase.py — Component A: Chase rate (O-Swing%) ablation test.
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

SWING_DESCS = {
    "swinging_strike", "swinging_strike_blocked", "foul", "foul_tip",
    "foul_bunt", "missed_bunt", "bunt_foul_tip", "hit_into_play",
}
BIP_EVENTS_H = {
    "single","double","triple","field_out","force_out",
    "grounded_into_double_play","double_play","fielders_choice",
    "fielders_choice_out","field_error","sac_fly","sac_fly_double_play",
}
SLIGHT_BUY_T, BUY_LOW_T     =  0.025,  0.050
SELL_HIGH_T, SLIGHT_SELL_T  = -0.075, -0.045
MIN_APRIL_PA, MIN_OUT_PA, FLAT = 80, 100, 0.015
CHASE_FIRE   = 0.040   # |chase_gap| threshold to fire modifier
CHASE_AMP    = 1.10    # amplification factor
CHASE_DAMP   = 0.90    # dampen factor

with open("data/hitter_career_babip.json") as f:
    raw = json.load(f)
career_babip_h = {int(k): float(v["career_babip"])
                  for k, v in raw.items() if v.get("career_babip") is not None}

# ── Build per-year O-swing table ─────────────────────────────────────────────
all_osw_rows = []
for year in YEARS:
    path = CACHE / f"v4_april_{year}.csv"
    if not path.exists():
        continue
    df = pd.read_csv(path)
    oop = df[df["zone"].isin([11, 12, 13, 14])].copy()
    swings = oop.groupby("batter")["description"].apply(
        lambda s: s.isin(SWING_DESCS).sum())
    total  = oop.groupby("batter").size()
    yr_df  = pd.DataFrame({"o_swing": swings / total, "n_oop": total}).reset_index()
    yr_df["year"] = year
    all_osw_rows.append(yr_df)

all_osw = pd.concat(all_osw_rows, ignore_index=True)


def _career_o_swing(batter_id, current_year, min_pitches=30):
    prior = all_osw[(all_osw["batter"] == batter_id) & (all_osw["year"] < current_year)]
    if prior.empty:
        return float("nan")
    total_w = prior["n_oop"].sum()
    if total_w < min_pitches:
        return float("nan")
    return float((prior["o_swing"] * prior["n_oop"]).sum() / total_w)


def _classify(s, xg=float("nan")):
    if s >= BUY_LOW_T:      sig = "BUY_LOW"
    elif s >= SLIGHT_BUY_T: sig = "SLIGHT_BUY"
    elif s <= SELL_HIGH_T:  sig = "SELL_HIGH"
    elif s <= SLIGHT_SELL_T:sig = "SLIGHT_SELL"
    else:                    sig = "NEUTRAL"
    # xwOBA gate (already validated)
    if sig == "SLIGHT_BUY" and not np.isnan(xg) and xg < 0.015:
        return "NEUTRAL"
    return sig


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
    batted["is_bip"] = batted["events"].isin(BIP_EVENTS_H).astype(int)
    batted["is_hit"] = batted["events"].isin({"single","double","triple"}).astype(int)
    bip_agg = batted.groupby("batter").agg(
        bip=("is_bip","sum"), hits_bip=("is_hit","sum")).reset_index()

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
    sig["ss_rate"]  = np.where(sig["bbe"].fillna(0)>0,
                                sig["ss"].fillna(0)/sig["bbe"].fillna(1), np.nan)
    sig["bb_rate"]  = sig["bb_count"] / sig["april_pa"]
    sig["k_rate"]   = sig["k_count"]  / sig["april_pa"]
    sig["xwoba_gap"] = sig["april_xwoba"] - sig["april_woba"]
    sig["career_babip"] = sig["batter"].map(lambda b: career_babip_h.get(int(b), 0.300))
    sig["babip_luck"]   = sig["career_babip"] - sig["babip"]

    sig = sig[sig["april_pa"] >= MIN_APRIL_PA].copy()
    sig["luck_score"] = (sig["xwoba_gap"]*0.60 + sig["babip_luck"]*0.40).round(4)
    buy = sig["luck_score"] > 0
    sig.loc[buy & (sig["ss_rate"] > 0.12), "luck_score"] = (sig.loc[buy & (sig["ss_rate"]>0.12), "luck_score"] * 1.05).round(4)
    sig.loc[buy & (sig["ss_rate"] < 0.06), "luck_score"] = (sig.loc[buy & (sig["ss_rate"]<0.06), "luck_score"] * 0.95).round(4)
    buy = sig["luck_score"] > 0
    sig.loc[buy & (sig["bb_rate"]>0.10) & (sig["k_rate"]<0.18), "luck_score"] = (sig.loc[buy & (sig["bb_rate"]>0.10) & (sig["k_rate"]<0.18), "luck_score"] * 1.08).round(4)
    sig.loc[buy & ((sig["bb_rate"]<0.06)|(sig["k_rate"]>0.28)), "luck_score"] = (sig.loc[buy & ((sig["bb_rate"]<0.06)|(sig["k_rate"]>0.28)), "luck_score"] * 0.88).round(4)
    sig["luck_score"] = sig["luck_score"].round(4)

    # ── Chase rate modifier ───────────────────────────────────────────────────
    if use_chase and year >= 2023:
        oop = april[april["zone"].isin([11, 12, 13, 14])].copy()
        sw  = oop.groupby("batter")["description"].apply(lambda s: s.isin(SWING_DESCS).sum())
        tot = oop.groupby("batter").size()
        osw = pd.DataFrame({"curr_o_swing": sw/tot}).reset_index()
        sig = sig.merge(osw, on="batter", how="left")
        sig["career_o_swing"] = sig["batter"].apply(
            lambda b: _career_o_swing(b, year))
        sig["chase_gap"] = (sig["curr_o_swing"] - sig["career_o_swing"]).fillna(0.0)

        chasing_more = sig["chase_gap"] > CHASE_FIRE
        chasing_less = sig["chase_gap"] < -CHASE_FIRE
        buy_pos  = sig["luck_score"] > 0
        sell_neg = sig["luck_score"] < 0

        sig.loc[buy_pos  & chasing_less, "luck_score"] = (sig.loc[buy_pos  & chasing_less, "luck_score"] * CHASE_AMP ).round(4)
        sig.loc[buy_pos  & chasing_more, "luck_score"] = (sig.loc[buy_pos  & chasing_more, "luck_score"] * CHASE_DAMP).round(4)
        sig.loc[sell_neg & chasing_more, "luck_score"] = (sig.loc[sell_neg & chasing_more, "luck_score"] * CHASE_AMP ).round(4)
        sig.loc[sell_neg & chasing_less, "luck_score"] = (sig.loc[sell_neg & chasing_less, "luck_score"] * CHASE_DAMP).round(4)
    else:
        sig["chase_gap"] = float("nan")

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


CORRECT = {"SLIGHT_BUY":"IMPROVED","BUY_LOW":"IMPROVED",
           "SLIGHT_SELL":"DECLINED","SELL_HIGH":"DECLINED"}

def accuracy_table(df):
    rows = {}
    for sig, exp in CORRECT.items():
        sub = df[(df["signal"]==sig) & (df["outcome"]!="FLAT")]
        n = len(sub); c = (sub["outcome"]==exp).sum()
        rows[sig] = (c, n, c/n if n else 0)
    in_sig = df[df["outcome"]!="FLAT"][df[df["outcome"]!="FLAT"]["signal"].isin(CORRECT)]
    tot_c  = in_sig.apply(lambda r: r["outcome"]==CORRECT.get(r["signal"],"?"), axis=1).sum()
    rows["OVERALL"] = (tot_c, len(in_sig), tot_c/len(in_sig) if len(in_sig) else 0)
    return rows


# ── Run both modes ────────────────────────────────────────────────────────────
rows_base  = [score_year(y, use_chase=False) for y in YEARS]
rows_chase = [score_year(y, use_chase=True)  for y in YEARS]
base  = pd.concat([d for d in rows_base  if d is not None], ignore_index=True)
chase = pd.concat([d for d in rows_chase if d is not None], ignore_index=True)

tb = accuracy_table(base)
tc = accuracy_table(chase)

print("COMPONENT A — CHASE RATE (O-SWING% vs CAREER) ABLATION TEST")
print("=" * 65)
print(f"{'Signal':14} {'Baseline':>14} {'With Chase':>14} {'Delta':>8}")
print("-" * 55)
for sig in list(CORRECT.keys()) + ["OVERALL"]:
    b_c, b_n, b_acc = tb[sig]
    c_c, c_n, c_acc = tc[sig]
    delta = c_acc - b_acc
    print(f"{sig:14} {b_c}/{b_n}={b_acc:>6.1%}  {c_c}/{c_n}={c_acc:>6.1%}  {delta:+.1%}")

print()
chase_fired = chase[(chase["chase_gap"].abs().fillna(0) > CHASE_FIRE) &
                    (chase["year"] >= 2023)]
print(f"Chase modifier fired: {len(chase_fired)} player-seasons (2023-2025)")
print(f"  Chasing more (dampen buy / amplify sell): {(chase['chase_gap'].fillna(0)>CHASE_FIRE).sum()}")
print(f"  Chasing less (amplify buy / dampen sell): {(chase['chase_gap'].fillna(0)<-CHASE_FIRE).sum()}")

# Decision
delta_overall = tc["OVERALL"][2] - tb["OVERALL"][2]
bl_regress = tc["BUY_LOW"][2] - tb["BUY_LOW"][2]
sh_regress = tc["SELL_HIGH"][2] - tb["SELL_HIGH"][2]
print()
if delta_overall >= 0.01 and bl_regress >= -0.01 and sh_regress >= -0.01:
    print("CHASE RATE: KEPT")
    print(f"  Overall +{delta_overall:.1%} | Buy_low delta {bl_regress:+.1%} | Sell_high delta {sh_regress:+.1%}")
else:
    reason = []
    if delta_overall < 0.01: reason.append(f"overall delta only {delta_overall:+.1%} (need >= +1pp)")
    if bl_regress < -0.01:   reason.append(f"buy_low regressed {bl_regress:.1%}")
    if sh_regress < -0.01:   reason.append(f"sell_high regressed {sh_regress:.1%}")
    print(f"CHASE RATE: REVERTED — {'; '.join(reason)}")
