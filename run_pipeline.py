"""
run_pipeline.py
Runs the full fantasy baseball Statcast pipeline in sequence.

Hitter pipeline:
  1. fetch_stats.py           — pull raw Statcast data
  2. process_stats.py         — aggregate into per-batter metrics
  3. score_luck.py            — score each batter and print buy/sell tables

Pitcher pipeline:
  4. fetch_pitcher_stats.py   — pull pitcher Statcast + FanGraphs data
  5. process_pitcher_stats.py — aggregate per-pitcher metrics and compute gaps
  6. score_pitcher_luck.py    — score each pitcher and print buy/sell tables

Usage:
    python run_pipeline.py              # run all 6 steps
    python run_pipeline.py --hitters    # run hitter pipeline only (steps 1-3)
    python run_pipeline.py --pitchers   # run pitcher pipeline only (steps 4-6)
"""

import subprocess
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd


HITTER_SCRIPTS = [
    ("fetch_stats.py",           "Fetching hitter Statcast data from Baseball Savant"),
    ("process_stats.py",         "Aggregating per-batter metrics"),
    ("score_luck.py",            "Scoring luck and generating buy/sell rankings"),
]

PITCHER_SCRIPTS = [
    ("fetch_pitcher_stats.py",   "Fetching pitcher Statcast + FanGraphs data"),
    ("process_pitcher_stats.py", "Aggregating per-pitcher metrics and ERA gaps"),
    ("score_pitcher_luck.py",    "Scoring luck and generating pitcher buy/sell rankings"),
]

def _select_scripts() -> list:
    args = sys.argv[1:]
    if "--hitters" in args:
        return HITTER_SCRIPTS
    if "--pitchers" in args:
        return PITCHER_SCRIPTS
    return HITTER_SCRIPTS + PITCHER_SCRIPTS

SCRIPTS = _select_scripts()

DIVIDER       = "=" * 65
STEP_DIVIDER  = "-" * 65


def fmt_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s}s"


def run_step(step_num: int, total: int, script: str, description: str) -> float:
    """Run a single pipeline script, streaming its output. Returns elapsed seconds."""
    print(f"\n{STEP_DIVIDER}")
    print(f"  Step {step_num}/{total}: {description}")
    print(f"  Script : {script}")
    print(STEP_DIVIDER)

    start = time.perf_counter()

    proc = subprocess.Popen(
        [sys.executable, script],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,   # merge stderr into stdout so output is ordered
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,                  # line-buffered
        cwd=Path(__file__).parent,
    )

    output_lines = []
    for line in proc.stdout:
        safe_line = line.replace("�", "?")
        print(f"  {safe_line}", end="")
        output_lines.append(line)

    proc.wait()
    elapsed = time.perf_counter() - start

    if proc.returncode != 0:
        # Collect any remaining output that might still be buffered
        tail = "".join(output_lines[-20:]) if output_lines else "(no output captured)"
        print(f"\n  [ERROR] {script} exited with code {proc.returncode}")
        raise RuntimeError(
            f"Step {step_num} failed: {script}\n"
            f"  Description : {description}\n"
            f"  Exit code   : {proc.returncode}\n"
            f"  Last output :\n"
            + "\n".join(f"    {l.rstrip()}" for l in output_lines[-20:])
        )

    return elapsed


def main():
    total = len(SCRIPTS)

    args = sys.argv[1:]
    if "--hitters" in args:
        label = "Hitter Pipeline"
    elif "--pitchers" in args:
        label = "Pitcher Pipeline"
    else:
        label = "Full Pipeline (Hitters + Pitchers)"

    print(DIVIDER)
    print(f"  Fantasy Baseball Statcast Pipeline — {label}")
    print(f"  {total} step{'s' if total != 1 else ''} to run")
    print(DIVIDER)

    # Refresh ownership data before hitter scoring (graceful failure — never blocks pipeline)
    if any(s == "score_luck.py" for s, _ in SCRIPTS):
        print("\nFetching ownership data...")
        result = subprocess.run(
            [sys.executable, "fetch_ownership.py"],
            capture_output=True, text=True,
            cwd=Path(__file__).parent,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                print(f"  {line}")
            print("  Ownership data updated")
        else:
            err = (result.stderr or result.stdout or "unknown error")[:200]
            print(f"  Ownership fetch failed — using cached data ({err.splitlines()[0]})")

    pipeline_start = time.perf_counter()
    step_times = []

    for i, (script, description) in enumerate(SCRIPTS, start=1):
        try:
            elapsed = run_step(i, total, script, description)
        except RuntimeError as exc:
            print(f"\n{DIVIDER}")
            print("  PIPELINE FAILED")
            print(DIVIDER)
            print(f"\n{exc}")
            print(f"\nPipeline stopped at step {i}/{total}. "
                  "Fix the error above and re-run.")
            sys.exit(1)

        step_times.append((script, elapsed))
        print(f"\n  Step {i}/{total} complete in {fmt_duration(elapsed)}")

        # After score_luck.py runs, update Yordan tracker
        if script == "score_luck.py":
            update_yordan_tracker()

    total_elapsed = time.perf_counter() - pipeline_start

    print(f"\n{DIVIDER}")
    print("  PIPELINE COMPLETE")
    print(DIVIDER)
    print()
    for script, t in step_times:
        print(f"  {script:<22}  {fmt_duration(t):>6}")
    print(f"  {'-' * 30}")
    print(f"  {'Total':<22}  {fmt_duration(total_elapsed):>6}")
    print()

    # Enrich pitcher_luck_scores.csv with pitch mix / evolution columns
    # Must run after score_pitcher_luck.py and before generate_projections.py
    if any(s == "score_pitcher_luck.py" for s, _ in SCRIPTS):
        print(f"\n{STEP_DIVIDER}")
        print("  Building pitcher pitch mix baselines...")
        print(STEP_DIVIDER)
        result = subprocess.run(
            [sys.executable, "build_pitcher_pitch_mix.py"],
            capture_output=True, text=True,
            cwd=Path(__file__).parent,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                print(f"  {line}")
        else:
            err = (result.stderr or result.stdout or "unknown error")[:200]
            print(f"  WARNING: Pitch mix build failed: {err.splitlines()[0]}")

    # Generate player projections CSV
    print(f"\n{STEP_DIVIDER}")
    print("  Generating player projections...")
    print(STEP_DIVIDER)
    result = subprocess.run(
        [sys.executable, "generate_projections.py"],
        capture_output=True, text=True,
        cwd=Path(__file__).parent,
    )
    if result.returncode == 0:
        for line in result.stdout.splitlines():
            print(f"  {line.strip()}")
    else:
        err = (result.stderr or result.stdout or "unknown error")[:200]
        print(f"  WARNING: Projections generation failed: {err}")

    # Generate public signal board
    print(f"\n{STEP_DIVIDER}")
    print("  Generating signal board export...")
    print(STEP_DIVIDER)
    result = subprocess.run(
        [sys.executable, "export_signal_board.py"],
        capture_output=True, text=True,
        cwd=Path(__file__).parent,
    )
    if result.returncode == 0:
        for line in result.stdout.splitlines():
            print(f"  {line.strip()}")
        print("  Signal board exported: outputs/signal_board_latest.xlsx")
    else:
        err = (result.stderr or result.stdout or "unknown error")[:200]
        print(f"  WARNING: Signal board export failed: {err}")


YORDAN_ID       = 670541
LUCK_SCORES_PATH = Path(__file__).parent / "luck_scores.csv"
YORDAN_TRACKER  = Path(__file__).parent / "data" / "yordan_tracker.csv"


def update_yordan_tracker() -> None:
    if not LUCK_SCORES_PATH.exists():
        print("  Yordan tracker: luck_scores.csv not found, skipping.")
        return

    df = pd.read_csv(LUCK_SCORES_PATH)
    row = df[df["batter"] == YORDAN_ID]
    if row.empty:
        print("  Yordan tracker: Yordan Alvarez not in luck_scores.csv, skipping.")
        return

    r = row.iloc[0]
    today = date.today().isoformat()

    new_row = {
        "week_ending":   today,
        "woba":          round(float(r.get("wOBA", float("nan"))), 4),
        "xwoba":         round(float(r.get("xwOBA", float("nan"))), 4),
        "babip":         round(float(r.get("BABIP", float("nan"))), 4),
        "luck_score":    round(float(r.get("luck_score", float("nan"))), 4),
        "verdict":       str(r.get("verdict", "")),
        "career_babip":  round(float(r.get("career_babip", float("nan"))), 4),
    }

    YORDAN_TRACKER.parent.mkdir(exist_ok=True)

    if YORDAN_TRACKER.exists():
        tracker = pd.read_csv(YORDAN_TRACKER)
        week_n  = len(tracker) + 1
        tracker = pd.concat([tracker, pd.DataFrame([new_row])], ignore_index=True)
    else:
        week_n  = 1
        tracker = pd.DataFrame([new_row])

    tracker.to_csv(YORDAN_TRACKER, index=False)
    print(f"  Yordan tracker updated: Week {week_n}")


if __name__ == "__main__":
    main()
