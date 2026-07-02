"""Regenerates py-manifest.json - the list of Python source files
ui/web/js/scan-worker.js fetches and writes into Pyodide's virtual
filesystem at boot.

Run this whenever a .py file is added to or removed from scanner/, data/,
db/, or export/ (gamefiles/ is intentionally excluded - see PACKAGE_DIRS
below for why). Re-run: python ui/web/generate_manifest.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = Path(__file__).resolve().parent / "py-manifest.json"

# Package roots the live scan/export/storage pipeline actually needs.
# gamefiles/ is deliberately excluded: the only live use of it was reading
# one file (t/0001-l044.xml) out of the game's .cat/.dat archives, which the
# web build now bundles as a pre-extracted static asset instead (see
# extract_language_file.py) rather than reading the archives live.
PACKAGE_DIRS = ["scanner", "data", "db", "export", "pyweb"]

# Top-level modules (not inside one of the package dirs above) the web
# pipeline also needs. pipeline.py is the shared scan pipeline web_entry.py
# calls; its module-level path constants are harmless inside Pyodide's
# sandboxed filesystem (web_entry passes explicit MEMFS paths instead).
# x4_save_scanner.py and display.py are no longer staged: the CLI shell and
# its console report became desktop-only once web_entry stopped importing
# them (they used to ride along just to satisfy an import chain).
TOP_LEVEL_MODULES = ["pipeline.py"]


def main():
    paths = []
    for pkg in PACKAGE_DIRS:
        pkg_dir = ROOT / pkg
        for ext in ("*.py", "*.sql"):
            for path in sorted(pkg_dir.rglob(ext)):
                # __init__.py files are empty package markers here (verified -
                # none of them have real code), and GitHub Pages' Jekyll build
                # silently 404s any underscore-prefixed file regardless of a
                # .nojekyll marker. Skipping them is safe: Python 3's implicit
                # namespace packages (PEP 420) work fine with no __init__.py
                # on disk, as long as the directory itself exists - which it
                # does, since every package dir here has other staged files.
                if path.name == "__init__.py":
                    continue
                paths.append(path.relative_to(ROOT).as_posix())
    paths.extend(TOP_LEVEL_MODULES)
    paths.sort()

    OUT_PATH.write_text(json.dumps(paths, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(paths)} entries to {OUT_PATH}")


if __name__ == "__main__":
    main()
