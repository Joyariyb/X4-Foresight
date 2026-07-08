"""Core role: Economy-domain advisor rules (overflow risk, market opportunity, pricing gap).

See advisors.py for the shared _finding() renderer and lookups this module
builds on, and __init__.py's compute_advisors() for how these rules combine
with other domains into one findings list.
"""
from __future__ import annotations
from .advisors import _finding

# A station whose surplus will overflow its cargo bay within this many
# in-game hours is worth flagging now, while there's still time to react.
OVERFLOW_HOURS_THRESHOLD = 24.0

# 3 phrasings per finding type so the feed doesn't read as copy-pasted.
TEMPLATES: dict[str, list[str]] = {
    'overflow_risk': [
        "{station_name} in {sector_name} will hit cargo capacity for {ware_name} "
        "in about {hours}h — {value_per_hour} Cr/hr of production will go to "
        "waste once it caps.",
        "Heads up: {ware_name} at {station_name} ({sector_name}) caps out in "
        "~{hours}h. That's {value_per_hour} Cr/hr sitting idle once the bay fills.",
        "{station_name} is about to overflow on {ware_name} (~{hours}h left) — "
        "add storage or a hauler before {value_per_hour} Cr/hr of output backs up.",
    ],
    'market_opportunity': [
        "{station_name} is producing surplus {ware_name} — {npc_name} "
        "({jumps} jump(s) away) is buying it at {price} Cr/unit, worth roughly "
        "{value_per_hour} Cr/hr if routed there.",
        "Sell opportunity: your {ware_name} surplus at {station_name} could go "
        "to {npc_name}, {jumps} jump(s) out, paying {price} Cr/unit "
        "(~{value_per_hour} Cr/hr).",
        "{npc_name} wants more {ware_name} and is only {jumps} jump(s) from "
        "{station_name}'s surplus — worth roughly {value_per_hour} Cr/hr.",
    ],
    'pricing_gap': [
        "You're selling {ware_name} at {station_name} for {player_price} Cr/unit, "
        "but {npc_name} pays {npc_price} Cr/unit ({jumps} jump(s) away) — "
        "re-routing your stock there could gain ~{gain} Cr.",
        "{npc_name} pays {npc_price} Cr for {ware_name} vs your {player_price} Cr "
        "at {station_name} — a gap worth ~{gain} Cr on your current stock.",
        "Pricing gap: {station_name}'s {ware_name} sells for {player_price} Cr, "
        "but {npc_name} ({jumps} jump(s) away) offers {npc_price} Cr — "
        "~{gain} Cr on the table.",
    ],
}


# ── Rule 1: production overflow risk ─────────────────────────────────────────

def overflow_risk_findings(conn, scan_id, avg_prices) -> list[dict]:
    rows = conn.execute(
        "SELECT spa.station_id, spa.ware_id, spa.ware_name, spa.surplus_rate, "
        "       spa.time_to_cap_hours, s.code, s.name AS station_name, "
        "       sec.sector_name "
        "FROM station_production_analytics spa "
        "JOIN stations s ON s.object_id = spa.station_id AND s.scan_id = spa.scan_id "
        "LEFT JOIN sectors sec ON sec.sector_macro = s.sector_macro "
        "WHERE spa.scan_id = ? AND spa.surplus_rate > 0 "
        "  AND spa.time_to_cap_hours IS NOT NULL "
        "  AND spa.time_to_cap_hours <= ?",
        (scan_id, OVERFLOW_HOURS_THRESHOLD))
    findings = []
    for r in rows:
        value_per_hour = r['surplus_rate'] * avg_prices.get(r['ware_id'], 0)
        if value_per_hour <= 0:
            continue
        # Urgency-weighted: same value/hr scores higher the sooner it caps.
        priority = value_per_hour / max(r['time_to_cap_hours'], 1.0)
        slots = {
            'station_name': r['station_name'] or r['code'],
            'sector_name':  r['sector_name'] or 'an unknown sector',
            'ware_name':    r['ware_name'],
            'hours':        round(r['time_to_cap_hours'], 1),
            'value_per_hour': round(value_per_hour),
        }
        evidence = {
            'station_id': r['station_id'], 'code': r['code'],
            'ware_id': r['ware_id'], 'surplus_rate': r['surplus_rate'],
            'time_to_cap_hours': r['time_to_cap_hours'],
        }
        findings.append(_finding(
            f"overflow:{r['station_id']}:{r['ware_id']}",
            'economy', 'overflow_risk', priority, slots, evidence, TEMPLATES))
    return findings


# ── Rule 2: market opportunity (surplus -> reachable NPC demand) ─────────────

def market_opportunity_findings(conn, scan_id, demand_by_ware) -> list[dict]:
    rows = conn.execute(
        "SELECT spa.station_id, spa.ware_id, spa.ware_name, spa.surplus_rate, "
        "       s.code, s.name AS station_name "
        "FROM station_production_analytics spa "
        "JOIN stations s ON s.object_id = spa.station_id AND s.scan_id = spa.scan_id "
        "WHERE spa.scan_id = ? AND spa.surplus_rate > 0",
        (scan_id,))
    findings = []
    for r in rows:
        demands = demand_by_ware.get(r['ware_id'])
        if not demands:
            continue
        # Nearest genuine buyer first; ties broken by deepest unmet demand.
        best = min(demands, key=lambda d: (d['jumps'], -d['demand_depth']))
        price_cr = (best['price'] or 0) / 100.0
        # Distance-dampened: a farther buyer is less actionable right now.
        value_per_hour = r['surplus_rate'] * price_cr / (1 + best['jumps'])
        if value_per_hour <= 0:
            continue
        slots = {
            'station_name': r['station_name'] or r['code'],
            'ware_name':    r['ware_name'],
            'npc_name':     best['station_name'] or best['code'],
            'jumps':        best['jumps'],
            'price':        round(price_cr, 1),
            'value_per_hour': round(value_per_hour),
        }
        evidence = {
            'station_id': r['station_id'], 'ware_id': r['ware_id'],
            'surplus_rate': r['surplus_rate'], 'npc_station_id': best['object_id'],
            'jumps': best['jumps'], 'demand_depth': best['demand_depth'],
        }
        findings.append(_finding(
            f"marketgap:{r['station_id']}:{r['ware_id']}:{best['object_id']}",
            'economy', 'market_opportunity', value_per_hour, slots, evidence,
            TEMPLATES))
    return findings


# ── Rule 3: pricing gap (player selling below a reachable NPC buyer) ────────

def pricing_gap_findings(conn, scan_id, demand_by_ware) -> list[dict]:
    # The player's own SELL side of each ware — sell_price/sell_amount aliased
    # to the generic names the gap math below reads. A co-posted buy offer for
    # the same ware keeps its own columns and can't skew the sell price here.
    rows = conn.execute(
        "SELECT so.station_id, so.ware_id, so.ware_name, "
        "       so.sell_price AS price, so.sell_amount AS amount, "
        "       s.code, s.name AS station_name "
        "FROM station_offers so "
        "JOIN stations s ON s.object_id = so.station_id AND s.scan_id = so.scan_id "
        "WHERE so.scan_id = ? AND so.is_selling = 1 AND so.sell_price IS NOT NULL",
        (scan_id,))
    findings = []
    for r in rows:
        demands = demand_by_ware.get(r['ware_id'])
        if not demands:
            continue
        # Best payer net of distance dampening — matches the opportunity rule's
        # weighting so a much-closer, slightly-lower offer can still win.
        best = max(demands, key=lambda d: (d['price'] or 0) / (1 + d['jumps']))
        gap_cents = (best['price'] or 0) - r['price']
        if gap_cents <= 0:
            continue
        # One-time estimate: what re-routing the CURRENTLY STOCKED units would
        # gain, not a rate — station_offers has no throughput figure of its own.
        gain = gap_cents / 100.0 * (r['amount'] or 0)
        if gain <= 0:
            continue
        slots = {
            'station_name': r['station_name'] or r['code'],
            'ware_name':    r['ware_name'],
            'npc_name':     best['station_name'] or best['code'],
            'jumps':        best['jumps'],
            'player_price': round(r['price'] / 100.0, 1),
            'npc_price':    round((best['price'] or 0) / 100.0, 1),
            'gain':         round(gain),
        }
        evidence = {
            'station_id': r['station_id'], 'ware_id': r['ware_id'],
            'player_price_cents': r['price'], 'npc_price_cents': best['price'],
            'npc_station_id': best['object_id'], 'jumps': best['jumps'],
            'amount': r['amount'],
        }
        findings.append(_finding(
            f"pricing:{r['station_id']}:{r['ware_id']}:{best['object_id']}",
            'economy', 'pricing_gap', gain, slots, evidence, TEMPLATES))
    return findings
