  // ── SECTORS TAB ────────────────────────────────────────────────────────────
  // Master-detail view sharing the universe map's data: _sectorInfoMap (rows),
  // _sectorAdj (links), _nearestStation (jumps) and _npcBySector (presence) are
  // all populated by renderUniverseMap, which always runs before this view opens.
  let _selectedSector = null;

  // Cluster display name: same precedence the map uses — static API names first,
  // then a real cluster_name from the export, finally a prettified macro string.
  function _clusterName(macro, sec) {
    if (CLUSTER_NAMES[macro]) return CLUSTER_NAMES[macro];
    if (sec && sec.cluster_name && sec.cluster_name !== macro) return sec.cluster_name;
    return (macro || '').replace(/_macro$/, '').replace(/_/g, ' ')
                        .replace(/\b\w/g, c => c.toUpperCase());
  }

  // Strip the "[TEL] " bracket prefix the export puts on faction display names.
  function _ownerLabel(name) { return (name || '').replace(/^\[\w+\]\s*/, '') || 'Unclaimed'; }

  // Full, grouped number — no abbreviations (e.g. 2360711 → "2,360,711"), so the
  // reader sees the real figure rather than decoding "2.4M".
  function _fmtFull(n) { return (Number(n) || 0).toLocaleString('en-US'); }

  // Human-readable yield level. 9.00 uses verylow/low/medium/high/veryhigh; the
  // map covers the older fine-grained tags too. Falls back to a capitalised tag.
  const YIELD_LABELS = {
    verylow: 'Very Low', low: 'Low', lowplus: 'Low+', lowminus: 'Low−',
    lowest: 'Lowest', lowextra: 'Low Extra', medlow: 'Med-Low', medium: 'Medium',
    medplus: 'Med+', medhigh: 'Med-High', highlow: 'High-Low', high: 'High',
    highplus: 'High+', veryhigh: 'Very High', highest: 'Highest',
  };
  function _yieldLabel(y) {
    return YIELD_LABELS[y] || (y ? y.charAt(0).toUpperCase() + y.slice(1) : '—');
  }

  // Bucket a ship role into miner / trader / combat (the catch-all). Used for the
  // "Your Ships" breakdown. MINER_ROLES is the same set the fleet/alerts use.
  function _shipCategory(role) {
    if (MINER_ROLES.has(role)) return 'miner';
    if (role === 'Freighter' || role === 'Trader' || role === 'Transporter') return 'trader';
    return 'combat';
  }

  // Derive a few at-a-glance "character" tags for a sector. Kept short and only
  // the ones that apply, so the chip row stays a thin summary, not a wall.
  function _sectorTags(sec, macro, ownerRep) {
    const tags = [];
    // Ownership / standing. "Your Territory" means the player FACTION owns the
    // sector's sovereignty — not merely having a station in someone else's space.
    if (sec.owner_id === 'player') tags.push({ label: 'Your Territory', cls: 'tag-you' });
    else if (!sec.owner_id) tags.push({ label: 'Unclaimed', cls: 'tag-neutral' });
    else if (ownerRep && (ownerRep.tier === 'Hostile' || ownerRep.tier === 'At War'))
      tags.push({ label: 'Hostile', cls: 'tag-bad' });

    // Proximity to your empire (jumps from your nearest territory).
    //   Core 0–1 · Frontier 2–5 · Remote 6+
    const dist = _distFromEmpire[macro];
    if (dist != null) {
      if (dist <= 1)      tags.push({ label: 'Core',     cls: 'tag-core' });
      else if (dist <= 5) tags.push({ label: 'Frontier', cls: 'tag-frontier' });
      else                tags.push({ label: 'Remote',   cls: 'tag-remote' });
    }

    // Features.
    if ((sec.resources || []).some(r => /^high/.test(r.yield_level) || r.yield_level === 'veryhigh'))
      tags.push({ label: 'Mining-Rich', cls: 'tag-rich' });
    if (sec.sunlight != null && sec.sunlight >= 1.3) tags.push({ label: 'High Sunlight', cls: 'tag-sun' });
    if ((_sectorAdj[macro] || []).length >= 4) tags.push({ label: 'Hub', cls: 'tag-hub' });
    return tags;
  }

  // One sector row, shared by the grouped (alpha) and flat (metric) views.
  // metricHtml is an optional right-aligned value for the active sort.
  function _sectorRowHtml(s, metricHtml) {
    const dot    = FACTION_COLOURS[s.owner_id] || '#6e7681';
    const active = s.sector_macro === _selectedSector ? ' active' : '';
    // Count of the player's own stations in this sector (badge when > 0).
    const pCount = (_playerStaBySector[s.sector_macro] || []).length;
    const badge  = pCount ? `<span class="sr-sta-badge" title="${pCount} of your stations"><i class="ti ti-building-factory-2"></i>${pCount}</span>` : '';
    const metric = metricHtml ? `<span class="sr-metric">${metricHtml}</span>` : '';
    return `<div class="sector-row${active}" data-macro="${s.sector_macro}" onclick="showSectorDetail('${s.sector_macro}')">`
         + `<span class="sr-dot" style="background:${dot}"></span>`
         + `<span class="sr-name">${s.sector_name || s.sector_macro}</span>${badge}${metric}</div>`;
  }

  // Sort metric for a sector under the given mode. Returns the numeric value to
  // sort on (descending) plus the HTML shown on the row. Missing data sorts last.
  function _sectorSortMetric(s, mode) {
    if (mode === 'player') {
      // Player-station count drives the sort; the badge already shows it.
      return { value: (_playerStaBySector[s.sector_macro] || []).length, label: '' };
    }
    if (mode === 'sunlight') {
      const v = s.sunlight != null ? s.sunlight : 0;
      return { value: v, label: `<span class="sr-metric-sun">${Math.round(v * 100)}%</span>` };
    }
    if (mode.startsWith('res:')) {
      const ware = mode.slice(4);
      const r = (s.resources || []).find(x => x.ware === ware);
      if (!r) return { value: -1, label: '' };  // sector lacks this resource → bottom
      return {
        value: r.recharge_max || 0,
        label: `<span class="sr-metric-yield" data-yield="${r.yield_level || ''}">${_fmtFull(r.recharge_max)}</span>`,
      };
    }
    return { value: 0, label: '' };
  }

  function renderSectorsList() {
    const listEl = document.getElementById('sectors-list');
    if (!listEl) return;
    const mode = document.getElementById('sectors-sort')?.value || 'alpha';

    // Only discovered sectors are ever listed.
    const discovered = Object.values(_sectorInfoMap).filter(s => s.is_discovered);
    let html = '';

    if (mode === 'alpha') {
      // Default view: grouped by cluster, alphabetical, with cluster headers.
      const clusters = {}; // macro → { name, owners:{id→count}, sectors:[] }
      for (const s of discovered) {
        const cm = s.cluster_macro || 'unknown';
        const c  = clusters[cm] || (clusters[cm] = { macro: cm, name: _clusterName(cm, s), owners: {}, sectors: [] });
        c.sectors.push(s);
        if (s.owner_id) c.owners[s.owner_id] = (c.owners[s.owner_id] || 0) + 1;
      }
      // Dominant-faction colour for the cluster header swatch (mirrors the map).
      const clusterColour = (c) => {
        const sorted = Object.entries(c.owners).sort((a, b) => b[1] - a[1]);
        for (const [id] of sorted) if (FACTION_COLOURS[id]) return FACTION_COLOURS[id];
        return '#3d444d';
      };
      const ordered = Object.values(clusters).sort((a, b) => a.name.localeCompare(b.name));
      for (const c of ordered) {
        html += `<div class="sectors-cluster-head"><span class="scl-dot" style="background:${clusterColour(c)}"></span>${c.name}</div>`;
        c.sectors.sort((a, b) => (a.sector_name || '').localeCompare(b.sector_name || ''));
        for (const s of c.sectors) html += _sectorRowHtml(s, '');
      }
    } else {
      // Metric sort: a flat list, highest value first, name as tie-breaker.
      const rows = discovered
        .map(s => ({ s, m: _sectorSortMetric(s, mode) }))
        .sort((a, b) => b.m.value - a.m.value
                     || (a.s.sector_name || '').localeCompare(b.s.sector_name || ''));
      for (const { s, m } of rows) html += _sectorRowHtml(s, m.label);
    }

    listEl.innerHTML = html || '<div class="sectors-empty">No sector data.</div>';
  }

  function showSectorDetail(macro) {
    _selectedSector = macro;

    // Reflect selection in the list.
    document.querySelectorAll('#sectors-list .sector-row').forEach(r =>
      r.classList.toggle('active', r.dataset.macro === macro));

    const detailEl = document.getElementById('sectors-detail');
    if (!detailEl) return;
    const sec = _sectorInfoMap[macro];
    if (!sec) { detailEl.innerHTML = '<div class="sectors-empty">Sector not found.</div>'; return; }

    const ownColor = FACTION_COLOURS[sec.owner_id] || 'var(--text-dim)';
    const near     = _nearestStation[macro];
    const jumpsTxt = near ? (near.jumps === 0 ? 'In sector' : `${near.jumps} jump${near.jumps !== 1 ? 's' : ''}`) : '—';
    const sunTxt   = (sec.sunlight != null) ? Math.round(sec.sunlight * 100) + '%' : '—';

    // Single-sector clusters share the sector's name, so the cluster subtitle
    // would just repeat it — only show it when it actually differs.
    const clusterName = _clusterName(sec.cluster_macro, sec);
    const showCluster = clusterName.trim().toLowerCase() !== (sec.sector_name || '').trim().toLowerCase();

    // Owner standing — reuse the Diplomacy tab's tierBadge so the label is
    // byte-identical (same text, same colour) to the Faction Standings table.
    const ownerRep   = sec.owner_id ? _repByFaction[sec.owner_id] : null;
    const ownerBadge = ownerRep ? ' ' + tierBadge(ownerRep.tier) : '';

    let html = `<div class="sd-head"><div class="sd-name">${sec.sector_name || macro}</div>`
             + (showCluster ? `<div class="sd-cluster">${clusterName}</div>` : '')
             + `</div>`;

    // Summary tags — a thin, instantly-visible row characterising the sector.
    const tags = _sectorTags(sec, macro, ownerRep);
    if (tags.length) {
      html += '<div class="sd-tags">'
            + tags.map(t => `<span class="sd-tag ${t.cls}">${t.label}</span>`).join('')
            + '</div>';
    }

    html += `<div class="sd-owner"><span style="color:${ownColor}">${_ownerLabel(sec.owner_name)}</span>${ownerBadge}</div>`;

    // Key stats.
    html += '<div class="sd-grid">'
          + `<div class="sd-stat"><div class="sd-stat-label">Sunlight</div><div class="sd-stat-value">${sunTxt}</div></div>`
          + `<div class="sd-stat"><div class="sd-stat-label">Nearest Station</div><div class="sd-stat-value">${jumpsTxt}</div></div>`;
    if (near) html += `<div class="sd-stat"><div class="sd-stat-label">Station</div><div class="sd-stat-value" style="font-size:13px;font-family:var(--font-cond)">${near.name}</div></div>`;
    html += '</div>';

    // The player's own stations in this sector. Click jumps to the station card.
    const myStations = _playerStaBySector[macro] || [];
    if (myStations.length) {
      html += `<div class="sd-section-title">Your Stations (${myStations.length})</div><div class="sd-list">`;
      for (const st of myStations) {
        const code = st.code || '';
        html += `<div class="sd-sta-row" onclick="goToStation('${code}')">`
              + `<i class="ti ti-building-factory-2"></i>`
              + `<span class="sd-sta-name">${st.name || code || 'Station'}</span>`
              + (code ? `<span class="sd-sta-code">${code}</span>` : '')
              + `</div>`;
      }
      html += '</div>';
    }

    // The player's own ships in this sector, as a collapsible set (default closed
    // to stay compact). The summary line carries the count + a role breakdown.
    const myShips = _playerShipsBySector[macro] || [];
    if (myShips.length) {
      const cat = { miner: 0, trader: 0, combat: 0 };
      for (const sp of myShips) cat[_shipCategory(sp.role)]++;
      const breakdown = [
        cat.miner  && `${cat.miner} mining`,
        cat.trader && `${cat.trader} trade`,
        cat.combat && `${cat.combat} combat`,
      ].filter(Boolean).join(' · ');
      html += `<details class="sd-ships"><summary class="sd-ships-sum">`
            + `<i class="ti ti-chevron-right sd-ships-chev"></i>`
            + `<span class="sd-ships-title">Your Ships (${myShips.length})</span>`
            + `<span class="sd-ships-break">${breakdown}</span></summary>`
            + `<div class="sd-ships-list">`;
      for (const sp of myShips) {
        html += `<div class="sd-ship-row">`
              + `<span class="sd-ship-name">${sp.display_name || sp.name || sp.code || 'Ship'}</span>`
              + `<span class="sd-ship-role">${sp.role || ''}</span>`
              + (sp.code ? `<span class="sd-ship-code">${sp.code}</span>` : '')
              + `</div>`;
      }
      html += '</div></details>';
    }

    // Mineable resources, richest first. A 3-column grid keeps the Yield and
    // Amount columns aligned across rows; a header labels them once (no per-row
    // abbreviations). 9.00's `amount` is a live figure that depletes/regenerates.
    const resources = sec.resources || [];
    if (resources.length) {
      html += '<div class="sd-section-title">Resources</div><div class="sd-res-table">'
            + '<div class="sd-res-head"><span></span>'
            + '<span class="sd-res-h">Yield</span><span class="sd-res-h">Amount</span></div>';
      for (const res of resources) {
        const yl = res.yield_level || '';
        html += `<div class="sd-res-row">`
              + `<span class="sd-res-name">${res.ware_name || res.ware}</span>`
              + `<span class="sd-res-yield" data-yield="${yl}">${_yieldLabel(yl)}</span>`
              + `<span class="sd-res-amt">${_fmtFull(res.recharge_max)}</span></div>`;
      }
      html += '</div>';
    }

    // Connections (gates / highways). Undiscovered neighbours are omitted, to
    // match the map where jump-lines to undiscovered sectors aren't drawn.
    const links = (_sectorAdj[macro] || [])
      .filter(lk => { const ns = _sectorInfoMap[lk.macro]; return ns && ns.is_discovered; })
      .sort((a, b) => a.cost - b.cost);
    if (links.length) {
      html += '<div class="sd-section-title">Connections</div><div class="sd-list">';
      for (const lk of links) {
        const ns    = _sectorInfoMap[lk.macro];
        const nName = ns.sector_name || lk.macro;
        const nDot  = FACTION_COLOURS[ns.owner_id] || '#6e7681';
        const costTxt = lk.cost === 0 ? 'highway' : `${lk.cost} jump${lk.cost !== 1 ? 's' : ''}`;
        html += `<div class="sd-conn-row" onclick="showSectorDetail('${lk.macro}')">`
              + `<span class="sr-dot" style="background:${nDot}"></span>`
              + `<span class="sd-conn-name">${nName}</span>`
              + `<span class="sd-conn-cost">${costTxt}</span></div>`;
      }
      html += '</div>';
    }

    // NPC station presence by faction.
    const facs = _npcBySector[macro] || [];
    if (facs.length) {
      html += '<div class="sd-section-title">Station Presence</div><div class="sd-list">';
      for (const f of facs) {
        const fc = FACTION_COLOURS[f.owner_id] || '#6e7681';
        html += `<div class="sd-fac-row">`
              + `<span class="sr-dot" style="background:${fc}"></span>`
              + `<span class="sd-fac-name">${_ownerLabel(f.owner_name)}</span>`
              + `<span class="sd-fac-count">${f.count}</span></div>`;
      }
      html += '</div>';
    }

    detailEl.innerHTML = html;
  }

  // Click handlers for the fleet table:
  //   .crew-link  → jump to that pilot's crew file
  //   .stn-link   → switch to Stations tab and scroll to that station's card
  document.getElementById('fleet-table').addEventListener('click', function(e) {
    // Crew file navigation (pilot stars)
    const crewLink = e.target.closest('.crew-link');
    if (crewLink) {
      e.stopPropagation();
      const allIdx = parseInt(crewLink.dataset.crewIdx, 10);
      if (!isNaN(allIdx) && allIdx >= 0) jumpToCrew(allIdx);
      return;
    }
    // Station navigation (homebase code)
    const stnLink = e.target.closest('.stn-link');
    if (stnLink) {
      e.stopPropagation();
      const code = stnLink.dataset.stnCode;
      if (code) goToStation(code);
    }
  });

  // Shared hover tooltip — used for hull bars, pilot skills, and storage breakdowns.
  (function() {
    const tip = document.getElementById('hull-tip');

    function moduleTipHtml(groups) {
      // Renders module groups as category headers followed by name × count rows.
      return `<div style="min-width:180px;max-width:260px;padding:2px 0">` +
        groups.map(g =>
          `<div style="margin-bottom:8px">
             <div style="font-size:9px;letter-spacing:0.12em;text-transform:uppercase;
                         color:var(--text-faint);margin-bottom:4px;padding-bottom:3px;
                         border-bottom:1px solid var(--border)">${g.category}</div>
             ${g.items.map(([name, count]) =>
               `<div style="display:flex;justify-content:space-between;align-items:baseline;
                            gap:12px;padding:1px 0">
                  <span style="color:var(--text-dim);font-size:11px;white-space:nowrap;
                               overflow:hidden;text-overflow:ellipsis">${name}</span>
                  <span style="color:var(--text-faint);font-size:10px;flex-shrink:0">×${count}</span>
                </div>`
             ).join('')}
           </div>`
        ).join('') +
      `</div>`;
    }

    function loadoutTipHtml(loadout) {
      // Ship equipment grouped by slot — same category + "name ×count" layout as
      // moduleTipHtml. Each row shows the maker faction (when the part has one;
      // generic parts like thrusters don't) and the installed count.
      const SLOT_ORDER = [
        ['weapon',   'Weapons'],
        ['turret',   'Turrets'],
        ['shield',   'Shields'],
        ['engine',   'Engine'],
        ['thruster', 'Thruster'],
      ];
      const FACTION = {
        argon:'Argon', paranid:'Paranid', teladi:'Teladi', split:'Split',
        terran:'Terran', boron:'Boron', xenon:'Xenon', khaak:"Kha'ak",
        pirate:'Pirate', yaki:'Yaki',
      };
      const sections = SLOT_ORDER.map(([slot, label]) => {
        // Skip unresolved internal parts (raw macros still end in "_macro"), so a
        // deployable's hidden engine never shows a raw id in the tooltip.
        const items = loadout.filter(e => e.slot === slot && !e.name.endsWith('_macro'));
        if (!items.length) return '';
        const rows = items.map(e => {
          const mk  = e.mk ? ` Mk${e.mk}` : '';
          const fac = FACTION[e.race]
            ? `<span style="color:var(--text-dim);font-size:10px;margin-right:8px">${FACTION[e.race]}</span>` : '';
          return `<div style="display:flex;justify-content:space-between;align-items:baseline;gap:12px;padding:1px 0">
                    <span style="color:var(--text-dim);font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${e.name}${mk}</span>
                    <span style="flex-shrink:0;white-space:nowrap">${fac}<span style="color:var(--text-faint);font-size:10px">×${e.count}</span></span>
                  </div>`;
        }).join('');
        return `<div style="margin-bottom:8px">
                  <div style="font-size:9px;letter-spacing:0.12em;text-transform:uppercase;color:var(--text-faint);margin-bottom:4px;padding-bottom:3px;border-bottom:1px solid var(--border)">${label}</div>
                  ${rows}
                </div>`;
      }).join('');
      return `<div style="min-width:200px;max-width:280px;padding:2px 0">${sections || '—'}</div>`;
    }

    function budgetTipHtml(d) {
      // Per-slice economy tooltip: ware name in its colour, share of budget, the
      // amount × price = value figures, and which rule set the value (basis).
      const fmt = n => Math.round(n).toLocaleString();
      const BASIS = {
        'manual storage cap':    'Manual storage cap',
        'auto: 2h production':   'Automatic · 2h production',
        'auto: 2h consumption':  'Automatic · 2h consumption',
        'trade (max price)':     'Trade ware · max price',
        'buy order (unverified)':'Buy order',
      };
      return `<div style="min-width:200px;padding:2px 0">
        <div style="display:flex;justify-content:space-between;align-items:baseline;gap:12px;margin-bottom:5px">
          <span style="color:${d.colour};font-size:11px;letter-spacing:0.06em;text-transform:uppercase;white-space:nowrap">${d.ware}</span>
          <span style="color:${d.colour};font-family:var(--font-mono);font-size:12px">${d.pct}%</span>
        </div>
        <div style="display:flex;justify-content:space-between;gap:12px;padding:1px 0">
          <span style="color:var(--text-faint);font-size:10px">Amount × Price</span>
          <span style="color:var(--text-dim);font-family:var(--font-mono);font-size:10px">${fmt(d.amount)} × ${fmt(d.price)}</span>
        </div>
        <div style="display:flex;justify-content:space-between;gap:12px;padding:1px 0">
          <span style="color:var(--text-faint);font-size:10px">Value</span>
          <span style="color:var(--lime);font-family:var(--font-mono);font-size:11px">${fmt(d.value)} Cr</span>
        </div>
        <div style="margin-top:5px;padding-top:4px;border-top:1px solid var(--border);font-size:10px;color:var(--text-faint)">${BASIS[d.basis] || d.basis}</div>
      </div>`;
    }

    function cashflowTipHtml(d) {
      // Cash-flow hover: one hour's trade breakdown — the hour's net at top,
      // then a row per ware (sells ▲ green, buys ▼ red) with units and credits.
      const fmtU = n => Math.round(n).toLocaleString();
      const fmtC = n => (n < 0 ? '−' : '+') + Math.abs(Math.round(n)).toLocaleString();
      const span = d.hAgo === 0 ? 'Past hour' : `${d.hAgo}–${d.hAgo + 1}h ago`;
      const MAX = 8;
      const shown = d.rows.slice(0, MAX);
      const more  = d.rows.length - shown.length;
      return `<div style="min-width:230px;padding:2px 0">
        <div style="display:flex;justify-content:space-between;align-items:baseline;gap:12px;margin-bottom:5px;padding-bottom:4px;border-bottom:1px solid var(--border)">
          <span style="color:var(--text-faint);font-size:10px;letter-spacing:0.08em;text-transform:uppercase">${span}</span>
          <span style="color:${d.net >= 0 ? '#19e6c8' : '#ef5350'};font-family:var(--font-mono);font-size:11px">${fmtC(d.net)} Cr</span>
        </div>` +
        shown.map(r => `
          <div style="display:flex;justify-content:space-between;align-items:baseline;gap:12px;padding:1px 0">
            <span style="font-size:10px;letter-spacing:0.04em;text-transform:uppercase;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:130px;color:${r.colour}">
              <span style="color:${r.dir === 'sell' ? '#19e6c8' : '#ef5350'}">${r.dir === 'sell' ? '▲' : '▼'}</span> ${r.ware}
            </span>
            <span style="font-family:var(--font-mono);font-size:10px;color:var(--text-dim);flex-shrink:0;white-space:nowrap">
              ${fmtU(r.units)}u · <span style="color:${r.cr >= 0 ? '#19e6c8' : '#ef5350'}">${fmtC(r.cr)}</span>
            </span>
          </div>`).join('') +
        (more > 0 ? `<div style="margin-top:4px;font-size:10px;color:var(--text-faint)">+${more} more ware${more > 1 ? 's' : ''}</div>` : '') +
      `</div>`;
    }

    function cashflowTradeTipHtml(d) {
      // By-Trade hover: one individual trade's full details + the running total.
      const fmtU = n => Math.round(n).toLocaleString();
      const fmtC = n => (n < 0 ? '−' : '+') + Math.abs(Math.round(n)).toLocaleString();
      const ago  = d.hAgo < 1 ? Math.round(d.hAgo * 60) + 'm ago'
                              : d.hAgo.toFixed(1).replace(/\.0$/, '') + 'h ago';
      // The trade has two "other side" fields: counterparty (the station the
      // goods went to / came from — the scanner resolves this for almost all
      // sells) and ship (the transport, resolved for most buys but often a
      // transient NPC buyer whose ID is a raw "[0x…]" hex on sells). Show the
      // station as the buyer/seller and the transport as the ship; fall back to
      // "Unknown" only when neither resolves.
      const isRawId = s => /^\[?0x[0-9a-f]+\]?$/i.test(String(s).trim());
      const shipResolved = d.ship && !isRawId(d.ship);
      const partyLabel   = d.dir === 'sell' ? 'Buyer' : 'Seller';
      const row = (label, value, colour) => `
        <div style="display:flex;justify-content:space-between;gap:12px;padding:1px 0">
          <span style="color:var(--text-faint);font-size:10px">${label}</span>
          <span style="color:${colour || 'var(--text-dim)'};font-family:var(--font-mono);font-size:10px;text-align:right">${value}</span>
        </div>`;
      return `<div style="min-width:220px;padding:2px 0">
        <div style="display:flex;justify-content:space-between;align-items:baseline;gap:12px;margin-bottom:5px;padding-bottom:4px;border-bottom:1px solid var(--border)">
          <span style="color:${d.colour};font-size:11px;letter-spacing:0.05em;text-transform:uppercase;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:160px">
            <span style="color:${d.dir === 'sell' ? '#19e6c8' : '#ef5350'}">${d.dir === 'sell' ? '▲ SOLD' : '▼ BOUGHT'}</span> ${d.ware}
          </span>
        </div>` +
        row('Amount × Price', `${fmtU(d.units)} × ${fmtU(d.priceEa)} Cr`) +
        row('Trade value', `${fmtC(d.total)} Cr`, d.total >= 0 ? '#19e6c8' : '#ef5350') +
        (d.counterparty ? row(partyLabel, d.counterparty) : '') +
        (shipResolved   ? row('Ship', d.ship) : '') +
        (!d.counterparty && !shipResolved ? row(partyLabel, 'Unknown') : '') +
        `<div style="margin-top:5px;padding-top:4px;border-top:1px solid var(--border);text-align:right;font-size:10px;color:var(--text-faint)">${ago}</div>
      </div>`;
    }

    function wareChartTipHtml(d) {
      // By-Ware hover: the ware, its exact price, where that price sits in
      // the game's min–avg–max band, the quantity, and the trade's counterparty.
      // d.dir ('sell'|'buy') controls the direction label and counterparty role.
      const fmtU = n => Math.round(n).toLocaleString();
      const ago  = d.hAgo < 1
        ? Math.round(d.hAgo * 60) + 'm ago'
        : d.hAgo.toFixed(1).replace(/\.0$/, '') + 'h ago';

      // Express the price relative to the ware's average: +12% above or −5% below.
      const diff    = d.price - d.pAvg;
      const diffPct = d.pAvg > 0 ? Math.round(Math.abs(diff) / d.pAvg * 100) : 0;
      const diffCol = diff >= 0 ? '#19e6c8' : '#ef5350';
      const diffStr = diff === 0
        ? 'at avg'
        : `${diff > 0 ? '+' : '−'}${diffPct}% vs avg`;

      const isRawId = s => /^\[?0x[0-9a-f]+\]?$/i.test(String(s).trim());
      const shipResolved = d.ship && !isRawId(d.ship);

      const row = (label, value, colour) => `
        <div style="display:flex;justify-content:space-between;gap:12px;padding:1px 0">
          <span style="color:var(--text-faint);font-size:10px">${label}</span>
          <span style="color:${colour || 'var(--text-dim)'};font-family:var(--font-mono);font-size:10px;text-align:right">${value}</span>
        </div>`;

      return `<div style="min-width:220px;padding:2px 0">
        <div style="display:flex;justify-content:space-between;align-items:baseline;gap:12px;
                    margin-bottom:5px;padding-bottom:4px;border-bottom:1px solid var(--border)">
          <span style="color:${d.colour};font-size:11px;letter-spacing:0.05em;text-transform:uppercase;
                       white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:180px">
            <span style="color:${d.dir === 'buy' ? '#ef5350' : '#19e6c8'}">${d.dir === 'buy' ? '▼ BOUGHT' : '▲ SOLD'}</span> ${d.ware}
          </span>
        </div>` +
        row('Price',      `${fmtU(d.price)} Cr`) +
        row('vs Average', diffStr, diffCol) +
        row('Band',       `${fmtU(d.pMin)} – ${fmtU(d.pMax)} Cr`) +
        row('Amount',     `${fmtU(d.amount)} units`) +
        (d.counterparty ? row(d.dir === 'buy' ? 'Seller' : 'Buyer', d.counterparty) : '') +
        (shipResolved   ? row('Ship',  d.ship)         : '') +
        `<div style="margin-top:5px;padding-top:4px;border-top:1px solid var(--border);
                     text-align:right;font-size:10px;color:var(--text-faint)">${ago}</div>
      </div>`;
    }

    function avgPriceTipHtml(d) {
      // Avg Price hover: the hour's mean price (big), how it moved vs the
      // previous traded hour (teal ▲ / red ▼), the min–max spread that hour as a
      // little band with a glowing marker at the average, and the trade count.
      const fmtU = n => Math.round(n).toLocaleString();
      const span = d.hAgo === 0 ? 'Past hour' : `${d.hAgo}–${d.hAgo + 1}h ago`;
      const dirLabel = d.dir === 'sell' ? '▲ SOLD' : '▼ BOUGHT';
      const dirCol   = d.dir === 'sell' ? '#19e6c8' : '#ef5350';

      // Delta vs the previous populated hour.
      let deltaHtml = `<span style="color:var(--text-faint);font-size:10px">first hour</span>`;
      if (d.prevAvg != null && d.prevAvg > 0) {
        const diff = d.avg - d.prevAvg;
        const pct  = Math.abs(diff / d.prevAvg * 100);
        const flat = Math.abs(diff) < 0.005 * d.prevAvg;
        const c    = flat ? 'var(--text-faint)' : diff > 0 ? '#19e6c8' : '#ef5350';
        const ch   = flat ? '▬' : diff > 0 ? '▲' : '▼';
        deltaHtml  = `<span style="color:${c};font-family:var(--font-mono);font-size:11px">${ch} ${pct.toFixed(1)}%</span>`;
      }

      // Marker position within the hour's min–max range (clamped).
      const range   = (d.max - d.min) || 1;
      const avgFrac = Math.max(0, Math.min(1, (d.avg - d.min) / range)) * 100;
      const spread  = d.max > d.min
        ? `<div style="display:flex;justify-content:space-between;font-size:9px;color:var(--text-faint);font-family:var(--font-mono);margin-bottom:2px">
             <span>${fmtU(d.min)}</span><span style="letter-spacing:0.12em">SPREAD</span><span>${fmtU(d.max)}</span>
           </div>
           <div style="position:relative;height:5px;background:${d.colour}22;border-radius:3px;margin-bottom:6px;overflow:visible">
             <div style="position:absolute;inset:0;background:linear-gradient(90deg,${d.colour}33,${d.colour}66);border-radius:3px"></div>
             <div style="position:absolute;left:${avgFrac.toFixed(1)}%;top:50%;width:7px;height:7px;border-radius:50%;background:${d.colour};transform:translate(-50%,-50%);box-shadow:0 0 5px ${d.colour}"></div>
           </div>`
        : `<div style="font-size:9px;color:var(--text-faint);font-family:var(--font-mono);margin-bottom:6px">single trade · no spread</div>`;

      return `<div style="min-width:210px;padding:2px 0">
        <div style="display:flex;justify-content:space-between;align-items:baseline;gap:12px;margin-bottom:6px;padding-bottom:4px;border-bottom:1px solid var(--border)">
          <span style="color:${d.colour};font-size:11px;letter-spacing:0.05em;text-transform:uppercase;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:160px">
            <span style="color:${dirCol}">${dirLabel}</span> ${d.ware}
          </span>
          <span style="color:var(--text-faint);font-size:10px;letter-spacing:0.06em;white-space:nowrap">${span}</span>
        </div>
        <div style="display:flex;align-items:baseline;justify-content:space-between;gap:10px;margin-bottom:7px">
          <span style="font-family:var(--font-mono);font-size:18px;color:${d.colour};line-height:1">${fmtU(d.avg)}<span style="font-size:10px;color:var(--text-faint)"> cr avg</span></span>
          ${deltaHtml}
        </div>
        ${spread}
        <div style="display:flex;justify-content:space-between;gap:12px">
          <span style="color:var(--text-faint);font-size:10px">Trades this hour</span>
          <span style="color:var(--text-dim);font-family:var(--font-mono);font-size:10px">${d.count}</span>
        </div>
      </div>`;
    }

    function storageTipHtml(types) {
      // Renders each storage type as a label + % row followed by a fill bar.
      // Label, percentage, and m³ text all use the category's fixed accent colour.
      // The Total row is preceded by a thin separator line.
      const fmtM3 = v => v >= 1e6 ? (v/1e6).toFixed(2)+'M' : v >= 1e3 ? (v/1e3).toFixed(1)+'K' : v;
      return `<div style="min-width:220px;padding:2px 0">` +
        types.map(t => {
          const barW = t.pct != null ? Math.min(t.pct, 100) : 0;
          const pctLabel = t.pct != null ? `${t.pct}%` : '—';
          const sub = (t.m3 != null && t.max != null)
            ? `<div style="margin-top:2px;text-align:right;font-size:10px;color:${t.color};opacity:0.75">${fmtM3(t.m3)} / ${fmtM3(t.max)} m³</div>`
            : '';
          const sep = t.isTotal
            ? `<div style="border-top:1px solid var(--border);margin:5px 0 8px"></div>`
            : '';
          return `${sep}<div style="margin-bottom:8px">
            <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:3px">
              <span style="font-size:10px;letter-spacing:0.1em;text-transform:uppercase;color:${t.color}">${t.label}</span>
              <span style="color:${t.color};font-family:var(--font-mono);margin-left:12px">${pctLabel}</span>
            </div>
            <div style="height:6px;background:var(--border);border-radius:2px;overflow:hidden">
              <div style="height:100%;width:${barW}%;background:${t.color};border-radius:2px"></div>
            </div>
            ${sub}
          </div>`;
        }).join('') +
      `</div>`;
    }

    document.addEventListener('mousemove', function(e) {
      // Clear all chart highlight rings at the start of each move; whichever
      // chart the cursor is over will re-show its own ring below.
      document.querySelectorAll('.cf-detail-marker,.cf-ware-marker').forEach(m => { m.style.display = 'none'; });
      // Clear Avg Price bar highlight + readout line (reapplied below if hovered).
      document.querySelectorAll('.avg-bars rect.avg-hot').forEach(r => r.classList.remove('avg-hot'));
      document.querySelectorAll('.avg-hot-line').forEach(l => { l.style.opacity = '0'; });

      const el = e.target.closest('[data-hull-tip],[data-pilot-skills],[data-storage-tip],[data-modules-tip],[data-loadout-tip],[data-fleet-tip],[data-budget-tip],[data-cashflow-tip],[data-cfdetail],[data-cfware],[data-avgtip]');
      if (!el) { tip.style.display = 'none'; return; }

      if (el.dataset.cfdetail) {
        // By-Trade chart: find the trade nearest the cursor's x position and
        // show its details, with the highlight ring snapped to that point.
        const arr = cashflowDetailData[el.dataset.cfdetail];
        if (!arr || !arr.length) { tip.style.display = 'none'; return; }
        const r = el.getBoundingClientRect();
        const f = (e.clientX - r.left) / r.width;
        let best = arr[0], bd = Infinity;
        for (const p of arr) { const dd = Math.abs(p.fx - f); if (dd < bd) { bd = dd; best = p; } }
        tip.innerHTML = cashflowTradeTipHtml(best);
        tip.style.color = '';
        tip.style.whiteSpace = 'normal';
        const svg = el.closest('svg');
        const mk = svg && svg.querySelector('.cf-detail-marker');
        if (mk) { mk.setAttribute('cx', best.vbx); mk.setAttribute('cy', best.vby); mk.style.display = 'block'; }
      } else if (el.dataset.cfware) {
        // By-Ware chart: find the nearest visible trade dot by Euclidean distance
        // so the cursor naturally locks on to whichever ware line it is closest to.
        const sc  = el.dataset.cfware;
        const arr = wareChartData[sc];
        if (!arr || !arr.length) { tip.style.display = 'none'; return; }
        const r  = el.getBoundingClientRect();
        const fx = (e.clientX - r.left) / r.width;
        const fy = (e.clientY - r.top)  / r.height;
        let best = null, bd = Infinity;
        for (const p of arr) {
          // Skip points belonging to wares the user has toggled off.
          if (wareVisibility[sc] && wareVisibility[sc][p.ware] === false) continue;
          const dd = (p.fx - fx) ** 2 + (p.fy - fy) ** 2;
          if (dd < bd) { bd = dd; best = p; }
        }
        if (!best) { tip.style.display = 'none'; return; }
        tip.innerHTML = wareChartTipHtml(best);
        tip.style.color = '';
        tip.style.whiteSpace = 'normal';
        const svg = el.closest('svg');
        const mk  = svg && svg.querySelector('.cf-ware-marker');
        if (mk) {
          mk.setAttribute('cx', best.vbx);
          mk.setAttribute('cy', best.vby);
          mk.setAttribute('stroke', best.colour);
          mk.style.display = 'block';
        }
      } else if (el.dataset.cashflowTip) {
        // Cash-flow chart: one hour's per-ware trade breakdown
        tip.innerHTML = cashflowTipHtml(JSON.parse(decodeURIComponent(el.dataset.cashflowTip)));
        tip.style.color      = '';
        tip.style.whiteSpace = 'normal';
      } else if (el.dataset.avgtip) {
        // Avg Price chart: hour stats + highlight the bar and project a dashed
        // readout line from its top across to the price axis.
        const d = JSON.parse(decodeURIComponent(el.dataset.avgtip));
        tip.innerHTML       = avgPriceTipHtml(d);
        tip.style.color     = '';
        tip.style.whiteSpace = 'normal';
        const svg  = el.closest('svg');
        const bars = svg && svg.querySelector('.avg-bars');
        const bar  = bars && bars.children[+el.dataset.avgI];
        if (bar) {
          bar.classList.add('avg-hot');
          const y  = +bar.getAttribute('y');
          const cx = +bar.getAttribute('x') + (+bar.getAttribute('width')) / 2;
          const line = svg.querySelector('.avg-hot-line');
          if (line) {
            line.setAttribute('x1', 56); // ml — the price axis
            line.setAttribute('x2', cx.toFixed(1));
            line.setAttribute('y1', y.toFixed(1));
            line.setAttribute('y2', y.toFixed(1));
            line.setAttribute('stroke', d.colour);
            line.style.opacity = '1';
          }
        }
      } else if (el.dataset.budgetTip) {
        // Economy pie slice: ware share, figures, and basis
        tip.innerHTML = budgetTipHtml(JSON.parse(decodeURIComponent(el.dataset.budgetTip)));
        tip.style.color      = '';
        tip.style.whiteSpace = 'normal';
      } else if (el.dataset.pilotSkills) {
        // Pilot skills: name header + per-skill star rows.
        // data-pilot-name is the pilot's display name (moved off the row).
        tip.innerHTML = pilotTipHtml(JSON.parse(el.dataset.pilotSkills), el.dataset.pilotName || '');
        tip.style.color      = '';
        tip.style.whiteSpace = 'nowrap';
      } else if (el.dataset.storageTip) {
        // Storage breakdown: one bar row per container type
        tip.innerHTML = storageTipHtml(JSON.parse(decodeURIComponent(el.dataset.storageTip)));
        tip.style.color      = '';
        tip.style.whiteSpace = 'normal';
      } else if (el.dataset.modulesTip) {
        // Module list: grouped by category with counts
        tip.innerHTML = moduleTipHtml(JSON.parse(decodeURIComponent(el.dataset.modulesTip)));
        tip.style.color      = '';
        tip.style.whiteSpace = 'normal';
      } else if (el.dataset.loadoutTip) {
        // Ship equipment: grouped by slot with faction + counts
        tip.innerHTML = loadoutTipHtml(JSON.parse(decodeURIComponent(el.dataset.loadoutTip)));
        tip.style.color      = '';
        tip.style.whiteSpace = 'normal';
      } else if (el.dataset.fleetTip) {
        // Assigned fleet breakdown: pre-rendered HTML encoded into the attribute
        tip.innerHTML = decodeURIComponent(el.dataset.fleetTip);
        tip.style.color      = '';
        tip.style.whiteSpace = 'normal';
      } else {
        // Hull bar: plain coloured text
        tip.textContent      = el.dataset.hullTip;
        tip.style.color      = el.dataset.hullColor || '';
        tip.style.whiteSpace = 'nowrap';
      }

      tip.style.display = 'block';
      // e.clientX/Y are in physical pixels; tip.style positions are in zoomed
      // CSS pixels. Divide by zoom to convert into the correct coordinate space.
      // window.innerWidth is also physical in QtWebEngine, so divide it too
      // before subtracting tip.offsetWidth (which IS in CSS pixels).
      const _z = parseFloat(document.documentElement.style.zoom) || 1;
      const x = Math.min(e.clientX / _z + 14, window.innerWidth / _z - tip.offsetWidth - 8);
      const y = Math.max(e.clientY / _z - 32, 8);
      tip.style.left = x + 'px';
      tip.style.top  = y + 'px';
    });
    document.addEventListener('mouseleave', function() { tip.style.display = 'none'; });

    // ── Scrubber zoom + pan drag handler ──────────────────────────────────────
    // Mousedown on the handle body starts a pan; on either edge grip starts a
    // resize.  mousemove / mouseup are on the document so drags that leave the
    // element are not interrupted.
    (function() {
      document.addEventListener('mousedown', function(e) {
        const resizeEl = e.target.closest('.cf-scrubber-resize[data-side]');
        const handleEl = !resizeEl && e.target.closest('.cf-scrubber-handle');
        const trackEl  = e.target.closest('[data-scrubber]');
        // Only act when the click was inside a known scrubber part.
        if (!trackEl || (!resizeEl && !handleEl)) return;

        const safeCode = trackEl.dataset.scrubber;
        if (!cfZoom[safeCode]) return;
        const { hours, offsetHours } = cfZoom[safeCode];

        cfScrubDrag = {
          safeCode,
          // 'pan' moves both edges; 'resize-left'/'resize-right' moves one edge.
          mode:       resizeEl ? (resizeEl.dataset.side === 'left' ? 'resize-left' : 'resize-right') : 'pan',
          startX:     e.clientX,
          startHours: hours,
          startOff:   offsetHours,
          trackW:     trackEl.getBoundingClientRect().width,
          _raf:       false,
        };
        e.preventDefault(); // prevent text selection during drag
      });

      document.addEventListener('mousemove', function(e) {
        if (!cfScrubDrag) return;
        const { safeCode, mode, startX, startHours, startOff, trackW } = cfScrubDrag;
        // Convert mouse delta (px) to hours using the track's current width.
        const dH = (e.clientX - startX) / trackW * CF_MAX_HOURS;

        let newH = startHours, newOff = startOff;
        if (mode === 'pan') {
          // Both edges shift by the same amount.
          // Dragging right → toward NOW → offset decreases.
          newOff = startOff - dH;
        } else if (mode === 'resize-left') {
          // Left edge moves, right edge (= offsetHours) is fixed.
          // Dragging right → window shrinks; left → grows.
          newH = startHours - dH;
        } else {
          // resize-right: right edge moves, left edge position is fixed.
          // Fixed left = startOff + startHours, so offset = leftFixed - newH.
          newH   = startHours  + dH;
          newOff = startOff    - dH;
        }

        // Clamp window width and offset so nothing goes out of range.
        newH   = Math.max(CF_MIN_HOURS, Math.min(CF_MAX_HOURS, newH));
        newOff = Math.max(0, Math.min(CF_MAX_HOURS - newH, newOff));
        cfZoom[safeCode] = { hours: newH, offsetHours: newOff };

        // Fast-path: update the handle geometry immediately so the track feels
        // responsive even before the full rAF chart rebuild completes.
        const track = document.querySelector(`[data-scrubber="${safeCode}"]`);
        if (track) {
          const handle = track.querySelector('.cf-scrubber-handle');
          if (handle) {
            handle.style.left  = ((CF_MAX_HOURS - newOff - newH) / CF_MAX_HOURS * 100).toFixed(2) + '%';
            handle.style.width = (newH / CF_MAX_HOURS * 100).toFixed(2) + '%';
          }
        }

        // Throttle chart rebuilds to one per animation frame so intermediate
        // mouse events don't pile up and cause jank.
        if (!cfScrubDrag._raf) {
          cfScrubDrag._raf = true;
          requestAnimationFrame(function() {
            if (cfScrubDrag) { cfScrubDrag._raf = false; rebuildCfChart(safeCode); }
          });
        }
      });

      document.addEventListener('mouseup', function() {
        if (cfScrubDrag) {
          // One final rebuild on release to guarantee the chart matches the
          // handle's resting position even if the last rAF fired early.
          rebuildCfChart(cfScrubDrag.safeCode);
          cfScrubDrag = null;
        }
      });
    })();
  })();

  // Primary data path: the Qt QWebChannel bridge exposed by main_ui.py.
  // When running inside QtWebEngine, `qt.webChannelTransport` exists and we pull
  // the empire data straight from the EmpireBridge.
  //
  // Browser fallback: when opened in a plain browser (e.g. the dev preview
  // server), there is no Qt bridge, so we fetch the exported JSON over HTTP
  // instead. This lets the UI render with real data outside the desktop app for
  // fast layout iteration. The bridge always wins when present — this branch
  // only runs when it's absent.
