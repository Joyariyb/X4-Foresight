# X4 Foresight — Empire Intelligence

A desktop application for scanning *X4: Foundations* save files and generating structured JSON snapshots for AI strategic advice.

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![PyQt6](https://img.shields.io/badge/UI_Pyqt6-blue.svg)](https://www.riverbankcomputing.com/software/pyqt/)

---

## 🗺️ Scan Pipeline Overview

```
┌─────────────────┐     ┌──────────────┐     ┌──────────────────────┐
│  X4 Save File   │ →   │ Scanner      │ →   │ x4_empire_state.json │
│ (save_001.xml)  │     │ Pipeline     │     │ (JSON snapshot)       │
└─────────────────┘     └──────────────┘     └──────────────────────┘
                              ↓
                        ┌──────────────┐
                        │ UI Dashboard │
                        │ + Reports    │
                        └──────────────┘
```

---

## 📂 Core Functionality

- **Scans Your Save File:** Extracts player identity, stations, ships, reputation, and crew data from *X4: Foundations* save files.
- **Generates Structured JSON:** Outputs `x4_empire_state.json` for use with AI assistants or external dashboards.
- **Configurable Modes & Tiers:** Run in `full` or `ships` mode; set ship scan tiers (1–3) to control NPC fleet inclusion.

---

## 🖥️ Entry Points

### Desktop Application

- **Windows Launcher:** `X4_Empire_Intelligence.pyw`  
  Opens a PyQt6 desktop UI with save selector, progress dialogs, and embedded dashboard.

- **CLI Scanner:** `x4_save_scanner.py`  
  Standalone console scanner for scripting or batch processing.

---

## 📊 Output Format (`x4_empire_state.json`)

| Section | Contents |
|---------|----------|
| **Player** | Name, sector, credits |
| **Stations** | List grouped by sector with production, manager skills |
| **Fleet** | Ships sorted by sector, hull status, captured flags, pilot sub-lines |
| **Reputation** | Faction standings (-30 to +30), base + booster values |
| **Crew** | Roles (manager, pilot, service, marine) with assigned station, primary skill |
| **NPC Fleet** | Tiers 2/3 only: sector → faction → role counts when enabled |

---

## 🔧 Configuration Options

| Mode | Description |
|------|-------------|
| `full` | Default — scans all data (player, stations, fleet, reputation, crew) |
| `ships` | Scans player + fleet only; excludes stations and reputation if desired |

**Scan Tiers:**
- **Tier 1:** Player + faction info
- **Tier 2:** Add stations, managers
- **Tier 3:** Include NPC ships (if enabled), crew details

---

## 📦 Auto-Generated Outputs

| File | Description |
|------|-------------|
| `data/ships.py` | Ship name mappings for UI display |
| `data/ship_stats.json` | Pre-computed faction/sector baselines |
| `x4_empire_state.json` | JSON snapshot of current empire state |

---

## 🛠️ Dependencies

- Python 3.10+
- PyQt6
- PyInstaller (for frozen builds)
- Optional: X4: Foundations save file (`save_001.xml`) and language file (`0001-l044.xml`) for full functionality

---

## 📁 Project Structure

```
X4 Foresight/
├── x4_save_scanner.py       # CLI scanner entry point
├── X4_Empire_Intelligence.pyw  # Windows launcher (no console)
├── launcher.py               # PyQt6 desktop app wrapper
├── display.py                # Console report formatter (ASCII art)
├── export_json.py            # JSON export engine
├── language.py               # Sector/ship name resolution
├── scanner/                  # Scanner modules
│   ├── pass1_player_identity.py
│   ├── pass2_station_reputation.py
│   └── pass3_fleet_crew.py
├── data/                     # Auto-generated outputs
│   ├── ships.py
│   └── ship_stats.json
└── ui/                       # Desktop application source
    ├── main_ui.py            # PyQt6 app entry point
    └── ui.html               # Embedded web dashboard
```

---

## 🚀 Quick Start

1. **Place your X4 save file** in the project root (`save_001.xml`). - not required if save files are in the default location
2. **Run the scanner:**
   - CLI: `python x4_save_scanner.py`
   - GUI: Double-click `X4_Empire_Intelligence.pyw`
3. **Check output:** Open `x4_empire_state.json` for structured data or use UI dashboard.

---

*For detailed code references and architecture diagrams, see `X4_Foresight_Code_Reference.md` and `X4_Foresight_Architecture v2.md`.*
