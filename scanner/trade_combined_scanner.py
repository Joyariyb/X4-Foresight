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
                        buyer_id  = elem.get('buyer',  '')
                        seller_id = elem.get('seller', '')

                        buyer_is_player  = buyer_id  in player_station_ids
                        seller_is_player = seller_id in player_station_ids

                        if buyer_is_player or seller_is_player:
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
                                    'buyer_code':      id_to_code.get(buyer_id,  buyer_id)  if buyer_id  else '—',
                                    'seller_code':     id_to_code.get(seller_id, seller_id) if seller_id else '—',
                                    'ware':            ware_id,
                                    'ware_name':       ware_name,
                                    'amount':          amount,
                                    'price_cr':        price_cr,
                                    'total_cr':        amount * price_cr,
                                    'time_ago_s':      max(0.0, game_time - entry_time),
                                    'player_is_buyer':  buyer_is_player,
                                    'player_is_seller': seller_is_player,
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

                    # ── Economylog section close (Pass 6) ─────────────────────
                    if tag == 'entries' and in_trade_entries:
                        in_trade_entries = False

                    elem.clear()

    except ET.XMLSyntaxError as e:
        print(f"\n[XML Error] Save file has a formatting issue: {e}")
        raise

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
    bought       = sum(1 for t in history_trades if t['player_is_buyer'])
    sold         = sum(1 for t in history_trades if t['player_is_seller'])
    print(
        f"[Scanning] Active trades  — {len(active_trades)} order(s) "
        f"({station_hits} via station filter, {ship_hits} via ship filter)."
    )
    print(
        f"[Scanning] Trade history  — {len(history_trades)} completed trade(s) "
        f"({bought} purchases, {sold} sales)."
    )

    return {
        "trades":        active_trades,
        "trade_history": history_trades,
    }
