# Core role: Extracts NPC stations from save, including faction affiliation and trade resources.

from __future__ import annotations
import re
from data.factions import FACTION_NAMES, PERMANENTLY_HOSTILE
from data.wares import WARE_NAMES
from ..entities import NpcStation, NpcStationWare
from ..language import (
    resolve_text_ref,
    resolve_station_type,
    resolve_station_macro_name,
    nameindex_to_roman,
)


# Faction short codes derived from the bracket notation in FACTION_NAMES.
# e.g. "argon" → "ARG", "teladi" → "TEL", "paranid" → "PAR"
# Used to prefix the station display name the same way the game UI does.
_FACTION_SHORT_RE = re.compile(r'\[(\w+)\]')
_FACTION_SHORT: dict[str, str] = {
    fid: m.group(1)
    for fid, display in FACTION_NAMES.items()
    if (m := _FACTION_SHORT_RE.match(display))
}


def parse_trade_offers(trade_elem) -> list[NpcStationWare]:
    """Walk the individual <trade ware="..."> offer rows under a <trade> element.

    This is the "Format B" offer shape, shared by god-production NPC stations
    and player stations (player stations additionally keep <reservation> rows
    under the same <trade> element — those are a different tag, so this walk
    never touches them):

        <trade>
          <offers><production>
            <trade ware="advancedelectronics" seller="[own id]" amount="810" price="..."/>
            <trade ware="energycells" buyer="[own id]" amount="2607" desired="2607" price="..." flags="...|shady"/>
          </production></offers>
        </trade>

    buyer=/seller= holds the station's own component id — its PRESENCE (not its
    value) is what marks the direction of that trade offer. desired= appears on
    buy offers only (the total order size); the unmet demand a buyer still wants
    is amount=, not desired-amount= (see advisors.npc_demand_by_ware).

    One station commonly posts the same ware in TWO offers at once — a buy and a
    sell (any trading station quotes a spread) — with different prices and
    quantities on each. Rows still merge by ware_id (so the UI shows one line
    with both direction arrows), but the buy and sell figures land in their own
    price/amount slots. Folding them into one shared slot lost whichever offer
    parsed last, corrupting the demand and arbitrage numbers keyed off it.
    """
    by_ware: dict[str, NpcStationWare] = {}
    for t in trade_elem.findall('.//trade'):
        ware_id = t.get('ware', '')
        if not ware_id:
            continue
        w = by_ware.setdefault(ware_id, NpcStationWare(ware_id=ware_id))
        price  = t.get('price')
        amount = t.get('amount')
        # Direction routes each figure to its own slot, so a buy and a sell for
        # the same ware never overwrite one another.
        if t.get('buyer'):
            w.is_buying = True
            if price:  w.buy_price  = int(price)
            if amount: w.buy_amount = int(amount)
            if (desired := t.get('desired')):
                w.desired = int(desired)
        if t.get('seller'):
            w.is_selling = True
            if price:  w.sell_price  = int(price)
            if amount: w.sell_amount = int(amount)
        if 'shady' in (t.get('flags') or ''):
            w.illegal = True
    return sorted(by_ware.values(), key=lambda w: w.ware_id)


class NpcStationHandler:
    """
    Extracts NPC-owned station data from buffered station subtrees.

    Called twice per station:
      on_start() — when the <component class="station|factory|..."> opening
                   tag is seen. Captures top-level attributes and sector macro
                   from the component stack.
      on_end()   — when that component closes. The full subtree is still in
                   memory; the handler walks it to extract production module
                   macros (for type resolution) and the wares attribute.

    Name resolution uses three paths in priority order:
      A. basename / name attribute → resolved via language file (most stations).
      B. Production module macros  → resolved to factory type category.
      C. Station macro string      → last-resort regex fallback.

    All NPC stations are captured regardless of sector, so the npc_station_index
    covers the full galaxy for counterparty resolution during post-processing.
    """

    def __init__(self, texts: dict) -> None:
        # Language texts for pages 20102 (station name refs) and 20215
        # (factory category names). Loaded once by Scanner at startup.
        self._texts = texts

        # State for the station currently being buffered. Cleared in on_end.
        self._object_id:    str = ''
        self._code:         str = ''
        self._macro:        str = ''
        self._owner_id:     str = ''
        self._raw_name:     str = ''   # resolved from basename/name attribute
        self._nameindex:    str = '0'
        self._sector_macro: str = ''

    # ── Dispatcher entry points ───────────────────────────────────────────────

    def on_start(self, elem, ctx) -> None:
        """
        Capture attributes from the station component's opening tag.

        Sector macro is read from the component stack here (before buffering
        adds nested children) — ctx.frame_at(1) is the sector component that
        directly contains this station.
        """
        self._object_id = elem.get('id',    '')
        self._code      = elem.get('code',  '')
        self._macro     = elem.get('macro', '')
        self._owner_id  = elem.get('owner', '')
        self._nameindex = elem.get('nameindex', '0')

        # Some stations use a text ref like {20102,1301}; resolve it now.
        # Others have a plain string; resolve_text_ref() returns it unchanged.
        raw            = elem.get('name', '') or elem.get('basename', '')
        self._raw_name = resolve_text_ref(raw, self._texts)

        # Read the running sector macro from context rather than walking the
        # component stack — stack depth between sector and station varies.
        self._sector_macro = ctx.current_sector_macro

    def on_end(self, elem, ctx) -> None:
        """
        Finalise the NpcStation once the full subtree is in memory.

        Walks the subtree for production module macros, finds the <trade wares>
        attribute, resolves the display name and type, then appends to both
        ctx.npc_stations and ctx.npc_station_index.
        """
        if not self._object_id:
            return

        # ── Single subtree walk: production macros + dockingbay index ────────
        # Collect production module macros for type resolution AND register
        # every child component id → this station for aidirector dest resolution.
        prod_macros: list[str] = []
        station_id = self._object_id
        for c in elem.iter('component'):
            if c is elem:
                continue
            cid = c.get('id', '')
            if cid:
                ctx.dockingbay_index[cid] = station_id
            if c.get('class') == 'production':
                prod_macros.append(c.get('macro', ''))

        # ── Station type (three paths) ────────────────────────────────────────
        type_name = (
            self._raw_name
            or resolve_station_type(prod_macros, self._texts)
            or resolve_station_macro_name(self._macro)
        )

        # ── Display name ──────────────────────────────────────────────────────
        # Format matches X4's in-game UI:
        #   "{FactionAbbr} {TypeName} {RomanNumeral} ({StationCode})"
        #   e.g. "TEL Advanced Electronics Factory I (CYS-158)"
        parts = []
        short = _FACTION_SHORT.get(self._owner_id.lower(), '')
        if short:
            parts.append(short)
        if type_name:
            parts.append(type_name)
        roman = nameindex_to_roman(self._nameindex)
        if roman:
            parts.append(roman)
        display_name = ' '.join(parts)
        if self._code:
            display_name += f' ({self._code})'

        # ── Wares ─────────────────────────────────────────────────────────────
        # Two formats exist in the save file:
        #
        # Format A — summary attribute (pirate bases, some station types):
        #   <trade wares="majadust spacefuel spaceweed">
        #   No buy/sell direction is given at all — these are undirected.
        #
        # Format B — individual offer rows (god-production stations, and the
        #   same shape player stations use): see parse_trade_offers().
        #
        # We try Format A first; if wares is empty, walk the individual
        # <trade ware="..."> elements inside the offers.
        #
        # Permanently-hostile factions (Xenon, Kha'ak) are skipped here: they
        # can never be traded with, and every advisor consumer of
        # npc_station_wares already drops them via a reputation gate, so parsing
        # and storing their offers is dead work. The station record itself is
        # still built below, so these stations stay on the universe map.
        trade_elem = elem.find('trade')
        wares: list[NpcStationWare] = []

        if trade_elem is not None and self._owner_id.lower() not in PERMANENTLY_HOSTILE:
            wares_str = trade_elem.get('wares', '')
            if wares_str:
                # Format A — direction unknown, so leave is_buying/is_selling False
                wares = [NpcStationWare(ware_id=w) for w in wares_str.split()]
            else:
                wares = parse_trade_offers(trade_elem)

        # ── Build and register ────────────────────────────────────────────────
        station = NpcStation(
            scan_id      = ctx.scan_id,
            object_id    = self._object_id,
            code         = self._code,
            name         = display_name,
            macro        = self._macro,
            station_type = type_name,
            sector_macro = self._sector_macro,
            owner_id     = self._owner_id,
            owner_name   = FACTION_NAMES.get(self._owner_id, self._owner_id.title()),
            wares        = wares,
        )

        ctx.npc_stations.append(station)

        # Index by object_id for O(1) counterparty resolution in post-processing.
        # All NPC stations are indexed regardless of sector — trades can happen
        # with any faction's station anywhere in the galaxy.
        ctx.npc_station_index[self._object_id] = station

        self._object_id = ''
