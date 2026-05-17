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

RUN MODES:
  "full"  — Runs the complete pipeline: player data, stations, reputation,
             ships, display, and JSON export. Normal production usage.
  "ships" — Skips Pass 1 (player/stations) and Pass 2 (reputation) entirely.
             Loads sector names, scans ships only, and displays the fleet
             section with stub values for all other fields. Use this when
             iterating on ship_scanner.py so you're not waiting for the full scan.
"""

import pathlib
import sys
import time
import traceback

# Force UTF-8 output so Unicode box-drawing characters in display.py render
# correctly regardless of the Windows console's default code page (cp1252).
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ── Allow running from the project root without installing as a package ───────
# Add the project root to sys.path so that 'scanner', 'data', 'export' are
# importable as packages regardless of the working directory.
ROOT = pathlib.Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scanner.language import load_sector_names
from scanner.scanner  import scan_save, scan_reputation
from scanner.ship_scanner    import scan_ships
from export.jsonexport import export_json
from display          import display_results

# ─────────────────────────────────────────────────────────────────────────────
#  FILE PATHS
# ─────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR = pathlib.Path(__file__).parent
SAVE_FILE  = SCRIPT_DIR / "save_001.xml"
LANG_FILE  = SCRIPT_DIR / "0001-l044.xml"

# ─────────────────────────────────────────────────────────────────────────────
#  RUN MODE
#  Controls which passes are executed on each run.
#
#  "full"  — complete pipeline (player, stations, reputation, ships, export)
#  "ships" — ships scan only; skips Pass 1 and Pass 2 entirely
#
#  Switch to "ships" when iterating on ship_scanner.py to avoid the overhead of
#  scanning stations and reputation on every test run.
# ─────────────────────────────────────────────────────────────────────────────

RUN_MODE = "full"  # "full" | "ships"

# ─────────────────────────────────────────────────────────────────────────────
#  SHIP SCAN TIER
#  1 = player ships only (default — fastest, no extra RAM)
#  2 = + NPC ships in sectors where you have stations
#  3 = + NPC ships in all sectors where you have ships
#
#  Note: Tiers 2 and 3 require station/ship sector data from Pass 1, so they
#  are only meaningful in RUN_MODE = "full". In "ships" mode, tier 1 is always
#  used regardless of this setting.
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

        # ── Sector names are always needed — both full and ships mode use them
        # to resolve human-readable sector names from macro strings.
        t0 = time.perf_counter()
        sector_names = load_sector_names(LANG_FILE)
        print(f"[Done] Sector names loaded in {time.perf_counter() - t0:.2f}s")

        # ─────────────────────────────────────────────────────────────────────
        #  SHIPS MODE
        #  Bypasses Pass 1 and Pass 2 completely. Builds a minimal game_data
        #  stub so display_results() can render the fleet section without any
        #  changes to display.py. All non-ship fields are set to neutral dummy
        #  values that make it obvious ships mode is active in the output.
        # ─────────────────────────────────────────────────────────────────────

        if RUN_MODE == "ships":
            print("[Mode] Ships-only scan — skipping player, stations, and reputation passes.")

            t0    = time.perf_counter()
            ships = scan_ships(SAVE_FILE, sector_names)
            print(f"[Done] Ships scan completed in {time.perf_counter() - t0:.2f}s")

            # Stub out everything display_results() expects beyond ships.
            # These values won't appear in any meaningful output context —
            # they just satisfy the dict shape so we don't touch display.py.
            game_data = {
                "player_name":    "— ships mode —",
                "player_sector":  "—",
                "player_credits": "0",
                "stations":       [],
                "reputation":     [],
                "ships":          ships,
            }

            display_results(game_data)

        # ─────────────────────────────────────────────────────────────────────
        #  FULL MODE
        #  Runs the complete pipeline exactly as before — no changes here.
        # ─────────────────────────────────────────────────────────────────────

        elif RUN_MODE == "full":
            t0        = time.perf_counter()
            game_data = scan_save(SAVE_FILE, sector_names)
            print(f"[Done] Pass 1 completed in {time.perf_counter() - t0:.2f}s")

            t0 = time.perf_counter()
            game_data["reputation"] = scan_reputation(SAVE_FILE)
            print(f"[Done] Pass 2 completed in {time.perf_counter() - t0:.2f}s")

            station_sectors: set[str] | None = None
            ship_sectors:    set[str] | None = None

            if SHIP_SCAN_TIER >= 2:
                station_sectors = {s["sector"] for s in game_data["stations"]}

            if SHIP_SCAN_TIER == 3:
                print("[Ships] Pre-scan to locate player ship sectors for tier 3...")
                t0         = time.perf_counter()
                tier1_data = scan_ships(SAVE_FILE, sector_names)
                print(f"[Done] Tier 3 pre-scan completed in {time.perf_counter() - t0:.2f}s")
                ship_sectors = (
                    {s["sector"] for s in tier1_data["player_ships"]}
                    | (station_sectors or set())
                )

            t0 = time.perf_counter()
            game_data["ships"] = scan_ships(
                SAVE_FILE,
                sector_names,
                station_sectors=station_sectors,
                ship_sectors=ship_sectors,
            )
            print(f"[Done] Ships scan completed in {time.perf_counter() - t0:.2f}s")

            display_results(game_data)
            export_json(game_data, output_dir=SCRIPT_DIR)

        else:
            print(f"[Error] Unknown RUN_MODE '{RUN_MODE}'. Valid options: 'full', 'ships'.")

    except Exception as e:
        print(f"\n[FATAL ERROR] {e}")
        traceback.print_exc()

    input("\nPress Enter to exit...")