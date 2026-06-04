"""
v2/scanner/ship_names.py

Pure ship naming / classification helpers — macro string in, display data out.
No handler state, no ScanContext, no XML. Shared by ShipHandler (extraction),
TradePostProcessor (transport names on trade rows), and any display/export code,
so there is ONE source of truth for "what do we call this ship".

Resolution mirrors v1's resolve_ship_type(), but the display helper keeps v2's
richer model: a ship's custom name and its type name stay distinct, and
ship_display_name() chooses between them rather than overwriting one with the
other.
"""
from __future__ import annotations
import re
from data.ships import SHIP_NAMES


# Maps the ship class attribute to the short size notation used in the UI.
# Verified: the save uses exactly these four class values for ships.
SIZE_LABELS: dict[str, str] = {
    "ship_s":  "S",
    "ship_m":  "M",
    "ship_l":  "L",
    "ship_xl": "XL",
}

# Role patterns matched against the ship macro string.
# Order matters — more specific patterns (miner_solid) must come before
# the broader parent (miner) so the correct label wins.
_ROLE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'miner_solid',     re.I), "Miner (Solid)"),
    (re.compile(r'miner_liquid',    re.I), "Miner (Liquid)"),
    (re.compile(r'miner_gas',       re.I), "Miner (Gas)"),
    (re.compile(r'miner',           re.I), "Miner"),
    (re.compile(r'trans_container', re.I), "Freighter"),
    (re.compile(r'trans_',          re.I), "Transport"),
    (re.compile(r'heavyfighter',    re.I), "Heavy Fighter"),
    (re.compile(r'fighter',         re.I), "Fighter"),
    (re.compile(r'corvette',        re.I), "Corvette"),
    (re.compile(r'frigate',         re.I), "Frigate"),
    (re.compile(r'bomber',          re.I), "Bomber"),
    (re.compile(r'destroyer',       re.I), "Destroyer"),
    (re.compile(r'carrier',         re.I), "Carrier"),
    (re.compile(r'resupplier',      re.I), "Resupplier"),
    (re.compile(r'builder',         re.I), "Builder"),
    (re.compile(r'scout',           re.I), "Scout"),
]

# Maps the 3-letter faction prefix in ship macro names to a display name.
# X4 macro format: ship_{prefix}_{size}_{role}_{index}_{variant}_macro
# e.g. "ship_arg_l_trans_container_01_b_macro" → prefix "arg" → "Argon"
# Used to flag ships whose hull faction differs from their current owner
# (captured ships, prizes, faction cross-ownership).
_HULL_FACTION: dict[str, str] = {
    "arg": "Argon",
    "tel": "Teladi",
    "par": "Paranid",
    "tri": "Paranid",   # Paranid religious faction — same hull stock
    "spl": "Split",
    "ter": "Terran",
    "bor": "Boron",
    "xen": "Xenon",
    "yak": "Yaki",
    "pir": "Buccaneer",
    "kha": "Kha'ak",
    "buc": "Buccaneer",
    "atf": "Terran",    # ATF uses Terran hull designs
    "pio": "Pioneer",
    "gen": "Generic",   # cross-faction hull (e.g. generic miners/freighters)
}

# Matches unresolved language reference tokens like "{20101,22603}" that appear
# in some name attributes. The game resolves these at runtime — we treat any
# name matching this as "not a real custom name".
LANG_REF_RE = re.compile(r'^\{\d+,\d+\}$')


def extract_role(macro: str) -> str:
    """Returns a human-readable role label by matching the macro against _ROLE_PATTERNS."""
    for pattern, label in _ROLE_PATTERNS:
        if pattern.search(macro):
            return label
    return "Unknown"


def extract_hull_origin(macro: str) -> tuple[str, str]:
    """
    Returns (faction_prefix, display_name) for the ship's original hull faction.

    The prefix is the second underscore-delimited segment in the macro, e.g.
    "ship_arg_l_trans_container_01_b_macro" → ("arg", "Argon").
    If the macro doesn't follow the expected format, returns ("", "Unknown").
    """
    parts = macro.split("_")
    if len(parts) > 1:
        prefix = parts[1].lower()
        return prefix, _HULL_FACTION.get(prefix, prefix.title())
    return "", "Unknown"


def resolve_ship_type(macro: str) -> str:
    """
    Returns a display name for the ship TYPE from the macro string.

    Priority:
      1. SHIP_NAMES lookup (data/ships.py) — exact in-game names, e.g. "Magnetar Vanguard"
      2. Constructed fallback from macro parts — e.g. "Argon L Freighter (B)"
    """
    if macro in SHIP_NAMES:
        return SHIP_NAMES[macro]

    parts = macro.split("_")
    if len(parts) < 4:
        return macro  # too short to parse safely — return raw macro

    _, hull_name = extract_hull_origin(macro)
    size         = parts[2].upper()              # e.g. "L", "M", "XL"
    role         = extract_role(macro)

    # Variant letter (a, b, c...) is the last segment before the trailing "macro"
    # token, e.g. "ship_arg_l_trans_container_01_b_macro" → last core part = "b".
    # Only treat it as a variant if it's exactly one alpha character.
    core    = parts[:-1]  # strip the trailing "macro" token
    last    = core[-1] if core else ""
    variant = last.upper() if len(last) == 1 and last.isalpha() else None

    name = f"{hull_name} {size} {role}"
    if variant:
        name += f" ({variant})"
    return name


def ship_display_name(macro: str, custom_name: str | None = None) -> str:
    """
    The canonical name to SHOW for a ship.

    Returns the player's custom name when it is a real string (not an unresolved
    "{page,id}" language token); otherwise the resolved type name. Never returns
    a bare code — that is the caller's to append, e.g. f"{display} [{code}]".
    """
    if custom_name and not LANG_REF_RE.match(custom_name):
        return custom_name
    return resolve_ship_type(macro)
