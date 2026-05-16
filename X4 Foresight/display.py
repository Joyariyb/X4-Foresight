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
    Values scaled to match in-game display (-30 to +30 range, log10 curve).
    Shows Total (what the game UI displays), a visual bar, tier label,
    the permanent Base value, and any temporary Booster from missions.

    PLAYER FLEET:
    Ships grouped by sector, matching the station layout style. Each ship
    shows its display name (player-given or code fallback), size, role,
    current order, and hull origin. A pilot line is printed beneath each
    ship only when a named pilot is assigned, keeping output compact for
    large fleets. Captured ships (hull origin differs from standard player
    factions) are flagged with a ★ prefix.

    NPC PRESENCE (tiers 2 / 3 only):
    When NPC ship data was collected, a separate section groups enemy and
    neutral ships by sector and faction, summarising their composition by
    role count. This gives a quick threat and activity picture for sectors
    the player operates in.
    """
    SEP  = "═" * 68
    LINE = "─" * 68
    THIN = "·" * 68

    print(f"\n{SEP}")
    print("         X4 FOUNDATIONS — EMPIRE INTELLIGENCE REPORT v4.1")
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

                # Production line — indented to align under the station name.
                # Indent width matches the connector so text lines up cleanly.
                indent = "       " if i == len(stations) - 1 else "│      "
                if s["production"]:
                    print(f"  {indent} Produces : {s['production']}")
                else:
                    print(f"  {indent} Produces : —")

            print()  # Blank line between sector groups for breathing room

    else:
        print("    No player-owned stations detected.")

    print(LINE)

    # ── REPUTATION ────────────────────────────────────────────────────────────
    # Displayed as in-game values (log10 curve, range -30 to +30).
    # Base = permanent standing | Booster = temporary mission bonus.
    # Total = base + booster combined, matching what the in-game UI shows.
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

    print(f"  PLAYER FLEET  ({len(player_ships)} ships)")
    print()

    if player_ships:
        # Group by sector, preserving encounter order
        sectors_seen = {}   # { sector_name: [ship dicts] }
        for s in player_ships:
            sec = s["sector"]
            if sec not in sectors_seen:
                sectors_seen[sec] = []
            sectors_seen[sec].append(s)

        # Column headers — aligned to the data lines printed below
        print(f"    {'Ship / Pilot':<34} {'Size':<4}  {'Role':<16}  {'Order':<22}  {'Hull'}")
        print(f"    {'─' * 34} {'─' * 4}  {'─' * 16}  {'─' * 22}  {'─' * 12}")

        for sector, ships in sectors_seen.items():
            ship_word = "ship" if len(ships) == 1 else "ships"
            print(f"\n  ┌─ SECTOR: {sector}  ({len(ships)} {ship_word})")

            for i, s in enumerate(ships):
                # Corner piece on last ship, tee on all others — same as stations
                connector = "└──" if i == len(ships) - 1 else "├──"
                indent    = "       " if i == len(ships) - 1 else "│      "

                # Prefer player-given name; fall back to the ship code.
                # Most ships won't have a custom name so the code is the
                # primary identifier for the majority of the fleet.
                display_name = s["name"] if s["name"] else s["code"]

                # Flag non-standard hull origins (e.g. captured Xenon ships).
                # We check against factions players can normally buy ships from
                # — anything else is captured, gifted, or otherwise unusual.
                hull = s["hull_origin"]
                if hull.lower() not in ("argon", "teladi", "paranid", "split",
                                        "terran", "boron", "antigone"):
                    hull = f"★ {hull}"   # ★ makes captured ships immediately visible

                print(
                    f"  {connector} {display_name:<34} {s['size']:<4}  "
                    f"{s['role']:<16}  {s['order']:<22}  {hull}"
                )

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

        print()

    else:
        print("    No player ships detected.")
        print()

    # ── NPC PRESENCE (tiers 2 / 3 only) ──────────────────────────────────────
    # Only printed when NPC ship data was actually collected. At tier 1 the
    # npc_ships list will be empty and this section is skipped entirely,
    # keeping the default output clean and fast.
    #
    # WHY ROLE SUMMARY INSTEAD OF INDIVIDUAL SHIPS:
    # Sectors can contain hundreds of NPC ships. Listing each one would make
    # the output unreadable. Grouping by faction and summarising by role
    # (e.g. "3× Fighter, 2× Corvette") gives a useful threat picture without
    # flooding the console. The AI export (jsonexport.py) includes full
    # individual ship data for the AI to reason about in more detail.
    if npc_ships:
        from collections import defaultdict, Counter

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
                connector = "└──" if fi == len(faction_list) - 1 else "├──"

                total = sum(roles.values())
                # Most common roles listed first, e.g. "3× Fighter, 1× Corvette"
                role_summary = ", ".join(
                    f"{count}× {role}" for role, count in roles.most_common()
                )
                print(f"  {connector} {faction:<36}  {total:>5}  {role_summary}")

        print()

    print(f"\n{SEP}")