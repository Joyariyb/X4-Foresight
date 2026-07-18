  // Core role: Ingests scanner JSON export, adapts field names to UI conventions, and populates all tab data models.

  function populate(data) {
    // Rendering code reads the export's own field names (ship_order,
    // hull_origin_name, hull_max, owner_id, …) directly. What populate() adds
    // IN PLACE is only *derived* data the export doesn't carry: resolved
    // sector names, nested crew skills, and the ship→pilot join.

    // Equipment/hull catalog (Designs tab + Resource Library) is loaded
    // independently by scan-loader.js's loadResourceLibrary() — it's static,
    // not derived from the save, so scan payloads no longer carry it.

    // Keep the picker button label in sync whenever a scan loads.
    if (data.meta && data.meta.scan_id != null) {
      _currentScanId = data.meta.scan_id;
      const label = document.getElementById('scan-picker-label');
      if (label) label.textContent = _currentScanId;
    }

    const player = data.player || {};

    // sector_macro → readable name (ships/crew only carry the macro).
    const sectorName = {};
    (data.sectors || []).forEach(s => { sectorName[s.sector_macro] = s.sector_name; });
    const resolveSector = s => sectorName[s.sector_macro] || s.sector_name || s.sector_macro || null;

    // Nest flat skill_* fields; index by object_id for ship→pilot joins
    const crew = data.crew || [];
    const crewById = {};
    crew.forEach(c => {
      crewById[c.object_id] = c;
      c.skills = {
        piloting:    c.skill_piloting,
        management:  c.skill_management,
        engineering: c.skill_engineering,
        morale:      c.skill_morale,
        boarding:    c.skill_boarding,
      };
      // assigned_type is "ship"/"station"; the asset code is shown separately.
      c.assigned_to = c.assigned_type
        ? c.assigned_type.charAt(0).toUpperCase() + c.assigned_type.slice(1)
        : null;
      c.sector = resolveSector(c);
    });

    const normShip = s => {
      s.sector = resolveSector(s);
    };

    const playerShips = data.ships || [];

    // Courier deliveries in flight, indexed for the two render sites: the
    // loading station's trade-log panel (deliveriesByStation, keyed by station
    // display code, read from economy-logs.js) and the courier's own fleet row
    // (s.delivery, read from fleet.js).
    const allDeliveries = data.in_progress_deliveries || [];
    deliveriesByStation = {};
    const deliveryByShip = {};
    allDeliveries.forEach(d => {
      (deliveriesByStation[d.from_station_code] =
        deliveriesByStation[d.from_station_code] || []).push(d);
      if (d.ship_id) deliveryByShip[d.ship_id] = d;
    });

    playerShips.forEach(s => {
      normShip(s);
      const p = s.pilot_id ? crewById[s.pilot_id] : null;
      s.pilot = p ? { name: p.name, skills: p.skills } : null;
      s.delivery = deliveryByShip[s.object_id] || null;
    });

    const npcList = data.npc_ships || [];
    npcList.forEach(normShip);

    // Stations only need the resolved sector name here; the deeper economy /
    // storage / production fields are a separate wiring pass (the card handles
    // their absence gracefully — empty panels, not errors).
    (data.stations || []).forEach(s => { s.sector = resolveSector(s); });
    (data.npc_trade_partners || []).forEach(s => { s.sector = resolveSector(s); });

    // Resolve each crew member's assigned asset to its display name — assigned_to
    // only carries the kind ("Ship"/"Station"), and assigned_code is a bare code.
    // Ships prefer their catalogued display_name (same string the Fleet table
    // shows), then a custom name; stations use their custom name. Left null when
    // the asset isn't in the current data so the card falls back to the code.
    const assetNameByCode = {};
    playerShips.forEach(s => { if (s.code) assetNameByCode[s.code] = s.display_name || s.name || null; });
    (data.stations || []).forEach(s => { if (s.code) assetNameByCode[s.code] = s.name || null; });
    crew.forEach(c => { c.assigned_name = c.assigned_code ? (assetNameByCode[c.assigned_code] || null) : null; });

    // Re-assemble the { fleet_summary, player_ships, npc_ships } object the
    // rest of populate() reads as `ships`.
    const ships    = { fleet_summary: data.fleet_summary || {},
                       player_ships:  playerShips,
                       npc_ships:     npcList };
    const fleet    = ships.fleet_summary;
    const players  = ships.player_ships;
    const stations  = data.stations       || [];
    const rep       = data.reputation     || [];
    const allTrades = data.station_trades   || [];
    const allMining = data.mining_deliveries || [];
    warePrices      = data.ware_prices    || {};

    // Captains Log data — the feed renders on tab open (and re-renders here in
    // case the Events tab is the one currently visible during a re-scan).
    // The entity arrays let the feed resolve an event's component= link to the
    // ship/station it points at (their .sector is already resolved above);
    // rep lets it show a faction's CURRENT standing next to a past rep event;
    // sectors is the full discovered-galaxy list, used to validate a sector
    // name parsed out of event prose (see events-feed.js's _extractSector).
    EventsFeed.setData(data.events, data.player_stats,
                       { ships: playerShips, stations, npcShips: npcList, rep,
                         sectors: data.sectors || [] });
    EventsFeed.render();

    // Station bulletin-board missions — same hand-off pattern as EventsFeed:
    // data in now, the sidebar's Missions item re-renders on open.
    MissionsFeed.setData(data.station_missions);
    MissionsFeed.render();

    // Economic Advisor findings — same hand-off pattern as EventsFeed: data
    // in now, the sidebar's Advisors > Economic item re-renders on open.
    AdvisorsFeed.setData(data.advisors);
    AdvisorsFeed.render();

    document.getElementById("ov-pilot").textContent  = player.name || "—";
    document.getElementById("nav-ships").textContent = fleet.total || "—";

    const waiting  = players.filter(s => s.ship_order === "Waiting");

    // Hostile Presence / Force Build-Up — sourced from the Military advisor
    // findings (db/advisors/military.py) rather than a separate hull-origin
    // check, so the "is this actually a threat" force comparison (theirs vs.
    // the player's, per sector) lives in one place. 'Covered' verdicts mean
    // the player's present force there already wins that fight, so those are
    // excluded — only sectors where the hostiles are at least a threat.
    const militaryFindings = ((data.advisors || {}).findings || [])
      .filter(f => f.domain === "military");
    const hostilePresence = militaryFindings.filter(f =>
      f.type === "hostile_presence" && f.slots.verdict !== "Covered");
    const buildups = militaryFindings.filter(f => f.type === "buildup");
    const compositionGaps = militaryFindings.filter(f => f.type === "composition_gap");
    const outranged = militaryFindings.filter(f => f.type === "outranged");
    const damagedFleet = militaryFindings.filter(f => f.type === "damaged_fleet");

    // Storage Overflow — sourced from the Economic advisor's overflow_risk
    // findings (db/advisors/economy.py's overflow_risk_findings()), same
    // hand-off pattern as the military-sourced alerts above: this is the
    // single source of truth for "a station's about to cap out on a ware",
    // so no separate raw cargo-percentage check belongs here. The advisor's
    // own window (OVERFLOW_HOURS_THRESHOLD, 5h) is "worth mentioning";
    // Alerts narrows further to OVERFLOW_ALERT_HOURS since game hours track
    // real hours 1:1 here and this tab is for "needs attention now".
    const OVERFLOW_ALERT_HOURS = 1;
    const OVERFLOW_ALERT_RED_HOURS = 0.5;
    const storageOverflow = ((data.advisors || {}).findings || [])
      .filter(f => f.domain === "economy" && f.type === "overflow_risk"
        && f.slots.hours <= OVERFLOW_ALERT_HOURS);

    // Stranded Deliveries — sourced from the Trader advisor's stranded_delivery
    // findings (db/advisors/trader.py's stranded_delivery_findings()): a ship
    // has been holding pickup cargo past STRANDED_HOURS_THRESHOLD with no
    // delivery destination assigned. Single source of truth like the other
    // advisor-backed alerts above — no separate raw-order check here.
    const strandedDeliveries = ((data.advisors || {}).findings || [])
      .filter(f => f.domain === "trader" && f.type === "stranded_delivery");

    // Station Damaged / Under Attack — sourced straight from data.stations[]
    // (export/jsonexport.py's _stations(), the stations table's hull/shield_pct
    // columns), not an advisor finding: this is raw scan health data, no
    // trend or force-comparison reasoning behind it. Under Construction is
    // excluded since a new build's hull naturally starts below 100% and
    // that's not damage. Shields collapsed to near-zero (while the station
    // actually has a hull to protect) flags fire happening *right now*,
    // ahead of hull_pct dropping on the next scan.
    const STATION_HULL_RED_PCT = 60;
    const STATION_HULL_AMBER_PCT = 90;
    const STATION_SHIELD_NEAR_ZERO_PCT = 5;
    const damagedStationsRed = [];
    const damagedStationsAmber = [];
    stations.filter(s => s.status !== "Under Construction").forEach(s => {
      const underFire = s.hull_max > 0 && s.shield_pct != null && s.shield_pct <= STATION_SHIELD_NEAR_ZERO_PCT;
      if (underFire || (s.hull_pct != null && s.hull_pct < STATION_HULL_RED_PCT)) {
        damagedStationsRed.push(s);
      } else if (s.hull_pct != null && s.hull_pct < STATION_HULL_AMBER_PCT) {
        damagedStationsAmber.push(s);
      }
    });
    const stationDamageActive = damagedStationsRed.length > 0 || damagedStationsAmber.length > 0;

    const alertCount = (hostilePresence.length > 0 ? 1 : 0)
      + (buildups.length > 0 ? 1 : 0) + (compositionGaps.length > 0 ? 1 : 0)
      + (outranged.length > 0 ? 1 : 0) + (waiting.length > 0 ? 1 : 0)
      + (damagedFleet.length > 0 ? 1 : 0) + (storageOverflow.length > 0 ? 1 : 0)
      + (strandedDeliveries.length > 0 ? 1 : 0) + (stationDamageActive ? 1 : 0);
    document.getElementById("nav-alerts").textContent = alertCount;

    // Hostiles Present — enemy NPC ships sitting in a sector where the player
    // owns a station (npc_ships is already bounded to those sectors at export
    // time, so no extra sector filtering is needed here). "Hostile" mirrors
    // the reputation tiers sectors.js treats as adversarial, not just the
    // locked-hostile races, so an active war with a normally-neutral faction
    // still counts.
    const HOSTILE_REP_TIERS = new Set(["Hostile", "At War"]);
    const repTierByFaction = {};
    rep.forEach(f => { repTierByFaction[f.faction_id] = f.tier; });
    const hostilesPresent = npcList.filter(s => HOSTILE_REP_TIERS.has(repTierByFaction[s.owner_id])).length;

    const playerStats = data.player_stats || {};

    // Summary cards
    const cards = [
      { label:"Credits",         value: fmtCredits(player.credits),         cls:"amber" },
      { label:"Total Ships",     value: fleet.total || "—",                 cls:"" },
      { label:"Stations",        value: stations.length,                    cls:"" },
      { label:"Hostiles Present", value: hostilesPresent,                    cls: hostilesPresent > 0 ? "red" : "green" },
      { label:"Waiting",         value: waiting.length,                     cls: waiting.length > 0 ? "amber" : "" },
      { label:"Trade Rank",      value: playerStats.trade_rank      ?? "—", cls:"" },
      { label:"Trade Score",     value: playerStats.trade_score     ?? "—", cls:"" },
      { label:"Fight Rank",      value: playerStats.fight_rank      ?? "—", cls:"" },
      { label:"Fight Score",     value: playerStats.fight_score     ?? "—", cls:"" },
      { label:"Ships Destroyed", value: playerStats.ships_destroyed ?? "—", cls:"" },
    ];
    document.getElementById("summary-cards").innerHTML = cards.map(c => {
      const icon = CARD_ICONS[c.label] || "ti-info-circle";
      return `<div class="card">
        <div class="card-top"><i class="ti ${icon}"></i><div class="lbl">${c.label}</div></div>
        <div class="val ${c.cls}">${c.value}</div>
      </div>`;
    }).join("");

    // Fleet by role
    const byRole = fleet.by_role || {};
    document.querySelector("#role-table tbody").innerHTML =
      Object.entries(byRole).sort((a,b)=>b[1]-a[1]).map(([role,count]) => {
        const icon = ROLE_ICONS[role] || "ti-rocket";
        return `<tr>
          <td><i class="ti ${icon}" style="font-size:13px;vertical-align:-2px;margin-right:6px;color:var(--text-brand)"></i>${role}</td>
          <td class="mono" style="color:var(--color-primary)">${count}</td>
        </tr>`;
      }).join("");

    // Fleet by order
    const byOrder = fleet.by_order || {};
    document.querySelector("#order-table tbody").innerHTML =
      Object.entries(byOrder).sort((a,b)=>b[1]-a[1]).map(([order,count]) => {
        const col  = ORDER_COLOURS[order] || "var(--text-secondary)";
        const icon = ORDER_ICONS[order]   || "ti-circle";
        return `<tr>
          <td><i class="ti ${icon}" style="font-size:13px;vertical-align:-2px;margin-right:6px;color:${col}"></i>${order}</td>
          <td class="mono" style="color:${col}">${count}</td>
        </tr>`;
      }).join("");

    // Store ships for re-use by setSort(), then do the initial render
    // using the default sort key and direction.
    // Crew data must be loaded before renderFleet so pilot name links can resolve.
    allCrewData = data.crew || [];

    allPlayerShips = players;
    renderFleet(allPlayerShips, currentSortKey, currentSortDir);
    updateFleetSortHeaders();
    document.getElementById('ft-count-player').textContent = players.length;

    const crewCounts = { manager: 0, pilot: 0, service: 0, marine: 0 };
    allCrewData.forEach(c => { if (crewCounts[c.role] !== undefined) crewCounts[c.role]++; });
    document.getElementById('crew-count-all').textContent     = allCrewData.length;
    document.getElementById('crew-count-manager').textContent = crewCounts.manager;
    document.getElementById('crew-count-pilot').textContent   = crewCounts.pilot;
    document.getElementById('crew-count-service').textContent = crewCounts.service;
    document.getElementById('crew-count-marine').textContent  = crewCounts.marine;
    crewRoleFilter = 'all';
    renderCrewRoster();

    // Build NPC faction sub-tabs and panels, sorted by ship count descending.
    const npcShips = ships.npc_ships || [];
    const byFaction = {};
    npcShips.forEach(s => { (byFaction[s.owner_id] = byFaction[s.owner_id] || []).push(s); });
    const sortedFactions = Object.entries(byFaction).sort((a, b) => b[1].length - a[1].length);

    // Supplement the hardcoded tag map with any tags found in the live rep data,
    // so factions added by future DLC are picked up automatically.
    const tagMap  = Object.assign({}, FACTION_LABELS);
    const nameMap = Object.assign({}, FACTION_FULL_NAMES_FALLBACK);
    rep.forEach(f => {
      const m = f.faction_name.match(/^\[(\w+)\]\s*(.+)$/);
      if (m) {
        tagMap[f.faction_id]  = m[1];
        nameMap[f.faction_id] = m[2];
      }
    });

    const subtabs   = document.getElementById('fleet-subtabs');
    const npcPanels = document.getElementById('fleet-npc-panels');

    // Remove any faction tabs from a previous data load, then rebuild.
    subtabs.querySelectorAll('.fleet-subtab:not([data-faction="player"])').forEach(t => t.remove());
    npcPanels.innerHTML = '';

    sortedFactions.forEach(([factionId, fShips]) => {
      const label    = tagMap[factionId]  || factionId.toUpperCase().slice(0, 3);
      const fullName = nameMap[factionId] || label;
      const color    = FACTION_COLOURS[factionId] || '#2dd4bf';

      // Sub-tab
      const tab = document.createElement('div');
      tab.className = 'fleet-subtab';
      tab.dataset.faction = factionId;
      tab.style.setProperty('--tab-color',  color);
      tab.style.setProperty('--tab-bg',     hexToRgba(color, 0.12));
      tab.style.setProperty('--tab-border', hexToRgba(color, 0.3));
      tab.innerHTML = `${label} <span class="ft-count">${fShips.length}</span>`;
      tab.onclick = () => switchFleetTab(factionId, tab);
      subtabs.appendChild(tab);

      // Panel
      const panel = document.createElement('div');
      panel.className = 'fleet-panel';
      panel.id = 'fleet-panel-' + factionId;
      npcSortState[factionId]  = { key: 'role', dir: 1 };
      npcShipsCache[factionId] = fShips;
      // Headers are clickable sorters, same interaction as the player table
      // (the old sort dropdown predates sortable headers and is gone).
      panel.innerHTML = `
        <div class="sec-header">
          <div class="sec-title">${fullName} Ships</div>
          <div class="sec-line"></div>
        </div>
        <div class="panel" style="overflow:auto; max-height: calc(100vh - 200px);">
          <table class="data-table" id="npc-table-${factionId}">
            <thead><tr>
              <th data-sort-key="name"   onclick="setNpcSort('${factionId}','name')">Name / Code</th>
              <th data-sort-key="size"   onclick="setNpcSort('${factionId}','size')">Size</th>
              <th data-sort-key="role"   onclick="setNpcSort('${factionId}','role')">Hull Type</th>
              <th data-sort-key="order"  onclick="setNpcSort('${factionId}','order')">Order</th>
              <th data-sort-key="sector" onclick="setNpcSort('${factionId}','sector')">Sector</th>
            </tr></thead>
            <tbody></tbody>
          </table>
        </div>`;
      npcPanels.appendChild(panel);

      renderNpcFleet(fShips, factionId);
    });

    // Build Diplomacy faction sub-tabs and panels — same pattern as the Naval
    // strip above. Tab order: the player's standing with each subject faction,
    // descending, so allies come first and Xenon anchors the end.
    const relRows = data.faction_relations || [];
    const relByFaction = {};
    relRows.forEach(r => { (relByFaction[r.faction_id] = relByFaction[r.faction_id] || []).push(r); });

    // Player's standing per faction — used for tab ordering and mirrored rows.
    const repByFaction = {};
    rep.forEach(r => { repByFaction[r.faction_id] = r; });

    const diploMenu     = document.getElementById('diplo-dd-menu');
    const diploControls = document.getElementById('diplo-controls');
    const diploPanels   = document.getElementById('diplo-npc-panels');

    // Reset the dropdown list, the injected Matrix button and the panels.
    // (The dropdown trigger and the static Player panel stay in markup.)
    diploMenu.innerHTML = '';
    document.getElementById('diplo-matrix-btn')?.remove();
    diploPanels.innerHTML = '';

    // Build one dropdown entry — a .fleet-subtab so it's visually identical to
    // the old strip button, just stacked in the menu.
    const makeDiploItem = (factionId, label, color, locked) => {
      const item = document.createElement('div');
      item.className = 'fleet-subtab';
      item.dataset.faction = factionId;
      item.style.setProperty('--tab-color',  color);
      item.style.setProperty('--tab-bg',     hexToRgba(color, 0.12));
      item.style.setProperty('--tab-border', hexToRgba(color, 0.3));
      item.innerHTML = locked
        ? `${label} <i class="ti ti-lock" style="font-size:12px" data-text-tip="Standings locked by the game"></i>`
        : label;
      item.onclick = () => switchDiploTab(factionId);
      return item;
    };

    // Player is always the first choice in the list.
    diploMenu.appendChild(makeDiploItem('player', 'Player', '#2dd4bf', false));

    const diploOrder = Object.keys(relByFaction)
      .sort((a, b) => (repByFaction[b]?.value ?? -99) - (repByFaction[a]?.value ?? -99));

    diploOrder.forEach(factionId => {
        const label    = tagMap[factionId]  || factionId.toUpperCase().slice(0, 3);
        const fullName = nameMap[factionId] || label;
        const color    = FACTION_COLOURS[factionId] || '#2dd4bf';
        const locked   = relByFaction[factionId][0].locked === 1;

        // Dropdown entry for this faction.
        diploMenu.appendChild(makeDiploItem(factionId, label, color, locked));

        // Rows arrive pre-sorted value-descending from the export. A few
        // factions store no player pairing on their side of the save —
        // relations are symmetric, so mirror the player's own standing in.
        let rows = relByFaction[factionId];
        if (!rows.some(r => r.other_id === 'player') && repByFaction[factionId]) {
          const pr = repByFaction[factionId];
          rows = [...rows, { other_id: 'player', other_name: 'Player',
                             value: pr.value, tier: pr.tier, mirrored: true }]
            .sort((a, b) => b.value - a.value);
        }

        // Panel — same table shape as the player standings, minus base/booster
        // (NPC boosters are not extracted).
        const lockNote = locked
          ? `<span style="font-size:11px;color:var(--text-brand);margin-left:8px;letter-spacing:0;text-transform:none">
               <i class="ti ti-lock" style="font-size:11px;vertical-align:-1px"></i> standings locked by the game</span>`
          : '';
        const panel = document.createElement('div');
        panel.className = 'diplo-panel';
        panel.id = 'diplo-panel-' + factionId;
        panel.innerHTML = `
          <div class="sec-header">
            <div class="sec-title">${fullName} Standings${lockNote}</div>
            <div class="sec-line"></div>
          </div>
          <div class="panel" style="overflow:auto; max-height: calc(100vh - 200px);">
            <table class="data-table">
              <thead><tr><th>Faction</th><th>Tier</th><th>Score</th><th>Bar</th></tr></thead>
              <tbody>${rows.map(r => {
                const col = { Allied:"var(--color-positive)", Friendly:"var(--color-primary)", Neutral:"var(--text-secondary)", Hostile:"var(--color-warning)", "At War":"var(--color-negative)" }[r.tier] || "var(--text-secondary)";
                const isPlayer = r.other_id === 'player';
                const hint = r.mirrored
                  ? 'Mirrored from your own standings — this faction stores no player entry in the save'
                  : 'How this faction sees you';
                const name = isPlayer
                  ? `<span style="color:#2dd4bf" data-text-tip="${hint}">${player.name || 'Player'} (you)</span>`
                  : r.other_name;
                return `<tr${isPlayer ? ' style="background:rgba(45,212,191,0.07)"' : ''}>
                  <td>${name}</td>
                  <td>${tierBadge(r.tier)}</td>
                  <td class="mono" style="color:${col}">${sign(r.value)}</td>
                  <td>${repBar(r.value)}</td>
                </tr>`;
              }).join('')}</tbody>
            </table>
          </div>`;
        diploPanels.appendChild(panel);
      });

    // Matrix sub-tab — the whole diplomatic web in one grid. Row = how that
    // faction sees each column. Pure presentation: same rows the tabs use,
    // with the symmetric pairing as fallback when only one side is stored.
    if (diploOrder.length) {
      const TIER_COLOURS = { Allied: '#3fb950', Friendly: '#2dd4bf', Neutral: '#8b949e', Hostile: '#d29922', 'At War': '#f85149' };
      const matrixOrder = ['player', ...diploOrder];
      const dmTag  = f => f === 'player' ? 'YOU' : (tagMap[f] || f.toUpperCase().slice(0, 3));
      const dmName = f => f === 'player' ? (player.name || 'Player') : (nameMap[f] || dmTag(f));

      // 'subject|target' → standing row, both stored directions.
      const relLookup = {};
      relRows.forEach(r => { relLookup[r.faction_id + '|' + r.other_id] = r; });
      rep.forEach(r => { relLookup['player|' + r.faction_id] = r; });

      let mhtml = '<table class="diplo-matrix"><thead><tr><th class="dm-row"></th>'
        + matrixOrder.map(f => `<th data-text-tip="${dmName(f)}">${dmTag(f)}</th>`).join('')
        + '</tr></thead><tbody>';
      matrixOrder.forEach(a => {
        mhtml += `<tr><th class="dm-row" data-text-tip="Open the ${dmName(a)} tab"
                      onclick="switchDiploTab('${a}')">${dmTag(a)}</th>`;
        matrixOrder.forEach(b => {
          if (a === b) { mhtml += '<td class="dm-empty"></td>'; return; }
          const r = relLookup[a + '|' + b] || relLookup[b + '|' + a];
          if (!r) { mhtml += '<td class="dm-empty" data-text-tip="No standing recorded in the save">·</td>'; return; }
          const col = TIER_COLOURS[r.tier] || '#8b949e';
          const v   = Math.round(r.value);
          mhtml += `<td style="background:${hexToRgba(col, 0.15)};color:${col}"
                        data-text-tip="${dmName(a)} ↔ ${dmName(b)}: ${sign(r.value)} (${r.tier})">${v > 0 ? '+' + v : v}</td>`;
        });
        mhtml += '</tr>';
      });
      mhtml += '</tbody></table>';

      // Matrix lives beside the dropdown as its own toggle, not in the list.
      const mbtn = document.createElement('div');
      mbtn.className = 'fleet-subtab';
      mbtn.id = 'diplo-matrix-btn';
      mbtn.dataset.faction = 'matrix';
      mbtn.style.setProperty('--tab-color',  '#8b949e');
      mbtn.style.setProperty('--tab-bg',     'rgba(139,148,158,0.10)');
      mbtn.style.setProperty('--tab-border', 'rgba(139,148,158,0.3)');
      mbtn.innerHTML = '<i class="ti ti-grid-dots" style="font-size:13px;vertical-align:-2px;margin-right:4px"></i>Matrix';
      mbtn.onclick = () => switchDiploTab('matrix');
      diploControls.appendChild(mbtn);

      const mpanel = document.createElement('div');
      mpanel.className = 'diplo-panel';
      mpanel.id = 'diplo-panel-matrix';
      mpanel.innerHTML = `
        <div class="sec-header">
          <div class="sec-title">Relations Matrix
            <span style="font-size:11px;color:var(--text-secondary);margin-left:8px;letter-spacing:0;text-transform:none">
              row = how that faction sees each column · click a row label to open its tab</span>
          </div>
          <div class="sec-line"></div>
        </div>
        <div class="panel" style="overflow:auto; max-height: calc(100vh - 200px);">${mhtml}</div>`;
      diploPanels.appendChild(mpanel);
    }

    // Land on Player after a rebuild: syncs the trigger label/colour and the
    // active panel (the menu item now exists to copy styling from).
    switchDiploTab('player');

    // Stations
    document.getElementById("stations-grid").innerHTML = stations.map(s => {
      const factionTag = stationFactionTag(s);
      const typeLabel  = stationTypeLabel(s);

      // Hull health
      const hullPct    = s.hull_pct;
      const hullColor  = hullPct == null ? 'var(--text-brand)' : hullPct >= 95 ? 'var(--color-positive)' : hullPct >= 50 ? 'var(--color-warning)' : 'var(--color-negative)';
      const hullPctStr = hullPct != null ? Math.round(hullPct) + '%' : '—';
      const hullBarW   = hullPct != null ? Math.min(hullPct, 100).toFixed(1) : '0';

      // Shield health — scanner doesn't capture station shields yet; shows — until added
      const shieldPct    = s.shield_pct;
      const shieldColor  = shieldPct == null ? 'var(--text-brand)' : shieldPct >= 80 ? '#388bfd' : shieldPct >= 50 ? 'var(--color-warning)' : 'var(--color-negative)';
      const shieldPctStr = shieldPct != null ? Math.round(shieldPct) + '%' : '—';
      const shieldBarW   = shieldPct != null ? Math.min(shieldPct, 100).toFixed(1) : '0';

      // Two-state label colour rule: amber/red values demand attention so the
      // label inherits the same colour as its value — they read as one unit.
      // Any other colour (green, teal, blue) is "healthy/normal" so the label
      // stays muted and only the value carries the colour.
      const attnColor = col =>
        (col === 'var(--color-warning)' || col === 'var(--color-negative)') ? col : 'var(--text-brand)';

      // Shield cell inner HTML — null renders a "NO SHIELDS" label centred in the bar area
      const shieldDisplay = shieldPct == null
        ? `<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.5rem">
             <span style="font-family:var(--font-data);font-size:0.9rem;letter-spacing:0.12em;text-transform:uppercase;color:var(--color-negative)">Shields</span>
           </div>
           <div style="height:2.2rem;background:var(--outline);border-radius:0.2rem;display:flex;align-items:center;justify-content:center">
             <span style="font-family:var(--font-data);font-size:0.9rem;letter-spacing:0.14em;text-transform:uppercase;color:var(--color-negative)">No Shields</span>
           </div>`
        : `<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.5rem">
             <span style="font-family:var(--font-data);font-size:0.9rem;letter-spacing:0.12em;text-transform:uppercase;color:${attnColor(shieldColor)}">Shields</span>
             <span style="font-family:var(--font-data);font-size:1.1rem;color:${shieldColor}">${shieldPctStr}</span>
           </div>
           <div style="height:2.2rem;background:var(--outline);border-radius:0.2rem;overflow:hidden">
             <div style="height:100%;width:${shieldBarW}%;background:${shieldColor};border-radius:0.2rem"></div>
           </div>`;

      // Station status badge
      const statusRaw   = (s.status || '').toLowerCase();
      const statusLabel = statusRaw.includes('construction') ? 'UNDER CONSTRUCTION'
                        : statusRaw.includes('wreck')        ? 'DESTROYED'
                        : 'OPERATIONAL';
      const statusColor = statusRaw.includes('construction') ? 'var(--color-warning)'
                        : statusRaw.includes('wreck')        ? 'var(--color-negative)'
                        : 'var(--color-positive)';

      // Stats
      const dockedShips  = s.docked_ships || [];
      const modCount     = s.module_count != null ? s.module_count : '—';

      // Assigned fleet: ships whose homebase is this station (from export).
      // Distinct from docked ships, which are physically present right now.
      const af        = s.assigned_fleet || {};
      const afTotal   = af.total   || 0;
      const afColor   = afTotal > 0 ? 'var(--color-primary)' : 'var(--text-brand)';
      // Build tooltip rows for each non-zero bucket, falling back to "None assigned".
      const afBuckets = [
        { label: 'Traders', val: af.traders || 0, color: 'var(--color-primary)'   },
        { label: 'Miners',  val: af.miners  || 0, color: 'var(--color-warning)'  },
        { label: 'Combat',  val: af.combat  || 0, color: 'var(--color-negative)'    },
        { label: 'Other',   val: af.other   || 0, color: 'var(--text-secondary)'},
      ];
      const afTipRows = afBuckets
        .filter(b => b.val > 0)
        .map(b => `<div style="display:flex;justify-content:space-between;gap:1.6rem;padding:0.2rem 0">
           <span style="color:${b.color}">${b.label}</span>
           <span style="font-weight:600;color:${b.color}">${b.val}</span>
         </div>`)
        .join('');
      const afTipHtml = afTipRows
        ? `<div style="font-family:var(--font-data);font-size:1.1rem;min-width:11rem">${afTipRows}</div>`
        : `<div style="font-family:var(--font-data);font-size:1.1rem;color:var(--text-brand)">None assigned</div>`;
      const afTipAttr = `data-fleet-tip="${encodeURIComponent(afTipHtml)}"`;

      const storageRaw   = s.cargo_adj_pct;
      const storageStr   = storageRaw != null ? Math.round(storageRaw) + '%' : '—';
      const storageColor = storageRaw != null ? (storageRaw > 90 ? 'var(--color-negative)' : storageRaw > 70 ? 'var(--color-warning)' : 'var(--color-primary)') : 'var(--text-brand)';

      // Build per-type storage breakdown for the hover tooltip.
      // Fixed accent colour per storage category — matches the in-game cargo display.
      // The Total row is computed from the combined values and always shown last.
      //
      // The DB-read export delivers per-type storage as a cargo_by_type list
      // ({cargo_type, m3, max_m3, pct}); we index it by type and emit the three
      // categories in fixed order so the tooltip rows stay stable. (The legacy
      // export carried flat cargo_<type>_* fields instead — reading those here is
      // what silently dropped this tooltip after the switch to the DB export.)
      const cargoByType = {};
      (s.cargo_by_type || []).forEach(c => { cargoByType[c.cargo_type] = c; });
      const allStorageTypes = [
        { label: 'Container', type: 'container', color: 'var(--color-primary)'   },
        { label: 'Solid',     type: 'solid',     color: 'var(--color-warning)'  },
        { label: 'Liquid',    type: 'liquid',    color: 'var(--color-special)' },
      ].map(t => {
        const c = cargoByType[t.type] || {};
        return { label: t.label, color: t.color,
                 pct: c.pct, m3: c.m3 || 0, max: c.max_m3 || 0 };
      });
      const storageTipTypes = allStorageTypes.filter(t => t.max > 0);
      if (storageTipTypes.length > 0) {
        // Sum across all three types so the Total denominator includes every bay,
        // even types that happen to be empty (max > 0 but m3 == 0).
        const totalMax = allStorageTypes.reduce((acc, t) => acc + t.max, 0);
        const totalM3  = allStorageTypes.reduce((acc, t) => acc + t.m3,  0);
        storageTipTypes.push({
          label: 'Total', color: 'var(--color-positive)', isTotal: true,
          pct:   totalMax > 0 ? totalM3 / totalMax * 100 : null,
          m3:    totalM3, max: totalMax,
        });
      }
      // Only attach the tooltip when at least one storage type has data.
      const storageTipAttr = storageTipTypes.length > 0
        ? `data-storage-tip="${encodeURIComponent(JSON.stringify(storageTipTypes.map(t => ({
            label:   t.label,
            pct:     t.pct != null ? Math.round(t.pct) : null,
            m3:      t.m3  != null ? Math.round(t.m3)  : null,
            max:     t.max,
            color:   t.color,
            isTotal: !!t.isTotal,
          }))))}"` : '';

      // Build grouped module breakdown for the hover tooltip.
      // Modules are grouped by category (in display-priority order), then by
      // display_name with duplicates counted, so "Argon Struct × 12" beats
      // listing each one individually.
      const MODULE_CAT_ORDER = ['Production', 'Dock Area', 'Pier', 'Storage', 'Struct'];
      const moduleGroups = {};
      (s.modules || []).forEach(m => {
        const cat  = m.category || 'Other';
        const name = m.display_name || m.macro;
        if (!moduleGroups[cat]) moduleGroups[cat] = {};
        moduleGroups[cat][name] = (moduleGroups[cat][name] || 0) + 1;
      });
      const moduleTipData = [
        ...MODULE_CAT_ORDER.filter(c => moduleGroups[c]),
        ...Object.keys(moduleGroups).filter(c => !MODULE_CAT_ORDER.includes(c)),
      ].map(cat => ({
        category: cat,
        items: Object.entries(moduleGroups[cat]).sort((a, b) => a[0].localeCompare(b[0])),
      }));
      const moduleTipAttr = moduleTipData.length > 0
        ? `data-modules-tip="${encodeURIComponent(JSON.stringify(moduleTipData))}"`
        : '';

      // Stat cell builder — each cell is its own slightly lighter box.
      // Label colour follows the two-state rule via attnColor().
      // tipAttr is an optional extra attribute string e.g. 'data-storage-tip="..."'
      const sc = (lbl, val, col = 'var(--text-primary)', last = false, tipAttr = '', icon = '') =>
        `<div style="padding:1rem 1.2rem;text-align:center;background:var(--surface-2);border-radius:0.3rem${tipAttr ? ';cursor:default' : ''}" ${tipAttr}>
           ${icon ? `<div style="font-size:1.5rem;color:${attnColor(col)};margin-bottom:0.3rem"><i class="ti ${icon}"></i></div>` : ''}
           <div style="font-family:var(--font-data);font-size:0.9rem;letter-spacing:0.1em;text-transform:uppercase;color:${attnColor(col)};margin-bottom:0.5rem">${lbl}</div>
           <div style="font-family:var(--font-data);font-size:2rem;color:${col}">${val}</div>
         </div>`;

      // ── PRODUCTION TAB ─────────────────────────────────────────────────────
      // Each ware row is a 1fr/1fr grid — the same split as the Hull/Shields row
      // above it — so the seam between the two bars runs down the card centre:
      //   Left half  — ware name + STOCKPILE bar: ware's volume_m3 / max_m3 for
      //                its cargo type
      //   Right half — INTERNAL USE bar (how much of the hourly output is consumed
      //                by other production modules at this station) + rate + runtime
      // Rate text shows the hourly production figure from production_rates
      // (module count × PRODUCTION_STATS rate, computed server-side in jsonexport.py).
      const wares = s.production ? s.production.split(',').map(w => w.trim()).filter(Boolean) : [];

      // Lookup: cargo type → total bay capacity in m³ for this station.
      const cargoMaxByType = {};
      (s.cargo_by_type || []).forEach(c => { cargoMaxByType[c.cargo_type] = c.max_m3 || 0; });

      // Pre-computed units/hour per ware from the export (exact, not budget-derived).
      const prodRates = s.production_rates || {};

      // Pre-computed units/hour consumed internally by other modules at this station.
      // E.g. for a station with solar panels + hull parts modules, Energy Cells will
      // have a consumption_rate equal to what the hull parts modules burn per hour.
      const consRates = s.consumption_rates || {};

      // Runtime data keyed by produced-ware display name. Each entry has:
      //   minutes      — float time remaining, or null if no inputs needed
      //   limiting_ware — display name of the bottleneck input, or null
      const runtimes = s.production_runtimes || {};

      // Formats a runtime in minutes to a compact human-readable string.
      const fmtRuntime = mins => {
        if (mins < 60) return Math.round(mins) + 'm';
        const h = Math.floor(mins / 60), m = Math.round(mins % 60);
        return m > 0 ? `${h}h ${m}m` : `${h}h`;
      };

      const prodRows = wares.length === 0
        ? `<div style="padding:1.2rem 1.4rem;font-family:var(--font-data);font-size:1.1rem;color:var(--text-brand)">No production modules</div>`
        : wares.map(w => {
            const wareCol  = WARE_COLOURS[w] || 'var(--text-secondary)';
            // ware_id key matches the inventory dict: "Energy Cells" → "energycells"
            const wareKey  = w.toLowerCase().replace(/\s+/g, '');
            const inv      = (s.inventory || {})[wareKey] || {};
            const volM3    = inv.volume_m3  ?? 0;
            const cargType = inv.cargo_type || 'container';
            const maxM3    = cargoMaxByType[cargType] || 0;
            // Bar 1: how much of this cargo type's total bay the ware currently fills
            const storagePct = maxM3 > 0 ? Math.min(100, volM3 / maxM3 * 100) : 0;
            // Bar 2: what fraction of hourly output is consumed internally
            const prodHr   = prodRates[w] ?? null;
            const consHr   = consRates[w] ?? 0;
            const usagePct = prodHr > 0 ? Math.min(100, consHr / prodHr * 100) : 0;
            const rateLabel = prodHr != null ? Math.round(prodHr).toLocaleString() + '/hr' : '—/hr';

            // Numbers overlaid on the bars: the bar FILL shows the proportion,
            // the text shows the actual quantity (units in stock / units per
            // hour consumed internally). 0/hr rows stay blank — a column of
            // zeros on empty bars is noise, a blank bar already reads as "none".
            const stockLabel = Math.round(inv.amount ?? 0).toLocaleString();
            const consLabel  = consHr > 0 ? Math.round(consHr).toLocaleString() + '/hr' : '';
            // Double shadow punches the text out of the bright fill behind it.
            const barTextStyle = 'position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-family:var(--font-data);font-size:0.9rem;color:var(--text-primary);text-shadow:0 0 3px rgba(2,8,14,0.95),0 0 3px rgba(2,8,14,0.95);pointer-events:none';

            // Runtime label: time until this ware's production stops due to a depleted
            // input. null minutes = no inputs needed (e.g. energy cells) → show nothing.
            const rt = runtimes[w];
            let rtLabel = '', rtColor = 'var(--text-brand)', rtTitle = '';
            if (rt && rt.minutes !== null) {
              rtTitle = rt.limiting_ware ? `Limiting input: ${rt.limiting_ware}` : '';
              if (rt.minutes === 0) {
                rtLabel = 'OUT';
                rtColor = 'var(--color-negative)';
              } else if (rt.minutes < 60) {    // < 1 h → red
                rtLabel = fmtRuntime(rt.minutes);
                rtColor = 'var(--color-negative)';
              } else if (rt.minutes < 120) {   // 1 h – 2 h → amber
                rtLabel = fmtRuntime(rt.minutes);
                rtColor = 'var(--color-warning)';
              } else {
                rtLabel = fmtRuntime(rt.minutes);
                // > 2 h — all the same faint colour, not urgent
              }
            }
            const rtSpan = rtLabel
              ? `<span style="font-family:var(--font-data);font-size:1rem;color:${rtColor};min-width:5.2rem;text-align:right" data-text-tip="${rtTitle}">${rtLabel}</span>`
              : `<span style="min-width:5.2rem"></span>`;

            return `<div style="display:grid;grid-template-columns:1fr 1fr;border-bottom:1px solid var(--outline)">
               <div style="display:flex;align-items:center;gap:0.8rem;padding:0.5rem 1.4rem;border-right:1px solid var(--outline)">
                 <span style="font-family:var(--font-data);font-size:1.1rem;letter-spacing:0.06em;text-transform:uppercase;color:${wareCol};min-width:16rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${w.toUpperCase()}</span>
                 <div style="flex:1;height:1.3rem;background:${wareCol}30;border-radius:0.2rem;overflow:hidden;position:relative" data-text-tip="Stockpile: ${stockLabel} units · ${storagePct.toFixed(1)}% of ${cargType} bay">
                   <div style="height:100%;width:${storagePct.toFixed(1)}%;background:${wareCol};border-radius:0.2rem"></div>
                   <span style="${barTextStyle}">${stockLabel}</span>
                 </div>
               </div>
               <div style="display:flex;align-items:center;gap:0.8rem;padding:0.5rem 1.4rem">
                 <div style="flex:1;height:1.3rem;background:${wareCol}30;border-radius:0.2rem;overflow:hidden;position:relative" data-text-tip="Internal use: ${usagePct.toFixed(1)}% of output consumed internally">
                   <div style="height:100%;width:${usagePct.toFixed(1)}%;background:${wareCol};border-radius:0.2rem"></div>
                   <span style="${barTextStyle}">${consLabel}</span>
                 </div>
                 <span style="font-family:var(--font-data);font-size:1rem;color:var(--text-brand);min-width:5.4rem;text-align:right">${rateLabel}</span>
                 ${rtSpan}
               </div>
             </div>`;
          }).join('');

      // Column titles for the production rows — built with the same grid and
      // flex slots as the rows themselves so each title sits exactly over its
      // column. Only shown when there are rows to label.
      const prodHdrStyle = 'font-family:var(--font-data);font-size:0.9rem;letter-spacing:0.12em;text-transform:uppercase;color:var(--text-brand)';
      const prodHeader = wares.length === 0 ? '' :
        `<div style="display:grid;grid-template-columns:1fr 1fr;border-bottom:1px solid var(--outline);background:var(--surface-1)">
           <div style="display:flex;gap:0.8rem;padding:0.4rem 1.4rem;border-right:1px solid var(--outline)">
             <span style="${prodHdrStyle};min-width:16rem">Ware</span>
             <span style="${prodHdrStyle};flex:1">Stockpile</span>
           </div>
           <div style="display:flex;gap:0.8rem;padding:0.4rem 1.4rem">
             <span style="${prodHdrStyle};flex:1">Internal Use</span>
             <span style="${prodHdrStyle};min-width:5.4rem;text-align:right">Output</span>
             <span style="${prodHdrStyle};min-width:5.2rem;text-align:right">Runtime</span>
           </div>
         </div>`;

      // ── DOCKED SHIPS TAB ───────────────────────────────────────────────────
      const dockedRows = dockedShips.length === 0
        ? `<div style="padding:1.2rem 1.4rem;font-family:var(--font-data);font-size:1.1rem;color:var(--text-brand)">No docked ships</div>`
        : dockedShips.map(ds => {
            // Look up the ship first in the player fleet, then in the full NPC list.
            // This handles both directly-owned ships and civilian-faction ships that
            // are docked here but belong to X4's ambient civilian faction.
            const matchedPlayer = players.find(p => p.code === ds.code);
            const matchedNpc    = !matchedPlayer ? npcShips.find(n => n.code === ds.code) : null;
            const matched       = matchedPlayer || matchedNpc;
            const shipName      = matched ? (matched.name || ds.macro) : ds.macro;
            const cls           = ds.class ? ds.class.replace('ship_', '').toUpperCase() : '?';
            // Determine which fleet subtab to navigate to on click.
            const shipFaction   = matchedNpc ? matchedNpc.owner_id : 'player';
            const clickable     = !!matched && !ds.under_construction;
            return `<div class="${clickable ? 'docked-ship-row' : ''}"
                         style="display:flex;align-items:center;gap:1rem;padding:0.6rem 1.4rem;border-bottom:1px solid var(--outline);${clickable ? 'cursor:pointer' : ''}"
                         ${clickable ? `onclick="jumpToShip('${ds.code}', '${shipFaction}')"` : ''}>
              <span style="font-family:var(--font-data);color:var(--color-highlight);font-size:1.1rem;min-width:6.4rem">${ds.code}</span>
              <span style="font-family:var(--font-data);font-size:1rem;color:var(--text-brand);padding:0.1rem 0.5rem;border:1px solid var(--outline);border-radius:0.2rem">${cls}</span>
              <span class="ship-name" style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${shipName}</span>
              ${ds.under_construction
                ? '<span style="font-family:var(--font-data);font-size:0.9rem;letter-spacing:0.1em;color:var(--color-warning)">CONSTRUCTING</span>'
                : clickable ? '<span style="font-family:var(--font-data);font-size:0.9rem;color:var(--text-brand)">→ Fleet</span>' : ''}
            </div>`;
          }).join('');

      // ── STORAGE TAB ────────────────────────────────────────────────────────
      // adj fields match the game's displayed fill (physical cargo ± trade reservations).
      const fmtM3 = v => v == null ? '—' : v >= 1e6 ? (v/1e6).toFixed(1)+'M' : v >= 1e3 ? (v/1e3).toFixed(1)+'k' : String(Math.round(v));
      const TYPE_COLOR = { container:'var(--color-primary)', solid:'var(--color-warning)', liquid:'var(--color-special)' };
      const TYPE_LABEL = { container:'Container',   solid:'Solid',        liquid:'Liquid'        };

      const hasStorage = ['container','solid','liquid'].some(t => s[`cargo_${t}_adj_pct`] != null) || s.cargo_adj_pct != null;
      let storageRows  = `<div style="padding:1.2rem 1.4rem;font-family:var(--font-data);font-size:1.1rem;color:var(--text-brand)">No storage data</div>`;
      if (hasStorage) {
        const typeRowsHtml = ['container','solid','liquid'].map(t => {
          const pct = s[`cargo_${t}_adj_pct`];
          const m3  = s[`cargo_${t}_adj_m3`];
          const max = s[`cargo_${t}_max`];
          if (pct == null) return '';
          const col = pct > 90 ? 'var(--color-negative)' : TYPE_COLOR[t];
          return `<div style="display:flex;align-items:center;gap:0.8rem;padding:0.5rem 1.4rem;border-bottom:1px solid var(--outline)">
            <span style="font-family:var(--font-data);font-size:1rem;letter-spacing:0.06em;text-transform:uppercase;color:${col};min-width:6.8rem">${TYPE_LABEL[t]}</span>
            <div style="flex:1;height:0.3rem;background:var(--outline);border-radius:0.2rem;overflow:hidden">
              <div style="height:100%;width:${Math.min(pct,100).toFixed(1)}%;background:${col};border-radius:0.2rem"></div>
            </div>
            <span style="font-family:var(--font-data);font-size:1.1rem;color:${col};min-width:3.4rem;text-align:right">${pct.toFixed(0)}%</span>
            <span style="font-family:var(--font-data);font-size:1rem;color:var(--text-brand);white-space:nowrap">${fmtM3(m3)}/${fmtM3(max)} m³</span>
          </div>`;
        }).join('');

        let totalRow = '';
        if (s.cargo_adj_pct != null) {
          const pct = s.cargo_adj_pct;
          const col = pct > 90 ? 'var(--color-negative)' : pct > 70 ? 'var(--color-warning)' : 'var(--color-positive)';
          totalRow = `<div style="display:flex;align-items:center;gap:0.8rem;padding:0.6rem 1.4rem;background:var(--surface-1)">
            <span style="font-family:var(--font-data);font-size:1rem;letter-spacing:0.08em;text-transform:uppercase;color:var(--text-brand);min-width:6.8rem">Total</span>
            <div style="flex:1;height:0.4rem;background:var(--outline);border-radius:0.2rem;overflow:hidden">
              <div style="height:100%;width:${Math.min(pct,100).toFixed(1)}%;background:${col};border-radius:0.2rem"></div>
            </div>
            <span style="font-family:var(--font-data);font-size:1.1rem;color:${col};min-width:3.4rem;text-align:right">${pct.toFixed(0)}%</span>
            <span style="font-family:var(--font-data);font-size:1rem;color:var(--text-brand);white-space:nowrap">${fmtM3(s.cargo_adj_m3)}/${fmtM3(s.cargo_max)} m³</span>
          </div>`;
        }
        storageRows = typeRowsHtml + totalRow;
      }

      // ── ECONOMY PANEL (slider position 1) ──────────────────────────────────
      // Renders the reverse-engineered supply budget (scanner/budget.py): a total
      // header, then one row per budgeted ware showing amount × price = value and
      // the basis tag (which rule set the figure). Sunlight is shown in Overview.
      // Mirrors the validated console breakdown.
      const bud      = s.budget || {};
      const budLines = bud.lines || [];
      const fmtCr    = n => n == null ? '—' : Math.round(n).toLocaleString();
      const BASIS_LABEL = {
        'manual storage cap':    'Manual cap',
        'auto: 2h production':   'Auto · 2h prod',
        'auto: 2h consumption':  'Auto · 2h use',
        'trade (max price)':     'Trade · max',
        'buy order (unverified)':'Buy order',
      };
      // Pie (interactive budget breakdown). The budget total lives in the donut
      // centre; per-ware figures appear on slice hover. safeCode is the same
      // sanitised key used by the cashflow chart so both share a common ID space.
      const safeCode = s.code.replace(/[^a-z0-9]/gi, '');
      // Which Economy sub-panel is showing — set by the Breakdown/Logs dropdown
      // (selectEconomyView), defaults to Breakdown on first render.
      const econView = economyViewByStation[s.code] || 'breakdown';
      const econRows = budLines.length === 0
        ? `<div style="padding:1.2rem 1.4rem;font-family:var(--font-data);font-size:1.1rem;color:var(--text-brand)">No economy data</div>`
        : `<!-- Pie (left) + cash-flow graph (right) as one locked, equal-height pair.
             All sizing/justification lives in .econ-row / .econ-pie / .econ-graph
             (ui/css/charts.css). Wraps to stacked on narrow windows. -->
           <div class="econ-row">
             <div id="pie-${safeCode}" class="econ-pie">${economyPieSvg(bud, allTrades, safeCode, s.code)}</div>
             ${goodsChartSvg(s, allTrades)}
           </div>`;

      return `<div class="panel" id="station-${s.code}">
        <!-- Header: vertical faction tag + name/location/status -->
        <div style="display:flex;min-height:5.2rem">
          <div style="writing-mode:vertical-lr;transform:rotate(180deg);font-family:var(--font-data);font-size:0.9rem;letter-spacing:0.18em;color:var(--text-brand);background:var(--surface-1);border-right:1px solid var(--outline);padding:0.8rem 0.6rem;display:flex;align-items:center;justify-content:center;text-transform:uppercase;flex-shrink:0">
            ${factionTag}
          </div>
          <div style="flex:1;padding:0.8rem 1.4rem;background:var(--surface-1)">
            <div style="display:flex;justify-content:space-between;align-items:baseline;gap:1rem">
              <div style="display:flex;align-items:baseline;gap:1rem;min-width:0;overflow:hidden">
                <span style="font-family:var(--font-data);font-size:1.3rem;color:var(--color-alert);letter-spacing:0.1em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${s.name.trim().toUpperCase()}</span>
                <span style="font-family:var(--font-data);color:var(--color-highlight);font-size:1.1rem;white-space:nowrap">${s.code}</span>
              </div>
              <span style="font-family:var(--font-data);font-size:1rem;color:${statusColor};letter-spacing:0.12em;white-space:nowrap;flex-shrink:0">${statusLabel}</span>
            </div>
            <!-- Two ring planes at ±45° form a cross over the planet.
                 Technique: clip-path lives on a <g> with NO transform, so the
                 horizontal cut (y<50 = back, y>50 = front) is always in SVG
                 root/screen space regardless of each ring's own rotation.
                 objectBoundingBox gradients (x1=0→x2=1) use the element's
                 screen-space bounding box, so tips fade to transparent for
                 both ring planes automatically with one gradient definition. -->
            <!-- Container is 5rem tall for layout. The SVG is 10rem tall and
                 centred vertically (top:50% + translateY(-50%)), so 2.5rem of
                 the rings bleed above and below. A vertical mask-image fades
                 those bleed zones so the arms dissolve naturally into the card. -->
            <div style="display:flex;justify-content:center;align-items:center;margin-top:0.7rem;margin-bottom:0.1rem;position:relative;height:5rem">
              <svg viewBox="0 0 180 100"
                   style="width:18rem;height:10rem;position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);pointer-events:none;
                          -webkit-mask-image:linear-gradient(to bottom,transparent 0%,black 30%,black 70%,transparent 100%);
                                  mask-image:linear-gradient(to bottom,transparent 0%,black 30%,black 70%,transparent 100%)"
                   xmlns="http://www.w3.org/2000/svg">
                <defs>
                  <linearGradient id="rg-${s.code}" x1="0" y1="0.5" x2="1" y2="0.5">
                    <stop offset="0%"   stop-color="#2dd4bf" stop-opacity="0.00"/>
                    <stop offset="22%"  stop-color="#2dd4bf" stop-opacity="0.55"/>
                    <stop offset="50%"  stop-color="#2dd4bf" stop-opacity="0.67"/>
                    <stop offset="78%"  stop-color="#2dd4bf" stop-opacity="0.55"/>
                    <stop offset="100%" stop-color="#2dd4bf" stop-opacity="0.00"/>
                  </linearGradient>
                  <linearGradient id="ri-${s.code}" x1="0" y1="0.5" x2="1" y2="0.5">
                    <stop offset="0%"   stop-color="#f59e0b" stop-opacity="0.00"/>
                    <stop offset="22%"  stop-color="#f59e0b" stop-opacity="0.50"/>
                    <stop offset="50%"  stop-color="#f59e0b" stop-opacity="0.62"/>
                    <stop offset="78%"  stop-color="#f59e0b" stop-opacity="0.50"/>
                    <stop offset="100%" stop-color="#f59e0b" stop-opacity="0.00"/>
                  </linearGradient>
                </defs>

                <ellipse cx="90" cy="50" rx="60" ry="9" fill="none"
                         stroke="url(#rg-${s.code})" stroke-width="3"
                         transform="rotate(45 90 50)"/>
                <ellipse cx="90" cy="50" rx="46" ry="7" fill="none"
                         stroke="url(#ri-${s.code})" stroke-width="5.5"
                         transform="rotate(45 90 50)"/>
                <ellipse cx="90" cy="50" rx="60" ry="9" fill="none"
                         stroke="url(#rg-${s.code})" stroke-width="3"
                         transform="rotate(-45 90 50)"/>
                <ellipse cx="90" cy="50" rx="46" ry="7" fill="none"
                         stroke="url(#ri-${s.code})" stroke-width="5.5"
                         transform="rotate(-45 90 50)"/>
              </svg>

              <div class="econ-dd-wrap" style="width:25.2rem;z-index:1">
                <div class="tri-track" id="tri-${s.code}" data-pos="0" style="position:relative">
                  <div class="tri-thumb"></div>
                  <span class="tri-opt active" onclick="setStationSlider('${s.code}',0)">Overview</span>
                  <span class="tri-opt"        onclick="toggleStationDropdown(event,'econdd-${s.code}')">Economy<i class="ti ti-chevron-down tri-opt-caret"></i></span>
                  <span class="tri-opt"        onclick="toggleStationDropdown(event,'moredd-${s.code}')">More<i class="ti ti-chevron-down tri-opt-caret"></i></span>
                </div>
                <!-- Breakdown/Logs picker for the Economy segment — click-driven
                     (see toggleStationDropdown), anchored under that third only. -->
                <div class="econ-dd-menu" id="econdd-${s.code}">
                  <div class="econ-dd-item" onclick="selectEconomyView('${s.code}','breakdown')"><i class="ti ti-chart-donut-2"></i> Breakdown</div>
                  <div class="econ-dd-item" onclick="selectEconomyView('${s.code}','logs')"><i class="ti ti-list-details"></i> Logs</div>
                </div>
                <!-- Picker for the More segment — same shell as the Economy menu,
                     but anchored under the right third (.under-more). Production
                     is the only option for now; selectMoreView is already shaped
                     for more entries later. -->
                <div class="econ-dd-menu under-more" id="moredd-${s.code}">
                  <div class="econ-dd-item" onclick="selectMoreView('${s.code}','production')"><i class="ti ti-settings"></i> Production</div>
                </div>
              </div>
            </div>
            <div style="display:flex;justify-content:space-between;align-items:center;margin-top:0.5rem">
              <span style="font-family:var(--font-data);font-size:1rem;color:var(--text-brand);letter-spacing:0.08em">${s.sector.toUpperCase()}</span>
              <span style="font-family:var(--font-data);font-size:1rem;color:var(--text-secondary);letter-spacing:0.06em">${typeLabel}</span>
            </div>
          </div>
        </div>
        <!-- Slider panel 0: Overview — the default station body (health, stats, tabs).
             The three-position header slider (setStationSlider) swaps this whole
             region for the Economy panel (1) or the placeholder (2). -->
        <div class="station-slider-panel" data-slider="0" style="display:block">
        <!-- Sunlight strip — Overview only; one-liner below the sector name. -->
        ${bud.sunlight != null ? `<div style="padding:0.4rem 1.4rem;border-bottom:1px solid var(--outline);background:var(--surface-1)"><span style="font-family:var(--font-data);font-size:0.9rem;letter-spacing:0.1em;text-transform:uppercase;color:var(--text-brand)">Sunlight </span><span style="font-family:var(--font-data);font-size:1rem;color:var(--text-secondary)">${Math.round(bud.sunlight*100)}%</span></div>` : ''}
        <!-- Hull + Shields health bars -->
        <div style="display:grid;grid-template-columns:1fr 1fr;border-top:1px solid var(--outline);border-bottom:1px solid var(--outline)">
          <div style="padding:0.7rem 1.4rem;border-right:1px solid var(--outline)">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.5rem">
              <span style="font-family:var(--font-data);font-size:0.9rem;letter-spacing:0.12em;text-transform:uppercase;color:${attnColor(hullColor)}">Hull</span>
              <span style="font-family:var(--font-data);font-size:1.1rem;color:${hullColor}">${hullPctStr}</span>
            </div>
            <div style="height:2.2rem;background:var(--outline);border-radius:0.2rem;overflow:hidden">
              <div style="height:100%;width:${hullBarW}%;background:${hullColor};border-radius:0.2rem"></div>
            </div>
          </div>
          <div style="padding:0.7rem 1.4rem">
            ${shieldDisplay}
          </div>
        </div>
        <!-- Stats row: Modules | Crew | Ships | Storage -->
        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:0.4rem;padding:0.4rem;background:var(--surface-1);border-bottom:1px solid var(--outline)">
          ${sc('Modules', modCount, 'var(--text-primary)',                                      false, moduleTipAttr, 'ti-building-community')}
          ${sc('Crew',    '—',      'var(--text-brand)',                               false, '',             'ti-users')}
          ${sc('Ships',   afTotal,   afColor,                                             false, afTipAttr,  'ti-ship')}
          ${sc('Storage', storageStr, storageColor,                                   true,  storageTipAttr, 'ti-box')}
        </div>
        <!-- Tab bar -->
        <div style="display:flex;gap:0.4rem;padding:0.6rem 1rem;border-bottom:1px solid var(--outline);background:var(--surface-1)">
          <button class="station-tab-btn active" data-tab="production" onclick="switchStationTab('${s.code}','production')"><i class="ti ti-settings" style="font-size:1.1rem;vertical-align:-1px;margin-right:0.4rem"></i>Production</button>
          <button class="station-tab-btn" data-tab="docked" onclick="switchStationTab('${s.code}','docked')"><i class="ti ti-ship" style="font-size:1.1rem;vertical-align:-1px;margin-right:0.4rem"></i>Docked${dockedShips.length > 0 ? ' · ' + dockedShips.length : ''}</button>
        </div>
        <!-- Tab panels -->
        <div class="station-tab-panel" data-tab="production" style="display:block">${prodHeader}${prodRows}</div>
        <div class="station-tab-panel" data-tab="docked"     style="display:none">${dockedRows}</div>
        </div>
        <!-- Slider panel 1: Economy — Breakdown (budget/graph pair, unchanged) or
             Logs (trade/mining history), switched by the Breakdown/Logs dropdown
             above the tri-track. See selectEconomyView in station-helpers.js. -->
        <div class="station-slider-panel" data-slider="1" style="display:none">
          <div class="econview-stack">
            <div class="econview-panel${econView === 'breakdown' ? ' active' : ''}" data-econview="breakdown">${econRows}</div>
            <div class="econview-panel${econView === 'logs' ? ' active' : ''}" data-econview="logs" id="econlogs-${safeCode}">${economyLogsHtml(safeCode, s.code, allTrades, allMining)}</div>
          </div>
        </div>
        <!-- Slider panel 2: More → Production — ware-flow diagram
             (productionFlowSvg in production-flow.js). -->
        <div class="station-slider-panel" data-slider="2" style="display:none">
          ${productionFlowSvg(s)}
        </div>
      </div>`;
    }).join("");

    // Faction standings
    document.querySelector("#rep-table tbody").innerHTML = rep.map(f => {
      const col   = { Allied:"var(--color-positive)", Friendly:"var(--color-primary)", Neutral:"var(--text-secondary)", Hostile:"var(--color-warning)", "At War":"var(--color-negative)" }[f.tier] || "var(--text-secondary)";
      const boost = f.booster ? sign(f.booster) : "—";
      return `<tr>
        <td>${f.faction_name}</td>
        <td>${tierBadge(f.tier)}</td>
        <td class="mono" style="color:${col}">${sign(f.value)}</td>
        <td>${repBar(f.value)}</td>
        <td class="mono" style="color:var(--text-brand)">${sign(f.base)}</td>
        <td class="mono" style="color:var(--text-brand)">${boost}</td>
      </tr>`;
    }).join("");

    // Alerts
    const alertsList = document.getElementById("alerts-list");
    const alerts = [];

    // Alert tiles stay terse (sector + severity) rather than mirroring the
    // advisor's full finding text — the "Advise" button is the deep link to
    // that reasoning (AdvisorsFeed.jumpToFinding() switches to the Military
    // advisor tab, expands that exact card's evidence drawer, and scrolls it
    // into view).
    const adviseBtn = (f, view = "military") => `<button class="alert-advise" onclick="AdvisorsFeed.jumpToFinding('${f.id}','${view}')">Advise</button>`;

    // Station codes jump to the Stations tab via goToStation() (station-helpers.js) —
    // same .stn-link affordance the Fleet tab's homebase column uses.
    const stationLink = code => `<span class="stn-link" onclick="goToStation('${code}')">${code}</span>`;

    // Hostile Presence — one tile per (sector, hostile faction) where their
    // force is at least a match for the player's present defence there.
    // Undefended/Outmatched (we'd lose that fight) render red; Contested
    // (could go either way) renders amber.
    hostilePresence.forEach(f => {
      const cls = (f.slots.verdict === "Outmatched" || f.slots.verdict === "Undefended")
        ? "red" : "amber";
      const msg = `<div class="alert-title">${f.slots.sector_name}</div>
        <div class="alert-sub">${f.slots.verdict} · ${f.slots.faction_name}</div>
        <div class="alert-actions">${adviseBtn(f)}${AdvisorsFeed.counterIconHtml(f)}</div>`;
      alerts.push({ msg, cls, icon: "ti-alert-triangle" });
    });

    // Force Build-Up — sectors where hostile combat strength has risen every
    // tracked scan (staging, not a raid); see buildup_findings() for the
    // run-length/growth gates. Early-warning, so amber rather than red even
    // though nothing here has been filtered by "would we currently win".
    buildups.forEach(f => {
      const msg = `<div class="alert-title">${f.slots.sector_name}</div>
        <div class="alert-sub">Building up · ${f.slots.faction_name} (${f.slots.growth}×)</div>
        <div class="alert-actions">${adviseBtn(f)}</div>`;
      alerts.push({ msg, cls: "amber", icon: "ti-trending-up-2" });
    });

    // Composition Gap — sectors where the hostile force is mostly S/M strike
    // craft the defence's guns can't track (composition_gap_findings() in
    // military.py compares dps_anti_small to total DPS). Always amber: it's
    // a loadout mismatch to fix ahead of time, not a fight being lost now.
    compositionGaps.forEach(f => {
      const msg = `<div class="alert-title">${f.slots.sector_name}</div>
        <div class="alert-sub">${f.slots.small_count} strike craft, only ${f.slots.anti_small_pct}% of your DPS tracks them · ${f.slots.faction_name}</div>
        <div class="alert-actions">${adviseBtn(f)}</div>`;
      alerts.push({ msg, cls: "amber", icon: "ti-puzzle" });
    });

    // Outranged — sectors where hostile capital hulls (L/XL) out-reach the
    // whole defence (outranged_findings() in military.py). Standoff-bombardment
    // risk rather than a fight already being lost, so amber like the other
    // loadout-mismatch alerts.
    outranged.forEach(f => {
      const msg = `<div class="alert-title">${f.slots.sector_name}</div>
        <div class="alert-sub">${f.slots.capital_count} capital(s) reach ${f.slots.their_range_km} km vs your ${f.slots.our_range_km} km · ${f.slots.faction_name}</div>
        <div class="alert-actions">${adviseBtn(f)}</div>`;
      alerts.push({ msg, cls: "amber", icon: "ti-target-arrow" });
    });

    // Damaged Fleet — combat ships under DAMAGED_HULL_PCT (75%) hull, undocked
    // (damaged_fleet_findings() in military.py), so every finding here has
    // already taken 25%+ damage. Severity is relative damage (hull_pct), not
    // priority_score's absolute missing HP — "badly hurt" should mean the
    // ship itself is close to lost, not that it's expensive, so a fighter at
    // 30% hull reads the same urgency as a destroyer at 30% hull. 40% hull is
    // the halfway point of this alert's whole 0-75% range: below it the ship
    // has taken more damage than it has left (red), above it there's still
    // more hull than damage (amber).
    const DAMAGED_FLEET_RED_HULL_PCT = 40;
    damagedFleet.forEach(f => {
      const cls = f.slots.hull_pct < DAMAGED_FLEET_RED_HULL_PCT ? "red" : "amber";
      const msg = `<div class="alert-title">${f.slots.ship_name}</div>
        <div class="alert-sub">${f.slots.hull_pct}% hull · ${f.slots.role} · ${f.slots.sector_name}</div>
        <div class="alert-actions">${adviseBtn(f)}</div>`;
      alerts.push({ msg, cls, icon: "ti-heart-broken" });
    });

    // Station Damaged / Under Attack — buckets stations by severity rather
    // than one tile per station (there can be a lot of stations), same list
    // pattern as the idling-ships/idle-miners rows below. ti-building-broken
    // doesn't exist in the bundled Tabler set, so this falls back to the
    // same triangle icon as the other red/amber alerts above.
    if (damagedStationsRed.length > 0) {
      const codes = damagedStationsRed.slice(0,6).map(s=>stationLink(s.code)).join(", ");
      const more  = damagedStationsRed.length > 6 ? ` (+${damagedStationsRed.length-6} more)` : "";
      alerts.push({ msg:`<div class="alert-sub">${damagedStationsRed.length} station(s) under attack or critical hull: ${codes}${more}</div>`, cls:"red", icon:"ti-alert-triangle" });
    }
    if (damagedStationsAmber.length > 0) {
      const codes = damagedStationsAmber.slice(0,6).map(s=>stationLink(s.code)).join(", ");
      const more  = damagedStationsAmber.length > 6 ? ` (+${damagedStationsAmber.length-6} more)` : "";
      alerts.push({ msg:`<div class="alert-sub">${damagedStationsAmber.length} station(s) damaged: ${codes}${more}</div>`, cls:"amber", icon:"ti-alert-triangle" });
    }

    // Storage Overflow — stations about to cap out on a surplus ware within
    // OVERFLOW_ALERT_HOURS (1h). Terse tile per finding (station + the
    // at-risk ware), same as the military tiles above; the "Advise" button is
    // the deep link to the Economic advisor card with the full reasoning.
    // Under OVERFLOW_ALERT_RED_HOURS (30min) renders red — same red/amber
    // split idea as Damaged Fleet above, just on time-to-cap instead of hull.
    storageOverflow.forEach(f => {
      const cls = f.slots.hours <= OVERFLOW_ALERT_RED_HOURS ? "red" : "amber";
      const msg = `<div class="alert-title">${f.slots.station_name}</div>
        <div class="alert-sub">${f.slots.ware_name}</div>
        <div class="alert-actions">${adviseBtn(f, "economic")}</div>`;
      alerts.push({ msg, cls, icon: "ti-database-exclamation" });
    });

    // Ship codes are player ships (`waiting` is filtered from `players`
    // above), so every code in these messages jumps to the Fleet tab via
    // jumpToShip() — same .ship-link affordance used on the Crew/Economy tabs.
    const shipLink = code => `<span class="ship-link" onclick="jumpToShip('${code}','player')">${code}</span>`;

    // Stranded Deliveries — one tile per ship+ware, same terse pattern as the
    // advisor-backed tiles above. Always amber: a missing delivery order is a
    // fix-it-when-convenient paperwork gap, not damage or hostile action.
    strandedDeliveries.forEach(f => {
      const msg = `<div class="alert-title">${shipLink(f.slots.ship_code)} · ${f.slots.ware_name}</div>
        <div class="alert-sub">Holding cargo ${f.slots.hours}h, no delivery destination</div>
        <div class="alert-actions">${adviseBtn(f, "trader")}</div>`;
      alerts.push({ msg, cls: "amber", icon: "ti-package-off" });
    });

    // Wrapped in a single <div>: bare text mixed with inline .ship-link spans
    // as DIRECT children of the flex-column .alert tile gets split into one
    // anonymous flex item per run, each picking up the tile's own gap — the
    // wrapper makes the whole message one flex item so it just wraps as a
    // normal paragraph instead.
    if (waiting.length > 0) {
      const codes = waiting.slice(0,6).map(s=>shipLink(s.code)).join(", ");
      const more  = waiting.length > 6 ? ` (+${waiting.length-6} more)` : "";
      alerts.push({ msg:`<div class="alert-sub">${waiting.length} ships idling (Waiting order): ${codes}${more}</div>`, cls:"amber", icon:"ti-clock" });
    }

    const idleMiners = waiting.filter(s => MINER_ROLES.has(s.role));
    if (idleMiners.length > 0) {
      alerts.push({ msg:`<div class="alert-sub">${idleMiners.length} idle miner(s): ${idleMiners.map(s=>shipLink(s.code)).join(", ")}</div>`, cls:"amber", icon:"ti-shovel" });
    }

    alertsList.innerHTML = alerts.length === 0
      ? `<div class="alert green"><i class="ti ti-circle-check"></i> No alerts detected.</div>`
      : alerts.map(a => `<div class="alert ${a.cls}"><i class="ti ${a.icon}"></i> ${a.msg}</div>`).join("");

    // Trends tab — cross-scan trajectory + changes feed. Guarded so an older
    // export without a `trends` section (or a shell that didn't load trends.js)
    // degrades to an empty tab instead of throwing mid-populate.
    if (typeof renderTrends === 'function') renderTrends(data);

    renderNpcStations(data);
    renderUniverseMap(data);
    // renderUniverseMap repopulates the shared sector maps; if the Sectors tab
    // is already open, rebuild it against the new scan (and refresh the detail).
    if (document.getElementById('tab-sectors')?.classList.contains('active')) {
      renderSectorsList();
      if (_selectedSector) showSectorDetail(_selectedSector);
    }

    document.getElementById("loading").style.display = "none";
    document.getElementById("shell").style.display   = "flex";
  }


  // ── Tooltip content builders ───────────────────────────────
  // Moved out of tooltips.js (the dispatcher there is a shared engine): each
  // builder lives with the feature that stamps its matching data-* attribute.
  // The dispatcher still calls these by name — they are file-global here.

    function moduleTipHtml(groups) {
      return `<div style="min-width:18rem;max-width:26rem;padding:0.2rem 0">` +
        groups.map(g =>
          `<div style="margin-bottom:0.8rem">
             <div style="font-size:0.9rem;letter-spacing:0.12em;text-transform:uppercase;
                         color:var(--text-brand);margin-bottom:0.4rem;padding-bottom:0.3rem;
                         border-bottom:1px solid var(--outline)">${g.category}</div>
             ${g.items.map(([name, count]) =>
               `<div style="display:flex;justify-content:space-between;align-items:baseline;
                            gap:1.2rem;padding:1px 0">
                  <span style="color:var(--text-secondary);font-size:1.1rem;white-space:nowrap;
                               overflow:hidden;text-overflow:ellipsis">${name}</span>
                  <span style="color:var(--text-brand);font-size:1rem;flex-shrink:0">×${count}</span>
                </div>`
             ).join('')}
           </div>`
        ).join('') +
      `</div>`;
    }

    function storageTipHtml(types) {
      // Renders each storage type as a label + % row followed by a fill bar.
      // Label, percentage, and m³ text all use the category's fixed accent colour.
      // The Total row is preceded by a thin separator line.
      const fmtM3 = v => v >= 1e6 ? (v/1e6).toFixed(2)+'M' : v >= 1e3 ? (v/1e3).toFixed(1)+'K' : v;
      return `<div style="min-width:22rem;padding:0.2rem 0">` +
        types.map(t => {
          const barW = t.pct != null ? Math.min(t.pct, 100) : 0;
          const pctLabel = t.pct != null ? `${t.pct}%` : '—';
          const sub = (t.m3 != null && t.max != null)
            ? `<div style="margin-top:0.2rem;text-align:right;font-size:1rem;color:${t.color};opacity:0.75">${fmtM3(t.m3)} / ${fmtM3(t.max)} m³</div>`
            : '';
          const sep = t.isTotal
            ? `<div style="border-top:1px solid var(--outline);margin:0.5rem 0 0.8rem"></div>`
            : '';
          return `${sep}<div style="margin-bottom:0.8rem">
            <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:0.3rem">
              <span style="font-size:1rem;letter-spacing:0.1em;text-transform:uppercase;color:${t.color}">${t.label}</span>
              <span style="color:${t.color};font-family:var(--font-data);margin-left:1.2rem">${pctLabel}</span>
            </div>
            <div style="height:0.6rem;background:var(--outline);border-radius:0.2rem;overflow:hidden">
              <div style="height:100%;width:${barW}%;background:${t.color};border-radius:0.2rem"></div>
            </div>
            ${sub}
          </div>`;
        }).join('') +
      `</div>`;
    }


  // ── Tooltip registration ──────────────────────────────────────────
  // Station cards stamp these: storage-bay breakdown, module list, and the
  // pre-rendered assigned-fleet breakdown (fleet tip HTML is built at stamp time).
  registerTip('storageTip', (el, _e, tip) => {
    tip.innerHTML = storageTipHtml(JSON.parse(decodeURIComponent(el.dataset.storageTip)));
    tip.style.color      = '';
    tip.style.whiteSpace = 'normal';
    return true;
  });

  registerTip('modulesTip', (el, _e, tip) => {
    tip.innerHTML = moduleTipHtml(JSON.parse(decodeURIComponent(el.dataset.modulesTip)));
    tip.style.color      = '';
    tip.style.whiteSpace = 'normal';
    return true;
  });

  registerTip('fleetTip', (el, _e, tip) => {
    // Pre-rendered HTML encoded into the attribute at stamp time.
    tip.innerHTML = decodeURIComponent(el.dataset.fleetTip);
    tip.style.color      = '';
    tip.style.whiteSpace = 'normal';
    return true;
  });
