"""
v2 scanner smoke test.

Run from the v2/ directory:
    python test_scan.py

Or from the project root:
    python v2/test_scan.py
"""
import sys
import io
from pathlib import Path

# Force UTF-8 on Windows consoles (default cp1252 can't encode box-drawing chars).
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Make v2/ packages importable regardless of where the script is invoked from.
V2_DIR = Path(__file__).resolve().parent
if str(V2_DIR) not in sys.path:
    sys.path.insert(0, str(V2_DIR))

PROJECT_ROOT = V2_DIR.parent
SAVE_FILE    = PROJECT_ROOT / 'save_001.xml'
LANG_FILE    = PROJECT_ROOT / '0001-l044.xml'

from scanner.scanner import Scanner
from scanner.ship_names import resolve_ship_type as _resolve_type


def _bar(value: float, width: int = 20) -> str:
    """Simple ASCII fill bar for reputation / hull / shield display."""
    filled = round((value / 100.0) * width)
    return '[' + '█' * filled + '░' * (width - filled) + ']'


def main() -> None:
    try:
        _run()
    except Exception as e:
        import traceback
        print('\n' + '!' * 60)
        print('  ERROR')
        print('!' * 60)
        traceback.print_exc()
    finally:
        input('\nPress Enter to close...')


def _run() -> None:
    import time

    print('=' * 60)
    print('  X4 Foresight v2 — Scanner Smoke Test')
    print('=' * 60)
    print(f'  Save : {SAVE_FILE}  (exists={SAVE_FILE.exists()})')
    print(f'  Lang : {LANG_FILE}  (exists={LANG_FILE.exists()})')
    print()

    scanner = Scanner(lang_path=LANG_FILE)

    t_start = time.perf_counter()
    ctx     = scanner.scan(SAVE_FILE, scan_id=1)
    t_end   = time.perf_counter()
    elapsed = t_end - t_start

    # ── Game metadata ─────────────────────────────────────────────────────────
    print('── Game metadata ─────────────────────────────────────')
    print(f'  game_time_s  : {ctx.game_time_s:,.1f} s')
    print(f'  player_name  : {ctx.player_name!r}')
    print(f'  player_sector: {ctx.player_sector!r}')
    print(f'  player_credits: {ctx.player_credits:,} Cr')
    print()

    # ── Reputation ────────────────────────────────────────────────────────────
    print(f'── Reputation  ({len(ctx.reputation)} factions) ──────────────────')
    for r in ctx.reputation[:6]:
        sign = '+' if r.value >= 0 else ''
        print(f'  {r.faction_name:<38} {sign}{r.value:5.1f}  {r.tier}')
    if len(ctx.reputation) > 6:
        print(f'  ... and {len(ctx.reputation) - 6} more')
    print()

    # ── Sectors ───────────────────────────────────────────────────────────────
    print(f'── Sectors  ({len(ctx.sectors)} found) ───────────────────────────')
    for s in ctx.sectors[:5]:
        print(f'  {s.sector_name:<30}  owner={s.owner_id:<12}  sun={s.sunlight:.2f}')
    if len(ctx.sectors) > 5:
        print(f'  ... and {len(ctx.sectors) - 5} more')
    print()

    # ── NPC Stations ─────────────────────────────────────────────────────────
    print(f'── NPC Stations  ({len(ctx.npc_stations)} found) ─────────────────')
    for n in ctx.npc_stations[:5]:
        wares = ', '.join(n.wares[:3]) + ('...' if len(n.wares) > 3 else '')
        print(f'  {n.name:<45}  wares=[{wares}]')
    if len(ctx.npc_stations) > 5:
        print(f'  ... and {len(ctx.npc_stations) - 5} more')
    print()

    # ── Player Stations ───────────────────────────────────────────────────────
    print(f'── Player Stations  ({len(ctx.stations)} found) ──────────────────')
    for st in ctx.stations:
        hull_str  = f'hull={st.hull_pct:.0f}%'   if st.hull_pct  is not None else 'hull=N/A'
        shld_str  = f'shld={st.shield_pct:.0f}%' if st.shield_pct is not None else 'shld=none'
        cargo_str = (
            f'cargo={st.cargo_total.pct:.0f}%' if st.cargo_total else 'cargo=none'
        )
        print(
            f'  {st.name:<40}  [{st.status:<20}]  '
            f'mods={st.module_count:>3}  {hull_str}  {shld_str}  {cargo_str}'
        )
        if st.account_amount is not None:
            print(f'    account: {st.account_amount:>12,} Cr')
        if st.budget_total:
            print(f'    budget:  {st.budget_total:>12,.0f} Cr  (sunlight={st.budget_sunlight:.2f})')
        if st.inventory:
            top = sorted(st.inventory.items(), key=lambda x: -x[1])[:4]
            inv_str = '  '.join(f'{w}:{a:,}' for w, a in top)
            print(f'    inventory: {inv_str}')
    print()

    # ── Crew ──────────────────────────────────────────────────────────────────
    managers = [c for c in ctx.crew if c.role == 'manager']
    pilots   = [c for c in ctx.crew if c.role == 'pilot']
    service  = [c for c in ctx.crew if c.role == 'service']
    marines  = [c for c in ctx.crew if c.role == 'marine']
    print(f'── Crew  ({len(ctx.crew)} total) ──────────────────────────────')
    print(f'  managers={len(managers)}  pilots={len(pilots)}  service={len(service)}  marines={len(marines)}')
    for m in managers:
        print(
            f'  {m.name:<28}  → {m.assigned_code}  '
            f'mgmt={m.skill_management}  pilot={m.skill_piloting}  '
            f'eng={m.skill_engineering}  morale={m.skill_morale}'
        )
    print()

    # ── Ships ─────────────────────────────────────────────────────────────────
    player_ships = [s for s in ctx.ships if s.owner_id == 'player']
    npc_ships    = [s for s in ctx.ships if s.owner_id != 'player']
    print(f'── Ships  ({len(ctx.ships)} total: {len(player_ships)} player, {len(npc_ships)} NPC) ──')
    print(f'  player_ship_ids: {len(ctx.player_ship_ids)} registered')
    print(f'  homebase_index:  {len(ctx.homebase_index)} entries')
    print(f'  npc_ship_codes:  {len(ctx.npc_ship_codes)} entries')
    print()
    print('  Sample player ships:')
    for s in player_ships[:6]:
        hull_str  = f'hull={s.hull_pct:.0f}%' if s.hull_pct is not None else 'hull=N/A'
        shld_str  = f'shld={s.shield_pct:.0f}%' if s.shield_pct is not None else 'shld=none'
        hb_str    = f'hb={s.homebase_id}' if s.homebase_id else 'hb=none'
        print(
            f'  {(s.name or _resolve_type(s.macro)):<40}  [{s.order:<20}]  '
            f'{s.size}  {s.role:<18}  {hull_str}  {shld_str}  {hb_str}'
        )
    if len(player_ships) > 6:
        print(f'  ... and {len(player_ships) - 6} more')
    print()
    print('  Sample NPC ships (first 5):')
    for s in npc_ships[:5]:
        type_name = ctx.npc_ship_codes.get(s.code, s.macro)
        print(f'  {type_name:<40}  owner={s.owner_id:<12}  sector={s.sector_macro[:40]}')
    print()

    # ── Economy log (raw harvest) ──────────────────────────────────────────────
    pstn = set(ctx.player_station_ids)
    pshp = set(ctx.player_ship_ids)
    raw  = ctx.trade_log
    involves_pstn = sum(1 for r in raw if r['buyer'] in pstn or r['seller'] in pstn)
    involves_pshp = sum(1 for r in raw if r['buyer'] in pshp or r['seller'] in pshp)
    print(f'── Economy log  ({len(raw):,} raw trade rows) ─────────────────')
    print(f'  involve a player STATION : {involves_pstn:,}')
    print(f'  involve a player SHIP    : {involves_pshp:,}')
    print(f'  removed_codes harvested  : {len(ctx.removed_codes):,}')
    print(f'  homebase_index (ships)   : {len(ctx.homebase_index):,}')
    print(f'  delivery_dest_index      : {len(ctx.delivery_dest_index):,}  (ships mid-delivery)')
    if raw:
        print('  sample rows:')
        for r in raw[:3]:
            print(f'    {r["seller"]} -> {r["buyer"]}  {r["ware"]:<18} '
                  f'x{r["amount"]:<6} @{r["price_cr"]:.2f}Cr  ({r["time_ago_s"]:.0f}s ago)')
    print()

    # ── Trade history resolution ───────────────────────────────────────────────
    from scanner.trade_postprocess import TradePostProcessor
    pstats = TradePostProcessor().run(ctx)
    th  = ctx.trade_history
    thi = ctx.trade_history_internal
    resolved = sum(1 for t in th if t.counterparty_name)
    print(f'── Trade history  ({len(th):,} commercial, {len(thi):,} internal) ──')
    if th:
        print(f'  counterparty resolved : {resolved:,}/{len(th):,} '
              f'({resolved/len(th)*100:.1f}%)')
    print('  provenance breakdown:')
    for label, n in pstats.most_common():
        print(f'    {n:>5}  {label}')
    print('  sample commercial trades:')
    for t in th[:6]:
        cp = t.counterparty_name or '— UNRESOLVED —'
        print(f'    {t.station_code} {t.direction:<3} {t.ware_name:<16} x{t.amount:<5} '
              f'@{t.price_cr:7.2f}  via {t.ship_code:<10} -> {cp}')
    print()

    print('── player_station_ids ────────────────────────────────')
    print(f'  {len(ctx.player_station_ids)} ids registered: {list(ctx.player_station_ids)[:5]}')
    print()
    print(f'Completed in {elapsed:.2f}s')


if __name__ == '__main__':
    main()

