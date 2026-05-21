"""
X4 SAVE FILE — TAG NAME LISTER
================================
Streams through the save file and collects every unique XML tag name.

Output:
  tag_names.txt  — all unique tag names, sorted alphabetically, one per line

Run:
  python tools/list_tag_names.py
"""

import gzip
import pathlib
import sys
import xml.etree.ElementTree as ET

# ── paths ─────────────────────────────────────────────────────────────────────

PROJECT_ROOT = pathlib.Path(__file__).parent.parent
OUT_FILE     = PROJECT_ROOT / "tag_names.txt"

# ── save discovery (same logic as map_save_structure.py) ──────────────────────

def find_save() -> pathlib.Path:
    x4_base = pathlib.Path.home() / "Documents" / "Egosoft" / "X4"
    saves_dir = None

    if x4_base.exists():
        for d in sorted(x4_base.iterdir()):
            candidate = d / "save"
            if candidate.is_dir():
                saves_dir = candidate
                break

    all_saves = []
    if saves_dir:
        all_saves  = sorted(saves_dir.glob("save_*.xml.gz"),     key=lambda p: p.stat().st_mtime, reverse=True)
        all_saves += sorted(saves_dir.glob("autosave_*.xml.gz"), key=lambda p: p.stat().st_mtime, reverse=True)

    root_save = PROJECT_ROOT / "save_001.xml"

    if all_saves:
        print(f"  Using: {all_saves[0]}")
        return all_saves[0]
    elif root_save.exists():
        print(f"  Using: {root_save}")
        return root_save
    else:
        sys.exit("  [Error] No X4 save file found.")


def open_save(path: pathlib.Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rb")
    return open(path, "rb")


# ── main scan ─────────────────────────────────────────────────────────────────

def scan(path: pathlib.Path) -> set[str]:
    tag_names: set[str] = set()
    elem_count = 0

    print("  Scanning… (this may take a minute)")

    with open_save(path) as f:
        for event, elem in ET.iterparse(f, events=("start",)):
            tag_names.add(elem.tag)
            elem_count += 1
            elem.clear()

            if elem_count % 500_000 == 0:
                print(f"    … {elem_count:,} elements, {len(tag_names)} unique tags so far")

    print(f"  Done. {elem_count:,} elements, {len(tag_names)} unique tag names found.")
    return tag_names


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print()
    print("  X4 Tag Name Lister")
    print("  ---------------------------------------------")

    save_path = find_save()
    tag_names = scan(save_path)

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        for name in sorted(tag_names):
            f.write(name + "\n")

    print(f"  Written: {OUT_FILE}")
