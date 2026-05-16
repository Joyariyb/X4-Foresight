# X4 Foresight — Empire Intelligence

Scans an unzipped X4: Foundations save file and produces a structured JSON snapshot of your empire — pilot info, credits, stations, faction rep, and fleet — ready to paste into an AI prompt for strategic advice. Also includes a PyQt6 desktop UI to browse the data.

## Project structure

```
X4 Foresight/
├── scanner/               # XML parsing
│   ├── language.py        # Sector name resolution from language file
│   ├── scanner.py         # Pass 1 (player/stations) and Pass 2 (reputation)
│   └── ships.py           # Pass 3 (player fleet + optional NPC ships)
├── data/                  # Static lookup tables
│   ├── factions.py        # Faction names and reputation scaling
│   ├── wares.py           # Production ware display names
│   └── ships.py           # Ship type display names (auto-generated — see Legacy)
├── export/                # Output
│   └── jsonexport.py      # Builds and writes x4_empire_state.json
├── ui/                    # Desktop frontend
│   ├── main_ui.py         # PyQt6 window + JS bridge
│   ├── ui.html            # Dashboard HTML
│   └── assets/            # Icons and fonts used by ui.html
│       ├── tabler-icons_min.css
│       └── tabler-icons.woff2
├── Legacy/                # One-time generation tools and extracted game data
│   └── generate_ship_names.py  # Regenerate data/ships.py from game files
├── display.py             # Console report formatter
├── x4_save_scanner.py     # Entry point — run this
└── X4_Empire_Intelligence.pyw  # Windows double-click launcher (no console)
```

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate      # macOS / Linux

pip install PyQt6 PyQt6-WebEngine
```

## Usage

1. Unzip your X4 save file and rename it to `save_001.xml`, place it in the project root.
2. Optionally place `0001-l044.xml` (X4 English language file) in the project root for human-readable sector names and ship type names.
3. Run the scanner:

```bash
python x4_save_scanner.py
```

This writes `x4_empire_state.json` to the project root and prints a console report.

4. Launch the UI:

```bash
python ui/main_ui.py
# or on Windows, double-click X4_Empire_Intelligence.pyw
```

## Run modes

Edit `RUN_MODE` in `x4_save_scanner.py` to control which passes run:

| Mode | What runs | Use case |
|------|-----------|----------|
| `"full"` | Complete pipeline — player, stations, reputation, ships, export | Normal usage |
| `"ships"` | Ships scan only — skips Pass 1 and Pass 2 | Iterating on ship data |

## Ship scan tiers

Edit `SHIP_SCAN_TIER` in `x4_save_scanner.py` (only meaningful in `"full"` mode):

| Tier | What's included | Speed |
|------|----------------|-------|
| 1 | Player ships only (default) | Fastest |
| 2 | + NPC ships in sectors where you have stations | Medium |
| 3 | + NPC ships in all sectors where you have ships | Slowest |

## Ship type names

Ship display names (e.g. "Magpie Sentinel", "Magnetar (Gas) Vanguard") are stored in `data/ships.py`, which is auto-generated from the game's language and macro files. It covers the base game and all DLC factions.

To regenerate `data/ships.py` after a game update or new DLC:

1. Extract ship macro XMLs from the game's `.cat` files using XRCatTool (from X Tools on Steam):
```
XRCatTool.exe -in "X4 Foundations" -out "extracted" -include "assets/units/.*/macros/ship_.*_macro\.xml"
```
2. Run the generator from the project root:
```bash
python Legacy/generate_ship_names.py
```

## Notes

- `save_001.xml` and `0001-l044.xml` are gitignored (user-specific, large files).
- `x4_empire_state.json` is also gitignored — it's generated output.
- `data/ships.py` is committed to the repo — no need to regenerate unless the game adds new ships.
- `.idea/` (PyCharm) and `.venv/` are gitignored.
