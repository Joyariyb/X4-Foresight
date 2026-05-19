# scanner/scanner.py
# ─────────────────────────────────────────────────────────────────────────────
#  SCANNER COORDINATOR
#  Re-exports the public scanner functions so callers don't need to know which
#  sub-module each one lives in. Add new scanners here as the project grows.
# ─────────────────────────────────────────────────────────────────────────────

from scanner.station_scanner    import scan_save         # noqa: F401  Pass 1
from scanner.reputation_scanner import scan_reputation   # noqa: F401  Pass 2
# Pass 3 (scan_ships) is imported directly from scanner.ship_scanner by callers
# since it has a richer signature (tier flags, npc_only) that doesn't fit a
# simple re-export pattern cleanly.
