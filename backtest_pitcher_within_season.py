"""
Pitcher Within-Season Backtest — April 2024 signals -> May-July 2024 ERA outcomes.

Signal: ERA-FIP gap (primary luck indicator) + BABIP luck + LOB% luck.
Outcome: Did ERA improve (move toward FIP / xERA) May-July 2024?
Modifier: Stuff+ tier from data/pitcher_stuff_plus_2025.csv (proxy).

Minimums: 15 IP April, 30 IP May-July.
Baseline: 68.2% RTM baseline.
"""

import io
import json
import os
import sys
import numpy as np
import pandas as pd
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE_DIR       = Path(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR      = BASE_DIR / "backtest_cache"
DATA_DIR       = BASE_DIR / "data"
STUFF_PATH     = DATA_DIR / "pitcher_stuff_plus_2025.csv"
CAREER_PATH    = DATA_DIR / "career_stats.json"
PITCHER_BABIP  = DATA_DIR / "pitcher_career_babip.json"

CACHE_DIR.mkdir(exist_ok=True)

APRIL_CACHE   = CACHE_DIR / "pitcher_statcast_april_2024.parquet"
OUTCOME_CACHE = CACHE_DIR / "pitcher_statcast_mayjuly_2024.parquet"

MIN_APRIL_IP    = 15.0
MIN_OUTCOME_IP  = 30.0
RTM_BASELINE    = 0.682
LEAGUE_AVG_ERA  = 4.20
LEAGUE_AVG_BABIP = 0.300

# Signal thresholds (ERA-FIP gap in runs/9)
BUY_LOW_THRESH    =  1.20   # ERA > FIP by 1.20+ (unlucky)
SLIGHT_BUY_THRESH =  0.60   # ERA > FIP by 0.60-1.20
SELL_HIGH_THRESH  = -1.20   # ERA < FIP by 1.20+ (lucky, overperforming)
SLIGHT_SELL_THRESH = -0.60  # ERA < FIP by 0.60-1.20

SIGNAL_MAP = {
    "BUY_LOW":    "IMPROVED",
    "SLIGHT_BUY": "IMPROVED",
    "SELL_HIGH":  "DECLINED",
    "SLIGHT_SELL":"DECLINED",
}

PARK_FACTORS = {
    "COL":1.12,"CIN":1.08,"TEX":1.06,"HOU":1.05,"BAL":1.04,"BOS":1.04,
    "PHI":1.03,"MIL":1.02,"ATL":1.02,"NYY":1.01,"TOR":1.01,"WSH":1.00,
    "CHC":1.00,"STL":1.00,"LAD":0.99,"NYM":0.99,"ARI":0.99,"MIN":0.98,
    "DET":0.98,"CLE":0.98,"CWS":0.97,"SEA":0.97,"SF":0.96,"MIA":0.96,
    "TB":0.96,"PIT":0.96,"KC":0.96,"LAA":0.95,"SD":0.95,"OAK":0.94,
}

BIP_EVENTS = {
    "single","double","triple","field_out","grounded_into_double_play",
    "force_out","double_play","fielders_choice",
}


# ------------------------------------------------------------------
# DATA FETCHING
# ------------------------------------------------------------------

def fetch_statcast_range(start: str, end: str, label: str) -> pd.DataFrame:
    """Fetch statcast in weekly chunks and return combined DataFrame."""
    import pybaseball as pb
    pb.cache.enable()
    dates = pd.date_range(start, end, freq="W-SUN")
    starts = [start] + [str(d.date()) for d in dates[:-1]]
    ends   = [str(d.date()) for d in dates] + [end]
    pairs  = list(dict.fromkeys(zip(starts, ends)))

    frames = []
    for i, (s, e) in enumerate(pairs):
        print(f"  [{label}] chunk {i+1}/{len(pairs)}: {s} -> {e}", flush=True)
        try:
            chunk = pb.statcast(start_dt=s, end_dt=e)
            if chunk is not None and not chunk.empty:
                frames.append(chunk)
        except Exception as ex:
            print(f"    WARNING: {ex}")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def load_or_fetch(cache_path: Path, start: str, end: str, label: str) -> pd.DataFrame:
    if cache_path.exists():
        print(f"  Loading {label} from cache: {cache_path.name}")
        return pd.read_parquet(cache_path)
    print(f"  Fetching {label} from Baseball Savant...")
    df = fetch_statcast_range(start, end, label)
    if not df.empty:
        df.to_parquet(cache_path, index=False)
        print(f"  Cached to {cache_path.name} ({len(df):,} rows)")
    return df


# ------------------------------------------------------------------
# STAT COMPUTATION FROM STATCAST
# ------------------------------------------------------------------

def compute_pitcher_stats(sc: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate statcast pitch-level data to pitcher-level season stats.
    Returns one row per pitcher with ERA, FIP components, BABIP, xERA proxy.
    """
    sc = sc.copy()
    sc["pitcher"] = pd.to_numeric(sc["pitcher"], errors="coerce")
    sc = sc[sc["pitcher"].notna()].copy()
    sc["pitcher"] = sc["pitcher"].astype(int)

    # IP calculation: each out = 1/3 IP
    # Outs from events
    out_events = {
        "field_out","grounded_into_double_play","double_play","force_out",
        "fielders_choice_out","fielders_choice","sac_fly","sac_bunt",
        "strikeout","strikeout_double_play",
    }
    sc["is_out"]    = sc["events"].isin(out_events).astype(int)
    sc["is_dp"]     = sc["events"].isin({"grounded_into_double_play","double_play","strikeout_double_play"}).astype(int)
    sc["is_k"]      = sc["events"].isin({"strikeout","strikeout_double_play"}).astype(int)
    sc["is_bb"]     = sc["events"].isin({"walk","intent_walk"}).astype(int)
    sc["is_hr"]     = (sc["events"] == "home_run").astype(int)
    sc["is_single"] = (sc["events"] == "single").astype(int)
    sc["is_hit"]    = sc["events"].isin({"single","double","triple","home_run"}).astype(int)
    sc["is_bip"]    = sc["events"].isin(BIP_EVENTS | {"home_run"}).astype(int)
    sc["is_bip_no_hr"] = sc["events"].isin(BIP_EVENTS).astype(int)
    sc["is_hit_no_hr"] = sc["events"].isin({"single","double","triple"}).astype(int)
    sc["is_run"]    = sc["post_bat_score"].notna() & sc["bat_score"].notna()

    # PA-level: only rows with an event
    ev = sc[sc["events"].notna() & (sc["events"] != "")].copy()

    agg = ev.groupby("pitcher").agg(
        outs=("is_out", "sum"),
        dp_outs=("is_dp", "sum"),  # double plays add extra outs
        k=("is_k", "sum"),
        bb=("is_bb", "sum"),
        hr=("is_hr", "sum"),
        hits=("is_hit", "sum"),
        bip=("is_bip_no_hr", "sum"),
        hits_no_hr=("is_hit_no_hr", "sum"),
        pa=("is_out", "count"),
    ).reset_index()

    # Runs allowed — use run expectancy delta (crude)
    # Simpler: count runs scored (home_score + away_score changes)
    # Even simpler: use RA = PA - K - BB - (H-HR) estimate, or just infer from wOBA
    # Best available: sum of runs from post_bat_score - bat_score
    run_ev = sc[sc["events"].notna() & sc["post_bat_score"].notna() & sc["bat_score"].notna()].copy()
    run_ev["runs_scored"] = (run_ev["post_bat_score"] - run_ev["bat_score"]).clip(lower=0)
    runs_agg = run_ev.groupby("pitcher")["runs_scored"].sum().reset_index()
    runs_agg.columns = ["pitcher", "runs_allowed"]

    agg = agg.merge(runs_agg, on="pitcher", how="left")
    agg["runs_allowed"] = agg["runs_allowed"].fillna(0)

    # IP (outs + DP bonus outs)
    agg["ip"] = (agg["outs"] + agg["dp_outs"]) / 3.0

    # ERA (RA9 proxy — using runs scored against)
    agg["era"] = np.where(
        agg["ip"] >= 0.1,
        (agg["runs_allowed"] / agg["ip"]) * 9,
        np.nan
    )

    # FIP = (13*HR + 3*BB - 2*K) / IP + FIP_constant (use 3.10 for 2024 MLB)
    FIP_CONST = 3.10
    agg["fip"] = np.where(
        agg["ip"] >= 0.1,
        (13 * agg["hr"] + 3 * agg["bb"] - 2 * agg["k"]) / agg["ip"] + FIP_CONST,
        np.nan
    )

    # BABIP = (H - HR) / (BIP)
    agg["babip"] = np.where(
        agg["bip"] > 0,
        agg["hits_no_hr"] / agg["bip"],
        np.nan
    )

    # xwOBA from statcast (mean of estimated_woba_using_speedangle for BIP pitches)
    bbe = sc[sc["launch_speed"].notna()].copy()
    if "estimated_woba_using_speedangle" in bbe.columns and not bbe.empty:
        xwoba_agg = bbe.groupby("pitcher")["estimated_woba_using_speedangle"].mean().reset_index()
        xwoba_agg.columns = ["pitcher", "xwoba_allowed"]
        agg = agg.merge(xwoba_agg, on="pitcher", how="left")
    else:
        agg["xwoba_allowed"] = np.nan

    # wOBA allowed
    woba_ev = ev[ev["woba_value"].notna()].groupby("pitcher")["woba_value"].mean().reset_index()
    woba_ev.columns = ["pitcher", "woba_allowed"]
    agg = agg.merge(woba_ev, on="pitcher", how="left")

    # xERA proxy: use xwOBA * 9 scaling (rough)
    # Better: xERA ≈ (xwoba_allowed / 0.320) * league_avg_ERA
    agg["xera"] = np.where(
        agg["xwoba_allowed"].notna(),
        (agg["xwoba_allowed"] / 0.320) * LEAGUE_AVG_ERA,
        np.nan
    )

    # Team (most common team for each pitcher)
    if "home_team" in sc.columns and "away_team" in sc.columns and "inning_topbot" in sc.columns:
        sc["pitcher_team"] = sc.apply(
            lambda r: r["away_team"] if r["inning_topbot"] == "Top" else r["home_team"],
            axis=1
        )
        team_agg = sc.groupby("pitcher")["pitcher_team"].agg(
            lambda x: x.mode().iloc[0] if len(x) > 0 else "UNK"
        ).reset_index()
        team_agg.columns = ["pitcher", "team"]
        agg = agg.merge(team_agg, on="pitcher", how="left")
    else:
        agg["team"] = "UNK"

    # Player name
    if "player_name" in sc.columns:
        name_agg = sc.groupby("pitcher")["player_name"].first().reset_index()
        name_agg.columns = ["pitcher", "name"]
        agg = agg.merge(name_agg, on="pitcher", how="left")
    else:
        agg["name"] = agg["pitcher"].astype(str)

    return agg


# ------------------------------------------------------------------
# LUCK SCORE
# ------------------------------------------------------------------

def classify_signal(era_fip_gap: float) -> str:
    """ERA - FIP gap: positive = pitcher unlucky (ERA > FIP), buy low."""
    if era_fip_gap >= BUY_LOW_THRESH:     return "BUY_LOW"
    if era_fip_gap >= SLIGHT_BUY_THRESH:  return "SLIGHT_BUY"
    if era_fip_gap <= SELL_HIGH_THRESH:   return "SELL_HIGH"
    if era_fip_gap <= SLIGHT_SELL_THRESH: return "SLIGHT_SELL"
    return "NEUTRAL"


def load_stuff_plus() -> dict:
    """Returns {pitcher_id (int): stuff_plus_avg}."""
    if not STUFF_PATH.exists():
        return {}
    df = pd.read_csv(STUFF_PATH)
    col = "stuff_plus_avg" if "stuff_plus_avg" in df.columns else df.columns[2]
    id_col = "pitcher_id" if "pitcher_id" in df.columns else df.columns[0]
    return dict(zip(df[id_col].astype(int), df[col].astype(float)))


def load_career_babip_pitchers() -> dict:
    """Returns {pitcher_id (int): career_babip_allowed}."""
    if not PITCHER_BABIP.exists():
        return {}
    with open(PITCHER_BABIP) as f:
        raw = json.load(f)
    return {
        int(k): float(v["career_babip_allowed"])
        for k, v in raw.items()
        if v.get("career_babip_allowed") is not None
    }


# ------------------------------------------------------------------
# MAIN BACKTEST
# ------------------------------------------------------------------

def main():
    print("Pitcher Within-Season Backtest — April 2024 -> May-July 2024")
    print("=" * 68)

    # ── Fetch / load statcast ──────────────────────────────────────────
    print("\nLoading April 2024 pitcher data...")
    april_sc = load_or_fetch(APRIL_CACHE, "2024-04-01", "2024-04-30", "April 2024")

    print("\nLoading May-July 2024 pitcher data...")
    outcome_sc = load_or_fetch(OUTCOME_CACHE, "2024-05-01", "2024-07-31", "May-July 2024")

    if april_sc.empty or outcome_sc.empty:
        print("ERROR: Could not load statcast data.")
        return

    print(f"\nApril:    {len(april_sc):,} pitch events | May-Jul: {len(outcome_sc):,} pitch events")

    # ── Compute pitcher stats ─────────────────────────────────────────
    print("\nComputing April pitcher stats...")
    apr_stats = compute_pitcher_stats(april_sc)
    apr_stats = apr_stats[apr_stats["ip"] >= MIN_APRIL_IP].copy()
    print(f"  {len(apr_stats)} pitchers with >= {MIN_APRIL_IP} IP in April")

    print("Computing May-July pitcher stats...")
    out_stats = compute_pitcher_stats(outcome_sc)
    out_stats = out_stats[out_stats["ip"] >= MIN_OUTCOME_IP].copy()
    print(f"  {len(out_stats)} pitchers with >= {MIN_OUTCOME_IP} IP in May-July")

    # ── Load modifiers ────────────────────────────────────────────────
    stuff_plus    = load_stuff_plus()
    career_babip  = load_career_babip_pitchers()
    print(f"  Stuff+ data: {len(stuff_plus)} pitchers")
    print(f"  Career BABIP data: {len(career_babip)} pitchers")

    # ── Signal computation ────────────────────────────────────────────
    sig = apr_stats.copy()
    sig["park_factor"] = sig["team"].map(PARK_FACTORS).fillna(1.0)

    # Career BABIP baseline (or league avg)
    sig["career_babip_allowed"] = sig["pitcher"].map(career_babip).fillna(LEAGUE_AVG_BABIP)
    sig["babip_expected"] = sig["career_babip_allowed"] * sig["park_factor"]
    sig["babip_luck"] = sig["babip_expected"] - sig["babip"]  # positive = unlucky (BABIP > expected)

    # ERA-FIP gap (primary signal)
    sig["era_fip_gap"] = sig["era"] - sig["fip"]  # positive = ERA > FIP = unlucky

    # Stuff+ modifier: elite stuff (>115) amplifies buy signals; poor stuff (<90) dampens
    sig["stuff_plus"] = sig["pitcher"].map(stuff_plus)
    n_stuff = sig["stuff_plus"].notna().sum()

    # Composite luck score (weighted)
    # 0.70 ERA-FIP gap (normalized to wOBA scale / 9) + 0.30 BABIP luck
    sig["luck_score_raw"] = (
        sig["era_fip_gap"] * 0.70 +   # ERA-FIP already in runs/9 scale
        sig["babip_luck"]  * 0.30 * 9  # BABIP luck scaled to runs/9
    ).round(3)

    # Stuff+ adjustment: amplify buy signal for elite stuff, dampen for poor
    def apply_stuff(row):
        score = row["luck_score_raw"]
        sp    = row["stuff_plus"]
        if pd.isna(sp) or score <= 0:
            return score
        if sp >= 115:
            return round(score * 1.15, 3)  # elite — buy signal more credible
        if sp < 90:
            return round(score * 0.80, 3)  # poor stuff — dampen buy
        return score

    sig["luck_score"] = sig.apply(apply_stuff, axis=1)
    sig["signal"]     = sig["era_fip_gap"].apply(classify_signal)

    print(f"\n  Stuff+ modifier applied to {n_stuff} pitchers")
    sig_counts = sig["signal"].value_counts()
    print(f"  Signal distribution: {dict(sig_counts)}")

    # ── Outcomes ──────────────────────────────────────────────────────
    merged = sig.merge(
        out_stats[["pitcher","era","fip","babip","ip"]].rename(columns={
            "era":  "outcome_era",
            "fip":  "outcome_fip",
            "babip":"outcome_babip",
            "ip":   "outcome_ip",
        }),
        on="pitcher", how="inner"
    )
    print(f"\n  {len(merged)} pitchers with both April signals and May-July outcomes")

    # Outcome: ERA improved = moved toward (or below) FIP
    # Positive era_fip_gap in April (BUY) → IMPROVED if outcome_era < april_era
    # Negative era_fip_gap in April (SELL) → DECLINED if outcome_era > april_era
    ERA_FLAT = 0.40  # ~0.40 ERA change minimum to count

    merged["era_change"] = merged["outcome_era"] - merged["era"]
    merged["outcome"] = np.where(
        merged["era_change"] <= -ERA_FLAT, "IMPROVED",
        np.where(merged["era_change"] >= ERA_FLAT, "DECLINED", "FLAT")
    )

    eval_df = merged[
        merged["signal"].isin(SIGNAL_MAP) &
        (merged["outcome"] != "FLAT")
    ].copy()
    eval_df["correct"] = eval_df.apply(
        lambda r: r["outcome"] == SIGNAL_MAP[r["signal"]], axis=1
    )

    # ── Results table ──────────────────────────────────────────────────
    print(f"\n{'=' * 68}")
    print("ACCURACY TABLE — April signals -> May-July ERA outcomes  (2024)")
    print(f"{'=' * 68}")

    bucket_results = []
    for sig_name in ["BUY_LOW","SLIGHT_BUY","SELL_HIGH","SLIGHT_SELL"]:
        grp = eval_df[eval_df["signal"] == sig_name]
        n   = len(grp)
        c   = int(grp["correct"].sum()) if n > 0 else 0
        acc = c / n if n > 0 else float("nan")
        bucket_results.append((sig_name, n, c, acc))

    ov_n = len(eval_df)
    ov_c = int(eval_df["correct"].sum())
    ov_acc = ov_c / ov_n if ov_n > 0 else float("nan")

    print(f"\n  {'Signal':<14} {'n':>5} {'correct':>9} {'accuracy':>10}")
    print(f"  {'-' * 42}")
    for sig_name, n, c, acc in bucket_results:
        acc_str = f"{acc:.1%}" if not pd.isna(acc) else "n/a"
        print(f"  {sig_name:<14} {n:>5} {c:>9} {acc_str:>10}")
    print(f"  {'-' * 42}")
    print(f"  {'OVERALL':<14} {ov_n:>5} {ov_c:>9} {ov_acc:.1%}")
    print(f"  {'vs RTM':<14} {'':>5} {'':>9} {ov_acc - RTM_BASELINE:>+9.1%}pp")

    # ── Gradient table ─────────────────────────────────────────────────
    print(f"\n{'=' * 68}")
    print("GRADIENT — mean ERA change by signal bucket")
    print(f"{'=' * 68}")
    print(f"\n  {'Signal':<14} {'n':>5} {'mean ERA chg':>14} {'mean FIP chg':>14}")
    print(f"  {'-' * 50}")
    merged["fip_change"] = merged["outcome_fip"] - merged["fip"]
    for sig_name in ["BUY_LOW","SLIGHT_BUY","NEUTRAL","SLIGHT_SELL","SELL_HIGH"]:
        grp = merged[merged["signal"] == sig_name]
        n   = len(grp)
        if n < 3:
            print(f"  {sig_name:<14} {n:>5} {'n/a':>14} {'n/a':>14}")
            continue
        era_chg = grp["era_change"].mean()
        fip_chg = grp["fip_change"].mean()
        print(f"  {sig_name:<14} {n:>5} {era_chg:>+14.3f} {fip_chg:>+14.3f}")

    # ── Marquee calls ──────────────────────────────────────────────────
    print(f"\n{'=' * 68}")
    print("MARQUEE PITCHER CALLS (named players with strong signals + correct outcome)")
    print(f"{'=' * 68}")

    named = eval_df[eval_df["correct"] == True].copy()
    named = named.sort_values("era_fip_gap", key=abs, ascending=False)

    print(f"\n  {'Name':<22} {'Team':>4} {'Signal':<12} {'Apr ERA':>8} {'Apr FIP':>8} {'MJul ERA':>9} {'Change':>8} {'Stuff+':>7}")
    print(f"  {'-' * 80}")
    shown = 0
    for _, r in named.iterrows():
        name  = str(r.get("name", r["pitcher"]))
        # Reformat "Last, First" → "First Last"
        if "," in name:
            parts = [p.strip() for p in name.split(",")]
            name = f"{parts[1]} {parts[0]}" if len(parts) == 2 else name
        team  = str(r.get("team", "UNK"))[:3]
        sp    = r["stuff_plus"]
        sp_str = f"{sp:.0f}" if pd.notna(sp) else "n/a"
        print(f"  {name:<22} {team:>4} {r['signal']:<12} {r['era']:>8.2f} {r['fip']:>8.2f} {r['outcome_era']:>9.2f} {r['era_change']:>+8.2f} {sp_str:>7}")
        shown += 1
        if shown >= 20:
            break

    # ── Misses ────────────────────────────────────────────────────────
    print(f"\n{'=' * 68}")
    print("HONEST MISSES (signal was wrong, |era_fip_gap| >= 0.60)")
    print(f"{'=' * 68}")
    misses = eval_df[eval_df["correct"] == False].sort_values("era_fip_gap", key=abs, ascending=False)
    print(f"\n  {'Name':<22} {'Team':>4} {'Signal':<12} {'Apr ERA':>8} {'Apr FIP':>8} {'MJul ERA':>9} {'Change':>8}")
    print(f"  {'-' * 74}")
    for _, r in misses.head(10).iterrows():
        name = str(r.get("name", r["pitcher"]))
        if "," in name:
            parts = [p.strip() for p in name.split(",")]
            name = f"{parts[1]} {parts[0]}" if len(parts) == 2 else name
        team = str(r.get("team", "UNK"))[:3]
        print(f"  {name:<22} {team:>4} {r['signal']:<12} {r['era']:>8.2f} {r['fip']:>8.2f} {r['outcome_era']:>9.2f} {r['era_change']:>+8.2f}")

    # ── Summary ───────────────────────────────────────────────────────
    print(f"\n{'=' * 68}")
    print("SUMMARY")
    print(f"{'=' * 68}")
    print(f"  Signal pitchers (April >= {MIN_APRIL_IP:.0f} IP):  {len(sig)}")
    print(f"  Evaluated (May-Jul >= {MIN_OUTCOME_IP:.0f} IP):    {ov_n}")
    print(f"  Overall accuracy:                   {ov_acc:.1%}")
    print(f"  vs RTM baseline ({RTM_BASELINE:.1%}):          {ov_acc - RTM_BASELINE:>+.1%}pp")
    for sig_name, n, c, acc in bucket_results:
        acc_str = f"{acc:.1%}" if not pd.isna(acc) else "n/a"
        print(f"  {sig_name:<18}: n={n:<4} acc={acc_str}")

    bl_n   = next((n  for s, n, c, a in bucket_results if s == "BUY_LOW"), 0)
    bl_acc = next((a  for s, n, c, a in bucket_results if s == "BUY_LOW"), float("nan"))
    sh_n   = next((n  for s, n, c, a in bucket_results if s == "SELL_HIGH"), 0)
    sh_acc = next((a  for s, n, c, a in bucket_results if s == "SELL_HIGH"), float("nan"))
    verdict = "STRONG SIGNAL" if ov_acc > 0.75 else ("MODERATE SIGNAL" if ov_acc > 0.60 else "WEAK / NOISE")
    print(f"\n  ERA-FIP backtest verdict: {verdict}")


if __name__ == "__main__":
    main()
