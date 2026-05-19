# scanner/scanner_revised.py
import pathlib
import re
from lxml import etree as ET
from data.wares import WARE_NAMES
from data.factions import FACTION_NAMES, SKIP_FACTIONS, scale_reputation, reputation_label
from scanner.language import macro_to_sector_name, resolve_sector_from_location, open_save

# ─────────────────────────────────────────────────────────────────────────────
#  MODULE OVERVIEW
#  This module provides low-level XML parsing utilities for X4 save files.
#  It extracts:
#    - Player identity (name, credits, sector)
#    - Owned stations (names, codes, production, managers)
#    - Faction reputation (base standings + temporary boosters)
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
#  STATION CLASS NAMES
#  The XML 'class' attribute values X4 uses for player-built structures.
# ─────────────────────────────────────────────────────────────────────────────

LANG_STRING_RE = re.compile(r'^\{\d+,\d+\}$')

STATION_CLASSES = {"station", "factory", "headquarters", "complex"}

# ─────────────────────────────────────────────────────────────────────────────
#  PRODUCTION MODULE PATTERN
#  Station production modules use the naming convention:
#      prod_{prefix}_WARENAME_macro
#  (e.g., prod_gen_energycells_macro)
#  
#  The regular expression pre-compiles for performance—calling re.compile() 
#  repeatedly inside a loop processing large save files would be inefficient.
# ─────────────────────────────────────────────────────────────────────────────

PROD_MACRO_RE = re.compile(r'^prod_(?:\w+?)_(\w+)_macro$', re.IGNORECASE)


def parse_production_from_construction(station_elem: ET.Element) -> str:
    """
    Extracts unique production outputs from a station's <construction><sequence> block.
    
    DISPLAY FORMAT:
      Returns a comma-separated string of ware display names (e.g., "Energy Cells, Hull Parts")
      
    WHY THIS WORKS:
      - Each production module has an <entry> element with a 'macro' attribute following the pattern 'prod_gen_WARENAME_macro'.
      - We extract the ware name from the middle, look it up in WARE_NAMES for its display name.
      - Duplicates are removed because multiple modules of the same type may exist (e.g., three energy cells).
    
    WHY WE IGNORE <snapshot>:
      The XML contains a later <construction><snapshot> block that repeats the sequence from an earlier time point. 
      We must stop parsing at </sequence> to avoid including stale duplicate entries.
      
    HOW FINDALL WORKS:
      elem.findall('.//entry') searches all descendant <entry> elements regardless of nesting depth, 
      which is necessary because <entry> can appear multiple levels deep.
      
    RETURNS:
        A comma-separated string of unique ware display names, or an empty string if no production modules are found.
    """
    seen_wares = set()      # Tracks wares we've already added to avoid duplicates
    production = []         # Ordered list for display (first occurrence wins)

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
            continue    # Not a production module — skip it

        ware_id = m.group(1).lower()    # Extract e.g. "energycells"

        if ware_id in seen_wares:
            continue    # Already listed this ware — skip duplicates

        seen_wares.add(ware_id)

        # Look up the human-readable name; fall back to title-cased ID
        display = WARE_NAMES.get(ware_id, ware_id.replace('_', ' ').title())
        production.append(display)

    return ", ".join(production)


def _parse_manager(station_elem: ET.Element) -> dict | None:
    """
    Finds and returns information about a station's assigned manager.
    
    HOW MANAGERS ARE STORED:
      Managers are stored similarly to ship pilots — via a <control><post> element with id="manager" 
      that references the manager's NPC component by ID. That NPC holds the name and <traits><skills> block.
      
    RETURNS:
        A dictionary with {"name": str, "skills": dict} if a valid manager is found; 
        None if no manager exists or the slot is empty.
        
    SPECIAL CASES:
      - Returns None for newly built stations where the manager slot is still vacant.
      - Returns None if the name attribute contains unresolved placeholders (e.g., "{12345,67890}").
    """
    control = station_elem.find('control')
    if control is None:
        return None

    # Find the manager post and grab the component ID reference.
    manager_id = None
    for post in control.findall('post'):
        if post.get('id') == 'manager':
            manager_id = post.get('component')
            break

    if not manager_id:
        return None

    # Walk the station's subtree to find the NPC component with that ID.
    for npc in station_elem.iter('component'):
        if npc.get('id') != manager_id or npc.get('class') != 'npc':
            continue

        raw_name = npc.get('name')
        if not raw_name or LANG_STRING_RE.match(raw_name):
            return None

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

    return None


def _parse_station_health(station_elem: ET.Element) -> dict:
    """
    Extracts hull and shield HP from a fully-buffered station element.

    Hull follows the same convention as ships: X4 only writes <hull value="..."/>
    when the station has taken damage. A missing element means full health.

    Shields are more complex than ships — a station can have zero or many
    individual shield generator modules, each stored as a child <component>
    whose class attribute starts with "shieldgenerator". Each generator has
    its own <shield value="..."/> recording current HP. We aggregate across
    all generators to produce a single total current-shield figure.

    Without a station_stats max-HP table, we can't compute percentages yet.
    Callers should treat None hull_hp as undamaged and shield_hp as a raw
    aggregate until max values are available.

    Returns a dict with:
        hull_hp   — current hull HP as float, or None if undamaged
        shield_hp — total current shield HP across all generators, or None if
                    no generators are present / all are at full health
    """
    # Hull — absent element means full health, same pattern as ships.
    hull_hp = None
    hull_elem = station_elem.find('hull')
    if hull_elem is not None:
        try:
            hull_hp = float(hull_elem.get('value', 0))
        except (ValueError, TypeError):
            pass

    # Shields — sum current HP across every shield generator module.
    # X4 only writes the <shield> child when the generator is damaged, so
    # generators whose element is absent are implicitly at full capacity.
    # We can't compute a total-shield percentage without knowing max HP per
    # generator type, so we store the raw aggregate for now.
    shield_total = 0.0
    has_generators = False
    for comp in station_elem.iter('component'):
        if comp is station_elem:
            continue
        if not comp.get('class', '').startswith('shieldgenerator'):
            continue
        has_generators = True
        shield_elem = comp.find('shield')
        if shield_elem is not None:
            try:
                shield_total += float(shield_elem.get('value', 0))
            except (ValueError, TypeError):
                pass

    shield_hp = shield_total if has_generators else None

    return {"hull_hp": hull_hp, "shield_hp": shield_hp}


# ═════════════════════════════════════════════════════════════════════════════
#  SECTION 3 — PASS 1: PLAYER DATA AND STATIONS
# ═════════════════════════════════════════════════════════════════════════════

def scan_save(file_path: pathlib.Path, sector_names: dict) -> dict:
    """
    First pass: Extracts player identity, credits, sector location, and all owned stations.
    
    STREAMING STRATEGY:
      The save file is 700MB+. We use iterparse() to stream it element-by-element 
      with low RAM usage. After processing each closing tag ('end' event), we call 
      elem.clear() to release memory immediately.
      
    SECTOR TRACKING:
      The universe XML is hierarchical: galaxy > cluster > sector > zone > objects.
      Sector components use a 'macro' attribute (e.g., "cluster_43_sector001_macro").
      As we stream through, we track the most recently seen sector name. When we 
      encounter a player station, whatever sector was last active is its location.
      
    STATION NAME PRIORITY:
      1. Custom in-game name ('name' attribute)
      2. "Player HQ" (if macro contains "headquarters")
      3. "Station #N" (using 'nameindex' fallback)
      4. "Unnamed Station" (last resort)
      
    STATION BUFFERING:
      Normally we clear elements after each 'end' event to free RAM. However, reading 
      production modules requires access to the station's child elements. To solve this, 
      when we detect a player station on 'start', we save a reference and set inside_station=True, 
      which temporarily suppresses clearing until parsing is complete.
      
    RETURNS:
        Dictionary with keys: player_name, player_credits, player_sector, stations (list), managers (list)
    """
    data = {
        "player_name":    None,
        "player_credits": None,
        "player_sector":  None,
        "stations":       [],
        "reputation":     [],
        "managers":       [],   # Crew entries for station managers
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

                            # Extract station manager as a crew entry.
                            mgr = _parse_manager(elem)
                            if mgr:
                                data["managers"].append({
                                    "name":          mgr["name"],
                                    "role":          "manager",
                                    "skills":        mgr["skills"],
                                    "assigned_to":   display_name,
                                    "assigned_code": code,
                                    "assigned_type": "station",
                                    "sector":        station_sector_pending,
                                })

                        inside_station         = False
                        station_elem_pending   = None
                        station_sector_pending = None
                        elem.clear()
                        continue

                if event == 'end' and not inside_station:
                    elem.clear()

    except ET.XMLSyntaxError as e:
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
    Second pass: Extracts faction reputation (base standing + temporary boosters).
    
    WHY A SEPARATE PASS:
      Although reputation data lives in the same <faction id="player"> block as player info, 
      parsing it alongside station extraction would complicate the logic. A dedicated pass is 
      cleaner and more maintainable.
      
    DATA STRUCTURE:
      Player standings are stored in <faction id="player"><relations>:
        <relation faction="argon" relation="0.0032"/>
        <booster faction="argon" relation="0.2562" time="326867.385"/>
      
      - Base 'relation' = permanent standing
      - Booster entries = temporary bonuses from missions that decay over time
      
    RETURNS:
        List of dictionaries sorted by total reputation (highest first), each containing:
          - faction_id: Internal identifier (e.g., "argon")
          - faction_name: Human-readable name from FACTION_NAMES mapping
          - value: Total scaled reputation
          - base: Scaled base standing
          - booster: Scaled temporary bonus (0 if none)
          - tier: UI display tier string (e.g., "Hostile", "Neutral", "Friendly")
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
        scaled_base    = scale_reputation(raw_base) if raw_base != 0 else 0.0
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
