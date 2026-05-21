"""
X4 FOUNDATIONS — SAVE FILE SCANNER  v4.2
==========================================
Reads an unzipped X4 save file and extracts empire data across up to three passes:

  Pass 1 — Stations  : player identity, credits, owned stations + health
  Pass 2 — Reputation: faction standing breakdown (log10-scaled to in-game values)
  Pass 3 — Ships     : player fleet and optionally NPC ships in sectors of interest

Output: console report via display.py, and optionally x4_empire_state.json for AI use.

SHIP SCAN TIERS (Pass 3 only):
  1 — Player ships only                           (fastest)
  2 — + NPC ships in sectors where you have stations
  3 — + NPC ships in all sectors where you have ships

RUN MODES — selected interactively at startup:
  Full        — all three passes + JSON export
  Stations    — Pass 1 only (~5s, use when iterating on station display)
  Reputation  — Pass 2 only (fast, reads one block of the save)
  Ships       — Pass 3 only (no station or reputation data)
"""

import pathlib
import sys
import time
import traceback
from datetime import datetime

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

ROOT = pathlib.Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scanner.language           import load_sector_names
from scanner.scanner            import scan_save, scan_reputation
from scanner.ship_scanner       import scan_ships, merge_station_docked_ships
from export.jsonexport          import export_json
from display                    import display_results

# ─────────────────────────────────────────────────────────────────────────────
#  FILE PATHS
# ─────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR = pathlib.Path(__file__).parent
LANG_FILE  = SCRIPT_DIR / "0001-l044.xml"

# ─────────────────────────────────────────────────────────────────────────────
#  SCAN MODE REGISTRY
#  Each entry declares which passes the mode runs and whether to export JSON.
#  Add new modes here — the selector and dispatcher pick them up automatically.
# ─────────────────────────────────────────────────────────────────────────────

SCAN_MODES = [
    {
        "key":    "full",
        "label":  "Full scan",
        "desc":   "All passes — stations, reputation, ships + JSON export",
        "passes": ["stations", "reputation", "ships"],
        "export": True,
    },
    {
        "key":    "stations",
        "label":  "Stations only",
        "desc":   "Player data, station health + inventory  (~5s, exports JSON)",
        "passes": ["stations"],
        "export": True,
    },
    {
        "key":    "reputation",
        "label":  "Reputation only",
        "desc":   "Faction standing breakdown",
        "passes": ["reputation"],
        "export": False,
    },
    {
        "key":    "ships",
        "label":  "Ships only",
        "desc":   "Fleet scan, skips stations and reputation",
        "passes": ["ships"],
        "export": False,
    },
]

# ─────────────────────────────────────────────────────────────────────────────
#  INTERACTIVE SELECTORS
# ─────────────────────────────────────────────────────────────────────────────

def select_save_file() -> pathlib.Path:
    """Lists available X4 saves and prompts the user to choose one."""
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


def select_mode() -> dict:
    """Presents the scan mode menu and returns the chosen mode dict."""
    print()
    print("  ── SELECT MODE ────────────────────────────────────────────────────")
    print()
    for i, mode in enumerate(SCAN_MODES, 1):
        print(f"  [{i}]  {mode['label']:<20}  {mode['desc']}")
    print()

    while True:
        choice = input(f"  Select [1-{len(SCAN_MODES)}]: ").strip()
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(SCAN_MODES):
                return SCAN_MODES[idx - 1]
        print("  Invalid selection, try again.")


def select_ship_tier(stations_active: bool) -> int:
    """
    Prompts for a ship scan tier.

    Tier 2 needs station sector data so it is only offered when the stations
    pass is also running. Tier 3 discovers player ship sectors inside the ship
    scan itself, so it works independently of the stations pass.
    """
    print()
    print("  ── SHIP SCAN TIER ─────────────────────────────────────────────────")
    print()
    print("  [1]  Player ships only                    (fastest)")
    if stations_active:
        print("  [2]  + NPC ships in sectors with stations")
    print("  [3]  + NPC ships in all player ship sectors")
    print()

    valid = {1, 3} | ({2} if stations_active else set())

    while True:
        choice = input(f"  Select [1/{'2/' if stations_active else ''}3]: ").strip()
        if choice.isdigit() and int(choice) in valid:
            return int(choice)
        print("  Invalid selection, try again.")


# ─────────────────────────────────────────────────────────────────────────────
#  PASS RUNNERS
#  Each function runs exactly one scanner pass and returns its raw output.
#  The dispatcher below decides which ones to call — nothing runs twice.
# ─────────────────────────────────────────────────────────────────────────────

def _run_stations_pass(save_file: pathlib.Path, sector_names: dict) -> dict:
    t0     = time.perf_counter()
    result = scan_save(save_file, sector_names)
    print(f"[Done] Stations pass completed in {time.perf_counter() - t0:.2f}s")
    return result


def _run_reputation_pass(save_file: pathlib.Path) -> list:
    t0     = time.perf_counter()
    result = scan_reputation(save_file)
    print(f"[Done] Reputation pass completed in {time.perf_counter() - t0:.2f}s")
    return result


def _run_ships_pass(
    save_file:    pathlib.Path,
    sector_names: dict,
    ship_tier:    int,
    station_sectors: set | None,
) -> dict:
    """
    Runs the ships pass at the requested tier.

    Tier 3 uses one scan:
      - collect player ships normally
      - collect slim NPC ship records for all sectors
      - after the scan, build the player-sector set and filter NPC ships down

    This is faster than the old two-scan approach because we only stream the
    huge save file once. The tradeoff is keeping temporary slim NPC records in
    memory until we know which sectors matter.

    Tiers 1 and 2 do a single scan — no pre-scan needed.
    """
    ship_sectors = None

    if ship_tier == 3:
        # Tier 3 wants NPC ships in every sector where we have a player ship.
        # We only know those sectors after player ships have been parsed.
        #
        # collect_all_npcs=True tells scan_ships() to keep slim records for all
        # NPC ships during the same pass. Once the pass is finished, we can
        # filter those NPC rows down to the sectors we actually care about.
        t0     = time.perf_counter()
        result = scan_ships(
            save_file,
            sector_names,
            station_sectors=station_sectors,
            collect_all_npcs=True,
        )
        print(f"[Done] Ships pass completed in {time.perf_counter() - t0:.2f}s")

        ship_sectors = (
            {s["sector"] for s in result["player_ships"]}
            | (station_sectors or set())
        )

        # Keep only NPC ships in the final tier 3 context sectors.
        # The temporary all-NPC list is intentionally slim: no crew, hull, or
        # shield data is parsed for NPC ships, so this filter stays cheap.
        result["npc_ships"] = [
            s for s in result["npc_ships"]
            if s["sector"] in ship_sectors
        ]

        return {
            "player_ships": result["player_ships"],
            "npc_ships":    result["npc_ships"],
            "crew":         result.get("crew", []),
        }

    else:
        # Tiers 1 and 2 — single scan, no duplication.
        t0     = time.perf_counter()
        result = scan_ships(
            save_file, sector_names,
            station_sectors=station_sectors,
        )
        print(f"[Done] Ships pass completed in {time.perf_counter() - t0:.2f}s")
        return result


# ─────────────────────────────────────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        SAVE_FILE = select_save_file()
        print(f"\n  Loading: {SAVE_FILE.name}")

        mode = select_mode()
        passes = mode["passes"]

        ship_tier = 1
        if "ships" in passes:
            ship_tier = select_ship_tier(stations_active="stations" in passes)

        print()

        # Sector names are needed by both the stations and ships passes.
        # Load once and share — no point reading the language file twice.
        t0 = time.perf_counter()
        sector_names = load_sector_names(LANG_FILE)
        print(f"[Done] Sector names loaded in {time.perf_counter() - t0:.2f}s")

        # ── Build game_data incrementally from whichever passes run ───────────
        # Initialise with empty stubs so display_results() always gets a complete
        # dict regardless of which passes were skipped.
        game_data: dict = {
            "player_name":      None,
            "player_credits":   None,
            "player_sector":    None,
            "stations":         [],
            "reputation":       [],
            "ships":            {"player_ships": [], "npc_ships": []},
            "crew":               [],
            "managers":           [],
            "stations_scanned":   False,
            "reputation_scanned": False,
            "ships_scanned":      False,
        }

        # ── Pass 1: stations ──────────────────────────────────────────────────
        if "stations" in passes:
            result = _run_stations_pass(SAVE_FILE, sector_names)
            game_data.update(result)
            # Managers from Pass 1 seed the crew list; ship crew is added below.
            game_data["crew"] = result.get("managers", [])
            game_data["stations_scanned"] = True

        # ── Pass 2: reputation ────────────────────────────────────────────────
        if "reputation" in passes:
            game_data["reputation"] = _run_reputation_pass(SAVE_FILE)
            game_data["reputation_scanned"] = True

        # ── Pass 3: ships ─────────────────────────────────────────────────────
        if "ships" in passes:
            # Station sectors are only available if Pass 1 ran — otherwise None
            # and the ships pass will treat it as tier 1 regardless.
            station_sectors = (
                {s["sector"] for s in game_data["stations"]}
                if "stations" in passes else None
            )
            ships_result = _run_ships_pass(
                SAVE_FILE, sector_names, ship_tier, station_sectors
            )
            # If the stations pass also ran, plug any station-docked player ships
            # that the ship scanner missed back into player_ships now — before
            # the JSON export — so they appear in the fleet with translated names.
            if "stations" in passes:
                merge_station_docked_ships(
                    game_data["stations"],
                    ships_result["player_ships"],
                )

            game_data["ships"] = {
                "player_ships": ships_result["player_ships"],
                "npc_ships":    ships_result["npc_ships"],
            }
            # Append ship crew after station managers so managers appear first.
            game_data["crew"] += ships_result.get("crew", [])
            game_data["ships_scanned"] = True

        display_results(game_data)

        if mode["export"]:
            export_json(game_data, output_dir=SCRIPT_DIR)

    except Exception as e:
        print(f"\n[FATAL ERROR] {e}")
        traceback.print_exc()

    input("\nPress Enter to exit...")
