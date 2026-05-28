# scanner/trade_combined_scanner.py
# ─────────────────────────────────────────────────────────────────────────────
#  COMBINED TRADE LOG + TRADE HISTORY SCANNER  (single-pass)
# ─────────────────────────────────────────────────────────────────────────────
#
#  Merges the active trade scanner (Pass 5, trade_scanner.py) and the
#  completed trade history scanner (Pass 6, economy_scanner.py) into one
#  streaming read of the save file.
#
#  WHY THEY CAN BE COMBINED CLEANLY
#  The two scanners look for completely different XML elements and maintain
#  completely independent state machines — there is zero overlap:
#
#    Pass 5 state:
#      ship_stack    — tracks which ship component we're currently inside
#                      (needed to identify the transport executing a trade)
#      in_trade_order / order_depth — detect <order order="TradePerform"> and
#                      its direct <trade buyer= seller= ...> child
#
#    Pass 6 state:
#      game_time / game_time_found — captures <game time="..."> for timestamps
#      in_trade_entries — detect <entries type="trade"> and its <log> children
#
#  The two state machines never touch the same elements and can run side by
#  side in the same iterparse loop with no risk of interference.

import pathlib
from lxml import etree as ET

from data.wares import WARE_NAMES
from scanner.language import open_save

# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────

# Station component classes — mirrors station_scanner.STATION_CLASSES.
# Economy log <entries type="trade"> blocks appear inside station subtrees;
# detecting which NPC station we're inside lets us annotate every log entry
# with the counterparty station ID directly (no ship → homebase chain needed).
_STATION_CLASSES = {"station", "factory", "headquarters", "complex"}


def _norm(raw: str) -> str:
    """
    Normalise a component ID to bracketed-hex format "[0xNN]".

    X4 economy log attributes use two ID formats:
      "[0x1234]" — bracketed hex (most entries)
      "853"      — plain decimal (occasional entries)

    Both refer to the same component-ID space. Normalising to "[0xNN]" makes
    lookups against homebase_index and player_station_ids consistent regardless
    of which format the save file happens to use for a particular entry.
    """
    if not raw or raw.startswith('['):
        return raw
    try:
        return f'[{hex(int(raw))}]'
    except ValueError:
        return raw

# ─────────────────────────────────────────────────────────────────────────────
#  COMBINED SCANNER
# ─────────────────────────────────────────────────────────────────────────────

def scan_trade_log_and_history(
    file_path:          pathlib.Path,
    player_station_ids: set,
    id_to_code:         dict,
    player_ship_ids:    set | None = None,
) -> dict:
    """
    Streams the save file once and returns both active trade orders and
    completed trade history, using the same filter inputs for both.

    Args:
        file_path:          Path to the .xml or .xml.gz save file.
        player_station_ids: Set of hex object IDs for player-owned stations.
                            Trades where neither station is player-owned are
                            still included when the transport ship is.
        id_to_code:         Hex object ID → display code for buyer/seller and
                            station resolution. Unresolved IDs show as raw hex.
        player_ship_ids:    Optional set of hex object IDs for player-owned
                            ships. When provided, active trades where a player
                            ship is the executing transport are included even
                            when neither station is player-owned.

    Returns a dict:
        "trades"        — list of active TradePerform order dicts
                          (same shape as scan_trade_orders returns)
        "trade_history" — list of completed economylog entry dicts
                          (same shape as scan_trade_history returns)
    """
    if not player_station_ids and not (player_ship_ids or set()):
        return {"trades": [], "trade_history": []}

    _ship_ids = player_ship_ids or set()

    # ── Active trade order state (Pass 5) ─────────────────────────────────────
    # ship_stack tracks the current ship context as a LIFO stack.
    # Each entry is (ship_id, ship_code). Pushing on the opening tag of any
    # ship component and popping on its closing tag gives us the correct
    # transport ship even when ships are nested (e.g. fighters inside carriers).
    active_trades:  list[dict]        = []
    in_trade_order: bool              = False
    order_depth:    int               = 0
    ship_stack:     list[tuple[str, str]] = []

    # ── Completed trade history state (Pass 6) ────────────────────────────────
    # game_time is captured from <game time="..."> near the top of the save.
    # It is subtracted from each log entry's own timestamp to produce a
    # "seconds ago" value (time_ago_s) that is always >= 0.
    history_trades:  list[dict] = []
    game_time:       float      = 0.0
    game_time_found: bool       = False
    in_trade_entries: bool      = False   # True while inside <entries type="trade">

    # ── Economylog removed-object state (Pass 6 extension) ───────────────────────
    # <economylog><removed> lists ships/stations that made trades but have since
    # despawned. Their plain-decimal object IDs appear as buyer/seller in log
    # entries. We collect them here so those entries resolve to a readable label.
    #
    # X4 records two distinct ID formats in economy log entries:
    #   "[0x1234]" — bracketed hex  (persistent components still in the save)
    #   "408"      — plain decimal  (economy objects now in <removed>)
    # _norm() converts both to "[0xNN]" before lookup; removed_codes is keyed
    # the same way so id_to_code → removed_codes → raw-hex is a clean chain.
    in_removed:    bool           = False
    removed_codes: dict[str, str] = {}

    # ── NPC station context for economy log (Pass 6) ───────────────────────────
    # X4 records each completed trade in the economy log of BOTH the buyer and
    # the seller station. When we are inside an NPC station's <component> subtree
    # we can read the counterparty station's object_id directly from the XML
    # rather than going through the fragile ship → homebase chain.
    #
    # in_npc_station — True while streaming through an NPC station's subtree.
    # npc_station_id — the NPC station's object_id (set when in_npc_station=True).
    # npc_depth      — element nesting depth from the station's own opening tag.
    #                  Decrements on every end event; reaches 0 when the station's
    #                  own closing tag arrives, signalling we have left the subtree.
    in_npc_station: bool = False
    npc_station_id: str  = ''
    npc_depth:      int  = 0

    print(
        f"[Scanning] Trade log + history — scanning TradePerform orders and "
        f"economylog entries ({len(player_station_ids)} player station(s), "
        f"{len(_ship_ids)} player ship(s) as filter)..."
    )

    try:
        with open_save(file_path) as f:
            context = ET.iterparse(f, events=('start', 'end'))

            for event, elem in context:
                tag = elem.tag

                if event == 'start':

                    # ── NPC station depth tracking (Pass 6) ───────────────────
                    # Increment depth for EVERY element while inside an NPC
                    # station subtree. This is the broadest possible counter —
                    # any start event inside the station adds 1 regardless of
                    # tag, so the corresponding end event always subtracts 1 and
                    # the depth reaches exactly 0 when the station's own closing
                    # tag fires. (The station's opening tag contributes the
                    # initial depth=1 in the NPC-station-detection block below.)
                    if in_npc_station:
                        npc_depth += 1

                    # ── Economylog removed-object collection (Pass 6) ────────
                    if tag == 'removed':
                        in_removed = True

                    if in_removed and tag == 'object':
                        _raw_id = elem.get('id', '')
                        # Only decimal-format IDs belong to removed economy
                        # objects; hex-bracket IDs in other <removed> sections
                        # are a different concept and should not be collected.
                        if _raw_id and not _raw_id.startswith('['):
                            _rname = elem.get('name', '')
                            _rcode = elem.get('code', '')
                            if _rname:
                                _rlabel = f"{_rname} [{_rcode}]" if _rcode else _rname
                                removed_codes[_norm(_raw_id)] = _rlabel

                    # ── Game time capture (Pass 6) ────────────────────────────
                    # <game time="..."> appears near the top of every save.
                    # We capture it once for use in trade history timestamps.
                    if tag == 'game' and not game_time_found:
                        try:
                            game_time       = float(elem.get('time', 0))
                            game_time_found = True
                        except (ValueError, TypeError):
                            pass

                    # ── Ship component tracking (Pass 5) ──────────────────────
                    # Maintain a stack of the ship components we're currently
                    # inside. This tells us which ship is executing a
                    # TradePerform order when we hit its <trade> child element.
                    if tag == 'component':
                        cls = elem.get('class', '')
                        if cls.startswith('ship_'):
                            ship_stack.append((
                                elem.get('id',   ''),
                                elem.get('code', ''),
                            ))

                    # ── NPC station entry detection (Pass 6) ──────────────────
                    # When we enter a station-class component owned by a non-
                    # player faction, record it as the current economy log owner.
                    # Stations do not nest inside each other in X4, so we only
                    # enter this branch when not already tracking an NPC station.
                    # The initial depth is set to 1 here (the station's own
                    # opening tag); every subsequent element increments it above.
                    if tag == 'component' and not in_npc_station:
                        comp_cls = elem.get('class', '')
                        owner    = elem.get('owner', '')
                        if comp_cls in _STATION_CLASSES and owner and owner != 'player':
                            in_npc_station = True
                            npc_station_id = elem.get('id', '')
                            npc_depth      = 1   # station's own opening tag

                    # ── TradePerform order detection (Pass 5) ─────────────────
                    if not in_trade_order:
                        if tag == 'order' and elem.get('order') == 'TradePerform':
                            in_trade_order = True
                            order_depth    = 1
                    else:
                        order_depth += 1

                        # The <trade> element is the direct child of <order>
                        # (depth 2). Its buyer/seller/ware/price attributes are
                        # all present on the opening tag, so we read them now.
                        if tag == 'trade' and order_depth == 2:
                            buyer_id  = elem.get('buyer',  '')
                            seller_id = elem.get('seller', '')

                            current_ship_id   = ship_stack[-1][0] if ship_stack else ''
                            current_ship_code = ship_stack[-1][1] if ship_stack else ''

                            buyer_is_player  = buyer_id  in player_station_ids
                            seller_is_player = seller_id in player_station_ids
                            ship_is_player   = bool(_ship_ids) and current_ship_id in _ship_ids

                            if buyer_is_player or seller_is_player or ship_is_player:
                                try:
                                    amount   = int(float(elem.get('amount', 0)))
                                    price_cr = float(elem.get('price', 0)) / 100
                                except (ValueError, TypeError):
                                    amount = 0; price_cr = 0.0

                                if amount > 0:
                                    ware_id   = elem.get('ware', '')
                                    ware_name = WARE_NAMES.get(
                                        ware_id, ware_id.replace('_', ' ').title()
                                    )
                                    active_trades.append({
                                        'buyer_id':    buyer_id,
                                        'seller_id':   seller_id,
                                        'buyer_code':  id_to_code.get(buyer_id,  buyer_id)  if buyer_id  else '—',
                                        'seller_code': id_to_code.get(seller_id, seller_id) if seller_id else '—',
                                        'ship_id':     current_ship_id,
                                        'ship_code':   current_ship_code,
                                        'ware':        ware_id,
                                        'ware_name':   ware_name,
                                        'amount':      amount,
                                        'price_cr':    price_cr,
                                        'total_cr':    amount * price_cr,
                                        'player_is_buyer':  buyer_is_player,
                                        'player_is_seller': seller_is_player,
                                        'player_is_ship':   ship_is_player and not buyer_is_player and not seller_is_player,
                                    })

                    # ── Economylog section detection (Pass 6) ─────────────────
                    # <entries type="trade"> can appear multiple times — once
                    # globally and once per station that has logged trades.
                    # We re-enter the flag each time so all blocks are captured.
                    if tag == 'entries' and elem.get('type') == 'trade':
                        in_trade_entries = True

                    # ── Economylog entry (Pass 6) ─────────────────────────────
                    # Each <log type="trade"> inside an entries block is one
                    # completed transaction. The 'v' attribute is the volume
                    # (units traded); 'price' is stored in cents (÷ 100 → Cr).
                    elif in_trade_entries and tag == 'log' and elem.get('type') == 'trade':
                        # Normalise to "[0xNN]" bracketed-hex format.
                        # X4 economy log attributes use two formats: "[0x1234]"
                        # and plain decimal (e.g. "853"). _norm() makes both
                        # consistent so player_station_ids lookups and the
                        # homebase_index fallback work regardless of which format
                        # this particular log entry happens to use.
                        buyer_id  = _norm(elem.get('buyer',  ''))
                        seller_id = _norm(elem.get('seller', ''))

                        buyer_is_player       = buyer_id  in player_station_ids
                        seller_is_player      = seller_id in player_station_ids
                        # Also capture trades where a player SHIP is the buyer or
                        # seller — e.g. a player trader picking up from a player
                        # station then delivering to an NPC station, or vice versa.
                        buyer_ship_is_player  = buyer_id  in _ship_ids
                        seller_ship_is_player = seller_id in _ship_ids

                        if (buyer_is_player or seller_is_player
                                or buyer_ship_is_player or seller_ship_is_player):
                            try:
                                amount     = int(float(elem.get('v', 0)))
                                price_cr   = float(elem.get('price', 0)) / 100
                                entry_time = float(elem.get('time', game_time))
                            except (ValueError, TypeError):
                                amount = 0; price_cr = 0.0; entry_time = game_time

                            if amount > 0:
                                ware_id   = elem.get('ware', '')
                                ware_name = WARE_NAMES.get(
                                    ware_id, ware_id.replace('_', ' ').title()
                                )
                                history_trades.append({
                                    'buyer_id':        buyer_id,
                                    'seller_id':       seller_id,
                                    # id_to_code first (persistent component), then
                                    # removed_codes (despawned economy object whose
                                    # plain-decimal ID was normalised by _norm()),
                                    # then raw hex as last resort.
                                    'buyer_code':      id_to_code.get(buyer_id,  removed_codes.get(buyer_id,  buyer_id))  if buyer_id  else '—',
                                    'seller_code':     id_to_code.get(seller_id, removed_codes.get(seller_id, seller_id)) if seller_id else '—',
                                    'ware':            ware_id,
                                    'ware_name':       ware_name,
                                    'amount':          amount,
                                    'price_cr':        price_cr,
                                    'total_cr':        amount * price_cr,
                                    'time_ago_s':      max(0.0, game_time - entry_time),
                                    'player_is_buyer':        buyer_is_player,
                                    'player_is_seller':       seller_is_player,
                                    # True when a player-owned SHIP (not station) is
                                    # on that side — covers the second leg of a player
                                    # trader's route (e.g. ship sells to NPC station).
                                    'player_ship_is_buyer':   buyer_ship_is_player,
                                    'player_ship_is_seller':  seller_ship_is_player,
                                    # Direct NPC station reference — set when this
                                    # log entry appears inside an NPC station's
                                    # subtree. That station IS the counterparty.
                                    # Empty string when inside a player station's
                                    # log or in a global entries block.
                                    'counterparty_station_id': npc_station_id,
                                    # Internal deduplication key — the same trade
                                    # is logged by both the buyer and seller station,
                                    # so we may see it twice. Popped before returning.
                                    '_dup_key': (
                                        buyer_id, seller_id,
                                        ware_id,  elem.get('time', ''),
                                    ),
                                })

                elif event == 'end':

                    # ── Ship component tracking (Pass 5) ──────────────────────
                    # Pop before clearing — elem's attributes are still readable
                    # here; elem.clear() below would wipe them.
                    if tag == 'component':
                        cls = elem.get('class', '')
                        if cls.startswith('ship_') and ship_stack:
                            ship_stack.pop()

                    # ── TradePerform order depth (Pass 5) ─────────────────────
                    if in_trade_order:
                        order_depth -= 1
                        if order_depth == 0:
                            in_trade_order = False

                    # ── Economylog removed section close (Pass 6) ─────────────
                    if tag == 'removed' and in_removed:
                        in_removed = False

                    # ── Economylog section close (Pass 6) ─────────────────────
                    if tag == 'entries' and in_trade_entries:
                        in_trade_entries = False

                    # ── NPC station depth tracking (Pass 6) ───────────────────
                    # Decrement for EVERY end event while inside the NPC station.
                    # When depth reaches 0 the station's own closing tag has just
                    # been processed — we've left the subtree and must reset.
                    if in_npc_station:
                        npc_depth -= 1
                        if npc_depth == 0:
                            in_npc_station = False
                            npc_station_id = ''

                    elem.clear()

    except ET.XMLSyntaxError as e:
        print(f"\n[XML Error] Save file has a formatting issue: {e}")
        raise

    # ── Deduplicate trade history ──────────────────────────────────────────────
    # X4 records each completed trade in the economy log of both the buying and
    # the selling station, so the same transaction appears twice in the save file.
    # We keep only one copy per trade. When two copies of the same entry exist,
    # we prefer the one with counterparty_station_id set (from the NPC station's
    # log), because that gives us the resolved counterparty for free. The _dup_key
    # tuple (buyer, seller, ware, raw-time-string) uniquely identifies each trade.
    seen_trades: dict = {}   # _dup_key → entry dict
    for entry in history_trades:
        key      = entry.pop('_dup_key')   # remove internal field before storing
        existing = seen_trades.get(key)
        if existing is None:
            seen_trades[key] = entry
        elif (not existing.get('counterparty_station_id')
              and entry.get('counterparty_station_id')):
            # Replace the earlier copy with the more informative NPC-station copy.
            seen_trades[key] = entry
    history_trades = list(seen_trades.values())

    # ── Sort active trades (mirrors scan_trade_orders output order) ────────────
    active_trades.sort(key=lambda t: (
        t['buyer_code']  if t['player_is_buyer']  else '',
        t['seller_code'] if t['player_is_seller'] else '',
        t.get('ship_code', '') if t.get('player_is_ship') else '',
        t['ware_name'],
    ))

    # ── Summary ────────────────────────────────────────────────────────────────
    station_hits = sum(1 for t in active_trades  if not t['player_is_ship'])
    ship_hits    = sum(1 for t in active_trades  if t['player_is_ship'])
    bought      = sum(1 for t in history_trades if t['player_is_buyer'])
    sold        = sum(1 for t in history_trades if t['player_is_seller'])
    ship_bought = sum(1 for t in history_trades if t.get('player_ship_is_buyer'))
    ship_sold   = sum(1 for t in history_trades if t.get('player_ship_is_seller'))
    print(
        f"[Scanning] Active trades  — {len(active_trades)} order(s) "
        f"({station_hits} via station filter, {ship_hits} via ship filter)."
    )
    print(
        f"[Scanning] Trade history  — {len(history_trades)} completed trade(s) "
        f"({bought} station purchases, {sold} station sales, "
        f"{ship_bought} ship purchases, {ship_sold} ship sales)."
    )

    return {
        "trades":        active_trades,
        "trade_history": history_trades,
    }
