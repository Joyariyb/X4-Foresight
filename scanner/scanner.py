# scanner/scanner.py
# ─────────────────────────────────────────────────────────────────────────────
#  SCANNER COORDINATOR
#  Re-exports the public scanner functions so callers don't need to know which
#  sub-module each one lives in. Add new scanners here as the project grows.
# ─────────────────────────────────────────────────────────────────────────────

from scanner.station_scanner     import scan_save              # noqa: F401  Pass 1 (+4 when collect_npc_stations=True)
from scanner.reputation_scanner  import scan_reputation        # noqa: F401  Pass 2
from scanner.combined_scanner    import scan_save_and_ships    # noqa: F401  Pass 1+3 combined — single file read
from scanner.trade_scanner          import scan_trade_orders          # noqa: F401  Pass 5 — active TradePerform orders
from scanner.economy_scanner        import scan_trade_history         # noqa: F401  Pass 6 — completed economylog entries
from scanner.trade_combined_scanner import scan_trade_log_and_history # noqa: F401  Pass 5+6 combined — single file read
# scan_ships and merge_station_docked_ships are imported directly from
# scanner.ship_scanner by callers — their richer signatures don't fit a
# simple re-export pattern cleanly.
#
# scan_npc_stations (npc_station_scanner.py) is no longer called by the main
# pipeline — NPC station collection is now built into scan_save() via the
# collect_npc_stations=True flag, which merges Passes 1 and 4 into one file read.
#
# scan_save_and_ships (combined_scanner.py) merges Passes 1 and 3 into a single
# file read — use it when both stations and ships are needed in the same run.
#
# scan_trade_log_and_history (trade_combined_scanner.py) merges Passes 5 and 6
# into a single file read — use it when both active orders and history are needed.
