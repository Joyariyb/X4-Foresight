import pathlib
import re
from lxml import etree as ET

from data.factions import FACTION_NAMES
from data.wares import WARE_NAMES
from scanner.language import factory_name_from_ware, macro_to_sector_name, open_save, resolve_text_ref

# ─────────────────────────────────────────────────────────────────────────────
#  CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

STATION_CLASSES = {"station", "factory", "headquarters", "complex"}

# Roman numerals for nameindex conversion. NPC station counts rarely exceed 30.
_ROMAN = [
    "", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX",
    "X", "XI", "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX",
    "XX", "XXI", "XXII", "XXIII", "XXIV", "XXV", "XXVI", "XXVII", "XXVIII", "XXIX",
    "XXX", "XXXI", "XXXII", "XXXIII", "XXXIV", "XXXV", "XXXVI", "XXXVII", "XXXVIII", "XXXIX",
    "XL", "XLI", "XLII", "XLIII", "XLIV", "XLV", "XLVI", "XLVII", "XLVIII", "XLIX",
]

# Faction short codes derived from FACTION_NAMES bracket notation, e.g. "argon" -> "ARG".
_FACTION_SHORT_RE = re.compile(r'\[(\w+)\]')
FACTION_SHORT: dict[str, str] = {}
for _fid, _display in FACTION_NAMES.items():
    _m = _FACTION_SHORT_RE.match(_display)
    if _m:
        FACTION_SHORT[_fid] = _m.group(1)


# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _to_roman(n: int) -> str:
    if 0 < n < len(_ROMAN):
        return _ROMAN[n]
    return str(n)



def _build_display_name(raw_name: str, nameindex: str, code: str, owner: str) -> str:
    """
    Assembles the full display name for an NPC station.

    Format matches X4's in-game UI:
        "{FactionAbbr} {WareName} Factory {RomanNumeral} ({StationCode})"
    e.g. "TEL Advanced Electronics Factory I (CYS-158)"
    """
    parts = []

    short = FACTION_SHORT.get(owner.lower(), '')
    if short:
        parts.append(short)

    if raw_name:
        parts.append(raw_name)

    try:
        idx = int(nameindex)
        if idx > 0:
            parts.append(_to_roman(idx))
    except (ValueError, TypeError):
        if nameindex:
            parts.append(nameindex)

    display = " ".join(parts)
    if code:
        display += f" ({code})"
    return display


# ─────────────────────────────────────────────────────────────────────────────
#  PASS 4 — NPC STATIONS IN PLAYER SECTORS
# ─────────────────────────────────────────────────────────────────────────────

def scan_npc_stations(
    file_path: pathlib.Path,
    sector_names: dict,
    player_sectors: set,
    language_texts: dict | None = None,
    factory_names: dict | None = None,
) -> list[dict]:
    """
    Streams the save file and returns all NPC stations located in sectors
    where the player also has a station.

    Name resolution uses three paths in order (matching X4PlayerShipTradeAnalyzer):
      A. 'name' attribute on the component element
      B. 'basename' attribute as fallback
      C. Deferred: read into production children to find the factory ware type

    For Path C, the parser keeps a 'seeking_name' flag and watches for:
      - <production originalproduct="food"> → "Food Factory"
      - <component class="production" macro="prod_gen_food_01_macro"> → same
    The macro token at index [2] is the ware ID: prod_{faction}_{ware}_{variant}_macro.

    Traded wares are captured from the <trade wares="..."> attribute, which
    lists all ware IDs the station deals in as a space-separated string.

    Args:
        file_path:      Path to .xml or .xml.gz save file.
        sector_names:   Sector macro -> display name dict from load_sector_names().
        player_sectors: Set of sector names from Pass 1 (e.g. {"Grand Exchange I"}).

    Returns:
        List of dicts with keys: name, owner, sector, code, macro, wares.
    """
    if not player_sectors:
        return []

    texts  = language_texts or {}
    result: list[dict] = []

    depth              = 0
    current_sector     = "Unknown Sector"
    npc_station_depth  = None   # XML depth where the active NPC station opened
    player_station_depth = None # XML depth of the player station we're skipping over
    pending: dict | None = None # partial data for the NPC station being captured
    seeking_name       = False  # True when we still need a name from production children

    print(f"[Scanning] Pass 4 — NPC stations in {len(player_sectors)} player sector(s)...")

    try:
        with open_save(file_path) as f:
            context = ET.iterparse(f, events=('start', 'end'))

            for event, elem in context:
                tag = elem.tag

                # ── START ─────────────────────────────────────────────────────
                if event == 'start':
                    depth += 1

                    if tag == 'component':
                        comp_class = elem.get('class', '')
                        owner      = elem.get('owner', '')

                        # Keep current_sector up to date for all stations below it.
                        if comp_class == 'sector':
                            macro    = elem.get('macro', '')
                            resolved = macro_to_sector_name(macro, sector_names)
                            if resolved:
                                current_sector = resolved

                        # Mark player stations so we don't capture anything inside them.
                        # (NPC-owned sub-components can appear inside player stations in
                        # theory; this guard keeps the results clean.)
                        elif (
                            player_station_depth is None
                            and npc_station_depth is None
                            and comp_class in STATION_CLASSES
                            and owner == 'player'
                        ):
                            player_station_depth = depth

                        # Detect NPC station in a sector the player occupies.
                        elif (
                            npc_station_depth is None
                            and player_station_depth is None
                            and comp_class in STATION_CLASSES
                            and owner
                            and owner != 'player'
                            and current_sector in player_sectors
                        ):
                            raw_name  = resolve_text_ref(
                                elem.get('name', '') or elem.get('basename', ''),
                                texts,
                            )
                            code      = elem.get('code', '')
                            nameindex = elem.get('nameindex', '0')
                            macro     = elem.get('macro', '')

                            pending = {
                                'owner':     owner,
                                'code':      code,
                                'nameindex': nameindex,
                                'sector':    current_sector,
                                'name':      raw_name,
                                'macro':     macro,
                                'wares':     [],
                            }
                            npc_station_depth = depth
                            seeking_name = not bool(raw_name)

                    # Inside NPC station — resolve name from production children (Path C).
                    if npc_station_depth is not None and seeking_name:
                        if tag == 'production':
                            product = elem.get('originalproduct', '')
                            if product:
                                pending['name'] = factory_name_from_ware(product, factory_names)
                                seeking_name = False

                        elif tag == 'component' and elem.get('class') == 'production':
                            macro  = elem.get('macro', '')
                            parts  = macro.split('_')
                            # macro format: prod_{faction}_{ware}_{variant}_macro
                            ware_id = parts[2] if len(parts) >= 4 else ''
                            pending['name']  = factory_name_from_ware(ware_id, factory_names) if ware_id else macro
                            pending['macro'] = macro
                            seeking_name = False

                    # Inside NPC station — capture the station's traded ware list.
                    # The <trade wares="..."> element is a direct child of the station.
                    if (
                        npc_station_depth is not None
                        and tag == 'trade'
                        and depth == npc_station_depth + 1
                    ):
                        wares_str = elem.get('wares', '')
                        if wares_str:
                            pending['wares'] = wares_str.split()

                # ── END ───────────────────────────────────────────────────────
                elif event == 'end':
                    if player_station_depth is not None and depth == player_station_depth:
                        player_station_depth = None

                    elif npc_station_depth is not None and depth == npc_station_depth:
                        if pending is not None:
                            display = _build_display_name(
                                pending['name'],
                                pending['nameindex'],
                                pending['code'],
                                pending['owner'],
                            )
                            wares_display = sorted(
                                WARE_NAMES.get(w, w.replace('_', ' ').title())
                                for w in pending['wares']
                            )
                            result.append({
                                'name':   display,
                                'owner':  pending['owner'],
                                'sector': pending['sector'],
                                'code':   pending['code'],
                                'macro':  pending['macro'],
                                'wares':  wares_display,
                            })
                        npc_station_depth = None
                        pending           = None
                        seeking_name      = False

                    # Always clear elements on end — we read all needed data from
                    # start events (attributes), so there is nothing left to keep.
                    elem.clear()
                    depth -= 1

    except ET.XMLSyntaxError as e:
        print(f"\n[XML Error] Save file has a formatting issue: {e}")
        raise

    print(f"[Scanning] Pass 4 — found {len(result)} NPC station(s).")
    return result
