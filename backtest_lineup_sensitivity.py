#!/usr/bin/env python3
"""
backtest_lineup_sensitivity.py
Validates lineup context multiplier sensitivity values using 2025 data.

Method:
  1. Derive 2025 batting slots from pitcher_statcast_april_2025.parquet
  2. Compute 2025 team lineup context (OBP/SLG by slot) from same parquet
  3. Compute multipliers for each sensitivity value [0.8, 1.0, 1.2, 1.5, 2.0]
  4. Apply to existing proj_full_r / proj_full_rbi from projection_accuracy_2025.csv
  5. Compare adjusted vs raw vs actual 2025 R and RBI
  6. Report optimal sensitivity per stat, MAE improvement, signal-group breakdown

Does NOT modify any production files.
"""

import json
import numpy as np
import pandas as pd
from collections import Counter

PARQ_2025   = "backtest_cache/pitcher_statcast_april_2025.parquet"
ACC_2025    = "data/projection_accuracy_2025.csv"

SENSITIVITIES = [0.0, 0.8, 1.0, 1.2, 1.5, 2.0]

# Weight structure (same as lineup_context.py)
R_OFFSETS   = {1: 0.35, 2: 0.25, 3: 0.20, 4: 0.20}
RBI_OFFSETS = {1: 0.40, 2: 0.35, 3: 0.25}
MIN_PA_TRUST = 10
MULT_MIN, MULT_MAX = 0.80, 1.20

# Event sets (same as build_lineup_context.py)
HIT_EVENTS = {"single", "double", "triple", "home_run"}
BB_EVENTS  = {"walk", "intent_walk"}
HBP_EVENTS = {"hit_by_pitch", "catcher_interf"}
AB_EVENTS  = {
    "single", "double", "triple", "home_run",
    "strikeout", "strikeout_double_play",
    "field_out", "grounded_into_double_play", "double_play",
    "triple_play", "force_out", "fielders_choice",
    "fielders_choice_out", "other_out",
}
SF_EVENTS = {"sac_fly", "sac_fly_double_play"}


# ── slot derivation (identical to build_lineup_context.py) ──────────────────
def derive_slots(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["bat_team"] = np.where(
        df["inning_topbot"] == "Top", df["away_team"], df["home_team"]
    )
    first_ab = (
        df.sort_values("at_bat_number")
        .groupby(["game_pk", "batter"])
        .agg(
            first_ab_num=("at_bat_number", "min"),
            topbot=("inning_topbot", "first"),
            bat_team=("bat_team", "first"),
        )
        .reset_index()
    )
    first_ab["batting_slot"] = (
        first_ab.groupby(["game_pk", "topbot"])["first_ab_num"]
        .rank(method="min")
        .astype(int)
        .clip(1, 9)
    )
    return first_ab


def modal_slot(series):
    return Counter(series).most_common(1)[0][0]


def _obp_slg(events: pd.Series) -> tuple[float, float, int]:
    hits = events.isin(HIT_EVENTS).sum()
    bb   = events.isin(BB_EVENTS).sum()
    hbp  = events.isin(HBP_EVENTS).sum()
    ab   = events.isin(AB_EVENTS).sum()
    sf   = events.isin(SF_EVENTS).sum()
    denom = ab + bb + hbp + sf
    obp = (hits + bb + hbp) / denom if denom > 0 else 0.0
    slg_n = (
        (events == "single").sum() * 1
        + (events == "double").sum() * 2
        + (events == "triple").sum() * 3
        + (events == "home_run").sum() * 4
    )
    slg = slg_n / ab if ab > 0 else 0.0
    return float(obp), float(slg), int(denom)


def cyclic(slot: int, offset: int) -> int:
    return ((slot - 1 + offset) % 9) + 1


# ── multiplier computation ───────────────────────────────────────────────────
def compute_mult(slot: int, team: str, ctx: dict,
                 r_sens: float, rbi_sens: float) -> tuple[float, float]:
    lg_obp = ctx["_league_avg"]["obp"]
    lg_slg = ctx["_league_avg"]["slg"]

    def get_obp(t, s):
        d = ctx.get(t, {}).get(str(s), {})
        if d.get("pa", 0) >= MIN_PA_TRUST and d.get("obp", 0) > 0:
            return d["obp"]
        return lg_obp

    def get_slg(t, s):
        d = ctx.get(t, {}).get(str(s), {})
        if d.get("pa", 0) >= MIN_PA_TRUST and d.get("slg", 0) > 0:
            return d["slg"]
        return lg_slg

    weighted_slg = sum(w * get_slg(team, cyclic(slot, off)) for off, w in R_OFFSETS.items())
    weighted_obp = sum(w * get_obp(team, cyclic(slot, -off)) for off, w in RBI_OFFSETS.items())

    r_raw   = 1.0 + r_sens   * (weighted_slg / lg_slg - 1.0)
    rbi_raw = 1.0 + rbi_sens * (weighted_obp / lg_obp - 1.0)

    return (
        round(min(MULT_MAX, max(MULT_MIN, r_raw)),   4),
        round(min(MULT_MAX, max(MULT_MIN, rbi_raw)), 4),
    )


# ── main ─────────────────────────────────────────────────────────────────────
def main():
    # 1. Load 2025 parquet
    print("Loading pitcher_statcast_april_2025.parquet...")
    needed = ["batter", "game_pk", "at_bat_number", "inning_topbot",
              "home_team", "away_team", "events"]
    pdf = pd.read_parquet(PARQ_2025, columns=needed)
    print(f"  {len(pdf):,} rows | {pdf['batter'].nunique()} batters | "
          f"{pdf['game_pk'].nunique()} games")

    # 2. Derive 2025 batting slots
    print("\nDeriving 2025 batting slots...")
    first_ab = derive_slots(pdf)
    batter_slots = (
        first_ab.groupby("batter")
        .agg(
            modal_slot=("batting_slot", lambda s: modal_slot(s)),
            n_games=("batting_slot", "count"),
            modal_team=("bat_team", lambda s: Counter(s).most_common(1)[0][0]),
        )
        .reset_index()
    )
    print(f"  {len(batter_slots)} batters with slot assignment")

    # 3. Compute 2025 team lineup context
    print("\nComputing 2025 team lineup context...")
    pdf2 = pdf.merge(
        first_ab[["game_pk", "batter", "batting_slot"]],
        on=["game_pk", "batter"],
        how="left",
    )
    pdf2["bat_team"] = np.where(
        pdf2["inning_topbot"] == "Top", pdf2["away_team"], pdf2["home_team"]
    )
    pa25 = pdf2[pdf2["events"].notna() & pdf2["batting_slot"].notna()].copy()
    pa25["batting_slot"] = pa25["batting_slot"].astype(int)

    ctx = {}
    lg_h = lg_bb = lg_hbp = lg_ab = lg_sf = 0
    lg_slg_n = 0

    for team in sorted(pa25["bat_team"].dropna().unique()):
        t = pa25[pa25["bat_team"] == team]
        ctx[team] = {}
        for slot in range(1, 10):
            ev = t.loc[t["batting_slot"] == slot, "events"]
            obp, slg, pa_n = _obp_slg(ev)
            ctx[team][str(slot)] = {"obp": round(obp, 4), "slg": round(slg, 4), "pa": pa_n}
            hits = ev.isin(HIT_EVENTS).sum()
            bb   = ev.isin(BB_EVENTS).sum()
            hbp  = ev.isin(HBP_EVENTS).sum()
            ab   = ev.isin(AB_EVENTS).sum()
            sf   = ev.isin(SF_EVENTS).sum()
            lg_h += hits; lg_bb += bb; lg_hbp += hbp; lg_ab += ab; lg_sf += sf
            lg_slg_n += ((ev=="single").sum()*1 + (ev=="double").sum()*2
                         + (ev=="triple").sum()*3 + (ev=="home_run").sum()*4)

    denom_obp = lg_ab + lg_bb + lg_hbp + lg_sf
    lg_obp = (lg_h + lg_bb + lg_hbp) / denom_obp if denom_obp else 0.320
    lg_slg = lg_slg_n / lg_ab if lg_ab else 0.410
    ctx["_league_avg"] = {"obp": round(lg_obp, 4), "slg": round(lg_slg, 4)}
    print(f"  2025 league avg OBP: {lg_obp:.4f}  SLG: {lg_slg:.4f}")

    # 4. Load projection accuracy data
    print(f"\nLoading {ACC_2025}...")
    acc = pd.read_csv(ACC_2025)
    print(f"  {len(acc)} players with proj_full_r / proj_full_rbi / actual_r / actual_rbi")
    acc = acc.dropna(subset=["proj_full_r", "proj_full_rbi", "actual_r", "actual_rbi"])
    print(f"  {len(acc)} players after dropping NaN stats")

    # 5. Join batting slot and team for each accuracy player
    slot_map = batter_slots.set_index("batter")[["modal_slot", "modal_team", "n_games"]].to_dict("index")

    def get_slot_team(bid):
        info = slot_map.get(bid)
        if info is None:
            return None, None, 0
        return info["modal_slot"], info["modal_team"], info["n_games"]

    acc["_slot"]   = acc["batter_id"].map(lambda x: get_slot_team(x)[0])
    acc["_team"]   = acc["batter_id"].map(lambda x: get_slot_team(x)[1])
    acc["_ngames"] = acc["batter_id"].map(lambda x: get_slot_team(x)[2])

    matched = acc["_slot"].notna().sum()
    print(f"  Matched to 2025 slot: {matched} / {len(acc)} "
          f"({100*matched/max(len(acc),1):.0f}%)")
    print(f"  Unmatched (using mult=1.0): {len(acc)-matched}")

    # 6. Sensitivity sweep
    print("\n" + "="*60)
    print("SENSITIVITY SWEEP")
    print("="*60)

    results = {}   # sens → {r_mae, rbi_mae, r_bias, rbi_bias}

    for sens in SENSITIVITIES:
        r_adj_list   = []
        rbi_adj_list = []
        r_raw_list   = []
        rbi_raw_list = []
        act_r_list   = []
        act_rbi_list = []

        for _, row in acc.iterrows():
            slot = row["_slot"]
            team = row["_team"]
            proj_r   = float(row["proj_full_r"])
            proj_rbi = float(row["proj_full_rbi"])
            act_r    = float(row["actual_r"])
            act_rbi  = float(row["actual_rbi"])

            if pd.notna(slot) and pd.notna(team):
                rm, xm = compute_mult(int(slot), str(team), ctx, r_sens=sens, rbi_sens=sens)
            else:
                rm, xm = 1.0, 1.0

            r_adj_list.append(proj_r * rm)
            rbi_adj_list.append(proj_rbi * xm)
            r_raw_list.append(proj_r)
            rbi_raw_list.append(proj_rbi)
            act_r_list.append(act_r)
            act_rbi_list.append(act_rbi)

        r_mae   = np.mean(np.abs(np.array(r_adj_list) - np.array(act_r_list)))
        rbi_mae = np.mean(np.abs(np.array(rbi_adj_list) - np.array(act_rbi_list)))
        r_bias  = np.mean(np.array(r_adj_list) - np.array(act_r_list))
        rbi_bias = np.mean(np.array(rbi_adj_list) - np.array(act_rbi_list))
        results[sens] = {"r_mae": r_mae, "rbi_mae": rbi_mae,
                         "r_bias": r_bias, "rbi_bias": rbi_bias}

    # Baseline (sens=0.0 → all mults=1.0)
    raw_r_mae   = results[0.0]["r_mae"]
    raw_rbi_mae = results[0.0]["rbi_mae"]
    raw_r_bias  = results[0.0]["r_bias"]
    raw_rbi_bias = results[0.0]["rbi_bias"]

    print(f"\n{'Sensitivity':>12} {'R_MAE':>8} {'R_Δ':>7} {'R_Bias':>8} {'RBI_MAE':>9} {'RBI_Δ':>7} {'RBI_Bias':>10}")
    print("-" * 68)
    for s in SENSITIVITIES:
        r = results[s]
        r_delta   = r["r_mae"]   - raw_r_mae
        rbi_delta = r["rbi_mae"] - raw_rbi_mae
        marker = " ← baseline" if s == 0.0 else ""
        print(f"{s:>12.1f} {r['r_mae']:>8.2f} {r_delta:>+7.2f} {r['r_bias']:>+8.2f}"
              f" {r['rbi_mae']:>9.2f} {rbi_delta:>+7.2f} {r['rbi_bias']:>+10.2f}{marker}")

    # Best per-axis (optimize R and RBI independently)
    print("\n" + "="*60)
    print("INDEPENDENT AXIS OPTIMIZATION")
    print("="*60)

    # Vary only R sensitivity (RBI mult=1.0 by using rbi_sens=0)
    r_only = {}
    rbi_only = {}
    for sens in SENSITIVITIES:
        r_l, rbi_l, ar, arbi = [], [], [], []
        for _, row in acc.iterrows():
            slot = row["_slot"]; team = row["_team"]
            proj_r = float(row["proj_full_r"]); proj_rbi = float(row["proj_full_rbi"])
            act_r  = float(row["actual_r"]);   act_rbi  = float(row["actual_rbi"])
            if pd.notna(slot) and pd.notna(team):
                rm, _  = compute_mult(int(slot), str(team), ctx, r_sens=sens, rbi_sens=0.0)
                _,  xm = compute_mult(int(slot), str(team), ctx, r_sens=0.0,  rbi_sens=sens)
            else:
                rm, xm = 1.0, 1.0
            r_l.append(proj_r * rm); rbi_l.append(proj_rbi * xm)
            ar.append(act_r);        arbi.append(act_rbi)
        r_only[sens]   = np.mean(np.abs(np.array(r_l)   - np.array(ar)))
        rbi_only[sens] = np.mean(np.abs(np.array(rbi_l) - np.array(arbi)))

    opt_r_sens   = min(r_only,   key=r_only.get)
    opt_rbi_sens = min(rbi_only, key=rbi_only.get)

    print(f"\n  R-axis (RBI held at 1.0):")
    for s in SENSITIVITIES:
        delta = r_only[s] - r_only[0.0]
        best_marker = " ← BEST" if s == opt_r_sens else ""
        print(f"    sens={s:.1f}  R_MAE={r_only[s]:.3f}  Δ={delta:+.3f}{best_marker}")

    print(f"\n  RBI-axis (R held at 1.0):")
    for s in SENSITIVITIES:
        delta = rbi_only[s] - rbi_only[0.0]
        best_marker = " ← BEST" if s == opt_rbi_sens else ""
        print(f"    sens={s:.1f}  RBI_MAE={rbi_only[s]:.3f}  Δ={delta:+.3f}{best_marker}")

    # 7. Signal group breakdown at optimal settings
    print("\n" + "="*60)
    print(f"SIGNAL GROUP BREAKDOWN  (R_sens={opt_r_sens}  RBI_sens={opt_rbi_sens})")
    print("="*60)
    for sig in acc["signal"].unique():
        sg = acc[acc["signal"] == sig]
        r_raw_e = []; r_adj_e = []; rbi_raw_e = []; rbi_adj_e = []; ar_e = []; arbi_e = []
        for _, row in sg.iterrows():
            slot = row["_slot"]; team = row["_team"]
            proj_r = float(row["proj_full_r"]); proj_rbi = float(row["proj_full_rbi"])
            act_r  = float(row["actual_r"]);   act_rbi  = float(row["actual_rbi"])
            if pd.notna(slot) and pd.notna(team):
                rm, xm = compute_mult(int(slot), str(team), ctx,
                                      r_sens=opt_r_sens, rbi_sens=opt_rbi_sens)
            else:
                rm, xm = 1.0, 1.0
            r_raw_e.append(proj_r); r_adj_e.append(proj_r*rm)
            rbi_raw_e.append(proj_rbi); rbi_adj_e.append(proj_rbi*xm)
            ar_e.append(act_r); arbi_e.append(act_rbi)
        n = len(sg)
        r_mae_raw = np.mean(np.abs(np.array(r_raw_e) - np.array(ar_e)))
        r_mae_adj = np.mean(np.abs(np.array(r_adj_e) - np.array(ar_e)))
        rbi_mae_raw = np.mean(np.abs(np.array(rbi_raw_e) - np.array(arbi_e)))
        rbi_mae_adj = np.mean(np.abs(np.array(rbi_adj_e) - np.array(arbi_e)))
        print(f"\n  {sig} (n={n}):")
        print(f"    R    raw_MAE={r_mae_raw:.2f}  adj_MAE={r_mae_adj:.2f}  Δ={r_mae_adj-r_mae_raw:+.2f}")
        print(f"    RBI  raw_MAE={rbi_mae_raw:.2f}  adj_MAE={rbi_mae_adj:.2f}  Δ={rbi_mae_adj-rbi_mae_raw:+.2f}")

    # 8. Mult distribution at optimal
    print("\n" + "="*60)
    print("MULTIPLIER DISTRIBUTION AT OPTIMAL SETTINGS")
    print("="*60)
    r_mults = []; rbi_mults = []
    at_cap_r = at_cap_rbi = at_floor_r = at_floor_rbi = at_one = 0
    for _, row in acc.iterrows():
        slot = row["_slot"]; team = row["_team"]
        if pd.notna(slot) and pd.notna(team):
            rm, xm = compute_mult(int(slot), str(team), ctx,
                                  r_sens=opt_r_sens, rbi_sens=opt_rbi_sens)
        else:
            rm, xm = 1.0, 1.0
        r_mults.append(rm); rbi_mults.append(xm)
        if rm == MULT_MAX: at_cap_r += 1
        if rm == MULT_MIN: at_floor_r += 1
        if xm == MULT_MAX: at_cap_rbi += 1
        if xm == MULT_MIN: at_floor_rbi += 1
        if rm == 1.0 and xm == 1.0: at_one += 1
    print(f"\n  R_mult  : mean={np.mean(r_mults):.4f}  std={np.std(r_mults):.4f}  "
          f"at_cap({MULT_MAX})={at_cap_r}  at_floor({MULT_MIN})={at_floor_r}")
    print(f"  RBI_mult: mean={np.mean(rbi_mults):.4f}  std={np.std(rbi_mults):.4f}  "
          f"at_cap({MULT_MAX})={at_cap_rbi}  at_floor({MULT_MIN})={at_floor_rbi}")
    print(f"  Exactly (1.0,1.0): {at_one}")

    # 9. Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"\n  Baseline (no adjustment):")
    print(f"    R   MAE={raw_r_mae:.2f}   bias={raw_r_bias:+.2f}")
    print(f"    RBI MAE={raw_rbi_mae:.2f}   bias={raw_rbi_bias:+.2f}")
    print(f"\n  Optimal R   sensitivity: {opt_r_sens}  → MAE {r_only[opt_r_sens]:.2f}  "
          f"Δ={r_only[opt_r_sens]-raw_r_mae:+.2f}")
    print(f"  Optimal RBI sensitivity: {opt_rbi_sens}  → MAE {rbi_only[opt_rbi_sens]:.2f}  "
          f"Δ={rbi_only[opt_rbi_sens]-raw_rbi_mae:+.2f}")

    verdict_r   = "IMPROVE" if r_only[opt_r_sens] < raw_r_mae else "NO IMPROVEMENT"
    verdict_rbi = "IMPROVE" if rbi_only[opt_rbi_sens] < raw_rbi_mae else "NO IMPROVEMENT"
    print(f"\n  R   verdict:   {verdict_r}")
    print(f"  RBI verdict:   {verdict_rbi}")

    if verdict_r == "NO IMPROVEMENT" and verdict_rbi == "NO IMPROVEMENT":
        print("\n  RECOMMENDATION: Do not wire lineup multipliers into stat_projections.py.")
        print("  The April sample size is insufficient to produce reliable slot-level OBP/SLG")
        print("  estimates — adding noise does not beat the raw projection baseline.")
    else:
        print(f"\n  RECOMMENDATION: Wire lineup_context.py with R_SENSITIVITY={opt_r_sens}, "
              f"RBI_SENSITIVITY={opt_rbi_sens}.")


if __name__ == "__main__":
    main()
