import pathlib
import re
import xml.etree.ElementTree as ET
from data.wares import WARE_NAMES
from data.factions import FACTION_NAMES, SKIP_FACTIONS, scale_reputation, reputation_label
from scanner.language import macro_to_sector_name, resolve_sector_from_location, open_save

# ─────────────────────────────────────────────────────────────────────────────
#  STATION CLASS NAMES
#  The XML 'class' attribute values X4 uses for player-built structures.
# ─────────────────────────────────────────────────────────────────────────────

STATION_CLASSES = {"station", "factory", "headquarters", "complex"}

# ─────────────────────────────────────────────────────────────────────────────
#  PRODUCTION MODULE PATTERN
#  Station modules that produce wares use a consistent macro naming convention:
#      prod_gen_WARENAME_macro
#  e.g. prod_gen_energycells_macro, prod_gen_hullparts_macro
#  We use a regular expression to extract the ware name from the middle.
#  re.compile() pre-compiles the pattern once for efficiency — calling it
#  millions of times on a large save file would be slow otherwise.
# ─────────────────────────────────────────────────────────────────────────────

PROD_MACRO_RE = re.compile(r'^prod_(?:\w+?)_(\w+)_macro$', re.IGNORECASE)


def parse_production_from_construction(station_elem: ET.Element) -> str:
    """
    Reads the <construction><sequence> block inside a station element and
    returns a comma-separated string of unique produced ware display names.

    WHY THIS WORKS:
    Every production module in a station has an <entry> element whose 'macro'
    attribute follows the pattern 'prod_gen_WARENAME_macro'. We extract the
    ware name from the middle, look it up in WARE_NAMES for a display name,
    and collect unique values.

    WHY WE DEDUPLICATE:
    The same production module type can appear multiple times (e.g. a station
    might have three energycells modules for higher output). We only want to
    list each ware once. We also skip the <snapshot> block that appears later
    in the XML — it repeats the construction sequence as it was at a previous
    point in time, so we'd get duplicates if we didn't stop at </sequence>.

    HOW findall WORKS HERE:
    elem.findall('.//entry') searches all descendant elements named 'entry',
    regardless of how deeply nested they are. The './/' prefix means
    "anywhere below this element". This handles the fact that <entry> elements
    sit inside <construction><sequence> without us needing to navigate there
    step by step.

    WHY THIS FUNCTION RECEIVES THE WHOLE ELEMENT:
    iterparse() only gives us access to child elements once the closing tag
    has been read (the 'end' event). By the time we see </component> for a
    station, all its children — including <construction><sequence> — are
    already in memory and accessible via findall().
    """
    seen_wares = set()      # tracks which wares we've already added
    production = []         # ordered list for display (first occurrence wins)

    # Navigate to <construction><sequence> explicitly so we don't accidentally
    # read the <snapshot> block, which repeats the sequence at an earlier time.
    construction = station_elem.find('construction')
    if construction is None:
        return ""

    sequence = construction.find('sequence')
    if sequence is None:
        return ""

    # Iterate over every <entry> directly inside <sequence>
    for entry in sequence.findall('entry'):
        macro = entry.get('macro', '')

        # Try to match the production module naming pattern
        m = PROD_MACRO_RE.match(macro)
        if not m:
            continue    # not a production module — skip it

        ware_id = m.group(1).lower()    # extract e.g. "energycells"

        if ware_id in seen_wares:
            continue    # already listed this ware — skip duplicates

        seen_wares.add(ware_id)

        # Look up the human-readable name; fall back to title-cased ID
        display = WARE_NAMES.get(ware_id, ware_id.replace('_', ' ').title())
        production.append(display)

    return ", ".join(production)


# ═════════════════════════════════════════════════════════════════════════════
#  SECTION 3 — PASS 1: PLAYER DATA AND STATIONS
# ═════════════════════════════════════════════════════════════════════════════

def scan_save(file_path: pathlib.Path, sector_names: dict) -> dict:
    """
    Streams through the X4 save XML and extracts player data and stations.

    WHY iterparse():
    The save file is 700MB+. iterparse() reads it as a stream one element at
    a time, keeping RAM usage low. We call elem.clear() on every 'end' event
    to immediately release processed elements from memory.

    HOW SECTOR TRACKING WORKS:
    The universe XML is hierarchical: galaxy > cluster > sector > zone > objects.
    Sector components use the 'macro' attribute (e.g. 'cluster_43_sector001_macro').
    We track the most recently seen sector name as we stream through — when we
    encounter a player station, whatever sector we last saw is its location.
    This works because stations are always nested inside their sector in the XML.

    HOW STATION NAMES ARE BUILT:
    Priority order:
      1. Custom name set by player in-game (the 'name' attribute)
      2. Player HQ detected via macro name
      3. nameindex attribute used as fallback number
      4. Last resort: "Unnamed Station"

    HOW STATION BUFFERING WORKS:
    Normally we call elem.clear() after every 'end' event to free RAM. But to
    read production modules we need a station's child elements, which would
    already be cleared by the time we reach the station's own closing tag.
    Solution: when we spot a player station on 'start', we save a reference to
    it and set inside_station=True, which suppresses elem.clear() for all
    descendants. When the station's closing tag arrives, children are still in
    memory, we parse them, then clear everything and reset the flag.
    """
    data = {
        "player_name":    None,
        "player_credits": None,
        "player_sector":  None,
        "stations":       [],
        "reputation":     [],
    }

    in_player_faction = False   # True while inside <faction id="player">
    current_sector    = "Unknown Sector"  # Updated whenever we enter a sector component

    # ── STATION BUFFERING ──────────────────────────────────────────────────────
    inside_station       = False
    station_elem_pending = None
    station_sector_pending = None

    print(f"[Scanning] Pass 1 — player identity, credits, stations...")

    try:
        with open_save(file_path) as f:
            context = ET.iterparse(f, events=('start', 'end'))

            for event, elem in context:
                tag = elem.tag

                if event == 'start' and tag == 'player':
                    if not data["player_name"]:
                        data["player_name"] = elem.get('name')
                        loc = elem.get('location', '')
                        if loc:
                            data["player_sector"] = resolve_sector_from_location(
                                loc, sector_names
                            )

                if event == 'start' and tag == 'faction' and elem.get('id') == 'player':
                    in_player_faction = True

                if in_player_faction and event == 'start' and tag == 'account':
                    if not data["player_credits"]:
                        data["player_credits"] = (
                            elem.get('amount') or elem.get('balance')
                        )

                if event == 'end' and tag == 'faction' and elem.get('id') == 'player':
                    in_player_faction = False

                if event == 'start' and tag == 'component':
                    comp_class = elem.get('class', '')
                    if comp_class == 'sector':
                        macro = elem.get('macro', '')
                        resolved = macro_to_sector_name(macro, sector_names)
                        if resolved:
                            current_sector = resolved

                    if (elem.get('owner') == 'player' and
                            comp_class in STATION_CLASSES and
                            not inside_station):
                        inside_station         = True
                        station_elem_pending   = elem
                        station_sector_pending = current_sector

                if event == 'end' and tag == 'component' and inside_station:
                    if elem is station_elem_pending:
                        macro     = elem.get('macro', '')
                        code      = elem.get('code', '')
                        name_attr = elem.get('name')
                        nameindex = elem.get('nameindex', '')

                        if name_attr:
                            display_name = name_attr
                        elif 'headquarters' in macro.lower():
                            display_name = "Player HQ"
                        elif nameindex:
                            display_name = f"Station #{nameindex}"
                        else:
                            display_name = "Unnamed Station"

                        production = parse_production_from_construction(elem)

                        entry = {
                            "name":       display_name,
                            "code":       code,
                            "class":      elem.get('class', ''),
                            "macro":      macro,
                            "sector":     station_sector_pending,
                            "production": production,
                        }

                        if not any(s["code"] == code for s in data["stations"]):
                            data["stations"].append(entry)

                        inside_station         = False
                        station_elem_pending   = None
                        station_sector_pending = None
                        elem.clear()
                        continue

                if event == 'end' and not inside_station:
                    elem.clear()

    except ET.ParseError as e:
        print(f"\n[XML Error] Save file has a formatting issue: {e}")
        raise
    except Exception as e:
        print(f"\n[Error] Unexpected problem: {e}")
        raise

    return data


# ═════════════════════════════════════════════════════════════════════════════
#  SECTION 4 — PASS 2: FACTION REPUTATION
# ═════════════════════════════════════════════════════════════════════════════

def scan_reputation(file_path: pathlib.Path) -> list:
    """
    Second pass to extract faction reputation from the player's faction block.

    WHY A SECOND PASS:
    iterparse() can't easily track parent context during complex nested scanning.
    A dedicated pass for reputation is cleaner and more reliable.

    HOW REPUTATION IS STORED:
    The player's standings are in <faction id="player"><relations>:
        <relation faction="argon" relation="0.0032"/>
        <booster faction="argon" relation="0.2562" time="326867.385"/>

    Base 'relation' is the permanent standing. 'booster' entries are temporary
    bonuses from missions that decay over time. We report base and booster
    separately so you can see what's permanent vs temporary.
    """
    in_player_fac  = False
    in_relations   = False
    base_relations = {}
    boosters       = {}

    print(f"[Scanning] Pass 2 — faction reputation...")

    with open_save(file_path) as f:
        context = ET.iterparse(f, events=('start', 'end'))

        for event, elem in context:
            tag = elem.tag

            if event == 'start' and tag == 'faction' and elem.get('id') == 'player':
                in_player_fac = True

            if in_player_fac:
                if event == 'start' and tag == 'relations':
                    in_relations = True

                if in_relations and event == 'start' and tag == 'relation':
                    fid = elem.get('faction')
                    try:
                        base_relations[fid] = float(elem.get('relation', '0'))
                    except ValueError:
                        base_relations[fid] = 0.0

                if in_relations and event == 'start' and tag == 'booster':
                    fid = elem.get('faction')
                    try:
                        boosters[fid] = float(elem.get('relation', '0'))
                    except ValueError:
                        boosters[fid] = 0.0

                if event == 'end' and tag == 'relations':
                    in_relations = False

                if event == 'end' and tag == 'faction' and elem.get('id') == 'player':
                    in_player_fac = False
                    break

            if event == 'end':
                elem.clear()

    all_factions = set(base_relations.keys()) | set(boosters.keys())
    reputation   = []

    for fid in all_factions:
        if fid in SKIP_FACTIONS:
            continue

        raw_base    = base_relations.get(fid, 0.0)
        raw_booster = boosters.get(fid, 0.0)

        raw_total    = raw_base + raw_booster
        scaled_total   = scale_reputation(raw_total)
        scaled_base    = scale_reputation(raw_base)    if raw_base    != 0 else 0.0
        scaled_booster = scale_reputation(raw_booster) if raw_booster != 0 else 0.0

        faction_name = FACTION_NAMES.get(fid, fid.title())

        reputation.append({
            "faction_id":   fid,
            "faction_name": faction_name,
            "value":        round(scaled_total,   2),
            "base":         round(scaled_base,    2),
            "booster":      round(scaled_booster, 2),
            "tier":         reputation_label(scaled_total),
        })

    reputation.sort(key=lambda x: x["value"], reverse=True)
    return reputation
