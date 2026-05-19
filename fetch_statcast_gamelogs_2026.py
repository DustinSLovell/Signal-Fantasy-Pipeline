"""
fetch_statcast_gamelogs_2026.py
Pull 2026 game-by-game Statcast data from Baseball Savant.
Fetches all signaled (non-Neutral) players from luck_scores.csv + pitcher_luck_scores.csv.
Output: data/statcast_gamelogs_2026/hitter_{id}.csv  and  pitcher_{id}.csv

Caching: skips files that were already fetched today (mtime == today).
Re-fetches once per day to pick up new games.
"""
import csv
import os
import time
import urllib.request
from datetime import date
from pathlib import Path

BASE_URL  = "https://baseballsavant.mlb.com/statcast_search/csv"
OUT_DIR   = Path("data/statcast_gamelogs_2026")
DELAY_SEC = 1.5

HITTER_CSV  = "luck_scores.csv"
PITCHER_CSV = "pitcher_luck_scores.csv"
NEUTRAL     = {"neutral", ""}


def _build_url(mlbam_id: int, player_type: str) -> str:
    lookup_key = (
        "batters_lookup%5B%5D" if player_type == "batter"
        else "pitchers_lookup%5B%5D"
    )
    params = (
        f"hfSea=2026%7C"
        f"&player_type={player_type}"
        f"&{lookup_key}={mlbam_id}"
        f"&group_by=name-date"
        f"&min_pas=1"
    )
    return f"{BASE_URL}?{params}"


def _fetch_player(mlbam_id: int, player_type: str, out_path: Path) -> int:
    url = _build_url(mlbam_id, player_type)
    req = urllib.request.Request(url, headers={
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
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
    return len(lines) - 1


def _fetched_today(path: Path) -> bool:
    if not path.exists() or path.stat().st_size < 200:
        return False
    mtime = date.fromtimestamp(path.stat().st_mtime)
    return mtime == date.today()


def _load_signaled(csv_path: str, id_col: str) -> list[tuple[str, int]]:
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            verdict = r.get("verdict", "").strip().lower()
            if verdict in NEUTRAL:
                continue
            try:
                name = r.get("name", str(r.get(id_col, "")))
                rows.append((name, int(r[id_col])))
            except (KeyError, ValueError):
                pass
    return rows


def fetch_cohort(
    csv_path: str, id_col: str, player_type: str, prefix: str
) -> dict:
    players = _load_signaled(csv_path, id_col)
    total   = len(players)
    results = {"fetched": 0, "cached": 0, "skipped": 0, "total_rows": 0}

    print(f"\n{'='*60}")
    print(f"Fetching {total} {player_type}s from {csv_path}")
    print(f"{'='*60}")

    for n, (name, mlbam_id) in enumerate(players, 1):
        out_path = OUT_DIR / f"{prefix}_{mlbam_id}.csv"
        print(f"  [{n:>3}/{total}] {name} ({mlbam_id})... ", end="", flush=True)

        if _fetched_today(out_path):
            row_count = sum(1 for _ in out_path.open()) - 1
            print(f"cached today ({row_count} rows)")
            results["cached"]     += 1
            results["total_rows"] += row_count
            continue

        row_count = _fetch_player(mlbam_id, player_type, out_path)
        if row_count > 0:
            print(f"{row_count} rows")
            results["fetched"]    += 1
            results["total_rows"] += row_count
        else:
            print("no data")
            results["skipped"] += 1

        time.sleep(DELAY_SEC)

    return results


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"2026 Statcast game log fetch  [{date.today()}]")
    print("Scope: non-Neutral signaled players only (caches daily)")

    h_res = fetch_cohort(HITTER_CSV,  "batter",  "batter",  "hitter")
    p_res = fetch_cohort(PITCHER_CSV, "pitcher", "pitcher", "pitcher")

    total_files = h_res["fetched"] + h_res["cached"] + p_res["fetched"] + p_res["cached"]
    total_rows  = h_res["total_rows"] + p_res["total_rows"]

    print(f"\n{'='*60}")
    print("FETCH COMPLETE")
    print(f"{'='*60}")
    print(f"  Hitters:   {h_res['fetched']} fetched, {h_res['cached']} cached, "
          f"{h_res['skipped']} skipped")
    print(f"  Pitchers:  {p_res['fetched']} fetched, {p_res['cached']} cached, "
          f"{p_res['skipped']} skipped")
    print(f"  Total files available: {total_files}")
    print(f"  Total game rows:       {total_rows:,}")


if __name__ == "__main__":
    main()
