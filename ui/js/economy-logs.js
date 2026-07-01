  // Core role: Renders the Economy "Logs" sub-panel — Trade Log and Mining Log
  // display windows, each with their own selectable data view above the table,
  // mirroring the button-driven graph pattern used by the cashflow chart.

  // Per-station UI state: which log window is showing, and the trade log's
  // direction filter. Keyed by safeCode (same sanitised key economy-chart.js
  // and cashflow-chart.js use) so it survives re-renders across scans.
  const econLogModeByStation = {};      // 'trade' | 'mining', default 'trade'
  const econLogDirectionByStation = {}; // 'all' | 'buy' | 'sell', default 'all'

  // Cached per-station trade rows so mode/direction toggles can rebuild the
  // panel in place without re-walking the whole card template.
  const econLogsCacheByStation = {};

  // Time-window scrubber state, one per station — same shape as cashflow-chart.js's
  // cfZoom so it can share the generic drag handler (see registerScrubber() call
  // at the bottom of this file). Unlike the cash-flow chart, the logs track's full
  // width isn't a fixed 24H: X4's economy log has no time cap, only a count cap, so
  // the oldest entry on record can be minutes or days old depending on station
  // activity. econLogMaxHours holds that per-station span, recomputed on every
  // render so it tracks the data as new scans come in.
  const LOG_MIN_HOURS = 0.25; // 15 minutes — logs can be dense within an hour, finer than the cash-flow chart's 3H floor
  const econLogZoom = {};
  const econLogMaxHours = {};

  // Full timeline span (hours) covered by this station's trade + mining log
  // entries combined, so the scrubber governs both tabs with one shared window.
  // Returns null if the station has no log entries of either kind yet.
  function _econLogMaxAgoHours(stationCode, allTrades, allMining) {
    let maxS = -1;
    for (const t of allTrades) if (t.station_code === stationCode && t.time_ago_s > maxS) maxS = t.time_ago_s;
    for (const t of allMining) if (t.station_code === stationCode && t.time_ago_s > maxS) maxS = t.time_ago_s;
    return maxS < 0 ? null : maxS / 3600;
  }

  function _inLogWindow(timeAgoS, zoom) {
    const hAgo = timeAgoS / 3600;
    return hAgo >= zoom.offsetHours && hAgo <= zoom.offsetHours + zoom.hours;
  }

  function _logHoursLabel(h) {
    return h < 1 ? `-${Math.round(h * 60)}M` : `-${h % 1 !== 0 ? h.toFixed(1) : Math.round(h)}H`;
  }

  // Track markup identical to cashflow-chart.js's buildScrubberHtml (same
  // .cf-scrubber-track/-handle/-resize classes so it looks and drags the same),
  // just against econLogZoom/econLogMaxHours instead of cfZoom/CF_MAX_HOURS, and
  // tagged data-scrubber-kind="logs" so the shared drag handler in tooltips.js
  // routes it to the right zoom store.
  function _logScrubberHtml(safeCode) {
    const maxHours = econLogMaxHours[safeCode] || LOG_MIN_HOURS;
    const { hours, offsetHours } = econLogZoom[safeCode] || { hours: maxHours, offsetHours: 0 };
    const hLeft  = ((maxHours - offsetHours - hours) / maxHours * 100).toFixed(2);
    const hWidth = (hours / maxHours * 100).toFixed(2);
    return `<div class="cf-scrubber-track" data-scrubber="${safeCode}" data-scrubber-kind="logs">
      <div class="cf-scrubber-handle" style="left:${hLeft}%;width:${hWidth}%">
        <div class="cf-scrubber-resize" data-side="left"></div>
        <div class="cf-scrubber-resize" data-side="right"></div>
      </div>
      <span class="cf-scrubber-label" style="left:1.5rem">${_logHoursLabel(maxHours)}</span>
      <span class="cf-scrubber-label" style="left:50%;transform:translate(-50%,-50%)">◄ DRAG · EDGES RESIZE ►</span>
      <span class="cf-scrubber-label" style="right:1.5rem">NOW</span>
    </div>`;
  }

  // Same PROVEN/INFERRED resolution sets as _trade_log() in display.py, so the
  // counterparty colour-coding matches the CLI report exactly.
  const _TRADE_LOG_PROVEN   = new Set(['direct', 'courier']);
  const _TRADE_LOG_INFERRED = new Set(['homebase', 'visit', 'sector', 'delivery', 'docked']);

  function _tradeLogAgo(s) {
    s = Math.floor(s);
    if (s < 60) return s + 's';
    if (s < 3600) return Math.floor(s / 60) + 'm';
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
    return h + 'h ' + String(m).padStart(2, '0') + 'm';
  }

  function _counterpartyHtml(t) {
    const name = t.counterparty || '—';
    if (t.resolution === 'despawned') return `<span style="color:var(--text-label)">despawned</span>`;
    if (_TRADE_LOG_PROVEN.has(t.resolution))   return `<span style="color:var(--color-positive)">${name}</span>`;
    if (_TRADE_LOG_INFERRED.has(t.resolution)) return `<span style="color:var(--color-warning)">${name}</span>`;
    return `<span style="color:var(--text-label)">${name}</span>`;
  }

  // Entry point — called by populate.js when it builds a station card, and
  // again internally on every mode/direction toggle. Rebuilds and caches.
  //
  // Wrapped in .econ-row/.econ-graph — the same dark backdrop, padding, and
  // width caps (32-63.5rem) the Breakdown cash-flow chart uses — so the Logs
  // window reads as the same shape and size as the graph it replaces, just
  // with a table instead of an SVG chart inside.
  function economyLogsHtml(safeCode, stationCode, allTrades, allMining) {
    allTrades = allTrades || [];
    allMining = allMining || [];
    econLogsCacheByStation[safeCode] = { stationCode, allTrades, allMining };

    // Recompute the station's full log span and clamp any existing zoom to it —
    // a rescan can grow or shrink the span (new trades logged, or the game's own
    // log retention dropping old entries), so the window must stay in range
    // without resetting the user's pan/zoom on every scan.
    const maxAgo = _econLogMaxAgoHours(stationCode, allTrades, allMining);
    const hasLogs = maxAgo !== null;
    if (hasLogs) {
      const maxHours = Math.max(maxAgo, LOG_MIN_HOURS);
      econLogMaxHours[safeCode] = maxHours;
      const z = econLogZoom[safeCode];
      if (!z) {
        econLogZoom[safeCode] = { hours: maxHours, offsetHours: 0 };
      } else {
        z.hours = Math.min(z.hours, maxHours);
        z.offsetHours = Math.max(0, Math.min(maxHours - z.hours, z.offsetHours));
      }
    }

    const mode = econLogModeByStation[safeCode] || 'trade';
    return `
      <div class="econ-row econ-row-logs">
        <div class="econ-graph">
          <div class="trend-toggle" style="margin-bottom:0.6rem">
            <button class="trend-toggle-btn ${mode === 'trade'  ? 'active' : ''}" onclick="setEconLogMode('${safeCode}','trade')"><i class="ti ti-arrows-exchange"></i> Trade Log</button>
            <button class="trend-toggle-btn ${mode === 'mining' ? 'active' : ''}" onclick="setEconLogMode('${safeCode}','mining')"><i class="ti ti-triangle"></i> Mining Log</button>
          </div>
          ${mode === 'trade'
            ? _tradeLogHtml(safeCode, stationCode, allTrades)
            : _miningLogHtml(safeCode, stationCode, allMining)}
          ${hasLogs ? _logScrubberHtml(safeCode) : ''}
        </div>
      </div>`;
  }

  function setEconLogMode(safeCode, mode) {
    econLogModeByStation[safeCode] = mode;
    _rebuildEconomyLogs(safeCode);
  }

  function setEconLogDirection(safeCode, dir) {
    econLogDirectionByStation[safeCode] = dir;
    _rebuildEconomyLogs(safeCode);
  }

  function _rebuildEconomyLogs(safeCode) {
    const cache = econLogsCacheByStation[safeCode];
    const el = document.getElementById('econlogs-' + safeCode);
    if (!cache || !el) return;
    el.innerHTML = economyLogsHtml(safeCode, cache.stationCode, cache.allTrades, cache.allMining);
  }

  // Full per-station commercial trade log — same rows as the CLI's
  // COMPLETED TRADE LOG (display.py _trade_log), minus the raw ship ID
  // (the UI links the ship name straight to the Naval tab instead).
  const _TRADE_LOG_CAP = 150;

  // Buy/Sell/All direction filter for the trade log — same vertical
  // sliding-pill look as the Ships graph's Total/Kills/Losses switch on the
  // Trends tab (trends.js SHIPS_MODES + combatToggle: one dark bordered
  // track, colour-coded thumb slides behind the active label), just sized
  // up to match .trend-toggle-btn's font/padding instead of the tiny
  // SVG-viewBox-scale pixels that pill uses inside a chart. Pinned to the
  // left of the log box via position:absolute so it doesn't take up layout
  // width or resize the table.
  const _DIR_MODES = {
    all:  { label: 'All',  color: CHART_LINE },
    buy:  { label: 'Buy',  color: CHART_LOSS },
    sell: { label: 'Sell', color: CHART_ACCENT },
  };

  function _dirPillHtml(safeCode, dir) {
    const keys = Object.keys(_DIR_MODES);
    const rowH = 2, pillH = rowH * keys.length; // rem
    const activeTop = keys.indexOf(dir) * rowH;
    const activeColor = _DIR_MODES[dir].color;
    return `
      <div style="position:absolute;top:0;right:calc(100% + 0.6rem);width:4.5rem;height:${pillH}rem;
          display:grid;grid-template-rows:repeat(${keys.length}, 1fr);
          background:rgba(4,12,20,0.88);border:1px solid rgba(0,0,0,0.70);border-radius:var(--radius-sm);
          overflow:hidden;user-select:none;
          box-shadow:inset 0 2px 7px rgba(0,0,0,0.70),inset 0 1px 3px rgba(0,0,0,0.50),0 1px 0 rgba(255,255,255,0.07)">
        <div style="position:absolute;left:1px;right:1px;height:${rowH}rem;top:${activeTop}rem;
            background:linear-gradient(170deg, ${activeColor}, ${activeColor}cc);border-radius:1px;pointer-events:none;
            box-shadow:0 3px 9px rgba(0,0,0,0.70),inset 0 1px 0 rgba(255,255,255,0.40),inset 0 -1px 0 rgba(0,0,0,0.24)"></div>
        ${keys.map(k => `
        <span onclick="setEconLogDirection('${safeCode}','${k}')" style="position:relative;z-index:1;cursor:pointer;
            display:flex;align-items:center;justify-content:center;
            font-family:var(--font-data);font-size:1rem;letter-spacing:0.08em;text-transform:uppercase;
            color:${dir === k ? '#051210' : 'var(--text-brand)'};font-weight:${dir === k ? '700' : '400'}">${_DIR_MODES[k].label}</span>`).join('')}
      </div>`;
  }

  function _tradeLogHtml(safeCode, stationCode, allTrades) {
    const dir = econLogDirectionByStation[safeCode] || 'all';
    const dirFilter = dir === 'buy' ? 'In' : dir === 'sell' ? 'Out' : null;
    // Infinity hours = no window set yet (station has no logs at all), which
    // makes the window check a no-op rather than needing a separate branch.
    const zoom = econLogZoom[safeCode] || { hours: Infinity, offsetHours: 0 };

    let rows = allTrades.filter(t =>
      t.station_code === stationCode && (!dirFilter || t.direction === dirFilter) &&
      _inLogWindow(t.time_ago_s, zoom));
    rows.sort((a, b) => a.time_ago_s - b.time_ago_s); // most recent first
    const total = rows.length;
    const truncated = total > _TRADE_LOG_CAP;
    if (truncated) rows = rows.slice(0, _TRADE_LOG_CAP);

    const pill = _dirPillHtml(safeCode, dir);

    if (!total) {
      return `<div style="position:relative">${pill}
        <div class="econlog-box" style="display:flex;align-items:center;justify-content:center;text-align:center;font-family:var(--font-data);font-size:1.1rem;color:var(--text-brand)">No trades logged</div>
      </div>`;
    }

    const trRows = rows.map(t => {
      const ship = t.ship_name || t.ship_code || '—';
      const shipHtml = t.ship_code
        ? `<span class="ship-link" onclick="jumpToShip('${t.ship_code}','${t.ship_owner_id || 'player'}')">${ship}</span>`
        : ship;
      const wareColour = WARE_COLOURS[t.ware_name] || CHART_LINE;
      // Dir/Units/Cr-u/Total Cr move into a hover tooltip on the row — see
      // tradeLogTipHtml below — so the visible table stays to what fits at a
      // glance: Time, Ship, Ware, Counterparty.
      const tip = encodeURIComponent(JSON.stringify({
        dir: t.direction === 'Out' ? 'sell' : 'buy',
        units: t.amount, priceEa: t.price_cr, total: t.total_cr,
      }));
      return `<tr data-trade-log-tip="${tip}">
        <td class="mono">${_tradeLogAgo(t.time_ago_s)}</td>
        <td>${shipHtml}</td>
        <td style="color:${wareColour}">${t.ware_name}</td>
        <td>${_counterpartyHtml(t)}</td>
      </tr>`;
    }).join('');

    return `<div style="position:relative">${pill}
      <div class="econlog-box">
        <table class="data-table">
          <thead><tr>
            <th>Time</th><th>Ship</th><th>Ware</th><th>Counterparty</th>
          </tr></thead>
          <tbody>${trRows}</tbody>
        </table>
        ${truncated ? `<div style="padding-top:0.6rem;font-family:var(--font-data);font-size:0.95rem;color:var(--text-label)">Showing ${_TRADE_LOG_CAP} most recent of ${total.toLocaleString()}</div>` : ''}
      </div>
    </div>`;
  }

  // Trade log row hover — Dir/Units/Cr-u/Total Cr, using the same sold ▲ /
  // bought ▼ arrow-and-colour convention as the cashflow chart's hourly
  // tooltip (cashflowTipHtml in cashflow-chart.js).
  function tradeLogTipHtml(d) {
    const isSell = d.dir === 'sell';
    const dirCol = isSell ? CHART_ACCENT : CHART_LOSS;
    const fmtU = n => Math.round(n).toLocaleString();
    const row = (label, value) => `
        <div style="display:flex;justify-content:space-between;gap:1.2rem;padding:1px 0">
          <span style="color:var(--text-brand);font-size:1rem">${label}</span>
          <span style="color:var(--text-secondary);font-family:var(--font-data);font-size:1rem;text-align:right">${value}</span>
        </div>`;
    return `<div style="min-width:14rem;padding:0.2rem 0">
      <div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:0.4rem;padding-bottom:0.4rem;border-bottom:1px solid var(--outline)">
        <span style="color:${dirCol};font-size:1.1rem">${isSell ? '▲' : '▼'}</span>
        <span style="color:${dirCol};font-size:1rem;letter-spacing:0.06em;text-transform:uppercase">${isSell ? 'Sold' : 'Bought'}</span>
      </div>
      ${row('Units', fmtU(d.units))}
      ${row('Each', fmtU(d.priceEa) + ' Cr')}
      ${row('Total', fmtU(d.total) + ' Cr')}
    </div>`;
  }

  registerTip('tradeLogTip', (el, _e, tip) => {
    tip.innerHTML = tradeLogTipHtml(JSON.parse(decodeURIComponent(el.dataset.tradeLogTip)));
    tip.style.color = '';
    tip.style.whiteSpace = 'normal';
    return true;
  });

  // Raw-resource deliveries (ore, silicon, ice, gas, ...) from player mining
  // ships to this station — same rows as the CLI's "Mining deliveries" block
  // in display.py's _trades(), but per-delivery rather than aggregated, and
  // sorted most-recent-first like the trade log. One-directional (the
  // station only ever receives), so there's no All/Buy/Sell filter here.
  function _miningLogHtml(safeCode, stationCode, allMining) {
    const zoom = econLogZoom[safeCode] || { hours: Infinity, offsetHours: 0 };
    let rows = allMining.filter(t => t.station_code === stationCode && _inLogWindow(t.time_ago_s, zoom));
    rows.sort((a, b) => a.time_ago_s - b.time_ago_s); // most recent first
    const total = rows.length;
    const truncated = total > _TRADE_LOG_CAP;
    if (truncated) rows = rows.slice(0, _TRADE_LOG_CAP);

    if (!total) {
      return `<div class="econlog-box" style="display:flex;align-items:center;justify-content:center;text-align:center;font-family:var(--font-data);font-size:1.1rem;color:var(--text-brand)">No mining deliveries logged</div>`;
    }

    const trRows = rows.map(t => {
      const ship = t.ship_name || t.ship_code || '—';
      // Mining ships delivering to a player station are always player-owned.
      const shipHtml = t.ship_code
        ? `<span class="ship-link" onclick="jumpToShip('${t.ship_code}','player')">${ship}</span>`
        : ship;
      return `<tr>
        <td class="mono">${_tradeLogAgo(t.time_ago_s)}</td>
        <td>${shipHtml}</td>
        <td>${t.ware_name}</td>
        <td class="mono" style="text-align:right">${t.amount.toLocaleString()}</td>
        <td class="mono" style="text-align:right">${t.price_cr.toLocaleString(undefined, {maximumFractionDigits: 2})}</td>
        <td class="mono" style="text-align:right">${Math.round(t.total_cr).toLocaleString()}</td>
      </tr>`;
    }).join('');

    return `
      <div class="econlog-box">
        <table class="data-table">
          <thead><tr>
            <th>Time</th><th>Ship</th><th>Ware</th>
            <th style="text-align:right">Units</th><th style="text-align:right">Cr/u</th>
            <th style="text-align:right">Total Cr</th>
          </tr></thead>
          <tbody>${trRows}</tbody>
        </table>
        ${truncated ? `<div style="padding-top:0.6rem;font-family:var(--font-data);font-size:0.95rem;color:var(--text-label)">Showing ${_TRADE_LOG_CAP} most recent of ${total.toLocaleString()}</div>` : ''}
      </div>`;
  }

  // Registers the logs panel's zoom store with the generic scrubber drag
  // handler in tooltips.js (see SCRUBBER_KINDS in tip-registry.js) — one
  // window shared by both the Trade Log and Mining Log tabs. maxHours is
  // per-station (unlike the cash-flow chart's fixed 24H), so it's passed as a
  // lookup function rather than a constant.
  registerScrubber('logs', {
    zoom: econLogZoom,
    minHours: LOG_MIN_HOURS,
    maxHours: safeCode => econLogMaxHours[safeCode] || LOG_MIN_HOURS,
    onChange: _rebuildEconomyLogs,
  });
