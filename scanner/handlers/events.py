# Core role: Harvests the player's notification/event log and career stats from the savegame.

from __future__ import annotations
import dataclasses
import re

from scanner.language import resolve_text_ref
from scanner.entities import PlayerEvent

# Embedded {page,id} language refs inside a longer title/text string.
# resolve_text_ref() only handles a bare whole-string ref (the faction= case);
# event prose mixes refs into sentences ("… under attack by {20203,101}.").
_EMBEDDED_REF_RE = re.compile(r'\{(\d+),(\d+)\}')

# The game writes line breaks inside event prose as a literal "[\012]" token
# (octal 012 = LF) instead of a real newline — e.g. reputation events read
# "Reason: Trade Completed[\012]Current reputation: 21". Decoded here, once,
# so the DB/JSON carry real newlines and no consumer needs to know the escape.
_NEWLINE_ESCAPE = '[\\012]'

# Low-signal notification rows the player never needs to review after the fact:
# travel-mode / autopilot toggles, the "you have entered space protected by X"
# police notice, and individual crew-assignment confirmations. These fire
# constantly during normal play and bury the events that actually matter
# (attacks, losses, war news), so they're dropped at harvest — they never reach
# the DB, the exported JSON, or the advisor that reads it. Matched leniently
# (case-insensitive substring against title + text) so a small wording change
# between game versions can't silently let them back in; to hide another
# notification type, add its distinctive phrase to this tuple.
_NOISE_SUBSTRINGS = (
    'travel mode',
    'autopilot',
    'protected by',            # "You have entered space protected by <faction>."
    'assigned individual',     # "Assigned Individual <name> to <ship>."
)


def _is_noise(title: str, text: str) -> bool:
    """True when this row is one of the recurring low-signal notifications."""
    haystack = f'{title}\n{text}'.lower()
    return any(phrase in haystack for phrase in _NOISE_SUBSTRINGS)


def _richness(e: PlayerEvent) -> tuple:
    """Orders a double-logged pair: the categorised/attributed row wins."""
    return (e.category != 'uncategorised', bool(e.faction_name),
            e.component_id is not None)


def _texts_match(a: str, b: str) -> bool:
    """True when the texts are equal, or one is the other minus leading
    line(s) — the bare reputation twin carries an extra "Faction: X" first
    line that its faction=-attributed twin drops."""
    if a == b:
        return True
    longer, shorter = (a, b) if len(a) > len(b) else (b, a)
    return bool(shorter) and longer.endswith('\n' + shorter)


def dedupe_events(events: list[PlayerEvent]) -> list[PlayerEvent]:
    """Collapses event rows the game logs twice (observed in 7.x saves).

    Many events land in the log as two rows at the exact same timestamp: a
    bare one (no category/faction/component) plus a richer twin — e.g. pirate
    sightings get a categorised 'alerts' copy carrying component=, reputation
    changes get a copy carrying faction= without the "Faction: X" text line.
    Rows merge when time and title match and the texts match per
    _texts_match(); the richer row wins, and any field it lacks is filled
    from the discarded twin. Order of the kept rows is preserved.
    """
    kept_by_key: dict[tuple, list[int]] = {}
    out: list[PlayerEvent | None] = list(events)
    for i, ev in enumerate(events):
        key = (ev.game_time_s, ev.title)
        for j in kept_by_key.get(key, ()):
            kept = out[j]
            if kept is not None and _texts_match(kept.text, ev.text):
                w, l = (kept, ev) if _richness(kept) >= _richness(ev) else (ev, kept)
                out[j] = dataclasses.replace(
                    w,
                    faction_name = w.faction_name or l.faction_name,
                    component_id = w.component_id or l.component_id)
                out[i] = None
                break
        else:
            kept_by_key.setdefault(key, []).append(i)
    return [e for e in out if e is not None]


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

    def _clean(self, s: str) -> str:
        """Full title/text cleanup: resolve refs, then decode newline escapes.

        Escape decoding runs AFTER ref resolution because the escape can live
        inside the resolved t-file text too, not just the save attribute.
        """
        return self._resolve_embedded(s).replace(_NEWLINE_ESCAPE, '\n')

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
        # Clean before the noise check: the escape/ref decoding happens on the
        # same strings we match against, so a phrase split by a language ref
        # still gets recognised.
        title = self._clean(title)
        text  = self._clean(text)
        if _is_noise(title, text):
            return
        faction_ref = elem.get('faction') or ''
        ctx.player_events.append(PlayerEvent(
            scan_id      = ctx.scan_id,
            category     = elem.get('category') or 'uncategorised',
            title        = title,
            text         = text,
            faction_name = resolve_text_ref(faction_ref, self._texts) if faction_ref else '',
            component_id = elem.get('component') or None,
            game_time_s  = t,
            time_ago_s   = ctx.game_time_s - t,
        ))
