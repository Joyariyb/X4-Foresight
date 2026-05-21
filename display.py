import sys
import os
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

    print(f"\n{SEP}")