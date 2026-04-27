"""
build_hitter_career_platoon.py
==============================
Builds hitter_career_platoon.json from pitcher Statcast parquet files.

Data sources:
  backtest_cache/pitcher_statcast_april_{year}.parquet   — 2022-2025 (woba + xwoba)
  backtest_cache/pitcher_statcast_mayjuly_2024.parquet   — only year with woba + xwoba

Output: data/hitter_career_platoon.json
  { "player_id": {
      "stand": "L"|"R",
      "career_gap_woba":  float,   # same-hand wOBA minus opp-hand wOBA (typically negative)
      "career_gap_xwoba": float,
      "career_woba_same": float,   # wOBA vs same-hand pitcher
      "career_woba_opp":  float,
      "career_xwoba_same": float,
      "career_xwoba_opp":  float,
      "career_pa_same":   int,
      "career_pa_opp":    int,
  } }

Only players with >= MIN_CAREER_PA_EACH vs each hand are included.
"""

import json
import os
import pandas as pd
from pathlib import Path

BASE_DIR   = Path(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR  = BASE_DIR / "backtest_cache"
OUTPUT     = BASE_DIR / "data" / "hitter_career_platoon.json"

MIN_CAREER_PA_EACH = 30   # min PA vs EACH hand for career entry
PA_EVENTS = {
    "single","double","triple","home_run",
    "field_out","force_out","grounded_into_double_play","double_play",
    "fielders_choice","fielders_choice_out","field_error",
    "walk","intent_walk","hit_by_pitch","strikeout","strikeout_double_play",
    "sac_fly","sac_fly_double_play","sac_bunt","sac_bunt_double_play",
    "truncated_pa",
}


def _load_parquet(path: Path, cols: list[str]) -> pd.DataFrame:
    try:
        df = pd.read_parquet(path, columns=cols)
        return df
    except Exception as ex:
        print(f"  WARNING: could not load {path.name}: {ex}")
        return pd.DataFrame()


def _extract_pa(df: pd.DataFrame) -> pd.DataFrame:
    """Keep only PA-terminal rows (has event), with relevant columns."""
    need = {"batter", "stand", "p_throws", "woba_value"}
    if not need.issubset(df.columns):
        return pd.DataFrame()
    pa = df[df["events"].isin(PA_EVENTS)].copy()
    has_x = "estimated_woba_using_speedangle" in pa.columns
    if not has_x:
        pa["estimated_woba_using_speedangle"] = float("nan")
    return pa[["batter", "stand", "p_throws", "woba_value",
               "estimated_woba_using_speedangle"]].copy()


def main():
    print("Building hitter_career_platoon.json")
    print("=" * 60)

    frames = []

    for yr in [2022, 2023, 2024, 2025]:
        path = CACHE_DIR / f"pitcher_statcast_april_{yr}.parquet"
        if not path.exists():
            print(f"  MISSING: {path.name}")
            continue
        need_cols = ["batter", "stand", "p_throws", "events",
                     "woba_value", "estimated_woba_using_speedangle"]
        raw = _load_parquet(path, need_cols)
        pa  = _extract_pa(raw)
        if pa.empty:
            print(f"  {yr} April: 0 PA rows")
            continue
        print(f"  {yr} April: {len(pa):,} PA rows | "
              f"batters={pa['batter'].nunique()}")
        frames.append(pa)

    # May-July 2024 also has woba + xwoba
    mj24 = CACHE_DIR / "pitcher_statcast_mayjuly_2024.parquet"
    if mj24.exists():
        need_cols = ["batter", "stand", "p_throws", "events",
                     "woba_value", "estimated_woba_using_speedangle"]
        raw = _load_parquet(mj24, need_cols)
        pa  = _extract_pa(raw)
        if not pa.empty:
            print(f"  2024 May-Jul: {len(pa):,} PA rows | "
                  f"batters={pa['batter'].nunique()}")
            frames.append(pa)

    if not frames:
        print("ERROR: No data loaded. Exiting.")
        return

    all_pa = pd.concat(frames, ignore_index=True)
    print(f"\nTotal PA rows: {len(all_pa):,} | Unique batters: {all_pa['batter'].nunique()}")

    result = {}
    skipped_pa = skipped_multi = 0

    for batter_id, grp in all_pa.groupby("batter"):
        bid = int(batter_id)

        # Determine handedness (most common stand value in data)
        stands = grp["stand"].value_counts()
        if stands.empty:
            continue
        stand = stands.index[0]
        if stand not in ("L", "R"):
            skipped_multi += 1
            continue  # skip switch hitters

        # Split by pitcher handedness
        same_rows = grp[grp["p_throws"] == stand]
        opp_rows  = grp[grp["p_throws"] != stand]

        pa_same = int(same_rows["woba_denom"].sum() if "woba_denom" in same_rows.columns
                      else len(same_rows[same_rows["woba_value"].notna()]))
        pa_opp  = int(opp_rows["woba_denom"].sum() if "woba_denom" in opp_rows.columns
                      else len(opp_rows[opp_rows["woba_value"].notna()]))

        # Use count of rows with non-null woba_value as PA proxy
        pa_same = int(same_rows["woba_value"].notna().sum())
        pa_opp  = int(opp_rows["woba_value"].notna().sum())

        if pa_same < MIN_CAREER_PA_EACH or pa_opp < MIN_CAREER_PA_EACH:
            skipped_pa += 1
            continue

        woba_same  = float(same_rows["woba_value"].mean())
        woba_opp   = float(opp_rows["woba_value"].mean())
        xwoba_same = float(same_rows["estimated_woba_using_speedangle"].mean())
        xwoba_opp  = float(opp_rows["estimated_woba_using_speedangle"].mean())

        result[bid] = {
            "stand":             stand,
            "career_gap_woba":   round(woba_same  - woba_opp,  4),
            "career_gap_xwoba":  round(xwoba_same - xwoba_opp, 4),
            "career_woba_same":  round(woba_same,  4),
            "career_woba_opp":   round(woba_opp,   4),
            "career_xwoba_same": round(xwoba_same, 4),
            "career_xwoba_opp":  round(xwoba_opp,  4),
            "career_pa_same":    pa_same,
            "career_pa_opp":     pa_opp,
        }

    print(f"\nBuilt career platoon for {len(result):,} batters")
    print(f"Skipped: {skipped_pa} (PA < {MIN_CAREER_PA_EACH} vs each hand) | "
          f"{skipped_multi} (switch hitters)")

    # Distribution of gap values
    gaps = [v["career_gap_woba"] for v in result.values()]
    import statistics
    if gaps:
        print(f"\nCareer gap distribution (wOBA same-hand minus opp-hand):")
        print(f"  mean={statistics.mean(gaps):.3f}  "
              f"median={statistics.median(gaps):.3f}  "
              f"stdev={statistics.stdev(gaps):.3f}")
        print(f"  min={min(gaps):.3f}  max={max(gaps):.3f}")

    with open(OUTPUT, "w") as f:
        json.dump({str(k): v for k, v in result.items()}, f, indent=2)
    print(f"\nSaved → {OUTPUT}")


if __name__ == "__main__":
    main()
