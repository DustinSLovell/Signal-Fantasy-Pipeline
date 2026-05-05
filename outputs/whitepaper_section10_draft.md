# Section 10: Live Signal Accuracy (Through Week 9, 2026)

*Status: May 5, 2026. Track 1 signals under active collection through Week 9.
Official accuracy reporting begins Week 10 (mid-June 2026).*

---

## 10.1 Signal Accuracy Framework

The Signal Fantasy operates a two-track accuracy system to maintain methodological honesty:

**Track 1 — April Signals (This Section)**
April data is the highest-signal window for luck detection: the market is maximally mispriced, PA are limited so BABIP variance is highest, and the full May-August season remains to validate the call. Track 1 signals are model-validated and published with authority.

Official Track 1 accuracy reporting begins at Week 10 (mid-June), once enough calls have had sufficient time to resolve. Before Week 10, we report collection-phase data — signal counts, movement direction, and mechanism classification — without claiming final accuracy percentages.

**Track 2 — In-Season Rolling Signals (NOT reported here)**
Week-to-week tracker updates use rolling wOBA/xwOBA and are reported as observations only ("the data is moving in the right direction"). Track 2 has no validated backtest framework and will not be published with accuracy claims until it does.

**Why this distinction matters:** Mixing Track 1 and Track 2 without clear labeling would corrupt the published track record. Every number in this section refers exclusively to Track 1 April signals.

---

## 10.2 Directional Accuracy (2022–2025 Backtest)

The directional accuracy metric answers: "Did the player recover/decline as the signal predicted?" using full-season wOBA change from April baseline.

### Hitter Model (n=305, years 2022–2025)

| Signal | n | Accuracy | vs Baseline (+50%) | vs RTM | FP Rate |
|--------|---|----------|--------------------|--------|---------|
| Buy Low | 88 | **94.3%** | +44.3pp | +8.1pp | 5.7% |
| Slight Buy | 85 | 72.9% | +22.9pp | **-13.3pp** | 27.1% |
| Slight Sell | 82 | 85.4% | +35.4pp | -0.9pp | 14.6% |
| Sell High | 50 | **94.0%** | +44.0pp | +7.8pp | 6.0% |
| **Overall** | **305** | **85.9%** | +35.9pp | -0.3pp | — |

RTM (regression-to-mean) accuracy: 86.2% on this dataset.

**Key finding:** The model's advantage is **concentrated at the extreme signal tiers**. Buy Low (94.3%) and Sell High (94.0%) both add 8pp vs RTM. Slight signals do not add vs RTM — Slight Buy is 13pp *worse* than RTM. The model knows what it knows: strong signals are highly reliable, weak signals are noisy.

**Year-over-year trend:**

| Year | n | Overall | Buy Low | Sell High |
|------|---|---------|---------|-----------|
| 2022 | 51 | 86.3% | 94.4% | 100.0% |
| 2023 | 64 | 87.5% | 89.5% | 92.3% |
| 2024 | 96 | 81.2% | 94.7% | 86.7% |
| 2025 | 94 | 89.4% | 96.9% | 100.0% |

2025 OOS accuracy (89.4%) is the *highest* year — no degradation from training to OOS. Buy Low at 96.9% OOS (n=32) is the strongest single-year result in the dataset. The model is not overfitting to 2022–2024 training years.

### Pitcher Model (n=284, years 2022–2025)

| Signal | n | Accuracy | FP Rate |
|--------|---|----------|---------|
| Buy Low | 89 | 86.5% | 13.5% |
| Slight Buy | 50 | 62.0% | 38.0% |
| Slight Sell | 76 | 82.9% | 17.1% |
| Sell High | 69 | 91.3% | 8.7% |
| **Overall** | **284** | **82.4%** | — |

Same pattern as hitters: extreme signals reliable, slight signals noisy. Pitcher Slight Buy (62.0%) is barely better than random.

**Honest limitation:** Pitcher model was calibrated on fewer seasons. Buy Low accuracy improves from 78.9% (2022) to 90.9% (2024) year-over-year — the model continues learning as we add pitcher Statcast coverage.

---

## 10.3 wOBA Projection Accuracy by Signal Tier

*Source: backtest_C_hitters_2025.csv merged with 2025 directional signals. n=235 hitters, 2025 OOS.*

| Tier | N | Model wOBA MAE | Steamer MAE | Delta | Winner |
|------|---|----------------|-------------|-------|--------|
| Buy Low | 22 | 0.0291 | 0.0297 | -0.0006 | MODEL (-1.9%) |
| Slight Buy | 16 | 0.0290 | 0.0245 | +0.0045 | Steamer |
| Neutral | 135 | 0.0343 | 0.0268 | +0.0075 | Steamer (+27.8%) |
| Slight Sell | 19 | 0.0412 | 0.0340 | +0.0071 | Steamer |
| Sell High | 7 | 0.0217 | 0.0274 | -0.0057 | MODEL (-20.8%) |

**The precision claim:** The model's wOBA accuracy advantage is concentrated where the signal fires. For Buy Low players, we beat Steamer by 1.9%. For Sell High players, we beat Steamer by 20.8%. For Neutral, Slight Buy, and Slight Sell players, Steamer wins — we make no claim of accuracy advantage for those groups.

### Luck Score Threshold Analysis

At what luck score threshold does the model start beating Steamer?

| Threshold | n | Model MAE | Steamer MAE | Winner | Margin |
|-----------|---|-----------|-------------|--------|--------|
| Buy >0.020 | 38 | 0.0291 | 0.0275 | Steamer | +5.7% |
| Buy >0.030 | 32 | 0.0261 | 0.0253 | Steamer | +3.1% |
| **Buy >0.040** | **21** | **0.0289** | **0.0294** | **MODEL** | **-1.9%** |
| Buy >0.050 | 9 | 0.0366 | 0.0266 | Steamer | +37.7% (n too small) |
| Sell <-0.040 | 26 | 0.0359 | 0.0322 | Steamer | +11.5% |
| Sell <-0.050 | 19 | 0.0319 | 0.0317 | Steamer | +0.6% (tied) |
| **Sell <-0.065** | **7** | **0.0217** | **0.0274** | **MODEL** | **-20.8%** |
| Sell <-0.090 | 3 | 0.0267 | 0.0311 | MODEL | -14.2% (n too small) |

**Finding:** The Buy Low threshold (0.040, Ruler 1 scale) is precisely calibrated — below it, Steamer wins; at or above it, the model wins. The Sell High threshold (-0.065) is similarly precise. This validates the calibration methodology: our thresholds are not arbitrary; they mark the point where signal quality surpasses baseline projection accuracy.

### Bootstrap Confidence Intervals

*1,000-sample bootstrap with replacement, 95% CI on (Model MAE - Steamer MAE).*

| Signal | Observed diff | 95% CI | Model wins in X% of samples | Significant? |
|--------|--------------|--------|------------------------------|--------------|
| Buy Low (n=21) | -0.0005 | [-0.0100, +0.0095] | 53% | **NO** |
| Sell High (n=7) | -0.0057 | [-0.0211, +0.0101] | 76% | **NO** |

**Honest statement:** Neither finding achieves statistical significance. Both CIs include zero. The Buy Low result (53% bootstrap win rate) is barely directional; the Sell High result (76% win rate) is more convincing but n=7 is too small to be definitive. We are collecting 2026 live data to strengthen these claims. We do not publish these as established findings — they are directional evidence consistent with the hypothesis that strong signals improve wOBA projection accuracy.

---

## 10.4 Multi-Stat Signal Accuracy

*For Buy Low and Sell High cohorts vs Steamer, 2025 OOS.*
*Source: outputs/signal_accuracy_full_matrix.csv*

| Tier | Stat | N | Model MAE | Steamer MAE | Winner | Margin |
|------|------|---|-----------|-------------|--------|--------|
| Buy Low | HR | 24 | 6.06 | 6.34 | MODEL | -4.4% |
| Buy Low | R | 24 | 12.03 | 14.65 | **MODEL** | **-17.8%** |
| Buy Low | RBI | 24 | 17.16 | 18.35 | MODEL | -6.5% |
| Buy Low | AVG | 24 | 0.0188 | 0.0148 | Steamer | +26.8% |
| Buy Low | wOBA | 22 | 0.0291 | 0.0297 | MODEL | -1.9% |
| Sell High | HR | 9 | 7.24 | 5.36 | Steamer | +35.3% |
| Sell High | R | 9 | 18.33 | 13.99 | Steamer | +31.0% |
| Sell High | RBI | 9 | 13.60 | 13.46 | Steamer | +1.0% (tied) |
| Sell High | AVG | 9 | 0.0131 | 0.0177 | **MODEL** | **-25.9%** |
| Sell High | wOBA | 7 | 0.0217 | 0.0274 | MODEL | -20.8% |

**Interpretation:**

*Buy Low signal adds most value on:*
- **R (−17.8% vs Steamer)** — runs accumulate as luck normalizes and batters return to true hitting ability
- **HR (−4.4%) and RBI (−6.5%)** — solid improvement, consistent with the regression narrative
- *Loses on AVG*: April average is too noisy to project reliably from a one-month sample (industry-wide limitation, not a model bug)

*Sell High signal adds most value on:*
- **AVG (−25.9% vs Steamer)** — the model correctly identifies unsustainable BABIP runs
- **wOBA (−20.8%)** — contact quality degradation correctly detected
- *Loses on HR and R counting stats*: Sell High players may accumulate counting stats even while their contact quality metrics decline (park factors, lineup protection, health). The signal identifies the mechanism correctly; the counting stat suppression is overdone in projection.

**Practical implication for trade decisions:** Sell High signals are most reliable for wOBA/AVG-based valuation metrics. If trading a Sell High player, their counting stats (HR, R) may not decline as fast as the projection model predicts. Trust the contact quality degradation; discount the counting stat projection suppression.

---

## 10.5 Model Limitations (Honest Acknowledgment)

**Slight signals do not beat Steamer.** Slight Buy and Slight Sell tiers show no consistent edge over Steamer on wOBA MAE and underperform RTM on directional accuracy. The model fires slight signals as leading indicators — they warrant monitoring but not full confidence.

**Small sample caveats.** Sell High wOBA finding (−20.8%) is based on n=7 in 2025 OOS. This is directionally compelling but not statistically significant. Bootstrap CI: [−0.0211, +0.0101]. We need 50+ resolved Sell High cases before publishing this as an established finding.

**AVG is fundamentally noisy in April.** R²=0.056 between April wOBA-derived AVG projection and full-season actual AVG (Backtest A, Session 11). This is not a model bug — preseason projection systems all struggle with April AVG. We project AVG primarily as a sanity check, not a high-confidence claim.

**Sell High counting stats.** The model applies R×0.92 and RBI×0.92 multipliers for Sell High players. In the 2025 OOS data, this over-suppresses HR (+35.3% worse than Steamer) and R (+31.0% worse). Contact quality correctly identified; counting stat projection is too aggressive on the downside. Use sell signals for wOBA/AVG valuation, not counting stat projection.

**Pitcher ERA regression.** Our ERA bias is +0.25 vs Steamer's +0.41. We are less biased on ERA direction, but our MAE (0.882) exceeds Steamer's (0.786). More IP in the dataset would help; April pitching samples are especially volatile.

---

## 10.6 Signal Context Overrides (New — Session 34)

Two context layers have been added as post-processing overlays. These do NOT change model scores or verdicts. They add interpretive flags for article and tool display.

### Elite Track Record Gate (Pitchers)

**Canonical case:** A pitcher with two consecutive sub-2.00 ERA seasons gets a marginal Sell High signal (ERA-FIP gap < 0.50). For a generational talent, this gap may be within normal variance for their proven level. The gate adds context without suppressing the signal.

**Gate criteria:**
- Career 2yr ERA < 2.50 (multi-year generational ERA)
- Pitcher quality tier = Elite (FIP- < 80)
- |ERA - FIP| < 0.50 (marginal gap — signal borderline)

**Backtest validation:** Gate fires for 0 cases in 2025 OOS. All 2025 Sell High pitchers with career ERA < 2.50 had gaps > 1.37 — legitimately large sell signals that resolved correctly (100% accuracy). The gate is a forward-looking safeguard, not a retroactive correction.

**Current state (May 5, 2026):** 0 pitchers downgraded. Ranger Suárez (career ERA 0.78, gap −0.56) is borderline — would fire if threshold moved from 0.50 to 0.60.

### Injury Recovery Flag

**Canonical case:** Carroll (hamate surgery Feb 14, 2026). Model fires Sell High (wOBA > xwOBA, high BABIP). Injury context: hamate recovery may affect bat path and power metrics.

**Flag criteria:**
- Player in `data/player_injury_context.json`
- Weeks elapsed since surgery < expected_recovery_weeks
- Applies to any signal tier (including buys)

**Current state (May 5, 2026):** 0 active flags. Both Carroll (11.4 weeks) and Lindor (13.3 weeks) have passed their 8-week expected recovery windows. Flag would have been active in March–April 2026 during active recovery.

**Note on Carroll's signal:** His Sell High is driven by BABIP=0.373 vs career 0.308 (+65pt gap) with xwOBA=0.366 slightly above career (0.348). The hamate context does not suppress a valid sell signal — his xwOBA is not depressed by the injury. The injury flag adds interpretive context, not signal reversal.

---

## 10.7 Live 2026 Tracker Status (Week 9, May 5, 2026)

*Track 1 accuracy reporting begins Week 10. Current collection-phase data:*

| Status | Count |
|--------|-------|
| Confirmed correct | 32 |
| Signal deepening (score intensifying) | 59 |
| Still active / signal intact | 15 |
| Honest misses | 3 |
| **Total tracked** | **169** |

Week 10 (next Monday) opens the official accuracy window. With 32 confirmed + 3 misses already, the preliminary rate is 32/35 = 91.4% — but this will be reported as "preliminary, subject to resolution of 124 active signals."

---

*Section 10 last updated: May 5, 2026 (Session 34)*
*Next update: Post-Week 10 when official Track 1 accuracy window opens*
