# Core role: Parse context and component frame stack for streaming XML extraction.

from __future__ import annotations
from dataclasses import dataclass, field

from .entities import (
    Station, NpcStation, Ship, CrewMember, ReputationEntry, Sector, Gate,
    SectorResource, FactionRelationEntry,
    ActiveTrade, ActiveAutoTrade,
    TradeHistory, TradeHistoryMining, TradeHistoryInternal,
)

# All saves use class="station"; others ("factory", "headquarters", "complex") may occur in DLC.
STATION_CLASSES: frozenset[str] = frozenset({"station", "factory", "headquarters", "complex"})

SHIP_CLASSES: frozenset[str] = frozenset({"ship_s", "ship_m", "ship_l", "ship_xl"})


# ─────────────────────────────────────────────────────────────────────────────
#  COMPONENT FRAME  (one entry on the stack)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ComponentFrame:
    """One <component> element on the parse stack (pushed on 'start', popped on 'end').

    Handlers inspect the stack to determine parsing context without per-handler flags.
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
    """Shared state for scan coordinator and all handlers (one per scan).

    Handlers read for context and write to accumulate results; nothing is returned.
    Three sections: parse-time state (changes per-element), accumulated results, cross-handler refs.
    """

    # ── Scan metadata ─────────────────────────────────────────────────────────
    scan_id:     int   # FK on every entity table
    save_file:   str   # filename e.g. "save_003.xml.gz"
    game_time_s: float = 0.0  # Anchor for time_ago calculations on trades
    # Player identity from <player> + <faction id="player"><account> elements
    player_name:    str = ''
    player_credits: int = 0
    player_sector:  str = ''


    # ── Parse-time state ──────────────────────────────────────────────────────
    # Fields change per-element; handlers must not hold references after returning.
    component_stack: list[ComponentFrame] = field(default_factory=list)
    # Most recent sector macro (stack depth varies due to zones/components)
    current_sector_macro: str = ''
    # Entity objects currently being built (cleared at closing </component>)
    current_station:     Station     | None = None
    current_ship:        Ship        | None = None
    current_npc_station: NpcStation  | None = None


    # ── Accumulated results ───────────────────────────────────────────────────
    # Appended throughout scan; read by post-processor and exporter after parse completes.
    stations:               list[Station]               = field(default_factory=list)
    ships:                  list[Ship]                  = field(default_factory=list)
    crew:                   list[CrewMember]            = field(default_factory=list)
    reputation:             list[ReputationEntry]       = field(default_factory=list)
    faction_relations:      list[FactionRelationEntry]  = field(default_factory=list)
    sectors:                list[Sector]                = field(default_factory=list)
    sector_resources:       list[SectorResource]        = field(default_factory=list)
    gates:                  list[Gate]                  = field(default_factory=list)
    npc_stations:           list[NpcStation]            = field(default_factory=list)
    active_trades:          list[ActiveTrade]           = field(default_factory=list)
    active_auto_trades:     list[ActiveAutoTrade]       = field(default_factory=list)
    trade_history:          list[TradeHistory]          = field(default_factory=list)
    trade_history_mining:   list[TradeHistoryMining]    = field(default_factory=list)
    trade_history_internal: list[TradeHistoryInternal]  = field(default_factory=list)


    # ── Cross-handler reference data ──────────────────────────────────────────
    # Built early; read later. Safe: XML guarantees stations/ships before trades.
    player_station_ids: set[str] = field(default_factory=set)  # For trade classification
    # Buildstorages separate from player_station_ids to avoid misclassifying NPC material purchases
    player_buildstorage_ids: set[str] = field(default_factory=set)
    player_ship_ids: set[str] = field(default_factory=set)  # For transport ship classification

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
