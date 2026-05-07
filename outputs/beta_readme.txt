THE SIGNAL FANTASY — TRADE ANALYZER BETA
==========================================

Thank you for beta testing the Signal Trade Analyzer.
This tool evaluates fantasy baseball trades using luck signals,
projected stats, and position scarcity.


HOW TO RUN
----------
Open a terminal in the fantasy-baseball folder and type:

  python trade_analyzer.py
    --give "Player Name"
    --receive "Player Name"

Example:
  python trade_analyzer.py --give "Brice Turang" --receive "Jose Ramirez" "Joe Ryan"

Add multiple players on either side by listing them with quotes:
  python trade_analyzer.py
    --give "Jose Ramirez" "Joe Ryan"
    --receive "Paul Skenes"


WHICH LEAGUE?
-------------
  --league 1   CBS 13-team standard (batting average scoring)
  --league 2   Fantrax 15-team OBP scoring

Default is league 1. Add --league 2 to your command for Fantrax.

Example:
  python trade_analyzer.py --give "Corey Seager" --receive "Matt Chapman" "Dillon Dingler" --league 2


OPEN ROSTER SLOT?
-----------------
If you have an open roster spot and don't need to drop a player
to make room, add --open-slot:

  python trade_analyzer.py
    --give "Brice Turang"
    --receive "Joe Ryan" "Jose Ramirez"
    --open-slot


WHAT THE VERDICT MEANS
----------------------
  STRONG TRADE         — clear advantage (run it)
  FAVORABLE            — moderate advantage (lean yes)
  SLIGHTLY FAVORABLE   — small edge (consider it)
  NEUTRAL              — roughly even (fair trade)
  SLIGHTLY UNFAVORABLE — small disadvantage (ask for more)
  UNFAVORABLE          — meaningful disadvantage (probably decline)
  AVOID                — clear disadvantage (decline)

The verdict is based on projected rest-of-season stats,
position scarcity, luck signals, and player rank.


WHAT THE SIGNALS MEAN
---------------------
  Buy Low:   This player is underperforming their underlying
             contact quality. Their stats should improve.
             A good player to receive in a trade.

  Sell High: This player is overperforming their underlying
             contact quality. Their stats may regress.
             A good player to trade away while their value is high.

  Neutral:   Stats are roughly matching underlying performance.
             No strong signal either way.

For pitchers:
  Buy Low:   ERA is inflated by bad luck (BABIP, strand rate).
             Peripherals (FIP, xERA) suggest improvement ahead.
  Sell High: ERA looks better than underlying metrics suggest.
             Regression may be coming.


PLAYER NAMES
------------
Use the player's full name in quotes. If a name isn't found,
try the last name only:

  python trade_analyzer.py --give "Turang" --receive "Ramirez"

Common issues:
  - Accents: "Jose Ramirez" works (accent optional)
  - Nicknames: use official names (e.g., "Brice Turang" not "Brett Turang")
  - Two players with same last name: add first name to disambiguate


HOW TO REPORT ISSUES
--------------------
DM on Substack or reply to the beta post.

Please include:
  1. The exact command you ran
  2. The full output (copy-paste from terminal)
  3. What you expected vs what you saw

Known limitations:
  - Not all players are in the database (rookies, NPB call-ups may be missing)
  - Saves/holds projections use last year's Steamer data (no live 2026 data yet)
  - The tool is CBS-scoring focused; Fantrax OBP is supported but other formats are not


QUICK EXAMPLES
--------------
Textbook signal trade:
  python trade_analyzer.py --give "Brice Turang" --receive "Joe Ryan" "Jose Ramirez" --league 1

Warning trade (what NOT to do):
  python trade_analyzer.py --give "Jose Ramirez" "Joe Ryan" --receive "Paul Skenes" --league 1

League comparison:
  python trade_analyzer.py --give "Corey Seager" --receive "Matt Chapman" "Dillon Dingler" --league 1
  python trade_analyzer.py --give "Corey Seager" --receive "Matt Chapman" "Dillon Dingler" --league 2
