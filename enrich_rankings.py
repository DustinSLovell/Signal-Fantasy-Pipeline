"""enrich_rankings.py — Post-scoring column enrichment for luck CSVs.

Reads three new data sources and merges into luck_scores.csv and
pitcher_luck_scores.csv without touching Layer 1 scoring logic.

Columns updated:
  fp_rank    — overwritten from fp_ros_rankings_2026.csv (FP ROS consensus rank)
  owned_pct  — updated from cbs_ownership_2026.csv where CBS has data;
               keeps existing ESPN value for non-trending players
  cbs_rank   — added/updated from cbs_ros_rankings_{hitters,pitchers}_2026.csv
               (position rank within CBS; blank if player not ranked)

Run: python enrich_rankings.py
"""

import csv
import re
import unicodedata
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"

HITTER_CSV   = BASE_DIR / "luck_scores.csv"
PITCHER_CSV  = BASE_DIR / "pitcher_luck_scores.csv"

FP_ROS_PATH  = DATA_DIR / "fp_ros_rankings_2026.csv"
CBS_OWN_PATH = DATA_DIR / "cbs_ownership_2026.csv"
CBS_H_PATH   = DATA_DIR / "cbs_ros_rankings_hitters_2026.csv"
CBS_P_PATH   = DATA_DIR / "cbs_ros_rankings_pitchers_2026.csv"


def _norm(name: str) -> str:
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_str = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", ascii_str.lower()).strip()


SUFFIX_RE = re.compile(r"\s+(jr|sr|ii|iii|iv)\.?\s*$")


def _abbrev_norm(name_norm: str) -> str:
    """'fernando tatis jr.' -> 'f. tatis jr.' (matches CBS abbreviated format)."""
    parts = name_norm.split()
    if len(parts) < 2:
        return name_norm
    return parts[0][0] + ". " + " ".join(parts[1:])


def _extra_keys(key: str) -> list[str]:
    """Return suffix-stripped variant as fallback matching key (avoids Jr. misses)."""
    stripped = SUFFIX_RE.sub("", key).strip()
    return [stripped] if stripped != key else []


def _load_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _write_csv(rows: list[dict], path: Path, fieldnames: list[str]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


# ─── Build lookup tables ─────────────────────────────────────────────────────

def build_fp_lk() -> dict[str, int]:
    """name_norm -> fp_ros_rank (overall ECR rank). Also indexes without Jr./Sr. suffix."""
    rows = _load_csv(FP_ROS_PATH)
    lk = {}
    for r in rows:
        key = r.get("player_name_norm", "").strip()
        rank = r.get("fp_ros_rank", "")
        if key and rank:
            try:
                v = int(float(rank))
                lk[key] = v
                for alt in _extra_keys(key):
                    lk.setdefault(alt, v)
            except ValueError:
                pass
    print(f"  FP ROS: {len(lk)} entries loaded")
    return lk


def build_cbs_own_lk() -> dict[str, str]:
    """name_norm -> owned_pct (decimal 0-1)."""
    rows = _load_csv(CBS_OWN_PATH)
    lk = {}
    for r in rows:
        key = r.get("player_name_norm", "").strip()
        pct = r.get("owned_pct", "").strip()
        if key and pct:
            lk[key] = pct
    print(f"  CBS ownership: {len(lk)} entries loaded")
    return lk


def build_cbs_ros_lk(path: Path) -> dict[str, int]:
    """abbrev_norm -> cbs_rank (position rank). Also indexes without Jr./Sr. suffix."""
    rows = _load_csv(path)
    lk = {}
    for r in rows:
        key = r.get("player_name_abbrev_norm", "").strip()
        rank = r.get("cbs_rank", "")
        if key and rank:
            try:
                v = int(float(rank))
                lk[key] = v
                for alt in _extra_keys(key):
                    lk.setdefault(alt, v)
            except ValueError:
                pass
    print(f"  CBS ROS ({path.name}): {len(lk)} entries loaded")
    return lk


# ─── Enrichment ──────────────────────────────────────────────────────────────

def _get_name(row: dict, *candidates: str) -> str:
    """Return first non-empty name field from candidates."""
    for col in candidates:
        v = row.get(col, "")
        if v:
            return v
    return ""


def enrich(
    csv_path: Path,
    fp_lk: dict,
    cbs_own_lk: dict,
    cbs_ros_lk: dict,
    name_cols: tuple[str, ...],
) -> tuple[int, int, int]:
    """Enrich one CSV in-place. Returns (fp_updated, own_updated, cbs_added) counts."""
    rows = _load_csv(csv_path)
    if not rows:
        print(f"  {csv_path.name}: not found or empty — skipping")
        return 0, 0, 0

    # Ensure cbs_rank column exists (may not be in original CSV)
    fieldnames = list(rows[0].keys())
    if "cbs_rank" not in fieldnames:
        fieldnames.append("cbs_rank")

    fp_n = own_n = cbs_n = 0

    for row in rows:
        raw_name = _get_name(row, *name_cols)
        nn = _norm(raw_name)
        abn = _abbrev_norm(nn)

        # fp_rank: update from FP ROS if match found
        if nn in fp_lk:
            row["fp_rank"] = fp_lk[nn]
            fp_n += 1

        # owned_pct: use CBS where available; keep existing otherwise
        if nn in cbs_own_lk:
            row["owned_pct"] = cbs_own_lk[nn]
            own_n += 1

        # cbs_rank: add from CBS ROS (position rank)
        cbs_val = cbs_ros_lk.get(abn)
        if cbs_val is not None:
            row["cbs_rank"] = cbs_val
            cbs_n += 1
        elif "cbs_rank" not in row:
            row["cbs_rank"] = ""

    _write_csv(rows, csv_path, fieldnames)
    return fp_n, own_n, cbs_n


# ─── Main ────────────────────────────────────────────────────────────────────

def main() -> None:
    print("Building lookup tables...")
    fp_lk      = build_fp_lk()
    cbs_own_lk = build_cbs_own_lk()
    cbs_h_lk   = build_cbs_ros_lk(CBS_H_PATH)
    cbs_p_lk   = build_cbs_ros_lk(CBS_P_PATH)

    print("\nEnriching hitters (luck_scores.csv)...")
    fp_n, own_n, cbs_n = enrich(
        HITTER_CSV, fp_lk, cbs_own_lk, cbs_h_lk, ("name",)
    )
    print(f"  fp_rank updated: {fp_n}  |  owned_pct (CBS): {own_n}  |  cbs_rank added: {cbs_n}")

    print("\nEnriching pitchers (pitcher_luck_scores.csv)...")
    fp_n, own_n, cbs_n = enrich(
        PITCHER_CSV, fp_lk, cbs_own_lk, cbs_p_lk, ("player_name", "name")
    )
    print(f"  fp_rank updated: {fp_n}  |  owned_pct (CBS): {own_n}  |  cbs_rank added: {cbs_n}")

    print("\nDone.")


if __name__ == "__main__":
    main()
