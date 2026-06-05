"""
v2/display.py — colored console intelligence report.

Renders a populated ScanContext to the terminal, matching v1's layout (sector-
grouped tree, reputation bars, dynamic columns) and improving the colour:

  - hull / shield graded green→yellow→red by health
  - reputation bars tinted by standing
  - HOSTILE factions (Xenon/Kha'ak, and anyone you're at war with) flagged RED
    in the threat panel
  - trade counterparties tinted by provenance (proven green / inferred yellow /
    unknown grey)

COLOUR + ALIGNMENT RULE: ANSI escape codes have zero display width but DO count
as characters in f-string padding. So we always PAD the visible text first, then
wrap colour around the finished cell — never pad an already-coloured string.
"""
from __future__ import annotations
import os
import sys
from collections import Counter, defaultdict

from scanner.ship_names import ship_display_name
from data.wares import WARE_NAMES
from data.production import (
    display_name_to_id, units_per_cycle, units_per_hour,
    inputs_per_cycle, runtime_minutes,
)


# ── ANSI colour (ported from v1, expanded) ─────────────────────────────────────

def _enable_ansi() -> bool:
    if not sys.stdout.isatty():
        return False
    if os.name == 'nt':
        try:
            import ctypes
            k = ctypes.windll.kernel32
            k.SetConsoleMode(k.GetStdHandle(-11), 7)  # enable VT processing
        except Exception:
            return False
    return True


_ANSI = _enable_ansi()


def _c(code: str) -> str:
    return code if _ANSI else ''


RESET   = _c('\033[0m')
BOLD    = _c('\033[1m')
DIM     = _c('\033[2m')
RED     = _c('\033[91m')
GREEN   = _c('\033[92m')
YELLOW  = _c('\033[93m')
BLUE    = _c('\033[94m')
MAGENTA = _c('\033[95m')
CYAN    = _c('\033[96m')
GREY    = _c('\033[90m')

# Factions that are hostile to everyone — always a threat regardless of rep.
_ALWAYS_HOSTILE = {'xenon', 'khaak', 'kha\'ak'}


def paint(text: str, color: str) -> str:
    """Wrap already-padded text in a colour (no-op when colour is disabled)."""
    return f"{color}{text}{RESET}" if color and _ANSI else text


# ── small formatters ───────────────────────────────────────────────────────────

def _credits(n) -> str:
    return f"{n:,} Cr" if isinstance(n, (int, float)) else f"{n} Cr"


def _m3(v) -> str:
    if v is None:
        return "—"
    if v >= 1_000_000:
        return f"{v/1_000_000:.1f}M m³"
    if v >= 1_000:
        return f"{v/1_000:.1f}k m³"
    return f"{v:.0f} m³"


def _ago(s: float) -> str:
    s = int(s)
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s//60}m"
    return f"{s//3600}h {(s%3600)//60:02d}m"


def _game_clock(s: float) -> str:
    h = int(s // 3600)
    return f"{h}h {int((s % 3600)//60):02d}m"


def _health_color(pct):
    if pct is None:
        return ''
    if pct >= 66:
        return GREEN
    if pct >= 33:
        return YELLOW
    return RED


def _health_str(pct, hp, mx) -> str:
    """Colour-graded 'NN%  (hp / max)' or 'Full' / '—'."""
    if pct is None:
        return paint("—", GREY)
    if pct >= 99.9:
        body = f"Full ({mx:,.0f})" if mx else "Full"
        return paint(body, GREEN)
    body = f"{pct:.0f}%"
    if hp is not None and mx:
        body += f" ({hp:,.0f}/{mx:,.0f})"
    return paint(body, _health_color(pct))


def _runtime(mins) -> tuple[str, str]:
    """Return (text, colour) for input-stock runtime — red when running low."""
    if mins is None:
        return '', ''
    if mins <= 0:
        return 'no stock', RED
    txt = f'{mins:.0f}m stock' if mins < 60 else f'{int(mins//60)}h {int(mins%60):02d}m stock'
    color = RED if mins < 30 else YELLOW if mins < 120 else GREY
    return txt, color


def _wrap(items: list[str], width: int) -> list[str]:
    """Wrap a comma-joined list of items to lines no wider than `width`."""
    lines: list[str] = []
    cur = ""
    for it in items:
        chunk = it + ", "
        if cur and len(cur) + len(chunk) > width:
            lines.append(cur.rstrip(", "))
            cur = chunk
        else:
            cur += chunk
    if cur:
        lines.append(cur.rstrip(", "))
    return lines or [""]


# ── section: header ─────────────────────────────────────────────────────────────

SEP  = "═" * 78
LINE = "─" * 78


def _header(ctx) -> None:
    print()
    print(paint(SEP, CYAN))
    print(paint(f"  {BOLD}X4 FORESIGHT v2 — EMPIRE INTELLIGENCE", CYAN))
    print(paint(SEP, CYAN))
    print(f"  Pilot    : {BOLD}{ctx.player_name or 'Unknown'}{RESET}")
    print(f"  Sector   : {ctx.player_sector or 'Unknown'}")
    print(f"  Credits  : {paint(_credits(ctx.player_credits), GREEN)}")
    print(f"  {DIM}Save {ctx.save_file}  ·  game clock {_game_clock(ctx.game_time_s)}{RESET}")


# ── section: stations ───────────────────────────────────────────────────────────

def _stations(ctx, sector_name: dict) -> None:
    print("\n" + LINE)
    print(f"  {BOLD}OWNED STATIONS{RESET}  ({len(ctx.stations)})")

    # Sunlight per sector (drives energy-cell output + shown in the header).
    sector_sun = {s.sector_name: s.sunlight for s in ctx.sectors}

    # Docked-ship counts per station id, from every ship whose docked_at is set
    # (own = player, visiting = civilian/NPC parked at our station).
    docked: dict[str, dict] = defaultdict(lambda: {'own': 0, 'visiting': 0})
    for sh in ctx.ships:
        if sh.docked_at:
            docked[sh.docked_at]['own' if sh.owner_id == 'player' else 'visiting'] += 1

    by_sector: dict[str, list] = defaultdict(list)
    for s in ctx.stations:
        by_sector[sector_name.get(s.sector_macro, s.sector_macro)].append(s)

    for sector, stations in by_sector.items():
        sun = sector_sun.get(sector)
        sun_str = f"  ·  {paint(f'{sun*100:.0f}% sun', YELLOW)}" if sun else ""
        print(f"\n  {paint('┌─ ' + sector, CYAN)}{sun_str}  ({len(stations)})")
        for i, s in enumerate(stations):
            last = i == len(stations) - 1
            conn = "└──" if last else "├──"
            ind  = "      " if last else "│     "
            status = '' if s.status == 'Operational' else paint(f"  ·  {s.status}", YELLOW)
            print(f"  {conn} {BOLD}{s.name}{RESET} [{s.code}]  ·  {s.module_count} mods{status}")

            # ── Production: per ware, with rate / inputs / stock runtime ──────
            # runtime_minutes() keys inventory by DISPLAY name; our store is keyed
            # by ware_id, so convert once per station before the loop.
            inv_by_name = {WARE_NAMES.get(w, w): a for w, a in s.inventory.items()}
            prod = Counter(m.produces for m in s.modules if m.produces)
            for idx, (ware, count) in enumerate(sorted(prod.items())):
                lbl = 'Produces' if idx == 0 else '        '
                wid = display_name_to_id(ware)
                if wid:
                    pc = count * units_per_cycle(wid, sector)
                    ph = count * units_per_hour(wid, sector)
                    rt, rtc = _runtime(runtime_minutes(wid, count, inv_by_name))
                    rt_str = f"  ·  {paint(rt, rtc)}" if rt else ""
                    print(f"  {ind} {lbl} : {paint(f'{ware:<22}', CYAN)} {count}x  "
                          f"{pc:>5.0f}/cyc · {ph:>7,.0f}/hr{rt_str}")
                    inps = inputs_per_cycle(wid, count)
                    if inps:
                        istr = "  ·  ".join(f"{q:,} {n}" for n, q in sorted(inps.items()))
                        print(f"  {ind}            {DIM}└ needs {istr}{RESET}")
                else:
                    print(f"  {ind} {lbl} : {count}x {ware}")

            # ── Hull / shield ────────────────────────────────────────────────
            print(f"  {ind} Hull     : {_health_str(s.hull_pct, s.hull_hp, s.hull_max)}"
                  f"   Shield : {_health_str(s.shield_pct, s.shield_hp, s.shield_max)}")

            # ── Storage: per type, then total ────────────────────────────────
            for label, cs in (('Container', s.cargo_container),
                              ('Solid', s.cargo_solid), ('Liquid', s.cargo_liquid)):
                if cs is not None:
                    pct = cs.adj_pct if cs.adj_pct is not None else cs.pct
                    print(f"  {ind} {label:<9}: {_m3(cs.m3)} / {_m3(cs.max_m3)}  ({pct:.0f}%)")
            if s.cargo_total:
                ct = s.cargo_total
                pct = ct.adj_pct if ct.adj_pct is not None else ct.pct
                col = RED if (pct or 0) >= 90 else YELLOW if (pct or 0) >= 70 else ''
                print(f"  {ind} {'Storage':<9}: {_m3(ct.m3)} / {_m3(ct.max_m3)}  "
                      f"({paint(f'{pct:.0f}%', col)}) {DIM}[total]{RESET}")

            # ── Inventory: all, wrapped 4 per row ────────────────────────────
            if s.inventory:
                items = sorted(s.inventory.items(), key=lambda x: -x[1])
                for r0 in range(0, len(items), 4):
                    row = items[r0:r0 + 4]
                    lbl = 'Inventory' if r0 == 0 else '         '
                    content = "  ·  ".join(f"{a:,} {w}" for w, a in row)
                    print(f"  {ind} {DIM}{lbl}: {content}{RESET}")

            # ── Docked ships ─────────────────────────────────────────────────
            d = docked.get(s.object_id)
            if d and (d['own'] or d['visiting']):
                parts = []
                if d['own']:      parts.append(f"{d['own']} own")
                if d['visiting']: parts.append(f"{d['visiting']} visiting")
                print(f"  {ind} Docked   : {d['own'] + d['visiting']} ({' · '.join(parts)})")

            # ── Account / budget ─────────────────────────────────────────────
            if s.account_amount is not None:
                acct = paint(_credits(s.account_amount), GREEN)
                budget = f"  ·  budget {s.budget_total:,.0f} Cr" if s.budget_total else ""
                print(f"  {ind} Account  : {acct}{DIM}{budget}{RESET}")


# ── section: NPC stations in your sectors ───────────────────────────────────────

def _npc_stations(ctx, sector_name: dict) -> None:
    pstn_sectors = {s.sector_macro for s in ctx.stations if s.sector_macro}
    npc = [n for n in ctx.npc_stations if n.sector_macro in pstn_sectors]
    if not npc:
        return

    rep = {r.faction_id: r.value for r in ctx.reputation}

    def hostile(owner_id: str) -> bool:
        return owner_id in _ALWAYS_HOSTILE or rep.get(owner_id, 0) <= -10

    print("\n" + LINE)
    print(f"  {BOLD}NPC STATIONS — YOUR SECTORS{RESET}  ({len(npc)})")

    by_sector: dict[str, list] = defaultdict(list)
    for n in npc:
        by_sector[sector_name.get(n.sector_macro, n.sector_macro)].append(n)

    for sector, stations in by_sector.items():
        print(f"\n  {paint('┌─ ' + sector, CYAN)}  ({len(stations)})")
        stations.sort(key=lambda n: (n.owner_name, n.name))
        for i, n in enumerate(stations):
            last = i == len(stations) - 1
            conn = "└──" if last else "├──"
            ind  = "      " if last else "│     "
            mark = paint("● ", RED) if hostile(n.owner_id) else ""
            name = paint(n.name, RED) if hostile(n.owner_id) else f"{BOLD}{n.name}{RESET}"
            print(f"  {conn} {mark}{name}")
            if n.wares:
                wares = _wrap([WARE_NAMES.get(w, w.replace('_', ' ').title())
                               for w in n.wares], 62)
                print(f"  {ind} {DIM}Trades : {wares[0]}{RESET}")
                for extra in wares[1:]:
                    print(f"  {ind} {DIM}         {extra}{RESET}")


# ── section: reputation ─────────────────────────────────────────────────────────

def _rep_color(value: float) -> str:
    if value >= 20:
        return GREEN
    if value >= 0:
        return CYAN
    if value > -10:
        return YELLOW
    return RED


def _reputation(ctx) -> None:
    print("\n" + LINE)
    print(f"  {BOLD}FACTION REPUTATION{RESET}  ({len(ctx.reputation)})"
          f"   {DIM}[ -30 ◄ hostile · neutral · friendly ► +30 ]{RESET}")
    print()
    print(f"    {'Faction':<34} {'Std':>6}  {'':22}  {'Tier':<10}  {'Base':>6} {'Boost':>6}")
    print(f"    {'─'*34} {'─'*6}  {'─'*22}  {'─'*10}  {'─'*6} {'─'*6}")
    for r in ctx.reputation:
        fill = max(0, min(20, int((r.value + 30) / 60 * 20)))
        bar  = paint("█" * fill, _rep_color(r.value)) + paint("░" * (20 - fill), GREY)
        val  = paint(f"{r.value:>+6.2f}", _rep_color(r.value))
        boost = f"{r.booster:>+6.2f}" if r.booster else paint(f"{'—':>6}", GREY)
        print(f"    {r.faction_name:<34} {val}  [{bar}]  "
              f"{r.tier:<10}  {r.base:>+6.2f} {boost}")


# ── section: player fleet ───────────────────────────────────────────────────────

def _fleet(ctx, sector_name: dict) -> None:
    players = [s for s in ctx.ships if s.owner_id == 'player']
    print("\n" + LINE)
    print(f"  {BOLD}PLAYER FLEET{RESET}  ({len(players)})")

    # role/size summary line
    by_role = Counter(s.role for s in players)
    roles = "  ".join(f"{n}× {r}" for r, n in by_role.most_common(6))
    print(f"  {DIM}{roles}{RESET}")

    # crew counts per ship code
    crew_n: dict = defaultdict(lambda: {'service': 0, 'marine': 0})
    for c in ctx.crew:
        if c.role in ('service', 'marine'):
            crew_n[c.assigned_code][c.role] += 1

    by_sector: dict[str, list] = defaultdict(list)
    for s in players:
        by_sector[sector_name.get(s.sector_macro, s.sector_macro)].append(s)

    name_col = max((len(ship_display_name(s.macro, s.name)) for s in players), default=20)
    name_col = max(20, min(34, name_col + 1))

    for sector, ships in by_sector.items():
        print(f"\n  {paint('┌─ ' + sector, CYAN)}  ({len(ships)})")
        for i, s in enumerate(ships):
            last = i == len(ships) - 1
            conn = "└──" if last else "├──"
            ind  = "      " if last else "│     "
            name = ship_display_name(s.macro, s.name)
            hp   = _health_str(s.hull_pct, s.hull_hp, s.hull_max)
            sh   = _health_str(s.shield_pct, s.shield_hp, s.shield_max) if s.shield_pct is not None else ''
            line = (f"  {conn} {name:<{name_col}} {s.size:<3} {s.role:<16} "
                    f"{DIM}{s.order:<14}{RESET} {hp}")
            if sh:
                line += f" / {sh}"
            print(line)
            # pilot sub-line
            pilot = next((c for c in ctx.crew
                          if c.role == 'pilot' and c.assigned_code == s.code), None)
            if pilot:
                print(f"  {ind} {paint('↳', GREY)} {pilot.name}  "
                      f"{DIM}Plt:{pilot.skill_piloting} Mgt:{pilot.skill_management} "
                      f"Eng:{pilot.skill_engineering} Mor:{pilot.skill_morale}{RESET}")
            cc = crew_n[s.code]
            if cc['service'] or cc['marine']:
                parts = []
                if cc['service']: parts.append(f"Service {cc['service']}")
                if cc['marine']:  parts.append(f"Marines {cc['marine']}")
                print(f"  {ind} {paint('↳', GREY)} {DIM}{' · '.join(parts)}{RESET}")


# ── section: NPC threat presence ────────────────────────────────────────────────

def _npc_presence(ctx, sector_name: dict) -> None:
    pstn_sectors = {s.sector_macro for s in ctx.stations if s.sector_macro}
    npc = [s for s in ctx.ships
           if s.owner_id != 'player' and s.sector_macro in pstn_sectors]
    if not npc:
        return

    # rep lookup so factions you're at war with also flag red
    rep = {r.faction_id: r.value for r in ctx.reputation}

    def hostile(owner_id: str) -> bool:
        return owner_id in _ALWAYS_HOSTILE or rep.get(owner_id, 0) <= -10

    by_sector: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    owner_name: dict[str, str] = {}
    for s in npc:
        by_sector[sector_name.get(s.sector_macro, s.sector_macro)][s.owner_id][s.role] += 1
        owner_name[s.owner_id] = s.owner_name

    print("\n" + LINE)
    print(f"  {BOLD}NPC PRESENCE — YOUR STATION SECTORS{RESET}  ({len(npc)})"
          f"   {paint('● hostile', RED)}")

    for sector, factions in by_sector.items():
        tot = sum(sum(roles.values()) for roles in factions.values())
        print(f"\n  {paint('┌─ ' + sector, CYAN)}  ({tot} ships)")
        ordered = sorted(factions.items(), key=lambda x: -sum(x[1].values()))
        for fi, (owner_id, roles) in enumerate(ordered):
            conn = "└──" if fi == len(ordered) - 1 else "├──"
            n = sum(roles.values())
            summary = ", ".join(f"{c}× {r}" for r, c in roles.most_common(5))
            fac = owner_name.get(owner_id, owner_id)
            if hostile(owner_id):
                marker = paint("●", RED)
                fac = paint(fac, RED)
            else:
                marker = " "
            print(f"  {conn} {marker} {fac:<26} {n:>4}  {DIM}{summary}{RESET}")


# ── section: trade activity ─────────────────────────────────────────────────────

_PROVEN = {'direct', 'courier'}
_INFERRED = {'homebase', 'visit', 'sector', 'delivery'}


def _prov_paint(resolution: str, text: str) -> str:
    if resolution in _PROVEN:
        return paint(text, GREEN)
    if resolution in _INFERRED:
        return paint(text, YELLOW)
    return paint(text, GREY)


def _trades(ctx) -> None:
    th  = ctx.trade_history
    mining = ctx.trade_history_mining
    internal = ctx.trade_history_internal
    print("\n" + LINE)
    print(f"  {BOLD}TRADE ACTIVITY{RESET}")

    proven   = sum(1 for t in th if t.resolution in _PROVEN)
    inferred = sum(1 for t in th if t.resolution in _INFERRED)
    unknown  = len(th) - proven - inferred
    sold = sum(t.total_cr for t in th if t.direction == 'Out')
    bought = sum(t.total_cr for t in th if t.direction == 'In')
    print(f"  Commercial: {len(th):,}   "
          f"{paint(f'{proven} proven', GREEN)} · "
          f"{paint(f'{inferred} inferred', YELLOW)} · "
          f"{paint(f'{unknown} unknown', GREY)}")
    print(f"  Flow      : {paint('Sold ' + f'{sold:,.0f} Cr', GREEN)}  ·  "
          f"Bought {bought:,.0f} Cr")
    print(f"  {DIM}Also {len(mining):,} mining deliveries · {len(internal):,} internal transfers{RESET}")

    # ── Summary by station, broken out by direction and ware ─────────────────
    # station (code,name) -> direction -> ware -> [trades, units, total_cr]
    agg: dict = defaultdict(lambda: {'Out': defaultdict(lambda: [0, 0, 0.0]),
                                     'In':  defaultdict(lambda: [0, 0, 0.0])})
    for t in th:
        r = agg[(t.station_code, t.station_name)][t.direction][t.ware_name]
        r[0] += 1; r[1] += t.amount; r[2] += t.total_cr

    print(f"\n  {BOLD}── Summary by station ──{RESET}")
    for (code, name), dirs in sorted(
            agg.items(),
            key=lambda kv: -sum(v[2] for d in kv[1].values() for v in d.values())):
        out_cr = sum(v[2] for v in dirs['Out'].values())
        in_cr  = sum(v[2] for v in dirs['In'].values())
        print(f"\n  {paint('┌─ ' + name, CYAN)} [{code}]  ·  "
              f"{paint('Sold ' + f'{out_cr:,.0f}', GREEN)}  ·  Bought {in_cr:,.0f}")
        print(f"     {'Dir':<3} {'Ware':<20} {'Trades':>6} {'Units':>11} "
              f"{'Cr/u':>8} {'Total Cr':>14}")
        for d in ('Out', 'In'):
            dcol = GREEN if d == 'Out' else ''
            for ware, (n, units, total) in sorted(dirs[d].items(), key=lambda x: -x[1][2]):
                avg = total / units if units else 0
                print(f"     {paint(f'{d:<3}', dcol)} {ware[:20]:<20} {n:>6} "
                      f"{units:>11,} {avg:>8,.0f} {total:>14,.0f}")

    # ── Recent commercial trades (coloured by provenance) ────────────────────
    recent = sorted(th, key=lambda t: t.time_ago_s)[:15]
    if recent:
        print(f"\n  {BOLD}── Recent commercial trades ──{RESET}  "
              f"{DIM}counterparty: {paint('proven', GREEN)}/"
              f"{paint('inferred', YELLOW)}/{paint('unknown', GREY)}{RESET}")
        print(f"     {'Time':<7} {'Ship':<24} {'Dir':<3} {'Ware':<16} "
              f"{'Total Cr':>11}  Counterparty")
        for t in recent:
            ship = t.ship_name or t.ship_code or ''
            # Counterparty is the last column — print full, coloured by provenance.
            cp = _prov_paint(t.resolution, t.counterparty_name or '—')
            print(f"     {_ago(t.time_ago_s):<7} {ship[:24]:<24} {t.direction:<3} "
                  f"{t.ware_name[:16]:<16} {t.total_cr:>11,.0f}  {cp}")

    # ── Mining deliveries summary (raw resources → your stations) ────────────
    if mining:
        magg: dict = defaultdict(lambda: defaultdict(lambda: [0, 0.0]))
        for t in mining:
            r = magg[t.station_code][t.ware_name]
            r[0] += t.amount; r[1] += t.total_cr
        print(f"\n  {BOLD}── Mining deliveries (raw → your stations) ──{RESET}")
        for code, wares in sorted(magg.items()):
            parts = "  ·  ".join(
                f"{u:,} {w}" for w, (u, _) in
                sorted(wares.items(), key=lambda x: -x[1][0]))
            print(f"     {code:<10} {DIM}{parts}{RESET}")


# ── section: crew roster ─────────────────────────────────────────────────────────

def _crew(ctx) -> None:
    managers = [c for c in ctx.crew if c.role == 'manager']
    if not managers:
        return
    counts = Counter(c.role for c in ctx.crew)
    summary = " · ".join(f"{counts[k]} {lbl}" for k, lbl in
                         (('manager', 'managers'), ('pilot', 'pilots'),
                          ('service', 'service'), ('marine', 'marines')) if counts[k])
    print("\n" + LINE)
    print(f"  {BOLD}STATION MANAGERS{RESET}  ({DIM}{summary}{RESET})")
    print()
    print(f"    {'Manager':<28} {'Station':<10} Skills")
    print(f"    {'─'*28} {'─'*10} {'─'*24}")
    for m in managers:
        sk = f"Mgt:{m.skill_management} Mor:{m.skill_morale} Eng:{m.skill_engineering}"
        print(f"    {m.name[:28]:<28} {m.assigned_code:<10} {DIM}{sk}{RESET}")


# ── orchestrator ─────────────────────────────────────────────────────────────────

def display_report(ctx) -> None:
    """Print the full coloured intelligence report for a populated ScanContext."""
    sector_name = {s.sector_macro: s.sector_name for s in ctx.sectors}
    _header(ctx)
    _stations(ctx, sector_name)
    _npc_stations(ctx, sector_name)
    _reputation(ctx)
    _fleet(ctx, sector_name)
    _npc_presence(ctx, sector_name)
    _trades(ctx)
    _crew(ctx)
    print("\n" + paint(SEP, CYAN) + "\n")
