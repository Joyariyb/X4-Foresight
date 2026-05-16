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
from scanner.language import macro_to_sector_name

# ─────────────────────────────────────────────────────────────────────────────
#  ROLE EXTRACTION
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
    if len(parts) > 1:
        return MACRO_FACTION_MAP.get(parts[1], parts[1].title())
    return "Unknown"


# ─────────────────────────────────────────────────────────────────────────────
#  CHILD ELEMENT PARSERS
# ─────────────────────────────────────────────────────────────────────────────

def _parse_sector_from_zone_macro(ship_elem: ET.Element, sector_names: dict) -> str:
    """
    Resolves the sector name for a ship from its zone macro, which is stamped
    onto the element by the scanner as '_zone_macro' before buffering begins.
    """
    zone_macro = ship_elem.get('_zone_macro', '')
    if not zone_macro:
        return "Unknown Sector"

    m = re.match(r'zone\d+_(cluster_.+)', zone_macro, re.IGNORECASE)
    if not m:
        return "Unknown Sector"

    sector_macro = m.group(1)
    result = macro_to_sector_name(sector_macro, sector_names)
    return result if result else "Unknown Sector"


def _parse_pilot(ship_elem: ET.Element) -> dict:
    """
    Finds the pilot assigned to the aipilot post and returns their name
    and skill ratings.
    """
    control = ship_elem.find('control')
    pilot_id = None
    if control is not None:
        for post in control.findall('post'):
            if post.get('id') == 'aipilot':
                pilot_id = post.get('component')
                break

    if not pilot_id:
        return {"name": None, "skills": {}}

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
    """
    orders_elem = ship_elem.find('orders')
    if orders_elem is None:
        return "Idle"

    default_order = None
    for order in orders_elem.findall('order'):
        raw   = order.get('order', 'Idle')
        label = ORDER_LABELS.get(raw, raw)

        if order.get('default') == '1':
            default_order = label

        if order.get('state') == 'started' and order.get('temp') != '1':
            return label

    return default_order or "Idle"


def _parse_commander(ship_elem: ET.Element) -> str | None:
    """
    Returns the component ID reference of this ship's commander, or None.
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
    """
    context_sectors = set()
    if station_sectors:
        context_sectors |= station_sectors
    if ship_sectors:
        context_sectors |= ship_sectors

    SHIP_CLASSES = {"ship_s", "ship_m", "ship_l", "ship_xl"}

    player_ships: list[dict] = []
    npc_ships:    list[dict] = []

    current_zone_macro = ""

    inside_ship        = False
    ship_elem_pending  = None
    ship_owner_pending = None
    ship_depth         = 0

    print("[Scanning] Ships — player fleet and context NPC ships...")

    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        context = ET.iterparse(f, events=('start', 'end'))

        for event, elem in context:
            tag = elem.tag
            cls = elem.get('class', '')

            if not inside_ship:
                if event == 'start' and cls == 'zone':
                    current_zone_macro = elem.get('macro', '')
                elif event == 'end' and cls == 'zone':
                    current_zone_macro = ""

            if event == 'start' and cls in SHIP_CLASSES and not inside_ship:
                owner = elem.get('owner', '')

                is_player      = (owner == 'player')
                is_context_npc = (owner != 'player' and bool(context_sectors))

                if is_player or is_context_npc:
                    elem.set('_zone_macro', current_zone_macro)

                    inside_ship        = True
                    ship_elem_pending  = elem
                    ship_owner_pending = owner
                    ship_depth         = 1
                    continue

            if inside_ship:
                if event == 'start':
                    ship_depth += 1
                elif event == 'end':
                    ship_depth -= 1

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

                        inside_ship        = False
                        ship_elem_pending  = None
                        ship_owner_pending = None
                        se.clear()
                        continue

            if event == 'end' and not inside_ship:
                elem.clear()

    return {
        "player_ships": player_ships,
        "npc_ships":    npc_ships,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  SUMMARY HELPERS
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
