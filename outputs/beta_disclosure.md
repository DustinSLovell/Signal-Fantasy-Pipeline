# Signal Fantasy Trade Analyzer — Beta Disclosure

*For beta testers. Last updated May 12, 2026.*

---

## What This Tool Does

The trade analyzer compares the projected value surplus of players you give versus players you receive, adjusted for luck signals (Buy Low / Sell High) and elite scarcity premiums.
It is built on the same signal model that has called 91.4% of Buy Low and Sell High outcomes correctly since April 22, 2026.

---

## Known Limitations

### 1. Two-way players (Ohtani) show hitter value only

In standard leagues, Shohei Ohtani is evaluated as a hitter (OF/DH position).
His pitching surplus is not included because he occupies one roster spot in standard league formats.
In a two-way league where he fills a pitcher slot as well, the tool will undervalue him.
**Workaround**: Add his pitching contribution manually if you are in a two-way league.

### 2. Names with periods or accents may need last-name-only input

Players like J.T. Realmuto, A.J. Minter, or names with accent characters may not resolve on the first try.
**Workaround**: Use last name only (e.g., `Realmuto`) or try alternate spellings.

### 3. IL players may show negative surplus

A player currently on the injured list may have negative surplus because their rest-of-season projected stats are depressed.
The signal (e.g., Buy Low) reflects the underlying peripheral quality, not current availability.
When the surplus is negative, the signal warning is labeled accordingly — this is expected behavior, not a bug.

### 4. Signal-adjusted vs Elite-adjusted display

The per-player output shows two adjusted values:

- **Signal-adjusted** (e.g., `+188 (+21)`) — display-only estimate of where the player's value sits after factoring in the luck signal. *Not* used in totals.
- **Elite-adjusted** (e.g., `Elite-adjusted: +217`) — base surplus × elite scarcity premium. *This* feeds into the verdict totals.

The elite premium is applied to base surplus, not to the signal-adjusted number. The parenthetical note in the output clarifies this.

### 5. Roto league undervaluation of power hitters (pending update)

Trade verdicts use a signal-adjusted projected value score. In 5x5 roto leagues, power hitters with multi-category contributions (HR cascades into home runs, runs, and RBI simultaneously) may be directionally undervalued pending a roto surplus model update. The current model weights all counting stats equally by position rank contribution.

---

## Multi-Player Trade Syntax

You can pass multiple players two ways — both are equivalent:

```
# Space-separated under one flag (original)
python trade_analyzer.py --give "Player A" "Player B" --receive "Player C" "Player D"

# Repeated flags (added in this release)
python trade_analyzer.py --give "Player A" --give "Player B" --receive "Player C" --receive "Player D"
```

---

## What the Verdict Thresholds Mean

| Verdict | Delta |
|---------|-------|
| STRONG TRADE | ≥ +50 |
| FAVORABLE | ≥ +20 |
| SLIGHTLY FAVORABLE | ≥ +5 |
| NEUTRAL | −5 to +5 |
| SLIGHTLY UNFAVORABLE | ≤ −5 |
| UNFAVORABLE | ≤ −20 |
| AVOID | ≤ −50 |

The delta is the Projected Value surplus above replacement level.
A delta of ±20 is meaningful. A delta of ±5 is within estimation noise.

---

## Feedback

If a player returns "not found," try the last name only first.
If a signal or surplus looks wrong, describe the trade scenario and I will investigate.
