# CLAUDE.md — The Signal Fantasy
# Auto-read by Claude Code at session start.
# Last updated: May 3, 2026 (Sessions 1-19)
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
- William Contreras: top 9 catchers (relaxed from top-8 after lineup context wiring April 2026 — MIL slot 2 weak upstream OBP correctly penalizes RBI)

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

### Product Positioning vs Steamer/ZiPS (established April 2026 via Backtest C)
Signal Fantasy does NOT compete with preseason projection systems on raw MAE. Backtest C (Session 12)
confirms we lose to Steamer and ZiPS on every metric (K, ERA, WHIP, HR, AVG, R, RBI, wOBA).
This is expected and irreducible: they use full preseason context; we project from April data only.

**Our actual advantage is signal direction accuracy**: 88.6% Buy Low / 88.0% Sell High (Backtest B).
Steamer and ZiPS cannot detect in-season luck-driven mispricing because they're preseason systems.
April luck signals identify players mispriced by the market right now — Steamer can't do that.

**Correct framing for all published content:**
- "Our projections are solid but not competing with Steamer on raw counting stats" — accurate
- "Our luck signals identify mispriced players Steamer can't detect" — the real differentiator
- "Complementary to Steamer" is the honest positioning, not "beats Steamer"
- Do NOT publish head-to-head raw MAE comparisons against Steamer — they will not favor us

**One notable exception:** ERA bias — our bias is +0.25 vs Steamer's +0.41. We are LESS biased
on ERA despite higher MAE. This is publishable as "better calibrated on ERA direction."

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

- **Playing time / injury module** — HIGHEST PRIORITY after Backtest C (Session 12 finding).
  Fixes K, R, RBI, and HR projection errors simultaneously. The is_sp fix proved IP is the root
  cause of K MAE (39.4 vs Steamer 21.9). The remaining gap is not K/9 error — it's IP error.
  Design: for starters, load real IP projections from Steamer (already have the CSV) rather than
  the fixed 22 starts × 5.6 IP formula. For relievers, use Steamer appearances. This makes our
  IP match Steamer IP, so counting stat projections should close most of the accuracy gap.
  Implementation: add steamer_ip field to all pitcher projections. For hitters, Steamer's PA
  projection replaces 4.1 PA/game × games_rem. One source of truth for playing time.
  Benefit: projection accuracy improves on K (biggest gap), R, RBI, HR without changing signal logic.
  Note: this is a BACKTEST improvement only — production stat_projections.py uses real in-season
  data which self-corrects for PT. The backtest needs PT from an external source because it
  projects from April data forward without knowing who got hurt.

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

--- Session 10 (lineup context wiring) ---
Lineup context module: build_lineup_context.py + lineup_context.py (new files)
  - data/hitter_batting_slot_2026.json: 452 batters, modal batting slot + n_games
    Slot distribution: {1:49, 2:37, 3:35, 4:36, 5:43, 6:35, 7:44, 8:47, 9:126}
  - data/team_lineup_context_2026.json: 30 teams + _league_avg, OBP/SLG/PA per slot
    League avg: OBP=0.3242, SLG=0.3942
  - Sensitivities backtest-validated against 2025 actuals (n=141): R=0.8, RBI=1.2
  - Sell High RBI cap: min(rbi_mult, 1.05) for overperforming players
  - Caps: MULT_MIN=0.80, MULT_MAX=1.20
Wired into stat_projections.py:
  - compute_lineup_multipliers imported with graceful fallback
  - project_player() applies R_mult/RBI_mult to hitter counting stats
  - 11 Sell High players had RBI_mult capped at 1.05
  - 37/37 PASS
Wired into score_value.py:
  - hitter_luck dict now carries 'team' field (from luck_scores.csv)
  - Post-projection loop applies R_mult/RBI_mult to R_proj/RBI_proj
  - Applied to 419 hitters; all invariants PASS
  - William Contreras invariant relaxed top-8 → top-9 (MIL slot 2 correct penalty)
    MIL slots 8/9/1 OBP all below league avg → 9.3% RBI reduction is real signal
  - 37/37 PASS
Team code audit: ZERO mismatches across all 4 data sources
  - ATH (Oakland) consistent in hitters_statcast.csv, projections, luck_scores, parquet
Top lineup beneficiaries: Kyle Tucker LAD (RBI_mult=1.20), Austin Riley ATL (1.20)
Top lineup penalties: Ke'Bryan Hayes CIN (RBI_mult=0.80), Luis Robert NYM (0.80), Francisco Álvarez NYM (0.80)
Data leakage audit COMPLETE: 2025 is a valid OOS validation year for projection backtest
  - stat_projections.py FG_YEARS=[2022,2023,2024,2025] in PRODUCTION only (intentional)
  - projection_backtest_2025.py explicitly uses [2022,2023,2024] (no leakage)
  - CBS coefficients trained on 2024 only; 2025 is held-out OOS test
  - All hardcoded constants (LG_BARREL=0.066, SWSTR_TO_K9=77.3, league avgs) are 2022-2024 era priors

--- Session 11 (projection backtest A + two projection fixes) ---
William Contreras invariant relaxed: score_value.py rank ≤ 9 (from ≤ 8)
  - MIL slot 2 correct penalty: slots 8/9/1 all below league avg OBP (0.3242)
  - RBI_mult = 0.9407 → 9.3% RBI reduction is a real lineup signal, not a bug
  - 37/37 PASS; all other invariants PASS (Sanchez rank=21, Yordan rank=9, Raleigh rank=2, Baldwin rank=3)
Projection Backtest A: projection_backtest_A.py (new file, ~600 lines)
  - Inputs: April 2025 v4_april_2025.csv (hitters) + pitcher_statcast_april_2025.parquet (pitchers)
  - Actuals: CBS 2025 (hitters counting stats via CBS GP gate ≥80) + statcast_2025_may_july.csv (ROS wOBA)
  - Career baselines: explicit [2022, 2023, 2024] loop (no FG_YEARS contamination)
  - ROS scale: 162/135 = 1.20× for counting stats
  - CBS GP gate: ≥80 GP required (281 of 426 hitters retained)
  - W excluded from pitcher success criteria: all methods use identical starts × 0.33 formula
  - Outputs: data/backtest_A_hitters_2025.csv (235 rows), data/backtest_A_pitchers_2025.csv (165 rows)
  - 37/37 PASS
Projection Fix 1 — AVG (stat_projections.py: hitter_true_talent()):
  - Old: formula_avg only; career_avg used only as floor; systematically over-projected AVG
  - New: true_avg = career_ba × 0.65 + formula_avg × 0.35 (when career_pa ≥ 200)
  - xwOBA-gap nudge: ±0.008 when |xwOBA - wOBA| > 0.030
  - Fallback to formula_avg when career_pa < MIN_CAREER_PA_BA=200
  - New constants: CAREER_BA_WEIGHT=0.65, APRIL_AVG_WEIGHT=0.35, MIN_CAREER_PA_BA=200
  - 5 spot checks: all showed reduced AVG (-0.002 to -0.007), confirming over-projection fix
  - 37/37 PASS; all invariants PASS
Projection Fix 2 — WHIP (stat_projections.py: pitcher_true_talent()):
  - Old: current_whip = true_era × 0.20 + 0.55 (ERA-derived fallback); regresses too slowly
  - New: component approach — proj_h9 = career_h9 × 0.60 + current_h9 × 0.40
         proj_bb9 = career_bb9 × 0.60 + current_bb9 × 0.40; true_whip = (proj_h9 + proj_bb9) / 9
  - career_h9 derived algebraically: career_whip × 9 - career_bb9 (no new data sources)
  - current_h9 from existing pitcher_rates fields: whip_raw × 9 - bb_per9
  - New constants: LG_H9=8.8, LG_BB9=3.1 (2022-2024 era priors)
  - 5 pitcher spot checks: same or lower WHIP (0.00 to -0.01)
  - 37/37 PASS; all invariants PASS
  - NOTE: WHIP fix marginally backfired (MAE 0.1930→0.1944, +0.0014). Component approach introduces
    slightly more noise than ERA-derived formula. Small effect but direction is wrong.
    RTM dominates WHIP (0.155 vs 0.194) — structural problem, not signal-related.
Backtest A re-run (post-fix validation):
  - AVG fix confirmed: MAE 0.0232→0.0216 (−0.0016); bias corrected +0.0058→−0.0023 (over-proj eliminated)
  - WHIP fix honest finding: MAE 0.1930→0.1944 (+0.0014 regression, small but wrong direction)
  - No category flips (AVG/WHIP still RTM-dominant, gap narrowed for AVG, widened slightly for WHIP)
  - Model beats RTM: 4/5 hitter categories (HR, R, RBI, wOBA), 2/3 pitcher categories (ERA, K)
  - Methodology: pre-fix numbers recovered from git HEAD; post-fix from live run

--- Projection Backtest B (signal-informed accuracy, Session 11) ---
Setup: same 235 hitters / 165 pitchers as Backtest A; 2025 signals from backtest_audit_*_v2.csv
Method: signal multipliers applied on top of Model projections; compare 4 methods (Naive/RTM/Model/Signal)

Signal direction accuracy (Table 3 — core validation):
  Hitters:
    Buy Low (n=44):    88.6% outperformed April wOBA  avg Δwoba = +0.058
    Slight Buy (n=8):  87.5% outperformed April wOBA  avg Δwoba = +0.039
    Slight Sell (n=15): 80.0% declined vs April wOBA  avg Δwoba = −0.051
    Sell High (n=25):  88.0% declined vs April wOBA   avg Δwoba = −0.061
  Pitchers:
    Buy Low (n=7):    100% improved ERA  avg ΔERA = −1.08
    Sell High (n=9):  100% declined ERA  avg ΔERA = +1.88

Backtest B v1 findings (what worked, what didn't):
  WORKS: wOBA multipliers — all non-neutral tiers improved vs Model; Signal beats RTM overall (0.0342 vs 0.0397)
  WORKS: HR buy-side — Buy Low 63.3% win rate, Slight Buy 75.0% win rate
  FAILS: AVG multipliers — hurt every tier (career-BA anchor already captures the correction)
  FAILS: HR sell-side — Slight Sell/Sell High MAE worsened (sell signals catch real contact issues, not just luck)
  FAILS: Pitcher Buy Low ERA — n=7, 28.6% win rate; MAE worsened 0.4657→0.6689

Backtest B v2 — cleaned adjustments (production version):
  Active signal adjustments:
    Hitters: wOBA all non-neutral tiers (Buy Low×1.08, Slight Buy×1.04, Slight Sell×0.96, Sell High×0.92)
    Hitters: HR buy-side only (Buy Low×1.05, Slight Buy×1.02; sell-side = 1.00)
    Pitchers Sell High: ERA×1.10, WHIP×1.05, K×0.95
    Pitchers Buy Low: WHIP×0.95, K×1.05 (ERA adj removed)
  Removed: AVG (all tiers), HR sell-side, Pitcher Buy Low ERA
  v2 improvements over v1: HR 6.288→6.256, AVG 0.0242→0.0216 (no longer hurts), ERA 0.8867→0.8780 (now beats Model)
  wOBA unchanged at 0.0342 (same multipliers; still beats RTM)

Backtest B v2 success criteria — ALL PASS:
  [PASS] Signal-adj MAE < Model for Buy Low wOBA:  Model=0.0335  Signal=0.0303
  [PASS] Signal-adj MAE < Model for Sell High wOBA: Model=0.0350  Signal=0.0348
  [PASS] Buy Low outperforms April wOBA ≥60%:  88.6% (39/44)
  [PASS] Sell High underperforms April wOBA ≥60%: 88.0% (22/25)

Files:
  projection_backtest_B.py — v2 cleaned signal adjustments (production version)
  data/backtest_A_hitters_2025.csv, data/backtest_A_pitchers_2025.csv — Backtest A outputs (235/165 rows)
  data/backtest_B_hitters_2025.csv, data/backtest_B_pitchers_2025.csv — Backtest B outputs with signal columns
  data/backtest_B_results_v2.csv — tier-level MAE + direction accuracy summary (15 rows)

STEAMER COMPARISON: COMPLETED — See Backtest C (Session 12).
  Result: we do NOT beat Steamer or ZiPS on any metric when comparing raw MAE.
  Our value-add is signal direction accuracy (88.6%/88.0% BL/SH) and April-informed
  luck detection — not preseason projection accuracy.

--- Session 12 (is_sp fix + Backtest C six-way comparison) ---
is_sp tautology bug fix: projection_backtest_A.py
  - Old formula: `(ip / max(1, ip / 5.0)) >= 4.5` — always True for ip ≥ 4.5 (mathematical proof)
  - Fix: `steamer_gs >= 10` using Steamer 2025 pitcher GS data (loaded in main(), keyed by MLBAMID)
  - Same fix applied to project_pitcher_naive() and project_pitcher_rtm() — both now branch on is_sp
  - Reliever formula: appearances_rem = int(games_rem / 162 × RP_APPS_PER_SEASON × 0.85)
    proj_ip = appearances_rem × 1.0 (where RP_APPS_PER_SEASON=60)
    → ~42 ROS appearances → 42 IP ROS → 50 IP full-season equivalent
  - Steamer GS loaded: 5,214 pitchers (189 SP GS≥10, 5,025 RP GS<10)

K MAE impact from is_sp fix:
  - Before fix: K MAE = 45.8, bias = +23.0 (massive over-projection from treating all as starters)
  - After fix:  K MAE = 39.4, bias = −12.4 (significant improvement, now slight under-projection)
  - Steamer K MAE: 21.9 — we still don't beat Steamer, but gap narrowed from +23.9 to +17.5
  - Root: IP error contribution: +36.5 (before fix) → resolved
    Remaining gap: our IP projection for starters still volatile (early-season-only data)
  - Production code confirmed unchanged: stat_projections.py NOT in git diff
  - 37/37 PASS

Backtest C (six-way comparison — Naive/RTM/Steamer/ZiPS/Model/Signal):
  Files: projection_backtest_C.py (new), data/backtest_C_hitters_2025.csv, data/backtest_C_pitchers_2025.csv
  Pool: 235 hitters / 165 pitchers (100% Steamer match rate, 99.6% hitter / 100% pitcher)

  TABLE 1 — Six-way MAE summary:
  Hitters:
    HR:   ZiPS=5.18  Steamer=5.92  Model=6.30  Signal=6.26  → Ours loses
    AVG:  ZiPS=0.018 Steamer=0.019 Model=0.022 Signal=0.022 → Ours loses
    R:    ZiPS=13.55 Steamer=15.12 Model=17.19              → Ours loses
    RBI:  ZiPS=15.96 Steamer=16.49 Model=17.01              → Ours loses
    wOBA: Steamer=ZiPS=0.0277       Model=0.0350 Signal=0.0342 → Ours loses
  Pitchers:
    ERA:  Steamer=0.786 ZiPS=0.849  Model=0.882 Signal=0.878 → Ours loses
    WHIP: ZiPS=0.133   Steamer=0.136 Model=0.194             → Ours loses
    K:    Steamer=21.9  ZiPS=25.4   Model=39.4  Signal=39.4  → Ours loses

  Success criteria: [FAIL] both hitter and pitcher (0 metrics beat BOTH Steamer & ZiPS)

  KEY INTERPRETATION — This is expected and doesn't undermine the product:
  - Steamer/ZiPS are professional systems trained on decades of historical data
  - We project ROS from 1 month of April data; Steamer/ZiPS use full preseason context
  - Our ADVANTAGE is signal detection (luck mispricing), not raw projection accuracy
  - Signal direction accuracy (88.6% BL, 88.0% SH) is the real differentiator
  - The correct framing: "Our luck signals identify mispriced players; our projections
    are decent but not competing with preseason projection systems on raw accuracy"

  Bias summary (Backtest C post-fix):
    ERA bias: Steamer=+0.41, ZiPS=+0.41, Model=+0.25 (we're LESS biased than Steamer/ZiPS on ERA)
    K bias: Steamer=−4.5, Model=−12.4, ZiPS=−16.2 (Steamer least biased on K)
    wOBA bias: Steamer=−0.008, Model=−0.012 (both slight under-projection)

  Notable wins vs Steamer (Table 5):
    wOBA: Cam Smith (margin +0.051), Nick Allen (+0.044) — under-priced April breakouts we caught
    HR: Gunnar Henderson (margin +14.3), Ben Rice (+14.2) — thin baseline fix working

PENDING MANUAL ACTIONS:
  - Review and publish Week 2 article in Substack (if not yet done)
  - Career lessons database (Sessions 8-12+) — add new lessons manually in Claude.ai
  - Update thread_handoff.md in Claude.ai with full session summary
  - White paper: update Section 10 (live track record) in 2-3 weeks, then publish to whitepapersonline.com
  - Week 3 article: May 5-6 deadline — run_pipeline.py --write → weekly_update.py --update → --report --top 15

--- Session 13 (FantasyPros ownership + hidden gem query) ---
fetch_fantasypros_ownership.py: new file — scrapes FP stats pages for cross-platform ownership
  - Source: fantasypros.com/mlb/stats/hitters.php + pitchers.php (both return 200, no auth required)
  - Parses consensus-own (ESPN+Yahoo+CBS aggregate), espn-own, yahoo-own per player
  - 300 hitters + 300 pitchers per page (598 unique FP players total)
  - Name normalization: NFD decompose → strip combining marks → lowercase → drop non-alpha-space
  - Match rate: 571/819 (69.7%) against our universe (421H + 400P)
  - Unmatched = FP doesn't rank them in top-300 (low-ownership players like injured Bohm, Hayes)
  - Adds 4 columns to data/player_ownership_2026.csv: fp_ownership, fp_espn_own, fp_yahoo_own, fp_fetched
  - 601/3797 rows updated in player_ownership_2026.csv (covers our active hitter+pitcher universe)
  - --check flag: probe mode, no writes; usage: python fetch_fantasypros_ownership.py [--check]
  - Includes hidden gem preview (fp_ownership < 35%, wOBA > .330) at end of run

Hidden gem query (fp_ownership primary, ESPN fallback):
  - Uses fp_ownership when available; falls back to owned_pct (ESPN) when no FP match
  - Top candidates (April 28-29 2026): TJ Rumfield COL 9% (Buy Low, luck+0.252), Samuel Basallo BAL 20%
    (xwOBA .393, gap+.042), Ryan Jeffers MIN 18% (wOBA .414), Kerry Carpenter DET 34% (xwOBA > wOBA)
  - 10 candidates meet filter (own<35%, wOBA>.330, gap>-0.020, luck>-0.085, PA≥75)
  - 37/37 PASS

--- Session 14 (playing time module + launch angle display + Sanchez invariant fix) ---
Playing time module: stat_projections.py — Steamer-based PA/IP blending
  - _STEAMER_PA, _STEAMER_IP, _IL_STATUS, _HITTER_GP, _PT_LOADED module-level dicts
  - _load_pt_lookups(): lazy-loads Steamers 2025 batters.csv + pitchers.csv + ownership + statcast GP
  - _blend_pa(mlbam_id, games_rem, pa_so_far, games_played): GP-tiered Steamer trust
    games_played < 20: w_s=0.70 | 20-50: w_s=0.60 | 50+: w_s=0.40
    IL penalties: DAY_TO_DAY -5 games, INJURY_RESERVE -12 games (ESPN returns ACTIVE for all players)
    Fallback to slot formula when Steamer absent or pace unreliable
  - _blend_ip(mlbam_id, games_rem, current_ip, current_gs, current_games): SP/RP branching
    SP: 0.55 Steamer_ros + 0.45 pace_ros; RP: 0.80 Steamer_ros + 0.20 pace_ros; RP cap 70 IP
    Fallback to steamer_ros when current_ip < 15 or current_games = 0
  - project_hitter_counting(): new params mlbam_id, pa_so_far, games_played (all Optional, backward-compat)
  - project_pitcher_counting(): new params mlbam_id, current_ip, current_gs, current_games
  - project_player(): passes batter_id/pitcher_id to counting functions; loads HITTER_GP for GP lookup
  - Steamer coverage: 417/423 hitters (98.6%), 396/402 pitchers (98.5%); unmatched = rookies/NPB
  - G/GS null for all 402 pitchers in pitcher_luck_scores.csv (FanGraphs join failure) — OK because
    _blend_ip uses steamer_data['GS'] for SP/RP classification, independent of current GS column
  - ESPN injuryStatus: players_wl endpoint does NOT expose injuryStatus — all return ACTIVE
    Infrastructure in place; IL penalties = 0 until a different endpoint is used
  - 380 hitters changed by >20 PA; 254 pitchers changed by >10 IP
  - Top PA gainers: Ohtani +102, Kurtz +101, Schwarber +73
  - Top PA losers: bench players with 4-14 GP correctly dropping from 498 to 10-100 PA
  - Top IP gainers: Webb +61, Gilbert +59, Alcantara +57 (all elite SPs getting full workload credit)

Launch angle display: score_luck.py + build_hitter_launch_angle.py
  - build_hitter_launch_angle.py: standalone script; builds data/hitter_launch_angle.json
    Career baseline: weighted mean LA from v4_april_{2022-2025}.csv (MIN_YEAR_BBE=10, MIN_CAREER_BBE=100)
    Current season: hitters_statcast.csv (MIN_CURRENT_BBE=50)
    454 records; 336 with career baseline; 148 with full delta; 54 trending_up; 35 trending_down
  - score_luck.py: LAUNCH_ANGLE_PATH added; _launch_angle_h dict loaded at startup
    Display columns added to luck_scores.csv: current_la_avg, career_la_avg, la_delta,
    la_trending_up (delta >+3°), la_trending_down (delta <-3°), la_display (text description)
  - display-only — zero impact on luck_score or verdict
  - 37/37 PASS

fetch_ownership.py: injury_status column added
  - ESPN players_wl endpoint: injuryStatus field silently returns ACTIVE for all players
  - Column added to player_ownership_2026.csv; infrastructure ready for better endpoint
  - 37/37 PASS

score_value.py: Sanchez Test fix — pre-existing FAIL (rank 20) resolved
  - Root cause: xwOBA not regressed toward career baseline; Sanchez's 77-PA xwOBA=0.433
    (vs career 0.326) inflated R/RBI and pushed him to catcher rank 20
  - Fix 1: xwOBA career regression — blends current xwOBA toward xwoba_3yr from luck_scores.csv
    XWOBA_PA_STAB=250; same PA-weighted pattern as barrel_rate
    xwoba_3yr added to load_luck_scores() and merged into hitter_df before project_hitter_stats()
  - Fix 2: BARREL_PA_STAB 200→250 (more defensible; barrel rate takes 250+ PA to stabilize)
  - Post-fix: Sanchez L1=20.4→19.X, rank 20→21 (just below Kirk's CQS floor of 20.0)
  - All invariants PASS: Yordan 8, Raleigh 2, Baldwin 3, Contreras 6, Sanchez 21
  - 37/37 PASS

PENDING MANUAL ACTIONS:
  - Week 3 article (May 5-6): run_pipeline.py --write → weekly_update.py --update → --report --top 15
  - Career lessons database (Sessions 8-14+) — add manually in Claude.ai
  - White paper Section 10 update in 2-3 weeks

--- May 1, 2026 (Session 16) ---
CBS rank aliases: 5 entries added to fetch_cbs_rank.py _CBS_ALIASES
  - "michael king" → "mike king" (Mike King SD was CBS#27 Sell High — silently missing)
  - "louie varland" → "louis varland", "mike soroka" → "michael soroka"
  - "jake junis" → "jakob junis", "jt ginn" → "j t ginn"
  - Pitcher match rate 171→176
  - fetch_cbs_rank.py committed bcf0aff

SP role override system: score_pitcher_luck.py output extended
  - player_name/team/ip alias columns added (downstream script compatibility)
  - player_type: "SP"/"RP" from Steamer GS>=10
  - role_override: True/False — 33 pitchers reclassified RP→SP via gates:
    total_starts>=5 AND IP>=20 AND IP/total_starts>=4.0
  - Display-only; verdict logic unchanged
  - Committed 4869109

_blend_ip() SP fallback fix: stat_projections.py
  - Pitchers Steamer classifies as RP but demonstrably starting get SP blend
  - Weights flipped: 0.45 Steamer + 0.55 pace (Steamer IP forecast wrong for them)
  - Cap: 110 IP ROS max for role-override SPs
  - Schlittler: 7.5 → 74.8 IP after fix
  - 110 IP cap also applied in project_pitcher_counting() fallback branch
    (catches pitchers absent from Steamer CSV — e.g. Chase Burns 123.3→110.0)
  - role_overridden parameter threaded through call site (~line 1375)
  - Committed 17cd159

Replacement level formula corrected: league_settings.py
  - Was: base_fpts * (0.90 + 0.10 * pool_ratio) — INVERTED
  - Fixed: base_fpts * (1.10 - 0.10 * pool_ratio)
  - Deeper leagues now correctly produce lower replacement FPTS
  - 13-team SP ≈ 208 FPTS | 15-team SP ≈ 197 FPTS

League settings Phase 1: committed 4cfde51
  - data/leagues/league_1.json: CBS 13-Team (AVG, SV×3+H×2, C:2, P:9, 7 reserves)
  - data/leagues/league_2.json: Fantrax 15-Team (OBP, SV×1+H×1, C:1, P:10, 5 reserves)
  - data/leagues/template.json: blank schema template
  - league_settings.py: load_league(), get_replacement_level(), get_stat_weight(), _validate()
  - dashboard.html: tvLeagueNames → "CBS 13-Team" / "Fantrax 15-Team"
  - dashboard.html: taLeague default extended with roster_slots, saves_holds_ratio, team_count
  - dashboard.html: _LEAGUE_DEFAULTS constant; setLeague() merges defaults on toggle
  - dashboard.html: loadLeagueSettings() seeds from league1 on first visit
  - 37/37 PASS throughout session

PENDING MANUAL ACTIONS:
  - Week 3 article (May 5-6): run_pipeline.py --write → weekly_update.py --update → --report --top 15
  - Career lessons database (Sessions 15-17) — add new lessons manually in Claude.ai
  - White paper Section 10 update in 2-3 weeks

--- May 2, 2026 (Session 17) ---

1. Trade tool architecture fix (Bug 3) — trade_analyzer.py, commit fda45c4
   Correct 5-step flow: Steamer projections → signal multipliers → CBS FPTS → surplus → verdict.
   Signals now adjust projected stats only; surplus delta drives verdict (_trade_verdict_v3).
   Backtest B v2 multipliers: BL→R×1.08/HR×1.05/RBI×1.08; SH→R×0.92/RBI×0.92;
   P SH→ERA×1.10/WHIP×1.05/K×0.95; P BL→WHIP×0.95/K×1.05.

2. Skenes SP classification fix — _derive_pos() uses player_type/role_override from
   pitcher_luck_scores.csv. _get_fpos() routes pitchers through _derive_pos() instead of
   stale player_values.json. Skenes: SP+95 surplus vs SP replacement (not RP).

3. New verdict thresholds (surplus delta): ≥50 STRONG | ≥20 FAVORABLE | ≥5 SLIGHT
   | ≤-50 AVOID | ≤-20 UNFAVORABLE | ≤-5 SLIGHTLY UNFAVORABLE | else NEUTRAL.

4. All 3 smell tests PASS:
   Case 1 (Skenes→Rice): delta -142 → AVOID ✓
   Case 2 (Skubal→Rice): delta -131 → AVOID ✓
   Case 3 (Acuña BL→Rice SH): delta -251 → AVOID ✓

5. Housekeeping: 2 new Tier 2 parking lot items added to thread_handoff.md
   (Steamer Dependency Audit + Own Projection System), commit f0639ad.

6. 37/37 PASS. No invariant failures.

PENDING MANUAL ACTIONS:
  - Week 3 article (May 5-6): run_pipeline.py --write → weekly_update.py --update → --report --top 15
  - Career lessons database (Sessions 17-18) — add new lessons manually in Claude.ai
  - White paper Section 10 update in 2-3 weeks

--- May 2, 2026 (Session 18) ---

1. trade_analyzer.py surplus display — per-player breakdown with position and replacement FPTS reference.
   Old: "give +95 | get -47 | delta -142"
   New: "Give surplus: Paul Skenes +95 (SP, repl 201) | Get surplus: Ben Rice -47 (C, repl 219)"
   Commit 4277a8f.

2. trade_analyzer.py --explain flag — step-by-step CBS valuation walkthrough.
   Shows: model projections → trade-tool signal multipliers → per-term CBS FPTS calculation →
   replacement level and N → surplus → verdict summary.
   Usage: python trade_analyzer.py --explain
   Commit 4277a8f.

3. stat_projections.py _blend_pa GP estimation fix — when games_played=0 (ESPN endpoint
   limitation) but pa_so_far >= 5, estimate gp_eff = max(pa_so_far // 4, 5).
   Prevents Steamer-only domination for breakout players whose 2025 Steamer PA is stale.
   Rice: projected_pa 155 → 285. Counting stats unchanged (rate-based model).
   Commit 4277a8f.

4. Rice surplus clarified — -47 (adjusted) is model's honest Sell High signal.
   Architecture: projections_2026.csv has in-model LUCK_MULTIPLIERS (R×0.94 for SH);
   trade tool adds Backtest B v2 multipliers (R×0.92) on top. Combined: R×0.865.
   Career HR baseline drag (0.029 career vs 0.052 current) also constrains HR projection.
   CBS projects 28 HR vs our 11 HR — known under-projection for young breakout players
   (documented in Backtest C, Session 12). Not a bug; will improve when native projection
   system replaces Steamer 2025 proxy.

5. All 3 smell tests PASS with new per-player display:
   Case 1 (Skenes→Rice): delta -142 → AVOID ✓
   Case 2 (Skubal→Rice): delta -131 → AVOID ✓
   Case 3 (Acuña→Rice): delta -255 → AVOID ✓

6. 37/37 PASS. All invariants PASS (Sanchez rank 22, Yordan rank 8).

7. Parking lot additions (Tier 1) — thread_handoff.md updated:
   - Young Breakout Player Projection Fix: career weight 0.60 too high for players <300 career PA
     (Rice/Walker case). Target: reduce to 0.30-0.40 with sensitivity sweep + short-baseline confidence flag.
   - Trade Tool Edge Case Analysis: C replacement calibration, career weight sweep, PA crossover threshold.
   - --explain Flag paid tier surface: built Session 18 (commit 4277a8f); surface in dashboard premium toggle.

PENDING MANUAL ACTIONS:
  - Week 3 article (May 5-6): run_pipeline.py --write → weekly_update.py --update → --report --top 15
  - Career lessons database (Sessions 17-18) — add new lessons manually in Claude.ai
  - White paper Section 10 update in 2-3 weeks

--- May 3, 2026 (Session 19) ---

1. career_weight_sweep.py (new diagnostic) — sensitivity sweep proving career weight is NOT the lever
   - Rice surplus ranges -36.3 to -35.4 across ALL weights (0.30-0.60) — HR accounts for only +1.7 FPTS
   - R/RBI are 6.5× more valuable per unit than HR in CBS FPTS formula
   - Real fix: Steamer G=48.4 (backup projection) was dominating PA blend
   - PA scenario confirmed: ~480 PA needed for +60 surplus; stale-Steamer fix is the correct lever
   - Crossover diagnostic: surplus=+60 requires 233.8 HRs (impossible) — career weight irrelevant

2. stat_projections.py — stale-Steamer override fix in _blend_pa()
   - Added _STEAMER_G module-level dict + loading in _load_pt_lookups()
   - Added _STEAMER_PT_OVERRIDE_FLAGS module-level dict
   - Trigger: pace_ros > steamer_ros × 1.5 AND Steamer G ∈ [20, 80) → w_s=0.30, w_p=0.70
   - G >= 20 floor prevents rookies/NPB players (G < 20) from trivially firing override
   - 120 hitters with steamer_pt_override=True (all legitimate part-timer→starter cases)
   - Ben Rice: PA 285 → 384; HR 11→15, R 36→48, RBI 32→42, SB 2→6
   - project_player(): steamer_pt_override flag threaded to projected stats dict

3. generate_projections.py — steamer_pt_override column added to COLUMNS and row dicts

4. trade_analyzer.py — short-baseline confidence flag (display-only)
   - career_pa < 300: prints "⚠ Short baseline — under 300 career PA. Verify barrel rate
     and exit velocity trend before acting on this call."
   - No verdict change

5. dashboard.html — .short-baseline-badge CSS + Simple View + Advanced View badges
   - Purple/lavender badge "Short Sample" for career_pa < 300 hitters
   - Both views wired; title tooltip with full warning text

6. Rice before/after:
   - Old: PA=285, HR=11, R=36, RBI=32, surplus=-47 (C repl 219.4)
   - New: PA≈384, HR=15, R=48, RBI=42, surplus=-15 (C repl 239)
   - Improvement: +32 surplus points. Still negative (SH signal suppresses counting stats).
   - Target +60 to +100 requires ~480 PA — stale-Steamer fix is a real improvement but
     won't reach target until Rice accumulates 400+ PA and model trust shifts to current pace.

7. Smell tests — all PASS with new values:
   Case 1 (Skenes→Rice): delta -110 → AVOID ✓
   Case 2 (Skubal→Rice): delta -98 → AVOID ✓
   Case 3 (Acuña→Rice): delta -213 → AVOID ✓

8. 37/37 PASS. All invariants PASS (Sanchez rank=22, Yordan rank=8, Raleigh rank=2, Baldwin rank=3).

PENDING MANUAL ACTIONS:
  - Week 3 article (May 5-6 deadline — check if overdue): run_pipeline.py --write → weekly_update.py --update → --report --top 15
  - Career lessons database (Sessions 17-19) — add new lessons manually in Claude.ai
  - White paper Section 10 update in 2-3 weeks
  - Update thread_handoff.md in Claude.ai with Session 19 summary

--- May 3, 2026 (Session 19 — continued audit + fixes) ---

1. _blend_pa() gate tightening (stat_projections.py) — override count 120 → 30
   - Raised G floor: 20 → 40 (eliminates fringe bench players with G=20-39 getting opportunistic ABs)
   - Added PA gate: pa_so_far >= 80 required (prevents injured/optioned players with <25 PA from firing)
   - All 9 legitimate cases from audit preserved; 90 noise overrides eliminated
   - New gates: G ∈ [40, 80) AND pace_ros > steamer_ros × 1.5 AND pa_so_far >= 80

2. Max Muncy MLBAM ID disambiguation bug — FIXED (stat_projections.py + generate_projections.py)
   - Root cause: project_player(name="Max Muncy") used _fuzzy_find() → always picked LAD row (first match)
   - ATH Muncy (691777) was getting LAD Muncy's (571970) stats in both projections_2026.csv and player_values.json
   - Fix: project_player() now accepts optional mlbam_id param; when provided, filters fuzzy matches by ID
   - generate_projections.py: passes batter= (hitters) and pitcher= (pitchers) MLBAM IDs to project_player()
   - Post-fix: ATH Muncy now shows distinct stats (proj_avg .208 / HR 10 / R 31 vs LAD's .233 / HR 15 / R 52)
   - This pattern applies to any duplicate name — the fix is general, not Muncy-specific

3. Ohtani display edge case — KNOWN ISSUE, logged here (no code change)
   - In standard leagues: Ohtani appears as hitter only (RP classification in pitcher_luck_scores.csv
     produces +216 surplus vs RP replacement, which is noise from his hitting stats)
   - In two-way player leagues: he should split into hitter + pitcher with separate surplus calculations
   - Do NOT hardcode a suppression rule — this requires league_settings.json configuration
   - Action required before trade tool goes public: add two_way_player flag to league settings schema;
     in standard leagues suppress pitcher row for Ohtani; in two-way leagues show both rows separately
   - Current state: trade tool displays Ohtani correctly as hitter when queried directly; the RP surplus
     noise only appears in diagnostic position tables (Part 2 audit), not in user-facing trade output

4. 37/37 PASS. All invariants PASS (Sanchez rank=22, Yordan rank=8, Raleigh rank=2, Baldwin rank=3).
   Smell tests re-verified after gate changes (Skenes→Rice: -110 AVOID, Skubal→Rice: -98 AVOID).

PENDING MANUAL ACTIONS:
  - Week 3 article (May 5-6 deadline — check if overdue): run_pipeline.py --write → weekly_update.py --update → --report --top 15
  - Career lessons database (Sessions 17-19) — add new lessons manually in Claude.ai
  - White paper Section 10 update in 2-3 weeks
  - Update thread_handoff.md in Claude.ai with Session 19 summary (include Session 19 continued)

---
*This file is the persistent memory for Claude Code sessions.*
*thread_handoff.md in Claude.ai is the persistent memory for Claude.ai sessions.*
*Both must be kept in sync. Update both at end of every session.*
