"""
fetch_cbs_rank.py
=================
Scrapes CBS Fantasy Baseball YTD stats to derive overall rank by FPTS.
Rank = position in FPTS-sorted list across all positions (1 = highest).

Separate rank pools: hitters ranked among hitters, pitchers among pitchers.
Saves a combined table; rank within type is what matters for divergence vs ESPN.

Outputs:
  data/cbs_rank_2026.csv
    player_name, mlbam_id, cbs_rank, cbs_fpts, position, player_type, fetched_date

Side effects:
  luck_scores.csv          gains: cbs_rank (hitters)
  pitcher_luck_scores.csv  gains: cbs_rank (pitchers)

Also prints divergence report (CBS vs ESPN rank) and validates known players.

Usage:
  python fetch_cbs_rank.py            # scrape + join + report
  python fetch_cbs_rank.py --check    # probe only, no writes
"""

import argparse
import re
import sys
import time
import unicodedata
from datetime import date
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

# ── paths ─────────────────────────────────────────────────────────────────────
BASE_DIR     = Path(__file__).parent
DATA_DIR     = BASE_DIR / "data"
OUT_PATH     = DATA_DIR / "cbs_rank_2026.csv"
LUCK_H_PATH  = BASE_DIR / "luck_scores.csv"
LUCK_P_PATH  = BASE_DIR / "pitcher_luck_scores.csv"
OWN_PATH     = DATA_DIR / "player_ownership_2026.csv"

# ── CBS config ────────────────────────────────────────────────────────────────
YEAR  = 2026
DELAY = 0.8  # seconds between requests

CBS_URL = "https://www.cbssports.com/fantasy/baseball/stats/{pos}/{year}/ytd/stats/"

HITTER_POSITIONS  = ["C", "1B", "2B", "SS", "3B", "OF", "U"]
PITCHER_POSITIONS = ["SP", "RP"]

HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://www.cbssports.com/",
}

HITTER_COLS  = {"fpts": "fpts", "gp": "GP", "r": "R", "hr": "HR",
                "rbi": "RBI", "avg": "AVG", "sb": "SB"}
PITCHER_COLS = {"fpts": "fpts", "w": "W", "era": "ERA",
                "whip": "WHIP", "so": "K", "sv": "SV"}


# ── name normalisation ────────────────────────────────────────────────────────

def _norm(s: str) -> str:
    """Lowercase, strip accents, drop non-alpha-space."""
    s = unicodedata.normalize("NFD", str(s))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z ]", "", s.lower()).strip()


# ── HTML helpers (same as build_cbs_fpts.py) ─────────────────────────────────

def _short_code(header_text: str) -> str:
    m = re.match(r"^([a-z%/0-9]+)[A-Z]", header_text.strip())
    return m.group(1) if m else header_text.lower().split()[0]


def _clean(val: str):
    v = str(val).strip()
    return float("nan") if v in ("—", "", "nan") else v


def _player_name(cell) -> str:
    long_span = cell.find("span", class_="CellPlayerName--long")
    if long_span:
        link = long_span.find("a")
        if link:
            return link.get_text(strip=True)
    link = cell.find("a")
    return link.get_text(strip=True) if link else cell.get_text(strip=True)


def _player_pos(cell) -> str:
    """Extract position abbreviation from player cell (e.g. 'C', 'SP')."""
    long_span = cell.find("span", class_="CellPlayerName--long")
    if long_span:
        pos_span = long_span.find("span", class_="CellPlayerName-position")
        if pos_span:
            return pos_span.get_text(strip=True)
    return ""


# ── page fetch ────────────────────────────────────────────────────────────────

def fetch_page(url: str, retries: int = 3) -> BeautifulSoup | None:
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=25)
            if r.status_code == 200:
                return BeautifulSoup(r.text, "html.parser")
            print(f"    HTTP {r.status_code} for {url}")
            if r.status_code in (403, 429):
                wait = 30 * (attempt + 1)
                print(f"    Rate-limited — waiting {wait}s")
                time.sleep(wait)
        except Exception as e:
            print(f"    Request error ({e}), attempt {attempt+1}/{retries}")
            time.sleep(5 * (attempt + 1))
    return None


# ── table parser ──────────────────────────────────────────────────────────────

def parse_stats_table(soup: BeautifulSoup, col_map: dict) -> pd.DataFrame | None:
    table = soup.find("table")
    if not table:
        return None

    thead = table.find("thead")
    if not thead:
        return None
    header_cells = thead.find_all(["th", "td"])
    headers = [cell.get_text(strip=True) for cell in header_cells]

    col_index: dict[str, int] = {}
    for idx, h in enumerate(headers):
        code = _short_code(h) if idx > 0 else "player"
        if code in col_map:
            col_index[col_map[code]] = idx

    if not col_index:
        print(f"    No matching columns. Headers: {headers[:8]}")
        return None

    tbody = table.find("tbody")
    if not tbody:
        return None

    rows_out = []
    for tr in tbody.find_all("tr"):
        cells = tr.find_all("td")
        if not cells:
            continue
        name = _player_name(cells[0])
        pos  = _player_pos(cells[0])
        row  = {"name": name, "cbs_pos": pos}
        for col_name, idx in col_index.items():
            row[col_name] = _clean(cells[idx].get_text(strip=True)) if idx < len(cells) else float("nan")
        rows_out.append(row)

    if not rows_out:
        return None

    df = pd.DataFrame(rows_out)
    for col in col_map.values():
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


# ── scrape helpers ────────────────────────────────────────────────────────────

def _scrape_positions(positions: list[str], col_map: dict, label: str) -> pd.DataFrame:
    print(f"  {label} YTD {YEAR}:")
    frames = []
    seen_names: set[str] = set()
    seen_norm:  set[str] = set()

    for pos in positions:
        url  = CBS_URL.format(pos=pos, year=YEAR)
        soup = fetch_page(url)
        if soup is None:
            print(f"    {pos}: fetch failed, skipping")
            time.sleep(DELAY)
            continue

        df = parse_stats_table(soup, col_map)
        if df is None or df.empty:
            print(f"    {pos}: no data parsed")
            time.sleep(DELAY)
            continue

        # Dedup: keep player if we haven't seen them yet (first position = primary)
        new_rows = []
        for _, row in df.iterrows():
            key = _norm(row["name"])
            if key not in seen_norm:
                seen_norm.add(key)
                seen_names.add(row["name"])
                new_rows.append(row)

        if new_rows:
            frames.append(pd.DataFrame(new_rows))
        print(f"    {pos}: {len(df)} rows, {len(new_rows)} new (total unique: {len(seen_norm)})")
        time.sleep(DELAY)

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values("fpts", ascending=False, na_position="last").reset_index(drop=True)
    return combined


# ── ID matching ───────────────────────────────────────────────────────────────

def _build_name_id_map() -> dict[str, int]:
    """Build norm(name) → mlbam_id from player_ownership_2026.csv."""
    if not OWN_PATH.exists():
        print(f"  Warning: {OWN_PATH.name} not found — mlbam_id will be empty")
        return {}
    df = pd.read_csv(OWN_PATH, dtype={"mlbam_id": "Int64"})
    result: dict[str, int] = {}
    for _, row in df.iterrows():
        k = _norm(str(row.get("player_name", "")))
        if k and pd.notna(row.get("mlbam_id")):
            result[k] = int(row["mlbam_id"])
    return result


# ── ESPN rank map ─────────────────────────────────────────────────────────────

def _build_espn_rank_map() -> dict[str, int]:
    """Build norm(name) → espn_rank from player_ownership_2026.csv."""
    if not OWN_PATH.exists():
        return {}
    df = pd.read_csv(OWN_PATH, dtype={"rank": "Int64"})
    result: dict[str, int] = {}
    for _, row in df.iterrows():
        k = _norm(str(row.get("player_name", "")))
        if k and pd.notna(row.get("rank")):
            result[k] = int(row["rank"])
    return result


# ── main ──────────────────────────────────────────────────────────────────────

def main(dry_run: bool = False) -> None:
    today = date.today().isoformat()

    # 1. Scrape hitters
    print("\nFetching hitter stats from CBS...")
    h_df = _scrape_positions(HITTER_POSITIONS, HITTER_COLS, "Hitters")
    if h_df.empty:
        print("ERROR: No hitter data fetched. Aborting.")
        sys.exit(1)
    h_df["player_type"] = "hitter"
    h_df["cbs_rank"]    = range(1, len(h_df) + 1)

    # 2. Scrape pitchers
    print("\nFetching pitcher stats from CBS...")
    p_df = _scrape_positions(PITCHER_POSITIONS, PITCHER_COLS, "Pitchers")
    if p_df.empty:
        print("ERROR: No pitcher data fetched. Aborting.")
        sys.exit(1)
    p_df["player_type"] = "pitcher"
    p_df["cbs_rank"]    = range(1, len(p_df) + 1)

    # 3. Build combined table + attach mlbam_id
    id_map = _build_name_id_map()

    def _attach(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["name_norm"] = df["name"].apply(_norm)
        df["mlbam_id"]  = df["name_norm"].map(id_map).astype("Int64")
        df["fetched_date"] = today
        return df

    h_df = _attach(h_df)
    p_df = _attach(p_df)
    combined = pd.concat([h_df, p_df], ignore_index=True)

    out_cols = ["name", "mlbam_id", "cbs_rank", "fpts", "cbs_pos", "player_type", "fetched_date"]
    out_df = combined[out_cols].rename(columns={"name": "player_name", "fpts": "cbs_fpts",
                                                 "cbs_pos": "position"})

    # 4. Save CSV
    if not dry_run:
        DATA_DIR.mkdir(exist_ok=True)
        out_df.to_csv(OUT_PATH, index=False)
        print(f"\nSaved {len(out_df)} rows -> {OUT_PATH.name}")
        print(f"  Hitters: {(out_df['player_type']=='hitter').sum()}")
        print(f"  Pitchers: {(out_df['player_type']=='pitcher').sum()}")
    else:
        print(f"\n[dry-run] Would save {len(out_df)} rows to {OUT_PATH.name}")
        print(out_df.head(10).to_string())

    # 5. Validate known players
    print("\n--- Validation ---")
    name_to_rank = dict(zip(combined["name_norm"], zip(combined["cbs_rank"], combined["player_type"])))

    checks = [
        ("Aaron Judge",    "hitter",  lambda r: r <= 10,   "top 10"),
        ("Corbin Carroll", "hitter",  lambda r: r <= 60,   "<=60 (expect ~28-44)"),
        ("Nick Kurtz",     "hitter",  lambda r: True,       "any rank (check value)"),
        ("Paul Skenes",    "pitcher", lambda r: True,       "any rank (check value)"),
    ]
    for player_name, ptype, test, desc in checks:
        k = _norm(player_name)
        if k in name_to_rank:
            rank, found_type = name_to_rank[k]
            status = "PASS" if test(rank) else "WARN"
            print(f"  [{status}] {player_name}: CBS rank {rank} ({found_type}) — expected {desc}")
        else:
            print(f"  [MISS] {player_name}: not found in CBS data")

    # 6. Join cbs_rank into luck_scores.csv (hitters)
    if not dry_run and LUCK_H_PATH.exists():
        h_rank_map = dict(zip(h_df["name_norm"], h_df["cbs_rank"]))
        luck_h = pd.read_csv(LUCK_H_PATH)
        luck_h["name_norm"] = luck_h["name"].apply(_norm)
        luck_h["cbs_rank"] = luck_h["name_norm"].map(h_rank_map).astype("Int64")
        luck_h.drop(columns=["name_norm"], inplace=True)
        luck_h.to_csv(LUCK_H_PATH, index=False)
        matched_h = luck_h["cbs_rank"].notna().sum()
        print(f"\nJoined cbs_rank into luck_scores.csv: {matched_h}/{len(luck_h)} matched")

    # 7. Join cbs_rank into pitcher_luck_scores.csv
    if not dry_run and LUCK_P_PATH.exists():
        p_rank_map = dict(zip(p_df["name_norm"], p_df["cbs_rank"]))
        luck_p = pd.read_csv(LUCK_P_PATH)
        luck_p["name_norm"] = luck_p["name"].apply(_norm)
        luck_p["cbs_rank"] = luck_p["name_norm"].map(p_rank_map).astype("Int64")
        luck_p.drop(columns=["name_norm"], inplace=True)
        luck_p.to_csv(LUCK_P_PATH, index=False)
        matched_p = luck_p["cbs_rank"].notna().sum()
        print(f"Joined cbs_rank into pitcher_luck_scores.csv: {matched_p}/{len(luck_p)} matched")

    # 8. Divergence report: ESPN rank vs CBS rank
    print("\n--- Divergence Report: ESPN vs CBS ---")
    espn_map = _build_espn_rank_map()

    div_rows = []
    for _, row in combined.iterrows():
        k = row["name_norm"]
        cbs_r = int(row["cbs_rank"])
        ptype = row["player_type"]
        espn_r = espn_map.get(k)
        if espn_r is not None:
            div_rows.append({
                "name":        row["name"],
                "player_type": ptype,
                "espn_rank":   espn_r,
                "cbs_rank":    cbs_r,
                "divergence":  espn_r - cbs_r,   # positive = CBS ranks higher than ESPN
            })

    if div_rows:
        div_df = pd.DataFrame(div_rows).sort_values("divergence")

        print("\n  Top 10 CBS-ranked-higher-than-ESPN (divergence most positive):")
        print(f"  {'Player':<25} {'Type':<8} {'ESPN':>6} {'CBS':>6} {'Diff':>6}")
        print("  " + "-" * 55)
        for _, r in div_df.tail(10).iloc[::-1].iterrows():
            diff_str = f"+{int(r['divergence'])}"
            print(f"  {r['name']:<25} {r['player_type']:<8} {int(r['espn_rank']):>6} {int(r['cbs_rank']):>6} {diff_str:>6}")

        print(f"\n  Top 10 ESPN-ranked-higher-than-CBS (divergence most negative):")
        print(f"  {'Player':<25} {'Type':<8} {'ESPN':>6} {'CBS':>6} {'Diff':>6}")
        print("  " + "-" * 55)
        for _, r in div_df.head(10).iterrows():
            diff_str = f"{int(r['divergence'])}"
            print(f"  {r['name']:<25} {r['player_type']:<8} {int(r['espn_rank']):>6} {int(r['cbs_rank']):>6} {diff_str:>6}")

        n_matched = len(div_df)
        print(f"\n  {n_matched} players matched across ESPN + CBS for divergence analysis")
    else:
        print("  No divergence data (ESPN rank map empty or no overlap)")

    if dry_run:
        print("\n[dry-run] No files written.")


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape CBS rank and join to luck files.")
    parser.add_argument("--check", action="store_true", help="Probe only — no file writes")
    args = parser.parse_args()
    main(dry_run=args.check)
