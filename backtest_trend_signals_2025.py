"""backtest_trend_signals_2025.py — 2025 validation of mid-season trend signal concept

QUESTION: Does adding a trajectory filter to the existing luck signals
improve prediction accuracy over luck signals alone?

DATA SOURCES:
  data/projection_accuracy_2025.csv    — 141 players, April signals + april_xwoba
  data/fg_batting_2025.csv             — full-season wOBA/xwOBA (Statcast)
  data/backtest_A_hitters_2025.csv     — actual ROS wOBA (validation target)
  data/fg_pitching_2025.csv            — full-season ERA/xERA for pitchers
  data/backtest_A_pitchers_2025.csv    — pitcher April IP + full-season actuals

TREND PROXY (IMPORTANT CAVEAT):
  The ideal trend proxy is "May 1-17 rolling xwOBA vs April xwOBA."
  We do not have 2025 game logs broken by date.

  Proxy used: (full_season_xwOBA - april_xwOBA)
  ⚠️ This uses post-May-17 information — it simulates the DIRECTION
  of benefit rather than a true out-of-sample test.

  The 2026 live system uses actual rolling game-log windows (no leakage).

ACCURACY DEFINITION:
  Buy-side correct  : actual_ros_woba > april_xwoba + THRESHOLD
  Sell-side correct : actual_ros_woba < april_xwoba - THRESHOLD
  THRESHOLD = 0.020 (matches existing backtest standard)
"""
import csv, math, statistics
from collections import defaultdict

THRESHOLD = 0.020    # wOBA delta to call a signal "correct"
TREND_UP  = +0.020   # fs_xwoba - april_xwoba threshold for "Trending Up"
TREND_DN  = -0.020   # threshold for "Trending Down"

# ── Helpers ───────────────────────────────────────────────────────────────────
def flt(v, default=None):
    try: return float(v)
    except: return default

def load_csv(path):
    with open(path, encoding='utf-8') as f:
        return list(csv.DictReader(f))

def section(title):
    print()
    print('=' * 72)
    print(title)
    print('=' * 72)

# ── Load data ─────────────────────────────────────────────────────────────────
acc  = load_csv('data/projection_accuracy_2025.csv')
fg   = {r['batter_id']: r for r in load_csv('data/fg_batting_2025.csv')}
bt   = {r['mlbam_id']:  r for r in load_csv('data/backtest_A_hitters_2025.csv')}
fg_p = {r['pitcher_id']: r for r in load_csv('data/fg_pitching_2025.csv')}
bt_p = {r['mlbam_id']:  r for r in load_csv('data/backtest_A_pitchers_2025.csv')}

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1: HITTER BACKTEST
# ══════════════════════════════════════════════════════════════════════════════

hitter_records = []
skipped = 0

for r in acc:
    bid          = r['batter_id']
    signal       = r['signal']
    april_xwoba  = flt(r.get('april_xwoba'))
    april_pa     = flt(r.get('april_pa'), 0)

    fg_row       = fg.get(bid, {})
    fs_xwoba     = flt(fg_row.get('est_woba'))    # full-season Statcast xwOBA

    bt_row       = bt.get(bid, {})
    ros_woba     = flt(bt_row.get('actual_ros_woba'))
    ros_pa       = flt(bt_row.get('ros_pa'), 0)

    if any(v is None for v in [april_xwoba, fs_xwoba, ros_woba]):
        skipped += 1
        continue
    if april_pa < 50 or ros_pa < 50:   # minimum sample
        skipped += 1
        continue

    # Trend proxy: direction the player moved AFTER April
    # (using full-season xwOBA; see caveat in module docstring)
    trend_delta  = fs_xwoba - april_xwoba
    trend_dir    = ('Up'   if trend_delta >= TREND_UP  else
                   'Down' if trend_delta <= TREND_DN  else 'Flat')

    # Combined signal
    sl = signal.lower()
    if   'buy low'    in sl and trend_dir == 'Up':   combined = 'Strong Buy'
    elif 'buy low'    in sl and trend_dir == 'Down':  combined = 'Conflicted Buy'
    elif 'buy low'    in sl:                          combined = 'Buy Low (Flat)'
    elif 'slight buy' in sl and trend_dir == 'Up':   combined = 'Slight Buy + Up'
    elif 'slight buy' in sl and trend_dir == 'Down':  combined = 'Slight Buy + Down'
    elif 'sell high'  in sl and trend_dir == 'Down':  combined = 'Strong Sell'
    elif 'sell high'  in sl and trend_dir == 'Up':   combined = 'Conflicted Sell'
    elif 'sell high'  in sl:                          combined = 'Sell High (Flat)'
    elif 'slight sell' in sl and trend_dir == 'Down': combined = 'Slight Sell + Down'
    elif 'slight sell' in sl and trend_dir == 'Up':  combined = 'Slight Sell + Up'
    else:                                              combined = f'Neutral + {trend_dir}'

    # Outcome: did ros_woba move in predicted direction vs April baseline?
    woba_delta = ros_woba - april_xwoba   # positive = improved from April

    if   'buy'  in sl: correct = woba_delta >  THRESHOLD
    elif 'sell' in sl: correct = woba_delta < -THRESHOLD
    else:              correct = abs(woba_delta) <= THRESHOLD  # neutral = staying flat

    hitter_records.append({
        'name':         r['player_name'],
        'batter_id':    bid,
        'signal':       signal,
        'trend_dir':    trend_dir,
        'trend_delta':  round(trend_delta, 4),
        'combined':     combined,
        'april_xwoba':  round(april_xwoba, 4),
        'fs_xwoba':     round(fs_xwoba, 4),
        'ros_woba':     round(ros_woba, 4),
        'woba_delta':   round(woba_delta, 4),
        'april_pa':     int(april_pa),
        'ros_pa':       int(ros_pa),
        'correct':      int(correct),
    })

section(f'HITTER TREND BACKTEST — 2025  (N={len(hitter_records)}, skipped={skipped})')
print('⚠️  CAVEAT: trend proxy uses full-season xwOBA (post-May-17 data).')
print('    This shows directional potential, not true OOS accuracy.')
print(f'    Trend thresholds: Up > +{TREND_UP:.3f}, Down < {TREND_DN:.3f}')
print(f'    Accuracy threshold: wOBA delta > ±{THRESHOLD:.3f}')

# ── Section 1a: Luck-signal-only baseline ────────────────────────────────────
section('SECTION 1a: LUCK SIGNAL ONLY (BASELINE)')

SIGNAL_TIERS = ['Buy Low', 'Slight Buy', 'Neutral', 'Slight Sell', 'Sell High']
print(f"  {'Signal':<16} {'N':>4} {'Correct':>8} {'Acc%':>7} {'Avg delta':>10} {'Std delta':>10}")
print(f"  {'-'*60}")

luck_only_results = {}
for sig in SIGNAL_TIERS:
    grp = [r for r in hitter_records if r['signal'] == sig]
    if not grp: continue
    n       = len(grp)
    correct = sum(r['correct'] for r in grp)
    deltas  = [r['woba_delta'] for r in grp]
    acc_pct = 100 * correct / n
    avg_d   = statistics.mean(deltas)
    std_d   = statistics.stdev(deltas) if n > 1 else 0
    print(f"  {sig:<16} {n:>4} {correct:>8} {acc_pct:>6.1f}% {avg_d:>+10.4f} {std_d:>10.4f}")
    luck_only_results[sig] = {'n': n, 'correct': correct, 'acc_pct': acc_pct, 'avg_delta': avg_d}

# ── Section 1b: Combined signal breakdown ────────────────────────────────────
section('SECTION 1b: COMBINED SIGNAL (LUCK + TREND DIRECTION)')

COMBINED_ORDER = [
    'Strong Buy', 'Buy Low (Flat)', 'Conflicted Buy',
    'Slight Buy + Up', 'Slight Buy + Down',
    'Neutral + Up', 'Neutral + Flat', 'Neutral + Down',
    'Slight Sell + Down', 'Slight Sell + Up',
    'Strong Sell', 'Sell High (Flat)', 'Conflicted Sell',
]

print(f"  {'Combined Signal':<24} {'N':>4} {'Correct':>8} {'Acc%':>7} {'Avg wOBA Δ':>11} {'vs baseline':>12}")
print(f"  {'-'*72}")

combined_results = {}
for sig in COMBINED_ORDER:
    grp = [r for r in hitter_records if r['combined'] == sig]
    if not grp: continue
    n       = len(grp)
    correct = sum(r['correct'] for r in grp)
    deltas  = [r['woba_delta'] for r in grp]
    acc_pct = 100 * correct / n
    avg_d   = statistics.mean(deltas)

    # Find baseline from luck-only
    base_sig = next((s for s in SIGNAL_TIERS if s.lower() in sig.lower()), None)
    baseline = luck_only_results.get(base_sig)
    vs_base  = f"{acc_pct - baseline['acc_pct']:+.1f}pp" if baseline else '—'

    print(f"  {sig:<24} {n:>4} {correct:>8} {acc_pct:>6.1f}% {avg_d:>+11.4f} {vs_base:>12}")
    combined_results[sig] = {'n': n, 'correct': correct, 'acc_pct': acc_pct, 'avg_delta': avg_d}

# ── Section 1c: Key question — does trend improve accuracy? ──────────────────
section('SECTION 1c: KEY QUESTION — DOES TREND FILTER ADD VALUE?')

comparisons = [
    ('Buy Low (all)',   [r for r in hitter_records if r['signal'] == 'Buy Low'],
     'Strong Buy',      [r for r in hitter_records if r['combined'] == 'Strong Buy'],
     'Conflicted Buy',  [r for r in hitter_records if r['combined'] == 'Conflicted Buy']),
    ('Sell High (all)', [r for r in hitter_records if r['signal'] == 'Sell High'],
     'Strong Sell',     [r for r in hitter_records if r['combined'] == 'Strong Sell'],
     'Conflicted Sell', [r for r in hitter_records if r['combined'] == 'Conflicted Sell']),
]

def acc_str(grp):
    if not grp: return 'N/A'
    n = len(grp); c = sum(r['correct'] for r in grp)
    return f"{100*c/n:.1f}% ({c}/{n})"

def avg_d_str(grp):
    if not grp: return 'N/A'
    return f"{statistics.mean(r['woba_delta'] for r in grp):+.4f}"

for base_lbl, base_grp, pos_lbl, pos_grp, neg_lbl, neg_grp in comparisons:
    print(f"\n  {base_lbl}: acc={acc_str(base_grp)}  avg_delta={avg_d_str(base_grp)}")
    print(f"    {pos_lbl:<22}: acc={acc_str(pos_grp)}  avg_delta={avg_d_str(pos_grp)}")
    print(f"    {neg_lbl:<22}: acc={acc_str(neg_grp)}  avg_delta={avg_d_str(neg_grp)}")
    if pos_grp and neg_grp and base_grp:
        pos_acc  = 100 * sum(r['correct'] for r in pos_grp)  / len(pos_grp)
        neg_acc  = 100 * sum(r['correct'] for r in neg_grp)  / len(neg_grp)
        base_acc = 100 * sum(r['correct'] for r in base_grp) / len(base_grp)
        pos_d    = statistics.mean(r['woba_delta'] for r in pos_grp)
        neg_d    = statistics.mean(r['woba_delta'] for r in neg_grp)
        base_d   = statistics.mean(r['woba_delta'] for r in base_grp)
        print(f"    Trend uplift vs base: confirmed={pos_acc-base_acc:+.1f}pp | conflicted={neg_acc-base_acc:+.1f}pp")
        print(f"    Delta separation:     confirmed={pos_d-base_d:+.4f} | conflicted={neg_d-base_d:+.4f}")

# ── Section 1d: Player-level detail on Strong Buy / Strong Sell ──────────────
section('SECTION 1d: PLAYER-LEVEL DETAIL — STRONG BUY')

strong_buy = sorted([r for r in hitter_records if r['combined'] == 'Strong Buy'],
                    key=lambda r: -r['trend_delta'])
print(f"  {'Player':<22} {'Apr xwOBA':>10} {'FS xwOBA':>9} {'Trend Δ':>8} {'ROS wOBA':>9} {'wOBA Δ':>8} {'OK?':>4}")
print(f"  {'-'*76}")
for r in strong_buy:
    ok = '✓' if r['correct'] else '✗'
    print(f"  {r['name']:<22} {r['april_xwoba']:>10.4f} {r['fs_xwoba']:>9.4f} "
          f"{r['trend_delta']:>+8.4f} {r['ros_woba']:>9.4f} {r['woba_delta']:>+8.4f} {ok:>4}")

section('SECTION 1d: PLAYER-LEVEL DETAIL — STRONG SELL')

strong_sell = sorted([r for r in hitter_records if r['combined'] == 'Strong Sell'],
                     key=lambda r: r['trend_delta'])
print(f"  {'Player':<22} {'Apr xwOBA':>10} {'FS xwOBA':>9} {'Trend Δ':>8} {'ROS wOBA':>9} {'wOBA Δ':>8} {'OK?':>4}")
print(f"  {'-'*76}")
for r in strong_sell:
    ok = '✓' if r['correct'] else '✗'
    print(f"  {r['name']:<22} {r['april_xwoba']:>10.4f} {r['fs_xwoba']:>9.4f} "
          f"{r['trend_delta']:>+8.4f} {r['ros_woba']:>9.4f} {r['woba_delta']:>+8.4f} {ok:>4}")

section('SECTION 1d: PLAYER-LEVEL DETAIL — CONFLICTED BUY (recovery thesis weakening)')

conf_buy = sorted([r for r in hitter_records if r['combined'] == 'Conflicted Buy'],
                  key=lambda r: r['trend_delta'])
print(f"  {'Player':<22} {'Apr xwOBA':>10} {'FS xwOBA':>9} {'Trend Δ':>8} {'ROS wOBA':>9} {'wOBA Δ':>8} {'OK?':>4}")
print(f"  {'-'*76}")
for r in conf_buy:
    ok = '✓' if r['correct'] else '✗'
    print(f"  {r['name']:<22} {r['april_xwoba']:>10.4f} {r['fs_xwoba']:>9.4f} "
          f"{r['trend_delta']:>+8.4f} {r['ros_woba']:>9.4f} {r['woba_delta']:>+8.4f} {ok:>4}")

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2: PITCHER ANALYSIS (ERA trajectory, no luck signal available)
# ══════════════════════════════════════════════════════════════════════════════
section('SECTION 2: PITCHER ERA TRAJECTORY — 2025')
print('NOTE: No 2025 pitcher luck signals available. Using ERA gap as proxy.')
print('      April ERA proxy = naive_era (April-pace annualized from backtest_A).')
print('      Full-season xERA from fg_pitching_2025 = quality trajectory indicator.')
print('      Target = actual_era (full-season).')
print()

pitcher_records = []
skipped_p = 0

for r in bt_p.values():
    pid       = r['mlbam_id']
    april_ip  = flt(r.get('april_ip'), 0)
    naive_era = flt(r.get('naive_era'))    # April-pace ERA
    actual_era= flt(r.get('actual_era'))   # full-season actual ERA (target)
    fg_row    = fg_p.get(pid, {})
    xera_fs   = flt(fg_row.get('xera'))   # full-season xERA (trajectory quality proxy)
    era_fs    = flt(fg_row.get('era'))     # full-season ERA

    if any(v is None for v in [naive_era, actual_era, xera_fs]) or april_ip < 15:
        skipped_p += 1
        continue
    if naive_era <= 0 or naive_era > 12:   # filter extreme outliers
        skipped_p += 1
        continue

    # April "luck" proxy: high naive_era vs xERA_fs = was outperforming bad luck
    era_luck_gap = naive_era - xera_fs     # positive = April ERA >> expected → unlucky in April

    # Trend proxy: did full-season xERA improve vs April pace?
    trend_delta  = naive_era - actual_era  # positive = ERA improved from April pace
    trend_dir    = ('Better' if trend_delta >= 0.50 else
                   'Worse'  if trend_delta <= -0.50 else 'Flat')

    # Signal proxy: classify April ERA situation
    if naive_era >= 5.00 and era_luck_gap >= 0.75:  signal_proxy = 'Buy Low proxy'
    elif naive_era <= 3.00 and era_luck_gap <= -0.50: signal_proxy = 'Sell High proxy'
    else:                                              signal_proxy = 'Neutral'

    combined = f"{signal_proxy} + {trend_dir}"

    # Correct: buy = actual_era < naive_era by >= 0.40 (ERA improved)
    #          sell = actual_era > naive_era by >= 0.40 (ERA regressed)
    if 'Buy'  in signal_proxy: correct = actual_era < naive_era - 0.40
    elif 'Sell' in signal_proxy: correct = actual_era > naive_era + 0.40
    else: correct = abs(actual_era - naive_era) <= 0.40

    pitcher_records.append({
        'name':         r['name'],
        'mlbam_id':     pid,
        'april_ip':     round(april_ip, 1),
        'naive_era':    round(naive_era, 2),
        'xera_fs':      round(xera_fs, 2),
        'era_luck_gap': round(era_luck_gap, 2),
        'actual_era':   round(actual_era, 2),
        'era_delta':    round(actual_era - naive_era, 2),  # negative = improved
        'trend_dir':    trend_dir,
        'signal_proxy': signal_proxy,
        'combined':     combined,
        'correct':      int(correct),
    })

print(f'Pitcher records: {len(pitcher_records)}, skipped: {skipped_p}')

P_GROUPS = ['Buy Low proxy', 'Neutral', 'Sell High proxy']
print(f"\n  {'Signal Proxy':<20} {'N':>4} {'Correct':>8} {'Acc%':>7} {'Avg ERA Δ':>10}")
print(f"  {'-'*56}")
for sig in P_GROUPS:
    grp = [r for r in pitcher_records if r['signal_proxy'] == sig]
    if not grp: continue
    n = len(grp); c = sum(r['correct'] for r in grp)
    era_deltas = [r['era_delta'] for r in grp]
    print(f"  {sig:<20} {n:>4} {c:>8} {100*c/n:>6.1f}% {statistics.mean(era_deltas):>+10.3f}")

# Buy Low proxy: did trend direction help?
print()
print('  Buy Low proxy — trend filter impact:')
for td in ['Better', 'Flat', 'Worse']:
    grp = [r for r in pitcher_records if r['signal_proxy'] == 'Buy Low proxy' and r['trend_dir'] == td]
    if not grp: continue
    n = len(grp); c = sum(r['correct'] for r in grp)
    avg_d = statistics.mean(r['era_delta'] for r in grp)
    print(f"    {td:<8} N={n:>3}  acc={100*c/n:>5.1f}%  avg_ERA_delta={avg_d:>+.3f}")

print()
print('  Sell High proxy — trend filter impact:')
for td in ['Worse', 'Flat', 'Better']:
    grp = [r for r in pitcher_records if r['signal_proxy'] == 'Sell High proxy' and r['trend_dir'] == td]
    if not grp: continue
    n = len(grp); c = sum(r['correct'] for r in grp)
    avg_d = statistics.mean(r['era_delta'] for r in grp)
    print(f"    {td:<8} N={n:>3}  acc={100*c/n:>5.1f}%  avg_ERA_delta={avg_d:>+.3f}")

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3: SUMMARY TABLE
# ══════════════════════════════════════════════════════════════════════════════
section('SECTION 3: SUMMARY TABLE — SIGNAL TIER COMPARISON')

print(f"  {'Signal Tier':<28} {'N':>4} {'Correct':>8} {'Accuracy':>9} {'Avg wOBA Δ':>11}")
print(f"  {'-'*64}")

summary_tiers = [
    ('Buy Low (baseline)',   [r for r in hitter_records if r['signal'] == 'Buy Low']),
    ('Strong Buy',           [r for r in hitter_records if r['combined'] == 'Strong Buy']),
    ('Conflicted Buy',       [r for r in hitter_records if r['combined'] == 'Conflicted Buy']),
    ('Sell High (baseline)', [r for r in hitter_records if r['signal'] == 'Sell High']),
    ('Strong Sell',          [r for r in hitter_records if r['combined'] == 'Strong Sell']),
    ('Conflicted Sell',      [r for r in hitter_records if r['combined'] == 'Conflicted Sell']),
    ('Slight Buy (all)',     [r for r in hitter_records if r['signal'] == 'Slight Buy']),
    ('Neutral (all)',        [r for r in hitter_records if r['signal'] == 'Neutral']),
]

for lbl, grp in summary_tiers:
    if not grp: continue
    n = len(grp); c = sum(r['correct'] for r in grp)
    avg_d = statistics.mean(r['woba_delta'] for r in grp)
    print(f"  {lbl:<28} {n:>4} {c:>8} {100*c/n:>8.1f}% {avg_d:>+11.4f}")

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4: VERDICT
# ══════════════════════════════════════════════════════════════════════════════
section('SECTION 4: VERDICT — DOES TREND DATA ADD VALUE?')

def pct(grp): return 100 * sum(r['correct'] for r in grp) / len(grp) if grp else 0

bl_all   = [r for r in hitter_records if r['signal'] == 'Buy Low']
sb_grp   = [r for r in hitter_records if r['combined'] == 'Strong Buy']
cb_grp   = [r for r in hitter_records if r['combined'] == 'Conflicted Buy']
sh_all   = [r for r in hitter_records if r['signal'] == 'Sell High']
ss_grp   = [r for r in hitter_records if r['combined'] == 'Strong Sell']
cs_grp   = [r for r in hitter_records if r['combined'] == 'Conflicted Sell']

bl_base = pct(bl_all);  sh_base = pct(sh_all)
sb_acc  = pct(sb_grp);  ss_acc  = pct(ss_grp)
cb_acc  = pct(cb_grp);  cs_acc  = pct(cs_grp)

print(f"  1. Strong Buy vs Buy Low baseline:   {sb_acc:.1f}% vs {bl_base:.1f}%  ({sb_acc-bl_base:+.1f}pp, N={len(sb_grp)})")
print(f"  2. Strong Sell vs Sell High baseline: {ss_acc:.1f}% vs {sh_base:.1f}%  ({ss_acc-sh_base:+.1f}pp, N={len(ss_grp)})")
print(f"  3. Conflicted Buy vs Buy Low:         {cb_acc:.1f}% vs {bl_base:.1f}%  ({cb_acc-bl_base:+.1f}pp, N={len(cb_grp)})")
print(f"  4. Conflicted Sell vs Sell High:      {cs_acc:.1f}% vs {sh_base:.1f}%  ({cs_acc-sh_base:+.1f}pp, N={len(cs_grp)})")

print()

bl_avg = statistics.mean(r['woba_delta'] for r in bl_all)  if bl_all  else 0
sb_avg = statistics.mean(r['woba_delta'] for r in sb_grp)  if sb_grp  else 0
cb_avg = statistics.mean(r['woba_delta'] for r in cb_grp)  if cb_grp  else 0
sh_avg = statistics.mean(r['woba_delta'] for r in sh_all)  if sh_all  else 0
ss_avg = statistics.mean(r['woba_delta'] for r in ss_grp)  if ss_grp  else 0
cs_avg = statistics.mean(r['woba_delta'] for r in cs_grp)  if cs_grp  else 0

print(f"  Average wOBA delta (ROS - April xwOBA):")
print(f"    Buy Low all:    {bl_avg:+.4f}   Strong Buy:     {sb_avg:+.4f}   Conflicted Buy:  {cb_avg:+.4f}")
print(f"    Sell High all:  {sh_avg:+.4f}   Strong Sell:    {ss_avg:+.4f}   Conflicted Sell: {cs_avg:+.4f}")

print()
print('  INTERPRETATION:')
if sb_acc > bl_base and sb_avg > bl_avg:
    print('  ✅ Strong Buy outperforms Buy Low — trend confirmation adds signal value.')
else:
    print('  ⚠️  Strong Buy does NOT outperform Buy Low — trend confirmation uncertain.')

if ss_acc > sh_base and ss_avg < sh_avg:
    print('  ✅ Strong Sell outperforms Sell High — trend confirmation adds signal value.')
else:
    print('  ⚠️  Strong Sell does NOT outperform Sell High — trend confirmation uncertain.')

if cb_acc < bl_base:
    print('  ✅ Conflicted Buy correctly identifies weaker signals — useful as a caution flag.')
else:
    print('  ⚠️  Conflicted Buy does not degrade vs baseline — trend may not add filtering value.')

if cs_acc < sh_base:
    print('  ✅ Conflicted Sell correctly identifies weaker signals — useful as a caution flag.')
else:
    print('  ⚠️  Conflicted Sell does not degrade vs baseline — filtering effect uncertain.')

print()
print('  SAMPLE SIZE NOTE:')
print(f'    Buy Low N={len(bl_all)}, Sell High N={len(sh_all)} — small groups, results noisy.')
print('    ⚠️  Trend proxy uses FULL-SEASON xwOBA (forward-looking).')
print('    2026 live system uses game-log rolling windows (no leakage).')

# ── Save CSV ──────────────────────────────────────────────────────────────────
FIELDS = [
    'name', 'batter_id', 'signal', 'trend_dir', 'trend_delta', 'combined',
    'april_xwoba', 'fs_xwoba', 'ros_woba', 'woba_delta',
    'april_pa', 'ros_pa', 'correct',
]
with open('data/trend_signal_backtest_2025.csv', 'w', encoding='utf-8', newline='') as f:
    w = csv.DictWriter(f, fieldnames=FIELDS)
    w.writeheader()
    w.writerows(hitter_records)

print()
print(f'Saved {len(hitter_records)} hitter rows -> data/trend_signal_backtest_2025.csv')
