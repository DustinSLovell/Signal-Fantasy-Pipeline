"""
process_pitcher_stats.py
Reads pitchers_statcast.csv and pitchers_fangraphs.csv, computes per-pitcher
luck metrics, joins the two sources, and saves to pitcher_luck_input.csv.

Metrics computed from Statcast (pitch-level):
  BABIP allowed       — hits on balls in play / total balls in play
  hard_hit_rate       — exit velo >= 95 mph / all batted ball events
  barrel_rate         — barrels (launch_speed_angle == 6) / all BBE
  swstr_rate          — swinging strikes / total pitches thrown
  hr_fb_rate          — home runs / fly balls (Statcast bb_type)
  xERA                — approximated from xwOBA allowed (see formula below)

Metrics from FanGraphs:
  ERA, FIP, xFIP      — standard rate stats; FanGraphs is authoritative here
  lob_pct             — strand rate (LOB%)
  IP                  — used for the minimum-10-IP filter

Derived columns:
  ERA_minus_FIP       — positive = ERA running ahead of peripherals (lucky)
  ERA_minus_xERA      — positive = ERA running ahead of contact quality (lucky)

xERA formula (approximation):
  For each plate-appearance-ending event, use estimated_woba_using_speedangle
  (xwOBA on contact) where available, falling back to woba_value for home
  runs (where xwOBA is null in Statcast) and true-outcome events (K, BB, HBP).
  Then scale to an ERA-like value:
      xERA ≈ (mean_xwOBA_allowed − 0.320) × 33.0 + 4.00
  Baselines: lgxwOBA = 0.320, lgERA = 4.00, scale factor ≈ 33.0
  This is a reasonable proxy, not the official Baseball Savant xERA.
"""

import json
import os
import urllib.request

import pandas as pd

try:
    from pybaseball import playerid_reverse_lookup
except ImportError:
    raise SystemExit("pybaseball not found. Run: pip install pybaseball pandas")

BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
SC_PATH        = os.path.join(BASE_DIR, "pitchers_statcast.csv")
FG_PATH        = os.path.join(BASE_DIR, "pitchers_fangraphs.csv")
OUTPUT_PATH    = os.path.join(BASE_DIR, "pitcher_luck_input.csv")

MIN_IP = 7.0    # 7 IP catches all regular-use pitchers by ~18 days into the season
                # (previous threshold of 10.0 excluded ~70 relevant pitchers in April)

# ---------------------------------------------------------------------------
# Event sets (mirrored from process_stats.py for consistency)
# ---------------------------------------------------------------------------
CONTACT_DESCS    = {"hit_into_play", "foul", "foul_tip", "foul_bunt", "bunt_foul_tip"}
SWING_MISS_DESCS = {"swinging_strike", "swinging_strike_blocked", "missed_bunt"}

BIP_EVENTS     = {
    "single", "double", "triple",
    "field_out", "force_out", "grounded_into_double_play",
    "double_play", "fielders_choice", "fielders_choice_out",
    "field_error", "sac_fly", "sac_fly_double_play",
}
HIT_BIP_EVENTS = {"single", "double", "triple"}
NON_PA_EVENTS  = {"truncated_pa"}

# xERA scaling constants
LG_XWOBA = 0.320
LG_ERA   = 4.00
XERA_SCALE = 33.0   # derived from wOBA-to-runs linear weight environment

MIN_START_IP = 2.0   # per-start minimum: starts below this excluded from ERA/BABIP/xERA

# Out values per event — used to compute IP from Statcast
OUT_VALUES = {
    "strikeout": 1, "field_out": 1, "force_out": 1,
    "fielders_choice_out": 1, "sac_fly": 1, "sac_bunt": 1,
    "grounded_into_double_play": 2, "double_play": 2,
    "sac_fly_double_play": 2, "strikeout_double_play": 2,
    "sac_bunt_double_play": 2,
    "triple_play": 3,
}


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def safe_div(num: pd.Series, den: pd.Series) -> pd.Series:
    return num.div(den).where(den > 0, other=float("nan"))


def _runs_per_at_bat(df: pd.DataFrame) -> pd.DataFrame:
    """
    Attribute runs to the pitcher who faced each batter (at-bat level).

    bat_score in Statcast is the score BEFORE each pitch, so when a home run
    or RBI hit ends an at-bat, the run shows up on the NEXT pitch's bat_score.
    If a pitcher change happens between at-bats, the naive pitch-level lag
    wrongly credits that run to the incoming reliever.

    Fix: compare bat_score at the START of consecutive at-bats within the same
    batting-team half (game_pk + inning_topbot). This assigns each at-bat's run
    production to whichever pitcher COMPLETED that at-bat.

    Returns a DataFrame with columns: pitcher, game_pk, ab_runs
    (one row per at-bat that scored ≥ 1 run).
    """
    sc = df.sort_values(
        ["game_pk", "inning_topbot", "at_bat_number", "pitch_number"]
    ).copy()

    # First pitch of each at-bat gives the score BEFORE the at-bat starts
    ab_info = (
        sc.groupby(["game_pk", "inning_topbot", "at_bat_number"])
        .agg(
            start_score=("bat_score", "first"),
            # 'last' pitcher = who completed the at-bat (handles rare mid-AB changes)
            pitcher=("pitcher", "last"),
        )
        .reset_index()
        .sort_values(["game_pk", "inning_topbot", "at_bat_number"])
    )

    # Start score of the NEXT at-bat (within same batting-team half) = score after this AB
    ab_info["next_start"] = ab_info.groupby(
        ["game_pk", "inning_topbot"]
    )["start_score"].shift(-1)

    # For the LAST at-bat in each team's game half, fall back to max(bat_score)
    # across all pitches in that at-bat (handles walk-off/end-of-game scoring)
    last_ab_max = (
        sc.groupby(["game_pk", "inning_topbot", "at_bat_number"])["bat_score"]
        .max()
        .rename("max_score")
        .reset_index()
    )
    ab_info = ab_info.merge(
        last_ab_max, on=["game_pk", "inning_topbot", "at_bat_number"], how="left"
    )
    ab_info["end_score"] = ab_info["next_start"].fillna(ab_info["max_score"])
    ab_info["ab_runs"] = (ab_info["end_score"] - ab_info["start_score"]).clip(lower=0)

    return ab_info[["pitcher", "game_pk", "inning_topbot", "at_bat_number", "ab_runs"]]


def compute_per_start_stats(df: pd.DataFrame) -> pd.DataFrame:
    """
    Per-start (pitcher × game_pk) statistics for 2-IP filtering and volatility analysis.

    Columns returned:
        pitcher, game_pk, start_ip, start_ra, start_era (RA9),
        qualifying (start_ip >= MIN_START_IP),
        is_qs     (start_ip >= 6.0 AND start_ra <= 3),
        is_disaster (start_era > 10.0 AND qualifying)
    """
    # IP per start
    pa = df[df["events"].notna()].copy()
    pa["_outs"] = pa["events"].map(OUT_VALUES).fillna(0)
    ip_per_start = (
        pa.groupby(["pitcher", "game_pk"])["_outs"]
        .sum()
        .reset_index()
        .rename(columns={"_outs": "total_outs"})
    )
    ip_per_start["start_ip"] = ip_per_start["total_outs"] / 3.0

    # Runs per start using at-bat-level attribution (fixes pitcher-change boundary bug)
    ab_runs = _runs_per_at_bat(df)
    runs_per_start = (
        ab_runs.groupby(["pitcher", "game_pk"])["ab_runs"]
        .sum()
        .reset_index()
        .rename(columns={"ab_runs": "start_ra"})
    )

    starts = ip_per_start.merge(runs_per_start, on=["pitcher", "game_pk"], how="left")
    starts["start_ra"] = starts["start_ra"].fillna(0.0)
    starts["start_era"] = (
        (starts["start_ra"] / (starts["start_ip"] / 9))
        .where(starts["start_ip"] > 0)
        .round(2)
    )
    starts["qualifying"]  = starts["start_ip"] >= MIN_START_IP
    starts["is_qs"]       = (starts["start_ip"] >= 6.0) & (starts["start_ra"] <= 3)
    starts["is_disaster"] = (starts["start_era"] > 10.0) & starts["qualifying"]

    return starts[["pitcher", "game_pk", "start_ip", "start_ra",
                   "start_era", "qualifying", "is_qs", "is_disaster"]]


# ---------------------------------------------------------------------------
# Statcast-derived stats (all grouped by pitcher MLBAM ID)
# ---------------------------------------------------------------------------

def calc_babip_allowed(df: pd.DataFrame) -> pd.Series:
    """BABIP allowed = hits on BIP / total BIP. HR, K, BB, HBP excluded."""
    bip = df[df["events"].isin(BIP_EVENTS | HIT_BIP_EVENTS)]
    grouped   = bip.groupby("pitcher")
    hits_bip  = grouped["events"].apply(lambda s: s.isin(HIT_BIP_EVENTS).sum())
    total_bip = grouped["events"].apply(lambda s: s.isin(BIP_EVENTS | HIT_BIP_EVENTS).sum())
    return safe_div(hits_bip, total_bip).rename("BABIP_allowed")


def calc_hard_hit_rate(df: pd.DataFrame) -> pd.Series:
    """Hard hit rate allowed = BBE with exit velo >= 95 mph / all BBE."""
    bbe     = df[df["launch_speed"].notna()]
    grouped = bbe.groupby("pitcher")
    hard    = grouped["launch_speed"].apply(lambda s: (s >= 95).sum())
    total   = grouped["launch_speed"].count()
    return safe_div(hard, total).rename("hard_hit_rate_allowed")


def calc_barrel_rate(df: pd.DataFrame) -> pd.Series:
    """Barrel rate allowed = barrels (launch_speed_angle == 6) / all BBE."""
    bbe     = df[df["launch_speed"].notna()]
    grouped = bbe.groupby("pitcher")
    barrels = grouped["launch_speed_angle"].apply(lambda s: (s == 6).sum())
    total   = grouped["launch_speed"].count()
    return safe_div(barrels, total).rename("barrel_rate_allowed")


def calc_swstr_rate(df: pd.DataFrame) -> pd.Series:
    """
    Swinging-strike rate = swinging strikes / total pitches.
    Counts swinging_strike and swinging_strike_blocked (catcher blocked it).
    Total is every row since each row is one pitch.
    """
    grouped   = df.groupby("pitcher")
    swstr     = grouped["description"].apply(
        lambda s: s.isin({"swinging_strike", "swinging_strike_blocked"}).sum()
    )
    total_pitches = grouped["description"].count()
    return safe_div(swstr, total_pitches).rename("swstr_rate")


def calc_hr_fb_rate(df: pd.DataFrame) -> pd.Series:
    """
    HR/FB rate allowed = home runs / fly balls.
    In Statcast, HR have bb_type == 'fly_ball', so the denominator already
    includes HR (same definition used for hitters in process_stats.py).
    """
    pa_rows  = df[df["events"].notna()]
    grouped  = pa_rows.groupby("pitcher")
    hr_count = grouped["events"].apply(lambda s: (s == "home_run").sum())
    fb_count = grouped["bb_type"].apply(lambda s: (s == "fly_ball").sum())
    return safe_div(hr_count, fb_count).rename("hr_fb_rate")


def calc_xera(df: pd.DataFrame) -> pd.Series:
    """
    Approximate xERA from xwOBA allowed per plate appearance.

    For each PA-ending event:
      - Use estimated_woba_using_speedangle (xwOBA on contact) where non-null.
        This covers non-HR batted balls and captures contact quality.
      - Fall back to woba_value for home runs (xwOBA is null in Statcast for HR)
        and true-outcome events (K=0, BB≈0.69, HBP≈0.72). These outcomes are
        not pitch-quality-luck events, so using actual wOBA is appropriate.
    Scale: xERA ≈ (mean_xwOBA − 0.320) × 33.0 + 4.00
    """
    pa_rows = df[
        df["events"].notna() & ~df["events"].isin(NON_PA_EVENTS)
    ].copy()

    # Prefer xwOBA on contact; fall back to actual wOBA for everything else
    pa_rows["xwoba_pa"] = pa_rows["estimated_woba_using_speedangle"].fillna(
        pa_rows["woba_value"]
    )

    xwoba_mean = pa_rows.groupby("pitcher")["xwoba_pa"].mean()
    xera = (xwoba_mean - LG_XWOBA) * XERA_SCALE + LG_ERA
    return xera.rename("xERA")


# ---------------------------------------------------------------------------
# Statcast-native fallbacks for IP, RA9, FIP, LOB%
# These are used when FanGraphs data is unavailable.
# ---------------------------------------------------------------------------

def calc_ip_statcast(df: pd.DataFrame) -> pd.Series:
    """
    Innings pitched from Statcast out events.
    Each PA-ending event is mapped to its out value (1, 2, or 3).
    IP = total_outs / 3  (decimal, not baseball notation).
    """
    pa_rows = df[df["events"].notna()].copy()
    pa_rows["_outs"] = pa_rows["events"].map(OUT_VALUES).fillna(0)
    total_outs = pa_rows.groupby("pitcher")["_outs"].sum()
    return (total_outs / 3).rename("IP_sc")


def calc_runs_allowed(df: pd.DataFrame) -> pd.Series:
    """
    Runs allowed per pitcher using at-bat-level attribution.
    See _runs_per_at_bat() for the reason this is preferred over pitch-level lag.
    """
    ab_runs = _runs_per_at_bat(df)
    return ab_runs.groupby("pitcher")["ab_runs"].sum().rename("RA_sc")


def calc_fip_statcast(df: pd.DataFrame, ip_sc: pd.Series) -> pd.Series:
    """
    FIP from Statcast event counts.
    cFIP is derived from the league totals in this same dataset so the
    constant self-calibrates to the current run environment.
    FIP = (13*HR + 3*(BB+HBP) - 2*K) / IP + cFIP
    """
    pa = df[df["events"].notna()]
    grp = pa.groupby("pitcher")["events"]

    hr  = grp.apply(lambda s: (s == "home_run").sum())
    bb  = grp.apply(lambda s: (s == "walk").sum())
    hbp = grp.apply(lambda s: (s == "hit_by_pitch").sum())
    k   = grp.apply(lambda s: s.isin({"strikeout", "strikeout_double_play"}).sum())

    # League totals for cFIP
    lg_hr, lg_bb, lg_hbp, lg_k = hr.sum(), bb.sum(), hbp.sum(), k.sum()
    lg_ip = ip_sc.sum()
    lg_fip_num = (13 * lg_hr + 3 * (lg_bb + lg_hbp) - 2 * lg_k) / lg_ip
    cfip = LG_ERA - lg_fip_num

    fip_raw = (13 * hr + 3 * (bb + hbp) - 2 * k) / ip_sc + cfip
    return fip_raw.rename("FIP_sc")


def calc_lob_pct_statcast(df: pd.DataFrame, ra_sc: pd.Series) -> pd.Series:
    """
    LOB% from Statcast.
    Formula: (H + BB + HBP - R) / (H + BB + HBP - 1.4*HR)
    where H = non-HR hits, R = runs allowed (from calc_runs_allowed).
    """
    pa = df[df["events"].notna()]
    grp = pa.groupby("pitcher")["events"]

    hits = grp.apply(lambda s: s.isin({"single", "double", "triple"}).sum())
    bb   = grp.apply(lambda s: (s == "walk").sum())
    hbp  = grp.apply(lambda s: (s == "hit_by_pitch").sum())
    hr   = grp.apply(lambda s: (s == "home_run").sum())

    reach  = hits + bb + hbp
    num    = reach - ra_sc
    denom  = reach - 1.4 * hr

    return safe_div(num, denom).clip(0, 1).rename("lob_pct_sc")


# ---------------------------------------------------------------------------
# Name + FanGraphs ID lookup
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


def _is_blank_name(name) -> bool:
    """True if a Chadwick-returned name is missing or effectively empty."""
    if name is None:
        return True
    s = str(name).strip().lower()
    return s in ("", "nan", "none", "nan nan", " ")


def build_id_map(mlbam_ids: list) -> pd.DataFrame:
    """
    Return a DataFrame mapping key_mlbam → name + key_fangraphs.

    Two-tier lookup:
      1. Chadwick Bureau via pybaseball playerid_reverse_lookup — covers most
         established players. Returns name_first + name_last + key_fangraphs.
      2. MLB Stats API fallback for any ID that either:
           a) was not returned by the Chadwick Bureau at all (new callups not
              yet indexed), OR
           b) was returned but with a blank/null name (Chadwick has the record
              but the name fields are empty — produces "Nan Nan" without this fix).
         The MLB Stats API always has the correct full name for any active player.
    """
    try:
        lookup = playerid_reverse_lookup(mlbam_ids, key_type="mlbam")
        lookup["name"] = (
            lookup["name_first"].str.capitalize()
            + " "
            + lookup["name_last"].str.capitalize()
        )
        id_map = lookup[["key_mlbam", "key_fangraphs", "name"]].copy()
    except Exception as exc:
        print(f"  Chadwick Bureau lookup failed ({exc}) — querying MLB Stats API for all IDs")
        id_map = pd.DataFrame(columns=["key_mlbam", "key_fangraphs", "name"])

    # IDs completely absent from the Chadwick result
    found_ids = set(id_map["key_mlbam"].tolist())
    not_returned = [pid for pid in mlbam_ids if pid not in found_ids]

    # IDs that Chadwick returned but with a blank/null name (new callup stubs)
    blank_name_ids = id_map.loc[
        id_map["name"].apply(_is_blank_name), "key_mlbam"
    ].tolist()

    # Remove blank-name rows so the API result replaces them cleanly
    if blank_name_ids:
        id_map = id_map[~id_map["key_mlbam"].isin(blank_name_ids)]

    missing = not_returned + blank_name_ids
    if missing:
        source = "not in Chadwick Bureau or had blank name"
        print(f"  {len(missing)} ID(s) {source} — querying MLB Stats API …")
        fallback_rows = []
        for pid in missing:
            full_name = _mlb_api_name(pid)
            if full_name:
                fallback_rows.append({"key_mlbam": pid, "key_fangraphs": pd.NA, "name": full_name})
                print(f"    {pid}: {full_name}")
            else:
                print(f"    {pid}: (not found — will appear as blank in dashboard)")
        if fallback_rows:
            id_map = pd.concat(
                [id_map, pd.DataFrame(fallback_rows)],
                ignore_index=True,
            )

    return id_map


# ---------------------------------------------------------------------------
# FanGraphs percentage normalization
# ---------------------------------------------------------------------------

def _normalize_pct(series: pd.Series) -> pd.Series:
    """
    FanGraphs rate columns (LOB%, SwStr%, etc.) should arrive as 0-1 decimals
    via pybaseball. If the max is > 1 the data came back as 0-100; divide by 100.
    """
    if series.dropna().empty:
        return series
    if series.dropna().max() > 1.5:   # clear sign of 0-100 scale
        return series / 100.0
    return series


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # ---- Load Statcast ----
    print(f"Reading {SC_PATH} …")
    sc = pd.read_csv(SC_PATH, low_memory=False)
    print(f"  Loaded {len(sc):,} rows, {sc['pitcher'].nunique():,} unique pitchers")

    # ---- Per-start stats + 2 IP filter ----
    print("Computing per-start statistics …")
    start_stats = compute_per_start_stats(sc)
    n_total_starts    = len(start_stats)
    n_excluded        = int((~start_stats["qualifying"]).sum())
    n_pitchers_excl   = start_stats[~start_stats["qualifying"]]["pitcher"].nunique()
    print(f"  Total pitcher-starts  : {n_total_starts:,}")
    print(f"  Excluded (< {MIN_START_IP} IP)  : {n_excluded:,} starts across {n_pitchers_excl} pitchers")
    print(f"  ERA / BABIP / xERA computed from qualifying starts only")

    start_stats_path = os.path.join(BASE_DIR, "pitcher_per_start_stats.csv")
    start_stats.to_csv(start_stats_path, index=False)
    print(f"  Per-start data saved  : {start_stats_path}")

    # Top excluded starts for transparency
    excl = (
        start_stats[~start_stats["qualifying"]]
        .sort_values("start_ip", ascending=True)
        .head(10)
    )
    if not excl.empty:
        print("  Excluded starts sample (lowest IP):")
        for _, row in excl.iterrows():
            print(f"    pitcher={int(row['pitcher'])}  "
                  f"game={row['game_pk']}  "
                  f"IP={row['start_ip']:.1f}  "
                  f"RA={int(row['start_ra'])}  "
                  f"RA9={row['start_era'] if pd.notna(row['start_era']) else 'n/a'}")

    # Build qualifying-starts-only subset for ERA/BABIP/xERA
    qual_pairs = (
        start_stats.loc[start_stats["qualifying"], ["pitcher", "game_pk"]]
        .assign(_q=True)
    )
    sc_merged = sc.merge(qual_pairs, on=["pitcher", "game_pk"], how="left")
    sc_qual   = sc[sc_merged["_q"].fillna(False).values].copy()
    print(f"  Qualifying subset     : {len(sc_qual):,} rows / {sc_qual['pitcher'].nunique():,} pitchers")

    # ---- Compute Statcast metrics ----
    print("Aggregating Statcast metrics …")

    # ERA denominator and numerator for qualifying starts come directly from
    # per-start stats (computed on full sc). This avoids the sc_qual subset
    # gap problem: sc_qual has missing at_bat_numbers (non-qualifying pitchers
    # are absent), so comparing consecutive ABs in that subset spans multiple
    # real ABs and accumulates stray runs onto the wrong pitcher.
    ip_sc_adj = (
        start_stats[start_stats["qualifying"]]
        .groupby("pitcher")["start_ip"]
        .sum()
        .rename("IP_sc_adj")
    )
    ra_sc_adj = (
        start_stats[start_stats["qualifying"]]
        .groupby("pitcher")["start_ra"]
        .sum()
        .rename("RA_sc")
    )
    fip_sc     = calc_fip_statcast(sc_qual, ip_sc_adj)
    lob_sc     = calc_lob_pct_statcast(sc_qual, ra_sc_adj)
    era_adj_sc = (ra_sc_adj / (ip_sc_adj / 9)).where(ip_sc_adj > 0).round(2).rename("ERA_adj_sc")

    # Total IP — all starts (what players see on the dashboard)
    ip_sc_all = calc_ip_statcast(sc).rename("IP_sc")

    # FIP fallback for pure relievers who never reach 2 IP per outing — computed
    # from all appearances so they're included in the cFIP self-calibration pool.
    fip_sc_all = calc_fip_statcast(sc, calc_ip_statcast(sc)).rename("FIP_sc_all")

    # Fallback metrics for pure relievers who never reach 2 IP (all appearances)
    babip_all = calc_babip_allowed(sc).rename("BABIP_allowed_all")
    xera_all  = calc_xera(sc).rename("xERA_all")
    ra_sc_all = calc_runs_allowed(sc)
    era_all_sc = (ra_sc_all / (calc_ip_statcast(sc) / 9)).where(calc_ip_statcast(sc) > 0).round(2).rename("ERA_all_sc")

    sc_stats = pd.concat([
        calc_babip_allowed(sc_qual),     # 2 IP filtered: outcome metric
        babip_all,                       # fallback for pure relievers
        calc_hard_hit_rate(sc),          # all pitches: contact-quality metric
        calc_barrel_rate(sc),            # all pitches
        calc_swstr_rate(sc),             # all pitches
        calc_hr_fb_rate(sc_qual),        # 2 IP filtered: per-inning rate distorted by short exits
        calc_xera(sc_qual),              # 2 IP filtered: used in ERA-xERA gap
        xera_all,                        # fallback for pure relievers
        ip_sc_all,                       # total IP
        ip_sc_adj.rename("IP_sc_adj"),   # qualifying-start IP (for reliever detection)
        ra_sc_adj.rename("RA_sc"),       # qualifying-start runs
        fip_sc,
        fip_sc_all,                      # FIP from all appearances (fallback for pure relievers)
        lob_sc,
        era_adj_sc,                      # adjusted Statcast ERA (qualifying starts)
        era_all_sc,                      # fallback ERA for pure relievers
    ], axis=1)

    # ---- Load FanGraphs ----
    print(f"Reading {FG_PATH} …")
    try:
        fg = pd.read_csv(FG_PATH)
        if fg.empty or len(fg.columns) == 0:
            raise ValueError("empty file")
        print(f"  Loaded {len(fg):,} pitchers from FanGraphs")
    except (pd.errors.EmptyDataError, ValueError):
        print("  FanGraphs file is empty — Statcast fallbacks will supply ERA, FIP, IP, LOB%")
        fg = pd.DataFrame()

    # Normalize any percentage columns that might have come back as 0-100
    for col in ["LOB%", "SwStr%", "HR/FB", "K%", "BB%"]:
        if col in fg.columns:
            fg[col] = _normalize_pct(fg[col])

    # Rename FanGraphs columns to clean, consistent names
    fg = fg.rename(columns={
        "LOB%":  "lob_pct",
        "SwStr%": "fg_swstr_rate",   # kept for reference; swstr_rate from Statcast is primary
        "HR/FB":  "fg_hr_fb_rate",   # same — Statcast-computed hr_fb_rate is primary
        "K%":    "k_pct",
        "BB%":   "bb_pct",
    })

    # ---- ID lookup: MLBAM → name + FanGraphs ID ----
    print("Looking up player names and FanGraphs IDs …")
    mlbam_ids  = sc_stats.index.tolist()
    id_map     = build_id_map(mlbam_ids)

    # Merge name and key_fangraphs onto the Statcast aggregation
    agg = sc_stats.reset_index()   # 'pitcher' becomes a column
    if not id_map.empty:
        id_map["key_mlbam"] = id_map["key_mlbam"].astype("Int64")
        agg["pitcher"]      = agg["pitcher"].astype("Int64")
        agg = agg.merge(
            id_map,
            left_on="pitcher",
            right_on="key_mlbam",
            how="left",
        ).drop(columns=["key_mlbam"])
    else:
        agg["name"]           = float("nan")
        agg["key_fangraphs"]  = float("nan")

    # ---- Join FanGraphs stats ----
    print("Joining FanGraphs stats …")
    if "IDfg" in fg.columns and "key_fangraphs" in agg.columns:
        # Both IDs may be float (NaN-bearing); cast to nullable Int64 for a clean join
        fg["IDfg"]              = pd.to_numeric(fg["IDfg"],              errors="coerce").astype("Int64")
        agg["key_fangraphs"]    = pd.to_numeric(agg["key_fangraphs"],    errors="coerce").astype("Int64")

        fg_cols = [c for c in [
            "IDfg", "Team", "G", "GS", "IP", "TBF",
            "ERA", "FIP", "xFIP",
            "lob_pct", "fg_swstr_rate", "fg_hr_fb_rate", "k_pct", "bb_pct",
        ] if c in fg.columns]

        agg = agg.merge(
            fg[fg_cols],
            left_on="key_fangraphs",
            right_on="IDfg",
            how="left",
        ).drop(columns=["IDfg"], errors="ignore")
    else:
        print("  WARNING: Could not join FanGraphs data — IDfg or key_fangraphs missing")
        for col in ["Team", "G", "GS", "IP", "TBF", "ERA", "FIP", "xFIP",
                    "lob_pct", "fg_swstr_rate", "fg_hr_fb_rate", "k_pct", "bb_pct"]:
            agg[col] = float("nan")

    # ---- Coalesce ERA -------------------------------------------------------
    # Primary: ERA_adj_sc — Statcast RA9 from qualifying starts only (2 IP min).
    #          This removes inflation from early exits (e.g. Opening Day disasters).
    # Fallback: FanGraphs ERA (kept as ERA_fg for reference); used only when
    #           Statcast data is missing (player has no qualifying starts yet).
    era_adj = agg["ERA_adj_sc"] if "ERA_adj_sc" in agg.columns else pd.Series(dtype=float, index=agg.index)
    era_all = agg["ERA_all_sc"] if "ERA_all_sc" in agg.columns else pd.Series(dtype=float, index=agg.index)

    # Pure-reliever detection: if qualifying IP (2+ IP appearances) is < 50% of
    # total IP, ERA_adj_sc captures only a minority of their real workload and
    # becomes unrepresentative (e.g. Ashby: 4.3 of 15 IP qualifying → ERA_adj 6.23
    # vs ERA_all 4.20). Use ERA_all_sc for those pitchers instead.
    if "IP_sc_adj" in agg.columns and "IP_sc" in agg.columns:
        qual_ratio = agg["IP_sc_adj"].fillna(0) / agg["IP_sc"].clip(lower=0.01)
        reliever_mask = qual_ratio < 0.50
        n_reliever = int(reliever_mask.sum())
        if n_reliever:
            print(f"  Pure-reliever ERA override: {n_reliever} pitchers using ERA_all_sc "
                  f"(qualifying IP < 50% of total IP)")
        era_for_scoring = era_adj.where(~reliever_mask, era_all)
    else:
        era_for_scoring = era_adj

    if "ERA" in agg.columns and not agg["ERA"].isna().all():
        agg["ERA_fg"] = agg["ERA"]
        agg["ERA"] = era_for_scoring.reindex(agg.index).fillna(era_all.reindex(agg.index)).fillna(agg["ERA_fg"]).round(2)
    else:
        # No FG data — use reliever-aware ERA selection
        agg["ERA"] = era_for_scoring.reindex(agg.index).fillna(era_all.reindex(agg.index)).round(2)

    # For BABIP and xERA: fill relievers' NaN with all-appearances fallback
    if "BABIP_allowed" in agg.columns and "BABIP_allowed_all" in agg.columns:
        agg["BABIP_allowed"] = agg["BABIP_allowed"].fillna(agg["BABIP_allowed_all"])
    if "xERA" in agg.columns and "xERA_all" in agg.columns:
        agg["xERA"] = agg["xERA"].fillna(agg["xERA_all"])

    _fip_sc_all = agg["FIP_sc_all"] if "FIP_sc_all" in agg.columns else pd.Series(dtype=float, index=agg.index)
    if "FIP" not in agg.columns or agg["FIP"].isna().all():
        agg["FIP"] = agg["FIP_sc"].fillna(_fip_sc_all).round(2)
    else:
        agg["FIP"] = agg["FIP"].fillna(agg["FIP_sc"]).fillna(_fip_sc_all).round(2)
    n_fip_null = int(agg["FIP"].isna().sum())
    print(f"  FIP null after coalesce: {n_fip_null} pitchers")

    if "IP" not in agg.columns or agg["IP"].isna().all():
        agg["IP"] = agg["IP_sc"].round(1)
    else:
        agg["IP"] = agg["IP"].fillna(agg["IP_sc"].round(1))

    if "lob_pct" not in agg.columns or agg["lob_pct"].isna().all():
        agg["lob_pct"] = agg["lob_pct_sc"].round(3)
    else:
        agg["lob_pct"] = agg["lob_pct"].fillna(agg["lob_pct_sc"].round(3))

    # Recompute gap columns after coalescing (ERA/FIP/xERA now always populated)
    agg["ERA_minus_FIP"]  = (agg["ERA"] - agg["FIP"]).round(2)
    if "xERA" in agg.columns:
        agg["ERA_minus_xERA"] = (agg["ERA"] - agg["xERA"]).round(2)

    # ---- Apply minimum-IP filter ----
    # FanGraphs IP uses baseball notation: 9.2 = 9⅔ innings.
    # Filtering >= 10.0 correctly retains only pitchers with ≥ 10 full innings.
    before = len(agg)
    if "IP" in agg.columns:
        agg = agg[agg["IP"].notna() & (agg["IP"] >= MIN_IP)]
        print(f"  Pitchers with >= {MIN_IP} IP: {len(agg):,} "
              f"(dropped {before - len(agg):,} with fewer)")
    else:
        print("  WARNING: IP column not found — minimum-IP filter not applied")

    # ---- Derived gap columns ----
    if {"ERA", "FIP"}.issubset(agg.columns):
        agg["ERA_minus_FIP"]  = (agg["ERA"] - agg["FIP"]).round(2)
    if {"ERA", "xERA"}.issubset(agg.columns):
        agg["ERA_minus_xERA"] = (agg["ERA"] - agg["xERA"]).round(2)

    # ---- Round rate stats ----
    rate_cols = [
        "BABIP_allowed", "hard_hit_rate_allowed", "barrel_rate_allowed",
        "swstr_rate", "hr_fb_rate", "xERA",
        "lob_pct", "fg_swstr_rate", "fg_hr_fb_rate", "k_pct", "bb_pct",
    ]
    for col in rate_cols:
        if col in agg.columns:
            agg[col] = agg[col].round(3)

    for col in ["ERA", "FIP", "xFIP", "ERA_minus_FIP", "ERA_minus_xERA"]:
        if col in agg.columns:
            agg[col] = agg[col].round(2)

    # ---- Column order ----
    ordered = [
        "pitcher", "name", "Team",
        "IP", "ERA", "ERA_fg", "ERA_adj_sc", "FIP", "xFIP", "xERA",
        "ERA_minus_FIP", "ERA_minus_xERA",
        "BABIP_allowed", "lob_pct", "hr_fb_rate",
        "hard_hit_rate_allowed", "barrel_rate_allowed", "swstr_rate",
        "k_pct", "bb_pct",
        "G", "GS", "TBF",
        "key_fangraphs", "fg_swstr_rate", "fg_hr_fb_rate",
    ]
    ordered = [c for c in ordered if c in agg.columns]
    remaining = [c for c in agg.columns if c not in ordered]
    agg = agg[ordered + remaining]

    # Sort by IP descending (most-used pitchers first)
    if "IP" in agg.columns:
        agg.sort_values("IP", ascending=False, inplace=True)
    agg.reset_index(drop=True, inplace=True)

    # ---- Save ----
    print(f"Saving {len(agg):,} rows to {OUTPUT_PATH} …")
    agg.to_csv(OUTPUT_PATH, index=False)
    print("Done.\n")

    # ---- Preview ----
    preview_cols = [c for c in [
        "name", "IP", "ERA", "FIP", "xFIP", "xERA",
        "ERA_minus_FIP", "ERA_minus_xERA",
        "BABIP_allowed", "lob_pct", "hard_hit_rate_allowed", "barrel_rate_allowed",
    ] if c in agg.columns]
    print(agg[preview_cols].head(10).to_string(index=False))

    # ---- Summary counts ----
    print(f"\nTotal pitchers: {len(agg):,}")
    if "ERA_minus_FIP" in agg.columns:
        lucky   = (agg["ERA_minus_FIP"] < -0.50).sum()
        unlucky = (agg["ERA_minus_FIP"] >  0.50).sum()
        print(f"ERA-FIP > +0.50 (ERA running high, likely unlucky): {unlucky}")
        print(f"ERA-FIP < -0.50 (ERA running low, likely lucky)   : {lucky}")

    # ---- 2 IP filter impact: most affected pitchers ----
    if "ERA_fg" in agg.columns and "ERA" in agg.columns:
        agg["_era_delta"] = (agg["ERA_fg"] - agg["ERA"]).abs()
        affected = (
            agg[agg["_era_delta"] > 0.20]
            .sort_values("_era_delta", ascending=False)
            .head(8)
        )
        if not affected.empty:
            print(f"\n2 IP filter meaningfully changed ERA (delta > 0.20) for {len(affected)} pitchers:")
            show_cols = [c for c in ["name", "IP", "ERA", "ERA_fg", "_era_delta", "FIP", "BABIP_allowed"] if c in affected.columns]
            print(affected[show_cols].to_string(index=False))
        agg.drop(columns=["_era_delta"], inplace=True)


if __name__ == "__main__":
    main()
