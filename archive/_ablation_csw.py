"""
_ablation_csw.py — Component B: CSW% vs career ablation test for pitchers.
Read-only: does not modify any production or backtest files.
Uses _pitcher_tier_audit.run_pitcher_audit for baseline + patched version.
"""
import io, sys, json, warnings
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from pathlib import Path

CACHE   = Path("backtest_cache")
YEARS   = [2022, 2023, 2024, 2025]
CSW_DESCS = {"called_strike","swinging_strike","swinging_strike_blocked","foul_tip"}
MIN_PITCHES = 100
CSW_FIRE    = 0.025   # |csw_gap| threshold to fire modifier
CSW_AMP     = 1.10
CSW_DAMP    = 0.90

with open("data/pitcher_career_csw.json") as f:
    career_csw_db = {int(k): v for k, v in json.load(f).items()}

# ── Build per-year CSW table from parquets ────────────────────────────────────
all_csw_rows = []
for year in YEARS:
    path = CACHE / f"pitcher_statcast_april_{year}.parquet"
    if not path.exists():
        continue
    df = pd.read_parquet(path, columns=["pitcher","description"])
    df = df[~df["description"].isin({"automatic_ball","pitchout"})]
    df["is_csw"] = df["description"].isin(CSW_DESCS).astype(int)
    agg = df.groupby("pitcher").agg(
        csw_count=("is_csw","sum"), total=("is_csw","count")).reset_index()
    agg = agg[agg["total"] >= MIN_PITCHES].copy()
    agg["csw"] = (agg["csw_count"] / agg["total"]).round(4)
    agg["year"] = year
    all_csw_rows.append(agg)

all_csw = pd.concat(all_csw_rows, ignore_index=True)


def _career_csw_prior(pitcher_id, current_year, min_pitches=200):
    """Weighted career CSW from years prior to current_year."""
    prior = all_csw[(all_csw["pitcher"] == pitcher_id) & (all_csw["year"] < current_year)]
    if prior.empty:
        return float("nan")
    total_w = prior["total"].sum()
    if total_w < min_pitches:
        return float("nan")
    return float((prior["csw"] * prior["total"]).sum() / total_w)


# ── Run pitcher audit for each year and apply CSW modifier ───────────────────
from _pitcher_tier_audit import run_pitcher_audit

CORRECT = {
    "SLIGHT_BUY":  "IMPROVED",
    "BUY_LOW":     "IMPROVED",
    "SLIGHT_SELL": "DECLINED",
    "SELL_HIGH":   "DECLINED",
}


def run_year(year, use_csw=False):
    try:
        metrics, df = run_pitcher_audit(year)
    except Exception:
        return None
    if df is None or df.empty:
        return None
    df = df.copy()
    df["year"] = year

    if use_csw and year >= 2023:
        # Get current-year CSW for each pitcher
        csw_yr = all_csw[all_csw["year"] == year][["pitcher","csw"]].rename(columns={"csw":"curr_csw"})
        df = df.merge(csw_yr, on="pitcher", how="left")
        df["career_csw"] = df["pitcher"].apply(lambda p: _career_csw_prior(p, year))
        df["csw_gap"] = (df["curr_csw"] - df["career_csw"]).fillna(0.0)

        # Modifier: applies to BUY signals only (sell unaffected per spec)
        buy_mask  = df["signal"].isin(["BUY_LOW", "SLIGHT_BUY"])
        csw_up    = df["csw_gap"] >  CSW_FIRE
        csw_down  = df["csw_gap"] < -CSW_FIRE

        # Reclassify by adjusting era_fip_gap proxy via luck_score column
        # Use luck_score as the signal proxy
        df.loc[buy_mask & csw_up,   "luck_score"] = (df.loc[buy_mask & csw_up,   "luck_score"] * CSW_AMP ).round(4)
        df.loc[buy_mask & csw_down, "luck_score"] = (df.loc[buy_mask & csw_down, "luck_score"] * CSW_DAMP).round(4)

        # Re-classify after luck_score change
        P_SLIGHT_BUY = 0.60
        P_BUY_LOW    = 1.20

        def _reclassify(row):
            ls = row["luck_score"]
            era = row.get("era", float("nan"))
            # Keep original sell signals unchanged
            if row["signal"] in ("SELL_HIGH","SLIGHT_SELL"):
                return row["signal"]
            # Slight buy gate: ERA >= 4.0 (already applied in audit but re-check)
            if ls >= P_BUY_LOW:
                return "BUY_LOW"
            if ls >= P_SLIGHT_BUY:
                if not np.isnan(era) and era < 4.0:
                    return "NEUTRAL"
                return "SLIGHT_BUY"
            return "NEUTRAL"

        df["signal"] = df.apply(_reclassify, axis=1)
    else:
        df["csw_gap"] = float("nan")

    return df


print("Building pitcher baseline + CSW runs...")
rows_base = [run_year(y, use_csw=False) for y in YEARS]
rows_csw  = [run_year(y, use_csw=True)  for y in YEARS]

base = pd.concat([d for d in rows_base if d is not None], ignore_index=True)
csw  = pd.concat([d for d in rows_csw  if d is not None], ignore_index=True)


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


tb = accuracy_table(base)
tc = accuracy_table(csw)

print()
print("COMPONENT B — CSW% vs CAREER (PITCHER) ABLATION TEST")
print("=" * 65)
print(f"{'Signal':14} {'Baseline':>14} {'With CSW':>14} {'Delta':>8}")
print("-" * 55)
for sig in list(CORRECT.keys()) + ["OVERALL"]:
    b_c, b_n, b_acc = tb[sig]
    c_c, c_n, c_acc = tc[sig]
    delta = c_acc - b_acc
    print(f"{sig:14} {b_c}/{b_n}={b_acc:>6.1%}  {c_c}/{c_n}={c_acc:>6.1%}  {delta:+.1%}")

csw_fired = csw[csw["csw_gap"].abs().fillna(0) > CSW_FIRE]
print(f"\nCSW modifier fired: {len(csw_fired)} pitcher-seasons (2023-2025)")
print(f"  CSW improving (amplify buy): {(csw['csw_gap'].fillna(0) > CSW_FIRE).sum()}")
print(f"  CSW declining (dampen buy):  {(csw['csw_gap'].fillna(0) < -CSW_FIRE).sum()}")

delta_overall = tc["OVERALL"][2] - tb["OVERALL"][2]
bl_regress    = tc["BUY_LOW"][2]  - tb["BUY_LOW"][2]
sh_regress    = tc["SELL_HIGH"][2] - tb["SELL_HIGH"][2]
sb_delta      = tc["SLIGHT_BUY"][2] - tb["SLIGHT_BUY"][2]
print()
if delta_overall >= 0.01 and bl_regress >= -0.01 and sh_regress >= -0.01:
    print("CSW: KEPT")
    print(f"  Overall {delta_overall:+.1%} | Buy_low {bl_regress:+.1%} | Sell_high {sh_regress:+.1%}")
else:
    reason = []
    if delta_overall < 0.01: reason.append(f"overall delta only {delta_overall:+.1%}")
    if bl_regress < -0.01:   reason.append(f"buy_low regressed {bl_regress:.1%}")
    if sh_regress < -0.01:   reason.append(f"sell_high regressed {sh_regress:.1%}")
    print(f"CSW: REVERTED — {'; '.join(reason)}")
