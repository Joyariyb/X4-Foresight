# Core role: Unit tests for NpcStationHandler's permanently-hostile ware skip.
from __future__ import annotations

import types
import xml.etree.ElementTree as ET

from scanner.handlers.npc_station import NpcStationHandler


def _run(owner: str, extra_offers: str = ''):
    """Feed one Format-B trading station owned by `owner` through the handler
    and return the captured NpcStation. A SimpleNamespace stands in for
    ScanContext — the handler only touches these five attributes. extra_offers
    is raw <trade> XML spliced into the <production> block for direction tests."""
    xml = (
        f'<component class="station" macro="station_tel_factory_l_macro" '
        f'owner="{owner}" id="[0x9000]" code="TST-1" nameindex="1">'
        '<trade><offers><production>'
        '<trade ware="energycells" seller="[0x9000]" amount="500" price="18"/>'
        '<trade ware="siliconwafers" buyer="[0x9000]" amount="100" desired="300" price="110"/>'
        f'{extra_offers}'
        '</production></offers></trade>'
        '</component>'
    )
    elem = ET.fromstring(xml)
    ctx = types.SimpleNamespace(
        scan_id=1, current_sector_macro='sec_test',
        dockingbay_index={}, npc_stations=[], npc_station_index={})
    handler = NpcStationHandler(texts={})
    handler.on_start(elem, ctx)
    handler.on_end(elem, ctx)
    return ctx.npc_stations[0]


def test_tradeable_faction_keeps_wares():
    station = _run('teladi')
    assert {w.ware_id for w in station.wares} == {'energycells', 'siliconwafers'}


def test_permanently_hostile_faction_wares_skipped():
    # The station is still captured (it belongs on the universe map), but its
    # trade offers are dropped — no advisor path would ever use Xenon wares.
    station = _run('xenon')
    assert station.owner_id == 'xenon'
    assert station.wares == []


def test_buy_and_sell_same_ware_keep_separate_figures():
    # Regression: a trading station that both BUYS and SELLS the same ware used
    # to collapse into one row with last-write-wins on price/amount, conflating
    # the buy demand with the sell stock. Both offers' figures must now survive
    # in their own slots. (siliconwafers already has a buy row in _run; add a
    # sell row for it here — different price and quantity from the buy side.)
    station = _run('teladi',
        '<trade ware="siliconwafers" seller="[0x9000]" amount="2980" price="384"/>')
    sw = next(w for w in station.wares if w.ware_id == 'siliconwafers')
    assert sw.is_buying and sw.is_selling
    # Buy side (from _run's base offer) untouched by the sell row, and vice versa.
    assert sw.buy_amount == 100 and sw.buy_price == 110 and sw.desired == 300
    assert sw.sell_amount == 2980 and sw.sell_price == 384
