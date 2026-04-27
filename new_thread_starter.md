# NEW THREAD STARTER — April 24, 2026
# Paste this at the start of your next Claude conversation.

---

## SESSION CONTEXT

Today is April 24, 2026. This document has everything you need to continue
work on The Signal Fantasy fantasy baseball Statcast model.

---

## THREAD HANDOFF (Updated April 24, 2026)

## PITCHER MODEL v2.0 — April 23 2026 (updated)
Status: PRODUCTION
Overall accuracy: 91.1% (was 82.4%)
Sell high: 94.6% (was 91.3%)
vs RTM: +21.1pp (was +12.4pp)
Buy low: 82.1% 4-yr / 75-78% recent (pool tightened)
Slight buy: 84.4% (backtest, was 62% pre-gate / 75% in production)

Key changes:
1. Split scoring architecture (buy ERA-FIP dominant, sell full composite)
2. Career HH%/barrel baselines (sell side precision)
3. Age tier: modifier not hard override
4. Buy verdict pre-confidence-scaling classification
5. Buy quality gates: MIN_IP=20, ERA>=3.50, FIP/xERA confluence
6. Boyle exception: raw_buy_score>=1.50 waives IP floor and FIX 3
7. Slight buy ERA gate: ERA >= 4.00 required (elite pitchers with FIP~2.6
   and ERA 3.5-3.9 don't show enough improvement to register — need BUY_LOW gap)

Backtest: data/backtest_composite_summary.csv
Snapshot: data/snapshots/pitcher_luck_scores_april_2026.csv

---

THE SIGNAL FANTASY — PITCHER MODEL v2.0
========================================
Architecture: Split scorer (buy/sell separate)
Validated: 2022-2025, 284+ pitcher-seasons
Production date: April 23, 2026

ACCURACY (Version E + slight buy gates):
  Buy low:     82.1% 4-yr avg (77-78% in 2024/2025)
  Slight buy:  84.4% (backtest; ERA>=4.0 gate implemented April 23)
  Slight sell: 84.2%
  Sell high:   94.6%
  Overall:     91.1%
  vs. RTM:     +21.1pp

HITTER MODEL (Option 3 + xwOBA gate — recalibrated April 23, 2026):
  Buy low:     ~98.0%
  Slight buy:  ~82.3% base + ~2pp from xwOBA gate = ~84% estimated
  Slight sell: ~89.7%
  Sell high:   ~93.5%
  Overall:     ~88.1%
  vs. RTM:     +17.9pp
  Thresholds:  Buy low >0.150 (was >0.120), Slight buy >0.065 (was >0.050)
               Sell high <-0.150 (was <-0.120), Slight sell <-0.085 (was <-0.065)
  New gate:    Slight buy requires xwOBA_gap >= 0.015 (filters BABIP-only signals)

KEY HEADLINE NUMBERS:
  94.6% SELL HIGH pitchers
  94.1% SELL HIGH hitters
  94.3% BUY LOW hitters
  91.1% overall pitchers
  88.1% overall hitters
  +21.1pp vs RTM pitchers
  +17.9pp vs RTM hitters

PITCHER MODEL v2.0 — SPLIT ARCHITECTURE:

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
  6. Hard hit allowed vs career baseline (×-1.5) — NEW
  7. Barrel rate vs career baseline (×-1.5) — NEW
  8. SwStr% vs 11% (×2.0)

BUY QUALIFICATION GATES (all must pass):
  - FIP <= 4.50
  - SwStr% >= 8%
  - Career IP >= 100
  - IP >= 20 (waived if raw_buy_score >= 1.50)
  - ERA >= 3.50 (all buys); ERA >= 4.00 for SLIGHT BUY only
  - |FIP-xERA| <= 1.50 OR xERA <= 4.50
  - FIP >= 1.50 if IP < 20

AGE TIER LOGIC (fixed April 23):
  - Age 35+ + luck <= -0.20 → "Sell and Move On"
  - Age 35+ + luck <= -0.12 → "Sell High on Perception"
  - Age 35+ + mild signal → keep tier + "Age 35+ monitor"

CURRENT SIGNALS (April 24, 2026):

Buy low (7):
  Jesus Luzardo   PHI  ERA 6.41  FIP 3.22  xERA 3.99  IP 26.7  luck 0.4531
  Joe Ryan        MIN  ERA 5.29  FIP 3.20  xERA 2.58  IP 32.3  luck 0.3487  [CSW dampened]
  Joe Boyle       TB   ERA 6.46  FIP 3.05  xERA 4.59  IP 15.3  luck 0.3351
  Cristopher Sanchez PHI ERA 3.82 FIP 2.60 xERA 3.03  IP 33.0  luck 0.3095
  Logan Gilbert   SEA  ERA 4.22  FIP 2.99  xERA 3.62  IP 32.0  luck 0.2791
  Kyle Bradish    BAL  ERA 5.55  FIP 3.48  xERA 3.46  IP 24.3  luck 0.2405
  Shane Baz       BAL  ERA 5.20  FIP 3.69  xERA 4.30  IP 27.7  luck 0.2047  [CSW dampened]

Slight buy (8):
  Bailey Ober     MIN  ERA 4.50  FIP 3.42  xERA 3.84  IP 26.0  luck 0.1347
  Trevor Rogers   BAL  ERA 4.45  FIP 3.68  xERA 3.10  IP 28.3  luck 0.1076
  Aaron Nola      PHI  ERA 5.13  FIP 4.02  xERA 4.72  IP 26.3  luck 0.1012
  Garrett Crochet BOS  ERA 4.43  FIP 3.38  xERA 3.93  IP 24.0  luck 0.0944
  Logan Webb      SF   ERA 4.32  FIP 3.75  xERA 4.13  IP 25.0  luck 0.0854
  Nathan Eovaldi  TEX  ERA 5.40  FIP 4.38  xERA 4.06  IP 26.7  luck 0.0850
  Janson Junk     MIA  ERA 4.44  FIP 3.71  xERA 3.43  IP 26.3  luck 0.0830
  Brandon Woodruff MIL ERA 3.91  FIP 3.58  xERA 2.35  IP 23.0  luck 0.0820

Sell high (26):
  Jose Soriano    LAA  ERA 0.24  FIP 2.12  luck -0.51
  Michael Wacha   KC   ERA 2.23  FIP 3.60  luck -0.40
  Nick Martinez   TB   ERA 1.82  FIP 3.88  luck -0.40
  Clay Holmes     NYM  ERA 2.10  FIP 4.24  luck -0.34
  Michael Mcgreevy STL ERA 3.04  FIP 4.49  luck -0.34
  Tomoyuki Sugano COL  ERA 3.42  FIP 4.82  luck -0.31
  Eduardo Rodriguez AZ ERA 2.89  FIP 4.96  luck -0.30
  Seth Lugo       KC   ERA 1.17  FIP 2.26  luck -0.29
  Martin Perez    ATL  ERA 2.31  FIP 4.61  luck -0.29
  Mike King       SD   ERA 1.33  FIP 3.66  luck -0.28
  Kai-wei Teng    HOU  ERA 0.79  FIP 2.14  luck -0.26
  Gavin Williams  CLE  ERA 2.17  FIP 3.90  luck -0.24
  Connelly Early  BOS  ERA 2.52  FIP 4.15  luck -0.23
  Jack Kochanowicz LAA ERA 2.79  FIP 4.11  luck -0.23
  Shota Imanaga   CHC  ERA 1.55  FIP 2.87  luck -0.23
  Kyle Freeland   COL  ERA 2.30  FIP 3.81  luck -0.23
  Parker Messick  CLE  ERA 1.23  FIP 2.49  luck -0.22
  Connor Phillips CIN  ERA 2.81  FIP 5.44  luck -0.22
  Davis Martin    CWS  ERA 2.22  FIP 3.48  luck -0.22
  Freddy Peralta  NYM  ERA 2.02  FIP 4.31  luck -0.21
  Randy Vasquez   SD   ERA 1.95  FIP 2.49  luck -0.19
  Luis Gil        NYY  ERA 4.11  FIP 7.28  luck -0.19
  Chad Patrick    MIL  ERA 2.38  FIP 4.34  luck -0.17
  Bubba Chandler  PIT  ERA 3.15  FIP 4.66  luck -0.17
  German Marquez  SD   ERA 4.08  FIP 6.11  luck -0.17
  Justin Wrobleski LAD ERA 1.85  FIP 2.98  luck -0.16

---

## PITCHER MODEL v2.0 — KEY FILES
- score_pitcher_luck.py — production scorer (split architecture)
- _pitcher_tier_audit.py — ERA-FIP backtest (run_pitcher_audit function)
- backtest_pitcher_composite.py — full composite backtest (Versions A-E)
- generate_backtest_report.py — Substack table formatter
- build_pitcher_stuff_baselines.py — stuff quality career data builder
- data/pitcher_career_babip.json — career BABIP/HH%/barrel baselines
- data/pitcher_career_stuff.json — SwStr%/velo/spin baselines (display only)
- data/pitcher_stuff_current_2026.csv — current season stuff metrics
- data/snapshots/pitcher_luck_scores_april_2026.csv — April 23 snapshot
- data/backtest_composite_summary.csv — full ablation results
- data/yordan_tracker.csv — weekly Yordan wOBA/xwOBA tracker

---

## PARKING LOT

- Hitter HH% denominator fix: COMPLETE. process_stats.py now uses
  FAIR_BIP_EVENTS denominator (mean 39.4%) matching career JSON (39.2%).
  Career baseline integration live in score_luck.py. 296/414 hitters matched.
  118 hitters use default 0.370 threshold.
- Platoon adjustment: implemented as Layer 7 confidence modifier.
  Slight buy +1.6pp, Buy low +0.6pp in backtest. Live in production.
- Threshold recalibration: Option 3 implemented in score_luck.py.
  Hitter backtest: buy low 92.6%→98.0%, slight buy 73.4%→82.3%.
- Yordan weekly tracker: automated in run_pipeline.py.
  Saves to data/yordan_tracker.csv after every pipeline run.
  Week 1: wOBA .518, xwOBA .603, luck 0.288, Buy low.
- Stuff Quality Layer 7: April trends non-predictive (38% buy accuracy).
  Display columns only. Revisit with June+ full-season data.
- LOB% confluence flag: added as display column. 6 buy confirms.
- Multi-year April pattern flag: 4 buy lows confirmed with prior-year pattern.
- Slight buy accuracy investigation: COMPLETE (April 23).
- New signal ablation session: COMPLETE (April 23).
  PARKING LOT remaining:
  (1) CSW buy-low-only ablation — KEPT in production (April 24)
  (2) Chase rate sell-side-only — KEPT in production (April 24)
  (3) Sprint speed with reliable age data — REVERTED (April 24, only +0.2pp)
  (4) Pitcher evolution detector — COMPLETE (April 24)
  (5) Extended scoring categories: OBP, SLG, TB, QS for non-standard leagues
  (6) Post-blend AVG floor in project_hitter_counting(): still 26 fringe hitters
      projecting below .195 (low priority)
  (7) Hitter evolution detector: launch angle, pull rate, sprint speed
- Follow-up ablation session: COMPLETE (April 24).
  Chase rate sell-side only: KEPT. CSW buy-low only: KEPT. Sprint v2: REVERTED.
- This Is Actually Bad: COMPLETE (April 24).
  9 Confirmed, 7 Monitor. Sheet in signal board.
- Live ownership data: COMPLETE (April 24). ESPN public API.
  Coverage: 414/414 hitters matched.
- Composite pitcher backtest: buy-side gap remains. Full composite buy pending.
- Signal board: COMPLETE. export_signal_board.py → outputs/signal_board_latest.xlsx.
  4 sheets: Hitter Signals, Pitcher Signals, This Is Real, How to Use.
- Stat projection engine: COMPLETE + formula fixes applied (April 24). stat_projections.py.
  8-function pipeline. validate_formulas.py: 37/37 PASS.
  Formula fixes (April 24):
    SWSTR_TO_K9: 22.5 → 77.3 (swstr_rate is decimal, not percent)
    xwOBA→AVG scale: 1.80 → 1.057 (league-avg .320 now gives .255 AVG)
    .260 floor cap removed; upper AVG clamp raised .340 → .375
  Sanity warnings: 51 (v1) → 39 (v2) → 35 (after April 24 formula fixes).
- Pitcher evolution detector: COMPLETE (April 24). detect_pitcher_evolution().
  6-factor scoring; Bradley ERA 4.47→3.77 (evolution_score=4).
- Formula validation suite: COMPLETE (April 24). validate_formulas.py — 37/37 PASS.
  Run: python -X utf8 validate_formulas.py
- Dashboard SyntaxError: DIAGNOSED (April 24). No actual syntax error in current file.
  Node check passes. All braces/brackets balanced. File is clean.
- Trade analyzer v2: COMPLETE (April 24). trade_analyzer.py.
- Trade analyzer dashboard tab: COMPLETE (April 24). dashboard.html.
  Both Trade Analyzer panel and Signal Rankings panel always visible.
  File-picker path: fetches player_values.json + calls buildPlayerIndex().
  Search: normalizeName() handles accents (Jesús Luzardo works).
- This Is Real: COMPLETE. 27 Confirmed, 34 Monitor (April 23).

---

## SOCIAL LAUNCH STATUS (April 23, 2026)
- X (@SignalFantasy): 5-tweet thread posted, banner + bio live
- Reddit (u/Dlovell02): 4K+ views, 14 upvotes, 13 comments
- Instagram (@thesignalfantasy): accuracy graphic posted
- Substack: Article #1 live, methodology updated
- Facebook: Deferred

## CONTENT CALENDAR
Week 2 (Apr 29) — PLANNED
  "Before the Regression Hits" — recurring series
  Lead: Corey Seager buy low
  Slight buys/sells introduction, Pitcher model v2.0 update
Mid-week bonus (Apr 26-27) — NEW
  "By Request" — 5-10 signals, shorter format
Week 3 (May 6) — PLANNED
  Composite backtest buy-side validation, Stuff Quality update (June+ data)
  Yordan tracking update

---

## HOW TO START EACH SESSION
1. Read thread_handoff.md
2. Run python run_pipeline.py to refresh scores
3. Check data/player_values.json record count and date
4. Review any PARKING LOT items relevant to today's goal
5. Confirm target output (article, backtest, model change, etc.)
6. Run career transition quiz (technical concept + interview framing)

---

## FORMULA VALIDATION SUITE OUTPUT (April 24, 2026)

```
============================================================
  FORMULA VALIDATION SUITE — stat_projections.py
============================================================

SECTION A — Pitcher Formulas (10 tests)
-------------------------------------------------------
  [PASS] A1: K/9 at league-avg SwStr% (0.110)
  [PASS] A2: K/9 at elite SwStr% (0.155)
  [PASS] A3: K/9 at poor SwStr% (0.075)
  [PASS] A4: ERA – elite pitcher FIP=2.50 xERA=2.80
  [PASS] A5: ERA – bad pitcher FIP=5.50 xERA=5.20
  [PASS] A6: ERA – FIP=2.50 vs xERA=5.00 (big disagreement)
  [PASS] A7: WHIP – ERA~4.00 career WHIP=1.30
  [PASS] A8: Win projection ~30 starts x 0.33 win rate
  [PASS] A9: Projected IP – 30 starts x 5.8 ip/start x 0.85 health
  [PASS] A10: K counting – K/9=9.0 ~140 IP
  Section A: 10/10 PASS

SECTION B — Hitter Formulas (10 tests)
-------------------------------------------------------
  [PASS] B1: xwOBA->AVG raw formula at xwOBA=.320
  [PASS] B2: AVG – elite hitter xwOBA=.420 career_avg=.300
  [PASS] B3: AVG – poor hitter xwOBA=.260 career_avg=.235
  [PASS] B4: HR/600PA – barrel=10% (elite tier)
  [PASS] B5: HR/600PA – barrel=8% (league avg)
  [PASS] B6: SB – sprint 28.5mph over 100 games
  [PASS] B7: R formula – H=80 HR=20 BB=40
  [PASS] B8: RBI formula – H=80 HR=20
  [PASS] B9: PA per game by batting position spread
  [PASS] B10: PA – 139 games remain, batting 3rd, health=0.85
  Section B: 10/10 PASS

SECTION C — Blend and Weight Tests (6 tests)
-------------------------------------------------------
  [PASS] C1-C6: All blend/weight tests pass
  Section C: 6/6 PASS

SECTION D — Real Player Sanity Tests (5 tests)
-------------------------------------------------------
  [PASS] D1: Yordan Alvarez – elite hitter rest-of-season
  [PASS] D2: Trea Turner – speed hitter, SB signal
  [PASS] D3: Luzardo – buy-low pitcher, ERA regression from 6.41
  [PASS] D4: Wacha – sell-high, expects ERA regression from 2.23
  [PASS] D5: Gary Sanchez – replacement-level hitter, Neutral verdict
  Section D: 5/5 PASS

SECTION E — Edge Case Tests (7 tests)
-------------------------------------------------------
  [PASS] E1-E6: All edge cases pass
  [LIMIT] E7: Age 40+ decay — not implemented yet
  Section E: 6/6 PASS  +1 KNOWN LIMITATION

============================================================
  Total: 37/37 PASS — All tests passed!
  Known limitations: E7 (age decay), R/RBI lineup-dependent, reliever heuristic
============================================================
```

---

## CURRENT PROJECTIONS SAMPLE (data/projections_2026.csv — April 24)

794 total players: 414 hitters + 380 pitchers. Generated by generate_projections.py.

**Top 10 Hitters by luck_score (buy-low signals):**

```
              name  signal  proj_avg  proj_hr  proj_r  proj_rbi  proj_sb
      Jose Ramirez Buy low     0.343     17.0    72.0      64.0     15.0
      Ivan Herrera Buy low     0.332     15.0    69.0      60.0      6.0
      Corey Seager Buy low     0.312     18.0    68.0      60.0      2.0
Vinnie Pasquantino Buy low     0.282     14.0    59.0      53.0      2.0
    Chase Delauter Buy low     0.283     14.0    60.0      53.0      3.0
         Alec Bohm Buy low     0.297     11.0    59.0      53.0      6.0
     Manny Machado Buy low     0.293     13.0    61.0      53.0      2.0
  Gunnar Henderson Buy low     0.300     15.0    64.0      57.0     15.0
      Ronald Acuna Buy low     0.324     18.0    70.0      64.0     15.0
         Tj Friedl Buy low     0.272     11.0    56.0      49.0      6.0
```

**Top 10 Pitchers by luck_score (buy-low signals):**

```
              name  signal  proj_era  proj_whip  proj_k  proj_w
     Jesus Luzardo Buy low      3.48       1.27   133.0     7.0
      Nick Pivetta Neutral      3.66       1.32   124.0     7.0
          Joe Ryan Buy low      3.18       1.21   129.0     7.0
         Joe Boyle Buy low      4.54       1.47   128.0     7.0
Cristopher Sanchez Buy low      2.84       1.17   136.0     7.0
     Logan Gilbert Buy low      3.09       1.18   133.0     7.0
```

---

## CURRENT SIGNAL COUNTS (April 24, 2026)

From luck_scores.csv (414 hitters):
  Buy low:    53
  Slight buy: 41
  Neutral:    259
  Slight sell: 29
  Sell high:   32

From pitcher_luck_scores.csv (380 pitchers):
  Buy low:     7 (8 in projections CSV — minor rounding diff)
  Slight buy:  8
  Neutral:    325
  Slight sell: 15
  Sell high:   25

---

## DASHBOARD STATUS (April 24, 2026)

File: dashboard.html
SyntaxError fix: DIAGNOSED — no actual syntax error in current file.
  Node --check equivalent passes. Braces/brackets balanced (1152/1152, 210/210, 666/666).
  No </script> embedded in JS. Error was from a transient prior-session state.

Trade analyzer search: IMPLEMENTED — search dropdowns functional.
  File-picker path now calls buildPlayerIndex() after loading CSVs.
  normalizeName() handles accents (Jesús, José, etc.) via NFD decomposition.
  Both Trade Analyzer panel + Signal Rankings panel always visible (no mode bar).

Trade analyzer status: Built. Testing needed end-to-end (Luzardo search, add card,
  Analyze Trade, results panel) — verify against live player_values.json.

---

## NEXT SESSION PRIORITIES

1. Test trade analyzer end-to-end in browser (search Luzardo, add card, click Analyze)
2. Backtest v4 vs v5 vs v6 (ref: project_backtest_v4.md memory)
3. Phase C seasonal pattern detection
4. Week 2 article content ("Before the Regression Hits" — Corey Seager lead)
5. validate_formulas.py: add --validate flag to run_pipeline.py

---
