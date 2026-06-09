# ─────────────────────────────────────────────────────────────────────────────
#  PRODUCTION CALCULATIONS
#  Functions for computing effective production rates from static data.
#  Add further production helpers here as the economy tab grows.
# ─────────────────────────────────────────────────────────────────────────────

import re

from data.production_stats import PRODUCTION_STATS
from data.sector_stats import SECTOR_SUNLIGHT
from data.wares import WARE_NAMES

# Matches production module macros: prod_{faction}_{ware}_macro
# e.g. prod_gen_refinedmetals_macro, prod_tel_hullparts_macro
_PROD_MACRO_RE = re.compile(r'^prod_(\w+?)_(\w+)_macro$', re.IGNORECASE)

# Maps the faction token in a module macro to its recipe method in PRODUCTION_STATS.
# Faction modules can use different input recipes (e.g. Teladi uses teladianium
# instead of refined metals). Falls back to 'default' for unknown tokens.
_FACTION_METHOD: dict[str, str] = {
    "gen": "default",
    "arg": "argon",
    "tel": "teladi",
    "par": "paranid",
    "spl": "split",
    "ter": "terran",
    "bor": "boron",
}

# Inverted lookup: display name → ware_id  (e.g. "Energy Cells" → "energycells")
_DISPLAY_TO_ID: dict[str, str] = {v: k for k, v in WARE_NAMES.items()}


def display_name_to_id(display_name: str) -> str | None:
    """Converts a ware display name (e.g. 'Energy Cells') to its production stats key."""
    return _DISPLAY_TO_ID.get(display_name)


def units_per_cycle(ware_id: str, sector: str) -> float:
    """Returns effective units produced per cycle for one module.

    Energy cells apply the sector sunlight multiplier; all other wares are
    unaffected by location. Returns 0 for unknown ware IDs.
    Defaults to sunlight 1.0 for unrecognised sectors.
    """
    stats = PRODUCTION_STATS.get(ware_id)
    if stats is None:
        return 0.0
    amount = stats["amount"]
    if ware_id == "energycells":
        # Game floors the per-cycle output to an integer before computing hourly rates.
        amount = int(amount * SECTOR_SUNLIGHT.get(sector, 1.0))
    return float(amount)


def units_per_hour(ware_id: str, sector: str) -> float:
    """Returns effective units produced per hour for one module."""
    stats = PRODUCTION_STATS.get(ware_id)
    if stats is None:
        return 0.0
    return units_per_cycle(ware_id, sector) * (3600 / stats["time"])


def runtime_minutes(ware_id: str, module_count: int, inventory: dict[str, int]) -> float | None:
    """Returns how many minutes production can continue given current inventory.

    Finds the limiting input — the one that runs out first — and converts the
    remaining cycles to minutes using the ware's cycle time.

    Returns None for wares with no inputs (e.g. energy cells, which run on sunlight).
    Returns 0.0 if any required input has zero stock.
    Inventory keys must be display names (e.g. 'Energy Cells'), matching what
    _parse_station_storage stores.
    """
    stats = PRODUCTION_STATS.get(ware_id)
    if stats is None:
        return None

    inputs = stats["methods"].get("default", {})
    if not inputs:
        return None  # no raw inputs needed

    min_cycles = float("inf")
    for input_id, qty_per_module in inputs.items():
        total_per_cycle = qty_per_module * module_count
        stock           = inventory.get(WARE_NAMES.get(input_id, input_id), 0)
        min_cycles      = min(min_cycles, stock / total_per_cycle)

    return min_cycles * stats["time"] / 60.0


def inputs_per_cycle(ware_id: str, count: int = 1) -> dict[str, int]:
    """Returns {input_display_name: total_qty} consumed per cycle across `count` modules.

    Uses the default production method. Energy cells and mineables return {}.
    """
    stats = PRODUCTION_STATS.get(ware_id)
    if stats is None:
        return {}
    raw = stats["methods"].get("default", {})
    return {WARE_NAMES.get(iid, iid): qty * count for iid, qty in raw.items()}


def consumption_rates_from_modules(modules: list[dict]) -> dict[str, float]:
    """Returns {ware_display_name: units_per_hour_consumed_internally} for a station.

    Walks every production module (identified by its macro) and sums up how many
    units of each INPUT ware all the modules collectively consume per hour. Result
    is keyed by display name so the UI can look up by the same name used in
    production_rates.

    `modules` is the list of dicts with at least a 'macro' key, as stored in
    station_modules / the export's d['modules'].

    Example: a station with 3 hull-parts modules and 2 energy-cell modules would
    return {'Energy Cells': X, 'Graphene': Y, 'Refined Metals': Z} — the combined
    internal demand from both module types.
    """
    consumed: dict[str, float] = {}  # ware_id → units/hr

    for m in modules:
        match = _PROD_MACRO_RE.match(m.get('macro', ''))
        if not match:
            continue
        faction, ware = match.group(1).lower(), match.group(2).lower()
        stats = PRODUCTION_STATS.get(ware)
        if not stats or not stats['time']:
            continue

        # Pick the faction-specific recipe if one exists, fall back to default.
        method = _FACTION_METHOD.get(faction, 'default')
        inputs = stats['methods'].get(method) or stats['methods'].get('default', {})
        cycles_per_hr = 3600.0 / stats['time']

        for in_ware, in_amt in inputs.items():
            consumed[in_ware] = consumed.get(in_ware, 0.0) + in_amt * cycles_per_hr

    # Convert ware IDs to display names for the UI. Unknown IDs are dropped
    # (they'd have no WARE_COLOURS entry and the UI can't use them anyway).
    return {WARE_NAMES[w]: v for w, v in consumed.items() if w in WARE_NAMES}
