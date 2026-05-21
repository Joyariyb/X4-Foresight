# ─────────────────────────────────────────────────────────────────────────────
#  PRODUCTION CALCULATIONS
#  Functions for computing effective production rates from static data.
#  Add further production helpers here as the economy tab grows.
# ─────────────────────────────────────────────────────────────────────────────

from data.production_stats import PRODUCTION_STATS
from data.sector_stats import SECTOR_SUNLIGHT
from data.wares import WARE_NAMES

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
