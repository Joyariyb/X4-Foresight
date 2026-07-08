-- Core role: SQLite schema for scan history, trade ledger, and reference galaxy data.
--
-- THREE STORAGE CLASSES:
--   HISTORY   — one row per entity per scan (track YOUR empire trajectory)
--   LEDGER    — each trade stored once, deduplicated by game time (cumulative)
--   REFERENCE — latest-only, upserted (galaxy data that rarely changes)
--
-- All HISTORY rows FK to scans.scan_id with CASCADE delete. Pragmas (foreign_keys, WAL) set by connection.py.


-- ══ ROOT ═════════════════════════════════════════════════════════════════════
-- One row per scan. Everything in the HISTORY class points back here.
CREATE TABLE IF NOT EXISTS scans (
    scan_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    scanned_at      TEXT    NOT NULL,            -- real-world ISO datetime of the scan
    save_file       TEXT    NOT NULL,            -- e.g. "save_001.xml.gz"
    game_time_s     REAL    NOT NULL,            -- in-game clock — anchor for all time_ago math
    player_name     TEXT,
    player_sector   TEXT,
    player_credits  INTEGER,
    -- Player lifetime kill counter from the savegame <stats> block. MUST stay the
    -- last column: write.py inserts scans with an explicit column list, but _migrate
    -- appends this column at the physical end on pre-existing DBs — keeping it last
    -- here means fresh and migrated databases share one column order. NULL on scans
    -- taken before this was tracked (re-scan to backfill).
    ships_destroyed INTEGER
);


-- ══ HISTORY (per-scan snapshots) ═════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS reputation (
    scan_id       INTEGER NOT NULL REFERENCES scans(scan_id) ON DELETE CASCADE,
    faction_id    TEXT    NOT NULL,
    faction_name  TEXT,
    value         REAL,                          -- scaled -30..+30 (in-game display)
    base          REAL,                          -- permanent component
    booster       REAL,                          -- temporary mission component
    tier          TEXT,                          -- "Allied", "Friendly", ...
    PRIMARY KEY (scan_id, faction_id)
);

-- Faction standings (Diplomacy tabs). Base values only — NPC boosters intentionally not stored.
-- other_id may be "player": how that faction sees the player.
CREATE TABLE IF NOT EXISTS faction_relations (
    scan_id       INTEGER NOT NULL REFERENCES scans(scan_id) ON DELETE CASCADE,
    faction_id    TEXT    NOT NULL,               -- subject e.g. "argon"
    faction_name  TEXT,
    other_id      TEXT    NOT NULL,               -- target e.g. "xenon" or "player"
    other_name    TEXT,
    value         REAL,                           -- scaled -30..+30 (in-game display)
    tier          TEXT,                           -- "Allied", "Friendly", ...
    locked        INTEGER NOT NULL DEFAULT 0,     -- 1 = game hard-locks these standings (Xenon, Kha'ak)
    PRIMARY KEY (scan_id, faction_id, other_id)
);

-- Per-faction enemy-kill credits (cumulative, one row per faction per scan).
-- Source: "Destroyed Enemy" reputation entries in the event log. The save does NOT
-- record the destroyed ship's type, only which faction credited the kill — so this
-- is a faction breakdown, not a ship-by-ship list. Counts are cumulative-to-scan
-- (the log is the full lifetime history), so cross-scan deltas give kills-since.
CREATE TABLE IF NOT EXISTS combat_kills (
    scan_id       INTEGER NOT NULL REFERENCES scans(scan_id) ON DELETE CASCADE,
    faction_id    TEXT    NOT NULL,               -- internal id, or raw display name if unknown
    faction_name  TEXT,
    kills         INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (scan_id, faction_id)
);

CREATE TABLE IF NOT EXISTS stations (
    scan_id         INTEGER NOT NULL REFERENCES scans(scan_id) ON DELETE CASCADE,
    object_id       TEXT    NOT NULL,            -- hex component id e.g. "[0x1ca1c]"
    code            TEXT,                         -- display code e.g. "CAB-143"
    name            TEXT,
    sector_macro    TEXT,
    status          TEXT,                         -- "Operational", "Under Construction", ...
    module_count    INTEGER,
    hull_hp         REAL,
    hull_max        REAL,
    hull_pct        REAL,
    shield_hp       REAL,
    shield_max      REAL,
    shield_pct      REAL,
    -- Aggregate (total across all storage types) — kept inline for cheap trend
    -- queries; per-type detail lives in station_cargo.
    cargo_m3        REAL,
    cargo_max_m3    REAL,
    cargo_pct       REAL,
    cargo_adj_pct   REAL,                         -- adjusted for trade reservations
    account_amount  INTEGER,                      -- station cash on hand
    budget_total    REAL,                         -- estimated supply budget
    budget_sunlight REAL,
    PRIMARY KEY (scan_id, object_id)
);

CREATE TABLE IF NOT EXISTS station_cargo (
    scan_id     INTEGER NOT NULL REFERENCES scans(scan_id) ON DELETE CASCADE,
    station_id  TEXT    NOT NULL,
    cargo_type  TEXT    NOT NULL,                 -- "container" | "solid" | "liquid"
    m3          REAL,
    max_m3      REAL,
    pct         REAL,
    adj_pct     REAL,
    PRIMARY KEY (scan_id, station_id, cargo_type)
);

CREATE TABLE IF NOT EXISTS station_modules (
    scan_id     INTEGER NOT NULL REFERENCES scans(scan_id) ON DELETE CASCADE,
    station_id  TEXT    NOT NULL,
    macro       TEXT    NOT NULL,
    category    TEXT,                             -- "Production", "Storage", ...
    produces    TEXT                              -- output ware display name, NULL if none
    -- no PK: a station can hold several identical modules
);

CREATE TABLE IF NOT EXISTS station_inventory (
    scan_id     INTEGER NOT NULL REFERENCES scans(scan_id) ON DELETE CASCADE,
    station_id  TEXT    NOT NULL,
    ware_id     TEXT    NOT NULL,
    ware_name   TEXT,
    amount      INTEGER,
    volume_m3   REAL,
    PRIMARY KEY (scan_id, station_id, ware_id)
);

-- The station's own posted buy/sell listings from <trade><offers> — same
-- record shape as npc_station_wares, but per-scan like the other station_*
-- tables (prices move; the advisor wants history, not latest-only).
CREATE TABLE IF NOT EXISTS station_offers (
    scan_id     INTEGER NOT NULL REFERENCES scans(scan_id) ON DELETE CASCADE,
    station_id  TEXT    NOT NULL,
    ware_id     TEXT    NOT NULL,
    ware_name   TEXT,
    is_buying   INTEGER NOT NULL DEFAULT 0,
    is_selling  INTEGER NOT NULL DEFAULT 0,
    -- Split per direction (see npc_station_wares): a station that buys AND
    -- sells the same ware keeps both offers' figures instead of the shared
    -- price/amount losing whichever parsed last. buy_amount = unmet demand,
    -- sell_amount = stock for sale.
    buy_price   INTEGER,
    buy_amount  INTEGER,
    sell_price  INTEGER,
    sell_amount INTEGER,
    desired     INTEGER,                          -- buy offers only: target stock
    illegal     INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (scan_id, station_id, ware_id)
);

CREATE TABLE IF NOT EXISTS station_budget_lines (
    scan_id     INTEGER NOT NULL REFERENCES scans(scan_id) ON DELETE CASCADE,
    station_id  TEXT    NOT NULL,
    ware_id     TEXT    NOT NULL,
    ware_name   TEXT,
    amount      INTEGER,
    price       REAL,
    value       REAL,
    basis       TEXT,                             -- how the line was estimated
    PRIMARY KEY (scan_id, station_id, ware_id)
);

CREATE TABLE IF NOT EXISTS ships (
    scan_id            INTEGER NOT NULL REFERENCES scans(scan_id) ON DELETE CASCADE,
    object_id          TEXT    NOT NULL,
    code               TEXT,
    name               TEXT,                      -- player-given name, NULL if none
    ship_class         TEXT,                      -- "ship_m"
    size               TEXT,                      -- S / M / L / XL
    macro              TEXT,
    role               TEXT,                      -- "Freighter", "Miner", ...
    owner_id           TEXT,                      -- "player" or faction id
    owner_name         TEXT,
    hull_origin_id     TEXT,
    hull_origin_name   TEXT,
    sector_macro       TEXT,
    ship_order         TEXT,                      -- current order ("order" is reserved)
    homebase_id        TEXT,
    docked_at          TEXT,
    commander_id       TEXT,
    under_construction INTEGER,                   -- 0/1
    hull_hp            REAL,
    hull_max           REAL,
    hull_pct           REAL,
    shield_hp          REAL,
    shield_max         REAL,
    shield_pct         REAL,
    cargo_m3           REAL,
    cargo_max_m3       REAL,
    pilot_id           TEXT,
    PRIMARY KEY (scan_id, object_id)
);

-- Ship equipment (weapons, turrets, shields, engines, thrusters).
-- Dedup source for ship "designs"; macros resolve to stats via equipment_stats.py at export time.
-- Player ships (buffered subtree walk) + the npc_ships subset (streamed capture,
-- bounded to player-station sectors); ship_id joins to ships OR npc_ships.
CREATE TABLE IF NOT EXISTS ship_equipment (
    scan_id   INTEGER NOT NULL REFERENCES scans(scan_id) ON DELETE CASCADE,
    ship_id   TEXT    NOT NULL,            -- FK → ships.object_id
    slot_type TEXT    NOT NULL,            -- weapon / turret / shield / engine / thruster
    macro     TEXT    NOT NULL,
    count     INTEGER NOT NULL DEFAULT 1
    -- no PK: aggregated per (ship, slot, macro); a ship holds many of each
);

-- NPC ships in player's station sectors (threat awareness). Bounded subset (~hundreds) per scan.
-- Identity-level only; full ~12k NPC ships not stored.
CREATE TABLE IF NOT EXISTS npc_ships (
    scan_id      INTEGER NOT NULL REFERENCES scans(scan_id) ON DELETE CASCADE,
    object_id    TEXT,
    code         TEXT,
    name         TEXT,         -- resolved type name e.g. "Mercury Vanguard"
    ship_class   TEXT,
    size         TEXT,
    macro        TEXT,
    role         TEXT,
    owner_id     TEXT,         -- faction id
    owner_name   TEXT,
    sector_macro TEXT,
    sector_name  TEXT,
    destination  TEXT,         -- station it is hauling to, if mid-delivery; else NULL
    ship_order   TEXT          -- current order e.g. "Trading", "Attacking", "Patrolling"
);

CREATE TABLE IF NOT EXISTS crew (
    scan_id           INTEGER NOT NULL REFERENCES scans(scan_id) ON DELETE CASCADE,
    role              TEXT,                       -- "pilot" | "manager" | "service" | "marine"
    name              TEXT,
    object_id         TEXT,                       -- pilots/managers only
    seed              TEXT,                       -- service/marines only
    assigned_code     TEXT,                       -- ship/station the crew serves
    assigned_type     TEXT,                       -- "ship" | "station"
    sector_macro      TEXT,
    faction           TEXT,
    gender            TEXT,
    skill_piloting    INTEGER,
    skill_management  INTEGER,
    skill_morale      INTEGER,
    skill_engineering INTEGER,
    skill_boarding    INTEGER
);

-- Active orders are point-in-time, so they live in the HISTORY class (per scan).
CREATE TABLE IF NOT EXISTS active_trades (
    scan_id           INTEGER NOT NULL REFERENCES scans(scan_id) ON DELETE CASCADE,
    station_id        TEXT,
    station_code      TEXT,
    station_name      TEXT,
    direction         TEXT,                       -- "In" | "Out"
    ship_id           TEXT,
    ship_code         TEXT,
    ship_name         TEXT,
    ware_id           TEXT,
    ware_name         TEXT,
    amount            INTEGER,
    price_cr          REAL,
    total_cr          REAL,
    counterparty_id   TEXT,
    counterparty_name TEXT
);

CREATE TABLE IF NOT EXISTS active_auto_trades (
    scan_id      INTEGER NOT NULL REFERENCES scans(scan_id) ON DELETE CASCADE,
    ship_id      TEXT,
    ship_code    TEXT,
    ship_name    TEXT,
    buyer_id     TEXT,
    buyer_code   TEXT,
    buyer_name   TEXT,
    seller_id    TEXT,
    seller_code  TEXT,
    seller_name  TEXT,
    ware_id      TEXT,
    ware_name    TEXT,
    amount       INTEGER,
    price_cr     REAL,
    total_cr     REAL
);


-- Player-courier deliveries in flight at save time: the BUY leg is in the
-- economy log but the commercial SELL leg hasn't landed, so the ware is on the
-- ship. One row per pending pickup (TradePostProcessor._suppress_pending_pickups).
CREATE TABLE IF NOT EXISTS in_progress_deliveries (
    scan_id           INTEGER NOT NULL REFERENCES scans(scan_id) ON DELETE CASCADE,
    ship_id           TEXT,
    ship_code         TEXT,
    ship_name         TEXT,
    ware_id           TEXT,
    ware_name         TEXT,
    amount            INTEGER,
    from_station_id   TEXT,         -- player station that loaded the ship
    from_station_code TEXT,
    from_station_name TEXT,
    dest_station_id   TEXT,         -- NULL when no active destination is known
    dest_station_name TEXT,
    time_ago_s        REAL          -- seconds since pickup
);


-- Player notification/event log, most recent rows per category. The save holds
-- thousands of rows; write.py caps what it keeps (EVENTS_PER_CATEGORY there).
CREATE TABLE IF NOT EXISTS player_events (
    scan_id      INTEGER NOT NULL REFERENCES scans(scan_id) ON DELETE CASCADE,
    category     TEXT,          -- alerts | upkeep | missions | news | diplomacy | tips | uncategorised
    title        TEXT,
    text         TEXT,
    faction_name TEXT,          -- resolved faction= language ref, '' if none
    component_id TEXT,          -- ship/station object_id the event points at
    game_time_s  REAL,
    time_ago_s   REAL
);

-- Career stats from the savegame <stats> block (trade_score, fight_rank, …).
-- One row per stat per scan so ranks and scores can be trended across scans.
CREATE TABLE IF NOT EXISTS player_stats (
    scan_id  INTEGER NOT NULL REFERENCES scans(scan_id) ON DELETE CASCADE,
    stat_id  TEXT    NOT NULL,
    value    REAL,
    PRIMARY KEY (scan_id, stat_id)
);


-- ══ LEDGER (cumulative, dedup'd across scans) ════════════════════════════════
-- Completed trades (once per trade, dedup'd by game_time_s). INSERT OR IGNORE on trade_key
-- since overlapping log windows show the same trade in consecutive scans.
-- first_scan_id=discovery; last_scan_id allows refresh of previously-unresolved counterparties.

CREATE TABLE IF NOT EXISTS trade_history (
    trade_key         TEXT    PRIMARY KEY,        -- game_time:station:dir:ware:amount:ship
    first_scan_id     INTEGER NOT NULL,
    last_scan_id      INTEGER NOT NULL,
    station_id        TEXT,
    station_code      TEXT,
    station_name      TEXT,
    direction         TEXT,
    ship_id           TEXT,
    ship_code         TEXT,
    ship_name         TEXT,
    ware_id           TEXT,
    ware_name         TEXT,
    amount            INTEGER,
    price_cr          REAL,
    total_cr          REAL,
    counterparty_id   TEXT,
    counterparty_name TEXT,
    resolution        TEXT,                       -- direct|courier|homebase|visit|sector|delivery|''
    game_time_s       REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_trade_history_time    ON trade_history(game_time_s);
CREATE INDEX IF NOT EXISTS ix_trade_history_station ON trade_history(station_id);
CREATE INDEX IF NOT EXISTS ix_trade_history_ware    ON trade_history(ware_id);

CREATE TABLE IF NOT EXISTS trade_history_mining (
    trade_key      TEXT    PRIMARY KEY,
    first_scan_id  INTEGER NOT NULL,
    last_scan_id   INTEGER NOT NULL,
    station_id     TEXT,
    station_code   TEXT,
    station_name   TEXT,
    ship_id        TEXT,
    ship_code      TEXT,
    ship_name      TEXT,
    ware_id        TEXT,
    ware_name      TEXT,
    amount         INTEGER,
    price_cr       REAL,
    total_cr       REAL,
    game_time_s    REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_mining_time ON trade_history_mining(game_time_s);

CREATE TABLE IF NOT EXISTS trade_history_internal (
    trade_key       TEXT    PRIMARY KEY,
    first_scan_id   INTEGER NOT NULL,
    last_scan_id    INTEGER NOT NULL,
    station_a_id    TEXT,
    station_a_code  TEXT,
    station_a_name  TEXT,
    station_b_id    TEXT,
    station_b_code  TEXT,
    station_b_name  TEXT,
    ship_id         TEXT,
    ship_code       TEXT,
    ship_name       TEXT,
    ware_id         TEXT,
    ware_name       TEXT,
    amount          INTEGER,
    price_cr        REAL,
    total_cr        REAL,
    game_time_s     REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_internal_time ON trade_history_internal(game_time_s);


-- ══ REFERENCE (latest-only, upserted) ════════════════════════════════════════
-- Galaxy data refreshed via INSERT OR REPLACE. last_scan_id detects destroyed/stale objects.

CREATE TABLE IF NOT EXISTS sectors (
    sector_macro   TEXT    PRIMARY KEY,
    last_scan_id   INTEGER NOT NULL,
    sector_name    TEXT,
    cluster_macro  TEXT,
    cluster_name   TEXT,
    owner_id       TEXT,
    owner_name     TEXT,
    sunlight       REAL,
    -- 1 when the save marked this sector knownto="player" (discovered/seen),
    -- 0 otherwise. MUST stay the last column: write.py inserts positionally and
    -- _migrate appends this column at the physical end on pre-existing DBs.
    is_discovered  INTEGER
);

-- Mineable resources per sector (aggregated from save's <resourceareas>).
-- Reference data: cleared each scan like sector_links.
CREATE TABLE IF NOT EXISTS sector_resources (
    sector_macro   TEXT    NOT NULL,
    ware           TEXT    NOT NULL,
    yield_level    TEXT,              -- verylow|low|lowplus|medium|medhigh|high
    recharge_max   INTEGER,           -- summed capacity across the sector's areas
    recharge_time  INTEGER,           -- refresh time in ms
    last_scan_id   INTEGER NOT NULL,
    PRIMARY KEY (sector_macro, ware)
);

CREATE TABLE IF NOT EXISTS npc_stations (
    object_id      TEXT    PRIMARY KEY,
    last_scan_id   INTEGER NOT NULL,
    code           TEXT,
    name           TEXT,
    macro          TEXT,
    station_type   TEXT,
    sector_macro   TEXT,
    owner_id       TEXT,
    owner_name     TEXT
);

CREATE TABLE IF NOT EXISTS npc_station_wares (
    station_id   TEXT NOT NULL,
    ware_id      TEXT NOT NULL,
    ware_name    TEXT,
    is_buying    INTEGER NOT NULL DEFAULT 0,
    is_selling   INTEGER NOT NULL DEFAULT 0,
    -- A station commonly buys AND sells the same ware at once, at different
    -- prices and quantities, so each direction keeps its own pair rather than
    -- sharing one price/amount (which lost whichever offer was written last).
    -- buy_amount is the unmet demand; sell_amount is the stock for sale.
    buy_price    INTEGER,
    buy_amount   INTEGER,
    sell_price   INTEGER,
    sell_amount  INTEGER,
    -- Buy offers only: target order size. Migrated DBs have desired plus the
    -- four buy_/sell_ columns at the table's physical end (v2/v3 ALTERs) —
    -- write.py's explicit-column INSERT copes.
    desired      INTEGER,
    illegal      INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (station_id, ware_id)
);

-- Static ware properties from libraries/wares.xml. Written once at connection time.
-- Single queryable source for name, cargo type, volume (avoids Python-dict imports in export layer).
CREATE TABLE IF NOT EXISTS ware_metadata (
    ware_id        TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    transport_type TEXT,   -- container / solid / liquid
    volume_m3      REAL
);

-- Market price bands from libraries/wares.xml. Written once at connection time.
-- Replaces Python dict in export layer so price data is queryable with other ware fields.
CREATE TABLE IF NOT EXISTS ware_prices (
    ware_id    TEXT PRIMARY KEY,
    price_min  INTEGER NOT NULL,
    price_avg  INTEGER NOT NULL,
    price_max  INTEGER NOT NULL
);

-- Per-scan production analytics. Computed during scanning (export layer is pure DB read).
-- Enables cross-scan trend analysis.
CREATE TABLE IF NOT EXISTS station_production_analytics (
    scan_id            INTEGER NOT NULL REFERENCES scans(scan_id) ON DELETE CASCADE,
    station_id         TEXT    NOT NULL,
    ware_id            TEXT    NOT NULL,
    ware_name          TEXT,              -- display name of the produced ware
    production_rate    REAL,              -- units/hr produced (all modules combined)
    consumption_rate   REAL,              -- units/hr consumed internally by other modules
    surplus_rate       REAL,              -- production_rate − consumption_rate
    time_to_cap_hours  REAL,             -- hrs until cargo bay fills at current surplus rate;
                                         --   NULL = no surplus (consuming ≥ producing)
    runtime_minutes    REAL,              -- NULL = no inputs needed (e.g. energy cells)
    limiting_ware_id   TEXT,             -- ware_id of the input that runs out first
    limiting_ware_name TEXT,             -- display name of that input
    PRIMARY KEY (scan_id, station_id, ware_id)
);

-- Galaxy connectivity graph: sector-to-sector links (one row per undirected edge).
-- Cost 1=gate/accelerator (counts toward jump range); cost 0=superhighway (free).
-- Unique among REFERENCE tables: topology is ONE coherent graph, so cleared+rewritten each scan.
-- sector_a < sector_b canonicalizes each edge to one stored row.
CREATE TABLE IF NOT EXISTS sector_links (
    sector_a      TEXT    NOT NULL,
    sector_b      TEXT    NOT NULL,
    cost          INTEGER NOT NULL,
    last_scan_id  INTEGER NOT NULL,
    PRIMARY KEY (sector_a, sector_b)
);
