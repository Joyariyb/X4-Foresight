# X4 Empire Intelligence — UI Layout Reference

---

## Shell

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  #topbar                                                                 [48px] │
├─────────────────────────────────────────────────────────────────────────────────┤
│  #nav                                                                    [38px] │
├───────────────────┬─────────────────────────────────────────────────────────────┤
│                   │                                                             │
│  #sidebar         │  #content                                                   │
│                   │  (active .tab-panel)                                        │
│                   │                                                             │
│                   │                                                             │
└───────────────────┴─────────────────────────────────────────────────────────────┘
```

---

## Top Bar  `#topbar`

```
┌──────────────────┬──────────────┬──────────────┬──────────────┬──────────┬────────────┐
│  ◈ X4 FORESIGHT  │  PILOT       │  SECTOR      │  CREDITS     │  SHIPS   │  STATIONS  │
│  .tb-logo        │  [name]      │  [name]      │  [1.2M Cr]   │  [42]    │  [7]       │
│                  │  .tb-field   │  .tb-field   │  .tb-field   │.tb-field │  .tb-field │
└──────────────────┴──────────────┴──────────────┴──────────────┴──────────┴────────────┘
  teal logo          tb-pilot       tb-sector       tb-credits    tb-ships    tb-stations
```

---

## Nav Bar  `#nav`

```
┌────────────┬────────────┬────────────┬────────────┬────────────┬────────────┐
│  Overview  │   Fleet    │  Stations  │   Crew     │ Diplomacy  │  Alerts 🔴 │
│  .nav-tab  │  .nav-tab  │  .nav-tab  │  .nav-tab  │  .nav-tab  │  .nav-tab  │
│  .active ◀─┤            │            │            │            │  .nav-badge│
└────────────┴────────────┴────────────┴────────────┴────────────┴────────────┘
  #tab-overview #tab-fleet  #tab-stations #tab-crew  #tab-diplomacy #tab-alerts
```

Active tab has a teal underline border. Alerts badge turns red when alerts exist.

---

## Sidebar  `#sidebar`

```
┌───────────────────┐
│  FLEET            │  ← .sb-heading
│  ─────────────── │
│  🚀 Military   8  │  ← .sb-item  #sb-military
│  📦 Traders   14  │  ← .sb-item  #sb-traders
│  ⛏  Miners    6  │  ← .sb-item  #sb-miners
│  ⚠  Hostile   0  │  ← .sb-item  #sb-hostile  (.warn → red text)
│  ─────────────── │  ← .sb-divider
│  STATIONS         │  ← .sb-heading
│  > Sector Name    │  ← .sb-sector-label
│    Station Name   │  ← .sb-station  (click → scrolls to card)
│    Station Name   │
│  > Sector Name    │
│    Station Name   │
│    ...            │
└───────────────────┘
                         Clicking a station name scrolls to its card in #tab-stations
```

---

## Overview Tab  `#tab-overview`

```
┌──────────────────────────────────────────────────────────────────────┐
│  Empire Snapshot                                                      │
│                                                                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│  │ CREDITS  │ │TOT SHIPS │ │ STATIONS │ │ HOSTILE  │ │ WAITING  │  │
│  │  1.2M Cr │ │    42    │ │    7     │ │    0     │ │    3     │  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘  │
│                                           .cards-row  #summary-cards │
│                                                                      │
│  ┌─────────────────────────┐  ┌─────────────────────────────────┐   │
│  │  Fleet by Role          │  │  Fleet by Order                 │   │
│  │  ─────────────────────  │  │  ─────────────────────────────  │   │
│  │  Role         Count     │  │  Order           Count          │   │
│  │  Fighter        12      │  │  Trading           14           │   │
│  │  Freighter       8      │  │  Mining             6           │   │
│  │  ...            ...     │  │  ...               ...          │   │
│  │  #role-table            │  │  #order-table                   │   │
│  └─────────────────────────┘  └─────────────────────────────────┘   │
│            .two-col (side-by-side)                                   │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Fleet Tab  `#tab-fleet`

### Sub-tab bar  `.fleet-subtabs  #fleet-subtabs`

```
┌──────────────────┬─────────────┬─────────────┬─────────────┐
│  Player  42      │  CIV  3     │  XEN  12    │  ...        │
│  .fleet-subtab   │.fleet-subtab│.fleet-subtab│             │
│  .active  (teal) │  (faction   │  (faction   │             │
│  data-faction=   │   colour)   │   colour)   │             │
│  "player"        │ "civilian"  │  "xenon"    │             │
└──────────────────┴─────────────┴─────────────┴─────────────┘
  #fleet-panel-player shown; NPC panels in #fleet-npc-panels
```

NPC faction tabs are **built dynamically** by `populate()` — only factions with ships appear.

### Player Fleet Panel  `#fleet-panel-player`

```
┌─────────────────────────────────────────────────────────────────────┐
│  Player Fleet                    Sort  [ Role ↑ ]  [Change… ▾]      │
│                                  #sort-indicator  #sort-select       │
│  ─────────────────────────────────────────────────────────────────  │
│  Code / Name    Size   Hull Type   HP        Order   Sector   Pilot  │
│  ─────────────────────────────────────────────────────────────────  │
│  LSS-001        XL     *Xenon      ██░░ 84%  Mining  Hewa I  Jana R  │
│  ABX-113        M      Argon       ████100%  Trading  ...    ...     │
│  ...                                                                 │
│  #fleet-table                                                        │
└─────────────────────────────────────────────────────────────────────┘
```

**Fleet table columns:**

| Column | Notes |
|--------|-------|
| Code / Name | Ship code + custom name if set |
| Size | `S` / `M` / `L` / `XL` — colour coded (teal M, amber L) |
| Hull Type | Faction badge. `*` prefix + red = hostile origin (Xenon / Yaki / Kha'ak) |
| HP | Hull bar. Green → amber → red by %. Blue = >100% (hull mod) |
| Order | `Trading` green · `Mining` amber · `Escorting` teal · `Waiting` dim |
| Sector | Current sector name |
| Pilot | Pilot name + star skill hover tooltip |

**Null sort rule:** ships with missing data for the chosen field always sort to the bottom.

---

## Crew Tab  `#tab-crew`

### Sub-tab bar  `#crew-subtabs`

```
┌──────────────┬──────────────┬──────────────┬──────────────┐
│  All  28     │ Managers  4  │  Pilots  12  │ Marines  3   │
│  (teal)      │  (purple)    │  (amber)     │  (red)       │
└──────────────┴──────────────┴──────────────┴──────────────┘
```

### Layout  `.crew-layout`

```
┌────────────────────────────────────┬───────────────────────────────┐
│  Crew Roster          .crew-roster │  Crew File          .crew-file │
│                                    │                                │
│  Name  Role  Primary  Assigned To  │  [Select a crew member        │
│  ───────────────────────────────   │   to view their file]         │
│  Jana  pilot  ★★★★☆  LSS-001       │                                │
│  Marc  svc    ★★☆☆☆  Station X     │  (populated on row click)     │
│  ...                               │  #crew-file-card               │
│  #crew-table                       │                                │
└────────────────────────────────────┴───────────────────────────────┘
```

---

## Stations Tab  `#tab-stations`

Rendered as a column of station cards in `#stations-grid`.

### Station Card Anatomy

```
┌─────────────────────────────────────────────────────────────────────────┐
│  ARG  PRODUCTION STATION          Hewa Prime I            ● OPERATIONAL  │
│  [faction tag]  [type label]      [sector]                [status badge] │
│  APX-001  ·  My Station Name                                             │
│  [code]         [display name]                                           │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────────────────┐   │
│  │ MODULES  │  │   CREW   │  │  SHIPS   │  │  STORAGE          ↗   │   │
│  │    12    │  │   —      │  │    3     │  │   57%                  │   │
│  └──────────┘  └──────────┘  └──────────┘  └───────────────────────┘   │
│       stat cells (.sc)  ──  hover Storage for breakdown tooltip         │
├─────────────────────────────────────────────────────────────────────────┤
│  Hull   ████████████████████░░░  84%   current / max HP                 │
│  Shield ████████████████████████ 100%  current / max HP                 │
│         (or:  Shields  ✕ NO SHIELDS — when no generator fitted)         │
├─────────────────────────────────────────────────────────────────────────┤
│  [ Production ]  [ Docked · 3 ]   ← station tab bar (.station-tab-btn) │
├─────────────────────────────────────────────────────────────────────────┤
│  ADVANCED ELECTRONICS  ────────────────────────────────────────  —  —/hr│
│  QUANTUM TUBES         ────────────────────────────────────────  —  —/hr│
│  ENERGY CELLS          ────────────────────────────────────────  —  —/hr│
│                        ↑ each ware in its WARE_COLOURS accent            │
└─────────────────────────────────────────────────────────────────────────┘
```

**Status badge colours:**

| `status` value | Label | Colour |
|---|---|---|
| contains `"construction"` | `UNDER CONSTRUCTION` | amber |
| contains `"wreck"` | `DESTROYED` | red |
| anything else | `OPERATIONAL` | green |

**Hull / Shield bar colours:**

| Range | Colour |
|---|---|
| 0 – 49 % | red |
| 50 – 79 % | amber |
| 80 – 100 % | green |
| > 100 % (hull mod) | blue |

### Docked Ships Tab

```
│  ┌──────┬─────────────────────────────────┐
│  │  M   │  AJP-437  Freighter             │  ← clickable → jumps to Fleet tab
│  │  S   │  EXL-556  Scout                 │  ← (click on CIV ships → CIV subtab)
│  │  ?   │  [under construction]           │  ← not clickable, dimmed
│  └──────┴─────────────────────────────────┘
```

---

## Diplomacy Tab  `#tab-diplomacy`

```
┌──────────────────────────────────────────────────────────────────┐
│  Faction Standings                                                │
│  ──────────────────────────────────────────────────────────────  │
│  Faction              Tier       Score   Bar        Base  Booster│
│  ──────────────────────────────────────────────────────────────  │
│  [ARG] Argon Fed.    [Allied]   +27.4   ██████████  +25.1  +2.3 │
│  [TEL] Teladi Co.    [Friendly] +12.0   █████░░░░░  +12.0   0.0 │
│  [XEN] Xenon         [At War]   −30.0   ░░░░░░░░░░  −30.0   0.0 │
│  ...                                                             │
│  #rep-table                                                      │
└──────────────────────────────────────────────────────────────────┘
```

Rep bar: green for positive, red for negative, scaled −30 → +30.

---

## Alerts Tab  `#tab-alerts`

```
┌────────────────────────────────────────────────────────┐
│  Alerts                                                │
│  ────────────────────────────────────────────────────  │
│  🔴  3 ships with hostile hulls (Xenon origin)         │
│  🟡  2 ships waiting for orders                        │
│  🟡  1 idle miner                                      │
│  #alerts-list                                          │
└────────────────────────────────────────────────────────┘
```

**Alert conditions:**

| Alert | Trigger | Colour |
|---|---|---|
| Hostile hulls | `hull_origin` ∈ `{Xenon, Yaki, Kha'ak}` | red |
| Waiting ships | `order === "Waiting"` | amber |
| Idle miners | waiting + mining role | amber |

---

## Hover Tooltips  `#hull-tip`

One shared `<div id="hull-tip">` is repositioned by `mousemove`. Four types:

### Hull Bar  `data-hull-tip`

```
┌───────────────────────────────────┐
│  LSS-001                          │
│  ████████████░░░░  75%            │
│  12,400 / 16,500 HP               │
└───────────────────────────────────┘
  Triggered by hovering the hull bar on a fleet row
```

### Pilot Skills  `data-pilot-skills`

```
┌───────────────────────────────────┐
│  Piloting      ★★★★☆             │
│  Management    ★★★☆☆             │
│  Morale        ★★☆☆☆             │
│  Engineering   ★☆☆☆☆             │
└───────────────────────────────────┘
  Triggered by hovering the Pilot cell on a fleet row
  Empty stars → --text-dim (grey).  Filled stars → skill colour.
```

### Storage Breakdown  `data-storage-tip`

```
┌───────────────────────────────────┐
│  CONTAINER            57%        │  ← teal
│  ████████████░░░░░░░░            │
│  566.9K / 1.0M m³                │
│                                  │
│  SOLID                 4%        │  ← amber
│  ██░░░░░░░░░░░░░░░░░░            │
│  35.7K / 1.0M m³                 │
│                                  │
│  LIQUID                8%        │  ← purple
│  ████░░░░░░░░░░░░░░░░            │
│  82.3K / 1.0M m³                 │
│  ─────────────────────────────── │
│  TOTAL                23%        │  ← green
│  ████░░░░░░░░░░░░░░░░            │
│  684.9K / 3.0M m³                │
└───────────────────────────────────┘
  Triggered by hovering the Storage stat cell on a station card
```

### Module List  `data-modules-tip`

```
┌───────────────────────────────────┐
│  Production                       │
│    Argon Energy Cell Prod.  × 2   │
│    Advanced Electronics     × 1   │
│  Dock Area                        │
│    S/M Dock                 × 4   │
│  Storage                          │
│    Container Storage L      × 3   │
│  Struct                           │
│    Argon Struct             × 12  │
└───────────────────────────────────┘
  Triggered by hovering the Modules stat cell on a station card
  Categories in order: Production · Dock Area · Pier · Storage · Struct · Other
```

---

## Colour Reference

| Variable | Hex | Used for |
|---|---|---|
| `--teal` | `#2dd4bf` | Primary accent, player fleet, active tabs |
| `--green` | `#3fb950` | Health OK, trading orders, total storage |
| `--amber` | `#d29922` | Warnings, L-ships, mining, solid storage |
| `--red` | `#f85149` | Danger, hostile, shields down |
| `--purple` | `#a371f7` | Liquid storage, managers |
| `--yellow` | `#e3b341` | Secondary highlights |
| `--text` | `#c9d1d9` | Primary body text |
| `--text-dim` | `#8b949e` | Secondary text, empty stars |
| `--text-faint` | `#3fb950` | Label text (green) |
| `--bg` | `#0d1117` | Page background |
| `--bg-panel` | `#161b22` | Panels, nav, sidebar |
| `--bg-card` | `#1c2128` | Cards, stat cell insets |
| `--border` | `#21262d` | All dividers and borders |

### Fleet / Order Colours

| Value | Colour |
|---|---|
| Trading | `--green` |
| Mining | `--amber` |
| Escorting | `--teal` |
| Waiting | `--text-faint` |
| L ships | `--amber` |
| M ships | `--teal` |
| S ships | `--text-dim` |
