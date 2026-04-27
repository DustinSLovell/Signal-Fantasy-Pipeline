"""
_ablation_sprint_v2.py
Sprint speed BABIP modifier ablation — Task 6.
Fix vs v1: uses age from luck_scores.csv (reliable 2026 age),
back-computes age at each backtest year instead of birth_year=0 from JSON.
"""
import io, sys, json, warnings
import numpy as np, pandas as pd
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
warnings.filterwarnings("ignore")

CACHE    = Path("backtest_cache")
YEARS    = [2022, 2023, 2024, 2025]
CURR_YEAR = 2026  # luck_scores.csv age is as-of this year

BIP_EVENTS = {
    "single","double","triple","field_out","force_out",
    "grounded_into_double_play","double_play","fielders_choice",
    "fielders_choice_out","field_error","sac_fly","sac_fly_double_play",
}
SLIGHT_BUY_T, BUY_LOW_T     =  0.025,  0.050
SELL_HIGH_T, SLIGHT_SELL_T  = -0.075, -0.045
MIN_APRIL_PA, MIN_OUT_PA, FLAT = 80, 100, 0.015

SPRINT_DECLINE_ADJ = -0.008
SPRINT_IMPROVE_ADJ = +0.005
SPRINT_MIN_AGE     = 28
SPRINT_MAX_AGE     = 30

CORRECT = {
    "BUY_LOW": "IMPROVED", "SLIGHT_BUY": "IMPROVED",
    "SELL_HIGH": "DECLINED", "SLIGHT_SELL": "DECLINED",
}

# ── Load data ─────────────────────────────────────────────────────────────────
with open("data/hitter_career_babip.json") as f:
    raw = json.load(f)
career_babip_h = {
    int(k): float(v["career_babip"])
    for k, v in raw.items()
    if isinstance(v, dict) and v.get("career_babip") is not None
}

with open("data/hitter_career_sprint.json") as f:
    sprint_db = {int(k): v for k, v in json.load(f).items()}

# Build batter_id -> 2026 age from luck_scores.csv (reliable source)
luck = pd.read_csv("luck_scores.csv")[["batter", "age"]].dropna()
luck = luck[luck["age"] > 0]
age_2026 = dict(zip(luck["batter"].astype(int), luck["age"].astype(int)))


def get_age(batter_id, year):
    curr = age_2026.get(int(batter_id))
    if curr is None:
        return 0
    return int(curr) - (CURR_YEAR - year)


def classify(s, xg=float("nan")):
    if s >= BUY_LOW_T:     sig = "BUY_LOW"
    elif s >= SLIGHT_BUY_T: sig = "SLIGHT_BUY"
    elif s <= SELL_HIGH_T:  sig = "SELL_HIGH"
    elif s <= SLIGHT_SELL_T:sig = "SLIGHT_SELL"
    else:                   sig = "NEUTRAL"
    if sig == "SLIGHT_BUY" and not np.isnan(xg) and xg < 0.015:
        return "NEUTRAL"
    return sig


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
    batted["is_bip"] = batted["events"].isin(BIP_EVENTS).astype(int)
    batted["is_hit"] = batted["events"].isin({"single", "double", "triple"}).astype(int)
    batted["is_gb"]  = (batted["bb_type"] == "ground_ball").astype(int)
    bip_agg = batted.groupby("batter").agg(
        bip=("is_bip","sum"), hits_bip=("is_hit","sum"), gb=("is_gb","sum")).reset_index()

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
           .merge(bip_agg, on="batter", how="left")
           .merge(bbe_agg, on="batter", how="left")
           .merge(disc, on="batter", how="left"))

    sig["babip"]   = np.where(sig["bip"] > 0, sig["hits_bip"] / sig["bip"], np.nan)
    sig["gb_rate"] = np.where(sig["bip"] > 0, sig["gb"] / sig["bip"], np.nan)
    sig["ss_rate"] = np.where(sig["bbe"].fillna(0) > 0,
                               sig["ss"].fillna(0) / sig["bbe"].fillna(1), np.nan)
    sig["bb_rate"]   = sig["bb_count"] / sig["april_pa"]
    sig["k_rate"]    = sig["k_count"]  / sig["april_pa"]
    sig["xwoba_gap"] = sig["april_xwoba"] - sig["april_woba"]

    sig["career_babip"] = sig["batter"].map(lambda b: career_babip_h.get(int(b), 0.300))
    # Use age from luck_scores.csv, back-computed to this year
    sig["age"] = sig["batter"].apply(lambda b: get_age(b, year))

    sig["babip_expected"] = sig["career_babip"].copy()
    sig.loc[sig["gb_rate"] > 0.50, "babip_expected"] -= 0.010
    sig.loc[sig["gb_rate"] < 0.35, "babip_expected"] += 0.008

    if use_sprint:
        def _sprint_adj(row):
            pid   = int(row["batter"])
            age   = int(row["age"])
            rec   = sprint_db.get(pid)
            if rec is None or age == 0:
                return 0.0
            trend = rec.get("trend", "stable")
            if trend == "declining" and age >= SPRINT_MAX_AGE:
                return SPRINT_DECLINE_ADJ
            if trend == "improving" and age <= SPRINT_MIN_AGE:
                return SPRINT_IMPROVE_ADJ
            return 0.0

        sig["sprint_adj"] = sig.apply(_sprint_adj, axis=1)
        sig["babip_expected"] = (sig["babip_expected"] + sig["sprint_adj"]).round(4)
    else:
        sig["sprint_adj"] = 0.0

    sig["babip_luck"] = sig["babip_expected"] - sig["babip"]
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

    sig["signal"] = sig.apply(
        lambda r: classify(r["luck_score"], r.get("xwoba_gap", float("nan"))), axis=1)

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
rows_base   = [score_year(y, False) for y in YEARS]
rows_sprint = [score_year(y, True)  for y in YEARS]
base   = pd.concat([d for d in rows_base   if d is not None], ignore_index=True)
sprint = pd.concat([d for d in rows_sprint if d is not None], ignore_index=True)

tb = accuracy_table(base)
ts = accuracy_table(sprint)

print("TASK 6 — SPRINT SPEED v2 ABLATION (age from luck_scores.csv)")
print("=" * 65)
print(f"  {'Bucket':<14} {'Baseline':>12} {'w/Sprint':>12} {'Delta':>8}")
print(f"  {'-'*52}")
for sig, label in [
    ("BUY_LOW",    "Buy low"),
    ("SLIGHT_BUY", "Slight buy"),
    ("SELL_HIGH",  "Sell high"),
    ("SLIGHT_SELL","Slight sell"),
    ("OVERALL",    "Overall"),
]:
    b_c, b_n, b_acc = tb[sig]
    s_c, s_n, s_acc = ts[sig]
    print(f"  {label:<14} {b_acc*100:>7.1f}% n={b_n:<4} {s_acc*100:>7.1f}% n={s_n:<4} {(s_acc-b_acc)*100:>+7.1f}pp")

print()
print("  AGE 30+ COHORT (declining sprint gate):")
for sig, label in [("BUY_LOW","Buy low"),("SLIGHT_BUY","Slight buy"),("OVERALL","Overall")]:
    b30 = base[base["age"] >= 30]
    s30 = sprint[sprint["age"] >= 30]
    tb30 = accuracy_table(b30); ts30 = accuracy_table(s30)
    b_c,b_n,b_acc = tb30[sig]; s_c,s_n,s_acc = ts30[sig]
    print(f"    {label:<14} base {b_acc*100:.1f}% n={b_n:<3} sprint {s_acc*100:.1f}% n={s_n:<3} {(s_acc-b_acc)*100:>+6.1f}pp")

print()
# Sprint modifier counts
sprint_fired = sprint[sprint["sprint_adj"].abs().fillna(0) > 0]
n_decline = (sprint["sprint_adj"].fillna(0) == SPRINT_DECLINE_ADJ).sum()
n_improve = (sprint["sprint_adj"].fillna(0) == SPRINT_IMPROVE_ADJ).sum()
n_fired   = len(sprint_fired)
print(f"  Sprint modifier fired: {n_fired} player-seasons")
print(f"    Declining (BABIP -8pts, age>=30): {n_decline}")
print(f"    Improving (BABIP +5pts, age<=28): {n_improve}")

# How many of those improved their prediction?
if n_fired > 0:
    corr_base   = sprint_fired.apply(
        lambda r: CORRECT.get(r["signal"],"?") == r["outcome"], axis=1)
    print(f"    Correct predictions among fired: {corr_base.sum()}/{n_fired} "
          f"({corr_base.mean()*100:.1f}%)")

print()
ov_delta  = (ts["OVERALL"][2]    - tb["OVERALL"][2])   * 100
age30_ov  = accuracy_table(sprint[sprint["age"]>=30])["OVERALL"]
age30_b   = accuracy_table(base[base["age"]>=30])["OVERALL"]
age30_delta = (age30_ov[2] - age30_b[2]) * 100

if ov_delta >= 1.0 or age30_delta >= 3.0:
    print("  SPRINT SPEED v2: IMPLEMENT IN score_luck.py")
    print(f"  Overall {ov_delta:+.1f}pp | Age 30+ {age30_delta:+.1f}pp")
else:
    print(f"  SPRINT SPEED v2: REVERTED -- overall {ov_delta:+.1f}pp "
          f"(need >=1pp), age 30+ {age30_delta:+.1f}pp (need >=3pp)")
    print("  Finding: sprint trend signal is real but insufficient in isolation")
