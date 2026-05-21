"""
X4 SAVE FILE — TRANSACTION LOG INSPECTOR
==========================================
Two things:
  1. Buffers and dumps the full savegame/economylog subtree (raw XML)
  2. Samples up to MAX_ENTRY_SAMPLES <log><entry> elements whose title
     contains any of the TRADE_KEYWORDS, showing all attributes

Output:
  transaction_log_samples.txt

Run:
  python tools/inspect_transaction_logs.py
"""

import gzip
import pathlib
import sys
import xml.etree.ElementTree as ET

PROJECT_ROOT    = pathlib.Path(__file__).parent.parent
OUT_FILE        = PROJECT_ROOT / "transaction_log_samples.txt"
MAX_ENTRY_SAMPLES = 40

# Keywords to match against <entry title="..."> values
TRADE_KEYWORDS = {
    "trade", "sold", "bought", "purchase", "money", "credit", "payment",
    "profit", "revenue", "ware", "cargo", "deliver", "transfer", "account",
    "fund", "earn", "income", "sell", "buy", "econom",
}

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

# ── helpers ───────────────────────────────────────────────────────────────────

def title_matches(title: str) -> bool:
    low = title.lower()
    return any(kw in low for kw in TRADE_KEYWORDS)

def elem_to_text(elem: ET.Element, indent: int = 0) -> str:
    """Render an element and its children as indented text (not full XML)."""
    pad  = "  " * indent
    line = f"{pad}<{elem.tag}"
    for k, v in elem.attrib.items():
        line += f' {k}="{v}"'
    children = list(elem)
    if not children and not (elem.text and elem.text.strip()):
        line += " />"
        return line
    line += ">"
    if elem.text and elem.text.strip():
        line += elem.text.strip()
    lines = [line]
    for child in children:
        lines.append(elem_to_text(child, indent + 1))
    lines.append(f"{pad}</{elem.tag}>")
    return "\n".join(lines)

# ── scan ──────────────────────────────────────────────────────────────────────

def scan(path: pathlib.Path):
    economylog_elem  = None
    entry_samples    = []
    seen_titles      = set()

    stack           = []
    in_log          = False
    buffering_econlog = False
    econlog_depth   = None
    econlog_buf     = None
    elem_count      = 0

    print("  Scanning...")

    with open_save(path) as f:
        for event, elem in ET.iterparse(f, events=("start", "end")):
            if event == "start":
                stack.append(elem.tag)
                elem_count += 1

                if elem_count % 1_000_000 == 0:
                    print(f"    ... {elem_count:,} elements")

                depth = len(stack)

                # Detect savegame/economylog (depth 2)
                if depth == 2 and elem.tag == "economylog" and not buffering_econlog:
                    buffering_econlog = True
                    econlog_depth     = depth
                    econlog_buf       = elem

                # Detect savegame/log (depth 2)
                if depth == 2 and elem.tag == "log":
                    in_log = True

            else:
                depth = len(stack)

                # Close of savegame/economylog
                if buffering_econlog and depth == econlog_depth and elem.tag == "economylog":
                    economylog_elem   = econlog_buf
                    buffering_econlog = False

                # Log entries
                if in_log and elem.tag == "entry":
                    title = elem.get("title", "")
                    if title_matches(title) and title not in seen_titles:
                        seen_titles.add(title)
                        entry_samples.append(dict(elem.attrib))
                        if len(entry_samples) >= MAX_ENTRY_SAMPLES:
                            in_log = False

                if depth == 2 and elem.tag == "log":
                    in_log = False

                # Don't clear buffered elements
                if not buffering_econlog:
                    elem.clear()

                stack.pop()

            # Stop early if both collected
            if economylog_elem is not None and len(entry_samples) >= MAX_ENTRY_SAMPLES:
                break

    print(f"  Done. {elem_count:,} elements scanned.")
    return economylog_elem, entry_samples

# ── output ────────────────────────────────────────────────────────────────────

def write_report(econlog: ET.Element, entries: list):
    with open(OUT_FILE, "w", encoding="utf-8") as f:

        # Section 1 — savegame/economylog
        f.write("=" * 70 + "\n")
        f.write("SECTION 1: savegame/economylog (full subtree)\n")
        f.write("=" * 70 + "\n\n")

        if econlog is not None:
            children = list(econlog)
            f.write(f"  Direct children: {len(children)}\n")
            f.write(f"  Attributes: {dict(econlog.attrib) or '(none)'}\n\n")
            if children:
                f.write(elem_to_text(econlog))
            else:
                f.write("  (element is empty — no children or text)\n")
        else:
            f.write("  (not found in save file)\n")

        f.write("\n\n")

        # Section 2 — log entries
        f.write("=" * 70 + "\n")
        f.write(f"SECTION 2: <log><entry> samples matching trade keywords ({len(entries)} unique titles)\n")
        f.write("=" * 70 + "\n\n")

        for i, attrs in enumerate(entries):
            f.write(f"  Entry #{i+1}\n")
            for k, v in sorted(attrs.items()):
                f.write(f"    {k} = {v}\n")
            f.write("\n")

    print(f"  Written: {OUT_FILE}")


if __name__ == "__main__":
    print()
    print("  X4 Transaction Log Inspector")
    print("  ---------------------------------------------")
    save_path          = find_save()
    econlog, entries   = scan(save_path)
    write_report(econlog, entries)
