"""Core role: Bridge operations shared by both UI shells (desktop EmpireBridge and the Pyodide web build).

One implementation instead of the near-verbatim copies ui/main_ui.py and
pyweb/web_entry.py used to carry — a fix applied here reaches both shells.

Every function returns a ready-to-ship JSON string and never raises across the
JS boundary: errors come back as {"error": "..."} so the page can render them.
db_path is a parameter because the shells disagree on where the DB lives (the
desktop uses the on-disk file next to the repo; Pyodide uses a MEMFS path).
A fresh connection is opened per call: WAL mode lets these reads run alongside
a concurrent scan write, and sqlite connections aren't safe to share across
the threads Qt may dispatch slots on.
"""
from __future__ import annotations
import json

from db.connection import get_connection
from export.jsonexport import to_export, resource_library_export


def get_resource_library() -> str:
    """Static equipment/hull catalog — no DB or scan required, so the
    Resource Library tab works before any scan has ever been run."""
    try:
        return json.dumps(resource_library_export(), ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"Could not build resource library: {e}"})


def get_empire_data(db_path, scan_id: int = -1) -> str:
    """Return the export JSON for `scan_id`; -1 (the JS default) = latest scan."""
    try:
        conn = get_connection(db_path)
        try:
            data = to_export(conn, None if scan_id < 0 else scan_id)
        finally:
            conn.close()
        return json.dumps(data, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"Could not read empire data from DB: {e}"})


def list_scans(db_path) -> str:
    """Scan history for the picker: newest first, as a JSON array of
    {scan_id, scanned_at, save_file, game_time_s}. Empty array if none."""
    try:
        conn = get_connection(db_path)
        try:
            rows = conn.execute(
                "SELECT scan_id, scanned_at, save_file, game_time_s "
                "FROM scans ORDER BY scan_id DESC"
            ).fetchall()
        finally:
            conn.close()
        return json.dumps([dict(r) for r in rows])
    except Exception as e:
        return json.dumps({"error": f"Could not list scans: {e}"})


def delete_scan(db_path, scan_id: int) -> str:
    """Delete a scan and all its cascaded child rows (foreign_keys = ON handles
    cascade). Returns JSON {"ok": true} or {"error": "..."}."""
    try:
        conn = get_connection(db_path)
        try:
            conn.execute("DELETE FROM scans WHERE scan_id = ?", (scan_id,))
            # If the table is now empty, reset the AUTOINCREMENT counter so the
            # next scan starts from 1 again instead of continuing from the
            # highest ever-used id.
            remaining = conn.execute("SELECT COUNT(*) FROM scans").fetchone()[0]
            if remaining == 0:
                conn.execute("DELETE FROM sqlite_sequence WHERE name = 'scans'")
            conn.commit()
        finally:
            conn.close()
        return json.dumps({"ok": True})
    except Exception as e:
        return json.dumps({"error": f"Could not delete scan: {e}"})


def delete_all_scans(db_path) -> str:
    """Delete every scan (and cascaded child rows). Returns JSON
    {"ok": true} or {"error": "..."}."""
    try:
        conn = get_connection(db_path)
        try:
            conn.execute("DELETE FROM scans")
            conn.execute("DELETE FROM sqlite_sequence WHERE name = 'scans'")
            conn.commit()
        finally:
            conn.close()
        return json.dumps({"ok": True})
    except Exception as e:
        return json.dumps({"error": f"Could not delete all scans: {e}"})
