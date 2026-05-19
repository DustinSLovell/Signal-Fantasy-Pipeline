"""
fetch_statcast_gamelogs_2025.py
Pull 2025 game-by-game Statcast data from Baseball Savant.
Fetches all players in backtest_A_hitters_2025.csv and backtest_A_pitchers_2025.csv.
Output: data/statcast_gamelogs_2025/hitter_{id}.csv and pitcher_{id}.csv
"""
import csv
import os
import time
import urllib.request
import urllib.parse
from pathlib import Path

BASE_URL   = "https://baseballsavant.mlb.com/statcast_search/csv"
OUT_DIR    = Path("data/statcast_gamelogs_2025")
DELAY_SEC  = 1.5

HITTER_CSV  = "data/backtest_A_hitters_2025.csv"
PITCHER_CSV = "data/backtest_A_pitchers_2025.csv"


def _build_url(mlbam_id: int, player_type: str) -> str:
    if player_type == "batter":
        lookup_key = "batters_lookup%5B%5D"
    else:
        lookup_key = "pitchers_lookup%5B%5D"

    params = (
        f"hfSea=2025%7C"
        f"&player_type={player_type}"
        f"&{lookup_key}={mlbam_id}"
        f"&group_by=name-date"
        f"&min_pas=1"
    )
    return f"{BASE_URL}?{params}"


def _fetch_player(mlbam_id: int, player_type: str, out_path: Path) -> int:
    """Fetch one player's 2025 game logs. Returns row count (0 on failure)."""
    url = _build_url(mlbam_id, player_type)
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        print(f"    ERROR: {exc}")
        return 0

    lines = [l for l in raw.strip().splitlines() if l.strip()]
    if len(lines) < 2:
        return 0

    out_path.write_text(raw, encoding="utf-8")
    return len(lines) - 1  # subtract header


def _load_ids(csv_path: str) -> list[tuple[str, int]]:
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                rows.append((r["name"], int(r["mlbam_id"])))
            except (KeyError, ValueError):
                pass
    return rows


def fetch_cohort(csv_path: str, player_type: str, prefix: str) -> dict:
    players = _load_ids(csv_path)
    total   = len(players)
    results = {"fetched": 0, "skipped": 0, "total_rows": 0, "files": []}

    print(f"\n{'='*60}")
    print(f"Fetching {total} {player_type}s from {csv_path}")
    print(f"{'='*60}")

    for n, (name, mlbam_id) in enumerate(players, 1):
        out_path = OUT_DIR / f"{prefix}_{mlbam_id}.csv"

        print(f"  [{n:>3}/{total}] {name} ({mlbam_id})... ", end="", flush=True)

        if out_path.exists() and out_path.stat().st_size > 200:
            row_count = sum(1 for _ in out_path.open()) - 1
            print(f"cached ({row_count} rows)")
            results["fetched"]     += 1
            results["total_rows"]  += row_count
            results["files"].append(str(out_path))
            continue

        row_count = _fetch_player(mlbam_id, player_type, out_path)
        if row_count > 0:
            print(f"{row_count} rows")
            results["fetched"]    += 1
            results["total_rows"] += row_count
            results["files"].append(str(out_path))
        else:
            print("no data")
            results["skipped"] += 1

        time.sleep(DELAY_SEC)

    return results


def _verify_elly(mlbam_id: int = 666163):
    path = OUT_DIR / f"hitter_{mlbam_id}.csv"
    if not path.exists():
        print("  Elly De La Cruz file not found — may have been skipped")
        return

    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print("  File empty")
        return

    want = ["game_date", "xwoba", "woba", "babip", "xba",
            "hardhit_percent", "barrels_per_pa_percent", "k_percent", "pa"]
    available = [c for c in want if c in rows[0]]

    dates = sorted(r["game_date"] for r in rows if r.get("game_date"))

    print(f"\n  Elly De La Cruz ({mlbam_id}) — {len(rows)} game dates")
    print(f"  Date range: {dates[0]} → {dates[-1]}")
    print(f"  Columns available: {available}")
    print()
    print(f"  {'game_date':<12}  "
          + "  ".join(f"{c:<12}" for c in available))
    print(f"  {'-'*70}")
    for row in rows[:3]:
        line = f"  {row.get('game_date',''):<12}  "
        for c in available:
            line += f"{row.get(c,''):<14}"
        print(line)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    h_res = fetch_cohort(HITTER_CSV,  "batter",  "hitter")
    p_res = fetch_cohort(PITCHER_CSV, "pitcher", "pitcher")

    total_files = h_res["fetched"] + p_res["fetched"]
    total_rows  = h_res["total_rows"] + p_res["total_rows"]
    total_skip  = h_res["skipped"]  + p_res["skipped"]
    avg_rows    = total_rows / total_files if total_files else 0

    print(f"\n{'='*60}")
    print("FETCH COMPLETE")
    print(f"{'='*60}")
    print(f"  Hitters:   {h_res['fetched']} fetched, {h_res['skipped']} skipped")
    print(f"  Pitchers:  {p_res['fetched']} fetched, {p_res['skipped']} skipped")
    print(f"  Total files:    {total_files}")
    print(f"  Total rows:     {total_rows:,}")
    print(f"  Skipped:        {total_skip}")
    print(f"  Avg rows/file:  {avg_rows:.1f}")

    print(f"\n--- Elly De La Cruz spot-check ---")
    _verify_elly(682829)  # ID from backtest_A_hitters_2025.csv


if __name__ == "__main__":
    main()
