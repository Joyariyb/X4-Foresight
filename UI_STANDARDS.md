# UI Standards

The design rulebook for everything under `ui/`. The single source of truth is
[`ui/css/base.css`](ui/css/base.css) — this document explains *how* to use the
tokens defined there. For comment formatting see [`COMMENT_STYLE.md`](COMMENT_STYLE.md).

## The one rule

**Never type a colour, font, radius, duration, or coloured border as a literal.
Reference a token.** If no token fits, add it to `base.css` first (see
[Adding a colour or theme](#adding-a-colour-or-theme)), then use it. A hand-typed
`#2dd4bf`, `rgba(45,212,191,0.3)`, `0.3rem`, or `0.15s` in a component file is a bug.

## 1. Token tiers

`base.css` defines tokens in two tiers. Components only ever touch the second one.

- **Palette** (raw values: `--teal`, `--bg-card`, `--red-line`, `--font-mono`) —
  the source of truth. Read **only** by `base.css` itself, to wire up the semantic
  tier. Never reference a palette token from `css/*.css` or `body.html`.
- **Semantic** (intent names: `--color-primary`, `--surface-2`,
  `--color-negative-line`, `--font-data`) — what every component uses.

Why: a component that says `--color-primary` keeps working if the brand colour
changes or a second theme is added. A component that says `--teal` does not.

## 2. Colour

**Surfaces — by elevation:**
- `--surface-0` — app background (deepest)
- `--surface-1` — panels, toolbars
- `--surface-2` — raised cards
- `--outline` — every 1px border and divider

**Text — by hierarchy:**
- `--text-primary` — body copy and stat values
- `--text-secondary` — muted / secondary text
- `--text-label` — structural micro-labels (section titles, field labels).
  Intentionally **brand green**, not grey — this is the house look.
- `--text-brand` — brand-green accent text (`--text-faint` is the older raw
  alias for the same green — also not grey despite the name; prefer
  `--text-brand`/`--text-label` in new code)

**Semantic feedback — always a trio:** each meaning ships as solid /
`-dim` (~0.1 alpha fill) / `-line` (0.3 alpha border). Use the three together for a
tinted callout (e.g. a warning chip = `--color-warning` text on
`--color-warning-dim` fill with a `--color-warning-line` border). Meanings:
`primary`, `positive`, `warning`, `negative`, `alert`, `special`, `highlight`.

- Never hand-type `rgba(...)` for a coloured border — the `-line` tokens are locked
  at 0.3 alpha so borders can't drift across components.
- Green is overloaded **by design** (`--color-positive` shares its hex with
  `--text-label`). That's accepted — just don't invent a third green.
- Avoid grey as a primary accent; lean on the brand palette (green is ubiquitous).

## 3. Type — choose by role, not by taste

- `--font-body` (Barlow) — sentences, prose, paragraph copy.
- `--font-label` (Barlow Condensed) — structural labels: section titles, panel
  heads, tab chips, card field-labels. Usually uppercase + letter-spaced.
- `--font-data` (Share Tech Mono) — data: stat values, table cells and headers,
  codes, coordinates, anything tabular or numeric.

Quick test: a *label for* a thing → `--font-label`; the thing's *data* →
`--font-data`; reads like a *sentence* → `--font-body`.

**Sizing:** `html` is pinned to `10px` as the rem anchor — never make it rem and
never override it (`js/init.js`'s `updateScale()` multiplies it for responsive
scaling). Size everything else in **rem** so it scales; a px size opts that element
out of responsive scaling.

> SVG note: inside a `viewBox` SVG, set text size with the bare `font-size="N"`
> attribute, not CSS rem — the viewBox transform already scales it, so rem
> double-scales.

## 4. Shape (radius) — by component size

- `--radius-sm` (0.2rem) — badges, chips, bars, tiny indicators
- `--radius-md` (0.3rem) — cards, panels, inputs, menus (default when unsure)
- `--radius-lg` (0.4rem) — large builder boxes, big dropdown surfaces

No raw rem radii in components.

## 5. Motion — two durations, one curve

- `--duration-short` (150ms) — hovers, focus, toggles, small flips
- `--duration-medium` (250ms) — expands/collapses, panel and menu reveals
- `--ease-standard` — the easing curve for **every** transition

No bare `0.15s`, no per-element curves.

## 6. State layers — translucent overlays, not solid swaps

- `--state-hover` (translucent white)
- `--state-focus` (translucent brand)
- `--state-active` (stronger brand)

Apply these as a background layer on hover/focus/active. Don't fake a hover by
swapping to a solid `--surface-1` — that only reads right on one backdrop and
breaks on coloured tabs.

## 7. QtWebEngine gotcha

`ui/ui.html` renders in **QtWebEngine**. For drop shadows use the CSS
`filter: drop-shadow(...)`, **not** the SVG `<feDropShadow>` filter — the SVG
filter silently fails to render there.

## 8. Tooltips — a registry, not a single dispatcher

All hovers render into one shared `#hull-tip` popover, wired through a registry:

- [`ui/js/tip-registry.js`](ui/js/tip-registry.js) (loaded right after
  `constants.js` in both `ui/ui.html` and `ui/web/index.html`) defines
  `TIP_HANDLERS`, `registerTip(key, handler)`, `TIP_RESETS`, and `onTipReset(fn)`.
- [`ui/js/tooltips.js`](ui/js/tooltips.js) is just the engine: runs reset hooks,
  builds its hover selector from the registered keys, finds the one `data-*-tip`
  attribute on the hovered element, calls that handler `(el, event, tip) =>
  boolean` (true = show + position), and clamps to the viewport. It knows nothing
  about any feature.
- Each feature file owns its own builder(s) **and** a `registerTip('camelKey', …)`
  call at the bottom of that same file (e.g. `weaponTip` in `designs-builder.js`,
  `trendTip` in `trends.js`, `hullTip` in `formatters.js`). The dataset key is the
  camelCase of the attribute (`data-weapon-tip` → `weaponTip`).

**Never use native SVG `<title>` or an HTML `title=` attribute.** They render
unstyled, ignore the tokens, and can't be positioned. Add a `data-*-tip` instead.

**Adding a new hover:** write a builder in the feature's own JS, stamp
`data-x-tip="…"` (a JSON-encoded payload via `encodeURIComponent` for chart data,
or pre-rendered HTML via `decodeURIComponent` — the `fleetTip`/`trendTip`
pattern), then `registerTip('xTip', …)` in that same file. No edit to
`tooltips.js` needed. Nearest-point line charts key a global data array and
resolve the nearest point *inside* the handler, returning `false` to stay hidden
when off-point (the `cfware`/`shipflow` pattern) — register an `onTipReset` to
clear their markers each move. Hover targets must be large enough to hit; give
tiny dots a wider transparent hit circle. Chart colours come from `CHART_*` in
`constants.js` (hex, not CSS vars — vars don't resolve inside SVG attrs).

Tooltip markup is still UI — colours, fonts, and radii inside a builder follow
§1–4 like any other component.

## 9. Content — numbers and labels

Show full numbers with thousands separators (`toLocaleString` → "2,360,711"),
never abbreviations like "2.4M" — the program's whole point is to make X4's
overwhelming data easy to read at a glance. Use readable words for levels
(Title Case, e.g. "Very High"), but label sparingly: a column header once,
not repeated per row.

**Exception — compact chart axes and volume.** Chart Y-axis tick labels
(`cashflow-chart.js`, `trends.js`) and cargo-volume labels (`fmtM3` in
`populate.js`) abbreviate ("2.4M", "120k") on purpose: axis ticks have no room
for full numbers without crowding the chart, and volume isn't a headline
credits figure. `fmtCredits()` in `formatters.js` is the same story for compact
credit readouts next to a chart. Any number that's the primary thing being
read (a stat value, a table cell, a summary total) still spells out in full —
this exception is for supporting/axis chrome only.

## 10. New-component checklist

- Surfaces from `--surface-*`; borders/dividers from `--outline`
- Colour by semantic trio (`--color-<meaning>` / `-dim` / `-line`)
- Text from `--text-*`; font picked by role (§3)
- Corners from `--radius-*`; all sizes in rem
- Transitions use `--duration-*` + `--ease-standard`
- Hover/focus/active via `--state-*`
- Missing a value? Add it to the **semantic** tier of `base.css` first, then use it.

## 11. JS files — one global per file

`ui/js` scripts are classic scripts sharing one global scope (about two
thousand top-level bindings and counting). There is no module system on
purpose: the desktop shell loads over `file://` in QtWebEngine, where ES-module
imports don't resolve, and the project has no build step.

To keep that livable:

- **A new JS file exposes exactly one global** — a namespace object named
  after the file, with everything else private inside an IIFE:

  ```js
  window.NpcStations = (function () {
    function render() { … }
    function openInspector() { … }
    return { render, openInspector };
  })();
  ```

- Existing files migrate **opportunistically** — when a file is already being
  edited for other reasons, never as a bulk sweep.
- Load order lives in [`js/shell-manifest.js`](ui/js/shell-manifest.js),
  shared by both shells. New files are added there — never to `ui.html` or
  `ui/web/index.html` directly.

## Adding a colour or theme

- **New colour:** add `--x`, `--x-dim`, `--x-line` to the palette block, then expose
  it as `--color-<meaning>` (plus `-dim` / `-line`) in the semantic block.
  Components reference only the `--color-<meaning>*` names.
- **New theme:** add a second `:root` / `[data-theme="…"]` block that re-points the
  **semantic** tokens. That block is the only file you touch — no component reads the
  palette directly, so nothing else needs to change.

---

**Applies to:** everything under `ui/` (CSS, `body.html`, inline SVG).
**Source of truth:** [`ui/css/base.css`](ui/css/base.css).
