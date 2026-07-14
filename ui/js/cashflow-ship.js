  // Core role: By-Ship panel of the station cash-flow chart — hourly credits earned per ship, filtered by faction.
  //
  // The builder receives the shared layout context (ctx) prepared by
  // buildCfBodiesHtml in cashflow-chart.js.

  const shipChartData = {}; // { [safeCode]: [{fx,fy,vbx,vby,ship,name,colour,isSell,hAgo,total,trades}] }

  // Ship-earnings chart state (By Ship mode).
  // Colours are auto-assigned alphabetically from this palette so the same
  // ship always gets the same colour regardless of the scrubber window.
  const SHIP_COLOURS_PALETTE = [
    '#fbbf24', // amber
    '#c084fc', // violet
    '#38bdf8', // sky blue
    '#f87171', // coral
    '#a3e635', // lime
    '#fb923c', // orange
    '#f472b6', // pink
    '#818cf8', // indigo
    '#34d399', // emerald
    '#facc15', // yellow
  ];
  const shipMode          = {}; // 'sell'|'buy' per station
  const shipVisibility    = {}; // { [safeCode]: { [ship_code]: bool } }
  const shipColourMap     = {}; // { [safeCode]: { [ship_code]: colour } } — seeded once from full 24h
  const shipFactionFilter = {}; // { [safeCode]: owner_id } — which faction's ships to show
  const _shipPieTimers    = {}; // debounce handles so rapid toggles batch into one pie rebuild

  // ── By Ship body ───────────────────────────────────────────────────────────
  // One line per ship of the selected faction that traded at this station,
  // showing hourly credits earned. A faction chip row (Player + any NPC
  // factions) filters which group is shown. A SELL/BUY pill splits directions.
  // Colours are assigned alphabetically from SHIP_COLOURS_PALETTE so they
  // stay stable as the user drags the scrubber.
  function buildCfShipBody(ctx) {
    const { safeCode, station, allTrades, trades, numHours, windowHours, offsetHours, svgW, svgH, ml, mt, pw, ph, xOf, xTicksHtml, yAxisHtml } = ctx;

    const isRawId = s => /^\[?0x[0-9a-f]+\]?$/i.test(String(s || '').trim());
    const curMode  = shipMode[safeCode] || 'sell';
    const isSell   = curMode === 'sell';

    // Faction chip helpers. FACTION_LABELS / FACTION_COLOURS are globals
    // defined in designs-builder.js and available on the shared page scope.
    const factionLabel  = id => id === 'player' ? 'PLR'
      : (typeof FACTION_LABELS  !== 'undefined' && FACTION_LABELS[id])  || id.slice(0, 3).toUpperCase();
    const factionColour = id => id === 'player' ? CHART_LINE
      : (typeof FACTION_COLOURS !== 'undefined' && FACTION_COLOURS[id]) || '#6e7681';

    // Compute the unique factions from the FULL 24h window (not just the
    // zoom slice) so the chips don't vanish when the user pans to a quiet
    // period. Player always sorts first; remaining factions alphabetically.
    const allFactions = new Map(); // owner_id → { label, colour }
    allTrades.forEach(t => {
      if (t.station_code !== station.code || !t.ship_owner_id || isRawId(t.ship_code)) return;
      if (!allFactions.has(t.ship_owner_id)) {
        allFactions.set(t.ship_owner_id, {
          label:  factionLabel(t.ship_owner_id),
          colour: factionColour(t.ship_owner_id),
        });
      }
    });
    const sortedFactions = [...allFactions.entries()]
      .sort(([a], [b]) => a === 'player' ? -1 : b === 'player' ? 1 : a.localeCompare(b));

    // Default the faction filter to 'player' on first view, falling back to
    // the first available faction if player never traded here.
    if (!shipFactionFilter[safeCode]) {
      shipFactionFilter[safeCode] = allFactions.has('player')
        ? 'player'
        : (sortedFactions[0]?.[0] || 'player');
    }
    const activeFaction = shipFactionFilter[safeCode];

    // Seed the colour map once from all 24h named ships so colours are stable.
    if (!shipColourMap[safeCode]) {
      const allShips = [...new Set(
        allTrades
          .filter(t => t.station_code === station.code && t.ship_code && !isRawId(t.ship_code))
          .map(t => t.ship_code)
      )].sort();
      shipColourMap[safeCode] = {};
      allShips.forEach((c, i) => {
        shipColourMap[safeCode][c] = SHIP_COLOURS_PALETTE[i % SHIP_COLOURS_PALETTE.length];
      });
    }

    // Faction selector dropdown — shown above the chart, not inside the SVG.
    // Styled to match cf-toggle-btn.active so it blends with the mode buttons.
    const factionChipsHtml = `<select
      class="cf-toggle-btn"
      style="background:#030d14;color:${CHART_LINE};border-color:${CHART_LINE}"
      onchange="setShipFactionFilter('${safeCode}', this.value)">${
      sortedFactions.map(([id, f]) =>
        `<option value="${id}"${id === activeFaction ? ' selected' : ''} style="background:#030d14;color:${f.colour}">${f.label}</option>`
      ).join('')
    }</select>`;

    // Filter to selected direction, active faction, named ships, visible window.
    const filteredTrades = trades.filter(t =>
      t.direction === (isSell ? 'Out' : 'In') &&
      t.ship_code && !isRawId(t.ship_code) &&
      t.ship_owner_id === activeFaction
    );

    // Vertical SELL/BUY pill — same design as By Ware and Avg Price.
    const shipToggleFO = `
      <foreignObject x="2" y="${mt}" width="30" height="44">
        <div xmlns="http://www.w3.org/1999/xhtml" style="
            width:30px;height:44px;
            display:grid;grid-template-rows:1fr 1fr;
            position:relative;
            background:rgba(4,12,20,0.88);
            border:1px solid rgba(0,0,0,0.70);
            border-radius:2px;overflow:hidden;user-select:none;
            box-shadow:inset 0 2px 7px rgba(0,0,0,0.70),inset 0 1px 3px rgba(0,0,0,0.50),0 1px 0 rgba(255,255,255,0.07)">
          <div style="
              position:absolute;left:1px;right:1px;height:20px;
              top:${isSell ? '1px' : '23px'};
              background:linear-gradient(170deg,rgba(85,245,215,0.97) 0%,rgba(46,202,178,0.93) 42%,rgba(29,170,150,0.91) 100%);
              border-radius:1px;pointer-events:none;
              box-shadow:0 3px 9px rgba(0,0,0,0.70),0 1px 3px rgba(0,0,0,0.50),inset 0 1px 0 rgba(255,255,255,0.42),inset 0 -1px 0 rgba(0,0,0,0.24)">
          </div>
          <span onclick="setShipMode('${safeCode}','sell')" style="
              position:relative;z-index:1;cursor:pointer;
              display:flex;align-items:center;justify-content:center;
              font-family:'Share Tech Mono',monospace;font-size:7px;letter-spacing:0.06em;text-transform:uppercase;
              color:${isSell ? '#051210' : 'rgba(45,212,191,0.40)'};
              font-weight:${isSell ? '700' : '400'}">SELL</span>
          <span onclick="setShipMode('${safeCode}','buy')" style="
              position:relative;z-index:1;cursor:pointer;
              display:flex;align-items:center;justify-content:center;
              font-family:'Share Tech Mono',monospace;font-size:7px;letter-spacing:0.06em;text-transform:uppercase;
              color:${!isSell ? '#051210' : 'rgba(45,212,191,0.40)'};
              font-weight:${!isSell ? '700' : '400'}">BUY</span>
        </div>
      </foreignObject>`;

    if (!filteredTrades.length) {
      const factionLabel = (allFactions.get(activeFaction) || {}).label || activeFaction;
      return `
        <div style="padding:0.3rem 0.1rem 0.5rem">${factionChipsHtml}</div>
        <div style="display:flex;align-items:flex-start;gap:0.8rem;padding:0.2rem 0 0.4rem">
          <div style="display:flex;flex-direction:column;gap:0.2rem">
            <button class="cf-toggle-btn ${isSell ? 'active' : ''}" onclick="setShipMode('${safeCode}','sell')">Sell</button>
            <button class="cf-toggle-btn ${!isSell ? 'active' : ''}" onclick="setShipMode('${safeCode}','buy')">Buy</button>
          </div>
          <div style="padding:0.6rem 0;font-family:var(--font-data);font-size:1.1rem;color:var(--text-brand)">No ${isSell ? 'sell' : 'buy'} activity for [${factionLabel}] in this window</div>
        </div>`;
    }

    // Group by ship code; sort alphabetically for a stable render order.
    // Also capture ship_name so the chip labels show "Hull (CODE)" format.
    const byShip    = {};
    const shipNames = {}; // ship_code → hull name
    filteredTrades.forEach(t => {
      (byShip[t.ship_code] = byShip[t.ship_code] || []).push(t);
      if (t.ship_name && !shipNames[t.ship_code]) shipNames[t.ship_code] = t.ship_name;
    });
    const shipCodes = Object.keys(byShip).sort();

    // Seed per-ship visibility defaults.
    if (!shipVisibility[safeCode]) shipVisibility[safeCode] = {};
    shipCodes.forEach(c => {
      if (shipVisibility[safeCode][c] === undefined) shipVisibility[safeCode][c] = true;
    });

    // Hourly credit totals and trade counts per ship.
    // Index 0 = most recent hour (same orientation as net[] in hourlyBody).
    const shipHourly  = {};
    const shipTradeCt = {};
    shipCodes.forEach(code => {
      shipHourly[code]  = new Array(numHours).fill(0);
      shipTradeCt[code] = new Array(numHours).fill(0);
      byShip[code].forEach(t => {
        const i = Math.floor(t.time_ago_s / 3600 - offsetHours);
        if (i < 0 || i >= numHours) return;
        shipHourly[code][i]  += t.total_cr || 0;
        shipTradeCt[code][i] += 1;
      });
    });

    // Y-axis: zero-floored, scaled to the highest single-ship hourly value.
    let yHi = 0;
    shipCodes.forEach(code => shipHourly[code].forEach(v => { if (v > yHi) yHi = v; }));
    const step  = cfNiceStep(yHi || 1, 6);
    const axTop = Math.ceil(yHi / step) * step || step;
    const axBot = 0;
    // axBot = 0 simplifies: yOf(0) = mt+ph (baseline), yOf(axTop) = mt (top).
    const yOf = v => mt + ph - v / axTop * ph;

    const glowId   = `ship-glow-${safeCode}`;
    const shipType = (cfChartType[safeCode] || {}).byship || 'line';

    const shipGroupHtml = [];
    // Per-dot hover store: one entry per ship per non-zero hour bucket.
    // Committed to shipChartData[safeCode] after the loop so tooltips.js can
    // find the nearest point by Euclidean distance (same pattern as By-Ware).
    const storeShip = [];

    // Per-ship SVG line or scatter.
    shipCodes.forEach(code => {
      const col = (shipColourMap[safeCode] || {})[code] || CHART_LINE;
      // Plot bucket centres oldest-to-newest (left-to-right), same as hourlyBody.
      const pts = [];
      for (let i = numHours - 1; i >= 0; i--) {
        const cx = xOf(offsetHours + (i + Math.min(i + 1, windowHours)) / 2);
        pts.push([cx, yOf(shipHourly[code][i])]);
      }
      const baseY = mt + ph;

      let elements;
      if (shipType === 'scatter') {
        elements = pts
          .filter(([, y]) => y < baseY - 0.5) // skip zero-value points
          .map(([x, y]) =>
            `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="2.5" fill="${col}" style="filter:drop-shadow(0 0 4px ${col})" opacity="0.90"/>`
          ).join('');
      } else {
        // Line (default): faint glow copy + crisp line + dots at non-zero hours.
        const linePts  = pts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
        const areaPath = `M ${pts[0][0].toFixed(1)} ${baseY} ` +
                         pts.map(([x, y]) => `L ${x.toFixed(1)} ${y.toFixed(1)}`).join(' ') +
                         ` L ${pts[pts.length - 1][0].toFixed(1)} ${baseY} Z`;
        const dots = pts
          .filter(([, y]) => y < baseY - 0.5)
          .map(([x, y]) => `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="2" fill="${col}" opacity="0.85"/>`)
          .join('');
        elements = `
          <path d="${areaPath}" fill="${col}" fill-opacity="0.08" stroke="none"/>
          <polyline points="${linePts}" fill="none" stroke="${col}" stroke-width="3" stroke-linejoin="round" stroke-linecap="round" opacity="0.25" filter="url(#${glowId})"/>
          <polyline points="${linePts}" fill="none" stroke="${col}" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/>
          ${dots}`;
      }

      // Populate hover store: one entry per non-zero hour bucket for this ship.
      // Individual trades are pre-sorted largest first so the tooltip shows the
      // most impactful ware at the top without needing to sort at display time.
      for (let i = 0; i < numHours; i++) {
        if (!shipHourly[code][i]) continue;
        const cx = xOf(offsetHours + (i + Math.min(i + 1, windowHours)) / 2);
        const cy = yOf(shipHourly[code][i]);
        storeShip.push({
          fx:     (cx - ml) / pw,
          fy:     (cy - mt) / ph,
          vbx:    +cx.toFixed(1),
          vby:    +cy.toFixed(1),
          ship:   code,
          name:   shipNames[code] || '',
          colour: col,
          isSell,
          hAgo:   offsetHours + i,
          total:  shipHourly[code][i],
          trades: byShip[code]
            .filter(t => Math.floor(t.time_ago_s / 3600 - offsetHours) === i)
            .sort((a, b) => (b.total_cr || 0) - (a.total_cr || 0))
            .map(t => ({
              ware:         t.ware_name || 'Unknown',
              wareColour:   WARE_COLOURS[t.ware_name] || CHART_LINE,
              dir:          t.direction === 'Out' ? 'sell' : 'buy',
              amount:       t.amount,
              priceEa:      t.price_cr,
              total:        t.total_cr,
              counterparty: t.counterparty || '',
            })),
        });
      }

      const safeShip = code.replace(/[^a-z0-9]/gi, '');
      const visible  = shipVisibility[safeCode][code];
      shipGroupHtml.push(`<g id="ship-group-${safeCode}-${safeShip}" style="display:${visible ? 'block' : 'none'}">${elements}</g>`);
    });

    // Legend chips — click toggles the ship's line on/off.
    const chips = shipCodes.map(code => {
      const col      = (shipColourMap[safeCode] || {})[code] || CHART_LINE;
      const safeShip = code.replace(/[^a-z0-9]/gi, '');
      const on       = shipVisibility[safeCode][code];
      const label = shipNames[code] ? `${shipNames[code]} (${code})` : code;
      return `<span id="ship-chip-${safeCode}-${safeShip}"
                    onclick="toggleShip('${safeCode}','${code}')"
                    style="cursor:pointer;opacity:${on ? '1' : '0.35'};
                           display:inline-flex;align-items:center;
                           padding:0.2rem 0.7rem;border-radius:0.2rem;
                           border:1px solid ${col}44;background:${col}22;
                           color:${col};font-family:var(--font-data);
                           font-size:1rem;white-space:nowrap;letter-spacing:0.04em;
                           user-select:none">${label}</span>`;
    }).join('');

    const typeLabel = shipType === 'scatter' ? 'DOT' : 'LINE';
    const typePill  = `
      <g onclick="cycleChart('${safeCode}','byship')" style="cursor:pointer">
        <rect x="${(ml + pw - 38).toFixed(1)}" y="${(mt + 3).toFixed(1)}" width="36" height="13" rx="2"
              fill="${CHART_ACCENT}10" stroke="${CHART_ACCENT}30" stroke-width="0.5"/>
        <text x="${(ml + pw - 4).toFixed(1)}" y="${(mt + 11).toFixed(1)}" text-anchor="end"
              fill="${CHART_LINE}" fill-opacity="0.75"
              style="font-family:var(--font-data);font-size:0.7rem;letter-spacing:0.08em">${typeLabel} ›</text>
      </g>`;

    // Commit hover store so tooltips.js can do nearest-point lookup.
    shipChartData[safeCode] = storeShip;

    return `
      <div style="padding:0.3rem 0.1rem 0.5rem">${factionChipsHtml}</div>
      <div style="background:#030d14;border:1px solid rgba(25,230,200,0.18);border-radius:0.3rem;box-shadow:inset 0 0 24px rgba(25,230,200,0.05);padding:0.4rem">
        <svg viewBox="0 0 ${svgW} ${svgH}" style="display:block;width:100%;height:auto">
          <defs>
            <filter id="${glowId}" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="2"/></filter>
            <clipPath id="cfclip-${safeCode}-s"><rect x="${ml}" y="${mt}" width="${pw}" height="${ph}"/></clipPath>
          </defs>
          <rect x="${ml}" y="${mt}" width="${pw}" height="${ph}" fill="#020a10" onclick="cycleChart('${safeCode}','byship')"/>
          ${yAxisHtml(yOf, axBot, axTop, step)}
          ${xTicksHtml}
          <g clip-path="url(#cfclip-${safeCode}-s)">
            ${shipGroupHtml.join('')}
          </g>
          <line x1="${ml}" y1="${mt}" x2="${ml}" y2="${mt + ph}" stroke="${CHART_ACCENT}" stroke-opacity="0.35" stroke-width="1"/>
          <text x="9" y="${mt + ph / 2}" text-anchor="middle" dominant-baseline="middle" fill="${CHART_LINE}" fill-opacity="0.6"
                style="font-family:var(--font-data);font-size:0.8rem;letter-spacing:0.1em" transform="rotate(-90 9 ${mt + ph / 2})">CREDITS/HR</text>
          <!-- Highlight ring for the nearest hovered datapoint; colour set dynamically -->
          <circle class="cf-ship-marker" r="5" fill="none" stroke="${CHART_LINE}" stroke-width="1.5" style="display:none;pointer-events:none"/>
          <!-- Transparent overlay captures mouse events; nearest-point search in tooltips.js -->
          <rect x="${ml}" y="${mt}" width="${pw}" height="${ph}" fill="transparent" data-shipflow="${safeCode}" onclick="cycleChart('${safeCode}','byship')" style="cursor:crosshair"/>
          ${typePill}
          <!-- SELL/BUY toggle must render last so it sits above the hit overlay. -->
          ${shipToggleFO}
        </svg>
      </div>
      <div style="display:flex;flex-wrap:wrap;gap:0.5rem;padding:0.6rem 0.2rem 0.2rem">
        ${chips}
      </div>`;
  }

  // Switch the By Ship chart between sell (Out) and buy (In) trades.
  function setShipMode(safeCode, mode) {
    shipMode[safeCode] = mode;
    rebuildCfChart(safeCode);
    rebuildPie(safeCode);
  }

  // Switch which faction's ships are shown in the By Ship chart.
  // Clears the per-station ship visibility map so the new faction's ships all
  // start visible (rather than inheriting toggle state from a different faction).
  function setShipFactionFilter(safeCode, ownerId) {
    shipFactionFilter[safeCode] = ownerId;
    delete shipVisibility[safeCode]; // reset to "all visible" for new faction
    rebuildCfChart(safeCode);
  }

  // Toggle a single ship's line on/off in the By Ship chart.
  function toggleShip(safeCode, shipCode) {
    const vis = shipVisibility[safeCode];
    if (!vis) return;
    vis[shipCode]       = !vis[shipCode];
    const safeShip      = shipCode.replace(/[^a-z0-9]/gi, '');
    const group         = document.getElementById(`ship-group-${safeCode}-${safeShip}`);
    const chip          = document.getElementById(`ship-chip-${safeCode}-${safeShip}`);
    if (group) group.style.display = vis[shipCode] ? 'block' : 'none';
    if (chip)  chip.style.opacity  = vis[shipCode] ? '1'     : '0.35';
    // Debounce the pie rebuild so rapid clicks don't queue up multiple expensive
    // innerHTML replacements — the same approach used for the universe-map transform.
    clearTimeout(_shipPieTimers[safeCode]);
    _shipPieTimers[safeCode] = setTimeout(() => rebuildPie(safeCode), 150);
  }

  function shipflowTipHtml(d) {
    // By Ship hover: one ship's individual trades for the hovered hour bucket.
    // Each row shows ware (in its defined colour), direction, amount × unit price,
    // total credits, and the counterparty station where the goods moved.
    const fmtU = cfFmtU;
    const fmtC = n => '+' + Math.round(n).toLocaleString();
    const h0   = Math.round(d.hAgo);
    const span = h0 === 0 ? 'Past hour' : `${h0}–${h0 + 1}h ago`;
    const label = d.name ? `${d.name} (${d.ship})` : d.ship;

    const tradeRows = d.trades.map(t => {
      const isSell = t.dir === 'sell';
      const dirCol = isSell ? CHART_ACCENT : CHART_LOSS;
      const cpRow  = t.counterparty
        ? `<div style="color:var(--text-brand);font-family:var(--font-data);font-size:0.82rem;padding-left:1.3rem;margin-top:2px;letter-spacing:0.04em">${isSell ? '→' : '←'} ${t.counterparty}</div>`
        : '';
      return `<div style="padding:5px 0 4px;border-bottom:1px solid rgba(255,255,255,0.05)">
        <div style="display:flex;align-items:baseline;gap:0.45rem">
          <span style="color:${dirCol};font-size:0.9rem;flex-shrink:0">${isSell ? '▲' : '▼'}</span>
          <span style="color:${t.wareColour};font-size:1rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${t.ware}</span>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:baseline;padding-left:1.3rem;margin-top:3px">
          <span style="font-family:var(--font-data);font-size:0.88rem;color:var(--text-brand);white-space:nowrap">
            ${fmtU(t.amount)}<span style="color:var(--text-brand);opacity:0.5"> ×</span> ${fmtU(t.priceEa)} Cr
          </span>
          <span style="font-family:var(--font-data);font-size:1rem;color:${CHART_ACCENT};white-space:nowrap;flex-shrink:0">${fmtC(t.total)} Cr</span>
        </div>
        ${cpRow}
      </div>`;
    }).join('');

    return `<div style="min-width:26rem;max-width:34rem;padding:0.2rem 0">
      <div style="display:flex;justify-content:space-between;align-items:baseline;gap:1.2rem;margin-bottom:0.4rem;padding-bottom:0.4rem;border-bottom:1px solid var(--outline)">
        <span style="color:${d.colour};font-size:1rem;letter-spacing:0.04em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:20rem">${label}</span>
        <span style="font-family:var(--font-data);font-size:0.85rem;color:var(--text-brand);flex-shrink:0">${span}</span>
      </div>
      ${tradeRows}
      <div style="margin-top:0.4rem;padding-top:0.4rem;border-top:1px solid var(--outline);display:flex;justify-content:space-between;align-items:baseline">
        <span style="font-size:0.9rem;color:var(--text-brand)">${d.trades.length} trade${d.trades.length !== 1 ? 's' : ''}</span>
        <span style="font-family:var(--font-data);font-size:1.1rem;color:${CHART_ACCENT}">${fmtC(d.total)} Cr</span>
      </div>
    </div>`;
  }

  registerTip('shipflow', (el, e, tip) => {
    // By Ship chart: find the nearest ship-hour dot by Euclidean distance and show
    // its individual trades (ware, amount x price, counterparty, total).
    const sc  = el.dataset.shipflow;
    const arr = shipChartData[sc];
    if (!arr || !arr.length) return false;
    const r  = el.getBoundingClientRect();
    const fx = (e.clientX - r.left) / r.width;
    const fy = (e.clientY - r.top)  / r.height;
    let best = null, bd = Infinity;
    for (const p of arr) {
      // Skip points for ships the user has toggled off.
      if (shipVisibility[sc] && shipVisibility[sc][p.ship] === false) continue;
      const dd = (p.fx - fx) ** 2 + (p.fy - fy) ** 2;
      if (dd < bd) { bd = dd; best = p; }
    }
    if (!best) return false;
    tip.innerHTML = shipflowTipHtml(best);
    tip.style.color = '';
    tip.style.whiteSpace = 'normal';
    const svg = el.closest('svg');
    const mk  = svg && svg.querySelector('.cf-ship-marker');
    if (mk) {
      mk.setAttribute('cx', best.vbx);
      mk.setAttribute('cy', best.vby);
      mk.setAttribute('stroke', best.colour);
      mk.style.display = 'block';
    }
    return true;
  });
