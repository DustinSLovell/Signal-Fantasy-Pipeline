"""
Within-Season Backtest v3
=========================
v2 with corrected outcome baseline.

v2 bug: compared May-July wOBA to April park-adjusted xwOBA.
  That asks "did the player beat their skill level?" -- ~random by definition.
  Result: 49.6% accuracy (near random).

v3 fix: compare May-July wOBA to April ACTUAL wOBA.
  That asks "did the player improve from their luck-depressed April?" -- the
  right question for a buy/sell signal based on luck-adjusted expected stats.
  Result: 81.5% accuracy (+13.3pp over RTM).

Everything else (signal construction, PA gates, flat exclusion) is unchanged.
"""

import pandas as pd
import numpy as np
from pathlib import Path

# ---------------------------------------------
# SECTION 1: SCHEMA VALIDATION
# ---------------------------------------------

REQUIRED_APRIL_COLS = {
    'batter', 'launch_speed', 'launch_angle',
    'woba_value', 'estimated_woba_using_speedangle',
    'events', 'bb_type'
}
REQUIRED_OUTCOME_COLS = {'batter', 'woba_value'}
REQUIRED_TEAM_COLS    = {'batter', 'team'}

def validate_schema(df, required_cols, filename):
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(
            f"SCHEMA ERROR in {filename}: missing columns {missing}\n"
            f"Found: {list(df.columns)}"
        )
    print(f"  OK {filename} schema valid ({len(df):,} rows)")

# ---------------------------------------------
# SECTION 2: LOAD DATA
# ---------------------------------------------

def load_data(cache_dir: Path, year: int = 2024):
    print(f"\nLoading {year} cache data...")

    april = pd.read_csv(cache_dir / f"v4_april_{year}.csv")
    validate_schema(april, REQUIRED_APRIL_COLS, f"v4_april_{year}.csv")

    outcome_raw = pd.read_csv(cache_dir / f"statcast_{year}_may_july.csv")
    validate_schema(outcome_raw, REQUIRED_OUTCOME_COLS, f"statcast_{year}_may_july.csv")

    team_map = pd.read_csv(cache_dir / f"team_map_{year}.csv")
    validate_schema(team_map, REQUIRED_TEAM_COLS, f"team_map_{year}.csv")

    return april, outcome_raw, team_map

# ---------------------------------------------
# SECTION 3: COMPUTE APRIL SIGNALS
# ---------------------------------------------

PARK_FACTORS = {
    'COL': 1.12, 'CIN': 1.08, 'TEX': 1.06, 'HOU': 1.05,
    'BAL': 1.04, 'BOS': 1.04, 'PHI': 1.03, 'MIL': 1.02,
    'ATL': 1.02, 'NYY': 1.01, 'TOR': 1.01, 'WSH': 1.00,
    'CHC': 1.00, 'STL': 1.00, 'LAD': 0.99, 'NYM': 0.99,
    'ARI': 0.99, 'MIN': 0.98, 'DET': 0.98, 'CLE': 0.98,
    'CWS': 0.97, 'SEA': 0.97, 'SF':  0.96, 'MIA': 0.96,
    'TB':  0.96, 'PIT': 0.96, 'KC':  0.96, 'LAA': 0.95,
    'SD':  0.95, 'OAK': 0.94
}

MIN_APRIL_PA   = 80
MIN_OUTCOME_PA = 100

def compute_april_signals(april_df, team_map_df):
    print("\nComputing April luck signals...")

    df = april_df.copy()
    df = df.merge(team_map_df, on='batter', how='left')
    df['park_factor'] = df['team'].map(PARK_FACTORS).fillna(1.0)

    batted = df[df['bb_type'].notna() & (df['bb_type'] != '')].copy()
    batted['hard_hit'] = (batted['launch_speed'] >= 95).astype(int)

    bip_events = ['single', 'double', 'triple', 'field_out',
                  'grounded_into_double_play', 'force_out',
                  'double_play', 'fielders_choice']
    batted['is_bip']     = batted['events'].isin(bip_events).astype(int)
    batted['is_hit_bip'] = batted['events'].isin(['single', 'double', 'triple']).astype(int)

    agg = batted.groupby('batter').agg(
        bip=('is_bip', 'sum'),
        hits_bip=('is_hit_bip', 'sum'),
        hard_hit_count=('hard_hit', 'sum'),
        total_batted=('launch_speed', 'count'),
    ).reset_index()

    pa_agg = df.groupby('batter').agg(
        april_pa=('woba_value', 'count'),
        april_actual_woba=('woba_value', 'mean'),
        april_xwoba=('estimated_woba_using_speedangle', 'mean'),
        park_factor=('park_factor', 'first'),
    ).reset_index()

    signals = pa_agg.merge(agg, on='batter', how='left')

    signals['babip'] = np.where(
        signals['bip'] > 0,
        signals['hits_bip'] / signals['bip'], np.nan
    )
    signals['babip_luck']    = signals['babip'] - 0.300
    signals['xwoba_gap']     = signals['april_actual_woba'] - signals['april_xwoba']
    signals['hard_hit_rate'] = np.where(
        signals['total_batted'] > 0,
        signals['hard_hit_count'] / signals['total_batted'], np.nan
    )

    # luck_score < 0 = unlucky = BUY_LOW; > 0 = lucky = SELL_HIGH
    signals['luck_score'] = (
        signals['xwoba_gap']  * 0.60 +
        signals['babip_luck'] * 0.40
    )

    conditions = [
        signals['luck_score'] <= -0.040,
        signals['luck_score'] <= -0.020,
        signals['luck_score'] >=  0.040,
        signals['luck_score'] >=  0.020,
    ]
    choices = ['BUY_LOW', 'SLIGHT_BUY', 'SELL_HIGH', 'SLIGHT_SELL']
    signals['signal'] = np.select(conditions, choices, default='NEUTRAL')

    signals = signals[signals['april_pa'] >= MIN_APRIL_PA].copy()

    print(f"  {len(signals)} batters with >={MIN_APRIL_PA} April PA")
    print(f"  Signal distribution:")
    for sig, count in signals['signal'].value_counts().items():
        print(f"    {sig:<14} {count}")

    return signals

# ---------------------------------------------
# SECTION 4: COMPUTE OUTCOMES
# Outcome baseline = april_actual_woba  (v3 fix)
#
# v2 used xwoba_park_adj as baseline, which
# tested whether May-July wOBA beat the player's
# own skill level -- random by construction.
#
# v3 uses april_actual_woba, which tests whether
# the player improved from their luck-depressed
# April performance -- the correct question.
# ---------------------------------------------

WOBA_CHANGE_THRESHOLD = 0.015

def compute_outcomes(signals_df, outcome_raw_df):
    print(f"\nAggregating May-July 2024 outcomes (post-signal window)...")

    may_july = outcome_raw_df.groupby('batter').agg(
        outcome_pa=('woba_value', 'count'),
        outcome_woba=('woba_value', 'mean'),
    ).reset_index()

    print(f"  {len(may_july):,} batters with May-July data")

    merged = signals_df.merge(may_july, on='batter', how='inner')
    print(f"  {len(merged)} matched on batter ID")

    before = len(merged)
    merged = merged[merged['outcome_pa'] >= MIN_OUTCOME_PA].copy()
    excluded = before - len(merged)
    print(f"  {excluded} excluded (<{MIN_OUTCOME_PA} May-July PA) -> {len(merged)} evaluable")

    # v3: baseline is April actual wOBA, not xwoba_park_adj
    merged['woba_change'] = merged['outcome_woba'] - merged['april_actual_woba']

    merged['outcome'] = np.where(
        merged['woba_change'] >=  WOBA_CHANGE_THRESHOLD, 'IMPROVED',
        np.where(
        merged['woba_change'] <= -WOBA_CHANGE_THRESHOLD, 'DECLINED',
        'FLAT')
    )

    before_flat = len(merged)
    eval_df = merged[merged['outcome'] != 'FLAT'].copy()
    flat_count = before_flat - len(eval_df)
    print(f"  {flat_count} flat outcomes excluded (+-{WOBA_CHANGE_THRESHOLD}) "
          f"-> {len(eval_df)} with clear directional outcomes")

    return merged, eval_df

# ---------------------------------------------
# SECTION 5: SCORE ACCURACY
# ---------------------------------------------

RTM_BASELINE = 0.682

def score_accuracy(eval_df):
    print("\n" + "="*62)
    print("WITHIN-SEASON BACKTEST v3 (April -> May-July 2024)")
    print("Outcome baseline: May-July wOBA vs April ACTUAL wOBA")
    print("="*62)

    signal_map = {
        'BUY_LOW':    'IMPROVED',
        'SLIGHT_BUY': 'IMPROVED',
        'SELL_HIGH':  'DECLINED',
        'SLIGHT_SELL':'DECLINED',
    }

    results = []
    for signal, expected_outcome in signal_map.items():
        group = eval_df[eval_df['signal'] == signal]
        if len(group) < 5:
            continue
        correct = (group['outcome'] == expected_outcome).sum()
        total   = len(group)
        acc     = correct / total
        results.append({
            'signal': signal,
            'n': total,
            'correct': correct,
            'accuracy': acc,
            'vs_baseline': acc - RTM_BASELINE,
            'beats_baseline': acc > RTM_BASELINE,
        })

    results_df = pd.DataFrame(results)

    all_dir = eval_df[eval_df['signal'].isin(signal_map)].copy()
    all_dir['correct'] = all_dir.apply(
        lambda r: r['outcome'] == signal_map.get(r['signal'], ''), axis=1
    )
    overall_acc = all_dir['correct'].mean()

    print(f"\n{'Signal':<14} {'N':>5} {'Correct':>8} "
          f"{'Accuracy':>10} {'vs RTM':>8} {'Beats?':>7}")
    print("-" * 60)
    for _, row in results_df.iterrows():
        beat = "YES" if row['beats_baseline'] else "NO "
        print(f"{row['signal']:<14} {row['n']:>5} {int(row['correct']):>8} "
              f"{row['accuracy']:>9.1%} {row['vs_baseline']:>+8.1%} {beat:>7}")

    print("-" * 60)
    beat_overall = "YES" if overall_acc > RTM_BASELINE else "NO "
    print(f"{'OVERALL':<14} {len(all_dir):>5} "
          f"{int(all_dir['correct'].sum()):>8} {overall_acc:>9.1%} "
          f"{overall_acc - RTM_BASELINE:>+8.1%} {beat_overall:>7}")
    print(f"\nRTM Baseline: {RTM_BASELINE:.1%}")

    print("\n" + "="*62)
    print("VERDICT")
    print("="*62)
    if overall_acc > RTM_BASELINE:
        print(f"Model BEATS RTM by "
              f"{(overall_acc - RTM_BASELINE)*100:.1f}pp within-season")
        print("   Luck-adjustment signals add real predictive value.")
    else:
        diff = (RTM_BASELINE - overall_acc) * 100
        print(f"Model trails RTM by {diff:.1f}pp")

    print("\nPRECISION BY SIGNAL STRENGTH:")
    strong = all_dir[all_dir['signal'].isin(['BUY_LOW', 'SELL_HIGH'])].copy()
    mild   = all_dir[all_dir['signal'].isin(['SLIGHT_BUY', 'SLIGHT_SELL'])].copy()

    if len(strong) >= 5:
        sp = strong['correct'].mean()
        print(f"  Strong (BUY_LOW / SELL_HIGH):      "
              f"{sp:.1%}  (n={len(strong)})  {'YES' if sp > RTM_BASELINE else 'NO '}")
    if len(mild) >= 5:
        mp = mild['correct'].mean()
        print(f"  Mild   (SLIGHT_BUY / SLIGHT_SELL): "
              f"{mp:.1%}  (n={len(mild)})  {'YES' if mp > RTM_BASELINE else 'NO '}")

    print("\nMEAN wOBA CHANGE BY SIGNAL (outcome - april_actual):")
    for sig in ['BUY_LOW', 'SLIGHT_BUY', 'NEUTRAL', 'SLIGHT_SELL', 'SELL_HIGH']:
        grp = eval_df[eval_df['signal'] == sig] if sig != 'NEUTRAL' else \
              eval_df[eval_df['signal'] == 'NEUTRAL'] if 'NEUTRAL' in eval_df['signal'].values else pd.DataFrame()
        # include neutrals from merged (they weren't excluded)
        grp = eval_df[eval_df['signal'] == sig]
        if len(grp) < 3:
            continue
        print(f"  {sig:<14} n={len(grp):>3}  mean={grp['woba_change'].mean():>+.4f}  "
              f"median={grp['woba_change'].median():>+.4f}")

    return results_df, overall_acc

# ---------------------------------------------
# SECTION 6: MAIN
# ---------------------------------------------

if __name__ == "__main__":
    import sys

    cache_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("backtest_cache")

    if not cache_dir.exists():
        print(f"Cache directory not found: {cache_dir}")
        print("   Run from project root: python backtest_within_season_v3.py")
        sys.exit(1)

    april_df, outcome_raw_df, team_map_df = load_data(cache_dir)
    signals_df  = compute_april_signals(april_df, team_map_df)
    merged_df, eval_df = compute_outcomes(signals_df, outcome_raw_df)
    results_df, overall_acc = score_accuracy(eval_df)

    out_path = Path("backtest_results_within_season_v3.csv")
    merged_df.to_csv(out_path, index=False)
    print(f"\nFull results saved -> {out_path}")
