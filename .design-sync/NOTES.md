# Design Sync Notes — X4 Foresight Design System

## Setup

- Shape: `package` (no Storybook)
- Entry: `design-system/dist/index.es.js`
- Node modules: `design-system/node_modules`
- CSS: `design-system/dist/x4-foresight-ds.css` (single bundled stylesheet; Vite `cssCodeSplit: false`)
- Build command: `cd design-system && npm run build`
- Playwright installed into `.ds-sync/node_modules` for the render check

## Font handling

- Barlow / Barlow Condensed / Share Tech Mono: loaded from Google Fonts via `@import url(...)` in the compiled CSS. `[FONT_REMOTE]` — loads at runtime, no action needed.
- tabler-icons: embedded as a base64 data URI in `x4-foresight-ds.css`. No separate woff2 file to manage.

## cardMode overrides

- `DataTable`: `cardMode: "column"` — tables are wider than grid cells
- `Panel`: `cardMode: "column"` — same reason; wraps DataTable
- `X4Icon`: `cardMode: "column"` — CuratedSet grid overflows the multi-column card layout

## Known render warns

- `[FONT_REMOTE]` for Barlow families — expected, loads at runtime from Google Fonts

## Re-sync risks

- **Google Fonts**: the Barlow family load from the Google Fonts CDN at runtime. If the DS ever moves to self-hosted fonts, update `cssEntry` or `extraFonts` accordingly.
- **tabler-icons subset**: `design-system/src/styles/icons.css` is a curated subset (~20 glyphs). If new icons are added there, rebuild and re-sync — the X4Icon preview's `CuratedSet` story lists the set at sync time.
- **Preview content**: previews use hardcoded faction names, ware names, and credit values from the X4 universe. These are stable domain vocabulary, not live data.
- **Playwright version**: the Chromium binary in `C:\Users\lenovo\AppData\Local\ms-playwright\chromium-1228` must stay in sync with the playwright version in `.ds-sync/node_modules`. If you upgrade playwright, re-run `npx playwright install chromium` from `.ds-sync/`.
