#!/usr/bin/env python3
"""
fetch_fantasypros_ownership.py
Fetches cross-platform ownership % and ROS consensus rankings from FantasyPros.

Ownership source: fantasypros.com/mlb/stats/hitters.php + pitchers.php
  - fp_ownership  : consensus % (ESPN+Yahoo+CBS blend — the "Rost%" column)
  - fp_espn_own   : ESPN only
  - fp_yahoo_own  : Yahoo only
  - fp_vbr_rank   : YTD Value-Based Rank (first col of stats page — backward-looking)

ROS rank source: fantasypros.com/mlb/projections/ros-{hitters,sp,rp}.php
  - fp_ros_rank   : row position = FP consensus ROS rank (1 = best projected)
                    Hitters ranked among hitters; SP among SPs; RP among RPs.

Output: player_ownership_2026.csv gains columns:
  fp_ownership, fp_espn_own, fp_yahoo_own, fp_vbr_rank, fp_ros_rank, fp_fetched

Usage:
  python fetch_fantasypros_ownership.py          # update ownership CSV
  python fetch_fantasypros_ownership.py --check  # probe only, no writes
"""

import argparse
import csv
import re
import sys
import unicodedata
import urllib.request
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).parent
OUT_PATH = BASE_DIR / "data" / "player_ownership_2026.csv"
LUCK_H   = BASE_DIR / "luck_scores.csv"
LUCK_P   = BASE_DIR / "pitcher_luck_scores.csv"

# Stats pages (ownership + VBR)
HITTER_URL  = "https://www.fantasypros.com/mlb/stats/hitters.php"
PITCHER_URL = "https://www.fantasypros.com/mlb/stats/pitchers.php"

# ROS projections pages (row order = consensus ROS rank)
ROS_HITTER_URL = "https://www.fantasypros.com/mlb/projections/ros-hitters.php"
ROS_SP_URL     = "https://www.fantasypros.com/mlb/projections/ros-sp.php"
ROS_RP_URL     = "https://www.fantasypros.com/mlb/projections/ros-rp.php"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}


# ---------------------------------------------------------------------------
# Name normalisation
# ---------------------------------------------------------------------------

def _norm(s: str) -> str:
    """Lowercase, strip accents, drop non-alpha-space characters."""
    s = unicodedata.normalize("NFD", str(s))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z ]", "", s.lower()).strip()


def _norm_strip_suffix(s: str) -> str:
    """Like _norm() but also strips trailing generational suffixes (jr, sr, ii, iii, iv, v).
    Used when matching our pipeline names (which strip suffixes) against ESPN/FP names (which keep them).
    """
    s = _norm(s)
    s = re.sub(r"\s+\b(jr|sr|ii|iii|iv|v)\b$", "", s).strip()
    return re.sub(r"\s+", " ", s)


# Maps our normalized pipeline name → FP/ESPN normalized name when they differ by more
# than accents/capitalization (i.e. suffix differences _norm_strip_suffix cannot catch
# in both directions).  Keys are _norm() of our name, values are _norm() of FP's name.
_FP_ALIASES: dict[str, str] = {
    # Generational suffixes kept by FP/ESPN, stripped in our Statcast pipeline
    "bobby witt":         "bobby witt jr",
    "vladimir guerrero":  "vladimir guerrero jr",
    "jazz chisholm":      "jazz chisholm jr",
    "michael harris":     "michael harris ii",
    "ronald acuna":       "ronald acuna jr",
    "fernando tatis":     "fernando tatis jr",
    "daniel lynch":       "daniel lynch iv",
}


# ---------------------------------------------------------------------------
# HTTP fetch
# ---------------------------------------------------------------------------

def _fetch_html(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Stats page parser (ownership + VBR)
# ---------------------------------------------------------------------------

def parse_fp_page(html: str) -> list[dict]:
    """
    Extract per-player ownership and VBR from a FantasyPros stats page.
    Each <tr class="mpb-player-XXXX"> contains:
      - VBR numeric rank in first <td>
      - fp-player-name="..." attribute
      - <td class="own consensus-own">NN%</td>
      - <td class="own yahoo-own">NN%</td>
      - <td class="own espn-own">NN%</td>
    """
    rows = []
    player_blocks = re.split(r'(?=<tr class="mpb-player-\d+)', html)
    for block in player_blocks:
        name_m = re.search(r'fp-player-name="([^"]+)"', block)
        if not name_m:
            continue
        name = name_m.group(1).strip()

        team_m = re.search(r'<small>\(<a[^>]+>([A-Z]{2,3})</a>\s*-\s*([^)]+)\)', block)
        team = team_m.group(1).strip() if team_m else ""
        pos  = team_m.group(2).strip() if team_m else ""

        def _own(cls):
            m = re.search(rf'class="own {cls}">(\d+)%', block)
            return float(m.group(1)) if m else float("nan")

        consensus = _own("consensus-own")
        espn_own  = _own("espn-own")
        yahoo_own = _own("yahoo-own")

        if not name or (consensus != consensus):  # skip if no consensus value
            continue

        # VBR: first <td> containing only digits before the player name cell
        # The VBR column is the first column in the stats table
        vbr = None
        vbr_m = re.search(r'<td[^>]*>\s*(\d{1,4})\s*</td>', block)
        if vbr_m:
            candidate = int(vbr_m.group(1))
            # Sanity: VBR should be a reasonable rank (1–500)
            if 1 <= candidate <= 500:
                vbr = candidate

        rows.append({
            "name":         name,
            "name_norm":    _norm(name),
            "team":         team,
            "pos":          pos,
            "fp_ownership": consensus,
            "fp_espn_own":  espn_own,
            "fp_yahoo_own": yahoo_own,
            "fp_vbr_rank":  vbr,
        })
    return rows


# ---------------------------------------------------------------------------
# ROS projections page parser (rank by row order)
# ---------------------------------------------------------------------------

def parse_fp_ros_page(html: str) -> list[dict]:
    """
    Extract player names from a FP ROS projections page.
    Row order (1-indexed) = fp_ros_rank.

    FP projections pages use the same mpb-player-XXXX / fp-player-name
    pattern as the stats pages.
    """
    rows = []

    # Primary pattern: same mpb-player row structure as stats pages
    player_blocks = re.split(r'(?=<tr class="mpb-player-\d+)', html)
    for block in player_blocks:
        name_m = re.search(r'fp-player-name="([^"]+)"', block)
        if not name_m:
            continue
        name = name_m.group(1).strip()
        if name:
            rows.append({"name": name, "name_norm": _norm(name)})

    # Fallback: look for player name links if mpb-player pattern absent
    if not rows:
        for m in re.finditer(
            r'<a[^>]+class="[^"]*player-name[^"]*"[^>]*>([^<]+)</a>', html
        ):
            name = m.group(1).strip()
            if name and len(name) > 3:
                rows.append({"name": name, "name_norm": _norm(name)})

    # Assign rank based on row position (1 = best)
    for i, r in enumerate(rows):
        r["fp_ros_rank"] = i + 1

    return rows


# ---------------------------------------------------------------------------
# Load our player universe for match reporting
# ---------------------------------------------------------------------------

def _load_our_names(path: Path, name_col: str = "name") -> dict[str, str]:
    """Return {norm_name: raw_name} from a luck scores CSV."""
    out = {}
    if not path.exists():
        return out
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            raw = row.get(name_col, "").strip()
            if raw:
                out[_norm(raw)] = raw
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true",
                        help="Probe pages only; report match rate without writing")
    args = parser.parse_args()

    print("=" * 60)
    print("FantasyPros Ownership + ROS Rank Fetch")
    print("=" * 60)

    # ── Fetch stats pages (ownership + VBR) ──────────────────────────────────
    fp_players: list[dict] = []
    for label, url in [("hitters", HITTER_URL), ("pitchers", PITCHER_URL)]:
        print(f"\n  Fetching {label} stats page...")
        try:
            html = _fetch_html(url)
            rows = parse_fp_page(html)
            n_vbr = sum(1 for r in rows if r["fp_vbr_rank"] is not None)
            print(f"  Parsed {len(rows)} {label} — "
                  f"{n_vbr} with VBR rank")
            if rows:
                sample = rows[0]
                print(f"  Sample: {sample['name']} {sample['team']} "
                      f"consensus={sample['fp_ownership']:.0f}%  "
                      f"VBR={sample['fp_vbr_rank']}")
            fp_players.extend(rows)
        except Exception as e:
            print(f"  ERROR fetching {label}: {e}")
            sys.exit(1)

    # Build ownership+VBR lookup: norm_name → row
    fp_lookup: dict[str, dict] = {}
    for row in fp_players:
        nk = row["name_norm"]
        if nk not in fp_lookup or row["fp_ownership"] > fp_lookup[nk]["fp_ownership"]:
            fp_lookup[nk] = row

    print(f"\n  Total unique FP players (stats): {len(fp_lookup)}")

    # ── Fetch ROS projections pages (fp_ros_rank) ─────────────────────────────
    ros_lookup: dict[str, int] = {}  # norm_name → fp_ros_rank
    ros_pages = [
        ("hitters ROS", ROS_HITTER_URL),
        ("SP ROS",      ROS_SP_URL),
        ("RP ROS",      ROS_RP_URL),
    ]
    total_ros = 0
    for label, url in ros_pages:
        print(f"\n  Fetching {label} projections page...")
        try:
            html = _fetch_html(url)
            rows = parse_fp_ros_page(html)
            print(f"  Parsed {len(rows)} players (rank 1={rows[0]['name'] if rows else '?'})")
            for row in rows:
                nk = row["name_norm"]
                if nk not in ros_lookup:   # first-seen wins (hitters before pitchers)
                    ros_lookup[nk] = row["fp_ros_rank"]
            total_ros += len(rows)
        except Exception as e:
            print(f"  WARNING: could not fetch {label}: {e}")

    print(f"\n  Total unique ROS-ranked players: {len(ros_lookup)}")

    # ── Match against our universe ────────────────────────────────────────────
    our_h = _load_our_names(LUCK_H)
    our_p = _load_our_names(LUCK_P)
    our_all = {**our_h, **our_p}

    own_matched  = [(nk, fp_lookup[nk]) for nk in our_all if nk in fp_lookup]
    ros_matched  = [(nk, ros_lookup[nk]) for nk in our_all if nk in ros_lookup]
    unmatched_own = [name for nk, name in our_h.items() if nk not in fp_lookup]

    print(f"\n  Our universe : {len(our_h)} hitters + {len(our_p)} pitchers "
          f"= {len(our_all)} total")
    print(f"  FP ownership matched : {len(own_matched):3d} / {len(our_all)} "
          f"({100*len(own_matched)/max(1,len(our_all)):.1f}%)")
    print(f"  FP ROS rank matched  : {len(ros_matched):3d} / {len(our_all)} "
          f"({100*len(ros_matched)/max(1,len(our_all)):.1f}%)")

    # Compare ROS rank coverage to old 40-row CSV
    old_csv = BASE_DIR / "data" / "fantasy_rankings_hitters_2026.csv"
    old_count = 0
    if old_csv.exists():
        with open(old_csv, newline="", encoding="utf-8") as f:
            old_count = sum(1 for _ in csv.DictReader(f))
    ros_h_matched = sum(1 for nk in our_h if nk in ros_lookup)
    print(f"\n  fp_rank coverage:")
    print(f"    Old manual CSV   : {old_count} hitters")
    print(f"    New ROS scrape   : {ros_h_matched} hitters (vs {len(our_h)} in our universe)")

    # Ownership distribution
    matched_pcts = [fp_lookup[nk]["fp_ownership"] for nk, _ in own_matched]
    if matched_pcts:
        under35 = sum(1 for p in matched_pcts if p < 35)
        print(f"\n  Ownership distribution (matched):")
        print(f"    <35%  : {under35}  |  35-75%: "
              f"{sum(1 for p in matched_pcts if 35<=p<75)}  |  >=75%: "
              f"{sum(1 for p in matched_pcts if p>=75)}")

    # Top 20 hitters by fp_ros_rank — sanity check
    print("\n  Top 20 hitters by fp_ros_rank:")
    h_ranked = [(ros_lookup[nk], our_h[nk]) for nk in our_h if nk in ros_lookup]
    h_ranked.sort()
    print(f"  {'Rk':>3}  Name")
    for rank, name in h_ranked[:20]:
        print(f"  {rank:>3}  {name}")

    if args.check:
        print("\n  [--check mode] No files written.")
        return

    # ── Update player_ownership_2026.csv ──────────────────────────────────────
    if not OUT_PATH.exists():
        print(f"\n  ERROR: {OUT_PATH} not found — run fetch_ownership.py first")
        sys.exit(1)

    with open(OUT_PATH, newline="", encoding="utf-8") as f:
        existing = list(csv.DictReader(f))

    new_cols = ["fp_ownership", "fp_espn_own", "fp_yahoo_own",
                "fp_vbr_rank", "fp_ros_rank", "fp_fetched"]

    updated_own = 0
    updated_ros = 0
    today = str(date.today())

    for row in existing:
        nk = _norm(row.get("player_name", ""))
        # Alias fallback: if our pipeline name strips a suffix that FP/ESPN keeps,
        # try the alias key before giving up.  _norm_strip_suffix covers the reverse
        # direction (FP name has suffix, our lookup key does not).
        nk_alias = _FP_ALIASES.get(nk, _FP_ALIASES.get(_norm_strip_suffix(nk), ""))

        # Ownership + VBR
        fp = fp_lookup.get(nk) or (fp_lookup.get(nk_alias) if nk_alias else None)
        if fp:
            row["fp_ownership"] = f"{fp['fp_ownership']:.1f}"
            row["fp_espn_own"]  = (f"{fp['fp_espn_own']:.1f}"
                                   if fp["fp_espn_own"] == fp["fp_espn_own"] else "")
            row["fp_yahoo_own"] = (f"{fp['fp_yahoo_own']:.1f}"
                                   if fp["fp_yahoo_own"] == fp["fp_yahoo_own"] else "")
            row["fp_vbr_rank"]  = str(fp["fp_vbr_rank"]) if fp["fp_vbr_rank"] else ""
            row["fp_fetched"]   = today
            updated_own += 1
        else:
            for k in new_cols:
                row.setdefault(k, "")

        # ROS rank
        ros_rank = ros_lookup.get(nk)
        if ros_rank is None and nk_alias:
            ros_rank = ros_lookup.get(nk_alias)
        if ros_rank is not None:
            row["fp_ros_rank"] = str(ros_rank)
            updated_ros += 1
        else:
            row.setdefault("fp_ros_rank", "")

    base_fields = list(existing[0].keys()) if existing else []
    all_fields  = base_fields + [c for c in new_cols if c not in base_fields]

    with open(OUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=all_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(existing)

    print(f"\n  Updated {updated_own}/{len(existing)} rows with FP ownership/VBR")
    print(f"  Updated {updated_ros}/{len(existing)} rows with FP ROS rank")
    print(f"  Saved  : {OUT_PATH}")

    # ── Hidden gem preview ────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("HIDDEN GEM PREVIEW (fp_ownership < 35%, wOBA > .330)")
    print("=" * 60)
    import math

    if LUCK_H.exists():
        with open(LUCK_H, newline="", encoding="utf-8") as f:
            hitters = list(csv.DictReader(f))

        def _f(v):
            try:
                x = float(v); return x if math.isfinite(x) else float("nan")
            except Exception:
                return float("nan")

        gems = []
        for h in hitters:
            nk = _norm(h.get("name", ""))
            fp = fp_lookup.get(nk)
            if not fp:
                continue
            fp_own = fp["fp_ownership"]
            woba   = _f(h.get("wOBA"))
            xwoba  = _f(h.get("xwOBA"))
            gap    = _f(h.get("xwOBA_gap"))
            luck   = _f(h.get("luck_score"))
            pa     = _f(h.get("PA"))
            if (fp_own < 35 and woba > 0.330 and gap > -0.020
                    and luck > -0.085 and pa >= 75):
                gems.append((woba, h.get("name"), h.get("team"),
                             fp_own, woba, xwoba, gap, luck, int(pa),
                             h.get("verdict", "")))

        gems.sort(reverse=True)
        print(f"\n  {'Name':<25} {'Tm':<4} {'FP Own':>7} {'wOBA':>6} "
              f"{'xwOBA':>6} {'Gap':>6} {'Luck':>7} {'PA':>4}  Signal")
        print("  " + "-" * 84)
        for woba, name, team, fp_own, w, xw, gap, luck, pa, verdict in gems[:5]:
            print(f"  {name:<25} {str(team):<4} {fp_own:>6.1f}%  {w:.3f}  "
                  f"{xw:.3f}  {gap:>+.3f}  {luck:>+.3f}  {pa:>4}  [{verdict}]")
        if not gems:
            print("  No candidates found.")


if __name__ == "__main__":
    main()
