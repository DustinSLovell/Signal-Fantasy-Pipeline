"""
generate_narratives.py
Calls the Anthropic API to generate simple + advanced trade narratives for the
top buy-low and sell-high players identified by the luck scoring pipeline.

Reads:  luck_scores.csv, pitcher_luck_scores.csv, data/player_values.json
Writes: data/narratives.json  (only after terminal review and user approval)

Players selected:
  Hitters — top 5 buy low (PA>=40, maxTV>=20), top 5 sell high (PA>=40)
  Pitchers — top 3 buy low (buy_qualified=True, IP>=15), top 3 sell high (IP>=15)
"""

import csv
import json
import os
import sys
import io
import traceback
from datetime import date

# Load .env if present (python-dotenv); falls back to existing env var if not found
try:
    from dotenv import load_dotenv
    _env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    load_dotenv(_env_path)
except ImportError:
    pass  # dotenv not installed — rely on environment variable directly

import anthropic

# ── Force UTF-8 output on Windows ────────────────────────────────────────────
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE_DIR          = os.path.dirname(os.path.abspath(__file__))
LUCK_CSV          = os.path.join(BASE_DIR, "luck_scores.csv")
PITCHER_CSV       = os.path.join(BASE_DIR, "pitcher_luck_scores.csv")
PLAYER_VALUES     = os.path.join(BASE_DIR, "data", "player_values.json")
OUTPUT_PATH       = os.path.join(BASE_DIR, "data", "narratives.json")

MODEL             = "claude-sonnet-4-6"
MAX_TOKENS        = 1000
MIN_HITTER_PA     = 40
MIN_HITTER_TV     = 20   # at least one league must have value >= this
MIN_PITCHER_IP    = 15


# ── Tier framing instructions for the prompt ──────────────────────────────────
TIER_FRAMING = {
    # buy signals
    "buy_low": (
        "This player is unlucky — their results badly lag their underlying contact/stuff quality. "
        "Regression upward is coming. Frame as a genuine opportunity before the market adjusts."
    ),
    "slight_buy": (
        "This player shows mild positive regression potential. Results are slightly behind talent. "
        "Frame as a quiet buy, not an urgent one."
    ),
    # sell signals
    "Sell and Move On": (
        "This player's results are NOT supported by their underlying talent. They are getting lucky. "
        "Frame as urgent — extract value now before the correction hits."
    ),
    "Sell High on Perception": (
        "This is an elite player running hot, exceeding even their own high standard. "
        "Frame as a peak-value window — the player IS good, just temporarily running above true talent. "
        "Sell into strength, not weakness."
    ),
    "Veteran Regression": (
        "Proven veteran on a lucky stretch. A modest correction is coming but the talent is real. "
        "Frame as a hold-unless-you-get-full-value situation — don't panic sell, but extract max value if offered."
    ),
    "Slight Regression Expected": (
        "Mild luck working in the player's favor. Minor correction likely, nothing dramatic. "
        "Frame as low-urgency — monitor rather than act aggressively."
    ),
}


def flt(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def fmt_pct(v):
    """Format a 0-1 float as a percentage string like 30.2%."""
    try:
        return f"{float(v)*100:.1f}%"
    except (TypeError, ValueError):
        return "n/a"


def fmt_rate(v, decimals=3):
    try:
        return f".{round(float(v)*1000):03d}"
    except (TypeError, ValueError):
        return "n/a"


# ── Player selection helpers ──────────────────────────────────────────────────

def load_hitters(luck_csv: str, player_values: str):
    with open(luck_csv, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    with open(player_values) as f:
        pv = json.load(f)

    tv_by_id  = {str(p["id"]): p for p in pv["players"]}
    pos_by_id = {str(p["id"]): p.get("pos", "?") for p in pv["players"]}

    buy_rows  = []
    sell_rows = []

    for r in sorted(rows, key=lambda x: flt(x.get("luck_score"), 0), reverse=True):
        verdict = r.get("verdict", "")
        pa      = flt(r.get("PA", 0))
        if pa < MIN_HITTER_PA:
            continue
        bid   = r.get("batter", "")
        pdata = tv_by_id.get(str(bid), {})
        max_tv = max(pdata.get("league1_value") or 0, pdata.get("league2_value") or 0)
        pos    = pos_by_id.get(str(bid), "?")
        r["_pos"]    = pos
        r["_max_tv"] = max_tv

        if verdict in ("Buy low", "Slight buy") and max_tv >= MIN_HITTER_TV:
            buy_rows.append(r)
        elif verdict in ("Sell high", "Slight sell"):
            sell_rows.append(r)

    # sell_rows already in ascending luck order from the sorted() above — reverse needed
    sell_rows.sort(key=lambda x: flt(x.get("luck_score"), 0))

    return buy_rows[:5], sell_rows[:5]


def load_pitchers(pitcher_csv: str):
    with open(pitcher_csv, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    buy_rows  = []
    sell_rows = []

    for r in sorted(rows, key=lambda x: flt(x.get("luck_score"), 0), reverse=True):
        ip      = flt(r.get("IP", 0))
        verdict = r.get("verdict", "")
        if ip < MIN_PITCHER_IP:
            continue
        if verdict in ("Buy low", "Slight buy") and r.get("buy_qualified", "True") == "True":
            buy_rows.append(r)
        elif verdict in ("Sell high", "Slight sell"):
            sell_rows.append(r)

    sell_rows.sort(key=lambda x: flt(x.get("luck_score"), 0))

    return buy_rows[:3], sell_rows[:3]


# ── Prompt builders ───────────────────────────────────────────────────────────

def build_hitter_prompt(r: dict, signal: str) -> str:
    name     = r.get("name", "Unknown")
    pos      = r.get("_pos", "?")
    age      = r.get("age", "?")
    verdict  = r.get("verdict", "")
    tier     = r.get("tier_sell", "") or verdict
    luck     = flt(r.get("luck_score", 0))
    pa       = int(flt(r.get("PA", 0)))
    babip    = fmt_rate(r.get("BABIP"))
    xgap     = flt(r.get("xwOBA_gap", 0))
    hhr      = fmt_pct(r.get("hard_hit_rate"))
    hrfb     = fmt_pct(r.get("hr_fb_rate"))
    woba     = fmt_rate(r.get("wOBA"))
    xwoba    = fmt_rate(r.get("xwOBA"))
    z_con    = fmt_pct(r.get("z_contact_rate"))
    career   = int(flt(r.get("career_pa", 0)))

    if signal == "buy":
        metrics_block = (
            f"  BABIP: {babip} (league avg ~.295 — this is extremely low)\n"
            f"  xwOBA gap: +{xgap:.3f} (actual wOBA is {xgap:.3f} BELOW contact quality; positive = unlucky)\n"
            f"  Hard hit rate: {hhr}\n"
            f"  Zone contact rate: {z_con}\n"
            f"  Current PA: {pa}  |  Career PA: {career:,} (track record context)\n"
            f"  Verdict: {verdict}  |  Luck score: +{luck:.3f}"
        )
        framing = TIER_FRAMING["buy_low"]
    else:
        metrics_block = (
            f"  BABIP: {babip} (league avg ~.295 — this is extremely high/unsustainable)\n"
            f"  xwOBA gap: {xgap:+.3f} (negative = actual wOBA EXCEEDS contact quality = lucky)\n"
            f"  HR/FB rate: {hrfb} (league avg ~14% — elevated = lucky, will regress)\n"
            f"  wOBA: {woba}  |  xwOBA: {xwoba} (gap shows luck component)\n"
            f"  Hard hit rate: {hhr}\n"
            f"  Current PA: {pa}\n"
            f"  Verdict: {verdict}  |  Tier: {tier}  |  Luck score: {luck:.3f}"
        )
        framing = TIER_FRAMING.get(tier, TIER_FRAMING["Sell and Move On"])

    return f"""You are a sharp fantasy baseball analyst. Generate two trade narratives for this player.

PLAYER: {name}
POSITION: {pos}
AGE: {age}
SIGNAL: {verdict}{f' — {tier}' if tier and tier != verdict else ''}

KEY METRICS:
{metrics_block}

FRAMING INSTRUCTION: {framing}

Generate EXACTLY this format — two labeled blocks, no extra text before or after:

SIMPLE:
[2 sentences max. Zero jargon, zero stats. Plain English action + reason. Tone: confident fantasy advisor who is certain about the call. Use the player's first name or a natural nickname.]

ADVANCED:
[3-4 sentences. Name and cite the specific metrics above. Explain WHY the regression mechanism works — what is causing the luck and why it will normalize. Tone: serious analyst with conviction. Reference career context where relevant.]"""


def build_pitcher_prompt(r: dict, signal: str) -> str:
    name     = r.get("name", "Unknown")
    age      = r.get("age", "?")
    ip       = flt(r.get("IP", 0))
    verdict  = r.get("verdict", "")
    tier     = r.get("tier_sell", "") or verdict
    luck     = flt(r.get("luck_score", 0))
    era      = flt(r.get("ERA", 0))
    fip      = flt(r.get("FIP", 0))
    xera     = flt(r.get("xERA", 0))
    efip     = flt(r.get("ERA_minus_FIP", 0))
    babip_a  = fmt_rate(r.get("BABIP_allowed"))
    lob      = fmt_pct(r.get("lob_pct"))
    swstr    = fmt_pct(r.get("swstr_rate"))
    xgap     = flt(r.get("xwoba_gap", 0))
    hrfb     = fmt_pct(r.get("hr_fb_rate"))
    gbp      = fmt_pct(r.get("gb_pct"))
    career_ip = int(flt(r.get("career_ip", 0)))

    if signal == "buy":
        metrics_block = (
            f"  ERA: {era:.2f}  |  FIP: {fip:.2f}  |  xERA: {xera:.2f}\n"
            f"  ERA minus FIP gap: +{efip:.2f} (ERA is {efip:.2f} runs ABOVE FIP — the gap is luck-driven)\n"
            f"  SwStr%: {swstr}  |  GB%: {gbp}\n"
            f"  BABIP allowed: {babip_a} (league avg ~.295)\n"
            f"  LOB% (strand rate): {lob}\n"
            f"  xwOBA gap: {xgap:+.3f} (positive = pitcher is unlucky relative to contact quality allowed)\n"
            f"  IP: {ip:.0f}  |  Career IP: {career_ip:,}\n"
            f"  Verdict: {verdict}  |  Luck score: +{luck:.3f}"
        )
        framing = TIER_FRAMING["buy_low"]
    else:
        metrics_block = (
            f"  ERA: {era:.2f}  |  FIP: {fip:.2f}  |  xERA: {xera:.2f}\n"
            f"  ERA minus FIP gap: {efip:.2f} (ERA is {abs(efip):.2f} runs BELOW FIP — the gap is luck-driven)\n"
            f"  BABIP allowed: {babip_a}  |  LOB%: {lob}\n"
            f"  HR/FB rate: {hrfb}  |  SwStr%: {swstr}\n"
            f"  xwOBA gap: {xgap:+.3f} (negative = pitcher is lucky; allowing worse contact than results show)\n"
            f"  IP: {ip:.0f}\n"
            f"  Verdict: {verdict}  |  Tier: {tier}  |  Luck score: {luck:.3f}"
        )
        framing = TIER_FRAMING.get(tier, TIER_FRAMING["Sell and Move On"])

    return f"""You are a sharp fantasy baseball analyst. Generate two trade narratives for this pitcher.

PLAYER: {name}
AGE: {age}
SIGNAL: {verdict}{f' — {tier}' if tier and tier != verdict else ''}

KEY METRICS:
{metrics_block}

FRAMING INSTRUCTION: {framing}

Generate EXACTLY this format — two labeled blocks, no extra text before or after:

SIMPLE:
[2 sentences max. Zero jargon, zero stats. Plain English action + reason. Tone: confident fantasy advisor who is certain about the call. Use the pitcher's first name or a natural nickname.]

ADVANCED:
[3-4 sentences. Name and cite the specific metrics above. Explain WHY the ERA gap will close — what is driving the luck and why it won't persist. Tone: serious analyst with conviction.]"""


# ── API call ──────────────────────────────────────────────────────────────────

def call_api(client: anthropic.Anthropic, prompt: str, player_name: str) -> dict:
    """Returns {'simple': str, 'advanced': str} or {'error': str}."""
    try:
        msg = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()

        # Parse SIMPLE / ADVANCED blocks
        simple_text  = ""
        advanced_text = ""
        current = None
        lines = raw.splitlines()
        for line in lines:
            stripped = line.strip()
            if stripped.upper().startswith("SIMPLE:"):
                current = "simple"
                after = stripped[7:].strip()
                if after:
                    simple_text = after
            elif stripped.upper().startswith("ADVANCED:"):
                current = "advanced"
                after = stripped[9:].strip()
                if after:
                    advanced_text = after
            elif current == "simple" and stripped:
                simple_text = (simple_text + " " + stripped).strip()
            elif current == "advanced" and stripped:
                advanced_text = (advanced_text + " " + stripped).strip()

        if not simple_text or not advanced_text:
            return {"error": f"Could not parse SIMPLE/ADVANCED blocks from response:\n{raw}"}

        return {"simple": simple_text, "advanced": advanced_text, "raw": raw}

    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}\n{traceback.format_exc()}"}


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    client = anthropic.Anthropic()

    print("Loading player data …")
    buy_hitters,  sell_hitters  = load_hitters(LUCK_CSV, PLAYER_VALUES)
    buy_pitchers, sell_pitchers = load_pitchers(PITCHER_CSV)

    results = {
        "generated_date": date.today().isoformat(),
        "hitters":  {"buy_low": [], "sell_high": []},
        "pitchers": {"buy_low": [], "sell_high": []},
    }

    divider = "─" * 72

    # ── Hitter buy low ────────────────────────────────────────────────────────
    print(f"\n{'='*72}")
    print("  HITTER BUY LOW — generating narratives")
    print(f"{'='*72}")

    for r in buy_hitters:
        name   = r.get("name", "?")
        pos    = r.get("_pos", "?")
        age    = r.get("age", "?")
        luck   = flt(r.get("luck_score", 0))
        verdict = r.get("verdict", "")
        babip  = fmt_rate(r.get("BABIP"))
        xgap   = flt(r.get("xwOBA_gap", 0))
        hhr    = fmt_pct(r.get("hard_hit_rate"))

        print(f"\n{divider}")
        print(f"  {name} ({pos}, age {age}) | luck={luck:+.3f} | BABIP={babip} | xgap={xgap:+.3f} | hhr={hhr}")
        print(f"  Calling API …")

        prompt = build_hitter_prompt(r, "buy")
        resp   = call_api(client, prompt, name)

        if "error" in resp:
            print(f"  ❌ ERROR: {resp['error']}")
            entry = {"name": name, "pos": pos, "age": age, "verdict": verdict,
                     "tier": "", "luck_score": luck,
                     "key_metrics": {"BABIP": babip, "xwOBA_gap": xgap, "hard_hit_rate": hhr},
                     "simple_narrative": None, "advanced_narrative": None, "error": resp["error"]}
        else:
            print(f"\n  SIMPLE:   {resp['simple']}")
            print(f"\n  ADVANCED: {resp['advanced']}")
            entry = {"name": name, "pos": pos, "age": age, "verdict": verdict,
                     "tier": "", "luck_score": luck,
                     "key_metrics": {"BABIP": babip, "xwOBA_gap": xgap, "hard_hit_rate": hhr,
                                     "PA": int(flt(r.get("PA", 0)))},
                     "simple_narrative": resp["simple"],
                     "advanced_narrative": resp["advanced"]}

        results["hitters"]["buy_low"].append(entry)

    # ── Hitter sell high ──────────────────────────────────────────────────────
    print(f"\n\n{'='*72}")
    print("  HITTER SELL HIGH — generating narratives")
    print(f"{'='*72}")

    for r in sell_hitters:
        name    = r.get("name", "?")
        pos     = r.get("_pos", "?")
        age     = r.get("age", "?")
        luck    = flt(r.get("luck_score", 0))
        verdict = r.get("verdict", "")
        tier    = r.get("tier_sell", "")
        age_flag = r.get("age_flag", "")
        babip   = fmt_rate(r.get("BABIP"))
        xgap    = flt(r.get("xwOBA_gap", 0))
        hrfb    = fmt_pct(r.get("hr_fb_rate"))

        print(f"\n{divider}")
        print(f"  {name} ({pos}, age {age}) | luck={luck:+.3f} | tier={tier}{' | '+age_flag if age_flag else ''}")
        print(f"  BABIP={babip} | xgap={xgap:+.3f} | HR/FB={hrfb}")
        print(f"  Calling API …")

        prompt = build_hitter_prompt(r, "sell")
        resp   = call_api(client, prompt, name)

        if "error" in resp:
            print(f"  ❌ ERROR: {resp['error']}")
            entry = {"name": name, "pos": pos, "age": age, "verdict": verdict,
                     "tier": tier, "age_flag": age_flag, "luck_score": luck,
                     "key_metrics": {"BABIP": babip, "xwOBA_gap": xgap, "hr_fb_rate": hrfb},
                     "simple_narrative": None, "advanced_narrative": None, "error": resp["error"]}
        else:
            print(f"\n  SIMPLE:   {resp['simple']}")
            print(f"\n  ADVANCED: {resp['advanced']}")
            entry = {"name": name, "pos": pos, "age": age, "verdict": verdict,
                     "tier": tier, "age_flag": age_flag, "luck_score": luck,
                     "key_metrics": {"BABIP": babip, "xwOBA_gap": xgap, "hr_fb_rate": hrfb,
                                     "wOBA": fmt_rate(r.get("wOBA")),
                                     "xwOBA": fmt_rate(r.get("xwOBA"))},
                     "simple_narrative": resp["simple"],
                     "advanced_narrative": resp["advanced"]}

        results["hitters"]["sell_high"].append(entry)

    # ── Pitcher buy low ───────────────────────────────────────────────────────
    print(f"\n\n{'='*72}")
    print("  PITCHER BUY LOW — generating narratives")
    print(f"{'='*72}")

    for r in buy_pitchers:
        name   = r.get("name", "?")
        age    = r.get("age", "?")
        luck   = flt(r.get("luck_score", 0))
        verdict = r.get("verdict", "")
        era    = flt(r.get("ERA", 0))
        fip_v  = flt(r.get("FIP", 0))
        efip   = flt(r.get("ERA_minus_FIP", 0))
        ip     = flt(r.get("IP", 0))

        print(f"\n{divider}")
        print(f"  {name} (age {age}) | luck={luck:+.3f} | ERA={era:.2f} FIP={fip_v:.2f} gap={efip:+.2f} | IP={ip:.0f}")
        print(f"  Calling API …")

        prompt = build_pitcher_prompt(r, "buy")
        resp   = call_api(client, prompt, name)

        if "error" in resp:
            print(f"  ❌ ERROR: {resp['error']}")
            entry = {"name": name, "age": age, "verdict": verdict, "tier": "",
                     "luck_score": luck,
                     "key_metrics": {"ERA": era, "FIP": fip_v, "ERA_minus_FIP": efip, "IP": ip},
                     "simple_narrative": None, "advanced_narrative": None, "error": resp["error"]}
        else:
            print(f"\n  SIMPLE:   {resp['simple']}")
            print(f"\n  ADVANCED: {resp['advanced']}")
            entry = {"name": name, "age": age, "verdict": verdict, "tier": "",
                     "luck_score": luck,
                     "key_metrics": {"ERA": era, "FIP": fip_v, "ERA_minus_FIP": efip,
                                     "xERA": flt(r.get("xERA", 0)),
                                     "SwStr_pct": fmt_pct(r.get("swstr_rate")),
                                     "GB_pct": fmt_pct(r.get("gb_pct")), "IP": ip},
                     "simple_narrative": resp["simple"],
                     "advanced_narrative": resp["advanced"]}

        results["pitchers"]["buy_low"].append(entry)

    # ── Pitcher sell high ─────────────────────────────────────────────────────
    print(f"\n\n{'='*72}")
    print("  PITCHER SELL HIGH — generating narratives")
    print(f"{'='*72}")

    for r in sell_pitchers:
        name    = r.get("name", "?")
        age     = r.get("age", "?")
        luck    = flt(r.get("luck_score", 0))
        verdict = r.get("verdict", "")
        tier    = r.get("tier_sell", "")
        age_flag = r.get("age_flag", "")
        era     = flt(r.get("ERA", 0))
        fip_v   = flt(r.get("FIP", 0))
        efip    = flt(r.get("ERA_minus_FIP", 0))
        ip      = flt(r.get("IP", 0))

        print(f"\n{divider}")
        print(f"  {name} (age {age}) | luck={luck:+.3f} | tier={tier}{' | '+age_flag if age_flag else ''}")
        print(f"  ERA={era:.2f} FIP={fip_v:.2f} gap={efip:+.2f} | IP={ip:.0f}")
        print(f"  Calling API …")

        prompt = build_pitcher_prompt(r, "sell")
        resp   = call_api(client, prompt, name)

        if "error" in resp:
            print(f"  ❌ ERROR: {resp['error']}")
            entry = {"name": name, "age": age, "verdict": verdict,
                     "tier": tier, "age_flag": age_flag, "luck_score": luck,
                     "key_metrics": {"ERA": era, "FIP": fip_v, "ERA_minus_FIP": efip, "IP": ip},
                     "simple_narrative": None, "advanced_narrative": None, "error": resp["error"]}
        else:
            print(f"\n  SIMPLE:   {resp['simple']}")
            print(f"\n  ADVANCED: {resp['advanced']}")
            entry = {"name": name, "age": age, "verdict": verdict,
                     "tier": tier, "age_flag": age_flag, "luck_score": luck,
                     "key_metrics": {"ERA": era, "FIP": fip_v, "ERA_minus_FIP": efip,
                                     "xERA": flt(r.get("xERA", 0)),
                                     "LOB_pct": fmt_pct(r.get("lob_pct")),
                                     "xwOBA_gap": flt(r.get("xwoba_gap", 0)), "IP": ip},
                     "simple_narrative": resp["simple"],
                     "advanced_narrative": resp["advanced"]}

        results["pitchers"]["sell_high"].append(entry)

    # ── Summary ───────────────────────────────────────────────────────────────
    total  = (len(results["hitters"]["buy_low"]) + len(results["hitters"]["sell_high"]) +
              len(results["pitchers"]["buy_low"]) + len(results["pitchers"]["sell_high"]))
    errors = sum(
        1 for bucket in (results["hitters"]["buy_low"], results["hitters"]["sell_high"],
                         results["pitchers"]["buy_low"], results["pitchers"]["sell_high"])
        for entry in bucket if "error" in entry
    )

    print(f"\n\n{'='*72}")
    print(f"  DONE — {total} players processed, {errors} API errors")
    print(f"  Review narratives above, then run with --write to save")
    print(f"{'='*72}")

    # ── Write gate ────────────────────────────────────────────────────────────
    if "--write" in sys.argv:
        os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        size_kb = os.path.getsize(OUTPUT_PATH) / 1024
        print(f"\n  Wrote {OUTPUT_PATH} ({size_kb:.1f} KB)")
    else:
        print(f"\n  (dry run — pass --write to save to {OUTPUT_PATH})")

    return results


if __name__ == "__main__":
    main()
