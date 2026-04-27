# CLAUDE.md — The Signal Fantasy
# Auto-read by Claude Code at session start.
# Last updated: April 29, 2026
# DO NOT modify scoring logic without running validate_formulas.py after.

---

## WHAT THIS PROJECT IS

Fantasy baseball analytics pipeline built by Dustin Lovell.
Production ML model that scores hitters and pitchers for luck-based buy/sell signals.
Published on Substack (signalfantasy.substack.com) with live track record from April 22, 2026.

**DO NOT treat this as a learning/experimental project.**
This is a production system with published accuracy numbers and a live audience.
Every change must be validated before shipping.

---

## SESSION START — RUN THESE FIRST

Before doing ANY work, verify the production files are current:

```bash
# 1. Confirm pitcher v2.0 split architecture is present
grep -n "ERA >= 4.00\|ERA >= 3.50\|raw_buy_score\|BUY_QUALIFICATION" score_pitcher_luck.py | head -20

# 2. Confirm pitcher Buy Low ERA floor fix is present (implemented April 25, 2026)
grep -n "3.75\|BUY_LOW_ERA" score_pitcher_luck.py | head -10

# 3. Confirm hitter recalibrated thresholds are present
grep -n "0.150\|0.100\|0.085\|xwOBA_gap\|0.030\|0.380" score_luck.py | head -20

# 4. Confirm K%/pull modifier is wired in (implemented April 25, 2026)
grep -n "k_flag\|pull_flag\|K%/pull\|CAREER_K_PULL" score_luck.py | head -10

# 5. Run formula validation suite
python -X utf8 validate_formulas.py
```

Expected results:
- score_pitcher_luck.py: ERA >= 4.00 gate present, raw_buy_score present
- score_pitcher_luck.py: ERA < 3.75 gate present at line ~967 (Buy Low ERA floor)
- score_luck.py: threshold 0.150 present (Buy Low), 0.100 present (Slight Buy), 0.380 present (xwOBA ceiling)
- score_luck.py: CAREER_K_PULL_PATH present, k_flag/pull_flag columns wired
- validate_formulas.py: 37/37 PASS

If ANY of these fail → STOP. Do not proceed. Report the failure immediately.

---

## ARCHITECTURE — 4 LAYER STACK

```
Layer 1: Signal Model     → luck_score, verdict, tier
           score_luck.py (hitters)
           score_pitcher_luck.py (pitchers — v2.0 split architecture)

Layer 2: Projection Engine → proj_avg, proj_hr, proj_rbi, proj_era etc.
           stat_projections.py
           generate_projections.py

Layer 3: Value Engine      → league1_value, rank
           score_value.py

Layer 4: Trade Analyzer    → trade verdict
           trade_analyzer.py
```

**LAYER 1 IS SACRED. DO NOT MODIFY scoring logic without explicit instruction.**
Changes to Layer 1 require: ablation test + invariant check + validate_formulas.py

---

## CURRENT MODEL VERSIONS

### Hitter Model (recalibrated April 25, 2026):
- Thresholds: Buy Low >0.150 | Slight Buy >0.100 | Slight Sell <-0.085 | Sell High <-0.150
- Gates: Slight Buy requires xwOBA_gap >= 0.030 AND xwOBA < 0.380 (updated April 25 — backtest analysis confirmed 3 failure modes)
- Chase rate modifier (sell-side): gap >0.040 → ×1.10, >0.060 → ×1.15
- Platoon adjustment: Layer 7 — uses career baseline from hitter_career_platoon.json (updated April 26)

### Pitcher Model v2.0 (split architecture — April 23, 2026):
- BUY side: ERA-FIP dominant (×0.60 ERA-FIP, ×0.25 xwOBA, ×0.15 BABIP)
- SELL side: 8-component composite (BABIP, LOB%, ERA-FIP, ERA-xERA, HR/FB, HH%, barrel, SwStr%)
- Classification from RAW score BEFORE confidence scaling
- CSW buy-low-only modifier: csw_gap >+0.025 → ×1.10, <-0.025 → ×0.90

### Financial Motivation Cohort Framework (display-only — April 26-27, 2026):
_assign_cohort() in score_luck.py. contract_cohort column in luck_scores.csv.
Priority: manual override → prove_it → secured ($20M+, 3+yr) → post-prime (33+) → payday (25-31, ≤2yr) → mid-contract
**BUG FIXED April 27:** _assign_cohort was called before df["age"] was set → all players returned "unknown". Fixed by moving apply() call to after df["age"] = ... line.
Distribution (416 hitters, post-Spotrac merge April 28): 1-payday: 160 | 3-secured: 17 | 4-post-prime: 58 | 5-mid-contract: 163 | unknown: 18
Contract data coverage: 31 players loaded (13 manual + 18 from Spotrac Wayback merge)
Cohort 3 (17 players): Ohtani, Judge, Trout, Harper, Seager, Lindor, Turner, Machado, Riley, Bobby Witt Jr., Julio Rodríguez (manual) + Ramírez, Swanson, Bogaerts, Stanton, Olson, Nola, Yelich (Spotrac merge April 28)
Note: Yordan ($19.2M AAV, 1yr remaining) is correctly Cohort 1 (not 3) — below $20M threshold AND below 3yr threshold.

### Additive Modifier Architecture — Version D (adopted April 26, 2026):
All hitter buy signal dampeners use flat additive penalties (NOT multiplicative).
Penalties accumulate in `_buy_penalty` column; capped at H_MAX_COMBINED_PEN=0.040 total.
Applied in one combined pass at the end of all flag detection.

**Calibrated penalties (from sensitivity sweep on 2022-2024 training data):**
- k_flag (K-rate spike >3pp):        -0.010
- pull_flag (pull-rate drop >5pp):   -0.008
- hh_flag (hard-hit rate drop >3pp): -0.012
- speed_flag (sprint YoY >0.3 ft/s): -0.010  (analogue to k_flag)
- chase_flag (chase rise >3pp):      -0.008  (analogue to pull_flag)

**Backtest results (Version D, April 26):**
Train 2022-2024: A=84.4% → D=86.1% (+1.7pp)
OOS 2025: A=89.4% → D=89.7% (+0.3pp)
42 verdict changes across 4 years (C → D)
OOS guard PASS (≥87.0%)

**Root cause of improvement:** Additive penalties CAN cross tier boundaries (score 0.050 - 0.010 = 0.040 = threshold drop to Neutral). Multiplicative ×0.95 cannot (0.050 × 0.95 = 0.0475 → stays Slight Buy).

All penalty constants in config.py: H_KP_K_PENALTY, H_KP_PULL_PENALTY, H_HH_PENALTY, H_SPEED_PENALTY, H_CHASE_PENALTY, H_MAX_COMBINED_PEN

### Pitch Mix Modifier (Phase 2 — wired April 25, 2026):
- 6-flag stacking system: abandonment, velo_drop, rv_degrade (bearish ×0.90); effectiveness, velo_gain (bullish ×1.10); rv_improve (×1.05)
- Bearish: each flag ×0.90 on buy score (×1.10 on sell score)
- Bullish: effectiveness/velo_gain ×1.10 on buy score; rv_improve ×1.05
- Status: VERDICT-NEUTRAL in backtest (Version E/F/G all 94.0% train / 87.0% OOS)
- Architecture caveat: 10% multipliers insufficient to cross tier boundaries (~0.085 unit gap)
  Three stacked bearish flags = ×0.729 total dampening — only moves borderline scores
- 234 pitchers covered in 2026 production run
- Data: data/pitcher_pitch_mix_delta.json (251 pitchers, Phase 2)

### Buy Qualification Gates (ALL must pass for a buy signal):
- FIP <= 4.50
- SwStr% >= 8%
- Career IP >= 100
- IP >= 20 (waived if raw_buy_score >= 1.50 — Boyle exception)
- ERA >= 3.50 (all buys)
- ERA >= 3.75 (Buy Low only — implemented April 25, 2026)
- ERA >= 4.00 (Slight Buy only)
- |FIP-xERA| <= 1.50 OR xERA <= 4.50
- FIP >= 1.50 if IP < 20

---

## MEASUREMENT FRAMEWORK — TWO RULERS, BOTH VALID

The backtest and production pipeline operate on **different score scales**. This is permanent
and by design — not a bug to fix. Each ruler is correctly calibrated to its own distribution.

### Ruler 1: Backtest (backtest_multi_year_v7.py)
- Formula: `luck_score = xwoba_gap * 0.60 + babip_luck * 0.40` (April-only, ~100-150 PA)
- Score range: peaks at 0.080-0.120
- Thresholds: H_BT_BUY_LOW=0.040, H_BT_SLIGHT_BUY=0.020, H_BT_SELL_HIGH=-0.065, H_BT_SLIGHT_SELL=-0.040
- **Use for**: signal direction validation, A vs B modifier comparisons

### Ruler 2: Production (score_luck.py, score_pitcher_luck.py)
- Formula: 4-component weighted sum + 10+ modifiers, full-season PA window
- Score range: regularly exceeds ±0.150
- Thresholds: H_PROD_BUY_LOW=0.150, H_PROD_SLIGHT_BUY=0.100, H_PROD_SELL_HIGH=-0.150, H_PROD_SLIGHT_SELL=-0.085
- **Use for**: live fantasy decisions, Substack publishing
- All thresholds centralized in config.py — single source of truth

These rulers are NOT interchangeable. Applying production thresholds to backtest scores yields
~23 evaluable cases (vs 305 with calibrated thresholds) and misleading accuracy numbers.

---

## VALIDATED ACCURACY NUMBERS (DO NOT PUBLISH DIFFERENT NUMBERS)

### Hitter Model (backtest v7, Ruler 1 thresholds):

**Version A — baseline (no modifiers):**
| Signal | Train 2022-24 n | Train acc | OOS 2025 n | OOS acc | 4yr pooled |
|--------|-----------------|-----------|------------|---------|------------|
| Buy Low | 57 | 91.2% | 32 | 96.9% | ~92.8% |
| Slight Buy | 62 | 69.4% | 22 | 86.4% | ~75.4% |
| Slight Sell | 56 | 89.3% | 26 | 76.9% | ~84.1% |
| Sell High | 36 | 91.7% | 14 | 100.0% | ~94.8% |
| **Overall** | **211** | **84.4%** | **94** | **89.4%** | **86.1%** |
| vs RTM | — | — | — | — | +17.9pp |

**Version D — additive modifiers (PRODUCTION as of April 26, 2026):**
| Signal | Train 2022-24 n | Train acc | OOS 2025 n | OOS acc |
|--------|-----------------|-----------|------------|---------|
| Buy Low | 55 | 91.3% | 25 | 96.0% |
| Slight Buy | 56 | 73.5% | 22 | 90.9% |
| Slight Sell | 56 | 89.3% | 26 | 76.9% |
| Sell High | 36 | 91.7% | 14 | 100.0% |
| **Overall** | **187** | **86.1%** | **87** | **89.7%** |

Version D notes: n_eval lower than A (187 vs 211 train) because additive penalties cross tier boundaries — borderline buys correctly downgraded to Neutral are excluded from eval. OOS guard PASS (89.7% ≥ 87.0%).

Version B (multiplicative K%/pull): Train Δ=−0.1pp | OOS Δ=−0.1pp | VERDICT-NEUTRAL
Version C (B + HH rate): Train Δ=0.0pp | OOS Δ=0.0pp | VERDICT-NEUTRAL

### Pitcher Model v2.0 (backtest v7, 2024 single-year):
| Signal | n | acc |
|--------|---|-----|
| Buy Low | 33 | 90.9% |
| Slight Buy | 10 | 60.0% |
| Slight Sell | 21 | 76.2% |
| Sell High | 20 | 100.0% |
| **Overall** | **84** | **85.7%** |
| vs RTM | — | +17.5pp |

### Numbers that are INVALID — do not publish:
- "~89.0% train / ~93.5% OOS": production thresholds applied to backtest scores → 23 cases → 100% (overfitted noise)
- "v7 Backtest: 85.9% pooled": superseded by train/OOS split table above

---

## PERMANENT INVARIANTS — RUN AFTER EVERY score_value.py --write

```bash
python score_value.py --check-invariants
```

MUST ALWAYS PASS:
- Yordan Alvarez: top 20 overall
- Cal Raleigh: top 3 catchers (relaxed to top 4 until catcher PA > 150 — early xwOBA variance)
- Drake Baldwin: top 5 catchers
- William Contreras: top 8 catchers

THE SANCHEZ TEST (most important):
- Gary Sanchez: rank 21+ catchers
- IF Sanchez appears in top 15 → STOP. Something is broken.
- The AVG liability penalty (.188 proj AVG) is load-bearing. Ablation C confirmed.

---

## KEY FILES — WHAT EACH DOES

### Production scorers (Layer 1 — handle with care):
- score_luck.py — hitter luck scoring
- score_pitcher_luck.py — pitcher luck scoring (v2.0 split architecture)

### Pipeline:
- run_pipeline.py — full pipeline (fetch → process → score → project → value)
- validate_formulas.py — 37-test formula suite, run after any change

### Data outputs:
- luck_scores.csv — 414 hitters with signals
- pitcher_luck_scores.csv — 380 pitchers with signals
- data/projections_2026.csv — 794 players, rest-of-season projections
- data/player_values.json — 773 players, trade values + rankings
- data/player_ownership_2026.csv — 3,795 players, live ESPN ownership

### Career baselines:
- data/career_quality.json — CQS floors (11 records corrected April 24)
- data/pitcher_career_babip.json — pitcher career BABIP/HH%/barrel
- data/pitcher_career_csw.json — CSW baselines (611 pitchers)
- data/pitcher_career_pitch_mix.json — 2025 arsenal baseline (318 pitchers)
- data/hitter_career_discipline.json — chase rate baselines (672 batters)
- data/hitter_career_k_pull.json — K% and pull rate baselines (643 career, 415 current, 327 with deltas)
- build_hitter_career_k_pull.py — builds K%/pull baselines from v4_april_{year} CSVs
- data/hitter_career_platoon.json — platoon career baselines (489 batters) — built April 26
  Fields: career_gap_woba, career_gap_xwoba, stand, career_pa_same/opp per pitcher hand
  Source: pitcher_statcast_april_{2022-2025}.parquet + pitcher_statcast_mayjuly_2024.parquet
  Mean career gap: -0.019 (wOBA same-hand minus opp-hand)
- build_hitter_career_platoon.py — builds career platoon baselines from pitcher Statcast parquets

### Pitch mix evolution (Phase 2 — built April 25, 2026):
- data/pitcher_arsenal_rv_allyears.csv — 15,947 rows, run_value_per_100 per pitch type, 2022-2026
- data/pitcher_career_velo_per_pitch.json — career avg velo per pitch type (800 pitchers, 2,043 entries)
- data/pitcher_career_arsenal_rv.json — career avg rv/100 per pitch type (1,252 pitchers, 4,752 entries)
- data/pitcher_arsenal_rv_2026.json — current 2026 rv/100 per pitch type (514 pitchers)
- data/pitcher_pitch_mix_delta.json — Phase 2 pitch mix delta signals (251 pitchers)
- build_pitcher_phase2_baselines.py — builds career velo + RV + 2026 current RV baselines
- build_pitch_mix_delta.py — computes Phase 2 flags from baselines
- backtest_pitcher_pitch_mix.py — Version E/F/G pitcher backtest

### score_value.py — barrel rate regression (added April 25):
- PA-weighted blend toward league mean: LG_BARREL=0.066, BARREL_PA_STAB=200
- Weight = PA / (PA + 200); at 95 PA weight ≈ 0.32 (small samples regress heavily)
- Fixed indentation error from prior session (code was at module level, not inside function)

### Worry Index / Confidence Meter (April 27, 2026 — display-only):
Two output columns in luck_scores.csv: worry_flag, breakout_flag, worry_label.
- CONCERN (worry_flag=True): fp_rank < 50 AND wOBA > 40pts below xwoba_3yr AND no signal (|luck| < 0.085)
  Label: "No luck signal detected — struggle may be real, not random"
- BREAKOUT (breakout_flag=True): fp_rank > 100 AND wOBA > 40pts above xwoba_3yr AND no signal
  Label: "No regression signal detected — breakout may be real"
Thresholds in score_luck.py: WORRY_LUCK_BAND=0.085, WORRY_WOBA_GAP=0.040
Current 2026 concern flags (5): Pete Alonso (fp5→17), Bo Bichette (fp14), Juan Soto (fp5), Rafael Devers (fp16), Willy Adames (fp25)
Current breakout flags: 0 (no surprise performers with 40+ pt wOBA lead + no regression signal)
Note: Pete Crow-Armstrong has luck=-0.133 (Slight Sell signal) — excluded because HE HAS an active signal. Also fp_rank=NaN.
Do NOT wire as model modifier — display-only until backtest evidence establishes predictive value.

### Calls tracker (April 26, 2026):
- data/calls_tracker.csv — 169 players tracked (127 hitters, 42 pitchers), Week 1 baseline April 22
  Columns: player_id, name, type, call, call_date, week1_luck, week1_woba, week1_xwoba,
           woba_delta, xwoba_delta, mechanism, prediction_correct, last_updated, notes
  For pitchers: week1_woba=ERA, week1_xwoba=FIP (sign-flipped so +delta = prediction moving correct)
- weekly_update.py — tracker / article generator:
  --init: bootstrap week1 from current luck_scores.csv + pitcher_luck_scores.csv
  --update: add weekN_* columns from current CSVs, recompute deltas/mechanism/prediction_correct
  --report [--top N]: markdown table (Substack-ready) with trend arrows and story sentences
  Mechanism: results_improving | results_declining | contact_improving | contact_deteriorating | insufficient_movement
  Accuracy: confirmed + refuted only in denominator (watch/re-evaluate excluded until resolved)
  Significance thresholds: wOBA_THRESH=0.020, XWOBA_THRESH=0.015

### Weekly article workflow (every Monday — article day):
```bash
# 1. Refresh all stats with new Statcast data
python run_pipeline.py --write

# 2. Snapshot current week into tracker + recompute deltas
python weekly_update.py --update

# 3. Generate article table (top 15 per category, sorted confirmed → re-eval → too early)
python weekly_update.py --report --top 15

# 4. Paste output into Substack article draft
```
NOTE: --update must be run AFTER run_pipeline.py --write so luck_scores.csv is fresh.
Week 1 baseline = April 22 (call_date in tracker). Week numbers increment each --update call.
If signals change significantly mid-season (new model run): re-run --init to reset baseline.

### Audit/backtest:
- data/backtest_audit_hitters.csv — 305 row-level hitter backtest (v7 logic)
- data/backtest_audit_pitchers.csv — 284 row-level pitcher backtest (v7 logic)
- data/backtest_large_miss_analysis.txt — large miss categorization + proposed fixes

---

## WHAT NOT TO TOUCH

1. **Layer 1 scoring logic** without explicit instruction + full validation
2. **validate_formulas.py tests** — never modify tests to make them pass
3. **Ablation scripts** — these are diagnostic, not production
4. **Backtest cache** — historical Statcast data, do not regenerate unless asked
5. **career_quality.json** — manually corrected records, treat as ground truth
6. **The Sanchez Test** — if anything causes Sanchez to rank top 15 catchers, stop

---

## AFTER EVERY CHANGE

1. Run: `python -X utf8 validate_formulas.py` → must be 37/37 PASS
2. Run: `python score_value.py --write` → check invariants pass
3. Confirm Sanchez Test passes
4. Report what changed, what was tested, what passed

---

## PIPELINE RUN ORDER

```bash
python run_pipeline.py --write
```

Manual order if needed:
1. fetch_ownership.py
2. fetch_stats.py + fetch_pitcher_stats.py
3. process_stats.py + process_pitcher_stats.py
4. score_luck.py + score_pitcher_luck.py
5. build_pitcher_pitch_mix.py
6. generate_projections.py
7. score_value.py --write
8. export_signal_board.py
9. validate_formulas.py
```

---

## DASHBOARD

File: dashboard.html
Run: launch_dashboard.bat (or python -m http.server 8000)
Access: localhost:8000/dashboard.html

All 7 audit fixes complete as of April 24, 2026:
- Simple/Advanced toggle ✅
- Signal filter pills ✅
- Park change badges (43 players) ✅
- Simple View 3-column redesign ✅
- Pitcher ownership merged (374/380) ✅
- IL warning banner ✅
- Trade search end-to-end verified ✅

---

## CURRENT SIGNALS SUMMARY (April 26, 2026 — post Version D)

Hitters (414 total, production run):
Buy Low: 55 | Slight Buy: 12 | Neutral: 293 | Slight Sell: 27 | Sell High: 27
(Total tracked in calls_tracker.csv: 127 hitters + 42 pitchers = 169)

Pitchers (380 total, unchanged):
Buy Low: 7 | Slight Buy: 8 | Neutral: 325 | Slight Sell: 15 | Sell High: 25

Top pitcher buy lows: Luzardo (0.4531), Ryan (0.3487), Boyle (0.3351),
C.Sanchez (0.3095), Gilbert (0.2791), Bradish (0.2405), Baz (0.2047)

Relievers dormant until 15 IP threshold: Morejón (ERA 8.03, FIP 2.47),
Doval (ERA 8.59, FIP 4.81), T.Rogers (ERA 5.62, FIP 2.79)
NOTE: Verify xERA before calling any reliever a buy low in articles.

---

## IMPORTANT DATA NOTES

- Both Max Muncys correctly disambiguated:
  Dodgers Muncy: ID 571970 (age 36) — slight sell
  A's Muncy: ID 691777 (age 24) — stronger sell
- Murakami: CWS (not ARI) — confirmed in pipeline
- Vásquez: spelled with accent (Randy Vásquez) in CSV
- Yordan Week 1 tracker: wOBA .518, xwOBA .603, luck 0.288, Buy low
- Raleigh rank 4 (April 25) — floor-propped at CQS=80.2; xwOBA .336 + AVG liability (.186) crushes natural ESV to ~4.7. Ben Rice's .507 xwOBA (95 PA) pushing him to #1. Invariant relaxed to top-4 until PA stabilize >150 (mid-May 2026).

---

## ARCHITECTURAL DECISIONS

### Training Window (2022+)
Training window starts 2022 due to two rule changes that structurally altered run environment:
- **Deadened ball standardization** (2021-2022): MLB centralized ball production mid-2021 through 2022;
  pre-2022 HR/FB rates and BABIP norms are not comparably predictive
- **Universal DH adoption** (2022): Pitchers no longer bat; lineup construction changed

**Policy**: Pre-2022 seasons excluded from signal training data.
Pre-2022 career baselines ARE retained for individual player context — used as relative reference for
that specific player only, not cross-player comparisons. A player's 2019 chase rate matters for
understanding their personal baseline; the 2019 league average does not transfer to 2022+.

### Backtest Formula vs Production (Two Rulers)
See "MEASUREMENT FRAMEWORK — TWO RULERS, BOTH VALID" section above.

### Two-Track In-Season Signal System

**Track 1 — April Signals (validated, PRODUCTION)**
- April data only; validated at 86.1% train / 89.7% OOS (Version D, hitters)
- These are the published Substack signals. Never downgrade the authority framing on these.
- Production cadence: run_pipeline.py --write every Monday morning before article

**Track 2 — In-Season Rolling Signals (HYPOTHESIS, NOT VALIDATED)**
- Rolling wOBA/xwOBA from current-season data (beyond April); weekly_update.py --update
- Presented as tracker/observation only — NOT model-validated signals
- Article framing: "The data is moving in the right direction" — never "new signal"
- Do NOT publish running accuracy numbers for Track 2 until it has its own backtest

**Why this distinction exists:** April is the highest-signal window (max market mispricing,
full-season PA ahead to validate). In-season rolling data suffers from survivorship bias,
regression to mean already in progress, and no validated accuracy framework. Mixing the two
without clear labeling would corrupt the published track record.

**Publishing cadence:**
- Tuesday night: publish Substack article using Monday's data run
- Monday morning: run_pipeline.py --write → weekly_update.py --update → --report --top 15
- Every 4 weeks: re-evaluate if any Track 2 rolling movers warrant a fresh April-style signal call

---

## PARKING LOT

### TIER 1 — Do immediately after Week 2 publishes

- **Weekly tracker mechanism classifier** — HIGHEST PRIORITY build after Week 2. This is the core
  accountability engine and the content foundation for the entire May-August publishing schedule.
  Implement wOBA vs xwOBA decomposition in weekly_update.py to distinguish "results declining as
  predicted" vs "contact quality improving" — same luck score movement, opposite meanings.
  Add mechanism column with values: Normalizing | Re-evaluate | Confirmed | Refuted | Watch.
  Without this, the tracker is showing movement but not explaining it. With it, every weekly
  article has a built-in narrative engine ("these 3 calls are normalizing, these 2 need re-eval").

- **April Big Board** — Consolidated view of all April calls, current status, and what the model
  expects going forward. Publish as Week 3 content. Format: table with player, call date, signal,
  current wOBA vs xwOBA, mechanism, status. This is the track record proof-of-work document.

### TIER 2 — This week

- **Pitcher Slight Buy sensitivity analysis** — n=4 historically is too thin to validate.
  Ablation test ERA floor (4.00→3.75?), luck score window width, IP minimum threshold independently.
  Goal: generate enough historical signals to validate the tier statistically.
  Method: ablation test each gate individually, measure signal count AND accuracy.

- **is_article_worthy() gate** — build after Week 2 publishes. Filter signals worth featuring
  in articles from borderline cases. Prevents weak signals from cluttering the article table.

### RESEARCH AGENDA (post-2026 season)

- **Worry Index sensitivity analysis** — validate WORRY_WOBA_GAP=0.040 and WORRY_LUCK_BAND=0.085
  thresholds empirically after full season. Current thresholds are estimated priors. Need 50+
  flagged cases with resolved outcomes before calibrating. Built as display-only in score_luck.py;
  concern flags: Devers, Bichette, Adames, Alonso, Soto (April 2026).

- **Financial motivation backtest** — PRELIMINARY RUN COMPLETE (April 29, 2026).
  Spotrac MLB_Contracts_3.xlsx: 1,000 rows, 609 unique players, 2015-2039 range.
  Hitter contracts: 506 rows, 308 unique players. Saved: data/spotrac_contracts_clean.csv.
  Joined to backtest_audit_hitters.csv (2022-2024, n=211): 112 matched (53%), 99 unmatched.
  Unmatched = pre-arb/arb players (no Spotrac FA deal entry). All 3 sanity checks pass:
    Mookie Betts 2022 → contract_year=False (end=2032) ✓
    Aaron Judge 2022 → contract_year=True (end=2022) ✓
    Corey Seager 2022 → contract_year=False (end=2031) ✓
  Saved: data/spotrac_contract_backtest.csv (211 rows, with cohort assignments).

  PRELIMINARY RESULTS — all n<10 per cohort/signal, too thin for conclusions:
  Cohort 3 (Secured): 96.4% overall, 100% Buy Low (n=9) — highest, but borderline reliable.
  No evidence of financial motivation effect: CY Buy Low 85.7% (n=7) vs non-CY 92.3% (n=26).
  Must reach 50+ players per cohort before publishing conclusions.
  Full backtest still requires 100+ players × 3 seasons for reliable signal.

- **Elite player ascending theory** — test whether age 27-31 players in final year of a strong deal
  ($200M+) outperform or underperform luck signals. The financial motivation question is unresolved:
  does the generational payday window produce measurable performance lift, or is it captured by age?
  Requires Cohort 1 (payday) players with resolved signals — earliest viable mid-2027.

- **In-season signal validation (Track 2)** — Track 2 framework documented; 2026 is the first data
  collection year. Validate rolling wOBA/xwOBA window approach for 2027 publishing. Must have
  own backtest before publishing Track 2 numbers with authority. Do NOT combine with Track 1 accuracy.

- **Age-weighted chase rate sensitivity** — H_CHASE_AGE_WEIGHT_U25=0.40 and
  H_CHASE_AGE_WEIGHT_26_27=0.70 are estimated priors, not empirically calibrated. Currently
  zero verdict impact (no young buy signal near a boundary). Proper calibration requires 2+ full
  seasons of age-stratified chase-rate data and a per-age-bucket train/OOS backtest.
  Build once 30+ age-stratified call resolutions exist (mid-2027 earliest).
  Constants in config.py: H_CHASE_AGE_WEIGHT_U25, H_CHASE_AGE_WEIGHT_26_27.

- **Contract Year Historical Experiment** — PRELIMINARY RUN COMPLETE (April 29 2026). See
  Financial motivation backtest entry above. Full validation requires 50+ per cohort/signal.
  Source: MLB_Contracts_3.xlsx (user-provided Spotrac export, 1,000 rows).
  Next step: Expand contract match rate beyond 53% by adding arb-year salary data.

### TRADE TOOL FOUNDATION

**CBS FPTS Model — BUILT (April 2026):**
- build_cbs_fpts.py scrapes CBS full-season stats (2024+2025); Ridge regression (α=0.1).
- Train R²=0.983 hitters / 0.927 pitchers. OOS R²=0.983 / 0.909. Both pass ≥0.85 guard.
- Constants in config.py: CBS_H_COEF_*, CBS_P_COEF_*, CBS_H/P_INTERCEPT, CBS_H/P_R2_*.
- Wired into trade_analyzer.py: _compute_cbs_fpts() + replacement_level.py surplus calc.
- Data files: data/cbs_{hitter,pitcher}_fpts_{2024,2025}.csv, data/cbs_regression_results.txt

**CRITICAL — CBS coefficient interpretation:**
Individual CBS coefficients are NOT interpretable as "CBS points per stat" due to multicollinearity
(R/HR/RBI correlated; ERA/WHIP correlated). Use full-vector prediction ONLY. The combined model
is accurate (R²=0.983 OOS); individual coefs reflect marginal contribution after collinearity.
Do NOT use HR coef (0.430) to manually estimate HR value — the model uses all five stats together.

**Replacement Level — BUILT (April 2026):**
- replacement_level.py: N = roster_spots × 12 teams per position (default 12-team standard).
- surplus_value = projected CBS FPTS − replacement FPTS at position.
- Surplus displayed in trade_analyzer.py player card and verdict section.
- `python trade_analyzer.py --replacement-table` shows full position table.
- 12-team standard replacement levels (April 2026):
  C: 289.8 (William Contreras, N=12) | 1B: 275.7 (Josh Bell, N=24)
  2B: 277.7 (Marcus Semien, N=18) | 3B: 267.0 (Ramón Urías, N=24)
  SS: 293.9 (Bo Bichette, N=18) | OF: 296.3 (Jake Mangum, N=36)
  SP: 221.5 (Randy Vásquez, N=60) | RP: 157.0 (Raisel Iglesias, N=36)
- Skenes/Rice surplus result: Rice surplus +44 (C pool) > Skenes surplus +33 (SP pool).
  Verdict does NOT flip — Rice has more surplus, but luck model correctly shows higher regression
  risk (luck delta -0.266 AVOID). The tension is intentional and informative.
- Note: Ben Rice CBS position = C (retains C eligibility). Surplus vs C repl = +44.
  If treating as 1B: surplus = +58. Either way Rice surplus > Skenes surplus (+33).

**Projection Accuracy Backtest — BUILT (April 2026):**
- Script: projection_backtest_2025.py | Outputs: data/projection_accuracy_2025.csv, data/projection_accuracy_summary_2025.csv
- Method: April 2025 Statcast events → player rates → stat_projections.py → projected full-season → vs CBS 2025 actuals (n=141)
- Career baselines: 2022-2024 FG data only (no 2025 leakage)
- HR MAE overall: 6.70 | Bias: -3.78 (systematic under-projection — April window misses late-season breakouts)
- **Thin baseline fix VALIDATED:** career_pa < 1000 shows 54% less HR bias (-2.05 vs -4.44) and lower MAE (5.18 vs 7.28) vs established players
- Sell High R²=0.656 — strongest signal group; sell signals correctly identify players who won't accumulate counting stats
- AVG R²=0.056 — unpredictable from April data (industry-wide known limitation; not a model bug)
- RBI bias -9.65 — lineup context not captured; expected from simplified formula
- Late-season breakouts are irreducible misses (Caminero proj 20 actual 45; Goodman proj 15 actual 31)
- Ben Rice: proj 26 HR, actual 26 HR — thin baseline fix working exactly as intended

- **CBS Rankings Reverse Engineering** — Reverse engineer CBS end-of-season overall rankings using
  linear regression against final player stats for 2022-2024.
  X = [HR, R, RBI, SB, AVG, ERA, WHIP, K, W, SV], y = CBS overall rank (inverted).
  Target R² >= 0.90. Compare coefficients across years for stability.
  Output: CBS implicit weights (baseline) + Signal Fantasy optimized weights (differentiator).
  Check CBS archive / Wayback Machine for historical rankings.

- **CBS coefficient ratios as trade value exchange rates** — Same coefficients power both rankings
  engine AND trade analyzer. One source of truth: if HR is worth 3× SB in CBS rankings, that same
  ratio determines whether a trade is fair. Exposes CBS coefficients in config.py; import into
  score_value.py + trade_analyzer.py. Prerequisite: CBS regression above must reach R² >= 0.90.

- **Replacement level calculator** — BUILT April 2026 (replacement_level.py). See above.

- **Fantasy points conversion engine** — Multiply projected stats × CBS-derived point values
  per category. Enables apples-to-apples comparison across positions and categories.

- **League settings intake UI** — Roster construction, scoring format, categories. One-time setup
  that parameterizes all value calculations. Prerequisite for multi-league product.

- **Positional scarcity cap** — 15-spot rule: never let scarcity flip a tier. Prevents the catcher
  scarcity premium from making a replacement-level catcher appear equal to a top outfielder.

- **ERA_all_sc option for pitcher luck scores** — DIAGNOSED, NOT IMPLEMENTED (April 29, 2026).
  Full simulation run: era_simulation.py tested ERA_all_sc vs filtered ERA across 389 pitchers.
  Result: 7 verdict changes (1.8%). 3 were artifacts; 4 real:
    Skenes: Sell High → Slight Sell (ERA-FIP gap -1.58 → -0.05, final luck -0.151 → -0.074)
    Crochet, Suarez: Neutral → Buy Low (FALSE SIGNALS — driven by excluded disaster starts)
    López: Neutral → Slight Buy (borderline, FIP 4.45 near gate)
  Decision: KEEP filtered ERA (qualifying starts only, MIN_START_IP=2.0).
  Reasoning: switching to ERA_all_sc creates phantom buy signals from blowup outings that the
  filter correctly ignores. Skenes is the only legitimate case, and his sell is BABIP/LOB-dominant
  anyway (-0.60 BABIP, -0.77 LOB components), not ERA-driven.
  Revisit after full season if filtering creates systematic bias for pitchers with early blowups.

- **Projection stress test / consensus blend** — NOT YET BUILT (as of April 2026).
  Only CBS actuals scraped (build_cbs_fpts.py). ESPN and FantasyPros projections not attempted.
  When ready: scrape ESPN projections page + FantasyPros consensus, build α=0.60/0.40 blend,
  save to data/projection_consensus_2026.csv. Known divergences to check once built:
  Rice HR 21 (ours) vs 28 (CBS) — fixed post thin-baseline patch; recheck after building consensus.
  Skenes W 7 (ours) vs 11 (CBS), K 114 vs 153 — conservative IP projection from velo/SwStr flags.
  Prerequisite: build_cbs_fpts.py already scrapes CBS actuals; extend to CBS ROS projection pages.

### CONTENT PIPELINE

- **White paper** — signal_fantasy_whitepaper.docx, 11 sections drafted (April 2026).
  Sections 1-8 final. Section 10 (live track record table) needs 2-3 more weeks of data.
  Publish to whitepapersonline.com after Section 10 update + GitHub push.
  Establishes methodology timestamp and IP protection alongside repo commit history.

- **"Why April Signals Matter Most" article** — Explainer on why April is the highest-value window
  for luck detection. Model detects mispricing in April, validates against May-August core fantasy
  season. Market is maximally mispriced in April. Publish mid-May as paid tier content.

- **"How I Built This in 10 Days with AI" article** — Publish after 6-8 weeks of live track record.
  Full outline already documented in thread_handoff.md. This is the commercialization anchor story.

- **Live 2026 Accuracy Tracker** — Running tracker showing current season call performance in real
  time as May-August results come in. Updates weekly alongside article. Strong paid tier feature.
  Build once 30+ calls have resolved (mid-June 2026 earliest).

- **Spotrac Phase 2: historical 2022-2024 contract data** — Run build_spotrac_contracts.py with
  historical season parameters for each prior year. Populates financial motivation cohort data for
  backtest. Target: 100+ players × 3 seasons. Prerequisite for financial motivation backtest above.

- **Historical contract data — Baseball Reference approach (easier than Spotrac):**
  baseball-reference.com/friv/free_agents.fcgi?year=2022 (repeat for 2023, 2024).
  FA class tables are copy-paste friendly into Excel. INDEX/MATCH join against backtest signal
  players → export to CSV and import into contract_year_2026.csv schema.
  Estimated time: ~45 minutes. Populates cohort backtest for financial motivation research.
  This is the fastest viable path to 100+ historical contract records.

### BUILT — Display-only, not yet validated as model modifiers

- **Worry Index / Confidence Meter** — BUILT April 27. worry_flag, breakout_flag, worry_label
  columns in luck_scores.csv. CONCERN: fp_rank<50 + wOBA 40+pts below 3yr xwOBA + no signal.
  BREAKOUT: fp_rank>100 + wOBA 40+pts above 3yr xwOBA + no signal.
  Do NOT wire as model modifier until backtest validates thresholds (see Research Agenda above).

- **Financial Motivation Cohort Framework** — BUILT April 26-28. _assign_cohort() in score_luck.py.
  31 players loaded (13 manual + 18 Spotrac merge). Display-only, contract_cohort column in output.
  Do NOT add model weight until cohort × signal backtest complete (see Research Agenda above).

- **Pull Rate Increase as Bullish Signal** — Flip side of pull_flag: hitters whose pull rate has
  INCREASED 5pp+ may be making mechanical adjustments toward a power-friendly approach.
  Consider as optional bullish buy modifier (×1.05?). Needs backtest before wiring.

### IP Protection
- **Private GitHub repo:** DustinSLovell/Signal-Fantasy-Pipeline (created April 26, 2026)
  All code committed with timestamps for IP protection. Push after every session:
  ```
  cd C:\Users\dusti\fantasy-baseball
  git add .
  git commit -m "Session update - [date]"
  git push
  ```
  First commit timestamped April 26, 2026 — establishes prior art for all scoring logic,
  backtest methodology, and CBS FPTS regression coefficients.

- **White paper:** signal_fantasy_whitepaper.docx — 11 sections drafted (April 2026).
  Sections 1-8 final. Section 10 (live track record) needs 2-3 weeks of tracker movement.
  Publish to whitepapersonline.com after GitHub push. Serves as timestamped methodology proof.
  Add copyright notice to every new Substack article: "© 2026 Dustin Lovell / Signal Fantasy."

- **Copyright on articles** — Add to every Substack post footer before publishing.

### Operations
- **Check console.anthropic.com monthly** for Claude Code API token consumption tracking.
  Commercial project — cost monitoring is important hygiene for budget management.
- **Career lessons database** (career_lessons_database.html) is maintained in the Claude.ai web interface — NOT updated by Claude Code. Add new lessons manually at end of each session.
  Session 7 (April 26-28) lessons COMPLETED: Worry Index / model silence as signal | Temporal validity | Content flywheel architecture | Financial motivation score vs binary CY flag | Two-path luck normalization.
  File: outputs/career_lessons_database.html

---

## SESSION END CHECKLIST

Before closing any Claude Code session:
1. Confirm validate_formulas.py still 37/37 PASS
2. Note any files modified
3. Note any parking lot items resolved or added
4. Push to GitHub (IP protection — run every session without exception):
   ```
   cd C:\Users\dusti\fantasy-baseball
   git add .
   git commit -m "Session update - [date]"
   git push
   ```
5. Tell Dustin to update thread_handoff.md in Claude.ai before closing

ERA floor fix: April 25 — score_pitcher_luck.py line ~967
Slight Buy thresholds: April 25 — score_luck.py (floor 0.065→0.100, gap 0.015→0.030, ceiling 0.380)
Barrel regression fix: April 25 — score_value.py (LG_BARREL=0.066, BARREL_PA_STAB=200, indentation corrected)
Cal Raleigh invariant: April 25 — relaxed to top-4 until catcher PA > 150 (mid-May 2026)
Pitch mix Phase 1: April 25 — build_pitch_mix_delta.py + score_pitcher_luck.py wired; backtest verdict-neutral
Pitch mix Phase 2: April 25 — build_pitcher_phase2_baselines.py + per-pitch velo/RV baselines; Version G backtest 94.0%/87.0% OOS PASS
K%/pull modifier: April 25 — score_luck.py wired; build_hitter_career_k_pull.py; 37/37 PASS
K%/pull backtest: April 25 — backtest_multi_year_v7.py Version B; train Δ=-0.1pp, OOS Δ=-0.1pp; VERDICT-NEUTRAL
Threshold centralization: April 25 — config.py created; all three files import from config; two-ruler framework documented
Hard hit rate modifier: April 25 — score_luck.py; backtest Version C verdict-neutral
Sprint speed modifier: April 25 — build_hitter_sprint_speed.py; data/hitter_sprint_speed.json (911 players)
Chase rise buy dampener: April 25 — score_luck.py (curr > career +3pp, PA>=50)
Contract year flag: April 25 — data/contract_year_2026.csv + pitcher_contract_year_2026.csv; display only

--- April 26, 2026 ---
Additive modifier architecture (Version D): April 26 — ALL hitter buy dampeners converted from multiplicative to additive
  - score_luck.py now uses _buy_penalty accumulator; combined application with cap
  - config.py: H_KP_K_PENALTY=0.010, H_KP_PULL_PENALTY=0.008, H_HH_PENALTY=0.012, H_SPEED_PENALTY=0.010, H_CHASE_PENALTY=0.008, H_MAX_COMBINED_PEN=0.040
  - Calibrated via sensitivity sweep: k=0.010, pull=0.008, hh=0.012 (each maximized training accuracy independently)
  - Version D backtest: train A=84.4%→D=86.1% (+1.7pp) | OOS A=89.4%→D=89.7% (+0.3pp) | 42 verdict changes | OOS guard PASS
  - ADOPTION DECISION: ADOPTED (equal/better accuracy + real verdict changes)
  - backtest_multi_year_v7.py: added _apply_additive_modifiers(), _print_sensitivity_sweep(), _print_abcd_comparison(), player_recs in run_year_h
  - 37/37 PASS
Platoon fix (April 26): career baseline added, PA min raised 15→30, xwOBA splits added
  - build_hitter_career_platoon.py: new file; builds from pitcher_statcast_april_{2022-2025}.parquet + mayjuly_2024.parquet
  - data/hitter_career_platoon.json: 489 batters, mean gap=-0.019
  - score_luck.py: _build_platoon_splits() now loads xwOBA; _platoon_modifier() now takes career_platoon dict; compares curr gap to career gap instead of static expected gap; fallback=−0.019 when no career data
  - score_luck.py: CAREER_PLATOON_PATH added; platoon section loads career_platoon dict
  - 37/37 PASS
Contract year cohort framework (April 26): display-only 5-cohort classification
  - score_luck.py: _assign_cohort() function added; contract_cohort column in output
  - Cohorts: 1=FA-bound | 2=pre-arb | 3=prove-it | 4=final | 5=locked-up
  - No model weight; requires manual CSV data population before being useful
  - Spotrac scraping attempt: no programmatic source found (pybaseball=no, FG=no, Spotrac=ToS blocked)
  - 37/37 PASS
Financial motivation cohort redesign (April 26): _assign_cohort() rebuilt around contract economics
  - New priority logic: manual override → prove_it flag → secured ($20M+ AAV, 3+yr) → post-prime (age 33+) → payday (age 25-31, ≤2yr or pre-arb) → mid-contract
  - data/contract_year_2026.csv: new schema (batter_id, name, annual_salary_m, years_remaining, prove_it, cohort_override, notes)
  - Pre-populated: 9 Cohort 3 players (Ohtani, Judge, Trout, Harper, Seager, Lindor, Turner, Machado, Riley) + 2 Cohort 1 (Acuña, Yordan)
  - Wayback Machine CDX API (web.archive.org): PROCEED — contracts readable for test players
  - build_spotrac_contracts.py: CDX discovery + page parser; 60s timeout; team-specific URL (no wildcards); recent-first date range
  - 37/37 PASS
Calls tracker (April 26): weekly article accuracy infrastructure
  - data/calls_tracker.csv: 169 players (127H, 42P), Week 1 baseline April 22, 2026
  - weekly_update.py: --init / --update / --report pipeline
  - Sign convention: woba_delta positive always = prediction moving toward correct (sign-flipped for pitchers)
  - Mechanism + accuracy tracking matches backtest discipline (watch/re-eval excluded from denominator)

--- April 26-27, 2026 (continued) ---
Pitcher Version H (additive modifier backtest): April 26 — VERDICT-NEUTRAL
  - backtest_pitcher_pitch_mix.py: added BEARISH_FLAGS_H, P_MAX_COMBINED_PEN, _overall_acc_df,
    _reclassify_h, sweep_penalties_pitcher, add_signal_h, print_h_comparison
  - run_year: saves abandonment_flag, velo_drop_flag, rv_degrade_flag into merged; keeps xera_g + career_ip_g
  - Result: all penalties calibrate to 0.0; buy sample (n=21 train) too small for additive advantage
  - Decision: KEEP multiplicative architecture for pitchers; additive not adopted
Age-weighted chase rate modifier: April 26 — implemented in score_luck.py
  - score_luck.py: age ≤25 → H_CHASE_PENALTY × 0.40; age 26-27 → H_CHASE_PENALTY × 0.70; age 28+ → full
  - config.py: H_CHASE_AGE_WEIGHT_U25=0.40, H_CHASE_AGE_WEIGHT_26_27=0.70
  - 37/37 PASS; zero verdict impact at current score levels (no young buy near boundary)
  - 8 young buy players affected (Gunnar Henderson, Jackson Merrill, Ezequiel Tovar, Tyler Soderstrom,
    Cam Smith, Jordan Beck, Jacob Wilson, Wyatt Langford — all receive +0.0048 score relief)
  - Parking lot: sensitivity analysis needed before empirical calibration (mid-2027)
Two-track in-season signal framework: documented in CLAUDE.md ARCHITECTURAL DECISIONS
  - Track 1 = April Signals (validated, published); Track 2 = in-season rolling (hypothesis, no backtest)
  - Key rule: never present Track 2 with equal authority to Track 1
Worry Index / Confidence Meter: April 27 — display-only layer in score_luck.py
  - 5 concern flags: Alonso (fp17), Bichette (fp14), Soto (fp5), Devers (fp16), Adames (fp25)
  - 0 breakout flags
  - WORRY_LUCK_BAND=0.085, WORRY_WOBA_GAP=0.040
  - Columns: worry_flag, breakout_flag, worry_label in luck_scores.csv
  - Note: Pete Crow-Armstrong excluded — luck=-0.133 (Slight Sell signal IS present), fp_rank=NaN
  - 37/37 PASS
Cohort framework age-ordering bug fix: April 27 — _assign_cohort() was called before df["age"] was set
  - score_luck.py: moved contract_cohort apply() to after df["age"] = ... (line ~1390)
  - Previous runs: ALL players returned "unknown" (bug present since April 26 introduction)
  - Post-fix distribution: 1-payday=161, 3-secured=11, 4-post-prime=62, 5-mid-contract=164, unknown=18
  - Cohort 3: 11 players (added Bobby Witt Jr. 677951, Julio Rodríguez 677594 to contract_year_2026.csv)
  - Note: Yordan correctly Cohort 1 (AAV $19.2M, 1yr remaining — below both Cohort 3 thresholds)
  - 37/37 PASS

--- April 28, 2026 ---
Spotrac contract merge: April 28 — 18 entries added to data/contract_year_2026.csv (31 total players loaded)
  - merge_spotrac_contracts.py: new file; normalizes AAV, filters expired/pre-arb, applies MLBAM ID lookup
  - Second scraper run fixed salary parsing (pre-arb values now correctly 0.72M not 720000.0M)
  - New Cohort 3 additions: Ramírez (20.14M/3yr), Swanson (25.29M/4yr), Bogaerts (25.45M/8yr),
    Stanton (25.0M/3yr), Olson (21.0M/5yr), Nola (24.57M/4yr), Yelich (26.93M/4yr)
  - Post-merge distribution: 1-payday=160 | 3-secured=17 | 4-post-prime=58 | 5-mid-contract=163 | unknown=18
  - 37/37 PASS
run_pipeline.py subprocess encoding fix: April 28 — added encoding="utf-8", errors="replace" to Popen call
  - Was crashing with UnicodeDecodeError on tqdm progress bar output (Windows CP1252 default)
  - Permanent fix; all 6 pipeline steps now complete cleanly
Week 2 article generated: April 28 — full pipeline run + weekly_update.py --update + --report
  - Lead: Corey Seager (wOBA .332, xwOBA .378, gap +.046, score +0.344, Buy Low)
  - Feature: Dillon Dingler (xwOBA .459, gap +.105, score +0.317), José Ramírez (fp7, score +0.483)
  - New section: Worry Index (Devers fp16 wOBA .241/xwOBA .265, Adames fp25, Bichette fp14)
  - Yordan tracker: wOBA .510/xwOBA .595 consistent Week 1→2
  - Pitcher buys: Luzardo (ERA 6.41/FIP 3.14), Joe Ryan (ERA 5.29/FIP 3.12), C.Sánchez (ERA 3.82/FIP 2.51)
  - Tracker shows all calls "too early" at 1 week — expected per significance thresholds
  - Article draft ready for Tuesday April 29 publication; pending manual review/publish

--- April 28-29, 2026 (continued) ---
CBS FPTS scraper: April 28 — build_cbs_fpts.py; scraped CBS 2024+2025; Ridge regression
  - data/cbs_{hitter,pitcher}_fpts_{2024,2025}.csv saved; data/cbs_regression_results.txt
  - Train R²: hitters=0.985, pitchers=0.927 | OOS R²: hitters=0.983, pitchers=0.909
  - Constants added to config.py: CBS_H_COEF_* + CBS_P_COEF_* + intercepts + R² guards
  - 37/37 PASS
CBS FPTS + surplus wired into trade_analyzer.py: April 28-29
  - _compute_cbs_fpts() uses CBS coefficients from config.py
  - Projected FPTS displayed in player card with CBS projected stats line
  - Verdict section shows FPTS delta (give vs get)
  - 37/37 PASS
Projection diagnostic (April 28-29): two stat_projections.py bugs identified and fixed
  - Fix 1 (BABIP-only sell): project_hitter_counting() now accepts xwoba_gap param;
    sell-high HR multiplier suppressed when xwoba_gap > -0.020 (BABIP-driven, not contact-driven)
  - Fix 2 (thin career baseline): career_pa < 1000 → career weight × 0.85; current weight boosted
  - Rice projection after fixes: HR 17→21, AVG .280→.290, FPTS 312→334
  - 37/37 PASS; projections_2026.csv regenerated
Replacement level calculator: April 29 — replacement_level.py
  - FANTASY_POS_MAP: raw MLB pos → fantasy pos (LF/RF/CF→OF, DH→1B, etc.)
  - DEFAULT_ROSTER_N: 12-team standard N per position (C=12, 1B=24, 2B=18, 3B=24, SS=18, OF=36, SP=60, RP=36)
  - surplus_value = projected CBS FPTS − Nth-best at position FPTS
  - Wired into trade_analyzer.py: surplus shown in player card + verdict surplus delta line
  - `python trade_analyzer.py --replacement-table` for position table
  - Result: Rice surplus +44 (C pool) vs Skenes surplus +33 (SP pool) — verdict does not flip
  - 37/37 PASS
GitHub repo: DustinSLovell/Signal-Fantasy-Pipeline (private) — first commit April 26, 2026

--- April 29, 2026 (continued) ---
Projection accuracy backtest: April 29 — projection_backtest_2025.py
  - Aggregates April 2025 Statcast events → per-player rates → stat_projections.py → projected full-season
  - Career baselines: FG 2022-2024 only (no 2025 leakage); 141 players matched to CBS 2025 actuals
  - HR overall: MAE 6.70 | Bias -3.78 (systematic under-projection from April-only window)
  - Thin baseline fix VALIDATED: career_pa<1000 → 54% less HR bias (2.05 vs 4.44), lower MAE (5.18 vs 7.28)
  - Sell High HR R²=0.656 — strongest signal group; validates sell signal direction
  - AVG R²=0.056 — unpredictable from April alone (industry-wide); RBI bias -9.65 (lineup context missing)
  - Ben Rice: proj 26 HR, actual 26 HR — thin baseline fix working exactly as intended
  - Irreducible misses: Caminero (proj 20, actual 45), Goodman (proj 15, actual 31) — late-season breakouts
  - Outputs: data/projection_accuracy_2025.csv (141 rows), data/projection_accuracy_summary_2025.csv
  - 37/37 PASS
Backtest data structure documented: April 29
  - backtest_cache/v4_april_2025.csv = raw event-level Statcast, date range 2025-03-27 to 2025-04-30
  - backtest_cache/april_statcast_2025.parquet = sparse game-context join table (not main data)
  - data/backtest_audit_hitters.csv = model OUTPUT (luck scores/verdicts 2022-2025, n=305)
  - april_statcast_2024.parquet for hitters: MISSING (only pitcher versions exist for 2024)
  - data/projection_consensus_2026.csv: does NOT exist — consensus blend task not yet built

--- April 29, 2026 (Session 9 — continued) ---
ERA_all_sc simulation: era_simulation.py — 389 pitchers, 7 verdict changes (1.8%)
  - 4 real changes: Skenes SH→SS, Crochet/Suarez N→BL (false signals), López N→SB
  - Decision: keep filtered ERA — ERA_all_sc creates phantom buy signals from excluded disasters
  - era_simulation.py saved (diagnostic only, not production code)
  - 37/37 PASS (no production code changed)
Financial motivation backtest: spotrac_contract_backtest.csv (211 rows)
  - Source: MLB_Contracts_3.xlsx (1,000 rows, 609 players, Spotrac export)
  - data/spotrac_contracts_clean.csv: 506 hitter rows, 308 unique players
  - Match rate: 112/211 (53%) — 99 unmatched are pre-arb/arb players
  - Sanity checks PASS (Betts 2022 False, Judge 2022 True, Seager 2022 False)
  - Cohort 3 (Secured) shows 96.4% accuracy (n=28) — preliminary positive signal
  - ALL cohort/signal combinations n<10 except Cohort 5 — no publishable conclusions
  - 37/37 PASS

PENDING MANUAL ACTIONS:
  - Review and publish Week 2 article in Substack (Tuesday April 29 deadline)
  - Career lessons database (Session 8-9) — add new lessons manually in Claude.ai
  - Push code to GitHub: git add . && git commit -m "Session update - April 29" && git push
  - Update thread_handoff.md in Claude.ai with full session summary (including ERA sim + contract backtest)
  - White paper: update Section 10 (live track record) in 2-3 weeks, then publish to whitepapersonline.com
  - Week 3 article: May 5-6 deadline — run_pipeline.py --write → weekly_update.py --update → --report --top 15

---
*This file is the persistent memory for Claude Code sessions.*
*thread_handoff.md in Claude.ai is the persistent memory for Claude.ai sessions.*
*Both must be kept in sync. Update both at end of every session.*
