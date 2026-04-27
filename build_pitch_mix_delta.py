"""
build_pitch_mix_delta.py — Phase 2 pitch mix evolution delta

Computes per-pitcher pitch mix signals (2026 vs career baseline) from JSON files
and Phase 2 baseline files built by build_pitcher_phase2_baselines.py.

Outputs: data/pitcher_pitch_mix_delta.json

PHASE 1 signals (career_pitch_mix.json):
  - Abandonment (bearish): best career pitch (by career_swstr) losing >10pp usage
    AND career_swstr > 15%. Applies regardless of buy/sell direction.
  - SwStr effectiveness (bullish): best pitch SwStr improved >2pp AND curr >= 12%.

PHASE 2 signals (NEW — from phase 2 baselines):
  - Velo drop (bearish): best career pitch losing >1.5 mph.
    Velocity decline on the best whiff-getter = stuff is fading.
  - Velo gain (bullish): best career pitch gaining >1.0 mph.
    Velocity recovery = potential breakout candidate.
  - RV degradation (bearish): best pitch run_value_per_100 worse by >1.5 vs career avg.
    Run value directly measures whether the pitch is getting hitters out less.
  - RV improvement (bullish): best pitch rv100 better by >1.5 vs career avg.
  - New pitch detection (now enabled): pitch in curr not in career velo baseline,
    usage >5%, curr_swstr >12%, AND velo is distinct (>3 mph from nearest career pitch).
    Statcast relabeling artifacts are filtered by the velo continuity test.

Multiplier summary (applied in score_pitcher_luck.py):
  bearish flags each apply ×0.90 on buy / ×1.10 on sell
  bullish flags each apply ×1.10 on buy
  flags stack multiplicatively
"""

import json
import math
import os

BASE_DIR     = os.path.dirname(os.path.abspath(__file__)) or "."
CAREER_PATH  = os.path.join(BASE_DIR, "data", "pitcher_career_pitch_mix.json")
CURRENT_PATH = os.path.join(BASE_DIR, "data", "pitcher_current_pitch_mix.json")
CAREER_VELO_PATH = os.path.join(BASE_DIR, "data", "pitcher_career_velo_per_pitch.json")
CAREER_RV_PATH   = os.path.join(BASE_DIR, "data", "pitcher_career_arsenal_rv.json")
CURR_RV_PATH     = os.path.join(BASE_DIR, "data", "pitcher_arsenal_rv_2026.json")
OUTPUT_PATH  = os.path.join(BASE_DIR, "data", "pitcher_pitch_mix_delta.json")

# Phase 1 thresholds
ABANDON_USAGE_THRESH  = 0.10   # >10pp drop in best pitch usage
ABANDON_SWSTR_FLOOR   = 0.15   # career swstr must exceed this to flag
EFFECT_SWSTR_DELTA    = 0.02   # 2pp SwStr improvement on best pitch
EFFECT_SWSTR_FLOOR    = 0.12   # curr swstr must clear this threshold

# Phase 2 thresholds
VELO_DROP_THRESH      = 1.5    # mph drop on best pitch (bearish)
VELO_GAIN_THRESH      = 1.0    # mph gain on best pitch (bullish)
RV_DEGRADE_THRESH     = 3.0    # rv/100 worsening — >1 stdev from early-April noise floor (~3.15 stdev)
RV_IMPROVE_THRESH     = 3.0    # rv/100 improvement — same threshold both directions
NEW_PITCH_USAGE_MIN   = 0.05   # new pitch must have >5% usage
NEW_PITCH_SWSTR_MIN   = 0.12   # new pitch must show >12% whiff
NEW_PITCH_VELO_MARGIN = 3.0    # mph — new pitch must differ from nearest career pitch by >3 mph


def _load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def build_pitch_mix_delta():
    career      = _load_json(CAREER_PATH)
    curr        = _load_json(CURRENT_PATH)
    career_velo = _load_json(CAREER_VELO_PATH)   # {pid: {pt: avg_speed}}
    career_rv   = _load_json(CAREER_RV_PATH)      # {pid: {pt: {rv100_avg, ...}}}
    curr_rv     = _load_json(CURR_RV_PATH)         # {pid: {pt: {rv100, ...}}}

    phase2_velo = bool(career_velo)
    phase2_rv   = bool(career_rv) and bool(curr_rv)
    print(f"  Phase 2 velo baseline loaded: {phase2_velo} ({len(career_velo)} pitchers)")
    print(f"  Phase 2 RV baseline loaded:   {phase2_rv} ({len(career_rv)} career, {len(curr_rv)} current)")

    career_by_id = {str(k): v for k, v in career.items()}
    curr_by_id   = {str(k): v for k, v in curr.items()}
    overlap_ids  = set(career_by_id.keys()) & set(curr_by_id.keys())

    results = {}
    counts = {
        "abandonment": 0, "effectiveness": 0,
        "velo_drop": 0, "velo_gain": 0,
        "rv_degrade": 0, "rv_improve": 0,
        "new_pitch": 0,
    }

    for pid in overlap_ids:
        c_rec = career_by_id[pid]
        n_rec = curr_by_id[pid]

        c_usage = c_rec.get("career_usage", {})
        n_usage = n_rec.get("curr_usage", {})
        c_swstr = c_rec.get("career_swstr", {})
        n_swstr = n_rec.get("curr_swstr", {})
        n_velo  = n_rec.get("curr_velo", {})

        # Phase 1: usage + swstr deltas
        shared_types = set(c_usage.keys()) & set(n_usage.keys())
        usage_delta  = {pt: round(n_usage[pt] - c_usage[pt], 4) for pt in shared_types}
        shared_swstr = set(c_swstr.keys()) & set(n_swstr.keys())
        swstr_delta  = {pt: round(n_swstr[pt] - c_swstr[pt], 4) for pt in shared_swstr}

        # Best career pitch by career SwStr%
        best_pt = None
        best_career_swstr = None
        if c_swstr:
            best_pt = max(c_swstr, key=lambda pt: c_swstr[pt])
            best_career_swstr = round(c_swstr[best_pt], 4)

        best_usage_delta = usage_delta.get(best_pt) if best_pt else None
        best_swstr_delta = swstr_delta.get(best_pt) if best_pt else None

        # Overall SwStr delta (diagnostic only — excluded from signal at early April sample sizes)
        c_swstr_overall = c_rec.get("career_swstr_overall")
        n_swstr_overall = n_rec.get("curr_swstr_overall")
        swstr_overall_delta = None
        if c_swstr_overall is not None and n_swstr_overall is not None:
            swstr_overall_delta = round(n_swstr_overall - c_swstr_overall, 4)

        # ── Phase 1: Abandonment signal ─────────────────────────────────────
        abandonment_flag = False
        abandonment_note = None
        if (best_pt and best_career_swstr is not None
                and best_career_swstr > ABANDON_SWSTR_FLOOR
                and best_usage_delta is not None
                and best_usage_delta < -ABANDON_USAGE_THRESH):
            abandonment_flag = True
            abandonment_note = (
                f"{best_pt} usage {best_usage_delta:+.0%} "
                f"(career swstr {best_career_swstr:.1%})"
            )
            counts["abandonment"] += 1

        # ── Phase 1: SwStr effectiveness signal ──────────────────────────────
        effectiveness_flag = False
        effectiveness_note = None
        if (best_pt and best_swstr_delta is not None
                and best_swstr_delta > EFFECT_SWSTR_DELTA
                and n_swstr.get(best_pt, 0.0) >= EFFECT_SWSTR_FLOOR):
            effectiveness_flag = True
            effectiveness_note = (
                f"{best_pt} swstr {best_swstr_delta:+.1%} vs career "
                f"(curr {n_swstr.get(best_pt,0):.1%})"
            )
            counts["effectiveness"] += 1

        # ── Phase 2A: Per-pitch velocity delta ──────────────────────────────
        velo_drop_flag = False
        velo_gain_flag = False
        velo_drop_note = None
        velo_gain_note = None
        best_velo_delta = None
        c_velo_map = career_velo.get(pid, {})  # {pt: avg_speed}

        if best_pt and c_velo_map and best_pt in n_velo and best_pt in c_velo_map:
            best_velo_delta = round(n_velo[best_pt] - c_velo_map[best_pt], 2)
            if best_velo_delta < -VELO_DROP_THRESH:
                velo_drop_flag = True
                velo_drop_note = (
                    f"{best_pt} velo {best_velo_delta:+.1f} mph "
                    f"({c_velo_map[best_pt]:.1f} career → {n_velo[best_pt]:.1f} curr)"
                )
                counts["velo_drop"] += 1
            elif best_velo_delta > VELO_GAIN_THRESH:
                velo_gain_flag = True
                velo_gain_note = (
                    f"{best_pt} velo {best_velo_delta:+.1f} mph "
                    f"({c_velo_map[best_pt]:.1f} career → {n_velo[best_pt]:.1f} curr)"
                )
                counts["velo_gain"] += 1

        # Per-pitch velo delta dict (all shared types with career velo)
        velo_delta = {}
        for pt in n_velo:
            if pt in c_velo_map:
                velo_delta[pt] = round(n_velo[pt] - c_velo_map[pt], 2)

        # ── Phase 2B: Run value delta ────────────────────────────────────────
        rv_degrade_flag = False
        rv_improve_flag = False
        rv_degrade_note = None
        rv_improve_note = None
        best_rv_delta = None
        c_rv_map = career_rv.get(pid, {})   # {pt: {rv100_avg, ...}}
        n_rv_map = curr_rv.get(pid, {})      # {pt: {rv100, ...}}

        if best_pt and c_rv_map.get(best_pt) and n_rv_map.get(best_pt):
            career_rv100 = c_rv_map[best_pt].get("rv100_avg")
            curr_rv100   = n_rv_map[best_pt].get("rv100")
            if career_rv100 is not None and curr_rv100 is not None:
                best_rv_delta = round(curr_rv100 - career_rv100, 3)
                # Positive delta = pitch getting worse (costs more runs)
                if best_rv_delta > RV_DEGRADE_THRESH:
                    rv_degrade_flag = True
                    rv_degrade_note = (
                        f"{best_pt} rv/100 {best_rv_delta:+.1f} "
                        f"({career_rv100:.1f} career → {curr_rv100:.1f} curr)"
                    )
                    counts["rv_degrade"] += 1
                elif best_rv_delta < -RV_IMPROVE_THRESH:
                    rv_improve_flag = True
                    rv_improve_note = (
                        f"{best_pt} rv/100 {best_rv_delta:+.1f} "
                        f"({career_rv100:.1f} career → {curr_rv100:.1f} curr)"
                    )
                    counts["rv_improve"] += 1

        # ── Phase 2C: New pitch detection (velo fingerprint) ─────────────────
        new_pitch_flag  = False
        new_pitch_note  = None
        new_pitch_types = []

        career_velo_values = list(c_velo_map.values())  # all career pitch velocities

        for pt, usage in n_usage.items():
            # Skip if this pitch type existed in career data
            if pt in c_usage:
                continue
            if usage < NEW_PITCH_USAGE_MIN:
                continue
            curr_pt_swstr = n_swstr.get(pt, 0.0)
            if curr_pt_swstr < NEW_PITCH_SWSTR_MIN:
                continue
            # Velo fingerprint check: is this a truly new pitch or a relabeling?
            pt_velo = n_velo.get(pt)
            if pt_velo is None or not career_velo_values:
                # No velo data — can't verify, skip for safety
                continue
            min_velo_gap = min(abs(pt_velo - cv) for cv in career_velo_values)
            if min_velo_gap <= NEW_PITCH_VELO_MARGIN:
                # Velocity overlaps an existing career pitch → relabeling artifact
                continue
            # Passes all gates: truly new pitch with distinct velo + effectiveness
            new_pitch_types.append(pt)

        if new_pitch_types:
            new_pitch_flag = True
            new_pitch_note = (
                f"New pitch: {', '.join(new_pitch_types)} "
                f"(distinct velo, usage {max(n_usage.get(pt,0) for pt in new_pitch_types):.0%}, "
                f"whiff {max(n_swstr.get(pt,0) for pt in new_pitch_types):.1%})"
            )
            counts["new_pitch"] += 1

        # ── Composite pitch mix signal score ──────────────────────────────────
        # Phase 1 components
        bearish_flags = [abandonment_flag, velo_drop_flag, rv_degrade_flag]
        bullish_flags = [effectiveness_flag, velo_gain_flag, rv_improve_flag, new_pitch_flag]

        pitch_mix_signal = 0.0
        notes = []
        for flag, weight, label in [
            (abandonment_flag,  -0.10, "abandonment"),
            (effectiveness_flag, +0.05, "effectiveness"),
            (velo_drop_flag,    -0.08, "velo_drop"),
            (velo_gain_flag,    +0.05, "velo_gain"),
            (rv_degrade_flag,   -0.08, "rv_degrade"),
            (rv_improve_flag,   +0.05, "rv_improve"),
            (new_pitch_flag,    +0.07, "new_pitch"),
        ]:
            if flag:
                pitch_mix_signal += weight
                notes.append(f"{label} {weight:+.2f}")

        pitch_mix_signal = round(pitch_mix_signal, 4)
        pitch_mix_note = " | ".join(notes) if notes else None

        results[pid] = {
            # Identity
            "name":              c_rec.get("name"),
            "total_pitches_2026": n_rec.get("total_pitches_2026"),
            "career_pitches":    c_rec.get("career_pitches"),
            # Phase 1 deltas
            "usage_delta":             usage_delta,
            "swstr_delta":             swstr_delta,
            "best_pitch_career":       best_pt,
            "best_pitch_career_swstr": best_career_swstr,
            "best_pitch_usage_delta":  round(best_usage_delta, 4) if best_usage_delta is not None else None,
            "best_pitch_swstr_delta":  round(best_swstr_delta, 4) if best_swstr_delta is not None else None,
            "swstr_overall_delta":     swstr_overall_delta,
            # Phase 2 deltas
            "velo_delta":              velo_delta,
            "best_velo_delta":         best_velo_delta,
            "best_rv_delta":           best_rv_delta,
            # Flags
            "abandonment_flag":   abandonment_flag,
            "abandonment_note":   abandonment_note,
            "effectiveness_flag": effectiveness_flag,
            "effectiveness_note": effectiveness_note,
            "velo_drop_flag":     velo_drop_flag,
            "velo_drop_note":     velo_drop_note,
            "velo_gain_flag":     velo_gain_flag,
            "velo_gain_note":     velo_gain_note,
            "rv_degrade_flag":    rv_degrade_flag,
            "rv_degrade_note":    rv_degrade_note,
            "rv_improve_flag":    rv_improve_flag,
            "rv_improve_note":    rv_improve_note,
            "new_pitch_flag":     new_pitch_flag,
            "new_pitch_note":     new_pitch_note,
            "new_pitch_types":    new_pitch_types,
            # Composite
            "pitch_mix_signal":   pitch_mix_signal,
            "pitch_mix_note":     pitch_mix_note,
        }

    with open(OUTPUT_PATH, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nbuild_pitch_mix_delta (Phase 2): {len(results)} pitchers → {OUTPUT_PATH}")
    print(f"  Phase 1  — Abandonment: {counts['abandonment']}, "
          f"SwStr effectiveness: {counts['effectiveness']}")
    print(f"  Phase 2A — Velo drop: {counts['velo_drop']}, "
          f"Velo gain: {counts['velo_gain']}")
    print(f"  Phase 2B — RV degrade: {counts['rv_degrade']}, "
          f"RV improve: {counts['rv_improve']}")
    print(f"  Phase 2C — New pitch (velo-verified): {counts['new_pitch']}")
    total_bearish = counts["abandonment"] + counts["velo_drop"] + counts["rv_degrade"]
    total_bullish = counts["effectiveness"] + counts["velo_gain"] + counts["rv_improve"] + counts["new_pitch"]
    print(f"\n  TOTAL bearish flags: {total_bearish}")
    print(f"  TOTAL bullish flags: {total_bullish}")

    neg = sum(1 for v in results.values() if v["pitch_mix_signal"] < 0)
    pos = sum(1 for v in results.values() if v["pitch_mix_signal"] > 0)
    zer = sum(1 for v in results.values() if v["pitch_mix_signal"] == 0)
    print(f"\n  Signal distribution: {neg} bearish | {pos} bullish | {zer} neutral")
    return results


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)) or ".")
    build_pitch_mix_delta()
