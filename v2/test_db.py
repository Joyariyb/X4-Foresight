"""
DB round-trip test: scan once, write twice.

Proves the three storage classes behave correctly:
  HISTORY   doubles (one row-set per scan)
  LEDGER    stays flat (same trades dedup by trade_key)
  REFERENCE stays flat (latest-only upsert)
"""
import sys, os
from pathlib import Path

V2_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(V2_DIR))
ROOT = V2_DIR.parent

from scanner.scanner import Scanner
from scanner.trade_postprocess import TradePostProcessor
from db.connection import get_connection
from db.write import write_scan


def count(conn, table):
    return conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()['n']


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

    id1 = write_scan(conn, ctx)
    snap1 = {t: count(conn, t) for t in (
        'scans', 'reputation', 'stations', 'ships', 'crew',
        'trade_history', 'trade_history_internal', 'sectors', 'npc_stations')}

    id2 = write_scan(conn, ctx)   # identical ctx again
    snap2 = {t: count(conn, t) for t in snap1}

    print(f"scan ids: {id1}, {id2}")
    print(f"{'table':<24}{'after 1':>9}{'after 2':>9}   class")
    classes = {
        'scans': 'history', 'reputation': 'history', 'stations': 'history',
        'ships': 'history', 'crew': 'history',
        'trade_history': 'LEDGER', 'trade_history_internal': 'LEDGER',
        'sectors': 'reference', 'npc_stations': 'reference',
    }
    for t in snap1:
        a, b = snap1[t], snap2[t]
        flag = ''
        if classes[t] == 'history' and b != a * 2:
            flag = '  <-- expected 2x!'
        if classes[t] in ('LEDGER', 'reference') and b != a:
            flag = '  <-- expected flat!'
        print(f"{t:<24}{a:>9,}{b:>9,}   {classes[t]}{flag}")

    # Spot-check provenance survived the round-trip
    prov = conn.execute(
        "SELECT resolution, COUNT(*) n FROM trade_history GROUP BY resolution "
        "ORDER BY n DESC").fetchall()
    print("\ntrade_history.resolution in DB:")
    for r in prov:
        print(f"  {r['n']:>5}  {r['resolution'] or '(unresolved)'}")

    conn.close()
    print("\nOK")


if __name__ == '__main__':
    main()
