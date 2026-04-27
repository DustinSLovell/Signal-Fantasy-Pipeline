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
)

BASE_DIR      = Path(__file__).parent
HITTER_CSV    = BASE_DIR / "luck_scores.csv"
PITCHER_CSV   = BASE_DIR / "pitcher_luck_scores.csv"
PROJ_CSV      = BASE_DIR / "data" / "projections_2026.csv"
CONFIG_PATH   = BASE_DIR / "data" / "league_config.json"
HISTORY_PATH  = BASE_DIR / "data" / "trade_history.csv"

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
        # GS column is typically NaN; use IP-per-appearance from total_starts
        ip = row.get("IP", 0)
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
        pid = row.get("batter") if row.get("_type") == "hitter" else row.get("pitcher")
        try:
            fpos = pos_map.get(int(pid)) if pd.notna(pid) else None
        except (TypeError, ValueError):
            fpos = None
        if fpos:
            return fpos
        # Fallback: pitchers use _derive_pos; hitters unknown
        if row.get("_type") == "pitcher":
            return "SP" if _derive_pos(row) == "SP" else "RP"
        return None

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


def _analyze_and_display(give_rows: list[pd.Series], get_rows: list[pd.Series],
                         config: dict) -> str:
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

    # --- Score computation ---
    give_score = _aggregate_score(give_rows)
    get_score  = _aggregate_score(get_rows)
    raw_delta  = get_score - give_score

    # TODO: Re-enable when league settings import is live (Phase B2)
    # scarcity_adj, scarcity_notes = _scarcity_adj(give_rows, get_rows, config)
    scarcity_adj, scarcity_notes = 0.0, []
    trajectory_adj, trajectory_notes = _trajectory_adj(give_rows, get_rows)
    total_delta = raw_delta + scarcity_adj + trajectory_adj

    verdict = _trade_verdict_v2(raw_delta, total_delta)

    # --- CBS FPTS and surplus totals ---
    give_fpts_vals = [_compute_cbs_fpts(r) for r in give_rows]
    get_fpts_vals  = [_compute_cbs_fpts(r) for r in get_rows]
    give_fpts_total = sum(v for v in give_fpts_vals if v is not None) or None
    get_fpts_total  = sum(v for v in get_fpts_vals  if v is not None) or None
    fpts_delta = (get_fpts_total - give_fpts_total) if (give_fpts_total and get_fpts_total) else None

    give_surplus_vals = [
        get_surplus(_compute_cbs_fpts(r), r.get("_fpos"), _REPL_LEVELS) for r in give_rows
    ]
    get_surplus_vals  = [
        get_surplus(_compute_cbs_fpts(r), r.get("_fpos"), _REPL_LEVELS) for r in get_rows
    ]
    give_surplus_total = sum(v for v in give_surplus_vals if v is not None) or None
    get_surplus_total  = sum(v for v in get_surplus_vals  if v is not None) or None
    surplus_delta = (
        (get_surplus_total - give_surplus_total)
        if (give_surplus_total is not None and get_surplus_total is not None)
        else None
    )

    # --- Verdict display ---
    print()
    print(THIN)
    print("  TRADE VERDICT")
    print(THIN)

    give_str = _stat(give_score, dec=3, signed=True)
    get_str  = _stat(get_score,  dec=3, signed=True)
    raw_str  = _stat(raw_delta,  dec=3, signed=True)
    print(f"  Give side score : {give_str}   |   Get side score: {get_str}")
    print(f"  Luck delta      : {raw_str}  (positive = better luck incoming)")

    if surplus_delta is not None:
        sg_str  = f"{give_surplus_total:+.0f}" if give_surplus_total is not None else "N/A"
        sge_str = f"{get_surplus_total:+.0f}"  if get_surplus_total  is not None else "N/A"
        note = "value edge incoming" if surplus_delta >= 0 else "value edge outgoing"
        print(f"  Surplus (give/get): {sg_str} / {sge_str}  |  delta {surplus_delta:+.0f} ({note})")
    elif fpts_delta is not None:
        fpts_give_str = f"{give_fpts_total:.0f}" if give_fpts_total else "N/A"
        fpts_get_str  = f"{get_fpts_total:.0f}"  if get_fpts_total  else "N/A"
        note = "more proj FPTS incoming" if fpts_delta >= 0 else "fewer proj FPTS incoming"
        print(f"  FPTS (give/get) : {fpts_give_str} / {fpts_get_str}  |  delta {fpts_delta:+.0f} ({note})")

    all_notes = scarcity_notes + trajectory_notes
    if all_notes:
        print()
        print("  Adjustments:")
        for note in all_notes:
            print(note)
        total_str = _stat(total_delta, dec=3, signed=True)
        print(f"  Adjusted delta  : {total_str}")

    print()
    print(f"  ➤  {verdict}")
    print(THIN)

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


def analyze_trade(players: pd.DataFrame, config: dict) -> None:
    _print_header(config)
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

        verdict = _analyze_and_display(give_rows, get_rows, config)
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
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Signal Fantasy Trade Analyzer v2")
    parser.add_argument("--setup",             action="store_true", help="Configure league settings")
    parser.add_argument("--test",              action="store_true", help="Run non-interactive test suite")
    parser.add_argument("--history",           action="store_true", help="Show trade history")
    parser.add_argument("--replacement-table", action="store_true", help="Show replacement level table")
    args = parser.parse_args()

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

    analyze_trade(players, config)


if __name__ == "__main__":
    main()
