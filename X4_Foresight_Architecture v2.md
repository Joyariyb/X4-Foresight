# X4 Foresight — Architecture Overview

A guide to how the system fits together: data flow, module relationships, the central data schema, and the Python-to-JavaScript bridge.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Data Flow](#2-data-flow)
3. [The Three Passes](#3-the-three-passes)
4. [The `game_data` Schema](#4-the-game_data-schema)
5. [The `x4_empire_state.json` Schema](#5-the-x4_empire_statejson-schema)
6. [The Python ↔ JavaScript Bridge](#6-the-python--javascript-bridge)
7. [The UI: Structure and Rendering](#7-the-ui-structure-and-rendering)
8. [Module Dependency Map](#8-module-dependency-map)
9. [Scan Tiers and Run Modes](#9-scan-tiers-and-run-modes)
10. [Known Limitations and Gotchas](#10-known-limitations-and-gotchas)

---

## 1. System Overview

X4 Foresight has two independent outputs from a single scan pipeline:

- **Console report** — printed immediately after scanning via `display.py`
- **JSON export** — written to `x4_empire_state.json` via `export/jsonexport.py`, consumed by both the desktop UI and AI prompts

The scanner itself never touches the UI. The UI is a completely separate process that reads the JSON file on launch. This means you can run the scanner headlessly, inspect the JSON, paste it into an AI prompt, and only optionally open the UI — all from the same output file.

```
save_001.xml ──► Scanner Pipeline ──► game_data dict ──┬──► Console Report
                                                        └──► x4_empire_state.json ──► UI / AI Prompt
```

---

## 2. Data Flow

The full pipeline in execution order:

```
x4_save_scanner.py
│
├── load_sector_names()          scanner/language.py
│     └── reads 0001-l044.xml
│         returns { lang_id: sector_name }
│
├── scan_save()                  scanner/scanner.py       [Pass 1]
│     ├── streams save_001.xml
│     ├── calls macro_to_sector_name()
│     ├── calls resolve_sector_from_location()
│     └── calls parse_production_from_construction()
│         returns game_data (player, stations)
│
├── scan_reputation()            scanner/scanner.py       [Pass 2]
│     ├── streams save_001.xml again
│     ├── calls scale_reputation()      data/factions.py
│     └── calls reputation_label()      data/factions.py
│         returns reputation list
│
├── scan_ships()                 scanner/ship_scanner.py  [Pass 3]
│     ├── streams save_001.xml again
│     ├── calls macro_to_sector_name()
│     ├── calls extract_role()
│     ├── calls extract_faction_from_macro()
│     ├── calls resolve_ship_type()     data/ships.py
│     ├── calls _parse_pilot()
│     ├── calls _parse_current_order()
│     ├── calls _parse_commander()
│     ├── calls _parse_software()
│     ├── calls _parse_hull()
│     └── looks up SHIP_STATS           data/ship_stats.py
│         returns { player_ships, npc_ships }
│
├── display_results()            display.py
│     └── prints console report
│
└── export_json()                export/jsonexport.py
      ├── calls _build_fleet_summary()
      ├── calls _build_npc_summary()
      └── writes x4_empire_state.json
```

---

## 3. The Three Passes

The save file is streamed three times rather than once. This is an intentional design choice driven by memory constraints.

**Why not one pass?**

X4 save files are 700MB+. `iterparse()` is used throughout to stream the XML one element at a time rather than loading it into memory. The problem is that iterparse makes tracking parent context across deeply nested structures complex — particularly for reputation data, which sits inside `<faction id="player"><relations>` while stations and ships are elsewhere in the universe hierarchy.

Three focused passes, each with a clear single responsibility, are simpler and more reliable than one monolithic pass with complex state tracking. The CPU cost of re-streaming is small relative to the RAM that would be required to hold the whole tree.

**Pass 1 — Player identity and stations** (`scan_save`)

Tracks the current sector as it streams, so that any player-owned station encountered inherits the sector it's nested within. Uses a buffering technique: when a player station's opening tag is spotted, `elem.clear()` is suppressed for all descendants until the station's closing tag arrives, preserving child elements needed to parse production modules.

**Pass 2 — Faction reputation** (`scan_reputation`)

A short, focused pass that stops as soon as the player faction block is fully read. Separates permanent base standing from temporary mission boosters and converts raw internal floats to in-game display values using the log10 curve.

**Pass 3 — Ships** (`scan_ships`)

The most complex pass. Tracks zone macros to resolve ship sectors (ships are nested under zones, not sectors directly), uses the same buffering technique as Pass 1 to preserve ship child elements, and applies name resolution in priority order. For each ship, hull health is extracted from the `<hull value="..."/>` child element (absent when undamaged) and the base max hull is looked up from `SHIP_STATS` in `data/ship_stats.py` to compute a percentage. Collects NPC ships only for sectors in `context_sectors`.

---

## 4. The `game_data` Schema

`game_data` is the central dictionary assembled in `x4_save_scanner.py` and passed to both `display_results()` and `export_json()`. It is never written to disk directly — it is the in-memory intermediate representation.

```python
game_data = {

    # ── Player identity ───────────────────────────────────────────────────────
    "player_name":    str | None,   # Pilot name as set in-game
    "player_sector":  str | None,   # Human-readable current sector name
    "player_credits": str | None,   # Raw integer string, e.g. "4831209"

    # ── Stations ──────────────────────────────────────────────────────────────
    "stations": [
        {
            "name":       str,   # Display name (custom, HQ, index, or "Unnamed")
            "code":       str,   # Short identifier code, e.g. "APX-001"
            "class":      str,   # XML class: "station", "factory", "headquarters", "complex"
            "macro":      str,   # Raw macro string from save XML
            "sector":     str,   # Human-readable sector name
            "production": str,   # Comma-separated ware display names, or ""
        },
        # ... one entry per player-owned station
    ],

    # ── Reputation ────────────────────────────────────────────────────────────
    # Populated by Pass 2. Empty list in "ships" run mode.
    "reputation": [
        {
            "faction_id":   str,    # Internal ID, e.g. "argon"
            "faction_name": str,    # Display name, e.g. "[ARG] Argon Federation"
            "value":        float,  # Scaled total (base + booster), range -30..+30
            "base":         float,  # Scaled permanent standing
            "booster":      float,  # Scaled temporary mission bonus (0.0 if none)
            "tier":         str,    # "Allied" | "Friendly" | "Neutral" | "Hostile" | "At War"
        },
        # ... sorted by value descending
    ],

    # ── Ships ─────────────────────────────────────────────────────────────────
    # Populated by Pass 3. Nested dict returned directly by scan_ships().
    "ships": {

        "player_ships": [
            {
                "code":        str,          # Ship identifier code, e.g. "LSS-543"
                "name":        str | None,   # Custom name, type name, or None
                "class":       str,          # "ship_s" | "ship_m" | "ship_l" | "ship_xl"
                "size":        str,          # "S" | "M" | "L" | "XL"
                "macro":       str,          # Raw macro string
                "role":        str,          # e.g. "Freighter", "Miner (Solid)", "Fighter"
                "hull_origin": str,          # Faction that built the hull, e.g. "Argon", "Xenon"
                "owner":       str,          # Always "player" for player ships
                "sector":      str,          # Human-readable sector name
                "order":       str,          # e.g. "Mining", "Trading", "Idle"
                "pilot": {
                    "name":   str | None,
                    "skills": {
                        "piloting":    int,
                        "management":  int,
                        "morale":      int,
                        "engineering": int,
                    }
                    # skills is {} if no pilot found
                },
                "software":   list[str],    # Installed software ware IDs
                "commander":  str | None,   # Commander connection reference, or None
                "hull_hp":    float | None, # Current hull HP; None means undamaged (full health)
                "hull_pct":   float | None, # HP as % of base max (0–100+); None if max unknown
                "max_hull":   int | None,   # Base max HP from SHIP_STATS; None if macro not found
            },
            # ...
        ],

        "npc_ships": [
            {
                "code":        str,
                "class":       str,
                "size":        str,
                "macro":       str,
                "role":        str,
                "hull_origin": str,
                "owner":       str,   # Faction ID of NPC owner
                "sector":      str,
                "order":       str,
            },
            # ... only populated at scan tiers 2 and 3
        ],
    },
}
```

### Hull health fields explained

X4 only writes `<hull value="..."/>` inside a ship's save data when the ship has taken damage. Absence of the element means the ship is at full health. This is why `hull_hp` is `None` (not `0`) for undamaged ships.

`hull_pct` is derived by dividing `hull_hp` by `max_hull` from `data/ship_stats.py`. If a ship's macro is not in `SHIP_STATS` (e.g. a modded ship or a new DLC ship not yet extracted), `hull_pct` will be `None` even if the ship is damaged.

`hull_pct` can exceed 100% when a hull capacity mod is installed — the mod raises the ship's effective max above the base value stored in `SHIP_STATS`, so the scanner's percentage calculation overshoots. See section 10 for details.

---

## 5. The `x4_empire_state.json` Schema

The JSON export is a restructured version of `game_data` with two pre-computed summary dicts added. It is the only artifact that persists to disk and is consumed by both the UI and AI prompts.

```
{
  "player_name":    string | null,
  "player_sector":  string | null,
  "player_credits": string | null,

  "stations": [ ...same shape as game_data.stations... ],

  "reputation": [ ...same shape as game_data.reputation... ],

  "ships": {

    "player_ships": [ ...same shape as game_data.ships.player_ships...
                       including hull_hp, hull_pct, max_hull ],

    "fleet_summary": {
      "total":     int,
      "by_role":   { role: count },
      "by_size":   { size: count },
      "by_order":  { order: count },
      "by_sector": { sector: { role: count } }
    },

    "npc_ships": [ ...same shape as game_data.ships.npc_ships... ],

    "npc_summary": {
      sector: {
        faction: {
          role: count
        }
      }
    }
  }
}
```

The `fleet_summary` and `npc_summary` blocks are pre-digested so that an AI assistant can get an immediate high-level picture without counting individual ships, and so the UI can populate summary cards without iterating the full ship list on every render.

The `player_ships` list is passed through from the scanner without filtering, so all fields including `hull_hp`, `hull_pct`, and `max_hull` are present in the JSON automatically.

---

## 6. The Python ↔ JavaScript Bridge

The desktop UI runs as a `QWebEngineView` inside a native Qt window. The HTML dashboard is a local file loaded from disk — it has no server, no HTTP, and no network access. Data passes from Python to JavaScript through Qt's `QWebChannel` mechanism.

### Python side (`ui/main_ui.py`)

```python
# 1. Create the bridge object with the empire data
self.bridge = EmpireBridge(data)

# 2. Register it with a QWebChannel under the name "bridge"
self.channel = QWebChannel()
self.channel.registerObject("bridge", self.bridge)

# 3. Attach the channel to the web page
self.view.page().setWebChannel(self.channel)
```

`EmpireBridge` exposes one slot:

```python
@pyqtSlot(result=str)
def get_empire_data(self) -> str:
    return json.dumps(self._data)
```

The `@pyqtSlot` decorator is required — without it, the method is not visible to JavaScript. The `result=str` annotation tells Qt the return type so it can marshal the value correctly across the bridge.

### JavaScript side (`ui/ui.html`)

The HTML file loads Qt's channel script from a virtual resource path:

```html
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
```

This script is built into Qt and provides the `QWebChannel` constructor. Once the page loads, JavaScript connects to the channel and calls the Python method:

```javascript
new QWebChannel(qt.webChannelTransport, function(channel) {
    channel.objects.bridge.get_empire_data(function(jsonStr) {
        try {
            populate(JSON.parse(jsonStr));
        } catch(e) {
            document.getElementById("loading").textContent = "Error parsing data: " + e;
        }
    });
});
```

- `qt.webChannelTransport` is a global injected by Qt into every page loaded by `QWebEngineView` when a channel is attached
- `channel.objects.bridge` maps to the Python object registered under the name `"bridge"`
- `get_empire_data` is called asynchronously; the result arrives in the callback as a JSON string
- `populate()` parses the JSON and renders the entire UI in one synchronous pass

### Why this matters for future development

Any new data you want to expose to the UI must go through this bridge. The pattern is:

1. Add the data to the `game_data` dict in the scanner
2. Include it in the JSON export in `export_json()`
3. It will automatically be available in `populate(data)` in the HTML — no Python UI changes needed unless you want to add a new callable method

If you need JavaScript to *call back into Python* (e.g. to trigger a rescan), you would add a new `@pyqtSlot` method to `EmpireBridge` and call it via `channel.objects.bridge.your_method(args, callback)`.

---

## 7. The UI: Structure and Rendering

### Layout

The UI is a single-page dashboard with no routing or component framework. Layout is pure CSS with four structural regions:

```
┌─────────────────────────────────────────────────────┐
│  #topbar   Pilot · Sector · Credits · Ships · Stations │
├─────────────────────────────────────────────────────┤
│  #nav      Overview · Fleet · Stations · Diplomacy · Alerts │
├──────────┬──────────────────────────────────────────┤
│ #sidebar │ #content                                  │
│          │  (active .tab-panel)                     │
│          │                                           │
└──────────┴──────────────────────────────────────────┘
```

### Tabs

Tab switching is handled by `switchTab(name, clickedEl)`, which removes the `active` class from all `.tab-panel` and `.nav-tab` elements and adds it to the target panel and tab. The sidebar items call the same function. No state is stored — the active tab is purely determined by which element has the `active` class.

### The `populate(data)` function

All rendering happens in a single call to `populate(data)` after the JSON is received from the bridge. There is no incremental rendering or reactive state. `populate` does the following in order:

1. Fills the top bar fields (pilot, sector, credits, ship count, station count)
2. Derives filtered ship lists: `hostile`, `military`, `traders`, `miners`, `waiting`
3. Updates sidebar counts for each fleet category
4. Builds the sidebar station list grouped by sector
5. Updates the alerts badge count in the nav
6. Renders the five summary cards (Credits, Total Ships, Stations, Hostile Hulls, Waiting)
7. Renders the Fleet by Role table
8. Renders the Fleet by Order table
9. Renders the full fleet table (one row per player ship) via `renderFleet()`
10. Renders the stations grid (one panel card per station)
11. Renders the faction standings table
12. Generates and renders alert messages
13. Hides the loading spinner and shows the main shell

### Fleet sort

The fleet table supports sorting by any column. Sort state is tracked in two module-level variables: `currentSortKey` and `currentSortDir` (1 = ascending, −1 = descending). The sort dropdown resets to a neutral placeholder after every pick so that re-selecting the same option always fires `onchange` and toggles the direction. A `sort-indicator` label next to the dropdown shows the active sort key and arrow (↑/↓) at all times.

Null values (ships with missing data for the selected field) always sort to the bottom regardless of direction. The **Health** sort defaults to descending on first pick (highest HP first) and toggles from there.

### Alert logic

Three alert conditions are checked in `populate`:

| Alert | Condition | Colour |
|---|---|---|
| Hostile hulls | Any player ship with `hull_origin` in `HOSTILE_ORIGINS` (`Xenon`, `Yaki`, `Kha'ak`) | Red |
| Waiting ships | Any player ship with `order === "Waiting"` | Amber |
| Idle miners | Intersection of waiting ships and `MINER_ROLES` | Amber |

### Icon and colour lookup tables

Rather than inline logic, the UI uses flat lookup objects defined at the top of the script block. To add support for a new role or order, add an entry to the relevant table:

| Table | Purpose |
|---|---|
| `ROLE_ICONS` | Maps role strings to Tabler icon class names |
| `ORDER_ICONS` | Maps order strings to Tabler icon class names |
| `ORDER_COLOURS` | Maps order strings to CSS colour variables |
| `SIZE_COLOURS` | Maps size strings (`S`, `M`, `L`, `XL`) to CSS colour variables |
| `CARD_ICONS` | Maps summary card label strings to Tabler icon class names |

### Helper functions

| Function | Purpose |
|---|---|
| `fmtCredits(n)` | Formats a credit value as `1.2M Cr`, `430.5k Cr`, or `n Cr` |
| `hullBadge(origin)` | Returns a coloured `<span class="badge">` for a hull origin faction; prefixes hostile origins with `*` |
| `hullBar(pct, hullHp, maxHull)` | Returns an HTML block containing a labelled percentage bar for hull health. Bar colour graduates from red (0%) through amber to green (100%); ships above 100% (hull mod installed) render in blue. Shows `current / max HP` text below the label. Degrades gracefully when `pct` or `maxHull` is null. |
| `tierBadge(tier)` | Returns a coloured `<span class="badge">` for a reputation tier |
| `repBar(value)` | Returns an inline HTML reputation bar scaled to the −30..+30 range, coloured green for positive and red for negative |
| `sign(n)` | Formats a float with an explicit `+` or `−` prefix |

---

## 8. Module Dependency Map

```
x4_save_scanner.py
├── scanner/language.py
├── scanner/scanner.py
│   ├── scanner/language.py
│   ├── data/factions.py
│   └── data/wares.py
├── scanner/ship_scanner.py
│   ├── scanner/language.py
│   ├── data/ships.py
│   └── data/ship_stats.py
├── export/jsonexport.py
└── display.py

ui/main_ui.py          (separate process)
└── reads x4_empire_state.json

generate_ship_names.py    (one-time utility, formerly in Legacy/)
└── writes data/ships.py

generate_ship_stats.py    (one-time utility)
├── reads ship xml/**/*.xml
└── writes data/ship_stats.py
```

`data/factions.py`, `data/wares.py`, `data/ships.py`, and `data/ship_stats.py` are all leaf nodes — they import nothing from the project and have no side effects. They are pure lookup tables.

`scanner/language.py` is imported by both `scanner/scanner.py` and `scanner/ship_scanner.py`, making it the most widely shared module in the project.

---

## 9. Scan Tiers and Run Modes

### Run modes

Controlled by `RUN_MODE` in `x4_save_scanner.py`. Edit this constant directly — there is no CLI flag.

| Mode | Passes run | Output |
|---|---|---|
| `"full"` | All three passes + display + export | Console report + JSON file |
| `"ships"` | Sector names + Pass 3 only | Console fleet section only, stub values for all other fields |

`"ships"` mode is useful when iterating on `ship_scanner.py` — it skips the 30–60 second overhead of Passes 1 and 2.

### Ship scan tiers

Controlled by `SHIP_SCAN_TIER` in `x4_save_scanner.py`. Only meaningful in `"full"` mode.

| Tier | NPC ships included | How `context_sectors` is built |
|---|---|---|
| 1 | None | `station_sectors=None`, `ship_sectors=None` |
| 2 | Sectors with player stations | `station_sectors={s["sector"] for s in game_data["stations"]}` |
| 3 | Sectors with stations or player ships | Tier 2 + a preliminary tier-1 ship scan to collect ship sectors |

Tier 3 requires two ship scans: a fast tier-1 pre-scan to discover which sectors contain player ships, then the full scan with that sector set. The extra scan adds meaningful time on large save files.

---

## 10. Known Limitations and Gotchas

**Save file must be manually prepared.** X4 saves are stored as compressed archives. The file must be unzipped manually and renamed to `save_001.xml` in the project root before scanning. There is no automatic decompression.

**`RUN_MODE` and `SHIP_SCAN_TIER` require manual editing.** These are module-level constants, not CLI arguments. Open `x4_save_scanner.py` and change them directly.

**Language file is optional but strongly recommended.** Without `0001-l044.xml`, all sector names display as raw macro IDs (e.g. `cluster_43_sector001_macro`) and ship type names fall back to hull-origin + role strings. The file must be extracted from the game's `.cat` files using X Tools (available free on Steam).

**`data/ships.py` needs regeneration after DLC or game updates.** New ships added by expansions will not appear in `SHIP_NAMES` until you extract their macro XMLs and re-run `generate_ship_names.py`. Unrecognised macros fall back to hull-origin + role as the display name.

**`data/ship_stats.py` also needs regeneration after DLC or game updates.** Similarly, new ship macros will not have a `max_hull` entry until their XMLs are added to `ship xml/` and `generate_ship_stats.py` is re-run. Ships with no entry will show `hull_pct = None` and the UI will display raw HP only with no percentage bar.

**Hull mods cause `hull_pct` to exceed 100%.** When a ship has a hull capacity mod installed (visible as `<modification><ship maxhull="1.08375"/>` in the save XML), the ship's effective max HP is higher than the base value stored in `SHIP_STATS`. The scanner calculates percentage against the base max, so a modded ship at full health will appear at e.g. 108% rather than 100%. The UI renders these in blue to distinguish them. See `TO BE NOTED.txt` in the project root for a documented example (Behemoth E destroyer).

**The UI reads the JSON at launch only.** There is no live reload or file watcher. If you re-run the scanner, you must close and reopen the UI to see updated data.

**NPC ship data at tiers 2 and 3 can be slow and memory-intensive.** Large sectors with many NPC ships significantly increase scan time and peak RAM usage. Tier 1 is the default for a reason.

**Windows console requires UTF-8 mode.** The console report uses box-drawing characters (`═`, `─`, `┌`, etc.) that Windows' default `cp1252` encoding cannot handle. Run with `PYTHONUTF8=1` or from Windows Terminal which defaults to UTF-8. The `.pyw` launcher and the UI are unaffected.

**Reputation boosters decay in-game but are static in the scan.** The booster values extracted reflect the save file at the moment of the scan. X4 decays boosters in real time — the displayed booster value will drift from the in-game value the longer you play without rescanning.
