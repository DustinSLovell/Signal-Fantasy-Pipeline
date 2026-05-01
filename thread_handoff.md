# THE SIGNAL FANTASY — Thread Handoff Document
# Single source of truth. Overwrite at end of every session.
# Last updated: April 30, 2026 (Sessions 11-14)

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

## SOCIAL STATUS (April 30, 2026)

- Reddit Post #1 (u/Dlovell02): 17K views, 52 upvotes, 43 comments, #2 post r/fantasybaseball
- Reddit Post #2 (April 30, 2026): 8.6K views, 28 upvotes, 16 comments — Week 2 signals
- Substack Article #1: April 22, 2026 — live, 510+ views
- Substack Article #2: April 29, 2026 — "Week 2 of the Signal Tracker" — 175 views, 58.33% open rate, 25 recipients
- X (@SignalFantasy): Active — Dingler tweet thread posted April 24 (timestamped)
- Instagram (@signalfantasy): Accuracy graphic posted
- Facebook: Deferred
- Fangraphs membership: ACTIVE (purchased for Steamer/ZiPS historical data)

### POSTED April 24:
- Reddit AMA follow-up comment (Pages, Vásquez, Murakami) — top level reply
- Dingler tweet thread: "CBS #6, consensus #17 — buy the value" — timestamped April 24

### POSTED April 29-30:
- Article #2 published: "Week 2 of the Signal Tracker! New leads, checking on previous calls, and more!"
- Reddit Post #2: Week 2 signals + tracker update + hidden gem (TJ Rumfield)
- Community engagement: VrinTheTerrible subscribed to Substack from Reddit ✅
- HonorableJudgeIto validated Wood swing angle with Baseball Savant link

---

## THE PROJECT

**Location:** C:\Users\dusti\fantasy-baseball
**Dashboard:** localhost:8000/dashboard.html
**Pipeline files:** luck_scores.csv (hitters), pitcher_luck_scores.csv (pitchers)
**Career lessons:** career_lessons_database.html (88 concepts, open in browser)
**External projections:** data/projections_external/ (Steamer + ZiPS 2025 hitters/pitchers)

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

### PROJECTION MODEL — Backtest A/B Results (April 29-30, 2026):

Backtest A (projection only vs RTM, n=235 hitters / 165 pitchers, 2025 OOS):
- wOBA: Model 0.0342 vs RTM 0.0397 → **+13.9% better**
- ERA: Model 0.878 vs RTM 1.012 → **+13.2% better**
- HR: Model 6.256 vs RTM 6.693 → **+6.5% better**
- AVG: RTM wins (0.0198 vs 0.0216) — known weakness
- WHIP: RTM wins (0.155 vs 0.194) — known weakness

Backtest B (signal-adjusted projections, direction accuracy):
- Buy Low hitters: **88.6% improved wOBA** (39/44) ✅
- Sell High hitters: **88.0% declined wOBA** (22/25) ✅
- Pitcher Buy Low ERA: **100% improved** (n=7, avg -1.08 ERA) ✅
- Pitcher Sell High ERA: **100% increased** (n=9, avg +1.88 ERA) ✅

Backtest C (vs Steamer + ZiPS, honest result):
- We do NOT beat Steamer or ZiPS on any metric
- ERA head-to-head vs ZiPS: 51.5% win rate (competitive)
- R bias: +0.82 (nearly unbiased vs Steamer -8.33) — lineup context strength
- K MAE gap: 39.4 vs Steamer 21.9 — is_sp bug partially fixed, structural gap remains
- Product positioning: COMPLEMENTARY to Steamer, not competing

Active signal adjustments (Backtest B v2 — production):
- wOBA: ×1.08 Buy Low / ×1.04 Slight Buy / ×0.96 Slight Sell / ×0.92 Sell High
- HR: ×1.05 Buy Low / ×1.02 Slight Buy (buy side only)
- Pitcher Sell High ERA: ×1.10
- REMOVED: AVG adjustments, HR sell-side, Pitcher Buy Low ERA

### BACKTEST METHODOLOGY NOTE:
- Training/calibration: 2022-2024 data ONLY
- Out-of-sample validation: 2025 ONLY
- Never publish 2022-2024 numbers as "live accuracy" — those are in-sample
- 89.7% 2025 OOS is the headline credibility number (Version D — updated April 26)
- Backtest audit CSVs: data/backtest_audit_hitters.csv + data/backtest_audit_pitchers.csv

### KEY HEADLINE NUMBERS (use everywhere):
- 100% SELL HIGH pitchers (2025 OOS, n=14)
- 91.7% SELL HIGH hitters (train 2022-24, Version D)
- 91.3% BUY LOW hitters (train 2022-24, Version D) / 96.0% OOS 2025
- 86.1% overall hitters (train 2022-24, Version D) / 89.7% OOS 2025
- 85.7% overall pitchers (2024 single-year backtest)
- +17.9pp vs RTM hitters (OOS 2025)
- 88.6% Buy Low / 88.0% Sell High direction accuracy (Backtest B v2)
- Projection engine beats RTM by 13% on wOBA and ERA accuracy

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

### NEW DISPLAY LAYERS (April 30, 2026 — no model weight):

**Launch Angle YoY Delta:**
- build_hitter_launch_angle.py → data/hitter_launch_angle.json (454 records)
- 6 new columns in luck_scores.csv: la_delta, current_la_avg, career_la_avg, la_trending_up, la_trending_down, la_display
- Threshold: la_trending_up if delta > +3.0°, la_trending_down if delta < -3.0°
- Coverage: 148 players have full delta (35%)
- Notable: Chapman -17.2° (career 21.0° → current 3.7°) — strongest signal in dataset
- Torres -13.4° with Slight Buy — tension case worth flagging in articles
- Acuña +10.6° with Buy Low — double buy signal
- Wood: no career baseline (rookie) — cannot compute delta yet

**Worry Index / Confidence Meter:**
- CONCERN (fp_rank<50, wOBA 40+pts below 3yr xwOBA, no luck signal): "struggle may be real"
- BREAKOUT (fp_rank>100, wOBA 40+pts above 3yr xwOBA, no regression signal): "breakout may be real"
- Active flags: Devers (fp16, K rate +12.5pp, HH -10.6pp — real struggle not luck)
- James Wood: MASHING, barrel 29.9% vs career 14.4%, HH 65.7%, BABIP below expected — REAL

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
Pre-populated Cohort 3: Ohtani, Judge, Trout, Harper, Seager, Lindor, Turner, Machado, Riley, Ramírez, Swanson, Bogaerts, Stanton, Olson, Nola, Yelich (17 players after Spotrac merge April 28)
Pre-populated Cohort 1: Acuña ($12.5M/yr, 2yr left), Yordan ($19.2M/yr, 1yr left)
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

### NEW SIGNAL VARIABLES — PRIORITY TABLE AND REASONING (documented April 25-26):

| Rank | Variable | Signal impact | Expected stats impact | Trade tool impact |
|------|----------|--------------|----------------------|-------------------|
| 1 | Pitch mix evolution (pitchers) | Medium-High | High — K/9 projection | High |
| 2 | K% trend (hitters) | Medium | High — AVG/wOBA projection | High |
| 3 | Pull rate trend (hitters) | Medium | Medium-High — HR projection | Medium-High |
| 4 | Catcher framing (pitchers) | Medium | Medium — ERA ±0.20-0.35 | Medium |
| 4 | Leverage index (relievers) | Medium | Medium-High — SV+H projection | High |
| 6 | First pitch strike % (pitchers) | Low-Medium | Medium — WHIP/BB projection | Low-Medium |
| 7 | Opponent quality | Low | Low | Low |

Key insight: pitch mix evolution and K% trend have outsized trade tool impact because they
directly change projected counting stats (K, AVG, wOBA, HR) not just the luck score signal.
A 2pp SwStr% improvement = ~1.5 K/9 = ~17 projected Ks over 100 IP.

**Pitch mix Phase 1+2 — COMPLETE (April 25):**
Phase 1: SwStr-based abandonment + effectiveness flags. Version F = verdict-neutral (0.0pp vs E).
Phase 2: 6-flag system (abandonment, velo_drop, rv_degrade, effectiveness, velo_gain, rv_improve).
Version G = verdict-neutral (0.0pp vs E, OOS PASS ✓). Coverage 2026: 234 pitchers.
Architecture conclusion: pitch mix is INFORMATIONAL layer. 10% multipliers rarely cross tier boundaries.
Data: pitcher_pitch_mix_delta.json (251 pitchers), pitcher_career_velo_per_pitch.json, pitcher_career_arsenal_rv.json

---

## PROJECTION MODEL — CURRENT STATE (April 30, 2026)

### Playing Time Module (NEW — April 30, 2026):
Built _blend_pa() and _blend_ip() in stat_projections.py.
380 hitters and 254 pitchers now have Steamer-weighted projections.

HITTER PA blend formula:
- Primary: Steamer 2025 full-season PA × (games_rem / 162)
- Secondary: current pace × games_remaining × 0.90
- Weights by games played: <20GP (70/30), 20-50GP (60/40), 50+GP (40/60)
- IL penalty: DAY_TO_DAY=-5g, INJURY_RESERVE=-12g (ESPN returns ACTIVE for all — infrastructure ready)

PITCHER IP blend formula:
- SP (Steamer GS ≥ 10): 55% Steamer + 45% pace
- RP (Steamer GS < 10): 80% Steamer + 20% pace, cap 70 IP
- RP with <15 current IP: 100% Steamer

Key validation results:
- Grisham: 498 PA → 327 PA (platoon player correctly reduced; Steamer 239 full-season)
- Judge: 498 PA → 553 PA (elite player correctly increased; Steamer 625)
- Stanton: 498 PA → 360 PA (conservative Steamer projection for IL-prone player)
- Skenes: 104.7 IP → 157.3 IP (elite SP gets full workload credit)
- Luzardo: 104.7 IP → 144.6 IP (SP with Steamer-confirmed workload)
- Top gainers: Ohtani +102 PA, Kurtz +101 PA, Schwarber +73 PA
- Top losers: bench players 4-14 GP correctly dropping from 498 to single digits

### Lineup Context Module (April 27, 2026):
- data/hitter_batting_slot_2026.json: 452 batters, modal batting slot
- data/team_lineup_context_2026.json: 30 teams, OBP/SLG per slot
- R_SENSITIVITY = 0.8, RBI_SENSITIVITY = 1.2 (backtest-validated against 2025 actuals, n=141)
- Sell High RBI cap: min(rbi_mult, 1.05)
- Caps: MULT_MIN=0.80, MULT_MAX=1.20
- Top beneficiaries: Tucker LAD (RBI_mult=1.20), Riley ATL (1.20)
- Top penalties: Hayes CIN (0.80), L.Robert NYM (0.80), F.Álvarez NYM (0.80)

### CBS Regression (completed April 28-29):
- Hitters: Train R²=0.985, OOS R²=0.983 | Pitchers: Train R²=0.927, OOS R²=0.909
- Coefficients in config.py (CBS_H_COEF_*, CBS_P_COEF_*)
- Wired into trade_analyzer.py: _compute_cbs_fpts() + replacement_level.py surplus calc

### Known Projection Weaknesses:
- AVG: career BA anchor (65% blend) beats naive but loses to RTM
- WHIP: component H/9+BB/9 approach marginally worse than ERA-derived formula
- K: 39.4 MAE vs Steamer 21.9 — structural gap from April-only IP data
- R/RBI: lineup-dependent, partially addressed by lineup context module
- Playing time: Steamer 2025 used for 2026 projections (best available)

---

## EXTERNAL PROJECTION FILES (downloaded April 2026)

Location: data/projections_external/ AND root directory (Steamers 2025 batters.csv etc.)
- Steamers 2025 batters.csv (4,140 players, MLBAMID, PA, HR, AVG, wOBA, etc.) — ROOT
- Steamers 2025 pitchers.csv (5,215 players, MLBAMID, IP, GS, ERA, WHIP, K, etc.) — ROOT
- Zips_2025_batters.csv (1,963 players) — data/projections_external/
- Zips_Pitchers_2025.csv (1,866 players) — data/projections_external/

Fangraphs membership: ACTIVE — historical preseason projections available
Match rate: 98.6% hitters (417/423), 98.5% pitchers (396/402)
Unmatched = rookies/NPB players not in Steamer 2025

---

## CURRENT SIGNALS (April 29-30, 2026)

### Pitcher Buy Low (7):
| Pitcher | ERA | FIP | xERA | IP | Luck |
|---------|-----|-----|------|----|------|
| Jesus Luzardo | 5.08 | 2.65 | 2.93 | 33.7 | +0.530 |
| Joe Ryan | 4.78 | 2.88 | 2.72 | 37.7 | +0.420 |
| C. Sanchez | 3.82 | 2.52 | 3.03 | 33.0 | +0.269 |
| Mlodzinski | TBD | TBD | TBD | TBD | +0.185 |
| Paddack | TBD | TBD | TBD | TBD | +0.169 |
| Baz | 5.20 | 3.60 | 4.30 | TBD | +0.161 |

### Pitcher Slight Buy (April 24 snapshot):
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

### Pitcher Sell High (April 24 list):
Soriano, Wacha, Martinez, Holmes, Mcgreevy, Sugano, E.Rodriguez, S.Lugo,
M.Perez, King, Teng, G.Williams, Early, Kochanowicz, Imanaga, Freeland,
Messick, C.Phillips, D.Martin, F.Peralta, Vásquez, L.Gil, C.Patrick,
Chandler, G.Marquez, Wrobleski

### Relievers — Dormant but watch (cross 15 IP threshold to fire):
- Adrián Morejón: ERA 8.03, FIP 2.47 — massive gap, verify xERA before calling buy
- Camilo Doval: ERA 8.59, FIP 4.81
- Taylor Rogers: ERA 5.62, FIP 2.79
NOTE: All score Neutral now (< 15 IP confidence threshold — intentional).

### Hitter Signals (April 26 — post Version D):
Signal counts (416 hitters): Buy low: 54 | Slight buy: 12 | Neutral: 288 | Slight sell: 28 | Sell high: 34

### Article #1 Call Tracker (Week 2 scores):
| Player | Signal | Wk1 Score | Wk2 Score | Status |
|--------|--------|-----------|-----------|--------|
| Yordan Alvarez | Buy Low | +0.288 | +0.213 | Normalizing |
| Z. Pasquantino | Buy Low | +0.434 | +0.401 | Injured — wait |
| Trent Grisham | Buy Low | +0.409 | +0.532 | Strengthening |
| Oneil Cruz | Sell High | -0.191 | -0.214 | Watching |
| Jordan Walker | Sell High | -0.196 | -0.265 | Deepening |
| Jesus Luzardo | Buy Low | +0.369 | +0.530 | Confirmed |
| Kyle Bradish | Buy Low | +0.178 | +0.173 | Refuted |
| Michael Wacha | Sell High | -0.371 | -0.370 | Stalled |
| Gavin Williams | Slight Sell | -0.101 | -0.101 | ERA moved (2.17→3.34) |

### Tracker Status:
- 169 total calls tracked (127H + 42P)
- Current accuracy: 73.9% on 23 resolved calls
- Duplicate week guard built — tracker won't burn week slots without new Statcast data

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

### Fixes Applied April 25, 2026:
- Fix I: Barrel rate regression — PA-weighted blend toward league mean
  LG_BARREL=0.066, BARREL_PA_STAB=250 (raised from 200 April 30 — statistically sounder)
  At 77 PA: weight 0.236 → small samples blend heavily toward 6.6% league avg
  Note: ESV barely changed for Rice (17.815→17.759) — barrel only affects HR_proj, not R/RBI

### Fix Applied April 30, 2026 (xwOBA career regression):
- xwOBA career regression toward xwoba_3yr baseline
  XWOBA_PA_STAB=250 — same pattern as barrel_rate
  xwoba_3yr loaded from luck_scores.csv (95.7% coverage, 405/423)
  Merged into hitter_df before project_hitter_stats()
  R and RBI now use blended xwOBA: (_wt × current_xwOBA + (1-_wt) × xwoba_3yr)
  Fixes: Sanchez 77-PA xwOBA=0.433 (career .326) was inflating R/RBI projections
  Result: Sanchez drops from catcher rank 20 → rank 21 ✅

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

- Yordan Alvarez: top 20 overall ✅
- Cal Raleigh: top 4 catchers (relaxed from top-3 until catcher PA > 150, re-tighten mid-May 2026)
  Root cause: Ben Rice .507 xwOBA at 95 PA inflates R/RBI projections, pushing him to #1.
  Raleigh natural ESV ~4.7 (xwOBA .336 + AVG .186 liability); rank 2 is floor-driven (CQS=80.2).
- Drake Baldwin: top 5 catchers ✅
- William Contreras: top 9 catchers (relaxed from top-8 — MIL lineup weak upstream OBP, 9.3% RBI reduction is real)
- Will Smith: top 12 catchers ✅

### THE SANCHEZ TEST:
- Gary Sanchez: rank 21+ catchers ✅ (FIXED April 30 — xwOBA career regression added)
- IF Sanchez appears in top 15 catchers → STOP, something is broken
- The AVG liability penalty (proj_avg ≈ 0.200) is load-bearing for keeping him down
- The xwOBA regression (XWOBA_PA_STAB=250) prevents hot-start noise from inflating his R/RBI

---

## PIPELINE SCRIPTS (current as of April 30, 2026)

| Script | Purpose |
|--------|---------|
| score_luck.py | Hitter luck scoring (Layer 1) |
| score_pitcher_luck.py | Pitcher luck scoring (Layer 1, v2.0 split architecture) |
| stat_projections.py | Rest-of-season projections — WITH PLAYING TIME MODULE |
| generate_projections.py | Runs projection pipeline |
| score_value.py | Trade values and rankings (Layer 3) |
| trade_analyzer.py | Trade verdicts v2 (Layer 4) |
| fetch_ownership.py | ESPN ownership + injury_status column |
| fetch_fantasypros_ownership.py | FantasyPros cross-platform ownership |
| fetch_prior_teams.py | 2025 team assignments for park change detection |
| validate_formulas.py | 37/37 PASS formula suite |
| export_signal_board.py | Excel signal board with ownership data |
| run_pipeline.py | Full pipeline runner |
| build_hitter_launch_angle.py | Launch angle YoY delta builder |
| lineup_context.py | R/RBI lineup multipliers |
| build_lineup_context.py | Lineup context data builder |
| weekly_update.py | Tracker with duplicate week guard |
| projection_backtest_A.py | Projection accuracy vs RTM |
| projection_backtest_B.py | Signal-adjusted projection accuracy |
| projection_backtest_C.py | Six-way comparison vs Steamer + ZiPS |
| backtest_pitcher_composite.py | Full pitcher composite backtest (Versions A-E) |
| build_pitcher_stuff_baselines.py | Stuff quality career data builder |
| build_pitcher_phase2_baselines.py | Career velo/RV baselines from parquets + arsenal stats |
| build_pitch_mix_delta.py | Phase 2 pitch mix delta signals (velo + RV flags) |
| build_hitter_career_k_pull.py | K%/pull rate career baseline builder (v4_april CSVs) |
| backtest_pitcher_pitch_mix.py | Version E/F/G pitch mix backtest |
| backtest_multi_year_v7.py | Current active v7 hitter backtest script |
| build_hitter_career_platoon.py | Career platoon baseline builder |
| merge_spotrac_contracts.py | Spotrac contract data merger |
| era_simulation.py | ERA_all_sc simulation (diagnostic only) |
| model_architecture_explainer.md | 4-layer architecture documentation |
| pitcher_buy_model_testing_rationale.md | 10-test diagnostic results |

### Key data files:
- data/projections_2026.csv — 794 players, 19 columns
- data/player_ownership_2026.csv — 3,797 players + injury_status
- data/player_values.json — 825 players, rebuilt by score_value.py
- data/career_quality.json — CQS floors (11 records fixed April 24)
- data/prior_teams_2025.json — 998 players, 2025 team assignments
- data/hitter_launch_angle.json — 454 records, LA delta (built April 30)
- data/hitter_batting_slot_2026.json — 452 batters, batting slot
- data/team_lineup_context_2026.json — 30 teams, OBP/SLG per slot
- data/calls_tracker.csv — 169 calls, week-over-week tracking
- data/projections_external/ — Steamer + ZiPS 2025 hitters/pitchers
- data/backtest_A_hitters_2025.csv + data/backtest_A_pitchers_2025.csv
- data/backtest_B_results_v2.csv — tier breakdown summary
- data/backtest_audit_hitters.csv + data/backtest_audit_pitchers.csv — row-level
- data/backtest_composite_summary.csv — full pitcher ablation results
- data/pitcher_career_babip.json — career BABIP/HH%/barrel baselines
- data/pitcher_career_csw.json — CSW career baselines (611 pitchers)
- data/pitcher_career_pitch_mix.json — 2025 arsenal baseline (318 pitchers)
- data/pitcher_current_pitch_mix.json — 2026 current pitch mix (459 pitchers)
- data/pitcher_arsenal_rv_allyears.csv — 15,947 rows, rv/100 per pitch type, 2022-2026
- data/pitcher_career_velo_per_pitch.json — career avg velo per pitch type (800 pitchers)
- data/pitcher_career_arsenal_rv.json — career avg rv/100 per pitch type (1,252 pitchers)
- data/pitcher_arsenal_rv_2026.json — current 2026 rv/100 per pitch type (514 pitchers)
- data/pitcher_pitch_mix_delta.json — Phase 2 pitch mix delta signals (251 pitchers)
- data/hitter_career_k_pull.json — K%/pull rate baselines (643 career, 415 current, 327 with deltas)
- data/hitter_career_discipline.json — chase rate baselines (672 batters)
- data/hitter_career_sprint.json — sprint speed baselines (849 players)
- data/hitter_career_platoon.json — career platoon baselines (489 batters)
- data/spotrac_contracts_clean.csv — 506 hitter rows, 308 unique players (Spotrac export)
- data/spotrac_contract_backtest.csv — 211 rows, cohort × signal preliminary results
- data/contract_year_2026.csv — 31 players loaded (13 manual + 18 Spotrac merge)
- data/yordan_tracker.csv — weekly Yordan wOBA/xwOBA tracker
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
- Verdict thresholds: ≥75% Strong | ≥60% Favorable | ≥40% Neutral | ≥25% Unfavorable | <25% Avoid
- Known issue: trade tool search click bug — onClick handler not firing (Tier 3 fix)
- Known issue: Dashboard sort bug — Advanced View sorts by absolute magnitude

### Park Changes (43 players flagged):
Ke'Bryan Hayes, Josh Lowe, Pete Alonso, José Caballero, Brandon Nimmo + 38 others
Badge shows: "Park change (OLD→NEW) — career baseline less reliable"

---

## OWNERSHIP DATA SOURCES

### ESPN (primary):
- fetch_ownership.py → player_ownership_2026.csv (3,797 players)
- Columns: player_name, mlbam_id, owned_pct, rank, source, fetched_date, injury_status
- ESPN players_wl endpoint returns ACTIVE for all players (injuryStatus not surfaced)
- Infrastructure in place; IL penalties = 0 until a different endpoint is used

### FantasyPros (secondary — April 30, 2026):
- fetch_fantasypros_ownership.py → fp_ownership, fp_espn_own, fp_yahoo_own columns
- Aggregates ESPN + Yahoo + CBS into one number
- 598 unique FP players (top 300 hitters + 300 pitchers)
- 69.7% match rate (571/819) — unmatched are low-ownership/injured
- 601/3797 rows updated in player_ownership_2026.csv

### CBS vs ESPN ownership discrepancy:
- CBS leagues = more competitive/experienced players
- ESPN underrepresents serious players' roster decisions
- Jeffers: ESPN 17%, CBS 59% | Herrera: ESPN 26%, CBS 80%
- Hidden Gem queries should use fp_ownership (CBS blend) not ESPN only

---

## ARTICLES PUBLISHED

### Article #1 — PUBLISHED April 22, 2026
**Title:** Fantasy Baseball: Using Seven Layers of Statcast to Predict Buying/Selling Signals
**URL:** https://open.substack.com/pub/thesignalfantasy/p/fantasy-baseball-using-seven-layers
Players: Pasquantino, Yordan Álvarez, Trent Grisham (buy) | Cruz, Walker (sell) | Luzardo, Bradish (pitcher buy) | Wacha, Williams (pitcher sell)

Known edits still needed:
- Fix "Without I'm proud to say" → "I'm proud to say"
- Verify Cruz "hardest ever hit ball in Statcast era" claim before promoting

### Article #2 — PUBLISHED April 29, 2026
**Title:** Week 2 of the Signal Tracker! New leads, checking on previous calls, and more!
**Stats:** 175 views, 58.33% open rate, 25 recipients, Reddit driving 40% of traffic
**New calls:** Seager, Herrera, Dingler (buy) | Chapman, Vargas (sell) | Ryan, Sanchez (pitcher buy) | Arrighetti, Ray (pitcher sell)
**Features:** Week-over-week tracker table, Worry/Get Hyped index (Devers/Wood), Hidden Gem (Rumfield)
**What's Coming:** luck score spreadsheet release, trade analyzer announcement
Copyright footer "© 2026 Dustin Lovell / Signal Fantasy" added to both articles ✅
Substack global footer set ✅

### Week 3 Article — DUE May 5-6, 2026
- Run pipeline Monday May 5: run_pipeline.py --write → weekly_update.py --update → --report --top 15
- First week where confirmed/refuted calls should be statistically meaningful
- April Big Board: consolidated view of all April calls
- Chapman -17.2° LA delta is article gold — strongest sell confirmation in dataset

---

## WEEK 2 ARTICLE — DRAFT STRUCTURE (published April 29 — preserved for reference)

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
7. Pitcher model v2.0 update
8. Honorable Mentions
9. Closing + Week 3 tease

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

## PARKING LOT — PRIORITIZED (updated April 30, 2026)

### TIER 0 — Done:
- **Steamer/ZiPS direct comparison** — COMPLETE ✅ (Backtest C). Honest FAIL vs both.
  Complementary positioning confirmed. We don't compete on raw MAE; we add luck signal layer.

### TIER 1 — Do immediately:
- **Weekly tracker mechanism classifier** — HIGHEST PRIORITY. wOBA vs xwOBA decomposition.
  Mechanism values: Normalizing | Re-evaluate | Confirmed | Refuted | Watch.
  Duplicate week guard now built ✅. Without this, the tracker shows movement but not meaning.
- **Week 3 article** (May 5-6 deadline): Monday pipeline run → tracker → report
  Chapman -17.2° LA delta is the lead story
- **April Big Board** — consolidated view of all April calls
- **White paper Section 10** — after 2-3 more weeks of live tracker data

### TIER 2 — This week:
- **CBS rank integration** — display CBS rank in dashboard for neutral player sorting
  Two purposes: (1) content engine for breakout/worry identification (2) coefficients already exist
- **Hidden Gem detector** — formal pipeline feature
  Query: fp_ownership < 35%, wOBA > .330, xwOBA gap > -0.020, luck > -0.085, PA >= 75
  One Hidden Gem per article — hitters and pitchers alternating weeks
  Timing issue: CBS corrects faster than ESPN — run Monday, publish Tuesday
- **Pitcher Slight Buy sensitivity analysis** — n=4 historically too thin
  Priority: SB ERA floor ablation (4.00 → 3.75) to grow SB sample.
  Gate B (HR/FB > +0.03 above career): best gate candidate, OOS 80.0% (+7.8pp) but n=3 SB OOS
- **is_article_worthy() gate** — build after Week 3 publishes

### RESEARCH AGENDA (post-2026 season):
- Worry Index sensitivity validation (validate WORRY_WOBA_GAP=0.040 and WORRY_LUCK_BAND=0.085 thresholds)
- Financial motivation backtest (cohort × signal when n>50 per cohort)
- Gate B SB confirmation retest (after 2026 adds signals; currently n≈2/year after gates)
- SB ERA floor ablation (lower 4.00→3.75 to grow SB sample)
- Age-weighted chase rate calibration (empirical mid-2027; current priors are H_CHASE_AGE_WEIGHT_U25=0.40/26_27=0.70)
- xwOBA slot replacement for pitcher buy score (β=0.25 confirmed as drag in authoritative backtest; +3.8pp OOS when removed — but no clear replacement; revisit after 2026 full season)

### TRADE TOOL FOUNDATION:
- CBS rank reverse engineering: COMPLETE ✅ (R²=0.983 hitters, R²=0.909 pitchers)
- Replacement level calculator: COMPLETE ✅ (replacement_level.py)
- Lineup context module: COMPLETE ✅
- Playing time module: COMPLETE ✅ (Steamer-weighted, IL penalty)
- Projection backtests A+B: COMPLETE ✅
- League settings intake UI: not yet built
- Stress test 5-10 real trades: not yet done
- Trade tool search click bug: dashboard.html onClick handler needs fix
- Fantasy points conversion engine: projected stats × CBS point values — not yet built

### CONTENT PIPELINE:
- "Why April Signals Matter Most" article: publish mid-May (paid tier anchor)
- "How I Built This in 10 Days with AI" article: after 6-8 weeks live track record
- Live 2026 Accuracy Tracker: paid tier dashboard, updates weekly (build mid-June 2026)
- Weekly luck score spreadsheet: release next 1-2 weeks (promised in Article #2)
- CBS rank in dashboard: enables "Sort by CBS rank → find biggest signal divergences" content
- Spotrac Phase 2: historical 2022-2024 contract data via Wayback for financial motivation backtest

### SCORING FORMAT EXPANSION (Tier 3):
- OBP leagues
- Saves + Holds with configurable ratio (1:1, 2:1, 3:2)
- QS (quality starts)
- K-BB% for pitchers
- WHIP as projection metric
- wRC+ for hitters
- Ask Reddit for other common formats

### PROJECTION MODEL GAPS (prioritized):
1. Playing time — COMPLETE ✅
2. Park factor adjustment — 43 flagged players not yet adjusted in projections
3. Platoon splits into projections — infrastructure exists, not wired into proj stats
4. IP trajectory refinement — partially addressed by playing time module
5. SB projection — sprint speed used, no green light rate
6. AVG projection precision — career BA anchor helps but loses to RTM

### TIER 3 — Important, not blocking:
- Nola/Rogers ERA gap fix (~1 run miscalibration)
- 2026 live prediction log (CSV timestamping)
- Post-blend AVG floor (26 fringe hitters below .195)
- Extended scoring categories
- Dashboard sort bug (Advanced View sorts by absolute magnitude)
- Trade tool search click bug (dashboard.html onClick handler)
- Current rank integration (fp_rank shows preseason, not in-season)

### TIER 4 — Week 3-4+:
- Trade analyzer B2 (roster context module)
- IL badge integration (banner caveat covers for now)
- Hitter evolution detector (launch angle >5°, pull rate >10°, sprint speed)
- CSW buy-low-only ablation
- Multi-year pitcher backtest refinement
- Recent game trend line display

### HIDDEN GEM DETECTOR (formal feature — Tier 2):
Query: fp_ownership < 35%, wOBA > .330, xwOBA gap > -0.020, luck > -0.085, PA >= 75
Timing issue: CBS corrects faster than ESPN — run query Monday, publish Tuesday
One Hidden Gem per article — hitters and pitchers alternating weeks

### TWO-TRACK IN-SEASON SIGNAL SYSTEM (documented April 27):
Track 1 — April Signals (PRODUCTION): validated 86.1%/89.7% — the published signals.
Track 2 — In-Season Rolling (HYPOTHESIS): weekly_update.py tracker, no validated accuracy.
Rule: NEVER present Track 2 with equal authority to Track 1.
Article framing for Track 2: "data moving in the right direction" not "new signal."
Publishing cadence: Tuesday nights publish / Monday production run (run_pipeline.py → weekly_update.py → --report).

### TIER 5 — Future:
- Football product (Year 2-3, nflfastR)
- Podcast pitch (live calls format)
- Career playbook document
- CBS Coefficient Ratios as Trade Value Exchange Rates (same coefficients for rankings AND trade analyzer)
- Leverage index for relievers (SV+H projection)
- Catcher framing (ERA ±0.20-0.35)
- First pitch strike % (WHIP/BB projection)

---

## TRADE TOOL KNOWN ISSUES (from stress testing April 25)

**Issue 1 — Smell test failure: Skenes for Ben Rice returns "Favorable"**
- Skenes (Slight Sell, ERA 0.95, FIP 2.56) given away for Rice (Sell High, C-NYY)
- Tool returned "Favorable — slight edge in your favor" for getting Rice
- This should be rejected 10/10 times — Skenes is far more valuable
- Root cause: positional scarcity of C overweighting Rice, OR career discount on Skenes
- Fix needed: value gap check — if player given away is top-20 overall, verdict should not favor other side

**Issue 2 — Pitcher net stats direction misleading**
- Giving away Skenes shows ERA -1.50 and WHIP -0.76 as positive changes
- Technically correct (you lose his stats) but misleading in context
- Fix needed: replacement-level baseline for pitchers in net stats calculation

**Issue 3 — Architectural principle: signals should inform stats, not verdicts**
- Current: signal tier (Buy Low/Sell High) feeds directly into verdict logic
- Correct: signal feeds into projected stats ONLY → stats determine trade value → verdict = value comparison
- Signal badge should be display-only, not independently weight the verdict
- Fix location: trade_analyzer.py — remove signal-tier weighting from verdict calculation

---

## COMPLETED PARKING LOT ITEMS (reference)

- Dashboard 7-fix audit: COMPLETE ✅
- Pitcher ownership ESPN fetch: COMPLETE ✅ (374/380 matched)
- Reliever FIP fix: COMPLETE ✅ (April 24) — 110 relievers via fip_sc_all fallback
- Hitter HH% denominator fix: COMPLETE (296/414 matched, 118 use default 0.370)
- Platoon adjustment: COMPLETE ✅ (Layer 7 confidence modifier, live in production)
- Slight buy accuracy investigation: COMPLETE ✅ (hitter xwOBA gate + pitcher ERA gate)
- New signal ablation (chase/CSW/sprint): COMPLETE ✅
- Live ownership data: COMPLETE ✅ (ESPN + FantasyPros)
- Stat projection engine v2: COMPLETE ✅
- Pitcher evolution detector: COMPLETE ✅ (6-factor, Bradley evolution_score=4)
- Formula validation suite: COMPLETE ✅ (37/37 PASS)
- Trade analyzer v2: COMPLETE ✅
- Park change detection: COMPLETE ✅ (998 players, 43 flagged)
- Score_value.py fixes A-I: COMPLETE ✅ (all fixes applied April 24-30)
- Pitch mix Phase 1 (abandonment + effectiveness): COMPLETE ✅ (April 25 — verdict-neutral)
- Pitch mix Phase 2 (per-pitch velo + RV): COMPLETE ✅ (April 25 — 94.0%/87.0% OOS PASS)
- Cal Raleigh invariant relaxed: COMPLETE ✅ (top-4 until catcher PA > 150, re-tighten mid-May)
- Pitcher ERA floor Buy Low 3.50→3.75: COMPLETE ✅ (April 25 — score_pitcher_luck.py line ~967)
- Slight Buy hitter threshold recalibration: COMPLETE ✅ (0.100 floor, 0.030 gap gate, 0.380 ceiling)
- K%/pull rate evolution modifier: COMPLETE ✅ (April 25 — wired in score_luck.py, 37/37 PASS)
- Additive modifier architecture Version D: COMPLETE ✅ (April 26 — train +1.7pp, OOS +0.3pp, 42 verdict changes)
- Platoon career baseline fix: COMPLETE ✅ (April 26 — 489 batters, mean gap=-0.019)
- Contract year cohort framework: COMPLETE ✅ (April 26 — display-only, 5-cohort classification)
- Financial motivation cohort redesign + Spotrac merge: COMPLETE ✅ (April 26-28, 31 players loaded)
- Calls tracker: COMPLETE ✅ (April 26 — 169 players, duplicate guard added April 30)
- Worry Index / Confidence Meter: COMPLETE ✅ (April 27 — score_luck.py display layer)
- Age-weighted chase rate modifier: COMPLETE ✅ (April 27 — config.py, 37/37 PASS)
- Cohort framework age-ordering bug fix: COMPLETE ✅ (April 27 — moved apply() after df["age"] set)
- run_pipeline.py subprocess encoding fix: COMPLETE ✅ (April 28 — UnicodeDecodeError on Windows fixed)
- Week 2 article: PUBLISHED ✅ April 29, 2026
- CBS FPTS scraper + regression: COMPLETE ✅ (April 28-29 — R²=0.983 hitters, 0.909 pitchers)
- Replacement level calculator: COMPLETE ✅ (April 29 — replacement_level.py)
- Projection diagnostic + two stat_projections.py fixes: COMPLETE ✅ (April 28-29)
  Fix 1 (BABIP-only sell HR multiplier suppressed when xwoba_gap > -0.020)
  Fix 2 (thin career baseline: career_pa < 1000 → career weight × 0.85)
- ERA simulation: COMPLETE ✅ (April 29 — 389 pitchers, keep filtered ERA, era_simulation.py diagnostic)
- Financial motivation backtest preliminary: COMPLETE ✅ (April 29 — 112/211 matched, n<10 per cohort, no conclusions)
- Projection accuracy backtest (Backtest A): COMPLETE ✅ (April 29 — 235H/165P, beats RTM 4/5 hitter, 2/3 pitcher)
- Projection backtest B v2: COMPLETE ✅ (April 30 — 88.6%/88% direction accuracy)
- Backtest C six-way comparison: COMPLETE ✅ (April 30 — honest FAIL vs Steamer/ZiPS, ERA bias win)
- is_sp tautology bug fix: COMPLETE ✅ (April 30 — projection_backtest_A.py, steamer_gs >= 10)
- FantasyPros ownership fetch: COMPLETE ✅ (April 30 — fetch_fantasypros_ownership.py)
- Duplicate week guard (weekly_update.py): COMPLETE ✅
- ESPN injury_status field: COMPLETE ✅ (infrastructure ready, all return ACTIVE currently)
- Sanchez Test fix: COMPLETE ✅ (April 30 — xwOBA career regression + BARREL_PA_STAB=250)
- Pitcher buy model testing (10 tests): COMPLETE ✅ (April 27-30 — all correctly rejected)
- Playing time module: COMPLETE ✅ (April 30 — Steamer-weighted, 380H/254P updated)
- Launch angle YoY delta: COMPLETE ✅ (April 30 — display only, 148 players, build_hitter_launch_angle.py)
- White paper published: COMPLETE ✅ (signal_fantasy_whitepaper.docx — 11 sections, GitHub timestamped)
- GitHub DustinSLovell/Signal-Fantasy-Pipeline: current ✅ — pushed April 30, 2026

---

## IMPORTANT DATA NOTES

- Both Max Muncys correctly disambiguated:
  Dodgers Muncy: ID 571970 (age 36) — slight sell
  A's Muncy: ID 691777 (age 24) — stronger sell
- Murakami: CWS (not ARI) — confirmed in pipeline
- Vásquez: spelled with accent (Randy Vásquez) in CSV
- Seager: wOBA .332/xwOBA .378/score +0.344 — Buy Low, Article #2 lead ✓
- Dingler: wOBA .354/xwOBA .459/gap +.105/score +0.317 — Buy Low, Week 2 feature ✓
- Yordan Week 1→2: wOBA .510/xwOBA .595/score +0.213; normalizing as expected; Buy Low holding
- Matt Chapman: LA delta -17.2° — most extreme in dataset, confirms sell signal
- Gleyber Torres: LA delta -13.4° with Slight Buy — tension case, worth flagging in articles
- Acuña: LA delta +10.6° with Buy Low — double buy signal
- TJ Rumfield COL: Buy Low +0.252, 35% CBS, Hard hit 39.5%, BABIP .289 at Coors — Article #2 Hidden Gem
- Iván Herrera STL: Buy Low +0.365, 26.7% owned
- Dillon Dingler DET: Buy Low +0.260 (softened from +0.317 — results improving)
- Rafael Devers: Worry flag — K rate 33.3% (+12.5pp), HH 43.1% (-10.6pp), xwOBA .269 (career .371) — real struggle
- James Wood: barrel 29.9% vs career 14.4%, HH 65.7%, BABIP below expected — REAL performance, no luck signal
- Worry Index active flags: Devers (fp16), Bichette (fp14), Adames (fp25), Alonso (fp17), Soto (fp5/42PA too early)

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
SWSTR_TO_K9 = 77.3 at line ~52 in stat_projections.py ✅

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

## BACKTEST STATUS & METHODOLOGY (April 30, 2026)

CRITICAL — Training/Test Split:
- Training/calibration: 2022-2024 data ONLY
- Out-of-sample validation: 2025 ONLY
- NEVER mix 2022-2024 into published accuracy claims — that's in-sample
- The 89.7% headline number uses 2025 out-of-sample data only

Validated headline numbers — Version D (from backtest_multi_year_v7.py — source of truth):
- Hitter (Version D, backtest v7): 86.1% train (n=187) / 89.7% OOS 2025 (n=87) | +17.9pp vs RTM
  Buy Low: 91.3% train / 96.0% OOS | Slight Buy: 73.5% train / 90.9% OOS
  Slight Sell: 89.3% train / 76.9% OOS | Sell High: 91.7% train / 100.0% OOS
- Pitcher (backtest v7, 2024 single-year): 85.7% overall | Buy Low 90.9% | Sell High 100.0%
- 2025 OOS: 89.7% hitters (never trained on this data — most trustworthy number for publishing)
- vs RTM: hitters +17.9pp OOS

Backtest files (authoritative):
- backtest_multi_year_v7.py — current active hitter v7 script
- backtest_audit_hitters_v2.csv — 729 rows, 383 in_eval=True — AUTHORITATIVE hitter source
- backtest_composite_pitcher.csv — pitcher Version E results — AUTHORITATIVE pitcher source

### PITCH MIX BACKTEST RESULTS:
| Version | Train 22-24 | OOS 2025 | vs RTM (train) | Architecture |
|---------|-------------|----------|----------------|-------------|
| E (baseline) | 94.0% (n=134) | 87.0% (n=46) | +24.0pp | no pitch mix |
| F (Phase 1 — SwStr) | 94.0% (n=134) | 87.0% (n=46) | +24.0pp | abandonment + effectiveness ×0.90/×1.10 |
| G (Phase 2 — velo+RV) | 94.0% (n=133) | 87.0% (n=46) | +24.0pp | 6-flag multiplicative |
| H (additive — April 27) | 94.0% (n=134) | 87.0% (n=46) | +24.0pp | additive penalties, all → 0.0 |

Version H result: VERDICT-NEUTRAL. All 3 bearish flag penalties calibrate to 0.0. Buy sample too small (n=21 train) for additive advantage. DECISION: Keep multiplicative ×0.90/×1.10 for pitchers. Additive works for hitters (n=211 train, 5 flags) but not pitchers.

DO NOT mix 2022-2024 in-sample numbers into published accuracy claims.
Publish 2025 OOS numbers whenever possible — that's the honest track record.

---

## COMMERCIAL ROADMAP

- Paid tier ($10/month): activate after 200-500 free subscribers
- Trade analyzer public: Phase B (local only now) → beta after validation
- Podcast pitch: live calls format, accountability content
- Backtest audit log: commercialization credibility asset (building now)
- Football product: Year 2-3 using nflfastR

---

## PITCHER BUY MODEL — TESTING RATIONALE (April 27, 2026)

10 architectural tests run, all correctly rejected. Key findings:
- Buy score is functionally single-variable (ERA-FIP contributes 99.3%)
- Z-score normalization failed authoritative backtest (population shift)
- Slight Buy tier structurally undertrained (n=2/year after gates)
- Gate B (HR/FB above career >0.03) is strongest SB confirmation signal — retest after 2026 season
- xwOBA is a slight drag (removing it +3.8% OOS) but replacing it makes things worse
- Full documentation: pitcher_buy_model_testing_rationale.md

Session 10 detailed test results:
1. ERA/FIP ratio sweep: VERDICT-NEUTRAL (no threshold improves OOS)
2. Coefficient sensitivity sweep: VERDICT-NEUTRAL (best combo +0.1pp train, 0% OOS)
3. Component replacement — LOB% as γ=0.15: VERDICT-NEUTRAL (better corr, same accuracy)
4. Component replacement — SwStr% as γ=0.15: DISQUALIFIED (wrong sign, r=−0.071)
5. Component replacement — HR/FB as γ=0.15: VERDICT-NEUTRAL (r=+0.314, no accuracy gain)
6. Z-score normalization diagnostic: looked promising (+12pp BL OOS in diagnostic)
7. T_SB threshold sweep: T_SB=+0.20 found as sweet spot in diagnostic space
8. Authoritative z-score backtest: MARGINAL, Guard FAIL (population stats shifted from enriched subset)
9. Raw LOB swap (xwOBA → LOB, β=0.25, no normalization): BL OOS 75.0% → 72.7%, Guard FAIL
10. SB confirmation gate diagnostic (15 OR-combinations of 4 gates A/B/C/D): all fail guards structurally

---

## CAREER LESSONS DATABASE

File: career_lessons_database.html
Concepts: 88 (through April 24, 2026)
Open in any browser — fully searchable by category

### Lessons from April 24 session:
- Metric Complementarity (FIP vs xERA — what each measures/misses)
- Construct Validity (TRM measured longevity not confidence)
- Ablation Testing a Value Model (ranking coherence vs accuracy delta)
- Invariant Testing (permanent anchors that catch subtle bugs)
- Asymmetric Category Damage (roto: .188 AVG actively hurts roster)
- Content Inventory Management (signals are scarce — ration them)
- Misdiagnosed Root Cause (FanGraphs "block" was actually a sampling filter)
- Load-Bearing Components (remove it, known-correct output breaks — that's the definition)
- Documentation Drift (multiple "handoff" docs diverge fast — one source of truth only)
- Measurement Validity (new backtest returned worse numbers — model was fine, evaluation script was wrong)

### Lessons from April 25 session:
- Sensitivity Analysis (systematic parameter testing — vary one thing at a time, measure signal count AND accuracy, use 2025 OOS as guard rail)
- Build Order Discipline (add variables individually, backtest each, ablation confirm — never add multiple variables at once)
- Signal vs Stats Impact (a new variable can have modest signal impact but large trade tool impact if it changes projected counting stats)
- Trade Tool Architecture (signals inform projected stats, not verdicts directly)
- Recovery Path Thinking (always know your path back before you need it)
- PA-Weighted Mean Reversion (barrel rate, small samples: PA / (PA + STAB) as blend weight)
- Data Architecture Audit Before Building (confirmed career_primary_velo is ONE float, not per-pitch — always trace exact field structure)
- Labeling Noise as Signal Filter (Statcast relabeled pitch types 2022-2025 — 238/251 pitchers "added" new pitches but 95% are artifacts)
- Verdict-Neutral Layers (a modifier can be correctly built yet not move verdicts if tier gaps exceed multiplier magnitude)
- Stacking vs Threshold (three ×0.90 bearish flags = ×0.729 compound, but tier gap is binding constraint)

### Lessons from April 26-27 session:
- Additive vs Multiplicative Penalties (multiplicative ×0.95 is verdict-neutral at standard tier gaps; additive flat penalties cross tier boundaries)
- Sensitivity Sweep Design (sweep each parameter independently, maximize training accuracy, validate OOS)
- Career Baseline vs Static Average (comparing player to their own historical norm is more powerful than league average)
- Data Source Exhaustion Documentation (when all programmatic routes blocked, document exact URL structure and failure mode)
- Infrastructure-Ready Feature (build the plumbing even when data isn't available — wiring takes minutes later vs hours)
- Worry Index / Model Silence as Signal (absence of luck signal is itself informative with preseason context)
- Temporal Validity (April signals require separate validation from in-season rolling — never mix track records)
- Content Flywheel Architecture (April calls → Big Board → rolling tracker → accountability audit is self-reinforcing)
- Financial Motivation vs Binary Flag (security gap — how far below market — is the real variable, not contract year yes/no)
- Two-Path Luck Normalization (wOBA declining while xwOBA stays flat = BABIP luck depleting; different recovery timelines)

### Lessons from April 29 session (Session 9):
- Simulation as Architecture Test (simulate all records against the alternative — run the whole population; edge cases appear automatically)
- False Signal Archaeology (ERA_all_sc created phantom buy signals — excluded disaster starts inflated ERA; ask "are these real or artifacts?")
- Baseline Coverage as Research Risk (53% match rate reveals true population scope; understanding WHY data is missing as important as getting more)
- Preliminary vs Validated (Cohort 3 at 96.4% is promising, not a finding; n=9 means one misclassification swings accuracy 11pp)
- N<10 as a Hard Stop (any cohort/signal combination with n<10 gets explicit warning flag; coin-flip variance dominates below 10 observations)

### Lessons from Sessions 11-13 (add to database):

**Projection Model Lessons:**
- Backtest Population vs Production Population (diagnostic using enriched subset produced gains that evaporated in authoritative backtest — always validate population stats against full qualifying population)
- Scale Imbalance as Hidden Architecture Flaw (multi-component formula can be single-variable if one component's magnitude dwarfs others — ERA-FIP at 99.3% of pitcher buy score)
- Complementary Positioning (we don't beat Steamer on projections — we add luck signal layer Steamer can't replicate; differentiate where unique)
- Playing Time as Projection Foundation (counting stat projections are meaningless without accurate PA/IP — Grisham getting 2.5x too many PA invalidates every downstream calculation)
- IL Status as Real-Time Signal (static projections need dynamic adjustment — injury status changes daily)
- Validation Sample Integrity (Backtest B direction accuracy 88.6% looks identical to luck signal OOS because they're measuring the same phenomenon from different angles)

**Content/Community Lessons:**
- Accountability as Differentiation (most analysts make picks and disappear — publicly tracking week-over-week with honest misses builds compounding trust)
- CBS vs ESPN Ownership Arbitrage (CBS players are more sophisticated — they find value faster; window between "model identifies" and "CBS corrects" is narrow; publish early in week)
- Community Validation in Real Time (HonorableJudgeIto validated Wood's swing angle with Baseball Savant — Reddit community fact-checks and extends sound methodology)
- Hidden Gem Timing Problem (by the time you trust a signal PA-wise, CBS-level players have already found the player; lower PA threshold OR publish Monday morning)

---

## LOGO

File: signal_fantasy_logo.html (in outputs)
Three versions: Full logo, Circle profile picture, Icon/favicon
Colors: Deep navy (#0d1117) + sky blue (#38bdf8)
Typography: Georgia serif
Tagline decision pending: "Luck is noise. We find the signal."

---

## GITHUB STATUS

Repository: DustinSLovell/Signal-Fantasy-Pipeline (private)
Current commit: April 30, 2026 — Session 14 committed and pushed
Last push: April 30, 2026

Files added through Session 14:
- fetch_fantasypros_ownership.py
- build_hitter_launch_angle.py
- lineup_context.py
- build_lineup_context.py
- projection_backtest_A.py
- projection_backtest_B.py
- projection_backtest_C.py
- model_architecture_explainer.md
- pitcher_buy_model_testing_rationale.md
- era_simulation.py (diagnostic only)
- data/hitter_launch_angle.json
- data/hitter_batting_slot_2026.json
- data/team_lineup_context_2026.json
- data/projections_external/ (Steamer + ZiPS 2025)
- data/backtest_A_hitters_2025.csv + pitchers
- data/backtest_B_results_v2.csv
- data/backtest_C_hitters_2025.csv + pitchers

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

   **Canary checks:**
   ```
   # Ben Rice should be C-eligible (Fix F, April 24)
   python -c "import json; d=json.load(open('data/player_positions.json')); print([p for p in d if 'Rice' in p])"

   # Sanchez should be rank 21+ catchers (fixed April 30)
   python -c "import json; d=json.load(open('data/player_values.json')); catchers=[p for p in d['players'] if p.get('pos')=='C']; catchers.sort(key=lambda x: x.get('league1_value',0),reverse=True); [print(i+1,p['name'],p.get('league1_value')) for i,p in enumerate(catchers[:25]) if 'Sanchez' in p.get('name','')]"

   # AVG penalty should exist in score_value.py (Fix C, load-bearing)
   grep -n "0.220\|avg_liability\|AVG.*penalty" score_value.py | head -5

   # Playing time module wired
   grep -n "_blend_pa\|_STEAMER_PA" stat_projections.py | head -5

   # Launch angle columns in output
   grep -n "la_delta\|la_trending" score_luck.py | head -5

   # xwOBA career regression wired (April 30 fix)
   grep -n "xwoba_3yr\|XWOBA_PA_STAB" score_value.py | head -5
   ```

   Expected results:
   - Ben Rice: appears with C in position list ✅
   - Sanchez: rank 21 or higher among catchers ✅
   - AVG penalty: line found in score_value.py ✅
   - Playing time: _blend_pa found in stat_projections.py ✅
   - Launch angle: la_delta found in score_luck.py ✅
   - xwOBA regression: xwoba_3yr and XWOBA_PA_STAB found ✅
   If ANY fail → stop and report before proceeding

5. Check dashboard is running (localhost:8000)
6. State assumptions explicitly — if anything in this doc seems inconsistent with what Dustin describes, flag it immediately

### MONDAY WORKFLOW (every week):
```
python run_pipeline.py --write
python fetch_ownership.py
python weekly_update.py --update
python weekly_update.py --report --top 15
```
Note: weekly_update.py --update has duplicate guard — won't increment if data unchanged

### SESSION GOAL FORMAT:
- "Model improvement" → focus on accuracy, signal quality, backtest
- "Infrastructure" → focus on dashboard, pipeline, tooling
- "Content" → focus on article writing, social, publishing
- "Trade tool" → focus on trade analyzer development
- "Stability" → focus on validation, documentation, cleanup
- "Projection" → focus on projection engine accuracy

### SESSION END CHECKLIST (every thread, no exceptions):
1. Run validate_formulas.py → confirm 37/37 PASS
2. If ANY model change → run ablation test on affected tier
3. If ANY model change → run backtest_pitcher_composite.py and confirm numbers match validated baselines
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
- "Why is the pitcher buy score functionally single-variable and what did we do about it?"
- "What does Backtest C tell us about our positioning vs Steamer?"
- "What is the playing time module and why was Grisham the worst failure case?"
- "Why does the launch angle delta live as a display column rather than a model weight?"
- "What is the Hidden Gem timing problem and how do we solve it?"
- "What is the difference between Backtest A, B, and C?"
- "What are the two rulers and why are they not interchangeable?"
- "What is the Two-Track In-Season Signal System and why does it matter for publishing?"

---
*End of handoff. Update this file at end of every session before closing.*
*Download and save to C:\Users\dusti\fantasy-baseball\thread_handoff.md*
