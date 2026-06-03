"""
v2/db/connection.py

Opens (creating if needed) the X4 Foresight SQLite database and applies the
schema. One entry point: get_connection().
"""
from __future__ import annotations
import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent / 'schema.sql'

# Default location — project root alongside the JSON export.
DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / 'x4_foresight.db'


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
    conn.commit()
