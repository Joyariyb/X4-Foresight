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
    econLogsCacheByStation[safeCode] = {
      stationCode,
      allTrades: allTrades || [],
      allMining: allMining || [],
    };
    const mode = econLogModeByStation[safeCode] || 'trade';
    return `
      <div class="econ-row">
        <div class="econ-graph">
          <div class="trend-toggle" style="margin-bottom:0.6rem">
            <button class="trend-toggle-btn ${mode === 'trade'  ? 'active' : ''}" onclick="setEconLogMode('${safeCode}','trade')"><i class="ti ti-arrows-exchange"></i> Trade Log</button>
            <button class="trend-toggle-btn ${mode === 'mining' ? 'active' : ''}" onclick="setEconLogMode('${safeCode}','mining')"><i class="ti ti-triangle"></i> Mining Log</button>
          </div>
          ${mode === 'trade'
            ? _tradeLogHtml(safeCode, stationCode, allTrades)
            : _miningLogHtml(safeCode, stationCode, allMining || [])}
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

  function _tradeLogHtml(safeCode, stationCode, allTrades) {
    const dir = econLogDirectionByStation[safeCode] || 'all';
    const dirFilter = dir === 'buy' ? 'In' : dir === 'sell' ? 'Out' : null;

    let rows = allTrades.filter(t =>
      t.station_code === stationCode && (!dirFilter || t.direction === dirFilter));
    rows.sort((a, b) => a.time_ago_s - b.time_ago_s); // most recent first
    const total = rows.length;
    const truncated = total > _TRADE_LOG_CAP;
    if (truncated) rows = rows.slice(0, _TRADE_LOG_CAP);

    const dirBar = `
      <div class="trend-toggle" style="margin-bottom:0.6rem">
        <button class="trend-toggle-btn ${dir === 'all'  ? 'active' : ''}" onclick="setEconLogDirection('${safeCode}','all')">All</button>
        <button class="trend-toggle-btn ${dir === 'buy'  ? 'active' : ''}" onclick="setEconLogDirection('${safeCode}','buy')">Buy</button>
        <button class="trend-toggle-btn ${dir === 'sell' ? 'active' : ''}" onclick="setEconLogDirection('${safeCode}','sell')">Sell</button>
      </div>`;

    if (!total) {
      return `${dirBar}<div class="econlog-box" style="display:flex;align-items:center;justify-content:center;text-align:center;font-family:var(--font-data);font-size:1.1rem;color:var(--text-brand)">No trades logged</div>`;
    }

    const trRows = rows.map(t => {
      const ship = t.ship_name || t.ship_code || '—';
      const shipHtml = t.ship_code
        ? `<span class="ship-link" onclick="jumpToShip('${t.ship_code}','${t.ship_owner_id || 'player'}')">${ship}</span>`
        : ship;
      const dirColor = t.direction === 'Out' ? 'var(--color-positive)' : 'var(--text-secondary)';
      return `<tr>
        <td class="mono">${_tradeLogAgo(t.time_ago_s)}</td>
        <td>${shipHtml}</td>
        <td class="mono" style="color:${dirColor}">${t.direction}</td>
        <td>${t.ware_name}</td>
        <td class="mono" style="text-align:right">${t.amount.toLocaleString()}</td>
        <td class="mono" style="text-align:right">${t.price_cr.toLocaleString(undefined, {maximumFractionDigits: 2})}</td>
        <td class="mono" style="text-align:right">${Math.round(t.total_cr).toLocaleString()}</td>
        <td>${_counterpartyHtml(t)}</td>
      </tr>`;
    }).join('');

    return `${dirBar}
      <div class="econlog-box">
        <table class="data-table">
          <thead><tr>
            <th>Time</th><th>Ship</th><th>Dir</th><th>Ware</th>
            <th style="text-align:right">Units</th><th style="text-align:right">Cr/u</th>
            <th style="text-align:right">Total Cr</th><th>Counterparty</th>
          </tr></thead>
          <tbody>${trRows}</tbody>
        </table>
        ${truncated ? `<div style="padding-top:0.6rem;font-family:var(--font-data);font-size:0.95rem;color:var(--text-label)">Showing ${_TRADE_LOG_CAP} most recent of ${total.toLocaleString()}</div>` : ''}
      </div>`;
  }

  // Raw-resource deliveries (ore, silicon, ice, gas, ...) from player mining
  // ships to this station — same rows as the CLI's "Mining deliveries" block
  // in display.py's _trades(), but per-delivery rather than aggregated, and
  // sorted most-recent-first like the trade log. One-directional (the
  // station only ever receives), so there's no All/Buy/Sell filter here.
  function _miningLogHtml(safeCode, stationCode, allMining) {
    let rows = allMining.filter(t => t.station_code === stationCode);
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
