#!/usr/bin/env python3
"""
build_lineup_context.py
Generates:
  data/hitter_batting_slot_2026.json   — MLBAM ID → {slot, n_games}
  data/team_lineup_context_2026.json   — team → slot → {obp, slg, pa}

Primary source: hitters_statcast.csv (2026 live April data)
Fallback:       backtest_cache/pitcher_statcast_april_2025.parquet
                (for batters with < MIN_GAMES appearances)
"""

import json
import os
import numpy as np
import pandas as pd
from collections import Counter

PRIMARY_CSV   = "hitters_statcast.csv"
FALLBACK_PARQ = "backtest_cache/pitcher_statcast_april_2025.parquet"
SLOT_JSON     = "data/hitter_batting_slot_2026.json"
CONTEXT_JSON  = "data/team_lineup_context_2026.json"
MIN_GAMES     = 5

# --- Event classification for OBP / SLG ---------------------------------
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
SF_EVENTS  = {"sac_fly", "sac_fly_double_play"}


# -------------------------------------------------------------------------
def derive_slots(df: pd.DataFrame) -> pd.DataFrame:
    """Return one row per (game_pk, batter) with batting_slot 1-9.
    Slot derived by ranking each batter's minimum at_bat_number within their
    team's half (Top=away, Bot=home) of that game.
    """
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


def modal_slot(series: pd.Series) -> int:
    return Counter(series).most_common(1)[0][0]


def _obp_slg(events: pd.Series) -> dict:
    """Compute OBP, SLG, and PA count from a series of Statcast event strings."""
    hits = events.isin(HIT_EVENTS).sum()
    bb   = events.isin(BB_EVENTS).sum()
    hbp  = events.isin(HBP_EVENTS).sum()
    ab   = events.isin(AB_EVENTS).sum()
    sf   = events.isin(SF_EVENTS).sum()
    denom_obp = ab + bb + hbp + sf
    obp = (hits + bb + hbp) / denom_obp if denom_obp > 0 else 0.0
    slg_num = (
        (events == "single").sum() * 1
        + (events == "double").sum() * 2
        + (events == "triple").sum() * 3
        + (events == "home_run").sum() * 4
    )
    slg = slg_num / ab if ab > 0 else 0.0
    return {
        "obp": round(float(obp), 4),
        "slg": round(float(slg), 4),
        "pa":  int(denom_obp),
    }


# -------------------------------------------------------------------------
def main():
    # --- Load primary data -----------------------------------------------
    print("Loading hitters_statcast.csv...")
    hdf = pd.read_csv(PRIMARY_CSV, low_memory=False)
    print(f"  {len(hdf):,} rows | {hdf['batter'].nunique()} batters | "
          f"{hdf['game_pk'].nunique()} games | {hdf['home_team'].nunique()} home teams")

    # =====================================================================
    # STEP 1 — Batting slot assignment
    # =====================================================================
    print("\n=== STEP 1: batting slot assignment ===")
    first_ab = derive_slots(hdf)

    batter_summary = (
        first_ab.groupby("batter")["batting_slot"]
        .agg(modal_slot_val=lambda s: modal_slot(s), n_games=lambda s: len(s))
        .reset_index()
    )

    # Identify batters with too few games for a reliable slot
    low_bat = batter_summary.loc[batter_summary["n_games"] < MIN_GAMES, "batter"].tolist()
    print(f"  Batters with <{MIN_GAMES} games (need fallback): {len(low_bat)}")

    if low_bat and os.path.exists(FALLBACK_PARQ):
        try:
            pdf = pd.read_parquet(
                FALLBACK_PARQ,
                columns=["batter", "game_pk", "at_bat_number", "inning_topbot",
                         "home_team", "away_team"],
            )
            pdf = pdf[pdf["batter"].isin(low_bat)]
            if len(pdf) > 0:
                pfab = derive_slots(pdf)
                pf_summary = (
                    pfab.groupby("batter")["batting_slot"]
                    .agg(modal_slot_val=lambda s: modal_slot(s), n_games=lambda s: len(s))
                    .reset_index()
                )
                bs = batter_summary.set_index("batter")
                for _, row in pf_summary.iterrows():
                    bid = row["batter"]
                    if bid in bs.index and bs.at[bid, "n_games"] < MIN_GAMES:
                        bs.at[bid, "modal_slot_val"] = row["modal_slot_val"]
                batter_summary = bs.reset_index()
                print(f"  Fallback updated {len(pf_summary)} batters from 2025 parquet")
        except Exception as exc:
            print(f"  Fallback skipped: {exc}")

    # Build slot JSON
    slot_out = {}
    for _, row in batter_summary.iterrows():
        slot_out[str(int(row["batter"]))] = {
            "slot":   int(row["modal_slot_val"]),
            "n_games": int(row["n_games"]),
        }

    with open(SLOT_JSON, "w") as f:
        json.dump(slot_out, f)
    print(f"  Saved {SLOT_JSON}: {len(slot_out)} batters")
    dist = Counter(v["slot"] for v in slot_out.values())
    print(f"  Slot distribution: { {k: dist[k] for k in sorted(dist)} }")

    # =====================================================================
    # STEP 2 — Team lineup context (OBP / SLG by team × slot)
    # =====================================================================
    print("\n=== STEP 2: team lineup context (OBP/SLG by team × slot) ===")

    # Join slot back to pitch-level data via merge (fast path)
    hdf = hdf.merge(
        first_ab[["game_pk", "batter", "batting_slot"]],
        on=["game_pk", "batter"],
        how="left",
    )
    hdf["bat_team"] = np.where(
        hdf["inning_topbot"] == "Top", hdf["away_team"], hdf["home_team"]
    )

    # PA-completing rows only (events != NaN) with a valid slot
    pa = hdf[hdf["events"].notna() & hdf["batting_slot"].notna()].copy()
    pa["batting_slot"] = pa["batting_slot"].astype(int)

    context_out: dict = {}
    lg_hits = lg_bb = lg_hbp = lg_ab = lg_sf = 0
    lg_slg_num = 0

    teams = sorted(pa["bat_team"].dropna().unique())
    for team in teams:
        t = pa[pa["bat_team"] == team]
        context_out[team] = {}
        for slot in range(1, 10):
            ev = t.loc[t["batting_slot"] == slot, "events"]
            stats = _obp_slg(ev)
            context_out[team][str(slot)] = stats
            # league accumulation
            lg_hits    += ev.isin(HIT_EVENTS).sum()
            lg_bb      += ev.isin(BB_EVENTS).sum()
            lg_hbp     += ev.isin(HBP_EVENTS).sum()
            lg_ab      += ev.isin(AB_EVENTS).sum()
            lg_sf      += ev.isin(SF_EVENTS).sum()
            lg_slg_num += (
                (ev == "single").sum() * 1
                + (ev == "double").sum() * 2
                + (ev == "triple").sum() * 3
                + (ev == "home_run").sum() * 4
            )

    lg_obp_denom = lg_ab + lg_bb + lg_hbp + lg_sf
    lg_obp = (lg_hits + lg_bb + lg_hbp) / lg_obp_denom if lg_obp_denom else 0.320
    lg_slg = lg_slg_num / lg_ab if lg_ab else 0.410
    context_out["_league_avg"] = {
        "obp": round(float(lg_obp), 4),
        "slg": round(float(lg_slg), 4),
    }

    with open(CONTEXT_JSON, "w") as f:
        json.dump(context_out, f, indent=2)
    print(f"  Saved {CONTEXT_JSON}: {len(context_out) - 1} teams")
    print(f"  League avg — OBP: {lg_obp:.4f}  SLG: {lg_slg:.4f}")

    # Sample: LAD slots 3-5
    if "LAD" in context_out:
        print("\n  LAD cleanup-window context:")
        for s in ["3", "4", "5"]:
            d = context_out["LAD"][s]
            print(f"    Slot {s}: OBP {d['obp']:.3f}  SLG {d['slg']:.3f}  PA {d['pa']}")

    # =====================================================================
    # STEP 4 — Sanity checks  (inline after build so data is fresh)
    # =====================================================================
    print("\n=== STEP 4: sanity checks ===")
    from lineup_context import compute_lineup_multipliers  # noqa: E402

    TESTS = [
        # (description, mlbam_id, team, check_fn)
        ("Freeman RBI_mult > 1.10",  518692, "LAD",  lambda r, x: x > 1.10),
        ("Freeman R_mult > 1.00",    518692, "LAD",  lambda r, x: r > 1.00),
        ("Leadoff R_mult > 1.05 (Betts LAD slot 1)", 605141, "LAD",  lambda r, x: r > 1.05),
        ("Cleanup weak team < 1.10 RBI (league avg slot)", None, None, None),  # placeholder
    ]

    # Check Freeman
    for desc, bid, team, fn in TESTS[:3]:
        try:
            rm, xm = compute_lineup_multipliers(bid, team)
            ok = fn(rm, xm)
            print(f"  {'PASS' if ok else 'FAIL'}  {desc}  →  R={rm:.4f}  RBI={xm:.4f}")
        except Exception as exc:
            print(f"  ERROR  {desc}  →  {exc}")

    # League-average slot should yield (1.0, 1.0) — test with a made-up player
    # Instead compute slot-5 across all teams and check mean ≈ 1.0
    r_vals, x_vals = [], []
    for bid_str, d in slot_out.items():
        # Find this player's team from pa data
        bid_int = int(bid_str)
        rows = pa[pa["batter"] == bid_int]
        if rows.empty:
            continue
        team = rows["bat_team"].mode().iloc[0] if not rows["bat_team"].mode().empty else None
        if team is None:
            continue
        try:
            rm, xm = compute_lineup_multipliers(bid_int, team)
            r_vals.append(rm)
            x_vals.append(xm)
        except Exception:
            pass

    print(f"\n=== STEP 5: coverage and distribution ===")
    print(f"  Coverage: {len(r_vals)} / {len(slot_out)} batters ({100*len(r_vals)/max(len(slot_out),1):.1f}%)")
    if r_vals:
        import statistics
        print(f"  R_mult   — min {min(r_vals):.4f}  max {max(r_vals):.4f}  "
              f"mean {statistics.mean(r_vals):.4f}  std {statistics.stdev(r_vals):.4f}")
        print(f"  RBI_mult — min {min(x_vals):.4f}  max {max(x_vals):.4f}  "
              f"mean {statistics.mean(x_vals):.4f}  std {statistics.stdev(x_vals):.4f}")

        # Top 5 RBI (cleanup batters on good teams)
        paired = list(zip(x_vals, r_vals, [int(b) for b in slot_out.keys() if int(b) in
                          [int(k) for k in slot_out.keys()]]))
        # rebuild with names
        all_entries = []
        for bid_str, d in slot_out.items():
            bid_int = int(bid_str)
            rows = pa[pa["batter"] == bid_int]
            if rows.empty:
                continue
            mode_result = rows["bat_team"].mode()
            if mode_result.empty:
                continue
            team = mode_result.iloc[0]
            try:
                rm, xm = compute_lineup_multipliers(bid_int, team)
                all_entries.append((bid_int, team, d["slot"], rm, xm))
            except Exception:
                pass

        top_rbi = sorted(all_entries, key=lambda x: x[4], reverse=True)[:5]
        top_r   = sorted(all_entries, key=lambda x: x[3], reverse=True)[:5]
        exactly_1 = [e for e in all_entries if e[3] == 1.0 and e[4] == 1.0]

        print(f"\n  Top 5 RBI_mult (expect LAD/NYY middle order):")
        for bid, team, slot, rm, xm in top_rbi:
            print(f"    ID={bid}  team={team}  slot={slot}  R={rm:.4f}  RBI={xm:.4f}")

        print(f"\n  Top 5 R_mult (expect leadoff on good teams):")
        for bid, team, slot, rm, xm in top_r:
            print(f"    ID={bid}  team={team}  slot={slot}  R={rm:.4f}  RBI={xm:.4f}")

        print(f"\n  Exactly (1.0, 1.0): {len(exactly_1)} batters (fallback due to missing team data)")


if __name__ == "__main__":
    main()
