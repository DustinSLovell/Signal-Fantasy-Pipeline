"""
fetch_fg_pitch_values.py
Fetches hitter pitch-type performance data from Baseball Savant (2024-2026).
"Pitch values" = how well each batter hits each pitch type (run value per 100).
Also fetches current-season batted ball profiles (LD%, FB%, GB%).

Source: baseballsavant.mlb.com/leaderboard/pitch-arsenal-stats?type=batter
  — public CSV endpoint, no auth required, supports year filtering

Outputs:
  data/fg_pitch_values_2024_2026.csv  — all 3 years combined
  data/fg_pitch_values_2026.csv       — 2026 only
  data/fg_batted_ball_2024_2026.csv   — batted ball profiles (2026 YTD only;
                                        endpoint does not support year filtering)

Pitch type mapping (Savant code → FanGraphs column name convention):
  FF = Four-seam → wFA  |  SI = Sinker → wSI  |  FC = Cutter → wFC
  SL = Slider   → wSL  |  CH = Changeup → wCH |  CU = Curve → wCU
  KC = Knuckle curve → wKC  |  FS = Splitter → wFS

Run: python fetch_fg_pitch_values.py [--check]
"""
import csv
import sys
import time
import urllib.request
from pathlib import Path

BASE_ARSENAL = (
    "https://baseballsavant.mlb.com/leaderboard/pitch-arsenal-stats"
    "?type=batter&pitchType={pt}&year={yr}&position=&team=&min=10&csv=true"
)
BASE_BB = (
    "https://baseballsavant.mlb.com/leaderboard/batted-ball?csv=true"
)

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# Savant pitch codes → FanGraphs-style column name
PITCH_MAP = {
    "FF": "wFA",
    "SI": "wSI",
    "FC": "wFC",
    "SL": "wSL",
    "CH": "wCH",
    "CU": "wCU",
    "KC": "wKC",
    "FS": "wFS",
}
SAVANT_PITCH_TYPES = list(PITCH_MAP.keys())
YEARS = [2024, 2025, 2026]
DELAY = 0.8  # seconds between requests

DATA_DIR = Path("data")
PITCH_ALL_OUT = DATA_DIR / "fg_pitch_values_2024_2026.csv"
PITCH_26_OUT  = DATA_DIR / "fg_pitch_values_2026.csv"
BB_ALL_OUT    = DATA_DIR / "fg_batted_ball_2024_2026.csv"

MERRILL_ID = "701538"


def _fetch_csv(url: str) -> list[dict]:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        content = r.read().decode("utf-8-sig")
    return list(csv.DictReader(content.splitlines()))


def fetch_pitch_arsenal(year: int, pitch_type: str) -> list[dict]:
    """Fetch one pitch type / one year from Savant pitch-arsenal-stats."""
    url = BASE_ARSENAL.format(pt=pitch_type, yr=year)
    rows = _fetch_csv(url)
    fg_col = PITCH_MAP[pitch_type]
    for r in rows:
        r["year"]    = year
        r["fg_col"]  = fg_col
    return rows


def fetch_batted_ball() -> list[dict]:
    """Fetch current-season batted ball profiles (no year param supported)."""
    rows = _fetch_csv(BASE_BB)
    for r in rows:
        r["season"] = 2026
    return rows


def build_pitch_value_table(all_arsenal: list[dict]) -> list[dict]:
    """
    Pivot from per-pitch-type rows into one row per (player, year) with
    a column per pitch type: wFA/C, wSI/C, wFC/C … (run value per 100).
    """
    from collections import defaultdict
    # key = (player_id, year)
    table = defaultdict(lambda: {})
    for r in all_arsenal:
        pid  = r.get("player_id", "")
        year = r.get("year", "")
        fg   = r.get("fg_col", "")  # e.g. "wFA"
        if not (pid and year and fg):
            continue
        key = (str(pid), int(year))
        if not table[key]:
            table[key]["player_id"] = str(pid)
            table[key]["name"]      = r.get("last_name, first_name", "")
            table[key]["season"]    = int(year)
            table[key]["pa"]        = r.get("pa", "")
        # store run_value_per_100 as wXX/C convention
        rate_col = f"{fg}/C"
        table[key][rate_col] = r.get("run_value_per_100", "")
        # also store total run value and pitch count for sample gate
        table[key][f"{fg}_rv"]     = r.get("run_value", "")
        table[key][f"{fg}_pitches"] = r.get("pitches", "")

    return list(table.values())


def main(check_mode: bool = False):
    print("=" * 65)
    print("FETCH HITTER PITCH VALUES + BATTED BALL DATA")
    print("Source: Baseball Savant (pitch-arsenal-stats API)")
    print("=" * 65)

    # ── Pitch arsenal data (7 types × 3 years = 21 calls) ────────────────────
    print()
    print("Fetching pitch arsenal data...")
    all_arsenal = []
    counts_by_year: dict[int, int] = {y: 0 for y in YEARS}

    for year in YEARS:
        for pt in SAVANT_PITCH_TYPES:
            try:
                rows = fetch_pitch_arsenal(year, pt)
                all_arsenal.extend(rows)
                counts_by_year[year] += len(rows)
                print(f"  [{year}] {pt} ({PITCH_MAP[pt]}/C): {len(rows)} batters")
            except Exception as e:
                print(f"  [{year}] {pt}: FAILED — {e}")
            time.sleep(DELAY)

    print()
    for year in YEARS:
        print(f"  {year} total arsenal rows: {counts_by_year[year]}")

    # ── Pivot to per-player-year rows ─────────────────────────────────────────
    pivot_rows = build_pitch_value_table(all_arsenal)
    print(f"\n  Pivoted: {len(pivot_rows)} player-year rows")

    # ── Save combined CSV ─────────────────────────────────────────────────────
    rate_cols  = [f"{fg}/C" for fg in PITCH_MAP.values()]
    rv_cols    = [f"{fg}_rv" for fg in PITCH_MAP.values()]
    cnt_cols   = [f"{fg}_pitches" for fg in PITCH_MAP.values()]
    fieldnames = ["player_id", "name", "season", "pa"] + rate_cols + rv_cols + cnt_cols

    with open(PITCH_ALL_OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(pivot_rows, key=lambda x: (x.get("season", 0), x.get("name", ""))))
    print(f"\nSaved: {PITCH_ALL_OUT} ({len(pivot_rows)} rows)")

    rows_2026 = [r for r in pivot_rows if r.get("season") == 2026]
    with open(PITCH_26_OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows_2026)
    print(f"Saved: {PITCH_26_OUT} ({len(rows_2026)} rows — 2026 only)")

    # ── Batted ball data ──────────────────────────────────────────────────────
    print()
    print("Fetching batted ball profiles (2026 YTD)...")
    try:
        bb_rows = fetch_batted_ball()
        print(f"  Rows: {len(bb_rows)}")
        bb_cols = list(bb_rows[0].keys()) if bb_rows else []
        print(f"  Columns: {bb_cols}")

        with open(BB_ALL_OUT, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=bb_cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(bb_rows)
        print(f"Saved: {BB_ALL_OUT} ({len(bb_rows)} rows, 2026 only)")
    except Exception as e:
        print(f"  FAILED — {e}")

    # ── SUMMARY ───────────────────────────────────────────────────────────────
    print()
    print("=" * 65)
    print("SUMMARY — rows per year (after pivot)")
    print("=" * 65)
    for yr in YEARS:
        n = sum(1 for r in pivot_rows if r.get("season") == yr)
        print(f"  {yr}: {n} batters with at least one pitch-type value")

    # ── Merrill spot-check ────────────────────────────────────────────────────
    print()
    print("Jackson Merrill (MLBAM 701538) pitch-value spot-check:")
    for yr in YEARS:
        m = [r for r in pivot_rows
             if str(r.get("player_id", "")) == MERRILL_ID and r.get("season") == yr]
        if m:
            r = m[0]
            wfa = r.get("wFA/C", "n/a")
            wsl = r.get("wSL/C", "n/a")
            wch = r.get("wCH/C", "n/a")
            wsi = r.get("wSI/C", "n/a")
            print(f"  {yr}: wFA/C={wfa}  wSL/C={wsl}  wCH/C={wch}  wSI/C={wsi}")
        else:
            print(f"  {yr}: not found (< 10 pitches of any type?)")

    print()
    print("Jackson Merrill batted-ball spot-check:")
    if bb_rows:
        m_bb = [r for r in bb_rows if str(r.get("id", "")) == MERRILL_ID]
        if m_bb:
            r = m_bb[0]
            print(f"  2026 YTD: ld={r.get('ld_rate','?')[:6]}  "
                  f"fb={r.get('fb_rate','?')[:6]}  "
                  f"gb={r.get('gb_rate','?')[:6]}  "
                  f"bbe={r.get('bbe','?')}")
        else:
            print("  Merrill not found in batted-ball data (< 10 BBE?)")

    if check_mode:
        print()
        print("CHECK — first 5 batters in 2026 pivot:")
        for r in sorted(rows_2026, key=lambda x: x.get("name", ""))[:5]:
            print(f"  {r.get('name','?'):<30} wFA/C={r.get('wFA/C',''):>6}  "
                  f"wSL/C={r.get('wSL/C',''):>6}  pa={r.get('pa','')}")


if __name__ == "__main__":
    check_mode = "--check" in sys.argv
    main(check_mode=check_mode)
