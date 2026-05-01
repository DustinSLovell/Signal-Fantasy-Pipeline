#!/usr/bin/env python3
# Appends sections 9-17 to thread_handoff.md
import textwrap

text = textwrap.dedent("""

---

## SECTION 9: PIPELINE (every script)

**Automated:** `python run_pipeline.py --write`

**Manual order:** fetch_ownership → fetch_stats + fetch_pitcher_stats → process_stats + process_pitcher_stats → score_luck + score_pitcher_luck → build_pitcher_pitch_mix → generate_projections → score_value --write → export_signal_board → validate_formulas

**Monday workflow:**
```
python run_pipeline.py --write
python fetch_fantasypros_ownership.py
python fetch_cbs_rank.py
python weekly_update.py --update
python weekly_update.py --report --top 15
```

**score_luck.py** — Layer 1 hitter scoring. Inputs: hitters_statcast.csv + all career JSONs. Outputs: luck_scores.csv (423 hitters, 74 columns). SACRED — never modify without ablation + validate_formulas.py.

**score_pitcher_luck.py** — Layer 1 pitcher scoring, v2.0 split architecture. Outputs: pitcher_luck_scores.csv (402 pitchers). Buy gates: FIP<=4.50, SwStr>=8%, CareerIP>=100, IP>=20 (waivable at raw_buy>=1.50), ERA>=3.50 base, ERA>=3.75 Buy Low, ERA>=4.00 Slight Buy.

**stat_projections.py** — Layer 2 projections. Key constants: SWSTR_TO_K9=77.3 (line ~52), PARK_FACTORS_PROJ dict, CAREER_BA_WEIGHT=0.65, LG_H9=8.8, LG_BB9=3.1. Playing time: _blend_pa() for hitters (Steamer-weighted by games played tier), _blend_ip() for pitchers (55% Steamer SP, 80% Steamer RP, cap 70 IP). Known issue: G/GS null for all pitchers — OK, _blend_ip uses Steamer GS for SP/RP classification.

**generate_projections.py** — Layer 2 runner. Outputs: data/projections_2026.csv (794 players, 20 cols, pf_adj_applied flag).

**score_value.py** — Layer 3 value engine. Inputs: luck CSVs + projections + career_quality.json + player_positions.json. Outputs: data/player_values.json (825 players). Key: xwOBA career regression (XWOBA_PA_STAB=250), barrel regression (LG_BARREL=0.066, BARREL_PA_STAB=250), AVG penalty (proj_avg<0.220 load-bearing). Run: --write then --check-invariants.

**trade_analyzer.py** — Layer 4. CBS FPTS _compute_cbs_fpts() + replacement level surplus. Verdict thresholds: >=75% Strong, >=60% Favorable, >=40% Neutral, >=25% Unfavorable, <25% Avoid.

**run_pipeline.py** — Full runner. Encoding fix April 28: encoding="utf-8", errors="replace" in Popen (Windows CP1252 was crashing on tqdm progress bar output).

**fetch_ownership.py** — ESPN ownership → data/player_ownership_2026.csv (3,797 players). injury_status column all ACTIVE (ESPN endpoint limitation — infrastructure ready, real data when better endpoint found).

**fetch_fantasypros_ownership.py** — FP cross-platform ownership. 598 unique FP players, 69.7% match rate. Adds fp_ownership/fp_espn_own/fp_yahoo_own to player_ownership_2026.csv. --check flag for probe mode.

**fetch_cbs_rank.py** — CBS YTD FPTS scraper. 9 position pages (C/1B/2B/SS/3B/OF/U/SP/RP). Outputs: data/cbs_rank_2026.csv (545 players). _CBS_ALIASES = {"cameron schlittler": "cam schlittler"}. _norm_cbs() applies alias after normalization. 42% pitcher match rate: structural (CBS publishes top-100/position = max 178 pitchers vs our 402). --check flag.

**validate_formulas.py** — 37/37 PASS required before shipping any change. Never modify tests to make them pass — fix the underlying code.

**weekly_update.py** — Tracker. --init: bootstrap week1 baseline. --update: add weekN columns (duplicate guard — won't increment if luck_scores.csv unchanged). --report --top 15: Substack-ready markdown. Sign convention pitchers: week1_woba=ERA, week1_xwoba=FIP (sign-flipped so +delta = prediction correct). Significance thresholds: WOBA_THRESH=0.020, XWOBA_THRESH=0.015.

**build_hitter_launch_angle.py** — LA delta builder. Career: v4_april_{2022-2025}.csv (MIN_CAREER_BBE=100). Current: hitters_statcast.csv (MIN_CURRENT_BBE=50). Outputs: data/hitter_launch_angle.json (454 records, 148 with full delta).

**backtest_multi_year_v7.py** — Authoritative hitter backtest (train 2022-2024, OOS 2025). Source of truth for all published accuracy numbers.

**projection_backtest_A.py** — Projection vs RTM (n=235H/165P). is_sp fix: steamer_gs >= 10. Career: explicit [2022,2023,2024] loop (no FG_YEARS contamination).

**projection_backtest_B.py** — Signal-adjusted projections (v2 production). Active multipliers: wOBA x1.08/1.04/0.96/0.92, HR buy-side x1.05/1.02, pitcher SH ERA x1.10.

**projection_backtest_C.py** — Six-way vs Steamer + ZiPS. Honest FAIL. ERA bias win (our +0.25 vs Steamer +0.41).

**era_simulation.py** — DIAGNOSTIC ONLY. ERA_all_sc vs filtered. 389 pitchers, 7 verdict changes. Decision: keep filtered ERA. Not production.

**Key data files:**
- luck_scores.csv — 423 hitters, 74 columns (authoritative hitter signal output)
- pitcher_luck_scores.csv — 402 pitchers (authoritative pitcher signal output)
- data/projections_2026.csv — 794 players, 20 cols
- data/player_values.json — 825 players
- data/cbs_rank_2026.csv — 545 players (367H + 178P), YTD CBS FPTS
- data/player_ownership_2026.csv — 3,797 players
- data/calls_tracker.csv — 169 calls (127H + 42P), week1-7 columns
- data/career_quality.json — CQS floors (11 manually corrected April 24)
- data/hitter_career_platoon.json — 489 batters, mean gap=-0.019
- data/hitter_career_k_pull.json — 643 career, 415 current, 327 with deltas
- data/hitter_career_discipline.json — chase rate baselines (672 batters)
- data/hitter_career_sprint.json — sprint speed (849 players)
- data/hitter_launch_angle.json — 454 records, LA delta
- data/pitcher_career_babip.json — career BABIP/HH%/barrel
- data/pitcher_career_csw.json — CSW baselines (611 pitchers)
- data/pitcher_pitch_mix_delta.json — Phase 2 flags (251 pitchers)
- data/hitter_batting_slot_2026.json — 452 batters, modal batting slot
- data/team_lineup_context_2026.json — 30 teams + league avg, OBP/SLG per slot
- data/contract_year_2026.csv — 31 players (13 manual + 18 Spotrac merge)
- data/prior_teams_2025.json — 998 players, 2025 team assignments
- Steamers 2025 batters.csv (root) — 4,140 players, MLBAMID + PA/HR/AVG/wOBA
- Steamers 2025 pitchers.csv (root) — 5,215 players, MLBAMID + IP/GS/ERA/WHIP/K
- career_lessons_database.html — 88+ career concepts (open in browser)
- data/backtest_audit_hitters.csv — 305 row-level hitter backtest
- data/backtest_audit_pitchers.csv — 284 row-level pitcher backtest

---

## SECTION 10: PARKING LOT

### TIER 1 — Do immediately

**Week 3 article (May 5-6 deadline):** Monday run → update → report. Lead: Chapman -17.2° LA delta. Second: CBS divergences (Soto, Betts). Third: Ohtani quiet worry. Feature: April Big Board (17/23 = 73.9%). Must also release luck score spreadsheet (promised Article #2).

**Weekly tracker mechanism classifier (HIGHEST PRIORITY build):** Mechanism column exists (confirmed/refuted/contact_improving/etc.). Gap: article narrative framing per mechanism. Needed for Week 3+ articles to tell the story behind tracker movement.

**April Big Board:** Consolidated view of all April calls with current status. Player | call date | signal | current wOBA vs xwOBA | mechanism | resolved status. Track record proof-of-work document.

**White paper Section 10:** Live track record table — needs 2-3 more weeks data. Then publish to whitepapersonline.com.

### TIER 2 — This week

**Hidden Gem detector (formal):** Query: fp_ownership<35%, wOBA>.330, xwOBA_gap>-0.020, luck>-0.085, PA>=75. Current: Rumfield (COL,10%), Herrera (STL,29%), Aranda (TB,27%), Bogaerts (SD,31%). Run Monday morning, publish Tuesday.

**Pitcher Slight Buy sensitivity:** n=4/yr too thin. Ablation: ERA floor 4.00→3.75 to grow SB sample. Gate B (HR/FB >+0.03 above career): best candidate, OOS 80.0% (+7.8pp) but n=3 SB OOS — retest after 2026 season.

**is_article_worthy() gate (build after Week 3):** SELL HIGH: owned>58% OR fp_rank<150. BUY LOW: owned>10% minimum.

**Platoon splits into projections:** DEFERRED mid-May (150+ PA). Infrastructure: hitter_career_platoon.json (489 batters).

### TIER 3 — Not blocking
- Dashboard sort bug (absolute magnitude)
- Trade tool search click bug
- ESPN injury status real endpoint
- Nola/Rogers ERA gap fix (~1 run miscalibration)
- Post-blend AVG floor (26 hitters below .195)
- fp_rank refresh (shows preseason, not in-season)

### RESEARCH AGENDA (post-2026 season)
- Worry Index threshold validation (50+ resolved flags — mid-2027)
- Financial motivation backtest (50+ per cohort/signal — expand contract match rate)
- Track 2 in-season validation (2026 = collection year; validate for 2027 publishing)
- Age-weighted chase rate calibration (mid-2027)
- xwOBA β=0.25 replacement in pitcher buy score (revisit post-2026)
- Gate B SB confirmation retest (n≈2/year currently — needs 2026 season to grow)

### CONTENT PIPELINE
- CBS rank divergence as weekly content engine (May 1+): sort by |ESPN_rank - CBS_rank| where signal fires
- "Why April Signals Matter Most": publish mid-May (paid tier anchor)
- "How I Built This in 10 Days with AI": publish mid-June (6-8 weeks track record)
- Live 2026 Accuracy Tracker: paid tier dashboard, build once 30+ calls resolved (mid-June)
- Weekly luck score spreadsheet: release this week (promised Article #2)
- Spotrac Phase 2: Baseball Reference friv/free_agents.fcgi for historical 2022-2024 contracts

### TRADE TOOL STATUS
| Component | Status |
|-----------|--------|
| CBS FPTS regression R2=0.983H/0.909P | COMPLETE |
| Replacement level calculator | COMPLETE |
| Lineup context module | COMPLETE |
| Playing time module | COMPLETE |
| Backtest A+B+C | COMPLETE |
| League settings UI | NOT BUILT |
| 5-10 real trade stress tests | NOT DONE |
| Search click bug | TIER 3 |

---

## SECTION 11: TRADE TOOL (known issues)

Architecture: trade_analyzer.py. CBS FPTS via _compute_cbs_fpts(). Replacement level via replacement_level.py. 12-team replacement levels: C=289.8 | 1B=275.7 | 2B=277.7 | 3B=267.0 | SS=293.9 | OF=296.3 | SP=221.5 | RP=157.0.

**Bug 1 — Skenes/Rice smell test FAIL:** Giving Skenes (ERA 0.95) for Rice (Sell High, wOBA .492) returns "Favorable for Rice side." Root cause: C positional scarcity overweights Rice surplus (+44) vs Skenes surplus (+33). Fix needed: top-20 player giveaway cannot return favorable verdict.

**Bug 2 — Pitcher net stats misleading:** Giving Skenes shows ERA -1.50 as "positive change." Fix: replacement-level baseline for net stats.

**Bug 3 — Signals weight verdict directly:** Current: signal tier feeds verdict logic. Correct: signal feeds projected stats only → stats determine value → verdict = comparison. Fix location: trade_analyzer.py verdict calculation.

**Bug 4 — Search click:** Dashboard onClick intermittent. Tier 3.

---

## SECTION 12: DASHBOARD

File: dashboard.html. Run: `python -m http.server 8000` → localhost:8000/dashboard.html

**All 7 fixes COMPLETE (April 24, 2026):**
1. View Toggle: Simple/Advanced switcher
2. Signal Filter Pills: live counts
3. Park Change Badges: 43 players (Hayes, Lowe, Alonso, Caballero, Nimmo + 38)
4. Simple View: 3-column (Player | Signal | Why 120-char)
5. Pitcher Ownership: 374/380 matched
6. IL Status Banner: yellow warning (static)
7. Trade Search: normalizeName() handles accents

**CBS YTD column (May 1, 2026):**
Added { key:'cbs_rank', label:'CBS YTD', fmt:'int' } to HITTER_COLS and PITCHER_COLS.
Placement: after owned_pct. F.int formatter: NaN → "—". sortKey() pushes null to bottom.

**Current signal counts (May 1):**
Hitters: 61 BL | 17 SB | 278 N | 30 SS | 37 SH
Pitchers: 8 BL | 7 SB | 354 N | 8 SS | 25 SH

**Known bugs:** Advanced View sort (absolute magnitude), trade search click, IL per-player (banner covers).

---

## SECTION 13: CAREER LESSONS (key concepts — full database in career_lessons_database.html)

**Additive vs Multiplicative Penalties:** Multiplicative ×0.95 cannot cross tier boundaries. Score 0.115 × 0.95 = 0.109 (stays Slight Buy). Score 0.115 − 0.020 = 0.095 (drops to Neutral). Root cause why Versions B+C were verdict-neutral; Version D produced 42 changes.

**Two-Ruler Measurement:** Backtest ruler (peaks 0.08-0.12) and production ruler (±0.15+) permanently different scales. Mixing produces 23 cases → 100% overfitted. Never cross rulers. This is the most important methodological principle.

**Load-Bearing Components:** Component is load-bearing if removing it breaks a known-correct output. AVG penalty keeps Sanchez correctly ranked (ablation C confirmed). Never remove without verifying downstream invariant still holds.

**Model Silence as Signal:** When results AND contact quality both diverge from baseline AND no luck signal fires, the model silence is itself the signal. Devers: K rate spike, HH collapse, xwOBA also depressed — no lucky bounce coming. The absence of a buy signal is more informative than any sell signal.

**Independence Requirement for Comparison Columns:** CBS rank scraped externally is independent (their formula, their data, their audience). Computing CBS rank from our own projected stats (with Buy Low ×1.08 HR multiplier) is circular. The scraped rank means something precisely because we did NOT compute it.

**ESPN = Reputation, CBS = Production:** Soto ESPN#7/CBS#186 is the story: one market prices name, the other prices YTD production. When a luck signal also fires, the three-layer narrative (CBS gap + ESPN gap + model view) is maximally compelling content.

**Market Divergence as Content Engine:** A 179-rank divergence requires no explanation. Readers instantly understand one market is wrong. Model signals tell WHY; divergence tells WHERE THE MONEY IS.

**Platform Audience Calibration:** ESPN = casual players (name recognition). CBS = serious players (find value faster). Same player: 7% ESPN, 60% CBS. Substack audience = CBS-level readers. Calibrate content accordingly.

**Two-Location Problem:** score_luck.py park-adjusted the luck signal. stat_projections.py needed a SEPARATE park adjustment for projected counting stats. Correction in one layer does not propagate to another. Audit end-to-end when adding new data dimensions.

**Import Circularity as Design Constraint:** When clean architecture creates circular imports, the pragmatic solution (parallel dict with sync comment) is correct. Code quality means maintainability, not abstract purity.

**Playing Time as Projection Foundation:** Grisham getting 2.5× too many PA invalidated every downstream calculation. Fix playing time first. Counting stats are meaningless without accurate PA/IP.

**Dry-Run Protocol for Scrapers:** Always add --check flag. Run first to confirm: (1) URLs 200, (2) data structure matches expectations, (3) sample values sensible. Prevents corrupting production CSVs.

**Threshold Design from Distribution Inspection:** Set |pf_delta|>=0.02 park filter by checking what it excluded (LAD→ATL=0.00, trivial moves). Never set thresholds without examining edge cases at the distribution boundary.

**Park Sensitivity Hierarchy:** HR most park-sensitive (×1.5 raw PF delta). R/RBI moderate (×0.7). AVG least (×0.5 — defense partially neutralizes). Never apply flat multiplier across all stat categories.

**Content Flywheel Architecture:** April calls → Big Board → rolling tracker → accountability audit. Self-reinforcing machine. Each piece references the others. This is not just a model — it is a publishing system with compounding trust.

**Preliminary vs Validated:** Cohort 3 at 96.4% is promising, not a finding. n=9 means one misclassification swings accuracy 11pp. N<10 = hard stop for publishing accuracy claims.

**Simulation as Architecture Test:** Run the whole population — edge cases appear automatically. ERA_all_sc test found 7 verdict changes in 389 pitchers; 3 artifacts, 4 real. Spot checks miss systematic patterns.

**False Signal Archaeology:** ERA_all_sc created phantom buy signals from excluded disaster starts. Ask "are these real or artifacts?" for every unexpected signal change from a new methodology.

**Baseline Coverage as Research Risk:** 53% contract match rate reveals true population scope. Understanding WHY data is missing is as important as getting more data.

**Complementary Positioning:** We lose to Steamer/ZiPS on raw MAE. Our value is luck signal detection (88.6%/88.0% BL/SH direction accuracy) that preseason systems cannot replicate. Never compete where you'll lose — differentiate where you're unique.

**Accountability as Differentiation:** Most analysts make picks and disappear. Publicly tracking with honest misses builds compounding trust. The calls tracker IS the product, not just the article.

**CBS vs ESPN Ownership Arbitrage:** CBS finds value faster. Window between "model identifies" and "CBS corrects" is narrow. Run Monday morning, publish Tuesday — not Wednesday.

**Community Validation in Real Time:** HonorableJudgeIto validated Wood's swing angle on Reddit. Independent community fact-checking validates methodology publicly and generates future article content ("readers who dug deeper confirmed...").

**Hidden Gem Timing Problem:** By the time enough PA for PA-based trust, CBS-level players may have already found the player. Lower PA threshold (75 PA instead of 150) OR publish Monday morning.

**Recovery Path Thinking:** Before making a change, know your path back. Git commit before risky changes. Canary check before declaring success.

**Build Order Discipline:** Add variables individually. Backtest each. Ablation-confirm. Never add multiple variables simultaneously — attribution becomes impossible.

**Sensitivity Sweep Design:** Vary one parameter. Measure BOTH signal count AND accuracy. Use 2025 OOS as guard rail. The optimal constant is not always the highest-accuracy one — consider signal count implications (too restrictive gate = 4 signals/year = statistically meaningless).

---

## SECTION 14: SESSION START/END CHECKLISTS

### SESSION START CHECKLIST (no exceptions)
1. Read entire thread_handoff.md before acting
2. Confirm today's goal with Dustin
3. Ask Dustin to run in Claude Code:
```bash
grep -n "ERA >= 4.00" score_pitcher_luck.py
grep -n "3.75" score_pitcher_luck.py
grep -n "0.150" score_luck.py
grep -n "H_KP_K_PENALTY" score_luck.py
grep -n "_blend_pa" stat_projections.py
grep -n "XWOBA_PA_STAB" score_value.py
grep -n "PARK_FACTORS_PROJ" stat_projections.py
python -c "import pandas as pd; df=pd.read_csv('luck_scores.csv'); print('cbs_rank' in df.columns, df['cbs_rank'].notna().sum())"
python -X utf8 validate_formulas.py
```
Expected: all greps find matches, cbs_rank ~330, 37/37 PASS.
4. Check Sanchez invariant (rank 21+ catchers). If any check fails: STOP and report.

### SESSION END CHECKLIST (no exceptions)
1. python -X utf8 validate_formulas.py → 37/37 PASS
2. If model change → ablation test + backtest numbers match
3. If score_value.py change → --write then --check-invariants → Sanchez 21+
4. List every file modified
5. Update parking lot
6. Add new career lessons to Section 13
7. Update accuracy numbers if model changed
8. Update current signals if pipeline re-run
9. Regenerate this document completely (overwrite)
10. git add . && git commit -m "Session N — [description]" && git push
11. Tell Dustin: "Download updated thread_handoff.md to C:\\Users\\dusti\\fantasy-baseball\\thread_handoff.md"

### PERMANENT INVARIANTS (after every score_value.py --write)
- Yordan Álvarez: top 20 overall
- Cal Raleigh: top 4 catchers (relaxed until PA > 150 — re-tighten mid-May)
- Drake Baldwin: top 5 catchers
- William Contreras: top 9 catchers (MIL lineup penalty is real signal — 9.3% RBI reduction)
- Will Smith: top 12 catchers
- **SANCHEZ TEST: rank 21+ catchers. If top 15 → STOP.**
  AVG penalty (proj_avg ~.200) is load-bearing. xwOBA regression (XWOBA_PA_STAB=250) prevents hot-start noise.

### QUIZ BANK
- What is the Sanchez Test and why does it exist?
- What are the two rulers and why not interchangeable?
- Why did Version D produce 42 verdict changes when B+C were neutral?
- Why does the pitcher buy score functionally ignore xwOBA?
- What is the Two-Track In-Season Signal System?
- Why is the park factor a parallel dict in stat_projections.py instead of imported from score_luck.py?
- Why is Soto ESPN#7/CBS#186 article content and not a data error?
- What does the Worry/Get Hyped Index flag and why is model silence the signal?
- Why is Cam Schlittler CBS#3 but Neutral verdict?
- Why did Ben Rice get Sell High with wOBA .492?
- What is the Hidden Gem timing problem?
- Why does Cohort 3 at 96.4% get a N<10 warning?
- What are the three park factor amplifiers and why do they differ?
- What is the is_sp tautology bug and how was it fixed?

---

## SECTION 15: CONTENT STRATEGY

### Publishing Cadence
Monday morning: full pipeline + ownership + weekly_update
Tuesday night: publish Substack article
Wednesday: Reddit post with summary
Every 4 weeks: evaluate Track 2 movers for fresh April-style call

### Article Structure (repeating template)
1. Opening hook: one stat line demanding explanation
2. Accountability: honest check-in on prior calls
3. Yordan Tracker: 2-sentence recurring update
4. Lead buy: highest-confidence known player
5. Feature: deep-dive one player (300-400 words, specific Statcast numbers)
6. Sell: high-profile sell (owned >58%)
7. Pitchers: 2 buys + 1-2 sells (brief)
8. Rotating: Worry/Get Hyped | Hidden Gem | CBS Divergence | Big Board
9. Honorable mentions: 3-5 brief callouts
10. Week N+1 tease

### Ownership Tiers
- >87%: pure trade signal, no caveat
- 58-87%: available in most 12-team leagues
- 20-58%: available in standard 12-team leagues
- 11-20%: deeper league pickup
- <11%: universal waiver wire
- <5%: dynasty or speculative only
Two questions before featuring: Is he owned in standard 12-team (>58%)? If not, what format does he matter in?

### Hidden Gem Criteria
fp_ownership<35% AND wOBA>.330 AND xwOBA_gap>-0.020 AND luck>-0.085 AND PA>=75
Use fp_ownership (CBS blend) not ESPN owned_pct. Run Monday, publish Tuesday.
Current: Rumfield COL (10%), Herrera STL (29%), Aranda TB (27%), Bogaerts SD (31%)

### Worry/Get Hyped Criteria
WORRY: fp_rank<50, wOBA 40+pts below 3yr xwOBA, luck>-0.085, PA>=75. Framing: "Don't buy this dip — model sees real struggle."
GET HYPED: fp_rank>100, wOBA 40+pts above 3yr xwOBA, luck<0.085, PA>=75. Framing: "He's mashing and it's completely real."
Current WORRY: Devers SF (K spike+HH collapse — most serious), Adames SF, Ohtani LAD (subtle).
Current GET HYPED: 0 active.

### Two-Track System (publishing discipline)
Track 1 = April Signals (validated 86.1%/89.7%) — published Substack signals, full authority.
Track 2 = weekly_update tracker — hypothesis only, "data moving in right direction" framing.
NEVER mix. Track 2 needs its own backtest before publishing accuracy numbers.

### Reddit Strategy
Post from u/Dlovell02 (personal, more credible). Lead title with player names. First comment: expand with stat table. Engage counterarguments publicly. Don't post every week — save for compelling weeks. One Substack mention max in comments.

### Paid Tier ($10/month — activate at 200-500 free subscribers)
Free: one Buy Low, one Sell High, one pitcher per article.
Paid: full signal list, hidden gem, all pitchers, accuracy tracker, trade analyzer.
Build Live Accuracy Tracker for paid tier (mid-June 2026 when 30+ calls resolved).

### Commercial Roadmap
1. Paid tier: 200-500 free subscribers → activate
2. Trade analyzer beta: after 5-10 real trade stress tests
3. "Built in 10 Days" article: mid-June 2026
4. White paper: whitepapersonline.com (Section 10 needs 2-3 more weeks)
5. Podcast: Year 2 (live calls format)
6. Football product: Year 2-3 (nflfastR)
7. Career: VP Analytics / Director AI Strategy portfolio

---

## SECTION 16: DATA NOTES & DISAMBIGUATION

**Player-specific disambiguation:**
- Devers: now SF (was BOS) — park change in luck_scores.csv
- Adames: now SF (was MIL)
- Bichette: now NYM (was TOR) — now Slight Buy +0.115
- Ozuna: PIT (was ATL)
- Both Max Muncys: LAD Muncy ID 571970 (age 36, Slight Sell), ATH Muncy ID 691777 (age 24, Sell High) — correctly disambiguated
- Vásquez: WITH accent (Randy Vásquez) in CSV
- Murakami: CWS (not ARI)
- Ben Rice: C-eligible in player_positions.json (Fix F). CBS #6. Sell High = sell at peak value, not collapse predicted.
- Cam Schlittler NYY: CBS #3 pitcher (ERA 1.96, FIP 1.41). NEUTRAL verdict — ERA too good for buy gate (needs ERA>=4.00 for Slight Buy). NOT a data error.
- Paul Skenes PIT: CBS #17. Sell High (−0.151). ERA 0.95 < FIP 2.54 → ERA below FIP → results better than metrics → sell at peak perceived value.
- James Wood WSH: CBS #3 hitter. wOBA .424, xwOBA .479. Neutral (no 3yr baseline as rookie → no Get Hyped flag). Performance REAL: barrel 29.9% vs career 14.4%, swing angle change confirmed by Baseball Savant.
- Yordan tracker: wOBA .501, xwOBA .581, luck +0.213. Buy Low normalizing (was +0.288 Week 1) but still valid.

**K/9 constant (critical):**
SWSTR_TO_K9 = 77.3 (line ~52 in stat_projections.py)
NOT 22.5 (old incorrect formula that produced K%, not K/9)
Derivation: 0.11 SwStr × 77.3 = 8.5 K/9 (league average)
Canary: grep -n "77.3" stat_projections.py

**GitHub:**
Repo: DustinSLovell/Signal-Fantasy-Pipeline (private)
Last push: May 1, 2026 (commit 1cbf493 — Worry/Get Hyped Index documentation)
Push every session for IP protection.

**Two-document memory:**
thread_handoff.md (C:/Users/dusti/fantasy-baseball/) → Claude.ai memory
CLAUDE.md (same dir) → Claude Code memory
Keep in sync. Never create variants. One file each, always overwritten.

---

## SECTION 17: TRAINING WINDOW & ARCHITECTURAL DECISIONS

**Why 2022+ only:**
1. Deadened ball standardization (2021-2022): MLB centralized ball production mid-2021 through 2022. Pre-2022 HR/FB rates and BABIP norms not comparably predictive.
2. Universal DH adoption (2022): pitchers no longer bat; lineup construction changed fundamentally.
Pre-2022 career baselines ARE retained for individual player context only — not cross-player comparisons.

**Product positioning vs Steamer/ZiPS (permanent):**
Backtest C confirmed: we lose to Steamer and ZiPS on every raw MAE metric. Expected and irreducible — they use full preseason context; we project from April data only.
Our value: signal direction accuracy (88.6% Buy Low, 88.0% Sell High) that preseason systems cannot replicate.
One notable win: ERA bias. Our +0.25 vs Steamer +0.41 — we are LESS biased on ERA direction. Publishable.
Never publish MAE head-to-head vs Steamer. Correct framing: "Complementary to Steamer, not competing."

**ERA_all_sc decision (April 29):**
Keep filtered ERA (qualifying starts only, MIN_START_IP=2.0). ERA_all_sc creates phantom buy signals from excluded disaster starts. Skenes is the only legitimate case (ERA-FIP gap would narrow) — but his sell signal is BABIP/LOB-dominant anyway. Revisit after full season if filtering creates systematic bias.

---

*End of thread_handoff.md — Sections 1-17 complete.*
*Overwrite completely at end of every session. Single source of truth.*
*Save to: C:\\Users\\dusti\\fantasy-baseball\\thread_handoff.md*
""")

with open(r'C:\Users\dusti\fantasy-baseball\thread_handoff.md', 'a', encoding='utf-8') as f:
    f.write(text)

with open(r'C:\Users\dusti\fantasy-baseball\thread_handoff.md', encoding='utf-8') as f:
    lines = f.readlines()
print(f'Total lines: {len(lines)}')
print('Append complete.')
