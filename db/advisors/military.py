"""Core role: Military-domain advisor rules (hostile presence near the player, damaged combat ships).

See advisors.py for the shared _finding() renderer, and __init__.py's
compute_advisors() for how these rules combine with other domains into one
findings list.

Hostility is decided by REPUTATION (value <= -25, mirroring
ReputationEntry.is_hostile in scanner/entities.py), not by hull origin —
the UI's Xenon/Yaki/Kha'ak origin list is a display shortcut, and a faction
the player has personally angered is just as much a threat as the Xenon.

hostile_presence verdicts come from force.py's fitted-loadout math (time to
kill in each direction), banded rather than percentaged — see force.py's
header for what the model deliberately ignores. Still out of scope here:
"can that fleet actually catch my hauler" routing advice, because SHIP_STATS
has no speed fields yet (weapon-stats gap in the project backlog). Extending
gamefiles/generate_data.py to pull speed from the ship macros' physics block
is its own prerequisite batch — don't guess at synthetic speed values here.
"""
from __future__ import annotations
from .advisors import _finding, ADVISOR_MAX_JUMPS
from .force import sector_forces, ttk_seconds, merge_profiles

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

# One side must need this many times longer than the other to break through
# before the verdict leaves "Contested". 2× is deliberately wide: force.py's
# TTK ignores pilot skill, mods and OOS combat quirks, so a narrower band
# would claim precision the model doesn't have.
OUTMATCHED_RATIO = 2.0

# How much each verdict inflates the presence score — a force you'd lose to
# outranks an equal-size one you'd beat, and an undefended sector outranks
# both because there is nothing on site to buy time.
VERDICT_MULTIPLIER = {'Undefended': 4, 'Outmatched': 3, 'Contested': 2,
                      'Covered': 1}

# composition_gap gates. First-pass tuning guesses (like economy's 24h/15%),
# expect retuning; the MECHANISM they gate — plasma can't track fighters,
# flak/pulse/guided can — is the researched part, encoded in force.py's
# tracking model. Findings only fire when the mismatch is one-sided: mostly
# strike craft on their side, mostly untracking guns on ours.
SMALL_SHARE_THRESHOLD = 0.6        # their S+M share of ships
ANTI_SMALL_SHARE_THRESHOLD = 0.25  # our DPS share able to track S/M
MIN_SMALL_CRAFT = 4                # fewer strike craft than this isn't a swarm

# outranged gates. The margin filters near-ties (a 5% reach edge decides
# nothing); the L/XL requirement exists because only a capital hull can USE a
# range advantage — a fighter with a long-range gun still has to close, a
# destroyer parks at max range and pounds ("standoff bombardment").
OUTRANGE_MARGIN = 1.25             # their reach ÷ ours before it's a finding

# A combat ship under this hull percentage, flying around undocked, should
# see a repair dock before its next engagement. Shields regenerate on their
# own, so hull is the signal that persists between fights.
DAMAGED_HULL_PCT = 75.0

# 3 phrasings per finding type so the feed doesn't read as copy-pasted.
# hostile_presence composes two pre-built slots — {force_clause} (the numbers
# comparison, which needs undefended/unassessed variants) and {advice} (the
# verdict-specific recommendation) — so the templates only vary the framing
# around them instead of each phrasing re-deriving every edge case.
TEMPLATES: dict[str, list[str]] = {
    'hostile_presence': [
        "{verdict}: {faction_name} has {ship_count} ship(s) in {sector_name}, "
        "{jumps} jump(s) from your position, {force_clause}. {advice}",
        "{sector_name} ({jumps} jump(s) out): {ship_count} {faction_name} "
        "vessel(s), {force_clause} — assessment: {verdict}. {advice}",
        "Hostile presence in {sector_name} — {ship_count} {faction_name} "
        "ship(s) {jumps} jump(s) away, {force_clause}. {verdict}. {advice}",
    ],
    'damaged_fleet': [
        "{ship_name} is down to {hull_pct}% hull in {sector_name} and isn't "
        "docked anywhere — send it for repairs before its next fight.",
        "Repair needed: {ship_name} ({role}) is flying at {hull_pct}% hull "
        "in {sector_name}. It won't survive a serious engagement like this.",
        "{ship_name} took a beating — {hull_pct}% hull remaining, still "
        "undocked in {sector_name}. Dock it for repairs while things are quiet.",
    ],
    'composition_gap': [
        "{faction_name} is running {small_count} strike craft in "
        "{sector_name} ({jumps} jump(s) out), and only {anti_small_pct}% of "
        "your defenders' firepower can track targets that small. Add flak "
        "turrets or fighter escorts.",
        "Tracking mismatch in {sector_name}: {small_count} of "
        "{faction_name}'s {ship_count} ship(s) are S/M craft, but just "
        "{anti_small_pct}% of your damage output can hit them. Flak, pulse "
        "or fighters would close the gap.",
        "Your defence in {sector_name} is built for big targets — "
        "{anti_small_pct}% of its damage tracks strike craft, while "
        "{faction_name} fields {small_count} of them {jumps} jump(s) from "
        "you. Rebalance toward flak or escorts.",
    ],
    'outranged': [
        "{faction_name}'s capital weapons in {sector_name} reach "
        "{their_range_km} km; your longest-ranged defender stops at "
        "{our_range_km} km. They can fire from standoff — close the distance "
        "fast or bring longer-range ships.",
        "Outranged in {sector_name} ({jumps} jump(s) out): {capital_count} "
        "{faction_name} capital(s) shoot to {their_range_km} km against "
        "your {our_range_km} km. Expect to take fire before you can reply.",
        "Range gap in {sector_name}: {faction_name} out-reaches you "
        "{their_range_km} km to {our_range_km} km with {capital_count} "
        "capital hull(s) on station. Standoff bombardment risk — reposition "
        "or refit.",
    ],
}


# ── Shared force computation ─────────────────────────────────────────────────

def threat_forces(conn, scan_id) -> dict:
    """sector_forces() gated by this domain's hostility policy (the same
    reputation threshold every military rule uses).

    Computed once in compute_advisors() and passed into each rule — same
    share-the-expensive-lookup convention as economy's npc_demand_by_ware,
    since three rules reading the same equipment table independently would
    triple the scan's heaviest advisor query.
    """
    hostile_ids = {r['faction_id'] for r in conn.execute(
        "SELECT faction_id FROM reputation WHERE scan_id = ? AND value <= ?",
        (scan_id, HOSTILE_REPUTATION))}
    return sector_forces(conn, scan_id, hostile_ids)


def _threat_names(conn, scan_id) -> tuple[dict, dict]:
    """({sector_macro: name}, {faction_id: name}) for template slots —
    force.py profiles deal purely in power numbers and carry no names."""
    sectors, factions = {}, {}
    for r in conn.execute(
            "SELECT DISTINCT sector_macro, sector_name, owner_id, owner_name "
            "FROM npc_ships WHERE scan_id = ?", (scan_id,)):
        if r['sector_macro'] and r['sector_name']:
            sectors[r['sector_macro']] = r['sector_name']
        if r['owner_id'] and r['owner_name']:
            factions[r['owner_id']] = r['owner_name']
    return sectors, factions


def _dominant_faction(hostile_profiles: dict, faction_names: dict) -> str:
    """Display name for a merged multi-faction threat: the biggest fleet's
    name, marked when it isn't alone — a card that says just 'Xenon' while
    counting Kha'ak ships would misdirect the response."""
    top = max(hostile_profiles, key=lambda f: hostile_profiles[f]['ship_count'])
    name = faction_names.get(top, top)
    return name if len(hostile_profiles) == 1 else f"{name} (and other hostiles)"


# ── Rule 1: hostile-faction presence in a player-station sector ─────────────

def _fmt_duration(seconds: float) -> str:
    """~30 seconds / ~4 minutes / ~2 hours — TTK is an approximation, so the
    body never shows a number more precise than the model deserves."""
    if seconds < 120:
        return f"{round(seconds)} seconds"
    if seconds < 7200:
        return f"{round(seconds / 60)} minutes"
    return f"{round(seconds / 3600)} hours"


def _verdict(theirs: dict, ours: dict) -> str:
    """Band the engagement from both directions' time-to-kill.

    The all-unassessed guards matter more than the maths: a side with zero
    weapon data reads as zero DPS, which without the guard would score a
    completely unknown fleet as harmless ("Covered"). Missing data must
    degrade toward the middle band, never toward reassurance — the same
    reason a partially-unassessed hostile force can't earn "Covered".
    """
    if ours['ship_count'] == 0:
        return 'Undefended'
    if (theirs['unassessed_count'] == theirs['ship_count']
            or ours['unassessed_count'] == ours['ship_count']):
        return 'Contested'

    t_they = ttk_seconds(theirs, ours)   # how long they need to break us
    t_we = ttk_seconds(ours, theirs)     # how long we need to break them
    if t_we is None and t_they is None:
        return 'Contested'               # neither side can hurt the other
    if t_we is None:
        return 'Outmatched'              # we can never crack them
    if t_they is None:
        verdict = 'Covered'              # they can never crack us
    elif t_we > OUTMATCHED_RATIO * t_they:
        verdict = 'Outmatched'
    elif t_they > OUTMATCHED_RATIO * t_we:
        verdict = 'Covered'
    else:
        verdict = 'Contested'
    if verdict == 'Covered' and theirs['unassessed_count'] > 0:
        return 'Contested'
    return verdict


def _force_clause(theirs: dict, ours: dict, verdict: str) -> str:
    """The numbers half of the card body — needs its own undefended and
    no-data variants, which is why it's a slot instead of template text."""
    their_dps = round(theirs['dps_hull'] + theirs['dps_shield'])
    our_dps = round(ours['dps_hull'] + ours['dps_shield'])
    if verdict == 'Undefended':
        clause = (f"bringing ~{their_dps:,} dmg/s sustained with nothing of "
                  "yours in-sector to answer")
    elif theirs['unassessed_count'] == theirs['ship_count']:
        clause = "with loadouts the scan couldn't assess"
    else:
        clause = (f"bringing ~{their_dps:,} dmg/s sustained against your "
                  f"{ours['ship_count']} defender(s)' ~{our_dps:,}")
    if 0 < theirs['unassessed_count'] < theirs['ship_count']:
        clause += f" (plus {theirs['unassessed_count']} ship(s) unassessed)"
    return clause


def _advice(verdict: str, t_they: float | None) -> str:
    """Verdict-specific recommendation. Only Outmatched quotes the TTK — that
    is the one case where "how long until it goes wrong" changes what the
    player does next."""
    if verdict == 'Undefended':
        return ("Anything you own there is exposed — station defence or a "
                "patrol is overdue.")
    if verdict == 'Outmatched':
        if t_they:
            return (f"They could break your present defence in roughly "
                    f"{_fmt_duration(t_they)} — reinforce heavily or pull "
                    "your assets out.")
        return ("Your ships there cannot crack their defences — reinforce "
                "heavily or pull your assets out.")
    if verdict == 'Covered':
        return "Your present force should hold."
    return "The engagement could go either way — reinforcements would tip it."


def hostile_presence_findings(conn, scan_id, distances_from_current,
                              forces) -> list[dict]:
    """Hostile-reputation ships operating where the player has stations,
    scored by fitted-loadout force comparison (force.py) instead of raw counts.

    ``forces`` is threat_forces()' result, computed once by the caller.

    npc_ships only records ships in sectors that contain a player STATION
    (see db/write.py::_write_npc_ships), so every hit here is already sitting
    on top of a player asset — the distance gate then keeps the advisor
    player-relative, same reasoning as the economy rules: a threat 12 jumps
    away is real, but not what you can react to from where you're standing.
    """
    # Names, reputation and the combat/non-combat role split aren't part of
    # force.py's profiles (it deals purely in power numbers), so they come
    # from the same grouped query v1 used.
    rows = conn.execute(
        "SELECT ns.sector_macro, ns.sector_name, ns.owner_id, ns.owner_name, "
        "       ns.role, COUNT(*) AS n, r.value AS rep_value "
        "FROM npc_ships ns "
        "JOIN reputation r ON r.faction_id = ns.owner_id AND r.scan_id = ns.scan_id "
        "WHERE ns.scan_id = ? AND r.value <= ? "
        "GROUP BY ns.sector_macro, ns.owner_id, ns.role",
        (scan_id, HOSTILE_REPUTATION))

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
        theirs = forces[sector_macro]['hostile'][faction_id]
        ours = forces[sector_macro]['player']
        verdict = _verdict(theirs, ours)
        t_they = ttk_seconds(theirs, ours)
        t_we = ttk_seconds(ours, theirs)

        # v1's distance-dampened presence weight, now scaled by how the fight
        # would actually go — the verdict multiplier is the batch-2 change.
        weighted = COMBAT_SHIP_WEIGHT * g['combat'] + g['noncombat']
        priority = (weighted * THREAT_SCALE * VERDICT_MULTIPLIER[verdict]
                    / (1 + jumps))
        slots = {
            'verdict':      verdict,
            'faction_name': g['faction_name'] or faction_id,
            'sector_name':  g['sector_name'] or 'an unknown sector',
            'ship_count':   g['combat'] + g['noncombat'],
            'combat_count': g['combat'],
            'jumps':        jumps,
            'force_clause': _force_clause(theirs, ours, verdict),
            'advice':       _advice(verdict, t_they),
        }
        evidence = {
            'sector_macro':          sector_macro,
            'faction_id':            faction_id,
            'reputation':            g['rep_value'],
            'combat_count':          g['combat'],
            'noncombat_count':       g['noncombat'],
            'unassessed_count':      theirs['unassessed_count'],
            'defender_count':        ours['ship_count'],
            'their_dps':             round(theirs['dps_hull'] + theirs['dps_shield']),
            'our_dps':               round(ours['dps_hull'] + ours['dps_shield']),
            'their_ehp':             round(theirs['ehp_hull'] + theirs['ehp_shield']),
            'our_ehp':               round(ours['ehp_hull'] + ours['ehp_shield']),
            'ttk_they_break_us_s':   round(t_they) if t_they is not None else None,
            'ttk_we_break_them_s':   round(t_we) if t_we is not None else None,
            'hostile_fleet_value_cr': round(theirs['value_cr']),
            'jumps':                 jumps,
        }
        findings.append(_finding(
            f"hostile:{sector_macro}:{faction_id}",
            'military', 'hostile_presence', priority, slots, evidence, TEMPLATES))
    return findings


# ── Rule 2: defence composition can't track their strike craft ──────────────

def composition_gap_findings(conn, scan_id, distances_from_current,
                             forces) -> list[dict]:
    """Sectors where the threat is mostly S/M craft but the defence's guns
    mostly can't track them (force.py's dps_anti_small vs total DPS).

    One finding per SECTOR, hostiles merged across factions — a flak turret
    doesn't care whose fighters it tracks, so splitting the swarm by owner
    would let two half-swarms each duck under the threshold. Skipped when the
    defence has no assessed weapons at all: "your guns can't track them" is
    an unfoundable claim about guns we never saw.
    """
    sector_names, faction_names = _threat_names(conn, scan_id)
    findings = []
    for sector_macro, sides in forces.items():
        jumps = distances_from_current.get(sector_macro)
        if jumps is None or jumps > ADVISOR_MAX_JUMPS:
            continue
        ours = sides['player']
        our_dps = ours['dps_hull'] + ours['dps_shield']
        if ours['ship_count'] == 0 or our_dps <= 0:
            continue
        theirs = merge_profiles(sides['hostile'].values())
        small = (theirs['size_counts'].get('S', 0)
                 + theirs['size_counts'].get('M', 0))
        if small < MIN_SMALL_CRAFT:
            continue
        if small / theirs['ship_count'] < SMALL_SHARE_THRESHOLD:
            continue
        anti_small_share = ours['dps_anti_small'] / our_dps
        if anti_small_share >= ANTI_SMALL_SHARE_THRESHOLD:
            continue

        # Swarm size × how blind the defence is to it, distance-dampened —
        # same threat-point units as hostile_presence, so the two rules rank
        # sensibly against each other in the military view.
        priority = (small * COMBAT_SHIP_WEIGHT * THREAT_SCALE
                    * (1 - anti_small_share) / (1 + jumps))
        slots = {
            'faction_name':   _dominant_faction(sides['hostile'], faction_names),
            'sector_name':    sector_names.get(sector_macro, 'an unknown sector'),
            'small_count':    small,
            'ship_count':     theirs['ship_count'],
            'anti_small_pct': round(anti_small_share * 100),
            'jumps':          jumps,
        }
        evidence = {
            'sector_macro':       sector_macro,
            'small_count':        small,
            'hostile_ship_count': theirs['ship_count'],
            'defender_count':     ours['ship_count'],
            'our_dps':            round(our_dps),
            'our_anti_small_dps': round(ours['dps_anti_small']),
            'unassessed_count':   theirs['unassessed_count'],
            'jumps':              jumps,
        }
        findings.append(_finding(
            f"compgap:{sector_macro}",
            'military', 'composition_gap', priority, slots, evidence, TEMPLATES))
    return findings


# ── Rule 3: their capitals out-reach every defender ──────────────────────────

def outranged_findings(conn, scan_id, distances_from_current,
                       forces) -> list[dict]:
    """Sectors where hostile capital hulls (L/XL) hold a real weapon-range
    advantage over the whole defence — the standoff-bombardment setup, where
    defenders take fire the entire approach before they can reply.

    Like composition_gap: per sector, hostiles merged, and silent when the
    defence has no assessed weapons (our_range 0 would "prove" any gun
    out-ranges us). The hostile range comes only from assessed ships too, so
    an unassessed K never triggers this — hostile_presence still reports it.
    """
    sector_names, faction_names = _threat_names(conn, scan_id)
    findings = []
    for sector_macro, sides in forces.items():
        jumps = distances_from_current.get(sector_macro)
        if jumps is None or jumps > ADVISOR_MAX_JUMPS:
            continue
        ours = sides['player']
        if ours['ship_count'] == 0 or ours['max_range_m'] <= 0:
            continue
        theirs = merge_profiles(sides['hostile'].values())
        capitals = (theirs['size_counts'].get('L', 0)
                    + theirs['size_counts'].get('XL', 0))
        if capitals == 0:
            continue
        if theirs['max_range_m'] < OUTRANGE_MARGIN * ours['max_range_m']:
            continue

        # Kilometres of standoff × number of platforms that can exploit it.
        gap_km = (theirs['max_range_m'] - ours['max_range_m']) / 1000
        priority = gap_km * capitals * THREAT_SCALE / (1 + jumps)
        slots = {
            'faction_name':   _dominant_faction(sides['hostile'], faction_names),
            'sector_name':    sector_names.get(sector_macro, 'an unknown sector'),
            'their_range_km': round(theirs['max_range_m'] / 1000, 1),
            'our_range_km':   round(ours['max_range_m'] / 1000, 1),
            'capital_count':  capitals,
            'jumps':          jumps,
        }
        evidence = {
            'sector_macro':   sector_macro,
            'their_range_m':  round(theirs['max_range_m']),
            'our_range_m':    round(ours['max_range_m']),
            'capital_count':  capitals,
            'defender_count': ours['ship_count'],
            'jumps':          jumps,
        }
        findings.append(_finding(
            f"outranged:{sector_macro}",
            'military', 'outranged', priority, slots, evidence, TEMPLATES))
    return findings


# ── Rule 4: damaged combat ship not docked for repairs ───────────────────────

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
