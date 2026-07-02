# Core role: Harvests the player's notification/event log and career stats from the savegame.

from __future__ import annotations
import re

from scanner.language import resolve_text_ref
from scanner.entities import PlayerEvent

# Embedded {page,id} language refs inside a longer title/text string.
# resolve_text_ref() only handles a bare whole-string ref (the faction= case);
# event prose mixes refs into sentences ("… under attack by {20203,101}.").
_EMBEDDED_REF_RE = re.compile(r'\{(\d+),(\d+)\}')


class EventLogHandler:
    """Captures the two player-history blocks the rest of the scanner ignores.

    1. Career stats — every numeric <stat id= value=> pair (first occurrence
       wins), not just the ships_destroyed counter CombatHandler keeps, so
       ranks and scores can be trended across scans.

    2. The player event log — the <log> of <entry> rows directly after
       </stats> (structure notes: docs/save-format.md). Like CombatHandler,
       rows are matched on content instead of tracking the enclosing element:
       a real event has a time= plus a title= or text=. The tag's other user —
       station construction sequences (<entry index= macro=>) — has neither,
       and lives inside buffered subtrees the dispatcher skips anyway.

    Language refs resolve against the pages the Scanner pre-loads (page 20203
    faction names, etc.). Refs to pages we don't load stay as literal
    {page,id} braces — partial text beats dropping the event.
    """

    def __init__(self, texts: dict) -> None:
        self._texts = texts

    def _resolve_embedded(self, s: str) -> str:
        if '{' not in s:
            return s
        return _EMBEDDED_REF_RE.sub(
            lambda m: self._texts.get(f'{m.group(1)}:{m.group(2)}', m.group(0)), s)

    def on_stat(self, elem, ctx) -> None:
        """Record one career stat (first occurrence wins; numeric values only)."""
        sid = elem.get('id') or ''
        if not sid or sid in ctx.player_stats:
            return
        try:
            num = float(elem.get('value'))
        except (TypeError, ValueError):
            return
        ctx.player_stats[sid] = int(num) if num.is_integer() else num

    def on_entry(self, elem, ctx) -> None:
        """Record one event-log row; non-event <entry> shapes no-op cheaply."""
        title = elem.get('title') or ''
        text  = elem.get('text') or ''
        if not (title or text):
            return
        try:
            t = float(elem.get('time'))
        except (TypeError, ValueError):
            return
        faction_ref = elem.get('faction') or ''
        ctx.player_events.append(PlayerEvent(
            scan_id      = ctx.scan_id,
            category     = elem.get('category') or 'uncategorised',
            title        = self._resolve_embedded(title),
            text         = self._resolve_embedded(text),
            faction_name = resolve_text_ref(faction_ref, self._texts) if faction_ref else '',
            component_id = elem.get('component') or None,
            game_time_s  = t,
            time_ago_s   = ctx.game_time_s - t,
        ))
