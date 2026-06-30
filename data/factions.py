# Core role: Faction metadata (names, colors, relationships) and reputation scale conversion.

import math
#   • Converting internal log10-scale reputation to in-game display scale (-30..+30)
#   • Mapping reputation scores to descriptive tier labels (At War -> Allied)
#   • Managing faction name lookups and excluding non-playable factions from reports
# =============================================================================

# ─────────────────────────────────────────────────────────────────────────────
#  FACTION NAME LOOKUP
#  Maps short internal faction IDs to full display names used in the game UI.
# 
# Each entry associates a lowercase faction identifier with its canonical name
# as it appears in-game, including faction abbreviations and official titles.
# This lookup is used to present friendly, readable faction names to players.
# ─────────────────────────────────────────────────────────────────────────────

FACTION_NAMES = {
    "argon":            "[ARG] Argon Federation",
    "antigone":         "[ANT] Antigone Republic",
    "hatikvah":         "[HAT] Hatikvah Free League",
    "paranid":          "[PAR] Godrealm of the Paranid",
    "trinity":          "[TRI] Realm of the Trinity",
    "split":            "[ZYA] Zyarth Patriarchy",
    "fallensplit":      "[FAF] Fallen Families",
    "freesplit":        "[FRF] Free Families",
    "teladi":           "[TEL] Teladi Company",
    "ministry":         "[MIN] Ministry of Finance",
    "xenon":            "[XEN] Xenon",
    "khaak":            "[KHK] Kha'ak",
    "buccaneers":       "[BUC] Duke's Buccaneers",
    "scaleplate":       "[SCA] Scale Plate Pact",
    "loanshark":        "[RIP] Riptide Rakers",
    "holyorder":        "[HOP] Holy Order of the Pontifex",
    "holyorderfanatic": "[HOF] Holy Order Faithful",
    "yaki":             "[YAK] Yaki",
    "pioneers":         "[PIO] Segaris Pioneers",
    "terran":           "[TER] Terran Protectorate",
    "boron":            "[BOR] Queendom of Boron",
}

# Reverse lookup: in-game display name (no "[ABC] " prefix) → internal faction id.
# The save's event log tags reputation-gain entries with a {20203,N} language ref
# that resolves to the bare display name ("Teladi Company"), NOT the internal id,
# so combat-kill tallies need this to key by the same faction_id the reputation
# table uses — otherwise the two could never be joined in the Trends hover.
FACTION_ID_BY_DISPLAY = {
    name.split('] ', 1)[-1].lower(): fid
    for fid, name in FACTION_NAMES.items()
}


def faction_id_from_display(display_name: str) -> str:
    """Map a bare faction display name back to its internal id, or '' if unknown.

    '' (rather than a guess) lets callers fall back to storing the raw display
    name for minor factions that aren't in FACTION_NAMES, instead of silently
    misattributing their kills to a known faction."""
    return FACTION_ID_BY_DISPLAY.get((display_name or '').strip().lower(), '')


# Factions that are excluded from the reputation report.
# These represent neutral entities, player classification labels, or background NPCs
# that do not have meaningful faction relationships in the game.
# 
# Exclusions include:
#   • Role-based classifications (criminal, civilian, smuggler, outlaw, scavenger)
#   • Background factions without relationship dynamics (kaori, court, alliance)
#   • Special entities like visitor state and player classification
SKIP_FACTIONS = {
    "criminal", "civilian", "smuggler", "outlaw", "visitor",
    "scavenger", "kaori", "court", "alliance", "player",
}


def scale_reputation(raw: float) -> float:
    """
    Converts X4's internal reputation float to the in-game display scale.

    The game stores reputation on a log10-based internal scale. This function
    transforms that value to match the in-game UI display range of -30 to +30
    using the formula:
        display = log10(raw) * 10 + 30

    Special behaviors:
      • A raw value of 0 is treated as minimum reputation (-30.0)
      • Raw values below 0 mirror the positive curve (symmetrical handling)
      • Results are clamped to the -30..+30 display range

    Note: For very small positive raw values approaching zero, the log10
    transformation will approach the minimum (-30.0) before being clamped.

    Examples:
        scale_reputation(0.1)     → approximately 30.0 (maximum allied)
        scale_reputation(1.0)      → approximately 40.0, clamped to +30.0
        scale_reputation(0.01)     → approximately 20.0 (friendly tier)
        scale_reputation(-0.1)     → mirrored positive value
    """
    if raw == 0.0:
        return -30.0
    if raw < 0:
        return -scale_reputation(-raw)   # mirror for negatives
    scaled = math.log10(raw) * 10.0 + 30.0
    return max(-30.0, min(30.0, scaled))


def reputation_label(scaled_value: float) -> str:
    """
    Returns a descriptive tier label based on the scaled (in-game) reputation value.

    The function maps the numeric reputation score to one of five relationship tiers
    that appear in the game's faction menu: "At War", "Hostile", "Neutral",
    "Friendly", and "Allied".

    Thresholds are intentionally approximate because X4's actual unlock points
    for prestige missions and benefits vary per faction. These thresholds provide
    a reasonable generalization across all factions for display purposes.

    The returned label corresponds directly to the in-game UI text shown when
    hovering over or selecting a faction in the relationship screen.

    Threshold behavior:
        scaled_value >= 20     → "Allied"      (strongest alliance)
        scaled_value >= 10     → "Friendly"    (positive relationship)
        scaled_value >=  0     → "Neutral"     (no special standing)
        scaled_value >= -10    → "Hostile"     (adversarial stance)
        otherwise              → "At War"      (active conflict)

    Note: The thresholds are inclusive; a value of exactly 10.0 returns "Friendly".
    """
    if scaled_value >= 20:  return "Allied"
    if scaled_value >= 10:  return "Friendly"
    if scaled_value >= 0:   return "Neutral"
    if scaled_value >= -10: return "Hostile"
    return "At War"
