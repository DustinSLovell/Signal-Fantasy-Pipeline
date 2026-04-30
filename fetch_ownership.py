"""
fetch_ownership.py
Fetches live ownership % from ESPN Fantasy Baseball public API.
Outputs data/player_ownership_2026.csv.

Source: ESPN public player endpoint (no auth required)
  https://lm-api-reads.fantasy.espn.com/apis/v3/games/flb/seasons/2026/players
  X-Fantasy-Filter: {"filterActive": {"value": true}}

Columns: player_name, mlbam_id, owned_pct, rank, source, fetched_date

Usage:
    python fetch_ownership.py
"""

import json
import re
import sys
import unicodedata
import urllib.request
from datetime import date
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).parent
OUT_PATH = BASE_DIR / "data" / "player_ownership_2026.csv"
LUCK_CSV = BASE_DIR / "luck_scores.csv"
SEASON   = 2026

ESPN_URL = (
    f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/flb"
    f"/seasons/{SEASON}/players?scoringPeriodId=0&view=players_wl&limit=3000"
)
ESPN_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
    "X-Fantasy-Filter": json.dumps({"filterActive": {"value": True}}),
}

_SUFFIX_RE = re.compile(r"\b(jr|sr|ii|iii|iv)\b")


def _norm(s: str) -> str:
    try:
        s = str(s).encode("latin1").decode("utf-8")
    except Exception:
        pass
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^a-z ]", "", s.lower()).strip()
    return re.sub(r" +", " ", s)


def _strip_suffix(norm: str) -> str:
    return _SUFFIX_RE.sub("", norm).strip()


def fetch_espn(timeout: int = 30) -> list:
    """Returns list of {fullName, espn_id, owned_pct} from ESPN."""
    req = urllib.request.Request(ESPN_URL, headers=ESPN_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read())
    return [
        {
            "fullName":      p["fullName"],
            "espn_id":       p["id"],
            "owned_pct":     float(p.get("ownership", {}).get("percentOwned", 0.0)),
            "injury_status": p.get("injuryStatus", "ACTIVE"),
        }
        for p in data
    ]


def build_mlbam_map() -> dict:
    """Returns {normalized_name: mlbam_id} from luck_scores.csv."""
    if not LUCK_CSV.exists():
        return {}
    df = pd.read_csv(LUCK_CSV, usecols=["batter", "name"])
    result = {}
    for _, row in df.iterrows():
        if pd.notna(row["batter"]) and pd.notna(row["name"]):
            norm = _norm(str(row["name"]))
            mlbam = int(row["batter"])
            result[norm] = mlbam
            stripped = _strip_suffix(norm)
            if stripped != norm:
                result.setdefault(stripped, mlbam)
    return result


def main() -> None:
    print("Fetching ownership data from ESPN...")

    try:
        players = fetch_espn()
    except Exception as e:
        print(f"  ESPN fetch failed: {e}")
        if OUT_PATH.exists():
            print(f"  Cached data remains at {OUT_PATH.name} — pipeline will use it")
        else:
            print("  No cached data available — ownership_tier will fall back to rank proxy")
        sys.exit(1)

    print(f"  Received {len(players):,} players from ESPN")

    # Sort by owned_pct descending → assign rank
    players.sort(key=lambda p: p["owned_pct"], reverse=True)
    for i, p in enumerate(players, 1):
        p["rank"] = i

    # MLBAM ID lookup via luck_scores.csv name matching
    mlbam_map = build_mlbam_map()
    matched = 0
    today = date.today().isoformat()

    rows = []
    for p in players:
        norm = _norm(p["fullName"])
        mlbam_id = mlbam_map.get(norm)
        if mlbam_id is None:
            mlbam_id = mlbam_map.get(_strip_suffix(norm))
        if mlbam_id is not None:
            matched += 1
        rows.append({
            "player_name":   p["fullName"],
            "mlbam_id":      int(mlbam_id) if mlbam_id is not None else "",
            "owned_pct":     round(p["owned_pct"], 2),
            "rank":          p["rank"],
            "source":        "ESPN",
            "fetched_date":  today,
            "injury_status": p.get("injury_status", "ACTIVE"),
        })

    df_out = pd.DataFrame(rows)
    OUT_PATH.parent.mkdir(exist_ok=True)
    df_out.to_csv(OUT_PATH, index=False)

    n_any  = (df_out["owned_pct"] > 0).sum()
    n_60p  = (df_out["owned_pct"] >= 60).sum()
    n_40p  = ((df_out["owned_pct"] >= 40) & (df_out["owned_pct"] < 60)).sum()
    n_20p  = ((df_out["owned_pct"] >= 20) & (df_out["owned_pct"] < 40)).sum()

    print(f"  Saved {len(df_out):,} players -> {OUT_PATH.name}")
    print(f"  Widely rostered (>=60%):        {n_60p}")
    print(f"  Commonly rostered (40-60%):     {n_40p}")
    print(f"  Deep league relevant (20-40%):  {n_20p}")
    print(f"  Some ownership (<20%):          {n_any - n_60p - n_40p - n_20p}")
    print(f"  MLBAM matched: {matched}/{len(rows)} players via luck_scores.csv")


if __name__ == "__main__":
    main()
