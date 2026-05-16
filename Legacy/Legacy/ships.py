# ─────────────────────────────────────────────────────────────────────────────
#  SHIPS
#  Extracts player ships (always) and optionally NPC ships in sectors of
#  interest (where the player has stations or ships).
#
#  Three scan tiers, controlled by the caller:
#    Tier 1 — Player ships only              scan_ships(file, sector_names)
#    Tier 2 — + NPC ships in station sectors scan_ships(..., station_sectors={...})
#    Tier 3 — + NPC ships in all ship sectors scan_ships(..., ship_sectors={...})
# ─────────────────────────────────────────────────────────────────────────────

import re
import pathlib
import xml.etree.ElementTree as ET

# ─────────────────────────────────────────────────────────────────────────────
#  ROLE EXTRACTION
#  Derives a human-readable role from the ship macro string.
#  Macro format: ship_[faction]_[size]_[role...]_[variant]_macro
#  e.g. ship_tel_m_miner_liquid_01_b_macro → "Miner (Liquid)"
#  Patterns are ordered most-specific first so "miner_solid" matches
#  before the more general "miner".
# ─────────────────────────────────────────────────────────────────────────────

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

SIZE_LABELS = {
    "ship_s":  "S",
    "ship_m":  "M",
    "ship_l":  "L",
    "ship_xl": "XL",
}

# Maps raw XML order names to human-readable labels.
# Any order not in this dict passes through as-is, which acts as a
# safe fallback for orders we haven't seen yet.
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

# Language string pattern: {page,id} — appears in ship names and other fields
# when the game hasn't resolved the string to display text. We treat these as
# unnamed so the code falls back to the ship code instead.
LANG_STRING_RE = re.compile(r'^\{\d+,\d+\}$')


def extract_role(macro: str) -> str:
    """Returns a display role string derived from a ship macro name."""
    for pattern, label in ROLE_PATTERNS:
        if pattern.search(macro):
            return label
    return "Unknown"


def extract_faction_from_macro(macro: str) -> str:
    """
    Extracts the original hull faction from the macro name.
    e.g. ship_xen_m_corvette_02_a_macro → 'Xenon'
    Useful for captured ships where owner != hull origin.
    """
    MACRO_FACTION_MAP = {
        "arg": "Argon",      "tel": "Teladi",
        "par": "Paranid",    "tri": "Paranid",
        "spl": "Split",      "ter": "Terran",
        "bor": "Boron",      "xen": "Xenon",
        "yak": "Yaki",       "pir": "Buccaneer",
        "kha": "Kha'ak",     "buc": "Buccaneer",
    }
    parts = macro.lower().split("_")
    # parts[0] = "ship", parts[1] = faction code
    if len(parts) > 1:
        return MACRO_FACTION_MAP.get(parts[1], parts[1].title())
    return "Unknown"


# ─────────────────────────────────────────────────────────────────────────────
#  CHILD ELEMENT PARSERS
#  Called once a ship element is fully buffered in memory.
# ─────────────────────────────────────────────────────────────────────────────

def _parse_sector_from_zone_macro(ship_elem: ET.Element, sector_names: dict) -> str:
    """
    Resolves the sector name for a ship from its zone macro, which is stamped
    onto the element by the scanner as '_zone_macro' before buffering begins.

    HOW ZONE MACROS ENCODE SECTOR NAMES:
    Zones are nested inside sectors in the XML hierarchy. Their macro names
    directly embed the sector macro, e.g.:
        zone002_cluster_01_sector003_macro
    Stripping the 'zoneNNN_' prefix gives:
        cluster_01_sector003_macro
    We then pass this to macro_to_sector_name() which applies the language
    file ID formula (cluster_num * 10 + sector_suffix) to look up the
    human-readable name from sector_names.

    WHY WE USE macro_to_sector_name() RATHER THAN A DIRECT DICT LOOKUP:
    sector_names is keyed by numeric language IDs like "270011", not by
    macro strings. macro_to_sector_name() already knows how to convert
    "cluster_27_sector001_macro" → "270011" → "The Void", so we reuse
    that existing logic rather than duplicating the arithmetic here or
    building a separate macro-keyed dict.

    WHY WE STAMP THE ZONE MACRO ONTO THE SHIP ELEMENT:
    When streaming with iterparse(), zone start events fire before the ships
    inside them. By saving the current zone macro as a custom '_zone_macro'
    attribute on the ship element at buffer time, we avoid needing a separate
    data structure or a second pass to resolve the sector later.
    """
    from language import macro_to_sector_name

    zone_macro = ship_elem.get('_zone_macro', '')
    if not zone_macro:
        return "Unknown Sector"

    # Strip the zone prefix: zone002_cluster_01_sector003_macro
    #                       →        cluster_01_sector003_macro
    m = re.match(r'zone\d+_(cluster_.+)', zone_macro, re.IGNORECASE)
    if not m:
        # 'tempzone' and other non-standard zones don't encode a sector —
        # these appear for ships docked inside stations or carriers.
        return "Unknown Sector"

    sector_macro = m.group(1)

    # macro_to_sector_name() converts the macro to a language ID and looks
    # it up in sector_names. Returns None if the macro isn't recognised.
    result = macro_to_sector_name(sector_macro, sector_names)
    return result if result else "Unknown Sector"


def _parse_pilot(ship_elem: ET.Element) -> dict:
    """
    Finds the pilot assigned to the aipilot post and returns their name
    and skill ratings.

    WHY TWO-STEP LOOKUP:
    Named crew (with names and component IDs) live inside cockpit connection
    elements. Their skills however are stored in <people><person> entries
    keyed by npcseed. We find the pilot's name and npcseed from their
    cockpit NPC element, then match to the <person> entry to get skills.

    WHY NOT USE <traits>:
    The <traits> element on cockpit NPCs contains role/flag data, not skill
    values. Actual skill numbers live exclusively in <people><person><skills>.
    """
    # Step 1: find the pilot component ID from the control block
    control = ship_elem.find('control')
    pilot_id = None
    if control is not None:
        for post in control.findall('post'):
            if post.get('id') == 'aipilot':
                pilot_id = post.get('component')
                break

    if not pilot_id:
        return {"name": None, "skills": {}}

    # Step 2: find the cockpit NPC with that component ID to get name and npcseed
    pilot_name = None
    pilot_seed = None
    for npc in ship_elem.iter('component'):
        if npc.get('id') == pilot_id and npc.get('class') == 'npc':
            raw_name = npc.get('name')
            if raw_name and not LANG_STRING_RE.match(raw_name):
                pilot_name = raw_name
            seed_elem = npc.find('npcseed')
            if seed_elem is not None:
                pilot_seed = seed_elem.get('seed')
            break

    if not pilot_name:
        return {"name": None, "skills": {}}

    # Step 3: match the npcseed to a <person> entry to get skill values.
    # Skills live in <people><person><skills> — not on the cockpit NPC element.
    skills = {}
    if pilot_seed:
        for person in ship_elem.iter('person'):
            seed_elem = person.find('npcseed')
            if seed_elem is not None and seed_elem.get('seed') == pilot_seed:
                skills_elem = person.find('skills')
                if skills_elem is not None:
                    skills = {
                        "piloting":    int(skills_elem.get('piloting',    0)),
                        "management":  int(skills_elem.get('management',  0)),
                        "morale":      int(skills_elem.get('morale',      0)),
                        "engineering": int(skills_elem.get('engineering', 0)),
                    }
                break

    return {"name": pilot_name, "skills": skills}


def _parse_current_order(ship_elem: ET.Element) -> str:
    """
    Returns a human-readable label for the ship's current order.

    ORDER PRIORITY:
    A ship can have multiple orders queued. We look for a non-default order
    with state="started" and temp != "1" first — this is the active order
    the ship is actually executing. If none exists, we fall back to the
    default standing order (order with default="1"). If neither is found,
    we return "Idle".

    Temporary orders (temp="1") are transient sub-steps like MiningCollect
    within a broader MiningRoutine — we skip these to report the top-level
    intent rather than the momentary action.
    """
    orders_elem = ship_elem.find('orders')
    if orders_elem is None:
        return "Idle"

    default_order = None
    for order in orders_elem.findall('order'):
        raw   = order.get('order', 'Idle')
        label = ORDER_LABELS.get(raw, raw)   # pass through unknown orders as-is

        if order.get('default') == '1':
            default_order = label

        # Active non-temporary order takes priority over the default
        if order.get('state') == 'started' and order.get('temp') != '1':
            return label

    return default_order or "Idle"


def _parse_commander(ship_elem: ET.Element) -> str | None:
    """
    Returns the component ID reference of this ship's commander (station or
    ship), or None if the ship has no commander link.

    Used to reconstruct fleet hierarchy — subordinate ships report to a
    commander whose ID can be matched against station codes or other ships.
    The 'connected connection' value is the commander's connection ID, which
    cross-references to the commander component elsewhere in the XML.
    """
    for conn in ship_elem.findall('connections/connection'):
        if conn.get('connection') == 'commander':
            connected = conn.find('connected')
            if connected is not None:
                return connected.get('connection')
    return None


def _parse_software(ship_elem: ET.Element) -> list[str]:
    """
    Returns a list of software ware IDs installed on the ship.
    Software is stored as a space-separated string in the 'wares' attribute
    of a single <software> element, e.g.:
        <software wares="software_dockmk2 software_trademk1"/>
    """
    sw = ship_elem.find('software')
    if sw is None:
        return []
    wares_str = sw.get('wares', '')
    return [w for w in wares_str.split() if w]


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN SCANNER
# ─────────────────────────────────────────────────────────────────────────────

def scan_ships(
    file_path: pathlib.Path,
    sector_names: dict,
    station_sectors: set[str] | None = None,
    ship_sectors:    set[str] | None = None,
) -> dict:
    """
    Streams through the X4 save and extracts ship data at up to three tiers.

    Parameters
    ----------
    file_path       : path to the save XML
    sector_names    : dict of sector macro → display name (from language.py)
    station_sectors : optional set of sector names where the player has stations.
                      NPC ships in these sectors are included (Tier 2).
    ship_sectors    : optional set of sector names where the player has ships.
                      NPC ships in these sectors are included (Tier 3).
                      Typically a superset of station_sectors.

    Returns
    -------
    {
        "player_ships": [ {...}, ... ],
        "npc_ships":    [ {...}, ... ],   # empty if no context sectors given
    }

    HOW BUFFERING WORKS:
    Same pattern as station scanning in scanner.py. On the 'start' event for
    a qualifying ship element we save a reference and suppress elem.clear()
    for all descendants. On the 'end' event for that same element we parse
    all children (now still in memory) and then clear manually.

    HOW SECTOR RESOLUTION WORKS:
    Ships are nested inside zone elements in the XML. We track the most
    recently opened zone's macro as we stream, and stamp it onto each ship
    element as a custom '_zone_macro' attribute at buffer time. The parser
    later strips the zone prefix to get a sector macro and looks it up
    directly in sector_names.

    WHY WE TRACK DEPTH:
    Ship elements can be nested (e.g. a drone inside a carrier). We only want
    top-level ships, so we track nesting depth and ignore ships encountered
    while already inside another ship element.
    """
    context_sectors = set()
    if station_sectors:
        context_sectors |= station_sectors
    if ship_sectors:
        context_sectors |= ship_sectors

    SHIP_CLASSES = {"ship_s", "ship_m", "ship_l", "ship_xl"}

    player_ships: list[dict] = []
    npc_ships:    list[dict] = []

    # Zone tracking — updated on every zone start/end event so that ships
    # encountered inside that zone can inherit the correct sector macro.
    current_zone_macro = ""

    # Buffering state
    inside_ship        = False
    ship_elem_pending  = None
    ship_owner_pending = None
    ship_depth         = 0   # XML depth counter while a ship is buffered

    print("[Scanning] Ships — player fleet and context NPC ships...")

    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        context = ET.iterparse(f, events=('start', 'end'))

        for event, elem in context:
            tag = elem.tag
            cls = elem.get('class', '')

            # ── ZONE TRACKING ─────────────────────────────────────────────
            # We need to know which zone (and therefore which sector) we are
            # currently inside so we can stamp it on each ship we buffer.
            # We only track this outside of a buffered ship to avoid the
            # inner zone of a station or carrier confusing the sector lookup.
            if not inside_ship:
                if event == 'start' and cls == 'zone':
                    current_zone_macro = elem.get('macro', '')
                elif event == 'end' and cls == 'zone':
                    current_zone_macro = ""

            # ── SHIP START ────────────────────────────────────────────────
            if event == 'start' and cls in SHIP_CLASSES and not inside_ship:
                owner = elem.get('owner', '')

                is_player      = (owner == 'player')
                is_context_npc = (owner != 'player' and bool(context_sectors))

                if is_player or is_context_npc:
                    # Stamp the current zone macro onto the element so the
                    # parser can resolve the sector name after buffering.
                    elem.set('_zone_macro', current_zone_macro)

                    inside_ship        = True
                    ship_elem_pending  = elem
                    ship_owner_pending = owner
                    ship_depth         = 1
                    continue   # don't clear — we need child elements

            # ── DEPTH TRACKING while buffered ────────────────────────────
            if inside_ship:
                if event == 'start':
                    ship_depth += 1
                elif event == 'end':
                    ship_depth -= 1

                    # ── SHIP END: parse and record ────────────────────────
                    if ship_depth == 0:
                        se    = ship_elem_pending
                        owner = ship_owner_pending
                        macro = se.get('macro', '')
                        code  = se.get('code',  '')
                        cls   = se.get('class', '')

                        sector  = _parse_sector_from_zone_macro(se, sector_names)
                        role    = extract_role(macro)
                        size    = SIZE_LABELS.get(cls, cls)
                        hull    = extract_faction_from_macro(macro)
                        order   = _parse_current_order(se)
                        pilot   = _parse_pilot(se)
                        sw      = _parse_software(se)
                        cmdr    = _parse_commander(se)

                        # Reject unresolved language string names like {20102,1234}
                        raw_name = se.get('name')
                        name = None
                        if raw_name and not LANG_STRING_RE.match(raw_name):
                            name = raw_name

                        entry = {
                            "code":        code,
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
                        }

                        if owner == 'player':
                            player_ships.append(entry)
                        elif sector in context_sectors:
                            # Trim NPC entries — pilot/software not needed
                            # for threat assessment
                            npc_ships.append({
                                "code":        code,
                                "class":       cls,
                                "size":        size,
                                "macro":       macro,
                                "role":        role,
                                "hull_origin": hull,
                                "owner":       owner,
                                "sector":      sector,
                                "order":       order,
                            })

                        # Reset buffering state and clear the element manually
                        inside_ship        = False
                        ship_elem_pending  = None
                        ship_owner_pending = None
                        se.clear()
                        continue   # skip the general clear below

            # ── MEMORY MANAGEMENT ────────────────────────────────────────
            # Clear each element after its closing tag to free RAM.
            # Skipped while buffering a ship so children stay in memory.
            if event == 'end' and not inside_ship:
                elem.clear()

    return {
        "player_ships": player_ships,
        "npc_ships":    npc_ships,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  SUMMARY HELPERS
#  Called by jsonexport.py to produce concise fleet overviews.
# ─────────────────────────────────────────────────────────────────────────────

def summarise_player_fleet(player_ships: list[dict]) -> dict:
    """
    Returns a high-level summary of the player fleet grouped by role,
    useful for both display and the AI export JSON.
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
    Returns NPC ship counts grouped by sector and faction,
    useful for threat and activity assessment.
    """
    from collections import defaultdict, Counter

    by_sector = defaultdict(lambda: defaultdict(int))

    for ship in npc_ships:
        by_sector[ship["sector"]][ship["owner"]] += 1

    return {
        sector: dict(factions)
        for sector, factions in by_sector.items()
    }