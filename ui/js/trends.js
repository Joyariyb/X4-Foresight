  // Core role: Renders the Trends tab — empire trajectory line chart, all-time
  // trade totals, and the changes[] event feed — from data.trends / data.changes.
  //
  // Reads the cross-scan section the DB-read export attaches (db/trends.py):
  //   data.trends.series  — shared `scans` x-axis + one parallel array per metric
  //   data.trends.windows — all-time cumulative trade totals across the 3 ledgers
  //   data.changes        — newest-first event feed (built/lost/crossing/milestone)
  //
  // Single-scan saves produce a one-point series and an empty feed; both states are
  // handled (a lone dot, and a friendly placeholder) rather than left blank.

  // Cached on each render so the metric toggle can redraw the chart without the
  // whole export. _trendMetric persists the user's selected line across redraws.
  let _trendSeries = {};
  let _trendScans  = [];
  let _trendMetric = 'net_worth';

  // Which lines the toggle offers. `count` flags integer metrics (ships/stations)
  // so the axis and headline don't get credit-style M/k formatting. Colours are
  // hex literals because they end up in SVG stroke/fill attrs (CSS vars don't
  // resolve there — same reason constants.js keeps the CHART_* palette as hex).
  const TREND_METRICS = [
    { key: 'net_worth',     label: 'Net Worth',    color: CHART_ACCENT },
    { key: 'credits',       label: 'Credits',      color: '#fdd835' },
    { key: 'station_cash',  label: 'Station Cash', color: '#5eead4' },
    { key: 'ship_count',    label: 'Ships',        color: '#38bdf8', count: true },
    { key: 'station_count', label: 'Stations',     color: '#a3e635', count: true },
  ];

  // ── small helpers ──────────────────────────────────────────────────────────
  // "Nice" axis step (1/2/2.5/5 × 10ⁿ) so gridlines land on round numbers.
  const _trNiceStep = (range, target) => {
    const raw  = Math.max(range, 1) / target;
    const mag  = Math.pow(10, Math.floor(Math.log10(raw)));
    const norm = raw / mag;
    const nice = norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 2.5 ? 2.5 : norm <= 5 ? 5 : 10;
    return nice * mag;
  };
  // Compact axis label: integer counts as-is, credit values as B/M/k.
  const _trFmtAxis = (v, count) => {
    if (count) return Math.round(v).toLocaleString();
    const a = Math.abs(v);
    return a >= 1e9 ? (v / 1e9).toFixed(a % 1e9 ? 1 : 0) + 'B'
         : a >= 1e6 ? (v / 1e6).toFixed(a % 1e6 ? 1 : 0) + 'M'
         : a >= 1e3 ? (v / 1e3).toFixed(a % 1e3 ? 1 : 0) + 'k'
         : String(Math.round(v));
  };
  // Headline value: full credits via the shared formatter, or a plain count.
  const _trFmtHead = (v, count) =>
    v == null ? '—' : count ? Math.round(v).toLocaleString() : fmtCredits(v);
  // Short real-world date for a scan stamp.
  const _trDate = iso => {
    if (!iso) return '';
    const d = new Date(iso);
    return isNaN(d) ? '' : d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  };

  // ── trajectory chart ───────────────────────────────────────────────────────
  // One metric at a time (selected by the toggle). viewBox units are the drawing
  // space, so text uses bare font-size attributes (NOT rem) — rem double-scales
  // through the viewBox transform in QtWebEngine.
  function _trendChartSvg(metric) {
    const vals = _trendSeries[metric.key] || [];
    const n    = _trendScans.length;
    if (!n) return `<div class="trend-empty">No trend data yet.</div>`;

    const W = 720, H = 300, ml = 66, mr = 20, mt = 18, mb = 36;
    const pw = W - ml - mr, ph = H - mt - mb;

    // A single scan can't draw a line; centre the lone point so it reads as "now".
    const xOf = i => n === 1 ? ml + pw / 2 : ml + (i / (n - 1)) * pw;

    // Baseline at 0 (credits/counts never go below it in practice) unless a value
    // is negative, in which case include it so the line stays on-canvas.
    const numeric = vals.map(v => v == null ? 0 : v);
    const lo = Math.min(0, ...numeric);
    let   hi = Math.max(...numeric);
    if (hi === lo) hi = lo + 1;                         // flat series → avoid /0
    const step  = _trNiceStep(hi - lo, 5);
    const axTop = Math.ceil(hi / step) * step || step;
    const axBot = Math.floor(lo / step) * step;
    const yOf   = v => mt + ph - (v - axBot) / (axTop - axBot) * ph;

    // y grid + labels
    let yAxis = '';
    for (let v = axBot; v <= axTop + step * 0.001; v += step) {
      const y = yOf(v).toFixed(1);
      const zero = Math.abs(v) < step * 0.001;
      yAxis += `<line x1="${ml}" y1="${y}" x2="${ml + pw}" y2="${y}" stroke="${CHART_ACCENT}" stroke-opacity="${zero ? 0.3 : 0.09}" stroke-width="${zero ? 1 : 0.6}"/>`
             + `<text x="${ml - 7}" y="${y}" text-anchor="end" dominant-baseline="middle" fill="${CHART_LINE}" fill-opacity="0.7" font-family="var(--font-mono)" font-size="11">${_trFmtAxis(v, metric.count)}</text>`;
    }

    // x labels: each scan's #id, thinned out when there are many.
    const xStep = n <= 10 ? 1 : Math.ceil(n / 10);
    let xAxis = '';
    _trendScans.forEach((s, i) => {
      if (i % xStep !== 0 && i !== n - 1) return;
      const x = xOf(i).toFixed(1);
      xAxis += `<text x="${x}" y="${mt + ph + 16}" text-anchor="middle" fill="${CHART_LINE}" fill-opacity="0.65" font-family="var(--font-mono)" font-size="11">#${s.scan_id}</text>`;
    });

    // line + area + dots
    const pts = numeric.map((v, i) => [xOf(i), yOf(v)]);
    const linePts = pts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
    const baseY = yOf(axBot < 0 ? 0 : axBot).toFixed(1);
    const areaPath = `M ${pts[0][0].toFixed(1)} ${baseY} `
      + pts.map(([x, y]) => `L ${x.toFixed(1)} ${y.toFixed(1)}`).join(' ')
      + ` L ${pts[pts.length - 1][0].toFixed(1)} ${baseY} Z`;
    const fillId = 'trend-fill';

    // Glow via a stacked faint halo + solid core (two plain circles) rather than
    // a per-dot CSS `filter: drop-shadow`. In QtWebEngine every filtered element
    // becomes its own render surface that gets re-rasterised on each scroll frame,
    // and we draw one dot per scan — so a long scan history turns into N filters
    // repainting as #content scrolls, which is the source of the scroll lag. The
    // halo-circle trick composites for free and is the same glow the cashflow
    // chart uses for its markers (and why the line glow above is a fat polyline).
    const r = n === 1 ? 4 : 2.6;
    const dots = pts.map(([x, y], i) => {
      const s = _trendScans[i];
      const cx = x.toFixed(1), cy = y.toFixed(1);
      const title = `#${s.scan_id} · ${_trDate(s.scanned_at)} · ${_trFmtHead(vals[i], metric.count)}`;
      return `<circle cx="${cx}" cy="${cy}" r="${(r * 2.2).toFixed(1)}" fill="${metric.color}" opacity="0.18"/>`
           + `<circle cx="${cx}" cy="${cy}" r="${r}" fill="${metric.color}"><title>${title}</title></circle>`;
    }).join('');

    // n>1 draws the glow+line; a single point is just the dot.
    const lineLayer = n === 1 ? '' : `
      <path d="${areaPath}" fill="url(#${fillId})" stroke="none"/>
      <polyline points="${linePts}" fill="none" stroke="${CHART_GLOW}" stroke-width="3" stroke-linejoin="round" stroke-linecap="round" opacity="0.35"/>
      <polyline points="${linePts}" fill="none" stroke="${metric.color}" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/>`;

    return `
      <div class="trend-chart-card">
        <svg viewBox="0 0 ${W} ${H}" style="display:block;width:100%;height:auto">
          <defs>
            <linearGradient id="${fillId}" x1="0" y1="${mt}" x2="0" y2="${mt + ph}" gradientUnits="userSpaceOnUse">
              <stop offset="0" stop-color="${metric.color}" stop-opacity="0.28"/>
              <stop offset="1" stop-color="${metric.color}" stop-opacity="0.02"/>
            </linearGradient>
          </defs>
          <rect x="${ml}" y="${mt}" width="${pw}" height="${ph}" fill="#020a10"/>
          ${yAxis}
          ${xAxis}
          <line x1="${ml}" y1="${mt}" x2="${ml}" y2="${mt + ph}" stroke="${CHART_ACCENT}" stroke-opacity="0.35" stroke-width="1"/>
          ${lineLayer}
          ${dots}
        </svg>
      </div>`;
  }

  // Called by the metric toggle buttons; swaps the active line in place.
  function setTrendMetric(key) {
    _trendMetric = key;
    const host = document.getElementById('trend-chart');
    if (host) host.innerHTML = _trendChartSvg(TREND_METRICS.find(m => m.key === key));
    document.querySelectorAll('#trend-metric-toggle .trend-toggle-btn')
      .forEach(b => b.classList.toggle('active', b.dataset.metric === key));
  }

  // ── changes feed ─────────────────────────────────────────────────────────────
  // Map each event type to an icon + colour + one-line description.
  function _changeDesc(c) {
    const b = s => `<b style="color:var(--text-primary)">${s ?? '?'}</b>`;
    switch (c.type) {
      case 'station_built':
        return { icon: 'ti-building-factory-2', color: 'var(--color-positive)',
                 text: `Station built — ${b(c.code)}${c.name ? ' · ' + c.name : ''} in ${c.sector_name || c.sector_macro || '—'}` };
      case 'station_lost':
        return { icon: 'ti-flame', color: 'var(--color-negative)',
                 text: `Station lost — ${b(c.code)}${c.name ? ' · ' + c.name : ''}` };
      case 'ship_gained':
        return { icon: 'ti-rocket', color: 'var(--color-primary)',
                 text: `Ship acquired — ${b(c.code)} · ${c.type_name || c.name || '—'}` };
      case 'ship_lost':
        return { icon: 'ti-circle-x', color: 'var(--color-negative)',
                 text: `Ship lost — ${b(c.code)} · ${c.type_name || c.name || '—'}` };
      case 'reputation_crossing': {
        const up = c.direction === 'up';
        return { icon: up ? 'ti-trending-up' : 'ti-trending-down',
                 color: up ? 'var(--color-positive)' : 'var(--color-warning)',
                 text: `${c.faction_name || c.faction} — ${c.from_tier} → ${b(c.to_tier)}` };
      }
      case 'milestone':
        return { icon: 'ti-trophy', color: 'var(--color-warning)', text: c.label || 'Milestone' };
      default:
        return { icon: 'ti-point', color: 'var(--text-secondary)', text: c.type };
    }
  }

  // Group the (already newest-first) feed by detecting scan, with a header per scan.
  function _changesFeedHtml(changes) {
    if (!changes.length) {
      return `<div class="panel trend-feed-empty">
        <i class="ti ti-history"></i>
        No changes recorded yet. Scan the same save again after time passes in-game to start tracking your empire's history.
      </div>`;
    }
    let html = '', lastScan = null;
    changes.forEach(c => {
      if (c.scan_id !== lastScan) {
        lastScan = c.scan_id;
        const gh = c.game_time_s != null ? Math.round(c.game_time_s / 3600) + 'h' : '';
        html += `<div class="trend-scan-group">
          <span class="trend-scan-id">Scan #${c.scan_id}</span>
          <span class="trend-scan-date">${_trDate(c.scanned_at)}${gh ? ' · ' + gh : ''}</span>
          <div class="trend-scan-line"></div>
        </div>`;
      }
      const d = _changeDesc(c);
      html += `<div class="trend-change-row">
        <i class="ti ${d.icon} trend-change-icon" style="color:${d.color}"></i>
        <span class="trend-change-text">${d.text}</span>
      </div>`;
    });
    return `<div class="panel trend-feed">${html}</div>`;
  }

  // ── trade-window cards ───────────────────────────────────────────────────────
  function _tradeCardsHtml(windows) {
    const bucket = (windows.buckets || [])[0];
    if (!bucket) return '';
    const st = bucket.station_trades || {}, mn = bucket.mining_deliveries || {}, it = bucket.internal_transfers || {};
    const net = st.net_cr || 0;
    const cards = [
      { label: 'Trade Profit',  value: fmtCredits(net), cls: net >= 0 ? 'green' : 'red', icon: 'ti-coin' },
      { label: 'Sold',          value: fmtCredits(st.sold_cr || 0),   cls: '',      icon: 'ti-arrow-up-right' },
      { label: 'Bought',        value: fmtCredits(st.bought_cr || 0), cls: '',      icon: 'ti-arrow-down-left' },
      { label: 'Volume Traded', value: (st.volume_units || 0).toLocaleString(), cls: '', icon: 'ti-package' },
      { label: 'Mining Value',  value: fmtCredits(mn.value_cr || 0),  cls: 'amber', icon: 'ti-shovel' },
      { label: 'Internal Value', value: fmtCredits(it.value_cr || 0), cls: '',      icon: 'ti-arrows-exchange' },
    ];
    return cards.map(c => `<div class="card">
      <div class="card-top"><i class="ti ${c.icon}"></i><div class="lbl">${c.label}</div></div>
      <div class="val ${c.cls}">${c.value}</div>
    </div>`).join('');
  }

  // ── entry point (called from populate()) ─────────────────────────────────────
  function renderTrends(data) {
    const root = document.getElementById('trends-root');
    if (!root) return;

    const trends  = data.trends  || {};
    _trendSeries  = trends.series || {};
    _trendScans   = _trendSeries.scans || [];
    const windows = trends.windows || { buckets: [] };
    const changes = data.changes  || [];

    // Nav badge: how many events the feed holds.
    const badge = document.getElementById('nav-trends-count');
    if (badge) badge.textContent = changes.length;

    // Headline for the currently-selected metric: latest value + change vs the
    // previous scan, so the trajectory has a number, not just a curve.
    const metric = TREND_METRICS.find(m => m.key === _trendMetric) || TREND_METRICS[0];
    const vals   = _trendSeries[metric.key] || [];
    const n      = _trendScans.length;
    const latest = n ? vals[n - 1] : null;
    const prev   = n > 1 ? vals[n - 2] : null;
    let deltaHtml = '';
    if (latest != null && prev != null) {
      const d = latest - prev;
      const col = d > 0 ? 'var(--color-positive)' : d < 0 ? 'var(--color-negative)' : 'var(--text-secondary)';
      const arrow = d > 0 ? '▲' : d < 0 ? '▼' : '·';
      deltaHtml = `<span class="trends-delta" style="color:${col}">${arrow} ${_trFmtHead(Math.abs(d), metric.count)} since last scan</span>`;
    }

    const toggle = TREND_METRICS.map(m =>
      `<button class="trend-toggle-btn ${m.key === _trendMetric ? 'active' : ''}" data-metric="${m.key}" onclick="setTrendMetric('${m.key}')">${m.label}</button>`
    ).join('');

    root.innerHTML = `
      <div class="trends-head">
        <div class="trends-title">Empire Trajectory</div>
        <div class="trends-sub">${n} scan${n === 1 ? '' : 's'} on record</div>
      </div>

      <div class="sec-header"><div class="sec-title">${metric.label}</div><div class="sec-line"></div></div>
      <div class="trends-headline">
        <div class="trends-metric-value" style="color:${metric.color}">${_trFmtHead(latest, metric.count)}</div>
        ${deltaHtml}
      </div>
      <div id="trend-metric-toggle" class="trend-toggle">${toggle}</div>
      <div id="trend-chart">${_trendChartSvg(metric)}</div>

      <div class="trends-section">
        <div class="sec-header"><div class="sec-title">Trade Totals · All-Time</div><div class="sec-line"></div></div>
        <div class="cards-row">${_tradeCardsHtml(windows)}</div>
      </div>

      <div class="trends-section">
        <div class="sec-header"><div class="sec-title">Recent Changes</div><div class="sec-line"></div></div>
        ${_changesFeedHtml(changes)}
      </div>`;
  }
