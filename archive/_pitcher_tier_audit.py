"""
Multi-year per-tier pitcher backtest accuracy audit.
Mirrors the v7 pitcher scoring logic: ERA-FIP gap signal, 2 IP per-start filter,
volatility dampening. Runs 2022-2025.

Signal is classified from era_fip_gap = april_ERA - april_FIP.
  BUY_LOW   ≥ +1.20  (ERA >> FIP → unlucky → ERA should improve)
  SLIGHT_BUY ≥ +0.60
  SLIGHT_SELL ≤ -0.60 (ERA << FIP → lucky → ERA should worsen)
  SELL_HIGH  ≤ -1.20

Outcome: era_change = outcome_ERA - april_ERA
  IMPROVED  if era_change ≤ -0.40  (ERA went down)
  DECLINED  if era_change ≥ +0.40  (ERA went up)
  FLAT      otherwise
"""
import json, math, sys, os
import numpy as np
import pandas as pd
from pathlib import Path

BASE_DIR  = Path(os.path.dirname(os.path.abspath(__file__))).parent
CACHE_DIR = BASE_DIR / "backtest_cache"

P_YEARS           = [2022, 2023, 2024, 2025]
MIN_APRIL_IP      = 15.0
MIN_OUTCOME_IP    = 30.0
MIN_START_IP      = 2.0
ERA_FLAT          = 0.40
FIP_CONST         = 3.10
LEAGUE_AVG_BABIP  = 0.300
DISASTER_ERA      = 10.0
DISASTER_RATE     = 0.30
START_VAR         = 4.0
VOL_DAMP          = 0.90

P_BUY_LOW_THRESH    =  1.20
P_SLIGHT_BUY_THRESH =  0.60
P_SELL_HIGH_THRESH  = -1.20
P_SLIGHT_SELL_THRESH= -0.60

PARK_FACTORS = {
    "COL": 1.12, "CIN": 1.08, "TEX": 1.06, "HOU": 1.05,
    "BAL": 1.04, "BOS": 1.04, "PHI": 1.03, "MIL": 1.02,
    "ATL": 1.02, "NYY": 1.01, "TOR": 1.01, "WSH": 1.00,
    "CHC": 1.00, "STL": 1.00, "LAD": 0.99, "NYM": 0.99,
    "ARI": 0.99, "MIN": 0.98, "DET": 0.98, "CLE": 0.98,
    "CWS": 0.97, "SEA": 0.97, "SF":  0.96, "MIA": 0.96,
    "TB":  0.96, "PIT": 0.96, "KC":  0.96, "LAA": 0.95,
    "SD":  0.95, "OAK": 0.94,
}
SIGNAL_MAP = {
    "BUY_LOW":    "IMPROVED",
    "SLIGHT_BUY": "IMPROVED",
    "SELL_HIGH":  "DECLINED",
    "SLIGHT_SELL":"DECLINED",
}
P_OUT_EVENTS = {
    "field_out","grounded_into_double_play","double_play","force_out",
    "fielders_choice_out","fielders_choice","sac_fly","sac_bunt",
    "strikeout","strikeout_double_play",
}
P_BIP_EVENTS = {
    "single","double","triple","field_out","grounded_into_double_play",
    "force_out","double_play","fielders_choice",
}

# ── Load pitcher career baselines ─────────────────────────────────────────────
babip_path = BASE_DIR / "data" / "pitcher_career_babip.json"
if babip_path.exists():
    with open(babip_path) as f:
        raw = json.load(f)
    career_babip_p = {int(k): float(v["career_babip_allowed"])
                      for k, v in raw.items()
                      if v.get("career_babip_allowed") is not None}
    career_hh_p = {int(k): float(v["career_hard_hit_allowed"])
                   for k, v in raw.items()
                   if v.get("career_hard_hit_allowed") is not None}
    career_barrel_p = {int(k): float(v["career_barrel_allowed"])
                       for k, v in raw.items()
                       if v.get("career_barrel_allowed") is not None}
else:
    career_babip_p = {}
    career_hh_p = {}
    career_barrel_p = {}

# ── Fetch helpers ──────────────────────────────────────────────────────────────
NEEDED_COLS = [
    "pitcher", "batter", "events", "post_bat_score", "bat_score",
    "game_pk", "player_name", "home_team", "away_team", "inning_topbot",
]

def _fetch_statcast(start_dt: str, end_dt: str, label: str) -> pd.DataFrame:
    """Fetch statcast data from pybaseball; result always has NEEDED_COLS."""
    import pybaseball as pb
    pb.cache.enable()
    print(f"  Fetching {label} ({start_dt} to {end_dt})...", flush=True)
    try:
        df = pb.statcast(start_dt=start_dt, end_dt=end_dt)
        if df is None or df.empty:
            print(f"  WARNING: empty result for {label}")
            return pd.DataFrame(columns=NEEDED_COLS)
        present = [c for c in NEEDED_COLS if c in df.columns]
        return df[present].copy()
    except Exception as ex:
        print(f"  ERROR fetching {label}: {ex}")
        return pd.DataFrame(columns=NEEDED_COLS)


def load_or_fetch(cache_path: Path, start_dt: str, end_dt: str, label: str) -> pd.DataFrame:
    if cache_path.exists():
        print(f"  Loading cached {label}: {cache_path.name}")
        df = pd.read_parquet(cache_path)
        present = [c for c in NEEDED_COLS if c in df.columns]
        return df[present].copy()
    df = _fetch_statcast(start_dt, end_dt, label)
    if not df.empty:
        df.to_parquet(cache_path, index=False)
        print(f"  Cached: {cache_path.name}")
    return df


# ── Core stat computation ──────────────────────────────────────────────────────
def _prep(sc: pd.DataFrame) -> pd.DataFrame:
    sc = sc.copy()
    sc["pitcher"] = pd.to_numeric(sc.get("pitcher"), errors="coerce")
    sc = sc[sc["pitcher"].notna()].copy()
    sc["pitcher"] = sc["pitcher"].astype(int)
    ev_mask = sc["events"].notna() & (sc["events"] != "")
    sc["is_out"] = (sc["events"].isin(P_OUT_EVENTS) & ev_mask).astype(int)
    sc["is_dp"]  = (sc["events"].isin({"grounded_into_double_play","double_play",
                                        "strikeout_double_play"}) & ev_mask).astype(int)
    return sc


def per_start_stats(sc: pd.DataFrame) -> pd.DataFrame:
    if "game_pk" not in sc.columns:
        return pd.DataFrame(columns=["pitcher","game_pk","start_ip","start_ra",
                                     "start_era","qualifying","is_qs","is_disaster"])
    sc  = _prep(sc)
    ev  = sc[sc["events"].notna() & (sc["events"] != "")].copy()
    outs = ev.groupby(["pitcher","game_pk"]).agg(
        outs=("is_out","sum"), dp_outs=("is_dp","sum")).reset_index()
    outs["start_ip"] = (outs["outs"] + outs["dp_outs"]) / 3.0

    if "post_bat_score" in ev.columns and "bat_score" in ev.columns:
        re = ev[ev["post_bat_score"].notna() & ev["bat_score"].notna()].copy()
        re["runs"] = (re["post_bat_score"] - re["bat_score"]).clip(lower=0)
        runs = re.groupby(["pitcher","game_pk"])["runs"].sum().reset_index()
        runs.rename(columns={"runs":"start_ra"}, inplace=True)
    else:
        runs = outs[["pitcher","game_pk"]].copy(); runs["start_ra"] = 0.0

    starts = outs.merge(runs, on=["pitcher","game_pk"], how="left")
    starts["start_ra"] = starts["start_ra"].fillna(0.0)
    starts["start_era"] = np.where(
        starts["start_ip"] > 0,
        (starts["start_ra"] / starts["start_ip"]) * 9, np.nan).round(2)
    starts["qualifying"]  = starts["start_ip"] >= MIN_START_IP
    starts["is_qs"]       = (starts["start_ip"] >= 6.0) & (starts["start_ra"] <= 3)
    starts["is_disaster"] = (starts["start_era"] > DISASTER_ERA) & starts["qualifying"]
    return starts[["pitcher","game_pk","start_ip","start_ra",
                   "start_era","qualifying","is_qs","is_disaster"]]


def pitcher_stats(sc: pd.DataFrame, start_stats: pd.DataFrame) -> pd.DataFrame:
    """ERA / FIP / BABIP with 2 IP per-start filter; fallback to all-appearances."""
    sc = _prep(sc)
    ev = sc[sc["events"].notna() & (sc["events"] != "")].copy()

    # Qualifying-start subset
    qual_pairs = pd.DataFrame()
    if "game_pk" in start_stats.columns and not start_stats.empty:
        qual_pairs = start_stats[start_stats["qualifying"]][["pitcher","game_pk"]].assign(_q=True)
        if "game_pk" in sc.columns:
            sc_mq   = sc.merge(qual_pairs, on=["pitcher","game_pk"], how="left")
            sc_qual = sc[sc_mq["_q"].fillna(False).values].copy()
        else:
            sc_qual = sc.copy()
        ev_qual = sc_qual[sc_qual["events"].notna() & (sc_qual["events"] != "")].copy()
    else:
        sc_qual = sc.copy()
        ev_qual = ev.copy()

    def _ip(df):
        a = df.groupby("pitcher").agg(
            outs=("is_out","sum"), dp=("is_dp","sum")).reset_index()
        a["ip"] = (a["outs"] + a["dp"]) / 3.0
        return a.set_index("pitcher")["ip"]

    ip_qual = _ip(ev_qual)
    ip_all  = _ip(ev)

    # ERA from qualifying starts
    if "post_bat_score" in ev_qual.columns and "bat_score" in ev_qual.columns:
        re = ev_qual[ev_qual["post_bat_score"].notna() & ev_qual["bat_score"].notna()].copy()
        re["runs"] = (re["post_bat_score"] - re["bat_score"]).clip(lower=0)
        ra_qual = re.groupby("pitcher")["runs"].sum()
    else:
        ra_qual = pd.Series(dtype=float)
    era_qual = (ra_qual / (ip_qual / 9)).where(ip_qual > 0).round(2)

    # ERA from all appearances (fallback / reliever)
    if "post_bat_score" in ev.columns and "bat_score" in ev.columns:
        re2 = ev[ev["post_bat_score"].notna() & ev["bat_score"].notna()].copy()
        re2["runs"] = (re2["post_bat_score"] - re2["bat_score"]).clip(lower=0)
        ra_all = re2.groupby("pitcher")["runs"].sum()
        era_all = (ra_all / (ip_all / 9)).where(ip_all > 0).round(2)
    else:
        era_all = pd.Series(dtype=float)
    era_final = era_qual.combine_first(era_all)

    # FIP from qualifying starts
    ev_qual["is_k"]  = ev_qual["events"].isin({"strikeout","strikeout_double_play"}).astype(int)
    ev_qual["is_bb"] = ev_qual["events"].isin({"walk","intent_walk"}).astype(int)
    ev_qual["is_hr"] = (ev_qual["events"] == "home_run").astype(int)
    fip_agg = ev_qual.groupby("pitcher").agg(k=("is_k","sum"),bb=("is_bb","sum"),hr=("is_hr","sum"))
    fip_series = ((13*fip_agg["hr"] + 3*fip_agg["bb"] - 2*fip_agg["k"]) / ip_qual + FIP_CONST
                  ).where(ip_qual > 0).round(2)

    # BABIP from qualifying starts; fallback all
    ev_qual["is_bip"] = ev_qual["events"].isin(P_BIP_EVENTS).astype(int)
    ev_qual["is_hit"] = ev_qual["events"].isin({"single","double","triple"}).astype(int)
    b_agg = ev_qual.groupby("pitcher").agg(bip=("is_bip","sum"),hits=("is_hit","sum"))
    babip_qual = (b_agg["hits"] / b_agg["bip"]).where(b_agg["bip"] > 0).round(3)

    ev["is_bip"] = ev["events"].isin(P_BIP_EVENTS).astype(int)
    ev["is_hit"] = ev["events"].isin({"single","double","triple"}).astype(int)
    b_all = ev.groupby("pitcher").agg(bip=("is_bip","sum"),hits=("is_hit","sum"))
    babip_all  = (b_all["hits"] / b_all["bip"]).where(b_all["bip"] > 0).round(3)
    babip_final= babip_qual.combine_first(babip_all)

    # Team (mode)
    team_s = pd.Series(dtype=str, name="team")
    if {"home_team","away_team","inning_topbot"}.issubset(sc.columns):
        sc["p_team"] = sc.apply(
            lambda r: r["away_team"] if r["inning_topbot"]=="Top" else r["home_team"], axis=1)
        team_s = sc.groupby("pitcher")["p_team"].agg(lambda x: x.mode().iloc[0])

    name_s = pd.Series(dtype=str, name="name")
    if "player_name" in sc.columns:
        name_s = sc.groupby("pitcher")["player_name"].first()

    agg = pd.DataFrame({"ip": ip_all, "era": era_final, "fip": fip_series, "babip": babip_final})
    return agg.join(team_s, how="left").join(name_s, how="left").reset_index().rename(columns={"index":"pitcher"})


def compute_volatility(start_stats: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for pid, grp in start_stats.groupby("pitcher"):
        total = len(grp)
        d_n   = int(grp["is_disaster"].sum())
        d_rate= d_n / total if total > 0 else 0.0
        quals = grp.loc[grp["qualifying"],"start_era"].dropna()
        svar  = float(quals.std()) if len(quals) >= 2 else float("nan")
        flagged = d_rate > DISASTER_RATE or (not math.isnan(svar) and svar > START_VAR)
        rows.append({"pitcher": int(pid), "volatility_flag": flagged})
    return pd.DataFrame(rows)


def classify_p(gap: float) -> str:
    if gap >= P_BUY_LOW_THRESH:     return "BUY_LOW"
    if gap >= P_SLIGHT_BUY_THRESH:  return "SLIGHT_BUY"
    if gap <= P_SELL_HIGH_THRESH:   return "SELL_HIGH"
    if gap <= P_SLIGHT_SELL_THRESH: return "SLIGHT_SELL"
    return "NEUTRAL"


# ── Per-year run ──────────────────────────────────────────────────────────────
_TIER_DISPLAY = {
    "BUY_LOW":    "Buy low",
    "SLIGHT_BUY": "Slight buy",
    "SLIGHT_SELL":"Slight sell",
    "SELL_HIGH":  "Sell high",
}


def run_pitcher_audit(year: int):
    """
    Runs the full per-year pitcher backtest pipeline for one year.
    Returns (result_dict, merged_df), or (None, None) if data is missing.

    result_dict structure:
      {
        "year": int,
        "Buy low":    {"n", "correct", "accuracy", "era_delta"},
        "Slight buy": {"n", "correct", "accuracy", "era_delta"},
        "Slight sell":{"n", "correct", "accuracy", "era_delta"},
        "Sell high":  {"n", "correct", "accuracy", "era_delta"},
        "Overall":    {"n", "correct", "accuracy"},
        "do_nothing_accuracy": float   # IMPROVED rate among all non-flat pitchers
      }
    """
    print(f"\n{'='*60}")
    print(f"Year {year}")
    print(f"{'='*60}")

    # April data
    if year == 2024:
        apr_cache = CACHE_DIR / "pitcher_statcast_april_2024.parquet"
        out_cache = CACHE_DIR / "pitcher_statcast_mayjuly_2024.parquet"
    else:
        apr_cache = CACHE_DIR / f"pitcher_statcast_april_{year}.parquet"
        out_cache = CACHE_DIR / f"pitcher_statcast_mayjuly_{year}.parquet"

    apr_sc = load_or_fetch(apr_cache, f"{year}-04-01", f"{year}-04-30", f"April {year}")
    out_sc = load_or_fetch(out_cache, f"{year}-05-01", f"{year}-07-31", f"May-Jul {year}")

    if apr_sc.empty or out_sc.empty:
        print(f"  {year}: missing data -- skip")
        return None, None

    # Per-start stats (for 2 IP filter + volatility)
    print(f"  Computing per-start stats...", flush=True)
    apr_starts = per_start_stats(apr_sc)
    out_starts = per_start_stats(out_sc)

    # Season-level stats
    print(f"  Computing pitcher stats...", flush=True)
    apr_stats = pitcher_stats(apr_sc, apr_starts)
    out_stats = pitcher_stats(out_sc, out_starts)

    # IP filters
    apr_stats = apr_stats[apr_stats["ip"] >= MIN_APRIL_IP].copy()
    out_stats = out_stats[out_stats["ip"] >= MIN_OUTCOME_IP].copy()
    print(f"  April qualifiers: {len(apr_stats)}, May-Jul qualifiers: {len(out_stats)}")

    # Signal computation
    sig = apr_stats.copy()
    sig["park_factor"]    = sig["team"].map(PARK_FACTORS).fillna(1.0) if "team" in sig.columns else 1.0
    sig["career_babip"]   = sig["pitcher"].map(career_babip_p).fillna(LEAGUE_AVG_BABIP)
    sig["babip_expected"] = sig["career_babip"] * sig["park_factor"]
    sig["babip_luck"]     = sig["babip_expected"] - sig["babip"]
    sig["era_fip_gap"]    = sig["era"] - sig["fip"]
    sig["luck_score_raw"] = (sig["era_fip_gap"] * 0.70 + sig["babip_luck"] * 0.30 * 9).round(3)
    sig["luck_score"]     = sig["luck_score_raw"]

    # CHANGE 3: career HH and barrel columns (available for cohort splits; not used in scoring)
    sig["career_hh_allowed"]     = sig["pitcher"].map(career_hh_p)
    sig["career_barrel_allowed"] = sig["pitcher"].map(career_barrel_p)

    # Volatility dampening on buy signals
    if not apr_starts.empty:
        vol_df = compute_volatility(apr_starts)
        sig = sig.merge(vol_df[["pitcher","volatility_flag"]], on="pitcher", how="left")
        sig["volatility_flag"] = sig["volatility_flag"].fillna(False)
        buy_vol = sig["volatility_flag"] & (sig["luck_score"] > 0)
        sig.loc[buy_vol, "luck_score"] = (sig.loc[buy_vol, "luck_score"] * VOL_DAMP).round(3)
    else:
        sig["volatility_flag"] = False

    # Signal classified from era_fip_gap (v7 convention — not luck_score)
    sig["signal"] = sig["era_fip_gap"].apply(classify_p)

    # Outcomes
    merged = sig.merge(
        out_stats[["pitcher","era","ip"]].rename(columns={"era":"outcome_era","ip":"outcome_ip"}),
        on="pitcher", how="inner"
    )
    merged["era_change"] = merged["outcome_era"] - merged["era"]
    merged["outcome"] = np.where(
        merged["era_change"] <= -ERA_FLAT, "IMPROVED",
        np.where(merged["era_change"] >= ERA_FLAT, "DECLINED", "FLAT")
    )
    merged["year"] = year
    print(f"  Eval set: {len(merged)} pitchers, outcomes: "
          f"IMPROVED={int((merged['outcome']=='IMPROVED').sum())} "
          f"DECLINED={int((merged['outcome']=='DECLINED').sum())} "
          f"FLAT={int((merged['outcome']=='FLAT').sum())}")

    # ── Build structured result dict ──────────────────────────────────────────
    result = {"year": year}

    for sig_name, display in _TIER_DISPLAY.items():
        sub_all = merged[merged["signal"] == sig_name]
        sub     = sub_all[sub_all["outcome"] != "FLAT"].copy()
        n_eval  = len(sub)
        if n_eval == 0:
            result[display] = {"n": 0, "correct": 0, "accuracy": float("nan"),
                               "era_delta": sub_all["era_change"].mean() if len(sub_all) > 0 else float("nan")}
            continue
        sub["correct"] = (sub["outcome"] == SIGNAL_MAP[sig_name])
        n_corr = int(sub["correct"].sum())
        result[display] = {
            "n":        n_eval,
            "correct":  n_corr,
            "accuracy": n_corr / n_eval,
            "era_delta": sub_all["era_change"].mean(),
        }

    ov_sub = merged[merged["signal"].isin(SIGNAL_MAP) & (merged["outcome"] != "FLAT")].copy()
    ov_sub["correct"] = ov_sub.apply(lambda r: r["outcome"] == SIGNAL_MAP[r["signal"]], axis=1)
    ov_n = len(ov_sub)
    ov_c = int(ov_sub["correct"].sum()) if ov_n > 0 else 0
    result["Overall"] = {"n": ov_n, "correct": ov_c,
                         "accuracy": ov_c / ov_n if ov_n > 0 else float("nan")}

    non_flat = merged[merged["outcome"] != "FLAT"]
    n_imp    = int((non_flat["outcome"] == "IMPROVED").sum())
    n_nf     = len(non_flat)
    result["do_nothing_accuracy"] = n_imp / n_nf if n_nf > 0 else float("nan")

    return result, merged


if __name__ == "__main__":
    all_rows      = []
    audit_results = []

    for year in P_YEARS:
        res, merged = run_pitcher_audit(year)
        if res is not None:
            audit_results.append(res)
            all_rows.append(merged)

    if not all_rows:
        print("No data -- exiting"); sys.exit(1)

    data = pd.concat(all_rows, ignore_index=True)

    # ── Build output rows ─────────────────────────────────────────────────────
    TIER_PRINT = ["BUY_LOW", "SLIGHT_BUY", "NEUTRAL", "SLIGHT_SELL", "SELL_HIGH", "OVERALL"]
    YEARS      = sorted(data["year"].unique())

    rows = []
    for year in YEARS:
        yr = data[data["year"] == year]
        for tier in TIER_PRINT + ["NEUTRAL"] if "NEUTRAL" not in TIER_PRINT else TIER_PRINT:
            if tier == "OVERALL":
                sub_all = yr[yr["signal"].isin(SIGNAL_MAP)]
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
                    sub["correct"] = sub.apply(lambda r: r["outcome"] == SIGNAL_MAP.get(r["signal"]), axis=1)
                else:
                    expected = SIGNAL_MAP.get(tier)
                    sub["correct"] = (sub["outcome"] == expected) if expected else False
                n_eval = len(sub)
                n_corr = int(sub["correct"].sum()) if n_eval > 0 else 0
                acc    = n_corr / n_eval if n_eval > 0 else float("nan")

            avg_era = sub_all["era_change"].mean() if n_total > 0 else float("nan")
            rows.append({
                "year": year, "tier": tier,
                "n_total": n_total, "n_flat": n_flat,
                "n_improved": n_imp, "n_declined": n_dec,
                "n_eval": n_eval, "n_correct": n_corr,
                "accuracy": acc, "avg_era_chg": avg_era,
            })

    df = pd.DataFrame(rows)


    # ── Print table ───────────────────────────────────────────────────────────
    TIER_LABEL = {
        "BUY_LOW":    "BUY LOW    ",
        "SLIGHT_BUY": "SLIGHT BUY ",
        "NEUTRAL":    "NEUTRAL    ",
        "SLIGHT_SELL":"SLIGHT SELL",
        "SELL_HIGH":  "SELL HIGH  ",
        "OVERALL":    "OVERALL    ",
    }

    print("\n")
    print("=" * 80)
    print("PITCHER BACKTEST - PER-YEAR, PER-TIER ACCURACY  (v7 ERA-FIP signal, 2 IP filter)")
    print("=" * 80)

    hdr = f"{'Tier':<13}"
    for y in YEARS:
        hdr += f"   {y}"
    print(hdr)
    print("=" * (13 + len(YEARS) * 25))

    for tier in TIER_PRINT:
        print(f"\n{TIER_LABEL[tier]}")
        sub = df[df["tier"] == tier]
        ntot_line = "  n(eval)  :"
        nacc_line = "  accuracy :"
        nchg_line = "  avg ERA d :"
        for y in YEARS:
            row = sub[sub["year"] == y]
            if row.empty:
                ntot_line += "      —       "
                nacc_line += "      —       "
                nchg_line += "      —       "
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
            chg_s = f"{r['avg_era_chg']:+.2f}" if not (isinstance(r['avg_era_chg'], float) and math.isnan(r['avg_era_chg'])) else "—"
            nchg_line += f"  {chg_s:<10}"
        print(ntot_line)
        if tier != "NEUTRAL":
            print(nacc_line)
        print(nchg_line)

    # ── 4-year rollup ─────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print(f"{len(YEARS)}-YEAR COMBINED ({min(YEARS)}-{max(YEARS)})")
    print("=" * 60)
    for tier in TIER_PRINT:
        sub    = df[df["tier"] == tier]
        n_tot  = int(sub["n_total"].sum())
        n_ev   = int(sub["n_eval"].sum())
        n_corr = int(sub["n_correct"].sum())
        acc    = n_corr / n_ev if n_ev > 0 else float("nan")
        avg_chg= (sub["avg_era_chg"] * sub["n_total"]).sum() / n_tot if n_tot > 0 else float("nan")
        if tier == "NEUTRAL":
            print(f"  {TIER_LABEL[tier]}  n={n_tot:3d}  (no directional)  avg_ERA_chg={avg_chg:+.2f}")
        else:
            acc_s = f"{acc:.1%}" if n_ev > 0 else "n/a"
            print(f"  {TIER_LABEL[tier]}  n={n_ev:3d}  acc={acc_s:<7}  avg_ERA_chg={avg_chg:+.2f}")
