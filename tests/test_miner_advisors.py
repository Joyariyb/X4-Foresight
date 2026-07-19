# Core role: Regression tests for the Miner advisor rules (db/advisors/miner.py).
from __future__ import annotations

import pytest

from db.connection import get_connection
from db.advisors import miner


@pytest.fixture()
def miner_db(tmp_path):
    """One scan with a player station (STV) consuming four inputs, each probing
    one branch of the mining-supply-gap rule:
      - methane : running low, mineable in reach, NO recent mining  -> FIRES
      - ore     : running low, mineable, but a miner delivered it recently -> excluded
      - refined : running low, mineable, but only in a too-far sector -> excluded
      - silicon : mineable, no recent mining, but well-stocked        -> excluded
      - workunit: running low, no recent mining, but NOT mineable     -> excluded
    """
    conn = get_connection(tmp_path / 'miner_test.db')
    # Current clock at 10h. Lookback window is 1h, so cutoff is game_time 32400s.
    conn.execute("INSERT INTO scans (scan_id, scanned_at, save_file, game_time_s, "
                 "player_credits) VALUES (1, '2026-01-01T00:00:00', 'test.xml', 36000, 5000000)")

    conn.executemany(
        "INSERT INTO sectors (sector_macro, last_scan_id, sector_name, owner_id, is_discovered) "
        "VALUES (?, 1, ?, 'teladi', 1)",
        [('sec_home', 'Home Sector'),
         ('sec_gas', 'Methane Fields'),
         ('sec_ore', 'Ore Belt'),
         ('sec_far', 'Distant Reach')])

    conn.execute(
        "INSERT INTO stations (scan_id, object_id, code, name, sector_macro, status) "
        "VALUES (1, '[0xA1]', 'STV-1', 'Station TV', 'sec_home', 'Operational')")

    conn.executemany(
        "INSERT INTO sector_resources (sector_macro, ware, yield_level, recharge_max, "
        "recharge_time, last_scan_id) VALUES (?, ?, ?, ?, 100000, 1)",
        [('sec_gas', 'methane', 'high', 40000),
         ('sec_ore', 'ore', 'medium', 50000),
         ('sec_ore', 'silicon', 'high', 30000),
         ('sec_far', 'refined', 'high', 20000)])   # only deposit is out of range

    conn.executemany(
        "INSERT OR IGNORE INTO ware_metadata (ware_id, name, transport_type, volume_m3) "
        "VALUES (?, ?, ?, ?)",
        [('methane', 'Methane', 'liquid', 6),
         ('ore', 'Ore', 'solid', 10),
         ('silicon', 'Silicon', 'solid', 10),
         ('refined', 'Refined Metals', 'solid', 8),
         ('workunit', 'Superfluid Coolant', 'container', 1)])

    conn.executemany(
        "INSERT INTO station_input_rates (scan_id, station_id, ware_id, ware_name, "
        "consumption_rate, stock_units, runtime_hours) VALUES (1, '[0xA1]', ?, ?, ?, ?, ?)",
        [('methane', 'Methane', 500.0, 1000, 2.0),      # low, mineable, unfed -> fires
         ('ore', 'Ore', 300.0, 300, 1.0),               # low, mineable, but mined recently
         ('refined', 'Refined Metals', 200.0, 200, 1.0),# low, mineable only too far away
         ('silicon', 'Silicon', 200.0, 20000, 100.0),   # mineable & unfed but well-stocked
         ('workunit', 'Superfluid Coolant', 100.0, 50, 0.5)])  # low, unfed, but not mineable

    # Ore got a mining delivery 35000s (inside the 1h window); methane's most
    # recent is 30000s (outside it), so methane still counts as "not being mined".
    conn.executemany(
        "INSERT INTO trade_history_mining (trade_key, first_scan_id, last_scan_id, "
        "station_id, ware_id, ware_name, amount, game_time_s) VALUES (?, 1, 1, ?, ?, ?, ?, ?)",
        [('m1', '[0xA1]', 'ore', 'Ore', 400, 35000.0),
         ('m2', '[0xA1]', 'methane', 'Methane', 400, 30000.0)])

    # Purchases (trade_history direction 'In') for the mine-vs-buy rule. Window
    # is 2h back from game_time 36000, so the cutoff is 28800s.
    conn.executemany(
        "INSERT INTO trade_history (trade_key, first_scan_id, last_scan_id, "
        "station_id, direction, ware_id, ware_name, amount, total_cr, game_time_s) "
        "VALUES (?, 1, 1, '[0xA1]', ?, ?, ?, ?, ?, ?)",
        [('t1', 'In', 'ore', 'Ore', 5000, 1_000_000, 35000.0),        # mineable, big spend -> fires
         ('t2', 'In', 'workunit', 'Superfluid Coolant', 100, 500_000, 35000.0),  # not mineable
         ('t3', 'In', 'silicon', 'Silicon', 10, 5_000, 35000.0),      # mineable but spend under floor
         ('t4', 'In', 'ore', 'Ore', 4000, 800_000, 20000.0),         # ore buy OUTSIDE the window
         ('t5', 'Out', 'ore', 'Ore', 9999, 9_999_999, 35000.0)])      # a sale, not a buy

    # Ships for the idle-miner and miner-exposed rules. docked_at distinguishes
    # a free-flying miner (exposed) from one sheltering at a station.
    conn.executemany(
        "INSERT INTO ships (scan_id, object_id, code, name, role, ship_order, "
        "cargo_max_m3, sector_macro, docked_at) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)",
        [('[0xS1]', 'PSD-162', 'Gas Sentinel', 'Miner (Liquid)', 'Waiting', 57200.0, 'sec_gas', None),  # idle + exposed
         ('[0xS2]', 'RYV-907', 'Mineral Van', 'Miner (Solid)', 'Mining', 50000.0, 'sec_ore', None),     # active
         ('[0xS3]', 'BHT-123', None, 'Miner (Solid)', 'Trading', 9500.0, 'sec_home', None),             # active
         ('[0xS4]', 'DRL-004', 'Drill', 'Miner (Solid)', None, 10000.0, 'sec_home', None),              # null order -> idle; sec_home has too few hostiles
         ('[0xS5]', 'FRT-001', None, 'Freighter', 'Waiting', 20000.0, 'sec_home', None),                # not a miner
         ('[0xS6]', 'DCK-006', None, 'Miner (Liquid)', 'Docked', 8000.0, 'sec_gas', '[0xA1]'),          # docked in hostile sector -> sheltered
         ('[0xS7]', 'ESC-007', 'Escort Me', 'Miner (Solid)', 'Mining', 12000.0, 'sec_gas', None)])      # free-flying in hostile sector -> exposed

    # Reputation for the exposed rule: Xenon is hostile (<= -25), Teladi isn't.
    conn.executemany(
        "INSERT INTO reputation (scan_id, faction_id, faction_name, value) VALUES (1, ?, ?, ?)",
        [('xenon', 'Xenon', -30.0), ('teladi', 'Teladi', 5.0)])

    # Hostile fleet: 4 Xenon in sec_gas (over the floor), 2 in sec_home (under
    # it), plus a friendly Teladi ship in sec_gas that must NOT be counted.
    npc = [(f'[0xX{i}]', 'xenon', 'Xenon', 'sec_gas', 'Methane Fields') for i in range(1, 5)]
    npc += [(f'[0xX{i}]', 'xenon', 'Xenon', 'sec_home', 'Home Sector') for i in range(5, 7)]
    npc += [('[0xT1]', 'teladi', 'Teladi', 'sec_gas', 'Methane Fields')]
    conn.executemany(
        "INSERT INTO npc_ships (scan_id, object_id, owner_id, owner_name, "
        "sector_macro, sector_name) VALUES (1, ?, ?, ?, ?, ?)", npc)

    # Storage for the oversupply rule: solid nearly full WITH miners delivering
    # (fires); liquid nearly full but nothing recently mined in (no fire);
    # container ignored (not solid/liquid).
    conn.executemany(
        "INSERT INTO station_cargo (scan_id, station_id, cargo_type, m3, max_m3, pct) "
        "VALUES (1, '[0xA1]', ?, ?, 1000000, ?)",
        [('solid', 950000, 95.0), ('liquid', 950000, 95.0), ('container', 990000, 99.0)])

    # Solid ore deliveries from two distinct miners inside the 1h window -> the
    # oversupply rule sees the solid bay is actively being fed.
    conn.executemany(
        "INSERT INTO trade_history_mining (trade_key, first_scan_id, last_scan_id, "
        "station_id, ship_id, ware_id, ware_name, amount, game_time_s) "
        "VALUES (?, 1, 1, '[0xA1]', ?, 'ore', 'Ore', 400, ?)",
        [('m3', '[0xS2]', 35000.0), ('m4', '[0xS7]', 34000.0)])

    conn.commit()
    yield conn
    conn.close()


# sec_far sits past DEPOSIT_MAX_JUMPS; the rest are comfortably within reach.
DISTANCES = {'sec_home': 0, 'sec_gas': 2, 'sec_ore': 3,
             'sec_far': miner.DEPOSIT_MAX_JUMPS + 1}


def test_mining_supply_gap_fires_on_starved_mineable_input(miner_db):
    findings = miner.mining_supply_gap_findings(miner_db, 1, DISTANCES)
    by_id = {f['id']: f for f in findings}

    # Methane: consumed, running dry, no recent mining, deposit in reach -> fires.
    f = by_id['mininggap:[0xA1]:methane']
    assert f['domain'] == 'miner'
    assert f['slots']['miner_type'] == 'Liquid miner'
    assert f['slots']['need_units'] == 500
    assert f['evidence']['deposit_sector'] == 'sec_gas'
    assert f['evidence']['deposit_jumps'] == 2
    # 500 units/hr * 6 m3 = 3000 m3/hr, above the M-class band -> L-class.
    assert f['slots']['size_hint'] == 'L-class'
    assert 'Methane Fields' in f['body']


def test_recent_mining_delivery_suppresses(miner_db):
    """Ore is running just as dry, but a miner delivered it inside the lookback
    window — the rule stays quiet because it IS being mined."""
    findings = miner.mining_supply_gap_findings(miner_db, 1, DISTANCES)
    assert 'mininggap:[0xA1]:ore' not in {f['id'] for f in findings}


def test_non_mineable_input_ignored(miner_db):
    """A starved input that no sector mines is a trade problem, not a miner one —
    the rule leaves it to the economy/trader domains."""
    findings = miner.mining_supply_gap_findings(miner_db, 1, DISTANCES)
    assert 'mininggap:[0xA1]:workunit' not in {f['id'] for f in findings}


def test_well_stocked_input_ignored(miner_db):
    """Mineable and unfed, but with a deep buffer: not starving, so no nag."""
    findings = miner.mining_supply_gap_findings(miner_db, 1, DISTANCES)
    assert 'mininggap:[0xA1]:silicon' not in {f['id'] for f in findings}


def test_out_of_range_deposit_ignored(miner_db):
    """Refined Metals is only mineable past DEPOSIT_MAX_JUMPS, so a miner can't
    cheaply service it — the rule doesn't recommend one it can't reach."""
    findings = miner.mining_supply_gap_findings(miner_db, 1, DISTANCES)
    assert 'mininggap:[0xA1]:refined' not in {f['id'] for f in findings}


def test_lookback_window_boundary(miner_db):
    """Moving methane's only delivery to just inside the window suppresses it;
    just outside, it fires again — the 1h cutoff is the switch."""
    # 35999s is 1s inside the 1h window (cutoff 32400s) -> suppressed.
    miner_db.execute("UPDATE trade_history_mining SET game_time_s = 35999 "
                     "WHERE trade_key = 'm2'")
    findings = miner.mining_supply_gap_findings(miner_db, 1, DISTANCES)
    assert 'mininggap:[0xA1]:methane' not in {f['id'] for f in findings}


# ── Rule 2: mine vs buy ──────────────────────────────────────────────────────

def test_mine_vs_buy_fires_on_significant_purchase(miner_db):
    findings = miner.mine_vs_buy_findings(miner_db, 1, DISTANCES)
    by_id = {f['id']: f for f in findings}

    # Ore: mineable in reach, bought for 1M inside the window -> fires. Only the
    # in-window buy (t1) counts; the older t4 and the t5 sale are excluded, so
    # the spend is exactly t1's 1,000,000 and units its 5,000.
    f = by_id['minevsbuy:[0xA1]:ore']
    assert f['domain'] == 'miner'
    assert f['slots']['spend_cr'] == 1_000_000
    assert f['slots']['bought_units'] == 5000
    assert f['slots']['miner_type'] == 'Solid miner'
    assert f['evidence']['deposit_sector'] == 'sec_ore'
    assert f['priority_score'] == 1_000_000


def test_mine_vs_buy_ignores_non_mineable_purchase(miner_db):
    """Buying a ware no reachable sector mines is unavoidable — no miner card."""
    findings = miner.mine_vs_buy_findings(miner_db, 1, DISTANCES)
    assert 'minevsbuy:[0xA1]:workunit' not in {f['id'] for f in findings}


def test_mine_vs_buy_ignores_trivial_spend(miner_db):
    """A tiny top-up buy (under MINE_VS_BUY_MIN_SPEND_CR) isn't a spending habit."""
    findings = miner.mine_vs_buy_findings(miner_db, 1, DISTANCES)
    assert 'minevsbuy:[0xA1]:silicon' not in {f['id'] for f in findings}


def test_mine_vs_buy_ignores_sales(miner_db):
    """Only purchases (direction 'In') count; an ore SALE must not inflate the
    ore spend past its in-window buy."""
    findings = miner.mine_vs_buy_findings(miner_db, 1, DISTANCES)
    ore = next(f for f in findings if f['id'] == 'minevsbuy:[0xA1]:ore')
    # 1,000,000 (t1 only) — proves neither the 9,999,999 sale (t5) nor the
    # out-of-window 800,000 buy (t4) was summed in.
    assert ore['slots']['spend_cr'] == 1_000_000


# ── Rule 3: idle miner ───────────────────────────────────────────────────────

def test_idle_miner_fires_on_parked_miners(miner_db):
    findings = miner.idle_miner_findings(miner_db, 1)
    by_id = {f['id']: f for f in findings}

    # Waiting miner fires, with its bay size as priority and a resolved type.
    f = by_id['idleminer:[0xS1]']
    assert f['slots']['cargo_max'] == 57200
    assert f['slots']['miner_type'] == 'Liquid miner'
    assert f['slots']['order'] == 'Waiting'
    assert f['priority_score'] == 57200.0
    # A NULL order also counts as idle.
    assert 'idleminer:[0xS4]' in by_id


def test_idle_miner_ignores_working_and_docked(miner_db):
    """Mining/Trading miners are busy; a Docked one may be mid-cycle — none fire."""
    ids = {f['id'] for f in miner.idle_miner_findings(miner_db, 1)}
    assert 'idleminer:[0xS2]' not in ids   # Mining
    assert 'idleminer:[0xS3]' not in ids   # Trading
    assert 'idleminer:[0xS6]' not in ids   # Docked


def test_idle_miner_ignores_non_miners(miner_db):
    """An idle Freighter is the logistics domain's problem, not the miner's."""
    ids = {f['id'] for f in miner.idle_miner_findings(miner_db, 1)}
    assert 'idleminer:[0xS5]' not in ids


# ── Rule 4: miner exposed ────────────────────────────────────────────────────

def test_miner_exposed_fires_on_free_flying_miner_in_hostile_sector(miner_db):
    findings = miner.miner_exposed_findings(miner_db, 1)
    by_id = {f['id']: f for f in findings}

    # sec_gas has 4 Xenon ships (the friendly Teladi one doesn't count), so both
    # free-flying miners there fire, headlined by Xenon and the hostile count.
    f = by_id['minerexposed:[0xS1]']
    assert f['slots']['hostile_count'] == 4
    assert f['slots']['faction_name'] == 'Xenon'
    assert f['priority_score'] == 4.0
    assert 'minerexposed:[0xS7]' in by_id


def test_miner_exposed_ignores_docked_and_thin_threats(miner_db):
    ids = {f['id'] for f in miner.miner_exposed_findings(miner_db, 1)}
    # Docked in the same hostile sector -> sheltered, not exposed.
    assert 'minerexposed:[0xS6]' not in ids
    # sec_home has only 2 hostiles, under the floor -> its idle miner isn't flagged.
    assert 'minerexposed:[0xS4]' not in ids


def test_miner_exposed_silent_without_hostiles(miner_db):
    """No hostile reputation -> the rule can't classify any fleet as a threat."""
    miner_db.execute("UPDATE reputation SET value = 10 WHERE faction_id = 'xenon'")
    assert miner.miner_exposed_findings(miner_db, 1) == []


# ── Rule 6: mining oversupply ────────────────────────────────────────────────

def test_mining_oversupply_fires_on_full_bay_still_fed(miner_db):
    findings = miner.mining_oversupply_findings(miner_db, 1)
    by_id = {f['id']: f for f in findings}

    # Solid bay at 95% with two distinct miners still delivering ore -> fires.
    f = by_id['miningover:[0xA1]:solid']
    assert f['slots']['fill_pct'] == 95
    assert f['slots']['miner_count'] == 2
    assert f['slots']['cargo_type'] == 'solid'


def test_mining_oversupply_needs_active_deliveries(miner_db):
    """The liquid bay is just as full, but nothing was mined into it recently —
    a merely-full bay isn't an active waste, so it doesn't fire."""
    ids = {f['id'] for f in miner.mining_oversupply_findings(miner_db, 1)}
    assert 'miningover:[0xA1]:liquid' not in ids
    # container is neither solid nor liquid — never considered.
    assert 'miningover:[0xA1]:container' not in ids


# ── Rule 7: mineral demand ───────────────────────────────────────────────────

def test_mineral_demand_fires_on_reachable_buyer_with_deposit(miner_db):
    demand_by_ware = {
        # 250 Cr/unit * 1000 = 250,000 Cr, ore mineable in sec_ore -> fires.
        'ore': [{'object_id': '[0xN1]', 'code': 'ORB-1', 'station_name': 'Ore Buyer',
                 'jumps': 2, 'price': 25000, 'amount': 1000, 'desired': 1000,
                 'demand_depth': 1000}],
        # 10 Cr/unit * 50 = 500 Cr, under the value floor -> no fire.
        'silicon': [{'object_id': '[0xN2]', 'code': 'SLB-1', 'station_name': 'Sili Buyer',
                     'jumps': 1, 'price': 1000, 'amount': 50, 'desired': 50,
                     'demand_depth': 50}],
        # High value, but no reachable deposit (refined only in out-of-range sec_far).
        'refined': [{'object_id': '[0xN3]', 'code': 'RFB-1', 'station_name': 'Ref Buyer',
                     'jumps': 1, 'price': 50000, 'amount': 1000, 'desired': 1000,
                     'demand_depth': 1000}],
    }
    findings = miner.mineral_demand_findings(miner_db, 1, DISTANCES, demand_by_ware)
    by_id = {f['id']: f for f in findings}

    f = by_id['mineraldemand:[0xN1]:ore']
    assert f['slots']['value_cr'] == 250_000
    assert f['slots']['price'] == 250.0
    assert f['slots']['miner_type'] == 'Solid miner'
    assert f['priority_score'] == 250_000

    assert not any(fid.endswith(':silicon') for fid in by_id)  # under value floor
    assert not any(fid.endswith(':refined') for fid in by_id)  # no reachable deposit
