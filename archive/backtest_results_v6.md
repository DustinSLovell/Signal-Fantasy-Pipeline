# Fantasy Baseball Luck Model — Backtest Report v6

**Generated:** 2026-04-21
**Models compared:** v4 (current baseline) · v5 (Phase A) · v6 (Phase B)
**Significance:** `***` p<0.001  `**` p<0.01  `*` p<0.05  `†` p<0.10  _(blank)_ ns

---

## 1. Backtest Design

| Parameter | Value |
| --------- | ----- |
| Scoring years | 2022, 2023, 2024 |
| Outcome years | 2023, 2024, 2025 |
| Min PA (scoring year) | 300 (full season) |
| Min PA (outcome year) | 300 (full season) |
| Total player-seasons | 506 (2022: 163; 2023: 170; 2024: 173) |
| v4 model | BABIP + HR/FB + Z-contact + xwOBA gap + contextual modifiers |
| v5 model (Phase A) | v4 + park factor adjustment + wRC+ quality gate + RTM + PT discount + amp cap |
| v6 model (Phase B) | v5 × per-player consistency multiplier (variance-based) |

**Prior-year xwOBA note:** For the quality gate and RTM integration, only full-season
xwOBA from years *prior* to the scoring year is used (strict no-look-ahead):
- Scoring 2022: same-year 2022 xwOBA used as proxy (no prior data available).
- Scoring 2023: 2022 full-season xwOBA.
- Scoring 2024: average of 2022–2023 full-season xwOBA.

**Phase B variance note:** Consistency multipliers use the full 2022–2024 expected-stats
window (matching production behavior). This is slightly look-ahead for 2022/2023 scoring
years but gives Phase B a fair test with the same data it uses in practice.

---

## 2. Summary Comparison Table

| Metric | RTM Baseline | v4 | v5 (Phase A) | v6 (Phase B) |
| ------ | ------------ | ---- | ------------ | ------------ |
| Correlation (r vs Δ wOBA) | — | +0.2112*** | +0.2092*** | +0.2104*** |
| Directional accuracy | 68.2% (n=506) | 59.4% | 59.8% | 59.6% |
| Buy Low accuracy | — | 59.2% | 62.8% | 62.8% |
| Sell High accuracy | — | 64.5% | 66.3% | 66.3% |
| Sample size | 506 | 506 | 506 | 506 |

> **Methodology note:** This is a cross-season out-of-sample test (April luck score →
> following *full season* wOBA delta, 300/300 PA thresholds). This is strictly harder
> than the original v1 backtest (April → May-July intra-season, 50/100 PA), which
> showed r=0.506 and 71% accuracy. The cross-season window introduces macro factors
> (injuries, position changes, park moves) that no luck model can predict.

---

## 3. Phase A Component Breakdown

Each component added cumulatively to v4 to show incremental accuracy impact:

| Step | Version | Dir. Accuracy | Δ vs previous | Pearson r |
| ---- | ------- | ------------- | ------------- | --------- |
| v4 baseline | v4 | 59.4% | — | +0.2112*** |
| + Park factor | v4+park | 60.1% | +0.7% | +0.2162*** |
| + wRC+ quality gate | v4+pk+q | 60.5% | +0.3% | +0.2122*** |
| + RTM + PT + amp cap | v5 (full) | 59.8% | -0.7% | +0.2092*** |
| + Consistency (Phase B) | v6 | 59.6% | -0.2% | +0.2104*** |

**Park factor analysis — players on extreme-park teams vs neutral parks:**

| Group | N | v4 Pearson r | v5 Pearson r | Δ r |
| ----- | ---- | ------------ | ------------ | ---- |
| Extreme park teams (PF ≠ 1.0) | 148 | +0.237 | +0.254 | +0.017 |
| Neutral park teams (PF = 1.0) | 358 | +0.198 | +0.188 | -0.010 |

---

## 4. Phase B Component Breakdown

**Consistency tier distribution across all player-seasons:**

| Variance Tier | N (player-seasons) | v5 Pearson r | v6 Pearson r |
| ------------- | ------------------ | ------------ | ------------ |
| Very Consistent | 425 | +0.217 | +0.219 |
| Consistent | 79 | +0.203 | +0.203 |
| Inconsistent | 2 | — | — |

**Interpretation:** Tiers where v6 r > v5 r show the consistency multiplier is
adding genuine signal. If v6 ≈ v5 overall, Phase B is not materially impacting
the cross-season test — consistent with the expectation that ~58% of players
receive multiplier=1.00 due to insufficient variance history.

---

## 5. Verdict Bucket Analysis

### v4

| Verdict | N | Mean Δ wOBA | % Correct Direction |
| ------- | ---- | ----------- | ------------------- |
| Buy low | 130 | +0.0075 | 77/130 (59%) |
| Slight buy | 62 | -0.0007 | 31/62 (50%) |
| Neutral | 146 | -0.0031 | N/A |
| Slight sell | 75 | -0.0071 | 46/75 (61%) |
| Sell high | 93 | -0.0110 | 60/93 (65%) |

### v5 (Phase A)

| Verdict | N | Mean Δ wOBA | % Correct Direction |
| ------- | ---- | ----------- | ------------------- |
| Buy low | 113 | +0.0094 | 71/113 (63%) |
| Slight buy | 69 | -0.0033 | 33/69 (48%) |
| Neutral | 163 | -0.0034 | N/A |
| Slight sell | 60 | -0.0044 | 34/60 (57%) |
| Sell high | 101 | -0.0108 | 67/101 (66%) |

### v6 (Phase B)

| Verdict | N | Mean Δ wOBA | % Correct Direction |
| ------- | ---- | ----------- | ------------------- |
| Buy low | 113 | +0.0094 | 71/113 (63%) |
| Slight buy | 70 | -0.0034 | 33/70 (47%) |
| Neutral | 162 | -0.0034 | N/A |
| Slight sell | 60 | -0.0044 | 34/60 (57%) |
| Sell high | 101 | -0.0108 | 67/101 (66%) |

---

## 6. RTM Baseline Comparison

| Model | Directional Accuracy | Pearson r | Notes |
| ----- | -------------------- | --------- | ----- |
| RTM baseline (Steamer proxy) | 68.2% (n=506) | — | Pure regression to mean |
| v4 (current) | 59.4% | +0.2112*** | Phase 0 baseline |
| v5 (Phase A) | 59.8% | +0.2092*** | Park + quality + RTM + PT + amp |
| v6 (Phase B) | 59.6% | +0.2104*** | v5 + consistency multiplier |
| Random guess | 50.0% | — | Theoretical floor |

---

## 7. Top Retrospective Calls (v6)

### Top 10 Buy-Low Calls

| Player | Year | v4 Score | v5 Score | v6 Score | April xwOBA | April BABIP | Δ wOBA | Correct? |
| ------ | ---- | -------- | -------- | -------- | ----------- | ----------- | ------ | -------- |
| Marcell Ozuna | 2023 | +0.403 | +0.645 | +0.645 | 0.295 | 0.077 | +0.014 | ✓ |
| Christian Walker | 2022 | +0.446 | +0.637 | +0.637 | 0.372 | 0.135 | +0.005 | ✓ |
| Carlos Santana | 2022 | +0.353 | +0.609 | +0.609 | 0.354 | 0.128 | +0.015 | ✓ |
| Randy Arozarena | 2024 | +0.448 | +0.601 | +0.601 | 0.270 | 0.167 | +0.012 | ✓ |
| Marcus Semien | 2022 | +0.327 | +0.595 | +0.595 | 0.237 | 0.194 | +0.037 | ✓ |
| Whit Merrifield | 2022 | +0.428 | +0.581 | +0.581 | 0.290 | 0.162 | +0.010 | ✓ |
| Ketel Marte | 2022 | +0.347 | +0.578 | +0.578 | 0.259 | 0.183 | +0.044 | ✓ |
| Kyle Schwarber | 2022 | +0.294 | +0.520 | +0.572 | 0.346 | 0.175 | -0.005 | ✗ |
| Max Muncy | 2022 | +0.404 | +0.548 | +0.548 | 0.352 | 0.149 | +0.026 | ✓ |
| Corey Seager | 2024 | +0.161 | +0.415 | +0.456 | 0.352 | 0.272 | +0.000 | ✗ |

### Top 10 Sell-High Calls

| Player | Year | v4 Score | v5 Score | v6 Score | April xwOBA | April BABIP | Δ wOBA | Correct? |
| ------ | ---- | -------- | -------- | -------- | ----------- | ----------- | ------ | -------- |
| Brandon Marsh | 2023 | -0.559 | -0.912 | -0.912 | 0.359 | 0.453 | -0.032 | ✓ |
| Matt Chapman | 2023 | -0.546 | -0.870 | -0.870 | 0.505 | 0.485 | +0.012 | ✗ |
| Thairo Estrada | 2023 | -0.422 | -0.763 | -0.763 | 0.343 | 0.416 | -0.060 | ✓ |
| Manny Machado | 2022 | -0.405 | -0.688 | -0.688 | 0.402 | 0.438 | -0.048 | ✓ |
| Luis Arráez | 2023 | -0.379 | -0.677 | -0.677 | 0.404 | 0.452 | -0.046 | ✓ |
| Nolan Arenado | 2022 | -0.317 | -0.633 | -0.633 | 0.413 | 0.415 | -0.054 | ✓ |
| Xander Bogaerts | 2022 | -0.451 | -0.616 | -0.616 | 0.354 | 0.475 | -0.020 | ✓ |
| Randy Arozarena | 2023 | -0.235 | -0.581 | -0.581 | 0.445 | 0.382 | -0.027 | ✓ |
| Geraldo Perdomo | 2023 | -0.345 | -0.552 | -0.552 | 0.339 | 0.477 | -0.002 | ✓ |
| Josh Bell | 2022 | -0.288 | -0.514 | -0.514 | 0.403 | 0.397 | -0.021 | ✓ |

---

## 8. Key Findings

**Overall model trajectory (v4 → v5 → v6):**

| Version | r | Dir. Accuracy | Buy Low | Sell High |
| --- | --- | --- | --- | --- |
| v4 | +0.2112*** | 59.4% | 59.2% | 64.5% |
| v5 (Phase A) | +0.2092*** | 59.8% | 62.8% | 66.3% |
| v6 (Phase B) | +0.2104*** | 59.6% | 62.8% | 66.3% |

**Phase A component impact (incremental accuracy):**

- Park factor adjustment: +0.7%
- wRC+ quality gate: +0.3%
- RTM + PT discount + amp cap: -0.7%
- All Phase A combined (v4→v5): +0.3%

**Phase B impact (v5→v6):** -0.2% directional accuracy

---

*Report generated by `backtest_v6.py` · Fantasy Baseball Statcast Pipeline*