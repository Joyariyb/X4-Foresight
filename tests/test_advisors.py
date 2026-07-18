# Core role: Regression tests for the Advisors findings engine (db/advisors/) against the mini save.
from __future__ import annotations

import pytest

from db.connection import get_connection
from db.advisors import military
from db.advisors.combine import compute_advisors
from db.advisors.advisors import merge_anchors


def _finding(export, ftype, id_):
    findings = [f for f in export['advisors']['findings']
                if f['type'] == ftype and f['id'] == id_]
    assert len(findings) == 1, f'expected exactly one {ftype} finding {id_!r}'
    return findings[0]


def test_overflow_risk(export):
    # Overflow Test Station: one energycells production module vastly
    # outproduces its small (50000 m3) storage bay, so time_to_cap comes out
    # well under the 5h threshold with no need for implausible cargo values.
    f = _finding(export, 'overflow_risk', 'overflow:[0x6000]:energycells')
    assert f['domain'] == 'economy'
    assert f['slots']['station_name'] == 'Overflow Test Station'
    assert f['slots']['hours'] < 5
    assert f['priority_score'] > 0
    # Renders without a KeyError for whichever template variant was picked.
    assert f['slots']['ware_name'] in f['body']


def test_market_opportunity(export):
    # Test Energy Plant's energycells surplus matches the Format B NPC station's
    # unmet demand — the buy offer's `amount` (2607 = how much it still wants),
    # NOT desired-amount. 1 jump away.
    f = _finding(export, 'market_opportunity',
                 'marketgap:[0x1000]:energycells:[0x2200]')
    assert f['slots']['jumps'] == 1
    assert f['evidence']['demand_depth'] == 2607
    assert f['priority_score'] > 0


def test_pricing_gap(export):
    # Player sells energycells at 20 cents/unit; the NPC station's buy offer
    # is deliberately priced above that (35) in the fixture.
    f = _finding(export, 'pricing_gap', 'pricing:[0x1000]:energycells:[0x2200]')
    assert f['slots']['player_price'] == 0.2
    # 35 cents rounds to 1 decimal place for display, same as market_opportunity.
    assert f['slots']['npc_price'] == 0.3
    assert f['priority_score'] > 0


def test_idle_hauler(export):
    # Idle Hauler is homed to the Overflow Test Station (a surplus producer)
    # but has no storage component at all — an empty bay, not "no bay".
    f = _finding(export, 'idle_hauler', 'idle:[0x6100]')
    assert f['slots']['fill_pct'] == 0
    assert f['evidence']['cargo_max_m3'] == 8200.0
    assert f['priority_score'] > 0


def test_hostile_presence(export):
    # One Xenon fighter (reputation -32, past the -25 is_hostile threshold)
    # in the player's home sector — which is BOTH a player-station sector
    # (distances_from_player == 0) AND where the avatar is currently standing
    # (distances_from_current == 0). This is the dual-anchor acceptance case:
    # merge_anchors() must produce a single 0-jump entry with anchor == 'both'
    # rather than two separate results the caller would have to dedupe.
    f = _finding(export, 'hostile_presence',
                 'hostile:cluster_1_sector001_macro:xenon')
    assert f['domain'] == 'military'
    assert f['slots']['jumps'] == 0
    assert f['evidence']['anchor'] == 'both'
    # Exactly one finding for this sector/faction — the merge, not two
    # separate anchor-driven rule passes, is what guarantees this.
    assert len([x for x in export['advisors']['findings']
                if x['type'] == 'hostile_presence'
                and x['evidence']['sector_macro'] == 'cluster_1_sector001_macro']) == 1
    assert f['slots']['ship_count'] == 1
    # The "fighter" macro token classifies as a combat role, so the one ship
    # is also the one combat ship.
    assert f['slots']['combat_count'] == 1
    assert f['evidence']['reputation'] <= -25
    # Both player fighters (docked FGT-001, escort FGT-002) count as
    # defenders present in the threatened sector.
    assert f['evidence']['defender_count'] == 2

    # Force comparison (batch 2): the Xenon M fighter's beam (72.619 dmg/s
    # sustained, 10,000 catalog hull) against the armed escort's pulse laser
    # (78.266 dmg/s) plus both fighters' hulls (3,100 catalog + 1,600 actual)
    # and FGT-002's 1,196 shield. TTKs land within 2× of each other, so the
    # verdict is Contested — and must render into whichever template variant
    # was picked.
    assert f['slots']['verdict'] == 'Contested'
    assert 'Contested' in f['body']
    assert f['evidence']['their_dps'] == 73
    assert f['evidence']['our_dps'] == 78
    assert f['evidence']['their_ehp'] == 10000
    assert f['evidence']['our_ehp'] == 5896
    assert f['evidence']['ttk_they_break_us_s'] == 162
    assert f['evidence']['ttk_we_break_them_s'] == 256
    # FGT-001 carries no equipment in the fixture — the defender side must
    # report the gap, not silently read it as an unarmed ship.
    assert f['evidence']['unassessed_count'] == 0          # hostile side
    # Verdict multiplier ×2 (Contested) on v1's weighted presence score:
    # 1 combat ship × 4 weight × 100 scale × 2 / (1 + 0 jumps).
    assert f['priority_score'] == 800.0

    # Counter-advice hover rows: a lone M fighter is under the 4-craft swarm
    # floor and there are no capitals, so only the always-on shield-balance
    # row remains — and with no shield fitted it must read hull-heavy (the
    # "ion wastes a slot" branch), never recommend shield-stripping.
    assert len(f['counters']) == 1
    assert f['counters'][0]['threat'] == 'Hull-heavy force (shields 0% of eHP)'
    assert 'ion' in f['counters'][0]['advice']


def test_no_force_gap_findings_in_fixture(export):
    # The mini save must NOT trigger the batch-3 rules: one hostile M fighter
    # is below the 4-strike-craft swarm floor, there are no hostile capitals,
    # and the escort's pulse laser tracks fighters fine. If either type shows
    # up here, a gate regressed.
    types = {f['type'] for f in export['advisors']['findings']}
    assert 'composition_gap' not in types
    assert 'outranged' not in types


# ── composition_gap / outranged: direct-DB scenario ──────────────────────────
# The mini save deliberately can't trigger these (above), so the positive
# paths get their own throwaway DB, same style as test_force.py: real catalog
# macros, golden numbers copied from the catalogs.

@pytest.fixture()
def threat_db(tmp_path):
    """One sector, one player destroyer armed ONLY with L plasma (can't track
    fighters, 7,200 m reach) against a 5-fighter Xenon swarm plus one beam-
    armed capital (11,000 m reach) — both batch-3 rules should fire."""
    conn = get_connection(tmp_path / 'threat_test.db')
    conn.execute("INSERT INTO scans (scan_id, scanned_at, save_file, game_time_s) "
                 "VALUES (1, '2026-01-01T00:00:00', 'test.xml', 0)")
    conn.execute("INSERT INTO reputation (scan_id, faction_id, faction_name, value) "
                 "VALUES (1, 'xenon', 'Xenon', -30)")

    npc = [(f'[0xC{i}]', 'ship_xen_s_fighter_01_a_macro', 'S') for i in range(5)]
    npc.append(('[0xC5]', 'ship_arg_l_destroyer_01_a_macro', 'L'))
    conn.executemany(
        "INSERT INTO npc_ships (scan_id, object_id, macro, size, owner_id, "
        "owner_name, sector_macro, sector_name) "
        "VALUES (1,?,?,?,'xenon','Xenon','sec_a','Contested Reach')", npc)

    conn.execute(
        "INSERT INTO ships (scan_id, object_id, macro, size, role, "
        "sector_macro, owner_id, under_construction) "
        "VALUES (1,'[0xD1]','ship_arg_l_destroyer_01_a_macro','L','Destroyer',"
        "'sec_a','player',0)")

    equipment = [(f'[0xC{i}]', 'weapon', 'weapon_xen_s_gatling_01_mk1_macro', 1)
                 for i in range(5)]
    equipment += [
        ('[0xC5]', 'weapon', 'weapon_bor_l_beam_01_mk1_macro', 1),
        ('[0xD1]', 'turret', 'turret_arg_l_plasma_01_mk1_macro', 2),
    ]
    conn.executemany(
        "INSERT INTO ship_equipment (scan_id, ship_id, slot_type, macro, count) "
        "VALUES (1,?,?,?,?)", equipment)
    conn.commit()
    yield conn
    conn.close()


def test_merge_anchors():
    # Station-only, current-only, station-nearer, current-nearer, and a tie
    # (equal distance, including the 0==0 "standing at your own station" case)
    # must each resolve to the right winner and the right merged jump count.
    jumps, anchor = merge_anchors(
        distances_from_player={'a': 0, 'c': 5, 'd': 2, 'e': 3},
        distances_from_current={'b': 4, 'c': 2, 'd': 5, 'e': 3})
    assert jumps == {'a': 0, 'b': 4, 'c': 2, 'd': 2, 'e': 3}
    assert anchor == {'a': 'station', 'b': 'current', 'c': 'current',
                       'd': 'station', 'e': 'both'}


def test_hostile_presence_survives_avatar_relocation(threat_db):
    # Regression for the dual-anchor bug: sec_a holds a player station (so
    # distances_from_player reaches it at 0 jumps) but the avatar is off
    # flying a mission somewhere distances_from_current never reaches sec_a
    # at all. Anchoring purely to the avatar's position would silently drop
    # this finding; the merged jumps dict must still surface it via the
    # station anchor.
    result = compute_advisors(
        threat_db, 1,
        distances_from_player={'sec_a': 0},
        distances_from_current={'far_away_sector': 1})
    findings = [f for f in result['findings']
                if f['type'] == 'hostile_presence' and f['id'] == 'hostile:sec_a:xenon']
    assert len(findings) == 1
    f = findings[0]
    assert f['slots']['jumps'] == 0
    assert f['evidence']['anchor'] == 'station'


def test_composition_gap(threat_db):
    forces = military.threat_forces(threat_db, 1)
    findings = military.composition_gap_findings(
        threat_db, 1, {'sec_a': 0}, {'sec_a': 'station'}, forces)
    assert len(findings) == 1
    f = findings[0]
    assert f['id'] == 'compgap:sec_a'
    # 5 of 6 hostiles are strike craft (83% ≥ 60% share, ≥ 4 floor); the
    # plasma-only defence tracks 0% of them (< 25% threshold).
    assert f['slots']['small_count'] == 5
    assert f['slots']['ship_count'] == 6
    assert f['slots']['anti_small_pct'] == 0
    assert f['slots']['faction_name'] == 'Xenon'   # single faction, no suffix
    assert f['slots']['sector_name'] == 'Contested Reach'
    # 5 smalls × 4 combat weight × 100 scale × (1 − 0 tracked share) / (1+0).
    assert f['priority_score'] == 2000.0
    assert 'Contested Reach' in f['body']


def test_composition_gap_silent_when_flak_fitted(threat_db):
    # Refit the defender with flak (tracks fighters fully) — the same swarm
    # must no longer produce a finding: the gap is about the DEFENCE mix,
    # not the hostile composition alone.
    threat_db.execute(
        "UPDATE ship_equipment SET macro = 'turret_arg_m_flak_01_mk1_macro' "
        "WHERE ship_id = '[0xD1]'")
    forces = military.threat_forces(threat_db, 1)
    assert military.composition_gap_findings(
        threat_db, 1, {'sec_a': 0}, {'sec_a': 'station'}, forces) == []


def test_outranged(threat_db):
    forces = military.threat_forces(threat_db, 1)
    findings = military.outranged_findings(
        threat_db, 1, {'sec_a': 0}, {'sec_a': 'station'}, forces)
    assert len(findings) == 1
    f = findings[0]
    assert f['id'] == 'outranged:sec_a'
    # The capital's beam reaches 11,000 m vs the plasma's 7,200 m — past the
    # 1.25× margin. Fighters' Needlers (3,360 m) must not count as "reach".
    assert f['slots']['their_range_km'] == 11.0
    assert f['slots']['our_range_km'] == 7.2
    assert f['slots']['capital_count'] == 1
    assert f['evidence']['their_range_m'] == 11000
    # 3.8 km standoff gap × 1 capital × 100 scale / (1+0 jumps).
    assert f['priority_score'] == 380.0


def test_counter_advice_rows(threat_db):
    # The full archetype spread: 5-fighter swarm + 1 capital, no shields
    # anywhere on the hostile side, and a plasma-only defence (0% tracking).
    forces = military.threat_forces(threat_db, 1)
    findings = military.hostile_presence_findings(
        threat_db, 1, {'sec_a': 0}, {'sec_a': 'station'}, forces)
    assert len(findings) == 1
    tips = findings[0]['counters']
    assert [t['threat'] for t in tips] == [
        '5 strike craft (S/M)',
        '1 capital hull(s) (L/XL)',
        'Hull-heavy force (shields 0% of eHP)',
    ]
    # The swarm row grades the player's own mix: plasma tracks nothing, so
    # it must say refit — the same 25% share line composition_gap gates on.
    assert '0% of your in-sector damage tracks them' in tips[0]['advice']
    assert 'refit' in tips[0]['advice']
    assert 'Plasma L turrets' in tips[1]['advice']


def test_outranged_needs_a_capital(threat_db):
    # Same range picture but the long-reach gun sits on a fighter: no L/XL
    # hull to hold standoff, so no finding — a fighter has to close anyway.
    threat_db.execute(
        "UPDATE npc_ships SET size = 'S' WHERE object_id = '[0xC5]'")
    forces = military.threat_forces(threat_db, 1)
    assert military.outranged_findings(
        threat_db, 1, {'sec_a': 0}, {'sec_a': 'station'}, forces) == []


def test_damaged_fleet(export):
    # The escort fighter flies at 1600/3100 hull (~52%) and is not docked;
    # the equally damaged Hauler One (50%) must NOT fire the rule — it's a
    # freighter, not a combat role.
    f = _finding(export, 'damaged_fleet', 'damaged:[0x3100]')
    assert f['domain'] == 'military'
    assert f['slots']['hull_pct'] == 52
    assert f['evidence']['hull_max'] == 3100.0
    assert f['priority_score'] == 1500.0    # missing hull HP
    assert not [x for x in export['advisors']['findings']
                if x['type'] == 'damaged_fleet' and x['id'] == 'damaged:[0x3000]']


# ── buildup: multi-scan direct-DB scenario ───────────────────────────────────
# The mini save holds a single scan, so a trend rule can't fire there (see
# test_no_buildup_on_a_single_scan). The positive path gets a throwaway DB
# where each scan is "how many ARMED Xenon fighters sit in sec_a". The fighters
# carry a real gatling (weapon_xen_s_gatling_01_mk1_macro) because strength is
# now combat_strength, not a hull-price count — an unarmed fleet reads zero
# firepower ⇒ zero strength and would never trigger. Every fighter is
# identical, so firepower/hull/shield each scale linearly with the count and
# combat_strength's geometric mean stays linear too: overall growth == the
# exact count ratio.

@pytest.fixture()
def buildup_db(tmp_path):
    """Factory: buildup_db([1, 2, 4, 8]) builds one scan per entry with that
    many armed hostile fighters in sec_a (0 = scan exists, sector empty)."""
    made = []

    def build(counts):
        name = 'buildup_' + '_'.join(str(n) for n in counts)
        conn = get_connection(tmp_path / f'{name}.db')
        for sid, n in enumerate(counts, start=1):
            conn.execute(
                "INSERT INTO scans (scan_id, scanned_at, save_file, game_time_s) "
                "VALUES (?, '2026-01-01T00:00:00', 'test.xml', ?)", (sid, sid))
            conn.execute(
                "INSERT INTO reputation (scan_id, faction_id, faction_name, value) "
                "VALUES (?, 'xenon', 'Xenon', -30)", (sid,))
            ids = [f'[0xE{sid}{i}]' for i in range(n)]
            conn.executemany(
                "INSERT INTO npc_ships (scan_id, object_id, macro, size, "
                "owner_id, owner_name, sector_macro, sector_name) "
                "VALUES (?,?,'ship_xen_s_fighter_01_a_macro','S','xenon',"
                "'Xenon','sec_a','Getsu Fune')",
                [(sid, oid) for oid in ids])
            conn.executemany(
                "INSERT INTO ship_equipment (scan_id, ship_id, slot_type, "
                "macro, count) VALUES (?,?,'weapon',"
                "'weapon_xen_s_gatling_01_mk1_macro',1)",
                [(sid, oid) for oid in ids])
        conn.commit()
        made.append(conn)
        return conn

    yield build
    for conn in made:
        conn.close()


def test_buildup(buildup_db):
    # Doubling every scan: strictly rising all 4 scans, 8× overall.
    conn = buildup_db([1, 2, 4, 8])
    forces = military.threat_forces(conn, 4)
    findings = military.buildup_findings(
        conn, 4, {'sec_a': 3}, {'sec_a': 'current'}, forces)
    assert len(findings) == 1
    f = findings[0]
    assert f['id'] == 'buildup:sec_a'
    assert f['slots']['scan_count'] == 4
    assert f['slots']['faction_name'] == 'Xenon'
    assert f['slots']['sector_name'] == 'Getsu Fune'
    # Identical fighters, so every axis scales with the count: overall growth
    # is the exact 1→8 ratio, and firepower/hull track it linearly.
    assert f['slots']['growth'] == 8.0
    assert f['slots']['firepower_growth'] == 8.0
    assert f['slots']['hull_growth'] == 8.0
    ev = f['evidence']
    assert ev['overall_growth'] == 8.0
    assert ev['firepower_from'] > 0                     # armed: real firepower
    assert ev['firepower_to'] > ev['firepower_from']
    # firepower_growth (from unrounded values) already locks the 8× linearity;
    # hull is integer-rounded, so its then→now stays an exact multiple.
    assert ev['hull_to'] == 8 * ev['hull_from']
    # These fighters carry no shield component, so the shield axis is a real
    # zero — its growth ratio is undefined (None), never a divide-by-zero.
    assert ev['shield_from'] == 0
    assert ev['shield_growth'] is None
    # Unlike the other military rules, jumps is reported but NOT a gate — a
    # build-up 3 jumps out is exactly the early warning the rule exists for.
    assert ev['jumps'] == 3
    assert ev['anchor'] == 'current'
    # 8 ships × 100 scale × 8.0 growth; no distance dampening.
    assert f['priority_score'] == 6400.0
    assert 'Getsu Fune' in f['body']


def test_buildup_a_dip_breaks_the_pattern(buildup_db):
    # A raid profile: strength fell between scans 2 and 3. Ends 8× up overall,
    # but "rising monotonically" is the whole claim — no finding.
    conn = buildup_db([1, 4, 2, 8])
    forces = military.threat_forces(conn, 4)
    assert military.buildup_findings(conn, 4, {'sec_a': 0}, {'sec_a': 'station'}, forces) == []


def test_buildup_needs_real_growth(buildup_db):
    # Rising every scan but only 1.6× overall — patrol churn, not staging.
    conn = buildup_db([5, 6, 7, 8])
    forces = military.threat_forces(conn, 4)
    assert military.buildup_findings(conn, 4, {'sec_a': 0}, {'sec_a': 'station'}, forces) == []


def test_buildup_ignores_coverage_gaps(buildup_db):
    # sec_a empty in the first two scans (e.g. the station wasn't built yet,
    # so npc_ships had no coverage there). Only 2 nonzero points remain —
    # under the 3-point floor, so growth measured from a gap can't fire.
    conn = buildup_db([0, 0, 4, 8])
    forces = military.threat_forces(conn, 4)
    assert military.buildup_findings(conn, 4, {'sec_a': 0}, {'sec_a': 'station'}, forces) == []


def test_no_buildup_on_a_single_scan(export):
    # One scan = no trend. If this fires on the mini save, the run-length
    # floor regressed.
    assert 'buildup' not in {f['type'] for f in export['advisors']['findings']}


def test_findings_sorted_by_priority_descending(export):
    scores = [f['priority_score'] for f in export['advisors']['findings']]
    assert scores == sorted(scores, reverse=True)


def test_all_templates_render_without_error(export):
    # A missing slot key would raise inside _finding() at compute time, not
    # here — this test instead guards against an empty/near-empty findings
    # list silently masking a broken rule (e.g. a bad JOIN returning nothing).
    findings = export['advisors']['findings']
    assert len(findings) >= 6
    for f in findings:
        assert f['body'], f"finding {f['id']} rendered an empty body"
