# X4 Foresight Design System — build conventions

A dark, sci-fi *terminal* UI: deep charcoal surfaces, a teal primary accent, and
semantic feedback colours (green / amber / red / purple / lime). Data is shown in
a monospace font; labels in a condensed uppercase font. Build dashboards: summary
KPI tiles, framed panels, dense data tables, status badges, and inline bars.

## Setup — no provider, but design on a dark surface

There is **no React provider or theme wrapper**. Components are self-styling the
moment `styles.css` is loaded — all tokens live in `:root`. The one thing that
*will* look wrong if you skip it: these components are built for a **dark
background**. Put your own layout glue on a dark surface, or everything floats on
default white. Wrap a screen like this:

```jsx
import { SummaryCard, Panel, DataTable, Badge, ProgressBar } from "@x4-foresight/design-system";

<div style={{ background: "var(--bg)", color: "var(--text-primary)", padding: 16, fontFamily: "var(--font-body)" }}>
  <div className="x4-cards-row">
    <SummaryCard label="Account Balance" value="12,480,650 Cr" icon="wallet" tone="teal" />
    <SummaryCard label="Net Profit / hr" value="+842,300 Cr" icon="trending-up" tone="green" />
  </div>
  <Panel title="Fleet">
    <DataTable
      columns={[{ header: "Ship", field: "ship" }, { header: "Hull", field: "hull" }]}
      rows={[{ ship: "ARG Behemoth", hull: <ProgressBar variant="hull" value={92} /> }]}
    />
  </Panel>
</div>
```

## Styling idiom — props for components, tokens for your own markup

**Style library components through their props, never `className`.** The design
language is carried by enum props:

- `SummaryCard tone` / `ProgressBar tone`: `teal | green | amber | red` (`auto` ramps a bar green→amber→red by value)
- `Badge relation`: `allied | friendly | neutral | hostile | atwar`
- `Alert tone`: `red | amber | green`
- `ProgressBar variant`: `rep` (thin) | `hull` (taller health bar)
- `DataTable` columns take `numeric: true` to right-align in the data font

**For your own layout glue, use the CSS custom properties** (defined globally in
`styles.css`) — do not hard-code hex values:

- Surfaces: `--bg`, `--surface-1`, `--surface-2`, `--outline`
- Text: `--text-primary`, `--text-secondary`, `--text-label` (brand green)
- Accents: `--color-primary` (teal), `--color-positive`, `--color-warning`, `--color-negative`, `--color-special`, `--color-highlight`
- Fonts: `--font-body` (Barlow), `--font-label` (Barlow Condensed, uppercase labels), `--font-data` (Share Tech Mono, all numbers/IDs)
- Shape: `--radius-sm | --radius-md | --radius-lg`

Two layout helper classes ship for composing screens: `x4-cards-row` (auto-fit
KPI grid) and `x4-two-col`. Icons come from `X4Icon name="<tabler-name>"` (a
curated Tabler subset — wallet, coin, ship, rocket, building-factory-2, world,
package, users, shield, swords, chart-line, trending-up/down, alert-triangle,
flask, cpu, database, planet, building-warehouse).

## Where the truth lives

Read the bound `styles.css` (and its `@import`ed `_ds_bundle.css`) for the full
token list, and each component's `.d.ts` / `.prompt.md` for its exact props before
composing. Numbers and identifiers always render in the monospace data font —
keep that habit and screens read as authentic X4 readouts.
