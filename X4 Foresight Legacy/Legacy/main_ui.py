"""
X4 Foundations Empire Intelligence — PyQt6 + QtWebEngine UI
Loads x4_empire_state.json and renders the HTML dashboard in a native window.

Requirements:
    pip install PyQt6 PyQt6-WebEngine pywebview qtpy

Usage:
    python main_ui.py
    python main_ui.py --json path/to/x4_empire_state.json
"""

import json
import os
import sys
import argparse

from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineScript
from PyQt6.QtCore import QUrl, QObject, pyqtSlot
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtGui import QIcon


# ── Python → JS bridge ────────────────────────────────────────────────────────

class EmpireBridge(QObject):
    """
    Exposed to the frontend as window.bridge via QWebChannel.
    Add methods here as the UI grows.
    """

    def __init__(self, data: dict):
        super().__init__()
        self._data = data

    @pyqtSlot(result=str)
    def get_empire_data(self) -> str:
        """Return the full empire state as a JSON string."""
        return json.dumps(self._data)


# ── Main window ───────────────────────────────────────────────────────────────

class EmpireWindow(QMainWindow):

    def __init__(self, data: dict, html_path: str):
        super().__init__()
        self.setWindowTitle("X4 · Empire Intelligence")
        self.resize(1200, 800)
        self.setMinimumSize(900, 600)

        # Web view
        self.view = QWebEngineView()

        # Set up the WebChannel bridge so JS can call Python
        self.channel = QWebChannel()
        self.bridge  = EmpireBridge(data)
        self.channel.registerObject("bridge", self.bridge)
        self.view.page().setWebChannel(self.channel)

        self.setCentralWidget(self.view)
        self.view.setUrl(QUrl.fromLocalFile(os.path.abspath(html_path)))


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_json(path: str) -> dict:
    if not os.path.exists(path):
        print(f"[Error] File not found: {path}")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="X4 Empire Intelligence UI")
    parser.add_argument(
        "--json",
        default="x4_empire_state.json",
        help="Path to empire state JSON (default: x4_empire_state.json)",
    )
    args = parser.parse_args()
    data = load_json(args.json)

    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui.html")
    if not os.path.exists(html_path):
        print("[Error] ui.html not found — make sure it is in the same directory as main_ui.py.")
        sys.exit(1)

    app = QApplication(sys.argv)
    app.setApplicationName("X4 Empire Intelligence")

    window = EmpireWindow(data, html_path)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
