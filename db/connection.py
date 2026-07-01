"""Core role: Opens/creates SQLite database and applies schema (entry point: get_connection())."""
from __future__ import annotations
import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent / 'schema.sql'

# Default location — project root alongside the JSON export.
DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / 'x4_foresight.db'


def get_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    """
    Return a connection to the Foresight DB, creating the file and schema on
    first use.

    - row_factory = sqlite3.Row so callers can read columns by name.
    - foreign_keys ON so deleting a scan cascades to its history rows.
    - WAL journal so reads (the UI) don't block a write (a scan).
    """
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    conn.execute('PRAGMA journal_mode = WAL')
    apply_schema(conn)
    return conn


def apply_schema(conn: sqlite3.Connection) -> None:
    """Run schema.sql. Every statement is CREATE ... IF NOT EXISTS, so this is
    idempotent and safe to call on every connection."""
    conn.executescript(SCHEMA_PATH.read_text(encoding='utf-8'))
    _migrate(conn)
    _populate_ware_metadata(conn)
    _populate_ware_prices(conn)
    conn.commit()


def _migrate(conn: sqlite3.Connection) -> None:
    """Apply additive migrations that schema.sql's CREATE IF NOT EXISTS can't handle."""
    existing = {row[1] for row in conn.execute('PRAGMA table_info(station_inventory)')}
    if 'volume_m3' not in existing:
        conn.execute('ALTER TABLE station_inventory ADD COLUMN volume_m3 REAL')

    # time_to_cap_hours added when overproduction detector was implemented.
    # ALTER TABLE appends the column at the physical end of the table on old DBs,
    # even though schema.sql declares it between surplus_rate and runtime_minutes.
    # write.py uses an explicit column-name INSERT to cope with this — positional
    # VALUES(?) would map values to the wrong columns on migrated databases.
    # Old rows will have NULL for this column until the station is re-scanned.
    spa_cols = {row[1] for row in conn.execute('PRAGMA table_info(station_production_analytics)')}
    if 'time_to_cap_hours' not in spa_cols:
        conn.execute('ALTER TABLE station_production_analytics ADD COLUMN time_to_cap_hours REAL')

    # is_discovered added when sector fog-of-war (knownto="player") was surfaced.
    # ALTER appends it at the table's physical end, which matches schema.sql
    # declaring it as the last sectors column — so write.py's positional INSERT
    # stays correct on both fresh and migrated databases.
    sec_cols = {row[1] for row in conn.execute('PRAGMA table_info(sectors)')}
    if 'is_discovered' not in sec_cols:
        conn.execute('ALTER TABLE sectors ADD COLUMN is_discovered INTEGER')

    # ships_destroyed added when the combat-trends (kills/losses) feature landed.
    # Appended at the scans table's physical end, matching schema.sql's last-column
    # placement, so write.py's explicit-column INSERT stays correct on both fresh and
    # migrated DBs. Old scans read NULL until re-scanned. (combat_kills is a new table,
    # so CREATE IF NOT EXISTS handles it — no migration needed there.)
    scan_cols = {row[1] for row in conn.execute('PRAGMA table_info(scans)')}
    if 'ships_destroyed' not in scan_cols:
        conn.execute('ALTER TABLE scans ADD COLUMN ships_destroyed INTEGER')

    # is_buying/is_selling/price/amount/illegal added when NPC station wares
    # gained buy/sell direction (previously just a flat ware-name list). All
    # appended at the table's physical end, after schema.sql's declared
    # ware_name column — write.py uses an explicit column-name INSERT so this
    # matches on both fresh and migrated DBs. Old rows read 0/NULL until the
    # station is re-scanned.
    nsw_cols = {row[1] for row in conn.execute('PRAGMA table_info(npc_station_wares)')}
    if 'is_buying' not in nsw_cols:
        conn.execute('ALTER TABLE npc_station_wares ADD COLUMN is_buying INTEGER NOT NULL DEFAULT 0')
        conn.execute('ALTER TABLE npc_station_wares ADD COLUMN is_selling INTEGER NOT NULL DEFAULT 0')
        conn.execute('ALTER TABLE npc_station_wares ADD COLUMN price INTEGER')
        conn.execute('ALTER TABLE npc_station_wares ADD COLUMN amount INTEGER')
        conn.execute('ALTER TABLE npc_station_wares ADD COLUMN illegal INTEGER NOT NULL DEFAULT 0')


def _populate_ware_metadata(conn: sqlite3.Connection) -> None:
    """Write static ware properties from data/wares.py into ware_metadata.

    Uses INSERT OR IGNORE so this is safe to call on every connection — existing
    rows are never touched. The full set of wares is the union of WARE_NAMES,
    WARE_TRANSPORT, and WARE_VOLUME (some wares appear in only one or two of
    the three dicts, so we take the union to ensure complete coverage).
    """
    from data.wares import WARE_NAMES, WARE_TRANSPORT, WARE_VOLUME
    all_ids = set(WARE_NAMES) | set(WARE_TRANSPORT) | set(WARE_VOLUME)
    rows = [
        (
            ware_id,
            WARE_NAMES.get(ware_id, ware_id),      # fall back to raw id if unnamed
            WARE_TRANSPORT.get(ware_id),
            WARE_VOLUME.get(ware_id),
        )
        for ware_id in sorted(all_ids)
    ]
    conn.executemany("INSERT OR IGNORE INTO ware_metadata VALUES(?,?,?,?)", rows)


def _populate_ware_prices(conn: sqlite3.Connection) -> None:
    """Write market price bands from data/ware_prices.py into ware_prices.

    Uses INSERT OR IGNORE so re-running on an existing DB is a no-op. Each ware
    gets the min/average/max price band extracted from the game's wares.xml.
    """
    from data.ware_prices import WARE_PRICES
    rows = [
        (ware_id, p['min'], p['average'], p['max'])
        for ware_id, p in sorted(WARE_PRICES.items())
    ]
    conn.executemany("INSERT OR IGNORE INTO ware_prices VALUES(?,?,?,?)", rows)
