#!/usr/bin/env python3
"""
list_sectors.py
---------------
Standalone script — does not import any X4 Foresight project modules.

Scans save_001.xml (or save_001.xml.gz) from the project root, lists every
unique sector found in the save file, and lists all stations in The Void.

Usage:
    python Generators/list_sectors.py

Requirements:
    - save_001.xml (or save_001.xml.gz) in the project root
    - 0001-l044.xml in the project root for human-readable names (optional;
      without it, raw macro strings are shown instead)
"""

import gzip
import pathlib
import re
import time

from lxml import etree as ET

# ─── Paths ────────────────────────────────────────────────────────────────────
# This script lives in Generators/, so the project root is one level up.
PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
SAVE_PATH    = PROJECT_ROOT / "save_001.xml"
LANG_PATH    = PROJECT_ROOT / "0001-l044.xml"

# Transparently try the compressed version if the plain XML isn't present.
if not SAVE_PATH.exists():
    SAVE_PATH = PROJECT_ROOT / "save_001.xml.gz"

# Wares file — used to resolve exact in-game factory names (e.g. "Solar Power Plant").
# The fallback chain is tried in order; the first path that exists is used.
# To switch to the game's own extracted files, add that path as a second entry.
_WARES_CANDIDATES = [
    PROJECT_ROOT / "XML Library" / "libraries" / "wares.xml",
    # Example: pathlib.Path(r"C:\SteamLibrary\steamapps\common\X4 Foundations\extracted\libraries\wares.xml"),
]
WARES_PATH = next((p for p in _WARES_CANDIDATES if p.exists()), _WARES_CANDIDATES[0])

# ─── Constants ────────────────────────────────────────────────────────────────
# All component class values that represent a station-level object.
STATION_CLASSES = {"station", "factory", "headquarters", "complex"}

# Faction abbreviations inlined from data/factions.py.
# Used to prefix NPC station names in X4's UI style, e.g. "ARG Trade Station I".
FACTION_ABBR = {
    "argon":            "ARG",
    "antigone":         "ANT",
    "hatikvah":         "HAT",
    "paranid":          "PAR",
    "trinity":          "TRI",
    "split":            "ZYA",
    "fallensplit":      "FAF",
    "freesplit":        "FRF",
    "teladi":           "TEL",
    "ministry":         "MIN",
    "xenon":            "XEN",
    "khaak":            "KHK",
    "buccaneers":       "BUC",
    "scaleplate":       "SCA",
    "loanshark":        "RIP",
    "holyorder":        "HOP",
    "holyorderfanatic": "HOF",
    "yaki":             "YAK",
    "pioneers":         "PIO",
    "terran":           "TER",
    "boron":            "BOR",
}

# Roman numerals for the nameindex attribute (X4 uses this as a duplicate counter).
_ROMAN = [
    "", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X",
    "XI", "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX",
]

# ─── Regex patterns (pre-compiled) ───────────────────────────────────────────
# Language file sector entries look like "{20003,270001}(The Void)".
# Extracts the human name from the parentheses at the end.
_SECTOR_NAME_RE = re.compile(r'\(([^)]+)\)\s*$')

# Matches sector macro strings like "cluster_43_sector001_macro".
_SECTOR_MACRO_RE = re.compile(r'cluster_(\d+)_sector(\d+)_macro', re.IGNORECASE)

# Matches bare {page,id} language references, e.g. "{20102,5}" or "{20215,3}".
# Used to resolve the basename attribute on station elements.
_TEXT_REF_RE = re.compile(r'^\{(\d+),(\d+)\}$')

# Extracts the ware ID from production module macros like "prod_arg_energycells_macro".
# The faction token uses non-greedy matching to handle multi-part names (e.g. prod_gen_...).
_PROD_MACRO_RE = re.compile(r'^prod_(?:\w+?)_(\w+)_macro$', re.IGNORECASE)


# ─── Language file loader ─────────────────────────────────────────────────────
def load_language(lang_path: pathlib.Path) -> tuple[dict, dict]:
    """
    Parses the language file in a single pass and returns both sector names
    and station type texts needed for name resolution.

    We load three pages in one file read rather than calling separate loaders:
      Page 20004 — sector names. Entries look like "{20003,XXXXXX}(The Void)";
                   we extract the text inside the final parentheses.
      Page 20102 — station/defence type names. These are what the 'basename'
                   attribute on station elements points to via {page,id} refs.
      Page 20215 — factory category names (Agricultural Goods Factory, etc.).
                   Used as a fallback when a station produces multiple wares.

    Returns:
        sector_names  {sector_id: name}   — keyed by the numeric language ID
        texts         {"page:id": text}   — keyed by "{page}:{id}" for fast lookup
    """
    sector_names: dict = {}
    texts:        dict = {}

    if not lang_path.exists():
        print(f"[Warning] Language file not found: {lang_path.name}")
        print("  Names will fall back to raw IDs and macros.")
        print("  Extract 0001-l044.xml from X4's .cat files using X Tools (Steam).")
        return sector_names, texts

    print(f"[Language] Loading from {lang_path.name}...")

    # Pages loaded and what each is used for:
    #   20004 — sector names (resolved from "(Name)" suffix in each entry)
    #   20102 — station/defence type names (what basename {page,id} refs point to)
    #   20201 — individual factory names (what factoryname attrs in wares.xml point to)
    #   20215 — factory category names, e.g. "Agricultural Goods Factory"
    TARGET_PAGES = {'20004', '20102', '20201', '20215'}
    found = set()

    try:
        tree = ET.parse(lang_path)
        for page in tree.getroot().findall('page'):
            pid = page.get('id', '')
            if pid not in TARGET_PAGES:
                continue

            if pid == '20004':
                # Sector name entries: extract the name from "(Name)" at the end.
                for t in page.findall('t'):
                    text = (t.text or '').strip()
                    m = _SECTOR_NAME_RE.search(text)
                    if m:
                        sector_names[t.get('id', '')] = m.group(1)
            else:
                # All other target pages: store raw text as-is for {page,id} lookup.
                for t in page.findall('t'):
                    tid  = t.get('id', '')
                    text = (t.text or '').strip()
                    if text:
                        texts[f"{pid}:{tid}"] = text

            found.add(pid)
            if found == TARGET_PAGES:
                break  # All target pages collected — no need to scan further.

        print(f"[Language] {len(sector_names)} sector names, {len(texts)} station type texts.")
    except Exception as e:
        print(f"[Warning] Could not parse language file: {e}")

    return sector_names, texts


# ─── Wares file loader ───────────────────────────────────────────────────────
def load_ware_factory_names(wares_path: pathlib.Path, texts: dict) -> dict:
    """
    Parses wares.xml and returns {ware_id: factory_name} for every ware that
    has a factoryname attribute.

    Why wares.xml is needed:
    The language file page 20201 contains factory name strings, but gives us no
    way to map a ware ID like "energycells" to a language entry like "20201:704".
    The factoryname attribute in wares.xml provides that link — each <ware> entry
    carries factoryname="{20201,704}", which we resolve against the already-loaded
    texts dict to get "Solar Power Plant".

    This function must be called after load_language() so that page 20201 is
    already present in texts. If the file is missing, an empty dict is returned
    and _type_from_prod_macros() falls back to title-cased ware IDs.
    """
    factory_names: dict = {}

    if not wares_path.exists():
        print(f"[Warning] Wares file not found: {wares_path.name}")
        print("  Factory names will fall back to title-cased ware IDs.")
        return factory_names

    print(f"[Wares] Loading factory names from {wares_path.name}...")
    try:
        tree = ET.parse(wares_path)
        for ware in tree.getroot().findall('ware'):
            ware_id     = ware.get('id', '')
            factoryname = ware.get('factoryname', '')
            if not ware_id or not factoryname:
                continue
            resolved = _resolve_text_ref(factoryname, texts)
            # Only store successfully resolved names — skip any unresolved refs.
            if resolved and not resolved.startswith('{'):
                factory_names[ware_id] = resolved

        print(f"[Wares] Loaded {len(factory_names)} factory names.")
    except Exception as e:
        print(f"[Warning] Could not parse wares file: {e}")

    return factory_names


# ─── Name resolution helpers ──────────────────────────────────────────────────

def _resolve_text_ref(raw: str, texts: dict) -> str:
    """
    Resolves a bare {page,id} language reference to its text string.
    Returns the raw value unchanged if it is not a reference or not found.

    For example: "{20102,5}" → "Trade Station" (if page 20102, entry 5 is loaded).
    """
    m = _TEXT_REF_RE.match(raw)
    if m:
        return texts.get(f"{m.group(1)}:{m.group(2)}", "")
    return raw


def _nameindex_to_roman(nameindex_str: str) -> str:
    """
    Converts a nameindex attribute string like "2" to a Roman numeral like "II".
    X4 uses nameindex to disambiguate multiple auto-named stations of the same type
    in the same sector, e.g. "The Void Trade Station I" and "The Void Trade Station II".
    Returns an empty string for index 0 or out-of-range values.
    """
    try:
        n = int(nameindex_str)
        if 0 < n < len(_ROMAN):
            return _ROMAN[n]
        return str(n) if n > 0 else ''
    except (ValueError, TypeError):
        return ''


def _type_from_prod_macros(prod_macros: list[str], factory_names: dict) -> str:
    """
    Derives a readable station type name from production module macros.

    For single-ware stations, looks up the exact in-game factory name from
    factory_names (sourced from wares.xml via load_ware_factory_names). This
    gives correct names like "Solar Power Plant" for energycells rather than
    the naive "Energy Cells Factory".

    Falls back to title-casing the ware ID for any ware not present in
    factory_names (e.g. mod-added wares or future DLC not in the wares file).

    For stations producing multiple distinct wares, we take the first
    alphabetically as a label — a rough approximation since the full
    priority-based group system (from data/wares.py) is not available here.
    """
    wares: set[str] = set()
    for macro in prod_macros:
        m = _PROD_MACRO_RE.match(macro)
        if m:
            wares.add(m.group(1).lower())

    if not wares:
        return ''
    if len(wares) == 1:
        ware_id = next(iter(wares))
        # Exact in-game name from wares.xml when available.
        return factory_names.get(ware_id) or f"{ware_id.replace('_', ' ').title()} Factory"
    else:
        primary = sorted(wares)[0].replace('_', ' ').title()
        return f"{primary} Complex"


def _resolve_station_name(
    name_attr:     str,
    basename:      str,
    nameindex:     str,
    owner:         str,
    macro:         str,
    prod_macros:   list[str],
    texts:         dict,
    factory_names: dict,
    sector:        str,
) -> str:
    """
    Resolves the display name for a station element.

    Mirrors the logic from station_scanner.py with the same priority order,
    but adapted for streaming (no full subtree available — production macros
    were collected incrementally as child elements streamed past).

    PLAYER STATIONS
      Path A (player-given name): name_attr is a literal string, used verbatim.
                                  No prefix or suffix — the player chose the name.
      Path B (auto-named):        basename resolves via {page,id} lookup.
      Path C (production fallback): derive type from production module macros.
      Format: "{sector} {type} {roman}"  e.g. "The Void Trade Station II"

    NPC STATIONS
      Path B first: basename or name_attr resolves via {page,id} lookup.
      Path C fallback: derive type from production module macros.
      Format: "{ABBR} {type} {roman} ({code})"  e.g. "ARG Trade Station I (ABZ-012)"
      Note: NPC stations never have player-given names, so Path A is skipped.
    """
    is_player = (owner == 'player')

    # ── Path A: Player gave this station a custom name ────────────────────────
    if is_player and name_attr and not _TEXT_REF_RE.match(name_attr):
        return name_attr

    # ── Path B: Resolve the basename / name attribute as a {page,id} ref ─────
    # The game stores the station type as a language reference in basename,
    # e.g. basename="{20102,5}" resolves to "Trade Station" via page 20102.
    type_name = ''
    raw_ref   = name_attr or basename
    if raw_ref:
        resolved = _resolve_text_ref(raw_ref, texts)
        if resolved and not resolved.startswith('{'):
            type_name = resolved

    # ── Path C: Derive type from production module macros ─────────────────────
    # Used when basename is absent or didn't resolve. Extract the ware ID from
    # each prod_{faction}_{ware}_macro child component and construct a label.
    if not type_name and prod_macros:
        type_name = _type_from_prod_macros(prod_macros, factory_names)

    # ── Last resort: macro-based fallback ─────────────────────────────────────
    if not type_name:
        if 'headquarters' in macro.lower():
            type_name = 'Headquarters'
        elif not is_player:
            type_name = 'Station'   # NPC station with no resolvable type
        else:
            return 'Unnamed Station'

    # ── Format the final display name ─────────────────────────────────────────
    roman = _nameindex_to_roman(nameindex)

    if is_player:
        # X4 format for auto-named player stations: "{sector} {type} {roman}"
        parts = [p for p in [sector, type_name, roman] if p]
        return ' '.join(parts)
    else:
        # X4 format for NPC stations: "{ABBR} {type} {roman} ({code})"
        # Code is appended here so the full display name matches X4's UI.
        abbr  = FACTION_ABBR.get(owner.lower(), '')
        parts = [p for p in [abbr, type_name, roman] if p]
        return ' '.join(parts)


# ─── Sector macro → human name ────────────────────────────────────────────────
def macro_to_name(macro: str, sector_names: dict) -> str | None:
    """
    Converts 'cluster_XY_sectorZZ_macro' to a human-readable sector name.

    Derives the language file key from the cluster and sector numbers:
      lang_id = (cluster * 10) concat (sector * 10 + 1, zero-padded to 3 digits)
    e.g. cluster_43, sector001  →  "430" + "011"  →  key "430011"

    Returns None for non-matching macros (e.g. some DLC sectors).
    """
    m = _SECTOR_MACRO_RE.match(macro)
    if not m:
        return None
    cluster_num = int(m.group(1))
    sector_num  = int(m.group(2))
    prefix  = str(cluster_num * 10)
    suffix  = str(sector_num * 10 + 1).zfill(3)
    lang_id = prefix + suffix
    return sector_names.get(lang_id)


# ─── Combined save file scanner ───────────────────────────────────────────────
def scan_save(
    save_path:     pathlib.Path,
    sector_names:  dict,
    texts:         dict,
    factory_names: dict,
) -> tuple[list[dict], list[dict]]:
    """
    Single-pass scan that collects both sectors and stations from the save file.

    SECTORS
    Detected on <component class="sector"> start events. The macro attribute is
    resolved to a human name immediately and the current_sector variable is
    updated — this is how subsequent station elements know what sector they are in.

    STATIONS
    Detected on <component class in STATION_CLASSES> start events. We save the
    element's attributes to a pending dict but do NOT finalise the name yet,
    because name resolution may require production module macros from children.

    While station_ref is set, any <component class="production"> start events
    have their macro appended to station_prod_macros. When the outer station's
    end event fires (identified by Python object identity, not tag matching),
    _resolve_station_name() is called with all collected data.

    The station_ref identity guard prevents nested sub-components that happen to
    share a station class value from being registered as separate stations.

    All elements are cleared on their end events to keep memory usage low.
    """
    seen_sectors:       set[str]              = set()
    sectors:            list[tuple[str, str]] = []
    stations:           list[dict]            = []

    current_sector      = "Unknown Sector"
    station_ref         = None   # reference to the open station element
    station_pending     = None   # attributes captured at station start event
    station_prod_macros = []     # production module macros collected during streaming

    opener = gzip.open if save_path.suffix == '.gz' else open

    print(f"[Scanning] Streaming {save_path.name} ...")

    with opener(save_path, 'rb') as f:
        for event, elem in ET.iterparse(f, events=('start', 'end')):

            if event == 'start' and elem.tag == 'component':
                cls   = elem.get('class', '')
                macro = elem.get('macro', '')

                # ── Sector tracking ───────────────────────────────────────────
                if cls == 'sector':
                    resolved = macro_to_name(macro, sector_names)
                    if resolved:
                        current_sector = resolved
                    if macro and macro not in seen_sectors:
                        seen_sectors.add(macro)
                        sectors.append({
                            'name':      resolved or macro,
                            'macro':     macro,
                            'code':      elem.get('code', ''),
                            'owner':     elem.get('owner', ''),
                            'contested': elem.get('contested') == '1',
                        })

                # ── Station detection ─────────────────────────────────────────
                elif station_ref is None and cls in STATION_CLASSES:
                    # Save the element reference so we can recognise this exact
                    # element's end event later, and capture the attributes now
                    # while they're available on the start event.
                    station_ref     = elem
                    station_pending = {
                        'name_attr': elem.get('name', ''),
                        'basename':  elem.get('basename', ''),
                        'nameindex': elem.get('nameindex', ''),
                        'owner':     elem.get('owner', ''),
                        'code':      elem.get('code', ''),
                        'cls':       cls,
                        'macro':     macro,
                        'sector':    current_sector,
                    }
                    station_prod_macros = []

                # ── Production child collection ───────────────────────────────
                # While inside a station, gather production module macros so that
                # _resolve_station_name() can fall back to them if basename fails.
                elif station_ref is not None and cls == 'production':
                    station_prod_macros.append(macro)

            # ── Station finalisation ──────────────────────────────────────────
            # When the exact element that opened our station closes, we have seen
            # all of its children and can resolve the display name.
            if event == 'end' and station_ref is not None and elem is station_ref:
                p = station_pending
                display = _resolve_station_name(
                    p['name_attr'],
                    p['basename'],
                    p['nameindex'],
                    p['owner'],
                    p['macro'],
                    station_prod_macros,
                    texts,
                    factory_names,
                    p['sector'],
                )
                stations.append({
                    'name':   display,
                    'owner':  p['owner'],
                    'code':   p['code'],
                    'cls':    p['cls'],
                    'macro':  p['macro'],
                    'sector': p['sector'],
                })
                station_ref         = None
                station_pending     = None
                station_prod_macros = []

            # Free every element once it has fully closed. On a large save file
            # this is what keeps RAM manageable — without it the whole tree
            # would accumulate in memory.
            if event == 'end':
                elem.clear()

    return sectors, stations


# ─── Entry point ──────────────────────────────────────────────────────────────
def main():
    start = time.perf_counter()

    if not SAVE_PATH.exists():
        print("[Error] Save file not found.")
        print(f"  Expected: {SAVE_PATH}")
        print("  Place save_001.xml (or save_001.xml.gz) in the project root.")
        input("\nPress Enter to exit...")
        return

    sector_names, texts   = load_language(LANG_PATH)
    factory_names         = load_ware_factory_names(WARES_PATH, texts)
    sectors, stations     = scan_save(SAVE_PATH, sector_names, texts, factory_names)
    elapsed               = time.perf_counter() - start

    sep = '─' * 70

    # ── Sector listing ────────────────────────────────────────────────────────
    if not sectors:
        print("\n  No sectors found in save file.")
        input("\nPress Enter to exit...")
        return

    sectors.sort(key=lambda s: s['name'].lower())

    print(f"\n{sep}")
    print(f"  SECTORS  ({len(sectors)} found)  ·  completed in {elapsed:.2f}s")
    print(sep)
    print(f"  {'Name':<40}  {'Code':<12}  Owner")
    print(f"  {'─' * 40}  {'─' * 12}  {'─' * 20}")
    for s in sectors:
        flag = '  ⚠ CONTESTED' if s['contested'] else ''
        print(f"  {s['name']:<40}  {s['code']:<12}  {s['owner']}{flag}")
    print(sep)

    # ── Stations grouped by sector ────────────────────────────────────────────
    # Group every station under its sector, then display sector headers with
    # the code and owner we now capture, with stations indented beneath each.
    # Only sectors that contain at least one station are shown here — empty
    # sectors are already visible in the full list above.
    by_sector: dict[str, list] = {}
    for st in stations:
        by_sector.setdefault(st['sector'], []).append(st)

    # Keyed lookup so each sector group header can show code/owner/contested.
    sector_meta = {s['name']: s for s in sectors}

    sectors_with_stations = sorted(by_sector.keys(), key=str.lower)

    print(f"\n{sep}")
    print(f"  STATIONS BY SECTOR  "
          f"({len(stations)} stations across {len(sectors_with_stations)} sectors)")
    print(sep)

    for sec_name in sectors_with_stations:
        meta      = sector_meta.get(sec_name, {})
        sec_code  = meta.get('code', '')
        sec_owner = meta.get('owner', '')
        flag      = '  ⚠ CONTESTED' if meta.get('contested') else ''
        sec_sts   = sorted(
            by_sector[sec_name],
            key=lambda s: (s['owner'] != 'player', s['owner'], s['name']),
        )
        n     = len(sec_sts)
        label = 'station' if n == 1 else 'stations'

        # Sector header line — code and owner alongside the name.
        parts = [sec_name]
        if sec_code:  parts.append(sec_code)
        if sec_owner: parts.append(sec_owner)
        print(f"\n  ┌─ {'  ·  '.join(parts)}  ({n} {label}){flag}")

        for st in sec_sts:
            owner_tag = f"[{st['owner']}]" if st['owner'] else ""
            code_str  = f"({st['code']})"  if st['code']  else ""
            print(f"  │   {owner_tag:<16}  {st['name']:<44}  {code_str}")

    print(f"\n{sep}")

    input("\nPress Enter to exit...")


if __name__ == '__main__':
    main()
