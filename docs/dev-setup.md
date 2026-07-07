# Development setup

## Prerequisites

- Python **3.12+** (the dev machine runs 3.14; CI tests 3.12 and 3.14)
- git
- Optional: an X4: Foundations install. The scanner reads the language file
  straight out of the game's `.cat` archives when present; without it, sector
  names don't resolve (see the warning the CLI prints). You can also drop a
  pre-extracted `0001-l044.xml` in the repo root.

## Install

```bash
pip install -e .[desktop,dev]   # everything: pipeline + PyQt6 UI + pytest
# or minimal, pipeline/CLI only:
pip install lxml
```

## Run

| What | How |
|------|-----|
| CLI scan (picker) | `python cli/x4_save_scanner.py` |
| CLI scan (direct) | `python cli/x4_save_scanner.py path\to\save_001.xml.gz` |
| Desktop UI | `python X4_Empire_Intelligence.pyw` (or `python ui/main_ui.py`) |
| Web build | any static file server from the **repo root**, then open `/ui/web/index.html` (GitHub Pages serves it the same way) |

The pipeline phases themselves live in `pipeline.py` — all three entry points
above are thin wrappers around `run_pipeline()`.

## Tests

```bash
python -m pytest tests/ -v
```

Sub-second, no game install or real save needed. Golden-file regeneration and
fixture anatomy: see [tests/README.md](../tests/README.md). CI runs the suite
on every push (`.github/workflows/tests.yml`).

## Things that bite

- **Adding/removing any `.py` file** → regenerate the web build's staging
  manifest: `python ui/web/generate_manifest.py`. Forgetting this breaks only
  the web build, silently.
- **Adding a JS file** → add it to `ui/js/shell-manifest.js` (one shared,
  order-sensitive list), never to the HTML shells directly.
- **UI work** → read [UI_STANDARDS.md](UI_STANDARDS.md) first (token tiers,
  §11 one-global-per-file rule); comments follow
  [COMMENT_STYLE.md](COMMENT_STYLE.md).
- **Navigating the code** → query the knowledge graph before grepping:
  `python -m graphify query "..."` / `explain "Symbol"` (see
  [CLAUDE.md](../CLAUDE.md)). Refresh after a chunk of work with
  `python -m graphify update .`.
- Save-file structure knowledge lives in [save-format.md](save-format.md) —
  append what you learn.
