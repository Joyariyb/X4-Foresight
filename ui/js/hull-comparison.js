  // Core role: Hull comparison view (two-hull picker with side-by-side stat cards).

  // Persisted like reslibInspectMacro — so flipping to Hull List/Inspector
  // and back to Comparison doesn't lose the picks.
  let reslibCompareMacroA = null;
  let reslibCompareMacroB = null;

  function reslibShowHullCompare() {
    reslibHullView = 'compare';
    renderResLibHeader();
    renderResLib();
  }

  function reslibSetCompareHull(slot, macro) {
    if (slot === 'a') reslibCompareMacroA = macro || null;
    else reslibCompareMacroB = macro || null;
    renderResLibHullCompare();
  }

  // <select> grouped by faction (same grouping hullFactionFor() already
  // gives the List tab's Faction filter), alphabetical within each group —
  // a plain native select is enough here since this is a single pick, not
  // the multi-axis filter the heavier .beqf-dd faction dropdown exists for.
  function reslibHullCompareSelect(slot, currentMacro) {
    const byFaction = new Map();
    for (const [macro, h] of Object.entries(HULL_CATALOG)) {
      const fac = hullFactionFor(macro, h);
      if (!byFaction.has(fac)) byFaction.set(fac, []);
      byFaction.get(fac).push({ macro, name: h.name || macro });
    }
    const groups = [...byFaction.keys()].sort().map(fac => {
      const opts = byFaction.get(fac)
        .sort((a, b) => a.name.localeCompare(b.name))
        .map(o => `<option value="${o.macro}" ${o.macro === currentMacro ? 'selected' : ''}>${o.name}</option>`)
        .join('');
      return `<optgroup label="${fac}">${opts}</optgroup>`;
    }).join('');
    return `<div class="reslib-fbox">
      <select onchange="reslibSetCompareHull('${slot}', this.value)">
        <option value="" ${currentMacro ? '' : 'selected'}>Select a hull…</option>
        ${groups}
      </select>
    </div>`;
  }

  // Sum of a hardpoint type across every mount size (S/M/L/XL) — same shape
  // EQUIPMENT/hull list rows already total in renderResLibHulls().
  const hcmpHpTotal = (h, slot) => Object.values((h.hardpoints && h.hardpoints[slot]) || {}).reduce((a, b) => a + b, 0);

  // Slot rows borrow the same icon/colour as the Hull List table's hardpoint
  // summary (SLOT_META, designs-builder.js) so a "Weapon Slots" row here
  // reads as the same thing as the weapon icon on that table.
  const hcmpSlotLabel = (slot, text) => {
    const m = SLOT_META[slot];
    return `<i class="ti ${m.icon}" style="color:${m.color}"></i> ${text}`;
  };

  // Stylized A/B indicator for comparison rows and hull cards
  const hcmpLabel = (letter) => `<span class="hcmp-label">${letter}</span>`;

  // [label, getter, unit]. Mirrors the two stat rows on the .dhull card
  // (Hull HP/Price/Crew/Cargo/Missiles/Units) plus the three hardpoint
  // totals the Hull List table already surfaces — every number that's
  // shown anywhere else on a hull, now compared head-to-head.
  const HCMP_STATS = [
    ['Hull HP', h => h.max_hull, ''],
    ['Price', h => h.price, ''],
    [hcmpSlotLabel('weapon', 'Weapon Slots'), h => hcmpHpTotal(h, 'weapon'), ''],
    [hcmpSlotLabel('turret', 'Turret Slots'), h => hcmpHpTotal(h, 'turret'), ''],
    [hcmpSlotLabel('shield', 'Shield Slots'), h => hcmpHpTotal(h, 'shield'), ''],
    ['Crew', h => h.crew_capacity, ''],
    ['Cargo', h => h.cargo_max, 'm³'],
    ['Missiles', h => h.missile_storage, ''],
    ['Units', h => h.unit_storage, ''],
  ];

  // One row: hull A's bar always on top, hull B's always on the bottom
  // (fixed position, not faction-tinted — confirmed with the maintainer).
  // Bars scale against the larger of the two values for THIS stat (a
  // head-to-head comparison, not a catalog-wide ranking), and the larger
  // value is lime/the smaller is red; a tie (or a stat missing on one side,
  // where "winning" wouldn't mean anything) stays neutral teal.
  function hcmpStatRow(label, getter, hA, hB, unit) {
    const vA = getter(hA);
    const vB = getter(hB);
    if (vA == null && vB == null) {
      return `<div class="hcmp-row">
        <div class="hcmp-lbl">${label}</div>
        <div style="font-size:11px;color:var(--text-faint)">No data for either hull.</div>
      </div>`;
    }
    const haveBoth = vA != null && vB != null;
    const a = vA ?? 0, b = vB ?? 0;
    const max = Math.max(a, b, 1);
    let colorA = 'var(--teal)', colorB = 'var(--teal)';
    if (haveBoth && a !== b) {
      colorA = a > b ? 'var(--lime)' : 'var(--red)';
      colorB = b > a ? 'var(--lime)' : 'var(--red)';
    }
    const fmt = v => v == null ? '—' : designCr(v) + (unit ? ' ' + unit : '');
    const bar = (val, pct, color, letter) => `<div class="hcmp-bar-line">
      ${hcmpLabel(letter)}
      <div class="hcmp-bar-track"><div class="hcmp-bar-fill" style="width:${pct}%;background:${color}"></div></div>
      <span class="hcmp-val" style="color:${color}">${fmt(val)}</span>
    </div>`;
    return `<div class="hcmp-row">
      <div class="hcmp-lbl">${label}</div>
      ${bar(vA, (a / max) * 100, colorA, 'A')}
      ${bar(vB, (b / max) * 100, colorB, 'B')}
    </div>`;
  }

  function renderResLibHullCompare() {
    if (!Object.keys(HULL_CATALOG).length) {
      reslibShowEmpty('ti-radar-2', 'No hull catalog loaded', 'Run a scan first — the hull catalog ships inside the scan export.');
      return;
    }
    document.getElementById('reslib-panel').style.display = 'none';
    document.getElementById('reslib-inspector').style.display = 'none';
    document.getElementById('reslib-empty').style.display = 'none';
    const panel = document.getElementById('reslib-compare');
    panel.style.display = '';

    const hA = reslibCompareMacroA ? HULL_CATALOG[reslibCompareMacroA] : null;
    const hB = reslibCompareMacroB ? HULL_CATALOG[reslibCompareMacroB] : null;

    // Same .dhull framing as a real card (dashed border swapped in via CSS)
    // so picking/clearing a hull doesn't reflow the other two columns.
    const placeholderA = `<div class="dhull hcmp-empty-card" style="max-width:300px">
      <div class="dhull-hd"><i class="ti ti-ufo"></i><span class="lbl">Hull A</span></div>
      <div class="hcmp-empty-msg">Select a hull above</div>
    </div>`;
    const placeholderB = `<div class="dhull hcmp-empty-card" style="max-width:300px">
      <div class="dhull-hd"><i class="ti ti-ufo"></i><span class="lbl">Hull B</span></div>
      <div class="hcmp-empty-msg">Select a hull above</div>
    </div>`;

    const colA = `<div class="hcmp-col">${reslibHullCompareSelect('a', reslibCompareMacroA)}${hA ? hullStatCardHtml(reslibCompareMacroA, 'a') : placeholderA}</div>`;
    const colB = `<div class="hcmp-col">${reslibHullCompareSelect('b', reslibCompareMacroB)}${hB ? hullStatCardHtml(reslibCompareMacroB, 'b') : placeholderB}</div>`;

    const summary = (hA && hB)
      ? `<div class="hcmp-summary">${HCMP_STATS.map(([label, get, unit]) => hcmpStatRow(label, get, hA, hB, unit)).join('')}</div>`
      : `<div class="hcmp-summary hcmp-summary-empty">
          <i class="ti ti-arrows-left-right"></i>
          <div>Select two hulls to compare.</div>
        </div>`;

    panel.innerHTML = `<div class="hcmp-wrap">${colA}${colB}${summary}</div>`;
  }
