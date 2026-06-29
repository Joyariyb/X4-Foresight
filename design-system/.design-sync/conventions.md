# X4 Foresight Design System — Conventions

## Wrapping and setup

No provider or root wrapper is required. Every component is pure presentational — no React context, theme, or router. Import and render directly.

The system is **dark-only**: the token palette assumes a dark surface host. Wrap top-level content in a surface element to get the correct backdrop:

```jsx
<div style={{ background: 'var(--surface-0)', padding: '16px' }}>
  {/* components here */}
</div>
```

Surface tiers (dark to slightly raised): `var(--surface-0)` (#0d1117) → `var(--surface-1)` (#161b22) → `var(--surface-2)` (#1c2128). Components set their own surface automatically; only the page/section background needs explicit colour.

## Styling idiom — props + CSS custom properties

This is a **props-based API with no utility classes**. Style the component through its props; use CSS variables only for layout glue the agent authors itself.

**Key semantic tokens** (defined in `styles.css` → `_ds_bundle.css`):

| Purpose | Token |
|---|---|
| Brand / primary | `var(--color-primary)` — teal #2dd4bf |
| Positive / success | `var(--color-positive)` — green #3fb950 |
| Warning | `var(--color-warning)` — amber #d29922 |
| Danger / critical | `var(--color-negative)` — red #f85149 |
| Label text (brand green) | `var(--text-label)` |
| Primary text | `var(--text-primary)` |
| Secondary text | `var(--text-secondary)` |
| Body font | `var(--font-body)` — Barlow |
| Data / monospace | `var(--font-data)` — Share Tech Mono |
| Label / condensed | `var(--font-label)` — Barlow Condensed |
| Standard outline | `var(--outline)` — dark border |
| State hover bg | `var(--state-hover)` |

**Layout helpers** (shipped in `_ds_bundle.css`, usable in the agent's own markup):

- `.x4-cards-row` — `grid; auto-fit; minmax(160px,1fr); gap:8px` — the standard summary-card strip
- `.x4-two-col` — two equal columns, `gap:12px`

Do **not** write `x4-badge`, `x4-table`, or other component-internal class names — they're owned by the component and not part of the public API.

## Where the truth lives

- `styles.css` + its `@import` chain (includes `_ds_bundle.css`) — full token and component CSS; read this for the complete variable vocabulary
- `components/<group>/<Name>/<Name>.prompt.md` — each component's props and usage notes
- `components/<group>/<Name>/<Name>.d.ts` — TypeScript props interface

## Idiomatic build snippet

```jsx
import {
  SectionHeader,
  SummaryCard,
  Panel,
  DataTable,
  Badge,
  ProgressBar,
  Alert,
} from '@x4-foresight/design-system';

function EmpireOverview() {
  return (
    <div style={{ background: 'var(--surface-0)', padding: '16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>

      {/* KPI strip — use .x4-cards-row or an equivalent auto-fit grid */}
      <div className="x4-cards-row">
        <SummaryCard label="Account Balance" value="4 289 000 Cr" icon="coin" tone="teal" />
        <SummaryCard label="Active Ships" value="42" icon="rocket" tone="green" />
        <SummaryCard label="Hull Damage" value="3 ships" icon="shield" tone="amber" />
      </div>

      <Alert tone="amber">TEL Serpent hull at 12% — dock immediately</Alert>

      <SectionHeader title="Fleet Status" />

      {/* Panel wraps DataTable flush — no extra padding on the body */}
      <Panel title="Ships" headerExtra="42 ships">
        <DataTable
          columns={[
            { header: 'Ship', field: 'name' },
            { header: 'Faction', field: 'faction' },
            { header: 'Hull', field: 'hull' },
            { header: 'Cargo', field: 'cargo', numeric: true },
          ]}
          rows={[
            { name: 'ARG Mjölnir', faction: <Badge relation="allied" />, hull: <ProgressBar value={87} variant="hull" tone="auto" />, cargo: '12 400' },
            { name: 'TEL Serpent', faction: <Badge relation="friendly" />, hull: <ProgressBar value={12} variant="hull" tone="auto" />, cargo: '4 200' },
          ]}
        />
      </Panel>

    </div>
  );
}
```
