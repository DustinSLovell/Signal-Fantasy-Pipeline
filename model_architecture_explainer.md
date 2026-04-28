# The Signal Fantasy — Model Architecture Explainer
# Last updated: April 2026

---

## What This Is

A production fantasy baseball analytics pipeline that scores MLB hitters and pitchers for luck-based buy/sell signals. Built from April 12-14, 2026 in ~10 days. Validated against out-of-sample 2025 data before any live publishing. First article published April 22, 2026.

---

## Four-Layer Architecture

```
Layer 1: Signal Model     →  luck_score, verdict, tier
           score_luck.py (hitters)
           score_pitcher_luck.py (pitchers — v2.0 split architecture)

Layer 2: Projection Engine →  proj_avg, proj_hr, proj_rbi, proj_era, proj_k, etc.
           stat_projections.py + generate_projections.py

Layer 3: Value Engine      →  league1_value, rank, surplus_value
           score_value.py + replacement_level.py

Layer 4: Trade Analyzer    →  trade verdict, FPTS delta, surplus comparison
           trade_analyzer.py
```

Layer 1 is the core. Every downstream calculation inherits from it. Signals inform projected stats; projected stats determine trade value. Signals do not directly weight trade verdicts — that separation is intentional.

---

## Layer 1: Signal Model

### The Core Hypothesis

ERA (actual runs allowed) lags behind contact quality metrics by weeks to months. A pitcher with ERA 6.00 but xwOBA-allowed matching his career norm is a buy, not a sell. A hitter with wOBA .250 but xwOBA .340 is running below expected contact quality — he will regress upward.

The model detects this mispricing in April, before the rest of the market corrects.

### Why April?

April is structurally the highest-signal window:
- **Maximum market mispricing**: small samples produce volatile surface stats; fantasy managers overreact
- **Maximum time value**: a correct April buy has the entire May-August core season ahead to validate
- **Minimum ERA gate issues**: pitchers with inflated ERAs from BABIP/LOB luck haven't yet been dropped

The backtest uses April data to generate signals and May-July data to validate outcomes.

---

## Hitter Model (Version D — adopted April 26, 2026)

### Signal Formula

```
luck_score = xwOBA_gap × 0.60 + babip_luck × 0.40
             (backtest ruler — simplified 2-component form)
```

Production uses a 4-component weighted sum with 10+ modifiers. The backtest uses a simplified form calibrated to the April data distribution. These are two different rulers — never mix thresholds between them.

### Signal Tiers (production thresholds)

| Tier | Threshold | Description |
|------|-----------|-------------|
| Buy Low | > +0.150 | Strong mispricing, expect significant ERA/wOBA correction |
| Slight Buy | > +0.100 | Moderate mispricing, likely upside |
| Neutral | −0.085 to +0.100 | No reliable signal |
| Slight Sell | < −0.085 | Mild overperformance |
| Sell High | < −0.150 | Clear overperformance, expect regression |

### Slight Buy Gates (recalibrated April 25, 2026)

Slight Buy fires only when:
1. `xwOBA_gap >= 0.030` — eliminates BABIP-only signals (28.6% accuracy below this)
2. `xwOBA < 0.380` — eliminates already-elite hitters with no regression room
3. `luck_score > 0.100` — eliminates borderline coin-flip signals

### Additive Modifier Architecture (Version D)

Buy signals are dampened when secondary indicators suggest the ERA/wOBA gap may not fully close:

| Flag | Condition | Additive Penalty |
|------|-----------|-----------------|
| k_flag | K-rate spike >3pp above career | −0.010 |
| pull_flag | Pull rate drop >5pp below career | −0.008 |
| hh_flag | Hard-hit rate drop >3pp below career | −0.012 |
| speed_flag | Sprint speed cliff >0.3 ft/s YoY | −0.010 |
| chase_flag | Chase rate rise >3pp (buy-side only) | −0.008 |

Penalties are additive and cumulative. Combined cap: −0.040. Applied once after all flag detection.

**Why additive beats multiplicative:** A multiplicative ×0.95 penalty on a score of 0.050 yields 0.0475 — still Slight Buy. An additive −0.012 yields 0.038 — Neutral. The tier gap (0.040 between Slight Buy and Neutral) exceeds multiplier magnitude. Additive penalties are the only architecture that produces real tier reclassifications.

Age-weighted chase rate: penalty × 0.40 for age ≤25, × 0.70 for age 26-27 (development noise).

### Validated Accuracy (Version D, backtest v7)

| Signal | Train 2022-24 n | Train acc | OOS 2025 n | OOS acc |
|--------|-----------------|-----------|------------|---------|
| Buy Low | 55 | 91.3% | 25 | 96.0% |
| Slight Buy | 56 | 73.5% | 22 | 90.9% |
| Slight Sell | 56 | 89.3% | 26 | 76.9% |
| Sell High | 36 | 91.7% | 14 | 100.0% |
| **Overall** | **187** | **86.1%** | **87** | **89.7%** |
| vs RTM | — | — | — | **+17.9pp** |

Training: 2022-2024 only. Out-of-sample: 2025 only (never seen during training). The 89.7% OOS number is the authoritative credibility figure.

---

## Pitcher Model (v2.0 — split architecture, April 23, 2026)

### Architecture Motivation

Pitchers overperform and underperform ERA for fundamentally different reasons. A unified composite fails to capture this — BABIP-driven luck looks different from HR/FB-driven luck. Version 2.0 uses separate buy-side and sell-side formulas.

### Buy Score (ERA-FIP dominant)

```
raw_buy_score = ERA_minus_FIP × 0.60
              + xwOBA_gap     × 0.25
              + BABIP_gap     × 0.15
```

**Why ERA-FIP at 60%:** ERA_minus_FIP mean for buy signals is ~1.9 — roughly 100× larger than xwOBA_gap (~0.018) and BABIP_gap (~0.022). In raw form, ERA-FIP contributes ~99% of the signal. The secondary components add minor filtering but do not cross tier boundaries. This is a known limitation; see Parking Lot.

**Classification from raw score before confidence scaling.** Confidence scaling (`_april_conf_scale`) is applied after tier assignment, not before. Rationale: a pitcher 25 IP into the season at a given raw buy score is the same signal — just with less confidence in the outcome.

### Sell Score (8-component composite)

```
composite_sell = BABIP_allowed vs career  × 5.00
               + LOB% vs 72.4%            × −3.00
               + ERA_minus_FIP            × 0.15
               + ERA_minus_xERA           × 0.10
               + HR/FB rate (nonlinear, fires >14%)
               + Hard-hit% vs career      × −1.50
               + Barrel% vs career        × −1.50
               + SwStr% vs 11%            × 2.00
```

Buy and sell are evaluated independently. If raw_buy_score > 0 and sell score is not dominant, the buy path fires. If the sell side is dominant, the sell composite determines the tier.

### Buy Qualification Gates (all must pass)

```
FIP <= 4.50
SwStr% >= 8%
Career IP >= 100
IP >= 20 (waived if raw_buy_score >= 1.50 — dominant signal exception)
ERA >= 3.50 (global floor, all buys)
ERA >= 3.75 (Buy Low only — implemented April 25, 2026)
ERA >= 4.00 (Slight Buy only)
|FIP − xERA| <= 1.50 OR xERA <= 4.50
FIP >= 1.50 if IP < 20
```

The ERA >= 3.75 Buy Low floor was raised from 3.50 on April 25. Effect: +7.3pp OOS accuracy for Buy Low (removed pitchers whose ERAs were inflated but who were genuinely overperforming vs career contact quality).

### Validated Accuracy (2024 single-year backtest)

| Signal | n | Accuracy |
|--------|---|----------|
| Buy Low | 33 | 90.9% |
| Slight Buy | 10 | 60.0% |
| Slight Sell | 21 | 76.2% |
| Sell High | 20 | 100.0% |
| **Overall** | **84** | **85.7%** |
| vs RTM | — | **+17.5pp** |

Slight Buy n=10 historically is too thin to validate independently. Active research item.

---

## The Two-Ruler Framework

The backtest and production pipeline use different score scales. This is intentional and permanent.

| | Backtest (v7) | Production |
|--|--------------|------------|
| Formula | `xwOBA_gap × 0.60 + babip_luck × 0.40` | 4-component weighted sum + 10+ modifiers |
| Score range | peaks at 0.080-0.120 | regularly exceeds ±0.150 |
| Buy Low threshold | 0.040 | 0.150 |
| Slight Buy threshold | 0.020 | 0.100 |
| Use for | signal direction validation, A/B comparisons | live fantasy decisions, publishing |

Applying production thresholds to backtest scores yields ~23 evaluable cases — statistically meaningless. The two rulers exist because April-only 100-150 PA data produces a compressed distribution. Full-season PA windows produce a wider distribution, requiring wider thresholds.

---

## Layer 2: Projection Engine

Generates rest-of-season stat projections for 794 players from April Statcast data.

**Blend methodology:** PA-weighted blend between current-season rates and career baselines. At 95 PA: ~30% current, ~70% career. At 350 PA: ~60% current, ~40% career. Signal tier applies a directional multiplier (Buy Low pitchers: K × 1.05, ERA × 0.90).

**Thin baseline fix (April 2026):** Players with career PA < 1,000 receive a higher current-season weight (career weight × 0.85). Backtest validated: reduces HR bias from −4.44 to −2.05 for thin-baseline players.

**Known limitations:**
- RBI bias: −9.65 (lineup context not captured)
- AVG R²: 0.056 (unpredictable from April data — industry-wide limitation)
- Late-season breakouts are irreducible misses (Caminero proj 20, actual 45)

---

## Layer 3: Value Engine

Converts projected stats to CBS fantasy point equivalents via Ridge regression (R² = 0.983 OOS for hitters, 0.909 for pitchers). Surplus value = projected FPTS − replacement FPTS at position.

**CQS floors:** Career quality scores prevent young catchers with elite contact metrics from being undervalued when counting stats haven't accumulated yet.

**AVG liability penalty:** Hitters projecting below .220 receive a significant penalty to account for the roto damage of starting a near-.200 hitter. This is load-bearing — removing it allows Gary Sanchez to rank top-15 catchers, which fails the Sanchez Test.

---

## Layer 4: Trade Analyzer

Compares surplus value on both sides of a trade. Signals inform projected stats; signals do not independently weight verdicts.

**Verdict thresholds:** ≥75% Strong | ≥60% Favorable | ≥40% Neutral | ≥25% Unfavorable | <25% Avoid

---

## Training Window and Design Decisions

**Why 2022+:** Two rule changes make pre-2022 data non-comparable — deadened ball standardization (2021-2022) and universal DH adoption (2022). Pre-2022 career baselines are retained for individual player context only (relative reference, not cross-player comparison).

**Why April only:** April is the highest-signal window for detecting mispricing. Market is maximally reactive to surface stats in April. The model detects the gap before it closes.

**Two-track publishing:**
- Track 1 (April Signals): validated 86.1%/89.7% — the published Substack signals
- Track 2 (In-season rolling): weekly tracker, no validated accuracy — presented as observation only

---

## Validation Methodology

All numbers are from a strict train/OOS split:
- **Training:** 2022-2024 data (in-sample calibration)
- **Out-of-sample:** 2025 data only (never seen during training)
- **Guard rail:** any new modifier must not reduce 2025 OOS accuracy

Steps for every production change:
1. Add modifier individually
2. In-sample backtest (2022-2024)
3. OOS validation against 2025 (must improve or stay flat)
4. Ablation test confirming individual contribution
5. `validate_formulas.py` 37/37 PASS
6. Update validated numbers

The 37-test formula validation suite covers all key formulas, edge cases, and known anchors (Sanchez Test, Yordan Test, Luzardo projection).

---

## Permanent Invariants

These must pass after every `score_value.py --write`:

- Yordan Alvarez: top 20 overall
- Cal Raleigh: top 4 catchers (relaxed until PA > 150, mid-May 2026)
- Drake Baldwin: top 5 catchers
- William Contreras: top 8 catchers
- **Gary Sanchez: rank 21+ catchers** (The Sanchez Test — most important)

If Sanchez appears in the top 15, something is broken.

---

## Key Files

| File | Layer | Purpose |
|------|-------|---------|
| `score_luck.py` | 1 | Hitter luck scoring |
| `score_pitcher_luck.py` | 1 | Pitcher luck scoring (v2.0) |
| `stat_projections.py` | 2 | Per-player stat projection logic |
| `generate_projections.py` | 2 | Projection pipeline runner |
| `score_value.py` | 3 | Trade values and rankings |
| `replacement_level.py` | 3 | Position replacement baselines |
| `trade_analyzer.py` | 4 | Trade verdict engine |
| `config.py` | — | All thresholds — single source of truth |
| `validate_formulas.py` | — | 37-test formula validation suite |
| `run_pipeline.py` | — | Full pipeline orchestrator |

---

*© 2026 Dustin Lovell / Signal Fantasy*
