import pathlib
import xml.etree.ElementTree as ET
from wares import format_wares
from factions import FACTION_NAMES, SKIP_FACTIONS, scale_reputation, reputation_label
from language import macro_to_sector_name, resolve_sector_from_location

# ─────────────────────────────────────────────────────────────────────────────
#  STATION CLASS NAMES
#  The XML 'class' attribute values X4 uses for player-built structures.
# ─────────────────────────────────────────────────────────────────────────────

STATION_CLASSES = {"station", "factory", "headquarters", "complex"}

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