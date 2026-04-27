"""
backtest_stuff_quality.py
==========================
Backtests stuff_score as a standalone ERA predictor.
For each year 2022-2025:
  - Compute April stuff_score using that year's arsenal stats
    vs prior years as career baseline
  - Match to May-Jul ERA outcomes from cached parquets
  - Report: buy/sell accuracy, n, vs RTM

Prior-year baseline construction:
  2022 test: career baseline = 2020 + 2021
  2023 test: career baseline = 2021 + 2022
  2024 test: career baseline = 2022 + 2023
  2025 test: career baseline = 2023 + 2024
"""

import json, os
import numpy as np
import pandas as pd
import pybaseball as pb

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
DATA_DIR   = os.path.join(BASE_DIR, "data")
CACHE_DIR  = os.path.join(BASE_DIR, "backtest_cache")

pb.cache.enable()

# Mirrors backtest thresholds
ERA_FLAT        = 0.40
MIN_APRIL_IP    = 15.0
MIN_OUTCOME_IP  = 30.0
RTM_BASELINE    = 0.70

SWSTR_THRESHOLD = 0.015
VELO_THRESHOLD  = 0.8
SPIN_THRESHOLD  = 100.0
SWSTR_WEIGHT    = 3.0
VELO_WEIGHT     = 2.0
SPIN_WEIGHT     = 1.0
SCORE_CAP       = 1.5

BUY_THRESHOLD  =  0.08
SELL_THRESHOLD = -0.08

YEAR_PRIOR_YEARS = {
    2022: [2020, 2021],
    2023: [2021, 2022],
    2024: [2022, 2023],
    2025: [2023, 2024],
}


def _cache(name):
    return os.path.join(DATA_DIR, f"stuff_{name}.csv")


def _load_or_fetch_arsenal(year):
    path = _cache(f"arsenal_stats_{year}")
    if os.path.exists(path):
        df = pd.read_csv(path)
        if len(df) > 0:
            return df
    try:
        df = pb.statcast_pitcher_arsenal_stats(year, minPA=25)
        df.to_csv(path, index=False)
        return df
    except Exception as e:
        print(f"    arsenal_stats {year} FAILED: {e}")
        return pd.DataFrame()


def _load_or_fetch_speed(year):
    path = _cache(f"arsenal_speed_{year}")
    if os.path.exists(path):
        df = pd.read_csv(path)
        if len(df) > 0:
            return df
    try:
        df = pb.statcast_pitcher_pitch_arsenal(year, minP=100, arsenal_type="avg_speed")
        df.to_csv(path, index=False)
        return df
    except Exception as e:
        print(f"    arsenal_speed {year} FAILED: {e}")
        return pd.DataFrame()


def _load_or_fetch_spin(year):
    path = _cache(f"arsenal_spin_{year}")
    if os.path.exists(path):
        df = pd.read_csv(path)
        if len(df) > 0:
            return df
    try:
        df = pb.statcast_pitcher_pitch_arsenal(year, minP=100, arsenal_type="avg_spin")
        df.to_csv(path, index=False)
        return df
    except Exception as e:
        print(f"    arsenal_spin {year} FAILED: {e}")
        return pd.DataFrame()


def _fb_whiff(arsenal_df, player_id):
    pdf = arsenal_df[arsenal_df["player_id"] == player_id]
    if pdf.empty:
        return None, 0
    for pt in ("FF", "SI"):
        row = pdf[pdf["pitch_type"] == pt]
        if not row.empty and pd.notna(row.iloc[0]["whiff_percent"]):
            r = row.iloc[0]
            return float(r["whiff_percent"]) / 100.0, int(r.get("pitches", 0) or 0)
    pdf2 = pdf.dropna(subset=["whiff_percent"])
    if pdf2.empty:
        return None, 0
    pitches = pdf2["pitches"].fillna(0).astype(float)
    if pitches.sum() == 0:
        return None, 0
    return float(np.average(pdf2["whiff_percent"] / 100.0, weights=pitches)), int(pitches.sum())


def _fb_velo(speed_df, player_id):
    if speed_df.empty:
        return None
    pid_col = "pitcher" if "pitcher" in speed_df.columns else "player_id"
    row = speed_df[speed_df[pid_col] == player_id]
    if row.empty:
        return None
    r = row.iloc[0]
    for col in ("ff_avg_speed", "si_avg_speed"):
        if col in r and pd.notna(r[col]):
            return float(r[col])
    return None


def _fb_spin(spin_df, player_id):
    if spin_df.empty:
        return None
    pid_col = "pitcher" if "pitcher" in spin_df.columns else "player_id"
    row = spin_df[spin_df[pid_col] == player_id]
    if row.empty:
        return None
    r = row.iloc[0]
    for col in ("ff_avg_spin", "si_avg_spin"):
        if col in r and pd.notna(r[col]):
            return float(r[col])
    return None


def build_career_baseline(prior_years: list[int]) -> dict:
    """Build per-pitcher career baseline from list of prior years."""
    arsenal_frames = [_load_or_fetch_arsenal(y) for y in prior_years]
    speed_frames   = [_load_or_fetch_speed(y)   for y in prior_years]
    spin_frames    = [_load_or_fetch_spin(y)     for y in prior_years]

    # Gather all pitcher ids
    all_pids = set()
    for df in arsenal_frames:
        if not df.empty:
            all_pids.update(df["player_id"].dropna().astype(int).tolist())

    baselines = {}
    for pid in all_pids:
        swstr_vals, swstr_wts = [], []
        velo_vals, spin_vals  = [], []

        for a_df, s_df, sp_df in zip(arsenal_frames, speed_frames, spin_frames):
            if a_df.empty:
                continue
            w, n = _fb_whiff(a_df, pid)
            if w is not None and n >= 100:
                swstr_vals.append(w)
                swstr_wts.append(n)
            v = _fb_velo(s_df, pid)
            if v is not None:
                velo_vals.append(v)
            sp = _fb_spin(sp_df, pid)
            if sp is not None:
                spin_vals.append(sp)

        if not swstr_vals and not velo_vals:
            continue

        career_swstr = (float(np.average(swstr_vals, weights=swstr_wts))
                        if swstr_vals else None)
        career_velo  = float(np.mean(velo_vals)) if velo_vals else None
        career_spin  = float(np.mean(spin_vals)) if spin_vals else None

        baselines[pid] = {
            "career_swstr_pct": career_swstr,
            "career_fb_velo":   career_velo,
            "career_spin_rate": career_spin,
        }
    return baselines


def compute_april_stuff_scores(year: int, prior_years: list[int]) -> pd.DataFrame:
    """Compute stuff_score for all pitchers in April {year}."""
    print(f"  Building career baseline from {prior_years} ...")
    baselines = build_career_baseline(prior_years)
    print(f"    {len(baselines):,} pitchers in baseline")

    print(f"  Loading April {year} arsenal data ...")
    a_df  = _load_or_fetch_arsenal(year)
    s_df  = _load_or_fetch_speed(year)
    sp_df = _load_or_fetch_spin(year)

    if a_df.empty:
        print(f"    No arsenal data for {year}")
        return pd.DataFrame()

    all_pids = a_df["player_id"].dropna().astype(int).unique()
    rows = []
    for pid in all_pids:
        car = baselines.get(int(pid), {})
        car_swstr = car.get("career_swstr_pct")
        car_velo  = car.get("career_fb_velo")
        car_spin  = car.get("career_spin_rate")

        cur_swstr, n_fb = _fb_whiff(a_df, pid)
        cur_velo  = _fb_velo(s_df,  pid)
        cur_spin  = _fb_spin(sp_df, pid)

        def gap(cur, car):
            if cur is None or car is None:
                return None
            return float(cur) - float(car)

        sg = gap(cur_swstr, car_swstr)
        vg = gap(cur_velo,  car_velo)
        rg = gap(cur_spin,  car_spin)

        swstr_comp = (sg * SWSTR_WEIGHT
                      if sg is not None and abs(sg) > SWSTR_THRESHOLD else 0.0)
        velo_comp  = ((vg / 3.0) * VELO_WEIGHT
                      if vg is not None and abs(vg) > VELO_THRESHOLD  else 0.0)
        spin_comp  = ((rg / 300.0) * SPIN_WEIGHT
                      if rg is not None and abs(rg) > SPIN_THRESHOLD  else 0.0)

        if sg is None and vg is None and rg is None:
            stuff_score = None
        else:
            stuff_score = float(np.clip(swstr_comp + velo_comp + spin_comp,
                                         -SCORE_CAP, SCORE_CAP))

        rows.append({
            "pitcher":     pid,
            "stuff_score": stuff_score,
            "n_fb":        n_fb,
        })

    return pd.DataFrame(rows)


def get_era_outcomes(year: int) -> pd.DataFrame:
    """
    Load April and May-Jul ERA from cached parquets.
    Returns DataFrame with pitcher, april_era, outcome_era, era_change.
    """
    from _pitcher_tier_audit import (
        load_or_fetch, per_start_stats, pitcher_stats,
        CACHE_DIR as PCT_CACHE_DIR, MIN_APRIL_IP, MIN_OUTCOME_IP
    )
    from pathlib import Path

    apr_cache = Path(PCT_CACHE_DIR) / f"pitcher_statcast_april_{year}.parquet"
    out_cache = Path(PCT_CACHE_DIR) / f"pitcher_statcast_mayjuly_{year}.parquet"

    apr_sc = load_or_fetch(apr_cache, f"{year}-04-01", f"{year}-04-30", f"April {year}")
    out_sc = load_or_fetch(out_cache, f"{year}-05-01", f"{year}-07-31", f"May-Jul {year}")

    if apr_sc.empty or out_sc.empty:
        return pd.DataFrame()

    apr_stats = pitcher_stats(apr_sc, per_start_stats(apr_sc))
    out_stats = pitcher_stats(out_sc, per_start_stats(out_sc))

    apr_stats = apr_stats[apr_stats["ip"] >= MIN_APRIL_IP]
    out_stats = out_stats[out_stats["ip"] >= MIN_OUTCOME_IP]

    merged = apr_stats[["pitcher","era","ip"]].merge(
        out_stats[["pitcher","era"]].rename(columns={"era":"outcome_era"}),
        on="pitcher", how="inner"
    )
    merged["era_change"] = merged["outcome_era"] - merged["era"]
    return merged


def run_year(year: int, prior_years: list[int]) -> dict | None:
    print(f"\n{'='*50}")
    print(f"Year {year} (baseline: {prior_years})")
    print(f"{'='*50}")

    stuff_df = compute_april_stuff_scores(year, prior_years)
    if stuff_df.empty:
        print(f"  No stuff scores — skipping {year}")
        return None

    outcomes = get_era_outcomes(year)
    if outcomes.empty:
        print(f"  No ERA outcomes — skipping {year}")
        return None

    merged = outcomes.merge(stuff_df[["pitcher","stuff_score"]], on="pitcher", how="inner")
    merged = merged.dropna(subset=["stuff_score"])

    # Classify stuff signal
    merged["predicted"] = merged["stuff_score"].apply(
        lambda s: "BUY" if s > BUY_THRESHOLD else ("SELL" if s < SELL_THRESHOLD else "NEUTRAL")
    )
    merged["actual"] = merged["era_change"].apply(
        lambda d: "IMPROVED" if d < -ERA_FLAT else ("DECLINED" if d > ERA_FLAT else "FLAT")
    )

    eval_df = merged[merged["predicted"] != "NEUTRAL"].copy()
    eval_df = eval_df[eval_df["actual"] != "FLAT"]

    if eval_df.empty:
        print(f"  No evaluable predictions after filters")
        return None

    buy_df  = eval_df[eval_df["predicted"] == "BUY"]
    sell_df = eval_df[eval_df["predicted"] == "SELL"]

    buy_acc  = (buy_df["actual"] == "IMPROVED").mean() if len(buy_df) > 0 else None
    sell_acc = (sell_df["actual"] == "DECLINED").mean() if len(sell_df) > 0 else None

    overall_correct = (
        ((eval_df["predicted"] == "BUY")  & (eval_df["actual"] == "IMPROVED")) |
        ((eval_df["predicted"] == "SELL") & (eval_df["actual"] == "DECLINED"))
    ).sum()
    overall_acc = overall_correct / len(eval_df) if len(eval_df) > 0 else None

    vs_rtm = (overall_acc - RTM_BASELINE) * 100 if overall_acc is not None else None

    print(f"  {len(merged):,} pitchers matched | {len(eval_df)} evaluable predictions")
    print(f"  Buy predictions:  {len(buy_df):>3} | accuracy {buy_acc*100:.1f}%" if buy_acc is not None else f"  Buy: n={len(buy_df)}")
    print(f"  Sell predictions: {len(sell_df):>3} | accuracy {sell_acc*100:.1f}%" if sell_acc is not None else f"  Sell: n={len(sell_df)}")

    return {
        "year":       year,
        "n_buy":      len(buy_df),
        "n_sell":     len(sell_df),
        "n_eval":     len(eval_df),
        "buy_acc":    buy_acc,
        "sell_acc":   sell_acc,
        "overall_acc": overall_acc,
        "vs_rtm_pp":  vs_rtm,
    }


def main():
    print("STUFF QUALITY STANDALONE BACKTEST (2022-2025)")
    print("=" * 60)

    results = []
    for year, prior in YEAR_PRIOR_YEARS.items():
        res = run_year(year, prior)
        if res:
            results.append(res)

    if not results:
        print("No results — all years failed")
        return

    print("\n" + "=" * 70)
    print("STANDALONE STUFF QUALITY — ACCURACY TABLE")
    print("=" * 70)
    hdr = f"{'Year':<6} | {'Buy acc':>8} | {'n_buy':>6} | {'Sell acc':>9} | {'n_sell':>7} | {'Overall':>8} | {'vs RTM':>7}"
    print(hdr)
    print("-" * len(hdr))
    for r in results:
        ba  = f"{r['buy_acc']*100:.1f}%"  if r['buy_acc']  is not None else "—"
        sa  = f"{r['sell_acc']*100:.1f}%" if r['sell_acc'] is not None else "—"
        oa  = f"{r['overall_acc']*100:.1f}%" if r['overall_acc'] is not None else "—"
        vs  = f"{r['vs_rtm_pp']:+.1f}pp" if r['vs_rtm_pp'] is not None else "—"
        print(f"{r['year']:<6} | {ba:>8} | {r['n_buy']:>6} | {sa:>9} | {r['n_sell']:>7} | {oa:>8} | {vs:>7}")

    # 4-year weighted average
    all_buy  = sum(r.get("n_buy",  0) or 0 for r in results)
    all_sell = sum(r.get("n_sell", 0) or 0 for r in results)
    all_eval = sum(r.get("n_eval", 0) or 0 for r in results)

    buy_correct  = sum((r.get("buy_acc")  or 0) * (r.get("n_buy")  or 0) for r in results)
    sell_correct = sum((r.get("sell_acc") or 0) * (r.get("n_sell") or 0) for r in results)

    if all_buy > 0:
        avg_buy = buy_correct / all_buy
    else:
        avg_buy = None
    if all_sell > 0:
        avg_sell = sell_correct / all_sell
    else:
        avg_sell = None

    all_correct = buy_correct + sell_correct
    avg_overall = all_correct / all_eval if all_eval > 0 else None
    avg_vs_rtm  = (avg_overall - RTM_BASELINE) * 100 if avg_overall is not None else None

    print("-" * len(hdr))
    ba  = f"{avg_buy*100:.1f}%"    if avg_buy     is not None else "—"
    sa  = f"{avg_sell*100:.1f}%"   if avg_sell    is not None else "—"
    oa  = f"{avg_overall*100:.1f}%" if avg_overall is not None else "—"
    vs  = f"{avg_vs_rtm:+.1f}pp"  if avg_vs_rtm  is not None else "—"
    print(f"{'4-yr':<6} | {ba:>8} | {all_buy:>6} | {sa:>9} | {all_sell:>7} | {oa:>8} | {vs:>7}")
    print()

    # Store results for Task 6
    return {
        "buy_acc_4yr":  avg_buy,
        "sell_acc_4yr": avg_sell,
        "overall_4yr":  avg_overall,
        "vs_rtm_4yr":   avg_vs_rtm,
        "n_buy":        all_buy,
        "n_sell":       all_sell,
    }


if __name__ == "__main__":
    main()
