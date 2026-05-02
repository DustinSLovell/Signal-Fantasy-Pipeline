# THE SIGNAL FANTASY — Thread Handoff Document
# Complete project state. Overwrite at end of every session.
# Last updated: May 1, 2026 (Sessions 1–16)
# DO NOT skim. Read every section before acting.

---

## SECTION 1: PROJECT IDENTITY

### Who Dustin Is
Dustin Lovell — CPG (consumer packaged goods) leadership professional actively transitioning into senior tech roles. Target positions: VP Analytics, Director of AI Strategy, RevOps at growth-stage tech companies. The Signal Fantasy is the portfolio project proving data/ML skills with production-level engineering rigor and a live public track record.

Career philosophy: build something real that generates external credibility (public track record, GitHub commit history, published accuracy numbers, live audience) that no resume bullet can replicate. The project must be defensible in an executive interview as "production ML with accountability mechanisms."

Every Claude Code session includes optional career lessons — data/ML concepts that map back to tech leadership interviews. These are logged in career_lessons_database.html (88+ concepts as of May 2026).

### Why This Project Exists
1. Career portfolio: demonstrate ML pipeline development, backtest methodology, statistical modeling, live deployment
2. Fantasy baseball product: monetizable analytics tool targeting serious players (CBS-platform audience)
3. IP protection: timestamped GitHub commits + white paper establish prior art for scoring methodology
4. Content: Substack + Reddit + X publication cadence building an audience before monetization

### Project Timeline
- April 12-14, 2026: Project started from zero
- April 22, 2026: First public article published
- ~10 days from zero to production ML pipeline + live audience
- This is the headline story for the "How I Built This in 10 Days with AI" article (planned post-Week 6)

### Brand Details
- **Name:** The Signal Fantasy
- **Tagline (pending):** "Luck is noise. We find the signal."
- **Gmail:** thesignalfantasy@gmail.com
- **Substack:** signalfantasy.substack.com
- **X:** @SignalFantasy
- **Instagram:** @signalfantasy
- **Reddit:** u/Dlovell02 (personal account — 4yr old, 169 karma — more credible than brand account)
- **GitHub:** DustinSLovell/Signal-Fantasy-Pipeline (private — IP protection)
- **White paper:** signal_fantasy_whitepaper.docx (11 sections, Sections 1-8 final, Section 10 pending track record data)

### Logo
- File: outputs/signal_fantasy_logo.html
- Three versions: Full logo, Circle profile picture, Icon/favicon
- Colors: Deep navy (#0d1117) + sky blue (#38bdf8)
- Typography: Georgia serif

---

## SECTION 2: SOCIAL STATUS (as of May 1, 2026)

### Reddit (u/Dlovell02)
**Post #1 — April 22, 2026:**
- Title: "I built a 7-layer Statcast luck model — here are this week's Buy Low and Sell High signals" (approximate)
- Results: 17K views, 52 upvotes, 43 comments, ranked #2 on r/fantasybaseball that day
- Key engagement driver: combining specific Statcast numbers with actionable buy/sell calls
- Notable comments: community engagement on methodology, requests for pitcher signals
- What worked: lead with the model's outputs (specific players + specific stats), methodology second

**Post #2 — April 30, 2026:**
- Title: Week 2 signals + tracker update + hidden gem (TJ Rumfield)
- Results: 8.6K views, 28 upvotes, 16 comments
- Engagement drop from Post #1 is expected — first post had novelty premium
- Community member VrinTheTerrible subscribed to Substack from Reddit ✅
- Community member HonorableJudgeIto validated James Wood's swing angle improvement with a Baseball Savant link — Reddit community fact-checked the methodology and independently confirmed it. This is signal that methodology is sound enough to withstand public scrutiny.

### Substack (signalfantasy.substack.com)
**Article #1 — April 22, 2026:**
- Title: "Fantasy Baseball: Using Seven Layers of Statcast to Predict Buying/Selling Signals"
- URL: https://open.substack.com/pub/thesignalfantasy/p/fantasy-baseball-using-seven-layers
- Views: 510+ as of April 30
- Subscribers at publish: early days, base established from Reddit traffic
- Known edit still needed: Fix "Without I'm proud to say" → "I'm proud to say" (minor typo)
- Known claim to verify before promoting: "Oneil Cruz hardest ever hit ball in Statcast era" — fact-check this before using in promotion

**Article #2 — April 29, 2026:**
- Title: "Week 2 of the Signal Tracker! New leads, checking on previous calls, and more!"
- Views: 175 as of April 30, 58.33% open rate, 25 recipients
- Traffic sources: Reddit driving ~40% of traffic
- Featured: Seager (buy), Dingler (buy), Chapman (sell), Vargas (sell), Ryan (pitcher buy), Sanchez (pitcher buy), Arrighetti (pitcher sell), Ray (pitcher sell)
- First appearance of Worry/Get Hyped Index in an article
- First Hidden Gem feature: TJ Rumfield (CBS-based discovery)
- Copyright footer: "© 2026 Dustin Lovell / Signal Fantasy" added ✅
- Substack global footer set ✅

### X (@SignalFantasy)
- April 24: Dingler tweet thread — "CBS #6, consensus #17 — buy the value" — posted as timestamp proof before Article #2
- Purpose: timestamp key calls before publication for credibility

### Instagram (@signalfantasy)
- Accuracy graphic posted

### Facebook
- Deferred

### Fangraphs
- Membership: ACTIVE (purchased for Steamer/ZiPS historical projection data download)

### Community Relationships
- **VrinTheTerrible:** Subscribed to Substack from Reddit ✅
- **HonorableJudgeIto:** Validated James Wood swing angle (LA delta +10.6°) with Baseball Savant link on Reddit — independent third-party confirmation of methodology
- **SlightlyAnonymous87:** Mentioned in early sessions (early community engagement)

### Subscriber Growth
- Pre-publish: 0
- Post-Article #1: Base established via Reddit traffic
- Post-Article #2: 25+ recipients (58% open rate suggests quality > casual list)
- Paid tier plan: activate at 200-500 free subscribers

---

## SECTION 3: ARTICLES (full detail)

### Article #1 — "Fantasy Baseball: Using Seven Layers of Statcast to Predict Buying/Selling Signals"
**Published:** April 22, 2026
**URL:** https://open.substack.com/pub/thesignalfantasy/p/fantasy-baseball-using-seven-layers
**Views:** 510+
**Reddit traffic:** Primary source (Post #1 = 17K views)

**Structure:**
1. Intro: What the model does (7-layer Statcast luck scoring)
2. Methodology overview (brief — readers want signals, not math)
3. Buy Low picks (3 hitters)
4. Sell High picks (2 hitters)
5. Pitcher signals (2 buys, 2 sells)
6. Closing + promise of weekly tracker

**Players featured:**

HITTER BUY LOW:
- Vinnie Pasquantino KC: BABIP .177, xwOBA gap positive, unlucky contact quality not reflected in results
- Yordan Álvarez HOU: Week 1 luck score +0.288, wOBA .518, xwOBA .603, gap +.085 — elite contact quality suppressed by BABIP luck
- Trent Grisham NYY: luck +0.409, wOBA .314, xwOBA .401, BABIP .138 (historically low), gap +.087

HITTER SELL HIGH:
- Oneil Cruz PIT: luck -0.191, high BABIP, results overperforming underlying contact quality
- Jordan Walker STL: luck -0.196, BABIP elevated, xwOBA gap negative

PITCHER BUY LOW:
- Jesús Luzardo PHI: ERA 5.08 vs FIP 2.64 — massive gap, unlucky BABIP and LOB
- Kyle Bradish BAL: ERA elevated vs FIP, buy signal

PITCHER SELL HIGH:
- Michael Wacha KC: luck -0.371, ERA 2.23 vs FIP 3.52/xERA 3.52 — outperforming
- Gavin Williams CLE: Slight Sell (mild signal)

**What was promised for next week:** Weekly tracker with check-ins on every call

**Edits still needed:**
- Fix "Without I'm proud to say" → "I'm proud to say"
- Verify Cruz "hardest ever hit ball in Statcast era" before promoting

---

### Article #2 — "Week 2 of the Signal Tracker! New leads, checking on previous calls, and more!"
**Published:** April 29, 2026
**Stats:** 175 views, 58.33% open rate, 25 recipients

**Structure:**
1. Opening: Week 1 accountability (honest "too early to judge" framing)
2. Yordan Tracker: wOBA .518→.510 (Week 1→2), xwOBA .603→.595, luck normalizing — Buy Low holding
3. Lead: Corey Seager TEX — luck +0.344, wOBA .332, xwOBA .378, 91% owned
   - Article framing: "91% owned = you have him, but don't trade him away"
4. Feature: Dillon Dingler DET
   - xwOBA .477 (3rd in MLB at time of writing, behind Yordan and Trout)
   - Barrel rate 19.6% (96th percentile)
   - BABIP .264 vs career .312
   - CBS current #6, consensus #17 — buy the value
   - 72% owned = available in most 12-team leagues
   - Small sample caveat (82 PA) — explicitly honest
   - April 24 tweet referenced as timestamp proof
5. NEW: Slight signals introduction
6. Pitcher Model v2.0 update (Buy Lows: Ryan, Sanchez)
7. NEW: Worry/Get Hyped Index debut
   - Devers CONCERN: K rate 33.3% (+12.5pp above career), HH rate 43.1% (-10.6pp below career)
   - James Wood GET HYPED: barrel 29.9% vs career 14.4%, HH 65.7%
8. Hidden Gem: TJ Rumfield COL — CBS 35% ownership, wOBA .345, Buy Low
9. Pitcher Sell High alerts: Arrighetti, Ray (ERA 2.00 vs FIP 3.59, xERA 4.99)
10. Copyright footer

**What was promised for Week 3:** April Big Board (all April calls), luck score spreadsheet release

---

### Week 3 Article — DUE May 5-6, 2026
**Workflow:** Monday May 5: `run_pipeline.py --write → weekly_update.py --update → --report --top 15`
**Lead story:** Matt Chapman SF — LA delta -17.2° (career 21.0° → current 3.7°) — strongest sell confirmation in entire dataset. His launch angle collapse is the most extreme physical change in 454 tracked players.
**Content opportunities:**
- First week where confirmed/refuted calls should be statistically meaningful (currently 17/23 = 73.9%)
- April Big Board: consolidated view of all April calls, current status
- CBS rank divergences: Soto ESPN #7 / CBS #186 — "the market is still pricing Soto on his name"
- Ohtani worry flag (new): wOBA .390 vs 3yr xwOBA .433 — quiet underperformance from #2 overall

---

## SECTION 4: ACCURACY NUMBERS (authoritative — do not publish different numbers)

### THE TWO-RULER PROBLEM — CRITICAL
The backtest (backtest_multi_year_v7.py) and production scorers use **different score scales and different threshold calibrations**. This is permanent by design, not a bug.

**Ruler 1 — Backtest:**
- Formula: `luck_score = xwoba_gap × 0.60 + babip_luck × 0.40` (April-only, ~100-150 PA)
- Score range: peaks at 0.080-0.120
- Thresholds: H_BT_BUY_LOW=0.040, H_BT_SLIGHT_BUY=0.020, H_BT_SELL_HIGH=-0.065, H_BT_SLIGHT_SELL=-0.040
- **Use for:** signal direction validation, A vs B modifier comparisons

**Ruler 2 — Production:**
- Formula: 4-component weighted sum + 10+ modifiers (full-season PA window)
- Score range: regularly exceeds ±0.150
- Thresholds: H_PROD_BUY_LOW=0.150, H_PROD_SLIGHT_BUY=0.100, H_PROD_SELL_HIGH=-0.150, H_PROD_SLIGHT_SELL=-0.085
- **Use for:** live fantasy decisions, Substack publishing

**NEVER apply production thresholds to backtest scores.** Doing so produces ~23 evaluable cases (vs 305 with calibrated thresholds) and overfits to noise. "~89.0% train / ~93.5% OOS" is an INVALID number — it came from this mistake. Do not publish it.

---

### HITTER MODEL — Version D (Production — adopted April 26, 2026)

| Signal | Train 2022-24 n | Train acc | OOS 2025 n | OOS acc |
|--------|-----------------|-----------|------------|---------|
| Buy Low | 55 | 91.3% | 25 | 96.0% |
| Slight Buy | 56 | 73.5% | 22 | 90.9% |
| Slight Sell | 56 | 89.3% | 26 | 76.9% |
| Sell High | 36 | 91.7% | 14 | 100.0% |
| **Overall** | **187** | **86.1%** | **87** | **89.7%** |
| vs RTM | — | — | — | **+17.9pp** |

**Version A baseline (no modifiers):** 84.4% train (n=211) / 89.4% OOS (n=94)
**Version D improvement:** +1.7pp train / +0.3pp OOS / 42 real verdict changes
**Why n dropped 211→187 in train:** additive penalties correctly downgrade borderline buys to Neutral (excluded from eval by design)
**OOS guard PASS:** 89.7% ≥ 87.0% threshold

**Calibration history:**
- Version A: no modifiers (baseline)
- Version B: multiplicative K%/pull — verdict-neutral (train Δ=-0.1pp, OOS Δ=-0.1pp)
- Version C: B + HH rate — verdict-neutral (0.0pp both)
- Version D: additive K%/pull/HH/speed/chase — +1.7pp train, +0.3pp OOS, 42 verdict changes — **ADOPTED**

**Production thresholds (config.py):**
- Buy Low: luck_score > 0.150 (raised from 0.100 April 22 after early overfiring)
- Slight Buy: luck_score > 0.100 AND xwOBA_gap >= 0.030 AND xwOBA < 0.380
- Slight Sell: luck_score < -0.085
- Sell High: luck_score < -0.150

**Slight Buy gates (updated April 25, 2026) — ALL must pass:**
- xwOBA_gap >= 0.030: removes BABIP-only signals (28.6% accuracy below this threshold)
- xwOBA < 0.380: removes already-elite hitters (25% accuracy above 0.380 — ceiling effect)
- luck_score > 0.100 floor: removes weak signals in 0.065-0.099 range (16.7% accuracy)

---

### PITCHER MODEL v2.0 (split architecture — April 23, ERA floor April 25)

| Signal | n | acc |
|--------|---|-----|
| Buy Low | 33 | 90.9% |
| Slight Buy | 10 | 60.0% → post ERA floor ~84.4% |
| Slight Sell | 21 | 76.2% |
| Sell High | 20 | 100.0% |
| **Overall** | **84** | **85.7%** (2024 single-year backtest) |
| vs RTM | — | **+17.5pp** |

**ERA gate changes (April 25):** ERA >= 3.75 for Buy Low (was 3.50), ERA >= 4.00 for Slight Buy only
This change raised Buy Low OOS accuracy +7.3pp by removing early-season noise signals.

---

### PROJECTION MODEL ACCURACY — Backtest A/B/C

**Backtest A (projection vs RTM, n=235 hitters / 165 pitchers, 2025 OOS):**
- wOBA: Model 0.0342 vs RTM 0.0397 → **+13.9% better**
- ERA: Model 0.878 vs RTM 1.012 → **+13.2% better**
- HR: Model 6.256 vs RTM 6.693 → **+6.5% better**
- AVG: RTM 0.0198 vs Model 0.0216 — RTM wins (known weakness)
- WHIP: RTM 0.155 vs Model 0.194 — RTM wins (known weakness)

**Backtest B v2 (signal-adjusted direction accuracy):**
- Buy Low hitters: **88.6%** improved wOBA vs April baseline (39/44)
- Sell High hitters: **88.0%** declined wOBA vs April baseline (22/25)
- Pitcher Buy Low ERA: **100% improved** (n=7, avg ΔERA = -1.08)
- Pitcher Sell High ERA: **100% worsened** (n=9, avg ΔERA = +1.88)

**Active signal adjustments in Backtest B v2 (production):**
- wOBA: ×1.08 Buy Low / ×1.04 Slight Buy / ×0.96 Slight Sell / ×0.92 Sell High
- HR: ×1.05 Buy Low / ×1.02 Slight Buy (buy side only; sell side removed — hurts MAE)
- Pitcher Sell High: ERA×1.10, WHIP×1.05, K×0.95
- Pitcher Buy Low: WHIP×0.95, K×1.05 (ERA multiplier removed — was hurting MAE)
- REMOVED: AVG multipliers all tiers, HR sell-side, Pitcher Buy Low ERA

**Backtest C (six-way: Naive / RTM / Steamer / ZiPS / Model / Signal-adjusted):**
Result: **We do NOT beat Steamer or ZiPS on any raw projection metric**. This is expected and irreducible.
- They use full preseason context; we project from April data only
- ERA bias: our +0.25 vs Steamer +0.41 — **we are LESS biased on ERA despite higher MAE** (publishable)
- K MAE: ours 39.4 vs Steamer 21.9 — structural gap, partially fixed by is_sp tautology fix
- R bias: our +0.82 (near-unbiased) vs Steamer -8.33 — lineup context module strength

**Product positioning (from Backtest C):** Complementary to Steamer/ZiPS, not competing. Our value is luck signal detection (88.6%/88.0% Buy Low / Sell High direction accuracy) that preseason systems cannot replicate. Never publish head-to-head raw MAE vs Steamer — it will not favor us.

---

### HEADLINE NUMBERS (use everywhere — all valid):
- **89.7%** overall hitter accuracy (2025 OOS, Version D)
- **96.0%** Buy Low hitter accuracy (2025 OOS, n=25)
- **100.0%** Sell High hitter accuracy (2025 OOS, n=14)
- **86.1%** overall hitter accuracy (2022-2024 train, Version D)
- **85.7%** overall pitcher accuracy (2024 single-year)
- **+17.9pp** vs Regression to Mean (hitters, 2025 OOS)
- **88.6% Buy Low** / **88.0% Sell High** direction accuracy (Backtest B v2)
- Projection beats RTM by **13%** on wOBA and ERA

---

### INVALID NUMBERS — NEVER PUBLISH:
- "~89.0% train / ~93.5% OOS" — production thresholds on backtest scores → 23 cases → noise
- "v7 Backtest: 85.9% pooled" — superseded by train/OOS split table above
- Any pitcher Slight Buy accuracy number from before ERA gate fix (old gates = ~62%)

---

## SECTION 5: MODEL ARCHITECTURE (full detail)

### FOUR-LAYER STACK

```
Layer 1: Signal Model     → luck_score, verdict, tier
           score_luck.py (hitters)
           score_pitcher_luck.py (pitchers v2.0 split architecture)

Layer 2: Projection Engine → proj_avg, proj_hr, proj_rbi, proj_era, etc.
           stat_projections.py
           generate_projections.py

Layer 3: Value Engine      → league1_value, rank
           score_value.py

Layer 4: Trade Analyzer    → trade verdict
           trade_analyzer.py
```

**LAYER 1 IS SACRED.** Never modify without explicit instruction + ablation test + invariant check + validate_formulas.py.

---

### HITTER SIGNAL STACK — 7 Layers (score_luck.py)

**Layer 1: Core xwOBA Gap**
xwOBA_gap = xwOBA - wOBA (Statcast contact quality vs actual results)
Positive gap = unlucky (contact quality exceeds results) → buy signal
Negative gap = lucky (results exceed contact quality) → sell signal
This is the single most predictive component. Everything else modifies it.

**Layer 2: Defensive Adjustment (OAA)**
Outfield Assist Above Average adjusts BABIP baseline
Better defenses artificially suppress BABIP → adjust expected BABIP upward
Typically ±0.008 on the expected BABIP baseline

**Layer 3: Contact Type (GB rate)**
Ground balls have a predictable BABIP regardless of defense
High GB rate = lower BABIP expected → adjust baseline downward
Prevents penalizing extreme grounder hitters for "low BABIP"

**Layer 4: Plate Discipline (BB%/K%)**
BB rate > career → positive; K rate > career → negative (modest modifiers)
Primary use: flag extreme discipline changes for additive penalty logic

**Layer 5: Career BABIP Baseline**
476 hitters have individual career BABIP records (vs using league average ~.300)
Comparing player to their OWN history is more predictive than league average
If career BABIP is .245 and current is .240, that's fine — not bad luck
Age-adjusted BABIP decay applied on top:
- Age 32-34: career_BABIP × 0.97
- Age 35-36: career_BABIP × 0.94
- Age 37-38: career_BABIP × 0.91
- Age 39+:   career_BABIP × 0.88

**Layer 6: Park Factor Adjustment**
Park factors affect expected BABIP and HR/FB rate (not the luck score directly)
PARK_FACTORS dict in score_luck.py: 32 teams, relative to league average
Applied to babip_expected and hrfb_expected before luck_score computation
Park change detection: if team changed from prior_teams_2025, badge applied
43 players flagged with park change in 2026

**Layer 7: Seasonal Pattern + Platoon Adjustment**
- Platoon modifier (updated April 26):
  Compares CURRENT same-hand vs opposite-hand wOBA split gap to CAREER baseline gap
  from hitter_career_platoon.json (489 batters, built from 2022-2025 pitcher Statcast)
  gap_delta > +0.040 vs career → AMPLIFY ×1.05 (larger platoon split = more signal)
  gap_delta < -0.040 vs career → DAMPEN ×0.90 (narrower split = less predictable)
  Fallback: -0.019 mean when no career record
  PA minimum: 30 at-bats each hand to fire
  Result: 19 modifier changes vs old static approach

**Formula:**
```
raw_score = (xwOBA_gap × 0.40 + babip_luck × 0.35 + hrfb_luck × 0.15 + bb_k × 0.10)
luck_score = raw_score × platoon_modifier − _buy_penalty (if buy) or × sell_amplifier (if sell)
```

---

### VERSION D ADDITIVE MODIFIER ARCHITECTURE (adopted April 26, 2026)

All buy-side dampeners use FLAT ADDITIVE penalties, not multiplicative multipliers.
Penalties accumulate in `_buy_penalty` column. Combined cap: H_MAX_COMBINED_PEN=0.040.
Applied in one combined pass AFTER all flag detection blocks.

**Why additive beats multiplicative:**
Multiplicative ×0.95 cannot cross tier boundaries. If luck_score=0.050 (Slight Buy):
- ×0.95 → 0.0475 → still Slight Buy (tier boundary is 0.100, but gap to Neutral is only 0.050)
Wait — the gap between Slight Buy threshold (0.100) and Neutral (below 0.100) means:
- Score of 0.115: multiplicative ×0.95 → 0.109 → still Slight Buy
- Score of 0.115: additive -0.012 → 0.103 → still Slight Buy
- Score of 0.115: additive -0.020 → 0.095 → drops to Neutral ✅
The additive penalty CAN cross the 0.100 tier boundary; multiplicative often cannot.
42 verdict changes in 2022-2024 training confirmed real impact.

**Calibrated penalty constants (from sensitivity sweep on 2022-2024 training data):**
All constants in config.py — single source of truth.
```python
H_KP_K_PENALTY      = 0.010   # K-rate spike >3pp above career baseline
H_KP_PULL_PENALTY   = 0.008   # pull-rate drop >5pp below career baseline
H_HH_PENALTY        = 0.012   # hard-hit rate drop >3pp below career baseline
H_SPEED_PENALTY     = 0.010   # sprint speed cliff >0.3 ft/s YoY (from hitter_career_sprint.json)
H_CHASE_PENALTY     = 0.008   # chase rate rise >3pp above career (buy-side only)
H_MAX_COMBINED_PEN  = 0.040   # hard cap — no matter how many flags fire, max penalty = 0.040
```

**Age-weighted chase rate modifier (config.py):**
```python
H_CHASE_AGE_WEIGHT_U25   = 0.40  # age ≤25: chase penalty × 0.40 (development variance)
H_CHASE_AGE_WEIGHT_26_27 = 0.70  # age 26-27: chase penalty × 0.70 (still maturing)
# age 28+: full penalty
```
8 young buy players affected: Henderson, Merrill, Tovar, Soderstrom, Cam Smith, Jordan Beck, Jacob Wilson, Langford.
Current verdict impact: zero (no young buy near a tier boundary currently).
Note: thresholds are estimated priors — empirical calibration requires 2+ seasons of data (mid-2027).

---

### PITCHER SIGNAL STACK v2.0 — SPLIT ARCHITECTURE (score_pitcher_luck.py)

The key insight: buy signals and sell signals come from FUNDAMENTALLY DIFFERENT phenomena.
- Buy signal = ERA artificially high due to luck (BABIP, LOB)
- Sell signal = ERA artificially low due to luck (strand rates, HR/FB luck)
Using one model for both corrupted accuracy. Split architecture confirmed +5.5pp OOS.

**BUY SCORE (ERA-FIP dominant):**
```
raw_buy = (ERA - FIP) × 0.60 + (xwOBA_gap) × 0.25 + (BABIP vs career) × 0.15
```
- ERA-FIP gap is 99.3% of the buy score in practice (other components rarely change verdicts)
- xwOBA_gap inclusion confirmed as slight drag (+3.8pp OOS without it) but no clear replacement
- Classification from RAW score BEFORE confidence scaling

**SELL SCORE (8-component composite):**
1. BABIP allowed vs career baseline (weight ×5.0)
2. LOB% vs 72.4% baseline (weight ×-3.0)
3. ERA-FIP gap (weight ×0.15)
4. ERA-xERA gap (weight ×0.10)
5. HR/FB rate — non-linear, fires at >14%
6. Hard hit rate allowed vs career baseline (weight ×-1.5)
7. Barrel rate allowed vs career baseline (weight ×-1.5)
8. SwStr% vs 11% baseline (weight ×2.0)

**BUY QUALIFICATION GATES (ALL must pass for any buy signal):**
- FIP <= 4.50
- SwStr% >= 8%
- Career IP >= 100
- IP >= 20 (waived if raw_buy_score >= 1.50 — the "Boyle exception")
- ERA >= 3.50 (all buys — Neutral result expected when ERA already good)
- ERA >= 3.75 for Buy Low specifically (raised April 25 from 3.50, +7.3pp OOS)
- ERA >= 4.00 for Slight Buy only
- |FIP - xERA| <= 1.50 OR xERA <= 4.50
- FIP >= 1.50 if IP < 20

**ERA >= 4.00 for Slight Buy logic:** The buy signal requires ERA to be elevated vs FIP. A pitcher with ERA 1.96 and FIP 1.41 (like Schlittler) doesn't need a buy — his ERA is already excellent. The gate ensures we're identifying pitchers who are genuinely unlucky, not just pitchers who happen to have ERA > FIP by a small margin when overall ERA is still great.

**CSW (Called Strikes + Whiffs) buy-low-only modifier:**
- csw_gap > +0.025 → buy score ×1.10 (CSW above career = better stuff than ERA shows)
- csw_gap < -0.025 → buy score ×0.90 (CSW below career = ERA may be deserved)
- Applied to Buy Low signals only

**Pitch Mix Phase 2 (6-flag system — wired April 25):**
Bearish flags (each ×0.90 on buy score): abandonment, velo_drop, rv_degrade
Bullish flags: effectiveness, velo_gain (×1.10 buy); rv_improve (×1.05)
Architecture finding: verdict-neutral across Versions E/F/G/H (all 94.0%/87.0% OOS)
Reason: 10% multipliers insufficient to cross tier boundaries (~0.085 unit gap between tiers)
Three stacked bearish flags = ×0.729 total — still rarely crosses a boundary
Status: INFORMATIONAL layer only; wired but verdict-neutral
Coverage: 234 pitchers in 2026 production run

**Age tier logic:**
- Age 35+ + luck <= -0.20 → "Sell and Move On"
- Age 35+ + luck <= -0.12 → "Sell High on Perception"
- Age 35+ + mild signal → keep tier + "Age 35+ monitor"

---

### WORRY INDEX / GET HYPED INDEX (display only — no model weight)
Implemented in score_luck.py. Columns: worry_flag, breakout_flag, worry_label in luck_scores.csv.
Thresholds: WORRY_LUCK_BAND=0.085, WORRY_WOBA_GAP=0.040
These are estimated priors — validate after 50+ resolved flags (mid-2027 earliest).

**Core concept:** Flags where MODEL SILENCE is itself the signal.
When a player is posting results far above/below their established xwOBA baseline AND no luck signal fires, it means we CANNOT attribute the gap to luck. The model silence says: this performance difference looks real, not correctable.
- Buy/Sell signals say: "Luck will correct, results will converge to contact quality"
- Worry/Get Hyped says: "Contact quality AND results are both moving the same direction — no correction coming"

**WORRY flag — ALL conditions must be true:**
- fp_rank < 50 (high-expectation player market still trusts)
- wOBA running 40+ points BELOW 3-year xwOBA baseline
- No positive luck signal: luck_score > -0.085 (i.e., no sell signal already firing — if a sell IS firing, redundant)
- Minimum 75 PA
- Display label: "Struggle may be real — not luck driven"
- Article framing: "Don't buy the dip yet — the model says it's not luck"

**GET HYPED flag — ALL conditions must be true:**
- fp_rank > 100 (undervalued/unrecognized player)
- wOBA running 40+ points ABOVE 3-year xwOBA baseline
- No sell signal: luck_score < 0.085 (i.e., no buy signal already firing)
- Minimum 75 PA
- Display label: "Breakout may be real — not luck driven"
- Article framing: "He's MASHING and it appears completely real"

**ACTIVE WORRY FLAGS (May 1, 2026 — from current luck_scores.csv):**
- **Rafael Devers SF:** wOBA .243, xwOBA .269, 3yr xwOBA .371 (gap = −128 pts), luck=-0.002 (Neutral), fp_rank=16, 116 PA. K rate 31.9%, HH rate 43.1% (−10.6pp below career). CRITICAL: his xwOBA (.269) is also depressed — not just results. Real struggle. Devers traded to SF (was BOS) — park change adds uncertainty. "Don't buy Devers on name alone."
- **Shohei Ohtani LAD (NEW — not in prior articles):** wOBA .390, xwOBA .415, 3yr xwOBA .433 (gap = −43 pts), luck=-0.002 (Neutral), fp_rank=2, 134 PA. HH rate 50.0% (still elite). This is a SUBTLE worry — his xwOBA at .415 is still excellent, just below his transcendent .433 career baseline. Not a crisis, but worth monitoring. Do NOT publish as a major concern (he's .390 wOBA — still top-5 player).
- **Willy Adames SF:** wOBA .273, xwOBA .293, 3yr xwOBA .334 (gap = −61 pts), luck=-0.021 (Neutral), fp_rank=25, 116 PA. Adames also traded to SF (was MIL). Park change relevant.

**ACTIVE GET HYPED FLAGS (May 1, 2026):**
- 0 active — no breakout flags firing

**James Wood WSH (does NOT qualify for Get Hyped):**
- Wood has no active BUY signal (luck_score = -0.026, Neutral)
- wOBA .424, xwOBA .479 — BOTH excellent
- But wOBA .424 - 3yr xwOBA: Wood has no 3yr baseline (rookie) — cannot compute
- His performance looks real: barrel 29.9% vs career 14.4%, HH 65.7%, BABIP BELOW expected
- Baseball Savant confirmed swing angle change (validated by HonorableJudgeIto on Reddit)
- He's CBS #3 overall (137.0 FPTS YTD)
- Framing: "Wood is MASHING and it looks completely real" — say it, just not via the Get Hyped flag mechanism

---

### LAUNCH ANGLE YoY DELTA (display only — no model weight)
Built by build_hitter_launch_angle.py → data/hitter_launch_angle.json (454 records)
Added to luck_scores.csv: current_la_avg, career_la_avg, la_delta, la_trending_up, la_trending_down, la_display
Thresholds: la_trending_up if delta > +3.0°, la_trending_down if delta < -3.0°
Coverage: 148 of 423 hitters have full delta (35%); 454 records total

**Most extreme down (May 1, 2026 data):**
- Matt Chapman SF: -17.2° (career 21.0° → current 3.7°) — Sell High, strongest sell confirmation
- Gleyber Torres DET: -13.4° (career 17.2° → current 3.8°) — Slight Buy (tension: signal says buy but LA collapsing)
- Max Muncy LAD: -9.2° (career 21.5° → current 12.3°) — Slight Sell
- José Altuve HOU: -8.7° (career 15.7° → current 7.0°) — Neutral

**Most extreme up (May 1, 2026 data):**
- Jacob Young WSH: +16.3° (career -4.7° → current 11.6°) — Neutral (most dramatic rise)
- Giancarlo Stanton NYY: +12.8° (career 9.3° → current 22.1°) — Sell High (tension: rising LA but sell signal)
- Ronald Acuña ATL: +10.6° (career 5.8° → current 16.4°) — Buy Low (double buy signal — unlucky AND improving approach)
- Ke'Bryan Hayes CIN: +10.4° (career 8.2° → current 18.6°) — Buy Low
- Elly De La Cruz CIN: +10.7° (career 5.5° → current 16.1°) — Neutral

**Key tension case for articles:**
- Gleyber Torres DET: Slight Buy signal (+0.146) BUT LA delta -13.4°. The signal says buy (low BABIP, contact quality good), but the launch angle decline is a real concern. Worth mentioning: "signal says buy but swing change warrants monitoring."

---

### LINEUP CONTEXT MODULE (stat_projections.py + lineup_context.py)
Built April 27. Adjusts R and RBI projections based on batting slot + surrounding lineup quality.

**Data sources:**
- data/hitter_batting_slot_2026.json: 452 batters, modal batting slot + n_games
- data/team_lineup_context_2026.json: 30 teams + _league_avg, OBP/SLG/PA per batting slot
- League average: OBP=0.3242, SLG=0.3942

**Formula:**
- R multiplier: based on OBP of slots batting AHEAD of the player
- RBI multiplier: based on OBP/SLG of slots batting AHEAD + player's own slot
- R_SENSITIVITY = 0.8, RBI_SENSITIVITY = 1.2 (validated against 2025 actuals, n=141)
- Sell High RBI cap: min(rbi_mult, 1.05) — sell signal shouldn't get full RBI boost
- Hard caps: MULT_MIN=0.80, MULT_MAX=1.20

**Key results:**
- Kyle Tucker LAD: RBI_mult=1.20 (batting in loaded lineup)
- Austin Riley ATL: RBI_mult=1.20
- Ke'Bryan Hayes CIN: RBI_mult=0.80 (moved to CIN — weak lineup)
- Luis Robert NYM: RBI_mult=0.80
- Francisco Álvarez NYM: RBI_mult=0.80

---

### PLAYING TIME MODULE (stat_projections.py — added April 30, 2026)

**Hitter PA blend formula:**
```python
_blend_pa(mlbam_id, games_rem, pa_so_far, games_played):
  steamer_ros = steamer_pa_full × (games_rem / 162)
  pace_ros = (pa_so_far / games_played) × games_rem × 0.90  # 10% regression
  # Weighting by games played trust tiers:
  if games_played < 20:  w_s=0.70, w_p=0.30
  elif games_played < 50: w_s=0.60, w_p=0.40
  else: w_s=0.40, w_p=0.60
  # IL status penalty (ESPN returns ACTIVE for all — infrastructure ready):
  DAY_TO_DAY: -5 games  |  INJURY_RESERVE: -12 games
```
Coverage: 417/423 hitters (98.6%); unmatched = rookies/NPB players

**Pitcher IP blend formula:**
```python
_blend_ip(mlbam_id, games_rem, current_ip, current_gs, current_games):
  if steamer_gs >= 10:  # Starting pitcher (Steamer classification)
    sp: 0.55 × steamer_ros + 0.45 × pace_ros
  elif current_gs >= 5 and current_ip >= 20 and current_ip/current_gs >= 4.0:
    # SP role override: Steamer thought RP but demonstrably starting in 2026
    # Flipped weights (Steamer forecast meaningless for this pitcher)
    blended = 0.45 × steamer_ros + 0.55 × pace_ros, capped at 110 IP
  else:  # Reliever
    rp: 0.80 × steamer_ros + 0.20 × pace_ros
    cap: 70 IP max
  if current_ip < 15 or current_games == 0:
    fallback to 100% steamer_ros
```
Coverage: 396/402 pitchers (98.5%)
Note: project_pitcher_counting() also applies 110 IP cap for role_overridden=True in its fallback branch (catches pitchers absent from Steamer CSV entirely, e.g. Chase Burns).

**Key PA/IP changes after playing time module:**
- Ohtani: +102 PA (Steamer full commitment)
- Kurtz: +101 PA (Steamer projects full load)
- Grisham: 498 PA → 327 PA (platoon player correctly reduced)
- Webb: +61 IP (elite SP gets full workload credit)
- Gilbert: +59 IP
- Top IP losers: bench arms with <10 IP correctly dropping to minimal projections

---

### PARK FACTOR ADJUSTMENT (stat_projections.py — added May 1, 2026)

**Location:** Parallel PARK_FACTORS_PROJ dict in stat_projections.py
Why NOT imported from score_luck.py: would create circular import (score_luck.py imports stat functions; stat_projections.py importing from score_luck.py → circular). Pragmatic solution: parallel dict with sync comment.

**Amplifiers (different from raw park factor):**
```python
HR_AMPLIFIER = 1.5   # HR most park-sensitive (launch angle physics)
AVG_AMPLIFIER = 0.5  # AVG least sensitive (defense partially neutralizes park)
R_RBI_AMPLIFIER = 0.7  # R/RBI moderately sensitive
THRESHOLD = 0.02     # Only apply if |pf_delta| >= 0.02 (trivial moves ignored)
```

**Why different amplifiers:** HR flies over the fence — park dimensions matter maximally. AVG is partly governed by defense, infield dimensions, and foul territory that partially offset park effect. R/RBI are downstream of everything else.

**Key moves (45/46 flagged park-change hitters adjusted):**
- COL arrivals (e.g., Pete Alonso BAL→COL): +HR projection
- SF departures (e.g., Logan Webb stays SF but Devers SF move): SF is pitcher's park, -HR
- pf_adj_applied flag: True/False column in projections_2026.csv

37/37 PASS, all invariants PASS after implementation.

---

### CBS RANK INTEGRATION (fetch_cbs_rank.py — added May 1, 2026)

**What it is:** CBS Sports publishes YTD FPTS rankings for all rostered players. These are INDEPENDENT of our model — CBS uses their own formula, their own data, their own audience. The rank reflects real CBS league performance, not our projections.

**Why independence matters:** If we computed CBS rank from our own projected stats (which include Buy Low ×1.08 HR multiplier), the comparison would be circular. The scraped rank means something precisely because it was NOT computed by us.

**Coverage:**
- 545 players saved to data/cbs_rank_2026.csv (367 hitters + 178 pitchers)
- Hitter match rate: 330/423 (78%) — high coverage
- Pitcher match rate: 170/402 (42%) — lower because CBS only publishes top-100 per position (9 positions = max 178 after dedup)
- CBS scrapes 9 position pages: C, 1B, 2B, SS, 3B, OF, U (util), SP, RP

**Alias mapping (fetch_cbs_rank.py):**
```python
_CBS_ALIASES = {
    "cameron schlittler": "cam schlittler",  # CBS uses Cameron, pipeline uses Cam
}
```
Applied via _norm_cbs() function. Schlittler was CBS #3 pitcher with null match — now fixed.

**Key CBS rank divergences (ESPN rank vs CBS rank):**
(Positive divergence = ESPN ranks player HIGHER than CBS → ESPN overvaluation)
- Juan Soto: ESPN #7 / CBS #186 → gap = -179 (CBS sees reality; ESPN prices name)
- Mookie Betts: ESPN #43 / CBS #268 → gap = -225 (injury impact not in ESPN rank)
- Ketel Marte: ESPN #17 / CBS #114 → gap = -97 (Worry Index patient confirmed)
- Rafael Devers: ESPN #134 / CBS #238 → gap = -104 (market catching up to struggles)
- Cal Raleigh: ESPN #14 / CBS #86 → gap = -72 (Buy Low with CBS confirmation)
- Manny Machado: ESPN #25 / CBS #83 → gap = -58 (Buy Low with CBS confirmation)
- Francisco Lindor: ESPN #30 / CBS #171 → gap = -141 (Slight Buy despite CBS low rank)

**ESPN rank = reputation rank. CBS rank = production rank.**
When these diverge significantly AND a luck signal fires, that's the content story:
- Signal tells you WHY the player is mispriced (luck vs. skill)
- CBS/ESPN gap tells you WHERE the mispricing lives (which market is wrong)
- Together: "ESPN is still pricing Soto on his name; CBS shows the reality; our model confirms no lucky bounce is coming"

---

### FINANCIAL MOTIVATION COHORT FRAMEWORK (display only — score_luck.py)
contract_cohort column in luck_scores.csv. Built around financial SECURITY GAP (not binary CY yes/no).

**Five cohorts (priority order):**
1. **Generational Payday (cohort 1):** Age 25-31, underpaid vs market, ≤2yr to FA. Max motivation — career-defining contract window. Example: Yordan ($19.2M AAV, 1yr) ✅
2. **Prove-It (cohort 2):** Any age, 1-2yr deal post-injury or down year. Rebuilding market value. Example: Manual override
3. **Already Secured (cohort 3):** AAV ≥ $20M AND years_remaining ≥ 3. Less motivated (financial security achieved). Examples: Ohtani, Judge, Trout, Harper, Seager, Lindor, Turner, Machado, Riley, Ramírez, Swanson, Bogaerts, Stanton, Olson, Nola, Yelich (17 players)
4. **Post-Prime (cohort 4):** Age 33+, any contract. Physical ceiling, not motivation issue.
5. **Mid-Contract (cohort 5):** Age 28-33, multi-year, not FA-bound. Neutral baseline.

**Note on Yordan:** AAV $19.2M = BELOW $20M threshold. Years remaining = 1 = BELOW 3yr threshold. Correctly Cohort 1 (not 3) despite being a superstar.

**Preliminary backtest (April 29, 2026):**
- Source: MLB_Contracts_3.xlsx (1,000 rows, 609 players, Spotrac export)
- Match rate: 112/211 (53%) — unmatched = pre-arb/arb (no Spotrac FA entry)
- Cohort 3 shows 96.4% overall accuracy (n=28) — promising but n<10 per signal tier
- ALL n<10 per cohort/signal combination → no publishable conclusions
- Requires 50+ players per cohort before validation

**Bug fixed April 27:** _assign_cohort() was called before df["age"] was set → all players returned "unknown". Fixed by moving apply() after df["age"] = ... line. Confirmed by distribution check (no longer all "unknown").

---

## SECTION 6: CURRENT SIGNALS (May 1, 2026 — from live luck_scores.csv)

Signal counts: **61 Buy Low | 17 Slight Buy | 278 Neutral | 30 Slight Sell | 37 Sell High**
Total: 423 hitters

### HITTER BUY LOW (top 30 by luck score)

| Name | Team | Luck | wOBA | xwOBA | Gap | BABIP | PA | CBS# | Own% |
|------|------|------|------|-------|-----|-------|-----|------|------|
| Trent Grisham | NYY | +0.565 | .279 | .389 | +.110 | .138 | 109 | 115 | 14% |
| José Ramírez | CLE | +0.520 | .345 | .420 | +.075 | .211 | 133 | 15 | 99.8% |
| Alec Bohm | PHI | +0.503 | .222 | .270 | +.048 | .183 | 110 | 237 | 17% |
| Ke'Bryan Hayes | CIN | +0.430 | .214 | .317 | +.103 | .145 | 80 | 285 | 0.5% |
| Vinnie Pasquantino | KC | +0.401 | .290 | .311 | +.021 | .177 | 123 | 144 | 67% |
| Corey Seager | TEX | +0.367 | .306 | .361 | +.055 | .214 | 126 | 68 | 91% |
| Jake Cronenworth | SD | +0.366 | .253 | .321 | +.068 | .188 | 101 | 234 | 5% |
| J.P. Crawford | SEA | +0.357 | .320 | .400 | +.080 | .226 | 101 | — | 5.6% |
| Jarren Duran | BOS | +0.355 | .213 | .269 | +.056 | .209 | 103 | 176 | 81% |
| Evan Carter | TEX | +0.348 | .301 | .354 | +.053 | .233 | 108 | 152 | 5% |
| Marcell Ozuna | PIT | +0.347 | .231 | .300 | +.069 | .215 | 103 | — | 6% |
| Kyle Karros | COL | +0.344 | .278 | .344 | +.066 | .246 | 108 | 191 | 0.3% |
| Dillon Dingler | DET | +0.306 | .354 | .447 | +.093 | .246 | 99 | 89 | 43% |
| Kyle Schwarber | PHI | +0.303 | .361 | .413 | +.052 | .204 | 126 | 16 | 99.5% |
| Chase Delauter | CLE | +0.292 | .338 | .379 | +.041 | .244 | 111 | 61 | 70% |
| TJ Friedl | CIN | +0.291 | .251 | .246 | −.005 | .250 | 114 | 182 | 14% |
| Michael Busch | CHC | +0.287 | .260 | .293 | +.033 | .215 | 127 | 167 | 42% |
| Manny Machado | SD | +0.286 | .328 | .355 | +.027 | .239 | 114 | 83 | 99% |
| Jackson Merrill | SD | +0.278 | .281 | .321 | +.040 | .250 | 124 | 87 | 92% |
| Austin Riley | ATL | +0.277 | .281 | .306 | +.025 | .238 | 131 | 113 | 87% |
| Austin Wells | NYY | +0.276 | .293 | .366 | +.073 | .180 | 83 | 231 | 10% |
| Ezequiel Tovar | COL | +0.272 | .242 | .281 | +.039 | .273 | 119 | 221 | 6% |
| Caleb Durbin | BOS | +0.269 | .253 | .281 | +.028 | .203 | 107 | 170 | 32% |
| Bryson Stott | PHI | +0.260 | .233 | .300 | +.067 | .246 | 82 | 236 | 37% |
| TJ Rumfield | COL | +0.259 | .345 | .348 | +.003 | .292 | 123 | 98 | 10% |
| Ronald Acuña | ATL | +0.259 | .332 | .387 | +.055 | .299 | 140 | — | 99.8% |
| Sal Stewart | CIN | +0.257 | .410 | .437 | +.027 | .263 | 126 | 4 | 93% |
| Gunnar Henderson | BAL | +0.255 | .347 | .388 | +.041 | .239 | 132 | 27 | 99% |
| Iván Herrera | STL | +0.249 | .387 | .419 | +.032 | .286 | 133 | 29 | 29% |
| Aaron Judge | NYY | +0.239 | .450 | .496 | +.046 | .262 | 130 | 8 | 99.9% |

**Notable: Yordan Álvarez (luck +0.213, wOBA .501, xwOBA .581, gap +.080, CBS #1)** — Buy Low on the best hitter in baseball. BABIP .322 (below his .340+ career norm), xwOBA .581 is extraordinary. Signal is normalizing (was +0.288 Week 1, +0.213 now) but still valid.

**Notable hidden gems (own<35%, strong stats):**
- TJ Rumfield COL: 10% owned, Buy Low, wOBA .345
- Iván Herrera STL: 29% owned, Buy Low, wOBA .387, xwOBA .419
- Jonathan Aranda TB: 27% owned, Buy Low, wOBA .331, xwOBA .370
- Xander Bogaerts SD: 31% owned, Buy Low, wOBA .363, xwOBA .371

---

### HITTER SLIGHT BUY (17 players)

| Name | Team | Luck | wOBA | xwOBA | Gap | PA | CBS# | Notes |
|------|------|------|------|-------|-----|-----|------|-------|
| Lawrence Butler | ATH | +0.148 | .271 | .329 | +.058 | 100 | 193 | LA delta −7.6° (tension) |
| Gleyber Torres | DET | +0.146 | .332 | .363 | +.031 | 127 | 81 | LA delta −13.4° (major tension) |
| Luis Robert | NYM | +0.146 | .299 | .329 | +.030 | 93 | 192 | Borderline gap gate |
| Luisangel Acuña | CWS | +0.139 | .208 | .279 | +.071 | 78 | 249 | Young, development noise |
| Bo Naylor | CLE | +0.129 | .179 | .293 | +.114 | 68 | 319 | Low PA, catcher |
| Junior Caminero | TB | +0.127 | .338 | .371 | +.033 | 125 | 49 | 99.7% owned — hold signal |
| Roman Anthony | BOS | +0.127 | .277 | .329 | +.052 | 110 | 196 | 85% owned |
| Logan O'Hoppe | LAA | +0.124 | .268 | .298 | +.030 | 89 | 240 | Borderline gap |
| Bo Bichette | NYM | +0.115 | .281 | .348 | +.067 | 127 | 134 | Was Worry flag — now SB |
| Francisco Lindor | NYM | +0.107 | .304 | .336 | +.032 | 100 | 171 | ESPN#30/CBS#171 gap |
| Will Smith | LAD | +0.117 | .311 | .349 | +.038 | 95 | 160 | Injury risk |
| Wenceel Pérez | DET | +0.105 | .205 | .353 | +.148 | 49 | — | Tiny sample, extreme gap |

**Key tension case:** Gleyber Torres Slight Buy (+0.146) with LA delta −13.4° is the clearest model tension in the current dataset. The signal says contact quality is above results. The launch angle data says his swing has fundamentally changed. Worth explicit flagging in articles.

---

### HITTER SELL HIGH (37 players, top by magnitude)

| Name | Team | Luck | wOBA | xwOBA | Gap | BABIP | PA | CBS# | Own% |
|------|------|------|------|-------|-----|-------|-----|------|------|
| Matt Chapman | SF | −0.519 | .339 | .295 | −.044 | .362 | 118 | 116 | 75% |
| Daniel Schneemann | CLE | −0.473 | .405 | .394 | −.011 | .426 | 85 | 125 | 11% |
| Garrett Mitchell | MIL | −0.370 | .346 | .345 | −.001 | .432 | 90 | 107 | 7% |
| Ildemaro Vargas | AZ | −0.362 | .470 | .454 | −.016 | .377 | 91 | 38 | 64% |
| Otto Lopez | MIA | −0.314 | .405 | .365 | −.040 | .389 | 127 | 44 | 72% |
| Randy Arozarena | SEA | −0.301 | .362 | .348 | −.014 | .366 | 130 | 32 | 91% |
| Corbin Carroll | AZ | −0.300 | .409 | .386 | −.023 | .393 | 109 | 28 | 99.7% |
| Nick Gonzales | PIT | −0.299 | .331 | .326 | −.005 | .397 | 104 | 131 | 3% |
| José Fernandez | AZ | −0.282 | .378 | .325 | −.053 | .393 | 86 | 143 | 7% |
| Max Muncy | ATH | −0.276 | .318 | .315 | −.003 | .364 | 104 | 183 | 8% |
| Ben Rice | NYY | −0.273 | .492 | .502 | +.010 | .368 | 117 | 6 | 99% |
| Jordan Walker | STL | −0.259 | .395 | .387 | −.008 | .367 | 121 | 17 | 83% |
| José Caballero | NYY | −0.260 | .334 | .274 | −.060 | .329 | 108 | 77 | 38% |
| Taylor Ward | BAL | −0.221 | .410 | .389 | −.021 | .386 | 132 | 37 | 86% |
| Paul Skenes | PIT | −0.151 | — | — | — | — | — | 17p | 100% |

**Ben Rice (CBS #6, Sell High signal):** This is the canonical trade tool tension case. Rice has wOBA .492/xwOBA .502 (elite), CBS #6 overall — but Sell High signal fires because BABIP .368 is well above expected. Signal says: results will regress toward contact quality. But contact quality is still excellent, so "Sell High" means sell at peak value, not that he'll collapse. Surplus value vs replacement C = +44 FPTS.

**Matt Chapman SF (strongest sell):** LA delta −17.2° (career 21.0° → current 3.7°). His launch angle collapse is the most extreme in the dataset. Confirmed sell signal with physical change as mechanism. Article lead for Week 3.

---

### HITTER SLIGHT SELL (30 players, select notable)

| Name | Team | Luck | wOBA | xwOBA | PA | CBS# | Notes |
|------|------|------|------|-------|-----|------|-------|
| Matt Olson | ATL | −0.138 | .422 | .422 | 139 | 5 | CBS #5, results matching expected — sell at peak |
| Drake Baldwin | ATL | −0.137 | .392 | .414 | 142 | 9 | CBS #9 catcher — slight sell |
| Max Muncy | LAD | −0.137 | .402 | .453 | 111 | 183 | xwOBA good, BABIP luck |
| Christian Yelich | MIL | −0.086 | .353 | .280 | 51 | 208 | Tiny sample — borderline |
| Pete Crow-Armstrong | CHC | −0.086 | .293 | .298 | 123 | 97 | Borderline — 92% owned |

---

### PITCHER BUY LOW (8 pitchers)

| Name | Team | ERA | FIP | xERA | IP | Luck | CBS# | Own% | Key Signal |
|------|------|-----|-----|------|----|------|------|------|-----------|
| Jesús Luzardo | PHI | 5.08 | 2.64 | 2.927 | 33.7 | +0.532 | 92 | 88% | BABIP .352, LOB 60.8%, SwStr 15.1% |
| Joe Ryan | MIN | 4.78 | 2.87 | 2.713 | 37.7 | +0.422 | 47 | 97% | BABIP .275, LOB 54.6% |
| Yusei Kikuchi | LAA | 5.87 | 3.62 | 4.694 | 30.7 | +0.293 | — | 14% | ERA-FIP gap 2.25 |
| Cristopher Sánchez | PHI | 3.82 | 2.51 | 3.023 | 33.0 | +0.270 | 39 | 99% | ERA-FIP gap 1.31, BABIP .423 |
| Carmen Mlodzinski | PIT | 4.13 | 2.18 | 4.064 | 28.3 | +0.186 | 148 | 5% | ERA-FIP gap 1.95, borderline xERA |
| Kyle Bradish | BAL | 5.59 | 4.00 | 4.305 | 29.0 | +0.173 | — | 68% | ERA-FIP gap 1.59, BABIP .376 |
| Chris Paddack | MIA | 6.43 | 4.35 | 3.578 | 28.0 | +0.170 | — | 0.4% | xERA 3.578 vs ERA 6.43 |
| Shane Baz | BAL | 4.59 | 3.63 | 4.010 | 33.3 | +0.162 | — | 26% | Borderline signal |

**Luzardo detail:** BABIP .352 (career ~.290), LOB% 60.8% (normal ~72.4%), SwStr 15.1% (elite — 96th percentile). The underlying stuff is elite; the results are a BABIP/strand rate disaster. Most likely to see dramatic ERA improvement.

**Ryan detail:** BABIP .275 (actually below career) but LOB% only 54.6% (extreme bad luck stranding runners). With normal strand rates, ERA would be ~3.30 based on FIP/xERA.

**Note on Cam Schlittler (NYY, CBS #3 pitcher, Neutral verdict):** ERA 1.96, FIP 1.41, xERA 1.57, 41.3 IP. Schlittler does NOT qualify for a buy signal because ERA 1.96 < 4.00 gate. His ERA is ALREADY excellent — no luck adjustment warranted. He's outperforming expectations legitimately. The CBS #3 rank is fully deserved.

---

### PITCHER SLIGHT BUY (7 pitchers)

| Name | Team | ERA | FIP | xERA | IP | Luck | CBS# | Notes |
|------|------|-----|-----|------|----|------|------|-------|
| Ben Brown | CHC | 4.35 | 2.64 | 2.236 | 22.3 | +0.132 | 113 | Strong underlying stuff |
| Bryan Woo | SEA | 4.41 | 3.66 | 3.471 | 34.7 | +0.124 | 67 | 97.8% owned |
| Trevor Rogers | BAL | 4.45 | 3.59 | 3.095 | 30.0 | +0.116 | 114 | 52.8% owned |
| Reid Detmers | LAA | 3.51 | 3.12 | 2.411 | 33.3 | +0.102 | 82 | ERA near gate threshold |
| Bailey Ober | MIN | 4.26 | 3.79 | 3.771 | 31.7 | +0.078 | 30 | 27.5% owned |
| Logan Webb | SF | 4.22 | 3.50 | 4.178 | 32.0 | +0.074 | 49 | 96.5% owned |
| Jake Irvin | WSH | 4.55 | 4.01 | 4.562 | 29.7 | +0.033 | — | Borderline |

---

### PITCHER SELL HIGH (25 pitchers, most notable)

| Name | Team | ERA | FIP | xERA | IP | Luck | CBS# | Why selling |
|------|------|-----|-----|------|----|------|------|-------------|
| José Soriano | LAA | 0.86 | 2.70 | 2.668 | 42.0 | −0.587 | 2 | ERA way below FIP, strand luck |
| Nick Martínez | SD | 1.47 | 3.52 | 3.676 | 36.7 | −0.469 | 20 | ERA will regress to ~3.5 |
| Michael McGreevy | STL | 2.78 | 4.21 | 5.949 | 32.3 | −0.402 | 56 | xERA 5.95 — run prevention luck |
| Tomoyuki Sugano | SD | 2.87 | 4.63 | 5.483 | 31.3 | −0.396 | 52 | LOB luck + soft contact luck |
| Clay Holmes | NYM | 1.75 | 3.72 | 3.848 | 36.0 | −0.382 | 23 | Reliever, massive strand luck |
| Eduardo Rodríguez | AZ | 3.03 | 4.74 | 5.014 | 32.7 | −0.345 | 73 | xERA 5.01 extreme |
| Parker Messick | TBD | 1.29 | 2.17 | 2.085 | 35.0 | −0.200 | 11 | ERA low, xERA confirms luck-driven |
| Paul Skenes | PIT | 0.95 | 2.54 | 0.488 | 29.0 | −0.151 | 17 | Complex — xERA 0.488 extreme |
| Randy Vásquez | NYY | 3.03 | 3.34 | 5.042 | 32.7 | −0.171 | 25 | xERA 5.042 — sell at peak |
| Chris Sale | ATL | 2.31 | 3.83 | 2.574 | 35.0 | −0.178 | 7 | CBS #7, ERA below FIP |

**Paul Skenes note:** ERA 0.95, FIP 2.54, xERA 0.488 — the sell signal fires because ERA > FIP is the buy direction. Actually ERA 0.95 < FIP 2.54 → ERA is BELOW FIP → this is a "lucky" pitcher (results better than underlying metrics). Sell High means: consider trading him while he's at peak perceived value. The xERA 0.488 suggests his stuff is even better than FIP shows — complex case. ERA simulation analysis (April 29) found the sell signal is BABIP/LOB-dominant, not ERA-driven. Confirmed keep filtered ERA methodology.

---

### PITCHER SLIGHT SELL (8 pitchers)

| Name | Team | ERA | FIP | xERA | IP | Luck | CBS# |
|------|------|-----|-----|------|----|------|------|
| Freddy Peralta | MIL | 2.23 | 3.80 | 3.359 | 32.3 | −0.105 | 74 |
| Kai-wei Teng | SF | 1.93 | 1.96 | 4.243 | 19.3 | −0.100 | 158 |
| Chase Burns | CIN | 2.67 | 3.71 | 2.729 | 33.7 | −0.098 | 22 |
| Gavin Williams | CLE | 2.98 | 3.79 | 3.629 | 42.3 | −0.096 | 4 |
| Ranger Suárez | PHI | 2.91 | 3.27 | 3.326 | 34.0 | −0.083 | 40 |
| Kris Bubic | KC | 3.58 | 3.73 | 4.300 | 32.7 | −0.070 | 50 |

---

### NOTABLE RELIEVERS — DORMANT (below 15 IP confidence threshold)
- **Adrián Morejón SD:** ERA 6.89, FIP 2.59, xERA 2.96, 15.7 IP — JUST crossed 15 IP threshold. Gap is massive. Verify xERA before calling buy — borderline for first article mention.
- **Camilo Doval NYY:** ERA 7.71, FIP 5.44, xERA 3.36, 9.3 IP — only 9 IP, too early
- **Taylor Rogers MIN:** ERA 6.52, FIP 3.39, 9.7 IP — only 9.7 IP

---

## SECTION 7: ARTICLE CALL TRACKER (complete state as of May 1, 2026)

### Tracker Infrastructure
- File: data/calls_tracker.csv (169 players: 127H + 42P)
- Columns include: week1-7 luck/woba/xwoba, mechanism, prediction_correct, last_updated
- Duplicate week guard: won't increment week without new Statcast data
- Current data: Week 3 columns populated
- Mechanism values: confirmed | refuted | contact_improving | contact_deteriorating | results_improving | results_declining | genuine_decline | insufficient_movement

### Current Track Record (17/23 resolved = 73.9%)

**Accuracy note:** "Resolved" = confirmed OR refuted only. "Insufficient_movement" and other mechanisms excluded from denominator by design (matches backtest discipline).

---

### CONFIRMED CALLS (17)

| Name | Type | Call | Wk1 Luck | Wk3 Luck | Mechanism |
|------|------|------|----------|----------|-----------|
| Manny Machado | Hitter | Buy Low | +0.375 | +0.389 | confirmed |
| Aaron Judge | Hitter | Buy Low | +0.272 | +0.329 | confirmed |
| Mike Trout | Hitter | Buy Low | +0.222 | +0.292 | confirmed |
| Shohei Ohtani | Hitter | Buy Low | +0.198 | +0.079 | confirmed (weakening) |
| Samuel Basallo | Hitter | Slight Buy | +0.101 | +0.098 | confirmed |
| Owen Caissie | Hitter | Sell High | −0.209 | −0.162 | genuine_decline |
| Carson Kelly | Hitter | Sell High | −0.213 | −0.213 | genuine_decline |
| Max Muncy | Hitter | Sell High | −0.223 | −0.212 | genuine_decline |
| Luke Raley | Hitter | Sell High | −0.287 | −0.231 | genuine_decline |
| Jesús Luzardo | Pitcher | Buy Low | +0.369 | +0.370 | confirmed (signal strengthening) |
| Joe Ryan | Pitcher | Buy Low | +0.361 | +0.362 | confirmed |
| Janson Junk | Pitcher | Slight Buy | +0.074 | +0.074 | confirmed |
| Randy Vásquez | Pitcher | Sell High | −0.161 | −0.161 | genuine_decline |
| Connelly Early | Pitcher | Sell High | −0.182 | −0.311 | genuine_decline |
| Mike King | Pitcher | Sell High | −0.220 | −0.334 | genuine_decline |
| Seth Lugo | Pitcher | Sell High | −0.275 | +0.038 (normalized!) | genuine_decline (resolved correctly) |
| José Soriano | Pitcher | Sell High | −0.443 | −0.443 | genuine_decline |

---

### REFUTED CALLS (6)

| Name | Type | Call | Wk1 Luck | Wk3 Luck | Wk1 wOBA | Wk3 wOBA | Notes |
|------|------|------|----------|----------|----------|----------|-------|
| José Ramírez | Hitter | Buy Low | +0.508 | +0.505 | .363 | .354 | wOBA declining slightly despite strong signal |
| Corey Seager | Hitter | Buy Low | +0.322 | +0.401 | .332 | .318 | wOBA falling while signal strengthens — unlucky |
| Ezequiel Tovar | Hitter | Buy Low | +0.203 | +0.250 | .267 | .247 | wOBA declining |
| Kyle Bradish | Pitcher | Buy Low | +0.178 | +0.174 | ERA 5.55 | ERA 5.59 | Signal weakening slightly |
| Luis Castillo | Pitcher | Slight Buy | +0.129 | +0.129 | ERA 6.45 | ERA 6.45 | No movement |
| Aaron Nola | Pitcher | Slight Buy | +0.096 | +0.132 | ERA 5.13 | ERA 6.10 | ERA worsening |

**Nuance on "refuted" Ramírez and Seager:** Both have strengthening or stable luck scores (+0.505, +0.401). They are classified "refuted" because wOBA declined vs April baseline, but the underlying mechanism is still valid. Seager's signal is strengthening (+0.322 → +0.401) while his wOBA fell only modestly (.332 → .318). This is "too early to judge" territory — the mechanism is correct but insufficient time elapsed.

---

## SECTION 8: PROJECTION MODEL (full detail)

### CBS FPTS Regression (build_cbs_fpts.py — April 28-29)
Ridge regression (α=0.1) on 2024+2025 CBS actuals.

**Hitter coefficients (config.py CBS_H_COEF_*):**
- HR: primary HR driver
- R: runs contribution
- RBI: RBI contribution
- SB: speed premium
- AVG: batting average weight
- Train R²=0.985, OOS R²=0.983

**Pitcher coefficients (config.py CBS_P_COEF_*):**
- K: strikeout premium
- W: wins (overweighted by CBS)
- ERA: inverse ERA penalty
- WHIP: inverse WHIP penalty
- SV/H: saves + holds
- Train R²=0.927, OOS R²=0.909

**CRITICAL: Do NOT interpret individual CBS coefficients as "points per stat."** Due to multicollinearity (R/HR/RBI correlated; ERA/WHIP correlated), individual coefficients reflect marginal contribution given others. The combined model is accurate; individual coefs are not independently meaningful. Use full-vector prediction ONLY.

**Replacement level (replacement_level.py — April 29):**
12-team standard replacement levels (as of April 2026):
- C: 289.8 FPTS (William Contreras tier)
- 1B: 275.7 (Josh Bell tier)
- 2B: 277.7 (Marcus Semien tier)
- 3B: 267.0 (Ramón Urías tier)
- SS: 293.9 (Bo Bichette tier)
- OF: 296.3 (Jake Mangum tier)
- SP: 221.5 (Randy Vásquez tier)
- RP: 157.0 (Raisel Iglesias tier)

Surplus value = projected FPTS − replacement FPTS at player's position.
Ben Rice surplus vs C replacement: +44 FPTS
Paul Skenes surplus vs SP replacement: +33 FPTS
Note: Rice surplus > Skenes surplus in this model due to C scarcity. The tension in the Rice/Skenes comparison is intentional and informative — model shows Rice has more surplus value, but luck signal correctly shows Rice has more regression risk.

### Known Projection Weaknesses (with Backtest evidence)
- **AVG (MAE 0.022 vs RTM 0.020):** Loses to RTM. Career BA anchor (65% blend) is better than naive but still loses. AVG is fundamentally unpredictable from April data. Do not emphasize projection accuracy on AVG in articles.
- **WHIP (MAE 0.194 vs RTM 0.155):** Component H/9+BB/9 approach marginally worse than ERA-derived formula. RTM dominates WHIP. Structural problem.
- **K (MAE 39.4 vs Steamer 21.9):** is_sp tautology bug fixed (now uses Steamer GS >= 10 to classify SP). Remaining gap is from April-only IP data for starters — structural, not fixable without better IP projections.
- **R/RBI:** Lineup-dependent, partially addressed by lineup context module. Bias -9.65 RBI (known from Backtest A).
- **Playing time:** Steamer 2025 used for 2026 projections (best available — no 2026 Steamer yet)

### AVG Fix Details (April 30, stat_projections.py)
```python
CAREER_BA_WEIGHT = 0.65    # how much to trust career batting average
APRIL_AVG_WEIGHT = 0.35    # how much to trust current April data
MIN_CAREER_PA_BA = 200     # minimum career PA to use career anchor
```
When career_pa >= 200: true_avg = career_ba × 0.65 + formula_avg × 0.35
xwOBA-gap nudge: ±0.008 when |xwOBA - wOBA| > 0.030 (directional correction)
Result: MAE 0.0232 → 0.0216 (−7%), bias corrected from over-projection

### WHIP Fix Details (April 30, stat_projections.py)
```python
LG_H9  = 8.8   # league average hits per 9 IP (2022-2024 era priors)
LG_BB9 = 3.1   # league average walks per 9 IP
```
Component approach: proj_h9 = career_h9 × 0.60 + current_h9 × 0.40
true_whip = (proj_h9 + proj_bb9) / 9
Honest result: MAE marginally WORSE (0.1930 → 0.1944). RTM dominates WHIP; structural problem.

### xwOBA Career Regression (score_value.py — April 30)
```python
XWOBA_PA_STAB = 250  # PA needed for full trust in current xwOBA (raised from 200)
```
Blend: _wt = PA / (PA + 250); at 77 PA, _wt = 0.24 (76% weight to 3yr career baseline)
xwoba_3yr loaded from luck_scores.csv (95.7% coverage, 405/423 hitters matched)
Purpose: Sanchez's 77-PA xwOBA=0.433 (career .326) was inflating R/RBI projections
Result: Sanchez drops from catcher rank 20 → rank 21 ✅

### Barrel Rate Regression (score_value.py — April 25, updated April 30)
```python
LG_BARREL     = 0.066   # league average barrel rate (~6.6%)
BARREL_PA_STAB = 250    # raised from 200 (more statistically defensible)
```
At 95 PA: weight = 95/345 = 0.28 (72% toward league 6.6%)
At 250 PA: weight = 0.50 (equal blend)
Purpose: prevent small-sample barrel rate from dominating HR projections


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

**Session 16 additions to pitcher_luck_scores.csv output:**
- Alias columns: `player_name` (=name), `team` (=Team), `ip` (=IP) — enables downstream scripts to use consistent column names
- `player_type`: "SP" or "RP" from Steamer GS (GS>=10 → SP, else RP)
- `role_override`: True/False — 33 pitchers reclassified RP→SP via SP conversion gates:
  total_starts>=5 AND IP>=20 AND IP/total_starts>=4.0

**SP role override gate (applies to all three systems consistently):**
Same gate logic used in score_pitcher_luck.py (role_override column), _blend_ip() SP fallback, and project_pitcher_counting() cap.
33 pitchers reclassified as of May 1, 2026 run. Display-only; verdict logic not affected by role_override.

**stat_projections.py** — Layer 2 projections. Key constants: SWSTR_TO_K9=77.3 (line ~52), PARK_FACTORS_PROJ dict, CAREER_BA_WEIGHT=0.65, LG_H9=8.8, LG_BB9=3.1. Playing time: _blend_pa() for hitters (Steamer-weighted by games played tier), _blend_ip() for pitchers (55% Steamer SP, 80% Steamer RP, cap 70 IP). Known issue: G/GS null for all pitchers — OK, _blend_ip uses Steamer GS for SP/RP classification.

**Session 16: _blend_ip() SP fallback (role-override path):**
When Steamer classifies pitcher as RP (GS<10) BUT they are demonstrably starting in 2026 (current_gs>=5, current_ip>=20, ip/start>=4.0):
- is_starter overridden to True, _role_overridden=True
- Blend: 0.45 × steamer_ros + 0.55 × pace_ros (flipped from normal 0.55/0.45 — Steamer IP forecast is wrong for this pitcher)
- Cap: 110 IP ROS max (unproven SP converts)
- Example: Schlittler 7.5 IP → 74.8 IP after fix

**Session 16: project_pitcher_counting() 110 IP cap (second cap location):**
Chase Burns (MLBAM 695505) is absent from Steamer CSV entirely → _blend_ip() returns None → falls to fallback in project_pitcher_counting(). Added `role_overridden` parameter + `if role_overridden: projected_ip = min(projected_ip, 110.0)` to the `elif is_starter:` fallback branch.
Burns: 123.3 → 110.0 IP after fix.

**Call site (line ~1375): current_gs = total_starts (because FanGraphs GS always NaN)**
`current_gs_val = int(_safe_float(row.get("total_starts", row.get("GS", 0)), 0))`
`_role_overridden = bool(row.get("role_override", False))`

**generate_projections.py** — Layer 2 runner. Outputs: data/projections_2026.csv (794 players, 20 cols, pf_adj_applied flag).

**score_value.py** — Layer 3 value engine. Inputs: luck CSVs + projections + career_quality.json + player_positions.json. Outputs: data/player_values.json (825 players). Key: xwOBA career regression (XWOBA_PA_STAB=250), barrel regression (LG_BARREL=0.066, BARREL_PA_STAB=250), AVG penalty (proj_avg<0.220 load-bearing). Run: --write then --check-invariants.

**trade_analyzer.py** — Layer 4. CBS FPTS _compute_cbs_fpts() + replacement level surplus. Verdict thresholds: >=75% Strong, >=60% Favorable, >=40% Neutral, >=25% Unfavorable, <25% Avoid.

**run_pipeline.py** — Full runner. Encoding fix April 28: encoding="utf-8", errors="replace" in Popen (Windows CP1252 was crashing on tqdm progress bar output).

**fetch_ownership.py** — ESPN ownership → data/player_ownership_2026.csv (3,797 players). injury_status column all ACTIVE (ESPN endpoint limitation — infrastructure ready, real data when better endpoint found).

**fetch_fantasypros_ownership.py** — FP cross-platform ownership. 598 unique FP players, 69.7% match rate. Adds fp_ownership/fp_espn_own/fp_yahoo_own to player_ownership_2026.csv. --check flag for probe mode.

**fetch_cbs_rank.py** — CBS YTD FPTS scraper. 9 position pages (C/1B/2B/SS/3B/OF/U/SP/RP). Outputs: data/cbs_rank_2026.csv (545 players). _norm_cbs() applies alias after normalization. Pitcher match rate improved 171→176 (Session 16) after adding 5 aliases. 42% overall pitcher match rate: structural (CBS publishes top-100/position = max 178 pitchers vs our 402). --check flag.

```python
_CBS_ALIASES = {
    "cameron schlittler": "cam schlittler",  # CBS uses Cameron; pipeline uses Cam
    "michael king":       "mike king",        # Mike King (SD) was CBS#27 Sell High — was silently missing
    "louie varland":      "louis varland",
    "mike soroka":        "michael soroka",
    "jake junis":         "jakob junis",
    "jt ginn":            "j t ginn",         # "J.T." → "jt" but pipeline has "J. t." → "j t"
}
```

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

**Week 3 article (May 5-6 deadline):** Monday run → update → report. Lead: Matt Chapman LA delta -17.2°. Manual Get Hyped: Cam Schlittler (ERA 1.96/FIP 1.41/xERA 1.57/CBS #3 — three metrics agree). CBS divergences: Soto ESPN#7/CBS#186, Betts ESPN#43/CBS#268. Ohtani quiet worry flag. April Big Board: 17/23 = 73.9%. Release luck score spreadsheet (promised Article #2).

**Trade tool architecture fix — HIGHEST PRIORITY next session:** Current flow is broken: signal tier feeds verdict logic directly. Correct flow: signal feeds projected stats only → stats determine value → verdict = comparison. Fix in trade_analyzer.py. The Skenes/Rice problem (giving Skenes for Rice = "Favorable") exists because C positional scarcity overweights Rice surplus — the fix is proper architecture, not a threshold patch. See Section 11 Bug 3.

**Weekly tracker mechanism classifier:** Mechanism column exists (confirmed/refuted/contact_improving/etc.). Gap: article narrative framing per mechanism. Needed for Week 3+ articles to tell the story behind tracker movement.

**April Big Board:** Consolidated view of all April calls with current status. Player | call date | signal | current wOBA vs xwOBA | mechanism | resolved status. Track record proof-of-work document.

**White paper Section 10:** Live track record table — needs 2-3 more weeks data. Then publish to whitepapersonline.com.

**Mid-season signal architecture (full spec — build before May 15):**
Three time-period modes:

APRIL (prediction mode — current):
- Standard buy/sell signals; full 89.7% accuracy claim; 5-month correction window

MID-SEASON May 15 - July 31 (momentum vs merit):
- Buy/sell still valid but with urgency framing
- Urgency indicator: weeks remaining in season
- Rank trajectory layer: rising/falling vs signal
- "Don't chase" (rising rank + sell signal), "Buy the dip" (falling rank + buy signal)
- No standalone accuracy claim; runway indicator on every signal
- Article framing: separate labeled section "Mid-Season Signals" (NEVER mix with April accuracy)

LATE SEASON August+ (stretch run mode):
- Buy/sell for playoff implications only; short window explicitly stated
- "Act now or hold through season" binary framing
- Collection year for 2027 backtest

Components to build:
- signal_age column in calls_tracker.csv (weeks since call_date)
- runway_weeks computed from current date
- rank_trajectory (rising/falling/stable) from weekly delta
- urgency_flag: signal + runway < 8 weeks
- Framing templates by time period

Backtest: Do mid-May signals predict June-July regression? Same methodology as April backtest. Cannot publish accuracy until 2026 completes. 2025 collection year data available.

Key publishing rule: Never mix April accuracy (89.7%) with mid-season signals. Two separate labeled sections. Urgency as content hook: "Window closing on these calls."

### TIER 2 — This week

**Wire league_settings.py into trade_analyzer.py:** Replacement levels become league-aware. Rice/Skenes verdict should differ between CBS 13-team (C:2 → shallower C pool → higher replacement FPTS) and Fantrax 15-team (C:1 → deeper pool → lower replacement FPTS). Prerequisite: trade tool architecture fix (Tier 1) must land first so replacement levels flow correctly.

**Wire OBP vs AVG into hitter values (league-aware scoring):** League 2 (Fantrax) uses OBP — Seager, Judge, Schwarber worth more. AVG-only guys lose value. Requires stat_weights from league JSON to flow into score_value.py hitter ESV calculation. stat_weights in league JSON already present (AVG:0.0/OBP:1.0 for league_2). Implementation: load league settings in score_value.py, apply weight to AVG and OBP terms.

**Wire SV/H ratio into reliever values:** League 1: saves×3 + holds×2. League 2: saves×1 + holds×1. Changes RP surplus value calculations. Use saves_holds_ratio from league JSON. Implementation: SV_WEIGHT × saves + H_WEIGHT × holds in CBS FPTS formula for pitchers.

**Pressure test league settings with 5-10 real trades from both leagues:** Run concrete trades (e.g., Seager for Grisham, Skenes for Rice) through trade_analyzer.py with both league JSONs before building any user-facing UI. Edge cases that no theoretical design catches appear immediately in real data.

**Signal age indicator (build after Week 3):** Flag signals firing 8+ weeks without resolution. Display label: "Reassess — signal age X weeks." No verdict change — display layer only. signal_age = current_date - call_date in calls_tracker.csv.

**Hidden Gem detector (formal):** Query: fp_ownership<35%, wOBA>.330, xwOBA_gap>-0.020, luck>-0.085, PA>=75. Current: Rumfield (COL,10%), Herrera (STL,29%), Aranda (TB,27%), Bogaerts (SD,31%). Run Monday morning, publish Tuesday.

**Pitcher Slight Buy sensitivity:** n=4/yr too thin. Ablation: ERA floor 4.00→3.75 to grow SB sample. Gate B (HR/FB >+0.03 above career): best candidate, OOS 80.0% (+7.8pp) but n=3 SB OOS — retest after 2026 season.

**is_article_worthy() gate (build after Week 3):** SELL HIGH: owned>58% OR fp_rank<150. BUY LOW: owned>10% minimum.

**Platoon splits into projections:** DEFERRED mid-May (150+ PA). Infrastructure: hitter_career_platoon.json (489 batters).

### TIER 3 — Not blocking
- Dashboard sort bug (Advanced View — absolute magnitude)
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
| League settings JSON schema (league_1/2.json) | COMPLETE (Session 16) |
| league_settings.py loader + get_replacement_level() | COMPLETE (Session 16) |
| Dashboard toggle labels + taLeague wiring | COMPLETE (Session 16) |
| Wire league_settings.py into trade_analyzer.py | TIER 2 |
| Wire OBP/AVG stat_weights into score_value.py | TIER 2 |
| Wire SV/H ratio into reliever FPTS | TIER 2 |
| Trade tool architecture fix (signals → stats → value) | TIER 1 — NEXT SESSION |
| 5-10 real trade stress tests | TIER 2 |
| Search click bug | TIER 3 |

---

## SECTION 11: TRADE TOOL (known issues)

Architecture: trade_analyzer.py. CBS FPTS via _compute_cbs_fpts(). Replacement level via replacement_level.py. 12-team replacement levels: C=289.8 | 1B=275.7 | 2B=277.7 | 3B=267.0 | SS=293.9 | OF=296.3 | SP=221.5 | RP=157.0.

**Bug 1 — Skenes/Rice smell test FAIL:** Giving Skenes (ERA 0.95) for Rice (Sell High, wOBA .492) returns "Favorable for Rice side." Root cause: C positional scarcity overweights Rice surplus (+44) vs Skenes surplus (+33). Fix needed: top-20 player giveaway cannot return favorable verdict. This is a symptom of Bug 3.

**Bug 2 — Pitcher net stats misleading:** Giving Skenes shows ERA -1.50 as "positive change." Fix: replacement-level baseline for net stats.

**Bug 3 — Signals weight verdict directly (HIGHEST PRIORITY):** Current: signal tier feeds verdict logic. Correct: signal feeds projected stats only → projected stats determine value → verdict = comparison of two sides' projected value. Fix location: trade_analyzer.py verdict calculation. Once signals correctly modulate projected stats only, the downstream verdict naturally reflects both luck-adjusted upside AND positional value without circularity.

**Bug 4 — Search click:** Dashboard onClick intermittent. Tier 3.

**League settings not wired (Session 16):** league_settings.py and JSON files exist. Replacement levels are still fixed at 12-team standard (replacement_level.py). Next: load league from data/leagues/ based on active S.league in dashboard, pass to trade_analyzer. C:2 CBS vs C:1 Fantrax means Rice surplus differs between leagues.

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

**League Settings Phase 1 (Session 16):**
- `tvLeagueNames`: { league1: 'CBS 13-Team', league2: 'Fantrax 15-Team' } — toggle button labels updated
- `taLeague` default object extended with `roster_slots`, `saves_holds_ratio`, `team_count` (seeded from league1/CBS 13-team defaults)
- `_LEAGUE_DEFAULTS` constant (above `setLeague()`): mirrors data/leagues/*.json in JS for instant client-side access
- `setLeague(lg)` now calls `Object.assign({}, S.taLeague, defaults)` on toggle — switching CBS→Fantrax automatically updates: AVG→OBP, SV×3+H×2→SV×1+H×1, C:2→C:1, 13→15 teams
- `loadLeagueSettings()` seeds from league1 defaults on first visit (no localStorage record)
- Data files: data/leagues/league_1.json, data/leagues/league_2.json, data/leagues/template.json, league_settings.py

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

**Task Closure Discipline / Reducing WIP:** Every open Claude Code prompt is an open loop with mental overhead and merge risk. Finish the thing before starting the next thing. Senior engineers are relentless about this. A half-built feature is worse than a not-started one — it creates debt, confusion, and testing surface without shipping value.

**Time-Aware Signal Architecture:** A signal's value is a function of both its accuracy AND the correction window remaining. April signals are most valuable not just because they're accurate but because the window is longest. Building urgency into signal framing is product differentiation, not just presentation. "Buy Low — 22 weeks remaining to correct" is more actionable than "Buy Low." The correction window is part of the product.

**Momentum vs Merit Distinction:** Rank trajectory tells you what the market thinks. Contact quality tells you what the player is. When they diverge AND a luck signal fires, that's the three-layer narrative: merit says X, momentum says Y, luck explains the gap. "Don't chase" (rising rank + sell signal) and "Buy the dip" (falling rank + buy signal) are the mid-season content engine. This is not complexity for its own sake — it's a richer product for more of the season.

**Schema-First Architecture:** Define the data structure correctly once before building any UI. League settings JSON schema means the UI gets built once correctly instead of rebuilt three times as edge cases appear. The cost of getting the schema right upfront is two hours. The cost of retrofitting schema after UI is built is two days plus regression risk.

**Pressure Testing Before Productizing:** Run real trades through the tool with real league settings before building the user-facing UI. Edge cases that no theoretical design catches appear immediately in real data. Five concrete trades reveal more about architecture flaws than five hours of design review.

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
grep -n "_role_overridden" stat_projections.py
grep -n "XWOBA_PA_STAB" score_value.py
grep -n "PARK_FACTORS_PROJ" stat_projections.py
python -c "import pandas as pd; df=pd.read_csv('luck_scores.csv'); print('cbs_rank' in df.columns, df['cbs_rank'].notna().sum())"
python -c "import pandas as pd; df=pd.read_csv('pitcher_luck_scores.csv'); print('player_type' in df.columns, df['role_override'].sum(), 'overrides')"
python -c "from league_settings import load_league; lg=load_league('league_1'); print(lg['league_name'], lg['team_count'], 'teams')"
python -X utf8 validate_formulas.py
```
Expected: all greps find matches, cbs_rank ~330, player_type present + ~33 overrides, league_1 = "CBS 13-Team 13 teams", 37/37 PASS.
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
11. Tell Dustin: "Download updated thread_handoff.md to C:\Users\dusti\fantasy-baseball\thread_handoff.md"

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
- Why are _blend_ip SP fallback weights 0.45/0.55 instead of the normal 0.55/0.45?
- Why does the trade tool architecture need fixing — what is the current flow vs correct flow?
- Why does deeper league size produce LOWER replacement FPTS? (Prove with 15-team SP vs 13-team SP)
- What is the momentum vs merit distinction and what is the three-layer mid-season narrative?

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
Last push: May 1, 2026 (commit 4cfde51 — Session 16: League settings Phase 1 + SP role override + CBS aliases + _blend_ip SP fallback)
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

---

## SECTION 18: SESSION 16 CHANGELOG

**Session 16 — May 1, 2026**

1. CBS rank aliases: 5 entries added to _CBS_ALIASES in fetch_cbs_rank.py — Mike King (most important — CBS#27 Sell High was silently missing), Varland, Soroka, Junis, Ginn. Pitcher match rate 171→176.

2. SP role override system: Added player_name/team/ip alias columns + player_type (from Steamer GS) + role_override (True/False) to pitcher_luck_scores.csv output in score_pitcher_luck.py. 33 pitchers reclassified RP→SP via gates (total_starts>=5, IP>=20, IP/total_starts>=4.0). Display-only; verdict logic unchanged. Committed bcf0aff + 4869109.

3. _blend_ip() SP fallback fix in stat_projections.py: Steamer-RP pitchers demonstrably starting in 2026 get 0.45 Steamer + 0.55 pace blend (flipped — Steamer IP forecast is wrong for them). Schlittler: 7.5 → 74.8 IP. Committed 17cd159.

4. 110 IP cap: Applied in _blend_ip() for role-override path AND in project_pitcher_counting() fallback branch (for pitchers absent from Steamer like Chase Burns). Burns: 123.3 → 110.0 IP. Committed 17cd159.

5. get_replacement_level() formula corrected in league_settings.py: Was (0.90 + 0.10 × pool_ratio) — inverted. Fixed to (1.10 − 0.10 × pool_ratio). Deeper leagues now correctly produce lower replacement FPTS. 13-team SP: ~208 FPTS, 15-team SP: ~197 FPTS. Committed 4cfde51.

6. League settings Phase 1 complete:
   - data/leagues/league_1.json: CBS 13-Team (AVG, SV×3+H×2, C:2, P:9, 7 reserves)
   - data/leagues/league_2.json: Fantrax 15-Team (OBP, SV×1+H×1, C:1, P:10, 5 reserves)
   - data/leagues/template.json: blank schema for paid users
   - league_settings.py: load_league(), get_replacement_level(), get_stat_weight(), _validate()
   - dashboard.html: tvLeagueNames updated (CBS 13-Team / Fantrax 15-Team), taLeague extended with roster_slots/saves_holds_ratio/team_count, setLeague() merges _LEAGUE_DEFAULTS on toggle, loadLeagueSettings() seeds from league1 on first visit
   - Committed 4cfde51.

7. 37/37 PASS throughout session. No invariant failures. 5 commits pushed to GitHub.

**Files modified this session:**
- fetch_cbs_rank.py (aliases)
- score_pitcher_luck.py (alias columns, player_type, role_override block)
- stat_projections.py (_blend_ip SP fallback, project_pitcher_counting 110 IP cap, role_overridden parameter + call site)
- pitcher_luck_scores.csv (regenerated with new columns)
- league_settings.py (new file)
- data/leagues/league_1.json (new file)
- data/leagues/league_2.json (new file)
- data/leagues/template.json (new file)
- dashboard.html (tvLeagueNames, taLeague defaults, setLeague, loadLeagueSettings, _LEAGUE_DEFAULTS)
- thread_handoff.md (this file)
- CLAUDE.md (Session 16 changelog — if updated)

---

*End of thread_handoff.md — Sections 1-18 complete.*
*Overwrite completely at end of every session. Single source of truth.*
*Save to: C:\Users\dusti\fantasy-baseball\thread_handoff.md*
