import pathlib
import re
from lxml import etree as ET
from data.wares import WARE_NAMES, WARE_VOLUME, WARE_TRANSPORT
from data.station_stats import STATION_STATS
from scanner.language import macro_to_sector_name, resolve_sector_from_location, open_save, resolve_text_ref
from scanner.crew_scanner import _parse_manager, _iter_components

# ─────────────────────────────────────────────────────────────────────────────
#  CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

STATION_CLASSES = {"station", "factory", "headquarters", "complex"}
SHIP_CLASSES    = {"ship_s", "ship_m", "ship_l", "ship_xl"}

# Production modules follow the naming pattern prod_{prefix}_WARENAME_macro.
# Pre-compiled for performance — called on every entry in large save files.
PROD_MACRO_RE = re.compile(r'^prod_(?:\w+?)_(\w+)_macro$', re.IGNORECASE)

# Maps the raw XML state attribute on a station <component> to a player-facing label.
# Operational stations have no state attribute at all — the absent case defaults to "Operational".
# "wreck" stations remain in the save file as destroyed objects until the game cleans them up.
_STATE_LABELS = {
    "construction": "Under Construction",
    "wreck":        "Destroyed",
}

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


def _extract_station_docked_ships(station_elem: ET.Element) -> list[dict]:
    """
    Returns all ships physically docked at a station.

    Ships with connection="dock" are sitting in a docking bay inside the
    station's component subtree. This distinguishes them from ships with
    connection="space", which are defenders or visitors flying nearby.

    Ships under construction at a shipyard/HQ also appear here with a
    state="construction" attribute — they are included and tagged accordingly
    so the caller can separate active ships from ships-being-built.

    Only named ship classes (ship_s/m/l/xl) are returned. Drones are stored
    as <unit> ammunition elements and never appear as ship components.
    """
    docked = []

    for child in station_elem.iter():
        if child is station_elem:
            continue
        cls = child.get('class', '')
        if cls not in SHIP_CLASSES:
            continue
        if child.get('connection') != 'dock':
            continue

        docked.append({
            "code":              child.get('code', ''),
            "macro":             child.get('macro', ''),
            "owner":             child.get('owner', ''),
            "class":             cls,
            "under_construction": child.get('state') == 'construction',
        })

    return docked


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

        # Build a player-readable display name from the already-decoded fields.
        # Production modules identify themselves by what they make; all others
        # assemble faction + category + size, omitting any parts that are None.
        ware_id  = stats_entry.get('produces')
        produces = WARE_NAMES.get(ware_id, ware_id.replace('_', ' ').title()) if ware_id else None

        if produces:
            display_name = f"{produces} Production"
        else:
            name_parts = [p for p in (info["faction"], info["category"]) if p]
            display_name = " ".join(name_parts)
            if info["size"]:
                display_name += f" ({info['size']})"

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
                "macro":        macro,
                "display_name": display_name,
                "category":     info["category"],
                "faction":      info["faction"],
                "size":         info["size"],
                "produces":     None,
                "is_shield":    True,
                "hull_hp":      None,
                "hull_max":     None,
                "hull_pct":     None,
                "shield_hp":    current,
                "shield_max":   max_cap,
                "shield_pct":   (current / max_cap * 100.0) if max_cap else None,
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
                # No <hull> element means the module is at full health
                current_h = max_hull

            modules.append({
                "macro":        macro,
                "display_name": display_name,
                "category":     info["category"],
                "faction":      info["faction"],
                "size":         info["size"],
                "produces":     produces,
                "is_shield":    False,
                "hull_hp":      current_h,
                "hull_max":     max_hull,
                "hull_pct":     (current_h / max_hull * 100.0) if max_hull else None,
                "shield_hp":    None,
                "shield_max":   None,
                "shield_pct":   None,
            })

    return modules


def _classify_reservation(flags: str) -> str:
    """
    Returns 'buy', 'sell', or 'ignore' for a trade reservation entry.

    Reverse-engineered from live save data against known in-game fill values:
    - sellermoneyvirtual|buyermoneyvirtual (no invertfactionrestriction): incoming
      cargo en route to this station — pre-allocates space, adds to displayed fill.
    - sellermoneyvirtual|buyermoneyvirtual|invertfactionrestriction: goods
      physically present but committed to an outgoing order — subtracts from fill.
    - sell|virtual: virtual offer not backed by physical goods (e.g. in transit),
      not reflected in the game's displayed fill — ignored.
    """
    parts = set(flags.split('|'))
    if 'virtual' in parts and 'sell' in parts:
        return 'ignore'
    if 'invertfactionrestriction' in parts:
        return 'sell'
    if 'buyermoneyvirtual' in parts:
        return 'buy'
    return 'ignore'


def _parse_station_storage(station_elem: ET.Element) -> dict:
    """
    Returns per-type and total cargo storage utilisation for the station.

    Iterates instantiated <component class="storage"> subtrees within the
    station — each one carries a <cargo><ware ware="X" amount="Y"/></cargo>
    block with its current stock. The module type (container / solid / liquid)
    is inferred from the macro name substring. Amounts are converted to m³
    using WARE_VOLUME; the default for unknown wares is 1 m³/unit.

    Only modules present in STATION_STATS with a cargo_capacity are counted —
    this naturally excludes ship cargo holds (their macros aren't in that dict).
    _iter_components() skips ship subtrees, so docked ships' cargo never bleeds
    into the station's totals even if they happened to share a macro name.

    Modules whose macro name contains none of container/solid/liquid (e.g.
    tradestation storage) are counted toward the total only, not any type bar.
    """
    # Per-type accumulators: [current_m3, max_m3]
    acc = {"container": [0.0, 0], "solid": [0.0, 0], "liquid": [0.0, 0]}
    total_m3   = 0.0
    total_max  = 0
    inventory: dict[str, int] = {}  # ware_id → total units across all storage modules

    for comp in _iter_components(station_elem):
        if comp.get('class') != 'storage':
            continue
        macro    = comp.get('macro', '')
        capacity = STATION_STATS.get(macro, {}).get('cargo_capacity')
        if not capacity:
            continue

        # Map macro name to type; tradestation-style modules fall through to None
        m = macro.lower()
        if 'container' in m:
            type_key = 'container'
        elif 'solid' in m:
            type_key = 'solid'
        elif 'liquid' in m:
            type_key = 'liquid'
        else:
            type_key = None

        # Sum current stock in m³ from the module's <cargo> block; also tally units
        current_m3 = 0.0
        cargo_elem = comp.find('cargo')
        if cargo_elem is not None:
            for ware_elem in cargo_elem.findall('ware'):
                ware_id = ware_elem.get('ware', '')
                try:
                    amount = float(ware_elem.get('amount', 0))
                except (ValueError, TypeError):
                    amount = 0.0
                current_m3 += amount * WARE_VOLUME.get(ware_id, 1.0)
                if amount > 0:
                    inventory[ware_id] = inventory.get(ware_id, 0) + int(amount)

        if type_key:
            acc[type_key][0] += current_m3
            acc[type_key][1] += capacity
        total_m3  += current_m3
        total_max += capacity

    # ── Trade reservation adjustments ─────────────────────────────────────────
    # Parse <trade><reservations> to compute fill values matching the game UI.
    # Raw physical values (acc) and adjusted values (adj) are kept separate so
    # both are available independently in the exported JSON.
    #
    # adj starts as a copy of physical m³, then:
    #   buy  reservations add m³  (incoming cargo pre-allocating storage space)
    #   sell reservations subtract m³ (physically present goods committed outgoing)
    adj          = {t: acc[t][0] for t in ("container", "solid", "liquid")}
    adj_total_m3 = total_m3

    trade_elem = station_elem.find('trade')
    if trade_elem is not None:
        res_elem = trade_elem.find('reservations')
        if res_elem is not None:
            for res in res_elem.findall('reservation'):
                ware_id = res.get('ware', '')
                flags   = res.get('flags', '')
                try:
                    amount = float(res.get('amount', 0))
                except (ValueError, TypeError):
                    amount = 0.0

                rtype = _classify_reservation(flags)
                if rtype == 'ignore':
                    continue

                transport = WARE_TRANSPORT.get(ware_id)
                if transport not in adj:
                    continue

                delta = amount * WARE_VOLUME.get(ware_id, 1.0)
                if rtype == 'buy':
                    adj[transport]  += delta
                    adj_total_m3    += delta
                elif rtype == 'sell':
                    adj[transport]  -= delta
                    adj_total_m3    -= delta

    result: dict = {}
    for type_key in ("container", "solid", "liquid"):
        m3, max_v = acc[type_key]
        adj_m3    = adj[type_key]
        if max_v > 0:
            result[f"cargo_{type_key}_m3"]      = m3
            result[f"cargo_{type_key}_max"]     = max_v
            result[f"cargo_{type_key}_pct"]     = (m3 / max_v) * 100.0
            result[f"cargo_{type_key}_adj_m3"]  = adj_m3
            result[f"cargo_{type_key}_adj_pct"] = (adj_m3 / max_v) * 100.0
        else:
            result[f"cargo_{type_key}_m3"]      = None
            result[f"cargo_{type_key}_max"]     = None
            result[f"cargo_{type_key}_pct"]     = None
            result[f"cargo_{type_key}_adj_m3"]  = None
            result[f"cargo_{type_key}_adj_pct"] = None

    if total_max > 0:
        result["cargo_m3"]      = total_m3
        result["cargo_max"]     = total_max
        result["cargo_pct"]     = (total_m3 / total_max) * 100.0
        result["cargo_adj_m3"]  = adj_total_m3
        result["cargo_adj_pct"] = (adj_total_m3 / total_max) * 100.0
    else:
        result["cargo_m3"]      = None
        result["cargo_max"]     = None
        result["cargo_pct"]     = None
        result["cargo_adj_m3"]  = None
        result["cargo_adj_pct"] = None

    result["inventory"] = {
        WARE_NAMES.get(wid, wid): amt
        for wid, amt in sorted(inventory.items())
    }

    return result


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

def scan_save(file_path: pathlib.Path, sector_names: dict, language_texts: dict | None = None) -> dict:
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
                            display_name = resolve_text_ref(name_attr, language_texts or {})
                        elif 'headquarters' in macro.lower():
                            display_name = "Player HQ"
                        elif nameindex:
                            display_name = f"Station #{nameindex}"
                        else:
                            display_name = "Unnamed Station"

                        production    = parse_production_from_construction(elem)
                        module_count  = _count_construction_modules(elem)
                        modules       = _parse_station_modules(elem)
                        health        = _parse_station_health(modules)
                        storage       = _parse_station_storage(elem)
                        docked_ships  = _extract_station_docked_ships(elem)

                        raw_state = elem.get('state')
                        status    = _STATE_LABELS.get(raw_state, "Operational")

                        entry = {
                            "name":          display_name,
                            "code":          code,
                            "class":         elem.get('class', ''),
                            "macro":         macro,
                            "sector":        station_sector_pending,
                            "status":        status,
                            "production":    production,
                            "module_count":  module_count,
                            "docked_ships":  docked_ships,
                            "hull_hp":       health["hull_hp"],
                            "hull_max":      health["hull_max"],
                            "hull_pct":      health["hull_pct"],
                            "shield_hp":     health["shield_hp"],
                            "shield_max":    health["shield_max"],
                            "shield_pct":    health["shield_pct"],
                            "cargo_container_m3":      storage["cargo_container_m3"],
                            "cargo_container_max":     storage["cargo_container_max"],
                            "cargo_container_pct":     storage["cargo_container_pct"],
                            "cargo_container_adj_m3":  storage["cargo_container_adj_m3"],
                            "cargo_container_adj_pct": storage["cargo_container_adj_pct"],
                            "cargo_solid_m3":          storage["cargo_solid_m3"],
                            "cargo_solid_max":         storage["cargo_solid_max"],
                            "cargo_solid_pct":         storage["cargo_solid_pct"],
                            "cargo_solid_adj_m3":      storage["cargo_solid_adj_m3"],
                            "cargo_solid_adj_pct":     storage["cargo_solid_adj_pct"],
                            "cargo_liquid_m3":         storage["cargo_liquid_m3"],
                            "cargo_liquid_max":        storage["cargo_liquid_max"],
                            "cargo_liquid_pct":        storage["cargo_liquid_pct"],
                            "cargo_liquid_adj_m3":     storage["cargo_liquid_adj_m3"],
                            "cargo_liquid_adj_pct":    storage["cargo_liquid_adj_pct"],
                            "cargo_m3":                storage["cargo_m3"],
                            "cargo_max":               storage["cargo_max"],
                            "cargo_pct":               storage["cargo_pct"],
                            "cargo_adj_m3":            storage["cargo_adj_m3"],
                            "cargo_adj_pct":           storage["cargo_adj_pct"],
                            "inventory":     storage["inventory"],
                            "modules":       modules,
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

    return data
