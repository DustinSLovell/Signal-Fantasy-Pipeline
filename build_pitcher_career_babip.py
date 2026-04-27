"""
build_pitcher_career_babip.py
==============================
Builds per-pitcher career BABIP/HardHit/Barrel baselines using Baseball Savant
endpoints (FanGraphs is Cloudflare-blocked in 2026).

Data sources (all via pybaseball):
  statcast_pitcher_expected_stats(year) -> ba, bip, pa  per pitcher-season
  statcast_pitcher_exitvelo_barrels(year) -> ev95percent, brl_percent, attempts

BABIP derivation:
  BABIP_approx = BA + 0.048  (same-year r=0.87, N=193, validated against
  actual BABIP computed from pitchers_statcast.csv for 2026 season)
  Weighted by bip count per season.

Career baselines (min 100 IP-equivalent PA across all years):
  career_babip_allowed     IP-weighted mean BABIP (BA+0.048)
  career_hard_hit_allowed  attempt-weighted mean HH%
  career_barrel_allowed    attempt-weighted mean barrel%
  career_ip_equiv          total PA (proxy for IP, r>0.99)

Output: data/pitcher_career_babip.json  (keyed by MLBAM pitcher_id, str)
Cache:  data/fg_pitching_{year}.csv     (one file per season)
"""

import json
import os

import numpy as np
import pandas as pd
import pybaseball

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
DATA_DIR  = os.path.join(BASE_DIR, "data")
OUT_PATH  = os.path.join(DATA_DIR, "pitcher_career_babip.json")
YEARS     = [2022, 2023, 2024, 2025]

# Validated correction: BABIP = BA + BABIP_BA_OFFSET  (same-year r=0.87)
BABIP_BA_OFFSET  = 0.048
MIN_BIP_SEASON   = 20    # minimum BIP to include a single season row
MIN_PA_CAREER    = 300   # min career PA-equivalent for a published baseline (~100 IP)
MIN_BBE_SEASON   = 20    # min BBE for exit-velo row inclusion


def _cache_path(year: int) -> str:
    return os.path.join(DATA_DIR, f"fg_pitching_{year}.csv")


def fetch_expected_stats(year: int) -> pd.DataFrame:
    """Return per-pitcher BA, BIP, PA for year. Cached to fg_pitching_{year}.csv."""
    cache = _cache_path(year)

    # Try to load from cache first
    if os.path.exists(cache):
        try:
            df = pd.read_csv(cache)
            # Validate it has the columns we need (old cache may be empty from failed FG fetch)
            if "ba" in df.columns and len(df) > 0:
                print(f"  {year}: expected_stats loaded from cache ({len(df):,} rows)")
                return df
        except Exception:
            pass  # fall through to fresh fetch

    print(f"  {year}: fetching expected_stats from Baseball Savant ...")
    pybaseball.cache.enable()
    try:
        raw = pybaseball.statcast_pitcher_expected_stats(year, minPA=MIN_BIP_SEASON)
    except Exception as e:
        print(f"  {year}: fetch failed: {e}")
        return pd.DataFrame()

    df = raw.rename(columns={"player_id": "pitcher_id"}).copy()
    df.to_csv(cache, index=False)
    print(f"  {year}: {len(df):,} rows -> cached to {os.path.basename(cache)}")
    return df


def fetch_exitvelo(year: int) -> pd.DataFrame:
    """Return per-pitcher HH% and barrel% for year (not cached separately)."""
    ev_cache = os.path.join(DATA_DIR, f"fg_pitching_ev_{year}.csv")
    if os.path.exists(ev_cache):
        try:
            df = pd.read_csv(ev_cache)
            if "ev95percent" in df.columns and len(df) > 0:
                print(f"  {year}: exitvelo loaded from cache ({len(df):,} rows)")
                return df
        except Exception:
            pass

    print(f"  {year}: fetching exitvelo from Baseball Savant ...")
    pybaseball.cache.enable()
    try:
        raw = pybaseball.statcast_pitcher_exitvelo_barrels(year, minBBE=MIN_BBE_SEASON)
    except Exception as e:
        print(f"  {year}: exitvelo fetch failed: {e}")
        return pd.DataFrame()

    df = raw.rename(columns={"player_id": "pitcher_id"}).copy()
    df.to_csv(ev_cache, index=False)
    print(f"  {year}: {len(df):,} rows -> {os.path.basename(ev_cache)}")
    return df


def build_baselines() -> dict:
    os.makedirs(DATA_DIR, exist_ok=True)

    print("Step 1 — Fetching per-season pitcher data (2022-2025)")
    print("=" * 60)

    es_frames  = {}   # year -> expected_stats df
    ev_frames  = {}   # year -> exitvelo df

    for yr in YEARS:
        es = fetch_expected_stats(yr)
        ev = fetch_exitvelo(yr)
        if not es.empty:
            es_frames[yr] = es
        if not ev.empty:
            ev_frames[yr] = ev

    print("\nRow counts:")
    for yr in YEARS:
        es_n = len(es_frames.get(yr, []))
        ev_n = len(ev_frames.get(yr, []))
        print(f"  {yr}: expected_stats={es_n:>4} | exitvelo={ev_n:>4}")

    # ── Collect all rows ──────────────────────────────────────────────────
    print("\nStep 2 — Computing IP-weighted career baselines")
    print("=" * 60)

    babip_rows = []
    ev_rows    = []

    for yr, df in es_frames.items():
        pid_col = "pitcher_id" if "pitcher_id" in df.columns else "player_id"
        if pid_col not in df.columns:
            print(f"  {yr}: no pitcher_id column — skipped")
            continue
        for _, r in df.iterrows():
            pid  = r.get(pid_col)
            bip  = r.get("bip", 0) or 0
            pa   = r.get("pa", 0) or 0
            ba   = r.get("ba")
            name = str(r.get("last_name, first_name", "")).strip()
            if pd.isna(pid) or bip < MIN_BIP_SEASON or pd.isna(ba):
                continue
            babip_rows.append({
                "pitcher_id": str(int(pid)),
                "name":       name,
                "year":       yr,
                "bip":        float(bip),
                "pa":         float(pa),
                "babip_approx": float(ba) + BABIP_BA_OFFSET,
            })

    for yr, df in ev_frames.items():
        pid_col = "pitcher_id" if "pitcher_id" in df.columns else "player_id"
        if pid_col not in df.columns:
            continue
        for _, r in df.iterrows():
            pid       = r.get(pid_col)
            attempts  = r.get("attempts", 0) or 0
            ev95      = r.get("ev95percent")
            brl_pct   = r.get("brl_percent")
            if pd.isna(pid) or attempts < MIN_BBE_SEASON:
                continue
            ev_rows.append({
                "pitcher_id":  str(int(pid)),
                "year":        yr,
                "attempts":    float(attempts),
                "hard_hit_pct":float(ev95) / 100 if pd.notna(ev95) else np.nan,
                "barrel_pct":  float(brl_pct) / 100 if pd.notna(brl_pct) else np.nan,
            })

    if not babip_rows:
        print("  No data collected — empty output")
        return {}

    babip_df = pd.DataFrame(babip_rows)
    ev_df    = pd.DataFrame(ev_rows) if ev_rows else pd.DataFrame(
                 columns=["pitcher_id","year","attempts","hard_hit_pct","barrel_pct"])

    # ── Build career aggregations ────────────────────────────────────────
    result = {}

    all_pids = set(babip_df["pitcher_id"].unique())
    for pid in all_pids:
        b  = babip_df[babip_df["pitcher_id"] == pid]
        ev = ev_df[ev_df["pitcher_id"] == pid] if len(ev_df) > 0 else pd.DataFrame()

        total_pa = b["pa"].sum()
        if total_pa < MIN_PA_CAREER:
            continue

        # IP-weighted BABIP (weighted by BIP count)
        babip_baseline = float(np.average(b["babip_approx"], weights=b["bip"])) \
                         if len(b) > 0 else None

        # Attempt-weighted HH% and barrel%
        def wavg_ev(col):
            sub = ev[["attempts", col]].dropna()
            if len(sub) < 1 or sub["attempts"].sum() == 0:
                return None
            return float(np.average(sub[col], weights=sub["attempts"]))

        hh  = wavg_ev("hard_hit_pct")
        brl = wavg_ev("barrel_pct")

        result[pid] = {
            "name":                    b["name"].iloc[-1],
            "career_pa_equiv":         round(total_pa, 0),
            "career_babip_allowed":    round(babip_baseline, 4) if babip_baseline else None,
            "career_hard_hit_allowed": round(hh,  4) if hh  is not None else None,
            "career_barrel_allowed":   round(brl, 4) if brl is not None else None,
            "seasons":                 sorted(b["year"].tolist()),
            "n_seasons":               len(b),
        }

    return result


def print_summary(baselines: dict):
    babips = [v["career_babip_allowed"] for v in baselines.values()
              if v["career_babip_allowed"] is not None]
    if not babips:
        return
    arr = np.array(babips)
    print(f"\n  Career BABIP baseline distribution ({len(arr)} pitchers):")
    print(f"    mean={arr.mean():.4f}  std={arr.std():.4f}  "
          f"min={arr.min():.4f}  max={arr.max():.4f}")
    print(f"    < 0.270 (elite suppressor):  {(arr < 0.270).sum():>4}")
    print(f"    0.270 - 0.290:               {((arr >= 0.270) & (arr < 0.290)).sum():>4}")
    print(f"    0.290 - 0.310 (average):     {((arr >= 0.290) & (arr < 0.310)).sum():>4}")
    print(f"    0.310 - 0.325:               {((arr >= 0.310) & (arr < 0.325)).sum():>4}")
    print(f"    >= 0.325 (poor suppressor):  {(arr >= 0.325).sum():>4}")

    # Key pitchers
    print("\n  Sample pitchers:")
    targets = {
        "skenes":    "Paul Skenes",
        "wheeler":   "Zach Wheeler",
        "alcantara": "Sandy Alcantara",
        "cole":      "Gerrit Cole",
        "burnes":    "Corbin Burnes",
    }
    for pid, v in baselines.items():
        n = v["name"].lower()
        for key, display in list(targets.items()):
            if key in n:
                del targets[key]
                print(f"    {display:<26} pid={pid:<8} "
                      f"BABIP={v['career_babip_allowed']:.4f}  "
                      f"HH%={v['career_hard_hit_allowed']:.4f}  "
                      f"Brl%={v['career_barrel_allowed']:.4f}  "
                      f"PA={v['career_pa_equiv']:.0f}  "
                      f"seasons={v['seasons']}")


def main():
    baselines = build_baselines()
    print(f"\n  {len(baselines):,} pitchers qualify (>= {MIN_PA_CAREER} career PA-equiv)")
    print_summary(baselines)

    with open(OUT_PATH, "w") as f:
        json.dump(baselines, f, indent=2)
    sz = os.path.getsize(OUT_PATH) / 1024
    print(f"\nSaved {len(baselines):,} records -> {OUT_PATH}  ({sz:.1f} KB)")


if __name__ == "__main__":
    main()
