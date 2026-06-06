from __future__ import annotations
from dataclasses import dataclass, field

from .entities import (
    Station, NpcStation, Ship, CrewMember, ReputationEntry, Sector,
    ActiveTrade, ActiveAutoTrade,
    TradeHistory, TradeHistoryMining, TradeHistoryInternal,
)

# Verified against save_001.xml.
# All stations in the save use class="station". The additional values
# ("factory", "headquarters", "complex") appear in v1's scanner and may occur
# in saves with the player HQ or certain DLC content — kept for safety.
STATION_CLASSES: frozenset[str] = frozenset({"station", "factory", "headquarters", "complex"})

# Verified against save_001.xml — exactly these four size classes exist.
SHIP_CLASSES: frozenset[str] = frozenset({"ship_s", "ship_m", "ship_l", "ship_xl"})


# ─────────────────────────────────────────────────────────────────────────────
#  COMPONENT FRAME  (one entry on the stack)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ComponentFrame:
    """
    Represents one <component> element on the parse stack.

    Pushed when iterparse fires a 'start' event for <component>.
    Popped when iterparse fires the matching 'end' event.

    Handlers inspect the stack to know what context they are currently inside
    (e.g. "am I inside a player station?") without needing their own flags.
    """
    object_id: str   # hex component ID e.g. "[0x4f44]"
    cls:       str   # element class e.g. "ship_m", "station", "storage"
    macro:     str   # raw macro ID e.g. "ship_arg_m_fighter_01_a_macro"
    owner:     str   # "player" or a faction ID e.g. "argon"


# ─────────────────────────────────────────────────────────────────────────────
#  SCAN CONTEXT  (shared state — passed to every handler)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ScanContext:
    """
    Shared state object for the entire scan.

    The Scanner coordinator creates one ScanContext per scan and passes it to
    every handler. Handlers read from it (for context) and write to it (to
    accumulate results). Nothing is returned from individual handlers — all
    output flows through this object.

    Three distinct sections:
      1. Parse-time state   — changes moment to moment as iterparse progresses
      2. Accumulated results — entity lists built up during the scan
      3. Cross-handler refs  — data one handler builds that another handler needs
    """

    # ── Scan metadata ─────────────────────────────────────────────────────────
    # Set once before the scan starts; every entity records these as FK / anchor.

    scan_id:     int   # FK on every entity table — identifies this scan
    save_file:   str   # filename e.g. "save_003.xml.gz"

    # Read from the save XML near the top of the file, before any entities.
    # Anchors the time_ago_s calculation on every trade record.
    game_time_s: float = 0.0

    # Player identity — populated early in the parse from <player> and
    # <faction id="player"><account> elements. Written to the Scan record
    # after the parse completes.
    player_name:    str = ''
    player_credits: int = 0
    player_sector:  str = ''


    # ── Parse-time state ──────────────────────────────────────────────────────
    # These fields change every time iterparse moves to a new element.
    # Handlers must never hold on to these after their event handler returns.

    # Full component nesting stack — see ComponentFrame above.
    component_stack: list[ComponentFrame] = field(default_factory=list)

    # Tracks the most recently entered sector macro. Updated by SectorHandler
    # each time a sector component is processed. All station and ship handlers
    # read this instead of walking the stack — the stack depth between a sector
    # and its child stations/ships varies (zones and other components also push
    # frames), so frame_at(1) is unreliable for sector resolution.
    current_sector_macro: str = ''

    # The entity object currently being built. Set by a handler when it opens a
    # relevant component; cleared when the closing </component> is processed.
    current_station:     Station     | None = None
    current_ship:        Ship        | None = None
    current_npc_station: NpcStation  | None = None


    # ── Accumulated results ───────────────────────────────────────────────────
    # Appended to throughout the scan. Read in full by the post-processor and
    # then the exporter once the parse is complete.

    stations:               list[Station]               = field(default_factory=list)
    ships:                  list[Ship]                  = field(default_factory=list)
    crew:                   list[CrewMember]            = field(default_factory=list)
    reputation:             list[ReputationEntry]       = field(default_factory=list)
    sectors:                list[Sector]                = field(default_factory=list)
    npc_stations:           list[NpcStation]            = field(default_factory=list)
    active_trades:          list[ActiveTrade]           = field(default_factory=list)
    active_auto_trades:     list[ActiveAutoTrade]       = field(default_factory=list)
    trade_history:          list[TradeHistory]          = field(default_factory=list)
    trade_history_mining:   list[TradeHistoryMining]    = field(default_factory=list)
    trade_history_internal: list[TradeHistoryInternal]  = field(default_factory=list)


    # ── Cross-handler reference data ──────────────────────────────────────────
    # Built by one handler early in the parse; read by another handler later.
    # This is safe because the XML stream guarantees stations and ships appear
    # before their associated trade records.

    # StationHandler → EconomyHandler, TradeHandler
    # Needed to classify whether a trade involves a player station.
    player_station_ids: set[str] = field(default_factory=set)

    # Scanner → post-processor
    # Player-owned construction platforms (class="buildstorage"). These are NOT
    # production stations and do not trade with the market, but energy cell sales
    # from a player station module to a buildstorage are internal player transfers.
    # Kept separate from player_station_ids so their NPC purchases (construction
    # materials bought from despawned/NPC sellers) are not misclassified as player
    # station "In" trades.
    player_buildstorage_ids: set[str] = field(default_factory=set)

    # ShipHandler → TradeHandler
    # Needed to classify whether a transport ship is player-owned.
    player_ship_ids: set[str] = field(default_factory=set)

    # NpcStationHandler → post-processor (counterparty resolution)
    # Maps object_id → NpcStation for O(1) counterparty lookup after the scan.
    npc_station_index: dict[str, NpcStation] = field(default_factory=dict)

    # ShipHandler → post-processor (homebase attribution)
    # Maps ship object_id → station object_id so the post-processor can attach
    # homebase names to ships and group fleets without a second file read.
    homebase_index: dict[str, str] = field(default_factory=dict)

    # ShipHandler → post-processor (in-progress delivery resolution)
    # Maps ship object_id → destination station object_id for ships that are
    # mid-delivery at save time (an active, started DockAt order flagged
    # trading="1"). Used to name the counterparty for a courier that has picked
    # up cargo from a player station but whose commercial SELL leg has not been
    # logged yet — that trade lives in "in-progress deliveries", not history.
    delivery_dest_index: dict[str, str] = field(default_factory=dict)

    # ShipHandler → trade name resolution
    # Maps ship code → ship display name. Trade records reference ships by code;
    # this index resolves names without a separate lookup table.
    npc_ship_codes: dict[str, str] = field(default_factory=dict)

    # EconomyHandler → TradePostProcessor
    # Raw completed-trade rows harvested from the economy log during the scan.
    # Deliberately NOT classified or resolved here: a player ship can appear in
    # the file AFTER the trade-log block (e.g. docked at the HQ near the end), so
    # the id indexes (player_ship_ids, homebase_index, …) are not guaranteed
    # complete at log time. The post-processor classifies and resolves these once
    # the full parse is done and every index is final. Each row is a dict:
    #   buyer, seller (normalised ids), ware, amount, price_cr, game_time_s, time_ago_s
    trade_log: list[dict] = field(default_factory=list)

    # EconomyHandler → TradePostProcessor
    # Despawned economy objects listed in <economylog><removed>. Their plain
    # decimal ids appear as buyer/seller in some trade rows; this maps the
    # normalised id to a readable "Name [CODE]" label so those rows still resolve
    # to a human-meaningful party instead of a raw hex id.
    removed_codes: dict[str, str] = field(default_factory=dict)

    # ShipHandler → TradePostProcessor (NPC ships docked at NPC stations)
    # Maps ship object_id → (code, macro, npc_station_id) for every NPC ship
    # found inside a buffered NPC station subtree at scan time.
    #
    # WHY THIS EXISTS: ships docked at NPC stations are invisible to on_start()
    # because the scanner suppresses dispatch inside buffered sections. They never
    # reach ctx.ships, so ship_by_id and delivery_dest_index both miss them.
    # Capturing them here gives the postprocessor two things:
    #   1. name resolution  — code + macro → display name
    #   2. counterparty     — the station they are physically sitting in is the
    #                         most direct evidence of where goods were delivered
    npc_docked_ships: dict[str, tuple] = field(default_factory=dict)

    # StationHandler + NpcStationHandler → EconomyHandler (aidirector resolution)
    # Maps every sub-component id found inside a buffered station subtree to the
    # parent station's object_id — e.g. pier ids, docking bay ids.
    #
    # WHY THIS EXISTS: the Faction AI Econ_Manager stores its trade assignment's
    # $destination as the specific docking bay component, not the station itself.
    # This index lets EconomyHandler resolve that bay id to its parent station
    # when populating delivery_dest_index from aidirector script vars.
    dockingbay_index: dict[str, str] = field(default_factory=dict)


    # ── Stack helpers ─────────────────────────────────────────────────────────

    @property
    def top(self) -> ComponentFrame | None:
        """The innermost (current) component frame. None if stack is empty."""
        return self.component_stack[-1] if self.component_stack else None

    @property
    def depth(self) -> int:
        """Number of component frames currently on the stack."""
        return len(self.component_stack)

    def push(self, frame: ComponentFrame) -> None:
        """Push a frame when entering a <component> element."""
        self.component_stack.append(frame)

    def pop(self) -> ComponentFrame | None:
        """Pop the top frame when leaving a </component> element."""
        return self.component_stack.pop() if self.component_stack else None

    def frame_at(self, depth_from_top: int) -> ComponentFrame | None:
        """
        Returns the frame N levels up from the top of the stack.

        frame_at(0) == top (innermost)
        frame_at(1) == the frame that contains the current one
        frame_at(2) == two levels up, etc.

        Returns None if the requested depth exceeds the stack size.
        Used by handlers that need parent context, e.g. to detect a ship
        docked inside a carrier.
        """
        idx = -(depth_from_top + 1)
        try:
            return self.component_stack[idx]
        except IndexError:
            return None


    # ── Context checks ────────────────────────────────────────────────────────
    # Convenience properties that handlers use as gates before doing any work.
    # All derived from the stack — no separate flags needed.

    @property
    def in_player_station(self) -> bool:
        """True when currently parsing inside a player-owned station."""
        t = self.top
        return t is not None and t.owner == "player" and t.cls in STATION_CLASSES

    @property
    def in_player_ship(self) -> bool:
        """True when currently parsing inside a player-owned ship (any size)."""
        t = self.top
        return t is not None and t.owner == "player" and t.cls in SHIP_CLASSES

    @property
    def in_player_entity(self) -> bool:
        """True when inside any player-owned component (station or ship)."""
        t = self.top
        return t is not None and t.owner == "player"

    @property
    def docked_inside_ship(self) -> bool:
        """
        True when the current component is a ship nested inside another ship.

        Detects docked fighters/scouts/transports inside a carrier. The stack
        at this point looks like: [..., carrier_frame, this_ship_frame].
        The handler uses this to route the ship to docked-ship extraction
        rather than treating it as a free-flying ship.
        """
        if self.depth < 2:
            return False
        parent = self.frame_at(1)
        current = self.top
        return (
            parent is not None
            and current is not None
            and current.cls in SHIP_CLASSES
            and parent.cls in SHIP_CLASSES
        )
