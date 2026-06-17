  // ── DESIGNS TAB ───────────────────────────────────────────────────────────
  // A "design" is a unique ship configuration: same hull macro + the same
  // installed equipment (same macros, same counts). Many ships collapse onto
  // one design. Built entirely from the loadout the export already carries —
  // no backend. Deployables have no loadout, so they never appear here.

  // Static catalogs set by populate(): equipment (macro → name/stats/price) and
  // hulls (macro → name/class/hardpoints/price). The blueprint builder reads both.
  let EQUIPMENT_CATALOG = {};
  let HULL_CATALOG = {};

  const DESIGN_SLOTS = [
    ['weapon','Weapons'], ['turret','Turrets'], ['shield','Shields'],
    ['engine','Engine'],  ['thruster','Thruster'],
  ];

  const designCr = n => Number(n).toLocaleString();

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

  // Per-slot stat columns: [catalog key, header label, value formatter].
  const SLOT_STATS = {
    weapon:   [['damage_hull','Damage',designCr], ['range_m','Range',v=>(v/1000).toFixed(1)+' km'], ['reload_rate','Rate',v=>v+'/s']],
    turret:   [['damage_hull','Damage',designCr], ['range_m','Range',v=>(v/1000).toFixed(1)+' km'], ['reload_rate','Rate',v=>v+'/s']],
    shield:   [['capacity','Capacity',designCr],  ['recharge_rate','Rechg',v=>designCr(v)+'/s'],   ['recharge_delay','Delay',v=>v+' s']],
    engine:   [['thrust_forward','Forward',designCr], ['travel_thrust','Travel',v=>Math.round(v)]],
    thruster: [['strafe','Strafe',designCr], ['pitch','Pitch',designCr], ['yaw','Yaw',designCr], ['roll','Roll',designCr]],
  };

  // 3-letter faction tag in the hull-badge style (.badge .{faction} colour).
  // Generic / no-maker parts (thrusters) get a neutral GEN badge.
  const FAC3 = {
    argon:'ARG', paranid:'PAR', teladi:'TEL', split:'SPL', terran:'TER',
    boron:'BOR', xenon:'XEN', khaak:'KHA', pirate:'PIR', yaki:'YAK',
  };
  function designBadge(faction) {
    if (!faction) return '<span class="badge neutral">GEN</span>';
    const f = faction.toLowerCase();
    return `<span class="badge ${f}">${FAC3[f] || f.slice(0,3).toUpperCase()}</span>`;
  }

  // Resolvable equipment only — drops the unresolved internal parts (raw macros).
  const designItems = s => (s.loadout || []).filter(e => !e.name.endsWith('_macro'));

  // Stable grouping key: hull + each item as slot:macro:count, sorted so the
  // order equipment was read never affects whether two ships match.
  function designSignature(s) {
    return s.macro + '||' +
      designItems(s).map(e => `${e.slot}:${e.macro}:${e.count}`).sort().join('|');
  }

  function renderDesigns() {
    const grid  = document.getElementById('designs-grid');
    const empty = document.getElementById('designs-empty');
    const ships = (allPlayerShips || []).filter(s => designItems(s).length);
    if (!ships.length) { grid.innerHTML = ''; empty.style.display = 'flex'; return; }
    empty.style.display = 'none';

    // Group ships by signature.
    const groups = new Map();
    for (const s of ships) {
      const sig = designSignature(s);
      if (!groups.has(sig))
        groups.set(sig, {
          type: s.type_name || s.macro, loadout: s.loadout, ships: [],
          hullFaction: s.hull_origin, hullMax: s.hull_max, hullPrice: s.hull_price,
          hullSize: s.size, hardpoints: s.hardpoints,
        });
      groups.get(sig).ships.push(s);
    }
    const designs = [...groups.values()];

    // Config letters per hull type, lettered by descending member count. A type
    // with only one config gets no letter (no "Config A" when there's no B).
    const byType = {};
    designs.forEach(d => (byType[d.type] = byType[d.type] || []).push(d));
    Object.values(byType).forEach(list => {
      list.sort((a, b) => b.ships.length - a.ships.length);
      list.forEach((d, i) =>
        d.config = list.length > 1 ? ' · Config ' + String.fromCharCode(65 + i) : '');
    });

    // Most-common designs first.
    designs.sort((a, b) => b.ships.length - a.ships.length || a.type.localeCompare(b.type));
    grid.innerHTML = designs.map((d, i) => designCardHtml(d, i)).join('');
  }

  // Generic placeholder hull wireframe. Replaced per-hull by the .xmf mesh
  // render in a later phase; kept neutral so it reads as a preview, not data.
  const WIRE_SVG = `<svg viewBox="0 0 140 64" style="width:140px;height:64px;filter:drop-shadow(0 0 3px rgba(45,212,191,0.5))" aria-hidden="true">
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

    let total = d.hullPrice || 0;

    // ── Hull section: wireframe preview + the priced hull row ────────────────
    const hullDefs = [['hull_max', 'Hull HP', designCr]];
    const hullInner = `<div style="display:flex;gap:12px;align-items:center">
      <div style="border:1px solid rgba(45,212,191,0.27);border-radius:3px;background:#0a0e13;padding:3px;flex-shrink:0">${WIRE_SVG}</div>
      <div style="flex:1">
        ${headerRow(hullDefs)}
        <div class="drow">
          <span class="dcnt">1×</span>${designBadge(d.hullFaction)}
          <span style="font-family:var(--font-cond);font-weight:600;font-size:14px">${d.type}</span>
          ${statCells({ hull_max: d.hullMax }, hullDefs)}
          <span class="dcost">${d.hullPrice != null ? designCr(d.hullPrice) : '—'}</span>
        </div>
      </div>
    </div>`;
    let body = section('hull', 'Hull',
      `${d.hullSize || ''}${d.hullFaction ? ' · ' + d.hullFaction : ''}`, hullInner);

    // ── Equipment sections ──────────────────────────────────────────────────
    for (const [slot, label] of DESIGN_SLOTS) {
      const items = (d.loadout || []).filter(e => e.slot === slot && !e.name.endsWith('_macro'));
      if (!items.length) continue;
      const defs = SLOT_STATS[slot] || [];
      // Section header right side: "fitted / capacity · sizes" when the hull's
      // hardpoints are known, else just the mount sizes seen on the fitted gear.
      const hp = (d.hardpoints && d.hardpoints[slot]) || null;
      const fitted = items.reduce((a, e) => a + e.count, 0);
      const cap = hp ? Object.values(hp).reduce((a, b) => a + b, 0) : null;
      const sizes = (hp ? Object.keys(hp) : items.map(e => e.size).filter(Boolean))
        .filter((s, i, a) => a.indexOf(s) === i).map(s => s.toUpperCase()).join('/');
      const slotsText = cap != null ? `${fitted} / ${cap} · ${sizes}` : sizes;
      const rows = items.map(e => {
        if (e.price) total += e.price * e.count;
        const mk = e.mk ? ` Mk${e.mk}` : '';
        return `<div class="drow">
          <span class="dcnt">${e.count}×</span>${designBadge(e.race)}
          <span class="dnm">${e.name}${mk}</span>
          ${statCells(e, defs)}
          <span class="dcost">${e.price != null ? designCr(e.price) : '—'}</span>
        </div>`;
      }).join('');
      body += section(slot, label, slotsText, headerRow(defs) + rows);
    }

    const n = d.ships.length;
    const chips = d.ships.map(s =>
      `<span onclick="jumpToShip('${s.code}')" style="cursor:pointer;font-family:var(--font-mono);font-size:11px;color:var(--teal);border:1px solid var(--border);border-radius:2px;padding:2px 8px">${s.code}${s.name ? ' · ' + s.name : ''}</span>`
    ).join('');

    return `<div class="panel" style="margin-bottom:12px;padding:14px">
      <div style="display:flex;align-items:center;gap:10px;border-bottom:1px solid var(--border);padding-bottom:8px;margin-bottom:8px">
        <i class="ti ti-vector-triangle" style="color:var(--teal);font-size:16px"></i>
        <span style="font-family:var(--font-cond);font-weight:600;font-size:16px;color:var(--text)">${d.type}${d.config}</span>
        <span onclick="toggleDesignShips(${idx})" style="margin-left:auto;cursor:pointer;color:var(--text-dim);font-size:12px;white-space:nowrap">used by <b style="color:var(--lime)">${n}</b> ship${n > 1 ? 's' : ''} <i class="ti ti-chevron-down" style="vertical-align:-2px"></i></span>
      </div>
      ${body}
      <div style="display:flex;align-items:baseline;gap:10px;border-top:1px solid var(--border);margin-top:2px;padding-top:9px">
        <span style="font-family:var(--font-cond);font-weight:600;font-size:13px;letter-spacing:0.06em;text-transform:uppercase;color:var(--text-dim)">Design total</span>
        <span style="margin-left:auto;font-family:var(--font-mono);font-size:16px;color:var(--amber)">${designCr(total)} <span style="font-size:11px;color:var(--text-dim)">Cr</span></span>
      </div>
      <div id="design-ships-${idx}" style="display:none;gap:6px;flex-wrap:wrap;margin-top:8px;padding-top:8px;border-top:1px solid var(--border)">${chips}</div>
    </div>`;
  }

  function toggleDesignShips(idx) {
    const el = document.getElementById('design-ships-' + idx);
    if (el) el.style.display = el.style.display === 'flex' ? 'none' : 'flex';
  }

  // ══ SHIP BUILDER (interactive blueprint builder) ═══════════════════════════
  // Reuses the design-card layout (.dsect sections, SLOT_META, SLOT_STATS,
  // designBadge, WIRE_SVG) but makes it editable. State: chosen hull + per-slot
  // fitted equipment. fits[slot] = [{macro, count}].
  let builderState = { hull: null, name: '', fits: {}, selectedSlot: null };

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
    // Pre-select the first category this hull actually has slots for.
    builderState.selectedSlot = DESIGN_SLOTS.map(([s]) => s)
      .find(s => Object.values(builderCapacity(s)).reduce((a, b) => a + b, 0) > 0) || null;
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

  function builderSelect(slot) {
    builderState.selectedSlot = slot;
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

    // ── LEFT pane: a card per category (count box + name + stepper + Fit) ────
    let left = '';
    for (const [slot, label] of DESIGN_SLOTS) {
      const cap = builderCapacity(slot);
      const capTotal = Object.values(cap).reduce((a, b) => a + b, 0);
      if (!capTotal) continue;   // hull has no slots of this type
      const m = SLOT_META[slot];
      const fits = builderState.fits[slot] || [];
      const fittedTotal = fits.reduce((a, f) => a + f.count, 0);
      const sizes = Object.keys(cap).map(s => s.toUpperCase()).join('/');

      const rows = fits.map(f => {
        const e = EQUIPMENT_CATALOG[f.macro] || { name: f.macro };
        if (e.price) total += e.price * f.count;
        const mk = e.mk ? ` Mk${e.mk}` : '';
        return `<div class="bfr">
          <span class="bstep"><span class="bsb" onclick="builderCount('${slot}','${f.macro}',-1)">−</span><span class="bcbox">${f.count}</span><span class="bsb" onclick="builderCount('${slot}','${f.macro}',1)">+</span></span>
          <span style="font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${e.name}${mk}</span>
        </div>`;
      }).join('');

      const free = capTotal - fittedTotal;
      const fitBtn = free > 0
        ? `<div class="bfit" onclick="builderSelect('${slot}')"><i class="ti ti-plus" style="font-size:11px;vertical-align:-1px"></i> Fit ${label.toLowerCase()} · ${free} free</div>` : '';

      left += `<div class="bcat ${sel === slot ? 'sel' : ''}">
        <div class="bcat-h" style="background:${m.tint}" onclick="builderSelect('${slot}')"><i class="ti ${m.icon}" style="color:${m.color}"></i><span class="lbl">${label}</span><span class="cap">${fittedTotal} / ${capTotal} · ${sizes}</span></div>
        ${rows}${fitBtn}
      </div>`;
    }

    // ── RIGHT pane: available equipment for the selected category, with stats ─
    let right;
    if (sel) {
      const cap = builderCapacity(sel);
      const sizesSet = new Set(Object.keys(cap));
      const defs = SLOT_STATS[sel] || [];
      const m = SLOT_META[sel];
      const fitted = new Set((builderState.fits[sel] || []).map(f => f.macro));
      const full = [...sizesSet].every(s => (builderFittedBySize(sel)[s] || 0) >= cap[s]);
      const label = (DESIGN_SLOTS.find(([s]) => s === sel) || [, sel])[1];

      const statCells = e => [0,1,2,3].map(i => {
        if (!defs[i]) return '<span></span>';
        const v = e[defs[i][0]];
        return `<span class="dst">${v != null ? defs[i][2](v) : '—'}</span>`;
      }).join('');
      const headerCells = [0,1,2,3].map(i => `<span class="boh">${defs[i] ? defs[i][1] : ''}</span>`).join('');

      const opts = Object.entries(EQUIPMENT_CATALOG)
        .filter(([, e]) => e.slot === sel && sizesSet.has(e.size))
        .sort((a, b) => (a[1].price || 0) - (b[1].price || 0))
        .map(([mac, e]) => {
          const on = fitted.has(mac);
          return `<div class="borow ${on ? 'on' : ''}" onclick="builderFitAdd('${sel}','${mac}')">
            ${designBadge(e.race)}<span style="font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;${on ? 'color:var(--lime)' : ''}">${e.name}${e.mk ? ` Mk${e.mk}` : ''}</span>
            ${statCells(e)}<span class="dcost">${e.price != null ? designCr(e.price) : '—'}</span>
            <i class="ti ${on ? 'ti-check' : 'ti-plus'}" style="color:var(--lime);font-size:13px"></i></div>`;
        }).join('');

      right = `<div class="bopts">
        <div class="bopts-h"><i class="ti ${m.icon}" style="color:${m.color};font-size:15px"></i><span class="lbl">Available · ${label}</span><span class="mt">${[...sizesSet].map(s => s.toUpperCase()).join('/')} mount${full ? ' · full' : ''}</span></div>
        <div style="padding:5px 8px">
          <div class="borow"><span></span><span></span>${headerCells}<span class="boh">Cost</span><span></span></div>
          ${opts || '<div style="color:var(--text-dim);font-size:11px;padding:8px">No compatible equipment.</div>'}
        </div></div>`;
    } else {
      right = `<div class="bopts" style="padding:30px;text-align:center;color:var(--text-dim)">Select a category to fit equipment.</div>`;
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

