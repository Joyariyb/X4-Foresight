"""Core role: Advisors combiner — merges every domain's findings into one list.

Domains live in their own files (economy.py, logistics.py, military.py, ...);
shared helpers (the _finding() renderer, cross-domain lookups) live in
advisors.py. Adding a new domain (e.g. diplomacy) means adding a new file here
and one more `findings += ...` line below — the other domains are untouched.

Deliberately NOT in __init__.py: ui/web/generate_manifest.py skips every
__init__.py when staging files for the Pyodide build (GitHub Pages' Jekyll
build 404s underscore-prefixed files, and every other __init__.py in this repo
really is an empty marker). A normally-named module keeps that assumption true
and gets staged like any other file.
"""
from __future__ import annotations
import sqlite3

from .advisors import ware_avg_prices, npc_demand_by_ware, merge_anchors
from . import economy, logistics, military, trader


def compute_advisors(conn: sqlite3.Connection, scan_id: int | None = None,
                      distances_from_player: dict[str, int] | None = None,
                      distances_from_current: dict[str, int] | None = None) -> dict:
    """Player-relative advisor findings for one scan.

    Both distance dicts come from jsonexport's galaxy_map, already computed
    by the caller rather than this module rebuilding the sector graph a
    second time (same convention as jsonexport._npc_trade_partners taking
    distances_from_player):
      - ``distances_from_player``: jumps from the NEAREST PLAYER STATION —
        drives the economy rules, since a trade route starts at the surplus
        station regardless of where the avatar is standing.
      - ``distances_from_current``: jumps from the avatar's CURRENT sector —
        merged with distances_from_player (advisors.merge_anchors) to drive
        the distance-aware military rules, since a threat can be sitting on
        a player asset OR right where the avatar currently is.
    Missing/empty dicts simply mean the corresponding rules find nothing to
    report — an empty findings list is a completely valid result on a fresh
    empire.

    Returns ``{'findings': [...]}``, highest priority_score first. No cap
    here — the UI decides how many to surface.
    """
    if scan_id is None:
        row = conn.execute("SELECT MAX(scan_id) AS m FROM scans").fetchone()
        scan_id = row['m']
    if scan_id is None:
        raise ValueError("no scans in database to compute advisors")

    distances_from_player = distances_from_player or {}
    distances_from_current = distances_from_current or {}
    military_jumps, military_anchor = merge_anchors(
        distances_from_player, distances_from_current)

    avg_prices = ware_avg_prices(conn)
    demand_by_ware = npc_demand_by_ware(conn, scan_id, distances_from_player)
    # Shared by the four force-based military rules — same convention as
    # demand_by_ware above (compute the expensive lookup once, pass it in).
    forces = military.threat_forces(conn, scan_id)

    findings: list[dict] = []
    findings += economy.overflow_risk_findings(conn, scan_id, avg_prices)
    findings += economy.market_opportunity_findings(conn, scan_id, demand_by_ware)
    findings += economy.pricing_gap_findings(conn, scan_id, demand_by_ware)
    findings += logistics.idle_hauler_findings(conn, scan_id)
    findings += trader.station_siting_findings(
        conn, scan_id, distances_from_player, avg_prices)
    findings += trader.galaxy_arbitrage_findings(conn, scan_id, distances_from_player)
    findings += trader.stranded_delivery_findings(conn, scan_id, avg_prices)
    findings += trader.idle_trade_capital_findings(conn, scan_id)
    findings += military.hostile_presence_findings(
        conn, scan_id, military_jumps, military_anchor, forces)
    findings += military.composition_gap_findings(
        conn, scan_id, military_jumps, military_anchor, forces)
    findings += military.outranged_findings(
        conn, scan_id, military_jumps, military_anchor, forces)
    findings += military.buildup_findings(
        conn, scan_id, military_jumps, military_anchor, forces)
    findings += military.damaged_fleet_findings(conn, scan_id)

    findings.sort(key=lambda f: -f['priority_score'])
    return {'findings': findings}
