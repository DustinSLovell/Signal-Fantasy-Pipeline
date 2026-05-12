"""
build_il_stubs.py
Injects IL pitcher/hitter stubs into player_values.json so they appear in the trade tool.

Players on IL all season with zero 2026 Statcast data cannot enter the normal pipeline.
This module adds them with Steamer ROS projection estimates so they are searchable.

Reads:  data/il_pitcher_stubs.csv
Writes: data/player_values.json (appends IL entries; removes stale ones first)

Run BEFORE compute_roto_surplus.py so IL players are included in roto rank pool.
Called automatically from score_value.py --write.
"""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path

_DIR = Path(__file__).parent
STUBS_PATH = _DIR / "data" / "il_pitcher_stubs.csv"
PV_PATH    = _DIR / "data" / "player_values.json"

try:
    from config import (
        CBS_P_COEF_W, CBS_P_COEF_ERA, CBS_P_COEF_WHIP,
        CBS_P_COEF_K, CBS_P_COEF_SV, CBS_P_INTERCEPT,
    )
except ImportError:
    CBS_P_COEF_W      = 10.5398
    CBS_P_COEF_ERA    = -2.5531
    CBS_P_COEF_WHIP   = -90.7701
    CBS_P_COEF_K      =  1.3236
    CBS_P_COEF_SV     =  6.3282
    CBS_P_INTERCEPT   = 122.7395

# League 1 replacement levels (12-team CBS standard, from replacement_level.py)
SP_REPL_L1 = 221.5
RP_REPL_L1 = 157.0


def _cbs_fpts(w: float, era: float, whip: float, k: float, sv: float) -> float:
    return (CBS_P_COEF_W * w + CBS_P_COEF_ERA * era + CBS_P_COEF_WHIP * whip
            + CBS_P_COEF_K * k + CBS_P_COEF_SV * sv + CBS_P_INTERCEPT)


def main() -> None:
    if not STUBS_PATH.exists():
        print("[il_stubs] data/il_pitcher_stubs.csv not found — skipped")
        return

    with open(PV_PATH, encoding="utf-8") as f:
        data = json.load(f)

    # Remove stale IL-only entries before re-adding (idempotent re-runs)
    data["players"] = [p for p in data["players"] if not p.get("il_only")]

    stubs_added = 0
    with open(STUBS_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                mlbam_id = int(row["mlbam_id"])
                ip       = float(row.get("proj_ip") or 0)
                w        = float(row.get("proj_w")   or 0)
                era      = float(row.get("proj_era")  or 4.50)
                whip     = float(row.get("proj_whip") or 1.30)
                k        = float(row.get("proj_k")    or 0)
                sv_h     = float(row.get("proj_sv_h") or 0)
                fp_rank_raw = row.get("fp_ros_rank")
                fp_rank  = int(float(fp_rank_raw)) if fp_rank_raw else None

                pos     = "SP" if ip >= 60 else "RP"
                repl    = SP_REPL_L1 if pos == "SP" else RP_REPL_L1
                fpts_l1 = _cbs_fpts(w, era, whip, k, sv_h)
                surplus = round(fpts_l1 - repl, 1)

                entry: dict = {
                    "id":            mlbam_id,
                    "name":          row["name"].strip(),
                    "type":          "pitcher",
                    "pos":           pos,
                    "team":          row.get("team", "").strip(),
                    "league1_value": round(fpts_l1, 1),
                    "league2_value": round(fpts_l1, 1),
                    "surplus_l1":    surplus,
                    "fp_rank":       fp_rank,
                    "fp_rank_tier":  None,
                    "verdict":       "Neutral",
                    "il_only":       True,
                    "il_note":       row.get("note", "IL — Steamer ROS projection only").strip(),
                    "roto_surplus_l1": None,   # filled by compute_roto_surplus
                    "proj": {
                        "ERA":    round(era,  2),
                        "WHIP":   round(whip, 2),
                        "K":      round(k,    0),
                        "W":      round(w,    1),
                        "SVH_L1": round(sv_h, 1),
                        "SVH_L2": round(sv_h, 1),
                        "IP":     round(ip,   0),
                    },
                }
                data["players"].append(entry)
                stubs_added += 1
            except Exception as e:
                print(f"  [il_stubs] Error processing {row.get('name', '?')}: {e}")

    with open(PV_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"[il_stubs] {stubs_added} IL player stubs added to player_values.json")

    # Quick sanity check
    for p in data["players"]:
        if p.get("il_only"):
            print(f"  {p['name']:25s}  pos={p['pos']}  CBS_FPTS={p['league1_value']:+.0f}  "
                  f"surplus={p['surplus_l1']:+.0f}  fp_rank={p.get('fp_rank')}")


if __name__ == "__main__":
    main()
