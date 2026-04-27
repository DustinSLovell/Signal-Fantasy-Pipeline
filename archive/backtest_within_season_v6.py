"""
Within-Season Backtest v6
=========================
Four-layer incremental evaluation of signal enrichments.

Signal window:  April 2024  (v4_april_2024.csv)
Outcome window: May-July 2024  (statcast_2024_may_july.csv)
Outcome metric: May-July wOBA vs April actual wOBA
PA gates:       >= 80 April PA, >= 100 May-July PA
Flat threshold: +/- 0.015
RTM baseline:   68.2%

Sign convention (matches score_luck.py / v5):
  positive luck_score = unlucky = BUY_LOW
  xwoba_gap  = xwOBA - actual    (positive = actual < xwOBA = unlucky)
  babip_luck = 0.300 - babip     (positive = below-avg BABIP = unlucky)

Layer stack:
  Layer 1 — Core:           luck_score = xwoba_gap*0.60 + babip_luck*0.40
  Layer 2 — Sweet spot:     >0.12 & buy -> x1.05 | <0.06 & buy -> x0.95
  Layer 3 — EV trend:       current EV < career by >2 mph & buy -> x0.85
  Layer 4 — Phase C:        V-shape/slow/summer/fader modifiers

Sweet spot rate and avg exit velocity computed directly from v4_april_2024.csv
(same data used for the core signal — temporally clean).
Career exit velocity from data/career_stats.json (2022-2024 April averages).

Output: four side-by-side columns + Phase C players column.
"""

import json
import os
import numpy as np
import pandas as pd
from pathlib import Path

# ------------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------------

BASE_DIR      = Path(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR     = BASE_DIR / "backtest_cache"
SEASONAL_PATH = BASE_DIR / "data" / "seasonal_patterns.json"
CAREER_PATH   = BASE_DIR / "data" / "career_stats.json"

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
    april       = pd.read_csv(CACHE_DIR / "v4_april_2024.csv")
    outcome_raw = pd.read_csv(CACHE_DIR / "statcast_2024_may_july.csv")
    team_map    = pd.read_csv(CACHE_DIR / "team_map_2024.csv")
    print(f"  April: {len(april):,} rows  |  May-Jul: {len(outcome_raw):,} rows")
    return april, outcome_raw, team_map


def load_career_stats() -> dict:
    if not CAREER_PATH.exists():
        print(f"  WARNING: {CAREER_PATH} not found -- Layer 3 (EV trend) skipped")
        return {}
    with open(CAREER_PATH) as f:
        raw = json.load(f)
    cs = {int(k): v for k, v in raw.items()}
    ev_count = sum(1 for v in cs.values() if v.get("avg_exit_velocity") is not None)
    print(f"  Career stats: {len(cs):,} players  |  {ev_count:,} with avg_exit_velocity")
    return cs


def load_seasonal_patterns() -> dict:
    if not SEASONAL_PATH.exists():
        print(f"  WARNING: {SEASONAL_PATH} not found -- Layer 4 (Phase C) skipped")
        return {}
    with open(SEASONAL_PATH) as f:
        records = json.load(f)
    patterns = {int(r["player_id"]): r for r in records}
    print(f"  Seasonal patterns: {len(patterns):,} players loaded")
    return patterns

# ------------------------------------------------------------------
# LAYER 1 — CORE SIGNAL
# ------------------------------------------------------------------

def compute_layer1(april_df: pd.DataFrame, team_map_df: pd.DataFrame) -> pd.DataFrame:
    """
    Per-batter April luck signal.
    Also computes sweet_spot_rate and avg_exit_velocity from the same data
    for use in Layers 2 and 3 (temporally clean — same window, no lookahead).
    """
    df = april_df.copy()
    df = df.merge(team_map_df, on='batter', how='left')
    df['park_factor'] = df['team'].map(PARK_FACTORS).fillna(1.0)

    # -- BIP subset for BABIP --
    batted = df[df['bb_type'].notna() & (df['bb_type'] != '')].copy()
    batted['is_bip']     = batted['events'].isin(BIP_EVENTS).astype(int)
    batted['is_hit_bip'] = batted['events'].isin({'single', 'double', 'triple'}).astype(int)

    bip_agg = batted.groupby('batter').agg(
        bip=('is_bip', 'sum'),
        hits_bip=('is_hit_bip', 'sum'),
    ).reset_index()

    # -- Batted ball subset for sweet spot + exit velocity --
    bbe = df[df['launch_speed'].notna() & df['launch_angle'].notna()].copy()

    bbe_agg = bbe.groupby('batter').apply(
        lambda s: pd.Series({
            'sweet_spot_count': ((s['launch_speed'] >= 98) & s['launch_angle'].between(8, 32)).sum(),
            'bbe_total':        len(s),
            'avg_exit_velocity': s['launch_speed'].mean(),
        })
    ).reset_index()

    # -- PA-level aggregation --
    pa_agg = df.groupby('batter').agg(
        april_pa=('woba_value', 'count'),
        april_actual_woba=('woba_value', 'mean'),
        april_xwoba=('estimated_woba_using_speedangle', 'mean'),
    ).reset_index()

    # -- Merge all --
    signals = pa_agg.merge(bip_agg,  on='batter', how='left')
    signals = signals.merge(bbe_agg, on='batter', how='left')

    # -- Derived metrics --
    signals['babip'] = np.where(
        signals['bip'] > 0, signals['hits_bip'] / signals['bip'], np.nan
    )

    # xwoba_gap positive = actual < xwOBA = unlucky = BUY signal
    signals['xwoba_gap']  = signals['april_xwoba']        - signals['april_actual_woba']
    # babip_luck positive = BABIP < .300 = unlucky = BUY signal
    signals['babip_luck'] = 0.300                         - signals['babip']

    signals['luck_score_L1'] = (
        signals['xwoba_gap']  * 0.60 +
        signals['babip_luck'] * 0.40
    ).round(4)

    signals['sweet_spot_rate'] = np.where(
        signals['bbe_total'] > 0,
        signals['sweet_spot_count'] / signals['bbe_total'], np.nan
    )

    # Apply PA gate
    signals = signals[signals['april_pa'] >= MIN_APRIL_PA].copy()
    return signals

# ------------------------------------------------------------------
# LAYER 2 — SWEET SPOT MODIFIER
# ------------------------------------------------------------------

def apply_layer2(df: pd.DataFrame) -> pd.DataFrame:
    """High sweet spot amplifies buy; low sweet spot dampens buy."""
    out = df.copy()
    out['luck_score_L2'] = out['luck_score_L1'].copy()

    buy_mask  = out['luck_score_L2'] > 0
    high_ss   = buy_mask & (out['sweet_spot_rate'] > 0.12)
    low_ss    = buy_mask & (out['sweet_spot_rate'] < 0.06)

    out.loc[high_ss, 'luck_score_L2'] = (out.loc[high_ss, 'luck_score_L2'] * 1.05).round(4)
    out.loc[low_ss,  'luck_score_L2'] = (out.loc[low_ss,  'luck_score_L2'] * 0.95).round(4)

    n_high = high_ss.sum()
    n_low  = low_ss.sum()
    print(f"  Layer 2 (sweet spot): {n_high} buy signals amplified x1.05  |  {n_low} dampened x0.95")
    return out

# ------------------------------------------------------------------
# LAYER 3 — EXIT VELOCITY TREND MODIFIER
# ------------------------------------------------------------------

def apply_layer3(df: pd.DataFrame, career_stats: dict) -> pd.DataFrame:
    """Current EV more than 2 mph below career baseline -> dampen buy signal."""
    out = df.copy()
    out['luck_score_L3'] = out['luck_score_L2'].copy()

    dampened = 0
    for idx, row in out.iterrows():
        if row['luck_score_L3'] <= 0:
            continue
        career_ev = (career_stats.get(int(row['batter'])) or {}).get('avg_exit_velocity')
        if career_ev is None or pd.isna(row['avg_exit_velocity']):
            continue
        if (row['avg_exit_velocity'] - career_ev) < -2.0:
            out.at[idx, 'luck_score_L3'] = round(row['luck_score_L3'] * 0.85, 4)
            dampened += 1

    print(f"  Layer 3 (EV trend):   {dampened} buy signals dampened x0.85 (EV >2 mph below career)")
    return out

# ------------------------------------------------------------------
# LAYER 4 — PHASE C SEASONAL MODIFIER
# ------------------------------------------------------------------

def apply_layer4(df: pd.DataFrame, patterns: dict) -> pd.DataFrame:
    """V-shape / slow-starter / summer / fader pattern modifiers."""
    out = df.copy()
    out['luck_score_L4']    = out['luck_score_L3'].copy()
    out['seasonal_modifier'] = 1.0
    out['seasonal_label']    = None

    if not patterns:
        print("  Layer 4 (Phase C):   no patterns loaded -- skipped")
        return out

    modified = 0
    vshape   = 0

    for idx, row in out.iterrows():
        pid  = int(row['batter'])
        raw  = row['luck_score_L4']

        if pid not in patterns:
            continue

        p      = patterns[pid]
        slow   = p.get('slow_starter', False)
        fader  = p.get('second_half_fader', False)
        summer = p.get('summer_performer', False)
        is_buy  = raw > 0
        is_sell = raw < 0

        mult  = 1.0
        label = None

        if slow and summer:
            if is_buy:
                mult, label = 1.20, 'V-shape (buy x1.20)'
                vshape += 1
            elif is_sell:
                mult, label = 0.90, 'V-shape (sell dampened x0.90)'
        elif slow and not summer:
            if is_buy:
                mult, label = 0.80, 'Slow starter (buy dampened x0.80)'
        elif summer and not slow:
            if is_buy:
                mult, label = 1.10, 'Summer performer (buy x1.10)'

        if fader:
            if is_sell:
                mult  = max(mult, 1.15)
                label = (label + ' + fader (sell x1.15)') if label else 'Fader (sell x1.15)'
            elif is_buy:
                mult  = min(mult, 0.90)
                label = (label + ' + fader conflict') if label else 'Fader conflict (buy dampened x0.90)'

        if mult != 1.0:
            out.at[idx, 'luck_score_L4']    = round(raw * mult, 4)
            out.at[idx, 'seasonal_modifier'] = mult
            out.at[idx, 'seasonal_label']    = label
            modified += 1

    print(f"  Layer 4 (Phase C):   {modified} players modified  |  {vshape} V-shape amplifications")
    return out

# ------------------------------------------------------------------
# OUTCOMES
# ------------------------------------------------------------------

def compute_outcomes(signals_df: pd.DataFrame, outcome_raw_df: pd.DataFrame) -> pd.DataFrame:
    may_july = outcome_raw_df.groupby('batter').agg(
        outcome_pa=('woba_value', 'count'),
        outcome_woba=('woba_value', 'mean'),
    ).reset_index()

    merged = signals_df.merge(may_july, on='batter', how='inner')
    before = len(merged)
    merged = merged[merged['outcome_pa'] >= MIN_OUTCOME_PA].copy()
    excluded = before - len(merged)
    merged['woba_change'] = merged['outcome_woba'] - merged['april_actual_woba']

    print(f"  {before} matched  |  {excluded} excluded (<{MIN_OUTCOME_PA} May-Jul PA)  "
          f"->  {len(merged)} evaluable")
    flat_n = (merged['woba_change'].abs() < FLAT_THRESHOLD).sum()
    print(f"  {flat_n} flat outcomes (|D wOBA| < {FLAT_THRESHOLD}) excluded from accuracy")
    return merged

# ------------------------------------------------------------------
# CLASSIFY + ACCURACY HELPERS
# ------------------------------------------------------------------

def classify(df: pd.DataFrame, score_col: str) -> pd.DataFrame:
    out = df.copy()
    conds = [
        out[score_col] >= 0.040,
        out[score_col] >= 0.020,
        out[score_col] <= -0.040,
        out[score_col] <= -0.020,
    ]
    out['signal'] = np.select(conds, ['BUY_LOW', 'SLIGHT_BUY', 'SELL_HIGH', 'SLIGHT_SELL'],
                              default='NEUTRAL')
    out['outcome'] = np.where(
        out['woba_change'] >=  FLAT_THRESHOLD, 'IMPROVED',
        np.where(out['woba_change'] <= -FLAT_THRESHOLD, 'DECLINED', 'FLAT')
    )
    return out


def bucket_stats(df: pd.DataFrame) -> dict:
    eval_df = df[df['signal'].isin(SIGNAL_MAP) & (df['outcome'] != 'FLAT')].copy()
    eval_df['correct'] = eval_df.apply(
        lambda r: r['outcome'] == SIGNAL_MAP[r['signal']], axis=1
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
# REPORT
# ------------------------------------------------------------------

def report(merged_df: pd.DataFrame):
    # Classify at each layer
    d1 = classify(merged_df, 'luck_score_L1')
    d2 = classify(merged_df, 'luck_score_L2')
    d3 = classify(merged_df, 'luck_score_L3')
    d4 = classify(merged_df, 'luck_score_L4')

    s1 = bucket_stats(d1)
    s2 = bucket_stats(d2)
    s3 = bucket_stats(d3)
    s4 = bucket_stats(d4)

    # Phase C players only (seasonal_modifier changed)
    phase_c_mask = merged_df['seasonal_modifier'] != 1.0
    s4c = bucket_stats(d4[phase_c_mask])

    WIDTH = 124
    print("\n" + "=" * WIDTH)
    print("WITHIN-SEASON BACKTEST v6 -- LAYER-BY-LAYER SIGNAL EVALUATION")
    print("Signal: April 2024 -> May-July 2024  |  Flat: ±0.015  |  RTM baseline: 68.2%")
    print("=" * WIDTH)

    hdr = (
        f"\n{'':14}  "
        f"{'--- L1: Core (v2 baseline) ---':^26}  "
        f"{'--- L1+2: +Sweet Spot ---':^26}  "
        f"{'--- L1+2+3: +EV Trend ---':^26}  "
        f"{'--- L1+2+3+4: Full v6 ---':^26}  "
        f"{'--- Phase C Only ---':^22}"
    )
    sub = (
        f"{'Signal':<14}  "
        f"{'N':>4} {'Acc':>7} {'vs RTM':>7}  "
        f"{'N':>4} {'Acc':>7} {'D':>7}  "
        f"{'N':>4} {'Acc':>7} {'D':>7}  "
        f"{'N':>4} {'Acc':>7} {'D':>7}  "
        f"{'N':>4} {'Acc':>7} {'vs RTM':>7}"
    )
    div = "-" * WIDTH

    print(hdr)
    print(sub)
    print(div)

    ORDER = ['BUY_LOW', 'SLIGHT_BUY', 'SELL_HIGH', 'SLIGHT_SELL', 'OVERALL']
    for sig in ORDER:
        if sig == 'OVERALL':
            print(div)

        v1n, v1c, v1a = s1.get(sig, (0, 0, float('nan')))
        v2n, v2c, v2a = s2.get(sig, (0, 0, float('nan')))
        v3n, v3c, v3a = s3.get(sig, (0, 0, float('nan')))
        v4n, v4c, v4a = s4.get(sig, (0, 0, float('nan')))
        cn,  cc,  ca  = s4c.get(sig, (0, 0, float('nan')))

        def fmt(a):
            return f'{a:>7.1%}' if not pd.isna(a) else '    n/a'
        def fmtd(a):
            return f'{a:>+7.1%}' if not pd.isna(a) else '    n/a'

        delta2 = v2a - v1a if not pd.isna(v2a) and not pd.isna(v1a) else float('nan')
        delta3 = v3a - v1a if not pd.isna(v3a) and not pd.isna(v1a) else float('nan')
        delta4 = v4a - v1a if not pd.isna(v4a) and not pd.isna(v1a) else float('nan')
        c_vs   = ca - RTM_BASELINE if not pd.isna(ca) else float('nan')

        marker4 = ' <--' if not pd.isna(delta4) and abs(delta4) >= 0.02 else '    '

        phase_c_col = f"  {cn:>4} {fmt(ca)} {fmtd(c_vs)}" if cn > 0 else "  (none in bucket)"

        print(
            f"{sig:<14}  "
            f"{v1n:>4} {fmt(v1a)} {fmtd(v1a - RTM_BASELINE if not pd.isna(v1a) else float('nan'))}  "
            f"{v2n:>4} {fmt(v2a)} {fmtd(delta2)}  "
            f"{v3n:>4} {fmt(v3a)} {fmtd(delta3)}  "
            f"{v4n:>4} {fmt(v4a)} {fmtd(delta4)}{marker4}"
            f"{phase_c_col}"
        )

    # ------------------------------------------------------------------
    # SWEET SPOT BREAKDOWN
    # ------------------------------------------------------------------
    print(f"\n{'=' * WIDTH}")
    print("LAYER 2 DETAIL — accuracy by sweet spot tier (L1+2 signals, non-flat outcomes)")
    print(f"{'=' * WIDTH}")
    eval2 = d2[d2['signal'].isin(SIGNAL_MAP) & (d2['outcome'] != 'FLAT')].copy()
    eval2['correct'] = eval2.apply(lambda r: r['outcome'] == SIGNAL_MAP[r['signal']], axis=1)
    eval2['ss_tier'] = pd.cut(
        eval2['sweet_spot_rate'],
        bins=[-0.001, 0.06, 0.10, 0.12, 0.16, 1.0],
        labels=['<6% (low)', '6-10%', '10-12%', '12-16%', '>16% (high)'],
    )
    print(f"  {'Sweet Spot Tier':<18} {'N':>5} {'Correct':>8} {'Acc':>8} {'vs RTM':>8}")
    print(f"  {'-' * 52}")
    for tier, grp in eval2.groupby('ss_tier', observed=True):
        n = len(grp)
        if n < 3:
            continue
        c   = int(grp['correct'].sum())
        acc = c / n
        print(f"  {str(tier):<18} {n:>5} {c:>8} {acc:>7.1%} {acc - RTM_BASELINE:>+8.1%}")

    # ------------------------------------------------------------------
    # EXIT VELOCITY BREAKDOWN
    # ------------------------------------------------------------------
    print(f"\n{'=' * WIDTH}")
    print("LAYER 3 DETAIL — accuracy by EV vs career baseline (L1+2+3 signals, buy-only, non-flat)")
    print(f"{'=' * WIDTH}")
    eval3 = d3[d3['signal'].isin(['BUY_LOW', 'SLIGHT_BUY']) & (d3['outcome'] != 'FLAT')].copy()
    eval3['correct'] = eval3.apply(lambda r: r['outcome'] == SIGNAL_MAP[r['signal']], axis=1)

    career_ev_lookup = {}
    if CAREER_PATH.exists():
        with open(CAREER_PATH) as f:
            raw = json.load(f)
        career_ev_lookup = {int(k): (v.get('avg_exit_velocity')) for k, v in raw.items()}

    eval3['career_ev'] = eval3['batter'].map(career_ev_lookup)
    eval3['ev_delta']  = eval3['avg_exit_velocity'] - eval3['career_ev']

    def ev_tier(delta):
        if pd.isna(delta):
            return 'No career baseline'
        if delta < -4.0:
            return '< -4 mph (severe decline)'
        if delta < -2.0:
            return '-4 to -2 mph (dampened)'
        if delta < 0:
            return '-2 to 0 mph (slight dip)'
        if delta < 2.0:
            return '0 to +2 mph (stable)'
        return '> +2 mph (trending up)'

    eval3['ev_tier'] = eval3['ev_delta'].apply(ev_tier)
    tier_order = ['< -4 mph (severe decline)', '-4 to -2 mph (dampened)',
                  '-2 to 0 mph (slight dip)', '0 to +2 mph (stable)',
                  '> +2 mph (trending up)', 'No career baseline']
    print(f"  {'EV vs Career Tier':<28} {'N':>5} {'Correct':>8} {'Acc':>8} {'vs RTM':>8}")
    print(f"  {'-' * 62}")
    for tier in tier_order:
        grp = eval3[eval3['ev_tier'] == tier]
        n = len(grp)
        if n < 3:
            continue
        c   = int(grp['correct'].sum())
        acc = c / n
        print(f"  {tier:<28} {n:>5} {c:>8} {acc:>7.1%} {acc - RTM_BASELINE:>+8.1%}")

    # ------------------------------------------------------------------
    # PHASE C BREAKDOWN (same as v5)
    # ------------------------------------------------------------------
    print(f"\n{'=' * WIDTH}")
    print("LAYER 4 DETAIL — accuracy by seasonal pattern type (full v6, non-flat outcomes)")
    print(f"{'=' * WIDTH}")
    eval4 = d4[d4['signal'].isin(SIGNAL_MAP) & (d4['outcome'] != 'FLAT')].copy()
    eval4['correct'] = eval4.apply(lambda r: r['outcome'] == SIGNAL_MAP[r['signal']], axis=1)
    eval4['label_group'] = eval4['seasonal_label'].fillna('No pattern (baseline)')
    print(f"  {'Pattern':<42} {'N':>5} {'Correct':>8} {'Acc':>8} {'vs RTM':>8}")
    print(f"  {'-' * 72}")
    for label, grp in eval4.groupby('label_group'):
        n = len(grp)
        if n < 3:
            continue
        c   = int(grp['correct'].sum())
        acc = c / n
        print(f"  {label:<42} {n:>5} {c:>8} {acc:>7.1%} {acc - RTM_BASELINE:>+8.1%}")

    # ------------------------------------------------------------------
    # SIGNAL MIGRATION TABLE
    # ------------------------------------------------------------------
    print(f"\n{'=' * WIDTH}")
    print("SIGNAL MIGRATION — players whose bucket changed L1 -> Full v6 (Layer 1+2+3+4)")
    print(f"{'=' * WIDTH}")
    mig = (
        d1[['batter', 'signal']].rename(columns={'signal': 'L1'})
          .merge(d4[['batter', 'signal']].rename(columns={'signal': 'L4'}), on='batter')
    )
    changed = mig[mig['L1'] != mig['L4']]
    print(f"  Players whose signal bucket changed: {len(changed)}")
    if len(changed) > 0:
        print(f"\n  {'L1 Signal':<16} -> {'v6 Signal':<16}  Count")
        print(f"  {'-' * 48}")
        for (l1s, l4s), grp in changed.groupby(['L1', 'L4']):
            print(f"  {l1s:<16} -> {l4s:<16}  {len(grp)}")

    # ------------------------------------------------------------------
    # MEAN wOBA CHANGE
    # ------------------------------------------------------------------
    print(f"\nMEAN wOBA CHANGE BY SIGNAL (full v6, raw — no flat filter):")
    for sig in ['BUY_LOW', 'SLIGHT_BUY', 'NEUTRAL', 'SLIGHT_SELL', 'SELL_HIGH']:
        grp = d4[d4['signal'] == sig]
        if len(grp) < 3:
            continue
        print(f"  {sig:<14} n={len(grp):>3}  mean={grp['woba_change'].mean():>+.4f}  "
              f"median={grp['woba_change'].median():>+.4f}")

    # ------------------------------------------------------------------
    # VERDICT
    # ------------------------------------------------------------------
    print(f"\n{'=' * WIDTH}")
    print("VERDICT")
    print(f"{'=' * WIDTH}")

    for label, st in [
        ("L1 (core / v2 baseline)", s1),
        ("L1+2 (+ sweet spot)    ", s2),
        ("L1+2+3 (+ EV trend)    ", s3),
        ("L1+2+3+4 (full v6)     ", s4),
    ]:
        ov_n, ov_c, ov_a = st['OVERALL']
        bl_n, bl_c, bl_a = st.get('BUY_LOW', (0, 0, float('nan')))
        beat = "BEATS" if ov_a > RTM_BASELINE else "trails"
        pp   = abs(ov_a - RTM_BASELINE) * 100
        bl_str = f"  BUY_LOW={bl_a:.1%}" if not pd.isna(bl_a) else ""
        print(f"  {label}: Overall={ov_a:.1%} ({beat} RTM by {pp:.1f}pp)"
              f"  vs L1: {ov_a - s1['OVERALL'][2]:>+.1%}{bl_str}")

    v6_bl = s4.get('BUY_LOW', (0, 0, float('nan')))[2]
    v1_bl = s1.get('BUY_LOW', (0, 0, float('nan')))[2]
    v6_ov = s4['OVERALL'][2]
    v1_ov = s1['OVERALL'][2]
    print(f"\n  Key questions:")
    print(f"    Sweet spot improve BUY_LOW beyond {v1_bl:.1%}?  "
          f"L1+2 BUY_LOW = {s2.get('BUY_LOW',(0,0,float('nan')))[2]:.1%}  "
          f"-> {'YES' if s2.get('BUY_LOW',(0,0,float('nan')))[2] > v1_bl else 'NO'}")
    print(f"    EV trend dampen false buys?  "
          f"L1+2+3 BUY_LOW = {s3.get('BUY_LOW',(0,0,float('nan')))[2]:.1%}  "
          f"-> {'YES' if s3.get('BUY_LOW',(0,0,float('nan')))[2] >= s2.get('BUY_LOW',(0,0,float('nan')))[2] else 'NO'}")
    print(f"    Full v6 beat 81.5% overall?  v6 Overall = {v6_ov:.1%}  "
          f"-> {'YES' if v6_ov > 0.815 else 'NO'}")


# ------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------

def main():
    print("Within-Season Backtest v6 — Incremental Layer Evaluation")
    print("=" * 70)

    april_df, outcome_raw_df, team_map_df = load_data()

    print("\nLoading enrichment data...")
    career_stats = load_career_stats()
    patterns     = load_seasonal_patterns()

    print("\nComputing Layer 1 (core signal)...")
    signals = compute_layer1(april_df, team_map_df)
    print(f"  {len(signals)} batters with >={MIN_APRIL_PA} April PA")
    vc = pd.cut(signals['luck_score_L1'],
                bins=[-99, -0.040, -0.020, 0.020, 0.040, 99],
                labels=['SELL_HIGH', 'SLIGHT_SELL', 'NEUTRAL', 'SLIGHT_BUY', 'BUY_LOW'])
    for sig, count in vc.value_counts().sort_index().items():
        print(f"    {sig:<14} {count}")

    print("\nApplying Layer 2 (sweet spot modifier)...")
    signals = apply_layer2(signals)

    print("\nApplying Layer 3 (exit velocity trend)...")
    signals = apply_layer3(signals, career_stats)

    print("\nApplying Layer 4 (Phase C seasonal patterns)...")
    signals = apply_seasonal_modifier_as_layer4(signals, patterns)

    print("\nAggregating May-July outcomes...")
    merged = compute_outcomes(signals, outcome_raw_df)

    report(merged)

    out_path = BASE_DIR / "backtest_results_within_season_v6.csv"
    merged.to_csv(out_path, index=False)
    print(f"\nFull results saved -> {out_path}")


# apply_seasonal_modifier_as_layer4 is just apply_layer4 renamed for clarity in main()
apply_seasonal_modifier_as_layer4 = apply_layer4


if __name__ == "__main__":
    main()
