# Architecture

A one-page map of how a save file becomes a dashboard, and *why* the code is
shaped the way it is. Update this only when a pipeline phase or a layer
boundary actually moves — not for feature work inside a layer.

## The one-sentence version

Three thin shells (CLI, desktop, web) all call one shared pipeline —
**scan → resolve → DB → JSON** — and two UI shells read the result through
one shared bridge API.

```
save_*.xml.gz
     │
     ▼
 scanner/          streaming parse into in-memory entities (ScanContext)
     │
     ▼
 resolve steps     trade counterparties, ship homebases
     │
     ▼
 db/               SQLite write (the durable record, one row-set per scan)
     │
     ▼
 export/           JSON for the UI — via file (CLI) or bridge call (UI shells)
     │
     ▼
 ui/               the dashboard (shared between desktop and web)
```

## The shared pipeline

[`pipeline.py`](../pipeline.py) owns `run_pipeline()` and the canonical file
paths. Every entry point is deliberately thin — it picks a save, wires up a
progress display, and calls `run_pipeline()`. **Never re-assemble the phases
in an entry point**; that's exactly the duplication `pipeline.py` was
extracted to kill.

| Shell | Entry point | Notes |
|-------|------------|-------|
| CLI | `cli/x4_save_scanner.py` | also writes the on-disk JSON export |
| Desktop | `X4_Empire_Intelligence.pyw` → `ui/main_ui.py` | PyQt6 + QtWebEngine |
| Web | `ui/web/` → `pyweb/web_entry.py` | Pyodide — see [web-build.md](web-build.md) |

`run_pipeline()` reports progress as `(stage_index, label)`:
`0` scan, `1` trade resolution, `2` homebase resolution, `3` DB write,
`4` JSON export (only when `json_path` is given). The web worker keys its own
display strings off the *index*, so **keep the numbering stable** when
inserting phases.

## Why each layer looks the way it does

- **`scanner/` streams, never loads.** A mature save is tens of millions of
  XML lines, so the scanner uses `iterparse` with subtree buffering and
  deferred resolution instead of building a DOM. Per-element logic lives in
  `scanner/handlers/`; cross-entity fixups that need the *whole* save parsed
  first (trade counterparties, homebases) run as separate resolve phases
  after the scan.
- **`db/` is the durable record, not a cache.** Scans accumulate as rows
  (scan history powers the Trends view); the UI reads the DB, not the scan in
  memory. Schema versioning uses `PRAGMA user_version` — new *tables* are
  `CREATE TABLE IF NOT EXISTS` and need no version bump; changing an
  *existing* table needs a migration in `db/connection.py`'s `MIGRATIONS`
  list.
- **`export/jsonexport.py` is the only place export shape is defined.**
  `to_export()` builds the big per-scan JSON; `resource_library_export()`
  builds the static equipment/hull catalog (no scan needed).
- **`export/bridge_api.py` is shared shell plumbing.** The five operations
  both UI shells need (`get_empire_data`, `list_scans`, `delete_scan`,
  `delete_all_scans`, `get_resource_library`) live here once. Desktop
  `EmpireBridge` (QWebChannel) and web `pyweb/web_entry.py` (Pyodide RPC) are
  thin wrappers — a fix applied in `bridge_api.py` reaches both. New bridge
  operations go here first, then get a wrapper in each shell.
- **`ui/` is one front-end with two shells.** `ui/ui.html` (desktop) and
  `ui/web/index.html` (web) both load the same `ui/body.html` and the same
  script list from `ui/js/shell-manifest.js` via `shell-loader.js` — so
  there is exactly one place to register a new JS file. On page load,
  `ui/js/scan-loader.js` finds its data source by probing in order:
  `window._bridge` (web) → QWebChannel (desktop) → the on-disk JSON file
  (no-bridge browser dev fallback).

## The export JSON contract

The UI and the pipeline agree on the export shape through a golden file:
[`tests/golden/export.json`](../tests/golden/export.json). The golden test
diffs a fresh export of the synthetic mini-save against it, so any change to
the export shape — intentional or not — fails CI until you *bless* it:

```powershell
# PowerShell
$env:UPDATE_GOLDEN='1'; python -m pytest tests/test_export_golden.py; Remove-Item Env:UPDATE_GOLDEN
# bash
UPDATE_GOLDEN=1 python -m pytest tests/test_export_golden.py
```

Then review the golden diff in git like any other code change. There is no
separate hand-written schema doc on purpose: the golden file is the schema,
and it can't drift because the test enforces it.

## Rules that keep this shape

1. Entry points stay thin — new pipeline behaviour goes in `pipeline.py`.
2. Bridge operations go in `export/bridge_api.py`, wrappers in the shells.
3. Adding/removing any `.py` file under `scanner/`, `data/`, `db/` or
   `export/` requires regenerating the web build's manifest:
   `python ui/web/generate_manifest.py` (see [web-build.md](web-build.md)).
4. New JS files register in `ui/js/shell-manifest.js` and expose one global
   ([UI_STANDARDS.md](UI_STANDARDS.md) §11).
5. Save-format knowledge goes in [save-format.md](save-format.md) the moment
   it's decoded — it is expensive to rediscover.
