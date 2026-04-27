"""
Within-Season Backtest v5
=========================
v3 baseline + Phase C seasonal pattern modifiers.

Signal window:  April 2024 (v4_april_2024.csv)
Outcome window: May-July 2024 (statcast_2024_may_july.csv)
Outcome baseline: May-July wOBA vs April actual wOBA  (v3 fix)

Signal formula (identical to v2/v3):
  luck_score = xwoba_gap * 0.60 + babip_luck * 0.40

Phase C modifiers applied AFTER luck_score, BEFORE signal classification:
  V-shape (slow_starter AND summer_performer) + positive score: x1.20
  Slow starter only + positive score:                           x0.80
  Summer performer only + positive score:                       x1.10
  Second half fader + negative score:                           x1.15
  Second half fader + positive score:                           x0.90
  (modifiers are independent -- fader stacks with slow/summer)

Output: three-column comparison
  Col 1 -- v2 baseline (no modifiers)
  Col 2 -- v5 Phase C (modifiers applied)
  Col 3 -- Phase C only (accuracy among the ~70 modified players only)

Key question: does Phase C push overall accuracy above 81.5% and
BUY_LOW above 94.7%?
"""

import json
import os
import numpy as np
import pandas as pd
from pathlib import Path

# ------------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------------

BASE_DIR   = Path(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR  = BASE_DIR / "backtest_cache"
SEASONAL_PATH = BASE_DIR / "data" / "seasonal_patterns.json"

MIN_APRIL_PA   = 80
MIN_OUTCOME_PA = 100
FLAT_THRESHOLD = 0.015
RTM_BASELINE   = 0.682

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

BIP_EVENTS = {
    'single', 'double', 'triple', 'field_out', 'grounded_into_double_play',
    'force_out', 'double_play', 'fielders_choice',
}

SIGNAL_MAP = {
    'BUY_LOW':    'IMPROVED',
    'SLIGHT_BUY': 'IMPROVED',
    'SELL_HIGH':  'DECLINED',
    'SLIGHT_SELL':'DECLINED',
}

# ------------------------------------------------------------------
# DATA LOADING
# ------------------------------------------------------------------

def load_data():
    print("Loading 2024 cache data...")
    april      = pd.read_csv(CACHE_DIR / "v4_april_2024.csv")
    outcome_raw = pd.read_csv(CACHE_DIR / "statcast_2024_may_july.csv")
    team_map   = pd.read_csv(CACHE_DIR / "team_map_2024.csv")
    print(f"  April: {len(april):,} rows  |  May-Jul: {len(outcome_raw):,} rows")
    return april, outcome_raw, team_map


def load_seasonal_patterns() -> dict:
    """Returns dict: player_id (int) -> pattern dict."""
    if not SEASONAL_PATH.exists():
        print(f"  WARNING: {SEASONAL_PATH} not found -- Phase C skipped")
        return {}
    with open(SEASONAL_PATH) as f:
        records = json.load(f)
    patterns = {int(r["player_id"]): r for r in records}
    print(f"  Seasonal patterns: {len(patterns):,} players loaded")
    return patterns

# ------------------------------------------------------------------
# APRIL SIGNALS  (identical to v2/v3)
# ------------------------------------------------------------------

def compute_april_signals(april_df, team_map_df) -> pd.DataFrame:
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
    ).reset_index()

    signals = pa_agg.merge(bip_agg, on='batter', how='left')
    signals['babip']      = np.where(signals['bip'] > 0, signals['hits_bip'] / signals['bip'], np.nan)
    signals['babip_luck'] = signals['babip'] - 0.300
    # Positive gap = actual < xwOBA = unlucky = BUY_LOW (matches score_luck.py convention)
    signals['xwoba_gap']  = signals['april_xwoba'] - signals['april_actual_woba']
    # Positive babip_luck = BABIP < .300 = unlucky = BUY_LOW (flip sign vs v2/v3)
    signals['luck_score'] = signals['xwoba_gap'] * 0.60 + (-signals['babip_luck']) * 0.40

    signals = signals[signals['april_pa'] >= MIN_APRIL_PA].copy()
    return signals

# ------------------------------------------------------------------
# PHASE C MODIFIER
# ------------------------------------------------------------------

def apply_seasonal_modifier(signals_df: pd.DataFrame, patterns: dict) -> pd.DataFrame:
    """
    Applies Phase C modifiers to a copy of signals_df.
    Adds columns: luck_score_v5, seasonal_modifier, seasonal_label.
    """
    df = signals_df.copy()

    modifiers = []
    labels    = []

    for _, row in df.iterrows():
        pid  = int(row['batter'])
        raw  = row['luck_score']

        if pid not in patterns:
            modifiers.append(1.0)
            labels.append(None)
            continue

        p       = patterns[pid]
        slow    = p.get('slow_starter', False)
        fader   = p.get('second_half_fader', False)
        summer  = p.get('summer_performer', False)
        is_buy  = raw > 0
        is_sell = raw < 0

        mult  = 1.0
        label = None

        # V-shape: slow starter + summer performer
        if slow and summer:
            if is_buy:
                mult  = 1.20
                label = 'V-shape (buy x1.20)'
            elif is_sell:
                mult  = 0.90
                label = 'V-shape (sell dampened x0.90)'

        # Slow starter only
        elif slow and not summer:
            if is_buy:
                mult  = 0.80
                label = 'Slow starter (buy dampened x0.80)'

        # Summer performer only
        elif summer and not slow:
            if is_buy:
                mult  = 1.10
                label = 'Summer performer (buy x1.10)'

        # Second half fader (independent -- stacks)
        if fader:
            if is_sell:
                mult  = max(mult, 1.15)
                label = (label + ' + fader (sell x1.15)') if label else 'Fader (sell x1.15)'
            elif is_buy:
                mult  = min(mult, 0.90)
                label = (label + ' + fader conflict') if label else 'Fader conflict (buy dampened x0.90)'

        modifiers.append(mult)
        labels.append(label)

    df['seasonal_modifier'] = modifiers
    df['seasonal_label']    = labels
    df['luck_score_v5']     = (df['luck_score'] * df['seasonal_modifier']).round(4)

    modified_count = (df['seasonal_modifier'] != 1.0).sum()
    print(f"  Phase C: {modified_count} players modified")
    vshape = df['seasonal_label'].str.contains('V-shape', na=False).sum()
    print(f"  V-shape amplifications: {vshape}")

    return df

# ------------------------------------------------------------------
# OUTCOMES
# ------------------------------------------------------------------

def compute_outcomes(signals_df, outcome_raw_df) -> pd.DataFrame:
    may_july = outcome_raw_df.groupby('batter').agg(
        outcome_pa=('woba_value', 'count'),
        outcome_woba=('woba_value', 'mean'),
    ).reset_index()

    merged = signals_df.merge(may_july, on='batter', how='inner')
    merged = merged[merged['outcome_pa'] >= MIN_OUTCOME_PA].copy()
    merged['woba_change'] = merged['outcome_woba'] - merged['april_actual_woba']
    return merged

# ------------------------------------------------------------------
# CLASSIFY + ACCURACY
# ------------------------------------------------------------------

def classify(df: pd.DataFrame, score_col: str) -> pd.DataFrame:
    out = df.copy()
    conditions = [
        out[score_col] >= 0.040,
        out[score_col] >= 0.020,
        out[score_col] <= -0.040,
        out[score_col] <= -0.020,
    ]
    out['signal'] = np.select(conditions, ['BUY_LOW', 'SLIGHT_BUY', 'SELL_HIGH', 'SLIGHT_SELL'], default='NEUTRAL')
    out['outcome'] = np.where(
        out['woba_change'] >=  FLAT_THRESHOLD, 'IMPROVED',
        np.where(out['woba_change'] <= -FLAT_THRESHOLD, 'DECLINED', 'FLAT')
    )
    return out


def bucket_stats(df: pd.DataFrame) -> dict:
    eval_df = df[df['signal'].isin(SIGNAL_MAP) & (df['outcome'] != 'FLAT')].copy()
    eval_df['correct'] = eval_df.apply(lambda r: r['outcome'] == SIGNAL_MAP[r['signal']], axis=1)
    stats = {}
    for sig in ['BUY_LOW', 'SLIGHT_BUY', 'SELL_HIGH', 'SLIGHT_SELL']:
        grp = eval_df[eval_df['signal'] == sig]
        n   = len(grp)
        c   = int(grp['correct'].sum()) if n > 0 else 0
        stats[sig] = (n, c, c / n if n > 0 else float('nan'))
    ov_n = len(eval_df)
    ov_c = int(eval_df['correct'].sum())
    stats['OVERALL'] = (ov_n, ov_c, ov_c / ov_n if ov_n > 0 else float('nan'))
    return stats

# ------------------------------------------------------------------
# REPORT
# ------------------------------------------------------------------

def report(merged_df: pd.DataFrame):
    # Col 1: v2 baseline (unmodified luck_score)
    v2_df   = classify(merged_df, 'luck_score')
    v2_stats = bucket_stats(v2_df)

    # Col 2: v5 Phase C (modified luck_score_v5)
    v5_df   = classify(merged_df, 'luck_score_v5')
    v5_stats = bucket_stats(v5_df)

    # Col 3: Phase C only -- players whose modifier != 1.0
    modified_mask = merged_df['seasonal_modifier'] != 1.0
    v5_mod_df     = v5_df[modified_mask].copy()
    v5_mod_stats  = bucket_stats(v5_mod_df)

    print("\n" + "=" * 100)
    print("WITHIN-SEASON BACKTEST v5 -- PHASE C SEASONAL MODIFIER EVALUATION")
    print("Signal: xwoba_gap*0.60 + babip_luck*0.40  |  Outcome: May-Jul vs April actual wOBA  |  April 2024")
    print("=" * 100)

    hdr = (
        f"\n{'':14}  "
        f"{'--- v2 Baseline ---':^24}  "
        f"{'--- v5 Phase C ---':^24}  "
        f"{'--- Phase C Players Only ---':^28}"
    )
    sub = (
        f"{'Signal':<14}  "
        f"{'N':>4} {'Acc':>7} {'vs RTM':>7}  "
        f"{'N':>4} {'Acc':>7} {'vs RTM':>7}  {'D Acc':>7}  "
        f"{'N':>4} {'Acc':>7} {'vs RTM':>7}"
    )
    div = "-" * 100
    print(hdr)
    print(sub)
    print(div)

    ORDER = ['BUY_LOW', 'SLIGHT_BUY', 'SELL_HIGH', 'SLIGHT_SELL', 'OVERALL']
    for sig in ORDER:
        v2n, v2c, v2a = v2_stats.get(sig, (0, 0, float('nan')))
        v5n, v5c, v5a = v5_stats.get(sig, (0, 0, float('nan')))
        mn,  mc,  ma  = v5_mod_stats.get(sig, (0, 0, float('nan')))

        v2_vs  = v2a - RTM_BASELINE if not pd.isna(v2a) else float('nan')
        v5_vs  = v5a - RTM_BASELINE if not pd.isna(v5a) else float('nan')
        m_vs   = ma  - RTM_BASELINE if not pd.isna(ma)  else float('nan')
        d_acc  = v5a - v2a          if not pd.isna(v5a) and not pd.isna(v2a) else float('nan')

        marker = ''
        if not pd.isna(d_acc) and abs(d_acc) >= 0.02:
            marker = ' <--'

        if sig == 'OVERALL':
            print(div)

        def fmt(a):
            return f'{a:>7.1%}' if not pd.isna(a) else '    n/a'
        def fmtd(a):
            return f'{a:>+7.1%}' if not pd.isna(a) else '    n/a'

        mod_part = f"  {mn:>4} {fmt(ma)} {fmtd(m_vs)}" if mn > 0 else "  (no modified players in bucket)"
        print(
            f"{sig:<14}  "
            f"{v2n:>4} {fmt(v2a)} {fmtd(v2_vs)}  "
            f"{v5n:>4} {fmt(v5a)} {fmtd(v5_vs)}  {fmtd(d_acc)}{marker}"
            f"{mod_part}"
        )

    # ------------------------------------------------------------------
    # MODIFIER BREAKDOWN TABLE
    # ------------------------------------------------------------------
    print(f"\n{'=' * 100}")
    print("MODIFIER BREAKDOWN -- accuracy by pattern type (v5 classified signals, non-flat outcomes only)")
    print(f"{'=' * 100}")
    print(f"  {'Pattern':<40} {'N':>5} {'Correct':>8} {'Acc':>8} {'vs RTM':>8}")
    print(f"  {'-'*75}")

    eval_v5 = v5_df[v5_df['signal'].isin(SIGNAL_MAP) & (v5_df['outcome'] != 'FLAT')].copy()
    eval_v5['correct'] = eval_v5.apply(lambda r: r['outcome'] == SIGNAL_MAP[r['signal']], axis=1)

    # Group by label (None = unmodified)
    eval_v5['label_group'] = eval_v5['seasonal_label'].fillna('No pattern (baseline)')

    for label, grp in eval_v5.groupby('label_group'):
        n = len(grp)
        if n < 3:
            continue
        c   = int(grp['correct'].sum())
        acc = c / n
        vs  = acc - RTM_BASELINE
        print(f"  {label:<40} {n:>5} {c:>8} {acc:>7.1%} {vs:>+8.1%}")

    # ------------------------------------------------------------------
    # SIGNAL MIGRATION TABLE
    # ------------------------------------------------------------------
    print(f"\n{'=' * 100}")
    print("SIGNAL MIGRATION -- how Phase C modifiers shifted players across signal buckets")
    print(f"{'=' * 100}")

    v2_sig = v2_df[['batter', 'signal']].rename(columns={'signal': 'v2_signal'})
    v5_sig = v5_df[['batter', 'signal']].rename(columns={'signal': 'v5_signal'})
    migration = v2_sig.merge(v5_sig, on='batter')
    migration = migration[migration['v2_signal'] != migration['v5_signal']].copy()

    print(f"  Players whose signal bucket changed: {len(migration)}")
    if len(migration) > 0:
        print(f"\n  {'v2 Signal':<16} -> {'v5 Signal':<16}  Count")
        print(f"  {'-'*46}")
        for (v2s, v5s), grp in migration.groupby(['v2_signal', 'v5_signal']):
            print(f"  {v2s:<16} -> {v5s:<16}  {len(grp)}")

    # ------------------------------------------------------------------
    # MEAN wOBA CHANGE
    # ------------------------------------------------------------------
    print(f"\nMEAN wOBA CHANGE BY SIGNAL (v5, raw -- no flat filter):")
    for sig in ['BUY_LOW', 'SLIGHT_BUY', 'NEUTRAL', 'SLIGHT_SELL', 'SELL_HIGH']:
        grp = v5_df[v5_df['signal'] == sig]
        if len(grp) < 3:
            continue
        print(f"  {sig:<14} n={len(grp):>3}  mean={grp['woba_change'].mean():>+.4f}  "
              f"median={grp['woba_change'].median():>+.4f}")

    # ------------------------------------------------------------------
    # VERDICT
    # ------------------------------------------------------------------
    print(f"\n{'=' * 100}")
    print("VERDICT")
    print(f"{'=' * 100}")
    v2_ov = v2_stats['OVERALL'][2]
    v5_ov = v5_stats['OVERALL'][2]
    v2_bl = v2_stats.get('BUY_LOW', (0, 0, float('nan')))[2]
    v5_bl = v5_stats.get('BUY_LOW', (0, 0, float('nan')))[2]

    for label, acc, baseline_acc in [
        ("v2 Baseline  ", v2_ov, None),
        ("v5 Phase C   ", v5_ov, v2_ov),
    ]:
        beat = "BEATS" if acc > RTM_BASELINE else "trails"
        pp   = abs(acc - RTM_BASELINE) * 100
        delta = f"  (D vs v2: {acc - baseline_acc:+.1%})" if baseline_acc is not None else ""
        print(f"  {label}: Overall {acc:.1%}  ({beat} RTM by {pp:.1f}pp){delta}")

    print(f"\n  BUY_LOW:  v2={v2_bl:.1%}  v5={v5_bl:.1%}  D={v5_bl - v2_bl:+.1%}")

    phase_c_improves = v5_ov > v2_ov
    buylow_improves  = v5_bl > v2_bl
    print(f"\n  Phase C improves overall accuracy:  {'YES' if phase_c_improves else 'NO'}")
    print(f"  Phase C improves BUY_LOW accuracy:  {'YES' if buylow_improves  else 'NO'}")


# ------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------

def main():
    print("Within-Season Backtest v5 -- Phase C Seasonal Modifier Evaluation")
    print("=" * 70)

    april_df, outcome_raw_df, team_map_df = load_data()

    print("\nComputing April signals...")
    signals_df = compute_april_signals(april_df, team_map_df)
    print(f"  {len(signals_df)} batters with >={MIN_APRIL_PA} April PA")
    vc = pd.cut(signals_df['luck_score'], bins=[-99, -0.040, -0.020, 0.020, 0.040, 99],
                labels=['SELL_HIGH', 'SLIGHT_SELL', 'NEUTRAL', 'SLIGHT_BUY', 'BUY_LOW'])
    for sig, count in vc.value_counts().items():
        print(f"    {sig:<14} {count}")

    print("\nLoading seasonal patterns...")
    patterns = load_seasonal_patterns()

    print("\nApplying Phase C modifiers...")
    signals_v5 = apply_seasonal_modifier(signals_df, patterns)

    print("\nAggregating May-July outcomes...")
    merged = compute_outcomes(signals_v5, outcome_raw_df)
    print(f"  {len(merged)} players with >={MIN_OUTCOME_PA} May-Jul PA")
    flat_n = (abs(merged['woba_change']) < FLAT_THRESHOLD).sum()
    print(f"  {flat_n} flat outcomes (|D wOBA| < {FLAT_THRESHOLD}) -- excluded from accuracy")

    report(merged)

    out_path = BASE_DIR / "backtest_results_within_season_v5.csv"
    merged.to_csv(out_path, index=False)
    print(f"\nFull results saved -> {out_path}")


if __name__ == "__main__":
    main()
