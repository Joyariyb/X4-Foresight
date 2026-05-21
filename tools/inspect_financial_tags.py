"""
X4 SAVE FILE — FINANCIAL TAG INSPECTOR
========================================
Streams through the save file and, for each financially relevant tag,
captures:
  - Every unique path it appears at (parent context)
  - Every attribute name and its occurrence count
  - Up to MAX_SAMPLES unique values per attribute

Output:
  financial_tags.txt  — human-readable report

Run:
  python tools/inspect_financial_tags.py
"""

import gzip
import pathlib
import sys
import xml.etree.ElementTree as ET

# ── config ────────────────────────────────────────────────────────────────────

# Tags to inspect
FINANCIAL_TAGS = {
    "account", "buy", "sell", "prices", "trade", "traderule", "traderules",
    "tradeloopcargo", "economylog", "offer", "offers", "discount", "discounts",
    "commission", "commissions", "licence", "licences", "quota", "quotas",
    "quotalist", "quotalists", "production", "ware", "wares", "cargo",
    "resources", "nextresources", "workforce", "workforces", "shortage",
    "supplies", "yield", "yields", "stat", "stats", "history", "inventory",
}

# How many unique example values to keep per attribute
MAX_SAMPLES = 10

# ── paths ─────────────────────────────────────────────────────────────────────

PROJECT_ROOT = pathlib.Path(__file__).parent.parent
OUT_FILE     = PROJECT_ROOT / "financial_tags.txt"

# ── save discovery ────────────────────────────────────────────────────────────

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


# ── data structure ────────────────────────────────────────────────────────────
# results[tag][path] = { "count": int, "attrs": { attr: { "count": int, "samples": set } } }

def make_path_entry():
    return {"count": 0, "attrs": {}}


# ── main scan ─────────────────────────────────────────────────────────────────

def scan(path: pathlib.Path) -> dict:
    results = {tag: {} for tag in FINANCIAL_TAGS}
    stack: list[str] = []
    elem_count = 0

    print("  Scanning... (this may take a minute)")

    with open_save(path) as f:
        for event, elem in ET.iterparse(f, events=("start", "end")):
            if event == "start":
                stack.append(elem.tag)
                elem_count += 1

                if elem.tag in FINANCIAL_TAGS:
                    path_str = "/".join(stack)
                    tag_data = results[elem.tag]

                    if path_str not in tag_data:
                        tag_data[path_str] = make_path_entry()

                    entry = tag_data[path_str]
                    entry["count"] += 1

                    for attr, val in elem.attrib.items():
                        if attr not in entry["attrs"]:
                            entry["attrs"][attr] = {"count": 0, "samples": set()}
                        entry["attrs"][attr]["count"] += 1
                        if len(entry["attrs"][attr]["samples"]) < MAX_SAMPLES:
                            entry["attrs"][attr]["samples"].add(val)

                if elem_count % 500_000 == 0:
                    print(f"    ... {elem_count:,} elements processed")

            else:
                stack.pop()
                elem.clear()

    print(f"  Done. {elem_count:,} elements scanned.")
    return results


# ── output ────────────────────────────────────────────────────────────────────

def write_report(results: dict):
    with open(OUT_FILE, "w", encoding="utf-8") as f:

        for tag in sorted(results.keys()):
            paths = results[tag]
            if not paths:
                continue

            total = sum(p["count"] for p in paths.values())
            f.write(f"{'=' * 60}\n")
            f.write(f"TAG: <{tag}>  (total occurrences: {total:,})\n")
            f.write(f"{'=' * 60}\n\n")

            for path_str, entry in sorted(paths.items(), key=lambda x: -x[1]["count"]):
                f.write(f"  PATH: {path_str}\n")
                f.write(f"  COUNT: {entry['count']:,}\n")

                if entry["attrs"]:
                    f.write(f"  ATTRIBUTES:\n")
                    for attr, data in sorted(entry["attrs"].items()):
                        samples = sorted(data["samples"])
                        sample_str = ", ".join(f'"{s}"' for s in samples[:MAX_SAMPLES])
                        f.write(f"    {attr} ({data['count']:,}x)  eg: {sample_str}\n")
                else:
                    f.write(f"  ATTRIBUTES: none\n")

                f.write("\n")

    print(f"  Written: {OUT_FILE}")


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print()
    print("  X4 Financial Tag Inspector")
    print("  ---------------------------------------------")

    save_path = find_save()
    results   = scan(save_path)
    write_report(results)
