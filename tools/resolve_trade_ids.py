"""
Pulls 5 real trade log entries from savegame/economylog/entries[type=trade],
then does a second pass to resolve buyer/seller component IDs to names and sectors.

Output: printed to console.
"""

import gzip
import pathlib
import sys
import xml.etree.ElementTree as ET

PROJECT_ROOT = pathlib.Path(__file__).parent.parent

STATION_CLASSES = {"station", "factory", "headquarters", "complex"}
SHIP_CLASSES    = {"ship_s", "ship_m", "ship_l", "ship_xl"}


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


# ── Pass 1: grab a handful of real trade entries ──────────────────────────────

def collect_trade_samples(path, n=5):
    samples = []
    stack = []
    in_trade_entries = False

    with open_save(path) as f:
        for event, elem in ET.iterparse(f, events=("start", "end")):
            if event == "start":
                stack.append(elem.tag)
                depth = len(stack)
                if depth == 3 and elem.tag == "entries" and elem.get("type") == "trade":
                    in_trade_entries = True
                if in_trade_entries and depth == 4 and elem.tag == "log":
                    if len(samples) < n:
                        samples.append(dict(elem.attrib))
            else:
                depth = len(stack)
                if depth == 3 and elem.tag == "entries":
                    in_trade_entries = False
                elem.clear()
                stack.pop()
            if len(samples) >= n and not in_trade_entries:
                break

    return samples


# ── Pass 2: resolve component IDs to names and sectors ────────────────────────

def resolve_ids(path, target_ids: set) -> dict:
    """
    Streams the universe component tree and builds a dict:
      component_id -> {"name": str, "class": str, "sector": str}

    Stops as soon as all target_ids are found (or the universe section ends).
    """
    resolved = {}
    current_sector = "Unknown Sector"
    stack = []       # stack of (tag, id) so we can track sector context

    with open_save(path) as f:
        for event, elem in ET.iterparse(f, events=("start", "end")):
            if event == "start":
                tag   = elem.tag
                cid   = elem.get("id", "")
                cls   = elem.get("class", "")
                stack.append((tag, cid, cls))

                if tag == "component":
                    if cls == "sector":
                        name = elem.get("name") or elem.get("macro", "Unknown Sector")
                        current_sector = name

                    if cid in target_ids and cid not in resolved:
                        name = elem.get("name") or elem.get("macro") or cid
                        resolved[cid] = {
                            "name":   name,
                            "class":  cls,
                            "sector": current_sector,
                        }

            else:
                stack.pop()
                elem.clear()

            # Stop once we have all IDs or leave the universe section
            if len(resolved) == len(target_ids):
                break

    return resolved


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    path = find_save()
    print(f"Save: {path}\n")

    print("Pass 1 — collecting trade log samples...")
    samples = collect_trade_samples(path)
    print(f"  Got {len(samples)} trade entries.\n")

    # Collect all component IDs we need to resolve
    target_ids = set()
    for s in samples:
        for key in ("buyer", "seller", "partner"):
            v = s.get(key, "")
            if v.startswith("["):
                target_ids.add(v)
    print(f"Pass 2 — resolving {len(target_ids)} component IDs: {target_ids}\n")

    resolved = resolve_ids(path, target_ids)
    print(f"  Resolved {len(resolved)} of {len(target_ids)} IDs.\n")

    print("=" * 60)
    print("TRADE LOG ENTRIES (with resolved names)")
    print("=" * 60)

    for i, entry in enumerate(samples, 1):
        buyer_id  = entry.get("buyer",  "—")
        seller_id = entry.get("seller", "—")
        buyer_r   = resolved.get(buyer_id,  {})
        seller_r  = resolved.get(seller_id, {})

        price_total = int(entry.get("price", 0))
        qty         = int(entry.get("v", 1))
        per_unit    = price_total / qty if qty else 0

        b     = int(entry.get("b",    0))
        bmax  = int(entry.get("bmax", 0))
        load  = f"{b / bmax * 100:.1f}%" if bmax else "—"

        print(f"\nEntry #{i}")
        print(f"  ware        : {entry.get('ware', '?')}")
        print(f"  quantity    : {qty:,}")
        print(f"  price/unit  : {per_unit:.2f} Cr")
        print(f"  price total : {price_total:,} Cr")
        print(f"  load        : {load}  (b={b}, bmax={bmax})")
        print(f"  buyer  {buyer_id:12}  -> name: {buyer_r.get('name','?')}  class: {buyer_r.get('class','?')}  sector: {buyer_r.get('sector','?')}")
        print(f"  seller {seller_id:12}  -> name: {seller_r.get('name','?')}  class: {seller_r.get('class','?')}  sector: {seller_r.get('sector','?')}")

    print()


if __name__ == "__main__":
    main()
