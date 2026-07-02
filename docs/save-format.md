# X4 save-format notes

An append-only journal of what this project has reverse-engineered about the
X4: Foundations save file. This knowledge is expensive to rediscover — when a
new structure gets decoded, write it down here (date it), even if no code uses
it yet. Feature ideas belong in [TODO.md](../TODO.md); this file is only about
what the save *contains* and how it behaves.

## Container

- Saves live in `Documents\Egosoft\X4\{steamid}\save\` as `save_*.xml.gz` /
  `autosave_*.xml.gz`. `scanner/language.py::open_save()` also accepts plain
  `.xml` (used by the dev root save and the test fixture).
- A mature save is tens of millions of XML lines — everything downstream of
  this fact (streaming iterparse, subtree buffering, deferred resolution) is
  in `scanner/scanner.py`'s and `scanner/context.py`'s own comments.

## The `<component>` tree

- Every world object is a `<component>` with `id` (`"[0x4f44]"` hex form),
  `class`, `macro`, and `owner` attributes. `class` drives handler dispatch —
  see `STATION_CLASSES` / `SHIP_CLASSES` in `scanner/context.py`.
- Some references use a *plain decimal* id form instead of the bracketed hex
  form (seen in economy-log rows for despawned objects): `853` ≡ `[0x355]`.
  `scanner/xml_utils.py::norm_id()` normalises both to the bracketed form.
- References often point at a **sub-element** of an object, not the object
  itself: a ship's homebase/commander refs give a *connection* element id on
  the station (e.g. a docking bay), which must be resolved to the station's
  own id (`ctx.dockingbay_index`, built during station buffering).
- Attributes on non-component elements must be read at the element's *start*
  event — the scanner clears elements on end to keep memory flat.

## Trade economy log

- Completed trades: `<entries type="trade">` wrapping `<log>` rows near the
  end of the save. `price` is in **cents** (divide by 100 for credits);
  `v` is unit volume.
- Buyer/seller ids may belong to objects that no longer exist; those are
  declared in an `<economylog><removed>` block as `<object>` labels, which is
  the only place their display names survive.
- Ordering caveat: a player ship can appear in the file *after* the trade log
  that references it, so rows must be collected raw and classified only after
  the full parse (`scanner/trade_postprocess.py`).
- Mid-delivery destinations hide in two places: an active `DockAt` order's
  params on the ship, and the AI director's script vars (`$thisship` /
  `$destination` / `$trading` inside `<aidirector>…<vars>` blocks).

## Sectors, names, and language refs

- Sector display names resolve through the game's language t-file
  (`t/0001-l044.xml`, readable straight out of the `.cat` archives —
  `gamefiles/catalog.py`). Strings elsewhere may embed `{page,id}` refs
  (e.g. `faction="{20203,601}"`) that need the same file.
- Known text pages: 20004 (sector names), 20102 (station basenames),
  20215 (factory categories), 20201 (factory names), 20203 (faction names).
- **A sector whose name can't be resolved is dropped whole**:
  `SectorHandler.on_sector` returns before setting `ctx.current_sector_macro`,
  so its stations/ships/gates never attach to a sector. Without a language
  file there are effectively no sectors (pinned by `tests/`'s
  `TestNoLanguageFile`).
- `knownto="player"` on a sector marks fog-of-war discovery.
- `<resourceareas>` (9.00+ format) nests per-area ware yields; amounts sum
  across areas, best yield wins (`scanner/handlers/resource.py`).

## Player event log + career stats — NOT YET PARSED (researched 2026-06)

The save holds the player's in-game notification/event log AND career stats.
High value as a "recent events" feed (reputation changes, mission updates,
combat alerts, crew assignments, news).

WHERE (`save_001.xml`): a `<log>` element wrapping ~4,000 `<entry>` rows,
immediately AFTER a `<stats>` block, near the trade economy log
(~line 13,112,002 in the reference save). Find again via
`grep -n '<entry .*category='` or locate the `<log>` that directly follows
`</stats>`.

ENTRY SHAPE:

    <entry time="106477.0" category="upkeep"
           title="Assigned Individual … to Osprey Vanguard"
           text="…" faction="{20203,601}" component="[0x205e2]"
           interact="showonmap"/>

- `time` — absolute game_time_s → subtract scan game_time for "ago".
- `category` — news(353) · missions(318) · upkeep(288) · alerts(262) ·
  diplomacy(17) · tips(7) · uncategorised(2786). `alerts` = combat/threat
  warnings (most actionable); `upkeep` = crew/asset assignments;
  `missions`/`diplomacy` = storyline.
- `title`/`text` — human strings, but MAY contain `{page,id}` language refs.
- `component` — links the event to a ship/station object_id, i.e. to entities
  we already scan. (This is what tied a named-crew frigate and a diplomacy
  gift-ship to two "civilian" hulls docked at the HQ.)

PLAYER STATS block just before the `<log>` (cheap, grab too):

    <stats><stat id="trade_score" value="38448"/>
           <stat id="trade_rank" value="16"/>
           <stat id="fight_score" value="715"/>
           <stat id="fight_rank" value="16"/> …</stats>

(The scanner already reads one stat — `ships_destroyed` — via
`CombatHandler.on_stat`; the rest stream past unparsed.)

## Reputation

- Player standings live in `<faction>` blocks: `<relations>` wraps base
  `<relation>` entries plus temporary `<booster>` bonuses (mission rewards).
  Displayed value = base + booster, scaled to the in-game −30…+30 scale
  (`scale_reputation()` in `scanner/handlers/reputation.py`).
- `locked="1"` on a `<relations>` wrapper marks factions the game never
  changes (Xenon, Kha'ak — permanently hostile).
- Stub faction blocks exist (e.g. `visitor001`) and must be ignored.
