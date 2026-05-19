# ════════════════════════════════════════════════════════════════════════════
#                          LANGUAGE FILE: SECTOR NAME RESOLUTION
# ════════════════════════════════════════════════════════════════════════════
"""
Module for resolving human-readable sector names from X4 language files.

This module provides utilities to extract and map sector names defined in the
game's language XML files (specifically page ID 20004). It handles both standard
XML and compressed (.gz) formats, offering a fast C-based parsing interface via lxml.

Core Capabilities:
- Load sector name mappings from English language files
- Convert sector macro names (e.g., 'cluster_43_sector001_macro') to readable names
- Resolve player location references ({20004,XXXXX}) to actual sector names

Usage Example:
    from pathlib import Path
    from scanner.language import load_sector_names, macro_to_sector_name
    
    lang_path = Path("extracts/0001-l044.xml")
    sector_names = load_sector_names(lang_path)
    
    readable_name = macro_to_sector_name("cluster_43_sector001_macro", sector_names)
    print(freadable_name)  # Outputs: "The Void" or None if not found
"""

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
    """Opens an X4 save file for reading, handling both .xml and .xml.gz formats.

    Uses binary mode with lxml's C parser for maximum performance—lxml detects
    the file's encoding automatically from the XML declaration, making text
    decoding unnecessary.

    Args:
        path: Path to the .xml or .xml.gz file to open.

    Yields:
        File handle opened in binary mode.
    """
    if path.suffix == '.gz':
        with gzip.open(path, 'rb') as f:
            yield f
    else:
        with open(path, 'rb') as f:
            yield f


def load_sector_names(lang_path: pathlib.Path) -> dict:
    """Loads and parses sector names from the X4 English language file.

    Sector names are located in page ID 20004 of the language XML. Each entry
    follows the pattern: {ClusterID,BaseID}(Name), where the name is extracted
    from parentheses at the end.

    Args:
        lang_path: Path to the language XML file (e.g., 'extracts/0001-l044.xml').

    Returns:
        Dictionary mapping sector IDs to readable names:
            {"270011": "The Void", "140011": "Argon Prime", ...}

    Notes:
        - If the file is not found, a warning is printed and an empty dict is returned.
          Sector names will then display as macro IDs in reports.
        - To extract the language file, use X Tools (Steam) to unpack .cat archives
          and pull '0001-l044.xml' from the appropriate cluster.

    Example:
        >>> load_sector_names(Path("extracts/0001-l044.xml"))
        {"270011": "The Void", "140011": "Argon Prime"}
    """
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
    """Converts a sector macro name to its human-readable counterpart.

    Macro names follow the pattern 'cluster_XY_sectorZZ_macro' and are decoded
    using a specific formula applied against entries in the language file:
        language_id = str(cluster_number * 10) + sector_suffix

    The suffix increments by 10 for each subsequent sector:
        sector001 -> "011"
        sector002 -> "021"
        sector003 -> "031"

    Examples:
        cluster_43_sector001_macro → 430 + 011 = "430011" → "Hewa's Twin V"
        cluster_14_sector001_macro → 140 + 011 = "140011" → "Argon Prime"
        cluster_27_sector001_macro → 270 + 011 = "270011" → "The Void"
        cluster_1_sector001_macro  →   10 + 011 = "10011" → "Grand Exchange I"

    Args:
        macro: The macro name string (e.g., 'cluster_43_sector001_macro').
        sector_names: Dictionary loaded from the language file.

    Returns:
        The readable sector name if found, or None if the macro doesn't match
        the expected pattern or isn't in the language file.
    """
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
    """Resolves a sector reference from the player's current location string.

    Used specifically for displaying the player's current position at the top of
    the intelligence report. Handles references in the format {20004,XXXXX}.

    Note: Station sectors (e.g., from macro names) should be resolved via
    macro_to_sector_name() instead.

    Args:
        location_str: The player location attribute value (e.g., '270011').
        sector_names: Dictionary loaded from the language file.

    Returns:
        Readable sector name if found, otherwise returns "Unknown" or the raw
        ID string.
    """
    if not location_str:
        return "Unknown"
    m = _LOCATION_REF_RE.search(location_str)
    if m:
        return sector_names.get(m.group(1), f"Sector {m.group(1)}")
    return location_str
