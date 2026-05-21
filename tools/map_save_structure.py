"""
X4 SAVE FILE — XML STRUCTURE MAPPER
=====================================
Streams through the entire save file and builds a database of:
  - Every unique tag path (parent/child relationships)
  - Every attribute name seen on each tag
  - Occurrence counts
  - All unique values of key attributes (title, category, type, state, kind)

Special output: all unique <entry title="..."> values from the <log> section,
so we can find the English equivalent of "Handel abgeschlossen".

Outputs:
  save_structure.json   — full tag/attribute database
  log_titles.txt        — every unique log entry title, sorted alphabetically

Run:
  python tools/map_save_structure.py
"""

import collections
import gzip
import json
import pathlib
import sys
from lxml import etree as ET

# ── paths ─────────────────────────────────────────────────────────────────────

SCRIPT_DIR = pathlib.Path(__file__).parent.parent   # project root
OUT_JSON   = SCRIPT_DIR / "save_structure.json"
OUT_TITLES = SCRIPT_DIR / "log_titles.txt"

# Attributes whose unique values we collect (kept bounded — not price/id/etc.)
COLLECT_VALUES_FOR = {"title", "category", "type", "state", "kind", "faction",
                      "class", "group", "sector", "owner", "product"}

# ── save discovery (mirrors x4_save_scanner.py logic) ────────────────────────

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

    root_save = SCRIPT_DIR / "save_001.xml"

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

def scan(path: pathlib.Path):
    # tag_info[path_string] = {"count": int, "attrs": {attr: count}, "values": {attr: {val: count}}}
    tag_info: dict[str, dict] = {}

    # parent stack — list of tag names, e.g. ["savegame", "universe", "component"]
    stack: list[str] = []

    log_titles: dict[str, int] = {}   # title value → count
    entry_count = 0
    elem_count  = 0

    print("  Scanning… (this may take a minute)")

    with open_save(path) as f:
        for event, elem in ET.iterparse(f, events=("start", "end")):
            if event == "start":
                stack.append(elem.tag)
                path_str = "/".join(stack)

                if path_str not in tag_info:
                    tag_info[path_str] = {"count": 0, "attrs": {}, "values": {}}

                info = tag_info[path_str]
                info["count"] += 1
                elem_count += 1

                for attr, val in elem.attrib.items():
                    info["attrs"][attr] = info["attrs"].get(attr, 0) + 1

                    # Collect unique values for selected attributes
                    if attr in COLLECT_VALUES_FOR:
                        if attr not in info["values"]:
                            info["values"][attr] = {}
                        info["values"][attr][val] = info["values"][attr].get(val, 0) + 1

                # Capture log entry titles
                if elem.tag == "entry" and "title" in elem.attrib:
                    entry_count += 1
                    t = elem.attrib["title"]
                    log_titles[t] = log_titles.get(t, 0) + 1

                if elem_count % 500_000 == 0:
                    print(f"    … {elem_count:,} elements processed, {len(tag_info):,} unique paths")

            else:  # end
                stack.pop()
                elem.clear()

    print(f"  Done. {elem_count:,} elements, {len(tag_info):,} unique paths, {entry_count:,} log entries")
    return tag_info, log_titles


# ── serialise ─────────────────────────────────────────────────────────────────

def save_outputs(tag_info: dict, log_titles: dict):
    # Sort paths for readability
    ordered = dict(sorted(tag_info.items()))

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(ordered, f, indent=2, ensure_ascii=False)
    print(f"  Written: {OUT_JSON}")

    with open(OUT_TITLES, "w", encoding="utf-8") as f:
        f.write(f"# Unique <entry title=...> values in <log> section\n")
        f.write(f"# Total distinct titles: {len(log_titles)}\n\n")
        for title, count in sorted(log_titles.items(), key=lambda x: x[0]):
            f.write(f"[{count:>6}x]  {title}\n")
    print(f"  Written: {OUT_TITLES}")


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print()
    print("  X4 Save Structure Mapper")
    print("  ─────────────────────────────────────────────")

    save_path = find_save()
    tag_info, log_titles = scan(save_path)
    save_outputs(tag_info, log_titles)

    print()
    print(f"  Log entry titles ({len(log_titles)} unique):")
    for title, count in sorted(log_titles.items(), key=lambda x: -x[1])[:30]:
        print(f"    [{count:>6}x]  {title}")
