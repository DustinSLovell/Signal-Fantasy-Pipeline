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

import sys
from datetime import date
from pathlib import Path

import pandas as pd

BASE_DIR    = Path(__file__).parent
TRACKER     = BASE_DIR / "data" / "calls_tracker.csv"
LUCK_H      = BASE_DIR / "luck_scores.csv"
LUCK_P      = BASE_DIR / "pitcher_luck_scores.csv"
CALL_DATE   = "2026-04-22"   # Week 1 article date

# Significance thresholds (from spec)
WOBA_THRESH  = 0.020   # wOBA movement to classify
XWOBA_THRESH = 0.015   # xwOBA movement to classify

# Mechanism → human-readable status label and emoji
# Mechanisms:
#   BUY calls:  results_improving | contact_deteriorating | confirmed | refuted | insufficient_movement
#   SELL calls: results_declining | contact_improving     | genuine_decline | refuted | insufficient_movement
STATUS_LABEL = {
    "results_improving":     "Normalizing",
    "results_declining":     "Normalizing",
    "contact_deteriorating": "Re-evaluate",
    "contact_improving":     "Re-evaluate",
    "confirmed":             "Confirmed",
    "genuine_decline":       "Confirmed",
    "refuted":               "Refuted",
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
    "insufficient_movement": "⏳",
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
    """Recompute woba_delta, xwoba_delta, mechanism, prediction_correct."""
    wc = _week_cols(df)
    if not wc:
        return df

    latest = wc[-1].split("_")[0]  # e.g. "week3"

    for col, base in [("woba_delta", "woba"), ("xwoba_delta", "xwoba")]:
        init_col    = f"week1_{base}"
        current_col = f"{latest}_{base}"
        if init_col in df.columns and current_col in df.columns:
            # For pitchers: woba=ERA (lower is better → flip sign)
            sign = df["type"].map(lambda t: -1 if t == "Pitcher" else 1)
            df[col] = (df[current_col] - df[init_col]) * sign
        else:
            df[col] = float("nan")

    df["mechanism"]         = df.apply(_classify_mechanism, axis=1)
    df["prediction_correct"] = df.apply(_classify_correct, axis=1)
    df["last_updated"]       = str(date.today())
    return df


def _classify_mechanism(row) -> str:
    """
    Classify the mechanism driving wOBA/xwOBA movement.

    Sign convention (from _compute_deltas):
      woba_delta  > 0  = prediction moving toward correct  (wOBA up for buy; ERA down for sell pitcher)
      xwoba_delta > 0  = underlying quality moving toward correct (xwOBA up for buy; FIP down for sell pitcher)
      For SELL calls the prediction is results get WORSE, so:
        woba_delta < 0 = bad results getting worse  = prediction moving correct
        xwoba_delta > 0 = underlying quality improving = re-evaluate the sell

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

    if is_buy:
        if woba_sig_pos and xwoba_sig_pos:
            return "confirmed"               # both improving — buy confirmed
        if woba_sig_neg and xwoba_sig_neg:
            return "refuted"                 # both declining — buy call wrong
        if xwoba_sig_neg:
            return "contact_deteriorating"   # xwOBA down — re-evaluate
        if woba_sig_pos and (xwoba_stable or math.isnan(xd)):
            return "results_improving"       # wOBA up, xwOBA stable — normalizing
    if is_sell:
        if woba_sig_neg and xwoba_sig_neg:
            return "genuine_decline"         # both declining — confirmed genuine decline
        if woba_sig_pos and xwoba_sig_pos:
            return "refuted"                 # both improving — sell call wrong
        if xwoba_sig_pos:
            return "contact_improving"       # xwOBA improving — re-evaluate
        if woba_sig_neg and (xwoba_stable or math.isnan(xd)):
            return "results_declining"       # wOBA declining, xwOBA stable — normalizing
    return "insufficient_movement"


def _classify_correct(row) -> object:
    """Returns 1 (correct), 0 (refuted), or None (unresolved).
    Requires both wOBA and xwOBA to confirm (mechanism-based, not threshold-only).
    """
    mech = row.get("mechanism", "insufficient_movement")
    if mech in ("confirmed", "genuine_decline"):
        return 1
    if mech == "refuted":
        return 0
    return None


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

def cmd_update():
    """Pull current luck CSVs → add weekN columns → recompute deltas & mechanism."""
    if not TRACKER.exists():
        print("No tracker found. Run --init first.")
        return

    df = pd.read_csv(TRACKER)
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

    if n_denom > 0:
        lines += [
            f"**Running accuracy: {accuracy}** ({n_conf}/{n_denom} resolved calls)",
            "",
        ]

    for call_group, header in [
        (BUY_VERDICTS,  "### Buy Signals"),
        (SELL_VERDICTS, "### Sell Signals"),
    ]:
        group = df[df["call"].isin(call_group)].copy()
        # Sort: confirmed → normalizing → re-evaluate → refuted → watch
        mech_order = {
            "confirmed":             0,
            "genuine_decline":       0,
            "results_improving":     1,
            "results_declining":     1,
            "contact_deteriorating": 2,
            "contact_improving":     2,
            "refuted":               3,
            "insufficient_movement": 4,
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
    if mech == "insufficient_movement" or (wd_val is None and xd_val is None):
        story = f"Too early — {weeks_elapsed} week{'s' if weeks_elapsed != 1 else ''} of data"
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

    n_corr = (df["prediction_correct"] == 1).sum()
    n_ref  = (df["prediction_correct"] == 0).sum()
    if n_corr + n_ref > 0:
        print(f"\nAccuracy: {n_corr/(n_corr+n_ref)*100:.1f}%  "
              f"({n_corr} confirmed / {n_ref} refuted)")
    else:
        print("\nNo resolved calls yet.")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]
    if "--init" in args:
        cmd_init()
    elif "--update" in args:
        cmd_update()
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
