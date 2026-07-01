  // Core role: Opens/closes the NPC Station Inspector popup (Stations -> NPC row click-through).

  // Neutral pill, same shell as tierBadge()'s ".badge" but with no tier
  // colour of its own — station_type isn't a diplomatic state, so it borrows
  // the same icon set npcStationIcon() already resolves for the table row.
  function npcTypeBadge(type) {
    return `<span class="badge neutral">
      <i class="ti ${npcStationIcon(type)}" style="font-size:1.1rem;vertical-align:-2px;margin-right:5px;color:var(--text-brand)"></i>${type || '—'}
    </span>`;
  }

  // Same coloured-name treatment as economy-logs.js's ware column — WARE_COLOURS
  // is keyed by display name (npc_station_wares.ware_name is already resolved
  // at scan time, see db/write.py's _ware_name()), CHART_LINE is the fallback
  // for any ware the palette hasn't catalogued yet. Plain text line, no chip
  // background — the colour alone is the identity cue here.
  //
  // Direction is from the STATION's own point of view (matches the save
  // file's buyer=/seller= attributes): "Selling" means the station has this
  // ware in stock for the player to buy, "Buying" means the station wants
  // to buy it from the player. Pirate/black-market bases (Format A in the
  // save) carry no direction at all, so both flags are false and the ware
  // renders as a plain undirected line, same as before this feature existed.
  function npcWareLine(ware) {
    const tags = [];
    if (ware.is_selling) tags.push(`<span style="color:${CHART_ACCENT}">Selling</span>`);
    if (ware.is_buying)  tags.push(`<span style="color:${CHART_LOSS}">Buying</span>`);
    const dir     = tags.length ? ` <span class="npc-insp-ware-dir">${tags.join(' ')}</span>` : '';
    const price   = ware.price ? `<span class="npc-insp-ware-price mono">${Math.round(ware.price).toLocaleString()} Cr</span>` : '';
    const illegal = ware.illegal ? '<span class="npc-insp-ware-illegal">Black market</span>' : '';
    return `<div style="color:${WARE_COLOURS[ware.ware_name] || CHART_LINE}">${ware.ware_name}${dir}${illegal}${price}</div>`;
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

    document.getElementById('npc-insp-wares').innerHTML = s.wares && s.wares.length
      ? s.wares.map(npcWareLine).join('')
      : '<div class="npc-insp-placeholder">No wares traded.</div>';

    // Most-recent-first, same ordering _tradeLogHtml() uses in economy-logs.js.
    const trades = npcStationTrades
      .filter(t => t.counterparty_id === s.object_id)
      .sort((a, b) => a.time_ago_s - b.time_ago_s);
    document.getElementById('npc-insp-trades-rows').innerHTML = trades.length
      ? trades.map(npcTradeRow).join('')
      : '<tr><td colspan="6" class="npc-insp-placeholder">No trades logged.</td></tr>';

    document.getElementById('npc-inspector-overlay').style.display = 'flex';
  }

  function closeNpcStationInspector() {
    document.getElementById('npc-inspector-overlay').style.display = 'none';
  }

  // Backdrop click, the Location sector-link, and a trade row's ship-link
  // all share this one listener: backdrop closes the popup outright; the
  // other two navigate away (sector map / fleet), so the popup closes first
  // rather than sitting open over a now-unrelated tab. ship-link's own
  // onclick="jumpToShip(...)" already ran by the time this bubbles up here.
  document.getElementById('npc-inspector-overlay').addEventListener('click', function(e) {
    if (e.target === this) { closeNpcStationInspector(); return; }
    const link = e.target.closest('.sector-link');
    if (link) { closeNpcStationInspector(); goToSector(link.dataset.sectorMacro); return; }
    if (e.target.closest('.ship-link')) closeNpcStationInspector();
  });

  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') closeNpcStationInspector();
  });
