# scanner/scanner.py
# ─────────────────────────────────────────────────────────────────────────────
#  SCANNER COORDINATOR
#  Re-exports the public scanner functions so callers don't need to know which
#  sub-module each one lives in. Add new scanners here as the project grows.
# ─────────────────────────────────────────────────────────────────────────────

from scanner.station_scanner     import scan_save          # noqa: F401  Pass 1
from scanner.reputation_scanner  import scan_reputation    # noqa: F401  Pass 2
from scanner.npc_station_scanner import scan_npc_stations   # noqa: F401  Pass 4
# scan_ships and merge_station_docked_ships are imported directly from
# scanner.ship_scanner by callers — their richer signatures don't fit a
# simple re-export pattern cleanly.
