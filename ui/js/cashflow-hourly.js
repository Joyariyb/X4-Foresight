  // Core role: Hourly and By-Trade panels of the station cash-flow chart — net credits per hour, and every individual trade's size.
  //
  // Both builders receive the shared layout context (ctx) prepared by
  // buildCfBodiesHtml in cashflow-chart.js, so every panel shares one window
  // filter and axis geometry.

  // Per-station hover store for the By-Trade panel — one entry per plotted
  // trade, searched by the cfdetail tooltip handler below.
  const cashflowDetailData = {};

  // ── Hourly body ──────────────────────────────────────────────────────────
  function buildCfHourlyBody(ctx) {
    const { safeCode, trades, numHours, windowHours, offsetHours, svgW, svgH, ml, mt, pw, ph, xOf, xTicksHtml, yAxisHtml } = ctx;

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

    const hi = Math.max(0, ...net), lo = Math.min(0, ...net);
    const step = cfNiceStep(hi - lo, 6);
    const axTop = Math.ceil(hi / step) * step || step;
    const axBot = Math.floor(lo / step) * step;
    const yOf = v => mt + ph - (v - axBot) / (axTop - axBot) * ph;
    const zeroY = yOf(0), zeroFrac = ((zeroY - mt) / ph).toFixed(4);
    const glowId = `holo-glow-${safeCode}-h`, fillId = `cashfill-${safeCode}-h`;
    // Which visual style to render — persists across scrubber drags and tab switches.
    const hourlyType = (cfChartType[safeCode] || {}).hourly || 'line';

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

    // Markers (line-mode dots) are only shown in line mode; hitCols drive hover
    // tooltips in every mode so they are always built.
    const markers = [], hitCols = [];
    for (let i = 0; i < numHours; i++) {
      const rows = [];
      Object.keys(detail[i]).forEach(w => {
        const d = detail[i][w], col = WARE_COLOURS[w] || CHART_LINE;
        if (d.soldU   > 0) rows.push({ ware: w, colour: col, dir: 'sell', units: d.soldU,   cr:  d.soldCr });
        if (d.boughtU > 0) rows.push({ ware: w, colour: col, dir: 'buy',  units: d.boughtU, cr: -d.boughtCr });
      });
      if (!rows.length) continue;
      rows.sort((a, b) => Math.abs(b.cr) - Math.abs(a.cr));
      const cx = xOf(bucketCentre(i)).toFixed(1), cy = yOf(net[i]).toFixed(1);
      const dotCol = net[i] >= 0 ? CHART_LINE : CHART_LOSS;
      if (hourlyType === 'line') {
        markers.push(`<circle cx="${cx}" cy="${cy}" r="2.2" fill="${dotCol}" style="filter:drop-shadow(0 0 3px ${dotCol})"/>`);
      }
      // hAgo = absolute hours-ago for the bucket start (rounded to nearest hour).
      const tipHAgo = Math.round(offsetHours + i);
      const tip = encodeURIComponent(JSON.stringify({ hAgo: tipHAgo, net: net[i], rows }));
      // Hover column spans the bucket's visible hours exactly — the oldest
      // bucket is capped at the window edge so the rect never leaves the plot.
      const colX1 = xOf(offsetHours + Math.min(i + 1, windowHours));
      const colX2 = xOf(offsetHours + i);
      hitCols.push(`<rect class="cf-col" x="${colX1.toFixed(1)}" y="${mt}" width="${(colX2 - colX1).toFixed(1)}" height="${ph}" data-cashflow-tip="${tip}" onclick="cycleChart('${safeCode}','hourly')"></rect>`);
    }

    // Build the chart-type-specific data layer, clipped to the plot rect.
    const zeroLineHtml = `<line x1="${ml}" y1="${zeroY.toFixed(1)}" x2="${(ml + pw).toFixed(1)}" y2="${zeroY.toFixed(1)}" stroke="${CHART_ACCENT}" stroke-opacity="0.35" stroke-width="1"/>`;
    let dataLayer;
    if (hourlyType === 'bar') {
      // One rect per bucket anchored at the zero line, coloured by profit/loss.
      // Bar width = 80% of one bucket's pixel span so there is a visible gap between bars.
      const barHalf = (pw / windowHours) * 0.40;
      const bars = ordered.map(([x, v]) => {
        const y0 = zeroY, y1 = yOf(v), h = Math.abs(y0 - y1);
        if (h < 0.5) return ''; // skip near-zero bars that would just be slivers
        const col = v >= 0 ? CHART_ACCENT : CHART_LOSS;
        return `<rect x="${(x - barHalf).toFixed(1)}" y="${Math.min(y0, y1).toFixed(1)}" width="${(barHalf * 2).toFixed(1)}" height="${h.toFixed(1)}" fill="${col}" fill-opacity="0.78"/>`;
      }).join('');
      dataLayer = zeroLineHtml + bars;
    } else if (hourlyType === 'scatter') {
      // Circles only — no connecting line, no area fill. Larger radius than the
      // line-mode tick marks so individual hours are easy to spot and hover.
      const dots = ordered.map(([x, v]) => {
        const y = yOf(v).toFixed(1), col = v >= 0 ? CHART_LINE : CHART_LOSS;
        return `<circle cx="${x.toFixed(1)}" cy="${y}" r="3.5" fill="${col}" style="filter:drop-shadow(0 0 5px ${col})" opacity="0.90"/>`;
      }).join('');
      dataLayer = zeroLineHtml + dots;
    } else {
      // Line + area fill (default). Two overlapping polylines produce the glow halo.
      const linePts = ordered.map(([x, v]) => `${x.toFixed(1)},${yOf(v).toFixed(1)}`).join(' ');
      const areaPath = `M ${ordered[0][0].toFixed(1)} ${zeroY.toFixed(1)} ` +
                       ordered.map(([x, v]) => `L ${x.toFixed(1)} ${yOf(v).toFixed(1)}`).join(' ') +
                       ` L ${ordered[ordered.length - 1][0].toFixed(1)} ${zeroY.toFixed(1)} Z`;
      dataLayer = `
        <path d="${areaPath}" fill="url(#${fillId})" stroke="none"/>
        <polyline points="${linePts}" fill="none" stroke="${CHART_GLOW}" stroke-width="3" stroke-linejoin="round" stroke-linecap="round" opacity="0.35" filter="url(#${glowId})"/>
        <polyline points="${linePts}" fill="none" stroke="${CHART_LINE}" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/>
        ${markers.join('')}`;
    }

    // Small pill in the top-right corner of the plot that cycles the chart type.
    // Rendered after the hit columns in document order so it sits above them in
    // z-order and receives the click — tooltip hover still works everywhere else.
    const typeLabel = hourlyType === 'bar' ? 'BAR' : hourlyType === 'scatter' ? 'DOT' : 'LINE';
    const typeIndicator = `
      <g onclick="cycleChart('${safeCode}','hourly')" style="cursor:pointer">
        <rect x="${(ml + pw - 38).toFixed(1)}" y="${(mt + 3).toFixed(1)}" width="36" height="13" rx="2"
              fill="${CHART_ACCENT}10" stroke="${CHART_ACCENT}30" stroke-width="0.5"/>
        <text x="${(ml + pw - 4).toFixed(1)}" y="${(mt + 11).toFixed(1)}" text-anchor="end"
              fill="${CHART_LINE}" fill-opacity="0.75"
              style="font-family:var(--font-data);font-size:0.7rem;letter-spacing:0.08em">${typeLabel} ›</text>
      </g>`;

    return `
      <div style="background:#030d14;border:1px solid rgba(25,230,200,0.18);border-radius:0.3rem;box-shadow:inset 0 0 24px rgba(25,230,200,0.05);padding:0.4rem">
        <svg viewBox="0 0 ${svgW} ${svgH}" style="display:block;width:100%;height:auto">
          <defs>
            <filter id="${glowId}" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="2"/></filter>
            <linearGradient id="${fillId}" x1="0" y1="${mt}" x2="0" y2="${mt + ph}" gradientUnits="userSpaceOnUse">
              <stop offset="0"           stop-color="${CHART_ACCENT}" stop-opacity="0.30"/>
              <stop offset="${zeroFrac}" stop-color="${CHART_ACCENT}" stop-opacity="0.05"/>
              <stop offset="${zeroFrac}" stop-color="${CHART_LOSS}" stop-opacity="0.05"/>
              <stop offset="1"           stop-color="${CHART_LOSS}" stop-opacity="0.30"/>
            </linearGradient>
            <clipPath id="cfclip-${safeCode}-h"><rect x="${ml}" y="${mt}" width="${pw}" height="${ph}"/></clipPath>
          </defs>
          <rect x="${ml}" y="${mt}" width="${pw}" height="${ph}" fill="#020a10" onclick="cycleChart('${safeCode}','hourly')"/>
          ${yAxisHtml(yOf, axBot, axTop, step)}
          ${xTicksHtml}
          <!-- Data layer is clipped to the plot rect so strokes/glow can never
               spill past the axes, whatever the zoom window does. -->
          <g clip-path="url(#cfclip-${safeCode}-h)">
            ${dataLayer}
          </g>
          <line x1="${ml}" y1="${mt}" x2="${ml}" y2="${mt + ph}" stroke="${CHART_ACCENT}" stroke-opacity="0.35" stroke-width="1"/>
          <text x="9" y="${mt + ph / 2}" text-anchor="middle" dominant-baseline="middle" fill="${CHART_LINE}" fill-opacity="0.6"
                style="font-family:var(--font-data);font-size:0.8rem;letter-spacing:0.1em" transform="rotate(-90 9 ${mt + ph / 2})">CREDITS/HR</text>
          ${hitCols.join('')}
          ${typeIndicator}
        </svg>
      </div>
      <div style="display:flex;gap:1.6rem;padding:0.6rem 0.2rem 0.2rem;font-family:var(--font-data);font-size:0.9rem;letter-spacing:0.04em">
        <span style="display:inline-flex;align-items:center;gap:0.5rem;color:${CHART_ACCENT}"><span style="display:inline-block;width:1.1rem;height:0.2rem;background:${CHART_ACCENT};border-radius:0.1rem;filter:drop-shadow(0 0 2px ${CHART_ACCENT})"></span>INCOME (SELLS)</span>
        <span style="display:inline-flex;align-items:center;gap:0.5rem;color:${CHART_LOSS}"><span style="display:inline-block;width:1.1rem;height:0.2rem;background:${CHART_LOSS};border-radius:0.1rem;filter:drop-shadow(0 0 2px ${CHART_LOSS})"></span>SPEND (BUYS)</span>
      </div>`;
  }

  // ── By-Trade body (drill-down) ─────────────────────────────────────────────
  // Size of each individual trade: every vertex is one trade plotted at its
  // signed credit value (sells +, buys −), connected in time order — a spiky
  // line that shows how big each deal was. Hover snaps to the nearest trade.
  function buildCfTradeBody(ctx) {
    const { safeCode, trades, svgW, svgH, ml, mt, pw, ph, xOf, xTicksHtml, yAxisHtml } = ctx;

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

    const tradeType = (cfChartType[safeCode] || {}).trade || 'line';
    const verts = pts.map(p => [xOf(p.hAgo), yOf(p.value)]);

    // Per-trade dots + hover lookup table. Dot radius is slightly larger in
    // scatter mode where there is no line to connect points.
    const store = [];
    const dots = pts.map(p => {
      const x = xOf(p.hAgo), y = yOf(p.value);
      const isSell = p.t.direction === 'Out';
      store.push({
        fx: (x - ml) / pw, vbx: +x.toFixed(1), vby: +y.toFixed(1),
        ware: p.t.ware_name || 'Unknown', colour: WARE_COLOURS[p.t.ware_name] || CHART_LINE,
        dir: isSell ? 'sell' : 'buy', units: p.t.amount, priceEa: p.t.price_cr,
        total: p.value, hAgo: p.hAgo, ship: p.t.ship_code || '', counterparty: p.t.counterparty || '',
      });
      const r = tradeType === 'scatter' ? '2.5' : '1.6';
      return `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${r}" fill="${isSell ? CHART_LINE : CHART_LOSS}" opacity="0.85"/>`;
    }).join('');
    cashflowDetailData[safeCode] = store;

    // Spiky line through each trade's value (line mode only).
    let dataLayer;
    if (tradeType === 'scatter') {
      dataLayer = dots;
    } else {
      const linePts  = verts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
      const areaPath = `M ${verts[0][0].toFixed(1)} ${zeroY.toFixed(1)} ` +
                       verts.map(([x, y]) => `L ${x.toFixed(1)} ${y.toFixed(1)}`).join(' ') +
                       ` L ${verts[verts.length - 1][0].toFixed(1)} ${zeroY.toFixed(1)} Z`;
      dataLayer = `
        <path d="${areaPath}" fill="url(#${fillId})" stroke="none"/>
        <polyline points="${linePts}" fill="none" stroke="${CHART_GLOW}" stroke-width="4" stroke-linejoin="round" stroke-linecap="round" opacity="0.45" filter="url(#${glowId})"/>
        <polyline points="${linePts}" fill="none" stroke="${CHART_LINE_ALT}" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/>
        ${dots}`;
    }

    const tradeTypeLabel = tradeType === 'scatter' ? 'DOT' : 'LINE';
    const tradeTypeIndicator = `
      <g onclick="cycleChart('${safeCode}','trade')" style="cursor:pointer">
        <rect x="${(ml + pw - 38).toFixed(1)}" y="${(mt + 3).toFixed(1)}" width="36" height="13" rx="2"
              fill="${CHART_ACCENT}10" stroke="${CHART_ACCENT}30" stroke-width="0.5"/>
        <text x="${(ml + pw - 4).toFixed(1)}" y="${(mt + 11).toFixed(1)}" text-anchor="end"
              fill="${CHART_LINE}" fill-opacity="0.75"
              style="font-family:var(--font-data);font-size:0.7rem;letter-spacing:0.08em">${tradeTypeLabel} ›</text>
      </g>`;

    return `
      <div style="background:#030d14;border:1px solid rgba(25,230,200,0.18);border-radius:0.3rem;box-shadow:inset 0 0 24px rgba(25,230,200,0.05);padding:0.4rem">
        <svg viewBox="0 0 ${svgW} ${svgH}" style="display:block;width:100%;height:auto">
          <defs>
            <filter id="${glowId}" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="3"/></filter>
            <linearGradient id="${fillId}" x1="0" y1="${mt}" x2="0" y2="${mt + ph}" gradientUnits="userSpaceOnUse">
              <stop offset="0"           stop-color="${CHART_GLOW}" stop-opacity="0.45"/>
              <stop offset="${zeroFrac}" stop-color="${CHART_GLOW}" stop-opacity="0.04"/>
              <stop offset="${zeroFrac}" stop-color="${CHART_LOSS}" stop-opacity="0.04"/>
              <stop offset="1"           stop-color="${CHART_LOSS}" stop-opacity="0.45"/>
            </linearGradient>
            <clipPath id="cfclip-${safeCode}-d"><rect x="${ml}" y="${mt}" width="${pw}" height="${ph}"/></clipPath>
          </defs>
          <rect x="${ml}" y="${mt}" width="${pw}" height="${ph}" fill="#020a10" onclick="cycleChart('${safeCode}','trade')"/>
          ${yAxisHtml(yOf, axBot, axTop, step)}
          ${xTicksHtml}
          <!-- Clipped like the hourly chart — see comment there. -->
          <g clip-path="url(#cfclip-${safeCode}-d)">
            ${dataLayer}
          </g>
          <line x1="${ml}" y1="${mt}" x2="${ml}" y2="${mt + ph}" stroke="${CHART_ACCENT}" stroke-opacity="0.35" stroke-width="1"/>
          <text x="9" y="${mt + ph / 2}" text-anchor="middle" dominant-baseline="middle" fill="${CHART_LINE}" fill-opacity="0.6"
                style="font-family:var(--font-data);font-size:0.8rem;letter-spacing:0.1em" transform="rotate(-90 9 ${mt + ph / 2})">TRADE SIZE · CR</text>
          <!-- Highlight ring follows the nearest trade on hover -->
          <circle class="cf-detail-marker" r="3.8" fill="none" stroke="#ffffff" stroke-width="1.5" style="display:none;pointer-events:none"/>
          <!-- Transparent plot overlay drives nearest-point hover; also cycles chart type on click -->
          <rect data-cfdetail="${safeCode}" x="${ml}" y="${mt}" width="${pw}" height="${ph}" fill="transparent" style="cursor:crosshair" onclick="cycleChart('${safeCode}','trade')"/>
          ${tradeTypeIndicator}
        </svg>
      </div>
      <div style="padding:0.6rem 0.2rem 0.2rem;font-family:var(--font-data);font-size:0.9rem;letter-spacing:0.04em;color:var(--text-brand)">
        ${pts.length.toLocaleString()} trades · individual trade size · hover a point for trade details
      </div>`;
  }

  function cashflowTipHtml(d) {
    // Cash-flow hover: one hour's trade breakdown — the hour's net at top,
    // then a row per ware (sells ▲ green, buys ▼ red) with units and credits.
    const fmtU = cfFmtU;
    const fmtC = n => (n < 0 ? '−' : '+') + Math.abs(Math.round(n)).toLocaleString();
    const span = d.hAgo === 0 ? 'Past hour' : `${d.hAgo}–${d.hAgo + 1}h ago`;
    const MAX = 8;
    const shown = d.rows.slice(0, MAX);
    const more  = d.rows.length - shown.length;
    return `<div style="min-width:23rem;padding:0.2rem 0">
      <div style="display:flex;justify-content:space-between;align-items:baseline;gap:1.2rem;margin-bottom:0.5rem;padding-bottom:0.4rem;border-bottom:1px solid var(--outline)">
        <span style="color:var(--text-brand);font-size:1rem;letter-spacing:0.08em;text-transform:uppercase">${span}</span>
        <span style="color:${d.net >= 0 ? CHART_ACCENT : CHART_LOSS};font-family:var(--font-data);font-size:1.1rem">${fmtC(d.net)} Cr</span>
      </div>` +
      shown.map(r => `
        <div style="display:flex;justify-content:space-between;align-items:baseline;gap:1.2rem;padding:1px 0">
          <span style="font-size:1rem;letter-spacing:0.04em;text-transform:uppercase;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:13rem;color:${r.colour}">
            <span style="color:${r.dir === 'sell' ? CHART_ACCENT : CHART_LOSS}">${r.dir === 'sell' ? '▲' : '▼'}</span> ${r.ware}
          </span>
          <span style="font-family:var(--font-data);font-size:1rem;color:var(--text-secondary);flex-shrink:0;white-space:nowrap">
            ${fmtU(r.units)}u · <span style="color:${r.cr >= 0 ? CHART_ACCENT : CHART_LOSS}">${fmtC(r.cr)}</span>
          </span>
        </div>`).join('') +
      (more > 0 ? `<div style="margin-top:0.4rem;font-size:1rem;color:var(--text-brand)">+${more} more ware${more > 1 ? 's' : ''}</div>` : '') +
    `</div>`;
  }

  function cashflowTradeTipHtml(d) {
    // By-Trade hover: one individual trade's full details + the running total.
    const fmtU = cfFmtU;
    const fmtC = n => (n < 0 ? '−' : '+') + Math.abs(Math.round(n)).toLocaleString();
    const ago  = d.hAgo < 1 ? Math.round(d.hAgo * 60) + 'm ago'
                            : d.hAgo.toFixed(1).replace(/\.0$/, '') + 'h ago';
    // The trade has two "other side" fields: counterparty (the station the
    // goods went to / came from — the scanner resolves this for almost all
    // sells) and ship (the transport, resolved for most buys but often a
    // transient NPC buyer whose ID is a raw "[0x…]" hex on sells). Show the
    // station as the buyer/seller and the transport as the ship; fall back to
    // "Unknown" only when neither resolves.
    const isRawId = s => /^\[?0x[0-9a-f]+\]?$/i.test(String(s).trim());
    const shipResolved = d.ship && !isRawId(d.ship);
    const partyLabel   = d.dir === 'sell' ? 'Buyer' : 'Seller';
    const row = cfRow;
    return `<div style="min-width:22rem;padding:0.2rem 0">
      <div style="display:flex;justify-content:space-between;align-items:baseline;gap:1.2rem;margin-bottom:0.5rem;padding-bottom:0.4rem;border-bottom:1px solid var(--outline)">
        <span style="color:${d.colour};font-size:1.1rem;letter-spacing:0.05em;text-transform:uppercase;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:16rem">
          <span style="color:${d.dir === 'sell' ? CHART_ACCENT : CHART_LOSS}">${d.dir === 'sell' ? '▲ SOLD' : '▼ BOUGHT'}</span> ${d.ware}
        </span>
      </div>` +
      row('Amount × Price', `${fmtU(d.units)} × ${fmtU(d.priceEa)} Cr`) +
      row('Trade value', `${fmtC(d.total)} Cr`, d.total >= 0 ? CHART_ACCENT : CHART_LOSS) +
      (d.counterparty ? row(partyLabel, d.counterparty) : '') +
      (shipResolved   ? row('Ship', d.ship) : '') +
      (!d.counterparty && !shipResolved ? row(partyLabel, 'Unknown') : '') +
      `<div style="margin-top:0.5rem;padding-top:0.4rem;border-top:1px solid var(--outline);text-align:right;font-size:1rem;color:var(--text-brand)">${ago}</div>
    </div>`;
  }

  registerTip('cashflowTip', (el, _e, tip) => {
    // Cash-flow chart: one hour's per-ware trade breakdown.
    tip.innerHTML = cashflowTipHtml(JSON.parse(decodeURIComponent(el.dataset.cashflowTip)));
    tip.style.color      = '';
    tip.style.whiteSpace = 'normal';
    return true;
  });

  registerTip('cfdetail', (el, e, tip) => {
    // By-Trade chart: find the trade nearest the cursor's x position and show its
    // details, with the highlight ring snapped to that point.
    const arr = cashflowDetailData[el.dataset.cfdetail];
    if (!arr || !arr.length) return false;
    const r = el.getBoundingClientRect();
    const f = (e.clientX - r.left) / r.width;
    let best = arr[0], bd = Infinity;
    for (const p of arr) { const dd = Math.abs(p.fx - f); if (dd < bd) { bd = dd; best = p; } }
    tip.innerHTML = cashflowTradeTipHtml(best);
    tip.style.color = '';
    tip.style.whiteSpace = 'normal';
    const svg = el.closest('svg');
    const mk = svg && svg.querySelector('.cf-detail-marker');
    if (mk) { mk.setAttribute('cx', best.vbx); mk.setAttribute('cy', best.vby); mk.style.display = 'block'; }
    return true;
  });
