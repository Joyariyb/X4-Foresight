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
        d['inventory'] = {
            r['ware_id']: r['amount']
            for r in conn.execute(
                "SELECT ware_id, amount FROM station_inventory "
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
        out.append(d)
    return out


def _ships(conn, scan_id) -> list[dict]:
    return [_drop(dict(r), 'scan_id')
            for r in conn.execute("SELECT * FROM ships WHERE scan_id=?", (scan_id,))]


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
        "SELECT sector_macro, sector_name, cluster_name, owner_id, owner_name, "
        "sunlight FROM sectors ORDER BY sector_name")


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
        'stations':              _stations(conn, scan_id),
        'ships':                 ships,
        'fleet_summary':         _fleet_summary(ships),
        'crew':                  _crew(conn, scan_id),
        'station_trades':        _station_trades(conn, scan_id, game_time),
        'mining_deliveries':     _mining(conn, scan_id, game_time),
        'internal_transfers':    _internal(conn, scan_id, game_time),
        # TradeHandler not implemented yet — kept for shape stability.
        'active_trades':         [],
        'in_progress_deliveries': [],
    }


def write_export(conn: sqlite3.Connection,
                 out_path: str | Path,
                 scan_id: int | None = None) -> Path:
    """Build the export and write it to out_path as pretty JSON. Returns the path."""
    data = to_export(conn, scan_id)
    out = Path(out_path)
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
    return out
