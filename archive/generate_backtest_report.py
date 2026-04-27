"""
Pitcher backtest report generator.
Imports run_pitcher_audit from _pitcher_tier_audit (runs all 4 years at import time
via module-level loop — fast since all parquets are cached), then produces:
  1. Formatted per-year x per-tier accuracy table (console)
  2. Soft-contact cohort table (career_hh_allowed < 0.35)
  3. Two CSVs: data/backtest_report_pitcher.csv, data/backtest_softcontact.csv
"""

# ── Section 1: imports ────────────────────────────────────────────────────────
import pandas as pd
from pathlib import Path

# Importing runs module-level loop (all 4 years); fast with cached parquets.
from _pitcher_tier_audit import (
    run_pitcher_audit,
    P_YEARS,
    SIGNAL_MAP,
    _TIER_DISPLAY,
)

TIERS = ["BUY_LOW", "SLIGHT_BUY", "SLIGHT_SELL", "SELL_HIGH"]
RTM_BASELINE = 0.70
DATA_DIR = Path("data")

# ── Section 2: run all years ──────────────────────────────────────────────────

def build_results():
    results = {}   # year -> result_dict from run_pitcher_audit
    frames  = []   # merged_df per year

    for year in P_YEARS:
        res, merged = run_pitcher_audit(year)
        if res is not None:
            results[year] = res
            frames.append(merged)

    all_df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return results, all_df


# ── Section 3: console table ──────────────────────────────────────────────────

def _cell(res_year, tier_key):
    """Return '78.9% (n=19)' or '—' if tier absent / n==0."""
    label = _TIER_DISPLAY.get(tier_key, tier_key)
    if res_year is None or label not in res_year:
        return "—"
    entry = res_year[label]
    if entry["n"] == 0:
        return "—"
    return f"{entry['accuracy']*100:.1f}% (n={entry['n']})"


def _wt_avg(all_df, tier_key):
    """4-yr weighted accuracy for a signal tier (excludes FLAT outcomes)."""
    sub = all_df[all_df["signal"] == tier_key].copy()
    sub = sub[sub["outcome"] != "FLAT"]
    if len(sub) == 0:
        return None, None
    expected_outcome = SIGNAL_MAP[tier_key]
    n_correct = (sub["outcome"] == expected_outcome).sum()
    accuracy  = n_correct / len(sub)
    era_delta = sub[sub["outcome"] == expected_outcome]["era_change"].mean()
    return accuracy, era_delta


def print_pitcher_table(results, all_df):
    years = sorted(results.keys())

    col_w   = 18
    sig_w   = 13
    delta_w = 10

    header_parts = [f"{'Signal':<{sig_w}}"]
    for y in years:
        header_parts.append(f"{str(y):^{col_w}}")
    header_parts.append(f"{'4-Yr Avg':^{col_w}}")
    header_parts.append(f"{'Avg ERA d':^{delta_w}}")
    header = " | ".join(header_parts)

    sep = "-" * len(header)

    print()
    print("Pitcher April Signals -> May-Jul ERA | Walk-Forward Backtest 2022-2025")
    print(sep)
    print(header)
    print(sep)

    for tier_key in TIERS:
        label = _TIER_DISPLAY.get(tier_key, tier_key)
        row_parts = [f"{label:<{sig_w}}"]
        for y in years:
            row_parts.append(f"{_cell(results.get(y), tier_key):^{col_w}}")
        avg_acc, avg_delta = _wt_avg(all_df, tier_key)
        if avg_acc is not None:
            avg_str   = f"{avg_acc*100:.1f}%"
            delta_str = f"{avg_delta:+.2f}"
        else:
            avg_str   = "—"
            delta_str = "—"
        row_parts.append(f"{avg_str:^{col_w}}")
        row_parts.append(f"{delta_str:^{delta_w}}")
        print(" | ".join(row_parts))

    print(sep)

    # Overall row
    overall_parts = [f"{'Overall':<{sig_w}}"]
    for y in years:
        res_y = results.get(y)
        if res_y and "Overall" in res_y:
            ov = res_y["Overall"]
            cell = f"{ov['accuracy']*100:.1f}% (n={ov['n']})" if ov["n"] else "—"
        else:
            cell = "—"
        overall_parts.append(f"{cell:^{col_w}}")

    # 4-yr overall weighted avg (exclude FLAT)
    non_flat = all_df[all_df["outcome"] != "FLAT"].copy()
    non_flat = non_flat[non_flat["signal"].isin(TIERS)]
    if len(non_flat):
        correct = non_flat.apply(
            lambda r: r["outcome"] == SIGNAL_MAP.get(r["signal"], ""), axis=1
        ).sum()
        ov_avg_str = f"{correct/len(non_flat)*100:.1f}%"
    else:
        ov_avg_str = "—"
    overall_parts.append(f"{ov_avg_str:^{col_w}}")
    overall_parts.append(f"{'':^{delta_w}}")
    print(" | ".join(overall_parts))

    # vs. RTM row — show pp lift over RTM_BASELINE per year and for 4-yr avg
    rtm_parts = [f"{'vs. RTM':^{sig_w}}"]
    for y in years:
        res_y = results.get(y)
        if res_y and "Overall" in res_y and res_y["Overall"]["n"] > 0:
            ov = res_y["Overall"]
            yr_acc = ov["correct"] / ov["n"]
            lift = (yr_acc - RTM_BASELINE) * 100
            rtm_cell = f"{lift:+.1f}pp"
        else:
            rtm_cell = "—"
        rtm_parts.append(f"{rtm_cell:^{col_w}}")
    # 4-yr avg lift
    if len(non_flat):
        overall_4yr = correct / len(non_flat)
        lift_4yr = (overall_4yr - RTM_BASELINE) * 100
        rtm_parts.append(f"{lift_4yr:+.1f}pp".center(col_w))
    else:
        rtm_parts.append(f"{'—':^{col_w}}")
    rtm_parts.append(f"{'':^{delta_w}}")
    print(" | ".join(rtm_parts))
    print(sep)
    print()


# ── Section 4: soft-contact cohort table ─────────────────────────────────────

def print_softcontact_table(all_df):
    sub = all_df[all_df["career_hh_allowed"] < 0.35].copy()
    if sub.empty:
        print("No soft-contact pitchers found (career_hh_allowed < 0.35).")
        return

    years = sorted(sub["year"].unique())
    col_w = 18
    sig_w = 13
    delta_w = 10

    header_parts = [f"{'Signal':<{sig_w}}"]
    for y in years:
        header_parts.append(f"{str(y):^{col_w}}")
    header_parts.append(f"{'4-Yr Avg':^{col_w}}")
    header_parts.append(f"{'Avg ERA d':^{delta_w}}")
    header = " | ".join(header_parts)
    sep = "-" * len(header)

    print("Soft-Contact Cohort (career HH% < 32%) | April -> May-Jul ERA")
    print(sep)
    print(header)
    print(sep)

    for tier_key in TIERS:
        label = _TIER_DISPLAY.get(tier_key, tier_key)
        tier_sub = sub[sub["signal"] == tier_key]
        row_parts = [f"{label:<{sig_w}}"]

        for y in years:
            yr_sub = tier_sub[tier_sub["year"] == y]
            yr_eval = yr_sub[yr_sub["outcome"] != "FLAT"]
            if len(yr_eval) == 0:
                row_parts.append(f"{'—':^{col_w}}")
                continue
            expected = SIGNAL_MAP[tier_key]
            correct  = (yr_eval["outcome"] == expected).sum()
            acc      = correct / len(yr_eval)
            row_parts.append(f"{acc*100:.1f}% (n={len(yr_eval)})".center(col_w))

        # 4-yr weighted avg for this tier in cohort
        t_eval = tier_sub[tier_sub["outcome"] != "FLAT"]
        if len(t_eval):
            expected = SIGNAL_MAP[tier_key]
            correct  = (t_eval["outcome"] == expected).sum()
            avg_acc  = correct / len(t_eval)
            avg_era  = t_eval["era_change"].mean()
            row_parts.append(f"{avg_acc*100:.1f}%".center(col_w))
            row_parts.append(f"{avg_era:+.2f}".center(delta_w))
        else:
            row_parts.append(f"{'—':^{col_w}}")
            row_parts.append(f"{'—':^{delta_w}}")

        print(" | ".join(row_parts))

    print(sep)
    print(f"  Soft-contact pitchers: {sub['pitcher'].nunique()} unique | "
          f"{len(sub)} player-seasons\n")


# ── Section 5: save CSVs ──────────────────────────────────────────────────────

def save_csvs(results, all_df):
    DATA_DIR.mkdir(exist_ok=True)

    # Full pitcher backtest report
    rows = []
    for year, res in sorted(results.items()):
        for tier_key in TIERS:
            label = _TIER_DISPLAY.get(tier_key, tier_key)
            entry = res.get(label, {})
            rows.append({
                "year":     year,
                "signal":   label,
                "n":        entry.get("n", 0),
                "correct":  entry.get("correct", 0),
                "accuracy": round(entry.get("accuracy", 0), 4),
                "era_delta": round(entry.get("era_delta", float("nan")), 3),
            })
    df_report = pd.DataFrame(rows)
    out1 = DATA_DIR / "backtest_report_pitcher.csv"
    df_report.to_csv(out1, index=False)
    print(f"Saved: {out1} ({len(df_report)} rows)")

    # Soft-contact cohort
    sc = all_df[all_df["career_hh_allowed"] < 0.35].copy()
    cols = ["year", "pitcher", "player_name", "signal", "era", "fip",
            "era_fip_gap", "outcome_era", "era_change", "outcome",
            "career_hh_allowed", "career_barrel_allowed", "volatility_flag"]
    sc_out = sc[[c for c in cols if c in sc.columns]]
    out2 = DATA_DIR / "backtest_softcontact.csv"
    sc_out.to_csv(out2, index=False)
    print(f"Saved: {out2} ({len(sc_out)} rows, {sc_out['pitcher'].nunique()} pitchers)")


# ── Section 6: main ───────────────────────────────────────────────────────────

def main():
    print("\nBuilding pitcher backtest results (all parquets cached - should be fast)...")
    results, all_df = build_results()

    if not results:
        print("ERROR: no results returned from run_pitcher_audit. Check _pitcher_tier_audit.py.")
        return

    print(f"Loaded {len(all_df)} pitcher-seasons across {sorted(results.keys())}\n")

    print_pitcher_table(results, all_df)
    print_softcontact_table(all_df)
    save_csvs(results, all_df)


if __name__ == "__main__":
    main()
