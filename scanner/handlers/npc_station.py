# Core role: Extracts NPC stations from save, including faction affiliation and trade resources.

from __future__ import annotations
import re
from data.factions import FACTION_NAMES
from data.wares import WARE_NAMES
from ..entities import NpcStation
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
        #
        # Format B — god-production stations (no summary attribute):
        #   <trade>
        #     <offers><production>
        #       <trade ware="advancedelectronics" seller="..."/>
        #       <trade ware="energycells"         buyer="..."/>
        #     </production></offers>
        #   </trade>
        #
        # We try Format A first; if wares is empty, collect unique ware IDs
        # from the individual <trade ware="..."> elements inside the offers.
        trade_elem = elem.find('trade')
        wares: list[str] = []

        if trade_elem is not None:
            wares_str = trade_elem.get('wares', '')
            if wares_str:
                # Format A
                wares = wares_str.split()
            else:
                # Format B — deduplicate with a set so each ware appears once
                wares = sorted({
                    t.get('ware', '')
                    for t in trade_elem.findall('.//trade')
                    if t.get('ware')
                })

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
