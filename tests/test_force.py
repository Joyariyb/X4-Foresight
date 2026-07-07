# Core role: Unit tests for the force-comparison engine (db/advisors/force.py).
#
# Golden numbers below are copied from data/equipment_stats.py / ship_stats.py
# (same convention as test_pipeline asserting hull_max from SHIP_STATS): if a
# game update rebalances a weapon and the catalogs are regenerated, these
# tests fail loudly — which is the point, because every advisor verdict
# downstream shifts with them.
from __future__ import annotations

import pytest

from data.equipment_stats import EQUIPMENT_STATS
from db.connection import get_connection
from db.advisors.force import (ship_power, sector_forces, tracking_factor,
                               ttk_seconds, combat_strength)


# ── tracking_factor: the community-calibrated anchor cases ──────────────────
# Each case is one of the consensus judgements the ramps were tuned against
# (see the sources block in force.py); if a ramp constant changes, these
# say which community fact broke.

def _tf(macro, slot_type, hull_class):
    return tracking_factor(EQUIPMENT_STATS[macro], slot_type, hull_class,
                           macro=macro)


def test_tracking_flak_is_the_universal_answer():
    # Argon M Flak: 120°/s rotation, 3000 m/s projectile — both ramps maxed.
    assert _tf('turret_arg_m_flak_01_mk1_macro', 'turret', 'ship_l') == 1.0


def test_tracking_plasma_turrets_cannot_hit_fighters():
    # L Plasma (25°/s, 600 m/s): both ramps floor out.
    assert _tf('turret_arg_l_plasma_01_mk1_macro', 'turret', 'ship_l') == 0.0
    # M Plasma rotates fast enough (60°/s) but the 1000 m/s projectile is the
    # multiplicative killer — this is why the ramps multiply, not average.
    assert _tf('turret_arg_m_plasma_01_mk1_macro', 'turret', 'ship_l') == 0.0


def test_tracking_beam_turret_partial_credit():
    # L Beam: hitscan (projectile ramp 1.0) but only 40°/s rotation →
    # (40-30)/(90-30) — "effective but low dps" territory.
    assert _tf('turret_arg_l_beam_01_mk1_macro', 'turret', 'ship_l') \
        == pytest.approx(1 / 6)


def test_tracking_guided_missiles_butcher_fighters():
    # Guidance token substitutes for projectile speed; 100°/s caps rotation.
    assert _tf('turret_arg_m_guided_01_mk1_macro', 'turret', 'ship_l') == 1.0


def test_tracking_dumbfire_gets_token_credit():
    # 100°/s rotation ramp × 0.25 dumbfire credit.
    assert _tf('turret_arg_m_dumbfire_01_mk1_macro', 'turret', 'ship_l') \
        == pytest.approx(0.25)


def test_tracking_fixed_weapons_use_hull_class():
    # A ship-aimed gun on a fighter only needs projectile speed (Pulse
    # Laser, 5000 m/s → 1.0); the identical mount on an L hull is a main
    # battery that can't track strike craft at all.
    assert _tf('weapon_gen_s_laser_01_mk1_macro', 'weapon', 'ship_s') == 1.0
    assert _tf('weapon_gen_s_laser_01_mk1_macro', 'weapon', 'ship_l') == 0.0
    # S Plasma's 1200 m/s ball is hard to land even ship-aimed → 0.2 ramp.
    assert _tf('weapon_gen_s_plasma_01_mk1_macro', 'weapon', 'ship_s') \
        == pytest.approx(0.2)


# ── ship_power ───────────────────────────────────────────────────────────────

def test_ship_power_destroyer_loadout():
    # Behemoth (93,000 hull, 4,713,125 Cr) with a plausible mixed fit.
    p = ship_power('ship_arg_l_destroyer_01_a_macro', [
        ('turret', 'turret_arg_l_plasma_01_mk1_macro', 2),   # 685.86 dps each
        ('turret', 'turret_arg_m_flak_01_mk1_macro', 4),     # 119.07 dps each
        ('shield', 'shield_arg_l_standard_01_mk1_macro', 3), # 55,200 cap each
    ])
    # Every listed weapon deals equal hull/shield per shot, so the sustained
    # total splits 50/50.
    total = 2 * 685.86 + 4 * 119.07
    assert p['dps_hull'] == pytest.approx(total / 2)
    assert p['dps_shield'] == pytest.approx(total / 2)
    # Only the flak tracks fighters — the plasma's 1371.72 dps contributes 0.
    assert p['dps_anti_small'] == pytest.approx(4 * 119.07)
    assert p['ehp_hull'] == 93000
    assert p['ehp_shield'] == 3 * 55200
    assert p['max_range_m'] == 7200                          # the plasma's reach
    assert p['value_cr'] == pytest.approx(
        4713125 + 2 * 114685 + 4 * 65668 + 3 * 46851)


def test_ship_power_actual_hull_overrides_catalog():
    # A half-dead defender must not count at catalog strength.
    p = ship_power('ship_arg_l_destroyer_01_a_macro', [], hull_hp=46500)
    assert p['ehp_hull'] == 46500


def test_ship_power_resolves_equipment_aliases():
    # shield_arg_m_standard_02_* is an alias of ..._01_mk1 (5,750 capacity) —
    # skin variants must not silently contribute zero.
    p = ship_power('ship_xen_s_fighter_01_a_macro',
                   [('shield', 'shield_arg_m_standard_02_mk1_macro', 1)])
    assert p['ehp_shield'] == 5750


# ── combat_strength ───────────────────────────────────────────────────────────

def test_combat_strength_splits_the_axes():
    p = {'dps_hull': 30.0, 'dps_shield': 20.0, 'ehp_hull': 800.0,
         'ehp_shield': 200.0}
    s = combat_strength(p)
    assert s['firepower'] == 50.0                 # 30 + 20
    assert s['hull'] == 800.0
    assert s['shield'] == 200.0
    # Geometric mean of firepower (50) and total eHP (1000): sqrt(50,000).
    assert s['overall'] == pytest.approx((50 * 1000) ** 0.5)


def test_combat_strength_gunless_hull_is_no_threat():
    # The maintainer's own rule: a 90 m hull with no guns must not out-score a
    # small gunship. Firepower gates the overall index, so no guns → zero,
    # however much hull it carries.
    freighter = {'dps_hull': 0.0, 'dps_shield': 0.0,
                 'ehp_hull': 90000.0, 'ehp_shield': 40000.0}
    gunship = {'dps_hull': 120.0, 'dps_shield': 80.0,
               'ehp_hull': 3000.0, 'ehp_shield': 1200.0}
    assert combat_strength(freighter)['overall'] == 0.0
    assert combat_strength(gunship)['overall'] > 0.0


# ── ttk_seconds ──────────────────────────────────────────────────────────────

def test_ttk_shields_then_hull():
    atk = {'dps_shield': 100.0, 'dps_hull': 50.0}
    dfd = {'ehp_shield': 1000.0, 'ehp_hull': 500.0}
    assert ttk_seconds(atk, dfd) == pytest.approx(10 + 10)


def test_ttk_none_when_a_pool_is_unbreakable():
    # No shield damage against a shielded target → the fight never progresses.
    atk = {'dps_shield': 0.0, 'dps_hull': 500.0}
    dfd = {'ehp_shield': 1000.0, 'ehp_hull': 500.0}
    assert ttk_seconds(atk, dfd) is None


def test_ttk_zero_for_empty_defender():
    # 0.0 means "nothing there to kill" — callers treat it as no defence.
    atk = {'dps_shield': 100.0, 'dps_hull': 100.0}
    assert ttk_seconds(atk, {'ehp_shield': 0.0, 'ehp_hull': 0.0}) == 0.0


# ── sector_forces ────────────────────────────────────────────────────────────

@pytest.fixture()
def force_db(tmp_path):
    """A throwaway DB with one threatened sector, exercising every inclusion
    rule at once: hostile with/without captured loadout, non-hostile NPC,
    player defender, player freighter, under-construction hull, and a second
    player ship in an unthreatened sector."""
    conn = get_connection(tmp_path / 'force_test.db')
    conn.execute("INSERT INTO scans (scan_id, scanned_at, save_file, game_time_s) "
                 "VALUES (1, '2026-01-01T00:00:00', 'test.xml', 0)")

    npc = [
        # Armed Xenon fighter: 2 Needler Guns + 1 shield (loadout below).
        ('[0xA1]', 'ship_xen_s_fighter_01_a_macro', 'S', 'xenon', 'sec_a'),
        # Second hostile whose loadout capture failed → counted, unassessed.
        ('[0xA2]', 'ship_xen_s_fighter_01_a_macro', 'S', 'xenon', 'sec_a'),
        # Non-hostile NPC in the same sector → excluded entirely.
        ('[0xA3]', 'ship_xen_s_fighter_01_a_macro', 'S', 'teladi', 'sec_a'),
    ]
    conn.executemany(
        "INSERT INTO npc_ships (scan_id, object_id, macro, size, owner_id, "
        "sector_macro) VALUES (1,?,?,?,?,?)", npc)

    player = [
        # (object_id, role, hull_hp, sector, under_construction)
        ('[0xB1]', 'Fighter', 1250.0, 'sec_a', 0),   # the defender
        ('[0xB2]', 'Freighter', None, 'sec_a', 0),   # wrong role bucket
        ('[0xB3]', 'Fighter', None, 'sec_a', 1),     # still on the slipway
        ('[0xB4]', 'Fighter', None, 'sec_b', 0),     # sector has no hostiles
    ]
    conn.executemany(
        "INSERT INTO ships (scan_id, object_id, macro, size, role, hull_hp, "
        "sector_macro, owner_id, under_construction) "
        "VALUES (1,?,'ship_xen_s_fighter_01_a_macro','S',?,?,?,'player',?)",
        [(oid, role, hp, sec, uc) for oid, role, hp, sec, uc in player])

    equipment = [
        ('[0xA1]', 'weapon', 'weapon_xen_s_gatling_01_mk1_macro', 2),
        ('[0xA1]', 'shield', 'shield_xen_s_standard_01_mk1_macro', 1),
        ('[0xB1]', 'weapon', 'weapon_gen_s_laser_01_mk1_macro', 1),
        ('[0xB1]', 'shield', 'shield_xen_s_standard_01_mk1_macro', 1),
        # The freighter is armed, but its role keeps it off the player side.
        ('[0xB2]', 'turret', 'turret_arg_m_flak_01_mk1_macro', 2),
    ]
    conn.executemany(
        "INSERT INTO ship_equipment (scan_id, ship_id, slot_type, macro, count) "
        "VALUES (1,?,?,?,?)", equipment)
    conn.commit()
    yield conn
    conn.close()


def test_sector_forces(force_db):
    forces = sector_forces(force_db, 1, hostile_owner_ids={'xenon'})

    # Only the threatened sector appears — sec_b has a defender but no threat.
    assert set(forces) == {'sec_a'}
    sec = forces['sec_a']
    assert set(sec['hostile']) == {'xenon'}

    xen = sec['hostile']['xenon']
    assert xen['ship_count'] == 2
    assert xen['unassessed_count'] == 1          # [0xA2] had no loadout rows
    assert xen['size_counts'] == {'S': 2}
    # Only the assessed fighter contributes weapons: 2 Needlers at 108.073
    # sustained each, split 50/50 hull/shield; both track fighters fully
    # (ship-aimed, 2400 m/s).
    assert xen['dps_hull'] == pytest.approx(108.073)
    assert xen['dps_shield'] == pytest.approx(108.073)
    assert xen['dps_anti_small'] == pytest.approx(216.146)
    # BOTH hulls count (the macro is known even when the loadout isn't) but
    # only the assessed fighter's shield does — eHP is a floor, not a guess.
    assert xen['ehp_hull'] == 2 * 2500
    assert xen['ehp_shield'] == 950
    assert xen['max_range_m'] == 3360
    assert xen['value_cr'] == pytest.approx(2 * 34530 + 2 * 37552 + 2112)

    pl = sec['player']
    # Exactly one defender: the freighter fails the role gate, the slipway
    # hull fails under_construction, and [0xB4] is in the wrong sector.
    assert pl['ship_count'] == 1
    assert pl['unassessed_count'] == 0
    # One Pulse Laser at 78.266 sustained, 50/50 split; actual (half) hull.
    assert pl['dps_hull'] == pytest.approx(39.133)
    assert pl['dps_anti_small'] == pytest.approx(78.266)
    assert pl['ehp_hull'] == 1250
    assert pl['ehp_shield'] == 950

    # The engine's numbers flow straight into a TTK verdict: the Xenon pair
    # breaks the lone defender far faster than the reverse.
    assert ttk_seconds(xen, pl) < ttk_seconds(pl, xen)


def test_sector_forces_empty_without_hostiles(force_db):
    assert sector_forces(force_db, 1, hostile_owner_ids=set()) == {}
