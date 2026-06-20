  // Core role: Plots station trade cash flow over 24 hours with two modes (hourly net per-ware, or cumulative by-trade) and zoom/scrubber navigation.
  //
  // Measured directly from recorded trades (account balance and inventory can't be reconstructed from a save snapshot).
  const HOURS = 24;
  const cashflowDetailData = {};
  let warePrices = {};
  const wareVisibility = {};
  const wareChartData = {};

  const CF_MIN_HOURS = 3, CF_MAX_HOURS = 24;
  const cfZoom = {}; // Persists across tab switches
  const cfStationCache = {}; // Reuse on scrubber drag (avoid recomputation)
  let cfScrubDrag = null;
  const wareMode = {};

  const avgWare = {};
  const avgMode = {};
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
      return `<div style="flex:1 1 360px;min-width:320px;padding:16px 14px;font-family:var(--font-mono);font-size:11px;color:var(--text-faint)">No trade activity in the last 24h</div>`;
    }
    const net24 = allStation.reduce((s, t) =>
      s + (t.direction === 'Out' ? 1 : -1) * (t.total_cr || 0), 0);

    return `
      <div id="cf-${safeCode}" style="flex:1 1 360px;min-width:320px;display:flex;flex-direction:column">
        <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:4px">
          <div style="display:flex;align-items:center;gap:6px;min-width:0">
            <span style="font-family:var(--font-mono);font-size:8px;letter-spacing:0.18em;color:#5fe9d4;text-transform:uppercase;white-space:nowrap">Cash Flow</span>
            <button class="cf-toggle-btn active" data-mode="hourly"   onclick="setCashflowMode('${safeCode}','hourly')">Hourly</button>
            <button class="cf-toggle-btn"        data-mode="trade"    onclick="setCashflowMode('${safeCode}','trade')">By Trade</button>
            <button class="cf-toggle-btn"        data-mode="ware"     onclick="setCashflowMode('${safeCode}','ware')">By Ware</button>
            <button class="cf-toggle-btn"        data-mode="avgprice" onclick="setCashflowMode('${safeCode}','avgprice')">Avg Price</button>
          </div>
          <span style="font-family:var(--font-mono);font-size:10px;color:${net24 >= 0 ? '#19e6c8' : '#ef5350'};white-space:nowrap">${cfFmtCr(net24)}</span>
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

  // Build only the three chart-mode divs + scrubber for one station.
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
        out.push(`<line x1="${x}" y1="${mt}" x2="${x}" y2="${mt + ph}" stroke="#19e6c8" stroke-opacity="0.08" stroke-width="0.6"/>
          <text x="${x}" y="${mt + ph + 13}" text-anchor="middle" fill="#5fe9d4" fill-opacity="0.7"
                style="font-family:var(--font-mono);font-size:8px;letter-spacing:0.06em">${label}</text>`);
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
                      stroke="#19e6c8" stroke-opacity="${isZero ? 0.35 : 0.10}" stroke-width="${isZero ? 1 : 0.6}"/>`;
      }).join('');
      const labels = ticks.map(v => {
        const y = yOf(v).toFixed(1);
        return `<text x="${ml - 6}" y="${y}" text-anchor="end" dominant-baseline="middle"
                      fill="#5fe9d4" fill-opacity="0.7" style="font-family:var(--font-mono);font-size:8px">${cfFmtY(v)}</text>`;
      }).join('');
      return grid + labels;
    };

    // Hourly net buckets. Bucket index 0 = most recent hour of the window.
    const net    = new Array(numHours).fill(0);
    const detail = Array.from({ length: numHours }, () => ({}));
    trades.forEach(t => {
      const i = Math.floor(t.time_ago_s / 3600 - offsetHours);
      if (i < 0 || i >= numHours) return;
      const cr = t.total_cr || 0;
      net[i] += (t.direction === 'Out' ? 1 : -1) * cr;
      const w = t.ware_name || 'Unknown';
      const d = detail[i][w] || (detail[i][w] = { soldU: 0, soldCr: 0, boughtU: 0, boughtCr: 0 });
      if (t.direction === 'Out') { d.soldU += t.amount; d.soldCr += cr; }
      else                       { d.boughtU += t.amount; d.boughtCr += cr; }
    });

    // If the zoom window contains no trades show a lightweight empty state for all
    // three modes so the scrubber remains visible and interactive.
    if (!trades.length) {
      const empty = `<div style="padding:16px 14px;font-family:var(--font-mono);font-size:11px;color:var(--text-faint)">No trades in this window</div>`;
      return `
        <div data-cfmode="hourly" style="display:block">${empty}</div>
        <div data-cfmode="trade"  style="display:none">${empty}</div>
        <div data-cfmode="ware"   style="display:none">${empty}</div>
        ${buildScrubberHtml(safeCode)}`;
    }

    // ── Hourly body ──────────────────────────────────────────────────────────
    const hourlyBody = (() => {
      const hi = Math.max(0, ...net), lo = Math.min(0, ...net);
      const step = cfNiceStep(hi - lo, 6);
      const axTop = Math.ceil(hi / step) * step || step;
      const axBot = Math.floor(lo / step) * step;
      const yOf = v => mt + ph - (v - axBot) / (axTop - axBot) * ph;
      const zeroY = yOf(0), zeroFrac = ((zeroY - mt) / ph).toFixed(4);
      const glowId = `holo-glow-${safeCode}-h`, fillId = `cashfill-${safeCode}-h`;

      // Bucket centres are arranged right→left (bucket 0 = rightmost = most recent).
      // The scrubber produces fractional windows (e.g. 4.37h → 5 buckets), so the
      // oldest bucket is usually cut off by the left edge. Plot it at the centre
      // of its *visible* span — min(i+1, windowHours) caps the bucket end at the
      // window edge — otherwise its vertex lands left of the y-axis.
      const bucketCentre = i => offsetHours + (i + Math.min(i + 1, windowHours)) / 2;
      const ordered = [];
      for (let i = numHours - 1; i >= 0; i--) {
        ordered.push([xOf(bucketCentre(i)), net[i]]);
      }
      const linePts = ordered.map(([x, v]) => `${x.toFixed(1)},${yOf(v).toFixed(1)}`).join(' ');
      const areaPath = `M ${ordered[0][0].toFixed(1)} ${zeroY.toFixed(1)} ` +
                       ordered.map(([x, v]) => `L ${x.toFixed(1)} ${yOf(v).toFixed(1)}`).join(' ') +
                       ` L ${ordered[ordered.length - 1][0].toFixed(1)} ${zeroY.toFixed(1)} Z`;

      const markers = [], hitCols = [];
      for (let i = 0; i < numHours; i++) {
        const rows = [];
        Object.keys(detail[i]).forEach(w => {
          const d = detail[i][w], col = WARE_COLOURS[w] || '#5eead4';
          if (d.soldU   > 0) rows.push({ ware: w, colour: col, dir: 'sell', units: d.soldU,   cr:  d.soldCr });
          if (d.boughtU > 0) rows.push({ ware: w, colour: col, dir: 'buy',  units: d.boughtU, cr: -d.boughtCr });
        });
        if (!rows.length) continue;
        rows.sort((a, b) => Math.abs(b.cr) - Math.abs(a.cr));
        const cx = xOf(bucketCentre(i)).toFixed(1), cy = yOf(net[i]).toFixed(1);
        const dotCol = net[i] >= 0 ? '#5eead4' : '#ef5350';
        markers.push(`<circle cx="${cx}" cy="${cy}" r="2.6" fill="${dotCol}" filter="url(#${glowId})"/>
                      <circle cx="${cx}" cy="${cy}" r="2.2" fill="${dotCol}"/>`);
        // hAgo = absolute hours-ago for the bucket start (rounded to nearest hour).
        const tipHAgo = Math.round(offsetHours + i);
        const tip = encodeURIComponent(JSON.stringify({ hAgo: tipHAgo, net: net[i], rows }));
        // Hover column spans the bucket's visible hours exactly — the oldest
        // bucket is capped at the window edge so the rect never leaves the plot.
        const colX1 = xOf(offsetHours + Math.min(i + 1, windowHours));
        const colX2 = xOf(offsetHours + i);
        hitCols.push(`<rect class="cf-col" x="${colX1.toFixed(1)}" y="${mt}" width="${(colX2 - colX1).toFixed(1)}" height="${ph}" data-cashflow-tip="${tip}"></rect>`);
      }

      return `
        <div style="background:#030d14;border:1px solid rgba(25,230,200,0.18);border-radius:3px;box-shadow:inset 0 0 24px rgba(25,230,200,0.05);padding:4px">
          <svg viewBox="0 0 ${svgW} ${svgH}" preserveAspectRatio="xMidYMid meet" style="display:block;width:100%;height:auto">
            <defs>
              <filter id="${glowId}" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="2"/></filter>
              <linearGradient id="${fillId}" x1="0" y1="${mt}" x2="0" y2="${mt + ph}" gradientUnits="userSpaceOnUse">
                <stop offset="0"           stop-color="#19e6c8" stop-opacity="0.30"/>
                <stop offset="${zeroFrac}" stop-color="#19e6c8" stop-opacity="0.05"/>
                <stop offset="${zeroFrac}" stop-color="#ef5350" stop-opacity="0.05"/>
                <stop offset="1"           stop-color="#ef5350" stop-opacity="0.30"/>
              </linearGradient>
              <clipPath id="cfclip-${safeCode}-h"><rect x="${ml}" y="${mt}" width="${pw}" height="${ph}"/></clipPath>
            </defs>
            <rect x="${ml}" y="${mt}" width="${pw}" height="${ph}" fill="#020a10"/>
            ${yAxisHtml(yOf, axBot, axTop, step)}
            ${xTicksHtml}
            <!-- Data layer is clipped to the plot rect so strokes/glow can never
                 spill past the axes, whatever the zoom window does. -->
            <g clip-path="url(#cfclip-${safeCode}-h)">
              <path d="${areaPath}" fill="url(#${fillId})" stroke="none"/>
              <polyline points="${linePts}" fill="none" stroke="#2dd4bf" stroke-width="3" stroke-linejoin="round" stroke-linecap="round" opacity="0.35" filter="url(#${glowId})"/>
              <polyline points="${linePts}" fill="none" stroke="#5eead4" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/>
              ${markers.join('')}
            </g>
            <line x1="${ml}" y1="${mt}" x2="${ml}" y2="${mt + ph}" stroke="#19e6c8" stroke-opacity="0.35" stroke-width="1"/>
            <text x="9" y="${mt + ph / 2}" text-anchor="middle" dominant-baseline="middle" fill="#5fe9d4" fill-opacity="0.6"
                  style="font-family:var(--font-mono);font-size:8px;letter-spacing:0.1em" transform="rotate(-90 9 ${mt + ph / 2})">CREDITS/HR</text>
            ${hitCols.join('')}
          </svg>
        </div>
        <div style="display:flex;gap:16px;padding:6px 2px 2px;font-family:var(--font-mono);font-size:9px;letter-spacing:0.04em">
          <span style="display:inline-flex;align-items:center;gap:5px;color:#19e6c8"><span style="display:inline-block;width:11px;height:2px;background:#19e6c8;border-radius:1px;filter:drop-shadow(0 0 2px #19e6c8)"></span>INCOME (SELLS)</span>
          <span style="display:inline-flex;align-items:center;gap:5px;color:#ef5350"><span style="display:inline-block;width:11px;height:2px;background:#ef5350;border-radius:1px;filter:drop-shadow(0 0 2px #ef5350)"></span>SPEND (BUYS)</span>
        </div>`;
    })();

    // ── By-Trade body (drill-down) ─────────────────────────────────────────────
    // Size of each individual trade: every vertex is one trade plotted at its
    // signed credit value (sells +, buys −), connected in time order — a spiky
    // line that shows how big each deal was. Hover snaps to the nearest trade.
    const detailBody = (() => {
      const chron = trades.slice().sort((a, b) => b.time_ago_s - a.time_ago_s); // oldest → newest
      const pts = chron.map(t => ({
        hAgo: t.time_ago_s / 3600,
        value: (t.direction === 'Out' ? 1 : -1) * (t.total_cr || 0),
        t,
      }));
      let rlo = 0, rhi = 0;
      pts.forEach(p => { if (p.value < rlo) rlo = p.value; if (p.value > rhi) rhi = p.value; });
      const step = cfNiceStep(rhi - rlo, 6);
      const axTop = Math.ceil(rhi / step) * step || step;
      const axBot = Math.floor(rlo / step) * step;
      const yOf = v => mt + ph - (v - axBot) / (axTop - axBot) * ph;
      const zeroY = yOf(0), zeroFrac = ((zeroY - mt) / ph).toFixed(4);
      const glowId = `holo-glow-${safeCode}-d`, fillId = `cashfill-${safeCode}-d`;

      // Spiky line through each trade's value, with the area filled to the zero
      // baseline (teal above for sells, red below for buys).
      const verts    = pts.map(p => [xOf(p.hAgo), yOf(p.value)]);
      const linePts  = verts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
      const areaPath = `M ${verts[0][0].toFixed(1)} ${zeroY.toFixed(1)} ` +
                       verts.map(([x, y]) => `L ${x.toFixed(1)} ${y.toFixed(1)}`).join(' ') +
                       ` L ${verts[verts.length - 1][0].toFixed(1)} ${zeroY.toFixed(1)} Z`;

      // Per-trade dots + the hover lookup table (nearest-point by x fraction).
      const store = [];
      const dots = pts.map(p => {
        const x = xOf(p.hAgo), y = yOf(p.value);
        const isSell = p.t.direction === 'Out';
        store.push({
          fx: (x - ml) / pw, vbx: +x.toFixed(1), vby: +y.toFixed(1),
          ware: p.t.ware_name || 'Unknown', colour: WARE_COLOURS[p.t.ware_name] || '#5eead4',
          dir: isSell ? 'sell' : 'buy', units: p.t.amount, priceEa: p.t.price_cr,
          total: p.value, hAgo: p.hAgo, ship: p.t.ship_code || '', counterparty: p.t.counterparty || '',
        });
        return `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="1.6" fill="${isSell ? '#5eead4' : '#ef5350'}" opacity="0.85"/>`;
      }).join('');
      cashflowDetailData[safeCode] = store;

      return `
        <div style="background:#030d14;border:1px solid rgba(25,230,200,0.18);border-radius:3px;box-shadow:inset 0 0 24px rgba(25,230,200,0.05);padding:4px">
          <svg viewBox="0 0 ${svgW} ${svgH}" preserveAspectRatio="xMidYMid meet" style="display:block;width:100%;height:auto">
            <defs>
              <filter id="${glowId}" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="3"/></filter>
              <linearGradient id="${fillId}" x1="0" y1="${mt}" x2="0" y2="${mt + ph}" gradientUnits="userSpaceOnUse">
                <stop offset="0"           stop-color="#2dd4bf" stop-opacity="0.45"/>
                <stop offset="${zeroFrac}" stop-color="#2dd4bf" stop-opacity="0.04"/>
                <stop offset="${zeroFrac}" stop-color="#ef5350" stop-opacity="0.04"/>
                <stop offset="1"           stop-color="#ef5350" stop-opacity="0.45"/>
              </linearGradient>
              <clipPath id="cfclip-${safeCode}-d"><rect x="${ml}" y="${mt}" width="${pw}" height="${ph}"/></clipPath>
            </defs>
            <rect x="${ml}" y="${mt}" width="${pw}" height="${ph}" fill="#020a10"/>
            ${yAxisHtml(yOf, axBot, axTop, step)}
            ${xTicksHtml}
            <!-- Clipped like the hourly chart — see comment there. -->
            <g clip-path="url(#cfclip-${safeCode}-d)">
              <path d="${areaPath}" fill="url(#${fillId})" stroke="none"/>
              <polyline points="${linePts}" fill="none" stroke="#2dd4bf" stroke-width="4" stroke-linejoin="round" stroke-linecap="round" opacity="0.45" filter="url(#${glowId})"/>
              <polyline points="${linePts}" fill="none" stroke="#7af5e4" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/>
              ${dots}
            </g>
            <line x1="${ml}" y1="${mt}" x2="${ml}" y2="${mt + ph}" stroke="#19e6c8" stroke-opacity="0.35" stroke-width="1"/>
            <text x="9" y="${mt + ph / 2}" text-anchor="middle" dominant-baseline="middle" fill="#5fe9d4" fill-opacity="0.6"
                  style="font-family:var(--font-mono);font-size:8px;letter-spacing:0.1em" transform="rotate(-90 9 ${mt + ph / 2})">TRADE SIZE · CR</text>
            <!-- Highlight ring follows the nearest trade on hover -->
            <circle class="cf-detail-marker" r="3.8" fill="none" stroke="#ffffff" stroke-width="1.5" style="display:none;pointer-events:none"/>
            <!-- Transparent plot overlay drives nearest-point hover -->
            <rect data-cfdetail="${safeCode}" x="${ml}" y="${mt}" width="${pw}" height="${ph}" fill="transparent" style="cursor:crosshair"/>
          </svg>
        </div>
        <div style="padding:6px 2px 2px;font-family:var(--font-mono);font-size:9px;letter-spacing:0.04em;color:var(--text-faint)">
          ${pts.length.toLocaleString()} trades · individual trade size · hover a point for trade details
        </div>`;
    })();

    // ── By-Ware body ───────────────────────────────────────────────────────────
    // One step-line per ware, normalised to its own min/avg/max price band.
    // A Sold / Bought toggle at the top-left switches between Out and In trades
    // so the user can inspect both what the station sold and what it bought.
    const byWareBody = (() => {
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
        return `<div style="display:flex;align-items:flex-start;gap:8px;padding:2px 0 4px">
          <div style="display:flex;flex-direction:column;gap:2px">
            <button class="cf-toggle-btn ${isSell ? 'active' : ''}" onclick="setWareMode('${safeCode}','sell')">Sell</button>
            <button class="cf-toggle-btn ${!isSell ? 'active' : ''}" onclick="setWareMode('${safeCode}','buy')">Buy</button>
          </div>
          <div style="padding:6px 0;font-family:var(--font-mono);font-size:11px;color:var(--text-faint)">No ${isSell ? 'sell' : 'buy'} activity in this window</div>
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

      const storeWare = []; // hover lookup table — one entry per trade dot
      const wareGroupHtml = [];

      // Process each ware: compute price band, build SVG paths, populate hover store.
      wareNames.forEach(wareName => {
        const col     = WARE_COLOURS[wareName] || '#5eead4';
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

        const groupId = `ware-group-${safeCode}-${wareKey}`;
        const visible = wareVisibility[safeCode][wareName];
        wareGroupHtml.push(`<g id="${groupId}" style="display:${visible ? 'block' : 'none'}">
          <path d="${areaD}" fill="${col}" fill-opacity="0.10" stroke="none"/>
          <path d="${stepD}" fill="none" stroke="${col}" stroke-width="3"   stroke-linejoin="round" opacity="0.18"/>
          <path d="${stepD}" fill="none" stroke="${col}" stroke-width="1.5" stroke-linejoin="round"/>
          ${pts.map(p => `<circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="2" fill="${col}" opacity="0.85"/>`).join('')}
        </g>`);
      });

      // Commit the lookup table so the mousemove handler can find it by safeCode.
      wareChartData[safeCode] = storeWare;

      // Y-axis: MIN / AVG / MAX reference lines — labels apply equally to all
      // wares since every line is normalised to its own band.
      const yMax = mt, yAvg = mt + ph / 2, yMin = mt + ph;
      const yAxisWare = `
        <line x1="${ml}" y1="${yMax.toFixed(1)}" x2="${(ml+pw).toFixed(1)}" y2="${yMax.toFixed(1)}" stroke="#19e6c8" stroke-opacity="0.10" stroke-width="0.6"/>
        <line x1="${ml}" y1="${yAvg.toFixed(1)}" x2="${(ml+pw).toFixed(1)}" y2="${yAvg.toFixed(1)}" stroke="#19e6c8" stroke-opacity="0.28" stroke-width="1" stroke-dasharray="4 3"/>
        <line x1="${ml}" y1="${yMin.toFixed(1)}" x2="${(ml+pw).toFixed(1)}" y2="${yMin.toFixed(1)}" stroke="#19e6c8" stroke-opacity="0.10" stroke-width="0.6"/>
        <text x="${ml-6}" y="${yMax.toFixed(1)}" text-anchor="end" dominant-baseline="middle" fill="#5fe9d4" fill-opacity="0.70" style="font-family:var(--font-mono);font-size:8px">MAX</text>
        <text x="${ml-6}" y="${yAvg.toFixed(1)}" text-anchor="end" dominant-baseline="middle" fill="#5fe9d4" fill-opacity="0.90" style="font-family:var(--font-mono);font-size:8px">AVG</text>
        <text x="${ml-6}" y="${yMin.toFixed(1)}" text-anchor="end" dominant-baseline="middle" fill="#5fe9d4" fill-opacity="0.70" style="font-family:var(--font-mono);font-size:8px">MIN</text>`;

      // Legend chips — clicking toggles the ware line on/off.
      const chips = wareNames.map(wareName => {
        const col     = WARE_COLOURS[wareName] || '#5eead4';
        const wareKey = wareName.toLowerCase().replace(/\s+/g, '');
        const on      = wareVisibility[safeCode][wareName];
        return `<span id="ware-chip-${safeCode}-${wareKey}"
                      onclick="toggleWare('${safeCode}','${wareName}')"
                      style="cursor:pointer;opacity:${on ? '1' : '0.35'};
                             display:inline-flex;align-items:center;
                             padding:2px 7px;border-radius:2px;
                             border:1px solid ${col}44;background:${col}22;
                             color:${col};font-family:var(--font-mono);
                             font-size:10px;white-space:nowrap;letter-spacing:0.04em;
                             user-select:none">${wareName}</span>`;
      }).join('');

      return `
        <div style="background:#030d14;border:1px solid rgba(25,230,200,0.18);border-radius:3px;box-shadow:inset 0 0 24px rgba(25,230,200,0.05);padding:4px">
          <svg viewBox="0 0 ${svgW} ${svgH}" preserveAspectRatio="xMidYMid meet" style="display:block;width:100%;height:auto">
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
            <line x1="${ml}" y1="${mt}" x2="${ml}" y2="${mt+ph}" stroke="#19e6c8" stroke-opacity="0.35" stroke-width="1"/>
            <text x="9" y="${mt + ph/2}" text-anchor="middle" dominant-baseline="middle" fill="#5fe9d4" fill-opacity="0.6"
                  style="font-family:var(--font-mono);font-size:8px;letter-spacing:0.1em" transform="rotate(-90 9 ${mt + ph/2})">PRICE · BAND</text>
            <!-- Highlight ring — stroke colour set dynamically to match the hovered ware -->
            <circle class="cf-ware-marker" r="4" fill="none" stroke="#ffffff" stroke-width="1.5" style="display:none;pointer-events:none"/>
            <!-- Transparent overlay that captures mouse events for nearest-point hover -->
            <rect data-cfware="${safeCode}" x="${ml}" y="${mt}" width="${pw}" height="${ph}" fill="transparent" style="cursor:crosshair"/>
            <!-- Sold/Bought toggle — must come after the hit rect in document order so
                 it paints and receives clicks on top of the crosshair overlay. -->
            ${wareToggleFO}
          </svg>
        </div>
        <div style="display:flex;flex-wrap:wrap;gap:5px;padding:6px 2px 2px;will-change:transform">
          ${chips}
        </div>`;
    })();

    return `
      <div data-cfmode="hourly" style="display:block">${hourlyBody}</div>
      <div data-cfmode="trade"  style="display:none">${detailBody}</div>
      <div data-cfmode="ware"   style="display:none">${byWareBody}</div>
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
    return `<div class="cf-scrubber-track" data-scrubber="${safeCode}">
      <div class="cf-scrubber-handle" style="left:${hLeft}%;width:${hWidth}%">
        <div class="cf-scrubber-resize" data-side="left"></div>
        <div class="cf-scrubber-resize" data-side="right"></div>
      </div>
      <span class="cf-scrubber-label" style="left:3px">-24H</span>
      <span class="cf-scrubber-label" style="left:50%;transform:translate(-50%,-50%)">DRAG &amp; RESIZE</span>
      <span class="cf-scrubber-label" style="right:3px">NOW</span>
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
    // is retargeted in place so its bars animate (see buildAvgPriceBody).
    volatileEl.innerHTML = buildCfBodiesHtml(safeCode);
    updateAvgPrice(safeCode);
    setCashflowMode(safeCode, activeMode);
  }

  // ── Avg Price chart ───────────────────────────────────────────────────────
  // Average trade price per hour for a single selected ware, one bar per hour,
  // split by direction via a SOLD/BOUGHT toggle (like By Ware). Unlike the other
  // charts this one is built ONCE (buildAvgPriceBody) then mutated in place
  // (updateAvgPrice) so its bars CSS-transition between values on every change.

  // Wares this station traded in `dir` over the full 24h, sorted alphabetically.
  // Computed over all history (not the zoom window) so the chip list and current
  // selection stay stable while the user scrubs the time slider.
  function avgPriceWareList(safeCode, dir) {
    const { station, allTrades } = cfStationCache[safeCode];
    const want = dir === 'sell' ? 'Out' : 'In';
    const set = new Set();
    allTrades.forEach(t => {
      if (t.station_code === station.code && t.direction === want &&
          t.time_ago_s / 3600 < CF_MAX_HOURS) set.add(t.ware_name || 'Unknown');
    });
    return [...set].sort();
  }

  // Seed a sensible default the first time a station's chart is shown: prefer a
  // direction that actually has trades, sells first.
  function avgPriceSeed(safeCode) {
    if (avgMode[safeCode] && avgWare[safeCode]) return;
    const sells = avgPriceWareList(safeCode, 'sell');
    const buys  = avgPriceWareList(safeCode, 'buy');
    if (sells.length)     { avgMode[safeCode] = 'sell'; avgWare[safeCode] = sells[0]; }
    else if (buys.length) { avgMode[safeCode] = 'buy';  avgWare[safeCode] = buys[0]; }
    else                  { avgMode[safeCode] = 'sell'; avgWare[safeCode] = null; }
  }

  // Static scaffold only — the grid/ticks/bars/toggle/chips are populated by
  // updateAvgPrice so they can change (and the bars animate) without a rebuild.
  function buildAvgPriceBody(safeCode) {
    avgPriceSeed(safeCode);
    const svgW = 560, svgH = 320, ml = 56, mr = 14, mt = 12, mb = 30;
    const pw = svgW - ml - mr, ph = svgH - mt - mb;
    return `
      <div style="background:#030d14;border:1px solid rgba(25,230,200,0.18);border-radius:3px;box-shadow:inset 0 0 24px rgba(25,230,200,0.05);padding:4px">
        <svg viewBox="0 0 ${svgW} ${svgH}" preserveAspectRatio="xMidYMid meet" style="display:block;width:100%;height:auto">
          <defs>
            <clipPath id="avgclip-${safeCode}"><rect x="${ml}" y="${mt}" width="${pw}" height="${ph}"/></clipPath>
          </defs>
          <rect x="${ml}" y="${mt}" width="${pw}" height="${ph}" fill="#020a10"/>
          <g class="avg-grid"></g>
          <g class="avg-xticks"></g>
          <g class="avg-bars" clip-path="url(#avgclip-${safeCode})"></g>
          <line x1="${ml}" y1="${mt}" x2="${ml}" y2="${mt + ph}" stroke="#19e6c8" stroke-opacity="0.35" stroke-width="1"/>
          <text x="9" y="${mt + ph / 2}" text-anchor="middle" dominant-baseline="middle" fill="#5fe9d4" fill-opacity="0.6"
                style="font-family:var(--font-mono);font-size:8px;letter-spacing:0.1em" transform="rotate(-90 9 ${mt + ph / 2})">PRICE · CR</text>
          <!-- Readout line: on hover it projects the bar's top across to the
               price axis at that hour's average. Colour set per-hover in JS. -->
          <line class="avg-hot-line" stroke-dasharray="3 3" stroke-width="0.8" style="opacity:0;transition:opacity 0.15s;pointer-events:none"/>
          <!-- Transparent per-hour hit columns (full plot height) drive the
               tooltip + bar highlight; rebuilt each update. -->
          <g class="avg-hits"></g>
          <g class="avg-toggle"></g>
        </svg>
      </div>
      <div class="avg-chips" style="display:flex;flex-wrap:wrap;gap:5px;padding:6px 2px 2px"></div>`;
  }

  // Switch the chart's direction / selected ware (radio); both retarget the bars.
  function setAvgMode(safeCode, mode) {
    if (avgMode[safeCode] === mode) return;
    avgMode[safeCode] = mode;
    // The selected ware may not exist in the new direction — fall back to first.
    const list = avgPriceWareList(safeCode, mode);
    if (!list.includes(avgWare[safeCode])) avgWare[safeCode] = list[0] || null;
    updateAvgPrice(safeCode);
  }
  function setAvgWare(safeCode, ware) {
    avgWare[safeCode] = ware;
    updateAvgPrice(safeCode);
  }

  // Retarget the persistent bars + axes/ticks/chips/toggle to the current zoom
  // window, ware and direction. Called on first view and after every scrubber
  // change. Only the <rect> bars are reused (so they animate); everything else
  // is cheap to rewrite.
  function updateAvgPrice(safeCode) {
    const root = document.getElementById('cf-avg-' + safeCode);
    if (!root || !cfStationCache[safeCode]) return;
    avgPriceSeed(safeCode);

    const svgW = 560, svgH = 320, ml = 56, mr = 14, mt = 12, mb = 30;
    const pw = svgW - ml - mr, ph = svgH - mt - mb;
    const SVG_NS = 'http://www.w3.org/2000/svg';

    const { station, allTrades } = cfStationCache[safeCode];
    const { hours: windowHours, offsetHours } = cfZoom[safeCode] || { hours: CF_MAX_HOURS, offsetHours: 0 };
    const dir  = avgMode[safeCode] || 'sell';
    const ware = avgWare[safeCode];
    const want = dir === 'sell' ? 'Out' : 'In';
    const numHours = Math.ceil(windowHours);
    const col = ware ? (WARE_COLOURS[ware] || '#5eead4') : '#5eead4';

    const xOf = h => ml + (offsetHours + windowHours - h) / windowHours * pw;

    // Hourly mean price for the selected ware+direction in the visible window.
    const sum = new Array(numHours).fill(0);
    const cnt = new Array(numHours).fill(0);
    const mn  = new Array(numHours).fill(Infinity);   // cheapest trade that hour
    const mx  = new Array(numHours).fill(-Infinity);  // dearest trade that hour
    if (ware) allTrades.forEach(t => {
      if (t.station_code !== station.code || t.direction !== want) return;
      if ((t.ware_name || 'Unknown') !== ware) return;
      const hAgo = t.time_ago_s / 3600;
      if (hAgo < offsetHours || hAgo >= offsetHours + windowHours) return;
      const i = Math.floor(hAgo - offsetHours);
      if (i < 0 || i >= numHours) return;
      sum[i] += t.price_cr; cnt[i] += 1;
      if (t.price_cr < mn[i]) mn[i] = t.price_cr;
      if (t.price_cr > mx[i]) mx[i] = t.price_cr;
    });
    const avg  = sum.map((s, i) => cnt[i] ? s / cnt[i] : null);
    const vals = avg.filter(v => v != null);

    // ── radio chips ──
    const chipsEl = root.querySelector('.avg-chips');
    const wares   = avgPriceWareList(safeCode, dir);
    chipsEl.innerHTML = wares.length ? wares.map(w => {
      const c = WARE_COLOURS[w] || '#5eead4', on = w === ware;
      return `<span onclick="setAvgWare('${safeCode}','${w}')"
        style="cursor:pointer;opacity:${on ? '1' : '0.4'};display:inline-flex;align-items:center;
               padding:2px 7px;border-radius:2px;border:1px solid ${c}${on ? 'aa' : '44'};
               background:${c}${on ? '33' : '14'};color:${c};font-family:var(--font-mono);
               font-size:10px;white-space:nowrap;letter-spacing:0.04em;user-select:none">${w}</span>`;
    }).join('') : `<span style="font-family:var(--font-mono);font-size:10px;color:var(--text-faint)">No ${dir} activity in the last 24h</span>`;

    // ── SOLD/BOUGHT toggle (vertical pill, mirrors By Ware) ──
    const isSell = dir === 'sell';
    root.querySelector('.avg-toggle').innerHTML = `
      <foreignObject x="2" y="${mt}" width="30" height="44">
        <div xmlns="http://www.w3.org/1999/xhtml" style="width:30px;height:44px;display:grid;grid-template-rows:1fr 1fr;
            position:relative;background:rgba(4,12,20,0.88);border:1px solid rgba(0,0,0,0.70);border-radius:2px;
            overflow:hidden;user-select:none;box-shadow:inset 0 2px 7px rgba(0,0,0,0.70),inset 0 1px 3px rgba(0,0,0,0.50),0 1px 0 rgba(255,255,255,0.07)">
          <div style="position:absolute;left:1px;right:1px;height:20px;top:${isSell ? '1px' : '23px'};
              background:linear-gradient(170deg,rgba(85,245,215,0.97) 0%,rgba(46,202,178,0.93) 42%,rgba(29,170,150,0.91) 100%);
              border-radius:1px;pointer-events:none;transition:top 0.18s ease;
              box-shadow:0 3px 9px rgba(0,0,0,0.70),0 1px 3px rgba(0,0,0,0.50),inset 0 1px 0 rgba(255,255,255,0.42),inset 0 -1px 0 rgba(0,0,0,0.24)"></div>
          <span onclick="setAvgMode('${safeCode}','sell')" style="position:relative;z-index:1;cursor:pointer;display:flex;align-items:center;
              justify-content:center;font-family:'Share Tech Mono',monospace;font-size:7px;letter-spacing:0.06em;text-transform:uppercase;
              color:${isSell ? '#051210' : 'rgba(45,212,191,0.40)'};font-weight:${isSell ? '700' : '400'}">SELL</span>
          <span onclick="setAvgMode('${safeCode}','buy')" style="position:relative;z-index:1;cursor:pointer;display:flex;align-items:center;
              justify-content:center;font-family:'Share Tech Mono',monospace;font-size:7px;letter-spacing:0.06em;text-transform:uppercase;
              color:${!isSell ? '#051210' : 'rgba(45,212,191,0.40)'};font-weight:${!isSell ? '700' : '400'}">BUY</span>
        </div>
      </foreignObject>`;

    const gridEl = root.querySelector('.avg-grid');
    const xtEl   = root.querySelector('.avg-xticks');
    const barsEl = root.querySelector('.avg-bars');

    // Empty window: clear axes, collapse any existing bars to the baseline.
    if (!vals.length) {
      gridEl.innerHTML = ''; xtEl.innerHTML = '';
      [...barsEl.children].forEach(r => { r.setAttribute('height', '0'); r.setAttribute('opacity', '0'); });
      return;
    }

    // ── Y axis: price, zoomed to the data so hourly variation is visible ──
    const lo = Math.min(...vals), hi = Math.max(...vals);
    const step  = cfNiceStep((hi - lo) || hi || 1, 5);
    const axBot = Math.max(0, Math.floor(lo / step) * step);
    let   axTop = Math.ceil(hi / step) * step;
    if (axTop <= axBot) axTop = axBot + step; // guard flat / single-value data
    const yOf  = v => mt + ph - (v - axBot) / (axTop - axBot) * ph;
    const baseY = yOf(axBot); // = mt + ph

    const ticks = [];
    for (let v = axBot; v <= axTop + 0.5; v += step) ticks.push(v);
    gridEl.innerHTML = ticks.map(v => {
      const y = yOf(v).toFixed(1);
      return `<line x1="${ml}" y1="${y}" x2="${ml + pw}" y2="${y}" stroke="#19e6c8" stroke-opacity="0.10" stroke-width="0.6"/>
        <text x="${ml - 6}" y="${y}" text-anchor="end" dominant-baseline="middle" fill="#5fe9d4" fill-opacity="0.7" style="font-family:var(--font-mono);font-size:8px">${cfFmtY(v)}</text>`;
    }).join('');

    // ── X ticks: same adaptive spacing as the other charts ──
    const tickStep = windowHours <= 3 ? 0.5 : windowHours <= 6 ? 1 : windowHours <= 12 ? 2 : 6;
    let xt = '';
    for (let h = Math.ceil(offsetHours / tickStep) * tickStep; h <= offsetHours + windowHours + 0.001; h += tickStep) {
      const x = xOf(h).toFixed(1);
      const label = h === 0 ? 'NOW' : h < 1 ? `-${Math.round(h * 60)}M` : `-${h % 1 !== 0 ? h.toFixed(1) : Math.round(h)}H`;
      xt += `<line x1="${x}" y1="${mt}" x2="${x}" y2="${mt + ph}" stroke="#19e6c8" stroke-opacity="0.08" stroke-width="0.6"/>
        <text x="${x}" y="${mt + ph + 13}" text-anchor="middle" fill="#5fe9d4" fill-opacity="0.7" style="font-family:var(--font-mono);font-size:8px;letter-spacing:0.06em">${label}</text>`;
    }
    xtEl.innerHTML = xt;

    // ── Bars: reconcile to exactly numHours <rect>s, then retarget geometry.
    // Identity is by slot index (0 = most recent hour, right edge), so panning
    // glides each slot's value and resizing adds/removes slots at the old end.
    const gap = 2;
    while (barsEl.children.length < numHours) {
      const r = document.createElementNS(SVG_NS, 'rect');
      r.setAttribute('rx', '1');
      r.setAttribute('y', baseY.toFixed(1)); r.setAttribute('height', '0'); r.setAttribute('opacity', '0');
      barsEl.appendChild(r);
    }
    while (barsEl.children.length > numHours) barsEl.removeChild(barsEl.lastChild);

    for (let i = 0; i < numHours; i++) {
      const r = barsEl.children[i];
      // Oldest (leftmost) bucket is capped at the window edge so it never pokes
      // past the y-axis when the window width is fractional.
      const x = xOf(offsetHours + Math.min(i + 1, windowHours));
      const w = xOf(offsetHours + i) - x;
      r.setAttribute('x', (x + gap / 2).toFixed(1));
      r.setAttribute('width', Math.max(0.5, w - gap).toFixed(1));
      r.setAttribute('fill', col);
      if (avg[i] == null) {
        r.setAttribute('y', baseY.toFixed(1)); r.setAttribute('height', '0'); r.setAttribute('opacity', '0');
        r.removeAttribute('data-avg-tip');
      } else {
        const y = yOf(avg[i]);
        r.setAttribute('y', y.toFixed(1));
        r.setAttribute('height', Math.max(0, baseY - y).toFixed(1));
        r.setAttribute('opacity', '0.9');
      }
    }

    // ── Hit columns + tooltip data (only for hours that have trades) ──
    // Full-height transparent rects so the cursor catches the whole column, not
    // just the bar. Each carries its hour's stats + the previous populated
    // hour's average (for the "vs previous hour" delta in the tooltip).
    let hitsHtml = '';
    for (let i = 0; i < numHours; i++) {
      if (avg[i] == null) continue;
      let prevAvg = null;
      for (let j = i + 1; j < numHours; j++) { if (avg[j] != null) { prevAvg = avg[j]; break; } }
      const x = xOf(offsetHours + Math.min(i + 1, windowHours));
      const w = xOf(offsetHours + i) - x;
      const tipData = encodeURIComponent(JSON.stringify({
        ware, dir, colour: col,
        hAgo: Math.round(offsetHours + i),
        avg: avg[i], count: cnt[i], min: mn[i], max: mx[i], prevAvg,
      }));
      hitsHtml += `<rect class="avg-hit" data-avgtip="${tipData}" data-avg-i="${i}" x="${x.toFixed(1)}" y="${mt}" width="${Math.max(0.5, w).toFixed(1)}" height="${ph}" fill="transparent" style="cursor:crosshair"/>`;
    }
    root.querySelector('.avg-hits').innerHTML = hitsHtml;
  }

  // Toggle between the Hourly, By-Trade, and By-Ware cash-flow views for one station.
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

  // Switch the By-Ware chart between sold (Out) and bought (In) trades.
  // State persists per station; triggers a full bodies rebuild so the SVG and
  // chips update to reflect the selected direction.
  function setWareMode(safeCode, mode) {
    wareMode[safeCode] = mode;
    rebuildCfChart(safeCode);
  }

  const ROLE_ICONS = {
    "Fighter":              "ti-rocket",
    "Heavy Fighter":        "ti-rocket",
    "Corvette":             "ti-rocket",
    "Destroyer":            "ti-anchor",
    "Frigate":              "ti-shield",
    "Gunboat":              "ti-crosshair",
    "Scout":                "ti-eye",
    "Carrier":              "ti-drone",
    "Freighter":            "ti-package",
    "Transport":            "ti-package",
    "Gas Tanker":           "ti-ripple",
    "Miner (Solid)":        "ti-shovel",
    "Miner (Liquid)":       "ti-droplet",
    "Combat Supply":        "ti-box",
    "Supply":               "ti-box",
    "Boarding":             "ti-sword",
  };

  const ORDER_ICONS = {
    "Trading":   "ti-arrows-exchange",
    "Mining":    "ti-shovel",
    "Escorting": "ti-shield",
    "Waiting":   "ti-clock",
    "Idle":      "ti-clock",
    "Patrol":    "ti-route",
    "Attack":    "ti-crosshair",
    "Building":  "ti-hammer",
    "Repair":    "ti-tool",
    "Supply":    "ti-box",
    "Docking":   "ti-ship",
    "Travel":    "ti-route",
  };

  const CARD_ICONS = {
    "Credits":       "ti-coin",
    "Total Ships":   "ti-rocket",
    "Stations":      "ti-building-factory-2",
    "Hostile Hulls": "ti-alert-triangle",
    "Waiting":       "ti-clock",
  };

