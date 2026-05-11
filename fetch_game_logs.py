"""
fetch_game_logs.py
==================
Fetches per-game (hitters) and per-start (pitchers) MLB Stats API game logs
for all players with active Buy Low or Sell High signals.

Outputs:
  data/game_logs/hitter_{mlb_id}.json   — per-game stats for signaled hitters
  data/game_logs/pitcher_{mlb_id}.json  — per-start stats for signaled pitchers

Usage:
  python fetch_game_logs.py
"""

import json
import sys
import time
import urllib.request
from pathlib import Path

import pandas as pd

LUCK_H_PATH   = Path("luck_scores.csv")
LUCK_P_PATH   = Path("pitcher_luck_scores.csv")
GAME_LOGS_DIR = Path("data/game_logs")
SEASON        = 2026
DELAY         = 0.5  # seconds between API requests

ACTIVE_SIGNALS = {"Buy low", "Sell high"}

_MLB_API = (
    "https://statsapi.mlb.com/api/v1/people/{mlb_id}/stats"
    "?stats=gameLog&group={group}&season={season}"
)


def _parse_ip(ip_val) -> float:
    """Convert MLB API inningsPitched string ('6.1', '6.2') to true decimal IP."""
    try:
        s = str(ip_val)
        if "." in s:
            whole, frac = s.split(".", 1)
            return int(whole) + int(frac) / 3
        return float(s)
    except (ValueError, AttributeError, TypeError):
        return 0.0


def _fetch_splits(mlb_id: int, group: str) -> list:
    """Fetch game log from MLB Stats API. Returns list of split dicts."""
    url = _MLB_API.format(mlb_id=mlb_id, group=group, season=SEASON)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SignalFantasy/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        return data.get("stats", [{}])[0].get("splits", [])
    except Exception as exc:
        print(f"    WARNING: API error id={mlb_id} group={group}: {exc}")
        return []


def _process_hitter(splits: list) -> list:
    games = []
    for s in splits:
        stat = s.get("stat", {})
        games.append({
            "date": s.get("date", ""),
            "R":  int(stat.get("runs",         0) or 0),
            "H":  int(stat.get("hits",         0) or 0),
            "HR": int(stat.get("homeRuns",     0) or 0),
            "RBI":int(stat.get("rbi",          0) or 0),
            "SB": int(stat.get("stolenBases",  0) or 0),
            "AB": int(stat.get("atBats",       0) or 0),
        })
    return sorted(games, key=lambda g: g["date"])


def _process_pitcher(splits: list) -> list:
    games = []
    for s in splits:
        stat = s.get("stat", {})
        ip_raw = stat.get("inningsPitched", "0.0")
        games.append({
            "date":       s.get("date", ""),
            "IP":         _parse_ip(ip_raw),
            "IP_display": str(ip_raw),
            "ER":  int(stat.get("earnedRuns",   0) or 0),
            "H":   int(stat.get("hits",         0) or 0),
            "BB":  int(stat.get("baseOnBalls",  0) or 0),
            "K":   int(stat.get("strikeOuts",   0) or 0),
            "W":   int(stat.get("wins",         0) or 0),
            "SV":  int(stat.get("saves",        0) or 0),
            "HLD": int(stat.get("holds",        0) or 0),
            "GS":  int(stat.get("gamesStarted", 0) or 0),
        })
    return sorted(games, key=lambda g: g["date"])


def main():
    GAME_LOGS_DIR.mkdir(parents=True, exist_ok=True)

    if not LUCK_H_PATH.exists():
        print(f"ERROR: {LUCK_H_PATH} not found — run score_luck.py first.")
        sys.exit(1)
    if not LUCK_P_PATH.exists():
        print(f"ERROR: {LUCK_P_PATH} not found — run score_pitcher_luck.py first.")
        sys.exit(1)

    hitters  = pd.read_csv(LUCK_H_PATH)
    pitchers = pd.read_csv(LUCK_P_PATH)

    h_sig = hitters[hitters["verdict"].isin(ACTIVE_SIGNALS)][["name", "batter", "verdict"]].copy()
    p_sig = pitchers[pitchers["verdict"].isin(ACTIVE_SIGNALS)][["name", "pitcher", "verdict"]].copy()

    print(f"Rolling Performance Indicator — fetching game logs")
    print(f"  Hitters with active signal: {len(h_sig)}")
    print(f"  Pitchers with active signal: {len(p_sig)}")
    print()

    h_ok, h_empty, h_total = 0, 0, len(h_sig)
    for i, (_, row) in enumerate(h_sig.iterrows(), 1):
        mlb_id = int(row["batter"])
        name   = row["name"]
        out    = GAME_LOGS_DIR / f"hitter_{mlb_id}.json"

        splits = _fetch_splits(mlb_id, "hitting")
        games  = _process_hitter(splits)

        payload = {
            "mlb_id":  mlb_id,
            "name":    name,
            "verdict": row["verdict"],
            "games":   games,
        }
        with open(out, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

        if games:
            h_ok += 1
        else:
            h_empty += 1
            print(f"    No data: {name} ({mlb_id})")

        if i % 20 == 0:
            print(f"  Hitters: {i}/{h_total} processed...")

        time.sleep(DELAY)

    print(f"  Hitters done: {h_ok} fetched, {h_empty} empty")
    print()

    p_ok, p_empty, p_total = 0, 0, len(p_sig)
    for i, (_, row) in enumerate(p_sig.iterrows(), 1):
        mlb_id = int(row["pitcher"])
        name   = row["name"]
        out    = GAME_LOGS_DIR / f"pitcher_{mlb_id}.json"

        splits = _fetch_splits(mlb_id, "pitching")
        games  = _process_pitcher(splits)

        payload = {
            "mlb_id":  mlb_id,
            "name":    name,
            "verdict": row["verdict"],
            "games":   games,
        }
        with open(out, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

        if games:
            p_ok += 1
        else:
            p_empty += 1
            print(f"    No data: {name} ({mlb_id})")

        if i % 10 == 0:
            print(f"  Pitchers: {i}/{p_total} processed...")

        time.sleep(DELAY)

    print(f"  Pitchers done: {p_ok} fetched, {p_empty} empty")
    print(f"Game logs saved to {GAME_LOGS_DIR}/")
    print(f"Total API calls: {h_total + p_total}")


if __name__ == "__main__":
    main()
