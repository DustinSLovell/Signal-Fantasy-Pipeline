# -*- coding: utf-8 -*-
"""
DIAGNOSTIC ONLY — does not modify the model.
Compares model xwOBA (luck_scores.csv) vs true Savant xwOBA (est_woba leaderboard),
recomputes xwOBA_gap and a first-order corrected luck_score / verdict, and reports flips.

First-order correction assumption:
  xwOBA_gap enters the base luck_score with weight 1.000 (score_luck.py docstring).
  gap = xwOBA - wOBA; wOBA is unchanged, so  delta_gap = true_xwOBA - model_xwOBA.
  corrected_luck = luck_score + delta_gap   (net multiplicative modifiers treated as ~1.0
  for the marginal change). Cases within 0.02 of a threshold are flagged borderline.
"""
import csv, io, json, urllib.request, statistics
from pathlib import Path

# thresholds (config.py)
BUY_LOW    =  0.175
SLIGHT_BUY =  0.175   # eliminated (== BUY_LOW)
SELL_HIGH  = -0.150
SLIGHT_SELL= -0.085

LUCK_CSV   = "luck_scores.csv"
AUDIT_CSV  = "data/backtest_audit_hitters.csv"
CACHE      = Path("data/savant_true_xwoba_2026.json")
OUT_CSV    = Path("data/xwoba_verdict_flip_diagnostic.csv")

def assign_verdict(s):
    if s > BUY_LOW:     return "Buy low"
    if s > SLIGHT_BUY:  return "Slight buy"
    if s < SELL_HIGH:   return "Sell high"
    if s < SLIGHT_SELL: return "Slight sell"
    return "Neutral"

def f(v):
    try: return float(v)
    except: return None

# ---- 1. true xwOBA from Savant bulk leaderboard (cached) ----
def load_true_xwoba():
    if CACHE.exists():
        return {int(k): v for k, v in json.loads(CACHE.read_text()).items()}
    url = ("https://baseballsavant.mlb.com/leaderboard/expected_statistics"
           "?type=batter&year=2026&position=&team=&filterType=bip&min=1&csv=true")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    raw = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace").lstrip("﻿")
    rd = csv.DictReader(io.StringIO(raw))
    out = {}
    for r in rd:
        pid = f(r.get("player_id"))
        ew  = f(r.get("est_woba"))
        pa  = f(r.get("pa"))
        if pid is not None and ew is not None:
            out[int(pid)] = {"true_xwoba": ew, "savant_pa": pa}
    CACHE.write_text(json.dumps({str(k): v for k, v in out.items()}, indent=2))
    print(f"Fetched true xwOBA for {len(out)} batters -> {CACHE}")
    return out

# ---- 2. model rows ----
def load_model():
    rows = []
    with open(LUCK_CSV, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            rows.append({
                "name": r["name"],
                "mlbam_id": int(r["batter"]) if r.get("batter") else None,
                "PA": f(r.get("PA")),
                "k_rate": f(r.get("k_rate")),
                "wOBA": f(r.get("wOBA")),
                "model_xwoba": f(r.get("xwOBA")),
                "model_gap": f(r.get("xwOBA_gap")),
                "luck_score": f(r.get("luck_score")),
                "verdict": r.get("verdict", "").strip(),
            })
    return rows

# ---- 3. 2025 backtest Buy Low (correct) ----
def load_bt_buylow():
    bl_all, bl_correct = set(), set()
    with open(AUDIT_CSV, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("year") != "2025":
                continue
            if r.get("signal") == "Buy Low":
                mid = int(r["mlbam_id"])
                bl_all.add(mid)
                if r.get("correct", "").lower() == "true":
                    bl_correct.add(mid)
    return bl_all, bl_correct

def main():
    truth = load_true_xwoba()
    model = load_model()
    bl_all, bl_correct = load_bt_buylow()

    matched, unmatched = [], 0
    for m in model:
        t = truth.get(m["mlbam_id"]) if m["mlbam_id"] is not None else None
        if t is None or m["model_xwoba"] is None or m["luck_score"] is None or m["wOBA"] is None:
            unmatched += 1
            continue
        true_xwoba = t["true_xwoba"]
        inflation  = m["model_xwoba"] - true_xwoba          # model - true (>=0 expected)
        delta_gap  = true_xwoba - m["model_xwoba"]           # applied to luck_score
        corrected  = round(m["luck_score"] + delta_gap, 4)
        cv = assign_verdict(corrected)
        near = min(abs(corrected - BUY_LOW), abs(corrected - SELL_HIGH),
                   abs(corrected - SLIGHT_SELL))
        m.update({"true_xwoba": true_xwoba, "inflation": inflation,
                  "delta_gap": delta_gap, "corrected_luck": corrected,
                  "corrected_verdict": cv, "borderline": near < 0.02})
        matched.append(m)

    # ---- flips ----
    NEUT = {"Neutral", "Slight buy", "Slight sell"}
    bl_flips = [m for m in matched if m["verdict"] == "Buy low"  and m["corrected_verdict"] != "Buy low"]
    sh_flips = [m for m in matched if m["verdict"] == "Sell high" and m["corrected_verdict"] != "Sell high"]
    new_sells= [m for m in matched if m["verdict"] != "Sell high" and m["corrected_verdict"] == "Sell high"]
    all_flips= [m for m in matched if m["verdict"] != m["corrected_verdict"]]

    # ---- scratch CSV (signaled cohort = non-Neutral) ----
    cohort = [m for m in matched if m["verdict"] not in ("Neutral",)]
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["name","mlbam_id","current_xwOBA_model","true_xwOBA_savant",
                    "gap_difference","current_luck","corrected_luck",
                    "current_verdict","corrected_verdict","flipped","borderline"])
        for m in sorted(cohort, key=lambda x: x["corrected_luck"], reverse=True):
            w.writerow([m["name"], m["mlbam_id"], f"{m['model_xwoba']:.3f}",
                        f"{m['true_xwoba']:.3f}", f"{m['delta_gap']:+.3f}",
                        f"{m['luck_score']:.4f}", f"{m['corrected_luck']:.4f}",
                        m["verdict"], m["corrected_verdict"],
                        "YES" if m["verdict"] != m["corrected_verdict"] else "",
                        "borderline" if m["borderline"] else ""])

    # ---- print ----
    print("="*78)
    print("xwOBA VERDICT-FLIP DIAGNOSTIC (model xwOBA vs true Savant xwOBA)")
    print("="*78)
    print(f"Hitters in luck_scores.csv : {len(model)}")
    print(f"Matched to Savant true xwOBA: {len(matched)}   (unmatched/insufficient: {unmatched})")
    cur = {}
    for m in matched: cur[m["verdict"]] = cur.get(m["verdict"],0)+1
    print(f"Current verdict mix (matched): {cur}")
    print()

    print("-"*78)
    print(f"BUY LOW -> non-Buy flips: {len(bl_flips)}")
    print("-"*78)
    print(f"{'PLAYER':<22}{'modxw':>7}{'truexw':>8}{'Δgap':>7}{'cur LS':>8}{'cor LS':>8}  {'-> verdict':<12}{'note'}")
    for m in sorted(bl_flips, key=lambda x:x["corrected_luck"], reverse=True):
        print(f"{m['name']:<22}{m['model_xwoba']:>7.3f}{m['true_xwoba']:>8.3f}"
              f"{m['delta_gap']:>+7.3f}{m['luck_score']:>8.3f}{m['corrected_luck']:>8.3f}  "
              f"{m['corrected_verdict']:<12}{'borderline' if m['borderline'] else ''}")
    print()
    print("-"*78)
    print(f"SELL HIGH -> non-Sell flips: {len(sh_flips)}")
    print("-"*78)
    for m in sorted(sh_flips, key=lambda x:x["corrected_luck"]):
        print(f"{m['name']:<22}{m['model_xwoba']:>7.3f}{m['true_xwoba']:>8.3f}"
              f"{m['delta_gap']:>+7.3f}{m['luck_score']:>8.3f}{m['corrected_luck']:>8.3f}  "
              f"{m['corrected_verdict']:<12}{'borderline' if m['borderline'] else ''}")
    if not sh_flips:
        print("  (none — correction lowers scores, so Sell High strengthens rather than flips out)")
    print()
    print(f"NEW Sell High (was non-Sell -> Sell high): {len(new_sells)}")
    for m in sorted(new_sells, key=lambda x:x["corrected_luck"]):
        print(f"  {m['name']:<22} {m['verdict']} -> Sell high  (cor LS {m['corrected_luck']:+.3f})"
              f"{'  borderline' if m['borderline'] else ''}")

    # ---- summary ----
    print()
    print("="*78)
    print("SUMMARY COUNTS")
    print("="*78)
    print(f"  Total verdict flips (any direction): {len(all_flips)}")
    print(f"  Buy Low  -> Neutral/Slight flips:    {len(bl_flips)}")
    print(f"  Sell High-> Neutral/Slight flips:    {len(sh_flips)}")
    print(f"  (Bonus) Neutral/Slight -> Sell High: {len(new_sells)}")
    unchanged = len(matched) - len(all_flips)
    print(f"  Verdict unchanged:                   {unchanged}")
    bb = [m for m in all_flips if m["borderline"]]
    print(f"  ...of flips, borderline (|Δ to threshold|<0.02): {len(bb)}")

    # ===== FOLLOW-UP Q1: BL flips that were TRUE Buy Low in 2025 backtest =====
    print()
    print("="*78)
    print("Q1 — Buy Low flips cross-referenced to 2025 backtest")
    print("="*78)
    in_bt   = [m for m in bl_flips if m["mlbam_id"] in bl_all]
    in_bt_c = [m for m in bl_flips if m["mlbam_id"] in bl_correct]
    print(f"  Buy Low flips total:                          {len(bl_flips)}")
    print(f"  ...present in 2025 backtest as Buy Low:        {len(in_bt)}")
    print(f"  ...were CORRECT Buy Low in 2025 backtest:      {len(in_bt_c)}")
    print(f"  ...NOT in 2025 Buy Low set (no 2025 evidence): {len(bl_flips)-len(in_bt)}")
    for m in in_bt:
        tag = "CORRECT-2025" if m["mlbam_id"] in bl_correct else "in-2025-only"
        print(f"     {m['name']:<22} {tag}")

    # ===== Q2: distribution of inflation across all matched hitters =====
    infl = [m["inflation"] for m in matched]
    infl_s = sorted(infl)
    def pct(p):
        i=int(round((p/100)*(len(infl_s)-1))); return infl_s[i]
    print()
    print("="*78)
    print("Q2 — Distribution of inflation (model_xwOBA - true_xwOBA), n=%d" % len(infl))
    print("="*78)
    print(f"  mean={statistics.mean(infl):+.4f}  median={statistics.median(infl):+.4f}  "
          f"stdev={statistics.pstdev(infl):.4f}")
    print(f"  min={min(infl):+.4f}  p10={pct(10):+.4f}  p25={pct(25):+.4f}  "
          f"p75={pct(75):+.4f}  p90={pct(90):+.4f}  max={max(infl):+.4f}")
    # histogram
    bins = [(-1,0),(0,0.01),(0.01,0.02),(0.02,0.03),(0.03,0.04),(0.04,0.05),
            (0.05,0.06),(0.06,0.08),(0.08,1)]
    print("  histogram (pts):")
    for lo,hi in bins:
        c=sum(1 for x in infl if lo<=x<hi)
        lbl=f"{lo*1000:+.0f}..{hi*1000:+.0f}" if hi<1 else f">{lo*1000:+.0f}"
        if lo==-1: lbl=f"<0 (model<true)"
        print(f"    {lbl:>16}: {'#'*c} {c}")

    # ===== Q3: correlation inflation vs K% =====
    pairs = [(m["inflation"], m["k_rate"]) for m in matched if m["k_rate"] is not None]
    xs=[a for a,_ in pairs]; ys=[b for _,b in pairs]
    n=len(pairs)
    mx,my=statistics.mean(xs),statistics.mean(ys)
    cov=sum((a-mx)*(b-my) for a,b in pairs)/n
    r=cov/(statistics.pstdev(xs)*statistics.pstdev(ys))
    print()
    print("="*78)
    print(f"Q3 - Correlation: inflation vs K%  (n={n})")
    print("="*78)
    print(f"  Pearson r = {r:+.3f}")
    # k% buckets
    print("  mean inflation by K% bucket:")
    buckets=[(0,0.15),(0.15,0.20),(0.20,0.25),(0.25,0.30),(0.30,1.0)]
    for lo,hi in buckets:
        grp=[a for a,b in pairs if lo<=b<hi]
        if grp:
            print(f"    K% {lo*100:>4.0f}-{hi*100:<4.0f}: n={len(grp):<3} "
                  f"mean inflation={statistics.mean(grp)*1000:+.1f} pts")

    print(f"\nScratch CSV: {OUT_CSV} ({len(cohort)} cohort rows)")

if __name__ == "__main__":
    main()
