# X4 Foresight — Code Reference

A complete reference for all modules, classes, and functions in the X4 Foresight: Empire Intelligence project.

---

## Table of Contents

1. [🚀 Entry Points](#1-entry-points)
   1. [⌨️ x4_save_scanner.py](#x4_save_scannerpy)
   2. [🪟 X4_Empire_Intelligence.pyw](#x4_empire_intelligencepyw)
2. [🌐 scanner/language.py](#2-scannerlanguagepy)
3. [🔍 scanner/scanner.py](#3-scannerscannerpy)
   1. [🏗️ scanner/station_scanner.py](#scannerstation_scannerpy)
   2. [⭐ scanner/reputation_scanner.py](#scannerreputation_scannerpy)
   3. [👥 scanner/crew_scanner.py](#scannercrew_scannerpy)
4. [🚢 scanner/ship_scanner.py](#4-scannership_scannerpy)
5. [📊 display.py](#5-displaypy)
6. [📤 export/jsonexport.py](#6-exportjsonexportpy)
7. [🖥️ ui/main_ui.py](#7-uimain_uipy)
8. [⚔️ data/factions.py](#8-datafactionspy)
9. [📦 data/wares.py](#9-datawarespy)
10. [📋 data/ships.py](#10-datashipspy)
11. [📈 data/ship_stats.py](#11-dataship_statspy)
12. [🛡️ data/station_stats.py](#12-datastation_statspy)
13. [🔧 generate_ship_stats.py](#13-generate_ship_statspy)
14. [🏗️ generate_station_stats.py](#14-generate_station_statspy)
15. [🗂️ generate_ship_names.py](#15-generate_ship_namespy)

---

<a id="1-entry-points"></a>
## 🚀 1. Entry Points

### `x4_save_scanner.py`

The main entry point for the scanner pipeline. Run this directly from the project root.

**Module-level constants**

| Constant | Type | Description |
|---|---|---|
| `SCRIPT_DIR` | `Path` | Absolute path to the project root, derived from `__file__`. |
| `LANG_FILE` | `Path` | Expected location of the X4 English language file (`0001-l044.xml`). |
| `SCAN_MODES` | `list[dict]` | Registry of available scan modes. Each entry declares a `key`, `label`, `desc`, `passes` (list of pass names to run), and `export` (whether to write JSON). Add new modes here — the selector and dispatcher pick them up automatically. |

**Interactive selectors**

| Function | Description |
|---|---|
| `select_save_file()` | Lists available saves from `~/Documents/Egosoft/X4/<id>/save/` with timestamps. Accepts a number (`1–N`), `L` for latest, or `R` for the `save_001.xml` root fallback. Exits with code 1 if no saves are found. |
| `select_mode()` | Presents the `SCAN_MODES` menu and returns the chosen mode dict. |
| `select_ship_tier(stations_active)` | Prompts for ship scan tier (1–3). Tier 2 is only offered when the stations pass is also running, since it needs station sector data. |

**Execution flow**

On launch the script runs interactively: `select_save_file()` → `select_mode()` → `select_ship_tier()` (if ships pass is selected). The chosen save path and mode are passed to all subsequent calls.

The script then runs whichever passes the chosen mode declares, in order:

1. `load_sector_names()` — always runs; loads the language file for human-readable sector names.
2. `_run_stations_pass()` — Pass 1 (if `"stations"` in mode passes): player identity, credits, stations.
3. `_run_reputation_pass()` — Pass 2 (if `"reputation"` in mode passes): faction standings.
4. `_run_ships_pass()` — Pass 3 (if `"ships"` in mode passes): fleet and optionally NPC ships.
5. `display_results()` — prints the console report regardless of which passes ran.
6. `export_json()` — writes `x4_empire_state.json` only if the mode's `export` flag is set.

A `game_data` stub is initialised with empty values for all keys before any passes run, so `display_results()` always receives a complete dict and can display "not selected" messages for skipped passes.

---

### `X4_Empire_Intelligence.pyw`

Windows double-click launcher. Equivalent to running `python ui/main_ui.py` but suppresses the console window via the `.pyw` extension. Contains no logic beyond launching the UI entry point.

---

<a id="2-scannerlanguagepy"></a>
## 🌐 2. `scanner/language.py`

Handles parsing the X4 English language file (`0001-l044.xml`) to resolve human-readable names for sectors and ships. All other modules that need sector names call into this one.

---

### `open_save(path)`

```python
def open_save(path: pathlib.Path)
```

Context manager that opens either `.xml` or `.xml.gz` save files in binary mode. Scanner passes use this so callers do not need separate handling for compressed and uncompressed saves.

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

<a id="3-scannerscannerpy"></a>
## 🔍 3. `scanner/scanner.py`

Thin coordinator module. Re-exports the public scanner functions from their sub-modules so callers can import from a single namespace without needing to know which sub-module each function lives in.

| Re-export | Source module |
|---|---|
| `scan_save` | `scanner.station_scanner` |
| `scan_reputation` | `scanner.reputation_scanner` |

`scan_ships` is imported directly from `scanner.ship_scanner` by callers — its richer signature (tier flags, `npc_only`) does not fit a simple re-export pattern.

---

### scanner/station_scanner.py

Pass 1 scanner. Streams the save XML and extracts player identity, credits, sector location, and all owned stations with their production, health, and manager data. Uses `lxml.etree.iterparse()` for memory-efficient streaming of 700 MB+ files.

### ⚙️ Module Constants

| Constant | Type | Description |
|---|---|---|
| `STATION_CLASSES` | `set[str]` | XML `class` attribute values that identify player-buildable structures: `"station"`, `"factory"`, `"headquarters"`, `"complex"`. |
| `PROD_MACRO_RE` | `re.Pattern` | Pre-compiled regex matching production module macro names of the form `prod_<prefix>_<warename>_macro`. Group 1 captures the ware name. |
| `_STATE_LABELS` | `dict[str, str]` | Maps station state attributes such as `"construction"` and `"wreck"` to display labels. Missing state means `"Operational"`. |
| `_MODULE_CATEGORIES` | `dict[str, str]` | Decodes station module macro category prefixes into display categories. |
| `_MODULE_FACTIONS` | `dict[str, str \| None]` | Decodes module designer/faction tokens such as `arg`, `tel`, `ter`, and `gen`. |
| `_SIZE_TOKENS` | `set[str]` | Valid module size tokens (`s`, `m`, `l`, `xl`) used while parsing macro names. |

---

### 🔧 Internal Helpers

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

### `_count_construction_modules(station_elem)`

```python
def _count_construction_modules(station_elem: ET.Element) -> int
```

Counts all entries in `<construction><sequence>`, including production, storage, dock, pier, defence, shield, habitat, and connector modules. This is the planned module count, not just the subset with known health stats.

---

### `_extract_station_docked_ships(station_elem)`

```python
def _extract_station_docked_ships(station_elem: ET.Element) -> list[dict]
```

Returns ships physically docked inside a station subtree (`connection="dock"`), including ships under construction. These entries feed the station `docked_ships` field and are later used by `merge_station_docked_ships()` to recover player ships missed by the streaming ship pass.

Each returned dict contains: `code`, `macro`, `owner`, `class`, `under_construction`.

---

### `_parse_module_info(macro)`

```python
def _parse_module_info(macro: str) -> dict
```

Decodes a station module macro into `category`, `faction`, and `size` fields for UI-friendly module details.

---

### `_parse_station_modules(station_elem)`

```python
def _parse_station_modules(station_elem: ET.Element) -> list[dict]
```

Walks the buffered station subtree via `_iter_components()` and returns one record per structural module or shield generator found in `STATION_STATS`. Modules include display metadata plus hull or shield values, with missing `<hull>`/`<shield>` elements treated as full health.

Each module dict includes: `macro`, `display_name`, `category`, `faction`, `size`, `produces`, `is_shield`, `hull_hp`, `hull_max`, `hull_pct`, `shield_hp`, `shield_max`, `shield_pct`.

---

### `_classify_reservation(flags)`

```python
def _classify_reservation(flags: str) -> str
```

Classifies trade reservation flags as `"buy"`, `"sell"`, or `"ignore"` so station cargo fill can match the in-game UI. Incoming reservations add adjusted fill; outgoing committed goods subtract adjusted fill; virtual sell offers are ignored.

---

### `_parse_station_storage(station_elem)`

```python
def _parse_station_storage(station_elem: ET.Element) -> dict
```

Computes station cargo usage from instantiated storage module cargo, converting ware amounts to cubic metres with `WARE_VOLUME`. It reports physical and reservation-adjusted fill for container, solid, liquid, and total storage. Transport type for reservation adjustment comes from `WARE_TRANSPORT`.

Returned keys include `cargo_container_m3`, `cargo_container_max`, `cargo_container_pct`, `cargo_container_adj_m3`, `cargo_container_adj_pct`, equivalent solid/liquid keys, and total `cargo_m3`, `cargo_max`, `cargo_pct`, `cargo_adj_m3`, `cargo_adj_pct`.

---

### `_parse_station_health(modules)`

```python
def _parse_station_health(modules: list[dict]) -> dict
```

Folds the module list from `_parse_station_modules()` into station-level hull and shield totals.

**Returns** `dict` with keys: `hull_hp`, `hull_max`, `hull_pct`, `shield_hp`, `shield_max`, `shield_pct`.

---

### 📡 Public API

### `scan_save(file_path, sector_names)`

```python
def scan_save(file_path: pathlib.Path, sector_names: dict) -> dict
```

Streams through the X4 save XML (Pass 1) and extracts player identity, credits, and all player-owned stations.

Uses `iterparse()` with `start` and `end` events to keep RAM usage low, calling `elem.clear()` after each processed element. Sector context is tracked as a running variable — whenever a `sector`-class component is seen, `current_sector` is updated, so any station encountered afterward inherits the correct location.

Station buffering is used to preserve child elements in memory: when a player station's opening tag is detected, `elem.clear()` is suppressed for all descendants until the station's closing tag arrives, at which point production, module count, module details, health, storage, docked ships, and manager data are parsed before clearing.

Station names are resolved in priority order: player-given name → HQ detection via macro → `nameindex` fallback → `"Unnamed Station"`.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `file_path` | `pathlib.Path` | Path to the save file (`.xml` or `.xml.gz`). |
| `sector_names` | `dict` | Dictionary returned by `load_sector_names()`. |

**Returns** `dict` with keys: `player_name`, `player_credits`, `player_sector`, `stations` (list of station dicts), `reputation` (empty list, filled by Pass 2), `managers` (list of manager crew dicts).

Each station dict contains: `name`, `code`, `class`, `macro`, `sector`, `status`, `production`, `module_count`, `docked_ships`, hull/shield fields, cargo fields, and `modules`.

---

### scanner/reputation_scanner.py

Pass 2 scanner. Streams the save XML and extracts faction reputation standings from the player faction's `<relations>` block.

### `scan_reputation(file_path)`

```python
def scan_reputation(file_path: pathlib.Path) -> list
```

Second pass over the save file. Extracts faction reputation standings from the `<faction id="player"><relations>` block.

Base `<relation>` entries represent permanent standing. `<booster>` entries are temporary mission bonuses. Both are extracted separately and reported alongside the combined total. Raw internal floats are converted to in-game display values using `scale_reputation()` from `data/factions.py`. Factions in `SKIP_FACTIONS` (internal/non-playable) are excluded. Results are sorted by total reputation descending.

The pass breaks out of the parse loop immediately after the player faction's closing `</faction>` tag — it does not scan the rest of the file.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `file_path` | `pathlib.Path` | Path to the save file (`.xml` or `.xml.gz`). |

**Returns** `list[dict]`, each dict containing: `faction_id`, `faction_name`, `value` (scaled total), `base` (scaled permanent), `booster` (scaled temporary), `tier` (label string).

---

### scanner/crew_scanner.py

Shared NPC parsing utilities used by both `station_scanner.py` and `ship_scanner.py`. Contains no public scanner pass — all functions are internal helpers imported directly by the pass modules.

### ⚙️ Module Constants

| Constant | Type | Description |
|---|---|---|
| `LANG_STRING_RE` | `re.Pattern` | Compiled regex matching language reference strings of the form `{digits,digits}`. Used to detect and discard unresolved name placeholders in NPC `name` attributes. |

---

### 🔧 Helpers

### `_parse_character_macro(macro)`

```python
def _parse_character_macro(macro: str) -> dict
```

Extracts appearance metadata from a character macro string. X4 character macros encode faction, gender, ethnicity, role, and variant in their name segments (e.g. `character_arg_male_cau_pilot_01_macro`).

**Parameters**

| Name | Type | Description |
|---|---|---|
| `macro` | `str` | Character macro string from the save XML. |

**Returns** `dict` with keys: `faction`, `gender`, `ethnicity`, `variant` — each a `str` or `None` if not encoded in the macro.

---

### `_parse_pilot(ship_elem)`

```python
def _parse_pilot(ship_elem: ET.Element) -> dict
```

Finds the NPC assigned to the `aipilot` post in the ship's `<control>` block, then resolves their name and skill ratings by matching the post's component ID against NPC elements in the ship subtree.

Pilot names stored as unresolved language reference strings (matching `LANG_STRING_RE`) are discarded; the function returns `{"name": None, "skills": {}}` for any ship without a named, resolved pilot.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `ship_elem` | `ET.Element` | The buffered ship element with children in memory. |

**Returns** `dict` with keys: `name` (`str` or `None`) and `skills` (`dict` with keys `piloting`, `management`, `morale`, `engineering`, `boarding`, each an `int`; empty dict if no pilot found).

---

### `_extract_people(ship_elem, ship_name, ship_code, ship_sector)`

```python
def _extract_people(
    ship_elem:   ET.Element,
    ship_name:   str,
    ship_code:   str,
    ship_sector: str,
) -> list[dict]
```

Extracts service crew and marines from the `<people>` block of a player ship. These are stored as `<person>` elements with a seed child rather than as full NPC components — placeholder names (`"Service Crew #N"`, `"Marine #N"`) are assigned since decoding the seed requires game runtime tables that are not available.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `ship_elem` | `ET.Element` | The buffered ship element. |
| `ship_name` | `str` | Display name of the ship (used as `assigned_to`). |
| `ship_code` | `str` | Ship code identifier (used as `assigned_code`). |
| `ship_sector` | `str` | Resolved sector name where the ship is located. |

**Returns** `list[dict]`, each dict containing: `name`, `role`, `skills`, `assigned_to`, `assigned_code`, `assigned_type` (`"ship"`), `sector`, `faction`, `gender`, `ethnicity`, `variant`, `seed`.

---

### `_parse_manager(station_elem)`

```python
def _parse_manager(station_elem: ET.Element) -> dict | None
```

Finds the station's assigned manager NPC and returns their name and skills. Managers are stored via `<control><post id="manager" component="[0xABC]"/>` pointing to a `<component class="npc">` element in the station subtree.

Called by `station_scanner.scan_save()` after a station element is fully buffered.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `station_elem` | `ET.Element` | The buffered station element with children in memory. |

**Returns** `dict` with keys `name` (`str`) and `skills` (`dict`), or `None` if the manager slot is vacant or the name is an unresolved language reference.

---

<a id="4-scannership_scannerpy"></a>
## 🚢 4. `scanner/ship_scanner.py`

Performs Pass 3: scans the player fleet and optionally NPC ships in sectors of interest. Imports `SHIP_NAMES` from `data/ships.py` for display name lookup.

### ⚙️ Module Constants

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

### 🔡 Name & Role Resolution

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
def resolve_ship_type(macro: str) -> str
```

Returns a ship type display name. Resolution priority is exact lookup in `SHIP_NAMES`, then a macro-derived fallback of faction, size, role, and optional variant.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `macro` | `str` | Ship macro string. |

**Returns** `str` — always a non-`None` display string. Unknown or new macros fall back to a constructed name, or the raw macro if it is too short to parse.

---

### 🔬 Element Parsers

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

### `_parse_sector(ship_elem, sector_names)`

```python
def _parse_sector(ship_elem: ET.Element, sector_names: dict) -> str
```

Resolves the sector name for a ship. It first checks `_sector_macro`, stamped from the enclosing sector component, which handles X4's dynamic `tempzone` elements. If that fails, it falls back to `_zone_macro`, strips the `zoneN_` prefix, and resolves the remaining sector macro.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `ship_elem` | `ET.Element` | The buffered ship element with `_sector_macro` and/or `_zone_macro` set. |
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

### `_parse_shield(ship_elem)`

```python
def _parse_shield(ship_elem: ET.Element) -> dict
```

Sums installed shield generator capacity for a player ship or docked carrier child. Shield generator stats come from `STATION_STATS`; missing `<shield>` elements are treated as full capacity.

**Returns** `dict` with keys: `shield_hp`, `shield_max`, `shield_pct`, all `None` when no known shield generators are present.

---

### `_extract_docked_ships(carrier_elem, carrier_sector, owner)`

```python
def _extract_docked_ships(
    carrier_elem: ET.Element,
    carrier_sector: str,
    owner: str,
) -> list[dict]
```

Extracts ships nested inside a fully buffered carrier or large ship subtree. Docked ships inherit the carrier sector and are returned with the same player ship shape, including pilot, software, commander, hull, and shield fields when available.

---

### 📡 Public API

### `scan_ships(file_path, sector_names, station_sectors, ship_sectors, npc_only)`

```python
def scan_ships(
    file_path: pathlib.Path,
    sector_names: dict,
    station_sectors: set[str] | None = None,
    ship_sectors: set[str] | None = None,
    npc_only: bool = False,
) -> dict
```

Streams the save file and collects player and optionally NPC ship data using `iterparse()`. The union of `station_sectors` and `ship_sectors` forms `context_sectors` — NPC ships are only recorded when their resolved sector is in this set.

Sector and zone macro tracking run as separate state variables. Both markers are stamped onto each ship element before buffering so `_parse_sector()` can resolve location after parent elements have been cleared.

Ship name resolution follows this priority: player-given custom name → `SHIP_NAMES` lookup by macro → macro-derived fallback. Language reference strings in the `name` attribute are detected via `LANG_STRING_RE` and skipped.

Player ship entries include the full set of parsed fields and crew extraction. NPC ship entries contain a reduced set (no pilot, software, commander, hull, or shield parsing).

**Parameters**

| Name | Type | Description |
|---|---|---|
| `file_path` | `pathlib.Path` | Path to the save file (`.xml` or `.xml.gz`). |
| `sector_names` | `dict` | Dictionary returned by `load_sector_names()`. |
| `station_sectors` | `set[str] \| None` | Sector names where the player has stations; NPC ships here are included at tier 2. |
| `ship_sectors` | `set[str] \| None` | Sector names where the player has ships; NPC ships here are included at tier 3. |
| `npc_only` | `bool` | When true, skips buffering player ships. Used by the tier 3 CLI flow after a pre-scan has already collected player ships. |

**Returns** `dict` with keys:

- `player_ships` — list of dicts with keys: `code`, `name`, `class`, `size`, `macro`, `role`, `hull_origin`, `owner`, `sector`, `order`, `pilot`, `software`, `commander`, `hull_hp`, `hull_pct`, `max_hull`, `shield_hp`, `shield_max`, `shield_pct`.
- `npc_ships` — list of dicts with keys: `code`, `name`, `class`, `size`, `macro`, `role`, `hull_origin`, `owner`, `sector`, `order`.
- `crew` — player ship pilot, service crew, and marine roster entries.

**Hull health fields** (player ships only)

| Key | Type | Description |
|---|---|---|
| `hull_hp` | `float \| None` | Raw current hull HP. `None` when undamaged (no `<hull>` element in save). |
| `hull_pct` | `float \| None` | Percentage of max hull remaining. `100.0` when undamaged; `None` when max hull is unknown (ship not in `SHIP_STATS`). Can exceed 100 if a hull capacity mod is installed — see `TO BE NOTED.txt`. |
| `max_hull` | `int \| None` | Base (unmodded) max hull HP from `SHIP_STATS`, or `None` if the macro is not in the lookup. |

---

### `merge_station_docked_ships(stations, player_ships)`

```python
def merge_station_docked_ships(
    stations: list[dict],
    player_ships: list[dict],
) -> list[dict]
```

Adds player-owned ships found in station `docked_ships` lists but missing from the normal ship scan. This covers ships parked or under construction in station bays that are not reliably discovered by the streaming ship pass. Added entries are complete stubs with translated name, size, role, origin, sector, and `"Docked"` order; health, pilot, software, commander, and shield fields are `None` where the station scan cannot provide them.

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

<a id="5-displaypy"></a>
## 📊 5. `display.py`

Formats the assembled `game_data` dictionary as a console report. Called by `x4_save_scanner.py` after whichever interactive scan mode was selected.

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

<a id="6-exportjsonexportpy"></a>
## 📤 6. `export/jsonexport.py`

Builds and writes the structured JSON output file (`x4_empire_state.json`) used for AI prompt input and the desktop UI.

### 🔧 Internal Helpers

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

### 📤 Public API

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

<a id="7-uimain_uipy"></a>
## 🖥️ 7. `ui/main_ui.py`

PyQt6 desktop UI. Presents a save selector dialog, runs the scanner pipeline in a background thread, then renders the HTML dashboard (`ui/ui.html`) in a native Qt window. Empire data is passed from Python to JavaScript via a `QWebChannel` bridge.

### 🔍 Save Discovery

### `_find_steam_root()`

```python
def _find_steam_root() -> pathlib.Path | None
```

Looks up the Steam installation directory via Windows registry keys. Used only by the first-run language-file setup path.

---

### `find_x4_lang_file()`

```python
def find_x4_lang_file() -> pathlib.Path | None
```

Searches Steam library folders for `common/X4 Foundations/t/0001-l044.xml`. Returns the file path if found; otherwise returns `None`.

---

### Class: `LangSetupDialog`

```python
class LangSetupDialog(QDialog)
```

First-run dialog shown when `0001-l044.xml` is missing next to the app/exe. It can auto-detect the file through Steam, browse manually, or skip setup. Auto-detect and browse copy the selected file to `LANG_PATH`.

---

### `find_saves()`

```python
def find_saves() -> list[pathlib.Path]
```

Discovers X4 save files from the default game directory (`~/Documents/Egosoft/X4/<id>/save/`). Returns manual saves (`save_*.xml.gz`) followed by autosaves (`autosave_*.xml.gz`), each group sorted lexicographically by filename. Returns an empty list if the directory is not found.

---

### Class: `SaveSelectDialog`

```python
class SaveSelectDialog(QDialog)
```

Modal dialog that lists all saves returned by `find_saves()` and lets the user pick one to scan. The most recently modified save is pre-selected. Double-clicking a row or pressing **Scan** accepts; **Cancel** rejects.

**Constructor**

```python
def __init__(self, parent=None)
```

**Methods**

`selected_path() -> pathlib.Path | None`
Returns the `pathlib.Path` of the selected save, or `None` if no row is selected.

---

### ⚙️ Scanner Thread

### Class: `ScanWorker`

```python
class ScanWorker(QThread)
```

Background thread that runs the full scanner pipeline (`load_sector_names` → `scan_save` → `scan_reputation` → `scan_ships` → `merge_station_docked_ships` → `export_json`) without blocking the Qt event loop. The UI does not expose CLI scan modes or ship tiers; it always runs this full pipeline. Emits three signals:

| Signal | Payload | When |
|---|---|---|
| `progress` | `str` — status message | After each pipeline step |
| `finished` | — | Scan and JSON export complete |
| `error` | `str` — traceback | On any unhandled exception |

**Constructor**

```python
def __init__(self, save_path: pathlib.Path)
```

| Parameter | Type | Description |
|---|---|---|
| `save_path` | `pathlib.Path` | Path to the `.xml.gz` save file to scan. |

---

### Class: `ScanProgressDialog`

```python
class ScanProgressDialog(QDialog)
```

Modal dialog shown while `ScanWorker` runs. Displays an indeterminate progress bar and a status label updated via the worker's `progress` signal. The close button is disabled during scanning. Accepts when `finished` fires; rejects on `error`, storing the traceback in `error_msg`.

**Constructor**

```python
def __init__(self, save_path: pathlib.Path, parent=None)
```

**Attributes**

`error_msg: str | None` — set to the error traceback if the scan failed; `None` on success.

---

### 🌉 Bridge & Window

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
def __init__(self, data: dict)
```

| Parameter | Type | Description |
|---|---|---|
| `data` | `dict` | The loaded empire state dictionary, passed to `EmpireBridge`. |

---

### 🚀 Helpers & Entry Point

### `load_json(path)`

```python
def load_json(path: pathlib.Path) -> dict
```

Loads and parses a JSON file.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `path` | `pathlib.Path` | Path to the JSON file. |

**Returns** `dict` — parsed JSON content.

---

### `run_scan(parent=None)`

```python
def run_scan(parent=None) -> dict | None
```

Convenience function that sequences the save selector and progress dialog. Shows `SaveSelectDialog`; if accepted, runs `ScanProgressDialog`; if the scan succeeds, reads `x4_empire_state.json` from disk and returns it. Returns `None` if the user cancels at any point or the scan fails (errors are shown in a `QMessageBox`).

The JSON is read back from disk rather than passed in memory because `export_json()` restructures `game_data` into the format `ui.html` expects.

---

### `main()`

```python
def main()
```

Entry point for the UI. Launch behaviour depends on whether `x4_empire_state.json` already exists:

- If `0001-l044.xml` is missing, offers language-file setup before the scan/load decision. Skipping is allowed, but names may fall back to raw IDs.
- **JSON exists** — asks the user whether to run a new scan. Choosing **No** loads the existing JSON immediately. Choosing **Yes** opens the save selector; if the user cancels, falls back to the existing JSON.
- **No JSON** — goes straight to the save selector. If the user cancels with no data to show, exits with code 0.

---

### 🖥️ `ui/ui.html` — JavaScript Helpers

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

<a id="8-datafactionspy"></a>
## ⚔️ 8. `data/factions.py`

Static lookup tables and scaling functions for faction data. Imported by `scanner/reputation_scanner.py`.

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

<a id="9-datawarespy"></a>
## 📦 9. `data/wares.py`

Static lookup tables for ware display names, volume conversion, and transport type classification. Imported by `scanner/station_scanner.py`.

**Module-level constants**

| Constant | Type | Description |
|---|---|---|
| `WARE_NAMES` | `dict[str, str]` | Maps lowercase ware ID strings extracted from production module macros to human-readable display names, e.g. `"energycells"` → `"Energy Cells"`. Covers raw resources, refined materials, ship/station components, and food/consumables. If a ware ID is not present, callers fall back to title-casing with underscores replaced by spaces. |
| `WARE_VOLUME` | `dict[str, float]` | Maps ware IDs to m³ per unit. Used by `_parse_station_storage()` to convert cargo amounts into storage fill volume. Unknown wares default to `1.0` m³/unit in the scanner. |
| `WARE_TRANSPORT` | `dict[str, str]` | Maps ware IDs to storage transport type (`"container"`, `"solid"`, or `"liquid"`). Used to attribute trade reservations to the correct cargo bucket. |

---

### `format_wares(overviewgraphs)` *(Legacy)*

```python
def format_wares(overviewgraphs: str) -> str
```

**No longer called by the main scanner.** Previously converted the `overviewgraphs` station XML attribute into a readable ware list. Replaced by `parse_production_from_construction()` in `station_scanner.py`, which reads directly from `<construction><sequence>` entries and is more reliable. Retained for debugging reference.

---

<a id="10-datashipspy"></a>
## 📋 10. `data/ships.py`

Auto-generated static lookup table mapping ship macro names to display names. Not edited by hand.

**Module-level constants**

| Constant | Type | Description |
|---|---|---|
| `SHIP_NAMES` | `dict[str, str]` | Maps ship macro name strings to in-game display names, e.g. `"ship_tel_s_trans_container_01_b_macro"` → `"Magpie Sentinel"`. Covers base game and all DLC factions. |

This file is committed to the repository. It only needs to be regenerated when new ships are added by a game update or DLC. The current `generate_ship_names.py` script contains the generation logic, although its `OUTPUT_FILE` constant currently points at `data/ship_scanner.py`; verify that before regenerating `data/ships.py`.

---

<a id="11-dataship_statspy"></a>
## 📈 11. `data/ship_stats.py`

Auto-generated static lookup table mapping ship macro names to per-ship stats (currently hull HP). Not edited by hand — regenerated by `generate_ship_stats.py` whenever ship XMLs are updated.

**Module-level constants**

| Constant | Type | Description |
|---|---|---|
| `SHIP_STATS` | `dict[str, dict]` | Maps ship macro name strings to a nested dict of stats. Currently each entry contains only `max_hull`. Example: `"ship_arg_l_destroyer_01_a_macro": {"max_hull": 93000}`. |

The dict is structured as `SHIP_STATS[macro]["stat_name"]` so that additional stats (e.g. cargo capacity, max speed) can be added in future without changing the key structure.

This file is committed to the repository. It only needs to be regenerated when ship XMLs change (new DLC, game patch). See `generate_ship_stats.py` for the generation process.

---

<a id="12-datastation_statspy"></a>
## 🛡️ 12. `data/station_stats.py`

Auto-generated static lookup table mapping station module and shield equipment macro names to static stats. Imported by `scanner/station_scanner.py` for station health/storage/module details and by `scanner/ship_scanner.py` for ship shield capacity.

**Module-level constants**

| Constant | Type | Description |
|---|---|---|
| `STATION_STATS` | `dict[str, dict]` | Maps macro names to entries containing `max_hull`, `max_shield`, `cargo_capacity`, and/or `produces`, depending on the macro type. |

This file is committed to the repository. It is regenerated by `generate_station_stats.py` after extracting station module and shield XMLs. The committed table includes `cargo_capacity` entries used by station storage parsing; verify the generator before regenerating if cargo capacity must be preserved.

---

<a id="13-generate_ship_statspy"></a>
## 🔧 13. `generate_ship_stats.py`

One-time utility script that generates `data/ship_stats.py` by walking all ship macro XMLs in the `ship xml/` folder. The current script runs procedurally at import/execution time; it does not define `extract_hull_max()` or `main()`.

**Required inputs**

- `ship xml/` — folder of ship macro XMLs in the project root. XML files can be extracted from the game's `.cat` files using XRCatTool.

**Module-level constants**

| Constant | Type | Description |
|---|---|---|
| `XML_DIR` | `Path` | Expected location of ship macro XMLs (`ship xml/`). |
| `OUT_FILE` | `Path` | Write target for the generated file (`data/ship_stats.py`). |
| `SHIP_CLASSES` | `set[str]` | XML `class` attribute values that identify whole-ship macros: `"ship_xs"`, `"ship_s"`, `"ship_m"`, `"ship_l"`, `"ship_xl"`. Entries with other classes are skipped. |

**Execution flow**

The script checks that `XML_DIR` exists, recursively reads all `.xml` files, extracts `<macro name="..." class="...">` and `<properties><hull max="..."/>`, stores `{"max_hull": int}`, sorts entries by macro name, then writes a Python source file containing `SHIP_STATS`.

---

<a id="14-generate_station_statspy"></a>
## 🏗️ 14. `generate_station_stats.py`

One-time utility script that generates `data/station_stats.py` from extracted station module XMLs and shield equipment XMLs.

**Required inputs**

- `station xml/` — station module macro XMLs from X4's `.cat` files.
- `shield xml/` — shield equipment macro XMLs from base game and DLC `.cat` files.

**Module-level constants**

| Constant | Type | Description |
|---|---|---|
| `MODULE_DIR` | `Path` | Expected location of station module XMLs (`station xml/`). |
| `SHIELD_DIR` | `Path` | Expected location of shield XMLs (`shield xml/`). |
| `OUT_FILE` | `Path` | Write target for `data/station_stats.py`. |

**Execution flow**

Pass 1 walks `MODULE_DIR`, reads module hull values, and captures production ware IDs when present. Pass 2 walks `SHIELD_DIR`, reads shield generator recharge capacity, and stores it as `max_shield`. The combined `STATION_STATS` dict is sorted and written as Python source. The current committed `data/station_stats.py` also contains `cargo_capacity` entries used by `_parse_station_storage()`, so preserve that path when updating the generator.

---

<a id="15-generate_ship_namespy"></a>
## 🗂️ 15. `generate_ship_names.py`

One-time utility script that builds a ship macro-to-display-name lookup from extracted ship macro XML files and the language file. Run from the project root after extracting ship macros from the game's `.cat` files using XRCatTool.

**Important current-code note:** the script's docstring and `OUTPUT_FILE` currently target `data/ship_scanner.py`, while the live scanner imports `SHIP_NAMES` from `data/ships.py`. Treat regeneration as needing a quick output-path check before use.

**Required inputs**

- `extracted/` — folder of ship macro XMLs extracted from `.cat` files. Expected path structure: `extracted/assets/units/size_*/macros/ship_*_macro.xml`.
- `0001-l044.xml` — X4 English language file, in the project root.

### ⚙️ Module Constants

| Constant | Type | Description |
|---|---|---|
| `SCRIPT_DIR` | `Path` | Project root, derived from `__file__`. |
| `EXTRACTED_DIR` | `Path` | Expected location of extracted ship macro XMLs. |
| `LANG_FILE` | `Path` | Expected location of the language file. |
| `OUTPUT_FILE` | `Path` | Current write target in code: `data/ship_scanner.py`. The scanner currently imports `data/ships.py`. |
| `BASE_REF_RE` | `re.Pattern` | Pre-compiled regex matching page 20101 language references, e.g. `{20101,22601}`. Group 1 captures the numeric ID. |
| `VAR_REF_RE` | `re.Pattern` | Pre-compiled regex matching page 20111 variant token references, e.g. `{20111,1101}`. Group 1 captures the numeric ID. |
| `HEADER` | `str` | File header comment block and opening of the `SHIP_NAMES` dict written to the output file. |
| `FOOTER` | `str` | Closing brace written to the output file. |

---

### 🔧 Functions

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

Writes the macro-to-display-name mapping to the configured `output_path` as a Python source file containing a `SHIP_NAMES` dict. Entries are sorted alphabetically by macro name. Single quotes within display names are backslash-escaped. Creates the output directory if it does not exist.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `mapping` | `dict` | Dict returned by `build_macro_to_name()`. |
| `output_path` | `pathlib.Path` | Destination path for the generated Python file. |
