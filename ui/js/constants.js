  // Core role: Shared UI constants (role/faction/ware sets, color mappings, faction metadata).

  const HOSTILE_ORIGINS = new Set(["Xenon", "Yaki", "Kha'ak"]);

  // Factions whose standing with the player is hard-locked (permanently hostile at
  // −30, can never be raised) — confirmed only Xenon and Kha'ak (egosoft wiki). They
  // carry locked="1" in the save and are excluded from the Reputation History chart:
  // a flat line that can't move is noise, and it would stretch the auto-zoomed Y axis.
  const LOCKED_REP_FACTIONS = new Set(["xenon", "khaak"]);
  const MILITARY_ROLES  = new Set(["Fighter","Heavy Fighter","Corvette","Destroyer","Frigate","Gunboat"]);
  const MINER_ROLES     = new Set(["Miner (Solid)","Miner (Liquid)"]);

  // Semantic tier only — these feed inline style="color:…" (faction-tabs.js,
  // fleet.js, populate.js), which is the JS equivalent of body.html, so §1's
  // "never reference the palette tier outside base.css" applies here too.
  const ORDER_COLOURS = { Trading:"var(--color-positive)", Delivering:"var(--color-positive)", Mining:"var(--color-warning)", Escorting:"var(--color-primary)", Waiting:"var(--text-brand)" };
  const SIZE_COLOURS  = { XL:"var(--color-special)", L:"var(--color-warning)", M:"var(--color-primary)", S:"var(--text-secondary)" };

  // Tabler-icon class per ship role / order / summary card — shared by
  // populate.js, fleet.js and faction-tabs.js (same consumers as the colour
  // maps above, so they live together here).
  const ROLE_ICONS = {
    "Fighter":              "ti-rocket",
    "Heavy Fighter":        "ti-rocket",
    "Corvette":             "ti-rocket",
    "Destroyer":            "ti-anchor",
    "Frigate":              "ti-shield",
    "Gunboat":              "ti-crosshair",
    "Scout":                "ti-eye",
    "Carrier":              "ti-drone",
    "Freighter":            "ti-package",
    "Transport":            "ti-package",
    "Gas Tanker":           "ti-ripple",
    "Miner (Solid)":        "ti-shovel",
    "Miner (Liquid)":       "ti-droplet",
    "Combat Supply":        "ti-box",
    "Supply":               "ti-box",
    "Boarding":             "ti-sword",
  };

  const ORDER_ICONS = {
    "Trading":   "ti-arrows-exchange",
    "Delivering": "ti-package-export",
    "Mining":    "ti-shovel",
    "Escorting": "ti-shield",
    "Waiting":   "ti-clock",
    "Idle":      "ti-clock",
    "Patrol":    "ti-route",
    "Attack":    "ti-crosshair",
    "Building":  "ti-hammer",
    "Repair":    "ti-tool",
    "Supply":    "ti-box",
    "Docking":   "ti-ship",
    "Travel":    "ti-route",
  };

  const CARD_ICONS = {
    "Credits":       "ti-coin",
    "Total Ships":   "ti-rocket",
    "Stations":      "ti-building-factory-2",
    "Hostile Hulls": "ti-alert-triangle",
    "Waiting":       "ti-clock",
  };

  // ── Chart series palette ──────────────────────────────────────────────────
  // These are hex literals rather than var(--color-primary): the cash-flow and economy
  // charts render as inline SVG, and CSS custom properties don't resolve inside
  // SVG presentation attributes (fill="…", stroke="…"). Centralised here so the
  // teal family stays in one place instead of drifting into the near-identical
  // copies it had grown into (#5fe9d4 vs #5eead4 etc.).
  //
  // The data line is intentionally drawn twice — a dim, wide CHART_GLOW stroke
  // under a thin, bright CHART_LINE stroke — and that layering IS the glow
  // effect, so CHART_GLOW and CHART_LINE must stay different colours.
  const CHART_ACCENT   = '#19e6c8'; // primary accent: bars, grid, gradient stops, positive figures
  const CHART_GLOW     = '#2dd4bf'; // dim wide under-stroke behind the data line (matches --teal)
  const CHART_LINE     = '#5eead4'; // bright data line (hourly), axis labels, ware fallback
  const CHART_LINE_ALT = '#7af5e4'; // bright data line (cumulative-by-trade mode)
  const CHART_LOSS     = '#ef5350'; // negative / loss values (incl. own-ship losses)
  const CHART_KILL     = '#fb923c'; // offensive combat tally (enemy kills) — warm, distinct from CHART_LOSS

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

