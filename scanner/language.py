# ════════════════════════════════════════════════════════════════════════════
#                          LANGUAGE FILE: SECTOR NAME RESOLUTION
# ════════════════════════════════════════════════════════════════════════════

import contextlib
import gzip
import pathlib
import re

from lxml import etree as ET

# Pre-compiled so these don't recompile on every call inside the iterparse loops.
_SECTOR_NAME_RE = re.compile(r'\(([^)]+)\)\s*$')
_SECTOR_MACRO_RE = re.compile(r'cluster_(\d+)_sector(\d+)_macro', re.IGNORECASE)
_LOCATION_REF_RE = re.compile(r'\{20004,(\d+)\}')


@contextlib.contextmanager
def open_save(path: pathlib.Path):
    """Opens a .xml or .xml.gz save file in binary mode for lxml iterparse."""
    if path.suffix == '.gz':
        with gzip.open(path, 'rb') as f:
            yield f
    else:
        with open(path, 'rb') as f:
            yield f


def load_sector_names(lang_path: pathlib.Path) -> dict:
    """Parses page ID 20004 from the language XML, returning {sector_id: name} dict."""
    lookup = {}

    if not lang_path.exists():
        print(f"\n[Warning] Language file not found: {lang_path.name}")
        print("  Sector names will show as macro IDs.")
        print("  Extract 0001-l044.xml from X4's .cat files using X Tools (Steam).\n")
        return lookup

    try:
        print(f"[Language] Loading sector names from {lang_path.name}...")
        tree = ET.parse(lang_path)
        root = tree.getroot()

        for page in root.findall('page'):
            if page.get('id') == '20004':
                for t in page.findall('t'):
                    tid = t.get('id', '')
                    text = (t.text or '').strip()
                    # Extract the name from parentheses at the end of the string
                    # e.g. "{20003,270001}(The Void)" -> "The Void"
                    m = _SECTOR_NAME_RE.search(text)
                    if m:
                        lookup[tid] = m.group(1)
                break  # Page 20004 found — no need to continue scanning

        print(f"[Language] Loaded {len(lookup)} sector names successfully.")

    except Exception as e:
        print(f"[Warning] Failed to parse language file: {e}")

    return lookup


def macro_to_sector_name(macro: str, sector_names: dict) -> str:
    """Converts 'cluster_XY_sectorZZ_macro' to a readable name via the language file."""
    m = _SECTOR_MACRO_RE.match(macro)
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
    """Resolves a {20004,XXXXX} player location string to a readable sector name."""
    if not location_str:
        return "Unknown"
    m = _LOCATION_REF_RE.search(location_str)
    if m:
        return sector_names.get(m.group(1), f"Sector {m.group(1)}")
    return location_str
