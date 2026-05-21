"""
Samples raw <log> entries from savegame/economylog/entries, grouped by
the parent <entries type="..."> so you can see one example of each type.

Output: printed to console.
"""

import gzip
import pathlib
import sys
import xml.etree.ElementTree as ET

PROJECT_ROOT = pathlib.Path(__file__).parent.parent

def find_save() -> pathlib.Path:
    x4_base = pathlib.Path.home() / "Documents" / "Egosoft" / "X4"
    if x4_base.exists():
        for d in sorted(x4_base.iterdir()):
            candidate = d / "save"
            if candidate.is_dir():
                saves = sorted(candidate.glob("save_*.xml.gz"),
                               key=lambda p: p.stat().st_mtime, reverse=True)
                if saves:
                    return saves[0]
    fallback = PROJECT_ROOT / "save_001.xml"
    if fallback.exists():
        return fallback
    sys.exit("No save file found.")

def open_save(path):
    return gzip.open(path, "rb") if path.suffix == ".gz" else open(path, "rb")

def scan(path, samples_per_type=3):
    """Stream the economylog/entries/log elements, collect samples per entries type."""
    samples = {}   # type_str -> list of attr dicts
    stack = []
    current_entries_type = None

    with open_save(path) as f:
        for event, elem in ET.iterparse(f, events=("start", "end")):
            if event == "start":
                stack.append(elem.tag)
                depth = len(stack)

                # savegame/economylog/entries  (depth 3)
                if depth == 3 and elem.tag == "entries":
                    current_entries_type = elem.get("type", "unknown")
                    if current_entries_type not in samples:
                        samples[current_entries_type] = []

                # savegame/economylog/entries/log  (depth 4)
                if depth == 4 and elem.tag == "log" and current_entries_type is not None:
                    bucket = samples.setdefault(current_entries_type, [])
                    if len(bucket) < samples_per_type:
                        bucket.append(dict(elem.attrib))

            else:
                depth = len(stack)
                if depth == 3 and elem.tag == "entries":
                    current_entries_type = None
                elem.clear()
                stack.pop()

            # Stop once we've collected enough samples for all types seen
            if all(len(v) >= samples_per_type for v in samples.values()) and len(samples) >= 4:
                break

    return samples

def main():
    path = find_save()
    print(f"Save: {path}\n")
    samples = scan(path)

    for etype, entries in samples.items():
        print("=" * 60)
        print(f"entries type=\"{etype}\"  ({len(entries)} samples)")
        print("=" * 60)
        for i, attrs in enumerate(entries, 1):
            print(f"\n  Log #{i}:")
            for k, v in attrs.items():
                print(f"    {k:12} = {v}")
    print()

if __name__ == "__main__":
    main()
