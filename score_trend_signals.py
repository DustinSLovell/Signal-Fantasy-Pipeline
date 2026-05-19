"""score_trend_signals.py
DEPRECATED — superseded by score_trend_signals_v2.py as of May 19, 2026.
v2 uses a seven-layer contact-quality architecture (xwOBA gap, exit velocity,
hard-hit%, barrel%, bat speed, plate discipline) with 2026 Baseball Savant
game logs. Do not run this script. Left in place for reference only.

Original: Mid-season trajectory trend signal system.
Detects TRAJECTORY over the last 3-4 weeks, separate from the static
April luck signals (Buy Low / Sell High).

DATA CONSTRAINTS:
  Hitter game logs contain: R, H, HR, RBI, SB, AB  (no xwOBA/wOBA/BABIP)
  Pitcher game logs contain: IP, ER, H, BB, K       (no FIP/xERA, no HR allowed)

  Hitter trend therefore uses:  BA + HR/AB rate
  Pitcher trend uses:           ERA + K/9 (BB/9 as tertiary)

WINDOWS:
  Recent  = last 21 calendar days from REF_DATE
  Prior   = 21 days immediately before the recent window
"""
import csv, json, os, sys
from datetime import date, timedelta

# ── Config ─────────────────────────────────────────────────────────────────────
REF_DATE       = date(2026, 5, 17)     # most recent game date in logs
RECENT_DAYS    = 21
PRIOR_DAYS     = 21

# Hitter thresholds (BA-based; game logs lack xwOBA/wOBA)
H_BA_HOT       =  0.035   # BA delta: recent > prior by this much → hot
H_BA_COLD      =  0.035   # BA delta: recent < prior by this much → cold
H_BA_STRONG    =  0.055   # stronger signal for Emerging/Fading tiers
H_MIN_AB       =  30      # minimum AB in recent window to qualify

# Pitcher thresholds (ERA + K/9; no FIP without HR allowed)
P_ERA_HOT      =  0.50    # ERA drop: prior - recent >= this → improving
P_ERA_COLD     =  0.50    # ERA rise: recent - prior >= this → declining
P_ERA_STRONG   =  0.80    # stronger for Emerging/Fading tiers
P_K9_CONF      =  0.80    # K/9 confirmation (improves signal quality)
P_MIN_IP       = 15.0     # minimum IP in recent window

GAME_LOG_DIR   = 'data/game_logs'
OUT_CSV        = 'data/trend_signals_2026.csv'

# ── Window boundaries ──────────────────────────────────────────────────────────
recent_end   = REF_DATE
recent_start = REF_DATE - timedelta(days=RECENT_DAYS - 1)
prior_end    = recent_start - timedelta(days=1)
prior_start  = prior_end   - timedelta(days=PRIOR_DAYS - 1)


# ── Helpers ───────────────────────────────────────────────────────────────────
def flt(v, default=None):
    try: return float(v)
    except Exception: return default

def load_csv(path):
    with open(path, encoding='utf-8') as f:
        return list(csv.DictReader(f))

def in_window(game_date_str, start, end):
    d = date.fromisoformat(game_date_str)
    return start <= d <= end

def games_in(games, start, end):
    return [g for g in games if in_window(g['date'], start, end)]


# ── Load luck signals ─────────────────────────────────────────────────────────
hitter_luck  = {}   # mlbam_id (int) -> {verdict, luck_score, name, fp_rank}
pitcher_luck = {}

for r in load_csv('luck_scores.csv'):
    bid = int(r['batter'])
    hitter_luck[bid] = {
        'name':       r['name'],
        'verdict':    r['verdict'],
        'luck_score': flt(r.get('luck_score'), 0),
        'fp_rank':    r.get('fp_rank', ''),
    }

for r in load_csv('pitcher_luck_scores.csv'):
    pid = int(r['pitcher'])
    pitcher_luck[pid] = {
        'name':       r['name'],
        'verdict':    r['verdict'],
        'luck_score': flt(r.get('luck_score'), 0),
        'fp_rank':    r.get('fp_rank', ''),
    }


# ── HITTER trend processing ───────────────────────────────────────────────────
def compute_hitter_window(games):
    ab = sum(g['AB'] for g in games)
    h  = sum(g['H']  for g in games)
    hr = sum(g['HR'] for g in games)
    r  = sum(g['R']  for g in games)
    rbi= sum(g['RBI'] for g in games)
    sb = sum(g['SB'] for g in games)
    ba       = h  / ab if ab > 0 else None
    hr_rate  = hr / ab if ab > 0 else None
    prod_ab  = (r + rbi) / ab if ab > 0 else None  # R+RBI per AB proxy
    return {'ab': ab, 'h': h, 'hr': hr, 'ba': ba,
            'hr_rate': hr_rate, 'prod_ab': prod_ab, 'sb': sb}

def classify_hitter_trend(rec, pri):
    """Returns (trend_dir, strength, notes)"""
    if rec['ab'] < H_MIN_AB:
        return 'Insufficient', 0.0, f"only {rec['ab']} AB in recent window"
    if pri['ab'] < 15:
        return 'Insufficient', 0.0, f"only {pri['ab']} AB in prior window"

    ba_delta = (rec['ba'] or 0) - (pri['ba'] or 0)
    hr_delta = (rec['hr_rate'] or 0) - (pri['hr_rate'] or 0)

    if ba_delta >= H_BA_STRONG:
        return 'Hot', abs(ba_delta), f"BA +{ba_delta:+.3f}"
    if ba_delta >= H_BA_HOT:
        # Require HR rate not cratering for a clean hot signal
        if hr_delta >= -0.010:
            return 'Hot', abs(ba_delta), f"BA {ba_delta:+.3f}"
        return 'Mixed', abs(ba_delta), f"BA {ba_delta:+.3f} but HR rate down"
    if ba_delta <= -H_BA_STRONG:
        return 'Cold', abs(ba_delta), f"BA {ba_delta:+.3f}"
    if ba_delta <= -H_BA_HOT:
        if hr_delta <= 0.010:
            return 'Cold', abs(ba_delta), f"BA {ba_delta:+.3f}"
        return 'Mixed', abs(ba_delta), f"BA {ba_delta:+.3f} but HR rate up"
    return 'Neutral', abs(ba_delta), f"BA {ba_delta:+.3f} (no clear trend)"


# ── PITCHER trend processing ──────────────────────────────────────────────────
def compute_pitcher_window(games):
    ip  = sum(g['IP']  for g in games)
    er  = sum(g['ER']  for g in games)
    h   = sum(g['H']   for g in games)
    bb  = sum(g['BB']  for g in games)
    k   = sum(g['K']   for g in games)
    era  = (er * 9) / ip  if ip > 0 else None
    k9   = (k  * 9) / ip  if ip > 0 else None
    bb9  = (bb * 9) / ip  if ip > 0 else None
    whip = (h + bb) / ip  if ip > 0 else None
    return {'ip': ip, 'er': er, 'era': era, 'k9': k9, 'bb9': bb9, 'whip': whip}

def classify_pitcher_trend(rec, pri):
    """Returns (trend_dir, strength, notes)"""
    if rec['ip'] < P_MIN_IP:
        return 'Insufficient', 0.0, f"only {rec['ip']:.1f} IP in recent window"
    if pri['ip'] < 10.0:
        return 'Insufficient', 0.0, f"only {pri['ip']:.1f} IP in prior window"

    era_delta = (rec['era'] or 0) - (pri['era'] or 0)   # negative = improving
    k9_delta  = (rec['k9']  or 0) - (pri['k9']  or 0)   # positive = improving

    if era_delta <= -P_ERA_STRONG and k9_delta >= 0:
        return 'Hot', abs(era_delta), f"ERA {era_delta:+.2f}, K/9 {k9_delta:+.1f}"
    if era_delta <= -P_ERA_HOT:
        if k9_delta >= -P_K9_CONF:
            return 'Hot', abs(era_delta), f"ERA {era_delta:+.2f}"
        return 'Mixed', abs(era_delta), f"ERA {era_delta:+.2f} but K/9 down"
    if era_delta >= P_ERA_STRONG and k9_delta <= 0:
        return 'Cold', abs(era_delta), f"ERA {era_delta:+.2f}, K/9 {k9_delta:+.1f}"
    if era_delta >= P_ERA_HOT:
        if k9_delta <= P_K9_CONF:
            return 'Cold', abs(era_delta), f"ERA {era_delta:+.2f}"
        return 'Mixed', abs(era_delta), f"ERA {era_delta:+.2f} but K/9 up"
    return 'Neutral', abs(era_delta), f"ERA {era_delta:+.2f} (no clear trend)"


# ── Combined signal logic ─────────────────────────────────────────────────────
def combined_signal(luck_verdict, trend_dir):
    v = (luck_verdict or '').lower()
    t = trend_dir

    is_buy  = 'buy low'   in v
    is_sell = 'sell high' in v
    is_sbuy = 'slight buy' in v
    is_ssell= 'slight sell' in v
    is_neut = not (is_buy or is_sell or is_sbuy or is_ssell)

    if   is_buy  and t == 'Hot':   return 'Strong Buy'
    elif is_sell and t == 'Cold':  return 'Strong Sell'
    elif is_buy  and t == 'Cold':  return 'Conflicted (Buy vs Cold)'
    elif is_sell and t == 'Hot':   return 'Conflicted (Sell vs Hot)'
    elif is_neut and t == 'Hot':   return 'Emerging Buy'
    elif is_neut and t == 'Cold':  return 'Fading Sell'
    elif (is_sbuy or is_ssell) and t == 'Hot':  return 'Slight Buy + Hot'
    elif (is_sbuy or is_ssell) and t == 'Cold': return 'Slight Sell + Cold'
    elif t in ('Hot', 'Cold'):     return f'Trend Only: {t}'
    else:                          return 'No Signal'


# ── Main processing loop ──────────────────────────────────────────────────────
records = []
skipped_min = 0

for fn in sorted(os.listdir(GAME_LOG_DIR)):
    if not fn.endswith('.json'):
        continue

    path = os.path.join(GAME_LOG_DIR, fn)
    with open(path, encoding='utf-8') as f:
        log = json.load(f)

    mlbam   = log['mlb_id']
    is_hit  = fn.startswith('hitter_')
    is_pit  = fn.startswith('pitcher_')
    luck    = (hitter_luck if is_hit else pitcher_luck).get(mlbam, {})
    verdict = luck.get('verdict', 'Neutral')
    luck_sc = luck.get('luck_score', 0.0)
    fp_rank = luck.get('fp_rank', '')
    name    = log.get('name', luck.get('name', f'ID {mlbam}'))

    games = log.get('games', [])
    rec_games = games_in(games, recent_start, recent_end)
    pri_games = games_in(games, prior_start,  prior_end)

    if is_hit:
        rec = compute_hitter_window(rec_games)
        pri = compute_hitter_window(pri_games)
        trend_dir, strength, notes = classify_hitter_trend(rec, pri)

        if trend_dir == 'Insufficient':
            skipped_min += 1
            continue

        records.append({
            'player_name':        name,
            'mlbam_id':           mlbam,
            'player_type':        'hitter',
            'pos':                '',
            'luck_signal':        verdict,
            'luck_score':         round(luck_sc, 4),
            'fp_rank':            fp_rank,
            'trend_dir':          trend_dir,
            'trend_strength':     round(strength, 4),
            'trend_notes':        notes,
            'combined_signal':    combined_signal(verdict, trend_dir),
            # Recent window
            'recent_metric':      round(rec['ba'], 3) if rec['ba'] is not None else '',
            'prior_metric':       round(pri['ba'], 3) if pri['ba'] is not None else '',
            'metric_delta':       round((rec['ba'] or 0) - (pri['ba'] or 0), 3),
            'metric_label':       'BA',
            'recent_secondary':   round(rec['hr_rate'], 4) if rec['hr_rate'] is not None else '',
            'prior_secondary':    round(pri['hr_rate'], 4) if pri['hr_rate'] is not None else '',
            'secondary_label':    'HR/AB',
            'recent_volume':      rec['ab'],
            'recent_volume_label':'AB',
            'prior_volume':       pri['ab'],
            'window_start_recent':recent_start.isoformat(),
            'window_end_recent':  recent_end.isoformat(),
            'window_start_prior': prior_start.isoformat(),
            'window_end_prior':   prior_end.isoformat(),
        })

    elif is_pit:
        rec = compute_pitcher_window(rec_games)
        pri = compute_pitcher_window(pri_games)
        trend_dir, strength, notes = classify_pitcher_trend(rec, pri)

        if trend_dir == 'Insufficient':
            skipped_min += 1
            continue

        records.append({
            'player_name':        name,
            'mlbam_id':           mlbam,
            'player_type':        'pitcher',
            'pos':                '',
            'luck_signal':        verdict,
            'luck_score':         round(luck_sc, 4),
            'fp_rank':            fp_rank,
            'trend_dir':          trend_dir,
            'trend_strength':     round(strength, 4),
            'trend_notes':        notes,
            'combined_signal':    combined_signal(verdict, trend_dir),
            # Recent window
            'recent_metric':      round(rec['era'], 2) if rec['era'] is not None else '',
            'prior_metric':       round(pri['era'], 2) if pri['era'] is not None else '',
            'metric_delta':       round((rec['era'] or 0) - (pri['era'] or 0), 2),
            'metric_label':       'ERA',
            'recent_secondary':   round(rec['k9'],  2) if rec['k9']  is not None else '',
            'prior_secondary':    round(pri['k9'],  2) if pri['k9']  is not None else '',
            'secondary_label':    'K/9',
            'recent_volume':      round(rec['ip'], 1),
            'recent_volume_label':'IP',
            'prior_volume':       round(pri['ip'], 1),
            'window_start_recent':recent_start.isoformat(),
            'window_end_recent':  recent_end.isoformat(),
            'window_start_prior': prior_start.isoformat(),
            'window_end_prior':   prior_end.isoformat(),
        })


# ── Save CSV ──────────────────────────────────────────────────────────────────
FIELDS = [
    'player_name', 'mlbam_id', 'player_type', 'pos',
    'luck_signal', 'luck_score', 'fp_rank',
    'trend_dir', 'trend_strength', 'trend_notes', 'combined_signal',
    'recent_metric', 'prior_metric', 'metric_delta', 'metric_label',
    'recent_secondary', 'prior_secondary', 'secondary_label',
    'recent_volume', 'recent_volume_label', 'prior_volume',
    'window_start_recent', 'window_end_recent',
    'window_start_prior',  'window_end_prior',
]

with open(OUT_CSV, 'w', encoding='utf-8', newline='') as f:
    w = csv.DictWriter(f, fieldnames=FIELDS)
    w.writeheader()
    w.writerows(records)


# ── Summary printing ──────────────────────────────────────────────────────────
def hdr(title):
    print()
    print('=' * 72)
    print(title)
    print('=' * 72)

def print_table(rows, col_labels, col_fns, indent=2):
    pad = ' ' * indent
    widths = [len(lbl) for lbl in col_labels]
    data = [[fn(r) for fn in col_fns] for r in rows]
    for row_vals in data:
        for i, v in enumerate(row_vals):
            widths[i] = max(widths[i], len(str(v)))
    hline = pad + '  '.join('-' * w for w in widths)
    hrow  = pad + '  '.join(lbl.ljust(w) for lbl, w in zip(col_labels, widths))
    print(hrow)
    print(hline)
    for row_vals in data:
        print(pad + '  '.join(str(v).ljust(w) for v, w in zip(row_vals, widths)))

# Split by combined signal and type
def grp(signal, ptype=None):
    return [r for r in records
            if r['combined_signal'] == signal
            and (ptype is None or r['player_type'] == ptype)]

# ── DATA NOTE ────────────────────────────────────────────────────────────────
print()
print('NOTE: Hitter trend uses BA + HR/AB (game logs lack xwOBA/wOBA/BABIP).')
print('      Pitcher trend uses ERA + K/9 (game logs lack FIP/xERA/HR allowed).')
print(f'      Windows: Recent {recent_start} to {recent_end} | Prior {prior_start} to {prior_end}')
print(f'      Qualified: {len(records)} players | Skipped (min sample): {skipped_min}')

# Distribution
hdr('SIGNAL DISTRIBUTION')
dist = {}
for r in records:
    key = r['combined_signal']
    dist[key] = dist.get(key, 0) + 1
for sig, cnt in sorted(dist.items(), key=lambda x: -x[1]):
    print(f'  {sig:<40} {cnt:>3}')

# ── STRONG BUY ────────────────────────────────────────────────────────────────
hdr('STRONG BUY — Buy Low luck + Trending Hot')
sb = sorted(grp('Strong Buy'), key=lambda r: -r['trend_strength'])
if sb:
    print_table(sb,
        ['Player', 'Luck Score', 'FP Rank', f'Prior BA/ERA', f'Recent BA/ERA', 'Delta', 'Vol', 'Notes'],
        [lambda r: r['player_name'][:22],
         lambda r: f"{r['luck_score']:+.2f}",
         lambda r: f"#{r['fp_rank']}" if r['fp_rank'] else '—',
         lambda r: str(r['prior_metric']),
         lambda r: str(r['recent_metric']),
         lambda r: f"{r['metric_delta']:+.3f}" if r['player_type']=='hitter' else f"{r['metric_delta']:+.2f}",
         lambda r: f"{r['recent_volume']} {r['recent_volume_label']}",
         lambda r: r['trend_notes']])
else:
    print('  (none)')

# ── STRONG SELL ──────────────────────────────────────────────────────────────
hdr('STRONG SELL — Sell High luck + Trending Cold')
ss = sorted(grp('Strong Sell'), key=lambda r: -r['trend_strength'])
if ss:
    print_table(ss,
        ['Player', 'Luck Score', 'FP Rank', 'Prior', 'Recent', 'Delta', 'Vol', 'Notes'],
        [lambda r: r['player_name'][:22],
         lambda r: f"{r['luck_score']:+.2f}",
         lambda r: f"#{r['fp_rank']}" if r['fp_rank'] else '—',
         lambda r: str(r['prior_metric']),
         lambda r: str(r['recent_metric']),
         lambda r: f"{r['metric_delta']:+.3f}" if r['player_type']=='hitter' else f"{r['metric_delta']:+.2f}",
         lambda r: f"{r['recent_volume']} {r['recent_volume_label']}",
         lambda r: r['trend_notes']])
else:
    print('  (none)')

# ── EMERGING BUY ─────────────────────────────────────────────────────────────
hdr('EMERGING BUY — Neutral luck + Trending Hot')
eb = sorted(grp('Emerging Buy'), key=lambda r: -r['trend_strength'])
if eb:
    print_table(eb,
        ['Player', 'Luck Score', 'FP Rank', 'Prior', 'Recent', 'Delta', 'Vol'],
        [lambda r: r['player_name'][:22],
         lambda r: f"{r['luck_score']:+.2f}",
         lambda r: f"#{r['fp_rank']}" if r['fp_rank'] else '—',
         lambda r: str(r['prior_metric']),
         lambda r: str(r['recent_metric']),
         lambda r: f"{r['metric_delta']:+.3f}" if r['player_type']=='hitter' else f"{r['metric_delta']:+.2f}",
         lambda r: f"{r['recent_volume']} {r['recent_volume_label']}"])
else:
    print('  (none)')

# ── FADING SELL ──────────────────────────────────────────────────────────────
hdr('FADING SELL — Neutral luck + Trending Cold')
fs = sorted(grp('Fading Sell'), key=lambda r: -r['trend_strength'])
if fs:
    print_table(fs,
        ['Player', 'Luck Score', 'FP Rank', 'Prior', 'Recent', 'Delta', 'Vol'],
        [lambda r: r['player_name'][:22],
         lambda r: f"{r['luck_score']:+.2f}",
         lambda r: f"#{r['fp_rank']}" if r['fp_rank'] else '—',
         lambda r: str(r['prior_metric']),
         lambda r: str(r['recent_metric']),
         lambda r: f"{r['metric_delta']:+.3f}" if r['player_type']=='hitter' else f"{r['metric_delta']:+.2f}",
         lambda r: f"{r['recent_volume']} {r['recent_volume_label']}"])
else:
    print('  (none)')

# ── CONFLICTED ───────────────────────────────────────────────────────────────
hdr('CONFLICTED — Luck and trend pointing in opposite directions')
conf = sorted(
    [r for r in records if r['combined_signal'].startswith('Conflicted')],
    key=lambda r: (-abs(r['luck_score']), -r['trend_strength'])
)
if conf:
    print_table(conf,
        ['Player', 'Luck Signal', 'Luck Score', 'Trend', 'Delta', 'Vol', 'Why Conflicted'],
        [lambda r: r['player_name'][:22],
         lambda r: r['luck_signal'],
         lambda r: f"{r['luck_score']:+.2f}",
         lambda r: r['trend_dir'],
         lambda r: f"{r['metric_delta']:+.3f}" if r['player_type']=='hitter' else f"{r['metric_delta']:+.2f}",
         lambda r: f"{r['recent_volume']} {r['recent_volume_label']}",
         lambda r: r['combined_signal'].replace('Conflicted ','').replace('(','').replace(')','')])
else:
    print('  (none)')

# ── HOT / COLD standalone ────────────────────────────────────────────────────
hdr('ALL HOT PLAYERS (any luck signal)')
hot_all = sorted([r for r in records if r['trend_dir'] == 'Hot'],
                 key=lambda r: -r['trend_strength'])
if hot_all:
    print_table(hot_all,
        ['Player', 'Type', 'Luck Signal', 'Prior', 'Recent', 'Delta', 'Vol', 'Combined'],
        [lambda r: r['player_name'][:22],
         lambda r: r['player_type'][:3],
         lambda r: r['luck_signal'],
         lambda r: str(r['prior_metric']),
         lambda r: str(r['recent_metric']),
         lambda r: f"{r['metric_delta']:+.3f}" if r['player_type']=='hitter' else f"{r['metric_delta']:+.2f}",
         lambda r: f"{r['recent_volume']} {r['recent_volume_label']}",
         lambda r: r['combined_signal']])
else:
    print('  (none)')

hdr('ALL COLD PLAYERS (any luck signal)')
cold_all = sorted([r for r in records if r['trend_dir'] == 'Cold'],
                  key=lambda r: -r['trend_strength'])
if cold_all:
    print_table(cold_all,
        ['Player', 'Type', 'Luck Signal', 'Prior', 'Recent', 'Delta', 'Vol', 'Combined'],
        [lambda r: r['player_name'][:22],
         lambda r: r['player_type'][:3],
         lambda r: r['luck_signal'],
         lambda r: str(r['prior_metric']),
         lambda r: str(r['recent_metric']),
         lambda r: f"{r['metric_delta']:+.3f}" if r['player_type']=='hitter' else f"{r['metric_delta']:+.2f}",
         lambda r: f"{r['recent_volume']} {r['recent_volume_label']}",
         lambda r: r['combined_signal']])
else:
    print('  (none)')

print()
print(f'Saved {len(records)} rows -> {OUT_CSV}')
