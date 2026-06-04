"""
Full pipeline test: scan -> write_scan (DB) -> write_export (JSON from DB).

Proves the DB-read export round-trips and shows the JSON shape + sizes.
"""
import sys, json
from pathlib import Path

V2_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(V2_DIR))
ROOT = V2_DIR.parent

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from scanner.scanner import Scanner
from scanner.trade_postprocess import TradePostProcessor
from db.connection import get_connection
from db.write import write_scan
from export.jsonexport import to_export, write_export


def main():
    scanner = Scanner(lang_path=ROOT / '0001-l044.xml')
    ctx = scanner.scan(ROOT / 'save_001.xml', scan_id=1)
    TradePostProcessor().run(ctx)

    db = V2_DIR / '_test.db'
    for ext in ('', '-wal', '-shm'):
        p = Path(str(db) + ext)
        if p.exists():
            p.unlink()
    conn = get_connection(db)
    scan_id = write_scan(conn, ctx)

    out = write_export(conn, ROOT / 'x4_empire_state.json')
    data = to_export(conn)

    print('=' * 70)
    print('  DB-READ EXPORT — pipeline: scan -> DB -> JSON')
    print('=' * 70)
    print(f"  written to: {out}")
    print(f"  file size : {out.stat().st_size / 1024:.0f} KB")
    print()
    print('  meta:', json.dumps(data['meta']))
    print('  player:', json.dumps(data['player']))
    print()
    print('  top-level keys & sizes:')
    for k, v in data.items():
        if isinstance(v, list):
            print(f"    {k:<24} list[{len(v)}]")
        elif isinstance(v, dict):
            print(f"    {k:<24} dict({len(v)} keys)")
    print()

    # Provenance distribution in the exported trades (the v2 addition)
    from collections import Counter
    res = Counter(t['resolution'] or 'unresolved' for t in data['station_trades'])
    print('  station_trades resolution tags:', dict(res.most_common()))
    print()
    print('  sample station_trade:')
    print('   ', json.dumps(data['station_trades'][0], ensure_ascii=False))
    print('  sample mining_delivery:')
    print('   ', json.dumps(data['mining_deliveries'][0], ensure_ascii=False))
    print('  sample station (trimmed):')
    s = dict(data['stations'][0])
    s['inventory'] = dict(list(s['inventory'].items())[:3])
    s['modules'] = f"[{len(s['modules'])} modules]"
    print('   ', json.dumps(s, ensure_ascii=False)[:300], '...')

    conn.close()
    print('\nOK')


if __name__ == '__main__':
    main()
