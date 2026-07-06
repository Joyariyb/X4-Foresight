"""Core role: Shared helpers for the advisor domain modules (economy.py, logistics.py, ...).

Pattern: snapshot -> metrics -> rules -> findings -> templates. Each domain
module's rule reads this scan's DB rows (pure read, same contract as
db/trends.py), scores what it finds, and renders one of a few canned
phrasings via _finding() so the feed doesn't read as copy-pasted. No LLM is
involved — an LLM would only ever be an optional renderer sitting on top of
these same findings.

Advice is PLAYER-RELATIVE, not galaxy-wide: every rule that reaches toward an
NPC station filters by distance from the player's CURRENT sector (not asset
sectors — an idle scout half the map away is not "nearby" just because a
station is there) and by faction reputation (can't usefully trade with
someone who'll shoot you).

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


def npc_demand_by_ware(conn, scan_id, distances_from_current,
                        max_jumps=ADVISOR_MAX_JUMPS) -> dict[str, list[dict]]:
    """{ware_id: [reachable NPC buy offers with genuine unmet demand]}.

    "Genuine unmet demand" means desired > amount (there's room below the
    station's own target stock) — a fully-stocked buy offer isn't an
    opportunity even though is_buying=1. Reputation gate mirrors
    ReputationEntry.can_trade (value >= -10); reachability is jumps from the
    player's CURRENT location, capped at max_jumps, same shape as
    jsonexport._npc_trade_partners but asset-independent.
    """
    rows = conn.execute(
        "SELECT ns.object_id, ns.code, ns.name AS station_name, ns.sector_macro, "
        "       ns.owner_id, ns.owner_name, "
        "       w.ware_id, w.ware_name, w.price, w.amount, w.desired "
        "FROM npc_stations ns "
        "JOIN npc_station_wares w ON w.station_id = ns.object_id "
        "JOIN reputation r ON r.faction_id = ns.owner_id AND r.scan_id = ? "
        "WHERE w.is_buying = 1 AND w.desired IS NOT NULL AND r.value >= -10",
        (scan_id,))
    out: dict[str, list[dict]] = {}
    for r in rows:
        jumps = distances_from_current.get(r['sector_macro'])
        if jumps is None or jumps > max_jumps:
            continue
        depth = (r['desired'] or 0) - (r['amount'] or 0)
        if depth <= 0:
            continue
        out.setdefault(r['ware_id'], []).append({
            'object_id':   r['object_id'], 'code': r['code'],
            'station_name': r['station_name'], 'jumps': jumps,
            'price': r['price'], 'amount': r['amount'], 'desired': r['desired'],
            'demand_depth': depth,
        })
    return out
