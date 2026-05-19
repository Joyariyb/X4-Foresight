import pathlib
import re
from lxml import etree as ET
from data.wares import WARE_NAMES
from data.station_stats import STATION_STATS
from scanner.language import macro_to_sector_name, resolve_sector_from_location, open_save
from scanner.crew_scanner import _parse_manager, _iter_components

# ─────────────────────────────────────────────────────────────────────────────
#  CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

STATION_CLASSES = {"station", "factory", "headquarters", "complex"}

# Production modules follow the naming pattern prod_{prefix}_WARENAME_macro.
# Pre-compiled for performance — called on every entry in large save files.
PROD_MACRO_RE = re.compile(r'^prod_(?:\w+?)_(\w+)_macro$', re.IGNORECASE)

# ─────────────────────────────────────────────────────────────────────────────
#  MODULE INFO TABLES
#  Used by _parse_module_info() to decode macro tokens into human-readable fields.
# ─────────────────────────────────────────────────────────────────────────────

_MODULE_CATEGORIES = {
    "buildmodule": "Build Module",
    "cargo":       "Cargo",
    "connect":     "Connection",
    "defence":     "Defence",
    "dockarea":    "Dock Area",
    "hab":         "Habitat",
    "pier":        "Pier",
    "proc":        "Processing",
    "prod":        "Production",
    "radar":       "Radar",
    "shield":      "Shield",
    "storage":     "Storage",
}

# "gen" modules are cross-faction (no specific designer), so faction is None.
_MODULE_FACTIONS = {
    "arg": "Argon",
    "par": "Paranid",
    "tel": "Teladi",
    "spl": "Split",
    "ter": "Terran",
    "bor": "Boron",
    "xen": "Xenon",
    "kha": "Kha'ak",
    "pir": "Pirate",
    "gen": None,
}

_SIZE_TOKENS = {"s", "m", "l", "xl"}


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


def _count_construction_modules(station_elem: ET.Element) -> int:
    """
    Counts every entry in the station's <construction><sequence> block.

    Unlike _parse_station_modules(), this counts ALL module types — production,
    habitat, storage, dock areas, connection pieces, defence, shields, etc. —
    regardless of whether they appear in STATION_STATS. The result is the true
    planned module count as the player built it.
    """
    construction = station_elem.find('construction')
    if construction is None:
        return 0
    sequence = construction.find('sequence')
    if sequence is None:
        return 0
    return sum(1 for _ in sequence.findall('entry'))


def _parse_module_info(macro: str) -> dict:
    """
    Decodes the category, designer faction, and size from a module macro string.

    Macro format: {category}_{faction}_{size?}_{...}_{variant}_macro
    Token[0] is always the category prefix; token[1] is always the faction code.
    Size (s/m/l/xl) is found by scanning the remaining tokens — its position
    varies by category so positional indexing would be fragile.
    """
    tokens   = macro.removesuffix("_macro").split("_")
    category = _MODULE_CATEGORIES.get(tokens[0], tokens[0].title()) if tokens else macro
    faction  = None
    size     = None

    if len(tokens) >= 2:
        faction = _MODULE_FACTIONS.get(tokens[1], tokens[1].title())
    for token in tokens[2:]:
        if token in _SIZE_TOKENS:
            size = token.upper()
            break

    return {"category": category, "faction": faction, "size": size}


def _parse_station_modules(station_elem: ET.Element) -> list[dict]:
    """
    Iterates a fully-buffered station element and returns one dict per
    structural module and shield generator found in STATION_STATS.

    All module types share the same list — shield generators are distinguished
    by is_shield=True. This lets _parse_station_health() fold the list into
    totals, and lets the UI show per-module detail without a second parse.
    """
    modules = []

    for comp in _iter_components(station_elem):
        macro       = comp.get('macro', '')
        stats_entry = STATION_STATS.get(macro, {})
        is_shield   = 'max_shield' in stats_entry
        is_hull     = 'max_hull'   in stats_entry

        if not is_hull and not is_shield:
            continue

        info = _parse_module_info(macro)

        if is_shield:
            max_cap  = stats_entry['max_shield']
            cap_elem = comp.find('shield')
            if cap_elem is not None:
                try:
                    current = float(cap_elem.get('value', max_cap))
                except (ValueError, TypeError):
                    current = max_cap
            else:
                current = max_cap
            modules.append({
                "macro":      macro,
                "category":   info["category"],
                "faction":    info["faction"],
                "size":       info["size"],
                "produces":   None,
                "is_shield":  True,
                "hull_hp":    None,
                "hull_max":   None,
                "hull_pct":   None,
                "shield_hp":  current,
                "shield_max": max_cap,
                "shield_pct": (current / max_cap * 100.0) if max_cap else None,
            })
        else:
            max_hull  = stats_entry['max_hull']
            hull_elem = comp.find('hull')
            if hull_elem is not None:
                try:
                    current_h = float(hull_elem.get('value', max_hull))
                except (ValueError, TypeError):
                    current_h = max_hull
            else:
                current_h = max_hull

            ware_id  = stats_entry.get('produces')
            produces = WARE_NAMES.get(ware_id, ware_id.replace('_', ' ').title()) if ware_id else None

            modules.append({
                "macro":      macro,
                "category":   info["category"],
                "faction":    info["faction"],
                "size":       info["size"],
                "produces":   produces,
                "is_shield":  False,
                "hull_hp":    current_h,
                "hull_max":   max_hull,
                "hull_pct":   (current_h / max_hull * 100.0) if max_hull else None,
                "shield_hp":  None,
                "shield_max": None,
                "shield_pct": None,
            })

    return modules


def _parse_station_health(modules: list[dict]) -> dict:
    """
    Folds a module list into station-level hull and shield totals.
    Separated from _parse_station_modules() so either can be called independently.
    """
    hull_current   = 0.0
    hull_max_total = 0.0
    shield_current = 0.0
    shield_max_total = 0.0
    has_shields    = False

    for mod in modules:
        if mod["is_shield"]:
            has_shields        = True
            shield_current    += mod["shield_hp"]
            shield_max_total  += mod["shield_max"]
        else:
            hull_current   += mod["hull_hp"]
            hull_max_total += mod["hull_max"]

    if hull_max_total > 0:
        hull_pct     = (hull_current / hull_max_total) * 100.0
        hull_out     = hull_current
        hull_max_out = hull_max_total
    else:
        hull_out = hull_max_out = hull_pct = None

    if not has_shields:
        shield_hp = shield_max_out = shield_pct = None
    elif shield_max_total > 0:
        shield_hp      = shield_current
        shield_max_out = shield_max_total
        shield_pct     = (shield_current / shield_max_total) * 100.0
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

                        production   = parse_production_from_construction(elem)
                        module_count = _count_construction_modules(elem)
                        modules      = _parse_station_modules(elem)
                        health       = _parse_station_health(modules)

                        entry = {
                            "name":         display_name,
                            "code":         code,
                            "class":        elem.get('class', ''),
                            "macro":        macro,
                            "sector":       station_sector_pending,
                            "production":   production,
                            "module_count": module_count,
                            "hull_hp":      health["hull_hp"],
                            "hull_max":     health["hull_max"],
                            "hull_pct":     health["hull_pct"],
                            "shield_hp":    health["shield_hp"],
                            "shield_max":   health["shield_max"],
                            "shield_pct":   health["shield_pct"],
                            "modules":      modules,
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
