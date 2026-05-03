"""
career_weight_sweep.py
======================
Diagnostic sensitivity sweep: career HR weight impact on CBS FPTS and surplus.
Tests career_weight = 0.60 (current broken baseline), 0.50, 0.40, 0.30.

Players:
  Ben Rice     (C)   — values provided by user
  Jordan Walker (OF) — values pulled from luck_scores.csv + projections_2026.csv

Target surplus range: +60 to +100.
DO NOT MODIFY PRODUCTION FILES — diagnostic only.
"""
import sys, math
import pandas as pd

# ── CBS hitter coefficients (from config.py) ──────────────────────────────────
CBS_R   = 2.8067
CBS_HR  = 0.4303
CBS_RBI = 2.0806
CBS_SB  = 1.4222
CBS_AVG = 227.3683
CBS_INT = -53.0439

# ── Replacement levels (from --replacement-table run) ────────────────────────
REPL = {
    "C":  219.4,   # Drake Baldwin  N=12
    "OF": 243.1,   # Jake McCarthy  N=36
}

BARREL_TO_HR = 0.42   # config.py

# Career weights to sweep (0.60 = current broken baseline)
WEIGHTS = [0.60, 0.50, 0.40, 0.30]

TARGET_LO, TARGET_HI = 60.0, 100.0


# ── Helpers ───────────────────────────────────────────────────────────────────

def cbs_fpts(r, hr, rbi, sb, avg):
    return r * CBS_R + hr * CBS_HR + rbi * CBS_RBI + sb * CBS_SB + avg * CBS_AVG + CBS_INT


def surplus_verdict(s):
    if s >= 100: return "STRONG"
    if s >=  60: return "FAVORABLE  ← target range"
    if s >=  20: return "SLIGHT+"
    if s >=   5: return "SLIGHT+"
    if s >=  -5: return "NEUTRAL"
    if s >= -20: return "SLIGHT-"
    if s >= -50: return "UNFAVORABLE"
    return "AVOID"


def run_sweep(name, pos, career_hr_rate, true_hr_rate, proj_pa,
              proj_r, proj_rbi, proj_sb, proj_avg, signal):
    repl = REPL[pos]
    print()
    print("=" * 72)
    print(f"  {name}  ({pos})  |  signal: {signal}  |  proj_PA: {proj_pa}")
    print(f"  career_hr_rate: {career_hr_rate:.4f}   true_hr_rate (barrel-derived): {true_hr_rate:.4f}")
    print(f"  Fixed stats — R: {proj_r}  RBI: {proj_rbi}  SB: {proj_sb}  AVG: {proj_avg:.3f}")
    print(f"  {pos} replacement FPTS: {repl:.1f}")
    print("=" * 72)
    print(f"  {'CW':>5}  {'Blnd%':>6}  {'HR':>4}  {'FPTS':>7}  {'Surplus':>8}  Verdict")
    print(f"  {'-'*65}")

    for cw in WEIGHTS:
        blended = cw * career_hr_rate + (1.0 - cw) * true_hr_rate
        hr      = int(proj_pa * blended)
        fpts    = cbs_fpts(proj_r, hr, proj_rbi, proj_sb, proj_avg)
        surp    = fpts - repl
        label   = surplus_verdict(surp)

        flags = []
        if cw == 0.60:
            flags.append("← CURRENT BROKEN BASELINE")
        elif TARGET_LO <= surp <= TARGET_HI:
            flags.append("← IN TARGET RANGE")

        flag_str = "  " + flags[0] if flags else ""
        print(f"  {cw:.2f}   {blended:.4f}   {hr:>4}  {fpts:>7.1f}  {surp:>+8.1f}  {label}{flag_str}")

    print()
    # Crossover: what weight produces surplus at threshold boundaries?
    for threshold, tname in [(60.0, "+60 (target floor)"), (20.0, "+20 (favorable)")]:
        # surplus = fpts(hr) - repl; fpts = f(hr); hr = floor(proj_pa * blended)
        # Find continuous crossover weight (ignoring floor())
        # repl + threshold = cbs_fpts(r, pa*blended, rbi, sb, avg)
        # CBS_HR * pa * blended = (repl + threshold - cbs_fpts(r,0,rbi,sb,avg))
        base_fpts = cbs_fpts(proj_r, 0, proj_rbi, proj_sb, proj_avg)
        needed_hr = (repl + threshold - base_fpts) / CBS_HR
        needed_rate = needed_hr / proj_pa
        # blended = cw * career + (1-cw) * true  →  cw = (needed - true)/(career - true)
        denom = career_hr_rate - true_hr_rate
        if abs(denom) < 1e-9:
            print(f"  Crossover {tname}: career==true rate, N/A")
        else:
            cw_cross = (needed_rate - true_hr_rate) / denom
            cw_cross = max(0.0, min(1.0, cw_cross))
            print(f"  Crossover {tname}: career_weight ≈ {cw_cross:.2f}  (HR needed: {needed_hr:.1f})")


# ── BEN RICE (user-provided values) ──────────────────────────────────────────

rice_params = dict(
    name           = "Ben Rice",
    pos            = "C",
    career_hr_rate = 0.029,
    true_hr_rate   = 0.052,
    proj_pa        = 285,
    proj_r         = 36,
    proj_rbi       = 32,
    proj_sb        = 2,
    proj_avg       = 0.270,
    signal         = "Sell High",
)

# ── JORDAN WALKER (pulled from luck_scores.csv + projections_2026.csv) ────────

luck = pd.read_csv("luck_scores.csv")
proj = pd.read_csv("data/projections_2026.csv")

wluck = luck[luck["name"] == "Jordan Walker"].iloc[0]
wproj = proj[proj["name"] == "Jordan Walker"].iloc[0]

# Rates from luck_scores (same formulas as hitter_true_talent in stat_projections.py)
barrel_rate   = float(wluck["barrel_rate"])
bb_rate       = float(wluck["bb_rate"])
k_rate        = float(wluck["k_rate"])
bip_rate      = max(0.0, 1.0 - k_rate - bb_rate)
w_true_hr     = min(0.090, barrel_rate * bip_rate * BARREL_TO_HR)

# Career HR rate from xwoba_3yr (matches stat_projections.py line 535)
xwoba_3yr      = float(wluck["xwoba_3yr"])
w_career_hr    = max(0.010, min(0.090, (xwoba_3yr - 0.25) * 0.10 + 0.020))

# Projected PA: back-calculate from current proj_hr + the weight used at PA=130
# sample_weight(130) = 0.45 → career_weight = 0.55
w_cw_used      = 0.55
w_blended_used = w_cw_used * w_career_hr + (1.0 - w_cw_used) * w_true_hr
w_proj_hr_now  = int(wproj["proj_hr"])
w_proj_pa      = int(round(w_proj_hr_now / w_blended_used)) if w_blended_used > 0 else 400

walker_params = dict(
    name           = "Jordan Walker",
    pos            = "OF",
    career_hr_rate = w_career_hr,
    true_hr_rate   = w_true_hr,
    proj_pa        = w_proj_pa,
    proj_r         = int(wproj["proj_r"]),
    proj_rbi       = int(wproj["proj_rbi"]),
    proj_sb        = int(wproj["proj_sb"]),
    proj_avg       = float(wproj["proj_avg"]),
    signal         = str(wproj["signal"]),
)

# ── Diagnostic inputs printout ────────────────────────────────────────────────

print("\n" + "=" * 72)
print("  CAREER WEIGHT SENSITIVITY SWEEP — HR PROJECTION & SURPLUS IMPACT")
print("=" * 72)

print("\n  Derived Walker inputs (from luck_scores.csv):")
print(f"    barrel_rate   : {barrel_rate:.4f}")
print(f"    bb_rate       : {bb_rate:.4f}")
print(f"    k_rate        : {k_rate:.4f}")
print(f"    bip_rate      : {bip_rate:.4f}")
print(f"    xwoba_3yr     : {xwoba_3yr:.4f}")
print(f"    career_pa     : {int(wluck['career_pa'])}")
print(f"  Derived rates:")
print(f"    true_hr_rate  : {w_true_hr:.4f}  (barrel × bip × {BARREL_TO_HR})")
print(f"    career_hr_rate: {w_career_hr:.4f}  ((xwoba_3yr - 0.25) × 0.10 + 0.020)")
print(f"    cw_at_PA=130  : 0.55  (sample_weight=0.45 → hist_weight=0.55)")
print(f"    proj_hr (now) : {w_proj_hr_now}  → back-calc proj_PA ≈ {w_proj_pa}")

# ── Run sweeps ────────────────────────────────────────────────────────────────

run_sweep(**rice_params)
run_sweep(**walker_params)

# ── Summary table ─────────────────────────────────────────────────────────────

print("\n" + "=" * 72)
print("  SUMMARY — Surplus at each career weight")
print("=" * 72)
print(f"  {'Player':<20} {'CW=0.60':>10} {'CW=0.50':>10} {'CW=0.40':>10} {'CW=0.30':>10}  Target: +60→+100")
print(f"  {'-'*65}")

for params in [rice_params, walker_params]:
    repl = REPL[params["pos"]]
    row_vals = []
    for cw in WEIGHTS:
        blended = cw * params["career_hr_rate"] + (1.0 - cw) * params["true_hr_rate"]
        hr      = int(params["proj_pa"] * blended)
        fpts    = cbs_fpts(params["proj_r"], hr, params["proj_rbi"],
                           params["proj_sb"], params["proj_avg"])
        row_vals.append(fpts - repl)
    flags = ["←BROKEN" if i == 0 else ("✓" if TARGET_LO <= row_vals[i] <= TARGET_HI else "")
             for i in range(len(WEIGHTS))]
    cells = [f"{v:>+6.0f}{flags[i]}" for i, v in enumerate(row_vals)]
    name  = params["name"]
    print(f"  {name:<20} {cells[0]:>10} {cells[1]:>10} {cells[2]:>10} {cells[3]:>10}")

print()
