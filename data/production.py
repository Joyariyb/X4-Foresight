# Core role: Production rate calculations (cycles, throughput, duration) from module and ware data.

import re

from data.production_stats import PRODUCTION_STATS
from data.sector_stats import SECTOR_SUNLIGHT
from data.wares import WARE_NAMES, WARE_TRANSPORT, WARE_VOLUME

# Matches production module macros: prod_{faction}_{ware}_macro
# e.g. prod_gen_refinedmetals_macro, prod_tel_hullparts_macro
# Public (no underscore) so scanner and export layers can share this definition
# rather than each re-defining it locally.
PROD_MACRO_RE = re.compile(r'^prod_(\w+?)_(\w+)_macro$', re.IGNORECASE)

# Maps the faction token in a module macro to its recipe method in PRODUCTION_STATS.
# Faction modules can use different input recipes (e.g. Teladi uses teladianium
# instead of refined metals). Falls back to 'default' for unknown tokens.
FACTION_METHOD: dict[str, str] = {
    "gen": "default",
    "arg": "argon",
    "tel": "teladi",
    "par": "paranid",
    "spl": "split",
    "ter": "terran",
    "bor": "boron",
}


def _get_macro(m) -> str:
    """Return the macro string from either a StationModule object or a dict row."""
    return m.macro if hasattr(m, 'macro') else m.get('macro', '')

# Inverted lookup: display name → ware_id  (e.g. "Energy Cells" → "energycells")
_DISPLAY_TO_ID: dict[str, str] = {v: k for k, v in WARE_NAMES.items()}


def display_name_to_id(display_name: str) -> str | None:
    """Converts a ware display name (e.g. 'Energy Cells') to its production stats key."""
    return _DISPLAY_TO_ID.get(display_name)


def units_per_cycle(ware_id: str, sector_macro: str) -> float:
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
        amount = int(amount * SECTOR_SUNLIGHT.get(sector_macro, 1.0))
    return float(amount)


def units_per_hour(ware_id: str, sector_macro: str) -> float:
    """Returns effective units produced per hour for one module."""
    stats = PRODUCTION_STATS.get(ware_id)
    if stats is None:
        return 0.0
    return units_per_cycle(ware_id, sector_macro) * (3600 / stats["time"])


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


def _consumed_per_hour_by_id(modules) -> dict[str, float]:
    """Returns {ware_id: units_per_hour} every production module consumes, combined.

    Walks every production module (identified by its macro) and sums up how many
    units of each INPUT ware all the modules collectively consume per hour,
    picking the faction-specific recipe when one exists. Shared core of
    consumption_rates_from_modules, input_rates_from_modules and
    production_analytics_from_modules so the three can never drift apart on
    recipe handling.
    """
    consumed: dict[str, float] = {}  # ware_id → units/hr

    for m in modules:
        match = PROD_MACRO_RE.match(_get_macro(m))
        if not match:
            continue
        faction, ware = match.group(1).lower(), match.group(2).lower()
        stats = PRODUCTION_STATS.get(ware)
        if not stats or not stats['time']:
            continue

        # Pick the faction-specific recipe if one exists, fall back to default.
        method = FACTION_METHOD.get(faction, 'default')
        inputs = stats['methods'].get(method) or stats['methods'].get('default', {})
        cycles_per_hr = 3600.0 / stats['time']

        for in_ware, in_amt in inputs.items():
            consumed[in_ware] = consumed.get(in_ware, 0.0) + in_amt * cycles_per_hr

    return consumed


def consumption_rates_from_modules(modules: list[dict]) -> dict[str, float]:
    """Returns {ware_display_name: units_per_hour_consumed_internally} for a station.

    Display-name-keyed view of _consumed_per_hour_by_id so the UI can look up
    by the same name used in production_rates.

    `modules` is the list of dicts with at least a 'macro' key, as stored in
    station_modules / the export's d['modules'].

    Example: a station with 3 hull-parts modules and 2 energy-cell modules would
    return {'Energy Cells': X, 'Graphene': Y, 'Refined Metals': Z} — the combined
    internal demand from both module types.
    """
    # Unknown IDs are dropped (they'd have no WARE_COLOURS entry and the UI
    # can't use them anyway).
    return {WARE_NAMES[w]: v
            for w, v in _consumed_per_hour_by_id(modules).items()
            if w in WARE_NAMES}


def input_rates_from_modules(
    modules,
    inventory: dict[str, tuple[int, float]],
) -> list[dict]:
    """Returns per-consumed-ware rows for a station, ready to store in
    station_input_rates.

    The complement of production_analytics_from_modules: that table is keyed by
    PRODUCED ware, so externally sourced inputs (e.g. ore at a refinery) never
    get a rate row there. This is one row per CONSUMED ware — it drives the
    sized input ribbons on the UI's station production-flow panel.

    `inventory` — {ware_id: (units, volume_m3)} as stored on the Station entity.

    Each dict: ware_id, ware_name, consumption_rate (units/hr), stock_units,
    runtime_hours (stock ÷ rate; None when the rate is zero).
    """
    rows = []
    for ware_id, rate in _consumed_per_hour_by_id(modules).items():
        stock = inventory.get(ware_id, (0, 0.0))[0]   # units only
        rows.append({
            'ware_id':          ware_id,
            'ware_name':        WARE_NAMES.get(ware_id, ware_id),
            'consumption_rate': rate,
            'stock_units':      stock,
            'runtime_hours':    (stock / rate) if rate > 0 else None,
        })
    return rows


def production_analytics_from_modules(
    modules,
    inventory: dict[str, tuple[int, float]],
    sector_macro: str,
    cargo: dict | None = None,
) -> list[dict]:
    """Returns per-produced-ware analytics for a station, ready to store in
    station_production_analytics.

    `modules` — list of StationModule objects OR dicts with a 'macro' key
                (the function accepts both so it can be called from the scanner
                with entity objects and from the export layer with DB row dicts).
    `inventory` — {ware_id: (units, volume_m3)} as stored on the Station entity.
    `sector_macro` — the station's sector macro, used for energy-cell sunlight scaling.
    `cargo` — optional dict keyed by transport type ('container'/'solid'/'liquid'),
               values are objects (or dicts) with .max_m3 and .adj_m3 (or ['max_m3']
               / ['adj_m3']).  When provided, time_to_cap_hours is computed for each
               ware with a positive surplus.  Pass None to skip (e.g. from tests).

    Each returned dict contains:
      ware_id            — produced ware ID
      ware_name          — display name
      production_rate    — units/hr (all modules combined, sunlight-corrected for energy cells)
      consumption_rate   — units/hr of this ware consumed internally by other modules
      surplus_rate       — production_rate − consumption_rate
      time_to_cap_hours  — hrs until cargo bay fills at current surplus rate;
                           None when surplus_rate ≤ 0 or cargo data unavailable
      runtime_minutes    — float or None (None = no inputs needed, e.g. energy cells)
      limiting_ware_id   — ware_id of the input that runs out first, or None
      limiting_ware_name — display name of that input, or None
    """
    # Step 1: parse module macros → {produced_ware_id: [faction_token, ...]}
    prod_modules: dict[str, list[str]] = {}
    for m in modules:
        match = PROD_MACRO_RE.match(_get_macro(m))
        if not match:
            continue
        faction, ware = match.group(1).lower(), match.group(2).lower()
        if ware not in PRODUCTION_STATS:
            continue
        prod_modules.setdefault(ware, []).append(faction)

    # Step 2: sum internal consumption per input ware across all modules,
    # respecting faction-specific recipes (e.g. Teladi hull parts use teladianium).
    consumed_per_hr = _consumed_per_hour_by_id(modules)

    # Step 3: build one analytics dict per produced ware.
    analytics = []
    for ware_id, factions in prod_modules.items():
        stats = PRODUCTION_STATS[ware_id]
        count = len(factions)
        cycles_per_hr = 3600.0 / stats['time']

        # Production rate — energy cells scale with sector sunlight.
        amount = stats['amount']
        if ware_id == 'energycells':
            amount = int(amount * SECTOR_SUNLIGHT.get(sector_macro, 1.0))
        production_rate = float(amount) * cycles_per_hr * count

        # How much of this produced ware is consumed internally by other modules.
        consumption_rate = consumed_per_hr.get(ware_id, 0.0)

        # Runtime: use the default recipe to find the limiting input.
        # Faction-specific recipes affect which inputs are used but the default
        # is a close approximation and covers the vast majority of player modules.
        inputs = stats['methods'].get('default', {})
        runtime_minutes   = None
        limiting_ware_id   = None
        limiting_ware_name = None
        if inputs:
            min_rt_hrs = float('inf')
            for in_ware, qty_per_module in inputs.items():
                cons_per_hr = qty_per_module * count * cycles_per_hr
                stock = inventory.get(in_ware, (0, 0.0))[0]   # units only
                rt = stock / cons_per_hr                        # cons_per_hr always > 0
                if rt < min_rt_hrs:
                    min_rt_hrs       = rt
                    limiting_ware_id   = in_ware
                    limiting_ware_name = WARE_NAMES.get(in_ware, in_ware)
            runtime_minutes = min_rt_hrs * 60.0

        surplus_rate = production_rate - consumption_rate

        # time_to_cap_hours: worst-case hours until the cargo bay for this ware's
        # transport type fills up at the current surplus rate.  Only meaningful
        # when there is a positive surplus AND cargo data was supplied.
        time_to_cap_hours = None
        if surplus_rate > 0 and cargo is not None:
            transport    = WARE_TRANSPORT.get(ware_id, 'container')
            vol_per_unit = WARE_VOLUME.get(ware_id, 1.0)
            cs = cargo.get(transport)
            if cs is not None:
                # Use duck-typing — works with both CargoStorage dataclass objects
                # (from the scanner) and plain dicts (from tests / future DB reads).
                max_m3 = cs['max_m3'] if isinstance(cs, dict) else cs.max_m3
                adj_m3 = cs['adj_m3'] if isinstance(cs, dict) else cs.adj_m3
                free_m3 = max_m3 - adj_m3
                surplus_m3_per_hr = surplus_rate * vol_per_unit
                if surplus_m3_per_hr > 0 and free_m3 >= 0:
                    time_to_cap_hours = free_m3 / surplus_m3_per_hr

        analytics.append({
            'ware_id':            ware_id,
            'ware_name':          WARE_NAMES.get(ware_id, ware_id),
            'production_rate':    production_rate,
            'consumption_rate':   consumption_rate,
            'surplus_rate':       surplus_rate,
            'time_to_cap_hours':  time_to_cap_hours,
            'runtime_minutes':    runtime_minutes,
            'limiting_ware_id':   limiting_ware_id,
            'limiting_ware_name': limiting_ware_name,
        })

    return analytics
