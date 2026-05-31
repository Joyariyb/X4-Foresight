"""
budget.py
=========
Estimates the credit budget a station needs to keep itself supplied — the same
figure the in-game station manager shows as the station's allocated budget.

The number is reverse-engineered, not read directly: X4 doesn't store the budget
in the save. It recomputes it from each ware's storage/trade configuration. We
reproduce that computation here and have validated it to the credit against real
stations (GX HQ, Station BHS).

PER-WARE DECISION TREE
----------------------
For every ware that participates in the station's economy, the budget value is:

  1. Trade ware  (has BOTH a buy and a sell order, and is neither produced nor
     consumed by this station's production):
         amount = buy_order_remaining - current_stock
         price  = MAX market price  (data/ware_prices.py)
     A pure trader is budgeted to top up its buy order at the worst-case price.

  2. Production ware (consumed and/or produced here):
       a. Manual storage cap set (ware appears in <overrides><max amount=...>):
              amount = that manual cap        price = station buy price
       b. Automatic + produced here (e.g. a solar plant making energy cells):
              amount = 2 hours of production output   price = station buy price
              Energy cell output is scaled by the sector's sunlight multiplier.
       c. Automatic + only consumed (a raw input bought in, e.g. ore, methane):
              amount = 2 hours of consumption  price = station buy price

  3. Anything else (a buy order with no sell order and no production link) is a
     fallback we haven't seen in real data: valued like a trade ware but at the
     station buy price, and flagged so it's visible rather than silently wrong.

"AUTOMATIC vs MANUAL" is rule 5/6 from our spec: a ware's storage is MANUAL only
if it appears in <overrides><max> WITH an amount attribute. An entry with no
amount (a cleared override) or no entry at all means automatic.

STATION BUY PRICE comes from the station's own <trade><prices>: the player
<override> if set, otherwise the game's <reference>. Trade wares ignore this and
use the max market price instead.
"""

import re

from data.production_stats import PRODUCTION_STATS
from data.ware_prices import WARE_PRICES
from data.sector_stats import SECTOR_SUNLIGHT
from data.wares import WARE_NAMES
from scanner.crew_scanner import _iter_components

# Production module macros look like prod_{faction}_{ware}_macro, e.g.
# prod_gen_refinedmetals_macro. Group 1 is the faction token, group 2 the ware.
# Non-economy production modules (e.g. the HQ research landmark) don't match and
# are ignored — exactly what we want.
_PROD_MACRO_RE = re.compile(r'^prod_(\w+?)_(\w+)_macro$', re.IGNORECASE)

# Maps the faction token in a production macro to the recipe method id used in
# PRODUCTION_STATS. Determines which input list a module consumes — most modules
# are "gen" (generic) and use the default recipe; faction modules can differ
# (e.g. Teladi hull parts use teladianium instead of refined metals).
_FACTION_METHOD = {
    "gen": "default",
    "arg": "argon",
    "tel": "teladi",
    "par": "paranid",
    "spl": "split",
    "ter": "terran",
    "bor": "boron",
}

# Two real-game hours, in seconds — the window X4 budgets supply for.
_BUDGET_WINDOW_SECONDS = 2 * 3600


def _production_modules(station_elem) -> dict[str, list[str]]:
    """
    Returns {produced_ware_id: [faction_token, ...]} for the station.

    One entry per production module, so the list length is the module count for
    that ware and each token records which recipe method that module uses.
    """
    modules: dict[str, list[str]] = {}
    for comp in _iter_components(station_elem):
        if comp.get('class') != 'production':
            continue
        m = _PROD_MACRO_RE.match(comp.get('macro', ''))
        if not m:
            continue
        faction, ware = m.group(1).lower(), m.group(2).lower()
        if ware not in PRODUCTION_STATS:
            continue
        modules.setdefault(ware, []).append(faction)
    return modules


def _override_max(station_elem) -> dict[str, int]:
    """
    Returns {ware_id: manual_cap} for wares whose storage is set MANUALLY.

    Only <overrides><max> entries that carry an amount count. An entry with no
    amount is a cleared override (back to automatic) and is deliberately omitted
    so the caller treats it as automatic.
    """
    caps: dict[str, int] = {}
    overrides = station_elem.find('overrides')
    if overrides is None:
        return caps
    max_elem = overrides.find('max')
    if max_elem is None:
        return caps
    for ware in max_elem.findall('ware'):
        amount = ware.get('amount')
        if amount is not None:
            caps[ware.get('ware', '')] = int(amount)
    return caps


def _buy_prices(station_elem) -> dict[str, int]:
    """
    Returns {ware_id: buy_price} from the station's <trade><prices>.

    The player <override> price wins where present; otherwise the game's
    <reference> price is used. Values are whole credits per unit.
    """
    prices: dict[str, int] = {}
    trade = station_elem.find('trade')
    if trade is None:
        return prices
    price_elem = trade.find('prices')
    if price_elem is None:
        return prices

    # Reference first, then override on top, so override wins on collision.
    for section in ('reference', 'override'):
        sect = price_elem.find(section)
        if sect is None:
            continue
        for ware in sect.findall('ware'):
            buy = ware.get('buy')
            if buy is not None:
                prices[ware.get('ware', '')] = int(buy)
    return prices


def _trade_orders(station_elem) -> tuple[dict[str, int], set[str]]:
    """
    Returns (buy_orders, sell_wares) from the station's live trade offers.

    buy_orders maps ware → remaining quantity the station wants to buy (the
    'buyer' offers). sell_wares is the set of wares it currently offers to sell
    (the 'seller' offers). Together they identify trade wares (in both sets).
    """
    buy_orders: dict[str, int] = {}
    sell_wares: set[str] = set()
    trade = station_elem.find('trade')
    if trade is None:
        return buy_orders, sell_wares
    offers = trade.find('offers')
    if offers is None:
        return buy_orders, sell_wares
    production = offers.find('production')
    if production is None:
        return buy_orders, sell_wares

    for t in production.findall('trade'):
        ware = t.get('ware', '')
        if 'buyer' in t.attrib:
            try:
                buy_orders[ware] = int(t.get('amount', 0))
            except (ValueError, TypeError):
                buy_orders[ware] = 0
        elif 'seller' in t.attrib:
            sell_wares.add(ware)
    return buy_orders, sell_wares


def _inventory(station_elem) -> dict[str, int]:
    """
    Returns {ware_id: units_in_stock} summed across the station's storage.

    Uses _iter_components so cargo inside docked ships is never counted as the
    station's own stock.
    """
    inv: dict[str, int] = {}
    for comp in _iter_components(station_elem):
        if comp.get('class') != 'storage':
            continue
        cargo = comp.find('cargo')
        if cargo is None:
            continue
        for ware in cargo.findall('ware'):
            wid = ware.get('ware', '')
            try:
                amt = int(float(ware.get('amount', 0)))
            except (ValueError, TypeError):
                amt = 0
            inv[wid] = inv.get(wid, 0) + amt
    return inv


def _two_hour_flows(modules: dict[str, list[str]], sunlight: float
                    ) -> tuple[dict[str, float], dict[str, float]]:
    """
    Converts the module list into 2-hour production and consumption totals.

    Returns (produced_2h, consumed_2h):
      produced_2h  — units each ware is OUTPUT over the budget window. Energy
                     cell output is scaled by the sector sunlight multiplier
                     (solar plants are the only sunlight-dependent producers).
      consumed_2h  — units each input ware is CONSUMED over the budget window,
                     summed across every module that uses it.
    """
    produced_2h: dict[str, float] = {}
    consumed_2h: dict[str, float] = {}

    for ware, factions in modules.items():
        recipe = PRODUCTION_STATS[ware]
        cycle_time = recipe['time']
        if not cycle_time:
            continue
        cycles = _BUDGET_WINDOW_SECONDS / cycle_time

        for faction in factions:
            # Output: one module makes `amount` per cycle. Sunlight only scales
            # solar energy-cell production.
            out = recipe['amount'] * cycles
            if ware == 'energycells':
                out *= sunlight
            produced_2h[ware] = produced_2h.get(ware, 0.0) + out

            # Inputs: pick the recipe method matching this module's faction,
            # falling back to default when the faction has no distinct recipe.
            method = _FACTION_METHOD.get(faction, 'default')
            inputs = recipe['methods'].get(method) or recipe['methods'].get('default', {})
            for in_ware, in_amt in inputs.items():
                consumed_2h[in_ware] = consumed_2h.get(in_ware, 0.0) + in_amt * cycles

    return produced_2h, consumed_2h


def estimate_station_budget(station_elem, sector_name: str) -> dict:
    """
    Estimates the station's supply budget in credits.

    Returns:
      {
        "total":     float,          # sum of all line items, in credits
        "sunlight":  float,          # multiplier applied to energy-cell output
        "lines": [                   # one entry per budgeted ware
            {"ware", "amount", "price", "value", "basis"}, ...
        ],
      }
    `basis` records which branch of the decision tree set the value, so the
    breakdown is auditable in the report and JSON.
    """
    sunlight = SECTOR_SUNLIGHT.get(sector_name)
    if sunlight is None:
        # A missing sector would silently under-budget energy production. Surface
        # it instead of guessing quietly (see Generators/generate_sector_stats.py).
        print(f"[Budget] WARNING: sector {sector_name!r} not in SECTOR_SUNLIGHT — "
              f"using sunlight 1.0; energy-cell budget may be understated.")
        sunlight = 1.0

    modules = _production_modules(station_elem)
    produced_2h, consumed_2h = _two_hour_flows(modules, sunlight)
    manual_caps = _override_max(station_elem)
    buy_prices  = _buy_prices(station_elem)
    buy_orders, sell_wares = _trade_orders(station_elem)
    inventory   = _inventory(station_elem)

    produced = set(produced_2h)
    consumed = set(consumed_2h)

    # A ware is budgeted if it is consumed by production OR has an active buy
    # order (rule 7). Produced-only outputs with no buy order carry no cost.
    candidates = consumed | set(buy_orders)

    lines = []
    for ware in sorted(candidates):
        stock        = inventory.get(ware, 0)
        is_manual    = ware in manual_caps
        is_produced  = ware in produced
        participates = is_produced or ware in consumed
        has_buy      = ware in buy_orders
        has_sell     = ware in sell_wares

        if has_buy and has_sell and not participates:
            # Pure trade ware — top up the buy order at worst-case price.
            amount = max(buy_orders[ware] - stock, 0)
            price  = WARE_PRICES.get(ware, {}).get('max', 0)
            basis  = "trade (max price)"
        elif participates:
            if is_manual:
                amount = manual_caps[ware]
                price  = buy_prices.get(ware, WARE_PRICES.get(ware, {}).get('average', 0))
                basis  = "manual storage cap"
            elif is_produced:
                amount = produced_2h[ware]
                price  = buy_prices.get(ware, WARE_PRICES.get(ware, {}).get('average', 0))
                basis  = "auto: 2h production"
            else:
                amount = consumed_2h[ware]
                price  = buy_prices.get(ware, WARE_PRICES.get(ware, {}).get('average', 0))
                basis  = "auto: 2h consumption"
        else:
            # Buy order with no sell order and no production link. Unseen in real
            # data — value it like a buy top-up at the station price, and flag it.
            amount = max(buy_orders[ware] - stock, 0)
            price  = buy_prices.get(ware, WARE_PRICES.get(ware, {}).get('average', 0))
            basis  = "buy order (unverified)"

        value = amount * price
        lines.append({
            "ware":      ware,
            # Display name for the UI/report; falls back to a title-cased id.
            "ware_name": WARE_NAMES.get(ware, ware.replace('_', ' ').title()),
            "amount":    amount,
            "price":     price,
            "value":     value,
            "basis":     basis,
        })

    total = sum(line["value"] for line in lines)
    return {"total": total, "sunlight": sunlight, "lines": lines}
