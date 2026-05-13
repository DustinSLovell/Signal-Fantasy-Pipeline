"""fetch_fp_ros_rankings.py — FantasyPros ROS overall rankings scraper.

Data source: ecrData JSON embedded in the FP page (no JS rendering needed).
Output: data/fp_ros_rankings_2026.csv

Run: python fetch_fp_ros_rankings.py [--check]
"""

import json
import re
import unicodedata
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).parent
OUT_PATH = BASE_DIR / "data" / "fp_ros_rankings_2026.csv"

FP_URL = "https://www.fantasypros.com/mlb/rankings/ros-overall.php"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def _norm(name: str) -> str:
    """Strip accents, lowercase, collapse whitespace."""
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_str = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", ascii_str.lower()).strip()


def _fetch_html() -> str:
    req = urllib.request.Request(FP_URL, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", errors="replace")


def _parse_ecr_data(html: str) -> list[dict]:
    """Extract and parse the ecrData JSON from the FP page."""
    m = re.search(r"var ecrData\s*=\s*(\{.*?\});\s*\n", html, re.DOTALL)
    if not m:
        raise ValueError("ecrData JSON not found in FantasyPros page — page structure may have changed")
    data = json.loads(m.group(1))
    return data.get("players", [])


def _build_rows(players: list[dict]) -> list[dict]:
    rows = []
    for p in players:
        name = p.get("player_name", "")
        team = p.get("player_team_id", "")
        primary_pos = p.get("primary_position", "")
        all_positions = p.get("player_positions", primary_pos)
        rank_ecr = p.get("rank_ecr")
        pos_rank = p.get("pos_rank", "")
        rows.append({
            "player_name": name,
            "player_name_norm": _norm(name),
            "team": team,
            "primary_position": primary_pos,
            "all_positions": all_positions,
            "fp_ros_rank": rank_ecr,
            "fp_pos_rank": pos_rank,
        })
    # Sort by ECR rank
    rows.sort(key=lambda r: (r["fp_ros_rank"] is None, r["fp_ros_rank"] or 9999))
    return rows


def _write_csv(rows: list[dict]) -> None:
    cols = ["player_name", "player_name_norm", "team", "primary_position",
            "all_positions", "fp_ros_rank", "fp_pos_rank"]
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(",".join(cols) + "\n")
        for r in rows:
            vals = [str(r.get(c, "") or "") for c in cols]
            # Escape commas in names
            escaped = [f'"{v}"' if "," in v else v for v in vals]
            f.write(",".join(escaped) + "\n")
    print(f"Wrote {len(rows)} rows -> {OUT_PATH}")


def main(check: bool = False) -> None:
    print("Fetching FantasyPros ROS rankings…")
    html = _fetch_html()
    players = _parse_ecr_data(html)
    print(f"  Parsed {len(players)} players from ecrData JSON")

    rows = _build_rows(players)

    if check:
        print("\n-- SPOT CHECK (top 10) --")
        for r in rows[:10]:
            print(f"  #{r['fp_ros_rank']:>3}  {r['player_name']:<25}  {r['primary_position']:<3}  {r['team']}  ({r['fp_pos_rank']})")
        return

    _write_csv(rows)
    print("Done.")


if __name__ == "__main__":
    import sys
    main(check="--check" in sys.argv)
