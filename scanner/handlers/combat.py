# Core role: Extracts player combat tallies — lifetime ships-destroyed count and
# per-faction enemy-kill credits — from the savegame's <stats> and event <log>.

from __future__ import annotations

from data.factions import FACTION_NAMES, faction_id_from_display
from scanner.language import resolve_text_ref


class CombatHandler:
    """Harvests two combat signals the rest of the scanner ignores.

    1. ``ships_destroyed`` — the player's lifetime kill counter from the savegame
       statistics block (``<stat id="ships_destroyed" value="295"/>``). This is a
       single cumulative number, so the Trends chart can plot it directly.

    2. Per-faction kill credits — the event log records one entry per reputation
       gain, and combat kills carry ``text="Reason: Destroyed Enemy..."`` plus a
       ``faction="{20203,N}"`` language ref naming the faction that *credited* the
       kill (whose enemy you destroyed). We can't know the destroyed ship's TYPE —
       the save doesn't record it — only which faction rewarded each kill, so the
       Trends hover shows a per-faction breakdown, not a ship list.

    Why no <stats>/<log> boundary tracking: the wanted stat ids are unique to the
    player gamestats block and each entry self-identifies via its text, so we match
    on content rather than gating on the enclosing element. First write wins for the
    counter (the player block appears once); kills accumulate across all log entries.

    State lives on the handler instance and is copied onto ScanContext as it arrives,
    so nothing here needs a scan-end hook.
    """

    def __init__(self, texts: dict) -> None:
        # Page 20203 (faction names) text refs, for resolving {20203,N} → display name.
        self._texts = texts

    def on_stat(self, elem, ctx) -> None:
        """Capture the lifetime ships-destroyed counter (first occurrence wins)."""
        if elem.get('id') != 'ships_destroyed':
            return
        if ctx.combat_ships_destroyed is not None:
            return
        try:
            ctx.combat_ships_destroyed = int(elem.get('value') or 0)
        except (ValueError, TypeError):
            ctx.combat_ships_destroyed = 0

    def on_entry(self, elem, ctx) -> None:
        """Tally one enemy-kill credit per "Destroyed Enemy" reputation log entry.

        Gated on the text marker so the thousands of news/mission/tip entries that
        share the <entry> tag are a cheap string-check no-op."""
        text = elem.get('text') or ''
        if 'Destroyed Enemy' not in text:
            return

        # 7.x saves double-log reputation events: an attributed row (faction=)
        # plus a bare twin whose text instead opens with a "Faction: X" line.
        # Skip the bare twin so one kill isn't tallied twice — once correctly
        # and once into the 'Unknown' bucket. (Same save quirk dedupe_events
        # in events.py collapses for the event feed.)
        if text.startswith('Faction:'):
            return

        ref = elem.get('faction') or ''
        name = resolve_text_ref(ref, self._texts) if ref else ''
        fid = faction_id_from_display(name)
        # Key by faction_id when known so the tally joins the reputation table; for
        # minor factions not in FACTION_NAMES, fall back to the raw display name as
        # the key so their kills are still counted rather than dropped.
        key = fid or name or 'unknown'
        bucket = ctx.combat_kills.get(key)
        if bucket is None:
            ctx.combat_kills[key] = {
                'faction_id':   fid,
                'faction_name': FACTION_NAMES.get(fid, name or 'Unknown'),
                'kills':        1,
            }
        else:
            bucket['kills'] += 1
