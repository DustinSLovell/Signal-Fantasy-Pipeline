"""
_ablation_csw_combined.py
Compare: ERA gate only  vs  ERA gate + CSW modifier
"""
import io, sys, json, warnings
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd
from pathlib import Path

CACHE = Path("backtest_cache")
YEARS = [2022, 2023, 2024, 2025]
CSW_DESCS = {"called_strike","swinging_strike","swinging_strike_blocked","foul_tip"}
CSW_FIRE = 0.025
CSW_AMP, CSW_DAMP = 1.10, 0.90
P_SB, P_BL = 0.60, 1.20

with open("data/pitcher_career_csw.json") as f:
    _raw = json.load(f)
career_csw_db = {int(k): v for k, v in _raw.items()}

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
    agg = agg[agg["total"] >= 100].copy()
    agg["csw"] = (agg["csw_count"]/agg["total"]).round(4)
    agg["year"] = year
    all_csw_rows.append(agg)
all_csw = pd.concat(all_csw_rows, ignore_index=True)


def career_csw_prior(pid, year, min_p=200):
    prior = all_csw[(all_csw["pitcher"]==pid) & (all_csw["year"]<year)]
    if prior.empty: return float("nan")
    w = prior["total"].sum()
    if w < min_p: return float("nan")
    return float((prior["csw"]*prior["total"]).sum() / w)


from _pitcher_tier_audit import run_pitcher_audit

CORRECT = {
    "SLIGHT_BUY": "IMPROVED", "BUY_LOW": "IMPROVED",
    "SLIGHT_SELL": "DECLINED", "SELL_HIGH": "DECLINED",
}

all_rows = []
for year in YEARS:
    try:
        _, df = run_pitcher_audit(year)
        if df is not None and len(df):
            df["year"] = year
            all_rows.append(df.copy())
    except Exception:
        pass
full = pd.concat(all_rows, ignore_index=True)

# ── Variant 1: ERA gate only ──────────────────────────────────────────────────
era_gate = full.copy()
sb_low_era = (era_gate["signal"] == "SLIGHT_BUY") & (era_gate["era"] < 4.0)
era_gate.loc[sb_low_era, "signal"] = "NEUTRAL"

# ── Variant 2: ERA gate + CSW modifier ───────────────────────────────────────
era_csw = full.copy()
era_csw.loc[(era_csw["signal"] == "SLIGHT_BUY") & (era_csw["era"] < 4.0), "signal"] = "NEUTRAL"

# Merge current-year CSW and compute gaps
csw_by_year = {}
for year in [2023, 2024, 2025]:
    csw_yr = all_csw[all_csw["year"] == year].set_index("pitcher")["csw"].to_dict()
    csw_by_year[year] = csw_yr

era_csw["curr_csw"] = era_csw.apply(
    lambda r: csw_by_year.get(r["year"], {}).get(r["pitcher"], float("nan")), axis=1)
era_csw["career_csw"] = era_csw.apply(
    lambda r: career_csw_prior(r["pitcher"], r["year"]) if r["year"] >= 2023 else float("nan"), axis=1)
era_csw["csw_gap"] = (era_csw["curr_csw"] - era_csw["career_csw"]).fillna(0.0)

# Apply modifier to 2023+ buy signals
apply_mask = (era_csw["year"] >= 2023) & era_csw["signal"].isin(["BUY_LOW","SLIGHT_BUY"])
csw_up   = era_csw["csw_gap"] >  CSW_FIRE
csw_down = era_csw["csw_gap"] < -CSW_FIRE

era_csw.loc[apply_mask & csw_up,   "luck_score"] = (era_csw.loc[apply_mask & csw_up,   "luck_score"] * CSW_AMP ).round(4)
era_csw.loc[apply_mask & csw_down, "luck_score"] = (era_csw.loc[apply_mask & csw_down, "luck_score"] * CSW_DAMP).round(4)

# Re-classify buy signals after modifier
for idx in era_csw[apply_mask].index:
    ls  = era_csw.at[idx, "luck_score"]
    era = era_csw.at[idx, "era"]
    if ls >= P_BL:
        era_csw.at[idx, "signal"] = "BUY_LOW"
    elif ls >= P_SB:
        era_csw.at[idx, "signal"] = "NEUTRAL" if (not np.isnan(era) and era < 4.0) else "SLIGHT_BUY"
    else:
        era_csw.at[idx, "signal"] = "NEUTRAL"


def acc_table(df):
    rows = {}
    for sig, exp in CORRECT.items():
        sub = df[(df["signal"] == sig) & (df["outcome"] != "FLAT")]
        n = len(sub); c = (sub["outcome"] == exp).sum()
        rows[sig] = (c, n, c/n if n else 0)
    ins = df[df["outcome"] != "FLAT"]
    ins = ins[ins["signal"].isin(CORRECT)]
    tc = ins.apply(lambda r: r["outcome"] == CORRECT.get(r["signal"], "?"), axis=1).sum()
    rows["OVERALL"] = (tc, len(ins), tc/len(ins) if len(ins) else 0)
    return rows


teg = acc_table(era_gate)
tec = acc_table(era_csw)

print("COMBINED: ERA GATE vs ERA GATE + CSW MODIFIER")
print("=" * 65)
print(f"{'Signal':14} {'ERA gate only':>16} {'ERA gate + CSW':>16} {'Delta':>8}")
print("-" * 60)
for sig in list(CORRECT.keys()) + ["OVERALL"]:
    b_c, b_n, b_acc = teg[sig]
    c_c, c_n, c_acc = tec[sig]
    delta = c_acc - b_acc
    print(f"{sig:14} {b_c}/{b_n}={b_acc:>6.1%}  {c_c}/{c_n}={c_acc:>6.1%}  {delta:+.1%}")

csw_applied = apply_mask & (era_csw["csw_gap"].abs().fillna(0) > CSW_FIRE)
print(f"\nCSW modifier fired on buy signals: {csw_applied.sum()} pitcher-seasons")
print(f"  Improving (amplified): {(apply_mask & csw_up).sum()}")
print(f"  Declining (dampened):  {(apply_mask & csw_down).sum()}")

delta_overall = tec["OVERALL"][2] - teg["OVERALL"][2]
bl_d = tec["BUY_LOW"][2]  - teg["BUY_LOW"][2]
sh_d = tec["SELL_HIGH"][2] - teg["SELL_HIGH"][2]
sb_d = tec["SLIGHT_BUY"][2] - teg["SLIGHT_BUY"][2]
print()
if delta_overall >= 0.01 and bl_d >= -0.01 and sh_d >= -0.01:
    print(f"CSW: KEPT (vs ERA-gate baseline)")
    print(f"  Overall {delta_overall:+.1%} | Buy_low {bl_d:+.1%} | Slight_buy {sb_d:+.1%} | Sell_high {sh_d:+.1%}")
else:
    reason = []
    if delta_overall < 0.01: reason.append(f"overall delta only {delta_overall:+.1%}")
    if bl_d < -0.01: reason.append(f"buy_low regressed {bl_d:.1%}")
    if sh_d < -0.01: reason.append(f"sell_high regressed {sh_d:.1%}")
    print(f"CSW: REVERTED — {'; '.join(reason)}")
