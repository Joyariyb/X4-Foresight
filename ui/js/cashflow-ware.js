  // Core role: By-Ware panel of the station cash-flow chart — one step-line per ware, normalised to its own min/avg/max price band.
  //
  // The builder receives the shared layout context (ctx) prepared by
  // buildCfBodiesHtml in cashflow-chart.js.

  // By-Ware panel state, keyed by station safeCode.
  const wareMode = {};        // 'sell'|'buy' per station
  const wareVisibility = {};  // { [safeCode]: { [ware_name]: bool } }
  const wareChartData = {};   // hover lookup table — one entry per trade dot

  // ── By-Ware body ───────────────────────────────────────────────────────────
  // One step-line per ware, normalised to its own min/avg/max price band.
  // A Sold / Bought toggle at the top-left switches between Out and In trades
  // so the user can inspect both what the station sold and what it bought.
  function buildCfWareBody(ctx) {
    const { safeCode, trades, offsetHours, svgW, svgH, ml, mt, pw, ph, xOf, xTicksHtml } = ctx;

    // Read the current direction ('sell' = station sold Out; 'buy' = station bought In).
    const curMode = wareMode[safeCode] || 'sell';
    const isSell  = curMode === 'sell';

    // Filter to only the selected trade direction within the visible window.
    const filteredTrades = trades.filter(t => t.direction === (isSell ? 'Out' : 'In'));

    // Vertical direction toggle — embedded as a <foreignObject> in the SVG's
    // LEFT MARGIN (x=2, outside the dark plot rectangle) at y=mt, so it sits
    // next to the MAX label. Matches the tri-track sliding-pill aesthetic but
    // oriented vertically: SOLD on top, BOUGHT on bottom.
    // The thumb position is baked in at render time (top:1px = sell, top:23px = buy);
    // the pill snaps rather than animating because innerHTML is replaced on each toggle.
    // Width=30 keeps the toggle clear of the MAX label (which right-aligns at x=50,
    // spanning ~x=36–50 at 8px mono), leaving a ~4px gap.
    const wareToggleFO = `
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
          <span onclick="setWareMode('${safeCode}','sell')" style="
              position:relative;z-index:1;cursor:pointer;
              display:flex;align-items:center;justify-content:center;
              font-family:'Share Tech Mono',monospace;font-size:7px;letter-spacing:0.06em;text-transform:uppercase;
              color:${isSell ? '#051210' : 'rgba(45,212,191,0.40)'};
              font-weight:${isSell ? '700' : '400'}">SELL</span>
          <span onclick="setWareMode('${safeCode}','buy')" style="
              position:relative;z-index:1;cursor:pointer;
              display:flex;align-items:center;justify-content:center;
              font-family:'Share Tech Mono',monospace;font-size:7px;letter-spacing:0.06em;text-transform:uppercase;
              color:${!isSell ? '#051210' : 'rgba(45,212,191,0.40)'};
              font-weight:${!isSell ? '700' : '400'}">BUY</span>
        </div>
      </foreignObject>`;

    // Empty state: no data in this direction/window.
    // No SVG to host the foreignObject, so fall back to simple vertical HTML buttons.
    if (!filteredTrades.length) {
      return `<div style="display:flex;align-items:flex-start;gap:0.8rem;padding:0.2rem 0 0.4rem">
        <div style="display:flex;flex-direction:column;gap:0.2rem">
          <button class="cf-toggle-btn ${isSell ? 'active' : ''}" onclick="setWareMode('${safeCode}','sell')">Sell</button>
          <button class="cf-toggle-btn ${!isSell ? 'active' : ''}" onclick="setWareMode('${safeCode}','buy')">Buy</button>
        </div>
        <div style="padding:0.6rem 0;font-family:var(--font-data);font-size:1.1rem;color:var(--text-brand)">No ${isSell ? 'sell' : 'buy'} activity in this window</div>
      </div>`;
    }

    // Group by ware name, sort alphabetically for a stable rendering order.
    const byWare = {};
    filteredTrades.forEach(t => { (byWare[t.ware_name] = byWare[t.ware_name] || []).push(t); });
    const wareNames = Object.keys(byWare).sort();

    // Seed visibility defaults for any new wares not yet tracked for this station.
    if (!wareVisibility[safeCode]) wareVisibility[safeCode] = {};
    wareNames.forEach(w => {
      if (wareVisibility[safeCode][w] === undefined) wareVisibility[safeCode][w] = true;
    });

    const wareType = (cfChartType[safeCode] || {}).ware || 'step';
    const storeWare = []; // hover lookup table — one entry per trade dot
    const wareGroupHtml = [];

    // Process each ware: compute price band, build SVG paths, populate hover store.
    wareNames.forEach(wareName => {
      const col     = WARE_COLOURS[wareName] || CHART_LINE;
      // Normalise ware display name to the key used in WARE_PRICES, e.g. "Energy Cells" → "energycells"
      const wareKey = wareName.toLowerCase().replace(/\s+/g, '');
      const band    = warePrices[wareKey];

      // Sort trades oldest → newest (largest time_ago_s first).
      const wt = byWare[wareName].slice().sort((a, b) => b.time_ago_s - a.time_ago_s);

      // Price band: prefer static game data; fall back to observed min/max.
      let pMin, pAvg, pMax;
      if (band) {
        pMin = band.min; pAvg = band.average; pMax = band.max;
      } else {
        const ps = wt.map(t => t.price_cr);
        pMin = Math.min(...ps); pMax = Math.max(...ps);
        pAvg = (pMin + pMax) / 2;
      }
      const pRange = pMax - pMin || 1; // guard against zero-range

      // pMin → bottom (mt+ph), pMax → top (mt). Clamped to [0,1] for safety.
      const yOfP = p => mt + ph - Math.max(0, Math.min(1, (p - pMin) / pRange)) * ph;

      // Populate the hover store. fx/fy are normalised plot-area fractions [0–1].
      // dir is stored so the tooltip can show "Buyer" vs "Seller" for counterparty.
      wt.forEach(t => {
        const x = xOf(t.time_ago_s / 3600);
        const y = yOfP(t.price_cr);
        storeWare.push({
          fx: (x - ml) / pw, fy: (y - mt) / ph,
          vbx: +x.toFixed(1), vby: +y.toFixed(1),
          ware: wareName, colour: col, dir: curMode,
          price: t.price_cr, amount: t.amount,
          hAgo: t.time_ago_s / 3600,
          ship: t.ship_code || '', counterparty: t.counterparty || '',
          pMin, pAvg, pMax,
        });
      });

      // Build the SVG step path left-to-right (oldest = left, right edge = most recent).
      const pts = wt.map(t => ({ x: xOf(t.time_ago_s / 3600), y: yOfP(t.price_cr) }));
      let stepD = `M ${pts[0].x.toFixed(1)} ${pts[0].y.toFixed(1)}`;
      for (let i = 1; i < pts.length; i++) {
        stepD += ` H ${pts[i].x.toFixed(1)} V ${pts[i].y.toFixed(1)}`;
      }
      // Extend the last price level to the right edge of the visible window.
      stepD += ` H ${xOf(offsetHours).toFixed(1)}`;

      const bY    = (mt + ph).toFixed(1);
      const areaD = stepD + ` V ${bY} H ${pts[0].x.toFixed(1)} Z`;

      // Build the elements for this ware based on the selected display style.
      let wareElements;
      if (wareType === 'area') {
        // Filled silhouette only — step line and dots removed, opacity raised so
        // the shape is readable without the line to define its edges.
        wareElements = `<path d="${areaD}" fill="${col}" fill-opacity="0.35" stroke="none"/>`;
      } else if (wareType === 'scatter') {
        // Individual trade dots only — no step line, no area fill. Slightly
        // larger than line-mode dots so the points are clearly distinct.
        wareElements = pts.map(p =>
          `<circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="2.8" fill="${col}" opacity="0.90"/>`
        ).join('');
      } else {
        // Step (default): area fill + step path + dots (original render).
        wareElements = `
          <path d="${areaD}" fill="${col}" fill-opacity="0.10" stroke="none"/>
          <path d="${stepD}" fill="none" stroke="${col}" stroke-width="3"   stroke-linejoin="round" opacity="0.18"/>
          <path d="${stepD}" fill="none" stroke="${col}" stroke-width="1.5" stroke-linejoin="round"/>
          ${pts.map(p => `<circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="2" fill="${col}" opacity="0.85"/>`).join('')}`;
      }

      const groupId = `ware-group-${safeCode}-${wareKey}`;
      const visible = wareVisibility[safeCode][wareName];
      wareGroupHtml.push(`<g id="${groupId}" style="display:${visible ? 'block' : 'none'}">${wareElements}</g>`);
    });

    // Commit the lookup table so the mousemove handler can find it by safeCode.
    wareChartData[safeCode] = storeWare;

    // Y-axis: MIN / AVG / MAX reference lines — labels apply equally to all
    // wares since every line is normalised to its own band.
    const yMax = mt, yAvg = mt + ph / 2, yMin = mt + ph;
    const yAxisWare = `
      <line x1="${ml}" y1="${yMax.toFixed(1)}" x2="${(ml+pw).toFixed(1)}" y2="${yMax.toFixed(1)}" stroke="${CHART_ACCENT}" stroke-opacity="0.10" stroke-width="0.6"/>
      <line x1="${ml}" y1="${yAvg.toFixed(1)}" x2="${(ml+pw).toFixed(1)}" y2="${yAvg.toFixed(1)}" stroke="${CHART_ACCENT}" stroke-opacity="0.28" stroke-width="1" stroke-dasharray="4 3"/>
      <line x1="${ml}" y1="${yMin.toFixed(1)}" x2="${(ml+pw).toFixed(1)}" y2="${yMin.toFixed(1)}" stroke="${CHART_ACCENT}" stroke-opacity="0.10" stroke-width="0.6"/>
      <text x="${ml-6}" y="${yMax.toFixed(1)}" text-anchor="end" dominant-baseline="middle" fill="${CHART_LINE}" fill-opacity="0.70" style="font-family:var(--font-data);font-size:0.8rem">MAX</text>
      <text x="${ml-6}" y="${yAvg.toFixed(1)}" text-anchor="end" dominant-baseline="middle" fill="${CHART_LINE}" fill-opacity="0.90" style="font-family:var(--font-data);font-size:0.8rem">AVG</text>
      <text x="${ml-6}" y="${yMin.toFixed(1)}" text-anchor="end" dominant-baseline="middle" fill="${CHART_LINE}" fill-opacity="0.70" style="font-family:var(--font-data);font-size:0.8rem">MIN</text>`;

    // Legend chips — clicking toggles the ware line on/off.
    const chips = wareNames.map(wareName => {
      const col     = WARE_COLOURS[wareName] || CHART_LINE;
      const wareKey = wareName.toLowerCase().replace(/\s+/g, '');
      const on      = wareVisibility[safeCode][wareName];
      return `<span id="ware-chip-${safeCode}-${wareKey}"
                    onclick="toggleWare('${safeCode}','${wareName}')"
                    style="cursor:pointer;opacity:${on ? '1' : '0.35'};
                           display:inline-flex;align-items:center;
                           padding:0.2rem 0.7rem;border-radius:0.2rem;
                           border:1px solid ${col}44;background:${col}22;
                           color:${col};font-family:var(--font-data);
                           font-size:1rem;white-space:nowrap;letter-spacing:0.04em;
                           user-select:none">${wareName}</span>`;
    }).join('');

    return `
      <div style="background:#030d14;border:1px solid rgba(25,230,200,0.18);border-radius:0.3rem;box-shadow:inset 0 0 24px rgba(25,230,200,0.05);padding:0.4rem">
        <svg viewBox="0 0 ${svgW} ${svgH}" style="display:block;width:100%;height:auto">
          <defs>
            <clipPath id="cfclip-${safeCode}-w"><rect x="${ml}" y="${mt}" width="${pw}" height="${ph}"/></clipPath>
          </defs>
          <rect x="${ml}" y="${mt}" width="${pw}" height="${ph}" fill="#020a10"/>
          ${yAxisWare}
          ${xTicksHtml}
          <!-- Clipped like the hourly chart — see comment there. -->
          <g clip-path="url(#cfclip-${safeCode}-w)">
            ${wareGroupHtml.join('')}
          </g>
          <line x1="${ml}" y1="${mt}" x2="${ml}" y2="${mt+ph}" stroke="${CHART_ACCENT}" stroke-opacity="0.35" stroke-width="1"/>
          <text x="9" y="${mt + ph/2}" text-anchor="middle" dominant-baseline="middle" fill="${CHART_LINE}" fill-opacity="0.6"
                style="font-family:var(--font-data);font-size:0.8rem;letter-spacing:0.1em" transform="rotate(-90 9 ${mt + ph/2})">PRICE · BAND</text>
          <!-- Highlight ring — stroke colour set dynamically to match the hovered ware -->
          <circle class="cf-ware-marker" r="4" fill="none" stroke="#ffffff" stroke-width="1.5" style="display:none;pointer-events:none"/>
          <!-- Transparent overlay that captures mouse events for nearest-point hover -->
          <rect data-cfware="${safeCode}" x="${ml}" y="${mt}" width="${pw}" height="${ph}" fill="transparent" style="cursor:crosshair" onclick="cycleChart('${safeCode}','ware')"/>
          <!-- Chart-type pill — after the crosshair overlay so it sits above it in
               z-order and receives clicks first. Positioned top-right, clear of the
               SELL/BUY toggle (which is in the left margin). -->
          <g onclick="cycleChart('${safeCode}','ware')" style="cursor:pointer">
            <rect x="${(ml + pw - 44).toFixed(1)}" y="${(mt + 3).toFixed(1)}" width="42" height="13" rx="2"
                  fill="${CHART_ACCENT}10" stroke="${CHART_ACCENT}30" stroke-width="0.5"/>
            <text x="${(ml + pw - 4).toFixed(1)}" y="${(mt + 11).toFixed(1)}" text-anchor="end"
                  fill="${CHART_LINE}" fill-opacity="0.75"
                  style="font-family:var(--font-data);font-size:0.7rem;letter-spacing:0.08em">${wareType === 'area' ? 'AREA' : wareType === 'scatter' ? 'DOT' : 'STEP'} ›</text>
          </g>
          <!-- Sold/Bought toggle — must come after the hit rect in document order so
               it paints and receives clicks on top of the crosshair overlay. -->
          ${wareToggleFO}
        </svg>
      </div>
      <div style="display:flex;flex-wrap:wrap;gap:0.5rem;padding:0.6rem 0.2rem 0.2rem;will-change:transform">
        ${chips}
      </div>`;
  }

  // Switch the By-Ware chart between sold (Out) and bought (In) trades.
  // State persists per station; triggers a full bodies rebuild so the SVG and
  // chips update to reflect the selected direction.
  function setWareMode(safeCode, mode) {
    wareMode[safeCode] = mode;
    rebuildCfChart(safeCode);
    rebuildPie(safeCode);
  }

  // Toggle a single ware's line on/off in the By-Ware chart.
  // Updates both the SVG group visibility and the legend chip opacity.
  function toggleWare(safeCode, wareName) {
    const vis = wareVisibility[safeCode];
    if (!vis) return;
    vis[wareName] = !vis[wareName];
    const wareKey = wareName.toLowerCase().replace(/\s+/g, '');
    const group   = document.getElementById(`ware-group-${safeCode}-${wareKey}`);
    const chip    = document.getElementById(`ware-chip-${safeCode}-${wareKey}`);
    if (group) group.style.display   = vis[wareName] ? 'block' : 'none';
    if (chip)  chip.style.opacity    = vis[wareName] ? '1'     : '0.35';
  }

  function wareChartTipHtml(d) {
    // By-Ware hover: the ware, its exact price, where that price sits in
    // the game's min–avg–max band, the quantity, and the trade's counterparty.
    // d.dir ('sell'|'buy') controls the direction label and counterparty role.
    const fmtU = cfFmtU;
    const ago  = d.hAgo < 1
      ? Math.round(d.hAgo * 60) + 'm ago'
      : d.hAgo.toFixed(1).replace(/\.0$/, '') + 'h ago';

    // Express the price relative to the ware's average: +12% above or −5% below.
    const diff    = d.price - d.pAvg;
    const diffPct = d.pAvg > 0 ? Math.round(Math.abs(diff) / d.pAvg * 100) : 0;
    const diffCol = diff >= 0 ? CHART_ACCENT : CHART_LOSS;
    const diffStr = diff === 0
      ? 'at avg'
      : `${diff > 0 ? '+' : '−'}${diffPct}% vs avg`;

    const isRawId = s => /^\[?0x[0-9a-f]+\]?$/i.test(String(s).trim());
    const shipResolved = d.ship && !isRawId(d.ship);

    const row = cfRow;

    return `<div style="min-width:22rem;padding:0.2rem 0">
      <div style="display:flex;justify-content:space-between;align-items:baseline;gap:1.2rem;
                  margin-bottom:0.5rem;padding-bottom:0.4rem;border-bottom:1px solid var(--outline)">
        <span style="color:${d.colour};font-size:1.1rem;letter-spacing:0.05em;text-transform:uppercase;
                     white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:18rem">
          <span style="color:${d.dir === 'buy' ? CHART_LOSS : CHART_ACCENT}">${d.dir === 'buy' ? '▼ BOUGHT' : '▲ SOLD'}</span> ${d.ware}
        </span>
      </div>` +
      row('Price',      `${fmtU(d.price)} Cr`) +
      row('vs Average', diffStr, diffCol) +
      row('Band',       `${fmtU(d.pMin)} – ${fmtU(d.pMax)} Cr`) +
      row('Amount',     `${fmtU(d.amount)} units`) +
      (d.counterparty ? row(d.dir === 'buy' ? 'Seller' : 'Buyer', d.counterparty) : '') +
      (shipResolved   ? row('Ship',  d.ship)         : '') +
      `<div style="margin-top:0.5rem;padding-top:0.4rem;border-top:1px solid var(--outline);
                   text-align:right;font-size:1rem;color:var(--text-brand)">${ago}</div>
    </div>`;
  }

  registerTip('cfware', (el, e, tip) => {
    // By-Ware chart: find the nearest visible trade dot by Euclidean distance so
    // the cursor naturally locks on to whichever ware line it is closest to.
    const sc  = el.dataset.cfware;
    const arr = wareChartData[sc];
    if (!arr || !arr.length) return false;
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
    if (!best) return false;
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
    return true;
  });
