from __future__ import annotations
from pathlib import Path
from lxml.etree import iterparse as lxml_iterparse

from .context import ScanContext, ComponentFrame, STATION_CLASSES, SHIP_CLASSES
from .language import open_save, load_sector_names, load_text_pages, resolve_sector_from_location
from .handlers.station     import StationHandler
from .handlers.ship        import ShipHandler
from .handlers.reputation  import ReputationHandler
from .handlers.trade       import TradeHandler
from .handlers.economy     import EconomyHandler
from .handlers.crew        import CrewHandler
from .handlers.npc_station import NpcStationHandler
from .handlers.sector      import SectorHandler


class Scanner:
    """
    Single-pass save file coordinator.

    Responsibilities — and nothing beyond these:
      - Open the save file via open_save()
      - Drive the lxml iterparse loop
      - Manage the component stack on ScanContext
      - Dispatch element events to the right handler
      - Return the populated ScanContext when done

    All domain knowledge (what data to extract, how to parse it) lives in the
    handlers. This class only knows about two structural concerns:
      1. <component> — every component tag is pushed/popped on the stack
      2. <game>       — game_time_s is read here and stored on the context

    BUFFERING STRATEGY
    ------------------
    Some handlers need the full XML subtree of a component to be in memory
    when that component closes (e.g. StationHandler walks the station tree
    to extract modules, cargo, and budget in one pass).

    When iterparse enters a bufferable component, buffer_depth is set to the
    current stack depth. While inside that depth, child elements are NOT
    cleared — they stay attached to the parent in memory. When iterparse closes
    the root of that buffered section, the full element is handed to the handler
    via on_end(), then cleared.

    Buffered:     all stations (player and NPC), player ships
    Not buffered: NPC ships — only top-level attributes are needed
    """

    def __init__(self, lang_path: Path | None = None) -> None:
        # Load sector names once at startup. All handlers that need to resolve
        # a sector macro to a human name receive the same pre-built dict.
        # Defaults to the standard project-root location of the language file.
        _lang_path   = lang_path or Path('0001-l044.xml')
        sector_names = load_sector_names(_lang_path)

        # Pages needed by NpcStationHandler (and later StationHandler):
        #   20102 — station basename text refs  e.g. "{20102,1301}" → "Advanced Electronics"
        #   20215 — factory category names used by resolve_station_type()
        texts = load_text_pages(_lang_path, {20102, 20215})

        self._station = StationHandler(sector_names, texts)
        self._ship    = ShipHandler()
        self._rep     = ReputationHandler()
        self._trade   = TradeHandler()
        self._economy = EconomyHandler()
        self._crew    = CrewHandler()
        self._npc     = NpcStationHandler(texts)
        self._sector  = SectorHandler(sector_names)

        # Stored for handlers that need them during scan (ship, station).
        self._sector_names = sector_names
        self._texts        = texts

    def scan(self, save_path: str | Path, scan_id: int) -> ScanContext:
        """
        Parse save_path in a single pass and return a fully populated
        ScanContext.

        scan_id is assigned by the caller (DB auto-increment or a simple
        counter for CLI-only runs) — the Scanner has no persistence dependency.
        """
        save_path = Path(save_path)
        ctx = ScanContext(scan_id=scan_id, save_file=save_path.name)

        with open_save(save_path) as f:
            # When None: streaming normally — elements are cleared after use.
            # When int: we are inside a buffered component at that stack depth.
            # Child elements at greater depth are kept in memory for the handler.
            buffer_depth: int | None = None

            for event, elem in lxml_iterparse(f, events=('start', 'end')):
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

                        # Start buffering if this component needs a subtree
                        # walk at close time. Only starts when we are NOT
                        # already buffering — nested components are covered by
                        # the outer buffer.
                        if buffer_depth is None:
                            if frame.cls in STATION_CLASSES:
                                # All stations — player and NPC — are buffered.
                                # NPC stations need trade offer children for
                                # ware extraction; player stations need modules
                                # and cargo children for budget calculations.
                                buffer_depth = ctx.depth
                            elif frame.cls in SHIP_CLASSES and frame.owner == 'player':
                                # Player ships only. NPC ships are streamed with
                                # top-level attributes — no subtree walk needed.
                                buffer_depth = ctx.depth

                        # Dispatch component start. When we are already inside
                        # a buffered subtree, skip — the parent handler processes
                        # nested components itself via tree walk on end.
                        if buffer_depth is None or ctx.depth == buffer_depth:
                            self._on_component_start(frame, elem, ctx)

                    else:  # end
                        frame = ctx.top

                        if buffer_depth is not None and ctx.depth == buffer_depth:
                            # Closing the buffer root — the full subtree is
                            # still in memory. Hand it to the handler, then
                            # release the buffer and clear.
                            self._on_buffered_end(frame, elem, ctx)
                            buffer_depth = None
                            ctx.pop()
                            elem.clear()

                        elif buffer_depth is None:
                            # Normal streaming — clear after processing.
                            ctx.pop()
                            elem.clear()

                        else:
                            # Nested component inside a buffered section.
                            # Do NOT clear — the buffered root's on_end handler
                            # needs to walk this element. Just pop the frame.
                            ctx.pop()

                    continue

                # ── Non-component elements ────────────────────────────────
                # Inside a buffered subtree: skip dispatch and do NOT clear.
                # The buffered handler walks children during its on_end() call.
                if buffer_depth is not None:
                    continue

                # Outside a buffered section: dispatch start and end events.
                # Only clear on END so that element attributes remain available
                # across the full start→end lifetime (e.g. <faction id="player">
                # must still have its id attribute when on_faction_end fires).
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
        """
        Dispatch for component start events that are not inside a buffered
        subtree. Handlers receive only the component's own attributes here —
        children have not been parsed yet.
        """
        if frame.cls in STATION_CLASSES:
            if frame.owner == 'player':
                self._station.on_start(elem, ctx)
            else:
                self._npc.on_start(elem, ctx)

        elif frame.cls in SHIP_CLASSES:
            # Player ships trigger buffering and will get on_end() later.
            # NPC ships are not buffered — this is their only dispatch point.
            self._ship.on_start(elem, ctx)

        elif frame.cls == 'sector':
            # All sector data is on the opening tag — no buffering needed.
            self._sector.on_sector(elem, ctx)

    def _on_buffered_end(
        self, frame: ComponentFrame | None, elem, ctx: ScanContext
    ) -> None:
        """
        Dispatch for the closing tag of a buffered component. elem still has
        its complete subtree intact. The handler extracts everything it needs
        and appends results to ctx before returning.
        """
        if frame is None:
            return

        if frame.cls in STATION_CLASSES:
            if frame.owner == 'player':
                self._station.on_end(elem, ctx)
            else:
                self._npc.on_end(elem, ctx)

        elif frame.cls in SHIP_CLASSES and frame.owner == 'player':
            self._ship.on_end(elem, ctx)

    def _on_element_start(
        self, tag: str, elem, ctx: ScanContext
    ) -> None:
        """
        Dispatch for non-component start events outside any buffered section.
        Each handler does its own context check before doing any work, so it
        is safe to always call through — unrecognised contexts are simply
        ignored by the handler.
        """
        if tag == 'player' and not ctx.player_name:
            # <player name="..." location="..."> appears once near the top.
            ctx.player_name = elem.get('name', '')
            loc = elem.get('location', '')
            if loc:
                ctx.player_sector = resolve_sector_from_location(
                    loc, self._sector_names
                )

        elif tag == 'account' and self._rep._active:
            # Player faction cash account — <account amount="..."> inside the
            # <faction id="player"> block. RepHandler._active is True only
            # while we're inside that block.
            if not ctx.player_credits:
                try:
                    ctx.player_credits = int(
                        elem.get('amount') or elem.get('balance') or 0
                    )
                except (ValueError, TypeError):
                    pass

        elif tag == 'faction':
            # Opening tag of a faction block — RepHandler checks if it's the
            # player faction and starts collecting if so.
            self._rep.on_faction_start(elem, ctx)

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

        elif tag == 'removed':
            # Open an <economylog><removed> block — despawned objects whose ids
            # appear as buyer/seller in trade rows.
            self._economy.on_removed_start(elem, ctx)

        elif tag == 'object':
            # Despawned object label inside a <removed> block. EconomyHandler
            # guards on its own in-removed flag, so this is a cheap no-op for
            # the many other <object> elements elsewhere in the save.
            self._economy.on_object(elem, ctx)

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

        elif tag == 'npc':
            # Crew elements outside buffered sections. Player ship/station crew
            # is inside buffered elements; this fires for NPC ship crew.
            # CrewHandler checks ctx.top.owner before doing any work.
            self._crew.on_npc(elem, ctx)

    def _on_element_end(
        self, tag: str, elem, ctx: ScanContext
    ) -> None:
        """
        Dispatch end events for non-component elements that need finalisation.

        Only called outside buffered sections. Used by handlers that accumulate
        data across multiple child elements and need to know when the parent
        closes — e.g. ReputationHandler waits for </faction> to build entries.
        """
        if tag == 'faction':
            self._rep.on_faction_end(elem, ctx)

        elif tag == 'removed':
            # Close the <economylog><removed> block.
            self._economy.on_removed_end(elem, ctx)
