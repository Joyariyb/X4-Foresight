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
│   └── wares.py           # Production ware display names
├── export/                # Output
│   └── jsonexport.py      # Builds and writes x4_empire_state.json
├── ui/                    # Desktop frontend
│   ├── main_ui.py         # PyQt6 window + JS bridge
│   ├── ui.html            # Dashboard HTML
│   └── assets/            # Icons and fonts used by ui.html
│       ├── tabler-icons_min.css
│       └── tabler-icons.woff2
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
2. Optionally place `0001-l044.xml` (X4 English language file) in the project root for human-readable sector names.
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

## Ship scan tiers

Edit `SHIP_SCAN_TIER` in `x4_save_scanner.py`:

| Tier | What's included | Speed |
|------|----------------|-------|
| 1 | Player ships only (default) | Fastest |
| 2 | + NPC ships in sectors where you have stations | Medium |
| 3 | + NPC ships in all sectors where you have ships | Slowest |

## Notes

- `save_001.xml` and `0001-l044.xml` are gitignored (user-specific, large files).
- `x4_empire_state.json` is also gitignored — it's generated output.
- `.idea/` (PyCharm) and `.venv/` are gitignored.
