"""
merge_spotrac_contracts.py
==========================
Post-processes spotrac_contracts_raw.csv and merges valid entries into
data/contract_year_2026.csv.

Handles two known parsing artifacts from the raw CSV:
  - annual_salary_m >= 1000 → raw dollars (e.g. 720000.0) → /1_000_000
  - annual_salary_m >= 100  → partial-thousands format (e.g. 720.0) → /1_000
  - annual_salary_m < 100   → already in millions, no change

Applies a -1 year correction to years_remaining (known Wayback Machine heuristic
offset: scraper tends to find a year 1 too large in the salary table due to
deferred payment rows).

Skips pre-arb entries (normalized annual_salary_m < 1.0M).
Skips players already in contract_year_2026.csv by MLBAM ID.
Uses luck_scores.csv + pitcher_luck_scores.csv for name → MLBAM ID mapping.

Usage:
    python merge_spotrac_contracts.py [--dry-run]
"""

import sys
from pathlib import Path
import pandas as pd

BASE_DIR   = Path(__file__).parent
RAW_CSV    = BASE_DIR / "data" / "spotrac_contracts_raw.csv"
TARGET_CSV = BASE_DIR / "data" / "contract_year_2026.csv"
LUCK_H     = BASE_DIR / "luck_scores.csv"
LUCK_P     = BASE_DIR / "pitcher_luck_scores.csv"

PRE_ARB_THRESHOLD  = 1.0    # normalized AAV below this → skip (pre-arb, cohort by age)
MIN_END_YEAR       = 2026   # skip contracts that expired before 2026 season

# Players where name lookup returns the wrong MLBAM ID (e.g. same name, two players).
# Keyed on (name, age) from the scraper row → correct MLBAM ID.
MLBAM_OVERRIDES: dict[tuple, int] = {
    ("Max Muncy", 36): 571970,   # Dodgers Muncy; default lookup returns A's Muncy (691777)
}


def _normalize_aav(val) -> float:
    """Normalize annual_salary_m from raw CSV to millions."""
    if not val or str(val).strip() in ("", "nan"):
        return 0.0
    v = float(val)
    if v >= 1_000:
        return round(v / 1_000_000, 4)   # raw dollars (720000 → 0.72M)
    if v >= 100:
        return round(v / 1_000, 4)       # thousands form (720.0 → 0.72M)
    return round(v, 4)                    # already in millions


def build_id_map() -> dict[str, int]:
    """Build name → MLBAM ID map from luck score files."""
    id_map = {}
    if LUCK_H.exists():
        df = pd.read_csv(LUCK_H, usecols=["batter", "name"])
        for _, row in df.iterrows():
            id_map[row["name"].strip()] = int(row["batter"])
    if LUCK_P.exists():
        df = pd.read_csv(LUCK_P, usecols=["pitcher", "name"])
        for _, row in df.iterrows():
            id_map[row["name"].strip()] = int(row["pitcher"])
    return id_map


def fuzzy_lookup(name: str, id_map: dict) -> int | None:
    """Look up MLBAM ID by name, tolerating accent/encoding differences."""
    # Exact match first
    if name in id_map:
        return id_map[name]
    # Normalized comparison (strip accents, lowercase)
    import unicodedata
    def _normalize(s):
        nfkd = unicodedata.normalize("NFKD", s)
        return nfkd.encode("ascii", "ignore").decode("ascii").lower().strip()

    target = _normalize(name)
    for k, v in id_map.items():
        if _normalize(k) == target:
            return v
    # Last-name + first initial match
    parts = target.split()
    if len(parts) >= 2:
        last, first_initial = parts[-1], parts[0][0]
        for k, v in id_map.items():
            kp = _normalize(k).split()
            if len(kp) >= 2 and kp[-1] == last and kp[0][0] == first_initial:
                return v
    return None


def read_existing_ids() -> set[int]:
    """Return set of MLBAM IDs already in contract_year_2026.csv."""
    existing = set()
    if not TARGET_CSV.exists():
        return existing
    with open(TARGET_CSV, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(",")
            try:
                existing.add(int(parts[0]))
            except ValueError:
                pass
    return existing


def main(dry_run: bool = False):
    print("=" * 65)
    print("Spotrac Contract Merge -- spotrac_contracts_raw.csv -> contract_year_2026.csv")
    print(f"Mode: {'DRY-RUN' if dry_run else 'WRITE'}")
    print("=" * 65)

    if not RAW_CSV.exists():
        print(f"ERROR: {RAW_CSV} not found — run build_spotrac_contracts.py first")
        return

    raw = pd.read_csv(RAW_CSV)
    id_map = build_id_map()
    existing_ids = read_existing_ids()

    print(f"\nRaw CSV: {len(raw)} rows | Existing in target: {len(existing_ids)} players")
    print(f"ID map loaded: {len(id_map)} players\n")

    to_add = []
    skipped = []

    for _, row in raw.iterrows():
        name = str(row.get("name", "")).strip()
        aav_raw = row.get("annual_salary_m", "")
        yrs_raw = row.get("years_remaining", "")
        end_yr  = row.get("contract_end_year", "")

        # Normalize AAV
        aav = _normalize_aav(aav_raw)

        # Skip pre-arb
        if aav < PRE_ARB_THRESHOLD:
            skipped.append((name, f"pre-arb (AAV=${aav:.3f}M)"))
            continue

        # Skip expired contracts (end_year before current season)
        try:
            if int(float(end_yr)) < MIN_END_YEAR:
                skipped.append((name, f"expired contract (end_year={int(float(end_yr))})"))
                continue
        except (ValueError, TypeError):
            pass

        # Apply known MLBAM ID overrides (disambiguation for same-name players)
        age_val = row.get("age", 0)
        try:
            age_val = int(float(age_val))
        except (ValueError, TypeError):
            age_val = 0
        override_key = (name, age_val)
        if override_key in MLBAM_OVERRIDES:
            mlbam_id = MLBAM_OVERRIDES[override_key]
        else:
            mlbam_id = fuzzy_lookup(name, id_map)

        if not mlbam_id:
            skipped.append((name, "MLBAM ID not found"))
            continue

        # Skip if already in target
        if mlbam_id in existing_ids:
            skipped.append((name, f"already in file (ID={mlbam_id})"))
            continue

        # Use scraper's years_remaining as-is (heuristic is not uniformly off by 1)
        try:
            yrs = max(0, int(float(yrs_raw)))
        except (ValueError, TypeError):
            yrs = ""

        # Build note
        ct = row.get("contract_years", "")
        total = row.get("contract_total_m", "")
        end = row.get("contract_end_year", "")
        snap = str(row.get("snapshot_date", ""))
        note = f"Spotrac via Wayback ({snap[:4]}): {ct}yr/${total}M total; AAV=${aav:.2f}M; through {end}"

        to_add.append({
            "batter_id": mlbam_id,
            "name": name,
            "annual_salary_m": round(aav, 2),
            "years_remaining": yrs,
            "prove_it": "",
            "cohort_override": "",
            "notes": note,
        })
        print(f"  ADD: {name} (ID={mlbam_id}) AAV=${aav:.2f}M, yrs_rem={yrs}")

    print(f"\nSummary:")
    print(f"  To add:   {len(to_add)}")
    print(f"  Skipped:  {len(skipped)}")

    if skipped:
        print("\nSkipped:")
        for name, reason in skipped:
            print(f"  {name}: {reason}")

    if not to_add:
        print("\nNothing to add.")
        return

    if dry_run:
        print("\n[dry-run] No changes written.")
        return

    # Append to contract_year_2026.csv
    with open(TARGET_CSV, "a", encoding="utf-8", newline="") as f:
        f.write(f"# ── Rows below merged from spotrac_contracts_raw.csv ──\n")
        for entry in to_add:
            line = (
                f"{entry['batter_id']},"
                f"{entry['name']},"
                f"{entry['annual_salary_m']},"
                f"{entry['years_remaining']},"
                f"{entry['prove_it']},"
                f"{entry['cohort_override']},"
                f"{entry['notes']}"
            )
            f.write(line + "\n")

    print(f"\nAppended {len(to_add)} rows to {TARGET_CSV}")
    print("NEXT STEP: Verify cohort distribution with: python score_luck.py (check cohort_counts output)")


if __name__ == "__main__":
    _dry = "--dry-run" in sys.argv
    main(dry_run=_dry)
