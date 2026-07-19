  // Core role: Ware-flow SVG for the station card's More → Production panel.

  // Drawn from the per-station analytics in the export. Three input-column
  // modes, newest data first:
  //   1. input_breakdown (station_input_breakdown table, added Jul 2026) —
  //      compact input chips docked beside EACH module lane, showing exactly
  //      what that module's recipe consumes. Exact per-lane attribution.
  //   2. input_rates only (older scans) — the aggregate input rail, ribbons
  //      converging on the module column since these exports can't attribute
  //      an input to a specific product.
  //   3. neither (oldest scans) — limiting-ware status chips.
  //
  // Internal consumption is shown as a per-lane "↻ N/h internal" pill, not a
  // ribbon: the earlier ribbons-to-shared-sink design made every internal
  // flow curve past other module rows on its way down, which read as "this
  // ware feeds that module" — a wrong and misleading implication. The pill
  // keeps the fact on the row it belongs to, paired with the ↺ marker on
  // self-supplied input chips so producer and consumer sides cross-reference.
  //
  // Colour rules (matching the existing Production tab in populate.js):
  //   - Every ware — module box, input chip, and its ribbons — is coloured by
  //     WARE_COLOURS[name], the same identity colour used by the cash-flow
  //     By-Ware chart and the station card's own Production tab. Ribbon width
  //     still encodes rate; colour encodes *which ware*, not its health.
  //   - Health/urgency (starved, overflowing) is conveyed only by the badge
  //     and the input chip's runtime sub-label, via the CHART_WARN/CHART_LOSS
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
  // Chip-mode lanes grow past PFLOW_LANE when a recipe has 4+ inputs
  // (Claytronics, Drone Components), so lane tops are cumulative, not fixed.
  const PFLOW_W = 900, PFLOW_HEADER = 34, PFLOW_LANE = 84, PFLOW_INROW = 50;
  const PFLOW_CHIP = 24;   // input-chip pitch: 20px chip + 4px gap

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

  // Returns the full panel HTML for one station: header labels, an input
  // column (chips / rail / fallback chips per the mode chain above), one lane
  // per produced ware (module node → export ribbon → status badge), and a
  // per-lane internal-use pill where output is consumed on-station.
  function productionFlowSvg(s) {
    const prodRates  = s.production_rates || {};
    const consRates  = s.consumption_rates || {};
    const runtimes   = s.production_runtimes || {};
    const inputRates = s.input_rates || {};       // {name: {rate, stock, runtime_hours}}
    const breakdown  = s.input_breakdown || {};   // {producedName: {inputName: rate}}
    const sources    = s.input_sources || {};     // {name: {bought, mined, transferred}}

    // Largest flow first so ribbon widths read as a visual ranking.
    const wares = Object.keys(prodRates)
      .filter(w => prodRates[w] > 0)
      .sort((a, b) => prodRates[b] - prodRates[a]);

    if (wares.length === 0) {
      return `<div style="padding:1.2rem 1.4rem;font-family:var(--font-data);font-size:1.1rem;color:var(--text-brand)">No production modules on this station.</div>`;
    }

    const inputs = Object.entries(inputRates)
      .filter(([, v]) => v.rate > 0)
      .sort((a, b) => b[1].rate - a[1].rate);
    const chipMode = Object.keys(breakdown).length > 0;
    const railMode = !chipMode && inputs.length > 0;

    // One tooltip row answering "where does this input come from?". Priority:
    // produced on-station beats the trade ledger (a self-supplied ware may
    // also log stray purchases); otherwise the last game-hour of deliveries
    // decides, collapsing to a single label when one channel dominates.
    const sourceRow = name => {
      if ((prodRates[name] || 0) > 0) return ['Source', '↺ station production', SVG_TEXT_DIM];
      const src    = sources[name] || {};
      const mined  = src.mined || 0, bought = src.bought || 0, xfer = src.transferred || 0;
      const total  = mined + bought + xfer;
      if (total <= 0) return ['Source', 'none last hour', CHART_WARN];
      const parts = [['own miners', mined], ['bought (NPC)', bought], ['own stations', xfer]]
        .sort((a, b) => b[1] - a[1]);
      const pct = Math.round(parts[0][1] / total * 100);
      return ['Source', pct >= 85 ? parts[0][0] : `mixed · ${pct}% ${parts[0][0]}`, SVG_TEXT_DIM];
    };

    // Net runtime for a self-supplied input: the stored runtime_hours is
    // stock ÷ consumption, which ignores replenishment — wrong for a ware the
    // station also produces. The real drain rate is (consumption − production);
    // when that's ≤ 0 stock only grows and the answer is "sustained" (null).
    // Slightly optimistic: assumes the producing module itself keeps running —
    // the lane badge already covers that module stalling, so no restatement here.
    const selfRuntimeMins = (name, consRate, stock) => {
      const net = consRate - (prodRates[name] || 0);
      return net > 0.5 ? (stock / net) * 60 : null;
    };

    // ── Geometry ─────────────────────────────────────────────────
    // Chip mode: each lane is as tall as its chip stack needs; rail mode keeps
    // the fixed lane height and centres the shorter column against the taller.
    const laneHeights = wares.map(w => {
      const n = chipMode ? Object.keys(breakdown[w] || {}).length : 0;
      return Math.max(PFLOW_LANE, n * PFLOW_CHIP + 16);
    });
    const lanesH  = laneHeights.reduce((a, b) => a + b, 0);
    const railH   = railMode ? inputs.length * PFLOW_INROW : 0;
    const bodyH   = Math.max(lanesH, railH);
    const laneTop = PFLOW_HEADER + (bodyH - lanesH) / 2;
    const railTop = PFLOW_HEADER + (bodyH - railH) / 2;
    const H = PFLOW_HEADER + bodyH + 10;

    // Lane vertical centres from the cumulative heights.
    const laneYs = [];
    { let y = laneTop;
      laneHeights.forEach(h => { laneYs.push(y + h / 2); y += h; }); }

    // One shared width scale across inputs and outputs so a 1,000/h input
    // ribbon visually equals a 1,000/h output ribbon. sqrt keeps high-volume
    // wares (energy cells) from flattening everything else to hairlines.
    const maxRate = Math.max(
      ...wares.map(w => prodRates[w]),
      ...inputs.map(([, v]) => v.rate));
    const ribbonW = r => Math.max(2, Math.round(22 * Math.sqrt(r / maxRate)));

    // Rail mode's input ribbons converge on the module column's vertical
    // midpoint — those older exports can't attribute an input to a specific
    // product, so a per-lane fan would imply precision that isn't in the data.
    const modMidY = (laneYs[0] + laneYs[laneYs.length - 1]) / 2;

    const rail = !railMode ? '' : inputs.map(([name, v], i) => {
      const iy      = railTop + i * PFLOW_INROW + PFLOW_INROW / 2;
      const wareCol = WARE_COLOURS[name] || CHART_LINE;

      // A produced-on-station input is replenished continuously, so its
      // stock-based runtime_hours would be misleading — use the net-drain
      // figure from selfRuntimeMins instead (null = sustained).
      const selfSupplied = (prodRates[name] || 0) > 0;
      const rtMins = v.runtime_hours === null ? null : v.runtime_hours * 60;
      const effMins = selfSupplied
        ? selfRuntimeMins(name, v.rate, v.stock ?? 0) : rtMins;
      let tone = 'primary';
      if (effMins !== null && effMins < 60) tone = 'negative';
      else if (effMins !== null && effMins < 120) tone = 'warning';
      const statusCol = tone === 'negative' ? CHART_LOSS : tone === 'warning' ? CHART_WARN : SVG_TEXT_DIM;

      const rtLabel = selfSupplied
        ? (effMins === null ? '↺ sustained' : '↺ ' + _pflowMins(effMins))
        : rtMins === null ? ''
        : rtMins <= 0 ? 'OUT'
        : _pflowMins(rtMins);
      const sub = `${_pflowRate(v.rate)}/h${rtLabel ? ' · ' + rtLabel : ''}`;

      const tipRows = [
        ['Consumption', `${_pflowRate(v.rate)}/h`],
        ['Stock', `${Math.round(v.stock ?? 0).toLocaleString()} units`],
      ];
      if (selfSupplied) tipRows.push(['Runtime',
        effMins === null ? 'Sustained (self-supplied)' : `${_pflowMins(effMins)} · net drain`,
        effMins === null ? SVG_TEXT_DIM : statusCol]);
      else if (rtMins !== null) tipRows.push(['Runtime', rtMins <= 0 ? 'Out of stock' : _pflowMins(rtMins), statusCol]);
      tipRows.push(sourceRow(name));
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
      const ly      = laneYs[i];
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

      // ── Left column ──────────────────────────────────────────
      let left = '';
      if (chipMode) {
        // One compact chip per recipe input, docked beside this lane's module
        // box with a short stub that only ever touches its own module — the
        // whole point of the redesign: nothing crosses another lane.
        const recipe = Object.entries(breakdown[w] || {}).sort((a, b) => b[1] - a[1]);
        if (recipe.length === 0) {
          left = `<text x="95" y="${ly + 4}" text-anchor="middle" font-size="10" style="font-family:var(--font-data);fill:${SVG_TEXT_DIM}" opacity="0.6">no inputs</text>`;
        } else {
          const startY = ly - (recipe.length * PFLOW_CHIP) / 2 + 2;
          left = recipe.map(([name, rate], j) => {
            const cy   = startY + j * PFLOW_CHIP;   // chip top edge
            const mid  = cy + 10;
            const col  = WARE_COLOURS[name] || CHART_LINE;
            const ir   = inputRates[name] || {};
            const selfSupplied = (prodRates[name] || 0) > 0;

            // Externally sourced wares use the stored stock÷rate runtime;
            // self-supplied ones use the net-drain figure (null = sustained,
            // shown as a bare ↺ to keep the chip compact).
            const rtMins = (ir.runtime_hours === null || ir.runtime_hours === undefined)
              ? null : ir.runtime_hours * 60;
            const selfMins = selfSupplied
              ? selfRuntimeMins(name, ir.rate || 0, ir.stock ?? 0) : null;
            let rtCol = SVG_TEXT_DIM, rtTxt = '';
            if (!selfSupplied && rtMins !== null) {
              rtTxt = rtMins <= 0 ? ' · OUT' : ' · ' + _pflowMins(rtMins);
              rtCol = rtMins < 60 ? CHART_LOSS : rtMins < 120 ? CHART_WARN : SVG_TEXT_DIM;
            } else if (selfSupplied && selfMins !== null) {
              rtTxt = ' · ↺ ' + _pflowMins(selfMins);
              rtCol = selfMins < 60 ? CHART_LOSS : selfMins < 120 ? CHART_WARN : SVG_TEXT_DIM;
            }

            const tipRows = [
              ['This module', `${_pflowRate(rate)}/h`],
              // Station total only when other lanes also consume this ware —
              // repeating an identical number is noise.
              ...(ir.rate && ir.rate - rate > 0.5
                ? [['Station total', `${_pflowRate(ir.rate)}/h`]] : []),
              ['Stock', `${Math.round(ir.stock ?? 0).toLocaleString()} units`],
              selfSupplied
                ? ['Runtime',
                   selfMins === null ? 'Sustained (self-supplied)' : `${_pflowMins(selfMins)} · net drain`,
                   selfMins === null ? SVG_TEXT_DIM : rtCol]
                : (rtMins !== null
                    ? ['Runtime', rtMins <= 0 ? 'Out of stock' : _pflowMins(rtMins), rtCol]
                    : null),
              sourceRow(name),
            ].filter(Boolean);
            const tipAttr = `data-pflow-input-tip="${encodeURIComponent(JSON.stringify({ ware: name, colour: col, rows: tipRows }))}"`;

            return `
              <line x1="172" y1="${mid}" x2="210" y2="${ly}" stroke="${col}" stroke-width="2" stroke-opacity="0.45"/>
              <g ${tipAttr} style="cursor:default">
                <rect x="10" y="${cy}" width="162" height="20" rx="3" fill="${SVG_SURFACE}" stroke="${SVG_OUTLINE}"/>
                <text x="18" y="${cy + 14}" font-size="10" style="font-family:var(--font-data)"><tspan fill="${col}">${name}</tspan><tspan fill="${SVG_TEXT_DIM}"> ${_pflowRate(rate)}${selfSupplied && selfMins === null ? ' ↺' : ''}</tspan><tspan fill="${rtCol}">${rtTxt}</tspan></text>
              </g>`;
          }).join('');
        }
      } else if (!railMode) {
        // Fallback chip (no input data at all in this export): the limiting
        // input is the only input-side fact available.
        let chipTxt, chipCol;
        if (mins === null) {
          chipTxt = 'No inputs needed';
          chipCol = SVG_TEXT_DIM;
        } else {
          chipTxt = `${rt.limiting_ware || 'Inputs'} · ${_pflowMins(mins)}`;
          chipCol = tone === 'primary' ? SVG_TEXT_DIM : statusCol;
        }
        left = `
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

      const wExp = ribbonW(exp);
      const expRibbon = exp > 0.5 ? `
        <path d="M380,${ly - 10} H700" fill="none" stroke="${wareCol}" stroke-width="${wExp}" stroke-opacity="0.75"/>
        <text x="540" y="${ly - 10 - wExp / 2 - 5}" text-anchor="middle" font-size="12" style="font-family:var(--font-data);fill:${SVG_TEXT_DIM}">${_pflowRate(exp)}/h export</text>` : '';
      // Internal use stays on its own row as a pill (see header comment) —
      // its counterpart is the ↺ marker on the consuming lanes' input chips.
      const intPill = consInt > 0.5 ? `
        <g ${laneTipAttr} style="cursor:default">
          <rect x="390" y="${ly + 6}" width="170" height="24" rx="12" fill="${wareCol}18" stroke="${wareCol}50"/>
          <text x="475" y="${ly + 22}" text-anchor="middle" font-size="11" style="font-family:var(--font-data);fill:${wareCol}">↻ ${_pflowRate(consInt)}/h internal</text>
        </g>` : '';

      return `${left}${expRibbon}${intPill}
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

    const hdr = (x, label) =>
      `<text x="${x}" y="20" text-anchor="middle" font-size="11" style="font-family:var(--font-data);letter-spacing:0.18em;fill:${SVG_BRAND}">${label}</text>`;
    const inputHdr = chipMode ? hdr(95, 'INPUTS / HR')
      : railMode ? hdr(83, 'INPUTS') : hdr(98, 'INPUTS');

    return `<div style="padding:0.8rem 1rem">
      <svg viewBox="0 0 ${PFLOW_W} ${H}" style="width:100%;height:auto;display:block" xmlns="http://www.w3.org/2000/svg">
        ${inputHdr}${hdr(295, 'MODULES')}${hdr(796, 'OUTPUT / HR')}
        ${rail}${lanes}
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
