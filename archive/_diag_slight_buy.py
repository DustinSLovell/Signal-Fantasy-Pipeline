"""
_diag_slight_buy.py  —  Diagnostic: slight buy misses, hitters + pitchers.
Read-only: does not modify any backtest files.
"""
import io, sys, json, warnings
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from pathlib import Path

BASE  = Path(".")
CACHE = BASE / "backtest_cache"
YEARS = [2022, 2023, 2024, 2025]

BIP_EVENTS_H = {
    "single","double","triple","field_out","force_out",
    "grounded_into_double_play","double_play","fielders_choice",
    "fielders_choice_out","field_error","sac_fly","sac_fly_double_play",
}

# ── Option 3 thresholds (what produced 80.7% slight buy) ───────────────────
SLIGHT_BUY_T   =  0.025
BUY_LOW_T      =  0.050
SELL_HIGH_T    = -0.075
SLIGHT_SELL_T  = -0.045

P_SLIGHT_BUY_T =  0.60
P_BUY_LOW_T    =  1.20

FLAT_THRESH    = 0.015
MIN_APRIL_PA   = 80
MIN_OUT_PA     = 100

PARK_H = {
    "COL":1.12,"CIN":1.08,"TEX":1.06,"HOU":1.05,"BAL":1.04,"BOS":1.04,
    "PHI":1.03,"MIL":1.02,"ATL":1.02,"NYY":1.01,"TOR":1.01,"WSH":1.00,
    "CHC":1.00,"STL":1.00,"LAD":0.99,"NYM":0.99,"ARI":0.99,"MIN":0.98,
    "DET":0.98,"CLE":0.98,"CWS":0.97,"SEA":0.97,"SF":0.96,"MIA":0.96,
    "TB":0.96,"PIT":0.96,"KC":0.96,"LAA":0.95,"SD":0.95,"OAK":0.94,
}

# ── Load support data ───────────────────────────────────────────────────────
with open("data/hitter_career_babip.json") as f:
    raw = json.load(f)
career_babip_h = {int(k): float(v["career_babip"]) for k,v in raw.items()
                  if v.get("career_babip") is not None}
career_meta_h  = {int(k): v for k,v in raw.items()}

# Build name lookup from luck_scores.csv (batter -> name)
_luck_names = pd.read_csv("luck_scores.csv", usecols=["batter","name"]) if Path("luck_scores.csv").exists() else pd.DataFrame(columns=["batter","name"])
name_lk = dict(zip(_luck_names["batter"].astype(int), _luck_names["name"]))

with open("data/pitcher_career_babip.json") as f:
    pitcher_career = json.load(f)
career_babip_p = {int(k): float(v["career_babip_allowed"]) for k,v in pitcher_career.items()
                  if v.get("career_babip_allowed") is not None}

def _babip_age_mult(age):
    if age < 26: return 1.03
    if age < 30: return 1.00
    if age < 33: return 0.97
    if age < 36: return 0.94
    return 0.90


# ===========================================================================
# HITTER DIAGNOSTIC
# ===========================================================================

def score_hitter_year(year):
    ap = CACHE / f"v4_april_{year}.csv"
    ou = CACHE / f"statcast_{year}_may_july.csv"
    tm = CACHE / f"team_map_{year}.csv"
    if not ap.exists() or not ou.exists():
        return None

    april   = pd.read_csv(ap)
    outcome = pd.read_csv(ou)
    if tm.exists():
        tmap  = pd.read_csv(tm)
        april = april.merge(tmap, on="batter", how="left")
    april["park_factor"] = (
        april["team"].map(PARK_H).fillna(1.0) if "team" in april.columns else 1.0
    )

    batted = april[april["bb_type"].notna() & (april["bb_type"] != "")].copy()
    batted["is_bip"] = batted["events"].isin(BIP_EVENTS_H).astype(int)
    batted["is_hit"] = batted["events"].isin({"single","double","triple"}).astype(int)
    batted["is_gb"]  = (batted["bb_type"] == "ground_ball").astype(int)
    bip_agg = batted.groupby("batter").agg(
        bip=("is_bip","sum"), hits_bip=("is_hit","sum"), gb=("is_gb","sum")
    ).reset_index()

    bbe = april[april["launch_speed"].notna() & april["launch_angle"].notna()].copy()
    if len(bbe):
        bbe_agg = bbe.groupby("batter").apply(lambda s: pd.Series({
            "sweet_spot_count": int(((s["launch_speed"]>=98)&s["launch_angle"].between(8,32)).sum()),
            "bbe_total": len(s),
            "avg_ev": float(s["launch_speed"].mean()),
        })).reset_index()
    else:
        bbe_agg = pd.DataFrame(columns=["batter","sweet_spot_count","bbe_total","avg_ev"])

    april["is_bb"] = april["events"].isin({"walk","intent_walk"}).astype(int)
    april["is_k"]  = april["events"].isin({"strikeout","strikeout_double_play"}).astype(int)
    disc = april.groupby("batter").agg(
        bb_count=("is_bb","sum"), k_count=("is_k","sum")).reset_index()

    has_xwoba = "estimated_woba_using_speedangle" in april.columns
    pa_agg = april.groupby("batter").agg(
        april_pa=("woba_value","count"),
        april_woba=("woba_value","mean"),
        **({
            "april_xwoba": ("estimated_woba_using_speedangle","mean")
        } if has_xwoba else {}),
        park_factor=("park_factor","first"),
    ).reset_index()
    if not has_xwoba:
        pa_agg["april_xwoba"] = np.nan

    sig = pa_agg.merge(bip_agg, on="batter", how="left")
    if len(bbe_agg):
        sig = sig.merge(bbe_agg, on="batter", how="left")
    else:
        sig[["sweet_spot_count","bbe_total","avg_ev"]] = np.nan
    sig = sig.merge(disc, on="batter", how="left")

    sig["babip"]      = np.where(sig["bip"]>0, sig["hits_bip"]/sig["bip"], np.nan)
    sig["gb_rate"]    = np.where(sig["bip"]>0, sig["gb"]/sig["bip"], np.nan)
    sig["ss_rate"]    = np.where(sig["bbe_total"].fillna(0)>0,
                                  sig["sweet_spot_count"].fillna(0)/sig["bbe_total"].fillna(1), np.nan)
    sig["bb_rate"]    = sig["bb_count"] / sig["april_pa"]
    sig["k_rate"]     = sig["k_count"]  / sig["april_pa"]
    sig["xwoba_gap"]  = sig["april_xwoba"] - sig["april_woba"]

    sig["career_babip"] = sig["batter"].map(
        lambda b: career_babip_h.get(int(b), 0.300))
    sig["age"] = sig["batter"].apply(
        lambda b: year - int((career_meta_h.get(int(b),{}) or {}).get("birth_year",0) or 0))

    def _age_adj(row):
        base = row["career_babip"]
        meta = career_meta_h.get(int(row["batter"]), {})
        byr  = int((meta or {}).get("birth_year", 0) or 0)
        if byr == 0: return base
        return round(base * _babip_age_mult(year - byr), 4)
    sig["babip_baseline"] = sig.apply(_age_adj, axis=1)

    park_adj = (sig["park_factor"] - 1.0) * 0.10
    sig["babip_expected"] = (sig["babip_baseline"] - park_adj).round(4)
    sig.loc[sig["gb_rate"] > 0.50, "babip_expected"] -= 0.010
    sig.loc[sig["gb_rate"] < 0.35, "babip_expected"] += 0.008
    sig["babip_luck"] = sig["babip_expected"] - sig["babip"]
    sig["babip_gap"]  = sig["babip"] - sig["babip_baseline"]   # current - career

    sig = sig[sig["april_pa"] >= MIN_APRIL_PA].copy()
    sig["luck_score"] = (sig["xwoba_gap"]*0.60 + sig["babip_luck"]*0.40).round(4)

    # L2 sweet spot
    buy = sig["luck_score"] > 0
    if sig["ss_rate"].notna().any():
        sig.loc[buy & (sig["ss_rate"] > 0.12), "luck_score"] *= 1.05
        sig.loc[buy & (sig["ss_rate"] < 0.06), "luck_score"] *= 0.95
        sig["luck_score"] = sig["luck_score"].round(4)

    # L5 discipline
    buy = sig["luck_score"] > 0
    sig.loc[buy & (sig["bb_rate"]>0.10) & (sig["k_rate"]<0.18), "luck_score"] *= 1.08
    sig.loc[buy & ((sig["bb_rate"]<0.06) | (sig["k_rate"]>0.28)),  "luck_score"] *= 0.88
    sig["luck_score"] = sig["luck_score"].round(4)

    # Signal classification (Option 3)
    def _classify(s):
        if s >= BUY_LOW_T:    return "BUY_LOW"
        if s >= SLIGHT_BUY_T: return "SLIGHT_BUY"
        if s <= SELL_HIGH_T:  return "SELL_HIGH"
        if s <= SLIGHT_SELL_T:return "SLIGHT_SELL"
        return "NEUTRAL"
    sig["signal"] = sig["luck_score"].apply(_classify)

    # Outcomes
    may_july = outcome.groupby("batter").agg(
        out_pa=("woba_value","count"), out_woba=("woba_value","mean")
    ).reset_index()
    merged = sig.merge(may_july, on="batter", how="inner")
    merged = merged[merged["out_pa"] >= MIN_OUT_PA].copy()
    merged["woba_change"] = merged["out_woba"] - merged["april_woba"]
    merged["outcome"] = np.where(merged["woba_change"] >=  FLAT_THRESH, "IMPROVED",
                        np.where(merged["woba_change"] <= -FLAT_THRESH, "DECLINED", "FLAT"))
    merged["year"] = year
    merged["name"] = merged["batter"].map(name_lk).fillna("?")
    return merged


# ===========================================================================
# PITCHER DIAGNOSTIC
# ===========================================================================

PARK_P = PARK_H.copy()
ERA_FLAT   = 0.50
MIN_APR_IP = 15.0
MIN_OUT_IP = 30.0
LEAGUE_BABIP_P = 0.290

def _prep(sc):
    ev = sc[sc["events"].notna() & ~sc["events"].isin({"","ball","called_strike","swinging_strike"})].copy()
    return ev

def _ip(df):
    outs = int(df["events"].isin({
        "field_out","force_out","grounded_into_double_play","double_play",
        "fielders_choice_out","strikeout","strikeout_double_play","sac_fly_double_play"
    }).sum())
    return round(outs/3, 1)

def pitcher_stats_year(sc):
    ev = _prep(sc)
    if ev.empty: return pd.DataFrame()
    # BIP / BABIP
    bip_events = {"single","double","triple","field_out","force_out","grounded_into_double_play",
                  "double_play","fielders_choice","fielders_choice_out","field_error","sac_fly"}
    ev["is_bip"] = ev["events"].isin(bip_events).astype(int)
    ev["is_hit"] = ev["events"].isin({"single","double","triple"}).astype(int)
    ev["is_k"]   = ev["events"].isin({"strikeout","strikeout_double_play"}).astype(int)
    ev["is_bb"]  = ev["events"].isin({"walk","intent_walk"}).astype(int)
    ev["is_hr"]  = (ev["events"] == "home_run").astype(int)

    # runs allowed (approximate from events)
    agg = ev.groupby("pitcher").apply(lambda s: pd.Series({
        "bip":       s["is_bip"].sum(),
        "hits_bip":  s["is_hit"].sum(),
        "k":         s["is_k"].sum(),
        "bb":        s["is_bb"].sum(),
        "hr":        s["is_hr"].sum(),
        "total_bf":  len(s),
    })).reset_index()

    agg["babip"]    = np.where(agg["bip"]>0, agg["hits_bip"]/agg["bip"], np.nan)
    agg["k_pct"]    = agg["k"] / agg["total_bf"]
    agg["bb_pct"]   = agg["bb"] / agg["total_bf"]
    agg["hr_fb"]    = np.where(agg["bip"]>0, agg["hr"]/agg["bip"], np.nan)

    # IP
    ip_s = ev.groupby("pitcher").apply(_ip).rename("ip").reset_index()
    agg  = agg.merge(ip_s, on="pitcher", how="left")

    # ERA approximation: (hits+bb+hr)*const / IP
    agg["ra_approx"] = np.where(agg["ip"]>0,
        ((agg["hits_bip"] + agg["bb"] + agg["hr"]) * 9 / agg["ip"]) * 0.75, np.nan)

    # FIP
    agg["fip"] = np.where(agg["ip"]>0,
        ((agg["hr"]*13 + (agg["bb"])*3 - agg["k"]*2) / agg["ip"] + 3.10), np.nan)

    # Use player_name for name lookup
    name_map = ev.groupby("pitcher")["player_name"].first().reset_index() if "player_name" in ev.columns else None

    # Team
    if "home_team" in ev.columns and "away_team" in ev.columns and "p_throws" in ev.columns:
        def _team(g):
            row = g.iloc[0]
            return row["home_team"]   # simplistic
        team_s = ev.groupby("pitcher").apply(_team).rename("team").reset_index()
        agg = agg.merge(team_s, on="pitcher", how="left")
    else:
        agg["team"] = "UNK"

    if name_map is not None:
        agg = agg.merge(name_map, on="pitcher", how="left")

    # LOB% proxy: strand rate using (H+BB-R) / (H+BB - 1.4*HR)
    # Too complex without run data; skip LOB, use babip_luck as proxy
    return agg


def score_pitcher_year(year):
    ap_path  = CACHE / f"pitcher_statcast_april_{year}.parquet"
    out_path = CACHE / f"pitcher_statcast_mayjuly_{year}.parquet"
    if not ap_path.exists() or not out_path.exists():
        return None

    apr_sc  = pd.read_parquet(ap_path)
    out_sc  = pd.read_parquet(out_path)

    apr_st = pitcher_stats_year(apr_sc)
    out_st = pitcher_stats_year(out_sc)
    if apr_st.empty or out_st.empty:
        return None

    apr_st = apr_st[apr_st["ip"] >= MIN_APR_IP].copy()
    out_st = out_st[out_st["ip"] >= MIN_OUT_IP].copy()

    sig = apr_st.copy()
    sig["park_factor"]  = sig["team"].map(PARK_P).fillna(1.0) if "team" in sig.columns else 1.0
    sig["career_babip"] = sig["pitcher"].map(career_babip_p).fillna(LEAGUE_BABIP_P)
    sig["babip_luck"]   = sig["career_babip"] - sig["babip"]
    sig["era_fip_gap"]  = sig["ra_approx"] - sig["fip"]

    def _classify_p(gap):
        if gap >= P_BUY_LOW_T:    return "BUY_LOW"
        if gap >= P_SLIGHT_BUY_T: return "SLIGHT_BUY"
        if gap <= -P_BUY_LOW_T:   return "SELL_HIGH"
        if gap <= -P_SLIGHT_BUY_T:return "SLIGHT_SELL"
        return "NEUTRAL"
    sig["signal"] = sig["era_fip_gap"].apply(_classify_p)

    merged = sig.merge(
        out_st[["pitcher","ra_approx","fip","ip"]].rename(
            columns={"ra_approx":"out_era","fip":"out_fip","ip":"out_ip"}),
        on="pitcher", how="inner"
    )
    merged["era_change"] = merged["out_era"] - merged["ra_approx"]
    merged["outcome"] = np.where(merged["era_change"] <= -ERA_FLAT, "IMPROVED",
                        np.where(merged["era_change"] >=  ERA_FLAT, "DECLINED", "FLAT"))
    merged["year"] = year
    merged["name"] = merged.get("player_name", pd.Series(["?"]*len(merged)))
    return merged


# ===========================================================================
# MAIN ANALYSIS
# ===========================================================================
print("=" * 65)
print("TASK 1 — HITTER SLIGHT BUY DIAGNOSTIC")
print("=" * 65)

h_dfs = [score_hitter_year(y) for y in YEARS]
h_all = pd.concat([d for d in h_dfs if d is not None], ignore_index=True)
print(f"Total hitter player-seasons: {len(h_all)}")

# Full accuracy for reference
for sig_name, expected in [("SLIGHT_BUY","IMPROVED"),("BUY_LOW","IMPROVED"),("SLIGHT_SELL","DECLINED"),("SELL_HIGH","DECLINED")]:
    sub = h_all[(h_all["signal"]==sig_name) & (h_all["outcome"]!="FLAT")]
    n   = len(sub)
    c   = (sub["outcome"]==expected).sum()
    print(f"  {sig_name:12}: {c}/{n} = {c/n:.1%}" if n else f"  {sig_name}: no data")

# Slight buy misses
sb = h_all[(h_all["signal"]=="SLIGHT_BUY") & (h_all["outcome"]!="FLAT")]
sb_miss = sb[sb["outcome"]=="DECLINED"].copy()
n_miss = len(sb_miss)
print(f"\nSLIGHT_BUY misses: {n_miss}")

# Failure modes
modeA = sb_miss[sb_miss["xwoba_gap"].fillna(0) < 0.020]                              # weak xwOBA signal
modeB = sb_miss[sb_miss["age"] >= 33]                                                  # old player
modeC = sb_miss[sb_miss["april_xwoba"].fillna(0) < 0.310]                            # weak underlying hitter
modeD = sb_miss[sb_miss["gb_rate"].fillna(0) > 0.50]                                  # high GB — BABIP sticky
modeE = sb_miss[(sb_miss["k_rate"].fillna(0)>0.28)|(sb_miss["bb_rate"].fillna(0)<0.06)]  # poor discipline
modeF = sb_miss[(sb_miss["xwoba_gap"].fillna(0)<0.010)&(sb_miss["babip_luck"].fillna(0)>0.015)]  # BABIP-only

print("\nFailure modes (not mutually exclusive):")
for lbl, df in [("A: xwOBA gap < .020 (weak signal)", modeA),
                ("B: Age 33+ (age decline)", modeB),
                ("C: xwOBA < .310 (weak hitter)", modeC),
                ("D: GB rate > 50% (BABIP stickier)", modeD),
                ("E: Poor plate discipline", modeE),
                ("F: BABIP-only signal (no xwOBA support)", modeF)]:
    pct = len(df)/n_miss*100 if n_miss else 0
    print(f"  {lbl}: {len(df)} ({pct:.0f}%)")

print("\nSample misses:")
cols_h = ["year","name","april_woba","out_woba","woba_change","xwoba_gap",
          "babip","babip_baseline","babip_gap","luck_score","gb_rate","age"]
avail = [c for c in cols_h if c in sb_miss.columns]
print(sb_miss.sort_values("luck_score", ascending=False)[avail].head(15).to_string(index=False))

print("\n" + "=" * 65)
print("TASK 2 — PITCHER SLIGHT BUY DIAGNOSTIC")
print("=" * 65)

p_dfs = [score_pitcher_year(y) for y in YEARS]
p_all = pd.concat([d for d in p_dfs if d is not None], ignore_index=True)
print(f"Total pitcher player-seasons: {len(p_all)}")

for sig_name, expected in [("SLIGHT_BUY","IMPROVED"),("BUY_LOW","IMPROVED"),("SLIGHT_SELL","DECLINED"),("SELL_HIGH","DECLINED")]:
    sub = p_all[(p_all["signal"]==sig_name) & (p_all["outcome"]!="FLAT")]
    n   = len(sub)
    c   = (sub["outcome"]==expected).sum()
    print(f"  {sig_name:12}: {c}/{n} = {c/n:.1%}" if n else f"  {sig_name}: no data")

p_sb      = p_all[(p_all["signal"]=="SLIGHT_BUY") & (p_all["outcome"]!="FLAT")]
p_sb_miss = p_sb[p_sb["outcome"]=="DECLINED"].copy()
p_n_miss  = len(p_sb_miss)
print(f"\nSLIGHT_BUY pitcher misses: {p_n_miss}")

# Pitcher failure modes
p_modeA = p_sb_miss[p_sb_miss["era_fip_gap"].fillna(0) < 0.80]                            # ERA-FIP gap small
p_modeB = p_sb_miss[p_sb_miss.get("babip_luck", pd.Series([0]*len(p_sb_miss))).fillna(0) < 0.010]  # BABIP luck weak
p_modeC = p_sb_miss[p_sb_miss["fip"].fillna(5) > 4.20]                                   # high underlying FIP
p_modeD = p_sb_miss[p_sb_miss["hr_fb"].fillna(0) > 0.15]                                  # high HR/FB

print("\nPitcher failure modes:")
for lbl, df in [("A: ERA-FIP gap < 0.80 (marginal signal)", p_modeA),
                ("B: Weak BABIP luck support", p_modeB),
                ("C: Underlying FIP > 4.20 (mediocre pitcher)", p_modeC),
                ("D: High HR/FB rate (>15%)", p_modeD)]:
    pct = len(df)/p_n_miss*100 if p_n_miss else 0
    print(f"  {lbl}: {len(df)} ({pct:.0f}%)")

print("\nPitcher sample misses:")
p_cols = ["year","name","ra_approx","out_era","era_change","era_fip_gap","fip","babip","career_babip"]
p_avail = [c for c in p_cols if c in p_sb_miss.columns]
print(p_sb_miss.sort_values("era_fip_gap")[p_avail].head(15).to_string(index=False))
