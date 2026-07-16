# Core role: Unit tests for data/production.py input-rate math and its DB→export roundtrip.
#
# The golden-export fixture stations are pure solar plants (no inputs), so the
# station_input_rates path would otherwise ship with zero coverage — these
# tests exercise it with a hull-parts module, whose recipe has three inputs.
from __future__ import annotations

import pytest

from data.production import (
    consumption_rates_from_modules,
    input_rates_from_modules,
    production_analytics_from_modules,
)
from data.wares import WARE_NAMES
from db.connection import get_connection
from db.write import write_scan
from export.jsonexport import to_export
from scanner.context import ScanContext
from scanner.entities import Station, StationModule

# One Argon hull-parts module: 900 s cycle = 4 cycles/hr; default recipe is
# {energycells: 80, graphene: 40, refinedmetals: 280} per cycle. 'arg' also
# exercises the faction-method fallback (no 'argon' recipe exists for
# hull parts, so the default must be picked up).
HULLPARTS = StationModule(macro='prod_arg_hullparts_macro',
                          category='production', produces='hullparts')
SOLAR     = StationModule(macro='prod_gen_energycells_macro',
                          category='production', produces='energycells')
DOCK      = StationModule(macro='dockarea_arg_m_station_01_macro',
                          category='dock', produces='')

INVENTORY = {
    'energycells':   (640, 640.0),   # 2 h of stock at 320/hr
    'refinedmetals': (0, 0.0),       # already out
    # graphene deliberately absent — missing stock must read as 0, not crash
}


def test_input_rates_follow_recipe():
    rows = {r['ware_id']: r for r in input_rates_from_modules([HULLPARTS], INVENTORY)}

    assert rows['energycells']['consumption_rate']   == pytest.approx(320.0)
    assert rows['graphene']['consumption_rate']      == pytest.approx(160.0)
    assert rows['refinedmetals']['consumption_rate'] == pytest.approx(1120.0)

    assert rows['energycells']['runtime_hours']   == pytest.approx(2.0)
    assert rows['refinedmetals']['runtime_hours'] == 0.0
    assert rows['graphene']['stock_units'] == 0
    assert rows['graphene']['runtime_hours'] == 0.0

    assert rows['energycells']['ware_name'] == WARE_NAMES['energycells']


def test_input_rates_agree_with_consumption_rates():
    # Both functions share _consumed_per_hour_by_id; if they ever disagree, one
    # of them stopped using the shared core and recipe handling can drift.
    modules = [HULLPARTS, SOLAR]
    by_name = consumption_rates_from_modules(modules)
    rows    = input_rates_from_modules(modules, {})
    assert {r['ware_name']: r['consumption_rate'] for r in rows} == by_name


def test_no_input_wares_yield_no_rows():
    # Energy cells run on sunlight; docks aren't production modules at all.
    assert input_rates_from_modules([SOLAR], INVENTORY) == []
    assert input_rates_from_modules([DOCK],  INVENTORY) == []
    assert input_rates_from_modules([],      INVENTORY) == []


def test_input_rates_roundtrip_to_export(tmp_path):
    # Full write_scan → to_export pass over a synthetic one-station context,
    # because the mini-save fixture can't cover the station_input_rates table.
    modules = [HULLPARTS]
    station = Station(
        scan_id=1, object_id='[0x1]', code='TST-001', name='Roundtrip Test',
        sector_macro='cluster_14_sector001_macro', status='Operational',
        module_count=1,
        hull_hp=None, hull_max=None, hull_pct=None,
        shield_hp=None, shield_max=None, shield_pct=None,
        cargo_container=None, cargo_solid=None, cargo_liquid=None,
        cargo_total=None,
        account_amount=None, budget_total=None, budget_sunlight=None,
        modules=modules,
        inventory=INVENTORY,
        production_analytics=production_analytics_from_modules(
            modules, INVENTORY, 'cluster_14_sector001_macro'),
        input_rates=input_rates_from_modules(modules, INVENTORY),
    )
    ctx = ScanContext(scan_id=1, save_file='test.xml')
    ctx.stations.append(station)

    conn = get_connection(tmp_path / 'roundtrip.db')
    try:
        scan_id = write_scan(conn, ctx)
        export  = to_export(conn, scan_id)
    finally:
        conn.close()

    st = export['stations'][0]
    assert st['input_rates']['Energy Cells']['rate']            == pytest.approx(320.0)
    assert st['input_rates']['Energy Cells']['runtime_hours']   == pytest.approx(2.0)
    assert st['input_rates']['Refined Metals']['runtime_hours'] == 0.0
    assert st['input_rates']['Graphene']['stock']               == 0
