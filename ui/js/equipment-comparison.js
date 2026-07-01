  // Core role: Equipment comparison view (two-item picker with side-by-side
  // stat cards), the Weapon/Turret/Shield/Engine/Thruster analogue of the Hull
  // Comparison tab in hull-comparison.js. Deliberately mirrors that file's
  // shape and reuses its .dhull / .hcmp-* CSS so the two pages read identically.

  // Persisted like reslibCompareMacroA/B so flipping List <-> Comparison and
  // back doesn't lose the picks. Reset in switchResLibCat() when the category
  // changes, since a weapon macro is meaningless once you're on Shields.
  let reslibEquipCmpA = null;
  let reslibEquipCmpB = null;

  // Open/closed state for the two pickers (A and B). A native <select> can't
  // render a right-justified, size-tinted badge inside an <option>, so each
  // picker is a custom .beqf-dd dropdown (the same shell the faction filters
  // use) and we track its open state ourselves.
  let reslibEquipDDOpen = { a: false, b: false };

  function reslibShowEquipList() {
    reslibEquipView = 'list';
    renderResLibHeader();
    renderResLib();
  }
  function reslibShowEquipCompare() {
    reslibEquipView = 'compare';
    renderResLibHeader();
    renderResLib();
  }

  function reslibSetCompareEquip(which, macro) {
    if (which === 'a') reslibEquipCmpA = macro || null;
    else reslibEquipCmpB = macro || null;
    reslibEquipDDOpen[which] = false;   // collapse the menu once a pick is made
    renderResLibEquipCompare();
  }

  // Open/close plumbing for the custom pickers. Opening one collapses the
  // other so two menus never overlap; any click outside both dismisses them.
  function reslibToggleEquipDD(which, e) {
    if (e) e.stopPropagation();
    const other = which === 'a' ? 'b' : 'a';
    reslibEquipDDOpen[other] = false;
    document.getElementById(`reslib-eqcmp-menu-${other}`)?.classList.remove('open');
    reslibEquipDDOpen[which] = !reslibEquipDDOpen[which];
    document.getElementById(`reslib-eqcmp-menu-${which}`)?.classList.toggle('open', reslibEquipDDOpen[which]);
  }
  function reslibCloseEquipDD() {
    reslibEquipDDOpen.a = reslibEquipDDOpen.b = false;
    document.getElementById('reslib-eqcmp-menu-a')?.classList.remove('open');
    document.getElementById('reslib-eqcmp-menu-b')?.classList.remove('open');
  }
  document.addEventListener('click', (e) => {
    if (!e.target.closest('.reslib-eqcmp-dd')) reslibCloseEquipDD();
  });

  // Compact, size-tinted pill (S/M/L/XL) — the same stylized label the Hull
  // Comparison rows use (.hcmp-size-badge), coloured through SIZE_TINT so a
  // glance at the dropdown tells you the mount size. Empty for the handful of
  // parts with no size (e.g. some thrusters), so they just show a bare name.
  function equipSizeBadge(e) {
    const sz = (e.size || '').toUpperCase();
    if (!sz) return '';
    const tint = SIZE_TINT[sz] || SIZE_TINT.S;
    return `<span class="hcmp-size-badge ecmp-opt-size" style="color:${tint.c};border-color:${tint.c}">${sz}</span>`;
  }

  // Full faction name for grouping/labels — same RACE_FULL_NAMES table the
  // equipment List badge resolves through (raceKeyOf buckets maker-less gear,
  // e.g. most thrusters, under 'generic').
  const equipFactionName = e => {
    const k = raceKeyOf(e);
    return RACE_FULL_NAMES[k] || (k.charAt(0).toUpperCase() + k.slice(1));
  };

  // Custom picker grouped by faction, alphabetical within each group —
  // restricted to the category currently open (reslibCat) so you only ever
  // compare like with like. Mirrors the Hull Comparison picker's choices but
  // swaps the native <select> for a .beqf-dd dropdown so each row can carry a
  // right-justified size badge (which a native <option> can't render).
  function reslibEquipCompareSelect(which, currentMacro) {
    const byFaction = new Map();
    for (const [macro, e] of Object.entries(EQUIPMENT_CATALOG)) {
      if (e.slot !== reslibCat) continue;
      const fac = equipFactionName(e);
      if (!byFaction.has(fac)) byFaction.set(fac, []);
      byFaction.get(fac).push({ macro, e, name: (e.name || macro) + (e.mk ? ` Mk${e.mk}` : '') });
    }
    // Faction sections replace native <optgroup>s: a faded header row followed
    // by its items (name on the left, size badge pushed to the right).
    const sections = [...byFaction.keys()].sort().map(fac => {
      const items = byFaction.get(fac)
        .sort((a, b) => a.name.localeCompare(b.name))
        .map(o => `<div class="beqf-item ecmp-opt ${o.macro === currentMacro ? 'sel' : ''}" onclick="reslibSetCompareEquip('${which}', '${o.macro}')">
          <span class="ecmp-opt-name">${o.name}</span>${equipSizeBadge(o.e)}
        </div>`).join('');
      return `<div class="ecmp-dd-sec">${fac}</div>${items}`;
    }).join('');

    const singular = (SLOT_SINGULAR[reslibCat] || 'item').toLowerCase();
    const cur = currentMacro ? EQUIPMENT_CATALOG[currentMacro] : null;
    const triggerInner = cur
      ? `<span class="ecmp-opt-name">${cur.name || currentMacro}${cur.mk ? ` Mk${cur.mk}` : ''}</span>${equipSizeBadge(cur)}`
      : `<span class="ecmp-opt-name ecmp-dd-ph">Select a ${singular}…</span>`;

    return `<div class="beqf-dd reslib-eqcmp-dd" id="reslib-eqcmp-dd-${which}">
      <div class="beqf-trigger ecmp-trigger" onclick="reslibToggleEquipDD('${which}', event)">${triggerInner}<i class="ti ti-chevron-down"></i></div>
      <div class="beqf-menu ${reslibEquipDDOpen[which] ? 'open' : ''}" id="reslib-eqcmp-menu-${which}">
        <div class="beqf-item ecmp-opt ${cur ? '' : 'sel'}" onclick="reslibSetCompareEquip('${which}', '')">
          <span class="ecmp-opt-name ecmp-dd-ph">Select a ${singular}…</span>
        </div>
        ${sections}
      </div>
    </div>`;
  }

  // ── EQUIPMENT STAT CARD ──────────────────────────────────────────────────
  // The .dhull card (reused as-is, just without the hull wireframe) for one
  // catalogued item, by macro. 'letter' ('a'/'b') drives the "Weapon A" header
  // the way slot does on hullStatCardHtml().
  function equipStatCardHtml(macro, slot, letter) {
    const e = EQUIPMENT_CATALOG[macro];
    if (!e) return '';
    const facColour = FACTION_COLOURS[raceKeyOf(e)] || 'var(--color-primary)';
    const m = SLOT_META[slot] || {};
    const size = (e.size || '').toLowerCase();
    const mk = e.mk ? ` Mk${e.mk}` : '';
    const label = `${SLOT_SINGULAR[slot] || 'Item'} ${letter.toUpperCase()}`;

    // [label, value] cells: Size, then this category's List columns, then
    // Price — every number the List table shows for the item, on one card.
    const cells = [['Size', SIZE_WORD[size] || size.toUpperCase()]];
    for (const [k, colLabel, fmt] of (RESLIB_EQUIP_COLUMNS[slot] || []))
      cells.push([colLabel, e[k] != null ? fmt(e[k]) : '—']);
    cells.push(['Price', e.price != null ? designCr(e.price) : '—']);

    // Chunk into rows of 4 (same two-row shape as the hull card) so a 5-stat
    // thruster doesn't squeeze every cell onto one overflowing line.
    let rows = '';
    for (let i = 0; i < cells.length; i += 4) {
      rows += `<div class="dhull-stats">` + cells.slice(i, i + 4).map(([l, v]) =>
        `<div class="dhull-stat"><span class="dhs-lbl">${l}</span><span class="dhs-val">${v}</span></div>`
      ).join('') + `</div>`;
    }

    return `<div class="dhull" style="--dhull-border:${hexA(facColour, 0.35)};--dhull-glow:${hexA(facColour, 0.1)};max-width:30rem">
      <div class="dhull-hd"><i class="ti ${m.icon}" style="color:${m.color}"></i><span class="lbl">${label}</span></div>
      <div class="dhull-id">${designBadge(equipFactionName(e))}<span class="dhull-nm">${e.name || macro}${mk}</span></div>
      ${rows}
    </div>`;
  }

  // Compare rows = the category's List columns plus Price. Each entry is
  // [label, key, formatter] — formatters come straight from RESLIB_EQUIP_COLUMNS
  // so a value reads the same (km, /s, …) here as it does in the table.
  function ecmpStatsFor(slot) {
    const cols = (RESLIB_EQUIP_COLUMNS[slot] || []).map(([k, label, fmt]) => [label, k, fmt]);
    cols.push(['Price', 'price', v => designCr(v)]);
    return cols;
  }

  // Stats where a *smaller* number wins (e.g. a shield's recharge delay, or
  // price — cheaper is the win). Every other stat follows the
  // hull-comparison default of "bigger is greener".
  const ECMP_LOWER_BETTER = new Set(['recharge_delay', 'price']);

  // One row, identical layout to hcmpStatRow(): item A's bar on top, B's below.
  // Bars scale against the larger of the two values (head-to-head magnitude);
  // the winning side is lime, the loser red, a tie/missing value stays teal —
  // except for ECMP_LOWER_BETTER keys, where the smaller value is the winner.
  function ecmpStatRow(label, key, fmt, eA, eB) {
    const vA = eA[key];
    const vB = eB[key];
    if (vA == null && vB == null) {
      return `<div class="hcmp-row">
        <div class="hcmp-lbl">${label}</div>
        <div style="font-size:11px;color:var(--text-brand)">No data for either item.</div>
      </div>`;
    }
    const haveBoth = vA != null && vB != null;
    const a = vA ?? 0, b = vB ?? 0;
    const max = Math.max(a, b, 1);
    const lower = ECMP_LOWER_BETTER.has(key);
    let colorA = 'var(--color-primary)', colorB = 'var(--color-primary)';
    if (haveBoth && a !== b) {
      const aWins = lower ? a < b : a > b;
      colorA = aWins ? 'var(--color-alert)' : 'var(--color-negative)';
      colorB = aWins ? 'var(--color-negative)' : 'var(--color-alert)';
    }
    const fmtV = v => v == null ? '—' : fmt(v);
    const bar = (val, pct, color, letter) => `<div class="hcmp-bar-line">
      ${hcmpLabel(letter)}
      <div class="hcmp-bar-track"><div class="hcmp-bar-fill" style="width:${pct}%;background:${color}"></div></div>
      <span class="hcmp-val" style="color:${color}">${fmtV(val)}</span>
    </div>`;
    return `<div class="hcmp-row">
      <div class="hcmp-lbl">${label}</div>
      ${bar(vA, (a / max) * 100, colorA, 'A')}
      ${bar(vB, (b / max) * 100, colorB, 'B')}
    </div>`;
  }

  function renderResLibEquipCompare() {
    const slot = reslibCat;
    const hasAny = Object.values(EQUIPMENT_CATALOG).some(e => e.slot === slot);
    if (!hasAny) {
      reslibShowEmpty('ti-radar-2', 'No equipment catalog loaded', 'Run a scan first — the equipment catalog ships inside the scan export.');
      return;
    }
    document.getElementById('reslib-panel').style.display = 'none';
    document.getElementById('reslib-inspector').style.display = 'none';
    document.getElementById('reslib-empty').style.display = 'none';
    const panel = document.getElementById('reslib-compare');
    panel.style.display = '';

    // Guard against a pick left over from a different category (shouldn't
    // happen — switchResLibCat clears them — but cheap insurance).
    const valid = macro => { const e = EQUIPMENT_CATALOG[macro]; return e && e.slot === slot ? e : null; };
    const eA = reslibEquipCmpA ? valid(reslibEquipCmpA) : null;
    const eB = reslibEquipCmpB ? valid(reslibEquipCmpB) : null;

    const singular = SLOT_SINGULAR[slot] || 'Item';
    const m = SLOT_META[slot] || {};
    const placeholder = (letter) => `<div class="dhull hcmp-empty-card" style="max-width:300px">
      <div class="dhull-hd"><i class="ti ${m.icon}" style="color:${m.color}"></i><span class="lbl">${singular} ${letter}</span></div>
      <div class="hcmp-empty-msg">Select ${singular.toLowerCase()} above</div>
    </div>`;

    const colA = `<div class="hcmp-col">${reslibEquipCompareSelect('a', eA ? reslibEquipCmpA : null)}${eA ? equipStatCardHtml(reslibEquipCmpA, slot, 'a') : placeholder('A')}</div>`;
    const colB = `<div class="hcmp-col">${reslibEquipCompareSelect('b', eB ? reslibEquipCmpB : null)}${eB ? equipStatCardHtml(reslibEquipCmpB, slot, 'b') : placeholder('B')}</div>`;

    const summary = (eA && eB)
      ? `<div class="hcmp-summary">${ecmpStatsFor(slot).map(([label, key, fmt]) => ecmpStatRow(label, key, fmt, eA, eB)).join('')}</div>`
      : `<div class="hcmp-summary hcmp-summary-empty">
          <i class="ti ti-arrows-left-right"></i>
          <div>Select two ${singular.toLowerCase()}s to compare.</div>
        </div>`;

    panel.innerHTML = `<div class="hcmp-wrap">${colA}${colB}${summary}</div>`;
  }
