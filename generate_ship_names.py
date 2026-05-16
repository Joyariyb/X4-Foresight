"""
GENERATE SHIP NAMES - One-time utility script
==============================================
Reads all extracted ship macro XML files and the X4 language file to produce
a static SHIP_NAMES lookup dict, written to data/ships.py.

Run this once (or again after extracting DLC cat files) from the project root:
    python generate_ship_names.py

REQUIRED INPUTS:
    extracted/          - Folder of ship macro XMLs extracted from 01.cat and
                          07.cat (and optionally DLC cats) using XRCatTool.exe.
                          Expected structure mirrors the cat file layout:
                          extracted/assets/units/size_*/macros/ship_*_macro.xml

    0001-l044.xml       - X4 English language file, already in the project root.

OUTPUT:
    data/ships.py       - Static dict mapping macro name to display name.
                          e.g. "ship_tel_s_trans_container_01_b_macro": "Magpie Sentinel"

HOW IT WORKS:
    Two identification structures exist in the macro XML files:

    Structure A (newer ships with basename + variation):
        <identification basename="{20101,22601}" variation="{20111,3201} {20111,1101}" />
    We resolve the basename from page 20101 and each variation token from
    page 20111, then join them: "Magnetar" + "(Gas)" + "Vanguard" = "Magnetar (Gas) Vanguard"

    Structure B (older ships and Xenon/E-variants with name only):
        <identification name="{20101,11004}" />
    We resolve the name directly from page 20101: "Behemoth E"

    We try structure A first, and fall back to structure B if basename is absent.

WHY STATIC OUTPUT:
    Parsing hundreds of macro XMLs at runtime on every scan would be slow
    and requires the extracted folder to be present. A static dict in
    data/ships.py is fast, portable, and matches the pattern already used
    by data/wares.py and data/factions.py.
"""

import pathlib
import re
import xml.etree.ElementTree as ET

SCRIPT_DIR    = pathlib.Path(__file__).parent
EXTRACTED_DIR = SCRIPT_DIR / "extracted"
LANG_FILE     = SCRIPT_DIR / "0001-l044.xml"
OUTPUT_FILE   = SCRIPT_DIR / "data" / "ships.py"


def clean_text(text: str) -> str:
    """Strips backslash escapes from language file text."""
    return text.replace('\\(', '(').replace('\\)', ')')


def load_language_tables(lang_path: pathlib.Path) -> tuple[dict, dict]:
    """
    Parses the language file and returns two dicts:
        ship_names  { "22601": "Magnetar", "11004": "Behemoth E", ... }
        variations  { "1101": "Vanguard", "3201": "(Gas)", ... }

    Page 20101 covers ship names in three forms:
      - Plain text base names:    <t id="22601">Magnetar</t>
      - Plain text full names:    <t id="11004">Behemoth E</t>
      - Annotated pre-composed:   <t id="22603">(Magpie Sentinel){20101,...}</t>

    Page 20111 covers variant suffix tokens like Vanguard, Sentinel, (Gas) etc.
    """
    ship_names = {}
    variations = {}

    print(f"[Language] Loading language tables from {lang_path.name}...")

    tree = ET.parse(str(lang_path))
    root = tree.getroot()

    for page in root.findall('page'):
        pid = page.get('id')

        if pid == '20101':
            for t in page.findall('t'):
                tid  = t.get('id', '')
                # Work on raw text BEFORE clean_text so backslash-escaped
                # inner parens like \( and \) are still intact when we regex.
                raw  = (t.text or '').strip()

                # Skip pure cross-references - no display text
                if not raw or raw.startswith('{'):
                    continue

                if raw.startswith('('):
                    # Pre-composed annotated entry e.g. "(Chthonios E \(Gas\)){...}"
                    # Match the outer parens, allowing \( and \) inside.
                    # Pattern: opening (, then any chars including \( \), then closing )
                    m = re.match(r'^\(((\\.|[^)])+)\)', raw)
                    if m:
                        # Now clean the extracted name to strip backslash escapes
                        ship_names[tid] = clean_text(m.group(1))
                else:
                    # Plain text - base name like "Magnetar" or full name like "Behemoth E"
                    # Strip any trailing pronunciation note e.g. 'PE(pronounce...)'
                    plain = re.sub(r'\([^)]+\)$', '', raw).strip()
                    ship_names[tid] = clean_text(plain) if plain else clean_text(raw)

        elif pid == '20111':
            for t in page.findall('t'):
                tid  = t.get('id', '')
                text = clean_text((t.text or '').strip())
                if not text or text.startswith('{'):
                    continue
                # Strip parenthesised annotations e.g. "(extra-small)XS" -> "XS"
                m = re.match(r'^\([^)]+\)(.+)$', text)
                if m:
                    text = m.group(1).strip()
                variations[tid] = text

    print(f"[Language] Loaded {len(ship_names)} ship name entries, "
          f"{len(variations)} variation tokens.")
    return ship_names, variations


BASE_REF_RE = re.compile(r'\{\s*20101\s*,\s*(\d+)\s*\}')
VAR_REF_RE  = re.compile(r'\{\s*20111\s*,\s*(\d+)\s*\}')


def build_macro_to_name(
    extracted_dir: pathlib.Path,
    ship_names:    dict,
    variations:    dict,
) -> dict:
    """
    Walks all ship_*_macro.xml files under extracted_dir and returns a
    dict mapping macro name to display name.

    Tries structure A (basename + variation) first, falls back to
    structure B (name only) for Xenon ships, E-variants, and older ships.
    """
    mapping  = {}
    missing  = []
    no_ident = []

    macro_files = sorted(extracted_dir.rglob("ship_*_macro.xml"))
    print(f"[Macros] Found {len(macro_files)} ship macro files to process...")

    for path in macro_files:
        try:
            tree = ET.parse(str(path))
            root = tree.getroot()

            macro_elem = root.find('macro')
            if macro_elem is None:
                no_ident.append(path.name)
                continue

            macro_name = macro_elem.get('name', '')

            ident = macro_elem.find('.//identification')
            if ident is None:
                no_ident.append(macro_name or path.name)
                continue

            # ── Structure A: basename + variation ──────────────────────────
            # Used by most standard ships. Builds name from parts so that
            # miners correctly include both resource type and Vanguard/Sentinel.
            basename_attr = ident.get('basename', '')
            base_m = BASE_REF_RE.search(basename_attr)

            if base_m:
                base_id   = base_m.group(1)
                base_name = ship_names.get(base_id)
                if not base_name:
                    missing.append((macro_name, f"base id {base_id} not in page 20101"))
                    continue

                variation_attr = ident.get('variation', '')
                suffix_parts   = []
                for var_m in VAR_REF_RE.finditer(variation_attr):
                    var_str = variations.get(var_m.group(1), '')
                    if var_str:
                        suffix_parts.append(var_str)

                full_name = base_name
                if suffix_parts:
                    full_name = base_name + ' ' + ' '.join(suffix_parts)
                mapping[macro_name] = full_name
                continue

            # ── Structure B: name only (fallback) ──────────────────────────
            # Used by Xenon ships, E-variants, and other ships where the full
            # display name is pre-composed directly in the language file.
            name_attr = ident.get('name', '')
            name_m = BASE_REF_RE.search(name_attr)

            if name_m:
                name_id      = name_m.group(1)
                display_name = ship_names.get(name_id)
                if display_name:
                    mapping[macro_name] = display_name
                else:
                    missing.append((macro_name, f"name id {name_id} not in page 20101"))
            else:
                no_ident.append(macro_name)

        except ET.ParseError as e:
            print(f"  [Warning] XML parse error in {path.name}: {e}")

    if no_ident:
        print(f"[Macros] {len(no_ident)} files skipped "
              f"(no identification - drones, spacesuits, NPC vessels etc.)")

    if missing:
        print(f"[Macros] {len(missing)} macros could not be resolved:")
        for macro, reason in missing:
            print(f"  {macro} -> {reason}")

    print(f"[Macros] Resolved {len(mapping)} ship names successfully.")
    return mapping


HEADER = """\
# ─────────────────────────────────────────────────────────────────────────────
#  SHIP DISPLAY NAMES
#  Maps ship macro names (as found in the X4 save file) to their in-game
#  display names, e.g. "ship_tel_s_trans_container_01_b_macro": "Magpie Sentinel"
#
#  AUTO-GENERATED by generate_ship_names.py - do not edit by hand.
#  Re-run generate_ship_names.py after extracting DLC cat files to add
#  new ships from expansions.
#
#  HOW THIS IS USED:
#  scanner/ships.py looks up each ship's macro here to get the display name.
#  If a macro is not listed, ships.py falls back to the hull origin + role.
# ─────────────────────────────────────────────────────────────────────────────

SHIP_NAMES = {
"""

FOOTER = "}\n"


def write_ships_py(mapping: dict, output_path: pathlib.Path):
    """Writes the macro to display name mapping to data/ships.py."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(HEADER)
        for macro, name in sorted(mapping.items()):
            safe_name = name.replace("'", "\\'")
            f.write(f"    '{macro}': '{safe_name}',\n")
        f.write(FOOTER)

    print(f"[Output] Written {len(mapping)} entries to {output_path}")


if __name__ == "__main__":
    if not EXTRACTED_DIR.exists():
        print(f"[Error] Extracted folder not found: {EXTRACTED_DIR}")
        print("  Run XRCatTool.exe to extract ship macro XMLs first.")
        exit(1)

    if not LANG_FILE.exists():
        print(f"[Error] Language file not found: {LANG_FILE}")
        print("  Place 0001-l044.xml in the project root.")
        exit(1)

    lang_names, variations = load_language_tables(LANG_FILE)
    mapping                = build_macro_to_name(EXTRACTED_DIR, lang_names, variations)
    write_ships_py(mapping, OUTPUT_FILE)

    print("\n[Done] Run this script again after extracting DLC cat files")
    print("       to add Terran, Split, Boron, and pirate ship names.")