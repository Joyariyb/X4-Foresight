# ═════════════════════════════════════════════════════════════════════════════
#  SECTION 1 — LANGUAGE FILE: SECTOR NAME RESOLUTION
# ═════════════════════════════════════════════════════════════════════════════
import pathlib
import re
import xml.etree.ElementTree as ET

def load_sector_names(lang_path: pathlib.Path) -> dict:
    """
    Parses the X4 English language file and returns a lookup dictionary:
        { "270011": "The Void", "140011": "Argon Prime", ... }

    Sector names live in <page id="20004">. Each entry looks like:
        <t id="270011">{20003,270001}(The Void)</t>
    We extract the name from the parentheses at the end and key it by ID.
    """
    lookup = {}

    if not lang_path.exists():
        print(f"\n[Warning] Language file not found: {lang_path.name}")
        print("  Sector names will show as macro IDs.")
        print("  Extract 0001-l044.xml from X4's .cat files using X Tools (Steam).\n")
        return lookup

    try:
        print(f"[Language] Loading sector names from {lang_path.name}...")
        tree = ET.parse(str(lang_path))
        root = tree.getroot()

        for page in root.findall('page'):
            if page.get('id') == '20004':
                for t in page.findall('t'):
                    tid  = t.get('id', '')
                    text = (t.text or '').strip()
                    # Extract the name in parentheses at the end of the string
                    # e.g. "{20003,270001}(The Void)" -> "The Void"
                    m = re.search(r'\(([^)]+)\)\s*$', text)
                    if m:
                        lookup[tid] = m.group(1)
                break  # Page 20004 found — no need to continue scanning

        print(f"[Language] Loaded {len(lookup)} sector names successfully.")

    except Exception as e:
        print(f"[Warning] Failed to parse language file: {e}")

    return lookup


def macro_to_sector_name(macro: str, sector_names: dict) -> str:
    """
    Converts a sector macro name like 'cluster_43_sector001_macro' into
    a human-readable sector name like 'Hewa's Twin V'.

    HOW THE FORMULA WORKS:
    The language file uses numeric IDs for sectors. The pattern is:
        language_id = str(cluster_number * 10) + sector_suffix
    Where sector_suffix is:
        sector001 -> "011"
        sector002 -> "021"
        sector003 -> "031"  (each step adds 10 to the middle digit)

    Examples:
        cluster_43_sector001_macro -> 43*10=430, suffix=011 -> "430011" -> "Hewa's Twin V"
        cluster_14_sector001_macro -> 14*10=140, suffix=011 -> "140011" -> "Argon Prime"
        cluster_27_sector001_macro -> 27*10=270, suffix=011 -> "270011" -> "The Void"
        cluster_1_sector001_macro  ->  1*10=10,  suffix=011 ->  "10011" -> "Grand Exchange I"

    Returns None if the macro doesn't match the expected pattern.
    """
    m = re.match(r'cluster_(\d+)_sector(\d+)_macro', macro, re.IGNORECASE)
    if not m:
        return None

    cluster_num = int(m.group(1))
    sector_num  = int(m.group(2))  # 1 for sector001, 2 for sector002, etc.

    # Build the language file ID from the cluster and sector numbers
    prefix     = str(cluster_num * 10)
    suffix     = str(sector_num * 10 + 1).zfill(3)  # 1->"011", 2->"021", 3->"031"
    lang_id    = prefix + suffix

    return sector_names.get(lang_id)

def resolve_sector_from_location(location_str: str, sector_names: dict) -> str:
    """
    Resolves a sector reference in the {20004,XXXXX} format used in the
    save's <info><player location="..."/> attribute.

    This is only used for the player's current position displayed at the top
    of the report. Station sectors are resolved via macro_to_sector_name().
    """
    if not location_str:
        return "Unknown"
    m = re.search(r'\{20004,(\d+)\}', location_str)
    if m:
        return sector_names.get(m.group(1), f"Sector {m.group(1)}")
    return location_str