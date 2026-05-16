# ─────────────────────────────────────────────────────────────────────────────
#  WARE DISPLAY NAMES
#  X4 stores production module macros as 'prod_gen_WARENAME_macro'.
#  This lookup converts the extracted WARENAME (lowercase) to a proper
#  human-readable display name with spaces and capitalisation.
#
#  HOW THIS IS USED:
#  scanner.py extracts the ware name from each production module macro using
#  a regular expression, then looks it up here. If a ware isn't listed,
#  the fallback is title-cased with underscores replaced by spaces — which
#  works for most names but won't always look perfect.
#
#  Add more entries here if you build stations producing unlisted wares.
# ─────────────────────────────────────────────────────────────────────────────

WARE_NAMES = {
    # Raw resources
    "ore":                        "Ore",
    "silicon":                    "Silicon",
    "ice":                        "Ice",
    "hydrogen":                   "Hydrogen",
    "helium":                     "Helium",
    "methane":                    "Methane",
    "nividium":                   "Nividium",
    # Refined / basic materials
    "refinedmetals":              "Refined Metals",
    "siliconwafers":              "Silicon Wafers",
    "energycells":                "Energy Cells",
    "graphene":                   "Graphene",
    "superfluidcoolant":          "Superfluid Coolant",
    "antimattercells":            "Antimatter Cells",
    "plasmaconductors":           "Plasma Conductors",
    "quantumtubes":               "Quantum Tubes",
    "microchips":                 "Microchips",
    "advancedelectronics":        "Advanced Electronics",
    "advancedcomposites":         "Advanced Composites",
    "scanningarrays":             "Scanning Arrays",
    "engineparts":                "Engine Parts",
    "hullparts":                  "Hull Parts",
    "smartchips":                 "Smart Chips",
    "dronecomponents":            "Drone Components",
    "fieldcoils":                 "Field Coils",
    "majadust":                   "Maja Dust",
    "teladianium":                "Teladianium",
    "protectivecoating":          "Protective Coating",
    "computronicsubstrate":       "Computronic Substrate",
    "metallic microlattice":      "Metallic Microlattice",
    "metallicmicrolattice":       "Metallic Microlattice",
    "siliconcarbidemicrolattice": "Silicon Carbide Microlattice",
    "carboncarbide":              "Carbon Carbide",
    # Ship / station components
    "weaponcomponents":           "Weapon Components",
    "missilecomponents":          "Missile Components",
    "shieldcomponents":           "Shield Components",
    "turretcomponents":           "Turret Components",
    "claytronics":                "Claytronics",
    "antimatterconverters":       "Antimatter Converters",
    "redundantcoolingsystems":    "Redundant Cooling Systems",
    "podcontrolsystems":          "Pod Control Systems",
    # Food / consumables
    "foodrations":                "Food Rations",
    "medicalsupplies":            "Medical Supplies",
    "spaceweed":                  "Space Weed",
    "spacefuel":                  "Space Fuel",
    "maja snails":                "Maja Snails",
    "majasnails":                 "Maja Snails",
    "stimulants":                 "Stimulants",
    "hallucinogenics":            "Hallucinogenics",
}


def format_wares(overviewgraphs: str) -> str:
    """
    LEGACY FUNCTION — no longer called by the main scanner.
    Previously converted the 'overviewgraphs' attribute from the station XML
    into a readable list, but that data was unreliable (it reflected UI display
    hints, not actual production modules). Production is now parsed directly
    from <construction><sequence> entries in scanner.py.

    Kept here in case it's useful for debugging or future reference.
    """
    if not overviewgraphs:
        return ""
    wares = overviewgraphs.strip().split()
    display = [WARE_NAMES.get(w.lower(), w.replace('_', ' ').title()) for w in wares]
    return ", ".join(display)