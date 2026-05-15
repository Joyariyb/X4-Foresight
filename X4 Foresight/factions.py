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