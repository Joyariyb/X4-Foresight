# Design-sync notes — @x4-foresight/design-system

## Repo layout / how to run
- The DS package is a **subfolder** of the X4-Foresight repo: `design-system/`.
  Run ALL sync commands with that as cwd. Staged scripts live in
  `design-system/.ds-sync/`, config in `design-system/.design-sync/`.
- Build: `npm run build` (vite lib mode + tsc for .d.ts). Converter entry:
  `--entry ./dist/index.es.js --node-modules node_modules`.
- This library is a **hand-port** of the app UI (`ui/css/shared-ui.css` +
  `ui/css/base.css`). It does NOT auto-track the app — if those CSS files change
  upstream, the port must be updated by hand and rebuilt.

## Deliberate decisions
- Component CSS is authored in **px at the app's 10px rem-anchor** (1rem→10px) so
  the library is self-contained and doesn't depend on the host doc's root
  font-size. Token shape values (`--radius-*`) likewise px.
- Class names are namespaced `x4-` (they ship in the global styles.css every
  design receives; bare `.card`/`.badge` would collide with the agent's markup).
- The Tabler icon woff2 is **inlined as a base64 data-URI** in the bundled CSS
  (Vite lib mode inlines it). This is intentional/good: fully self-contained, no
  font-path resolution, icons never box-fallback. Only a curated ~20-glyph subset
  ships (see `src/styles/icons.css`) — add a rule there for a new icon.
- Barlow / Barlow Condensed / Share Tech Mono load via a Google Fonts `@import`
  in `src/styles/fonts.css`.

## Known render warns (triaged — not new on re-sync)
- `[FONT_REMOTE] "Barlow", "Barlow Condensed", "Share Tech Mono"` — expected; the
  Google Fonts `@import` serves them at runtime. Not a `[FONT_MISSING]`.
- 5 components are `cardMode: column` overrides (DataTable, Panel, Alert,
  SectionHeader, SummaryCard) — their wide stories overflow a grid cell otherwise.

## Bug fixed during this sync
- `ProgressBar` fill (`.x4-bar`) is a `<span>` — inline by default, which silently
  ignores `width`/`height` (bar collapsed to 0, looked like an empty dark track).
  Fixed with `display: block` on `.x4-bar`. Watch for the same trap on any future
  bar/fill element built as a span.

## Re-sync risks / what to watch
- **Upload was never done** in the first run: this environment had no Claude
  Design authorization (`/design-login` unavailable). The validated bundle is at
  `design-system/ds-bundle/`, ready to upload. `config.json` has **no projectId**
  yet — the first authorized sync must create/pick the project and record it.
- Grades + verification state are local (`.design-sync/.cache/`, gitignored) and
  were NOT anchored by an upload, so the first authorized sync re-verifies. That's
  expected and safe.
- The Google-Fonts `@import` is a network dependency at design render time.
