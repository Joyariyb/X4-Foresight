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
  // Faction-reputation series (its own multi-line chart, not part of the toggle).
  let _trendReputation = [];

  // Which lines the toggle offers. `count` flags integer metrics (ships/stations)
  // so the axis and headline don't get credit-style M/k formatting. `multi` flags
  // the odd one out — reputation — which is a many-faction chart on a fixed scale
  // rather than a single line with a headline number, so it renders its own way
  // (see _trendPanelHtml). Colours are hex literals because they end up in SVG
  // stroke/fill attrs (CSS vars don't resolve there — same reason constants.js
  // keeps the CHART_* palette as hex).
  const TREND_METRICS = [
    { key: 'net_worth',     label: 'Net Worth',    color: CHART_ACCENT },
    { key: 'credits',       label: 'Credits',      color: '#fdd835' },
    { key: 'station_cash',  label: 'Station Cash', color: '#5eead4' },
    { key: 'ship_count',    label: 'Ships',        color: '#38bdf8', count: true },
    { key: 'station_count', label: 'Stations',     color: '#a3e635', count: true },
    { key: 'reputation',    label: 'Reputation',   color: CHART_LINE,  multi: true },
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

  // ── shared chart scaffold ────────────────────────────────────────────────────
  // The Trends tab has two charts behind the metric toggle: the single-metric
  // trajectory (_trendChartSvg) and the multi-line faction reputation view
  // (_reputationChartSvg). Their DATA layers differ — one area-filled line vs many
  // thin faction lines — but the FRAME must be pixel-identical so the box doesn't
  // jump when you switch tabs. Everything common (geometry, plot box, axes, the
  // outer panel) lives here so a layout tweak lands once, not in two places that
  // can drift. viewBox units are the drawing space, so all text uses bare font-size
  // attributes (NOT rem) — rem double-scales through the viewBox transform in
  // QtWebEngine.
  const TR_GEO = { W: 720, H: 300, ml: 66, mr: 20, mt: 18, mb: 36 };
  TR_GEO.pw = TR_GEO.W - TR_GEO.ml - TR_GEO.mr;
  TR_GEO.ph = TR_GEO.H - TR_GEO.mt - TR_GEO.mb;

  // x of scan index i. A single scan can't span a line, so centre its lone point.
  const _trXOf = (i, n) => {
    const { ml, pw } = TR_GEO;
    return n === 1 ? ml + pw / 2 : ml + (i / (n - 1)) * pw;
  };

  // y gridlines + value labels from a list of { v, text, zero } ticks (v in data
  // units; yOf maps it to canvas space). The `zero` tick draws brighter as the
  // baseline. Callers choose the tick values + formatting; the markup is shared so
  // both charts' grids are identical.
  function _trYAxis(ticks, yOf) {
    const { ml, pw } = TR_GEO;
    return ticks.map(t => {
      const y = yOf(t.v).toFixed(1);
      return `<line x1="${ml}" y1="${y}" x2="${ml + pw}" y2="${y}" stroke="${CHART_ACCENT}" stroke-opacity="${t.zero ? 0.3 : 0.09}" stroke-width="${t.zero ? 1 : 0.6}"/>`
           + `<text x="${ml - 7}" y="${y}" text-anchor="end" dominant-baseline="middle" fill="${CHART_LINE}" fill-opacity="0.7" font-family="var(--font-mono)" font-size="11">${t.text}</text>`;
    }).join('');
  }

  // x labels: each scan's #id along the bottom, thinned out when there are many.
  function _trXAxis(n) {
    const { mt, ph } = TR_GEO;
    const xStep = n <= 10 ? 1 : Math.ceil(n / 10);
    let out = '';
    _trendScans.forEach((s, i) => {
      if (i % xStep !== 0 && i !== n - 1) return;
      out += `<text x="${_trXOf(i, n).toFixed(1)}" y="${mt + ph + 16}" text-anchor="middle" fill="${CHART_LINE}" fill-opacity="0.65" font-family="var(--font-mono)" font-size="11">#${s.scan_id}</text>`;
    });
    return out;
  }

  // Wraps a chart's axes + data in the shared panel/svg/plot-rect/left-axis-line.
  // `defs` is optional extra <defs> (the trajectory chart's gradient). Draw order
  // is plot bg → axes → left axis line → data on top, matching both old charts.
  function _trChartFrame({ defs = '', axes = '', data = '' }) {
    const { W, H, ml, mt, pw, ph } = TR_GEO;
    return `
      <div style="background:#030d14;border:1px solid rgba(25,230,200,0.18);border-radius:0.3rem;box-shadow:inset 0 0 24px rgba(25,230,200,0.05);padding:0.4rem">
        <svg viewBox="0 0 ${W} ${H}" style="display:block;width:100%;height:auto">
          ${defs ? `<defs>${defs}</defs>` : ''}
          <rect x="${ml}" y="${mt}" width="${pw}" height="${ph}" fill="#020a10"/>
          ${axes}
          <line x1="${ml}" y1="${mt}" x2="${ml}" y2="${mt + ph}" stroke="${CHART_ACCENT}" stroke-opacity="0.35" stroke-width="1"/>
          ${data}
        </svg>
      </div>`;
  }

  // ── trajectory chart ───────────────────────────────────────────────────────
  // One metric at a time (selected by the toggle), drawn into the shared frame.
  function _trendChartSvg(metric) {
    const vals = _trendSeries[metric.key] || [];
    const n    = _trendScans.length;
    if (!n) return `<div style="padding:1.6rem;font-family:var(--font-mono);color:var(--text-faint)">No trend data yet.</div>`;

    const { mt, ph } = TR_GEO;
    const xOf = i => _trXOf(i, n);

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

    // y ticks: every step from axBot..axTop, formatted per metric. The float
    // accumulator means the zero line is "close to 0", not exactly equal.
    const ticks = [];
    for (let v = axBot; v <= axTop + step * 0.001; v += step)
      ticks.push({ v, text: _trFmtAxis(v, metric.count), zero: Math.abs(v) < step * 0.001 });

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

    const defs = `<linearGradient id="${fillId}" x1="0" y1="${mt}" x2="0" y2="${mt + ph}" gradientUnits="userSpaceOnUse">
            <stop offset="0" stop-color="${metric.color}" stop-opacity="0.28"/>
            <stop offset="1" stop-color="${metric.color}" stop-opacity="0.02"/>
          </linearGradient>`;

    return _trChartFrame({
      defs,
      axes: _trYAxis(ticks, yOf) + _trXAxis(n),
      data: lineLayer + dots,
    });
  }

  // Builds the swappable panel for the selected metric: section title, then either
  // a single headline number + delta + line chart (the credit/count metrics) or the
  // multi-line reputation chart + legend. Kept as one function so the toggle can
  // re-render the WHOLE block — title and headline included — not just the chart,
  // so a credits headline never sits stale above a reputation chart.
  function _trendPanelHtml(metric) {
    const m = metric || TREND_METRICS[0];
    const title = `<div class="sec-header"><div class="sec-title">${m.label}</div><div class="sec-line"></div></div>`;

    // Reputation: many factions on the fixed -30..+30 scale, so the "headline" is
    // the faction count rather than a single value — but it uses the SAME big-number
    // + descriptor layout as the other metrics so the panel reads consistently.
    if (m.multi) {
      const facs = _trendReputation.length;
      return title
        + `<div style="display:flex;align-items:baseline;gap:1.2rem;margin-bottom:0.6rem">
            <div style="font-family:var(--font-cond);font-weight:700;font-size:2.4rem;color:${m.color}">${facs}</div>
            <span style="font-family:var(--font-mono);font-size:1.1rem;color:var(--text-dim)">faction${facs === 1 ? '' : 's'} tracked · in-game −30 to +30 scale</span>
          </div>`
        + `<div>${_reputationChartSvg()}</div>`
        + `<div style="display:flex;flex-wrap:wrap;gap:0.6rem 1.4rem;margin-top:0.7rem">${_reputationLegendHtml()}</div>`;
    }

    // Single-metric headline: latest value + change vs the previous scan, so the
    // trajectory carries a number, not just a curve.
    const vals   = _trendSeries[m.key] || [];
    const n      = _trendScans.length;
    const latest = n ? vals[n - 1] : null;
    const prev   = n > 1 ? vals[n - 2] : null;
    let deltaHtml = '';
    if (latest != null && prev != null) {
      const d = latest - prev;
      const col = d > 0 ? 'var(--green)' : d < 0 ? 'var(--red)' : 'var(--text-faint)';
      const arrow = d > 0 ? '▲' : d < 0 ? '▼' : '·';
      deltaHtml = `<span style="font-family:var(--font-mono);font-size:1.1rem;color:${col}">${arrow} ${_trFmtHead(Math.abs(d), m.count)} since last scan</span>`;
    }
    return title
      + `<div style="display:flex;align-items:baseline;gap:1.2rem;margin-bottom:0.6rem">
          <div style="font-family:var(--font-cond);font-weight:700;font-size:2.4rem;color:${m.color}">${_trFmtHead(latest, m.count)}</div>
          ${deltaHtml}
        </div>`
      + `<div>${_trendChartSvg(m)}</div>`;
  }

  // Called by the metric toggle buttons; swaps the active panel in place.
  function setTrendMetric(key) {
    _trendMetric = key;
    const host = document.getElementById('trend-panel');
    if (host) host.innerHTML = _trendPanelHtml(TREND_METRICS.find(m => m.key === key));
    document.querySelectorAll('#trend-metric-toggle .cf-toggle-btn')
      .forEach(b => b.classList.toggle('active', b.dataset.metric === key));
  }

  // ── faction reputation chart ─────────────────────────────────────────────────
  // Multi-line: one line per faction on the in-game -30..+30 reputation scale, drawn
  // into the SAME frame as the trajectory chart (see _trChartFrame) so the box is
  // identical between tabs. Unlike the trajectory chart this draws every faction at
  // once (no toggle) — the point is comparing factions against each other over time.
  // Gridlines sit on the tier thresholds (Allied/Friendly/Neutral/Hostile/At War
  // from data/factions.py), so a line's vertical band reads as its standing.
  function _reputationChartSvg() {
    const facs = _trendReputation;
    const n    = _trendScans.length;
    if (!facs.length || !n)
      return `<div style="padding:1.6rem;font-family:var(--font-mono);color:var(--text-faint)">No reputation history yet.</div>`;

    const { mt, ph } = TR_GEO;
    const LO = -30, HI = 30;                          // the fixed in-game scale
    const xOf = i => _trXOf(i, n);
    const yOf = v => mt + ph - (v - LO) / (HI - LO) * ph;

    // Tier-threshold ticks (the value's meaning, not arbitrary "nice" steps).
    const ticks = [20, 10, 0, -10, -30].map(v =>
      ({ v, text: (v > 0 ? '+' : '') + v, zero: v === 0 }));

    // One line per faction, coloured from the shared FACTION_COLOURS map. Nulls
    // break the path into separate subpaths (a scan where a faction is absent is a
    // gap, not a drop to the floor — 0 is a real reputation value, not "missing").
    let lines = '';
    facs.forEach(f => {
      const col = (typeof FACTION_COLOURS !== 'undefined' && FACTION_COLOURS[f.faction_id]) || '#6e7681';
      let d = '', pen = false;
      f.values.forEach((v, i) => {
        if (v == null) { pen = false; return; }      // lift the pen across gaps
        d += (pen ? 'L' : 'M') + xOf(i).toFixed(1) + ' ' + yOf(v).toFixed(1) + ' ';
        pen = true;
      });
      if (d) lines += `<path d="${d.trim()}" fill="none" stroke="${col}" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round" opacity="0.9"/>`;
      // A dot at every known point — carries the hover tooltip and is the only mark
      // a single-scan (one-column) history can show.
      f.values.forEach((v, i) => {
        if (v == null) return;
        const s = _trendScans[i];
        lines += `<circle cx="${xOf(i).toFixed(1)}" cy="${yOf(v).toFixed(1)}" r="${n === 1 ? 3.5 : 2.2}" fill="${col}"><title>${f.faction_name || f.faction_id} · #${s.scan_id} · ${v.toFixed(1)}</title></circle>`;
      });
    });

    return _trChartFrame({
      axes: _trYAxis(ticks, yOf) + _trXAxis(n),
      data: lines,
    });
  }

  // Legend below the reputation chart: a colour swatch + latest value/tier per
  // faction (already ordered strongest-first by the export).
  function _reputationLegendHtml() {
    return _trendReputation.map(f => {
      const col = (typeof FACTION_COLOURS !== 'undefined' && FACTION_COLOURS[f.faction_id]) || '#6e7681';
      const val = f.latest == null ? '—' : (f.latest > 0 ? '+' : '') + f.latest.toFixed(1);
      return `<span style="display:inline-flex;align-items:center;gap:0.4rem;font-family:var(--font-mono);font-size:1rem;color:var(--text-dim)">
        <span style="width:0.9rem;height:0.2rem;border-radius:0.1rem;background:${col};flex-shrink:0"></span>
        ${f.faction_name || f.faction_id}<span style="color:var(--text-faint)">${val}${f.tier ? ' · ' + f.tier : ''}</span>
      </span>`;
    }).join('');
  }

  // ── changes feed ─────────────────────────────────────────────────────────────
  // Map each event type to an icon + colour + one-line description.
  function _changeDesc(c) {
    const b = s => `<b style="color:var(--text)">${s ?? '?'}</b>`;
    switch (c.type) {
      case 'station_built':
        return { icon: 'ti-building-factory-2', color: 'var(--green)',
                 text: `Station built — ${b(c.code)}${c.name ? ' · ' + c.name : ''} in ${c.sector_name || c.sector_macro || '—'}` };
      case 'station_lost':
        return { icon: 'ti-flame', color: 'var(--red)',
                 text: `Station lost — ${b(c.code)}${c.name ? ' · ' + c.name : ''}` };
      case 'ship_gained':
        return { icon: 'ti-rocket', color: 'var(--teal)',
                 text: `Ship acquired — ${b(c.code)} · ${c.type_name || c.name || '—'}` };
      case 'ship_lost':
        return { icon: 'ti-circle-x', color: 'var(--red)',
                 text: `Ship lost — ${b(c.code)} · ${c.type_name || c.name || '—'}` };
      case 'reputation_crossing': {
        const up = c.direction === 'up';
        return { icon: up ? 'ti-trending-up' : 'ti-trending-down',
                 color: up ? 'var(--green)' : 'var(--amber)',
                 text: `${c.faction_name || c.faction} — ${c.from_tier} → ${b(c.to_tier)}` };
      }
      case 'milestone':
        return { icon: 'ti-trophy', color: 'var(--amber)', text: c.label || 'Milestone' };
      default:
        return { icon: 'ti-point', color: 'var(--text-dim)', text: c.type };
    }
  }

  // Group the (already newest-first) feed by detecting scan, with a header per scan.
  function _changesFeedHtml(changes) {
    if (!changes.length) {
      return `<div class="panel" style="padding:2.4rem;text-align:center;color:var(--text-dim);font-family:var(--font-mono)">
        <i class="ti ti-history" style="font-size:2.4rem;color:var(--teal);opacity:0.5;display:block;margin-bottom:0.8rem"></i>
        No changes recorded yet. Scan the same save again after time passes in-game to start tracking your empire's history.
      </div>`;
    }
    let html = '', lastScan = null;
    changes.forEach(c => {
      if (c.scan_id !== lastScan) {
        lastScan = c.scan_id;
        const gh = c.game_time_s != null ? Math.round(c.game_time_s / 3600) + 'h' : '';
        html += `<div style="display:flex;align-items:center;gap:0.8rem;margin:1.2rem 0 0.5rem">
          <span style="font-family:var(--font-cond);font-weight:600;font-size:1.2rem;color:var(--teal)">Scan #${c.scan_id}</span>
          <span style="font-family:var(--font-mono);font-size:0.95rem;color:var(--text-faint)">${_trDate(c.scanned_at)}${gh ? ' · ' + gh : ''}</span>
          <div style="flex:1;height:1px;background:var(--border)"></div>
        </div>`;
      }
      const d = _changeDesc(c);
      html += `<div style="display:flex;align-items:center;gap:0.9rem;padding:0.55rem 0.9rem;border-bottom:1px solid var(--border)">
        <i class="ti ${d.icon}" style="font-size:1.4rem;color:${d.color};flex-shrink:0"></i>
        <span style="font-family:var(--font-mono);font-size:1.1rem;color:var(--text-dim)">${d.text}</span>
      </div>`;
    });
    return `<div class="panel" style="padding:0.4rem 0.6rem 0.8rem">${html}</div>`;
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
    _trendSeries     = trends.series || {};
    _trendScans      = _trendSeries.scans || [];
    _trendReputation = _trendSeries.reputation || [];
    const windows = trends.windows || { buckets: [] };
    const changes = data.changes  || [];

    // Nav badge: how many events the feed holds.
    const badge = document.getElementById('nav-trends-count');
    if (badge) badge.textContent = changes.length;

    // The selected metric drives the swappable panel below (defaults to the first
    // tab if the persisted choice is somehow gone).
    const metric = TREND_METRICS.find(m => m.key === _trendMetric) || TREND_METRICS[0];
    const n      = _trendScans.length;

    const toggle = TREND_METRICS.map(m =>
      `<button class="cf-toggle-btn ${m.key === _trendMetric ? 'active' : ''}" data-metric="${m.key}" onclick="setTrendMetric('${m.key}')">${m.label}</button>`
    ).join('');

    root.innerHTML = `
      <div style="display:flex;align-items:baseline;gap:1rem;padding-bottom:0.2rem">
        <div style="font-family:var(--font-cond);font-weight:600;font-size:1.8rem;color:var(--teal)">Empire Trajectory</div>
        <div style="font-family:var(--font-mono);font-size:1.1rem;color:var(--text-dim)">${n} scan${n === 1 ? '' : 's'} on record</div>
      </div>

      <div id="trend-metric-toggle" style="display:flex;flex-wrap:wrap;gap:0.4rem;margin:0.4rem 0 0.8rem">${toggle}</div>
      <div id="trend-panel">${_trendPanelHtml(metric)}</div>

      <div style="margin-top:1.6rem">
        <div class="sec-header"><div class="sec-title">Trade Totals · All-Time</div><div class="sec-line"></div></div>
        <div class="cards-row">${_tradeCardsHtml(windows)}</div>
      </div>

      <div style="margin-top:1.6rem">
        <div class="sec-header"><div class="sec-title">Recent Changes</div><div class="sec-line"></div></div>
        ${_changesFeedHtml(changes)}
      </div>`;
  }
