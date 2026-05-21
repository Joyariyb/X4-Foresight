"""
X4 SAVE FILE — ECONOMY LOG INSPECTOR
======================================
Finds components that have an <economylog> child and dumps:
  - The component's macro and id attributes (to identify what it is)
  - The economylog cargo/offer values
  - All <trade> records inside that component's trade/offers section
  - The account balance if present

Captures up to MAX_SAMPLES such components then stops early.

Output:
  economylog_samples.txt

Run:
  python tools/inspect_economylog.py
"""

import gzip
import pathlib
import sys
import xml.etree.ElementTree as ET

PROJECT_ROOT = pathlib.Path(__file__).parent.parent
OUT_FILE     = PROJECT_ROOT / "economylog_samples.txt"
MAX_SAMPLES  = 20   # stop after this many economylog components found

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

# ── main ──────────────────────────────────────────────────────────────────────

def scan(path: pathlib.Path):
    """
    Strategy: buffer every top-level <component> inside <universe/connections/.../connections>
    that is at station depth (4 connection/component pairs deep).
    We identify stations by checking if they contain an <economylog> child.
    Because the file is huge we use a two-pass approach:
      Pass 1 - find component ids that have economylog (stream, low memory)
      Pass 2 - buffer those specific components and extract detail
    """

    # ── Pass 1: find component ids that contain economylog ───────────────────
    print("  Pass 1: finding components with economylog...")

    target_ids = []   # list of component id attribute values
    stack = []        # stack of (tag, attrib) tuples
    elem_count = 0

    with open_save(path) as f:
        for event, elem in ET.iterparse(f, events=("start", "end")):
            if event == "start":
                stack.append((elem.tag, dict(elem.attrib)))
                elem_count += 1
                if elem_count % 1_000_000 == 0:
                    print(f"    ... {elem_count:,} elements, {len(target_ids)} targets found")

            else:
                if elem.tag == "economylog":
                    # Walk up the stack to find the nearest enclosing component
                    for tag, attrib in reversed(stack):
                        if tag == "component" and "id" in attrib:
                            cid = attrib["id"]
                            if cid not in target_ids:
                                target_ids.append(cid)
                                if len(target_ids) >= MAX_SAMPLES:
                                    break
                            break

                stack.pop()
                elem.clear()

            if len(target_ids) >= MAX_SAMPLES:
                break

    print(f"  Found {len(target_ids)} target component ids: {target_ids[:5]}...")

    # ── Pass 2: buffer those components and extract detail ───────────────────
    print("  Pass 2: buffering target components...")

    results = []
    stack = []
    buffering = False
    buffer_depth = 0
    current_id = None
    buffer_elem = None
    elem_count = 0

    with open_save(path) as f:
        for event, elem in ET.iterparse(f, events=("start", "end")):
            if event == "start":
                stack.append(elem.tag)
                elem_count += 1
                if elem_count % 1_000_000 == 0:
                    print(f"    ... {elem_count:,} elements, {len(results)} extracted")

                if not buffering and elem.tag == "component":
                    cid = elem.get("id")
                    if cid in target_ids:
                        buffering = True
                        buffer_depth = len(stack)
                        current_id = cid
                        buffer_elem = elem   # latch root for in-memory build

            else:
                if buffering and len(stack) == buffer_depth and stack[-1] == "component":
                    # We've closed the buffered component — extract info
                    results.append(extract_info(buffer_elem))
                    buffering = False
                    buffer_elem = None
                    current_id = None
                    if len(results) >= MAX_SAMPLES:
                        break

                if not buffering:
                    elem.clear()
                stack.pop()

    return results


def extract_info(comp: ET.Element) -> dict:
    info = {
        "id":         comp.get("id", "?"),
        "macro":      comp.get("macro", "?"),
        "class":      comp.get("class", "?"),
        "economylog": {},
        "account":    {},
        "trades":     [],
        "prices":     [],
    }

    # economylog
    el = comp.find(".//economylog")
    if el is not None:
        info["economylog"] = dict(el.attrib)

    # account
    acc = comp.find(".//account")
    if acc is not None:
        info["account"] = dict(acc.attrib)

    # trade records (inside trade/offers/production/trade or orders/order/trade)
    for trade in comp.findall(".//trade"):
        t = dict(trade.attrib)
        if "ware" in t or "price" in t:
            info["trades"].append(t)

    # per-ware prices from trade/prices/reference
    for ware in comp.findall(".//trade/prices/reference/ware"):
        info["prices"].append(dict(ware.attrib))

    return info


def write_report(results: list):
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        for i, info in enumerate(results):
            f.write(f"{'=' * 70}\n")
            f.write(f"COMPONENT #{i+1}\n")
            f.write(f"  id:    {info['id']}\n")
            f.write(f"  macro: {info['macro']}\n")
            f.write(f"  class: {info['class']}\n\n")

            f.write(f"  ECONOMYLOG:\n")
            for k, v in info["economylog"].items():
                f.write(f"    {k} = {v}\n")
            if not info["economylog"]:
                f.write("    (none)\n")

            f.write(f"\n  ACCOUNT:\n")
            for k, v in info["account"].items():
                f.write(f"    {k} = {v}\n")
            if not info["account"]:
                f.write("    (none)\n")

            f.write(f"\n  TRADE RECORDS ({len(info['trades'])}):\n")
            for t in info["trades"][:10]:   # cap at 10 per component
                parts = "  ".join(f"{k}={v}" for k, v in sorted(t.items()))
                f.write(f"    {parts}\n")
            if len(info["trades"]) > 10:
                f.write(f"    ... ({len(info['trades']) - 10} more)\n")

            f.write(f"\n  REFERENCE PRICES ({len(info['prices'])} wares):\n")
            for p in info["prices"][:10]:
                parts = "  ".join(f"{k}={v}" for k, v in sorted(p.items()))
                f.write(f"    {parts}\n")
            if len(info["prices"]) > 10:
                f.write(f"    ... ({len(info['prices']) - 10} more)\n")

            f.write("\n")

    print(f"  Written: {OUT_FILE}")


if __name__ == "__main__":
    print()
    print("  X4 Economy Log Inspector")
    print("  ---------------------------------------------")
    save_path = find_save()
    results   = scan(save_path)
    write_report(results)
    print(f"  Done. {len(results)} components extracted.")
