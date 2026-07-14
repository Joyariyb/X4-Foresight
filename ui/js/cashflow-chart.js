  // Core role: Station cash-flow chart shell — shared state, zoom/scrubber, mode switching, and the layout context for the per-panel builders (cashflow-hourly/ware/ship/avgprice.js).
  //
  // Measured directly from recorded trades (account balance and inventory can't be reconstructed from a save snapshot).
  // Static min/avg/max price band per ware — assigned by populate.js when save
  // data loads, read by the By-Ware panel (cashflow-ware.js).
  let warePrices = {};

  const CF_MIN_HOURS = 3, CF_MAX_HOURS = 24;
  const cfZoom = {}; // Persists across tab switches
  const cfStationCache = {}; // Reuse on scrubber drag (avoid recomputation)

  // Registers this chart's zoom store with the generic scrubber drag handler
  // in tooltips.js (see SCRUBBER_KINDS in tip-registry.js) — rebuildCfChart is
  // a hoisted function declaration, so referencing it here before its later
  // definition in this file is fine.
  registerScrubber('cf', { zoom: cfZoom, minHours: CF_MIN_HOURS, maxHours: CF_MAX_HOURS, onChange: rebuildCfChart });

  // Which visual style is active for each station's chart panels.
  // Keys and allowed values per panel are listed in CHART_CYCLES below.
  const cfChartType = {};
  const cfNiceStep = (range, target) => {
    const raw  = Math.max(range, 1) / target;
    const mag  = Math.pow(10, Math.floor(Math.log10(raw)));
    const norm = raw / mag;
    const nice = norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 2.5 ? 2.5 : norm <= 5 ? 5 : 10;
    return nice * mag;
  };
  const cfFmtY = v => {
    const a = Math.abs(v);
    return a >= 1e6 ? (v / 1e6).toFixed(a % 1e6 ? 1 : 0) + 'M'
         : a >= 1e3 ? (v / 1e3).toFixed(a % 1e3 ? 1 : 0) + 'k'
         : String(v);
  };
  const cfFmtCr = n => (n < 0 ? '−' : '+') + Math.abs(Math.round(n)).toLocaleString() + ' cr';

  // Station data cached so rebuildCfChart() can regenerate without recomputing.
  function goodsChartSvg(station, allTrades) {
    const safeCode = station.code.replace(/[^a-z0-9]/gi, '');

    cfStationCache[safeCode] = { station, allTrades };
    if (!cfZoom[safeCode]) cfZoom[safeCode] = { hours: CF_MAX_HOURS, offsetHours: 0 };

    // Net 24H total for the header — always over the full 24H window regardless
    // of zoom so the readout stays stable as the user pans or resizes.
    const allStation = allTrades.filter(t =>
      t.station_code === station.code && t.time_ago_s / 3600 < CF_MAX_HOURS);
    if (!allStation.length) {
      return `<div class="econ-graph" style="padding:1.6rem 1.4rem;font-family:var(--font-data);font-size:1.1rem;color:var(--text-brand)">No trade activity in the last 24h</div>`;
    }
    const net24 = allStation.reduce((s, t) =>
      s + (t.direction === 'Out' ? 1 : -1) * (t.total_cr || 0), 0);

    return `
      <div id="cf-${safeCode}" class="econ-graph">
        <div style="display:flex;align-items:center;justify-content:space-between;gap:1.25cqw;margin-bottom:0.625cqw">
          <div style="display:flex;align-items:center;gap:0.9375cqw;min-width:0">
            <span style="font-family:var(--font-data);font-size:1.25cqw;letter-spacing:0.18em;color:${CHART_LINE};text-transform:uppercase;white-space:nowrap">Cash Flow</span>
            <button class="cf-toggle-btn active" data-mode="hourly"   onclick="setCashflowMode('${safeCode}','hourly')">Hourly</button>
            <button class="cf-toggle-btn"        data-mode="trade"    onclick="setCashflowMode('${safeCode}','trade')">By Trade</button>
            <button class="cf-toggle-btn"        data-mode="ware"     onclick="setCashflowMode('${safeCode}','ware')">By Ware</button>
            <button class="cf-toggle-btn"        data-mode="avgprice" onclick="setCashflowMode('${safeCode}','avgprice')">Avg Price</button>
            <button class="cf-toggle-btn"        data-mode="byship"   onclick="setCashflowMode('${safeCode}','byship')">By Ship</button>
          </div>
          <span style="font-family:var(--font-data);font-size:1.5625cqw;color:${net24 >= 0 ? CHART_ACCENT : CHART_LOSS};white-space:nowrap">${cfFmtCr(net24)}</span>
        </div>
        <!-- Bodies split in two:
             • cf-avg — the Avg Price chart, built ONCE then mutated in place so
               its bars can CSS-transition between values (a fresh innerHTML each
               scrubber frame can't animate from a prior state). Placed first so
               the shared scrubber (which lives in the volatile part) still sits
               below the chart in every mode.
             • cf-volatile — hourly/trade/ware + scrubber, fully rebuilt on every
               scrubber drag. -->
        <div id="cf-bodies-${safeCode}">
          <div id="cf-avg-${safeCode}" data-cfmode="avgprice" style="display:none">${buildAvgPriceBody(safeCode)}</div>
          <div id="cf-volatile-${safeCode}">${buildCfBodiesHtml(safeCode)}</div>
        </div>
      </div>`;
  }

  // Build only the volatile chart-mode divs + scrubber for one station.
  // Called by goodsChartSvg() on first render and by rebuildCfChart() whenever
  // the scrubber changes the zoom window.
  // Requires cfStationCache[safeCode] and cfZoom[safeCode] to be set first.
  function buildCfBodiesHtml(safeCode) {
    const { station, allTrades } = cfStationCache[safeCode];
    const { hours: windowHours, offsetHours } = cfZoom[safeCode];
    // numHours = hourly buckets needed to cover the window (ceil covers partial hours).
    const numHours = Math.ceil(windowHours);

    // Shared SVG layout constants — same viewBox as always; scales to flex column width.
    const svgW = 560, svgH = 320;
    const ml = 56, mr = 14, mt = 12, mb = 30;
    const pw = svgW - ml - mr, ph = svgH - mt - mb;

    // Maps hours-ago to SVG X coordinate within the current zoom window.
    // h = offsetHours            → right edge (x = ml+pw, the "recent" side)
    // h = offsetHours+windowHours → left edge  (x = ml,   the "oldest" side)
    const xOf = h => ml + (offsetHours + windowHours - h) / windowHours * pw;

    // Filter trades to the visible window for this station.
    const trades = allTrades.filter(t => {
      const hAgo = t.time_ago_s / 3600;
      return t.station_code === station.code &&
             hAgo >= offsetHours &&
             hAgo < offsetHours + windowHours;
    });

    // X-axis tick interval adapts to window size so labels never crowd.
    const tickStep = windowHours <= 3 ? 0.5 : windowHours <= 6 ? 1 : windowHours <= 12 ? 2 : 6;
    const xTicksHtml = (() => {
      const out = [];
      // First tick at or after the left (oldest) edge of the window.
      const first = Math.ceil(offsetHours / tickStep) * tickStep;
      for (let h = first; h <= offsetHours + windowHours + 0.001; h += tickStep) {
        const x = xOf(h).toFixed(1);
        const label = h === 0 ? 'NOW'
          : h < 1  ? `-${Math.round(h * 60)}M`
          : `-${h % 1 !== 0 ? h.toFixed(1) : Math.round(h)}H`;
        out.push(`<line x1="${x}" y1="${mt}" x2="${x}" y2="${mt + ph}" stroke="${CHART_ACCENT}" stroke-opacity="0.08" stroke-width="0.6"/>
          <text x="${x}" y="${mt + ph + 13}" text-anchor="middle" fill="${CHART_LINE}" fill-opacity="0.7"
                style="font-family:var(--font-data);font-size:0.8rem;letter-spacing:0.06em">${label}</text>`);
      }
      return out.join('');
    })();

    // Reusable y-axis (grid lines + credit labels) for any axis range.
    const yAxisHtml = (yOf, axBot, axTop, step) => {
      const ticks = [];
      for (let v = axBot; v <= axTop + 0.5; v += step) ticks.push(v);
      const grid = ticks.map(v => {
        const y = yOf(v).toFixed(1), isZero = Math.abs(v) < step * 0.001;
        return `<line x1="${ml}" y1="${y}" x2="${ml + pw}" y2="${y}"
                      stroke="${CHART_ACCENT}" stroke-opacity="${isZero ? 0.35 : 0.10}" stroke-width="${isZero ? 1 : 0.6}"/>`;
      }).join('');
      const labels = ticks.map(v => {
        const y = yOf(v).toFixed(1);
        return `<text x="${ml - 6}" y="${y}" text-anchor="end" dominant-baseline="middle"
                      fill="${CHART_LINE}" fill-opacity="0.7" style="font-family:var(--font-data);font-size:0.8rem">${cfFmtY(v)}</text>`;
      }).join('');
      return grid + labels;
    };

    // If the zoom window contains no trades show a lightweight empty state for
    // every volatile mode so the scrubber remains visible and interactive.
    if (!trades.length) {
      const empty = `<div style="padding:1.6rem 1.4rem;font-family:var(--font-data);font-size:1.1rem;color:var(--text-brand)">No trades in this window</div>`;
      return `
        <div data-cfmode="hourly"  style="display:block">${empty}</div>
        <div data-cfmode="trade"   style="display:none">${empty}</div>
        <div data-cfmode="ware"    style="display:none">${empty}</div>
        <div data-cfmode="byship"  style="display:none">${empty}</div>
        ${buildScrubberHtml(safeCode)}`;
    }

    // Shared layout context handed to the per-panel body builders
    // (cashflow-hourly.js, cashflow-ware.js, cashflow-ship.js). One place
    // computes the window filter and axis helpers so every panel stays
    // geometrically in sync with the scrubber.
    const ctx = { safeCode, station, allTrades, trades, windowHours, offsetHours,
                  numHours, svgW, svgH, ml, mt, pw, ph, xOf, xTicksHtml, yAxisHtml };

    return `
      <div data-cfmode="hourly" style="display:block">${buildCfHourlyBody(ctx)}</div>
      <div data-cfmode="trade"  style="display:none">${buildCfTradeBody(ctx)}</div>
      <div data-cfmode="ware"   style="display:none">${buildCfWareBody(ctx)}</div>
      <div data-cfmode="byship" style="display:none">${buildCfShipBody(ctx)}</div>
      ${buildScrubberHtml(safeCode)}`;
  }

  // Build the scrubber track HTML for one station's zoom control.
  // Track left = 24H ago, track right = NOW.
  // Handle left % = (24 - offsetHours - hours) / 24 × 100
  // Handle width % = hours / 24 × 100
  function buildScrubberHtml(safeCode) {
    const { hours, offsetHours } = cfZoom[safeCode] || { hours: CF_MAX_HOURS, offsetHours: 0 };
    const hLeft  = ((CF_MAX_HOURS - offsetHours - hours) / CF_MAX_HOURS * 100).toFixed(2);
    const hWidth = (hours / CF_MAX_HOURS * 100).toFixed(2);
    return `<div class="cf-scrubber-track" data-scrubber="${safeCode}" data-scrubber-kind="cf">
      <div class="cf-scrubber-handle" style="left:${hLeft}%;width:${hWidth}%">
        <div class="cf-scrubber-resize" data-side="left"></div>
        <div class="cf-scrubber-resize" data-side="right"></div>
      </div>
      <span class="cf-scrubber-label" style="left:1.5rem">-24H</span>
      <span class="cf-scrubber-label" style="left:50%;transform:translate(-50%,-50%)">◄ DRAG · EDGES RESIZE ►</span>
      <span class="cf-scrubber-label" style="right:1.5rem">NOW</span>
    </div>`;
  }

  // Replace the bodies container of one station's cash-flow section with a
  // freshly built version at the current zoom window, then restore the active
  // chart tab. Called by the scrubber drag handler on every cfZoom change.
  function rebuildCfChart(safeCode) {
    if (!cfStationCache[safeCode]) return;
    const volatileEl = document.getElementById('cf-volatile-' + safeCode);
    if (!volatileEl) return;
    // Read the active mode from the toggle buttons BEFORE touching the DOM.
    const sec = document.getElementById('cf-' + safeCode);
    const activeBtn = sec && sec.querySelector('.cf-toggle-btn.active');
    const activeMode = activeBtn ? activeBtn.dataset.mode : 'hourly';
    // Only the volatile bodies are recreated. The Avg Price chart persists and
    // is retargeted in place so its bars animate (see cashflow-avgprice.js).
    volatileEl.innerHTML = buildCfBodiesHtml(safeCode);
    updateAvgPrice(safeCode);
    setCashflowMode(safeCode, activeMode);
  }

  // Switch which cash-flow panel (hourly/trade/ware/avgprice/byship) is visible for one station.
  function setCashflowMode(code, mode) {
    const sec = document.getElementById('cf-' + code);
    if (!sec) return;
    sec.querySelectorAll('[data-cfmode]').forEach(el => {
      el.style.display = el.dataset.cfmode === mode ? 'block' : 'none';
    });
    sec.querySelectorAll('.cf-toggle-btn').forEach(b => {
      b.classList.toggle('active', b.dataset.mode === mode);
    });
    // Avg Price is built empty and filled on first view (it isn't part of the
    // volatile rebuild, so nothing populates it until we ask here).
    if (mode === 'avgprice') updateAvgPrice(code);
    // Graph-mode pie tracks which chart tab is active (determines sell/buy/both).
    rebuildPie(code);
  }

  // Available display types per chart panel. Clicking cycles forward through the list.
  const CHART_CYCLES = {
    hourly: ['line', 'bar',  'scatter'],
    trade:  ['line', 'scatter'],
    ware:   ['step', 'area', 'scatter'],
    avg:    ['bar',  'line', 'scatter'],
    byship: ['line', 'scatter'],
  };

  // Single entry point for chart-type cycling across all four panels.
  // The avg panel mutates in place (no volatile rebuild), so it takes its own
  // path; the other three trigger a full volatile rebuild which re-reads cfChartType.
  function cycleChart(safeCode, panel) {
    if (!cfChartType[safeCode]) cfChartType[safeCode] = {};
    const types = CHART_CYCLES[panel];
    const cur = cfChartType[safeCode][panel] || types[0];
    cfChartType[safeCode][panel] = types[(types.indexOf(cur) + 1) % types.length];
    if (panel === 'avg') updateAvgPrice(safeCode);
    else rebuildCfChart(safeCode);
  }

  // ── Shared tooltip helpers ────────────────────────────────────────────────
  // The cashflow tooltip builders + registrations live in the per-panel files
  // (cashflow-hourly.js, cashflow-ware.js, cashflow-ship.js,
  // cashflow-avgprice.js), next to the feature that stamps each data-*
  // attribute. These two helpers are shared by several builders, so they stay
  // here in the shell. See tip-registry.js for the handler contract.
  const cfFmtU = n => Math.round(n).toLocaleString();
  const cfRow = (label, value, colour) => `
      <div style="display:flex;justify-content:space-between;gap:1.2rem;padding:1px 0">
        <span style="color:var(--text-brand);font-size:1rem">${label}</span>
        <span style="color:${colour || 'var(--text-secondary)'};font-family:var(--font-data);font-size:1rem;text-align:right">${value}</span>
      </div>`;

  // Clear every cashflow highlight (markers, bar highlight, readout line) at the
  // start of each move; the hovered chart re-shows its own below.
  onTipReset(() => {
    document.querySelectorAll('.cf-detail-marker,.cf-ware-marker,.cf-ship-marker').forEach(m => { m.style.display = 'none'; });
    document.querySelectorAll('.avg-bars rect.avg-hot').forEach(r => r.classList.remove('avg-hot'));
    document.querySelectorAll('.avg-hot-line').forEach(l => { l.style.opacity = '0'; });
  });
