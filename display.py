import sys
import os
import math
from collections import Counter, defaultdict
from data.factions import FACTION_NAMES as _FACTION_NAMES
from data.production import display_name_to_id, units_per_cycle, units_per_hour, inputs_per_cycle, runtime_minutes
from data.sector_stats import SECTOR_SUNLIGHT

# ─────────────────────────────────────────────────────────────────────────────
#  ANSI COLOUR SUPPORT
#  On Windows, Virtual Terminal Processing must be enabled before escape codes
#  work in CMD. We attempt this once at import time and fall back to empty
#  strings if it fails or if stdout isn't a real terminal (e.g. piped to file).
# ─────────────────────────────────────────────────────────────────────────────

def _enable_ansi() -> bool:
    if not sys.stdout.isatty():
        return False
    if os.name == 'nt':
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            # ENABLE_PROCESSED_OUTPUT | ENABLE_WRAP_AT_EOL_OUTPUT | ENABLE_VIRTUAL_TERMINAL_PROCESSING
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except Exception:
            return False
    return True

_ANSI = _enable_ansi()
BLUE  = '\033[94m' if _ANSI else ''
RESET = '\033[0m'  if _ANSI else ''

def format_credits(amount_str: str) -> str:
    """Formats a raw credit integer string into a comma-separated display value."""
    try:
        return f"{int(amount_str):,} Cr"
    except (ValueError, TypeError):
        return f"{amount_str} Cr"


def format_m3(value: float) -> str:
    """Formats a cargo volume in m³ to a compact string (k / M suffix)."""
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M m³"
    if value >= 1_000:
        return f"{value / 1_000:.1f}k m³"
    return f"{value:.0f} m³"

def format_runtime(mins: float | None) -> str:
    """Formats a runtime-in-minutes value as a compact stock duration string."""
    if mins is None:
        return ""
    if mins <= 0:
        return "  ·  no stock"
    if mins < 60:
        return f"  ·  {mins:.0f}m stock"
    h = int(mins // 60)
    m = int(mins % 60)
    return f"  ·  {h}h {m:02d}m stock"


def display_trade_log(data: dict):
    """
    Prints all active TradePerform orders that involve a player-owned station
    or a player-owned ship.

    Two sections:
      - Station trades: grouped by station code. One column-header block is
        printed once, then each station gets a separator line with its totals
        followed by aligned BUYING / SELLING data rows. A ↳ line beneath each
        ware row lists the ships currently transporting that ware.
      - NPC-to-NPC routes: player ship is the transport but neither station is
        player-owned. Shown as a flat table sorted by ship name.
    """
    LINE   = "─" * 68
    trades = data.get("trades", [])

    # Build ship code → display label ("Ship Name [CODE]") from the player fleet.
    ship_labels: dict[str, str] = {}
    for s in data.get("ships", {}).get("player_ships", []):
        code = s.get("code", "")
        name = s.get("name")
        if code:
            ship_labels[code] = f"{name} [{code}]" if name else code

    print(LINE)
    print("  ACTIVE TRADE ORDERS")
    print()

    if not trades:
        if not data.get("trades_scanned"):
            print("    Trade scan not selected.")
        else:
            print("    No active trade orders found at player stations or ships.")
        return

    station_trades = [t for t in trades if not t.get("player_is_ship")]
    ship_trades    = [t for t in trades if t.get("player_is_ship")]

    # ── Summary line ──────────────────────────────────────────────────────────
    inbound_cr  = sum(t["total_cr"] for t in station_trades if t["player_is_buyer"])
    outbound_cr = sum(t["total_cr"] for t in station_trades if t["player_is_seller"])
    ship_cr     = sum(t["total_cr"] for t in ship_trades)
    n           = len(trades)
    parts       = [f"{n} {'order' if n == 1 else 'orders'}"]
    if inbound_cr:  parts.append(f"Inbound: {math.floor(inbound_cr):,} Cr")
    if outbound_cr: parts.append(f"Outbound: {math.floor(outbound_cr):,} Cr")
    if ship_cr:     parts.append(f"Ship routes: {math.floor(ship_cr):,} Cr")
    print(f"  {'  ·  '.join(parts)}")
    print()

    # ── Per-station breakdown ─────────────────────────────────────────────────
    # Aggregate: station_code → ware → [order_count, units, total_cr, ship_set]
    if station_trades:
        station_buys:  dict[str, dict] = {}
        station_sells: dict[str, dict] = {}

        for t in station_trades:
            ware = t["ware_name"]
            ship = t.get("ship_code", "")
            if t["player_is_buyer"]:
                d = station_buys.setdefault(t["buyer_code"], {})
                r = d.setdefault(ware, [0, 0, 0.0, set()])
                r[0] += 1;  r[1] += t["amount"];  r[2] += t["total_cr"]
                if ship: r[3].add(ship)
            if t["player_is_seller"]:
                d = station_sells.setdefault(t["seller_code"], {})
                r = d.setdefault(ware, [0, 0, 0.0, set()])
                r[0] += 1;  r[1] += t["amount"];  r[2] += t["total_cr"]
                if ship: r[3].add(ship)

        wc = max((len(t["ware_name"]) for t in station_trades), default=14)
        wc = max(14, min(28, wc + 1))

        # Column headers printed once above all station blocks.
        print(f"  {'':3}  {'Ware':<{wc}}  {'Orders':>6}  {'Units':>9}  {'Avg Cr/unit':>11}  {'Total Cr':>14}")
        print(f"  {'─'*3}  {'─'*wc}  {'─'*6}  {'─'*9}  {'─'*11}  {'─'*14}")

        for code in sorted(set(station_buys) | set(station_sells)):
            buys  = station_buys.get(code,  {})
            sells = station_sells.get(code, {})
            buy_total  = sum(v[2] for v in buys.values())
            sell_total = sum(v[2] for v in sells.values())

            # Station separator — code + per-station totals on one line.
            print(f"  ── {code}  ·  In: {math.floor(buy_total):,} Cr  ·  Out: {math.floor(sell_total):,} Cr")

            rows = (
                [("In",  w, *v) for w, v in sorted(buys.items())] +
                [("Out", w, *v) for w, v in sorted(sells.items())]
            )
            for direction, ware, n, units, total, ships in rows:
                avg = total / units if units else 0
                print(f"  {direction:<3}  {ware:<{wc}}  {n:>6}  {units:>9,}  {avg:>11,.0f}  {math.floor(total):>14,}")
                if ships:
                    # ↳ line indented to align with the start of the Ware column.
                    # Indent = 2 (margin) + 3 (dir) + 2 (gap) = 7 spaces.
                    ship_strs = "  ·  ".join(ship_labels.get(sc, sc) for sc in sorted(ships))
                    print(f"       ↳ {ship_strs}")

            print()

    # ── Player ships — NPC-to-NPC routes ─────────────────────────────────────
    # Player ship is the transport; neither station is player-owned.
    # Flat table sorted by ship name — each ship has at most one active order.
    if ship_trades:
        n_st = len(ship_trades)
        print(f"  PLAYER SHIPS — NPC-to-NPC ROUTES  ·  "
              f"{n_st} {'order' if n_st == 1 else 'orders'}  ·  {math.floor(ship_cr):,} Cr")
        print()

        sc = max(
            (len(ship_labels.get(t.get("ship_code", ""), t.get("ship_code", ""))) for t in ship_trades),
            default=20,
        )
        sc = max(20, min(44, sc + 1))
        wc = max((len(t["ware_name"]) for t in ship_trades), default=12)
        wc = max(12, min(20, wc + 1))

        print(f"  {'Ship':<{sc}}  {'Ware':<{wc}}  {'Units':>9}  {'Cr/unit':>9}  {'Total Cr':>14}  Destination")
        print(f"  {'─'*sc}  {'─'*wc}  {'─'*9}  {'─'*9}  {'─'*14}  {'─'*20}")

        for t in sorted(ship_trades, key=lambda x: ship_labels.get(x.get("ship_code", ""), x.get("ship_code", ""))):
            code  = t.get("ship_code", "")
            label = ship_labels.get(code, code)
            dest  = t.get("buyer_code") or "?"
            print(
                f"  {label:<{sc}}  {t['ware_name']:<{wc}}  "
                f"{t['amount']:>9,}  {t['price_cr']:>9,.2f}  {math.floor(t['total_cr']):>14,}  → {dest}"
            )
        print()


def display_trade_history(data: dict):
    """
    Prints a summary of completed trade history from the economylog.

    Organised into two clearly labelled sections:

      SUMMARY BY STATION  — aggregated counts and Cr totals per station,
                            broken down by direction (In / Out) and ware.
                            Ware rows are indented under their station header
                            to make the parent-child relationship clear.

      INDIVIDUAL TRADE LOG — every recorded entry, split into:
                              · Station trades — grouped by player station,
                                with column headers per group so they are
                                always visible above the rows.
                              · Player ship trades — flat list for trades
                                where a player ship had no station on either
                                side.
    """
    from collections import defaultdict
    from itertools import groupby

    LINE    = "─" * 68
    history = data.get("trade_history", [])

    print(LINE)
    print("  COMPLETED TRADE HISTORY")
    print()

    if not history:
        if not data.get("trade_history_scanned"):
            print("    Trade history scan not selected.")
        else:
            print("    No completed trade entries found in economylog.")
            print("    (X4 8.0 may store an empty global log — entries appear per station.)")
        return

    # ── Top-level summary line ────────────────────────────────────────────────
    bought_cr = sum(t["total_cr"] for t in history if t["player_is_buyer"])
    # Exclude courier pickup legs (BUY legs where station sold to its own ship at
    # the internal handoff price). Include homebase-attributed SELL legs instead,
    # which carry the correct commercial price the NPC buyer actually paid.
    sold_cr   = sum(
        t["total_cr"] for t in history
        if (t["player_is_seller"] or t.get("_homebase_seller_id"))
        and not t.get("_courier_pickup")
    )
    oldest_s  = max((t["time_ago_s"] for t in history), default=0)
    age_str   = f"{oldest_s / 3600:.1f}h" if oldest_s >= 3600 else f"{oldest_s / 60:.0f}m"
    n         = len(history)

    print(f"  {n:,} {'entry' if n == 1 else 'entries'}  ·  "
          f"Purchased: {math.floor(bought_cr):,} Cr  ·  Sold: {math.floor(sold_cr):,} Cr  ·  "
          f"Log covers last ~{age_str}")
    print()

    # ── Shared lookups used by both sections ──────────────────────────────────
    # code → name: station display name for aggregate section headers.
    code_to_name: dict[str, str] = {
        s["code"]: s["name"]
        for s in data.get("stations", [])
        if s.get("code") and s.get("name")
    }
    # object_id → name: for grouping headers in the individual log section.
    station_id_to_name: dict[str, str] = {
        st["object_id"]: st["name"]
        for st in data.get("stations", [])
        if st.get("object_id") and st.get("name")
    }
    # Player ship IDs so the Ship column can mark them with ★.
    player_ship_ids: set[str] = {
        sh["object_id"]
        for sh in data.get("ships", {}).get("player_ships", [])
        if sh.get("object_id")
    }

    def _age(s: float) -> str:
        """Format seconds-ago as a compact human-readable string."""
        if s < 60:
            return f"{int(s)}s"
        if s < 3600:
            return f"{int(s // 60)}m"
        h = int(s // 3600)
        m = int((s % 3600) // 60)
        return f"{h}h {m:02d}m"

    def _truncate(label: str, width: int) -> str:
        """Clip to exactly `width` chars — f-string :<N pads but never clips."""
        return label if len(label) <= width else label[:width - 1] + "…"

    # ── Entry classification helpers ──────────────────────────────────────────
    # Defined here (before Section 1) so they are available to both the summary
    # aggregation and the individual trade log sections below.

    def _is_internal(t: dict) -> bool:
        """True for trades where goods flow between player-owned entities.

        Covers station-to-station transfers and player ships delivering TO a
        player station (mining, inbound transport). Explicitly excludes the
        case where a player ship is picking up from a player station to sell
        to an NPC — that ship is just the commercial transport leg.
        """
        if t["player_is_buyer"] and t["player_is_seller"]:
            return True  # station-to-station
        if t["player_is_buyer"] and t.get("player_ship_is_seller", False):
            return True  # player ship delivering to player station
        return False

    # ═════════════════════════════════════════════════════════════════════════
    #  SECTION 1 — SUMMARY BY STATION
    # ═════════════════════════════════════════════════════════════════════════

    agg: dict = defaultdict(lambda: {
        "In":  defaultdict(lambda: [0, 0, 0.0]),
        "Out": defaultdict(lambda: [0, 0, 0.0]),
    })
    for t in history:
        if _is_internal(t) or t.get("_courier_pickup"):
            continue
        ware = t["ware_name"]
        if t["player_is_buyer"]:
            r = agg[t["buyer_code"]]["In"][ware]
            r[0] += 1;  r[1] += t["amount"];  r[2] += t["total_cr"]
        if t["player_is_seller"]:
            r = agg[t["seller_code"]]["Out"][ware]
            r[0] += 1;  r[1] += t["amount"];  r[2] += t["total_cr"]
        if t.get("_homebase_seller_id"):
            r = agg[t["_homebase_seller_code"]]["Out"][ware]
            r[0] += 1;  r[1] += t["amount"];  r[2] += t["total_cr"]

    agg_wc = max(
        (len(w) for station in agg.values() for side in station.values() for w in side),
        default=14,
    )
    agg_wc = max(14, min(28, agg_wc + 1))

    print("  SUMMARY BY STATION")
    print()
    # Column header printed once; ware rows are indented 5 extra spaces below
    # each station header to show they are subordinate to that station.
    print(f"       {'Dir':<3}  {'Ware':<{agg_wc}}  {'Trades':>6}  {'Units':>9}  {'Avg Cr/unit':>11}  {'Total Cr':>14}")
    print(f"       {'─'*3}  {'─'*agg_wc}  {'─'*6}  {'─'*9}  {'─'*11}  {'─'*14}")

    for code in sorted(agg):
        inbound    = agg[code]["In"]
        outbound   = agg[code]["Out"]
        buy_total  = sum(v[2] for v in inbound.values())
        sell_total = sum(v[2] for v in outbound.values())

        name  = code_to_name.get(code)
        label = f"{name}  [{code}]" if name else code
        print(f"  ── {label}  ·  Purchased: {math.floor(buy_total):,} Cr  ·  Sold: {math.floor(sell_total):,} Cr")

        rows = (
            [("In",  w, *v) for w, v in sorted(inbound.items())] +
            [("Out", w, *v) for w, v in sorted(outbound.items())]
        )
        for direction, ware, n_trades, units, total in rows:
            avg = total / units if units else 0
            # 5-space indent visually nests these rows under the station header above.
            print(f"       {direction:<3}  {ware:<{agg_wc}}  {n_trades:>6}  {units:>9,}  {avg:>11,.0f}  {math.floor(total):>14,}")

        print()

    # ═════════════════════════════════════════════════════════════════════════
    #  SECTION 2 — INDIVIDUAL TRADE LOG
    # ═════════════════════════════════════════════════════════════════════════

    # Commercial: player station on one side, external NPC on the other.
    # Also includes homebase-attributed SELL legs (player courier delivering from
    # a player station to an NPC buyer). Courier pickup legs are suppressed — the
    # SELL leg shows the correct commercial price, the BUY leg would show the
    # internal handoff price.
    station_entries = sorted(
        (t for t in history
         if (t["player_is_buyer"] or t["player_is_seller"] or t.get("_homebase_seller_id"))
         and not _is_internal(t)
         and not t.get("_courier_pickup")),
        key=lambda t: t["time_ago_s"],
    )
    # Player ship as transport with no player station on either side.
    # Homebase-attributed SELL legs have moved to station_entries above.
    ship_entries = sorted(
        (t for t in history
         if (t.get("player_ship_is_buyer") or t.get("player_ship_is_seller"))
         and not (t["player_is_buyer"] or t["player_is_seller"])
         and not t.get("_homebase_seller_id")
         and not _is_internal(t)),
        key=lambda t: t["time_ago_s"],
    )
    # Internal: player-owned entity on both sides — mining deliveries, inter-station
    # transfers, and resupply runs between player stations and player ships.
    internal_entries = sorted(
        (t for t in history if _is_internal(t)),
        key=lambda t: t["time_ago_s"],
    )

    if not station_entries and not ship_entries and not internal_entries:
        return

    print("  INDIVIDUAL TRADE LOG")
    print()

    # Helpers shared by the commercial station and internal trade sections.
    def _st_key(t: dict) -> tuple[str, str]:
        """(object_id, code) of the player-station side of this entry."""
        if t.get("_homebase_seller_id"):
            # SELL leg attributed to a homebase player station — group under that station.
            return (t["_homebase_seller_id"], t["_homebase_seller_code"])
        return (t["buyer_id"],  t["buyer_code"])  if t["player_is_buyer"] \
          else (t["seller_id"], t["seller_code"])

    def _ship_lbl(t: dict) -> str:
        """Display label for the entity on the non-player-station side."""
        if t.get("_homebase_seller_id"):
            # Original seller_id is still the ship (not the homebase station).
            ship_id   = t["seller_id"]
            ship_code = t["seller_code"]
        else:
            ship_id   = t["seller_id"]   if t["player_is_buyer"] else t["buyer_id"]
            ship_code = t["seller_code"] if t["player_is_buyer"] else t["buyer_code"]
        return f"★ {ship_code}" if ship_id in player_ship_ids else ship_code

    def _ship_id(t: dict) -> str:
        """Hex component ID of the non-player-station entity (seller if player buys, buyer if player sells).
        Shown in the Ship ID column so any ship can be cross-referenced in the save XML."""
        if t.get("_homebase_seller_id"):
            return t["seller_id"] or "—"
        sid = t["seller_id"] if t["player_is_buyer"] else t["buyer_id"]
        return sid or "—"

    # ── Table 1: commercial station trades, grouped by player station ─────────
    # Grouping removes the need for a Station column on every row — the station
    # appears once as a section header, making the table narrower and easier to
    # scan within a single station's history.
    if station_entries:
        n_st = len(station_entries)
        print(f"  STATION TRADES  ·  {n_st} {'entry' if n_st == 1 else 'entries'}")
        print()

        # Sort by station code so rows are grouped, then most-recent-first within
        # each group (smallest time_ago_s = happened most recently).
        sorted_st = sorted(station_entries, key=lambda t: (_st_key(t)[1], t["time_ago_s"]))

        # Compute column widths once across all station entries.
        tc     = 8
        st_shc = max((len(_ship_lbl(t)) for t in station_entries), default=14)
        st_shc = max(14, min(36, st_shc + 1))
        st_ic  = max((len(_ship_id(t)) for t in station_entries), default=9)
        st_ic  = max(9, min(14, st_ic + 1))
        st_wc  = max((len(t["ware_name"]) for t in station_entries), default=14)
        st_wc  = max(14, min(28, st_wc + 1))
        st_cc  = max((len(t.get("counterparty_station") or "—") for t in station_entries), default=11)
        st_cc  = max(11, min(40, st_cc + 1))

        for (st_id, st_code), grp in groupby(sorted_st, key=_st_key):
            group = list(grp)
            name  = station_id_to_name.get(st_id, "")
            label = f"{name}  [{st_code}]" if name else st_code
            n_grp = len(group)
            print(f"  ── {label}  ·  {n_grp} {'entry' if n_grp == 1 else 'entries'}")
            # Column headers per group so they are always visible above the rows,
            # even when a station has many entries.
            print(f"     {'Time':<{tc}}  {'Ship':<{st_shc}}  {'Ship ID':<{st_ic}}  {'Dir'}  "
                  f"{'Ware':<{st_wc}}  {'Units':>9}  {'Cr/unit':>9}  {'Total Cr':>12}  {'Counterparty':<{st_cc}}")
            print(f"     {'─'*tc}  {'─'*st_shc}  {'─'*st_ic}  {'─'*3}  "
                  f"{'─'*st_wc}  {'─'*9}  {'─'*9}  {'─'*12}  {'─'*st_cc}")
            for t in group:
                direction = "In " if t["player_is_buyer"] else "Out"
                cp        = t.get("counterparty_station") or "—"
                print(f"     {_age(t['time_ago_s']):<{tc}}  "
                      f"{_truncate(_ship_lbl(t), st_shc):<{st_shc}}  {_ship_id(t):<{st_ic}}  {direction}  "
                      f"{t['ware_name']:<{st_wc}}  {t['amount']:>9,}  {t['price_cr']:>9,.2f}  "
                      f"{math.floor(t['total_cr']):>12,}  {cp:<{st_cc}}")
            print()

    # ── Table 2: ship-only trades (no player station on either side) ──────────
    if ship_entries:
        n_ship = len(ship_entries)
        print(f"  PLAYER SHIP TRADES  ·  {n_ship} {'entry' if n_ship == 1 else 'entries'}")
        print()

        def _ship_lbl2(t: dict) -> str:
            """Display label for the player ship in a ship-only entry."""
            ship_id   = t["buyer_id"]   if t.get("player_ship_is_buyer") else t["seller_id"]
            ship_code = t["buyer_code"] if t.get("player_ship_is_buyer") else t["seller_code"]
            return f"★ {ship_code}" if ship_id in player_ship_ids else ship_code

        def _ship_id2(t: dict) -> str:
            """Hex component ID of the player ship in a ship-only entry."""
            sid = t["buyer_id"] if t.get("player_ship_is_buyer") else t["seller_id"]
            return sid or "—"

        tc2  = 8
        shc2 = max((len(_ship_lbl2(t)) for t in ship_entries), default=14)
        shc2 = max(14, min(36, shc2 + 1))
        ic2  = max((len(_ship_id2(t)) for t in ship_entries), default=9)
        ic2  = max(9, min(14, ic2 + 1))
        wc2  = max((len(t["ware_name"]) for t in ship_entries), default=14)
        wc2  = max(14, min(28, wc2 + 1))
        cc2  = max((len(t.get("counterparty_station") or "—") for t in ship_entries), default=11)
        cc2  = max(11, min(40, cc2 + 1))

        print(f"  {'Time':<{tc2}}  {'Ship':<{shc2}}  {'Ship ID':<{ic2}}  {'Dir'}  "
              f"{'Ware':<{wc2}}  {'Units':>9}  {'Cr/unit':>9}  {'Total Cr':>12}  {'Counterparty':<{cc2}}")
        print(f"  {'─'*tc2}  {'─'*shc2}  {'─'*ic2}  {'─'*3}  "
              f"{'─'*wc2}  {'─'*9}  {'─'*9}  {'─'*12}  {'─'*cc2}")

        for t in ship_entries:
            direction = "In " if t.get("player_ship_is_buyer") else "Out"
            cp        = t.get("counterparty_station") or "—"
            print(f"  {_age(t['time_ago_s']):<{tc2}}  "
                  f"{_truncate(_ship_lbl2(t), shc2):<{shc2}}  {_ship_id2(t):<{ic2}}  {direction}  "
                  f"{t['ware_name']:<{wc2}}  {t['amount']:>9,}  {t['price_cr']:>9,.2f}  "
                  f"{math.floor(t['total_cr']):>12,}  {cp:<{cc2}}")

        print()

    # ── Table 3: internal trades (player-owned entities on both sides) ────────
    # Covers mining deliveries (player miner → player station), inter-station
    # transfers (player station → player station), and resupply runs. Separated
    # from commercial station trades so external market activity stays readable.
    if internal_entries:
        n_int = len(internal_entries)
        print(f"  INTERNAL TRADE  ·  {n_int} {'entry' if n_int == 1 else 'entries'}")
        print()

        tc_i   = 8
        in_shc = max((len(_ship_lbl(t)) for t in internal_entries), default=14)
        in_shc = max(14, min(36, in_shc + 1))
        in_ic  = max((len(_ship_id(t)) for t in internal_entries), default=9)
        in_ic  = max(9, min(14, in_ic + 1))
        in_wc  = max((len(t["ware_name"]) for t in internal_entries), default=14)
        in_wc  = max(14, min(28, in_wc + 1))

        sorted_int = sorted(internal_entries, key=lambda t: (_st_key(t)[1], t["time_ago_s"]))

        for (st_id, st_code), grp in groupby(sorted_int, key=_st_key):
            group = list(grp)
            name  = station_id_to_name.get(st_id, "")
            label = f"{name}  [{st_code}]" if name else st_code
            n_grp = len(group)
            print(f"  ── {label}  ·  {n_grp} {'entry' if n_grp == 1 else 'entries'}")
            print(f"     {'Time':<{tc_i}}  {'Counterparty':<{in_shc}}  {'Ship ID':<{in_ic}}  {'Dir'}  "
                  f"{'Ware':<{in_wc}}  {'Units':>9}  {'Cr/unit':>9}  {'Total Cr':>12}")
            print(f"     {'─'*tc_i}  {'─'*in_shc}  {'─'*in_ic}  {'─'*3}  "
                  f"{'─'*in_wc}  {'─'*9}  {'─'*9}  {'─'*12}")
            for t in group:
                direction = "In " if t["player_is_buyer"] else "Out"
                print(f"     {_age(t['time_ago_s']):<{tc_i}}  "
                      f"{_truncate(_ship_lbl(t), in_shc):<{in_shc}}  {_ship_id(t):<{in_ic}}  {direction}  "
                      f"{t['ware_name']:<{in_wc}}  {t['amount']:>9,}  {t['price_cr']:>9,.2f}  "
                      f"{math.floor(t['total_cr']):>12,}")
            print()


def display_in_progress_deliveries(data: dict):
    """
    Prints deliveries that are physically mid-flight at save time — ships that
    have already picked up their cargo and are en route to drop it off.

    A delivery is "in progress" when the ship has an active TradePerform order
    AND a DockAt sub-order pointing at its delivery destination. The scanner
    captures this in delivery_dest_index (ship_id → destination station ID);
    we cross-reference that against the active trades list to find the matching
    ware, quantity, and price.

    Ships without a matching TradePerform entry are shown with ware = "—" so
    mid-delivery ships that bypassed the trade scanner are still visible.
    """
    LINE   = "─" * 68
    trades = data.get("trades", [])
    delivery_dest_index: dict = data.get("delivery_dest_index", {})
    id_to_label: dict = {}

    # Build station ID → display code from player and NPC stations.
    for st in data.get("stations", []) + data.get("npc_stations", []):
        oid = st.get("object_id")
        if oid:
            id_to_label[oid] = st.get("code") or oid

    # Build ship display labels.
    ship_labels: dict[str, str] = {}
    for s in data.get("ships", {}).get("player_ships", []):
        code = s.get("code", "")
        name = s.get("name")
        oid  = s.get("object_id", "")
        if oid:
            ship_labels[oid] = f"{name} [{code}]" if name else code

    print(LINE)
    print("  IN PROGRESS DELIVERIES")
    print()

    if not data.get("trades_scanned"):
        print("    Trade scan not selected.")
        return

    if not delivery_dest_index:
        print("    No ships currently mid-delivery.")
        return

    # Index trades by ship_id for fast lookup.
    trade_by_ship: dict[str, dict] = {
        t["ship_id"]: t for t in trades if t.get("ship_id")
    }

    # Only show deliveries involving a player station or player ship.
    relevant = {
        ship_id: dest_id
        for ship_id, dest_id in delivery_dest_index.items()
        if ship_id in trade_by_ship or ship_id in ship_labels
    }

    if not relevant:
        print("    No player-related deliveries in progress.")
        return

    total_cr = sum(
        math.floor(trade_by_ship[sid]["total_cr"])
        for sid in relevant
        if sid in trade_by_ship
    )

    n = len(relevant)
    print(f"  {n} {'delivery' if n == 1 else 'deliveries'}  ·  Value in transit: {total_cr:,} Cr")
    print()

    sc = max(
        (len(ship_labels.get(sid, sid)) for sid in relevant),
        default=20,
    )
    sc = max(20, min(44, sc + 1))
    wc = max(
        (len(trade_by_ship[sid]["ware_name"]) for sid in relevant if sid in trade_by_ship),
        default=12,
    )
    wc = max(12, min(24, wc + 1))

    print(f"  {'Ship':<{sc}}  {'Ware':<{wc}}  {'Units':>9}  {'Cr/unit':>9}  {'Total Cr':>12}  Destination")
    print(f"  {'─'*sc}  {'─'*wc}  {'─'*9}  {'─'*9}  {'─'*12}  {'─'*20}")

    for ship_id, dest_id in sorted(relevant.items(),
                                    key=lambda kv: ship_labels.get(kv[0], kv[0])):
        ship_lbl = ship_labels.get(ship_id, ship_id)
        dest_lbl = id_to_label.get(dest_id, dest_id)
        t = trade_by_ship.get(ship_id)
        if t:
            print(
                f"  {ship_lbl:<{sc}}  {t['ware_name']:<{wc}}  "
                f"{t['amount']:>9,}  {t['price_cr']:>9,.2f}  "
                f"{math.floor(t['total_cr']):>12,}  → {dest_lbl}"
            )
        else:
            print(f"  {ship_lbl:<{sc}}  {'—':<{wc}}  {'—':>9}  {'—':>9}  {'—':>12}  → {dest_lbl}")

    print()


def display_results(data: dict):
    """
    Prints the extracted intelligence data to console in a readable, formatted report.

    SUMMARY:
    This function generates an X4 Foundations Empire Intelligence Report showing
    player-owned stations, faction reputation standings, fleet composition with
    hull health and pilot assignments, crew rosters, and NPC presence in monitored
    sectors (tier 2/3+ only). Uses ASCII art for visual grouping and dynamic column
    widths to handle variable-length ship names.

    DISPLAY FORMAT:
    - Stations are grouped by sector so that multiple stations in the same
      location are visually clustered together. The sector is printed once
      as a header, with each station indented beneath it. Station name and
      code appear on the first line, production on the second.
    - Reputation values are scaled to match in-game display (-30 to +30 range, log10 curve).
      Shows Total (what the game UI displays), a visual bar, tier label,
      the permanent Base value, and any temporary Booster from missions.
    - Ships are grouped by sector, matching the station layout style. Each ship
      shows its display name (player-given or code fallback), size, role,
      current order, and hull origin. A pilot line is printed beneath each
      ship only when a named pilot is assigned, keeping output compact for
      large fleets where ships have generic computer-controlled crew.
      Captured ships (hull origin differs from standard player factions)
      are flagged with a ★ prefix.
    - Crew roster groups all player-owned crew by role. Within each group the
      primary skill for that role is shown first so the most useful number
      is always visible at a glance without scanning the whole line.
    - NPC presence (tiers 2/3 only) shows enemy and neutral ships grouped by
      sector and faction, summarising their composition by role count. This
      gives a quick threat and activity picture for sectors the player operates in.

    COLUMN WIDTHS:
    - Ship name column dynamically calculates width based on longest ship name,
      with minimum 20 and maximum 40 characters to keep output balanced.
      Falls back to code if no custom name is provided.
    - Crew roster uses dynamic widths for name (min 20, max 30) and assignment
      columns (min 24, max 36) to ensure data fits cleanly.

    SPECIAL NOTATIONS:
    - Hull Origin "★ X" indicates captured/unusual hull origin (non-standard player faction)
    - Pilot sub-line shows only when named pilot assigned (compact output design)
    - HP display priority: Full → percentage with raw HP → raw HP only → "Full"
    """
    SEP  = "═" * 68
    LINE = "─" * 68
    THIN = "·" * 68

    print(f"\n{SEP}")
    print("         X4 FOUNDATIONS — EMPIRE INTELLIGENCE REPORT v4.1")
    print(SEP)
    if data.get("stations_scanned"):
        print(f"  PILOT          : {data['player_name'] or 'Unknown'}")
        print(f"  CURRENT SECTOR : {data['player_sector'] or 'Unknown'}")
        credits_str = format_credits(data['player_credits']) if data['player_credits'] else "Not found"
        print(f"  CREDITS        : {credits_str}")
    else:
        print(f"  PILOT          : Station scan not selected")
        print(f"  CURRENT SECTOR : Station scan not selected")
        print(f"  CREDITS        : Station scan not selected")
    print(LINE)

    # ── STATIONS — grouped by sector ──────────────────────────────────────────
    # We build an ordered dict of { sector_name: [station, station, ...] }
    # preserving the order sectors are first encountered in the save file.
    if data.get("stations_scanned"):
        print(f"  OWNED STATIONS  ({len(data['stations'])} total)")
    else:
        print(f"  OWNED STATIONS")
    print()

    if not data.get("stations_scanned"):
        print("    Station scan not selected.")
    elif data["stations"]:
        # Group stations by sector, preserving encounter order
        sectors_seen = {}   # { sector_name: [station dicts] }
        for s in data["stations"]:
            sector = s["sector"]
            if sector not in sectors_seen:
                sectors_seen[sector] = []
            sectors_seen[sector].append(s)

        # Print each sector group
        for sector, stations in sectors_seen.items():
            # Sector header — printed once per group
            station_word = "station" if len(stations) == 1 else "stations"
            sunlight     = SECTOR_SUNLIGHT.get(sector)
            sun_str      = f"  ·  {sunlight * 100:.0f}% sun" if sunlight is not None else ""
            print(f"  ┌─ SECTOR: {sector}  ({len(stations)} {station_word}){sun_str}")

            for i, s in enumerate(stations):
                is_last   = i == len(stations) - 1
                connector = "└──" if is_last else "├──"
                indent    = "       " if is_last else "│      "

                # Module count on the name line so it's visible at a glance.
                # Falls back to "?" if the field isn't present (older scan data).
                mod_count = s.get("module_count")
                mod_str   = f"  ·  {mod_count} modules" if mod_count is not None else ""
                print(f"  {connector} {s['name']} [{s['code']}]{mod_str}")

                status = s.get("status", "Operational")
                if status != "Operational":
                    print(f"  {indent} Status   : {status}")

                prod_modules = [m for m in s.get("modules", [])
                                if m.get("category") == "Production" and m.get("produces")]
                if prod_modules:
                    counts    = Counter(m["produces"] for m in prod_modules)
                    sector    = s.get("sector", "")
                    inventory = s.get("inventory") or {}
                    for idx, (ware_display, count) in enumerate(sorted(counts.items())):
                        lbl     = "Produces" if idx == 0 else "        "
                        ware_id = display_name_to_id(ware_display)
                        if ware_id:
                            per_cyc  = count * units_per_cycle(ware_id, sector)
                            per_hr   = count * units_per_hour(ware_id, sector)
                            rt_str   = format_runtime(runtime_minutes(ware_id, count, inventory))
                            print(f"  {indent} {lbl} : {ware_display:<22} {count}x  {per_cyc:>5.0f}/cyc  ·  {per_hr:>7,.0f}/hr{rt_str}")
                            inputs = inputs_per_cycle(ware_id, count)
                            if inputs:
                                inp_str = "  ·  ".join(f"{qty:,} {name}" for name, qty in sorted(inputs.items()))
                                print(f"  {indent}             └─ {inp_str}")
                        else:
                            print(f"  {indent} {lbl} : {count}x {ware_display}")
                elif s["production"]:
                    print(f"  {indent} Produces : {s['production']}")
                else:
                    print(f"  {indent} Produces : —")

                # ── Hull health ───────────────────────────────────────────────
                hull_pct = s.get("hull_pct")
                hull_hp  = s.get("hull_hp")
                hull_max = s.get("hull_max")

                if hull_pct is not None and hull_pct >= 99.9:
                    hull_str = f"Full  ({hull_max:,.0f} HP)"
                elif hull_pct is not None:
                    hull_str = f"{hull_pct:.0f}%  ({hull_hp:,.0f} / {hull_max:,.0f} HP)"
                else:
                    hull_str = "—"

                print(f"  {indent} Hull     : {hull_str}")

                # ── Shield health — own line, coloured blue ───────────────────
                # shield_pct is None when no shield generators are installed.
                shield_pct = s.get("shield_pct")
                shield_hp  = s.get("shield_hp")
                shield_max = s.get("shield_max")

                if shield_pct is not None and shield_pct >= 99.9:
                    shield_str = f"Full  ({shield_max:,.0f} HP)"
                elif shield_pct is not None:
                    shield_str = f"{shield_pct:.0f}%  ({shield_hp:,.0f} / {shield_max:,.0f} HP)"
                else:
                    shield_str = "None"

                print(f"  {indent} Shield   : {BLUE}{shield_str}{RESET}")

                # ── Storage utilisation — per type then total ─────────────────
                # Adjusted values (adj) include trade reservations and match the
                # game's displayed fill %. Raw physical values are stored in the
                # JSON under cargo_{type}_pct / cargo_pct for independent access.
                for type_label, type_key in (
                    ("Container", "container"),
                    ("Solid",     "solid"),
                    ("Liquid",    "liquid"),
                ):
                    t_adj_m3  = s.get(f"cargo_{type_key}_adj_m3")
                    t_max     = s.get(f"cargo_{type_key}_max")
                    t_adj_pct = s.get(f"cargo_{type_key}_adj_pct")
                    if t_adj_pct is not None:
                        print(f"  {indent} {type_label:<9}: {format_m3(t_adj_m3)} / {format_m3(t_max)}  ({t_adj_pct:.0f}%)")
                    elif t_adj_m3 is not None:
                        print(f"  {indent} {type_label:<9}: {format_m3(t_adj_m3)}")

                cargo_adj_m3  = s.get("cargo_adj_m3")
                cargo_max     = s.get("cargo_max")
                cargo_adj_pct = s.get("cargo_adj_pct")
                if cargo_adj_pct is not None:
                    print(f"  {indent} {'Storage':<9}: {format_m3(cargo_adj_m3)} / {format_m3(cargo_max)}  ({cargo_adj_pct:.0f}%) [total]")
                elif cargo_adj_m3 is not None:
                    print(f"  {indent} {'Storage':<9}: {format_m3(cargo_adj_m3)}")

                # ── Inventory ────────────────────────────────────────────────
                inventory = s.get("inventory")
                if inventory is None:
                    pass  # stations pass didn't run — omit the line entirely
                elif inventory:
                    items    = sorted(inventory.items())
                    row_size = 3
                    for row_start in range(0, len(items), row_size):
                        row     = items[row_start:row_start + row_size]
                        lbl     = "Inventory" if row_start == 0 else "         "
                        content = "  ·  ".join(f"{amt:,} {name}" for name, amt in row)
                        print(f"  {indent} {lbl}: {content}")
                else:
                    print(f"  {indent} Inventory: —")

                # ── Docked ships ──────────────────────────────────────────────
                # Ships with connection="dock" are physically present in a bay.
                # We split own (player) vs visiting (NPC traders/miners) because
                # a busy station with many visitors signals healthy trade activity,
                # while own ships docked might mean they're waiting for orders.
                docked = s.get("docked_ships", [])
                if docked:
                    own       = sum(1 for d in docked if d["owner"] == "player")
                    building  = sum(1 for d in docked if d["under_construction"])
                    visiting  = len(docked) - own
                    parts = []
                    if own - building:  parts.append(f"{own - building} own")
                    if building:        parts.append(f"{building} building")
                    if visiting:        parts.append(f"{visiting} visiting")
                    detail = "  (" + "  ·  ".join(parts) + ")" if parts else ""
                    print(f"  {indent} Docked   : {len(docked)} ships{detail}")

                # Blank line between stations within a sector for breathing room,
                # but not after the last one (the sector group already adds one).
                if not is_last:
                    print(f"  │")

            print()  # Blank line between sector groups

    else:
        print("    No player-owned stations detected.")

    print(LINE)

    # ── NPC STATIONS IN PLAYER SECTORS ───────────────────────────────────────
    npc_stations = data.get("npc_stations", [])
    if npc_stations:
        # Group by sector, then by faction within each sector.
        by_sector: dict[str, list] = {}
        for st in npc_stations:
            by_sector.setdefault(st["sector"], []).append(st)

        print(f"  NPC STATIONS IN PLAYER SECTORS  ({len(npc_stations)} found)")
        print()

        for sector in sorted(by_sector):
            stations = sorted(by_sector[sector], key=lambda s: (s["owner"], s["name"]))
            print(f"  ┌─ SECTOR: {sector}  ({len(stations)} stations)")

            for i, st in enumerate(stations):
                is_last   = i == len(stations) - 1
                connector = "└──" if is_last else "├──"
                indent    = "       " if is_last else "│      "

                faction = _FACTION_NAMES.get(st["owner"], st["owner"].title())
                print(f"  {connector} {st['name']}")
                print(f"  {indent} Faction  : {faction}")

                wares = st.get("wares", [])
                if wares:
                    # Wrap ware list at ~70 chars so it stays readable
                    line    = ""
                    lines   = []
                    for ware in wares:
                        chunk = (ware + ", ") if ware != wares[-1] else ware
                        if len(line) + len(chunk) > 70 and line:
                            lines.append(line.rstrip(", "))
                            line = chunk
                        else:
                            line += chunk
                    if line:
                        lines.append(line.rstrip(", "))
                    print(f"  {indent} Trades   : {lines[0]}")
                    for extra in lines[1:]:
                        print(f"  {indent}             {extra}")

                if not is_last:
                    print(f"  │")

            print()

        print(LINE)

    # ── REPUTATION ────────────────────────────────────────────────────────────
    # Displayed as in-game values (log10 curve, range -30 to +30).
    # Base = permanent standing | Booster = temporary mission bonus.
    # Total = base + booster combined, matching what the in-game UI shows.
    if data.get("reputation_scanned"):
        print(f"  FACTION REPUTATION  ({len(data['reputation'])} factions)"
              f"   [  -30 ◄ hostile · neutral · friendly ► +30  ]")
        print()
        print(f"    {'Faction':<38} {'Total':>6}  {'':22}  {'Tier':<10}  {'Base':>6}  {'Boost':>6}")
        print(f"    {'─' * 38} {'─' * 6}  {'─' * 22}  {'─' * 10}  {'─' * 6}  {'─' * 6}")

        if data["reputation"]:
            for r in data["reputation"]:
                # Scale -30..+30 onto a 20-character visual bar.
                # Adding 30 shifts the range to 0..60, dividing by 60 normalises
                # to 0..1, multiplying by 20 gives the bar character count.
                bar_val = int((r['value'] + 30) / 60 * 20)
                bar_val = max(0, min(20, bar_val))
                bar     = "█" * bar_val + "░" * (20 - bar_val)

                booster_str = f"{r['booster']:>+6.2f}" if r['booster'] != 0 else "     —"
                print(
                    f"    {r['faction_name']:<38} {r['value']:>+6.2f}  [{bar}]  "
                    f"{r['tier']:<10}  {r['base']:>+6.2f}  {booster_str}"
                )
        else:
            print("    No reputation data found.")
    else:
        print(f"  FACTION REPUTATION")
        print()
        print("    Reputation scan not selected.")

    print(LINE)

    # ── PLAYER FLEET ──────────────────────────────────────────────────────────
    # Ships are grouped by sector, matching the station layout pattern.
    # Within each sector group, ships are listed in save-file encounter order.
    # The pilot sub-line is conditional — we only print it when a named pilot
    # is present, keeping output compact for large fleets where many ships
    # have generic computer-controlled crew whose names add little value.
    ships_data   = data.get("ships", {})
    player_ships = ships_data.get("player_ships", [])
    npc_ships    = ships_data.get("npc_ships", [])

    # Pre-compute service crew and marine counts per ship code so we can
    # display them inline without re-scanning the full crew list per ship.
    crew = data.get("crew", [])
    _ship_crew: dict = defaultdict(lambda: {"service": 0, "marine": 0})
    for _c in crew:
        if _c["role"] in ("service", "marine"):
            _ship_crew[_c["assigned_code"]][_c["role"]] += 1

    if data.get("ships_scanned"):
        print(f"  PLAYER FLEET  ({len(player_ships)} ships)")
    else:
        print(f"  PLAYER FLEET")
    print()

    if not data.get("ships_scanned"):
        print("    Ships scan not selected.")
        print()
    elif player_ships:
        # Group by sector, preserving encounter order
        sectors_seen = {}   # { sector_name: [ship dicts] }
        for s in player_ships:
            sec = s["sector"]
            if sec not in sectors_seen:
                sectors_seen[sec] = []
            sectors_seen[sec].append(s)

        # ── Calculate column width dynamically ────────────────────────────
        # Now that ships have full type names (e.g. "Magnetar (Mineral) Vanguard")
        # instead of just codes, the name column needs to be wide enough for the
        # longest name in the fleet. We compute this once before the print loop.
        #
        # max() finds the longest display name across all ships. The 'or code'
        # fallback mirrors what we print below — if name is None we show the code.
        # We enforce a minimum of 20 so short fleets still look balanced, and
        # cap at 40 so very long custom names don't push everything off screen.
        name_col = max(
            (len(s["name"] if s["name"] else s["code"]) for s in player_ships),
            default=20
        )
        name_col = max(20, min(40, name_col + 1))

        print(f"    {'Ship / Pilot':<{name_col}} {'Size':<4}  {'Role':<16}  {'Order':<22}  {'Hull Origin':<14}  HP / Shield")
        print(f"    {'─' * name_col} {'─' * 4}  {'─' * 16}  {'─' * 22}  {'─' * 14}  {'─' * 16}")

        for sector, ships in sectors_seen.items():
            ship_word = "ship" if len(ships) == 1 else "ships"
            print(f"\n  ┌─ SECTOR: {sector}  ({len(ships)} {ship_word})")

            for i, s in enumerate(ships):
                # Corner piece on last ship, tee on all others
                connector = "└──" if i == len(ships) - 1 else "├──"
                indent    = "       " if i == len(ships) - 1 else "│      "

                # Prefer player-given name; fall back to the ship code.
                # Most ships won't have a custom name so the code is the
                # primary identifier for the majority of the fleet.
                display_name = s["name"] if s["name"] else s["code"]

                # Flag non-standard hull origins (e.g. captured Xenon ships).
                # We check against factions players can normally buy ships from
                # — anything else is captured, gifted, or otherwise unusual.
                hull_origin = s["hull_origin"]
                if hull_origin.lower() not in ("argon", "teladi", "paranid", "split",
                                               "terran", "boron", "antigone"):
                    hull_origin = f"★ {hull_origin}"   # ★ makes captured ships immediately visible

                hull_hp  = s.get("hull_hp")
                hull_pct = s.get("hull_pct")
                max_hull = s.get("max_hull")

                if hull_pct is not None and hull_pct >= 99.9 and max_hull:
                    hp_str = f"Full  ({max_hull:,} HP)"
                elif hull_pct is not None and hull_pct >= 99.9:
                    hp_str = "Full"
                elif hull_pct is not None:
                    hp_str = f"{hull_pct:.1f}%  ({hull_hp:,.0f} / {max_hull:,} HP)"
                elif hull_hp is not None:
                    hp_str = f"{hull_hp:,.0f} HP"
                else:
                    hp_str = "Full"

                shield_hp  = s.get("shield_hp")
                shield_pct = s.get("shield_pct")
                shield_max = s.get("shield_max")

                if shield_pct is not None and shield_pct >= 99.9 and shield_max:
                    shield_str = f"Full  ({shield_max:,.0f} HP)"
                elif shield_pct is not None and shield_pct >= 99.9:
                    shield_str = "Full"
                elif shield_pct is not None:
                    shield_str = f"{shield_pct:.1f}%  ({shield_hp:,.0f} / {shield_max:,.0f} HP)"
                elif shield_hp is not None:
                    shield_str = f"{shield_hp:,.0f} HP"
                else:
                    shield_str = None  # no generators installed — omit entirely

                ship_line = (
                    f"  {connector} {display_name:<{name_col}} {s['size']:<4}  "
                    f"{s['role']:<16}  {s['order']:<22}  {hull_origin:<14}  {hp_str}"
                )
                if shield_str is not None:
                    ship_line += f"  ·  {BLUE}{shield_str}{RESET}"
                print(ship_line)

                # Pilot sub-line — only printed when a named pilot is assigned.
                # Skills shown as compact codes (Plt/Mgt/Eng/Mor) to stay
                # within the 68-character line width.
                pilot_name = s.get("pilot", {}).get("name")
                if pilot_name:
                    skills    = s.get("pilot", {}).get("skills", {})
                    skill_str = ""
                    if skills:
                        skill_str = (
                            f"  Plt:{skills.get('piloting',    0)}"
                            f"  Mgt:{skills.get('management',  0)}"
                            f"  Eng:{skills.get('engineering', 0)}"
                            f"  Mor:{skills.get('morale',      0)}"
                        )
                    print(f"  {indent}  ↳ {pilot_name}{skill_str}")

                # Crew count line — only shown when the ship carries service
                # crew or marines; skipped entirely for empty ships.
                sc = _ship_crew[s["code"]]["service"]
                mc = _ship_crew[s["code"]]["marine"]
                if sc or mc:
                    parts = []
                    if sc: parts.append(f"Service: {sc}")
                    if mc: parts.append(f"Marines: {mc}")
                    print(f"  {indent}  ↳ {' · '.join(parts)}")

        print()

    else:
        print("    No player ships detected.")
        print()

    # ── CREW ROSTER ───────────────────────────────────────────────────────────
    # Groups all player-owned crew by role. Within each group the primary skill
    # for that role is shown first so the most useful number is always visible
    # at a glance without scanning the whole line.
    # The crew roster is only shown when the stations pass ran — pilots are
    # already displayed inline in the fleet section, so the roster's purpose
    # is listing station managers alongside their assigned pilots.
    named_crew = [c for c in crew if c["role"] in ("manager", "pilot")]
    if data.get("stations_scanned") and named_crew:
        print(LINE)

        # Header summary includes all roles for a complete picture, even though
        # the table below only lists named crew (managers and pilots).
        role_counts = Counter(c["role"] for c in crew)
        summary_parts = []
        for role_key, label in (("manager","managers"), ("pilot","pilots"),
                                 ("service","service crew"), ("marine","marines")):
            if role_counts[role_key]:
                summary_parts.append(f"{role_counts[role_key]} {label}")
        summary = " · ".join(summary_parts)
        print(f"  CREW ROSTER  ({len(named_crew)} named — {summary})")
        print()

        # Column widths based only on named crew so generic service crew names
        # (e.g. "Service Crew #1") don't inflate the columns unnecessarily.
        name_col   = max((len(c["name"])        for c in named_crew), default=20)
        name_col   = max(20, min(30, name_col + 1))
        assign_col = max((len(f"{c['assigned_to']} [{c['assigned_code']}]") for c in named_crew), default=24)
        assign_col = max(24, min(36, assign_col + 1))

        print(f"    {'Name':<{name_col}} {'Role':<9}  {'Assigned To':<{assign_col}}  Skills")
        print(f"    {'─' * name_col} {'─' * 9}  {'─' * assign_col}  {'─' * 30}")

        ROLE_ORDER  = ["manager", "pilot"]
        ROLE_LABELS = {"manager": "Manager", "pilot": "Pilot"}
        ROLE_SKILLS = {
            "manager": ["management", "morale", "engineering"],
            "pilot":   ["piloting", "management", "engineering", "morale"],
        }
        SKILL_ABBREV = {
            "piloting": "Plt", "management": "Mgt", "engineering": "Eng",
            "morale": "Mor", "boarding": "Brd",
        }

        for role_key in ROLE_ORDER:
            group = [c for c in named_crew if c["role"] == role_key]
            if not group:
                continue
            for c in group:
                assign = f"{c['assigned_to']} [{c['assigned_code']}]"
                skills = c.get("skills", {})
                skill_str = "  ".join(
                    f"{SKILL_ABBREV[sk]}:{skills[sk]}"
                    for sk in ROLE_SKILLS[role_key]
                    if sk in skills
                )
                print(f"    {c['name']:<{name_col}} {ROLE_LABELS[role_key]:<9}  {assign:<{assign_col}}  {skill_str}")

        print()

    # ── NPC PRESENCE (tiers 2 / 3 only) ──────────────────────────────────────
    # Only printed when NPC ship data was actually collected. At tier 1 the
    # npc_ships list will be empty and this section is skipped entirely,
    # keeping the default output clean and fast.
    #
    # ROLE SUMMARY INSTEAD OF INDIVIDUAL SHIPS:
    # Sectors can contain hundreds of NPC ships. Listing each one would make
    # the output unreadable. Grouping by faction and summarising by role
    # (e.g. "3× Fighter, 2× Corvette") gives a useful threat picture without
    # flooding the console. The AI export (jsonexport.py) includes full
    # individual ship data for the AI to reason about in more detail.
    if npc_ships:
        # Two-level grouping: sector → faction → { role: count }
        # defaultdict of defaultdict(Counter) means we never need to
        # check if a key exists before incrementing — it auto-initialises.
        by_sector: dict[str, dict[str, Counter]] = defaultdict(
            lambda: defaultdict(Counter)
        )
        for s in npc_ships:
            by_sector[s["sector"]][s["owner"]][s["role"]] += 1

        total_npc = len(npc_ships)
        print(LINE)
        print(f"  NPC PRESENCE IN MONITORED SECTORS  ({total_npc} ships detected)")
        print()
        print(f"    {'Sector / Faction':<38}  {'Total':>5}  Roles")
        print(f"    {'─' * 38}  {'─' * 5}  {'─' * 30}")

        for sector in sorted(by_sector):
            factions     = by_sector[sector]
            sector_total = sum(sum(roles.values()) for roles in factions.values())
            print(f"\n  ┌─ {sector}  ({sector_total} ships)")

            faction_list = sorted(factions.items())
            for fi, (faction, roles) in enumerate(faction_list):
                connector    = "└──" if fi == len(faction_list) - 1 else "├──"
                faction_name = _FACTION_NAMES.get(faction, faction.title())

                total = sum(roles.values())
                # Most common roles listed first, e.g. "3× Fighter, 1× Corvette"
                role_summary = ", ".join(
                    f"{count}× {role}" for role, count in roles.most_common()
                )
                print(f"  {connector} {faction_name:<36}  {total:>5}  {role_summary}")

        print()

    display_trade_log(data)
    display_in_progress_deliveries(data)
    display_trade_history(data)

    print(f"\n{SEP}")