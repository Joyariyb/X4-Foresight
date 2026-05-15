"""
X4 FOUNDATIONS — SAVE FILE SCANNER  v4.0
==========================================
Reads an unzipped X4 save file (save_001.xml) and extracts:
  - Pilot name and current sector
  - Credits / liquid cash
  - All player-owned stations with sector locations and production
  - Faction reputation standings displayed as in-game whole numbers

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
  The in-game UI multiplies these by 100 and displays them as whole numbers
  with one decimal place (e.g. 0.256 -> 25.6). This script replicates
  that scaling so figures match what you see in-game.
"""

import pathlib
import traceback
from language import load_sector_names
from display import display_results
from scanner import scan_save, scan_reputation
from jsonexport import export_json

# ─────────────────────────────────────────────────────────────────────────────
#  FILE PATHS
#  pathlib.Path(__file__).parent always points to the folder the script lives
#  in, regardless of how or where the script is launched from.
# ─────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR = pathlib.Path(__file__).parent
SAVE_FILE  = SCRIPT_DIR / "save_001.xml"
LANG_FILE  = SCRIPT_DIR / "0001-l044.xml"

# ═════════════════════════════════════════════════════════════════════════════
#  SECTION 6 — ENTRY POINT
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

        # Step 4: Display and export
        display_results(game_data)
        export_json(game_data)

    except Exception as e:
        print(f"\n[FATAL ERROR] {e}")
        traceback.print_exc()

    input("\nPress Enter to exit...")