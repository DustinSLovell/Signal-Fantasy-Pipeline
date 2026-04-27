"""
compute_stuff_quality.py
=========================
Computes Stuff Quality Score (Layer 7) by comparing current 2026
metrics against career baselines. Adds display columns to
pitcher_luck_scores.csv — does NOT modify scoring logic.

Components:
  SwStr% trend  (weight 3.0, threshold ±1.5pp)
  FB velo trend (weight 2.0, threshold ±0.8 mph, scaled /3.0)
  Spin trend    (weight 1.0, threshold ±100 RPM, scaled /300)

Outputs columns added to pitcher_luck_scores.csv:
  career_swstr_pct, career_fb_velo, career_spin_rate
  curr_swstr_pct, curr_fb_velo, curr_spin_rate
  swstr_gap, velo_gap, spin_gap
  stuff_score, stuff_signal
"""

import json
import os
import numpy as np
import pandas as pd

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
DATA_DIR    = os.path.join(BASE_DIR, "data")
CAREER_PATH = os.path.join(DATA_DIR, "pitcher_career_stuff.json")
CURRENT_PATH= os.path.join(DATA_DIR, "pitcher_stuff_current_2026.csv")
SCORES_PATH = os.path.join(BASE_DIR, "pitcher_luck_scores.csv")

SWSTR_THRESHOLD = 0.015   # 1.5pp minimum gap
VELO_THRESHOLD  = 0.8     # 0.8 mph minimum
SPIN_THRESHOLD  = 100.0   # 100 RPM minimum
SCORE_CAP       = 1.5

SWSTR_WEIGHT    = 3.0
VELO_WEIGHT     = 2.0
SPIN_WEIGHT     = 1.0


def _classify(score: float | None) -> str:
    if score is None or np.isnan(score):
        return "Insufficient data"
    if score >  0.15:  return "Improving stuff"
    if score >  0.08:  return "Slight stuff improvement"
    if score < -0.15:  return "Declining stuff"
    if score < -0.08:  return "Slight stuff decline"
    return "Neutral"


def compute_stuff_scores(career: dict, current_df: pd.DataFrame,
                         sc_path: str) -> pd.DataFrame:
    """
    Returns a DataFrame indexed by pitcher MLBAM id with all stuff columns.
    Uses pitchers_statcast.csv to map MLBAM ids to career JSON keys.
    """
    # Build id -> career data mapping (career keys are str of MLBAM id)
    career_by_id = {int(k): v for k, v in career.items()}

    # current_df is already keyed by pitcher_id (MLBAM int)
    curr = current_df.set_index("pitcher_id")

    rows = []
    # Use pitchers in current_df as the universe — they're already the pipeline pitchers
    for pid in curr.index:
        c = curr.loc[pid]
        car = career_by_id.get(int(pid), {})

        # Career values
        car_swstr = car.get("career_swstr_pct")
        car_velo  = car.get("career_fb_velo")
        car_spin  = car.get("career_spin_rate")

        # Current values
        cur_swstr = c.get("curr_swstr_pct")
        cur_velo  = c.get("curr_fb_velo")
        cur_spin  = c.get("curr_spin_rate")

        def _gap(cur, car):
            if cur is None or car is None:
                return None
            try:
                cur_f, car_f = float(cur), float(car)
                if np.isnan(cur_f) or np.isnan(car_f):
                    return None
                return round(cur_f - car_f, 4)
            except (TypeError, ValueError):
                return None

        swstr_gap = _gap(cur_swstr, car_swstr)
        velo_gap  = _gap(cur_velo,  car_velo)
        spin_gap  = _gap(cur_spin,  car_spin)

        # Component scores with thresholds
        swstr_comp = 0.0
        if swstr_gap is not None and abs(swstr_gap) > SWSTR_THRESHOLD:
            swstr_comp = swstr_gap * SWSTR_WEIGHT

        velo_comp = 0.0
        if velo_gap is not None and abs(velo_gap) > VELO_THRESHOLD:
            velo_comp = (velo_gap / 3.0) * VELO_WEIGHT

        spin_comp = 0.0
        if spin_gap is not None and abs(spin_gap) > SPIN_THRESHOLD:
            spin_comp = (spin_gap / 300.0) * SPIN_WEIGHT

        # Require at least one non-zero component with real data
        has_data = any(x is not None for x in [swstr_gap, velo_gap, spin_gap])
        if not has_data:
            stuff_score = None
        else:
            raw = swstr_comp + velo_comp + spin_comp
            stuff_score = round(float(np.clip(raw, -SCORE_CAP, SCORE_CAP)), 4)

        rows.append({
            "pitcher_id":       int(pid),
            "career_swstr_pct": round(float(car_swstr), 4) if car_swstr is not None else None,
            "career_fb_velo":   round(float(car_velo),  2) if car_velo  is not None else None,
            "career_spin_rate": round(float(car_spin),  1) if car_spin  is not None else None,
            "curr_swstr_pct":   round(float(cur_swstr), 4) if pd.notna(cur_swstr) and cur_swstr is not None else None,
            "curr_fb_velo":     round(float(cur_velo),  2) if pd.notna(cur_velo)  and cur_velo  is not None else None,
            "curr_spin_rate":   round(float(cur_spin),  1) if pd.notna(cur_spin)  and cur_spin  is not None else None,
            "swstr_gap":        swstr_gap,
            "velo_gap":         velo_gap,
            "spin_gap":         spin_gap,
            "stuff_score":      stuff_score,
            "stuff_signal":     _classify(stuff_score),
        })

    return pd.DataFrame(rows)


def main():
    # Load inputs
    if not os.path.exists(CAREER_PATH):
        print(f"MISSING: {CAREER_PATH} — run build_pitcher_stuff_baselines.py first")
        return
    with open(CAREER_PATH) as f:
        career = json.load(f)
    print(f"Career baselines loaded: {len(career):,} pitchers")

    if not os.path.exists(CURRENT_PATH):
        print(f"MISSING: {CURRENT_PATH} — run fetch_pitcher_stuff_current.py first")
        return
    current_df = pd.read_csv(CURRENT_PATH)
    print(f"Current 2026 metrics loaded: {len(current_df):,} pitchers")

    if not os.path.exists(SCORES_PATH):
        print(f"MISSING: {SCORES_PATH}")
        return
    scores = pd.read_csv(SCORES_PATH)
    print(f"pitcher_luck_scores.csv loaded: {len(scores):,} pitchers")

    sc_path = os.path.join(BASE_DIR, "pitchers_statcast.csv")

    # Compute stuff scores
    stuff_df = compute_stuff_scores(career, current_df, sc_path)
    print(f"\nStuff scores computed: {len(stuff_df):,} pitcher rows")

    # pitcher_luck_scores.csv already has 'pitcher' column = MLBAM id
    scores_with_id = scores.copy()
    scores_with_id["pitcher_id"] = scores_with_id["pitcher"]

    # Drop old stuff columns if they exist
    stuff_cols = ["career_swstr_pct","career_fb_velo","career_spin_rate",
                  "curr_swstr_pct","curr_fb_velo","curr_spin_rate",
                  "swstr_gap","velo_gap","spin_gap","stuff_score","stuff_signal"]
    scores_with_id.drop(columns=[c for c in stuff_cols if c in scores_with_id.columns],
                        inplace=True, errors="ignore")

    # Merge stuff scores
    merged = scores_with_id.merge(
        stuff_df.drop(columns=["career_swstr_pct","career_fb_velo","career_spin_rate",
                                "curr_swstr_pct","curr_fb_velo","curr_spin_rate",
                                "swstr_gap","velo_gap","spin_gap",
                                "stuff_score","stuff_signal"], errors="ignore"),
        on="pitcher_id", how="left"
    )
    # Re-merge the stuff columns properly
    merged = scores_with_id.merge(stuff_df, on="pitcher_id", how="left")

    # Fill missing stuff signal
    merged["stuff_signal"] = merged["stuff_signal"].fillna("Insufficient data")

    # Coverage stats
    n_total = len(merged)
    n_swstr = merged["swstr_gap"].notna().sum()
    n_velo  = merged["velo_gap"].notna().sum()
    n_spin  = merged["spin_gap"].notna().sum()
    n_score = merged["stuff_score"].notna().sum()

    print(f"\n  Stuff quality coverage ({n_total} pipeline pitchers):")
    print(f"    Have SwStr% gap:    {n_swstr:>4} ({n_swstr/n_total*100:.1f}%)")
    print(f"    Have velo gap:      {n_velo:>4} ({n_velo/n_total*100:.1f}%)")
    print(f"    Have spin gap:      {n_spin:>4} ({n_spin/n_total*100:.1f}%)")
    print(f"    Have stuff_score:   {n_score:>4} ({n_score/n_total*100:.1f}%)")

    # Signal distribution
    sig_counts = merged["stuff_signal"].value_counts()
    print(f"\n  Stuff signal distribution:")
    for sig, cnt in sig_counts.items():
        print(f"    {sig:<30} {cnt:>4}")

    # Remove the pitcher_id column added for joining if not originally in scores
    if "pitcher_id" not in scores.columns:
        merged.drop(columns=["pitcher_id"], inplace=True, errors="ignore")

    merged.to_csv(SCORES_PATH, index=False)
    print(f"\nSaved: {SCORES_PATH} (now {len(merged.columns)} columns)")

    # Also update snapshot
    snap_path = os.path.join(DATA_DIR, "snapshots", "pitcher_luck_scores_april_2026.csv")
    if os.path.exists(os.path.dirname(snap_path)):
        merged.to_csv(snap_path, index=False)
        print(f"Snapshot updated: {snap_path}")


if __name__ == "__main__":
    main()
