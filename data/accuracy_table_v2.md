# Signal Model Accuracy Tables — v2 Backtest
*Generated: April 25, 2026 | Composite Version E (production-aligned)*
*Pitcher model: 3-mismatch alignment fix applied (conf-scaled ls, ERA 4.00 SB gate, qual-first)*

---

## Hitter Model (score_luck.py — recalibrated April 23, 2026)

| Signal | 2022 | 2023 | 2024 | 2025 | 4-Yr Avg | Avg wOBA Δ |
|--------|------|------|------|------|----------|------------|
| Buy Low | 91.4% (n=35) | 85.7% (n=42) | 93.8% (n=48) | 96.5% (n=57) | 92.3% | +0.068 |
| Slight Buy | 50.0% (n=2) | 66.7% (n=6) | 54.5% (n=11) | 87.5% (n=8) | 66.7% | +0.053 |
| Slight Sell | 75.0% (n=8) | 81.8% (n=11) | 73.3% (n=15) | 82.4% (n=17) | 78.4% | -0.055 |
| Sell High | 100.0% (n=14) | 91.4% (n=35) | 88.1% (n=42) | 93.8% (n=32) | 91.9% | -0.083 |
| **Overall** | **89.8% (n=59)** | **86.2% (n=94)** | **85.3% (n=116)** | **93.0% (n=114)** | **88.5%** | — |
| vs RTM | +19.8pp | +16.2pp | +15.3pp | +23.0pp | **+18.5pp** | — |

> **Note:** CLAUDE.md published Buy Low ~98.0%. That figure reflects the 2026 live track record
> (April 22 forward), not this 4-year backtest. The backtest Buy Low of 92.3% is the correct
> historical figure for the 2022–2025 period with recalibrated thresholds applied retroactively.

---

## Pitcher Model v2.0 (score_pitcher_luck.py — split architecture, April 23, 2026)
*Composite Version E: BUY = ERA-FIP dominant (×0.60/×0.25/×0.15) | SELL = 8-component composite*
*Production-aligned: confidence-scaled luck_score thresholds, ERA >= 4.00 Slight Buy gate, qual-before-ERA ordering*

| Signal | 2022 | 2023 | 2024 | 2025 | 4-Yr Avg | Avg ERA Δ |
|--------|------|------|------|------|----------|-----------|
| Buy Low | 100.0% (n=2) | 100.0% (n=4) | 76.9% (n=13) | 72.7% (n=11) | 80.0% | -1.96 |
| Slight Buy | — | 100.0% (n=1) | 100.0% (n=2) | 100.0% (n=1) | 100.0% | -1.18 |
| Slight Sell | 100.0% (n=5) | 66.7% (n=6) | 100.0% (n=2) | 83.3% (n=6) | 84.2% | +1.98 |
| Sell High | 97.0% (n=33) | 96.0% (n=25) | 95.2% (n=42) | 89.7% (n=29) | 94.6% | +2.12 |
| **Overall** | **97.5% (n=40)** | **91.7% (n=36)** | **91.5% (n=59)** | **85.1% (n=47)** | **91.2%** | — |
| vs RTM | +27.5pp | +21.7pp | +21.5pp | +15.1pp | **+21.2pp** | — |

> **Note on Slight Buy n=4:** Small sample — 100% accuracy is not statistically robust vs the
> ~84% target. CLAUDE.md published figure of 84.4% reflects the v7 backtest with different
> (pre-mismatch-fix) classification logic. The 3-mismatch alignment changed which pitchers are
> classified as Slight Buy, producing a different (smaller) cohort.

---

## Before / After — Pitcher Model Alignment Fix

| Signal | Before (Version E pre-fix) | After (Version E aligned) | Delta |
|--------|---------------------------|--------------------------|-------|
| Buy Low | 82.1% | 80.0% | -2.1pp |
| Slight Buy | ~84% (n=4, different cohort) | 100.0% (n=4) | +16pp |
| Slight Sell | 84.2% | 84.2% | 0pp |
| Sell High | 94.6% | 94.6% | 0pp |
| **Overall** | **91.1%** | **91.2%** | **+0.1pp** |
| vs RTM | +21.1pp | +21.2pp | +0.1pp |

*Sell High and Overall are preserved within rounding. Buy Low -2.1pp is within acceptable range
given the 3 gate-ordering changes and small total n=30 over 4 years.*

---

## Open Fix — Pitcher Buy Low ERA Ceiling

Per CLAUDE.md: ERA < 3.75 should suppress Buy Low to Neutral.
- Accuracy when ERA < 3.75: 29.6% | when ERA >= 3.75: 89.3%
- Estimated gain: +5.5pp overall pitcher accuracy (91.2% → ~96.7% projected)
- **Not yet implemented.** Add ERA gate in `_assign_verdict_prescore()` in score_pitcher_luck.py.
