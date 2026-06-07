# Axial hex grid coordinates (q, r) for each cluster macro.
#
# Derived from the qsna.eu /api/x4/map endpoint (cross-referenced 2026-06-07).
# Positions were originally extracted from galaxy.xml, but the vanilla XML
# contained scale errors that made most vanilla clusters wrong.  The API data
# (in km units, hexSize = 10 000 km) gives the authoritative positions:
#
#   q = round(x_km / 15 000)
#   r = round(z_km / 17 320.508 - q / 2)
#
# Flat-top hex geometry, y-axis negated so the map matches the in-game galaxy
# orientation (+z up in game space, +y down in SVG).
#
# Grid bounds: q = -17 … 13,  r = -9 … 15  (31 cols × 25 rows)
# Total: 127 clusters across all DLCs including Timelines.

CLUSTER_POSITIONS: dict[str, tuple[int, int]] = {
    # ── Vanilla / base game (cluster_01–50) ────────────────────────────────────
    "cluster_01_macro": (   0,   0),   # Grand Exchange
    "cluster_02_macro": (   1,   1),   # Eighteen Billion
    "cluster_03_macro": (   2,   0),   # Memory of Profit
    "cluster_04_macro": (   3,  -3),   # Nopileos' Fortune
    "cluster_05_macro": (   0,  -1),   # Path to Profit
    "cluster_06_macro": (  -2,   1),   # Black Hole Sun
    "cluster_07_macro": (  -7,   6),   # The Reach
    "cluster_08_macro": (  -1,   6),   # Silent Witness
    "cluster_09_macro": (   4,   2),   # Bright Promise
    "cluster_10_macro": (   5,  -3),   # Unholy Retribution
    "cluster_11_macro": (  -2,  -3),   # Pontifex's Claim
    "cluster_12_macro": (  -4,  -1),   # True Sight
    "cluster_13_macro": (  -5,   2),   # Second Contact
    "cluster_14_macro": (  -6,   5),   # Argon Prime
    "cluster_15_macro": (   6,   1),   # Ianamus Zura
    "cluster_16_macro": (   6,   2),   # Matrix #451
    "cluster_17_macro": (   5,   3),   # Matrix #9
    "cluster_18_macro": (   5,  -1),   # Trinity Sanctum
    "cluster_19_macro": (   7,  -4),   # Hewa's Twin
    "cluster_20_macro": (   9,  -6),   # Company Regard
    "cluster_21_macro": (   9,  -7),   # Scale Plate Green
    "cluster_22_macro": (   2,  -4),   # Pious Mists
    "cluster_23_macro": (   4,  -7),   # Sacred Relic
    "cluster_24_macro": (  -3,  -2),   # Holy Vision
    "cluster_25_macro": (  -6,  -1),   # Faulty Logic
    "cluster_26_macro": (  -8,   1),   # Atiya's Misfortune
    "cluster_27_macro": ( -10,   7),   # The Void
    "cluster_28_macro": ( -11,   7),   # Antigone Memorial
    "cluster_29_macro": (  -4,   6),   # Hatikvah's Choice
    "cluster_30_macro": (  -6,   7),   # Morning Star
    "cluster_31_macro": (  -8,  10),   # Heretic's End
    "cluster_32_macro": (  -4,   8),   # Tharka's Cascade
    "cluster_33_macro": (  -5,   9),   # Matrix #79B
    "cluster_34_macro": (   3,   3),   # Profit Center Alpha
    "cluster_35_macro": (  -3,  -4),   # Lasting Vengeance
    "cluster_36_macro": (  -4,  -3),   # Cardinal's Redress
    "cluster_37_macro": (   3,  -5),   # Pious Mists
    "cluster_38_macro": (   2,  -5),   # Pious Mists
    "cluster_39_macro": (   2,  -1),   # Memory of Profit
    "cluster_40_macro": (  -6,   2),   # Second Contact
    "cluster_41_macro": (  -6,   3),   # Second Contact
    "cluster_42_macro": (   8,  -4),   # Hewa's Twin
    "cluster_43_macro": (   8,  -3),   # Hewa's Twin
    "cluster_44_macro": (   0,   6),   # Silent Witness
    "cluster_45_macro": (  -1,   7),   # Silent Witness
    "cluster_46_macro": (  -6,   8),   # Morning Star
    "cluster_47_macro": (   4,   0),   # Trinity Sanctum
    "cluster_48_macro": ( -10,   8),   # Getsu Fune
    "cluster_49_macro": (  -8,   3),   # Frontier Edge
    "cluster_50_macro": (  10,  -7),   # Turquoise Sea

    # ── Later base-game additions (cluster_709–725, 730, 740) ──────────────────
    # Added in game version updates post-launch; dlc=base in the API.
    "cluster_709_macro": (   4,  -8),   # Cardinal's Domain
    "cluster_710_macro": (   7,  -9),   # Moo-Kye's Revenge
    "cluster_711_macro": (   8,  -8),   # Mi Ton's Refuge
    "cluster_712_macro": (   7,  -7),   # Loomanckstrat's Legacy
    "cluster_713_macro": (   6,  -5),   # CEO's Doubt
    "cluster_714_macro": (  -4,  -4),   # Freedom's Reach
    "cluster_715_macro": (  -8,   0),   # Mists of Artemis
    "cluster_720_macro": ( -10,   4),   # Ore Belt
    "cluster_721_macro": ( -14,  11),   # Adventure's Promise
    "cluster_722_macro": (  -9,  -1),   # Sanctum Verge
    "cluster_723_macro": (  -2,  -6),   # Tempting Fumes
    "cluster_724_macro": ( -14,   1),   # Circle of Deceit
    "cluster_725_macro": (  -2,   0),   # Void of Opportunity
    "cluster_730_macro": ( -10,   5),   # Third Redemption (mini DLC 01)
    "cluster_740_macro": (  -3,   1),   # Scarlet Star (mini DLC 02)

    # ── Cradle of Humanity (ego_dlc_terran) ────────────────────────────────────
    "cluster_100_macro": ( -13,   7),   # Sol
    "cluster_101_macro": ( -14,   8),   # Sol
    "cluster_102_macro": ( -15,   9),   # Sol
    "cluster_104_macro": ( -14,   9),   # Sol
    "cluster_106_macro": ( -15,  10),   # Sol
    "cluster_107_macro": ( -14,   6),   # Sol
    "cluster_108_macro": ( -15,   6),   # Sol
    "cluster_109_macro": ( -16,   6),   # Sol
    "cluster_110_macro": ( -15,   5),   # Sol
    "cluster_111_macro": ( -16,   5),   # Sol
    "cluster_112_macro": (  -8,   8),   # Savage Spur
    "cluster_113_macro": ( -11,   1),   # Segaris
    "cluster_114_macro": ( -12,   1),   # Gaian Prophecy
    "cluster_115_macro": ( -13,   2),   # Brennan's Triumph
    "cluster_116_macro": ( -17,   5),   # Sol

    # ── Split Vendetta (ego_dlc_split) ─────────────────────────────────────────
    "cluster_400_macro": (  -7,  12),   # Wretched Skies
    "cluster_401_macro": (  -3,   9),   # Family Zhin
    "cluster_402_macro": (  -3,  10),   # Family Kritt
    "cluster_403_macro": (  -8,  12),   # Wretched Skies
    "cluster_404_macro": (   2,   8),   # Zyarth's Dominion
    "cluster_405_macro": (   3,   7),   # Zyarth's Dominion
    "cluster_406_macro": (   3,   8),   # Zyarth's Dominion
    "cluster_407_macro": (   8,   2),   # Family Tkr
    "cluster_408_macro": (   8,   1),   # Thuruk's Demise
    "cluster_409_macro": (  10,   1),   # Tharka's Ravine
    "cluster_410_macro": (  11,   1),   # Tharka's Ravine
    "cluster_411_macro": (  12,   2),   # Heart of Acrimony
    "cluster_412_macro": (  12,   0),   # Tharka's Ravine
    "cluster_413_macro": (  13,   0),   # Tharka's Ravine
    "cluster_414_macro": (  -3,  11),   # Rhy's Defiance
    "cluster_415_macro": (  -2,  11),   # Matrix #598
    "cluster_416_macro": (   6,   5),   # Guiding Star
    "cluster_417_macro": (   5,   7),   # Eleventh Hour
    "cluster_418_macro": (   0,   8),   # Family Nhuut
    "cluster_419_macro": (   2,   6),   # Open Market
    "cluster_420_macro": (   3,   5),   # Two Grand
    "cluster_421_macro": (   8,   3),   # Fires of Defeat
    "cluster_422_macro": (  -9,  13),   # Wretched Skies
    "cluster_423_macro": ( -11,  14),   # Litany of Fury
    "cluster_424_macro": ( -12,  15),   # Emperor's Pride
    "cluster_425_macro": (  11,   3),   # Heart of Acrimony

    # ── Tides of Avarice (ego_dlc_pirate) ─────────────────────────────────────
    # Note: cluster_502 and cluster_503 were previously excluded due to apparent
    # position collisions — those collisions were caused by incorrect vanilla
    # coordinates.  With corrected positions, there are no collisions.
    "cluster_500_macro": (  -1,   2),   # Avarice
    "cluster_501_macro": (  -2,   4),   # Windfall
    "cluster_502_macro": (  -3,   4),   # Windfall
    "cluster_503_macro": (  -3,   3),   # Windfall
    "cluster_504_macro": (  12,  -2),   # Unknown System

    # ── Timelines (ego_dlc_timelines) ─────────────────────────────────────────
    "cluster_701_macro": (  10,  -4),   # Mitsuno's Remembrance
    "cluster_702_macro": (  11,  -5),   # Mitsuno's Remembrance
    "cluster_703_macro": (  11,  -6),   # Mitsuno's Remembrance
    "cluster_704_macro": (   1,   3),   # President's End
    "cluster_705_macro": (  -8,   6),   # Nopileos' Memorial
    "cluster_706_macro": (  -7,   5),   # Hatikvah's Faith
    "cluster_708_macro": (  -3,   7),   # Matrix #101

    # ── Kingdom End (ego_dlc_boron) ────────────────────────────────────────────
    "cluster_601_macro": ( -10,  11),   # Watchful Gaze
    "cluster_602_macro": ( -11,  11),   # Barren Shores
    "cluster_603_macro": ( -12,  11),   # Great Reef
    "cluster_604_macro": ( -12,  10),   # Ocean of Fantasy
    "cluster_605_macro": ( -13,  13),   # Sanctuary of Darkness
    "cluster_606_macro": ( -15,  15),   # Kingdom End
    "cluster_607_macro": ( -16,  15),   # Rolk's Demise
    "cluster_608_macro": ( -15,  14),   # Atreus' Clouds
    "cluster_609_macro": ( -16,  14),   # Menelaus' Oasis
}

# Display names sourced from qsna.eu/api/x4/map (2026-06-07).
# For single-sector clusters the sector name (with roman numeral) is used to
# distinguish hexes that share a system name (e.g. "Pious Mists II/IV/XI").
# Multi-sector cluster hexes use the system name directly.
CLUSTER_NAMES: dict[str, str] = {
    # Vanilla / base game
    "cluster_01_macro": "Grand Exchange",
    "cluster_02_macro": "Eighteen Billion",
    "cluster_03_macro": "Memory of Profit IX",
    "cluster_04_macro": "Nopileos' Fortune",
    "cluster_05_macro": "Path to Profit",
    "cluster_06_macro": "Black Hole Sun",
    "cluster_07_macro": "The Reach",
    "cluster_08_macro": "Silent Witness I",
    "cluster_09_macro": "Bright Promise",
    "cluster_10_macro": "Unholy Retribution",
    "cluster_11_macro": "Pontifex's Claim",
    "cluster_12_macro": "True Sight",
    "cluster_13_macro": "Second Contact II Flashpoint",
    "cluster_14_macro": "Argon Prime",
    "cluster_15_macro": "Ianamus Zura",
    "cluster_16_macro": "Matrix #451",
    "cluster_17_macro": "Matrix #9",
    "cluster_18_macro": "Trinity Sanctum III",
    "cluster_19_macro": "Hewa's Twin",
    "cluster_20_macro": "Company Regard",
    "cluster_21_macro": "Scale Plate Green",
    "cluster_22_macro": "Pious Mists II",
    "cluster_23_macro": "Sacred Relic",
    "cluster_24_macro": "Holy Vision",
    "cluster_25_macro": "Faulty Logic",
    "cluster_26_macro": "Atiya's Misfortune",
    "cluster_27_macro": "The Void",
    "cluster_28_macro": "Antigone Memorial",
    "cluster_29_macro": "Hatikvah's Choice",
    "cluster_30_macro": "Morning Star III",
    "cluster_31_macro": "Heretic's End",
    "cluster_32_macro": "Tharka's Cascade",
    "cluster_33_macro": "Matrix #79B",
    "cluster_34_macro": "Profit Center Alpha",
    "cluster_35_macro": "Lasting Vengeance",
    "cluster_36_macro": "Cardinal's Redress",
    "cluster_37_macro": "Pious Mists IV",
    "cluster_38_macro": "Pious Mists XI",
    "cluster_39_macro": "Memory of Profit X",
    "cluster_40_macro": "Second Contact VII",
    "cluster_41_macro": "Second Contact XI",
    "cluster_42_macro": "Hewa's Twin",
    "cluster_43_macro": "Hewa's Twin V",
    "cluster_44_macro": "Silent Witness XI",
    "cluster_45_macro": "Silent Witness XII",
    "cluster_46_macro": "Morning Star IV",
    "cluster_47_macro": "Trinity Sanctum VII",
    "cluster_48_macro": "Getsu Fune",
    "cluster_49_macro": "Frontier Edge",
    "cluster_50_macro": "Turquoise Sea",
    # Later base-game additions
    "cluster_709_macro": "Cardinal's Domain",
    "cluster_710_macro": "Moo-Kye's Revenge",
    "cluster_711_macro": "Mi Ton's Refuge",
    "cluster_712_macro": "Loomanckstrat's Legacy",
    "cluster_713_macro": "CEO's Doubt",
    "cluster_714_macro": "Freedom's Reach",
    "cluster_715_macro": "Mists of Artemis",
    "cluster_720_macro": "Ore Belt",
    "cluster_721_macro": "Adventure's Promise",
    "cluster_722_macro": "Sanctum Verge",
    "cluster_723_macro": "Tempting Fumes",
    "cluster_724_macro": "Circle of Deceit",
    "cluster_725_macro": "Void of Opportunity",
    "cluster_730_macro": "Third Redemption",
    "cluster_740_macro": "Scarlet Star",
    # Cradle of Humanity — Sol sub-regions named after planets/bodies
    "cluster_100_macro": "Asteroid Belt",
    "cluster_101_macro": "Mars",
    "cluster_102_macro": "Venus",
    "cluster_104_macro": "Sol (Earth)",    # Earth + The Moon; API gives "Sol" for both 104/108
    "cluster_106_macro": "Mercury",
    "cluster_107_macro": "Jupiter",
    "cluster_108_macro": "Sol (Saturn)",   # Saturn + Titan; distinguished by sector content
    "cluster_109_macro": "Uranus",
    "cluster_110_macro": "Neptune",
    "cluster_111_macro": "Pluto",
    "cluster_112_macro": "Savage Spur",
    "cluster_113_macro": "Segaris",
    "cluster_114_macro": "Gaian Prophecy",
    "cluster_115_macro": "Brennan's Triumph",
    "cluster_116_macro": "Oort Cloud",
    # Split Vendetta
    "cluster_400_macro": "Wretched Skies IV Family Valka",
    "cluster_401_macro": "Family Zhin",
    "cluster_402_macro": "Family Kritt",
    "cluster_403_macro": "Wretched Skies V Family Phi",
    "cluster_404_macro": "Zyarth's Dominion I",
    "cluster_405_macro": "Zyarth's Dominion IV",
    "cluster_406_macro": "Zyarth's Dominion X",
    "cluster_407_macro": "Family Tkr",
    "cluster_408_macro": "Thuruk's Demise",
    "cluster_409_macro": "Tharka's Ravine XXIV",
    "cluster_410_macro": "Tharka's Ravine XVI",
    "cluster_411_macro": "Heart of Acrimony II",
    "cluster_412_macro": "Tharka's Ravine VIII",
    "cluster_413_macro": "Tharka's Ravine IV Tharka's Fall",
    "cluster_414_macro": "Rhy's Defiance",
    "cluster_415_macro": "Matrix #598",
    "cluster_416_macro": "Guiding Star",
    "cluster_417_macro": "Eleventh Hour",
    "cluster_418_macro": "Family Nhuut",
    "cluster_419_macro": "Open Market",
    "cluster_420_macro": "Two Grand",
    "cluster_421_macro": "Fires of Defeat",
    "cluster_422_macro": "Wretched Skies X",
    "cluster_423_macro": "Litany of Fury",
    "cluster_424_macro": "Emperor's Pride",
    "cluster_425_macro": "Heart of Acrimony I The Boneyard",
    # Tides of Avarice
    "cluster_500_macro": "Avarice",
    "cluster_501_macro": "Windfall I Union Summit",
    "cluster_502_macro": "Windfall III The Hoard",
    "cluster_503_macro": "Windfall IV Aurora's Dream",
    "cluster_504_macro": "Unknown System",
    # Kingdom End
    "cluster_601_macro": "Watchful Gaze",
    "cluster_602_macro": "Barren Shores",
    "cluster_603_macro": "Great Reef",
    "cluster_604_macro": "Ocean of Fantasy",
    "cluster_605_macro": "Sanctuary of Darkness",
    "cluster_606_macro": "Kingdom End",
    "cluster_607_macro": "Rolk's Demise",
    "cluster_608_macro": "Atreus' Clouds",
    "cluster_609_macro": "Menelaus' Oasis",
    # Timelines — each hex has its own distinct name
    "cluster_701_macro": "Mitsuno's Revelation",
    "cluster_702_macro": "Mitsuno's Defiance",
    "cluster_703_macro": "Mitsuno's Sacrifice",
    "cluster_704_macro": "President's End",
    "cluster_705_macro": "Nopileos' Memorial",
    "cluster_706_macro": "Hatikvah's Faith",
    "cluster_708_macro": "Matrix #101",
}
