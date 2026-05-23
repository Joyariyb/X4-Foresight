# ─────────────────────────────────────────────────────────────────────────────
#  SHIPS
#  Extracts player ships (always) and optionally NPC ships in sectors of
#  interest (where the player has stations or ships).
#
#  Three scan tiers, controlled by the caller:
#    Tier 1 — Player ships only               scan_ships(file, sector_names)
#    Tier 2 — + NPC ships in station sectors  scan_ships(..., station_sectors={...})
#    Tier 3 — + NPC ships in all ship sectors scan_ships(..., collect_all_npcs=True)
# ─────────────────────────────────────────────────────────────────────────────

import re
import pathlib
from lxml import etree as ET
from scanner.language import macro_to_sector_name, open_save
from data.ships import SHIP_NAMES
from data.ship_stats import SHIP_STATS  # static specs per macro (max hull, etc.)

# ─────────────────────────────────────────────────────────────────────────────
#  LOOKUP TABLES
# ─────────────────────────────────────────────────────────────────────────────

# Maps substrings found in ship macro names to human-readable role labels.
# Order matters: more specific patterns (e.g. 'miner_solid') must come before
# broader ones (e.g. 'miner') so the right label is matched first.
ROLE_PATTERNS = [
    (re.compile(r'miner_solid',    re.I), "Miner (Solid)"),
    (re.compile(r'miner_liquid',   re.I), "Miner (Liquid)"),
    (re.compile(r'miner_gas',      re.I), "Miner (Gas)"),
    (re.compile(r'miner',          re.I), "Miner"),
    (re.compile(r'trans_container',re.I), "Freighter"),
    (re.compile(r'trans_',         re.I), "Transport"),
    (re.compile(r'heavyfighter',   re.I), "Heavy Fighter"),
    (re.compile(r'fighter',        re.I), "Fighter"),
    (re.compile(r'corvette',       re.I), "Corvette"),
    (re.compile(r'frigate',        re.I), "Frigate"),
    (re.compile(r'bomber',         re.I), "Bomber"),
    (re.compile(r'destroyer',      re.I), "Destroyer"),
    (re.compile(r'carrier',        re.I), "Carrier"),
    (re.compile(r'resupplier',     re.I), "Resupplier"),
    (re.compile(r'builder',        re.I), "Builder"),
    (re.compile(r'scout',          re.I), "Scout"),
]

# Maps the ship class attribute from the XML to the short size label used
# throughout the rest of the codebase and the UI.
SIZE_LABELS = {
    "ship_s":  "S",
    "ship_m":  "M",
    "ship_l":  "L",
    "ship_xl": "XL",
}

# Maps X4's internal order identifiers to human-readable labels.
# These come from the 'order' attribute on <order> elements inside <orders>.
ORDER_LABELS = {
    "MiningRoutine":        "Mining",
    "MiningCollect":        "Mining (Collecting)",
    "Middleman":            "Trading",
    "TradeRoutine":         "Trading",
    "Trade":                "Trading",
    "Patrol":               "Patrolling",
    "Escort":               "Escorting",
    "KeepFormation":        "In Formation",
    "Dock":                 "Docking",
    "Wait":                 "Waiting",
    "MoveWait":             "Waiting",
    "Flee":                 "Fleeing",
    "Attack":               "Attacking",
    "Collect":              "Collecting",
    "TerraformMonitor":     "Monitoring",
    "Repair":               "Repairing",
    "Build":                "Building",
    "Supply":               "Supplying",
    "Police":               "Policing",
    "Salvage":              "Salvaging",
    "BoardingOperation":    "Boarding",
    "Protect":              "Protecting",
    "ProtectStation":       "Protecting Station",
    "Resupply":             "Resupplying",
    "Explore":              "Exploring",
}

from scanner.crew_scanner import LANG_STRING_RE, _parse_pilot, _extract_people, _iter_components
from data.station_stats import STATION_STATS

SHIP_CLASSES = {"ship_s", "ship_m", "ship_l", "ship_xl"}

MACRO_FACTION_MAP = {
    "arg": "Argon",      "tel": "Teladi",
    "par": "Paranid",    "tri": "Paranid",
    "spl": "Split",      "ter": "Terran",
    "bor": "Boron",      "xen": "Xenon",
    "yak": "Yaki",       "pir": "Buccaneer",
    "kha": "Kha'ak",     "buc": "Buccaneer",
    "atf": "Terran",     "pio": "Pioneer",
}


# ─────────────────────────────────────────────────────────────────────────────
#  ROLE AND FACTION EXTRACTION
# ─────────────────────────────────────────────────────────────────────────────

def extract_role(macro: str) -> str:
    """
    Returns a human-readable role string derived from a ship macro name.

    Iterates ROLE_PATTERNS in order and returns the label for the first match.
    Returns "Unknown" if no pattern matches.
    """
    for pattern, label in ROLE_PATTERNS:
        if pattern.search(macro):
            return label
    return "Unknown"


def extract_faction_from_macro(macro: str) -> str:
    """
    Extracts the original hull faction from the macro name.

    X4 macro names follow the pattern: ship_{faction}_{size}_{role}_...
    The second segment is a short faction code, e.g. 'arg' for Argon or
    'xen' for Xenon. This is useful for identifying captured ships where
    the current owner differs from the hull's original manufacturer.

    Examples:
        ship_xen_m_corvette_02_a_macro  ->  'Xenon'
        ship_arg_l_trans_container_01_b_macro  ->  'Argon'
    """
    parts = macro.lower().split("_")
    if len(parts) > 1:
        return MACRO_FACTION_MAP.get(parts[1], parts[1].title())
    return "Unknown"


# ─────────────────────────────────────────────────────────────────────────────
#  SHIP NAME RESOLUTION
# ─────────────────────────────────────────────────────────────────────────────

def resolve_ship_type(macro: str) -> str:
    """
    Returns a display name for a ship's type, always as a non-None string.

    Resolution uses two strategies in priority order:

    1. SHIP_NAMES lookup (data/ships.py)
       A pre-generated dict mapping macro strings to exact in-game names,
       e.g. "ship_tel_s_trans_container_01_b_macro" -> "Magpie Sentinel".
       This is the preferred result when available.

    2. Macro-derived fallback
       If the macro isn't in SHIP_NAMES (e.g. after a game update adds new
       ships before data/ships.py has been regenerated), the name is
       constructed from the parts of the macro string itself.

       X4 macro names follow this structure:
           ship_{faction}_{size}_{role...}_{index}_{variant}_macro

       From that we can reliably extract:
         - Faction:  the second segment, mapped via extract_faction_from_macro()
         - Size:     the third segment, uppercased (S, M, L, XL)
         - Role:     matched via extract_role() against the full macro string
         - Variant:  the last segment before 'macro', if it's a single letter
                     (a, b, c...) indicating a hull generation or refit

       Examples:
           ship_arg_l_trans_container_01_b_macro  ->  "Argon L Freighter (B)"
           ship_xen_m_corvette_02_a_macro         ->  "Xenon M Corvette (A)"
           ship_par_m_trans_container_01_a_macro  ->  "Paranid M Freighter (A)"
    """
    # Priority 1: exact lookup in the pre-generated ship names table.
    if macro in SHIP_NAMES:
        return SHIP_NAMES[macro]

    # Priority 2: construct a name from the macro string's own structure.
    parts = macro.split('_')

    # A well-formed ship macro has at least: ship + faction + size + one role part.
    # If the string is too short to parse, return it as-is rather than crash.
    if len(parts) < 4:
        return macro

    faction = extract_faction_from_macro(macro)  # e.g. "Argon", "Xenon"
    size    = parts[2].upper()                   # e.g. "S", "M", "L", "XL"
    role    = extract_role(macro)                # e.g. "Freighter", "Corvette"

    # The variant letter (a, b, c...) is the last segment before the trailing
    # 'macro' token. Check it's exactly one alphabetic character so we don't
    # accidentally treat a number or multi-character token as a variant.
    core_parts = parts[:-1]  # strip the trailing 'macro' token
    last = core_parts[-1]
    variant = last if len(last) == 1 and last.isalpha() else None

    name = f"{faction} {size} {role}"
    if variant:
        name += f" ({variant.upper()})"

    return name


# ─────────────────────────────────────────────────────────────────────────────
#  CHILD ELEMENT PARSERS
#  These functions all receive a fully-buffered ship element (with all its
#  children still in memory) and extract one specific piece of data from it.
# ─────────────────────────────────────────────────────────────────────────────

def _parse_sector(
    ship_elem:            ET.Element,
    sector_names:         dict,
    sector_macro_to_name: dict | None = None,
) -> str:
    """
    Resolves the sector name for a ship.

    Three sources are tried in priority order:

    1. Direct dict lookup via '_sector_macro' — when the caller supplies
       sector_macro_to_name (built during Pass 1), the sector macro is looked
       up directly without any regex. This is the fast, authoritative path and
       handles all sector types including DLC sectors whose macros don't follow
       the standard cluster_N_sectorN pattern.

    2. Regex fallback via '_sector_macro' — used when sector_macro_to_name is
       absent (ships-only scan mode where Pass 1 never ran). Parses the cluster
       and sector numbers from the macro string and derives the language key.
       Works for all standard macros; may fail for DLC sectors.

    3. Zone macro fallback via '_zone_macro' — for named zones whose macro
       encodes the parent sector (pattern: zone{N}_{sector_macro}). The regex
       strips the prefix and then applies priority 1 or 2 on the extracted
       sector macro. Less reliable than the sector macro sources above.
    """
    sector_macro = ship_elem.get('_sector_macro', '')
    if sector_macro:
        # Priority 1: direct lookup — O(1), no regex, handles all macro formats.
        if sector_macro_to_name is not None:
            name = sector_macro_to_name.get(sector_macro)
            if name:
                return name
        # Priority 2: regex-based derivation from the macro string.
        result = macro_to_sector_name(sector_macro, sector_names)
        if result:
            return result

    # Priority 3: extract a sector macro embedded in the zone macro string.
    zone_macro = ship_elem.get('_zone_macro', '')
    m = re.match(r'zone\d+_(cluster_.+)', zone_macro, re.IGNORECASE)
    if m:
        embedded = m.group(1)
        if sector_macro_to_name is not None:
            name = sector_macro_to_name.get(embedded)
            if name:
                return name
        result = macro_to_sector_name(embedded, sector_names)
        if result:
            return result

    return "Unknown Sector"



def _parse_current_order(ship_elem: ET.Element) -> str:
    """
    Returns a human-readable label for the ship's current active order.

    A ship can have multiple orders queued in its <orders> block. This function
    uses the following priority to decide which one to report:

    1. The first non-temporary order with state='started' — this is the order
       the ship is actively executing right now.
    2. The order marked default='1' — the ship's standing order that it falls
       back to when it has nothing else to do.
    3. "Idle" — if neither of the above is found.

    The 'temp' flag on an order indicates it was issued by the player directly
    (e.g. "go to this station") and will be discarded once complete. We skip
    temp orders so the reported order reflects the ship's actual assignment
    rather than a one-off command.
    """
    orders_elem = ship_elem.find('orders')
    if orders_elem is None:
        return "Idle"

    default_order = None
    for order in orders_elem.findall('order'):
        raw   = order.get('order', 'Idle')
        label = ORDER_LABELS.get(raw, raw)

        # Track the default order as a fallback in case no active one is found.
        if order.get('default') == '1':
            default_order = label

        # A started, non-temporary order is the ship's current active task.
        if order.get('state') == 'started' and order.get('temp') != '1':
            return label

    return default_order or "Idle"


def _parse_commander(ship_elem: ET.Element) -> str | None:
    """
    Returns the component ID reference of this ship's commander, or None.

    In X4, a commander is another ship (or station) that this ship reports to.
    The relationship is stored as a <connection> element inside <connections>
    with connection='commander'. The referenced ID can be used to look up the
    commanding ship elsewhere in the data.
    """
    for conn in ship_elem.findall('connections/connection'):
        if conn.get('connection') == 'commander':
            connected = conn.find('connected')
            if connected is not None:
                return connected.get('connection')
    return None


def _parse_hull(ship_elem: ET.Element) -> float | None:
    """
    Returns the ship's current hull HP, or None if the ship is at full health.

    X4 only writes <hull value="..."/> when hull is below maximum — absence
    of the element means the ship is undamaged.
    """
    hull_elem = ship_elem.find('hull')
    if hull_elem is None:
        return None
    try:
        return float(hull_elem.get('value', 0))
    except (ValueError, TypeError):
        return None




def _parse_shield(ship_elem: ET.Element) -> dict:
    """
    Returns total shield HP, max, and percentage for a ship.

    Ship shields are stored on individual shieldgenerator class components
    nested inside the ship element — there is no aggregate <shield> on the
    ship itself. Absent <shield> on a generator means it is at full capacity,
    matching the same convention used for hull HP.

    _iter_components() is used so that shield generators on docked ships
    (inside a carrier) are not counted toward the carrier's own shield total.

    Max shield per generator comes from STATION_STATS — ships and stations use
    the same equipment macros, so no separate lookup table is needed.

    Returns a dict with shield_hp, shield_max, shield_pct — all None if the
    ship has no shield generators installed.
    """
    current   = 0.0
    max_total = 0.0
    found_any = False

    for comp in _iter_components(ship_elem):
        if not comp.get('class', '').startswith('shieldgenerator'):
            continue
        stats = STATION_STATS.get(comp.get('macro', ''), {})
        if 'max_shield' not in stats:
            continue
        found_any = True
        max_cap   = stats['max_shield']
        sh_elem   = comp.find('shield')
        if sh_elem is not None:
            try:
                current += float(sh_elem.get('value', max_cap))
            except (ValueError, TypeError):
                current += max_cap
        else:
            current += max_cap
        max_total += max_cap

    if not found_any:
        return {"shield_hp": None, "shield_max": None, "shield_pct": None}

    return {
        "shield_hp":  current,
        "shield_max": max_total,
        "shield_pct": (current / max_total * 100.0) if max_total else None,
    }


def _parse_software(ship_elem: ET.Element) -> list[str]:
    """
    Returns a list of software ware IDs installed on the ship.

    Software is stored as a space-separated string in the 'wares' attribute
    of the <software> element, e.g. "software_dockmk2 software_trademk1".
    Returns an empty list if the element is absent or has no wares.
    """
    sw = ship_elem.find('software')
    if sw is None:
        return []
    wares_str = sw.get('wares', '')
    return [w for w in wares_str.split() if w]


def _extract_docked_ships(
    carrier_elem: ET.Element,
    carrier_sector: str,
    owner: str,
) -> list[dict]:
    """
    Extracts all ships nested inside a fully-buffered carrier element.

    Ships docked inside a carrier appear as descendants in the XML but are
    invisible to the main iterparse loop (inside_ship blocks their detection).
    This function scans the carrier's complete in-memory subtree once it is
    fully buffered and extracts each nested ship as a normal entry, inheriting
    the carrier's resolved sector.
    """
    docked = []

    for child in carrier_elem.iter():
        if child is carrier_elem:
            continue
        cls = child.get('class', '')
        if cls not in SHIP_CLASSES:
            continue

        macro       = child.get('macro', '')
        code        = child.get('code',  '')
        role        = extract_role(macro)
        size        = SIZE_LABELS.get(cls, cls)
        hull_origin = extract_faction_from_macro(macro)
        order       = _parse_current_order(child)
        pilot       = _parse_pilot(child)
        sw          = _parse_software(child)
        cmdr        = _parse_commander(child)
        hull_hp  = _parse_hull(child)
        max_hull = SHIP_STATS.get(macro, {}).get("max_hull")

        if hull_hp is None:
            hull_pct = 100.0
        elif max_hull:
            hull_pct = (hull_hp / max_hull) * 100.0
        else:
            hull_pct = None

        shield = _parse_shield(child)

        raw_name = child.get('name')
        if raw_name and not LANG_STRING_RE.match(raw_name):
            name = raw_name
        else:
            name = resolve_ship_type(macro)

        docked.append({
            "code":        code,
            "name":        name,
            "class":       cls,
            "size":        size,
            "macro":       macro,
            "role":        role,
            "hull_origin": hull_origin,
            "owner":       owner,
            "sector":      carrier_sector,
            "order":       order,
            "pilot":       pilot,
            "software":    sw,
            "commander":   cmdr,
            "hull_hp":     hull_hp,
            "hull_pct":    hull_pct,
            "max_hull":    max_hull,
            "shield_hp":   shield["shield_hp"],
            "shield_max":  shield["shield_max"],
            "shield_pct":  shield["shield_pct"],
        })

    return docked


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN SCANNER
# ─────────────────────────────────────────────────────────────────────────────

def scan_ships(
    file_path:            pathlib.Path,
    sector_names:         dict,
    station_sectors:      set[str] | None = None,
    ship_sectors:         set[str] | None = None,
    npc_only:             bool = False,
    collect_all_npcs:     bool = False,
    sector_macro_to_name: dict | None = None,
) -> dict:
    """
    Streams through the X4 save and extracts ship data.

    Uses iterparse() to process the XML one element at a time, which keeps
    RAM usage low even on 700MB+ save files. The file is never fully loaded
    into memory.

    PLAYER SHIPS are collected unless npc_only=True. NPC ships are usually only
    collected for sectors in 'context_sectors', which is built from
    station_sectors and/or ship_sectors depending on the scan tier.

    collect_all_npcs=True is used by the tier 3 CLI scan. In that mode we do
    not know the player ship sectors until after this pass has collected the
    player ships, so we temporarily collect slim records for every NPC ship and
    let the caller filter them down afterward. That avoids streaming the save
    file a second time just to collect NPC ships.

    npc_only=True is still available for callers that already have player
    ships and only want NPC rows. In that mode, player ship buffering is
    skipped and 'player_ships' in the returned dict will be empty.

    BUFFERING: When a ship element's opening tag is detected, elem.clear()
    is suppressed for all of its descendants until the closing tag arrives.
    This keeps the ship's child elements (crew, orders, software, etc.) in
    memory so the _parse_* functions can read them. Once parsing is done the
    element is cleared manually.

    ZONE TRACKING: Ships are nested under zone elements in the XML, not
    directly under sectors. The current zone macro is tracked as a running
    variable and stamped onto each ship element before buffering starts, so
    _parse_sector() can resolve the sector later.

    Parameters:
        file_path            — path to the save file (.xml or .xml.gz)
        sector_names         — dict from load_sector_names(), maps lang IDs to names
        station_sectors      — set of sector names where the player has stations
                               (used for tier 2 NPC collection)
        ship_sectors         — set of sector names where the player has ships
                               (used for tier 3 NPC collection, adds to station_sectors)
        npc_only             — if True, skip player ship buffering entirely;
                               player_ships in the returned dict will be empty
        collect_all_npcs     — if True, buffer and record every NPC ship, then
                               leave sector filtering to the caller
        sector_macro_to_name — optional dict mapping sector macro strings to resolved
                               display names, built during Pass 1. When present,
                               _parse_sector() does a direct O(1) lookup instead of
                               running the regex derivation. Pass None (default) when
                               running in ships-only mode — the regex fallback is used.

    Returns a dict with keys:
        'player_ships' — list of ship dicts for all player-owned ships
                         (empty list when npc_only=True)
        'npc_ships'    — list of ship dicts for NPC ships in context sectors
    """
    # Build the set of sectors in which NPC ships should be collected.
    # If neither is provided (tier 1), context_sectors is empty and no NPC
    # ships will be collected.
    context_sectors = set()
    if station_sectors:
        context_sectors |= station_sectors
    if ship_sectors:
        context_sectors |= ship_sectors

    player_ships: list[dict] = []
    npc_ships:    list[dict] = []
    crew:         list[dict] = []   # all named crew on player ships (pilots, service, marines)

    # Tracks the macro of the sector and zone the parser is currently inside.
    # current_sector_macro is the stable cluster_N_sectorN_macro used as the
    # primary location source. current_zone_macro is the fallback for named zones.
    # Both reset to "" on the respective closing tag.
    current_sector_macro = ""
    current_zone_macro   = ""

    # State variables for the ship buffering mechanism.
    inside_ship        = False   # True while we're collecting a ship's children
    ship_elem_pending  = None    # The ship element being buffered
    ship_owner_pending = None    # Its owner attribute, saved alongside it
    ship_depth         = 0       # Nesting depth counter; hits 0 at closing tag

    print("[Scanning] Ships — player fleet and context NPC ships...")

    with open_save(file_path) as f:
        context = ET.iterparse(f, events=('start', 'end'))

        for event, elem in context:
            tag = elem.tag
            cls = elem.get('class', '')

            # ── Sector and zone tracking ───────────────────────────────────
            # Only update when we're not inside a buffered ship, to avoid
            # misreading nested references within the ship XML.
            if not inside_ship:
                if event == 'start':
                    if cls == 'sector':
                        current_sector_macro = elem.get('macro', '')
                    elif cls == 'zone':
                        current_zone_macro = elem.get('macro', '')
                elif event == 'end':
                    if cls == 'sector':
                        current_sector_macro = ""
                    elif cls == 'zone':
                        current_zone_macro = ""

            # ── Ship detection ─────────────────────────────────────────────
            # When a ship's opening tag is seen, decide whether to buffer it.
            if event == 'start' and cls in SHIP_CLASSES and not inside_ship:
                owner = elem.get('owner', '')

                # When npc_only=True, the caller only wants NPC rows.
                # In that case, there is no need to buffer player ships.
                is_player      = (not npc_only) and (owner == 'player')
                # NPC ownership is already visible on this opening tag.
                #
                # Normal tier 2 behaviour:
                #   Only bother buffering NPC ships when we have context sectors
                #   to check against later.
                #
                # Tier 3 one-pass behaviour:
                #   collect_all_npcs=True means "record slim NPC rows now, then
                #   filter after we know the player ship sectors."
                is_context_npc = (
                    owner != 'player'
                    and (collect_all_npcs or bool(context_sectors))
                )

                if is_player or is_context_npc:
                    # Stamp both location markers onto the element now so
                    # _parse_sector() can resolve the sector name once the
                    # full ship subtree is in memory.
                    elem.set('_sector_macro', current_sector_macro)
                    elem.set('_zone_macro',   current_zone_macro)

                    inside_ship        = True
                    ship_elem_pending  = elem
                    ship_owner_pending = owner
                    ship_depth         = 1
                    continue  # skip the normal elem.clear() at the bottom

            # ── Ship buffering ─────────────────────────────────────────────
            # While inside a ship, track nesting depth. When depth reaches 0,
            # the ship's closing tag has been reached and all children are in
            # memory — parse the ship and then clear the element.
            if inside_ship:
                if event == 'start':
                    ship_depth += 1
                elif event == 'end':
                    ship_depth -= 1

                    if ship_depth == 0:
                        # All child elements are now in memory. Extract data.
                        se    = ship_elem_pending
                        owner = ship_owner_pending
                        macro = se.get('macro', '')
                        code  = se.get('code',  '')
                        cls   = se.get('class', '')

                        # ── Fields extracted for every ship ────────────────
                        # These are cheap lookups needed by both player and
                        # NPC ship entries, so we always compute them up front
                        # rather than duplicating the calls in each branch below.
                        sector = _parse_sector(se, sector_names, sector_macro_to_name)
                        role   = extract_role(macro)
                        size   = SIZE_LABELS.get(cls, cls)
                        hull   = extract_faction_from_macro(macro)
                        order  = _parse_current_order(se)

                        # ── Ship name resolution ───────────────────────────
                        # Priority order:
                        #   1. Player-given custom name — the 'name' attribute
                        #      on the component element, set via the in-game UI.
                        #   2. Ship type name — resolved by resolve_ship_type()
                        #      from either the SHIP_NAMES lookup or the macro
                        #      string itself. Always returns a non-None string.
                        #
                        # Some 'name' attributes in the save are language
                        # reference strings like "{20101,22603}" rather than
                        # actual text. LANG_STRING_RE detects these so we can
                        # skip them and fall through to the type name.
                        raw_name = se.get('name')
                        if raw_name and not LANG_STRING_RE.match(raw_name):
                            # Priority 1: player has given this ship a custom name.
                            name = raw_name
                        else:
                            # Priority 2: derive a type name from the macro.
                            # This always returns a string, never None.
                            name = resolve_ship_type(macro)

                        if owner == 'player':
                            # ── Player-only extractions ────────────────────
                            # Crew, software, and hull health are only relevant
                            # for ships we own. We deliberately skip them for
                            # NPC ships — calling _parse_pilot() on 1,000+ NPC
                            # ships would waste time traversing subtrees whose
                            # results we'd immediately throw away.
                            pilot    = _parse_pilot(se)
                            sw       = _parse_software(se)
                            cmdr     = _parse_commander(se)

                            # Build crew roster entries for this ship.
                            # Named pilot goes in first (if one is assigned),
                            # then all service crew and marines from <people>.
                            if pilot["name"]:
                                crew.append({
                                    "name":          pilot["name"],
                                    "role":          "pilot",
                                    "skills":        pilot["skills"],
                                    "assigned_to":   name,
                                    "assigned_code": code,
                                    "assigned_type": "ship",
                                    "sector":        sector,
                                })
                            crew.extend(_extract_people(se, name, code, sector))

                            # hull_hp is the ship's current HP as a raw float.
                            # X4 only writes <hull value="..."/> when the ship
                            # has taken damage — if the element is absent the
                            # ship is undamaged, so we treat None as full health.
                            hull_hp  = _parse_hull(se)

                            # Look up the ship type's maximum HP from SHIP_STATS.
                            # If the macro isn't in the table (e.g. a modded ship
                            # or a newly added hull we haven't extracted yet),
                            # max_hull stays None and we fall back to showing the
                            # raw HP value instead of a percentage.
                            max_hull = SHIP_STATS.get(macro, {}).get("max_hull")

                            # Compute hull as a percentage of maximum.
                            # Three possible outcomes:
                            #   hull_hp is None  → ship is undamaged → 100%
                            #   max_hull is None → we don't know the max → None
                            #   both present     → calculate the percentage
                            if hull_hp is None:
                                hull_pct = 100.0
                            elif max_hull:
                                hull_pct = (hull_hp / max_hull) * 100.0
                            else:
                                hull_pct = None

                            shield = _parse_shield(se)

                            player_ships.append({
                                "code":        code,
                                "object_id":   se.get('id', ''),  # hex ref e.g. "[0x4d4c]" — used as buyer/seller in economylog trade entries
                                "name":        name,
                                "class":       cls,
                                "size":        size,
                                "macro":       macro,
                                "role":        role,
                                "hull_origin": hull,
                                "owner":       owner,
                                "sector":      sector,
                                "order":       order,
                                "pilot":       pilot,
                                "software":    sw,
                                "commander":   cmdr,
                                "hull_hp":     hull_hp,
                                "hull_pct":    hull_pct,
                                "max_hull":    max_hull,
                                "shield_hp":   shield["shield_hp"],
                                "shield_max":  shield["shield_max"],
                                "shield_pct":  shield["shield_pct"],
                            })
                            # Also extract any ships docked inside this one.
                            # Carriers hold fighter wings internally — those ships
                            # are invisible to the main iterparse loop because the
                            # inside_ship flag blocks their detection, so we pull
                            # them from the buffered subtree separately.
                            player_ships.extend(
                                _extract_docked_ships(se, sector, owner)
                            )

                        elif collect_all_npcs or sector in context_sectors:
                            # ── NPC ship entry (slim) ──────────────────────
                            # We only need enough data to show faction activity
                            # in the UI — who is where and doing what. Crew and
                            # hull health are omitted because we don't own these
                            # ships and the extra parsing wouldn't be used.
                            #
                            # Commander: trade ships assigned to a station carry
                            # a <connection connection="commander"> that points
                            # to their controlling station. We extract it here so
                            # the trade history display can show which station an
                            # NPC ship is trading on behalf of. Free traders and
                            # ships on manual orders may return None.
                            cmdr = _parse_commander(se)

                            npc_ships.append({
                                "code":        code,
                                "object_id":   se.get('id', ''),  # hex ref e.g. "[0x1f673]"
                                "name":        name,
                                "class":       cls,
                                "size":        size,
                                "macro":       macro,
                                "role":        role,
                                "hull_origin": hull,      # faction that manufactured the hull
                                "owner":       owner,
                                "sector":      sector,
                                "order":       order,
                                "commander":   cmdr,      # raw ID of the commanding station (or None)
                            })

                        # Reset buffering state and free the element's memory.
                        inside_ship        = False
                        ship_elem_pending  = None
                        ship_owner_pending = None
                        se.clear()
                        continue

            # ── Default cleanup ────────────────────────────────────────────
            # For any element we're not buffering, free its memory immediately
            # after its closing tag. This is what keeps RAM usage low.
            if event == 'end' and not inside_ship:
                elem.clear()

    return {
        "player_ships": player_ships,
        "npc_ships":    npc_ships,
        "crew":         crew,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  STATION-DOCKED SHIP MERGE
# ─────────────────────────────────────────────────────────────────────────────

def merge_station_docked_ships(
    stations:     list[dict],
    player_ships: list[dict],
) -> list[dict]:
    """
    Adds player ships docked at stations that the main ship scanner missed.

    WHY THIS IS NEEDED:
      During Pass 3, the ship scanner streams the save XML with iterparse. Ships
      docked inside carrier hulls are blocked by the `inside_ship` flag and are
      recovered separately via `_extract_docked_ships()`. However, ships sitting
      in a *station's* docking bays can have a different XML layout — particularly
      at the player HQ, where ships under construction or stored in dry-dock bays
      sometimes lack the top-level attributes (sector macro, space connection) that
      the ship scanner relies on to decide whether to buffer them. These ships are
      captured reliably by the station scanner's `_extract_station_docked_ships()`
      but they end up only in each station's `docked_ships` list, never in
      `player_ships`.

    NOTE ON "CIVILIAN" SHIPS:
      Ships with owner="civilian" are not player-owned — they belong to X4's
      ambient civilian faction (mass traffic, neutral storyline vessels, etc.).
      The UI handles civilian ships that are docked at player stations by looking
      them up in npc_ships and navigating to the CIV fleet subtab on click.
      Only ships with owner="player" are merged here.

    WHAT IT DOES:
      Iterates every station's `docked_ships` list, finds any player-owned ship
      whose code is not already in `player_ships`, and appends a stub entry so the
      ship appears in the fleet data with a correct translated name, size, role, and
      sector. Health and pilot data are unavailable from the station scanner, so
      those fields are set to None.

    Args:
        stations:     List of station dicts from Pass 1 (scan_save). Each entry
                      must have a 'sector' key and an optional 'docked_ships' list.
        player_ships: The player fleet list from Pass 3 (scan_ships). Modified in
                      place and also returned for convenience.

    Returns:
        The updated player_ships list with any missing station-docked ships added.
    """
    # Build a set of codes we already have so the lookup is O(1) per ship.
    existing_codes = {s["code"] for s in player_ships}

    for station in stations:
        station_sector = station.get("sector", "Unknown")

        for ds in station.get("docked_ships", []):
            # Only add ships the player directly owns. Civilian-faction ships
            # (owner="civilian") that happen to be docked here are handled
            # entirely on the UI side — they already exist in npc_ships with
            # full data and the fleet tab navigates to the CIV subtab for them.
            if ds.get("owner") != "player":
                continue
            code = ds.get("code", "")
            if not code or code in existing_codes:
                continue

            macro = ds.get("macro", "")
            cls   = ds.get("class", "")

            # Build a complete stub that matches the shape of a normal player_ships
            # entry. Fields that require parsing the full ship XML subtree (pilot,
            # software, hull/shield health) are left as None — the UI handles None
            # gracefully, and a future scanner improvement could fill these in.
            player_ships.append({
                "code":        code,
                "name":        resolve_ship_type(macro),
                "class":       cls,
                "size":        SIZE_LABELS.get(cls, cls),
                "macro":       macro,
                "role":        extract_role(macro),
                "hull_origin": extract_faction_from_macro(macro),
                "owner":       "player",
                "sector":      station_sector,
                # Ships in a station bay are not executing an active order — show
                # "Docked" so they appear in the fleet tab under a sensible label.
                "order":       "Docked",
                "pilot":       {"name": None, "skills": []},
                "software":    [],
                "commander":   None,
                # Health data is not available from the station scanner's docked
                # ship extraction — would require buffering the full ship subtree.
                "hull_hp":     None,
                "hull_pct":    None,
                "max_hull":    None,
                "shield_hp":   None,
                "shield_max":  None,
                "shield_pct":  None,
            })
            existing_codes.add(code)

    return player_ships


# ─────────────────────────────────────────────────────────────────────────────
#  SUMMARY HELPERS
#  These are used by display.py for the console report. The JSON export uses
#  its own summary builder in export/jsonexport.py instead.
# ─────────────────────────────────────────────────────────────────────────────

def summarise_player_fleet(player_ships: list[dict]) -> dict:
    """
    Returns a high-level summary of the player fleet grouped by role, order,
    and sector. Used by display.py to print the console fleet report.
    """
    from collections import Counter, defaultdict

    by_role   = Counter()
    by_sector = defaultdict(list)
    by_order  = Counter()

    for ship in player_ships:
        by_role[ship["role"]]   += 1
        by_order[ship["order"]] += 1
        by_sector[ship["sector"]].append(ship["role"])

    return {
        "total":     len(player_ships),
        "by_role":   dict(by_role),
        "by_order":  dict(by_order),
        "by_sector": {k: dict(Counter(v)) for k, v in by_sector.items()},
    }


def summarise_npc_presence(npc_ships: list[dict]) -> dict:
    """
    Returns NPC ship counts grouped by sector and faction.
    Used by display.py to show nearby NPC activity in the console report.
    """
    from collections import defaultdict, Counter

    by_sector = defaultdict(lambda: defaultdict(int))

    for ship in npc_ships:
        by_sector[ship["sector"]][ship["owner"]] += 1

    return {
        sector: dict(factions)
        for sector, factions in by_sector.items()
    }
