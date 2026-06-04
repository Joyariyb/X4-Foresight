"""
Visual trade report — see how each completed trade was categorized.

Prints a per-station confidence summary + recent trades to the console, and
writes the FULL report (every trade, every station) to v2/trade_report.txt.

Source column legend:
  [v] proven   — direct station↔station, or player-courier BUY/SELL legs paired
  [~] inferred — homebase / visit / sector / delivery (best-effort guess)
  [?] unknown  — counterparty genuinely not recoverable from the save
"""
import sys
from pathlib import Path
from collections import defaultdict, Counter

V2_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(V2_DIR))
ROOT = V2_DIR.parent

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from scanner.scanner import Scanner
from scanner.trade_postprocess import TradePostProcessor

PROVEN = {'direct', 'courier'}
INFERRED = {'homebase', 'visit', 'sector', 'delivery'}


def fmt_time(s: float) -> str:
    s = int(s); h = s // 3600; m = (s % 3600) // 60
    return f'{h}h {m:02d}m' if h else f'{m}m'


def source_label(res: str) -> str:
    if res in PROVEN:   return f'[v] proven ({res})'
    if res in INFERRED: return f'[~] infer ({res})'
    return '[?] unknown'


def ship_label(t) -> str:
    name = t.ship_name or t.ship_code or ''
    # Append the code (like v1) when it isn't already the name, so the row
    # identifies the specific hull: "Ides Vanguard [WNP-362]".
    if t.ship_code and t.ship_code != name:
        name = f'{name} [{t.ship_code}]'
    return name


def row_line(t) -> str:
    cp = (t.counterparty_name or '—')[:38]
    return (f'  {fmt_time(t.time_ago_s):<8}'
            f'{ship_label(t)[:32]:<33}{t.direction:<4}'
            f'{t.ware_name[:16]:<17}{t.amount:>7,}'
            f'{t.price_cr:>9.2f}{t.total_cr:>12,.0f}  '
            f'{cp:<40}{source_label(t.resolution)}')


def main():
    scanner = Scanner(lang_path=ROOT / '0001-l044.xml')
    ctx = scanner.scan(ROOT / 'save_001.xml', scan_id=1)
    TradePostProcessor().run(ctx)

    th = ctx.trade_history
    by_station = defaultdict(list)
    for t in th:
        by_station[(t.station_code, t.station_name)].append(t)
    for k in by_station:
        by_station[k].sort(key=lambda t: t.time_ago_s)

    def conf_counts(rows):
        c = Counter()
        for t in rows:
            c['proven' if t.resolution in PROVEN else
              'inferred' if t.resolution in INFERRED else 'unknown'] += 1
        return c

    header = (f"  {'Time':<8}{'Ship':<33}{'Dir':<4}{'Ware':<17}{'Units':>7}"
              f"{'Cr/u':>9}{'Total':>12}  {'Counterparty':<40}Source")
    rule = '  ' + '─' * 129

    # ── Build full report ──────────────────────────────────────────────────────
    full = []
    overall = conf_counts(th)
    full.append('=' * 128)
    full.append('  X4 FORESIGHT v2 — COMPLETED STATION TRADES (with categorization)')
    full.append('=' * 128)
    full.append(f"  {len(th):,} commercial trades   "
                f"proven={overall['proven']:,}  inferred={overall['inferred']:,}  "
                f"unknown={overall['unknown']:,}")
    by_method = Counter(t.resolution or 'unresolved' for t in th)
    full.append('  by method: ' + '  '.join(f'{k}={n}' for k, n in by_method.most_common()))
    full.append(f"  (also {len(ctx.trade_history_internal):,} internal transfers, "
                f"not shown here)")
    full.append('')

    for (code, name), rows in sorted(by_station.items(), key=lambda x: -len(x[1])):
        cc = conf_counts(rows)
        full.append('─' * 128)
        full.append(f"  {name}  ·  {len(rows)} trades   "
                    f"[v] {cc['proven']}   [~] {cc['inferred']}   [?] {cc['unknown']}")
        full.append(rule)
        full.append(header)
        full.append(rule)
        for t in rows:
            full.append(row_line(t))
        full.append('')

    # ── Write full report to file ──────────────────────────────────────────────
    out = V2_DIR / 'trade_report.txt'
    out.write_text('\n'.join(full), encoding='utf-8')

    # ── Console: summary + a sample per station ────────────────────────────────
    print('=' * 128)
    print('  COMPLETED STATION TRADES — categorization summary')
    print('=' * 128)
    print(f"  {len(th):,} commercial trades:   "
          f"[v] proven {overall['proven']:,}   "
          f"[~] inferred {overall['inferred']:,}   "
          f"[?] unknown {overall['unknown']:,}")
    print('  by method: ' + '  '.join(f'{k}={n}' for k, n in by_method.most_common()))
    print(f"  (separately: {len(ctx.trade_history_mining):,} mining deliveries, "
          f"{len(ctx.trade_history_internal):,} internal transfers — not commercial)")
    print()
    for (code, name), rows in sorted(by_station.items(), key=lambda x: -len(x[1])):
        cc = conf_counts(rows)
        print('─' * 128)
        print(f"  {name}  ·  {len(rows)} trades   "
              f"[v] {cc['proven']}   [~] {cc['inferred']}   [?] {cc['unknown']}   "
              f"(showing 12 most recent)")
        print(rule); print(header); print(rule)
        for t in rows[:12]:
            print(row_line(t))
        print()
    print(f"Full report ({len(th):,} rows) written to: {out}")


if __name__ == '__main__':
    main()
