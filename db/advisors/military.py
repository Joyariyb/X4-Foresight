"""Core role: Military-domain advisor rules (hostile presence near the player, damaged combat ships).

See advisors.py for the shared _finding() renderer, and __init__.py's
compute_advisors() for how these rules combine with other domains into one
findings list.

Hostility is decided by REPUTATION (value <= -25, mirroring
ReputationEntry.is_hostile in scanner/entities.py), not by hull origin —
the UI's Xenon/Yaki/Kha'ak origin list is a display shortcut, and a faction
the player has personally angered is just as much a threat as the Xenon.

v1 deliberately sticks to presence and damage-state rules: SHIP_STATS has no
speed or maneuverability fields yet (see the weapon-stats gap in the project
backlog), so "can that fleet actually catch my hauler" routing advice is
impossible to score honestly. Extending gamefiles/generate_data.py to pull
speed from the ship macros' physics block is its own prerequisite batch —
don't guess at synthetic speed values here.
"""
from __future__ import annotations
from .advisors import _finding, ADVISOR_MAX_JUMPS

# Same combat-role taxonomy as the fleet-composition trend series, imported
# rather than copied — trends.py already warns its own copy must stay in sync
# with jsonexport's, and a third hand-maintained list would only widen that
# trap.
from db.trends import _role_bucket

# Mirrors ReputationEntry.is_hostile (scanner/entities.py): at or below this
# value the faction actively attacks the player.
HOSTILE_REPUTATION = -25.0

# A combat-role hostile counts this many times a non-combat one when scoring
# a sector's threat. A lone Xenon freighter passing through is noise; a lone
# Xenon fighter is not.
COMBAT_SHIP_WEIGHT = 4

# Scores are "threat points", meaningful only relative to other military
# findings — the UI renders each domain's list separately, so they never
# compete with economy's Cr/hr magnitudes for rail height. The scale factor
# just keeps small counts from rounding into indistinguishable single digits.
THREAT_SCALE = 100

# A combat ship under this hull percentage, flying around undocked, should
# see a repair dock before its next engagement. Shields regenerate on their
# own, so hull is the signal that persists between fights.
DAMAGED_HULL_PCT = 75.0

# 3 phrasings per finding type so the feed doesn't read as copy-pasted.
TEMPLATES: dict[str, list[str]] = {
    'hostile_presence': [
        "{faction_name} has {ship_count} ship(s) in {sector_name}, "
        "{jumps} jump(s) from your position — {combat_count} of them combat "
        "vessels. Check your defences there.",
        "Hostile activity: {combat_count} combat ship(s) among {ship_count} "
        "{faction_name} vessel(s) spotted in {sector_name}, {jumps} jump(s) "
        "away from you.",
        "{sector_name} ({jumps} jump(s) out) has {faction_name} presence — "
        "{ship_count} ship(s), {combat_count} armed for combat. Your assets "
        "there may need cover.",
    ],
    'damaged_fleet': [
        "{ship_name} is down to {hull_pct}% hull in {sector_name} and isn't "
        "docked anywhere — send it for repairs before its next fight.",
        "Repair needed: {ship_name} ({role}) is flying at {hull_pct}% hull "
        "in {sector_name}. It won't survive a serious engagement like this.",
        "{ship_name} took a beating — {hull_pct}% hull remaining, still "
        "undocked in {sector_name}. Dock it for repairs while things are quiet.",
    ],
}


# ── Rule 1: hostile-faction presence in a player-station sector ─────────────

def hostile_presence_findings(conn, scan_id, distances_from_current) -> list[dict]:
    """Hostile-reputation ships operating where the player has stations.

    npc_ships only records ships in sectors that contain a player STATION
    (see db/write.py::_write_npc_ships), so every hit here is already sitting
    on top of a player asset — the distance gate then keeps the advisor
    player-relative, same reasoning as the economy rules: a threat 12 jumps
    away is real, but not what you can react to from where you're standing.
    """
    # Player combat ships per sector — reported as evidence so the card can
    # show whether the threatened sector has any defence at all, without a
    # separate undefended_asset rule prejudging what "enough" defence is.
    defenders: dict[str, int] = {}
    for r in conn.execute(
            "SELECT sector_macro, role FROM ships WHERE scan_id = ?", (scan_id,)):
        if _role_bucket(r['role']) == 'combat' and r['sector_macro']:
            defenders[r['sector_macro']] = defenders.get(r['sector_macro'], 0) + 1

    rows = conn.execute(
        "SELECT ns.sector_macro, ns.sector_name, ns.owner_id, ns.owner_name, "
        "       ns.role, COUNT(*) AS n, r.value AS rep_value "
        "FROM npc_ships ns "
        "JOIN reputation r ON r.faction_id = ns.owner_id AND r.scan_id = ns.scan_id "
        "WHERE ns.scan_id = ? AND r.value <= ? "
        "GROUP BY ns.sector_macro, ns.owner_id, ns.role",
        (scan_id, HOSTILE_REPUTATION))

    # One finding per (sector, faction): the role rows fold into a combat /
    # non-combat split so the score can weight warships over passing traders.
    groups: dict[tuple[str, str], dict] = {}
    for r in rows:
        g = groups.setdefault((r['sector_macro'], r['owner_id']), {
            'sector_name':  r['sector_name'],
            'faction_name': r['owner_name'],
            'rep_value':    r['rep_value'],
            'combat': 0, 'noncombat': 0,
        })
        bucket = 'combat' if _role_bucket(r['role']) == 'combat' else 'noncombat'
        g[bucket] += r['n']

    findings = []
    for (sector_macro, faction_id), g in groups.items():
        jumps = distances_from_current.get(sector_macro)
        if jumps is None or jumps > ADVISOR_MAX_JUMPS:
            continue
        total = g['combat'] + g['noncombat']
        # Distance-dampened threat weight, same shape as economy's
        # value_per_hour / (1 + jumps) — closer threats are more actionable.
        weighted = COMBAT_SHIP_WEIGHT * g['combat'] + g['noncombat']
        priority = weighted * THREAT_SCALE / (1 + jumps)
        slots = {
            'faction_name': g['faction_name'] or faction_id,
            'sector_name':  g['sector_name'] or 'an unknown sector',
            'ship_count':   total,
            'combat_count': g['combat'],
            'jumps':        jumps,
        }
        evidence = {
            'sector_macro':    sector_macro,
            'faction_id':      faction_id,
            'reputation':      g['rep_value'],
            'combat_count':    g['combat'],
            'noncombat_count': g['noncombat'],
            'defender_count':  defenders.get(sector_macro, 0),
            'jumps':           jumps,
        }
        findings.append(_finding(
            f"hostile:{sector_macro}:{faction_id}",
            'military', 'hostile_presence', priority, slots, evidence, TEMPLATES))
    return findings


# ── Rule 2: damaged combat ship not docked for repairs ───────────────────────

def damaged_fleet_findings(conn, scan_id) -> list[dict]:
    """Combat ships flying below DAMAGED_HULL_PCT hull while undocked.

    hull_pct is NULL for undamaged ships (X4 omits the <hull> element at
    100%), so the NOT NULL filter is load-bearing, not defensive. docked_at
    IS NULL is a deliberate simplification: whether a given dock can actually
    repair (wharf module, carrier, friendly shipyard) isn't modelled yet, so
    a docked damaged ship is assumed "being handled" rather than guessed at.
    """
    rows = conn.execute(
        "SELECT sh.object_id, sh.code, sh.name, sh.role, sh.hull_hp, "
        "       sh.hull_max, sh.hull_pct, sh.shield_pct, sh.sector_macro, "
        "       sec.sector_name "
        "FROM ships sh "
        "LEFT JOIN sectors sec ON sec.sector_macro = sh.sector_macro "
        "WHERE sh.scan_id = ? AND sh.docked_at IS NULL "
        "  AND sh.under_construction = 0 "
        "  AND sh.hull_pct IS NOT NULL AND sh.hull_pct < ?",
        (scan_id, DAMAGED_HULL_PCT))
    findings = []
    for r in rows:
        if _role_bucket(r['role']) != 'combat':
            continue
        # Missing hull HP, not percentage: a battered destroyer outranks a
        # battered fighter because it takes longer to replace and costs more
        # to lose — the same "absolute stakes" logic as economy's Cr scores.
        priority = (r['hull_max'] or 0) - (r['hull_hp'] or 0)
        if priority <= 0:
            continue
        slots = {
            'ship_name':   r['name'] or r['code'],
            'role':        r['role'] or 'combat ship',
            'hull_pct':    round(r['hull_pct']),
            'sector_name': r['sector_name'] or 'an unknown sector',
        }
        evidence = {
            'ship_id':      r['object_id'],
            'code':         r['code'],
            'hull_hp':      r['hull_hp'],
            'hull_max':     r['hull_max'],
            'shield_pct':   r['shield_pct'],
            'sector_macro': r['sector_macro'],
        }
        findings.append(_finding(
            f"damaged:{r['object_id']}",
            'military', 'damaged_fleet', priority, slots, evidence, TEMPLATES))
    return findings
