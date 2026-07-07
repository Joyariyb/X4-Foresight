# Core role: Regression tests for the Trader advisor rules (db/advisors/trader.py).
from __future__ import annotations

import pytest

from db.connection import get_connection
from db.advisors import trader


@pytest.fixture()
def trader_db(tmp_path):
    """One scan with: an unclaimed resource sector (friendly-owned), a hostile-
    owned resource sector (must be excluded), a claimed player sector, two NPC
    stations forming a reachable galaxy arbitrage pair, one blocked-reputation
    NPC station, a stranded courier, and a small trading-ship fleet."""
    conn = get_connection(tmp_path / 'trader_test.db')
    conn.execute("INSERT INTO scans (scan_id, scanned_at, save_file, game_time_s, "
                 "player_credits) VALUES (1, '2026-01-01T00:00:00', 'test.xml', 36000, 10000000)")
    conn.executemany(
        "INSERT INTO reputation (scan_id, faction_id, faction_name, value, tier) "
        "VALUES (1, ?, ?, ?, ?)",
        [('teladi', 'Teladi', 5, 'Neutral'),
         ('xenon', 'Xenon', -30, 'Hostile')])

    conn.executemany(
        "INSERT INTO sectors (sector_macro, last_scan_id, sector_name, owner_id, is_discovered) "
        "VALUES (?, 1, ?, ?, 1)",
        [('sec_home', 'Home Sector', 'teladi'),
         ('sec_ore', 'Ore Belt', 'teladi'),
         ('sec_hostile', 'Hostile Reach', 'xenon')])

    conn.execute(
        "INSERT INTO stations (scan_id, object_id, code, name, sector_macro, status) "
        "VALUES (1, '[0xA1]', 'HOM-1', 'Home Station', 'sec_home', 'Operational')")

    conn.executemany(
        "INSERT INTO sector_resources (sector_macro, ware, yield_level, recharge_max, "
        "recharge_time, last_scan_id) VALUES (?, ?, ?, ?, 100000, 1)",
        [('sec_ore', 'ore', 'high', 50000),
         ('sec_ore', 'silicon', 'veryhigh', 1000),        # high yield, no demand
         ('sec_ore', 'water', 'low', 500),                # below the yield floor
         ('sec_ore', 'nividium', 'exotic', 800),          # unrecognised yield tier
         ('sec_hostile', 'ice', 'high', 20000),
         ('sec_home', 'energycells', 'medium', 5000)])   # already claimed — must be excluded

    conn.executemany(
        "INSERT OR IGNORE INTO ware_metadata (ware_id, name, transport_type, volume_m3) "
        "VALUES (?, ?, 'solid', 10)",
        [('ore', 'Ore'), ('silicon', 'Silicon'), ('ice', 'Ice'),
         ('water', 'Water'), ('nividium', 'Nividium'),
         ('energycells', 'Energy Cells')])

    conn.executemany(
        "INSERT OR IGNORE INTO ware_prices (ware_id, price_min, price_avg, price_max) "
        "VALUES (?, ?, ?, ?)",
        [('ore', 10, 20, 30), ('silicon', 5, 10, 15), ('ice', 8, 16, 24),
         ('water', 6, 12, 18), ('nividium', 500, 1000, 1500),
         ('energycells', 10, 15, 20)])

    conn.executemany(
        "INSERT INTO npc_stations (object_id, last_scan_id, code, name, sector_macro, "
        "owner_id, owner_name) VALUES (?, 1, ?, ?, ?, ?, ?)",
        [('[0xB1]', 'SEL-1', 'Cheap Seller', 'sec_home', 'teladi', 'Teladi'),
         ('[0xB2]', 'BUY-1', 'Pricey Buyer',  'sec_ore',  'teladi', 'Teladi'),
         ('[0xB3]', 'HOS-1', 'Xenon Post',    'sec_hostile', 'xenon', 'Xenon')])

    conn.executemany(
        "INSERT INTO npc_station_wares (station_id, ware_id, ware_name, is_buying, "
        "is_selling, price, amount, desired) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [('[0xB1]', 'energycells', 'Energy Cells', 0, 1, 1000, 500, None),
         ('[0xB2]', 'energycells', 'Energy Cells', 1, 0, 3000, 0, 500),
         ('[0xB3]', 'ice', 'Ice', 1, 0, 1500, 0, 200)])

    conn.execute(
        "INSERT INTO in_progress_deliveries (scan_id, ship_id, ship_code, ship_name, "
        "ware_id, ware_name, amount, from_station_id, from_station_name, "
        "dest_station_id, dest_station_name, time_ago_s) "
        "VALUES (1, '[0xC1]', 'HAU-1', 'Stray Hauler', 'ore', 'Ore', 100, "
        "'[0xA1]', 'Home Station', NULL, NULL, 10800)")  # 3h stranded
    conn.execute(
        "INSERT INTO in_progress_deliveries (scan_id, ship_id, ship_code, ship_name, "
        "ware_id, ware_name, amount, from_station_id, from_station_name, "
        "dest_station_id, dest_station_name, time_ago_s) "
        "VALUES (1, '[0xC2]', 'HAU-2', 'Fresh Hauler', 'ore', 'Ore', 100, "
        "'[0xA1]', 'Home Station', NULL, NULL, 1800)")  # 0.5h, under threshold

    ships = [('[0xD1]', 'Freighter')]
    ships += [(f'[0xD{i}]', 'Miner') for i in range(2, 11)]
    conn.executemany(
        "INSERT INTO ships (scan_id, object_id, role, sector_macro) "
        "VALUES (1, ?, ?, 'sec_home')", ships)

    conn.commit()
    yield conn
    conn.close()


DISTANCES = {'sec_home': 0, 'sec_ore': 3, 'sec_hostile': 2}


def test_station_siting_advises_low_demand_and_notes_high_demand(trader_db):
    avg_prices = {'ore': 20, 'silicon': 10, 'ice': 16}
    demand_by_ware = {'ore': [{'demand_depth': 500}]}   # silicon: no demand

    findings = trader.station_siting_findings(
        trader_db, 1, DISTANCES, avg_prices, demand_by_ware)
    by_id = {f['id']: f for f in findings}

    # High-demand ware: advised AND the body carries the demand call-out.
    ore = by_id['siting:sec_ore:ore']
    assert 'Demand' in ore['body']
    assert ore['evidence']['demand_depth'] == 500

    # High-yield ware with no demand: still advised (demand isn't a veto), and
    # the body makes no demand claim it can't back up.
    silicon = by_id['siting:sec_ore:silicon']
    assert silicon['slots']['demand_note'] == ''
    assert 'Demand' not in silicon['body']

    # Hostile-owned sector (reputation < -10): excluded even though it has a
    # resource, because building there isn't safe.
    assert 'siting:sec_hostile:ice' not in by_id

    # sec_home has a resource deposit too, but already holds a player station
    # (see the `stations` insert above) — the claimed-sector filter must skip it.
    assert 'siting:sec_home:energycells' not in by_id
    assert not any(f['evidence']['sector_macro'] == 'sec_home' for f in findings)


def test_station_siting_yield_floor(trader_db):
    """Only 'high'-and-above deposits earn a permanent station: a known Low
    deposit is dropped, while an unrecognised yield string keeps the benefit of
    the doubt (per _DEFAULT_YIELD_RANK) and still surfaces rather than being
    penalised for a save format we couldn't read."""
    findings = trader.station_siting_findings(
        trader_db, 1, {'sec_home': 0, 'sec_ore': 2},
        {'ore': 20, 'silicon': 10, 'water': 12, 'nividium': 1000}, {})
    ids = {f['id'] for f in findings}

    assert 'siting:sec_ore:ore' in ids        # High — advised
    assert 'siting:sec_ore:silicon' in ids    # Very High — advised
    assert 'siting:sec_ore:water' not in ids  # Low — below the floor, dropped
    assert 'siting:sec_ore:nividium' in ids   # unknown tier — benefit of the doubt


def test_station_siting_respects_max_jumps(trader_db):
    """The siting radius is a hard cut, not just a priority dampener: a deposit
    one jump past SITING_MAX_JUMPS produces no finding, while one sitting
    exactly on the boundary still does (the cut is inclusive)."""
    avg_prices = {'ore': 20, 'silicon': 10}
    demand_by_ware = {}

    far = trader.station_siting_findings(
        trader_db, 1,
        {'sec_home': 0, 'sec_ore': trader.SITING_MAX_JUMPS + 1},
        avg_prices, demand_by_ware)
    assert not any(f['evidence']['sector_macro'] == 'sec_ore' for f in far)

    edge = trader.station_siting_findings(
        trader_db, 1,
        {'sec_home': 0, 'sec_ore': trader.SITING_MAX_JUMPS},
        avg_prices, demand_by_ware)
    assert any(f['evidence']['sector_macro'] == 'sec_ore' for f in edge)


def test_galaxy_arbitrage(trader_db):
    findings = trader.galaxy_arbitrage_findings(trader_db, 1, DISTANCES)
    assert len(findings) == 1
    f = findings[0]
    assert f['slots']['sell_price'] == 10.0    # 1000 cents
    assert f['slots']['buy_price'] == 30.0      # 3000 cents
    assert f['slots']['gain'] == round((3000 - 1000) / 100.0 * min(500, 500))
    assert f['priority_score'] > 0


def test_stranded_delivery(trader_db):
    avg_prices = {'ore': 20}
    findings = trader.stranded_delivery_findings(trader_db, 1, avg_prices)
    ids = {f['id'] for f in findings}
    assert 'stranded:[0xC1]:ore' in ids     # 3h, over the 2h threshold
    assert 'stranded:[0xC2]:ore' not in ids  # 0.5h, under the threshold


def test_idle_trade_capital_fires_when_undertrading(trader_db):
    findings = trader.idle_trade_capital_findings(trader_db, 1)
    assert len(findings) == 1
    f = findings[0]
    assert f['slots']['credits'] == 10000000
    assert f['slots']['traders'] == 1
    assert f['slots']['total'] == 10
    assert f['slots']['pct'] == 10


def test_idle_trade_capital_silent_below_credit_threshold(trader_db):
    trader_db.execute("UPDATE scans SET player_credits = 1000 WHERE scan_id = 1")
    assert trader.idle_trade_capital_findings(trader_db, 1) == []


def test_idle_trade_capital_silent_when_fleet_already_trading(trader_db):
    trader_db.execute("UPDATE ships SET role = 'Freighter' WHERE sector_macro = 'sec_home'")
    assert trader.idle_trade_capital_findings(trader_db, 1) == []
