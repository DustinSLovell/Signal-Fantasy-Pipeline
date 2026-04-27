"""
Backtest Checkpoint — Temporal Signal Reliability
==================================================
Tests whether luck signal accuracy improves as the season progresses
and sample sizes grow.

Three checkpoints:
  CP1: April signals  -> May-July outcomes   (v4_april_2024.csv)
  CP2: May signals    -> Jun-Aug outcomes    (may_july filtered to month==5 -> month 6-8)
  CP3: July signals   -> Aug-Sep outcomes    (may_july filtered to month==7 -> aug_sep)

Signal: 2-component core luck (xwOBA gap + BABIP luck), same as v8 Layer 1
PA gates: >= 50 signal PA (lower for mid-season windows), >= 80 outcome PA
Flat threshold: +/- 0.015
RTM baseline: 68.2%

Key question: does SLIGHT_BUY accuracy improve from 66.7% (April) as
sample sizes grow in May (80-150 PA) and July (200+ PA)?
"""

import json
import numpy as np
import pandas as pd
from pathlib import Path

BASE_DIR   = Path(__file__).parent
CACHE_DIR  = BASE_DIR / "backtest_cache"
CAREER_PATH = BASE_DIR / "data" / "career_stats.json"

FLAT_THRESHOLD  = 0.015
RTM_BASELINE    = 0.682
MIN_SIGNAL_PA   = 50    # lower than April gate to keep enough players mid-season
MIN_OUTCOME_PA  = 80

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

# ------------------------------------------------------------------
# SIGNAL COMPUTATION
# ------------------------------------------------------------------

def compute_signals(raw_df: pd.DataFrame, team_map_df: pd.DataFrame,
                    min_pa: int) -> pd.DataFrame:
    df = raw_df.copy()
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
        signal_pa=('woba_value', 'count'),
        signal_actual_woba=('woba_value', 'mean'),
        signal_xwoba=('estimated_woba_using_speedangle', 'mean'),
    ).reset_index()

    signals = pa_agg.merge(bip_agg, on='batter', how='left')
    signals['babip'] = np.where(
        signals['bip'] > 0, signals['hits_bip'] / signals['bip'], np.nan
    )
    signals['xwoba_gap']  = signals['signal_xwoba'] - signals['signal_actual_woba']
    signals['babip_luck'] = 0.300 - signals['babip']
    signals['luck_score'] = (
        signals['xwoba_gap']  * 0.60 +
        signals['babip_luck'] * 0.40
    ).round(4)

    signals = signals[signals['signal_pa'] >= min_pa].copy()
    return signals


def compute_outcomes(outcome_df: pd.DataFrame) -> pd.DataFrame:
    return outcome_df.groupby('batter').agg(
        outcome_pa=('woba_value', 'count'),
        outcome_woba=('woba_value', 'mean'),
    ).reset_index()


def classify(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    conds = [
        out['luck_score'] >= 0.040,
        out['luck_score'] >= 0.020,
        out['luck_score'] <= -0.040,
        out['luck_score'] <= -0.020,
    ]
    out['signal'] = np.select(conds,
        ['BUY_LOW', 'SLIGHT_BUY', 'SELL_HIGH', 'SLIGHT_SELL'], default='NEUTRAL')
    out['outcome_label'] = np.where(
        out['woba_change'] >=  FLAT_THRESHOLD, 'IMPROVED',
        np.where(out['woba_change'] <= -FLAT_THRESHOLD, 'DECLINED', 'FLAT')
    )
    return out


def bucket_stats(df: pd.DataFrame) -> dict:
    eval_df = df[df['signal'].isin(SIGNAL_MAP) & (df['outcome_label'] != 'FLAT')].copy()
    eval_df['correct'] = eval_df.apply(
        lambda r: r['outcome_label'] == SIGNAL_MAP[r['signal']], axis=1
    )
    stats = {}
    for sig in ['BUY_LOW', 'SLIGHT_BUY', 'SELL_HIGH', 'SLIGHT_SELL']:
        grp = eval_df[eval_df['signal'] == sig]
        n, c = len(grp), int(grp['correct'].sum()) if len(grp) > 0 else 0
        stats[sig] = (n, c, c / n if n > 0 else float('nan'))
    ov_n = len(eval_df)
    ov_c = int(eval_df['correct'].sum())
    stats['OVERALL'] = (ov_n, ov_c, ov_c / ov_n if ov_n > 0 else float('nan'))
    return stats


# ------------------------------------------------------------------
# CHECKPOINT RUNNER
# ------------------------------------------------------------------

def run_checkpoint(label: str, signal_window: str, outcome_window: str,
                   signal_df_raw: pd.DataFrame, outcome_df_raw: pd.DataFrame,
                   team_map: pd.DataFrame, min_signal_pa: int = MIN_SIGNAL_PA) -> tuple:
    print(f"\n  [{label}] signal={signal_window} -> outcome={outcome_window}")

    signals  = compute_signals(signal_df_raw, team_map, min_signal_pa)
    outcomes = compute_outcomes(outcome_df_raw)

    merged = signals.merge(outcomes, on='batter', how='inner')
    before = len(merged)
    merged = merged[merged['outcome_pa'] >= MIN_OUTCOME_PA].copy()
    merged['woba_change'] = merged['outcome_woba'] - merged['signal_actual_woba']
    flat_n = (merged['woba_change'].abs() < FLAT_THRESHOLD).sum()

    print(f"    {len(signals)} signal batters (>={min_signal_pa} PA)  "
          f"|  {before} matched  "
          f"|  {len(merged)} with >={MIN_OUTCOME_PA} outcome PA  "
          f"|  {flat_n} flat")

    classified = classify(merged)
    stats = bucket_stats(classified)

    med_pa = merged['signal_pa'].median()
    print(f"    Median signal PA: {med_pa:.0f}")

    return classified, stats, merged


# ------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------

def main():
    print("Backtest Checkpoint -- Temporal Signal Reliability")
    print("=" * 70)

    team_map = pd.read_csv(CACHE_DIR / "team_map_2024.csv")

    # Raw data
    april_raw  = pd.read_csv(CACHE_DIR / "v4_april_2024.csv")
    mj_raw     = pd.read_csv(CACHE_DIR / "statcast_2024_may_july.csv")
    aug_sep    = pd.read_csv(CACHE_DIR / "statcast_2024_aug_sep.csv")

    # Parse dates for month filtering
    mj_raw['month'] = pd.to_datetime(mj_raw['game_date']).dt.month

    # Signal windows
    may_signal  = mj_raw[mj_raw['month'] == 5].drop(columns='month')
    july_signal = mj_raw[mj_raw['month'] == 7].drop(columns='month')

    # Outcome windows
    # CP2: June-August = months 6+7 from may_july + all of aug_sep
    june_july   = mj_raw[mj_raw['month'].isin([6, 7])].drop(columns='month')
    jun_aug_out = pd.concat([june_july, aug_sep], ignore_index=True)

    print("\nRunning checkpoints...")

    cp1_df, cp1_stats, cp1_merged = run_checkpoint(
        label="CP1", signal_window="April",
        outcome_window="May-July",
        signal_df_raw=april_raw,
        outcome_df_raw=mj_raw.drop(columns='month'),
        team_map=team_map,
        min_signal_pa=80,
    )

    cp2_df, cp2_stats, cp2_merged = run_checkpoint(
        label="CP2", signal_window="May",
        outcome_window="Jun-Aug",
        signal_df_raw=may_signal,
        outcome_df_raw=jun_aug_out,
        team_map=team_map,
        min_signal_pa=MIN_SIGNAL_PA,
    )

    cp3_df, cp3_stats, cp3_merged = run_checkpoint(
        label="CP3", signal_window="July",
        outcome_window="Aug-Sep",
        signal_df_raw=july_signal,
        outcome_df_raw=aug_sep,
        team_map=team_map,
        min_signal_pa=MIN_SIGNAL_PA,
    )

    # ------------------------------------------------------------------
    # REPORT
    # ------------------------------------------------------------------
    WIDTH = 110
    print("\n" + "=" * WIDTH)
    print("CHECKPOINT ACCURACY -- TEMPORAL SIGNAL RELIABILITY")
    print(f"Key question: does SLIGHT_BUY improve from 66.7% (April) as sample sizes grow?")
    print("=" * WIDTH)

    checkpoints = [
        ("CP1: April -> May-Jul  ", cp1_stats, cp1_merged),
        ("CP2: May   -> Jun-Aug  ", cp2_stats, cp2_merged),
        ("CP3: July  -> Aug-Sep  ", cp3_stats, cp3_merged),
    ]

    hdr = (
        f"\n{'':28}  "
        f"{'BUY_LOW':^22}  "
        f"{'SLIGHT_BUY':^22}  "
        f"{'SLIGHT_SELL':^22}  "
        f"{'SELL_HIGH':^22}  "
        f"{'OVERALL':^22}"
    )
    sub = (
        f"{'Checkpoint':<28}  "
        f"{'N':>4} {'Acc':>7} {'vs RTM':>7}  " * 5
    )
    div = "-" * WIDTH
    print(hdr)
    print(sub)
    print(div)

    for label, stats, merged_df in checkpoints:
        med_pa = merged_df['signal_pa'].median()
        row_parts = [f"{label} (med PA={med_pa:.0f})  "]
        for sig in ['BUY_LOW', 'SLIGHT_BUY', 'SLIGHT_SELL', 'SELL_HIGH', 'OVERALL']:
            n, c, acc = stats.get(sig, (0, 0, float('nan')))
            acc_str = f"{acc:>7.1%}" if not pd.isna(acc) else "    n/a"
            vs_rtm  = f"{acc - RTM_BASELINE:>+7.1%}" if not pd.isna(acc) else "    n/a"
            row_parts.append(f"{n:>4} {acc_str} {vs_rtm}  ")
        # pad label to consistent width
        label_col = f"{label} (med PA={med_pa:.0f})"
        print(f"{label_col:<30}  " + "".join(row_parts[1:]))

    # ------------------------------------------------------------------
    # SLIGHT_BUY DEEP DIVE
    # ------------------------------------------------------------------
    print(f"\n{'=' * WIDTH}")
    print("SLIGHT_BUY DEEP DIVE -- accuracy trend by checkpoint")
    print(f"{'=' * WIDTH}")
    print(f"  {'Checkpoint':<30} {'N':>5} {'Correct':>8} {'Acc':>8} {'vs RTM':>8}  {'Med signal PA':>14}")
    print(f"  {'-' * 80}")

    for label, stats, merged_df in checkpoints:
        n, c, acc = stats.get('SLIGHT_BUY', (0, 0, float('nan')))
        med_pa = merged_df[
            merged_df['luck_score'].between(0.020, 0.040)
        ]['signal_pa'].median()
        vs_rtm = f"{acc - RTM_BASELINE:>+8.1%}" if not pd.isna(acc) else "     n/a"
        acc_str = f"{acc:>8.1%}" if not pd.isna(acc) else "     n/a"
        threshold_met = "YES (>= 70%)" if not pd.isna(acc) and acc >= 0.70 else "no"
        print(f"  {label:<30} {n:>5} {c:>8} {acc_str} {vs_rtm}  {med_pa:>14.0f}  {threshold_met}")

    # ------------------------------------------------------------------
    # PA DISTRIBUTION WITHIN SLIGHT_BUY
    # ------------------------------------------------------------------
    print(f"\n{'=' * WIDTH}")
    print("SLIGHT_BUY -- PA DISTRIBUTION AND ACCURACY BY PA BAND")
    print(f"{'=' * WIDTH}")
    all_slight = []
    for label, stats, merged_df in checkpoints:
        tmp = merged_df[
            merged_df['luck_score'].between(0.020, 0.039999)
        ].copy()
        tmp['checkpoint'] = label.split(':')[0].strip()
        all_slight.append(tmp)
    slight_df = pd.concat(all_slight, ignore_index=True)

    slight_df['outcome_label'] = np.where(
        slight_df['woba_change'] >= FLAT_THRESHOLD, 'IMPROVED',
        np.where(slight_df['woba_change'] <= -FLAT_THRESHOLD, 'DECLINED', 'FLAT')
    )
    slight_df = slight_df[slight_df['outcome_label'] != 'FLAT'].copy()
    slight_df['correct'] = slight_df['outcome_label'] == 'IMPROVED'

    pa_bins = [0, 60, 80, 100, 130, 200, 9999]
    pa_labels = ['<60', '60-80', '80-100', '100-130', '130-200', '200+']
    slight_df['pa_band'] = pd.cut(slight_df['signal_pa'], bins=pa_bins, labels=pa_labels)

    print(f"  {'PA Band':<12} {'N':>5} {'Correct':>8} {'Acc':>8} {'vs RTM':>8}")
    print(f"  {'-' * 50}")
    for band in pa_labels:
        grp = slight_df[slight_df['pa_band'] == band]
        if len(grp) < 2:
            continue
        n = len(grp)
        c = int(grp['correct'].sum())
        acc = c / n
        print(f"  {band:<12} {n:>5} {c:>8} {acc:>7.1%} {acc - RTM_BASELINE:>+8.1%}")

    # ------------------------------------------------------------------
    # VERDICT
    # ------------------------------------------------------------------
    print(f"\n{'=' * WIDTH}")
    print("VERDICT -- Does SLIGHT_BUY improve over time?")
    print(f"{'=' * WIDTH}")
    for label, stats, merged_df in checkpoints:
        n, c, acc = stats.get('SLIGHT_BUY', (0, 0, float('nan')))
        ov_n, ov_c, ov_a = stats.get('OVERALL', (0, 0, float('nan')))
        med_pa = merged_df['signal_pa'].median()
        acc_str = f"{acc:.1%}" if not pd.isna(acc) else "n/a"
        ov_str  = f"{ov_a:.1%}" if not pd.isna(ov_a) else "n/a"
        print(f"  {label.strip():<28}  SLIGHT_BUY={acc_str} (n={n})  OVERALL={ov_str}  med_PA={med_pa:.0f}")

    cp1_sb = cp1_stats.get('SLIGHT_BUY', (0, 0, float('nan')))[2]
    cp2_sb = cp2_stats.get('SLIGHT_BUY', (0, 0, float('nan')))[2]
    cp3_sb = cp3_stats.get('SLIGHT_BUY', (0, 0, float('nan')))[2]
    improving = (not pd.isna(cp2_sb) and cp2_sb > cp1_sb) and \
                (not pd.isna(cp3_sb) and cp3_sb > cp2_sb)
    print(f"\n  Monotonically improving CP1 -> CP2 -> CP3? {'YES' if improving else 'NO'}")
    if not pd.isna(cp3_sb):
        print(f"  July SLIGHT_BUY >= 70%? {'YES' if cp3_sb >= 0.70 else 'NO'} ({cp3_sb:.1%})")
        print(f"  July SLIGHT_BUY >= 75%? {'YES' if cp3_sb >= 0.75 else 'NO'} ({cp3_sb:.1%})")


if __name__ == "__main__":
    main()
