  // ── DESIGNS TAB ───────────────────────────────────────────────────────────
  // A "design" is a unique ship configuration: same hull macro + the same
  // installed equipment (same macros, same counts). Many ships collapse onto
  // one design. Built entirely from the loadout the export already carries —
  // no backend. Deployables have no loadout, so they never appear here.

  // Static catalogs set by populate(): equipment (macro → name/stats/price) and
  // hulls (macro → name/class/hardpoints/price). The blueprint builder reads both.
  let EQUIPMENT_CATALOG = {};
  let HULL_CATALOG = {};

  // Weapon/turret hover stats mode -- 'ingame' truncates derived stats (damage
  // rates, rate of fire, cooldown/overheat) the same way the real in-game
  // tooltip does; 'true' shows the raw computed value to 3dp with no
  // truncation. Read by weaponTipHtml() in tooltips.js. Persisted across
  // sessions since it's a verification preference, not per-design state.
  let weaponStatsMode = localStorage.getItem('weaponStatsMode') || 'ingame';
  function setWeaponStatsMode(mode) {
    weaponStatsMode = mode;
    localStorage.setItem('weaponStatsMode', mode);
    renderBuilder();
  }

  const DESIGN_SLOTS = [
    ['weapon','Weapons'], ['turret','Turrets'], ['shield','Shields'],
    ['engine','Engine'],  ['thruster','Thruster'],
  ];

  const designCr = n => Number(n).toLocaleString();

  // '#rrggbb' -> 'rgba(r,g,b,a)'. Used to tint the hull preview panel border/
  // glow by faction colour without relying on CSS color-mix(), which isn't
  // guaranteed to be supported by QtWebEngine's bundled Chromium version.
  function hexA(hex, a) {
    const n = parseInt(hex.replace('#', ''), 16);
    return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
  }

  // Per-category icon + colour for the section headers (.dsect-hd). The tint is
  // the same colour at low alpha, used as the header background.
  const SLOT_META = {
    hull:     { icon:'ti-ufo',        color:'var(--yellow)', tint:'rgba(227,179,65,0.08)' },
    weapon:   { icon:'ti-bolt',       color:'var(--red)',    tint:'rgba(248,81,73,0.08)' },
    turret:   { icon:'ti-circle-dot', color:'var(--amber)',  tint:'rgba(210,153,34,0.08)' },
    shield:   { icon:'ti-shield',     color:'var(--teal)',   tint:'rgba(45,212,191,0.08)' },
    engine:   { icon:'ti-engine',     color:'var(--purple)', tint:'rgba(163,113,247,0.08)' },
    thruster: { icon:'ti-windmill',   color:'var(--lime)',   tint:'rgba(57,255,20,0.08)' },
  };

  // Colour + tint for the size badge in the card summary. Mirrors the S/M/L
  // colours already used for the Size column in the fleet/crew tables
  // (SIZE_COLOURS in constants.js); XL doesn't exist there yet so it's only
  // defined here for now.
  const SIZE_TINT = {
    S:  { c: 'var(--text-dim)', bg: 'rgba(255,255,255,0.05)' },
    M:  { c: 'var(--teal)',     bg: 'rgba(45,212,191,0.08)' },
    L:  { c: 'var(--amber)',    bg: 'rgba(210,153,34,0.08)' },
    XL: { c: 'var(--purple)',   bg: 'rgba(163,113,247,0.08)' },
  };

  // Per-slot stat columns: [catalog key, header label, value formatter].
  const SLOT_STATS = {
    weapon:   [['damage_hull','Damage',designCr], ['range_m','Range',v=>(v/1000).toFixed(1)+' km'], ['reload_rate','Rate',v=>v+'/s']],
    turret:   [['damage_hull','Damage',designCr], ['range_m','Range',v=>(v/1000).toFixed(1)+' km'], ['reload_rate','Rate',v=>v+'/s']],
    shield:   [['capacity','Capacity',designCr],  ['recharge_rate','Rechg',v=>designCr(v)+'/s'],   ['recharge_delay','Delay',v=>v+' s']],
    engine:   [['thrust_forward','Forward',designCr], ['travel_thrust','Travel',v=>Math.round(v)]],
    thruster: [['strafe','Strafe',designCr], ['pitch','Pitch',designCr], ['yaw','Yaw',designCr], ['roll','Roll',designCr]],
  };

  // 3-letter faction tag in the hull-badge style.
  // Generic / no-maker parts (thrusters) get a neutral GEN badge.
  const FAC3 = {
    argon:'ARG', paranid:'PAR', teladi:'TEL', split:'SPL', terran:'TER',
    boron:'BOR', xenon:'XEN', khaak:'KHA', pirate:'PIR', yaki:'YAK',
  };
  // Coloured from FACTION_COLOURS (defined below) rather than a per-faction
  // CSS class — the CSS classes only ever covered 5 of the 24 factions, so
  // every other faction rendered as a plain grey badge.
  function designBadge(faction) {
    if (!faction) return '<span class="badge neutral">GEN</span>';
    const f = faction.toLowerCase();
    const colour = FACTION_COLOURS[f] || '#6e7681';
    const style = `background:${hexA(colour, 0.1)};color:${colour};border:1px solid ${hexA(colour, 0.25)}`;
    return `<span class="badge" style="${style}">${FAC3[f] || f.slice(0,3).toUpperCase()}</span>`;
  }

  // Resolvable equipment only — drops the unresolved internal parts (raw macros).
  const designItems = s => (s.loadout || []).filter(e => !e.name.endsWith('_macro'));

  // Stable grouping key: hull + each item as slot:macro:count, sorted so the
  // order equipment was read never affects whether two ships match.
  function designSignature(s) {
    return s.macro + '||' +
      designItems(s).map(e => `${e.slot}:${e.macro}:${e.count}`).sort().join('|');
  }

  // Hull price + the cost of every fitted item in the categories the card
  // actually displays (DESIGN_SLOTS) — shared by the Cost sort and the card's
  // own "Design total" line so the two can never drift apart.
  function designTotalCost(d) {
    let total = d.hullPrice || 0;
    for (const [slot] of DESIGN_SLOTS) {
      for (const e of (d.loadout || []))
        if (e.slot === slot && !e.name.endsWith('_macro') && e.price) total += e.price * e.count;
    }
    return total;
  }

  // Size + faction filter state for the bar above the grid. 'all' means no
  // restriction on that axis.
  let designsFilter = { size: 'all', faction: 'all' };

  // Which designs the user has manually collapsed, keyed by design signature
  // (stable across re-renders — same hull+loadout always hashes the same way).
  // grid.innerHTML gets fully rebuilt on every render (tab switch, filter,
  // sort), which would otherwise reset every card back to its hardcoded
  // default open state, so the actual open/closed state lives here instead of
  // on the DOM.
  let designsCollapsed = new Set();

  // Sort key for the design grid. Each entry is a comparator over the grouped
  // design objects; alphabetical-by-type is the tiebreaker everywhere so the
  // order stays stable when the primary key ties.
  let designsSortBy = 'used';
  const SIZE_RANK = { xs: 0, s: 1, m: 2, l: 3, xl: 4 };
  // Largest-first comparator for mount-size keys ('l','m',...) — shared by the
  // design card and blueprint builder so a category's size groups (and their
  // "fitted/cap SIZE" header fractions) always list big mounts before small ones.
  const sizeRank = s => SIZE_RANK[(s || '').toLowerCase()] ?? -1;
  const bySizeDesc = (a, b) => sizeRank(b) - sizeRank(a);
  // Border/fill colour per mount size, used to give each size's "inner box"
  // (design card sub-groups, builder size groups) its own tint — same hue
  // language as SIZE_TINT/SIZE_COLOURS elsewhere, but as plain hex since the
  // box border needs hexA() alpha-blending rather than a bare CSS var().
  const SIZE_BOX = {
    xs: { hex: '#8b949e', bg: 'rgba(139,148,158,0.05)' },
    s:  { hex: '#8b949e', bg: 'rgba(139,148,158,0.05)' },
    m:  { hex: '#2dd4bf', bg: 'rgba(45,212,191,0.05)' },
    l:  { hex: '#d29922', bg: 'rgba(210,153,34,0.05)' },
    xl: { hex: '#a371f7', bg: 'rgba(163,113,247,0.05)' },
  };
  const DESIGN_SORTERS = {
    used:    (a, b) => b.ships.length - a.ships.length || a.type.localeCompare(b.type),
    size:    (a, b) => (SIZE_RANK[(a.hullSize || '').toLowerCase()] ?? 99) - (SIZE_RANK[(b.hullSize || '').toLowerCase()] ?? 99) || a.type.localeCompare(b.type),
    faction: (a, b) => (a.hullFaction || '').localeCompare(b.hullFaction || '') || a.type.localeCompare(b.type),
    type:    (a, b) => (a.role || '').localeCompare(b.role || '') || a.type.localeCompare(b.type),
    cost:    (a, b) => b.totalCost - a.totalCost || a.type.localeCompare(b.type),
  };
  function designsSetSort(sortBy) {
    designsSortBy = sortBy;
    renderDesigns();
  }

  function designsSetSizeFilter(size, el) {
    designsFilter.size = size;
    document.querySelectorAll('#designs-size-filter .fleet-subtab').forEach(t => t.classList.remove('active'));
    (el || document.querySelector(`#designs-size-filter [data-size="${size}"]`))?.classList.add('active');
    renderDesigns();
  }
  function designsSetFactionFilter(faction) {
    designsFilter.faction = faction;
    renderDesigns();
  }

  // Rebuilds the faction <option> list from whatever hull origins are present
  // in the unfiltered fleet. Cached on the joined faction list so it doesn't
  // rebuild (and drop focus) every render when nothing actually changed.
  let _designsFactionOptionsKey = null;
  function designsPopulateFactionOptions(ships) {
    const sel = document.getElementById('designs-faction-select');
    if (!sel) return;
    const factions = [...new Set(ships.map(s => s.hull_origin).filter(Boolean))].sort();
    const key = factions.join('|');
    if (key === _designsFactionOptionsKey) return;
    _designsFactionOptionsKey = key;
    sel.innerHTML = '<option value="all">All</option>' +
      factions.map(f => `<option value="${f}">${f}</option>`).join('');
    if (!factions.includes(designsFilter.faction)) designsFilter.faction = 'all';
    sel.value = designsFilter.faction;
  }

  // Flips every card's <details open> together. Reads majority state so one
  // click always does the obvious thing (collapse if most are open, else
  // expand), rather than tracking a separate "last action" flag.
  function designsToggleAll() {
    const cards = document.querySelectorAll('#designs-grid .dcard');
    const anyOpen = [...cards].some(c => c.open);
    const newOpen = !anyOpen;
    cards.forEach(c => {
      c.open = newOpen;
      if (newOpen) designsCollapsed.delete(c.dataset.sig); else designsCollapsed.add(c.dataset.sig);
    });
    designsUpdateToggleAllBtn();
  }
  // Persists a per-card collapse/expand from the native <details> chevron.
  // designsToggleAll() updates designsCollapsed itself (some Chromium versions
  // don't dispatch 'toggle' for a programmatic .open assignment), so this is
  // really only load-bearing for the manual, one-card-at-a-time click.
  function designsHandleToggle(ev) {
    const card = ev.target;
    const sig = card.dataset && card.dataset.sig;
    if (!sig) return;
    if (card.open) designsCollapsed.delete(sig); else designsCollapsed.add(sig);
    designsUpdateToggleAllBtn();
  }
  function designsUpdateToggleAllBtn() {
    const btn = document.getElementById('designs-toggle-all');
    if (!btn) return;
    const cards = document.querySelectorAll('#designs-grid .dcard');
    if (!cards.length) { btn.style.display = 'none'; return; }
    btn.style.display = '';
    const anyOpen = [...cards].some(c => c.open);
    btn.innerHTML = anyOpen
      ? '<i class="ti ti-chevrons-up"></i> Collapse All'
      : '<i class="ti ti-chevrons-down"></i> Expand All';
  }

  function renderDesigns() {
    const grid  = document.getElementById('designs-grid');
    const empty = document.getElementById('designs-empty');
    const emptyTitle = document.getElementById('designs-empty-title');
    const emptyBody  = document.getElementById('designs-empty-body');
    const count = document.getElementById('designs-result-count');
    const allShips = (allPlayerShips || []).filter(s => designItems(s).length);
    designsPopulateFactionOptions(allShips);

    let ships = allShips;
    if (designsFilter.size !== 'all') ships = ships.filter(s => s.size === designsFilter.size);
    if (designsFilter.faction !== 'all') ships = ships.filter(s => s.hull_origin === designsFilter.faction);

    if (!ships.length) {
      grid.innerHTML = '';
      empty.style.display = 'flex';
      if (count) count.textContent = '';
      designsUpdateToggleAllBtn();
      if (!allShips.length) {
        emptyTitle.textContent = 'No ship designs found';
        emptyBody.textContent = "This tab lists your fleet's unique ship configurations, deduplicated by hull and fitted equipment. Run a scan with a fleet in it to populate it.";
      } else {
        emptyTitle.textContent = 'No designs match these filters';
        emptyBody.textContent = 'Try a different size or faction.';
      }
      return;
    }
    empty.style.display = 'none';
    // Individual cards toggle natively (no JS), so listen for that here to
    // persist the open/closed state into designsCollapsed and keep the
    // Collapse/Expand All label honest. 'toggle' doesn't bubble, but a
    // capturing listener on the grid still sees it from every descendant.
    grid.addEventListener('toggle', designsHandleToggle, true);

    // Group ships by signature.
    const groups = new Map();
    for (const s of ships) {
      const sig = designSignature(s);
      if (!groups.has(sig))
        groups.set(sig, {
          sig, type: s.type_name || s.macro, loadout: s.loadout, ships: [],
          hullFaction: s.hull_origin, hullMax: s.hull_max, hullPrice: s.hull_price,
          hullSize: s.size, hardpoints: s.hardpoints, role: s.role,
        });
      groups.get(sig).ships.push(s);
    }
    const designs = [...groups.values()];
    designs.forEach(d => d.totalCost = designTotalCost(d));

    // Config letters per hull type, lettered by descending member count. A type
    // with only one config gets no letter (no "Config A" when there's no B).
    const byType = {};
    designs.forEach(d => (byType[d.type] = byType[d.type] || []).push(d));
    Object.values(byType).forEach(list => {
      list.sort((a, b) => b.ships.length - a.ships.length);
      list.forEach((d, i) =>
        d.config = list.length > 1 ? ' · Config ' + String.fromCharCode(65 + i) : '');
    });

    designs.sort(DESIGN_SORTERS[designsSortBy] || DESIGN_SORTERS.used);
    grid.innerHTML = designs.map((d, i) => designCardHtml(d, i)).join('');
    if (count) count.textContent = `${designs.length} design${designs.length > 1 ? 's' : ''} · ${ships.length} ship${ships.length > 1 ? 's' : ''}`;
    designsUpdateToggleAllBtn();
  }

  // Generic placeholder hull wireframe. Replaced per-hull by the .xmf mesh
  // render in a later phase; kept neutral so it reads as a preview, not data.
  // Sizing is left to the .dhull-wire CSS so it can scale up in the bigger
  // preview panel without a second copy of this markup.
  const WIRE_SVG = `<svg viewBox="0 0 140 64" style="filter:drop-shadow(0 0 4px rgba(45,212,191,0.5))" aria-hidden="true">
    <g fill="none" stroke="var(--teal)" stroke-width="1.1"><polygon points="70,5 80,26 76,54 70,60 64,54 60,26"/><line x1="70" y1="5" x2="70" y2="60"/><polygon points="60,30 41,38 44,49 60,45"/><polygon points="80,30 99,38 96,49 80,45"/></g>
    <g fill="none" stroke="var(--lime)" stroke-width="1.1"><line x1="66" y1="56" x2="66" y2="63"/><line x1="74" y1="56" x2="74" y2="63"/></g></svg>`;

  function designCardHtml(d, idx) {
    // Four stat cells from a source object + the slot's column defs (pads empties).
    const statCells = (src, defs) => [0,1,2,3].map(i => {
      if (!defs[i]) return '<span></span>';
      const v = src[defs[i][0]];
      return `<span class="dst">${v != null ? defs[i][2](v) : '—'}</span>`;
    }).join('');
    const headerRow = defs =>
      `<div class="drow"><span></span><span></span><span></span>` +
      [0,1,2,3].map(i => `<span class="dhd">${defs[i] ? defs[i][1] : ''}</span>`).join('') +
      `<span class="dhd">Cost</span></div>`;

    // One bounded, colour-headed category panel.
    const section = (slot, label, slotsText, inner) => {
      const m = SLOT_META[slot];
      return `<div class="dsect">
        <div class="dsect-hd" style="background:${m.tint}">
          <i class="ti ${m.icon}" style="color:${m.color}"></i><span class="lbl">${label}</span>
          <span class="slots">${slotsText || ''}</span>
        </div>
        <div class="dsect-body">${inner}</div>
      </div>`;
    };

    // ── Equipment column (left half) ──────────────────────────────────────
    let equip = '';
    for (const [slot, label] of DESIGN_SLOTS) {
      const items = (d.loadout || []).filter(e => e.slot === slot && !e.name.endsWith('_macro'));
      if (!items.length) continue;
      const defs = SLOT_STATS[slot] || [];
      // Mount sizes never get pooled into one combined total anymore — a hull
      // with 9 L and 8 M turrets used to show as one "17/17 · L/M" line, which
      // hid how the count actually split. Each size gets its own fraction in
      // the header (largest first) and its own sub-group of rows in the body.
      const hp = (d.hardpoints && d.hardpoints[slot]) || null;
      const sizesPresent = [...new Set([
        ...(hp ? Object.keys(hp) : []),
        ...items.map(e => (e.size || '').toLowerCase()).filter(Boolean),
      ])].sort(bySizeDesc);
      const sizeGroups = sizesPresent.map(sz => ({
        size: sz,
        items: items.filter(e => (e.size || '').toLowerCase() === sz),
        cap: hp ? (hp[sz] || 0) : null,
      }));
      const slotsText = sizeGroups.map(g => {
        const fitted = g.items.reduce((a, e) => a + e.count, 0);
        return (g.cap != null ? `${fitted}/${g.cap}` : `${fitted}`) + ` ${g.size.toUpperCase()}`;
      }).join(' · ');
      const body = sizeGroups.map(g => {
        const fitted = g.items.reduce((a, e) => a + e.count, 0);
        const box = SIZE_BOX[g.size] || SIZE_BOX.s;
        const subHd = `<div class="dsub-hd">
          <span class="dsub-badge" style="color:${box.hex};background:${box.bg};border-color:${box.hex}">${g.size.toUpperCase()}</span>
          <span class="dsub-cnt">${g.cap != null ? `${fitted} / ${g.cap}` : fitted}</span></div>`;
        const rows = g.items.map(e => {
          const mk = e.mk ? ` Mk${e.mk}` : '';
          return `<div class="drow">
            <span class="dcnt">${e.count}×</span>${designBadge(e.race)}
            <span class="dnm">${e.name}${mk}</span>
            ${statCells(e, defs)}
            <span class="dcost">${e.price != null ? designCr(e.price) : '—'}</span>
          </div>`;
        }).join('');
        return `<div class="dsub-box" style="border-color:${hexA(box.hex, 0.3)};background:${box.bg}">${subHd}${rows}</div>`;
      }).join('');
      equip += section(slot, label, slotsText, headerRow(defs) + body);
    }
    if (!equip) equip = `<div style="padding:30px 10px;text-align:center;color:var(--text-dim);font-size:12px">No equipment fitted.</div>`;

    // ── Hull preview (right half) — the swappable view, Hull/wireframe is the
    // only one built so far; more views (loadout diagram, stats) can slot in
    // alongside it later without touching the equipment column. ──────────────
    const facColour = FACTION_COLOURS[(d.hullFaction || '').toLowerCase()] || '#2dd4bf';
    const hullPanel = `<div class="dhull" style="--dhull-border:${hexA(facColour, 0.35)};--dhull-glow:${hexA(facColour, 0.1)}">
      <div class="dhull-hd"><i class="ti ti-ufo" style="color:${facColour}"></i><span class="lbl">Hull</span></div>
      <div class="dhull-wire">${WIRE_SVG}</div>
      <div class="dhull-id">${designBadge(d.hullFaction)}<span class="dhull-nm">${d.type}</span></div>
      <div class="dhull-stats">
        <div class="dhull-stat"><span class="dhs-lbl">Type</span><span class="dhs-val">${d.role || '—'}</span></div>
        <div class="dhull-stat"><span class="dhs-lbl">Size</span><span class="dhs-val">${d.hullSize || '—'}</span></div>
        <div class="dhull-stat"><span class="dhs-lbl">Hull HP</span><span class="dhs-val">${d.hullMax != null ? designCr(d.hullMax) : '—'}</span></div>
        <div class="dhull-stat"><span class="dhs-lbl">Hull Cost</span><span class="dhs-val">${d.hullPrice != null ? designCr(d.hullPrice) : '—'}</span></div>
      </div>
    </div>`;

    const n = d.ships.length;
    const chips = d.ships.map(s =>
      `<span onclick="jumpToShip('${s.code}')" style="cursor:pointer;font-family:var(--font-mono);font-size:11px;color:var(--teal);border:1px solid var(--border);border-radius:2px;padding:2px 8px">${s.code}${s.name ? ' · ' + s.name : ''}</span>`
    ).join('');

    // Summary strip — size badge, faction badge, ship count — lives in the
    // <summary> itself so it stays visible when the card is collapsed, not
    // just the bare title.
    const sizeTint = SIZE_TINT[d.hullSize] || SIZE_TINT.S;
    const summaryMeta = `<span class="dcard-meta">
      <span class="dcard-size-badge" style="color:${sizeTint.c};background:${sizeTint.bg};border-color:${sizeTint.c}">${d.hullSize || '—'}</span>
      ${designBadge(d.hullFaction)}
      <span class="dcard-meta-used">used by <b style="color:var(--lime)">${n}</b> ship${n > 1 ? 's' : ''}</span>
    </span>`;

    // Native <details> for the whole-card collapse (same idiom as the Sectors
    // tab's "Your Ships" set) — collapses down to just the <summary> title bar.
    // Open state is keyed off designsCollapsed (by signature) rather than a
    // hardcoded attribute, since this markup gets rebuilt from scratch on
    // every render and would otherwise forget any card the user collapsed.
    const isOpen = !designsCollapsed.has(d.sig);
    return `<details class="panel dcard" data-sig="${d.sig}" ${isOpen ? 'open' : ''}>
      <summary class="dcard-hd">
        <i class="ti ti-vector-triangle" style="color:${facColour};font-size:16px"></i>
        <span class="dcard-title">${d.type}${d.config}</span>
        ${summaryMeta}
        <i class="ti ti-chevron-down dcard-chev"></i>
      </summary>
      <div class="dcard-body">
        <div class="dcard-equip">${equip}</div>
        ${hullPanel}
      </div>
      <div class="dcard-footer">
        <span class="dcard-used" id="design-used-${idx}" onclick="toggleDesignShips(${idx})">used by <b style="color:var(--lime)">${n}</b> ship${n > 1 ? 's' : ''} <i class="ti ti-chevron-down"></i></span>
        <span class="dcard-total-val">Design total <b>${designCr(d.totalCost)}</b> <span style="font-size:11px;color:var(--text-dim)">Cr</span></span>
      </div>
      <div id="design-ships-${idx}" class="dcard-ships">${chips}</div>
    </details>`;
  }

  function toggleDesignShips(idx) {
    const el = document.getElementById('design-ships-' + idx);
    if (!el) return;
    const open = el.style.display !== 'flex';
    el.style.display = open ? 'flex' : 'none';
    document.getElementById('design-used-' + idx)?.classList.toggle('open', open);
  }

  // ══ SHIP BUILDER (interactive blueprint builder) ═══════════════════════════
  // Reuses the design-card layout (.dsect sections, SLOT_META, SLOT_STATS,
  // designBadge, WIRE_SVG) but makes it editable. State: chosen hull + per-slot
  // fitted equipment. fits[slot] = [{macro, count}].
  // factionFilter: array of selected race strings; empty array means "all factions".
  let builderState = { hull: null, name: '', fits: {}, selectedSlot: null, selectedSize: null, factionFilter: [] };

  // Whether the equipment card's faction filter dropdown is open. Tracked
  // outside builderState since renderBuilder() rebuilds the DOM from scratch —
  // a plain CSS class on the menu element wouldn't survive a re-render
  // triggered by checking another box, so the open/closed state has to live
  // in JS and get reapplied each render instead.
  let beqfOpen = false;

  // Full names for the maker races that show up in EQUIPMENT_CATALOG (e.race),
  // used by the equipment-list faction filter dropdown.
  const RACE_FULL_NAMES = {
    argon: 'Argon', paranid: 'Paranid', teladi: 'Teladi', split: 'Split',
    terran: 'Terran', boron: 'Boron', xenon: 'Xenon', khaak: "Kha'ak",
    pirate: 'Pirate', yaki: 'Yaki', generic: 'Generic',
  };
  // Equipment with no maker (e.g. most thrusters) carries no e.race at all —
  // bucket it under 'generic' so the faction filter can target it explicitly,
  // matching the neutral "GEN" badge designBadge() already shows for it.
  const raceKeyOf = e => (e.race || '').toLowerCase() || 'generic';
  const factionFilterBadge = r => r === 'generic' ? designBadge(null) : designBadge(r);

  // Singular slot label for the per-size "Fit Large Shield" button text —
  // DESIGN_SLOTS labels (Weapons, Turrets, ...) are plural for headers.
  const SLOT_SINGULAR = { weapon:'Weapon', turret:'Turret', shield:'Shield', engine:'Engine', thruster:'Thruster' };

  const HULL_FACTION_NAMES = {
    arg:'Argon', tel:'Teladi', par:'Paranid', tri:'Paranid', spl:'Split',
    ter:'Terran', bor:'Boron', xen:'Xenon', yak:'Yaki', pir:'Pirate',
    kha:"Kha'ak", atf:'Terran', pio:'Pioneer', gen:'Generic',
  };
  const hullFactionOf = m => HULL_FACTION_NAMES[(m.split('_')[1] || '')] || 'Other';
  const sizeFromClass = c => (c || '').replace('ship_', '');   // ship_m -> m
  const SIZE_WORD = { xs:'XS', s:'Small', m:'Medium', l:'Large', xl:'Extra Large' };

  // Called from the sidebar "Ship Builder" button. Picks a default hull (an
  // owned type if any) on first open, otherwise just re-renders current state.
  function initBuilder() {
    // Re-pick a default whenever there's no valid current hull (covers first
    // open and a stale hull no longer in the catalog) — also avoids a render loop.
    if (!builderState.hull || !HULL_CATALOG[builderState.hull]) {
      const owned = (allPlayerShips || []).map(s => s.macro).filter(m => HULL_CATALOG[m]);
      const def = owned[0] || Object.keys(HULL_CATALOG).sort()[0];
      if (def) { builderSelectHull(def); return; }
      document.getElementById('builder-root').innerHTML =
        '<div style="padding:60px;text-align:center;color:var(--text-dim)">No hull catalog loaded — run a scan first.</div>';
      return;
    }
    renderBuilder();
  }

  function builderSetName(v) { builderState.name = v; }

  function builderSelectHull(macro) {
    const hull = HULL_CATALOG[macro];
    builderState.hull = macro;
    builderState.fits = {};
    builderState.name = (hull ? hull.name : 'Ship') + ' · Custom';
    // Pre-select the first category this hull actually has slots for, and
    // within it the largest mount size — each size now has its own Fit
    // button, so the default selection needs a specific size, not just a slot.
    builderState.selectedSlot = null;
    builderState.selectedSize = null;
    for (const [s] of DESIGN_SLOTS) {
      const cap = builderCapacity(s);
      const sizes = Object.keys(cap).filter(sz => cap[sz] > 0).sort(bySizeDesc);
      if (sizes.length) { builderState.selectedSlot = s; builderState.selectedSize = sizes[0]; break; }
    }
    renderBuilder();
  }

  // Capacity {size: count} for a slot on the current hull. Thruster is a single
  // implicit slot at the hull's own size (it isn't a component connection).
  function builderCapacity(slot) {
    const hull = HULL_CATALOG[builderState.hull];
    if (!hull) return {};
    if (slot === 'thruster') { const s = {}; s[sizeFromClass(hull.class)] = 1; return s; }
    return (hull.hardpoints && hull.hardpoints[slot]) || {};
  }
  function builderFittedBySize(slot) {
    const out = {};
    for (const f of (builderState.fits[slot] || [])) {
      const sz = (EQUIPMENT_CATALOG[f.macro] || {}).size || '?';
      out[sz] = (out[sz] || 0) + f.count;
    }
    return out;
  }

  function builderSelect(slot, size) {
    builderState.selectedSlot = slot;
    builderState.selectedSize = size;
    builderState.factionFilter = [];   // each card starts unfiltered
    beqfOpen = false;
    renderBuilder();
  }
  function builderFitAdd(slot, macro) {
    const sz  = (EQUIPMENT_CATALOG[macro] || {}).size || '?';
    if ((builderFittedBySize(slot)[sz] || 0) >= (builderCapacity(slot)[sz] || 0)) return;
    const fits = builderState.fits[slot] = builderState.fits[slot] || [];
    const ex = fits.find(f => f.macro === macro);
    if (ex) ex.count++; else fits.push({ macro, count: 1 });
    renderBuilder();   // stay on this category so several items can be fitted
  }
  function builderCount(slot, macro, delta) {
    const fits = builderState.fits[slot] || [];
    const f = fits.find(x => x.macro === macro);
    if (!f) return;
    if (delta > 0) {
      const sz = (EQUIPMENT_CATALOG[macro] || {}).size || '?';
      if ((builderFittedBySize(slot)[sz] || 0) >= (builderCapacity(slot)[sz] || 0)) return;
    }
    f.count += delta;
    if (f.count <= 0) builderState.fits[slot] = fits.filter(x => x !== f);
    renderBuilder();
  }

  // Toggling "All factions" clears the selection (empty array = unfiltered);
  // toggling a race adds/removes just that one, so several can be checked at once.
  function builderToggleFactionFilter(race) {
    if (race === 'all') {
      builderState.factionFilter = [];
    } else {
      const sel = builderState.factionFilter;
      const i = sel.indexOf(race);
      if (i >= 0) sel.splice(i, 1); else sel.push(race);
    }
    renderBuilder();   // beqfOpen stays true, so the menu re-renders open
  }
  function toggleEqFilterDropdown(e) {
    if (e) e.stopPropagation();   // don't let the outside-click handler close it
    beqfOpen = !beqfOpen;
    document.getElementById('beqf-menu')?.classList.toggle('open', beqfOpen);
  }
  function closeEqFilterDropdown() {
    beqfOpen = false;
    document.getElementById('beqf-menu')?.classList.remove('open');
  }
  // Any click outside the dropdown dismisses the open menu.
  document.addEventListener('click', (e) => {
    if (!e.target.closest('#beqf-dd')) closeEqFilterDropdown();
  });

  // Faction filter dropdown for the "Available · ..." equipment card — narrows
  // the right pane's options to any number of maker races (plus a 'generic'
  // bucket for unmade parts). Only built (and only offered) for races actually
  // present among the current slot+size's equipment, so it never shows an
  // empty "Boron" option on a card with no Boron parts.
  function builderEqFilterDD(slot, size) {
    const items = Object.values(EQUIPMENT_CATALOG).filter(e => e.slot === slot && e.size === size);
    const races = [...new Set(items.map(raceKeyOf))].sort();
    if (!races.length) return '';

    const selected = builderState.factionFilter;
    const triggerInner = selected.length === 0
      ? 'All factions'
      : selected.map(factionFilterBadge).join('');

    const rows = ['all', ...races].map(r => {
      const isSel = r === 'all' ? selected.length === 0 : selected.includes(r);
      const label = r === 'all' ? 'All factions' : (RACE_FULL_NAMES[r] || r);
      const badge = r === 'all' ? '' : factionFilterBadge(r);
      return `<div class="beqf-item ${isSel ? 'sel' : ''}" onclick="builderToggleFactionFilter('${r}')">
        <span class="beqf-check ${isSel ? 'sel' : ''}"></span>${badge}<span>${label}</span>
      </div>`;
    }).join('');

    return `<div class="beqf-dd" id="beqf-dd">
      <div class="beqf-trigger" onclick="toggleEqFilterDropdown(event)">${triggerInner}<i class="ti ti-chevron-down"></i></div>
      <div class="beqf-menu ${beqfOpen ? 'open' : ''}" id="beqf-menu">${rows}</div>
    </div>`;
  }

  function builderHullSelect() {
    const byFac = {};
    for (const [m, h] of Object.entries(HULL_CATALOG))
      (byFac[hullFactionOf(m)] = byFac[hullFactionOf(m)] || []).push([m, h]);
    const groups = Object.keys(byFac).sort().map(fac => {
      const opts = byFac[fac].sort((a, b) => a[1].name.localeCompare(b[1].name)).map(([m, h]) =>
        `<option value="${m}" ${m === builderState.hull ? 'selected' : ''}>${h.name} · ${SIZE_WORD[sizeFromClass(h.class)] || sizeFromClass(h.class).toUpperCase()}${h.purchasable === false ? ' · Capture Only' : ''}</option>`).join('');
      return `<optgroup label="${fac}">${opts}</optgroup>`;
    }).join('');
    // Ship icon + native select (grouped by faction); option text carries the
    // spelled-out size, e.g. "Cerberus Vanguard · Medium".
    return `<div class="bhull"><i class="ti ti-rocket" style="color:var(--teal);font-size:16px"></i><select onchange="builderSelectHull(this.value)">${groups}</select></div>`;
  }

  function renderBuilder() {
    const root = document.getElementById('builder-root');
    const hull = HULL_CATALOG[builderState.hull];
    if (!hull) { initBuilder(); return; }

    let total = hull.price || 0;
    const sel = builderState.selectedSlot;
    const selSize = builderState.selectedSize;

    // ── LEFT pane: a card per category, split into one outlined box per mount
    // size with its own "Fit Large Shield · 2 free" button — picking a size's
    // Fit button (not the whole category) is what drives the right pane below,
    // so the equipment list it shows is always scoped to one specific size. ──
    let left = '';
    for (const [slot, label] of DESIGN_SLOTS) {
      const cap = builderCapacity(slot);
      const capTotal = Object.values(cap).reduce((a, b) => a + b, 0);
      if (!capTotal) continue;   // hull has no slots of this type
      const m = SLOT_META[slot];
      const fits = builderState.fits[slot] || [];
      const fittedBySize = builderFittedBySize(slot);
      const sizesSorted = Object.keys(cap).sort(bySizeDesc);
      const capText = sizesSorted.map(sz => `${fittedBySize[sz] || 0}/${cap[sz]} ${sz.toUpperCase()}`).join(' · ');

      const groups = sizesSorted.map(sz => {
        const box = SIZE_BOX[sz] || SIZE_BOX.s;
        const szFits = fits.filter(f => ((EQUIPMENT_CATALOG[f.macro] || {}).size || '?') === sz);
        const itemRows = szFits.map(f => {
          const e = EQUIPMENT_CATALOG[f.macro] || { name: f.macro };
          if (e.price) total += e.price * f.count;
          const mk = e.mk ? ` Mk${e.mk}` : '';
          return `<div class="bfr">
            <span class="bstep"><span class="bsb" onclick="builderCount('${slot}','${f.macro}',-1)">−</span><span class="bcbox">${f.count}</span><span class="bsb" onclick="builderCount('${slot}','${f.macro}',1)">+</span></span>
            <span style="font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${e.name}${mk}</span>
          </div>`;
        }).join('');
        const free = cap[sz] - (fittedBySize[sz] || 0);
        const isSel = sel === slot && selSize === sz;
        const fitBtn = free > 0
          ? `<div class="bfit" onclick="builderSelect('${slot}','${sz}')"><i class="ti ti-plus" style="font-size:11px;vertical-align:-1px"></i> Fit ${SIZE_WORD[sz] || sz.toUpperCase()} ${SLOT_SINGULAR[slot] || label} · ${free} free</div>`
          : '';
        return `<div class="bsub-box ${isSel ? 'sel' : ''}" style="border-color:${hexA(box.hex, 0.3)};background:${box.bg}">
          <div class="bsub-hd"><span class="bsub-badge" style="color:${box.hex};background:${box.bg};border-color:${box.hex}">${sz.toUpperCase()}</span><span class="bsub-cnt">${fittedBySize[sz] || 0} / ${cap[sz]}</span></div>
          ${itemRows}${fitBtn}
        </div>`;
      }).join('');

      left += `<div class="bcat">
        <div class="bcat-h" style="background:${m.tint}"><i class="ti ${m.icon}" style="color:${m.color}"></i><span class="lbl">${label}</span><span class="cap">${capText}</span></div>
        ${groups}
      </div>`;
    }

    // ── RIGHT pane: available equipment for the selected size, with stats ────
    let right;
    if (sel && selSize) {
      const cap = builderCapacity(sel);
      const defs = SLOT_STATS[sel] || [];
      const m = SLOT_META[sel];
      const fitted = new Set((builderState.fits[sel] || []).map(f => f.macro));
      const full = (builderFittedBySize(sel)[selSize] || 0) >= cap[selSize];
      const label = (DESIGN_SLOTS.find(([s]) => s === sel) || [, sel])[1];

      const statCells = e => [0,1,2,3].map(i => {
        if (!defs[i]) return '<span></span>';
        const v = e[defs[i][0]];
        return `<span class="dst">${v != null ? defs[i][2](v) : '—'}</span>`;
      }).join('');
      const headerCells = [0,1,2,3].map(i => `<span class="boh">${defs[i] ? defs[i][1] : ''}</span>`).join('');

      // Weapon/turret rows carry data-weapon-tip for the full stat hover
      // (sectors.js's shared tooltip dispatcher) — shields/engines/thrusters
      // don't have the damage/heat fields it shows, so skip them for now.
      // shipHeatFactor rides along in the payload: Time to Overheat is
      // genuinely ship-dependent (the selected hull's <modifiers><weapon
      // heat=>, confirmed against real tooltips this session — Sustained
      // Damage and Cooldown Duration are NOT affected by it), so the tooltip
      // needs to know which hull is currently selected to show it correctly.
      const wantsTip = sel === 'weapon' || sel === 'turret';
      const shipHeatFactor = (HULL_CATALOG[builderState.hull] || {}).weapon_heat_factor || 1;
      const factionFilter = builderState.factionFilter;
      const opts = Object.entries(EQUIPMENT_CATALOG)
        .filter(([, e]) => e.slot === sel && e.size === selSize &&
          (factionFilter.length === 0 || factionFilter.includes(raceKeyOf(e))))
        .sort((a, b) => (a[1].price || 0) - (b[1].price || 0))
        .map(([mac, e]) => {
          const on = fitted.has(mac);
          const tipAttr = wantsTip ? ` data-weapon-tip="${encodeURIComponent(JSON.stringify({...e, _shipHeatFactor: shipHeatFactor}))}"` : '';
          return `<div class="borow ${on ? 'on' : ''}" onclick="builderFitAdd('${sel}','${mac}')"${tipAttr}>
            ${designBadge(e.race)}<span style="font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;${on ? 'color:var(--lime)' : ''}">${e.name}${e.mk ? ` Mk${e.mk}` : ''}</span>
            ${statCells(e)}<span class="dcost">${e.price != null ? designCr(e.price) : '—'}</span>
            <i class="ti ${on ? 'ti-check' : 'ti-plus'}" style="color:var(--lime);font-size:13px"></i></div>`;
        }).join('');

      // In-Game/True Stats toggle for the hover tooltip's derived combat stats
      // (see setWeaponStatsMode + weaponTipHtml in tooltips.js) -- only
      // meaningful for weapon/turret cards, which are the only ones that
      // carry data-weapon-tip at all. One button: red = off (in-game,
      // truncated like the real tooltip), green = on (raw 3dp, no truncation).
      const trueOn = weaponStatsMode === 'true';
      const statsToggle = wantsTip ? `<button class="bstats-toggle ${trueOn ? 'on' : ''}"
          onclick="setWeaponStatsMode('${trueOn ? 'ingame' : 'true'}')"
          title="${trueOn ? 'Showing True Stats (raw, 3dp, no truncation) — click for In-Game' : 'Showing In-Game stats (truncated to match the real tooltip) — click for True Stats'}">
          <i class="ti ti-flask" style="font-size:11px"></i> True Stats</button>` : '';

      right = `<div class="bopts">
        <div class="bopts-h"><i class="ti ${m.icon}" style="color:${m.color};font-size:15px"></i><span class="lbl">Available · ${SIZE_WORD[selSize] || selSize.toUpperCase()} ${label}</span>${builderEqFilterDD(sel, selSize)}${statsToggle}<span class="mt">${selSize.toUpperCase()} mount${full ? ' · full' : ''}</span></div>
        <div style="padding:5px 8px">
          <div class="borow"><span></span><span></span>${headerCells}<span class="boh">Cost</span><span></span></div>
          ${opts || '<div style="color:var(--text-dim);font-size:11px;padding:8px">No compatible equipment.</div>'}
        </div></div>`;
    } else {
      right = `<div class="bopts" style="padding:30px;text-align:center;color:var(--text-dim)">Select a Fit button to choose equipment for that mount size.</div>`;
    }

    root.innerHTML = `
      <div class="bhdr">
        <div class="bfield" style="flex:1;min-width:200px"><span class="blbl">Blueprint name</span>
          <input class="binput" value="${(builderState.name || '').replace(/"/g, '&quot;')}" oninput="builderSetName(this.value)"></div>
        <div class="bfield"><span class="blbl">Hull</span>${builderHullSelect()}</div>
        <button class="bsave" onclick="builderSave()"><i class="ti ti-device-floppy" style="font-size:13px;vertical-align:-2px"></i> Save</button>
      </div>
      <div class="btwo"><div>${left}</div>${right}</div>
      <div style="display:flex;align-items:baseline;gap:10px;border-top:1px solid var(--border);margin-top:10px;padding-top:9px">
        <span style="font-family:var(--font-cond);font-weight:600;font-size:13px;letter-spacing:0.06em;text-transform:uppercase;color:var(--text-dim)">Design total</span>
        <span style="margin-left:auto;font-family:var(--font-mono);font-size:17px;color:var(--amber)">${designCr(total)} <span style="font-size:11px;color:var(--text-dim)">Cr</span></span>
      </div>`;
  }

  function builderSave() {
    // Persistence (ship_designs table + bridge save/load) is the next batch.
    alert('Saving blueprints lands in the next step (persistence).');
  }


  // Full faction names for factions that don't appear in the reputation data
  // (Xenon, Kha'ak, and non-playable groups are excluded from rep).
  const FACTION_FULL_NAMES_FALLBACK = {
    xenon:            'Xenon',
    khaak:            "Kha'ak",
    scavenger:        'Scavengers',
    ownerless:        'Ownerless',
    civilian:         'Civilian',
    buccaneers:       "Duke's Buccaneers",
    holyorderfanatic: 'Holy Order Faithful',
  };

  // Maps faction owner IDs to their in-game tag codes (mirrors data/factions.py).
  const FACTION_LABELS = {
    argon: 'ARG',      antigone: 'ANT',    hatikvah: 'HAT',
    paranid: 'PAR',    trinity: 'TRI',     split: 'ZYA',
    fallensplit: 'FAF', freesplit: 'FRF',  teladi: 'TEL',
    ministry: 'MIN',   xenon: 'XEN',       khaak: 'KHK',
    buccaneers: 'BUC', scaleplate: 'SCA',  loanshark: 'RIP',
    holyorder: 'HOP',  holyorderfanatic: 'HOF', yaki: 'YAK',
    pioneers: 'PIO',   terran: 'TER',      boron: 'BOR',
    scavenger: 'SCG',  ownerless: 'OWN',   civilian: 'CIV',
  };

  // Faction colour palette, keyed by owner ID.
  // Grouped by political bloc to keep related factions visually similar.
  const FACTION_COLOURS = {
    // Argon bloc — blues
    argon:            '#388bfd',
    antigone:         '#58a6ff',
    hatikvah:         '#79c0ff',
    // Paranid bloc — purples
    paranid:          '#a371f7',
    holyorder:        '#bc8cff',
    holyorderfanatic: '#d2a8ff',
    trinity:          '#8957e5',
    // Teladi bloc — greens
    teladi:           '#70d890',
    ministry:         '#56d364',
    scaleplate:       '#3fb950',
    // Split bloc — oranges
    split:            '#e3673a',
    freesplit:        '#f0883e',
    fallensplit:      '#c75c32',
    // Terran bloc — cyan
    terran:           '#39d5f0',
    pioneers:         '#d29922',
    // Hostiles — red
    xenon:            '#f85149',
    khaak:            '#f85149',
    // Fringe factions — amber/muted
    yaki:             '#e3b341',
    buccaneers:       '#e3b341',
    loanshark:        '#ff7b72',
    boron:            '#76e3ea',
    scavenger:        '#6e7681',
    ownerless:        '#6e7681',
    civilian:         '#6e7681',
  };

  const HOSTILE_FACTIONS = new Set(['xenon', 'khaak']);

