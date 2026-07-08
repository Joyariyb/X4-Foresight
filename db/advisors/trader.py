"""Core role: Trader-domain advisor rules (station siting, arbitrage, stranded
deliveries, idle capital).

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
from scanner.galaxy_map import distances_from
from .advisors import _finding

# The arbitrage and reputation-locked rules scout further afield than the
# reactive economy rules (a tip 6 jumps out is still worth surfacing, just
# lower priority via the same distance dampening) — a separate, larger radius
# from advisors.ADVISOR_MAX_JUMPS, which gates "act on this now" opportunities.
TRADER_MAX_JUMPS = 8

# Siting caps tighter, on its own knob rather than reusing TRADER_MAX_JUMPS. A
# mining station is a permanent asset you have to defend and resupply, so a
# deposit far outside your footprint is a poor site however rich it is — unlike
# a one-off arbitrage run, distance here isn't a per-trip cost you can just net
# against the gain, so the wider scouting radius doesn't fit. 5 mirrors the
# in-game trader jump range a station's own haulers work within, keeping
# suggestions inside reach of the fleet that would actually service them.
SITING_MAX_JUMPS = 5

# How far a would-be station's output can profitably reach buyers. Distinct
# from SITING_MAX_JUMPS ("how far from me will I build") — this is "how far can
# the new station sell", measured from the CANDIDATE sector, not the player's
# assets. 5 matches a trader's jump range from its home station.
SITING_DEMAND_JUMPS = 5

# Reachable unmet NPC demand (summed buy_amount within SITING_DEMAND_JUMPS of
# the candidate sector) at/above this is called out explicitly in a siting
# suggestion's body. Below it we still advise — low demand is not a veto, see
# below — we just don't claim a demand signal we can't back up.
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

# Siting advises 'high' richness and above — a Med-High-or-lower deposit rarely
# earns back a permanent station. Kept beside the ranking it indexes into so
# the two move together if the tiers are ever renumbered.
SITING_YIELD_FLOOR = YIELD_RANK['high']
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
        "asset).{demand_note}{also_note}",
        "Unclaimed opportunity: {sector_name}'s {yield_label} {ware_name} "
        "field sits untouched, {jumps} jump(s) out — a mining station there "
        "would put it to work.{demand_note}{also_note}",
        "Consider staking a claim in {sector_name} — its {yield_label} "
        "{ware_name} deposit has no player presence nearby ({jumps} "
        "jump(s) away).{demand_note}{also_note}",
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
}


# ── Rule 1: station siting (unclaimed resource, demand-aware) ───────────────

def station_siting_findings(conn, scan_id, distances_from_player, avg_prices) -> list[dict]:
    """Sectors within SITING_MAX_JUMPS that hold a mineable resource but no
    player station yet. Always fires regardless of demand — low demand isn't a reason
    NOT to build, it just means the note below doesn't get to claim a strong
    market — but appends a demand call-out when unmet NPC demand for that ware,
    reachable within SITING_DEMAND_JUMPS of the CANDIDATE sector, is high (see
    DEMAND_NOTE_THRESHOLD).

    Demand is centred on the candidate sector, not the player's assets: a new
    station sells what it extracts to buyers near IT, so two unclaimed Ore
    sectors get different demand notes depending on which buyers each can reach
    — not one galaxy-wide total pasted onto every card.

    One finding per SECTOR, not per deposit: a resource-rich sector is a single
    place to build, so it's headlined by its best-priority ware and the other
    qualifying deposits are folded into an "also rich in" mention rather than
    spamming the feed with a near-identical card per ware."""
    reputation = {r['faction_id']: r['value'] for r in conn.execute(
        "SELECT faction_id, value FROM reputation WHERE scan_id = ?", (scan_id,))}
    claimed = {r['sector_macro'] for r in conn.execute(
        "SELECT DISTINCT sector_macro FROM stations WHERE scan_id = ?", (scan_id,))}

    # Sector-centred demand: the galaxy jump graph (persisted in sector_links)
    # plus every reachable-faction NPC buy offer, grouped ware→sector→amount. A
    # 0-1 BFS from each candidate then sums the buy_amount of buyers within
    # SITING_DEMAND_JUMPS. buy_amount (not desired) is the unmet demand — see
    # advisors.npc_demand_by_ware.
    graph: dict[str, list[tuple[str, int]]] = {}
    for a, b, cost in conn.execute(
            "SELECT sector_a, sector_b, cost FROM sector_links WHERE last_scan_id = ?",
            (scan_id,)):
        graph.setdefault(a, []).append((b, cost))
        graph.setdefault(b, []).append((a, cost))
    demand_ws: dict[str, dict[str, list[int]]] = {}
    for r in conn.execute(
            "SELECT ns.sector_macro, w.ware_id, w.buy_amount "
            "FROM npc_stations ns "
            "JOIN npc_station_wares w ON w.station_id = ns.object_id "
            "JOIN reputation rep ON rep.faction_id = ns.owner_id AND rep.scan_id = ? "
            "WHERE w.is_buying = 1 AND w.buy_amount > 0 AND rep.value >= ?",
            (scan_id, REPUTATION_BLOCK_THRESHOLD)):
        demand_ws.setdefault(r['ware_id'], {}).setdefault(
            r['sector_macro'], []).append(r['buy_amount'])

    reach_cache: dict[str, set[str]] = {}

    def _sector_demand(sector: str, ware: str) -> tuple[int, int]:
        """(total unmet demand, buyer count) for `ware` within
        SITING_DEMAND_JUMPS of `sector` — 0-1 BFS, cached per sector. The
        candidate sector itself always counts (its own buyers, 0 jumps)."""
        by_sector = demand_ws.get(ware)
        if not by_sector:
            return 0, 0
        reach = reach_cache.get(sector)
        if reach is None:
            reach = reach_cache[sector] = (
                set(distances_from(graph, sector, SITING_DEMAND_JUMPS)) | {sector})
        total = buyers = 0
        for s in reach:
            amts = by_sector.get(s)
            if amts:
                total += sum(amts)
                buyers += len(amts)
        return total, buyers

    rows = conn.execute(
        "SELECT sr.sector_macro, sr.ware, sr.yield_level, sr.recharge_max, "
        "       sec.sector_name, sec.owner_id, "
        "       wm.name AS ware_name "
        "FROM sector_resources sr "
        "JOIN sectors sec ON sec.sector_macro = sr.sector_macro "
        "LEFT JOIN ware_metadata wm ON wm.ware_id = sr.ware "
        "WHERE sr.last_scan_id = ? AND sec.is_discovered = 1",
        (scan_id,))
    # Accumulate qualifying deposits per sector, then emit once. best_by_sector
    # keeps the highest-priority candidate as the headline; the demoted ones
    # feed the "also rich in" mention.
    best_by_sector: dict[str, dict] = {}
    for r in rows:
        sector = r['sector_macro']
        if sector in claimed:
            continue
        owner = r['owner_id']
        if owner and reputation.get(owner, 0) < REPUTATION_BLOCK_THRESHOLD:
            continue  # too hostile to safely build here
        jumps = distances_from_player.get(sector)
        if jumps is None or jumps > SITING_MAX_JUMPS:
            continue  # unreachable, or beyond the siting radius (see above)
        # A permanent station only pays off on a genuinely rich deposit, so we
        # advise 'high' yield and up. A *known* yield below the floor is a
        # confident skip; an unrecognised string keeps the benefit of the doubt
        # (see _DEFAULT_YIELD_RANK) rather than being dropped for a save format
        # we couldn't read.
        rank = YIELD_RANK.get(r['yield_level'], _DEFAULT_YIELD_RANK)
        if r['yield_level'] in YIELD_RANK and rank < SITING_YIELD_FLOOR:
            continue
        ware = r['ware']
        depth_sum, n_buyers = _sector_demand(sector, ware)
        avg_price = avg_prices.get(ware, 0)
        # No extraction-rate figure exists for raw resources (sector_resources
        # only records reservoir capacity, not a flow rate) — richness (yield
        # rank) and reachable demand are the only signals available, so the
        # priority is a proxy rather than a Cr/hr estimate like economy.py's.
        priority = (rank + 1) * max(avg_price, 1) * (1 + depth_sum / 100.0) / (1 + jumps)
        cand = {
            'ware': ware, 'ware_name': r['ware_name'] or ware, 'rank': rank,
            'yield_level': r['yield_level'], 'yield_label': YIELD_LABEL.get(
                r['yield_level'], (r['yield_level'] or 'Unknown').title()),
            'priority': priority, 'depth_sum': depth_sum, 'n_buyers': n_buyers,
            'avg_price': avg_price, 'recharge_max': r['recharge_max'],
            'jumps': jumps, 'sector_name': r['sector_name'] or sector,
        }
        entry = best_by_sector.get(sector)
        if entry is None:
            best_by_sector[sector] = {'best': cand, 'others': []}
        elif priority > entry['best']['priority']:
            entry['others'].append(entry['best'])   # demote the old headline
            entry['best'] = cand
        else:
            entry['others'].append(cand)

    findings = []
    for sector, entry in best_by_sector.items():
        best = entry['best']
        # Richest-first so the mention reads best deposit → worst.
        others = sorted(entry['others'], key=lambda c: -c['rank'])
        if best['depth_sum'] >= DEMAND_NOTE_THRESHOLD:
            demand_note = (f" Demand nearby is already strong — "
                            f"{best['depth_sum']:,.0f} units wanted across "
                            f"{best['n_buyers']} reachable buyer(s).")
        else:
            demand_note = ''
        if others:
            listed = ', '.join(f"{c['yield_label']} {c['ware_name']}" for c in others)
            also_note = f" This sector is also rich in {listed}."
        else:
            also_note = ''
        slots = {
            'sector_name': best['sector_name'],
            'ware_name':   best['ware_name'],
            'yield_label': best['yield_label'],
            'jumps':       best['jumps'],
            'demand_note': demand_note,
            'also_note':   also_note,
        }
        evidence = {
            'sector_macro': sector, 'ware_id': best['ware'],
            'yield_level': best['yield_level'], 'recharge_max': best['recharge_max'],
            'jumps': best['jumps'], 'demand_depth': round(best['depth_sum']),
            'avg_price': best['avg_price'],
            'other_wares': [c['ware'] for c in others],
        }
        findings.append(_finding(
            f"siting:{sector}", 'trader', 'station_siting', best['priority'],
            slots, evidence, TEMPLATES))
    return findings


# ── Rule 2: galaxy-wide arbitrage (NPC buy vs sell, not tied to player stock) ─

def galaxy_arbitrage_findings(conn, scan_id, distances_from_player) -> list[dict]:
    # Each side reads its own direction's price/amount pair (aliased to the
    # generic names the pairing logic below uses). A station that both buys and
    # sells this ware now surfaces on BOTH sides with the correct figures for
    # each, instead of one merged row whose single price/amount was whichever
    # offer parsed last.
    sells = conn.execute(
        "SELECT ns.object_id, ns.code, ns.name AS station_name, ns.sector_macro, "
        "       w.ware_id, w.ware_name, w.sell_price AS price, w.sell_amount AS amount "
        "FROM npc_stations ns "
        "JOIN npc_station_wares w ON w.station_id = ns.object_id "
        "JOIN reputation r ON r.faction_id = ns.owner_id AND r.scan_id = ? "
        "WHERE w.is_selling = 1 AND w.sell_price IS NOT NULL AND r.value >= ?",
        (scan_id, REPUTATION_BLOCK_THRESHOLD)).fetchall()
    buys = conn.execute(
        "SELECT ns.object_id, ns.code, ns.name AS station_name, ns.sector_macro, "
        "       w.ware_id, w.buy_price AS price, w.buy_amount AS amount "
        "FROM npc_stations ns "
        "JOIN npc_station_wares w ON w.station_id = ns.object_id "
        "JOIN reputation r ON r.faction_id = ns.owner_id AND r.scan_id = ? "
        "WHERE w.is_buying = 1 AND w.buy_price IS NOT NULL AND r.value >= ?",
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
        # A one-time run moves min(what the seller has in stock, what the buyer
        # still wants). The buyer's want is its offer `amount` (unfilled
        # remainder), not `desired` (the full order size) — see
        # advisors.npc_demand_by_ware.
        volume = min(sell_row['amount'] or 0, buy_row['amount'] or 0)
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
