"""
v2/export/jsonexport.py

Builds the JSON export (x4_empire_state.json) that the UI and AI consume.

DB-READ, by design: the snapshot is read back FROM the database for a given
scan_id (default = latest). This is the permanent export path — when cross-scan
trends are added later they become extra queries here, with no rework, and the
same function can already export any historical scan.

Shape mirrors v1's top-level keys (stations / reputation / crew / station_trades
/ ships) so an AI that knows v1's JSON reads this unchanged, plus v2 additions:
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
from scanner.ship_names import ship_display_name
from data.production import consumption_rates_from_modules, display_name_to_id, units_per_hour
from data.ware_prices import WARE_PRICES
from data.wares import WARE_TRANSPORT


def _rows(conn, sql, params=()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def _drop(d: dict, *keys) -> dict:
    for k in keys:
        d.pop(k, None)
    return d


# ── Section builders ───────────────────────────────────────────────────────────

def _stations(conn, scan_id) -> list[dict]:
    out = []
    for s in conn.execute("SELECT * FROM stations WHERE scan_id=?", (scan_id,)):
        d = _drop(dict(s), 'scan_id')
        sid = d['object_id']
        # Inventory keyed by ware_id. Each entry carries:
        #   amount     — units currently in storage
        #   volume_m3  — total m³ occupied (amount × per-unit volume from the scanner)
        #   cargo_type — "container" | "solid" | "liquid" (from WARE_TRANSPORT lookup)
        # The UI uses volume_m3 / cargo_by_type[cargo_type].max_m3 for the storage bar.
        d['inventory'] = {
            r['ware_id']: {
                'amount':     r['amount'],
                'volume_m3':  r['volume_m3'],
                'cargo_type': WARE_TRANSPORT.get(r['ware_id'], 'container'),
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
        # Comma-separated produced-ware display names for the Production tab.
        # Display names (not ids) so they match WARE_COLOURS and read cleanly.
        produced = sorted({m['produces'] for m in d['modules'] if m['produces']})
        d['production'] = ','.join(produced)

        # Total units/hour per ware, calculated from module count × PRODUCTION_STATS
        # rate (accounting for sector sunlight on energy cells). Keyed by display name
        # to match WARE_COLOURS and the production string above.
        sector = d.get('sector_macro', '')
        module_counts: dict[str, int] = {}
        for m in d['modules']:
            if m['produces']:
                module_counts[m['produces']] = module_counts.get(m['produces'], 0) + 1
        d['production_rates'] = {
            name: units_per_hour(display_name_to_id(name), sector) * count
            for name, count in module_counts.items()
            if display_name_to_id(name)   # skip wares not in PRODUCTION_STATS (e.g. mineables)
        }
        # Units/hour consumed internally by all production modules, keyed by the
        # INPUT ware's display name. Used by the UI's second bar to show what
        # fraction of a ware's output is consumed by other modules here.
        d['consumption_rates'] = consumption_rates_from_modules(d['modules'])
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


def _ships(conn, scan_id) -> list[dict]:
    out = []
    for r in conn.execute("SELECT * FROM ships WHERE scan_id=?", (scan_id,)):
        d = _drop(dict(r), 'scan_id')
        # Resolve the human-readable name the same way the CLI does — prefers the
        # player's custom name; falls back to the macro-derived type name (e.g.
        # "Magnetar Vanguard" or "Argon L Freighter (B)"). Stored as display_name
        # so the UI can show it without re-implementing resolution logic.
        d['display_name'] = ship_display_name(d.get('macro') or '', d.get('name'))
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


def _sectors(conn) -> list[dict]:
    # Reference table — latest-only, so no scan_id filter.
    return _rows(
        conn,
        "SELECT sector_macro, sector_name, cluster_macro, cluster_name, "
        "owner_id, owner_name, sunlight FROM sectors ORDER BY sector_name")


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
        # v2 addition: how the counterparty was resolved, so consumers can weight
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
        # Passed through here so the UI can normalise trade prices without
        # needing the data hardcoded in JS or stored in the DB.
        'ware_prices':           WARE_PRICES,
    }


def write_export(conn: sqlite3.Connection,
                 out_path: str | Path,
                 scan_id: int | None = None) -> Path:
    """Build the export and write it to out_path as pretty JSON. Returns the path."""
    data = to_export(conn, scan_id)
    out = Path(out_path)
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
    return out
