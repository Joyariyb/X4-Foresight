r"""
XTOOLS EXTRACTION COMMANDS — DO NOT DELETE

Base game:
for /L %i in (1,1,9) do XRCatTool -in "C:\Program Files (x86)\Steam\steamapps\common\X4 Foundations\0%i.cat" -out "C:\Users\lenovo\Documents\GitHub\X4 Foresight\XML Library" -include "libraries/mapdefaults\.xml"

DLC (create each folder under XML Library\DLC\ manually first, then run each line):
for /L %i in (1,1,3) do XRCatTool -in "C:\Program Files (x86)\Steam\steamapps\common\X4 Foundations\extensions\ego_dlc_boron\ext_0%i.cat" -out "C:\Users\lenovo\Documents\GitHub\X4 Foresight\XML Library\DLC\ego_dlc_boron" -include "libraries/mapdefaults\.xml"
for /L %i in (1,1,3) do XRCatTool -in "C:\Program Files (x86)\Steam\steamapps\common\X4 Foundations\extensions\ego_dlc_split\ext_0%i.cat" -out "C:\Users\lenovo\Documents\GitHub\X4 Foresight\XML Library\DLC\ego_dlc_split" -include "libraries/mapdefaults\.xml"
for /L %i in (1,1,3) do XRCatTool -in "C:\Program Files (x86)\Steam\steamapps\common\X4 Foundations\extensions\ego_dlc_terran\ext_0%i.cat" -out "C:\Users\lenovo\Documents\GitHub\X4 Foresight\XML Library\DLC\ego_dlc_terran" -include "libraries/mapdefaults\.xml"
for /L %i in (1,1,3) do XRCatTool -in "C:\Program Files (x86)\Steam\steamapps\common\X4 Foundations\extensions\ego_dlc_pirate\ext_0%i.cat" -out "C:\Users\lenovo\Documents\GitHub\X4 Foresight\XML Library\DLC\ego_dlc_pirate" -include "libraries/mapdefaults\.xml"
for /L %i in (1,1,3) do XRCatTool -in "C:\Program Files (x86)\Steam\steamapps\common\X4 Foundations\extensions\ego_dlc_timelines\ext_0%i.cat" -out "C:\Users\lenovo\Documents\GitHub\X4 Foresight\XML Library\DLC\ego_dlc_timelines" -include "libraries/mapdefaults\.xml"

generate_sector_stats.py
========================
Reads mapdefaults.xml from XML Library/ (base game) and XML Library/DLC/
(DLC sectors) and writes data/sector_stats.py.

SECTOR_SUNLIGHT maps each player-visible sector name to its sunlight multiplier.
Sunlight affects solar power plant (energy cell factory) output only -- it is the
<effect type="sunlight"> modifier in wares.xml. All other production modules
are unaffected.

    effective_output = base_amount * sunlight_factor

REQUIRED INPUTS:
    XML Library/libraries/mapdefaults.xml      -- base game (extracted above)
    XML Library/DLC/libraries/mapdefaults.xml  -- DLC sectors (extracted above)
    0001-l044.xml                              -- English language file

Re-run after a game update or DLC install.
"""

import pathlib
import re
import xml.etree.ElementTree as ET

ROOT          = pathlib.Path(__file__).parent.parent
XML_LIBRARY   = ROOT / "XML Library"
LANGUAGE_FILE = ROOT / "0001-l044.xml"
OUT_FILE      = ROOT / "data" / "sector_stats.py"

_LANG_REF_RE    = re.compile(r'^\{20004,(\d+)\}$')
_SECTOR_NAME_RE = re.compile(r'\(([^)]+)\)\s*$')


def load_sector_names(lang_path: pathlib.Path) -> dict:
    """Returns {lang_id: sector_name} from page 20004 of the language XML."""
    lookup = {}
    tree   = ET.parse(lang_path)
    root   = tree.getroot()
    for page in root.findall("page"):
        if page.get("id") == "20004":
            for t in page.findall("t"):
                tid  = t.get("id", "")
                text = (t.text or "").strip()
                m    = _SECTOR_NAME_RE.search(text)
                if m:
                    lookup[tid] = m.group(1)
            break
    return lookup


def _dataset_elements(root: ET.Element):
    """Yields <dataset> elements from either a full file or an XML diff file."""
    if root.tag == "diff":
        # DLC files patch the base with <diff><add sel="..."><dataset .../></add></diff>
        for add in root.findall("add"):
            yield from add.findall("dataset")
    else:
        yield from root.findall("dataset")


def parse_mapdefaults(xml_path: pathlib.Path, sector_names: dict, result: dict) -> int:
    """Parses one mapdefaults.xml and adds sector sunlight entries to result. Returns count added."""
    tree     = ET.parse(xml_path)
    root     = tree.getroot()
    datasets = list(_dataset_elements(root))

    # Pass 1: collect sunlight keyed by macro for every dataset that has it.
    # Base game stores sunlight on sector datasets; Boron DLC stores it on the
    # parent cluster dataset instead, so we need both levels in one lookup.
    sunlight_by_macro: dict[str, float] = {}
    for dataset in datasets:
        macro = dataset.get("macro", "")
        props = dataset.find("properties")
        if props is None:
            continue
        area = props.find("area")
        if area is not None and area.get("sunlight") is not None:
            sunlight_by_macro[macro] = float(area.get("sunlight"))

    # Pass 2: for each sector dataset, resolve its name and sunlight.
    added = 0
    for dataset in datasets:
        macro = dataset.get("macro", "")
        if "_Sector" not in macro and "_sector" not in macro:
            continue

        props = dataset.find("properties")
        if props is None:
            continue

        ident = props.find("identification")
        if ident is None:
            continue

        m = _LANG_REF_RE.match(ident.get("name", ""))
        if not m:
            continue

        sector_name = sector_names.get(m.group(1))
        if not sector_name:
            continue

        # Cluster-level <area sunlight> values (present in some DLC files) are a
        # different property and must NOT be used as a sector sunlight proxy.
        sunlight = sunlight_by_macro.get(macro)

        if sunlight is not None:
            # Real value: always write (base game may override a DLC entry).
            result[sector_name] = sunlight
        elif sector_name not in result:
            # DLC sector with no explicit sunlight (e.g. Boron) → standard output.
            # Only fills gaps so duplicate demo macros don't overwrite real values.
            result[sector_name] = 1.0
        else:
            continue

        added += 1

    return added


def write_output(sunlight: dict, out_path: pathlib.Path) -> None:
    lines = [
        "# ─────────────────────────────────────────────────────────────────────────────",
        "#  SECTOR STATS",
        "#  Generated by Generators/generate_sector_stats.py.",
        "#  Sources: libraries/mapdefaults.xml (base + DLC) + 0001-l044.xml.",
        "#  Re-run after a game update or DLC install.",
        "#",
        "#  SECTOR_SUNLIGHT maps sector name → sunlight multiplier.",
        "#  Only relevant for energy cell production (solar power plants):",
        "#    effective_output = base_amount * sunlight",
        "#  1.0 = standard output; values above 1.0 mean more cells per cycle.",
        "# ─────────────────────────────────────────────────────────────────────────────",
        "",
        "SECTOR_SUNLIGHT: dict[str, float] = {",
    ]

    for name, sl in sorted(sunlight.items()):
        lines.append(f"    {name!r}: {sl},")

    lines.append("}")
    lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[Output] Written to: {out_path}")
    print(f"[Stats]  {len(sunlight)} sectors total")


if __name__ == "__main__":
    if not LANGUAGE_FILE.exists():
        print(f"[Error] Language file not found: {LANGUAGE_FILE}")
        raise SystemExit(1)

    print(f"[Input]  Loading sector names from {LANGUAGE_FILE.name}...")
    sector_names = load_sector_names(LANGUAGE_FILE)
    print(f"[Input]  Loaded {len(sector_names)} sector names.")

    # Glob for every mapdefaults.xml under XML Library/ — covers base game and
    # any DLC subfolders created by the extraction commands above.
    all_files = sorted(XML_LIBRARY.rglob("mapdefaults.xml"))
    if not all_files:
        print(f"[Error] No mapdefaults.xml found under: {XML_LIBRARY}")
        raise SystemExit(1)

    sunlight = {}
    for xml_path in all_files:
        label = xml_path.relative_to(XML_LIBRARY)
        n     = parse_mapdefaults(xml_path, sector_names, sunlight)
        print(f"[Input]  {label}  ({n} sectors)")

    write_output(sunlight, OUT_FILE)
