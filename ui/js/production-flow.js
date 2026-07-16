  // Core role: Ware-flow SVG for the station card's More → Production panel.

  // Drawn from the per-station analytics in the export. Two input-column modes:
  // scans that carry input_rates (station_input_rates table, added Jul 2026)
  // get a rail of input nodes with ribbons sized by consumption rate; older
  // exports fall back to limiting-ware status chips, since the produced-ware
  // analytics are the only input-side facts they contain.
  //
  // Colour rules (matching the existing Production tab in populate.js):
  //   - Every ware — module box, input node, and its ribbons — is coloured by
  //     WARE_COLOURS[name], the same identity colour used by the cash-flow
  //     By-Ware chart and the station card's own Production tab. Ribbon width
  //     still encodes rate; colour encodes *which ware*, not its health.
  //   - Health/urgency (starved, overflowing) is conveyed only by the badge
  //     and the input node's runtime sub-label, via the CHART_WARN/CHART_LOSS
  //     status hex — the same isolation the existing rtSpan in populate.js
  //     uses (bars stay ware-coloured; only the small runtime text goes red).
  //   - CSS custom properties don't resolve inside inline-SVG attributes (see
  //     the constants.js chart-palette note), so every colour here comes from
  //     a JS hex constant (WARE_COLOURS / CHART_* / SVG_*), never var(...).
  //
  // Tooltips: never native SVG <title> — UI_STANDARDS.md §8 requires the
  // shared #hull-tip popover via data-*-tip + registerTip, same as every
  // other hover in this app (see the two registerTip calls at the bottom).

  // All geometry is in viewBox units on a fixed 900-wide canvas; the SVG
  // scales to the card width, so row counts are the only variable dimension.
  const PFLOW_W = 900, PFLOW_HEADER = 34, PFLOW_LANE = 84, PFLOW_INROW = 50;

  function _pflowRate(r) {
    return Math.round(r).toLocaleString();
  }

  function _pflowMins(mins) {
    if (mins < 60) return Math.round(mins) + 'm';
    const h = Math.floor(mins / 60), m = Math.round(mins % 60);
    return m > 0 ? `${h}h ${m}m` : `${h}h`;
  }

  function _pflowCapHrs(hrs) {
    return (hrs < 10 ? Math.round(hrs * 10) / 10 : Math.round(hrs)) + ' h';
  }

  // Shared label/value row — cfRow (cashflow-chart.js) is already the house
  // pattern for this exact layout in every other structured tooltip.
  function _pflowTipHtml(wareName, wareColour, rows) {
    return `<div style="min-width:16rem;padding:0.2rem 0">
      <div style="font-size:1.1rem;letter-spacing:0.06em;text-transform:uppercase;
                  color:${wareColour};margin-bottom:0.4rem;padding-bottom:0.3rem;
                  border-bottom:1px solid var(--outline)">${wareName}</div>
      ${rows.map(([label, value, colour]) => cfRow(label, value, colour)).join('')}
    </div>`;
  }

  // Returns the full panel HTML for one station: header labels, an input rail
  // (or fallback chips), one lane per produced ware (module node →
  // export/internal ribbons → status badge), and a shared "internal use" sink
  // when anything recycles.
  function productionFlowSvg(s) {
    const prodRates = s.production_rates || {};
    const consRates = s.consumption_rates || {};
    const runtimes  = s.production_runtimes || {};

    // Largest flow first so ribbon widths read as a visual ranking.
    const wares = Object.keys(prodRates)
      .filter(w => prodRates[w] > 0)
      .sort((a, b) => prodRates[b] - prodRates[a]);

    if (wares.length === 0) {
      return `<div style="padding:1.2rem 1.4rem;font-family:var(--font-data);font-size:1.1rem;color:var(--text-brand)">No production modules on this station.</div>`;
    }

    const inputs = Object.entries(s.input_rates || {})
      .filter(([, v]) => v.rate > 0)
      .sort((a, b) => b[1].rate - a[1].rate);
    const railMode = inputs.length > 0;

    // Whichever column is taller sets the body height; the shorter column is
    // vertically centred against it so the fan of ribbons stays symmetric.
    const lanesH  = wares.length * PFLOW_LANE;
    const railH   = inputs.length * PFLOW_INROW;
    const bodyH   = Math.max(lanesH, railH);
    const laneTop = PFLOW_HEADER + (bodyH - lanesH) / 2;
    const railTop = PFLOW_HEADER + (bodyH - railH) / 2;

    // Internal-use sink only exists when at least one produced ware is
    // consumed on-station; otherwise the bottom band would be dead space.
    const hasInternal = wares.some(w => (consRates[w] || 0) > 0.5);
    const H = PFLOW_HEADER + bodyH + (hasInternal ? 84 : 10);
    const sinkY = H - 60;

    // One shared width scale across inputs and outputs so a 1,000/h input
    // ribbon visually equals a 1,000/h output ribbon. sqrt keeps high-volume
    // wares (energy cells) from flattening everything else to hairlines.
    const maxRate = Math.max(
      ...wares.map(w => prodRates[w]),
      ...inputs.map(([, v]) => v.rate));
    const ribbonW = r => Math.max(2, Math.round(22 * Math.sqrt(r / maxRate)));

    const laneY = i => laneTop + i * PFLOW_LANE + PFLOW_LANE / 2;

    // Input ribbons converge on the module column's vertical midpoint — the
    // export can't attribute an input to a specific product (rates are summed
    // across all modules), so a per-lane fan would imply precision that isn't
    // in the data.
    const modMidY = (laneY(0) + laneY(wares.length - 1)) / 2;

    const rail = inputs.map(([name, v], i) => {
      const iy      = railTop + i * PFLOW_INROW + PFLOW_INROW / 2;
      const wareCol = WARE_COLOURS[name] || CHART_LINE;

      // A produced-on-station input (energy cells at a self-powered factory)
      // is replenished continuously, so its stock-based runtime would be
      // misleading — mark it as self-supplied instead.
      const selfSupplied = (prodRates[name] || 0) > 0;
      const rtMins = v.runtime_hours === null ? null : v.runtime_hours * 60;
      let tone = 'primary';
      if (!selfSupplied && rtMins !== null && rtMins < 60) tone = 'negative';
      else if (!selfSupplied && rtMins !== null && rtMins < 120) tone = 'warning';
      const statusCol = tone === 'negative' ? CHART_LOSS : tone === 'warning' ? CHART_WARN : SVG_TEXT_DIM;

      const rtLabel = selfSupplied ? '↺ internal'
        : rtMins === null ? ''
        : rtMins <= 0 ? 'OUT'
        : _pflowMins(rtMins);
      const sub = `${_pflowRate(v.rate)}/h${rtLabel ? ' · ' + rtLabel : ''}`;

      const tipRows = [
        ['Consumption', `${_pflowRate(v.rate)}/h`],
        ['Stock', `${Math.round(v.stock ?? 0).toLocaleString()} units`],
      ];
      if (selfSupplied) tipRows.push(['Runtime', 'Produced on-station', SVG_TEXT_DIM]);
      else if (rtMins !== null) tipRows.push(['Runtime', rtMins <= 0 ? 'Out of stock' : _pflowMins(rtMins), statusCol]);
      const tipAttr = `data-pflow-input-tip="${encodeURIComponent(JSON.stringify({ ware: name, colour: wareCol, rows: tipRows }))}"`;

      return `
        <path d="M158,${iy} C185,${iy} 185,${modMidY} 210,${modMidY}" fill="none" stroke="${wareCol}" stroke-width="${ribbonW(v.rate)}" stroke-opacity="0.45"/>
        <g ${tipAttr} style="cursor:default">
          <rect x="8" y="${iy - 19}" width="150" height="38" rx="3" fill="${SVG_SURFACE}" stroke="${SVG_OUTLINE}"/>
          <text x="83" y="${iy - 1}" text-anchor="middle" font-size="13" style="font-family:var(--font-data);fill:${wareCol}">${name}</text>
          <text x="83" y="${iy + 14}" text-anchor="middle" font-size="11" style="font-family:var(--font-data);fill:${statusCol}">${sub}</text>
        </g>`;
    }).join('');

    const lanes = wares.map((w, i) => {
      const ly      = laneY(i);
      const wareCol = WARE_COLOURS[w] || CHART_LINE;
      const prod    = prodRates[w];
      const consInt = consRates[w] || 0;
      const exp     = Math.max(0, prod - consInt);
      const rt      = runtimes[w] || {};
      const mins    = (rt.minutes === undefined) ? null : rt.minutes;
      const cap     = (rt.time_to_cap_hours === undefined) ? null : rt.time_to_cap_hours;

      // Lane tone mirrors the Overview production rows' runtime thresholds
      // (<60m negative, <120m warning) so the two views never disagree; a
      // storage cap inside 24h is the overflow warning from the analytics.
      let tone = 'primary';
      if (mins !== null && mins < 60) tone = 'negative';
      else if ((mins !== null && mins < 120) || (cap !== null && cap < 24)) tone = 'warning';
      const statusCol = tone === 'negative' ? CHART_LOSS : tone === 'warning' ? CHART_WARN : CHART_ACCENT;

      // Shared tooltip payload for both the module box and the badge — same
      // ware, same facts, just two hit areas.
      const laneTipRows = [
        ['Production', `${_pflowRate(prod)}/h`],
        ...(consInt > 0.5 ? [['Internal use', `${_pflowRate(consInt)}/h`]] : []),
        ['Surplus', `${_pflowRate(exp)}/h`, exp > 0.5 ? CHART_ACCENT : SVG_TEXT_DIM],
        mins === null
          ? ['Runtime', 'No inputs needed', SVG_TEXT_DIM]
          : ['Runtime', mins <= 0 ? 'Stopped' : _pflowMins(mins), statusCol],
        ...(rt.limiting_ware ? [['Limiting input', rt.limiting_ware]] : []),
        ...(cap !== null ? [['Storage caps in', _pflowCapHrs(cap), tone === 'warning' ? CHART_WARN : SVG_TEXT_DIM]] : []),
      ];
      const laneTipAttr = `data-pflow-lane-tip="${encodeURIComponent(JSON.stringify({ ware: w, colour: wareCol, rows: laneTipRows }))}"`;

      // Fallback chip (no input_rates in this export): the limiting input is
      // the only input-side fact available, so it carries the left column.
      let chip = '';
      if (!railMode) {
        let chipTxt, chipCol;
        if (mins === null) {
          chipTxt = 'No inputs needed';
          chipCol = SVG_TEXT_DIM;
        } else {
          chipTxt = `${rt.limiting_ware || 'Inputs'} · ${_pflowMins(mins)}`;
          chipCol = tone === 'primary' ? SVG_TEXT_DIM : statusCol;
        }
        chip = `
        <line x1="188" y1="${ly}" x2="210" y2="${ly}" stroke="${SVG_OUTLINE}"/>
        <g ${laneTipAttr} style="cursor:default">
          <rect x="8" y="${ly - 15}" width="180" height="30" rx="3" fill="${SVG_SURFACE}" stroke="${SVG_OUTLINE}"/>
          <text x="98" y="${ly + 4}" text-anchor="middle" font-size="12" style="font-family:var(--font-data);fill:${chipCol}">${chipTxt}</text>
        </g>`;
      }

      // Badge: worst pending event wins (stopped > starving > capping >
      // no-surplus > balanced) so the right column scans like an alert list.
      // Semantic trio: neutral surface when balanced, tone-tinted dim
      // fill + line border when something needs attention (UI_STANDARDS §2).
      let bTitle, bSub;
      if (mins !== null && mins <= 0) {
        bTitle = 'stopped'; bSub = `out of ${rt.limiting_ware || 'inputs'}`;
      } else if (tone === 'negative' || (mins !== null && mins < 120)) {
        bTitle = `stops in ${_pflowMins(mins)}`;
        bSub   = exp > 0.5 ? `+${_pflowRate(exp)}/h now` : 'no surplus';
      } else if (cap !== null && cap < 24) {
        bTitle = `caps in ${_pflowCapHrs(cap)}`; bSub = `+${_pflowRate(exp)}/h`;
      } else if (exp <= 0.5) {
        bTitle = 'no surplus'; bSub = 'all used internally';
      } else {
        bTitle = `+${_pflowRate(exp)}/h`; bSub = 'balanced';
      }
      const badgeFill   = tone === 'primary' ? SVG_SURFACE  : `${statusCol}22`;
      const badgeStroke = tone === 'primary' ? SVG_OUTLINE  : `${statusCol}55`;
      const badgeTitleCol = tone === 'primary' ? SVG_TEXT : statusCol;
      const badgeSubCol   = tone === 'primary' ? SVG_TEXT_DIM : `${statusCol}cc`;

      const wExp = ribbonW(exp), wInt = ribbonW(consInt);
      const expRibbon = exp > 0.5 ? `
        <path d="M380,${ly - 10} H700" fill="none" stroke="${wareCol}" stroke-width="${wExp}" stroke-opacity="0.75"/>
        <text x="540" y="${ly - 10 - wExp / 2 - 5}" text-anchor="middle" font-size="12" style="font-family:var(--font-data);fill:${SVG_TEXT_DIM}">${_pflowRate(exp)}/h export</text>` : '';
      const intRibbon = consInt > 0.5 ? `
        <path d="M380,${ly + 14} C560,${ly + 16} 570,${sinkY - 50} 570,${sinkY}" fill="none" stroke="${wareCol}" stroke-width="${wInt}" stroke-opacity="0.4"/>
        <text x="452" y="${ly + 14 + wInt / 2 + 14}" font-size="12" style="font-family:var(--font-data);fill:${SVG_TEXT_DIM}">${_pflowRate(consInt)}/h internal</text>` : '';

      return `${chip}${expRibbon}${intRibbon}
        <g ${laneTipAttr} style="cursor:default">
          <rect x="210" y="${ly - 24}" width="170" height="48" rx="3" fill="${SVG_SURFACE}" stroke="${SVG_OUTLINE}"/>
          <text x="295" y="${ly - 3}" text-anchor="middle" font-size="14" style="font-family:var(--font-data);fill:${wareCol}">${w}</text>
          <text x="295" y="${ly + 15}" text-anchor="middle" font-size="12" style="font-family:var(--font-data);fill:${SVG_TEXT_DIM}">${_pflowRate(prod)}/h</text>
        </g>
        <g ${laneTipAttr} style="cursor:default">
          <rect x="700" y="${ly - 24}" width="192" height="48" rx="3" fill="${badgeFill}" stroke="${badgeStroke}"/>
          <text x="796" y="${ly - 3}" text-anchor="middle" font-size="14" style="font-family:var(--font-data);fill:${badgeTitleCol}">${bTitle}</text>
          <text x="796" y="${ly + 15}" text-anchor="middle" font-size="12" style="font-family:var(--font-data);fill:${badgeSubCol}">${bSub}</text>
        </g>`;
    }).join('');

    const sink = hasInternal ? `
      <g data-text-tip="Wares consumed by this station's own modules never reach storage or trade." style="cursor:default">
        <rect x="490" y="${sinkY}" width="160" height="38" rx="3" fill="${SVG_SURFACE}" stroke="${SVG_OUTLINE}"/>
        <text x="570" y="${sinkY + 17}" text-anchor="middle" font-size="12" style="font-family:var(--font-data);letter-spacing:0.12em;fill:${SVG_BRAND}">INTERNAL USE</text>
        <text x="570" y="${sinkY + 31}" text-anchor="middle" font-size="11" style="font-family:var(--font-data);fill:${SVG_TEXT_DIM}">feeds this station's inputs</text>
      </g>` : '';

    const hdr = (x, label) =>
      `<text x="${x}" y="20" text-anchor="middle" font-size="11" style="font-family:var(--font-data);letter-spacing:0.18em;fill:${SVG_BRAND}">${label}</text>`;

    return `<div style="padding:0.8rem 1rem">
      <svg viewBox="0 0 ${PFLOW_W} ${H}" style="width:100%;height:auto;display:block" xmlns="http://www.w3.org/2000/svg">
        ${hdr(railMode ? 83 : 98, 'INPUTS')}${hdr(295, 'MODULES')}${hdr(796, 'OUTPUT / HR')}
        ${rail}${lanes}${sink}
      </svg>
    </div>`;
  }

  // ── Tooltip registration ──────────────────────────────────────────
  // Both stamp a JSON payload (ware, colour, pre-built label/value rows) at
  // render time; the handler just runs it through the shared row renderer.
  // Never native SVG <title> — see UI_STANDARDS.md §8.
  registerTip('pflowLaneTip', (el, _e, tip) => {
    const d = JSON.parse(decodeURIComponent(el.dataset.pflowLaneTip));
    tip.innerHTML = _pflowTipHtml(d.ware, d.colour, d.rows);
    tip.style.color      = '';
    tip.style.whiteSpace = 'normal';
    return true;
  });

  registerTip('pflowInputTip', (el, _e, tip) => {
    const d = JSON.parse(decodeURIComponent(el.dataset.pflowInputTip));
    tip.innerHTML = _pflowTipHtml(d.ware, d.colour, d.rows);
    tip.style.color      = '';
    tip.style.whiteSpace = 'normal';
    return true;
  });
