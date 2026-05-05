"""
config.py — Signal Fantasy threshold configuration
===================================================
Single source of truth for all verdict thresholds and modifier constants.

Two separate measurement systems — both valid, different purposes:

  PRODUCTION thresholds (score_luck.py, score_pitcher_luck.py):
    Calibrated to full-season pipeline output — full PA window, 4-component
    formula with modifiers. Scores regularly exceed ±0.150.

  BACKTEST thresholds (backtest_multi_year_v7.py):
    Calibrated to April-only simplified formula (xwoba_gap*0.60 + babip_luck*0.40).
    Score distribution peaks at 0.080-0.120. These thresholds select equivalent
    high-confidence tiers from that smaller distribution.
    NOT numerically comparable to production thresholds.

Both sets correctly identify "high confidence" signals from their respective
score distributions. Use backtest numbers for signal direction validation and
A vs B comparisons only. Use production numbers for live decisions and publishing.

Canonical accuracy (backtest v7): 91.9% train (2022-2024) | TBD OOS (Session 35 — post SB elimination + BL raise)

MODIFIER ARCHITECTURE — Version D (additive, April 26 2026):
  All hitter buy signal modifiers use flat additive penalties subtracted from
  luck_score. Empirically calibrated via sensitivity sweep on backtest training
  data (2022-2024). Penalties independently optimized per flag.
  Version D: train=86.1% (+1.7pp vs A) | OOS=89.7% (+0.3pp) | 42 verdict changes
"""

# ── Production hitter thresholds (score_luck.py) ─────────────────────────────
# Session 35: Slight Buy eliminated (72.9% accuracy, -13.3pp vs RTM = no edge).
# H_PROD_SLIGHT_BUY set equal to H_PROD_BUY_LOW so the SB condition can never fire.
# H_PROD_BUY_LOW raised 0.150→0.175 to drop the noisy 0.150-0.175 borderline cases.
# Backtest result: 91.9% overall (+6.0pp vs 85.9% baseline, +5.7pp vs RTM 86.2%).
H_PROD_BUY_LOW      =  0.175
H_PROD_SLIGHT_BUY   =  0.175  # = H_PROD_BUY_LOW — Slight Buy tier eliminated
H_PROD_SELL_HIGH    = -0.150
H_PROD_SLIGHT_SELL  = -0.085

# Slight Buy confidence gates — both must pass for Slight Buy to survive.
# Gate 1: xwOBA gap too small = BABIP-only signal, no contact quality support
# Gate 2: high xwOBA hitters have limited regression upside
H_PROD_SB_MIN_XWOBA_GAP = 0.030
H_PROD_SB_MAX_XWOBA     = 0.380

# ── Production pitcher thresholds (score_pitcher_luck.py) ────────────────────
P_PROD_BUY_LOW      =  0.15
P_PROD_SLIGHT_BUY   =  0.07
P_PROD_SELL_HIGH    = -0.15
P_PROD_SLIGHT_SELL  = -0.07

# ── Backtest hitter thresholds (backtest_multi_year_v7.py) ───────────────────
# Calibrated to April-only formula. Score range: ~0.010–0.100.
# Select the same relative confidence tiers as production, different scale.
H_BT_BUY_LOW        =  0.045  # raised from 0.040 (drops noisy 0.040-0.045 bucket, 82.6% acc)
H_BT_SLIGHT_BUY     =  0.045  # = H_BT_BUY_LOW — Slight Buy tier eliminated in backtest
H_BT_SELL_HIGH      = -0.065
H_BT_SLIGHT_SELL    = -0.040

# ── Backtest pitcher thresholds (backtest_multi_year_v7.py) ──────────────────
# ERA-FIP gap scale — entirely different from production luck score scale.
P_BT_BUY_LOW        =  1.20
P_BT_SLIGHT_BUY     =  0.60
P_BT_SELL_HIGH      = -1.20
P_BT_SLIGHT_SELL    = -0.60

# ── Hitter buy signal additive penalties (Version D — calibrated April 26 2026) ─
# Each flag subtracts a flat penalty from luck_score for buy signals only.
# Calibrated via sensitivity sweep on backtest training data 2022-2024.
# H_SPEED_PENALTY and H_CHASE_PENALTY match nearest calibrated analogue.
# Combined dampening capped at H_MAX_COMBINED_PEN regardless of flag count.
H_KP_K_PENALTY      = 0.010   # K-rate spike (strikeout contact deterioration)
H_KP_PULL_PENALTY   = 0.008   # Pull-rate drop (approach/shift adaptation)
H_HH_PENALTY        = 0.012   # Hard-hit rate drop (power/contact quality loss)
H_SPEED_PENALTY     = 0.010   # Sprint speed cliff >0.3 ft/s YoY (aging signal)
H_CHASE_PENALTY     = 0.008   # Chase rate rise >3pp (swing decision worsening)
H_MAX_COMBINED_PEN  = 0.040   # Hard cap on total additive dampening per player
# AGE WEIGHTS — estimated priors, not empirically calibrated. Young hitters (≤25)
# often post chase-rate spikes as part of normal development, not true regression.
# Need 2+ full seasons of contract-year data before reliable calibration.
H_CHASE_AGE_WEIGHT_U25    = 0.40   # age ≤25: 60% reduction (development noise)
H_CHASE_AGE_WEIGHT_26_27  = 0.70   # age 26-27: 30% reduction (still maturing)

# ── CBS FPTS Category Weights (trade_analyzer.py) ────────────────────────────
# Derived from Ridge regression on CBS Fantasy Baseball full-season data.
# Source: build_cbs_fpts.py | Train: 2024 (n=307/84) | OOS: 2025
# OOS R²: hitters=0.983, pitchers=0.909 — both pass ≥0.85 guard.
#
# MULTICOLLINEARITY NOTE:
#   Hitters: R/HR/RBI are correlated. Ridge stabilizes coefficients but HR
#   marginal coef (~0.43) reflects value BEYOND correlated R/RBI contribution.
#   For FPTS prediction the combined model is accurate; do not interpret
#   individual coefs as "CBS points per HR".
#   Pitchers: ERA/WHIP are correlated. Same caveat applies.
#
# USAGE: FPTS_projected = sum(stat * coef) + intercept
#   e.g. hitter: R*2.807 + HR*0.430 + RBI*2.081 + SB*1.422 + AVG*227.4 - 53.0
#   e.g. pitcher: W*10.540 + ERA*(-2.553) + WHIP*(-90.770) + K*1.324 + SV*6.328 + 122.7

# Hitters
CBS_H_COEF_R          = 2.8067    # per run scored
CBS_H_COEF_HR         = 0.4303    # per home run (marginal, after R/RBI collinearity)
CBS_H_COEF_RBI        = 2.0806    # per RBI
CBS_H_COEF_SB         = 1.4222    # per stolen base
CBS_H_COEF_AVG        = 227.3683  # per 1.000 batting avg (i.e. AVG as decimal)
CBS_H_INTERCEPT       = -53.0439
CBS_H_R2_TRAIN        = 0.9853    # train 2024
CBS_H_R2_OOS          = 0.9830    # OOS 2025

# Pitchers
CBS_P_COEF_W          = 10.5398   # per win
CBS_P_COEF_ERA        = -2.5531   # per ERA point (negative: higher ERA = lower FPTS)
CBS_P_COEF_WHIP       = -90.7701  # per WHIP point (negative: higher WHIP = lower FPTS)
CBS_P_COEF_K          = 1.3236    # per strikeout
CBS_P_COEF_SV         = 6.3282    # per save
CBS_P_INTERCEPT       = 122.7395
CBS_P_R2_TRAIN        = 0.9267    # train 2024
CBS_P_R2_OOS          = 0.9093    # OOS 2025
