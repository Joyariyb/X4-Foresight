# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

X4 Foresight is a Python tool that scans X4: Foundations save files (700MB+ compressed XML) and extracts structured empire data. It reads saves directly from the game's save directory, outputs a console report and a JSON export for AI analysis, and provides a PyQt6 desktop UI for interactive browsing. The UI can trigger a new scan itself without needing the CLI.

## Setup & Run

```bash
python -m venv .venv
.venv\Scripts\activate
pip install PyQt6 PyQt6-WebEngine

# Run full pipeline (interactive save selector → scanner → console report → JSON export)
python x4_save_scanner.py

# Launch desktop UI (prompts to run a new scan or load existing JSON)
python ui/main_ui.py

# Windows launcher (no console window)
pythonw X4_Empire_Intelligence.pyw
```

No formal test suite exists. Verification is done by running the pipeline against a real save file.

## Configuration

Edit constants at the top of `x4_save_scanner.py`:

- `RUN_MODE`: `"full"` (complete pipeline) or `"ships"` (ships-only scan)
- `SHIP_SCAN_TIER`: `1` (player ships only, fastest), `2` (+ NPC in station sectors), `3` (+ NPC in all ship sectors)

## Architecture

### Data Flow

```
Game save directory ──► select_save_file() ──► save_NNN.xml.gz
                                                      │
                                               open_save() ── streams gzip/xml
                                                      │
                                          Scanner Pipeline (3 passes)
                                                      │
                                                 game_data dict
                                                      │
                                        ┌─────────────┴───────────────┐
                                        ▼                             ▼
                                  display.py                   jsonexport.py
                               (console report)           (x4_empire_state.json)
                                                                      │
                                                                      ▼
                                                               main_ui.py + ui.html
                                                               (PyQt6 dashboard)
```

The UI has its own startup flow — it can prompt to run a new scan (using the same scanner modules as the CLI) before showing the dashboard.

### Three-Pass Streaming Pattern

All passes use `xml.etree.ElementTree.iterparse()` for memory efficiency on giant files. Elements are cleared immediately after processing except for station subtrees (which must buffer production module children). Save files are read via `open_save()` which transparently handles both `.xml` and `.xml.gz` formats.

| Pass | Module | Extracts |
|------|--------|----------|
| 1 | `scanner.py` | Player identity, credits, stations + their production modules |
| 2 | `scanner.py` | Faction reputation (raw float → log10 display scale) |
| 3 | `ship_scanner.py` | Ships (player always; NPC conditional on `SHIP_SCAN_TIER`) |

### Key Modules

| Module | Role |
|--------|------|
| `scanner.py` | Passes 1 & 2 — player stats, stations with sector tracking, reputation |
| `ship_scanner.py` | Pass 3 — ship extraction with role/faction lookup, pilot data, docked ship extraction |
| `language.py` | Loads X4 language file; resolves sector macro IDs to human names; provides `open_save()` |
| `display.py` | ASCII console report with reputation bars, fleet grouping |
| `export/jsonexport.py` | Builds structured JSON with fleet summaries by role/size/sector |
| `ui/main_ui.py` | Startup flow (scan prompt, save selector, background scan thread), PyQt6 window + WebChannel bridge |
| `ui/ui.html` | Single-file dashboard (dark theme, reads JSON via bridge) |
| `data/factions.py` | Faction names, rep scaling, tier labels |
| `data/ships.py` | Pre-generated macro → display name lookup |
| `data/wares.py` | Production ware display names |

### Python ↔ JavaScript Bridge

`main_ui.py` exposes `EmpireBridge.get_empire_data()` via `QWebChannel`. `ui.html` calls this method to retrieve the JSON and render the dashboard — no HTTP server involved. The UI always reads the exported JSON format (from `jsonexport.py`), not the raw `game_data` dict.

### UI Startup Flow (`main_ui.py`)

1. If `x4_empire_state.json` exists → ask "Run new scan?"
   - Yes → save selector dialog → scan in `ScanWorker` background thread → read exported JSON → show dashboard
   - No → read existing JSON → show dashboard
2. If no JSON exists → save selector → scan → show dashboard

The scan runs in a `QThread` (`ScanWorker`) so the Qt UI stays responsive during the ~90 second scan. It calls the same scanner functions as the CLI.

## Key Algorithms

**Save file discovery** (`x4_save_scanner.py`, `ui/main_ui.py`):
- Auto-detects from `%USERPROFILE%\Documents\Egosoft\X4\{steamid}\save\`
- `pathlib.Path.home()` handles any Windows username automatically
- Lists manual saves (`save_001`–`save_010`) then autosaves, sorted by slot number
- Falls back to `save_001.xml` in the project root if the game directory is not found

**Sector name resolution** (`language.py` → `ship_scanner.py`):
- Macro format: `cluster_43_sector001_macro`
- `lang_id = str(cluster_num * 10) + str(sector_num * 10 + 1).zfill(3)`
- `_parse_sector()` checks the parent **sector** macro first (handles X4's dynamic `tempzone` elements which don't encode the sector in their name), then falls back to parsing the zone macro string

**Docked ship extraction** (`ship_scanner.py`):
- Ships docked inside a carrier are invisible to the main iterparse loop (the `inside_ship` flag blocks their detection)
- `_extract_docked_ships()` is called after a carrier is fully buffered; it walks the carrier's complete in-memory subtree and extracts all nested ship elements at any depth
- Docked ships inherit the carrier's already-resolved sector

**Reputation scaling** (matches in-game display):
- Raw float from save → `display = log10(raw) * 10 + 30`, clamped to −30..+30, mirrored for negatives

**Ship name resolution** (priority order in `ship_scanner.py`):
1. Exact lookup in `data/ships.py` `SHIP_NAMES` dict
2. Constructed fallback: `"{Faction} {Size} {Role} ({Variant})"`

## Ignored Folders

`Legacy/` is excluded via `.claudeignore` — it contains raw extracted game XML files used during development and should not be read, searched, or modified.

## Required Input Files

These files are gitignored and must be provided by the user:
- `0001-l044.xml` — **Required.** English language file extracted from X4's `.cat` files using XRCatTool (free on Steam). Without it, all sector names will be unresolved. Place in the project root.
- Save files — read directly from `%USERPROFILE%\Documents\Egosoft\X4\{steamid}\save\` as `.xml.gz`. No manual unzipping required. As a fallback, `save_001.xml` (unzipped) can be placed in the project root.
