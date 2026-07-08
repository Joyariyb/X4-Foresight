"""Core role: Shared helpers for the advisor domain modules (economy.py, logistics.py, ...).

Pattern: snapshot -> metrics -> rules -> findings -> templates. Each domain
module's rule reads this scan's DB rows (pure read, same contract as
db/trends.py), scores what it finds, and renders one of a few canned
phrasings via _finding() so the feed doesn't read as copy-pasted. No LLM is
involved — an LLM would only ever be an optional renderer sitting on top of
these same findings.

Advice is PLAYER-RELATIVE, not galaxy-wide, and by faction reputation (can't
usefully trade with someone who'll shoot you). Economy rules (a hauler flying
station -> buyer) filter by distance from the player's STATIONS
(distances_from_player) — the goods have a fixed origin, so the avatar's
current position is irrelevant, and asset-relative reachability is what makes
"nearby" mean something once the empire has spread out. Military rules
instead need BOTH anchors: a threat sitting on a player station is a threat
whether or not the avatar is nearby, so distances_from_player alone already
answers the old "idle scout half the map away" objection (it's seeded ONLY
from station sectors) — but the avatar's own position can also be in danger,
so military merges distances_from_player with distances_from_current
(merge_anchors() below) rather than picking one.

This module holds only what's shared across domains. Domain-specific rules,
tuning constants, and templates live in their own files (economy.py,
logistics.py, ...) so a new domain (e.g. military) can be added without
touching the others.
"""
from __future__ import annotations
import zlib

# How far from the player's CURRENT sector an NPC station can be and still
# count as an actionable opportunity. Separate from jsonexport's
# NPC_TRADE_RANGE_MAX_JUMPS (asset-relative, a browse list) — this one gates
# what the advisor calls out as "worth your attention right now".
ADVISOR_MAX_JUMPS = 5


def _finding(id: str, domain: str, ftype: str, priority_score: float,
             slots: dict, evidence: dict, templates: dict[str, list[str]],
             counters: list[dict] | None = None) -> dict:
    """Render one finding using ``templates[ftype]``.

    Variant choice is a CRC32 of the finding's own id — deterministic (stable
    across runs, golden-testable) without the variety collapsing to "always
    variant 0". ``templates`` is passed in by the calling domain module (each
    domain owns its own phrasings) rather than looked up from a shared dict.

    ``counters`` is an optional [{threat, advice}] list rendered by the UI as
    a hover tooltip (military's counter-advice rows). The key is only present
    when a rule supplies it, so findings without one keep their exact shape.
    """
    variants = templates[ftype]
    variant = zlib.crc32(id.encode()) % len(variants)
    # Body text gets thousands separators (UI_STANDARDS §9 — full readable
    # numbers, never "168000 Cr/hr"); slots keeps raw values so consumers can
    # do maths without re-parsing formatted strings. bool is an int subclass,
    # so exclude it explicitly.
    display = {k: (f'{v:,}' if isinstance(v, int) and not isinstance(v, bool) else v)
               for k, v in slots.items()}
    out = {
        'id':             id,
        'domain':         domain,
        'type':           ftype,
        'priority_score': round(priority_score, 2),
        'body':           variants[variant].format(**display),
        'template_id':    ftype,
        'variant':        variant,
        'slots':          slots,
        'evidence':       evidence,
    }
    if counters is not None:
        out['counters'] = counters
    return out


# ── Shared lookups (used by more than one domain) ────────────────────────────

def ware_avg_prices(conn) -> dict[str, int]:
    """{ware_id: average price in credits} from the static wares.xml band."""
    return {r['ware_id']: r['price_avg'] for r in conn.execute(
        "SELECT ware_id, price_avg FROM ware_prices")}


def npc_demand_by_ware(conn, scan_id, distances_from_player,
                        max_jumps=ADVISOR_MAX_JUMPS) -> dict[str, list[dict]]:
    """{ware_id: [reachable NPC buy offers with genuine unmet demand]}.

    Demand depth is the buy offer's ``amount`` — how much the station still
    wants to buy right now. In an X4 save a buy offer carries ``desired`` (the
    total order size) and ``amount`` (the quantity left to fill); at rest the
    two are equal, and once a delivery is partway through ``amount`` is the
    unfilled remainder while ``desired - amount`` is the part already delivered.
    So ``amount`` IS the unmet demand — the old ``desired - amount`` was the
    inverse (verified against real saves: desired == amount on ~99% of standing
    offers, which collapsed this whole signal to zero). A zero-amount offer
    isn't an opportunity. Reputation gate mirrors ReputationEntry.can_trade
    (value >= -10); reachability is jumps from the NEAREST PLAYER STATION
    (distances_from_player), capped at max_jumps, same shape as
    jsonexport._npc_trade_partners.

    Station-relative, not avatar-relative: the hauler that would run this
    route starts from the surplus station, not from wherever the camera
    happens to be — so a mission deep in Xenon territory must not blank a
    trade opportunity next to a station that hasn't moved.
    """
    # buy_price/buy_amount are the station's OWN buy offer — aliased to
    # price/amount so the demand-depth logic below reads the same names it
    # always has. A co-located sell offer for this ware keeps its own
    # sell_price/sell_amount columns and can no longer clobber these.
    rows = conn.execute(
        "SELECT ns.object_id, ns.code, ns.name AS station_name, ns.sector_macro, "
        "       ns.owner_id, ns.owner_name, "
        "       w.ware_id, w.ware_name, w.buy_price AS price, "
        "       w.buy_amount AS amount, w.desired "
        "FROM npc_stations ns "
        "JOIN npc_station_wares w ON w.station_id = ns.object_id "
        "JOIN reputation r ON r.faction_id = ns.owner_id AND r.scan_id = ? "
        "WHERE w.is_buying = 1 AND w.buy_amount IS NOT NULL AND r.value >= -10",
        (scan_id,))
    out: dict[str, list[dict]] = {}
    for r in rows:
        jumps = distances_from_player.get(r['sector_macro'])
        if jumps is None or jumps > max_jumps:
            continue
        depth = r['amount'] or 0
        if depth <= 0:
            continue
        out.setdefault(r['ware_id'], []).append({
            'object_id':   r['object_id'], 'code': r['code'],
            'station_name': r['station_name'], 'jumps': jumps,
            'price': r['price'], 'amount': r['amount'], 'desired': r['desired'],
            'demand_depth': depth,
        })
    return out


def merge_anchors(distances_from_player, distances_from_current
                   ) -> tuple[dict[str, int], dict[str, str]]:
    """Merge the two galaxy_map anchors into one {sector: jumps} plus a
    parallel {sector: anchor} map recording which anchor produced that jump
    count ('station' | 'current' | 'both' on a tie, including 0 == 0 when the
    player is standing in a sector that also holds a station).

    Military threats matter near a player STATION (the asset stays put, so it
    is a threat regardless of where the avatar flies) AND near the avatar's
    CURRENT position (their own ship can also be caught out). Merging into
    one jumps dict — instead of running each rule twice, once per anchor, and
    concatenating — is what guarantees a rule fires at most once per sector:
    the MIN of the two distances is the only number that ever reaches the
    ADVISOR_MAX_JUMPS gate or the priority weighting, so there is only ever
    one candidate jump count per sector to begin with.
    """
    jumps: dict[str, int] = {}
    anchor: dict[str, str] = {}
    for sector in distances_from_player.keys() | distances_from_current.keys():
        p = distances_from_player.get(sector)
        c = distances_from_current.get(sector)
        if p is None:
            jumps[sector], anchor[sector] = c, 'current'
        elif c is None:
            jumps[sector], anchor[sector] = p, 'station'
        elif p < c:
            jumps[sector], anchor[sector] = p, 'station'
        elif c < p:
            jumps[sector], anchor[sector] = c, 'current'
        else:
            jumps[sector], anchor[sector] = p, 'both'
    return jumps, anchor
