from __future__ import annotations
from data.factions import FACTION_NAMES, SKIP_FACTIONS, scale_reputation, reputation_label
from ..entities import ReputationEntry


class ReputationHandler:
    """
    Extracts faction reputation from the player faction's <relations> block.

    XML path:
        <faction id="player">
          <relations>
            <relation faction="argon"    relation="0.0032"/>  ← permanent standing
            <booster  faction="hatikvah" relation="0.005"/>   ← temporary mission bonus
          </relations>
        </faction>

    Raw relation values are small floats on a log10 scale (e.g. 0.0032 ≈ +5
    in-game display). scale_reputation() converts them to the -30..+30 range
    that matches what the game UI shows.

    State lives entirely on this handler instance — reputation collection needs
    no cross-handler data and touches nothing on ScanContext until on_faction_end.
    """

    def __init__(self) -> None:
        # True while iterparse is inside <faction id="player"> ... </faction>
        self._active: bool = False

        # Raw base standing per faction_id — permanent, set by missions/actions
        self._base: dict[str, float] = {}

        # Raw booster per faction_id — temporary bonus, decays over time
        self._boosters: dict[str, float] = {}

    # ── Dispatcher entry points ───────────────────────────────────────────────

    def on_faction_start(self, elem, ctx) -> None:
        """Begin collecting when the player faction block opens."""
        if elem.get('id') == 'player':
            self._active = True
            self._base.clear()
            self._boosters.clear()

    def on_relation(self, elem, ctx) -> None:
        """
        Record one base standing entry.

        Guard on _active is essential — other factions also have <relation>
        elements inside their own blocks. Without the guard, NPC inter-faction
        relations would corrupt the player's reputation data.
        """
        if not self._active:
            return
        fid = elem.get('faction', '')
        if not fid:
            return
        try:
            self._base[fid] = float(elem.get('relation', 0))
        except (ValueError, TypeError):
            self._base[fid] = 0.0

    def on_booster(self, elem, ctx) -> None:
        """
        Record one temporary booster value.

        Boosters represent short-term reputation from completed missions.
        They appear in the game UI as a separate component of the total standing.
        """
        if not self._active:
            return
        fid = elem.get('faction', '')
        if not fid:
            return
        try:
            self._boosters[fid] = float(elem.get('relation', 0))
        except (ValueError, TypeError):
            self._boosters[fid] = 0.0

    def on_faction_end(self, elem, ctx) -> None:
        """
        Build ReputationEntry objects when the player faction block closes.

        By the time this fires, all <relation> and <booster> children have
        already been processed. We scale every raw value and append entries
        to ctx.reputation, sorted highest-first to match the v1 display order.
        """
        if elem.get('id') != 'player' or not self._active:
            return

        self._active = False

        for fid in set(self._base) | set(self._boosters):
            if fid in SKIP_FACTIONS:
                continue

            raw_base    = self._base.get(fid, 0.0)
            raw_booster = self._boosters.get(fid, 0.0)
            raw_total   = raw_base + raw_booster

            # Scale each component independently so the UI can display
            # "base: +12, booster: +3, total: +15" broken down separately.
            scaled_total   = scale_reputation(raw_total)
            scaled_base    = scale_reputation(raw_base)    if raw_base    != 0.0 else 0.0
            scaled_booster = scale_reputation(raw_booster) if raw_booster != 0.0 else 0.0

            ctx.reputation.append(ReputationEntry(
                scan_id      = ctx.scan_id,
                faction_id   = fid,
                faction_name = FACTION_NAMES.get(fid, fid.title()),
                value        = round(scaled_total,   2),
                base         = round(scaled_base,    2),
                booster      = round(scaled_booster, 2),
                tier         = reputation_label(scaled_total),
            ))

        # Highest reputation first — matches v1 sort order and CLI display.
        ctx.reputation.sort(key=lambda r: r.value, reverse=True)
