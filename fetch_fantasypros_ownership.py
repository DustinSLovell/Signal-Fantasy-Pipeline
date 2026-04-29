#!/usr/bin/env python3
"""
fetch_fantasypros_ownership.py
Fetches cross-platform ownership % from FantasyPros MLB stats pages.

Source: fantasypros.com/mlb/stats/hitters.php + pitchers.php
  - consensus-own : weighted average across ESPN + Yahoo + CBS (the "Rost%" column)
  - espn-own      : ESPN only
  - yahoo-own     : Yahoo only
  (No separate CBS column — CBS is folded into the consensus average)

Output: data/player_ownership_2026.csv gains two new columns:
  fp_ownership   — FantasyPros consensus % (ESPN+Yahoo+CBS blend)
  fp_espn_own    — ESPN as reported by FP (cross-check vs our ESPN fetch)
  fp_yahoo_own   — Yahoo ownership %

Match strategy: name normalization (lowercase, strip accents, drop punctuation),
same pattern used elsewhere in the pipeline.

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

HITTER_URL  = "https://www.fantasypros.com/mlb/stats/hitters.php"
PITCHER_URL = "https://www.fantasypros.com/mlb/stats/pitchers.php"

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


# ---------------------------------------------------------------------------
# FantasyPros page parser
# ---------------------------------------------------------------------------

def _fetch_html(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def parse_fp_page(html: str) -> list[dict]:
    """
    Extract per-player ownership from a FantasyPros stats page.
    Each <tr> contains:
      fp-player-name="..." attribute
      team in <small>(<a ...>TEAM</a> - POS)</small>
      <td class="own consensus-own">NN%</td>
      <td class="own yahoo-own">NN%</td>
      <td class="own espn-own">NN%</td>
    """
    rows = []
    # Split on player rows (each has class mpb-player-XXXX)
    player_blocks = re.split(r'(?=<tr class="mpb-player-\d+)', html)
    for block in player_blocks:
        name_m = re.search(r'fp-player-name="([^"]+)"', block)
        if not name_m:
            continue
        name = name_m.group(1).strip()

        team_m = re.search(r'<small>\(<a[^>]+>([A-Z]{2,3})</a>\s*-\s*([^)]+)\)', block)
        team = team_m.group(1).strip() if team_m else ""
        pos  = team_m.group(2).strip() if team_m else ""

        # Extract ownership values
        def _own(cls):
            m = re.search(rf'class="own {cls}">(\d+)%', block)
            return float(m.group(1)) if m else float("nan")

        consensus = _own("consensus-own")
        espn_own  = _own("espn-own")
        yahoo_own = _own("yahoo-own")

        if not name or (consensus != consensus):  # skip if no consensus value
            continue

        rows.append({
            "name":      name,
            "name_norm": _norm(name),
            "team":      team,
            "pos":       pos,
            "fp_ownership":  consensus,
            "fp_espn_own":   espn_own,
            "fp_yahoo_own":  yahoo_own,
        })
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
    print("FantasyPros Ownership Fetch")
    print("=" * 60)

    # --- Fetch both pages ---
    fp_players: list[dict] = []
    for label, url in [("hitters", HITTER_URL), ("pitchers", PITCHER_URL)]:
        print(f"\n  Fetching {label} page...")
        try:
            html = _fetch_html(url)
            rows = parse_fp_page(html)
            print(f"  Parsed {len(rows)} {label} with ownership data")
            if rows:
                print(f"  Sample: {rows[0]['name']} {rows[0]['team']} "
                      f"consensus={rows[0]['fp_ownership']:.0f}%  "
                      f"ESPN={rows[0]['fp_espn_own']:.0f}%  "
                      f"Yahoo={rows[0]['fp_yahoo_own']:.0f}%")
            fp_players.extend(rows)
        except Exception as e:
            print(f"  ERROR fetching {label}: {e}")
            sys.exit(1)

    # Build lookup: norm_name → row (keep highest fp_ownership if duplicate names)
    fp_lookup: dict[str, dict] = {}
    for row in fp_players:
        nk = row["name_norm"]
        if nk not in fp_lookup or row["fp_ownership"] > fp_lookup[nk]["fp_ownership"]:
            fp_lookup[nk] = row

    print(f"\n  Total unique FP players: {len(fp_lookup)}")

    # --- Match against our universe ---
    our_h = _load_our_names(LUCK_H)
    our_p = _load_our_names(LUCK_P)
    our_all = {**our_h, **our_p}

    matched   = [(nk, fp_lookup[nk]) for nk in our_all if nk in fp_lookup]
    unmatched = [name for nk, name in our_all.items() if nk not in fp_lookup]

    print(f"\n  Our universe : {len(our_h)} hitters + {len(our_p)} pitchers "
          f"= {len(our_all)} total")
    print(f"  FP matched   : {len(matched)} / {len(our_all)} "
          f"({100*len(matched)/max(1,len(our_all)):.1f}%)")
    print(f"  Unmatched    : {len(unmatched)}")
    if unmatched:
        print(f"  Sample unmatched: {unmatched[:10]}")

    # Ownership range among matched players
    matched_pcts = [fp_lookup[nk]["fp_ownership"] for nk, _ in matched]
    if matched_pcts:
        under35 = sum(1 for p in matched_pcts if p < 35)
        print(f"\n  Matched ownership distribution:")
        print(f"    <35%  : {under35} players  ({100*under35/len(matched_pcts):.1f}%)")
        print(f"    35-75%: {sum(1 for p in matched_pcts if 35<=p<75)} players")
        print(f"    >=75% : {sum(1 for p in matched_pcts if p>=75)} players")
        print(f"    min={min(matched_pcts):.0f}%  max={max(matched_pcts):.0f}%  "
              f"median={sorted(matched_pcts)[len(matched_pcts)//2]:.0f}%")

    if args.check:
        print("\n  [--check mode] No files written.")
        return

    # --- Update player_ownership_2026.csv ---
    if not OUT_PATH.exists():
        print(f"\n  ERROR: {OUT_PATH} not found — run fetch_ownership.py first")
        sys.exit(1)

    with open(OUT_PATH, newline="", encoding="utf-8") as f:
        existing = list(csv.DictReader(f))

    # Add FP columns to existing rows
    fp_col_defaults = {
        "fp_ownership": "",
        "fp_espn_own":  "",
        "fp_yahoo_own": "",
        "fp_fetched":   str(date.today()),
    }

    updated = 0
    for row in existing:
        nk = _norm(row.get("player_name", ""))
        fp = fp_lookup.get(nk)
        if fp:
            row["fp_ownership"] = f"{fp['fp_ownership']:.1f}"
            row["fp_espn_own"]  = f"{fp['fp_espn_own']:.1f}"  if fp["fp_espn_own"] == fp["fp_espn_own"] else ""
            row["fp_yahoo_own"] = f"{fp['fp_yahoo_own']:.1f}" if fp["fp_yahoo_own"] == fp["fp_yahoo_own"] else ""
            row["fp_fetched"]   = str(date.today())
            updated += 1
        else:
            for k, v in fp_col_defaults.items():
                row.setdefault(k, v)

    # Determine fieldnames (preserve original + add FP columns if new)
    base_fields = list(existing[0].keys()) if existing else []
    fp_fields = ["fp_ownership", "fp_espn_own", "fp_yahoo_own", "fp_fetched"]
    all_fields = base_fields + [f for f in fp_fields if f not in base_fields]

    with open(OUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=all_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(existing)

    print(f"\n  Updated {updated}/{len(existing)} rows with FP ownership data")
    print(f"  Saved  : {OUT_PATH}")

    # --- Quick hidden gem preview ---
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
