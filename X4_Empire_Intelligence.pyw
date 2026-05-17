"""
X4 Empire Intelligence — Windows launcher (source mode only).
Double-click to run the UI without a console window.
The PyInstaller build uses ui/main_ui.py as its entry point directly.
"""

import os
import subprocess
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
subprocess.run([sys.executable, os.path.join("ui", "main_ui.py")])
