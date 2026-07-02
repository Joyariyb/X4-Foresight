# Core role: Regression tests for the scan pipeline (Scanner -> TradePostProcessor -> homebase resolution) on the mini save.
from __future__ import annotations

from conftest import MINI_SAVE
from scanner.scanner import Scanner


def _ship(ctx, object_id):
    """Single ship by object_id — fails loudly if the fixture stops producing it."""
    matches = [s for s in ctx.ships if s.object_id == object_id]
    assert len(matches) == 1, f'expected exactly one ship {object_id}, got {len(matches)}'
    return matches[0]


# ─────────────────────────────────────────────────────────────────────────────
#  Save metadata + player identity
# ─────────────────────────────────────────────────────────────────────────────

class TestMetadata:
    def test_game_time(self, ctx):
        assert ctx.game_time_s == 1000000.0

    def test_player_identity(self, ctx):
        assert ctx.player_name == 'Test Pilot'
        # <account> is only captured while inside <faction id="player">; a wrong
        # value here usually means the reputation handler's _active gate broke.
        assert ctx.player_credits == 123456789
        # location="{20004,10011}" resolved through the mini language file.
        assert ctx.player_sector == 'Testora Prime'


# ─────────────────────────────────────────────────────────────────────────────
#  Reputation + faction relations
# ─────────────────────────────────────────────────────────────────────────────

class TestReputation:
    def test_player_reputation_includes_booster(self, ctx):
        rep = {r.faction_id: r for r in ctx.reputation}
        assert set(rep) == {'argon', 'teladi', 'xenon'}

        # argon: base 0.01 + booster 0.005, each scaled independently.
        # scale_reputation is log10-based: 0.01 -> 10.0, 0.005 -> 6.99,
        # 0.015 -> 11.76. A booster of 0.0 here means on_booster stopped firing.
        argon = rep['argon']
        assert argon.base == 10.0
        assert argon.booster == 6.99
        assert argon.value == 11.76
        assert argon.tier == 'Friendly'

        # teladi has no booster: total must equal base.
        assert rep['teladi'].booster == 0.0
        assert rep['teladi'].value == rep['teladi'].base == 6.99

    def test_visitor_faction_ignored(self, ctx):
        # visitor001 is not in FACTION_NAMES — its block must not leak into
        # either output (the guard is ReputationHandler._current).
        assert all(r.faction_id != 'visitor001' for r in ctx.reputation)
        assert all(r.faction_id != 'visitor001' for r in ctx.faction_relations)

    def test_npc_relations_and_locked_flag(self, ctx):
        rel = {(r.faction_id, r.other_id): r for r in ctx.faction_relations}
        assert rel[('argon', 'player')].value == 10.0
        assert rel[('argon', 'player')].locked is False
        # locked="1" comes from the <relations> wrapper, not the faction tag.
        assert rel[('xenon', 'player')].locked is True


# ─────────────────────────────────────────────────────────────────────────────
#  Player station
# ─────────────────────────────────────────────────────────────────────────────

class TestPlayerStation:
    def test_station_core_fields(self, ctx):
        assert len(ctx.stations) == 1
        st = ctx.stations[0]
        assert st.object_id == '[0x1000]'
        assert st.code == 'STA-001'
        # name= attribute is a literal player name — no sector prefix added.
        assert st.name == 'Test Energy Plant'
        assert st.sector_macro == 'cluster_1_sector001_macro'
        assert st.status == 'Operational'
        # 3 <entry> rows in <construction><sequence>.
        assert st.module_count == 3
        assert st.account_amount == 2000000

    def test_station_hull_from_module_stats(self, ctx):
        st = ctx.stations[0]
        # prod module at 108500/217000 + storage at full 565000 (no <hull>
        # child means undamaged) — both maxima come from STATION_STATS.
        assert st.hull_hp == 673500.0
        assert st.hull_max == 782000.0
        # One shield module, undamaged (no <shield> child = full capacity).
        assert st.shield_hp == st.shield_max == 55200.0
        assert st.shield_pct == 100.0

    def test_station_cargo_and_reservation(self, ctx):
        st = ctx.stations[0]
        assert st.inventory == {'energycells': (5000, 5000.0)}
        assert st.cargo_total.m3 == 5000.0
        assert st.cargo_total.max_m3 == 1000000.0
        # The buy-type reservation pre-allocates 1000 m3 of incoming cargo.
        assert st.cargo_total.adj_m3 == 6000.0

    def test_manager_crew(self, ctx):
        managers = [c for c in ctx.crew if c.role == 'manager']
        assert len(managers) == 1
        m = managers[0]
        assert m.name == 'Mira Tan'
        assert m.assigned_code == 'STA-001'
        assert m.skill_management == 14
        assert (m.faction, m.gender) == ('argon', 'female')

    def test_dockingbay_index_covers_subelements(self, ctx):
        # Every id inside the station subtree must map back to the station —
        # this is what makes homebase/commander refs resolvable at all.
        for sub_id in ('[0x1001]', '[0x1002]', '[0x1005]', '[0x1006]'):
            assert ctx.dockingbay_index[sub_id] == '[0x1000]'


# ─────────────────────────────────────────────────────────────────────────────
#  NPC station
# ─────────────────────────────────────────────────────────────────────────────

class TestNpcStation:
    def test_npc_station_resolved(self, ctx):
        assert len(ctx.npc_stations) == 1
        n = ctx.npc_stations[0]
        assert n.object_id == '[0x2000]'
        # Name assembled as {FactionShort} {TypeFromProdMacro} {Roman} ({Code}):
        # the energycells production module maps to "Solar Power Plant" and
        # nameindex="2" becomes "II".
        assert n.name == 'TEL Solar Power Plant II (TRD-042)'
        assert n.sector_macro == 'cluster_2_sector001_macro'
        # wares are NpcStationWare records (ware id + buy/sell direction) since
        # the NPC-station trade-details feature; the id list is the stable part.
        assert [w.ware_id for w in n.wares] == ['energycells', 'siliconwafers']
        assert ctx.npc_station_index['[0x2000]'] is n

    def test_npc_docked_ship_recorded_shallow(self, ctx):
        # Ships inside an NPC station subtree never reach ctx.ships; they only
        # land in npc_docked_ships for counterparty/name resolution.
        assert ctx.npc_docked_ships['[0x2100]'] == (
            'TLV-100', 'ship_tel_m_trans_container_01_a_macro', '[0x2000]')
        assert all(s.object_id != '[0x2100]' for s in ctx.ships)


# ─────────────────────────────────────────────────────────────────────────────
#  Ships + homebase resolution
# ─────────────────────────────────────────────────────────────────────────────

class TestShips:
    def test_ship_counts(self, ctx):
        # 3 player ships (docked fighter, hauler, escort) + 1 streamed NPC ship.
        assert len(ctx.ships) == 4
        assert ctx.player_ship_ids == {'[0x1100]', '[0x3000]', '[0x3100]'}

    def test_hauler_full_extraction(self, ctx):
        hauler = _ship(ctx, '[0x3000]')
        assert hauler.name == 'Hauler One'
        assert hauler.order == 'Trading'          # started TradeRoutine
        assert hauler.hull_hp == 3000.0
        assert hauler.hull_max == 6000            # from SHIP_STATS
        # One shield generator at 2875/5750, the other full (absent child).
        assert (hauler.shield_hp, hauler.shield_max) == (8625.0, 11500.0)
        # Loadout keeps duplicates (the UI counts them); thruster comes from
        # the ship attribute, not a component.
        assert sorted(hauler.loadout) == [
            ('engine',  'engine_arg_m_allround_01_mk1_macro'),
            ('shield',  'shield_arg_m_standard_01_mk1_macro'),
            ('shield',  'shield_arg_m_standard_01_mk1_macro'),
            ('thruster', 'thruster_gen_m_allround_01_mk1_macro'),
        ]
        assert hauler.pilot_id == '[0x3001]'
        pilots = [c for c in ctx.crew if c.role == 'pilot']
        assert [p.name for p in pilots] == ['Rex Calder']
        service = [c for c in ctx.crew if c.role == 'service']
        assert [c.assigned_code for c in service] == ['HAU-001']

    def test_homebase_resolved_via_traderoutine_range(self, ctx):
        # The raw range param points at the station's subordinates CONNECTION
        # ([0x1005]), not the station. The index must keep the raw ref while
        # the resolved ship carries the station's object_id.
        assert ctx.homebase_index['[0x3000]'] == '[0x1005]'
        assert _ship(ctx, '[0x3000]').homebase_id == '[0x1000]'

    def test_homebase_resolved_via_commander_fallback(self, ctx):
        # The escort has no trade order, so resolution must fall back to its
        # commander connection ref, again through dockingbay_index.
        escort = _ship(ctx, '[0x3100]')
        assert escort.commander_id == '[0x1005]'
        assert escort.homebase_id == '[0x1000]'
        assert escort.order == 'Escorting'

    def test_station_docked_ship_extracted(self, ctx):
        # Docked inside the buffered station subtree — invisible to the main
        # loop; only extract_station_docked_ships() can produce it.
        docked = _ship(ctx, '[0x1100]')
        assert docked.docked_at == '[0x1000]'
        assert docked.homebase_id == '[0x1000]'

    def test_npc_ship_streamed(self, ctx):
        npc = _ship(ctx, '[0x4000]')
        assert npc.owner_id == 'teladi'
        # Order label is captured by the streaming path (no buffered subtree).
        assert npc.order == 'Trading'
        # Hull needs child elements NPC ships never buffer.
        assert npc.hull_hp is None
        assert '[0x4000]' not in ctx.player_ship_ids

    def test_delivery_destination_from_temp_dockat(self, ctx):
        # destination + trading="1" on the temp DockAt marks a live delivery.
        assert ctx.delivery_dest_index == {'[0x3000]': '[0x2000]'}


# ─────────────────────────────────────────────────────────────────────────────
#  Sectors, resources, gates
# ─────────────────────────────────────────────────────────────────────────────

class TestGalaxy:
    def test_sectors(self, ctx):
        sec = {s.sector_macro: s for s in ctx.sectors}
        assert set(sec) == {'cluster_1_sector001_macro', 'cluster_2_sector001_macro'}
        assert sec['cluster_1_sector001_macro'].sector_name == 'Testora Prime'
        assert sec['cluster_1_sector001_macro'].cluster_macro == 'cluster_1_macro'
        assert sec['cluster_2_sector001_macro'].owner_id == 'teladi'
        assert all(s.is_discovered for s in ctx.sectors)

    def test_sector_resources_aggregate_areas(self, ctx):
        res = {(r.sector_macro, r.ware): r for r in ctx.sector_resources}
        ore = res[('cluster_1_sector001_macro', 'ore')]
        # Two ore areas: amounts sum, the higher yield level wins.
        assert ore.recharge_max == 954823 + 45000
        assert ore.yield_level == 'high'
        assert res[('cluster_1_sector001_macro', 'silicon')].yield_level == 'medium'

    def test_gate_pair_links_sectors(self, ctx):
        gates = {g.object_id: g for g in ctx.gates}
        assert set(gates) == {'[0x5000]', '[0x5100]'}
        a, b = gates['[0x5000]'], gates['[0x5100]']
        # The two endpoints must reference each other's connection ids — this
        # is what build_graph() pairs into a sector edge.
        assert a.partner_conn_id == b.conn_id
        assert b.partner_conn_id == a.conn_id
        assert a.sector_macro != b.sector_macro


# ─────────────────────────────────────────────────────────────────────────────
#  Economy log + trade post-processing
# ─────────────────────────────────────────────────────────────────────────────

class TestTrades:
    def test_raw_log_harvest(self, ctx):
        # 6 trade rows; the selloffer row (no buyer/seller) must be skipped.
        assert len(ctx.trade_log) == 6
        # The despawned seller's plain-decimal id is normalised to hex form.
        assert ctx.trade_log[0]['seller'] == '[0x355]'

    def test_removed_object_label(self, ctx):
        assert ctx.removed_codes == {'[0x355]': 'Old Heron [OLD-123]'}

    def test_postprocess_stats(self, trade_stats):
        # One row per provenance path the fixture exercises. Two suppressed
        # pickups: the completed courier's BUY leg (paired to its SELL) and the
        # pending siliconwafers pickup (which becomes an in-progress delivery).
        assert dict(trade_stats) == {
            'commercial:courier':   1,
            'commercial:visit':     1,
            'commercial:despawned': 1,
            'in-progress (suppressed)': 2,
        }

    def test_pending_pickup_becomes_in_progress_delivery(self, ctx):
        # The siliconwafers BUY leg has no later SELL leg, so it must surface
        # as an in-progress delivery instead of vanishing with the suppression.
        assert len(ctx.in_progress_deliveries) == 1
        d = ctx.in_progress_deliveries[0]
        assert d.ship_id   == '[0x3000]'
        assert d.ship_code == 'HAU-001'
        assert d.ware_id   == 'siliconwafers'
        assert d.ware_name == 'Silicon Wafers'
        assert d.amount    == 300
        assert d.from_station_id == '[0x1000]'
        # Destination resolved through the hauler's active DockAt order.
        assert d.dest_station_id   == '[0x2000]'
        assert d.dest_station_name == 'TEL Solar Power Plant II (TRD-042)'
        assert d.time_ago_s == 800.0

    def test_courier_sell_leg_attributed_to_station(self, ctx):
        rows = [t for t in ctx.trade_history if t.resolution == 'courier']
        assert len(rows) == 1
        t = rows[0]
        # SELL leg credited back to the loading station at the commercial
        # price; the ship stays the hauler, the counterparty the NPC buyer.
        assert t.station_id == '[0x1000]'
        assert t.direction == 'Out'
        assert t.ship_code == 'HAU-001'
        assert t.counterparty_id == '[0x2000]'
        assert t.counterparty_name == 'TEL Solar Power Plant II (TRD-042)'
        assert (t.amount, t.price_cr, t.total_cr) == (1000, 17.0, 17000.0)
        assert t.time_ago_s == 1000.0

    def test_npc_ship_counterparty_inferred_from_visit(self, ctx):
        rows = [t for t in ctx.trade_history if t.resolution == 'visit']
        assert len(rows) == 1
        t = rows[0]
        # The NPC ship itself is only the transport; the counterparty must be
        # the NPC station where its same-ware visit was logged.
        assert t.direction == 'In'
        assert t.ship_code == 'TLV-042'
        assert t.counterparty_id == '[0x2000]'
        assert t.counterparty_name == 'TEL Solar Power Plant II (TRD-042)'

    def test_despawned_seller_labelled(self, ctx):
        rows = [t for t in ctx.trade_history if t.resolution == 'despawned']
        assert len(rows) == 1
        t = rows[0]
        # The object is gone from the save: no counterparty, but the removed
        # block's label survives as the ship name.
        assert t.ship_name == 'Old Heron [OLD-123]'
        assert t.counterparty_id is None
        assert t.station_id == '[0x1000]'

    def test_no_internal_or_mining_rows(self, ctx):
        # The BUY leg pairs with the SELL leg, so nothing may leak into the
        # internal ledger (a row here means _attribute_sell_legs regressed).
        assert ctx.trade_history_internal == []
        assert ctx.trade_history_mining == []


# ─────────────────────────────────────────────────────────────────────────────
#  Degraded mode: no language file at all
# ─────────────────────────────────────────────────────────────────────────────

class TestNoLanguageFile:
    def test_sectors_and_gates_dropped_without_names(self, monkeypatch):
        # lang_path=None falls back to a real X4 install via gamefiles.catalog.
        # Force that lookup to fail so this test behaves the same on machines
        # that do have the game installed.
        import gamefiles.catalog as catalog
        monkeypatch.setattr(catalog, 'find_x4_install', lambda: None)

        ctx = Scanner(lang_path=None).scan(MINI_SAVE, scan_id=1)

        # SectorHandler skips unresolvable sectors BEFORE setting
        # current_sector_macro — so sectors AND gates vanish, and the station
        # loses its sector attribution. Entities themselves still parse.
        assert ctx.sectors == []
        assert ctx.gates == []
        assert len(ctx.stations) == 1
        assert ctx.stations[0].sector_macro == ''
        # Player location degrades to the raw language-reference id.
        assert ctx.player_sector == 'Sector 10011'
