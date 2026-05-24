# scanner/combined_scanner.py
# ─────────────────────────────────────────────────────────────────────────────
#  COMBINED STATION + SHIP SCANNER  (single-pass optimisation)
# ─────────────────────────────────────────────────────────────────────────────
#
#  Merges Pass 1 (station_scanner) and Pass 3 (ship_scanner) into one
#  streaming read of the 700MB+ save file. Previously those two passes were
#  always separate file reads. This module combines their iterparse loops
#  while keeping the original modules untouched — it imports helpers from
#  both and wires them together here.
#
#  ── MUTUAL EXCLUSION INVARIANT ──────────────────────────────────────────────
#  Exactly one of the three buffering states may be active at any moment:
#
#    inside_station          — buffering a player station's entire subtree so
#                              _parse_station_modules / _parse_station_storage
#                              can walk the element tree at close time.
#
#    npc_station_elem_pending — lightweight NPC station tracking: production
#                              macros and traded wares are read from start
#                              events; child elements are cleared normally.
#
#    inside_ship             — buffering a ship's entire subtree so crew,
#                              orders, software, and hull data can be read.
#
#  None of these three ever nest inside another, so ships inside station bays
#  are invisible to the main loop (blocked by inside_station) and picked up
#  by _extract_station_docked_ships() on the fully-buffered station element.
#  Ships inside carrier bays are similarly invisible (blocked by inside_ship)
#  and extracted by _extract_docked_ships() when the carrier closes.
#
#  ── NPC SHIP TIER HANDLING ──────────────────────────────────────────────────
#  In the two-pass approach, the station pass ran first, so station sectors
#  were known before any ship was buffered. In a single pass, a ship can appear
#  in the XML before the player station in the same sector has been seen.
#
#  Solution: collect ALL slim NPC ship records when any NPC ships are wanted
#  (tier >= 2), then filter to the appropriate sector set after the pass:
#
#    Tier 1  → no NPC ships collected (collect_all_npcs = False)
#    Tier 2  → filter to station sectors after the pass
#    Tier 3  → filter to station sectors ∪ player ship sectors after the pass

import pathlib
from lxml import etree as ET

from scanner.language import (
    macro_to_sector_name,
    nameindex_to_roman,
    resolve_sector_from_location,
    resolve_station_type,
    resolve_text_ref,
    open_save,
)
from scanner.station_scanner import (
    STATION_CLASSES,
    SHIP_CLASSES,
    _STATE_LABELS,
    _build_npc_display_name,
    parse_production_from_construction,
    _count_construction_modules,
    _extract_station_docked_ships,
    _parse_station_modules,
    _parse_station_health,
    _parse_station_storage,
)
from scanner.ship_scanner import (
    SIZE_LABELS,
    extract_role,
    extract_faction_from_macro,
    resolve_ship_type,
    _parse_sector,
    _parse_current_order,
    _parse_hull,
    _parse_shield,
    _parse_software,
    _parse_commander,
    _parse_homebase,
    _extract_docked_ships,
)
from scanner.crew_scanner import (
    LANG_STRING_RE,
    _parse_pilot,
    _extract_people,
    _parse_manager,
)
from data.wares import WARE_NAMES
from data.ship_stats import SHIP_STATS


def scan_save_and_ships(
    file_path:            pathlib.Path,
    sector_names:         dict,
    language_texts:       dict | None = None,
    collect_npc_stations: bool = False,
    ship_tier:            int  = 1,
) -> dict:
    """
    Streams the save file once and extracts both station data (Pass 1) and
    ship data (Pass 3) in the same iterparse loop.

    Args:
        file_path:            Path to the .xml or .xml.gz save file.
        sector_names:         Dict from load_sector_names() — maps language
                              IDs to human-readable sector display names.
        language_texts:       Dict from load_text_pages() — used to resolve
                              {page,id} language references in station names.
                              Pass None to skip text resolution.
        collect_npc_stations: When True, collect lightweight NPC station
                              records alongside player stations. The result
                              dict will include "npc_stations_raw"; the caller
                              filters that list to player sectors.
        ship_tier:            Controls NPC ship collection depth:
                              1 — player ships only (no NPC ships collected)
                              2 — collect all NPC ships, then filter to sectors
                                  where the player has a station
                              3 — collect all NPC ships, then filter to sectors
                                  where the player has a station OR a ship

    Returns a dict with keys:
        player_name / player_credits / player_sector — player identity
        stations        — list of player station dicts (same shape as scan_save)
        managers        — list of station manager crew entries
        reputation      — empty list (filled by reputation_scanner separately)
        player_ships    — list of player ship dicts (same shape as scan_ships)
        npc_ships       — list of NPC ship dicts (already tier-filtered)
        crew            — ship crew entries (pilots + service + marines)
                          NOTE: does not include station managers — those are
                          in 'managers'. The caller merges them.
        sector_macro_to_name — internal dict mapping macro strings to resolved
                               sector display names. Pop and discard before
                               merging into game_data — it's plumbing for
                               subsequent scans, not user-facing data.
        npc_stations_raw — present only when collect_npc_stations=True.
                           Unfiltered list of all NPC stations found.
    """
    texts = language_texts or {}

    # ── Output containers ──────────────────────────────────────────────────────
    player_name:      str | None   = None
    player_credits:   str | None   = None
    player_sector:    str | None   = None
    stations:         list[dict]   = []
    managers:         list[dict]   = []
    npc_stations_raw: list[dict]   = []

    player_ships: list[dict] = []
    npc_ships:    list[dict] = []
    crew:         list[dict] = []   # ship crew only; managers are separate

    # ship_id → homebase station object ID for every NPC ship encountered.
    # Populated two ways depending on whether the ship is buffered:
    #   - Buffered NPC ships (collect_all_npcs=True):  _parse_homebase(se) at close time.
    #   - Non-buffered NPC ships (collect_all_npcs=False): in_hb_ship state machine.
    # Ships that get filtered out by the tier filter are no longer in npc_ships,
    # but their entries remain in homebase_index so the trade history scanner can
    # resolve counterparty ships that have moved away from player sectors.
    homebase_index: dict[str, str] = {}

    # ── Sector / zone context tracking ────────────────────────────────────────
    # current_sector:       resolved display name for stations ("The Void", etc.)
    # current_sector_macro: raw macro string stamped onto ship elements so
    #                       _parse_sector() can look up the name at close time.
    # current_zone_macro:   raw zone macro, used as a fallback by _parse_sector().
    # sector_macro_to_name: cache built here, returned to the caller so any
    #                       subsequent scan (e.g. trade scanner) can resolve
    #                       sector names in O(1) without re-running the regex.
    current_sector:       str = "Unknown Sector"
    current_sector_macro: str = ""
    current_zone_macro:   str = ""
    sector_macro_to_name: dict[str, str] = {}

    # ── Player identity tracking ───────────────────────────────────────────────
    in_player_faction = False

    # ── Player station buffering ───────────────────────────────────────────────
    # The full station subtree must be in memory at close time so the helper
    # functions can iterate production modules, cargo, shields, etc.
    inside_station:         bool             = False
    station_elem_pending:   ET.Element | None = None
    station_sector_pending: str              = ""

    # ── NPC station lightweight tracking ──────────────────────────────────────
    # NPC station data is read from start events only — no subtree buffering.
    # Child elements are cleared normally by the default cleanup at the bottom.
    npc_station_elem_pending:   ET.Element | None = None
    npc_station_sector_pending: str               = ""
    npc_prod_macros:            list[str]         = []
    npc_wares:                  list[str]         = []

    # ── Ship buffering ─────────────────────────────────────────────────────────
    # Ships (player and NPC) are fully buffered for crew, order, and health parsing.
    # ship_depth counts XML nesting depth so we know exactly when the closing tag
    # of the ship component arrives (depth goes 1 → 0).
    inside_ship:        bool             = False
    ship_elem_pending:  ET.Element | None = None
    ship_owner_pending: str               = ""
    ship_depth:         int               = 0

    # ── Homebase extraction (non-buffered NPC ships) ───────────────────────────
    # When collect_all_npcs=False (tier 1), NPC ships are not buffered. We still
    # need their homebase station ID for trade history counterparty resolution, so
    # we use a lightweight state machine that reads the default order params from
    # start events without keeping any subtree in memory. Runs in parallel with the
    # normal buffering loop, triggered by the ship detection block below.
    in_hb_ship:     bool = False
    hb_ship_id:     str  = ''
    hb_depth:       int  = 0
    hb_in_orders:   bool = False
    hb_order_type:  str  = ''   # 'TradeRoutine' or 'Middleman'
    hb_in_default:  bool = False

    # The economy log can reference a ship by either the ship component's own id
    # (hex bracket, e.g. "[0x1717a]") or the outer <connection> wrapper's decimal
    # id (e.g. "114", which _norm() converts to "[0x72]"). These are different
    # values. We track the most-recent connection wrapper id and add a second entry
    # to homebase_index keyed by the normalised decimal form so the economy resolver
    # gets a hit regardless of which format the log entry uses.
    last_connection_id: str = ''   # id of the most-recent outer <connection> seen
    hb_conn_id:         str = ''   # connection wrapper id captured at in_hb_ship entry

    # Tier 1 = player ships only. Tier 2+ = collect slim records for all NPC
    # ships during the stream, then filter to context sectors after the pass.
    collect_all_npcs = (ship_tier >= 2)

    npc_str  = " + NPC stations" if collect_npc_stations else ""
    tier_str = f"ships tier {ship_tier}"
    print(f"[Scanning] Combined — player, stations{npc_str}, {tier_str}...")

    try:
        with open_save(file_path) as f:
            context = ET.iterparse(f, events=('start', 'end'))

            for event, elem in context:
                tag      = elem.tag
                comp_cls = elem.get('class', '')

                # ── Player identity ────────────────────────────────────────────
                # These checks mirror station_scanner.scan_save() exactly.
                # They run unconditionally — player identity elements appear at
                # the top of the file, never nested inside stations or ships.
                if event == 'start' and tag == 'player' and not player_name:
                    player_name = elem.get('name')
                    loc = elem.get('location', '')
                    if loc:
                        player_sector = resolve_sector_from_location(loc, sector_names)

                if event == 'start' and tag == 'faction' and elem.get('id') == 'player':
                    in_player_faction = True

                if in_player_faction and event == 'start' and tag == 'account' and not player_credits:
                    player_credits = elem.get('amount') or elem.get('balance')

                if event == 'end' and tag == 'faction' and elem.get('id') == 'player':
                    in_player_faction = False

                # ── Sector / zone tracking ─────────────────────────────────────
                # Only update when we are not inside a buffered element — there
                # are no nested sector or zone components inside a station or ship
                # in practice, so this guard is both safe and correct.
                if (not inside_station and not inside_ship
                        and not in_hb_ship and npc_station_elem_pending is None):
                    if event == 'start' and tag == 'component':
                        if comp_cls == 'sector':
                            macro    = elem.get('macro', '')
                            resolved = macro_to_sector_name(macro, sector_names)
                            if resolved:
                                # Keep the display name for station labelling and
                                # store it in the cache for O(1) ship lookups.
                                current_sector = resolved
                                sector_macro_to_name[macro] = resolved
                            # Always update the raw macro — _parse_sector() needs
                            # it even for unresolved sectors (regex fallback).
                            current_sector_macro = macro

                        elif comp_cls == 'zone':
                            current_zone_macro = elem.get('macro', '')

                    elif event == 'start' and tag == 'connection':
                        # Track the most-recent outer <connection id="NNN"> element.
                        # Ships appear as direct children of these wrappers, so the
                        # last connection id seen before a ship's opening tag is that
                        # ship's own wrapper id. We use it to build a second
                        # homebase_index key that matches the decimal-normalised form
                        # that economy log entries use for most ship references.
                        last_connection_id = elem.get('id', '')

                    elif event == 'end' and tag == 'component':
                        # Reset macro trackers on close so ships in a different
                        # sector can't accidentally inherit a stale macro.
                        if comp_cls == 'sector':
                            current_sector_macro = ""
                        elif comp_cls == 'zone':
                            current_zone_macro = ""

                # ── Station and ship detection ─────────────────────────────────
                # Guard: only detect when no buffering is already active.
                # This enforces the mutual exclusion invariant: ships inside
                # station bays (and NPC station subtrees) are not buffered here.
                if (event == 'start' and tag == 'component'
                        and not inside_station
                        and not inside_ship
                        and not in_hb_ship
                        and npc_station_elem_pending is None):

                    # ── Player station ─────────────────────────────────────────
                    # Buffer the entire subtree — production, cargo, and health
                    # data live in deep child elements that we read at close time.
                    if elem.get('owner') == 'player' and comp_cls in STATION_CLASSES:
                        inside_station         = True
                        station_elem_pending   = elem
                        station_sector_pending = current_sector

                    # ── NPC station ────────────────────────────────────────────
                    # Lightweight: data collected from start events only.
                    # Child elements are cleared by the default cleanup below.
                    elif (
                        collect_npc_stations
                        and comp_cls in STATION_CLASSES
                        and elem.get('owner', '') not in ('', 'player')
                    ):
                        npc_station_elem_pending   = elem
                        npc_station_sector_pending = current_sector
                        npc_prod_macros            = []
                        npc_wares                  = []

                    # ── Ship ──────────────────────────────────────────────────
                    # Buffer only player ships (always) and NPC ships when any
                    # tier >= 2 collection is active. We collect ALL NPC ships
                    # now and filter to context sectors after the pass, because
                    # station sectors may not be known yet when we first see an
                    # NPC ship earlier in the XML.
                    elif comp_cls in SHIP_CLASSES:
                        owner          = elem.get('owner', '')
                        is_player      = (owner == 'player')
                        is_context_npc = (owner != 'player' and collect_all_npcs)

                        if is_player or is_context_npc:
                            # Stamp both location macros onto the element now.
                            # Once inside_ship is True the current_* variables
                            # may advance, so we capture the sector/zone context
                            # at the moment this ship's opening tag was seen.
                            # Also stamp the connection wrapper id for dual-key
                            # homebase_index population at close time.
                            elem.set('_sector_macro', current_sector_macro)
                            elem.set('_zone_macro',   current_zone_macro)
                            elem.set('_conn_id',      last_connection_id)

                            inside_ship        = True
                            ship_elem_pending  = elem
                            ship_owner_pending = owner
                            ship_depth         = 1
                            # Skip the default cleanup — this element must stay
                            # in memory until its closing tag is processed.
                            continue

                        elif owner != 'player':
                            # NPC ship not being fully buffered (tier 1 / collect_all_npcs=False).
                            # Enter lightweight homebase extraction mode: track stream depth and
                            # read the default order's homebase param from start events only.
                            # No subtree stays in memory — each child is cleared on its end event.
                            in_hb_ship    = True
                            hb_ship_id    = elem.get('id', '')
                            hb_conn_id    = last_connection_id   # capture wrapper id for dual-key indexing
                            hb_depth      = 1
                            hb_in_orders  = False
                            hb_order_type = ''
                            hb_in_default = False
                            continue  # keep element in stream (children are not cleared yet)

                # ── NPC station data collection ────────────────────────────────
                # Read production macros and traded wares from START events only.
                # Using start events avoids double-counting: on the end event of
                # a child element the attributes are still accessible (before
                # elem.clear()), so checking both events would record each entry
                # twice. Starting events arrive before the element is cleared.
                if npc_station_elem_pending is not None and event == 'start':
                    if tag == 'component' and comp_cls == 'production':
                        npc_prod_macros.append(elem.get('macro', ''))
                    elif tag == 'trade' and not npc_wares and elem.get('wares'):
                        # Only the first <trade wares="..."> is the station-level
                        # ware list; inner <trade> elements have a different role.
                        npc_wares = elem.get('wares', '').split()
                    elif comp_cls in SHIP_CLASSES:
                        # Ship docked inside this NPC station — the station IS the
                        # ship's homebase. Index the ship component ID directly so
                        # the trade history counterparty resolver can find it.
                        #
                        # This is the most reliable homebase source: if a ship is
                        # physically docked inside station X, X is its homebase.
                        # The TradeRoutine/Middleman order-param approach (in_hb_ship
                        # state machine) only covers ships currently in flight; docked
                        # ships are invisible to that code because the ship detection
                        # guard requires npc_station_elem_pending is None.
                        ship_id    = elem.get('id', '')
                        station_id = npc_station_elem_pending.get('id', '')
                        if ship_id and station_id:
                            homebase_index[ship_id] = station_id

                # ── Ship buffering depth tracking ──────────────────────────────
                # Count XML nesting so we detect when the ship's closing tag
                # arrives (depth goes from 1 back to 0).
                if inside_ship:
                    if event == 'start':
                        ship_depth += 1
                    elif event == 'end':
                        ship_depth -= 1

                        if ship_depth == 0:
                            # ── Ship close — process buffered element ──────────
                            se    = ship_elem_pending
                            owner = ship_owner_pending
                            macro = se.get('macro', '')
                            code  = se.get('code',  '')
                            cls   = se.get('class', '')

                            # Fields common to both player and NPC ships.
                            sector  = _parse_sector(se, sector_names, sector_macro_to_name)
                            role    = extract_role(macro)
                            size    = SIZE_LABELS.get(cls, cls)
                            hull_f  = extract_faction_from_macro(macro)
                            order   = _parse_current_order(se)

                            # Prefer a player-given custom name; fall back to the
                            # type name derived from the macro. LANG_STRING_RE
                            # detects {page,id} refs that look like names but are
                            # actually language tokens — skip those and use the type.
                            raw_name = se.get('name')
                            if raw_name and not LANG_STRING_RE.match(raw_name):
                                name = raw_name
                            else:
                                name = resolve_ship_type(macro)

                            if owner == 'player':
                                # Full extraction for player ships: crew, software,
                                # commander link, and hull/shield health.
                                pilot = _parse_pilot(se)
                                sw    = _parse_software(se)
                                cmdr  = _parse_commander(se)

                                # Build crew roster entries.
                                if pilot["name"]:
                                    crew.append({
                                        "name":          pilot["name"],
                                        "role":          "pilot",
                                        "skills":        pilot["skills"],
                                        "assigned_to":   name,
                                        "assigned_code": code,
                                        "assigned_type": "ship",
                                        "sector":        sector,
                                    })
                                crew.extend(_extract_people(se, name, code, sector))

                                # Hull HP is absent from the save when the ship is at
                                # full health — None means undamaged, so hull_pct = 100%.
                                hull_hp  = _parse_hull(se)
                                max_hull = SHIP_STATS.get(macro, {}).get("max_hull")
                                if hull_hp is None:
                                    hull_pct = 100.0
                                elif max_hull:
                                    hull_pct = (hull_hp / max_hull) * 100.0
                                else:
                                    hull_pct = None

                                shield = _parse_shield(se)

                                player_ships.append({
                                    "code":        code,
                                    "object_id":   se.get('id', ''),
                                    "name":        name,
                                    "class":       cls,
                                    "size":        size,
                                    "macro":       macro,
                                    "role":        role,
                                    "hull_origin": hull_f,
                                    "owner":       owner,
                                    "sector":      sector,
                                    "order":       order,
                                    "pilot":       pilot,
                                    "software":    sw,
                                    "commander":   cmdr,
                                    "hull_hp":     hull_hp,
                                    "hull_pct":    hull_pct,
                                    "max_hull":    max_hull,
                                    "shield_hp":   shield["shield_hp"],
                                    "shield_max":  shield["shield_max"],
                                    "shield_pct":  shield["shield_pct"],
                                })

                                # Extract ships docked inside this carrier.
                                # They were invisible to the main loop (inside_ship
                                # blocked their detection) so we pull them from the
                                # fully-buffered subtree now, inheriting the carrier's
                                # resolved sector.
                                player_ships.extend(
                                    _extract_docked_ships(se, sector, owner)
                                )

                            else:
                                # Slim NPC record — no crew, software, or health.
                                # We only need enough to show faction activity in
                                # the relevant sectors, plus the homebase station
                                # ID for trade history counterparty resolution.
                                ship_id  = se.get('id', '')
                                homebase = _parse_homebase(se)

                                # Always populate homebase_index — even ships that
                                # get filtered out by the tier filter may be trade
                                # counterparties whose homebase we need to resolve.
                                if ship_id and homebase:
                                    # Primary key: the ship component's own hex bracket id.
                                    homebase_index[ship_id] = homebase

                                    # Secondary key: the outer <connection> wrapper's decimal
                                    # id, normalised to [0xN] hex bracket format. Economy log
                                    # entries reference ships by either the component id or the
                                    # wrapper id — we need both so counterparty resolution works
                                    # regardless of which format a given log entry uses.
                                    conn_id = se.get('_conn_id', '')
                                    if conn_id:
                                        try:
                                            homebase_index[f"[{hex(int(conn_id))}]"] = homebase
                                        except (ValueError, TypeError):
                                            pass  # wrapper id is not a plain decimal — skip

                                npc_ships.append({
                                    "code":        code,
                                    "object_id":   ship_id,
                                    "name":        name,
                                    "class":       cls,
                                    "size":        size,
                                    "macro":       macro,
                                    "role":        role,
                                    "hull_origin": hull_f,
                                    "owner":       owner,
                                    "sector":      sector,
                                    "order":       order,
                                    "homebase":    homebase,  # station object ID or None
                                })

                            # Reset buffering state and free memory.
                            inside_ship        = False
                            ship_elem_pending  = None
                            ship_owner_pending = ""
                            se.clear()
                            continue

                # ── Homebase extraction (non-buffered NPC ships) ──────────────
                # State machine for NPC ships not going through the inside_ship
                # path (i.e. when collect_all_npcs=False / tier 1). Each child
                # element is cleared on its end event — no subtree stays in memory.
                if in_hb_ship:
                    if event == 'start':
                        hb_depth += 1
                        if elem.tag == 'orders':
                            hb_in_orders = True
                        elif hb_in_orders and elem.tag == 'order' and elem.get('default') == '1':
                            hb_order_type = elem.get('order', '')
                            hb_in_default = True
                        elif hb_in_default and elem.tag == 'param' and elem.get('type') == 'component':
                            name_ = elem.get('name', '')
                            val   = elem.get('value', '')
                            if val and (
                                (hb_order_type == 'TradeRoutine' and name_ == 'range')
                                or (hb_order_type == 'Middleman'    and name_ == 'supplier')
                            ):
                                # Primary key: the ship component's own hex bracket id.
                                homebase_index[hb_ship_id] = val

                                # Secondary key: the outer <connection> wrapper's decimal
                                # id, normalised to [0xN] hex bracket format. Economy log
                                # entries reference ships by either the component id or the
                                # wrapper id — we need both so counterparty resolution works
                                # regardless of which format a given log entry uses.
                                if hb_conn_id:
                                    try:
                                        homebase_index[f"[{hex(int(hb_conn_id))}]"] = val
                                    except (ValueError, TypeError):
                                        pass  # wrapper id is not a plain decimal — skip
                    elif event == 'end':
                        hb_depth -= 1
                        if hb_depth == 0:
                            # Ship subtree is done — reset state machine.
                            in_hb_ship    = False
                            hb_ship_id    = ''
                            hb_conn_id    = ''
                            hb_in_orders  = False
                            hb_order_type = ''
                            hb_in_default = False
                        elem.clear()
                    continue  # never fall through to default cleanup while extracting

                # ── Player station close ───────────────────────────────────────
                # The identity check (elem is station_elem_pending) ensures we
                # only trigger on the exact element we started buffering, not on
                # any inner <component> closing tag.
                if event == 'end' and tag == 'component' and inside_station:
                    if elem is station_elem_pending:

                        macro     = elem.get('macro', '')
                        code      = elem.get('code', '')
                        object_id = elem.get('id', '')
                        name_attr = elem.get('name', '')
                        basename  = elem.get('basename', '')
                        nameindex = elem.get('nameindex', '')

                        # ── Station display name resolution ────────────────────
                        # Three paths, in priority order:
                        #
                        # A: Player-typed name (name attribute, not a {page,id} ref).
                        #    Used verbatim — no sector prefix or roman numeral added,
                        #    as those belong to X4's auto-name format, not player names.
                        #
                        # B: Language reference in basename / name — resolve the
                        #    {page,id} ref to get the station type string, then
                        #    prefix the sector and append a roman numeral.
                        #
                        # C: Production-based type resolution — collect all production
                        #    module macros from the buffered subtree and call
                        #    resolve_station_type(), which picks the highest-priority
                        #    ware group across all modules.
                        if name_attr:
                            display_name = name_attr
                        else:
                            display_name = ''

                            if basename:
                                resolved_text = resolve_text_ref(basename, texts)
                                if resolved_text and not resolved_text.startswith('{'):
                                    display_name = resolved_text

                            if not display_name:
                                prod_macros  = [
                                    comp.get('macro', '')
                                    for comp in elem.iter('component')
                                    if comp.get('class') == 'production'
                                ]
                                display_name = resolve_station_type(prod_macros, texts)

                            if not display_name:
                                if 'headquarters' in macro.lower():
                                    display_name = "Headquarters"
                                else:
                                    display_name = "Unnamed Station"

                            # Auto-name format: "{Sector} {Type} {Roman}".
                            # e.g. "The Void High Tech Factory II".
                            if display_name not in ("Unnamed Station",):
                                roman = nameindex_to_roman(nameindex) if nameindex else ''
                                if roman:
                                    display_name = f"{display_name} {roman}"
                                if station_sector_pending:
                                    display_name = f"{station_sector_pending} {display_name}"

                        production   = parse_production_from_construction(elem)
                        module_count = _count_construction_modules(elem)
                        modules      = _parse_station_modules(elem)
                        health       = _parse_station_health(modules)
                        storage      = _parse_station_storage(elem)
                        docked_ships = _extract_station_docked_ships(elem)

                        raw_state = elem.get('state')
                        status    = _STATE_LABELS.get(raw_state, "Operational")

                        entry = {
                            "name":          display_name,
                            "code":          code,
                            "object_id":     object_id,
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

                        # De-duplicate by code — the same station can appear in
                        # multiple zones (docked modules in adjacent zones) but
                        # the code attribute is unique per logical station.
                        if not any(s["code"] == code for s in stations):
                            stations.append(entry)

                            mgr = _parse_manager(elem)
                            if mgr:
                                managers.append({
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
                        station_sector_pending = ""
                        elem.clear()
                        continue

                # ── NPC station close ──────────────────────────────────────────
                # The identity check (elem is npc_station_elem_pending) ensures
                # we react only to the NPC station's own closing tag, not any
                # inner component that happens to share the 'component' tag name.
                # Child elements were cleared normally by the default cleanup,
                # so only the station element's own attributes remain here —
                # exactly what we need.
                if (event == 'end' and tag == 'component'
                        and npc_station_elem_pending is not None
                        and elem is npc_station_elem_pending):

                    owner    = elem.get('owner', '')
                    code     = elem.get('code', '')
                    raw_name = resolve_text_ref(
                        elem.get('name', '') or elem.get('basename', ''),
                        texts,
                    )
                    type_name = raw_name or resolve_station_type(npc_prod_macros, texts)
                    display   = _build_npc_display_name(
                        type_name,
                        elem.get('nameindex', '0'),
                        code,
                        owner,
                    )
                    wares_display = sorted(
                        WARE_NAMES.get(w, w.replace('_', ' ').title())
                        for w in npc_wares
                    )
                    npc_stations_raw.append({
                        'name':      display,
                        'owner':     owner,
                        'sector':    npc_station_sector_pending,
                        'code':      code,
                        'object_id': elem.get('id', ''),
                        'macro':     elem.get('macro', ''),
                        'wares':     wares_display,
                    })

                    npc_station_elem_pending   = None
                    npc_station_sector_pending = ""
                    npc_prod_macros            = []
                    npc_wares                  = []
                    elem.clear()
                    continue

                # ── Default cleanup ────────────────────────────────────────────
                # Free any element we are not actively buffering. This is what
                # keeps RAM usage flat on 700MB+ save files. The in_hb_ship check
                # is handled by the state machine's own elem.clear() above.
                if event == 'end' and not inside_station and not inside_ship and not in_hb_ship:
                    elem.clear()

    except ET.XMLSyntaxError as e:
        print(f"\n[XML Error] Save file has a formatting issue: {e}")
        raise

    # ── Post-pass NPC ship filtering ───────────────────────────────────────────
    # We couldn't filter NPC ships mid-stream because station sectors weren't
    # fully known until the entire file had been read. Now we can apply the tier
    # filter in a single in-memory pass over the (already-slim) NPC ship list.
    if ship_tier == 1:
        # Tier 1: player ships only — discard any NPC records (there shouldn't
        # be any since collect_all_npcs was False, but belt-and-suspenders).
        npc_ships = []

    elif ship_tier == 2:
        # Tier 2: keep NPC ships only in sectors where the player has a station.
        station_sectors = {s["sector"] for s in stations}
        npc_ships = [s for s in npc_ships if s["sector"] in station_sectors]

    elif ship_tier >= 3:
        # Tier 3: keep NPC ships in any sector where the player has a presence
        # (station OR ship). Player ship sectors are now fully known.
        station_sectors = {s["sector"] for s in stations}
        ship_sectors    = {s["sector"] for s in player_ships}
        context         = station_sectors | ship_sectors
        npc_ships       = [s for s in npc_ships if s["sector"] in context]

    # ── Summary ────────────────────────────────────────────────────────────────
    tier_npc_str = f", {len(npc_ships)} NPC ship(s)" if ship_tier >= 2 else ""
    npc_st_str   = f", {len(npc_stations_raw)} NPC station(s)" if collect_npc_stations else ""
    print(
        f"[Scanning] Combined — {len(stations)} station(s){npc_st_str}, "
        f"{len(player_ships)} player ship(s){tier_npc_str}. "
        f"Homebase index: {len(homebase_index)} NPC ship(s)."
    )

    result: dict = {
        # Station scanner outputs
        "player_name":    player_name,
        "player_credits": player_credits,
        "player_sector":  player_sector,
        "stations":       stations,
        "reputation":     [],   # filled by reputation_scanner in a separate pass
        "managers":       managers,
        # Ship scanner outputs (kept separate from stations so caller can
        # assemble game_data["ships"] = {...} in the expected nested format)
        "player_ships":   player_ships,
        "npc_ships":      npc_ships,
        "crew":           crew,
        # Internal plumbing — caller must pop these before game_data.update()
        "sector_macro_to_name": sector_macro_to_name,
        # ship_id → homebase station object ID for ALL NPC ships seen in the file.
        # Includes ships filtered out by the tier filter — used for trade history
        # counterparty resolution where the ship may have left the player's sector.
        "homebase_index": homebase_index,
    }

    if collect_npc_stations:
        # Unfiltered — caller applies the player-sector filter after this call.
        result["npc_stations_raw"] = npc_stations_raw

    return result
