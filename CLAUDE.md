# CLAUDE.md — The Signal Fantasy
# Auto-read by Claude Code at session start.
# Last updated: May 7, 2026 (Sessions 1-42, consolidated)
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

### Hitter Model (Version E — recalibrated May 5, 2026 / Session 35):
- Thresholds: Buy Low >0.175 | Slight Buy: ELIMINATED | Slight Sell <-0.085 | Sell High <-0.150
- Backtest thresholds (Ruler 1): BL >=0.045 | SB: eliminated | SS <=-0.040 | SH <=-0.065
- config.py: H_PROD_BUY_LOW=0.175, H_PROD_SLIGHT_BUY=0.175 (equal — SB impossible)
- config.py: H_BT_BUY_LOW=0.045, H_BT_SLIGHT_BUY=0.045 (equal — SB impossible)
- Chase rate modifier (sell-side): gap >0.040 → ×1.10, >0.060 → ×1.15
- Platoon adjustment: Layer 7 — uses career baseline from hitter_career_platoon.json

### Additive Modifier Architecture (Version D — hitters only):
All hitter buy dampeners use flat additive penalties (NOT multiplicative).
Penalties accumulate in `_buy_penalty` column; capped at H_MAX_COMBINED_PEN=0.040.
- H_KP_K_PENALTY=0.010 | H_KP_PULL_PENALTY=0.008 | H_HH_PENALTY=0.012
- H_SPEED_PENALTY=0.010 | H_CHASE_PENALTY=0.008 | H_MAX_COMBINED_PEN=0.040
- Age weights: H_CHASE_AGE_WEIGHT_U25=0.40, H_CHASE_AGE_WEIGHT_26_27=0.70

### Pitcher Model v2.0 / Version F (split architecture; SB eliminated May 5, Session 37):
- BUY side: ERA-FIP dominant (×0.60 ERA-FIP, ×0.25 xwOBA, ×0.15 BABIP)
- SELL side: 8-component composite (BABIP, LOB%, ERA-FIP, ERA-xERA, HR/FB, HH%, barrel, SwStr%)
- Classification from RAW score BEFORE confidence scaling
- CSW buy-low-only modifier: csw_gap >+0.025 → ×1.10, <-0.025 → ×0.90
- Slight Buy eliminated (62.0% accuracy, -18.0pp vs RTM = no edge)
- config.py: P_PROD_BUY_LOW=0.175, P_PROD_SLIGHT_BUY=0.175 (equal — SB impossible)
- config.py: P_BT_BUY_LOW=1.40, P_BT_SLIGHT_BUY=1.40 (equal — SB impossible)

### Buy Qualification Gates (ALL must pass for a buy signal):
- FIP <= 4.50 | SwStr% >= 8% | Career IP >= 100
- IP >= 20 (waived if raw_buy_score >= 1.50 — Boyle exception)
- ERA >= 3.50 (all buys) | ERA >= 3.75 (Buy Low only) | ERA >= 4.00 (Slight Buy only)
- |FIP-xERA| <= 1.50 OR xERA <= 4.50
- FIP >= 1.50 if IP < 20

### Financial Motivation Cohort (display-only):
_assign_cohort() in score_luck.py. contract_cohort column in luck_scores.csv.
31 players loaded (13 manual + 18 Spotrac merge). Do NOT add model weight until backtest complete.

### Pitch Mix Modifier (Phase 2, verdict-neutral):
6-flag stacking system. Bearish: abandonment, velo_drop, rv_degrade (each ×0.90 on buy score).
Bullish: effectiveness, velo_gain (×1.10), rv_improve (×1.05). Status: VERDICT-NEUTRAL in backtest.

---

## MEASUREMENT FRAMEWORK — TWO RULERS, BOTH VALID

### Ruler 1: Backtest (backtest_multi_year_v7.py)
- Formula: `luck_score = xwoba_gap * 0.60 + babip_luck * 0.40` (April-only, ~100-150 PA)
- Score range: peaks at 0.080-0.120
- Thresholds: H_BT_BUY_LOW=0.045, H_BT_SELL_HIGH=-0.065, H_BT_SLIGHT_SELL=-0.040
- **Use for**: signal direction validation, A vs B modifier comparisons

### Ruler 2: Production (score_luck.py, score_pitcher_luck.py)
- Formula: 4-component weighted sum + 10+ modifiers, full-season PA window
- Score range: regularly exceeds ±0.175
- Thresholds: H_PROD_BUY_LOW=0.175, H_PROD_SELL_HIGH=-0.150, H_PROD_SLIGHT_SELL=-0.085
- **Use for**: live fantasy decisions, Substack publishing

These rulers are NOT interchangeable.

---

## VALIDATED ACCURACY NUMBERS (DO NOT PUBLISH DIFFERENT NUMBERS)

### Hitter Model — Version E (PRODUCTION as of May 5, 2026):
| Signal | Train 2022-24 n | Train acc | OOS 2025 n | OOS acc | 4yr pooled |
|--------|-----------------|-----------|------------|---------|------------|
| Buy Low | 43 | 95.3% | 23 | 100.0% | 91.4% |
| Slight Buy | **0** | **eliminated** | **0** | **eliminated** | — |
| Slight Sell | 56 | 89.3% | 26 | 76.9% | — |
| Sell High | 36 | 91.7% | 14 | 100.0% | — |
| **Overall** | **135** | **91.9%** | **63** | **90.5%** | **91.4%** |
| vs RTM | — | — | — | — | **+23.2pp** |

### Pitcher Model v2.0 Version F (PRODUCTION as of May 5, 2026):
| Signal | n | acc |
|--------|---|-----|
| Buy Low | 33 | 90.9% |
| Slight Buy | **eliminated** | **62.0% / -18.0pp vs RTM** |
| Slight Sell | 21 | 76.2% |
| Sell High | 20 | 100.0% |
| **Overall** | **87.7% pooled** | **82.0% OOS** |

### Numbers that are INVALID — do not publish:
- "~89.0% train / ~93.5% OOS" — production thresholds on backtest scores → 23 cases → noise
- "v7 Backtest: 85.9% pooled" or "86.1%" — superseded by Version E (91.9% / 90.5%)
- Any Slight Buy accuracy claims — tier is eliminated as of Session 35/37

---

## PERMANENT INVARIANTS — RUN AFTER EVERY score_value.py --write

```bash
python score_value.py --check-invariants
```

MUST ALWAYS PASS:
- Yordan Alvarez: top 20 overall
- Cal Raleigh: top 3 catchers (relaxed to top 4 until catcher PA > 150 — early xwOBA variance)
- Drake Baldwin: top 5 catchers
- William Contreras: top 9 catchers

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
- luck_scores.csv — 435 hitters with signals (columns: owned_pct, fp_rank, worry_flag, etc.)
- pitcher_luck_scores.csv — 418 pitchers with signals
- data/projections_2026.csv — 794 players, rest-of-season projections
- data/player_values.json — 773 players, trade values + rankings
- data/player_ownership_2026.csv — 3,795 players (columns: owned_pct, fp_ownership, fp_ros_rank)

### Career baselines:
- data/career_quality.json — CQS floors (11 records corrected April 24)
- data/pitcher_career_babip.json — pitcher career BABIP/HH%/barrel
- data/pitcher_career_csw.json — CSW baselines (611 pitchers)
- data/pitcher_career_pitch_mix.json — 2025 arsenal baseline (318 pitchers)
- data/hitter_career_discipline.json — chase rate baselines (672 batters)
- data/hitter_career_k_pull.json — K% and pull rate baselines (643 career, 415 current)
- data/hitter_career_platoon.json — platoon career baselines (489 batters)
- data/hitter_sprint_speed.json — sprint speed (911 players)
- data/hitter_launch_angle.json — launch angle + career delta (454 records)

### Trade tool:
- trade_analyzer.py — CLI: --give / --receive / --league / --open-slot / --explain / --debug
- replacement_level.py — position replacement FPTS calculator
- league_settings.py — load_league(), get_replacement_level()
- data/leagues/league_1.json — CBS 13-Team | data/leagues/league_2.json — Fantrax 15-Team OBP
- signal_context.py — ELITE_TRACK_RECORD + INJURY_RECOVERY override module (display-only)

### Tracking:
- data/calls_tracker.csv — 169 players (127H, 42P), Week 1 baseline April 22
- weekly_update.py — --init / --update / --report pipeline
- data/ownership_history.json — ownership snapshots (846 players, Week 9 baseline May 5)

### Audit/backtest:
- data/backtest_audit_hitters.csv — 305 row-level hitter backtest (v7 logic)
- data/backtest_audit_pitchers.csv — 284 row-level pitcher backtest (v7 logic)

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
1. fetch_ownership.py → 2. fetch_stats.py + fetch_pitcher_stats.py
3. process_stats.py + process_pitcher_stats.py → 4. score_luck.py + score_pitcher_luck.py
5. build_pitcher_pitch_mix.py → 6. generate_projections.py
7. score_value.py --write → 8. export_signal_board.py → 9. validate_formulas.py

### Weekly article workflow (every Monday):
```bash
python run_pipeline.py --write
python weekly_update.py --update
python weekly_update.py --report --top 15
```
NOTE: --update must be run AFTER run_pipeline.py --write so luck_scores.csv is fresh.

---

## DASHBOARD

File: dashboard.html | Run: launch_dashboard.bat | Access: localhost:8000/dashboard.html
All 7 audit fixes complete as of April 24, 2026. FP rank column added Session 38.

---

## CURRENT SIGNALS SUMMARY (May 7, 2026 — post Version E/F)

Hitters (435 total): Buy Low: 42 | Slight Buy: 0 (ELIMINATED) | Neutral: 321 | Slight Sell: 28 | Sell High: 44
Pitchers (418 total): Buy Low: 8 | Slight Buy: 0 (ELIMINATED) | Neutral: 372 | Slight Sell: 15 | Sell High: 23

Top pitcher buy lows: Luzardo (0.4531), Ryan (0.3487), Boyle (0.3351), C.Sanchez (0.3095), Gilbert (0.2791)
Relievers dormant until 15 IP threshold: Morejón (ERA 8.03, FIP 2.47), Doval (ERA 8.59, FIP 4.81)

---

## IMPORTANT DATA NOTES

- luck_scores.csv uses `owned_pct` for ESPN ownership. `fp_ownership` is in player_ownership_2026.csv only.
- Both Max Muncys correctly disambiguated: Dodgers 571970 (age 36) | A's 691777 (age 24)
- Murakami: CWS (not ARI) — confirmed. Vásquez: spelled with accent (Randy Vásquez) in CSV.
- Raleigh invariant relaxed to top-4 until catcher PA > 150 (mid-May 2026).
- Worry Index concern flags (5): Alonso, Bichette, Soto, Devers, Adames — display-only.

---

## ARCHITECTURAL DECISIONS

### Training Window (2022+)
Pre-2022 excluded from signal training (deadened ball standardization + universal DH adoption 2022).
Pre-2022 career baselines retained for individual player context (not cross-player comparisons).

### Product Positioning vs Steamer/ZiPS
We LOSE to Steamer/ZiPS on all raw MAE metrics. This is expected and irreducible.
Our advantage: **signal direction accuracy** (Buy Low 91.4% / Sell High correct direction 94%+).
**Correct framing**: "Luck signals identify mispriced players Steamer can't detect."
**Do NOT publish** head-to-head raw MAE comparisons. One exception: ERA bias +0.25 vs Steamer +0.41.

### Two-Track In-Season Signal System
- **Track 1 — April Signals** (validated, PRODUCTION): Published Substack signals, 91.9% accuracy.
- **Track 2 — Rolling Signals** (HYPOTHESIS): Tracker/observation only. Never "new signal."
- Do NOT combine Track 2 numbers with Track 1 accuracy until Track 2 has its own backtest.

### Trade Analyzer Architecture (three layers):
1. Signal stat multipliers embedded in base_surplus (Backtest B v2: BL→R×1.08/HR×1.05/RBI×1.08; SH→R×0.92/RBI×0.92)
2. Elite premium × base_surplus → verdict totals (FP≤10→×1.30, ≤25→×1.15, ≤50→×1.05)
3. Signal_adj display (±luck×0.5) is visualization only — NOT in verdict totals
- Opportunity cost: `_repl_level_value(team_count)` → ≤10→4.0, ≤12→2.5, ≤14→1.5, 15+→0.5
- Verdict thresholds: ≥50 STRONG | ≥20 FAVORABLE | ≥5 SLIGHT | ≤-50 AVOID | ≤-20 UNFAVORABLE | ≤-5 SLIGHTLY UNFAVORABLE

### CBS Coefficient Interpretation
Individual CBS coefficients are NOT interpretable as "points per stat" due to multicollinearity.
Use full-vector prediction ONLY. Do NOT use HR coef (0.430) to manually estimate HR value.

---

## PARKING LOT

### TIER 1 — Active

- **Player decline detection layer** — Implemented Session 22 (3 triggers: Seager, Harper, Polanco).
  CQS floors currently dominate for all 3 — no rank change. Altuve NOT triggered (speed -0.47, HH up).
  Needs 50+ triggered player-seasons for multiplier calibration (end-of-2026 earliest).

- **CQS interaction with Buy Low signals** — Ramírez, Stewart, Caminero suppressed by CQS floors
  despite strong Buy Low signals + FP top-3 position rankings. Design requires signal-aware CQS rule.

- **Altuve batting slot verification** — Model 2B #8, FP rank #40. Slot 3 confirmed (n=26 games).
  No decline flags firing (hh_rate_delta=+6.7pp, speed -0.47 above threshold). Gap is FP projecting
  more production at age 36. Decline detection layer is the correct long-term fix.

- **Career BA floor multiplier** — Fix: raise 0.75→0.85 in score_value.py gate
  (career_ba >= 0.240 AND gap >0.040). Henderson: escapes avg_liability floor. 10-line change.
  Sanchez guard safe: career_ba=0.214 < 0.240 → gate fails.

### TIER 2 — Next

- **Ohtani two-way player config** — Add two_way_player flag to league_settings.json; suppress
  pitcher row in standard leagues; show both rows in two-way leagues.

- **SS multi-eligibility noise** — 12/15 SS top-15 flagged vs FP. SS pool diluted by CI/MI eligibles.

- **Skubal Sell High investigation** — FP #1 SP, model #10 with SH signal. Diagnose BABIP vs structural.

- **is_article_worthy() gate** — Filter signals worth featuring from borderline cases.

- **SP divergences check** — Schlittler, Misiorowski, McLean model top-5 vs FP #20-28.
  Verify projected IP and K for rookie arms.

### TIER 3 — Post-season

- OF replacement level review (Jake McCarthy at N=36 may be elevated)
- SS replacement level review (Masyn Winn at 252.2 FPTS — may be too high for 12-team)

### RESEARCH AGENDA (post-2026 season)

- Worry Index sensitivity analysis (need 50+ resolved flagged cases — mid-season 2026)
- Financial motivation backtest: preliminary run complete (n<10 per cohort, not publishable).
  Cohort 3 (Secured) shows 96.4% — needs 50+ per cohort. Source: data/spotrac_contracts_clean.csv.
- In-season signal validation Track 2 — 2026 is collection year. Validate for 2027 publishing.
- Age-weighted chase rate calibration — H_CHASE_AGE_WEIGHT_U25/26_27 are estimated priors.
  Need 30+ age-stratified resolutions (mid-2027 earliest).

### TRADE TOOL / BUILT FEATURES

- CBS FPTS Model: build_cbs_fpts.py. Train R²=0.985H/0.927P, OOS 0.983/0.909.
- Replacement Level: replacement_level.py. Surplus = proj FPTS − Nth-best FPTS at position.
- 12-team standard replacement: C 289.8 | 1B 275.7 | 2B 277.7 | 3B 267.0 | SS 293.9 | OF 296.3 | SP 221.5 | RP 157.0
- League settings Phase 1: league_1.json (CBS 13-Team) + league_2.json (Fantrax 15-Team OBP). BUILT.
- "Did you mean" fuzzy suggestion: _suggest_player() via difflib.SequenceMatcher. BUILT Session 40.
- Gap 1 display fix: Elite-adjusted note "(applied to base surplus, not signal-adjusted)". BUILT Session 41.
- --explain flag: step-by-step CBS valuation walkthrough. BUILT Session 18.
- --debug flag: per-player table (Side/FP/EP/Signal/Luck/BaseSurp/SigAdj/EliteAdj). BUILT Session 40.

### CONTENT PIPELINE

- White paper: signal_fantasy_whitepaper.docx. Sections 1-8 final. Section 10 needs tracker data.
  Publish to whitepapersonline.com after Section 10 + GitHub push.
- "Why April Signals Matter Most" — publish mid-May as paid tier content.
- "How I Built This in 10 Days with AI" — publish after 6-8 weeks of live track record.
- Live 2026 Accuracy Tracker — build once 30+ calls resolved (mid-June 2026 earliest).
- Substack beta posts: outputs/week4_article_draft.md (ready), outputs/reddit_beta_post.md (ready).

### BUILT — Display-only, not yet validated as model modifiers

- Worry Index: worry_flag/breakout_flag/worry_label in luck_scores.csv. Do NOT wire as modifier.
- Financial Motivation Cohort: _assign_cohort() in score_luck.py. contract_cohort column. Display-only.
- Pull Rate Increase as Bullish Signal: needs backtest before wiring.
- Signal Decay Classifier: PURE_LUCK=46 / MECHANICAL=27 / INJURY_RISK=8 in calls_tracker.csv.

### IP PROTECTION + OPERATIONS

- GitHub: DustinSLovell/Signal-Fantasy-Pipeline (private). Push every session without exception.
- Copyright notice on every Substack article: "© 2026 Dustin Lovell / Signal Fantasy."
- Career lessons database: outputs/career_lessons_database.html — maintained in Claude.ai only.
- Check console.anthropic.com monthly for API token consumption.

---

## SESSION END CHECKLIST

1. Confirm validate_formulas.py still 37/37 PASS
2. Note any files modified
3. Push to GitHub (IP protection — run every session without exception):
   ```
   git add .
   git commit -m "Session update - [date]"
   git push
   ```
4. Tell Dustin to update thread_handoff.md in Claude.ai before closing

---

## RECENT CHANGELOG (Sessions 35-42)

--- May 5, 2026 (Session 35) ---
Slight Buy tier eliminated (Version E): H_PROD_BUY_LOW 0.150→0.175, SB impossible (=BL threshold).
H_BT_BUY_LOW 0.040→0.045. New canonical accuracy: 91.9% train / 90.5% OOS / +23.2pp vs RTM.
OOS guard PASS. 12 formerly SB players now show Neutral. Backtest Option D adopted.
37/37 PASS. All invariants PASS.

--- May 5, 2026 (Session 36) ---
Pure diagnostic — no production code changes. Signal vs RTM backtest (8 dimensions, 27 rows).
Key finding: signal advantage concentrated at extremes (BL/SH +8pp vs RTM). 2023 RTM win documented honestly.
High-owned players: signal +12.8pp vs RTM. Low-owned: RTM wins marginally.
Pitcher SB identified as elimination candidate (-18pp vs RTM, worst in full dataset).
outputs/signal_vs_rtm_backtest_s36.csv (NEW).

--- May 5, 2026 (Session 37) ---
Pitcher Slight Buy eliminated (Version F): P_PROD_BUY_LOW 0.175, P_PROD_SLIGHT_BUY=0.175 (SB impossible).
P_BT_BUY_LOW 1.20→1.40, P_BT_SLIGHT_BUY=1.40. 87.7% pooled (+5.3pp), 82.0% OOS (+4.5pp).
Bug fixed: score_pitcher_luck.py CSW reclassification block had hardcoded 0.15/0.07 — now uses config constants.
Post-fix distribution: BL=8, SB=0, N=372, SS=15, SH=23. 37/37 PASS.

--- May 6, 2026 (Session 38) ---
FP ROS rank pipeline wiring: run_pipeline.py now calls fetch_fantasypros_ownership.py before score_luck.py.
score_pitcher_luck.py: ownership merge loads fp_ros_rank → fp_rank column. Coverage 96.7%.
Dashboard: Simple view shows ALL ranks (not just top-50). Advanced view: fp_rank column added.
trade_analyzer.py: trade_value() + evaluate_trade() public API added.
Data refreshed: luck_scores_public_hitters/pitchers.csv (NEW for Substack spreadsheet release).
37/37 PASS. Invariants: Sanchez C#29, Yordan #3, Raleigh C#1, Baldwin C#4, Contreras C#7.

--- May 7, 2026 (Session 39) ---
Trade analyzer output rewrite: ═══ divider blocks, per-player signal descriptions, VERDICT + SIGNAL CONTEXT sections.
League settings integration: _load_league_json() + _compute_roster_n() + _compute_cbs_fpts_league() (OBP substitution).
Opportunity cost: _repl_level_value(team_count) applied when net_received > 0. --open-slot bypasses.
Elite premium: _elite_premium(fp_rank) — FP≤10→×1.30, ≤25→×1.15, ≤50→×1.05. Changes verdicts.
Week 4 article prep: Scenario deltas updated with elite premium + opportunity cost.
L1 vs L2 comparison (Seager trade): -14.5 vs -65.1 (+50.6 OBP premium).
37/37 PASS. All invariants PASS.

--- May 7, 2026 (Session 40) ---
Calibration Option A confirmed (no change): elite_surp = base_surplus × ep is correct architecture.
--debug flag added: per-player table showing Side/FP/EP/Signal/Luck/BaseSurp/SigAdj/EliteAdj.
7-test validation suite: ALL PASS (both-neutral, BL/SH asymmetry, elite cancel, opp cost, --open-slot, give-top-10, league comparison).
Edge guards: single-side error, duplicate player detection, cross-type advisory.
"Did you mean" fuzzy suggestion: _suggest_player() via difflib SequenceMatcher. "Brett Turang" → "Brice Turang (MIL)?" ✓
Beta files: outputs/beta_readme.txt (user guide) + outputs/beta_gaps.txt (3 documented gaps).
37/37 PASS. All invariants PASS.

--- May 7, 2026 (Session 41) ---
Gap 1 display fix: Elite-adjusted line now shows "(applied to base surplus, not signal-adjusted)". Math unchanged.
Seager trade delta confirmed unchanged at -14.5 after display fix.
outputs/week4_article_draft.md (NEW): 3 new Buy Lows (Hayes, Bohm, Carter), 2 Sell Highs (Riley Greene, Holmes), Worry/Get Hyped sections, 3 trade scenarios.
outputs/reddit_beta_post.md (NEW): beta recruitment post with Scenario 2 output, 5 tester profiles.
37/37 PASS. All invariants PASS.

--- May 7, 2026 (Session 42) ---
CLAUDE.md consolidated: 161,957 chars → ~35k. Sessions 1-34 changelogs archived to thread_handoff.md.
Parking lot cleaned: completed items removed, active items retained.
fp_ownership audit: column is correct in player_ownership_2026.csv (fetch_fantasypros_ownership.py).
The error in user's Python snippet was querying luck_scores.csv (which has owned_pct, not fp_ownership).
No Python files needed changes. thread_handoff.md confirmed 297KB — under 500KB threshold, no archiving needed.
37/37 PASS. All invariants PASS.

PENDING MANUAL ACTIONS:
- Publish Week 4 article (outputs/week4_article_draft.md) to Substack
- Post Reddit beta recruitment (outputs/reddit_beta_post.md)
- White paper Section 10 update — use Version F pitcher accuracy (87.7% pooled / 82.0% OOS)
- Career lessons database (Sessions 22-42) — add manually in Claude.ai
- Update thread_handoff.md in Claude.ai with Session 42 summary

---
*This file is the persistent memory for Claude Code sessions.*
*thread_handoff.md in Claude.ai is the persistent memory for Claude.ai sessions.*
*Both must be kept in sync. Update both at end of every session.*
*Full session changelogs (Sessions 1-34) archived in thread_handoff.md under ## ARCHIVED FROM CLAUDE.md.*
