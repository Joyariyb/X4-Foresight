"""Core role: Converts raw economy-log rows into resolved TradeHistory entities with ship and counterparty distinction.

Runs once after full parse when all IDs are indexed. Key model: ship (transport) and counterparty (far-end station)
are kept strictly separate to avoid conflating them — a classic bug.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from data.wares import WARE_NAMES
from .entities import TradeHistory, TradeHistoryInternal, TradeHistoryMining
from .ship_names import ship_display_name


def _ware_name(ware_id: str) -> str:
    return WARE_NAMES.get(ware_id, ware_id.replace('_', ' ').title())


class TradePostProcessor:
    """
    Resolves ctx.trade_log into ctx.trade_history + ctx.trade_history_internal.

        stats = TradePostProcessor().run(ctx)

    `stats` is a Counter of provenance labels for the coverage report.
    """

    def run(self, ctx) -> Counter:
        # ── Indexes from the finished scan ────────────────────────────────────
        self.pstn_ids      = set(ctx.player_station_ids)
        self.pship_ids     = set(ctx.player_ship_ids)
        self.pbuildstorage = set(ctx.player_buildstorage_ids)
        self.npc_stn   = ctx.npc_station_index               # id → NpcStation
        self.pstn_by_id = {s.object_id: s for s in ctx.stations if s.object_id}
        self.ship_by_id = {s.object_id: s for s in ctx.ships if s.object_id}
        self.homebase   = ctx.homebase_index
        self.delivery   = ctx.delivery_dest_index
        self.removed    = ctx.removed_codes
        self.npc_docked = ctx.npc_docked_ships   # ship_id → (code, macro, station_id)
        self.ctx        = ctx

        # ── Flag rows with player-involvement booleans; keep player rows ──────
        rows: list[dict] = []
        for r in ctx.trade_log:
            b, s = r['buyer'], r['seller']
            row = {
                **r,
                'player_is_buyer':       b in self.pstn_ids,
                'player_is_seller':      s in self.pstn_ids,
                'player_ship_is_buyer':  b in self.pship_ids,
                'player_ship_is_seller': s in self.pship_ids,
            }
            if (row['player_is_buyer'] or row['player_is_seller']
                    or row['player_ship_is_buyer'] or row['player_ship_is_seller']):
                rows.append(row)

        # ── Build inference indexes (Step 4 visits, Step 5 sector buyers) ─────
        self._build_inference_indexes(ctx)

        # ── Pair player-courier legs (sets _homebase_seller_* and suppresses) ─
        self._attribute_sell_legs(rows)
        self._suppress_pending_pickups(rows)

        # ── Classify + resolve + emit each row ────────────────────────────────
        stats: Counter = Counter()
        for e in rows:
            self._process(e, stats)
        return stats

    # ──────────────────────────────────────────────────────────────────────────
    #  Inference indexes  (Step 4 visits, Step 5 sector-ware buyers)
    # ──────────────────────────────────────────────────────────────────────────

    def _build_inference_indexes(self, ctx) -> None:
        """
        Build the two evidence indexes used to resolve NPC free-traders, both
        derived purely from the harvested trade log (no extra scan).

        visits[ship_id] → [(npc_station_id, ware, time_ago_s), ...]
            Every log row with exactly one known NPC station: the OTHER side is a
            visiting transport. Records what ware it moved there and when, so a
            ship's counterparty can be matched to a specific same-ware visit.

        sector_ware_buyers[(sector_macro, ware)] → {npc_station_id, ...}
            NPC stations that appear as a BUYER of a ware, grouped by their own
            sector. Drives 'player sells ware X in sector S → the lone NPC
            consumer of X in S' inference.
        """
        self.visits = defaultdict(list)
        self.sector_ware_buyers = defaultdict(set)
        npc = self.npc_stn
        for r in ctx.trade_log:
            b, s, ware = r['buyer'], r['seller'], r['ware']
            b_is, s_is = b in npc, s in npc
            if b_is ^ s_is:  # exactly one side is a known NPC station
                station, visitor = (b, s) if b_is else (s, b)
                self.visits[visitor].append((station, ware, r['time_ago_s']))
            if b_is and ware:
                # The NPC buyer consumes this ware in its own sector.
                sect = npc[b].sector_macro
                if sect:
                    self.sector_ware_buyers[(sect, ware)].add(b)

    # ──────────────────────────────────────────────────────────────────────────
    #  Small helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _as_station(self, oid):
        """Return (code, name) if oid is a known station, else None."""
        npc = self.npc_stn.get(oid)
        if npc is not None:
            return (npc.code, npc.name)
        pst = self.pstn_by_id.get(oid)
        if pst is not None:
            return (pst.code, pst.name)
        return None

    def _resolve_ship(self, ship_id):
        """
        Return (ship_id, ship_code, ship_name) for a transport ship id.

        ship_name is the canonical display name (custom name, else the resolved
        type name like "Ides Vanguard") — never a bare code, so a row reads
        "Ides Vanguard [WNP-362]" rather than "WNP-362 [WNP-362]".
        """
        if not ship_id:
            return '', '', ''
        sh = self.ship_by_id.get(ship_id)
        if sh is not None:
            return ship_id, sh.code, ship_display_name(sh.macro, sh.name)
        info = self.npc_docked.get(ship_id)
        if info:
            code, macro, _ = info
            return ship_id, code, ship_display_name(macro, None)
        label = self.removed.get(ship_id)
        if label:
            # Despawned object — only a "Name [CODE]" label survives in removed.
            return ship_id, label, label
        return ship_id, ship_id, ship_id   # raw id fallback

    def _chase(self, ship_id, ware, time_ago, player_sector, is_sell):
        """
        Given a TRANSPORT ship id, find the counterparty STATION at the other end
        of its route. Returns (cp_id, cp_name, provenance) — cp_* None if unresolved.

        Cascade order is strongest evidence first. Provenance records
        which rung resolved it so the UI can flag proven vs inferred:

          PLAYER ship   → only its live delivery destination is meaningful (its
                          homebase is the SOURCE player station, not the buyer).
          NPC/despawned → homebase (Middleman, stable)        [inferred: homebase]
                        → visits  (same-ware logged visit)     [inferred: visit]
                        → sector  (lone NPC consumer in sector)[inferred: sector]
                        → delivery (live DockAt target)        [inferred: delivery]
        """
        # Player courier not caught by SELL-leg attribution — only its current
        # destination tells us anything (homebase would point back at our station).
        if ship_id in self.pship_ids:
            dest = self.delivery.get(ship_id)
            if dest:
                stn = self._as_station(dest)
                if stn:
                    return dest, stn[1], 'delivery'
            return None, None, 'unresolved'

        # Step 3 — homebase (Middleman assignment, stable).
        hb = self.homebase.get(ship_id)
        if hb:
            stn = self._as_station(hb)
            if stn:
                return hb, stn[1], 'homebase'

        # Step 3b — NPC dock: ship is physically sitting in an NPC station's bay
        # at save time. Strongest per-ship evidence after homebase — a ship
        # docked here either just delivered or is about to load for a run.
        info = self.npc_docked.get(ship_id)
        if info:
            _, _, dock_id = info
            stn = self._as_station(dock_id)
            if stn:
                return dock_id, stn[1], 'docked'

        # Step 4 — visits: the ship's own logged trade of THIS ware at an NPC
        # station, closest in time. Per-trade evidence, beats a sector guess.
        vs = self.visits.get(ship_id)
        if vs:
            cands = [(abs(t - time_ago), sid) for (sid, w, t) in vs if w == ware]
            if cands:
                cands.sort()
                sid = cands[0][1]
                stn = self._as_station(sid)
                if stn:
                    return sid, stn[1], 'visit'

        # Step 5 — sector-ware inference (player-sells only): the single NPC
        # consumer of this ware in the player station's sector, then — if that
        # yields nothing — in the ship's own sector. sector_ware_buyers is
        # already activity-filtered (built from trade log rows), so both lookups
        # automatically exclude stations with no recent transactions.
        if is_sell:
            sh = self.ship_by_id.get(ship_id)
            ship_sector = sh.sector_macro if sh else ''
            for sect in dict.fromkeys(s for s in (player_sector, ship_sector) if s):
                buyers = self.sector_ware_buyers.get((sect, ware))
                if buyers and len(buyers) == 1:
                    sid = next(iter(buyers))
                    stn = self._as_station(sid)
                    if stn:
                        return sid, stn[1], 'sector'

        # Step 6 — delivery: the ship's live DockAt destination. Last resort —
        # correct for recent loads, stale for old ones, so it ranks below the
        # per-trade evidence above.
        dest = self.delivery.get(ship_id)
        if dest:
            stn = self._as_station(dest)
            if stn:
                return dest, stn[1], 'delivery'

        # Explicitly flag despawned ships so the display can distinguish "we know
        # it's gone" from "we just don't know who this is".
        if self.removed.get(ship_id):
            return None, None, 'despawned'

        return None, None, 'unresolved'

    def _resolve_other(self, other_id, ware, time_ago, player_sector, is_sell):
        """
        Resolve the non-player-station side of a row into a (ship, counterparty)
        pair — the heart of the ship/counterparty separation.

        Returns (ship_id, ship_code, ship_name, cp_id, cp_name, provenance).

        If other_id is itself a station  → direct trade: no ship, counterparty=other.
        If other_id is a transport ship  → ship=other, counterparty=chase(other).
        """
        stn = self._as_station(other_id)
        if stn is not None:
            # Direct station↔station — there is no transport ship in this row.
            return '', '', '', other_id, stn[1], 'direct'

        # other_id is a transport ship (player/NPC/despawned).
        ship_id, ship_code, ship_name = self._resolve_ship(other_id)
        cp_id, cp_name, prov = self._chase(other_id, ware, time_ago, player_sector, is_sell)
        return ship_id, ship_code, ship_name, cp_id, cp_name, prov

    # ──────────────────────────────────────────────────────────────────────────
    #  Player-courier SELL-leg attribution
    # ──────────────────────────────────────────────────────────────────────────

    def _attribute_sell_legs(self, rows) -> None:
        """
        A player courier logs two rows per delivery:
          BUY leg  — player station sells to the player ship (internal price)
          SELL leg — player ship sells to the NPC buyer  (commercial price)

        Pair them by (ship_id, ware); attribute the SELL leg to the player
        station that loaded the ship (the BUY leg's seller) at the commercial
        price, and suppress the internal-price BUY leg.
        """
        buy_idx = defaultdict(list)
        for e in rows:
            if e['player_is_seller'] and e['player_ship_is_buyer']:
                buy_idx[(e['buyer'], e['ware'])].append(e)

        for e in rows:
            if (not e['player_ship_is_seller']
                    or e['player_is_buyer'] or e['player_is_seller']):
                continue
            cands = buy_idx.get((e['seller'], e['ware']))
            if not cands:
                continue
            best = min(cands, key=lambda x: abs(x['time_ago_s'] - e['time_ago_s']))
            station_id = best['seller']
            st = self.pstn_by_id.get(station_id) if station_id in self.pstn_ids else None
            if st is None:
                continue
            e['_homebase_seller_id']   = station_id
            e['_homebase_seller_code'] = st.code
            e['_homebase_seller_name'] = st.name
            best['_courier_pickup']    = True

    def _suppress_pending_pickups(self, rows) -> None:
        """BUY leg with no later SELL leg = picked up but not delivered → suppress."""
        min_sell: dict = {}
        for e in rows:
            if (not e['player_ship_is_seller']
                    or e['player_is_buyer'] or e['player_is_seller']):
                continue
            k = (e['seller'], e['ware'])
            if e['time_ago_s'] < min_sell.get(k, float('inf')):
                min_sell[k] = e['time_ago_s']
        for e in rows:
            if e.get('_courier_pickup'):
                continue
            if not (e['player_is_seller'] and e['player_ship_is_buyer']):
                continue
            k = (e['buyer'], e['ware'])
            if e['time_ago_s'] < min_sell.get(k, float('inf')):
                e['_courier_pickup'] = True

    # ──────────────────────────────────────────────────────────────────────────
    #  Per-row classify → resolve → emit
    # ──────────────────────────────────────────────────────────────────────────

    def _process(self, e, stats) -> None:
        # In-progress courier pickups are not completed history.
        if e.get('_courier_pickup'):
            stats['in-progress (suppressed)'] += 1
            return

        # Internal: both player stations, or player station buys from own ship.
        if e['player_is_buyer'] and e['player_is_seller']:
            stats['internal'] += 1
            self._emit_internal(e)
            return
        # A player station selling to its own construction platform (buildstorage).
        # These are internal material transfers; the buildstorage never trades with
        # the open market so its NPC purchases are excluded from player trade history.
        if e['player_is_seller'] and e['buyer'] in self.pbuildstorage:
            stats['internal'] += 1
            self._emit_internal(e)
            return
        if e['player_is_buyer'] and e['player_ship_is_seller']:
            # A player station buying from a player ship. If that ship is a
            # MINER, this is a mining delivery (miner → its home station), not a
            # station-to-station transfer — classify it as such so it doesn't
            # show the confusing "STN ↔ STN" self-reference.
            seller = self.ship_by_id.get(e['seller'])
            if seller is not None and seller.role.startswith('Miner'):
                stats['mining'] += 1
                self._emit_mining(e)
            else:
                stats['internal'] += 1
                self._emit_internal(e)
            return

        # Attributed SELL leg: player ship sold to NPC, credited to the player
        # station that loaded it. Ship = the player ship (seller); counterparty
        # = the NPC buyer (resolved directly or chased).
        hb_id = e.get('_homebase_seller_id')
        if hb_id:
            ship_id, ship_code, ship_name = self._resolve_ship(e['seller'])
            cp = self._as_station(e['buyer'])
            if cp is not None:
                # Player courier sold directly to a named station → proven.
                cp_id, cp_name, prov = e['buyer'], cp[1], 'courier'
            else:
                hb_st = self.pstn_by_id.get(hb_id)
                cp_id, cp_name, prov = self._chase(
                    e['buyer'], e['ware'], e['time_ago_s'],
                    hb_st.sector_macro if hb_st else '', True,
                )
            self._emit_resolved(
                e, station_id=hb_id,
                station_code=e['_homebase_seller_code'],
                station_name=e['_homebase_seller_name'],
                direction='Out',
                ship_id=ship_id, ship_code=ship_code, ship_name=ship_name,
                cp_id=cp_id, cp_name=cp_name, prov=prov, stats=stats,
            )
            return

        # Player station directly buys or sells. The OTHER side is the transport
        # ship (or, occasionally, a station for a direct station↔station trade).
        if e['player_is_buyer']:
            st = self.pstn_by_id.get(e['buyer'])
            station_id, direction, other = e['buyer'], 'In', e['seller']
        elif e['player_is_seller']:
            st = self.pstn_by_id.get(e['seller'])
            station_id, direction, other = e['seller'], 'Out', e['buyer']
        else:
            # Player ship only, not attributable to a station → not a station trade.
            stats['ship-only (not station trade)'] += 1
            return

        player_sector = st.sector_macro if st else ''
        ship_id, ship_code, ship_name, cp_id, cp_name, prov = self._resolve_other(
            other, e['ware'], e['time_ago_s'], player_sector, direction == 'Out',
        )
        self._emit_resolved(
            e, station_id=station_id,
            station_code=(st.code if st else station_id),
            station_name=(st.name if st else station_id),
            direction=direction,
            ship_id=ship_id, ship_code=ship_code, ship_name=ship_name,
            cp_id=cp_id, cp_name=cp_name, prov=prov, stats=stats,
        )

    def _emit_resolved(self, e, *, station_id, station_code, station_name,
                       direction, ship_id, ship_code, ship_name,
                       cp_id, cp_name, prov, stats) -> None:
        """
        Decide internal-vs-commercial from the resolved counterparty.

        PLAYER-STATION GUARD: if the counterparty resolves to one of OUR own
        stations, the transport is shuttling goods between player stations — an
        internal transfer, not a commercial sale. Emitting it as commercial with
        a player-station 'counterparty' would wrongly count our own shuttling
        as sales to ourselves. Route it to the internal ledger.
        """
        if cp_id and cp_id in self.pstn_ids:
            stats['internal (counterparty is player station)'] += 1
            self._emit_internal_pair(e, station_id, cp_id, ship_id, ship_code, ship_name)
            return
        self._emit_commercial(
            e, station_id=station_id, station_code=station_code, station_name=station_name,
            direction=direction, ship_id=ship_id, ship_code=ship_code, ship_name=ship_name,
            cp_id=cp_id, cp_name=cp_name, prov=prov, stats=stats,
        )

    def _emit_internal_pair(self, e, a_id, b_id, ship_id, ship_code, ship_name) -> None:
        """Emit an internal transfer between two explicit player stations."""
        a = self.pstn_by_id.get(a_id)
        b = self.pstn_by_id.get(b_id)
        self.ctx.trade_history_internal.append(TradeHistoryInternal(
            scan_id        = self.ctx.scan_id,
            station_a_id   = a_id,
            station_a_code = a.code if a else a_id,
            station_a_name = a.name if a else a_id,
            station_b_id   = b_id,
            station_b_code = b.code if b else b_id,
            station_b_name = b.name if b else b_id,
            ship_id        = ship_id,
            ship_code      = ship_code,
            ship_name      = ship_name,
            ware_id        = e['ware'],
            ware_name      = _ware_name(e['ware']),
            amount         = e['amount'],
            price_cr       = e['price_cr'],
            total_cr       = e['total_cr'],
            game_time_s    = e['game_time_s'],
            time_ago_s     = e['time_ago_s'],
        ))

    def _emit_commercial(self, e, *, station_id, station_code, station_name,
                         direction, ship_id, ship_code, ship_name,
                         cp_id, cp_name, prov, stats) -> None:
        stats[f'commercial:{prov}'] += 1
        self.ctx.trade_history.append(TradeHistory(
            scan_id           = self.ctx.scan_id,
            station_id        = station_id,
            station_code      = station_code,
            station_name      = station_name,
            direction         = direction,
            ship_id           = ship_id,
            ship_code         = ship_code,
            ship_name         = ship_name,
            ware_id           = e['ware'],
            ware_name         = _ware_name(e['ware']),
            amount            = e['amount'],
            price_cr          = e['price_cr'],
            total_cr          = e['total_cr'],
            counterparty_id   = cp_id,
            counterparty_name = cp_name,
            game_time_s       = e['game_time_s'],
            time_ago_s        = e['time_ago_s'],
            resolution        = prov if (cp_name or prov == 'despawned') else '',
        ))

    def _emit_mining(self, e) -> None:
        """A player mining ship delivered raw resource to a player station."""
        st = self.pstn_by_id.get(e['buyer'])
        ship_id, ship_code, ship_name = self._resolve_ship(e['seller'])
        self.ctx.trade_history_mining.append(TradeHistoryMining(
            scan_id      = self.ctx.scan_id,
            station_id   = e['buyer'],
            station_code = st.code if st else e['buyer'],
            station_name = st.name if st else e['buyer'],
            ship_id      = ship_id,
            ship_code    = ship_code,
            ship_name    = ship_name,
            ware_id      = e['ware'],
            ware_name    = _ware_name(e['ware']),
            amount       = e['amount'],
            price_cr     = e['price_cr'],
            total_cr     = e['total_cr'],
            game_time_s  = e['game_time_s'],
            time_ago_s   = e['time_ago_s'],
        ))

    def _emit_internal(self, e) -> None:
        # For buildstorage trades, player_is_buyer is False; pick b from
        # direct buyer/seller instead of relying on the flag.
        if e['player_is_seller']:
            a_id, b_id = e['seller'], e['buyer']
        else:
            a_id, b_id = e['buyer'], e['seller']
        a = self.pstn_by_id.get(a_id)
        b = self.pstn_by_id.get(b_id)
        ship_side = (e['buyer'] if e['player_ship_is_buyer']
                     else e['seller'] if e['player_ship_is_seller'] else '')
        ship_id, ship_code, ship_name = self._resolve_ship(ship_side)
        self.ctx.trade_history_internal.append(TradeHistoryInternal(
            scan_id        = self.ctx.scan_id,
            station_a_id   = a_id,
            station_a_code = a.code if a else a_id,
            station_a_name = a.name if a else a_id,
            station_b_id   = b_id,
            station_b_code = b.code if b else b_id,
            station_b_name = b.name if b else b_id,
            ship_id        = ship_id,
            ship_code      = ship_code,
            ship_name      = ship_name,
            ware_id        = e['ware'],
            ware_name      = _ware_name(e['ware']),
            amount         = e['amount'],
            price_cr       = e['price_cr'],
            total_cr       = e['total_cr'],
            game_time_s    = e['game_time_s'],
            time_ago_s     = e['time_ago_s'],
        ))
