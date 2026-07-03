  // Core role: Inline Station Inspector on Stations -> NPC — swaps in place of the table on row click.

  // Neutral pill, same shell as tierBadge()'s ".badge" but with no tier
  // colour of its own — station_type isn't a diplomatic state, so it borrows
  // the same icon set npcStationIcon() already resolves for the table row.
  function npcTypeBadge(type) {
    return `<span class="badge neutral">
      <i class="ti ${npcStationIcon(type)}" style="font-size:1.1rem;vertical-align:-2px;margin-right:5px;color:var(--text-brand)"></i>${type || '—'}
    </span>`;
  }

  // Direction is from the STATION's own point of view (matches the save
  // file's buyer=/seller= attributes): is_selling means the station has this
  // ware in stock for the player to buy, is_buying means the station wants
  // to buy it from the player. Pirate/black-market bases (Format A in the
  // save) carry no direction at all, so both flags are false and the arrow
  // slot renders empty — same "no claim either way" case as before this
  // feature existed, just without the text tag.
  //
  // ▲/▼ rather than the old trailing "Selling"/"Buying" text: same
  // colour-and-arrow convention as the trade log's Sold/Bought tooltip
  // (tradeLogTipHtml in economy-logs.js — CHART_ACCENT/▲ for a sale,
  // CHART_LOSS/▼ for a purchase), and a fixed-width glyph at the *start* of
  // the line scans faster down a long ware list than text buried after a
  // name of varying length. A ware can be both at once (station trades it
  // both ways), so both arrows can show together.
  function npcWareArrows(ware) {
    const up   = ware.is_selling ? `<span style="color:${CHART_ACCENT}">▲</span>` : '';
    const down = ware.is_buying  ? `<span style="color:${CHART_LOSS}">▼</span>`   : '';
    return `<span class="npc-insp-ware-arrows">${up}${down}</span>`;
  }

  // Same coloured-name treatment as economy-logs.js's ware column — WARE_COLOURS
  // is keyed by display name (npc_station_wares.ware_name is already resolved
  // at scan time, see db/write.py's _ware_name()), CHART_LINE is the fallback
  // for any ware the palette hasn't catalogued yet. Plain text line, no chip
  // background — the colour alone is the identity cue here.
  function npcWareLine(ware) {
    const price   = ware.price ? `<span class="npc-insp-ware-price mono">${Math.round(ware.price).toLocaleString()} Cr</span>` : '';
    const illegal = ware.illegal ? '<span class="npc-insp-ware-illegal">Black market</span>' : '';
    return `<div style="color:${WARE_COLOURS[ware.ware_name] || CHART_LINE}">${npcWareArrows(ware)}${ware.ware_name}${illegal}${price}</div>`;
  }

  // All/Buy/Sell filter for the Wares section — same pill-track visual as
  // the player Economy Logs' direction switch (_dirPillHtml in
  // economy-logs.js: dark inset track, colour-coded thumb sliding behind the
  // active label), laid out horizontally instead of vertically since this
  // sits inline in the section's own header row rather than pinned beside a
  // box that has spare margin to its left.
  //
  // Resets to 'all' on every open rather than remembering a choice per
  // station the way economy logs does per player station — economy logs'
  // per-station memory exists because a user pages between several open
  // player-station panels at once; here only one NPC station is ever visible
  // at a time behind a full inspector swap, so there's nothing to preserve
  // a choice *for* once it closes.
  let npcInspWares      = [];   // full unfiltered list for whichever station is currently open
  let npcInspWareFilter = 'all';

  const NPC_WARE_DIR_MODES = {
    all:  { label: 'All',  color: CHART_LINE },
    buy:  { label: 'Buy',  color: CHART_LOSS },
    sell: { label: 'Sell', color: CHART_ACCENT },
  };

  function npcWareDirPillHtml() {
    const keys = Object.keys(NPC_WARE_DIR_MODES);
    const colW = 4.4, pillW = colW * keys.length; // rem
    const activeLeft  = keys.indexOf(npcInspWareFilter) * colW;
    const activeColor = NPC_WARE_DIR_MODES[npcInspWareFilter].color;
    return `
      <div style="position:relative;width:${pillW}rem;height:2rem;flex-shrink:0;
          display:grid;grid-template-columns:repeat(${keys.length}, 1fr);
          background:rgba(4,12,20,0.88);border:1px solid rgba(0,0,0,0.70);border-radius:var(--radius-sm);
          overflow:hidden;user-select:none;
          box-shadow:inset 0 2px 7px rgba(0,0,0,0.70),inset 0 1px 3px rgba(0,0,0,0.50),0 1px 0 rgba(255,255,255,0.07)">
        <div style="position:absolute;top:1px;bottom:1px;left:${activeLeft}rem;width:${colW}rem;
            background:linear-gradient(170deg, ${activeColor}, ${activeColor}cc);border-radius:1px;pointer-events:none;
            box-shadow:0 3px 9px rgba(0,0,0,0.70),inset 0 1px 0 rgba(255,255,255,0.40),inset 0 -1px 0 rgba(0,0,0,0.24)"></div>
        ${keys.map(k => `
        <span onclick="setNpcWareFilter('${k}')" style="position:relative;z-index:1;cursor:pointer;
            display:flex;align-items:center;justify-content:center;
            font-family:var(--font-data);font-size:1rem;letter-spacing:0.08em;text-transform:uppercase;
            color:${npcInspWareFilter === k ? '#051210' : 'var(--text-brand)'};font-weight:${npcInspWareFilter === k ? '700' : '400'}">${NPC_WARE_DIR_MODES[k].label}</span>`).join('')}
      </div>`;
  }

  function renderNpcInspWares() {
    const wares = npcInspWareFilter === 'all' ? npcInspWares
      : npcInspWares.filter(w => npcInspWareFilter === 'buy' ? w.is_buying : w.is_selling);
    document.getElementById('npc-insp-wares').innerHTML = wares.length
      ? wares.map(npcWareLine).join('')
      : `<div class="npc-insp-placeholder">${npcInspWares.length ? 'No wares match this filter.' : 'No wares traded.'}</div>`;
  }

  function setNpcWareFilter(dir) {
    npcInspWareFilter = dir;
    document.getElementById('npc-insp-ware-pill').innerHTML = npcWareDirPillHtml();
    renderNpcInspWares();
  }

  // trade_history.direction is relative to the PLAYER station on the row
  // (station_code/station_name), not this NPC station — 'Out' means the
  // player sold (so this counterparty bought), 'In' means the player bought
  // (so this counterparty sold). Same colour convention as economy-logs.js's
  // Buy/Sell pill (CHART_LOSS/CHART_ACCENT).
  function npcTradeRow(t) {
    const isSell     = t.direction === 'Out';
    const dirColour  = isSell ? CHART_ACCENT : CHART_LOSS;
    const dirLabel   = isSell ? 'Sold' : 'Bought';
    const wareColour = WARE_COLOURS[t.ware_name] || CHART_LINE;
    const ship       = t.ship_name || t.ship_code || '—';
    const shipHtml   = t.ship_code
      ? `<span class="ship-link" onclick="jumpToShip('${t.ship_code}','${t.ship_owner_id || 'player'}')">${ship}</span>`
      : ship;
    return `<tr>
      <td class="mono">${_tradeLogAgo(t.time_ago_s)}</td>
      <td style="color:${dirColour}">${dirLabel}</td>
      <td style="color:${wareColour}">${t.ware_name}</td>
      <td class="mono">${Math.round(t.amount).toLocaleString()}</td>
      <td>${shipHtml}</td>
      <td>${t.station_name || t.station_code || '—'}</td>
    </tr>`;
  }

  // Open/closed is read straight off the panel's display style rather than a
  // shared flag — renderNpcStationsTable() (npc-stations.js) also needs the
  // answer, and the DOM is the one place both files already agree on.
  function npcInspectorOpen() {
    return document.getElementById('npc-station-inspector').style.display !== 'none';
  }

  // Where the user was in the list when they clicked a row. Captured here
  // because a display:none panel drops its scroll state — by close time the
  // browser has already forgotten it, and coming back at the top of a
  // 1000-row list after inspecting one station would lose the user's place.
  let npcInspReturnScroll = 0;

  // s is one row from allNpcTradePartners/npcSortedRows (npc-stations.js) —
  // same shape already used to build the table row, so no separate fetch.
  function openNpcStationInspector(s) {
    if (!s) return;

    document.getElementById('npc-insp-icon').className = `ti ${npcStationIcon(s.station_type)}`;
    document.getElementById('npc-insp-name').textContent = s.name;
    document.getElementById('npc-insp-code').textContent = s.code;

    document.getElementById('npc-insp-badges').innerHTML =
      npcOwnerBadge(s) + tierBadge(s.rep_tier) + npcTypeBadge(s.station_type);

    const sectorEl = document.getElementById('npc-insp-sector');
    sectorEl.dataset.sectorMacro = s.sector_macro;
    sectorEl.innerHTML = `<i class="ti ti-map-pin" style="font-size:12px;vertical-align:-2px;margin-right:4px;color:var(--text-brand)"></i>${s.sector}`;
    document.getElementById('npc-insp-jumps').textContent = `${s.jumps} jump${s.jumps === 1 ? '' : 's'}`;

    npcInspWares      = s.wares || [];
    npcInspWareFilter = 'all';
    document.getElementById('npc-insp-ware-pill').innerHTML = npcWareDirPillHtml();
    renderNpcInspWares();

    // Most-recent-first, same ordering _tradeLogHtml() uses in economy-logs.js.
    const trades = npcStationTrades
      .filter(t => t.counterparty_id === s.object_id)
      .sort((a, b) => a.time_ago_s - b.time_ago_s);
    document.getElementById('npc-insp-trades-rows').innerHTML = trades.length
      ? trades.map(npcTradeRow).join('')
      : '<tr><td colspan="6" class="npc-insp-placeholder">No trades logged.</td></tr>';

    // Swap in place of the table panel — the tab's header and filter controls
    // above stay put, same trick as reslibShowHullInspector() in the Resource
    // Library. The empty state is hidden too (not just the table) so a filter
    // combination with zero matches can't stack it under the inspector.
    npcInspReturnScroll = document.getElementById('npc-stations-panel').scrollTop;
    document.getElementById('npc-stations-panel').style.display = 'none';
    document.getElementById('npc-stations-empty').style.display = 'none';
    document.getElementById('npc-station-inspector').style.display = '';
    document.getElementById('npc-station-inspector').scrollTop = 0;
  }

  function closeNpcStationInspector() {
    document.getElementById('npc-station-inspector').style.display = 'none';
    // The filter controls stay live while the inspector is open, so the list
    // is restored by a full re-render against their *current* values, not by
    // just flipping display back — the rows may have changed shape meanwhile.
    renderNpcStationsTable();
    // After the render's own scroll-to-top: put the user back where they were.
    // If filters changed meanwhile the browser clamps the value, so a shorter
    // list degrades to "near the end" rather than erroring. The panel's
    // scroll listener re-windows the virtualized rows for the new position.
    document.getElementById('npc-stations-panel').scrollTop = npcInspReturnScroll;
  }

  // The back link, the Location sector-link, and a trade row's ship-link all
  // share this one listener: back closes the inspector outright; the other
  // two navigate away (sector map / fleet), so the inspector closes first —
  // otherwise returning to this tab later would land on a stale station.
  // ship-link's own onclick="jumpToShip(...)" already ran by the time this
  // bubbles up here.
  document.getElementById('npc-station-inspector').addEventListener('click', function(e) {
    if (e.target.closest('.npc-insp-back')) { closeNpcStationInspector(); return; }
    const link = e.target.closest('.sector-link');
    if (link) { closeNpcStationInspector(); goToSector(link.dataset.sectorMacro); return; }
    if (e.target.closest('.ship-link')) closeNpcStationInspector();
  });

  // Guarded so Escape does nothing when the inspector isn't up —
  // closeNpcStationInspector() now triggers a full table re-render, which
  // there's no reason to pay for on every stray Escape press elsewhere.
  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape' && npcInspectorOpen()) closeNpcStationInspector();
  });
