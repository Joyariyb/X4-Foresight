"""Core role: Cross-scan empire-trajectory reader (entry point: compute_trends()).

Foresight's DB keeps one snapshot row per entity per scan (the HISTORY storage
class in schema.sql) plus a deduped trade ledger. Every other export builder reads
a SINGLE scan; this module is the first that reads ACROSS scans to show how the
empire moved over time.

Pure DB read — same contract as the export/jsonexport.py builders (conn in, dict
out, no writes). v1 derives everything on the fly from existing tables, so there is
no schema change and no new persistence: see plan-the-trends-engine for the
deferred `scan_summary` materialization that would make this cheaper if the
per-export recompute ever becomes a cost.
"""
from __future__ import annotations
import sqlite3

from data.ship_stats import SHIP_STATS
from data.equipment_stats import EQUIPMENT_STATS, EQUIPMENT_ALIASES
from scanner.ship_names import resolve_ship_type


# Role → bucket classifier for the fleet-composition series. This mirrors the
# bucketing in export/jsonexport.py::_fleet_by_station (the source of truth); kept
# as a tiny local copy rather than refactoring that function's signature, but if the
# role taxonomy ever changes, change it in BOTH places (or unify them then).
def _role_bucket(role: str | None) -> str:
    role = role or ''
    if role in ('Freighter', 'Transport'):
        return 'traders'
    if role.startswith('Miner'):
        return 'miners'
    if any(role.startswith(r) for r in ('Fighter', 'Heavy Fighter', 'Corvette',
                                        'Frigate', 'Destroyer', 'Carrier', 'Bomber')):
        return 'combat'
    return 'other'


def _ship_asset_value(conn, scan_id) -> tuple[dict[int, float], dict[int, float]]:
    """Per-scan estimated resale value of the player FLEET, split into hull and
    fitted-equipment totals (returned as two {scan_id: credits} dicts).

    Prices come from the same static catalogs the export layer uses:
    SHIP_STATS[macro].price for hulls, EQUIPMENT_STATS[...].price × count for fitted
    gear (resolving macro aliases first). Unpriced macros contribute 0 rather than
    raising. Station STRUCTURE value is deliberately absent — STATION_STATS carries
    no price field, so stations enter net worth only via their account cash.
    """
    hull: dict[int, float] = {}
    for r in conn.execute("SELECT scan_id, macro FROM ships WHERE scan_id <= ?", (scan_id,)):
        price = (SHIP_STATS.get(r['macro'] or '', {}) or {}).get('price') or 0
        hull[r['scan_id']] = hull.get(r['scan_id'], 0) + price

    equip: dict[int, float] = {}
    for r in conn.execute("SELECT scan_id, macro, count FROM ship_equipment WHERE scan_id <= ?",
                          (scan_id,)):
        macro = r['macro'] or ''
        stat = EQUIPMENT_STATS.get(macro) or EQUIPMENT_STATS.get(EQUIPMENT_ALIASES.get(macro, ''), {})
        price = (stat.get('price') or 0) * (r['count'] or 1)
        equip[r['scan_id']] = equip.get(r['scan_id'], 0) + price
    return hull, equip


def _fleet_by_role(conn, scan_id) -> dict[int, dict[str, int]]:
    """Per-scan {scan_id: {traders, miners, combat, other}} player-fleet counts."""
    out: dict[int, dict[str, int]] = {}
    for r in conn.execute(
        "SELECT scan_id, role, COUNT(*) AS n FROM ships WHERE scan_id <= ? "
        "GROUP BY scan_id, role", (scan_id,)):
        bucket = out.setdefault(r['scan_id'], {'traders': 0, 'miners': 0, 'combat': 0, 'other': 0})
        bucket[_role_bucket(r['role'])] += r['n']
    return out


def _ships_lost_per_scan(conn, scan_ids) -> dict[int, int]:
    """{scan_id: count of player ships lost IN that scan's interval} (not cumulative).

    A loss is a ship `code` present in the previous scan and gone in this one — the
    exact roster diff compute_changes uses for ship_lost events. Each scan reports
    only its own interval's losses so the chart shows per-scan activity, not a
    running total. The first scan is the baseline (0 — no predecessor to diff)."""
    out: dict[int, int] = {}
    prev_codes: set[str] | None = None
    for sid in scan_ids:
        cur_codes = set(_ships_by_code(conn, sid).keys())
        out[sid] = 0 if prev_codes is None else len(prev_codes - cur_codes)
        prev_codes = cur_codes
    return out


def _per_scan_delta(cum: dict[int, int], scan_ids) -> list[int | None]:
    """Turn a cumulative {scan_id: total} into a per-scan-interval delta list,
    index-aligned to scan_ids.

    Each entry is this scan's total minus the previous scan's, so the chart plots
    what happened IN each interval rather than a climbing running total. The first
    scan has no predecessor → 0. A scan with no stored total (None — taken before
    the counter was tracked) yields None so the chart shows a gap, and the next real
    value also can't form a delta (None) rather than reading the whole backlog as a
    single spike."""
    out: list[int | None] = []
    prev: int | None = None
    for idx, sid in enumerate(scan_ids):
        v = cum.get(sid)
        if idx == 0:
            out.append(0 if v is not None else None)
        elif v is None or prev is None:
            out.append(None)
        else:
            out.append(max(0, v - prev))
        prev = v
    return out


def _kills_by_faction_by_scan(conn, scan_id, scan_ids) -> list[list[dict]]:
    """Per-scan faction kill breakdown, index-aligned to the `scans` axis.

    Each element is that scan's list of {faction_id, faction_name, kills} (cumulative
    counts), strongest first. Drives the Trends hover: the UI diffs a scan against its
    predecessor here (and against the reputation series) to show kills-since-last-scan
    and the matching reputation move per faction."""
    by_scan: dict[int, list[dict]] = {}
    for r in conn.execute(
            "SELECT scan_id, faction_id, faction_name, kills FROM combat_kills "
            "WHERE scan_id <= ? ORDER BY scan_id", (scan_id,)):
        by_scan.setdefault(r['scan_id'], []).append(
            {'faction_id': r['faction_id'], 'faction_name': r['faction_name'],
             'kills': r['kills']})
    return [sorted(by_scan.get(sid, []), key=lambda k: -k['kills']) for sid in scan_ids]


def _net_worth_by_scan(conn, scan_id) -> dict[int, float]:
    """{scan_id: net_worth} for every scan up to scan_id — the same definition the
    series uses (credits + station cash + fleet hull + fleet equipment). Used by the
    milestone detector in compute_changes; kept as one helper so the headline number
    and the milestone thresholds can never drift apart."""
    credits = {r['scan_id']: r['player_credits'] for r in conn.execute(
        "SELECT scan_id, player_credits FROM scans WHERE scan_id <= ?", (scan_id,))}
    cash = {r['scan_id']: r['c'] for r in conn.execute(
        "SELECT scan_id, COALESCE(SUM(account_amount), 0) AS c "
        "FROM stations WHERE scan_id <= ? GROUP BY scan_id", (scan_id,))}
    hull, equip = _ship_asset_value(conn, scan_id)
    return {sid: (credits.get(sid) or 0) + cash.get(sid, 0)
                 + hull.get(sid, 0) + equip.get(sid, 0)
            for sid in credits}


def _reputation_series(conn, scan_id, scan_ids) -> list[dict]:
    """Per-faction reputation value across every scan — the multi-line chart source.

    Returns one entry per faction that appears in any scan up to ``scan_id``:
    ``{faction_id, faction_name, tier, latest, values[]}``. Each ``values`` array is
    index-aligned to the shared ``scans`` axis, with ``None`` for scans where that
    faction has no row — so a gap stays a gap on the chart rather than reading as a
    plunge to zero (reputation legitimately sits anywhere on -30..+30, so 0 is a real
    value, not "missing").

    Ordered by latest known value descending, the same strongest-standing-first order
    the single-scan _reputation() builder uses, so the legend leads with the factions
    that matter most. faction_name/tier are the most RECENT known labels (rows are read
    oldest→newest, so the last write wins).
    """
    by_faction: dict[str, dict[int, float]] = {}
    name: dict[str, str] = {}
    tier: dict[str, str] = {}
    for r in conn.execute(
            "SELECT scan_id, faction_id, faction_name, value, tier "
            "FROM reputation WHERE scan_id <= ? ORDER BY scan_id", (scan_id,)):
        fid = r['faction_id']
        by_faction.setdefault(fid, {})[r['scan_id']] = r['value']
        name[fid] = r['faction_name']
        tier[fid] = r['tier']

    out: list[dict] = []
    for fid, vals in by_faction.items():
        series = [vals.get(sid) for sid in scan_ids]
        # Latest non-null value drives both the ordering and the legend headline.
        latest = next((v for v in reversed(series) if v is not None), None)
        out.append({'faction_id': fid, 'faction_name': name[fid],
                    'tier': tier[fid], 'latest': latest, 'values': series})
    # Strongest standing first; factions with no known value sink to the bottom.
    out.sort(key=lambda f: (f['latest'] is None, -(f['latest'] or 0)))
    return out


def _trade_windows(conn, game_time: float | None) -> dict:
    """All-time cumulative trade totals across the three ledger tables.

    Bounded by `game_time` (the selected scan's in-game clock) so that viewing an
    OLDER scan doesn't fold in trades that, in game time, hadn't happened yet — the
    same truncation principle the series uses. Sits on the ledgers' ix_*_time indexes.

    A note on "profit": the ledger stores each trade's `total_cr` (price × amount),
    not a per-trade margin, so the honest figure is *value moved*. For player
    station trades we additionally split by direction, so `net_cr` (sold − bought) is
    the closest real profit proxy we can offer; mining/internal carry value+volume
    only. The single 'all-time' bucket lives in a LIST so shorter game-hour windows
    can be appended later without reshaping consumers.
    """
    gt = game_time if game_time is not None else float('inf')
    st = conn.execute(
        "SELECT COALESCE(SUM(total_cr), 0) AS value, COALESCE(SUM(amount), 0) AS vol, "
        "       COUNT(*) AS n, "
        "       COALESCE(SUM(CASE WHEN direction='Out' THEN total_cr ELSE 0 END), 0) AS sold, "
        "       COALESCE(SUM(CASE WHEN direction='In'  THEN total_cr ELSE 0 END), 0) AS bought "
        "FROM trade_history WHERE game_time_s <= ?", (gt,)).fetchone()
    mn = conn.execute(
        "SELECT COALESCE(SUM(total_cr), 0) AS value, COALESCE(SUM(amount), 0) AS vol, "
        "COUNT(*) AS n FROM trade_history_mining WHERE game_time_s <= ?", (gt,)).fetchone()
    it = conn.execute(
        "SELECT COALESCE(SUM(total_cr), 0) AS value, COALESCE(SUM(amount), 0) AS vol, "
        "COUNT(*) AS n FROM trade_history_internal WHERE game_time_s <= ?", (gt,)).fetchone()
    return {
        'basis': 'game_time_s',
        'buckets': [{
            'label': 'all-time',
            'game_hours': None,
            'station_trades': {
                'value_cr': st['value'], 'volume_units': st['vol'], 'trades': st['n'],
                'sold_cr': st['sold'], 'bought_cr': st['bought'],
                'net_cr': st['sold'] - st['bought'],
            },
            'mining_deliveries': {
                'value_cr': mn['value'], 'volume_units': mn['vol'], 'trades': mn['n']},
            'internal_transfers': {
                'value_cr': it['value'], 'volume_units': it['vol'], 'trades': it['n']},
        }],
    }


# Net-worth milestones fire when the headline number first crosses one of these
# boundaries UPWARD between two scans (powers of ten: 10M, 100M, 1B, …). A single
# big jump can cross several at once → one event per boundary crossed.
_NET_WORTH_MILESTONES = [10 ** e for e in range(7, 13)]   # 1e7 … 1e12


def compute_trends(conn: sqlite3.Connection, scan_id: int | None = None) -> dict:
    """Empire trajectory across every scan up to and including ``scan_id``.

    Returns ``{'series': {...}}`` — an x-axis (`scans`) plus one parallel y-array
    per metric, all the same length and index-aligned to the axis. Parallel arrays
    (rather than a list of per-scan objects) let the UI bind each metric to the
    shared axis without reshaping, and adding a metric later is just one more array.

    ``scan_id`` defaults to the latest scan, mirroring to_export(): viewing an older
    scan shows the trajectory only up to that point, not the future the player
    hadn't reached yet.
    """
    if scan_id is None:
        row = conn.execute("SELECT MAX(scan_id) AS m FROM scans").fetchone()
        scan_id = row['m']
    if scan_id is None:
        raise ValueError("no scans in database to compute trends")

    # The x-axis: every scan up to the selected one, oldest → newest. Each metric
    # array below is built into a {scan_id: value} dict and then read back in this
    # order, so a scan that happens to have no rows in a child table still lines up
    # (it gets the default value rather than shifting later points left).
    axis = conn.execute(
        "SELECT scan_id, scanned_at, game_time_s FROM scans "
        "WHERE scan_id <= ? ORDER BY scan_id",
        (scan_id,),
    ).fetchall()
    scan_ids = [r['scan_id'] for r in axis]

    credits       = {r['scan_id']: r['player_credits'] for r in conn.execute(
        "SELECT scan_id, player_credits FROM scans WHERE scan_id <= ?", (scan_id,))}
    # COALESCE the SUM: account_amount can be NULL per station, and SUM over an
    # all-NULL (or empty) group returns NULL — we want 0 credits, not a gap.
    station_cash  = {r['scan_id']: r['cash'] for r in conn.execute(
        "SELECT scan_id, COALESCE(SUM(account_amount), 0) AS cash "
        "FROM stations WHERE scan_id <= ? GROUP BY scan_id", (scan_id,))}
    # The `ships` table holds only player-owned ships (NPC ships live in npc_ships),
    # so a plain COUNT is the fleet size — same basis as jsonexport._fleet_summary.
    ship_count    = {r['scan_id']: r['n'] for r in conn.execute(
        "SELECT scan_id, COUNT(*) AS n FROM ships WHERE scan_id <= ? GROUP BY scan_id",
        (scan_id,))}
    station_count = {r['scan_id']: r['n'] for r in conn.execute(
        "SELECT scan_id, COUNT(*) AS n FROM stations WHERE scan_id <= ? GROUP BY scan_id",
        (scan_id,))}
    # Lifetime enemy-kill counter off the scans row (cumulative in-game). Converted
    # to a per-scan delta below so the chart shows kills made IN each interval, not a
    # climbing total. None on scans taken before tracking → gap (see _per_scan_delta).
    ships_destroyed_cum = {r['scan_id']: r['ships_destroyed'] for r in conn.execute(
        "SELECT scan_id, ships_destroyed FROM scans WHERE scan_id <= ?", (scan_id,))}
    # Player ship losses per scan interval, derived from the roster diff (no counter).
    ships_lost = _ships_lost_per_scan(conn, scan_ids)

    # Full net worth = liquid credits + station account cash + fleet asset value
    # (hull + fitted equipment). See _ship_asset_value for the station-structure
    # caveat. Components are exposed as their own arrays below so the headline
    # net_worth number is fully inspectable (and the UI can stack them).
    hull_val, equip_val = _ship_asset_value(conn, scan_id)
    fleet_roles = _fleet_by_role(conn, scan_id)
    rep_series  = _reputation_series(conn, scan_id, scan_ids)
    kills_series = _kills_by_faction_by_scan(conn, scan_id, scan_ids)
    # axis is ordered oldest→newest, so its last row is the scan being viewed; bound
    # the trade windows to that scan's in-game clock.
    sel_game_time = axis[-1]['game_time_s'] if axis else None

    return {
        'windows': _trade_windows(conn, sel_game_time),
        'series': {
            'scans': [
                {'scan_id': r['scan_id'], 'scanned_at': r['scanned_at'],
                 'game_time_s': r['game_time_s']}
                for r in axis
            ],
            # GROUP BY only emits a row for scans that have ≥1 child row, so map back
            # over the full axis with a default for the silent (e.g. station-less)
            # scans — keeps every array exactly len(scan_ids).
            'credits':       [credits.get(sid)          for sid in scan_ids],
            'station_cash':  [station_cash.get(sid, 0)  for sid in scan_ids],
            'ship_count':    [ship_count.get(sid, 0)    for sid in scan_ids],
            'station_count': [station_count.get(sid, 0) for sid in scan_ids],
            # Combat: enemy kills (stat) and own-ship losses (roster diff), both
            # PER-SCAN (interval activity, not a running total). kills_by_faction
            # carries the per-scan hover breakdown (stored cumulative; the UI diffs it).
            'ships_destroyed': _per_scan_delta(ships_destroyed_cum, scan_ids),
            'ships_lost':      [ships_lost.get(sid, 0) for sid in scan_ids],
            'kills_by_faction': kills_series,
            # Net-worth components (kept separate for transparency) and the total.
            'ship_hull_value':  [hull_val.get(sid, 0)  for sid in scan_ids],
            'ship_equip_value': [equip_val.get(sid, 0) for sid in scan_ids],
            'net_worth': [
                (credits.get(sid) or 0) + station_cash.get(sid, 0)
                + hull_val.get(sid, 0) + equip_val.get(sid, 0)
                for sid in scan_ids
            ],
            # Fleet composition over time — one parallel array per role bucket.
            'fleet_by_role': {
                role: [fleet_roles.get(sid, {}).get(role, 0) for sid in scan_ids]
                for role in ('traders', 'miners', 'combat', 'other')
            },
            # Faction reputation over time — a list of per-faction entries, each with
            # its own `values` array index-aligned to `scans` (see _reputation_series).
            'reputation': rep_series,
        },
    }


# ── changes[] event feed ───────────────────────────────────────────────────────
# Each event is "detected at" the scan where it first shows up — i.e. comparing a
# scan to its immediate predecessor. The FIRST scan has no predecessor, so its
# entities are the baseline and never produce events (otherwise the very first scan
# would spuriously report the entire empire as "gained"). A single-scan DB → [].

def _stations_by_code(conn, scan_id) -> dict[str, dict]:
    """Player stations at one scan, keyed by `code`, with the sector name resolved from
    the reference `sectors` table for human-readable events.

    Keyed by `code` (the persistent "ABC-123" tag), NOT object_id: object_id is the hex
    component id X4 reassigns on every save, so it never matches across two scans and
    would make the whole fleet churn as lost/re-acquired. `code` is stable across saves
    and unique within a scan. Rows without a code are skipped so a code-less entity can't
    reintroduce that churn by always failing to match."""
    return {r['code']: dict(r) for r in conn.execute(
        "SELECT s.object_id, s.code, s.name, s.sector_macro, sec.sector_name "
        "FROM stations s "
        "LEFT JOIN sectors sec ON sec.sector_macro = s.sector_macro "
        "WHERE s.scan_id = ? AND s.code IS NOT NULL AND s.code != ''",
        (scan_id,))}


def _ships_by_code(conn, scan_id) -> dict[str, dict]:
    """Player ships at one scan, keyed by `code`. The `ships` table is the full player
    fleet (NPC ships live elsewhere), so diffing it is safe.

    Keyed by `code`, NOT object_id — see _stations_by_code for why: object_id is a
    per-save runtime id that can't join entities across scans; `code` is the persistent,
    scan-stable tag. Code-less rows are skipped."""
    return {r['code']: dict(r) for r in conn.execute(
        "SELECT object_id, code, name, macro, ship_class, size, role "
        "FROM ships WHERE scan_id = ? AND code IS NOT NULL AND code != ''",
        (scan_id,))}


def _reputation_by_faction(conn, scan_id) -> dict[str, dict]:
    """Faction reputation at one scan, keyed by faction_id."""
    return {r['faction_id']: dict(r) for r in conn.execute(
        "SELECT faction_id, faction_name, value, tier "
        "FROM reputation WHERE scan_id = ?",
        (scan_id,))}


def compute_changes(conn: sqlite3.Connection, scan_id: int | None = None) -> list[dict]:
    """The empire-event feed: notable changes between consecutive scans, newest
    first. v1 covers structural station changes (built / lost) and reputation tier
    crossings; ships and milestones arrive in later phases.

    Every event carries the detecting scan's `scan_id`, `game_time_s` AND
    `scanned_at` so the UI can show both an in-game age and a real-world age without
    re-querying — the same dual-clock idea the trade ledger uses.
    """
    if scan_id is None:
        row = conn.execute("SELECT MAX(scan_id) AS m FROM scans").fetchone()
        scan_id = row['m']
    if scan_id is None:
        raise ValueError("no scans in database to compute changes")

    scans = conn.execute(
        "SELECT scan_id, scanned_at, game_time_s FROM scans "
        "WHERE scan_id <= ? ORDER BY scan_id",
        (scan_id,),
    ).fetchall()

    # Net worth per scan, computed once up front, so milestone crossings below are a
    # cheap dict lookup per pair rather than a re-query.
    nw = _net_worth_by_scan(conn, scan_id)

    changes: list[dict] = []
    # Walk adjacent (prev, cur) pairs. zip(scans, scans[1:]) yields no pairs for a
    # single-scan DB, which is exactly the "baseline only, no events" behaviour.
    for prev, cur in zip(scans, scans[1:]):
        # The stamp every event from this pair shares — when it was first seen.
        at = {'scan_id': cur['scan_id'], 'game_time_s': cur['game_time_s'],
              'scanned_at': cur['scanned_at']}

        # ── stations built / lost ──────────────────────────────────────────────
        # Set-diff on object_id. The `stations` table is the complete set of PLAYER
        # stations each scan, so an id vanishing genuinely means built-out/destroyed,
        # not "fell out of a sampled subset" (the reason npc_ships is NOT diffed).
        # Keyed by `code` — set-diffing on the persistent tag, not the per-save object_id
        # (which would report the whole fleet as built/lost every scan). The event's
        # object_id comes from the row's real value for last-known reference.
        prev_st = _stations_by_code(conn, prev['scan_id'])
        cur_st  = _stations_by_code(conn, cur['scan_id'])
        for code in cur_st.keys() - prev_st.keys():
            st = cur_st[code]
            changes.append({'type': 'station_built', **at,
                            'object_id': st['object_id'], 'code': st['code'],
                            'name': st['name'], 'sector_macro': st['sector_macro'],
                            'sector_name': st['sector_name']})
        for code in prev_st.keys() - cur_st.keys():
            # Use the PREVIOUS scan's identity — the station is gone in `cur`, so its
            # last-known code/name/sector live in prev.
            st = prev_st[code]
            changes.append({'type': 'station_lost', **at,
                            'object_id': st['object_id'], 'code': st['code'],
                            'name': st['name'], 'sector_macro': st['sector_macro'],
                            'sector_name': st['sector_name']})

        # ── ships gained / lost ────────────────────────────────────────────────
        # Per your call, NO size filter — every player ship gain/loss is listed,
        # S-class included. A lost ship keeps its previous-scan identity (it's gone
        # in `cur`). type_name resolves the macro to a readable hull name the way the
        # main ship export does, so the feed isn't full of raw macro ids.
        prev_sh = _ships_by_code(conn, prev['scan_id'])
        cur_sh  = _ships_by_code(conn, cur['scan_id'])
        for code in cur_sh.keys() - prev_sh.keys():
            sh = cur_sh[code]
            changes.append({'type': 'ship_gained', **at, 'object_id': sh['object_id'],
                            'code': sh['code'], 'name': sh['name'],
                            'type_name': resolve_ship_type(sh['macro'] or ''),
                            'ship_class': sh['ship_class'], 'size': sh['size'],
                            'role': sh['role']})
        for code in prev_sh.keys() - cur_sh.keys():
            sh = prev_sh[code]
            changes.append({'type': 'ship_lost', **at, 'object_id': sh['object_id'],
                            'code': sh['code'], 'name': sh['name'],
                            'type_name': resolve_ship_type(sh['macro'] or ''),
                            'ship_class': sh['ship_class'], 'size': sh['size'],
                            'role': sh['role']})

        # ── reputation tier crossings ──────────────────────────────────────────
        # Only emit when the TIER LABEL changes (e.g. Neutral→Friendly) — within-tier
        # value drift is constant noise. Direction comes from the value delta's sign
        # (value is monotonic -30..+30), not from ranking the tier strings.
        prev_rep = _reputation_by_faction(conn, prev['scan_id'])
        cur_rep  = _reputation_by_faction(conn, cur['scan_id'])
        for fid, cr in cur_rep.items():
            pr = prev_rep.get(fid)
            # Need a baseline in prev, and both tiers known, to call it a crossing.
            if pr is None or cr['tier'] is None or pr['tier'] is None:
                continue
            if cr['tier'] == pr['tier']:
                continue
            changes.append({'type': 'reputation_crossing', **at,
                            'faction': fid, 'faction_name': cr['faction_name'],
                            'from_tier': pr['tier'], 'to_tier': cr['tier'],
                            'from_value': pr['value'], 'to_value': cr['value'],
                            'direction': 'up' if (cr['value'] or 0) >= (pr['value'] or 0)
                                         else 'down'})

        # ── net-worth milestones (powers of ten, upward) ───────────────────────
        pnw, cnw = nw.get(prev['scan_id'], 0), nw.get(cur['scan_id'], 0)
        for threshold in _NET_WORTH_MILESTONES:
            if pnw < threshold <= cnw:        # crossed this boundary upward
                changes.append({'type': 'milestone', **at, 'metric': 'net_worth',
                                'value': threshold, 'net_worth': cnw,
                                'label': f'Net worth passed {threshold:,} Cr'})

    # Newest first. Stable sort keeps each scan's events in the insertion order above
    # (stations before reputation), so the feed reads consistently within a scan.
    changes.sort(key=lambda c: c['scan_id'], reverse=True)
    return changes
