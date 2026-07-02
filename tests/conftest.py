# Core role: Shared pytest fixtures — run the scan pipeline once over the mini save and share the result.
from __future__ import annotations
import sys
from pathlib import Path

# The repo root must be importable before the scanner imports below run.
# pytest only guarantees the tests/ directory itself is on sys.path, and the
# scanner package assumes it is imported from the project root (data/, db/ ...).
TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest

from scanner.scanner import Scanner
from scanner.trade_postprocess import TradePostProcessor
from x4_save_scanner import resolve_ship_homebases

FIXTURES  = TESTS_DIR / 'fixtures'
MINI_SAVE = FIXTURES / 'mini_save.xml'
MINI_LANG = FIXTURES / 'mini_lang.xml'


@pytest.fixture(scope='session')
def pipeline():
    """(ctx, stats) after the full in-memory pipeline over the mini save.

    Session-scoped: the scan is deterministic and every test only reads from
    the result, so one parse serves the whole run. The DB/export golden test
    builds its own throwaway database from this same context.

    mini_lang.xml is passed explicitly because lang_path=None makes the scanner
    look for a real X4 installation — results would then differ between
    machines with and without the game installed.
    """
    ctx = Scanner(lang_path=MINI_LANG).scan(MINI_SAVE, scan_id=1)
    stats = TradePostProcessor().run(ctx)
    resolve_ship_homebases(ctx)
    return ctx, stats


@pytest.fixture(scope='session')
def ctx(pipeline):
    return pipeline[0]


@pytest.fixture(scope='session')
def trade_stats(pipeline):
    return pipeline[1]
