# X4 Foresight

**A free, browser-based save-file scanner and Empire Intelligence dashboard for [X4: Foundations](https://www.egosoft.com/games/x4/info_en.php).**

Load an X4 save and get an instant read on your whole empire — fleet readiness, station economy, the sector map, crew, and incoming Xenon threats. No install, no upload: the scan runs entirely in your browser.

### ▶ [Launch the dashboard →](https://joyariyb.github.io/X4-Foresight/)

> 🔒 **Private by design.** Your save file is read and processed locally in your browser (Python via [Pyodide](https://pyodide.org/) in a Web Worker). It is never uploaded to any server.

---

## What it shows

| Tab | What you get |
|-----|--------------|
| **Overview** | Empire snapshot — pilot, holdings, net worth at a glance |
| **Naval / Fleet** | Every ship by class & role, hull designs, equipment and loadouts |
| **Economy** | Station production, cashflow and trade |
| **Universe** | Interactive sector map of your assets |
| **Alerts** | Hostile NPC ships (incl. Xenon fleets) in your station sectors |
| **JSON Exports** | Resolved data as JSON for spreadsheets or your own tooling |

X4 Foresight is **read-only** — it visualizes your save, it never modifies it.

## How it works

1. **Find your save.** X4: Foundations stores saves as `.xml.gz` files in your Egosoft documents folder.
2. **Load it** into the [web dashboard](https://joyariyb.github.io/X4-Foresight/). The scanner runs in-browser.
3. **Read your empire** across the Overview, Naval, Universe and Alerts tabs — or export JSON.

The core pipeline is **scan → resolve → DB → JSON**, runnable on the desktop via `x4_save_scanner.py` or in the browser via the same Python code under Pyodide.

## Run locally (desktop build)

There is also a desktop build (PyQt + QtWebEngine) if you prefer to run it natively:

```bash
python X4_Empire_Intelligence.pyw
# or run just the pipeline:
python x4_save_scanner.py
```

## Project layout

| Path | Purpose |
|------|---------|
| `scanner/` | Streaming save-file parser |
| `db/` | Builds the in-memory database from resolved data |
| `export/` | JSON export (`jsonexport.py`) |
| `ui/` | Dashboard front-end (shared between desktop and web builds) |
| `ui/web/` | Web build entry point (Pyodide + Web Worker) |
| `index.html` | Landing page served by GitHub Pages |

See [`TODO.md`](TODO.md) for deferred work and the roadmap.

## Contributing

Issues and pull requests welcome.

---

*Not affiliated with or endorsed by Egosoft. X4: Foundations is a trademark of Egosoft GmbH.*
