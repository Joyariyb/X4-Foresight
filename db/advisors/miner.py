"""Core role: Miner-domain advisor rules (mining-ship supply gaps).

See advisors.py for the shared _finding() renderer, and combine.py's
compute_advisors() for how these rules combine with other domains into one
findings list.

Where the other domains reason about MONEY (economy: a station's own surplus;
trader: galaxy-wide arbitrage and where to plant a mining STATION), this domain
reasons about the mining SHIPS that feed player stations their raw inputs. The
canonical case: a station consumes a mineable ware, has no mining deliveries on
record recently, and is running its stock down — the fix is a miner, not a
market run, so it earns its own advice rather than an economy "buy it" card.

Distance uses distances_from_player (jumps from the nearest player station),
the same asset-relative anchor economy.py/trader.py use: a miner works out of a
home station, so reachability is measured from the empire's footprint, not the
avatar's current position.
"""
from __future__ import annotations
from scanner.galaxy_map import distances_from
from .advisors import _finding
# Yield ranking/labels are shared reference data that trader.py already owns
# (its siting rule ranks the same deposits) — importing keeps the two domains
# reading one table instead of drifting apart. No cycle: trader imports nothing
# from here.
from .trader import YIELD_RANK, YIELD_LABEL, _DEFAULT_YIELD_RANK
# The military domain owns the definition of "hostile" (a reputation floor);
# reuse it so a miner-exposed card and a military threat card never disagree on
# which factions count. No cycle: military doesn't import from here.
from .military import HOSTILE_REPUTATION

# "No mining in the last hour" — the window over which an absence of
# trade_history_mining deliveries counts as "this input isn't being mined".
# Matches the user-facing framing of the rule; game hours track real hours 1:1.
MINING_LOOKBACK_HOURS = 1.0

# Only nag when the input is actually about to run dry. A station with days of
# stock buffered isn't starving even with no miner assigned — it may be fed by
# trade, or simply hasn't drawn its buffer down yet. runtime_hours at/under this
# is "act now"; above it we stay quiet rather than crying wolf.
STARVE_RUNTIME_HOURS = 3.0

# How far from the player's footprint a deposit can sit and still back a "add a
# miner" suggestion. A miner ranges out from its home station, so a deposit past
# this is too far to service cheaply — and with NO reachable deposit the advice
# would be wrong (the ware has to be bought via trade, an economy/trader
# concern), so this rule stays silent in that case.
DEPOSIT_MAX_JUMPS = 8

# Coarse miner-size recommendation by hourly volume demand (m3/hr). These are
# deliberately rough bands, not a fleet-planning calculator: a single M miner
# comfortably runs a few thousand m3/hr on a short local route, an L miner an
# order of magnitude more. The card states the measured need alongside the hint
# so the player can size up if their deposit is far from home.
SIZE_BANDS = ((1500.0, 'M-class'), (float('inf'), 'L-class'))

# transport_type -> the in-game miner role that can carry it (mirrors
# constants.js MINER_ROLES). Solids (ore, silicon) and liquids/gases (methane,
# hydrogen, helium) need different ships, so the card names the right one.
MINER_TYPE_BY_TRANSPORT = {'solid': 'Solid miner', 'liquid': 'Liquid miner'}

# ── Rule 2 (mine vs buy) tuning ──────────────────────────────────────────────
# How far back to total a station's purchases of a mineable ware. Longer than
# the rule-1 mining window: a buy-vs-mine case is about a spending *habit*, not
# a single missed hour, so a couple of hours of history gives a steadier figure.
MINE_VS_BUY_LOOKBACK_HOURS = 2.0
# Don't nag about a trivial top-up buy. A station that mines most of its own ore
# and buys a little to cover a spike shouldn't trip this — only a real, ongoing
# spend on something a nearby miner could supply for free is worth flagging.
MINE_VS_BUY_MIN_SPEND_CR = 100_000

# ── Rule 3 (idle miner) tuning ───────────────────────────────────────────────
# Orders that mean a miner is NOT doing its job. 'Mining' and 'Trading' are
# productive; 'Waiting'/'Idle'/none mean the ship is parked. 'Docked' is left
# out on purpose — a docked miner may be mid-cycle (refuel/repair) rather than
# genuinely idle, and flagging those would cry wolf. None is matched in Python
# (SQL can't hold it in an IN list cleanly).
IDLE_MINER_ORDERS = frozenset({'Waiting', 'Idle', ''})

# ── Rule 4 (miner exposed) tuning ────────────────────────────────────────────
# How many hostile ships in a miner's sector make it "exposed". A lone patrol
# passing through isn't the same as a standing enemy fleet; a handful is the
# floor at which an unescorted miner is genuinely at risk. Note npc_ships is
# only populated in player-station sectors, so a miner working a hostile sector
# with no player presence nearby simply has no threat data to trip this.
MINER_EXPOSED_MIN_HOSTILES = 3

# ── Rule 6 (mining oversupply) tuning ────────────────────────────────────────
# Solid/liquid storage at/above this fill (percent, 0-100) is "about to bounce
# deliveries" — high enough that incoming mined loads will start being refused.
OVERSUPPLY_FILL_PCT = 90.0
# Only flag oversupply while miners are STILL delivering into the full bay
# (deliveries within this window) — a capped bay no longer receiving isn't an
# active waste, just full.
OVERSUPPLY_DELIVERY_HOURS = 1.0

# ── Rule 7 (mineral demand) tuning ───────────────────────────────────────────
# Minimum standing-demand value (Cr) for an NPC mineral buyer to be worth a
# "task a miner to sell here" card — keeps a trickle of demand from spamming the
# feed with runs that aren't worth diverting a ship for.
MINERAL_DEMAND_MIN_VALUE_CR = 100_000


def _miner_type_from_role(role: str | None) -> str:
    """The card's miner-type label from a ship's role string
    ('Miner (Solid)' -> 'Solid miner'). Falls back to a generic label for any
    role wording we don't recognise rather than guessing solid vs liquid."""
    if role:
        if 'Liquid' in role:
            return 'Liquid miner'
        if 'Solid' in role:
            return 'Solid miner'
    return 'mining ship'

# 3 phrasings per finding type so the feed doesn't read as copy-pasted.
TEMPLATES: dict[str, list[str]] = {
    'mining_supply_gap': [
        "{station_name} in {sector_name} is running low on {ware_name} "
        "(~{runtime}h of stock left) with no mining deliveries logged in the "
        "last hour — assign a {miner_type} (~{size_hint}) to cover its "
        "{need_units} units/hr draw.{deposit_note}",
        "No miner is feeding {station_name}'s {ware_name} demand — it consumes "
        "{need_units} units/hr and has only ~{runtime}h of stock left. A "
        "{miner_type} ({size_hint}) would keep it supplied.{deposit_note}",
        "{ware_name} is about to run dry at {station_name} ({sector_name}): "
        "~{runtime}h left, nothing mined in the last hour. Put a {miner_type} "
        "(~{size_hint}) on its {need_units} units/hr draw.{deposit_note}",
    ],
    'mine_vs_buy': [
        "{station_name} bought {bought_units} {ware_name} from NPC sellers "
        "recently (~{spend_cr} Cr) while a {yield_label} {ware_name} deposit "
        "sits {deposit_jumps} jump(s) away in {deposit_sector_name} — a "
        "{miner_type} would supply it at zero ware cost.",
        "You're paying for mineable {ware_name}: {station_name} spent ~{spend_cr} "
        "Cr buying {bought_units} units recently, with a {yield_label} deposit "
        "only {deposit_jumps} jump(s) out in {deposit_sector_name}. A "
        "{miner_type} would mine it for free.",
        "{station_name}'s {ware_name} is coming from the market (~{spend_cr} Cr, "
        "{bought_units} units recently) when {deposit_sector_name} has a "
        "{yield_label} field {deposit_jumps} jump(s) away — assign a "
        "{miner_type} and stop paying for it.",
    ],
    'idle_miner': [
        "{ship_name} ({ship_display}) is {order} in {sector_name} with "
        "{cargo_max} m3 of mining capacity sitting idle — assign it a mining "
        "route to put that {miner_type} to work.",
        "Idle miner: {ship_name} ({cargo_max} m3) has been {order} in "
        "{sector_name} with no mining order — a {miner_type} doing nothing is "
        "lost throughput.",
        "{ship_name} is parked ({order}) in {sector_name} while its "
        "{cargo_max} m3 bay stays empty — give this {miner_type} a mining "
        "assignment.",
    ],
    'miner_exposed': [
        "{ship_name} ({ship_display}) is out mining in {sector_name}, where "
        "{faction_name} has {hostile_count} ship(s) — an unescorted miner here "
        "is a loss waiting to happen. Pull it to a safe deposit or give it an "
        "escort.",
        "Exposed miner: {ship_name} is working {sector_name} with "
        "{hostile_count} hostile {faction_name} ship(s) present and no escort. "
        "Move it before you lose it.",
        "{sector_name} has {hostile_count} {faction_name} ship(s) and your "
        "miner {ship_name} ({ship_display}) is out there undefended — retask it "
        "somewhere safe or send cover.",
    ],
    'mining_oversupply': [
        "{station_name}'s {cargo_type} storage is {fill_pct}% full and "
        "{miner_count} miner(s) are still delivering {ware_name} — deliveries "
        "will start bouncing. Reassign a miner to a station that needs it or "
        "expand storage.",
        "{station_name} is drowning in {ware_name}: {cargo_type} storage at "
        "{fill_pct}% with {miner_count} miner(s) still hauling it in. Redirect "
        "one or add {cargo_type} storage.",
        "Oversupply at {station_name} — {cargo_type} bay {fill_pct}% full while "
        "{miner_count} miner(s) keep delivering {ware_name}. That capacity is "
        "wasted; move a miner to a hungrier station.",
    ],
    'mineral_demand': [
        "{npc_name} is buying {ware_name} at {price} Cr/unit, {jumps} jump(s) "
        "from your {yield_label} {ware_name} deposit in {deposit_sector_name} — "
        "task a {miner_type} to sell there (~{value_cr} Cr of standing demand).",
        "Unworked demand: {npc_name} wants {ware_name} at {price} Cr/unit and "
        "you have a {yield_label} deposit {jumps} jump(s) away in "
        "{deposit_sector_name}. A {miner_type} could mine and sell it for "
        "~{value_cr} Cr.",
        "{ware_name} sells to {npc_name} at {price} Cr/unit, within reach of "
        "your {yield_label} {deposit_sector_name} deposit — put a {miner_type} "
        "on it for ~{value_cr} Cr of open demand.",
    ],
}


# ── Nearest reachable deposit lookup ─────────────────────────────────────────

def _nearest_deposits(conn, scan_id, distances_from_player) -> dict[str, dict]:
    """{ware_id: nearest reachable deposit} — the closest discovered sector that
    holds each mineable ware, within DEPOSIT_MAX_JUMPS of the player's
    footprint. Ties on distance break toward the richer yield, so the note a
    card shows names the best deposit a miner would actually work.

    Built once and shared across every candidate station rather than re-querying
    per finding, same pass-the-lookup-in convention as the economy rules."""
    best: dict[str, dict] = {}
    for r in conn.execute(
            "SELECT sr.sector_macro, sr.ware, sr.yield_level, "
            "       sec.sector_name "
            "FROM sector_resources sr "
            "JOIN sectors sec ON sec.sector_macro = sr.sector_macro "
            "WHERE sr.last_scan_id = ? AND sec.is_discovered = 1",
            (scan_id,)):
        jumps = distances_from_player.get(r['sector_macro'])
        if jumps is None or jumps > DEPOSIT_MAX_JUMPS:
            continue
        rank = YIELD_RANK.get(r['yield_level'], _DEFAULT_YIELD_RANK)
        cur = best.get(r['ware'])
        # Closer wins; equal distance breaks toward the richer deposit.
        if cur is None or jumps < cur['jumps'] or (
                jumps == cur['jumps'] and rank > cur['rank']):
            best[r['ware']] = {
                'sector_macro': r['sector_macro'],
                'sector_name': r['sector_name'] or r['sector_macro'],
                'yield_level': r['yield_level'], 'rank': rank, 'jumps': jumps,
            }
    return best


def _size_hint(need_m3_per_hr: float) -> str:
    for ceiling, label in SIZE_BANDS:
        if need_m3_per_hr <= ceiling:
            return label
    return SIZE_BANDS[-1][1]


# ── Rule 1: mining supply gap (mineable input, no recent miner, running dry) ──

def mining_supply_gap_findings(conn, scan_id, distances_from_player) -> list[dict]:
    """Player stations consuming a mineable ware that has had no mining delivery
    in the last MINING_LOOKBACK_HOURS and is about to run dry (runtime at/under
    STARVE_RUNTIME_HOURS), when a workable deposit sits within reach.

    The three conditions together are what make "add a miner" the right advice:
    running dry alone could be fixed by trade; no-recent-mining alone might just
    mean a healthy buffer; and with no reachable deposit a miner can't help at
    all. Requiring a reachable deposit also lets the card name where to send the
    ship, which is the "nearby sector resource availability" half of the ask."""
    # Current in-game clock — the anchor the mining lookback window subtracts
    # from (trade_history_mining stores absolute game_time_s, not time_ago).
    row = conn.execute(
        "SELECT game_time_s FROM scans WHERE scan_id = ?", (scan_id,)).fetchone()
    if not row:
        return []
    now_s = row['game_time_s'] or 0
    cutoff_s = now_s - MINING_LOOKBACK_HOURS * 3600

    # (station, ware) pairs that DID receive a mining delivery inside the window
    # — these are being mined, so they're excluded below.
    recently_mined = {
        (r['station_id'], r['ware_id']) for r in conn.execute(
            "SELECT DISTINCT station_id, ware_id FROM trade_history_mining "
            "WHERE game_time_s >= ?", (cutoff_s,))}

    deposits = _nearest_deposits(conn, scan_id, distances_from_player)
    if not deposits:
        return []  # nothing mineable in range — no miner advice to give

    rows = conn.execute(
        "SELECT ir.station_id, ir.ware_id, ir.ware_name, ir.consumption_rate, "
        "       ir.stock_units, ir.runtime_hours, "
        "       s.code, s.name AS station_name, s.sector_macro, "
        "       sec.sector_name, wm.transport_type, wm.volume_m3 "
        "FROM station_input_rates ir "
        "JOIN stations s ON s.object_id = ir.station_id AND s.scan_id = ir.scan_id "
        "LEFT JOIN sectors sec ON sec.sector_macro = s.sector_macro "
        "LEFT JOIN ware_metadata wm ON wm.ware_id = ir.ware_id "
        "WHERE ir.scan_id = ? AND ir.consumption_rate > 0 "
        "  AND ir.runtime_hours IS NOT NULL AND ir.runtime_hours <= ?",
        (scan_id, STARVE_RUNTIME_HOURS))
    findings = []
    for r in rows:
        deposit = deposits.get(r['ware_id'])
        if deposit is None:
            continue  # consumed input isn't mineable within reach — skip
        if (r['station_id'], r['ware_id']) in recently_mined:
            continue  # a miner is already delivering this

        rate = r['consumption_rate'] or 0
        volume = r['volume_m3'] or 0
        need_m3 = rate * volume
        miner_type = MINER_TYPE_BY_TRANSPORT.get(
            r['transport_type'], 'mining ship')
        # Urgency-weighted like economy.overflow_risk: the same hourly draw is
        # more pressing the sooner the buffer empties. Scaled by need so a big
        # consumer outranks a trickle that happens to be equally close to dry.
        priority = rate * (1.0 + 1.0 / max(r['runtime_hours'], 0.1))

        deposit_note = (
            f" Nearest deposit: {YIELD_LABEL.get(deposit['yield_level'], 'Unknown')} "
            f"{r['ware_name']} in {deposit['sector_name']} "
            f"({deposit['jumps']} jump(s) away).")
        slots = {
            'station_name': r['station_name'] or r['code'],
            'sector_name':  r['sector_name'] or 'an unknown sector',
            'ware_name':    r['ware_name'],
            'miner_type':   miner_type,
            'size_hint':    _size_hint(need_m3),
            'need_units':   round(rate),
            'runtime':      round(r['runtime_hours'], 1),
            'deposit_note': deposit_note,
        }
        evidence = {
            'station_id': r['station_id'], 'code': r['code'],
            'ware_id': r['ware_id'],
            'consumption_rate': round(rate, 1),
            'stock_units': r['stock_units'],
            'runtime_hours': round(r['runtime_hours'], 2),
            'need_m3_per_hr': round(need_m3),
            'deposit_sector': deposit['sector_macro'],
            'deposit_yield': deposit['yield_level'],
            'deposit_jumps': deposit['jumps'],
        }
        findings.append(_finding(
            f"mininggap:{r['station_id']}:{r['ware_id']}",
            'miner', 'mining_supply_gap', priority, slots, evidence, TEMPLATES))
    return findings


# ── Rule 2: mine vs buy (paying NPCs for a ware a nearby miner could supply) ──

def mine_vs_buy_findings(conn, scan_id, distances_from_player) -> list[dict]:
    """Player stations that have spent real credits BUYING a mineable ware
    (trade_history direction 'In') over the last MINE_VS_BUY_LOOKBACK_HOURS,
    when a workable deposit for that ware sits within reach.

    Mined ware costs nothing at the source, so a sustained buy of something a
    nearby miner could pull is money left on the table — the priority IS that
    spend. Unlike rule 1 this doesn't care whether the station is running dry
    (it's clearly being supplied, just expensively); the spend threshold is what
    keeps a one-off top-up from tripping it."""
    row = conn.execute(
        "SELECT game_time_s FROM scans WHERE scan_id = ?", (scan_id,)).fetchone()
    if not row:
        return []
    cutoff_s = (row['game_time_s'] or 0) - MINE_VS_BUY_LOOKBACK_HOURS * 3600

    deposits = _nearest_deposits(conn, scan_id, distances_from_player)
    if not deposits:
        return []

    # Sum buys per (station, ware) over the window. Only player stations appear
    # in stations; the join drops any trade whose station is no longer ours.
    rows = conn.execute(
        "SELECT th.station_id, th.ware_id, th.ware_name, "
        "       SUM(th.amount)   AS bought_units, "
        "       SUM(th.total_cr) AS spend_cr, "
        "       s.code, s.name AS station_name, wm.transport_type "
        "FROM trade_history th "
        "JOIN stations s ON s.object_id = th.station_id AND s.scan_id = ? "
        "LEFT JOIN ware_metadata wm ON wm.ware_id = th.ware_id "
        "WHERE th.direction = 'In' AND th.game_time_s >= ? "
        "GROUP BY th.station_id, th.ware_id",
        (scan_id, cutoff_s))
    findings = []
    for r in rows:
        deposit = deposits.get(r['ware_id'])
        if deposit is None:
            continue  # not mineable within reach — buying is the only option
        spend = r['spend_cr'] or 0
        if spend < MINE_VS_BUY_MIN_SPEND_CR:
            continue  # trivial top-up, not a spending habit worth flagging
        miner_type = MINER_TYPE_BY_TRANSPORT.get(
            r['transport_type'], 'mining ship')
        # The spend itself is the value at stake — what a miner would stop you
        # paying. No distance dampening: the deposit is already gated to within
        # DEPOSIT_MAX_JUMPS, and the saving doesn't shrink with a longer haul.
        priority = spend
        slots = {
            'station_name': r['station_name'] or r['code'],
            'ware_name':    r['ware_name'],
            'bought_units': round(r['bought_units'] or 0),
            'spend_cr':     round(spend),
            'miner_type':   miner_type,
            'deposit_sector_name': deposit['sector_name'],
            'deposit_jumps': deposit['jumps'],
            'yield_label':  YIELD_LABEL.get(deposit['yield_level'], 'Unknown'),
        }
        evidence = {
            'station_id': r['station_id'], 'code': r['code'],
            'ware_id': r['ware_id'],
            'bought_units': round(r['bought_units'] or 0),
            'spend_cr': round(spend),
            'deposit_sector': deposit['sector_macro'],
            'deposit_yield': deposit['yield_level'],
            'deposit_jumps': deposit['jumps'],
        }
        findings.append(_finding(
            f"minevsbuy:{r['station_id']}:{r['ware_id']}",
            'miner', 'mine_vs_buy', priority, slots, evidence, TEMPLATES))
    return findings


# ── Rule 3: idle miner (a mining ship parked with no mining order) ───────────

def idle_miner_findings(conn, scan_id) -> list[dict]:
    """Player miners whose current order means they're doing nothing (see
    IDLE_MINER_ORDERS) — parked capacity that could be feeding a station.

    Priority is the idle bay size, same proxy logistics.idle_hauler uses for the
    same reason: without knowing what THIS ship would earn per trip, the biggest
    idle capacity is the biggest missed throughput."""
    rows = conn.execute(
        "SELECT sh.object_id, sh.code, sh.name, sh.role, sh.ship_order, "
        "       sh.cargo_max_m3, sh.sector_macro, "
        "       sec.sector_name "
        "FROM ships sh "
        "LEFT JOIN sectors sec ON sec.sector_macro = sh.sector_macro "
        "WHERE sh.scan_id = ? AND sh.role LIKE 'Miner%' "
        "  AND sh.cargo_max_m3 IS NOT NULL AND sh.cargo_max_m3 > 0",
        (scan_id,))
    findings = []
    for r in rows:
        # None isn't expressible in the SQL IN list, so the idle test lives here.
        order = r['ship_order']
        if (order or '') not in IDLE_MINER_ORDERS:
            continue
        cargo_max = r['cargo_max_m3']
        priority = cargo_max
        slots = {
            'ship_name':    r['code'] or r['object_id'],
            'ship_display': r['name'] or r['code'] or 'unnamed',
            'order':        order or 'idle',
            'sector_name':  r['sector_name'] or 'an unknown sector',
            'cargo_max':    round(cargo_max),
            'miner_type':   _miner_type_from_role(r['role']),
        }
        evidence = {
            'ship_id': r['object_id'], 'code': r['code'], 'role': r['role'],
            'ship_order': order, 'cargo_max_m3': cargo_max,
            'sector_macro': r['sector_macro'],
        }
        findings.append(_finding(
            f"idleminer:{r['object_id']}",
            'miner', 'idle_miner', priority, slots, evidence, TEMPLATES))
    return findings


# ── Rule 4: miner exposed (player miner free-flying in a hostile sector) ─────

def miner_exposed_findings(conn, scan_id) -> list[dict]:
    """Free-flying player miners in a sector holding a meaningful hostile fleet.

    The military domain anchors on player STATIONS; roaming miners are the gap
    it doesn't cover, and they're defenceless. Hostility uses the shared
    HOSTILE_REPUTATION floor so this never disagrees with a military card about
    who's an enemy. A docked miner is treated as safe (it's at a station), so
    only free-flying ones (docked_at IS NULL) count."""
    hostile_ids = {r['faction_id'] for r in conn.execute(
        "SELECT faction_id FROM reputation WHERE scan_id = ? AND value <= ?",
        (scan_id, HOSTILE_REPUTATION))}
    if not hostile_ids:
        return []

    # Hostile ships per sector: total count + the biggest single hostile faction
    # (its name headlines the card). npc_ships only covers player-station sectors
    # (see MINER_EXPOSED_MIN_HOSTILES note), which is exactly where a player
    # miner and an enemy fleet can share a sector.
    placeholders = ",".join("?" * len(hostile_ids))
    by_sector: dict[str, dict] = {}
    for r in conn.execute(
            f"SELECT sector_macro, sector_name, owner_id, owner_name, "
            f"       COUNT(*) AS n "
            f"FROM npc_ships WHERE scan_id = ? AND owner_id IN ({placeholders}) "
            f"GROUP BY sector_macro, owner_id",
            (scan_id, *hostile_ids)):
        sec = by_sector.setdefault(r['sector_macro'], {
            'total': 0, 'sector_name': r['sector_name'], 'top': None, 'top_n': 0})
        sec['total'] += r['n']
        if r['n'] > sec['top_n']:
            sec['top_n'] = r['n']
            sec['top'] = r['owner_name'] or r['owner_id']

    findings = []
    for r in conn.execute(
            "SELECT object_id, code, name, role, sector_macro "
            "FROM ships WHERE scan_id = ? AND role LIKE 'Miner%' "
            "  AND docked_at IS NULL",
            (scan_id,)):
        sec = by_sector.get(r['sector_macro'])
        if not sec or sec['total'] < MINER_EXPOSED_MIN_HOSTILES:
            continue
        # More hostiles = more urgent; the raw count is the whole signal here.
        priority = float(sec['total'])
        slots = {
            'ship_name':    r['code'] or r['object_id'],
            'ship_display': r['name'] or r['code'] or 'unnamed',
            'sector_name':  sec['sector_name'] or 'a contested sector',
            'faction_name': sec['top'] or 'hostile forces',
            'hostile_count': sec['total'],
        }
        evidence = {
            'ship_id': r['object_id'], 'code': r['code'], 'role': r['role'],
            'sector_macro': r['sector_macro'],
            'hostile_ship_count': sec['total'],
        }
        findings.append(_finding(
            f"minerexposed:{r['object_id']}",
            'miner', 'miner_exposed', priority, slots, evidence, TEMPLATES))
    return findings


# ── Rule 6: mining oversupply (full solid/liquid bay, miners still delivering) ─

def mining_oversupply_findings(conn, scan_id) -> list[dict]:
    """Player stations whose solid or liquid storage is at/over OVERSUPPLY_FILL_PCT
    while miners are STILL delivering that cargo type — incoming loads about to
    bounce. The inverse of rule 1: too much of a mined ware, not too little.

    Keyed by cargo TYPE (solid/liquid), not ware, because storage caps are
    per-type: a full solid bay bounces every mined solid regardless of which
    ore it is, and the recent-delivery join tells us miners are actively feeding
    it (a merely-full bay nobody is delivering into isn't an active waste)."""
    row = conn.execute(
        "SELECT game_time_s FROM scans WHERE scan_id = ?", (scan_id,)).fetchone()
    if not row:
        return []
    cutoff_s = (row['game_time_s'] or 0) - OVERSUPPLY_DELIVERY_HOURS * 3600

    # Recent mining deliveries grouped by (station, transport type): how many
    # distinct miners are feeding it and a sample ware name for the card.
    deliveries: dict[tuple[str, str], dict] = {}
    for r in conn.execute(
            "SELECT thm.station_id, wm.transport_type, thm.ware_name, "
            "       COUNT(DISTINCT thm.ship_id) AS miners "
            "FROM trade_history_mining thm "
            "LEFT JOIN ware_metadata wm ON wm.ware_id = thm.ware_id "
            "WHERE thm.game_time_s >= ? "
            "GROUP BY thm.station_id, wm.transport_type",
            (cutoff_s,)):
        tt = r['transport_type']
        if tt not in ('solid', 'liquid'):
            continue
        deliveries[(r['station_id'], tt)] = {
            'miners': r['miners'] or 0, 'ware_name': r['ware_name'] or tt}

    findings = []
    for r in conn.execute(
            "SELECT sc.station_id, sc.cargo_type, sc.pct, "
            "       s.code, s.name AS station_name "
            "FROM station_cargo sc "
            "JOIN stations s ON s.object_id = sc.station_id AND s.scan_id = sc.scan_id "
            "WHERE sc.scan_id = ? AND sc.cargo_type IN ('solid', 'liquid') "
            "  AND sc.pct >= ?",
            (scan_id, OVERSUPPLY_FILL_PCT)):
        d = deliveries.get((r['station_id'], r['cargo_type']))
        if not d:
            continue  # full, but nothing being mined into it — not a miner issue
        # Fuller bay + more miners hammering it = more throughput being wasted.
        priority = (r['pct'] / 100.0) * (1 + d['miners'])
        slots = {
            'station_name': r['station_name'] or r['code'],
            'cargo_type':   r['cargo_type'],
            'fill_pct':     round(r['pct']),
            'miner_count':  d['miners'],
            'ware_name':    d['ware_name'],
        }
        evidence = {
            'station_id': r['station_id'], 'code': r['code'],
            'cargo_type': r['cargo_type'], 'fill_pct': round(r['pct'], 1),
            'delivering_miners': d['miners'],
        }
        findings.append(_finding(
            f"miningover:{r['station_id']}:{r['cargo_type']}",
            'miner', 'mining_oversupply', priority, slots, evidence, TEMPLATES))
    return findings


# ── Rule 7: mineral demand (reachable NPC buyer for a ware you can mine) ─────

def mineral_demand_findings(conn, scan_id, distances_from_player,
                             demand_by_ware) -> list[dict]:
    """Reachable NPC buyers of a mineable ware for which the player has a
    workable deposit — a miner could mine it (free) and sell it. Reuses the
    shared npc_demand_by_ware lookup (already reputation- and distance-gated)
    rather than re-querying offers, and crosses it with _nearest_deposits so we
    only suggest wares the player can actually extract.

    One finding per ware (its best-value reachable buyer), gated by
    MINERAL_DEMAND_MIN_VALUE_CR so trivial demand doesn't spam the feed. Distinct
    from economy.market_opportunity, which needs the player to already PRODUCE a
    surplus of the ware — this needs only a deposit, and the action is 'assign a
    miner', not 'route your surplus hauler'."""
    deposits = _nearest_deposits(conn, scan_id, distances_from_player)
    if not deposits:
        return []
    # ware_id -> (name, transport_type) for the wares we might advise on.
    ware_meta = {r['ware_id']: (r['name'], r['transport_type'])
                 for r in conn.execute(
                     "SELECT ware_id, name, transport_type FROM ware_metadata")}

    findings = []
    for ware_id, deposit in deposits.items():
        demands = demand_by_ware.get(ware_id)
        if not demands:
            continue
        # Best payer net of distance — same weighting economy.pricing_gap uses.
        best = max(demands, key=lambda d: (d['price'] or 0) / (1 + d['jumps']))
        price_cr = (best['price'] or 0) / 100.0
        value = price_cr * (best['demand_depth'] or 0)
        if value < MINERAL_DEMAND_MIN_VALUE_CR:
            continue
        name, transport = ware_meta.get(ware_id, (ware_id, None))
        miner_type = MINER_TYPE_BY_TRANSPORT.get(transport, 'mining ship')
        priority = value
        slots = {
            'npc_name':   best['station_name'] or best['code'],
            'ware_name':  name,
            'price':      round(price_cr, 1),
            'jumps':      best['jumps'],
            'deposit_sector_name': deposit['sector_name'],
            'yield_label': YIELD_LABEL.get(deposit['yield_level'], 'Unknown'),
            'value_cr':   round(value),
            'miner_type': miner_type,
        }
        evidence = {
            'npc_station_id': best['object_id'], 'ware_id': ware_id,
            'price': price_cr, 'demand_depth': best['demand_depth'],
            'jumps': best['jumps'],
            'deposit_sector': deposit['sector_macro'],
            'deposit_yield': deposit['yield_level'],
            'value_cr': round(value),
        }
        findings.append(_finding(
            f"mineraldemand:{best['object_id']}:{ware_id}",
            'miner', 'mineral_demand', priority, slots, evidence, TEMPLATES))
    return findings
