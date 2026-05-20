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


# ─────────────────────────────────────────────────────────────────────────────
#  WARE VOLUMES  (m³ per unit)
#  Sourced directly from libraries/wares.xml (<ware volume="..."> attribute).
#  Used to convert ware amounts from station <cargo> blocks into m³ for fill %.
#  Wares not listed here default to 1 m³/unit in station_scanner.py.
# ─────────────────────────────────────────────────────────────────────────────

WARE_VOLUME: dict[str, float] = {
    # Solid (raw resources)
    "ice":                      8.0,
    "nividium":                10.0,
    "ore":                     10.0,
    "rawscrap":                10.0,
    "scrapmetal":              10.0,
    "silicon":                 10.0,
    # Liquid (gases)
    "helium":                   6.0,
    "hydrogen":                 6.0,
    "methane":                  6.0,
    # Container — refined materials
    "energycells":              1.0,
    "antimattercells":         18.0,
    "graphene":                20.0,
    "refinedmetals":           14.0,
    "siliconwafers":           18.0,
    "superfluidcoolant":       16.0,
    "water":                    6.0,
    # Container — manufactured components
    "advancedcomposites":      32.0,
    "advancedelectronics":     30.0,
    "antimatterconverters":    10.0,
    "claytronics":             24.0,
    "dronecomponents":         30.0,
    "engineparts":             15.0,
    "fieldcoils":              15.0,
    "hullparts":               12.0,
    "microchips":              22.0,
    "missilecomponents":        2.0,
    "nividiumgems":             2.0,
    "plasmaconductors":        32.0,
    "quantumtubes":            22.0,
    "scanningarrays":          38.0,
    "shieldcomponents":        10.0,
    "smartchips":               2.0,
    "teladianium":             16.0,
    "turretcomponents":        20.0,
    "weaponcomponents":        20.0,
    # Container — food and faction goods
    "foodrations":              1.0,
    "majadust":                 6.0,
    "majasnails":               6.0,
    "meat":                     6.0,
    "medicalsupplies":          2.0,
    "nostropoil":               1.0,
    "sojabeans":                5.0,
    "sojahusk":                 1.0,
    "spacefuel":                2.0,
    "spaceweed":                3.0,
    "spices":                   3.0,
    "sunriseflowers":           5.0,
    "swampplant":               6.0,
    "wheat":                    4.0,
}


# ─────────────────────────────────────────────────────────────────────────────
#  WARE TRANSPORT TYPE  (container / solid / liquid)
#  Sourced from libraries/wares.xml <ware transport="..."> attribute.
#  Used in station_scanner.py to attribute trade reservation amounts to the
#  correct storage type when computing reservation-adjusted fill percentages.
# ─────────────────────────────────────────────────────────────────────────────

WARE_TRANSPORT: dict[str, str] = {
    # Solid — raw materials loaded into solid storage bays
    "ice":                         "solid",
    "nividium":                    "solid",
    "ore":                         "solid",
    "rawscrap":                    "solid",
    "scrapmetal":                  "solid",
    "silicon":                     "solid",
    # Liquid — gases stored in pressurised tanks
    "helium":                      "liquid",
    "hydrogen":                    "liquid",
    "methane":                     "liquid",
    "water":                       "liquid",
    # Container — refined materials
    "energycells":                 "container",
    "antimattercells":             "container",
    "graphene":                    "container",
    "refinedmetals":               "container",
    "siliconwafers":               "container",
    "superfluidcoolant":           "container",
    # Container — manufactured components
    "advancedcomposites":          "container",
    "advancedelectronics":         "container",
    "antimatterconverters":        "container",
    "claytronics":                 "container",
    "computronicsubstrate":        "container",
    "dronecomponents":             "container",
    "engineparts":                 "container",
    "fieldcoils":                  "container",
    "hullparts":                   "container",
    "metallicmicrolattice":        "container",
    "microchips":                  "container",
    "missilecomponents":           "container",
    "nividiumgems":                "container",
    "plasmaconductors":            "container",
    "podcontrolsystems":           "container",
    "protectivecoating":           "container",
    "quantumtubes":                "container",
    "redundantcoolingsystems":     "container",
    "scanningarrays":              "container",
    "shieldcomponents":            "container",
    "siliconcarbidemicrolattice":  "container",
    "smartchips":                  "container",
    "teladianium":                 "container",
    "turretcomponents":            "container",
    "weaponcomponents":            "container",
    # Container — food, consumables, faction goods
    "foodrations":                 "container",
    "hallucinogenics":             "container",
    "majadust":                    "container",
    "majasnails":                  "container",
    "meat":                        "container",
    "medicalsupplies":             "container",
    "nostropoil":                  "container",
    "sojabeans":                   "container",
    "sojahusk":                    "container",
    "spacefuel":                   "container",
    "spaceweed":                   "container",
    "spices":                      "container",
    "stimulants":                  "container",
    "sunriseflowers":              "container",
    "swampplant":                  "container",
    "wheat":                       "container",
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