# Core role: Golden-file test — full pipeline into a temp SQLite DB, to_export(), compared against tests/golden/export.json.
from __future__ import annotations
import json
import os
from pathlib import Path

import pytest

from db.connection import get_connection
from db.write import write_scan
from export.jsonexport import to_export, resource_library_export

GOLDEN_PATH = Path(__file__).resolve().parent / 'golden' / 'export.json'

# Real-world wall-clock values differ on every run — never part of the golden.
# Stripped recursively: scanned_at appears both in meta and echoed inside the
# trends series' scan rows.
VOLATILE_KEYS = ('scanned_at',)

# Static data generated from game files (large, invariant across scans).
# Excluded from the golden so it stays a readable snapshot of what the SCAN
# produced; presence is asserted separately below. The equipment/hull catalogs
# are NOT in to_export() at all — they moved to resource_library_export(),
# which the bridges serve as a standalone call.
STATIC_SECTIONS = ('ware_prices',)


def _normalize(data: dict) -> dict:
    """Strip volatile/static parts and coerce to plain JSON types.

    The json round-trip matters: to_export() returns Python objects (tuples,
    ints-vs-floats) that must compare equal to what json.load() of the golden
    file yields, not just to each other.
    """
    data = json.loads(json.dumps(data, ensure_ascii=False))
    _strip_volatile(data)
    for key in STATIC_SECTIONS:
        data.pop(key, None)
    return data


def _strip_volatile(node) -> None:
    """Remove wall-clock keys wherever they occur (dicts nested in lists too)."""
    if isinstance(node, dict):
        for key in VOLATILE_KEYS:
            node.pop(key, None)
        for v in node.values():
            _strip_volatile(v)
    elif isinstance(node, list):
        for v in node:
            _strip_volatile(v)


def _first_diff(a, b, path='$'):
    """Path to the first structural difference — pytest's dict diff is unreadable
    at this size, so failures point at the exact key instead."""
    if type(a) is not type(b):
        return f'{path}: type {type(a).__name__} != {type(b).__name__}'
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a:
                return f'{path}.{k}: missing from actual'
            if k not in b:
                return f'{path}.{k}: missing from golden'
            d = _first_diff(a[k], b[k], f'{path}.{k}')
            if d:
                return d
        return None
    if isinstance(a, list):
        if len(a) != len(b):
            return f'{path}: length {len(a)} != {len(b)}'
        for i, (x, y) in enumerate(zip(a, b)):
            d = _first_diff(x, y, f'{path}[{i}]')
            if d:
                return d
        return None
    if a != b:
        return f'{path}: {a!r} != {b!r}'
    return None


@pytest.fixture(scope='module')
def export(ctx, tmp_path_factory):
    """to_export() result from a fresh throwaway DB holding exactly one scan."""
    db_path = tmp_path_factory.mktemp('db') / 'x4_test.db'
    conn = get_connection(db_path)
    try:
        scan_id = write_scan(conn, ctx)
        return to_export(conn, scan_id)
    finally:
        conn.close()


def test_static_sections_present(export):
    # Excluded from the golden, but their disappearance would still be a
    # pipeline regression (schema population happens at connection time).
    for key in STATIC_SECTIONS:
        assert export.get(key), f'{key} missing or empty in export'
    # The volatile field must exist before normalisation strips it.
    assert export['meta']['scanned_at']


def test_resource_library_catalogs():
    # The equipment/hull catalogs were split out of the scan export into a
    # standalone bridge call; losing either would blank the Resource Library tab.
    lib = resource_library_export()
    assert lib.get('equipment_catalog'), 'equipment_catalog missing or empty'
    assert lib.get('hull_catalog'), 'hull_catalog missing or empty'
    # Losing this one would blank the universe map's pre-scan interactive overlay.
    assert lib.get('sector_catalog'), 'sector_catalog missing or empty'


def test_export_matches_golden(export):
    actual = _normalize(export)

    if os.environ.get('UPDATE_GOLDEN') == '1':
        GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN_PATH.write_text(
            json.dumps(actual, indent=2, ensure_ascii=False) + '\n',
            encoding='utf-8',
        )

    assert GOLDEN_PATH.exists(), (
        f'{GOLDEN_PATH} missing — regenerate with UPDATE_GOLDEN=1 '
        '(see tests/README.md)'
    )
    golden = json.loads(GOLDEN_PATH.read_text(encoding='utf-8'))

    diff = _first_diff(actual, golden)
    assert diff is None, (
        f'export deviates from golden at {diff}\n'
        'If the change is intentional, regenerate with UPDATE_GOLDEN=1.'
    )
