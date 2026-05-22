import pathlib
from lxml import etree as ET

from data.wares import WARE_NAMES
from scanner.language import open_save

# ─────────────────────────────────────────────────────────────────────────────
#  ACTIVE TRADE ORDER SCANNER  (TradePerform pass)
# ─────────────────────────────────────────────────────────────────────────────
#
#  X4 8.0 save files do not contain a global completed-trade history
#  (the economylog section is per-station and empty). The best available
#  real-time trade data is the set of active TradePerform orders — each one
#  is a contracted deal currently being executed by a ship in transit.
#
#  Structure in the save:
#    <component id="[0xN]" class="ship_*" code="ABC-123">
#      <orders>
#        <order order="TradePerform">
#          <trade buyer="[0xN]" seller="[0xN]" ware="X" price="Y" amount="Z"/>
#        </order>
#      </orders>
#    </component>
#
#  We keep two filter sets:
#    player_station_ids — trades where a player station is buyer or seller
#    player_ship_ids    — trades where a player ship is the transport
#                         (lets us see our ships running NPC-to-NPC routes)
#
#  A ship-stack tracks which ship component we're currently inside so the
#  transporting ship's ID and code are available when we hit a <trade> element.
#  The stack correctly handles docked ships nested inside carriers.
#
#  Price in TradePerform orders is already in Cr (not the x100 cents encoding
#  used by the older economylog format).


def scan_trade_orders(
    file_path: pathlib.Path,
    player_station_ids: set,
    id_to_code: dict,
    player_ship_ids: set | None = None,
) -> list[dict]:
    """
    Streams the save file and returns all active TradePerform orders where a
    player-owned station is the buyer or seller, or a player-owned ship is the
    executing transport.

    Args:
        file_path:          Path to the .xml or .xml.gz save file.
        player_station_ids: Set of hex object IDs for player-owned stations.
                            Trades where neither station is player-owned are
                            still included if the transport ship is.
        id_to_code:         Hex object ID → display code for stations (player
                            and NPC). Unresolved IDs are shown as raw hex.
        player_ship_ids:    Optional set of hex object IDs for player-owned
                            ships. When provided, trades where a player ship is
                            the transport are included even if neither station
                            is player-owned.

    Returns:
        List of active trade record dicts. Each dict includes:
          ship_id / ship_code  — the transport ship executing the order
          player_is_ship       — True when captured only via the ship filter
                                 (neither station is player-owned)
    """
    _ship_ids = player_ship_ids or set()

    if not player_station_ids and not _ship_ids:
        return []

    result:          list[dict]        = []
    in_trade_order:  bool              = False   # True while inside <order order="TradePerform">
    order_depth:     int               = 0       # nesting depth inside the current trade order

    # Stack of (object_id, code) for each open ship component.
    # We push on the component's start event and pop on its end event.
    # This keeps track of which ship we're currently inside, even when
    # ship components are nested (e.g. a ship docked inside a carrier
    # pushes a second entry; popping it restores the carrier context).
    ship_stack: list[tuple[str, str]] = []

    print(f"[Scanning] Active trades — scanning TradePerform orders "
          f"({len(player_station_ids)} player station(s), "
          f"{len(_ship_ids)} player ship(s) as filter)...")

    try:
        with open_save(file_path) as f:
            context = ET.iterparse(f, events=('start', 'end'))

            for event, elem in context:
                tag = elem.tag

                if event == 'start':

                    # ── Ship component tracking ───────────────────────────────
                    # Maintain the stack so we always know which ship context
                    # a TradePerform order belongs to, without needing to buffer
                    # the whole ship subtree.
                    if tag == 'component':
                        cls = elem.get('class', '')
                        if cls.startswith('ship_'):
                            ship_stack.append((
                                elem.get('id',   ''),
                                elem.get('code', ''),
                            ))

                    # ── TradePerform detection ────────────────────────────────
                    if not in_trade_order:
                        if tag == 'order' and elem.get('order') == 'TradePerform':
                            in_trade_order = True
                            order_depth    = 1
                    else:
                        order_depth += 1

                        # The <trade> element is the direct child of <order>.
                        # Its attributes are available on the start event so we
                        # read them immediately without buffering the subtree.
                        if tag == 'trade' and order_depth == 2:
                            buyer_id  = elem.get('buyer',  '')
                            seller_id = elem.get('seller', '')

                            # Identify which player entity this trade touches.
                            current_ship_id   = ship_stack[-1][0] if ship_stack else ''
                            current_ship_code = ship_stack[-1][1] if ship_stack else ''

                            buyer_is_player  = buyer_id  in player_station_ids
                            seller_is_player = seller_id in player_station_ids
                            ship_is_player   = bool(_ship_ids) and current_ship_id in _ship_ids

                            # Skip trades that don't involve any player entity.
                            if not buyer_is_player and not seller_is_player and not ship_is_player:
                                continue

                            try:
                                amount   = int(float(elem.get('amount', 0)))
                                price_cr = float(elem.get('price', 0))   # already in Cr
                            except (ValueError, TypeError):
                                continue

                            ware_id   = elem.get('ware', '')
                            ware_name = WARE_NAMES.get(ware_id, ware_id.replace('_', ' ').title())

                            result.append({
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
                                # True only when the trade was captured because a player
                                # ship is the transport and no player station is involved.
                                # False when a player station is buyer/seller — the station
                                # display already handles those; the ship is just context.
                                'player_is_ship': ship_is_player and not buyer_is_player and not seller_is_player,
                            })

                elif event == 'end':

                    # ── Ship component tracking ───────────────────────────────
                    # Pop before clearing — lxml still has elem's attributes
                    # available at this point; elem.clear() below would wipe them.
                    if tag == 'component':
                        cls = elem.get('class', '')
                        if cls.startswith('ship_') and ship_stack:
                            ship_stack.pop()

                    if in_trade_order:
                        order_depth -= 1
                        if order_depth == 0:
                            in_trade_order = False

                    elem.clear()

    except ET.XMLSyntaxError as e:
        print(f"\n[XML Error] Save file has a formatting issue: {e}")
        raise

    # Sort station trades by player station code then ware; ship trades by ship code then ware.
    result.sort(key=lambda t: (
        t['buyer_code']  if t['player_is_buyer']  else '',
        t['seller_code'] if t['player_is_seller'] else '',
        t.get('ship_code', '') if t.get('player_is_ship') else '',
        t['ware_name'],
    ))

    station_hits = sum(1 for t in result if not t['player_is_ship'])
    ship_hits    = sum(1 for t in result if t['player_is_ship'])
    print(f"[Scanning] Active trades — found {len(result)} order(s) "
          f"({station_hits} via station filter, {ship_hits} via ship filter).")
    return result
