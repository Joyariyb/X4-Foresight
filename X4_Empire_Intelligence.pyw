"""X4 Empire Intelligence — Windows double-click launcher (source mode).

Double-click this file to open the UI without a console window. It just runs
ui/main_ui.py with the same interpreter. (.pyw is associated with pythonw.exe,
which has no console — main_ui.py handles the resulting stdout=None case.)
"""

import os
import subprocess
import sys

# Run from the repo root so the scanner's relative paths (DB, JSON, lang file)
# resolve, regardless of where the file was double-clicked from.
ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
subprocess.run([sys.executable, os.path.join("ui", "main_ui.py")])
