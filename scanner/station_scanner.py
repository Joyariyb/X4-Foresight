import pathlib
import re
from lxml import etree as ET
from data.wares import WARE_NAMES
from data.station_stats import STATION_STATS
from scanner.language import macro_to_sector_name, resolve_sector_from_location, open_save
from scanner.crew_scanner import _parse_manager

# ─────────────────────────────────────────────────────────────────────────────
#  CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

STATION_CLASSES = {"station", "factory", "headquarters", "complex"}

# Production modules follow the naming pattern prod_{prefix}_WARENAME_macro.
# Pre-compiled for performance — called on every entry in large save files.
PROD_MACRO_RE = re.compile(r'^prod_(?:\w+?)_(\w+)_macro$', re.IGNORECASE)


# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def parse_production_from_construction(station_elem: ET.Element) -> str:
    """
    Extracts unique production outputs from a station's <construction><sequence> block.
    Returns a comma-separated string of ware display names, or "" if none found.

    We read from <sequence> only (not <snapshot>) to avoid stale duplicate entries
    from an earlier snapshot of the construction state.
    """
    seen_wares = set()
    production = []

    construction = station_elem.find('construction')
    if construction is None:
        return ""
    sequence = construction.find('sequence')
    if sequence is None:
        return ""

    for entry in sequence.findall('entry'):
        macro = entry.get('macro', '')
        m = PROD_MACRO_RE.match(macro)
        if not m:
            continue
        ware_id = m.group(1).lower()
        if ware_id in seen_wares:
            continue
        seen_wares.add(ware_id)
        display = WARE_NAMES.get(ware_id, ware_id.replace('_', ' ').title())
        production.append(display)

    return ", ".join(production)



def _station_components(station_elem: ET.Element):
    """
    Yield every component element within a station, skipping docked ship subtrees.

    elem.iter('component') recurses into ships docked at the station — their
    shield generators and equipment would pollute the station's own hull and
    shield totals. We stop recursion the moment we hit a ship_* class component.
    """
    queue = list(station_elem)
    while queue:
        node = queue.pop()
        if node.tag != 'component':
            queue.extend(node)
            continue
        if node.get('class', '').startswith('ship_'):
            continue  # skip this ship and everything inside it
        yield node
        queue.extend(node)


def _parse_station_health(station_elem: ET.Element) -> dict:
    """
    Extracts hull and shield health from a fully-buffered station element.

    Hull: Iterates all module components and sums current vs max HP across
    every module whose macro exists in STATION_STATS. Missing <hull> means
    that module is at full health. Each module is recorded individually in
    the returned 'modules' list for storage and export.

    Shields: Sums capacity from all installed shield generator components.
    Missing <shield> means that generator is at full capacity. Docked ship
    components are excluded via _station_components().
    """
    hull_current   = 0.0
    hull_max       = 0.0
    shield_current = 0.0
    shield_max     = 0.0
    has_generators = False
    modules        = []

    for comp in _station_components(station_elem):
        macro       = comp.get('macro', '')
        stats_entry = STATION_STATS.get(macro, {})

        if 'max_hull' in stats_entry:
            max_h     = stats_entry['max_hull']
            hull_elem = comp.find('hull')
            if hull_elem is not None:
                try:
                    current_h = float(hull_elem.get('value', max_h))
                except (ValueError, TypeError):
                    current_h = max_h
            else:
                current_h = max_h

            hull_current += current_h
            hull_max     += max_h
            modules.append({
                "macro":    macro,
                "hull_hp":  current_h,
                "hull_max": max_h,
            })

        if comp.get('class', '').startswith('shieldgenerator') and 'max_shield' in stats_entry:
            has_generators = True
            max_sh         = stats_entry['max_shield']
            shield_elem    = comp.find('shield')
            if shield_elem is not None:
                try:
                    shield_current += float(shield_elem.get('value', max_sh))
                except (ValueError, TypeError):
                    shield_current += max_sh
            else:
                shield_current += max_sh
            shield_max += max_sh

    if hull_max > 0:
        hull_pct     = (hull_current / hull_max) * 100.0
        hull_out     = hull_current
        hull_max_out = hull_max
    else:
        hull_out = hull_max_out = hull_pct = None
        modules  = []

    if not has_generators:
        shield_hp = shield_max_out = shield_pct = None
    elif shield_max > 0:
        shield_hp      = shield_current
        shield_max_out = shield_max
        shield_pct     = (shield_current / shield_max) * 100.0
    else:
        shield_hp      = shield_current if shield_current > 0 else None
        shield_max_out = None
        shield_pct     = None

    return {
        "hull_hp":    hull_out,
        "hull_max":   hull_max_out,
        "hull_pct":   hull_pct,
        "shield_hp":  shield_hp,
        "shield_max": shield_max_out,
        "shield_pct": shield_pct,
        "modules":    modules,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  PASS 1 — PLAYER DATA AND STATIONS
# ─────────────────────────────────────────────────────────────────────────────

def scan_save(file_path: pathlib.Path, sector_names: dict) -> dict:
    """
    Streams the save file and extracts player identity, credits, sector location,
    and all owned stations with their production, health, and manager data.

    Uses iterparse() for memory efficiency on 700MB+ save files. Station elements
    are buffered in memory only long enough to extract their full subtree, then
    cleared. All other elements are cleared immediately after processing.
    """
    data = {
        "player_name":    None,
        "player_credits": None,
        "player_sector":  None,
        "stations":       [],
        "reputation":     [],
        "managers":       [],
    }

    in_player_faction    = False
    current_sector       = "Unknown Sector"
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
                        macro    = elem.get('macro', '')
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
                        health     = _parse_station_health(elem)

                        entry = {
                            "name":       display_name,
                            "code":       code,
                            "class":      elem.get('class', ''),
                            "macro":      macro,
                            "sector":     station_sector_pending,
                            "production": production,
                            "hull_hp":    health["hull_hp"],
                            "hull_max":   health["hull_max"],
                            "hull_pct":   health["hull_pct"],
                            "shield_hp":  health["shield_hp"],
                            "shield_max": health["shield_max"],
                            "shield_pct": health["shield_pct"],
                            "modules":    health["modules"],
                        }

                        if not any(s["code"] == code for s in data["stations"]):
                            data["stations"].append(entry)

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
