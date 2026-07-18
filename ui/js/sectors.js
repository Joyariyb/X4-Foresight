  // Core role: Master-detail sector view built from universe map data (_sectorInfoMap, _sectorAdj, _nearestStation, _npcBySector).

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

  // metricHtml is an optional right-aligned value for the active sort.
  function _sectorRowHtml(s, metricHtml) {
    const dot    = FACTION_COLOURS[s.owner_id] || '#6e7681';
    const active = s.sector_macro === _selectedSector ? ' active' : '';
    // Count of the player's own stations in this sector (badge when > 0).
    const pCount = (_playerStaBySector[s.sector_macro] || []).length;
    const badge  = pCount ? `<span class="sr-sta-badge" data-text-tip="${pCount} of your stations"><i class="ti ti-building-factory-2"></i>${pCount}</span>` : '';
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

    const ownColor = FACTION_COLOURS[sec.owner_id] || 'var(--text-secondary)';
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
    if (near) html += `<div class="sd-stat"><div class="sd-stat-label">Station</div><div class="sd-stat-value" style="font-size:13px;font-family:var(--font-label)">${near.name}</div></div>`;
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

    // NPC station presence by faction, one collapsible <details> per faction
    // (closed by default, same idiom as "Your Ships" above). Expanding lists
    // the faction's individual stations; a station is only clickable through
    // to the NPC Inspector if it's in allNpcTradePartners (npc-stations.js) —
    // that list is capped to NPC_TRADE_RANGE_MAX_JUMPS server-side, so a
    // station further out has no inspector data to show.
    const facs = _npcBySector[macro] || [];
    if (facs.length) {
      const reachable = new Set(allNpcTradePartners.map(s => s.object_id));
      html += '<div class="sd-section-title">Station Presence</div><div class="sd-list">';
      for (const f of facs) {
        const fc = FACTION_COLOURS[f.owner_id] || '#6e7681';
        html += `<details class="sd-fac"><summary class="sd-fac-sum">`
              + `<i class="ti ti-chevron-right sd-fac-chev"></i>`
              + `<span class="sr-dot" style="background:${fc}"></span>`
              + `<span class="sd-fac-name">${_ownerLabel(f.owner_name)}</span>`
              + `<span class="sd-fac-count">${f.count}</span></summary>`
              + `<div class="sd-fac-list">`;
        for (const st of (f.stations || [])) {
          const icon = npcStationIcon(st.station_type);
          if (reachable.has(st.object_id)) {
            html += `<div class="sd-fac-sta-row" onclick="goToNpcStation('${st.object_id}')">`
                  + `<i class="ti ${icon}"></i>`
                  + `<span class="sd-fac-sta-name">${st.name || st.code || 'Station'}</span>`
                  + `<span class="sd-fac-sta-type">${st.station_type || ''}</span></div>`;
          } else {
            html += `<div class="sd-fac-sta-row sd-fac-sta-row--muted" data-text-tip="Outside NPC trade range — no inspector data">`
                  + `<i class="ti ${icon}"></i>`
                  + `<span class="sd-fac-sta-name">${st.name || st.code || 'Station'}</span>`
                  + `<span class="sd-fac-sta-type">${st.station_type || ''}</span></div>`;
          }
        }
        html += '</div></details>';
      }
      html += '</div>';
    }

    detailEl.innerHTML = html;
  }
