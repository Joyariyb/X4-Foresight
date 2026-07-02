# Tests

Regression suite for the scan pipeline: `Scanner` → `TradePostProcessor` →
`resolve_ship_homebases` → `write_scan` → `to_export`. Real saves are
gitignored, so everything runs against a hand-built miniature save whose
element shapes were derived from what the handlers in `scanner/handlers/*.py`
actually parse.

## Running

```
pip install pytest          # once
python -m pytest tests/ -v  # from the repo root
```

No X4 installation, real save, or database is needed. The suite is fast
(sub-second): the save is parsed once per session and shared by all tests.

## Regenerating the golden file

`tests/test_export_golden.py` runs the full pipeline into a throwaway SQLite
DB, calls `to_export()`, and compares the result against
`tests/golden/export.json`. When an intentional change alters the export
shape, regenerate the golden and review the diff like any other code change:

```
# PowerShell
$env:UPDATE_GOLDEN='1'; python -m pytest tests/test_export_golden.py; Remove-Item Env:UPDATE_GOLDEN

# bash
UPDATE_GOLDEN=1 python -m pytest tests/test_export_golden.py
```

Before comparing (and before writing the golden), the export is normalised:

- `scanned_at` is dropped *recursively* — it's a real-world timestamp that
  differs every run, and it appears both in `meta` and echoed inside the
  trends series' scan rows.
- `ware_prices` is dropped — a large static price table, invariant across
  scans. Its *presence* is still asserted, so the golden stays a readable
  snapshot of scan output. (The equipment/hull catalogs are not in
  `to_export()` at all — they live in `resource_library_export()`, covered
  by their own presence test.)

On mismatch the failure message names the exact path of the first difference
(e.g. `$.stations[0].hull_pct: ...`), which is far easier to act on than a
full-dict diff.

## The fixtures

### `tests/fixtures/mini_save.xml`

A ~250-line synthetic save. What it covers:

- `<game time>` metadata, `<player>` name/location, player credits (the
  `<account>` inside `<faction id="player">`).
- Reputation: player base standings + a `<booster>`, an NPC faction block, a
  `locked="1"` relations wrapper (Xenon), and a `visitor001` stub that must be
  ignored.
- One player station with a production module (damaged hull), container
  storage with cargo, a shield module, a trade reservation, a station
  account, a manager NPC, a subordinates connection, and a player fighter
  docked *inside* the station subtree (only reachable via
  `extract_station_docked_ships`).
- One NPC station (type resolved from its production macro, `nameindex`
  roman numeral) with a Format-A `<trade wares>` attribute and a docked NPC
  ship (lands in `ctx.npc_docked_ships`, never `ctx.ships`).
- Two free-flying player ships: a hauler whose homebase comes from its
  TradeRoutine `range` param, and an escort resolved through its commander
  connection ref — both refs point at a *sub-element* of the station
  (`[0x1005]`) and must be mapped to the station id through
  `ctx.dockingbay_index` by `resolve_ship_homebases`. The hauler also
  carries shields/engine/thruster (loadout) and a temp DockAt order marking
  a live delivery.
- One streamed (non-buffered) NPC ship whose order label is captured by the
  streaming path.
- A gate pair across two sectors, one endpoint using a route-derived
  connection name instead of `"destination"`.
- Two sectors with `knownto="player"`, one 9.00-format `<resourceareas>`
  subtree (multiple areas per ware — amounts sum, best yield wins).
- An economy log exercising four post-processor paths: a courier BUY+SELL
  leg pair (`courier` resolution + suppressed pickup), an NPC ship resolved
  via same-ware `visit` evidence, a despawned seller declared in
  `<economylog><removed>` (plain-decimal id `853` → `[0x355]` via
  `norm_id`), and a `selloffer` row that must be skipped.

Deliberately omitted (out of scope for these tests):

- `<connections><connection>` wrappers around nested components — the
  scanner tracks only `<component>` elements, so direct nesting parses the
  same and reads better.
- The `<aidirector>` script-vars path into `delivery_dest_index`, carriers
  with docked fighters, buildstorages, mining trades, active trade orders
  (TradeHandler is a placeholder), legacy pre-9.00 `<wares>/<yields>`
  resource layout, and highway connections on gates.
- gzip: the fixture is plain `.xml`; `open_save()`'s `.gz` branch is not
  exercised.

### `tests/fixtures/mini_lang.xml`

A two-entry language file (page 20004). It exists because
`Scanner(lang_path=None)` falls back to reading `t/0001-l044.xml` out of a
real X4 install via `gamefiles.catalog` — results would then depend on
whether the machine has the game installed. More importantly, a sector whose
name cannot be resolved is *skipped entirely* by `SectorHandler` before it
sets `ctx.current_sector_macro`, which silently drops every station, ship and
gate in that sector. `TestNoLanguageFile` pins exactly that degradation mode
(with `find_x4_install` monkeypatched to `None` so it stays deterministic).

## Gotchas worth knowing before editing the fixture

- Macros must be real vanilla macros wherever a handler resolves them against
  the generated data tables (`SHIP_STATS`, `STATION_STATS`, `WARE_*`) —
  unknown macros are silently dropped from hull/shield/cargo accounting, and
  a fixture the handlers silently skip tests nothing.
- Trade-log `price` is in **cents**; `v` is the unit volume.
- Attributes on non-component elements are only readable at their *start*
  event (the scanner clears elements on end), so data must sit on opening
  tags exactly as it does in real saves.
- NPC ships must appear in a sector that contains a player station to reach
  the `npc_ships` DB table / export section.
