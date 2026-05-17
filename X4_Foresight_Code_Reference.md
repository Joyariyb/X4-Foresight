# X4 Foresight — Code Reference

A complete reference for all modules, classes, and functions in the X4 Foresight: Empire Intelligence project.

---

## Table of Contents

1. [Entry Points](#1-entry-points)
   - [x4_save_scanner.py](#x4_save_scannerpy)
   - [X4_Empire_Intelligence.pyw](#x4_empire_intelligencepyw)
2. [scanner/language.py](#2-scannerlanguagepy)
3. [scanner/scanner.py](#3-scannerscannerpy)
4. [scanner/ship_scanner.py](#4-scannership_scannerpy)
5. [display.py](#5-displaypy)
6. [export/jsonexport.py](#6-exportjsonexportpy)
7. [ui/main_ui.py](#7-uimain_uipy)
8. [data/factions.py](#8-datafactionspy)
9. [data/wares.py](#9-datawarespy)
10. [data/ships.py](#10-datashipspy)
11. [data/ship_stats.py](#11-dataship_statspy)
12. [generate_ship_stats.py](#12-generate_ship_statspy)
13. [Legacy/generate_ship_names.py](#13-legacygenerate_ship_namespy)

---

## 1. Entry Points

### `x4_save_scanner.py`

The main entry point for the scanner pipeline. Run this directly from the project root.

**Module-level constants**

| Constant | Type | Description |
|---|---|---|
| `SCRIPT_DIR` | `Path` | Absolute path to the project root, derived from `__file__`. |
| `SAVE_FILE` | `Path` | Expected location of the unzipped save file (`save_001.xml`). |
| `LANG_FILE` | `Path` | Expected location of the X4 English language file (`0001-l044.xml`). |
| `RUN_MODE` | `str` | Controls which passes execute. `"full"` runs the complete pipeline; `"ships"` skips Pass 1 and Pass 2 and scans ships only. |
| `SHIP_SCAN_TIER` | `int` | Controls NPC ship inclusion in full mode. `1` = player ships only, `2` = + NPC ships in station sectors, `3` = + NPC ships in all player ship sectors. Only meaningful when `RUN_MODE = "full"`. |

**Execution flow**

In `"full"` mode the script runs four sequential passes and then exports:

1. `load_sector_names()` — loads the language file for human-readable sector names.
2. `scan_save()` — Pass 1, extracts player identity, credits, and stations.
3. `scan_reputation()` — Pass 2, extracts faction reputation standings.
4. `scan_ships()` — Pass 3, scans the player fleet and optionally NPC ships depending on `SHIP_SCAN_TIER`.
5. `display_results()` — prints the console report.
6. `export_json()` — writes `x4_empire_state.json`.

In `"ships"` mode, only `load_sector_names()` and `scan_ships()` run. A stub `game_data` dict is constructed so `display_results()` can render the fleet section without modification.

---

### `X4_Empire_Intelligence.pyw`

Windows double-click launcher. Equivalent to running `python ui/main_ui.py` but suppresses the console window via the `.pyw` extension. Contains no logic beyond launching the UI entry point.

---

## 2. `scanner/language.py`

Handles parsing the X4 English language file (`0001-l044.xml`) to resolve human-readable names for sectors and ships. All other modules that need sector names call into this one.

---

### `load_sector_names(lang_path)`

```python
def load_sector_names(lang_path: pathlib.Path) -> dict
```

Parses the X4 language file and returns a dictionary mapping numeric language IDs to sector display names.

Sector names live on page `20004` of the language file. Each entry has the form `{20003,270001}(The Void)` — the function extracts the name from the trailing parentheses using a regex and keys it by the element's `id` attribute.

If the language file is absent, the function prints a warning and returns an empty dict; callers fall back to showing raw macro IDs.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `lang_path` | `pathlib.Path` | Path to `0001-l044.xml`. |

**Returns** `dict[str, str]` — maps language ID strings (e.g. `"270011"`) to display names (e.g. `"The Void"`).

---

### `macro_to_sector_name(macro, sector_names)`

```python
def macro_to_sector_name(macro: str, sector_names: dict) -> str | None
```

Converts a sector macro string (e.g. `cluster_43_sector001_macro`) into a human-readable sector name by deriving the language file ID and looking it up in the provided dictionary.

The ID formula is: `str(cluster_number * 10) + str(sector_number * 10 + 1).zfill(3)`. For example, `cluster_43_sector001_macro` produces ID `"430011"`.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `macro` | `str` | Raw macro string from the save XML `component` element. |
| `sector_names` | `dict` | Dictionary returned by `load_sector_names()`. |

**Returns** `str` with the display name, or `None` if the macro doesn't match the expected pattern.

---

### `resolve_sector_from_location(location_str, sector_names)`

```python
def resolve_sector_from_location(location_str: str, sector_names: dict) -> str
```

Resolves a sector name from the `{20004,XXXXX}` reference format used in the save file's `<info><player location="..."/>` attribute. This is only used for the player's current position shown at the top of the report; station sectors are resolved via `macro_to_sector_name()`.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `location_str` | `str` | Raw location string from the player element, e.g. `"{20004,270011}"`. |
| `sector_names` | `dict` | Dictionary returned by `load_sector_names()`. |

**Returns** `str` — the display name, a fallback `"Sector XXXXX"` string, or the original string if no match is found. Returns `"Unknown"` if the input is empty.

---

## 3. `scanner/scanner.py`

Performs Pass 1 (player identity, credits, and stations) and Pass 2 (faction reputation) over the save file. Uses `xml.etree.ElementTree.iterparse()` for memory-efficient streaming of large save files.

**Module-level constants**

| Constant | Type | Description |
|---|---|---|
| `STATION_CLASSES` | `set[str]` | XML `class` attribute values that identify player-buildable structures: `"station"`, `"factory"`, `"headquarters"`, `"complex"`. |
| `PROD_MACRO_RE` | `re.Pattern` | Pre-compiled regex matching production module macro names of the form `prod_<prefix>_<warename>_macro`. Group 1 captures the ware name. |

---

### `parse_production_from_construction(station_elem)`

```python
def parse_production_from_construction(station_elem: ET.Element) -> str
```

Reads the `<construction><sequence>` block of a station element and returns a comma-separated string of unique produced ware display names.

Each production module has an `<entry>` child whose `macro` attribute follows the pattern `prod_gen_WARENAME_macro`. The function extracts the ware name, deduplicates it (since stations often have multiple modules of the same type), looks it up in `WARE_NAMES`, and joins the results. The `<snapshot>` block is explicitly avoided to prevent duplicates from the historical state record.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `station_elem` | `ET.Element` | The `<component>` element for the station, with children still in memory. |

**Returns** `str` — comma-separated display names (e.g. `"Energy Cells, Hull Parts"`), or an empty string if no production modules are found.

---

### `scan_save(file_path, sector_names)`

```python
def scan_save(file_path: pathlib.Path, sector_names: dict) -> dict
```

Streams through the X4 save XML (Pass 1) and extracts player identity, credits, and all player-owned stations.

Uses `iterparse()` with `start` and `end` events to keep RAM usage low, calling `elem.clear()` after each processed element. Sector context is tracked as a running variable — whenever a `sector`-class component is seen, `current_sector` is updated, so any station encountered afterward inherits the correct location.

Station buffering is used to preserve child elements in memory: when a player station's opening tag is detected, `elem.clear()` is suppressed for all descendants until the station's closing tag arrives, at which point `parse_production_from_construction()` is called before clearing.

Station names are resolved in priority order: player-given name → HQ detection via macro → `nameindex` fallback → `"Unnamed Station"`.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `file_path` | `pathlib.Path` | Path to the unzipped save file. |
| `sector_names` | `dict` | Dictionary returned by `load_sector_names()`. |

**Returns** `dict` with keys: `player_name`, `player_credits`, `player_sector`, `stations` (list of station dicts), `reputation` (empty list, filled by Pass 2).

Each station dict contains: `name`, `code`, `class`, `macro`, `sector`, `production`.

---

### `scan_reputation(file_path)`

```python
def scan_reputation(file_path: pathlib.Path) -> list
```

Second pass over the save file. Extracts faction reputation standings from the `<faction id="player"><relations>` block.

Base `<relation>` entries represent permanent standing. `<booster>` entries are temporary mission bonuses. Both are extracted separately and reported alongside the combined total. Raw internal floats are converted to in-game display values using `scale_reputation()` from `data/factions.py`. Factions in `SKIP_FACTIONS` (internal/non-playable) are excluded. Results are sorted by total reputation descending.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `file_path` | `pathlib.Path` | Path to the unzipped save file. |

**Returns** `list[dict]`, each dict containing: `faction_id`, `faction_name`, `value` (scaled total), `base` (scaled permanent), `booster` (scaled temporary), `tier` (label string).

---

## 4. `scanner/ship_scanner.py`

Performs Pass 3: scans the player fleet and optionally NPC ships in sectors of interest. Imports `SHIP_NAMES` from `data/ships.py` for display name lookup.

**Module-level constants**

**Imports**

`SHIP_STATS` is imported from `data/ship_stats.py` and used during hull health calculation in `scan_ships()`.

**Module-level constants**

| Constant | Type | Description |
|---|---|---|
| `ROLE_PATTERNS` | `list[tuple[re.Pattern, str]]` | Ordered list of `(compiled_regex, label)` pairs matched against ship macro strings to derive a role display name. Order matters — more specific patterns (e.g. `miner_solid`) appear before broader ones (e.g. `miner`). |
| `SIZE_LABELS` | `dict[str, str]` | Maps ship class strings (`"ship_s"`, `"ship_m"`, `"ship_l"`, `"ship_xl"`) to display size labels (`"S"`, `"M"`, `"L"`, `"XL"`). |
| `ORDER_LABELS` | `dict[str, str]` | Maps internal order type strings (e.g. `"MiningRoutine"`, `"Middleman"`) to human-readable labels (e.g. `"Mining"`, `"Trading"`). |
| `LANG_STRING_RE` | `re.Pattern` | Compiled regex matching language reference strings of the form `{digits,digits}`. Used to detect and discard unresolved name placeholders in ship `name` attributes. |

---

### `extract_role(macro)`

```python
def extract_role(macro: str) -> str
```

Derives a display role string from a ship macro name by testing it against each pattern in `ROLE_PATTERNS` in order, returning the label of the first match. Returns `"Unknown"` if no pattern matches.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `macro` | `str` | Ship macro string, e.g. `"ship_tel_s_trans_container_01_b_macro"`. |

**Returns** `str` — role label, e.g. `"Freighter"`, `"Miner (Solid)"`, `"Fighter"`.

---

### `extract_faction_from_macro(macro)`

```python
def extract_faction_from_macro(macro: str) -> str
```

Extracts the hull origin faction from a ship macro name by reading the second underscore-separated token and looking it up in a local faction abbreviation map. Useful for identifying captured ships where the current `owner` differs from the hull's original faction.

For example, `"ship_xen_m_corvette_02_a_macro"` → `"Xenon"`.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `macro` | `str` | Ship macro string. |

**Returns** `str` — faction display name (e.g. `"Argon"`, `"Xenon"`, `"Kha'ak"`), or the raw token title-cased if not found in the map.

---

### `resolve_ship_type(macro)`

```python
def resolve_ship_type(macro: str) -> str | None
```

Looks up a ship's type display name (e.g. `"Magpie Sentinel"`) from the `SHIP_NAMES` dict in `data/ships.py` using the macro string as the key.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `macro` | `str` | Ship macro string. |

**Returns** `str` with the display name if found, or `None` if the macro is absent from the lookup (e.g. new DLC ships not yet regenerated).

---

### `_parse_hull(ship_elem)`

```python
def _parse_hull(ship_elem: ET.Element) -> float | None
```

Returns the ship's current hull HP as a float, or `None` if the ship is at full health.

X4 only writes a `<hull value="..."/>` child element when the ship's hull is below maximum. If the element is absent, the ship is undamaged and this function returns `None`. The caller then uses the absence of a value to set `hull_pct = 100.0` rather than computing it.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `ship_elem` | `ET.Element` | The buffered ship element with children in memory. |

**Returns** `float` with the raw HP value (e.g. `7152.237`), or `None` if the `<hull>` element is absent (full health).

---

### `_parse_sector_from_zone_macro(ship_elem, sector_names)`

```python
def _parse_sector_from_zone_macro(ship_elem: ET.Element, sector_names: dict) -> str
```

Resolves the sector name for a ship from its zone macro, which the main scanner stamps onto the element as a `_zone_macro` attribute before buffering begins. Strips the zone prefix to isolate the cluster/sector portion and passes it to `macro_to_sector_name()`.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `ship_elem` | `ET.Element` | The buffered ship element with `_zone_macro` set. |
| `sector_names` | `dict` | Dictionary returned by `load_sector_names()`. |

**Returns** `str` — resolved sector name, or `"Unknown Sector"` if the macro is absent or unrecognised.

---

### `_parse_pilot(ship_elem)`

```python
def _parse_pilot(ship_elem: ET.Element) -> dict
```

Finds the NPC assigned to the `aipilot` post in the ship's `<control>` block, then resolves their name and skill ratings by matching on component ID and NPC seed.

Pilot names stored as unresolved language reference strings (matching `LANG_STRING_RE`) are discarded; the function returns `{"name": None, "skills": {}}` for any ship without a named, resolved pilot.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `ship_elem` | `ET.Element` | The buffered ship element with children in memory. |

**Returns** `dict` with keys: `name` (`str` or `None`) and `skills` (`dict` with keys `piloting`, `management`, `morale`, `engineering`, each an `int`; empty dict if no pilot found).

---

### `_parse_current_order(ship_elem)`

```python
def _parse_current_order(ship_elem: ET.Element) -> str
```

Returns a human-readable label for the ship's current order by inspecting the `<orders>` block. Prefers the order with `state="started"` and `temp != "1"` (the active non-temporary order). Falls back to the default order if no started order is found, and to `"Idle"` if neither exists. Labels are resolved via `ORDER_LABELS`.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `ship_elem` | `ET.Element` | The buffered ship element. |

**Returns** `str` — order label, e.g. `"Mining"`, `"Trading"`, `"Idle"`.

---

### `_parse_commander(ship_elem)`

```python
def _parse_commander(ship_elem: ET.Element) -> str | None
```

Returns the component ID reference of this ship's commander by searching the `<connections>` block for a connection of type `"commander"`. Used to identify wing or fleet command relationships.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `ship_elem` | `ET.Element` | The buffered ship element. |

**Returns** `str` with the commander's connection reference, or `None` if the ship has no commander assigned.

---

### `_parse_software(ship_elem)`

```python
def _parse_software(ship_elem: ET.Element) -> list[str]
```

Returns a list of software ware IDs installed on the ship, read from the `wares` attribute of the `<software>` child element.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `ship_elem` | `ET.Element` | The buffered ship element. |

**Returns** `list[str]` — ware ID strings, or an empty list if no `<software>` element is present.

---

### `scan_ships(file_path, sector_names, station_sectors, ship_sectors)`

```python
def scan_ships(
    file_path: pathlib.Path,
    sector_names: dict,
    station_sectors: set[str] | None = None,
    ship_sectors: set[str] | None = None,
) -> dict
```

Streams the save file and collects player and optionally NPC ship data using `iterparse()`. The union of `station_sectors` and `ship_sectors` forms `context_sectors` — NPC ships are only recorded when their resolved sector is in this set.

Zone macro tracking runs as a separate state variable: whenever a `zone`-class component is opened, `current_zone_macro` is updated; this value is stamped onto each ship element before buffering so `_parse_sector_from_zone_macro()` can resolve it after the zone element has been cleared.

Ship name resolution follows a three-step priority: player-given custom name → `SHIP_NAMES` lookup by macro → `None` (display falls back to the ship code in `display.py`). Language reference strings in the `name` attribute are detected via `LANG_STRING_RE` and skipped.

Player ship entries include the full set of parsed fields. NPC ship entries contain a reduced set (no pilot, software, or commander).

**Parameters**

| Name | Type | Description |
|---|---|---|
| `file_path` | `pathlib.Path` | Path to the unzipped save file. |
| `sector_names` | `dict` | Dictionary returned by `load_sector_names()`. |
| `station_sectors` | `set[str] \| None` | Sector names where the player has stations; NPC ships here are included at tier 2. |
| `ship_sectors` | `set[str] \| None` | Sector names where the player has ships; NPC ships here are included at tier 3. |

**Returns** `dict` with keys:

- `player_ships` — list of dicts with keys: `code`, `name`, `class`, `size`, `macro`, `role`, `hull_origin`, `owner`, `sector`, `order`, `pilot`, `software`, `commander`, `hull_hp`, `hull_pct`, `max_hull`.
- `npc_ships` — list of dicts with keys: `code`, `class`, `size`, `macro`, `role`, `hull_origin`, `owner`, `sector`, `order`.

**Hull health fields** (player ships only)

| Key | Type | Description |
|---|---|---|
| `hull_hp` | `float \| None` | Raw current hull HP. `None` when undamaged (no `<hull>` element in save). |
| `hull_pct` | `float \| None` | Percentage of max hull remaining. `100.0` when undamaged; `None` when max hull is unknown (ship not in `SHIP_STATS`). Can exceed 100 if a hull capacity mod is installed — see `TO BE NOTED.txt`. |
| `max_hull` | `int \| None` | Base (unmodded) max hull HP from `SHIP_STATS`, or `None` if the macro is not in the lookup. |

---

### `summarise_player_fleet(player_ships)`

```python
def summarise_player_fleet(player_ships: list[dict]) -> dict
```

Returns a high-level summary of the player fleet grouped by role, order, and sector. Intended for display and AI export use.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `player_ships` | `list[dict]` | List of player ship dicts from `scan_ships()`. |

**Returns** `dict` with keys: `total` (int), `by_role` (dict), `by_order` (dict), `by_sector` (nested dict of `{ sector: { role: count } }`).

---

### `summarise_npc_presence(npc_ships)`

```python
def summarise_npc_presence(npc_ships: list[dict]) -> dict
```

Returns NPC ship counts grouped by sector and faction owner, useful for threat and activity assessment.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `npc_ships` | `list[dict]` | List of NPC ship dicts from `scan_ships()`. |

**Returns** `dict` of the form `{ sector: { owner: count } }`.

---

## 5. `display.py`

Formats the assembled `game_data` dictionary as a console report. Called by `x4_save_scanner.py` in both run modes.

---

### `format_credits(amount_str)`

```python
def format_credits(amount_str: str) -> str
```

Converts a raw credit integer string into a comma-separated display string with a `Cr` suffix. Returns the original value with `Cr` appended if conversion fails.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `amount_str` | `str` | Raw integer string as extracted from the save XML. |

**Returns** `str` — e.g. `"1,234,567 Cr"`.

---

### `display_results(data)`

```python
def display_results(data: dict)
```

Prints the full empire intelligence report to stdout. Accepts the `game_data` dict produced by the scanner pipeline.

The report contains five sections:

**Header** — pilot name, current sector, and credit balance.

**Stations** — grouped by sector using box-drawing characters. Each station shows its name, code, and produced wares. Multiple stations in the same sector are visually clustered under a single sector header.

**Faction Reputation** — tabular display of all tracked factions. Columns show the scaled total value, a 20-character visual bar (`█`/`░`), tier label, permanent base value, and temporary booster. Values match the in-game UI display range of −30 to +30.

**Player Fleet** — grouped by sector, matching the station layout style. Each ship shows display name (or code fallback), size, role, current order, hull origin, and hull health. Captured ships (hull origin not in the standard player-purchasable faction list) are flagged with a `★` prefix. Hull health is shown as `Full (N HP)` for undamaged ships, `PCT% (current / max HP)` for damaged ships, or raw HP if the max is not in `SHIP_STATS`. A pilot sub-line is printed only when a named pilot is assigned. Column width for ship names is computed dynamically and capped at 40 characters.

**NPC Presence** (tiers 2 and 3 only) — printed only when `npc_ships` is non-empty. Groups NPC ships by sector and faction, summarising composition as role counts (e.g. `3× Fighter, 1× Corvette`). Gives a threat picture without listing individual NPC ships.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `data` | `dict` | The assembled game data dict. Expected keys: `player_name`, `player_sector`, `player_credits`, `stations`, `reputation`, `ships` (containing `player_ships` and `npc_ships`). |

---

## 6. `export/jsonexport.py`

Builds and writes the structured JSON output file (`x4_empire_state.json`) used for AI prompt input and the desktop UI.

---

### `_build_fleet_summary(player_ships)`

```python
def _build_fleet_summary(player_ships: list[dict]) -> dict
```

Produces a pre-digested summary of the player fleet for inclusion in the JSON export. Intended to give an AI assistant a quick overview without requiring it to count individual ships.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `player_ships` | `list[dict]` | List of player ship dicts from `scan_ships()`. |

**Returns** `dict` with keys: `total` (int), `by_role` (dict), `by_size` (dict), `by_order` (dict), `by_sector` (nested dict of `{ sector: { role: count } }`).

---

### `_build_npc_summary(npc_ships)`

```python
def _build_npc_summary(npc_ships: list[dict]) -> dict
```

Produces a sector-level summary of NPC ship presence, grouped by sector, then faction, then role counts.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `npc_ships` | `list[dict]` | List of NPC ship dicts from `scan_ships()`. |

**Returns** `dict` of the form `{ sector: { faction: { role: count } } }`.

---

### `export_json(data, output_dir)`

```python
def export_json(data: dict, output_dir: pathlib.Path | None = None)
```

Writes all extracted game data to `x4_empire_state.json` in a structured format ready for AI prompting or UI display.

By default writes to the project root (the parent of the `export/` package directory). Pass `output_dir` to override. Calls `_build_fleet_summary()` and `_build_npc_summary()` internally.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `data` | `dict` | The assembled game data dict from the scanner pipeline. |
| `output_dir` | `pathlib.Path \| None` | Directory to write the JSON file into. Defaults to the project root. |

**Output JSON structure**

```
player_name
player_sector
player_credits
stations          (list)
reputation        (list)
ships
  ├── player_ships   (list)
  ├── fleet_summary  (dict)
  ├── npc_ships      (list)
  └── npc_summary    (dict)
```

---

## 7. `ui/main_ui.py`

PyQt6 desktop UI. Loads `x4_empire_state.json` and renders the HTML dashboard (`ui/ui.html`) in a native window using `QWebEngineView`. Empire data is passed from Python to JavaScript via a `QWebChannel` bridge.

---

### Class: `EmpireBridge`

```python
class EmpireBridge(QObject)
```

Python-to-JavaScript bridge object, registered with `QWebChannel` and exposed to the frontend as `window.bridge`. Add further `@pyqtSlot` methods here as the UI grows.

**Constructor**

```python
def __init__(self, data: dict)
```

| Parameter | Type | Description |
|---|---|---|
| `data` | `dict` | The loaded empire state dictionary. |

**Methods**

`get_empire_data() -> str`
Slot callable from JavaScript. Returns the full empire state as a JSON string via `json.dumps()`.

---

### Class: `EmpireWindow`

```python
class EmpireWindow(QMainWindow)
```

The main application window. Sets up the `QWebEngineView`, registers the `EmpireBridge` with a `QWebChannel`, and loads `ui.html` from the local filesystem.

Default size is 1200×800 with a minimum of 900×600.

**Constructor**

```python
def __init__(self, data: dict, html_path: str)
```

| Parameter | Type | Description |
|---|---|---|
| `data` | `dict` | The loaded empire state dictionary, passed to `EmpireBridge`. |
| `html_path` | `str` | Absolute path to `ui/ui.html`. |

---

### `load_json(path)`

```python
def load_json(path: str) -> dict
```

Loads and parses a JSON file. Exits with code 1 if the file is not found.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `path` | `str` | Path to the JSON file. |

**Returns** `dict` — parsed JSON content.

---

### `main()`

```python
def main()
```

Entry point for the UI. Parses the `--json` command-line argument (defaulting to `<project_root>/x4_empire_state.json`), loads the empire data, resolves the path to `ui.html`, and launches the Qt application.

**CLI argument**

`--json <path>` — optional path to an empire state JSON file.

---

### `ui/ui.html` — JavaScript helpers

The HTML dashboard contains a set of JavaScript helper functions that transform raw JSON values into rendered HTML. The most relevant for ship data are listed below.

---

#### `hullBadge(hullOrigin)`

Returns an HTML `<span>` chip coloured by hull origin faction, used to label the manufacturer of each ship in the fleet table. Captured ships (origin not in the standard faction set) receive a distinct warning colour.

---

#### `hullBar(pct, hullHp, maxHull)`

Returns an HTML fragment containing a gradient health bar and a numeric label beneath it.

- Bar colour transitions from red (hue 0°) at 0% health to green (hue 120°) at 100% health using an HSL colour string computed as `hsl(pct * 1.2, 100%, 42%)`.
- Values above 100% (hull capacity mod installed) are rendered in blue (`#388bfd`) to distinguish them from normal health.
- If `pct` is `null` (ship not in `SHIP_STATS`), only the raw HP is shown without a bar.
- The label beneath the bar shows `Full (N HP)` when undamaged, `N% (current / max HP)` when damaged, or just raw HP when the max is unknown.

---

## 8. `data/factions.py`

Static lookup tables and scaling functions for faction data. Imported by `scanner/scanner.py`.

**Module-level constants**

| Constant | Type | Description |
|---|---|---|
| `FACTION_NAMES` | `dict[str, str]` | Maps internal faction ID strings to formatted display names including faction code prefixes, e.g. `"argon"` → `"[ARG] Argon Federation"`. Covers all base game and DLC factions. |
| `SKIP_FACTIONS` | `set[str]` | Internal or non-playable faction IDs excluded from the reputation report, e.g. `"criminal"`, `"civilian"`, `"player"`. |

---

### `scale_reputation(raw)`

```python
def scale_reputation(raw: float) -> float
```

Converts X4's internal reputation float to the in-game display scale using a log10 curve, clamped to the range −30 to +30. Negative raw values are mirrored symmetrically. A raw value of `0.0` returns `−30.0`.

The formula is: `display = log10(raw) * 10 + 30`, clamped to `[−30, 30]`.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `raw` | `float` | Internal reputation value as stored in the save file (e.g. `0.0032`). |

**Returns** `float` — scaled display value in the range `[−30.0, 30.0]`.

---

### `reputation_label(scaled_value)`

```python
def reputation_label(scaled_value: float) -> str
```

Returns a descriptive tier label for a scaled reputation value. Thresholds are approximate.

| Range | Label |
|---|---|
| ≥ 20 | `"Allied"` |
| ≥ 10 | `"Friendly"` |
| ≥ 0 | `"Neutral"` |
| ≥ −10 | `"Hostile"` |
| < −10 | `"At War"` |

**Parameters**

| Name | Type | Description |
|---|---|---|
| `scaled_value` | `float` | Scaled reputation value from `scale_reputation()`. |

**Returns** `str` — tier label.

---

## 9. `data/wares.py`

Static lookup table mapping production ware IDs to display names. Imported by `scanner/scanner.py`.

**Module-level constants**

| Constant | Type | Description |
|---|---|---|
| `WARE_NAMES` | `dict[str, str]` | Maps lowercase ware ID strings extracted from production module macros to human-readable display names, e.g. `"energycells"` → `"Energy Cells"`. Covers raw resources, refined materials, ship/station components, and food/consumables. If a ware ID is not present, callers fall back to title-casing with underscores replaced by spaces. |

---

### `format_wares(overviewgraphs)` *(Legacy)*

```python
def format_wares(overviewgraphs: str) -> str
```

**No longer called by the main scanner.** Previously converted the `overviewgraphs` station XML attribute into a readable ware list. Replaced by `parse_production_from_construction()` in `scanner.py`, which reads directly from `<construction><sequence>` entries and is more reliable. Retained for debugging reference.

---

## 10. `data/ships.py`

Auto-generated static lookup table mapping ship macro names to display names. Not edited by hand.

**Module-level constants**

| Constant | Type | Description |
|---|---|---|
| `SHIP_NAMES` | `dict[str, str]` | Maps ship macro name strings to in-game display names, e.g. `"ship_tel_s_trans_container_01_b_macro"` → `"Magpie Sentinel"`. Generated by `Legacy/generate_ship_names.py`. Covers base game and all DLC factions. |

This file is committed to the repository. It only needs to be regenerated when new ships are added by a game update or DLC. See `Legacy/generate_ship_names.py` for the generation process.

---

## 11. `data/ship_stats.py`

Auto-generated static lookup table mapping ship macro names to per-ship stats (currently hull HP). Not edited by hand — regenerated by `generate_ship_stats.py` whenever ship XMLs are updated.

**Module-level constants**

| Constant | Type | Description |
|---|---|---|
| `SHIP_STATS` | `dict[str, dict]` | Maps ship macro name strings to a nested dict of stats. Currently each entry contains only `max_hull`. Example: `"ship_arg_l_destroyer_01_a_macro": {"max_hull": 93000}`. |

The dict is structured as `SHIP_STATS[macro]["stat_name"]` so that additional stats (e.g. cargo capacity, max speed) can be added in future without changing the key structure.

This file is committed to the repository. It only needs to be regenerated when ship XMLs change (new DLC, game patch). See `generate_ship_stats.py` for the generation process.

---

## 12. `generate_ship_stats.py`

One-time utility script that generates `data/ship_stats.py` by walking all ship macro XMLs in the `ship xml/` folder. Run from the project root after adding or updating ship XML files.

**Required inputs**

- `ship xml/` — folder of ship macro XMLs in the project root. XML files can be extracted from the game's `.cat` files using XRCatTool.

**Module-level constants**

| Constant | Type | Description |
|---|---|---|
| `SCRIPT_DIR` | `Path` | Project root, derived from `__file__`. |
| `XML_DIR` | `Path` | Expected location of ship macro XMLs (`ship xml/`). |
| `OUTPUT_FILE` | `Path` | Write target for the generated file (`data/ship_stats.py`). |
| `SHIP_CLASSES` | `set[str]` | XML `class` attribute values that identify whole-ship macros: `"ship_s"`, `"ship_m"`, `"ship_l"`, `"ship_xl"`. Entries with other classes (drones, spacesuit frames, turret hardpoints) are skipped. |

---

### `extract_hull_max(xml_path)`

```python
def extract_hull_max(xml_path: pathlib.Path) -> tuple[str, int] | None
```

Parses a single ship macro XML file and returns the macro name and base max hull HP.

The function reads the top-level `<macro>` element for its `name` and `class` attributes. Files whose class is not in `SHIP_CLASSES` are rejected immediately. The hull value is read from `<properties><hull max="..."/>`.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `xml_path` | `pathlib.Path` | Path to a single ship macro XML file. |

**Returns** `tuple[str, int]` — `(macro_name, max_hull_int)` if extraction succeeds, or `None` if the file should be skipped (wrong class, malformed XML, missing hull element).

---

### `main()` *(generate_ship_stats)*

```python
def main()
```

Walks every `.xml` file in `XML_DIR`, calls `extract_hull_max()` on each, accumulates results, and writes the `data/ship_stats.py` file. Prints a summary line showing how many ships were extracted and how many were skipped.

The output file is sorted alphabetically by macro name and prefixed with a header comment warning that it is auto-generated and should not be edited by hand.

---

## 13. `Legacy/generate_ship_names.py`

One-time utility script that generates `data/ships.py` from the game's extracted macro XML files and language file. Run from the project root after extracting ship macros from the game's `.cat` files using XRCatTool.

**Required inputs**

- `extracted/` — folder of ship macro XMLs extracted from `.cat` files. Expected path structure: `extracted/assets/units/size_*/macros/ship_*_macro.xml`.
- `0001-l044.xml` — X4 English language file, in the project root.

**Module-level constants**

| Constant | Type | Description |
|---|---|---|
| `SCRIPT_DIR` | `Path` | Project root, derived from `__file__`. |
| `EXTRACTED_DIR` | `Path` | Expected location of extracted ship macro XMLs. |
| `LANG_FILE` | `Path` | Expected location of the language file. |
| `OUTPUT_FILE` | `Path` | Write target for the generated file (`data/ships.py`). |
| `BASE_REF_RE` | `re.Pattern` | Pre-compiled regex matching page 20101 language references, e.g. `{20101,22601}`. Group 1 captures the numeric ID. |
| `VAR_REF_RE` | `re.Pattern` | Pre-compiled regex matching page 20111 variant token references, e.g. `{20111,1101}`. Group 1 captures the numeric ID. |
| `HEADER` | `str` | File header comment block and opening of the `SHIP_NAMES` dict written to the output file. |
| `FOOTER` | `str` | Closing brace written to the output file. |

---

### `clean_text(text)`

```python
def clean_text(text: str) -> str
```

Strips backslash-escaped parentheses from language file text, converting `\(` and `\)` to `(` and `)`.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `text` | `str` | Raw text string from the language file. |

**Returns** `str` — cleaned text.

---

### `load_language_tables(lang_path)`

```python
def load_language_tables(lang_path: pathlib.Path) -> tuple[dict, dict]
```

Parses the language file and returns two lookup dictionaries used by `build_macro_to_name()`.

Reads page `20101` for ship base names and full pre-composed names, and page `20111` for variant suffix tokens (e.g. `"Vanguard"`, `"(Gas)"`). Handles three entry formats on page 20101: plain base names, plain full names, and parenthesised pre-composed entries (e.g. `"(Chthonios E \(Gas\))"`). Strips pronunciation annotations from plain entries.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `lang_path` | `pathlib.Path` | Path to `0001-l044.xml`. |

**Returns** `tuple[dict, dict]` — `(ship_names, variations)` where `ship_names` maps page-20101 ID strings to display names, and `variations` maps page-20111 ID strings to variant tokens.

---

### `build_macro_to_name(extracted_dir, ship_names, variations)`

```python
def build_macro_to_name(
    extracted_dir: pathlib.Path,
    ship_names: dict,
    variations: dict,
) -> dict
```

Walks all `ship_*_macro.xml` files under `extracted_dir` and builds a dict mapping macro names to display names.

Two XML identification structures are handled:

**Structure A** (most standard ships) — `<identification basename="{20101,XXXX}" variation="{20111,YYYY} ..."/>`. The basename is looked up in `ship_names`, variation tokens are looked up in `variations`, and the parts are joined with spaces: e.g. `"Magnetar"` + `"(Gas)"` + `"Vanguard"` → `"Magnetar (Gas) Vanguard"`.

**Structure B** (Xenon ships, E-variants, older ships) — `<identification name="{20101,XXXX}"/>`. The full pre-composed name is looked up directly in `ship_names`.

Structure A is tried first; Structure B is the fallback. Ships with neither structure (drones, spacesuits, NPC vessels) are counted and skipped. Unresolvable macros are logged.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `extracted_dir` | `pathlib.Path` | Root directory containing extracted ship macro XML files. |
| `ship_names` | `dict` | Base name lookup from `load_language_tables()`. |
| `variations` | `dict` | Variant token lookup from `load_language_tables()`. |

**Returns** `dict[str, str]` — maps macro name strings to display name strings.

---

### `write_ships_py(mapping, output_path)`

```python
def write_ships_py(mapping: dict, output_path: pathlib.Path)
```

Writes the macro-to-display-name mapping to `data/ships.py` as a Python source file containing a `SHIP_NAMES` dict. Entries are sorted alphabetically by macro name. Single quotes within display names are backslash-escaped. Creates the output directory if it does not exist.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `mapping` | `dict` | Dict returned by `build_macro_to_name()`. |
| `output_path` | `pathlib.Path` | Destination path for the generated Python file. |
