"""
X4 Empire Intelligence — Windows launcher
Double-click this file to run the UI with no console window.
"""

import subprocess
import sys
import os

os.chdir(os.path.dirname(os.path.abspath(__file__)))
subprocess.run([sys.executable, os.path.join("ui", "main_ui.py")])
