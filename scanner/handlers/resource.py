from __future__ import annotations
from ..entities import SectorResource


class ResourceHandler:
    """
    Accumulates per-sector mineable resources from <resourceareas> subtrees.

    Sectors are STREAMED, not buffered (buffering a sector would hold every
    nested zone/station/ship in memory). But <resourceareas> is the sector's
    first child — it streams past before any buffered component opens — so we
    run a tiny state machine over its child elements instead of a tree walk.

    Save shape (verified against save_001):

        <component class="sector" macro="cluster_43_sector001_macro" ...>
          <resourceareas>                    ← activate, bind to this sector
            <area x=".." y=".." z="..">
              <wares>                          ← section = wares (capacity)
                <ware ware="ore">
                  <recharge max="7805" time="108000"/>
              <yields>                         ← section = yields (abundance)
                <ware ware="ore">
                  <yield name="low"/>

    Aggregation is per ware across every <area> in the sector: recharge max is
    summed, the highest yield level wins. All needed values sit on the OPENING
    tag, so reading on the 'start' event is safe even though the Scanner clears
    each element on its 'end' event.
    """

    # Abundance order, lowest → highest (full ladder seen in save_001, e.g.
    # medlow/medplus exist between low and high). Unknown levels rank below
    # everything known (-1) so a recognised level always beats an unknown one.
    YIELD_RANK = {
        'verylow': 0, 'low': 1, 'lowplus': 2, 'medlow': 3, 'medium': 4,
        'medplus': 5, 'medhigh': 6, 'high': 7, 'veryhigh': 8,
    }

    def __init__(self) -> None:
        self.active = False          # True only inside a sector's <resourceareas>
        self._sector = ''            # macro of the sector we're accumulating for
        self._section: str | None = None   # 'wares' | 'yields' | None
        self._ware = ''              # ware id of the <ware> currently open
        self._acc: dict[str, dict] = {}     # ware → {max, time, yield}

    def on_start(self, tag, elem, ctx) -> None:
        if tag == 'resourceareas':
            # Bind to the enclosing sector component. ctx.top is that <component>
            # because <resourceareas> itself is not a component (never pushed).
            frame = ctx.top
            if frame is not None and frame.cls == 'sector' and frame.macro:
                self.active = True
                self._sector = frame.macro
                self._section = None
                self._ware = ''
                self._acc = {}
            return

        if not self.active:
            return

        if tag == 'wares':
            self._section = 'wares'
        elif tag == 'yields':
            self._section = 'yields'
        elif tag == 'ware':
            self._ware = elem.get('ware', '')
        elif tag == 'recharge' and self._section == 'wares' and self._ware:
            rec = self._acc.setdefault(self._ware, {'max': 0, 'time': 0, 'yield': None})
            try:
                rec['max'] += int(elem.get('max', 0))
            except (ValueError, TypeError):
                pass
            try:
                rec['time'] = max(rec['time'], int(elem.get('time', 0)))
            except (ValueError, TypeError):
                pass
        elif tag == 'yield' and self._section == 'yields' and self._ware:
            name = elem.get('name', '')
            rec = self._acc.setdefault(self._ware, {'max': 0, 'time': 0, 'yield': None})
            cur = rec['yield']
            if cur is None or self.YIELD_RANK.get(name, -1) > self.YIELD_RANK.get(cur, -1):
                rec['yield'] = name

    def on_end(self, tag, elem, ctx) -> None:
        if not self.active:
            return

        if tag == 'ware':
            self._ware = ''
        elif tag in ('wares', 'yields'):
            self._section = None
        elif tag == 'resourceareas':
            # Flush one row per ware, then reset for the next sector.
            for ware, rec in self._acc.items():
                ctx.sector_resources.append(SectorResource(
                    sector_macro  = self._sector,
                    ware          = ware,
                    yield_level   = rec['yield'] or '',
                    recharge_max  = rec['max'],
                    recharge_time = rec['time'],
                ))
            self.active = False
            self._sector = ''
            self._section = None
            self._ware = ''
            self._acc = {}
