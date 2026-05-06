"""
build_value_rate_history.py
===========================
Standalone diagnostic — READ ONLY. Does not modify any scoring or projection files.

Builds outputs/value_rate_history.csv showing each tracked player's
CBS production rate at three snapshots:
  S1: 2026-04-22 (Article 1 call date)
  S2: 2026-04-29 (Article 2 call date)
  S3: 2026-05-04 (latest available Statcast)

Coefficients: config.py CBS Ridge constants (exact, auditable).
R/RBI: estimated via wOBA proxy — flagged clearly.
SB: 0 (not in pitch-level data) — flagged clearly.
"""

import pandas as pd
import numpy as np
import sys
import os

sys.path.insert(0, ".")
from config import (
    CBS_H_COEF_R, CBS_H_COEF_HR, CBS_H_COEF_RBI,
    CBS_H_COEF_SB, CBS_H_COEF_AVG, CBS_H_INTERCEPT,
)

# ── Constants ──────────────────────────────────────────────────────────────────
SNAP1 = "2026-04-22"
SNAP2 = "2026-04-29"
SNAP3 = "2026-05-04"   # latest Statcast available
MIN_GAMES = 3
MIN_PA    = 10
MIN_PA_P  = 15         # pitcher minimum
R_WOBA_MULT   = 0.42   # same as project_hitter_stats
RBI_WOBA_MULT = 0.38

# Pitcher ERA proxy scaling
LG_WOBA = 0.316
LG_ERA  = 4.00
PA_PER_IP = 3.3

NON_AB  = {"walk", "hit_by_pitch", "sac_fly", "sac_bunt", "catcher_interf"}
HIT_EV  = {"single", "double", "triple", "home_run"}

# ── Target players (corrected IDs verified against luck_scores.csv) ────────────
# Note: task spec had wrong IDs for Yordan (477600→670541) and Pasquantino (672710→686469)
# Jordan Walker (694497 in spec) is actually Evan Carter — used as-is from calls_tracker.csv
# Pitcher IDs corrected: Luzardo 660271→666200, Gavin Williams 694973→668909

HITTERS = [
    (670541, "Yordan Álvarez",     "Buy low"),
    (686469, "Vinnie Pasquantino", "Buy low"),
    (663757, "Trent Grisham",      "Buy low"),
    (608369, "Corey Seager",       "Buy low"),
    (693307, "Dillon Dingler",     "Buy low"),
    (671056, "Iván Herrera",       "Buy low"),
    (694497, "Evan Carter",        "Buy low"),
    (665833, "Oneil Cruz",         "Sell high"),
    (545121, "Ildemaro Vargas",    "Sell high"),
    (656305, "Matt Chapman",       "Sell high"),
]

PITCHERS = [
    (666200, "Jesús Luzardo",      "Buy low"),
    (608379, "Michael Wacha",      "Sell high"),
    (668909, "Gavin Williams",     "Slight sell"),
    (657746, "Joe Ryan",           "Buy low"),
    (650911, "Cristopher Sánchez", "Neutral"),
    (681293, "Spencer Arrighetti", "Sell high"),
]

# ── Load data ──────────────────────────────────────────────────────────────────
print("Loading hitters_statcast.csv...")
hsc = pd.read_csv(
    "hitters_statcast.csv",
    usecols=["game_date", "batter", "events", "woba_value", "woba_denom"],
    low_memory=False,
)
hsc["game_date"] = pd.to_datetime(hsc["game_date"])

print("Loading pitchers_statcast.csv...")
psc = pd.read_csv(
    "pitchers_statcast.csv",
    usecols=["game_date", "pitcher", "events", "woba_value", "woba_denom"],
    low_memory=False,
)
psc["game_date"] = pd.to_datetime(psc["game_date"])

print("Loading pitcher_luck_scores.csv...")
pl = pd.read_csv("pitcher_luck_scores.csv")

# ── Hitter snapshot function ───────────────────────────────────────────────────
def hitter_snap(pid, cutoff):
    sub = hsc[(hsc["batter"] == pid) & (hsc["game_date"] <= pd.Timestamp(cutoff))]
    pa_rows = sub[sub["woba_denom"] == 1]
    pa    = len(pa_rows)
    games = sub["game_date"].dt.date.nunique()
    if games < MIN_GAMES or pa < MIN_PA:
        return None, games

    h   = pa_rows["events"].isin(HIT_EV).sum()
    hr  = (pa_rows["events"] == "home_run").sum()
    ab  = pa_rows[~pa_rows["events"].isin(NON_AB)].shape[0]
    avg = h / ab if ab > 0 else 0.0

    woba_vals = pa_rows["woba_value"].dropna()
    woba_mean = float(woba_vals.mean()) if len(woba_vals) > 0 else 0.250

    r_est   = woba_mean * pa * R_WOBA_MULT
    rbi_est = woba_mean * pa * RBI_WOBA_MULT

    # AVG_coef × AVG × AB = AVG_coef × H  (hits contribution to CBS FPTS)
    fpts = (
        CBS_H_COEF_R   * r_est
        + CBS_H_COEF_HR  * hr
        + CBS_H_COEF_RBI * rbi_est
        + CBS_H_COEF_AVG * avg * ab
        + CBS_H_INTERCEPT
    )
    return round(fpts / games, 2), games


# ── Pitcher snapshot function ──────────────────────────────────────────────────
def pitcher_snap(pid, cutoff):
    sub = psc[(psc["pitcher"] == pid) & (psc["game_date"] <= pd.Timestamp(cutoff))]
    pa_rows = sub[sub["woba_denom"] == 1]
    pa    = len(pa_rows)
    games = sub["game_date"].dt.date.nunique()
    if games < MIN_GAMES or pa < MIN_PA_P:
        return None, None, games

    ip_est = pa / PA_PER_IP
    woba_vals    = pa_rows["woba_value"].dropna()
    woba_allowed = float(woba_vals.mean()) if len(woba_vals) > 0 else LG_WOBA
    era_proxy    = round((woba_allowed / LG_WOBA) * LG_ERA, 2)

    h_all  = pa_rows["events"].isin(HIT_EV).sum()
    bb_all = (pa_rows["events"] == "walk").sum()
    whip_proxy = round((h_all + bb_all) / ip_est, 2) if ip_est > 0 else None

    return era_proxy, whip_proxy, games


# ── Signal confirmation logic ──────────────────────────────────────────────────
def confirm_hitter(signal, trend):
    if trend == "insufficient":
        return "INSUFFICIENT"
    if signal == "Buy low":
        return "CONFIRMING" if trend == "up" else ("FLAT" if trend == "flat" else "NOT CONFIRMING")
    else:  # Sell high
        return "CONFIRMING" if trend == "down" else ("FLAT" if trend == "flat" else "NOT CONFIRMING")


def confirm_pitcher(signal, trend):
    if trend == "insufficient":
        return "INSUFFICIENT"
    if signal == "Buy low":
        # ERA going down = confirming
        return "CONFIRMING" if trend == "down" else ("FLAT" if trend == "flat" else "NOT CONFIRMING")
    elif signal in ("Sell high", "Slight sell"):
        # ERA going up = confirming
        return "CONFIRMING" if trend == "up" else ("FLAT" if trend == "flat" else "NOT CONFIRMING")
    else:
        return "TRACKING"


# ── Build rows ─────────────────────────────────────────────────────────────────
all_rows = []

for pid, name, signal in HITTERS:
    r1, g1 = hitter_snap(pid, SNAP1)
    r2, g2 = hitter_snap(pid, SNAP2)
    r3, g3 = hitter_snap(pid, SNAP3)

    if r1 is not None and r3 is not None:
        delta = r3 - r1
        trend = "up" if delta > 1.0 else "down" if delta < -1.0 else "flat"
    else:
        delta = None
        trend = "insufficient"

    all_rows.append({
        "player": name,
        "type": "Hitter",
        "signal": signal,
        "call_date": SNAP1,
        "metric": "CBS_FPTS_per_game",
        "games_s1": g1,
        "value_rate_s1": r1 if r1 is not None else "INSUF",
        "games_s2": g2,
        "value_rate_s2": r2 if r2 is not None else "INSUF",
        "games_s3": g3,
        "value_rate_s3": r3 if r3 is not None else "INSUF",
        "trend": trend,
        "signal_confirming": confirm_hitter(signal, trend),
        "abs_change": abs(delta) if delta is not None else -1,
        "data_quality": "estimated — R/RBI via wOBA proxy; SB=0; H/HR/AB/AVG exact from pitch events",
        "notes": "Snapshot 3 = May 4 (latest Statcast)",
    })

for pid, name, signal in PITCHERS:
    e1, w1, g1 = pitcher_snap(pid, SNAP1)
    e2, w2, g2 = pitcher_snap(pid, SNAP2)
    e3, w3, g3 = pitcher_snap(pid, SNAP3)

    cur = pl[pl["pitcher"] == pid]
    act_era = float(cur["ERA"].iloc[0]) if len(cur) > 0 and "ERA" in cur.columns else None
    act_fip = float(cur["FIP"].iloc[0]) if len(cur) > 0 and "FIP" in cur.columns else None

    if e1 is not None and e3 is not None:
        delta = e3 - e1
        trend = "down" if delta < -0.15 else "up" if delta > 0.15 else "flat"
    else:
        delta = None
        trend = "insufficient"

    all_rows.append({
        "player": name,
        "type": "Pitcher",
        "signal": signal,
        "call_date": SNAP1,
        "metric": "ERA_proxy",
        "games_s1": g1,
        "value_rate_s1": e1 if e1 is not None else "INSUF",
        "games_s2": g2,
        "value_rate_s2": e2 if e2 is not None else "INSUF",
        "games_s3": g3,
        "value_rate_s3": e3 if e3 is not None else "INSUF",
        "trend": trend,
        "signal_confirming": confirm_pitcher(signal, trend),
        "abs_change": abs(delta) if delta is not None else -1,
        "data_quality": "estimated — ERA proxy from wOBA allowed; actual ERA/FIP from pitcher_luck_scores.csv",
        "notes": f"Actual ERA May5={act_era} | FIP May5={act_fip}",
    })

out = pd.DataFrame(all_rows)
out_sorted = out.sort_values(["type", "abs_change"], ascending=[True, False])

os.makedirs("outputs", exist_ok=True)
out_sorted.drop(columns=["abs_change"]).to_csv("outputs/value_rate_history.csv", index=False)
print(f"Written: outputs/value_rate_history.csv  ({len(out_sorted)} rows)")
print()

# ── Console tables ─────────────────────────────────────────────────────────────
W = 100
print("=" * W)
print("HITTERS  —  CBS FPTS per game  (R/RBI estimated via wOBA proxy; SB=0)")
print(f"{'Player':<22} {'Signal':<10} {'Apr22':>7} {'Apr29':>7} {'May4':>7} {'Trend':<5} {'Status':<16} {'G3':>3}")
print("-" * W)
for _, r in out_sorted[out_sorted["type"] == "Hitter"].iterrows():
    print(
        f"{r['player']:<22} {r['signal']:<10} "
        f"{str(r['value_rate_s1']):>7} {str(r['value_rate_s2']):>7} {str(r['value_rate_s3']):>7} "
        f"{r['trend']:<5} {r['signal_confirming']:<16} {r['games_s3']:>3}"
    )

print()
print("=" * W)
print("PITCHERS  —  ERA proxy  (wOBA-allowed based; direction only — lower = better for buys)")
print(f"{'Player':<24} {'Signal':<11} {'Apr22':>7} {'Apr29':>7} {'May4':>7} {'Trend':<5} {'Status':<16} {'Notes'}")
print("-" * W)
for _, r in out_sorted[out_sorted["type"] == "Pitcher"].iterrows():
    print(
        f"{r['player']:<24} {r['signal']:<11} "
        f"{str(r['value_rate_s1']):>7} {str(r['value_rate_s2']):>7} {str(r['value_rate_s3']):>7} "
        f"{r['trend']:<5} {r['signal_confirming']:<16} {r['notes']}"
    )

print()
print("Value rate reconstruction complete.")
print(f"Data quality : ESTIMATED for R/RBI. EXACT for H/HR/AB/AVG.")
print(f"Coefficients : R={CBS_H_COEF_R} | HR={CBS_H_COEF_HR} | RBI={CBS_H_COEF_RBI} | "
      f"SB={CBS_H_COEF_SB} (unused) | AVG={CBS_H_COEF_AVG} | Intercept={CBS_H_INTERCEPT}")
print(f"ERA proxy    : (wOBA_allowed / {LG_WOBA}) x {LG_ERA}")
print(f"Snapshot 3   : May 4 (latest Statcast available through 2026-05-04)")
print(f"ID note      : Yordan corrected 477600→670541 | Pasquantino 672710→686469")
print(f"               Luzardo 660271→666200 | Gavin Williams 694973→668909")
print(f"               694497 = Evan Carter (tracker name), not Jordan Walker")
