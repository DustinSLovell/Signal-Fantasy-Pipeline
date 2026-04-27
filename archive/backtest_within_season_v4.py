"""
Within-Season Backtest v4
=========================
Tests tiered outcome-classification thresholds.

Signal: identical 2-component formula from v2/v3
  luck_score = xwoba_gap * 0.60 + babip_luck * 0.40  (negative = unlucky = BUY_LOW)

Signal buckets (same as v2/v3):
  BUY_LOW    luck <= -0.040
  SLIGHT_BUY luck <= -0.020
  SELL_HIGH  luck >= +0.040
  SLIGHT_SELL luck >= +0.020

Hypothesis: mild signals don't need to move as much to be "right".
A SLIGHT_BUY predicts a smaller improvement than a BUY_LOW, so
classifying outcomes with a tighter flat band should show their
real directional accuracy more fairly.

Tiered thresholds:
  Strong (BUY_LOW / SELL_HIGH):       ±0.015 wOBA change to escape flat
  Mild   (SLIGHT_BUY / SLIGHT_SELL):  ±0.008 wOBA change to escape flat

Results shown side by side vs uniform ±0.015 for every signal bucket.

Outcome baseline: May-July wOBA vs April actual wOBA (v3 fix).
Cache: v4_april_2024.csv, statcast_2024_may_july.csv, team_map_2024.csv
"""

import numpy as np
import pandas as pd
from pathlib import Path

# ------------------------------------------------------------------
# SCHEMA VALIDATION
# ------------------------------------------------------------------

REQUIRED_APRIL_COLS   = {
    'batter', 'launch_speed', 'woba_value',
    'estimated_woba_using_speedangle', 'events', 'bb_type',
}
REQUIRED_OUTCOME_COLS = {'batter', 'woba_value'}
REQUIRED_TEAM_COLS    = {'batter', 'team'}

def validate_schema(df, required_cols, filename):
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"SCHEMA ERROR in {filename}: missing {missing}\nFound: {list(df.columns)}")
    print(f"  OK {filename} ({len(df):,} rows)")

# ------------------------------------------------------------------
# LOAD DATA
# ------------------------------------------------------------------

def load_data(cache_dir: Path, year: int = 2024):
    print(f"\nLoading {year} cache data...")
    april = pd.read_csv(cache_dir / f"v4_april_{year}.csv")
    validate_schema(april, REQUIRED_APRIL_COLS, f"v4_april_{year}.csv")

    outcome_raw = pd.read_csv(cache_dir / f"statcast_{year}_may_july.csv")
    validate_schema(outcome_raw, REQUIRED_OUTCOME_COLS, f"statcast_{year}_may_july.csv")

    team_map = pd.read_csv(cache_dir / f"team_map_{year}.csv")
    validate_schema(team_map, REQUIRED_TEAM_COLS, f"team_map_{year}.csv")

    return april, outcome_raw, team_map

# ------------------------------------------------------------------
# APRIL SIGNAL  (identical to v2/v3)
# ------------------------------------------------------------------

PARK_FACTORS = {
    'COL': 1.12, 'CIN': 1.08, 'TEX': 1.06, 'HOU': 1.05,
    'BAL': 1.04, 'BOS': 1.04, 'PHI': 1.03, 'MIL': 1.02,
    'ATL': 1.02, 'NYY': 1.01, 'TOR': 1.01, 'WSH': 1.00,
    'CHC': 1.00, 'STL': 1.00, 'LAD': 0.99, 'NYM': 0.99,
    'ARI': 0.99, 'MIN': 0.98, 'DET': 0.98, 'CLE': 0.98,
    'CWS': 0.97, 'SEA': 0.97, 'SF':  0.96, 'MIA': 0.96,
    'TB':  0.96, 'PIT': 0.96, 'KC':  0.96, 'LAA': 0.95,
    'SD':  0.95, 'OAK': 0.94,
}

MIN_APRIL_PA   = 80
MIN_OUTCOME_PA = 100

BIP_EVENTS = {
    'single', 'double', 'triple', 'field_out', 'grounded_into_double_play',
    'force_out', 'double_play', 'fielders_choice',
}

def compute_april_signals(april_df, team_map_df):
    print("\nComputing April luck signals (2-component)...")

    df = april_df.copy()
    df = df.merge(team_map_df, on='batter', how='left')
    df['park_factor'] = df['team'].map(PARK_FACTORS).fillna(1.0)

    batted = df[df['bb_type'].notna() & (df['bb_type'] != '')].copy()
    batted['is_bip']     = batted['events'].isin(BIP_EVENTS).astype(int)
    batted['is_hit_bip'] = batted['events'].isin({'single', 'double', 'triple'}).astype(int)

    bip_agg = batted.groupby('batter').agg(
        bip=('is_bip', 'sum'),
        hits_bip=('is_hit_bip', 'sum'),
    ).reset_index()

    pa_agg = df.groupby('batter').agg(
        april_pa=('woba_value', 'count'),
        april_actual_woba=('woba_value', 'mean'),
        april_xwoba=('estimated_woba_using_speedangle', 'mean'),
        park_factor=('park_factor', 'first'),
    ).reset_index()

    signals = pa_agg.merge(bip_agg, on='batter', how='left')

    signals['babip'] = np.where(
        signals['bip'] > 0, signals['hits_bip'] / signals['bip'], np.nan
    )
    signals['babip_luck'] = signals['babip'] - 0.300
    signals['xwoba_gap']  = signals['april_actual_woba'] - signals['april_xwoba']

    # 2-component luck score (negative = unlucky = BUY_LOW)
    signals['luck_score'] = signals['xwoba_gap'] * 0.60 + signals['babip_luck'] * 0.40

    conditions = [
        signals['luck_score'] <= -0.040,
        signals['luck_score'] <= -0.020,
        signals['luck_score'] >=  0.040,
        signals['luck_score'] >=  0.020,
    ]
    signals['signal'] = np.select(
        conditions, ['BUY_LOW', 'SLIGHT_BUY', 'SELL_HIGH', 'SLIGHT_SELL'], default='NEUTRAL'
    )

    signals = signals[signals['april_pa'] >= MIN_APRIL_PA].copy()

    print(f"  {len(signals)} batters with >={MIN_APRIL_PA} April PA")
    print(f"  Signal distribution:")
    for sig, count in signals['signal'].value_counts().items():
        print(f"    {sig:<14} {count}")

    return signals

# ------------------------------------------------------------------
# OUTCOMES
# ------------------------------------------------------------------

def compute_outcomes(signals_df, outcome_raw_df):
    print("\nAggregating May-July 2024 outcomes...")

    may_july = outcome_raw_df.groupby('batter').agg(
        outcome_pa=('woba_value', 'count'),
        outcome_woba=('woba_value', 'mean'),
    ).reset_index()

    print(f"  {len(may_july):,} batters with May-July data")

    merged = signals_df.merge(may_july, on='batter', how='inner')
    print(f"  {len(merged)} matched on batter ID")

    before = len(merged)
    merged = merged[merged['outcome_pa'] >= MIN_OUTCOME_PA].copy()
    print(f"  {before - len(merged)} excluded (<{MIN_OUTCOME_PA} May-July PA) -> {len(merged)} evaluable")

    # Outcome baseline: v3 fix (April actual wOBA, not xwoba_park_adj)
    merged['woba_change'] = merged['outcome_woba'] - merged['april_actual_woba']

    return merged

# ------------------------------------------------------------------
# CLASSIFY OUTCOMES — two threshold regimes
# ------------------------------------------------------------------

STRONG_THRESHOLD = 0.015
MILD_THRESHOLD   = 0.008

STRONG_SIGNALS = {'BUY_LOW', 'SELL_HIGH'}
MILD_SIGNALS   = {'SLIGHT_BUY', 'SLIGHT_SELL'}

def classify_outcomes(merged_df, threshold: float) -> pd.DataFrame:
    """Uniform threshold: same flat band for all signals."""
    df = merged_df.copy()
    df['outcome'] = np.where(
        df['woba_change'] >=  threshold, 'IMPROVED',
        np.where(df['woba_change'] <= -threshold, 'DECLINED', 'FLAT')
    )
    return df


def classify_outcomes_tiered(merged_df) -> pd.DataFrame:
    """Tiered threshold: strong signals use ±0.015, mild signals use ±0.008."""
    df = merged_df.copy()
    threshold = np.where(
        df['signal'].isin(STRONG_SIGNALS), STRONG_THRESHOLD, MILD_THRESHOLD
    )
    df['outcome'] = np.where(
        df['woba_change'] >=  threshold, 'IMPROVED',
        np.where(df['woba_change'] <= -threshold, 'DECLINED', 'FLAT')
    )
    return df

# ------------------------------------------------------------------
# ACCURACY FOR ONE REGIME
# ------------------------------------------------------------------

RTM_BASELINE = 0.682
SIGNAL_MAP   = {
    'BUY_LOW':    'IMPROVED',
    'SLIGHT_BUY': 'IMPROVED',
    'SELL_HIGH':  'DECLINED',
    'SLIGHT_SELL':'DECLINED',
}

def bucket_stats(df_with_outcome):
    """Returns dict: signal -> (n_eval, n_correct, accuracy)."""
    eval_df = df_with_outcome[
        df_with_outcome['signal'].isin(SIGNAL_MAP) &
        (df_with_outcome['outcome'] != 'FLAT')
    ].copy()
    eval_df['correct'] = eval_df.apply(
        lambda r: r['outcome'] == SIGNAL_MAP[r['signal']], axis=1
    )
    stats = {}
    for sig in ['BUY_LOW', 'SLIGHT_BUY', 'SELL_HIGH', 'SLIGHT_SELL']:
        grp = eval_df[eval_df['signal'] == sig]
        n   = len(grp)
        c   = int(grp['correct'].sum()) if n > 0 else 0
        stats[sig] = (n, c, c / n if n > 0 else float('nan'))
    overall_n = len(eval_df)
    overall_c = int(eval_df['correct'].sum())
    stats['OVERALL'] = (overall_n, overall_c, overall_c / overall_n if overall_n > 0 else float('nan'))
    return stats

# ------------------------------------------------------------------
# SIDE-BY-SIDE REPORT
# ------------------------------------------------------------------

def report(merged_df):
    uniform = classify_outcomes(merged_df, STRONG_THRESHOLD)
    tiered  = classify_outcomes_tiered(merged_df)

    u_stats = bucket_stats(uniform)
    t_stats = bucket_stats(tiered)

    print("\n" + "=" * 82)
    print("WITHIN-SEASON BACKTEST v4 — TIERED vs UNIFORM OUTCOME THRESHOLDS")
    print(f"Signal: xwoba_gap*0.60 + babip_luck*0.40 | Outcome: May-July vs April actual wOBA")
    print("=" * 82)

    header = (
        f"\n{'':14}  "
        f"{'--- Uniform +-0.015 ---':^26}  "
        f"{'--- Tiered (strong +-0.015, mild +-0.008) ---':^40}"
    )
    subhdr = (
        f"{'Signal':<14}  "
        f"{'N':>5} {'Acc':>8} {'vs RTM':>8}  "
        f"{'N':>5} {'Acc':>8} {'vs RTM':>8}  {'Delta':>8}"
    )
    divider = "-" * 82
    print(header)
    print(subhdr)
    print(divider)

    ORDER = ['BUY_LOW', 'SLIGHT_BUY', 'SELL_HIGH', 'SLIGHT_SELL', 'OVERALL']
    for sig in ORDER:
        un, uc, ua = u_stats.get(sig, (0, 0, float('nan')))
        tn, tc, ta = t_stats.get(sig, (0, 0, float('nan')))
        u_vs  = ua - RTM_BASELINE if not pd.isna(ua) else float('nan')
        t_vs  = ta - RTM_BASELINE if not pd.isna(ta) else float('nan')
        delta = ta - ua if not pd.isna(ta) and not pd.isna(ua) else float('nan')
        marker = " <--" if abs(delta) >= 0.02 and not pd.isna(delta) else ""
        if sig == 'OVERALL':
            print(divider)
        print(
            f"{sig:<14}  "
            f"{un:>5} {ua:>7.1%} {u_vs:>+8.1%}  "
            f"{tn:>5} {ta:>7.1%} {t_vs:>+8.1%}  {delta:>+8.1%}{marker}"
        )

    print(f"\nRTM Baseline: {RTM_BASELINE:.1%}")
    print(f"Strong threshold: ±{STRONG_THRESHOLD} | Mild threshold: ±{MILD_THRESHOLD}")

    # Flat-rate comparison
    print("\nFLAT RATE BY SIGNAL (excluded from accuracy calc):")
    print(f"  {'Signal':<14} {'Uniform':>10}  {'Tiered':>10}  {'D flat count':>12}")
    print(f"  {'-'*52}")
    for sig in ['BUY_LOW', 'SLIGHT_BUY', 'SELL_HIGH', 'SLIGHT_SELL']:
        u_grp   = uniform[uniform['signal'] == sig]
        t_grp   = tiered[tiered['signal'] == sig]
        u_flat  = (u_grp['outcome'] == 'FLAT').sum()
        t_flat  = (t_grp['outcome'] == 'FLAT').sum()
        u_total = len(u_grp)
        u_pct   = u_flat / u_total if u_total > 0 else float('nan')
        t_pct   = t_flat / u_total if u_total > 0 else float('nan')
        print(f"  {sig:<14} {u_pct:>9.1%}   {t_pct:>9.1%}   {t_flat - u_flat:>+5} fewer flat")

    # Mean wOBA change (no threshold applied — raw signal quality check)
    print("\nMEAN wOBA CHANGE BY SIGNAL (raw, no flat filter):")
    for sig in ['BUY_LOW', 'SLIGHT_BUY', 'NEUTRAL', 'SLIGHT_SELL', 'SELL_HIGH']:
        grp = merged_df[merged_df['signal'] == sig]
        if len(grp) < 3:
            continue
        print(f"  {sig:<14} n={len(grp):>3}  mean={grp['woba_change'].mean():>+.4f}  "
              f"median={grp['woba_change'].median():>+.4f}")

    print("\nVERDICT")
    print("-" * 82)
    u_ov = u_stats['OVERALL'][2]
    t_ov = t_stats['OVERALL'][2]
    for label, acc in [("Uniform ±0.015", u_ov), ("Tiered          ", t_ov)]:
        beat = "BEATS" if acc > RTM_BASELINE else "trails"
        pp   = abs(acc - RTM_BASELINE) * 100
        print(f"  {label}: {acc:.1%}  ({beat} RTM by {pp:.1f}pp)")

    return u_stats, t_stats

# ------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    cache_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("backtest_cache")
    if not cache_dir.exists():
        print(f"Cache directory not found: {cache_dir}")
        sys.exit(1)

    april_df, outcome_raw_df, team_map_df = load_data(cache_dir)
    signals_df = compute_april_signals(april_df, team_map_df)
    merged_df  = compute_outcomes(signals_df, outcome_raw_df)
    u_stats, t_stats = report(merged_df)

    out_path = Path("backtest_results_within_season_v4.csv")
    merged_df.to_csv(out_path, index=False)
    print(f"\nFull results saved -> {out_path}")
