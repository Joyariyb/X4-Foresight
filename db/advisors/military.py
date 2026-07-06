"""Core role: Military-domain advisor rules (hostile presence, force gaps, build-up trends, damaged ships).

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

# Above this share of their eHP sitting in shields, shield-stripping (ion)
# weapons earn a counter-advice mention; below it they waste a slot. 0.35 is
# a first-pass guess like the other tuning constants.
SHIELD_HEAVY_SHARE = 0.35

# buildup gates. Three nonzero points (two rising intervals) is the minimum
# that separates "growing" from merely "more than last time"; the 2× floor
# keeps ordinary patrol rotation (one ship swapped for a pricier one) below
# the bar. The 4-scan window bounds both the claim and the cost: a passing
# raid arrives, fights and leaves, so it can't stay monotonically rising
# across 4 snapshots — and every extra scan in the window is one more full
# re-read of that scan's equipment table (see hostile_strength_history).
BUILDUP_WINDOW = 4       # scans considered, including the current one
BUILDUP_MIN_SCANS = 3    # nonzero, rising data points before it's a pattern
BUILDUP_GROWTH = 2.0     # newest ÷ oldest strength before it's a finding

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
    'buildup': [
        "{faction_name} strength in {sector_name} has grown {growth}× over "
        "your last {scan_count} scans — ~{from_cr} Cr of hardware then, "
        "~{to_cr} Cr now ({ship_count} ship(s) on station). Sustained "
        "build-up like this reads as invasion staging, not a raid — "
        "reinforce before it commits.",
        "Build-up in {sector_name}: {faction_name} force has risen every "
        "scan for {scan_count} scans running, {growth}× overall to "
        "{ship_count} ship(s). A raid comes and goes — steady growth like "
        "this is staging. Bolster the sector's defence early.",
        "Watch {sector_name} — {faction_name} hardware there has climbed "
        "scan over scan to {growth}× what it was {scan_count} scans ago "
        "(~{from_cr} → ~{to_cr} Cr). That pattern usually precedes an "
        "attack, not a passing raid.",
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


def _counter_advice(theirs: dict, ours: dict) -> list[dict]:
    """[{threat, advice}] rows for the card's counter-advice hover.

    Community-consensus counters, hardcoded on purpose (like force.py's
    tracking anchors) — each row's advice is the researched answer to the
    archetype its gate detects:
    - strike craft → flak / guided missiles / pulse, never plasma
        (sources in force.py's tracking-model block);
    - capitals → plasma L turrets (Paranid's reach furthest) or destroyer
      main guns from standoff, torpedoes once shields drop
        https://steamah.com/x4-foundations-weapons-turrets-comparison-guide/
        https://steamcommunity.com/sharedfiles/filedetails/?id=2826705145
    - shields → ion strips them fast but barely dents hull, so it's a
      pairing weapon — and a wasted slot against a hull-heavy force
        https://wiki.egosoft.com/X4%20Foundations%20Wiki/Manual%20and%20Guides/Objects%20in%20the%20Game%20Universe/Equipment/Ship%20Weapons/BeamGun%20Forward%20Weapons/Ion%20Blaster/

    The strike-craft row also grades the player's OWN mix (same anti-small
    share the composition_gap rule gates on) so the tip says "keep your mix"
    or "refit" instead of generic advice the reader must self-assess.
    """
    tips = []
    small = (theirs['size_counts'].get('S', 0)
             + theirs['size_counts'].get('M', 0))
    if small >= MIN_SMALL_CRAFT:
        advice = ("Flak and guided missile turrets track them; pulse lasers "
                  "for your own fighters. Plasma won't connect.")
        our_dps = ours['dps_hull'] + ours['dps_shield']
        if our_dps > 0:
            pct = round(ours['dps_anti_small'] / our_dps * 100)
            advice += (f" {pct}% of your in-sector damage tracks them — "
                       + ("keep that mix."
                          if pct >= ANTI_SMALL_SHARE_THRESHOLD * 100
                          else "refit toward flak or add fighter escorts."))
        tips.append({'threat': f"{small} strike craft (S/M)",
                     'advice': advice})

    capitals = (theirs['size_counts'].get('L', 0)
                + theirs['size_counts'].get('XL', 0))
    if capitals:
        tips.append({
            'threat': f"{capitals} capital hull(s) (L/XL)",
            'advice': ("Plasma L turrets (Paranid's reach furthest) or "
                       "destroyer main guns from standoff range; torpedo "
                       "runs finish them once shields drop."),
        })

    ehp_total = theirs['ehp_hull'] + theirs['ehp_shield']
    if ehp_total > 0:
        pct = round(theirs['ehp_shield'] / ehp_total * 100)
        if theirs['ehp_shield'] / ehp_total >= SHIELD_HEAVY_SHARE:
            tips.append({
                'threat': f"Shield-heavy force ({pct}% of eHP)",
                'advice': ("Ion blasters strip shields fast but barely dent "
                           "hull — pair them with hull-damage weapons or "
                           "missiles."),
            })
        else:
            tips.append({
                'threat': f"Hull-heavy force (shields {pct}% of eHP)",
                'advice': ("Shield-strippers (ion) waste a slot here — bring "
                           "sustained hull damage instead."),
            })
    return tips


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
            'military', 'hostile_presence', priority, slots, evidence,
            TEMPLATES, counters=_counter_advice(theirs, ours)))
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


# ── Rule 4: hostile strength building up scan over scan ──────────────────────

def hostile_strength_history(conn, scan_id, forces) -> dict[str, list[float]]:
    """{sector_macro: [hostile strength per scan, oldest→newest]} across the
    last BUILDUP_WINDOW scans, for the sectors in the CURRENT scan's forces.

    "Strength" is the merged hostile profiles' value_cr, not DPS: unassessed
    ships still contribute their hull's catalog price (the macro is always
    known) but read zero DPS, so a value series stays comparable between a
    scan that captured loadouts and one that didn't, where a DPS series would
    saw-tooth on capture luck alone.

    Derived from stored scans rather than a new history table — the DB
    already keeps npc_ships + ship_equipment per scan (HISTORY storage
    class), and trends.py's cross-scan sweeps set the precedent for paying
    the re-read instead of adding persistence. Each past scan is judged by
    its OWN reputation rows (threat_forces), so a faction that only just
    turned hostile has no past strength here and can't fire the rule off two
    scans of data it wasn't a threat for.
    """
    prev_ids = [r['scan_id'] for r in conn.execute(
        "SELECT scan_id FROM scans WHERE scan_id < ? "
        "ORDER BY scan_id DESC LIMIT ?", (scan_id, BUILDUP_WINDOW - 1))]

    history: dict[str, list[float]] = {sec: [] for sec in forces}
    for sid in reversed(prev_ids):          # oldest → newest
        past = threat_forces(conn, sid)
        for sec, series in history.items():
            sides = past.get(sec)
            series.append(
                merge_profiles(sides['hostile'].values())['value_cr']
                if sides else 0.0)
    for sec, series in history.items():
        series.append(merge_profiles(forces[sec]['hostile'].values())['value_cr'])
    return history


def buildup_findings(conn, scan_id, distances_from_current,
                     forces) -> list[dict]:
    """Sectors whose hostile strength has risen every scan — staging, not a
    raid. This is the early-warning rule: a snapshot can't tell a build-up
    from a raid, only the trend across scans can, which is also something
    watching the in-game map can't show you.

    Per sector with hostiles merged (like composition_gap — splitting a
    staged force by owner would let each half duck under the growth floor).
    Deliberately NOT gated by ADVISOR_MAX_JUMPS, unlike every other military
    rule: the threat is to the station in that sector, which doesn't get
    less threatened because the player flew away — and a multi-scan trend
    that flickered in and out with the player's position would defeat the
    point of a warning. Jumps still go in the evidence when known.
    """
    if not forces:
        return []
    sector_names, faction_names = _threat_names(conn, scan_id)
    findings = []
    for sector_macro, series in hostile_strength_history(
            conn, scan_id, forces).items():
        # The trailing run of scans where the sector had priced hostiles at
        # all. Zeros never join the run: npc_ships only covers player-station
        # sectors, so an older scan's 0 usually means "no station there yet"
        # (no coverage), and growth measured from a coverage gap would be
        # fiction.
        run: list[float] = []
        for v in reversed(series):
            if v <= 0:
                break
            run.append(v)
        run.reverse()
        if len(run) < BUILDUP_MIN_SCANS:
            continue
        if any(later <= earlier for earlier, later in zip(run, run[1:])):
            continue                        # dipped or stalled — raids do that
        growth = run[-1] / run[0]
        if growth < BUILDUP_GROWTH:
            continue

        theirs = merge_profiles(forces[sector_macro]['hostile'].values())
        # Threat-point units like the other rules, but scaled by growth
        # instead of dampened by distance — how fast it's rising IS this
        # rule's urgency, where "how close is it" was presence's.
        priority = theirs['ship_count'] * THREAT_SCALE * growth
        slots = {
            'faction_name': _dominant_faction(forces[sector_macro]['hostile'],
                                              faction_names),
            'sector_name':  sector_names.get(sector_macro, 'an unknown sector'),
            'scan_count':   len(run),
            'growth':       round(growth, 1),
            'ship_count':   theirs['ship_count'],
            'from_cr':      round(run[0]),
            'to_cr':        round(run[-1]),
        }
        evidence = {
            'sector_macro':       sector_macro,
            'strength_from_cr':   round(run[0]),
            'strength_to_cr':     round(run[-1]),
            'growth_ratio':       round(growth, 2),
            'scans_rising':       len(run),
            'hostile_ship_count': theirs['ship_count'],
            'unassessed_count':   theirs['unassessed_count'],
            'jumps':              distances_from_current.get(sector_macro),
        }
        findings.append(_finding(
            f"buildup:{sector_macro}",
            'military', 'buildup', priority, slots, evidence, TEMPLATES))
    return findings


# ── Rule 5: damaged combat ship not docked for repairs ───────────────────────

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
