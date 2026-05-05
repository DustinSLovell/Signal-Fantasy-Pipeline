"""
weekly_update.py
================
Calls tracker for The Signal Fantasy. Tracks wOBA/xwOBA (hitters) or ERA/FIP
(pitchers) movement against initial buy/sell calls. Generates article-ready
markdown output with mechanism classification and running accuracy.

Usage:
    python weekly_update.py                    # summary table
    python weekly_update.py --init             # initialize from current luck CSVs
    python weekly_update.py --update           # add new week columns + recompute
    python weekly_update.py --report           # markdown article output
    python weekly_update.py --report --top N   # limit to N players per category

Column notes:
    For hitters: week1_woba = wOBA,  week1_xwoba = xwOBA
    For pitchers: week1_woba = ERA,  week1_xwoba = FIP
    Delta sign convention: POSITIVE always means "prediction moving toward correct"
    (wOBA up for buys, ERA down for pitchers on buy calls → positive delta)
"""

import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

BASE_DIR          = Path(__file__).parent
TRACKER           = BASE_DIR / "data" / "calls_tracker.csv"
LUCK_H            = BASE_DIR / "luck_scores.csv"
LUCK_P            = BASE_DIR / "pitcher_luck_scores.csv"
OWNERSHIP_HISTORY = BASE_DIR / "data" / "ownership_history.json"
CALL_DATE         = "2026-04-22"   # Week 1 article date

# Significance thresholds (from spec)
WOBA_THRESH  = 0.020   # wOBA movement to classify
XWOBA_THRESH = 0.015   # xwOBA movement to classify

# Luck normalization thresholds for refuted gate.
# A call is only marked "refuted" if the underlying luck signal has faded.
# Luck still strongly positive/negative = signal still active → "still_waiting".
# Thresholds match production Slight Buy/Sell floors.
LUCK_NORMALIZE_BUY  =  0.100   # below this → buy signal effectively gone
LUCK_NORMALIZE_SELL = -0.085   # above this → sell signal effectively gone

# Rolling 4-week window luck deepening threshold
LUCK_DEEPEN_THRESH  =  0.030   # luck score moved this much → signal deepening

# Week 10 = mid-June: when Track 1 official accuracy reporting begins
TRACK1_RESOLUTION_WEEK = 10

# Rolling window age / urgency constants
WINDOW_ACTIVE_MAX   = 4    # weeks 1-4: active resolution window
WINDOW_EXTENDED_MAX = 8    # weeks 5-8: extended window
AVG_LUCK_DECAY_PER_WEEK = 0.050  # assumed weekly luck decay rate for ETA calculation

# Mechanism → human-readable status label and emoji
# Mechanisms:
#   BUY calls:  results_improving | contact_deteriorating | confirmed | refuted
#               still_waiting | insufficient_movement
#   SELL calls: results_declining | contact_improving | genuine_decline | refuted
#               still_waiting | insufficient_movement
STATUS_LABEL = {
    "results_improving":     "Normalizing",
    "results_declining":     "Normalizing",
    "contact_deteriorating": "Re-evaluate",
    "contact_improving":     "Re-evaluate",
    "confirmed":             "Confirmed",
    "genuine_decline":       "Confirmed",
    "refuted":               "Refuted",
    "still_waiting":         "Signal Active",  # luck intact, results not yet moving
    "insufficient_movement": "Watch",
}
STATUS_EMOJI = {
    "results_improving":     "✅",
    "results_declining":     "✅",
    "contact_deteriorating": "⚠️",
    "contact_improving":     "⚠️",
    "confirmed":             "✅",
    "genuine_decline":       "✅",
    "refuted":               "❌",
    "still_waiting":         "⏳",
    "insufficient_movement": "⏳",
}

# Window signal labels for rolling 4-week view
WINDOW_LABEL = {
    "confirming":       "Window confirming ✅",
    "deepening":        "Signal deepening ↑",
    "still_waiting":    "Still waiting ⏳",
    "refuted_4wk":      "4-wk window wrong ⚠",
    "insufficient_data":"Not enough data",
}

BUY_VERDICTS  = {"Buy low", "Slight buy"}
SELL_VERDICTS = {"Sell high", "Slight sell"}

# Name overrides: entries where title() alone produces wrong output
_NAME_FIXES: dict[str, str] = {
    "Tj Friedl":          "TJ Friedl",
    "J. P. Crawford":     "J.P. Crawford",
    "J. p. Crawford":     "J.P. Crawford",
    "Pete Crow-armstrong":"Pete Crow-Armstrong",
    "Jung hoo Lee":       "Jung Hoo Lee",
    "Pete Crow-Armstrong":"Pete Crow-Armstrong",  # idempotent
}


def _clean_name(name: str) -> str:
    """Title-case a player name with overrides for initials and hyphenated names."""
    if name in _NAME_FIXES:
        return _NAME_FIXES[name]
    fixed = name.title()
    return _NAME_FIXES.get(fixed, fixed)


# ── helpers ──────────────────────────────────────────────────────────────────

def _load_current_hitters() -> pd.DataFrame:
    df = pd.read_csv(LUCK_H)
    return df[["batter", "name", "luck_score", "wOBA", "xwOBA", "verdict"]].copy()


def _load_current_pitchers() -> pd.DataFrame:
    df = pd.read_csv(LUCK_P)
    return df[["pitcher", "name", "luck_score", "ERA", "FIP", "verdict"]].copy()


def _week_cols(df: pd.DataFrame) -> list[str]:
    """Return sorted list of all weekN_luck columns."""
    return sorted([c for c in df.columns if c.startswith("week") and c.endswith("_luck")],
                  key=lambda c: int(c.split("_")[0][4:]))


def _current_week_num(df: pd.DataFrame) -> int:
    wc = _week_cols(df)
    return int(wc[-1].split("_")[0][4:]) if wc else 0


def _compute_deltas(df: pd.DataFrame) -> pd.DataFrame:
    """Recompute woba_delta, xwoba_delta, rolling window columns, mechanism, prediction_correct."""
    wc = _week_cols(df)
    if not wc:
        return df

    latest = wc[-1].split("_")[0]  # e.g. "week8"
    sign   = df["type"].map(lambda t: -1 if t == "Pitcher" else 1)

    for col, base in [("woba_delta", "woba"), ("xwoba_delta", "xwoba")]:
        init_col    = f"week1_{base}"
        current_col = f"{latest}_{base}"
        if init_col in df.columns and current_col in df.columns:
            # For pitchers: woba=ERA (lower is better → flip sign)
            df[col] = (df[current_col] - df[init_col]) * sign
        else:
            df[col] = float("nan")

    # luck_delta: week1→current; positive = luck signal strengthened (more positive)
    init_luck     = "week1_luck"
    curr_luck_col = f"{latest}_luck"
    if init_luck in df.columns and curr_luck_col in df.columns:
        df["luck_delta"] = (pd.to_numeric(df[curr_luck_col], errors="coerce")
                            - pd.to_numeric(df[init_luck],    errors="coerce"))
    else:
        df["luck_delta"] = float("nan")

    # Rolling 4-week window: latest vs 4 weeks prior
    # wc[-5] = "week(latest-4)_luck" when we have ≥5 weeks of data
    if len(wc) >= 5:
        win_start_prefix = wc[-5].split("_")[0]   # e.g. "week4"
        w4_woba  = f"{win_start_prefix}_woba"
        w4_luck  = f"{win_start_prefix}_luck"
        lat_woba = f"{latest}_woba"
        lat_luck = f"{latest}_luck"

        if w4_woba in df.columns and lat_woba in df.columns:
            df["rolling_4wk_woba_delta"] = (
                (pd.to_numeric(df[lat_woba], errors="coerce")
                 - pd.to_numeric(df[w4_woba], errors="coerce")) * sign
            )
        else:
            df["rolling_4wk_woba_delta"] = float("nan")

        if w4_luck in df.columns and lat_luck in df.columns:
            df["rolling_4wk_luck_delta"] = (
                pd.to_numeric(df[lat_luck], errors="coerce")
                - pd.to_numeric(df[w4_luck], errors="coerce")
            )
        else:
            df["rolling_4wk_luck_delta"] = float("nan")
    else:
        df["rolling_4wk_woba_delta"] = float("nan")
        df["rolling_4wk_luck_delta"] = float("nan")

    df["mechanism"]          = df.apply(_classify_mechanism, axis=1)
    df["prediction_correct"] = df.apply(_classify_correct, axis=1)
    df["window_signal"]      = df.apply(_classify_window_signal, axis=1)

    # ── Rolling window age / urgency columns ────────────────────────────────
    # signal_age_weeks: how many weekly updates have elapsed since call_date.
    # All calls were made at Week 1 (April 22, 2026), so age = current_week - 1.
    current_week = len(wc)   # number of weekN_luck columns = weeks of data
    df["signal_age_weeks"] = max(0, current_week - 1)

    # window_4wk_status: "active" (≤4 wks), "extended" (5-8 wks), "stale" (>8 wks)
    def _status(age: int) -> str:
        if age <= WINDOW_ACTIVE_MAX:
            return "active"
        if age <= WINDOW_EXTENDED_MAX:
            return "extended"
        return "stale"
    df["window_4wk_status"] = df["signal_age_weeks"].map(_status)

    # urgency_flag: deepening signal that has been active 3+ weeks without confirming
    def _urgency(row) -> bool:
        return (row.get("window_signal") == "deepening"
                and int(row.get("signal_age_weeks", 0)) >= 3)
    df["urgency_flag"] = df.apply(_urgency, axis=1)

    # resolution_eta: estimated weeks until luck score crosses the normalization threshold.
    # Formula: (|luck_score| - normalization_threshold) / AVG_LUCK_DECAY_PER_WEEK
    # Clipped to [0, 20]. NaN when no current luck data.
    curr_luck_col = f"{latest}_luck" if latest else None
    if curr_luck_col and curr_luck_col in df.columns:
        def _eta(row) -> object:
            luck = row.get(curr_luck_col)
            try:
                luck = float(luck)
            except (TypeError, ValueError):
                return float("nan")
            import math
            if math.isnan(luck):
                return float("nan")
            call = row.get("call", "")
            is_buy = any(b in str(call).lower() for b in ("buy",))
            threshold = LUCK_NORMALIZE_BUY if is_buy else abs(LUCK_NORMALIZE_SELL)
            gap = abs(luck) - threshold
            if gap <= 0:
                return 0.0
            return round(min(20.0, gap / AVG_LUCK_DECAY_PER_WEEK), 1)
        df["resolution_eta"] = df.apply(_eta, axis=1)
    else:
        df["resolution_eta"] = float("nan")

    df["last_updated"]       = str(date.today())
    return df


def _classify_mechanism(row) -> str:
    """
    Classify the mechanism driving wOBA/xwOBA movement.

    Sign convention (from _compute_deltas):
      woba_delta  > 0  = results improving   (wOBA up for hitters; ERA down for pitchers)
      woba_delta  < 0  = results declining   (wOBA down for hitters; ERA up for pitchers)
      xwoba_delta > 0  = underlying quality improving  (xwOBA up for hitters; FIP down for pitchers)
      xwoba_delta < 0  = underlying quality declining  (xwOBA down for hitters; FIP up for pitchers)

      For BUY calls:  prediction-correct = woba_delta > 0 (results improving as expected)
      For SELL calls: prediction-correct = woba_delta < 0 (results declining / ERA rising as expected)

    BUY mechanisms:
      results_improving     — wOBA up, xwOBA stable      → Normalizing (luck clearing)
      contact_deteriorating — xwOBA declining             → Re-evaluate (underlying worsening)
      confirmed             — both improving              → Confirmed
      refuted               — both declining              → Refuted
      insufficient_movement — no threshold met            → Watch

    SELL mechanisms:
      results_declining     — wOBA declining, xwOBA stable → Normalizing (luck clearing)
      contact_improving     — xwOBA improving              → Re-evaluate (player genuinely good)
      genuine_decline       — both declining               → Confirmed
      refuted               — both improving               → Refuted
      insufficient_movement — no threshold met             → Watch
    """
    import math

    wd   = row.get("woba_delta",  float("nan"))
    xd   = row.get("xwoba_delta", float("nan"))
    call = row.get("call", "")

    wd_nan = math.isnan(float(wd)) if wd not in ("", None) else True
    xd_nan = math.isnan(float(xd)) if xd not in ("", None) else True
    if wd_nan:
        wd = float("nan")
    if xd_nan:
        xd = float("nan")

    if wd_nan and xd_nan:
        return "insufficient_movement"

    wd = float(wd)
    xd = float(xd) if not xd_nan else float("nan")

    is_buy  = call in BUY_VERDICTS
    is_sell = call in SELL_VERDICTS

    woba_sig_pos  = (not math.isnan(wd)) and wd >=  WOBA_THRESH
    woba_sig_neg  = (not math.isnan(wd)) and wd <= -WOBA_THRESH
    xwoba_sig_pos = (not math.isnan(xd)) and xd >=  XWOBA_THRESH
    xwoba_sig_neg = (not math.isnan(xd)) and xd <= -XWOBA_THRESH
    xwoba_stable  = (not math.isnan(xd)) and abs(xd) < XWOBA_THRESH

    # Get current luck score for luck-normalization gate on "refuted".
    # A call is only marked refuted if the luck signal has substantially normalized.
    # Luck still strongly positive/negative = signal still active → "still_waiting".
    luck_cols = sorted(
        [c for c in row.index if c.startswith("week") and c.endswith("_luck")],
        key=lambda c: int(c.split("_")[0][4:])
    )
    try:
        curr_luck = float(row[luck_cols[-1]]) if luck_cols else float("nan")
    except (ValueError, TypeError):
        curr_luck = float("nan")

    if is_buy:
        if woba_sig_pos and xwoba_sig_pos:
            return "confirmed"               # both improving — buy confirmed
        if woba_sig_neg and xwoba_sig_neg:
            # Only mark refuted when the luck signal itself has normalized.
            # If luck still >> 0, the underlying mispricing signal is intact.
            if not math.isnan(curr_luck) and curr_luck >= LUCK_NORMALIZE_BUY:
                return "still_waiting"       # luck active, wOBA not moving yet
            return "refuted"                 # luck normalized + both declining
        if xwoba_sig_neg:
            return "contact_deteriorating"   # xwOBA down — re-evaluate
        if woba_sig_pos and (xwoba_stable or math.isnan(xd)):
            return "results_improving"       # wOBA up, xwOBA stable — normalizing
    if is_sell:
        if woba_sig_neg and xwoba_sig_neg:
            return "genuine_decline"         # both declining — confirmed genuine decline
        if woba_sig_pos and xwoba_sig_pos:
            # Check luck delta: if sell signal deepened, label as results_declining not refuted
            ld = row.get("luck_delta", float("nan"))
            try:
                ld = float(ld)
            except (TypeError, ValueError):
                ld = float("nan")
            if not math.isnan(ld) and ld < -0.02:
                return "results_declining"   # luck deepened — sell signal stronger
            # Only mark refuted if the sell luck signal has normalized
            if not math.isnan(curr_luck) and curr_luck <= LUCK_NORMALIZE_SELL:
                return "still_waiting"       # sell signal still active, player just hitting
            return "refuted"                 # luck normalized + both improving
        if xwoba_sig_pos:
            return "contact_improving"       # xwOBA improving — re-evaluate
        if woba_sig_neg and (xwoba_stable or math.isnan(xd)):
            return "results_declining"       # wOBA declining, xwOBA stable — normalizing
    return "insufficient_movement"


def _classify_correct(row) -> object:
    """Returns 1 (correct), 0 (refuted), or None (unresolved).
    Requires both wOBA and xwOBA to confirm (mechanism-based, not threshold-only).
    still_waiting is UNRESOLVED — luck active, prediction not yet confirmed OR denied.
    """
    mech = row.get("mechanism", "insufficient_movement")
    if mech in ("confirmed", "genuine_decline"):
        return 1
    if mech == "refuted":
        return 0
    return None   # still_waiting, insufficient_movement, contact_*, results_* = unresolved


def _classify_window_signal(row) -> str:
    """Rolling 4-week window signal direction.

    window_signal:
      confirming  — results moving the correct direction in the last 4 weeks
      deepening   — luck score getting stronger (signal intensifying) despite flat results
      refuted_4wk — results moved the WRONG direction in the last 4 weeks
      still_waiting — insufficient movement in either direction
      insufficient_data — not enough weeks of data yet
    """
    import math
    rwd  = row.get("rolling_4wk_woba_delta",  float("nan"))
    rld  = row.get("rolling_4wk_luck_delta",  float("nan"))
    call = row.get("call", "")

    try:
        rwd = float(rwd)
    except (TypeError, ValueError):
        rwd = float("nan")
    try:
        rld = float(rld)
    except (TypeError, ValueError):
        rld = float("nan")

    if math.isnan(rwd) and math.isnan(rld):
        return "insufficient_data"

    is_buy  = call in BUY_VERDICTS
    is_sell = call in SELL_VERDICTS

    if is_buy:
        if not math.isnan(rld) and rld >= LUCK_DEEPEN_THRESH:
            return "deepening"          # luck getting stronger; results may lag
        if not math.isnan(rwd) and rwd >= WOBA_THRESH:
            return "confirming"         # results improving in last 4 weeks
        if not math.isnan(rwd) and rwd <= -WOBA_THRESH:
            return "refuted_4wk"        # results wrong direction in window
        return "still_waiting"

    if is_sell:
        if not math.isnan(rld) and rld <= -LUCK_DEEPEN_THRESH:
            return "deepening"          # sell signal getting stronger
        if not math.isnan(rwd) and rwd <= -WOBA_THRESH:
            return "confirming"         # results declining as predicted
        if not math.isnan(rwd) and rwd >= WOBA_THRESH:
            return "refuted_4wk"        # player improving in window
        return "still_waiting"

    return "still_waiting"


# ── signal decay classifier ───────────────────────────────────────────────────

def _load_luck_classifier_data() -> dict:
    """Load the subset of luck_scores.csv columns needed for signal type classification.
    Returns {mlbam_id: {field: value}} lookup.  Empty dict if file missing.
    """
    needed = ["batter", "xwOBA", "xwoba_3yr", "hh_flag", "speed_flag",
              "chase_flag", "la_trending_down"]
    try:
        df = pd.read_csv(LUCK_H, usecols=[c for c in needed if c in
                                           pd.read_csv(LUCK_H, nrows=0).columns])
        result = {}
        for _, r in df.iterrows():
            try:
                bid = int(r["batter"])
            except (ValueError, TypeError):
                continue
            result[bid] = r.to_dict()
        return result
    except Exception:
        return {}


def _classify_signal_type(pid: int, luck_lookup: dict) -> tuple[str, float]:
    """Classify a buy signal as PURE_LUCK / MECHANICAL / INJURY_RISK.

    Returns (signal_type, confidence_weight).
    Only applied to Buy Low and Slight Buy calls; others get ('N/A', 1.0).

    Rules (evaluated in priority order):
      INJURY_RISK (0.30): speed_flag=True AND hh_flag=True
        → both physical indicators declining simultaneously; possible injury-driven
      MECHANICAL  (0.60): xwOBA < xwoba_3yr - 0.020 (contact quality fading)
                          OR chase_flag=True (discipline deteriorating)
        → some mechanical degradation explains part of the unlucky result
      PURE_LUCK   (1.00): everything else
        → BABIP-driven noise; xwOBA stable; clean regression candidate
    """
    lr = luck_lookup.get(pid)
    if lr is None:
        return "PURE_LUCK", 1.00

    speed_flag     = bool(lr.get("speed_flag", False))
    hh_flag        = bool(lr.get("hh_flag", False))
    chase_flag     = bool(lr.get("chase_flag", False))
    la_down        = bool(lr.get("la_trending_down", False))

    import math
    xwoba     = lr.get("xwOBA")
    xwoba_3yr = lr.get("xwoba_3yr")
    try:
        xwoba     = float(xwoba)
        xwoba_3yr = float(xwoba_3yr)
        xwoba_below_career = (not math.isnan(xwoba) and not math.isnan(xwoba_3yr)
                              and xwoba < xwoba_3yr - 0.020)
    except (TypeError, ValueError):
        xwoba_below_career = False

    if speed_flag and hh_flag:
        return "INJURY_RISK", 0.30

    if xwoba_below_career or chase_flag:
        return "MECHANICAL", 0.60

    return "PURE_LUCK", 1.00


def _apply_signal_classifier(df: pd.DataFrame) -> pd.DataFrame:
    """Add signal_type and confidence_weight columns to calls_tracker.
    Only buy signals receive a classification; sell signals get N/A.
    """
    luck_lookup = _load_luck_classifier_data()
    signal_types  = []
    conf_weights  = []
    for _, row in df.iterrows():
        call = str(row.get("call", ""))
        if call in BUY_VERDICTS:
            try:
                pid = int(row["player_id"])
            except (ValueError, TypeError):
                pid = -1
            st, cw = _classify_signal_type(pid, luck_lookup)
        else:
            st, cw = "N/A", 1.00
        signal_types.append(st)
        conf_weights.append(cw)
    df["signal_type"]        = signal_types
    df["confidence_weight"]  = conf_weights
    return df


# ── ownership acceleration tracking ──────────────────────────────────────────

def _load_current_ownership() -> dict:
    """Return {mlbam_id (int): owned_pct (float)} from both luck CSVs."""
    out: dict[int, float] = {}
    for path, id_col in [(LUCK_H, "batter"), (LUCK_P, "pitcher")]:
        try:
            df = pd.read_csv(path, usecols=[id_col, "owned_pct"])
            for _, r in df.iterrows():
                try:
                    bid = int(r[id_col])
                    pct = float(r["owned_pct"])
                    if not pd.isna(pct):
                        out[bid] = round(pct, 2)
                except (ValueError, TypeError):
                    continue
        except Exception:
            continue
    return out


def _snapshot_ownership(week_num: int) -> None:
    """Append current ownership snapshot to data/ownership_history.json.

    Structure: {str(mlbam_id): [{week, ownership, date}, ...]}
    Retains full season history (no pruning).
    """
    today_str  = date.today().isoformat()
    current    = _load_current_ownership()
    if not current:
        print("  [ownership] No ownership data found — skipping snapshot.")
        return

    if OWNERSHIP_HISTORY.exists():
        with open(OWNERSHIP_HISTORY, encoding="utf-8") as f:
            history: dict = json.load(f)
    else:
        history = {}

    added = 0
    for mlbam_id, pct in current.items():
        key     = str(mlbam_id)
        records = history.get(key, [])
        # Avoid duplicate entry for same week
        if records and records[-1]["week"] == week_num:
            continue
        records.append({"week": week_num, "ownership": pct, "date": today_str})
        history[key] = records
        added += 1

    with open(OWNERSHIP_HISTORY, "w", encoding="utf-8") as f:
        json.dump(history, f, separators=(",", ":"))
    print(f"  [ownership] Snapshotted {added} players at week {week_num} -> {OWNERSHIP_HISTORY.name}")


def _compute_ownership_deltas(df: pd.DataFrame, week_num: int) -> pd.DataFrame:
    """Add delta_own_1w, delta_own_4w, own_velocity, own_acceleration to tracker.

    delta_own_1w:     current ownership - ownership 1 week ago (None if < 2 weeks)
    delta_own_4w:     current ownership - ownership 4 weeks ago (None if < 4 weeks)
    own_velocity:     same as delta_own_1w (alias for clarity in reports)
    own_acceleration: delta_own_1w (this week) - delta_own_1w_prior_week
                      positive = rise accelerating, negative = decelerating
    """
    if not OWNERSHIP_HISTORY.exists():
        for col in ("delta_own_1w", "delta_own_4w", "own_velocity", "own_acceleration"):
            if col not in df.columns:
                df[col] = float("nan")
        return df

    with open(OWNERSHIP_HISTORY, encoding="utf-8") as f:
        history: dict = json.load(f)

    d1w, d4w, vel, acc = [], [], [], []
    for _, row in df.iterrows():
        key     = str(int(row["player_id"]))
        records = history.get(key, [])
        rec_map = {r["week"]: r["ownership"] for r in records}

        curr      = rec_map.get(week_num)
        prev_1w   = rec_map.get(week_num - 1)
        prev_2w   = rec_map.get(week_num - 2)
        prev_4w   = rec_map.get(week_num - 4)

        delta_1 = round(curr - prev_1w, 2) if (curr is not None and prev_1w is not None) else float("nan")
        delta_4 = round(curr - prev_4w, 2) if (curr is not None and prev_4w is not None) else float("nan")

        # Acceleration: change in weekly velocity vs prior week's velocity
        delta_prev = round(prev_1w - prev_2w, 2) if (prev_1w is not None and prev_2w is not None) else float("nan")
        accel = round(delta_1 - delta_prev, 2) if (not pd.isna(delta_1) and not pd.isna(delta_prev)) else float("nan")

        d1w.append(delta_1)
        d4w.append(delta_4)
        vel.append(delta_1)   # velocity = 1-week delta
        acc.append(accel)

    df["delta_own_1w"]     = d1w
    df["delta_own_4w"]     = d4w
    df["own_velocity"]     = vel
    df["own_acceleration"] = acc
    return df


# ── init ─────────────────────────────────────────────────────────────────────

def cmd_init():
    """Bootstrap calls_tracker.csv from current luck CSVs (Week 1 baseline)."""
    rows = []

    hitters = _load_current_hitters()
    for _, r in hitters.iterrows():
        if r["verdict"] not in (BUY_VERDICTS | SELL_VERDICTS):
            continue
        rows.append({
            "player_id":          int(r["batter"]),
            "name":               _clean_name(r["name"]),
            "type":               "Hitter",
            "call":               r["verdict"],
            "call_date":          CALL_DATE,
            "week1_luck":         round(float(r["luck_score"]), 4),
            "week1_woba":         round(float(r["wOBA"]),       3),
            "week1_xwoba":        round(float(r["xwOBA"]),      3),
            "woba_delta":         "",
            "xwoba_delta":        "",
            "mechanism":          "insufficient_movement",
            "prediction_correct": "",
            "last_updated":       CALL_DATE,
            "notes":              "",
        })

    pitchers = _load_current_pitchers()
    for _, r in pitchers.iterrows():
        if r["verdict"] not in (BUY_VERDICTS | SELL_VERDICTS):
            continue
        rows.append({
            "player_id":          int(r["pitcher"]),
            "name":               _clean_name(r["name"]),
            "type":               "Pitcher",
            "call":               r["verdict"],
            "call_date":          CALL_DATE,
            "week1_luck":         round(float(r["luck_score"]), 4),
            "week1_woba":         round(float(r["ERA"]),        2),   # ERA for pitchers
            "week1_xwoba":        round(float(r["FIP"]),        2),   # FIP for pitchers
            "woba_delta":         "",
            "xwoba_delta":        "",
            "mechanism":          "insufficient_movement",
            "prediction_correct": "",
            "last_updated":       CALL_DATE,
            "notes":              "",
        })

    df = pd.DataFrame(rows)
    df.to_csv(TRACKER, index=False)
    print(f"Initialized {len(df)} calls → {TRACKER}")
    print(f"  Hitters: {len(df[df['type']=='Hitter'])}  "
          f"Pitchers: {len(df[df['type']=='Pitcher'])}")
    _print_summary(df)


# ── update ────────────────────────────────────────────────────────────────────

DUPLICATE_MATCH_THRESHOLD = 0.90   # fraction of players that must differ to allow write
DUPLICATE_LUCK_TOL        = 0.0002  # tolerance for luck_score match (4 decimal places)


def _check_duplicate(df: pd.DataFrame,
                     hitters: pd.DataFrame, pitchers: pd.DataFrame) -> bool:
    """
    Return True if current luck scores are identical to the last written week
    for >= DUPLICATE_MATCH_THRESHOLD of players (i.e. pipeline hasn't refreshed).
    """
    wc = _week_cols(df)
    if not wc:
        return False
    last_col = wc[-1]  # e.g. "week7_luck"

    matched = 0
    comparable = 0
    for _, row in df.iterrows():
        pid   = int(row["player_id"])
        ptype = row["type"]
        last  = pd.to_numeric(row.get(last_col), errors="coerce")
        if pd.isna(last):
            continue
        if ptype == "Hitter" and pid in hitters.index:
            curr = round(float(hitters.loc[pid, "luck_score"]), 4)
        elif ptype == "Pitcher" and pid in pitchers.index:
            curr = round(float(pitchers.loc[pid, "luck_score"]), 4)
        else:
            continue
        comparable += 1
        if abs(curr - last) <= DUPLICATE_LUCK_TOL:
            matched += 1

    if comparable == 0:
        return False
    rate = matched / comparable
    return rate >= DUPLICATE_MATCH_THRESHOLD


def cmd_update():
    """Pull current luck CSVs → add weekN columns → recompute deltas & mechanism."""
    if not TRACKER.exists():
        print("No tracker found. Run --init first.")
        return

    df = pd.read_csv(TRACKER)

    hitters  = _load_current_hitters().set_index("batter")
    pitchers = _load_current_pitchers().set_index("pitcher")

    # Guard: skip if pipeline data hasn't refreshed since last --update
    if _check_duplicate(df, hitters, pitchers):
        wc = _week_cols(df)
        last = wc[-1] if wc else "week0"
        print(f"[DUPLICATE DETECTED] luck scores unchanged from {last}.")
        print(f"  Run pipeline first (python run_pipeline.py --write) then re-run --update.")
        print(f"  Tracker NOT updated. Still at {last}.")
        return

    next_week = _current_week_num(df) + 1
    prefix    = f"week{next_week}"
    print(f"Adding {prefix} columns...")

    hitters  = _load_current_hitters().set_index("batter")
    pitchers = _load_current_pitchers().set_index("pitcher")

    new_luck  = []
    new_woba  = []
    new_xwoba = []

    for _, row in df.iterrows():
        pid  = int(row["player_id"])
        ptype = row["type"]
        if ptype == "Hitter" and pid in hitters.index:
            h = hitters.loc[pid]
            new_luck.append(round(float(h["luck_score"]), 4))
            new_woba.append(round(float(h["wOBA"]),       3))
            new_xwoba.append(round(float(h["xwOBA"]),     3))
        elif ptype == "Pitcher" and pid in pitchers.index:
            p = pitchers.loc[pid]
            new_luck.append(round(float(p["luck_score"]), 4))
            new_woba.append(round(float(p["ERA"]),        2))
            new_xwoba.append(round(float(p["FIP"]),       2))
        else:
            new_luck.append(float("nan"))
            new_woba.append(float("nan"))
            new_xwoba.append(float("nan"))

    df[f"{prefix}_luck"]  = new_luck
    df[f"{prefix}_woba"]  = new_woba
    df[f"{prefix}_xwoba"] = new_xwoba

    df = _compute_deltas(df)
    df = _apply_signal_classifier(df)
    _snapshot_ownership(next_week)
    df = _compute_ownership_deltas(df, next_week)
    df.to_csv(TRACKER, index=False)
    print(f"Updated → {TRACKER}  (now at {prefix})")
    _print_summary(df)


# ── report ────────────────────────────────────────────────────────────────────

def cmd_report(top_n: int = 99):
    """Generate markdown article table ready to paste into Substack."""
    if not TRACKER.exists():
        print("No tracker found. Run --init first.")
        return

    df = pd.read_csv(TRACKER)
    wc = _week_cols(df)
    weeks_elapsed = len(wc) - 1   # week1 = baseline, weeks beyond that = elapsed

    # Accuracy calculation (spec: confirmed + refuted only, exclude watch/re-evaluate)
    confirmed = df[df["prediction_correct"] == 1]
    refuted   = df[df["prediction_correct"] == 0]
    n_conf    = len(confirmed)
    n_ref     = len(refuted)
    n_denom   = n_conf + n_ref
    accuracy  = f"{n_conf / n_denom * 100:.1f}%" if n_denom > 0 else "No resolved calls yet"

    lines = [
        f"## Signal Tracker — Week {len(wc)} Update",
        f"*{date.today().strftime('%B %d, %Y')} | {weeks_elapsed} week(s) of movement data*",
        "",
    ]

    # Track 1 accuracy: collection-only until Week 10 (mid-June resolution window)
    if len(wc) >= TRACK1_RESOLUTION_WEEK and n_denom > 0:
        lines += [
            f"**Running accuracy: {accuracy}** ({n_conf}/{n_denom} resolved calls)",
            "",
        ]
    else:
        weeks_to_resolution = max(0, TRACK1_RESOLUTION_WEEK - len(wc))
        still_active = (df["mechanism"] == "still_waiting").sum()
        deepening    = (df.get("window_signal", pd.Series(dtype=str)) == "deepening").sum()
        lines += [
            f"*Track 1 signals — resolution window opens Week {TRACK1_RESOLUTION_WEEK} "
            f"(~{weeks_to_resolution} week{'s' if weeks_to_resolution != 1 else ''} away)*",
            f"*Confirmed: {n_conf} | Still active / signal intact: {still_active} | "
            f"Signal deepening: {deepening} | Honest misses: {n_ref}*",
            "",
        ]

    for call_group, header in [
        (BUY_VERDICTS,  "### Buy Signals"),
        (SELL_VERDICTS, "### Sell Signals"),
    ]:
        group = df[df["call"].isin(call_group)].copy()
        # Sort: confirmed → normalizing → re-evaluate → still_waiting → refuted → watch
        mech_order = {
            "confirmed":             0,
            "genuine_decline":       0,
            "results_improving":     1,
            "results_declining":     1,
            "contact_deteriorating": 2,
            "contact_improving":     2,
            "still_waiting":         3,
            "refuted":               4,
            "insufficient_movement": 5,
        }
        group["_sort"] = group["mechanism"].map(lambda m: mech_order.get(m, 4))
        group = group.sort_values(["_sort", "call"])

        if group.empty:
            continue

        lines.append(header)
        lines.append("")
        lines.append("| Player | Call | Trend | Story | Status |")
        lines.append("|--------|------|-------|-------|--------|")

        shown = 0
        for _, row in group.iterrows():
            if shown >= top_n:
                break
            line = _format_row(row, weeks_elapsed)
            lines.append(line)
            shown += 1

        lines.append("")

    print("\n".join(lines))


def _format_row(row, weeks_elapsed: int) -> str:
    import math

    name  = _clean_name(row["name"])
    call  = row["call"]
    mech  = row.get("mechanism", "insufficient_movement")
    emoji = STATUS_EMOJI.get(mech, "⏳")
    ptype = row["type"]

    wd = row.get("woba_delta",  None)
    xd = row.get("xwoba_delta", None)

    wd_val = float(wd) if wd not in ("", None) and not (isinstance(wd, float) and math.isnan(wd)) else None
    xd_val = float(xd) if xd not in ("", None) and not (isinstance(xd, float) and math.isnan(xd)) else None

    # Luck trend: show initial → current luck score
    wc = sorted([c for c in row.index if c.startswith("week") and c.endswith("_luck")],
                key=lambda c: int(c.split("_")[0][4:]))
    if len(wc) >= 2:
        luck_init    = float(row[wc[0]])
        luck_current = float(row[wc[-1]])
        delta_luck   = luck_current - luck_init
        direction    = "↑" if delta_luck > 0.020 else ("↓" if delta_luck < -0.020 else "→")
        trend = f"Luck {luck_init:+.3f}→{luck_current:+.3f} ({direction})"
    else:
        trend = "Luck — (baseline only)"

    # Metric labels and delta formatting
    # Pitchers: ERA/FIP on ~2-6 scale — show as decimals (e.g. "ERA down 0.30")
    # Hitters:  wOBA/xwOBA on ~0.300 scale — show as pts (e.g. "wOBA up 30pts")
    if ptype == "Pitcher":
        m1_label, m2_label = "ERA", "FIP"
        # woba_delta > 0 means ERA went DOWN (sign flipped in _compute_deltas)
        m1_dir = "down" if wd_val is not None and wd_val > 0 else "up"
        m2_dir = "down" if xd_val is not None and xd_val > 0 else "up"
        m1_pts = f"{abs(wd_val):.2f}" if wd_val is not None else "?"
        m2_pts = f"{abs(xd_val):.2f}" if xd_val is not None else "?"
    else:
        m1_label, m2_label = "wOBA", "xwOBA"
        m1_dir = "up"   if wd_val is not None and wd_val > 0 else "down"
        m2_dir = "up"   if xd_val is not None and xd_val > 0 else "down"
        m1_pts = str(abs(round(wd_val * 1000))) if wd_val is not None else "?"
        m2_pts = str(abs(round(xd_val * 1000))) if xd_val is not None else "?"
        m1_unit, m2_unit = "pts", "pts"

    def _m1_str():
        unit = "" if ptype == "Pitcher" else "pts"
        return f"{m1_label} {m1_dir} {m1_pts}{unit}"

    def _m2_str():
        unit = "" if ptype == "Pitcher" else "pts"
        return f"{m2_label} {m2_dir} {m2_pts}{unit}"

    is_buy  = call in BUY_VERDICTS
    is_sell = call in SELL_VERDICTS

    # Story sentence per spec
    # Rolling window signal for context
    win_sig = row.get("window_signal", "")

    if mech == "insufficient_movement" or (wd_val is None and xd_val is None):
        story = f"Too early — {weeks_elapsed} week{'s' if weeks_elapsed != 1 else ''} of data"
    elif mech == "still_waiting":
        # Luck signal still strongly active; results haven't moved yet
        luck_cols_r = sorted([c for c in row.index if c.startswith("week") and c.endswith("_luck")],
                             key=lambda c: int(c.split("_")[0][4:]))
        curr_luck_r = float(row[luck_cols_r[-1]]) if luck_cols_r else 0.0
        win_note = " — signal deepening" if win_sig == "deepening" else ""
        story = f"Signal intact (luck {curr_luck_r:+.3f}){win_note} — results pending"
    elif mech == "results_improving":
        story = f"{_m1_str()} — results improving as predicted"
    elif mech == "results_declining":
        story = f"{_m1_str()} — results regressing as predicted"
    elif mech == "contact_deteriorating":
        story = f"{_m2_str()} — contact quality declining, re-evaluate"
    elif mech == "contact_improving":
        story = f"{_m2_str()} — contact quality improving, not regression"
    elif mech == "confirmed":
        story = f"{_m1_str()}, {_m2_str()} — buy confirmed"
    elif mech == "genuine_decline":
        story = f"{_m1_str()}, {_m2_str()} — genuine decline"
    elif mech == "refuted" and is_buy:
        story = f"{m1_label} and {m2_label} both declining — buy call may be wrong"
    elif mech == "refuted" and is_sell:
        story = "Player improving across the board — sell call wrong"
    else:
        story = f"Too early — {weeks_elapsed} week{'s' if weeks_elapsed != 1 else ''} of data"

    return f"| {name} | {call} | {trend} | {story} | {emoji} |"


# ── summary ───────────────────────────────────────────────────────────────────

def _print_summary(df: pd.DataFrame):
    mechs = df["mechanism"].value_counts()
    print("\nMechanism breakdown:")
    for m, c in mechs.items():
        print(f"  {m:30s} {c}")

    if "window_signal" in df.columns:
        print("\nRolling 4-week window:")
        for ws, c in df["window_signal"].value_counts().items():
            print(f"  {ws:25s} {c}")

    n_corr = (df["prediction_correct"] == 1).sum()
    n_ref  = (df["prediction_correct"] == 0).sum()
    wc = _week_cols(df)
    if n_corr + n_ref > 0 and len(wc) >= TRACK1_RESOLUTION_WEEK:
        print(f"\nAccuracy: {n_corr/(n_corr+n_ref)*100:.1f}%  "
              f"({n_corr} confirmed / {n_ref} refuted)")
    elif n_corr + n_ref > 0:
        print(f"\nTrack 1 collection phase (Week {len(wc)}/{TRACK1_RESOLUTION_WEEK}): "
              f"{n_corr} confirmed | {n_ref} honest misses | "
              f"{(df['mechanism']=='still_waiting').sum()} signal active")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]
    if "--init" in args:
        cmd_init()
    elif "--update" in args:
        cmd_update()
    elif "--snapshot-ownership" in args:
        # Snapshot current ownership without requiring a new pipeline run.
        # Uses the current week number from the tracker (does not advance it).
        if not TRACKER.exists():
            print("No tracker found. Run --init first.")
            return
        df = pd.read_csv(TRACKER)
        week_num = _current_week_num(df)
        if week_num == 0:
            week_num = 1
        _snapshot_ownership(week_num)
        df = _compute_ownership_deltas(df, week_num)
        df.to_csv(TRACKER, index=False)
        print(f"Ownership snapshot complete at week {week_num}.")
        # Show current ownership for players in tracker
        current = _load_current_ownership()
        active  = df[df["mechanism"].isin(["still_waiting", "results_improving",
                                            "results_declining", "confirming",
                                            "insufficient_movement"])]
        print(f"\nTop 10 active signals - current ownership%:")
        shown = 0
        for _, row in active.sort_values("luck_delta", ascending=False, key=abs).iterrows():
            pid = int(row["player_id"])
            own = current.get(pid)
            if own is not None:
                d1 = row.get("delta_own_1w")
                d4 = row.get("delta_own_4w")
                d1_str = f"d1w={d1:+.1f}" if not pd.isna(d1) else "d1w=--"
                d4_str = f"d4w={d4:+.1f}" if not pd.isna(d4) else "d4w=--"
                print(f"  {row['name']:<22} {own:5.1f}%  {d1_str}  {d4_str}  [{row.get('call','')}]")
                shown += 1
                if shown >= 10:
                    break
    elif "--report" in args:
        top_n = 99
        if "--top" in args:
            idx = args.index("--top")
            if idx + 1 < len(args):
                top_n = int(args[idx + 1])
        cmd_report(top_n=top_n)
    else:
        if not TRACKER.exists():
            print("No calls_tracker.csv found. Run: python weekly_update.py --init")
            return
        df = pd.read_csv(TRACKER)
        print(f"Calls tracker: {len(df)} players, week {_current_week_num(df)}")
        _print_summary(df)


if __name__ == "__main__":
    main()
