# ─────────────────────────────────────────────────────────────────────────────
#  WARE DISPLAY NAMES
#  X4 stores production ware IDs as single concatenated lowercase strings
#  (e.g. "advancedelectronics"). This lookup converts them to proper
#  human-readable names with spaces (e.g. "Advanced Electronics").
#  Add more entries here if you build stations producing unlisted wares.
# ─────────────────────────────────────────────────────────────────────────────

WARE_NAMES = {
    # Raw resources
    "ore":                    "Ore",
    "silicon":                "Silicon",
    "ice":                    "Ice",
    "hydrogen":               "Hydrogen",
    "helium":                 "Helium",
    "methane":                "Methane",
    "nividium":               "Nividium",
    # Refined / basic materials
    "refinedmetals":          "Refined Metals",
    "siliconwafers":          "Silicon Wafers",
    "energycells":            "Energy Cells",
    "graphene":               "Graphene",
    "superfluidcoolant":      "Superfluid Coolant",
    "antimattercells":        "Antimatter Cells",
    "plasmaconductors":       "Plasma Conductors",
    "quantumtubes":           "Quantum Tubes",
    "microchips":             "Microchips",
    "advancedelectronics":    "Advanced Electronics",
    "advancedcomposites":     "Advanced Composites",
    "scanningarrays":         "Scanning Arrays",
    "engineparts":            "Engine Parts",
    "hullparts":              "Hull Parts",
    "smartchips":             "Smart Chips",
    "dronecomponents":        "Drone Components",
    "fieldcoils":             "Field Coils",
    "majadust":               "Maja Dust",
    "teladianium":            "Teladianium",
    "protectivecoating":      "Protective Coating",
    "computronicsubstrate":   "Computronic Substrate",
    "metallic microlattice":  "Metallic Microlattice",
    "metallicmicrolattice":   "Metallic Microlattice",
    "siliconcarbidemicrolattice": "Silicon Carbide Microlattice",
    "carboncarbide":          "Carbon Carbide",
    # Food / consumables
    "foodrations":            "Food Rations",
    "medicalsupplies":        "Medical Supplies",
    "spaceweed":              "Space Weed",
    "spacefuel":              "Space Fuel",
    "maja snails":            "Maja Snails",
    "majasnails":             "Maja Snails",
    "stimulants":             "Stimulants",
    "hallucinogenics":        "Hallucinogenics",
    # Ship / station components
    "weaponcomponents":       "Weapon Components",
    "missilecomponents":      "Missile Components",
    "shieldcomponents":       "Shield Components",
    "turretcomponents":       "Turret Components",
    "claytronics":            "Claytronics",
    "antimatterconverters":   "Antimatter Converters",
    "redundantcoolingsystems":"Redundant Cooling Systems",
    "podcontrolsystems":      "Pod Control Systems",
}


def format_wares(overviewgraphs: str) -> str:
    """
    Converts a raw overviewgraphs string like "advancedelectronics energycells microchips"
    into a readable list like "Advanced Electronics, Energy Cells, Microchips".
    Falls back to Title Case for any ware not in our lookup table.
    """
    if not overviewgraphs:
        return ""
    wares = overviewgraphs.strip().split()
    display = [WARE_NAMES.get(w.lower(), w.replace('_', ' ').title()) for w in wares]
    return ", ".join(display)