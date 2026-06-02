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
    inventory:       dict[str, int]      = field(default_factory=dict)
    # inventory → own table: station_inventory (scan_id, station_id, ware_id, ware_name, amount)
    # modules   → own table: station_modules   (scan_id, station_id, macro, category, produces)
    # budget lines → own table: station_budget_lines (scan_id, station_id, ware_id, ware_name, amount, price, value, basis)


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
