# ─────────────────────────────────────────────────────────────────────────────
#  SHIPS
#  Extracts player ships (always) and optionally NPC ships in sectors of
#  interest (where the player has stations or ships).
#
#  Three scan tiers, controlled by the caller:
#    Tier 1 — Player ships only               scan_ships(file, sector_names)
#    Tier 2 — + NPC ships in station sectors  scan_ships(..., station_sectors={...})
#    Tier 3 — + NPC ships in all ship sectors scan_ships(..., ship_sectors={...})
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

# Matches language reference strings like "{20101,22603}" that appear in some
# name attributes in the save file. These are placeholders the game resolves
# at runtime — we can't use them as display names, so we skip them.
LANG_STRING_RE = re.compile(r'^\{\d+,\d+\}$')


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
    MACRO_FACTION_MAP = {
        "arg": "Argon",      "tel": "Teladi",
        "par": "Paranid",    "tri": "Paranid",
        "spl": "Split",      "ter": "Terran",
        "bor": "Boron",      "xen": "Xenon",
        "yak": "Yaki",       "pir": "Buccaneer",
        "kha": "Kha'ak",     "buc": "Buccaneer",
        "atf": "Terran",     "pio": "Pioneer",
    }
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

def _parse_sector(ship_elem: ET.Element, sector_names: dict) -> str:
    """
    Resolves the sector name for a ship.

    Two sources are tried in priority order:

    1. '_sector_macro' — the macro of the enclosing sector element, stamped
       directly onto the ship before buffering. This handles ships inside
       dynamic 'tempzone' elements, which are unnamed zones X4 creates at
       runtime and don't encode the sector in their macro string.

    2. '_zone_macro' — the enclosing zone's macro, which follows the pattern
       zone{N}_{sector_macro} and lets us extract the sector by stripping the
       prefix. Used as a fallback for ships whose parent zone is a named zone.
    """
    # Priority 1: resolve from the parent sector macro directly.
    sector_macro = ship_elem.get('_sector_macro', '')
    if sector_macro:
        result = macro_to_sector_name(sector_macro, sector_names)
        if result:
            return result

    # Priority 2: fall back to extracting sector from the zone macro.
    zone_macro = ship_elem.get('_zone_macro', '')
    m = re.match(r'zone\d+_(cluster_.+)', zone_macro, re.IGNORECASE)
    if m:
        result = macro_to_sector_name(m.group(1), sector_names)
        if result:
            return result

    return "Unknown Sector"


def _parse_pilot(ship_elem: ET.Element) -> dict:
    """
    Finds the pilot assigned to the 'aipilot' control post and returns their
    name and skill ratings.

    HOW CREW IS STORED IN THE SAVE FILE:
    Every ship has a <control> block listing which NPC fills each crew role.
    Each role is a <post> element with an 'id' (the role name) and a
    'component' attribute (the ID of the NPC filling that role). Example:

        <control>
            <post id="aipilot"  component="[0x348]"/>
            <post id="engineer" component="[0x34a]"/>
        </control>

    The actual NPC data — name, skills — lives elsewhere in the ship's XML
    as a <component class="npc"> element whose 'id' matches the reference
    above. Skills are nested inside that component under <traits><skills>:

        <component class="npc" id="[0x348]" name="Mikela Dalina">
            <traits>
                <skills piloting="5" morale="7" boarding="3"/>
            </traits>
        </component>

    NOTE: There is also a <people> block on some ships that stores marines
    and cargo-hold crew using a different structure. Don't confuse the two —
    pilots are always found via the <control><post> route above.

    Returns a dict with keys:
        'name'   (str | None)  — the pilot's display name, or None if not found
        'skills' (dict)        — skill name → int value for any skills present,
                                 e.g. {"piloting": 5, "morale": 7, "boarding": 3}
                                 Only skills X4 actually wrote are included —
                                 a missing key means 0, not unknown.
    """
    # ── Step 1: find the pilot's component ID ─────────────────────────────────
    # We read the <control> block and look for the post whose id is 'aipilot'.
    # The 'component' attribute on that post tells us which NPC element to look
    # up next — it's like a reference/pointer to another part of the XML.
    control = ship_elem.find('control')
    pilot_id = None
    if control is not None:
        for post in control.findall('post'):
            if post.get('id') == 'aipilot':
                pilot_id = post.get('component')
                break

    # If no aipilot post exists (unmanned ship, station drone, etc.) stop here.
    if not pilot_id:
        return {"name": None, "skills": {}}

    # ── Step 2: find the NPC component and read name + skills ─────────────────
    # We search every <component> element inside the ship for one whose 'id'
    # matches the reference we just found. iter() searches all descendants,
    # no matter how deeply nested they are.
    for npc in ship_elem.iter('component'):
        if npc.get('id') != pilot_id or npc.get('class') != 'npc':
            continue  # wrong element — keep searching

        # The pilot's name is an attribute on the component element itself.
        # Some names in the save are language reference tokens like "{20101,22603}"
        # instead of real text — LANG_STRING_RE detects those so we can skip them.
        raw_name = npc.get('name')
        if not raw_name or LANG_STRING_RE.match(raw_name):
            return {"name": None, "skills": {}}

        # Skills live under <traits><skills> inside the NPC component.
        # We only include skills that X4 actually wrote to the file — a missing
        # attribute means 0 stars, so we let the caller treat absent keys as 0
        # rather than storing redundant zeros for every possible skill.
        skills = {}
        traits = npc.find('traits')
        if traits is not None:
            skills_elem = traits.find('skills')
            if skills_elem is not None:
                for attr in ('piloting', 'management', 'morale', 'engineering', 'boarding'):
                    val = skills_elem.get(attr)
                    if val is not None:
                        skills[attr] = int(val)

        return {"name": raw_name, "skills": skills}

    # If we exhausted the whole ship subtree without finding the component,
    # the save file reference is dangling — return empty rather than crashing.
    return {"name": None, "skills": {}}


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
    SHIP_CLASSES = {"ship_s", "ship_m", "ship_l", "ship_xl"}
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
        hull_hp     = _parse_hull(child)
        max_hull    = SHIP_STATS.get(macro, {}).get("max_hull")

        if hull_hp is None:
            hull_pct = 100.0
        elif max_hull:
            hull_pct = (hull_hp / max_hull) * 100.0
        else:
            hull_pct = None

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
        })

    return docked


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
    Streams through the X4 save and extracts ship data.

    Uses iterparse() to process the XML one element at a time, which keeps
    RAM usage low even on 700MB+ save files. The file is never fully loaded
    into memory.

    PLAYER SHIPS are always collected. NPC ships are only collected for
    sectors in 'context_sectors', which is built from station_sectors and/or
    ship_sectors depending on the scan tier chosen by the caller.

    BUFFERING: When a ship element's opening tag is detected, elem.clear()
    is suppressed for all of its descendants until the closing tag arrives.
    This keeps the ship's child elements (crew, orders, software, etc.) in
    memory so the _parse_* functions can read them. Once parsing is done the
    element is cleared manually.

    ZONE TRACKING: Ships are nested under zone elements in the XML, not
    directly under sectors. The current zone macro is tracked as a running
    variable and stamped onto each ship element before buffering starts, so
    _parse_sector_from_zone_macro() can resolve the sector later.

    Parameters:
        file_path       — path to the unzipped X4 save file
        sector_names    — dict from load_sector_names(), maps lang IDs to names
        station_sectors — set of sector names where the player has stations
                          (used for tier 2 NPC collection)
        ship_sectors    — set of sector names where the player has ships
                          (used for tier 3 NPC collection, adds to station_sectors)

    Returns a dict with keys:
        'player_ships' — list of ship dicts for all player-owned ships
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

    SHIP_CLASSES = {"ship_s", "ship_m", "ship_l", "ship_xl"}

    player_ships: list[dict] = []
    npc_ships:    list[dict] = []

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

                is_player      = (owner == 'player')
                # Collect NPC ships only when we have context sectors to filter by.
                is_context_npc = (owner != 'player' and bool(context_sectors))

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
                        sector = _parse_sector(se, sector_names)
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

                            player_ships.append({
                                "code":        code,
                                "name":        name,
                                "class":       cls,
                                "size":        size,
                                "macro":       macro,
                                "role":        role,
                                "hull_origin": hull,      # faction that manufactured the hull, e.g. "Argon"
                                "owner":       owner,
                                "sector":      sector,
                                "order":       order,
                                "pilot":       pilot,
                                "software":    sw,
                                "commander":   cmdr,
                                "hull_hp":     hull_hp,   # current HP as a raw float, or None if undamaged
                                "hull_pct":    hull_pct,  # 0–100 float, or None if max hull is unknown
                                "max_hull":    max_hull,  # base max HP from the ship's macro, or None
                            })
                            # Also extract any ships docked inside this one.
                            # Carriers hold fighter wings internally — those ships
                            # are invisible to the main iterparse loop because the
                            # inside_ship flag blocks their detection, so we pull
                            # them from the buffered subtree separately.
                            player_ships.extend(
                                _extract_docked_ships(se, sector, owner)
                            )

                        elif sector in context_sectors:
                            # ── NPC ship entry (slim) ──────────────────────
                            # We only need enough data to show faction activity
                            # in the UI — who is where and doing what. Crew and
                            # hull health are omitted because we don't own these
                            # ships and the extra parsing wouldn't be used.
                            npc_ships.append({
                                "code":        code,
                                "name":        name,
                                "class":       cls,
                                "size":        size,
                                "macro":       macro,
                                "role":        role,
                                "hull_origin": hull,      # faction that manufactured the hull
                                "owner":       owner,
                                "sector":      sector,
                                "order":       order,
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
    }


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