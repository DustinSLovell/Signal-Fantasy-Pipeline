"""
trade_analyzer.py  v2
Command-line trade evaluator using Signal Fantasy luck scores.

Usage:
    python trade_analyzer.py              # interactive trade analysis
    python trade_analyzer.py --setup      # configure league settings
    python trade_analyzer.py --test       # run non-interactive test suite
    python trade_analyzer.py --history    # show last 20 trades
"""

import argparse
import csv
import difflib
import json
import re
import sys
import unicodedata
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from config import (
    CBS_H_COEF_R, CBS_H_COEF_HR, CBS_H_COEF_RBI, CBS_H_COEF_SB,
    CBS_H_COEF_AVG, CBS_H_INTERCEPT,
    CBS_P_COEF_W, CBS_P_COEF_ERA, CBS_P_COEF_WHIP, CBS_P_COEF_K,
    CBS_P_COEF_SV, CBS_P_INTERCEPT,
)
from replacement_level import (
    load_replacement_levels, load_position_map,
    get_surplus, FANTASY_POS_MAP, build_replacement_table,
    DEFAULT_ROSTER_N,
)

BASE_DIR      = Path(__file__).parent
HITTER_CSV    = BASE_DIR / "luck_scores.csv"
PITCHER_CSV   = BASE_DIR / "pitcher_luck_scores.csv"
PROJ_CSV      = BASE_DIR / "data" / "projections_2026.csv"
CONFIG_PATH   = BASE_DIR / "data" / "league_config.json"
HISTORY_PATH  = BASE_DIR / "data" / "trade_history.csv"
LEAGUES_DIR   = BASE_DIR / "data" / "leagues"

BUY_LOW     =  0.150
SLIGHT_BUY  =  0.065
SLIGHT_SELL = -0.085
SELL_HIGH   = -0.150

# Scarcity score adjustments
SCARCITY_GET = 0.15   # bonus for acquiring a scarce-position player with positive signal
SCARCITY_GIVE = 0.10  # penalty for giving away a scarce-position player with positive signal

# Trajectory/timing uncertainty discount
TRAJECTORY_DISCOUNT = 0.05  # applied when signal is small-sample uncertain

# Innings/PA thresholds for small-sample flag
MIN_IP_CONFIDENT = 20.0
MIN_PA_CONFIDENT = 50

WIDE   = 65
THIN_W = 65
DIVIDER = "=" * WIDE
THIN    = "-" * THIN_W

# Force UTF-8 output so box/arrow chars render on Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Replacement levels loaded once at import time — safe to cache since
# projections_2026.csv is static within a session.
_REPL_LEVELS: dict[str, float] = load_replacement_levels()


# ---------------------------------------------------------------------------
# League config
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = {
    "league_type": "roto",
    "scoring_format": "categories",
    "team_count": 12,
    "auction_budget": None,
    "scarce_positions": ["SP", "C"],
}


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH) as f:
                cfg = json.load(f)
            return {**DEFAULT_CONFIG, **cfg}
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)


def save_config(cfg: dict) -> None:
    CONFIG_PATH.parent.mkdir(exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


def setup_league_config() -> None:
    print()
    print(DIVIDER)
    print("  SIGNAL FANTASY — League Setup")
    print(DIVIDER)
    cfg = load_config()

    def _ask(prompt: str, current, converter, valid=None):
        cur_str = str(current) if current is not None else "None"
        while True:
            raw = input(f"  {prompt} [{cur_str}]: ").strip()
            if not raw:
                return current
            try:
                val = converter(raw)
            except (ValueError, TypeError):
                print(f"  Invalid input. Expected {converter.__name__}.")
                continue
            if valid and val not in valid:
                print(f"  Must be one of: {valid}")
                continue
            return val

    cfg["league_type"]      = _ask("League type (roto/h2h)", cfg["league_type"], str, ["roto", "h2h"])
    cfg["scoring_format"]   = _ask("Scoring format (categories/points)", cfg["scoring_format"], str, ["categories", "points"])
    cfg["team_count"]       = _ask("Number of teams", cfg["team_count"], int)
    budget_raw = input(f"  Auction budget (Enter to skip) [{cfg['auction_budget']}]: ").strip()
    if budget_raw:
        try:
            cfg["auction_budget"] = int(budget_raw)
        except ValueError:
            cfg["auction_budget"] = None

    save_config(cfg)
    print()
    print(f"  Saved to {CONFIG_PATH.name}")
    _print_config(cfg)


def _print_config(cfg: dict) -> None:
    budget_str = f"${cfg['auction_budget']}" if cfg.get("auction_budget") else "snake draft"
    print(f"  League  : {cfg['team_count']}-team {cfg['league_type'].title()} | {cfg['scoring_format'].title()}")
    print(f"  Draft   : {budget_str}")
    print(f"  Scarce  : {', '.join(cfg.get('scarce_positions', []))}")


# ---------------------------------------------------------------------------
# League JSON helpers (Task 4 — Session 39)
# ---------------------------------------------------------------------------

def _load_league_json(league_id: int) -> dict:
    """Load data/leagues/league_{id}.json. Falls back to 12-team defaults."""
    path = LEAGUES_DIR / f"league_{league_id}.json"
    if path.exists():
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "league_id": f"league_{league_id}",
        "league_name": f"League {league_id} (defaults)",
        "team_count": 12,
        "roster_slots": {"C":1,"1B":1,"2B":1,"3B":1,"SS":1,"MI":1,"CI":1,"OF":3,"UT":1,"SP":5,"RP":3},
        "stat_weights": {"AVG": 1.0, "OBP": 0.0},
    }


def _compute_roster_n(league_json: dict) -> dict:
    """Derive per-position starter count from league_json roster_slots × team_count.

    CI (corner infield) split evenly between 1B and 3B.
    MI (middle infield) split evenly between 2B and SS.
    UT (utility) allocated 15% to OF pool.
    P (combined pitcher slots) split 60% SP / 40% RP.
    """
    tc    = league_json.get("team_count", 12)
    slots = league_json.get("roster_slots", {})

    ci  = slots.get("CI", 0)
    mi  = slots.get("MI", 0)
    ut  = slots.get("UT", 0)
    p   = slots.get("P", 0)

    n = {
        "C":  max(int(round(slots.get("C",  1)               * tc)), 8),
        "1B": max(int(round((slots.get("1B",1) + ci * 0.5)   * tc)), 8),
        "2B": max(int(round((slots.get("2B",1) + mi * 0.5)   * tc)), 8),
        "3B": max(int(round((slots.get("3B",1) + ci * 0.5)   * tc)), 8),
        "SS": max(int(round((slots.get("SS",1) + mi * 0.5)   * tc)), 8),
        "OF": max(int(round((slots.get("OF",3) + ut * 0.15)  * tc)), 12),
        "SP": max(int((slots.get("SP",0) + p * 0.6)          * tc), 12),
        "RP": max(int((slots.get("RP",0) + p * 0.4)          * tc), 12),
    }
    return n


def _repl_level_value(team_count: int) -> float:
    """Opportunity cost of dropping a waiver-wire player to clear a roster slot.
    Shallower leagues → better wire options → higher opp cost per drop.
    """
    if team_count <= 10: return 4.0
    if team_count <= 12: return 2.5
    if team_count <= 14: return 1.5
    return 0.5


def _elite_premium(fp_rank) -> float:
    """Non-linear scarcity premium for elite players based on FantasyPros ROS rank.

    Top-10: genuine scarcity, irreplaceable from waiver wire, maximum optionality → 30%
    Top-25: elite but some replaceability                                          → 15%
    Top-50: good, tradeable at fair value                                          →  5%
    Below 50: standard surplus calculation sufficient                              →  0%

    These are principled starting-point priors — NOT tuned to hit a specific verdict.
    """
    try:
        r = float(fp_rank)
        if r != r:  # NaN
            return 1.00
    except (TypeError, ValueError):
        return 1.00
    if r <= 10:  return 1.30
    if r <= 25:  return 1.15
    if r <= 50:  return 1.05
    return 1.00


def _compute_cbs_fpts_league(row: pd.Series, league_json: dict) -> Optional[float]:
    """Compute CBS-model projected FPTS respecting league stat_weights.

    For OBP leagues (stat_weights.OBP = 1): substitutes proj_obp for proj_avg.
    proj_obp computed as proj_avg + bb_rate × (1 − proj_avg) when bb_rate available;
    otherwise uses proj_avg + 0.065 as a principled proxy (avg walk-rate contribution).
    """
    ptype = row.get("_type", "hitter")
    stat_w = league_json.get("stat_weights", {})
    use_obp = stat_w.get("OBP", 0.0) > 0 and stat_w.get("AVG", 1.0) == 0

    def _f(col):
        v = row.get(col)
        try:
            return float(v) if pd.notna(v) else None
        except (TypeError, ValueError):
            return None

    if ptype == "hitter":
        r, hr, rbi, sb, avg = _f("proj_r"), _f("proj_hr"), _f("proj_rbi"), _f("proj_sb"), _f("proj_avg")
        if any(v is None for v in (r, hr, rbi, sb, avg)):
            return None
        if use_obp:
            bb = _f("bb_rate")
            if bb is not None:
                batting_val = avg + bb * (1.0 - avg)  # standard OBP proxy (no HBP)
            else:
                batting_val = avg + 0.065              # league-average walk-rate offset
        else:
            batting_val = avg
        return (CBS_H_COEF_R * r + CBS_H_COEF_HR * hr + CBS_H_COEF_RBI * rbi
                + CBS_H_COEF_SB * sb + CBS_H_COEF_AVG * batting_val + CBS_H_INTERCEPT)
    else:
        w, era, whip, k, sv = _f("proj_w"), _f("proj_era"), _f("proj_whip"), _f("proj_k"), _f("proj_sv_h")
        if any(v is None for v in (w, era, whip, k, sv)):
            return None
        return (CBS_P_COEF_W * w + CBS_P_COEF_ERA * era + CBS_P_COEF_WHIP * whip
                + CBS_P_COEF_K * k + CBS_P_COEF_SV * sv + CBS_P_INTERCEPT)


# ---------------------------------------------------------------------------
# Name normalisation
# ---------------------------------------------------------------------------

_SUFFIX_RE = re.compile(r"\b(jr|sr|ii|iii|iv)\b")
_POS_TAG_RE = re.compile(r"\[([a-zA-Z0-9/]+)\]")


def _norm(s: str) -> str:
    try:
        s = str(s).encode("latin1").decode("utf-8")
    except Exception:
        pass
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z ]", "", s.lower()).strip()


def _strip_pos_tag(name_input: str) -> tuple[str, Optional[str]]:
    """Extract optional [POS] tag from input. Returns (clean_name, pos_or_None)."""
    m = _POS_TAG_RE.search(name_input)
    if m:
        pos = m.group(1).upper()
        clean = _POS_TAG_RE.sub("", name_input).strip()
        return clean, pos
    return name_input.strip(), None


# ---------------------------------------------------------------------------
# Player loading + position derivation
# ---------------------------------------------------------------------------

_SP_IP_PER_APP = 4.0  # avg IP/appearance threshold to classify as SP


def _derive_pos(row: pd.Series) -> str:
    """Derive position string for display and scarcity checks."""
    ptype = row.get("_type", "hitter")
    user_pos = row.get("_user_pos")
    if user_pos:
        return user_pos
    if ptype == "pitcher":
        # Use player_type from pitcher_luck_scores.csv (most reliable — Steamer GS-based)
        player_type = row.get("player_type")
        if player_type in ("SP", "RP"):
            return player_type
        # role_override: Steamer said RP but pitcher is demonstrably starting in 2026
        role_override = row.get("role_override")
        if role_override is True or str(role_override).lower() == "true":
            return "SP"
        # Fallback: IP-per-appearance heuristic
        ip   = row.get("IP", 0)
        apps = row.get("total_starts")
        gs   = row.get("GS")
        try:
            if pd.notna(gs) and float(gs) >= 3:
                return "SP"
        except (TypeError, ValueError):
            pass
        try:
            if pd.notna(apps) and float(apps) > 0:
                ip_per_app = float(ip) / float(apps)
                return "SP" if ip_per_app >= _SP_IP_PER_APP else "RP"
        except (TypeError, ValueError):
            pass
        return "P"
    return "?"


def _compute_cbs_fpts(row: pd.Series) -> Optional[float]:
    """Compute CBS-model projected FPTS from rest-of-season projections."""
    ptype = row.get("_type", "hitter")

    def _f(col):
        v = row.get(col)
        try:
            return float(v) if pd.notna(v) else None
        except (TypeError, ValueError):
            return None

    if ptype == "hitter":
        r, hr, rbi, sb, avg = _f("proj_r"), _f("proj_hr"), _f("proj_rbi"), _f("proj_sb"), _f("proj_avg")
        if any(v is None for v in (r, hr, rbi, sb, avg)):
            return None
        return (CBS_H_COEF_R * r + CBS_H_COEF_HR * hr + CBS_H_COEF_RBI * rbi
                + CBS_H_COEF_SB * sb + CBS_H_COEF_AVG * avg + CBS_H_INTERCEPT)
    else:
        w, era, whip, k, sv = _f("proj_w"), _f("proj_era"), _f("proj_whip"), _f("proj_k"), _f("proj_sv_h")
        if any(v is None for v in (w, era, whip, k, sv)):
            return None
        return (CBS_P_COEF_W * w + CBS_P_COEF_ERA * era + CBS_P_COEF_WHIP * whip
                + CBS_P_COEF_K * k + CBS_P_COEF_SV * sv + CBS_P_INTERCEPT)


def _load_players() -> pd.DataFrame:
    frames = []
    for path, ptype in [(HITTER_CSV, "hitter"), (PITCHER_CSV, "pitcher")]:
        if path.exists():
            df = pd.read_csv(path)
            df["_type"] = ptype
            if "team" in df.columns and "Team" not in df.columns:
                df["Team"] = df["team"]
            frames.append(df)
    if not frames:
        raise FileNotFoundError("No luck score files found. Run the pipeline first.")
    combined = pd.concat(frames, ignore_index=True).copy()

    # Merge rest-of-season projections for CBS FPTS computation
    proj_cols = ["name", "proj_r", "proj_hr", "proj_rbi", "proj_sb", "proj_avg",
                 "proj_w", "proj_era", "proj_whip", "proj_k", "proj_sv_h"]
    if PROJ_CSV.exists():
        proj = pd.read_csv(PROJ_CSV)[proj_cols].copy()
        proj["_norm_proj"] = proj["name"].apply(_norm)
        combined["_norm_proj"] = combined["name"].apply(_norm)
        combined = combined.merge(
            proj.drop(columns=["name"]),
            on="_norm_proj", how="left"
        ).drop(columns=["_norm_proj"]).copy()

    # Merge fantasy positions from player_values.json (id-based for accuracy)
    pos_map = load_position_map()  # {mlbam_id: fantasy_pos}
    def _get_fpos(row):
        # For pitchers: player_type column (from Steamer GS) is most reliable.
        # player_values.json can lag when score_value.py run predates role corrections.
        if row.get("_type") == "pitcher":
            return "SP" if _derive_pos(row) == "SP" else "RP"
        # For hitters: use player_values.json id lookup (most accurate multi-pos handling)
        pid = row.get("batter")
        try:
            fpos = pos_map.get(int(pid)) if pd.notna(pid) else None
        except (TypeError, ValueError):
            fpos = None
        return fpos

    combined["_fpos"] = combined.apply(_get_fpos, axis=1)
    combined["_norm"] = combined["name"].apply(_norm)
    combined["_user_pos"] = None
    return combined


def _fuzzy_find(name_input: str, df: pd.DataFrame) -> pd.DataFrame:
    query = _norm(name_input)
    exact = df[df["_norm"] == query]
    if not exact.empty:
        return exact
    words = query.split()
    mask = df["_norm"].apply(lambda n: all(w in n for w in words))
    return df[mask]


def _suggest_player(name_input: str, df: pd.DataFrame, top_n: int = 2) -> list[dict]:
    """Return top_n close-match suggestions when exact/word match fails.

    Uses last-name match first, then SequenceMatcher ratio on full normalized names.
    Always returns candidates regardless of score — for display-only suggestions.
    """
    query = _norm(name_input)
    query_words = query.split()

    # Last-name match: if any word in query matches any word in a player's name
    last_word = query_words[-1] if query_words else ""
    lastname_matches = df[df["_norm"].apply(lambda n: last_word in n.split())]
    if not lastname_matches.empty:
        # Score lastname matches by full-name similarity
        scored = []
        for _, row in lastname_matches.iterrows():
            ratio = difflib.SequenceMatcher(None, query, row["_norm"]).ratio()
            team = row.get("Team", row.get("team", ""))
            scored.append({"name": row.get("name", "?"), "team": team, "ratio": ratio})
        scored.sort(key=lambda x: x["ratio"], reverse=True)
        return scored[:top_n]

    # Fallback: SequenceMatcher across all players
    scored = []
    for _, row in df.iterrows():
        ratio = difflib.SequenceMatcher(None, query, row["_norm"]).ratio()
        if ratio >= 0.50:
            team = row.get("Team", row.get("team", ""))
            scored.append({"name": row.get("name", "?"), "team": team, "ratio": ratio})
    scored.sort(key=lambda x: x["ratio"], reverse=True)
    return scored[:top_n]


def _resolve_player(name_input: str, players: pd.DataFrame, label: str = "Player") -> Optional[pd.Series]:
    """
    Interactive disambiguation. Returns a single row or None on failure.
    Handles [POS] tags and appends _user_pos to the returned row.
    """
    clean_name, user_pos = _strip_pos_tag(name_input)
    rows = _fuzzy_find(clean_name, players)

    if rows.empty:
        print(f"  {label} not found: '{clean_name}'. Try last name or partial name.")
        return None

    if len(rows) > 1:
        print(f"  Multiple matches for '{clean_name}':")
        for _, r in rows.iterrows():
            ptype = r.get("_type", "?")
            team  = r.get("Team", r.get("team", "?"))
            print(f"    {r['name']}  ({team}, {ptype})")
        choice = input("  Enter exact name to select (or Enter to skip): ").strip()
        if not choice:
            return None
        rows = _fuzzy_find(choice, players)
        if rows.empty or len(rows) > 1:
            print("  Could not resolve. Skipping.")
            return None

    row = rows.iloc[0].copy()
    if user_pos:
        row["_user_pos"] = user_pos
    return row


def _parse_side(raw_input: str, players: pd.DataFrame, side_label: str) -> list[pd.Series]:
    """Parse comma-separated player names into a list of resolved rows (1-4 players)."""
    parts = [p.strip() for p in raw_input.split(",") if p.strip()]
    if not parts:
        return []
    if len(parts) > 4:
        parts = parts[:4]
        print(f"  (Capped at 4 players per side)")

    resolved = []
    for i, name in enumerate(parts, 1):
        label = f"{side_label} player {i}" if len(parts) > 1 else side_label
        row = _resolve_player(name, players, label)
        if row is None:
            return []
        resolved.append(row)
    return resolved


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _stat(val, dec: int = 3, signed: bool = False, leading_zero: bool = True) -> str:
    try:
        v = float(val)
        if pd.isna(v):
            return "N/A"
    except (TypeError, ValueError):
        return "N/A"
    s = f"{abs(v):.{dec}f}"
    if not leading_zero and s.startswith("0."):
        s = s[1:]
    prefix = "+" if (signed and v >= 0) else ("-" if v < 0 else "")
    return prefix + s


def _signal_desc(verdict: str, ptype: str) -> str:
    """One-line description of what the signal means for this player in a trade."""
    v = verdict.lower()
    if ptype == "pitcher":
        if "buy low" in v:   return "ERA inflated by luck — peripherals suggest improvement ahead"
        if "sell high" in v: return "ERA masking poor peripherals — regression incoming"
        if "slight sell" in v: return "mild ERA outperformance — some regression likely"
    else:
        if "buy low" in v:   return "underperforming contact quality — buy before market adjusts"
        if "sell high" in v: return "overperforming contact quality — sell before regression hits"
        if "slight sell" in v: return "minor overperformance — modest regression risk"
    return "stats roughly matching underlying performance"


def _signal_context_warnings(give_rows: list, get_rows: list) -> list:
    """Return list of advisory strings for the SIGNAL CONTEXT block."""
    lines = []
    for row in give_rows:
        sig = str(row.get("verdict", "")).lower()
        name = row.get("name", "?")
        if "buy low" in sig:
            lines.append(f"  ⚠  Giving {name}: Buy Low — true value likely HIGHER than perceived. Consider asking for more.")
        elif "sell high" in sig:
            lines.append(f"  ✓  Giving {name}: Sell High — good time to sell at peak value.")
        elif "slight sell" in sig:
            lines.append(f"  ·  Giving {name}: Slight Sell — mild regression risk; market may still overvalue.")
    for row in get_rows:
        sig = str(row.get("verdict", "")).lower()
        name = row.get("name", "?")
        if "sell high" in sig:
            lines.append(f"  ⚠  Receiving {name}: Sell High — true value likely LOWER than perceived.")
        elif "buy low" in sig:
            lines.append(f"  ✓  Receiving {name}: Buy Low — good time to buy while market undervalues them.")
        elif "slight sell" in sig:
            lines.append(f"  ·  Receiving {name}: Slight Sell — mild regression on this side; monitor.")
    return lines


def _assessment(verdict: str, ptype: str) -> str:
    if ptype == "pitcher":
        if verdict == "Buy low":
            return "ERA inflated by luck — peripherals suggest improvement ahead."
        if verdict == "Slight buy":
            return "Moderate signal — some luck inflation, peripherals look better."
        if verdict == "Slight sell":
            return "ERA looks slightly too good — some regression likely."
        if verdict == "Sell high":
            return "ERA masking poor underlying stats — sell before regression hits."
        return "No strong signal — stats roughly match underlying performance."
    else:
        if verdict == "Buy low":
            return "Stats well below true talent — strong regression-upward candidate."
        if verdict == "Slight buy":
            return "Mild underperformance — contact quality suggests better results coming."
        if verdict == "Slight sell":
            return "Slight overperformance — stats a bit ahead of underlying quality."
        if verdict == "Sell high":
            return "Stats well above true talent — regression likely, sell at peak value."
        return "No strong signal — stats reflect underlying performance."


def _auction_estimate(row: pd.Series, config: dict) -> Optional[str]:
    budget = config.get("auction_budget")
    if not budget:
        return None
    teams = config.get("team_count", 12)
    owned_pct = row.get("owned_pct")
    if pd.isna(owned_pct) if not isinstance(owned_pct, str) else not owned_pct:
        return None
    try:
        pct = float(owned_pct)
    except (TypeError, ValueError):
        return None
    # Rough market value estimate
    market = max(1, round(pct / 100 * budget / teams * 1.5))
    verdict = str(row.get("verdict", "Neutral"))
    score = float(row.get("luck_score", 0.0)) if pd.notna(row.get("luck_score")) else 0.0
    if verdict == "Buy low":
        signal_mult = 1.35
    elif verdict == "Slight buy":
        signal_mult = 1.15
    elif verdict == "Sell high":
        signal_mult = 0.70
    elif verdict == "Slight sell":
        signal_mult = 0.85
    else:
        signal_mult = 1.0
    signal_val = max(1, round(market * signal_mult))
    if signal_mult > 1.0:
        return f"Market ~${market} | Signal value ~${signal_val} (underpriced)"
    elif signal_mult < 1.0:
        return f"Market ~${market} | Signal value ~${signal_val} (overpriced)"
    return f"Market ~${market}"


def _display_player(row: pd.Series, config: dict) -> None:
    ptype   = str(row.get("_type", "hitter"))
    name    = row.get("name", "Unknown")
    team    = row.get("Team", row.get("team", "?"))
    pos     = _derive_pos(row)
    verdict = str(row.get("verdict", "Neutral"))
    score   = row.get("luck_score", 0.0)
    age     = row.get("age", "?")

    score_str = _stat(score, dec=3, signed=True)
    print(f"  ▶  {name} — {team}  [{pos}, age {age}]")
    print(f"     Signal   : {verdict}  (luck score: {score_str})")

    if ptype == "hitter":
        woba  = _stat(row.get("wOBA"),     dec=3, leading_zero=False)
        xwoba = _stat(row.get("xwOBA"),    dec=3, leading_zero=False)
        gap   = _stat(row.get("xwOBA_gap", row.get("xwoba_gap", float("nan"))),
                      dec=3, signed=True, leading_zero=False)
        babip  = _stat(row.get("BABIP"),        dec=3, leading_zero=False)
        cbabip = _stat(row.get("career_babip"), dec=3, leading_zero=False)
        pa     = row.get("PA", "?")
        print(f"     wOBA     : {woba}  |  xwOBA: {xwoba}  |  xwOBA gap: {gap}")
        print(f"     BABIP    : {babip}  |  Career BABIP: {cbabip}  |  PA: {pa}")
    else:
        era  = _stat(row.get("ERA"),  dec=2)
        fip  = _stat(row.get("FIP"),  dec=2)
        xera = _stat(row.get("xERA"), dec=2)
        gap  = _stat(row.get("ERA_minus_FIP", float("nan")), dec=2, signed=True)
        ip   = row.get("IP", "?")
        conf = row.get("conf_phase", "")
        conf_str = f"  |  Phase: {conf}" if conf else ""
        print(f"     ERA/FIP  : {era} / {fip}  |  xERA: {xera}  |  ERA-FIP: {gap}  |  IP: {ip}{conf_str}")

    # CBS projected FPTS + positional surplus
    cbs_fpts = _compute_cbs_fpts(row)
    if cbs_fpts is not None:
        fpos = row.get("_fpos")
        surplus = get_surplus(cbs_fpts, fpos, _REPL_LEVELS)
        surplus_str = (f"  |  Surplus vs {fpos}: {surplus:+.0f}"
                       if surplus is not None else "")
        if ptype == "hitter":
            proj_line = (f"R {row.get('proj_r','?'):.0f}  HR {row.get('proj_hr','?'):.0f}"
                         f"  RBI {row.get('proj_rbi','?'):.0f}  SB {row.get('proj_sb','?'):.0f}"
                         f"  AVG {row.get('proj_avg','?'):.3f}")
        else:
            proj_line = (f"W {row.get('proj_w','?'):.0f}  ERA {row.get('proj_era','?'):.2f}"
                         f"  WHIP {row.get('proj_whip','?'):.2f}  K {row.get('proj_k','?'):.0f}"
                         f"  SV {row.get('proj_sv_h','?'):.0f}")
        print(f"     Proj FPTS: {cbs_fpts:.0f}{surplus_str}  ({proj_line})")

    # Ownership
    owned = row.get("owned_pct")
    tier  = row.get("ownership_tier", "")
    if pd.notna(owned) if not isinstance(owned, str) else owned:
        try:
            print(f"     Ownership: {float(owned):.1f}%  ({tier})")
        except (TypeError, ValueError):
            pass

    # This Is Real / Actually Bad
    real = row.get("this_is_real")
    bad  = row.get("this_is_actually_bad")
    if isinstance(real, str) and real in ("Confirmed", "Monitor"):
        print(f"     Reality  : {real} performer (stats backed by contact quality)")
    if isinstance(bad, str) and bad == "Confirmed":
        print(f"     ⚠ Warning: This Is Actually Bad — weak contact quality despite any luck signal")

    # Auction estimate
    auction_str = _auction_estimate(row, config)
    if auction_str:
        print(f"     Auction  : {auction_str}")

    # Short career baseline flag — display only, no verdict change
    try:
        if float(row.get("career_pa", 9999)) < 300:
            print("     ⚠ Short baseline — under 300 career PA. Verify barrel rate and "
                  "exit velocity trend before acting on this call.")
    except (TypeError, ValueError):
        pass

    print(f"     Note     : {_assessment(verdict, ptype)}")


# ---------------------------------------------------------------------------
# Score aggregation
# ---------------------------------------------------------------------------

def _aggregate_score(rows: list[pd.Series]) -> float:
    """Equal-weight mean luck score across all players on one side."""
    scores = []
    for r in rows:
        s = r.get("luck_score", 0.0)
        try:
            if pd.notna(s):
                scores.append(float(s))
        except (TypeError, ValueError):
            pass
    return sum(scores) / len(scores) if scores else 0.0


# ---------------------------------------------------------------------------
# Scarcity adjustment
# ---------------------------------------------------------------------------

def _is_scarce(row: pd.Series, config: dict) -> bool:
    pos = _derive_pos(row)
    scarce = config.get("scarce_positions", ["SP", "C"])
    return pos in scarce


def _scarcity_adj(give_rows: list[pd.Series], get_rows: list[pd.Series],
                  config: dict) -> tuple[float, list[str]]:
    """
    Returns net scarcity score delta (positive = trade favors you) and notes.
    Getting a scarce buy-low: +0.15
    Giving a scarce buy-low:  -0.10
    """
    adj = 0.0
    notes = []

    for row in get_rows:
        if _is_scarce(row, config):
            score = row.get("luck_score", 0.0)
            try:
                score = float(score)
            except (TypeError, ValueError):
                score = 0.0
            if score >= SLIGHT_BUY:
                adj += SCARCITY_GET
                pos = _derive_pos(row)
                notes.append(f"  ★ Getting {row.get('name','?')} [{pos}] — scarce position buy-low (+{SCARCITY_GET:.2f})")

    for row in give_rows:
        if _is_scarce(row, config):
            score = row.get("luck_score", 0.0)
            try:
                score = float(score)
            except (TypeError, ValueError):
                score = 0.0
            if score >= SLIGHT_BUY:
                adj -= SCARCITY_GIVE
                pos = _derive_pos(row)
                notes.append(f"  ⚠ Giving {row.get('name','?')} [{pos}] — scarce position buy-low (-{SCARCITY_GIVE:.2f})")

    return adj, notes


# ---------------------------------------------------------------------------
# Trajectory/timing adjustment
# ---------------------------------------------------------------------------

def _trajectory_adj(give_rows: list[pd.Series], get_rows: list[pd.Series]
                    ) -> tuple[float, list[str]]:
    """
    Apply a small uncertainty discount when signal is based on small samples.
    Getting a buy-low with tiny sample: -0.05 (less certain they'll bounce back)
    Giving a sell-high with tiny sample: +0.05 (may regress less if luck is real)
    """
    adj = 0.0
    notes = []

    for row in get_rows:
        if _is_small_sample(row):
            score = row.get("luck_score", 0.0)
            try:
                score = float(score) if pd.notna(score) else 0.0
            except (TypeError, ValueError):
                score = 0.0
            if score >= SLIGHT_BUY:
                adj -= TRAJECTORY_DISCOUNT
                notes.append(f"  ⚡ {row.get('name','?')}: early-season signal — small sample discount (-{TRAJECTORY_DISCOUNT:.2f})")

    for row in give_rows:
        if _is_small_sample(row):
            score = row.get("luck_score", 0.0)
            try:
                score = float(score) if pd.notna(score) else 0.0
            except (TypeError, ValueError):
                score = 0.0
            if score <= SLIGHT_SELL:
                adj += TRAJECTORY_DISCOUNT
                notes.append(f"  ⚡ {row.get('name','?')}: early-season signal — sell-high discount (+{TRAJECTORY_DISCOUNT:.2f})")

    return adj, notes


def _is_small_sample(row: pd.Series) -> bool:
    ptype = row.get("_type", "hitter")
    if ptype == "pitcher":
        ip = row.get("IP", 0)
        try:
            return float(ip) < MIN_IP_CONFIDENT
        except (TypeError, ValueError):
            return False
    else:
        pa = row.get("PA", 0)
        try:
            return int(pa) < MIN_PA_CONFIDENT
        except (TypeError, ValueError):
            return False


# ---------------------------------------------------------------------------
# Signal-adjusted projections (Backtest B v2 multipliers — Step 2)
# ---------------------------------------------------------------------------

# Validated multipliers from Backtest B v2 (projection_backtest_B.py).
# Applied to projected STAT columns ONLY.  Signal badges are display-only
# after this point and do NOT touch verdict logic.
# HR sell-side and AVG multipliers removed — hurt MAE in backtest.
_H_SIGNAL_MULTS: dict[str, dict[str, float]] = {
    "buy low":    {"proj_r": 1.08, "proj_rbi": 1.08, "proj_hr": 1.05},
    "slight buy": {"proj_r": 1.04, "proj_rbi": 1.04, "proj_hr": 1.02},
    "slight sell": {"proj_r": 0.96, "proj_rbi": 0.96},
    "sell high":  {"proj_r": 0.92, "proj_rbi": 0.92},
}
_P_SIGNAL_MULTS: dict[str, dict[str, float]] = {
    "buy low":  {"proj_whip": 0.95, "proj_k": 1.05},
    "sell high": {"proj_era": 1.10, "proj_whip": 1.05, "proj_k": 0.95},
}


def _apply_signal_multipliers(row: pd.Series) -> pd.Series:
    """Return a copy of row with projected stats adjusted per signal verdict."""
    row = row.copy()
    ptype   = row.get("_type", "hitter")
    verdict = str(row.get("verdict", "Neutral")).lower()

    table = _H_SIGNAL_MULTS if ptype == "hitter" else _P_SIGNAL_MULTS
    mults = None
    for tier, m in table.items():
        if tier in verdict:
            mults = m
            break

    if mults:
        for col, mult in mults.items():
            v = row.get(col)
            try:
                if v is not None and pd.notna(v):
                    row[col] = float(v) * mult
            except (TypeError, ValueError):
                pass
    return row


# ---------------------------------------------------------------------------
# Trade verdict
# ---------------------------------------------------------------------------

def _trade_verdict_v2(raw_delta: float, total_delta: float) -> str:
    if total_delta >= 0.25:
        return "STRONG TRADE — clear luck advantage on the incoming side"
    if total_delta >= 0.12:
        return "FAVORABLE — meaningful luck advantage"
    if total_delta >= 0.03:
        return "SLIGHTLY FAVORABLE — modest luck edge on the incoming side"
    if total_delta <= -0.25:
        return "AVOID — significant luck disadvantage incoming"
    if total_delta <= -0.12:
        return "UNFAVORABLE — meaningful luck disadvantage"
    if total_delta <= -0.03:
        return "SLIGHTLY UNFAVORABLE — modest luck edge on the outgoing side"
    return "NEUTRAL — similar luck profiles on both sides"


def _trade_verdict_v3(surplus_delta: Optional[float]) -> str:
    """Verdict based on signal-adjusted surplus delta (primary verdict driver)."""
    if surplus_delta is None:
        return "NEUTRAL — insufficient projection data for value comparison"
    if surplus_delta >= 50:
        return "STRONG TRADE — clear projected value advantage incoming"
    if surplus_delta >= 20:
        return "FAVORABLE — meaningful projected value advantage"
    if surplus_delta >= 5:
        return "SLIGHTLY FAVORABLE — modest projected value edge"
    if surplus_delta <= -50:
        return "AVOID — significant projected value disadvantage"
    if surplus_delta <= -20:
        return "UNFAVORABLE — meaningful projected value disadvantage"
    if surplus_delta <= -5:
        return "SLIGHTLY UNFAVORABLE — modest projected value gap"
    return "NEUTRAL — comparable projected value on both sides"


def _fmt(v, dec: int = 0) -> str:
    """Format a value for explain walkthrough; tolerates None/NaN."""
    try:
        f = float(v)
        if f != f:  # NaN
            return "?"
        fmt = f"{{:.{dec}f}}"
        return fmt.format(f)
    except (TypeError, ValueError):
        return str(v) if v is not None else "?"


def _explain_walkthrough(
    give_rows: list[pd.Series],
    get_rows: list[pd.Series],
    give_adj: list[pd.Series],
    get_adj: list[pd.Series],
    give_surplus_vals: list,
    get_surplus_vals: list,
    give_surplus_total: Optional[float],
    get_surplus_total: Optional[float],
    surplus_delta: Optional[float],
    verdict: str,
) -> None:
    """Print step-by-step CBS FPTS + surplus walkthrough (--explain mode)."""

    SEP  = "=" * WIDE
    LINE = "  " + "─" * (WIDE - 2)

    def _explain_one(row_orig: pd.Series, row_adj: pd.Series) -> None:
        name    = row_orig.get("name", "?")
        ptype   = row_orig.get("_type", "hitter")
        fpos    = row_orig.get("_fpos") or "?"
        sig     = str(row_orig.get("verdict", "Neutral"))
        repl    = _REPL_LEVELS.get(fpos)
        n_repl  = DEFAULT_ROSTER_N.get(fpos, "?")

        print()
        print(f"  {name}  [{fpos}  |  {sig}]")
        print(LINE)

        # Step 1: model projected stats (already contain LUCK_MULTIPLIERS from stat_projections.py)
        print("  Step 1 — Model projections  (projections_2026.csv, signal-informed):")
        v_low = sig.lower()
        if "sell high" in v_low:
            note = "  [in-model: R/RBI ×0.94, SB ×0.95, AVG ×0.94 already applied]"
        elif "slight sell" in v_low:
            note = "  [in-model: R/RBI ×0.97, SB ×0.98, AVG ×0.97 already applied]"
        elif "buy low" in v_low:
            note = "  [in-model: R/RBI ×1.06, HR ×1.08, SB ×1.05 already applied]"
        elif "slight buy" in v_low or "buy" in v_low:
            note = "  [in-model: R/RBI ×1.03, HR ×1.04, SB ×1.02 already applied]"
        else:
            note = ""

        if ptype == "hitter":
            print(f"           R {_fmt(row_orig.get('proj_r'))}  HR {_fmt(row_orig.get('proj_hr'))}"
                  f"  RBI {_fmt(row_orig.get('proj_rbi'))}  SB {_fmt(row_orig.get('proj_sb'))}"
                  f"  AVG {_fmt(row_orig.get('proj_avg'), 3)}{note}")
        else:
            print(f"           W {_fmt(row_orig.get('proj_w'))}  ERA {_fmt(row_orig.get('proj_era'), 2)}"
                  f"  WHIP {_fmt(row_orig.get('proj_whip'), 2)}  K {_fmt(row_orig.get('proj_k'))}"
                  f"  SV+H {_fmt(row_orig.get('proj_sv_h'))}{note}")

        # Step 2: trade-tool signal multipliers (Backtest B v2)
        print("  Step 2 — Trade-tool signal adjustment  (Backtest B v2 multipliers):")
        table = _H_SIGNAL_MULTS if ptype == "hitter" else _P_SIGNAL_MULTS
        mults_applied: Optional[dict] = None
        for tier, m in table.items():
            if tier in v_low:
                mults_applied = m
                break

        if mults_applied:
            mult_parts = [f"{k.replace('proj_', '')} ×{v:.2f}" for k, v in mults_applied.items()]
            print(f"           Applied: {',  '.join(mult_parts)}")
            if ptype == "hitter":
                print(f"           Adjusted: R {_fmt(row_adj.get('proj_r'), 1)}"
                      f"  HR {_fmt(row_adj.get('proj_hr'), 1)}"
                      f"  RBI {_fmt(row_adj.get('proj_rbi'), 1)}"
                      f"  SB {_fmt(row_adj.get('proj_sb'), 1)}"
                      f"  AVG {_fmt(row_adj.get('proj_avg'), 3)}")
            else:
                print(f"           Adjusted: W {_fmt(row_adj.get('proj_w'), 1)}"
                      f"  ERA {_fmt(row_adj.get('proj_era'), 2)}"
                      f"  WHIP {_fmt(row_adj.get('proj_whip'), 2)}"
                      f"  K {_fmt(row_adj.get('proj_k'), 1)}"
                      f"  SV+H {_fmt(row_adj.get('proj_sv_h'), 1)}")
        else:
            print(f"           Signal: {sig} — no trade-tool adjustments applied")

        # Step 3: CBS FPTS with per-term breakdown
        print("  Step 3 — CBS Fantasy Points  (signal-adjusted projections × coefficients):")

        def _fv(col: str) -> Optional[float]:
            v = row_adj.get(col)
            try:
                f = float(v)
                return f if f == f else None
            except (TypeError, ValueError):
                return None

        if ptype == "hitter":
            r, hr, rbi, sb, avg = _fv("proj_r"), _fv("proj_hr"), _fv("proj_rbi"), _fv("proj_sb"), _fv("proj_avg")
            if None not in (r, hr, rbi, sb, avg):
                fpts = (CBS_H_COEF_R * r + CBS_H_COEF_HR * hr + CBS_H_COEF_RBI * rbi
                        + CBS_H_COEF_SB * sb + CBS_H_COEF_AVG * avg + CBS_H_INTERCEPT)
                print(f"           R   {r:>6.1f} × {CBS_H_COEF_R:>8.4f}  =  {r * CBS_H_COEF_R:>8.1f}")
                print(f"           HR  {hr:>6.1f} × {CBS_H_COEF_HR:>8.4f}  =  {hr * CBS_H_COEF_HR:>8.1f}")
                print(f"           RBI {rbi:>6.1f} × {CBS_H_COEF_RBI:>8.4f}  =  {rbi * CBS_H_COEF_RBI:>8.1f}")
                print(f"           SB  {sb:>6.1f} × {CBS_H_COEF_SB:>8.4f}  =  {sb * CBS_H_COEF_SB:>8.1f}")
                print(f"           AVG {avg:>6.3f} × {CBS_H_COEF_AVG:>8.2f}  =  {avg * CBS_H_COEF_AVG:>8.1f}")
                print(f"           Intercept                   =  {CBS_H_INTERCEPT:>8.1f}")
                print(f"           {'─'*40}")
                print(f"           Total FPTS                  =  {fpts:>8.1f}")
            else:
                fpts = None
                print("           (insufficient projection data)")
        else:
            w, era, whip, k, sv = _fv("proj_w"), _fv("proj_era"), _fv("proj_whip"), _fv("proj_k"), _fv("proj_sv_h")
            if None not in (w, era, whip, k, sv):
                fpts = (CBS_P_COEF_W * w + CBS_P_COEF_ERA * era + CBS_P_COEF_WHIP * whip
                        + CBS_P_COEF_K * k + CBS_P_COEF_SV * sv + CBS_P_INTERCEPT)
                print(f"           W    {w:>6.1f} × {CBS_P_COEF_W:>8.4f}  =  {w * CBS_P_COEF_W:>8.1f}")
                print(f"           ERA  {era:>6.2f} × {CBS_P_COEF_ERA:>8.4f}  =  {era * CBS_P_COEF_ERA:>8.1f}")
                print(f"           WHIP {whip:>6.2f} × {CBS_P_COEF_WHIP:>8.2f}  =  {whip * CBS_P_COEF_WHIP:>8.1f}")
                print(f"           K    {k:>6.1f} × {CBS_P_COEF_K:>8.4f}  =  {k * CBS_P_COEF_K:>8.1f}")
                print(f"           SV+H {sv:>6.1f} × {CBS_P_COEF_SV:>8.4f}  =  {sv * CBS_P_COEF_SV:>8.1f}")
                print(f"           Intercept                   =  {CBS_P_INTERCEPT:>8.1f}")
                print(f"           {'─'*40}")
                print(f"           Total FPTS                  =  {fpts:>8.1f}")
            else:
                fpts = None
                print("           (insufficient projection data)")

        # Step 4: positional surplus
        print("  Step 4 — Positional Surplus:")
        if fpts is not None and repl is not None:
            s = fpts - repl
            print(f"           Position: {fpos}  |  Replacement: {repl:.1f} FPTS  (N={n_repl}, 12-team standard)")
            print(f"           Surplus = {fpts:.1f} − {repl:.1f} = {s:+.1f}")
            if s < 0:
                print(f"           [Model projects player BELOW typical {fpos} starter on ROS basis]")
        else:
            print(f"           Position: {fpos}  |  Replacement data unavailable")

    # --- Print each player ---
    print()
    print(SEP)
    print("  DETAILED VALUATION WALKTHROUGH")
    print(SEP)

    print()
    print(f"  GIVING ({len(give_rows)} player{'s' if len(give_rows) > 1 else ''}):")
    for row_o, row_a in zip(give_rows, give_adj):
        _explain_one(row_o, row_a)

    print()
    print(f"  GETTING ({len(get_rows)} player{'s' if len(get_rows) > 1 else ''}):")
    for row_o, row_a in zip(get_rows, get_adj):
        _explain_one(row_o, row_a)

    # --- Verdict summary ---
    print()
    print(SEP)
    print("  VERDICT SUMMARY")
    print(SEP)
    for row, surp, adj in zip(give_rows, give_surplus_vals, give_adj):
        nm   = row.get("name", "?")
        fpos = row.get("_fpos") or "?"
        repl = _REPL_LEVELS.get(fpos)
        sv   = f"{surp:+.1f}" if surp is not None else "N/A"
        rl   = f"{repl:.0f}" if repl is not None else "?"
        print(f"  Give  {nm:<24s} {sv:>6s}  ({fpos}, repl {rl})")
    for row, surp, adj in zip(get_rows, get_surplus_vals, get_adj):
        nm   = row.get("name", "?")
        fpos = row.get("_fpos") or "?"
        repl = _REPL_LEVELS.get(fpos)
        sv   = f"{surp:+.1f}" if surp is not None else "N/A"
        rl   = f"{repl:.0f}" if repl is not None else "?"
        print(f"  Get   {nm:<24s} {sv:>6s}  ({fpos}, repl {rl})")
    print()
    sg  = f"{give_surplus_total:+.1f}" if give_surplus_total is not None else "N/A"
    sge = f"{get_surplus_total:+.1f}"  if get_surplus_total  is not None else "N/A"
    sd  = f"{surplus_delta:+.1f}"      if surplus_delta      is not None else "N/A"
    print(f"  {'Give total surplus:':30s} {sg}")
    print(f"  {'Get  total surplus:':30s} {sge}")
    print(f"  {'Surplus delta:':30s} {sd}")
    print()
    print(f"  ➤  {verdict}")
    print(SEP)


def _analyze_and_display(give_rows: list[pd.Series], get_rows: list[pd.Series],
                         config: dict, explain: bool = False) -> str:
    """Display full trade analysis and return verdict string."""
    # --- GIVING side ---
    print()
    print(THIN)
    side_label = f"GIVING ({len(give_rows)} player{'s' if len(give_rows)>1 else ''})"
    print(f"  {side_label}")
    print(THIN)
    for row in give_rows:
        _display_player(row, config)
        if len(give_rows) > 1:
            print()

    # --- GETTING side ---
    print()
    print(THIN)
    side_label = f"GETTING ({len(get_rows)} player{'s' if len(get_rows)>1 else ''})"
    print(f"  {side_label}")
    print(THIN)
    for row in get_rows:
        _display_player(row, config)
        if len(get_rows) > 1:
            print()

    # --- Luck scores (informational context only — not verdict inputs) ---
    give_score = _aggregate_score(give_rows)
    get_score  = _aggregate_score(get_rows)
    raw_luck_delta = get_score - give_score

    # --- Step 2: Apply signal multipliers to projected stats ---
    give_adj = [_apply_signal_multipliers(r) for r in give_rows]
    get_adj  = [_apply_signal_multipliers(r) for r in get_rows]

    # --- Step 3: CBS FPTS on signal-adjusted projections ---
    give_fpts_vals = [_compute_cbs_fpts(r) for r in give_adj]
    get_fpts_vals  = [_compute_cbs_fpts(r) for r in get_adj]
    give_fpts_non_none = [v for v in give_fpts_vals if v is not None]
    get_fpts_non_none  = [v for v in get_fpts_vals  if v is not None]
    give_fpts_total = sum(give_fpts_non_none) if give_fpts_non_none else None
    get_fpts_total  = sum(get_fpts_non_none)  if get_fpts_non_none  else None

    # --- Step 4: Surplus vs replacement level ---
    give_surplus_vals = [
        get_surplus(_compute_cbs_fpts(r), r.get("_fpos"), _REPL_LEVELS) for r in give_adj
    ]
    get_surplus_vals = [
        get_surplus(_compute_cbs_fpts(r), r.get("_fpos"), _REPL_LEVELS) for r in get_adj
    ]
    give_surplus_non_none = [v for v in give_surplus_vals if v is not None]
    get_surplus_non_none  = [v for v in get_surplus_vals  if v is not None]
    give_surplus_total = sum(give_surplus_non_none) if give_surplus_non_none else None
    get_surplus_total  = sum(get_surplus_non_none)  if get_surplus_non_none  else None

    # --- Step 5: Verdict = surplus delta ---
    if give_surplus_total is not None and get_surplus_total is not None:
        surplus_delta: Optional[float] = get_surplus_total - give_surplus_total
    elif give_fpts_total is not None and get_fpts_total is not None:
        surplus_delta = get_fpts_total - give_fpts_total  # FPTS fallback (no pos data)
    else:
        surplus_delta = None

    verdict = _trade_verdict_v3(surplus_delta)

    # --- Trajectory notes (informational — small-sample flags) ---
    trajectory_adj, trajectory_notes = _trajectory_adj(give_rows, get_rows)

    # --- Verdict display ---
    print()
    print(THIN)
    print("  TRADE VERDICT")
    print(THIN)

    give_luck_str = _stat(give_score, dec=3, signed=True)
    get_luck_str  = _stat(get_score,  dec=3, signed=True)
    luck_delta_str = _stat(raw_luck_delta, dec=3, signed=True)
    print(f"  Luck scores     : give {give_luck_str}  |  get {get_luck_str}  |  delta {luck_delta_str}")

    if give_surplus_total is not None and get_surplus_total is not None:
        note = "value edge incoming" if surplus_delta >= 0 else "value edge outgoing"

        def _surplus_breakdown(rows: list, surplus_vals: list) -> str:
            parts = []
            for row, sv in zip(rows, surplus_vals):
                nm   = row.get("name", "?")
                fpos = row.get("_fpos") or "?"
                repl = _REPL_LEVELS.get(fpos)
                repl_str = f"repl {repl:.0f}" if repl is not None else "repl ?"
                sv_str = f"{sv:+.0f}" if sv is not None else "N/A"
                parts.append(f"{nm} {sv_str} ({fpos}, {repl_str})")
            return "  |  ".join(parts)

        give_bk = _surplus_breakdown(give_adj, give_surplus_vals)
        get_bk  = _surplus_breakdown(get_adj,  get_surplus_vals)
        print(f"  Give surplus    : {give_bk}")
        print(f"  Get  surplus    : {get_bk}")
        print(f"  Surplus delta   : {surplus_delta:+.0f}  ({note})")
    elif give_fpts_total is not None or get_fpts_total is not None:
        gf  = f"{give_fpts_total:.0f}" if give_fpts_total is not None else "N/A"
        gf2 = f"{get_fpts_total:.0f}"  if get_fpts_total  is not None else "N/A"
        print(f"  Adj FPTS        : give {gf}  |  get {gf2}")

    if trajectory_notes:
        print()
        print("  Notes:")
        for note in trajectory_notes:
            print(note)

    print()
    print(f"  ➤  {verdict}")
    print(THIN)

    if explain:
        _explain_walkthrough(
            give_rows, get_rows,
            give_adj, get_adj,
            give_surplus_vals, get_surplus_vals,
            give_surplus_total, get_surplus_total,
            surplus_delta, verdict,
        )

    return verdict


# ---------------------------------------------------------------------------
# Trade history
# ---------------------------------------------------------------------------

_HISTORY_COLS = ["date", "giving", "getting", "give_score", "get_score",
                 "scarcity_adj", "trajectory_adj", "verdict"]


def _log_trade(give_rows: list[pd.Series], get_rows: list[pd.Series],
               verdict: str, config: dict) -> None:
    HISTORY_PATH.parent.mkdir(exist_ok=True)
    give_names = "; ".join(r.get("name", "?") for r in give_rows)
    get_names  = "; ".join(r.get("name", "?") for r in get_rows)
    give_score = round(_aggregate_score(give_rows), 4)
    get_score  = round(_aggregate_score(get_rows),  4)
    # TODO: Re-enable when league settings import is live (Phase B2)
    # scarcity_adj, _ = _scarcity_adj(give_rows, get_rows, config)
    scarcity_adj = 0.0
    trajectory_adj, _ = _trajectory_adj(give_rows, get_rows)

    write_header = not HISTORY_PATH.exists()
    with open(HISTORY_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_HISTORY_COLS)
        if write_header:
            writer.writeheader()
        writer.writerow({
            "date":           date.today().isoformat(),
            "giving":         give_names,
            "getting":        get_names,
            "give_score":     give_score,
            "get_score":      get_score,
            "scarcity_adj":   round(scarcity_adj, 4),
            "trajectory_adj": round(trajectory_adj, 4),
            "verdict":        verdict,
        })


def _show_history(n: int = 20) -> None:
    if not HISTORY_PATH.exists():
        print("  No trade history found.")
        return
    df = pd.read_csv(HISTORY_PATH)
    df = df.tail(n)
    print()
    print(DIVIDER)
    print(f"  TRADE HISTORY (last {min(n, len(df))} entries)")
    print(DIVIDER)
    for _, row in df.iterrows():
        delta = round(float(row["get_score"]) - float(row["give_score"]) +
                      float(row.get("scarcity_adj", 0)) +
                      float(row.get("trajectory_adj", 0)), 3)
        delta_str = f"{delta:+.3f}"
        print(f"  {row['date']}  |  {row['giving']:25s}  →  {row['getting']:25s}  |  delta {delta_str}  |  {row['verdict']}")
    print()


# ---------------------------------------------------------------------------
# Interactive loop
# ---------------------------------------------------------------------------

def _print_header(config: dict) -> None:
    print()
    print(DIVIDER)
    print("  SIGNAL FANTASY TRADE ANALYZER  v2")
    print(DIVIDER)
    _print_config(config)
    print(f"  (Enter player names comma-separated for multi-player trades)")
    print(f"  (Append [POS] tag like 'Salvador Perez [C]' for scarcity context)")


def analyze_trade(players: pd.DataFrame, config: dict, explain: bool = False) -> None:
    _print_header(config)
    if explain:
        print("  [--explain mode: full valuation walkthrough will follow each verdict]")
    while True:
        print()
        give_input = input("  Players you're GIVING (comma-separated, or 'quit'): ").strip()
        if give_input.lower() in ("q", "quit", "exit"):
            break

        give_rows = _parse_side(give_input, players, "Giving")
        if not give_rows:
            continue

        get_input = input("  Players you're GETTING (comma-separated): ").strip()
        if get_input.lower() in ("q", "quit", "exit"):
            break

        get_rows = _parse_side(get_input, players, "Getting")
        if not get_rows:
            continue

        verdict = _analyze_and_display(give_rows, get_rows, config, explain=explain)
        _log_trade(give_rows, get_rows, verdict, config)

        again = input("\n  Analyze another trade? (Y/N): ").strip().lower()
        if again not in ("y", "yes"):
            break

    print("\n  Thanks for using The Signal Fantasy Trade Analyzer.")


# ---------------------------------------------------------------------------
# Non-interactive test suite
# ---------------------------------------------------------------------------

_TEST_CASES = [
    # (give_names_csv, get_names_csv, description)
    (
        "Jesus Luzardo",
        "Jose Soriano",
        "Test 1 — SP buy-low for SP sell-high (should be AVOID)",
    ),
    (
        "Jose Soriano",
        "Jesus Luzardo",
        "Test 2 — SP sell-high for SP buy-low (should be STRONG TRADE)",
    ),
    (
        "Jose Soriano, Michael Wacha",
        "Jesus Luzardo, Joe Ryan",
        "Test 3 — 2v2: two sell-highs for two buy-lows",
    ),
    (
        "Aaron Judge",
        "Jesus Luzardo",
        "Test 4 — Hitter (no strong signal) for SP buy-low",
    ),
]


def run_tests(players: pd.DataFrame, config: dict) -> None:
    print()
    print(DIVIDER)
    print("  TRADE ANALYZER — Test Suite (4 cases)")
    print(DIVIDER)

    results = []
    for i, (give_csv, get_csv, desc) in enumerate(_TEST_CASES, 1):
        print(f"\n{'─'*65}")
        print(f"  {desc}")
        print(f"{'─'*65}")

        give_rows = []
        for name in give_csv.split(","):
            row = _resolve_player_silent(name.strip(), players)
            if row is not None:
                give_rows.append(row)

        get_rows = []
        for name in get_csv.split(","):
            row = _resolve_player_silent(name.strip(), players)
            if row is not None:
                get_rows.append(row)

        if not give_rows or not get_rows:
            print(f"  SKIP — could not resolve all players ({give_csv} | {get_csv})")
            results.append((i, desc, "SKIP"))
            continue

        verdict = _analyze_and_display(give_rows, get_rows, config)
        _log_trade(give_rows, get_rows, verdict, config)
        results.append((i, desc, verdict))

    print()
    print(DIVIDER)
    print("  TEST SUMMARY")
    print(DIVIDER)
    for idx, desc, v in results:
        status = "PASS" if v != "SKIP" else "SKIP"
        print(f"  [{status}]  Test {idx}: {v}")
    print()


def _resolve_player_silent(name: str, players: pd.DataFrame) -> Optional[pd.Series]:
    """Non-interactive resolve — returns first match or None, no prompts."""
    clean, user_pos = _strip_pos_tag(name)
    rows = _fuzzy_find(clean, players)
    if rows.empty:
        print(f"  [warn] Player not found: '{clean}'")
        return None
    row = rows.iloc[0].copy()
    if user_pos:
        row["_user_pos"] = user_pos
    return row


# ---------------------------------------------------------------------------
# Public API — trade_value() and evaluate_trade()
# ---------------------------------------------------------------------------

def trade_value(player_name: str, league_id: int = 1) -> dict:
    """Return signal-adjusted surplus value for a single player.

    Returns dict with keys:
        name, signal, luck_score, surplus, signal_adjusted_surplus,
        fpts, position, perceived_value_rank
    Returns None if player not found.
    """
    players = _load_players()
    config  = load_config()
    row = _resolve_player_silent(player_name, players)
    if row is None:
        return {"error": f"Player not found: {player_name}"}

    adj_row   = _apply_signal_multipliers(row)
    fpts      = _compute_cbs_fpts(adj_row)
    fpos      = adj_row.get("_fpos")
    surplus   = get_surplus(fpts, fpos, _REPL_LEVELS)

    luck      = float(row.get("luck_score", 0.0) or 0.0)
    verdict   = str(row.get("verdict", "Neutral")).lower()
    if "buy low" in verdict:
        adj_surplus = surplus * (1 + luck * 0.5) if surplus is not None else None
    elif "sell high" in verdict:
        adj_surplus = surplus * (1 - abs(luck) * 0.5) if surplus is not None else None
    else:
        adj_surplus = surplus

    return {
        "name":                    row.get("name", player_name),
        "signal":                  row.get("verdict", "Neutral"),
        "luck_score":              round(luck, 4),
        "position":                fpos or row.get("_fpos", "?"),
        "fpts":                    round(fpts, 1) if fpts is not None else None,
        "surplus":                 round(surplus, 1) if surplus is not None else None,
        "signal_adjusted_surplus": round(adj_surplus, 1) if adj_surplus is not None else None,
    }


def evaluate_trade(
    side_a_players: list[str],
    side_b_players: list[str],
    league_id: int = 1,
) -> dict:
    """Programmatic trade evaluator. Returns verdict + per-player breakdown.

    side_a_players — players YOU are giving up
    side_b_players — players YOU are receiving
    Returns dict with verdict, side_a, side_b, surplus_delta.
    """
    players = _load_players()
    config  = load_config()

    give_rows = [_resolve_player_silent(n, players) for n in side_a_players]
    get_rows  = [_resolve_player_silent(n, players) for n in side_b_players]
    give_rows = [r for r in give_rows if r is not None]
    get_rows  = [r for r in get_rows  if r is not None]

    if not give_rows or not get_rows:
        return {"error": "One or more players not found"}

    give_adj = [_apply_signal_multipliers(r) for r in give_rows]
    get_adj  = [_apply_signal_multipliers(r) for r in get_rows]

    give_surplus_vals = [get_surplus(_compute_cbs_fpts(r), r.get("_fpos"), _REPL_LEVELS) for r in give_adj]
    get_surplus_vals  = [get_surplus(_compute_cbs_fpts(r), r.get("_fpos"), _REPL_LEVELS) for r in get_adj]
    give_total = sum(v for v in give_surplus_vals if v is not None) if any(v is not None for v in give_surplus_vals) else None
    get_total  = sum(v for v in get_surplus_vals  if v is not None) if any(v is not None for v in get_surplus_vals)  else None

    surplus_delta = (get_total - give_total) if (give_total is not None and get_total is not None) else None
    verdict = _trade_verdict_v3(surplus_delta)

    def _side_detail(rows, adj_rows, surplus_vals):
        out = []
        for row, adj, surp in zip(rows, adj_rows, surplus_vals):
            fpts = _compute_cbs_fpts(adj)
            luck = float(row.get("luck_score", 0.0) or 0.0)
            out.append({
                "name":       row.get("name", "?"),
                "signal":     row.get("verdict", "Neutral"),
                "luck_score": round(luck, 4),
                "position":   adj.get("_fpos", "?"),
                "fpts":       round(fpts, 1) if fpts is not None else None,
                "surplus":    round(surp, 1) if surp is not None else None,
            })
        return out

    return {
        "verdict":       verdict,
        "surplus_delta": round(surplus_delta, 1) if surplus_delta is not None else None,
        "give_total":    round(give_total, 1) if give_total is not None else None,
        "get_total":     round(get_total, 1)  if get_total  is not None else None,
        "side_a_giving": _side_detail(give_rows, give_adj, give_surplus_vals),
        "side_b_getting": _side_detail(get_rows, get_adj, get_surplus_vals),
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Signal Fantasy Trade Analyzer v2")
    parser.add_argument("--setup",             action="store_true", help="Configure league settings")
    parser.add_argument("--test",              action="store_true", help="Run non-interactive test suite")
    parser.add_argument("--history",           action="store_true", help="Show trade history")
    parser.add_argument("--replacement-table", action="store_true", help="Show replacement level table")
    parser.add_argument("--explain",           action="store_true",
                        help="Print step-by-step valuation walkthrough (CBS coefs, surplus calc) after each verdict")
    parser.add_argument("--give",    nargs="+", metavar="PLAYER",
                        help="Players you are giving (non-interactive mode)")
    parser.add_argument("--receive", nargs="+", metavar="PLAYER",
                        help="Players you are receiving (non-interactive mode)")
    parser.add_argument("--league",  type=int, default=1, metavar="ID",
                        help="League config ID (default 1)")
    parser.add_argument("--open-slot", action="store_true",
                        help="Receiving side has an open roster slot — no opportunity cost applied")
    parser.add_argument("--debug", action="store_true",
                        help="Show per-player surplus breakdown: base → signal_adj → elite_adj")
    args = parser.parse_args()

    # Provide a clear error when only one side is specified
    if (args.give and not args.receive) or (args.receive and not args.give):
        missing = "--receive" if args.give else "--give"
        print(f"\n  Error: {missing} is required when using non-interactive mode.")
        print("  Usage: python trade_analyzer.py --give PLAYER --receive PLAYER [PLAYER ...]")
        return

    # Non-interactive --give / --receive mode
    if args.give and args.receive:
        league_json  = _load_league_json(args.league)
        roster_n     = _compute_roster_n(league_json)
        repl_levels  = load_replacement_levels(roster_n)
        league_name  = league_json.get("league_name", f"League {args.league}")

        try:
            players = _load_players()
        except FileNotFoundError as exc:
            print(f"  Error: {exc}")
            return

        give_rows_raw = [_resolve_player_silent(n, players) for n in args.give]
        get_rows_raw  = [_resolve_player_silent(n, players) for n in args.receive]

        # Clear error on any unresolved player
        missing_give = [n for n, r in zip(args.give,    give_rows_raw) if r is None]
        missing_get  = [n for n, r in zip(args.receive, get_rows_raw)  if r is None]
        if missing_give or missing_get:
            print()
            for name in missing_give + missing_get:
                print(f"  Player not found: {name}")
                suggestions = _suggest_player(name, players, top_n=2)
                if suggestions:
                    for s in suggestions:
                        team_str = f" ({s['team']})" if s.get("team") else ""
                        print(f"  Did you mean: {s['name']}{team_str}?")
                print("  Check spelling or try last name only.")
            return

        give_rows = [r for r in give_rows_raw if r is not None]
        get_rows  = [r for r in get_rows_raw  if r is not None]

        # Duplicate detection: same player on both sides
        give_ids = {r.get("id") or r.get("batter") or r.get("pitcher") for r in give_rows}
        get_ids  = {r.get("id") or r.get("batter") or r.get("pitcher") for r in get_rows}
        overlap  = give_ids & get_ids
        if overlap:
            overlap_names = [r.get("name","?") for r in give_rows + get_rows
                             if (r.get("id") or r.get("batter") or r.get("pitcher")) in overlap]
            print(f"\n  Error: {overlap_names[0] if overlap_names else 'A player'} appears on both sides of the trade.")
            print("  A trade must have different players on each side.")
            return

        # Cross-type advisory (hitter-for-pitcher mismatch, allowed but worth noting)
        give_types = {r.get("_type","hitter") for r in give_rows}
        get_types  = {r.get("_type","hitter") for r in get_rows}
        if give_types != get_types and len(give_rows) == 1 and len(get_rows) == 1:
            print(f"\n  ℹ  Cross-type trade: giving a {next(iter(give_types))} for a {next(iter(get_types))}.")
            print("     Surplus compares each player to their own position pool. Analysis proceeds.")
            print()

        give_adj = [_apply_signal_multipliers(r) for r in give_rows]
        get_adj  = [_apply_signal_multipliers(r) for r in get_rows]

        give_fpts_vals = [_compute_cbs_fpts_league(r, league_json) for r in give_adj]
        get_fpts_vals  = [_compute_cbs_fpts_league(r, league_json) for r in get_adj]

        give_surplus_vals = [get_surplus(f, r.get("_fpos"), repl_levels)
                             for f, r in zip(give_fpts_vals, give_adj)]
        get_surplus_vals  = [get_surplus(f, r.get("_fpos"), repl_levels)
                             for f, r in zip(get_fpts_vals, get_adj)]

        # --- Elite premium (applied AFTER signal adjustment, to surplus values) ---
        give_elite_surplus = [
            (s * _elite_premium(r.get("fp_rank"))) if s is not None else None
            for s, r in zip(give_surplus_vals, give_rows)
        ]
        get_elite_surplus = [
            (s * _elite_premium(r.get("fp_rank"))) if s is not None else None
            for s, r in zip(get_surplus_vals, get_rows)
        ]
        give_non_none = [v for v in give_elite_surplus if v is not None]
        get_non_none  = [v for v in get_elite_surplus  if v is not None]
        give_total    = sum(give_non_none) if give_non_none else None
        get_total     = sum(get_non_none)  if get_non_none  else None

        # --- Opportunity cost (roster space) ---
        team_count   = league_json.get("team_count", 12)
        net_received = len(get_rows) - len(give_rows)
        opp_cost     = 0.0
        open_slot_flag = getattr(args, 'open_slot', False)
        if net_received > 0 and not open_slot_flag:
            opp_cost = _repl_level_value(team_count) * net_received
            if get_total is not None:
                get_total -= opp_cost

        surplus_delta = (get_total - give_total) if (give_total is not None and get_total is not None) else None
        verdict       = _trade_verdict_v3(surplus_delta)

        # --- Debug table ---
        if getattr(args, 'debug', False):
            _DBG = "-" * 90
            print(f"\n{'=' * 90}")
            print("  DEBUG: Per-Player Surplus Breakdown")
            print(f"{'=' * 90}")
            hdr = f"  {'Side':<5} {'Name':<22} {'FP':>4} {'EP':>5} {'Signal':<14} {'Luck':>7} {'BaseSurp':>9} {'SigAdj':>8} {'EliteAdj':>9}"
            print(hdr)
            print(f"  {_DBG}")

            def _dbg_row(side: str, orig_row, surp, elite_surp):
                name    = str(orig_row.get("name", "?"))[:21]
                fp_rank = orig_row.get("fp_rank")
                ep      = _elite_premium(fp_rank)
                fp_str  = f"{int(float(fp_rank))}" if fp_rank not in (None, "", "nan") and str(fp_rank) != "nan" else "—"
                sig     = str(orig_row.get("verdict", "Neutral"))[:13]
                luck    = float(orig_row.get("luck_score", 0.0) or 0.0)
                # signal-adjusted surplus for display (same formula used in _print_trade_player)
                if surp is not None:
                    if "buy" in sig.lower():
                        sadj = surp * (1 + luck * 0.5)
                    elif "sell" in sig.lower():
                        sadj = surp * (1 - abs(luck) * 0.5)
                    else:
                        sadj = surp
                else:
                    sadj = None
                b_str  = f"{surp:+.1f}"       if surp is not None       else "N/A"
                sa_str = f"{sadj:+.1f}"        if sadj is not None       else "N/A"
                ea_str = f"{elite_surp:+.1f}"  if elite_surp is not None else "N/A"
                ep_str = f"×{ep:.2f}"
                print(f"  {side:<5} {name:<22} {fp_str:>4} {ep_str:>5} {sig:<14} {luck:>+7.3f} {b_str:>9} {sa_str:>8} {ea_str:>9}")

            for orig, surp, esurf in zip(give_rows, give_surplus_vals, give_elite_surplus):
                _dbg_row("GIVE", orig, surp, esurf)
            for orig, surp, esurf in zip(get_rows, get_surplus_vals, get_elite_surplus):
                _dbg_row("GET", orig, surp, esurf)

            print(f"  {_DBG}")
            give_pre = sum(v for v in give_surplus_vals if v is not None)
            get_pre  = sum(v for v in get_surplus_vals  if v is not None)
            give_ep  = sum(v for v in give_elite_surplus if v is not None)
            get_ep   = sum(v for v in get_elite_surplus  if v is not None)
            print(f"  {'GIVE totals:':<30} base={give_pre:+.1f}  →  elite-adjusted={give_ep:+.1f}  (Δ {give_ep-give_pre:+.1f})")
            print(f"  {'GET totals (before opp cost):':<30} base={get_pre:+.1f}  →  elite-adjusted={get_ep:+.1f}  (Δ {get_ep-get_pre:+.1f})")
            if opp_cost:
                print(f"  {'Opportunity cost:':<30} -{opp_cost:.1f} applied to GET side")
                print(f"  {'GET final:':<30} {get_ep - opp_cost:+.1f}")
            delta_base  = get_pre  - give_pre
            delta_elite = (get_ep - opp_cost) - give_ep
            print(f"  {'Delta (base, no premium):':<30} {delta_base:+.1f}")
            print(f"  {'Delta (elite+opp_cost):':<30} {delta_elite:+.1f}  ({delta_elite - delta_base:+.1f} from elite premium)")
            print(f"  Directionality: GIVE ep={sum(_elite_premium(r.get('fp_rank')) for r in give_rows)/len(give_rows):.3f} avg | "
                  f"GET ep={sum(_elite_premium(r.get('fp_rank')) for r in get_rows)/len(get_rows):.3f} avg")
            print(f"  Giving a higher-ranked player INCREASES give_total → SHRINKS delta. "
                  f"Receiving a higher-ranked player INCREASES get_total → GROWS delta.")
            print(f"{'=' * 90}\n")

        W = 65
        D = "═" * W
        config = load_config()
        print()
        print(D)
        print(f"  THE SIGNAL FANTASY — TRADE ANALYZER  [{league_name}]")
        print(D)

        def _print_trade_player(orig_row: pd.Series, adj_row: pd.Series,
                                surp: Optional[float], elite_surp: Optional[float] = None) -> None:
            name  = orig_row.get("name", "?")
            team  = orig_row.get("Team", orig_row.get("team", "?"))
            pos   = orig_row.get("_fpos") or _derive_pos(orig_row) or "?"
            sig   = str(orig_row.get("verdict", "Neutral"))
            luck  = float(orig_row.get("luck_score", 0.0) or 0.0)
            ptype = orig_row.get("_type", "hitter")
            desc  = _signal_desc(sig, ptype)
            luck_str = f"{luck:+.3f}"
            surp_str = f"{surp:+.0f}" if surp is not None else "N/A"
            # Signal-adjusted surplus (display only — same logic as in totals)
            if "buy low" in sig.lower() and surp is not None:
                adj_s    = surp * (1.0 + luck * 0.5)
                diff_str = f"{adj_s - surp:+.0f}"
                adj_str  = f"{adj_s:+.0f} ({diff_str})"
            elif "sell high" in sig.lower() and surp is not None:
                adj_s    = surp * (1.0 - abs(luck) * 0.5)
                diff_str = f"{adj_s - surp:+.0f}"
                adj_str  = f"{adj_s:+.0f} ({diff_str})"
            else:
                adj_str  = surp_str
            # Short-sample flag
            try:
                short = float(orig_row.get("career_pa", 9999)) < 300
            except (TypeError, ValueError):
                short = False
            short_note = "  ⚠ Short baseline (<300 career PA)" if short else ""
            print(f"  {name} ({pos}, {team}){short_note}")
            print(f"  Signal: {sig} ({luck_str})")
            print(f"    {desc}")
            print(f"  Surplus: {surp_str}  |  Signal-adjusted: {adj_str}")
            # Elite tier display
            fp_rank = orig_row.get("fp_rank")
            ep = _elite_premium(fp_rank)
            if ep > 1.00:
                try:
                    fp_str = f"FP #{int(float(fp_rank))}"
                except (TypeError, ValueError):
                    fp_str = "Elite ranked"
                if ep >= 1.30:
                    tier_str = "top-10 overall"
                elif ep >= 1.15:
                    tier_str = "top-25 overall"
                else:
                    tier_str = "top-50 overall"
                ep_str = f"{elite_surp:+.0f}" if elite_surp is not None else "N/A"
                print(f"  Elite tier: {fp_str} ({tier_str}) — scarcity premium ×{ep:.2f}  |  Elite-adjusted: {ep_str}")

        print()
        print("  YOU GIVE:")
        print(f"  {'─' * 57}")
        for orig, adj, surp, esurf in zip(give_rows, give_adj, give_surplus_vals, give_elite_surplus):
            _print_trade_player(orig, adj, surp, esurf)
            print()

        print("  YOU RECEIVE:")
        print(f"  {'─' * 57}")
        for orig, adj, surp, esurf in zip(get_rows, get_adj, get_surplus_vals, get_elite_surplus):
            _print_trade_player(orig, adj, surp, esurf)
            print()

        # Roster impact (only when player counts differ)
        if net_received != 0:
            print("  ROSTER IMPACT:")
            print(f"  {'─' * 57}")
            give_n = len(give_rows)
            get_n  = len(get_rows)
            print(f"  You give {give_n} player{'s' if give_n > 1 else ''}, receive {get_n}.")
            if net_received > 0:
                if open_slot_flag:
                    print(f"  Open roster slot detected — no opportunity cost applied.")
                else:
                    drops = net_received
                    print(f"  You must drop {drops} player{'s' if drops > 1 else ''} to make roster room.")
                    print(f"  Estimated opportunity cost: -{opp_cost:.1f} surplus points")
                    print(f"  ({team_count}-team league replacement level: {_repl_level_value(team_count):.1f} pts/player)")
                    get_before_opp = get_total + opp_cost if get_total is not None else None
                    if get_before_opp is not None:
                        print(f"  Your adjusted get total: {get_before_opp:+.1f} → {get_total:+.1f} after opportunity cost")
            else:
                n_partner_drops = abs(net_received)
                partner_cost = _repl_level_value(team_count) * n_partner_drops
                print(f"  Your trade partner must drop {n_partner_drops} player{'s' if n_partner_drops > 1 else ''} to make room.")
                print(f"  Their opportunity cost: ~{partner_cost:.1f} surplus points (not applied to this analysis).")
            print()

        # Totals + verdict
        # Check if any elite premium was applied (for label clarity)
        any_elite = any(
            _elite_premium(r.get("fp_rank")) > 1.00
            for r in give_rows + get_rows
        )
        elite_note = "  (includes elite scarcity premium where applicable)" if any_elite else ""

        g_str = f"{give_total:+.1f}" if give_total is not None else "N/A"
        r_str = f"{get_total:+.1f}"  if get_total  is not None else "N/A"
        d_str = f"{surplus_delta:+.1f}" if surplus_delta is not None else "N/A"
        print(D)
        print()
        print(f"  VERDICT: {verdict}")
        print(f"  Give total: {g_str}  |  Get total: {r_str}  |  Delta: {d_str}")
        if elite_note:
            print(f"  {elite_note}")

        # Signal context warnings + elite qualitative warnings
        ctx = _signal_context_warnings(give_rows, get_rows)
        print()
        print("  SIGNAL CONTEXT:")
        if ctx:
            for line in ctx:
                print(line)
        else:
            print("  No active luck signals on either side — evaluate on surplus value alone.")

        # Elite player qualitative warnings
        for row in give_rows:
            fp_rank = row.get("fp_rank")
            ep = _elite_premium(fp_rank)
            if ep >= 1.15:
                try:
                    rank_str = f"FP #{int(float(fp_rank))}"
                except (TypeError, ValueError):
                    rank_str = "Elite tier"
                name = row.get("name", "?")
                print()
                print(f"  ⚠  You are giving up a top-25 overall player ({name}, {rank_str}).")
                print(f"     Elite players carry a scarcity premium beyond raw surplus. They are")
                print(f"     difficult to replace from the waiver wire and provide maximum trade")
                print(f"     optionality. Consider whether the aggregate production gain justifies")
                print(f"     losing elite-tier flexibility.")

        if open_slot_flag and net_received > 0:
            print()
            print(f"  ℹ  Open roster slot — no opportunity cost applied to this analysis.")

        print()
        print(D)
        return

    if args.setup:
        setup_league_config()
        return

    if args.history:
        _show_history()
        return

    if args.replacement_table:
        print()
        print(DIVIDER)
        print("  REPLACEMENT LEVEL TABLE (12-team standard)")
        print(DIVIDER)
        print(build_replacement_table())
        print()
        for pos, fpts in sorted(_REPL_LEVELS.items()):
            print(f"  {pos:4s} replacement FPTS: {fpts:.1f}")
        print()
        return

    config = load_config()

    print("\nLoading luck scores...")
    try:
        players = _load_players()
        n_h = (players["_type"] == "hitter").sum()
        n_p = (players["_type"] == "pitcher").sum()
        print(f"  Loaded {len(players):,} players ({n_h} hitters, {n_p} pitchers).")
    except FileNotFoundError as exc:
        print(f"Error: {exc}")
        sys.exit(1)

    if args.test:
        run_tests(players, config)
        return

    analyze_trade(players, config, explain=args.explain)


if __name__ == "__main__":
    main()
