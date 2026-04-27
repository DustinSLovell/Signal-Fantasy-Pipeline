"""
process_stats.py
Reads hitters_statcast.csv and aggregates pitch-level Statcast data into
per-batter metrics: PA, BABIP, hard-hit rate, barrel rate, Z-contact rate,
and HR/FB rate. Saves result to hitter_luck_input.csv.
"""

import json
import os
import urllib.request

import numpy as np
import pandas as pd
try:
    from pybaseball import playerid_reverse_lookup
except ImportError:
    raise SystemExit("pybaseball not found. Run: pip install pybaseball pandas")

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
INPUT_PATH = os.path.join(BASE_DIR, "hitters_statcast.csv")
OUTPUT_PATH = os.path.join(BASE_DIR, "hitter_luck_input.csv")

# ---------------------------------------------------------------------------
# Description-level sets used across multiple stats
# ---------------------------------------------------------------------------
CONTACT_DESCS = {
    "hit_into_play", "foul", "foul_tip", "foul_bunt", "bunt_foul_tip"
}
SWING_MISS_DESCS = {
    "swinging_strike", "swinging_strike_blocked", "missed_bunt"
}
SWING_DESCS = CONTACT_DESCS | SWING_MISS_DESCS

# Home-plate spray chart coordinates (Baseball Savant image space)
HP_X, HP_Y = 125.42, 198.27
# Minimum angle from dead-center required to qualify as a pull hit.
# At 20° the league-average pull rate is ~39%, consistent with Baseball Savant's
# published Pull% leaderboard (~38–42%).
PULL_ANGLE_THRESHOLD = 20.0

# Events that count as balls in play (exclude HR; exclude K, BB, HBP, sac, CI)
BIP_EVENTS = {
    "single", "double", "triple",
    "field_out", "force_out", "grounded_into_double_play",
    "double_play", "fielders_choice", "fielders_choice_out",
    "field_error", "sac_fly", "sac_fly_double_play",
}
HIT_BIP_EVENTS  = {"single", "double", "triple"}   # hits on BIP (no HR for BABIP)
FAIR_BIP_EVENTS = BIP_EVENTS | {"home_run"}         # all fair batted balls incl. HR (for pull rate)

# Events that count as plate appearances
NON_PA_EVENTS = {"truncated_pa"}

# True-outcome events: HR, K, BB, HBP.  Statcast leaves estimated_woba_using_speedangle
# null for these, so we fall back to actual woba_value when computing xwOBA.
TRUE_OUTCOME_EVENTS = {
    "home_run", "strikeout", "strikeout_double_play",
    "walk", "intent_walk", "hit_by_pitch",
}


# ---------------------------------------------------------------------------
# Helper: safe division
# ---------------------------------------------------------------------------
def safe_div(num: pd.Series, den: pd.Series) -> pd.Series:
    return num.div(den).where(den > 0, other=float("nan"))


# ---------------------------------------------------------------------------
# Stat computations (each returns a Series indexed by batter)
# ---------------------------------------------------------------------------

def calc_pa(df: pd.DataFrame) -> pd.Series:
    """Count of plate appearances (rows with a recorded, non-truncated event)."""
    pa_rows = df[df["events"].notna() & ~df["events"].isin(NON_PA_EVENTS)]
    return pa_rows.groupby("batter").size().rename("PA")


def calc_babip(df: pd.DataFrame) -> pd.Series:
    """BABIP = hits on balls in play / total balls in play."""
    bip = df[df["events"].isin(BIP_EVENTS | HIT_BIP_EVENTS)]
    grouped = bip.groupby("batter")
    hits_bip  = grouped["events"].apply(lambda s: s.isin(HIT_BIP_EVENTS).sum())
    total_bip = grouped["events"].apply(lambda s: s.isin(BIP_EVENTS | HIT_BIP_EVENTS).sum())
    return safe_div(hits_bip, total_bip).rename("BABIP")


def calc_hard_hit_rate(df: pd.DataFrame) -> pd.Series:
    """Hard-hit rate = BBE with exit velo >= 95 mph / fair batted ball events (BBE only).
    Denominator restricted to FAIR_BIP_EVENTS to match career baseline denominator
    (statcast_batter_exitvelo_barrels uses BBE/attempts, not all tracked EV)."""
    bbe = df[df["events"].isin(FAIR_BIP_EVENTS) & df["launch_speed"].notna()]
    grouped = bbe.groupby("batter")
    hard_hit = grouped["launch_speed"].apply(lambda s: (s >= 95).sum())
    total    = grouped["launch_speed"].count()
    return safe_div(hard_hit, total).rename("hard_hit_rate")


def calc_sweet_spot_rate(df: pd.DataFrame) -> pd.Series:
    """Sweet spot rate = BBE with EV >= 98 AND LA 8-32 degrees / fair BBE."""
    bbe = df[df["events"].isin(FAIR_BIP_EVENTS) & df["launch_speed"].notna()]
    grouped = bbe.groupby("batter")
    sweet = grouped.apply(
        lambda s: ((s["launch_speed"] >= 98) & s["launch_angle"].between(8, 32)).sum()
    )
    total = grouped["launch_speed"].count()
    return safe_div(sweet, total).rename("sweet_spot_rate")


def calc_avg_exit_velocity(df: pd.DataFrame) -> pd.Series:
    """Average exit velocity across fair batted ball events."""
    bbe = df[df["events"].isin(FAIR_BIP_EVENTS) & df["launch_speed"].notna()]
    return bbe.groupby("batter")["launch_speed"].mean().rename("avg_exit_velocity")


def calc_barrel_rate(df: pd.DataFrame) -> pd.Series:
    """Barrel rate = barrels (launch_speed_angle == 6) / fair batted ball events."""
    bbe = df[df["events"].isin(FAIR_BIP_EVENTS) & df["launch_speed"].notna()]
    grouped = bbe.groupby("batter")
    barrels = grouped["launch_speed_angle"].apply(lambda s: (s == 6).sum())
    total   = grouped["launch_speed"].count()
    return safe_div(barrels, total).rename("barrel_rate")


def calc_z_contact_rate(df: pd.DataFrame) -> pd.Series:
    """
    Z-contact rate = swings at in-zone pitches that made contact
                     / all swings at in-zone pitches.
    In-zone = Statcast zone 1-9; out-of-zone = 11-14.
    """
    in_zone = df[df["zone"].between(1, 9)]
    swings   = in_zone[in_zone["description"].isin(SWING_DESCS)]
    grouped  = swings.groupby("batter")
    contacts = grouped["description"].apply(lambda s: s.isin(CONTACT_DESCS).sum())
    total    = grouped["description"].count()
    return safe_div(contacts, total).rename("z_contact_rate")


def calc_hr_fb_rate(df: pd.DataFrame) -> pd.Series:
    """
    HR/FB rate = home runs / fly balls.
    In Statcast, HR bb_type is 'fly_ball', so fly ball denominator includes HR.
    """
    pa_rows = df[df["events"].notna()]
    grouped = pa_rows.groupby("batter")
    hr_count = grouped["events"].apply(lambda s: (s == "home_run").sum())
    # Fly balls include home runs (bb_type == 'fly_ball' for both)
    fb_count = grouped["bb_type"].apply(lambda s: (s == "fly_ball").sum())
    return safe_div(hr_count, fb_count).rename("hr_fb_rate")


def calc_pull_rate(df: pd.DataFrame) -> pd.Series:
    """
    Pull rate = clearly-pull-side batted balls / all fair batted ball events.

    Uses spray chart coordinates (hc_x, hc_y) to compute the hit angle from
    home plate, then flags a ball as "pulled" when the angle exceeds
    PULL_ANGLE_THRESHOLD (20°) toward the batter's pull side:
      RHB pull: angle < -20°  (toward left field)
      LHB pull: angle > +20°  (toward right field)

    This threshold produces a league-average pull rate of ~39%, consistent
    with Baseball Savant's published Pull% leaderboard. Rows where hc_x or
    hc_y is null (strikeouts, walks, bunts not tracked) are excluded.
    """
    fair_bip = df[
        df["events"].isin(FAIR_BIP_EVENTS)
        & df["hc_x"].notna()
        & df["hc_y"].notna()
    ].copy()
    if fair_bip.empty:
        return pd.Series(dtype=float, name="pull_rate")

    angle = np.degrees(np.arctan2(
        fair_bip["hc_x"] - HP_X,
        HP_Y - fair_bip["hc_y"],
    ))
    fair_bip["pulled"] = (
        ((fair_bip["stand"] == "R") & (angle < -PULL_ANGLE_THRESHOLD))
        | ((fair_bip["stand"] == "L") & (angle > PULL_ANGLE_THRESHOLD))
    )
    grouped    = fair_bip.groupby("batter")
    pull_count = grouped["pulled"].sum()
    total      = grouped["pulled"].count()
    return safe_div(pull_count, total).rename("pull_rate")


def calc_gb_rate(df: pd.DataFrame) -> pd.Series:
    """Ground ball rate = ground_ball bb_type / all batted ball events."""
    bbe = df[df["bb_type"].notna() & (df["bb_type"] != "")]
    grouped = bbe.groupby("batter")
    gb    = grouped["bb_type"].apply(lambda s: (s == "ground_ball").sum())
    total = grouped["bb_type"].count()
    return safe_div(gb, total).rename("gb_rate")


def calc_fb_rate(df: pd.DataFrame) -> pd.Series:
    """Fly ball rate = fly_ball bb_type / all batted ball events."""
    bbe = df[df["bb_type"].notna() & (df["bb_type"] != "")]
    grouped = bbe.groupby("batter")
    fb    = grouped["bb_type"].apply(lambda s: (s == "fly_ball").sum())
    total = grouped["bb_type"].count()
    return safe_div(fb, total).rename("fb_rate")


def calc_bb_rate(df: pd.DataFrame) -> pd.Series:
    """Walk rate = (walk + intent_walk) / plate appearances."""
    pa_rows = df[df["events"].notna() & ~df["events"].isin(NON_PA_EVENTS)]
    grouped = pa_rows.groupby("batter")
    walks = grouped["events"].apply(
        lambda s: s.isin({"walk", "intent_walk"}).sum()
    )
    pa_count = grouped.size()
    return safe_div(walks, pa_count).rename("bb_rate")


def calc_k_rate(df: pd.DataFrame) -> pd.Series:
    """Strikeout rate = (strikeout + strikeout_double_play) / plate appearances."""
    pa_rows = df[df["events"].notna() & ~df["events"].isin(NON_PA_EVENTS)]
    grouped = pa_rows.groupby("batter")
    ks = grouped["events"].apply(
        lambda s: s.isin({"strikeout", "strikeout_double_play"}).sum()
    )
    pa_count = grouped.size()
    return safe_div(ks, pa_count).rename("k_rate")


def calc_bb_k_ratio(df: pd.DataFrame) -> pd.Series:
    """BB/K ratio = bb_rate / k_rate; 0 when k_rate is 0."""
    bb = calc_bb_rate(df)
    k  = calc_k_rate(df)
    ratio = bb.div(k).where(k > 0, other=0.0)
    return ratio.rename("bb_k_ratio")


def calc_o_swing_rate(df: pd.DataFrame) -> pd.Series:
    """
    O-Swing rate (Chase rate) = swings at pitches outside the strike zone
                                / all pitches outside the strike zone.
    Out-of-zone = Statcast zone 11–14.
    League average is ~30%; thresholds of 35% / 40% represent the top-25% /
    top-10% of chasers.
    """
    out_zone = df[df["zone"].isin([11, 12, 13, 14])]
    grouped  = out_zone.groupby("batter")
    swings   = grouped["description"].apply(lambda s: s.isin(SWING_DESCS).sum())
    total    = grouped["description"].count()
    return safe_div(swings, total).rename("o_swing_rate")


def calc_woba(df: pd.DataFrame) -> pd.Series:
    """
    Actual wOBA = sum of woba_value / plate appearances.
    woba_value is Statcast's linear-weight value for each PA-ending event.
    """
    pa_rows = df[df["events"].notna() & ~df["events"].isin(NON_PA_EVENTS)]
    grouped = pa_rows.groupby("batter")
    woba_sum = grouped["woba_value"].sum()
    pa_count = grouped.size()
    return safe_div(woba_sum, pa_count).rename("wOBA")


def calc_xwoba(df: pd.DataFrame) -> pd.Series:
    """
    Expected wOBA (xwOBA) per PA:
      - Batted balls (non-HR): use estimated_woba_using_speedangle, which models
        the expected run value based purely on exit velocity and launch angle.
      - HR, K, BB, HBP (true outcomes): use actual woba_value — these events are
        not luck-driven on contact, so we treat them at face value.
      - Any row where estimated_woba_using_speedangle is null: fall back to woba_value.

    xwOBA represents what a player "deserved" based on contact quality.
    xwOBA_gap = xwOBA - wOBA: positive = player underperformed their contact (unlucky).
    """
    if "estimated_woba_using_speedangle" not in df.columns:
        return calc_woba(df).rename("xwOBA")

    pa_rows = df[df["events"].notna() & ~df["events"].isin(NON_PA_EVENTS)].copy()
    pa_rows["xw"] = pa_rows["estimated_woba_using_speedangle"]
    # Fall back to actual woba_value where xwOBA is null or event is a true outcome
    fallback = pa_rows["xw"].isna() | pa_rows["events"].isin(TRUE_OUTCOME_EVENTS)
    pa_rows.loc[fallback, "xw"] = pa_rows.loc[fallback, "woba_value"]

    grouped = pa_rows.groupby("batter")
    xw_sum   = grouped["xw"].sum()
    pa_count = grouped.size()
    return safe_div(xw_sum, pa_count).rename("xwOBA")


# ---------------------------------------------------------------------------
# Name lookup
# ---------------------------------------------------------------------------

def _mlb_api_name(mlbam_id: int) -> str | None:
    """Fetch a player's full name from the MLB Stats API by MLBAM ID."""
    try:
        url = f"https://statsapi.mlb.com/api/v1/people/{mlbam_id}"
        with urllib.request.urlopen(url, timeout=5) as r:
            data = json.loads(r.read())
        return data["people"][0]["fullName"]
    except Exception:
        return None


def add_player_names(agg: pd.DataFrame) -> pd.DataFrame:
    """
    Add player names by MLBAM ID using a two-tier lookup:
      1. Chadwick Bureau via pybaseball playerid_reverse_lookup (most players)
      2. MLB Stats API fallback for any IDs not returned by the Chadwick Bureau
         (covers recently called-up and international players not yet indexed)
    """
    ids = agg.index.tolist()

    # ── Tier 1: Chadwick Bureau ────────────────────────────────────────────
    try:
        lookup = playerid_reverse_lookup(ids, key_type="mlbam")
        lookup["name"] = (
            lookup["name_first"].str.capitalize()
            + " "
            + lookup["name_last"].str.capitalize()
        )
        id_map = lookup[["key_mlbam", "name"]].rename(columns={"key_mlbam": "batter"})
    except Exception as exc:
        print(f"  Chadwick Bureau lookup failed ({exc}) -- will try MLB Stats API for all IDs")
        id_map = pd.DataFrame(columns=["batter", "name"])

    # ── Tier 2: MLB Stats API for any IDs the Chadwick Bureau missed ───────
    found   = set(id_map["batter"].tolist())
    missing = [pid for pid in ids if pid not in found]
    if missing:
        print(f"  {len(missing)} ID(s) not in Chadwick Bureau -- querying MLB Stats API ...")
        fallback_rows = []
        for pid in missing:
            full_name = _mlb_api_name(pid)
            if full_name:
                fallback_rows.append({"batter": pid, "name": full_name})
                print(f"    {pid}: {full_name}")
            else:
                print(f"    {pid}: (not found)")
        if fallback_rows:
            id_map = pd.concat(
                [id_map, pd.DataFrame(fallback_rows)],
                ignore_index=True,
            )

    # ── Merge names and move to front ─────────────────────────────────────
    agg = agg.reset_index().merge(id_map, on="batter", how="left").set_index("batter")
    cols = ["name"] + [c for c in agg.columns if c != "name"]
    return agg[cols]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print(f"Reading {INPUT_PATH} …")
    df = pd.read_csv(INPUT_PATH, low_memory=False)
    print(f"  Loaded {len(df):,} rows, {df['batter'].nunique():,} unique batters")

    print("Aggregating stats …")
    stats = [
        calc_pa(df),
        calc_babip(df),
        calc_hard_hit_rate(df),
        calc_barrel_rate(df),
        calc_sweet_spot_rate(df),
        calc_avg_exit_velocity(df),
        calc_z_contact_rate(df),
        calc_hr_fb_rate(df),
        calc_pull_rate(df),
        calc_o_swing_rate(df),
        calc_gb_rate(df),
        calc_fb_rate(df),
        calc_bb_rate(df),
        calc_k_rate(df),
        calc_bb_k_ratio(df),
        calc_woba(df),
        calc_xwoba(df),
    ]
    agg = pd.concat(stats, axis=1)

    # Apply a minimum PA filter so fringe samples don't pollute analysis
    MIN_PA = 10
    before = len(agg)
    agg = agg[agg["PA"] >= MIN_PA]
    print(f"  Batters with >= {MIN_PA} PA: {len(agg):,} (dropped {before - len(agg):,} with fewer)")

    print("Looking up player names …")
    agg = add_player_names(agg)

    # Round rate stats for readability
    rate_cols = ["BABIP", "hard_hit_rate", "barrel_rate", "sweet_spot_rate",
                 "z_contact_rate", "hr_fb_rate", "pull_rate", "o_swing_rate",
                 "gb_rate", "fb_rate", "bb_rate", "k_rate", "bb_k_ratio",
                 "wOBA", "xwOBA"]
    agg[rate_cols] = agg[rate_cols].round(3)

    agg.sort_values("PA", ascending=False, inplace=True)

    print(f"Saving {len(agg):,} rows to {OUTPUT_PATH} …")
    agg.to_csv(OUTPUT_PATH)
    print("Done.\n")
    print(agg.head(10).to_string())


if __name__ == "__main__":
    main()
