"""
X4 FOUNDATIONS — SAVE FILE SCANNER  v4.1
==========================================
Reads an unzipped X4 save file (save_001.xml) and extracts:
  - Pilot name and current sector
  - Credits / liquid cash
  - All player-owned stations with sector locations and production
  - Faction reputation standings displayed as in-game values
  - Player fleet and optionally NPC ships in sectors of interest

Then exports everything to x4_empire_state.json for use as structured data
in AI prompts requiring strategic analysis.

REQUIRED FILES (all in the same folder as this script):
  0001-l044.xml    — X4 English language file (extracted from game .cat files
                     using X Tools, available free on Steam)

HOW SECTOR NAMES WORK:
  Sector components in the save file use a 'macro' attribute like
  'cluster_43_sector001_macro'. We convert this to a language file ID
  using the formula: cluster_num * 10 + sector_suffix, then look up
  the human-readable name from the language file's sector naming table.

HOW REPUTATION SCALING WORKS:
  X4 stores reputation internally as small floats (e.g. 0.0032).
  The in-game UI applies a log10 curve to produce display values.
  This script replicates that scaling so figures match what you see in-game.

SHIP SCAN TIERS:
  1 — Player ships only (default, fastest)
  2 — Player ships + NPC ships in sectors where you have stations
  3 — Player ships + NPC ships in all sectors where you have ships

RUN MODES:
  "full"     — Runs the complete pipeline: player data, stations, reputation,
               ships, display, and JSON export. Normal production usage.
  "stations" — Runs Pass 1 only (player data + stations). Skips reputation
               and ship scanning. Use when iterating on station display (~5s).
  "ships"    — Skips Pass 1 (player/stations) and Pass 2 (reputation) entirely.
               Loads sector names, scans ships only, and displays the fleet
               section with stub values for all other fields. Use this when
               iterating on ship_scanner.py to avoid waiting for the full scan.
"""

import pathlib
import sys
import time
import traceback
from datetime import datetime

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
LANG_FILE  = SCRIPT_DIR / "0001-l044.xml"


def select_save_file() -> pathlib.Path:
    """
    Interactive save file selector. Lists available X4 saves from the default
    game directory and prompts the user to choose one, with a fallback to any
    save_001.xml placed directly in the program folder for quick access.
    """
    x4_base   = pathlib.Path.home() / "Documents" / "Egosoft" / "X4"
    saves_dir = None

    if x4_base.exists():
        for d in sorted(x4_base.iterdir()):
            candidate = d / "save"
            if candidate.is_dir():
                saves_dir = candidate
                break

    manual_saves = []
    auto_saves   = []
    root_save    = SCRIPT_DIR / "save_001.xml"

    if saves_dir:
        manual_saves = sorted(saves_dir.glob("save_*.xml.gz"),     key=lambda p: p.name)
        auto_saves   = sorted(saves_dir.glob("autosave_*.xml.gz"), key=lambda p: p.name)

    all_saves = manual_saves + auto_saves

    if not all_saves and not root_save.exists():
        print("\n  [Error] No X4 save files found and no save_001.xml in program folder.")
        sys.exit(1)

    latest = max(all_saves, key=lambda p: p.stat().st_mtime) if all_saves else None

    print()
    print("  ── SELECT SAVE ────────────────────────────────────────────────────")
    if saves_dir:
        print(f"  Directory: {saves_dir}")
        print()
        for i, save in enumerate(all_saves, 1):
            mtime = datetime.fromtimestamp(save.stat().st_mtime)
            label = save.name.replace('.xml.gz', '')
            tag   = "  ← latest" if save is latest else ""
            print(f"  [{i:>2}]  {label:<20}  {mtime.strftime('%a %d %b  %H:%M')}{tag}")

    if root_save.exists():
        print(f"\n   [R]  Program folder  ({root_save.name})")

    print()
    prompt = f"  Select [1-{len(all_saves)} / L for latest / R for root folder]: "

    while True:
        choice = input(prompt).strip().upper()
        if choice == 'L' and latest:
            return latest
        if choice == 'R' and root_save.exists():
            return root_save
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(all_saves):
                return all_saves[idx - 1]
        print("  Invalid selection, try again.")

# ─────────────────────────────────────────────────────────────────────────────
#  RUN MODE
#  Controls which passes are executed on each run.
#
#  "full"     — complete pipeline (player, stations, reputation, ships, export)
#  "stations" — Pass 1 only (player + stations); fastest for iterating on station display
#  "ships"    — ships scan only; skips Pass 1 and Pass 2 entirely
#
#  Switch to "stations" when iterating on station display to avoid the ~90s ship scan.
#  Switch to "ships" when iterating on ship_scanner.py.
# ─────────────────────────────────────────────────────────────────────────────

RUN_MODE = "stations"  # "full" | "ships" | "stations"

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

SHIP_SCAN_TIER = 3

# ═════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    try:
        SAVE_FILE = select_save_file()
        print(f"\n  Loading: {SAVE_FILE.name}\n")

        # ── Sector names are always needed — both full and ships mode use them
        # to resolve human-readable sector names from macro strings.
        t0 = time.perf_counter()
        sector_names = load_sector_names(LANG_FILE)
        print(f"[Done] Sector names loaded in {time.perf_counter() - t0:.2f}s")

        # ─────────────────────────────────────────────────────────────────────
        #  STATIONS MODE
        #  Runs only Pass 1 (player data + stations). Skips reputation and ship
        #  scanning entirely so iterations on station display are fast (~5s vs ~90s).
        # ─────────────────────────────────────────────────────────────────────

        if RUN_MODE == "stations":
            print("[Mode] Stations-only scan — skipping reputation and ships passes.")

            t0        = time.perf_counter()
            game_data = scan_save(SAVE_FILE, sector_names)
            print(f"[Done] Pass 1 completed in {time.perf_counter() - t0:.2f}s")

            game_data["reputation"] = []
            game_data["ships"]      = {"player_ships": [], "npc_ships": []}
            game_data["crew"]       = game_data.get("managers", [])

            display_results(game_data)

        # ─────────────────────────────────────────────────────────────────────
        #  SHIPS MODE
        #  Bypasses Pass 1 (player data/stations) and Pass 2 (reputation) entirely.
        #  Builds a minimal game_data stub so display_results() can render the fleet
        #  section without any changes to display.py. All non-ship fields are set to
        #  neutral dummy values that clearly indicate ships mode is active in the output.
        # ─────────────────────────────────────────────────────────────────────

        elif RUN_MODE == "ships":
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
        #  Runs the complete pipeline: player data extraction, station analysis,
        #  reputation calculation, ship scanning (with optional NPC inclusion),
        #  display output to console, and JSON export for AI prompt usage.
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

            # In tier 3, the pre-scan above already found all player ships, so
            # the main scan only needs to collect NPC ships (npc_only=True skips
            # player ship buffering, halving the work). We then stitch the two
            # results back together. Tiers 1 and 2 do a single combined scan.
            t0       = time.perf_counter()
            npc_only = (SHIP_SCAN_TIER == 3)
            main_scan = scan_ships(
                SAVE_FILE,
                sector_names,
                station_sectors=station_sectors,
                ship_sectors=ship_sectors,
                npc_only=npc_only,
            )
            print(f"[Done] Ships scan completed in {time.perf_counter() - t0:.2f}s")

            if SHIP_SCAN_TIER == 3:
                # Re-use the player ships and crew we already found in the
                # pre-scan instead of scanning for them a second time.
                game_data["ships"] = {
                    "player_ships": tier1_data["player_ships"],
                    "npc_ships":    main_scan["npc_ships"],
                }
                ship_crew = tier1_data.get("crew", [])
            else:
                game_data["ships"] = main_scan
                ship_crew = main_scan.get("crew", [])

            # Merge station managers (from Pass 1) with ship crew (from Pass 3).
            # Managers come first so they appear at the top of the roster.
            game_data["crew"] = game_data.get("managers", []) + ship_crew

            display_results(game_data)
            export_json(game_data, output_dir=SCRIPT_DIR)

        else:
            print(f"[Error] Unknown RUN_MODE '{RUN_MODE}'. Valid options: 'full', 'ships'.")

    except Exception as e:
        print(f"\n[FATAL ERROR] {e}")
        traceback.print_exc()

    input("\nPress Enter to exit...")
