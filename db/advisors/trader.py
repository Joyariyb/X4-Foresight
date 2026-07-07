"""Core role: Trader-domain advisor rules (station siting, arbitrage, stranded
deliveries, idle capital, reputation-locked trade).

See advisors.py for the shared _finding() renderer and lookups this module
builds on, and __init__.py's compute_advisors() for how these rules combine
with other domains into one findings list.

economy.py/logistics.py react to ONE station's current surplus/cargo state.
Trader rules instead reason at the galaxy/fleet level — where to expand, where
the biggest cross-sector spread is, whether the fleet and bank balance are
actually being put to work — so a player who has cleared every Economic
finding still has somewhere new to look. Distance dampening reuses
distances_from_player (asset-relative, same anchor as economy.py) rather than
distances_from_current: a new station or a trade run has a fixed origin
point, not the avatar's current position, same reasoning as advisors.py's
npc_demand_by_ware.
"""
from __future__ import annotations
from .advisors import _finding

# Trader rules scout further afield than the reactive economy rules (a siting
# or arbitrage tip 6 jumps out is still worth surfacing, just lower priority
# via the same distance dampening) — a separate, larger radius from
# advisors.ADVISOR_MAX_JUMPS, which gates "act on this now" opportunities.
TRADER_MAX_JUMPS = 8

# Reachable unmet NPC demand (summed depth, from the shared demand_by_ware
# lookup) at/above this is called out explicitly in a siting suggestion's
# body. Below it we still advise — low demand is not a veto, see below — we
# just don't claim a demand signal we can't back up.
DEMAND_NOTE_THRESHOLD = 50

# Reputation floor below which we don't advise building/trading in a faction's
# territory — mirrors ReputationEntry.can_trade / advisors.py's demand gate.
REPUTATION_BLOCK_THRESHOLD = -10

# A courier sitting on an unresolved delivery this long (in-game hours) is
# "stranded" for advisor purposes, not just between two normal hops.
STRANDED_HOURS_THRESHOLD = 2.0

# A player with this much banked and less than the ratio below actively
# trading is sitting on idle capital worth flagging.
IDLE_CREDITS_THRESHOLD = 5_000_000
TRADER_SHIP_RATIO_THRESHOLD = 0.2
TRADER_ROLES = ('Freighter', 'Transport')

# Coarse abundance ordering for whatever yield string the save recorded.
# resource.py's extractor keeps the highest-ranked tag it saw per sector; an
# unrecognised string (a save format we haven't seen) ranks mid-table rather
# than being penalised to the bottom.
YIELD_RANK = {
    'lowest': 0, 'lowminus': 1, 'verylow': 2, 'low': 3, 'lowplus': 4,
    'lowextra': 5, 'medlow': 6, 'medium': 7, 'medplus': 8, 'medhigh': 9,
    'highlow': 10, 'high': 11, 'highplus': 12, 'veryhigh': 13, 'highest': 14,
}
_DEFAULT_YIELD_RANK = 6
YIELD_LABEL = {
    'lowest': 'Lowest', 'lowminus': 'Low-Minus', 'verylow': 'Very Low',
    'low': 'Low', 'lowplus': 'Low-Plus', 'lowextra': 'Low-Extra',
    'medlow': 'Med-Low', 'medium': 'Medium', 'medplus': 'Med-Plus',
    'medhigh': 'Med-High', 'highlow': 'High-Low', 'high': 'High',
    'highplus': 'High-Plus', 'veryhigh': 'Very High', 'highest': 'Highest',
}

# 3 phrasings per finding type so the feed doesn't read as copy-pasted.
TEMPLATES: dict[str, list[str]] = {
    'station_siting': [
        "{sector_name} has a {yield_label} {ware_name} deposit with no player "
        "station drawing on it yet — consider building a {ware_name} "
        "extraction station there ({jumps} jump(s) from your nearest "
        "asset).{demand_note}",
        "Unclaimed opportunity: {sector_name}'s {yield_label} {ware_name} "
        "field sits untouched, {jumps} jump(s) out — a mining station there "
        "would put it to work.{demand_note}",
        "Consider staking a claim in {sector_name} — its {yield_label} "
        "{ware_name} deposit has no player presence nearby ({jumps} "
        "jump(s) away).{demand_note}",
    ],
    'galaxy_arbitrage': [
        "{ware_name} sells for {sell_price} Cr/unit at {sell_name} but "
        "{buy_name} pays {buy_price} Cr/unit — a {jumps}-jump run worth "
        "roughly {gain} Cr.",
        "Arbitrage run: buy {ware_name} at {sell_name} ({sell_price} Cr/unit), "
        "sell to {buy_name} ({buy_price} Cr/unit) — ~{gain} Cr over {jumps} "
        "jump(s).",
        "{buy_name} pays {buy_price} Cr for {ware_name} that {sell_name} "
        "sells at just {sell_price} Cr — worth ~{gain} Cr if you run it, "
        "{jumps} jump(s) total.",
    ],
    'stranded_delivery': [
        "{ship_name} has been holding a {ware_name} pickup from "
        "{from_station} for {hours}h with no delivery destination assigned "
        "— check its orders.",
        "{ship_name} picked up {ware_name} at {from_station} {hours}h ago "
        "and still has nowhere to deliver it — it's sitting idle mid-route.",
        "No destination set: {ship_name} has carried {ware_name} from "
        "{from_station} for {hours}h without a delivery order.",
    ],
    'idle_trade_capital': [
        "You're sitting on {credits} Cr with only {traders} of {total} ships "
        "({pct}%) doing any trading — consider building or buying more "
        "traders to put that capital to work.",
        "{credits} Cr in reserve and just {pct}% of your fleet ({traders}/"
        "{total}) is trading — more haulers would turn that idle capital "
        "into income.",
        "Idle capital: {credits} Cr banked while only {traders} of your "
        "{total} ships trade ({pct}%) — expand the trade fleet to make it "
        "earn.",
    ],
    'reputation_locked_trade': [
        "{faction_name} territory ({sector_name}, {jumps} jump(s) away) has "
        "{ware_name} worth trading, but your {tier} reputation blocks it — "
        "improving relations would unlock this route.",
        "A trade opportunity for {ware_name} sits {jumps} jump(s) away in "
        "{faction_name} space, currently out of reach at {tier} standing.",
        "{faction_name} ({tier}) controls a reachable {ware_name} trade — "
        "{jumps} jump(s) out — that your reputation currently locks you "
        "out of.",
    ],
}


# ── Rule 1: station siting (unclaimed resource, demand-aware) ───────────────

def station_siting_findings(conn, scan_id, distances_from_player, avg_prices,
                             demand_by_ware) -> list[dict]:
    """Sectors with a mineable resource but no player station anywhere in
    them yet. Always fires regardless of demand — low demand isn't a reason
    NOT to build, it just means the note below doesn't get to claim a strong
    market — but appends a demand call-out when reachable unmet demand for
    that ware is high (see DEMAND_NOTE_THRESHOLD)."""
    reputation = {r['faction_id']: r['value'] for r in conn.execute(
        "SELECT faction_id, value FROM reputation WHERE scan_id = ?", (scan_id,))}
    claimed = {r['sector_macro'] for r in conn.execute(
        "SELECT DISTINCT sector_macro FROM stations WHERE scan_id = ?", (scan_id,))}
    rows = conn.execute(
        "SELECT sr.sector_macro, sr.ware, sr.yield_level, sr.recharge_max, "
        "       sec.sector_name, sec.owner_id, "
        "       wm.name AS ware_name "
        "FROM sector_resources sr "
        "JOIN sectors sec ON sec.sector_macro = sr.sector_macro "
        "LEFT JOIN ware_metadata wm ON wm.ware_id = sr.ware "
        "WHERE sr.last_scan_id = ? AND sec.is_discovered = 1",
        (scan_id,))
    findings = []
    for r in rows:
        sector = r['sector_macro']
        if sector in claimed:
            continue
        owner = r['owner_id']
        if owner and reputation.get(owner, 0) < REPUTATION_BLOCK_THRESHOLD:
            continue  # too hostile to safely build here
        jumps = distances_from_player.get(sector)
        if jumps is None:
            continue
        ware = r['ware']
        demands = demand_by_ware.get(ware, [])
        depth_sum = sum(d['demand_depth'] for d in demands)
        avg_price = avg_prices.get(ware, 0)
        rank = YIELD_RANK.get(r['yield_level'], _DEFAULT_YIELD_RANK)
        # No extraction-rate figure exists for raw resources (sector_resources
        # only records reservoir capacity, not a flow rate) — richness (yield
        # rank) and reachable demand are the only signals available, so the
        # priority is a proxy rather than a Cr/hr estimate like economy.py's.
        priority = (rank + 1) * max(avg_price, 1) * (1 + depth_sum / 100.0) / (1 + jumps)
        if depth_sum >= DEMAND_NOTE_THRESHOLD:
            demand_note = (f" Demand nearby is already strong — "
                            f"{depth_sum:,.0f} units wanted across "
                            f"{len(demands)} reachable buyer(s).")
        else:
            demand_note = ''
        slots = {
            'sector_name': r['sector_name'] or sector,
            'ware_name':   r['ware_name'] or ware,
            'yield_label': YIELD_LABEL.get(r['yield_level'],
                                           (r['yield_level'] or 'Unknown').title()),
            'jumps':       jumps,
            'demand_note': demand_note,
        }
        evidence = {
            'sector_macro': sector, 'ware_id': ware,
            'yield_level': r['yield_level'], 'recharge_max': r['recharge_max'],
            'jumps': jumps, 'demand_depth': round(depth_sum), 'avg_price': avg_price,
        }
        findings.append(_finding(
            f"siting:{sector}:{ware}", 'trader', 'station_siting', priority,
            slots, evidence, TEMPLATES))
    return findings


# ── Rule 2: galaxy-wide arbitrage (NPC buy vs sell, not tied to player stock) ─

def galaxy_arbitrage_findings(conn, scan_id, distances_from_player) -> list[dict]:
    sells = conn.execute(
        "SELECT ns.object_id, ns.code, ns.name AS station_name, ns.sector_macro, "
        "       w.ware_id, w.ware_name, w.price, w.amount "
        "FROM npc_stations ns "
        "JOIN npc_station_wares w ON w.station_id = ns.object_id "
        "JOIN reputation r ON r.faction_id = ns.owner_id AND r.scan_id = ? "
        "WHERE w.is_selling = 1 AND w.price IS NOT NULL AND r.value >= ?",
        (scan_id, REPUTATION_BLOCK_THRESHOLD)).fetchall()
    buys = conn.execute(
        "SELECT ns.object_id, ns.code, ns.name AS station_name, ns.sector_macro, "
        "       w.ware_id, w.price, w.desired "
        "FROM npc_stations ns "
        "JOIN npc_station_wares w ON w.station_id = ns.object_id "
        "JOIN reputation r ON r.faction_id = ns.owner_id AND r.scan_id = ? "
        "WHERE w.is_buying = 1 AND w.price IS NOT NULL AND r.value >= ?",
        (scan_id, REPUTATION_BLOCK_THRESHOLD)).fetchall()

    def _reachable(rows):
        out: dict[str, list] = {}
        for r in rows:
            jumps = distances_from_player.get(r['sector_macro'])
            if jumps is None or jumps > TRADER_MAX_JUMPS:
                continue
            out.setdefault(r['ware_id'], []).append((r, jumps))
        return out

    sell_by_ware = _reachable(sells)
    buy_by_ware = _reachable(buys)

    findings = []
    for ware_id, sell_opts in sell_by_ware.items():
        buy_opts = buy_by_ware.get(ware_id)
        if not buy_opts:
            continue
        # Cheapest reachable seller / priciest reachable buyer, each dampened
        # by their own distance — same convention as economy.pricing_gap_findings.
        sell_row, sell_jumps = min(sell_opts, key=lambda t: t[0]['price'] * (1 + t[1]))
        buy_row, buy_jumps = max(buy_opts, key=lambda t: t[0]['price'] / (1 + t[1]))
        if buy_row['object_id'] == sell_row['object_id']:
            continue
        gap_cents = (buy_row['price'] or 0) - (sell_row['price'] or 0)
        if gap_cents <= 0:
            continue
        volume = min(sell_row['amount'] or 0, buy_row['desired'] or 0)
        if volume <= 0:
            continue
        gain = gap_cents / 100.0 * volume
        jumps_total = sell_jumps + buy_jumps
        priority = gain / (1 + jumps_total)
        slots = {
            'ware_name':  sell_row['ware_name'],
            'sell_name':  sell_row['station_name'] or sell_row['code'],
            'sell_price': round((sell_row['price'] or 0) / 100.0, 1),
            'buy_name':   buy_row['station_name'] or buy_row['code'],
            'buy_price':  round((buy_row['price'] or 0) / 100.0, 1),
            'jumps':      jumps_total,
            'gain':       round(gain),
        }
        evidence = {
            'ware_id': ware_id, 'sell_station_id': sell_row['object_id'],
            'buy_station_id': buy_row['object_id'], 'sell_jumps': sell_jumps,
            'buy_jumps': buy_jumps, 'volume': volume,
            'sell_price_cents': sell_row['price'], 'buy_price_cents': buy_row['price'],
        }
        findings.append(_finding(
            f"arbitrage:{sell_row['object_id']}:{buy_row['object_id']}:{ware_id}",
            'trader', 'galaxy_arbitrage', priority, slots, evidence, TEMPLATES))
    return findings


# ── Rule 3: stranded delivery (courier holding cargo with no destination) ───

def stranded_delivery_findings(conn, scan_id, avg_prices) -> list[dict]:
    rows = conn.execute(
        "SELECT ship_id, ship_code, ship_name, ware_id, ware_name, amount, "
        "       from_station_name, time_ago_s "
        "FROM in_progress_deliveries "
        "WHERE scan_id = ? AND dest_station_id IS NULL AND time_ago_s >= ?",
        (scan_id, STRANDED_HOURS_THRESHOLD * 3600))
    findings = []
    for r in rows:
        hours = (r['time_ago_s'] or 0) / 3600.0
        value_est = avg_prices.get(r['ware_id'], 0) * (r['amount'] or 0)
        # Both staleness and cargo value matter: a cheap ware stranded a long
        # time and an expensive ware stranded briefly can both be worth flagging.
        priority = hours * (1 + value_est / 1000.0)
        slots = {
            'ship_name':    r['ship_name'] or r['ship_code'],
            'ware_name':    r['ware_name'],
            'from_station': r['from_station_name'] or 'its last stop',
            'hours':        round(hours, 1),
        }
        evidence = {
            'ship_id': r['ship_id'], 'ware_id': r['ware_id'],
            'amount': r['amount'], 'time_ago_s': r['time_ago_s'],
            'value_estimate': round(value_est),
        }
        findings.append(_finding(
            f"stranded:{r['ship_id']}:{r['ware_id']}", 'trader', 'stranded_delivery',
            priority, slots, evidence, TEMPLATES))
    return findings


# ── Rule 4: idle trade capital (credits banked, fleet not trading) ─────────

def idle_trade_capital_findings(conn, scan_id) -> list[dict]:
    row = conn.execute(
        "SELECT player_credits FROM scans WHERE scan_id = ?", (scan_id,)).fetchone()
    credits = (row['player_credits'] or 0) if row else 0
    if credits < IDLE_CREDITS_THRESHOLD:
        return []
    total = conn.execute(
        "SELECT COUNT(*) AS n FROM ships WHERE scan_id = ?", (scan_id,)).fetchone()['n']
    if not total:
        return []
    traders = conn.execute(
        "SELECT COUNT(*) AS n FROM ships WHERE scan_id = ? AND role IN (?, ?)",
        (scan_id, *TRADER_ROLES)).fetchone()['n']
    ratio = traders / total
    if ratio >= TRADER_SHIP_RATIO_THRESHOLD:
        return []
    priority = (credits / 1000.0) * (1 - ratio)
    slots = {
        'credits': round(credits),
        'traders': traders,
        'total':   total,
        'pct':     round(ratio * 100),
    }
    evidence = {
        'player_credits': credits, 'trader_ships': traders,
        'total_ships': total, 'ratio': round(ratio, 3),
    }
    return [_finding(
        f"idlecapital:{scan_id}", 'trader', 'idle_trade_capital', priority,
        slots, evidence, TEMPLATES)]


# ── Rule 5: reputation-locked trade (blocked faction, best reachable ware) ──

def reputation_locked_trade_findings(conn, scan_id, distances_from_player) -> list[dict]:
    reputation = {r['faction_id']: (r['value'], r['tier']) for r in conn.execute(
        "SELECT faction_id, value, tier FROM reputation WHERE scan_id = ?", (scan_id,))}
    rows = conn.execute(
        "SELECT ns.owner_id, ns.owner_name, ns.sector_macro, ns.object_id, "
        "       ns.code, ns.name AS station_name, sec.sector_name, "
        "       w.ware_id, w.ware_name, w.price, w.amount, w.desired, w.is_selling "
        "FROM npc_stations ns "
        "JOIN npc_station_wares w ON w.station_id = ns.object_id "
        "LEFT JOIN sectors sec ON sec.sector_macro = ns.sector_macro "
        "WHERE w.price IS NOT NULL")
    best_by_faction: dict[str, dict] = {}
    for r in rows:
        owner = r['owner_id']
        rep = reputation.get(owner)
        if rep is None or rep[0] >= REPUTATION_BLOCK_THRESHOLD:
            continue
        jumps = distances_from_player.get(r['sector_macro'])
        if jumps is None or jumps > TRADER_MAX_JUMPS:
            continue
        volume = r['amount'] if r['is_selling'] else r['desired']
        value_est = (r['price'] or 0) / 100.0 * (volume or 0)
        if value_est <= 0:
            continue
        priority = value_est / (1 + jumps)
        cur = best_by_faction.get(owner)
        if cur is None or priority > cur['priority']:
            best_by_faction[owner] = {
                'priority': priority, 'row': r, 'jumps': jumps,
                'rep_value': rep[0], 'tier': rep[1],
            }
    findings = []
    for owner, best in best_by_faction.items():
        r = best['row']
        slots = {
            'faction_name': r['owner_name'] or owner,
            'sector_name':  r['sector_name'] or r['sector_macro'],
            'ware_name':    r['ware_name'],
            'jumps':        best['jumps'],
            'tier':         best['tier'] or 'Hostile',
        }
        evidence = {
            'faction_id': owner, 'reputation_value': best['rep_value'],
            'ware_id': r['ware_id'], 'station_id': r['object_id'],
            'jumps': best['jumps'],
        }
        findings.append(_finding(
            f"replocked:{owner}", 'trader', 'reputation_locked_trade',
            best['priority'], slots, evidence, TEMPLATES))
    return findings
