"""Core role: QtWebEngine desktop shell for the empire state dashboard (ui.html).

Manages scan scheduling, JSON export delivery via QWebChannel bridge, and background scanning threads.
"""

import sys

# ── Chromium subprocess guard ─────────────────────────────────────────────────
# A PyInstaller-frozen build can re-use the main exe as QtWebEngine's Chromium
# renderer host; Chromium passes --type=renderer (etc.) in that case. Bail out
# before any Qt code so we never spawn an infinite loop of windows. Harmless in
# source mode (no such arg is ever present).
if any(arg.startswith('--type=') for arg in sys.argv[1:]):
    sys.exit(0)

import json
import os
import traceback
from datetime import datetime
from pathlib import Path

# Under pythonw.exe (the .pyw double-click path) there is no console, so
# sys.stdout / sys.stderr are None and any print() — including the scanner's
# CLI report — would raise. Redirect to the null device in that case. When a
# real console is attached we leave it alone (and widen the encoding so the
# report's box-drawing glyphs don't choke on cp1252).
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w', encoding='utf-8')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w', encoding='utf-8')
elif hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from PyQt6.QtCore import QObject, QThread, QUrl, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineCore import QWebEngineProfile
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QLabel, QListWidget,
    QMainWindow, QMessageBox, QProgressBar, QPushButton, QVBoxLayout,
)

# ── Path setup — works as source and (later) as a PyInstaller bundle ──────────
# In source mode the repo root is one level above ui/; we add it to sys.path so
# `import x4_save_scanner` (and the scanner packages it pulls in) resolves.
if getattr(sys, 'frozen', False):
    ROOT      = Path(sys.executable).parent
    HTML_PATH = Path(sys._MEIPASS) / "ui" / "ui.html"
else:
    ROOT = Path(__file__).resolve().parent.parent
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    HTML_PATH = Path(__file__).resolve().parent / "ui.html"

# The scanner module owns the canonical paths + the run() pipeline. Reusing its
# constants means the UI and the CLI always read/write the same files.
import x4_save_scanner as scanner
from x4_save_scanner import DB_PATH, JSON_PATH, ROOT_SAVE, _find_game_saves_dir

# The bridge now serves the dashboard straight from the SQLite DB rather than the
# on-disk JSON: to_export() is already a pure DB-read that produces the exact
# export shape the page consumes, so the file is no longer in the UI's read path.
# (scanner.run() still writes the JSON for the AI consumer + dev browser fallback.)
from db.connection import get_connection
from export.jsonexport import to_export, resource_library_export


# ── Save discovery + selector ─────────────────────────────────────────────────

def find_saves() -> list[Path]:
    """All X4 saves (manual then autosaves, each sorted by slot name).

    Reuses the scanner's save-directory locator so the UI and CLI agree on where
    saves live.
    """
    saves_dir = _find_game_saves_dir()
    if not saves_dir:
        return []
    manual = sorted(saves_dir.glob("save_*.xml.gz"),     key=lambda p: p.name)
    auto   = sorted(saves_dir.glob("autosave_*.xml.gz"), key=lambda p: p.name)
    return list(manual) + list(auto)


class SaveSelectDialog(QDialog):
    """Lists available saves (plus the project-root save_001.xml if present)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("X4 · Select Save")
        self.setMinimumWidth(480)

        self._saves = find_saves()
        # Offer the repo-root dev save as a final option when it exists.
        if ROOT_SAVE.exists():
            self._saves.append(ROOT_SAVE)

        latest = (
            max(self._saves, key=lambda p: p.stat().st_mtime)
            if self._saves else None
        )

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Select a save file to scan:"))

        self._list = QListWidget()
        for save in self._saves:
            mtime = datetime.fromtimestamp(save.stat().st_mtime)
            label = save.name.replace(".xml.gz", "")
            tag   = "  ← latest" if save is latest else ""
            self._list.addItem(f"{label}   {mtime.strftime('%a %d %b  %H:%M')}{tag}")

        if latest and self._saves:
            self._list.setCurrentRow(self._saves.index(latest))
        self._list.itemDoubleClicked.connect(self.accept)
        layout.addWidget(self._list)

        btns = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        scan = QPushButton("Scan")
        scan.setDefault(True)
        scan.clicked.connect(self.accept)
        btns.addWidget(cancel)
        btns.addWidget(scan)
        layout.addLayout(btns)

    def selected_path(self) -> Path | None:
        row = self._list.currentRow()
        return self._saves[row] if row >= 0 and self._saves else None


# ── Scanner background thread ─────────────────────────────────────────────────

class ScanWorker(QThread):
    """Runs the full scan pipeline off the UI thread.

    No data is carried on `finished`: run() writes x4_empire_state.json, and the
    bridge reads that file from disk — so the UI always sees the canonical export
    shape rather than a separately-marshalled object.
    """

    progress = pyqtSignal(str)
    finished = pyqtSignal()
    error    = pyqtSignal(str)

    def __init__(self, save_path: Path):
        super().__init__()
        self._save_path = save_path

    def run(self):
        try:
            # progress.emit is thread-safe (queued to the UI thread), so the
            # scanner can call it directly from this worker thread.
            scanner.run(self._save_path, progress=self.progress.emit)
            self.finished.emit()
        except Exception as e:
            self.error.emit(f"{e}\n\n{traceback.format_exc()}")


class ScanProgressDialog(QDialog):
    """Modal indeterminate-progress dialog shown while ScanWorker runs.

    The scanner doesn't report granular phase progress to the UI yet, so this is
    a busy spinner rather than a percentage bar.
    """

    def __init__(self, save_path: Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("X4 · Scanning")
        self.setMinimumWidth(420)
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Scanning: {save_path.name}"))
        # Live phase line, updated from the worker's progress signal.
        self._status = QLabel("Starting…")
        layout.addWidget(self._status)
        bar = QProgressBar()
        bar.setRange(0, 0)
        layout.addWidget(bar)

        self.error_msg: str | None = None
        self._worker = ScanWorker(save_path)
        self._worker.progress.connect(self._status.setText)
        self._worker.finished.connect(self.accept)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_error(self, msg: str):
        self.error_msg = msg
        self.reject()


# ── Python → JS bridge ────────────────────────────────────────────────────────

class EmpireBridge(QObject):
    """The single object the page reaches through QWebChannel.

    Builds the export FROM the database on each call (via to_export), so a re-scan
    — or switching to an older scan_id — is reflected without restarting and
    without touching the JSON file. A fresh read-only connection is opened per
    call: WAL mode lets these reads run alongside a concurrent scan write, and
    sqlite connections aren't safe to share across the threads Qt may dispatch
    slots on. The page owns the parse.
    """

    def __init__(self, window=None):
        super().__init__()
        self._window = window

    @pyqtSlot(result=str)
    def trigger_scan(self) -> str:
        """Show the save-picker and run the scan pipeline on the main thread.
        Returns {"ok": true} on success or {"ok": false, "cancelled": true} if
        the user dismissed the dialog without scanning."""
        try:
            success = run_scan(self._window)
            return json.dumps({"ok": success, "cancelled": not success})
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})

    @pyqtSlot(result=str)
    def get_resource_library(self) -> str:
        """Static equipment/hull catalog — no DB or scan required, so the
        Resource Library tab works before any scan has ever been run."""
        try:
            return json.dumps(resource_library_export(), ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": f"Could not build resource library: {e}"})

    @pyqtSlot(int, result=str)
    def get_empire_data(self, scan_id: int = -1) -> str:
        """Return the export JSON for `scan_id`; -1 (the JS default) = latest scan."""
        try:
            conn = get_connection(DB_PATH)
            try:
                data = to_export(conn, None if scan_id < 0 else scan_id)
            finally:
                conn.close()
            return json.dumps(data, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": f"Could not read empire data from DB: {e}"})

    @pyqtSlot(result=str)
    def list_scans(self) -> str:
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

    @pyqtSlot(int, result=str)
    def delete_scan(self, scan_id: int) -> str:
        """Delete a scan and all its cascaded child rows (foreign_keys = ON handles cascade).
        Returns JSON {"ok": true} on success or {"error": "..."} on failure."""
        try:
            conn = get_connection(DB_PATH)
            try:
                conn.execute("DELETE FROM scans WHERE scan_id = ?", (scan_id,))
                # If the table is now empty, reset the AUTOINCREMENT counter so
                # the next scan starts from 1 again instead of continuing from
                # the highest ever-used id.
                remaining = conn.execute("SELECT COUNT(*) FROM scans").fetchone()[0]
                if remaining == 0:
                    conn.execute("DELETE FROM sqlite_sequence WHERE name = 'scans'")
                conn.commit()
            finally:
                conn.close()
            return json.dumps({"ok": True})
        except Exception as e:
            return json.dumps({"error": f"Could not delete scan: {e}"})


# ── Main window ───────────────────────────────────────────────────────────────

class EmpireWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("X4 · Empire Intelligence")
        self.resize(1536, 960)        # 1536px is the UI's zoom=1.0 reference width
        self.setMinimumSize(900, 600)

        # QtWebEngine's default profile keeps a persistent on-disk HTTP cache
        # that survives full app restarts -- it caches the ui/css and ui/js
        # files loaded via file://, so editing them while developing (or
        # pulling an update from git) can silently keep showing stale styles
        # forever. There's no upside to caching local files for this app, so
        # disable it outright rather than rely on the user clearing a cache
        # they don't know exists.
        QWebEngineProfile.defaultProfile().setHttpCacheType(
            QWebEngineProfile.HttpCacheType.NoCache)

        self.view    = QWebEngineView()
        self.channel = QWebChannel()
        self.bridge  = EmpireBridge(self)
        self.channel.registerObject("bridge", self.bridge)
        self.view.page().setWebChannel(self.channel)
        self.setCentralWidget(self.view)
        self.view.setUrl(QUrl.fromLocalFile(str(HTML_PATH.resolve())))
        self.showMaximized()


# ── Launch flow ───────────────────────────────────────────────────────────────

def run_scan(parent=None) -> bool:
    """Show the save picker then scan. Returns True if a scan completed (the
    JSON on disk is now fresh), False if the user cancelled."""
    selector = SaveSelectDialog(parent)
    if selector.exec() != QDialog.DialogCode.Accepted:
        return False
    save_path = selector.selected_path()
    if save_path is None:
        return False

    progress = ScanProgressDialog(save_path, parent)
    if progress.exec() == QDialog.DialogCode.Accepted:
        return True
    if progress.error_msg:
        QMessageBox.critical(parent, "Scan Error", progress.error_msg)
    return False


def main() -> int:
    # Qt's default HiDPI policy rounds the OS scale factor to the nearest
    # integer (e.g. 125%/150% -> 100%/200%) before QtWebEngine ever sees the
    # window size. A real browser uses the exact OS scale, so the same
    # innerWidth-based zoom math in js/init.js produced visibly different
    # sizing between this app and the web build. PassThrough uses the exact
    # scale factor, matching browser behavior. Must be set before QApplication
    # is constructed.
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("X4 Empire Intelligence")

    # No language-file setup step anymore: the scanner reads t/0001-l044.xml
    # straight from the game's .cat archives (see scanner/language.py).

    if JSON_PATH.exists():
        reply = QMessageBox.question(
            None, "X4 · Empire Intelligence",
            "Existing empire data found.\nRun a new scan?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            run_scan()   # on cancel/failure we just fall back to existing JSON
    else:
        # Nothing to show yet — a scan is mandatory on the very first run.
        if not run_scan():
            return 0

    if not HTML_PATH.exists():
        QMessageBox.critical(None, "Error", f"ui.html not found at:\n{HTML_PATH}")
        return 1

    window = EmpireWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
