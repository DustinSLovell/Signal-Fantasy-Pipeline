"""
compute_career_quality.py
Computes Career Quality Score (CQS) for hitters using 3-year xwOBA, hard hit rate,
and career PA reliability. Used to apply trade value floors to proven players
so they are not buried by early-season sample-size noise.

CQS formula (0-100):
    xwOBA 3yr percentile rank  × 0.40   (ranked within 2000+ PA universe)
  + hard_hit% 3yr percentile rank × 0.30 (ranked within 2000+ PA universe)
  + career PA reliability weight  × 0.30
  → × 100
  → × conversion_rate modifier (if applicable)

Percentile ranking universe (Adjustment 1):
  - Players with career PA >= 2,000 are ranked against each other
  - Players with career PA < 2,000 are ranked against their own pool
  - All players get a CQS score; only the universe differs

Tier label PA gates (minimum career PA to receive each tier label):
  Superstar:         career PA >= 1,500  (rate stats unreliable below this)
  Established Star:  career PA >= 800
  Solid Contributor: career PA >= 400
  Developing:        assigned when career PA falls below the tier's floor,
                     regardless of rate-stat score

Floor eligibility (Adjustment 2 — career PA gates, with cascade + consecutive seasons):
  Superstar floor (60 units):       requires career PA >= 3,000
  Established Star floor (40 units): requires career PA >= 2,000
  Solid Contributor floor (20 units): requires career PA >= 1,000
  Consecutive seasons expansion:    career PA >= 800 AND 2+ seasons with 400+ PA
                                    → qualifies for Solid Contributor floor (20 units)
                                    captures established starters who don't yet have 1,000 career PA
  Below thresholds: CQS computed, no floor applied

Availability modifier (Adjustment 4 — applied after floor is computed):
  Uses per-year PA from Statcast data to estimate games-played availability.
  Full season ≈ 650 PA for a healthy starter; availability ≈ PA / (4.1 × 162).
  Recovery override: if most recent season ≥ 90% availability → treat as fully available.
  Otherwise: 3-year average availability rate.
  Floor modifiers:
    Availability >= 85%: full floor
    Availability 70–84%: floor × 0.75 (25% reduction)
    Availability 55–69%: floor × 0.50 (50% reduction)
    Availability  < 55%: floor = 0  → "Injury risk — floor protection removed"

Conversion rate modifier (Adjustment 3):
  conversion_rate = actual wOBA / xwOBA, computed per year
  Persistent underperformer (< 0.90 for 2+ consecutive years):  CQS × 0.85
  Persistent overperformer  (3yr average > 1.10):               CQS × 1.10
  Neutral: no modifier

Usage:
    python compute_career_quality.py          # dry run, prints results
    python compute_career_quality.py --write  # writes data/career_quality.json
"""

import argparse
import io
import json
import os
import sys

import numpy as np
import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

try:
    import pybaseball
    from pybaseball import statcast_batter_expected_stats, statcast_batter_exitvelo_barrels
    pybaseball.cache.enable()
except ImportError:
    sys.exit("pybaseball not installed — run: pip install pybaseball")

ROOT = os.path.dirname(os.path.abspath(__file__))
CAREER_STATS_PATH = os.path.join(ROOT, "data", "career_stats.json")
PLAYER_VALUES_PATH = os.path.join(ROOT, "data", "player_values.json")
OUTPUT_PATH = os.path.join(ROOT, "data", "career_quality.json")

YEARS = [2023, 2024, 2025]
MIN_PA = 20

# Approximate PA per game for availability estimation (league average ~4.1 PA/G)
_PA_PER_GAME   = 4.1
_FULL_GAMES    = 162
_PA_FULL_SZN   = _PA_PER_GAME * _FULL_GAMES   # ≈ 664 PA = nominal full season

# ---------------------------------------------------------------------------
# Career PA reliability weight
# ---------------------------------------------------------------------------
PA_KNOTS  = [0, 500, 1000, 2000, 3000]
PA_WEIGHTS = [0.40, 0.40, 0.65, 0.85, 1.00]

def career_pa_weight(career_pa: float) -> float:
    return float(np.interp(career_pa, PA_KNOTS, PA_WEIGHTS))

# ---------------------------------------------------------------------------
# Tier / floor eligibility
# ---------------------------------------------------------------------------

# Minimum career PA required to receive each tier label.
# Players whose rate stats qualify for a tier but lack sufficient PA history
# fall back to "Developing" — the sample is too small to trust the rates.
TIER_LABEL_PA = {
    "Superstar":         1500,
    "Established Star":   800,
    "Solid Contributor":  400,
}

def cqs_tier(cqs: float, career_pa: float = 0) -> str:
    """Assign tier label based on CQS score, gated by minimum career PA."""
    if cqs >= 80 and career_pa >= TIER_LABEL_PA["Superstar"]:
        return "Superstar"
    if cqs >= 60 and career_pa >= TIER_LABEL_PA["Established Star"]:
        return "Established Star"
    if cqs >= 40 and career_pa >= TIER_LABEL_PA["Solid Contributor"]:
        return "Solid Contributor"
    return "Developing"

def cqs_tier_rate_only(cqs: float) -> str:
    """Original tier assignment by rate stats alone (no PA gate). Used for before/after comparison."""
    if cqs >= 80:  return "Superstar"
    if cqs >= 60:  return "Established Star"
    if cqs >= 40:  return "Solid Contributor"
    return "Developing"

# Adj 2: floor requires minimum career PA per tier
TIER_FLOOR_PA = {
    "Superstar":        (60, 3000),
    "Established Star": (40, 2000),
    "Solid Contributor":(20, 1000),
    "Developing":       ( 0,    0),
}

def seasons_above_400pa(player_id_str: str, per_year_df: pd.DataFrame) -> int:
    """Count seasons in YEARS where the player had >= 400 PA."""
    try:
        pid_int = int(float(player_id_str))
    except (ValueError, TypeError):
        return 0
    mask = per_year_df["player_id"].apply(lambda x: int(float(x))) == pid_int
    return int((per_year_df.loc[mask, "pa"] >= 400).sum())


def compute_availability_score(player_id_str: str, per_year_df: pd.DataFrame) -> float:
    """
    Estimates availability from per-year PA (no extra API calls).
    availability per season ≈ (PA / 4.1) / 162, capped at 1.0.

    Recovery override: if most recent qualifying season shows >= 90% availability,
    return 1.0 (player has demonstrated full health regardless of prior seasons).
    Otherwise: 3-year average availability rate.

    Defaults to 1.0 when no per-year data is found (avoids penalising historical
    or recently-debuted players who lack data).
    """
    try:
        pid_int = int(float(player_id_str))
    except (ValueError, TypeError):
        return 1.0
    mask = per_year_df["player_id"].apply(lambda x: int(float(x))) == pid_int
    pdata = per_year_df.loc[mask].sort_values("year").copy()
    if pdata.empty:
        return 1.0
    pdata["avail"] = (pdata["pa"] / _PA_FULL_SZN).clip(0.0, 1.0)
    recent_avail = pdata.iloc[-1]["avail"]
    if recent_avail >= 0.90:
        return 1.0  # demonstrated full health in most recent season
    return float(pdata["avail"].mean())


def effective_floor(tier: str, career_pa: float, seasons_400: int = 0) -> int:
    """
    Standard floor: checks assigned tier's PA gate first.
    Consecutive seasons expansion: career PA >= 800 AND 2+ seasons with 400+ PA
    → qualifies for Solid Contributor floor (20 units) even if standard gate unmet.
    Does NOT cascade tiers: a Superstar who misses the 3000-PA gate is checked
    against the consecutive-seasons path, not automatically given lower-tier floors
    (to avoid giving Established Star players unearned Solid Contributor protection).
    """
    floor_val, min_pa = TIER_FLOOR_PA.get(tier, (0, 0))
    if career_pa >= min_pa:
        return floor_val
    # Consecutive seasons expansion
    if career_pa >= 800 and seasons_400 >= 2:
        return TIER_FLOOR_PA["Solid Contributor"][0]  # 20 units
    return 0


def apply_availability_modifier(base_floor: int, avail: float) -> tuple[int, str | None]:
    """
    Returns (modified_floor, availability_flag).
    avail: 0.0–1.0 from compute_availability_score().
    """
    if base_floor == 0:
        return 0, None
    if avail >= 0.85:
        return base_floor, None
    if avail >= 0.70:
        return int(base_floor * 0.75), "Availability: 25% floor reduction"
    if avail >= 0.55:
        return int(base_floor * 0.50), "Availability: 50% floor reduction"
    return 0, "Injury risk — floor protection removed"

# ---------------------------------------------------------------------------
# Data fetch — xwOBA + actual wOBA (both from same endpoint)
# ---------------------------------------------------------------------------
def fetch_expected_stats_all_years() -> tuple[pd.DataFrame, dict]:
    """Returns (per-year df, name_map {pid_str -> display_name})."""
    frames = []
    name_map: dict[str, str] = {}

    for yr in YEARS:
        print(f"  fetching expected stats {yr}...", flush=True)
        df = statcast_batter_expected_stats(yr, minPA=MIN_PA)

        # Build name map from all years (earlier years fill gaps)
        name_col = "last_name, first_name" if "last_name, first_name" in df.columns else None
        if name_col:
            for _, row in df.iterrows():
                pid_str = str(int(row["player_id"]))
                if pid_str not in name_map:
                    raw = str(row[name_col])
                    # "Last, First" → "First Last"
                    parts = [p.strip() for p in raw.split(",")]
                    name_map[pid_str] = f"{parts[1]} {parts[0]}" if len(parts) == 2 else raw

        keep = [c for c in ["player_id", "est_woba", "woba", "pa"] if c in df.columns]
        sub = df[keep].copy()
        sub["year"] = yr
        sub = sub.rename(columns={"est_woba": "xwoba"})
        frames.append(sub)

    return pd.concat(frames, ignore_index=True), name_map


def fetch_hhr_all_years() -> pd.DataFrame:
    frames = []
    for yr in YEARS:
        print(f"  fetching hard hit% {yr}...", flush=True)
        df = statcast_batter_exitvelo_barrels(yr, minBBE=10)
        if "ev95percent" not in df.columns:
            print(f"    WARNING: ev95percent missing {yr} — skipping", flush=True)
            continue
        sub = df[["player_id", "ev95percent"]].copy()
        sub["year"] = yr
        sub = sub.rename(columns={"ev95percent": "hard_hit_pct"})
        frames.append(sub)
    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------------------
# Conversion rate modifier (Adj 3)
# ---------------------------------------------------------------------------
def compute_conversion_flags(per_year_df: pd.DataFrame, career_stats: dict) -> pd.DataFrame:
    """
    Returns df with player_id, conversion_flag, conversion_note columns.
    Only applied to hitters with career PA >= 2,000 (per spec).
    conversion_flag: 'underperformer', 'overperformer', or None
    """
    df = per_year_df.copy()
    df["player_id_str"] = df["player_id"].astype(str).str.split(".").str[0]
    df["career_pa"] = df["player_id_str"].map(
        lambda pid: career_stats.get(pid, {}).get("career_pa", 0) or 0
    )
    # Gate: only 2000+ PA players, only rows with valid PA (>=50) and wOBA (>0.10)
    df = df[df["career_pa"] >= 2000].copy()
    df = df.dropna(subset=["xwoba", "woba"])
    df = df[(df["xwoba"] > 0.10) & (df["woba"] > 0.10) & (df["pa"] >= 50)].copy()
    df["conv_rate"] = df["woba"] / df["xwoba"]

    rows = []
    for pid, grp in df.groupby("player_id"):
        grp = grp.sort_values("year")
        rates = dict(zip(grp["year"], grp["conv_rate"]))

        # Adj A: underperformer = conv_rate < 0.90 for 2+ consecutive years
        under_pairs = 0
        for y1, y2 in [(2023, 2024), (2024, 2025)]:
            r1 = rates.get(y1)
            r2 = rates.get(y2)
            if r1 is not None and r2 is not None:
                if r1 < 0.90 and r2 < 0.90:
                    under_pairs += 1

        avg_rate = grp["conv_rate"].mean()

        # Adj B: overperformer = 3-year AVERAGE conversion_rate > 1.10
        #        (requires at least 2 seasons of data to guard against single-year outliers)
        is_overperformer = len(grp) >= 2 and avg_rate > 1.10

        flag = None
        note = None
        if under_pairs >= 1:
            flag = "underperformer"
            note = "Statcast underperformer — results persistently lag underlying metrics"
        elif is_overperformer:
            flag = "overperformer"
            note = "Results overperformer — consistently extracts more value than Statcast suggests"

        # Per-year rates for display
        rates_str = " | ".join(
            f"{yr}: {rates[yr]:.2f}" for yr in sorted(rates)
        )
        rows.append({
            "player_id": str(int(pid)),
            "conversion_flag": flag,
            "conversion_note": note,
            "avg_conv_rate": round(avg_rate, 3),
            "conv_rates_by_year": rates_str,
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 3-year aggregate
# ---------------------------------------------------------------------------
def compute_3yr_averages(per_year_df: pd.DataFrame, hhr_df: pd.DataFrame) -> pd.DataFrame:
    # PA-weighted xwOBA
    def wtd_xwoba(g):
        valid = g.dropna(subset=["xwoba"])
        if valid.empty:
            return pd.Series({"xwoba_3yr": np.nan, "total_pa_3yr": g["pa"].sum()})
        return pd.Series({
            "xwoba_3yr": np.average(valid["xwoba"], weights=valid["pa"]),
            "total_pa_3yr": g["pa"].sum(),
        })

    xwoba_agg = per_year_df.groupby("player_id").apply(wtd_xwoba).reset_index()

    # Simple average HHR
    hhr_agg = (
        hhr_df.groupby("player_id")["hard_hit_pct"]
        .mean().reset_index()
        .rename(columns={"hard_hit_pct": "hhr_3yr"})
    )

    merged = pd.merge(xwoba_agg, hhr_agg, on="player_id", how="outer")
    merged["player_id"] = merged["player_id"].astype(str)
    return merged


# ---------------------------------------------------------------------------
# Compute CQS with all adjustments
# ---------------------------------------------------------------------------
def compute_cqs(
    agg: pd.DataFrame,
    career_stats: dict,
    conv_flags: pd.DataFrame,
    per_year_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    df = agg.copy()

    df["career_pa"] = df["player_id"].map(
        lambda pid: career_stats.get(pid, {}).get("career_pa", 0) or 0
    )
    df["pa_weight"] = df["career_pa"].apply(career_pa_weight)

    # Adj 1: separate percentile universes
    high_pa = df["career_pa"] >= 2000
    low_pa  = ~high_pa

    for mask in [high_pa, low_pa]:
        sub_idx = df.index[mask & df["xwoba_3yr"].notna()]
        if len(sub_idx) > 0:
            df.loc[sub_idx, "xwoba_pctile"] = (
                df.loc[sub_idx, "xwoba_3yr"].rank(pct=True)
            )
        sub_idx_h = df.index[mask & df["hhr_3yr"].notna()]
        if len(sub_idx_h) > 0:
            df.loc[sub_idx_h, "hhr_pctile"] = (
                df.loc[sub_idx_h, "hhr_3yr"].rank(pct=True)
            )

    df["xwoba_pctile"] = df["xwoba_pctile"].fillna(0.0)
    df["hhr_pctile"]   = df["hhr_pctile"].fillna(0.0)

    df["cqs_raw"] = (
        df["xwoba_pctile"] * 0.40
        + df["hhr_pctile"]  * 0.30
        + df["pa_weight"]   * 0.30
    ) * 100

    # Adj 3: merge conversion flags and apply modifier
    df = pd.merge(df, conv_flags[["player_id", "conversion_flag", "conversion_note",
                                   "avg_conv_rate", "conv_rates_by_year"]],
                  on="player_id", how="left")

    multiplier = np.ones(len(df))
    multiplier[df["conversion_flag"] == "underperformer"] = 0.85
    multiplier[df["conversion_flag"] == "overperformer"]  = 1.10
    df["cqs_modifier"] = multiplier
    df["cqs"] = (df["cqs_raw"] * multiplier).clip(upper=100)

    # Tier label: rate-stat score gated by minimum career PA
    df["tier_rate_only"] = df["cqs"].apply(cqs_tier_rate_only)  # pre-gate (for comparison)
    df["tier"] = df.apply(lambda r: cqs_tier(r["cqs"], r["career_pa"]), axis=1)

    # Adj 2: floor gated by career PA + consecutive seasons expansion
    if per_year_df is not None:
        df["seasons_400pa"] = df["player_id"].apply(
            lambda pid: seasons_above_400pa(str(pid), per_year_df)
        )
    else:
        df["seasons_400pa"] = 0

    df["floor_base"] = df.apply(
        lambda r: effective_floor(r["tier"], r["career_pa"], int(r["seasons_400pa"])), axis=1
    )

    # Adj 4: availability modifier — applied only when floor_base > 0
    if per_year_df is not None:
        df["availability"] = df["player_id"].apply(
            lambda pid: compute_availability_score(str(pid), per_year_df)
        )
    else:
        df["availability"] = 1.0

    def _apply_avail(row):
        mod_floor, flag = apply_availability_modifier(int(row["floor_base"]), float(row["availability"]))
        return pd.Series({"floor": mod_floor, "availability_flag": flag})

    avail_results = df.apply(_apply_avail, axis=1)
    df["floor"]            = avail_results["floor"]
    df["availability_flag"] = avail_results["availability_flag"]

    return df


# ---------------------------------------------------------------------------
# Validation + reporting
# ---------------------------------------------------------------------------
VALIDATION_IDS = {
    "596019": "Francisco Lindor",
    "608070": "Jose Ramirez",
    "592450": "Aaron Judge",
}

def print_validation(cqs_df: pd.DataFrame, player_values: list, name_map: dict) -> None:
    tv_lookup: dict[str, float] = {}
    for rec in player_values:
        pid = str(rec.get("id", rec.get("player_id", "")))
        l1 = rec.get("league1_value", 0) or 0
        l2 = rec.get("league2_value", 0) or 0
        tv_lookup[pid] = max(l1, l2)

    # Supplement name_map from player_values
    for rec in player_values:
        pid = str(rec.get("id", ""))
        if pid and pid not in name_map:
            name_map[pid] = rec.get("name", pid)

    # Build reverse name lookup for Walker / Grisham
    name_to_pid: dict[str, str] = {v.lower(): k for k, v in name_map.items()}

    def find_pid_by_name(target: str) -> str | None:
        t = target.lower()
        for n, pid in name_to_pid.items():
            if all(part in n for part in t.split()):
                return pid
        return None

    print("\n" + "=" * 100)
    print("CAREER QUALITY SCORE — VALIDATION (all 3 adjustments applied)")
    print("=" * 100)
    hdr = f"{'Player':<22} {'CQS':>5} {'Mod':>5} {'Tier':<18} {'Floor':>6} {'MaxTV':>7} " \
          f"{'xwOBA3':>7} {'HHR3':>6} {'ConvRate':>9} {'CareerPA':>9}"
    print(hdr)
    print("-" * 100)

    shown: set[str] = set()

    def print_row(name: str, pid: str) -> None:
        row = cqs_df[cqs_df["player_id"] == pid]
        if row.empty:
            print(f"  {name:<22}  NOT FOUND")
            return
        r = row.iloc[0]
        max_tv = tv_lookup.get(pid, 0)
        flag = r.get("conversion_flag")
        has_flag = isinstance(flag, str) and flag
        mod_str   = f"{r['cqs_modifier']:.2f}" if has_flag else "  —  "
        conv_val  = r.get("avg_conv_rate", float("nan"))
        conv_str  = f"{conv_val:.2f}" if not pd.isna(conv_val) else "  —  "
        xwoba_val = r.get("xwoba_3yr", float("nan"))
        hhr_val   = r.get("hhr_3yr", float("nan"))
        xwoba_str = f"{xwoba_val:.3f}" if not pd.isna(xwoba_val) else "  —  "
        hhr_str   = f"{hhr_val:.1f}%" if not pd.isna(hhr_val) else "  —  "
        flag_txt   = f"  [{flag.upper()}]" if has_flag else ""
        avail_val  = r.get("availability", float("nan"))
        avail_str  = f"{avail_val:.0%}" if not pd.isna(avail_val) else "  —"
        avail_flag = r.get("availability_flag")
        avail_note = f"  ⚠ {avail_flag}" if isinstance(avail_flag, str) else ""
        s400       = int(r.get("seasons_400pa", 0))
        print(
            f"  {name:<22} {r['cqs']:>5.1f} {mod_str:>5} {r['tier']:<18} {r['floor']:>6}  "
            f"{max_tv:>6.1f}  {xwoba_str:>7} {hhr_str:>6} {conv_str:>9}  {int(r['career_pa']):>8}"
            f"  avail={avail_str} s400={s400}{flag_txt}{avail_note}"
        )
        shown.add(pid)

    for pid, name in VALIDATION_IDS.items():
        print_row(name, pid)

    for target in ["Jordan Walker", "Trent Grisham", "Vinnie Pasquantino",
                   "Byron Buxton", "Royce Lewis"]:
        pid = find_pid_by_name(target)
        if pid and pid not in shown:
            print_row(target, pid)
        elif pid is None:
            print(f"  {target:<22}  NOT FOUND in name map")

    print(f"  {'George Kirby':<22}  [PITCHER — CQS not applicable to pitchers yet]")
    print("=" * 100)

    # Conversion rate extremes
    has_flag = cqs_df[cqs_df["conversion_flag"].notna()].copy()
    has_flag["name"] = has_flag["player_id"].map(lambda p: name_map.get(p, p))

    print("\nTOP 5 STATCAST UNDERPERFORMERS (conv < 0.85 for 2+ consecutive years):")
    under = has_flag[has_flag["conversion_flag"] == "underperformer"].sort_values("avg_conv_rate")
    print(f"  {'Player':<24} {'AvgConv':>8} {'ConvByYear':<40} {'CQS':>5} {'Modifier':>8}")
    print("  " + "-" * 90)
    for _, r in under.head(5).iterrows():
        print(f"  {r['name']:<24} {r['avg_conv_rate']:>8.3f}  {r['conv_rates_by_year']:<40} {r['cqs']:>5.1f}     ×0.85")

    print("\nTOP 5 STATCAST OVERPERFORMERS (conv > 1.10 for 2+ consecutive years):")
    over = has_flag[has_flag["conversion_flag"] == "overperformer"].sort_values("avg_conv_rate", ascending=False)
    print(f"  {'Player':<24} {'AvgConv':>8} {'ConvByYear':<40} {'CQS':>5} {'Modifier':>8}")
    print("  " + "-" * 90)
    for _, r in over.head(5).iterrows():
        print(f"  {r['name']:<24} {r['avg_conv_rate']:>8.3f}  {r['conv_rates_by_year']:<40} {r['cqs']:>5.1f}     ×1.10")

    # ── PA-gate tier change report ──────────────────────────────────────────
    changed = cqs_df[cqs_df["tier_rate_only"] != cqs_df["tier"]].copy()
    changed["name"] = changed["player_id"].map(lambda p: name_map.get(p, p))

    print(f"\n{'='*100}")
    print(f"PA-GATE TIER CHANGES  (rate-stat tier vs PA-gated tier)")
    print(f"{'='*100}")
    print(f"  Players whose tier changed: {len(changed)}")

    if not changed.empty:
        # Show direction breakdown
        for old_t, new_t, grp in (
            (o, n, changed[(changed['tier_rate_only'] == o) & (changed['tier'] == n)])
            for o in ["Superstar","Established Star","Solid Contributor"]
            for n in ["Established Star","Solid Contributor","Developing"]
            if o != n
        ):
            if len(grp) > 0:
                print(f"    {old_t} -> {new_t}: {len(grp)} players")

        # Best examples: players with career_pa > 0 who hit the gate (not just missing from career_stats)
        active_movers = changed[changed["career_pa"] > 0].sort_values("career_pa", ascending=False)
        examples = active_movers.head(5)
        if len(examples) == 0:
            examples = changed.sort_values("career_pa", ascending=True).head(5)
        print(f"\n  5 examples of active players moved down (career PA > 0, sorted by PA desc):")
        print(f"  {'Player':<24} {'CareerPA':>9} {'CQS':>6} {'Rate Tier':<20} {'PA-Gated Tier':<20}")
        print(f"  {'-'*82}")
        for _, r in examples.iterrows():
            print(f"  {r['name']:<24} {int(r['career_pa']):>9} {r['cqs']:>6.1f} "
                  f"{r['tier_rate_only']:<20} {r['tier']:<20}")

    # Summary counts
    print(f"\n{'='*60}")
    print(f"Universe: {len(cqs_df)} players total")
    print(f"  2000+ PA universe (for percentile ranking): {(cqs_df['career_pa'] >= 2000).sum()}")
    print(f"  <2000 PA universe:                          {(cqs_df['career_pa'] < 2000).sum()}")
    print(f"Tier counts (after PA gate):")
    print(f"  Superstar (80+, >=1500 PA):        {(cqs_df['tier'] == 'Superstar').sum()}")
    print(f"  Established Star (60-79, >=800 PA): {(cqs_df['tier'] == 'Established Star').sum()}")
    print(f"  Solid Contributor (40-59, >=400 PA):{(cqs_df['tier'] == 'Solid Contributor').sum()}")
    print(f"  Developing (<40 or below PA floor): {(cqs_df['tier'] == 'Developing').sum()}")
    print(f"Floor-eligible (floor > 0):{(cqs_df['floor'] > 0).sum()}")
    print(f"Conversion modifiers applied: "
          f"{(cqs_df['conversion_flag'] == 'underperformer').sum()} underperformers, "
          f"{(cqs_df['conversion_flag'] == 'overperformer').sum()} overperformers")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    print("Fetching expected stats (xwOBA + wOBA, 3 years)...")
    per_year_df, name_map = fetch_expected_stats_all_years()

    print("Fetching hard hit% (3 years)...")
    hhr_df = fetch_hhr_all_years()

    print("Loading career_stats.json...")
    with open(CAREER_STATS_PATH) as f:
        career_stats = json.load(f)

    print("Computing conversion rate flags...")
    conv_flags = compute_conversion_flags(per_year_df, career_stats)

    print("Computing 3-year averages...")
    agg = compute_3yr_averages(per_year_df, hhr_df)

    print("Computing CQS...")
    cqs_df = compute_cqs(agg, career_stats, conv_flags, per_year_df=per_year_df)

    print("Loading player_values.json...")
    with open(PLAYER_VALUES_PATH) as f:
        player_values_raw = json.load(f)
    player_values = player_values_raw.get("players", []) if isinstance(player_values_raw, dict) else player_values_raw

    print_validation(cqs_df, player_values, name_map)

    if args.write:
        out = cqs_df.to_dict(orient="records")
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, default=str)
        print(f"\nWritten: {OUTPUT_PATH} ({len(out)} records)")
    else:
        print("\n[dry run] Use --write to save career_quality.json")


if __name__ == "__main__":
    main()
