"""
generate_station_stats.py
=========================
Reads station module macro XMLs from 'station xml/' and shield equipment macro
XMLs from 'shield xml/', then writes data/station_stats.py.

STATION_STATS maps each macro name to its static game specs:
    max_hull    — module's base maximum hull HP (station structure modules)
    max_shield  — shield generator recharge capacity in HP (shield equipment)

HOW TO RUN:
    python generate_station_stats.py

REQUIRED INPUT:
    station xml/  — Station module macro XMLs from X4's .cat files.
                    Extract with XRCatTool: -include "structures.*macros.*_macro[.]xml"
    shield xml/   — Shield equipment macro XMLs from X4's .cat files.
                    Extract with XRCatTool: -include "SurfaceElements.*macros.*shield_.*[.]xml"
                    Also run against extensions/ego_dlc_*/ext_0*.cat for DLC shields.

Re-run after extracting new XMLs (e.g. after a DLC update).

HOW STATION_STATS IS USED:
    scanner/scanner.py imports STATION_STATS in _parse_station_health() to look
    up max_hull per module and max_shield per installed shield generator.
    Without this table the scanner can still run but cannot report percentages.
"""

import pathlib
import xml.etree.ElementTree as ET

# ── Paths ─────────────────────────────────────────────────────────────────────

MODULE_DIR = pathlib.Path(__file__).parent / "station xml"
SHIELD_DIR = pathlib.Path(__file__).parent / "shield xml"
OUT_FILE   = pathlib.Path(__file__).parent / "data" / "station_stats.py"

stats = {}  # { macro_name: { 'max_hull': int } or { 'max_shield': int } }

# ── Pass 1: Station module hull data ──────────────────────────────────────────
# Any XML with properties/hull[@max] that isn't shield equipment is captured.
# This avoids maintaining a hardcoded class list that could miss new module types.

if not MODULE_DIR.exists():
    print(f"[Warning] '{MODULE_DIR.name}/' not found — skipping module hull extraction.")
    print("  Extract station module XMLs with XRCatTool -include 'structures.*macros.*_macro\\.xml'")
else:
    module_files = list(MODULE_DIR.rglob("*.xml"))
    print(f"[Modules] Found {len(module_files)} XML files in '{MODULE_DIR.name}/'")
    hull_count  = 0
    skipped     = 0

    for xml_file in module_files:
        try:
            root       = ET.parse(xml_file).getroot()
            macro_elem = root.find("macro")
            if macro_elem is None:
                skipped += 1
                continue

            # Shield equipment lives in shield xml/ and is handled in Pass 2
            if macro_elem.get("class") == "shieldgenerator":
                skipped += 1
                continue

            props = macro_elem.find("properties")
            if props is None:
                skipped += 1
                continue

            hull_elem = props.find("hull")
            if hull_elem is None:
                skipped += 1
                continue

            max_hull_str = hull_elem.get("max")
            if max_hull_str is None:
                skipped += 1
                continue

            entry = {"max_hull": int(max_hull_str)}

            # Production wares — what this module manufactures (production modules only)
            prod_elem = props.find("production")
            if prod_elem is not None:
                wares = prod_elem.get("wares")
                if wares:
                    entry["produces"] = wares

            stats[macro_elem.get("name", "")] = entry
            hull_count += 1

        except ET.ParseError as e:
            print(f"[Warning] Could not parse {xml_file.name}: {e}")
            skipped += 1

    print(f"[Modules] Extracted hull data for {hull_count} modules ({skipped} files skipped)")

# ── Pass 2: Shield equipment recharge capacity ────────────────────────────────
# Stations reference installed shields by macro name in their construction
# sequence <upgrades> blocks. We sum recharge max values across all installed
# shields to get the station's total shield capacity.
# Current HP is not stored in saves — shields always regenerate — so capacity
# is the only meaningful value we can report.

if not SHIELD_DIR.exists():
    print(f"[Warning] '{SHIELD_DIR.name}/' not found — skipping shield extraction.")
    print("  Extract shield XMLs with XRCatTool -include 'SurfaceElements.*macros.*shield_.*[.]xml'")
else:
    shield_files = list(SHIELD_DIR.rglob("shield_*_macro.xml"))
    print(f"[Shields] Found {len(shield_files)} shield XML files in '{SHIELD_DIR.name}/'")
    shield_count = 0
    skipped      = 0

    for xml_file in shield_files:
        try:
            root       = ET.parse(xml_file).getroot()
            macro_elem = root.find("macro")
            if macro_elem is None or macro_elem.get("class") != "shieldgenerator":
                skipped += 1
                continue

            props = macro_elem.find("properties")
            if props is None:
                skipped += 1
                continue

            recharge_elem = props.find("recharge")
            if recharge_elem is None:
                skipped += 1
                continue

            max_shield_str = recharge_elem.get("max")
            if max_shield_str is None:
                skipped += 1
                continue

            stats[macro_elem.get("name", "")] = {"max_shield": int(max_shield_str)}
            shield_count += 1

        except ET.ParseError as e:
            print(f"[Warning] Could not parse {xml_file.name}: {e}")
            skipped += 1

    print(f"[Shields] Extracted capacity for {shield_count} shield types ({skipped} files skipped)")

# ── Write data/station_stats.py ───────────────────────────────────────────────

sorted_stats = dict(sorted(stats.items()))

lines = [
    "# ─────────────────────────────────────────────────────────────────────────────",
    "#  STATION & SHIELD STATS",
    "#  Maps macro names to their static game specs.",
    "#",
    "#  AUTO-GENERATED by generate_station_stats.py — do not edit by hand.",
    "#  Re-run after extracting new XMLs from X4's .cat files.",
    "#",
    "#  CURRENT KEYS PER ENTRY:",
    "#    max_hull    — base maximum hull HP (station structure modules)",
    "#    max_shield  — shield recharge capacity in HP (shield equipment macros)",
    "#    produces    — ware produced by this module (production modules only)",
    "# ─────────────────────────────────────────────────────────────────────────────",
    "",
    "STATION_STATS = {",
]

for macro_name, entry in sorted_stats.items():
    lines.append(f"    {macro_name!r}: {{")
    if "max_hull" in entry:
        lines.append(f"        'max_hull': {entry['max_hull']},")
    if "max_shield" in entry:
        lines.append(f"        'max_shield': {entry['max_shield']},")
    if "produces" in entry:
        lines.append(f"        'produces': {entry['produces']!r},")
    lines.append(f"    }},")

lines.append("}")
lines.append("")

OUT_FILE.write_text("\n".join(lines), encoding="utf-8")
print(f"[Done] Written to {OUT_FILE} ({len(sorted_stats)} total entries)")
