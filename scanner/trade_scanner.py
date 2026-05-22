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
#    <component class="ship_*">
#      <orders>
#        <order order="TradePerform">
#          <trade buyer="[0xN]" seller="[0xN]" ware="X" price="Y" amount="Z"/>
#        </order>
#      </orders>
#    </component>
#
#  We stream all TradePerform orders and keep only those where a player station
#  appears as the buyer or seller. This shows what is currently flowing into
#  and out of the player's stations, regardless of who owns the transport ship.
#
#  Price in TradePerform orders is already in Cr (not the x100 cents encoding
#  used by the older economylog format).


def scan_trade_orders(
    file_path: pathlib.Path,
    player_station_ids: set,
    id_to_code: dict,
) -> list[dict]:
    """
    Streams the save file and returns all active TradePerform orders where a
    player-owned station is the buyer or seller.

    Args:
        file_path:          Path to the .xml or .xml.gz save file.
        player_station_ids: Set of hex object IDs for player-owned stations.
                            Trades that don't touch a player station are skipped.
        id_to_code:         Hex object ID → display code for both sides of a
                            trade (player stations + NPC stations if scanned).

    Returns:
        List of active trade record dicts, sorted by ware name then buyer.
    """
    if not player_station_ids:
        return []

    result:          list[dict] = []
    in_trade_order:  bool       = False   # True while inside <order order="TradePerform">
    order_depth:     int        = 0       # nesting depth inside the current trade order

    print(f"[Scanning] Active trades — scanning TradePerform orders "
          f"({len(player_station_ids)} player station(s) as filter)...")

    try:
        with open_save(file_path) as f:
            context = ET.iterparse(f, events=('start', 'end'))

            for event, elem in context:
                tag = elem.tag

                if event == 'start':
                    if not in_trade_order:
                        # Detect the start of a TradePerform order block.
                        if tag == 'order' and elem.get('order') == 'TradePerform':
                            in_trade_order = True
                            order_depth    = 1
                    else:
                        order_depth += 1

                        # The <trade> element is the direct child of <order> that
                        # carries the deal details. We read it on the start event
                        # (attributes are available immediately) without buffering
                        # the full subtree — this keeps the scan lightweight.
                        if tag == 'trade' and order_depth == 2:
                            buyer_id  = elem.get('buyer',  '')
                            seller_id = elem.get('seller', '')

                            # Skip trades that don't involve a player station.
                            if (buyer_id  not in player_station_ids and
                                    seller_id not in player_station_ids):
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
                                'ware':        ware_id,
                                'ware_name':   ware_name,
                                'amount':      amount,
                                'price_cr':    price_cr,
                                'total_cr':    amount * price_cr,
                                'player_is_buyer':  buyer_id  in player_station_ids,
                                'player_is_seller': seller_id in player_station_ids,
                            })

                elif event == 'end':
                    if in_trade_order:
                        order_depth -= 1
                        if order_depth == 0:
                            in_trade_order = False

                    elem.clear()

    except ET.XMLSyntaxError as e:
        print(f"\n[XML Error] Save file has a formatting issue: {e}")
        raise

    # Sort by player station code (buyer or seller), then ware name for readability.
    result.sort(key=lambda t: (
        t['buyer_code']  if t['player_is_buyer']  else '',
        t['seller_code'] if t['player_is_seller'] else '',
        t['ware_name'],
    ))

    print(f"[Scanning] Active trades — found {len(result)} order(s) touching player stations.")
    return result
