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
         ('sec_far', 'Distant Reach', 'teladi'),   # unlinked: no buyer in range
         ('sec_hostile', 'Hostile Reach', 'xenon')])

    # Jump graph: sec_home <-> sec_ore (1 jump). sec_far is deliberately absent,
    # so it's isolated — used to prove siting demand is centred on the candidate
    # sector (sec_ore reaches the sec_home ore buyer; sec_far reaches nobody).
    conn.executemany(
        "INSERT INTO sector_links (sector_a, sector_b, cost, last_scan_id) "
        "VALUES (?, ?, ?, 1)",
        [('sec_home', 'sec_ore', 1)])

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
         ('sec_far', 'ore', 'high', 50000),               # same ore, no buyer in reach
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
         ('[0xB3]', 'HOS-1', 'Xenon Post',    'sec_hostile', 'xenon', 'Xenon'),
         ('[0xB4]', 'ORE-1', 'Ore Buyer',     'sec_home', 'teladi', 'Teladi')])

    conn.executemany(
        "INSERT INTO npc_station_wares (station_id, ware_id, ware_name, is_buying, "
        "is_selling, buy_price, buy_amount, sell_price, sell_amount, desired) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        # Buy offers at rest: buy_amount (what's still wanted) == desired (order
        # size), matching how real saves store standing demand.
        # [0xB1] both SELLS energycells (stock 500 @ 10) AND posts a cheap,
        # never-selected BUY for it (want 9999 @ 0.5): a conflation guard. The
        # arbitrage seller side must read sell_amount (500), so the trade volume
        # is seller-bound at 500 — a merged row that clobbered sell_amount with
        # buy_amount (9999) would let B2's 8000 demand pull the volume to 8000.
        [('[0xB1]', 'energycells', 'Energy Cells', 1, 1, 50, 9999, 1000, 500, None),
         ('[0xB2]', 'energycells', 'Energy Cells', 1, 0, 3000, 8000, None, None, 8000),
         ('[0xB3]', 'ice', 'Ice', 1, 0, 1500, 200, None, None, 200),
         # Ore buyer in sec_home (1 jump from sec_ore) — the siting demand note's
         # source. buy_amount 500 is the unmet demand that must reach sec_ore.
         ('[0xB4]', 'ore', 'Ore', 1, 0, 250, 500, None, None, 500)])

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


def test_station_siting_notes_strong_demand(trader_db):
    avg_prices = {'ore': 20, 'silicon': 10, 'ice': 16}

    findings = trader.station_siting_findings(trader_db, 1, DISTANCES, avg_prices)
    by_id = {f['id']: f for f in findings}

    # sec_ore collapses to one finding, headlined by ore (its best-priority,
    # strongly-demanded ware); the body carries the demand call-out. Demand
    # (500) comes from the ore buyer in sec_home, 1 jump away via sector_links.
    f = by_id['siting:sec_ore']
    assert f['evidence']['ware_id'] == 'ore'
    assert f['evidence']['demand_depth'] == 500
    assert 'Demand' in f['body']

    # Hostile-owned sector (reputation < -10): excluded even though it has a
    # resource, because building there isn't safe.
    assert 'siting:sec_hostile' not in by_id

    # sec_home has a resource deposit too, but already holds a player station
    # (see the `stations` insert above) — the claimed-sector filter must skip it.
    assert not any(f['evidence']['sector_macro'] == 'sec_home' for f in findings)


def test_station_siting_dedups_per_sector(trader_db):
    """A resource-rich sector yields ONE finding, headlined by its best-priority
    ware, with the other qualifying deposits folded into an 'also rich in'
    mention rather than one card per ware."""
    findings = trader.station_siting_findings(
        trader_db, 1, {'sec_home': 0, 'sec_ore': 3}, {'ore': 20, 'silicon': 10})
    ore_findings = [f for f in findings if f['evidence']['sector_macro'] == 'sec_ore']

    assert len(ore_findings) == 1
    f = ore_findings[0]
    assert f['id'] == 'siting:sec_ore'
    assert f['evidence']['ware_id'] == 'ore'          # best priority — headline
    # The other high-yield deposit is surfaced as a richness signal, not dropped.
    assert 'silicon' in f['evidence']['other_wares']
    assert 'Silicon' in f['body']
    assert 'also rich in' in f['body']
    # The below-floor ware never appears, not even as a mention.
    assert 'water' not in f['evidence']['other_wares']
    assert 'Water' not in f['body']


def test_station_siting_yield_floor(trader_db):
    """Only 'high'-and-above deposits earn a permanent station: a known Low
    deposit is dropped, while an unrecognised yield string keeps the benefit of
    the doubt (per _DEFAULT_YIELD_RANK) and still surfaces rather than being
    penalised for a save format we couldn't read."""
    findings = trader.station_siting_findings(
        trader_db, 1, {'sec_home': 0, 'sec_ore': 2},
        {'ore': 20, 'silicon': 10, 'water': 12, 'nividium': 1000})
    f = next(f for f in findings if f['evidence']['sector_macro'] == 'sec_ore')

    # The sector's surviving wares — headline plus mentions — are exactly the
    # high-and-above ones; the Low deposit (water) is absent everywhere.
    surfaced = {f['evidence']['ware_id'], *f['evidence']['other_wares']}
    assert surfaced == {'ore', 'silicon', 'nividium'}
    assert 'water' not in surfaced
    # nividium (no buyers) out-prices ore for the headline, so the demand note
    # reflects the headline ware and stays silent — ore's demand is a demoted
    # mention, not a claim on this card.
    assert 'Demand' not in f['body']


def test_station_siting_respects_max_jumps(trader_db):
    """The siting radius is a hard cut, not just a priority dampener: a deposit
    one jump past SITING_MAX_JUMPS produces no finding, while one sitting
    exactly on the boundary still does (the cut is inclusive)."""
    avg_prices = {'ore': 20, 'silicon': 10}

    far = trader.station_siting_findings(
        trader_db, 1,
        {'sec_home': 0, 'sec_ore': trader.SITING_MAX_JUMPS + 1}, avg_prices)
    assert not any(f['evidence']['sector_macro'] == 'sec_ore' for f in far)

    edge = trader.station_siting_findings(
        trader_db, 1,
        {'sec_home': 0, 'sec_ore': trader.SITING_MAX_JUMPS}, avg_prices)
    assert any(f['evidence']['sector_macro'] == 'sec_ore' for f in edge)


def test_station_siting_demand_is_sector_centered(trader_db):
    """Same ware, two candidate sectors: the one within reach of an ore buyer
    gets the demand note; the isolated one gets none. This is the regression
    guard against a galaxy-wide total pasted identically onto every card."""
    findings = trader.station_siting_findings(
        trader_db, 1, {'sec_ore': 1, 'sec_far': 1}, {'ore': 20})
    by_id = {f['id']: f for f in findings}

    near, far = by_id['siting:sec_ore'], by_id['siting:sec_far']
    assert near['evidence']['ware_id'] == far['evidence']['ware_id'] == 'ore'
    # sec_ore reaches the sec_home ore buyer (linked, 1 jump); sec_far is
    # isolated in the jump graph, so no buyer is in range.
    assert near['evidence']['demand_depth'] == 500
    assert far['evidence']['demand_depth'] == 0
    assert 'Demand' in near['body']
    assert 'Demand' not in far['body']


def test_galaxy_arbitrage(trader_db):
    findings = trader.galaxy_arbitrage_findings(trader_db, 1, DISTANCES)
    assert len(findings) == 1
    f = findings[0]
    assert f['slots']['sell_price'] == 10.0    # 1000 cents (B1 sell offer)
    assert f['slots']['buy_price'] == 30.0      # 3000 cents (B2 buy offer)
    # Volume is seller-bound at B1's sell_amount (500), NOT its unrelated
    # buy_amount (9999) — proves the buy/sell figures no longer clobber.
    assert f['evidence']['volume'] == 500
    assert f['slots']['gain'] == round((3000 - 1000) / 100.0 * min(500, 8000))
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
