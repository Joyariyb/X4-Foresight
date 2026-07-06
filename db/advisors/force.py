"""Core role: Force-comparison engine — turns fitted loadouts into per-side combat power (DPS/eHP/range).

Pure metrics layer for the military advisor rules: it produces numbers, never
findings, and holds no policy — WHICH factions count as hostile is decided by
the caller (military.py's reputation gate), and template phrasing stays in the
rule modules. Same read-only DB contract as db/trends.py.

Why loadout math instead of ship counts: counts lie constantly in X4 — one
Xenon K outweighs twenty fighters — and every input needed to do better is
already captured (ship_equipment rows resolve to real damage/shield/range
stats via EQUIPMENT_STATS). Nothing in the game or community tooling computes
force strength from the ACTUAL fitted loadouts in a save, which is exactly
the gap this module fills.

Honesty limits, stated once here so the rules can cite them: pilot skill,
ship mods, ammo counts, and X4's simplified out-of-sector combat resolution
are all unmodelled. Consumers must present verdicts as coarse bands
(covered / contested / outmatched), never as precise win probabilities.
Ships whose loadout wasn't captured still contribute their HULL (the macro
is always known, so eHP has a floor) but no weapons or shields — profiles
carry an unassessed_count so the rules can refuse to promise "covered" on
partial data instead of silently underestimating a threat.
"""
from __future__ import annotations

from data.ship_stats import SHIP_STATS
from data.equipment_stats import EQUIPMENT_STATS, EQUIPMENT_ALIASES

# Same combat-role taxonomy as military.py's defender count — the two sides
# of a force comparison must agree on who counts as a defender.
from db.trends import _role_bucket


# ── Anti-small tracking model ────────────────────────────────────────────────
# Community consensus is that hitting fighters from a big ship needs high
# turret ROTATION speed plus high PROJECTILE speed, or guided missiles:
# flak/pulse/beam work, plasma is hopeless, dumbfires are poor, torpedoes are
# anti-capital only. See:
#   https://steamcommunity.com/app/392160/discussions/0/3104642254792297738/
#   https://steamcommunity.com/app/392160/discussions/0/3725072332583437242/
#   https://steamah.com/x4-foundations-weapons-turrets-comparison-guide/
# The ramp bounds below are calibrated against the shipped catalog so the
# known cases land where the community puts them (values from
# data/equipment_stats.py):
#   Argon M Flak    (120°/s, 3000 m/s) → 1.00  "the universal answer"
#   Argon L Plasma  ( 25°/s,  600 m/s) → 0.00  "plasma isn't meant to hit fighters"
#   Argon M Plasma  ( 60°/s, 1000 m/s) → 0.00  (projectile too slow, rotation moot)
#   Argon L Beam    ( 40°/s, hitscan)  → 0.17  "effective but low dps"
#   Argon M Guided  (100°/s, missile)  → 1.00  "will absolutely butcher fighter swarms"
# Catalog-wide, M turrets rotate 40–180°/s (median 100) and L turrets 18–60
# (median 30), so the 30→90 ramp naturally scores most M turrets high and
# most L turrets near zero — matching how the game actually plays.
ROTATION_FLOOR, ROTATION_CEIL = 30.0, 90.0      # °/s
PROJECTILE_FLOOR, PROJECTILE_CEIL = 1000.0, 2000.0   # m/s

# Missile macros carry no projectile speed in the catalog, so guidance is
# read from the macro-name token Egosoft uses consistently across factions
# (guided/dumbfire/torpedo). Dumbfires get a small non-zero credit — they can
# still clip slow/heavy S ships — torpedoes none (pure anti-capital).
MISSILE_ANTI_SMALL = {'guided': 1.0, 'dumbfire': 0.25, 'torpedo': 0.0}


def _ramp(value, floor, ceil) -> float:
    """0→1 linear ramp; None scores 0 (missing data must not inflate power)."""
    if value is None:
        return 0.0
    if value >= ceil:
        return 1.0
    if value <= floor:
        return 0.0
    return (value - floor) / (ceil - floor)


def _resolve(macro: str) -> dict:
    """Equipment macro → catalog stats, via the alias table first — story and
    DLC skin variants share stats with a canonical macro (same recipe as
    trends.py's _ship_asset_value)."""
    return (EQUIPMENT_STATS.get(macro)
            or EQUIPMENT_STATS.get(EQUIPMENT_ALIASES.get(macro, ''), {}))


def tracking_factor(stat: dict, slot_type: str, hull_class: str | None,
                    macro: str = '') -> float:
    """0..1 share of this weapon's DPS that can plausibly land on S/M craft.

    ``macro`` is the equipment macro id — only consulted for missiles, whose
    guidance mode lives in the macro name rather than the stats dict.

    Fixed weapons are aimed by the whole ship, so rotation is irrelevant:
    on an S/M hull only projectile speed matters, and on an L/XL hull a fixed
    main battery simply cannot track strike craft at all (community treats
    L fixed guns as anti-capital, full stop). Turrets multiply the rotation
    and projectile ramps — both must be good, which is exactly why plasma
    turrets (fast enough rotation on M mounts, glacial projectiles) still
    score zero.
    """
    is_missile = stat.get('class') in ('missileturret', 'missilelauncher')
    if is_missile:
        # Guidance quality substitutes for projectile speed.
        proj = next((v for k, v in MISSILE_ANTI_SMALL.items() if k in macro),
                    0.0)
    else:
        proj = _ramp(stat.get('projectile_speed_m_s'),
                     PROJECTILE_FLOOR, PROJECTILE_CEIL)

    if slot_type == 'weapon':
        return proj if hull_class in ('ship_xs', 'ship_s', 'ship_m') else 0.0
    return proj * _ramp(stat.get('rotation_speed'),
                        ROTATION_FLOOR, ROTATION_CEIL)


# ── Per-ship power ───────────────────────────────────────────────────────────

def ship_power(macro: str, equipment: list[tuple[str, str, int]],
               hull_hp: float | None = None) -> dict:
    """One ship's combat numbers from its hull macro + fitted loadout.

    ``equipment`` is (slot_type, macro, count) rows from ship_equipment.
    ``hull_hp`` overrides the catalog max_hull when the ACTUAL hull is known
    (player ships) — a half-dead defender must not count at full strength.
    NPC rows carry no hull reading, so they use the catalog value; that
    asymmetry errs toward overstating the threat, which is the safe direction
    for a defence advisor.

    DPS uses the catalog's damage_rate_sustained (tooltip-verified, includes
    the overheat duty cycle), split hull/shield by each weapon's per-shot
    damage ratio. damage_hull_while_shielded (shield-bypass) is deliberately
    ignored in v1 — it's small for most weapons and would make the TTK story
    unexplainable in a finding card.
    """
    hull_stat = SHIP_STATS.get(macro, {})
    p = {
        'dps_hull': 0.0, 'dps_shield': 0.0, 'dps_anti_small': 0.0,
        'ehp_hull': float(hull_hp if hull_hp is not None
                          else hull_stat.get('max_hull') or 0),
        'ehp_shield': 0.0,
        'max_range_m': 0.0,
        'value_cr': float(hull_stat.get('price') or 0),
    }
    for slot_type, emacro, count in equipment:
        stat = _resolve(emacro)
        if not stat:
            continue
        n = count or 1
        p['value_cr'] += (stat.get('price') or 0) * n

        if slot_type == 'shield':
            p['ehp_shield'] += (stat.get('capacity') or 0) * n
            continue
        if slot_type not in ('weapon', 'turret'):
            continue

        sustained = stat.get('damage_rate_sustained')
        per_shot = (stat.get('damage_hull') or 0) + (stat.get('damage_shield') or 0)
        if not sustained or not per_shot:
            continue
        dps = sustained * n
        p['dps_hull'] += dps * (stat.get('damage_hull') or 0) / per_shot
        p['dps_shield'] += dps * (stat.get('damage_shield') or 0) / per_shot
        p['dps_anti_small'] += dps * tracking_factor(
            stat, slot_type, hull_stat.get('class'), macro=emacro)
        p['max_range_m'] = max(p['max_range_m'], stat.get('range_m') or 0)
    return p


# ── Per-sector aggregation ───────────────────────────────────────────────────

# Profile keys that sum across ships; the rest (max_range_m, counts) have
# their own combining rules in _add_ship.
_SUM_KEYS = ('dps_hull', 'dps_shield', 'dps_anti_small',
             'ehp_hull', 'ehp_shield', 'value_cr')


def _empty_profile() -> dict:
    return {k: 0.0 for k in _SUM_KEYS} | {
        'max_range_m': 0.0, 'ship_count': 0, 'unassessed_count': 0,
        'size_counts': {},
    }


def _add_ship(profile: dict, power: dict, size: str | None,
              assessed: bool) -> None:
    """Fold one ship into a side's profile. ``assessed=False`` means the
    ship's loadout wasn't captured: its power dict still carries the hull
    (macro-derived) so eHP keeps a floor, but its DPS/shields read zero, and
    unassessed_count records the gap so the rules can qualify the verdict."""
    profile['ship_count'] += 1
    if size:
        profile['size_counts'][size] = profile['size_counts'].get(size, 0) + 1
    if not assessed:
        profile['unassessed_count'] += 1
    for k in _SUM_KEYS:
        profile[k] += power[k]
    profile['max_range_m'] = max(profile['max_range_m'], power['max_range_m'])


def sector_forces(conn, scan_id, hostile_owner_ids: set[str]) -> dict:
    """{sector_macro: {'hostile': {faction_id: profile}, 'player': profile}}
    for every sector where at least one hostile-owned ship was scanned.

    npc_ships is already bounded to player-station sectors (db/write.py), so
    "sectors with hostiles" here means "player assets under threat". The
    player side counts combat-role ships only (same _role_bucket policy as
    the existing defender count in military.py) and skips hulls still under
    construction — a half-built destroyer defends nothing.
    """
    # One pass over the scan's equipment; both owners' rows live in the same
    # table keyed by ship_id (see schema.sql), so a single grouped read serves
    # every ship_power() call below.
    equip: dict[str, list[tuple[str, str, int]]] = {}
    for r in conn.execute(
            "SELECT ship_id, slot_type, macro, count FROM ship_equipment "
            "WHERE scan_id = ?", (scan_id,)):
        equip.setdefault(r['ship_id'], []).append(
            (r['slot_type'], r['macro'], r['count']))

    forces: dict[str, dict] = {}
    for r in conn.execute(
            "SELECT object_id, macro, size, owner_id, sector_macro "
            "FROM npc_ships WHERE scan_id = ?", (scan_id,)):
        if r['owner_id'] not in hostile_owner_ids or not r['sector_macro']:
            continue
        sec = forces.setdefault(r['sector_macro'],
                                {'hostile': {}, 'player': _empty_profile()})
        prof = sec['hostile'].setdefault(r['owner_id'], _empty_profile())
        rows = equip.get(r['object_id'])
        _add_ship(prof, ship_power(r['macro'], rows or []), r['size'],
                  assessed=bool(rows))

    if not forces:
        return forces

    for r in conn.execute(
            "SELECT object_id, macro, size, role, hull_hp, sector_macro "
            "FROM ships WHERE scan_id = ? AND under_construction = 0",
            (scan_id,)):
        sec = forces.get(r['sector_macro'])
        if sec is None or _role_bucket(r['role']) != 'combat':
            continue
        rows = equip.get(r['object_id'])
        _add_ship(sec['player'],
                  ship_power(r['macro'], rows or [], hull_hp=r['hull_hp']),
                  r['size'], assessed=bool(rows))
    return forces


def merge_profiles(profiles) -> dict:
    """Fold several profiles into one combined force.

    Exists for rules that treat a sector's threat as a single opposing force
    regardless of faction (a flak turret doesn't care whose fighters it
    tracks) — sector_forces keys hostiles per faction because the presence
    rule reports them separately, but composition/range analysis shouldn't.
    """
    out = _empty_profile()
    for p in profiles:
        out['ship_count'] += p['ship_count']
        out['unassessed_count'] += p['unassessed_count']
        for size, n in p['size_counts'].items():
            out['size_counts'][size] = out['size_counts'].get(size, 0) + n
        for k in _SUM_KEYS:
            out[k] += p[k]
        out['max_range_m'] = max(out['max_range_m'], p['max_range_m'])
    return out


# ── Engagement math ──────────────────────────────────────────────────────────

def ttk_seconds(attacker: dict, defender: dict) -> float | None:
    """Seconds for ``attacker``'s sustained DPS to chew through ``defender``'s
    shield pool then hull pool. None = never (a pool exists that the attacker
    has zero matching DPS against). 0.0 = the defender has nothing to kill —
    callers must treat an empty side as "no defence", not "instant win".

    Sequential shields-then-hull mirrors X4's damage model (shields absorb
    fire first; hull takes over when they drop). It's an approximation for a
    fleet — individual ships lose shields at different moments — which is one
    more reason verdicts stay banded.
    """
    total = 0.0
    if defender['ehp_shield'] > 0:
        if attacker['dps_shield'] <= 0:
            return None
        total += defender['ehp_shield'] / attacker['dps_shield']
    if defender['ehp_hull'] > 0:
        if attacker['dps_hull'] <= 0:
            return None
        total += defender['ehp_hull'] / attacker['dps_hull']
    return total
