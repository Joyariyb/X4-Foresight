# X4 Foresight

A pipeline that scans X4 game/save files and exports data to a JSON-backed HTML UI.
The codebase at the repo root IS the program.

## Navigating this codebase — query the graph first

There is a prebuilt graphify knowledge graph in `graphify-out/` (`graphify-out/graph.json`).
It tracks relationships between symbols (calls, contains, shares_data_with) that a text
search can't see, and is faster and cheaper than reading files one at a time.

**Use graphify first to understand and search code connections** — not just for
open-ended exploration, but for any specific question too: "where is X used", "what
calls Y", "what else touches this state", "find every caller before removing this
parameter":

- `python -m graphify query "your question"` — find relevant nodes/edges
- `python -m graphify explain "SymbolName"` — a node's context and neighbours
- `python -m graphify path "A" "B"` — shortest path between two symbols

Grep is a fallback, not a first move — use it only for literal text the graph wouldn't
index (exact strings, CSS class names, comment wording), and ideally after graphify has
already narrowed down the likely files. Only open source files once the graph has
pointed you to the right place.

The graph can go stale: if `git rev-parse HEAD` doesn't match the commit recorded in
`graphify-out/GRAPH_REPORT.md`, refresh it with `python -m graphify update .`
(no API key needed). Update after merging a branch or finishing a chunk of work — not
mid-feature.

## Standards — read these before writing code

These are the authoritative rulebooks. Follow them; don't re-derive conventions.

- **[`COMMENT_STYLE.md`](COMMENT_STYLE.md)** — commenting standards. Comments explain
  *why*, not *what*; every code file opens with a one-line `Core role:` header. Covers
  Python, JavaScript, CSS, SQL, and HTML.
- **[`UI_STANDARDS.md`](UI_STANDARDS.md)** — the design rulebook for everything under
  `ui/`. Never type a colour, font, radius, duration, or coloured border as a literal —
  reference a token from `ui/css/base.css`. Covers token tiers, colour trios, type
  roles, shape, motion, and state layers.

## UI gotchas

- `ui/ui.html` renders in **QtWebEngine**. For drop shadows use the CSS
  `filter: drop-shadow(...)`, **not** SVG `<feDropShadow>` — the SVG filter silently
  fails to render in QtWebEngine. (Also in [`UI_STANDARDS.md`](UI_STANDARDS.md) §7.)

## Working style

- The maintainer is a junior programmer. Write comments that explain the *why* behind a
  decision, not just what the code does — see [`COMMENT_STYLE.md`](COMMENT_STYLE.md).
- Make changes in small, reviewable batches. Before removing a function parameter,
  query the graph (`python -m graphify explain "funcName"`) for all callers first.
- The maintainer handles their own git commits — don't commit unless asked.
