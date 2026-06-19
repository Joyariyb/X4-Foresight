"""
export/jsonexport.py

Builds the JSON export (x4_empire_state.json) that the UI and AI consume.

DB-READ, by design: the snapshot is read back FROM the database for a given
scan_id (default = latest). This is the permanent export path — when cross-scan
trends are added later they become extra queries here, with no rework, and the
same function can already export any historical scan.

Top-level keys: stations / reputation / crew / station_trades / ships, plus:
  - meta block (scan_id, timing)
  - resolution tag on every station trade (proven / inferred / unknown)
  - mining_deliveries and internal_transfers as their own keys
"""
from __future__ import annotations
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

from scanner import galaxy_map as gm
from scanner.ship_names import ship_display_name, resolve_ship_type
from data.equipment_stats import EQUIPMENT_STATS, EQUIPMENT_ALIASES
from data.ship_stats import SHIP_STATS

# Catalog stat fields copied onto each exported loadout entry. The UI picks
# which to show per slot; price drives the per-item cost + design total.
_EQUIP_STAT_KEYS = (
    'damage_hull', 'damage_shield', 'reload_rate', 'range_m',
    'capacity', 'recharge_rate', 'recharge_delay',
    'thrust_forward', 'thrust_reverse', 'travel_thrust', 'boost_thrust',
    'strafe', 'pitch', 'yaw', 'roll', 'price',
)


def _rows(conn, sql, params=()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def _drop(d: dict, *keys) -> dict:
    for k in keys:
        d.pop(k, None)
    return d


# ── Section builders ───────────────────────────────────────────────────────────

def _fleet_by_station(conn, scan_id) -> dict[str, dict]:
    """Returns {station_id: {total, traders, miners, combat, other}} for this scan.

    homebase_id in the ships table is set by _resolve_ship_homebases() in
    x4_save_scanner.py after the full parse.  That function resolves both the
    TradeRoutine `range` param (traders) and the commander connection ref (all
    other ship types) through dockingbay_index, so homebase_id is a reliable
    player-station object_id for every assigned ship type by DB write time.

    Role buckets (matched against extract_role() output — see scanner/ship_names.py):
      traders — Freighter, Transport
      miners  — any role starting with "Miner" (catches Miner (Solid) etc.)
      combat  — Fighter, Heavy Fighter, Corvette, Frigate, Destroyer, Carrier, Bomber
      other   — Builder, Resupplier, Scout, Unknown, anything else
    """
    # Simple GROUP BY — homebase_id is already a station object_id by the time
    # data is written to the DB, no further resolution needed here.
    rows = conn.execute(
        "SELECT homebase_id, role, COUNT(*) AS count "
        "FROM ships WHERE scan_id=? AND homebase_id IS NOT NULL "
        "GROUP BY homebase_id, role",
        (scan_id,),
    ).fetchall()

    result: dict[str, dict] = {}
    for r in rows:
        sid  = r['homebase_id']
        cnt  = r['count']
        role = r['role'] or ''
        if sid not in result:
            result[sid] = {'total': 0, 'traders': 0, 'miners': 0, 'combat': 0, 'other': 0}
        result[sid]['total'] += cnt
        # Role strings come from extract_role() in scanner/ship_names.py.
        # Use prefix matching so "Miner (Solid)" etc. all fall into miners,
        # and "Heavy Fighter" falls into combat alongside plain "Fighter".
        if role in ('Freighter', 'Transport'):
            result[sid]['traders'] += cnt
        elif role.startswith('Miner'):
            result[sid]['miners']  += cnt
        elif any(role.startswith(r) for r in ('Fighter', 'Heavy Fighter', 'Corvette',
                                               'Frigate', 'Destroyer', 'Carrier', 'Bomber')):
            result[sid]['combat']  += cnt
        else:
            result[sid]['other']   += cnt
    return result


def _station_transport_types(conn) -> dict[str, str]:
    """Load ware_id → transport_type from the DB for all wares.

    Used by _stations() to tag each inventory entry with its cargo category
    ('container' | 'solid' | 'liquid') without any Python-dict import.
    Falls back to 'container' for any ware that lacks an explicit transport type
    (same default the old WARE_TRANSPORT.get() call used).
    """
    rows = conn.execute(
        "SELECT ware_id, transport_type FROM ware_metadata "
        "WHERE transport_type IS NOT NULL"
    ).fetchall()
    return {r['ware_id']: r['transport_type'] for r in rows}


def _stations(conn, scan_id) -> list[dict]:
    # Load both lookups once up front — avoids repeated queries inside the loop.
    transport    = _station_transport_types(conn)
    fleet_by_stn = _fleet_by_station(conn, scan_id)

    _EMPTY_FLEET = {'total': 0, 'traders': 0, 'miners': 0, 'combat': 0, 'other': 0}

    out = []
    for s in conn.execute("SELECT * FROM stations WHERE scan_id=?", (scan_id,)):
        d = _drop(dict(s), 'scan_id')
        sid = d['object_id']
        # Inventory keyed by ware_id. Each entry carries:
        #   amount     — units currently in storage
        #   volume_m3  — total m³ occupied (amount × per-unit volume from the scanner)
        #   cargo_type — "container" | "solid" | "liquid" (from ware_metadata DB table)
        # The UI uses volume_m3 / cargo_by_type[cargo_type].max_m3 for the storage bar.
        d['inventory'] = {
            r['ware_id']: {
                'amount':     r['amount'],
                'volume_m3':  r['volume_m3'],
                'cargo_type': transport.get(r['ware_id'], 'container'),
            }
            for r in conn.execute(
                "SELECT ware_id, amount, volume_m3 FROM station_inventory "
                "WHERE scan_id=? AND station_id=? ORDER BY amount DESC",
                (scan_id, sid))
        }
        d['cargo_by_type'] = _rows(
            conn,
            "SELECT cargo_type, m3, max_m3, pct FROM station_cargo "
            "WHERE scan_id=? AND station_id=?", (scan_id, sid))
        d['modules'] = _rows(
            conn,
            "SELECT macro, category, produces FROM station_modules "
            "WHERE scan_id=? AND station_id=?", (scan_id, sid))

        # Production analytics — computed during scanning and stored per-scan so
        # the export is a pure DB read with no Python-side recalculation.
        analytics = _rows(
            conn,
            "SELECT ware_name, production_rate, consumption_rate, surplus_rate, "
            "time_to_cap_hours, runtime_minutes, limiting_ware_name "
            "FROM station_production_analytics "
            "WHERE scan_id=? AND station_id=?",
            (scan_id, sid))

        # Produced-ware names for the UI's production string and WARE_COLOURS lookup.
        d['production'] = ','.join(sorted(
            r['ware_name'] for r in analytics if r['ware_name']))

        # Flat dicts keyed by produced-ware display name, matching the shape the
        # UI's production tab expects for each row.
        d['production_rates']   = {r['ware_name']: r['production_rate']  for r in analytics if r['ware_name']}
        d['consumption_rates']  = {r['ware_name']: r['consumption_rate'] for r in analytics if r['ware_name']}
        d['production_runtimes'] = {
            r['ware_name']: {
                'minutes':          r['runtime_minutes'],
                'limiting_ware':    r['limiting_ware_name'],
                'time_to_cap_hours': r['time_to_cap_hours'],
            }
            for r in analytics if r['ware_name']
        }
        # Ships that call this station home, bucketed by role.  The UI shows the
        # total in the Ships stat cell and the breakdown on hover.
        d['assigned_fleet'] = fleet_by_stn.get(sid, _EMPTY_FLEET)

        # Nested budget object the Economy pie consumes: header totals plus the
        # per-ware breakdown (ware_id surfaced as `ware`, with ware_name/amount/
        # price/value/basis), biggest value first.
        d['budget'] = {
            'total':    d['budget_total'],
            'sunlight': d['budget_sunlight'],
            'lines': _rows(
                conn,
                "SELECT ware_id AS ware, ware_name, amount, price, value, basis "
                "FROM station_budget_lines WHERE scan_id=? AND station_id=? "
                "ORDER BY value DESC", (scan_id, sid)),
        }
        out.append(d)
    return out


def _ship_loadouts(conn, scan_id) -> dict[str, list[dict]]:
    """ship object_id → its equipment, each resolved to a display name.

    Reads the ship_equipment rows and joins them against the generated catalog
    (data/equipment_stats.py) so the UI gets ready-to-show names without owning
    any resolution logic. Falls back through EQUIPMENT_ALIASES, then to the raw
    macro if a piece of gear somehow isn't in the catalog (e.g. a mod's macro).
    """
    out: dict[str, list[dict]] = defaultdict(list)
    for r in conn.execute(
        "SELECT ship_id, slot_type, macro, count FROM ship_equipment "
        "WHERE scan_id=? ORDER BY slot_type, macro", (scan_id,),
    ):
        macro = r['macro']
        cat = EQUIPMENT_STATS.get(macro) or \
              EQUIPMENT_STATS.get(EQUIPMENT_ALIASES.get(macro, ''))
        entry = {
            'slot':  r['slot_type'],
            'macro': macro,
            'count': r['count'],
            'name':  cat['name'] if cat else macro,
            'mk':    cat.get('mk')   if cat else None,   # mark number, if any
            'race':  cat.get('race') if cat else None,   # maker faction, if any
            'size':  cat.get('size') if cat else None,   # S/M/L/XL mount size
        }
        if cat:
            # Flatten the catalog stats (damage/range/capacity/.../price) onto
            # the entry so the design card's stat columns have real numbers.
            entry.update({k: cat[k] for k in _EQUIP_STAT_KEYS if k in cat})
        out[r['ship_id']].append(entry)
    return out


def _ships(conn, scan_id) -> list[dict]:
    out = []
    loadouts = _ship_loadouts(conn, scan_id)
    # LEFT JOIN stations so each ship carries its homebase station code directly.
    # homebase_id is a station object_id (e.g. "[0x1ca1c]"); the JOIN resolves it
    # to the human-readable code (e.g. "TDD") without any Python-side lookup.
    # Ships with no homebase get homebase_code = NULL → the UI shows "—".
    for r in conn.execute(
        "SELECT s.*, st.code AS homebase_code "
        "FROM ships s "
        "LEFT JOIN stations st "
        "    ON st.scan_id = s.scan_id AND st.object_id = s.homebase_id "
        "WHERE s.scan_id = ?",
        (scan_id,),
    ):
        d = _drop(dict(r), 'scan_id')
        # Resolve the human-readable name the same way the CLI does — prefers the
        # player's custom name; falls back to the macro-derived type name (e.g.
        # "Magnetar Vanguard" or "Argon L Freighter (B)"). Stored as display_name
        # so the UI can show it without re-implementing resolution logic.
        d['display_name'] = ship_display_name(d.get('macro') or '', d.get('name'))
        # Hull TYPE name, independent of any custom ship name — the Designs view
        # titles each card by type (e.g. "Cerberus Vanguard"), not by a ship's
        # player-given name.
        d['type_name'] = resolve_ship_type(d.get('macro') or '')
        # Hull buy price (credits) — the base of the design's total cost.
        _hull = SHIP_STATS.get(d.get('macro') or '', {})
        d['hull_price'] = _hull.get('price')
        # Slot layout {type: {size: count}} — the blueprint builder uses it for
        # capacity, and the design cards show fitted/total per section.
        d['hardpoints'] = _hull.get('hardpoints')
        d['loadout'] = loadouts.get(d.get('object_id'), [])
        out.append(d)
    return out


def _fleet_summary(ships: list[dict]) -> dict:
    """Pre-digested role/size/order counts — saves an AI from re-aggregating."""
    by_role  = Counter(s.get('role')       for s in ships)
    by_size  = Counter(s.get('size')       for s in ships)
    by_order = Counter(s.get('ship_order') for s in ships)
    return {
        'total':    len(ships),
        'by_role':  dict(by_role),
        'by_size':  dict(by_size),
        'by_order': dict(by_order),
    }


def _npc_ships(conn, scan_id) -> list[dict]:
    """NPC ships in the player's station sectors (situational awareness)."""
    return [_drop(dict(r), 'scan_id')
            for r in conn.execute(
                "SELECT * FROM npc_ships WHERE scan_id=? "
                "ORDER BY sector_name, owner_name, role", (scan_id,))]


def _npc_presence(npc_ships: list[dict]) -> dict:
    """Digest NPC ships into sector → faction → role counts, so an AI gets a
    threat/activity read without re-aggregating ~300 rows."""
    out: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for s in npc_ships:
        out[s['sector_name']][s['owner_name']][s['role']] += 1
    return {
        sector: {fac: dict(roles) for fac, roles in facs.items()}
        for sector, facs in out.items()
    }


def _crew(conn, scan_id) -> list[dict]:
    return [_drop(dict(r), 'scan_id')
            for r in conn.execute("SELECT * FROM crew WHERE scan_id=?", (scan_id,))]


def _reputation(conn, scan_id) -> list[dict]:
    return _rows(
        conn,
        "SELECT faction_id, faction_name, value, base, booster, tier "
        "FROM reputation WHERE scan_id=? ORDER BY value DESC", (scan_id,))


def _faction_relations(conn, scan_id) -> list[dict]:
    # Flat list, ordered subject-then-standing so each Diplomacy tab's rows
    # arrive display-ready (allies first). The UI groups by faction_id the
    # same way it groups npc_ships by owner.
    return _rows(
        conn,
        "SELECT faction_id, faction_name, other_id, other_name, value, tier, locked "
        "FROM faction_relations WHERE scan_id=? ORDER BY faction_id, value DESC",
        (scan_id,))


def _sector_resources(conn) -> dict[str, list[dict]]:
    """
    {sector_macro: [{ware, ware_name, yield_level, recharge_max, recharge_time}]}
    for every sector with mineable resources, richest yield first. ware_name comes
    from ware_metadata (falls back to the raw ware id when unnamed).
    """
    rows = _rows(
        conn,
        "SELECT sr.sector_macro, sr.ware, "
        "       COALESCE(wm.name, sr.ware) AS ware_name, "
        "       sr.yield_level, sr.recharge_max, sr.recharge_time "
        "FROM sector_resources sr "
        "LEFT JOIN ware_metadata wm ON wm.ware_id = sr.ware "
        "ORDER BY sr.recharge_max DESC")
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r.pop('sector_macro'), []).append(r)
    return out


def _sectors(conn) -> list[dict]:
    # Reference table — latest-only, so no scan_id filter.
    rows = _rows(
        conn,
        "SELECT sector_macro, sector_name, cluster_macro, cluster_name, "
        "owner_id, owner_name, sunlight, is_discovered FROM sectors "
        "ORDER BY sector_name")
    resources = _sector_resources(conn)
    for r in rows:
        # Stored as INTEGER 0/1 (and NULL on rows scanned before this column
        # existed); expose a real bool so the UI can treat it directly.
        r['is_discovered'] = bool(r['is_discovered'])
        r['resources'] = resources.get(r['sector_macro'], [])
    return rows


def _npc_station_counts(conn, scan_id) -> dict:
    """
    Returns {sector_macro: [{owner_id, owner_name, count}, ...]} for all NPC
    stations seen in this scan, sorted per sector by count descending.
    Used by the galaxy map hover panel to show faction presence per sector.
    """
    rows = conn.execute(
        "SELECT sector_macro, owner_id, owner_name, COUNT(*) AS count "
        "FROM npc_stations WHERE last_scan_id = ? AND sector_macro IS NOT NULL "
        "GROUP BY sector_macro, owner_id "
        "ORDER BY sector_macro, count DESC",
        (scan_id,),
    ).fetchall()
    result: dict = {}
    for r in rows:
        result.setdefault(r['sector_macro'], []).append({
            'owner_id':   r['owner_id'],
            'owner_name': r['owner_name'],
            'count':      r['count'],
        })
    return result


def _galaxy_map(conn, scan_id) -> dict:
    """
    Galaxy connectivity for this scan's player empire.

    Rebuilds the adjacency graph from the stored sector_links, then reports the
    jump distance from the NEAREST player-asset sector to every reachable sector
    (0-1 BFS: gate/accelerator hops cost 1, intra-cluster superhighways cost 0).

    Consumers get three things:
      - player_sectors: sectors that currently hold a player station
      - edges:          the full topology [sector_a, sector_b, cost], so a client
                        can recompute any distance it likes (per-station, etc.)
      - distances_from_player: {sector_macro: jumps} — min over all player sectors
    Sector names are not duplicated here; join sector_macro to the `sectors` key.
    """
    edge_rows = conn.execute(
        "SELECT sector_a, sector_b, cost FROM sector_links").fetchall()

    graph: dict[str, list[tuple[str, int]]] = {}
    for r in edge_rows:
        a, b, cost = r['sector_a'], r['sector_b'], r['cost']
        graph.setdefault(a, []).append((b, cost))
        graph.setdefault(b, []).append((a, cost))

    player_sectors = [
        r['sector_macro'] for r in conn.execute(
            "SELECT DISTINCT sector_macro FROM stations "
            "WHERE scan_id=? AND sector_macro IS NOT NULL", (scan_id,))
    ]
    distances = gm.distances_from(graph, player_sectors) if player_sectors else {}

    return {
        'player_sectors':        player_sectors,
        'edges':                 [[r['sector_a'], r['sector_b'], r['cost']]
                                  for r in edge_rows],
        'distances_from_player': distances,
    }


# The ledger stores ABSOLUTE game_time_s (it spans many scans). "Seconds ago"
# is relative to THIS scan's clock, so we compute it at export time.
def _ago(game_time: float, trade_time: float) -> float:
    return max(0.0, game_time - trade_time)


def _station_trades(conn, scan_id, game_time) -> list[dict]:
    # last_scan_id == scan_id → trades visible in THIS scan's log window.
    rows = conn.execute(
        "SELECT * FROM trade_history WHERE last_scan_id=? ORDER BY game_time_s DESC",
        (scan_id,)).fetchall()
    return [{
        'station_code':  r['station_code'],
        'station_name':  r['station_name'],
        'direction':     r['direction'],
        'ware':          r['ware_id'],
        'ware_name':     r['ware_name'],
        'amount':        r['amount'],
        'price_cr':      r['price_cr'],
        'total_cr':      r['total_cr'],
        'time_ago_s':    _ago(game_time, r['game_time_s']),
        'ship_code':     r['ship_code'],
        'ship_name':     r['ship_name'],
        'counterparty':  r['counterparty_name'],
        # How the counterparty was resolved, so consumers can weight
        # confidence. PROVEN: direct/courier. INFERRED: homebase/visit/sector/
        # delivery. '' = unresolved (counterparty is null).
        'resolution':    r['resolution'],
    } for r in rows]


def _mining(conn, scan_id, game_time) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM trade_history_mining WHERE last_scan_id=? ORDER BY game_time_s DESC",
        (scan_id,)).fetchall()
    return [{
        'station_code': r['station_code'], 'station_name': r['station_name'],
        'ship_code':    r['ship_code'],    'ship_name':    r['ship_name'],
        'ware':         r['ware_id'],      'ware_name':    r['ware_name'],
        'amount':       r['amount'],       'price_cr':     r['price_cr'],
        'total_cr':     r['total_cr'],     'time_ago_s':   _ago(game_time, r['game_time_s']),
    } for r in rows]


def _internal(conn, scan_id, game_time) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM trade_history_internal WHERE last_scan_id=? ORDER BY game_time_s DESC",
        (scan_id,)).fetchall()
    return [{
        'station_a_code': r['station_a_code'], 'station_a_name': r['station_a_name'],
        'station_b_code': r['station_b_code'], 'station_b_name': r['station_b_name'],
        'ship_code':      r['ship_code'],      'ship_name':      r['ship_name'],
        'ware':           r['ware_id'],        'ware_name':      r['ware_name'],
        'amount':         r['amount'],         'price_cr':       r['price_cr'],
        'total_cr':       r['total_cr'],       'time_ago_s':     _ago(game_time, r['game_time_s']),
    } for r in rows]


# Unique scripted boss/superstructure hulls — they have a real wares.xml owner
# (so SHIP_STATS marks them flown) but aren't a normal ship anyone pilots or
# captures; they're one-off multi-part battle set-pieces. No static-file flag
# distinguishes this from a regular capturable Xenon/Kha'ak hull, so this list
# is manually curated — cross-checked against qsna.eu's X4 ship builder, which
# also omits it.
_MANUAL_HULL_EXCLUSIONS = {'ship_xen_xl_mothership_01_a_macro'}


def _hull_catalog() -> dict:
    """All hulls with equipment slots → {name, class, max_hull, price, hardpoints,
    purchasable, weapon_heat_factor}.

    The blueprint builder's hull selector reads this. Keyed by macro; deployables/
    drones (no hardpoints), never-flown macros (flown=False — NPC skin variants,
    escape pods, colony-ship set-piece parts; nobody in the game world ever owns
    them), the whole ship_xs class, and _MANUAL_HULL_EXCLUSIONS are excluded so
    the selector only lists real, player-pilotable ships. XS has no
    player-flyable hull at all — it's drones, escape pods, satellites and
    AI-only police escorts; a few of those have a real owner + a stray
    engine/shield slot so they'd otherwise slip past the flown/hardpoints
    checks (e.g. ship_arg_xs_police_01_a). purchasable is False for hulls
    SHIP_STATS marks capture/story-only (Xenon, Kha'ak, a few unique faction
    ships) — still real, ownable ships, just never sold at a shipyard, so the
    UI can badge them instead of hiding them.
    """
    out = {}
    for macro, st in SHIP_STATS.items():
        hp = st.get('hardpoints')
        if (not hp or not st.get('flown', True) or st.get('class') == 'ship_xs'
                or macro in _MANUAL_HULL_EXCLUSIONS):
            continue
        out[macro] = {
            'name':        resolve_ship_type(macro),
            'class':       st.get('class'),
            'max_hull':    st.get('max_hull'),
            'price':       st.get('price'),
            'hardpoints':  hp,
            'purchasable': st.get('purchasable', True),
            # Ship-specific multiplier on mounted weapons' heat generation
            # (1.0 = no effect) -- the Ship Builder's weapon hover tooltip
            # needs this to show the correct Time to Overheat for the
            # currently selected hull; see SHIP_STATS' docstring.
            'weapon_heat_factor': st.get('weapon_heat_factor', 1.0),
        }
    return out


# ── Top-level assembly ─────────────────────────────────────────────────────────

def to_export(conn: sqlite3.Connection, scan_id: int | None = None) -> dict:
    """Build the export dict for one scan (default: the latest)."""
    if scan_id is None:
        row = conn.execute("SELECT MAX(scan_id) AS m FROM scans").fetchone()
        scan_id = row['m']
    if scan_id is None:
        raise ValueError("no scans in database to export")

    scan = conn.execute("SELECT * FROM scans WHERE scan_id=?", (scan_id,)).fetchone()
    if scan is None:
        raise ValueError(f"scan_id {scan_id} not found")

    total_scans = conn.execute("SELECT COUNT(*) AS n FROM scans").fetchone()['n']
    game_time = scan['game_time_s']
    ships = _ships(conn, scan_id)
    npc_ships = _npc_ships(conn, scan_id)

    return {
        'meta': {
            'scan_id':      scan['scan_id'],
            'scanned_at':   scan['scanned_at'],
            'save_file':    scan['save_file'],
            'game_time_s':  scan['game_time_s'],
            'scans_total':  total_scans,
        },
        'player': {
            'name':    scan['player_name'],
            'sector':  scan['player_sector'],
            'credits': scan['player_credits'],
        },
        'reputation':            _reputation(conn, scan_id),
        'faction_relations':     _faction_relations(conn, scan_id),
        'sectors':               _sectors(conn),
        'galaxy_map':            _galaxy_map(conn, scan_id),
        'npc_stations_by_sector': _npc_station_counts(conn, scan_id),
        'stations':              _stations(conn, scan_id),
        'ships':                 ships,
        'fleet_summary':         _fleet_summary(ships),
        # NPC ships operating in the player's station sectors + a digested
        # sector → faction → role presence summary.
        'npc_ships':             npc_ships,
        'npc_presence':          _npc_presence(npc_ships),
        'crew':                  _crew(conn, scan_id),
        'station_trades':        _station_trades(conn, scan_id, game_time),
        'mining_deliveries':     _mining(conn, scan_id, game_time),
        'internal_transfers':    _internal(conn, scan_id, game_time),
        # TradeHandler not implemented yet — kept for shape stability.
        'active_trades':         [],
        'in_progress_deliveries': [],
        # Static game price bands — min/average/max per ware ID.
        # Read from the ware_prices DB table (populated at connection time from
        # data/ware_prices.py) so no Python dict import is needed here.
        'ware_prices': {
            r['ware_id']: {
                'min':     r['price_min'],
                'average': r['price_avg'],
                'max':     r['price_max'],
            }
            for r in conn.execute("SELECT * FROM ware_prices ORDER BY ware_id")
        },
        # Full equipment catalog (macro → name/stats/price), invariant across
        # scans. Embedded here so both the bridge and the dev-browser fetch path
        # get it; the blueprint builder's fit panel reads it to list compatible
        # gear per slot/size.
        'equipment_catalog': dict(EQUIPMENT_STATS),
        # All buildable hulls (name + slot layout + price) for the builder's
        # hull selector.
        'hull_catalog': _hull_catalog(),
    }


def write_export(conn: sqlite3.Connection,
                 out_path: str | Path,
                 scan_id: int | None = None) -> Path:
    """Build the export and write it to out_path as pretty JSON. Returns the path."""
    data = to_export(conn, scan_id)
    out = Path(out_path)
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
    return out
