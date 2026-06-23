  // Core role: Read-only sortable tables for equipment catalog and hull statistics (hulls, weapons, shields, engines).
  // Reuses EQUIPMENT_CATALOG and HULL_CATALOG globals from designs-builder.js; no backend computation.

  let reslibCat     = 'hull';
  let reslibSortKey = null;
  let reslibSortDir = 1;

  // Hulls get a second page (the per-hull detail "Hull Inspector", reached
  // by clicking a row in Hull List) — every other category is a single table
  // and never touches these. reslibInspectMacro is kept around (not cleared
  // on returning to the list) so re-opening Inspector via the tab lands back
  // on the last hull you looked at instead of nothing.
  let reslibHullView     = 'list';   // 'list' | 'inspect'
  let reslibInspectMacro = null;
  let reslibHullFilters  = { faction: '', size: '', type: '' };

  // Equipment categories (weapon/turret/shield/engine/thruster) now mirror the
  // hull List/Comparison split. The two-item picks themselves live in
  // equipment-comparison.js (reslibEquipCmpA/B), this is just which sub-view is
  // showing — reset to 'list' whenever the category changes (switchResLibCat).
  let reslibEquipView    = 'list';   // 'list' | 'compare'

  const RESLIB_CAT_LABELS = {
    hull: 'Hulls', weapon: 'Weapons', turret: 'Turrets', shield: 'Shields',
    engine: 'Engines', thruster: 'Thrusters', software: 'Software', item: 'Items',
  };

  // Fallback role guesser for rare hulls without <ship type=...> in their macro (covers ~91%).
  // Extracts multi-word role names (miner_liquid, trans_container) for display.
  function hullTypeOf(macro) {
    const parts = macro.split('_');
    const out = [];
    for (let i = 3; i < parts.length; i++) {
      if (parts[i] === 'macro' || /^\d/.test(parts[i])) break;
      out.push(parts[i]);
    }
    return out.join('_') || 'other';
  }
  // Game type values without separators (heavyfighter, largeminer) need explicit labels.
  const HULL_TYPE_LABELS = {
    heavyfighter: 'Heavy Fighter', largeminer: 'Large Miner',
    personalvehicle: 'Personal Vehicle', xsdrone: 'XS Drone',
    smalldrone: 'Small Drone', distressdrone: 'Distress Drone',
    escapepod: 'Escape Pod', lasertower: 'Laser Tower',
  };
  const hullTypeLabel = t => HULL_TYPE_LABELS[t] ||
    t.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');

  // Real role classification from the game's own macro XML (generate_data.py's
  // ship_type field — see data/ship_stats.py), falling back to the macro-id
  // guess only for the handful of hulls missing it.
  const hullTypeFor = (macro, h) => (h && h.ship_type) || hullTypeOf(macro);

  // Real faction from <identification makerrace=...> (lowercase race key,
  // same space as equipment's race field), mapped through the same
  // RACE_FULL_NAMES table the equipment faction filter uses, falling back to
  // the macro-id guess (hullFactionOf) for the handful of hulls with no
  // makerrace attribute.
  const hullFactionFor = (macro, h) => {
    const mr = ((h && h.makerrace) || '').toLowerCase();
    if (mr) return RACE_FULL_NAMES[mr] || (mr.charAt(0).toUpperCase() + mr.slice(1));
    return hullFactionOf(macro);
  };

  // Visibility is pure CSS (.reslib-wrap:hover .reslib-menu) — this just keeps
  // the fixed-position menu's coordinates pinned to the sidebar item, since
  // position:fixed can't use the usual left:100% trick (see layout.css).
  // Recomputed on every mouseenter rather than cached, so it stays correct
  // even if the sidebar scrolled or the window resized since last time.
  function positionReslibMenu() {
    const wrap = document.getElementById('reslib-wrap');
    const menu = document.getElementById('reslib-menu');
    if (!wrap || !menu) return;
    const r = wrap.getBoundingClientRect();
    menu.style.left = r.right + 'px';
    menu.style.top  = r.top + 'px';
  }
  document.getElementById('reslib-wrap')?.addEventListener('mouseenter', positionReslibMenu);

  // Called from the sidebar flyout: the only way into this tab — there is no
  // page-to-page nav link inside Resource Library itself, by design.
  function openResLib(cat) {
    switchTab('reslib', document.getElementById('nav-naval'));
    switchResLibCat(cat);
  }

  function switchResLibCat(cat) {
    reslibCat       = cat;
    reslibSortKey   = null;
    reslibSortDir   = 1;
    reslibHullView  = 'list';
    reslibHullFilters = { faction: '', size: '', type: '' };
    // Drop any comparison picks from the previous category — a weapon macro
    // wouldn't resolve against, say, the shield catalog (see equipment-comparison.js).
    reslibEquipView = 'list';
    reslibEquipCmpA = null;
    reslibEquipCmpB = null;
    renderResLibHeader();
    renderResLib();
  }

  function reslibSetSort(key) {
    if (key === reslibSortKey) reslibSortDir *= -1;
    else { reslibSortKey = key; reslibSortDir = 1; }
    renderResLib();
  }

  // Builds #reslib-header: the page title for every category except Hulls,
  // which instead gets the List/Inspector tab switch (+ Faction/Size/Type
  // filters under it on the List tab) in place of a static title — so the
  // header always reflects the page you're actually looking at.
  function renderResLibHeader() {
    const header = document.getElementById('reslib-header');
    if (reslibCat !== 'hull') {
      // Equipment categories with a stat-column definition (everything except
      // the not-yet-catalogued Software/Items placeholders) get the same
      // List/Comparison tab switch the hull header has, in place of a static
      // title. Software/Items fall through to the plain title below.
      if (RESLIB_EQUIP_COLUMNS[reslibCat]) {
        const singular = SLOT_SINGULAR[reslibCat] || RESLIB_CAT_LABELS[reslibCat];
        const tabs = `<div class="fleet-subtabs">
          <div class="fleet-subtab ${reslibEquipView === 'list' ? 'active' : ''}" onclick="reslibShowEquipList()"><i class="ti ti-list"></i> ${singular} List</div>
          <div class="fleet-subtab ${reslibEquipView === 'compare' ? 'active' : ''}" onclick="reslibShowEquipCompare()"><i class="ti ti-arrows-left-right"></i> ${singular} Comparison</div>
        </div>`;
        // Match the hull header: a "<Category> Comparison" title under the tabs
        // on the compare view; the List view's tabs stand on their own (no
        // filter row exists for equipment).
        const row2 = reslibEquipView === 'compare'
          ? `<div class="sec-header"><div class="sec-title">${singular} Comparison</div><div class="sec-line"></div></div>`
          : '';
        header.innerHTML = tabs + row2;
        return;
      }
      header.innerHTML = `<div class="sec-header"><div class="sec-title">${RESLIB_CAT_LABELS[reslibCat]}</div><div class="sec-line"></div></div>`;
      return;
    }

    const tabs = `<div class="fleet-subtabs">
      <div class="fleet-subtab ${reslibHullView === 'list' ? 'active' : ''}" onclick="reslibShowHullList()"><i class="ti ti-list"></i> Hull List</div>
      <div class="fleet-subtab ${reslibHullView === 'inspect' ? 'active' : ''} ${reslibInspectMacro ? '' : 'disabled'}" onclick="reslibInspectMacro && reslibShowHullInspector(reslibInspectMacro)"><i class="ti ti-zoom-in"></i> Hull Inspector</div>
      <div class="fleet-subtab ${reslibHullView === 'compare' ? 'active' : ''}" onclick="reslibShowHullCompare()"><i class="ti ti-arrows-left-right"></i> Hull Comparison</div>
    </div>`;

    const row2 = reslibHullView === 'list' ? reslibHullFiltersHtml() : reslibHullView === 'compare' ? (() => {
      return `<div class="sec-header"><div class="sec-title">Hull Comparison</div><div class="sec-line"></div></div>`;
    })() : (() => {
      const h = HULL_CATALOG[reslibInspectMacro] || {};
      return `<div class="sec-header"><div class="sec-title">${h.name || reslibInspectMacro}</div><div class="sec-line"></div></div>`;
    })();

    header.innerHTML = tabs + row2;
  }

  // Distinct Faction/Size/Type values actually present in the loaded hull
  // catalog, so the dropdowns never offer an option that would filter to
  // nothing (e.g. a faction with no purchasable hulls this scan).
  function reslibHullFilterOptions() {
    const factions = new Set(), sizes = new Set(), types = new Set();
    for (const macro of Object.keys(HULL_CATALOG)) {
      const h = HULL_CATALOG[macro];
      factions.add(hullFactionFor(macro, h));
      sizes.add(sizeFromClass(h.class));
      types.add(hullTypeFor(macro, h));
    }
    return { faction: [...factions].sort(), size: [...sizes].sort(bySizeDesc), type: [...types].sort() };
  }

  function reslibHullFiltersHtml() {
    const opts = reslibHullFilterOptions();
    const select = (key, label, values, fmt) => {
      const options = [`<option value="">All ${label}</option>`].concat(
        values.map(v => `<option value="${v}" ${reslibHullFilters[key] === v ? 'selected' : ''}>${fmt ? fmt(v) : v}</option>`)
      ).join('');
      return `<div class="reslib-fbox"><select onchange="reslibSetHullFilter('${key}', this.value)">${options}</select></div>`;
    };
    return `<div class="reslib-filters">
      ${reslibFactionDD(opts.faction)}
      ${select('size', 'Sizes', opts.size, v => SIZE_WORD[v] || v.toUpperCase())}
      ${select('type', 'Types', opts.type, hullTypeLabel)}
    </div>`;
  }

  function reslibSetHullFilter(key, value) {
    reslibHullFilters[key] = value;
    renderResLib();
  }

  // Faction filter — a custom badge+label dropdown instead of a plain
  // <select>, reusing the same .beqf-dd/.beqf-trigger/.beqf-menu markup (and
  // designBadge()) the Ship Builder's equipment faction filter already uses,
  // so the faction picker reads the same way everywhere in the app rather
  // than falling back to bare option text the one place it's a single-select.
  let reslibFacOpen = false;
  const reslibEscJs = s => String(s).replace(/'/g, "\\'");

  function reslibFactionDD(factions) {
    const selected = reslibHullFilters.faction;
    const triggerInner = selected ? `${designBadge(selected)}<span>${selected}</span>` : '<span>All Factions</span>';
    const rows = ['', ...factions].map(fac => {
      const isSel = selected === fac;
      const label = fac === '' ? 'All Factions' : fac;
      const badge = fac === '' ? '' : designBadge(fac);
      return `<div class="beqf-item ${isSel ? 'sel' : ''}" onclick="reslibSetHullFactionFilter('${reslibEscJs(fac)}')">${badge}<span>${label}</span></div>`;
    }).join('');
    return `<div class="beqf-dd" id="reslib-fac-dd">
      <div class="beqf-trigger" onclick="reslibToggleFacDD(event)">${triggerInner}<i class="ti ti-chevron-down"></i></div>
      <div class="beqf-menu ${reslibFacOpen ? 'open' : ''}" id="reslib-fac-menu">${rows}</div>
    </div>`;
  }
  function reslibToggleFacDD(e) {
    e.stopPropagation();
    reslibFacOpen = !reslibFacOpen;
    document.getElementById('reslib-fac-menu')?.classList.toggle('open', reslibFacOpen);
  }
  function reslibCloseFacDD() {
    reslibFacOpen = false;
    document.getElementById('reslib-fac-menu')?.classList.remove('open');
  }
  document.addEventListener('click', (e) => {
    if (!e.target.closest('#reslib-fac-dd')) reslibCloseFacDD();
  });
  function reslibSetHullFactionFilter(faction) {
    reslibHullFilters.faction = faction;
    reslibCloseFacDD();
    renderResLibHeader();   // trigger badge/label is custom markup, needs a full rebuild
    renderResLib();
  }

  function reslibShowHullList() {
    reslibHullView = 'list';
    renderResLibHeader();
    renderResLib();
  }

  function reslibShowHullInspector(macro) {
    reslibHullView     = 'inspect';
    reslibInspectMacro = macro;
    renderResLibHeader();
    renderResLib();
  }

  // Per-category column definitions: [data key, header label, formatter,
  // align-right]. Reuses the same designCr()/SIZE_WORD/designBadge helpers
  // the Ship Builder's catalog cards use, so numbers read identically
  // wherever they show up in the app (no abbreviation, full credit figures).
  const RESLIB_EQUIP_COLUMNS = {
    weapon:   [['damage_hull','Damage',v=>designCr(v),true], ['range_m','Range',v=>(v/1000).toFixed(1)+' km',true], ['reload_rate','Rate',v=>v.toFixed(2)+'/s',true]],
    turret:   [['damage_hull','Damage',v=>designCr(v),true], ['range_m','Range',v=>(v/1000).toFixed(1)+' km',true], ['reload_rate','Rate',v=>v.toFixed(2)+'/s',true]],
    shield:   [['capacity','Capacity',v=>designCr(v),true], ['recharge_rate','Recharge',v=>designCr(v)+'/s',true], ['recharge_delay','Delay',v=>v+' s',true]],
    engine:   [['thrust_forward','Forward',v=>designCr(v),true], ['travel_thrust','Travel',v=>Math.round(v),true], ['boost_thrust','Boost',v=>v!=null?Math.round(v):null,true]],
    thruster: [['strafe','Strafe',v=>designCr(v),true], ['pitch','Pitch',v=>designCr(v),true], ['yaw','Yaw',v=>designCr(v),true], ['roll','Roll',v=>designCr(v),true]],
  };

  // Placeholder copy for the two categories with no data source yet.
  const RESLIB_PLACEHOLDER = {
    software: {
      icon: 'ti-cpu',
      title: 'Software not catalogued yet',
      body: 'Ship and station software (trade/mining/scan upgrades, etc.) isn’t read out of the game files yet — only hulls and hardpoint equipment are. This page is reserved for it.',
    },
    item: {
      icon: 'ti-box',
      title: 'Items not catalogued yet',
      body: 'Inventory items (deployables, consumables, etc.) aren’t read out of the game files yet — only hulls and hardpoint equipment are. This page is reserved for them.',
    },
  };

  function reslibShowEmpty(icon, title, body) {
    document.getElementById('reslib-panel').style.display = 'none';
    document.getElementById('reslib-inspector').style.display = 'none';
    document.getElementById('reslib-compare').style.display = 'none';
    const empty = document.getElementById('reslib-empty');
    empty.style.display = 'flex';
    document.getElementById('reslib-empty-icon').className = 'ti ' + icon;
    document.getElementById('reslib-empty-title').textContent = title;
    document.getElementById('reslib-empty-body').textContent = body;
  }

  function renderResLib() {
    const cat = reslibCat;

    if (RESLIB_PLACEHOLDER[cat]) {
      const p = RESLIB_PLACEHOLDER[cat];
      reslibShowEmpty(p.icon, p.title, p.body);
      return;
    }

    if (cat === 'hull') {
      if (reslibHullView === 'inspect') { renderResLibHullInspector(); return; }
      if (reslibHullView === 'compare') { renderResLibHullCompare(); return; }
      renderResLibHulls();
      return;
    }
    if (reslibEquipView === 'compare') { renderResLibEquipCompare(); return; }
    renderResLibEquipment(cat);
  }

  function reslibSortHeader(key, label, active) {
    const arrow = active ? (reslibSortDir === 1 ? ' ↑' : ' ↓') : '';
    return `<th data-sort-key="${key}" class="${active ? 'sort-active' : ''}" onclick="reslibSetSort('${key}')">${label}${arrow}</th>`;
  }

  function reslibSortRows(rows, key, dir, fallbackName) {
    return rows.sort((a, b) => {
      const av = key ? a[key] : null;
      const bv = key ? b[key] : null;
      if (av == null && bv == null) return fallbackName(a).localeCompare(fallbackName(b));
      if (av == null) return 1;
      if (bv == null) return -1;
      if (av < bv) return -1 * dir;
      if (av > bv) return  1 * dir;
      return fallbackName(a).localeCompare(fallbackName(b));
    });
  }

  function renderResLibHulls() {
    if (!Object.keys(HULL_CATALOG).length) {
      reslibShowEmpty('ti-radar-2', 'No hull catalog loaded', 'Run a scan first — the hull catalog ships inside the scan export.');
      return;
    }
    document.getElementById('reslib-panel').style.display = '';
    document.getElementById('reslib-inspector').style.display = 'none';
    document.getElementById('reslib-compare').style.display = 'none';
    document.getElementById('reslib-empty').style.display = 'none';

    let rows = Object.entries(HULL_CATALOG).map(([macro, h]) => ({
      macro, name: h.name, faction: hullFactionFor(macro, h), size: sizeFromClass(h.class),
      type: hullTypeFor(macro, h), max_hull: h.max_hull, price: h.price,
      purchasable: h.purchasable !== false, hardpoints: h.hardpoints || {},
    }));
    const f = reslibHullFilters;
    if (f.faction) rows = rows.filter(r => r.faction === f.faction);
    if (f.size)    rows = rows.filter(r => r.size === f.size);
    if (f.type)    rows = rows.filter(r => r.type === f.type);
    rows = reslibSortRows(rows, reslibSortKey, reslibSortDir, r => r.name);

    document.getElementById('reslib-thead').innerHTML = `<tr>
      ${reslibSortHeader('name','Name', reslibSortKey==='name')}
      <th>Faction</th>
      ${reslibSortHeader('size','Class', reslibSortKey==='size')}
      ${reslibSortHeader('max_hull','Hull HP', reslibSortKey==='max_hull')}
      ${reslibSortHeader('price','Price', reslibSortKey==='price')}
      <th>Hardpoints</th>
    </tr>`;

    if (!rows.length) {
      document.getElementById('reslib-tbody').innerHTML =
        `<tr><td colspan="6" style="text-align:center;color:var(--text-dim);padding:3rem">No hulls match the selected filters.</td></tr>`;
      return;
    }

    document.getElementById('reslib-tbody').innerHTML = rows.map(r => {
      const tint = SIZE_TINT[(r.size || '').toUpperCase()] || { c: 'var(--text-dim)', bg: 'transparent' };
      const hp = ['weapon','turret','shield'].map(slot => {
        const cap = r.hardpoints[slot];
        if (!cap) return '';
        const total = Object.values(cap).reduce((a, b) => a + b, 0);
        if (!total) return '';
        const m = SLOT_META[slot];
        return `<span style="margin-right:1rem;white-space:nowrap"><i class="ti ${m.icon}" style="color:${m.color};font-size:1.2rem;vertical-align:-1px;margin-right:0.2rem"></i>${total}</span>`;
      }).join('');
      return `<tr style="cursor:pointer" onclick="reslibShowHullInspector('${r.macro}')">
        <td style="color:var(--text)">${r.name}</td>
        <td>${designBadge(r.faction)}</td>
        <td style="color:${tint.c}">${SIZE_WORD[r.size] || (r.size||'').toUpperCase()}</td>
        <td class="mono">${r.max_hull != null ? designCr(r.max_hull) : '—'}</td>
        <td class="mono">${r.price != null ? designCr(r.price) : '—'}</td>
        <td>${hp || '<span style="color:var(--text-faint)">—</span>'}${r.purchasable ? '' : ' <span class="badge neutral">Capture Only</span>'}</td>
      </tr>`;
    }).join('');
  }

  function renderResLibEquipment(slot) {
    const all = Object.entries(EQUIPMENT_CATALOG).filter(([, e]) => e.slot === slot);
    if (!Object.keys(EQUIPMENT_CATALOG).length) {
      reslibShowEmpty('ti-radar-2', 'No equipment catalog loaded', 'Run a scan first — the equipment catalog ships inside the scan export.');
      return;
    }
    document.getElementById('reslib-panel').style.display = '';
    document.getElementById('reslib-inspector').style.display = 'none';
    document.getElementById('reslib-compare').style.display = 'none';
    document.getElementById('reslib-empty').style.display = 'none';

    const defs = RESLIB_EQUIP_COLUMNS[slot] || [];
    let rows = all.map(([macro, e]) => ({ macro, ...e }));
    rows = reslibSortRows(rows, reslibSortKey, reslibSortDir, r => r.name || r.macro);

    const isMissile = e => e.class === 'missilelauncher' || e.class === 'missileturret';
    const wantsTip = slot === 'weapon' || slot === 'turret' || slot === 'shield' || slot === 'engine';

    document.getElementById('reslib-thead').innerHTML = `<tr>
      ${reslibSortHeader('name','Name', reslibSortKey==='name')}
      <th>Faction</th>
      ${reslibSortHeader('size','Size', reslibSortKey==='size')}
      ${defs.map(([k, label]) => reslibSortHeader(k, label, reslibSortKey===k)).join('')}
      ${reslibSortHeader('price','Price', reslibSortKey==='price')}
    </tr>`;

    document.getElementById('reslib-tbody').innerHTML = rows.map(e => {
      const tint = SIZE_TINT[(e.size || '').toUpperCase()] || { c: 'var(--text-dim)', bg: 'transparent' };
      const mk = e.mk ? ` Mk${e.mk}` : '';
      const missileTag = isMissile(e) ? ' <span class="badge neutral">Missile</span>' : '';
      const tipAttr = wantsTip ? ` data-weapon-tip="${encodeURIComponent(JSON.stringify({ ...e, _shipHeatFactor: 1 }))}"` : '';
      const cells = defs.map(([k, , fmt]) => {
        const v = e[k];
        return `<td class="mono">${v != null ? fmt(v) : '—'}</td>`;
      }).join('');
      return `<tr${tipAttr}>
        <td style="color:var(--text)">${e.name}${mk}${missileTag}</td>
        <td>${designBadge(e.race)}</td>
        <td style="color:${tint.c}">${e.size ? e.size.toUpperCase() : '—'}</td>
        ${cells}
        <td class="mono">${e.price != null ? designCr(e.price) : '—'}</td>
      </tr>`;
    }).join('');
  }

  // ── HULL STAT CARD ───────────────────────────────────────────────────────
  // The .dhull card for one hull, by macro. Shared by Hull Inspector below
  // and the Hull Comparison tab (hull-comparison.js) so both pages render
  // byte-identical cards from one source instead of drifting copies.
  // Optional slot parameter ('a' or 'b') used by Hull Comparison to label A/B.
  function hullStatCardHtml(macro, slot) {
    const h = HULL_CATALOG[macro];
    if (!h) return '';
    const faction = hullFactionFor(macro, h);
    const size = sizeFromClass(h.class);
    const type = hullTypeFor(macro, h);
    const facColour = FACTION_COLOURS[faction.toLowerCase()] || '#2dd4bf';
    const capitalize = s => s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
    // cargo_tags can be several space-separated ware types on multi-purpose
    // bays (e.g. "container solid liquid") -- show every one, not just the first.
    const cargoTagsLabel = (h.cargo_tags || '').split(' ').filter(Boolean).map(capitalize).join(' / ');
    // Hull Comparison uses slot='a' or slot='b' to show Hull A/Hull B labels instead of plain Hull
    const hullLabel = slot ? `Hull ${slot.toUpperCase()}` : 'Hull';

    return `<div class="dhull" style="--dhull-border:${hexA(facColour,0.35)};--dhull-glow:${hexA(facColour,0.1)};max-width:30rem">
      <div class="dhull-hd"><i class="ti ti-ufo" style="color:${facColour}"></i><span class="lbl">${hullLabel}</span></div>
      <div class="dhull-wire">${wireSvgFor(size)}</div>
      <div class="dhull-id">${designBadge(faction)}<span class="dhull-nm">${h.name}</span></div>
      <div class="dhull-stats">
        <div class="dhull-stat"><span class="dhs-lbl">Type</span><span class="dhs-val">${hullTypeLabel(type)}</span></div>
        <div class="dhull-stat"><span class="dhs-lbl">Size</span><span class="dhs-val">${SIZE_WORD[size] || size.toUpperCase()}</span></div>
        <div class="dhull-stat"><span class="dhs-lbl">Hull HP</span><span class="dhs-val">${h.max_hull != null ? designCr(h.max_hull) : '—'}</span></div>
        <div class="dhull-stat"><span class="dhs-lbl">Price</span><span class="dhs-val">${h.price != null ? designCr(h.price) : '—'}</span></div>
      </div>
      <div class="dhull-stats">
        <div class="dhull-stat"><span class="dhs-lbl">Crew</span><span class="dhs-val">${h.crew_capacity != null ? designCr(h.crew_capacity) : '—'}</span></div>
        <div class="dhull-stat"><span class="dhs-lbl">Cargo</span><span class="dhs-val">${h.cargo_max != null ? designCr(h.cargo_max) + ' m³' : '—'}</span></div>
        <div class="dhull-stat"><span class="dhs-lbl">Missiles</span><span class="dhs-val">${h.missile_storage != null ? designCr(h.missile_storage) : '—'}</span></div>
        <div class="dhull-stat"><span class="dhs-lbl">Units</span><span class="dhs-val">${h.unit_storage != null ? designCr(h.unit_storage) : '—'}</span></div>
      </div>
      ${cargoTagsLabel ? `<div style="width:100%;text-align:center;font-size:1rem;color:var(--text-faint);margin-top:-0.4rem">Cargo: ${cargoTagsLabel}</div>` : ''}
    </div>`;
  }

  // ── HULL INSPECTOR ───────────────────────────────────────────────────────
  // Per-hull detail page, reached by clicking a row in Hull List. Reuses the
  // same .dhull stat-card and .dsect/.dsub-box equipment-section markup as
  // the Designs tab's design cards (designCardHtml() in designs-builder.js)
  // for visual consistency, but instead of listing what's *fitted* on a
  // specific ship, it cross-references EQUIPMENT_CATALOG by slot+size to
  // show everything that's catalogued and COULD mount in each hardpoint.
  function renderResLibHullInspector() {
    const macro = reslibInspectMacro;
    const h = HULL_CATALOG[macro];
    document.getElementById('reslib-panel').style.display = 'none';
    document.getElementById('reslib-empty').style.display = 'none';
    document.getElementById('reslib-compare').style.display = 'none';
    const panel = document.getElementById('reslib-inspector');
    panel.style.display = '';

    if (!h) {
      panel.innerHTML = `<div style="padding:6rem;text-align:center;color:var(--text-dim)">Hull not found — it may have dropped out of the loaded catalog.</div>`;
      return;
    }

    const size = sizeFromClass(h.class);
    const capitalize = s => s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
    const hullCard = hullStatCardHtml(macro);

    const badges = [
      h.purchasable === false ? '<span class="badge neutral">Capture Only</span>' : '',
      h.purpose ? `<span class="badge neutral">${capitalize(h.purpose)}</span>` : '',
      (h.weapon_heat_factor && h.weapon_heat_factor !== 1) ? `<span class="badge neutral">Heat ×${h.weapon_heat_factor}</span>` : '',
    ].filter(Boolean).join(' ');

    const description = h.description
      ? `<div style="font-size:1.2rem;color:var(--text-dim);line-height:1.6;font-style:italic;margin-bottom:1.4rem;max-width:82rem">${h.description}</div>`
      : '';

    // Same padded-to-4-columns convention as designCardHtml()'s statCells/
    // headerRow, so weapon/turret/shield (3 stat defs) and thruster (4)
    // share one .drow grid template without the columns drifting per slot.
    const statCells = (e, defs) => [0,1,2,3].map(i => {
      if (!defs[i]) return '<span></span>';
      const v = e[defs[i][0]];
      return `<span class="dst">${v != null ? defs[i][2](v) : '—'}</span>`;
    }).join('');
    const headerRow = defs => `<div class="drow"><span></span><span></span><span></span>` +
      [0,1,2,3].map(i => `<span class="dhd">${defs[i] ? defs[i][1] : ''}</span>`).join('') +
      `<span class="dhd">Cost</span></div>`;

    let sections = '';
    for (const [slot, label] of DESIGN_SLOTS) {
      // Thruster isn't a component hardpoint — it's one implicit slot at the
      // hull's own size (same rule the Ship Builder's builderCapacity() uses).
      const cap = slot === 'thruster' ? { [size]: 1 } : ((h.hardpoints && h.hardpoints[slot]) || {});
      const sizesPresent = Object.keys(cap).filter(sz => cap[sz] > 0).sort(bySizeDesc);
      if (!sizesPresent.length) continue;

      const m = SLOT_META[slot];
      const defs = RESLIB_EQUIP_COLUMNS[slot] || [];
      const wantsTip = slot === 'weapon' || slot === 'turret' || slot === 'shield' || slot === 'engine';
      const capText = sizesPresent.map(sz => `${cap[sz]} ${sz.toUpperCase()}`).join(' · ');

      // One collapsed "N Size Slot Hardpoints" sub-card per mount size —
      // collapsed by default since a hull can have a dozen+ catalogued items
      // per size and listing them all inline made the page unreadable.
      // Expanding (<details>) is the "option to show the compatible
      // equipment" the per-size box now exists to offer.
      const body = sizesPresent.map(sz => {
        const box = SIZE_BOX[sz] || SIZE_BOX.s;
        const compat = Object.entries(EQUIPMENT_CATALOG)
          .filter(([, e]) => e.slot === slot && (e.size || '').toLowerCase() === sz)
          .map(([eMacro, e]) => ({ macro: eMacro, ...e }))
          .sort((a, b) => (a.name || '').localeCompare(b.name || ''));
        const title = `${cap[sz]} ${SIZE_WORD[sz] || sz.toUpperCase()} ${SLOT_SINGULAR[slot] || label} Hardpoint${cap[sz] > 1 ? 's' : ''}`;
        const inner = compat.length
          ? headerRow(defs) + compat.map(e => {
              const mk = e.mk ? ` Mk${e.mk}` : '';
              const tipAttr = wantsTip ? ` data-weapon-tip="${encodeURIComponent(JSON.stringify({ ...e, _shipHeatFactor: h.weapon_heat_factor || 1 }))}"` : '';
              return `<div class="drow"${tipAttr}>
                <span></span>${designBadge(e.race)}
                <span class="dnm">${e.name}${mk}</span>
                ${statCells(e, defs)}
                <span class="dcost">${e.price != null ? designCr(e.price) : '—'}</span>
              </div>`;
            }).join('')
          : `<div style="padding:0.6rem 0.2rem;color:var(--text-faint);font-size:1.1rem">No catalogued ${label.toLowerCase()} fit this size yet.</div>`;
        return `<details class="dsub-box reslib-hpcard" style="border-color:${hexA(box.hex,0.3)};background:${box.bg}">
          <summary class="dsub-hd">
            <span class="dsub-badge" style="color:${box.hex};background:${box.bg};border-color:${box.hex}">${sz.toUpperCase()}</span>
            <span class="reslib-hp-title">${title}</span>
            <i class="ti ti-chevron-down reslib-hp-chev"></i>
          </summary>
          <div class="reslib-hp-body">${inner}</div>
        </details>`;
      }).join('');

      sections += `<div class="dsect">
        <div class="dsect-hd" style="background:${m.tint}">
          <i class="ti ${m.icon}" style="color:${m.color}"></i><span class="lbl">${label}</span>
          <span class="slots">${capText}</span>
        </div>
        <div class="dsect-body">${body}</div>
      </div>`;
    }
    if (!sections) sections = `<div style="padding:3rem 1rem;text-align:center;color:var(--text-dim);font-size:1.2rem">This hull has no equipment hardpoints.</div>`;

    panel.innerHTML = `
      ${badges ? `<div style="margin-bottom:1rem">${badges}</div>` : ''}
      ${description}
      <div style="display:flex;gap:1.6rem;flex-wrap:wrap;align-items:flex-start">
        ${hullCard}
        <div style="flex:1;min-width:28rem">${sections}</div>
      </div>`;
  }
