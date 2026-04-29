#!/usr/bin/env python3
"""K projection diagnostic — not a production file."""
import csv, math, sys, os
import pandas as pd

sys.path.insert(0, '.')

def _f(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else float('nan')
    except:
        return float('nan')

ROS_SCALE  = 162 / 135
GAMES_REM  = 135
HEALTH     = 0.85
STARTS_REM = int(GAMES_REM / 5 * HEALTH)   # = 22

# ---- Load April 2025 pitcher data ----------------------------------------
print("Loading April 2025 parquet...")
parq = pd.read_parquet('backtest_cache/pitcher_statcast_april_2025.parquet',
    columns=['pitcher','events','game_pk','type','at_bat_number'])

K_EVENTS  = {'strikeout','strikeout_double_play'}
BB_EVENTS = {'walk','intent_walk'}
OUT_EVENTS = {'strikeout','strikeout_double_play','field_out',
              'grounded_into_double_play','double_play','triple_play',
              'force_out','fielders_choice','fielders_choice_out','other_out'}

april_agg = {}
for pid, grp in parq.groupby('pitcher'):
    ev = grp['events'].dropna()
    k   = int(ev.isin(K_EVENTS).sum())
    bb  = int(ev.isin(BB_EVENTS).sum())
    # Outs: count primary outs (grounded into double play counts as 2)
    outs = int(ev.isin(OUT_EVENTS).sum())
    outs += int(ev.isin({'grounded_into_double_play','double_play','triple_play'}).sum())
    ip  = outs / 3.0
    k9  = k / ip * 9 if ip >= 5 else float('nan')
    bb9 = bb / ip * 9 if ip >= 5 else float('nan')
    april_agg[str(int(pid))] = {'k': k, 'bb': bb, 'ip': ip, 'k9': k9, 'bb9': bb9}

print(f"  April pitcher pool: {len(april_agg)} pitchers")

# ---- Load career baselines (FG 2022-2024) --------------------------------
print("Loading FG career baselines (2022-2024)...")
BACKTEST_CACHE = 'backtest_cache'
career_k9_map  = {}
career_ip_map  = {}

for yr in [2022, 2023, 2024]:
    path = os.path.join(BACKTEST_CACHE, f'fg_pitchers_{yr}.csv')
    if not os.path.exists(path):
        print(f"  Missing: {path}")
        continue
    with open(path, newline='', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            pid = str(row.get('xMLBAMID') or row.get('MLBAMID') or '').strip()
            ip  = _f(row.get('IP', 0))
            k9  = _f(row.get('K/9', 0))
            gs  = _f(row.get('GS', 0))
            if not pid or ip <= 0:
                continue
            if pid not in career_k9_map:
                career_k9_map[pid] = []
                career_ip_map[pid] = []
            career_k9_map[pid].append((ip, k9))
            career_ip_map[pid].append((gs, ip))

def get_career_k9(pid):
    if pid not in career_k9_map:
        return 8.5
    data = [(ip, k9) for ip, k9 in career_k9_map[pid]
            if math.isfinite(ip) and math.isfinite(k9) and ip > 0]
    if not data:
        return 8.5
    total_ip = sum(ip for ip, _ in data)
    if total_ip < 10:
        return 8.5
    return sum(ip * k9 for ip, k9 in data) / total_ip

def get_career_ip_per_start(pid):
    if pid not in career_ip_map:
        return 5.60
    data = [(gs, ip) for gs, ip in career_ip_map[pid]
            if math.isfinite(gs) and math.isfinite(ip) and gs > 0]
    if not data:
        return 5.60
    total_gs = sum(gs for gs, _ in data)
    if total_gs < 5:
        return 5.60
    total_ip = sum(ip for _, ip in data)
    return min(7.5, max(3.5, total_ip / total_gs))

# ---- Load backtest C pitchers --------------------------------------------
with open('data/backtest_C_pitchers_2025.csv') as f:
    c_rows = list(csv.DictReader(f))

# ---- Load Steamer for IP comparison -------------------------------------
with open('Steamers 2025 pitchers.csv', newline='', encoding='utf-8-sig') as f:
    steamer = {str(r['MLBAMID']): r for r in csv.DictReader(f)}

# ---- Diagnostic per pitcher ----------------------------------------------
results = []
for row in c_rows:
    bid = str(row['mlbam_id'])
    april_ip  = _f(row.get('april_ip'))
    actual_k  = _f(row.get('actual_k'))
    model_k   = _f(row.get('model_k'))
    steamer_k = _f(row.get('steamer_k'))

    if not all(math.isfinite(v) for v in [actual_k, model_k, steamer_k]):
        continue

    # Reconstruct projected K/9 (same logic as pitcher_true_talent)
    apr = april_agg.get(bid, {})
    april_k9_obs = apr.get('k9', float('nan'))
    car_k9       = get_career_k9(bid)
    car_ip_ps    = get_career_ip_per_start(bid)

    # K/9 blending (70/30 current/career when April data available, else career)
    if math.isfinite(april_k9_obs):
        proj_k9 = round(april_k9_obs * 0.70 + car_k9 * 0.30, 2)
    else:
        proj_k9 = car_k9
    proj_k9 = max(3.0, min(16.0, proj_k9))

    # IP per start blending
    april_starts = max(1, round(april_ip / 5.5)) if april_ip > 0 else 1
    curr_ip_ps   = april_ip / april_starts if april_ip > 0 else car_ip_ps
    proj_ip_ps   = round(max(3.5, min(7.5, curr_ip_ps * 0.60 + car_ip_ps * 0.40)), 2)
    proj_ip_ros  = STARTS_REM * proj_ip_ps
    proj_ip_full = proj_ip_ros * ROS_SCALE   # full-season equivalent

    # K projection
    proj_k_ros  = proj_k9 / 9.0 * proj_ip_ros
    proj_k_full = proj_k_ros * ROS_SCALE

    # Steamer IP
    sr = steamer.get(bid, {})
    steamer_ip = _f(sr.get('IP', float('nan')))

    # Actual K/9 back-compute: actual_k / (actual_ip estimated from CBS actuals)
    # We don't have actual IP for pitchers in the backtest — proxy from Steamer IP
    # (they project close to actual season outcomes)

    results.append({
        'name':        row['name'][:26],
        'mlbam_id':    bid,
        'april_ip':    round(april_ip, 1),
        'april_k9_obs':round(april_k9_obs, 2) if math.isfinite(april_k9_obs) else float('nan'),
        'car_k9':      round(car_k9, 2),
        'proj_k9':     proj_k9,
        'car_ip_ps':   round(car_ip_ps, 2),
        'proj_ip_ps':  proj_ip_ps,
        'proj_ip_ros': round(proj_ip_ros, 1),
        'proj_ip_full':round(proj_ip_full, 1),
        'proj_k_full': round(proj_k_full, 1),
        'model_k':     model_k,
        'actual_k':    actual_k,
        'steamer_k':   steamer_k,
        'steamer_ip':  steamer_ip,
        'our_err':     round(model_k - actual_k, 1),
        'steam_err':   round(steamer_k - actual_k, 1),
    })

n = len(results)
def avg(col): return sum(r[col] for r in results if math.isfinite(r[col])) / n

print(f"\n{'='*70}")
print("SUMMARY — K PROJECTION DIAGNOSTICS")
print(f"{'='*70}")
print(f"n = {n} pitchers (full data)")
print()
print(f"  {'Metric':<35} {'Ours':>10} {'Steamer':>10} {'Actual':>10}")
print(f"  {'-'*35} {'-'*10} {'-'*10} {'-'*10}")
print(f"  {'Avg projected K (full season)':<35} {avg('proj_k_full'):>10.1f} "
      f"{avg('steamer_k'):>10.1f} {avg('actual_k'):>10.1f}")
print(f"  {'Avg model K (from backtest CSV)':<35} {avg('model_k'):>10.1f}")
print(f"  {'K bias (projected − actual)':<35} {avg('our_err'):>+10.1f} {avg('steam_err'):>+10.1f}")
print()
print(f"  {'Avg proj IP (full equiv)':<35} {avg('proj_ip_full'):>10.1f} "
      f"{avg('steamer_ip'):>10.1f}")
print(f"  {'Avg proj IP/start':<35} {avg('proj_ip_ps'):>10.2f}")
print(f"  {'Avg proj K/9':<35} {avg('proj_k9'):>10.2f}")
print(f"  {'Avg career K/9 baseline':<35} {avg('car_k9'):>10.2f}")
apr_k9_vals = [r['april_k9_obs'] for r in results if math.isfinite(r['april_k9_obs'])]
print(f"  {'Avg April K/9 observed':<35} {sum(apr_k9_vals)/len(apr_k9_vals):>10.2f}  (n={len(apr_k9_vals)})")
print(f"  Starts remaining (fixed):  {STARTS_REM}  (=int(135/5×0.85)=int(22.95))")

print()
print("IP DECOMPOSITION:")
print(f"  Projected full-season IP: {avg('proj_ip_full'):.1f}")
print(f"  Steamer full-season IP:   {avg('steamer_ip'):.1f}")
ip_gap = avg('proj_ip_full') - avg('steamer_ip')
print(f"  Gap (ours − Steamer):     {ip_gap:+.1f}  ← {'IP OVER-PROJECTION' if ip_gap > 0 else 'IP under-projection'}")

print()
print("K/9 DECOMPOSITION:")
# What K/9 would explain the actual K given Steamer IP?
steam_ips = [r['steamer_ip'] for r in results if math.isfinite(r['steamer_ip'])]
actual_ks = [r['actual_k'] for r in results if math.isfinite(r['steamer_ip'])]
implied_k9 = sum(k/ip*9 for k, ip in zip(actual_ks, steam_ips) if ip > 0) / len(actual_ks)
our_k9_avg = avg('proj_k9')
print(f"  Actual implied K/9 (actual_k / Steamer_IP × 9): {implied_k9:.2f}")
print(f"  Our projected K/9:                               {our_k9_avg:.2f}")
k9_gap = our_k9_avg - implied_k9
print(f"  Gap (ours − actual):                             {k9_gap:+.2f}  ← {'K/9 OVER-PROJECTION' if k9_gap > 0 else 'ok'}")

print()
print("ROOT CAUSE SPLIT:")
# K error = (proj_ip_full - steamer_ip) × (proj_k9/9) + steamer_ip × (proj_k9 - implied_k9)/9
avg_proj_ip   = avg('proj_ip_full')
avg_steam_ip  = avg('steamer_ip')
avg_proj_k9   = avg('proj_k9')
ip_error_contrib = (avg_proj_ip - avg_steam_ip) * avg_proj_k9 / 9
k9_error_contrib = avg_steam_ip * (avg_proj_k9 - implied_k9) / 9
print(f"  IP error contribution to K bias:  {ip_error_contrib:+.1f}")
print(f"  K/9 error contribution to K bias: {k9_error_contrib:+.1f}")
print(f"  Total estimated bias:             {ip_error_contrib + k9_error_contrib:+.1f}")
print(f"  Actual measured bias:             {avg('our_err'):+.1f}")

print()
print(f"{'='*70}")
print("TOP 20 K OVER-PROJECTIONS (sorted by our_err)")
print(f"{'='*70}")
print(f"{'Name':<28} {'AprIP':>6} {'AprK9':>6} {'CarK9':>6} {'ProjK9':>7} "
      f"{'ProjIP':>7} {'K_proj':>7} {'K_act':>7} {'K_stmr':>7} {'OurErr':>7}")
print('-'*100)
for r in sorted(results, key=lambda x: -x['our_err'])[:20]:
    ak9 = f"{r['april_k9_obs']:.2f}" if math.isfinite(r['april_k9_obs']) else "  N/A"
    print(f"{r['name']:<28} {r['april_ip']:>6.1f} {ak9:>6} {r['car_k9']:>6.2f} "
          f"{r['proj_k9']:>7.2f} {r['proj_ip_full']:>7.1f} "
          f"{r['proj_k_full']:>7.1f} {r['actual_k']:>7.0f} {r['steamer_k']:>7.0f} "
          f"{r['our_err']:>+7.0f}")

print()
print(f"{'='*70}")
print("IP RANGE DISTRIBUTION — ours vs Steamer")
print(f"{'='*70}")
buckets = {'<100': 0, '100-130': 0, '130-160': 0, '160-190': 0, '>190': 0}
steamer_buckets = {'<100': 0, '100-130': 0, '130-160': 0, '160-190': 0, '>190': 0}
for r in results:
    ip_f = r['proj_ip_full']
    s_ip = r['steamer_ip']
    for v, bd in [(ip_f, buckets), (s_ip, steamer_buckets)]:
        if not math.isfinite(v): continue
        if v < 100:   bd['<100'] += 1
        elif v < 130: bd['100-130'] += 1
        elif v < 160: bd['130-160'] += 1
        elif v < 190: bd['160-190'] += 1
        else:         bd['>190'] += 1
print(f"  Bucket     {'Ours':>8} {'Steamer':>8}")
for b in ['<100','100-130','130-160','160-190','>190']:
    print(f"  {b:<12} {buckets[b]:>8} {steamer_buckets[b]:>8}")
