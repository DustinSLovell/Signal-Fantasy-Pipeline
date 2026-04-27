"""
era_simulation.py — Diagnostic: impact of ERA → ERA_all_sc switch.
Simulates luck scores and verdicts for all 389 pitchers under both ERA variants.
Diagnosis only — does not modify any production file.
"""
import math
import pandas as pd
from datetime import date

df = pd.read_csv("pitcher_luck_scores.csv")
print(f"Loaded {len(df)} pitchers")

SEASON_START = date(2026, 3, 27)
TODAY = date(2026, 4, 29)
season_day = (TODAY - SEASON_START).days  # 33 → May phase


def confidence_scale(ip):
    if season_day <= 30:
        return 0.0 if ip < 15 else max(0.25, (ip - 15) / 40)
    elif season_day <= 60:
        return 0.0 if ip < 18 else max(0.15, (ip - 18) / 40)
    else:
        return max(0.0, (ip - 20) / 40)


def hrfb_component(hr_fb, hh):
    if pd.isna(hr_fb) or hr_fb <= 0.14:
        return 0.0
    base = (hr_fb - 0.12) * 2.0
    if not pd.isna(hh):
        if hh > 0.38:
            base *= 0.65
        elif hh < 0.28:
            base *= 1.25
    return base


def is_buy_qualified(fip, xera, swstr, career_ip):
    if pd.isna(fip) or pd.isna(swstr) or pd.isna(career_ip):
        return False
    if fip > 4.50:
        return False
    if career_ip < 100:
        return False
    fip_carveout = fip <= 3.50
    if not fip_carveout and (pd.isna(xera) or xera > 4.75):
        return False
    # SwStr% gate (simplified — gb_pct carve-out not re-checked here)
    if swstr < 0.08:
        return False
    return True


def parse_stuff_mult(sig, ls_sign):
    if not isinstance(sig, str):
        return 1.0
    if ("dampens sell x0.85" in sig or "elite contact, dampens sell" in sig) and ls_sign < 0:
        return 0.85
    if "Poor stuff dampens buy x0.85" in sig and ls_sign > 0:
        return 0.85
    if "Elite stuff+buy x1.15" in sig and ls_sign > 0:
        return 1.15
    if "Poor stuff+sell x1.15" in sig and ls_sign < 0:
        return 1.15
    if "poor outcomes, amplifies sell x1.15" in sig and ls_sign < 0:
        return 1.15
    return 1.0


def combine_rtm(ls, rtm):
    combined = ls * 0.75 + (rtm * 0.15) * 0.25
    if ls < 0 and rtm > 0:
        combined *= 1.15
    return round(combined, 4)


def assign_verdict(ls):
    if ls > 0.15:
        return "Buy low"
    if ls > 0.07:
        return "Slight buy"
    if ls < -0.15:
        return "Sell high"
    if ls < -0.07:
        return "Slight sell"
    return "Neutral"


MIN_BUY_IP = 20.0


def simulate(row, use_era_all):
    era = float(row["ERA_all_sc"]) if use_era_all else float(row["ERA"])
    fip = row.get("FIP", float("nan"))
    xera = row.get("xERA", float("nan"))
    ip = row.get("IP_sc", row.get("IP", 0.0))
    career_ip = row.get("career_ip", 0.0)
    swstr = row.get("swstr_rate", float("nan"))

    def f(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return float("nan")

    fip = f(fip); xera = f(xera); ip = f(ip); career_ip = f(career_ip); swstr = f(swstr)

    era_minus_fip  = (era - fip)  if not math.isnan(fip)  else 0.0
    era_minus_xera = (era - xera) if not math.isnan(xera) else 0.0

    babip    = f(row.get("BABIP_allowed"))
    babip_b  = f(row.get("park_adj_babip_expected"))
    lob      = f(row.get("lob_pct"))
    hh       = f(row.get("hard_hit_rate_allowed"))
    barrel   = f(row.get("barrel_rate_allowed"))
    hr_fb    = f(row.get("hr_fb_rate"))
    career_hh  = f(row.get("career_hh_allowed"))
    career_bar = f(row.get("career_barrel_allowed"))
    xwoba_gap  = f(row.get("xwoba_gap"))

    c_babip = ((babip - babip_b) if not math.isnan(babip) and not math.isnan(babip_b)
               else (babip - 0.300) if not math.isnan(babip) else 0.0) * 5.0
    c_lob   = ((lob - 0.724) * -3.0) if not math.isnan(lob) else 0.0
    c_era_f = era_minus_fip * 0.15
    c_era_x = era_minus_xera * 0.10
    c_hrfb  = hrfb_component(hr_fb, hh)
    hh_base = career_hh if not math.isnan(career_hh) else 0.360
    c_hh    = ((hh - hh_base) * -1.5) if not math.isnan(hh) else 0.0
    br_base = career_bar if not math.isnan(career_bar) else 0.080
    c_barrel = ((barrel - br_base) * -1.5) if not math.isnan(barrel) else 0.0
    c_swstr  = ((swstr - 0.110) * 2.0) if not math.isnan(swstr) else 0.0

    sell_score = c_babip + c_lob + c_era_f + c_era_x + c_hrfb + c_hh + c_barrel + c_swstr

    xw  = (xwoba_gap * 0.25) if not math.isnan(xwoba_gap) else 0.0
    bbp = (babip - babip_b) * 0.15 if not math.isnan(babip) and not math.isnan(babip_b) else 0.0
    buy_score = era_minus_fip * 0.60 + xw + bbp

    ss, bs = sell_score, buy_score
    if ss < 0 and bs > 0:
        raw_ls = era_minus_fip * 0.15
    elif ss < 0:
        raw_ls = ss
    elif bs > 0:
        raw_ls = bs
    else:
        raw_ls = 0.0

    conf = confidence_scale(ip)
    ls = round(raw_ls * conf, 4)

    rtm = f(row.get("rtm_signal", 0.0))
    if math.isnan(rtm):
        rtm = 0.0
    ls = combine_rtm(ls, rtm)

    sp_sig = row.get("stuff_plus_signal", None)
    ls = round(ls * parse_stuff_mult(sp_sig, ls), 4)

    pm = f(row.get("pitch_mix_signal", 0.0))
    if math.isnan(pm):
        pm = 0.0
    if ls > 0 and pm != 0:
        ls = round(ls * (1.0 + pm), 4)

    # Verdict assignment with ERA floors
    if bs > 0 and ss >= 0 and ls > 0:
        dominant = bs >= 1.50
        qual = is_buy_qualified(fip, xera, swstr, career_ip)
        if ip < MIN_BUY_IP and not dominant:
            verdict = "Neutral"
        elif ip < MIN_BUY_IP and not math.isnan(fip) and fip < 1.50:
            verdict = "Neutral"
        elif era < 3.50:
            verdict = "Neutral"
        elif not dominant and not math.isnan(xera) and not math.isnan(fip) and abs(fip - xera) > 1.50 and xera > 4.50:
            verdict = "Neutral"
        elif bs >= 0.50:
            v = "Neutral" if era < 3.75 else "Buy low"
            verdict = "Neutral" if (not qual and v == "Buy low") else v
        elif bs >= 0.30:
            v = "Neutral" if era < 4.00 else "Slight buy"
            verdict = "Neutral" if (not qual and v == "Slight buy") else v
        else:
            verdict = assign_verdict(ls)
            if verdict in ("Buy low", "Slight buy") and not qual:
                verdict = "Neutral"
    else:
        verdict = assign_verdict(ls)

    return ls, verdict, sell_score, buy_score


results = []
for _, row in df.iterrows():
    ls_a, v_a, ss_a, bs_a = simulate(row, use_era_all=False)
    ls_b, v_b, ss_b, bs_b = simulate(row, use_era_all=True)
    results.append({
        "name":      row["name"],
        "ERA":       row["ERA"],
        "ERA_all":   row["ERA_all_sc"],
        "era_delta": round((row["ERA_all_sc"] or 0) - (row["ERA"] or 0), 2),
        "FIP":       row["FIP"],
        "IP":        row["IP"],
        "actual":    row["verdict"],
        "simA":      v_a,
        "simB":      v_b,
        "ls_simA":   ls_a,
        "ls_simB":   ls_b,
    })

sim = pd.DataFrame(results)
match_count = (sim["actual"] == sim["simA"]).sum()
print(f"SimA vs actual: {match_count}/{len(sim)} match ({match_count/len(sim)*100:.1f}%)\n")

# For the comparison we use the full set — where simA disagrees with actual,
# both A and B disagree symmetrically (same gate issues), so the A→B delta is still valid.
changed = sim[sim["simA"] != sim["simB"]].copy()
print(f"VERDICT CHANGES under ERA_all_sc: {len(changed)} of {len(sim)}")
print()

# Categorise changes
def change_type(a, b):
    order = {"Buy low": 4, "Slight buy": 3, "Neutral": 2, "Slight sell": 1, "Sell high": 0}
    oa, ob = order.get(a, 2), order.get(b, 2)
    if ob > oa: return "STRONGER_BUY"
    if ob < oa: return "WEAKER_BUY / STRONGER_SELL"
    return "SAME_TIER"

changed["change_type"] = changed.apply(lambda r: change_type(r["simA"], r["simB"]), axis=1)

print("Changes in SELL direction (ERA_all_sc makes sell stronger):")
sell_str = changed[changed["change_type"] == "WEAKER_BUY / STRONGER_SELL"].sort_values("era_delta", ascending=False)
for _, r in sell_str.iterrows():
    print(f"  {r['name']:<28s}  ERA {r['ERA']:.2f}→{r['ERA_all']:.2f} (Δ{r['era_delta']:+.2f})  "
          f"{r['simA']:12s} → {r['simB']:12s}  ls {r['ls_simA']:+.3f}→{r['ls_simB']:+.3f}")

print()
print("Changes in BUY direction (ERA_all_sc makes buy stronger or unlocks signal):")
buy_str = changed[changed["change_type"] == "STRONGER_BUY"].sort_values("era_delta", ascending=False)
for _, r in buy_str.iterrows():
    print(f"  {r['name']:<28s}  ERA {r['ERA']:.2f}→{r['ERA_all']:.2f} (Δ{r['era_delta']:+.2f})  "
          f"{r['simA']:12s} → {r['simB']:12s}  ls {r['ls_simA']:+.3f}→{r['ls_simB']:+.3f}")

print()
print("── SIGNAL DISTRIBUTION ──────────────────────────────────────────────")
verts = ["Buy low", "Slight buy", "Neutral", "Slight sell", "Sell high"]
print(f"  {'Verdict':15s}  {'Actual':>6s}  {'SimA':>6s}  {'SimB':>6s}  {'A→B':>6s}")
for v in verts:
    a = (sim["actual"] == v).sum()
    sa = (sim["simA"] == v).sum()
    sb = (sim["simB"] == v).sum()
    print(f"  {v:15s}  {a:6d}  {sa:6d}  {sb:6d}  {sb-sa:+6d}")

sk = sim[sim["name"].str.contains("Skenes", case=False)]
if not sk.empty:
    r = sk.iloc[0]
    print()
    print("── SKENES ──────────────────────────────────────────────────────────")
    print(f"  ERA {r['ERA']:.2f}  ERA_all_sc {r['ERA_all']:.2f}  delta {r['era_delta']:+.2f}  FIP {r['FIP']:.2f}")
    print(f"  Actual verdict:  {r['actual']}")
    print(f"  SimA (filtered): {r['simA']}  ls={r['ls_simA']:+.4f}")
    print(f"  SimB (ERA_all):  {r['simB']}  ls={r['ls_simB']:+.4f}")
