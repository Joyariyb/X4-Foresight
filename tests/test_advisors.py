# Core role: Regression tests for the Advisors findings engine (db/advisors/) against the mini save.
from __future__ import annotations


def _finding(export, ftype, id_):
    findings = [f for f in export['advisors']['findings']
                if f['type'] == ftype and f['id'] == id_]
    assert len(findings) == 1, f'expected exactly one {ftype} finding {id_!r}'
    return findings[0]


def test_overflow_risk(export):
    # Overflow Test Station: one energycells production module vastly
    # outproduces its small (50000 m3) storage bay, so time_to_cap comes out
    # well under the 24h threshold with no need for implausible cargo values.
    f = _finding(export, 'overflow_risk', 'overflow:[0x6000]:energycells')
    assert f['domain'] == 'economy'
    assert f['slots']['station_name'] == 'Overflow Test Station'
    assert f['slots']['hours'] < 24
    assert f['priority_score'] > 0
    # Renders without a KeyError for whichever template variant was picked.
    assert f['slots']['ware_name'] in f['body']


def test_market_opportunity(export):
    # Test Energy Plant's energycells surplus matches the Format B NPC
    # station's genuine unmet demand (desired=3000 > amount=2607), 1 jump away.
    f = _finding(export, 'market_opportunity',
                 'marketgap:[0x1000]:energycells:[0x2200]')
    assert f['slots']['jumps'] == 1
    assert f['evidence']['demand_depth'] == 393
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
    # in the player's home sector — 0 jumps from the current position.
    f = _finding(export, 'hostile_presence',
                 'hostile:cluster_1_sector001_macro:xenon')
    assert f['domain'] == 'military'
    assert f['slots']['jumps'] == 0
    assert f['slots']['ship_count'] == 1
    # The "fighter" macro token classifies as a combat role, so the one ship
    # is also the one combat ship.
    assert f['slots']['combat_count'] == 1
    assert f['evidence']['reputation'] <= -25
    # Both player fighters (docked FGT-001, escort FGT-002) count as
    # defenders present in the threatened sector.
    assert f['evidence']['defender_count'] == 2
    assert f['priority_score'] > 0


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
