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

from scanner.language            import load_sector_names, load_text_pages
from scanner.scanner             import scan_save, scan_reputation, scan_trade_orders
from scanner.ship_scanner        import scan_ships, merge_station_docked_ships
from export.jsonexport           import export_json
from display                     import display_results

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
        "desc":   "All passes — stations, NPC stations, reputation, ships, trades + JSON export",
        "passes": ["stations", "reputation", "ships"],
        "export": True,
        # These bypass the interactive sub-prompts so the full scan runs
        # without stopping to ask questions. Other modes leave them absent,
        # which triggers the prompts as normal.
        "npc_stations": True,   # Pass 4 — resolves NPC counterparty codes in trade display
        "trade_log":    True,   # Pass 5 — active TradePerform orders
        "ship_tier":    1,      # Tier 1 captures all player ships (sufficient for trade filter)
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
    {
        "key":    "trade",
        "label":  "Trade log only",
        "desc":   "Active trade orders at player stations and ships (no reputation or JSON)",
        "passes": ["stations", "ships"],
        "export": False,
        # Stations pass provides player station IDs; ships pass provides player ship IDs.
        # NPC stations resolves counterparty codes in the trade display.
        # Reputation is intentionally excluded — not relevant to trade data.
        "npc_stations": True,
        "trade_log":    True,
        "ship_tier":    1,
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


def select_npc_stations() -> bool:
    """Asks whether to include NPC stations in player sectors (Pass 4)."""
    print()
    print("  ── NPC STATIONS ───────────────────────────────────────────────────")
    print()
    print("  Include NPC stations in sectors where you have a player station?")
    print("  (adds ~5-15s depending on save size)")
    print()
    while True:
        choice = input("  [Y]es / [N]o: ").strip().upper()
        if choice in ('Y', 'YES'):
            return True
        if choice in ('N', 'NO'):
            return False
        print("  Invalid selection, try again.")


def select_trade_log() -> bool:
    """Asks whether to scan the economylog for completed player trade transactions."""
    print()
    print("  ── TRADE LOG ──────────────────────────────────────────────────────")
    print()
    print("  Include completed trade log? (reads economylog — usually fast)")
    print()
    while True:
        choice = input("  [Y]es / [N]o: ").strip().upper()
        if choice in ('Y', 'YES'):
            return True
        if choice in ('N', 'NO'):
            return False
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

def _run_trade_pass(
    save_file:          pathlib.Path,
    player_station_ids: set,
    id_to_code:         dict,
    player_ship_ids:    set,
) -> list:
    """
    Runs the active trade order scan (Pass 5).

    player_station_ids — hex object IDs of player-owned stations.
    player_ship_ids    — hex object IDs of player-owned ships. May be empty if
                         the ships pass was not run; in that case the ship-transport
                         filter is skipped and only station-based trades are returned.
    id_to_code         — combined player + NPC station map for display resolution.
    """
    t0     = time.perf_counter()
    result = scan_trade_orders(save_file, player_station_ids, id_to_code, player_ship_ids)
    print(f"[Done] Active trades pass completed in {time.perf_counter() - t0:.2f}s")
    return result


def _run_stations_pass(
    save_file: pathlib.Path,
    sector_names: dict,
    language_texts: dict,
    collect_npc_stations: bool = False,
) -> dict:
    """
    Runs Pass 1 (player stations). When collect_npc_stations=True, NPC station
    data is gathered in the same file read and returned under "npc_stations_raw".
    The caller filters that list to player sectors after the pass completes.
    """
    t0     = time.perf_counter()
    result = scan_save(save_file, sector_names, language_texts, collect_npc_stations)
    print(f"[Done] Stations pass completed in {time.perf_counter() - t0:.2f}s")
    return result


def _run_reputation_pass(save_file: pathlib.Path) -> list:
    t0     = time.perf_counter()
    result = scan_reputation(save_file)
    print(f"[Done] Reputation pass completed in {time.perf_counter() - t0:.2f}s")
    return result


def _run_ships_pass(
    save_file:            pathlib.Path,
    sector_names:         dict,
    ship_tier:            int,
    station_sectors:      set | None,
    sector_macro_to_name: dict | None = None,
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
            sector_macro_to_name=sector_macro_to_name,
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
            sector_macro_to_name=sector_macro_to_name,
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

        # Sub-options: use mode-level overrides when present (e.g. full scan),
        # otherwise fall through to the interactive prompts so the user can
        # choose per-run for modes that don't pre-set these values.
        include_npc_stations = False
        if "stations" in passes:
            if "npc_stations" in mode:
                include_npc_stations = mode["npc_stations"]
            else:
                include_npc_stations = select_npc_stations()

        include_trade_log = False
        if "stations" in passes:
            if "trade_log" in mode:
                include_trade_log = mode["trade_log"]
            else:
                include_trade_log = select_trade_log()

        ship_tier = 1
        if "ships" in passes:
            if "ship_tier" in mode:
                ship_tier = mode["ship_tier"]
            else:
                ship_tier = select_ship_tier(stations_active="stations" in passes)

        print()

        t_total = time.perf_counter()   # overall pipeline timer — printed after all passes complete

        # Sector names are needed by both the stations and ships passes.
        # Load once and share — no point reading the language file twice.
        t0 = time.perf_counter()
        sector_names   = load_sector_names(LANG_FILE)
        # Page 20102: station type names ({page,id} refs in name/basename attributes).
        # Page 20215: ware group factory names for multi-product station naming.
        # Page 20201: individual ware texts — resolves any {20201,N} refs found in
        #             save file attributes (station names, trade data, etc.) directly,
        #             without needing to go through the hardcoded WARE_FACTORY_NAMES lookup.
        language_texts = load_text_pages(LANG_FILE, {'20102', '20215', '20201'})
        print(f"[Done] Sector names loaded in {time.perf_counter() - t0:.2f}s")

        # ── Build game_data incrementally from whichever passes run ───────────
        # Initialise with empty stubs so display_results() always gets a complete
        # dict regardless of which passes were skipped.
        #
        # sector_macro_to_name is an internal lookup (sector macro → display name)
        # built as a free side effect of Pass 1. It is passed to Pass 3 so ships
        # can resolve their sector by direct dict lookup instead of regex parsing.
        # It is never merged into game_data and never exported.
        sector_macro_to_name: dict = {}

        game_data: dict = {
            "player_name":      None,
            "player_credits":   None,
            "player_sector":    None,
            "stations":         [],
            "npc_stations":     [],
            "reputation":       [],
            "ships":            {"player_ships": [], "npc_ships": []},
            "crew":               [],
            "managers":           [],
            "trades":             [],   # populated by the trade scanner pass (not yet implemented)
            "stations_scanned":   False,
            "reputation_scanned": False,
            "ships_scanned":      False,
            "trades_scanned":     False,
        }

        # ── Pass 1 (+4): stations ─────────────────────────────────────────────
        # When include_npc_stations=True, NPC station data is collected in the
        # same file read and returned as "npc_stations_raw". We filter that list
        # to player sectors here — a cheap in-memory operation — rather than
        # opening the file a second time.
        if "stations" in passes:
            result = _run_stations_pass(
                SAVE_FILE, sector_names, language_texts,
                collect_npc_stations=include_npc_stations,
            )
            # Pop the sector map before the general update — it's internal
            # plumbing for Pass 3 and should not land in game_data or the export.
            sector_macro_to_name = result.pop("sector_macro_to_name", {})
            game_data.update(result)
            # Managers from Pass 1 seed the crew list; ship crew is added below.
            game_data["crew"] = result.get("managers", [])
            game_data["stations_scanned"] = True

            if include_npc_stations:
                player_sectors = {s["sector"] for s in game_data["stations"]}
                npc_raw        = game_data.pop("npc_stations_raw", [])
                game_data["npc_stations"] = [
                    st for st in npc_raw if st["sector"] in player_sectors
                ]
                print(f"[Done] NPC stations — {len(game_data['npc_stations'])} in player "
                      f"sectors (filtered from {len(npc_raw)} total).")

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
                SAVE_FILE, sector_names, ship_tier, station_sectors,
                sector_macro_to_name=sector_macro_to_name,
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

        # ── Pass 5: active trades (optional, requires Pass 1) ────────────────
        # Finds all TradePerform orders in the save where a player station is
        # the buyer or seller, OR a player ship is the executing transport.
        # Station IDs come from Pass 1; ship IDs from Pass 3 (empty set if
        # the ships pass was skipped — ship-transport filtering is disabled).
        if include_trade_log:
            player_station_ids = {
                st["object_id"]
                for st in game_data["stations"]
                if st.get("object_id")
            }
            # Ship IDs are only available when Pass 3 ran. An empty set is safe —
            # scan_trade_orders treats it as "no ship filter" and falls back to
            # station-only filtering.
            player_ship_ids = {
                sh["object_id"]
                for sh in game_data["ships"].get("player_ships", [])
                if sh.get("object_id")
            }
            # Resolution map: player + NPC station hex IDs → display codes.
            # Ship IDs are not in this map — raw hex shows for unresolved ships,
            # but the ship's own code attribute is captured directly during scanning.
            id_to_code = {
                st["object_id"]: st["code"]
                for st in game_data["stations"] + game_data["npc_stations"]
                if st.get("object_id") and st.get("code")
            }
            game_data["trades"]         = _run_trade_pass(SAVE_FILE, player_station_ids, id_to_code, player_ship_ids)
            game_data["trades_scanned"] = True

        display_results(game_data)

        if mode["export"]:
            export_json(game_data, output_dir=SCRIPT_DIR)

        elapsed = time.perf_counter() - t_total
        mins    = int(elapsed // 60)
        secs    = elapsed % 60
        time_str = f"{mins}m {secs:.1f}s" if mins else f"{secs:.1f}s"
        print(f"\n  Total scan time: {time_str}")

    except Exception as e:
        print(f"\n[FATAL ERROR] {e}")
        traceback.print_exc()

    input("\nPress Enter to exit...")
