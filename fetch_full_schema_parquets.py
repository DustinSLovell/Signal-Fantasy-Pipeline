"""
fetch_full_schema_parquets.py

One-time script: re-fetches April 2022, 2023, 2025 Statcast parquets
with the full column schema (no NEEDED_COLS filter).

2024 is skipped — it was already saved with 118 columns.

Uses pybaseball's local disk cache (3,800+ files already cached),
so each fetch should complete in seconds without live API calls.
"""
import time
import pandas as pd
import pybaseball as pb
from pathlib import Path

pb.cache.enable()

CACHE_DIR = Path("backtest_cache")
CACHE_DIR.mkdir(exist_ok=True)

YEARS_TO_FETCH = [2022, 2023, 2025]   # 2024 already full-schema — do not overwrite
SKIP_YEAR = 2024

def fetch_full(year: int) -> pd.DataFrame:
    start_dt = f"{year}-04-01"
    end_dt   = f"{year}-04-30"
    print(f"  Fetching April {year} ({start_dt} to {end_dt}) — no column filter...", flush=True)
    t0 = time.time()
    try:
        df = pb.statcast(start_dt=start_dt, end_dt=end_dt)
        elapsed = time.time() - t0
        if df is None or df.empty:
            print(f"  WARNING: empty result for {year}")
            return pd.DataFrame()
        print(f"  Fetched {len(df):,} rows x {len(df.columns)} cols in {elapsed:.1f}s")
        return df
    except Exception as ex:
        print(f"  ERROR: {ex}")
        return pd.DataFrame()


def main():
    # Report existing column counts first
    print("Current parquet state:")
    for year in [2022, 2023, 2024, 2025]:
        p = CACHE_DIR / f"pitcher_statcast_april_{year}.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            print(f"  {year}: {len(df.columns)} cols, {len(df):,} rows")
        else:
            print(f"  {year}: FILE MISSING")

    print()
    results = {}

    for year in YEARS_TO_FETCH:
        out_path = CACHE_DIR / f"pitcher_statcast_april_{year}.parquet"
        print(f"\n{'='*60}")
        print(f"April {year}")
        print("="*60)

        df = fetch_full(year)
        if df.empty:
            print(f"  SKIP {year} — fetch returned empty")
            results[year] = None
            continue

        df.to_parquet(out_path, index=False)
        print(f"  Saved: {out_path.name}  ({len(df.columns)} cols, {len(df):,} rows)")
        results[year] = len(df.columns)

    print()
    print("="*60)
    print("FINAL COLUMN COUNTS")
    print("="*60)
    for year in [2022, 2023, 2024, 2025]:
        p = CACHE_DIR / f"pitcher_statcast_april_{year}.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            status = "SKIP (not re-fetched)" if year == SKIP_YEAR else ""
            print(f"  {year}: {len(df.columns)} cols, {len(df):,} rows  {status}")
        else:
            print(f"  {year}: MISSING")


if __name__ == "__main__":
    main()
