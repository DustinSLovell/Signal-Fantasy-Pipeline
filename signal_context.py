"""
signal_context.py
=================
Post-processing signal context overrides for The Signal Fantasy.

Does NOT modify score_luck.py or score_pitcher_luck.py (Layer 1 sacred).
Adds context columns to hitter/pitcher DataFrames for display and
confidence-weighting purposes. Two override types:

1. ELITE_TRACK_RECORD (pitchers):
   A pitcher with a multi-year sub-2.50 ERA and Elite quality tier needs
   a larger ERA-FIP gap to justify a Sell High signal. Marginal gaps
   (<0.50) are noise for proven generational talents.

2. INJURY_RECOVERY (hitters + pitchers):
   Players in a known surgical recovery window receive reduced confidence
   weight (0.30). Signal direction may still be valid; timing of resolution
   is uncertain until recovery is complete.

Usage:
    import signal_context as sc
    pitcher_df, downgraded = sc.apply_pitcher_elite_gate(pitcher_df)
    hitter_df  = sc.apply_injury_context(hitter_df)
    pitcher_df = sc.apply_injury_context(pitcher_df, is_pitcher=True)
"""

import json
from datetime import date
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).parent

# ── Gate thresholds ──────────────────────────────────────────────────────────

ELITE_ERA_THRESHOLD  = 2.50   # career 2yr ERA below this = generational talent
ELITE_GAP_REQUIRED   = 0.50   # |ERA - FIP| must exceed this to stand for elite pitchers
ELITE_CONF_WEIGHT    = 0.50   # confidence weight when gap is marginal but not overriding
INJURY_CONF_WEIGHT   = 0.30   # confidence weight for players in recovery window

INJURY_CONTEXT_PATH  = BASE_DIR / "data" / "player_injury_context.json"
PITCHER_AUDIT_PATH   = BASE_DIR / "data" / "backtest_audit_pitchers.csv"


# ── Career ERA builder ────────────────────────────────────────────────────────

def _build_career_era_2yr() -> dict:
    """Return {mlbam_id (int): career_era_2yr (float)} from 2024+2025 backtest audit.

    Uses era_actual (April ERA at time of signal) for 2024 and 2025.
    A one-year entry uses that single season's ERA. Two-year entries average both.
    Returns empty dict if the audit file is missing.
    """
    try:
        df = pd.read_csv(PITCHER_AUDIT_PATH)
        recent = df[df["year"].isin([2024, 2025])][["mlbam_id", "era_actual"]].copy()
        era_map = recent.groupby("mlbam_id")["era_actual"].mean()
        return era_map.to_dict()
    except Exception:
        return {}


# ── Injury context loader ─────────────────────────────────────────────────────

def _load_injury_context() -> dict:
    """Return {mlbam_id (str): context_dict} from player_injury_context.json."""
    if not INJURY_CONTEXT_PATH.exists():
        return {}
    with open(INJURY_CONTEXT_PATH, encoding="utf-8") as f:
        return json.load(f)


def _weeks_since(date_str: str) -> float:
    """Return weeks elapsed since a YYYY-MM-DD date string."""
    try:
        surgery = date.fromisoformat(date_str)
        return (date.today() - surgery).days / 7.0
    except (ValueError, TypeError):
        return 0.0


# ── Override 1: Elite Track Record Gate (pitchers) ───────────────────────────

def apply_pitcher_elite_gate(pitcher_df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Apply ELITE_TRACK_RECORD context to pitcher Sell High signals.

    For pitchers with:
      - career_era_2yr < 2.50  (multi-year generational ERA)
      - pitcher_quality_tier == "Elite (FIP-<80)"
      - |ERA - FIP| < 0.50     (signal gap is marginal, not strong)

    The signal is flagged with signal_override='ELITE_TRACK_RECORD' and
    override_confidence=0.50 (reduced, but not zeroed — the data still
    shows marginal overperformance). The verdict column is NOT changed
    here; that decision belongs to Layer 1 or the user.

    Returns (modified_df, list_of_downgraded_names).
    """
    career_era = _build_career_era_2yr()

    pitcher_df = pitcher_df.copy()
    for col, default in [
        ("signal_override",     ""),
        ("override_confidence", 1.0),
        ("override_note",       ""),
    ]:
        if col not in pitcher_df.columns:
            pitcher_df[col] = default

    sells_mask = pitcher_df["verdict"].isin(["Sell high", "Sell High"])
    downgraded: list[str] = []

    for idx, row in pitcher_df[sells_mask].iterrows():
        pid   = int(row.get("pitcher", 0))
        c2yr  = career_era.get(pid)
        tier  = str(row.get("pitcher_quality_tier", ""))
        gap   = float(row.get("ERA_minus_FIP", -999))

        is_elite         = "Elite" in tier
        has_track_record = (c2yr is not None and c2yr < ELITE_ERA_THRESHOLD)
        gap_too_small    = abs(gap) < ELITE_GAP_REQUIRED

        if is_elite and has_track_record and gap_too_small:
            pitcher_df.at[idx, "signal_override"]     = "ELITE_TRACK_RECORD"
            pitcher_df.at[idx, "override_confidence"]  = ELITE_CONF_WEIGHT
            pitcher_df.at[idx, "override_note"] = (
                f"Career 2yr ERA {c2yr:.2f} < {ELITE_ERA_THRESHOLD} "
                f"(Elite tier) but ERA-FIP gap {gap:.2f} is below "
                f"required {ELITE_GAP_REQUIRED:.2f} threshold — "
                f"marginal signal for proven elite arm"
            )
            downgraded.append(str(row.get("name", pid)))

    return pitcher_df, downgraded


# ── Override 2: Injury Recovery Context ──────────────────────────────────────

def apply_injury_context(
    df: pd.DataFrame,
    id_col: str = "batter",
) -> pd.DataFrame:
    """Apply INJURY_RECOVERY context to players in known surgical recovery.

    Adds signal_override='INJURY_RECOVERY' and override_confidence=0.30
    for players whose expected_recovery_weeks has not yet elapsed since
    their surgery_date.

    Works for both hitters (id_col='batter') and pitchers (id_col='pitcher').
    Does NOT change verdict or luck_score — display context only.
    """
    context = _load_injury_context()
    if not context:
        return df

    df = df.copy()
    for col, default in [
        ("signal_override",     ""),
        ("override_confidence", 1.0),
        ("override_note",       ""),
    ]:
        if col not in df.columns:
            df[col] = default

    for idx, row in df.iterrows():
        try:
            pid = str(int(row.get(id_col, -1)))
        except (ValueError, TypeError):
            continue

        if pid not in context:
            continue

        ctx      = context[pid]
        surgery  = ctx.get("surgery_date", "")
        rec_wks  = int(ctx.get("expected_recovery_weeks", 0))
        elapsed  = _weeks_since(surgery)

        if elapsed < rec_wks:
            verdict = str(row.get("verdict", ""))
            df.at[idx, "signal_override"]     = "INJURY_RECOVERY"
            df.at[idx, "override_confidence"]  = INJURY_CONF_WEIGHT
            df.at[idx, "override_note"] = (
                f"{ctx.get('injury_type','surgery').replace('_',' ').title()} "
                f"{surgery} — {elapsed:.1f}/{rec_wks} weeks elapsed. "
                f"Signal ({verdict}) valid directionally but resolution "
                f"timing uncertain during recovery."
            )

    return df


# ── Summary helpers ───────────────────────────────────────────────────────────

def print_elite_gate_summary(pitcher_df: pd.DataFrame, downgraded: list[str]) -> None:
    print(f"\n=== ELITE TRACK RECORD GATE SUMMARY ===")
    print(f"Sell High pitchers evaluated: {pitcher_df['verdict'].isin(['Sell high','Sell High']).sum()}")
    print(f"Downgraded to Neutral (gap < {ELITE_GAP_REQUIRED}): {len(downgraded)}")
    if downgraded:
        for name in downgraded:
            print(f"  - {name}")
    else:
        print("  (none — all current Sell High pitchers have gap >= threshold)")

    # Show borderline cases (gap 0.50–0.70, elite pitchers — close to firing)
    sells = pitcher_df[pitcher_df["verdict"].isin(["Sell high", "Sell High"])].copy()
    career_era = _build_career_era_2yr()
    borderline = []
    for _, row in sells.iterrows():
        pid  = int(row.get("pitcher", 0))
        c2yr = career_era.get(pid)
        tier = str(row.get("pitcher_quality_tier", ""))
        gap  = float(row.get("ERA_minus_FIP", -999))
        if ("Elite" in tier and c2yr is not None and c2yr < ELITE_ERA_THRESHOLD
                and ELITE_GAP_REQUIRED <= abs(gap) < 0.70):
            borderline.append((row.get("name", pid), c2yr, gap))
    if borderline:
        print(f"\nBorderline (gap {ELITE_GAP_REQUIRED:.2f}–0.70, would fire at lower threshold):")
        for name, era, gap in borderline:
            print(f"  {name}: career ERA {era:.2f}, gap {gap:.2f}")


def print_injury_summary(df: pd.DataFrame) -> None:
    injured = df[df.get("signal_override", pd.Series(dtype=str)).eq("INJURY_RECOVERY")]
    if isinstance(df.get("signal_override"), type(None)):
        injured = df[df.get("signal_override", "") == "INJURY_RECOVERY"]
    flagged = df[df["signal_override"] == "INJURY_RECOVERY"] if "signal_override" in df.columns else pd.DataFrame()
    print(f"\n=== INJURY RECOVERY FLAGS ===")
    if flagged.empty:
        print("  (no active injury recovery flags)")
        return
    for _, row in flagged.iterrows():
        print(f"  {row.get('name','?')}: {row['override_note']}")


# ── Standalone run ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    print("Loading pitcher luck scores...")
    pitcher_df = pd.read_csv(BASE_DIR / "pitcher_luck_scores.csv")
    pitcher_df, downgraded = apply_pitcher_elite_gate(pitcher_df)
    print_elite_gate_summary(pitcher_df, downgraded)

    print("\nLoading hitter luck scores...")
    hitter_df = pd.read_csv(BASE_DIR / "luck_scores.csv")
    hitter_df = apply_injury_context(hitter_df, id_col="batter")
    print_injury_summary(hitter_df)

    print("\nLoading pitcher injury context...")
    pitcher_df = apply_injury_context(pitcher_df, id_col="pitcher")
    print_injury_summary(pitcher_df)
