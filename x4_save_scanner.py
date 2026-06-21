"""Core role: Command-line entry point (select save → scan → resolve → write DB → write JSON)."""
from __future__ import annotations
import sys
import time
from pathlib import Path
from datetime import datetime
from typing import Callable

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scanner.scanner import Scanner
from scanner.trade_postprocess import TradePostProcessor
from db.connection import get_connection
from db.write import write_scan
from export.jsonexport import write_export
from display import display_report

# Outputs and inputs live in the project root.
LANG_FILE = ROOT / '0001-l044.xml'
DB_PATH   = ROOT / 'x4_foresight.db'
JSON_PATH = ROOT / 'x4_empire_state.json'
ROOT_SAVE = ROOT / 'save_001.xml'


# ── Save selection (.gz + root fallback) ───────────────────────────────────────

def _find_game_saves_dir() -> Path | None:
    """Locate the X4 save directory under Documents\\Egosoft\\X4\\{steamid}\\save."""
    x4_base = Path.home() / "Documents" / "Egosoft" / "X4"
    if x4_base.exists():
        for d in sorted(x4_base.iterdir()):
            candidate = d / "save"
            if candidate.is_dir():
                return candidate
    return None


def select_save_file() -> Path:
    """List available saves and prompt for one. Falls back to the root save_001.xml."""
    saves_dir = _find_game_saves_dir()
    manual = auto = []
    if saves_dir:
        manual = sorted(saves_dir.glob("save_*.xml.gz"),     key=lambda p: p.name)
        auto   = sorted(saves_dir.glob("autosave_*.xml.gz"), key=lambda p: p.name)
    all_saves = list(manual) + list(auto)

    if not all_saves and not ROOT_SAVE.exists():
        print("\n  [Error] No X4 saves found and no save_001.xml in the project root.")
        sys.exit(1)

    # If the only option is the root save, just use it — no need to prompt.
    if not all_saves and ROOT_SAVE.exists():
        print(f"  Using project-root save: {ROOT_SAVE.name}")
        return ROOT_SAVE

    latest = max(all_saves, key=lambda p: p.stat().st_mtime)

    print("\n  ── SELECT SAVE ────────────────────────────────────────────────")
    print(f"  Directory: {saves_dir}\n")
    for i, save in enumerate(all_saves, 1):
        mtime = datetime.fromtimestamp(save.stat().st_mtime)
        tag   = "  <- latest" if save is latest else ""
        print(f"  [{i:>2}]  {save.name.replace('.xml.gz',''):<20}  "
              f"{mtime.strftime('%a %d %b  %H:%M')}{tag}")
    if ROOT_SAVE.exists():
        print(f"\n   [R]  Project root  ({ROOT_SAVE.name})")

    prompt = f"\n  Select [1-{len(all_saves)} / L=latest / R=root]: "
    while True:
        choice = input(prompt).strip().upper()
        if choice == 'L':
            return latest
        if choice == 'R' and ROOT_SAVE.exists():
            return ROOT_SAVE
        if choice.isdigit() and 1 <= int(choice) <= len(all_saves):
            return all_saves[int(choice) - 1]
        print("  Invalid selection, try again.")


# ── Pipeline ───────────────────────────────────────────────────────────────────

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


def run(save_path: Path, progress: Callable[[str], None] | None = None) -> None:
    """Run the full pipeline: scan -> resolve trades -> write DB -> write JSON.

    `progress`, when supplied, is called with a short status string at the start
    of each phase. The GUI uses it to update its scan dialog; the CLI passes
    None and relies on printed output instead. The single-pass scan can't be
    subdivided, so it's reported as one (long) phase.
    """
    def step(msg: str) -> None:
        if progress is not None:
            progress(msg)

    print(f"\n  Scanning {save_path.name} ...")
    t0 = time.perf_counter()

    step("Scanning save — extracting empire (this is the long part)…")
    scanner = Scanner(lang_path=LANG_FILE)
    ctx = scanner.scan(save_path, scan_id=1)   # scan_id is reassigned by the DB

    step("Resolving trade counterparties…")
    TradePostProcessor().run(ctx)

    step("Resolving ship homebases…")
    resolve_ship_homebases(ctx)

    step("Writing database…")
    conn = get_connection(DB_PATH)
    scan_id = write_scan(conn, ctx)

    step("Writing JSON export…")
    write_export(conn, JSON_PATH)
    conn.close()

    step("Finalising…")
    elapsed = time.perf_counter() - t0
    display_report(ctx)
    _footer(ctx, scan_id, elapsed)


def _footer(ctx, scan_id, elapsed) -> None:
    """One-line output/timing footer after the full report."""
    print(f"  DB scan #{scan_id} -> {DB_PATH.name}   ·   Export -> {JSON_PATH.name}"
          f"   ·   {elapsed:.1f}s\n")


def main() -> None:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    print("=" * 64)
    print("  X4 FORESIGHT")
    print("=" * 64)

    if not LANG_FILE.exists():
        print(f"\n  [Warning] Language file {LANG_FILE.name} not found — "
              f"sector names will be unresolved.")

    # Optional save-path argument skips the picker (handy for scripting).
    if len(sys.argv) > 1:
        save = Path(sys.argv[1])
        if not save.exists():
            print(f"\n  [Error] Save not found: {save}")
            sys.exit(1)
    else:
        save = select_save_file()

    try:
        run(save)
    except Exception:
        import traceback
        print("\n  [ERROR] Scan failed:")
        traceback.print_exc()
    finally:
        # Keep the window open when double-clicked on Windows. Guard against
        # non-interactive / redirected stdin so it never tracebacks on exit.
        if sys.stdin and sys.stdin.isatty():
            try:
                input("\n  Press Enter to exit...")
            except EOFError:
                pass


if __name__ == '__main__':
    main()
