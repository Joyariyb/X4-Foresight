"""
X4 SAVE FILE — STATS DUMPER
=============================
Extracts all <stat> elements from savegame/stats and dumps
every id/value pair to stats_dump.txt.

Run:
  python tools/dump_stats.py
"""

import gzip
import pathlib
import sys
import xml.etree.ElementTree as ET

PROJECT_ROOT = pathlib.Path(__file__).parent.parent
OUT_FILE     = PROJECT_ROOT / "stats_dump.txt"

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
        all_saves = sorted(saves_dir.glob("save_*.xml.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
    root_save = PROJECT_ROOT / "save_001.xml"
    if all_saves:
        print(f"  Using: {all_saves[0]}")
        return all_saves[0]
    elif root_save.exists():
        return root_save
    else:
        sys.exit("  [Error] No save file found.")

def open_save(path: pathlib.Path):
    return gzip.open(path, "rb") if path.suffix == ".gz" else open(path, "rb")

if __name__ == "__main__":
    print()
    print("  X4 Stats Dumper")
    print("  ---------------------------------------------")
    save_path = find_save()

    stats = []
    stack = []

    with open_save(save_path) as f:
        for event, elem in ET.iterparse(f, events=("start", "end")):
            if event == "start":
                stack.append(elem.tag)
                # Only capture stats directly under savegame/stats
                if elem.tag == "stat" and stack == ["savegame", "stats", "stat"]:
                    stats.append((elem.get("id", "?"), elem.get("value", "?")))
            else:
                stack.pop()
                elem.clear()
                # Stop after we leave savegame/stats
                if elem.tag == "stats" and len(stack) == 1:
                    break

    stats.sort(key=lambda x: x[0])

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        f.write(f"savegame/stats — {len(stats)} entries\n")
        f.write("-" * 50 + "\n\n")
        for sid, val in stats:
            f.write(f"  {sid:<45} {val}\n")

    print(f"  {len(stats)} stats written to {OUT_FILE}")
