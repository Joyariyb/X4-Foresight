from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
#  SCAN  (root record — every other table references this via scan_id)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Scan:
    scan_id:        int    # PK — auto-increment
    scanned_at:     str    # real-world datetime e.g. "2026-06-02T14:32:00Z"
    save_file:      str    # filename e.g. "save_003.xml.gz"
    game_time_s:    float  # in-game clock at save time — anchor for time_ago_s calculations
    player_name:    str    # e.g. "Ares"
    player_sector:  str    # e.g. "The Void"
    player_credits: int    # credits at scan time


# ─────────────────────────────────────────────────────────────────────────────
#  REPUTATION
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ReputationEntry:
    scan_id:      int    # FK → scans table
    faction_id:   str    # raw internal ID e.g. "argon"
    faction_name: str    # display name e.g. "Argon Federation"
    value:        float  # scaled −30 to +30 (matches in-game display)
    base:         float  # permanent standing component
    booster:      float  # temporary mission bonus component
    tier:         str    # label e.g. "Friendly", "Hostile"

    # ── Computed properties ───────────────────────────────────────────────────
    # Derived from value — no need to store separately.

    @property
    def can_trade(self) -> bool:
        """False when reputation is below −10 (trading blocked)."""
        return self.value >= -10.0

    @property
    def is_hostile(self) -> bool:
        """True when faction actively attacks player property (below −25)."""
        return self.value <= -25.0

    @property
    def promotion_available(self) -> bool:
        """True when player has reached a promotion threshold (+10 or +20)."""
        return self.value >= 10.0


# ─────────────────────────────────────────────────────────────────────────────
#  FACTION RELATIONS  (NPC faction → other faction standings)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class FactionRelationEntry:
    """
    One NPC faction's standing toward one other faction (or the player).

    Mirrors ReputationEntry but for non-player subjects. No base/booster split:
    NPC boosters exist in the save but are deliberately ignored — only the
    permanent <relation> value is captured (decision: 2026-06-12).
    """
    scan_id:      int    # FK → scans table
    faction_id:   str    # subject faction e.g. "argon" — whose standings these are
    faction_name: str    # subject display name e.g. "[ARG] Argon Federation"
    other_id:     str    # target faction e.g. "xenon", or "player"
    other_name:   str    # target display name
    value:        float  # scaled −30 to +30 (same scale as ReputationEntry)
    tier:         str    # label e.g. "Friendly", "At War"
    locked:       bool   # True when the save marks <relations locked="1"> —
                         # the game never changes this faction's standings
                         # (Xenon and Kha'ak in practice)


# ─────────────────────────────────────────────────────────────────────────────
#  SECTOR
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Sector:
    scan_id:       int
    sector_macro:  str           # raw macro ID e.g. "cluster_43_sector001_macro"
    sector_name:   str           # display name e.g. "The Void"
    cluster_macro: str           # parent cluster macro
    cluster_name:  str           # parent cluster display name
    owner_id:      str           # faction ID e.g. "argon"
    owner_name:    str           # faction display name e.g. "Argon Federation"
    sunlight:      float         # solar multiplier — affects energy cell production


# ─────────────────────────────────────────────────────────────────────────────
#  GATE  (one endpoint of a gate/accelerator pair — feeds the galaxy map graph)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Gate:
    """
    One gate endpoint sitting in a single sector.

    A traversable connection between two sectors is represented in the save as a
    PAIR of gate components — one endpoint in each sector. Each endpoint stores
    its own "destination" connection id plus the partner endpoint's connection id
    (reciprocal). The galaxy-map builder pairs them by matching conn_id across all
    gates, producing one edge per sector-to-sector link.

    Both jump gates and orbital accelerators count as a 1-jump hop in X4 (verified
    against the in-game trade-range rules), so gate_type is informational only —
    it is not used to weight distance. Superhighways are NOT gates; intra-cluster
    (0-jump) movement is derived separately from shared cluster membership.
    """
    scan_id:         int
    object_id:       str   # hex component ID e.g. "[0x48b8]"
    code:            str   # display code e.g. "FYW-152"
    macro:           str   # raw macro — e.g. "props_gates_anc_gate_macro"
    gate_type:       str   # "gate" (jump gate) or "accelerator" — derived from macro
    sector_macro:    str   # FK → sectors.sector_macro — the sector this endpoint is in
    conn_id:         str   # this endpoint's own "destination" connection id (pairing key)
    partner_conn_id: str   # the partner endpoint's connection id (resolves to the far sector)


# ─────────────────────────────────────────────────────────────────────────────
#  STATION
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CargoStorage:
    """Aggregated storage totals for one cargo type (container / solid / liquid / total)."""
    m3:      float   # raw physical volume currently stored
    max_m3:  float   # maximum capacity
    pct:     float   # raw fill percentage
    adj_m3:  float   # adjusted volume (includes trade reservations)
    adj_pct: float   # adjusted fill percentage


@dataclass
class StationModule:
    """One module installed on a player station."""
    macro:    str            # raw macro ID e.g. "prod_gen_energycells_macro"
    category: str            # human-readable category e.g. "Production"
    produces: str | None     # display name of output ware, None if not a production module


@dataclass
class Station:
    scan_id:         int
    object_id:       str            # hex component ID e.g. "[0x4f44]"
    code:            str            # display code e.g. "ABC-001"
    name:            str            # player-given name
    sector_macro:    str            # FK → sectors.sector_macro
    status:          str            # e.g. "Operational", "Under Construction", "Destroyed"
    module_count:    int
    hull_hp:         float | None
    hull_max:        float | None
    hull_pct:        float | None   # None when max is unknown
    shield_hp:       float | None
    shield_max:      float | None
    shield_pct:      float | None   # None when no shield generators installed
    cargo_container: CargoStorage | None   # None when no container storage installed
    cargo_solid:     CargoStorage | None   # None when no solid storage installed
    cargo_liquid:    CargoStorage | None   # None when no liquid storage installed
    cargo_total:     CargoStorage | None   # None when no storage at all
    account_amount:  int | None     # station cash on hand
    budget_total:    float | None   # estimated supply budget in credits
    budget_sunlight: float | None   # sunlight multiplier used in budget calculation
    modules:         list[StationModule] = field(default_factory=list)
    inventory:       dict[str, tuple[int, float]] = field(default_factory=dict)  # ware_id → (units, volume_m3)
    # Per-ware supply-budget breakdown from estimate_station_budget()['lines'];
    # each dict carries ware, ware_name, amount, price, value, basis. Drives the
    # station Economy pie in the UI.
    budget_lines:         list[dict] = field(default_factory=list)
    # Per-produced-ware analytics from production_analytics_from_modules():
    # production_rate, consumption_rate, surplus_rate, runtime_minutes,
    # limiting_ware_id, limiting_ware_name. Stored in station_production_analytics.
    production_analytics: list[dict] = field(default_factory=list)
    # inventory             → own table: station_inventory             (scan_id, station_id, ware_id, ware_name, amount, volume_m3)
    # modules               → own table: station_modules               (scan_id, station_id, macro, category, produces)
    # budget_lines          → own table: station_budget_lines          (scan_id, station_id, ware_id, ware_name, amount, price, value, basis)
    # production_analytics  → own table: station_production_analytics  (scan_id, station_id, ware_id, ...)


# ─────────────────────────────────────────────────────────────────────────────
#  NPC STATION
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class NpcStation:
    scan_id:      int
    object_id:    str    # hex component ID
    code:         str    # display code e.g. "CYS-158"
    name:         str    # full display name e.g. "TEL Advanced Electronics Factory I (CYS-158)"
    macro:        str    # raw macro ID
    station_type: str    # e.g. "Shipyard", "Trading Station", "Production"
    sector_macro: str    # FK → sectors.sector_macro
    owner_id:     str    # faction ID e.g. "teladi"
    owner_name:   str    # faction display name e.g. "Teladi Company"
    wares:        list[str] = field(default_factory=list)
    # wares → own table: npc_station_wares (scan_id, station_id, ware_id, ware_name, is_buying, is_selling)


# ─────────────────────────────────────────────────────────────────────────────
#  CREW
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CrewMember:
    scan_id:           int
    role:              str        # "pilot", "manager", "service", "marine"
    name:              str        # real name for pilots/managers, generated for others e.g. "Marine #2"
    object_id:         str | None # hex component ID — pilots and managers only (PK candidate)
    seed:              str | None # npcseed value — service crew and marines only (unique key)
    assigned_code:     str        # code of the ship or station they are assigned to
    assigned_type:     str        # "ship" or "station"
    sector_macro:      str        # FK → sectors.sector_macro
    faction:           str | None # from character macro e.g. "argon"
    gender:            str | None # "male" / "female"
    skill_piloting:    int        # 0-5 stars
    skill_management:  int        # 0-5 stars
    skill_morale:      int        # 0-5 stars
    skill_engineering: int        # 0-5 stars
    skill_boarding:    int        # 0-5 stars — primarily relevant for marines


# ─────────────────────────────────────────────────────────────────────────────
#  SHIP
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Ship:
    scan_id:            int
    object_id:          str            # hex component ID e.g. "[0x4d4c]" — PK candidate
    code:               str            # display code e.g. "ABC-123"
    name:               str | None     # player-given name, None if no custom name
    ship_class:         str            # raw class e.g. "ship_m"
    size:               str            # S / M / L / XL
    macro:              str            # raw macro ID
    role:               str            # e.g. "Fighter", "Miner", "Trader"
    owner_id:           str            # "player" or faction ID
    owner_name:         str            # "Player" or faction display name
    hull_origin_id:     str            # faction that built the hull
    hull_origin_name:   str            # display name — flags captured/unusual ships
    sector_macro:       str            # FK → sectors.sector_macro
    order:              str            # current order e.g. "Mining", "TradePerform", "Docked"
    homebase_id:        str | None     # FK → stations.object_id
    docked_at:          str | None     # FK → stations.object_id, None if free-flying
    commander_id:       str | None     # FK → ships.object_id OR stations.object_id (fleet hierarchy)
    under_construction: bool
    hull_hp:            float | None   # None for NPC ships
    hull_max:           float | None
    hull_pct:           float | None
    shield_hp:          float | None
    shield_max:         float | None
    shield_pct:         float | None
    cargo_m3:           float | None   # current cargo load — not yet extracted
    cargo_max_m3:       float | None   # maximum cargo capacity
    pilot_id:           str | None     # FK → crew.object_id, None for NPC ships


# ─────────────────────────────────────────────────────────────────────────────
#  TRADE HISTORY  (completed economylog entries — player station ↔ NPC)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TradeHistory:
    scan_id:           int
    station_id:        str        # FK → stations.object_id (always player-owned)
    station_code:      str        # display code e.g. "CAB-143"
    station_name:      str        # display name e.g. "Station BHS" — stored for self-contained history
    direction:         str        # "In" (bought) or "Out" (sold) relative to player station
    ship_id:           str        # FK → ships.object_id (transport ship)
    ship_code:         str        # display code e.g. "WYX-052"
    ship_name:         str        # display name e.g. "Mercury Sentinel"
    ware_id:           str        # raw ware ID e.g. "graphene"
    ware_name:         str        # display name e.g. "Graphene"
    amount:            int        # units traded
    price_cr:          float      # price per unit in Cr
    total_cr:          float      # amount × price_cr
    counterparty_id:   str | None # FK → npc_stations.object_id, None if unresolved
    counterparty_name: str | None # display name fallback e.g. "TEL Quantum Tube Factory I (OHW-677)"
    game_time_s:       float      # absolute in-game clock at trade time — dedup key across scans
    time_ago_s:        float      # seconds before save time e.g. 540.0 = 9 minutes ago
    # How the counterparty was resolved — lets the UI/AI weight confidence:
    #   PROVEN   : "direct" (station↔station), "courier" (player BUY/SELL legs paired)
    #   INFERRED : "homebase", "visit", "sector", "delivery" (best-effort guesses for
    #              unlogged NPC→NPC legs — a station is shown but it is not certain)
    #   ""       : unresolved (counterparty_name is None)
    resolution:        str = ''


# ─────────────────────────────────────────────────────────────────────────────
#  TRADE HISTORY MINING  (mining ship delivers resources to player station)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TradeHistoryMining:
    scan_id:      int
    station_id:   str     # FK → stations.object_id (receiving station — always player-owned)
    station_code: str     # display code e.g. "CAB-143"
    station_name: str     # display name e.g. "Station BHS"
    ship_id:      str     # FK → ships.object_id (mining ship that delivered)
    ship_code:    str     # display code e.g. "WYX-052"
    ship_name:    str     # display name e.g. "Magnetar Vanguard"
    ware_id:      str     # raw ware ID e.g. "ore"
    ware_name:    str     # display name e.g. "Ore"
    amount:       int     # units delivered
    price_cr:     float   # price per unit paid by station
    total_cr:     float   # amount × price_cr
    game_time_s:  float   # absolute game time — dedup key across scans
    time_ago_s:   float   # seconds before save time


# ─────────────────────────────────────────────────────────────────────────────
#  TRADE HISTORY INTERNAL  (station-to-station transfers via player ship)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TradeHistoryInternal:
    scan_id:        int
    station_a_id:   str     # FK → stations.object_id (one party)
    station_a_code: str
    station_a_name: str
    station_b_id:   str     # FK → stations.object_id (other party)
    station_b_code: str
    station_b_name: str
    ship_id:        str     # FK → ships.object_id (transport — context only)
    ship_code:      str
    ship_name:      str
    ware_id:        str
    ware_name:      str
    amount:         int
    price_cr:       float   # internal accounting price — not real commerce
    total_cr:       float   # amount × price_cr
    game_time_s:    float   # dedup key across scans
    time_ago_s:     float   # seconds before save time


# ─────────────────────────────────────────────────────────────────────────────
#  ACTIVE TRADES  (live TradePerform orders at player stations)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ActiveTrade:
    scan_id:           int
    station_id:        str        # FK → stations.object_id (player station)
    station_code:      str
    station_name:      str
    direction:         str        # "In" (buying) or "Out" (selling)
    ship_id:           str        # FK → ships.object_id (transport ship)
    ship_code:         str
    ship_name:         str
    ware_id:           str
    ware_name:         str
    amount:            int
    price_cr:          float
    total_cr:          float
    counterparty_id:   str | None # FK → npc_stations.object_id, None if unresolved
    counterparty_name: str | None # fallback display name


# ─────────────────────────────────────────────────────────────────────────────
#  ACTIVE AUTO TRADES  (live orders — player ship on NPC-to-NPC route)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ActiveAutoTrade:
    scan_id:      int
    ship_id:      str     # FK → ships.object_id (player ship executing the route)
    ship_code:    str
    ship_name:    str
    buyer_id:     str     # FK → npc_stations.object_id
    buyer_code:   str
    buyer_name:   str
    seller_id:    str     # FK → npc_stations.object_id
    seller_code:  str
    seller_name:  str
    ware_id:      str
    ware_name:    str
    amount:       int
    price_cr:     float
    total_cr:     float
