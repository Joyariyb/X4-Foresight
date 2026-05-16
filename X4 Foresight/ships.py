# ─────────────────────────────────────────────────────────────────────────────
#  SHIPS
#  Extracts player ships (always) and optionally NPC ships in sectors of
#  interest (where the player has stations or ships).
#
#  Three scan tiers, controlled by the caller:
#    Tier 1 — Player ships only              scan_ships(file, sector_names)
#    Tier 2 — + NPC ships in station sectors scan_ships(file, sector_names, station_sectors={"The Void", ...})
#    Tier 3 — + NPC ships in all ship sectors scan_ships(file, sector_names, station_sectors=..., ship_sectors=...)
# ─────────────────────────────────────────────────────────────────────────────

import re
import pathlib
import xml.etree.ElementTree as ET
from language import resolve_sector_from_location

# ─────────────────────────────────────────────────────────────────────────────
#  ROLE EXTRACTION
#  Derives a human-readable role from the ship macro string.
#  Macro format: ship_[faction]_[size]_[role...]_[variant]_macro
#  e.g. ship_tel_m_miner_liquid_01_b_macro → "Miner (Liquid)"
# ─────────────────────────────────────────────────────────────────────────────

# Ordered from most specific to least, so "miner_solid" matches before "miner"
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

ORDER_LABELS = {
    "MiningRoutine":   "Mining",
    "Middleman":       "Trading",
    "Patrol":          "Patrolling",
    "Escort":          "Escorting",
    "KeepFormation":   "In Formation",
    "Dock":            "Docking",
    "Wait":            "Waiting",
    "Flee":            "Fleeing",
    "Attack":          "Attacking",
    "Collect":         "Collecting",
    "MiningCollect":   "Mining (Collecting)",
    "TerraformMonitor":"Monitoring",
    "Repair":          "Repairing",
    "Build":           "Building",
    "Supply":          "Supplying",
    "Trade":           "Trading",
    "Police":          "Policing",
}


def extract_role(macro: str) -> str:
    """Returns a display role string derived from a ship macro name."""
    for pattern, label in ROLE_PATTERNS:
        if pattern.search(macro):
            return label
    return "Unknown"


def extract_faction_from_macro(macro: str) -> str:
    """
    Extracts the original hull faction from the macro name.
    e.g. ship_xen_m_corvette_02_a_macro → 'xenon' (mapped from 'xen')
    Useful for captured ships where owner != hull origin.
    """
    MACRO_FACTION_MAP = {
        "arg": "Argon",   "ant": "Argon",    "tel": "Teladi",
        "par": "Paranid", "tri": "Paranid",  "spl": "Split",
        "ter": "Terran",  "bor": "Boron",    "xen": "Xenon",
        "yak": "Yaki",    "pir": "Buccaneer","kha": "Kha'ak",
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

def _parse_sector_from_movement(ship_elem: ET.Element, sector_names: dict) -> str:
    """
    Reads the space reference from <movement><position><read space="[0x...]">
    and resolves it to a sector name via sector_names.
    Falls back to "Unknown Sector".
    """
    movement = ship_elem.find('movement')
    if movement is None:
        return "Unknown Sector"
    position = movement.find('position')
    if position is None:
        return "Unknown Sector"
    read_elem = position.find('read')
    if read_elem is None:
        return "Unknown Sector"
    space_ref = read_elem.get('space', '')
    return resolve_sector_from_location(space_ref, sector_names)


def _parse_pilot(ship_elem: ET.Element) -> dict:
    """
    Finds the NPC with post="aipilot" in the ship's control block and
    returns their name and skill ratings.
    """
    # Find <control><post id="aipilot" component="[0x...]"/> to get the pilot ID
    control = ship_elem.find('control')
    pilot_component_id = None
    if control is not None:
        for post in control.findall('post'):
            if post.get('id') == 'aipilot':
                pilot_component_id = post.get('component')
                break

    if not pilot_component_id:
        return {"name": None, "skills": {}}

    # Search all descendant NPCs for one whose id matches
    for npc in ship_elem.iter('component'):
        if npc.get('id') == pilot_component_id and npc.get('class') == 'npc':
            name = npc.get('name')
            traits = npc.find('traits')
            skills = {}
            if traits is not None:
                skills = {
                    "piloting":    int(traits.get('piloting',    0)),
                    "management":  int(traits.get('management',  0)),
                    "morale":      int(traits.get('morale',      0)),
                    "engineering": int(traits.get('engineering', 0)),
                }
            return {"name": name, "skills": skills}

    return {"name": None, "skills": {}}


def _parse_current_order(ship_elem: ET.Element) -> str:
    """
    Returns a human-readable label for the ship's active (non-default) order,
    or the default order if no active one exists.
    Falls back to the raw order name if not in ORDER_LABELS.
    """
    orders_elem = ship_elem.find('orders')
    if orders_elem is None:
        return "Idle"

    default_order = None
    for order in orders_elem.findall('order'):
        raw = order.get('order', 'Idle')
        label = ORDER_LABELS.get(raw, raw)
        if order.get('default') == '1':
            default_order = label
        if order.get('state') == 'started' and order.get('temp') != '1':
            return label        # active non-default order takes priority

    return default_order or "Idle"


def _parse_commander(ship_elem: ET.Element) -> str | None:
    """
    Returns the component ID of this ship's commander (station or ship),
    or None if the ship has no commander link.
    Used to reconstruct fleet hierarchy.
    """
    for conn in ship_elem.findall('connections/connection'):
        if conn.get('connection') == 'commander':
            connected = conn.find('connected')
            if connected is not None:
                return connected.get('connection')   # the commander's ID ref
    return None


def _parse_software(ship_elem: ET.Element) -> list[str]:
    """Returns a list of software ware IDs installed on the ship."""
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
    ship_sectors: set[str] | None = None,
) -> dict:
    """
    Streams through the X4 save and extracts ship data at up to three tiers.

    Parameters
    ----------
    file_path       : path to the save XML
    sector_names    : dict of zone/sector ID → display name (from language.py)
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

    # Buffering state
    inside_ship       = False
    ship_elem_pending = None
    ship_owner_pending = None
    ship_depth        = 0   # tracks XML depth while buffered

    print("[Scanning] Ships — player fleet and context NPC ships...")

    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        context = ET.iterparse(f, events=('start', 'end'))

        for event, elem in context:
            tag  = elem.tag
            cls  = elem.get('class', '')

            # ── SHIP START ────────────────────────────────────────────────
            if event == 'start' and cls in SHIP_CLASSES and not inside_ship:
                owner = elem.get('owner', '')
                macro = elem.get('macro', '')

                # Decide whether this ship is worth buffering
                is_player = (owner == 'player')
                is_context_npc = (
                    owner != 'player'
                    and bool(context_sectors)
                    # We can't know the sector yet (need movement child),
                    # so we buffer all NPC ships in context mode and filter
                    # after parsing. Skip if clearly irrelevant factions.
                )

                if is_player or is_context_npc:
                    inside_ship        = True
                    ship_elem_pending  = elem
                    ship_owner_pending = owner
                    ship_depth         = 1
                continue   # don't clear — we're buffering

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

                        sector  = _parse_sector_from_movement(se, sector_names)
                        role    = extract_role(macro)
                        size    = SIZE_LABELS.get(cls, cls)
                        hull    = extract_faction_from_macro(macro)
                        order   = _parse_current_order(se)
                        pilot   = _parse_pilot(se)
                        sw      = _parse_software(se)
                        cmdr    = _parse_commander(se)
                        name    = se.get('name')    # only if player named it

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
                            # Trim NPC entry — we don't need pilot/software
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

                        # Reset buffering
                        inside_ship        = False
                        ship_elem_pending  = None
                        ship_owner_pending = None
                        se.clear()
                        continue   # skip general clear below

            # ── MEMORY MANAGEMENT ────────────────────────────────────────
            if event == 'end' and not inside_ship:
                elem.clear()

    return {
        "player_ships": player_ships,
        "npc_ships":    npc_ships,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  SUMMARY HELPERS
#  Called by the display/export layer to produce concise output.
# ─────────────────────────────────────────────────────────────────────────────

def summarise_player_fleet(player_ships: list[dict]) -> dict:
    """
    Returns a high-level summary of the player fleet grouped by role,
    useful for both display and the AI export JSON.
    """
    from collections import Counter, defaultdict

    by_role    = Counter()
    by_sector  = defaultdict(list)
    by_order   = Counter()

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
    useful for threat/activity assessment.
    """
    from collections import defaultdict, Counter

    by_sector = defaultdict(lambda: defaultdict(int))

    for ship in npc_ships:
        by_sector[ship["sector"]][ship["owner"]] += 1

    return {
        sector: dict(factions)
        for sector, factions in by_sector.items()
    }