# Core role: Extracts player reputation and inter-faction relations from save.

from __future__ import annotations
from data.factions import FACTION_NAMES, SKIP_FACTIONS, scale_reputation, reputation_label
from ..entities import ReputationEntry, FactionRelationEntry
      - ctx.reputation        — the PLAYER's standings (base + booster split),
                                exactly as before.
      - ctx.faction_relations — every NPC faction's standings toward other
                                factions and the player (base value only;
                                NPC boosters are deliberately ignored).

    XML path (same shape for player and NPC factions — verified against
    save_001.xml.gz, 2026-06-12):
        <faction id="argon">
          <relations locked="0|1">
            <relation faction="antigone" relation="0.67"/>   ← permanent standing
            <booster  faction="player"   relation="0.005"/>  ← temporary (player path only)
          </relations>
        </faction>

    Raw relation values are small floats on a log10 scale (range −1.0..1.0 in
    practice; e.g. 0.0032 ≈ +5 in-game). scale_reputation() converts them to
    the −30..+30 range the game UI shows — identical math for every faction.

    SUBJECT FILTERING — the save holds 132 faction blocks but most are junk:
    101 are visitor/visitor001..100 stubs, others (criminal, smuggler, …) are
    role labels. Only subjects present in FACTION_NAMES are collected, and
    subjects marked active="0" (e.g. trinity in a save where that story isn't
    active) are skipped — no Diplomacy tab for a faction that isn't in play.

    State lives entirely on this handler instance — reputation collection needs
    no cross-handler data and touches nothing on ScanContext until on_faction_end.
    """

    def __init__(self) -> None:
        # True while iterparse is inside <faction id="player"> ... </faction>.
        # MUST keep meaning "player block only": scanner.py gates the player
        # credits <account> capture on self._rep._active.
        self._active: bool = False

        # Subject faction id currently being collected (player or NPC),
        # or None while inside a block we don't care about (visitors etc.).
        self._current: str | None = None

        # True when the current subject's <relations> block carries locked="1"
        # — the game hard-locks these standings (Xenon, Kha'ak).
        self._locked: bool = False

        # Raw base standing per target faction_id — permanent, set by missions/actions
        self._base: dict[str, float] = {}

        # Raw booster per target faction_id — temporary, decays over time.
        # Only collected for the player; NPC boosters exist but are ignored.
        self._boosters: dict[str, float] = {}

    # ── Dispatcher entry points ───────────────────────────────────────────────

    def on_faction_start(self, elem, ctx) -> None:
        """
        Begin collecting when a faction block we care about opens.

        The id must be captured HERE — attributes on non-component elements
        are cleared at their END event, so it's gone by on_faction_end.
        """
        fid = elem.get('id', '')

        if fid == 'player':
            self._active = True
            self._current = fid
        elif fid in FACTION_NAMES and elem.get('active') != '0':
            self._current = fid
        else:
            # visitor stubs, role-label factions, inactive factions — and a
            # defensive reset so a junk block can't inherit collection state.
            self._current = None
            return

        self._locked = False
        self._base.clear()
        self._boosters.clear()

    def on_relations(self, elem, ctx) -> None:
        """Capture the locked="1" flag from the subject's <relations> wrapper."""
        if self._current is not None:
            self._locked = elem.get('locked') == '1'

    def on_relation(self, elem, ctx) -> None:
        """
        Record one base standing entry for the current subject faction.

        Guard on _current is essential — it is None inside the ~100 visitor
        and role-label faction blocks whose <relation> rows we must not collect.
        """
        if self._current is None:
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
        Record one temporary booster value — player block only.

        Boosters represent short-term reputation from completed missions.
        NPC factions also carry boosters in the save, but those are ignored:
        the Diplomacy tabs show NPC base standings only.
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
        Build entries when the current faction block closes.

        By the time this fires, all <relation> and <booster> children have
        already been processed. Player blocks feed ctx.reputation (unchanged
        behaviour); NPC blocks feed ctx.faction_relations.
        """
        # Use handler state only — do not check elem.get('id') here.
        # Attributes on non-component elements are cleared at their END event,
        # which fires before this method; id may no longer be available.
        if self._current is None:
            return

        if self._active:
            self._build_player_reputation(ctx)
            self._active = False
        else:
            self._build_npc_relations(ctx)

        self._current = None

    # ── Entry builders ────────────────────────────────────────────────────────

    def _build_player_reputation(self, ctx) -> None:
        """Player path — identical behaviour to the original handler."""
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

        # Highest reputation first — the order the CLI display expects.
        ctx.reputation.sort(key=lambda r: r.value, reverse=True)

    def _build_npc_relations(self, ctx) -> None:
        """
        NPC path — one FactionRelationEntry per known target faction.

        Targets are whitelisted the same way subjects are: FACTION_NAMES plus
        "player" (the player must appear in each NPC tab — it's the row the
        UI highlights). Xenon/Kha'ak list standings toward all 100 visitor
        stubs; the whitelist collapses that to the ~20 factions that matter.
        """
        subject = self._current
        batch: list[FactionRelationEntry] = []

        for fid, raw in self._base.items():
            if fid != 'player' and fid not in FACTION_NAMES:
                continue
            if fid == subject:
                continue

            scaled = scale_reputation(raw)
            batch.append(FactionRelationEntry(
                scan_id      = ctx.scan_id,
                faction_id   = subject,
                faction_name = FACTION_NAMES.get(subject, subject.title()),
                other_id     = fid,
                other_name   = 'Player' if fid == 'player' else FACTION_NAMES.get(fid, fid.title()),
                value        = round(scaled, 2),
                tier         = reputation_label(scaled),
                locked       = self._locked,
            ))

        # Allies first, biggest enemy last — same order the player table uses,
        # applied per subject so each Diplomacy tab is display-ready.
        batch.sort(key=lambda r: r.value, reverse=True)
        ctx.faction_relations.extend(batch)
