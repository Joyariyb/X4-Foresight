  const HOSTILE_ORIGINS = new Set(["Xenon", "Yaki", "Kha'ak"]);
  const MILITARY_ROLES  = new Set(["Fighter","Heavy Fighter","Corvette","Destroyer","Frigate","Gunboat"]);
  const MINER_ROLES     = new Set(["Miner (Solid)","Miner (Liquid)"]);

  const ORDER_COLOURS = { Trading:"var(--green)", Mining:"var(--amber)", Escorting:"var(--teal)", Waiting:"var(--text-faint)" };
  const SIZE_COLOURS  = { XL:"var(--purple)", L:"var(--amber)", M:"var(--teal)", S:"var(--text-dim)" };

  // Bright accent colour for each production ware, keyed by display name.
  // Unrecognised wares fall back to --text-dim in the renderer.
  const WARE_COLOURS = {
    // Raw resources
    "Ore":                          "#cd7f32",
    "Silicon":                      "#b0bec5",
    "Ice":                          "#b3e5fc",
    "Hydrogen":                     "#fff176",
    "Helium":                       "#ce93d8",
    "Methane":                      "#a5d6a7",
    "Nividium":                     "#ab47bc",
    // Refined / basic materials
    "Refined Metals":               "#90a4ae",
    "Silicon Wafers":               "#00bcd4",
    "Energy Cells":                 "#fdd835",
    "Graphene":                     "#26a69a",
    "Superfluid Coolant":           "#4fc3f7",
    "Antimatter Cells":             "#ef5350",
    "Plasma Conductors":            "#7e57c2",
    "Quantum Tubes":                "#e91e63",
    "Microchips":                   "#43a047",
    "Advanced Electronics":         "#2196f3",
    "Advanced Composites":          "#8bc34a",
    "Scanning Arrays":              "#00e5ff",
    "Engine Parts":                 "#ff9800",
    "Hull Parts":                   "#78909c",
    "Smart Chips":                  "#29b6f6",
    "Drone Components":             "#ff5722",
    "Field Coils":                  "#5c6bc0",
    "Maja Dust":                    "#f06292",
    "Teladianium":                  "#ffc107",
    "Protective Coating":           "#66bb6a",
    "Computronic Substrate":        "#26c6da",
    "Metallic Microlattice":        "#90caf9",
    "Silicon Carbide Microlattice": "#ffb300",
    "Carbon Carbide":               "#bdbdbd",
    // Ship / station components
    "Weapon Components":            "#f44336",
    "Missile Components":           "#d32f2f",
    "Shield Components":            "#3f51b5",
    "Turret Components":            "#ff7043",
    "Claytronics":                  "#00acc1",
    "Antimatter Converters":        "#ec407a",
    "Redundant Cooling Systems":    "#80cbc4",
    "Pod Control Systems":          "#4db6ac",
    // Food / consumables
    "Food Rations":                 "#aed581",
    "Medical Supplies":             "#ef9a9a",
    "Space Weed":                   "#69f0ae",
    "Space Fuel":                   "#ff8a65",
    "Maja Snails":                  "#f48fb1",
    "Stimulants":                   "#e6ee9c",
    "Hallucinogenics":              "#b39ddb",
  };

