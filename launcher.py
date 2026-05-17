"""
X4 Empire Intelligence — PyInstaller entry point.

This file is the frozen-build entry point. X4_Empire_Intelligence.pyw
is used for source-mode double-click launching only.

All PyQt6 imports live here at the top level so PyInstaller's static
analyser has an unambiguous dependency tree to follow.
"""

import sys

# ── Chromium subprocess guard ─────────────────────────────────────────────────
# PyInstaller + QtWebEngine can use the main exe as the Chromium renderer host.
# Chromium passes --type=renderer (or similar) in argv in that case.
# Exit immediately — before any Qt code — to prevent an infinite spawn loop.
if any(arg.startswith('--type=') for arg in sys.argv[1:]):
    sys.exit(0)

import pathlib

# ── Path setup ────────────────────────────────────────────────────────────────
# Add the project root to sys.path so scanner/data/export packages are found.
if getattr(sys, 'frozen', False):
    ROOT = pathlib.Path(sys.executable).parent
else:
    ROOT = pathlib.Path(__file__).parent

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ── Explicit Qt imports ───────────────────────────────────────────────────────
# Listed here so PyInstaller's analyser sees them unconditionally.
# Do not move these inside conditionals or functions.
from PyQt6.QtCore import QObject, QThread, QUrl, Qt, pyqtSignal, pyqtSlot  # noqa: F401
from PyQt6.QtWebChannel import QWebChannel                                  # noqa: F401
from PyQt6.QtWebEngineWidgets import QWebEngineView                         # noqa: F401
from PyQt6.QtWidgets import (                                               # noqa: F401
    QApplication, QDialog, QFileDialog, QHBoxLayout, QLabel, QListWidget,
    QMainWindow, QMessageBox, QProgressBar, QPushButton, QVBoxLayout,
)

# ── Launch ────────────────────────────────────────────────────────────────────
from ui.main_ui import main  # noqa: E402

if __name__ == '__main__':
    main()
