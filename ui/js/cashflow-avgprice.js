  // Core role: Avg Price panel of the station cash-flow chart — hourly mean trade price for one ware, bars mutated in place so they animate.
  //
  // Unlike the other cash-flow panels (rebuilt via innerHTML on every scrubber
  // frame) this chart is built ONCE (buildAvgPriceBody) then retargeted in place
  // (updateAvgPrice) so its bars CSS-transition between values — a fresh
  // innerHTML each frame can't animate from a prior state. It shares the
  // cash-flow plumbing from cashflow-chart.js: cfStationCache, cfZoom,
  // cfNiceStep/cfFmtY/cfFmtU, and cycleChart.

  const avgWare = {};
  const avgMode = {};

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
      <div style="background:#030d14;border:1px solid rgba(25,230,200,0.18);border-radius:0.3rem;box-shadow:inset 0 0 24px rgba(25,230,200,0.05);padding:0.4rem">
        <svg viewBox="0 0 ${svgW} ${svgH}" style="display:block;width:100%;height:auto">
          <defs>
            <clipPath id="avgclip-${safeCode}"><rect x="${ml}" y="${mt}" width="${pw}" height="${ph}"/></clipPath>
          </defs>
          <rect x="${ml}" y="${mt}" width="${pw}" height="${ph}" fill="#020a10" onclick="cycleChart('${safeCode}','avg')"/>
          <g class="avg-grid"></g>
          <g class="avg-xticks"></g>
          <g class="avg-bars" clip-path="url(#avgclip-${safeCode})"></g>
          <!-- Overlay for line/scatter modes — populated by updateAvgPrice, empty in bar mode -->
          <g class="avg-overlay" clip-path="url(#avgclip-${safeCode})"></g>
          <line x1="${ml}" y1="${mt}" x2="${ml}" y2="${mt + ph}" stroke="${CHART_ACCENT}" stroke-opacity="0.35" stroke-width="1"/>
          <text x="9" y="${mt + ph / 2}" text-anchor="middle" dominant-baseline="middle" fill="${CHART_LINE}" fill-opacity="0.6"
                style="font-family:var(--font-data);font-size:0.8rem;letter-spacing:0.1em" transform="rotate(-90 9 ${mt + ph / 2})">PRICE · CR</text>
          <!-- Readout line: on hover it projects the bar's top across to the
               price axis at that hour's average. Colour set per-hover in JS. -->
          <line class="avg-hot-line" stroke-dasharray="3 3" stroke-width="0.8" style="opacity:0;transition:opacity 0.15s;pointer-events:none"/>
          <!-- Transparent per-hour hit columns (full plot height) drive the
               tooltip + bar highlight; rebuilt each update. -->
          <g class="avg-hits"></g>
          <g class="avg-toggle"></g>
          <!-- Chart-type pill — updated in place by updateAvgPrice on every cycle -->
          <g class="avg-type-pill"></g>
        </svg>
      </div>
      <div class="avg-chips" style="display:flex;flex-wrap:wrap;gap:0.5rem;padding:0.6rem 0.2rem 0.2rem"></div>`;
  }

  // Switch the chart's direction / selected ware (radio); both retarget the bars.
  function setAvgMode(safeCode, mode) {
    if (avgMode[safeCode] === mode) return;
    avgMode[safeCode] = mode;
    // The selected ware may not exist in the new direction — fall back to first.
    const list = avgPriceWareList(safeCode, mode);
    if (!list.includes(avgWare[safeCode])) avgWare[safeCode] = list[0] || null;
    updateAvgPrice(safeCode);
    rebuildPie(safeCode);
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
    const col = ware ? (WARE_COLOURS[ware] || CHART_LINE) : CHART_LINE;

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
      const c = WARE_COLOURS[w] || CHART_LINE, on = w === ware;
      return `<span onclick="setAvgWare('${safeCode}','${w}')"
        style="cursor:pointer;opacity:${on ? '1' : '0.4'};display:inline-flex;align-items:center;
               padding:0.2rem 0.7rem;border-radius:0.2rem;border:1px solid ${c}${on ? 'aa' : '44'};
               background:${c}${on ? '33' : '14'};color:${c};font-family:var(--font-data);
               font-size:1rem;white-space:nowrap;letter-spacing:0.04em;user-select:none">${w}</span>`;
    }).join('') : `<span style="font-family:var(--font-data);font-size:1rem;color:var(--text-brand)">No ${dir} activity in the last 24h</span>`;

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

    const gridEl    = root.querySelector('.avg-grid');
    const xtEl      = root.querySelector('.avg-xticks');
    const barsEl    = root.querySelector('.avg-bars');
    const overlayEl = root.querySelector('.avg-overlay');
    const pillEl    = root.querySelector('.avg-type-pill');
    const avgType   = (cfChartType[safeCode] || {}).avg || 'bar';

    // Empty window: clear axes, collapse any existing bars to the baseline.
    if (!vals.length) {
      gridEl.innerHTML = ''; xtEl.innerHTML = ''; overlayEl.innerHTML = '';
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
      return `<line x1="${ml}" y1="${y}" x2="${ml + pw}" y2="${y}" stroke="${CHART_ACCENT}" stroke-opacity="0.10" stroke-width="0.6"/>
        <text x="${ml - 6}" y="${y}" text-anchor="end" dominant-baseline="middle" fill="${CHART_LINE}" fill-opacity="0.7" style="font-family:var(--font-data);font-size:0.8rem">${cfFmtY(v)}</text>`;
    }).join('');

    // ── X ticks: same adaptive spacing as the other charts ──
    const tickStep = windowHours <= 3 ? 0.5 : windowHours <= 6 ? 1 : windowHours <= 12 ? 2 : 6;
    let xt = '';
    for (let h = Math.ceil(offsetHours / tickStep) * tickStep; h <= offsetHours + windowHours + 0.001; h += tickStep) {
      const x = xOf(h).toFixed(1);
      const label = h === 0 ? 'NOW' : h < 1 ? `-${Math.round(h * 60)}M` : `-${h % 1 !== 0 ? h.toFixed(1) : Math.round(h)}H`;
      xt += `<line x1="${x}" y1="${mt}" x2="${x}" y2="${mt + ph}" stroke="${CHART_ACCENT}" stroke-opacity="0.08" stroke-width="0.6"/>
        <text x="${x}" y="${mt + ph + 13}" text-anchor="middle" fill="${CHART_LINE}" fill-opacity="0.7" style="font-family:var(--font-data);font-size:0.8rem;letter-spacing:0.06em">${label}</text>`;
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
      if (avg[i] == null || avgType !== 'bar') {
        // Collapse bars in non-bar modes so they animate out of sight rather than
        // disappearing instantly — the CSS transition on height still fires.
        r.setAttribute('y', baseY.toFixed(1)); r.setAttribute('height', '0'); r.setAttribute('opacity', '0');
        r.removeAttribute('data-avg-tip');
      } else {
        const y = yOf(avg[i]);
        r.setAttribute('y', y.toFixed(1));
        r.setAttribute('height', Math.max(0, baseY - y).toFixed(1));
        r.setAttribute('opacity', '0.9');
      }
    }

    // ── Line / scatter overlay (non-bar modes) ────────────────────────────────
    // Collect points left-to-right (oldest first) so the polyline connects them
    // in time order. Buckets with no data in this window are skipped.
    if (avgType !== 'bar') {
      const pts = [];
      for (let i = numHours - 1; i >= 0; i--) {
        if (avg[i] == null) continue;
        // Bucket centre: midpoint of the hour slot's pixel span.
        const cx = (xOf(offsetHours + Math.min(i + 1, windowHours)) + xOf(offsetHours + i)) / 2;
        pts.push([cx, yOf(avg[i])]);
      }
      if (avgType === 'line' && pts.length > 1) {
        const ptStr = pts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
        overlayEl.innerHTML = `
          <polyline points="${ptStr}" fill="none" stroke="${col}" stroke-width="3" stroke-linejoin="round" stroke-linecap="round" opacity="0.35" filter="url(#avg-glow-${safeCode})"/>
          <polyline points="${ptStr}" fill="none" stroke="${col}" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round" opacity="0.9"/>
          ${pts.map(([x, y]) => `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="2.5" fill="${col}" opacity="0.9"/>`).join('')}`;
      } else if (avgType === 'scatter') {
        overlayEl.innerHTML = pts.map(([x, y]) =>
          `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="5" fill="${col}" opacity="0.40"/>
           <circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="3" fill="${col}" opacity="0.92"/>`
        ).join('');
      } else {
        overlayEl.innerHTML = ''; // single-point line or empty
      }

      // Ensure the glow filter exists in this SVG — bars don't use it so it isn't
      // in the static scaffold. Add it to <defs> lazily on first non-bar render.
      const svgEl = root.querySelector('svg');
      if (svgEl && !svgEl.querySelector(`#avg-glow-${safeCode}`)) {
        let defsEl = svgEl.querySelector('defs');
        if (!defsEl) { defsEl = document.createElementNS('http://www.w3.org/2000/svg', 'defs'); svgEl.prepend(defsEl); }
        const f = document.createElementNS('http://www.w3.org/2000/svg', 'filter');
        f.setAttribute('id', `avg-glow-${safeCode}`);
        f.setAttribute('x', '-20%'); f.setAttribute('y', '-20%');
        f.setAttribute('width', '140%'); f.setAttribute('height', '140%');
        const blur = document.createElementNS('http://www.w3.org/2000/svg', 'feGaussianBlur');
        blur.setAttribute('stdDeviation', '2');
        f.appendChild(blur);
        defsEl.appendChild(f);
      }
    } else {
      overlayEl.innerHTML = '';
    }

    // ── Type pill (top-right corner, updated every call) ─────────────────────
    const avgTypeLabel = avgType === 'line' ? 'LINE' : avgType === 'scatter' ? 'DOT' : 'BAR';
    pillEl.innerHTML = `
      <rect x="${(ml + pw - 38).toFixed(1)}" y="${(mt + 3).toFixed(1)}" width="36" height="13" rx="2"
            fill="${CHART_ACCENT}10" stroke="${CHART_ACCENT}30" stroke-width="0.5" onclick="cycleChart('${safeCode}','avg')" style="cursor:pointer"/>
      <text x="${(ml + pw - 4).toFixed(1)}" y="${(mt + 11).toFixed(1)}" text-anchor="end"
            fill="${CHART_LINE}" fill-opacity="0.75" onclick="cycleChart('${safeCode}','avg')" style="cursor:pointer;font-family:var(--font-data);font-size:0.7rem;letter-spacing:0.08em">${avgTypeLabel} ›</text>`;

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
      hitsHtml += `<rect class="avg-hit" data-avgtip="${tipData}" data-avg-i="${i}" x="${x.toFixed(1)}" y="${mt}" width="${Math.max(0.5, w).toFixed(1)}" height="${ph}" fill="transparent" style="cursor:crosshair" onclick="cycleChart('${safeCode}','avg')"/>`;
    }
    root.querySelector('.avg-hits').innerHTML = hitsHtml;
  }

  // ── Tooltip ────────────────────────────────────────────────────────────────
  // Lives here with the chart that stamps data-avgtip (same convention as the
  // other cash-flow tooltip builders in cashflow-chart.js).

  function avgPriceTipHtml(d) {
    // Avg Price hover: the hour's mean price (big), how it moved vs the
    // previous traded hour (teal ▲ / red ▼), the min–max spread that hour as a
    // little band with a glowing marker at the average, and the trade count.
    const fmtU = cfFmtU;
    const span = d.hAgo === 0 ? 'Past hour' : `${d.hAgo}–${d.hAgo + 1}h ago`;
    const dirLabel = d.dir === 'sell' ? '▲ SOLD' : '▼ BOUGHT';
    const dirCol   = d.dir === 'sell' ? CHART_ACCENT : CHART_LOSS;

    // Delta vs the previous populated hour.
    let deltaHtml = `<span style="color:var(--text-brand);font-size:1rem">first hour</span>`;
    if (d.prevAvg != null && d.prevAvg > 0) {
      const diff = d.avg - d.prevAvg;
      const pct  = Math.abs(diff / d.prevAvg * 100);
      const flat = Math.abs(diff) < 0.005 * d.prevAvg;
      const c    = flat ? 'var(--text-brand)' : diff > 0 ? CHART_ACCENT : CHART_LOSS;
      const ch   = flat ? '▬' : diff > 0 ? '▲' : '▼';
      deltaHtml  = `<span style="color:${c};font-family:var(--font-data);font-size:1.1rem">${ch} ${pct.toFixed(1)}%</span>`;
    }

    // Marker position within the hour's min–max range (clamped).
    const range   = (d.max - d.min) || 1;
    const avgFrac = Math.max(0, Math.min(1, (d.avg - d.min) / range)) * 100;
    const spread  = d.max > d.min
      ? `<div style="display:flex;justify-content:space-between;font-size:0.9rem;color:var(--text-brand);font-family:var(--font-data);margin-bottom:0.2rem">
           <span>${fmtU(d.min)}</span><span style="letter-spacing:0.12em">SPREAD</span><span>${fmtU(d.max)}</span>
         </div>
         <div style="position:relative;height:0.5rem;background:${d.colour}22;border-radius:0.3rem;margin-bottom:0.6rem;overflow:visible">
           <div style="position:absolute;inset:0;background:linear-gradient(90deg,${d.colour}33,${d.colour}66);border-radius:0.3rem"></div>
           <div style="position:absolute;left:${avgFrac.toFixed(1)}%;top:50%;width:0.7rem;height:0.7rem;border-radius:50%;background:${d.colour};transform:translate(-50%,-50%);box-shadow:0 0 0.5rem ${d.colour}"></div>
         </div>`
      : `<div style="font-size:0.9rem;color:var(--text-brand);font-family:var(--font-data);margin-bottom:0.6rem">single trade · no spread</div>`;

    return `<div style="min-width:21rem;padding:0.2rem 0">
      <div style="display:flex;justify-content:space-between;align-items:baseline;gap:1.2rem;margin-bottom:0.6rem;padding-bottom:0.4rem;border-bottom:1px solid var(--outline)">
        <span style="color:${d.colour};font-size:1.1rem;letter-spacing:0.05em;text-transform:uppercase;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:16rem">
          <span style="color:${dirCol}">${dirLabel}</span> ${d.ware}
        </span>
        <span style="color:var(--text-brand);font-size:1rem;letter-spacing:0.06em;white-space:nowrap">${span}</span>
      </div>
      <div style="display:flex;align-items:baseline;justify-content:space-between;gap:1rem;margin-bottom:0.7rem">
        <span style="font-family:var(--font-data);font-size:1.8rem;color:${d.colour};line-height:1">${fmtU(d.avg)}<span style="font-size:1rem;color:var(--text-brand)"> cr avg</span></span>
        ${deltaHtml}
      </div>
      ${spread}
      <div style="display:flex;justify-content:space-between;gap:1.2rem">
        <span style="color:var(--text-brand);font-size:1rem">Trades this hour</span>
        <span style="color:var(--text-secondary);font-family:var(--font-data);font-size:1rem">${d.count}</span>
      </div>
    </div>`;
  }

  registerTip('avgtip', (el, _e, tip) => {
    // Avg Price chart: hour stats + highlight the bar and project a dashed readout
    // line from its top across to the price axis.
    const d = JSON.parse(decodeURIComponent(el.dataset.avgtip));
    tip.innerHTML       = avgPriceTipHtml(d);
    tip.style.color     = '';
    tip.style.whiteSpace = 'normal';
    const svg  = el.closest('svg');
    const bars = svg && svg.querySelector('.avg-bars');
    const bar  = bars && bars.children[+el.dataset.avgI];
    if (bar) {
      bar.classList.add('avg-hot');
      const y  = +bar.getAttribute('y');
      const cx = +bar.getAttribute('x') + (+bar.getAttribute('width')) / 2;
      const line = svg.querySelector('.avg-hot-line');
      if (line) {
        line.setAttribute('x1', 56); // ml — the price axis
        line.setAttribute('x2', cx.toFixed(1));
        line.setAttribute('y1', y.toFixed(1));
        line.setAttribute('y2', y.toFixed(1));
        line.setAttribute('stroke', d.colour);
        line.style.opacity = '1';
      }
    }
    return true;
  });
