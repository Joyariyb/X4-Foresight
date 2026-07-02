"""Core role: web-build entry points called from scan-worker.js via Pyodide.

Exposes the same operations as EmpireBridge's QWebChannel slots in
ui/main_ui.py: the scan entry point calls the shared run_pipeline()
(pipeline.py) against Pyodide's MEMFS database, and everything else delegates
to export/bridge_api.py — both implementations shared with the desktop shell.
"""
from __future__ import annotations
import json
import traceback

from pipeline import run_pipeline
from export import bridge_api

# MEMFS path inside Pyodide - this is a fresh, in-memory-per-session database
# (not the desktop app's on-disk file), so cross-reload history isn't
# expected yet; see the OPFS follow-up note in the project plan.
DB_PATH = "/home/pyodide/x4_foresight.db"


def run_scan_from_staged(save_path: str, lang_path: str, progress=None) -> str:
    """Run the shared pipeline against an already-staged save file and
    language asset (both written into Pyodide's MEMFS by the caller).

    `progress`, when supplied, is called with a plain stage index (0-3) at the
    start of each phase - scan-worker.js owns its own display labels and just
    needs to know which stage is current, so run_pipeline's label argument is
    dropped here. No json_path: the web build reads the DB only.

    Returns JSON {"ok": true, "scan_id": N} or {"ok": false, "error": "..."}.
    """
    try:
        _ctx, scan_id = run_pipeline(
            save_path,
            lang_path=lang_path,
            db_path=DB_PATH,
            progress=(lambda stage, _msg: progress(stage))
                     if progress is not None else None,
        )
        return json.dumps({"ok": True, "scan_id": scan_id})
    except Exception as e:
        return json.dumps({
            "ok": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        })


def get_resource_library() -> str:
    """Static equipment/hull catalog — see export/bridge_api.py."""
    return bridge_api.get_resource_library()


def get_empire_data(scan_id: int = -1) -> str:
    """Return the export JSON for `scan_id`; -1 = latest scan."""
    return bridge_api.get_empire_data(DB_PATH, scan_id)


def list_scans() -> str:
    """Scan history for the picker, newest first."""
    return bridge_api.list_scans(DB_PATH)


def delete_scan(scan_id: int) -> str:
    """Delete a scan and all its cascaded child rows."""
    return bridge_api.delete_scan(DB_PATH, scan_id)


def delete_all_scans() -> str:
    """Delete every scan (and cascaded child rows)."""
    return bridge_api.delete_all_scans(DB_PATH)
