# ─────────────────────────────────────────────────────────────────────────────
#  FACTION NAME LOOKUP
#  Maps short internal faction IDs to full display names.
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

# Internal/non-playable factions excluded from the reputation report.
SKIP_FACTIONS = {
    "criminal", "civilian", "smuggler", "outlaw", "visitor",
    "scavenger", "kaori", "court", "alliance", "player",
}

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