"""
build_spotrac_contracts.py
==========================
Scrapes MLB player contract data from Spotrac via the Internet Archive
Wayback Machine CDX API. No ToS issue — fetching from web.archive.org,
not spotrac.com directly.

Usage:
    python build_spotrac_contracts.py                     # all signal players
    python build_spotrac_contracts.py --player "Aaron Judge"  # single player test
    python build_spotrac_contracts.py --dry-run           # CDX discovery only

Output:
    data/spotrac_contracts_raw.csv — raw scraped contract data (review before merging)
    Manually merge into data/contract_year_2026.csv after review.

CDX API note:
    Spotrac uses numeric ID suffixes in player URLs (e.g., aaron-judge-18499).
    CDX wildcard search discovers the correct URL pattern automatically.
    Pick latest snapshot before March 31 of the target season.
"""

import json
import re
import time
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path
import pandas as pd

BASE_DIR  = Path(__file__).parent
INPUT_CSV = BASE_DIR / "data" / "contract_year_curation_target_2026.csv"
OUTPUT    = BASE_DIR / "data" / "spotrac_contracts_raw.csv"

CDX_BASE  = "http://web.archive.org/cdx/search/cdx"
WB_BASE   = "https://web.archive.org/web"

TARGET_SEASON = 2026   # scrape snapshots from early this season
CDX_CUTOFF_BEFORE = f"{TARGET_SEASON}0401"   # latest snapshot to use

REQUEST_DELAY = 1.5    # seconds between requests (be polite to IA)
TIMEOUT       = 60     # seconds per request — CDX API needs up to 60s
CDX_FROM_RECENT = "20250101"  # prefer recent snapshots first
CDX_FROM_FALLBACK = "20230101"  # fallback if no recent snapshot

# MLB team code → Spotrac URL slug
TEAM_SLUGS: dict[str, str] = {
    "ARI": "arizona-diamondbacks", "ATL": "atlanta-braves",
    "BAL": "baltimore-orioles",    "BOS": "boston-red-sox",
    "CHC": "chicago-cubs",         "CWS": "chicago-white-sox",
    "CIN": "cincinnati-reds",      "CLE": "cleveland-guardians",
    "COL": "colorado-rockies",     "DET": "detroit-tigers",
    "HOU": "houston-astros",       "KC":  "kansas-city-royals",
    "LAA": "los-angeles-angels",   "LAD": "los-angeles-dodgers",
    "MIA": "miami-marlins",        "MIL": "milwaukee-brewers",
    "MIN": "minnesota-twins",      "NYM": "new-york-mets",
    "NYY": "new-york-yankees",     "OAK": "athletics",
    "PHI": "philadelphia-phillies","PIT": "pittsburgh-pirates",
    "SD":  "san-diego-padres",     "SF":  "san-francisco-giants",
    "SEA": "seattle-mariners",     "STL": "st-louis-cardinals",
    "TB":  "tampa-bay-rays",       "TEX": "texas-rangers",
    "TOR": "toronto-blue-jays",    "WSH": "washington-nationals",
}


# ── Utilities ────────────────────────────────────────────────────────────

def _slugify(name: str) -> str:
    """Convert player name to Spotrac slug (lowercase, hyphenated, no accents)."""
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_str = nfkd.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9\s]", "", ascii_str.lower()).strip()
    return re.sub(r"\s+", "-", slug)


def _fetch(url: str) -> bytes | None:
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (signal-fantasy-analytics/1.0)"}
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        print(f"    HTTP {e.code}: {url[:80]}")
        return None
    except Exception as e:
        print(f"    Error: {e} — {url[:80]}")
        return None


# ── CDX discovery ────────────────────────────────────────────────────────

def discover_spotrac_url(player_name: str, team_code: str = "") -> tuple[str | None, str | None]:
    """
    Find the Spotrac URL + best snapshot timestamp for a player via CDX.
    Uses team-specific URL pattern when team_code is provided (faster, no timeout).
    Returns (original_url, timestamp) or (None, None) if not found.
    """
    slug = _slugify(player_name)
    team_slug = TEAM_SLUGS.get(team_code.upper(), "") if team_code else ""

    def _cdx_query(from_date: str) -> list:
        base = f"spotrac.com/mlb/{team_slug}/{slug}*" if team_slug \
               else f"spotrac.com/mlb/*/{slug}*"
        url = (
            f"{CDX_BASE}?url={base}"
            f"&output=json&fl=original,timestamp,statuscode"
            f"&filter=statuscode:200"
            f"&from={from_date}&to={CDX_CUTOFF_BEFORE}&limit=30"
        )
        raw = _fetch(url)
        time.sleep(REQUEST_DELAY)
        if not raw:
            return []
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return []

    first_name_slug = slug.split("-")[0]

    def _extract_candidates(rows: list) -> list:
        cands = []
        for row in rows[1:]:
            if len(row) < 3:
                continue
            original, ts, sc = row[0], row[1], row[2]
            if sc != "200":
                continue
            parts = original.rstrip("/").split("/")
            if len(parts) >= 5 and first_name_slug in parts[-1]:
                cands.append((original, ts))
        return cands

    # Try recent first (2025+), fall back to 2023+
    for from_date in [CDX_FROM_RECENT, CDX_FROM_FALLBACK]:
        rows = _cdx_query(from_date)
        candidates = _extract_candidates(rows)
        if candidates:
            break

    if not candidates:
        return None, None

    # Pick most recent snapshot
    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[0]


# ── Contract page parser ─────────────────────────────────────────────────

def parse_contract_page(html: str) -> dict:
    """
    Parse the Spotrac player page for contract data.
    The contract summary lives in a <p class="currentinfo"> paragraph.
    Example: "Player signed a 10 year / $325,000,000 contract with Team,
              including $325,000,000 guaranteed, and an annual average
              salary of $32,500,000."
    """
    result = {}

    # Find the currentinfo paragraph
    m = re.search(r'class="currentinfo"[^>]*>(.*?)</p>', html, re.DOTALL | re.IGNORECASE)
    if not m:
        # Try alternate: first occurrence of "signed a X year"
        m = re.search(r'signed\s+a\s+(\d+)\s+year[^<]*\$[\d,]+', html, re.IGNORECASE)
        if not m:
            return result
        block = m.group(0)
    else:
        block = m.group(1)

    # Clean HTML tags from block
    block = re.sub(r"<[^>]+>", " ", block)
    block = re.sub(r"\s+", " ", block).strip()
    result["raw_text"] = block[:300]

    # Years
    m_yr = re.search(r"(\d+)\s+year", block, re.IGNORECASE)
    if m_yr:
        result["contract_years"] = int(m_yr.group(1))

    # Total value
    m_total = re.search(r"\$\s*([\d,]+(?:\.\d+)?)\s*(?:,000,000|M)?(?:\s+contract)?", block)
    if m_total:
        val_str = m_total.group(1).replace(",", "")
        val = float(val_str)
        if val >= 1_000:
            val /= 1_000_000   # raw dollars (e.g. 325000000 → 325.0M, or 720000 → 0.72M)
        # else already in millions (e.g. "4.0" or "32.5")
        result["contract_total_m"] = round(val, 2)

    # AAV
    m_aav = re.search(r"annual average salary of \$\s*([\d,]+)", block, re.IGNORECASE)
    if m_aav:
        aav_str = m_aav.group(1).replace(",", "")
        aav = float(aav_str)
        if aav >= 1_000:
            aav /= 1_000_000
        result["annual_salary_m"] = round(aav, 2)
    elif result.get("contract_years") and result.get("contract_total_m"):
        result["annual_salary_m"] = round(result["contract_total_m"] / result["contract_years"], 2)

    # Guaranteed
    m_guar = re.search(r"including \$\s*([\d,]+)[^,]* guaranteed", block, re.IGNORECASE)
    if m_guar:
        g_str = m_guar.group(1).replace(",", "")
        g = float(g_str)
        if g >= 1_000:
            g /= 1_000_000
        result["guaranteed_m"] = round(g, 2)

    # Try explicit "through YYYY" pattern in block
    m_thru = re.search(r"(?:through|thru|expires?|until)\s+(\d{4})", block, re.IGNORECASE)
    if m_thru:
        result["contract_end_year"] = int(m_thru.group(1))
        result["years_remaining"] = max(0, result["contract_end_year"] - TARGET_SEASON)

    return result


def _derive_end_year_from_html(html: str, contract_years: int | None,
                                snapshot_year: int) -> int | None:
    """
    Heuristic: find the last salary year in the HTML salary table.
    Scans for 4-digit years in [snapshot_year-1, snapshot_year+contract_years-1].
    The -1 lower bound handles contracts signed the prior year;
    the -1 upper bound avoids deferred/bonus year references beyond the last salary year.
    """
    if not contract_years:
        return None
    lower = snapshot_year - 1
    upper = snapshot_year + contract_years - 1
    found = sorted(set(
        int(y) for y in re.findall(r"\b(20\d{2})\b", html)
        if lower <= int(y) <= upper
    ))
    return max(found) if found else None


# ── Main ─────────────────────────────────────────────────────────────────

def scrape_player(row: pd.Series, dry_run: bool = False) -> dict | None:
    name = row["name"]
    player_id = row.get("batter_id", "") or row.get("#", "")
    player_type = row.get("type", "Hitter")
    team_code   = str(row.get("team", "")).strip()

    print(f"  {name} ({player_type}, age {int(row['age'])}, {team_code}) ...", end=" ", flush=True)

    orig_url, ts = discover_spotrac_url(name, team_code)
    if not orig_url:
        print("CDX: no snapshots found")
        return None

    snapshot_url = f"{WB_BASE}/{ts}/{orig_url}"
    print(f"CDX OK ({ts[:8]}) ...", end=" ", flush=True)

    if dry_run:
        print(f"[dry-run] would fetch: {snapshot_url[:80]}")
        return {"name": name, "spotrac_url": orig_url, "snapshot_ts": ts, "status": "dry-run"}

    html_bytes = _fetch(snapshot_url)
    time.sleep(REQUEST_DELAY)
    if not html_bytes:
        print("page fetch failed")
        return None

    html = html_bytes.decode("utf-8", errors="replace")
    contract = parse_contract_page(html)
    if not contract.get("annual_salary_m"):
        print(f"parse failed — raw: {contract.get('raw_text', '')[:80]}")
        return None

    # Derive end year from HTML table if not found in text
    if not contract.get("years_remaining") and contract.get("contract_years"):
        snap_year = int(ts[:4])
        end_yr = _derive_end_year_from_html(html, contract.get("contract_years"), snap_year)
        if end_yr:
            contract["contract_end_year"] = end_yr
            contract["years_remaining"] = max(0, end_yr - TARGET_SEASON)

    result = {
        "batter_id":        player_id,
        "name":             name,
        "type":             player_type,
        "age":              int(row["age"]),
        "signal":           row.get("signal", ""),
        "spotrac_url":      orig_url,
        "snapshot_date":    ts[:8],
        "contract_years":   contract.get("contract_years", ""),
        "contract_total_m": contract.get("contract_total_m", ""),
        "annual_salary_m":  contract.get("annual_salary_m", ""),
        "guaranteed_m":     contract.get("guaranteed_m", ""),
        "contract_end_year":contract.get("contract_end_year", ""),
        "years_remaining":  contract.get("years_remaining", ""),
        "raw_text":         contract.get("raw_text", "")[:150],
    }
    aav = contract.get("annual_salary_m", 0) or 0
    yr  = contract.get("years_remaining", "?")
    print(f"AAV=${aav:.1f}M, yrs_rem={yr}")
    return result


def main(dry_run: bool = False, single_player: str | None = None):
    print("=" * 70)
    print(f"Spotrac Wayback Machine Scraper — target season {TARGET_SEASON}")
    print(f"Mode: {'DRY-RUN (CDX only)' if dry_run else 'FULL'}")
    print("=" * 70)

    if not INPUT_CSV.exists():
        print(f"ERROR: {INPUT_CSV} not found — run previous pipeline step first")
        return

    df = pd.read_csv(INPUT_CSV)
    if "#" in df.columns:
        df = df.rename(columns={"#": "batter_id"})

    # Join team code from luck_scores.csv (hitters) and pitcher_luck_scores.csv
    luck_h = BASE_DIR / "luck_scores.csv"
    luck_p = BASE_DIR / "pitcher_luck_scores.csv"
    if luck_h.exists():
        teams_h = pd.read_csv(luck_h, usecols=["name","team"]).rename(columns={"team":"team_h"})
        df = df.merge(teams_h, on="name", how="left")
    if luck_p.exists():
        teams_p = pd.read_csv(luck_p, usecols=["name","Team"]).rename(columns={"Team":"team_p"})
        df = df.merge(teams_p, on="name", how="left")
    if "team_h" not in df.columns: df["team_h"] = ""
    if "team_p" not in df.columns: df["team_p"] = ""
    df["team"] = df.apply(
        lambda r: r["team_h"] if pd.notna(r["team_h"]) and r["team_h"] else r["team_p"], axis=1
    ).fillna("")

    if single_player:
        df = df[df["name"].str.contains(single_player, case=False, na=False)]
        if df.empty:
            print(f"Player '{single_player}' not found in input CSV")
            return

    results = []
    failed  = []

    for _, row in df.iterrows():
        result = scrape_player(row, dry_run=dry_run)
        if result:
            results.append(result)
        else:
            failed.append(row["name"])

    print()
    print(f"Results: {len(results)} success, {len(failed)} failed")
    if failed:
        print(f"Failed: {', '.join(failed[:20])}")

    if results and not dry_run:
        out_df = pd.DataFrame(results)
        out_df.to_csv(OUTPUT, index=False)
        print(f"\nSaved → {OUTPUT}")
        print("NEXT STEP: Review spotrac_contracts_raw.csv then merge into contract_year_2026.csv")
    elif dry_run and results:
        print("\nDry-run complete. Re-run without --dry-run to fetch pages.")


if __name__ == "__main__":
    import sys
    _dry   = "--dry-run" in sys.argv
    _p_idx = next((i for i, a in enumerate(sys.argv) if a == "--player"), None)
    _player = sys.argv[_p_idx + 1] if _p_idx and _p_idx + 1 < len(sys.argv) else None
    main(dry_run=_dry, single_player=_player)
