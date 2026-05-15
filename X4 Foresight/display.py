# ═════════════════════════════════════════════════════════════════════════════
#  SECTION 2 — HELPERS
# ═════════════════════════════════════════════════════════════════════════════

def format_credits(amount_str: str) -> str:
    """Formats a raw credit integer string into a comma-separated display value."""
    try:
        return f"{int(amount_str):,} Cr"
    except (ValueError, TypeError):
        return f"{amount_str} Cr"

# ═════════════════════════════════════════════════════════════════════════════
#  SECTION 5 — DISPLAY
# ═════════════════════════════════════════════════════════════════════════════

def display_results(data: dict):
    """
    Prints the extracted data to console in a readable format.

    STATION LAYOUT:
    Stations are grouped by sector so that multiple stations in the same
    location are visually clustered together. The sector is printed once
    as a header, with each station indented beneath it. Station name and
    code appear on the first line, production on the second.

    REPUTATION TABLE:
    Values scaled ×100 to match in-game display (-30 to +30 range).
    Shows Total (what the game UI displays), a visual bar, tier label,
    the permanent Base value, and any temporary Booster from missions.
    """
    SEP  = "═" * 68
    LINE = "─" * 68
    THIN = "·" * 68

    print(f"\n{SEP}")
    print("         X4 FOUNDATIONS — EMPIRE INTELLIGENCE REPORT v4.0")
    print(SEP)
    print(f"  PILOT          : {data['player_name'] or 'Unknown'}")
    print(f"  CURRENT SECTOR : {data['player_sector'] or 'Unknown'}")
    credits_str = format_credits(data['player_credits']) if data['player_credits'] else "Not found"
    print(f"  CREDITS        : {credits_str}")
    print(LINE)

    # ── STATIONS — grouped by sector ──────────────────────────────────────────
    # We build an ordered dict of { sector_name: [station, station, ...] }
    # preserving the order sectors are first encountered in the save file.
    print(f"  OWNED STATIONS  ({len(data['stations'])} total)")
    print()

    if data["stations"]:
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
            print(f"  ┌─ SECTOR: {sector}  ({len(stations)} {station_word})")

            for i, s in enumerate(stations):
                # Use corner piece on last station, tee on others
                connector = "└──" if i == len(stations) - 1 else "├──"

                # Station name line — name is the distinct header, code at the end
                print(f"  {connector} {s['name']} [{s['code']}]")

                # Production line — indented to align under the station name
                # Extra indent matches the connector width
                indent = "      " if i == len(stations) - 1 else "  │   "
                if s["production"]:
                    print(f"  {indent}  Produces : {s['production']}")
                else:
                    print(f"  {indent}  Produces : —")

            print()  # Blank line between sector groups for breathing room

    else:
        print("    No player-owned stations detected.")

    print(LINE)

    # ── REPUTATION ────────────────────────────────────────────────────────────
    # Displayed as in-game values (scaled ×100, range -30 to +30).
    # Base = permanent standing | Booster = temporary mission bonus from missions.
    # Total = base + booster, matching what the in-game UI shows.
    print(f"  FACTION REPUTATION  ({len(data['reputation'])} factions)"
          f"   [  -30 ◄ hostile · neutral · friendly ► +30  ]")
    print()
    print(f"    {'Faction':<32} {'Total':>6}  {'':22}  {'Tier':<10}  {'Base':>6}  {'Boost':>6}")
    print(f"    {'─'*32} {'─'*6}  {'─'*22}  {'─'*10}  {'─'*6}  {'─'*6}")

    if data["reputation"]:
        for r in data["reputation"]:
            # Scale -30..+30 onto a 20-character visual bar
            bar_val = int((r['value'] + 30) / 60 * 20)
            bar_val = max(0, min(20, bar_val))
            bar     = "█" * bar_val + "░" * (20 - bar_val)

            booster_str = f"{r['booster']:>+6.2f}" if r['booster'] != 0 else "     —"
            print(
                f"    {r['faction_name']:<32} {r['value']:>+6.2f}  [{bar}]  "
                f"{r['tier']:<10}  {r['base']:>+6.2f}  {booster_str}"
            )
    else:
        print("    No reputation data found.")

    print(f"\n{SEP}")