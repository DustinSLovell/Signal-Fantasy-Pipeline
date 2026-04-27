<<<<<<< HEAD
# Fantasy Baseball Statcast Pipeline

A Python pipeline that pulls pitch-level Statcast data from Baseball Savant and pitching stats from FanGraphs, aggregates them into per-player metrics, and scores each player for fantasy luck — identifying who to buy low and who to sell high.

---

## Project Structure

```
fantasy-baseball/
├── run_pipeline.py              # Run the full pipeline (or hitters/pitchers only)
├── run_pipeline.bat             # Windows batch wrapper: logs output, rotates logs, opens dashboard
├── launch_dashboard.bat         # Start HTTP server (port 8000) and open dashboard in browser
│
├── fetch_stats.py               # Hitter Step 1: Pull raw Statcast data
├── process_stats.py             # Hitter Step 2: Aggregate into per-batter metrics
├── score_luck.py                # Hitter Step 3: Score each batter and print buy/sell tables
│
├── fetch_pitcher_stats.py       # Pitcher Step 1: Pull pitcher Statcast + FanGraphs data
├── process_pitcher_stats.py     # Pitcher Step 2: Aggregate per-pitcher metrics and ERA gaps
├── score_pitcher_luck.py        # Pitcher Step 3: Score each pitcher and print buy/sell tables
│
├── score_value.py               # Trade value engine: 3-layer framework + CQS floors
├── compute_career_quality.py    # Career Quality Score: 3yr xwOBA + HHR + PA reliability
│
├── generate_narratives.py       # AI narrative generation via Anthropic API
│
├── backtest_april.py            # Backtest Step 1: Pull + cache historical Statcast, compute luck scores
├── backtest_analyze.py          # Backtest Step 2: Correlation analysis, verdict accuracy, weight grid search
│
├── dashboard.html               # Standalone browser dashboard; reads both luck score CSVs
│
├── hitters_statcast.csv         # Output of fetch_stats.py          (pitch-level, one row per pitch)
├── hitter_luck_input.csv        # Output of process_stats.py        (one row per batter)
├── luck_scores.csv              # Output of score_luck.py           (one row per batter, with scores)
│
├── pitchers_statcast.csv        # Output of fetch_pitcher_stats.py  (pitch-level, one row per pitch)
├── pitchers_fangraphs.csv       # Output of fetch_pitcher_stats.py  (one row per pitcher, FanGraphs)
├── pitcher_luck_input.csv       # Output of process_pitcher_stats.py (one row per pitcher, with gaps)
├── pitcher_luck_scores.csv      # Output of score_pitcher_luck.py   (one row per pitcher, with scores)
│
├── backtest_raw.csv             # Output of backtest_april.py  (551 player-seasons, April + May-July merged)
├── backtest_results.csv         # Output of backtest_analyze.py (with prediction_correct, signal_strength)
├── backtest_report.md           # Output of backtest_analyze.py (full narrative with all tables)
│
├── backtest_cache/              # Cached historical Statcast CSVs (2023-2024); re-used on subsequent runs
│   ├── statcast_2023_april.csv
│   ├── statcast_2023_mayjuly.csv
│   ├── statcast_2024_april.csv
│   └── statcast_2024_mayjuly.csv
│
└── logs/
    └── pipeline_YYYY-MM-DD.log  # Daily pipeline log; files older than 30 days are auto-deleted
```

---

## Career Quality Score (CQS)

`compute_career_quality.py` anchors proven players against early-season noise by computing a 0–100 Career Quality Score from 3-year Statcast percentiles and career PA reliability. Trade value floors are applied in `score_value.py` so elite veterans cannot fall below a minimum value regardless of small-sample April results.

**CQS formula:**

```
CQS = (3yr xwOBA percentile × 0.40)
    + (3yr hard hit% percentile × 0.30)
    + (career PA reliability weight × 0.30)
```

Career PA reliability uses a knot-interpolated ramp: 0 PA → 0.40, 500 PA → 0.40, 1,000 PA → 0.65, 2,000 PA → 0.85, 3,000+ PA → 1.00.

**Percentile universe split:** Players with 2,000+ career PA are ranked against each other; players below 2,000 PA are ranked against their own pool. This prevents low-PA players from dominating the percentile rankings and inflating their CQS tier relative to proven veterans.

**Tier floors with minimum PA gates:**

| Tier | CQS Range | Floor (units) | Min Career PA |
|---|---|---|---|
| Superstar | 80–100 | 60 | 3,000 |
| Established Star | 60–79 | 40 | 2,000 |
| Solid Contributor | 40–59 | 20 | 1,000 |
| Developing | < 40 | 0 | — |

Both floor eligibility conditions must be met: a player with CQS 85 but only 800 career PA receives no floor protection. This prevents overprotecting young players with promising metrics but unproven durability.

**Conversion rate modifier:**

`conversion_rate = 3yr actual wOBA / 3yr xwOBA` — measures whether a player's results match their Statcast quality. Applied only to players with 2,000+ career PA.

| Profile | Condition | Modifier | Example |
|---|---|---|---|
| Underperformer | Conv rate < 0.90 for 2+ consecutive years | CQS × 0.85 | Persistent outs on hard contact |
| Overperformer | 3yr average conv rate > 1.10 | CQS × 1.10 | Paredes (avg 1.102), Altuve (avg 1.122) |
| Standard | Neither condition | CQS × 1.00 | No adjustment |

Underperformers have structural reasons why results lag hard contact metrics — chase rates, speed, or launch angle distribution. Overperformers extract more value than Statcast predicts through plate discipline, speed, or favorable batted ball distributions. The modifier adjusts the floor accordingly: overperformers get a higher floor, underperformers get a reduced one.

**Output fields added to `data/player_values.json`:**

| Field | Description |
|---|---|
| `cqs` | Career Quality Score (0–100) |
| `cqs_tier` | Tier label: Superstar / Established Star / Solid Contributor / Developing |
| `cqs_floor` | Floor value in trade value units (0 if ineligible) |
| `cqs_floor_applied` | Boolean — true if L1/L2 were raised to meet the floor |
| `conversion_flag` | `"overperformer"`, `"underperformer"`, or null |
| `conversion_note` | Human-readable rate description (e.g. "avg conv 1.122, 3yr avg") |

```bash
python compute_career_quality.py          # dry run — validate output
python compute_career_quality.py --write  # write data/career_quality.json
```

**Availability modifier (2026-04-20):**

Floor protection is further adjusted by each player's availability history, using per-year PA from Statcast as a games-played proxy (full season ≈ 664 PA). Recovery override: if the most recent season ≥ 90% availability, the player is treated as fully available. Otherwise, a 3-year average rate is used.

| Availability Rate | Modifier |
|---|---|
| ≥ 85% | Full floor |
| 70–84% | Floor × 0.75 |
| 55–69% | Floor × 0.50 |
| < 55% | Floor removed — "Injury risk" |

**Consecutive seasons expansion (2026-04-20):**

Players with career_pa ≥ 800 and 2+ seasons of 400+ PA qualify for the Solid Contributor floor (20 units) even if total PA falls below 1,000. This captures established starters (e.g., Pasquantino) who missed time but have held down a starting role in back-to-back seasons.

**Output fields added to `data/player_values.json`:**

| Field | Description |
|---|---|
| `cqs` | Career Quality Score (0–100) |
| `cqs_tier` | Tier label: Superstar / Established Star / Solid Contributor / Developing |
| `cqs_floor` | Floor value in trade value units (0 if ineligible) |
| `cqs_floor_applied` | Boolean — true if L1/L2 were raised to meet the floor |
| `conversion_flag` | `"overperformer"`, `"underperformer"`, or null |
| `conversion_note` | Human-readable rate description (e.g. "avg conv 1.122, 3yr avg") |
| `availability_flag` | Reduction reason string, or null if full floor |

---

## 2026-04-20 Fixes

Six targeted fixes applied during sanity check review:

1. **Overperformer explanation gating** (`dashboard.html`): The overperformer template was firing on sell candidates and producing buy language. Gated the template on verdict direction — sell candidates now get "ideal time to sell" language; buy/neutral candidates get the "don't be fooled" text.

2. **Phase-aware starter classification** (`score_value.py`): The fixed 0.95 IP/day threshold misclassified all April starters as relievers. Replaced with phase-aware thresholds: April = 0.75, May = 0.85, June+ = 0.95. Added GS-based override (3/5/8 GS for April/May/June+) when FanGraphs data is available.

3. **CQS-aware buy explanation** (`dashboard.html`): Buy-low players with a CQS floor applied now receive career-track-record explanation language instead of soft-contact dismissal. Passes `pvEntry` (player value record) into `generateExplanation()` to enable the lookup.

4. **Altuve position override** (`score_value.py`): MLB API returns LF for Altuve; he was being valued against the LF pool. Added MLBAM ID 514888 to `MANUAL_POSITION_OVERRIDES` so he is valued against the 2B pool.

5. **Availability modifier** (`compute_career_quality.py`): New adjustment reduces or removes CQS floors for players with a history of missed time. See availability modifier table above. Consecutive seasons expansion also added (see above).

6. **Zero trade value tooltip differentiation** (`dashboard.html`): When a buy-low hitter has maxTv === 0 in both leagues, shows "buy for regression, not for star upside" instead of the generic low-value text. Preserves the existing < 20 branch for players with modest but nonzero value.

---

## Requirements

- Python 3.9+
- [pybaseball](https://github.com/jldbc/pybaseball)
- pandas
- python-dotenv (for AI narrative generation)
- anthropic (for AI narrative generation)

```bash
pip install pybaseball pandas python-dotenv anthropic
```

---

## Running the Pipeline

`run_pipeline.py` runs scripts in sequence, streams output from each step, reports how long each step took, and stops with a clear error message if any step fails.

```bash
python run_pipeline.py              # Run all 6 steps (hitters + pitchers)
python run_pipeline.py --hitters    # Run hitter pipeline only (steps 1–3)
python run_pipeline.py --pitchers   # Run pitcher pipeline only (steps 4–6)
```

Or run individual scripts directly:

```bash
# Hitter pipeline
python fetch_stats.py
python process_stats.py
python score_luck.py

# Pitcher pipeline
python fetch_pitcher_stats.py
python process_pitcher_stats.py
python score_pitcher_luck.py
```

To refresh data mid-season, re-run the fetch scripts followed by the processing scripts. pybaseball's cache stores results by date chunk, so only new dates are downloaded on subsequent runs. Because both pipelines call `statcast()` over the same date range, the second fetch reuses the cache and completes in seconds.

---

## Project Timeline

| Milestone | Date |
|---|---|
| Project start | April 12–14, 2026 |
| First article published | April 22, 2026 |
| Days from zero to production | ~10 days |
| Reddit launch | April 23, 2026 |
| Reddit results | 17K views, #2 post r/fantasybaseball |

---

## Additional Pipeline Scripts

| Script | Description |
|---|---|
| `fetch_ownership.py` | Pulls live ESPN ownership for 3,795 players daily |
| `fetch_prior_teams.py` | Pulls 2025 team assignments for park change detection (998 players in prior_teams_2025.json) |
| `stat_projections.py` | Rest-of-season projections (794 players, 19 columns); 37/37 formula validation tests pass |
| `generate_projections.py` | Runs the projection pipeline |
| `trade_analyzer.py` | Trade verdicts using luck scores + projected stats |
| `validate_formulas.py` | 38-test formula validation suite |
| `score_value.py` | Player trade values and rankings (794 players) |
| `export_signal_board.py` | Excel signal board with ownership data, sorted by owned_pct descending per bucket |

---

## Model Status

**Hitter model:** Option 3 thresholds, xwOBA gate, platoon modifier
- 88.1% overall, 94.1% sell high, 94.3% buy low

**Pitcher model:** v2.0 split architecture
- 91.1% overall, 94.6% sell high, 86.5% buy low

Both models use career baselines for 476 hitters / 287 pitchers, age tier logic, and park change detection.

---

## Data Files

| File | Description |
|---|---|
| `data/projections_2026.csv` | 794 players (414H + 380P) rest-of-season projections |
| `data/player_ownership_2026.csv` | 3,795 players, live ESPN ownership |
| `data/prior_teams_2025.json` | 998 players, 2025 team assignments for park change detection |
| `data/player_values.json` | 794 players, trade values rebuilt by score_value.py |
| `career_lessons_database.html` | 88 career transition concepts, fully searchable |

---

## Validation

```bash
python -X utf8 validate_formulas.py   # 37/37 PASS
python score_value.py --write         # 6/6 invariants PASS
```

Invariant anchors: Yordan top 20 overall, Raleigh top 3 catchers, Baldwin top 5 catchers, Contreras top 8 catchers, Sanchez rank 21+ catchers (the Sanchez Test).

---

## Known Limitations

- Pitcher ownership data missing from ESPN fetch (signal board falls back to luck sort)
- 106 pitchers missing FIP/FIP- due to FanGraphs block
- `fp_rank` reflects preseason rankings, not in-season
- Trade analyzer Phase B (league import) is local-only
- Cal Raleigh natural value is 4.6 without CQS floor — monitor as 2026 stats accumulate

---

## Hitter Pipeline

### `fetch_stats.py`

Pulls pitch-level Statcast data for all batters from the current season via pybaseball, which scrapes Baseball Savant. Saves the result to `hitters_statcast.csv`.

**What it does:**
- Queries `statcast()` for the date range from Opening Day through yesterday
- Keeps batter-relevant columns: identifiers, pitch metrics, batted-ball metrics (exit velocity, launch angle, barrels), outcome estimators (xBA, xwOBA), and game context
- Sorts chronologically by game, at-bat, and pitch number
- Enables pybaseball's local disk cache so repeat runs only fetch new dates

**Output — `hitters_statcast.csv`** (one row per pitch):

| Column group | Key columns |
|---|---|
| Identifiers | `game_date`, `game_pk`, `at_bat_number`, `pitch_number`, `batter`, `stand` |
| Pitch metrics | `pitch_type`, `release_speed`, `release_spin_rate`, `effective_speed`, `plate_x`, `plate_z` |
| Batted-ball | `launch_speed`, `launch_angle`, `launch_speed_angle`, `bb_type`, `hit_distance_sc` |
| Outcome estimators | `estimated_ba_using_speedangle`, `estimated_woba_using_speedangle`, `woba_value`, `babip_value` |
| Game context | `balls`, `strikes`, `outs_when_up`, `on_1b/2b/3b`, `inning`, `bat_score`, `fld_score` |

**Configuration** (top of script):

```python
SEASON_START = date(2026, 3, 27)                 # Opening Day -- update for future seasons
SEASON_END   = date.today() - timedelta(days=1)  # yesterday, auto-updating
```

---

### `process_stats.py`

Reads `hitters_statcast.csv` and aggregates the pitch-level data into one row per batter. Saves the result to `hitter_luck_input.csv`.

**What it does:**
- Computes ten per-batter stats (see below)
- Drops batters with fewer than 10 PA to remove noise from fringe samples
- Looks up player names by MLBAM ID via `playerid_reverse_lookup()` and joins them onto each row
- Rounds all rate stats to three decimal places and sorts by PA descending

**Output — `hitter_luck_input.csv`** (one row per batter, minimum 10 PA):

| Column | Definition |
|---|---|
| `name` | Player name resolved from MLBAM ID |
| `PA` | Plate appearances with a recorded, non-truncated outcome event |
| `BABIP` | Hits on balls in play (singles/doubles/triples) / total balls in play; HR, K, BB, HBP, and sac bunts excluded from both numerator and denominator |
| `hard_hit_rate` | Batted ball events with exit velocity >= 95 mph / all BBE (rows where `launch_speed` is not null) |
| `barrel_rate` | Barrels (`launch_speed_angle == 6`) / all BBE |
| `z_contact_rate` | In-zone swings resulting in contact / all in-zone swings; in-zone = Statcast zones 1-9; contact = `hit_into_play`, `foul`, `foul_tip`, `foul_bunt`, `bunt_foul_tip`; misses = `swinging_strike`, `swinging_strike_blocked`, `missed_bunt` |
| `hr_fb_rate` | Home runs / fly balls; in Statcast, HR have `bb_type == 'fly_ball'` so the denominator already includes HR |
| `pull_rate` | Pulled batted balls / all fair batted ball events. Uses spray-chart coordinates (`hc_x`, `hc_y`) to compute hit angle from home plate; a ball is "pulled" when the angle exceeds 20° toward the batter's pull side (RHB: toward left field, LHB: toward right field). Threshold calibrated to produce a league-average pull rate of ~39%, consistent with Baseball Savant's published Pull% leaderboard. |
| `o_swing_rate` | Swings at pitches outside the strike zone / all pitches outside the strike zone. Out-of-zone = Statcast zones 11–14. League average ~30%; values above 35% represent the top quartile of chasers. |
| `wOBA` | Actual weighted on-base average: `sum(woba_value)` / PA. `woba_value` is Statcast's linear-weight run value for each PA outcome. Used by `score_luck.py` to compute the xwOBA gap. |
| `xwOBA` | Expected wOBA based on contact quality. For batted balls (excluding HR): uses `estimated_woba_using_speedangle`, the Statcast model of expected run value from exit velocity and launch angle. For HR, strikeouts, walks, and HBP: uses actual `woba_value`, since these outcomes are not luck-driven on contact. `xwOBA_gap = xwOBA − wOBA` isolates luck from skill. |

---

### `score_luck.py`

Reads `hitter_luck_input.csv`, calculates a luck score for each batter, assigns a verdict, and saves the full results to `luck_scores.csv`. Also prints ranked buy-low and sell-high tables to the terminal.

**Model version:** v4 — adds minimum PA gates and hard hit% quality gates to the v3 contextual modifiers. Base weights backtested against 551 player-seasons (2023–2024 April vs May-July). See `backtest_report.md` for full methodology.

**Luck score formula:**

```
# Component 1: BABIP with directional contextual modifiers
babip_comp = (BABIP - 0.300) * -3.000
             × chase_modifier(o_swing_rate, BABIP)
             × zcon_modifier(z_contact_rate, BABIP)

# Component 2: HR/FB with pull-rate modifier
hrfb_comp  = (hr_fb_rate - 0.145) * -0.150
             × pull_modifier(pull_rate)

# Components 3 & 4: unchanged from v2
zcon_comp  = (z_contact_rate - 0.880) * -0.030
xwoba_comp = xwOBA_gap * 1.000

xwOBA_gap  = xwOBA - wOBA
luck_score = (babip_comp + hrfb_comp + zcon_comp + xwoba_comp)
             × confidence_scale(PA)
```

**Sign convention:** positive score = unlucky (buy low), negative score = lucky (sell high).

**Component breakdown:**

| Metric | League avg | Weight | Predictive r (vs Δ wOBA) | Logic |
|---|---|---|---|---|
| BABIP | .300 | −3.000 | −0.502 | Primary luck driver. Below-average BABIP with good contact quality = unlucky. Weight reduced from v1's −5.0: backtesting showed BABIP already dominated the signal and was over-leveraged. Modified in v3 by chase and z-contact contextual multipliers (see below). |
| HR/FB rate | 14.5% | −0.150 | −0.333 | Elevated HR/FB regresses strongly toward the mean. Weight increased 3.75× from v1's −0.04: backtesting showed this was the most underweighted component. Modified in v3 by pull-rate contextual multiplier (see below). |
| Z-contact rate | 88% | −0.030 | −0.080 | High in-zone contact without results suggests unlucky sequencing. Weight tripled from v1's −0.01. Also used as a contextual modifier on the BABIP component in v3. Low Z-contact (< ~80%) is a genuine skill concern, not luck — interpret with caution. |
| xwOBA gap | — | +1.000 | +0.402 | `xwOBA − wOBA`: positive = player's contact quality deserved better outcomes than they got. New in v2; second-strongest individual predictor in backtesting. Requires `wOBA` and `xwOBA` columns from `process_stats.py`. |

**v3 contextual modifiers:**

All three modifiers multiply their respective component after the base weight is applied. The z-contact and chase modifiers are **directional**: the effect reverses based on which side of .300 BABIP falls on, so the modifier always pushes the signal in the correct direction.

| Modifier | Applies to | Logic |
|---|---|---|
| **Pull rate** | HR/FB component | Pull hitters sustain higher HR/FB rates. `pull_rate > 0.45` → ×0.65; `> 0.40` → ×0.80. League mean ~39% (20° spray-angle threshold). |
| **Chase rate** (O-Swing%) | BABIP component | *Sell side (BABIP > .300):* High chase rate makes elevated BABIP less sustainable → amplify sell. `o_swing > 0.40` → ×1.25; `> 0.35` → ×1.15. *Buy side (BABIP ≤ .300):* High chase means low BABIP is partly skill-driven → dampen buy. `o_swing > 0.40` → ×0.75; `> 0.35` → ×0.85. League mean ~30%. |
| **Z-contact rate** | BABIP component | *Sell side (BABIP > .300):* High Z-contact makes elevated BABIP more sustainable → reduce sell. `z_contact > 0.92` → ×0.75; `> 0.88` → ×0.85. *Buy side (BABIP ≤ .300):* High Z-contact makes low BABIP more anomalous → amplify buy. `z_contact > 0.92` → ×1.25; `> 0.88` → ×1.15. League mean ~88%. |

The mirror-factor relationship (`0.75 ↔ 1.25`, `0.85 ↔ 1.15`) keeps the model symmetric around the .300 BABIP baseline.

**v4 modifier refinements:**

Two refinements tighten all buy-side contextual amplifiers to require minimum sample size and contact quality evidence:

**Minimum PA threshold (75 PA):** The buy-side effects of the z-contact amplifier, chase dampener, and pull rate modifier all require at least 75 PA. Below 75 PA these three modifiers default to ×1.00 on the buy side. Sell-side modifiers are unchanged. Rationale: a contextual amplifier that correctly strengthens a 300-PA signal creates noise on a 50-PA sample. Z-contact at 92% on 45 PA is not the same signal as z-contact at 92% on 300 PA.

**Hard hit% quality gate (z-contact buy-side amplification):** The z-contact buy-side amplifier now requires adequate contact quality to fire at full strength:
- `hard_hit% > 35%`: Full amplification (×1.25 or ×1.15) — high z-contact + hard contact = genuine sustainable BABIP signal
- `hard_hit% 28–35%`: Reduced amplification (×1.10 or ×1.05) — partial signal
- `hard_hit% < 28%`: No amplification (×1.00) — making contact but weakly; not a sustainable BABIP signal

The sell-side z-contact dampening is unchanged — soft contact sell-side players deserve their sell signal regardless.

**Hard hit% quality gate (pull rate modifier):** The pull rate HR/FB modifier now also requires hard contact:
- `hard_hit% > 35%`: Full modifier (×0.65 or ×0.80) — pull hitter with real power
- `hard_hit% 28–35%`: 30% attenuated (×0.755 or ×0.860) — partial modifier
- `hard_hit% < 28%`: No modifier (×1.00) — weak contact pull hitters don't sustainably outperform on HR/FB

**Metrics removed from scoring formula (still shown in CSV and dashboard):**

| Metric | v1 Weight | Why removed |
|---|---|---|
| Hard-hit rate | +0.025 | Predictive r = −0.142 individually. Signal is fully absorbed by the xwOBA gap, which captures the same contact-quality information more precisely. |
| Barrel rate | +0.030 | Predictive r = −0.229 individually. Similarly subsumed by xwOBA gap; removing it from the formula increased model correlation. |

Hard-hit rate and barrel rate remain in `hitter_luck_input.csv` and `luck_scores.csv` and are displayed in the dashboard as informational columns for manual review.

**Confidence multiplier:**

```python
confidence_scale(PA) = min(1.0, max(0.0, (PA - 30) / 70))
```

| PA | Multiplier | Effect |
|---|---|---|
| ≤ 30 | 0.00 | Score zeroed; verdict forced to Neutral |
| 65 | 0.50 | Score at half weight |
| ≥ 100 | 1.00 | Full confidence, no adjustment |

Prevents early-season noise from generating spurious strong buy/sell verdicts before meaningful samples have accumulated. Applied after the raw component sum, before rounding and verdict assignment.

**Correlation improvement from v1 → v2** (on held-out 2023–2024 data; v3 modifiers not yet backtested):

| | v1 | v2 | v3 |
|---|---|---|---|
| Pearson r (luck score vs Δ wOBA) | +0.506 | +0.539 | — (not backtested) |
| Buy-low directional accuracy | 71% | — | — |
| Sell-high directional accuracy | 71% | — | — |

**Verdict thresholds:**

| Score range | Verdict | Meaning |
|---|---|---|
| > 0.12 | **Buy low** | Strong underlying metrics, results lagging — strong buy candidate |
| 0.05 to 0.12 | **Slight buy** | Modest positive regression likely |
| −0.05 to 0.05 | **Neutral** | Results roughly in line with underlying metrics |
| −0.12 to −0.05 | **Slight sell** | Modest negative regression likely |
| < −0.12 | **Sell high** | Results running well ahead of contact quality — sell candidate |

**Terminal output:** prints the top 10 buy-low and top 10 sell-high players filtered to a **minimum 30 PA** for actionable sample sizes. All batters (minimum 10 PA) are still included in the saved CSV.

**Sell-tier system:**

Every "Sell high" or "Slight sell" batter also receives a `tier_sell` column with the sell rationale tier. The tier is shown as a color-coded badge in the dashboard next to the verdict.

| Tier | Condition | Color | Meaning |
|---|---|---|---|
| **Sell and Move On** | Verdict = Sell high; age ≥ 35 → *Decline risk*, or xwOBA gap < −0.020 | Dark red | Regression strongly supported by underlying metrics; move on quickly |
| **Sell High on Perception** | Verdict = Sell high; xwOBA gap ≥ −0.020 | Orange | Results ahead of metrics, but underlying contact not terrible; trade on current narrative |
| **Veteran Regression** | Verdict = Sell high; career PA > 2,000; xwOBA gap > −0.020; luck score in [−0.30, −0.15] | Amber | Proven hitter on a lucky streak; sell into the perception while it lasts |
| **Slight Regression Expected** | Verdict = Slight sell | Yellow | Modest correction likely; monitor before acting |

**Age modifier:**

`career_stats.json` (populated from the MLB Stats API) provides `birth_year` for each hitter. Three adjustments are applied after the confidence multiplier:

- **Rising (+0.02):** Age < 28 and luck_score > 0 — young hitters with buy signals get a small boost. Applied only to buy-signal players to avoid inflating sell signals.
- **Prime:** Age 28–34 — no modifier.
- **Decline risk:** Age ≥ 35 — automatically assigned Tier 1 "Sell and Move On" regardless of xwOBA gap.
- **Age concern flag:** Age 33–34 within a Veteran Regression tier assignment — flagged for awareness without overriding the tier.

---

## Phase B: Consistency Score

`compute_consistency.py` applies a per-player variance multiplier to the Phase A luck score (v5), producing `luck_score_v6`. This prevents the model from amplifying signals on consistently mediocre players or penalizing players for volatility that is legitimately explained by age or park changes.

**Usage:**

```bash
python compute_consistency.py            # validate only (no file writes)
python compute_consistency.py --write    # write consistency columns to luck_scores.csv and pitcher_luck_scores.csv
```

**How it works:**

1. Loads per-year xwOBA from `backtest_cache/expected_stats_{2022-2024}.csv` (minimum 300 PA per season).
2. Computes `variance_std` = standard deviation of the player's pseudo wRC+ (= xwOBA / 0.315 × 100) across qualified seasons.
3. Assigns a variance tier and base multiplier (see table below).
4. Applies a quality gate, age modifier, and park-change discount.
5. Multiplies `luck_score_v5 × consistency_multiplier` to produce `luck_score_v6`.

**Variance tiers:**

| Tier | Std dev | Base multiplier | Notes |
|---|---|---|---|
| Very Consistent | std < 8 | 1.10 | Boost only fires if wRC+ > 120 (elite quality gate) |
| Consistent | std 8–15 | 1.00 | Neutral — no change |
| Inconsistent | std 15–25 | 0.80 | Moderate penalty |
| Volatile | std 25–35 | 0.60 | Strong penalty |
| Extreme | std > 35 | 0.40 | Maximum penalty |
| Insufficient data | < 2 seasons | 1.00 | Neutral — no data to measure |

**Elite quality gate for the boost:**

A consistency boost (base multiplier > 1.00) only applies when the player is in the Very Consistent tier AND has a 3-year mean pseudo wRC+ > 120. This prevents average-consistent players (e.g., Alec Bohm, wRC+ ≈ 108) from receiving artificial signal inflation. Consistency in a player who is consistently average does not make their luck signal more trustworthy — it is the consistency of *elite* performance that amplifies conviction.

Example: Aaron Judge (std=2.4, wRC+=150) receives multiplier=1.10. Alec Bohm (std=1.9, wRC+=108) receives multiplier=1.00.

**Age modifier (applied to penalties only):**

| Age | Penalty modifier |
|---|---|
| < 26 | × 0.40 — young players' volatility is expected; discount the penalty |
| 26–31 | × 1.00 — prime years, full penalty |
| 32–34 | × 1.20 — aging curve, amplify penalty |
| 35+ | × 1.40 — decline risk, maximum amplification |

**Park-change discount:** When a player changed parks between 2022–2024 (activates when `park_change_detected = True`), the penalty is multiplied by 0.60 — year-to-year xwOBA variance partly reflects environment changes, not true inconsistency. **Currently always False** — park change detection requires per-year team data in the expected_stats cache (parking lot).

**Insufficient data behavior (expected, not a gap):**

Approximately 57–60% of active hitters receive a neutral multiplier (1.00) due to insufficient data — fewer than 2 seasons with 300+ PA in the 2022–2024 window. This is the correct answer: rookies and recent callups genuinely do not have enough history to measure consistency. Forcing a score on insufficient data would introduce false precision. The CQS PA gates already handle these players appropriately.

**Columns added to `luck_scores.csv`:**

| Column | Description |
|---|---|
| `variance_std` | Std dev of 3-year pseudo wRC+ (NaN if insufficient data) |
| `variance_tier` | Very Consistent / Consistent / Inconsistent / Volatile / Extreme / Insufficient data |
| `seasons_used` | Number of qualified seasons (300+ PA) in 2022–2024 |
| `wrc_plus_for_gate` | 3-year mean pseudo wRC+ used for the elite quality gate |
| `age_modifier_applied` | Penalty modifier from the age table (1.00 if no penalty) |
| `park_change_detected` | Boolean — always False until park-change tracking activated |
| `consistency_multiplier` | Final multiplier applied to luck_score_v5 |
| `luck_score_v5` | Pre-consistency Phase A luck score (from `score_luck.py`) |
| `luck_score_v6` | Post-consistency luck score (luck_score_v5 × consistency_multiplier) |

**Superstar wRC+ tier in score_luck.py (v5, Phase B addition):**

The quality gate multiplier in `score_luck.py` now includes a Superstar tier:

| wRC+ | Tier | Buy signal multiplier |
|---|---|---|
| ≥ 130 | Superstar | × 1.15 |
| 120–129 | Elite | × 1.10 |
| 100–119 | Above Avg | × 1.00 |
| 95–99 | Average | × 0.80 |
| 85–94 | Below Avg | × 0.60 |
| < 85 | Poor | × 0.40 |

The Superstar tier amplifies buy signals for Judge/Ohtani/Ramírez-level players whose elite track record adds conviction to the luck signal. The Elite tier shifts to 120–129 (unchanged multiplier).

---

## Pitcher Pipeline

### `fetch_pitcher_stats.py`

Pulls two data sources and saves them separately. Statcast reuses the pybaseball cache from the hitter fetch, so there is no duplicate download.

**Output — `pitchers_statcast.csv`** (one row per pitch):

Same Statcast pull as the hitter script, keeping pitcher-focused columns: `pitcher` (MLBAM ID), `p_throws`, pitch metrics, batted-ball metrics, `events`, `description`, `woba_value`, and `estimated_woba_using_speedangle` (null for HR — see xERA note below).

**Output — `pitchers_fangraphs.csv`** (one row per pitcher):

Pulled via `pitching_stats(year, year, qual=0)`. `qual=0` returns all pitchers; the 10-IP minimum is applied in the processing step.

| Column | Source | Definition |
|---|---|---|
| `IDfg` | FanGraphs | FanGraphs pitcher ID (used to join with Statcast MLBAM IDs) |
| `IP` | FanGraphs | Innings pitched in baseball notation (9.2 = 9⅔ innings) |
| `ERA` | FanGraphs | Earned run average |
| `FIP` | FanGraphs | Fielding Independent Pitching |
| `xFIP` | FanGraphs | Expected FIP (normalizes HR/FB to league average) |
| `LOB%` | FanGraphs | Strand rate |
| `SwStr%` | FanGraphs | Swinging-strike rate |
| `HR/FB` | FanGraphs | HR per fly ball |

---

### `process_pitcher_stats.py`

Reads `pitchers_statcast.csv` and `pitchers_fangraphs.csv`, computes per-pitcher metrics, joins both sources, applies the 10-IP minimum filter, and saves to `pitcher_luck_input.csv`.

**Player name resolution:** `build_id_map()` resolves MLBAM IDs to player names and FanGraphs IDs using a two-tier approach:

1. **Primary — Chadwick Bureau** (`playerid_reverse_lookup`): a community-maintained cross-reference database queried via pybaseball. Returns `name_first`, `name_last`, and `key_fangraphs` for most established players.
2. **Fallback — MLB Stats API**: any MLBAM IDs not found in the Chadwick Bureau are queried individually against `https://statsapi.mlb.com/api/v1/people/{id}`, which always has the correct full name for any active player. In the 2026 dataset this fallback resolved 20 pitchers missing from the Chadwick Bureau, including Andrew Painter (691725) and Ryan Weiss (680802), both recently called-up players not yet indexed in the community database.

Without the fallback, these pitchers appear with a blank name and show as `NaN` rows in the dashboard. The Chadwick Bureau lags for new callups; the MLB Stats API fallback ensures complete name coverage regardless of when a player debuted.

**Join path:** `key_fangraphs` from the Chadwick Bureau lookup maps directly to `IDfg` in the FanGraphs data.

**FanGraphs fallback:** FanGraphs' leaderboard endpoint (`leaders-legacy.aspx`) is protected by Cloudflare and may return HTTP 403. When it does, `fetch_pitcher_stats.py` saves an empty stub and `process_pitcher_stats.py` fills the affected columns (`ERA`, `FIP`, `IP`, `lob_pct`) from Statcast-native calculations:

| Fallback | Method |
|---|---|
| `IP` | Out events mapped to out counts (DP = 2, TP = 3) ÷ 3 |
| `ERA` | RA/9 from `bat_score` delta tracking per pitcher per half-inning |
| `FIP` | `(13×HR + 3×(BB+HBP) − 2×K) / IP + cFIP`; cFIP self-calibrates from league totals in the same dataset |
| `lob_pct` | `(H + BB + HBP − RA) / (H + BB + HBP − 1.4×HR)` |

**Output — `pitcher_luck_input.csv`** (one row per pitcher, minimum 10 IP):

| Column | Source | Definition |
|---|---|---|
| `pitcher` | Statcast | MLBAM pitcher ID |
| `name` | Lookup | Player name resolved from MLBAM ID |
| `Team` | FanGraphs | Current team |
| `IP` | FanGraphs / Statcast fallback | Innings pitched |
| `ERA` | FanGraphs / Statcast fallback | Earned run average (fallback is RA/9) |
| `FIP` | FanGraphs / Statcast fallback | Fielding Independent Pitching |
| `xFIP` | FanGraphs | Expected FIP (no fallback; omitted when FanGraphs unavailable) |
| `xERA` | Statcast | Approximated from xwOBA allowed (see formula below) |
| `ERA_minus_FIP` | Derived | Positive = ERA running above peripherals (likely unlucky); negative = ERA running below (likely lucky) |
| `ERA_minus_xERA` | Derived | Positive = ERA running above contact quality (likely unlucky); negative = ERA running below (likely lucky) |
| `BABIP_allowed` | Statcast | Hits on BIP / total BIP; HR, K, BB, HBP excluded |
| `lob_pct` | FanGraphs / Statcast fallback | Strand rate (LOB%) |
| `hr_fb_rate` | Statcast | Home runs / fly balls |
| `hard_hit_rate_allowed` | Statcast | BBE with exit velo >= 95 mph / all BBE |
| `barrel_rate_allowed` | Statcast | Barrels / all BBE |
| `swstr_rate` | Statcast | Swinging strikes / total pitches |
| `k_pct` | FanGraphs | Strikeout rate |
| `bb_pct` | FanGraphs | Walk rate |

**xERA formula:**

For each plate-appearance-ending event, `estimated_woba_using_speedangle` (xwOBA on contact) is used where non-null. For home runs — where Statcast leaves xwOBA null — and true-outcome events (K, BB, HBP), the actual `woba_value` is used instead, since these outcomes are not driven by pitch-quality luck. The mean xwOBA per pitcher is then scaled to an ERA-like value:

```
xERA ≈ (mean_xwOBA_allowed − 0.320) × 33.0 + 4.00

Baselines: lgxwOBA = 0.320, lgERA = 4.00, scale = 33.0
```

This is a reasonable approximation of the official Baseball Savant xERA, not an exact replication.

---

### `score_pitcher_luck.py`

Reads `pitcher_luck_input.csv` and `pitchers_statcast.csv`, calculates a composite luck score for each pitcher, and saves results to `pitcher_luck_scores.csv`. Also prints ranked buy-low and sell-high tables to the terminal.

**Model version:** v3 — adds a buy qualification gate over v2. The scoring formula is unchanged; v3 adds a post-scoring filter that prevents buy signals from surfacing pitchers who are unlucky but not worth owning when they normalize.

**Luck score formula:**

```
# Primary luck signals
luck_score = (BABIP_allowed        - 0.300) *  5.00   # high BABIP allowed = unlucky
           + (lob_pct              - 0.724) * -3.00   # low strand rate = unlucky
           + ERA_minus_FIP                  *  0.15   # positive gap = ERA inflated = unlucky
           + ERA_minus_xERA                *  0.10   # positive gap = ERA above contact quality = unlucky

# HR/FB rate luck component (only fires when hr_fb_rate > 0.14)
#   base = (hr_fb_rate − 0.12) × 2.0
#   Modifier: hard_hit > 0.38 → ×0.65  (hard contact partly explains HR/FB)
#             hard_hit < 0.28 → ×1.25  (soft contact + high HR/FB = strong regression candidate)
           + hrfb_component(hr_fb_rate, hard_hit_rate_allowed)

# xwOBA gap: actual wOBA allowed minus xwOBA allowed (from Statcast, per PA)
# Positive = pitcher giving up more than contact quality warrants = unlucky
           + (woba_allowed − xwoba_allowed) * 1.50

# Quality validators (sharpen the signal; do not drive it)
           + (hard_hit_rate_allowed - 0.360) * -1.50  # high hard-hit reduces buy confidence
           + (barrel_rate_allowed   - 0.080) * -1.50  # high barrel rate reduces buy confidence
           + (swstr_rate            - 0.110) *  2.00  # high SwStr% supports buy signal
```

ERA gap weights (0.15 and 0.10) are intentionally small relative to the BABIP/LOB% weights: ERA gaps are in run-unit space (~0–5 run range) while BABIP and LOB% are rate stats (0–1 range). At these weights, a 1-run ERA-FIP gap contributes roughly the same as a 3-point BABIP deviation.

**HR/FB rate logic:** Elevated HR/FB rates mean-revert strongly toward the league average (~12%). When a pitcher's rate exceeds 14%, the model adds a positive luck score (buy signal) scaled to the gap above 12%. The contextual modifier accounts for the fact that hard-contact pitchers legitimately allow more HRs per fly ball. The component does not fire for below-average HR/FB — there is no sell-side signal from this variable.

**xwOBA gap logic:** For each plate-appearance-ending event, `estimated_woba_using_speedangle` is used where available (non-HR batted balls), falling back to `woba_value` for home runs and true-outcome events (K, BB, HBP). This mirrors the `calc_xera()` construction in `process_pitcher_stats.py`. The gap (actual − expected) captures luck that the ERA gaps may miss when strand rate distorts the ERA picture.

**Confidence multiplier — date-aware (v2):**

The multiplier now adjusts its floor and zero-threshold based on how far into the season we are, preventing early-April pitchers from being muted to near-zero by a tiny raw multiplier.

```python
# Phase determined from today's date vs SEASON_START
April  (days  1-30): IP < 15 → 0.0;  IP >= 15 → max(0.25, (IP − 15) / 40)
May    (days 31-60): IP < 18 → 0.0;  IP >= 18 → max(0.15, (IP − 18) / 40)
June+  (days 61+):   max(0.0, (IP − 20) / 40)   ← original formula, no floor
```

| Phase | Zero threshold | Floor (qualifying IP) | Full confidence |
|---|---|---|---|
| April | < 15 IP | 0.25 at 15 IP | ≥ 55 IP |
| May | < 18 IP | 0.15 at 18 IP | ≥ 58 IP |
| June+ | < 20 IP | none (0.0) | ≥ 60 IP |

Example: a 22-IP pitcher in April gets a 0.25 multiplier instead of 0.05 under the old formula — a 5× amplification that allows real signals to surface before mid-May.

A `conf_phase` column is written to `pitcher_luck_scores.csv` and displayed in the terminal so you can verify which phase each pitcher was scored under.

**Verdict thresholds:**

| Score range | Verdict | Meaning |
|---|---|---|
| > 0.15 | **Buy low** | ERA running above true talent; underlying metrics support regression |
| 0.07 to 0.15 | **Slight buy** | Modest positive regression likely |
| −0.07 to 0.07 | **Neutral** | ERA roughly in line with peripherals |
| −0.15 to −0.07 | **Slight sell** | Modest negative regression likely |
| < −0.15 | **Sell high** | ERA running well below true talent; results likely to worsen |

Note: these thresholds were calibrated for the v1 model where scores rarely exceeded ±0.20. The v2/v3 model regularly produces scores in the ±0.40–0.65 range in April due to the confidence floor and new components. Recalibration is planned for Session 8 after a full season of data.

**Buy qualification gate (v3):**

A buy signal is only surfaced if the pitcher is both unlucky AND worth owning when their ERA normalizes. The gate checks four conditions after scoring:

| Gate | Threshold | Rationale |
|---|---|---|
| FIP | ≤ 4.50 | Minimum command/stuff quality |
| xERA | ≤ 4.75 | Statcast quality floor on contact allowed |
| SwStr% | ≥ 8.0% | Generating meaningful whiffs |
| Career IP | ≥ 100 | Not a complete unknown |

Pitchers failing any gate are overridden to Neutral with `buy_qualified = False` in the output CSV.

**Gate carve-outs:**

Two archetype-specific exceptions prevent the gate from being too strict:

| Carve-out | Condition | Waives |
|---|---|---|
| Elite FIP | FIP ≤ 3.50 | xERA gate — elite K/BB profile overrides Statcast noise |
| Ground ball | GB% > 52% | SwStr% gate — low whiffs are expected and sustainable for extreme GB pitchers |

GB% is computed from `pitchers_statcast.csv` (ground_ball BIP / total BIP). Pitchers without GB% data default to no carve-out.

Example: Luis Castillo (FIP 3.23, xERA 5.58) qualifies via the FIP carve-out despite failing the raw xERA gate. Dustin May (FIP 3.85, SwStr% 5.6%, GB% 41.3%) does not qualify — his 2026 GB% is below the threshold and his FIP is not elite enough for the FIP carve-out.

**Terminal output:** prints the top 10 buy-low and top 10 sell-high players filtered to a **minimum 15 IP**. All pitchers are still included in the saved CSV.

**Sell-tier system (same logic as hitters, pitcher thresholds):**

| Tier | Condition | Color | Meaning |
|---|---|---|---|
| **Sell and Move On** | Verdict = Sell high; age ≥ 35 → *Decline risk*, or xwOBA gap < −0.020 | Dark red | Strong underlying regression signal |
| **Sell High on Perception** | Verdict = Sell high; xwOBA gap ≥ −0.020 | Orange | ERA running hot but contact not catastrophic |
| **Veteran Regression** | Verdict = Sell high; career IP > 400; xwOBA gap > −0.020; luck score in [−0.30, −0.15] | Amber | Proven arm on a lucky stretch |
| **Slight Regression Expected** | Verdict = Slight sell | Yellow | Modest correction likely |

Birth year and career IP are sourced from `data/career_stats.json` (MLB Stats API). Age ≥ 35 → Decline risk; age 33–34 within Veteran Regression → Age concern flag.

---

## Trade Value Engine

### `score_value.py`

Reads the luck input CSVs plus cached API data and produces a trade value for every player across every league defined in `league_config.json`. Uses a **three-layer framework** that separates what you project, how much you trust the projection, and how much luck has distorted the current sample.

**Usage:**

```bash
python score_value.py            # compute, print top-10 tables, prompt for confirmation to write
python score_value.py --write    # compute and write data/player_values.json without prompting
python score_value.py --dry-run  # compute and print tables only; never write
```

#### Layer 1 — Expected Stats Value

Projects each player's full-season counting and rate stats from Statcast expected metrics (xwOBA, barrel_rate, xERA, k_pct, etc.), then computes how many standard deviations above the positional replacement level they are across all scoring categories.

**Replacement level:** For each roster slot, eligible players are ranked by a pre-score (unweighted z-sum); the last rostered player's projected stats set the replacement baseline. Value = Σ (player_proj − replacement_proj) / pool_std for each category. ERA and WHIP contributions are IP-weighted so starters' rate advantages scale with volume.

**Hitter projection formulas:**

| Stat | Formula | League-avg check |
|---|---|---|
| HR | `barrel_rate × 0.60 BBE/PA × 0.75 HR/barrel × PA_proj` | ≈ 18 HR/600 PA |
| R | `xwOBA × 0.42 × PA_proj` | ≈ 81 R/600 PA |
| RBI | `xwOBA × 0.38 × PA_proj + HR × 0.15` | ≈ 76 RBI/600 PA |
| SB | `position_default × PA_proj/600` (C/1B/DH=7.5, MI/CI=8.5, OF=9.0) | position-level |
| OBP | `xBA + bb_pct × (1−xBA) + 0.005` | ≈ .317 |
| AVG | `xBA` | — |

**Pitcher projection formulas:**

| Stat | Formula |
|---|---|
| ERA | `xERA` (clipped 1.50–9.00) |
| WHIP | `(bb_pct×4.30×9 + BABIP_allowed×contact_rate×4.30×9) / 9` |
| K | `k_pct × 4.30 BF/IP × IP_proj` |
| W | `IP_proj × 0.075 × max(0.3, 1 + (4.00−ERA)/7)` |
| SV/H | Estimated from performance tier (Elite/Good/Avg) when FanGraphs unavailable |

#### Layer 2 — Track Record Multiplier

Discounts projections for inexperienced players; full trust at career thresholds.

| Player type | Formula | Key breakpoints |
|---|---|---|
| Hitters | `min(1.0, 0.40 + career_PA/3000 × 0.60)` | 0 PA → 0.40, 1000 → 0.70, 3000+ → 1.00 |
| Pitchers | `min(1.0, 0.40 + career_IP/800 × 0.60)` | 0 IP → 0.40, 200 → 0.55, 800+ → 1.00 |

**Pitcher durability recency weight (applied to base):**
```
recency_mult = min(1.0, last_2yr_ip / 300)
track_record = base_track_record × (0.7 + 0.3 × recency_mult)
```

**Age curve for pitchers 32+ (applied after recency weight):**
```
age_decay = max(0.80, 1.0 - (age - 31) × 0.03)
```
A 35-year-old pitcher gets max(0.80, 1.0 − 4×0.03) = 0.88. Applied only to pitchers; hitters use career PA ramp only.

**Journeyman pitcher penalty (applied after age curve):**
Established pitchers with 0 quality points and career IP > 500 receive a 0.90 multiplier to prevent volume from masking mediocrity.

**Statcast quality point floor (Refinement 2):**
Young players (< 1,500 career PA for hitters, < 500 IP for pitchers) earn a track record floor boost from elite Statcast signals (0–3 points). A player with 3 QP gets a floor of 0.80 regardless of career volume.

| QP | Floor |
|---|---|
| 0 | 0.00 |
| 1 | 0.55 |
| 2 | 0.70 |
| 3 | 0.80 |

Hitter QP criteria (each +1 pt): top-15% xwOBA, top-15% hard-hit rate, top-15% bb%.
Pitcher QP criteria (each +1 pt): top-10% fastball velo, top-10% SwStr%, top-15% xERA.

#### Layer 3 — Luck Adjustment

Uses the luck score from `luck_scores.csv` / `pitcher_luck_scores.csv` to apply a ±25% multiplier:

```
luck_adj = 1.0 − luck_score × 0.10    capped at [0.75, 1.25]
Neutral verdict → 1.00 (no adjustment; small-sample confidence floor not met)
```

**Final trade value:**
```
raw_value  = expected_stats_value × track_record_mult × luck_adj
trade_value = raw_value / max_raw_value × 100    (scaled 0–100 per league)
```

#### Output — `data/player_values.json`

One record per player with all projections and three-layer breakdown for both leagues. Consumed by `dashboard.html` Trade Value tab.

**Key fields per record:**

| Field | Description |
|---|---|
| `id` | MLBAM player ID |
| `name` | Player name |
| `position` | Position abbreviation |
| `l1_value`, `l2_value` | Trade value (0–100) for League 1 / League 2 |
| `luck_score` | Raw luck score from `luck_scores.csv` |
| `verdict` | Buy low / Slight buy / Neutral / Slight sell / Sell high |
| `cqs` | Career Quality Score (0–100) |
| `cqs_tier` | Superstar / Established Star / Solid Contributor / Developing |
| `cqs_floor` | Trade value floor applied (0 if ineligible) |
| `cqs_floor_applied` | True if L1/L2 were raised to meet CQS floor |
| `conversion_flag` | `"overperformer"` / `"underperformer"` / null |
| `conversion_note` | Human-readable conversion rate summary |

---

## Backtesting Engine

### `backtest_april.py`

Pulls and caches historical Statcast data for 2023 and 2024, computes April luck scores using the current model, and merges them with May-July performance to produce a labeled dataset for model validation.

**What it does:**

1. Fetches four date ranges via pybaseball: 2023 April, 2023 May-July, 2024 April, 2024 May-July. Each is cached as a flat CSV in `backtest_cache/` so subsequent runs load instantly.
2. Aggregates April metrics per batter: PA, BABIP, hard-hit rate, barrel rate, z-contact rate, HR/FB rate, BA, wOBA, xBA, xwOBA, and xwOBA gap.
3. Computes April luck scores using the same `COMPONENTS` and `confidence_scale()` logic as the live model.
4. Aggregates May-July metrics per batter: PA, BABIP, BA, wOBA, HR rate.
5. Merges on batter MLBAM ID; applies minimum filters (≥ 50 April PA, ≥ 100 May-July PA).
6. Computes deltas: `delta_BABIP`, `delta_BA`, `delta_wOBA`, `delta_HR_rate` (May-July minus April).
7. Saves to `backtest_raw.csv` (551 player-seasons: 263 in 2023, 288 in 2024).

**xwOBA computation for backtest:** For batted balls (excluding HR), uses `estimated_woba_using_speedangle`. For HR, strikeouts, walks, and HBP (true-outcome events where xwOBA is null), falls back to actual `woba_value`. This matches the logic in `process_stats.py` exactly.

---

### `backtest_analyze.py`

Reads `backtest_raw.csv` and runs four analysis passes, then generates a full Markdown report and an annotated results CSV.

**Analysis passes:**

| Pass | What it measures |
|---|---|
| Correlation analysis | Pearson and Spearman r between April luck score and each delta metric (delta_wOBA, delta_BABIP, delta_BA, delta_HR_rate) |
| Verdict accuracy | Mean delta_wOBA and directional accuracy (% of players who improved when predicted to) for each verdict tier |
| Metric importance | Correlates each individual April metric deviation vs delta_wOBA to rank which raw metrics carry the most signal |
| Weight grid search | Tests 32,400 combinations across six weight dimensions; maximizes Pearson r with delta_wOBA |

**Grid search results (best weights):**

| Component | v1 weight | Optimal weight | Predictive r |
|---|---|---|---|
| BABIP | −5.000 | −3.000 | −0.502 |
| HR/FB rate | −0.040 | −0.150 | −0.333 |
| Hard-hit rate | +0.025 | 0.000 (removed) | −0.142 |
| Barrel rate | +0.030 | 0.000 (removed) | −0.229 |
| Z-contact rate | −0.010 | −0.030 | −0.080 |
| xwOBA gap | (new) | +1.000 | +0.402 |

**Model correlation improvement:**

| | v1 | v2 |
|---|---|---|
| Pearson r (luck score vs delta_wOBA) | +0.506 | +0.539 |

**Outputs:**

- `backtest_results.csv` — `backtest_raw.csv` plus `prediction_correct` (1/0) and `signal_strength` (luck score quartile) columns
- `backtest_report.md` — full narrative with correlation tables, verdict accuracy tables, metric importance ranking, and top-10 grid search weights

---

### `backtest_v4.py` (2026-04-20)

Full out-of-sample backtest of the v4 luck model. Strictly more rigorous than `backtest_april.py`: scores one full season's April data, then measures whether performance changed in the predicted direction across the *entire following season*.

**Design:**

| Parameter | Value |
|---|---|
| Scoring years | 2022, 2023, 2024 (April Statcast) |
| Outcome years | 2023, 2024, 2025 (full season wOBA delta) |
| Min PA (scoring year) | 300 (full season) |
| Min PA (outcome year) | 300 (full season) |
| Player-seasons | 506 (163 + 170 + 173) |
| Model scored | v4 (all contextual modifiers) + v1 (original 5-component, same data) |
| Benchmark | Regression-to-mean (Steamer proxy) |

v4 model includes all components: pull_rate modifier, chase rate modifier, z-contact quality gate, PA gate (≥75), confidence multiplier. v1 runs on the same player-seasons for direct comparison.

Note: April 2023/2024 cache files from `backtest_april.py` lack `hc_x`, `hc_y`, `stand` columns — the v4 backtest uses separate `v4_april_{year}.csv` caches with the full column set.

**Results:**

| Metric | v1 | v4 | Change |
|---|---|---|---|
| Pearson r vs Δ wOBA | +0.1623*** | +0.2112*** | +0.049 |
| Directional accuracy | 56.1% | 59.4% | +3.3pp |
| Buy Low accuracy | — | 59% (77/130) | — |
| Sell High accuracy | — | 65% (60/93) | — |
| RTM baseline (Steamer proxy) | — | 68.2% | — |

> **Cross-methodology note:** The original v1 backtest (r=0.506, 71%) used April → May-July intra-season regression with 50/100 PA thresholds. The v4 backtest uses full-season cross-year outcomes with 300/300 PA thresholds — a stricter, more conservative test. The different windows are not directly comparable; the v4 test is harder. Directional accuracy above random (50%) and RTM demonstrates genuine predictive power.

**Usage:**

```bash
python backtest_v4.py           # dry run — prints results, writes report only
python backtest_v4.py --write   # also writes backtest_v4_raw.csv
```

**Outputs:**

- `backtest_results_v4.md` — full report (correlation tables, verdict breakdown, component validation, CQS floor validation, Steamer comparison)
- `backtest_v4_raw.csv` — per-player-season data with v4 scores, v1 scores, delta wOBA, modifier flags

---

## Dashboard

### `dashboard.html`

A standalone browser dashboard that reads `luck_scores.csv` and `pitcher_luck_scores.csv` and renders an interactive luck analyzer. No web server or external dependencies required.

**Opening the dashboard:**

```
# Option 1 — double-click the desktop shortcut: "Fantasy Baseball Dashboard"

# Option 2 — run the launcher directly:
run_pipeline.bat        # pipeline runs first, then dashboard opens automatically

# Option 3 — start the server manually, then open in browser:
python -m http.server 8000
# Navigate to: http://localhost:8000/dashboard.html
```

When served over HTTP (localhost or a web server), the dashboard auto-loads both CSVs on page open. When opened directly as a local file (`file://`) in Chrome, the browser's security restrictions block `fetch()` reads of local files; the dashboard falls back to a clean file-picker UI where you select each CSV manually.

**Features:**
- Tabs for Hitters and Pitchers with independent sort, search, and filter state
- Five verdict summary cards (Buy Low / Slight Buy / Neutral / Slight Sell / Sell High); click any card to filter the table; click the same card again to deselect and show all players; search works alongside the card filter
- Active card is highlighted with a colored ring and lifted position; unselected cards dim to 35% opacity, confirming which filter is applied
- Sortable columns; clicking the same column twice reverses sort direction
- Search box filters by player name in real time
- Color-coded rows and verdict badges matching the score thresholds
- ERA gap columns highlighted green (pitcher likely unlucky) or red (pitcher likely lucky) for gaps > ±0.30
- NaN values displayed as `—`

**Known issue fixed — card filter onclick:** The original card click handlers used `onclick="toggleFilter(${JSON.stringify(key)})"`, where `JSON.stringify` wraps the verdict string in double quotes. Verdict keys contain spaces (e.g. `"Buy low"`), so the rendered HTML was `onclick="toggleFilter("Buy low")"` — the inner double quote ended the attribute before the function call completed, silently breaking all card clicks. Fixed by storing the verdict in a `data-verdict` attribute and reading it back with `this.dataset.verdict`, which bypasses HTML attribute quoting entirely. The same pattern was applied to column sort handlers.

---

## Automation

### `run_pipeline.bat`

A Windows batch file that wraps `run_pipeline.py` with logging and post-run dashboard launch. Intended for Task Scheduler but also runnable manually.

**What it does:**

1. Creates `logs/` if it doesn't exist
2. Builds a datestamped log filename using PowerShell (`Get-Date -Format yyyy-MM-dd`) to avoid locale-dependent `%DATE%` parsing failures
3. Deletes log files older than 30 days (`forfiles /d -30`)
4. Runs `run_pipeline.py` and redirects all stdout + stderr to the log file
5. On success (exit code 0), calls `launch_dashboard.bat` to start the HTTP server and open the dashboard

---

### `launch_dashboard.bat`

A standalone batch file that starts the HTTP server and opens the dashboard. Called automatically by `run_pipeline.bat` on success and also the target of the desktop shortcut.

**What it does:**

1. Checks whether port 8000 is already listening using `Get-NetTCPConnection -LocalPort 8000 -State Listen`
2. If the port is free, starts `python -m http.server 8000` in a minimized background window
3. Waits 2 seconds for the server to bind
4. Opens `http://localhost:8000/dashboard.html` in the default browser

If you run the shortcut a second time while the server is already running, it skips starting a duplicate process and goes straight to opening the browser.

---

### Task Scheduler

The pipeline runs automatically every morning via a Windows Task Scheduler task named **FantasyBaseballPipeline**.

**Trigger:** Daily at **6:00 AM Pacific time**

Task Scheduler stores the trigger time against the local system clock (`StartBoundary: 06:00:00`), not as a UTC absolute. This means:
- During Pacific Daylight Time (PDT, UTC−7): fires at 6:00 AM PDT
- During Pacific Standard Time (PST, UTC−8): fires at 6:00 AM PST

No manual adjustment is needed at DST transitions — the task follows the local clock automatically.

**Why 6 AM Pacific:** Baseball Savant processes Statcast data overnight and makes each day's games available by approximately 10 AM ET / 7 AM PT. Running at 6 AM Pacific ensures all games through two nights prior are fully available, and most games from the previous night will be present as well. Any same-day gaps are picked up on the following morning's run.

**StartWhenAvailable:** The task is configured with `StartWhenAvailable = true`. If the machine is asleep or off at 6 AM (e.g., a laptop that was closed overnight), Task Scheduler will run the pipeline as soon as the machine wakes up and a missed trigger is detected. Without this setting, a missed 6 AM run would be silently skipped until the next day.

**Manual trigger:**

```powershell
Start-ScheduledTask -TaskName 'FantasyBaseballPipeline'
```

Or double-click the **Fantasy Baseball Dashboard** desktop shortcut to start the server and open the dashboard without re-running the pipeline.

---

## Formula Validation

`validate_pitcher_calcs.py` cross-checks `pitcher_luck_input.csv` against official stats from the MLB Stats API (`statsapi.mlb.com`), which is publicly accessible and returns ERA, IP, and component counts (HR, BB, HBP, K) for all pitchers.

### Validation results (2026 season, 141 pitchers ≥ 10 IP)

| Stat | Mean absolute error | Within 0.50 | Within 1.00 | Verdict |
|---|---|---|---|---|
| **FIP** | 0.12 | 95% | 99% | Correct — negligible self-calibration bias of +0.025 |
| **IP** | 0.88 | 73% | 87% | Correct — error driven by Baseball Savant overnight lag (see below) |
| **ERA** | 0.71 | 45% | 72% | Sound methodology — gaps cascade from missing IP denominator |

FIP accuracy is high because it depends only on counting discrete events (HR, BB, HBP, K) which Statcast records reliably. ERA is derived from `bat_score` delta tracking, which is a sound approximation of RA/9 but not identical to official ERA (see known limitations below).

### Baseball Savant overnight lag

Baseball Savant processes Statcast data overnight, typically making each day's games available by ~10 AM ET the following morning. The MLB Stats API updates in near-real-time from official scoring. This creates a predictable one-day gap:

- If the pipeline is run before Baseball Savant has processed the prior day's games, that day's pitching appearances will be missing from `pitchers_statcast.csv`.
- `fetch_pitcher_stats.py` sets `SEASON_END = date.today()`, so each run fetches through the current date. Games that Baseball Savant hasn't yet published will return zero rows and be silently skipped; they will be picked up on the next run.
- The practical effect is that starters who pitched the previous evening may show an IP undercount of ~5–7 innings (one start) until the following morning's run. This inflates their Statcast-derived ERA for that run.
- **Recommendation:** run the pipeline in the morning (after ~10 AM ET) to ensure the prior day's games are fully available.

### Known limitations

**Inherited-runner ERA attribution for relievers.** The Statcast RA/9 method tracks runs scored by watching `bat_score` increase while a pitcher is on the mound. When a reliever enters with runners already on base and those runners score, the runs are attributed to the reliever in our model rather than the pitcher who allowed them on base. Official ERA uses a full inherited-runner accounting system that our score-change approach cannot replicate from pitch-level data alone.

The practical effect: relievers who frequently inherit runners (setup men, high-leverage closers) may show a higher Statcast ERA than their official ERA, making them appear unlucky when they are not. The ERA gap components in `score_pitcher_luck.py` use intentionally conservative weights (0.15 and 0.10) to limit this distortion. For starters — who represent the majority of high-IP buy/sell candidates — the method is accurate.

---

## Interpretation Guide

### Hitters

- **Buy low targets:** The strongest signal is a low BABIP combined with a positive xwOBA gap — the player is both failing to get hits on balls in play and getting worse outcomes than their contact quality deserves. A player running a .210 BABIP with a +.080 xwOBA gap is being hit hard twice over by luck. Hard-hit rate and barrel rate in the dashboard provide secondary confirmation.
- **Sell high targets:** Negative `luck_score` driven by a sky-high BABIP and negative xwOBA gap (getting better results than their contact quality justifies). A player hitting .450 BABIP with xwOBA well below actual wOBA is almost certainly due for a sharp decline.
- **xwOBA gap context:** A large positive xwOBA gap (+.060 or more) is one of the strongest predictors of upcoming improvement — it means the player's expected outcomes from contact quality are running well ahead of their actual results. A negative gap confirms a lucky stretch. Watch for cases where the BABIP and xwOBA gap disagree: BABIP is about sequencing, xwOBA is about contact quality, and divergence between them signals a more nuanced situation.
- **Be cautious with HR/FB:** This stat requires the most PA (~200+) to stabilize. Early-season HR/FB extremes are noisy but the backtesting showed they carry real predictive signal (r = −0.333), so extreme readings (< 5% or > 25%) are worth noting.
- **Z-contact context:** A low Z-contact rate (< ~80%) is often a real skill issue, not luck. If a player's buy-low case depends heavily on Z-contact, be skeptical.
- **Sample size:** The confidence multiplier handles this automatically — scores are zeroed below 30 PA and reach full weight at 100 PA. The displayed luck_score already reflects sample size uncertainty.

### Pitchers

- **ERA-FIP gap:** A large positive ERA-FIP gap means a pitcher's ERA is running well above their walk, strikeout, and HR rate — usually a sign of bad BABIP luck or sequencing. Expect regression toward FIP.
- **ERA-xERA gap:** Similar signal but anchored to contact quality rather than true outcomes. A pitcher allowing weak contact (low hard-hit rate, low barrel rate) but posting a high ERA is a strong buy-low candidate.
- **BABIP allowed:** League average is ~.300. Pitchers sustaining very high or very low BABIPs without corresponding contact quality differences are likely experiencing luck.
- **Strand rate (LOB%):** League average is ~72–74%. Pitchers with LOB% well below average often see ERA inflated by bad sequencing; those well above average are benefiting from luck with runners on base.
- **HR/FB rate:** Regresses toward league average (~10–12%) over a full season. A pitcher with a 20%+ HR/FB rate early in the season likely has ERA inflated by home run luck.
- **Sample size:** ERA gap metrics are most meaningful with at least 30–40 IP. Below that, a few bad outings can distort everything.

---

## Roadmap

Planned enhancements for future development sessions.

### Hitter model

| Feature | Description |
|---|---|
| **xBABIP** | Compute expected BABIP from per-ball-in-play contact quality (average xBA on BIP events) and replace raw BABIP deviation with the xBABIP gap. This removes the "true skill" component from BABIP: a line-drive hitter legitimately outperforms the .300 league average, while a popup hitter legitimately underperforms it. Replacing `(BABIP − .300)` with `(BABIP − xBABIP)` isolates the luck portion. |
| **Extended backtesting** | The current backtest covers 2023–2024 April vs May-July. Expanding to full-season windows and additional years (2021–2022) would reduce the risk of overfitting in the grid-searched weights and validate the confidence multiplier thresholds. |
| **Streak detection** | Flag players who have shown a sustained hot or cold stretch in the past 7–14 days, distinct from overall season luck. A player with a neutral season luck score but a +0.30 xwOBA gap over the past two weeks is a more timely buy-low candidate than the season-to-date score suggests. Could be implemented as a rolling-window second pass over `hitters_statcast.csv` and displayed as a "recent trend" column in the dashboard. |
| **ADP integration** | Pull current Average Draft Position data (from NFBC, Underdog, or Sleeper APIs) and cross-reference with luck scores. A player who is a strong Buy Low but whose ADP has already risen sharply in the past week is less actionable than one whose market hasn't caught up yet. Surface as a "market awareness" indicator alongside the luck verdict. |

### Pitcher model

| Feature | Description |
|---|---|
| **xBA gap** | Add xBA-vs-BA allowed as a supplemental signal. Pitchers giving up hits on weak contact (high BABIP relative to poor xBA) are strong buy-low candidates independent of ERA. |
| **Starter/reliever split** | Apply separate league-average baselines and verdict thresholds for starters vs. relievers. Relievers have structurally different ERA profiles (LOB% noise from inherited runners, volatile HR/FB from small samples); a shared model understates their signal-to-noise difference. |
| **Pitcher backtesting** | Run the same April vs May-July backtest framework against pitcher luck scores to validate and calibrate the pitcher model weights, mirroring the hitter model work in `backtest_april.py` / `backtest_analyze.py`. |
| **Verdict threshold recalibration (Session 8)** | The v2 model regularly produces scores in the ±0.40–0.65 range in April. The current thresholds (±0.07 / ±0.15) were calibrated for the v1 model where scores rarely exceeded ±0.20. Recalibrate after a full season of v2 scores using the backtest framework extended to pitchers. |

### Parking lot (Phase C and beyond)

| Feature | Description |
|---|---|
| **Phase C: Seasonal pattern detection** | Flag confirmed slow starters (3-year April vs full-season split chronically low BABIP) so their April buy signals are suppressed — the "regression" was expected from the start. |
| **Phase B: Chase modifier recalibration** | Backtest showed chase modifier reduces directional accuracy by 3.4pp when fired. Candidate for removal or threshold tightening (require both high O-Swing% AND extreme BABIP, not just O-Swing% alone). |
| **Career FIP integration for pitcher RTM** | `career_stats.json` currently stores only `career_pa` and `birth_year`. Adding career FIP average would enable true RTM signal for pitchers (vs current FIP-xERA same-season proxy). Add to career stats fetch in MLB Stats API layer. |
| **Verdict threshold recalibration (Phase A scores)** | Phase A refinements expand the score range significantly (scores now reach 0.5-0.7+ for strong buy/sell confluences). Current hitter thresholds (±0.05 / ±0.12) were calibrated for v4 scores. Review at end of 2026 season using the backtest framework with Phase A scores to check if thresholds need raising to reduce false positives. |
| **Park change detection** | Consistency multiplier framework includes a `park_change_detected` flag (currently always False). Activating it requires per-year team data in the expected_stats cache. Would reduce the consistency penalty for players who changed parks between 2022-2024 (e.g., Ohtani: Angels → Dodgers). |
| **wRC+ tier recalibration (post-backtest)** | The Superstar (≥130) and Elite (120-129) tier thresholds for quality gate multipliers were set theoretically. After the 2026 backtest (v4 vs v5 vs v6), recalibrate against actual prediction accuracy improvements per tier to confirm the 130 threshold is correct. |
| **Park factor updates** | Hardcoded 2026 park factor table (FanGraphs + Baseball Reference both block scraping). Update annually or when FanGraphs access is restored. Also: split BABIP vs HR/FB park factors — current model uses same factor for both, but some parks (e.g., Coors) inflate BABIP more than HR/FB and vice versa. |
| **Dashboard signal strength distinction** | Slight Buy / Slight Sell verdicts perform near-noise in backtest (Slight Buy ~50% accuracy). Dashboard should visually distinguish strong signals (Buy low / Sell high) from watch-list signals (Slight buy / Slight sell) to reflect true confidence level. |

### Session 6 roadmap

| Feature | Description |
|---|---|
| **Dashboard trade value tab** | Add a "Trade Value" tab to `dashboard.html` that reads `data/player_values.json` and displays League 1 / League 2 values side by side with the three-layer breakdown (Exp Stats, Track Rec, QP, Luck Adj, Verdict). |
| **Pitcher pool expansion** | Lower `MIN_IP` in `process_pitcher_stats.py` from 10 to 7 to capture more relievers early in the season. At 18 days into the season, MIN_IP=10 excludes ~70 relevant pitchers. Target pool: 200–250. |

### Completed

| Feature | Status |
|---|---|
| **v3 hitter luck model — contextual modifiers** | ✓ Implemented — `process_stats.py` now computes `pull_rate` (spray-angle method, ~39% league mean) and `o_swing_rate` (O-Swing%, ~30% league mean). `score_luck.py` v3 applies three directional modifiers: pull rate reduces the HR/FB luck penalty for pull hitters; chase rate and z-contact rate modulate the BABIP component based on which side of .300 BABIP falls on, so the modifier always pushes the signal in the correct direction for both buy and sell candidates. |
| **Three-layer trade value engine** | ✓ Implemented — `score_value.py` computes Expected Stats Value × Track Record Multiplier × Luck Adjustment for each player per league. Writes `data/player_values.json`. |
| **Track record multiplier** | ✓ Implemented — career PA / IP ramps (0 PA=0.40 floor, 3000 PA=1.00 for hitters; 0 IP=0.40, 800 IP=1.00 for pitchers). |
| **Statcast quality points** | ✓ Implemented — 0–3 QP from elite Statcast signals raises the track record floor for young players (< 1500 PA / < 500 IP). Hitter: xwOBA, hard-hit, bb%. Pitcher: velo, SwStr%, xERA. |
| **Pitcher durability recency weight** | ✓ Implemented — last_2yr_ip / 300 modifies base track record as `base × (0.7 + 0.3 × recency_mult)`. Fetched from MLB Stats API yearByYear, cached in `data/career_stats.json`. |
| **Journeyman pitcher penalty** | ✓ Implemented — 0 QP + career IP > 500 → 0.90× multiplier on track_record_mult. Prevents volume from outranking young elite-stuff arms. |
| **Age curve for pitchers 32+** | ✓ Implemented — `max(0.80, 1.0 - (age-31) × 0.03)` multiplied into track_record_mult. Birth years fetched from MLB Stats API, cached in `data/career_stats.json`. |
| **Ohtani / TWP position fix** | ✓ Fixed — players appearing in `hitter_luck_input.csv` with MLB API primary position "P" or "TWP" are forced to "DH" in the hitter pool so they are not excluded from hitter rankings. |
| **xwOBA gap (hitter)** | ✓ Implemented in v2 — `process_stats.py` now computes `wOBA` and `xwOBA`; `score_luck.py` adds `xwOBA_gap = xwOBA − wOBA` as a scoring component (weight +1.000, r = +0.402 vs Δ wOBA). |
| **Confidence multiplier (hitter)** | ✓ Implemented in v2 — `score_luck.py` applies `min(1, max(0, (PA−30)/70))` to fade scores toward zero for small samples. Players below 30 PA score zero. |
| **Pitcher luck model v2 — seasonal confidence floor** | ✓ Implemented — `score_pitcher_luck.py` now uses a date-aware multiplier with phase-specific floors: April floor 0.25 at ≥15 IP, May floor 0.15 at ≥18 IP, June+ original formula. A `conf_phase` column is written to the output CSV. A 22-IP pitcher in April gets 0.25× instead of 0.05×, allowing real signals to surface before mid-May. |
| **Pitcher luck model v2 — HR/FB rate as scored component** | ✓ Implemented — HR/FB rate > 0.14 triggers a positive luck signal `(hr_fb_rate − 0.12) × 2.0`. Contextual modifier: hard contact rate > 0.38 dampens the signal 35% (contact partly explains the HR/FB); soft contact rate < 0.28 amplifies it 25% (soft contact + high HR/FB = strong regression candidate). |
| **Pitcher luck model v2 — xwOBA gap** | ✓ Implemented — `score_pitcher_luck.py` loads `pitchers_statcast.csv` and computes `xwoba_gap = actual wOBA allowed − xwOBA allowed` per PA (weight +1.5). Uses `estimated_woba_using_speedangle` with `woba_value` fallback for HR and true outcomes — mirroring the xERA construction. Mirrors the hitter xwOBA gap in direction and methodology. |
| **Confidence multiplier (pitcher)** | ✓ Implemented — original formula: `min(1, max(0, (IP−20)/40))`. Replaced in v2 by the date-aware seasonal floor (see above). |
| **Backtesting** | ✓ Completed — `backtest_april.py` pulls 2023–2024 historical data; `backtest_analyze.py` runs correlation analysis, verdict accuracy, metric importance ranking, and 32,400-combination weight grid search. Results in `backtest_report.md`. |
| **Blank-name Chadwick fix (pitcher)** | ✓ Fixed — `process_pitcher_stats.py` now detects Chadwick Bureau entries where the name resolved to null/empty ("Nan Nan") and routes those IDs to the MLB Stats API fallback, same as completely-missing IDs. |
| **Phase B: Consistency score** | ✓ Implemented — `compute_consistency.py` applies per-player variance multipliers to luck_score_v5 producing luck_score_v6. Five-tier variance system (Very Consistent/Consistent/Inconsistent/Volatile/Extreme). Elite quality gate (wRC+ > 120) gates the consistency boost so average-consistent players (Bohm) receive neutral multiplier. Age modifier amplifies penalties for 32+ players. ~58% insufficient data is expected correct behavior for players without 2+ seasons of 300+ PA. Superstar wRC+ tier (≥130: ×1.15) added to score_luck.py quality gate. |
=======
# Signal-Fantasy-Pipeline
The Signal Fantasy - Statcast Luck Detection Pipeline.  First published April 22, 2026
>>>>>>> e85b09bbc3a81c9c33f0753b9448f23d40ab32fc
