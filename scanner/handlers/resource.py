from __future__ import annotations
from ..entities import SectorResource


class ResourceHandler:
    """
    Accumulates per-sector mineable resources from <resourceareas> subtrees.

    Sectors are STREAMED, not buffered (buffering a sector would hold every
    nested zone/station/ship in memory). But <resourceareas> is the sector's
    first child — it streams past before any buffered component opens — so we
    run a tiny state machine over its child elements instead of a tree walk.

    Two save layouts are supported:

    9.00+ (current) — resource + yield are encoded on the <area> tag itself:

        <component class="sector" macro="cluster_43_sector001_macro" ...>
          <resourceareas>                    ← activate, bind to this sector
            <area yieldid="sphere_large_ore_high_slow" yield="954823" ...>
              <offset><position .../></offset>
              <fields><field region=".." macro="env_ast_ore_l_01_macro" .../></fields>
            <area yieldid="sphere_small_helium_low_veryslow" yield="6911" ...>

      yieldid is sphere_<size>_<resource>_<yield>_<speed>; we take the resource
      and yield tokens. The `yield` attribute is the field's amount.

    Pre-9.00 (legacy) — resources lived in <wares>/<yields> children:

            <area x=".." y=".." z="..">
              <wares>  <ware ware="ore"><recharge max="7805" time="108000"/> …
              <yields> <ware ware="ore"><yield name="low"/> …

    Either way we aggregate per resource across every <area> in the sector:
    amount summed (recharge_max), highest yield level wins. recharge_time is the
    old refresh interval where present (0 in 9.00, which no longer stores it).
    All values sit on the OPENING tag, so reading on 'start' is safe even though
    the Scanner clears each element on its 'end' event.
    """

    # Abundance order, lowest → highest. 9.00 uses a simple 5-level ladder
    # (verylow/low/medium/high/veryhigh); the extra rare tags here are from the
    # pre-9.00 ladder and kept for back-compat. Ordering of the rare modifiers
    # isn't documented (best-effort guess); it only matters as a tie-break when
    # one resource spans multiple areas. Unknown tags rank below everything (-1).
    YIELD_RANK = {
        'lowest': 0, 'lowminus': 1, 'verylow': 2, 'low': 3, 'lowplus': 4,
        'lowextra': 5, 'medlow': 6, 'medium': 7, 'medplus': 8, 'medhigh': 9,
        'highlow': 10, 'high': 11, 'highplus': 12, 'veryhigh': 13, 'highest': 14,
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

        # 9.00 format: everything is on the <area> tag. yieldid encodes the
        # resource + yield level; `yield` is the amount.
        if tag == 'area' and elem.get('yieldid'):
            parts = elem.get('yieldid', '').split('_')
            # sphere_<size>_<resource>_<yield>_<speed>
            if len(parts) >= 5 and parts[0] == 'sphere':
                ware, level = parts[2], parts[3]
                rec = self._acc.setdefault(ware, {'max': 0, 'time': 0, 'yield': None})
                try:
                    rec['max'] += int(float(elem.get('yield', 0)))
                except (ValueError, TypeError):
                    pass
                self._bump_yield(rec, level)
            return

        # ── Legacy (pre-9.00) <wares>/<yields> layout ──────────────────────────
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
            rec = self._acc.setdefault(self._ware, {'max': 0, 'time': 0, 'yield': None})
            self._bump_yield(rec, elem.get('name', ''))

    def _bump_yield(self, rec: dict, level: str) -> None:
        """Keep the highest-ranked yield level seen for a resource."""
        cur = rec['yield']
        if cur is None or self.YIELD_RANK.get(level, -1) > self.YIELD_RANK.get(cur, -1):
            rec['yield'] = level

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
