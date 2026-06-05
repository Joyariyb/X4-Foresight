-- ─────────────────────────────────────────────────────────────────────────────
--  X4 Foresight v2 — SQLite schema
--
--  THREE STORAGE CLASSES (see dataset plan):
--    HISTORY   one row per entity PER SCAN  → trajectory of YOUR empire
--    LEDGER    each trade stored ONCE       → cumulative, dedup'd by game time
--    REFERENCE latest-only, upserted        → galaxy data that rarely changes
--
--  All HISTORY rows FK to scans.scan_id. Deleting a scan cascades to its rows.
--  Pragmas (foreign_keys, WAL) are set by connection.py, not here.
-- ─────────────────────────────────────────────────────────────────────────────


-- ══ ROOT ═════════════════════════════════════════════════════════════════════
-- One row per scan. Everything in the HISTORY class points back here.
CREATE TABLE IF NOT EXISTS scans (
    scan_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    scanned_at      TEXT    NOT NULL,            -- real-world ISO datetime of the scan
    save_file       TEXT    NOT NULL,            -- e.g. "save_001.xml.gz"
    game_time_s     REAL    NOT NULL,            -- in-game clock — anchor for all time_ago math
    player_name     TEXT,
    player_sector   TEXT,
    player_credits  INTEGER
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

-- NPC ships in the player's station sectors — situational awareness (who is
-- operating near your stations). Bounded subset (~hundreds), per-scan so threat
-- presence can be tracked over time. Identity-level only (no hull/crew); the
-- full ~12k NPC ships are NOT stored.
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


-- ══ LEDGER (cumulative, dedup'd across scans) ════════════════════════════════
-- A completed trade happened once, at game_time_s. Overlapping log windows mean
-- the same trade reappears in consecutive scans — so we INSERT OR IGNORE on a
-- synthetic trade_key. first_scan_id = when we first saw it; last_scan_id lets a
-- later scan refresh a previously-inferred/unresolved counterparty.

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
-- Galaxy data that rarely changes. One row per object, refreshed each scan via
-- INSERT OR REPLACE. last_scan_id reveals when an object was last seen (so a
-- destroyed NPC station stops advancing and can be detected as stale).

CREATE TABLE IF NOT EXISTS sectors (
    sector_macro   TEXT    PRIMARY KEY,
    last_scan_id   INTEGER NOT NULL,
    sector_name    TEXT,
    cluster_macro  TEXT,
    cluster_name   TEXT,
    owner_id       TEXT,
    owner_name     TEXT,
    sunlight       REAL
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
    PRIMARY KEY (station_id, ware_id)
);
