# Core role: Single-pass streaming XML parser that coordinates save file extraction across domain-specific handlers.

from __future__ import annotations
from pathlib import Path
from lxml.etree import iterparse as lxml_iterparse

from .context import ScanContext, ComponentFrame, STATION_CLASSES, SHIP_CLASSES
from .language import open_save, load_language_root, load_sector_names, load_text_pages, resolve_sector_from_location
from .handlers.station     import StationHandler
from .handlers.ship        import ShipHandler, EQUIPMENT_CLASSES
from .handlers.reputation  import ReputationHandler
from .handlers.trade       import TradeHandler
from .handlers.economy     import EconomyHandler
from .handlers.npc_station import NpcStationHandler
from .handlers.sector      import SectorHandler
from .handlers.gate        import GateHandler
from .handlers.resource    import ResourceHandler
from .handlers.combat      import CombatHandler
from .handlers.events      import EventLogHandler


# Every tag any handler dispatches on, across _on_component_start/_on_element_start/
# _on_element_end below AND ResourceHandler's own tag checks (it runs off the raw tag
# string too, not through the elif chains here). Passed to iterparse's tag= filter so
# the parser never surfaces a start/end event for the many tags nothing reads (weapon,
# physics, connections, ownership, ...) — those elements are still built into the tree
# (filtering doesn't affect tree construction, only which events reach this loop), so
# buffered subtree walks and elem.clear() on an ancestor still see/free everything.
# Keep this in sync with any new elif tag == '...' branch added to this file or to
# ResourceHandler; a tag left out here never reaches its handler.
_DISPATCHED_TAGS = (
    'game', 'component',
    'resourceareas', 'player', 'account', 'faction', 'relations', 'relation',
    'booster', 'log', 'stat', 'entry', 'removed', 'object', 'aidirector',
    'vars', 'value', 'order', 'param', 'trade',
    'area', 'wares', 'yields', 'ware', 'recharge', 'yield',
)


class Scanner:
    """Single-pass save file coordinator.

    Responsibilities:
      - Open save file, drive iterparse, manage component stack, dispatch events, return populated context
      - Domain knowledge lives in handlers; only knows <component> (push/pop stack) and <game> (game_time_s)

    Buffering strategy: some handlers need the full subtree in memory at close time.
    When buffer_depth is set, child elements are kept in memory until the buffer root closes.
    Buffered: all stations (player/NPC), player ships. Not buffered: NPC ships (top-level attributes only).
    """

    def __init__(self, lang_path: Path | None = None) -> None:
        # Load language file once; lang_path is a manual override if it exists.
        lang_root    = load_language_root(lang_path)
        sector_names = load_sector_names(lang_root)
        # Pages: 20102=station basename refs, 20215=factory categories (resolve_station_type),
        # 20203=faction names (resolve {20203,N} refs on combat-kill log entries).
        texts = load_text_pages(lang_root, {20102, 20215, 20203})

        self._station = StationHandler(sector_names, texts)
        self._ship    = ShipHandler()
        self._rep     = ReputationHandler()
        self._trade   = TradeHandler()
        self._economy = EconomyHandler()
        self._npc     = NpcStationHandler(texts)
        self._sector  = SectorHandler(sector_names)
        self._gate    = GateHandler()
        self._resource = ResourceHandler()
        self._combat  = CombatHandler(texts)
        self._events  = EventLogHandler(texts)

        # Stored for handlers that need them during scan (ship, station).
        self._sector_names = sector_names
        self._texts        = texts

    def scan(self, save_path: str | Path, scan_id: int) -> ScanContext:
        """Parse save_path in single pass; return populated ScanContext.

        scan_id assigned by caller (DB auto-increment or counter); Scanner has no persistence dependency.
        """
        save_path = Path(save_path)
        ctx = ScanContext(scan_id=scan_id, save_file=save_path.name)

        with open_save(save_path) as f:
            # None=streaming (elements cleared); int=buffer depth (child elements kept in memory)
            buffer_depth: int | None = None

            for event, elem in lxml_iterparse(f, events=('start', 'end'), tag=_DISPATCHED_TAGS):
                tag = elem.tag

                # ── Save metadata (line ~5 of every save file) ────────────
                if tag == 'game' and event == 'start':
                    try:
                        ctx.game_time_s = float(elem.get('time', 0))
                    except (ValueError, TypeError):
                        pass
                    elem.clear()
                    continue

                # ── Component stack management ────────────────────────────
                if tag == 'component':
                    if event == 'start':
                        frame = ComponentFrame(
                            object_id = elem.get('id',    ''),
                            cls       = elem.get('class', ''),
                            macro     = elem.get('macro', ''),
                            owner     = elem.get('owner', ''),
                        )
                        ctx.push(frame)

                        # Start buffering if component needs subtree walk at close (not already buffering).
                        if buffer_depth is None:
                            if frame.cls in STATION_CLASSES:
                                buffer_depth = ctx.depth
                            elif frame.cls in SHIP_CLASSES and frame.owner == 'player':
                                buffer_depth = ctx.depth
                            elif frame.cls == 'gate':
                                # Gates have pairing connection ids as children, not attributes
                                buffer_depth = ctx.depth

                        # Dispatch start. Skip if inside buffered subtree (parent handler walks children).
                        if buffer_depth is None or ctx.depth == buffer_depth:
                            self._on_component_start(frame, elem, ctx)

                    else:  # end
                        frame = ctx.top

                        if buffer_depth is not None and ctx.depth == buffer_depth:
                            # Closing buffer root with full subtree in memory. Hand to handler, release buffer.
                            self._on_buffered_end(frame, elem, ctx)
                            buffer_depth = None
                            ctx.pop()
                            elem.clear()

                        elif buffer_depth is None:
                            # Normal streaming mode
                            ctx.pop()
                            elem.clear()

                        else:
                            # Nested inside buffer; don't clear (parent handler needs to walk it).
                            ctx.pop()

                    continue

                # ── Non-component elements ────────────────────────────────
                # Inside buffer: skip dispatch, don't clear (parent handler walks during on_end).
                if buffer_depth is not None:
                    continue

                # Outside buffer: dispatch events. Clear only on END to keep attributes available.
                if event == 'start':
                    self._on_element_start(tag, elem, ctx)
                elif event == 'end':
                    self._on_element_end(tag, elem, ctx)
                    elem.clear()

        return ctx

    # ── Private dispatch ──────────────────────────────────────────────────────

    def _on_component_start(
        self, frame: ComponentFrame, elem, ctx: ScanContext
    ) -> None:
        """Dispatch component start (outside buffered subtree). Handlers get attributes only (children not yet parsed)."""
        if frame.cls in STATION_CLASSES:
            if frame.owner == 'player':
                self._station.on_start(elem, ctx)
            else:
                self._npc.on_start(elem, ctx)

        elif frame.cls in SHIP_CLASSES:
            # Player ships buffer for on_end(); NPC ships stream (top-level only).
            self._ship.on_start(elem, ctx)

        elif frame.cls == 'sector':
            # All data on opening tag
            self._sector.on_sector(elem, ctx)

        elif frame.cls == 'gate':
            # Capture attributes + sector; connection ids read from buffered subtree at on_end()
            self._gate.on_start(elem, ctx)

        elif frame.cls == 'buildstorage' and frame.owner == 'player':
            # Buildstorages tracked separately from stations to avoid misclassifying NPC purchases
            ctx.player_buildstorage_ids.add(frame.object_id)

        elif frame.cls in EQUIPMENT_CLASSES:
            # Streaming NPC-ship equipment. Only reachable for non-buffered ships
            # (player ship/station equipment is inside a buffer, never dispatched),
            # so this can't double-count with _parse_loadout()'s buffered walk.
            self._ship.on_npc_equipment(frame, ctx)

    def _on_buffered_end(
        self, frame: ComponentFrame | None, elem, ctx: ScanContext
    ) -> None:
        """Dispatch buffered component close. elem has complete subtree; handler extracts and appends to ctx."""
        if frame is None:
            return

        if frame.cls in STATION_CLASSES:
            if frame.owner == 'player':
                self._station.on_end(elem, ctx)
                # Extract docked ships (nested in buffered subtree, never seen by main loop)
                self._ship.extract_station_docked_ships(elem, ctx)
            else:
                self._npc.on_end(elem, ctx)
                self._ship.extract_npc_docked_ships(elem, frame.object_id, ctx)

        elif frame.cls in SHIP_CLASSES and frame.owner == 'player':
            self._ship.on_end(elem, ctx)

        elif frame.cls == 'gate':
            self._gate.on_end(elem, ctx)

    def _on_element_start(
        self, tag: str, elem, ctx: ScanContext
    ) -> None:
        """Dispatch non-component start events (outside buffered section). Handlers check context themselves."""
        # Sector <resourceareas> state machine (owns area/wares/ware/recharge/yields/yield children).
        if tag == 'resourceareas' or self._resource.active:
            self._resource.on_start(tag, elem, ctx)
            return

        if tag == 'player' and not ctx.player_name:
            ctx.player_name = elem.get('name', '')
            loc = elem.get('location', '')
            if loc:
                ctx.player_sector = resolve_sector_from_location(
                    loc, self._sector_names
                )

        elif tag == 'account' and self._rep._active:
            # Player faction cash (<account> inside <faction id="player"> block)
            if not ctx.player_credits:
                try:
                    ctx.player_credits = int(
                        elem.get('amount') or elem.get('balance') or 0
                    )
                except (ValueError, TypeError):
                    pass

        elif tag == 'faction':
            # Faction block (reputation + faction_relations; visitor/role-label factions ignored)
            self._rep.on_faction_start(elem, ctx)

        elif tag == 'relations':
            # Wrapper of a faction's standing entries — carries locked="1" on
            # factions whose relations the game never changes (Xenon, Kha'ak).
            self._rep.on_relations(elem, ctx)

        elif tag == 'relation':
            # Base standing entry inside a faction's <relations> block.
            self._rep.on_relation(elem, ctx)

        elif tag == 'booster':
            # Temporary reputation bonus inside a faction's <relations> block.
            self._rep.on_booster(elem, ctx)

        elif tag == 'log':
            # Completed-trade rows in the global economy log
            # (<entries type="trade"><log type="trade" .../></entries>).
            # EconomyHandler harvests raw rows; classification/resolution is
            # deferred to the post-processor (id indexes aren't final yet here).
            self._economy.on_log(elem, ctx)

        elif tag == 'stat':
            # Savegame statistics row (<stats><stat id="..." value="..."/>).
            # CombatHandler keeps ships_destroyed for the Trends chart;
            # EventLogHandler keeps every numeric stat as a career stat.
            self._combat.on_stat(elem, ctx)
            self._events.on_stat(elem, ctx)

        elif tag == 'entry':
            # Player event-log row. CombatHandler tallies the "Destroyed Enemy"
            # reputation entries by faction; EventLogHandler records the row
            # itself (news, missions, alerts, upkeep, …) as a PlayerEvent.
            self._combat.on_entry(elem, ctx)
            self._events.on_entry(elem, ctx)

        elif tag == 'removed':
            # Open an <economylog><removed> block — despawned objects whose ids
            # appear as buyer/seller in trade rows.
            self._economy.on_removed_start(elem, ctx)

        elif tag == 'object':
            # Despawned object label inside a <removed> block. EconomyHandler
            # guards on its own in-removed flag, so this is a cheap no-op for
            # the many other <object> elements elsewhere in the save.
            self._economy.on_object(elem, ctx)

        elif tag == 'aidirector':
            # Opening the AI director section — arm aidirector streaming in
            # EconomyHandler so it can capture mid-delivery NPC ship destinations.
            self._economy.on_aidirector_start(elem, ctx)

        elif tag == 'vars':
            # Start of a <vars> block inside the aidirector. Resets the
            # per-block $thisship / $destination / $trading accumulators.
            self._economy.on_vars_start(elem, ctx)

        elif tag == 'value':
            # A script variable inside a <vars> block. EconomyHandler picks out
            # $thisship, $destination, and $trading; ignores everything else.
            self._economy.on_value(elem, ctx)

        elif tag == 'order':
            # Order element streaming past — used by ShipHandler to detect an
            # active DockAt delivery on a non-buffered NPC ship. The handler
            # no-ops unless we are currently inside the NPC ship it armed.
            self._ship.on_npc_order(elem, ctx)

        elif tag == 'param':
            # Param of an NPC ship's active DockAt order (destination / trading).
            # Same gating as on_npc_order — cheap no-op outside an NPC ship.
            self._ship.on_npc_param(elem, ctx)

        elif tag == 'trade':
            # Active trade orders outside buffered sections (NPC stations, free
            # orders). Player-station orders are inside buffered elements and
            # are handled by StationHandler's tree walk.
            self._trade.on_trade(elem, ctx)

    def _on_element_end(
        self, tag: str, elem, ctx: ScanContext
    ) -> None:
        """
        Dispatch end events for non-component elements that need finalisation.

        Only called outside buffered sections. Used by handlers that accumulate
        data across multiple child elements and need to know when the parent
        closes — e.g. ReputationHandler waits for </faction> to build entries.
        """
        # Resource subtree end events: section resets and the final flush on
        # </resourceareas>. Mirrors the short-circuit in _on_element_start.
        if tag == 'resourceareas' or self._resource.active:
            self._resource.on_end(tag, elem, ctx)
            return

        if tag == 'faction':
            self._rep.on_faction_end(elem, ctx)

        elif tag == 'removed':
            # Close the <economylog><removed> block.
            self._economy.on_removed_end(elem, ctx)

        elif tag == 'aidirector':
            self._economy.on_aidirector_end(elem, ctx)

        elif tag == 'vars':
            # Commit the accumulated $Ship/$destination/$Ware triple (if present)
            # to delivery_dest_index.
            self._economy.on_vars_end(elem, ctx)
