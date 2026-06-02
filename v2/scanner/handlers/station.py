from __future__ import annotations
import re
from data.factions import FACTION_NAMES
from data.wares import WARE_NAMES, WARE_VOLUME, WARE_TRANSPORT
from data.station_stats import STATION_STATS
from ..entities import Station, StationModule, CargoStorage, CrewMember
from ..language import (
    macro_to_sector_name,
    resolve_text_ref,
    resolve_station_type,
    nameindex_to_roman,
)
from ..budget import estimate_station_budget
from ..xml_utils import iter_station_components


# ─────────────────────────────────────────────────────────────────────────────
#  MODULE-LEVEL CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

# Maps the raw state attribute on a station <component> to a display label.
# Operational stations have NO state attribute — absent maps to "Operational".
_STATE_LABELS = {
    "construction": "Under Construction",
    "wreck":        "Destroyed",
}

# Matches production module macros: prod_{faction}_{ware}_macro
# Group 1 is the produced ware ID.
_PROD_MACRO_RE = re.compile(r'^prod_(?:\w+?)_(\w+)_macro$', re.IGNORECASE)

# Maps the category token (first token of a module macro) to a display label.
# Used to produce a human-readable category for StationModule.
_MODULE_CATEGORIES: dict[str, str] = {
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


# ─────────────────────────────────────────────────────────────────────────────
#  HANDLER
# ─────────────────────────────────────────────────────────────────────────────

class StationHandler:
    """
    Extracts all player station data from buffered station subtrees.

    Called twice per station:
      on_start() — captures sector context from the component stack while the
                   opening tag is still being processed.
      on_end()   — the full subtree is in memory; walks it to extract modules,
                   cargo, health, budget, account, and manager crew.

    All logic is ported from v1's station_scanner.py, updated to produce
    typed dataclasses instead of raw dicts.
    """

    def __init__(self, sector_names: dict, texts: dict) -> None:
        self._sector_names = sector_names  # {lang_id: sector_name}
        self._texts        = texts         # language pages 20102, 20215

        # Per-station state, set in on_start and consumed in on_end.
        self._sector_macro: str = ''
        self._sector_name:  str = ''

    # ── Dispatcher entry points ───────────────────────────────────────────────

    def on_start(self, elem, ctx) -> None:
        """
        Capture the sector context before the subtree is buffered.

        We read ctx.current_sector_macro (set by SectorHandler) rather than
        walking the component stack. The stack depth between a sector and a
        station varies — zone and other components also push frames — so
        frame_at(1) is not reliably the sector frame.
        """
        self._sector_macro = ctx.current_sector_macro
        self._sector_name  = (
            macro_to_sector_name(self._sector_macro, self._sector_names) or ''
        )

    def on_end(self, elem, ctx) -> None:
        """
        Build the Station entity once the full subtree is in memory.

        Walks the buffered element to extract modules, health, cargo,
        inventory, budget, and manager. Appends to ctx.stations and
        registers the object_id in ctx.player_station_ids.
        """
        object_id = elem.get('id',    '')
        code      = elem.get('code',  '')
        macro     = elem.get('macro', '')
        raw_state = elem.get('state')         # absent = operational
        status    = _STATE_LABELS.get(raw_state, 'Operational')

        # ── Station name ──────────────────────────────────────────────────────
        name = self._resolve_name(elem, macro)

        # ── Module list and health ─────────────────────────────────────────────
        # _parse_modules walks the subtree once and returns both the
        # StationModule list and the per-module hull/shield data needed for
        # health totals — avoids a second traversal.
        modules, hull_hp, hull_max, shield_hp, shield_max = self._parse_modules(elem)
        hull_pct   = (hull_hp   / hull_max   * 100.0) if hull_max   else None
        shield_pct = (shield_hp / shield_max * 100.0) if shield_max else None

        # ── Cargo storage ─────────────────────────────────────────────────────
        cargo_container, cargo_solid, cargo_liquid, cargo_total, inventory = \
            self._parse_storage(elem)

        # ── Station account ───────────────────────────────────────────────────
        # own="1" marks the station's operating cash account; other <account>
        # elements inside the station are trade escrow accounts.
        acct_elem      = elem.find('account[@own="1"]')
        account_amount = None
        if acct_elem is not None:
            try:
                account_amount = int(acct_elem.get('amount', 0))
            except (ValueError, TypeError):
                pass

        # ── Module count ──────────────────────────────────────────────────────
        # Count every entry in the construction sequence (including structural
        # pieces, dock areas, etc.) for the true total module count.
        module_count = self._count_modules(elem)

        # ── Budget estimate ───────────────────────────────────────────────────
        # Reverse-engineered supply budget. Needs the resolved sector name for
        # the sunlight multiplier used in energy-cell production.
        budget = estimate_station_budget(elem, self._sector_name)

        # ── Build Station dataclass ───────────────────────────────────────────
        station = Station(
            scan_id          = ctx.scan_id,
            object_id        = object_id,
            code             = code,
            name             = name,
            sector_macro     = self._sector_macro,
            status           = status,
            module_count     = module_count,
            hull_hp          = hull_hp   if hull_max   else None,
            hull_max         = hull_max  if hull_max   else None,
            hull_pct         = hull_pct,
            shield_hp        = shield_hp   if shield_max else None,
            shield_max       = shield_max  if shield_max else None,
            shield_pct       = shield_pct,
            cargo_container  = cargo_container,
            cargo_solid      = cargo_solid,
            cargo_liquid     = cargo_liquid,
            cargo_total      = cargo_total,
            account_amount   = account_amount,
            budget_total     = budget['total'],
            budget_sunlight  = budget['sunlight'],
            modules          = modules,
            inventory        = inventory,
        )

        ctx.stations.append(station)

        # Register for EconomyHandler and TradeHandler — must be present before
        # those handlers process any trade entries. Safe because economy logs
        # and trade orders appear after station definitions in the XML stream.
        ctx.player_station_ids.add(object_id)

        # ── Manager crew member ───────────────────────────────────────────────
        manager = self._parse_manager(elem, code, ctx)
        if manager:
            ctx.crew.append(manager)

        # Clear per-station state ready for the next station.
        self._sector_macro = ''
        self._sector_name  = ''

    # ── Private helpers ───────────────────────────────────────────────────────

    def _resolve_name(self, elem, macro: str) -> str:
        """
        Resolves the display name for a player station.

        Path A — player typed a custom name (the name attribute is a literal
                  string, not a language reference): use it verbatim, no sector
                  prefix or roman numeral appended.

        Path B — basename is a {page,id} language reference: resolve it to the
                  station type name (e.g. "Defence Platform").

        Path C — infer from production module macros collected from the
                  fully-buffered construction sequence.

        Path D — fallback for HQ macro or unnamed station.

        Auto-named stations (B/C/D) are prefixed with the sector name and
        suffixed with a roman numeral to match X4's in-game auto-name format:
        e.g. "The Void High Tech Factory II".
        """
        name_attr = elem.get('name', '')
        basename  = elem.get('basename', '')
        nameindex = elem.get('nameindex', '')

        if name_attr:
            # Path A: player-given literal name
            return name_attr

        display = ''

        # Path B: basename language reference
        if basename:
            resolved = resolve_text_ref(basename, self._texts)
            if resolved and not resolved.startswith('{'):
                display = resolved

        # Path C: production module macros
        if not display:
            prod_macros = [
                c.get('macro', '')
                for c in elem.iter('component')
                if c.get('class') == 'production'
            ]
            display = resolve_station_type(prod_macros, self._texts)

        # Path D: fallback
        if not display:
            if 'headquarters' in macro.lower():
                display = 'Headquarters'
            else:
                display = 'Unnamed Station'

        # Append roman numeral and prepend sector name for auto-names
        if display not in ('Unnamed Station',):
            roman = nameindex_to_roman(nameindex) if nameindex else ''
            if roman:
                display = f'{display} {roman}'
            if self._sector_name:
                display = f'{self._sector_name} {display}'

        return display

    def _parse_modules(
        self, elem
    ) -> tuple[list[StationModule], float, float, float | None, float | None]:
        """
        Walks the station subtree and returns:
          (modules, hull_hp, hull_max, shield_hp, shield_max)

        Only components that appear in STATION_STATS are processed — this
        naturally excludes drones, decorative parts, and connection pieces
        that don't contribute to tracked health. iter_station_components
        skips docked ship subtrees so their modules are never counted.

        Hull: absent <hull> element means the module is at full health.
        Shield: absent <shield> element means the module is at full capacity.
        """
        station_modules: list[StationModule] = []
        hull_current    = 0.0
        hull_total      = 0.0
        shield_current  = 0.0
        shield_total    = 0.0
        has_shields     = False

        for comp in iter_station_components(elem):
            macro       = comp.get('macro', '')
            stats_entry = STATION_STATS.get(macro, {})
            if not stats_entry:
                continue

            is_shield = 'max_shield' in stats_entry
            is_hull   = 'max_hull'   in stats_entry
            if not is_hull and not is_shield:
                continue

            # ── Category and produces for StationModule ───────────────────────
            tokens   = macro.removesuffix('_macro').split('_')
            category = _MODULE_CATEGORIES.get(tokens[0], tokens[0].title()) if tokens else macro

            produces: str | None = None
            ware_id = stats_entry.get('produces')
            if ware_id:
                produces = WARE_NAMES.get(ware_id, ware_id.replace('_', ' ').title())
            elif is_shield:
                category = 'Shield'

            station_modules.append(StationModule(
                macro    = macro,
                category = category,
                produces = produces,
            ))

            # ── Health accounting ─────────────────────────────────────────────
            if is_shield:
                has_shields  = True
                max_cap      = stats_entry['max_shield']
                shield_elem  = comp.find('shield')
                if shield_elem is not None:
                    try:
                        current = float(shield_elem.get('value', max_cap))
                    except (ValueError, TypeError):
                        current = max_cap
                else:
                    # No <shield> element — module is at full capacity
                    current = max_cap
                shield_current += current
                shield_total   += max_cap
            else:
                max_hull  = stats_entry['max_hull']
                hull_elem = comp.find('hull')
                if hull_elem is not None:
                    try:
                        current_h = float(hull_elem.get('value', max_hull))
                    except (ValueError, TypeError):
                        current_h = max_hull
                else:
                    # No <hull> element — module is at full health
                    current_h = max_hull
                hull_current += current_h
                hull_total   += max_hull

        shield_hp  = shield_current if has_shields else None
        shield_max = shield_total   if has_shields else None

        return (
            station_modules,
            hull_current,
            hull_total,
            shield_hp,
            shield_max,
        )

    def _parse_storage(
        self, elem
    ) -> tuple[
        CargoStorage | None, CargoStorage | None,
        CargoStorage | None, CargoStorage | None,
        dict[str, int],
    ]:
        """
        Builds per-type and total CargoStorage objects for this station.

        Iterates <component class="storage"> subtrees to sum physical cargo
        volumes. Then applies trade reservations from <trade><reservations>
        to compute adjusted fill values that match the game UI.

        Ware volumes are converted using WARE_VOLUME (m³ per unit). Cargo
        type (container / solid / liquid) is inferred from the macro name.
        Only storage macros in STATION_STATS with a cargo_capacity are counted
        — this excludes ship cargo holds even if a ship is docked.
        """
        acc: dict[str, list[float]] = {
            'container': [0.0, 0.0],
            'solid':     [0.0, 0.0],
            'liquid':    [0.0, 0.0],
        }
        total_m3  = 0.0
        total_max = 0.0
        inventory: dict[str, int] = {}

        for comp in iter_station_components(elem):
            if comp.get('class') != 'storage':
                continue
            macro    = comp.get('macro', '')
            capacity = STATION_STATS.get(macro, {}).get('cargo_capacity')
            if not capacity:
                continue

            # Classify by macro name substring — confirmed naming convention
            m_lower = macro.lower()
            if 'container' in m_lower:
                type_key: str | None = 'container'
            elif 'solid' in m_lower:
                type_key = 'solid'
            elif 'liquid' in m_lower:
                type_key = 'liquid'
            else:
                type_key = None   # tradestation storage — total only

            # Sum current stock from <cargo><ware> children
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
                acc[type_key][1] += float(capacity)
            total_m3  += current_m3
            total_max += float(capacity)

        # ── Trade reservation adjustments ─────────────────────────────────────
        # Adjusted values match the fill % the player sees in-game.
        # buy  reservations add    m³ (incoming cargo en route, pre-allocating space)
        # sell reservations subtract m³ (goods committed to an outgoing order)
        adj: dict[str, float] = {t: acc[t][0] for t in acc}
        adj_total = total_m3

        trade_elem = elem.find('trade')
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
                        adj[transport] += delta
                        adj_total      += delta
                    elif rtype == 'sell':
                        adj[transport] -= delta
                        adj_total      -= delta

        # ── Build CargoStorage dataclasses ────────────────────────────────────
        def _make(type_key: str) -> CargoStorage | None:
            m3, max_v = acc[type_key]
            if max_v <= 0:
                return None
            a_m3 = adj[type_key]
            return CargoStorage(
                m3      = m3,
                max_m3  = max_v,
                pct     = (m3   / max_v) * 100.0,
                adj_m3  = a_m3,
                adj_pct = (a_m3 / max_v) * 100.0,
            )

        cargo_container = _make('container')
        cargo_solid     = _make('solid')
        cargo_liquid    = _make('liquid')
        cargo_total     = (
            CargoStorage(
                m3      = total_m3,
                max_m3  = total_max,
                pct     = (total_m3  / total_max) * 100.0,
                adj_m3  = adj_total,
                adj_pct = (adj_total / total_max) * 100.0,
            )
            if total_max > 0 else None
        )

        return cargo_container, cargo_solid, cargo_liquid, cargo_total, inventory

    def _count_modules(self, elem) -> int:
        """
        Returns the total number of modules in the station's construction sequence.

        Counts every <entry> in <construction><sequence> — production modules,
        storage, dock areas, connection pieces, defence, shields, etc. This is
        the true planned module count as the player built it, not just the
        tracked-health subset.
        """
        construction = elem.find('construction')
        if construction is None:
            return 0
        sequence = construction.find('sequence')
        if sequence is None:
            return 0
        return sum(1 for _ in sequence.findall('entry'))

    def _parse_manager(
        self, elem, station_code: str, ctx
    ) -> CrewMember | None:
        """
        Finds the station manager NPC and returns a CrewMember, or None if vacant.

        Manager location: <control><post id="manager" component="[0x...]"/>
        The component attribute references a <component class="npc"> in the
        station subtree. Skills are on a <skills> element under <traits>.
        """
        control = elem.find('control')
        if control is None:
            return None

        manager_id: str | None = None
        for post in control.findall('post'):
            if post.get('id') == 'manager':
                manager_id = post.get('component')
                break

        if not manager_id:
            return None

        # Find the NPC component with the matching id
        for comp in iter_station_components(elem):
            if comp.get('class') != 'npc' or comp.get('id') != manager_id:
                continue

            name = comp.get('name', '')
            # Skip unresolved language references (e.g. "{20101,22603}")
            if not name or (name.startswith('{') and name.endswith('}')):
                return None

            macro = comp.get('macro', '')

            traits = comp.find('traits')
            skills_elem = traits.find('skills') if traits is not None else None

            def skill(attr: str) -> int:
                if skills_elem is None:
                    return 0
                try:
                    return int(skills_elem.get(attr, 0))
                except (ValueError, TypeError):
                    return 0

            seed_elem = comp.find('npcseed')
            seed = seed_elem.get('seed') if seed_elem is not None else None

            # Faction and gender from the character macro:
            # e.g. "character_argon_male_asi_crew_01_macro"
            faction = None
            gender  = None
            if macro:
                parts = macro.split('_')
                if len(parts) >= 2:
                    faction = parts[1] if parts[1] != 'character' else (parts[2] if len(parts) > 2 else None)
                if 'male' in parts and 'fe' not in ''.join(parts):
                    gender = 'male'
                elif 'female' in parts:
                    gender = 'female'

            return CrewMember(
                scan_id           = ctx.scan_id,
                role              = 'manager',
                name              = name,
                object_id         = manager_id,
                seed              = seed,
                assigned_code     = station_code,
                assigned_type     = 'station',
                sector_macro      = self._sector_macro,
                faction           = faction,
                gender            = gender,
                skill_piloting    = skill('piloting'),
                skill_management  = skill('management'),
                skill_morale      = skill('morale'),
                skill_engineering = skill('engineering'),
                skill_boarding    = skill('boarding'),
            )

        return None


# ─────────────────────────────────────────────────────────────────────────────
#  RESERVATION CLASSIFIER
# ─────────────────────────────────────────────────────────────────────────────

def _classify_reservation(flags: str) -> str:
    """
    Returns 'buy', 'sell', or 'ignore' for a trade reservation entry.

    Reverse-engineered from live save data against known in-game fill values:
      sellermoneyvirtual|buyermoneyvirtual (no invertfactionrestriction):
          incoming cargo en route — pre-allocates storage space → 'buy'
      sellermoneyvirtual|buyermoneyvirtual|invertfactionrestriction:
          goods committed to an outgoing order → 'sell'
      sell|virtual:
          virtual offer not backed by physical goods — ignored
    """
    parts = set(flags.split('|'))
    if 'virtual' in parts and 'sell' in parts:
        return 'ignore'
    if 'invertfactionrestriction' in parts:
        return 'sell'
    if 'buyermoneyvirtual' in parts:
        return 'buy'
    return 'ignore'
