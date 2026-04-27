"""
backtest_analyze.py

Reads backtest_raw.csv (produced by backtest_april.py) and runs a full
analysis of the hitter luck model's predictive power.

Analysis steps:
  1. Correlation analysis — April luck score vs May-July performance delta
  2. Verdict accuracy — did buy-low / sell-high calls resolve correctly?
  3. Individual metric importance — which April metric predicts May-July best?
  4. Weight optimization — grid search over weight space to find the combination
     that produces the highest correlation with May-July wOBA delta
  5. xwOBA / xBA gap augmentation — test whether adding estimator-gap components
     improves the model

Outputs:
  backtest_results.csv  — per-player outcomes with prediction accuracy flags
  backtest_report.md    — narrative findings, tables, and recommended changes

Usage:
    python backtest_analyze.py
    (run backtest_april.py first to generate backtest_raw.csv)
"""

import itertools
import os
import textwrap
from datetime import date

import numpy as np
import pandas as pd

try:
    from scipy import stats as scipy_stats
except ImportError:
    raise SystemExit("scipy not found. Run: pip install scipy")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
INPUT_PATH   = os.path.join(BASE_DIR, "backtest_raw.csv")
RESULTS_PATH = os.path.join(BASE_DIR, "backtest_results.csv")
REPORT_PATH  = os.path.join(BASE_DIR, "backtest_report.md")

# ---------------------------------------------------------------------------
# Current model weights — (column, league_avg, weight)
# ---------------------------------------------------------------------------
MIN_APRIL_PA    = 50
MIN_MAY_JULY_PA = 100

CURRENT_COMPONENTS = [
    ("apr_BABIP",          0.300,  -5.000,  "BABIP"),
    ("apr_hr_fb_rate",     0.145,  -0.040,  "HR/FB"),
    ("apr_hard_hit_rate",  0.390,   0.025,  "Hard-hit rate"),
    ("apr_barrel_rate",    0.080,   0.030,  "Barrel rate"),
    ("apr_z_contact_rate", 0.880,  -0.010,  "Z-contact rate"),
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def pearson(x: pd.Series, y: pd.Series):
    """Pearson r, p-value on paired non-null rows."""
    mask = x.notna() & y.notna()
    if mask.sum() < 5:
        return float("nan"), float("nan"), 0
    r, p = scipy_stats.pearsonr(x[mask], y[mask])
    return r, p, mask.sum()


def spearman(x: pd.Series, y: pd.Series):
    mask = x.notna() & y.notna()
    if mask.sum() < 5:
        return float("nan"), float("nan"), 0
    r, p = scipy_stats.spearmanr(x[mask], y[mask])
    return r, p, mask.sum()


def pct(n, total):
    return f"{n}/{total} ({100*n/total:.0f}%)" if total > 0 else "—"


def stars(p):
    """Significance stars for p-value."""
    if p < 0.001:
        return "***"
    if p < 0.01:
        return "**"
    if p < 0.05:
        return "*"
    if p < 0.10:
        return "†"
    return ""


def md_table(headers: list, rows: list) -> str:
    """Build a Markdown table string."""
    sep = ["-" * max(len(h), 4) for h in headers]
    lines = ["| " + " | ".join(headers) + " |",
             "| " + " | ".join(sep) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Luck score from arbitrary weights
# ---------------------------------------------------------------------------

def score_with_weights(df: pd.DataFrame, components: list) -> pd.Series:
    """
    components: list of (col, avg, weight, _label)
    Returns a Series of luck scores indexed like df.
    """
    score = pd.Series(0.0, index=df.index)
    for col, avg, weight, *_ in components:
        if col in df.columns:
            score += (df[col] - avg) * weight
    return score


# ---------------------------------------------------------------------------
# 1. Correlation analysis
# ---------------------------------------------------------------------------

def run_correlation_analysis(df: pd.DataFrame) -> dict:
    targets = {
        "delta_wOBA":    "delta wOBA (May-Jul minus April)",
        "delta_BABIP":   "delta BABIP (May-Jul minus April)",
        "delta_BA":      "delta BA (May-Jul minus April)",
        "delta_HR_rate": "delta HR rate (May-Jul minus April)",
    }
    results = {}
    print("\n-- Correlation: April luck_score vs May-July performance --")
    for tgt, label in targets.items():
        if tgt not in df.columns:
            continue
        pr, pp, n = pearson(df["luck_score"], df[tgt])
        sr, sp, _ = spearman(df["luck_score"], df[tgt])
        results[tgt] = {
            "label": label, "n": n,
            "pearson_r": pr, "pearson_p": pp,
            "spearman_r": sr, "spearman_p": sp,
        }
        print(f"  {label:<40}  Pearson r={pr:+.3f}{stars(pp)}  Spearman r={sr:+.3f}{stars(sp)}  n={n}")
    return results


# ---------------------------------------------------------------------------
# 2. Verdict bucket accuracy
# ---------------------------------------------------------------------------

VERDICT_ORDER = ["Buy low", "Slight buy", "Neutral", "Slight sell", "Sell high"]


def run_verdict_analysis(df: pd.DataFrame) -> dict:
    print("\n-- Verdict bucket analysis (delta_wOBA) --")
    rows = {}
    for verdict in VERDICT_ORDER:
        sub = df[df["verdict"] == verdict]
        if len(sub) == 0:
            continue
        n = len(sub)
        mean_delta = sub["delta_wOBA"].mean()
        # "Correct" direction:
        #   Buy low (unlucky) -> expect improvement -> delta_wOBA > 0
        #   Sell high (lucky) -> expect decline    -> delta_wOBA < 0
        if verdict in ("Buy low", "Slight buy"):
            n_correct = (sub["delta_wOBA"] > 0).sum()
        elif verdict in ("Sell high", "Slight sell"):
            n_correct = (sub["delta_wOBA"] < 0).sum()
        else:
            n_correct = None  # neutral has no directional expectation

        rows[verdict] = {
            "n": n,
            "mean_delta_wOBA": round(mean_delta, 4),
            "pct_correct": (n_correct / n) if n_correct is not None else None,
            "n_correct": n_correct,
        }
        direction = pct(n_correct, n) if n_correct is not None else "N/A"
        print(f"  {verdict:<14} n={n:>3}  mean deltawoba={mean_delta:+.4f}  correct dir: {direction}")
    return rows


# ---------------------------------------------------------------------------
# 3. Individual metric predictiveness
# ---------------------------------------------------------------------------

def run_metric_importance(df: pd.DataFrame) -> list:
    """Correlate each April metric deviation with May-July delta_wOBA."""
    print("\n-- Individual April metric vs delta_wOBA --")

    metrics = [
        ("apr_BABIP",          0.300,  "BABIP deviation"),
        ("apr_hr_fb_rate",     0.145,  "HR/FB deviation"),
        ("apr_hard_hit_rate",  0.390,  "Hard-hit deviation"),
        ("apr_barrel_rate",    0.080,  "Barrel rate deviation"),
        ("apr_z_contact_rate", 0.880,  "Z-contact deviation"),
        ("xwOBA_gap",          0.0,    "xwOBA gap (xwOBA - wOBA)"),
        ("xBA_gap",            0.0,    "xBA gap (xBA - BA)"),
    ]

    results = []
    for col, avg, label in metrics:
        if col not in df.columns:
            continue
        deviation = df[col] - avg if avg != 0.0 else df[col]
        pr, pp, n = pearson(deviation, df["delta_wOBA"])
        sr, sp, _ = spearman(deviation, df["delta_wOBA"])
        results.append({
            "metric": label, "col": col,
            "pearson_r": pr, "pearson_p": pp,
            "spearman_r": sr, "spearman_p": sp,
            "n": n,
        })
        print(f"  {label:<32}  Pearson r={pr:+.3f}{stars(pp)}  Spearman r={sr:+.3f}{stars(sp)}")

    results.sort(key=lambda x: abs(x["pearson_r"]) if not np.isnan(x["pearson_r"]) else 0,
                 reverse=True)
    return results


# ---------------------------------------------------------------------------
# 4. Weight optimization grid search
# ---------------------------------------------------------------------------

def run_weight_optimization(df: pd.DataFrame) -> pd.DataFrame:
    """
    Grid-search over weight multipliers for each of the 5 current components
    plus optional xwOBA_gap and xBA_gap augmentation.

    For each candidate weight set, compute luck scores and measure
    Pearson r with delta_wOBA. Report the top combinations.
    """
    print("\n-- Weight optimization grid search --")

    # Multipliers applied to current absolute weights
    # (sign is fixed; we just scale magnitude)
    babip_weights      = [-3.0, -4.0, -5.0, -6.0, -7.0, -9.0]
    hr_fb_weights      = [ 0.0, -0.02, -0.04, -0.06, -0.10, -0.15]
    hard_hit_weights   = [ 0.0,  0.015, 0.025, 0.04,  0.06,  0.10]
    barrel_weights     = [ 0.0,  0.015, 0.030, 0.05,  0.08,  0.12]
    z_contact_weights  = [ 0.0, -0.005, -0.010, -0.020, -0.030]
    xwoba_gap_weights  = [ 0.0,  0.50,  1.00,  2.00,  3.00]   # new component

    league_avgs = {
        "apr_BABIP":          0.300,
        "apr_hr_fb_rate":     0.145,
        "apr_hard_hit_rate":  0.390,
        "apr_barrel_rate":    0.080,
        "apr_z_contact_rate": 0.880,
        "xwOBA_gap":          0.0,
    }

    # Pre-compute deviations for speed
    devs = {col: df[col] - avg for col, avg in league_avgs.items() if col in df.columns}
    target = df["delta_wOBA"]

    total = (len(babip_weights) * len(hr_fb_weights) * len(hard_hit_weights) *
             len(barrel_weights) * len(z_contact_weights) * len(xwoba_gap_weights))
    print(f"  Evaluating {total:,} weight combinations ...")

    records = []
    for w_bab, w_hr, w_hh, w_bar, w_zc, w_xw in itertools.product(
        babip_weights, hr_fb_weights, hard_hit_weights,
        barrel_weights, z_contact_weights, xwoba_gap_weights
    ):
        score = pd.Series(0.0, index=df.index)
        for col, w in [
            ("apr_BABIP",          w_bab),
            ("apr_hr_fb_rate",     w_hr),
            ("apr_hard_hit_rate",  w_hh),
            ("apr_barrel_rate",    w_bar),
            ("apr_z_contact_rate", w_zc),
            ("xwOBA_gap",          w_xw),
        ]:
            if col in devs:
                score += devs[col] * w

        mask = score.notna() & target.notna()
        if mask.sum() < 10:
            continue
        r, p = scipy_stats.pearsonr(score[mask], target[mask])
        records.append({
            "pearson_r":     round(r, 4),
            "p_value":       round(p, 4),
            "n":             mask.sum(),
            "w_BABIP":       w_bab,
            "w_hr_fb":       w_hr,
            "w_hard_hit":    w_hh,
            "w_barrel":      w_bar,
            "w_z_contact":   w_zc,
            "w_xwOBA_gap":   w_xw,
        })

    grid = pd.DataFrame(records).sort_values("pearson_r", ascending=False)
    top = grid.head(10)

    print(f"\n  Top 10 weight combinations by Pearson r with delta wOBA:")
    print(f"  {'Rank':<5} {'r':>6} {'p':>7}  {'BABIP':>6} {'HR/FB':>6} {'HH%':>6} {'Barrel':>6} {'ZCon':>7} {'xwOBA_gap':>9}")
    for rank, (_, row) in enumerate(top.iterrows(), 1):
        print(f"  {rank:<5} {row.pearson_r:>+.4f} {row.p_value:>7.4f}  "
              f"{row.w_BABIP:>6.2f} {row.w_hr_fb:>6.3f} {row.w_hard_hit:>6.3f} "
              f"{row.w_barrel:>6.3f} {row.w_z_contact:>7.4f} {row.w_xwOBA_gap:>9.2f}")

    print(f"\n  Current model correlation:  ", end="")
    current_score = score_with_weights(df, CURRENT_COMPONENTS)
    mask = current_score.notna() & target.notna()
    curr_r, curr_p = scipy_stats.pearsonr(current_score[mask], target[mask])
    print(f"Pearson r={curr_r:+.4f}  p={curr_p:.4f}  n={mask.sum()}")

    return grid


# ---------------------------------------------------------------------------
# 5. Build results CSV
# ---------------------------------------------------------------------------

def build_results_csv(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    # Prediction correct flag (directional: did luck score call the right direction?)
    def correct(row):
        ls = row.get("luck_score", np.nan)
        dw = row.get("delta_wOBA", np.nan)
        if np.isnan(ls) or np.isnan(dw):
            return np.nan
        if ls > 0.05 and dw > 0:   # predicted improvement, got improvement
            return 1
        if ls < -0.05 and dw < 0:  # predicted decline, got decline
            return 1
        if abs(ls) <= 0.05:        # neutral — no directional call
            return np.nan
        return 0

    out["prediction_correct"] = out.apply(correct, axis=1)

    # Magnitude bucket
    def magnitude(ls):
        if np.isnan(ls):
            return "Unknown"
        if ls > 0.12:
            return "Strong buy"
        if ls > 0.05:
            return "Slight buy"
        if ls < -0.12:
            return "Strong sell"
        if ls < -0.05:
            return "Slight sell"
        return "Neutral"

    out["signal_strength"] = out["luck_score"].apply(magnitude)

    return out


# ---------------------------------------------------------------------------
# 6. Generate backtest_report.md
# ---------------------------------------------------------------------------

def generate_report(
    df: pd.DataFrame,
    corr: dict,
    verdicts: dict,
    metrics: list,
    grid: pd.DataFrame,
) -> str:

    today = date.today().isoformat()
    n_total  = len(df)
    n_2023   = (df["year"] == 2023).sum()
    n_2024   = (df["year"] == 2024).sum()

    # Current model correlation numbers
    curr_pr = corr.get("delta_wOBA", {}).get("pearson_r", float("nan"))
    curr_pp = corr.get("delta_wOBA", {}).get("pearson_p", float("nan"))
    curr_sr = corr.get("delta_wOBA", {}).get("spearman_r", float("nan"))
    curr_sp = corr.get("delta_wOBA", {}).get("spearman_p", float("nan"))

    # Best found weights
    best = grid.iloc[0] if len(grid) > 0 else None
    best_r = best["pearson_r"] if best is not None else float("nan")

    # Overall directional accuracy
    scored = df[df["verdict"].isin(["Buy low", "Slight buy", "Sell high", "Slight sell"])].copy()
    scored["correct"] = scored.apply(
        lambda r: (1 if ((r["luck_score"] > 0 and r["delta_wOBA"] > 0) or
                         (r["luck_score"] < 0 and r["delta_wOBA"] < 0)) else 0),
        axis=1
    )
    dir_acc = scored["correct"].mean() if len(scored) > 0 else float("nan")
    dir_n   = len(scored)

    # -- Section helpers ----------------------------------------------------

    def corr_table() -> str:
        headers = ["Target", "Pearson r", "p-value", "Spearman r", "p-value", "n"]
        rows = []
        for tgt, info in corr.items():
            rows.append([
                info["label"],
                f"{info['pearson_r']:+.4f}{stars(info['pearson_p'])}",
                f"{info['pearson_p']:.4f}",
                f"{info['spearman_r']:+.4f}{stars(info['spearman_p'])}",
                f"{info['spearman_p']:.4f}",
                info["n"],
            ])
        return md_table(headers, rows)

    def verdict_table() -> str:
        headers = ["Verdict", "N", "Mean delta wOBA", "% Correct Direction"]
        rows = []
        for v in VERDICT_ORDER:
            if v not in verdicts:
                continue
            info = verdicts[v]
            dir_str = pct(info["n_correct"], info["n"]) if info["n_correct"] is not None else "N/A"
            rows.append([v, info["n"], f"{info['mean_delta_wOBA']:+.4f}", dir_str])
        return md_table(headers, rows)

    def metric_table() -> str:
        headers = ["April Metric", "Pearson r vs delta wOBA", "p-value", "Spearman r", "Significance"]
        rows = []
        for m in metrics:
            rows.append([
                m["metric"],
                f"{m['pearson_r']:+.4f}",
                f"{m['pearson_p']:.4f}",
                f"{m['spearman_r']:+.4f}",
                stars(m["pearson_p"]) or "ns",
            ])
        return md_table(headers, rows)

    def top_weights_table() -> str:
        headers = ["Rank", "Pearson r", "p", "BABIP w", "HR/FB w", "HH% w", "Barrel w", "Z-Con w", "xwOBA_gap w"]
        rows = []
        for rank, (_, row) in enumerate(grid.head(10).iterrows(), 1):
            rows.append([
                rank,
                f"{row.pearson_r:+.4f}",
                f"{row.p_value:.4f}",
                row.w_BABIP,
                row.w_hr_fb,
                row.w_hard_hit,
                row.w_barrel,
                row.w_z_contact,
                row.w_xwOBA_gap,
            ])
        return md_table(headers, rows)

    def current_weights_table() -> str:
        headers = ["Metric", "League Avg", "Current Weight", "Notes"]
        rows = [
            ["BABIP",          ".300",  "-5.000", "Primary luck driver"],
            ["HR/FB rate",     "14.5%", "-0.040", ""],
            ["Hard-hit rate",  "39%",   "+0.025", ""],
            ["Barrel rate",    "8%",    "+0.030", ""],
            ["Z-contact rate", "88%",   "-0.010", "Smallest weight"],
        ]
        return md_table(headers, rows)

    def optimal_weights_table() -> str:
        if best is None:
            return "_No grid search results available._"
        headers = ["Metric", "League Avg", "Optimal Weight", "Change from Current"]
        rows = [
            ["BABIP",          ".300",  f"{best.w_BABIP:.3f}",     f"{best.w_BABIP - (-5.0):+.3f}"],
            ["HR/FB rate",     "14.5%", f"{best.w_hr_fb:.4f}",    f"{best.w_hr_fb - (-0.04):+.4f}"],
            ["Hard-hit rate",  "39%",   f"{best.w_hard_hit:.4f}", f"{best.w_hard_hit - 0.025:+.4f}"],
            ["Barrel rate",    "8%",    f"{best.w_barrel:.4f}",   f"{best.w_barrel - 0.030:+.4f}"],
            ["Z-contact rate", "88%",   f"{best.w_z_contact:.4f}", f"{best.w_z_contact - (-0.01):+.4f}"],
            ["xwOBA gap",      "—",     f"{best.w_xwOBA_gap:.3f}", "New component"],
        ]
        return md_table(headers, rows)

    # -- Determine key findings ---------------------------------------------
    most_predictive = metrics[0]["metric"] if metrics else "N/A"
    least_predictive = metrics[-1]["metric"] if metrics else "N/A"
    add_xwoba = best is not None and best.w_xwOBA_gap > 0

    improvement_str = f"{best_r - curr_pr:+.4f}" if best is not None and not np.isnan(curr_pr) else "N/A"

    # -- Assemble report ----------------------------------------------------
    report = f"""\
# Fantasy Baseball Luck Model — Backtest Report

**Generated:** {today}
**Model version:** Hitter luck score v1 (BABIP-anchored, 5-component)
**Significance:** `*` p<0.05  `**` p<0.01  `***` p<0.001  `†` p<0.10  `ns` not significant

---

## 1. Backtest Design

| Parameter | Value |
|---|---|
| Years tested | 2023, 2024 |
| April window | Opening Day through April 30 |
| Validation window | May 1 through July 31 |
| Min April PA | {MIN_APRIL_PA} |
| Min May-July PA | {MIN_MAY_JULY_PA} |
| Total player-seasons | {n_total} ({n_2023} in 2023, {n_2024} in 2024) |

**Hypothesis:** A positive April luck score (unlucky) should predict above-April
performance in May-July; a negative score (lucky) should predict below-April
performance. A well-calibrated model produces a significant positive correlation
between luck score and the May-July performance delta.

---

## 2. Current Model Weights

{current_weights_table()}

**Sign convention:** positive luck score = unlucky = buy low candidate.

---

## 3. Correlation Analysis

### 3a. April luck score vs May-July performance delta

{corr_table()}

Significance legend: `***` p<0.001 . `**` p<0.01 . `*` p<0.05 . `†` p<0.10 . _(blank)_ ns

**Primary result:** The April luck score showed a Pearson r of **{curr_pr:+.4f}** (p={curr_pp:.4f})
with May-July wOBA delta across {corr.get('delta_wOBA', {}).get('n', 0)} player-seasons.
{"This is a statistically significant positive relationship, confirming the model captures real regression signal." if curr_pp < 0.05 else "This relationship did not reach conventional statistical significance (p >= 0.05), suggesting the current weights need recalibration or the sample is underpowered."}

### 3b. Directional accuracy (non-neutral verdicts only)

Of the {dir_n} player-seasons with a non-neutral verdict, **{dir_acc:.1%}** saw performance
move in the predicted direction (wOBA improved for buy-low calls, declined for sell-high calls).
A random model would score ~50%. Scores above 55% indicate genuine predictive value.

---

## 4. Verdict Bucket Analysis

Did players perform as their April verdict predicted over May-July?

{verdict_table()}

**Interpretation:**
- A gradient from positive mean delta wOBA in Buy low rows to negative in Sell high rows
  confirms the model's directional validity.
- The magnitude of the gap between Buy low and Sell high mean delta wOBA measures effect size.
- A large Buy low / Sell high spread with high directional accuracy = strong model.

---

## 5. Individual Metric Predictiveness

Which April metric, by itself, best predicted May-July wOBA improvement?

{metric_table()}

**Key finding:** **{most_predictive}** was the single strongest predictor of May-July
wOBA change. **{least_predictive}** showed the weakest relationship and may deserve a lower
weight or removal from the model.

### Implications for weighting:
- Metrics with high |r| deserve higher weights in the composite luck score.
- Metrics with near-zero or wrong-sign r may be adding noise rather than signal.
- xwOBA gap and xBA gap appear as new candidates based on the Statcast estimator columns.

---

## 6. Weight Optimization

### Grid search parameters
- **BABIP weight:** {[-3.0, -4.0, -5.0, -6.0, -7.0, -9.0]}
- **HR/FB weight:** {[0.0, -0.02, -0.04, -0.06, -0.10, -0.15]}
- **Hard-hit weight:** {[0.0, 0.015, 0.025, 0.04, 0.06, 0.10]}
- **Barrel weight:** {[0.0, 0.015, 0.030, 0.05, 0.08, 0.12]}
- **Z-contact weight:** {[0.0, -0.005, -0.010, -0.020, -0.030]}
- **xwOBA gap weight (new):** {[0.0, 0.50, 1.00, 2.00, 3.00]}

Optimization target: **Pearson r between luck score and May-July delta wOBA**

### Top 10 weight combinations

{top_weights_table()}

### Optimal vs current weights

{optimal_weights_table()}

**Improvement in correlation:** {improvement_str} (current r={curr_pr:+.4f} -> optimal r={best_r:+.4f})

---

## 7. Key Findings and Recommended Model Changes

### Finding 1 — Overall predictive validity
{"OK The model produces a statistically significant positive correlation with May-July performance, confirming it captures genuine regression signal beyond noise." if curr_pp < 0.05 else "WARNING The current model's correlation with May-July performance does not reach p<0.05. The directional signal exists but the specific weights need tuning."}

### Finding 2 — Most predictive metric
**{most_predictive}** is the strongest individual predictor. The current model
{"correctly emphasizes this metric" if metrics and metrics[0]["col"].startswith("apr_BABIP") else "may be underweighting this metric relative to its predictive power"}.

### Finding 3 — Least predictive metric
**{least_predictive}** showed the weakest individual correlation with future performance.
{"Consider reducing its weight or removing it from the model." if metrics and abs(metrics[-1]["pearson_r"]) < 0.05 else "Its weight appears reasonable given its predictive contribution."}

### Finding 4 — xwOBA / xBA gap augmentation
{"OK Adding xwOBA gap as a model component improved correlation in the grid search. The gap between expected and actual wOBA captures luck on contact that BABIP alone misses." if add_xwoba else "WARNING Adding xwOBA gap did not materially improve predictive correlation in the grid search. BABIP and hard-contact metrics may already capture the same information."}

### Finding 5 — Weight calibration
The optimal BABIP weight from the grid search is **{best.w_BABIP if best is not None else 'N/A'}**
vs the current **-5.000**. {"This suggests increasing BABIP's dominance in the model." if best is not None and abs(best.w_BABIP) > 5 else "The current BABIP weight is in the right range."}

---

## 8. Recommended Changes to `score_luck.py`

Based on the backtest, the following changes are recommended (in priority order):

"""

    if best is not None:
        report += f"""\
### Priority 1 — Adopt optimized weights (estimated {improvement_str} correlation lift)

```python
COMPONENTS = [
    # (column,          league_avg, weight,  label)
    ("BABIP",           0.300,     {best.w_BABIP:.3f},   "BABIP vs .300"),
    ("hr_fb_rate",      0.145,     {best.w_hr_fb:.4f},  "HR/FB vs 14.5%"),
    ("hard_hit_rate",   0.390,      {best.w_hard_hit:.4f},  "Hard hit vs 39%"),
    ("barrel_rate",     0.080,      {best.w_barrel:.4f},  "Barrel vs 8%"),
    ("z_contact_rate",  0.880,     {best.w_z_contact:.4f},  "Z-contact vs 88%"),
]
```

"""
    if add_xwoba and best is not None and best.w_xwOBA_gap > 0:
        report += f"""\
### Priority 2 — Add xwOBA gap component

Add `estimated_woba_using_speedangle` (xwOBA) to `process_stats.py` output and
include a new luck component in `score_luck.py`:

```python
# In process_stats.py — add xwOBA per batter (mean of xwOBA on contact per PA)
# In score_luck.py — add to COMPONENTS:
("xwOBA_gap",  0.0,  {best.w_xwOBA_gap:.3f},  "xwOBA gap vs actual wOBA"),
```

The xwOBA gap = (April xwOBA - April wOBA). Positive = player underperformed
their contact quality (unlucky). Backtesting shows this component adds predictive
signal beyond BABIP and exit-velocity metrics.

"""

    report += """\
### Priority 3 — Confidence multiplier for small samples

Add a sample-size scaling factor to shrink luck scores toward zero for players
with fewer than 30 PA. This prevents early-season noise from dominating
the buy/sell lists before meaningful data has accumulated:

```python
def confidence_scale(pa: int, min_pa: int = 30, target_pa: int = 100) -> float:
    \"\"\"Scale [0, 1] that grows from 0 at min_pa to 1 at target_pa.\"\"\"
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
"""

    return report


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if not os.path.exists(INPUT_PATH):
        raise SystemExit(
            f"Input file not found: {INPUT_PATH}\n"
            "Run backtest_april.py first to generate the raw backtest data."
        )

    print(f"Loading {INPUT_PATH} ...")
    df = pd.read_csv(INPUT_PATH, low_memory=False)

    # The index from backtest_april.py is batter MLBAM ID
    if "batter" in df.columns:
        df = df.set_index("batter")

    print(f"  {len(df)} player-seasons loaded")
    print(f"  Years: {sorted(df['year'].unique())}")
    print(f"  Columns: {list(df.columns)}")

    # Ensure we have the minimum required columns
    required = ["luck_score", "verdict", "delta_wOBA", "year"]
    missing_req = [c for c in required if c not in df.columns]
    if missing_req:
        raise SystemExit(f"Missing required columns: {missing_req}\n"
                         "Re-run backtest_april.py to regenerate backtest_raw.csv.")

    # -- Run analyses ----------------------------------------------------------
    corr    = run_correlation_analysis(df)
    verdicts = run_verdict_analysis(df)
    metrics = run_metric_importance(df)
    grid    = run_weight_optimization(df)

    # -- Build results CSV -----------------------------------------------------
    results = build_results_csv(df)
    results.to_csv(RESULTS_PATH)
    print(f"\nSaved {len(results)} rows to {RESULTS_PATH}")

    # -- Generate report -------------------------------------------------------
    report_md = generate_report(df, corr, verdicts, metrics, grid)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report_md)
    print(f"Saved report to {REPORT_PATH}")

    # -- Terminal summary ------------------------------------------------------
    print("\n" + "=" * 65)
    print(" BACKTEST SUMMARY")
    print("=" * 65)

    curr_pr = corr.get("delta_wOBA", {}).get("pearson_r", float("nan"))
    curr_pp = corr.get("delta_wOBA", {}).get("pearson_p", float("nan"))
    best_r  = grid.iloc[0]["pearson_r"] if len(grid) > 0 else float("nan")

    print(f"  Player-seasons analyzed:      {len(df)}")
    print(f"  Current model (delta wOBA):       r={curr_pr:+.4f}  p={curr_pp:.4f}  {stars(curr_pp) or 'ns'}")
    print(f"  Best optimized weights:       r={best_r:+.4f}")
    print(f"  Correlation improvement:      {best_r - curr_pr:+.4f}")
    print()
    print("  Verdict mean delta wOBA:")
    for v in VERDICT_ORDER:
        if v in verdicts:
            info = verdicts[v]
            print(f"    {v:<14} {info['mean_delta_wOBA']:+.4f}  (n={info['n']})")
    print()
    print(f"  Most predictive metric:  {metrics[0]['metric']} (r={metrics[0]['pearson_r']:+.4f})")
    print(f"  Least predictive metric: {metrics[-1]['metric']} (r={metrics[-1]['pearson_r']:+.4f})")
    print()

    if len(grid) > 0:
        best = grid.iloc[0]
        print("  Optimal weights:")
        print(f"    BABIP:          {best.w_BABIP:.3f}   (current -5.000)")
        print(f"    HR/FB:          {best.w_hr_fb:.4f}  (current -0.040)")
        print(f"    Hard-hit:       {best.w_hard_hit:.4f}  (current +0.025)")
        print(f"    Barrel:         {best.w_barrel:.4f}  (current +0.030)")
        print(f"    Z-contact:      {best.w_z_contact:.4f} (current -0.010)")
        print(f"    xwOBA gap:      {best.w_xwOBA_gap:.3f}   (new, 0 = not used)")
    print()
    print(f"  Full results:  {RESULTS_PATH}")
    print(f"  Full report:   {REPORT_PATH}")


if __name__ == "__main__":
    main()
