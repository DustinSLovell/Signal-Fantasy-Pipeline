# THE SIGNAL FANTASY — Thread Handoff Document
# Single source of truth. Overwrite at end of every session.
# Last updated: April 28, 2026 (Session 9)

# Official project start: April 12-14, 2026
# First public article: April 22, 2026
# Days from zero to production ML pipeline: ~10
# Reddit launch: 17K views, #2 on r/fantasybaseball
# "Built in 10 days" is the headline story

---

## WHO YOU ARE TALKING TO

Dustin Lovell — CPG leadership professional transitioning into senior tech roles
(VP Analytics, Director AI Strategy, RevOps at growth tech companies)

Project start: April 12-14, 2026
First article published: April 22, 2026
~10 days from zero to production ML pipeline
Fantasy baseball analytics pipeline is the portfolio project proving data/ML skills.
Every session includes career lessons tied to code concepts where relevant.

---

## THE BRAND

**Name:** The Signal Fantasy
**Tagline (pending):** "Luck is noise. We find the signal."
**Gmail:** thesignalfantasy@gmail.com
**Substack:** signalfantasy.substack.com
**X:** @SignalFantasy
**Instagram:** @signalfantasy
**Reddit:** u/Dlovell02 (personal — 4yr old, 169 karma — more credible than brand account)

---

## SOCIAL STATUS (April 24, 2026)

- Reddit (u/Dlovell02): 17K views, 52 upvotes, 43 comments, #2 post r/fantasybaseball
- Substack: Article #1 live April 22, 17+ subscribers, 510 views
- X (@SignalFantasy): Active — Dingler tweet thread posted April 24 (timestamped)
- Instagram (@signalfantasy): Accuracy graphic posted
- Facebook: Deferred

### POSTED April 24:
- Reddit AMA follow-up comment (Pages, Vásquez, Murakami) — top level reply
- Dingler tweet thread: "CBS #6, consensus #17 — buy the value" — timestamped April 24

---

## THE PROJECT

**Location:** C:\Users\dusti\fantasy-baseball
**Dashboard:** localhost:8000/dashboard.html
**Pipeline files:** luck_scores.csv (hitters), pitcher_luck_scores.csv (pitchers)
**Career lessons:** career_lessons_database.html (88 concepts, open in browser)

---

## AUTHORITATIVE ACCURACY NUMBERS (v2.0 — backtest v7, updated April 26, 2026)

⚠ TWO-RULER NOTE: Backtest (v7) and production scorers use different score scales and thresholds.
Never apply production thresholds to backtest scores — that produces ~23 cases and overfits to noise.
Backtest ruler numbers are the authoritative validation record. Production numbers are for live decisions.

### HITTER MODEL — Version D (additive modifiers, adopted April 26, 2026):

| Signal | Train 2022-24 n | Train acc | OOS 2025 n | OOS acc |
|--------|-----------------|-----------|------------|---------|
| Buy Low    | 55 | 91.3% | 25 | 96.0% |
| Slight Buy | 56 | 73.5% | 22 | 90.9% |
| Slight Sell| 56 | 89.3% | 26 | 76.9% |
| Sell High  | 36 | 91.7% | 14 | 100.0% |
| **Overall** | **187** | **86.1%** | **87** | **89.7%** |
| vs RTM | — | — | — | +17.9pp |

Version A baseline (no modifiers): train 84.4% (n=211) / OOS 89.4% (n=94)
Version D improvement: +1.7pp train / +0.3pp OOS / 42 real verdict changes
n_eval drop (211→187 train) is intentional: additive penalties cross tier boundaries,
downgrading borderline buys to Neutral which are excluded from eval.
OOS guard rail PASS: 89.7% ≥ 87.0% threshold.

Thresholds (production): Buy Low >0.150 | Slight Buy >0.100 | Slight Sell <-0.085 | Sell High <-0.150
Backtest thresholds (different scale): H_BT_BUY_LOW=0.040 | H_BT_SLIGHT_BUY=0.020 | etc.
Gates: Slight Buy requires xwOBA_gap >= 0.030 AND xwOBA < 0.380 (updated April 25)
  - 0.030 gap gate: removes BABIP-only signals (28.6% acc below this)
  - 0.380 xwOBA ceiling: removes already-good hitters (25% acc above this)
  - 0.100 floor: removes weak signals near coin-flip (16.7% acc in 0.065–0.099 range)

INVALID numbers — do not publish: "~89.0% train / ~93.5% OOS" — these used production
thresholds applied to backtest scores (23 cases), producing overfitted noise. Superseded.

### PITCHER MODEL v2.0 (Split architecture — April 23, ERA floor updated April 25):

| Signal | 4-Yr Avg | Notes |
|--------|----------|-------|
| Buy low | 85.7% | ERA floor raised 3.50→3.75 April 25 (+7.3pp OOS) |
| Slight buy | ~84% | n=4 historically — sensitivity analysis confirmed gate optimal |
| Slight sell | 84.2% | |
| Sell high | 94.6% | |
| **Overall** | **92.2%** | was 91.1% pre ERA floor fix |
| vs. RTM | +22.2pp | was +21.1pp |

Buy Low ERA gate change April 25: ERA >= 3.75 (was 3.50)
Sensitivity analysis confirmed: all other 10 parameters already optimal
Canary check: grep -n "3.75\|BUY_LOW_ERA" score_pitcher_luck.py → must find line ~967

### KEY HEADLINE NUMBERS (use everywhere):
- 100% SELL HIGH pitchers (2025 OOS, n=14)
- 91.7% SELL HIGH hitters (train 2022-24, Version D)
- 91.3% BUY LOW hitters (train 2022-24, Version D) / 96.0% OOS 2025
- 86.1% overall hitters (train 2022-24, Version D) / 89.7% OOS 2025
- 85.7% overall pitchers (2024 single-year backtest)
- +17.9pp vs RTM hitters (OOS 2025)
- 2025 out-of-sample: 89.7% hitters (never trained on this data — most trustworthy number)

### BACKTEST METHODOLOGY NOTE:
- Training/calibration: 2022-2024 data ONLY
- Out-of-sample validation: 2025 ONLY
- Never publish 2022-2024 numbers as "live accuracy" — those are in-sample
- 89.7% 2025 OOS is the headline credibility number (Version D — updated April 26)
- Backtest audit CSVs: data/backtest_audit_hitters.csv + data/backtest_audit_pitchers.csv

---

## SIGNAL STACK

### Hitter layers (7):
1. Core: xwOBA gap (actual vs expected contact quality)
2. Defensive adjustment (OAA) ±0.008
3. Contact type (GB rate BABIP adjustment)
4. Plate discipline (BB%/K% thresholds)
5. Career BABIP baseline (476 hitters) — not league average
6. Age-adjusted BABIP decay (32-34: ×0.97; 35-36: ×0.94; 37-38: ×0.91; 39+: ×0.88)
7. Seasonal patterns + platoon adjustment (Layer 7 confidence modifier)
   - Slight buy +1.6pp, Buy low +0.6pp in backtest
   - xwOBA gate (updated April 25): Slight buy requires xwOBA_gap >= 0.030 AND xwOBA < 0.380
   - Chase rate (sell-side only): gap > 0.040 → luck_score × 1.10; > 0.060 → × 1.15
   - Platoon modifier (updated April 26): compares current split gap to CAREER baseline from
     hitter_career_platoon.json (489 batters, PA min 30 each hand, prefers xwOBA over wOBA)
     gap_delta > +0.040 vs career → AMPLIFY ×1.05 | gap_delta < -0.040 vs career → DAMPEN ×0.90
     Fallback: -0.019 (career data mean) when no career record exists
     19 modifier result changes vs old static approach in 2026 data

### BUY SIGNAL ADDITIVE MODIFIER ARCHITECTURE — Version D (adopted April 26, 2026):
All hitter buy signal dampeners use flat additive penalties subtracted from luck_score.
Penalties accumulate in _buy_penalty column; capped at H_MAX_COMBINED_PEN=0.040 total.
Applied in one combined pass after all flag detection blocks.

Calibrated penalty constants (sensitivity sweep on 2022-2024 training data, config.py):
- H_KP_K_PENALTY      = 0.010   # K-rate spike >3pp above career
- H_KP_PULL_PENALTY   = 0.008   # pull-rate drop >5pp below career
- H_HH_PENALTY        = 0.012   # hard-hit rate drop >3pp below career
- H_SPEED_PENALTY     = 0.010   # sprint speed cliff >0.3 ft/s YoY
- H_CHASE_PENALTY     = 0.008   # chase rate rise >3pp above career (buy-side only)
- H_MAX_COMBINED_PEN  = 0.040   # hard cap on combined dampening per player
- H_CHASE_AGE_WEIGHT_U25   = 0.40  # age ≤25: chase penalty × 0.40 (development noise)
- H_CHASE_AGE_WEIGHT_26_27 = 0.70  # age 26-27: chase penalty × 0.70 (still maturing)
  8 young buy players receive +0.0048 score relief: Henderson, Merrill, Tovar, Soderstrom,
  Cam Smith, Jordan Beck, Jacob Wilson, Langford — zero verdict impact at current scores.

Why additive beats multiplicative: multiplicative ×0.95 cannot cross tier boundaries
(0.050 × 0.95 = 0.0475, stays Slight Buy). Additive can (0.050 − 0.012 = 0.038, drops to Neutral).
Root cause of all prior versions being verdict-neutral: the 0.040 tier gap exceeded multiplier magnitude.

Version A→D: +1.7pp train (84.4%→86.1%) / +0.3pp OOS (89.4%→89.7%) / 42 verdict changes

### FINANCIAL MOTIVATION COHORT FRAMEWORK (display only — redesigned April 26-27, 2026):
_assign_cohort() function in score_luck.py. contract_cohort column in luck_scores.csv output.
Framework rebuilt around financial security gap (not binary CY status). Five cohorts:
  1=Generational Payday: age 25-31, underpaid vs market, ≤2yr to FA → max motivation
  2=Prove-It: any age, 1-2yr deal post-injury or down year → rebuilding market value
  3=Already Secured: annual_salary_m ≥ $20M AND years_remaining ≥ 3 → secure, less motivated
  4=Post-Prime: age 33+ any contract → physical ceiling, not motivation
  5=Mid-Contract: age 28-33, multi-year, not FA-bound → neutral baseline assumption
Priority order: manual override → prove_it flag → secured ($20M+, 3+yr) → post-prime (33+) → payday (age 25-31, ≤2yr) → mid-contract.
Pre-populated Cohort 3: Ohtani, Judge, Trout, Harper, Seager, Lindor, Turner, Machado, Riley (9 players)
Pre-populated Cohort 1: Acuña ($12.5M/yr, 2yr left), Yordan ($19.2M/yr, 1yr left)
Wayback Machine scraper built (build_spotrac_contracts.py) — outputs spotrac_contracts_raw.csv.
CDX API (web.archive.org); team-specific URL pattern; 60s timeout; ~50-60% CDX success rate.
NEXT STEP: Review spotrac_contracts_raw.csv and merge valid entries into contract_year_2026.csv.
No model weight — contract cohort is display-only until backtest evidence supports weighting.

### Pitcher layers (v2.0 — split architecture):

BUY SCORE (ERA-FIP dominant):
- ERA-FIP gap (×0.60) — primary signal
- xwOBA gap (×0.25) — secondary validator
- BABIP vs career baseline (×0.15) — tertiary
- Classification from RAW score before confidence scaling

SELL SCORE (full 8-component composite):
1. BABIP allowed vs career baseline (×5.0)
2. LOB% vs 72.4% (×-3.0)
3. ERA-FIP gap (×0.15)
4. ERA-xERA gap (×0.10)
5. HR/FB rate (non-linear, fires >14%)
6. Hard hit allowed vs career baseline (×-1.5)
7. Barrel rate vs career baseline (×-1.5)
8. SwStr% vs 11% (×2.0)

BUY QUALIFICATION GATES (all must pass):
- FIP <= 4.50
- SwStr% >= 8%
- Career IP >= 100
- IP >= 20 (waived if raw_buy_score >= 1.50 — Boyle exception)
- ERA >= 3.50 (all buys); ERA >= 3.75 for BUY LOW; ERA >= 4.00 for SLIGHT BUY only
- |FIP-xERA| <= 1.50 OR xERA <= 4.50
- FIP >= 1.50 if IP < 20

CSW buy-low-only modifier (KEPT in production):
- csw_gap > +0.025 → ×1.10 (amplify)
- csw_gap < -0.025 → ×0.90 (dampen)
- Applied to buy-low signals only

AGE TIER LOGIC:
- Age 35+ + luck <= -0.20 → "Sell and Move On"
- Age 35+ + luck <= -0.12 → "Sell High on Perception"
- Age 35+ + mild signal → keep tier + "Age 35+ monitor"

---

## CURRENT SIGNALS (April 24, 2026)

### Pitcher Buy Low (7):
| Pitcher | Team | ERA | FIP | xERA | IP | Luck |
|---------|------|-----|-----|------|----|------|
| Jesus Luzardo | PHI | 6.41 | 3.22 | 3.99 | 26.7 | 0.4531 |
| Joe Ryan | MIN | 5.29 | 3.20 | 2.58 | 32.3 | 0.3487 [CSW dampened] |
| Joe Boyle | TB | 6.46 | 3.05 | 4.59 | 15.3 | 0.3351 |
| Cristopher Sanchez | PHI | 3.82 | 2.60 | 3.03 | 33.0 | 0.3095 |
| Logan Gilbert | SEA | 4.22 | 2.99 | 3.62 | 32.0 | 0.2791 |
| Kyle Bradish | BAL | 5.55 | 3.48 | 3.46 | 24.3 | 0.2405 |
| Shane Baz | BAL | 5.20 | 3.69 | 4.30 | 27.7 | 0.2047 [CSW dampened] |

### Pitcher Slight Buy (8):
| Pitcher | Team | ERA | FIP | xERA | IP | Luck |
|---------|------|-----|-----|------|----|------|
| Bailey Ober | MIN | 4.50 | 3.42 | 3.84 | 26.0 | 0.1347 |
| Trevor Rogers | BAL | 4.45 | 3.68 | 3.10 | 28.3 | 0.1076 |
| Aaron Nola | PHI | 5.13 | 4.02 | 4.72 | 26.3 | 0.1012 |
| Garrett Crochet | BOS | 4.43 | 3.38 | 3.93 | 24.0 | 0.0944 |
| Logan Webb | SF | 4.32 | 3.75 | 4.13 | 25.0 | 0.0854 |
| Nathan Eovaldi | TEX | 5.40 | 4.38 | 4.06 | 26.7 | 0.0850 |
| Janson Junk | MIA | 4.44 | 3.71 | 3.43 | 26.3 | 0.0830 |
| Brandon Woodruff | MIL | 3.91 | 3.58 | 2.35 | 23.0 | 0.0820 |

### Pitcher Sell High (26):
Soriano, Wacha, Martinez, Holmes, Mcgreevy, Sugano, E.Rodriguez, S.Lugo,
M.Perez, King, Teng, G.Williams, Early, Kochanowicz, Imanaga, Freeland,
Messick, C.Phillips, D.Martin, F.Peralta, Vásquez, L.Gil, C.Patrick,
Chandler, G.Marquez, Wrobleski

### Relievers — Dormant but watch (cross 15 IP threshold to fire):
- Adrián Morejón: ERA 8.03, FIP 2.47 — massive gap, verify xERA before calling buy
- Camilo Doval: ERA 8.59, FIP 4.81
- Taylor Rogers: ERA 5.62, FIP 2.79
NOTE: All score Neutral now (< 15 IP confidence threshold — intentional). Need xERA
confirmed before article call on any of these.

### Hitter Signals (April 26 — post Version D additive modifiers):
Signal counts (416 hitters, dry-run with additive modifiers):
- Buy low: 54 | Slight buy: 12 | Neutral: 288 | Slight sell: 28 | Sell high: 34
NOTE: Run score_luck.py --write after next pipeline update to get live counts.

Slight buy survivors pass 0.100/0.030/0.380 gates + Version D penalty cap.
Top buy-low hitters (from projections): Ramirez, Herrera, Seager, Pasquantino,
Delauter, Bohm, Machado, Henderson, Acuna, Friedl

---

## SCORE_VALUE.PY — LAYER 3 (Trade Value Engine)

### Architecture (4 layers):
1. Signal Model → luck_score, verdict, tier (Layer 1 — DO NOT TOUCH)
2. Projection Engine → proj_avg, proj_hr, proj_rbi (Layer 2)
3. Value Engine → league1_value, rank (Layer 3 — score_value.py)
4. Trade Analyzer → trade verdict (Layer 4)

### Fixes Applied April 24, 2026:
- Fix A: TRM floor narrowed 0.40→0.75
- Fix B: Exponential CQS-dampened luck adjustment
- Fix C: AVG liability penalty (proj_avg <.220 — LOAD-BEARING, confirmed by ablation C)
- Fix D: Sanchez Test + Invariant checks on every --write
- Fix E: Availability penalty fix (Will Smith/Realmuto/Rutschman)
- Fix F: Ben Rice C eligibility added to player_positions.json
- Fix G: 11 career_quality.json records corrected
- Fix H: Dingler small-sample PA confidence factor

### Fix Applied April 25, 2026:
- Fix I: Barrel rate regression — PA-weighted blend toward league mean
  LG_BARREL=0.066, BARREL_PA_STAB=200 (weight = PA / (PA + 200))
  At 95 PA: weight 0.32 → small samples blend heavily toward 6.6% league avg
  Also fixed indentation error from prior session (code was at module level, not inside _compute_hitter_projections())
  Note: ESV barely changed for Rice (17.815→17.759) because R/RBI use xwOBA directly, not barrel. Barrel only affects HR_proj.

### Ablation Results (April 24 baseline):
- A: TRM removed → Raleigh rank 2, Sanchez 21 — PASS
- B: Luck removed → Rice→Langeliers→Baldwin→Herrera→Raleigh→Contreras — PASS
- C: AVG penalty removed → Sanchez jumps rank ~4 (confirms load-bearing) — PASS
- D: CQS floors removed → Raleigh 66→4.6, Rutschman/Diaz both drop to ~0 — PASS

NOTE: Raleigh's natural value without floor is only 4.6 — rank 2 is floor-driven.
Monitor as 2026 stats accumulate throughout season.

---

## PERMANENT MODEL VALIDATION ANCHORS

Run after EVERY score_value.py --write. All must PASS before shipping.

SHOULD ALWAYS BE NEAR TOP:
- Yordan Alvarez: top 20 overall (current: rank 13 ✓)
- Cal Raleigh: top 3 catchers (current: rank 4 — RELAXED to top-4 until catcher PA > 150)
  Root cause: Ben Rice .507 xwOBA at 95 PA inflates R/RBI projections, pushing him to #1.
  Raleigh natural ESV ~4.7 (xwOBA .336 + AVG .186 liability); rank 2 is floor-driven (CQS=80.2).
  Re-tighten invariant to top-3 in mid-May 2026 when catcher PA stabilize above 150.
- Drake Baldwin: top 5 catchers (current: rank 5 ✓)
- William Contreras: top 8 catchers (current: rank 6 ✓)

THE SANCHEZ TEST:
- Gary Sanchez: rank 21+ catchers (current: rank 21 ✓)
- IF Sanchez appears in top 15 catchers → STOP, something is broken
- The AVG penalty (.188 proj AVG) is load-bearing for keeping him down

---

## PIPELINE SCRIPTS (current as of April 24)

| Script | Purpose |
|--------|---------|
| score_luck.py | Hitter luck scoring (Layer 1) |
| score_pitcher_luck.py | Pitcher luck scoring (Layer 1, v2.0 split architecture) |
| stat_projections.py | Rest-of-season projections (794 players, 19 cols) |
| generate_projections.py | Runs projection pipeline |
| score_value.py | Trade values and rankings (Layer 3) |
| trade_analyzer.py | Trade verdicts v2 (Layer 4) |
| fetch_ownership.py | Live ESPN ownership (3,795 players) |
| fetch_prior_teams.py | 2025 team assignments for park change detection |
| validate_formulas.py | 37/37 PASS formula suite |
| export_signal_board.py | Excel signal board with ownership data |
| run_pipeline.py | Full pipeline runner |
| backtest_pitcher_composite.py | Full pitcher composite backtest (Versions A-E) |
| build_pitcher_stuff_baselines.py | Stuff quality career data builder |
| _pitcher_tier_audit.py | ERA-FIP backtest runner |
| generate_backtest_report.py | Substack table formatter |
| build_pitcher_pitch_mix.py | Pitch mix evolution data builder (2026 current) |
| build_hitter_career_k_pull.py | K%/pull rate career baseline builder (v4_april CSVs) |
| build_pitch_mix_delta.py | Phase 2 pitch mix delta signals (velo + RV flags) |
| build_pitcher_phase2_baselines.py | Career velo/RV baselines from parquets + arsenal stats |
| backtest_pitcher_pitch_mix.py | Version E/F/G pitch mix backtest |

### Key data files:
- data/projections_2026.csv — 794 players, 19 columns
- data/player_ownership_2026.csv — 3,795 players, live ESPN
- data/prior_teams_2025.json — 998 players, 2025 team assignments
- data/player_values.json — 773 players, rebuilt by score_value.py
- data/career_quality.json — CQS floors (11 records fixed April 24)
- data/backtest_composite_summary.csv — full pitcher ablation results
- data/pitcher_career_babip.json — career BABIP/HH%/barrel baselines
- data/pitcher_career_stuff.json — SwStr%/velo/spin baselines (display only)
- data/pitcher_career_csw.json — CSW career baselines (611 pitchers)
- data/pitcher_stuff_current_2026.csv — current season stuff metrics
- data/pitcher_career_pitch_mix.json — 2025 arsenal baseline (318 pitchers)
- data/pitcher_current_pitch_mix.json — 2026 current pitch mix (459 pitchers)
- data/pitcher_arsenal_rv_allyears.csv — 15,947 rows, run_value_per_100 per pitch type, 2022-2026
- data/pitcher_career_velo_per_pitch.json — career avg velo per pitch type (800 pitchers)
- data/pitcher_career_arsenal_rv.json — career avg rv/100 per pitch type (1,252 pitchers)
- data/pitcher_arsenal_rv_2026.json — current 2026 rv/100 per pitch type (514 pitchers)
- data/pitcher_pitch_mix_delta.json — Phase 2 pitch mix delta signals (251 pitchers)
- data/hitter_career_k_pull.json — K%/pull rate baselines (643 career, 415 current, 327 with deltas)
- data/hitter_career_discipline.json — chase rate baselines (672 batters)
- data/hitter_career_sprint.json — sprint speed baselines (849 players)
- data/hitter_career_platoon.json — career platoon baselines (489 batters) — built April 26
  Fields: career_gap_woba, career_gap_xwoba, stand, career_pa_same/opp; mean gap=-0.019
  Source: pitcher_statcast_april_{2022-2025}.parquet + pitcher_statcast_mayjuly_2024.parquet
- data/contract_year_2026.csv — contract year flags (empty — needs manual curation)
- data/yordan_tracker.csv — weekly Yordan wOBA/xwOBA tracker
- data/trade_history.csv — CLI trade log
- data/snapshots/pitcher_luck_scores_april_2026.csv — April 23 snapshot
- career_lessons_database.html — 88 career concepts, open in browser

---

## DASHBOARD STATUS (April 24, 2026) — ALL 7 FIXES COMPLETE ✅

Fix 1: View Toggle ✅ — Two-button [Simple][Advanced] always visible, active highlighted blue
Fix 2: Signal Filter Buttons ✅ — Pill row with live counts on Hitters + Pitchers tabs
Fix 3: Park Change Labels ✅ — ⚠ orange badge in Simple + Advanced View (43 players flagged)
Fix 4: Simple View Redesign ✅ — 3-column: Player | Signal | Why (120-char truncated)
Fix 5: Pitcher Ownership ✅ — 374/380 pitchers matched to ESPN ownership data
Fix 6: IL Status Note ✅ — Yellow banner "⚠ IL status not yet integrated"
Fix 7: Trade Search ✅ — normalizeName() handles accents, end-to-end verified

### Trade Analyzer (dashboard tab):
- Two sub-modes: Trade Analyzer (default) | Player Rankings
- Multi-player trades (1-4 per side), position scarcity, trajectory discounts
- League config: data/league_config.json (--setup flag)
- Search: min 2 chars, accent normalization, top 8 results
- Verdict thresholds: ≥75% Strong | ≥60% Favorable | ≥40% Neutral | ≥25% Unfavorable | <25% Avoid
- Known limitations: R/RBI lineup-dependent, no trade history in dashboard (CLI only)
- Parking lot: trade history in dashboard, partner roster view, category need weighting

### Park Changes (43 players flagged):
Ke'Bryan Hayes, Josh Lowe, Pete Alonso, José Caballero, Brandon Nimmo + 38 others
Badge shows: "Park change (OLD→NEW) — career baseline less reliable"

---

## ARTICLE #1 — PUBLISHED

**Title:** Fantasy Baseball: Using Seven Layers of Statcast to Predict Buying/Selling Signals
**URL:** https://open.substack.com/pub/thesignalfantasy/p/fantasy-baseball-using-seven-layers
**Published:** April 22, 2026 — track record clock started

Players featured:
- BUY LOW HITTERS: Pasquantino, Yordan Álvarez, Trent Grisham
- SELL HIGH HITTERS: Oneil Cruz, Jordan Walker
- BUY LOW PITCHERS: Luzardo, Bradish
- SELL HIGH PITCHERS: Wacha, Gavin Williams
- BONUS: Garrett Mitchell sell-high (BABIP .538)

Known edits still needed:
- Fix "Without I'm proud to say" → "I'm proud to say"
- Verify Cruz "hardest ever hit ball in Statcast era" claim before promoting

---

## WEEK 2 ARTICLE — PLANNED

**Title:** "Before the Regression Hits"
**Publish target:** Wednesday April 29, 2026
**Length target:** 1,200-1,500 words

### Structure:
1. Opening — Week 1 accountability (3-4 sentences)
2. Yordan Tracker — Week 1: wOBA .518, xwOBA .603, luck 0.288, Buy low
3. Lead: Corey Seager buy low (luck +0.470, 91% owned)
4. Feature: Dillon Dingler buy low
   - Reference April 24 tweet as timestamp
   - xwOBA .477 (3rd in MLB — behind only Yordan/Trout)
   - Barrel rate 19.6% (96th percentile)
   - BABIP .264 vs career .312
   - CBS current #6, consensus #17
   - 72% owned = available in most 12-team leagues
   - Small sample caveat (82 PA) — be honest
5. Sell high (TBD — pull from dashboard, needs 60%+ ownership)
6. NEW: Slight signals introduction
   - Slight buy hitter: Bo Bichette (BABIP .282 vs career .341)
   - Slight sell hitter: Zach Neto (BABIP .327 vs career .297)
   - Slight buy pitcher: Kevin Gausman (ERA 2.83, FIP 2.21)
   - Slight sell pitcher: Taj Bradley (ERA 1.30, xERA 3.02, evolution score 4)
7. Pitcher model v2.0 update (split architecture, evolution detector)
8. Honorable Mentions
9. Closing + Week 3 tease

### Dingler research (April 24):
- MLB Trade Rumors: full piece, xwOBA 3rd in MLB
- RotoBaller: "must-add, 96th percentile barrel/HH rate"
- CBS: currently #6 actual stats, #17 consensus
- 72% owned ESPN

---

## OWNERSHIP CONTEXT FRAMEWORK

>87%:  Owned in ALL leagues — no caveat, pure trade signal
58-87%: Available in most 12-team leagues — "waiver wire in 12-team leagues"
20-58%: Available in standard 12-team leagues — "waiver wire in standard leagues"
11-20%: Available in 14-team+ leagues — "deeper league pickup"
<11%:  Available in virtually all leagues — "universal waiver wire"
<5%:   "dynasty / speculative only"

Key thresholds: 58% = 10-team | 20% = 12-team | 11% = 14-team

Two questions before publishing any call:
Q1: Owned in standard 12-team? (>58% = yes) → no format caveat needed
Q2: If not, what format does he matter in? → use tiers above

Applied examples: Seager 91% → no caveat | Dingler 72% → "most 12-team leagues"

---

## ARTICLE PUBLISHING FRAMEWORK

### is_article_worthy() — Two-stage filter (not yet coded, manual for now):
Stage 1: Is the signal statistically real? (luck model)
Stage 2: Is the player important enough that acting on it moves the needle?

SELL HIGH requires: ownership >58% OR fp_rank <150
BUY LOW requires: ownership >10% minimum + projected improvement meaningful

---

## PARKING LOT — PRIORITIZED (updated April 28, 2026)

### TIER 1 — Do immediately after Week 2 publishes:
- **Weekly tracker mechanism classifier** — HIGHEST PRIORITY. Implement wOBA vs xwOBA decomposition
  in weekly_update.py. Same luck score movement = two opposite meanings (results declining vs contact
  improving). Mechanism values: Normalizing | Re-evaluate | Confirmed | Refuted | Watch.
  This is the content engine for the entire May-August publishing schedule.
- **April Big Board** — Consolidated view of all April calls, current status, model expectations.
  Publish as Week 3 content. The track record proof-of-work document.

### TIER 2 — This week:
- **Pitcher Slight Buy sensitivity analysis** — n=4 historically too thin to validate.
  Ablation test ERA floor (4.00→3.75?), luck score window width, IP threshold independently.
- **is_article_worthy() gate** — filter signals worth featuring from borderline cases.

### RESEARCH AGENDA (post-2026 season):
- Worry Index sensitivity: validate WORRY_WOBA_GAP=0.040 / WORRY_LUCK_BAND=0.085 after full season
- Financial motivation backtest: cohort × signal accuracy when Spotrac Phase 2 populated
- Elite player ascending theory: age 27-31, final year of $200M+ deal — lift vs. baseline?
- In-season signal validation: 2026 is first Track 2 data collection year; validate for 2027
- Age-weighted chase rate calibration: H_CHASE_AGE_WEIGHT values are priors, not empirical (mid-2027)

### TRADE TOOL FOUNDATION:
- CBS reverse engineering: linear regression on end-of-season rankings 2022-2024, R² >= 0.90
- CBS coefficient ratios as exchange rates: same weights for rankings AND trade analyzer (one source)
- Replacement level calculator: N = roster spots × league size
- Fantasy points conversion engine: projected stats × CBS-derived point values
- League settings intake UI: roster construction, scoring format, categories
- Positional scarcity cap: 15-spot rule, never let scarcity flip a tier

### CONTENT PIPELINE:
- "Why April Signals Matter Most" article: publish mid-May (paid tier anchor)
- "How I Built This in 10 Days with AI" article: publish after 6-8 weeks live track record
- Live 2026 Accuracy Tracker: paid tier dashboard, updates weekly (build mid-June 2026)
- Spotrac Phase 2: historical 2022-2024 contract data via Wayback for financial motivation backtest

---

### TRADE TOOL KNOWN ISSUES (from stress testing April 25):

**Issue 1 — Smell test failure: Skenes for Ben Rice returns "Favorable"**
- Skenes (Slight Sell, ERA 0.95, FIP 2.56) given away for Rice (Sell High, C-NYY)
- Tool returned "Favorable — slight edge in your favor" for getting Rice
- This should be rejected 10/10 times — Skenes is far more valuable
- Root cause likely: positional scarcity of C overweighting Rice's value,
  OR New Pitcher career discount on Skenes suppressing his value too aggressively,
  OR sell signals being treated as equivalent regardless of underlying quality
- Fix needed: value gap check — if player being given away is top-20 overall,
  verdict should never be Favorable for the other side regardless of signals

**Issue 2 — Pitcher net stats direction is misleading**
- Giving away Skenes shows ERA -1.50 and WHIP -0.76 as positive changes
- Technically correct (you lose his stats) but misleading in context
- Tool doesn't account for replacement-level pitcher you'd start instead
- Real net change should factor in: "what pitcher replaces Skenes in your lineup?"
- Fix needed: replacement-level baseline for pitchers in net stats calculation
- This is a fundamental trade tool architecture issue (Layer 4 — parking lot B2)

**Issue 3 — Architectural principle: signals should inform stats, not verdicts**
- Current behavior: signal tier (Buy Low/Sell High) feeds directly into trade verdict logic
  ("giving away a buy low for a sell high" influences the verdict independently)
- Correct behavior: signal feeds into projected stats ONLY (adjusts ERA, K, wOBA projections)
  Those adjusted projections feed into trade value calculation
  Trade verdict = Side A total projected value vs Side B total projected value. Full stop.
- Signal badge should display informationally only — not independently weight the verdict
- Think of it as two separate tools sharing data:
  Tool 1 (Signal Model): "Here are luck-adjusted projected stats"
  Tool 2 (Trade Tool): "Here is total value on each side based on those stats"
  Tool 2 is informed by Tool 1 in the background but doesn't explicitly reference signals
- This fixes the Skenes problem: his Slight Sell label shouldn't suppress his trade value
  His value comes from his projected ERA 1.50 / WHIP 0.76 / K 197 — that's elite regardless of signal
- Implementation: remove signal-tier weighting from verdict calculation in trade_analyzer.py
  Keep signal badges as display-only information for the user
  Verdict threshold logic should reference projected value scores only

### CRITICAL BUG — Fix before trade tool testing:
**Trade tool search click not registering**
- Symptom: Typing filters correctly (autocomplete works) but clicking result does nothing
- Player does not get added to GIVING/GETTING panel after clicking
- Likely cause: onClick handler not firing, or event listener not attached to result items
- Fix location: dashboard.html — taSearchPlayers() or result rendering function
- Test to verify fix: Search "Luzardo" → click result → confirm appears in GIVING panel
- Discovered: April 24 during first live trade tool test

### TIER 1 — Do before/during trade tool testing tonight:
1. **Visual dashboard verification** (YOU — not Claude Code)
   Open localhost:8000, confirm all 7 fixes render correctly
2. **Trade tool end-to-end test** (YOU — tonight)
   Try 5-10 real trades, document where verdicts feel wrong

### TIER 2 — High leverage, this week:
3. **Backtest audit log** — RUNNING IN CLAUDE CODE (April 24)
   Row-level export: backtest_audit_hitters.csv + backtest_audit_pitchers.csv
   Commercialization asset + credibility proof
4. **Slight Buy pitcher sensitivity analysis** — n=4 historically is too thin to validate
   The luck score window between Neutral and Slight Buy may be too narrow for April data
   Gates to test: ERA floor (4.00 → 3.75?), luck score window width, IP threshold
   Goal: generate enough historical signals to validate the tier statistically
   Method: ablation test each gate individually, measure signal count AND accuracy
5. **is_article_worthy() gate** — build after Week 2 publishes Wednesday
6. **Current rank integration** — fp_rank shows preseason, not in-season
   Affects trade tool verdict quality directly

### TIER 3 — Important, not blocking:
6. **Nola/Rogers ERA gap fix** — ~1 run miscalibration, specific archetype
7. **2026 live prediction log** — CSV timestamping every signal call going forward
   Season-end track record for commercialization. ~30 min build.
8. **Post-blend AVG floor** — 26 fringe hitters projecting below .195
9. **Extended scoring categories** — OBP/SLG/TB/QS for non-standard leagues

### TIER 4 — Week 3-4+:
10. **Trade analyzer B2 — roster context module**
    Knows your roster needs, not just raw player values. Big effort, big reward.
11. **IL badge integration** — banner caveat covers for now
12. **Hitter evolution detector** — launch angle >5°, pull rate >10%, sprint speed
13. **CSW buy-low-only ablation** — strong signal, kept in production April 24
14. **Chase rate sell-side expanded testing**
15. **Multi-year pitcher backtest refinement**
16. **Recent game trend line display** — post-launch UI polish

### NEW SIGNAL LAYERS — Added April 27:
- **Worry Index / Confidence Meter** — flags where model SILENCE is meaningful.
  CONCERN (fp_rank<50, wOBA 40+pts below 3yr xwOBA, no luck signal): "struggle may be real"
  BREAKOUT (fp_rank>100, wOBA 40+pts above 3yr xwOBA, no regression signal): "breakout may be real"
  Display-only output columns (worry_flag, breakout_flag, worry_label). No model weight.
  Current example: Pete Crow-Armstrong (luck -0.133, Slight Sell) — concern flag.

### TWO-TRACK IN-SEASON SIGNAL SYSTEM (documented April 27):
Track 1 — April Signals (PRODUCTION): validated 86.1%/89.7% — the published signals.
Track 2 — In-Season Rolling (HYPOTHESIS): weekly_update.py tracker, no validated accuracy.
Rule: NEVER present Track 2 with equal authority to Track 1.
Article framing for Track 2: "data moving in the right direction" not "new signal."
Publishing cadence: Tuesday nights publish / Monday production run (run_pipeline.py → weekly_update.py → --report).

### TIER 5 — Future:
17. **Football product** — Year 2-3, nflfastR
18. **Podcast pitch** — live calls format, after stable publishing rhythm
19. **Career playbook document** — after stable publishing rhythm
20. **CBS Coefficient Ratios as Trade Value Exchange Rates** — Use the same CBS regression
    coefficients (HR, R, RBI, SB, AVG, ERA, WHIP, K, W, SV) as one weighting system flowing
    through BOTH the ranking engine AND the trade analyzer. One source of truth for category value:
    if HR is worth 3× SB in CBS rankings, that same ratio should determine whether a trade is fair.
    Closes the gap where the two tools could use different implicit weights and contradict each other.
    Implementation: expose CBS coefficients in config.py, import into score_value.py + trade_analyzer.py.
    Prerequisite: complete CBS Rankings Reverse Engineering experiment to get empirically validated
    coefficients before wiring in — R² >= 0.90 target.

### NEW VARIABLES — DETAILED REASONING (April 25):

**Why these variables matter for EXPECTED STATS (not just signals):**

**1. Pitch mix evolution (pitchers) — Priority #1**
Signal impact: Medium-High
Expected stats impact: HIGH — this is the key insight
- A 2pp SwStr% improvement from a new pitch = ~1.5 K/9 projected
- Over 100 remaining IP = ~17 more projected strikeouts
- K is a primary trade value driver for pitchers
- Current model knows CURRENT stuff quality but NOT whether it changed
- A pitcher adding a sweeper mid-season is fundamentally different
  from one losing velocity — current model treats them identically
- Implementation: pitch_mix_delta (current % - career %) already
  computable from existing files — lowest complexity of all three
- Data: pitcher_career_pitch_mix.json + pitcher_current_pitch_mix.json
  both exist — NO new fetch needed

**2. K% trend (hitters) — Priority #2**
Signal impact: Medium
Expected stats impact: HIGH
- K% change directly affects projected AVG and wOBA
- A hitter dropping K% from 28% to 22% while maintaining xwOBA
  projects .015-.020 wOBA improvement — meaningful trade value shift
- Current model uses current K% as a static gate (plate discipline layer)
  but doesn't capture DIRECTION of change
- Example: two hitters with identical current K% of 24% — one declining
  from 30% (improving) vs one rising from 18% (declining) — should
  project very differently but currently score identically
- Data: current 2026 K% EXISTS in hitters_statcast.csv
  Career K% baseline NEEDS: build hitter_career_k_pull.json
  using existing calc_k_rate() function in codebase

**3. Pull rate trend (hitters) — Priority #3**
Signal impact: Medium
Expected stats impact: Medium-High
- Pull rate increase correlates strongly with HR rate increase
- A 5pp pull rate jump historically = +3-5 projected HR
- HR is highest trade value category in roto after AVG
- Early breakout signal — pull rate changes often precede surface
  stat improvement by 2-4 weeks (market hasn't priced it in yet)
- Hard pull rate specifically (pulled balls with high exit velo)
  separates real power breakouts from fluke pull singles
- Data: pull_percent EXISTS in hitters_statcast.csv
  Career pull baseline NEEDS: same build as K% —
  add pull_rate to hitter_career_k_pull.json

**Why build order matters:**
Pitch mix first — pitcher side, completely separate infrastructure,
lowest complexity, can run while hitter baseline JSON is being built.
K% + pull rate share the same career baseline JSON build step —
build that once, then implement both signals on top of it.
Never add multiple variables simultaneously — can't attribute improvement.

**The 2025 OOS guard rail:**
Every new variable must improve OR not hurt 2025 OOS accuracy:
- Pitcher Buy Low current baseline: 85.7% OOS
- Hitter overall current baseline: ~88.1%
If any variable hurts 2025 OOS → revert immediately, no exceptions.

Build order and process for each new variable:
1. Add variable individually
2. Backtest isolated (2022-2024 in-sample)
3. Validate against 2025 out-of-sample (MUST improve or stay flat)
4. Ablation test confirms contribution
5. validate_formulas.py 37/37 PASS
6. Update handoff doc with new validated numbers

Build order:
1. Pitch mix evolution (pitcher side) — standalone
2. K% trend (hitter side) — standalone
3. Pull rate trend (hitter side) — add on top of K% trend, ablation both
4. Combined hitter backtest — confirms both work together

Exception: K% trend + pull rate can share one backtest run since both
are hitter-side, but MUST ablation test each independently to confirm
individual contribution.

Gate: 2025 OOS accuracy must not decline vs current baseline:
- Pitcher Buy Low current: 85.7% OOS (post ERA floor fix)
- Hitter overall current: ~88.1%
If any new variable hurts 2025 OOS → revert immediately

Diagnostic prompt results: data/new_variables_diagnostic.md ✅ COMPLETE

DIAGNOSTIC FINDINGS — what we have vs need:

**Pitch mix evolution:** LOW complexity
- career baseline EXISTS (pitcher_career_pitch_mix.json)
- current 2026 EXISTS (pitcher_current_pitch_mix.json)
- delta computable from existing files — NO new fetch needed
- Implementation: add pitch_mix_delta to score_pitcher_luck.py directly

**K% trend (hitters):** LOW-MEDIUM complexity
- career K% baseline PARTIAL (hitter_career_discipline.json has chase rate but not K%)
- current 2026 K% EXISTS in hitters_statcast.csv
- Need: build data/hitter_career_k_pull.json from backtest_cache using
  existing calc_k_rate() function — already exists in codebase

**Pull rate trend (hitters):** LOW-MEDIUM complexity
- career pull rate PARTIAL — same as K%, needs new baseline JSON
- current 2026 pull rate EXISTS in hitters_statcast.csv (pull_percent column)
- Need: same build as K% — add pull rate to hitter_career_k_pull.json

**CRITICAL DATA GAP — Per-pitch velocity (confirmed April 25):**
pitcher_career_pitch_mix.json has only career_primary_velo (ONE float, overall).
pitcher_current_pitch_mix.json has curr_velo: {FF: x, SL: y} (per-pitch).
Comparing them yields nonsense (Sale's SL 78.2 vs career_primary_velo 94.5 = -16.3 mph).
Phase 1 SKIPS per-pitch velo delta. Phase 2 requires pybaseball fetch.

**CRITICAL NOISE ISSUE — New pitch detection (confirmed April 25):**
238/251 overlap pitchers show "new" pitch types (ST sweeper, CH, SL etc.).
These are Statcast relabeling artifacts, NOT true new pitch additions.
new_pitch_flag=False until Phase 2 pybaseball fetch resolves label consistency.

**PHASE 1 BUILD — ✅ COMPLETE (April 25, 2026):**
build_pitch_mix_delta.py: SwStr-based abandonment + effectiveness flags.
Wired into score_pitcher_luck.py as _apply_pitch_mix() modifier.
Backtest result: Version F = verdict-neutral (0.0pp delta vs Version E).
Status: INFORMATIONAL LAYER only — display in dashboard, does not change verdicts.

**PHASE 2 BUILD — ✅ COMPLETE (April 25, 2026):**
build_pitcher_phase2_baselines.py: career velo from parquets (800 pitchers), career rv/100 from arsenal stats (1,252 pitchers).
build_pitch_mix_delta.py (Phase 2): 6-flag system — abandonment, velo_drop, rv_degrade, effectiveness, velo_gain, rv_improve.
Backtest result: Version G = verdict-neutral (0.0pp delta vs Version E, OOS PASS ✓).
Coverage 2026: 234 pitchers. Coverage by year: 73% velo, 94% RV.
Architecture conclusion: pitch mix is INFORMATIONAL layer. Verdict changes require threshold-crossing buys, which the ×0.729 stacking can achieve in theory but rarely in practice.

**NEXT CLAUDE CODE PROMPTS (in order):**
1. ✅ Build data/pitcher_pitch_mix_delta.json + wire signal into score_pitcher_luck.py (Phase 1)
2. ✅ Phase 2 pybaseball fetch + career velo/RV baselines + Version G backtest
3. ✅ Build data/hitter_career_k_pull.json + wire K%/pull modifier into score_luck.py
4. Run hitter K%/pull backtest — verify whether ×0.90/×0.95 multipliers improve OOS accuracy
5. Build data/hitter_career_pull_add.json — flag pull rate INCREASES (potential power breakouts)
   (currently only flags drops; increases are also signal-worthy for buy side)

**✅ INVARIANT FLAG — RESOLVED April 25:**
Cal Raleigh rank 4 diagnosed: Ben Rice .507 xwOBA (95 PA) inflating R/RBI.
Invariant relaxed to top-4 in code. Re-tighten mid-May 2026. See PERMANENT ANCHORS section.

| Rank | Variable | Signal impact | Expected stats impact | Trade tool impact |
|------|----------|--------------|----------------------|-------------------|
| 1 | Pitch mix evolution (pitchers) | Medium-High | High — K/9 projection | High |
| 2 | K% trend (hitters) | Medium | High — AVG/wOBA projection | High |
| 3 | Pull rate trend (hitters) | Medium | Medium-High — HR projection | Medium-High |
| 4 | Catcher framing (pitchers) | Medium | Medium — ERA ±0.20-0.35 | Medium |
| 4 | Leverage index (relievers) | Medium | Medium-High — SV+H projection | High |
| 6 | First pitch strike % (pitchers) | Low-Medium | Medium — WHIP/BB projection | Low-Medium |
| 7 | Opponent quality | Low | Low | Low |

Key insight: pitch mix evolution and K% trend have outsized trade tool impact
because they directly change projected counting stats (K, AVG, wOBA, HR)
not just the luck score signal. A 2pp SwStr% improvement = ~1.5 K/9 = ~17 projected Ks over 100 IP.

---

## COMPLETED PARKING LOT ITEMS (reference)

- Dashboard 7-fix audit: COMPLETE ✅ (April 24)
- Pitcher ownership ESPN fetch: COMPLETE ✅ (374/380 matched)
- Reliever FIP fix: COMPLETE ✅ (April 24) — was logic error not FanGraphs block
  110 relievers now have FIP via fip_sc_all fallback; score Neutral until 15 IP
- Hitter HH% denominator fix: COMPLETE (296/414 matched, 118 use default 0.370)
- Platoon adjustment: COMPLETE (Layer 7 confidence modifier, live in production)
- Threshold recalibration: COMPLETE (Option 3 in score_luck.py)
- Yordan tracker: COMPLETE (automated in run_pipeline.py → data/yordan_tracker.csv)
- LOB% confluence flag: COMPLETE (display column, 6 buy confirms)
- Multi-year April pattern flag: COMPLETE (4 buy lows confirmed)
- Slight buy accuracy investigation: COMPLETE (hitter xwOBA gate + pitcher ERA gate)
- New signal ablation: COMPLETE (chase sell-only KEPT, CSW buy-only KEPT, sprint REVERTED)
- Follow-up ablation: COMPLETE (all 3 re-tested with root-cause fixes April 24)
- This Is Actually Bad: COMPLETE (9 Confirmed, 7 Monitor April 24)
- This Is Real: COMPLETE (27 Confirmed, 34 Monitor April 23)
- Live ownership data: COMPLETE (3,795 players, ESPN public API)
- Signal board: COMPLETE (4-sheet Excel, auto-runs in pipeline)
- Stat projection engine v2: COMPLETE (6 fixes, 37/37 PASS)
- Pitcher evolution detector: COMPLETE (6-factor, Bradley evolution_score=4)
- Formula validation suite: COMPLETE (37/37 PASS)
- Trade analyzer v2: COMPLETE (multi-player, scarcity, trajectory, league config)
- Dashboard syntax error: DIAGNOSED — no actual error, was transient state
- Park change detection: COMPLETE (998 players, 43 flagged)
- Score_value.py fixes A-H: COMPLETE (all 8 fixes applied April 24)
- Score_value.py Fix I (barrel regression): COMPLETE (April 25 — LG_BARREL=0.066, BARREL_PA_STAB=200)
- Pitch mix Phase 1 (abandonment + effectiveness): COMPLETE (April 25 — Version F, verdict-neutral)
- Pitch mix Phase 2 (per-pitch velo + RV): COMPLETE (April 25 — Version G, 94.0%/87.0% OOS PASS)
- Cal Raleigh invariant relaxed: COMPLETE (April 25 — top-4 until catcher PA > 150, mid-May re-tighten)
- Pitcher ERA floor Buy Low 3.50→3.75: COMPLETE (April 25 — score_pitcher_luck.py line ~967)
- Slight Buy hitter threshold recalibration: COMPLETE (April 25 — 0.100 floor, 0.030 gap gate, 0.380 ceiling)
- K%/pull rate evolution modifier: COMPLETE (April 25 — score_luck.py wired, 37/37 PASS)
- Additive modifier architecture Version D: COMPLETE (April 26 — train +1.7pp→86.1%, OOS +0.3pp→89.7%, 42 verdict changes)
  config.py: H_KP_K_PENALTY=0.010, H_KP_PULL_PENALTY=0.008, H_HH_PENALTY=0.012, H_SPEED_PENALTY=0.010, H_CHASE_PENALTY=0.008, H_MAX_COMBINED_PEN=0.040
  backtest_multi_year_v7.py: _apply_additive_modifiers(), _print_sensitivity_sweep(), _print_abcd_comparison() added
  score_luck.py: _buy_penalty accumulator, combined application block, cap at 0.040
- Platoon career baseline fix: COMPLETE (April 26 — career gap replaces static -0.018/-0.012, PA min 15→30, xwOBA splits added)
  build_hitter_career_platoon.py: new builder from pitcher_statcast parquets
  data/hitter_career_platoon.json: 489 batters, mean career gap=-0.019
  score_luck.py: _build_platoon_splits() loads xwOBA; _platoon_modifier() uses gap_delta vs career
  19 modifier result changes in 2026 data vs old static approach
- Contract year cohort framework: COMPLETE (April 26 — display-only, 5-cohort classification)
  score_luck.py: _assign_cohort() function; contract_cohort column in CSV output
  data/contract_year_2026.csv: infrastructure ready, needs manual data curation
  All programmatic data sources exhausted and blocked (Spotrac 403, BRef 403, MLB API 404, Lahman salary-only)
- Financial motivation cohort redesign + Spotrac merge: COMPLETE (April 26-28)
  5 cohorts: 1=Payday, 2=Prove-It, 3=Secured($20M+,3+yr), 4=Post-Prime(33+), 5=Mid-Contract
  31 players loaded (13 manual + 18 Spotrac merge); new Cohort 3: Ramírez, Swanson, Bogaerts, Stanton, Olson, Nola, Yelich
  Distribution: 1-payday=160 | 3-secured=17 | 4-post-prime=58 | 5-mid-contract=163 | unknown=18
  merge_spotrac_contracts.py: new file; normalizes AAV, filters expired/pre-arb, MLBAM ID lookup from luck CSVs
- Pitcher additive modifier conversion (Version H): COMPLETE — VERDICT-NEUTRAL, NOT ADOPTED (April 27)
  All 3 bearish flag penalties calibrate to 0.0; buy sample n=21 too small; keep multiplicative ×0.90/×1.10
  backtest_pitcher_pitch_mix.py updated with sweep/comparison infrastructure
- Age-weighted chase rate modifier: COMPLETE (April 27 — score_luck.py + config.py)
  H_CHASE_AGE_WEIGHT_U25=0.40, H_CHASE_AGE_WEIGHT_26_27=0.70; 8 young players affected; 37/37 PASS
  Zero verdict impact at current scores; correctionally sound for future borderline cases
- Calls tracker built: COMPLETE (April 26 — data/calls_tracker.csv + weekly_update.py)
  169 players (127H, 42P); Week 1 baseline April 22; --update / --report pipeline ready
- Two-track in-season signal framework: COMPLETE (April 27 — documented in CLAUDE.md)
  Track 1 = April signals (validated, published); Track 2 = tracker (hypothesis only)
- Publishing cadence locked: COMPLETE (April 27 — Tuesday publish / Monday production run)
- Worry Index / Confidence Meter: BUILT (April 27 — score_luck.py display layer, 37/37 PASS)
  5 concern flags: Pete Alonso (fp17), Bo Bichette (fp14), Juan Soto (fp5), Rafael Devers (fp16), Willy Adames (fp25)
  0 breakout flags. Columns: worry_flag, breakout_flag, worry_label in luck_scores.csv
  Pete Crow-Armstrong excluded: luck=-0.133 (Slight Sell signal IS present), fp_rank=NaN in rankings file
- Cohort framework age-ordering bug fixed (April 27): _assign_cohort called before df["age"] was set → all "unknown"
  Moved apply() to after df["age"] = ... line; post-fix distribution: 1-payday=161, 3-secured=11, 4-post-prime=62, 5-mid-contract=164
- run_pipeline.py subprocess encoding fix (April 28): UnicodeDecodeError crash on Windows tqdm output
  Added encoding="utf-8", errors="replace" to Popen call; all 6 pipeline steps now complete cleanly; permanent fix
- Week 2 article generated (April 28): pipeline run + weekly_update.py --update + --report --top 15
  Lead: Corey Seager (wOBA .332/xwOBA .378/score +0.344, Buy Low)
  Feature: Dingler (xwOBA .459/gap+.105), Ramírez (fp7/score+0.483), Judge (fp1/score+0.282), Acuña (score+0.394)
  New Worry Index section: Devers (fp16, wOBA .241/xwOBA .265/3yr xwOBA .371 — real struggle, not luck)
  Yordan tracker: wOBA .510/xwOBA .595 consistent Week 1→2; Buy Low holding
  Pitcher buys: Luzardo (6.41 ERA/3.14 FIP), Joe Ryan (5.29/3.12), C.Sánchez (3.82/2.51)
  Tracker: all 169 calls show "too early" at 1 week — expected, significance thresholds not yet met
  Status: draft ready; PENDING Dustin review + Substack publish (Tuesday April 29 deadline)

---

## IMPORTANT DATA NOTES

- Both Max Muncys correctly disambiguated:
  Dodgers Muncy: ID 571970 (age 36) — slight sell
  A's Muncy: ID 691777 (age 24) — stronger sell
- Seager: wOBA .332/xwOBA .378/score +0.344 — Buy Low, Week 2 article lead ✓
- Dingler: wOBA .354/xwOBA .459/gap +.105/score +0.317 — Buy Low, Week 2 feature ✓
- Murakami: CWS (not ARI) — confirmed in pipeline
- Vásquez: spelled with accent (Randy Vásquez) in CSV
- Yordan Week 1→2: wOBA .510/xwOBA .595/score +0.227; Buy Low signal holding steady
- Worry Index active flags (April 28): Devers (fp16, wOBA .241/3yr xwOBA .371), Bichette (fp14), Adames (fp25), Alonso (fp17), Soto (fp5/42PA too early)
- Week 2 top pitcher buys: Luzardo (ERA 6.41/FIP 3.14), Joe Ryan (ERA 5.29/FIP 3.12), C.Sánchez (ERA 3.82/FIP 2.51)

---

## K/9 PROJECTION PIPELINE — HOW IT WORKS

Discovered during Luzardo pressure testing. 5-step pipeline for projecting strikeouts:

Step 1 — Current SwStr%:
swstr_rate = swinging_strikes / total_pitches (stored as decimal 0.110, NOT percent 11.0)

Step 2 — Career SwStr% baseline:
From pitcher_career_csw.json. swstr_gap = current - career.
Negative gap → evolution score -1 (trust career more)

Step 3 — K/9 translation (FIXED April 24):
WRONG (old): K/9 = SwStr% × 22.5 → produced K% not K/9
CORRECT: K/9 = SwStr% × 77.3
Derived: league avg 0.11 × X = 8.5 → X = 77.3
SWSTR_TO_K9 = 77.3 at line 52 in stat_projections.py ✅

Step 4 — Blend with career (at 27 IP, medium confidence):
Current weight 0.30, Career weight 0.70
Evolution detector adjusts weights up/down based on score

Step 5 — Luck multiplier + counting K:
Buy Low pitcher: K × 1.05 | Sell High: K × 0.95
Counting K = K% × projected_BF (IP × 4.3)

Key insight: Model is MORE conservative than naive projection.
"Luzardo's career says 24% K guy — we trust that more than 27 IP."
By June with 80+ IP, if SwStr% still shows poorly, model shifts weight.

Canary check: grep -n "77.3\|SWSTR_TO_K9" stat_projections.py | head -5
Expected: SWSTR_TO_K9 = 77.3 at line ~52 ✅

---

## BACKTEST STATUS & METHODOLOGY (April 24, 2026)

CRITICAL — Training/Test Split:
- Training/calibration: 2022-2024 data ONLY
- Out-of-sample validation: 2025 ONLY
- NEVER mix 2022-2024 into published accuracy claims — that's in-sample
- The 89.4% headline number uses 2025 out-of-sample data only

Validated headline numbers — Version D (from backtest_multi_year_v7.py — source of truth):
- Hitter (Version D, backtest v7): 86.1% train (n=187) / 89.7% OOS 2025 (n=87) | +17.9pp vs RTM
  Buy Low: 91.3% train / 96.0% OOS | Slight Buy: 73.5% train / 90.9% OOS
  Slight Sell: 89.3% train / 76.9% OOS | Sell High: 91.7% train / 100.0% OOS
- Pitcher (backtest v7, 2024 single-year): 85.7% overall | Buy Low 90.9% | Sell High 100.0%
- 2025 OOS: 89.7% hitters (never trained on this data — most trustworthy number for publishing)
- vs RTM: hitters +17.9pp OOS

Prior discrepancy RESOLVED (April 25-26):
- "~89.0% train / ~93.5% OOS" was production thresholds applied to backtest scores → 23 cases → invalid
- "42→9 slight buy signal reduction" from April 25 threshold recalibration: correct, gates working
- Pitcher Buy Low 68.2% from run_backtest_production.py was methodology error (train/test mixing)
  Authoritative numbers from backtest_multi_year_v7.py (hitters) and backtest_pitcher_composite.py (pitchers)

DO NOT mix 2022-2024 in-sample numbers into published accuracy claims.
Publish 2025 OOS numbers whenever possible — that's the honest track record.

Backtest scripts:
- backtest_audit_hitters_v2.csv — 729 rows, 383 in_eval=True (non-FLAT, non-Neutral) — AUTHORITATIVE hitter source
- backtest_composite_pitcher.csv — pitcher Version E results — AUTHORITATIVE pitcher source
- run_backtest_production.py — methodology under investigation, do not publish
- backtest_multi_year_v7.py — current active v7 script

Backtest scripts (in backtest/ folder after reorganization):
- run_backtest_production.py — new, methodology under investigation
- run_backtest_fresh.py — v7 logic backtest
- build_backtest_audit.py — row-level audit log builder
- backtest_multi_year_v7.py — current active v7 script
- extract_backtest_examples.py — example extractor
- backtest_pitcher_pitch_mix.py — Version E/F/G pitch mix comparison (root: project dir)

### PITCH MIX BACKTEST RESULTS (updated April 26-27, 2026):
| Version | Train 22-24 | OOS 2025 | vs RTM (train) | Architecture |
|---------|-------------|----------|----------------|-------------|
| E (baseline) | 94.0% (n=134) | 87.0% (n=46) | +24.0pp | no pitch mix |
| F (Phase 1 — SwStr) | 94.0% (n=134) | 87.0% (n=46) | +24.0pp | abandonment + effectiveness ×0.90/×1.10 |
| G (Phase 2 — velo+RV) | 94.0% (n=133) | 87.0% (n=46) | +24.0pp | 6-flag multiplicative |
| H (additive — April 27) | 94.0% (n=134) | 87.0% (n=46) | +24.0pp | additive penalties, all → 0.0 |

Version H result: VERDICT-NEUTRAL. All 3 bearish flag penalties calibrate to 0.0. Buy sample too small (n=21 train) for additive advantage. DECISION: Keep multiplicative ×0.90/×1.10 for pitchers.
OOS guard rail: PASS ✓ (H >= E - 0.005)
Architecture conclusion: pitch mix modifier is an INFORMATIONAL layer, not a verdict-mover
Additive approach works for hitters (n=211 train, 5 flags) but not pitchers (n=21 train buys)

---

## COMMERCIAL ROADMAP

- Paid tier ($10/month): activate after 200-500 free subscribers
- Trade analyzer public: Phase B (local only now) → beta after validation
- Podcast pitch: live calls format, accountability content
- Backtest audit log: commercialization credibility asset (building now)
- Football product: Year 2-3 using nflfastR

---

## CAREER LESSONS DATABASE

File: career_lessons_database.html
Concepts: 88 (through April 24, 2026)
Open in any browser — fully searchable by category

### New lessons from April 24 session (add to database):
- Metric Complementarity (FIP vs xERA — what each measures/misses)
- Construct Validity (TRM measured longevity not confidence)
- Ablation Testing a Value Model (ranking coherence vs accuracy delta)
- Invariant Testing (permanent anchors that catch subtle bugs)
- Asymmetric Category Damage (roto: .188 AVG actively hurts roster)
- Content Inventory Management (signals are scarce — ration them)
- Misdiagnosed Root Cause (FanGraphs "block" was actually a sampling filter)
- Load-Bearing Components (remove it, known-correct output breaks — that's the definition)
- Documentation Drift (multiple "handoff" docs diverge fast — one source of truth only)

- Measurement Validity (new backtest returned worse numbers — model was fine, evaluation script was wrong. Contact-only xERA vs all-PA xERA for K-heavy pitchers. Always check the ruler before concluding the thing you're measuring changed.)

### New lessons from April 26-27 session (add to database):
- Additive vs Multiplicative Penalties (multiplicative ×0.95 is verdict-neutral at standard tier gaps; additive flat penalties cross tier boundaries and produce real reclassifications. The constraint is the tier gap, not the multiplier magnitude.)
- Sensitivity Sweep Design (sweep each parameter independently over a grid, hold all others constant, maximize training accuracy, validate against OOS. Best values may be non-obvious — 0.012 for HH flag outperformed 0.010 and 0.014.)
- Career Baseline vs Static Average (comparing a player to their own historical norm is more powerful than comparing to a league average. Jazz Chisholm's -0.006 platoon gap is dramatic because his career is -0.093; the static -0.019 misses this entirely.)
- Data Source Exhaustion Documentation (when all programmatic routes are blocked, document the exact URL structure, failure mode, and column spec needed so the next engineer can build a targeted scraper. Don't just say "blocked" — say what you tried and what the data looks like.)
- Infrastructure-Ready Feature (build the plumbing even when data isn't available — contract_year_2026.csv header, _assign_cohort(), contract_cohort column. When data arrives, wiring takes minutes. Without the infrastructure, it takes hours.)
- Worry Index / Model Silence as Signal (absence of a luck signal is itself informative when combined with preseason expectation context. A struggling darling with no detected luck = worry. An outperforming surprise with no detected luck = potential breakout. The model's silence speaks.)
- Temporal Validity (April signals require validation separate from in-season rolling signals. Same metric, different context, different accuracy expectations. Never mix track records across different validation windows — they're measuring different things.)
- Content Flywheel Architecture (April calls → Big Board → rolling tracker → accountability audit forms a self-reinforcing loop. Week N article references Week N-1 calls, builds credibility, drives subscriptions that fund more tooling.)
- Financial Motivation vs Binary Flag (contract year = yes/no misses the magnitude of financial incentive. A player on a $2M prove-it deal has different motivation than one on a $10M one-year extension. The security gap — how far below market is their current deal — is the real variable.)
- Two-Path Luck Normalization (wOBA declining while xwOBA stays flat = BABIP luck depleting. xwOBA improving while wOBA lags = contact quality recovering. Both paths produce identical luck score movement but have different recovery timelines. Decompose when writing article analysis.)

### New lessons from April 25 session (add to database):
- Sensitivity Analysis (systematic parameter testing — vary one thing at a time, hold all else constant, measure signal count AND accuracy, use 2025 OOS as the guard rail)
- Measurement Validity (new backtest returned worse numbers — model was fine, evaluation script was wrong. Contact-only xERA vs all-PA xERA for K-heavy pitchers. Always check the ruler before concluding the thing you're measuring changed.)
- Build Order Discipline (add variables individually, backtest each, ablation confirm — never add multiple variables at once or you can't attribute the improvement)
- Signal vs Stats Impact (a new variable can have modest signal impact but large trade tool impact if it changes projected counting stats. Evaluate both dimensions separately.)
- Trade Tool Architecture (signals inform projected stats, not verdicts directly. The trade verdict is pure value comparison. Signal badge is display-only information.)
- Recovery Path Thinking (always know your path back before you need it — original threads, CC outputs, validated scripts. No problem is truly catastrophic with good documentation.)
- Documentation Drift (multiple "handoff" docs diverge fast — one source of truth only, overwrite at end of every session, never create "updated" suffix variants)
- PA-Weighted Mean Reversion (barrel rate, small samples: PA / (PA + 200) as blend weight. At 95 PA you trust current data only 32% — league average fills the rest. Prevents outlier small-sample projections from dominating trade values.)
- Data Architecture Audit Before Building (confirmed career_primary_velo is ONE float, not per-pitch. Comparing that to per-pitch curr_velo yields nonsense. Always trace the exact field structure before designing a delta. The gap discovery saved a broken feature from shipping.)
- Labeling Noise as Signal Filter (Statcast relabeled pitch types 2022-2025 — ST, CH, SL are often reclassifications of existing pitches. 238/251 pitchers "added" new pitch types, but 95% are artifacts. Hold new_pitch_flag=False until per-pitch career baseline confirms label consistency.)
- Split model architecture, ablation testing, systematic bias detection
- Data leakage, denominator mismatch, graceful degradation
- Feature engineering, environment mismatch
- Verdict-Neutral Layers (a modifier can be correctly built and correctly applied yet still not move verdicts if tier gaps exceed multiplier magnitude — document as informational display, not a scoring change)
- Stacking vs Threshold (three ×0.90 bearish flags = ×0.729 compound, but 72.9% × borderline buy score still lands in same tier; the tier gap is the binding constraint, not the multiplier size)

---

## LOGO

File: signal_fantasy_logo.html (in outputs)
Three versions: Full logo, Circle profile picture, Icon/favicon
Colors: Deep navy (#0d1117) + sky blue (#38bdf8)
Typography: Georgia serif
Tagline decision pending: "Luck is noise. We find the signal."

---

## HOW TO START EACH SESSION

**IMPORTANT FOR CLAUDE:** Read this entire document before doing anything else.
Do not skip sections. Do not assume you know the current state.
The project evolves rapidly across sessions — always verify before acting.

### SESSION START CHECKLIST (every thread, no exceptions):
1. Read this document top to bottom
2. Confirm today's goal with Dustin before starting any work
3. Run session opener quiz (one question from bank below)
4. Ask Dustin to run verification in Claude Code:

   **3-line model check:**
   ```
   grep -n "ERA >= 4.00" score_pitcher_luck.py
   grep -n "3.75\|BUY_LOW_ERA" score_pitcher_luck.py
   grep -n "0.150" score_luck.py
   grep -n "H_KP_K_PENALTY\|_buy_penalty\|H_MAX_COMBINED" score_luck.py
   python -X utf8 validate_formulas.py
   ```

   **Canary checks (spot-check known fixes carried over):**
   ```
   # Ben Rice should be C-eligible (Fix F, April 24)
   python -c "import json; d=json.load(open('data/player_positions.json')); print([p for p in d if 'Rice' in p])"

   # Sanchez should be rank 21+ catchers (Sanchez Test)
   python -c "import json; d=json.load(open('data/player_values.json')); catchers=[p for p in d.values() if p.get('position')=='C']; catchers.sort(key=lambda x: x.get('rank',999)); print([(p['name'],p['rank']) for p in catchers[:25] if 'Sanchez' in p.get('name','')])"

   # AVG penalty should exist in score_value.py (Fix C, load-bearing)
   grep -n "0.220\|avg_liability\|AVG.*penalty" score_value.py | head -5
   ```

   Expected results:
   - Ben Rice: appears with C in position list ✅
   - Sanchez: rank 21 or higher among catchers ✅
   - AVG penalty: line found in score_value.py ✅
   If ANY fail → stop and report before proceeding
5. Check dashboard is running (localhost:8000)
6. State assumptions explicitly — if anything in this doc seems inconsistent
   with what Dustin describes, flag it immediately before proceeding

### SESSION GOAL FORMAT:
Dustin should state the goal as one of:
- "Model improvement" → focus on accuracy, signal quality, backtest
- "Infrastructure" → focus on dashboard, pipeline, tooling
- "Content" → focus on article writing, social, publishing
- "Trade tool" → focus on trade analyzer development
- "Stability" → focus on validation, documentation, cleanup

### SESSION END CHECKLIST (every thread, no exceptions):
1. Run validate_formulas.py → confirm 37/37 PASS
2. If ANY model change was made → run ablation test on affected tier
3. If ANY model change was made → run backtest_pitcher_composite.py and confirm numbers match validated baselines
4. Note every file modified this session
5. Update PARKING LOT — mark completed items, add new ones
6. Add any new career lessons to the lessons section
7. Update accuracy numbers if model changed
8. Update CURRENT SIGNALS section if pipeline was re-run
9. Regenerate this document with all changes
10. Tell Dustin: "Download updated thread_handoff.md and save to project root"
11. Confirm CLAUDE.md is still current — flag if it needs updating

### WHY THIS MATTERS:
Each Claude.ai thread starts with zero memory of previous threads.
This document is the ONLY continuity between sessions.
If it is not updated at session end, the next Claude instance will
work from stale information and make decisions based on outdated state.
Skipping the end checklist is the single biggest source of project drift.

### TWO-DOCUMENT SYSTEM:
- thread_handoff.md (this file) → Claude.ai session memory
  Location: C:\Users\dusti\fantasy-baseball\thread_handoff.md
- CLAUDE.md → Claude Code session memory
  Location: C:\Users\dusti\fantasy-baseball\CLAUDE.md
Both must be kept in sync. Update both at end of every session.
Never create additional handoff/starter/updated variants — one file each, always overwritten.

### SESSION OPENER QUIZ BANK:
- "What is the Sanchez Test and why does it exist?"
- "What does ablation C tell us about the AVG penalty?"
- "What are the two questions before publishing any signal?" (is_article_worthy)
- "Why is Raleigh's rank 2 floor-driven and what should we monitor?"
- "What's the difference between FIP and xERA and why does it matter for Vásquez?"
- "Why does the pitcher model use a split architecture for buy vs sell signals?"
- "What is a load-bearing component and how do we prove something is one?"
- "Why did the Slight Buy pitcher accuracy jump from 62% to 84.4%?"
- "What is documentation drift and how do we prevent it?"
- "Why does the backtest need to use production scorer logic, not reimplemented logic?"

---
*End of handoff. Update this file at end of every session before closing.*
*Download and save to C:\Users\dusti\fantasy-baseball\thread_handoff.md*
