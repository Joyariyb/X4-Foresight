# ════════════════════════════════════════════════════════════════════════════
#                          LANGUAGE FILE: SECTOR NAME RESOLUTION
# ════════════════════════════════════════════════════════════════════════════

import contextlib
import gzip
import pathlib
import re

from lxml import etree as ET
from data.station_names import WARE_FACTORY_NAMES
from data.wares import WARE_GROUPS, WARE_GROUP_PRIORITY

# Pre-compiled so these don't recompile on every call inside the iterparse loops.
_SECTOR_NAME_RE = re.compile(r'\(([^)]+)\)\s*$')
_SECTOR_MACRO_RE = re.compile(r'cluster_(\d+)_sector(\d+)_macro', re.IGNORECASE)
_LOCATION_REF_RE = re.compile(r'\{20004,(\d+)\}')
_TEXT_REF_RE     = re.compile(r'^\{(\d+),(\d+)\}$')


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


def load_text_pages(lang_path: pathlib.Path, page_ids: set) -> dict:
    """
    Loads the requested pages from the language file.
    Returns {"page:id": text} for every entry found on those pages.

    Used by scanners that need to resolve {page,id} text references that
    appear as attribute values in the save file (e.g. station type names
    on page 20102).
    """
    texts = {}
    if not lang_path.exists():
        return texts
    try:
        tree      = ET.parse(lang_path)
        root      = tree.getroot()
        remaining = {str(p) for p in page_ids}
        for page in root.findall('page'):
            pid = page.get('id', '')
            if pid not in remaining:
                continue
            for t in page.findall('t'):
                tid  = t.get('id', '')
                text = (t.text or '').strip()
                if text:
                    texts[f"{pid}:{tid}"] = text
            remaining.discard(pid)
            if not remaining:
                break
    except Exception as e:
        print(f"[Warning] Failed to load language texts: {e}")
    return texts



# Matches the production module macro naming pattern prod_{faction}_{ware}_macro.
# The non-greedy faction token handles multi-part factions (e.g. prod_gen_hullparts_macro).
_PROD_MACRO_RE = re.compile(r'^prod_(?:\w+?)_(\w+)_macro$', re.IGNORECASE)


def resolve_station_type(prod_macros: list[str], texts: dict) -> str:
    """
    Returns the factory type name for a station given its production module macros.

    Applies X4's single/multi-product naming rule:

      • 1 unique ware type produced → individual factory name from page 20201
        (e.g. microchips-only → "Microchip Factory", energycells-only → "Solar
        Power Plant").  These come from WARE_FACTORY_NAMES in data/station_names.py,
        which was generated directly from wares.xml factoryname attributes.

      • 2+ unique ware types → category factory name from page 20215, chosen by
        the highest-priority ware group (lowest WARE_GROUP_PRIORITY rank).
        (e.g. wheat + meat → "Agricultural Goods Factory").

    Multiple modules producing the SAME ware (e.g. three microchip lines) still
    count as a single unique ware type — only the set of distinct ware IDs matters.

    Returns an empty string if none of the macros map to a known ware.
    """
    # Collect distinct ware IDs found in the production module list.
    # Duplicates (same ware, multiple modules) are collapsed by the set.
    unique_wares: set[str] = set()
    for macro in prod_macros:
        m = _PROD_MACRO_RE.match(macro)
        if not m:
            continue
        unique_wares.add(m.group(1).lower())

    if not unique_wares:
        return ''

    # ── Single unique ware → individual factory name ───────────────────────────
    if len(unique_wares) == 1:
        ware_id = next(iter(unique_wares))
        entry   = WARE_FACTORY_NAMES.get(ware_id)
        if entry:
            return entry.name
        # Unknown ware (DLC content, modded ware) — fall through to group logic.

    # ── Multiple unique wares → highest-priority group factory name ────────────
    best_priority = None
    winning_gid   = None
    for ware_id in unique_wares:
        gid  = WARE_GROUPS.get(ware_id)
        if gid is None:
            continue
        prio = WARE_GROUP_PRIORITY.get(gid, 999)
        if best_priority is None or prio < best_priority:
            best_priority = prio
            winning_gid   = gid
    if winning_gid is not None:
        return texts.get(f"20215:{winning_gid + 3}", '')
    return ''


_ROMAN = [
    "", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X",
    "XI", "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX",
    "XXI", "XXII", "XXIII", "XXIV", "XXV", "XXVI", "XXVII", "XXVIII", "XXIX", "XXX",
]


def nameindex_to_roman(nameindex_str: str) -> str:
    """Converts a nameindex attribute string (e.g. "2") to a Roman numeral (e.g. "II")."""
    try:
        n = int(nameindex_str)
        if 0 < n < len(_ROMAN):
            return _ROMAN[n]
        return str(n) if n > 0 else ''
    except (ValueError, TypeError):
        return ''


def resolve_text_ref(raw: str, texts: dict) -> str:
    """
    Resolves a bare {page,id} language reference to its text string.
    Returns the raw value unchanged if it is not a reference or not found.
    """
    m = _TEXT_REF_RE.match(raw)
    if m:
        return texts.get(f"{m.group(1)}:{m.group(2)}", raw)
    return raw


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
