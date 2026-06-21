"""Maintainer tool: extracts X4's language file (t/0001-l044.xml) from the
locally installed game and writes it into ui/web/assets/ as a static asset
the web build bundles and ships to every visitor.

The language file is static game data - it changes only when Egosoft patches
X4, not per-user or per-save - so there's no reason to make every visitor's
browser extract it live from their own install. Re-run this alongside
gamefiles/generate_data.py whenever the game updates:

    python ui/web/extract_language_file.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from gamefiles.catalog import CatalogIndex, find_x4_install

OUT_PATH = Path(__file__).resolve().parent / "assets" / "lang_0001-l044.xml"


def main():
    game_dir = find_x4_install()
    if game_dir is None:
        print("No X4 installation found - can't extract the language file.")
        sys.exit(1)

    print(f"game dir: {game_dir}")
    index = CatalogIndex.from_game_dir(game_dir)

    # verify=True re-hashes against the .cat's md5 - cheap insurance since
    # this only runs occasionally, not on a hot path.
    raw = index.read('t/0001-l044.xml', verify=True)
    print(f"read {len(raw)} bytes, md5-verified")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_bytes(raw)
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
