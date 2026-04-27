"""
build_pitcher_stuff_baselines.py
=================================
Builds per-pitcher career SwStr%, fastball velocity, and spin rate
baselines using Baseball Savant arsenal endpoints.

Data sources (pybaseball):
  statcast_pitcher_arsenal_stats(year, minPA=25)
    -> whiff_percent per pitch type  (whiff% = SwStr% per pitch)
    -> Use FF primary, SI fallback, overall fallback
  statcast_pitcher_pitch_arsenal(year, minP=100, arsenal_type='avg_speed')
    -> ff_avg_speed, si_avg_speed  (4-seam primary, sinker fallback)
  statcast_pitcher_pitch_arsenal(year, minP=100, arsenal_type='avg_spin')
    -> ff_avg_spin, si_avg_spin

YEARS: 2022, 2023, 2024, 2025
Weighting: pitch count per season (mirrors BIP-weighting in career_babip)
Minimums:
  - 200 fastballs per season to include that season
  - 2+ seasons of data
  - 400+ career fastballs total

Output: data/pitcher_career_stuff.json
"""

import json
import os
import numpy as np
import pandas as pd
import pybaseball as pb

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
OUT_PATH = os.path.join(DATA_DIR, "pitcher_career_stuff.json")
YEARS    = [2022, 2023, 2024, 2025]

MIN_FB_SEASON  = 200   # minimum fastballs per season to include
MIN_SEASONS    = 2     # minimum seasons for career baseline
MIN_FB_CAREER  = 400   # minimum career fastballs

pb.cache.enable()


def _cache(name: str) -> str:
    return os.path.join(DATA_DIR, f"stuff_{name}.csv")


def _load_or_fetch(name: str, fetcher, *args, **kwargs) -> pd.DataFrame:
    path = _cache(name)
    if os.path.exists(path):
        try:
            df = pd.read_csv(path)
            if len(df) > 0:
                print(f"  {name}: loaded from cache ({len(df):,} rows)")
                return df
        except Exception:
            pass
    print(f"  {name}: fetching ...")
    try:
        df = fetcher(*args, **kwargs)
        df.to_csv(path, index=False)
        print(f"  {name}: {len(df):,} rows -> cached")
        return df
    except Exception as e:
        print(f"  {name}: FAILED — {e}")
        return pd.DataFrame()


def fetch_arsenal_stats(year: int) -> pd.DataFrame:
    return _load_or_fetch(
        f"arsenal_stats_{year}",
        pb.statcast_pitcher_arsenal_stats, year, minPA=25
    )


def fetch_avg_speed(year: int) -> pd.DataFrame:
    return _load_or_fetch(
        f"arsenal_speed_{year}",
        pb.statcast_pitcher_pitch_arsenal, year, minP=100, arsenal_type="avg_speed"
    )


def fetch_avg_spin(year: int) -> pd.DataFrame:
    return _load_or_fetch(
        f"arsenal_spin_{year}",
        pb.statcast_pitcher_pitch_arsenal, year, minP=100, arsenal_type="avg_spin"
    )


def _fb_whiff(arsenal_df: pd.DataFrame, player_id: int) -> tuple[float | None, int]:
    """
    Return (whiff_pct, n_pitches) for a pitcher's fastball.
    FF primary, SI fallback, all-pitch weighted average last resort.
    """
    pdf = arsenal_df[arsenal_df["player_id"] == player_id].copy()
    if pdf.empty:
        return None, 0

    for pt in ("FF", "SI"):
        row = pdf[pdf["pitch_type"] == pt]
        if not row.empty and pd.notna(row.iloc[0]["whiff_percent"]):
            r = row.iloc[0]
            return float(r["whiff_percent"]) / 100.0, int(r.get("pitches", 0) or 0)

    # Fallback: pitch-count weighted average across all pitch types
    pdf = pdf.dropna(subset=["whiff_percent"])
    if pdf.empty:
        return None, 0
    pitches = pdf["pitches"].fillna(0).astype(float)
    total   = pitches.sum()
    if total == 0:
        return None, 0
    wavg = float(np.average(pdf["whiff_percent"] / 100.0, weights=pitches))
    return wavg, int(total)


def _fb_velo(speed_df: pd.DataFrame, player_id: int) -> tuple[float | None, int]:
    """FF primary, SI fallback. Returns (velo, n_pitches_proxy=0 since not in this df)."""
    if speed_df.empty:
        return None, 0
    pid_col = "pitcher" if "pitcher" in speed_df.columns else "player_id"
    row = speed_df[speed_df[pid_col] == player_id]
    if row.empty:
        return None, 0
    r = row.iloc[0]
    for col in ("ff_avg_speed", "si_avg_speed"):
        if col in r and pd.notna(r[col]):
            return float(r[col]), 0
    return None, 0


def _fb_spin(spin_df: pd.DataFrame, player_id: int) -> float | None:
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


def build_baselines() -> dict:
    os.makedirs(DATA_DIR, exist_ok=True)

    print("=" * 60)
    print("Step 1 — Fetching arsenal data (2022-2025)")
    print("=" * 60)

    arsenal  = {}  # year -> arsenal_stats df
    speeds   = {}  # year -> avg_speed df
    spins    = {}  # year -> avg_spin df

    for yr in YEARS:
        arsenal[yr] = fetch_arsenal_stats(yr)
        speeds[yr]  = fetch_avg_speed(yr)
        spins[yr]   = fetch_avg_spin(yr)

    print("\nRow counts:")
    for yr in YEARS:
        a = len(arsenal.get(yr, []))
        s = len(speeds.get(yr, []))
        sp = len(spins.get(yr, []))
        print(f"  {yr}: arsenal_stats={a:>4} | avg_speed={s:>4} | avg_spin={sp:>4}")

    print("\n" + "=" * 60)
    print("Step 2 — Computing per-pitcher season rows")
    print("=" * 60)

    # Gather all player ids and names from arsenal_stats
    all_pids: dict[int, str] = {}
    for yr, df in arsenal.items():
        if df.empty:
            continue
        for _, r in df.drop_duplicates("player_id").iterrows():
            pid  = int(r["player_id"])
            name = str(r.get("last_name, first_name", "")).strip()
            all_pids[pid] = name

    # Per-pitcher per-year data
    rows: list[dict] = []
    for yr in YEARS:
        a_df = arsenal.get(yr, pd.DataFrame())
        s_df = speeds.get(yr, pd.DataFrame())
        sp_df = spins.get(yr, pd.DataFrame())
        if a_df.empty:
            continue
        for pid, name in all_pids.items():
            whiff, n_fb = _fb_whiff(a_df, pid)
            velo,  _    = _fb_velo(s_df, pid)
            spin        = _fb_spin(sp_df, pid)
            if whiff is None and velo is None:
                continue
            rows.append({
                "pitcher_id": pid,
                "name":       name,
                "year":       yr,
                "whiff_pct":  whiff,
                "fb_velo":    velo,
                "spin_rate":  spin,
                "n_fb":       n_fb,
            })

    if not rows:
        print("  No rows collected.")
        return {}

    df = pd.DataFrame(rows)

    print(f"  {len(df):,} pitcher-season rows across {df['pitcher_id'].nunique()} pitchers")

    print("\n" + "=" * 60)
    print("Step 3 — Building career baselines")
    print("=" * 60)

    result: dict = {}
    for pid in df["pitcher_id"].unique():
        p = df[df["pitcher_id"] == pid].copy()
        name = p["name"].iloc[-1]

        # Apply per-season minimums
        p_fb = p[p["n_fb"] >= MIN_FB_SEASON].copy()

        # Minimum seasons / career pitches
        if len(p_fb) < MIN_SEASONS:
            continue
        total_fb = p_fb["n_fb"].sum()
        if total_fb < MIN_FB_CAREER:
            continue

        # Weighted career SwStr%
        swstr_rows = p_fb.dropna(subset=["whiff_pct"])
        career_swstr = (
            float(np.average(swstr_rows["whiff_pct"], weights=swstr_rows["n_fb"]))
            if len(swstr_rows) >= 1 and swstr_rows["n_fb"].sum() > 0
            else None
        )

        # Weighted career FB velo (equal-weight per season — pitch count not in speed df)
        velo_vals = p_fb["fb_velo"].dropna()
        career_velo = float(velo_vals.mean()) if len(velo_vals) >= 1 else None

        # Weighted career spin
        spin_vals = p_fb["spin_rate"].dropna()
        career_spin = float(spin_vals.mean()) if len(spin_vals) >= 1 else None

        result[str(pid)] = {
            "name":              name,
            "career_swstr_pct":  round(career_swstr, 4) if career_swstr is not None else None,
            "career_fb_velo":    round(career_velo, 2)  if career_velo  is not None else None,
            "career_spin_rate":  round(career_spin, 1)  if career_spin  is not None else None,
            "seasons":           sorted(p_fb["year"].tolist()),
            "n_seasons":         len(p_fb),
            "career_pitch_count": int(total_fb),
        }

    return result


def print_coverage(baselines: dict):
    n_swstr = sum(1 for v in baselines.values() if v["career_swstr_pct"] is not None)
    n_velo  = sum(1 for v in baselines.values() if v["career_fb_velo"]   is not None)
    n_spin  = sum(1 for v in baselines.values() if v["career_spin_rate"] is not None)
    total   = len(baselines)

    # Match against current pipeline
    luck_path = os.path.join(BASE_DIR, "pitcher_luck_scores.csv")
    if os.path.exists(luck_path):
        luck_df = pd.read_csv(luck_path)
        # pitcher_luck_scores uses pitcher MLBAM id — need to match via name or id
        # Load from pitchers_statcast.csv for id mapping
        sc_path = os.path.join(BASE_DIR, "pitchers_statcast.csv")
        if os.path.exists(sc_path):
            sc = pd.read_csv(sc_path, usecols=["pitcher"]).drop_duplicates()
            sc_ids = set(sc["pitcher"].astype(str))
            matched = sum(1 for pid in baselines if pid in sc_ids)
        else:
            matched = "N/A"
        n_pipeline = len(luck_df)
    else:
        matched = "N/A"
        n_pipeline = "N/A"

    print(f"\n  Coverage report:")
    print(f"    Total pitchers with career baseline: {total:>5}")
    print(f"    Have career SwStr%:                  {n_swstr:>5}")
    print(f"    Have career FB velo:                 {n_velo:>5}")
    print(f"    Have career spin rate:               {n_spin:>5}")
    print(f"    Pitchers in current pipeline:        {n_pipeline}")
    print(f"    Matched to pipeline (by MLBAM id):   {matched}")
    if isinstance(matched, int) and isinstance(n_pipeline, int) and n_pipeline > 0:
        print(f"    Match rate:                          {matched/n_pipeline*100:.1f}%")

    # Sample pitchers
    samples = ["Cole, Gerrit", "Skenes, Paul", "Wheeler, Zach", "Gilbert, Logan"]
    print("\n  Sample pitchers:")
    for pid, v in baselines.items():
        if v["name"] in samples:
            print(f"    {v['name']:<28} pid={pid:<8} "
                  f"swstr={v['career_swstr_pct']}  "
                  f"velo={v['career_fb_velo']}  "
                  f"spin={v['career_spin_rate']}  "
                  f"seasons={v['seasons']}")


def main():
    baselines = build_baselines()
    print(f"\n  {len(baselines):,} pitchers qualify for career stuff baseline")
    print_coverage(baselines)

    with open(OUT_PATH, "w") as f:
        json.dump(baselines, f, indent=2)
    sz = os.path.getsize(OUT_PATH) / 1024
    print(f"\nSaved {len(baselines):,} records -> {OUT_PATH}  ({sz:.1f} KB)")


if __name__ == "__main__":
    main()
