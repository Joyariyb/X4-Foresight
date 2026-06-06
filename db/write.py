"""
v2/db/write.py

write_scan(conn, ctx) — persist one ScanContext to the database.

The DB is the source of truth for scan_id: we INSERT the scans row, take the
auto-incremented id, and stamp every child row with it (ignoring the placeholder
scan_id the scanner stamped on the entities).

Three storage classes, handled differently (see schema.sql):
  HISTORY    one row per entity, this scan      → plain INSERT
  LEDGER     each trade once, dedup by trade_key → INSERT ... ON CONFLICT
  REFERENCE  galaxy data, latest-only           → INSERT OR REPLACE

NPC ships are deliberately NOT persisted per-scan: there are ~12k of them, they
are transient context, and trade rows already carry resolved ship names. Only
player-owned ships go into the history `ships` table.
"""
from __future__ import annotations
import sqlite3
from datetime import datetime, timezone

from data.wares import WARE_NAMES
from scanner.ship_names import ship_display_name


def _ware_name(ware_id: str) -> str:
    return WARE_NAMES.get(ware_id, ware_id.replace('_', ' ').title())


def _cargo(cs):
    """Flatten a CargoStorage|None into (m3, max_m3, pct, adj_pct)."""
    if cs is None:
        return (None, None, None, None)
    return (cs.m3, cs.max_m3, cs.pct, cs.adj_pct)


def _trade_key(*parts) -> str:
    """Synthetic unique id for a completed trade — the economy log has none."""
    return ':'.join('' if p is None else str(p) for p in parts)


# Resolution confidence rank, as a SQL CASE over a resolution column. Used so a
# later scan can UPGRADE a counterparty (proven > inferred > blank) but never
# downgrade one. Applied to both excluded (new) and existing rows.
def _rank(col: str) -> str:
    return (
        f"(CASE {col} "
        "WHEN 'direct' THEN 3 WHEN 'courier' THEN 3 "
        "WHEN 'homebase' THEN 1 WHEN 'visit' THEN 1 "
        "WHEN 'sector' THEN 1 WHEN 'delivery' THEN 1 "
        "WHEN 'docked' THEN 1 WHEN 'despawned' THEN 1 "
        "ELSE 0 END)"
    )


def write_scan(conn: sqlite3.Connection, ctx) -> int:
    """Persist ctx and return the new scan_id."""
    cur = conn.cursor()

    # ── ROOT ──────────────────────────────────────────────────────────────────
    cur.execute(
        "INSERT INTO scans(scanned_at, save_file, game_time_s, "
        "player_name, player_sector, player_credits) VALUES(?,?,?,?,?,?)",
        (datetime.now(timezone.utc).isoformat(timespec='seconds'),
         ctx.save_file, ctx.game_time_s,
         ctx.player_name, ctx.player_sector, ctx.player_credits),
    )
    scan_id = cur.lastrowid

    _write_reputation(cur, scan_id, ctx)
    _write_stations(cur, scan_id, ctx)
    _write_ships(cur, scan_id, ctx)
    _write_npc_ships(cur, scan_id, ctx)
    _write_crew(cur, scan_id, ctx)
    _write_active(cur, scan_id, ctx)
    _write_ledger(cur, scan_id, ctx)
    _write_reference(cur, scan_id, ctx)

    conn.commit()
    return scan_id


# ── HISTORY ────────────────────────────────────────────────────────────────────

def _write_reputation(cur, scan_id, ctx) -> None:
    cur.executemany(
        "INSERT INTO reputation VALUES(?,?,?,?,?,?,?)",
        [(scan_id, r.faction_id, r.faction_name, r.value, r.base, r.booster, r.tier)
         for r in ctx.reputation],
    )


def _write_stations(cur, scan_id, ctx) -> None:
    for s in ctx.stations:
        cur.execute(
            "INSERT INTO stations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (scan_id, s.object_id, s.code, s.name, s.sector_macro, s.status,
             s.module_count, s.hull_hp, s.hull_max, s.hull_pct,
             s.shield_hp, s.shield_max, s.shield_pct,
             *_cargo(s.cargo_total),
             s.account_amount, s.budget_total, s.budget_sunlight),
        )
        for typ, cs in (('container', s.cargo_container),
                        ('solid',     s.cargo_solid),
                        ('liquid',    s.cargo_liquid)):
            if cs is not None:
                cur.execute(
                    "INSERT INTO station_cargo VALUES(?,?,?,?,?,?,?)",
                    (scan_id, s.object_id, typ, cs.m3, cs.max_m3, cs.pct, cs.adj_pct),
                )
        cur.executemany(
            "INSERT INTO station_modules VALUES(?,?,?,?,?)",
            [(scan_id, s.object_id, m.macro, m.category, m.produces) for m in s.modules],
        )
        cur.executemany(
            "INSERT INTO station_inventory VALUES(?,?,?,?,?)",
            [(scan_id, s.object_id, w, _ware_name(w), a) for w, a in s.inventory.items()],
        )


def _write_ships(cur, scan_id, ctx) -> None:
    # Player-owned ships only (see module docstring).
    cur.executemany(
        "INSERT INTO ships VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [(scan_id, sh.object_id, sh.code, sh.name, sh.ship_class, sh.size, sh.macro,
          sh.role, sh.owner_id, sh.owner_name, sh.hull_origin_id, sh.hull_origin_name,
          sh.sector_macro, sh.order, sh.homebase_id, sh.docked_at, sh.commander_id,
          int(sh.under_construction), sh.hull_hp, sh.hull_max, sh.hull_pct,
          sh.shield_hp, sh.shield_max, sh.shield_pct, sh.cargo_m3, sh.cargo_max_m3,
          sh.pilot_id)
         for sh in ctx.ships if sh.owner_id == 'player'],
    )


def _write_npc_ships(cur, scan_id, ctx) -> None:
    """
    NPC ships operating in the player's STATION sectors — situational awareness.

    We capture every NPC ship's identity during the scan; here we keep only the
    ones whose sector contains a player station (a bounded, strategically
    relevant subset), resolve a readable type name, and attach a destination
    station for the ones currently mid-delivery.
    """
    pstn_sectors = {s.sector_macro for s in ctx.stations if s.sector_macro}
    if not pstn_sectors:
        return
    sect_name = {sec.sector_macro: sec.sector_name for sec in ctx.sectors}

    rows = []
    for s in ctx.ships:
        if s.owner_id == 'player' or s.sector_macro not in pstn_sectors:
            continue
        # Where is it hauling, if mid-delivery? Resolve to a station name.
        dest = None
        dest_id = ctx.delivery_dest_index.get(s.object_id)
        if dest_id:
            d = ctx.npc_station_index.get(dest_id)
            dest = d.name if d else None
        rows.append((
            scan_id, s.object_id, s.code, ship_display_name(s.macro, s.name),
            s.ship_class, s.size, s.macro, s.role, s.owner_id, s.owner_name,
            s.sector_macro, sect_name.get(s.sector_macro), dest,
            s.order or "Idle",
        ))
    cur.executemany(
        "INSERT INTO npc_ships VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)


def _write_crew(cur, scan_id, ctx) -> None:
    cur.executemany(
        "INSERT INTO crew VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [(scan_id, c.role, c.name, c.object_id, c.seed, c.assigned_code,
          c.assigned_type, c.sector_macro, c.faction, c.gender,
          c.skill_piloting, c.skill_management, c.skill_morale,
          c.skill_engineering, c.skill_boarding)
         for c in ctx.crew],
    )


def _write_active(cur, scan_id, ctx) -> None:
    cur.executemany(
        "INSERT INTO active_trades VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [(scan_id, t.station_id, t.station_code, t.station_name, t.direction,
          t.ship_id, t.ship_code, t.ship_name, t.ware_id, t.ware_name,
          t.amount, t.price_cr, t.total_cr, t.counterparty_id, t.counterparty_name)
         for t in ctx.active_trades],
    )
    cur.executemany(
        "INSERT INTO active_auto_trades VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [(scan_id, t.ship_id, t.ship_code, t.ship_name,
          t.buyer_id, t.buyer_code, t.buyer_name,
          t.seller_id, t.seller_code, t.seller_name,
          t.ware_id, t.ware_name, t.amount, t.price_cr, t.total_cr)
         for t in ctx.active_auto_trades],
    )


# ── LEDGER (dedup + counterparty upgrade) ──────────────────────────────────────

def _write_ledger(cur, scan_id, ctx) -> None:
    new_rank = _rank('excluded.resolution')
    old_rank = _rank('trade_history.resolution')
    th_sql = f"""
        INSERT INTO trade_history(
            trade_key, first_scan_id, last_scan_id, station_id, station_code,
            station_name, direction, ship_id, ship_code, ship_name, ware_id,
            ware_name, amount, price_cr, total_cr, counterparty_id,
            counterparty_name, resolution, game_time_s)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(trade_key) DO UPDATE SET
            last_scan_id = excluded.last_scan_id,
            counterparty_id   = CASE WHEN {new_rank} > {old_rank}
                                     THEN excluded.counterparty_id
                                     ELSE trade_history.counterparty_id END,
            counterparty_name = CASE WHEN {new_rank} > {old_rank}
                                     THEN excluded.counterparty_name
                                     ELSE trade_history.counterparty_name END,
            resolution        = CASE WHEN {new_rank} > {old_rank}
                                     THEN excluded.resolution
                                     ELSE trade_history.resolution END
    """
    cur.executemany(th_sql, [
        (_trade_key(t.game_time_s, t.station_id, t.direction, t.ware_id, t.amount, t.ship_id),
         scan_id, scan_id, t.station_id, t.station_code, t.station_name, t.direction,
         t.ship_id, t.ship_code, t.ship_name, t.ware_id, t.ware_name, t.amount,
         t.price_cr, t.total_cr, t.counterparty_id, t.counterparty_name,
         t.resolution, t.game_time_s)
        for t in ctx.trade_history
    ])

    # Mining + internal carry no counterparty resolution — pure dedup, refresh
    # only last_scan_id when seen again.
    cur.executemany(f"""
        INSERT INTO trade_history_mining(
            trade_key, first_scan_id, last_scan_id, station_id, station_code,
            station_name, ship_id, ship_code, ship_name, ware_id, ware_name,
            amount, price_cr, total_cr, game_time_s)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(trade_key) DO UPDATE SET last_scan_id = excluded.last_scan_id
    """, [
        (_trade_key(t.game_time_s, t.station_id, 'mining', t.ware_id, t.amount, t.ship_id),
         scan_id, scan_id, t.station_id, t.station_code, t.station_name, t.ship_id,
         t.ship_code, t.ship_name, t.ware_id, t.ware_name, t.amount, t.price_cr,
         t.total_cr, t.game_time_s)
        for t in ctx.trade_history_mining
    ])

    cur.executemany(f"""
        INSERT INTO trade_history_internal(
            trade_key, first_scan_id, last_scan_id, station_a_id, station_a_code,
            station_a_name, station_b_id, station_b_code, station_b_name, ship_id,
            ship_code, ship_name, ware_id, ware_name, amount, price_cr, total_cr,
            game_time_s)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(trade_key) DO UPDATE SET last_scan_id = excluded.last_scan_id
    """, [
        (_trade_key(t.game_time_s, t.station_a_id, t.station_b_id, t.ware_id, t.amount, t.ship_id),
         scan_id, scan_id, t.station_a_id, t.station_a_code, t.station_a_name,
         t.station_b_id, t.station_b_code, t.station_b_name, t.ship_id, t.ship_code,
         t.ship_name, t.ware_id, t.ware_name, t.amount, t.price_cr, t.total_cr,
         t.game_time_s)
        for t in ctx.trade_history_internal
    ])


# ── REFERENCE (latest-only upsert) ─────────────────────────────────────────────

def _write_reference(cur, scan_id, ctx) -> None:
    cur.executemany(
        "INSERT OR REPLACE INTO sectors VALUES(?,?,?,?,?,?,?,?)",
        [(s.sector_macro, scan_id, s.sector_name, s.cluster_macro, s.cluster_name,
          s.owner_id, s.owner_name, s.sunlight) for s in ctx.sectors],
    )
    cur.executemany(
        "INSERT OR REPLACE INTO npc_stations VALUES(?,?,?,?,?,?,?,?,?)",
        [(n.object_id, scan_id, n.code, n.name, n.macro, n.station_type,
          n.sector_macro, n.owner_id, n.owner_name) for n in ctx.npc_stations],
    )
    ware_rows = [
        (n.object_id, w, _ware_name(w))
        for n in ctx.npc_stations for w in n.wares
    ]
    cur.executemany(
        "INSERT OR REPLACE INTO npc_station_wares VALUES(?,?,?)", ware_rows,
    )
