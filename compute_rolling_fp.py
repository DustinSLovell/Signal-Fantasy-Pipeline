"""
compute_rolling_fp.py
=====================
Computes season FP/game and rolling-window FP/game for all signaled players.

Hitter rolling window: 60 AB (most recent games until 60 AB accumulated)
Pitcher rolling window: 20 IP (most recent starts until 20 IP accumulated)

CBS FPTS formula applied to window stats:
  Hitter: R×2.8067 + HR×0.4303 + RBI×2.0806 + SB×1.4222 + AVG×227.3683 − 53.0439
  Pitcher: W×10.5398 + ERA×(−2.5531) + WHIP×(−90.7701) + K×1.3236 + SVH×6.3282 + 122.7395
           SVH = SV×2 + HLD×1 (League 1 weighting)

Output: data/rolling_fp_2026.csv

Usage:
  python compute_rolling_fp.py
"""

import json
import sys
from pathlib import Path

import pandas as pd

GAME_LOGS_DIR = Path("data/game_logs")
LUCK_H_PATH   = Path("luck_scores.csv")
LUCK_P_PATH   = Path("pitcher_luck_scores.csv")
OUTPUT_PATH   = Path("data/rolling_fp_2026.csv")

ROLLING_AB = 60   # hitter rolling window threshold
ROLLING_IP = 20   # pitcher rolling window threshold

# CBS coefficients (must match config.py exactly)
CBS_H_R       =  2.8067
CBS_H_HR      =  0.4303
CBS_H_RBI     =  2.0806
CBS_H_SB      =  1.4222
CBS_H_AVG     = 227.3683
CBS_H_INT     = -53.0439

CBS_P_W       = 10.5398
CBS_P_ERA     = -2.5531
CBS_P_WHIP    = -90.7701
CBS_P_K       =  1.3236
CBS_P_SV      =  6.3282
CBS_P_INT     = 122.7395

# League 1: SV×2 + HLD×1
SV_WEIGHT  = 2
HLD_weight = 1

ACTIVE_SIGNALS = {"Buy low", "Sell high"}
RESOLVING_PCT  = 0.15   # rolling > season by this % → Resolving
DEEPENING_PCT  = 0.15   # rolling < season by this % → Deepening


def _h_fpts(R, HR, RBI, SB, AB, H) -> float:
    if AB == 0:
        return 0.0
    avg = H / AB
    return (CBS_H_R * R + CBS_H_HR * HR + CBS_H_RBI * RBI
            + CBS_H_SB * SB + CBS_H_AVG * avg + CBS_H_INT)


def _p_fpts(W, IP, ER, H, BB, K, SV, HLD) -> float:
    if IP == 0:
        return 0.0
    era  = (ER / IP) * 9
    whip = (H + BB) / IP
    svh  = SV * SV_WEIGHT + HLD * HLD_weight
    return (CBS_P_W * W + CBS_P_ERA * era + CBS_P_WHIP * whip
            + CBS_P_K * K + CBS_P_SV * svh + CBS_P_INT)


def _trend_label(season_fp: float, rolling_fp: float) -> str:
    if season_fp == 0:
        return "Mixed"
    pct_delta = (rolling_fp - season_fp) / abs(season_fp)
    if pct_delta > RESOLVING_PCT:
        return "Resolving"
    if pct_delta < -DEEPENING_PCT:
        return "Deepening"
    return "Mixed"


def _compute_hitter(games: list) -> dict:
    """Returns season and rolling FP/game metrics for a hitter."""
    if not games:
        return {}

    # Season totals (all games)
    s_R = s_H = s_HR = s_RBI = s_SB = s_AB = 0
    for g in games:
        s_R   += g["R"]
        s_H   += g["H"]
        s_HR  += g["HR"]
        s_RBI += g["RBI"]
        s_SB  += g["SB"]
        s_AB  += g["AB"]

    season_games  = len(games)
    season_fpts   = _h_fpts(s_R, s_HR, s_RBI, s_SB, s_AB, s_H)
    season_fp_pg  = round(season_fpts / season_games, 2) if season_games > 0 else None

    # Rolling window: scan from most recent game backward until ROLLING_AB accumulated
    rev = list(reversed(games))
    win_R = win_H = win_HR = win_RBI = win_SB = win_AB = 0
    win_games = 0
    for g in rev:
        win_R   += g["R"]
        win_H   += g["H"]
        win_HR  += g["HR"]
        win_RBI += g["RBI"]
        win_SB  += g["SB"]
        win_AB  += g["AB"]
        win_games += 1
        if win_AB >= ROLLING_AB:
            break

    sufficient = win_AB >= ROLLING_AB
    window_start = rev[win_games - 1]["date"] if win_games > 0 else ""
    window_end   = rev[0]["date"] if rev else ""

    rolling_fpts  = _h_fpts(win_R, win_HR, win_RBI, win_SB, win_AB, win_H)
    rolling_fp_pg = round(rolling_fpts / win_games, 2) if win_games > 0 else None

    return {
        "season_fp_per_game":       season_fp_pg,
        "rolling_fp_per_game":      rolling_fp_pg,
        "rolling_window_games":     win_games,
        "rolling_window_ab_or_ip":  win_AB,
        "rolling_window_start_date":window_start,
        "rolling_window_end_date":  window_end,
        "sufficient_sample":        sufficient,
        "season_games":             season_games,
        "season_ab":                s_AB,
    }


def _compute_pitcher(games: list) -> dict:
    """Returns season and rolling FP/start metrics for a pitcher."""
    if not games:
        return {}

    # Season totals (all appearances)
    s_W = s_IP = s_ER = s_H = s_BB = s_K = s_SV = s_HLD = 0
    season_starts = 0
    for g in games:
        s_W   += g["W"]
        s_IP  += g["IP"]
        s_ER  += g["ER"]
        s_H   += g["H"]
        s_BB  += g["BB"]
        s_K   += g["K"]
        s_SV  += g["SV"]
        s_HLD += g["HLD"]
        season_starts += 1

    season_fpts  = _p_fpts(s_W, s_IP, s_ER, s_H, s_BB, s_K, s_SV, s_HLD)
    season_fp_ps = round(season_fpts / season_starts, 2) if season_starts > 0 else None

    # Rolling window: scan from most recent appearance backward until ROLLING_IP accumulated
    rev = list(reversed(games))
    win_W = win_IP = win_ER = win_H = win_BB = win_K = win_SV = win_HLD = 0
    win_starts = 0
    for g in rev:
        win_W   += g["W"]
        win_IP  += g["IP"]
        win_ER  += g["ER"]
        win_H   += g["H"]
        win_BB  += g["BB"]
        win_K   += g["K"]
        win_SV  += g["SV"]
        win_HLD += g["HLD"]
        win_starts += 1
        if win_IP >= ROLLING_IP:
            break

    sufficient   = win_IP >= ROLLING_IP
    window_start = rev[win_starts - 1]["date"] if win_starts > 0 else ""
    window_end   = rev[0]["date"] if rev else ""

    rolling_fpts  = _p_fpts(win_W, win_IP, win_ER, win_H, win_BB, win_K, win_SV, win_HLD)
    rolling_fp_ps = round(rolling_fpts / win_starts, 2) if win_starts > 0 else None

    return {
        "season_fp_per_game":       season_fp_ps,
        "rolling_fp_per_game":      rolling_fp_ps,
        "rolling_window_games":     win_starts,
        "rolling_window_ab_or_ip":  round(win_IP, 2),
        "rolling_window_start_date":window_start,
        "rolling_window_end_date":  window_end,
        "sufficient_sample":        sufficient,
        "season_games":             season_starts,
        "season_ip":                round(s_IP, 2),
    }


def main():
    if not GAME_LOGS_DIR.exists():
        print(f"ERROR: {GAME_LOGS_DIR} not found — run fetch_game_logs.py first.")
        sys.exit(1)

    rows = []

    # ── Hitters ───────────────────────────────────────────────────────────────
    hitters = pd.read_csv(LUCK_H_PATH)
    h_sig   = hitters[hitters["verdict"].isin(ACTIVE_SIGNALS)][["name", "batter", "verdict"]].copy()

    h_ok, h_missing = 0, 0
    for _, row in h_sig.iterrows():
        mlb_id = int(row["batter"])
        path   = GAME_LOGS_DIR / f"hitter_{mlb_id}.json"

        if not path.exists():
            h_missing += 1
            continue

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        metrics = _compute_hitter(data.get("games", []))
        if not metrics:
            h_missing += 1
            continue

        season_fp  = metrics["season_fp_per_game"]
        rolling_fp = metrics["rolling_fp_per_game"]
        trend      = _trend_label(season_fp or 0, rolling_fp or 0)

        rows.append({
            "player_id":                mlb_id,
            "player_name":              row["name"],
            "type":                     "hitter",
            "signal":                   row["verdict"],
            "season_fp_per_game":       season_fp,
            "rolling_fp_per_game":      rolling_fp,
            "rolling_window_games":     metrics["rolling_window_games"],
            "rolling_window_ab_or_ip":  metrics["rolling_window_ab_or_ip"],
            "rolling_window_start_date":metrics["rolling_window_start_date"],
            "rolling_window_end_date":  metrics["rolling_window_end_date"],
            "sufficient_sample":        metrics["sufficient_sample"],
            "trend_label":              trend,
        })
        h_ok += 1

    print(f"Hitters processed: {h_ok} ok, {h_missing} missing game log")

    # ── Pitchers ──────────────────────────────────────────────────────────────
    pitchers = pd.read_csv(LUCK_P_PATH)
    p_sig    = pitchers[pitchers["verdict"].isin(ACTIVE_SIGNALS)][["name", "pitcher", "verdict"]].copy()

    p_ok, p_missing = 0, 0
    for _, row in p_sig.iterrows():
        mlb_id = int(row["pitcher"])
        path   = GAME_LOGS_DIR / f"pitcher_{mlb_id}.json"

        if not path.exists():
            p_missing += 1
            continue

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        metrics = _compute_pitcher(data.get("games", []))
        if not metrics:
            p_missing += 1
            continue

        season_fp  = metrics["season_fp_per_game"]
        rolling_fp = metrics["rolling_fp_per_game"]
        trend      = _trend_label(season_fp or 0, rolling_fp or 0)

        rows.append({
            "player_id":                mlb_id,
            "player_name":              row["name"],
            "type":                     "pitcher",
            "signal":                   row["verdict"],
            "season_fp_per_game":       season_fp,
            "rolling_fp_per_game":      rolling_fp,
            "rolling_window_games":     metrics["rolling_window_games"],
            "rolling_window_ab_or_ip":  metrics["rolling_window_ab_or_ip"],
            "rolling_window_start_date":metrics["rolling_window_start_date"],
            "rolling_window_end_date":  metrics["rolling_window_end_date"],
            "sufficient_sample":        metrics["sufficient_sample"],
            "trend_label":              trend,
        })
        p_ok += 1

    print(f"Pitchers processed: {p_ok} ok, {p_missing} missing game log")

    df = pd.DataFrame(rows)
    df.to_csv(OUTPUT_PATH, index=False)
    print(f"Written: {OUTPUT_PATH} ({len(df)} rows)")
    print()

    # ── Gate check: Luzardo ───────────────────────────────────────────────────
    luzardo = df[(df["player_name"].str.contains("Luzardo", case=False)) & (df["type"] == "pitcher")]
    if not luzardo.empty:
        r = luzardo.iloc[0]
        print(f"GATE CHECK — Luzardo:")
        print(f"  Season FP/start:  {r['season_fp_per_game']}")
        print(f"  Rolling FP/start: {r['rolling_fp_per_game']}")
        print(f"  Trend label:      {r['trend_label']}")
        print(f"  Window: {r['rolling_window_games']} starts, {r['rolling_window_ab_or_ip']} IP")
        print(f"  Window dates: {r['rolling_window_start_date']} → {r['rolling_window_end_date']}")
        print(f"  Sufficient sample: {r['sufficient_sample']}")
        if r["rolling_fp_per_game"] is not None and r["season_fp_per_game"] is not None:
            if r["rolling_fp_per_game"] > r["season_fp_per_game"]:
                print(f"  GATE 1 PASS: rolling ({r['rolling_fp_per_game']}) > season ({r['season_fp_per_game']}) ✓")
            else:
                print(f"  GATE 1 FAIL: rolling ({r['rolling_fp_per_game']}) <= season ({r['season_fp_per_game']}) ✗")

    # ── Gate check: any Sell High pitcher with rolling < season ───────────────
    sh_p = df[(df["type"] == "pitcher") & (df["signal"] == "Sell high")]
    deepening = sh_p[sh_p["trend_label"] == "Deepening"]
    print()
    print(f"GATE CHECK — Sell High pitchers deepening: {len(deepening)}")
    if not deepening.empty:
        print("  Examples:")
        for _, r in deepening.head(3).iterrows():
            print(f"    {r['player_name']}: season={r['season_fp_per_game']}, rolling={r['rolling_fp_per_game']}")
        print(f"  GATE 2 PASS ✓")
    else:
        print(f"  GATE 2 FAIL — no Sell High pitcher shows deepening signal ✗")

    # ── Summary ───────────────────────────────────────────────────────────────
    print()
    print("Trend distribution:")
    print(df["trend_label"].value_counts().to_string())


if __name__ == "__main__":
    main()
