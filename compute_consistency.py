"""
Phase B: Consistency Score
Computes per-player variance from 2022-2024 xwOBA, applies age and park-change
modifiers, and produces consistency_multiplier + luck_score_v6.

Usage:
    python compute_consistency.py            # validate only (no file writes)
    python compute_consistency.py --write    # write luck_scores.csv in-place
"""

import argparse
import json
import math
import os
import sys

import numpy as np
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, "backtest_cache")
DATA_DIR = os.path.join(BASE_DIR, "data")

LUCK_SCORES_PATH = os.path.join(BASE_DIR, "luck_scores.csv")
PITCHER_LUCK_PATH = os.path.join(BASE_DIR, "pitcher_luck_scores.csv")
CAREER_STATS_PATH = os.path.join(DATA_DIR, "career_stats.json")

LEAGUE_AVG_XWOBA = 0.315
MIN_PA_PER_SEASON = 300
MIN_SEASONS = 2

# Variance tiers: (std_dev_upper_bound, label, base_multiplier)
# Very Consistent boost (1.10) is gated behind wRC+ > 120 — see _consistency_multiplier.
VARIANCE_TIERS = [
    (8.0,          "Very Consistent",  1.10),
    (15.0,         "Consistent",       1.00),
    (25.0,         "Inconsistent",     0.80),
    (35.0,         "Volatile",         0.60),
    (float("inf"), "Extreme",          0.40),
]

# Age modifier applied to penalty component only (base_mult < 1.0)
# (age_upper_exclusive, modifier)
AGE_MODIFIERS = [
    (26,            0.40),
    (32,            1.00),
    (35,            1.20),
    (float("inf"),  1.40),
]


def _variance_tier(std_dev: float) -> tuple[float, str]:
    for upper, label, mult in VARIANCE_TIERS:
        if std_dev < upper:
            return mult, label
    return 0.40, "Extreme"


def _age_modifier(age: float) -> float:
    for upper, mod in AGE_MODIFIERS:
        if age < upper:
            return mod
    return 1.40


def _consistency_multiplier(
    base_mult: float,
    age: float,
    park_change: bool,
    wrc_plus: float = 100.0,
) -> float:
    """Apply age modifier and park-change discount to variance penalty.
    Boost (>1.0) only fires when wRC+ > 120 — prevents average-consistent
    players (e.g. Bohm) from getting artificial signal inflation."""
    if base_mult >= 1.0:
        if wrc_plus > 120:
            return round(base_mult, 4)
        return 1.0000  # consistent but not elite quality — no boost

    penalty = base_mult - 1.0

    if park_change:
        penalty *= 0.60

    penalty *= _age_modifier(age)

    return round(max(0.50, 1.0 + penalty), 4)


def load_yearly_xwoba() -> pd.DataFrame:
    frames = []
    for year in [2022, 2023, 2024]:
        path = os.path.join(CACHE_DIR, f"expected_stats_{year}.csv")
        df = pd.read_csv(path)
        df["year"] = year
        frames.append(df)
    combined = pd.concat(frames, ignore_index=True)
    combined = combined[combined["pa"] >= MIN_PA_PER_SEASON].copy()
    combined["pseudo_wrc_plus"] = (combined["xwoba"] / LEAGUE_AVG_XWOBA) * 100
    return combined


def compute_player_variance(yearly: pd.DataFrame) -> pd.DataFrame:
    """Returns one row per player with variance_std and seasons_used."""
    def _agg(grp):
        seasons = grp["year"].nunique()
        if seasons < MIN_SEASONS:
            return pd.Series({
                "variance_std": float("nan"),
                "seasons_used": seasons,
                "wrc_plus_mean": grp["pseudo_wrc_plus"].mean(),
            })
        return pd.Series({
            "variance_std": grp["pseudo_wrc_plus"].std(ddof=1),
            "seasons_used": seasons,
            "wrc_plus_mean": grp["pseudo_wrc_plus"].mean(),
        })

    result = yearly.groupby("player_id").apply(_agg).reset_index()
    return result


def build_consistency(luck_df: pd.DataFrame, variance_df: pd.DataFrame) -> pd.DataFrame:
    luck = luck_df.copy()

    merged = luck.merge(
        variance_df.rename(columns={"player_id": "batter"}),
        on="batter",
        how="left",
    )

    rows = []
    for _, row in merged.iterrows():
        std = row.get("variance_std", float("nan"))
        age = float(row.get("age", 30)) if not pd.isna(row.get("age")) else 30.0
        seasons = int(row.get("seasons_used", 0)) if not pd.isna(row.get("seasons_used")) else 0

        if pd.isna(std) or math.isnan(std):
            variance_tier_label = "Insufficient data"
            base_mult = 1.00
            std_display = float("nan")
        else:
            base_mult, variance_tier_label = _variance_tier(std)
            std_display = round(std, 2)

        # Park change: parking lot — no historical team data available
        # Framework is here; would require per-year team tracking to activate
        park_change = False

        wrc_plus = float(row.get("wrc_plus_mean", 100.0)) if not pd.isna(row.get("wrc_plus_mean")) else 100.0

        age_mod_applied = _age_modifier(age) if base_mult < 1.0 else 1.00
        mult = _consistency_multiplier(base_mult, age, park_change, wrc_plus)

        luck_v5 = float(row["luck_score"])
        luck_v6 = round(luck_v5 * mult, 4)

        rows.append({
            "batter": row["batter"],
            "variance_std": std_display,
            "variance_tier": variance_tier_label,
            "seasons_used": seasons,
            "wrc_plus_for_gate": round(wrc_plus, 1),
            "age_modifier_applied": round(age_mod_applied, 2),
            "park_change_detected": park_change,
            "consistency_multiplier": mult,
            "luck_score_v5": round(luck_v5, 4),
            "luck_score_v6": luck_v6,
        })

    return pd.DataFrame(rows)


def build_pitcher_consistency(pitcher_df: pd.DataFrame) -> pd.DataFrame:
    """Pitchers: consistency_multiplier = 1.00 (no per-year FIP variance data).
    Framework columns added; activate when historical pitcher FIP cache is built."""
    rows = []
    for _, row in pitcher_df.iterrows():
        luck_v5 = float(row["luck_score"])
        rows.append({
            "pitcher": row["pitcher"],
            "variance_std": float("nan"),
            "variance_tier": "No data",
            "seasons_used": 0,
            "age_modifier_applied": 1.00,
            "park_change_detected": False,
            "consistency_multiplier": 1.00,
            "luck_score_v5": round(luck_v5, 4),
            "luck_score_v6": round(luck_v5, 4),
        })
    return pd.DataFrame(rows)


def assign_verdict_v6(score: float) -> str:
    if score >= 0.40:   return "Buy low"
    if score >= 0.15:   return "Slight buy"
    if score <= -0.40:  return "Sell high"
    if score <= -0.15:  return "Slight sell"
    return "Neutral"


def print_validation(luck_df: pd.DataFrame, consistency_df: pd.DataFrame) -> None:
    full = luck_df.merge(consistency_df, on="batter")

    SPOT_CHECK_IDS = {
        691023: "Jordan Walker",
        664761: "Alec Bohm",
        660271: "Shohei Ohtani",
        621439: "Byron Buxton",
        596019: "Francisco Lindor",
        608070: "Jose Ramirez",
        592450: "Aaron Judge",
    }
    print("\n=== SPOT CHECK: Hitters ===")
    print(f"{'Name':<22} {'std':>6} {'Tier':<20} {'wRC+':>6} {'AgeMod':>7} {'PkChg':>6} {'CnsMlt':>7} {'v5':>8} {'v6':>8}")
    print("-" * 103)
    for player_id, name in SPOT_CHECK_IDS.items():
        match = full[full["batter"] == player_id]
        if match.empty:
            print(f"  {name:<20} NOT FOUND (id={player_id})")
            continue
        r = match.iloc[0]
        std_str = f"{r['variance_std']:.1f}" if not pd.isna(r['variance_std']) else "  N/A"
        wrc_str = f"{r['wrc_plus_for_gate']:.0f}" if "wrc_plus_for_gate" in r.index and not pd.isna(r.get("wrc_plus_for_gate")) else "N/A"
        print(
            f"  {r['name']:<20} {std_str:>6} {r['variance_tier']:<20}"
            f" {wrc_str:>6} {r['age_modifier_applied']:>7.2f} {str(r['park_change_detected']):>6}"
            f" {r['consistency_multiplier']:>7.3f} {r['luck_score_v5']:>8.4f} {r['luck_score_v6']:>8.4f}"
        )

    print("\n=== TOP 10 BUY LOW (v6) ===")
    buys = full[full["luck_score_v6"] >= 0.15].sort_values("luck_score_v6", ascending=False).head(10)
    for _, r in buys.iterrows():
        print(f"  {r['name']:<22} v5={r['luck_score_v5']:.4f}  v6={r['luck_score_v6']:.4f}  {r['variance_tier']}")

    print("\n=== VERDICT DISTRIBUTION: v5 vs v6 ===")
    full["verdict_v5"] = full["luck_score_v5"].apply(assign_verdict_v6)
    full["verdict_v6"] = full["luck_score_v6"].apply(assign_verdict_v6)
    v5_dist = full["verdict_v5"].value_counts().rename("v5")
    v6_dist = full["verdict_v6"].value_counts().rename("v6")
    dist = pd.concat([v5_dist, v6_dist], axis=1).fillna(0).astype(int)
    print(dist.to_string())

    tier_counts = consistency_df["variance_tier"].value_counts()
    n_inconsistent_or_worse = consistency_df["variance_tier"].isin(
        ["Inconsistent", "Volatile", "Extreme"]
    ).sum()
    n_park_change = consistency_df["park_change_detected"].sum()
    n_insufficient = (consistency_df["variance_tier"] == "Insufficient data").sum()
    n_total = len(consistency_df)
    print(f"\n  === Variance Tier Distribution ===")
    for tier in ["Very Consistent", "Consistent", "Inconsistent", "Volatile", "Extreme", "Insufficient data"]:
        count = tier_counts.get(tier, 0)
        pct = count / n_total * 100 if n_total > 0 else 0
        print(f"    {tier:<22}: {count:>4}  ({pct:.1f}%)")
    print(f"\n  Inconsistent or worse: {n_inconsistent_or_worse}  ({n_inconsistent_or_worse/n_total*100:.1f}%)")
    print(f"  Park change detected:  {n_park_change}  (parking lot -- no historical team data)")
    print(f"  Insufficient data:     {n_insufficient}  ({n_insufficient/n_total*100:.1f}%)  (< {MIN_SEASONS} seasons w/ {MIN_PA_PER_SEASON}+ PA)")


def print_pitcher_validation(pitcher_df: pd.DataFrame, pitcher_cons: pd.DataFrame) -> None:
    drop_cols = [c for c in pitcher_cons.columns if c != "pitcher" and c in pitcher_df.columns]
    full = pitcher_df.drop(columns=drop_cols).merge(pitcher_cons, on="pitcher")
    SPOT_CHECK_NAMES = ["Luzardo", "Gausman", "Schlittler"]
    print("\n=== SPOT CHECK: Pitchers ===")
    print(f"{'Name':<22} {'CnsMlt':>7} {'v5':>7} {'v6':>7} {'Tier'}")
    print("-" * 65)
    for name in SPOT_CHECK_NAMES:
        match = full[full["name"].str.contains(name, case=False, na=False)]
        if match.empty:
            print(f"  {name:<20} NOT FOUND")
            continue
        r = match.iloc[0]
        print(
            f"  {r['name']:<20} {r['consistency_multiplier']:>7.3f}"
            f" {r['luck_score_v5']:>7.4f} {r['luck_score_v6']:>7.4f}  {r['variance_tier']}"
        )
    print("\n  Note: pitcher consistency = 1.00 for all (no per-year FIP cache yet)")

    print("\n=== TOP 5 PITCHER BUY LOW (v6) ===")
    buys = full[full["luck_score_v6"] >= 0.15].sort_values("luck_score_v6", ascending=False).head(5)
    for _, r in buys.iterrows():
        print(f"  {r['name']:<22} v6={r['luck_score_v6']:.4f}  IP={r['IP']:.1f}  {r['verdict']}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="Write columns back to CSV files")
    args = parser.parse_args()

    print("Loading yearly xwOBA data...")
    yearly = load_yearly_xwoba()
    print(f"  Loaded {len(yearly)} player-seasons (2022-2024, PA >= {MIN_PA_PER_SEASON})")

    print("Computing per-player variance...")
    variance_df = compute_player_variance(yearly)
    qualified = variance_df[variance_df["seasons_used"] >= MIN_SEASONS]
    print(f"  {len(qualified)} players with >= {MIN_SEASONS} qualified seasons")

    print("Loading luck_scores.csv...")
    luck_df = pd.read_csv(LUCK_SCORES_PATH)
    print(f"  {len(luck_df)} hitters")

    print("Building hitter consistency scores...")
    consistency_df = build_consistency(luck_df, variance_df)

    print("Loading pitcher_luck_scores.csv...")
    pitcher_df = pd.read_csv(PITCHER_LUCK_PATH)
    print(f"  {len(pitcher_df)} pitchers")

    print("Building pitcher consistency scores (framework only)...")
    pitcher_cons = build_pitcher_consistency(pitcher_df)

    print_validation(luck_df, consistency_df)
    print_pitcher_validation(pitcher_df, pitcher_cons)

    if args.write:
        # Merge new columns back to luck_scores.csv
        new_cols = ["batter", "variance_std", "variance_tier", "seasons_used",
                    "wrc_plus_for_gate", "age_modifier_applied", "park_change_detected",
                    "consistency_multiplier", "luck_score_v5", "luck_score_v6"]
        to_merge = consistency_df[new_cols]

        # Drop existing Phase B cols if re-running
        drop_cols = [c for c in new_cols[1:] if c in luck_df.columns]
        luck_df = luck_df.drop(columns=drop_cols)

        luck_out = luck_df.merge(to_merge, on="batter", how="left")
        luck_out.to_csv(LUCK_SCORES_PATH, index=False)
        print(f"\nWrote {len(luck_out)} rows to luck_scores.csv")

        # Pitcher
        p_new_cols = ["pitcher", "variance_std", "variance_tier", "seasons_used",
                      "age_modifier_applied", "park_change_detected",
                      "consistency_multiplier", "luck_score_v5", "luck_score_v6"]
        p_to_merge = pitcher_cons[p_new_cols]
        p_drop = [c for c in p_new_cols[1:] if c in pitcher_df.columns]
        pitcher_df = pitcher_df.drop(columns=p_drop)
        pitcher_out = pitcher_df.merge(p_to_merge, on="pitcher", how="left")
        pitcher_out.to_csv(PITCHER_LUCK_PATH, index=False)
        print(f"Wrote {len(pitcher_out)} rows to pitcher_luck_scores.csv")
    else:
        print("\n[Validation only -- rerun with --write to persist changes]")


if __name__ == "__main__":
    main()
