"""Core role: Advisors package entry point — combines every domain's findings into one list.

Domains live in their own files (economy.py, logistics.py, military.py, ...);
shared helpers (the _finding() renderer, cross-domain lookups) live in
advisors.py. Adding a new domain (e.g. diplomacy) means adding a new file here
and one more `findings += ...` line below — the other domains are untouched.
"""
from __future__ import annotations
import sqlite3

from .advisors import ware_avg_prices, npc_demand_by_ware
from . import economy, logistics, military


def compute_advisors(conn: sqlite3.Connection, scan_id: int | None = None,
                      distances_from_current: dict[str, int] | None = None) -> dict:
    """Player-relative advisor findings for one scan.

    ``distances_from_current`` should be jsonexport's galaxy_map
    distances_from_current (jumps from where the player currently is) — the
    caller passes it in already computed rather than this module rebuilding
    the sector graph a second time, same convention as
    jsonexport._npc_trade_partners taking distances_from_player. An empty/
    missing dict (no resolvable current sector) simply means the NPC-facing
    rules find nothing to report — an empty findings list is a completely
    valid result on a fresh empire.

    Returns ``{'findings': [...]}``, highest priority_score first. No cap
    here — the UI decides how many to surface.
    """
    if scan_id is None:
        row = conn.execute("SELECT MAX(scan_id) AS m FROM scans").fetchone()
        scan_id = row['m']
    if scan_id is None:
        raise ValueError("no scans in database to compute advisors")

    distances_from_current = distances_from_current or {}
    avg_prices = ware_avg_prices(conn)
    demand_by_ware = npc_demand_by_ware(conn, scan_id, distances_from_current)

    findings: list[dict] = []
    findings += economy.overflow_risk_findings(conn, scan_id, avg_prices)
    findings += economy.market_opportunity_findings(conn, scan_id, demand_by_ware)
    findings += economy.pricing_gap_findings(conn, scan_id, demand_by_ware)
    findings += logistics.idle_hauler_findings(conn, scan_id)
    findings += military.hostile_presence_findings(conn, scan_id, distances_from_current)
    findings += military.damaged_fleet_findings(conn, scan_id)

    findings.sort(key=lambda f: -f['priority_score'])
    return {'findings': findings}
