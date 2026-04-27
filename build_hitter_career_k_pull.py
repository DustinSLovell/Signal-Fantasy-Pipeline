"""
build_hitter_career_k_pull.py

Builds data/hitter_career_k_pull.json — career K% and pull rate baselines
for every hitter in the pipeline.

Data source: backtest_cache/v4_april_{year}.csv for 2022-2025
  (these have the stand + hc_x/hc_y columns required for pull rate;
   statcast_may_july/aug_sep CSVs lack those columns)
Current-year values: luck_scores.csv (k_rate, pull_rate already computed)

Output per hitter:
  {
    "career_k_pct":    float,   # avg April K% over years with >= MIN_PA
    "curr_k_pct":      float,   # 2026 season K%
    "k_pct_delta":     float,   # curr - career (positive = more Ks now)
    "n_years_k":       int,     # years in career K baseline

    "career_pull_pct": float,   # avg April pull rate over years with >= MIN_PA
    "curr_pull_pct":   float,   # 2026 season pull rate
    "pull_pct_delta":  float,   # curr - career (negative = pulling less now)
    "n_years_pull":    int,     # years in career pull baseline

    "k_flag":     bool,  # curr_k_pct > career_k_pct + K_SPIKE_THRESH
    "pull_flag":  bool,  # curr_pull_pct < career_pull_pct - PULL_DROP_THRESH
  }
"""

import json
import math
import os
import numpy as np
import pandas as pd
from pathlib import Path

BASE_DIR   = Path(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR  = BASE_DIR / "backtest_cache"
DATA_DIR   = BASE_DIR / "data"
OUT_PATH   = DATA_DIR / "hitter_career_k_pull.json"
LUCK_PATH  = BASE_DIR / "luck_scores.csv"

CAREER_YEARS     = [2022, 2023, 2024, 2025]
MIN_PA           = 30     # minimum April PA per year to include in baseline
MIN_CURR_K_PA    = 40     # minimum current-season PA to flag K% spike
MIN_CURR_PULL_PA = 50     # minimum current-season PA to flag pull rate drop
                          # (pull rate needs more BIP to stabilize — ~50 PA ≈ 18 fair BIP)
K_SPIKE_THRESH   = 0.030  # 3pp K% rise above career → contact_deterioration flag
PULL_DROP_THRESH = 0.050  # 5pp pull rate drop below career → approach_change flag

# ── Mirror constants from process_stats.py ────────────────────────────────────
NON_PA_EVENTS = {"truncated_pa"}
FAIR_BIP_EVENTS = {
    "single", "double", "triple",
    "field_out", "force_out", "grounded_into_double_play",
    "double_play", "fielders_choice", "fielders_choice_out",
    "field_error", "sac_fly", "sac_fly_double_play",
    "home_run",
}
HP_X, HP_Y           = 125.42, 198.27
PULL_ANGLE_THRESHOLD = 20.0


def _safe_div(num: pd.Series, den: pd.Series) -> pd.Series:
    return num.div(den).where(den > 0, other=float("nan"))


def _calc_k_rate(df: pd.DataFrame) -> pd.Series:
    """K% per batter: (strikeout + strikeout_double_play) / PA."""
    pa_rows = df[df["events"].notna() & ~df["events"].isin(NON_PA_EVENTS)]
    grouped = pa_rows.groupby("batter")
    ks = grouped["events"].apply(
        lambda s: s.isin({"strikeout", "strikeout_double_play"}).sum()
    )
    pa_count = grouped.size()
    return _safe_div(ks, pa_count)


def _calc_pull_rate(df: pd.DataFrame) -> pd.Series:
    """Pull rate per batter using spray chart coords + batting side."""
    fair_bip = df[
        df["events"].isin(FAIR_BIP_EVENTS)
        & df["hc_x"].notna()
        & df["hc_y"].notna()
    ].copy()
    if fair_bip.empty:
        return pd.Series(dtype=float)

    angle = np.degrees(np.arctan2(
        fair_bip["hc_x"] - HP_X,
        HP_Y - fair_bip["hc_y"],
    ))
    fair_bip["pulled"] = (
        ((fair_bip["stand"] == "R") & (angle < -PULL_ANGLE_THRESHOLD))
        | ((fair_bip["stand"] == "L") & (angle > PULL_ANGLE_THRESHOLD))
    )
    grouped    = fair_bip.groupby("batter")
    pull_count = grouped["pulled"].sum()
    total      = grouped["pulled"].count()
    return _safe_div(pull_count, total)


def _calc_pa(df: pd.DataFrame) -> pd.Series:
    pa_rows = df[df["events"].notna() & ~df["events"].isin(NON_PA_EVENTS)]
    return pa_rows.groupby("batter").size()


def build_career_baselines() -> tuple[dict, dict]:
    """
    Returns (k_accum, pull_accum) where each is:
      {batter_id: [per-year values for years with >= MIN_PA]}
    """
    k_accum    = {}
    pull_accum = {}

    for year in CAREER_YEARS:
        path = CACHE_DIR / f"v4_april_{year}.csv"
        if not path.exists():
            print(f"  WARNING: {path} not found — skipping {year}")
            continue

        df = pd.read_csv(path)
        required = {"batter", "events", "stand", "hc_x", "hc_y"}
        if not required.issubset(df.columns):
            print(f"  WARNING: {year} CSV missing columns {required - set(df.columns)} — skipping")
            continue

        pa_series   = _calc_pa(df)
        k_series    = _calc_k_rate(df)
        pull_series = _calc_pull_rate(df)

        n_included = 0
        for bid in pa_series.index:
            pa = int(pa_series.get(bid, 0))
            if pa < MIN_PA:
                continue
            n_included += 1

            k_val    = k_series.get(bid)
            pull_val = pull_series.get(bid)

            if k_val is not None and not math.isnan(float(k_val)):
                k_accum.setdefault(bid, []).append(round(float(k_val), 4))

            if pull_val is not None and not math.isnan(float(pull_val)):
                pull_accum.setdefault(bid, []).append(round(float(pull_val), 4))

        print(f"  April {year}: {n_included:,} hitters included (>= {MIN_PA} PA)")

    return k_accum, pull_accum


def main():
    print("=== build_hitter_career_k_pull.py ===\n")

    # ── Career baselines from April parquets ─────────────────────────────────
    print("Building career K% and pull rate baselines...")
    k_accum, pull_accum = build_career_baselines()

    career_k    = {bid: round(sum(v) / len(v), 4) for bid, v in k_accum.items()}
    career_pull = {bid: round(sum(v) / len(v), 4) for bid, v in pull_accum.items()}
    n_years_k   = {bid: len(v) for bid, v in k_accum.items()}
    n_years_pull = {bid: len(v) for bid, v in pull_accum.items()}

    print(f"\n  Career K baselines:    {len(career_k):,} hitters")
    print(f"  Career pull baselines: {len(career_pull):,} hitters")

    # ── Current-year values from luck_scores.csv ─────────────────────────────
    print("\nLoading current-year values from luck_scores.csv...")
    if not LUCK_PATH.exists():
        print(f"  ERROR: {LUCK_PATH} not found — run score_luck.py first")
        return

    luck_df = pd.read_csv(LUCK_PATH)
    if "batter" not in luck_df.columns:
        print("  ERROR: 'batter' column not found in luck_scores.csv")
        return

    curr_k_map    = {}
    curr_pull_map = {}
    curr_pa_map   = {}
    for _, row in luck_df.iterrows():
        bid = int(row["batter"])
        curr_pa_map[bid] = int(row.get("PA") or 0)
        if pd.notna(row.get("k_rate")):
            curr_k_map[bid]    = round(float(row["k_rate"]), 4)
        if pd.notna(row.get("pull_rate")):
            curr_pull_map[bid] = round(float(row["pull_rate"]), 4)

    print(f"  Current K loaded:    {len(curr_k_map):,} hitters")
    print(f"  Current pull loaded: {len(curr_pull_map):,} hitters")

    # ── Build output ──────────────────────────────────────────────────────────
    # All batters that appear in current luck_scores (they're in the pipeline)
    all_bids = set(int(r["batter"]) for _, r in luck_df.iterrows() if pd.notna(r["batter"]))

    result = {}
    for bid in all_bids:
        rec = {}

        curr_pa = curr_pa_map.get(bid, 0)
        rec["curr_pa"] = curr_pa

        # K% baseline
        if bid in career_k and bid in curr_k_map:
            rec["career_k_pct"]  = career_k[bid]
            rec["curr_k_pct"]    = curr_k_map[bid]
            rec["k_pct_delta"]   = round(curr_k_map[bid] - career_k[bid], 4)
            rec["n_years_k"]     = n_years_k[bid]
            # Only flag if enough current-season PA to be meaningful
            rec["k_flag"]        = (
                rec["k_pct_delta"] > K_SPIKE_THRESH
                and curr_pa >= MIN_CURR_K_PA
            )
        else:
            rec["career_k_pct"]  = None
            rec["curr_k_pct"]    = curr_k_map.get(bid)
            rec["k_pct_delta"]   = None
            rec["n_years_k"]     = 0
            rec["k_flag"]        = False

        # Pull rate baseline
        if bid in career_pull and bid in curr_pull_map:
            rec["career_pull_pct"]  = career_pull[bid]
            rec["curr_pull_pct"]    = curr_pull_map[bid]
            rec["pull_pct_delta"]   = round(curr_pull_map[bid] - career_pull[bid], 4)
            rec["n_years_pull"]     = n_years_pull[bid]
            # Only flag if enough current-season PA for pull rate to stabilize
            rec["pull_flag"]        = (
                rec["pull_pct_delta"] < -PULL_DROP_THRESH
                and curr_pa >= MIN_CURR_PULL_PA
            )
        else:
            rec["career_pull_pct"]  = None
            rec["curr_pull_pct"]    = curr_pull_map.get(bid)
            rec["pull_pct_delta"]   = None
            rec["n_years_pull"]     = 0
            rec["pull_flag"]        = False

        result[bid] = rec

    # ── Stats ─────────────────────────────────────────────────────────────────
    n_k_computable    = sum(1 for r in result.values() if r["k_pct_delta"] is not None)
    n_pull_computable = sum(1 for r in result.values() if r["pull_pct_delta"] is not None)
    n_k_flag          = sum(1 for r in result.values() if r["k_flag"])
    n_pull_flag       = sum(1 for r in result.values() if r["pull_flag"])

    print(f"\nCoverage:")
    print(f"  K delta computable:    {n_k_computable}/{len(result)} ({n_k_computable/len(result)*100:.0f}%)")
    print(f"  Pull delta computable: {n_pull_computable}/{len(result)} ({n_pull_computable/len(result)*100:.0f}%)")
    print(f"  K% spike flags:        {n_k_flag}  (curr > career + {K_SPIKE_THRESH*100:.0f}pp)")
    print(f"  Pull drop flags:       {n_pull_flag}  (curr < career - {PULL_DROP_THRESH*100:.0f}pp)")

    # ── Save ──────────────────────────────────────────────────────────────────
    with open(OUT_PATH, "w") as f:
        json.dump({str(k): v for k, v in result.items()}, f, indent=2)
    print(f"\nSaved: {OUT_PATH} ({len(result):,} hitters)")

    # ── Summary tables ────────────────────────────────────────────────────────
    if not luck_df.empty:
        _name_map = {int(r["batter"]): r["name"] for _, r in luck_df.iterrows() if pd.notna(r.get("name"))}
        _verdict_map = {int(r["batter"]): r.get("verdict", "") for _, r in luck_df.iterrows()}

        print(f"\n── Top 15 K% spikes (>= {MIN_CURR_K_PA} PA, curr - career) ─────────────")
        k_rows = [
            (bid, _name_map.get(bid, str(bid)), r["career_k_pct"], r["curr_k_pct"],
             r["k_pct_delta"], r["curr_pa"], _verdict_map.get(bid, ""))
            for bid, r in result.items()
            if r["k_pct_delta"] is not None and r["curr_pa"] >= MIN_CURR_K_PA
        ]
        k_rows.sort(key=lambda x: x[4], reverse=True)
        print(f"  {'Name':<22} {'Career K%':>9} {'Curr K%':>8} {'Delta':>7} {'PA':>4} {'Flag':>5} {'Verdict'}")
        print("  " + "-" * 75)
        for bid, name, ck, cur, delta, pa, verdict in k_rows[:15]:
            flag = "K-FLAG" if delta > K_SPIKE_THRESH else ""
            print(f"  {name:<22} {ck*100:>8.1f}% {cur*100:>7.1f}% {delta*100:>+6.1f}pp {pa:>4} {flag:>6}  {verdict}")

        print(f"\n── Top 15 pull rate drops (>= {MIN_CURR_PULL_PA} PA, curr - career) ───────────")
        pull_rows = [
            (bid, _name_map.get(bid, str(bid)), r["career_pull_pct"], r["curr_pull_pct"],
             r["pull_pct_delta"], r["curr_pa"], _verdict_map.get(bid, ""))
            for bid, r in result.items()
            if r["pull_pct_delta"] is not None and r["curr_pa"] >= MIN_CURR_PULL_PA
        ]
        pull_rows.sort(key=lambda x: x[4])
        print(f"  {'Name':<22} {'Career Pull%':>12} {'Curr Pull%':>10} {'Delta':>7} {'PA':>4} {'Flag':>8} {'Verdict'}")
        print("  " + "-" * 78)
        for bid, name, cp, cur, delta, pa, verdict in pull_rows[:15]:
            flag = "PULL-FLAG" if delta < -PULL_DROP_THRESH else ""
            print(f"  {name:<22} {cp*100:>11.1f}% {cur*100:>9.1f}% {delta*100:>+6.1f}pp {pa:>4} {flag:>9}  {verdict}")

        print("\n── Flagged hitters with Buy/Slight Buy verdict ─────────────────────")
        buy_verdicts = {"Buy low", "Slight buy"}
        buy_flagged = [
            (bid, _name_map.get(bid, str(bid)), r, _verdict_map.get(bid, ""))
            for bid, r in result.items()
            if _verdict_map.get(bid, "") in buy_verdicts
            and (r["k_flag"] or r["pull_flag"])
        ]
        if buy_flagged:
            for bid, name, r, verdict in buy_flagged:
                flags = []
                if r["k_flag"]:
                    flags.append(f"K+{r['k_pct_delta']*100:+.1f}pp")
                if r["pull_flag"]:
                    flags.append(f"Pull{r['pull_pct_delta']*100:+.1f}pp")
                print(f"  {name:<22} {verdict:<12}  {', '.join(flags)}")
        else:
            print("  None — no buy signals currently flagged")

    print("\nDone.")


if __name__ == "__main__":
    os.chdir(str(BASE_DIR))
    main()
