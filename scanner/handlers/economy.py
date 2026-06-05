"""
v2/scanner/handlers/economy.py

EconomyHandler — harvests completed trades from the save's economy log.

DESIGN: pure collection, no classification.
--------------------------------------------------------------------------
The economy log is a single global block near the END of the save:

    <entries type="trade">
      <log time="240649.049" type="trade" ware="antimattercells"
           buyer="[0xc519]" seller="[0x1f3d4]" price="13419" v="135" .../>
      ...
    </entries>

Attribute meanings (verified against save_001.xml):
  buyer / seller  object id of the party whose storage the goods moved into / out
                  of. NOTE: this is the *immediate transacting party* — when a
                  ship hauls the goods, the SHIP is recorded here, not the
                  destination station. Resolving the real counterparty is the
                  post-processor's job.
  ware            ware id, e.g. "antimattercells"
  price           price per unit in CENTS — divide by 100 for credits
  v               volume (units traded)
  time            in-game clock (seconds) when the trade completed
  b/bmax/s/smax   buyer's & seller's stock levels after the trade (unused here)

Ids appear in two formats — bracketed hex "[0x...]" and plain decimal "853" —
so every id is run through norm_id() before storage.

WHY WE DON'T CLASSIFY HERE
A trade row references ships and stations by id. Whether an id is a player ship,
player station, NPC station, or NPC ship can only be decided against the fully
populated id indexes — and a player ship may be parsed AFTER this log block
(e.g. one docked at the HQ near the end of the file). So we harvest raw rows now
and let the post-processor classify + resolve once the whole save is parsed.
"""
from __future__ import annotations
from ..xml_utils import norm_id


class EconomyHandler:
    """
    Collects raw completed-trade rows and despawned-object labels.

    Populates two fields on the ScanContext:
      ctx.trade_log     — list of raw trade-row dicts (see module docstring)
      ctx.removed_codes — normalised id → "Name [CODE]" for despawned objects
    """

    def __init__(self) -> None:
        # True while iterparse is inside an <economylog><removed> block.
        # Guards on_object so we only collect ids that are genuinely despawned
        # economy objects, not the many other <object> elements in the save
        # (job pools, missions, etc.).
        self._in_removed: bool = False

    # ── Trade rows ────────────────────────────────────────────────────────────

    def on_log(self, elem, ctx) -> None:
        """
        Harvest one <log type="trade"> row into ctx.trade_log.

        Ignores non-trade logs in the same section (type="buyoffer" /
        "selloffer" carry an 'owner' attribute and no buyer/seller pair).
        """
        if elem.get('type') != 'trade':
            return

        buyer  = elem.get('buyer')
        seller = elem.get('seller')
        # Real completed trades always have at least one of buyer/seller.
        # Offer rows (buyoffer/selloffer) have neither — skip them.
        if buyer is None and seller is None:
            return

        # Volume — skip zero/garbage rows (matches v1's amount > 0 guard).
        try:
            amount = int(float(elem.get('v', 0)))
        except (ValueError, TypeError):
            return
        if amount <= 0:
            return

        # Price is stored in cents; convert to credits.
        try:
            price_cr = float(elem.get('price', 0)) / 100.0
        except (ValueError, TypeError):
            price_cr = 0.0

        # Trade timestamp; fall back to current game time if absent.
        try:
            t = float(elem.get('time', ctx.game_time_s))
        except (ValueError, TypeError):
            t = ctx.game_time_s

        ctx.trade_log.append({
            'buyer':       norm_id(buyer  or ''),
            'seller':      norm_id(seller or ''),
            'ware':        elem.get('ware', ''),
            'amount':      amount,
            'price_cr':    price_cr,
            'total_cr':    amount * price_cr,
            'game_time_s': t,
            # Seconds before save time; always >= 0. 0 = just happened.
            'time_ago_s':  max(0.0, ctx.game_time_s - t),
        })

    # ── Removed (despawned) objects ───────────────────────────────────────────

    def on_removed_start(self, elem, ctx) -> None:
        """Enter a <removed> block — start accepting <object> labels."""
        self._in_removed = True

    def on_removed_end(self, elem, ctx) -> None:
        """Leave a <removed> block."""
        self._in_removed = False

    def on_object(self, elem, ctx) -> None:
        """
        Record a despawned object's display label, keyed by its normalised id.

        Only plain-decimal ids belong to removed economy objects; bracketed-hex
        <object> ids inside other <removed> sections are a different concept and
        are deliberately skipped. The label is "Name [CODE]" (or just "Name").
        """
        if not self._in_removed:
            return

        raw_id = elem.get('id', '')
        if not raw_id or raw_id.startswith('['):
            return

        name = elem.get('name', '')
        if not name:
            return

        code = elem.get('code', '')
        label = f'{name} [{code}]' if code else name
        ctx.removed_codes[norm_id(raw_id)] = label
