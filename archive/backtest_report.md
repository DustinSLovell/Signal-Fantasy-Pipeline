# Fantasy Baseball Luck Model — Backtest Report

**Generated:** 2026-04-13
**Model version:** Hitter luck score v1 (BABIP-anchored, 5-component)
**Significance:** `*` p<0.05  `**` p<0.01  `***` p<0.001  `†` p<0.10  `ns` not significant

---

## 1. Backtest Design

| Parameter | Value |
|---|---|
| Years tested | 2023, 2024 |
| April window | Opening Day through April 30 |
| Validation window | May 1 through July 31 |
| Min April PA | 50 |
| Min May-July PA | 100 |
| Total player-seasons | 551 (263 in 2023, 288 in 2024) |

**Hypothesis:** A positive April luck score (unlucky) should predict above-April
performance in May-July; a negative score (lucky) should predict below-April
performance. A well-calibrated model produces a significant positive correlation
between luck score and the May-July performance delta.

---

## 2. Current Model Weights

| Metric | League Avg | Current Weight | Notes |
| ------ | ---------- | -------------- | ----- |
| BABIP | .300 | -5.000 | Primary luck driver |
| HR/FB rate | 14.5% | -0.040 |  |
| Hard-hit rate | 39% | +0.025 |  |
| Barrel rate | 8% | +0.030 |  |
| Z-contact rate | 88% | -0.010 | Smallest weight |

**Sign convention:** positive luck score = unlucky = buy low candidate.

---

## 3. Correlation Analysis

### 3a. April luck score vs May-July performance delta

| Target | Pearson r | p-value | Spearman r | p-value | n |
| ------ | --------- | ------- | ---------- | ------- | ---- |
| delta wOBA (May-Jul minus April) | +0.5056*** | 0.0000 | +0.4709*** | 0.0000 | 551 |
| delta BABIP (May-Jul minus April) | +0.7683*** | 0.0000 | +0.7476*** | 0.0000 | 551 |
| delta BA (May-Jul minus April) | +0.6569*** | 0.0000 | +0.6234*** | 0.0000 | 551 |
| delta HR rate (May-Jul minus April) | -0.0317 | 0.4572 | -0.0315 | 0.4612 | 551 |

Significance legend: `***` p<0.001 . `**` p<0.01 . `*` p<0.05 . `†` p<0.10 . _(blank)_ ns

**Primary result:** The April luck score showed a Pearson r of **+0.5056** (p=0.0000)
with May-July wOBA delta across 551 player-seasons.
This is a statistically significant positive relationship, confirming the model captures real regression signal.

### 3b. Directional accuracy (non-neutral verdicts only)

Of the 485 player-seasons with a non-neutral verdict, **68.0%** saw performance
move in the predicted direction (wOBA improved for buy-low calls, declined for sell-high calls).
A random model would score ~50%. Scores above 55% indicate genuine predictive value.

---

## 4. Verdict Bucket Analysis

Did players perform as their April verdict predicted over May-July?

| Verdict | N | Mean delta wOBA | % Correct Direction |
| ------- | ---- | --------------- | ------------------- |
| Buy low | 205 | +0.0291 | 146/205 (71%) |
| Slight buy | 44 | +0.0057 | 24/44 (55%) |
| Neutral | 66 | -0.0051 | N/A |
| Slight sell | 52 | -0.0185 | 30/52 (58%) |
| Sell high | 184 | -0.0363 | 130/184 (71%) |

**Interpretation:**
- A gradient from positive mean delta wOBA in Buy low rows to negative in Sell high rows
  confirms the model's directional validity.
- The magnitude of the gap between Buy low and Sell high mean delta wOBA measures effect size.
- A large Buy low / Sell high spread with high directional accuracy = strong model.

---

## 5. Individual Metric Predictiveness

Which April metric, by itself, best predicted May-July wOBA improvement?

| April Metric | Pearson r vs delta wOBA | p-value | Spearman r | Significance |
| ------------ | ----------------------- | ------- | ---------- | ------------ |
| BABIP deviation | -0.5022 | 0.0000 | -0.4669 | *** |
| xwOBA gap (xwOBA - wOBA) | +0.4023 | 0.0000 | +0.3675 | *** |
| xBA gap (xBA - BA) | +0.3945 | 0.0000 | +0.3695 | *** |
| HR/FB deviation | -0.3328 | 0.0000 | -0.3093 | *** |
| Barrel rate deviation | -0.2293 | 0.0000 | -0.1686 | *** |
| Hard-hit deviation | -0.1421 | 0.0008 | -0.1306 | *** |
| Z-contact deviation | -0.0801 | 0.0604 | -0.0701 | † |

**Key finding:** **BABIP deviation** was the single strongest predictor of May-July
wOBA change. **Z-contact deviation** showed the weakest relationship and may deserve a lower
weight or removal from the model.

### Implications for weighting:
- Metrics with high |r| deserve higher weights in the composite luck score.
- Metrics with near-zero or wrong-sign r may be adding noise rather than signal.
- xwOBA gap and xBA gap appear as new candidates based on the Statcast estimator columns.

---

## 6. Weight Optimization

### Grid search parameters
- **BABIP weight:** [-3.0, -4.0, -5.0, -6.0, -7.0, -9.0]
- **HR/FB weight:** [0.0, -0.02, -0.04, -0.06, -0.1, -0.15]
- **Hard-hit weight:** [0.0, 0.015, 0.025, 0.04, 0.06, 0.1]
- **Barrel weight:** [0.0, 0.015, 0.03, 0.05, 0.08, 0.12]
- **Z-contact weight:** [0.0, -0.005, -0.01, -0.02, -0.03]
- **xwOBA gap weight (new):** [0.0, 0.5, 1.0, 2.0, 3.0]

Optimization target: **Pearson r between luck score and May-July delta wOBA**

### Top 10 weight combinations

| Rank | Pearson r | p | BABIP w | HR/FB w | HH% w | Barrel w | Z-Con w | xwOBA_gap w |
| ---- | --------- | ---- | ------- | ------- | ----- | -------- | ------- | ----------- |
| 1 | +0.5390 | 0.0000 | -3.0 | -0.15 | 0.0 | 0.0 | -0.03 | 1.0 |
| 2 | +0.5387 | 0.0000 | -3.0 | -0.15 | 0.0 | 0.0 | -0.02 | 1.0 |
| 3 | +0.5385 | 0.0000 | -3.0 | -0.15 | 0.015 | 0.0 | -0.03 | 1.0 |
| 4 | +0.5384 | 0.0000 | -3.0 | -0.15 | 0.0 | 0.0 | -0.01 | 1.0 |
| 5 | +0.5382 | 0.0000 | -3.0 | -0.15 | 0.0 | 0.0 | -0.005 | 1.0 |
| 6 | +0.5381 | 0.0000 | -3.0 | -0.15 | 0.025 | 0.0 | -0.03 | 1.0 |
| 7 | +0.5381 | 0.0000 | -3.0 | -0.15 | 0.015 | 0.0 | -0.02 | 1.0 |
| 8 | +0.5381 | 0.0000 | -3.0 | -0.15 | 0.0 | 0.015 | -0.03 | 1.0 |
| 9 | +0.5380 | 0.0000 | -3.0 | -0.15 | 0.0 | 0.0 | 0.0 | 1.0 |
| 10 | +0.5378 | 0.0000 | -3.0 | -0.15 | 0.0 | 0.015 | -0.02 | 1.0 |

### Optimal vs current weights

| Metric | League Avg | Optimal Weight | Change from Current |
| ------ | ---------- | -------------- | ------------------- |
| BABIP | .300 | -3.000 | +2.000 |
| HR/FB rate | 14.5% | -0.1500 | -0.1100 |
| Hard-hit rate | 39% | 0.0000 | -0.0250 |
| Barrel rate | 8% | 0.0000 | -0.0300 |
| Z-contact rate | 88% | -0.0300 | -0.0200 |
| xwOBA gap | — | 1.000 | New component |

**Improvement in correlation:** +0.0334 (current r=+0.5056 -> optimal r=+0.5390)

---

## 7. Key Findings and Recommended Model Changes

### Finding 1 — Overall predictive validity
OK The model produces a statistically significant positive correlation with May-July performance, confirming it captures genuine regression signal beyond noise.

### Finding 2 — Most predictive metric
**BABIP deviation** is the strongest individual predictor. The current model
correctly emphasizes this metric.

### Finding 3 — Least predictive metric
**Z-contact deviation** showed the weakest individual correlation with future performance.
Its weight appears reasonable given its predictive contribution.

### Finding 4 — xwOBA / xBA gap augmentation
OK Adding xwOBA gap as a model component improved correlation in the grid search. The gap between expected and actual wOBA captures luck on contact that BABIP alone misses.

### Finding 5 — Weight calibration
The optimal BABIP weight from the grid search is **-3.0**
vs the current **-5.000**. The current BABIP weight is in the right range.

---

## 8. Recommended Changes to `score_luck.py`

Based on the backtest, the following changes are recommended (in priority order):

### Priority 1 — Adopt optimized weights (estimated +0.0334 correlation lift)

```python
COMPONENTS = [
    # (column,          league_avg, weight,  label)
    ("BABIP",           0.300,     -3.000,   "BABIP vs .300"),
    ("hr_fb_rate",      0.145,     -0.1500,  "HR/FB vs 14.5%"),
    ("hard_hit_rate",   0.390,      0.0000,  "Hard hit vs 39%"),
    ("barrel_rate",     0.080,      0.0000,  "Barrel vs 8%"),
    ("z_contact_rate",  0.880,     -0.0300,  "Z-contact vs 88%"),
]
```

### Priority 2 — Add xwOBA gap component

Add `estimated_woba_using_speedangle` (xwOBA) to `process_stats.py` output and
include a new luck component in `score_luck.py`:

```python
# In process_stats.py — add xwOBA per batter (mean of xwOBA on contact per PA)
# In score_luck.py — add to COMPONENTS:
("xwOBA_gap",  0.0,  1.000,  "xwOBA gap vs actual wOBA"),
```

The xwOBA gap = (April xwOBA - April wOBA). Positive = player underperformed
their contact quality (unlucky). Backtesting shows this component adds predictive
signal beyond BABIP and exit-velocity metrics.

### Priority 3 — Confidence multiplier for small samples

Add a sample-size scaling factor to shrink luck scores toward zero for players
with fewer than 30 PA. This prevents early-season noise from dominating
the buy/sell lists before meaningful data has accumulated:

```python
def confidence_scale(pa: int, min_pa: int = 30, target_pa: int = 100) -> float:
    """Scale [0, 1] that grows from 0 at min_pa to 1 at target_pa."""
    return min(1.0, max(0.0, (pa - min_pa) / (target_pa - min_pa)))

# In scoring loop:
luck_score *= confidence_scale(row["PA"])
```

---

## 9. Methodology Notes

- **Data source:** Baseball Savant via pybaseball. All Statcast data is pitch-level;
  per-batter metrics are aggregated from at-bat-ending events.
- **April window:** From Opening Day (varies by year) through April 30. Short sample
  means individual rate stats are noisy; the model aggregates across five metrics
  to reduce noise.
- **Validation window:** May 1 through July 31 (92 days). This is long enough to
  stabilize most rate stats while remaining within a season (avoiding roster-change
  confounds from trades).
- **Qualification thresholds:** 50 April PA and 100 May-July PA. Below these thresholds
  rate stats are too volatile for meaningful regression measurement.
- **Correlation target:** Pearson r with delta wOBA. wOBA is the most comprehensive
  single offensive metric, capturing walks, singles, extra-base hits, and HR in a
  single run-value-weighted number. delta wOBA (May-Jul wOBA minus April wOBA) measures
  raw performance change, not regression-to-mean; luck-driven players should show
  a stronger positive delta than non-luck-driven ones.
- **Grid search coverage:** Weight combinations are tested exhaustively within the
  defined grid. The optimal in-sample weights may overfit to the two years tested;
  they should be validated against held-out seasons before permanent adoption.

---

*Report generated by `backtest_analyze.py` . Fantasy Baseball Statcast Pipeline*
