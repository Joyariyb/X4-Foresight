"""
X4 FOUNDATIONS — SAVE FILE SCANNER  v4.1
==========================================
Reads an unzipped X4 save file (save_001.xml) and extracts:
  - Pilot name and current sector
  - Credits / liquid cash
  - All player-owned stations with sector locations and production
  - Faction reputation standings displayed as in-game values
  - Player fleet and optionally NPC ships in sectors of interest

Then exports everything to x4_empire_state.json, ready to paste
into an AI prompt for strategic advice.

REQUIRED FILES (all in the same folder as this script):
  save_001.xml     — your unzipped X4 save file
  0001-l044.xml    — X4 English language file (extracted from game .cat files
                     using X Tools, available free on Steam)

HOW SECTOR NAMES WORK:
  Sector components in the save file use a 'macro' attribute like
  'cluster_43_sector001_macro'. We convert this to a language file ID
  using the formula: cluster_num * 10 + sector_suffix, then look up
  the human-readable name from page 20004 of the language file.

HOW REPUTATION SCALING WORKS:
  X4 stores reputation internally as small floats (e.g. 0.0032).
  The in-game UI applies a log10 curve to produce in-game display values.
  This script replicates that scaling so figures match what you see in-game.

SHIP SCAN TIERS:
  1 — Player ships only (default, fastest)
  2 — Player ships + NPC ships in sectors where you have stations
  3 — Player ships + NPC ships in all sectors where you have ships
"""

import pathlib
import sys
import traceback

# ── Allow running from the project root without installing as a package ───────
# Add the project root to sys.path so that 'scanner', 'data', 'export' are
# importable as packages regardless of the working directory.
ROOT = pathlib.Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scanner.language import load_sector_names
from scanner.scanner  import scan_save, scan_reputation
from scanner.ships    import scan_ships
from export.jsonexport import export_json
from display          import display_results

# ─────────────────────────────────────────────────────────────────────────────
#  FILE PATHS
# ─────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR = pathlib.Path(__file__).parent
SAVE_FILE  = SCRIPT_DIR / "save_001.xml"
LANG_FILE  = SCRIPT_DIR / "0001-l044.xml"

# ─────────────────────────────────────────────────────────────────────────────
#  SHIP SCAN TIER
#  1 = player ships only (default — fastest, no extra RAM)
#  2 = + NPC ships in sectors where you have stations
#  3 = + NPC ships in all sectors where you have ships
# ─────────────────────────────────────────────────────────────────────────────

SHIP_SCAN_TIER = 1

# ═════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    try:
        if not SAVE_FILE.exists():
            print(f"Error: '{SAVE_FILE.name}' not found in the project folder.")
            print(f"Expected location: {SAVE_FILE}")
            print("Rename your unzipped X4 save to 'save_001.xml' and place it here.")
            input("\nPress Enter to exit...")
            exit(1)

        sector_names = load_sector_names(LANG_FILE)

        game_data = scan_save(SAVE_FILE, sector_names)
        game_data["reputation"] = scan_reputation(SAVE_FILE)

        station_sectors: set[str] | None = None
        ship_sectors:    set[str] | None = None

        if SHIP_SCAN_TIER >= 2:
            station_sectors = {s["sector"] for s in game_data["stations"]}

        if SHIP_SCAN_TIER == 3:
            print("[Ships] Pre-scan to locate player ship sectors for tier 3...")
            tier1_data  = scan_ships(SAVE_FILE, sector_names)
            ship_sectors = (
                {s["sector"] for s in tier1_data["player_ships"]}
                | (station_sectors or set())
            )

        game_data["ships"] = scan_ships(
            SAVE_FILE,
            sector_names,
            station_sectors=station_sectors,
            ship_sectors=ship_sectors,
        )

        display_results(game_data)
        export_json(game_data, output_dir=SCRIPT_DIR)

    except Exception as e:
        print(f"\n[FATAL ERROR] {e}")
        traceback.print_exc()

    input("\nPress Enter to exit...")
