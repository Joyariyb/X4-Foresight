"""
X4 FOUNDATIONS — SAVE FILE SCANNER  v3.0
==========================================
Reads an unzipped X4 save file (save_001.xml) and extracts:
  - Pilot name and current sector
  - Credits / liquid cash
  - All player-owned stations with sector locations
  - Faction reputation standings (with booster values)

Then exports everything to x4_empire_state.json, ready to paste
into an AI prompt for strategic advice.

REQUIRED FILES (all in the same folder as this script):
  save_001.xml     — your unzipped X4 save file
  0001-l044.xml    — X4 English language file (extracted from game .cat files
                     using X Tools, available free on Steam)

HOW SECTOR NAMES WORK:
  X4 save files don't store sector names as plain text. Instead they
  reference sectors as a page/id pair like {20004,270011}. The language
  file (0001-l044.xml) contains page 20004 which maps those IDs to
  human-readable names like "The Void". This script loads that mapping
  at startup so sector names appear correctly in the output.
"""

import xml.etree.ElementTree as ET
import json
import re
import pathlib
import traceback

# ─────────────────────────────────────────────────────────────────────────────
#  FILE PATHS
#  Using pathlib.Path(__file__).parent means "the folder this script lives in",
#  which is more reliable than os.getcwd() since the working directory can
#  change depending on how you launch the script (double-click, terminal, IDE).
# ─────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR = pathlib.Path(__file__).parent
SAVE_FILE  = SCRIPT_DIR / "save_001.xml"
LANG_FILE  = SCRIPT_DIR / "0001-l044.xml"


# ─────────────────────────────────────────────────────────────────────────────
#  STATION CLASS NAMES
#  These are the XML 'class' attribute values X4 uses for player-built
#  structures. We check against this set when scanning component tags.
# ─────────────────────────────────────────────────────────────────────────────

STATION_CLASSES = {"station", "factory", "headquarters", "complex"}


# ─────────────────────────────────────────────────────────────────────────────
#  FACTION NAME LOOKUP
#  X4 stores faction IDs as short lowercase strings (e.g. "argon", "holyorder").
#  This dict maps them to the full display names players recognise from the game.
#  If a faction ID isn't found here, the script falls back to .title() casing.
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
    "alliance":         "Alliance of the Word",
    "loanshark":        "Riptide Rakers",
    "holyorder":        "Holy Order of the Pontifex",
    "holyorderfanatic": "Holy Order Fanatics",
    "yaki":             "Yaki",
    "pioneers":         "Segaris Pioneers",
    "terran":           "Terran Protectorate",
    "boron":            "Boron Kingdom",
}

# Factions to exclude from reputation output entirely.
# These are internal/non-playable factions the player can't interact with
# meaningfully, so they'd just clutter the report.
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

    HOW IT WORKS:
    The language file groups all text strings into <page> blocks by category.
    Page 20004 is specifically titled "Sectors" and contains one entry per
    sector. Each entry looks like:
        <t id="270011">{20003,270001}(The Void)</t>
    The {20003,270001} part is a cross-reference to the system name (page 20003).
    The (The Void) part in parentheses at the end is the actual sector name.
    We extract just that parenthesised portion and key it by the numeric ID.

    WHY WE NEED THIS:
    In the save file, sectors are referenced as {20004,270011} — the page
    number (20004) and the ID (270011). This function lets us convert that
    ID directly into a human-readable sector name.
    """
    lookup = {}

    if not lang_path.exists():
        # Warn the user but don't crash — the script will still work,
        # just with "Unknown Sector" shown instead of names.
        print(f"\n[Warning] Language file not found: {lang_path.name}")
        print("  Sector names will appear as IDs.")
        print("  Extract 0001-l044.xml from X4's .cat files using X Tools (Steam)")
        print("  and place it in the same folder as this script.\n")
        return lookup

    try:
        print(f"[Language] Loading sector names from {lang_path.name}...")
        tree = ET.parse(str(lang_path))
        root = tree.getroot()

        for page in root.findall('page'):
            if page.get('id') == '20004':
                # Found the Sectors page — extract all name entries
                for t in page.findall('t'):
                    tid  = t.get('id', '')
                    text = (t.text or '').strip()
                    # Regex: match text in parentheses at the very end of the string
                    # e.g. "{20003,270001}(The Void)" -> captures "The Void"
                    m = re.search(r'\(([^)]+)\)\s*$', text)
                    if m:
                        lookup[tid] = m.group(1)
                break  # No need to keep scanning after finding page 20004

        print(f"[Language] Loaded {len(lookup)} sector names successfully.")

    except Exception as e:
        print(f"[Warning] Failed to parse language file: {e}")

    return lookup


def resolve_sector(location_str: str, sector_names: dict) -> str:
    """
    Converts a raw sector reference from the save file into a display name.

    X4 save files reference sectors in the format {20004,270011} where:
      20004 = the page number for "Sectors" in the language file
      270011 = the specific sector's ID within that page

    We extract the numeric ID and look it up in our sector_names dictionary.
    If we can't resolve it, we return a fallback string rather than crashing.

    Examples:
      "{20004,270011}" -> "The Void"
      "{20004,140011}" -> "Argon Prime"
      ""               -> "Unknown Sector"
    """
    if not location_str:
        return "Unknown Sector"

    # Look for the {20004,XXXXX} pattern
    m = re.search(r'\{20004,(\d+)\}', location_str)
    if m:
        sid = m.group(1)
        return sector_names.get(sid, f"Sector ID {sid}")

    # If the string is already just a numeric ID (unlikely but safe to handle)
    if location_str.isdigit():
        return sector_names.get(location_str, f"Sector ID {location_str}")

    # If it's already a plain text name or something unrecognised, return as-is
    return location_str


# ═════════════════════════════════════════════════════════════════════════════
#  SECTION 2 — HELPER FUNCTIONS
# ═════════════════════════════════════════════════════════════════════════════

def format_credits(amount_str: str) -> str:
    """
    Converts a raw credit amount string (e.g. "13066417") into a
    formatted, comma-separated display string (e.g. "13,066,417 Cr").
    Falls back gracefully if the value isn't a valid integer.
    """
    try:
        return f"{int(amount_str):,} Cr"
    except (ValueError, TypeError):
        return f"{amount_str} Cr"


def reputation_label(value: float) -> str:
    """
    Converts a raw X4 reputation float into a descriptive tier label.

    X4 reputation ranges roughly from -1.0 (minimum hostile) to +30.0
    (fully allied). The thresholds below are approximate — the game's
    actual unlock thresholds vary per faction, but these give a useful
    at-a-glance summary for the AI advisor context.
    """
    if value >= 20:  return "Allied"
    if value >= 10:  return "Friendly"
    if value >= 0:   return "Neutral"
    if value >= -10: return "Hostile"
    return "At War"


# ═════════════════════════════════════════════════════════════════════════════
#  SECTION 3 — PASS 1: PLAYER DATA AND STATIONS
# ═════════════════════════════════════════════════════════════════════════════

def scan_save(file_path: pathlib.Path, sector_names: dict) -> dict:
    """
    Streams through the X4 save XML file and extracts:
      - Player name and current sector
      - Player credit balance
      - All player-owned stations with their sector locations

    WHY WE USE iterparse() INSTEAD OF parse():
    The save file is 700MB+. Loading the entire XML tree into memory with
    ET.parse() would use several gigabytes of RAM and be very slow.
    ET.iterparse() reads the file as a stream, processing one element at a
    time and never holding the full tree in memory. We call elem.clear()
    after each 'end' event to release processed elements immediately.

    HOW SECTOR TRACKING WORKS:
    The universe XML is hierarchical: galaxy > cluster > sector > zone > objects.
    As we stream through, we watch for <component class="sector"> tags and read
    their 'knownname' attribute (e.g. "{20004,270011}"). We store the most
    recently seen sector name, so when we later find a player station, we can
    attach the correct sector to it. This works because stations are always
    children of sector components in the XML tree.

    HOW STATION DETECTION WORKS:
    Player-owned stations have owner="player" on their <component> tag and
    a class attribute matching one of our STATION_CLASSES set. We build a
    display name from whatever attributes are available, prioritising the
    custom name the player gave the station in-game (the 'name' attribute),
    then falling back to production type + station code.
    """
    data = {
        "player_name":    None,
        "player_credits": None,
        "player_sector":  None,
        "stations":       [],   # list of station detail dicts
        "reputation":     [],   # filled in by scan_reputation() in pass 2
    }

    in_player_faction = False   # True while we're inside <faction id="player">
    current_sector    = "Unknown Sector"  # updated as we encounter sector components

    print(f"[Scanning] Pass 1 — player identity, credits, stations...")

    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:

            # iterparse fires 'start' when it opens a tag, 'end' when it closes one.
            # We use 'start' to read attributes immediately, and 'end' to clear memory.
            context = ET.iterparse(f, events=('start', 'end'))

            for event, elem in context:
                tag = elem.tag

                # ── PLAYER NAME AND CURRENT SECTOR ────────────────────────────
                # The first <player> tag in the <info> block holds the pilot name
                # and their current location as a sector reference.
                if event == 'start' and tag == 'player':
                    if not data["player_name"]:
                        data["player_name"] = elem.get('name')
                        # location attr looks like "{20004,270011}" — resolve it
                        loc = elem.get('location', '')
                        if loc:
                            data["player_sector"] = resolve_sector(loc, sector_names)

                # ── PLAYER CREDITS ─────────────────────────────────────────────
                # Credits are stored inside <faction id="player"><account amount="X"/>
                # We set a flag when we enter the player faction block, then read
                # the account balance, then clear the flag when we leave.
                if event == 'start' and tag == 'faction' and elem.get('id') == 'player':
                    in_player_faction = True

                if in_player_faction and event == 'start' and tag == 'account':
                    if not data["player_credits"]:
                        # The attribute is called 'amount' in most saves,
                        # but some older versions used 'balance' — check both.
                        data["player_credits"] = (
                            elem.get('amount') or elem.get('balance')
                        )

                if event == 'end' and tag == 'faction' and elem.get('id') == 'player':
                    in_player_faction = False

                # ── SECTOR TRACKING ────────────────────────────────────────────
                # As we walk the XML tree, we track the most recently opened
                # sector component. All stations are nested inside sectors, so
                # whatever sector we saw last is the one the next station belongs to.
                if event == 'start' and tag == 'component':
                    comp_class = elem.get('class', '')

                    if comp_class == 'sector':
                        # Try 'knownname' first — this is the standard attribute
                        # X4 uses for the localised sector name reference.
                        # Fall back to 'name' if knownname isn't present.
                        for attr in ('knownname', 'name'):
                            val = elem.get(attr, '')
                            resolved = resolve_sector(val, sector_names)
                            if resolved != "Unknown Sector":
                                current_sector = resolved
                                break

                    # ── STATION DETECTION ──────────────────────────────────────
                    # A component is a player station if:
                    #   1. It has owner="player"
                    #   2. Its class is one of our known station class types
                    if (elem.get('owner') == 'player' and
                            comp_class in STATION_CLASSES):

                        macro     = elem.get('macro', '')
                        code      = elem.get('code', '')
                        name_attr = elem.get('name')       # custom name set by player
                        nameindex = elem.get('nameindex', '') # auto-generated index
                        overviews = elem.get('overviewgraphs', '') # production wares

                        # Build the best display name we can from available data.
                        # Priority: custom name > HQ special case > production-based name
                        if name_attr:
                            # Player gave this station a custom name — use it directly
                            display_name = name_attr
                        elif 'headquarters' in macro.lower():
                            # Player HQ has a distinctive macro name
                            display_name = f"Player HQ ({code})" if code else "Player HQ"
                        elif overviews:
                            # Use the production overview to describe what this station does.
                            # overviewgraphs="energycells ore refinedmetals" becomes
                            # "Station #2 [Energycells, Ore, Refinedmetals] (CAB-143)"
                            wares = overviews.replace(' ', ', ').title()
                            display_name = f"Station #{nameindex} [{wares}] ({code})"
                        else:
                            # Last resort — just use the index and code
                            display_name = f"Station #{nameindex} ({code})" if nameindex else f"Station ({code})"

                        entry = {
                            "name":       display_name,
                            "code":       code,
                            "class":      comp_class,
                            "macro":      macro,
                            "sector":     current_sector,
                            "production": overviews,
                        }

                        # Deduplicate by station code to avoid double-counting.
                        # This can happen if the same station tag appears in
                        # multiple XML contexts (e.g. construction snapshots).
                        if not any(s["code"] == code for s in data["stations"]):
                            data["stations"].append(entry)

                # ── MEMORY MANAGEMENT ──────────────────────────────────────────
                # After processing an element's closing tag, we clear it from
                # memory. This is critical for large files — without this, Python
                # would accumulate the entire XML tree in RAM.
                # We only do this on 'end' events because 'start' events fire
                # before child data is available; clearing too early loses data.
                if event == 'end':
                    elem.clear()

    except ET.ParseError as e:
        print(f"\n[XML Error] The save file has a formatting issue: {e}")
        print("This can happen with saves that were interrupted mid-write.")
        raise
    except Exception as e:
        print(f"\n[Error] Unexpected problem during scan: {e}")
        raise

    return data


# ═════════════════════════════════════════════════════════════════════════════
#  SECTION 4 — PASS 2: FACTION REPUTATION
# ═════════════════════════════════════════════════════════════════════════════

def scan_reputation(file_path: pathlib.Path) -> list:
    """
    Makes a second pass through the save file to extract faction reputation.

    WHY A SECOND PASS?
    iterparse() can't look backwards or sideways in the XML tree — it only
    knows the current element, not its parent. Reputation data requires knowing
    which faction block we're inside (the parent), which we lose track of during
    the first pass due to the complexity of the station scanning logic.
    A dedicated second pass is cleaner and more reliable.

    HOW REPUTATION IS STORED IN X4:
    The player's standing with other factions is stored in the player's own
    faction block, NOT in each other faction's block. It looks like this:

        <faction id="player">
          <relations>
            <relation faction="argon" relation="0.0032"/>
            <relation faction="antigone" relation="0.0032"/>
            ...
            <booster faction="argon" relation="0.2562" time="326867.385"/>
          </relations>
        </faction>

    The 'relation' value is the base standing. 'booster' entries are temporary
    reputation bonuses (e.g. from completing missions) that decay over time.
    The true effective reputation is base + booster combined.

    We stop scanning as soon as we exit the player faction block using 'break',
    which avoids reading the entire 700MB file unnecessarily.
    """
    reputation     = []
    in_player_fac  = False   # True while inside <faction id="player">
    in_relations   = False   # True while inside the <relations> sub-block
    base_relations = {}      # { faction_id: base_value }
    boosters       = {}      # { faction_id: booster_value }

    print(f"[Scanning] Pass 2 — faction reputation...")

    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        context = ET.iterparse(f, events=('start', 'end'))

        for event, elem in context:
            tag = elem.tag

            # Detect entry into the player's faction block
            if event == 'start' and tag == 'faction' and elem.get('id') == 'player':
                in_player_fac = True

            if in_player_fac:
                # Detect entry into the relations sub-block
                if event == 'start' and tag == 'relations':
                    in_relations = True

                # Read each faction's base reputation value
                if in_relations and event == 'start' and tag == 'relation':
                    fid = elem.get('faction')
                    try:
                        base_relations[fid] = float(elem.get('relation', '0'))
                    except ValueError:
                        base_relations[fid] = 0.0

                # Read booster values (temporary reputation bonuses from missions etc.)
                if in_relations and event == 'start' and tag == 'booster':
                    fid = elem.get('faction')
                    try:
                        boosters[fid] = float(elem.get('relation', '0'))
                    except ValueError:
                        boosters[fid] = 0.0

                if event == 'end' and tag == 'relations':
                    in_relations = False

                # Detect exit from the player faction block — stop scanning here
                # to avoid processing the rest of the 700MB file unnecessarily.
                if event == 'end' and tag == 'faction' and elem.get('id') == 'player':
                    in_player_fac = False
                    break

            if event == 'end':
                elem.clear()

    # Combine base + booster values and build the output list
    for fid, base_val in base_relations.items():

        # Skip internal/non-playable factions that would clutter the report
        if fid in SKIP_FACTIONS:
            continue

        booster_val  = boosters.get(fid, 0.0)
        effective    = base_val + booster_val
        faction_name = FACTION_NAMES.get(fid, fid.title())

        reputation.append({
            "faction_id":   fid,
            "faction_name": faction_name,
            "value":        round(effective, 4),   # true standing (base + boost)
            "base":         round(base_val, 4),    # standing without boosts
            "booster":      round(booster_val, 4), # active temporary bonus
            "tier":         reputation_label(effective),
        })

    # Sort best reputation first so the most important relationships appear at top
    reputation.sort(key=lambda x: x["value"], reverse=True)
    return reputation


# ═════════════════════════════════════════════════════════════════════════════
#  SECTION 5 — DISPLAY AND EXPORT
# ═════════════════════════════════════════════════════════════════════════════

def display_results(data: dict):
    """
    Prints the extracted empire data to the console in a readable format.
    The reputation bar visualises standing on a scale from -30 to +30,
    with filled blocks (█) representing positive standing.
    """
    SEP  = "=" * 65
    LINE = "-" * 65

    print(f"\n{SEP}")
    print("      X4 FOUNDATIONS — EMPIRE INTELLIGENCE REPORT v3.0")
    print(SEP)
    print(f"  PILOT          : {data['player_name'] or 'Unknown'}")
    print(f"  CURRENT SECTOR : {data['player_sector'] or 'Unknown'}")
    credits_str = format_credits(data['player_credits']) if data['player_credits'] else "Not found"
    print(f"  CREDITS        : {credits_str}")
    print(LINE)

    # Station summary
    print(f"  OWNED STATIONS ({len(data['stations'])} found):")
    if data["stations"]:
        for s in data["stations"]:
            print(f"    → {s['name']}")
            prod = f" | Produces: {s['production']}" if s['production'] else ""
            print(f"       Sector: {s['sector']}{prod}")
    else:
        print("    No player-owned stations detected.")
    print(LINE)

    # Reputation table with visual bar
    print(f"  FACTION REPUTATION ({len(data['reputation'])} factions):")
    if data["reputation"]:
        for r in data["reputation"]:
            # Scale the reputation value (-30 to +30) onto a 20-character bar.
            # This gives a quick visual sense of where each faction stands.
            bar_val = int((r['value'] + 30) / 60 * 20)
            bar_val = max(0, min(20, bar_val))
            bar     = "█" * bar_val + "░" * (20 - bar_val)
            # Show booster contribution separately so it's clear what's temporary
            booster = f" (+{r['booster']:.3f} boost)" if r['booster'] != 0 else ""
            print(f"    {r['faction_name']:<32} {r['value']:>+7.4f}  [{bar}]  {r['tier']}{booster}")
    else:
        print("    No reputation data found.")

    print(SEP)


def export_json(data: dict):
    """
    Exports the extracted empire data as a JSON file next to the script.

    The JSON format is ideal for feeding into an AI prompt because:
      - It's compact and structured
      - The AI can parse it reliably
      - You can paste it directly into a chat without manual formatting

    Example AI prompt:
      "Here is my current X4 Foundations empire state. Based on this,
       what should I prioritise next? [paste JSON here]"
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
    """
    Main execution flow:
      1. Check the save file exists
      2. Load sector name lookup from the language file
      3. Pass 1: scan for player data and stations
      4. Pass 2: scan for faction reputation
      5. Display results and export JSON

    The entire block is wrapped in try/except so that if anything goes wrong,
    the error is displayed clearly before the console window closes, rather
    than the window vanishing instantly (which happens on Windows double-click).
    """
    try:
        # Verify the save file is present before doing anything else
        if not SAVE_FILE.exists():
            print(f"Error: '{SAVE_FILE.name}' not found in the script folder.")
            print(f"Expected location: {SAVE_FILE}")
            print("Please rename your unzipped X4 save to 'save_001.xml'")
            print("and place it in the same folder as this script.")
            input("\nPress Enter to exit...")
            exit(1)

        # Step 1: Load sector names from the language file.
        # If the file is missing, sector names will show as IDs but won't crash.
        sector_names = load_sector_names(LANG_FILE)

        # Step 2: First pass — player identity, credits, stations
        game_data = scan_save(SAVE_FILE, sector_names)

        # Step 3: Second pass — faction reputation
        # Done separately because iterparse loses parent context during the
        # complex nested scanning in pass 1.
        game_data["reputation"] = scan_reputation(SAVE_FILE)

        # Step 4: Show results and write JSON output
        display_results(game_data)
        export_json(game_data)

    except Exception as e:
        # Catch any unhandled error, print a full traceback so we can debug it,
        # then wait for input so the window doesn't close immediately on Windows.
        print(f"\n[FATAL ERROR] {e}")
        traceback.print_exc()

    input("\nPress Enter to exit...")