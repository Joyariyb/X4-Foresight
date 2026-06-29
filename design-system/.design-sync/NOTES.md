# Design Sync Notes — X4 Foresight Design System

## Setup

- **Sync home is this package (`design-system/`)** — run all sync commands with
  `design-system/` as cwd. The config, staged scripts (`.ds-sync/`) and build
  output (`ds-bundle/`) all live under here. Linked Claude Design project:
  `93de3047-d0bc-4aac-ac06-034636d7ccf1` (window global `X4ForesightDS`).
- Shape: `package` (no Storybook)
- Entry: `./dist/index.es.js`
- Node modules: `node_modules`
- CSS: `dist/x4-foresight-ds.css` (single bundled stylesheet; Vite `cssCodeSplit: false`)
- Build command: `npm run build`
- Playwright installed into `.ds-sync/node_modules` for the render check

## Font handling

- Barlow (400/600), Barlow Condensed (600), Share Tech Mono (400): **self-hosted** as woff2 in `src/assets/fonts/`. Vite inlines them as base64 data URIs in `dist/x4-foresight-ds.css` at build time — they ship inside `_ds_bundle.css` and render correctly inside claude.ai/design's sandbox without a CDN.
- tabler-icons: embedded as a base64 data URI in `x4-foresight-ds.css`. No separate woff2 file to manage.
- Prior to 2026-06-29, Barlow and Share Tech Mono were loaded from Google Fonts (`@import url(...)`). The switch to self-hosted was made so the fonts render in the claude.ai/design sandbox (remote @import is not applied there).

## cardMode overrides

- `DataTable`: `cardMode: "column"` — tables are wider than grid cells
- `Panel`: `cardMode: "column"` — same reason; wraps DataTable
- `X4Icon`: `cardMode: "column"` — CuratedSet grid overflows the multi-column card layout

## Known render warns

(none — `[FONT_REMOTE]` for Barlow is resolved; fonts are now self-hosted)

## Re-sync risks

- **Self-hosted font woff2 files**: `src/assets/fonts/barlow-400.woff2`, `barlow-600.woff2`, `barlow-condensed-600.woff2`, `share-tech-mono-400.woff2`. If fonts are updated or new weights added, rebuild and re-sync. The woff2 files are checked into the repo (not gitignored).
- **tabler-icons subset**: `src/styles/icons.css` is a curated subset (~20 glyphs). If new icons are added there, rebuild and re-sync — the X4Icon preview's `CuratedSet` story lists the set at sync time.
- **Preview content**: previews use hardcoded faction names, ware names, and credit values from the X4 universe. These are stable domain vocabulary, not live data.
- **Playwright version**: the Chromium binary in `C:\Users\lenovo\AppData\Local\ms-playwright\chromium-1228` must stay in sync with the playwright version in `.ds-sync/node_modules`. If you upgrade playwright, re-run `npx playwright install chromium` from `.ds-sync/`.
