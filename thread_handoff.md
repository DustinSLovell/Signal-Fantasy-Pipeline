# THE SIGNAL FANTASY — Thread Handoff Document
# Complete project state. Overwrite at end of every session.
# Last updated: May 5, 2026 (Sessions 1–25)
# DO NOT skim. Read every section before acting.

---

## SESSION START — MANDATORY VERIFICATION PROTOCOL

Before responding to ANY session goal, Claude must:

1. READ SECTIONS 1–23 IN FULL using multiple Read calls.
   KNOWN TRUNCATION RISK: The doc exceeds 16,000 chars. Sections 5–10
   are often cut off in a single Read call. Always run a second Read
   call starting at line ~900 before declaring the doc read.

2. PROVE comprehension by stating unprompted:
   - The exact Tier 1 item marked HIGHEST PRIORITY
   - The hard deadline item and its date
   - The current track record fraction
   - The last GitHub commit hash and what it did

3. Do NOT proceed until Dustin confirms the comprehension check
   looks correct.

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

### Week 3 Article — DRAFTED May 5, 2026
**Status:** Draft complete at outputs/week3_article_draft.md — ready to publish to Substack.
**Lead:** Luzardo ERA 6.41→4.72 (luck +0.369→+0.720) — strongest buy low confirmation in dataset.
**Deepening signals:** Stewart (luck +0.214→+0.439), Carter (luck +0.227→+0.449), Ramírez (+0.508→+0.496).
**Honest miss:** Bradish (FIP up 1.24 — skill issue, luck +0.178→+0.111).
**New buy:** Trent Grisham (luck +0.577, BABIP .145, xwOBA .395, 15% owned).
**Get Hyped:** Cam Schlittler (ERA 1.96, FIP 1.41, SwStr 15.7%, 41.3 IP — real skill, not luck).
**Chapman LA delta:** -17.2° confirmed sell signal.
**CBS divergences:** Soto ESPN#7/CBS#186 (data artifact), Betts ESPN#43/CBS#268 (low PA).
**Rolling 4-week window framing throughout — no win/loss % published (Week 10 threshold).**

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

### _blend_sb() — Stolen Base Projection (stat_projections.py — Session 22)
```python
def _blend_sb(mlbam_id, games_remaining, sprint_sb) -> float:
    """0.65/0.35 Steamer-ROS/sprint blend.
    Calibrated on 2025 OOS actuals (n=235):
      sprint-only MAE=7.53 | 65/35 blend MAE=5.42 | Steamer pure MAE=4.72
    65/35 is 14.8% worse than Steamer — within 15% tolerance threshold.
    """
    steamer_ros = steamer_full_season_sb × (games_remaining / 162.0)
    blended = 0.65 × steamer_ros + 0.35 × sprint_sb
    return min(65.0, max(0.0, blended))  # SB cap = 65
```
Data source: `_STEAMER_SB` dict from Steamers 2025 batters.csv SB column.
Sprint tier input: `sprint_sb = sb_pg × games_remaining × health_factor` (from sprint_speed/PA lookup).
Returns sprint_sb unchanged when no Steamer data (rookies, NPB).
Systematic miss: elite breakout speedsters (Chandler Simpson 44 actual / 6 proj) — inherently
unresolvable from April sprint data; roster moves and breakouts cannot be predicted.
Top improvements: De La Cruz ROS 13→31, Carroll 9→22, Turang 9→29.
**FIXED (Session 23):** `score_value.py` now uses Steamer individual SB via `_load_steamer_sb()`.
Position defaults (SS=8.5, CF=9.0) have been replaced for 428/434 hitters. See below.

### _load_steamer_sb() — SB Fix in score_value.py (Session 23)

**Root cause of 9/15 largest model vs FP ranking divergences:** score_value.py used position-based SB defaults (SS=8.5, CF=9.0) ignoring individual speed profiles. stat_projections.py had `_blend_sb()` (Session 22) but score_value.py never called it.

**Fix:** `_load_steamer_sb()` in score_value.py reads Steamers 2025 batters.csv, converts to per-PA rate (steamer_sb / steamer_pa), returns {mlbam_id: sb_per_pa}. SB override block in main() iterates all hitters after `project_hitter_stats()` and replaces SB_proj = sb_per_pa × PA_proj. TWP override and Ohtani PLAYER_SB_PER_600 still applied LAST (take precedence).

```python
def _load_steamer_sb() -> dict:
    """Load Steamer full-season SB projections and convert to per-PA rate.
    Returns {mlbam_id (int): sb_per_pa (float)}.
    """
    # Reads: Steamers 2025 batters.csv (root dir)
    # Returns sb / pa per player
```

**Coverage:** 428/434 hitters updated. 6 kept position default (rookies/NPB not in Steamer CSV).

**Top improvements (L1 FPTS impact):**
- De La Cruz SB 8.5→48.4 (+23.4 L1)
- Turang SB 8.5→37.3 (+18.5 L1)

**Henderson/Turner still floor-propped — root cause updated (Session 24):**
After SB fix AND 0.85 floor fix (Session 24), Henderson remains at CQS floor. Root cause confirmed:
- Henderson: After 0.85 fix, AVG_proj=0.230 → avg_liability_mult=1.000 (penalty fully eliminated). ESV=2.211.
  CQS floor = 20.0. ESV 2.211 still below floor → floor-propped. SB and AVG fixes closed the gap but
  CQS floor = 20.0 requires ~10× more ESV than current projections can deliver at this PA level.
  Not fixable via AVG gate or SB fix — Henderson's model rank reflects real projection, not a bug.
- Turner: career_ba=0.290 (NOT 0.229 — prior session had a data error). Gate fires at 0.240 threshold.
  ESV=0.179 because Turner bats leadoff (PHI slot 1): RBI_mult=0.83 (17% RBI suppression). His projected
  RBI_proj≈63 is pulled down by lineup context. Z-score ~13th SS out of 18 roster spots = near replacement.
  Turner's issue is structural surplus calculation + leadoff RBI penalty, not AVG gate.
  Fix requires architectural change (CQS bypass for buylow signals, or surplus formula redesign).

---

### Decline Detection Layer (stat_projections.py — Session 22)
4-gate trigger for age 32+ hitters in `project_player()`. Operates in Layer 2 — no Layer 1 touch.
```python
# ALL four gates must pass:
age_val >= 32
speed_vs_career < -0.5      # latest sprint speed minus career avg (multi-year hitter_sprint_speed.json)
hh_rate_delta < -0.03       # hard-hit rate down >3pp vs career baseline
la_delta < 0 OR chase_delta > 0.02  # at least one mechanical signal (launch angle OR chase)

# Applied multipliers:
proj_r   × 0.94
proj_rbi × 0.94
proj_hr  × 0.92
```
`_speed_vs_career(mlbam_id)`: reads `hitter_sprint_speed.json` (NOT `hitter_career_sprint.json`).
Key distinction: `hitter_sprint_speed.json` → `{str_id: {speeds:{year:mph}, latest_speed}}` (multi-year).
`hitter_career_sprint.json` → `{int_id: float}` (single career average — used by signal model penalty).
`latest_speed - mean(prior_years)` requires the multi-year structure.
3 of 98 age-32+ hitters triggered: Seager (R 61→57, RBI 54→51, HR 18→17), Harper, Polanco.
Altuve BYPASSED: speed_vs_career=-0.47 (above -0.5), HH delta=+6.7pp (above -0.03 threshold).
Freeman BYPASSED: speed_vs_career=-0.87 BUT hh_rate_delta=+3.7pp (positive, gate fails).
`decline_flag: True/False` added to `projections_2026.csv` COLUMNS and both hitter/pitcher row dicts.
CQS floors dominate for triggered players — rank unchanged in `player_values.json`.

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
New Session 22 functions: `_blend_sb()` (65/35 Steamer-ROS/sprint; wires via `_STEAMER_SB` dict), `_load_sprint_yearly()` (reads hitter_sprint_speed.json multi-year structure into `_SPRINT_YEARLY`), `_speed_vs_career(mlbam_id)` (returns latest_speed minus prior-years average for decline detection). Decline detection block in `project_player()`: 4-gate trigger (age≥32, speed<-0.5, hh<-0.03, la<0 or chase>0.02) → proj_r/rbi×0.94, proj_hr×0.92; `decline_flag` output field. Note: `_STEAMER_SVH` dict and `_blend_sv_h()` (Session 21) handle RP saves/holds projections.

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
**Session 23 additions:** `_load_steamer_sb()` (reads Steamers 2025 batters.csv → {mlbam_id: sb_per_pa}); SB override block in main() replaces position-default SB with Steamer-individual for 428/434 hitters. Career BA conditional floor: gate `career_ba>=0.240 AND (career_ba-xBA)>0.040 → AVG_proj=max(xBA, career_ba×0.75)`.
**Session 24 update (COMPLETED):** Raised 0.75→0.85. Henderson: AVG_proj 0.209→0.230, avg_liability_mult 0.802→1.000 (penalty eliminated). ESV 1.779→2.211 (+24%). Still CQS floor-propped (ESV 2.211 < floor 20.0). Backtest C validation: gate-fires MAE 0.0679→0.0507 (-25%) on 7 historical players.
0.240→0.230 threshold lowering: BLOCKED — Chapman (Sell High, cba=0.237) would get avg_liability_mult relief (0.424→0.666), which is directionally wrong. Threshold stays at 0.240.
Turner: career_ba=0.290 (NOT 0.229 as prior session stated — that was a data error). Turner ALREADY fires the gate. His ESV=0.179 (pre-Session-25) was a surplus ranking + OBP calculation issue.
**Session 25 OBP anchor fix (COMPLETED):** OBP_proj previously used raw xba_col (before career anchor applied), while AVG_proj already had career anchor. Inconsistency: Turner AVG_proj=0.247 (career-anchored) but OBP_proj derived from raw xBA=0.218.
Fix: moved OBP_proj calculation to AFTER avg_proj career anchor block; use avg_proj instead of xba_col.
Before/after (5 players): Turner OBP 0.286→0.313, ESV 0.179→0.733 (+309%); Chisholm OBP 0.265→0.305, ESV 2.315→3.137, L1 15.0→18.4; Henderson OBP ~0.284→0.294, ESV 2.211→2.421; Bichette OBP unchanged (gap < 0.040); Montgomery OBP unchanged (career_ba=0.188 < 0.240).
Turner still CQS floor-propped (ESV 0.733 < floor 20.0). Correct: he's ~13th SS in 14-team OBP league, PHI slot-1 RBI_mult=0.83 (4th worst in MLB). Near-replacement status confirmed as real, not model error. Sanchez guard confirmed: career_ba=0.214 < 0.240 → gate fails → OBP unchanged.
37/37 PASS. Sanchez C#24 ✓.

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

### TIER 1 — Do immediately (Session 24+)

**Career BA floor multiplier fix: 0.75 → 0.85 (COMPLETED Session 24):**
score_value.py line ~929: `career_ba >= 0.240 AND (career_ba - xBA) > 0.040 → AVG_proj = max(xBA, career_ba * 0.85)`.
Henderson: AVG_proj 0.209→0.230, avg_liability_mult 0.802→1.000 (penalty eliminated). ESV 1.779→2.211 (+24%).
Backtest C validation: gate-fires MAE 0.0679→0.0507 (-25%) on 7 historical players — all improved individually.
Henderson still CQS floor-propped (ESV 2.211 < floor 20.0) — SB and AVG fixes closed the gap but CQS dominates.
**0.240→0.230 threshold: PERMANENTLY BLOCKED.** Chapman (Sell High, career_ba=0.237) would receive
avg_liability_mult relief (0.424→0.666) — partially undoing the sell signal. Wrong direction. Do not revisit.
**Turner correction + Session 25 OBP anchor fix (COMPLETED):** career_ba=0.290. Turner fires the career AVG gate.
ESV=0.179 (pre-Session-25) was partly caused by OBP/AVG inconsistency: AVG_proj career-anchored but OBP_proj still used raw xBA=0.218. OBP anchor fix (Session 25) moved OBP calc to after avg_proj anchor; Turner OBP 0.286→0.313, ESV 0.179→0.733 (+309%). Still CQS floor-propped at L1=20.0.
Full diagnostic (Session 25): PHI slot-1 RBI_mult=0.83 = 4th worst in MLB (slots 7/8/9 OBP .221/.291/.302 → weighted .278 vs lg_avg .324). Turner is ~13th SS in 14-team OBP league. Montgomery (#14 SS replacement) projects 26 HR/85 RBI. Turner's near-replacement status is real in this league configuration, not a model error.
Fix D verdict confirmed — no further fix warranted for Turner's CQS floor positioning.

**RP saves/holds projection fix (COMPLETED Session 21):**
`_blend_sv_h()` wired in stat_projections.py. `_STEAMER_SVH` dict loads Steamer 2025 full-season
SV+HLD. Scales by remaining-season fraction. 165 RPs now have proj_sv_h > 0.
Validation (Session 22): MAE=0.6 vs Steamer ROS-scaled — mathematically equivalent to Steamer.
Steamer full-season SV vs CBS 2025 actuals MAE=5.8 — irreducible baseline (closer role volatility).

**2B full audit — Chisholm slot fix (COMPLETED Session 22):**
Jazz Chisholm slot 6→5 (manual_override=True) in hitter_batting_slot_2026.json.
RBI_mult 1.1209→1.2000 (hit 1.20 cap); R_mult 0.9353→0.9482; projected RBI 48→52.
Altuve: no active decline flags (speed -0.47 above -0.5 threshold, HH rate +6.7pp positive).
FP gap is about projected PA at age 36 — decline detection layer is the correct long-term fix.

**Player decline detection layer (COMPLETED Session 22):**
4-gate trigger for age 32+ hitters. ALL must pass:
age>=32 AND speed_vs_career<-0.5 AND hh_rate_delta<-0.03 AND (la_delta<0 OR chase_delta>0.02)
Multipliers: proj_r×0.94, proj_rbi×0.94, proj_hr×0.92 (Layer 2 only — no Layer 1 touch).
3 of 98 age-32+ hitters triggered: Seager (32), Harper (34), Polanco (33).
Altuve CORRECTLY bypassed: speed -0.47 (above -0.5), HH +6.7pp (positive threshold fails).
Freeman CORRECTLY bypassed: speed -0.87 BUT hh_rate_delta +3.7pp (positive gate fails).
CQS floors dominate for all 3: Seager ESV=3.75 < floor=45; Harper ESV=1.69 < floor=60.
Rank unchanged in player_values.json due to CQS floor protection.
`decline_flag` column in projections_2026.csv (True/False per player).

**SB projection fix in stat_projections.py (COMPLETED Session 22):**
`_blend_sb()` implemented. 65/35 Steamer-ROS/sprint blend.
Backtest: sprint-only 7.53 MAE | 65/35 blend 5.42 MAE | Steamer pure 4.72 MAE.
65/35 is 14.8% worse than Steamer — within 15% threshold, adopted as production weight.
Before/after: De La Cruz 13→31 SB (ROS), Carroll 9→22, Turang 9→29.
Systematic miss: elite breakout speedsters (Chandler Simpson 44 actual/6 proj) — unresolvable.
NOTE: Only stat_projections.py is fixed. score_value.py still uses position defaults (see above).

**CQS interaction with active Buy Low signals (Ramírez, Stewart, Caminero suppressed):**
CQS floor props up José Ramírez (floor=40) even when luck_score is strongly positive (+0.483).
The floor does not modulate up for strong buy signals — it only prevents downside. Audit: are
there cases where the floor IS suppressing a buy signal's upside? Expected answer: no, floors
are lower bounds only. Confirm with Ramírez, Stewart, Caminero spot check.

---

**Young Breakout Player Projection Fix (COMPLETED Sessions 19-20):**
Root cause IDENTIFIED (Session 19): career weight was NOT the lever. career_weight_sweep.py proved
that career HR weight 0.60→0.00 changes FPTS by only +1.7 points (HR coefficient 0.43 is 5×
weaker than R/RBI coefficients 2.81/2.08). Real root cause: Steamer 2025 projected Rice as backup
catcher (G=48.4, PA~190) when he's now an everyday starter. Steamer PA dominates the blend at
70/30 Steamer/pace weights → ROS PA of only 285. R and RBI suffer catastrophically (6.5× more
valuable than HR per unit in CBS FPTS). Career weight tuning was the wrong lever.

**Fix COMPLETED (Sessions 19-20):**
stale-Steamer override in _blend_pa(). Final four-gate system:
1. steamer_games ∈ [40, 80) — Steamer projected as backup/part-time
2. pa_so_far >= 80 — confirmed sustained usage
3. pace_ros > steamer_ros × 1.5 — current pace significantly exceeds Steamer
4. (Gate 4 was ownership/CBS_rank check — deemed unnecessary after Session 20 audit)
G floor raised 20→40, PA gate 80+. Override count: 120 (initial) → 30 (Session 19) → ~9 final.
Fires for ~9 legitimately role-changed players. Jordan Walker same archetype.

**Rice before/after Sessions 19-20:**
- Original: PA=285, HR=11, R=36, RBI=32, surplus=-47 (pre-fix)
- Session 19: PA=384, HR=15, R=48, RBI=42, surplus=-15 (+32 points)
- Session 20 (CQS decay + AVG floor): surplus approximately -15 (minor change)
Smell tests: Skenes→Rice=-110 AVOID ✓ | Skubal→Rice=-98 AVOID ✓ | Acuña→Rice=-213 AVOID ✓
Short-baseline confidence flag (display-only): "Short baseline — under 300 career PA."
In trade_analyzer.py and dashboard.html. No verdict change.

**Trade Tool Edge Case Analysis (COMPLETED Sessions 19-20):**
1. ✅ C replacement level calibrated: Drake Baldwin #3 catcher is correct boundary
2. ✅ Career weight sensitivity sweep DONE: career weight irrelevant (HR coef too small)
3. ✅ PA threshold crossover: Rice needs ~480 PA for +60 surplus (not achievable until mid-June)
4. ✅ Gate audit complete: 9 legitimate overrides confirmed; 111 noise cases eliminated

**--explain Flag (paid tier feature — fully built, commit 4277a8f):**
Built Session 18. Prints full CBS coefficient walkthrough for any trade on demand.
Free tier: verdict label only.
Paid tier: full --explain breakdown — projection inputs, signal multipliers, per-term FPTS
calculation, replacement level reference, surplus.
ALREADY BUILT: python trade_analyzer.py --explain
Next: surface this in dashboard as premium feature toggle.

**Week 3 article (May 5-6 deadline):** Monday run → update → report. Lead: Matt Chapman LA delta -17.2°. Manual Get Hyped: Cam Schlittler (ERA 1.96/FIP 1.41/xERA 1.57/CBS #3 — three metrics agree). CBS divergences: Soto ESPN#7/CBS#186, Betts ESPN#43/CBS#268. Ohtani quiet worry flag. April Big Board: 17/23 = 73.9%. Release luck score spreadsheet (promised Article #2).

**Trade tool architecture fix — COMPLETE (Session 17, commit fda45c4):** Correct 5-step flow implemented. Signals adjust projected stats only. Verdict = adjusted surplus delta. Skenes correctly SP+95 surplus, Rice correctly -47 surplus. All 3 smell tests PASS. See Section 11.

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

**Ownership Acceleration Tracking (Tier 2 — start capturing now):**
Add week-over-week ownership delta columns to player_ownership_2026.csv. Players showing
rapid ownership increase (e.g., 10%→20%→60% over three weeks) = market breakout signal.
Two uses:
1. Additional gate input for steamer_pt_override: if ownership jumping fast, player has
   confirmed playing time and is no longer a "backup" regardless of Steamer G.
2. Standalone content signal for articles: "fastest rising ownership players this week"
   surface before the market fully prices them in.
Implementation: fetch_ownership.py saves weekly snapshot CSVs (like signal_board XLSX).
delta_own_1w and delta_own_4w columns computed from snapshots. Add to dashboard and
hidden gem query as secondary sort key.
**Start capturing weekly snapshots NOW so delta data exists by mid-May.**
Currently have no historical ownership snapshots — every week of delay = one fewer data point.

**Ohtani Two-Player League Configuration (Tier 2 — required before trade tool goes public):**
Ohtani displays as RP in position tables with +216 surplus (hitter CBS stats run through
pitcher formula = nonsense). In standard leagues, Ohtani is a hitter only and the RP
surplus should be suppressed. In two-way player leagues, he splits into hitter + pitcher
with separate surplus calculations.
Do NOT hardcode a suppression rule — this requires league_settings.json configuration.
Implementation:
- Add two_way_players list to league_settings.json (default: empty = standard league)
- In trade_analyzer.py: if player in two_way_players → show both rows; else hitter only
- Add Ohtani (660271) to two_way_players for two-way leagues
Currently: trade tool resolves Ohtani correctly as a hitter when queried directly by name.
Only surfaces as noise in position-table diagnostics, not user-facing trade output.
Non-blocking for beta; blocking for general public launch.

**Steamer Dependency Audit (pre-paid-tier requirement):**
Before activating paid tier, determine licensing path for Steamer ROS projections. Options in priority order:
1. Contact Jared Cross / FanGraphs for commercial license terms — do this at 200 free subscribers, not at launch
2. Evaluate licensable alternatives (PECOTA, etc.)
3. Accelerate own projection system to replace Steamer entirely (see item below)
Current status: Steamer 2025 CSV used as 2026 ROS proxy — acceptable for development and free tier. Not acceptable for paid product without resolution.
Priority: TIER 2. Promote to TIER 1 at 200 free subscribers or when licensing becomes a blocker.

**Own Projection System (Steamer replacement — Phase 2):**
Goal: replace Steamer ROS dependency with Signal Fantasy native projections. Two-phase approach:
Phase 1 (now): Steamer as trusted proxy while trade tool architecture is built and validated. Do not let this dependency slow down the architecture fix.
Phase 2 (mid-season or offseason): swap Steamer out underneath the same trade tool architecture. The tool doesn't change — just the data feeding into Step 1.

Infrastructure already built:
- pace-blend PA/IP engine (_blend_pa, _blend_ip) ✅
- career baselines (BABIP, xwOBA, K%, chase, sprint) ✅
- signal adjustment multipliers (Backtest B v2) ✅
- lineup context module ✅
- park factor adjustments ✅
- age decay curves ✅

Remaining gaps vs Steamer:
- HR projection (currently Steamer-dependent)
- W/L projection for pitchers (team context needed)
- Full counting stat engine independent of Steamer PA/IP

Build order:
1. Confirm trade tool architecture works correctly with Steamer as input (Phase 1 complete)
2. Build native counting stat projections using pace-blend as foundation
3. Backtest native projections vs Steamer on 2025 OOS data
4. If MAE gap < 15%, swap Steamer out underneath trade tool
5. Publish "We built our own projection system" as content

Priority: TIER 2 now. Promote to TIER 1 at 150 free subscribers or when Steamer licensing becomes a blocker.

### TIER 3 — Not blocking
- Dashboard sort bug (Advanced View — absolute magnitude)
- Trade tool search click bug
- ESPN injury status real endpoint
- Nola/Rogers ERA gap fix (~1 run miscalibration)
- Post-blend AVG floor (26 hitters below .195)
- fp_rank refresh (shows preseason, not in-season)
- **SS and OF replacement level review:** Current run shows SS repl=251.2 (Masyn Winn) and
  OF repl=246.2 (Jake McCarthy). Both appear elevated — check whether these are depressing
  surplus values for those positions relative to CBS fantasy context. Non-blocking: SS and
  OF top-15 lists look correct, but replacement player selection may shift with more data.
  Revisit after 200+ PA per replacement-level player.

**Threads Split Project (core vs. reference architecture):**
Trigger: handoff doc crosses ~2,500 lines OR a major new system
(trade tool live, mid-season architecture, paid tier) adds 300+
lines of reference content. Whichever comes first.

Workstream:
1. Audit current doc — tag every section as CORE (session-start
   required) or REFERENCE (on-demand lookup only)
2. Create thread_handoff_core.md — verification protocol, session
   goal, Tier 1 parking lot, current track record, last commit,
   active signals, known bugs. Hard ceiling: 800 lines.
3. Create thread_handoff_reference.md — full model specs, accuracy
   tables, backtest methodology, article archive, career lessons,
   data notes, player disambiguation. Grows without limit.
4. Update verification protocol — comprehension check runs against
   core only. Reference sections cited by name when needed
   ("check Reference Section 6 for pitcher model thresholds").
5. Update session start/end checklists in Section 14 — core file
   gets overwritten each session as today; reference file gets
   appended/updated only when relevant sections change.
6. Update CLAUDE.md to reflect new two-file structure.
7. Smoke test: run one full session with split structure, confirm
   CC reads core completely and can locate reference content
   on demand without missing critical session-start context.

Priority: TIER 3 now. Promote to TIER 1 when trigger condition met.

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
| Trade tool architecture fix (signals → stats → value) | COMPLETE (Session 17) |
| 5-10 real trade stress tests | TIER 2 |
| Search click bug | TIER 3 |

---

## SECTION 11: TRADE TOOL (known issues)

Architecture: trade_analyzer.py. CBS FPTS via _compute_cbs_fpts(). Replacement level via replacement_level.py.

**Current replacement levels (ROS scale — from projections_2026.csv):**
C=219.4 | 1B=226.9 | 2B=212.4 | 3B=189.8 | SS=252.2 | OF=247.1 | SP=201.0 | RP=193.2
(Note: these differ from CLAUDE.md values which were from an earlier pipeline run)

**Bug 3 — FIXED (Session 17, commit fda45c4):** Signals now feed projected stats only. Correct 5-step flow implemented:
1. Steamer ROS projections (from projections_2026.csv)
2. _apply_signal_multipliers() — Backtest B v2 multipliers on proj stats
3. CBS FPTS regression on adjusted projections
4. Surplus vs replacement level at player's position
5. Verdict = get_surplus_total − give_surplus_total → _trade_verdict_v3()

**Session 18 additions (commit 4277a8f):**
- Surplus display now per-player with position and replacement reference:
  "Give surplus: Skenes +95 (SP, repl 201) | Get surplus: Rice -47 (C, repl 219)"
- --explain flag: step-by-step CBS valuation walkthrough (model projections → signal mults
  → per-term FPTS calc → replacement level → surplus → verdict summary)
- _blend_pa GP estimation fix: when games_played=0 (ESPN endpoint limitation) but pa_so_far>=5,
  estimates gp_eff = max(pa_so_far // 4, 5). Prevents Steamer-only domination.
  Rice: projected_pa 155→285 (but counting stats unchanged — rate model dominates).

**Rice surplus clarification (permanent architectural note):**
Rice adj surplus = -47. This is model's intentional Sell High signal, not a bug.
Architecture: projections_2026.csv has in-model LUCK_MULTIPLIERS (R×0.94 Sell High);
trade tool adds Backtest B v2 on top (R×0.92). Combined: R×0.865.
Career HR rate (0.029) blending down current barrel rate (0.052) → 0.041 blended.
CBS projects 28 HR vs our 11 HR. Known under-projection for young breakout players.
Will improve when native projection system replaces Steamer 2025 proxy (Tier 2 parking lot).

**Smell test evidence (May 2, 2026):**

Case 1 — Giving Skenes SP / Getting Rice C (Sell High):
- Skenes: player_type=SP correctly resolved, adj surplus +95 (unadj +95, neutral signal)
- Rice: Sell High → R×0.92, RBI×0.92 → adj surplus -47 (unadj -34)
- Delta: -142 → AVOID ✓

Case 2 — Giving Skubal SP / Getting Rice C:
- Skubal: neutral signal, adj surplus +84
- Rice: adj surplus -47
- Delta: -131 → AVOID ✓

Case 3 — Giving Acuña Buy Low / Getting Rice Sell High:
- Acuña: Buy Low → R×1.08, HR×1.05, RBI×1.08 → adj surplus +208 (unadj +178)
- Rice: adj surplus -47
- Delta: -255 → AVOID ✓
- Architecture confirmed: verdict driven by adjusted surplus delta, not signal badges

**Bug 1 — RESOLVED by Bug 3 fix.** C positional scarcity no longer overweights Rice; Rice actual surplus is -34 (unadj) to -47 (sell-high-adjusted) — correctly below SP/elite OF surplus.

**Bug 2 — Pitcher net stats display:** Still shows raw proj stats in player card, not replacement-level-relative. Lower priority — display issue only, verdict is correct.

**Bug 4 — Search click:** Dashboard onClick intermittent. Tier 3.

**League settings not wired:** league_settings.py and JSON files exist. Replacement levels still fixed at 12-team standard (replacement_level.py). Next Tier 2: load league from data/leagues/ based on active S.league in dashboard. C:2 CBS vs C:1 Fantrax changes Rice surplus between leagues.

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

**Two-Location Problem Revisited (Score_value vs Stat_projections):** score_luck.py computes luck signal. stat_projections.py computes projected counting stats. score_value.py computes trade/rank value. These are THREE SEPARATE computations with THREE SEPARATE AVG anchors. Fixing AVG in stat_projections.py does NOT fix AVG in score_value.py. Any data correction must audit all downstream consumers independently — there is no single fix that propagates everywhere.

**PA-Scaled Floor Decay — Why Current Dormancy Is Correct:** CQS floor decay requires ≥150 current-season PA before activating. Early May PA counts (27-75) are all below threshold. This is not a bug — it's early-season protection by design. Veteran with one bad week should not lose their floor protection. Floor decay activates mid-May exactly when enough track record exists to trust. Impatience about dormant protections is the enemy of well-calibrated thresholds.

**Career BA Gate Design (0.240 / 0.040):** The conditional floor gate has two components: (1) career_ba ≥ 0.240 ensures the floor only applies to legitimate contact hitters, not career-low-AVG players using a bad April as cover; (2) gap > 0.040 ensures the floor only fires when the deviation is meaningful, not for normal statistical noise. Gary Sanchez (career_ba=0.214) correctly fails gate (1). This dual-gate design is reusable pattern for any career-based floor logic.

**Cross-Stat Consistency in Career Anchoring:** When a career anchor is applied to one stat (AVG), it should be propagated to any other stat that depends on the same underlying input. AVG_proj and OBP_proj both depend on xBA — if xBA is career-anchored for AVG, the same anchored value must be used for OBP or the two stats become inconsistent (Turner AVG=0.247 from career anchor but OBP derived from raw xBA=0.218 before the fix). The principle: one anchor input → one consistent value → all downstream stats. Audit every downstream stat after adding a career anchor.

**Ablation Gate Design for Sell-Signal Players:** Before lowering any buy-side threshold, explicitly list every player newly captured and check their current signal. Chapman (Sell High, career_ba=0.237) failing the 0.230 ablation test is the canonical case: lowering the gate fires a "correct" career BA floor but reduces a sell penalty — directionally wrong. The sell-side incompatibility is invisible until you enumerate the new-capture list. Always enumerate before committing.

**Career BA Verification Against Live Data vs Summaries:** Prior session summary said Turner career_ba=0.229 (FG "injury years only"). Live _load_fg_career_ba() returned 0.290. The summary was wrong — it described a hypothesis about what the data would show, not what it actually showed. When a memory or summary describes what data "should" contain, verify against the actual code/file output before acting on it. Summaries rot; code doesn't.

**ESV vs CBS FPTS — Not the Same Number:** ESV (Expected Stats Value) is a Z-score above replacement, not CBS FPTS. A player projecting 300 FPTS who ranks 13th at their position in a 13-team league has ESV ≈ 0 (near replacement). Turner's ESV=0.179 is not a projection bug — he projects fine (87R/17HR/63RBI/20SB/0.247), but Z-scored against 18 SS roster spots, he's ~13th. The scale_to_100 then maps that near-zero Z-score to near-zero L1. Confusing ESV for "raw value" leads to phantom debugging.

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
grep -n "_blend_sb\|_STEAMER_SB" stat_projections.py
grep -n "_load_steamer_sb\|_steamer_sb_per_pa" score_value.py
grep -n "decline_flag\|_speed_vs_career" stat_projections.py
grep -n "_role_overridden" stat_projections.py
grep -n "XWOBA_PA_STAB" score_value.py
grep -n "PARK_FACTORS_PROJ" stat_projections.py
grep -n "_load_fg_career_ba\|career_ba_lookup" score_value.py
grep -n "cqs_floor_base\|pa_2026.*150\|floor_base.*decay" score_value.py
grep -n "avg_proj.*bb_col\|OBP_proj.*avg_proj" score_value.py
python -c "import pandas as pd; df=pd.read_csv('luck_scores.csv'); print('cbs_rank' in df.columns, df['cbs_rank'].notna().sum())"
python -c "import pandas as pd; df=pd.read_csv('pitcher_luck_scores.csv'); print('player_type' in df.columns, df['role_override'].sum(), 'overrides')"
python -c "from league_settings import load_league; lg=load_league('league_1'); print(lg['league_name'], lg['team_count'], 'teams')"
python -X utf8 validate_formulas.py
```
Expected: all greps find matches, _blend_sb present, decline_flag present, _load_fg_career_ba present in score_value.py, _load_steamer_sb present in score_value.py, cqs_floor_base present, OBP_proj uses avg_proj (Session 25 anchor fix), cbs_rank ~330, player_type present + ~33 overrides, league_1 = "CBS 13-Team 13 teams", 37/37 PASS.
4. Check Sanchez invariant (rank 24 catchers as of Session 20). If any check fails: STOP and report.

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
   **HANDOFF OWNERSHIP: Claude Code (CC) is solely responsible for regenerating thread_handoff.md
   every session. Claude.ai does NOT write it. CC reads the current file in full, incorporates all
   session changes, and overwrites. Confirm with: "thread_handoff.md updated and pushed. Download to
   C:\Users\dusti\fantasy-baseball\thread_handoff.md"**
10. Add a dated changelog block to CLAUDE.md (do NOT overwrite — append the
    `--- [Date] (Session N) ---` block only and update the "Last updated" line).
    This keeps both files in sync without destroying CLAUDE.md's Claude Code formatting.
11. git add . && git commit -m "Session N — [description]" && git push
12. Tell Dustin: "Download updated thread_handoff.md to C:\Users\dusti\fantasy-baseball\thread_handoff.md"

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
Last push: May 5, 2026 (commit d18cf76 — Session 23: score_value.py SB fix (_load_steamer_sb) + decline backtest + AVG audit + Rutschman audit + CLAUDE.md changelog)
Session 24 commit: 57acd3d — AVG floor 0.75→0.85 + ablation (0.240 threshold blocked) + projection scorecard + thread_handoff.md
Session 25 commit: fbc249a — OBP anchor fix (score_value.py OBP_proj now uses career-anchored avg_proj) + Turner/SS diagnostic + thread_handoff.md
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

## SECTION 18 (continued): SESSION 17 CHANGELOG

**Session 17 — May 2, 2026**

1. **Update 3 housekeeping:** Added two new Tier 2 parking lot items to thread_handoff.md:
   - Steamer Dependency Audit (pre-paid-tier, promote at 200 subscribers)
   - Own Projection System (Phase 2 Steamer replacement, promote at 150 subscribers)
   Commit f0639ad.

2. **Trade tool architecture fix (Bug 3) — commit fda45c4:**

   **trade_analyzer.py changes:**
   - `_derive_pos()`: now uses `player_type` column from pitcher_luck_scores.csv first (Steamer GS-based, most reliable). Falls back to `role_override`, then to IP/starts heuristic. Skenes correctly classified SP.
   - `_get_fpos()`: pitchers now routed through `_derive_pos()` instead of player_values.json pos_map. Reason: player_values.json can lag when score_value.py run predates role corrections (Skenes was RP in pos_map).
   - `_apply_signal_multipliers()`: new function. Backtest B v2 multipliers applied to proj stat columns.
     Hitters: BL→R×1.08/HR×1.05/RBI×1.08; SB→R×1.04/HR×1.02/RBI×1.04; SS→R×0.96/RBI×0.96; SH→R×0.92/RBI×0.92.
     Pitchers: BL→WHIP×0.95/K×1.05; SH→ERA×1.10/WHIP×1.05/K×0.95.
     AVG + HR sell-side excluded (hurt MAE in Backtest B v2).
   - `_trade_verdict_v3()`: new function. Surplus delta thresholds: ≥50 STRONG, ≥20 FAVORABLE, ≥5 SLIGHTLY FAVORABLE, ≤-50 AVOID, ≤-20 UNFAVORABLE, ≤-5 SLIGHTLY UNFAVORABLE, else NEUTRAL.
   - `_analyze_and_display()`: rewritten verdict section.
     Step 2: apply signal multipliers to give/get rows
     Step 3: CBS FPTS on adjusted projections
     Step 4: surplus vs replacement level
     Step 5: verdict = get_surplus_total - give_surplus_total → _trade_verdict_v3()
     Luck scores shown as informational context only (no longer drive verdict)
     Removed "giving up buy-low for sell-highs" framing — replaced by surplus comparison

   **Signal multiplier constants:**
   ```python
   _H_SIGNAL_MULTS = {
       "buy low":    {"proj_r": 1.08, "proj_rbi": 1.08, "proj_hr": 1.05},
       "slight buy": {"proj_r": 1.04, "proj_rbi": 1.04, "proj_hr": 1.02},
       "slight sell": {"proj_r": 0.96, "proj_rbi": 0.96},
       "sell high":  {"proj_r": 0.92, "proj_rbi": 0.92},
   }
   _P_SIGNAL_MULTS = {
       "buy low":  {"proj_whip": 0.95, "proj_k": 1.05},
       "sell high": {"proj_era": 1.10, "proj_whip": 1.05, "proj_k": 0.95},
   }
   ```

3. **Smell test results (all 3 PASS):**
   - Case 1 (Skenes SP→Rice SH): give+95/get-47/delta-142 → AVOID ✓
   - Case 2 (Skubal SP→Rice SH): give+84/get-47/delta-131 → AVOID ✓
   - Case 3 (Acuña BL→Rice SH): give+204/get-47/delta-251 → AVOID ✓
   Skenes shows as SP (player_type=SP), surplus vs SP replacement (+201 FPTS).

4. 37/37 PASS throughout session. 3 commits pushed: f0639ad, fda45c4 + this doc.

**Files modified this session:**
- thread_handoff.md (Tier 2 items + Section 11 update + Session 17 changelog)
- trade_analyzer.py (architecture fix)

**Remaining Tier 1 (next session):**
- Weekly tracker mechanism classifier
- April Big Board

---

## SECTION 18 (continued): SESSION 18 CHANGELOG

**Session 18 — May 2, 2026**

1. **trade_analyzer.py surplus display fix — commit 4277a8f:**
   Changed single aggregated "give +95 | get -47 | delta -142" to per-player labeled lines:
   "Give surplus: Paul Skenes +95 (SP, repl 201)"
   "Get  surplus: Ben Rice    -47 (C,  repl 219)"
   "Surplus delta: -142  (value edge outgoing)"
   Makes reference point unambiguous — each player shows their own position and replacement FPTS.

2. **--explain flag added to trade_analyzer.py — commit 4277a8f:**
   Full step-by-step CBS valuation walkthrough for any trade.
   Step 1: Model projections (from projections_2026.csv, already signal-informed)
   Step 2: Trade-tool signal multipliers (Backtest B v2) — lists each multiplier applied
   Step 3: CBS FPTS per-term calculation (each coefficient × stat = subtotal, then total)
   Step 4: Position, replacement FPTS (N=12 etc.), surplus = FPTS − replacement
   Verdict summary: per-player surplus, total surplus, delta, verdict label.
   Usage: python trade_analyzer.py --explain
   Architecture note shown: "in-model: R/RBI ×0.94, SB ×0.95 already applied" for Sell High.
   This is Tier 1 paid-tier content: "here's exactly how the model evaluates a trade."

3. **_blend_pa GP estimation fix in stat_projections.py — commit 4277a8f:**
   When games_played=0 (ESPN player_wl endpoint returns ACTIVE for all, GP never populates)
   but pa_so_far >= 5, estimates gp_eff = max(pa_so_far // 4, 5).
   Prevents Steamer 2025 proxy dominating entirely for players with stale Steamer roles.
   Rice: projected_pa 155→285. Counting stats unchanged because rate model dominates:
   blended HR rate 0.041 → int(285 × 0.041) = 11 HR (same as int(155 × 0.041) = 6... wait).
   Actually Rice's stats didn't change because blended_hr_rate = 0.041 → both old and new PA
   gave 11 HR. Confirmed generate_projections.py regenerated with same R=36/HR=11/RBI=32.
   Root: career_hr_rate (0.029) drag + thin career weight (0.60) = blended 0.041.
   Fix prevents worse cases for other breakout players.

4. **Rice -47 surplus — permanent architectural note:**
   Not a bug. Model's honest Sell High signal:
   - In-model LUCK_MULTIPLIERS (stat_projections.py): R×0.94, RBI×0.94 (Sell High)
   - Trade tool _H_SIGNAL_MULTS (Backtest B v2): R×0.92, RBI×0.92
   - Combined effect: R×0.865, RBI×0.865 of "raw" model projection
   - Career HR rate drag: 0.029 career vs 0.052 current → 0.041 blended
   - CBS projects 28 HR vs our 11 HR: known under-projection for young breakout players
   - This gap = motivation for Own Projection System (Tier 2 parking lot)
   - The trade tool correctly says: "selling Rice at peak is the right move"

5. **All 3 smell tests PASS with new display:**
   - Case 1 (Skenes→Rice): give+95/get-47/delta-142 → AVOID ✓
   - Case 2 (Skubal→Rice): give+84/get-47/delta-131 → AVOID ✓
   - Case 3 (Acuña→Rice): give+208/get-47/delta-255 → AVOID ✓

6. **37/37 PASS. All invariants PASS** (Sanchez rank 22, Yordan rank 8, Raleigh rank 2, Baldwin rank 3, Contreras rank 5).

**Files modified this session:**
- trade_analyzer.py (surplus display + --explain flag)
- stat_projections.py (_blend_pa GP estimation fix)
- data/projections_2026.csv (regenerated May 2, minor date/luck_score change)
- CLAUDE.md (Session 18 changelog)
- thread_handoff.md (Section 11 update + Session 18 changelog)

**Remaining Tier 1 (next session):**
- Weekly tracker mechanism classifier
- April Big Board
- White paper Section 10

---

## SECTION 19: SESSION 19 CHANGELOG

**Session 19 — May 3, 2026**

### Root cause identified: stale Steamer PA projection

career_weight_sweep.py (new diagnostic, not production) proved career weight was NOT the lever for Rice's -47 surplus.

Key finding: HR coefficient in CBS FPTS (×0.43) is 5× weaker than R (×2.81) and RBI (×2.08). Sweeping career_weight 0.60→0.00 changes projected HRs by ~4 (+1.7 FPTS). That's noise. R and RBI dominate — and both are PA-driven. Crossover analysis: reaching +60 surplus via HR alone requires 233.8 HRs (impossible). Career weight is not the variable to tune.

Real broken variable: Steamer 2025 projected Rice as a backup catcher (G=48.4, PA~190). He's now an everyday starter. With gp_eff-tiered 60/40 Steamer/pace blend → steamer_ros=153, pace_ros=483 → PA=285. All counting stats suppressed. R and RBI (6.5× more FPTS value than HR) are the real victims.

### Fix implemented: stale-Steamer override in `_blend_pa()`

Three-gate system as of Session 19 (fourth ownership gate audited Session 20 — deemed unnecessary):
1. `steamer_games ∈ [40, 80)` — Steamer projected as backup/part-time, not everyday
2. `pa_so_far >= 80` — confirmed sustained usage (not injured/optioned player with 17 PA)
3. `pace_ros > steamer_ros × 1.5` — current pace significantly exceeds Steamer ROS projection
(Gate 4 — ownership/CBS_rank — was skipped: 9 remaining overrides were all legitimate without it)

G floor raised 20→40 (Session 19 audit: 97/120 overrides were fringe bench at G=20-39).
pa_so_far >= 80 gate eliminates injured/optioned players with <25 PA who fire on ratio alone.
Override count: 120 (initial) → 30 (Session 19 gate tightening) → ~9 (final, confirmed Session 20).

**Rice before/after:**
- Old: PA=285, HR=11, R=36, RBI=32, surplus=-47 (vs C replacement 219.4)
- Session 19: PA=384, HR=15, R=48, RBI=42, surplus=-15 (vs C replacement 239.2)
- Improvement: +32 surplus points. Final state post-Session 20: surplus ≈ -15.

**Smell tests re-verified after Session 19 gate changes:**
- Case 1 (Skenes→Rice): give+95/get-15/delta-110 → AVOID ✓
- Case 2 (Skubal→Rice): give+84/get-15/delta-98 → AVOID ✓
- Case 3 (Acuña→Rice): give+198/get-15/delta-213 → AVOID ✓

### Max Muncy MLBAM disambiguation — bug fixed

Root cause: `project_player(name="Max Muncy")` used `_fuzzy_find()` → always returned LAD row (first match). ATH Muncy (691777) was silently getting LAD Muncy's (571970) projections in `projections_2026.csv` and `player_values.json`.

Fix: optional `mlbam_id` parameter added to `project_player()`. When provided, filters fuzzy matches by MLBAM ID — exact row selected, not first-alphabetical. `generate_projections.py` now passes `batter=` and `pitcher=` IDs from source CSVs to `project_player()` for every player.

General fix — applies to any future duplicate-name player (no hardcoded Muncy logic).

Verification:
- LAD Muncy (571970): .233 AVG / 15 HR / 52 R / 41 RBI — Sell High
- ATH Muncy (691777): .208 AVG / 10 HR / 31 R / 30 RBI — Sell High (distinct, lower stats)
- Both appear correctly in luck_scores.csv (was always correct — uses batter ID for dedup)

### Ohtani display edge case — flagged, no code change

Standard leagues: Ohtani appears as hitter only. His pitcher_luck_scores.csv classification as RP
produces +216 surplus when hitter CBS stats are run through pitcher formula — nonsense.
Only surfaces in position-table diagnostics, not in user-facing trade tool output.
Requires `two_way_player` flag in league_settings.json before trade tool goes public.
Logged in Tier 2 parking lot. Non-blocking for beta.

### Full override player audit completed

120 override players characterized. Three categories:
- TOP (surplus > 0, 6 players): Dingler +53, Aranda +53, Baldwin +53, Goodman +17, Anthony +20, Rice +3
- BORDERLINE (−20 to 0, 3 players): Schmitt ≈0, Kim +6, Moniak −1
- NOISE (surplus < −20, 111 players): deep bench, <1% owned, CBS rank >250
Gate tightening (G 40+, PA 80+) reduced 120→30. Session 20 ownership gate reduces to ~9.

### 37/37 PASS. All invariants PASS.
Sanchez rank=22 ✓ | Yordan rank=8 ✓ | Raleigh rank=2 ✓ | Baldwin rank=3 ✓ | Contreras rank=5 ✓

**Files modified:**
- stat_projections.py (stale-Steamer override, G floor 20→40, PA>=80 gate, mlbam_id param in project_player)
- generate_projections.py (mlbam_id passed for hitters + pitchers)
- data/projections_2026.csv (regenerated — Muncy fixed, override count 30, new stats)
- data/player_values.json (regenerated via score_value.py --write — Muncy surplus corrected)
- CLAUDE.md (Session 19 changelogs — two entries)
- thread_handoff.md (this file)
- career_weight_sweep.py (new diagnostic — not production)

**Commits:** ba07bd7 (stale-Steamer fix + short-baseline flag) | 37a2e1e (gate tightening + Muncy fix)

**Remaining Tier 1 (Session 20 — COMPLETED):**
- ✅ Fix 1 (stat_projections.py): veteran exception + career BA floor raised 0.195→0.210
- ✅ Fix 2 (score_value.py): conditional career AVG floor via _load_fg_career_ba()
- ✅ Fix 3 (score_value.py): CQS PA-decay floor (100%→50% linear, 150-750 PA range)
- Fourth gate audit: ownership gate deemed unnecessary (9 legitimate overrides already clean)
- PA crossover: Rice needs ~480 PA for +60 surplus — mid-June at current pace

---

## SECTION 20: SESSION 20 CHANGELOG

**Session 20 — May 4, 2026**

Three score_value.py / stat_projections.py AVG + CQS fixes. No Layer 1 signal model changes.

### Fix 1 — stat_projections.py veteran exception + career BA floor bump

**Changes:**
- `career_ba_floor` raised 0.195 → 0.210 in `hitter_true_talent()`
- Veteran exception added: when `career_pa >= 1000` AND `formula_avg >= career_ba` AND `formula_avg >= 0.240`:
  blend becomes 0.50/0.50 instead of 0.65/0.35 (allows hot-start vets more credit)
- Gate prevents exception from helping poor-AVG veterans (< 0.240 formula_avg)

**Motivation:** Established hitters (Freddie Freeman, Trea Turner) with good current-year AVG
were being dragged down too aggressively toward career mean. Floor bump protects against
extreme downside for career-.250+ hitters whose April AVG < .210.

### Fix 2 — score_value.py conditional career AVG floor

**New helper:** `_load_fg_career_ba()` — PA-weighted career batting average from 4 FG CSVs.
- Sources: data/fg_batting_{2022-2025}.csv (batter_id, pa, ba columns)
- Returns: dict[mlbam_id → career_ba] for all batters with any PA

**Modified:** `project_hitter_stats()` signature now accepts `career_ba_lookup: dict | None = None`

**Conditional floor logic (inserted after xBA/AVG computation):**
```python
if career_ba >= 0.240 AND (career_ba - xBA) > 0.040:
    AVG_proj = max(xBA, career_ba * 0.75)
```
Gate requires: (1) career BA respectable (≥.240), (2) current xBA materially below career mean (>40pts gap).
Purpose: prevents score_value.py from projecting a career-.270 hitter at .195 when April xBA is .215.

**Sanchez invariant by design:** Gary Sánchez career_ba=0.214 < 0.240 → gate fails → NO floor applied.
This is correct and load-bearing. His AVG liability (proj ~.200) remains the invariant anchor.

**Key before/after (career_ba, xBA→AVG_proj):**
- Jazz Chisholm (career_ba=.258): xBA=.188 → AVG_proj=.193 (floor=.258×.75=.194, applied)
- Brendan Donovan (career_ba=.274): xBA=.199 → AVG_proj=.205 (floor=.274×.75=.206, applied)
- Gary Sánchez (career_ba=.214): xBA=.198 → AVG_proj=.198 (gate fails, no floor)

**In main():**
```python
_career_ba_lookup = _load_fg_career_ba()
hitter_df = project_hitter_stats(hitter_df, cfg, career_ba_lookup=_career_ba_lookup)
```

### Fix 3 — score_value.py CQS PA-decay floor

**Formula:**
```python
floor_eff = floor_base × max(0.50, 1.0 - (pa_2026 - 150) / 600)
```
- PA < 150: full floor (no decay, early-season protection)
- PA 150-750: linear decay from 100% → 50%
- PA > 750: permanent 50% floor (veteran never falls below half floor)

**PA source:** current-season PA from luck_scores.csv (hitter_luck_input.csv PA column)
h_merged now carries `PA` column from hitter_df for floor decay computation.

**`cqs_floor_base` field added** to player_values.json output (alongside existing `cqs_floor`).
This allows auditing how much decay has been applied at any point in the season.

**Current state (May 4):** ALL 5 egregious cases below 150 PA — decay is dormant.
Floor will activate mid-May as PA accumulates. This is correct behavior (early-season protection).
5 egregious cases (by estimated floor inflation vs natural ESV):
- Yelich: floor=60, natural ESV≈0 → +60 inflation (PA≈27 → no decay yet)
- Goldschmidt: floor=60, natural ESV≈0 → +60 inflation (PA≈49 → no decay yet)
- Springer: floor=40, natural ESV≈0 → +40 inflation (PA≈75 → no decay yet)
- Betts: floor=40, natural ESV≈28 → +12 inflation (PA≈43 → no decay yet)
- Rutschman: floor=35, natural ESV≈30 → +5 inflation (PA≈75 → no decay yet)

**Rutschman post-fix:** catcher rank 15 (tied with Realmuto at L1=35.0). No change at current PA.
Will surface mid-May as his PA increases and Yelich/Goldschmidt floors decay.

### Sanchez invariant results

Post-Fix 2 + Fix 3: Gary Sánchez catcher rank = **24** (L1=14.7). PASS ✓
All invariants:
- Yordan Álvarez: rank 8 overall ✓
- Cal Raleigh: catcher rank 2 ✓
- Drake Baldwin: catcher rank 4 ✓
- William Contreras: catcher rank 5 ✓
- Gary Sánchez: catcher rank 24 ✓ (must be ≥21)

### 37/37 PASS (validate_formulas.py)

### Files modified (Session 20)
- stat_projections.py (Fix 1: veteran exception + career BA floor 0.195→0.210)
- score_value.py (Fix 2: _load_fg_career_ba() + conditional AVG floor; Fix 3: CQS PA-decay)
- data/projections_2026.csv (regenerated — AVG projections updated for ~40 hitters)
- data/player_values.json (regenerated — cqs_floor_base field added, AVG values updated)
- CLAUDE.md (Session 20 changelog + parking lot refresh)
- thread_handoff.md (this file)

**Commits:** f1123e1 (AVG floor + CQS decay) | 2e4655a (BARREL_TO_HR + misc Session 19-20) | ebd9a67 (CLAUDE.md)

**All 5 Session 21 Tier 1 items resolved in Sessions 21-22.** See changelogs below.

---

## SECTION 21: SESSION 21 CHANGELOG

**Session 21 — May 5, 2026**

1. **Two-track accuracy framework (weekly_update.py):**
   - `LUCK_NORMALIZE_BUY=0.100`, `LUCK_NORMALIZE_SELL=-0.085`: refuted only fires when luck signal clears
   - `LUCK_DEEPEN_THRESH=0.030`: "deepening" classification when luck score rises 30+ pts in 4-week window
   - `TRACK1_RESOLUTION_WEEK=10`: accuracy % suppressed until Week 10 (~mid-June)
   - Rolling 4-week window: `rolling_4wk_woba_delta`, `rolling_4wk_luck_delta`, `window_signal` columns
   - `window_signal` values: "confirming" | "deepening" | "still_waiting" | "refuted_4wk" | "insufficient_data"
   - `_classify_window_signal()` added; `_classify_mechanism()` updated to check curr_luck before "refuted"
   - `cmd_report()` shows collection-phase breakdown before Week 10 instead of accuracy %
   - Recomputed mechanism: 17 refuted → 2 genuine refuted + 15 still_waiting
   - 2 genuine refuted: Isaac Collins (slight sell, luck cleared), Pete Crow-Armstrong (luck -0.014)
   - Bradish: luck 0.111 = still_waiting BUT window_signal=refuted_4wk (honest miss framing in article)

2. **RP saves/holds projection fix (stat_projections.py):**
   - `_STEAMER_SVH` dict: loads Steamer full-season SV+HLD per pitcher from Steamers 2025 pitchers.csv
   - `_blend_sv_h(mlbam_id, games_remaining, is_starter, current_ip)`: scales Steamer by remaining fraction
     `remaining_frac = min(1.0, 0.70 × games_frac + 0.30 × (1.0 - ip_used_frac))`
   - Starters always return (0.0, 0.0); RPs with no Steamer return (0.0, 0.0)
   - 165 RPs now have `proj_sv_h > 0`: Helsley 30, Iglesias 28, Williams 27, Miller 25
   - `generate_projections.py`: `proj_sv_h` column added to COLUMNS and pitcher row dicts

3. **Week 3 article draft (outputs/week3_article_draft.md):**
   - Lead: Luzardo ERA 6.41→4.72 (luck +0.369→+0.720), strongest buy low confirmation in dataset
   - Deepening: Stewart (luck +0.214→+0.439), Carter (luck +0.227→+0.449), Ramírez (+0.508→+0.496)
   - Honest miss: Bradish (FIP up 1.24 — skill issue, luck +0.178→+0.111)
   - New buy: Trent Grisham (luck +0.577, BABIP .145, xwOBA .395, 15% owned)
   - Ke'Bryan Hayes (luck +0.551, BABIP .136, 0.5% owned) — secondary buy
   - Get Hyped: Cam Schlittler (ERA 1.96, FIP 1.41, SwStr 15.7%, 41.3 IP — skill, not luck)
   - Chapman LA delta: -17.2° confirmed sell
   - CBS divergences: Soto ESPN#7/CBS#186 (artifact), Betts ESPN#43/CBS#268 (low PA)
   - Rolling 4-week window framing throughout — no win/loss % published

4. **2B audit (diagnostic):**
   - Chisholm: slot=6 (n=27 games, NYY), speed_flag + chase_flag correct. Luck=0.099, not a buy.
     Action: slot 3 would improve R_mult significantly (noted for next slot refresh).
   - Altuve: slot=3, age=36, la_delta=-8.7°, HH rate +6.7pp (positive). No active decline flags.
     Model 2B #8, FP rank #40. Gap is FP projecting more PA — decline layer is correct long-term fix.

5. **SB/speed projection diagnostic (no fix this session):**
   - Root cause confirmed: position-default SB formula misses extreme speed outliers and zeroes out correctly.
   - Top under-projections: De La Cruz (-27.9 vs Steamer), Carroll (-19.8), Garcia (-15.9)
   - Fix approach identified: blend proj_sb with Steamer ROS SB (implemented Session 22)

6. **37/37 PASS. All invariants PASS.** Sanchez C#24, Yordan #2, Raleigh C#2, Baldwin C#4, Contreras C#5.

**Files modified:**
- weekly_update.py (accuracy framework — constants, _classify_mechanism, window_signal logic, cmd_report)
- stat_projections.py (_STEAMER_SVH, _load_pt_lookups, _blend_sv_h, project_pitcher_counting)
- generate_projections.py (proj_sv_h column)
- data/projections_2026.csv (regenerated)
- data/player_values.json (regenerated)
- data/calls_tracker.csv (rolling_4wk columns + mechanism recompute)
- outputs/week3_article_draft.md (NEW — full Week 3 article draft)
- CLAUDE.md (Session 21 changelog)

---

## SECTION 22: SESSION 22 CHANGELOG

**Session 22 — May 5, 2026**

1. **Chisholm batting slot fix (data/hitter_batting_slot_2026.json):**
   Jazz Chisholm MLBAM 665862: slot 6 → 5. `manual_override: true` flag added.
   RBI_mult 1.1209 → 1.2000 (hit 1.20 cap). R_mult 0.9353 → 0.9482.
   Impact: projected RBI 48→52 (+4). Rank unchanged at 2B #14 — CQS tier cluster.
   FP #2 gap not closable by slot alone; speed_flag+chase_flag penalties still active (correct).

2. **`_blend_sb()` module (stat_projections.py):**
   `_STEAMER_SB` dict (Steamers 2025 batters.csv SB column).
   `SPRINT_YEARLY_JSON` + `_load_sprint_yearly()` (reads hitter_sprint_speed.json multi-year structure).
   `_blend_sb(mlbam_id, games_remaining, sprint_sb)`: 0.65/0.35 Steamer-ROS/sprint blend, cap=65.
   `project_hitter_counting()`: sprint_sb → blended_sb → SB (replaces position-default formula).
   ROS SB after fix: De La Cruz 13→31, Carroll 9→22, Turang 9→29.
   NOTE: score_value.py has independent SB logic — does NOT call `_blend_sb()`. See Tier 1 parking lot.

3. **SB backtest (weight calibration, n=235, 2025 CBS actuals):**
   Weight sweep: sprint-only 7.53 MAE | 50/50 5.84 | **65/35 5.42** | Steamer pure 4.72.
   65/35 is 14.8% worse than Steamer — within 15% tolerance → adopted as production weight.
   Systematic miss: elite breakout speedsters — irreducible (roster unknowns, no April predictors).

4. **Decline detection layer (stat_projections.py + generate_projections.py):**
   `_speed_vs_career(mlbam_id)`: latest sprint speed minus prior-years career average.
   Requires ≥2 seasons from `hitter_sprint_speed.json` (NOT `hitter_career_sprint.json`).
   4-gate trigger: age≥32 AND speed<-0.5 AND hh<-0.03 AND (la<0 OR chase>0.02).
   Multipliers: proj_r×0.94, proj_rbi×0.94, proj_hr×0.92.
   Triggers: 3 of 98 age-32+ hitters: Seager (32), Harper (34), Polanco (33).
   Altuve CORRECTLY bypassed: speed_vs_career=-0.47, HH +6.7pp — neither gate fires.
   `decline_flag` column added to generate_projections.py COLUMNS + hitter/pitcher row dicts.
   CQS floors dominate: rank unchanged in player_values.json for all 3 triggered players.

5. **Ranking audit — model vs FP top 25 divergences:**
   Root cause: SB under-projection in score_value.py (position defaults vs Steamer individual).
   9 of 15 largest divergences are primarily SB-driven.
   
   Top 15 divergences (model pos rank vs FP pos rank, positive = model ranks higher than FP):
   | Player | Pos | Model | FP | Gap | Classification |
   |--------|-----|-------|----|-----|----------------|
   | Gunnar Henderson | SS | #4 | #1 | 3 | NEEDS REVIEW (SB+AVG) |
   | Elly De La Cruz | SS | #15 | #2 | 13 | NEEDS REVIEW (SB) |
   | Trea Turner | SS | #9 | #3 | 6 | NEEDS REVIEW (SB+AVG) |
   | Ryan Turang | SS | #13 | #4 | 9 | NEEDS REVIEW (SB) |
   | Julio Rodríguez | CF | #? | top-5 | large | NEEDS REVIEW (SB) |
   | Bobby Witt Jr. | SS | #? | top-5 | large | NEEDS REVIEW (SB) |
   | Corbin Carroll | OF | #? | top-5 | large | NEEDS REVIEW (SB+Sell) |
   | José Ramírez | 3B | #? | top-3 | large | NEEDS REVIEW (SB+CQS) |
   | Bo Bichette | SS | #? | top-5 | large | NEEDS REVIEW (SB+AVG) |
   | Adley Rutschman | C | #15 | #1 | 14 | NEEDS REVIEW (low-PA slump) |
   | Xander Bogaerts | SS | high | lower | large | NEEDS REVIEW (AVG) |
   | Alex Bregman | 3B | high | lower | large | NEEDS REVIEW (AVG) |
   | José Altuve | 2B | #8 | #40 | 32 | JUSTIFIED (age 36, no decline layer) |
   | Carlos Correa | SS | high | lower | moderate | JUSTIFIED (realistic current stats) |
   | Cal Raleigh | C | #2 | #1 or 2 | small | JUSTIFIED (model correctly bullish) |
   
   ACTION: Wire Steamer individual SB into score_value.py (Tier 1 HIGHEST PRIORITY).
   Estimated to close 6+ of top-10 divergences.

6. **Saves/holds validation:**
   `_blend_sv_h()` vs Steamer ROS-scaled: MAE=0.6 (essentially identical — model = scaled Steamer).
   Steamer 2025 SV vs CBS 2025 actuals: MAE=5.8 (irreducible closer volatility baseline).
   Top projections: Helsley 30, Iglesias 28, Williams 27, Miller 25. Ordering looks reasonable.

7. **37/37 PASS throughout. All invariants PASS.**
   Sanchez C#24 ✓ | Yordan #2 ✓ | Raleigh C#2 ✓ | Baldwin C#4 ✓ | Contreras C#5 ✓

**Files modified:**
- data/hitter_batting_slot_2026.json (Chisholm slot 5, manual_override)
- stat_projections.py (_STEAMER_SB, _load_sprint_yearly, _speed_vs_career, _blend_sb,
  project_hitter_counting SB line, decline detection block with all 4 gates)
- generate_projections.py (decline_flag column added to COLUMNS + row dicts)
- data/projections_2026.csv (regenerated — decline flags + SB blend, 849 total players)
- data/player_values.json (regenerated)
- CLAUDE.md (Session 22 changelog)

**Commit hash:** faf4cf7

**Remaining Tier 1 (Session 23):**
1. score_value.py SB fix — wire Steamer individual SB (closes 6+ ranking divergences)
2. Publish Week 3 article (outputs/week3_article_draft.md) — OVERDUE

---

## SECTION 23: SESSION 23 CHANGELOG

**Session 23 — May 5, 2026**

### Task 1 — score_value.py SB fix (HIGHEST PRIORITY — COMPLETED)

**Problem:** score_value.py used position-based SB defaults (SS=8.5, CF=9.0) ignoring individual
speed profiles. stat_projections.py had `_blend_sb()` (Session 22) but score_value.py had independent
SB logic and never called it. This was the root cause of 9/15 largest model vs FP ranking divergences.

**Fix:** `_load_steamer_sb()` new helper function in score_value.py (added after `_load_fg_career_ba()`).
- Reads Steamers 2025 batters.csv, converts to per-PA rate (steamer_sb / steamer_pa)
- Returns {mlbam_id (int): sb_per_pa (float)}; gracefully returns {} if CSV missing
- SB override block added in `main()` after `project_hitter_stats()`, before TWP override:
  `SB_proj = steamer_sb_per_pa[bid] × PA_proj` for all Steamer-matched hitters
- TWP override and Ohtani PLAYER_SB_PER_600 still applied LAST (take precedence)

**Coverage:** 428/434 hitters updated. 6 kept position default (rookies/NPB not in Steamer CSV).

**Top impacts (L1 FPTS):**
- Elly De La Cruz: SB 8.5→48.4 (+23.4 L1)
- Ryan Turang: SB 8.5→37.3 (+18.5 L1)
- Both escape CQS floor suppression at their new ESV levels

**Henderson/Turner still floor-propped — root cause is AVG, not SB:**
After SB fix: Henderson ESV still suppressed by avg_liability_mult (AVG_proj=0.209 → mult=0.802).
Root cause chain: career BA gate fires (career_ba=0.270, gap=0.061) BUT floor = max(xBA=0.209,
0.270×0.75=0.202) = 0.209 → floor below xBA → gate fires but has zero effect. 0.75 multiplier
is the true bottleneck. Fix: raise to 0.85 (see Tier 1 parking lot — Session 24 task).

**37/37 PASS. All invariants PASS:** Sanchez C#24, Yordan #2, Raleigh C#2, Baldwin C#4, Contreras C#5,
Will Smith C#7.

### Task 2 — Decline Backtest (multiplier validation — diagnostic only)

**Question:** Are ×0.94 R/RBI and ×0.92 HR decline multipliers empirically justified?

**Method:** Applied 4-gate trigger to 2025 April data (backtest_A_hitters_2025.csv, n=235).
Sprint data from hitter_sprint_speed.json. HH rate and LA delta from backtest_decline_2025_metrics.csv.

**Result:** n=3 triggered in 2025 (Trea Turner, Mookie Betts, Neil McNeil).
- Turner/Betts: injury-recovery years — both wildly OUTPERFORMED model (injury → peak return, not decline)
- McNeil: correctly underperformed (R=42 vs 68 model, -39%)
- n=3 is too small to calibrate. Multipliers unchanged.

**3-gate proxy (drop speed gate, n=12):** Median R=0.891, RBI=0.878 — underperformance direction correct.
Confirmed declines: Goldschmidt (HR=0.60), Arenado (R=0.74), Rojas (R=0.58).
**Verdict:** Multipliers directionally sound. Need 50+ triggered player-seasons for proper calibration
(earliest: end-of-2026 season). Leave at ×0.94/0.94/0.92.

**New file:** data/backtest_decline_2025_metrics.csv (471 players: HH rate + avg LA from April 2025 BBEs).
Columns: batter, n_bbe, hh_rate, career_hh_rate, hh_delta_2025, avg_la, career_la, la_delta_2025.

### Task 3 — AVG Projection Audit (diagnostic only — no code changes)

**Henderson:** career_ba=0.270, gate fires (gap=0.061>0.040), but floor = max(xBA=0.209, 0.270×0.75=0.202)
= 0.209 → no improvement. Root cause: 0.75 multiplier means floor (0.202) < xBA (0.209) → useless.
Fix (not implemented): raise 0.75→0.85 → floor=0.230 → escapes avg_liability_mult.

**Turner:** FG window 2022-2025 gives career_ba=0.229. Gate threshold is 0.240 → gate fails.
His pre-2022 .300+ seasons are excluded (2022+ rule change per CLAUDE.md architectural decision).
Fix (not implemented): lower threshold 0.240→0.230 → Turner captured. Needs ablation.

**Adames:** career_ba=0.233 < 0.240 → gate fails. Correct behavior — genuine low-BA hitter.

**Bregman:** FG 2022-2024 (injury years, 2025 data missing) → career_ba=0.166. Data gap.
His true career BA (including 2025) likely 0.260+. Fix: add 2025 FG data or manual override.

**Key insight:** Henderson/Turner ESV suppression is AVG-liability-driven (not SB-driven).
avg_liability_mult formula: (1 - (0.220 - AVG_proj) × 18.0). Henderson at 0.209 → mult=0.802.
Until AVG_proj rises above 0.220, ESV remains ~20% suppressed regardless of SB or counting stats.

### Task 4 — Rutschman Ranking Audit (diagnostic — no fix needed)

**Model C#15, FP C#13 — gap is small.** Root cause: PA_proj=341 (vs FP likely 550+) suppresses all
counting stats. CQS floor=35 is correctly calibrated for Established Star tier.
wOBA=0.384 > xwOBA=0.355 → no buy signal available. No model error.
**Verdict:** Playing time dispute, not model error. Will naturally resolve as PA accumulate mid-May.

### Parking Lot Changes (Session 23)

**Removed from Tier 1:** score_value.py SB fix → COMPLETED.

**Added to Tier 1 (HIGHEST PRIORITY for Session 24):**
Career BA floor multiplier 0.75→0.85. Henderson canonical case. 1-line change.
Gate: career_ba ≥ 0.240 AND (career_ba - xBA) > 0.040 AND career_ba × 0.85 > xBA.
Sanchez guard confirmed safe (career_ba=0.214 < 0.240).

**Also added Tier 1:** AVG gate threshold 0.240→0.230 (captures Turner).
Requires ablation test first: show all newly captured players; if any look wrong, STOP and report.

### 37/37 PASS throughout. All invariants PASS.

**Files modified:**
- score_value.py (_load_steamer_sb() + SB override block in main())
- data/player_values.json (regenerated)
- data/backtest_decline_2025_metrics.csv (NEW — diagnostic, April 2025 BBE metrics, 471 players)
- CLAUDE.md (Session 23 changelog + parking lot updates)

**Commit hash:** d18cf76

---

## SECTION 21: SESSION 24 CHANGELOG

**Session 24 — May 5, 2026**

Continuation from Session 23 close. No Layer 1 signal model changes. All work in score_value.py.

### Task 1 — Session start baseline (established before any changes)

Scorecard confirmed:
- validate_formulas.py: 37/37 PASS
- Sanchez: C#25, L1=16.4 (invariant: 21+) — PASS (note: rank number changed from Session 23 due to pipeline re-run)
- Yordan: overall #2, L1=97.4 — PASS
- Henderson: ESV=1.779, CQS floor-propped, AVG_proj=0.209, avg_liability_mult=0.802

### Task 2 — Career BA floor multiplier 0.75→0.85 (COMPLETED)

**Change:** score_value.py line ~929: `cba * 0.75` → `cba * 0.85`

**Before/after Henderson:**
- AVG_proj: 0.209 → 0.230
- avg_liability_mult: 0.802 → 1.000 (penalty fully eliminated)
- ESV: 1.779 → 2.211 (+24%)
- Still CQS floor-propped (ESV 2.211 < floor 20.0) — floor closes it out

**Backtest C validation (gate-fires n=7):**
| Metric | No Floor | ×0.75 | ×0.85 | Steamer |
|--------|----------|-------|-------|---------|
| All 235 MAE | 0.0216 | 0.0214 | 0.0211 | 0.0187 |
| Gate-fires (n=7) MAE | 0.0679 | 0.0623 | 0.0507 | — |

All 7 gate-firing players improve individually. All errors remain negative (still conservative).
7 gate-firing players from backtest C: Jacob Wilson, Jake Mangum, Chandler Simpson, Nick Kurtz, Dillon Dingler, Isaac Collins, Hunter Goodman.

**37/37 PASS. Sanchez rank 25 (still ≥ 21). All invariants PASS.**

### Task 3 — AVG gate threshold ablation: 0.240 → 0.230 (BLOCKED — do not implement)

Ablation showed 32 new players captured at 0.230. Three have sell signals:
- **Matt Chapman (Sell High, career_ba=0.237, xBA=0.188):** avg_liability_mult 0.424 → 0.666. This REDUCES the sell penalty — wrong direction. Chapman's sell signal is confirmed by LA delta -17.2° and contact quality degradation. Undoing part of his penalty is architecturally incorrect.
- Eugenio Suárez (Slight Sell, career_ba=0.238): same issue — sell penalty partially undone
- Jorge Soler (Slight Sell, career_ba=0.233): same issue

Decision: threshold stays at 0.240. The sell-signal incompatibility is a hard blocker.

**Turner correction identified:** Prior session summary claimed Turner career_ba=0.229 (FG "injury years only"). Actual _load_fg_career_ba() output = 0.290. Turner ALREADY fires the gate at 0.240. His ESV=0.179 is a surplus ranking issue (Z-score ~13th SS in 13-team league, with PHI slot-1 RBI_mult=0.83 suppression), not an AVG gate issue.

### Task 4 — Backtest validation of 0.85 fix

Already covered in Task 2 table. Validated — gate-fires MAE -25%. Fix adopted.

### Task 5 — Bregman investigation

Checked fg_batting_2025.csv: EXISTS. Bregman (MLBAM 608324) PA=495, BA=0.273.
Prior session claim "2025 data missing" was WRONG — it was a faulty summary.
career_ba = 0.263 (PA-weighted 2022-2025). Gate fires at 0.240 (0.263 ≥ 0.240, gap=0.047 > 0.040).
0.85 fix benefits Bregman: floor 0.216→0.224, avg_liability_mult 0.933→1.000.

### Task 6 — Full projection scorecard

Top 10 model vs FP divergences at session close:

| Name | Model Rank | FP Rank | Gap | Root Cause |
|------|-----------|---------|-----|------------|
| Ben Rice | #4 overall | FP #28 | -24 | Sell High signal + young breakout under-proj |
| Gunnar Henderson | SS#4 (ovr ~15) | FP #8 | ~7 | CQS floor props, SB fix improved, ESV still suppressed |
| Trea Turner | SS#5 (ovr ~21) | FP #12 | ~9 | Leadoff RBI penalty (slot-1 mult 0.83) + Z-score near repl |
| Cam Schlittler | SP#1 (ovr ~8) | FP #22 | +14 | Model bullish on ERA 1.96/FIP 1.41 elite; FP cautious on IP |
| Elly De La Cruz | CF#3 (ovr ~12) | FP #6 | +6 | SB improved (48→correct), still minor gap |
| Corey Seager | SS#1 (ovr ~11) | FP #22 | ~11 | Model Buy Low; FP sees current .306 wOBA |
| José Ramírez | 3B#1 (ovr ~4) | FP #4 | ~0 | Aligned (Buy Low holding; CQS floor props) |
| Brandon Lowe | 2B (mid-tier) | FP ~#80 | — | FP sees PA risk; model projects full workload |

Key finding: CQS floor interaction with active buy signals (Ramírez, Stewart, Caminero) remains unresolved — see Tier 1 parking lot.

**37/37 PASS. All invariants PASS:**
- Sanchez: C#25, L1=16.4 ✓ (21+)
- Yordan: #2 overall, L1=97.4 ✓
- Raleigh: C#2 ✓
- Baldwin: C#4 ✓
- Contreras: C#5 ✓

### Files modified this session:
- score_value.py (0.75→0.85 multiplier change, line ~929)
- thread_handoff.md (this file — Section 8 Henderson/Turner notes, Section 9 score_value.py entry, Section 10 Tier 1 parking lot, Section 13 career lessons, Section 16 GitHub hash, this changelog)

**Commit hash:** 57acd3d

---

---

## SECTION 22: SESSION 25 CHANGELOG

**Session 25 — May 5, 2026**

Continuation from Session 24 close. Session goal: Turner ESV architecture + SS pool diagnostic. No Layer 1 signal model changes.

### Step 2a — Full ESV trace (Turner)

Confirmed ESV=0.179 comes entirely from MI slot (+0.1592). SS slot = -1.075 (negative).
Why SS slot negative: Montgomery (SS replacement #14) projects 26 HR/85 RBI. Turner projects 17 HR/63 RBI. HR gap (-9 units, -1.616 z) + RBI gap (-22.5, -1.502 z) = -3.118 negative vs +2.043 positive from R/SB/OBP = -1.075 net.

### Step 2b — SS pool analysis

14-team league, 18 SS roster slots. Turner ranks 13th by pre_score → Montgomery (#14) is replacement.
Montgomery: 26 HR/85 RBI/0.189 AVG/0.276 OBP/5.3 SB. Career_pa=347 (rookie) — sets high replacement bar in counting stats despite L1=2.7 (avg_liability_mult=0.58 reduces his L1, not his replacement stats).

### Step 2c — PHI slot-1 RBI_mult derivation

PHI slots 7/8/9 OBP: 0.221 / 0.291 / 0.302. Weighted: 0.40×0.302 + 0.35×0.291 + 0.25×0.221 = 0.278.
rbi_raw = 1.0 + 1.2 × (0.278 / 0.324 − 1.0) = 0.830. PHI is 4th worst in MLB for slot-1 RBI context.
League median slot-1 RBI_mult = 0.952. PHI (-12%) is a real structural penalty, not noise.
**Validation:** The 0.221 OBP in PHI slot 7 is the primary driver — empirically correct for 2026 PHI lineup.

### Step 2d — SS peer comparison (post-OBP-anchor fix)

| Player | OBP | HR | RBI | SB | ESV | L1 |
|--------|-----|----|----|-----|-----|-----|
| Correa | .358 | 22 | 102 | 1 | 4.00 | 30 |
| Seager | .341 | 26 | 89 | 3 | 3.83 | 45 |
| Bogaerts | .330 | 18 | 80 | 13 | 2.00 | 15 |
| Turner | .313 | 17 | 63 | 20 | 0.73 | 20 |
| Montgomery | .274 | 26 | 85 | 5 | 0.55 | 2.7 |

Turner's .313 OBP (post-fix) is 45pp below Correa and 28pp below Bogaerts. In OBP-scoring leagues, each .010 OBP gap ≈ 0.5 Z-score units. That's the structural gap.

### Step 3 — Fix E: OBP anchor consistency (IMPLEMENTED)

**Root cause identified:** OBP_proj used raw xba_col; AVG_proj used career-anchored avg_proj. Same underlying xBA input, two different output values. Turner: xBA=0.218 raw vs avg_proj=0.247 (career anchor). OBP_proj should use same anchored value.

**Fix (score_value.py):**
- Removed standalone OBP_proj line (was line 906)
- Moved OBP_proj calculation to AFTER avg_proj career anchor block
- `out["OBP_proj"] = (avg_proj + bb_col * (1.0 - avg_proj) + 0.005).clip(0.200, 0.600)`
- Both OBP and AVG now use the same career-anchored xBA assumption

**Before/after (5 players):**
| Player | OBP before | OBP after | ESV before | ESV after | L1 change |
|--------|-----------|-----------|-----------|-----------|-----------|
| Trea Turner (SS) | 0.286 | 0.313 | 0.179 | 0.733 | 20.0 → 20.0 (floor) |
| Jazz Chisholm (2B) | 0.265 | 0.305 | 2.315 | 3.137 | 15.0 → 18.4 |
| Gunnar Henderson (SS) | ~0.284 | 0.294 | 2.211 | 2.421 | 20.0 → 20.0 (floor) |
| Bo Bichette (SS) | 0.318 | 0.316 | 0.0 | 0.0 | 40.0 → 40.0 |
| Colson Montgomery (SS) | 0.276 | 0.274 | 0.728 | 0.552 | 3.6 → 2.7 |

**Sanchez guard confirmed:** career_ba=0.214 < 0.240 → gate fails → OBP unchanged → rank C#24 ✓

**Fix D verdict:** Turner IS near SS replacement level in 14-team OBP league. OBP anchor fix improved his model standing substantially (ESV +309%) but CQS floor (20.0) still propping. Structural conclusion stands.

### 37/37 PASS. All invariants PASS.

Sanchez: C#24, L1=15.1 ✓ | Yordan: overall #3 ✓ | Raleigh: C#2 ✓ | Baldwin: C#3 ✓ | Contreras: C#6 ✓

### Files modified this session:
- score_value.py (OBP_proj now uses career-anchored avg_proj — Session 25)
- data/player_values.json (regenerated — OBP/ESV/L1 updated for ~50 hitters)
- thread_handoff.md (this file — Sections 8, 9, 10, 13, 14, 16, this changelog)

**Commit hash:** fbc249a

---

*End of thread_handoff.md — Sections 1-25 complete.*
*Overwrite completely at end of every session. Single source of truth.*
*Save to: C:\Users\dusti\fantasy-baseball\thread_handoff.md*
