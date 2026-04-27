"""
Within-Season Backtest v2
=========================
Correct methodology: April 2024 signals → May-July 2024 outcomes ONLY
(post-signal window, no feature/label overlap)

Why this is the right methodology:
- Signal generated from April data (available May 1st)
- Outcome measured strictly after signal date (May-July)
- No temporal contamination between feature and label windows
- Maps exactly to real fantasy decision: "buy on May 1st, measure result"

Baseline we're beating: RTM at 68.2%
Success threshold: >68.2% directional accuracy

CAREER LESSON #17: Feature/Label Leakage
Using full-season wOBA as outcome would contaminate the label with
the same April data used to generate the signal. Always ensure your
outcome window is strictly AFTER your feature window.
"""

import pandas as pd
import numpy as np
from pathlib import Path

# ---------------------------------------------
# SECTION 1: SCHEMA VALIDATION
# Loud failures, not silent ones.
# CAREER LESSON #14: Defensive programming --
# assert your data contract at the door.
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
# Three sources:
#   - v4_april_2024.csv      -> signal generation (full columns)
#   - statcast_2024_may_july -> outcome measurement (post-signal)
#   - team_map_2024.csv      -> park factor lookup
# ---------------------------------------------

def load_data(cache_dir: Path, year: int = 2024):
    print(f"\nLoading {year} cache data...")

    # Signal source: full-column April cache
    april = pd.read_csv(cache_dir / f"v4_april_{year}.csv")
    validate_schema(april, REQUIRED_APRIL_COLS, f"v4_april_{year}.csv")

    # Outcome source: post-signal May-July pitch data
    # Using old-format cache -- woba_value is all we need for outcomes
    outcome_raw = pd.read_csv(cache_dir / f"statcast_{year}_may_july.csv")
    validate_schema(outcome_raw, REQUIRED_OUTCOME_COLS, f"statcast_{year}_may_july.csv")

    # Park factor lookup
    team_map = pd.read_csv(cache_dir / f"team_map_{year}.csv")
    validate_schema(team_map, REQUIRED_TEAM_COLS, f"team_map_{year}.csv")

    return april, outcome_raw, team_map

# ---------------------------------------------
# SECTION 3: COMPUTE APRIL SIGNALS
# Per-batter luck metrics from pitch-level data
# Mirrors v5 score_luck.py logic
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

MIN_APRIL_PA  = 80   # signal quality gate
MIN_OUTCOME_PA = 100  # post-signal outcome gate (censored data exclusion)

def compute_april_signals(april_df, team_map_df):
    print("\nComputing April luck signals...")

    df = april_df.copy()
    df = df.merge(team_map_df, on='batter', how='left')
    df['park_factor'] = df['team'].map(PARK_FACTORS).fillna(1.0)

    # Batted ball subset
    batted = df[df['bb_type'].notna() & (df['bb_type'] != '')].copy()
    batted['hard_hit'] = (batted['launch_speed'] >= 95).astype(int)

    bip_events = ['single', 'double', 'triple', 'field_out',
                  'grounded_into_double_play', 'force_out',
                  'double_play', 'fielders_choice']
    batted['is_bip']     = batted['events'].isin(bip_events).astype(int)
    batted['is_hit_bip'] = batted['events'].isin(
        ['single', 'double', 'triple']
    ).astype(int)

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

    # Luck metrics
    signals['babip'] = np.where(
        signals['bip'] > 0,
        signals['hits_bip'] / signals['bip'], np.nan
    )
    signals['babip_luck']     = signals['babip'] - 0.300
    signals['xwoba_gap']      = signals['april_actual_woba'] - signals['april_xwoba']
    signals['xwoba_park_adj'] = signals['april_xwoba'] / signals['park_factor']
    signals['hard_hit_rate']  = np.where(
        signals['total_batted'] > 0,
        signals['hard_hit_count'] / signals['total_batted'], np.nan
    )

    # v5 luck score (negative = unlucky = buy low)
    signals['luck_score'] = (
        signals['xwoba_gap']   * 0.60 +
        signals['babip_luck']  * 0.40
    )

    # Signal classification (v5 thresholds)
    conditions = [
        signals['luck_score'] <= -0.040,
        signals['luck_score'] <= -0.020,
        signals['luck_score'] >=  0.040,
        signals['luck_score'] >=  0.020,
    ]
    choices = ['BUY_LOW', 'SLIGHT_BUY', 'SELL_HIGH', 'SLIGHT_SELL']
    signals['signal'] = np.select(conditions, choices, default='NEUTRAL')

    # Minimum April PA gate (signal quality)
    signals = signals[signals['april_pa'] >= MIN_APRIL_PA].copy()

    print(f"  {len(signals)} batters with >={MIN_APRIL_PA} April PA")
    print(f"  Signal distribution:")
    for sig, count in signals['signal'].value_counts().items():
        print(f"    {sig:<14} {count}")

    return signals

# ---------------------------------------------
# SECTION 4: COMPUTE OUTCOMES (FIXED)
# Outcome = May-July wOBA ONLY
# No overlap with April signal window
#
# CAREER LESSON #17: Feature/Label Leakage
# Previously used full-season wOBA which
# included April -- the same data used to
# generate the signal. Fixed: outcome window
# is strictly post-signal (May-July only).
# ---------------------------------------------

WOBA_CHANGE_THRESHOLD = 0.015  # 15 points = meaningful movement

def compute_outcomes(signals_df, outcome_raw_df):
    """
    Aggregate May-July pitch data to per-batter wOBA.
    This is the post-signal outcome window only.
    No April data included -- clean temporal separation.
    """
    print(f"\nAggregating May-July 2024 outcomes (post-signal window)...")

    # Aggregate pitch-level May-July to per-batter wOBA
    may_july = outcome_raw_df.groupby('batter').agg(
        outcome_pa=('woba_value', 'count'),
        outcome_woba=('woba_value', 'mean'),
    ).reset_index()

    print(f"  {len(may_july):,} batters with May-July data")

    # Join signals to outcomes
    merged = signals_df.merge(may_july, on='batter', how='inner')
    print(f"  {len(merged)} matched on batter ID")

    # Apply outcome PA gate (censored data exclusion)
    before = len(merged)
    merged = merged[merged['outcome_pa'] >= MIN_OUTCOME_PA].copy()
    excluded = before - len(merged)
    print(f"  {excluded} excluded (<{MIN_OUTCOME_PA} May-July PA) -> {len(merged)} evaluable")

    # Directional outcome: did wOBA improve or decline vs April xwOBA signal?
    merged['woba_change'] = merged['outcome_woba'] - merged['xwoba_park_adj']

    merged['outcome'] = np.where(
        merged['woba_change'] >=  WOBA_CHANGE_THRESHOLD, 'IMPROVED',
        np.where(
        merged['woba_change'] <= -WOBA_CHANGE_THRESHOLD, 'DECLINED',
        'FLAT')
    )

    # Exclude flat outcomes -- inconclusive, neither right nor wrong
    before_flat = len(merged)
    eval_df = merged[merged['outcome'] != 'FLAT'].copy()
    flat_count = before_flat - len(eval_df)
    print(f"  {flat_count} flat outcomes excluded (+-{WOBA_CHANGE_THRESHOLD}) "
          f"-> {len(eval_df)} with clear directional outcomes")

    return merged, eval_df

# ---------------------------------------------
# SECTION 5: SCORE ACCURACY
# Precision vs Recall
# - Precision: of our BUY calls, % that were right
# - Recall: of all players who improved, % we caught
# For fantasy: precision matters more than recall
# ---------------------------------------------

RTM_BASELINE = 0.682

def score_accuracy(eval_df):
    print("\n" + "="*62)
    print("WITHIN-SEASON BACKTEST RESULTS (April -> May-July 2024)")
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

    # Overall across all directional signals
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

    # Verdict
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
        print("   Consider: threshold tuning, RTM removal, or Phase C.")

    # Precision by signal strength
    print("\nPRECISION BY SIGNAL STRENGTH:")
    strong = all_dir[all_dir['signal'].isin(['BUY_LOW', 'SELL_HIGH'])].copy()
    mild   = all_dir[all_dir['signal'].isin(['SLIGHT_BUY', 'SLIGHT_SELL'])].copy()

    if len(strong) >= 5:
        sp = strong['correct'].mean()
        print(f"  Strong (BUY_LOW / SELL_HIGH):      "
              f"{sp:.1%}  (n={len(strong)})  "
              f"{'YES' if sp > RTM_BASELINE else 'NO '}")
    if len(mild) >= 5:
        mp = mild['correct'].mean()
        print(f"  Mild   (SLIGHT_BUY / SLIGHT_SELL): "
              f"{mp:.1%}  (n={len(mild)})  "
              f"{'YES' if mp > RTM_BASELINE else 'NO '}")

    print("\n-- PRECISION vs RECALL NOTE --")
    print("  Precision = of our BUY calls, how many actually improved?")
    print("  Recall    = of all players who improved, how many did we flag?")
    print("  For fantasy buy/sell decisions, PRECISION matters more.")
    print("  A tight threshold = fewer calls, higher precision.")

    return results_df, overall_acc

# ---------------------------------------------
# SECTION 6: MAIN
# ---------------------------------------------

if __name__ == "__main__":
    import sys

    cache_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("backtest_cache")

    if not cache_dir.exists():
        print(f"Cache directory not found: {cache_dir}")
        print("   Run from project root: python backtest_within_season_v2.py")
        sys.exit(1)

    april_df, outcome_raw_df, team_map_df = load_data(cache_dir)
    signals_df  = compute_april_signals(april_df, team_map_df)
    merged_df, eval_df = compute_outcomes(signals_df, outcome_raw_df)
    results_df, overall_acc = score_accuracy(eval_df)

    # Save full results for deeper analysis
    out_path = Path("backtest_results_within_season.csv")
    merged_df.to_csv(out_path, index=False)
    print(f"\nFull results saved -> {out_path}")
    print("\nNext steps based on results:")
    print("  If beats RTM  -> proceed to Phase C (seasonal patterns)")
    print("  If trails RTM -> remove RTM double-count, retune thresholds")
