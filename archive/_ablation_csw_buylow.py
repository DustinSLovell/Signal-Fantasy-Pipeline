"""
_ablation_csw_buylow.py
Ablation: Buy-low ONLY CSW modifier (Task 4).
Modifies only BUY_LOW signals, not Slight buy.
No reclassification (mirrors production: verdict locked pre-modifier).
"""
import io, sys, json, warnings
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from pathlib import Path

CACHE   = Path("backtest_cache")
YEARS   = [2022, 2023, 2024, 2025]
CSW_DESCS   = {"called_strike", "swinging_strike", "swinging_strike_blocked", "foul_tip"}
MIN_PITCHES = 100
CSW_FIRE    = 0.025
CSW_AMP     = 1.10
CSW_DAMP    = 0.90

CORRECT = {
    "SLIGHT_BUY":  "IMPROVED",
    "BUY_LOW":     "IMPROVED",
    "SLIGHT_SELL": "DECLINED",
    "SELL_HIGH":   "DECLINED",
}

# Build per-year CSW table from parquets
all_csw_rows = []
for _yr in YEARS:
    _path = CACHE / f"pitcher_statcast_april_{_yr}.parquet"
    if not _path.exists():
        continue
    _df = pd.read_parquet(_path, columns=["pitcher", "description"])
    _df = _df[~_df["description"].isin({"automatic_ball", "pitchout"})]
    _df["is_csw"] = _df["description"].isin(CSW_DESCS).astype(int)
    _agg = _df.groupby("pitcher").agg(
        csw_count=("is_csw", "sum"), total=("is_csw", "count")).reset_index()
    _agg = _agg[_agg["total"] >= MIN_PITCHES].copy()
    _agg["csw"] = (_agg["csw_count"] / _agg["total"]).round(4)
    _agg["year"] = _yr
    all_csw_rows.append(_agg)

all_csw = pd.concat(all_csw_rows, ignore_index=True)


def _career_csw_prior(pitcher_id, current_year, min_pitches=200):
    prior = all_csw[(all_csw["pitcher"] == pitcher_id) & (all_csw["year"] < current_year)]
    if prior.empty:
        return float("nan")
    total_w = prior["total"].sum()
    if total_w < min_pitches:
        return float("nan")
    return float((prior["csw"] * prior["total"]).sum() / total_w)


from _pitcher_tier_audit import run_pitcher_audit


def run_year(year, use_csw=False):
    try:
        _, df = run_pitcher_audit(year)
    except Exception:
        return None
    if df is None or df.empty:
        return None
    df = df.copy()
    df["year"] = year

    if use_csw and year >= 2023:
        csw_yr = (all_csw[all_csw["year"] == year][["pitcher", "csw"]]
                  .rename(columns={"csw": "curr_csw"}))
        df = df.merge(csw_yr, on="pitcher", how="left")
        df["career_csw"] = df["pitcher"].apply(
            lambda p: _career_csw_prior(p, year))
        df["csw_gap"] = (df["curr_csw"] - df["career_csw"]).fillna(0.0)

        # BUY_LOW only — Slight buy and all sell signals completely untouched
        buy_lo = df["signal"] == "BUY_LOW"
        csw_up   = df["csw_gap"] >  CSW_FIRE
        csw_down = df["csw_gap"] < -CSW_FIRE

        df.loc[buy_lo & csw_up,   "luck_score"] = (
            df.loc[buy_lo & csw_up,   "luck_score"] * CSW_AMP ).round(4)
        df.loc[buy_lo & csw_down, "luck_score"] = (
            df.loc[buy_lo & csw_down, "luck_score"] * CSW_DAMP).round(4)

        # Reclassify buy-low only (slight buy and sells locked — never promoted/demoted)
        P_SLIGHT_BUY = 0.60
        P_BUY_LOW    = 1.20

        def _reclassify_buylo(row):
            if row["signal"] in ("SELL_HIGH", "SLIGHT_SELL", "SLIGHT_BUY"):
                return row["signal"]  # locked
            if row["signal"] == "BUY_LOW":
                ls = row["luck_score"]
                if ls >= P_BUY_LOW:    return "BUY_LOW"
                if ls >= P_SLIGHT_BUY: return "SLIGHT_BUY"
                return "NEUTRAL"
            return row["signal"]

        df["signal"] = df.apply(_reclassify_buylo, axis=1)
    else:
        df["csw_gap"] = float("nan")
    return df


print("Building pitcher baseline + buy-low-only CSW runs...")
rows_base  = [run_year(y, use_csw=False) for y in YEARS]
rows_csw   = [run_year(y, use_csw=True)  for y in YEARS]
base = pd.concat([d for d in rows_base if d is not None], ignore_index=True)
csw  = pd.concat([d for d in rows_csw  if d is not None], ignore_index=True)


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


tb = accuracy_table(base)
tc = accuracy_table(csw)

print()
print("TASK 4 — CSW BUY-LOW ONLY ABLATION")
print("  Only Buy low modified | No Slight buy change | No reclassification")
print("=" * 65)
print(f"  {'Bucket':<14} {'Baseline':>12} {'BuyLow Only':>13} {'Delta':>8}")
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
    print(f"  {label:<14} {b_acc*100:>7.1f}% n={b_n:<4} "
          f"{c_acc*100:>7.1f}% n={c_n:<4} {(c_acc-b_acc)*100:>+7.1f}pp")

bl_delta = (tc["BUY_LOW"][2]    - tb["BUY_LOW"][2])   * 100
sb_delta = (tc["SLIGHT_BUY"][2] - tb["SLIGHT_BUY"][2])* 100
sh_delta = (tc["SELL_HIGH"][2]  - tb["SELL_HIGH"][2])  * 100
ov_delta = (tc["OVERALL"][2]    - tb["OVERALL"][2])    * 100

print()
print(f"  Reference: Baseline 86.5% (per task spec)")
print(f"  Buy low delta: {bl_delta:+.1f}pp | Slight buy delta: {sb_delta:+.1f}pp | "
      f"Sell high delta: {sh_delta:+.1f}pp")
print()

if bl_delta >= 2.0 and abs(sb_delta) <= 1.0 and sh_delta >= -0.1:
    print("  CSW BUY-LOW: KEPT")
    print(f"  Buy low +{bl_delta:.1f}pp, Slight buy {sb_delta:+.1f}pp (unchanged), "
          f"Sell high {sh_delta:+.1f}pp")
else:
    reasons = []
    if bl_delta < 2.0:
        reasons.append(f"buy low only +{bl_delta:.1f}pp (need >=2pp)")
    if abs(sb_delta) > 1.0:
        reasons.append(f"slight buy changed {sb_delta:+.1f}pp (need within +/-1pp)")
    if sh_delta < -0.1:
        reasons.append(f"sell high regressed {sh_delta:.1f}pp")
    print(f"  CSW BUY-LOW: REVERTED -- {'; '.join(reasons)}")
