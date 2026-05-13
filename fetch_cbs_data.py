"""fetch_cbs_data.py — CBS Fantasy Baseball data scraper using Playwright.

Scrapes three CBS public pages (no auth required):
  1. Ownership %:      /trends/added/{pos}/ + /trends/dropped/{pos}/
                       → data/cbs_ownership_2026.csv
  2. ROS hitter ranks: /rankings/roto/{pos}/ (C 1B 2B SS 3B OF DH)
                       → data/cbs_ros_rankings_hitters_2026.csv
  3. ROS pitcher ranks: /rankings/roto/{pos}/ (SP RP)
                        → data/cbs_ros_rankings_pitchers_2026.csv

Run:
  python fetch_cbs_data.py                  # all three
  python fetch_cbs_data.py --ownership      # ownership only
  python fetch_cbs_data.py --rankings       # rankings only
  python fetch_cbs_data.py --check          # run + spot check
  python fetch_cbs_data.py --rankings --check

Requires: pip install playwright && playwright install chromium
"""

import re
import time
import unicodedata
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    raise SystemExit(
        "Playwright not installed.\n"
        "Run: pip install playwright && playwright install chromium"
    )

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
CBS_BASE = "https://www.cbssports.com/fantasy/baseball"

OWN_OUT   = DATA_DIR / "cbs_ownership_2026.csv"
ROS_H_OUT = DATA_DIR / "cbs_ros_rankings_hitters_2026.csv"
ROS_P_OUT = DATA_DIR / "cbs_ros_rankings_pitchers_2026.csv"

OWNERSHIP_POSITIONS = ["all", "C", "1B", "2B", "SS", "3B", "OF", "U", "SP", "RP"]
HITTER_POSITIONS    = ["C", "1B", "2B", "SS", "3B", "OF", "DH"]
PITCHER_POSITIONS   = ["SP", "RP"]

PAGE_DELAY = 2.0   # seconds between page requests
RANK_WAIT  = 5.0   # extra settle time for JS-heavy rankings pages
TREND_WAIT = 3.0   # settle time for trends pages


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _norm(name: str) -> str:
    """Strip accents, lowercase, collapse whitespace."""
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_str = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", ascii_str.lower()).strip()


def _parse_player_cell(text: str) -> tuple[str, str, str]:
    """'Spencer Jones CF  NYY' → ('Spencer Jones', 'CF', 'NYY')."""
    parts = text.split()
    if len(parts) < 3:
        return text.strip(), "", ""
    return " ".join(parts[:-2]), parts[-2], parts[-1]


def _pct_to_float(raw: str) -> str:
    """'62%' or '62' -> '62.0' (percentage 0-100 scale, matching ESPN owned_pct format)."""
    s = raw.replace("%", "").strip()
    try:
        return str(round(float(s), 2))
    except ValueError:
        return ""


def _write_csv(rows: list[dict], cols: list[str], out_path: Path) -> None:
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(",".join(cols) + "\n")
        for r in rows:
            vals = [str(r.get(c, "") or "") for c in cols]
            escaped = [f'"{v}"' if "," in v else v for v in vals]
            f.write(",".join(escaped) + "\n")
    print(f"  Wrote {len(rows)} rows -> {out_path}")


# ─── 1. CBS Ownership ────────────────────────────────────────────────────────

def _scrape_trends_page(page, url: str, flag: str) -> list[dict]:
    """Scrape one added/dropped trends page; return list of player rows."""
    print(f"    {url}")
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        time.sleep(TREND_WAIT)
    except Exception as exc:
        print(f"      SKIP (load error): {exc}")
        return []

    rows_out = []
    for row in page.query_selector_all("table tbody tr"):
        cells = row.query_selector_all("td")
        if len(cells) < 3:
            continue
        player_raw = cells[0].inner_text().strip()
        prev_raw   = cells[1].inner_text().strip()
        curr_raw   = cells[2].inner_text().strip()
        name, pos, team = _parse_player_cell(player_raw)
        if not name:
            continue
        rows_out.append({
            "player_name":      name,
            "player_name_norm": _norm(name),
            "position":         pos,
            "team":             team,
            "owned_pct":        _pct_to_float(curr_raw),
            "prev_owned_pct":   _pct_to_float(prev_raw),
            "add_drop_flag":    flag,
        })
    return rows_out


def fetch_ownership(page) -> None:
    print("\n[1] Fetching CBS ownership data...")
    # keyed by player_name_norm; "added" entries win over "dropped"
    seen: dict[str, dict] = {}

    for pos in OWNERSHIP_POSITIONS:
        for flag in ("added", "dropped"):
            url = f"{CBS_BASE}/trends/{flag}/{pos}/"
            for r in _scrape_trends_page(page, url, flag):
                key = r["player_name_norm"]
                if key not in seen or flag == "added":
                    seen[key] = r
            time.sleep(PAGE_DELAY)

    rows = sorted(seen.values(), key=lambda r: float(r["owned_pct"] or 0), reverse=True)
    cols = ["player_name", "player_name_norm", "position", "team",
            "owned_pct", "prev_owned_pct", "add_drop_flag"]
    _write_csv(rows, cols, OWN_OUT)


# ─── 2. CBS ROS Rankings ─────────────────────────────────────────────────────

def _parse_first_rankings_block(body_text: str) -> list[tuple[int, str]]:
    """
    Return [(rank, abbrev_name), …] for the first (consensus) rankings block.
    CBS pages contain multiple expert lists separated by 'RK  PLAYER' headers —
    we stop at the second such header.
    """
    results: list[tuple[int, str]] = []
    in_block = False

    for line in body_text.splitlines():
        stripped = line.strip()

        if not in_block:
            if re.match(r"RK\s+PLAYER", stripped, re.IGNORECASE):
                in_block = True
        else:
            # Row pattern: "1\tF. Tatis Jr." or "1  F. Tatis Jr."
            m = re.match(r"^(\d+)[\t ]+([A-Z]\. .+)", line)
            if m:
                results.append((int(m.group(1)), m.group(2).strip()))
            elif results and re.match(r"RK\s+PLAYER", stripped, re.IGNORECASE):
                # Second expert block header — consensus block is complete
                break

    return results


def _scrape_rankings_page(page, url: str, pos: str) -> list[dict]:
    """Scrape one CBS rankings page; return list of player rows."""
    print(f"    {url}")
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        time.sleep(RANK_WAIT)
    except Exception as exc:
        print(f"      SKIP (load error): {exc}")
        return []

    body = page.inner_text("body")
    pairs = _parse_first_rankings_block(body)
    print(f"      -> {len(pairs)} players for {pos}")
    return [
        {
            "cbs_rank":                rank,
            "player_name_abbrev":      abbrev,
            "player_name_abbrev_norm": _norm(abbrev),
            "position":                pos,
        }
        for rank, abbrev in pairs
    ]


def fetch_ros_rankings(page, positions: list[str], out_path: Path, label: str) -> None:
    print(f"\n[2] Fetching CBS ROS rankings ({label})...")
    # keyed by abbrev_norm; keep best (lowest) rank across position pages
    best: dict[str, dict] = {}

    for pos in positions:
        url = f"{CBS_BASE}/rankings/roto/{pos}/"
        for r in _scrape_rankings_page(page, url, pos):
            key = r["player_name_abbrev_norm"]
            if key not in best or r["cbs_rank"] < best[key]["cbs_rank"]:
                best[key] = r
        time.sleep(PAGE_DELAY)

    rows = sorted(best.values(), key=lambda r: r["cbs_rank"])
    cols = ["cbs_rank", "player_name_abbrev", "player_name_abbrev_norm", "position"]
    _write_csv(rows, cols, out_path)


# ─── Spot check ──────────────────────────────────────────────────────────────

def _spot_check() -> None:
    import csv
    print("\n-- SPOT CHECK --")

    if OWN_OUT.exists():
        with open(OWN_OUT, encoding="utf-8") as f:
            own_rows = list(csv.DictReader(f))
        print(f"\nOwnership ({len(own_rows)} players):")
        checks = [
            ("Manny Machado",       "expect 90%+"),
            ("Fernando Tatis Jr.",  "expect 95%+"),
            ("Ezequiel Tovar",      "expect <15%"),
            ("Cade Smith",          "expect 85%+"),
        ]
        for name, note in checks:
            norm = _norm(name)
            hit = next((r for r in own_rows if r["player_name_norm"] == norm), None)
            if hit:
                pct = float(hit["owned_pct"] or 0) * 100
                flag = hit.get("add_drop_flag", "?")
                print(f"  {hit['player_name']:<28} {pct:>5.1f}%  ({flag})  [{note}]")
            else:
                print(f"  {name:<28} NOT FOUND  [{note}]")

    for label, path, checks in [
        (
            "Hitter ROS",
            ROS_H_OUT,
            [("F. Tatis Jr.", "expect top 30"), ("J. Ramirez", "expect top 5"),
             ("M. Machado", "expect top 60")],
        ),
        (
            "Pitcher ROS",
            ROS_P_OUT,
            [("J. Luzardo", "expect top 60 SP"), ("Z. Wheeler", "expect top 10 SP"),
             ("C. Burnes", "expect top 15 SP")],
        ),
    ]:
        if path.exists():
            with open(path, encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            print(f"\n{label} ({len(rows)} players):")
            for abbrev, note in checks:
                norm = _norm(abbrev)
                hit = next((r for r in rows if r["player_name_abbrev_norm"] == norm), None)
                if hit:
                    print(f"  {hit['player_name_abbrev']:<28} CBS #{hit['cbs_rank']:<5}  [{note}]")
                else:
                    print(f"  {abbrev:<28} NOT FOUND  [{note}]")


# ─── Main ────────────────────────────────────────────────────────────────────

def main(run_ownership: bool = True, run_rankings: bool = True, check: bool = False) -> None:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )
        page = ctx.new_page()
        try:
            if run_ownership:
                fetch_ownership(page)
            if run_rankings:
                fetch_ros_rankings(page, HITTER_POSITIONS, ROS_H_OUT, "hitters")
                fetch_ros_rankings(page, PITCHER_POSITIONS, ROS_P_OUT, "pitchers")
        finally:
            browser.close()

    if check:
        _spot_check()
    print("\nDone.")


if __name__ == "__main__":
    import sys
    args = set(sys.argv[1:])
    check       = "--check"    in args
    own_only    = "--ownership" in args and "--rankings" not in args
    rank_only   = "--rankings"  in args and "--ownership" not in args
    main(
        run_ownership=not rank_only,
        run_rankings=not own_only,
        check=check,
    )
