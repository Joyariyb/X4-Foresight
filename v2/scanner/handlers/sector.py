from __future__ import annotations
from data.factions import FACTION_NAMES
from data.sector_stats import SECTOR_SUNLIGHT
from ..entities import Sector
from ..language import macro_to_sector_name


class SectorHandler:
    """
    Extracts sector ownership and sunlight data from sector component elements.

    XML path:
        <component class="cluster" macro="cluster_43_macro" ...>   ← parent on stack
          <component class="sector" macro="cluster_43_sector001_macro"
                     owner="teladi" id="[0x45d5]" .../>            ← dispatched here

    All required data is on the opening tag's attributes — no buffering needed.
    The parent cluster macro is read from the component stack (ctx.frame_at(1))
    rather than being parsed from the sector macro string, which is more reliable
    and avoids a second regex pass.

    cluster_name resolution is a known gap — the language file lookup ID formula
    for cluster names has not been confirmed. cluster_macro is stored as a usable
    fallback; cluster_name will be wired up once the formula is verified.
    """

    def __init__(self, sector_names: dict) -> None:
        # Pre-loaded {lang_id: sector_name} dict from the language file.
        # Passed in by the Scanner at startup so the file is read only once.
        self._sector_names = sector_names

    def on_sector(self, elem, ctx) -> None:
        """
        Process one sector component start event.

        Skips sectors whose macro doesn't match the standard cluster_XX_sectorYY
        pattern — those are temp zones or other internal entities that aren't
        real navigable sectors.
        """
        sector_macro = elem.get('macro', '')
        owner_id     = elem.get('owner', '')

        if not sector_macro:
            return

        # Resolve human-readable sector name. Falls back to the raw macro if
        # the language file wasn't loaded or this sector isn't in it.
        sector_name = macro_to_sector_name(sector_macro, self._sector_names)
        if not sector_name:
            # Not a standard cluster_XX_sectorYY macro — skip (temp zone, etc.)
            return

        # Cluster frame sits one level up on the component stack.
        # connection="cluster" on the sector element confirms this nesting.
        parent = ctx.frame_at(1)
        cluster_macro = parent.macro if parent else ''

        # TODO: resolve cluster_name from the language file.
        # The ID formula for cluster names (page 20004) has not been confirmed.
        # Storing the macro as a usable fallback until that is verified.
        cluster_name = cluster_macro

        # Sunlight is keyed by human-readable sector name. Default 1.0 is
        # standard output — only deviates for sectors near unusual stars.
        sunlight = SECTOR_SUNLIGHT.get(sector_name, 1.0)

        ctx.sectors.append(Sector(
            scan_id       = ctx.scan_id,
            sector_macro  = sector_macro,
            sector_name   = sector_name,
            cluster_macro = cluster_macro,
            cluster_name  = cluster_name,
            owner_id      = owner_id,
            owner_name    = FACTION_NAMES.get(owner_id, owner_id.title()),
            sunlight      = sunlight,
        ))
