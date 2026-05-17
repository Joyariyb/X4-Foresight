"""
X4 Foundations Empire Intelligence — PyQt6 + QtWebEngine UI

On launch:
  - If x4_empire_state.json exists, asks whether to run a new scan.
  - If no JSON exists, goes straight to the save selector.
  - Scanning runs in a background thread so the UI stays responsive.
  - Choosing "No" on the scan prompt loads the existing JSON immediately.

Requirements:
    pip install PyQt6 PyQt6-WebEngine
"""

import json
import os
import pathlib
import sys
import traceback
from datetime import datetime

from PyQt6.QtCore import QObject, QThread, QUrl, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QLabel, QListWidget,
    QMainWindow, QMessageBox, QProgressBar, QPushButton, QVBoxLayout,
)

# ── Project root on sys.path so scanner modules are importable ────────────────

ROOT = pathlib.Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scanner.language import load_sector_names, open_save  # noqa: E402
from scanner.scanner import scan_save, scan_reputation      # noqa: E402
from scanner.ship_scanner import scan_ships                 # noqa: E402
from export.jsonexport import export_json                   # noqa: E402

JSON_PATH = ROOT / "x4_empire_state.json"
LANG_PATH = ROOT / "0001-l044.xml"
HTML_PATH = pathlib.Path(__file__).parent / "ui.html"


# ── Save discovery ────────────────────────────────────────────────────────────

def find_saves() -> list[pathlib.Path]:
    """
    Returns all X4 save files (manual saves then autosaves, each sorted by
    slot number) found in the default game save directory.
    """
    x4_base   = pathlib.Path.home() / "Documents" / "Egosoft" / "X4"
    saves_dir = None

    if x4_base.exists():
        for d in sorted(x4_base.iterdir()):
            candidate = d / "save"
            if candidate.is_dir():
                saves_dir = candidate
                break

    if not saves_dir:
        return []

    manual = sorted(saves_dir.glob("save_*.xml.gz"),     key=lambda p: p.name)
    auto   = sorted(saves_dir.glob("autosave_*.xml.gz"), key=lambda p: p.name)
    return manual + auto


# ── Save selector dialog ──────────────────────────────────────────────────────

class SaveSelectDialog(QDialog):
    """Lists available saves and lets the user pick one to scan."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("X4 · Select Save")
        self.setMinimumWidth(480)

        self._saves = find_saves()
        latest      = (
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

    def selected_path(self) -> pathlib.Path | None:
        row = self._list.currentRow()
        return self._saves[row] if row >= 0 and self._saves else None


# ── Scanner background thread ─────────────────────────────────────────────────

class ScanWorker(QThread):
    progress = pyqtSignal(str)
    # No data on finished — after the scan we read the exported JSON from disk
    # rather than passing game_data directly. This matters because export_json()
    # restructures game_data into a different format that ui.html expects.
    finished = pyqtSignal()
    error    = pyqtSignal(str)

    def __init__(self, save_path: pathlib.Path):
        super().__init__()
        self._save_path = save_path

    def run(self):
        try:
            self.progress.emit("Loading sector names…")
            sector_names = load_sector_names(LANG_PATH)

            self.progress.emit("Pass 1 — player, stations…")
            game_data = scan_save(self._save_path, sector_names)

            self.progress.emit("Pass 2 — faction reputation…")
            game_data["reputation"] = scan_reputation(self._save_path)

            self.progress.emit("Pass 3 — ships…")
            game_data["ships"] = scan_ships(self._save_path, sector_names)

            self.progress.emit("Exporting JSON…")
            # export_json writes the restructured data to x4_empire_state.json.
            # We'll read that file back in the main thread rather than passing
            # game_data through the signal, so the UI always gets the right format.
            export_json(game_data, output_dir=ROOT)

            self.finished.emit()

        except Exception as e:
            self.error.emit(f"{e}\n\n{traceback.format_exc()}")


# ── Scan progress dialog ──────────────────────────────────────────────────────

class ScanProgressDialog(QDialog):
    """Modal dialog shown while the scanner runs in a background thread."""

    def __init__(self, save_path: pathlib.Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("X4 · Scanning")
        self.setMinimumWidth(420)
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)

        layout = QVBoxLayout(self)

        self._status = QLabel(f"Scanning: {save_path.name}")
        layout.addWidget(self._status)

        bar = QProgressBar()
        bar.setRange(0, 0)   # indeterminate spinner
        layout.addWidget(bar)

        self.error_msg: str | None = None

        self._worker = ScanWorker(save_path)
        self._worker.progress.connect(self._status.setText)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_finished(self):
        # Scan and export are done — close the dialog so the caller can
        # read the exported JSON from disk.
        self.accept()

    def _on_error(self, msg: str):
        self.error_msg = msg
        self.reject()


# ── Python → JS bridge ────────────────────────────────────────────────────────

class EmpireBridge(QObject):
    def __init__(self, data: dict):
        super().__init__()
        self._data = data

    @pyqtSlot(result=str)
    def get_empire_data(self) -> str:
        return json.dumps(self._data)


# ── Main window ───────────────────────────────────────────────────────────────

class EmpireWindow(QMainWindow):
    def __init__(self, data: dict):
        super().__init__()
        self.setWindowTitle("X4 · Empire Intelligence")
        self.resize(1200, 800)
        self.setMinimumSize(900, 600)

        self.view    = QWebEngineView()
        self.channel = QWebChannel()
        self.bridge  = EmpireBridge(data)
        self.channel.registerObject("bridge", self.bridge)
        self.view.page().setWebChannel(self.channel)
        self.setCentralWidget(self.view)
        self.view.setUrl(QUrl.fromLocalFile(str(HTML_PATH.resolve())))


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_json(path: pathlib.Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def run_scan(parent=None) -> dict | None:
    """
    Shows the save selector then runs the scanner.
    Returns the resulting data dict, or None if the user cancelled.
    """
    selector = SaveSelectDialog(parent)
    if selector.exec() != QDialog.DialogCode.Accepted:
        return None

    save_path = selector.selected_path()
    if save_path is None:
        return None

    progress = ScanProgressDialog(save_path, parent)
    if progress.exec() == QDialog.DialogCode.Accepted:
        # The scan wrote x4_empire_state.json — read that back now.
        # We use the file rather than in-memory data because export_json()
        # reshapes game_data into the structure ui.html actually expects.
        return load_json(JSON_PATH)

    if progress.error_msg:
        QMessageBox.critical(parent, "Scan Error", progress.error_msg)
    return None


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("X4 Empire Intelligence")

    json_exists = JSON_PATH.exists()
    data = None

    if json_exists:
        reply = QMessageBox.question(
            None,
            "X4 · Empire Intelligence",
            "Existing empire data found.\nRun a new scan?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            data = run_scan()
            if data is None:
                # User cancelled the selector — fall back to existing JSON
                data = load_json(JSON_PATH)
        else:
            data = load_json(JSON_PATH)
    else:
        data = run_scan()
        if data is None:
            sys.exit(0)   # No JSON and user cancelled — nothing to show

    if not HTML_PATH.exists():
        QMessageBox.critical(None, "Error", f"ui.html not found at:\n{HTML_PATH}")
        sys.exit(1)

    window = EmpireWindow(data)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
