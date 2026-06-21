"""Core role: web-build entry points called from scan-worker.js via Pyodide.

Mirrors EmpireBridge's four QWebChannel slots in ui/main_ui.py, built on the
same pipeline x4_save_scanner.run() drives (scan -> resolve trades -> resolve
homebases -> write DB) minus its JSON-file-writing tail - get_empire_data
reads straight from the DB instead, same as the desktop bridge already does
for every call after the first.
"""
from __future__ import annotations
import json
import traceback
from pathlib import Path

from scanner.scanner import Scanner
from scanner.trade_postprocess import TradePostProcessor
from x4_save_scanner import resolve_ship_homebases
from db.connection import get_connection
from db.write import write_scan
from export.jsonexport import to_export

# MEMFS path inside Pyodide - this is a fresh, in-memory-per-session database
# (not the desktop app's on-disk file), so cross-reload history isn't
# expected yet; see the OPFS follow-up note in the project plan.
DB_PATH = "/home/pyodide/x4_foresight.db"


def run_scan_from_staged(save_path: str, lang_path: str, progress=None) -> str:
    """Run the full scan pipeline against an already-staged save file and
    language asset (both written into Pyodide's MEMFS by the caller).

    `progress`, when supplied, is called with a stage index (0-3) at the
    start of each phase - mirrors x4_save_scanner.run()'s progress callback,
    but with a plain index instead of a status string since the caller here
    is JS (scan-worker.js), which already owns its own display labels and
    just needs to know which stage is current.

    Returns JSON {"ok": true, "scan_id": N} or {"ok": false, "error": "..."}.
    """
    def step(stage: int) -> None:
        if progress is not None:
            progress(stage)

    try:
        # load_language_root() calls .exists() directly on lang_path, so it
        # must be a real Path - JS strings cross the Pyodide boundary as
        # plain Python str, not Path, even though Scanner's lang_path
        # parameter is typed Path | None.
        step(0)
        scanner = Scanner(lang_path=Path(lang_path))
        ctx = scanner.scan(save_path, scan_id=1)   # scan_id reassigned by the DB

        step(1)
        TradePostProcessor().run(ctx)

        step(2)
        resolve_ship_homebases(ctx)

        step(3)
        conn = get_connection(DB_PATH)
        try:
            scan_id = write_scan(conn, ctx)
        finally:
            conn.close()

        return json.dumps({"ok": True, "scan_id": scan_id})
    except Exception as e:
        return json.dumps({
            "ok": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        })


def get_empire_data(scan_id: int = -1) -> str:
    """Return the export JSON for `scan_id`; -1 = latest scan."""
    try:
        conn = get_connection(DB_PATH)
        try:
            data = to_export(conn, None if scan_id < 0 else scan_id)
        finally:
            conn.close()
        return json.dumps(data, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"Could not read empire data from DB: {e}"})


def list_scans() -> str:
    """Scan history for the picker: newest first, as a JSON array of
    {scan_id, scanned_at, save_file, game_time_s}. Empty array if none."""
    try:
        conn = get_connection(DB_PATH)
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


def delete_scan(scan_id: int) -> str:
    """Delete a scan and all its cascaded child rows (foreign_keys = ON
    handles cascade). Returns JSON {"ok": true} or {"error": "..."}."""
    try:
        conn = get_connection(DB_PATH)
        try:
            conn.execute("DELETE FROM scans WHERE scan_id = ?", (scan_id,))
            remaining = conn.execute("SELECT COUNT(*) FROM scans").fetchone()[0]
            if remaining == 0:
                conn.execute("DELETE FROM sqlite_sequence WHERE name = 'scans'")
            conn.commit()
        finally:
            conn.close()
        return json.dumps({"ok": True})
    except Exception as e:
        return json.dumps({"error": f"Could not delete scan: {e}"})
