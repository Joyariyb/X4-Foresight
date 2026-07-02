# The web build (Pyodide)

How the in-browser build under `ui/web/` works, and the gotchas that cost
real debugging time to learn. Read this before touching anything in
`ui/web/` or `pyweb/`. Update it when the worker/bridge plumbing changes;
add new gotchas as they're discovered (same spirit as
[save-format.md](save-format.md)).

## The one-sentence version

The *same* Python pipeline runs in the browser under
[Pyodide](https://pyodide.org/) inside a Web Worker, reading the save
through the File System Access API and writing to an in-memory (MEMFS)
SQLite database — nothing is ever uploaded.

## The pieces

| File | Role |
|------|------|
| `ui/web/index.html` | Web shell — loads the shared `ui/body.html` + script list via `shell-loader.js`, plus its bridge trio |
| `ui/web/js/scan-worker.js` | The Web Worker owning the **one** persistent Pyodide instance + MEMFS SQLite DB for the whole session |
| `ui/web/js/pyodide-bridge.js` | Main-thread postMessage RPC proxy; sets `window._bridge` with the same method shape as the desktop `EmpireBridge` |
| `ui/web/js/fs-access.js` | File System Access grant for the saves folder, IndexedDB handle persistence |
| `ui/web/js/byte-staging.js` | Copies save bytes from a file handle into Pyodide's MEMFS |
| `ui/web/js/save-picker-dialog.js` | Save selection UI |
| `pyweb/web_entry.py` | Python entry points the worker calls — `run_pipeline()` for scans, `export/bridge_api.py` for everything else |
| `ui/web/py-manifest.json` | The list of Python files the worker stages into MEMFS at boot |
| `ui/web/generate_manifest.py` | Regenerates that manifest |
| `ui/web/assets/lang_0001-l044.xml` | Pre-extracted language file (committed, ~6 MB) |
| `ui/web/extract_language_file.py` | Offline extractor that produces it |

## Design decisions (the *why*)

- **The Worker is load-bearing, not a nicety.** A real-save scan is one
  synchronous ~80–100 s Python call that fully blocks whatever thread runs
  it — a main-thread scan froze the tab so hard devtools couldn't reach it.
  Every Python call goes through the worker (not just the scan), so they all
  share the one Pyodide instance and its MEMFS DB.
- **The language file is extracted offline, not read in-browser.** The
  scanner normally reads sector/ship names out of the game's `.cat`/`.dat`
  archives, which would have needed a second directory grant for the X4
  install folder. Instead, `extract_language_file.py` is run offline (on a
  machine with X4 installed) and the result is committed as a static asset.
  **Re-run it after an X4 patch** changes game text. Consequence:
  `gamefiles/` needs zero web-specific changes and is deliberately *not* in
  the py-manifest.
- **Only one filesystem grant in the whole app** — the saves folder.
  `showDirectoryPicker()` requires a genuine user click, so the grant rides
  on the existing "New Scan" button; the handle is persisted in IndexedDB so
  a returning visitor usually doesn't re-pick.
- **The DB is per-session.** MEMFS lives and dies with the tab, so scan
  history doesn't survive a reload yet. OPFS persistence is the known
  follow-up — it works, but needs an explicit `pyodide.FS.syncfs(false, cb)`
  after writes, and has known syncfs bugs on iOS/Safari. Test cross-browser
  before relying on it.
- **Python sources are fetched with `cache: "no-cache"`.** The source tree
  changes on every deploy; a stale HTTP-cached file once made a fixed bug
  keep reappearing. Keep that flag.

## Gotchas — each of these has already bitten once

- **Adding or removing any `.py` file** under `scanner/`, `data/`, `db/` or
  `export/` **breaks the web build** until you regenerate the manifest:
  `python ui/web/generate_manifest.py`. The desktop build won't notice, so
  this fails silently until someone opens the web build.
- **`lxml` and `sqlite3` are both unvendored** in Pyodide — the worker must
  `pyodide.loadPackage(["lxml", "sqlite3"])` explicitly, or imports fail at
  runtime.
- **`pyodide.runPythonAsync(code)` only auto-returns a top-level
  *expression*.** A top-level `try/except` is a compound statement and
  returns `undefined` even on success. Assign a variable inside each branch
  and put the bare name as the final line.
- **JS strings cross the boundary as plain `str`, not `pathlib.Path`.**
  `run_pipeline()` coerces its own arguments, but any new Python API that
  calls `.exists()` etc. on a value coming from JS must wrap it in
  `Path(...)` itself.
- **Worker-relative `fetch()` resolves against the worker script's own
  location** (`ui/web/js/`), not the page that created it — unlike a page's
  `<script>` tags. That's why the manifest fetch path is `../py-manifest.json`.
- **Progress stage numbering is a cross-boundary contract.** The worker
  forwards only the stage *index* (0–3) from `run_pipeline()` and owns its
  own display strings — keep the numbering stable when adding phases (see
  [architecture.md](architecture.md)).

## Running it locally

Serve the **repo root** with any static file server, then open
`/ui/web/index.html` — GitHub Pages serves it the same way. See
[dev-setup.md](dev-setup.md). It must be the repo root (not `ui/web/`)
because the worker fetches the Python source tree from paths above itself.
