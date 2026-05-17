# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

X4 Foresight is a Python tool that scans unzipped X4: Foundations save files (700MB+ XML) and extracts structured empire data. It outputs a console report and a JSON export for AI analysis, with a PyQt6 desktop UI for interactive browsing.

## Setup & Run

```bash
python -m venv .venv
.venv\Scripts\activate
pip install PyQt6 PyQt6-WebEngine

# Run full pipeline (scanner + console report + JSON export)
python x4_save_scanner.py

# Launch desktop UI (reads the generated JSON)
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
save_001.xml ──► Scanner Pipeline (3 passes) ──► game_data dict
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

### Three-Pass Streaming Pattern

All passes use `xml.etree.ElementTree.iterparse()` for memory efficiency on giant files. Elements are cleared immediately after processing except for station subtrees (which must buffer production module children).

| Pass | Module | Extracts |
|------|--------|----------|
| 1 | `scanner.py` | Player identity, credits, stations + their production modules |
| 2 | `scanner.py` | Faction reputation (raw float → log10 display scale) |
| 3 | `ship_scanner.py` | Ships (player always; NPC conditional on `SHIP_SCAN_TIER`) |

### Key Modules

| Module | Role |
|--------|------|
| `scanner.py` | Passes 1 & 2 — player stats, stations with sector tracking, reputation |
| `ship_scanner.py` | Pass 3 — ship extraction with role/faction lookup, pilot data |
| `language.py` | Loads X4 language file; resolves sector macro IDs to human names |
| `display.py` | ASCII console report with reputation bars, fleet grouping |
| `export/jsonexport.py` | Builds structured JSON with fleet summaries by role/size/sector |
| `ui/main_ui.py` | PyQt6 window + WebChannel bridge exposing `EmpireBridge` to JS |
| `ui/ui.html` | Single-file dashboard (~600 lines, dark theme, reads JSON via bridge) |
| `data/factions.py` | Faction names, rep scaling, tier labels |
| `data/ships.py` | Pre-generated macro → display name lookup |
| `data/wares.py` | Production ware display names |

### Python ↔ JavaScript Bridge

`main_ui.py` exposes `EmpireBridge.get_empire_data()` via `QWebChannel`. `ui.html` calls this method to retrieve the JSON and render the dashboard — no HTTP server involved.

## Key Algorithms

**Sector name resolution** (`language.py`):
- Macro format: `cluster_43_sector001_macro`
- `lang_id = str(cluster_num * 10) + str(sector_num * 10 + 1).zfill(3)`

**Reputation scaling** (matches in-game display):
- Raw float from save → `display = log10(raw) * 10 + 30`, clamped to −30..+30, mirrored for negatives

**Ship name resolution** (priority order in `ship_scanner.py`):
1. Exact lookup in `data/ships.py` `SHIP_NAMES` dict
2. Constructed fallback: `"{Faction} {Size} {Role} ({Variant})"`

## Ignored Folders

`Legacy/` is excluded via `.claudeignore` — it contains raw extracted game XML files used during development and should not be read, searched, or modified.

## Required Input Files

Users must provide (gitignored):
- `save_001.xml` — unzipped X4 save file (~700MB)
- `0001-l044.xml` — optional English language file (from game `.cat` files via XRCatTool); enables sector name resolution
