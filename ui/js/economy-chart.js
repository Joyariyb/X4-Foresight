  // Core role: Renders station budget or trade-data as an interactive donut/pie chart with per-ware slices.
  // Two modes per station, toggled by the cycle pill in the donut centre:
  //   budget — the reverse-engineered supply budget (default, unchanged)
  //   graph  — actual 24-h trade credits per ware, filtered to match the cashflow chart's
  //            active sell/buy direction (or both if no direction toggle is active there)

  const pieModeByStation = {}; // 'budget' | 'graph'
  const pieCacheByStation = {}; // { bud, allTrades, stationCode } — stored for rebuilds

  // Returns 'sell', 'buy', or 'both' based on the cashflow chart's currently active mode
  // and its direction toggle. Called at rebuild time so it always reflects the live chart state.
  function getPieDirection(safeCode) {
    const sec = document.getElementById('cf-' + safeCode);
    const activeBtn = sec && sec.querySelector('.cf-toggle-btn.active');
    const cfMode = activeBtn ? activeBtn.dataset.mode : null;
    if (cfMode === 'ware')     return wareMode[safeCode]  || 'sell';
    if (cfMode === 'avgprice') return avgMode[safeCode]   || 'sell';
    if (cfMode === 'byship')   return shipMode[safeCode]  || 'sell';
    return 'both'; // Hourly, By Trade, or no cashflow chart — no direction preference
  }

  // Aggregates allTrades into per-key credit totals for the graph-mode pie.
  // Groups by ship when the cashflow chart is in By Ship mode, by ware otherwise.
  function buildGraphPieLines(safeCode) {
    const { allTrades, stationCode } = pieCacheByStation[safeCode] || {};
    if (!allTrades) return [];
    const dir = getPieDirection(safeCode);
    const dirFilter = dir === 'sell' ? 'Out' : dir === 'buy' ? 'In' : null;
    // Mirror the cashflow chart's zoom window so the pie and chart always show
    // the same time slice. Falls back to full 24h if no zoom state is set yet.
    const { hours: windowHours = 24, offsetHours = 0 } = cfZoom[safeCode] || {};

    // Match the cashflow chart's active tab to decide what to group by.
    const sec = document.getElementById('cf-' + safeCode);
    const activeBtn = sec && sec.querySelector('.cf-toggle-btn.active');
    const cfMode = activeBtn ? activeBtn.dataset.mode : null;
    const groupByShip = cfMode === 'byship';
    // Raw hex IDs are anonymous ships the game hasn't named yet — skip them,
    // same as the By Ship chart does.
    const isRawId = s => /^\[?0x[0-9a-f]+\]?$/i.test(String(s || '').trim());

    const byKey = {};
    allTrades.forEach(t => {
      if (t.station_code !== stationCode) return;
      const hAgo = t.time_ago_s / 3600;
      if (hAgo < offsetHours || hAgo >= offsetHours + windowHours) return;
      if (dirFilter && t.direction !== dirFilter) return;
      let key;
      if (groupByShip) {
        if (!t.ship_code || isRawId(t.ship_code)) return;
        // Only include ships from the faction currently selected in the By Ship chart.
        if (shipFactionFilter[safeCode] && t.ship_owner_id !== shipFactionFilter[safeCode]) return;
        if ((shipVisibility[safeCode] || {})[t.ship_code] === false) return;
        key = t.ship_code;
      } else {
        key = t.ware_name || 'Unknown';
      }
      byKey[key] = (byKey[key] || 0) + (t.total_cr || 0);
    });

    const entries = Object.entries(byKey)
      .filter(([, v]) => v > 0)
      .sort((a, b) => b[1] - a[1]);

    if (groupByShip) {
      // Reuse the stable colour assignments from the cashflow chart so each ship
      // always gets the same colour in both the line chart and the pie.
      const colours = shipColourMap[safeCode] || {};
      const faction = shipFactionFilter[safeCode] || null;
      return entries.map(([name, value]) => ({
        ware_name: name,
        value,
        colour: colours[name] || null,
        // Carried through so the slice onclick can call jumpToShip(code, faction).
        faction,
      }));
    }

    return entries.map(([ware_name, value]) => ({ ware_name, value }));
  }

  // Ghost donut shown when graph mode has no trade data in the 24-h window.
  function graphPieEmptyState(safeCode) {
    const cx = 150, cy = 150, r = 92, hole = r * 0.5;
    // A thick dashed stroke on a circle halfway through the ring band creates the
    // same visual footprint as the filled slices, but hollow and dimmed.
    const ringMid = Math.round((r + hole) / 2); // 69
    const ringW   = r - hole;                   // 46 — fills the full slice band
    return `
      <div style="padding:1rem 0.6rem 1.6rem">
        <svg viewBox="-55 -25 410 350" style="width:100%;height:auto" overflow="visible">
          <circle cx="${cx}" cy="${cy}" r="${ringMid}" fill="none"
                  stroke="var(--border)" stroke-width="${ringW}" stroke-dasharray="14 8" opacity="0.6"/>
          <circle cx="${cx}" cy="${cy}" r="${hole}" fill="var(--bg-card)"/>
          <!-- Pill stays clickable so the user can flip back to budget -->
          <g onclick="setPieMode('${safeCode}')" style="cursor:pointer">
            <rect x="${cx - 30}" y="${cy - 14}" width="60" height="12" rx="2"
                  fill="#19e6c810" stroke="#19e6c830" stroke-width="0.5"/>
            <text x="${cx}" y="${cy - 5}" text-anchor="middle" fill="#5fe9d4" fill-opacity="0.8"
                  font-size="9" style="font-family:var(--font-mono);letter-spacing:0.08em;text-transform:uppercase">GRAPH ›</text>
          </g>
          <text x="${cx}" y="${cy + 8}" text-anchor="middle" fill="var(--text-dim)"
                font-size="9" style="font-family:var(--font-mono);letter-spacing:0.1em;text-transform:uppercase">No trades</text>
          <text x="${cx}" y="${cy + 20}" text-anchor="middle" fill="var(--text-dim)"
                font-size="7.5" style="font-family:var(--font-mono);opacity:0.55">last 24 h</text>
        </svg>
      </div>`;
  }

  // Toggle between budget and graph modes for one station's pie, then rebuild it.
  function setPieMode(safeCode) {
    pieModeByStation[safeCode] = pieModeByStation[safeCode] === 'graph' ? 'budget' : 'graph';
    const el = document.getElementById('pie-' + safeCode);
    if (!el || !pieCacheByStation[safeCode]) return;
    const { bud, allTrades, stationCode } = pieCacheByStation[safeCode];
    el.innerHTML = economyPieSvg(bud, allTrades, safeCode, stationCode);
  }

  // Rebuild the pie in place when the cashflow chart's direction changes.
  // Only fires in graph mode — budget pie doesn't depend on cashflow state.
  function rebuildPie(safeCode) {
    if ((pieModeByStation[safeCode] || 'budget') !== 'graph') return;
    const el = document.getElementById('pie-' + safeCode);
    if (!el || !pieCacheByStation[safeCode]) return;
    const { bud, allTrades, stationCode } = pieCacheByStation[safeCode];
    el.innerHTML = economyPieSvg(bud, allTrades, safeCode, stationCode);
  }

  function economyPieSvg(bud, allTrades, safeCode, stationCode) {
    // Store for rebuildPie / setPieMode so they can re-render without re-scanning.
    pieCacheByStation[safeCode] = { bud, allTrades: allTrades || [], stationCode };

    const mode = pieModeByStation[safeCode] || 'budget';

    // ── Select data source ────────────────────────────────────────────────────
    let lines, displayTotal;
    if (mode === 'graph') {
      const graphLines = buildGraphPieLines(safeCode);
      if (!graphLines.length) return graphPieEmptyState(safeCode);
      lines = graphLines;
      displayTotal = lines.reduce((s, l) => s + l.value, 0);
    } else {
      // Budget mode — data and rendering identical to the original.
      lines = (bud.lines || []).filter(l => l.value > 0)
                .slice().sort((a, b) => b.value - a.value);
      const pieSum = lines.reduce((sum, l) => sum + l.value, 0);
      if (!lines.length || pieSum <= 0) {
        return `<div style="padding:2.4rem 1.4rem;text-align:center;font-family:var(--font-mono);font-size:1.1rem;color:var(--text-faint)">No budget to chart</div>`;
      }
      // bud.total is the pre-computed scanner sum; prefer it so the displayed
      // figure stays consistent with the budget table even if some lines were filtered.
      displayTotal = bud.total;
    }

    // ── Geometry ──────────────────────────────────────────────────────────────
    const cx = 150, cy = 150, r = 92, labelR = r + 14;
    const lift = 7; // px a slice translates outward on hover (also sizes the sheen)
    const polar = (cxx, cyy, rad, deg) => {
      const a = (deg - 90) * Math.PI / 180; // -90 so 0° starts at the top
      return [cxx + rad * Math.cos(a), cyy + rad * Math.sin(a)];
    };

    const pieTotal = lines.reduce((sum, l) => sum + l.value, 0);

    let angle = 0;
    const slices = [];
    const labels = [];
    lines.forEach(ln => {
      const frac  = ln.value / pieTotal;
      const start = angle;
      const end   = angle + frac * 360;
      angle = end;
      const mid   = (start + end) / 2;
      // Ships carry a pre-assigned colour from shipColourMap; wares look up WARE_COLOURS.
      const col   = ln.colour || WARE_COLOURS[ln.ware_name] || 'var(--text-dim)';

      // Slice path. A single full-circle ware would degenerate the arc, so draw
      // it as a complete circle instead of a zero-length wedge.
      let path;
      if (frac >= 0.999) {
        path = `M ${cx} ${cy - r} A ${r} ${r} 0 1 1 ${cx - 0.01} ${cy - r} Z`;
      } else {
        const [x1, y1] = polar(cx, cy, r, start);
        const [x2, y2] = polar(cx, cy, r, end);
        const largeArc = (end - start) > 180 ? 1 : 0;
        path = `M ${cx} ${cy} L ${x1.toFixed(2)} ${y1.toFixed(2)} A ${r} ${r} 0 ${largeArc} 1 ${x2.toFixed(2)} ${y2.toFixed(2)} Z`;
      }

      const pct = (frac * 100).toFixed(1);
      // Graph mode tooltip only carries what's actually known (value + share).
      // Budget mode tooltip carries the full per-ware breakdown as before.
      const tipData = mode === 'graph'
        ? { ware: ln.ware_name, value: ln.value, pct, colour: col, mode: 'graph' }
        : { ware: ln.ware_name, amount: ln.amount, price: ln.price, value: ln.value, basis: ln.basis, pct, colour: col };
      const tip = encodeURIComponent(JSON.stringify(tipData));
      // Per-slice outward unit vector along the mid-angle, exposed as CSS vars so
      // the :hover rule can lift the slice toward the viewer for a 3D "pop".
      const [ux, uy] = polar(0, 0, 1, mid);
      // Ship slices (graph mode + byship) are clickable — they jump to that ship
      // in the Fleet tab. ln.faction is only set in that case.
      const shipClick = ln.faction
        ? ` onclick="jumpToShip('${ln.ware_name}','${ln.faction}')" style="--dx:${(ux*lift).toFixed(2)}px;--dy:${(uy*lift).toFixed(2)}px;cursor:pointer"`
        : ` style="--dx:${(ux*lift).toFixed(2)}px;--dy:${(uy*lift).toFixed(2)}px"`;
      slices.push(
        `<path class="pie-slice" d="${path}" fill="${col}" stroke="var(--bg-card)" stroke-width="1.5"
               ${shipClick} data-budget-tip="${tip}"></path>`
      );

      // Radial label, rotated to the slice mid-angle and flipped on the left side.
      const [lx, ly] = polar(cx, cy, labelR, mid);
      const onLeft   = mid > 180;
      const rot      = onLeft ? mid + 180 : mid; // keep upright
      const anchor   = onLeft ? 'end' : 'start';
      // Hide labels for very thin slices to avoid overlap clutter.
      if (frac >= 0.03) {
        // Wrap multi-word ware names onto stacked lines (no abbreviation) so each
        // spoke stays short. Lines are vertically centred on the label anchor.
        const words = ln.ware_name.split(' ');
        const lh    = 12; // line height in SVG units, ~matches the 12px font
        const y0    = ly - ((words.length - 1) * lh) / 2;
        const tspans = words.map((w, i) =>
          `<tspan x="${lx.toFixed(2)}" y="${(y0 + i * lh).toFixed(2)}">${w}</tspan>`
        ).join('');
        labels.push(
          `<text class="pie-label" fill="${col}"
                 text-anchor="${anchor}" dominant-baseline="middle"
                 transform="rotate(${(rot - 90).toFixed(2)} ${lx.toFixed(2)} ${ly.toFixed(2)})">${tspans}</text>`
        );
      }
    });

    // Centre hole + total label make it a donut and give the figures a home.
    const hole = r * 0.5;
    const pillLabel = mode === 'budget' ? 'BUDGET ›' : 'GRAPH ›';

    return `
      <div style="padding:1rem 0.6rem 1.6rem">
        <svg viewBox="-55 -25 410 350" style="width:100%;height:auto" overflow="visible">
          <defs>
            <radialGradient id="pieSheen" cx="0.36" cy="0.30" r="0.75">
              <stop offset="0%"   stop-color="#fff" stop-opacity="0.42"/>
              <stop offset="42%"  stop-color="#fff" stop-opacity="0.06"/>
              <stop offset="62%"  stop-color="#000" stop-opacity="0"/>
              <stop offset="100%" stop-color="#000" stop-opacity="0.42"/>
            </radialGradient>
            <radialGradient id="pieHole" cx="0.5" cy="0.5" r="0.5">
              <stop offset="60%"  stop-color="#000" stop-opacity="0"/>
              <stop offset="100%" stop-color="#000" stop-opacity="0.55"/>
            </radialGradient>
          </defs>
          <g class="pie-ring">${slices.join('')}</g>
          <!-- Spherical sheen sits above the slices but ignores pointer events
               so slice hover/tooltip still works through it. Radius is r + the
               hover lift so a lifted slice's rim stays under the sheen (otherwise
               the protruding crescent escapes the rim shading and looks bright). -->
          <circle cx="${cx}" cy="${cy}" r="${r + lift}" fill="url(#pieSheen)" style="pointer-events:none"></circle>
          <circle cx="${cx}" cy="${cy}" r="${hole}" fill="var(--bg-card)"></circle>
          <!-- Inner-edge shadow gives the centre hole apparent depth. -->
          <circle cx="${cx}" cy="${cy}" r="${hole}" fill="url(#pieHole)" style="pointer-events:none"></circle>
          <!-- Cycle pill replaces the static "Budget" label at the same centre position.
               Clicking cycles BUDGET → GRAPH → BUDGET for this station only. -->
          <g onclick="setPieMode('${safeCode}')" style="cursor:pointer">
            <rect x="${cx - 30}" y="${cy - 14}" width="60" height="12" rx="2"
                  fill="#19e6c810" stroke="#19e6c830" stroke-width="0.5"/>
            <text x="${cx}" y="${cy - 5}" text-anchor="middle" fill="#5fe9d4" fill-opacity="0.8"
                  font-size="9" style="font-family:var(--font-mono);letter-spacing:0.08em;text-transform:uppercase">${pillLabel}</text>
          </g>
          <text x="${cx}" y="${cy + 12}" text-anchor="middle" fill="var(--lime)"
                font-size="15" style="font-family:var(--font-mono)">${Math.round(displayTotal).toLocaleString()}</text>
          ${labels.join('')}
        </svg>
      </div>`;
  }
