  // Core role: Renders the Stations → NPC tab — sortable trade-partner table filtered by a jump-range slider.

  // Matches NPC_TRADE_RANGE_MAX_JUMPS in export/jsonexport.py — the export
  // never sends a station beyond this, so the slider's ceiling has to agree.
  const NPC_RANGE_MAX = 5;

  let allNpcTradePartners = [];
  // Full station_trades ledger (same array populate.js's economy logs read),
  // captured here so the Station Inspector can filter it by counterparty_id
  // without needing its own copy of the render pipeline's `data`.
  let npcStationTrades    = [];
  let npcRangeMin         = 0;
  let npcRangeMax         = NPC_RANGE_MAX;
  let npcStationSortKey   = 'jumps';
  let npcStationSortDir   = 1;
  let npcTradableOnly     = false;
  let npcFactionFilter    = [];    // owner_ids to show; empty = all factions
  let npcFactionDDOpen    = false; // tracked outside the DOM — renderNpcStationsTable() rebuilds the menu from scratch each call

  // A large empire can have 1000+ reachable NPC stations (own filters/save can
  // push this well past what fleet/crew tables ever see), and the panel only
  // ever shows ~20 rows at once through its scrolling window — so the table
  // is virtualized: renderNpcStationsTable() computes the full filtered+sorted
  // set once, and renderNpcStationsVisibleRows() below only builds DOM for the
  // rows actually near the viewport. Rebuilding all 1000+ rows on every
  // slider/filter/sort tick was the actual source of the reported lag.
  let npcSortedRows    = [];  // full filtered+sorted set, rebuilt by renderNpcStationsTable()
  let npcRowHeight     = 0;   // px, measured once from a real rendered row
  let npcScrollQueued  = false;
  const NPC_ROW_BUFFER = 6;  // extra rows rendered past each viewport edge so a fast scroll doesn't flash blank rows before the next frame catches up

  // Owner names arrive as "[ANT] Antigone Republic" — strip the bracket tag
  // since the coloured badge next to it already carries the identity cue.
  function npcOwnerLabel(name) { return (name || '').replace(/^\[\w+\]\s*/, ''); }

  // The bracket tag itself (e.g. "ANT") — the compact form used where the
  // full political name would be too much, same one-word feel as hullBadge()'s
  // race labels ("Argon", "Teladi") on the Ships tab.
  function npcFactionTag(name) {
    const m = /^\[(\w+)\]/.exec(name || '');
    return m ? m[1] : npcOwnerLabel(name);
  }

  // Same coloured-tag look as hullBadge() (formatters.js) / designBadge()
  // (designs-builder.js), but keyed by owner_id rather than a display-name
  // guess — stations carry a real faction id, so there's no need for the
  // lowercase-string matching those two rely on. `short` swaps the full
  // faction name for its bracket tag, for places too tight for the whole name.
  function npcFactionBadge(id, name, short) {
    const colour = FACTION_COLOURS[id] || '#6e7681';
    const style  = `background:${hexA(colour, 0.1)};color:${colour};border:1px solid ${hexA(colour, 0.25)}`;
    const label  = short ? npcFactionTag(name) : npcOwnerLabel(name);
    return `<span class="badge" style="${style}">${label}</span>`;
  }
  function npcOwnerBadge(s) { return npcFactionBadge(s.owner_id, s.owner_name); }

  // Comparable value per station and sort key — same null-to-bottom-free
  // contract as fleet.js's sortValue()/crew.js's crewSortValue() (every field
  // here is always populated by the export, so no null handling needed).
  function npcStationSortValue(s, key) {
    if (key === 'owner') return (s.owner_name || '').toLowerCase();
    if (key === 'type')  return (s.station_type || '').toLowerCase();
    if (key === 'jumps') return s.jumps;
    return (s.name || '').toLowerCase();
  }

  function setNpcStationSort(key) {
    if (key === npcStationSortKey) {
      npcStationSortDir *= -1;
    } else {
      npcStationSortKey = key;
      npcStationSortDir = 1;
    }
    renderNpcStationsTable();
  }

  // Two thumbs can't cross — dragging one past the other just clamps it at
  // the other's position rather than letting min > max or vice versa.
  function setNpcRangeMin(value) {
    npcRangeMin = Math.min(parseInt(value, 10), npcRangeMax);
    document.getElementById('npc-range-min').value = npcRangeMin;
    renderNpcStationsTable();
  }

  function setNpcRangeMax(value) {
    npcRangeMax = Math.max(parseInt(value, 10), npcRangeMin);
    document.getElementById('npc-range-max').value = npcRangeMax;
    renderNpcStationsTable();
  }

  function setNpcTradableFilter(only, el) {
    npcTradableOnly = only;
    document.querySelectorAll('#npc-tradable-filter .fleet-subtab').forEach(t => t.classList.remove('active'));
    el.classList.add('active');
    renderNpcStationsTable();
  }

  // Toggling 'all' clears the selection (empty array = unfiltered); toggling
  // one faction adds/removes just that id, so several can be checked at once —
  // same contract as builderToggleFactionFilter() in designs-builder.js.
  function toggleNpcFactionFilter(id) {
    if (id === 'all') {
      npcFactionFilter = [];
    } else {
      const i = npcFactionFilter.indexOf(id);
      if (i >= 0) npcFactionFilter.splice(i, 1); else npcFactionFilter.push(id);
    }
    renderNpcStationsTable();   // npcFactionDDOpen stays true, so the menu re-renders open
  }
  function toggleNpcFactionDropdown(e) {
    if (e) e.stopPropagation();   // don't let the outside-click handler below close it
    npcFactionDDOpen = !npcFactionDDOpen;
    document.getElementById('npc-faction-menu')?.classList.toggle('open', npcFactionDDOpen);
  }
  function closeNpcFactionDropdown() {
    npcFactionDDOpen = false;
    document.getElementById('npc-faction-menu')?.classList.remove('open');
  }
  document.addEventListener('click', (e) => {
    if (!e.target.closest('#npc-faction-dd')) closeNpcFactionDropdown();
  });

  // Faction filter dropdown — built from whatever owner factions actually
  // appear among the trade partners (not just the currently filtered rows),
  // so picking one faction doesn't make the others disappear from the list.
  // Under the Tradable toggle, Hostile owners drop out of the source list
  // entirely (same rep_tier check the row filter uses) rather than just
  // being unselectable, so the dropdown never offers a faction with zero
  // reachable stations.
  function npcFactionFilterDD() {
    const source = npcTradableOnly
      ? allNpcTradePartners.filter(s => s.rep_tier !== 'Hostile')
      : allNpcTradePartners;
    const factions = [...new Map(source.map(s => [s.owner_id, s.owner_name])).entries()]
      .sort((a, b) => npcOwnerLabel(a[1]).localeCompare(npcOwnerLabel(b[1])));
    if (!factions.length) return '';

    // Drop any selected faction that just fell out of the list (e.g. a
    // Hostile-only faction when Tradable was just switched on) so the
    // trigger never shows a stale badge for a faction no longer offered.
    npcFactionFilter = npcFactionFilter.filter(id => factions.some(([fid]) => fid === id));

    const selected = npcFactionFilter;
    const triggerInner = selected.length === 0
      ? 'Factions'
      : factions.filter(([id]) => selected.includes(id)).map(([id, name]) => npcFactionBadge(id, name, true)).join('');

    // Real factions show just the coloured badge (it already carries the
    // name); "all" has no badge to stand in for it, so it keeps a text label.
    const rows = [['all', '']].concat(factions).map(([id, name]) => {
      const isSel = id === 'all' ? selected.length === 0 : selected.includes(id);
      const badge = id === 'all' ? 'All' : npcFactionBadge(id, name);
      return `<div class="beqf-item ${isSel ? 'sel' : ''}" onclick="toggleNpcFactionFilter('${id}')">
        <span class="beqf-check ${isSel ? 'sel' : ''}"></span>${badge}
      </div>`;
    }).join('');

    return `<div class="beqf-dd" id="npc-faction-dd">
      <div class="beqf-trigger" onclick="toggleNpcFactionDropdown(event)">${triggerInner}<i class="ti ti-chevron-down"></i></div>
      <div class="beqf-menu ${npcFactionDDOpen ? 'open' : ''}" id="npc-faction-menu">${rows}</div>
    </div>`;
  }

  // Fill bar + label reflect the current [min, max] window; called every
  // render so they can never drift out of sync with the filter itself.
  function updateNpcRangeDisplay() {
    document.getElementById('npc-range-out').textContent = npcRangeMin === npcRangeMax
      ? `${npcRangeMin} jump${npcRangeMin === 1 ? '' : 's'}`
      : `${npcRangeMin}–${npcRangeMax} jumps`;
    const fill = document.getElementById('npc-range-fill');
    fill.style.left  = (npcRangeMin / NPC_RANGE_MAX * 100) + '%';
    fill.style.width = ((npcRangeMax - npcRangeMin) / NPC_RANGE_MAX * 100) + '%';

    // When the window collapses to a point, both thumbs sit on the same pixel
    // and the one later in the DOM (max) always wins hit-testing, trapping
    // min underneath with no way to grab it. Give whichever thumb needs room
    // to move *away* from that point the higher z-index: below the window's
    // midpoint that's max (room to its right), above it that's min (room to
    // its left) — so there's always a way to pull the two apart again.
    const nearLowEnd = (npcRangeMin + npcRangeMax) <= NPC_RANGE_MAX;
    document.getElementById('npc-range-min').style.zIndex = nearLowEnd ? 1 : 2;
    document.getElementById('npc-range-max').style.zIndex = nearLowEnd ? 2 : 1;
  }

  // Keyword match against the resolved display string rather than a fixed enum —
  // station_type covers hundreds of specific factory names (e.g. "Advanced
  // Electronics Factory"), not a short list of categories.
  const NPC_TYPE_ICONS = [
    [/wharf/i,                       'ti-anchor'],
    [/shipyard/i,                    'ti-building-factory-2'],
    [/trading/i,                     'ti-building-store'],
    [/mine/i,                        'ti-mountain'],
    [/refinery|factory|production/i, 'ti-building-factory'],
  ];
  function npcStationIcon(type) {
    const hit = NPC_TYPE_ICONS.find(([re]) => re.test(type || ''));
    return hit ? hit[1] : 'ti-building';
  }

  function renderNpcStations(data) {
    allNpcTradePartners = data.npc_trade_partners || [];
    npcStationTrades     = data.station_trades || [];
    renderNpcStationsTable();
  }

  function npcStationRow(s) {
    return `
      <tr class="npc-station-row" data-object-id="${s.object_id}">
        <td><div>${s.name}</div><div class="npc-station-code">${s.code}</div></td>
        <td>${npcOwnerBadge(s)} ${tierBadge(s.rep_tier)}</td>
        <td>
          <span class="sector-link" data-sector-macro="${s.sector_macro}">
            <i class="ti ti-map-pin" style="font-size:12px;vertical-align:-2px;margin-right:4px;color:var(--text-brand)"></i>${s.sector}
          </span>
          <div class="npc-jumps">${s.jumps} jump${s.jumps === 1 ? '' : 's'}</div>
        </td>
        <td><i class="ti ${npcStationIcon(s.station_type)}" style="font-size:13px;vertical-align:-2px;margin-right:5px;color:var(--text-brand)"></i>${s.station_type}</td>
      </tr>`;
  }

  function renderNpcStationsTable() {
    updateNpcRangeDisplay();
    document.getElementById('npc-faction-dd-slot').innerHTML = npcFactionFilterDD();

    // "Tradable" excludes Hostile owners on top of the export's own cutoff
    // (npc_trade_partners never includes At War in the first place — see
    // NPC_TRADE_RANGE_MAX_JUMPS / _npc_trade_partners() in jsonexport.py).
    npcSortedRows = allNpcTradePartners.filter(s =>
      s.jumps >= npcRangeMin && s.jumps <= npcRangeMax &&
      (!npcTradableOnly || s.rep_tier !== 'Hostile') &&
      (npcFactionFilter.length === 0 || npcFactionFilter.includes(s.owner_id)));

    document.getElementById('npc-range-count').textContent =
      `${npcSortedRows.length} of ${allNpcTradePartners.length} stations match these filters`;

    npcSortedRows.sort((a, b) => {
      const av = npcStationSortValue(a, npcStationSortKey);
      const bv = npcStationSortValue(b, npcStationSortKey);
      if (av < bv) return -1 * npcStationSortDir;
      if (av > bv) return  1 * npcStationSortDir;
      return 0;
    });

    // While the inline Station Inspector has replaced the list, filter changes
    // must not resurface the table (or the empty state) underneath it — the
    // count label above still tracks live, and closeNpcStationInspector()
    // re-runs this render once the inspector is gone.
    const inspecting = npcInspectorOpen();
    document.getElementById('npc-stations-panel').style.display = (npcSortedRows.length && !inspecting) ? '' : 'none';
    document.getElementById('npc-stations-empty').style.display = (npcSortedRows.length || inspecting) ? 'none' : 'flex';

    // The filtered/sorted set just changed shape, so any previous scroll
    // position no longer lines up with anything — start the window fresh.
    document.getElementById('npc-stations-panel').scrollTop = 0;
    renderNpcStationsVisibleRows();

    updateSortHeaders('#npc-stations-table', npcStationSortKey, npcStationSortDir);
  }

  // Builds DOM only for the slice of npcSortedRows near the panel's current
  // scroll position, plus two zero-content spacer rows that hold the
  // scrollbar at the correct total height for the rows that aren't in the
  // DOM. Called on every scroll tick (rAF-throttled below) as well as after
  // renderNpcStationsTable() rebuilds npcSortedRows.
  function renderNpcStationsVisibleRows() {
    const panel = document.getElementById('npc-stations-panel');
    const tbody = document.getElementById('npc-stations-rows');
    const total = npcSortedRows.length;
    if (total === 0) { tbody.innerHTML = ''; return; }

    if (!npcRowHeight) {
      // No measured row height yet — render a small first slice, measure a
      // real (non-spacer) row's rendered height from it, then fall through
      // to the normal windowed render below using that real number.
      tbody.innerHTML = npcSortedRows.slice(0, 40).map(npcStationRow).join('');
      const sample  = tbody.querySelector('tr');
      const measured = sample ? sample.getBoundingClientRect().height : 0;
      // This can run while the tab is still display:none (e.g. right after
      // startup, before the user has switched here) — a hidden element's
      // rect is always 0, which isn't a real height. Leave npcRowHeight unset
      // so the next visible render measures for real, instead of caching a
      // bogus 0 that would divide-by-zero the math below forever.
      if (measured > 0) npcRowHeight = measured;
    }
    const rowHeight = npcRowHeight || 40; // keeps this pass's math finite even before a real measurement lands

    // thead isn't sticky — it scrolls with the rows, so it occupies part of
    // scrollTop before any row does.
    const theadHeight = panel.querySelector('thead')?.getBoundingClientRect().height || 0;
    const viewTop     = Math.max(0, panel.scrollTop - theadHeight);
    const viewHeight  = panel.clientHeight;

    const start = Math.max(0, Math.floor(viewTop / rowHeight) - NPC_ROW_BUFFER);
    const end   = Math.min(total, Math.ceil((viewTop + viewHeight) / rowHeight) + NPC_ROW_BUFFER);

    const spacer = h => h > 0 ? `<tr style="height:${h}px"><td colspan="4" style="padding:0;border:0"></td></tr>` : '';
    tbody.innerHTML = spacer(start * rowHeight)
      + npcSortedRows.slice(start, end).map(npcStationRow).join('')
      + spacer((total - end) * rowHeight);
  }

  // rAF-throttled so a fast scroll doesn't queue a windowing pass per pixel —
  // only the latest position by the next paint actually re-renders.
  document.getElementById('npc-stations-panel').addEventListener('scroll', () => {
    if (npcScrollQueued) return;
    npcScrollQueued = true;
    requestAnimationFrame(() => { npcScrollQueued = false; renderNpcStationsVisibleRows(); });
  });

  // Sector cell navigation — same delegated-click pattern as fleet.js's
  // .sector-link handling, scoped to this table only. Checked first so the
  // sector link's own jump-to-sector action takes priority over the row's
  // open-inspector action beneath it.
  document.getElementById('npc-stations-table').addEventListener('click', function(e) {
    const link = e.target.closest('.sector-link');
    if (link) { goToSector(link.dataset.sectorMacro); return; }
    const row = e.target.closest('tr[data-object-id]');
    if (row) openNpcStationInspector(npcSortedRows.find(s => s.object_id === row.dataset.objectId));
  });
