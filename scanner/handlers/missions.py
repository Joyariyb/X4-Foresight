# Core role: Harvests station bulletin-board mission offers from the savegame's <missions> block.
"""
<missions> sits as a top-level sibling of <md> near the end of the save — NOT
inside any <component>, so it's outside the scanner's component-buffering
logic (same context as <log><entry>). It mixes several offer shapes:

    <offer id="28395" component="[0x3847d]" distance="50000" actor="[0xb0b41]"
           name="Hired Help" description="..." faction="argon" type="repair"
           level="veryeasy" reward="55120">
      <bbs><space component="[0x36644]"/></bbs>
      <briefing>
        <objective step="1" type="repair" text="ARG Weapon Component Factory III data leak"/>
      </briefing>
    </offer>

Verified against a real save by resolving the referenced component ids:
  component=  the STATION the mission is anchored to (class="station").
  actor=      the NPC person you comm for the briefing flavor text
              (class="npc") — deliberately NOT captured here. A mission's
              *station* is what this handler cares about, not the NPC who
              happens to narrate it.
  <bbs><space component=>  sector(s) where the map pin shows — not needed
              since missions are grouped by station directly.

Offers WITHOUT a component= attribute are tutorials (type="tutorial"), the
plot (type="plot"), or multi-stage faction-war campaign threads
(threadtype="sequential", nested <mission> children instead of <objective>,
actor = a faction rep, no single station anchor) — none of these are "a
station's mission", so the handler skips them entirely.
"""
from __future__ import annotations

from data.factions import FACTION_NAMES
from ..entities import StationMission

# The game writes line breaks inside mission prose (description=, rewardtext=)
# as a literal "[\012]" token instead of a real newline — same escape
# EventLogHandler decodes for the player event log. Decoded here too so the
# DB/JSON carry real newlines.
_NEWLINE_ESCAPE = '[\\012]'


class MissionHandler:
    """
    Collects station-anchored mission offers into ctx.station_missions.

    station_code/station_name/sector_macro/sector_name are left blank here and
    resolved at write time (db/write.py) via ctx.npc_station_index — the same
    deferred-resolution pattern _write_npc_ships uses for delivery
    destinations, since cross-handler indexes are only guaranteed complete
    once the whole file has been parsed.
    """

    def __init__(self) -> None:
        self._active: bool = False   # True while inside an <offer> we're keeping
        self._offer: dict | None = None

    def on_offer_start(self, elem, ctx) -> None:
        station_id = elem.get('component') or ''
        if not station_id:
            # Tutorial / plot / faction-war campaign thread — no station anchor.
            self._active = False
            self._offer = None
            return
        self._active = True
        reward = elem.get('reward')
        distance = elem.get('distance')
        faction_id = elem.get('faction') or ''
        self._offer = dict(
            offer_id     = elem.get('id', ''),
            station_id   = station_id,
            name         = elem.get('name', ''),
            description  = _decode(elem.get('description', '')),
            faction_id   = faction_id,
            faction_name = FACTION_NAMES.get(faction_id, faction_id.title()),
            mission_type = elem.get('type', ''),
            level        = elem.get('level', ''),
            reward_cr    = int(reward) if reward else None,
            reward_text  = _decode(elem.get('rewardtext')) if elem.get('rewardtext') else None,
            distance_m   = float(distance) if distance else None,
            objectives   = [],
        )

    def on_objective(self, elem, ctx) -> None:
        """Record one <briefing><objective> step of the current offer, if any."""
        if not self._active or self._offer is None:
            return
        try:
            step = int(elem.get('step'))
        except (TypeError, ValueError):
            step = 0
        self._offer['objectives'].append(
            (step, elem.get('type') or '', elem.get('text') or ''))

    def on_offer_end(self, elem, ctx) -> None:
        """Finalise the current offer (if it had a station anchor) into ctx."""
        if self._active and self._offer is not None:
            ctx.station_missions.append(_build(ctx.scan_id, self._offer))
        self._active = False
        self._offer = None


def _decode(s: str) -> str:
    return s.replace(_NEWLINE_ESCAPE, '\n')


def _build(scan_id: int, o: dict) -> StationMission:
    return StationMission(
        scan_id      = scan_id,
        offer_id     = o['offer_id'],
        station_id   = o['station_id'],
        station_code = '',
        station_name = '',
        sector_macro = '',
        sector_name  = '',
        name         = o['name'],
        description  = o['description'],
        faction_id   = o['faction_id'],
        faction_name = o['faction_name'],
        mission_type = o['mission_type'],
        level        = o['level'],
        reward_cr    = o['reward_cr'],
        reward_text  = o['reward_text'],
        distance_m   = o['distance_m'],
        objectives   = o['objectives'],
    )
