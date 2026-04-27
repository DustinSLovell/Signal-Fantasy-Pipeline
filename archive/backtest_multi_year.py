"""
Multi-Year Within-Season Backtest
===================================
Runs the full production signal stack across 2022-2025.
Signal: April v4 cache -> May-July outcome cache.
All metrics computed inline from pitch-level data.

Layers applied (degrades gracefully if columns missing):
  L1: xwoba_gap * 0.60 + babip_luck * 0.40  (always fires)
  L2: Sweet spot modifier (>0.12 x1.05, <0.06 x0.95 on buys)
  L3: EV trend dampener (>1.0 mph below career avg -> x0.85 on buys)
  L4: GB rate BABIP adj  (>0.50 -> -0.010, <0.35 -> +0.008)
  L5: Plate discipline   (elite bb/k -> x1.08, poor -> x0.88 on buys)
  L6: Seasonal patterns  (corrected multipliers from v9)
  L7: Defense OAA        (SKIPPED -- opponent team map not in older caches)

NOTE: career_stats.json includes 2022-2024 data. Applying it to 2022
      signals introduces minor lookahead bias on L3 for ~2023-24 debuts.
"""

import json
import os
import numpy as np
import pandas as pd
from pathlib import Path

BASE_DIR      = Path(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR     = BASE_DIR / "backtest_cache"
CAREER_PATH   = BASE_DIR / "data" / "career_stats.json"
SEASONAL_PATH = BASE_DIR / "data" / "seasonal_patterns.json"

YEARS          = [2022, 2023, 2024, 2025]
MIN_APRIL_PA   = 80
MIN_OUTCOME_PA = 100
FLAT_THRESHOLD = 0.015
RTM_BASELINE   = 0.682
EV_THRESHOLD   = 1.0
LEAGUE_AVG_BABIP = 0.300

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
    'BUY_LOW': 'IMPROVED', 'SLIGHT_BUY': 'IMPROVED',
    'SELL_HIGH': 'DECLINED', 'SLIGHT_SELL': 'DECLINED',
}

# Seasonal pattern corrected multipliers (v9)
PHASE_C = {
    'vshape_buy': 1.20, 'vshape_sell': None,
    'slow_buy': 1.10, 'summer_buy': 1.10,
    'fader_sell': 1.15, 'fader_buy': 0.90,
}

# ------------------------------------------------------------------
# SUPPORT DATA LOADERS
# ------------------------------------------------------------------

def load_career_stats() -> dict:
    if not CAREER_PATH.exists():
        return {}
    with open(CAREER_PATH) as f:
        return {int(k): v for k, v in json.load(f).items()}


def load_seasonal_patterns() -> dict:
    if not SEASONAL_PATH.exists():
        return {}
    with open(SEASONAL_PATH) as f:
        records = json.load(f)
    return {int(r["player_id"]): r for r in records}


# ------------------------------------------------------------------
# SIGNAL COMPUTATION  (inline, from raw pitch data)
# ------------------------------------------------------------------

def compute_signals(april_df: pd.DataFrame, team_map_df: pd.DataFrame,
                    career_stats: dict, patterns: dict) -> pd.DataFrame:
    df = april_df.copy()
    df = df.merge(team_map_df, on='batter', how='left')
    df['park_factor'] = df['team'].map(PARK_FACTORS).fillna(1.0)

    # -- BIP for BABIP -------------------------------------------------------
    batted = df[df['bb_type'].notna() & (df['bb_type'] != '')].copy()
    batted['is_bip']     = batted['events'].isin(BIP_EVENTS).astype(int)
    batted['is_hit_bip'] = batted['events'].isin({'single','double','triple'}).astype(int)
    bip_agg = batted.groupby('batter').agg(
        bip=('is_bip','sum'), hits_bip=('is_hit_bip','sum')
    ).reset_index()

    # -- BBE for sweet spot + EV ---------------------------------------------
    bbe = df[df['launch_speed'].notna() & df['launch_angle'].notna()].copy()
    bbe_agg = bbe.groupby('batter').apply(
        lambda s: pd.Series({
            'sweet_spot_count': ((s['launch_speed'] >= 98) & s['launch_angle'].between(8,32)).sum(),
            'bbe_total': len(s),
            'avg_exit_velocity': s['launch_speed'].mean(),
        })
    ).reset_index()

    # -- GB / FB for BABIP adjustment ----------------------------------------
    gb_agg = (
        batted.groupby('batter')
        .apply(lambda s: pd.Series({
            'gb_count': (s['bb_type'] == 'ground_ball').sum(),
            'bbe_bip':   len(s),
        }))
        .reset_index()
    )

    # -- BB / K rates --------------------------------------------------------
    pa_rows = df[df['events'].notna()].copy()
    disc_agg = pa_rows.groupby('batter').apply(
        lambda s: pd.Series({
            'total_pa': len(s),
            'walk_n':   s['events'].isin({'walk','intent_walk'}).sum(),
            'k_n':      s['events'].isin({'strikeout','strikeout_double_play'}).sum(),
        })
    ).reset_index()

    # -- Core wOBA aggregation -----------------------------------------------
    woba_agg = df.groupby('batter').agg(
        april_pa=('woba_value','count'),
        april_actual_woba=('woba_value','mean'),
        april_xwoba=('estimated_woba_using_speedangle','mean'),
        park_factor=('park_factor','first'),
    ).reset_index()

    # -- Assemble signals ----------------------------------------------------
    sig = (woba_agg
           .merge(bip_agg,  on='batter', how='left')
           .merge(bbe_agg,  on='batter', how='left')
           .merge(gb_agg,   on='batter', how='left')
           .merge(disc_agg, on='batter', how='left'))

    sig['babip'] = np.where(sig['bip'] > 0, sig['hits_bip'] / sig['bip'], np.nan)
    sig['sweet_spot_rate'] = np.where(
        sig['bbe_total'] > 0, sig['sweet_spot_count'] / sig['bbe_total'], np.nan)
    sig['gb_rate'] = np.where(
        sig['bbe_bip'] > 0, sig['gb_count'] / sig['bbe_bip'], np.nan)
    sig['bb_rate'] = np.where(
        sig['total_pa'] > 0, sig['walk_n']  / sig['total_pa'], np.nan)
    sig['k_rate']  = np.where(
        sig['total_pa'] > 0, sig['k_n']     / sig['total_pa'], np.nan)

    sig = sig[sig['april_pa'] >= MIN_APRIL_PA].copy()

    # -- L1: core luck score -------------------------------------------------
    sig['xwoba_gap']  = sig['april_xwoba'] - sig['april_actual_woba']
    sig['park_adj_babip_expected'] = (LEAGUE_AVG_BABIP * sig['park_factor']).round(4)

    # -- L4: GB rate BABIP adjustment ----------------------------------------
    gb_high = sig['gb_rate'] > 0.50
    gb_low  = sig['gb_rate'] < 0.35
    sig.loc[gb_high, 'park_adj_babip_expected'] -= 0.010
    sig.loc[gb_low,  'park_adj_babip_expected'] += 0.008
    sig['park_adj_babip_expected'] = sig['park_adj_babip_expected'].round(4)

    sig['babip_luck'] = sig['park_adj_babip_expected'] - sig['babip']
    sig['luck_score'] = (sig['xwoba_gap'] * 0.60 + sig['babip_luck'] * 0.40).round(4)

    layers_fired = ['L1', 'L4_gb']

    # -- L2: sweet spot modifier ---------------------------------------------
    buy = sig['luck_score'] > 0
    high_ss = buy & (sig['sweet_spot_rate'] > 0.12)
    low_ss  = buy & (sig['sweet_spot_rate'] < 0.06)
    sig.loc[high_ss, 'luck_score'] = (sig.loc[high_ss, 'luck_score'] * 1.05).round(4)
    sig.loc[low_ss,  'luck_score'] = (sig.loc[low_ss,  'luck_score'] * 0.95).round(4)
    layers_fired.append('L2_ss')

    # -- L3: EV trend modifier -----------------------------------------------
    if career_stats:
        buy = sig['luck_score'] > 0
        dampened = 0
        for idx, row in sig[buy].iterrows():
            cev = (career_stats.get(int(row['batter'])) or {}).get('avg_exit_velocity')
            if cev is None or pd.isna(row['avg_exit_velocity']):
                continue
            if row['avg_exit_velocity'] - cev < -EV_THRESHOLD:
                sig.at[idx, 'luck_score'] = round(row['luck_score'] * 0.85, 4)
                dampened += 1
        layers_fired.append(f'L3_ev({dampened})')

    # -- L5: plate discipline ------------------------------------------------
    buy = sig['luck_score'] > 0
    elite_disc = buy & (sig['bb_rate'] > 0.10) & (sig['k_rate'] < 0.18)
    poor_disc  = buy & ((sig['bb_rate'] < 0.06) | (sig['k_rate'] > 0.28))
    sig.loc[elite_disc, 'luck_score'] = (sig.loc[elite_disc, 'luck_score'] * 1.08).round(4)
    sig.loc[poor_disc,  'luck_score'] = (sig.loc[poor_disc,  'luck_score'] * 0.88).round(4)
    layers_fired.append(f'L5_disc(e{elite_disc.sum()}/p{poor_disc.sum()})')

    # -- L6: seasonal patterns -----------------------------------------------
    if patterns:
        n_mod = 0
        for idx, row in sig.iterrows():
            pid  = int(row['batter'])
            raw  = row['luck_score']
            if pid not in patterns:
                continue
            p      = patterns[pid]
            slow   = p.get('slow_starter', False)
            fader  = p.get('second_half_fader', False)
            summer = p.get('summer_performer', False)
            is_buy  = raw > 0
            is_sell = raw < 0
            mult   = 1.0
            if slow and summer:
                if is_buy:
                    mult = PHASE_C['vshape_buy']
            elif slow and not summer:
                if is_buy:
                    mult = PHASE_C['slow_buy']
            elif summer and not slow:
                if is_buy:
                    mult = PHASE_C['summer_buy']
            if fader:
                if is_sell:
                    mult = max(mult, PHASE_C['fader_sell'])
                elif is_buy:
                    mult = min(mult, PHASE_C['fader_buy'])
            if mult != 1.0:
                sig.at[idx, 'luck_score'] = round(raw * mult, 4)
                n_mod += 1
        layers_fired.append(f'L6_phaseC({n_mod})')

    return sig, layers_fired


# ------------------------------------------------------------------
# OUTCOMES
# ------------------------------------------------------------------

def compute_outcomes(signals_df: pd.DataFrame, outcome_df: pd.DataFrame) -> pd.DataFrame:
    outcomes = outcome_df.groupby('batter').agg(
        outcome_pa=('woba_value','count'),
        outcome_woba=('woba_value','mean'),
    ).reset_index()
    merged = signals_df.merge(outcomes, on='batter', how='inner')
    merged = merged[merged['outcome_pa'] >= MIN_OUTCOME_PA].copy()
    merged['woba_change'] = merged['outcome_woba'] - merged['april_actual_woba']
    return merged


# ------------------------------------------------------------------
# CLASSIFY + STATS
# ------------------------------------------------------------------

def classify(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    conds = [
        out['luck_score'] >= 0.040,
        out['luck_score'] >= 0.020,
        out['luck_score'] <= -0.040,
        out['luck_score'] <= -0.020,
    ]
    out['signal'] = np.select(conds,
        ['BUY_LOW','SLIGHT_BUY','SELL_HIGH','SLIGHT_SELL'], default='NEUTRAL')
    out['outcome'] = np.where(
        out['woba_change'] >=  FLAT_THRESHOLD, 'IMPROVED',
        np.where(out['woba_change'] <= -FLAT_THRESHOLD, 'DECLINED', 'FLAT')
    )
    return out


def bucket_stats(df: pd.DataFrame) -> dict:
    ev = df[df['signal'].isin(SIGNAL_MAP) & (df['outcome'] != 'FLAT')].copy()
    ev['correct'] = ev.apply(lambda r: r['outcome'] == SIGNAL_MAP[r['signal']], axis=1)
    stats = {}
    for sig in ['BUY_LOW','SLIGHT_BUY','SELL_HIGH','SLIGHT_SELL']:
        grp = ev[ev['signal'] == sig]
        n, c = len(grp), int(grp['correct'].sum()) if len(grp) > 0 else 0
        stats[sig] = (n, c, c/n if n > 0 else float('nan'))
    ov_n = len(ev); ov_c = int(ev['correct'].sum())
    stats['OVERALL'] = (ov_n, ov_c, ov_c/ov_n if ov_n > 0 else float('nan'))
    return stats


def gradient(df: pd.DataFrame) -> dict:
    """Mean wOBA change per signal bucket (all players, no flat filter)."""
    out = {}
    for sig in ['BUY_LOW','SLIGHT_BUY','NEUTRAL','SLIGHT_SELL','SELL_HIGH']:
        grp = df[df['signal'] == sig]
        out[sig] = grp['woba_change'].mean() if len(grp) >= 3 else float('nan')
    return out


# ------------------------------------------------------------------
# RUN ONE YEAR
# ------------------------------------------------------------------

def run_year(year: int, career_stats: dict, patterns: dict) -> dict:
    april_path  = CACHE_DIR / f"v4_april_{year}.csv"
    mj_path     = CACHE_DIR / f"statcast_{year}_may_july.csv"
    tmap_path   = CACHE_DIR / f"team_map_{year}.csv"

    if not (april_path.exists() and mj_path.exists() and tmap_path.exists()):
        return None

    april_df  = pd.read_csv(april_path)
    mj_df     = pd.read_csv(mj_path, usecols=['batter','woba_value'])
    team_map  = pd.read_csv(tmap_path)

    signals, layers = compute_signals(april_df, team_map, career_stats, patterns)
    merged          = compute_outcomes(signals, mj_df)
    classified      = classify(merged)
    stats           = bucket_stats(classified)
    grad            = gradient(classified)

    flat_n = (merged['woba_change'].abs() < FLAT_THRESHOLD).sum()

    # Signal bucket counts
    sig_counts = classified['signal'].value_counts().to_dict()

    return {
        'year':       year,
        'stats':      stats,
        'gradient':   grad,
        'layers':     layers,
        'n_signals':  len(signals),
        'n_eval':     stats['OVERALL'][0],
        'n_flat':     flat_n,
        'sig_counts': sig_counts,
        'df':         classified,
    }


# ------------------------------------------------------------------
# DISPLAY
# ------------------------------------------------------------------

def fmt_pct(v, width=6):
    return f"{v:{width}.1%}" if not pd.isna(v) else f"{'n/a':>{width}}"

def fmt_pp(v, width=6):
    return f"{v*100:{width}.1f}pp" if not pd.isna(v) else f"{'n/a':>{width}}"


def print_table(results: list):
    years_avail = [r['year'] for r in results]

    SIGS = ['BUY_LOW','SLIGHT_BUY','SELL_HIGH','SLIGHT_SELL','OVERALL']
    COL  = 8   # column width per year

    # Header
    hdr_top  = f"{'Signal':<12} " + "".join(f" {y:>{COL}}" for y in years_avail) + f" {'4yr Avg':>{COL+1}}"
    div_top  = "+" + "-"*12 + "+" + (("-"*COL + "+") * len(years_avail)) + "-"*(COL+1) + "+"
    div_mid  = "+" + "-"*12 + "+" + ("-"*COL + "+") * (len(years_avail)-1) + "-"*COL + "+" + "-"*(COL+1) + "+"
    div_bot  = "+" + "-"*12 + "+" + ("-"*COL + "+") * (len(years_avail)-1) + "-"*COL + "+" + "-"*(COL+1) + "+"

    print(div_top)
    print(f"| {'Signal':<10} |" + "|".join(f" {y:>{COL-1}} " for y in years_avail) + f"| {'4yr Avg':>{COL-1}} |")
    print(div_mid)

    # Per-bucket rows
    for sig in SIGS:
        if sig == 'OVERALL':
            print(div_mid)
        accs = []
        for r in results:
            n, c, acc = r['stats'].get(sig, (0, 0, float('nan')))
            accs.append(acc)
        valid = [a for a in accs if not pd.isna(a)]
        avg   = np.mean(valid) if valid else float('nan')
        row   = f"| {sig:<10} |"
        for acc in accs:
            row += f" {fmt_pct(acc, COL-1)} |"
        row += f" {fmt_pct(avg, COL-1)} |"
        print(row)

    print(div_mid)
    # vs RTM row
    row = f"| {'vs RTM':<10} |"
    vs_rtm_vals = []
    for r in results:
        ov_a = r['stats']['OVERALL'][2]
        vs   = ov_a - RTM_BASELINE if not pd.isna(ov_a) else float('nan')
        vs_rtm_vals.append(vs)
        row += f" {fmt_pp(vs, COL-1)} |"
    avg_vs = np.mean([v for v in vs_rtm_vals if not pd.isna(v)])
    row += f" {fmt_pp(avg_vs, COL-1)} |"
    print(row)

    # n evaluated row
    row = f"| {'n eval':<10} |"
    ns  = [r['n_eval'] for r in results]
    row += "".join(f" {n:>{COL-1}} |" for n in ns)
    row += f" {sum(ns):>{COL-1}} |"
    print(row)

    print(div_bot)


def print_year_detail(results: list):
    for r in results:
        year = r['year']
        g    = r['gradient']
        stat = r['stats']

        print(f"\n  -- {year} ----------------------------------------------------------")
        print(f"  Signal pool: {r['n_signals']} batters (>={MIN_APRIL_PA} April PA) | "
              f"{r['n_eval']} evaluated | {r['n_flat']} flat excluded")
        print(f"  Layers fired: {', '.join(r['layers'])}")

        # Bucket sizes
        sc = r['sig_counts']
        bc = " | ".join(f"{s}: {sc.get(s,0)}" for s in
                        ['BUY_LOW','SLIGHT_BUY','NEUTRAL','SLIGHT_SELL','SELL_HIGH'])
        print(f"  Buckets: {bc}")

        # Monotonic gradient
        vals = [(s, g.get(s, float('nan'))) for s in ['BUY_LOW','SLIGHT_BUY','NEUTRAL','SLIGHT_SELL','SELL_HIGH']]
        grad_str = "  Gradient: " + " -> ".join(
            f"{s}={v:+.4f}" if not pd.isna(v) else f"{s}=n/a" for s, v in vals
        )
        print(grad_str)

        # Check monotonic: BUY_LOW > SLIGHT_BUY > NEUTRAL > SLIGHT_SELL > SELL_HIGH
        grad_vals = [v for _, v in vals if not pd.isna(v)]
        monotonic = all(grad_vals[i] > grad_vals[i+1] for i in range(len(grad_vals)-1))
        print(f"  Gradient monotonically decreasing: {'YES' if monotonic else 'NO'}")

        # Per-bucket accuracy summary
        for sig in ['BUY_LOW','SLIGHT_BUY','SELL_HIGH','SLIGHT_SELL']:
            n, c, acc = stat.get(sig, (0, 0, float('nan')))
            acc_str = f"{acc:.1%}" if not pd.isna(acc) else "n/a"
            print(f"    {sig:<14} n={n:>3}  acc={acc_str}")


# ------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------

def main():
    print("Multi-Year Within-Season Backtest  (2022-2025)")
    print("=" * 70)

    career_stats = load_career_stats()
    patterns     = load_seasonal_patterns()
    print(f"Career stats: {len(career_stats):,} players  |  "
          f"Seasonal patterns: {len(patterns):,} players")
    print(f"Layer 7 (defense OAA) skipped -- opponent team maps not in older caches")

    results = []
    for year in YEARS:
        print(f"\nRunning {year}...")
        r = run_year(year, career_stats, patterns)
        if r is None:
            print(f"  SKIPPED -- missing cache files for {year}")
            continue
        results.append(r)
        ov_a = r['stats']['OVERALL'][2]
        bl_a = r['stats']['BUY_LOW'][2]
        print(f"  {r['n_signals']} signal batters -> {r['n_eval']} evaluated  |  "
              f"overall={ov_a:.1%}  BUY_LOW={bl_a:.1%}")

    if not results:
        print("No results. Check cache files.")
        return

    # -- Main accuracy table ----------------------------------------------
    print(f"\n{'=' * 75}")
    print("ACCURACY TABLE -- April signals -> May-July outcomes")
    print(f"{'=' * 75}")
    print_table(results)

    # -- Per-year detail --------------------------------------------------
    print(f"\n{'=' * 75}")
    print("PER-YEAR DETAIL")
    print(f"{'=' * 75}")
    print_year_detail(results)

    # -- Cross-year gradient consistency ----------------------------------
    print(f"\n{'=' * 75}")
    print("GRADIENT CONSISTENCY -- mean wOBA change by signal bucket")
    print(f"{'=' * 75}")
    sig_order = ['BUY_LOW','SLIGHT_BUY','NEUTRAL','SLIGHT_SELL','SELL_HIGH']
    hdr = f"  {'Signal':<14} " + "".join(f"{r['year']:>10}" for r in results) + f"  {'4yr avg':>10}"
    print(hdr)
    print("  " + "-" * (14 + 10 * len(results) + 12))
    for sig in sig_order:
        vals = [r['gradient'].get(sig, float('nan')) for r in results]
        valid = [v for v in vals if not pd.isna(v)]
        avg  = np.mean(valid) if valid else float('nan')
        row  = f"  {sig:<14} " + "".join(
            f"{v:>+10.4f}" if not pd.isna(v) else f"{'n/a':>10}" for v in vals
        )
        row += f"  {avg:>+10.4f}" if not pd.isna(avg) else f"  {'n/a':>10}"
        print(row)

    # -- Key questions ----------------------------------------------------
    print(f"\n{'=' * 75}")
    print("KEY QUESTIONS")
    print(f"{'=' * 75}")

    ov_accs  = [r['stats']['OVERALL'][2] for r in results]
    bl_accs  = [r['stats']['BUY_LOW'][2] for r in results]
    sb_accs  = [r['stats']['SLIGHT_BUY'][2] for r in results]
    valid_ov = [a for a in ov_accs if not pd.isna(a)]
    valid_bl = [a for a in bl_accs if not pd.isna(a)]
    valid_sb = [a for a in sb_accs if not pd.isna(a)]

    ov_avg  = np.mean(valid_ov)
    bl_avg  = np.mean(valid_bl)
    sb_avg  = np.mean(valid_sb)
    ov_std  = np.std(valid_ov)
    bl_std  = np.std(valid_bl)

    # Is accuracy consistent?
    ov_range = max(valid_ov) - min(valid_ov)
    consistent = ov_range < 0.05

    # Is 2024 an outlier?
    y2024_ov = next((r['stats']['OVERALL'][2] for r in results if r['year'] == 2024), float('nan'))
    is_2024_outlier = not pd.isna(y2024_ov) and abs(y2024_ov - ov_avg) > ov_std * 1.5

    # BUY_LOW always high?
    bl_always_high = all(not pd.isna(a) and a >= 0.80 for a in bl_accs)

    # Gradient holds in all years?
    all_monotonic = all(
        all(
            (r['gradient'].get(sig_order[i], float('nan')) >
             r['gradient'].get(sig_order[i+1], float('nan')))
            if not (pd.isna(r['gradient'].get(sig_order[i], float('nan'))) or
                    pd.isna(r['gradient'].get(sig_order[i+1], float('nan'))))
            else True   # skip if missing
            for i in range(len(sig_order)-1)
        )
        for r in results
    )

    print(f"\n  Q1: Accuracy consistent across all years?")
    print(f"      Range: {min(valid_ov):.1%} to {max(valid_ov):.1%}  "
          f"(spread={ov_range:.1%}, std={ov_std:.3f})")
    print(f"      Answer: {'YES -- spread < 5pp' if consistent else 'NO -- spread >= 5pp'}")

    print(f"\n  Q2: Is 2024 an outlier?")
    if not pd.isna(y2024_ov):
        print(f"      2024 overall: {y2024_ov:.1%}  vs 4yr avg: {ov_avg:.1%}  "
              f"(delta={y2024_ov - ov_avg:+.1%})")
        print(f"      Answer: {'YES (>1.5 SD from mean)' if is_2024_outlier else 'NO -- within normal range'}")

    print(f"\n  Q3: Does BUY_LOW maintain high accuracy in every year?")
    for r in results:
        bl = r['stats']['BUY_LOW']
        acc_str = f"{bl[2]:.1%}" if not pd.isna(bl[2]) else "n/a"
        print(f"      {r['year']}: {acc_str}  (n={bl[0]})")
    print(f"      4yr avg: {bl_avg:.1%}  |  All >= 80%? {'YES' if bl_always_high else 'NO'}")

    print(f"\n  Q4: Does the monotonic gradient hold in all four years?")
    for r in results:
        g = r['gradient']
        vals = [g.get(s, float('nan')) for s in sig_order]
        numeric = [v for v in vals if not pd.isna(v)]
        mono = all(numeric[i] > numeric[i+1] for i in range(len(numeric)-1))
        print(f"      {r['year']}: {'YES' if mono else 'NO'}")
    print(f"      All years monotonic? {'YES' if all_monotonic else 'NO'}")

    print(f"\n  Q5: 4-year averages")
    print(f"      Overall:    {ov_avg:.1%}  (beats RTM by {(ov_avg - RTM_BASELINE)*100:.1f}pp)")
    print(f"      BUY_LOW:    {bl_avg:.1%}")
    print(f"      SLIGHT_BUY: {sb_avg:.1%}")


if __name__ == "__main__":
    main()
