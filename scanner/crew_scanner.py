import re
from lxml import etree as ET

# Matches unresolved language reference tokens like "{20101,22603}" that appear
# in some name attributes. The game resolves these at runtime — we can't use
# them as display names, so callers skip any name that matches this pattern.
LANG_STRING_RE = re.compile(r'^\{\d+,\d+\}$')


def _parse_character_macro(macro: str) -> dict:
    """
    Extracts appearance metadata from a character macro string.

    X4 character macros follow this naming convention:
        character_{faction}_{gender}_{ethnicity}_{role}_{variant}_macro
        character_{faction}_generic_{variant}_macro   (no gender/ethnicity)

    We store these so the UI can build a character file card per crew member.
    The seed (stored separately) will eventually let us generate the real name.
    """
    inner  = macro.removeprefix('character_').removesuffix('_macro')
    parts  = inner.split('_')
    result = {"faction": None, "gender": None, "ethnicity": None, "variant": None}

    if not parts:
        return result

    result["faction"] = parts[0]

    if len(parts) < 2:
        return result

    if parts[1] in ('male', 'female'):
        result["gender"] = parts[1]
        if len(parts) > 2 and parts[2] in ('afr', 'asi', 'cau'):
            result["ethnicity"] = parts[2]
            if len(parts) > 4:
                result["variant"] = parts[4]
        elif len(parts) > 3:
            result["variant"] = parts[3]
    elif parts[1] == 'generic':
        if len(parts) > 2:
            result["variant"] = parts[2]

    return result


def _parse_pilot(ship_elem: ET.Element) -> dict:
    """
    Finds the pilot assigned to the 'aipilot' control post and returns their
    name and skill ratings.

    Pilots are stored via <control><post id="aipilot" component="[0x348]"/>.
    The referenced ID points to a <component class="npc"> element elsewhere in
    the ship subtree that holds the actual name and <traits><skills> block.

    Returns {"name": str | None, "skills": dict}.
    Missing skills keys mean 0 stars — we only store what X4 wrote.
    """
    control  = ship_elem.find('control')
    pilot_id = None
    if control is not None:
        for post in control.findall('post'):
            if post.get('id') == 'aipilot':
                pilot_id = post.get('component')
                break

    if not pilot_id:
        return {"name": None, "skills": {}}

    for npc in ship_elem.iter('component'):
        if npc.get('id') != pilot_id or npc.get('class') != 'npc':
            continue

        raw_name = npc.get('name')
        if not raw_name or LANG_STRING_RE.match(raw_name):
            return {"name": None, "skills": {}}

        skills = {}
        traits = npc.find('traits')
        if traits is not None:
            skills_elem = traits.find('skills')
            if skills_elem is not None:
                for attr in ('piloting', 'management', 'morale', 'engineering', 'boarding'):
                    val = skills_elem.get(attr)
                    if val is not None:
                        skills[attr] = int(val)

        return {"name": raw_name, "skills": skills}

    return {"name": None, "skills": {}}


def _extract_people(
    ship_elem:   ET.Element,
    ship_name:   str,
    ship_code:   str,
    ship_sector: str,
) -> list[dict]:
    """
    Extracts service crew and marines from the <people> block on a player ship.

    Service crew and marines are stored as <person> elements with an <npcseed>
    child rather than as full NPC components with names. We assign generic
    placeholder names (e.g. "Marine #2") because we can't decode the seed's
    name-generation algorithm without the game's runtime tables.

    The <people> block is separate from the <control><post> system used for
    pilots and managers — don't confuse the two.
    """
    crew    = []
    people  = ship_elem.find('people')
    if people is None:
        return crew

    service_count = 0
    marine_count  = 0

    for person in people.findall('person'):
        role = person.get('role', '')
        if role not in ('service', 'marine'):
            continue

        skills_elem = person.find('skills')
        skills = {}
        if skills_elem is not None:
            for attr in ('piloting', 'management', 'morale', 'engineering', 'boarding'):
                val = skills_elem.get(attr)
                if val is not None:
                    skills[attr] = int(val)

        if role == 'service':
            service_count += 1
            name = f"Service Crew #{service_count}"
        else:
            marine_count += 1
            name = f"Marine #{marine_count}"

        char_info = _parse_character_macro(person.get('macro', ''))
        seed_elem = person.find('npcseed')
        seed      = seed_elem.get('seed') if seed_elem is not None else None

        crew.append({
            "name":          name,
            "role":          role,
            "skills":        skills,
            "assigned_to":   ship_name,
            "assigned_code": ship_code,
            "assigned_type": "ship",
            "sector":        ship_sector,
            "faction":       char_info["faction"],
            "gender":        char_info["gender"],
            "ethnicity":     char_info["ethnicity"],
            "variant":       char_info["variant"],
            "seed":          seed,
        })

    return crew


def _parse_manager(station_elem: ET.Element) -> dict | None:
    """
    Finds the station's assigned manager NPC and returns their name and skills.

    Managers are stored via <control><post id="manager" component="[0xABC]"/>.
    The referenced ID points to a <component class="npc"> in the station subtree.

    Returns None if the manager slot is vacant or the name is unresolved.
    """
    control = station_elem.find('control')
    if control is None:
        return None

    manager_id = None
    for post in control.findall('post'):
        if post.get('id') == 'manager':
            manager_id = post.get('component')
            break

    if not manager_id:
        return None

    for npc in station_elem.iter('component'):
        if npc.get('id') != manager_id or npc.get('class') != 'npc':
            continue

        raw_name = npc.get('name')
        if not raw_name or LANG_STRING_RE.match(raw_name):
            return None

        skills = {}
        traits = npc.find('traits')
        if traits is not None:
            skills_elem = traits.find('skills')
            if skills_elem is not None:
                for attr in ('piloting', 'management', 'morale', 'engineering', 'boarding'):
                    val = skills_elem.get(attr)
                    if val is not None:
                        skills[attr] = int(val)

        return {"name": raw_name, "skills": skills}

    return None
