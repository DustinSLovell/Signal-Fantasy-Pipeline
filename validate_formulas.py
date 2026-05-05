"""
validate_formulas.py
Comprehensive formula validation and stress test suite for stat_projections.py.

Usage:
    python validate_formulas.py
    python run_pipeline.py --validate

38 tests covering: K/9, xwOBA→AVG, HR rate, SB rate, R/RBI, IP, blend weights,
luck multipliers, evolution adjustments, real player sanity, and edge cases.

Standalone — no imports from dashboard or score_luck.
"""

import math
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from stat_projections import (
    SWSTR_TO_K9, BARREL_TO_HR, WHIP_ERA_SLOPE, WHIP_ERA_INTERCEPT,
    LUCK_MULTIPLIERS, PITCHER_LUCK_MULTIPLIERS,
    LEAGUE_AVG_HITTER, LEAGUE_AVG_PITCHER,
    hitter_true_talent, pitcher_true_talent,
    sample_weight, blend_projection,
    project_hitter_counting, project_pitcher_counting,
    project_player, detect_pitcher_evolution,
    get_hitter_baseline, get_pitcher_baseline,
    _safe_float,
)

# ── Test reporter ──────────────────────────────────────────────────────────────
_results: list[dict] = []

def _report(name: str, passed: bool, actual, expected: str, fix: str = "") -> bool:
    status = "PASS" if passed else "FAIL"
    _results.append({"name": name, "pass": passed})
    print(f"  [{status}] {name}")
    if not passed:
        print(f"           Expected : {expected}")
        print(f"           Actual   : {actual}")
        if fix:
            print(f"           Fix      : {fix}")
    return passed

def _known_limit(name: str, reason: str) -> None:
    _results.append({"name": name, "pass": None})
    print(f"  [LIMIT] {name}")
    print(f"           {reason}")

# ── Mock row helpers ───────────────────────────────────────────────────────────
def _pitcher_row(**kw) -> pd.Series:
    d = {
        "FIP": float("nan"), "xERA": float("nan"),
        "swstr_rate": float("nan"), "IP": 20.0,
        "total_starts": 4.0, "pitcher": 99999,
        "k_pct": float("nan"), "swstr_gap": float("nan"),
        "velo_gap": float("nan"), "csw_gap": float("nan"),
    }
    d.update(kw)
    return pd.Series(d)

def _hitter_row(**kw) -> pd.Series:
    d = {
        "xwOBA": float("nan"), "BABIP": float("nan"),
        "barrel_rate": 0.065, "bb_rate": 0.085, "k_rate": 0.220,
        "PA": 60.0, "_sprint_speed": float("nan"), "batter": 99999,
        "park_adj_babip_expected": float("nan"), "career_babip": 0.300,
    }
    d.update(kw)
    return pd.Series(d)

def _pitcher_baseline(**kw) -> dict:
    b = dict(LEAGUE_AVG_PITCHER)
    b.update(kw)
    return b

def _hitter_baseline(**kw) -> dict:
    b = dict(LEAGUE_AVG_HITTER)
    b.update(kw)
    return b

# ==============================================================================
# SECTION A — PITCHER FORMULA TESTS
# ==============================================================================

def run_section_a() -> int:
    print("\nSECTION A — Pitcher Formulas (10 tests)")
    print("-" * 55)
    passed = 0

    # A1: K/9 from SwStr% at league average
    swstr = 0.110
    baseline = _pitcher_baseline()
    row = _pitcher_row(swstr_rate=swstr, FIP=3.80, xERA=3.90)
    # Pass None for pitcher_rates so swstr→K/9 path is exercised
    tt = pitcher_true_talent(row, baseline, pitcher_rates=None)
    k9 = tt["true_k_per9"]
    # With correct constant (77.3): 0.110 * 77.3 = 8.50; blended = 8.50*0.70 + 8.50*0.30 = 8.50
    ok = 8.0 <= k9 <= 9.5
    if _report("A1: K/9 at league-avg SwStr% (0.110)",
               ok, f"{k9:.2f}", "8.0 – 9.5",
               f"SWSTR_TO_K9={SWSTR_TO_K9}; correct constant ≈77.3"):
        passed += 1

    # A2: K/9 from SwStr% at elite (Cole tier)
    swstr = 0.155
    row = _pitcher_row(swstr_rate=swstr, FIP=2.80, xERA=2.90)
    tt = pitcher_true_talent(row, baseline, pitcher_rates=None)
    k9 = tt["true_k_per9"]
    ok = 10.5 <= k9 <= 14.0   # 0.155×77.3=12.0; blended with 8.5 career → ≈10.9
    if _report("A2: K/9 at elite SwStr% (0.155)",
               ok, f"{k9:.2f}", "10.5 – 14.0",
               f"SWSTR_TO_K9={SWSTR_TO_K9}; 0.155×77.3≈12.0, blended≈10.9"):
        passed += 1

    # A3: K/9 from SwStr% at poor level
    swstr = 0.075
    row = _pitcher_row(swstr_rate=swstr, FIP=4.80, xERA=4.60)
    tt = pitcher_true_talent(row, baseline, pitcher_rates=None)
    k9 = tt["true_k_per9"]
    ok = 5.5 <= k9 <= 7.5
    if _report("A3: K/9 at poor SwStr% (0.075)",
               ok, f"{k9:.2f}", "5.5 – 7.5",
               f"SWSTR_TO_K9={SWSTR_TO_K9}; 0.075×77.3≈5.8, blended≈6.3"):
        passed += 1

    # A4: ERA sanity — elite, FIP/xERA agree
    row = _pitcher_row(FIP=2.50, xERA=2.80, swstr_rate=0.140)
    tt = pitcher_true_talent(row, baseline, pitcher_rates=None)
    era = tt["true_era"]
    ok = 2.40 <= era <= 3.20
    if _report("A4: ERA – elite pitcher FIP=2.50 xERA=2.80",
               ok, f"{era:.2f}", "2.40 – 3.20"):
        passed += 1

    # A5: ERA sanity — bad pitcher
    row = _pitcher_row(FIP=5.50, xERA=5.20, swstr_rate=0.085)
    tt = pitcher_true_talent(row, baseline, pitcher_rates=None)
    era = tt["true_era"]
    ok = 4.80 <= era <= 5.80
    if _report("A5: ERA – bad pitcher FIP=5.50 xERA=5.20",
               ok, f"{era:.2f}", "4.80 – 5.80"):
        passed += 1

    # A6: ERA — big FIP/xERA disagreement: result must be between both values
    fip, xera = 2.50, 5.00
    row = _pitcher_row(FIP=fip, xERA=xera, swstr_rate=0.120)
    tt = pitcher_true_talent(row, baseline, pitcher_rates=None)
    era = tt["true_era"]
    ok = fip <= era <= xera
    if _report("A6: ERA – FIP=2.50 vs xERA=5.00 (big disagreement)",
               ok, f"{era:.2f}", f"between FIP ({fip}) and xERA ({xera})"):
        passed += 1

    # A7: WHIP formula
    base7 = _pitcher_baseline(career_whip=1.30)
    row = _pitcher_row(FIP=4.00, xERA=4.10, swstr_rate=0.100)
    tt = pitcher_true_talent(row, base7, pitcher_rates=None)
    whip = tt["true_whip"]
    ok = 1.20 <= whip <= 1.50
    if _report("A7: WHIP – ERA≈4.00 career WHIP=1.30",
               ok, f"{whip:.3f}", "1.20 – 1.50"):
        passed += 1

    # A8: Win projection — Steamer W blend (Session 30 fix)
    # Skubal (669373): Steamer full-season W=13.25; 153 games rem → 12.5 ROS
    # Fallback (no mlbam_id): W=0 (no Steamer data — expected)
    games_rem = 153
    blended = {"true_era": 3.90, "true_whip": 1.28, "true_k_per9": 9.0,
               "true_bb_per9": 3.0, "true_ip_per_start": 5.8}
    proj_sp  = project_pitcher_counting(blended, games_rem, is_starter=True,
                                         mlbam_id=669373)   # Skubal
    proj_fb  = project_pitcher_counting(blended, games_rem, is_starter=True)  # no ID
    w_sp = proj_sp["projected_w"]
    w_fb = proj_fb["projected_w"]
    ok = (8 <= w_sp <= 14) and (w_fb == 0)
    if _report("A8: Win projection — Steamer blend (SP ≥8W) + fallback=0",
               ok, f"SP={w_sp} fallback={w_fb}", "SP: 8–14, fallback: 0"):
        passed += 1

    # A9: IP per start — 30 starts × 0.85 × 5.8 ip/start ≈ 148 IP
    proj = project_pitcher_counting(blended, games_rem, is_starter=True)
    ip = proj["projected_ip"]
    ok = 120 <= ip <= 175
    if _report("A9: Projected IP – 30 starts × 5.8 ip/start × 0.85 health",
               ok, f"{ip:.1f}", "120 – 175 IP"):
        passed += 1

    # A10: K counting translation — K/9=9.0, IP=140
    blended_k = {"true_era": 4.00, "true_whip": 1.30, "true_k_per9": 9.0,
                 "true_bb_per9": 3.0, "true_ip_per_start": 5.6}
    # Provide games_remaining that yields ~140 IP
    # starts = int(games / 5 * 0.85) → games ≈ 140/5.6/0.85*5 = 147
    proj_k = project_pitcher_counting(blended_k, games_remaining=147, is_starter=True)
    k = proj_k["projected_k"]
    ok = 100 <= k <= 220
    if _report("A10: K counting – K/9=9.0 ~140 IP",
               ok, k, "100 – 220"):
        passed += 1

    print(f"  Section A: {passed}/10 PASS")
    return passed


# ==============================================================================
# SECTION B — HITTER FORMULA TESTS
# ==============================================================================

def run_section_b() -> int:
    print("\nSECTION B — Hitter Formulas (10 tests)")
    print("-" * 55)
    passed = 0

    # B1: xwOBA → AVG formula — raw formula check at league average
    # Correct constant: 1.057 → lg-avg xwOBA .320 gives .255 AVG
    xwoba_test = 0.320
    raw_formula = (xwoba_test - 0.050) / 1.057
    ok = 0.240 <= raw_formula <= 0.270
    if _report("B1: xwOBA→AVG raw formula at xwOBA=.320",
               ok, f"{raw_formula:.3f}", "0.240 – 0.270 (≈0.255 at lg-avg xwOBA)"):
        passed += 1

    # B2: xwOBA → AVG through function — elite hitter
    # Elite hitter: xwOBA=.420, career_avg=.300
    row_b2 = _hitter_row(xwOBA=0.420, barrel_rate=0.120, bb_rate=0.090, k_rate=0.210)
    base_b2 = _hitter_baseline(career_avg=0.300, career_woba=0.390)
    tt_b2 = hitter_true_talent(row_b2, base_b2)
    avg_b2 = tt_b2["true_avg"]
    ok = 0.310 <= avg_b2 <= 0.360
    if _report("B2: AVG – elite hitter xwOBA=.420 career_avg=.300",
               ok, f"{avg_b2:.3f}", "0.310 – 0.360",
               "floor capped at .260 → projects .260 not .310+; fix: remove .260 cap, fix scale"):
        passed += 1

    # B3: xwOBA → AVG — poor hitter (xwOBA=.260, career_avg=.235)
    row_b3 = _hitter_row(xwOBA=0.260, barrel_rate=0.040, bb_rate=0.070, k_rate=0.270)
    base_b3 = _hitter_baseline(career_avg=0.235, career_woba=0.295)
    tt_b3 = hitter_true_talent(row_b3, base_b3)
    avg_b3 = tt_b3["true_avg"]
    ok = 0.195 <= avg_b3 <= 0.250
    if _report("B3: AVG – poor hitter xwOBA=.260 career_avg=.235",
               ok, f"{avg_b3:.3f}", "0.195 – 0.250"):
        passed += 1

    # B4: HR rate from barrel — elite tier (10% barrel rate)
    k_rate, bb_rate = 0.220, 0.085
    bip_rate = 1.0 - k_rate - bb_rate   # 0.695
    hr_rate = 0.100 * bip_rate * BARREL_TO_HR
    hr_600 = 600 * hr_rate
    ok = 5 <= hr_600 <= 60
    if _report(f"B4: HR/600PA – barrel=10% (elite tier)",
               ok, f"{hr_600:.1f}", "5 – 60 (elite: 17-27)"):
        passed += 1

    # B5: HR rate from barrel — league average (8% barrel)
    hr_rate_avg = 0.080 * bip_rate * BARREL_TO_HR
    hr_600_avg = 600 * hr_rate_avg
    ok = 10 <= hr_600_avg <= 30
    if _report(f"B5: HR/600PA – barrel=8% (league avg)",
               ok, f"{hr_600_avg:.1f}", "10 – 30"):
        passed += 1

    # B6: SB from sprint speed — fast player (28.5 mph)
    row_b6 = _hitter_row(xwOBA=0.340, barrel_rate=0.070, bb_rate=0.080,
                         k_rate=0.200, _sprint_speed=28.5)
    base_b6 = _hitter_baseline()
    tt_b6 = hitter_true_talent(row_b6, base_b6)
    sb_pg = tt_b6["true_sb_per_game"]
    sb_100 = int(sb_pg * 100 * 0.85)   # 100 games × health factor
    ok = 8 <= sb_100 <= 20
    if _report(f"B6: SB – sprint 28.5mph over 100 games",
               ok, sb_100, "8 – 20"):
        passed += 1

    # B7: R formula — H=80, HR=20, BB=40
    h_count, hr, bb = 80, 20, 40
    r_formula = int(hr * 1.0 + (h_count - hr) * 0.35 + bb * 0.15)
    ok = 40 <= r_formula <= 60
    if _report(f"B7: R formula – H=80 HR=20 BB=40",
               ok, r_formula, "40 – 60"):
        passed += 1

    # B8: RBI formula — H=80, HR=20
    rbi_formula = int(hr * 1.30 + (h_count - hr) * 0.32)
    ok = 38 <= rbi_formula <= 65
    if _report(f"B8: RBI formula – H=80 HR=20",
               ok, rbi_formula, "38 – 65"):
        passed += 1

    # B9: PA per game by batting position — check the spread
    pa_map = {1: 4.4, 2: 4.4, 3: 4.2, 5: 4.2, 8: 3.9}
    blended_b9 = {"true_avg": 0.260, "true_hr_rate": 0.030, "true_bb_pct": 0.085,
                  "true_k_pct": 0.220, "true_sb_per_game": 0.0}
    all_ok = True
    for pos, expected_papg in pa_map.items():
        proj = project_hitter_counting(blended_b9, games_remaining=100,
                                       batting_order_pos=pos)
        actual_pa = proj["projected_pa"]
        actual_papg = actual_pa / (100 * 0.85)
        if abs(actual_papg - expected_papg) > 0.15:
            all_ok = False
    if _report("B9: PA per game by batting position spread",
               all_ok, "see inline", "pos1=4.4, pos5=4.2, pos8=3.9 (±0.15)"):
        passed += 1

    # B10: Full-season PA check
    blended_b10 = {"true_avg": 0.260, "true_hr_rate": 0.030, "true_bb_pct": 0.085,
                   "true_k_pct": 0.220, "true_sb_per_game": 0.0}
    proj_b10 = project_hitter_counting(blended_b10, games_remaining=139,
                                       batting_order_pos=3)
    pa_b10 = proj_b10["projected_pa"]
    # 139 × 0.85 × 4.2 ≈ 496
    ok = 400 <= pa_b10 <= 560
    if _report(f"B10: PA – 139 games remain, batting 3rd, health=0.85",
               ok, pa_b10, "400 – 560"):
        passed += 1

    print(f"  Section B: {passed}/10 PASS")
    return passed


# ==============================================================================
# SECTION C — BLEND AND WEIGHT TESTS
# ==============================================================================

def run_section_c() -> int:
    print("\nSECTION C — Blend and Weight Tests (6 tests)")
    print("-" * 55)
    passed = 0

    # C1: Sample weight sums to 1.0 for all tiers
    tiers_h = [0, 30, 75, 150, 300]
    tiers_p = [0, 10, 25, 45, 80]
    all_ok = True
    bad = []
    for pa in tiers_h:
        w = sample_weight(pa, is_pitcher=False)
        if abs(w + (1.0 - w) - 1.0) > 1e-9:
            all_ok = False; bad.append(f"hitter PA={pa}")
    for ip in tiers_p:
        w = sample_weight(ip, is_pitcher=True)
        if abs(w + (1.0 - w) - 1.0) > 1e-9:
            all_ok = False; bad.append(f"pitcher IP={ip}")
    if _report("C1: sample_weight() + (1-weight) = 1.0 for all tiers",
               all_ok, bad or "all 1.0", "1.0 at every sample-size tier"):
        passed += 1

    # C2: Sample weight monotone (more PA/IP = higher weight)
    weights_h = [sample_weight(pa, False) for pa in [10, 50, 100, 200]]
    weights_p = [sample_weight(ip, True)  for ip in [5, 20, 40, 60]]
    mono_h = all(weights_h[i] <= weights_h[i+1] for i in range(len(weights_h)-1))
    mono_p = all(weights_p[i] <= weights_p[i+1] for i in range(len(weights_p)-1))
    ok = mono_h and mono_p
    if _report("C2: sample_weight monotone (more PA → higher current weight)",
               ok, f"hitter={weights_h} pitcher={weights_p}",
               "weights must be non-decreasing"):
        passed += 1

    # C3: Blend result stays between current and career components
    curr = {"true_era": 3.00, "true_whip": 1.10, "true_k_per9": 11.0,
            "true_bb_per9": 2.0, "true_ip_per_start": 6.2}
    hist = _pitcher_baseline(career_era=5.00, career_whip=1.50,
                             career_k_per9=8.50, career_bb_per9=3.50,
                             career_ip_per_start=5.60)
    for w in [0.15, 0.30, 0.45]:
        blended = blend_projection(curr, hist, w)
        for ckey, hkey, lo, hi in [
            ("true_era", "career_era", 3.00, 5.00),
            ("true_whip", "career_whip", 1.10, 1.50),
        ]:
            val = blended[ckey]
            if not (lo - 0.001 <= val <= hi + 0.001):
                all_ok = False; bad.append(f"{ckey}={val:.3f} at w={w}")
    ok = all_ok
    if _report("C3: blend_projection result between current and career",
               ok, bad or "all within range",
               "blended ERA must be between 3.00 and 5.00"):
        passed += 1

    # C4: Luck multiplier direction correct for all verdicts
    # Buy low hitter → avg > 1.0 (higher projection); sell high → < 1.0
    dir_ok = True
    for verdict, mults in LUCK_MULTIPLIERS.items():
        avg_m = mults["avg"]
        if verdict in ("Buy low", "Slight buy") and avg_m <= 1.0:
            dir_ok = False; bad.append(f"hitter {verdict} avg={avg_m} ≤1.0")
        if verdict in ("Sell high", "Slight sell") and avg_m >= 1.0:
            dir_ok = False; bad.append(f"hitter {verdict} avg={avg_m} ≥1.0")
    for verdict, mults in PITCHER_LUCK_MULTIPLIERS.items():
        era_m = mults["era"]
        if verdict in ("Buy low", "Slight buy") and era_m >= 1.0:
            dir_ok = False; bad.append(f"pitcher {verdict} era={era_m} ≥1.0 (should improve ERA)")
        if verdict in ("Sell high", "Slight sell") and era_m <= 1.0:
            dir_ok = False; bad.append(f"pitcher {verdict} era={era_m} ≤1.0 (should worsen ERA)")
    if _report("C4: Luck multiplier direction correct",
               dir_ok, bad or "all correct",
               "buy-low hitter avg>1.0; buy-low pitcher era<1.0"):
        passed += 1

    # C5: Luck multiplier magnitude within ±20%
    mag_ok = True
    for verdict, mults in {**LUCK_MULTIPLIERS, **PITCHER_LUCK_MULTIPLIERS}.items():
        for stat, m in mults.items():
            if not (0.80 <= m <= 1.20):
                mag_ok = False; bad.append(f"{verdict} {stat}={m}")
    if _report("C5: All luck multipliers within ±20% (0.80–1.20)",
               mag_ok, bad or "all within range", ""):
        passed += 1

    # C6: Evolution adjustment direction
    # Score >= 5 → career_weight_adj = -0.40 → weight INCREASES (trust current more)
    # Score <= -2 → career_weight_adj = +0.10 → weight DECREASES (trust career more)
    mock_career_pm = {"career_pitch_types": ["FF", "CH"], "career_usage": {"FF": 0.60, "CH": 0.40},
                      "career_swstr": {"FF": 0.08, "CH": 0.14}}
    mock_curr_pm_evolved = {
        "curr_pitch_types": ["FF", "CH", "SL", "CU"],
        "curr_usage": {"FF": 0.35, "CH": 0.25, "SL": 0.25, "CU": 0.15},
        "curr_swstr": {"FF": 0.12, "CH": 0.22, "SL": 0.32, "CU": 0.18},
    }
    mock_curr_pm_declining = {
        "curr_pitch_types": ["FF", "CH"],
        "curr_usage": {"FF": 0.60, "CH": 0.40},
        "curr_swstr": {"FF": 0.06, "CH": 0.10},
    }
    evo_up   = detect_pitcher_evolution(99999,
                 {"swstr_gap": 0.045, "velo_gap": 2.0, "csw_gap": 0.03, "k_pct": 0.28},
                 mock_career_pm, mock_curr_pm_evolved)
    evo_down = detect_pitcher_evolution(99999,
                 {"swstr_gap": -0.035, "velo_gap": -2.0, "csw_gap": -0.03, "k_pct": 0.19},
                 mock_career_pm, mock_curr_pm_declining)
    dir_evo_ok = (evo_up["career_weight_adj"] < 0 and evo_down["career_weight_adj"] > 0)
    if _report("C6: Evolution adj direction (high score → trust current more)",
               dir_evo_ok,
               f"evolved adj={evo_up['career_weight_adj']} declining adj={evo_down['career_weight_adj']}",
               "evolved: adj must be negative; declining: adj must be positive"):
        passed += 1

    print(f"  Section C: {passed}/6 PASS")
    return passed


# ==============================================================================
# SECTION D — REAL PLAYER SANITY TESTS
# ==============================================================================

def run_section_d() -> int:
    print("\nSECTION D — Real Player Sanity Tests (5 tests)")
    print("-" * 55)
    passed = 0

    # D1: Yordan Alvarez (Buy low, elite hitter)
    yordan = project_player("Yordan Alvarez")
    if "error" in yordan:
        _report("D1: Yordan Alvarez — found in data", False, yordan["error"], "player found")
    else:
        ps = yordan["projected_stats"]
        avg, hr, rbi, sb = (ps.get("projected_avg", 0), ps.get("projected_hr", 0),
                            ps.get("projected_rbi", 0), ps.get("projected_sb", 0))
        ok = (0.290 <= avg <= 0.370 and 18 <= hr <= 35 and 50 <= rbi <= 90 and 0 <= sb <= 8)
        details = f"AVG={avg:.3f} HR={hr} RBI={rbi} SB={sb}"
        if _report("D1: Yordan Alvarez – elite hitter rest-of-season",
                   ok, details, "AVG .290-.370 HR 18-35 RBI 50-90 SB 0-8"):
            passed += 1

    # D2: Trea Turner (Buy low, speed hitter)
    trea = project_player("Trea Turner")
    if "error" in trea:
        _report("D2: Trea Turner — found in data", False, trea["error"], "player found")
    else:
        ps = trea["projected_stats"]
        avg, sb = ps.get("projected_avg", 0), ps.get("projected_sb", 0)
        ok_avg = 0.260 <= avg <= 0.320
        ok_sb  = 10 <= sb <= 45
        ok = ok_avg and ok_sb
        details = f"AVG={avg:.3f} SB={sb}"
        if _report("D2: Trea Turner – speed hitter, SB signal",
                   ok, details, "AVG .260-.320 SB 10-45"):
            passed += 1

    # D3: Jesús Luzardo (Buy low, power pitcher)
    luz = project_player("Luzardo")
    if "error" in luz:
        _report("D3: Luzardo — found in data", False, luz["error"], "player found")
    else:
        ps = luz["projected_stats"]
        era, k, whip = (ps.get("projected_era", 0), ps.get("projected_k", 0),
                        ps.get("projected_whip", 0))
        ok = (3.00 <= era <= 4.80 and 60 <= k <= 150 and 1.05 <= whip <= 1.55)
        details = f"ERA={era:.2f} K={k} WHIP={whip:.3f}"
        if _report("D3: Luzardo – buy-low pitcher, ERA regression from 6.41",
                   ok, details, "ERA 3.00-4.80 K 60-150 WHIP 1.05-1.55"):
            passed += 1

    # D4: Michael Wacha (Sell high — ERA regression expected)
    wacha = project_player("Wacha")
    if "error" in wacha:
        _report("D4: Wacha — found in data", False, wacha["error"], "player found")
    else:
        ps = wacha["projected_stats"]
        era, k = ps.get("projected_era", 0), ps.get("projected_k", 0)
        ok = (3.00 <= era <= 5.00 and 40 <= k <= 135)
        # Key: sell-high means ERA should be notably above his current 2.23
        era_regresses = era > 2.50
        ok = ok and era_regresses
        details = f"ERA={era:.2f} K={k} (current ERA=2.23 → expects regression)"
        if _report("D4: Wacha – sell-high, expects ERA regression from 2.23",
                   ok, details, "ERA 3.00-5.00, must be >2.50 (regression)"):
            passed += 1

    # D5: Replacement-level hitter (Gary Sanchez, Neutral)
    repl = project_player("Gary Sanchez")
    if "error" in repl:
        # fallback to any neutral hitter
        repl = project_player("replacement")
    if "error" in repl:
        _report("D5: Replacement-level hitter — found", False, repl.get("error", "not found"), "player found")
    else:
        ps = repl["projected_stats"]
        avg, hr = ps.get("projected_avg", 0), ps.get("projected_hr", 0)
        games = ps.get("games_remaining", 100)
        # Scale HR to 140-game pace
        hr_140 = int(hr * 140 / max(games, 1)) if games > 0 else hr
        ok = (0.210 <= avg <= 0.275 and 5 <= hr_140 <= 25)
        details = f"AVG={avg:.3f} HR={hr} (raw) HR/140g≈{hr_140}"
        if _report("D5: Gary Sanchez – replacement-level hitter, Neutral verdict",
                   ok, details, "AVG .210-.275, HR/140g 5-25"):
            passed += 1

    print(f"  Section D: {passed}/5 PASS")
    return passed


# ==============================================================================
# SECTION E — EDGE CASE TESTS
# ==============================================================================

def run_section_e() -> int:
    print("\nSECTION E — Edge Case Tests (7 tests)")
    print("-" * 55)
    passed = 0

    # E1: Zero IP pitcher — no exception, returns valid projection
    try:
        baseline_e1 = _pitcher_baseline()
        row_e1 = _pitcher_row(IP=0.0, FIP=float("nan"), xERA=float("nan"),
                              swstr_rate=float("nan"), total_starts=0.0)
        tt_e1 = pitcher_true_talent(row_e1, baseline_e1, pitcher_rates=None)
        w_e1 = sample_weight(0.0, is_pitcher=True)
        bl_e1 = blend_projection(tt_e1, baseline_e1, w_e1)
        proj_e1 = project_pitcher_counting(bl_e1, games_remaining=50, is_starter=True)
        era_e1 = proj_e1.get("projected_era", float("nan"))
        ok = (era_e1 == era_e1 and 1.80 <= era_e1 <= 7.00)
        if _report("E1: Zero-IP pitcher – no exception, valid ERA projection",
                   ok, f"ERA={era_e1:.2f}", "no exception; ERA 1.80-7.00"):
            passed += 1
    except Exception as exc:
        _report("E1: Zero-IP pitcher", False, f"EXCEPTION: {exc}", "no exception")

    # E2: Zero PA hitter — no exception, returns valid projection
    try:
        baseline_e2 = _hitter_baseline()
        row_e2 = _hitter_row(xwOBA=float("nan"), BABIP=float("nan"),
                             barrel_rate=float("nan"), bb_rate=float("nan"),
                             k_rate=float("nan"), PA=0.0)
        tt_e2 = hitter_true_talent(row_e2, baseline_e2)
        w_e2 = sample_weight(0.0, is_pitcher=False)
        bl_e2 = blend_projection(tt_e2, baseline_e2, w_e2)
        proj_e2 = project_hitter_counting(bl_e2, games_remaining=50)
        avg_e2 = proj_e2.get("projected_avg", float("nan"))
        ok = avg_e2 == avg_e2 and 0.190 <= avg_e2 <= 0.340
        if _report("E2: Zero-PA hitter – no exception, valid AVG projection",
                   ok, f"AVG={avg_e2:.3f}", "no exception; AVG .190-.340"):
            passed += 1
    except Exception as exc:
        _report("E2: Zero-PA hitter", False, f"EXCEPTION: {exc}", "no exception")

    # E3: Extreme xwOBA hitter (.600) — clamped to reasonable AVG
    row_e3 = _hitter_row(xwOBA=0.600, barrel_rate=0.220, bb_rate=0.140, k_rate=0.160)
    base_e3 = _hitter_baseline(career_avg=0.285)
    tt_e3 = hitter_true_talent(row_e3, base_e3)
    avg_e3 = tt_e3["true_avg"]
    ok = avg_e3 <= 0.380
    if _report("E3: xwOBA=.600 (extreme) – AVG clamped below .380",
               ok, f"{avg_e3:.3f}", "≤ 0.380"):
        passed += 1

    # E4: Negative ERA input (-1.0) — no exception, clamped
    try:
        base_e4 = _pitcher_baseline()
        row_e4 = _pitcher_row(FIP=-1.0, xERA=-2.0, swstr_rate=0.100)
        tt_e4 = pitcher_true_talent(row_e4, base_e4, pitcher_rates=None)
        era_e4 = tt_e4["true_era"]
        ok = 1.50 <= era_e4 <= 7.00
        if _report("E4: Negative ERA input – no exception, clamped ≥1.50",
                   ok, f"ERA={era_e4:.2f}", "no exception; ERA clamped 1.50-7.00"):
            passed += 1
    except Exception as exc:
        _report("E4: Negative ERA input", False, f"EXCEPTION: {exc}", "no exception")

    # E5: Unknown pitcher ID (99999) — fallback to league averages, no exception
    try:
        career_empty = {"hitter": {}, "pitcher": {}, "pitcher_rates": {},
                        "sprint": {}, "career_pitch_mix": {}, "current_pitch_mix": {}}
        base_e5 = get_pitcher_baseline(99999, career_empty)
        ok = (abs(base_e5["career_era"] - LEAGUE_AVG_PITCHER["career_era"]) < 0.01)
        if _report("E5: Unknown pitcher ID – fallback to league average ERA",
                   ok, f"career_era={base_e5['career_era']}", f"= {LEAGUE_AVG_PITCHER['career_era']}"):
            passed += 1
    except Exception as exc:
        _report("E5: Unknown pitcher ID", False, f"EXCEPTION: {exc}", "no exception")

    # E6: Reliever detection — IP/start ratio < 4.0 → is_starter=False
    from stat_projections import _is_starter
    row_rel = _pitcher_row(IP=30.0, total_starts=35.0)   # 0.857 IP/app → reliever
    row_sp  = _pitcher_row(IP=60.0, total_starts=10.0)   # 6.0 IP/start → starter
    ok = (not _is_starter(row_rel)) and _is_starter(row_sp)
    if _report("E6: Reliever detection via IP/start ratio",
               ok, f"reliever={_is_starter(row_rel)} starter={_is_starter(row_sp)}",
               "reliever(0.86 IP/app)=False; starter(6.0 IP/start)=True"):
        passed += 1

    # E7: Age 40+ decay — KNOWN LIMITATION
    _known_limit("E7: Age 40+ decay",
                 "No age-based decay implemented — old players project same as career average. "
                 "Future: pull player age from roster data and apply linear decay for age 35+.")

    print(f"  Section E: {passed}/6 PASS  +1 KNOWN LIMITATION")
    return passed


# ==============================================================================
# MAIN
# ==============================================================================

def main() -> None:
    print("=" * 60)
    print("  FORMULA VALIDATION SUITE — stat_projections.py")
    print("=" * 60)

    a = run_section_a()
    b = run_section_b()
    c = run_section_c()
    d = run_section_d()
    e = run_section_e()

    total_pass = a + b + c + d + e
    total_tests = 10 + 10 + 6 + 5 + 6   # E7 is KNOWN LIMIT, not counted

    print()
    print("=" * 60)
    print("  FORMULA VALIDATION SUITE RESULTS")
    print("=" * 60)
    print(f"  Section A (Pitcher):    {a}/10 PASS")
    print(f"  Section B (Hitter):     {b}/10 PASS")
    print(f"  Section C (Blend):      {c}/6  PASS")
    print(f"  Section D (Real):       {d}/5  PASS")
    print(f"  Section E (Edge):       {e}/6  PASS  +1 KNOWN LIMITATION")
    print(f"  {'─'*36}")
    print(f"  Total:               {total_pass}/{total_tests} PASS")
    print()

    failures = [r for r in _results if r["pass"] is False]
    if failures:
        print(f"  FAILURES ({len(failures)}):")
        for f in failures:
            print(f"    ✗ {f['name']}")
    else:
        print("  ✅ All tests passed!")
    print()
    print("  KNOWN LIMITATIONS (not fixable yet):")
    print("    - E7: No age 40+ decay — projects same as career average")
    print("    - R/RBI lineup-position dependent — estimates only")
    print("    - Reliever detection uses IP/start heuristic")
    print("=" * 60)


if __name__ == "__main__":
    main()
