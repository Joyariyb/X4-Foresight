import pathlib
from lxml import etree as ET
from data.factions import FACTION_NAMES, SKIP_FACTIONS, scale_reputation, reputation_label
from scanner.language import open_save


def scan_reputation(file_path: pathlib.Path) -> list:
    """
    Streams the save file and extracts faction reputation standings.

    Reads base standings and temporary boosters from the player faction's
    <relations> block, then scales both to the in-game display range (-30..+30)
    using the same log10 curve the game UI applies.

    Returns a list of dicts sorted by total reputation (highest first), each with:
        faction_id, faction_name, value (scaled total), base, booster, tier label.
    """
    in_player_fac  = False
    in_relations   = False
    base_relations = {}
    boosters       = {}

    print("[Scanning] Pass 2 — faction reputation...")

    with open_save(file_path) as f:
        context = ET.iterparse(f, events=('start', 'end'))

        for event, elem in context:
            tag = elem.tag

            if event == 'start' and tag == 'faction' and elem.get('id') == 'player':
                in_player_fac = True

            if in_player_fac:
                if event == 'start' and tag == 'relations':
                    in_relations = True

                if in_relations and event == 'start' and tag == 'relation':
                    fid = elem.get('faction')
                    try:
                        base_relations[fid] = float(elem.get('relation', '0'))
                    except ValueError:
                        base_relations[fid] = 0.0

                if in_relations and event == 'start' and tag == 'booster':
                    fid = elem.get('faction')
                    try:
                        boosters[fid] = float(elem.get('relation', '0'))
                    except ValueError:
                        boosters[fid] = 0.0

                if event == 'end' and tag == 'relations':
                    in_relations = False

                if event == 'end' and tag == 'faction' and elem.get('id') == 'player':
                    in_player_fac = False
                    break

            if event == 'end':
                elem.clear()

    reputation = []
    for fid in set(base_relations) | set(boosters):
        if fid in SKIP_FACTIONS:
            continue

        raw_base    = base_relations.get(fid, 0.0)
        raw_booster = boosters.get(fid, 0.0)
        raw_total   = raw_base + raw_booster

        scaled_total   = scale_reputation(raw_total)
        scaled_base    = scale_reputation(raw_base)    if raw_base    != 0 else 0.0
        scaled_booster = scale_reputation(raw_booster) if raw_booster != 0 else 0.0

        reputation.append({
            "faction_id":   fid,
            "faction_name": FACTION_NAMES.get(fid, fid.title()),
            "value":        round(scaled_total,   2),
            "base":         round(scaled_base,    2),
            "booster":      round(scaled_booster, 2),
            "tier":         reputation_label(scaled_total),
        })

    reputation.sort(key=lambda x: x["value"], reverse=True)
    return reputation
