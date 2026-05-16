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
import traceback
from language import load_sector_names
from display import display_results
from scanner import scan_save, scan_reputation
from ships import scan_ships
from jsonexport import export_json

# ─────────────────────────────────────────────────────────────────────────────
#  FILE PATHS
#  pathlib.Path(__file__).parent always points to the folder the script lives
#  in, regardless of how or where the script is launched from.
# ─────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR = pathlib.Path(__file__).parent
SAVE_FILE  = SCRIPT_DIR / "save_001.xml"
LANG_FILE  = SCRIPT_DIR / "0001-l044.xml"

# ─────────────────────────────────────────────────────────────────────────────
#  SHIP SCAN TIER
#  Controls how much NPC ship data is collected alongside your own fleet.
#  1 = player ships only (default — fastest, no extra RAM)
#  2 = + NPC ships in sectors where you have stations
#  3 = + NPC ships in all sectors where you have ships
#
#  Change this value and re-run to get more or less context.
# ─────────────────────────────────────────────────────────────────────────────

SHIP_SCAN_TIER = 1

# ═════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    try:
        # Verify save file exists before doing anything else
        if not SAVE_FILE.exists():
            print(f"Error: '{SAVE_FILE.name}' not found in the script folder.")
            print(f"Expected location: {SAVE_FILE}")
            print("Rename your unzipped X4 save to 'save_001.xml' and place it here.")
            input("\nPress Enter to exit...")
            exit(1)

        # Step 1: Load sector name lookup from the language file.
        # If the file is missing, sectors show as macro names but won't crash.
        sector_names = load_sector_names(LANG_FILE)

        # Step 2: First pass — player identity, credits, stations with sectors
        game_data = scan_save(SAVE_FILE, sector_names)

        # Step 3: Second pass — faction reputation with scaling and booster handling
        game_data["reputation"] = scan_reputation(SAVE_FILE)

        # Step 4: Third pass — ship data at the configured tier
        #
        # Tier 2 needs the set of sectors where stations exist so the scanner
        # knows which NPC ships are worth keeping.
        # Tier 3 additionally passes player ship sectors, but those aren't
        # known until after the ship scan itself. We solve this with a
        # lightweight first pass at tier 1 to collect player ship sectors,
        # then a full tier 3 pass — only done when explicitly requested.

        station_sectors: set[str] | None = None
        ship_sectors:    set[str] | None = None

        if SHIP_SCAN_TIER >= 2:
            station_sectors = {s["sector"] for s in game_data["stations"]}

        if SHIP_SCAN_TIER == 3:
            # Quick tier-1 pass to learn which sectors player ships are in
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

        # Step 5: Display and export
        display_results(game_data)
        export_json(game_data)

    except Exception as e:
        print(f"\n[FATAL ERROR] {e}")
        traceback.print_exc()

    input("\nPress Enter to exit...")