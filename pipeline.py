"""Core role: Shared scan pipeline (scan -> resolve trades -> resolve homebases -> DB -> optional JSON) + canonical file paths.

Extracted from x4_save_scanner.py so the three shells (CLI, desktop UI, Pyodide
web build) run one pipeline instead of each re-assembling the phases. Entry
points stay thin: they pick a save, wire a progress display, and call
run_pipeline().
"""
from __future__ import annotations
from pathlib import Path
from typing import Callable

from scanner.scanner import Scanner
from scanner.trade_postprocess import TradePostProcessor
from db.connection import get_connection
from db.write import write_scan
from export.jsonexport import write_export

# Canonical inputs/outputs — project root (the repo IS the program). The web
# build ignores these and passes explicit MEMFS paths instead.
ROOT = Path(__file__).resolve().parent
LANG_FILE = ROOT / '0001-l044.xml'
DB_PATH   = ROOT / 'x4_foresight.db'
JSON_PATH = ROOT / 'x4_empire_state.json'
ROOT_SAVE = ROOT / 'save_001.xml'


def find_game_saves_dir() -> Path | None:
    """Locate the X4 save directory under Documents\\Egosoft\\X4\\{steamid}\\save."""
    x4_base = Path.home() / "Documents" / "Egosoft" / "X4"
    if x4_base.exists():
        for d in sorted(x4_base.iterdir()):
            candidate = d / "save"
            if candidate.is_dir():
                return candidate
    return None


def resolve_ship_homebases(ctx) -> None:
    """Resolve homebase_id to a player station object_id for all player ships.

    Both _parse_homebase() (traders) and _parse_commander() (all other types)
    return sub-component connection references, NOT the station's own object_id.
    For example, a freighter's TradeRoutine `range` param gives [0x1b6f8], and
    its commander connection gives [0x1ca1f] — both are connection elements on
    the station, not the station root.

    dockingbay_index maps every sub-element id on a player station → that
    station's object_id (now built from elem.iter() so <connection> elements
    are included alongside <component> elements).  We resolve both homebase_id
    and commander_id through this index:

      1. If homebase_id is already set (from _parse_homebase) but is a
         sub-component ref rather than a station object_id, resolve it.
      2. If homebase_id is unset, try commander_id (miners, fighters, etc.).

    The player_station_ids guard ensures we only accept player stations —
    ships commanded by NPC stations or capital ships are left unresolved.
    """
    player_stations = ctx.player_station_ids
    for ship in ctx.ships:
        # Already a direct station object_id — nothing to do.
        if ship.homebase_id in player_stations:
            continue

        # Try each candidate ref in priority order:
        #   1. homebase_id set by _parse_homebase (TradeRoutine range / Middleman supplier)
        #   2. commander_id set by _parse_commander (miners, fighters, etc.)
        # Both are sub-component connection refs, so we look each up in
        # dockingbay_index which maps every sub-element id → parent station id.
        # We try homebase_id first so traders get the most-specific attribution;
        # if that lookup fails we fall through to commander_id as a fallback.
        for ref in (ship.homebase_id, ship.commander_id):
            if not ref:
                continue
            resolved = ctx.dockingbay_index.get(ref)
            if resolved and resolved in player_stations:
                ship.homebase_id = resolved
                break


def run_pipeline(
    save_path: str | Path,
    *,
    lang_path: str | Path | None = LANG_FILE,
    db_path: str | Path = DB_PATH,
    json_path: str | Path | None = None,
    progress: Callable[[int, str], None] | None = None,
):
    """Run scan -> resolve trades -> resolve homebases -> write DB (-> write JSON).

    `progress`, when supplied, is called with (stage_index, label) at the start
    of each phase: 0 scan, 1 trade resolution, 2 homebase resolution, 3 DB
    write, 4 JSON export (only when json_path is given). The desktop dialog
    shows the label; the web worker keys its own display strings off the index
    — keep the numbering stable when inserting phases.

    json_path is opt-in because only the CLI and desktop keep the on-disk JSON
    fresh (the AI consumer + the no-bridge browser dev fallback); the bridges
    themselves read the DB directly.

    Returns (ctx, scan_id).
    """
    def step(stage: int, msg: str) -> None:
        if progress is not None:
            progress(stage, msg)

    step(0, "Scanning save — extracting empire (this is the long part)…")
    # Coerce to Path: JS strings cross the Pyodide boundary as plain str, and
    # load_language_root() calls .exists() on the value directly.
    scanner = Scanner(lang_path=Path(lang_path) if lang_path else None)
    ctx = scanner.scan(save_path, scan_id=1)   # scan_id is reassigned by the DB

    step(1, "Resolving trade counterparties…")
    TradePostProcessor().run(ctx)

    step(2, "Resolving ship homebases…")
    resolve_ship_homebases(ctx)

    step(3, "Writing database…")
    conn = get_connection(db_path)
    try:
        scan_id = write_scan(conn, ctx)
        if json_path is not None:
            step(4, "Writing JSON export…")
            write_export(conn, json_path)
    finally:
        conn.close()

    return ctx, scan_id
