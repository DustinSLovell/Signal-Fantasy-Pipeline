# New Variables Diagnostic Report
*Generated: April 25, 2026 | Read-only analysis — no files modified*

---

## Data Readiness Summary

| Variable | Career baseline | Current 2026 | Delta computable | What's missing |
|----------|----------------|--------------|------------------|----------------|
| Pitch mix evolution | **PARTIAL** (318–504 pitchers depending on field) | **EXISTS** (461 pitchers) | **YES** for 251 pitchers | Per-pitch spin rate; 67 pitchers in current with no career pm baseline |
| K% trend (hitters) | **MISSING** | **EXISTS** (415 hitters, all) | **NO** (yet) | Career K% baseline — buildable from backtest_cache v4_april CSVs |
| Pull rate trend | **MISSING** | **EXISTS** (415 hitters, all) | **NO** (yet) | Career pull rate baseline — buildable from same backtest_cache CSVs |

---

## VARIABLE 1 — Pitch Mix Evolution (Pitchers)

### What exists

**Career baseline — two files:**

`data/pitcher_career_pitch_mix.json` — **318 pitchers**, 111.7KB
```
Fields per pitcher:
  name, career_pitch_types (list), career_pitches (int), n_seasons (int)
  career_usage:     {pitch_type: float}   ← per-pitch usage %
  career_swstr:     {pitch_type: float}   ← per-pitch SwStr%
  career_swstr_overall: float
  career_primary_velo:  float             ← overall primary velo only (not per-pitch)
```
Baseline window: 2022–2025 seasons (varies per pitcher, n_seasons field present).
**No per-pitch velocity breakdown. No spin rate at all.**

`data/pitcher_career_stuff.json` — **504 pitchers**, 128.9KB
```
Fields per pitcher:
  name, seasons (list), n_seasons (int), career_pitch_count (int)
  career_swstr_pct:   float   ← overall only
  career_fb_velo:     float   ← fastball velocity (overall, not per-pitch)
  career_spin_rate:   float   ← overall spin rate (not per-pitch)
```
Covers more pitchers (504) than career_pitch_mix (318) but coarser — no per-pitch breakdown.

**Current 2026 — two files:**

`data/pitcher_current_pitch_mix.json` — **461 pitchers**, 271.6KB
```
Fields per pitcher:
  curr_pitch_types (list), total_pitches_2026 (int)
  curr_usage:          {pitch_type: float}   ← per-pitch usage %
  curr_swstr:          {pitch_type: float}   ← per-pitch SwStr%
  curr_velo:           {pitch_type: float}   ← per-pitch velocity  ← KEY
  curr_swstr_overall:  float
  curr_primary_velo:   float
  curr_fb_velo:        float
```
**Has per-pitch velocity. No per-pitch spin rate.**

`data/pitcher_stuff_current_2026.csv` — **417 pitchers**, 7 columns
```
Columns: pitcher_id, name, curr_swstr_pct, curr_fb_velo, curr_spin_rate, n_fastballs, n_pa
```
Has current overall spin rate — pairs with career_spin_rate in career_stuff.json.

**Usage in score_pitcher_luck.py:**
- Line 814: stuff+ (arsenal quality) used as a modifier — reads `pitcher_stuff_current_2026.csv`
- Pitch mix **evolution** (delta vs career) is NOT currently computed or used anywhere
- Pitch types, usage %, and per-pitch SwStr% from `pitcher_current_pitch_mix.json` are not yet wired into the scorer

### Coverage overlap (pitchers with computable deltas)

| Delta | Files needed | Overlap n | Notes |
|-------|-------------|-----------|-------|
| Usage % delta (per pitch) | career_pm + curr_pm | **251** | Misses 67 curr_pm pitchers with no career baseline |
| Primary velo delta | career_pm + curr_pm | **251** | Only overall primary, not per-pitch career |
| Per-pitch velo delta | career_pm + curr_pm | **251** | Career has only overall velo; curr has per-pitch velo |
| SwStr% delta (per pitch) | career_pm + curr_pm | **251** | Directly computable |
| Overall SwStr% delta | career_stuff + curr_stuff | **276** | Broader coverage via career_stuff.json |
| Spin rate delta (overall) | career_stuff + curr_csv | **276** | Both have overall spin only — no per-pitch |
| Per-pitch spin delta | NOT AVAILABLE | — | Would require new fetch from Statcast API |

### Gap analysis

**Have now (no new fetch):**
- Usage % change per pitch type (curr_usage - career_usage) for 251 pitchers
- SwStr% change per pitch type (new pitch getting whiffs?) for 251 pitchers
- Per-pitch current velocity (curr_velo) but only overall career velocity for comparison
- Overall fastball velocity delta (career_fb_velo vs curr_fb_velo) for 276 pitchers
- Overall spin rate delta for 276 pitchers

**Would require new fetch:**
- Per-pitch spin rate baseline (career) — would need to build from Statcast parquets
- Coverage for the 210 pitchers in curr_pm with no career_pm entry (rookies, new arms)

**Implementation complexity: LOW**
All data for basic version (usage %, SwStr%, velo delta) already present in existing JSON files.
Computing deltas is a dictionary join — no new data pipeline required.

**New data fetch required: NO** (for basic version)
YES for per-pitch spin rate breakdown.

**Estimated build time: 45–60 min Claude Code session**
- Write `build_pitch_mix_delta.py` to compute deltas from existing JSONs
- Add `pitch_mix_delta_score` component to `score_pitcher_luck.py`
- Run validate_formulas.py + backtest to confirm

---

## VARIABLE 2 — K% Trend (Hitters)

### What exists

**Current 2026 K%:**
`luck_scores.csv` — `k_rate` column present for **all 415 hitters**, range 0.000–0.636
- Computed by `process_stats.py` `calc_k_rate()` (line 217) from `hitters_statcast.csv`
- Formula: `(strikeout + strikeout_double_play) / plate_appearances`

**Current use in score_luck.py:**
- Lines 1034–1037: `k_rate` used as discipline **modifier** on buy signals only
  - If `k_rate > 0.28` → dampens buy score (poor discipline)
  - If `k_rate < 0.18` (combined with BB > 10%) → amplifies buy score
  - NOT used as a standalone trend signal

**Career K% baseline:**
- `hitter_career_discipline.json` (672 hitters): only has `career_o_swing`, `career_oop_pitches`
  — **NO K% field of any kind**
- `career_stats.json` (varies): only `career_pa`, `birth_year`, `avg_exit_velocity`
  — **NO K%**
- `fg_batting_2022–2025.csv`: only wOBA/BA/xwOBA/BIP fields
  — **NO K%**
- `fg_batting_ev_2022–2025.csv`: only EV/barrel/sweet spot metrics
  — **NO K%**

**Can we build career K% from existing cache?**
YES — `backtest_cache/v4_april_{year}.csv` exists for 2022, 2023, 2024, 2025.
These have `events`, `batter`, `stand` columns. `calc_k_rate()` already knows how to
process this format (it's the same function `process_stats.py` uses for current data).
Single pass over 4 years of April data (4 × ~150K rows) yields per-batter career April K%.

Note: "career K%" from April-only data is directionally correct but slightly elevated vs
full-season K% (~+2–3pp on average). This is acceptable for a trend signal since we're
comparing April 2026 K% to April 2022–2025 baseline (apples-to-apples).

### Gap analysis

**Have now:** Current 2026 K% for all 415 hitters in luck_scores.csv

**Missing:** Career K% baseline file — does not exist in any form

**Path to build:** 
1. Write `build_hitter_career_discipline_v2.py` (or extend existing script)
2. Loop over `backtest_cache/v4_april_{year}.csv` for 2022–2025
3. Apply `calc_k_rate()` per batter per year
4. Average across years → `data/hitter_career_k_pull.json`
5. `k_pct_delta = luck_scores.k_rate - career_k_rate`

**Implementation complexity: MEDIUM**
Building the career baseline requires a new script but uses existing infrastructure.
Delta computation and scoring integration are straightforward.

**New data fetch required: NO**
All needed raw data already in `backtest_cache/v4_april_*.csv` (2022–2025).

**Estimated build time: 60–90 min Claude Code session**
(can be combined with pull rate — same cache files, single script)

---

## VARIABLE 3 — Pull Rate Trend (Hitters)

### What exists

**Current 2026 pull rate:**
`luck_scores.csv` — `pull_rate` column present for **all 415 hitters**, range 0.000–0.750
- Computed by `process_stats.py` `calc_pull_rate()` (lines 152–185)
- Formula: pulled fair BIP / total fair BIP, using `hc_x`, `hc_y`, `stand` from Statcast
- Threshold: 20° from dead-center toward pull side (league average ~39%)

**Hard pull rate:** Not directly stored but computable from `hitters_statcast.csv`
which has both `launch_speed` and `hc_x`/`hc_y`/`stand`.

**Current use in score_luck.py:**
- Lines 200–218: `_pull_modifier()` uses `pull_rate` to **dampen HR/FB luck component**
  for strong pull hitters (pull > 0.45 → reduce HR/FB luck estimate)
  — NOT used as a standalone trend signal

**Career pull rate baseline:**
- `hitter_career_discipline.json`: NO pull rate field
- `career_stats.json`: NO pull rate
- `fg_batting_ev_*.csv`: has `fbld` (fly ball distance) and directional info but NOT pull %
  — these files have `avg_hit_angle`, `gb` but not directional pull breakdown
- No existing career pull rate file anywhere in the project

**Can we build career pull rate from existing cache?**
YES — same `backtest_cache/v4_april_{year}.csv` files used for K%.
These have `hc_x`, `hc_y`, `stand`, `bb_type`, `events` — exactly what `calc_pull_rate()`
needs. The function already handles the geometry calculation.

### Gap analysis

**Have now:** Current 2026 pull rate for all 415 hitters in luck_scores.csv

**Missing:** Career pull rate baseline file — does not exist in any form

**Path to build:**
1. Same script as K% career build (process both in single pass)
2. Loop over `backtest_cache/v4_april_{year}.csv` for 2022–2025
3. Apply `calc_pull_rate()` per batter per year
4. Average across years → `data/hitter_career_k_pull.json` (combined with K%)
5. `pull_rate_delta = luck_scores.pull_rate - career_pull_rate`

**Hard pull rate delta:**
`hitters_statcast.csv` has `launch_speed` + coordinates for 2026.
Career hard pull would require same from backtest_cache files. Doable in same pass.

**Implementation complexity: MEDIUM**
(Same complexity as K% — build together in one script, shared infrastructure)

**New data fetch required: NO**
All needed raw data already in `backtest_cache/v4_april_*.csv`.

**Estimated build time: Combined with K% → 60–90 min total**
(not additive — same script handles both; marginal cost is ~15 min for pull rate)

---

## Combined Build Recommendation

K% trend and pull rate trend share identical data requirements and can be built
in a single script (`build_hitter_career_trends.py`):

```python
# Pseudo-structure
for year in [2022, 2023, 2024, 2025]:
    df = pd.read_csv(f"backtest_cache/v4_april_{year}.csv")
    k_rates[year]    = calc_k_rate(df)       # already exists in process_stats.py
    pull_rates[year] = calc_pull_rate(df)    # already exists in process_stats.py

# Average across years per batter
# Save to data/hitter_career_k_pull.json
```

Both functions (`calc_k_rate`, `calc_pull_rate`) already exist in `process_stats.py`.
No new algorithm needed — just orchestration over historical cache.

---

## Implementation Complexity and Build Time

| Variable | Complexity | New fetch? | Fetch source | Build time |
|----------|-----------|-----------|-------------|------------|
| Pitch mix evolution | **LOW** | NO | — | 45–60 min |
| K% trend | **MEDIUM** | NO | backtest_cache v4_april CSVs | 60–90 min |
| Pull rate trend | **MEDIUM** | NO (combined w/ K%) | backtest_cache v4_april CSVs | +15 min |
| **All three combined** | MEDIUM | NO | — | **~2 hrs** |

---

## Score Integration Notes

**score_pitcher_luck.py pitch mix signal:**
- Natural fit as a modifier on the BUY side composite score
- A pitcher adding a new swing-and-miss offering (high curr_swstr, low career_swstr for that type)
  amplifies buy signal; dramatic velocity drop dampens it
- Draft: `pitch_mix_signal = usage_delta * new_pitch_swstr + velo_delta * weight`

**score_luck.py K% signal:**
- Currently k_rate used as binary gate (>0.28 = bad, <0.18 + BB>10% = good)
- Trend adds directionality: improving K% (delta < 0 = fewer strikeouts) amplifies
  buy signals; worsening K% dampens them
- Draft: `k_trend_modifier = clip(k_pct_delta * -8.0, -0.15, +0.15)` (negative delta = good)

**score_luck.py pull rate signal:**
- Currently pull_rate used as HR/FB dampener for pull hitters
- Trend adds: sudden increase in pull rate may signal swing change (buy) or
  shift in approach (monitor); hard pull rate increase is more predictive
- Draft: signal only fires when `pull_rate_delta > 0.05` AND `hard_hit_rate` above avg

---

*No files were modified during this diagnostic.*
