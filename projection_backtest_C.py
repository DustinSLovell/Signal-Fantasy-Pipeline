#!/usr/bin/env python3
"""
projection_backtest_C.py
Six-way projection comparison: Naive / RTM / Steamer / ZiPS / Our Model / Signal-Adj
Validates our system against industry preseason projections on 2025 actuals.

Methodology note:
  Steamer & ZiPS are PRESEASON full-season projections (162-game scope).
  Our Model is April-informed ROS projected forward, scaled ×1.20 to full-season equivalent.
  Counting stats (HR/R/RBI/AVG) compared against CBS 2025 full-season actuals (GP≥80 gate).
  wOBA compared against May-July 2025 Statcast actuals (≥150 PA gate, true ROS).
  Slight methodological caveat: Steamer/ZiPS full-season wOBA includes April;
    our model wOBA targets the ROS period directly — a minor advantage for us on wOBA.

Do not modify any production files.
"""

import csv
import math
from pathlib import Path

# ---------------------------------------------------------------------------
# File paths
# ---------------------------------------------------------------------------
HITTER_A   = "data/backtest_A_hitters_2025.csv"
HITTER_B   = "data/backtest_B_hitters_2025.csv"
PITCHER_A  = "data/backtest_A_pitchers_2025.csv"
PITCHER_B  = "data/backtest_B_pitchers_2025.csv"
STEAMER_H  = "Steamers 2025 batters.csv"
STEAMER_P  = "Steamers 2025 pitchers.csv"
ZIPS_H     = "zips 2025 batters.csv"
ZIPS_P     = "Zips Pitchers 2025.csv"
OUT_H      = "data/backtest_C_hitters_2025.csv"
OUT_P      = "data/backtest_C_pitchers_2025.csv"

SEP = "=" * 76


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _f(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else float("nan")
    except (TypeError, ValueError):
        return float("nan")


def mae(errs):
    v = [abs(x) for x in errs if math.isfinite(x)]
    return round(sum(v) / len(v), 4) if v else float("nan"), len(v)


def bias(errs):
    v = [x for x in errs if math.isfinite(x)]
    return round(sum(v) / len(v), 4) if v else float("nan")


def win_rate(model_errs, ref_errs):
    pairs = [(m, r) for m, r in zip(model_errs, ref_errs)
             if math.isfinite(m) and math.isfinite(r)]
    if not pairs:
        return float("nan"), 0
    wins = sum(1 for m, r in pairs if abs(m) < abs(r))
    return round(wins / len(pairs), 3), len(pairs)


def _pct(v):
    if math.isfinite(v):
        return f"{v:.1%}"
    return "  N/A "


def _m(v, dec=4):
    if math.isfinite(v):
        return f"{v:.{dec}f}"
    return "  N/A"


# ---------------------------------------------------------------------------
# Load external projections indexed by MLBAMID str
# ---------------------------------------------------------------------------
def load_ext(path: str, cols: list[str]) -> dict[str, dict]:
    out = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            bid = str(row.get("MLBAMID", "")).strip()
            if bid:
                out[bid] = {c: _f(row.get(c)) for c in cols}
    return out


def load_csv(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print(SEP)
    print("Backtest C — Six-Way Projection Comparison vs 2025 Actuals")
    print(SEP)

    # --- Load core backtest data ------------------------------------------
    hitters_a = load_csv(HITTER_A)
    hitters_b = {str(r["mlbam_id"]): r for r in load_csv(HITTER_B)}
    pitchers_a = load_csv(PITCHER_A)
    pitchers_b = {str(r["mlbam_id"]): r for r in load_csv(PITCHER_B)}

    # --- Load Steamer -------------------------------------------------------
    steamer_h = load_ext(STEAMER_H, ["HR", "R", "RBI", "AVG", "wOBA", "SB"])
    steamer_p = load_ext(STEAMER_P, ["ERA", "WHIP", "SO", "W", "FIP"])

    # --- Load ZiPS ----------------------------------------------------------
    zips_h = load_ext(ZIPS_H, ["HR", "R", "RBI", "AVG", "wOBA", "SB"])
    zips_p = load_ext(ZIPS_P, ["ERA", "WHIP", "SO", "W", "FIP"])

    # --- Match rates --------------------------------------------------------
    print("\n[Match rates]")
    h_n = len(hitters_a)
    p_n = len(pitchers_a)
    h_steam  = sum(1 for r in hitters_a if str(r["mlbam_id"]) in steamer_h)
    h_zips   = sum(1 for r in hitters_a if str(r["mlbam_id"]) in zips_h)
    h_sig    = sum(1 for r in hitters_a if str(r["mlbam_id"]) in hitters_b)
    p_steam  = sum(1 for r in pitchers_a if str(r["mlbam_id"]) in steamer_p)
    p_zips   = sum(1 for r in pitchers_a if str(r["mlbam_id"]) in zips_p)
    p_sig    = sum(1 for r in pitchers_a if str(r["mlbam_id"]) in pitchers_b)
    print(f"  Hitters  n={h_n}: Steamer {h_steam} ({100*h_steam/h_n:.1f}%)  "
          f"ZiPS {h_zips} ({100*h_zips/h_n:.1f}%)  Signal {h_sig} ({100*h_sig/h_n:.1f}%)")
    print(f"  Pitchers n={p_n}: Steamer {p_steam} ({100*p_steam/p_n:.1f}%)  "
          f"ZiPS {p_zips} ({100*p_zips/p_n:.1f}%)  Signal {p_sig} ({100*p_sig/p_n:.1f}%)")

    # --- Build merged hitter rows ------------------------------------------
    hrows = []
    for r in hitters_a:
        bid = str(r["mlbam_id"])
        b_row = hitters_b.get(bid, {})
        s = steamer_h.get(bid, {})
        z = zips_h.get(bid, {})

        rec = {
            "name":       r["name"],
            "mlbam_id":   bid,
            "april_pa":   _f(r.get("april_pa")),
            "actual_hr":  _f(r.get("actual_hr")),
            "actual_r":   _f(r.get("actual_r")),
            "actual_rbi": _f(r.get("actual_rbi")),
            "actual_avg": _f(r.get("actual_avg")),
            "actual_ros_woba": _f(r.get("actual_ros_woba")),
            # our methods
            "naive_hr":  _f(r.get("naive_hr")),   "naive_r":  _f(r.get("naive_r")),
            "naive_rbi": _f(r.get("naive_rbi")),  "naive_avg":_f(r.get("naive_avg")),
            "naive_woba":_f(r.get("naive_woba")),
            "rtm_hr":    _f(r.get("rtm_hr")),     "rtm_r":    _f(r.get("rtm_r")),
            "rtm_rbi":   _f(r.get("rtm_rbi")),    "rtm_avg":  _f(r.get("rtm_avg")),
            "rtm_woba":  _f(r.get("rtm_woba")),
            "model_hr":  _f(r.get("model_hr")),   "model_r":  _f(r.get("model_r")),
            "model_rbi": _f(r.get("model_rbi")),  "model_avg":_f(r.get("model_avg")),
            "model_woba":_f(r.get("model_woba")),
            "signal_hr": _f(b_row.get("signal_hr")),
            "signal_avg":_f(b_row.get("signal_avg")),
            "signal_woba":_f(b_row.get("signal_woba")),
            # external
            "steamer_hr": s.get("HR",  float("nan")), "steamer_r":   s.get("R",   float("nan")),
            "steamer_rbi":s.get("RBI", float("nan")), "steamer_avg": s.get("AVG", float("nan")),
            "steamer_woba":s.get("wOBA",float("nan")),
            "zips_hr":    z.get("HR",  float("nan")), "zips_r":      z.get("R",   float("nan")),
            "zips_rbi":   z.get("RBI", float("nan")), "zips_avg":    z.get("AVG", float("nan")),
            "zips_woba":  z.get("wOBA",float("nan")),
        }
        hrows.append(rec)

    # --- Build merged pitcher rows -----------------------------------------
    prows = []
    for r in pitchers_a:
        bid = str(r["mlbam_id"])
        b_row = pitchers_b.get(bid, {})
        s = steamer_p.get(bid, {})
        z = zips_p.get(bid, {})

        rec = {
            "name":       r["name"],
            "mlbam_id":   bid,
            "april_ip":   _f(r.get("april_ip")),
            "actual_era": _f(r.get("actual_era")),
            "actual_whip":_f(r.get("actual_whip")),
            "actual_k":   _f(r.get("actual_k")),
            "actual_w":   _f(r.get("actual_w")),
            # our methods
            "naive_era":  _f(r.get("naive_era")), "naive_whip": _f(r.get("naive_whip")),
            "naive_k":    _f(r.get("naive_k")),   "naive_w":    _f(r.get("naive_w")),
            "rtm_era":    _f(r.get("rtm_era")),   "rtm_whip":   _f(r.get("rtm_whip")),
            "rtm_k":      _f(r.get("rtm_k")),     "rtm_w":      _f(r.get("rtm_w")),
            "model_era":  _f(r.get("model_era")), "model_whip": _f(r.get("model_whip")),
            "model_k":    _f(r.get("model_k")),   "model_w":    _f(r.get("model_w")),
            "signal_era": _f(b_row.get("signal_era")),
            "signal_whip":_f(b_row.get("signal_whip")),
            "signal_k":   _f(b_row.get("signal_k")),
            # external
            "steamer_era": s.get("ERA", float("nan")), "steamer_whip":s.get("WHIP",float("nan")),
            "steamer_k":   s.get("SO",  float("nan")), "steamer_w":   s.get("W",   float("nan")),
            "steamer_fip": s.get("FIP", float("nan")),
            "zips_era":    z.get("ERA", float("nan")), "zips_whip":   z.get("WHIP",float("nan")),
            "zips_k":      z.get("SO",  float("nan")), "zips_w":      z.get("W",   float("nan")),
            "zips_fip":    z.get("FIP", float("nan")),
        }
        prows.append(rec)

    # =======================================================================
    # TABLE 1 — Six-way MAE
    # =======================================================================
    print(f"\n{SEP}")
    print("TABLE 1 — Six-Way MAE Comparison")
    print(f"  {'Metric':<8} {'n':>4}  {'Naive':>7}  {'RTM':>7}  {'Steamer':>8}  "
          f"{'ZiPS':>7}  {'Model':>7}  {'Signal':>7}  Winner")
    print(f"  {'-'*8} {'-'*4}  {'-'*7}  {'-'*7}  {'-'*8}  {'-'*7}  {'-'*7}  {'-'*7}  {'-'*10}")

    print("\n  Hitters:")
    woba_rows = [r for r in hrows if math.isfinite(r["actual_ros_woba"])]

    h_metrics = [
        ("HR",   "actual_hr",       "naive_hr",  "rtm_hr",  "steamer_hr", "zips_hr",  "model_hr",  "signal_hr",  hrows),
        ("AVG",  "actual_avg",      "naive_avg", "rtm_avg", "steamer_avg","zips_avg", "model_avg", "signal_avg", hrows),
        ("R",    "actual_r",        "naive_r",   "rtm_r",   "steamer_r",  "zips_r",   "model_r",   None,         hrows),
        ("RBI",  "actual_rbi",      "naive_rbi", "rtm_rbi", "steamer_rbi","zips_rbi", "model_rbi", None,         hrows),
        ("wOBA*","actual_ros_woba", "naive_woba","rtm_woba","steamer_woba","zips_woba","model_woba","signal_woba",woba_rows),
    ]

    h_results = {}
    for label, act, nv, rm, st, zp, md, sg, pool in h_metrics:
        def errs(col): return [_f(r[col]) - _f(r[act]) for r in pool if col and col in r]
        n_e = errs(nv); r_e = errs(rm); s_e = errs(st); z_e = errs(zp); m_e = errs(md)
        g_e = errs(sg) if sg else []
        n_mae, n = mae(n_e); r_mae, _ = mae(r_e); s_mae, _ = mae(s_e)
        z_mae, _ = mae(z_e); m_mae, _ = mae(m_e)
        g_mae, _ = mae(g_e) if g_e else (float("nan"), 0)

        maes = {"Naive": n_mae, "RTM": r_mae, "Steamer": s_mae,
                "ZiPS": z_mae, "Model": m_mae, "Signal": g_mae}
        valid = {k: v for k, v in maes.items() if math.isfinite(v)}
        winner = min(valid, key=valid.get) if valid else "—"

        h_results[label] = {**maes, "winner": winner, "n": n,
                            "model_bias": bias(m_e), "steamer_bias": bias(s_e),
                            "zips_bias": bias(z_e)}
        print(f"  {label:<8} {n:>4}  {_m(n_mae):>7}  {_m(r_mae):>7}  {_m(s_mae):>8}  "
              f"{_m(z_mae):>7}  {_m(m_mae):>7}  {_m(g_mae):>7}  {winner}")

    print()
    print("  Pitchers:")
    p_metrics = [
        ("ERA",  "actual_era",  "naive_era",  "rtm_era",  "steamer_era",  "zips_era",  "model_era",  "signal_era",  prows),
        ("WHIP", "actual_whip", "naive_whip", "rtm_whip", "steamer_whip", "zips_whip", "model_whip", "signal_whip", prows),
        ("K",    "actual_k",    "naive_k",    "rtm_k",    "steamer_k",    "zips_k",    "model_k",    "signal_k",    prows),
        ("W†",   "actual_w",    "naive_w",    "rtm_w",    "steamer_w",    "zips_w",    "model_w",    None,          prows),
    ]

    p_results = {}
    for label, act, nv, rm, st, zp, md, sg, pool in p_metrics:
        def errs(col): return [_f(r[col]) - _f(r[act]) for r in pool if col and col in r]
        n_e = errs(nv); r_e = errs(rm); s_e = errs(st); z_e = errs(zp); m_e = errs(md)
        g_e = errs(sg) if sg else []
        n_mae, n = mae(n_e); r_mae, _ = mae(r_e); s_mae, _ = mae(s_e)
        z_mae, _ = mae(z_e); m_mae, _ = mae(m_e)
        g_mae, _ = mae(g_e) if g_e else (float("nan"), 0)

        maes = {"Naive": n_mae, "RTM": r_mae, "Steamer": s_mae,
                "ZiPS": z_mae, "Model": m_mae, "Signal": g_mae}
        valid = {k: v for k, v in maes.items() if math.isfinite(v)}
        winner = min(valid, key=valid.get) if valid else "—"

        p_results[label] = {**maes, "winner": winner, "n": n,
                            "model_bias": bias(m_e), "steamer_bias": bias(s_e),
                            "zips_bias": bias(z_e)}
        print(f"  {label:<8} {n:>4}  {_m(n_mae):>7}  {_m(r_mae):>7}  {_m(s_mae):>8}  "
              f"{_m(z_mae):>7}  {_m(m_mae):>7}  {_m(g_mae):>7}  {winner}")

    print("\n  * wOBA compared to May-July Statcast actuals (ROS, n=200 with ≥150 PA)")
    print("    Steamer/ZiPS wOBA is full-season; ours targets ROS — slight advantage for us")
    print("  † W: our model uses identical starts×0.33 formula; Steamer/ZiPS use full models")

    # =======================================================================
    # TABLE 2 — Head-to-head win rates
    # =======================================================================
    print(f"\n{SEP}")
    print("TABLE 2 — Head-to-Head Win Rate (% players where |our err| < |their err|)")
    print(f"  {'Metric':<8} {'n':>4}  {'Mdl>Stmr':>9}  {'Mdl>ZiPS':>9}  "
          f"{'Sig>Stmr':>9}  {'Sig>ZiPS':>9}")
    print(f"  {'-'*8} {'-'*4}  {'-'*9}  {'-'*9}  {'-'*9}  {'-'*9}")

    print("\n  Hitters:")
    for label, act, nv, rm, st, zp, md, sg, pool in h_metrics:
        m_e  = [_f(r[md]) - _f(r[act]) for r in pool]
        s_e  = [_f(r[st]) - _f(r[act]) for r in pool]
        z_e  = [_f(r[zp]) - _f(r[act]) for r in pool]
        g_e  = [_f(r[sg]) - _f(r[act]) for r in pool] if sg else []

        w_ms, n_ms = win_rate(m_e, s_e)
        w_mz, n_mz = win_rate(m_e, z_e)
        w_gs, n_gs = win_rate(g_e, s_e) if g_e else (float("nan"), 0)
        w_gz, n_gz = win_rate(g_e, z_e) if g_e else (float("nan"), 0)

        flag_ms = "✓" if w_ms > 0.50 else " "
        flag_mz = "✓" if w_mz > 0.50 else " "
        flag_gs = "✓" if math.isfinite(w_gs) and w_gs > 0.50 else " "
        flag_gz = "✓" if math.isfinite(w_gz) and w_gz > 0.50 else " "

        print(f"  {label:<8} {n_ms:>4}  "
              f"{_pct(w_ms):>7}{flag_ms}  {_pct(w_mz):>7}{flag_mz}  "
              f"{_pct(w_gs):>7}{flag_gs}  {_pct(w_gz):>7}{flag_gz}")

    print()
    print("  Pitchers:")
    for label, act, nv, rm, st, zp, md, sg, pool in p_metrics:
        m_e  = [_f(r[md]) - _f(r[act]) for r in pool]
        s_e  = [_f(r[st]) - _f(r[act]) for r in pool]
        z_e  = [_f(r[zp]) - _f(r[act]) for r in pool]
        g_e  = [_f(r[sg]) - _f(r[act]) for r in pool] if sg else []

        w_ms, n_ms = win_rate(m_e, s_e)
        w_mz, n_mz = win_rate(m_e, z_e)
        w_gs, n_gs = win_rate(g_e, s_e) if g_e else (float("nan"), 0)
        w_gz, n_gz = win_rate(g_e, z_e) if g_e else (float("nan"), 0)

        flag_ms = "✓" if w_ms > 0.50 else " "
        flag_mz = "✓" if w_mz > 0.50 else " "
        flag_gs = "✓" if math.isfinite(w_gs) and w_gs > 0.50 else " "
        flag_gz = "✓" if math.isfinite(w_gz) and w_gz > 0.50 else " "

        print(f"  {label:<8} {n_ms:>4}  "
              f"{_pct(w_ms):>7}{flag_ms}  {_pct(w_mz):>7}{flag_mz}  "
              f"{_pct(w_gs):>7}{flag_gs}  {_pct(w_gz):>7}{flag_gz}")

    # =======================================================================
    # TABLE 3 — Which system wins each metric
    # =======================================================================
    print(f"\n{SEP}")
    print("TABLE 3 — Category Winner Summary")
    print(f"  {'Metric':<8} {'Winner':<10} {'2nd':<10} {'MAE':>7}  {'2nd MAE':>8}  Gap")
    print(f"  {'-'*8} {'-'*10} {'-'*10} {'-'*7}  {'-'*8}  {'-'*6}")

    all_results = {**{f"H:{k}": v for k, v in h_results.items()},
                   **{f"P:{k}": v for k, v in p_results.items()}}
    for key, res in all_results.items():
        systems = ["Naive", "RTM", "Steamer", "ZiPS", "Model", "Signal"]
        ranked = sorted([(k, res[k]) for k in systems if math.isfinite(res[k])], key=lambda x: x[1])
        if len(ranked) < 2:
            continue
        w1, m1 = ranked[0]
        w2, m2 = ranked[1]
        gap = m2 - m1
        label = key.replace("H:", "").replace("P:","P-")
        print(f"  {label:<8} {w1:<10} {w2:<10} {_m(m1):>7}  {_m(m2):>8}  {gap:.4f}")

    # =======================================================================
    # TABLE 4 — Steamer vs ZiPS head-to-head
    # =======================================================================
    print(f"\n{SEP}")
    print("TABLE 4 — Steamer vs ZiPS Head-to-Head")
    print(f"  {'Metric':<8} {'n':>4}  {'Steamer MAE':>12}  {'ZiPS MAE':>9}  "
          f"{'Stmr>ZiPS%':>11}  Winner")
    print(f"  {'-'*8} {'-'*4}  {'-'*12}  {'-'*9}  {'-'*11}  {'-'*8}")

    print("\n  Hitters:")
    for label, act, nv, rm, st, zp, md, sg, pool in h_metrics:
        s_e = [_f(r[st]) - _f(r[act]) for r in pool]
        z_e = [_f(r[zp]) - _f(r[act]) for r in pool]
        s_mae, n = mae(s_e)
        z_mae, _ = mae(z_e)
        w_sz, _ = win_rate(s_e, z_e)
        winner = "Steamer" if s_mae < z_mae else "ZiPS"
        print(f"  {label:<8} {n:>4}  {_m(s_mae):>12}  {_m(z_mae):>9}  "
              f"{_pct(w_sz):>10}  {winner}")

    print()
    print("  Pitchers:")
    for label, act, nv, rm, st, zp, md, sg, pool in p_metrics:
        s_e = [_f(r[st]) - _f(r[act]) for r in pool]
        z_e = [_f(r[zp]) - _f(r[act]) for r in pool]
        s_mae, n = mae(s_e)
        z_mae, _ = mae(z_e)
        w_sz, _ = win_rate(s_e, z_e)
        winner = "Steamer" if s_mae < z_mae else "ZiPS"
        print(f"  {label:<8} {n:>4}  {_m(s_mae):>12}  {_m(z_mae):>9}  "
              f"{_pct(w_sz):>10}  {winner}")

    # =======================================================================
    # TABLE 5 — Our biggest wins vs Steamer (wOBA and HR)
    # =======================================================================
    print(f"\n{SEP}")
    print("TABLE 5 — Our Biggest Wins vs Steamer (wOBA, top 10 by margin)")
    print(f"  {'Name':<26} {'Actual':>7} {'Steamer':>8} {'Our Model':>10} "
          f"{'Stmr err':>9} {'Mdl err':>8} {'Margin':>7}")
    print(f"  {'-'*26} {'-'*7} {'-'*8} {'-'*10} {'-'*9} {'-'*8} {'-'*7}")

    wins_woba = []
    for r in woba_rows:
        act  = _f(r["actual_ros_woba"])
        st   = _f(r["steamer_woba"])
        md   = _f(r["model_woba"])
        if not (math.isfinite(act) and math.isfinite(st) and math.isfinite(md)):
            continue
        stmr_err = abs(st - act)
        mdl_err  = abs(md - act)
        margin   = stmr_err - mdl_err   # positive = we won
        wins_woba.append((margin, r["name"], act, st, md, stmr_err, mdl_err))

    for margin, name, act, st, md, se, me in sorted(wins_woba, key=lambda x: -x[0])[:10]:
        print(f"  {name[:25]:<26} {act:>7.4f} {st:>8.4f} {md:>10.4f} "
              f"{se:>+9.4f} {me:>+8.4f} {margin:>+7.4f}")

    print(f"\n  HR top 10:")
    print(f"  {'Name':<26} {'Actual':>7} {'Steamer':>8} {'Our Model':>10} "
          f"{'Stmr err':>9} {'Mdl err':>8} {'Margin':>7}")
    print(f"  {'-'*26} {'-'*7} {'-'*8} {'-'*10} {'-'*9} {'-'*8} {'-'*7}")
    wins_hr = []
    for r in hrows:
        act = _f(r["actual_hr"]); st = _f(r["steamer_hr"]); md = _f(r["model_hr"])
        if not (math.isfinite(act) and math.isfinite(st) and math.isfinite(md)):
            continue
        se = abs(st - act); me = abs(md - act)
        wins_hr.append((se - me, r["name"], act, st, md, se, me))
    for margin, name, act, st, md, se, me in sorted(wins_hr, key=lambda x: -x[0])[:10]:
        print(f"  {name[:25]:<26} {act:>7.1f} {st:>8.1f} {md:>10.1f} "
              f"{se:>+9.1f} {me:>+8.1f} {margin:>+7.1f}")

    # =======================================================================
    # TABLE 6 — Steamer's biggest wins over us (learning opportunities)
    # =======================================================================
    print(f"\n{SEP}")
    print("TABLE 6 — Steamer's Biggest Wins Over Us (wOBA, top 10 — learning opportunities)")
    print(f"  {'Name':<26} {'Actual':>7} {'Steamer':>8} {'Our Model':>10} "
          f"{'Stmr err':>9} {'Mdl err':>8} {'Margin':>7}")
    print(f"  {'-'*26} {'-'*7} {'-'*8} {'-'*10} {'-'*9} {'-'*8} {'-'*7}")

    for margin, name, act, st, md, se, me in sorted(wins_woba, key=lambda x: x[0])[:10]:
        print(f"  {name[:25]:<26} {act:>7.4f} {st:>8.4f} {md:>10.4f} "
              f"{se:>+9.4f} {me:>+8.4f} {margin:>+7.4f}")

    print(f"\n  ERA top 10 (Steamer wins over us):")
    print(f"  {'Name':<26} {'Actual':>7} {'Steamer':>8} {'Our Model':>10} "
          f"{'Stmr err':>9} {'Mdl err':>8} {'Margin':>7}")
    print(f"  {'-'*26} {'-'*7} {'-'*8} {'-'*10} {'-'*9} {'-'*8} {'-'*7}")
    wins_era = []
    for r in prows:
        act = _f(r["actual_era"]); st = _f(r["steamer_era"]); md = _f(r["model_era"])
        if not (math.isfinite(act) and math.isfinite(st) and math.isfinite(md)):
            continue
        se = abs(st - act); me = abs(md - act)
        wins_era.append((se - me, r["name"], act, st, md, se, me))  # steamer_margin: negative = steamer won
    for margin, name, act, st, md, se, me in sorted(wins_era, key=lambda x: x[0])[:10]:
        print(f"  {name[:25]:<26} {act:>7.2f} {st:>8.2f} {md:>10.2f} "
              f"{se:>+9.2f} {me:>+8.2f} {margin:>+7.2f}")

    # =======================================================================
    # SUCCESS CRITERIA
    # =======================================================================
    print(f"\n{SEP}")
    print("SUCCESS CRITERIA")
    print(SEP)

    model_beats_both_h = []
    signal_beats_both_h = []
    for label, res in h_results.items():
        if res["Model"] < res["Steamer"] and res["Model"] < res["ZiPS"]:
            model_beats_both_h.append(label)
        if math.isfinite(res.get("Signal", float("nan"))):
            if res["Signal"] < res["Steamer"] and res["Signal"] < res["ZiPS"]:
                signal_beats_both_h.append(label)

    model_beats_both_p = []
    signal_beats_both_p = []
    for label, res in p_results.items():
        if res["Model"] < res["Steamer"] and res["Model"] < res["ZiPS"]:
            model_beats_both_p.append(label)
        if math.isfinite(res.get("Signal", float("nan"))):
            if res["Signal"] < res["Steamer"] and res["Signal"] < res["ZiPS"]:
                signal_beats_both_p.append(label)

    h_pass = len(model_beats_both_h) >= 1 or len(signal_beats_both_h) >= 1
    p_pass = len(model_beats_both_p) >= 1 or len(signal_beats_both_p) >= 1

    print(f"\n  [{'PASS' if h_pass else 'FAIL'}] Beat BOTH Steamer & ZiPS in ≥1 hitter metric")
    print(f"       Model wins: {model_beats_both_h if model_beats_both_h else 'none'}")
    print(f"       Signal wins: {signal_beats_both_h if signal_beats_both_h else 'none'}")

    print(f"\n  [{'PASS' if p_pass else 'FAIL'}] Beat BOTH Steamer & ZiPS in ≥1 pitcher metric")
    print(f"       Model wins: {model_beats_both_p if model_beats_both_p else 'none'}")
    print(f"       Signal wins: {signal_beats_both_p if signal_beats_both_p else 'none'}")

    # ERA headline check
    era_res = p_results.get("ERA", {})
    era_headline = era_res.get("Model", float("nan")) < era_res.get("Steamer", float("nan")) and \
                   era_res.get("Model", float("nan")) < era_res.get("ZiPS", float("nan"))
    woba_res = h_results.get("wOBA*", {})
    woba_headline = woba_res.get("Model", float("nan")) < woba_res.get("Steamer", float("nan")) and \
                    woba_res.get("Model", float("nan")) < woba_res.get("ZiPS", float("nan"))

    print(f"\n  Headline ERA win (beat both): {'YES — publishable' if era_headline else 'NO'}")
    print(f"  Headline wOBA win (beat both): {'YES — publishable' if woba_headline else 'NO'}")
    if woba_headline:
        print(f"    NOTE: wOBA advantage partially methodological (ROS vs full-season scope) —")
        print(f"    frame as 'April-informed model outperforms preseason consensus on ROS wOBA'")

    # =======================================================================
    # BIAS SUMMARY
    # =======================================================================
    print(f"\n{SEP}")
    print("BIAS SUMMARY (mean predicted − actual; + = over-projection)")
    print(f"  {'Metric':<8} {'Steamer':>9}  {'ZiPS':>7}  {'Model':>8}")
    print(f"  {'-'*8} {'-'*9}  {'-'*7}  {'-'*8}")
    print("  Hitters:")
    for label, res in h_results.items():
        print(f"  {label:<8} {_m(res['steamer_bias']):>9}  "
              f"{_m(res['zips_bias']):>7}  {_m(res['model_bias']):>8}")
    print("  Pitchers:")
    for label, res in p_results.items():
        print(f"  {label:<8} {_m(res['steamer_bias']):>9}  "
              f"{_m(res['zips_bias']):>7}  {_m(res['model_bias']):>8}")

    # =======================================================================
    # Save outputs
    # =======================================================================
    print(f"\n{SEP}")
    h_fields = list(hrows[0].keys()) if hrows else []
    with open(OUT_H, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=h_fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(hrows)
    print(f"  Saved: {OUT_H}  ({len(hrows)} rows)")

    p_fields = list(prows[0].keys()) if prows else []
    with open(OUT_P, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=p_fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(prows)
    print(f"  Saved: {OUT_P}  ({len(prows)} rows)")


if __name__ == "__main__":
    main()
