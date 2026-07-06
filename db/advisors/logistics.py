"""Core role: Logistics-domain advisor rules (idle haulers sitting on surplus).

See advisors.py for the shared _finding() renderer, and __init__.py's
compute_advisors() for how these rules combine with other domains into one
findings list.
"""
from __future__ import annotations
from .advisors import _finding

# A freighter/transport under this cargo fill fraction, sitting at a station
# with something to move, is "idle" for advisor purposes.
IDLE_FILL_THRESHOLD = 0.15

# 3 phrasings per finding type so the feed doesn't read as copy-pasted.
TEMPLATES: dict[str, list[str]] = {
    'idle_hauler': [
        "{ship_name} is only {fill_pct}% loaded while its home station "
        "{station_name} builds up surplus — assign it a route to use that "
        "{cargo_max} m3 of capacity.",
        "{station_name} is overproducing while its hauler {ship_name} rides "
        "mostly empty ({fill_pct}% full) — put that {cargo_max} m3 bay to work.",
        "Idle capacity: {ship_name} ({cargo_max} m3) is nearly empty at "
        "{station_name}, which has surplus ready to move.",
    ],
}


# ── Rule: idle hauler at a surplus-producing home station ───────────────────

def idle_hauler_findings(conn, scan_id) -> list[dict]:
    surplus_stations = {r['station_id'] for r in conn.execute(
        "SELECT DISTINCT station_id FROM station_production_analytics "
        "WHERE scan_id = ? AND surplus_rate > 0", (scan_id,))}
    if not surplus_stations:
        return []

    rows = conn.execute(
        "SELECT sh.object_id, sh.code, sh.name, sh.homebase_id, "
        "       sh.cargo_m3, sh.cargo_max_m3, "
        "       s.code AS station_code, s.name AS station_name "
        "FROM ships sh "
        "JOIN stations s ON s.object_id = sh.homebase_id AND s.scan_id = sh.scan_id "
        "WHERE sh.scan_id = ? AND sh.role IN ('Freighter', 'Transport') "
        "  AND sh.cargo_max_m3 IS NOT NULL AND sh.cargo_max_m3 > 0",
        (scan_id,))
    findings = []
    for r in rows:
        if r['homebase_id'] not in surplus_stations:
            continue
        fill = (r['cargo_m3'] or 0) / r['cargo_max_m3']
        if fill >= IDLE_FILL_THRESHOLD:
            continue
        # Bigger idle bay = bigger missed opportunity; simplest available proxy
        # since we don't know what THIS ship would earn per trip.
        priority = r['cargo_max_m3'] * (1 - fill)
        slots = {
            'ship_name':    r['name'] or r['code'],
            'station_name': r['station_name'] or r['station_code'],
            'fill_pct':     round(fill * 100),
            'cargo_max':    round(r['cargo_max_m3']),
        }
        evidence = {
            'ship_id': r['object_id'], 'homebase_id': r['homebase_id'],
            'cargo_m3': r['cargo_m3'], 'cargo_max_m3': r['cargo_max_m3'],
        }
        findings.append(_finding(
            f"idle:{r['object_id']}",
            'logistics', 'idle_hauler', priority, slots, evidence, TEMPLATES))
    return findings
