"""
X4 FOUNDATIONS — SAVE FILE SCANNER  v4.0
==========================================
Reads an unzipped X4 save file (save_001.xml) and extracts:
  - Pilot name and current sector
  - Credits / liquid cash
  - All player-owned stations with sector locations and production
  - Faction reputation standings displayed as in-game whole numbers

Then exports everything to x4_empire_state.json, ready to paste
into an AI prompt for strategic advice.

REQUIRED FILES (all in the same folder as this script):
  save_001.xml     — your unzipped X4 save file
  0001-l044.xml    — X4 English language file (extracted from game .cat files
                     using X Tools, available free on Steam)

HOW SECTOR NAMES WORK:
  Sector components in the save file use a 'macro' attribute like
  'cluster_43_sector001_macro'. We convert this to a language file ID
  using the formula: cluster_num * 10 + sector_suffix, then look up
  the human-readable name from page 20004 of the language file.

HOW REPUTATION SCALING WORKS:
  X4 stores reputation internally as small floats (e.g. 0.0032).
  The in-game UI multiplies these by 100 and displays them as whole numbers
  with one decimal place (e.g. 0.256 -> 25.6). This script replicates
  that scaling so figures match what you see in-game.
"""

import xml.etree.ElementTree as ET
import json
import re
import pathlib
import traceback

# ─────────────────────────────────────────────────────────────────────────────
#  FILE PATHS
#  pathlib.Path(__file__).parent always points to the folder the script lives
#  in, regardless of how or where the script is launched from.
# ─────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR = pathlib.Path(__file__).parent
SAVE_FILE  = SCRIPT_DIR / "save_001.xml"
LANG_FILE  = SCRIPT_DIR / "0001-l044.xml"


# ─────────────────────────────────────────────────────────────────────────────
#  STATION CLASS NAMES
#  The XML 'class' attribute values X4 uses for player-built structures.
# ─────────────────────────────────────────────────────────────────────────────

STATION_CLASSES = {"station", "factory", "headquarters", "complex"}


# ─────────────────────────────────────────────────────────────────────────────
#  WARE DISPLAY NAMES
#  X4 stores production ware IDs as single concatenated lowercase strings
#  (e.g. "advancedelectronics"). This lookup converts them to proper
#  human-readable names with spaces (e.g. "Advanced Electronics").
#  Add more entries here if you build stations producing unlisted wares.
# ─────────────────────────────────────────────────────────────────────────────

WARE_NAMES = {
    # Raw resources
    "ore":                    "Ore",
    "silicon":                "Silicon",
    "ice":                    "Ice",
    "hydrogen":               "Hydrogen",
    "helium":                 "Helium",
    "methane":                "Methane",
    "nividium":               "Nividium",
    # Refined / basic materials
    "refinedmetals":          "Refined Metals",
    "siliconwafers":          "Silicon Wafers",
    "energycells":            "Energy Cells",
    "graphene":               "Graphene",
    "superfluidcoolant":      "Superfluid Coolant",
    "antimattercells":        "Antimatter Cells",
    "plasmaconductors":       "Plasma Conductors",
    "quantumtubes":           "Quantum Tubes",
    "microchips":             "Microchips",
    "advancedelectronics":    "Advanced Electronics",
    "advancedcomposites":     "Advanced Composites",
    "scanningarrays":         "Scanning Arrays",
    "engineparts":            "Engine Parts",
    "hullparts":              "Hull Parts",
    "smartchips":             "Smart Chips",
    "dronecomponents":        "Drone Components",
    "fieldcoils":             "Field Coils",
    "majadust":               "Maja Dust",
    "teladianium":            "Teladianium",
    "protectivecoating":      "Protective Coating",
    "computronicsubstrate":   "Computronic Substrate",
    "metallic microlattice":  "Metallic Microlattice",
    "metallicmicrolattice":   "Metallic Microlattice",
    "siliconcarbidemicrolattice": "Silicon Carbide Microlattice",
    "carboncarbide":          "Carbon Carbide",
    # Food / consumables
    "foodrations":            "Food Rations",
    "medicalsupplies":        "Medical Supplies",
    "spaceweed":              "Space Weed",
    "spacefuel":              "Space Fuel",
    "maja snails":            "Maja Snails",
    "majasnails":             "Maja Snails",
    "stimulants":             "Stimulants",
    "hallucinogenics":        "Hallucinogenics",
    # Ship / station components
    "weaponcomponents":       "Weapon Components",
    "missilecomponents":      "Missile Components",
    "shieldcomponents":       "Shield Components",
    "turretcomponents":       "Turret Components",
    "claytronics":            "Claytronics",
    "antimatterconverters":   "Antimatter Converters",
    "redundantcoolingsystems":"Redundant Cooling Systems",
    "podcontrolsystems":      "Pod Control Systems",
}


def format_wares(overviewgraphs: str) -> str:
    """
    Converts a raw overviewgraphs string like "advancedelectronics energycells microchips"
    into a readable list like "Advanced Electronics, Energy Cells, Microchips".
    Falls back to Title Case for any ware not in our lookup table.
    """
    if not overviewgraphs:
        return ""
    wares = overviewgraphs.strip().split()
    display = [WARE_NAMES.get(w.lower(), w.replace('_', ' ').title()) for w in wares]
    return ", ".join(display)


# ─────────────────────────────────────────────────────────────────────────────
#  FACTION NAME LOOKUP
#  Maps short internal faction IDs to full display names.
# ─────────────────────────────────────────────────────────────────────────────

FACTION_NAMES = {
    "argon":            "Argon Federation",
    "antigone":         "Antigone Republic",
    "hatikvah":         "Hatikvah Free League",
    "paranid":          "Godrealm of the Paranid",
    "trinity":          "Trinity of Paranid",
    "split":            "Free Families (Split)",
    "fallensplit":      "Fallen Families (Split)",
    "freesplit":        "Free Split",
    "teladi":           "Teladi Company",
    "ministry":         "Ministry of Finance",
    "xenon":            "Xenon",
    "khaak":            "Kha'ak",
    "buccaneers":       "Hewa's Twin Duchies",
    "scaleplate":       "Scale Plate Pact",
    "loanshark":        "Riptide Rakers",
    "holyorder":        "Holy Order of the Pontifex",
    "holyorderfanatic": "Holy Order Fanatics",
    "yaki":             "Yaki",
    "pioneers":         "Segaris Pioneers",
    "terran":           "Terran Protectorate",
    "boron":            "Boron Kingdom",
}

# Internal/non-playable factions excluded from the reputation report.
SKIP_FACTIONS = {
    "criminal", "civilian", "smuggler", "outlaw", "visitor",
    "scavenger", "kaori", "court", "alliance", "player",
}


# ═════════════════════════════════════════════════════════════════════════════
#  SECTION 1 — LANGUAGE FILE: SECTOR NAME RESOLUTION
# ═════════════════════════════════════════════════════════════════════════════

def load_sector_names(lang_path: pathlib.Path) -> dict:
    """
    Parses the X4 English language file and returns a lookup dictionary:
        { "270011": "The Void", "140011": "Argon Prime", ... }

    Sector names live in <page id="20004">. Each entry looks like:
        <t id="270011">{20003,270001}(The Void)</t>
    We extract the name from the parentheses at the end and key it by ID.
    """
    lookup = {}

    if not lang_path.exists():
        print(f"\n[Warning] Language file not found: {lang_path.name}")
        print("  Sector names will show as macro IDs.")
        print("  Extract 0001-l044.xml from X4's .cat files using X Tools (Steam).\n")
        return lookup

    try:
        print(f"[Language] Loading sector names from {lang_path.name}...")
        tree = ET.parse(str(lang_path))
        root = tree.getroot()

        for page in root.findall('page'):
            if page.get('id') == '20004':
                for t in page.findall('t'):
                    tid  = t.get('id', '')
                    text = (t.text or '').strip()
                    # Extract the name in parentheses at the end of the string
                    # e.g. "{20003,270001}(The Void)" -> "The Void"
                    m = re.search(r'\(([^)]+)\)\s*$', text)
                    if m:
                        lookup[tid] = m.group(1)
                break  # Page 20004 found — no need to continue scanning

        print(f"[Language] Loaded {len(lookup)} sector names successfully.")

    except Exception as e:
        print(f"[Warning] Failed to parse language file: {e}")

    return lookup


def macro_to_sector_name(macro: str, sector_names: dict) -> str:
    """
    Converts a sector macro name like 'cluster_43_sector001_macro' into
    a human-readable sector name like 'Hewa's Twin V'.

    HOW THE FORMULA WORKS:
    The language file uses numeric IDs for sectors. The pattern is:
        language_id = str(cluster_number * 10) + sector_suffix
    Where sector_suffix is:
        sector001 -> "011"
        sector002 -> "021"
        sector003 -> "031"  (each step adds 10 to the middle digit)

    Examples:
        cluster_43_sector001_macro -> 43*10=430, suffix=011 -> "430011" -> "Hewa's Twin V"
        cluster_14_sector001_macro -> 14*10=140, suffix=011 -> "140011" -> "Argon Prime"
        cluster_27_sector001_macro -> 27*10=270, suffix=011 -> "270011" -> "The Void"
        cluster_1_sector001_macro  ->  1*10=10,  suffix=011 ->  "10011" -> "Grand Exchange I"

    Returns None if the macro doesn't match the expected pattern.
    """
    m = re.match(r'cluster_(\d+)_sector(\d+)_macro', macro, re.IGNORECASE)
    if not m:
        return None

    cluster_num = int(m.group(1))
    sector_num  = int(m.group(2))  # 1 for sector001, 2 for sector002, etc.

    # Build the language file ID from the cluster and sector numbers
    prefix     = str(cluster_num * 10)
    suffix     = str(sector_num * 10 + 1).zfill(3)  # 1->"011", 2->"021", 3->"031"
    lang_id    = prefix + suffix

    return sector_names.get(lang_id)


def resolve_sector_from_location(location_str: str, sector_names: dict) -> str:
    """
    Resolves a sector reference in the {20004,XXXXX} format used in the
    save's <info><player location="..."/> attribute.

    This is only used for the player's current position displayed at the top
    of the report. Station sectors are resolved via macro_to_sector_name().
    """
    if not location_str:
        return "Unknown"
    m = re.search(r'\{20004,(\d+)\}', location_str)
    if m:
        return sector_names.get(m.group(1), f"Sector {m.group(1)}")
    return location_str


# ═════════════════════════════════════════════════════════════════════════════
#  SECTION 2 — HELPERS
# ═════════════════════════════════════════════════════════════════════════════

def format_credits(amount_str: str) -> str:
    """Formats a raw credit integer string into a comma-separated display value."""
    try:
        return f"{int(amount_str):,} Cr"
    except (ValueError, TypeError):
        return f"{amount_str} Cr"


def scale_reputation(raw: float) -> float:
    """
    Converts X4's internal reputation float to the in-game display scale.

    X4 stores reputation as small decimals internally (e.g. 0.256184) but
    the in-game UI displays these multiplied by 100 (e.g. 25.6).
    Clamped to the range -30.0 to +30.0 to match the in-game maximum.
    """
    scaled = raw * 100.0
    return max(-30.0, min(30.0, scaled))


def reputation_label(scaled_value: float) -> str:
    """
    Returns a descriptive tier label based on the scaled (in-game) reputation value.
    Thresholds are approximate — X4's actual unlock points vary per faction.
    """
    if scaled_value >= 20:  return "Allied"
    if scaled_value >= 10:  return "Friendly"
    if scaled_value >= 0:   return "Neutral"
    if scaled_value >= -10: return "Hostile"
    return "At War"


# ═════════════════════════════════════════════════════════════════════════════
#  SECTION 3 — PASS 1: PLAYER DATA AND STATIONS
# ═════════════════════════════════════════════════════════════════════════════

def scan_save(file_path: pathlib.Path, sector_names: dict) -> dict:
    """
    Streams through the X4 save XML and extracts player data and stations.

    WHY iterparse():
    The save file is 700MB+. iterparse() reads it as a stream one element at
    a time, keeping RAM usage low. We call elem.clear() on every 'end' event
    to immediately release processed elements from memory.

    HOW SECTOR TRACKING WORKS:
    The universe XML is hierarchical: galaxy > cluster > sector > zone > objects.
    Sector components use the 'macro' attribute (e.g. 'cluster_43_sector001_macro').
    We track the most recently seen sector name as we stream through — when we
    encounter a player station, whatever sector we last saw is its location.
    This works because stations are always nested inside their sector in the XML.

    HOW STATION NAMES ARE BUILT:
    Priority order:
      1. Custom name set by player in-game (the 'name' attribute)
      2. Player HQ detected via macro name
      3. Production type from 'overviewgraphs' attribute + station code
      4. Last resort: station index + code only
    """
    data = {
        "player_name":    None,
        "player_credits": None,
        "player_sector":  None,
        "stations":       [],
        "reputation":     [],
    }

    in_player_faction = False   # True while inside <faction id="player">
    current_sector    = "Unknown Sector"  # Updated whenever we enter a sector component

    print(f"[Scanning] Pass 1 — player identity, credits, stations...")

    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            context = ET.iterparse(f, events=('start', 'end'))

            for event, elem in context:
                tag = elem.tag

                # ── PLAYER NAME AND CURRENT SECTOR ────────────────────────────
                # The first <player> tag in <info> holds the pilot name and
                # their current location as a {20004,XXXXX} reference.
                if event == 'start' and tag == 'player':
                    if not data["player_name"]:
                        data["player_name"] = elem.get('name')
                        loc = elem.get('location', '')
                        if loc:
                            data["player_sector"] = resolve_sector_from_location(
                                loc, sector_names
                            )

                # ── PLAYER CREDITS ─────────────────────────────────────────────
                # Stored inside <faction id="player"><account amount="X"/>
                if event == 'start' and tag == 'faction' and elem.get('id') == 'player':
                    in_player_faction = True

                if in_player_faction and event == 'start' and tag == 'account':
                    if not data["player_credits"]:
                        data["player_credits"] = (
                            elem.get('amount') or elem.get('balance')
                        )

                if event == 'end' and tag == 'faction' and elem.get('id') == 'player':
                    in_player_faction = False

                # ── SECTOR TRACKING AND STATION DETECTION ─────────────────────
                if event == 'start' and tag == 'component':
                    comp_class = elem.get('class', '')

                    # Update current sector when we enter a sector component.
                    # Sectors use the 'macro' attribute: 'cluster_43_sector001_macro'
                    # We convert this to a display name via our formula.
                    if comp_class == 'sector':
                        macro = elem.get('macro', '')
                        resolved = macro_to_sector_name(macro, sector_names)
                        if resolved:
                            current_sector = resolved

                    # Detect player-owned stations
                    if (elem.get('owner') == 'player' and
                            comp_class in STATION_CLASSES):

                        macro     = elem.get('macro', '')
                        code      = elem.get('code', '')
                        name_attr = elem.get('name')        # custom name if player renamed it
                        nameindex = elem.get('nameindex', '') # auto-assigned index number
                        overviews = elem.get('overviewgraphs', '') # space-separated ware IDs

                        # Build the best display name available
                        if name_attr:
                            # Player gave this station a custom name in-game
                            display_name = name_attr
                        elif 'headquarters' in macro.lower():
                            display_name = "Player HQ"
                        elif overviews:
                            # Describe the station by what it produces, with readable ware names
                            wares = format_wares(overviews)
                            display_name = f"Station #{nameindex}"
                        else:
                            display_name = f"Station #{nameindex}" if nameindex else "Unnamed Station"

                        entry = {
                            "name":       display_name,
                            "code":       code,
                            "class":      comp_class,
                            "macro":      macro,
                            "sector":     current_sector,
                            "production": format_wares(overviews),
                        }

                        # Deduplicate by station code — the same station can appear
                        # in multiple XML contexts (e.g. in construction snapshots)
                        if not any(s["code"] == code for s in data["stations"]):
                            data["stations"].append(entry)

                # ── MEMORY MANAGEMENT ──────────────────────────────────────────
                # Clear each element after its closing tag to prevent RAM buildup.
                # Only safe on 'end' events — 'start' events fire before child data
                # is available, so clearing there would lose information.
                if event == 'end':
                    elem.clear()

    except ET.ParseError as e:
        print(f"\n[XML Error] Save file has a formatting issue: {e}")
        raise
    except Exception as e:
        print(f"\n[Error] Unexpected problem: {e}")
        raise

    return data


# ═════════════════════════════════════════════════════════════════════════════
#  SECTION 4 — PASS 2: FACTION REPUTATION
# ═════════════════════════════════════════════════════════════════════════════

def scan_reputation(file_path: pathlib.Path) -> list:
    """
    Second pass to extract faction reputation from the player's faction block.

    WHY A SECOND PASS:
    iterparse() can't easily track parent context during complex nested scanning.
    A dedicated pass for reputation is cleaner and more reliable.

    HOW REPUTATION IS STORED:
    The player's standings are in <faction id="player"><relations>:
        <relation faction="argon" relation="0.0032"/>
        <booster faction="argon" relation="0.2562" time="326867.385"/>

    Base 'relation' is the permanent standing. 'booster' entries are temporary
    bonuses from missions that decay over time. We report base and booster
    separately so you can see what's permanent vs temporary.

    WHY SOME FACTIONS APPEAR BOOSTER-ONLY:
    If you've never had a base relation recorded for a faction (e.g. Teladi),
    the save only stores their booster entry. We handle this by collecting
    all boosters regardless of whether a base relation exists, then merging.

    REPUTATION SCALING:
    Internal values are multiplied by 100 to match the in-game display.
    We show the base value scaled (permanent standing) and booster scaled
    (temporary bonus) separately, both to 2 decimal places.
    """
    in_player_fac  = False
    in_relations   = False
    base_relations = {}   # { faction_id: raw_float }
    boosters       = {}   # { faction_id: raw_float }

    print(f"[Scanning] Pass 2 — faction reputation...")

    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        context = ET.iterparse(f, events=('start', 'end'))

        for event, elem in context:
            tag = elem.tag

            if event == 'start' and tag == 'faction' and elem.get('id') == 'player':
                in_player_fac = True

            if in_player_fac:
                if event == 'start' and tag == 'relations':
                    in_relations = True

                # Collect base reputation values
                if in_relations and event == 'start' and tag == 'relation':
                    fid = elem.get('faction')
                    try:
                        base_relations[fid] = float(elem.get('relation', '0'))
                    except ValueError:
                        base_relations[fid] = 0.0

                # Collect booster values (temporary mission bonuses).
                # These exist even for factions with no base relation entry,
                # which is why Teladi can appear here but not in base_relations.
                if in_relations and event == 'start' and tag == 'booster':
                    fid = elem.get('faction')
                    try:
                        boosters[fid] = float(elem.get('relation', '0'))
                    except ValueError:
                        boosters[fid] = 0.0

                if event == 'end' and tag == 'relations':
                    in_relations = False

                # Once we leave the player faction block, stop scanning —
                # no need to read the remaining hundreds of MB of the file.
                if event == 'end' and tag == 'faction' and elem.get('id') == 'player':
                    in_player_fac = False
                    break

            if event == 'end':
                elem.clear()

    # Merge base relations and boosters.
    # We union both sets so factions that only appear in boosters (like Teladi)
    # are still included in the output.
    all_factions = set(base_relations.keys()) | set(boosters.keys())
    reputation   = []

    for fid in all_factions:
        if fid in SKIP_FACTIONS:
            continue

        raw_base    = base_relations.get(fid, 0.0)
        raw_booster = boosters.get(fid, 0.0)

        # Scale to in-game display values (multiply by 100, clamp to -30..+30)
        scaled_base    = scale_reputation(raw_base)
        scaled_booster = scale_reputation(raw_booster)
        scaled_total   = max(-30.0, min(30.0, (raw_base + raw_booster) * 100.0))

        faction_name = FACTION_NAMES.get(fid, fid.title())

        reputation.append({
            "faction_id":      fid,
            "faction_name":    faction_name,
            "value":           round(scaled_total, 2),    # total in-game standing
            "base":            round(scaled_base, 2),     # permanent component
            "booster":         round(scaled_booster, 2),  # temporary mission bonus
            "tier":            reputation_label(scaled_total),
        })

    # Sort best standing first
    reputation.sort(key=lambda x: x["value"], reverse=True)
    return reputation


# ═════════════════════════════════════════════════════════════════════════════
#  SECTION 5 — DISPLAY AND EXPORT
# ═════════════════════════════════════════════════════════════════════════════

def display_results(data: dict):
    """
    Prints the extracted data to console in a readable format.

    STATION LAYOUT:
    Stations are grouped by sector so that multiple stations in the same
    location are visually clustered together. The sector is printed once
    as a header, with each station indented beneath it. Station name and
    code appear on the first line, production on the second.

    REPUTATION TABLE:
    Values scaled ×100 to match in-game display (-30 to +30 range).
    Shows Total (what the game UI displays), a visual bar, tier label,
    the permanent Base value, and any temporary Booster from missions.
    """
    SEP  = "═" * 68
    LINE = "─" * 68
    THIN = "·" * 68

    print(f"\n{SEP}")
    print("         X4 FOUNDATIONS — EMPIRE INTELLIGENCE REPORT v4.0")
    print(SEP)
    print(f"  PILOT          : {data['player_name'] or 'Unknown'}")
    print(f"  CURRENT SECTOR : {data['player_sector'] or 'Unknown'}")
    credits_str = format_credits(data['player_credits']) if data['player_credits'] else "Not found"
    print(f"  CREDITS        : {credits_str}")
    print(LINE)

    # ── STATIONS — grouped by sector ──────────────────────────────────────────
    # We build an ordered dict of { sector_name: [station, station, ...] }
    # preserving the order sectors are first encountered in the save file.
    print(f"  OWNED STATIONS  ({len(data['stations'])} total)")
    print()

    if data["stations"]:
        # Group stations by sector, preserving encounter order
        sectors_seen = {}   # { sector_name: [station dicts] }
        for s in data["stations"]:
            sector = s["sector"]
            if sector not in sectors_seen:
                sectors_seen[sector] = []
            sectors_seen[sector].append(s)

        # Print each sector group
        for sector, stations in sectors_seen.items():
            # Sector header — printed once per group
            station_word = "station" if len(stations) == 1 else "stations"
            print(f"  ┌─ SECTOR: {sector}  ({len(stations)} {station_word})")

            for i, s in enumerate(stations):
                # Use corner piece on last station, tee on others
                connector = "└──" if i == len(stations) - 1 else "├──"

                # Station name line — name is the distinct header, code at the end
                print(f"  {connector} {s['name']} [{s['code']}]")

                # Production line — indented to align under the station name
                # Extra indent matches the connector width
                indent = "      " if i == len(stations) - 1 else "  │   "
                if s["production"]:
                    print(f"  {indent}  Produces : {s['production']}")
                else:
                    print(f"  {indent}  Produces : —")

            print()  # Blank line between sector groups for breathing room

    else:
        print("    No player-owned stations detected.")

    print(LINE)

    # ── REPUTATION ────────────────────────────────────────────────────────────
    # Displayed as in-game values (scaled ×100, range -30 to +30).
    # Base = permanent standing | Booster = temporary mission bonus from missions.
    # Total = base + booster, matching what the in-game UI shows.
    print(f"  FACTION REPUTATION  ({len(data['reputation'])} factions)"
          f"   [  -30 ◄ hostile · neutral · friendly ► +30  ]")
    print()
    print(f"    {'Faction':<32} {'Total':>6}  {'':22}  {'Tier':<10}  {'Base':>6}  {'Boost':>6}")
    print(f"    {'─'*32} {'─'*6}  {'─'*22}  {'─'*10}  {'─'*6}  {'─'*6}")

    if data["reputation"]:
        for r in data["reputation"]:
            # Scale -30..+30 onto a 20-character visual bar
            bar_val = int((r['value'] + 30) / 60 * 20)
            bar_val = max(0, min(20, bar_val))
            bar     = "█" * bar_val + "░" * (20 - bar_val)

            booster_str = f"{r['booster']:>+6.2f}" if r['booster'] != 0 else "     —"
            print(
                f"    {r['faction_name']:<32} {r['value']:>+6.2f}  [{bar}]  "
                f"{r['tier']:<10}  {r['base']:>+6.2f}  {booster_str}"
            )
    else:
        print("    No reputation data found.")

    print(f"\n{SEP}")


def export_json(data: dict):
    """
    Exports all extracted data as a structured JSON file.
    Paste the contents into an AI prompt for strategic advice, e.g.:
    'Here is my current X4 empire state. What should I prioritise next?'
    """
    out_path = SCRIPT_DIR / "x4_empire_state.json"
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    print(f"\n[Export] Saved to: {out_path.name}")
    print("  Paste the contents of x4_empire_state.json into an AI prompt for advice.")


# ═════════════════════════════════════════════════════════════════════════════
#  SECTION 6 — ENTRY POINT
# ═════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    try:
        # Verify save file exists before doing anything else
        if not SAVE_FILE.exists():
            print(f"Error: '{SAVE_FILE.name}' not found in the script folder.")
            print(f"Expected location: {SAVE_FILE}")
            print("Rename your unzipped X4 save to 'save_001.xml' and place it here.")
            input("\nPress Enter to exit...")
            exit(1)

        # Step 1: Load sector name lookup from the language file.
        # If the file is missing, sectors show as macro names but won't crash.
        sector_names = load_sector_names(LANG_FILE)

        # Step 2: First pass — player identity, credits, stations with sectors
        game_data = scan_save(SAVE_FILE, sector_names)

        # Step 3: Second pass — faction reputation with scaling and booster handling
        game_data["reputation"] = scan_reputation(SAVE_FILE)

        # Step 4: Display and export
        display_results(game_data)
        export_json(game_data)

    except Exception as e:
        print(f"\n[FATAL ERROR] {e}")
        traceback.print_exc()

    input("\nPress Enter to exit...")