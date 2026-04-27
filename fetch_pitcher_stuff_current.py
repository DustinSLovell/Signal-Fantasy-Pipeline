"""
fetch_pitcher_stuff_current.py
================================
Pulls 2026 current-season stuff metrics for all pitchers
in pitcher_luck_scores.csv.

Endpoints:
  statcast_pitcher_arsenal_stats(2026, minPA=10)
  statcast_pitcher_pitch_arsenal(2026, minP=50, arsenal_type='avg_speed')
  statcast_pitcher_pitch_arsenal(2026, minP=50, arsenal_type='avg_spin')

Output: data/pitcher_stuff_current_2026.csv
Columns: pitcher_id, name, curr_swstr_pct, curr_fb_velo,
         curr_spin_rate, n_fastballs, n_pa
"""

import os
import numpy as np
import pandas as pd
import pybaseball as pb

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
OUT_PATH = os.path.join(DATA_DIR, "pitcher_stuff_current_2026.csv")
YEAR     = 2026
MIN_FB   = 50   # minimum fastballs for current velo/spin
MIN_PA   = 10   # minimum PA for current SwStr%

pb.cache.enable()


def _fb_whiff_current(arsenal_df: pd.DataFrame, player_id: int) -> tuple[float | None, int, int]:
    """Returns (whiff_pct, n_fb_pitches, n_pa). FF primary, SI fallback, all-pitch fallback."""
    pdf = arsenal_df[arsenal_df["player_id"] == player_id].copy()
    if pdf.empty:
        return None, 0, 0

    total_pa = int(pdf["pa"].fillna(0).sum())

    for pt in ("FF", "SI"):
        row = pdf[pdf["pitch_type"] == pt]
        if not row.empty and pd.notna(row.iloc[0]["whiff_percent"]):
            r = row.iloc[0]
            n_fb = int(r.get("pitches", 0) or 0)
            n_pa = int(r.get("pa", 0) or 0)
            return float(r["whiff_percent"]) / 100.0, n_fb, n_pa

    # Fallback: weighted average over all pitch types
    pdf = pdf.dropna(subset=["whiff_percent"])
    if pdf.empty:
        return None, 0, total_pa
    pitches = pdf["pitches"].fillna(0).astype(float)
    total_p = pitches.sum()
    if total_p == 0:
        return None, 0, total_pa
    wavg = float(np.average(pdf["whiff_percent"] / 100.0, weights=pitches))
    return wavg, int(total_p), total_pa


def _fb_velo_spin_current(speed_df: pd.DataFrame, spin_df: pd.DataFrame,
                           player_id: int, min_fb: int) -> tuple[float | None, float | None]:
    """Return (curr_fb_velo, curr_spin_rate). Checks min_fb via presence in dataset."""
    velo, spin = None, None
    pid_col = "pitcher"

    if not speed_df.empty:
        row = speed_df[speed_df[pid_col] == player_id]
        if not row.empty:
            r = row.iloc[0]
            for col in ("ff_avg_speed", "si_avg_speed"):
                if col in r and pd.notna(r[col]):
                    velo = float(r[col])
                    break

    if not spin_df.empty:
        row = spin_df[spin_df[pid_col] == player_id]
        if not row.empty:
            r = row.iloc[0]
            for col in ("ff_avg_spin", "si_avg_spin"):
                if col in r and pd.notna(r[col]):
                    spin = float(r[col])
                    break

    return velo, spin


def main():
    os.makedirs(DATA_DIR, exist_ok=True)

    print(f"Fetching 2026 current stuff metrics ...")

    # Load pitcher pipeline for reference
    luck_path = os.path.join(BASE_DIR, "pitcher_luck_scores.csv")
    if os.path.exists(luck_path):
        luck_df = pd.read_csv(luck_path)
        pipeline_ids = set()
        # Get MLBAM ids from pitchers_statcast.csv via name matching
        sc_path = os.path.join(BASE_DIR, "pitchers_statcast.csv")
        if os.path.exists(sc_path):
            sc = pd.read_csv(sc_path, usecols=["pitcher"]).drop_duplicates()
            pipeline_ids = set(sc["pitcher"].astype(int))
    else:
        pipeline_ids = set()

    # Fetch 2026 endpoints
    print("  Fetching arsenal_stats 2026 ...")
    try:
        arsenal = pb.statcast_pitcher_arsenal_stats(2026, minPA=MIN_PA)
        print(f"    {len(arsenal):,} rows")
    except Exception as e:
        print(f"    FAILED: {e}")
        arsenal = pd.DataFrame()

    print("  Fetching avg_speed 2026 ...")
    try:
        speeds = pb.statcast_pitcher_pitch_arsenal(2026, minP=MIN_FB, arsenal_type="avg_speed")
        print(f"    {len(speeds):,} rows")
    except Exception as e:
        print(f"    FAILED: {e}")
        speeds = pd.DataFrame()

    print("  Fetching avg_spin 2026 ...")
    try:
        spins = pb.statcast_pitcher_pitch_arsenal(2026, minP=MIN_FB, arsenal_type="avg_spin")
        print(f"    {len(spins):,} rows")
    except Exception as e:
        print(f"    FAILED: {e}")
        spins = pd.DataFrame()

    if arsenal.empty:
        print("  Arsenal stats unavailable — saving empty CSV")
        pd.DataFrame(columns=["pitcher_id","name","curr_swstr_pct","curr_fb_velo",
                               "curr_spin_rate","n_fastballs","n_pa"]).to_csv(OUT_PATH, index=False)
        return

    # Build per-pitcher current stats
    rows = []
    all_pids = arsenal["player_id"].unique()

    for pid in all_pids:
        pid_int = int(pid)
        name_rows = arsenal[arsenal["player_id"] == pid]["last_name, first_name"]
        name = str(name_rows.iloc[0]).strip() if len(name_rows) > 0 else ""

        whiff, n_fb, n_pa = _fb_whiff_current(arsenal, pid_int)
        velo, spin = _fb_velo_spin_current(speeds, spins, pid_int, MIN_FB)

        # Apply minimums — null out if below threshold
        if n_fb < MIN_FB:
            velo  = None
            spin  = None

        rows.append({
            "pitcher_id":    pid_int,
            "name":          name,
            "curr_swstr_pct": round(whiff, 4) if whiff is not None else None,
            "curr_fb_velo":   round(velo, 2)  if velo  is not None else None,
            "curr_spin_rate": round(spin, 1)  if spin  is not None else None,
            "n_fastballs":    n_fb,
            "n_pa":           n_pa,
        })

    out_df = pd.DataFrame(rows)
    out_df.to_csv(OUT_PATH, index=False)

    n_swstr = out_df["curr_swstr_pct"].notna().sum()
    n_velo  = out_df["curr_fb_velo"].notna().sum()
    n_spin  = out_df["curr_spin_rate"].notna().sum()

    # Pipeline match
    if pipeline_ids:
        matched = out_df["pitcher_id"].isin(pipeline_ids).sum()
    else:
        matched = "N/A"

    print(f"\n  2026 current stuff — {len(out_df):,} pitchers total")
    print(f"    Have curr SwStr%:    {n_swstr:>4}")
    print(f"    Have curr FB velo:   {n_velo:>4}")
    print(f"    Have curr spin rate: {n_spin:>4}")
    print(f"    Match to pipeline:   {matched}")
    print(f"\nSaved: {OUT_PATH}")


if __name__ == "__main__":
    main()
