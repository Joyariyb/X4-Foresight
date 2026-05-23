import pathlib
from lxml import etree as ET

from data.wares import WARE_NAMES
from scanner.language import open_save

# ─────────────────────────────────────────────────────────────────────────────
#  COMPLETED TRADE HISTORY SCANNER  (economylog pass)
# ─────────────────────────────────────────────────────────────────────────────
#
#  X4 saves record completed trade transactions in <entries type="trade"> blocks.
#  These appear either globally (after the universe section) or nested inside
#  individual station components — this scanner captures both.
#
#  Each completed trade is a <log> element:
#    <log type="trade" seller="[0xN]" buyer="[0xN]" ware="X" price="Y" v="Z" time="T"/>
#
#  Attribute notes:
#    price — stored in cents (integer). Divide by 100 for display Cr.
#            e.g. price="16000" → 160.00 Cr per unit.
#    v     — volume / amount traded (integer units).
#    time  — game clock at transaction time (seconds, float).
#            Subtract from the current game time to get seconds-ago.
#
#  We capture the current game time from <game time="..."> at the top of the
#  save so each entry can be dated relative to "now" in the game timeline.


def scan_trade_history(
    file_path:          pathlib.Path,
    player_station_ids: set,
    id_to_code:         dict,
) -> list[dict]:
    """
    Streams the save file and returns all completed trades where a player-owned
    station was the buyer or seller.

    Args:
        file_path:          Path to the .xml or .xml.gz save file.
        player_station_ids: Set of hex object IDs for player-owned stations.
        id_to_code:         Hex ID → display code for buyer/seller resolution.
                            Unresolved IDs are shown as raw hex.

    Returns:
        List of completed trade dicts. Each dict includes:
          buyer_code / seller_code — resolved display codes
          ware / ware_name         — ware ID and human-readable name
          amount                   — units traded
          price_cr                 — price per unit in Cr (already divided by 100)
          total_cr                 — amount × price_cr
          time_ago_s               — seconds before save time (0 = happened right now,
                                     3600 = happened 1 in-game hour ago)
          player_is_buyer / player_is_seller — which side the player is on
    """
    if not player_station_ids:
        return []

    result:           list[dict] = []
    game_time:        float      = 0.0
    game_time_found:  bool       = False
    in_trade_entries: bool       = False   # True while inside <entries type="trade">

    print(f"[Scanning] Trade history — scanning economylog entries "
          f"({len(player_station_ids)} player station(s) as filter)...")

    try:
        with open_save(file_path) as f:
            context = ET.iterparse(f, events=('start', 'end'))

            for event, elem in context:
                tag = elem.tag

                if event == 'start':

                    # ── Capture current game time ─────────────────────────────
                    # The <game time="..."> element near the top of every save
                    # holds the current in-game clock in seconds. We use it to
                    # compute how long ago each logged trade happened.
                    if tag == 'game' and not game_time_found:
                        try:
                            game_time       = float(elem.get('time', 0))
                            game_time_found = True
                        except (ValueError, TypeError):
                            pass

                    # ── Trade section detection ───────────────────────────────
                    # <entries type="trade"> can appear multiple times — once
                    # globally and once per station that has logged any trades.
                    # We re-enter the flag each time so all sections are captured.
                    elif tag == 'entries' and elem.get('type') == 'trade':
                        in_trade_entries = True

                    # ── Trade log entry ───────────────────────────────────────
                    # Each <log type="trade"> inside an entries block is one
                    # completed transaction. Only process entries where a player
                    # station is buyer or seller — NPC-only trades are skipped.
                    elif in_trade_entries and tag == 'log' and elem.get('type') == 'trade':
                        # Normalise IDs to [0xN] bracketed-hex format.
                        # X4 usually writes "[0x1234]" but occasionally writes
                        # a plain decimal integer — convert those so id_to_code
                        # lookups work consistently.
                        def _norm(raw: str) -> str:
                            if not raw or raw.startswith('['):
                                return raw
                            try:
                                return f'[{hex(int(raw))}]'
                            except ValueError:
                                return raw

                        buyer_id  = _norm(elem.get('buyer',  ''))
                        seller_id = _norm(elem.get('seller', ''))

                        buyer_is_player  = buyer_id  in player_station_ids
                        seller_is_player = seller_id in player_station_ids

                        if not buyer_is_player and not seller_is_player:
                            continue

                        try:
                            amount     = int(float(elem.get('v', 0)))
                            # Price is in cents — divide by 100 for display Cr.
                            price_cr   = float(elem.get('price', 0)) / 100
                            entry_time = float(elem.get('time', game_time))
                        except (ValueError, TypeError):
                            continue

                        if amount <= 0:
                            continue

                        ware_id   = elem.get('ware', '')
                        ware_name = WARE_NAMES.get(ware_id, ware_id.replace('_', ' ').title())

                        result.append({
                            'buyer_id':        buyer_id,
                            'seller_id':       seller_id,
                            'buyer_code':      id_to_code.get(buyer_id,  'NPC Ship') if buyer_id  else '—',
                            'seller_code':     id_to_code.get(seller_id, 'NPC Ship') if seller_id else '—',
                            'ware':            ware_id,
                            'ware_name':       ware_name,
                            'amount':          amount,
                            'price_cr':        price_cr,
                            'total_cr':        amount * price_cr,
                            # Seconds before save time. 0 = just happened,
                            # 3600 = 1 in-game hour ago, always >= 0.
                            'time_ago_s':      max(0.0, game_time - entry_time),
                            'player_is_buyer':  buyer_is_player,
                            'player_is_seller': seller_is_player,
                        })

                elif event == 'end':
                    if tag == 'entries' and in_trade_entries:
                        in_trade_entries = False
                    elem.clear()

    except ET.XMLSyntaxError as e:
        print(f"\n[XML Error] Save file has a formatting issue: {e}")
        raise

    bought = sum(1 for t in result if t['player_is_buyer'])
    sold   = sum(1 for t in result if t['player_is_seller'])
    print(f"[Scanning] Trade history — found {len(result)} completed trade(s) "
          f"({bought} purchases, {sold} sales).")
    return result
