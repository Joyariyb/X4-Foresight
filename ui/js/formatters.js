  // Core role: Shared UI formatters (credits, percentages, times, durations, quantities).

  function fmtCredits(n) {
    n = parseFloat(n);
    if (isNaN(n)) return "—";
    if (n >= 1e6) return (n/1e6).toFixed(1) + "M Cr";
    if (n >= 1e3) return (n/1e3).toFixed(1) + "k Cr";
    return n.toLocaleString() + " Cr";
  }

  // Same K/M abbreviation as fmtCredits but unit-less, for stat-card values
  // (hull HP, price, etc.) that need to stay short in a fixed-width mono
  // column rather than showing the "Cr" suffix. Callers that abbreviate
  // should also set a title="" with the full toLocaleString() value so the
  // exact figure is still one hover away.
  function fmtCompact(n) {
    n = parseFloat(n);
    if (isNaN(n)) return "—";
    if (n >= 1e6) return (n/1e6).toFixed(1) + "M";
    if (n >= 1e5) return (n/1e3).toFixed(1) + "k";
    return n.toLocaleString();
  }

  function hullBadge(origin) {
    if (!origin) return '<span class="badge">—</span>';
    // Coloured from FACTION_COLOURS (same source as designBadge() in
    // designs-builder.js) rather than a per-faction CSS class — there is no
    // ".badge.argon" etc. defined in CSS, so the old per-faction class names
    // rendered every origin as a plain, uncoloured box.
    const hostile = HOSTILE_ORIGINS.has(origin);
    const colour  = FACTION_COLOURS[origin.toLowerCase()] || '#6e7681';
    const style   = `background:${hexA(colour, 0.1)};color:${colour};border:1px solid ${hexA(colour, 0.25)}`;
    const label   = hostile ? `* ${origin}` : origin;
    return `<span class="badge" style="${style}">${label}</span>`;
  }

  function tierBadge(tier) {
    if (!tier) return '<span class="badge">—</span>';
    const cls = tier.toLowerCase().replace(" ","");
    return `<span class="badge ${cls}">${tier}</span>`;
  }

  function repBar(value) {
    const pct = Math.min(Math.abs(value) / 30 * 100, 100).toFixed(1);
    const col = value >= 0 ? "var(--color-positive)" : "var(--color-negative)";
    const dir = value >= 0 ? "left" : "right";
    return `<div class="rep-bar-wrap"><div class="rep-bar" style="width:${pct}%;background:${col};float:${dir}"></div></div>`;
  }

  function sign(n) { return n >= 0 ? `+${n.toFixed(2)}` : n.toFixed(2); }

  function hullBar(pct, hullHp, maxHull) {
    if (pct === null || pct === undefined) {
      const raw = (hullHp !== null && hullHp !== undefined)
        ? Math.round(hullHp).toLocaleString() + " HP"
        : "—";
      return `<span style="font-family:var(--font-data);font-size:10px;color:var(--text-brand)">${raw}</span>`;
    }

    const barWidth = Math.min(pct, 100).toFixed(1);
    let color;
    if (pct > 100) {
      color = "var(--color-info)";
    } else {
      // Squaring the ratio makes colour shift from green toward red faster —
      // 80% health already reads as yellow-green rather than staying near-green.
      const hue = Math.pow(Math.min(pct, 100) / 100, 2) * 120;
      color = `hsl(${hue.toFixed(0)},65%,50%)`;
    }

    const label = pct >= 100 ? "Full" : `${Math.round(pct)}%`;
    const tipParts = [label];
    if (maxHull !== null && maxHull !== undefined) {
      const current = (hullHp !== null && hullHp !== undefined)
        ? Math.round(hullHp).toLocaleString()
        : maxHull.toLocaleString();
      tipParts.push(`${current} / ${maxHull.toLocaleString()} HP`);
    } else if (hullHp !== null && hullHp !== undefined) {
      tipParts.push(`${Math.round(hullHp).toLocaleString()} HP`);
    }

    return `<div class="hull-bar-wrap" style="cursor:default"
        data-hull-tip="${tipParts.join(' · ')}" data-hull-color="${color}">
      <div class="hull-bar" style="width:${barWidth}%;background:${color}"></div>
    </div>`;
  }

  // Shield bar — reuses hullBar's markup (so the shared #hull-tip hover tooltip
  // just works) but a blue→amber→red scheme so shields read as visually distinct
  // from the green→red hull bar. Same thresholds the station cards use for
  // shields. Only player ships carry shield data; NPC ships fall through to "—".
  function shieldBar(pct, shieldHp, maxShield) {
    if (pct === null || pct === undefined) {
      const raw = (shieldHp !== null && shieldHp !== undefined)
        ? Math.round(shieldHp).toLocaleString() + " HP"
        : "—";
      return `<span style="font-family:var(--font-data);font-size:10px;color:var(--text-brand)">${raw}</span>`;
    }

    const barWidth = Math.min(pct, 100).toFixed(1);
    const color = pct >= 80 ? "var(--color-info)" : pct >= 50 ? "var(--color-warning)" : "var(--color-negative)";

    const label = pct >= 100 ? "Full" : `${Math.round(pct)}%`;
    const tipParts = [label];
    if (maxShield !== null && maxShield !== undefined) {
      const current = (shieldHp !== null && shieldHp !== undefined)
        ? Math.round(shieldHp).toLocaleString()
        : maxShield.toLocaleString();
      tipParts.push(`${current} / ${maxShield.toLocaleString()} HP`);
    } else if (shieldHp !== null && shieldHp !== undefined) {
      tipParts.push(`${Math.round(shieldHp).toLocaleString()} HP`);
    }

    return `<div class="hull-bar-wrap" style="cursor:default"
        data-hull-tip="${tipParts.join(' · ')}" data-hull-color="${color}">
      <div class="hull-bar" style="width:${barWidth}%;background:${color}"></div>
    </div>`;
  }

  // Converts raw skill points (0–15) to 5 HTML stars (full / half / empty).
  // Half-star uses an absolutely-positioned clipped overlay so no font/icon
  // dependency is needed — just plain Unicode ★ and ☆ glyphs.
  // Wrap the returned HTML in a span with data-hull-tip to get the hover tooltip.
  function skillStars(value) {
    // 3 pts = 1 star; round to nearest 0.5 so we get clean half-star steps
    const stars = Math.round((value / 3) * 2) / 2;
    let html = '';
    for (let i = 1; i <= 5; i++) {
      if (stars >= i) {
        // full star
        html += `<span style="color:var(--color-warning)">★</span>`;
      } else if (stars >= i - 0.5) {
        // half star: dim empty star underneath, amber star clipped to 50% on top
        html += `<span style="position:relative;display:inline-block">` +
                `<span style="color:var(--text-secondary)">★</span>` +
                `<span style="position:absolute;left:0;top:0;width:50%;overflow:hidden;color:var(--color-warning)">★</span>` +
                `</span>`;
      } else {
        // empty star
        html += `<span style="color:var(--text-secondary)">☆</span>`;
      }
    }
    return html;
  }

  // Builds the inner HTML for the pilot skills hover tooltip.
  // Renders each skill as a labelled row of stars with the raw point value dim beside it.
  // Only skills present in the data are shown — boarding is rare, morale is always there.
  // The optional `name` parameter adds the pilot's name as a teal header at the top,
  // which is how the pilot cell shows the name now that it's been moved off the row.
  function pilotTipHtml(skills, name) {
    const SKILL_ORDER = [
      ['piloting',    'Piloting'],
      ['management',  'Management'],
      ['engineering', 'Engineering'],
      ['morale',      'Morale'],
      ['boarding',    'Boarding'],
    ];
    const rows = SKILL_ORDER.filter(([key]) => skills[key] != null);
    const nameHeader = name
      ? `<div style="color:var(--color-primary);font-weight:700;margin-bottom:${rows.length ? 6 : 0}px;` +
        `${rows.length ? 'padding-bottom:5px;border-bottom:1px solid var(--outline);' : ''}` +
        `white-space:nowrap">${name}</div>`
      : '';
    if (!rows.length) return nameHeader || '—';
    return nameHeader + rows.map(([key, label]) => {
      const pts = skills[key];
      return `<div style="display:flex;align-items:center;gap:8px">` +
             `<span style="min-width:82px;letter-spacing:0.06em;text-transform:uppercase">${label}</span>` +
             `<span style="letter-spacing:-1px">${skillStars(pts)}</span>` +
             `<span style="min-width:16px;text-align:right">${pts}</span>` +
             `</div>`;
    }).join('');
  }


  // ── Tooltip registration ──────────────────────────────────────────
  // Hull/shield bars stamp data-hull-tip (+ data-hull-color): plain coloured text,
  // no HTML. The simplest tip, and the historical default branch of the dispatcher.
  registerTip('hullTip', (el, _e, tip) => {
    tip.textContent      = el.dataset.hullTip;
    tip.style.color      = el.dataset.hullColor || '';
    tip.style.whiteSpace = 'nowrap';
    return true;
  });

  // Generic plain-text tip for anything that would otherwise reach for a native
  // title= (icons, table cells, buttons, …). Stamp data-text-tip instead so the
  // hover renders through the shared, styled #hull-tip popover — never title=,
  // it renders unstyled and can't be positioned (see UI_STANDARDS.md §8).
  registerTip('textTip', (el, _e, tip) => {
    tip.textContent      = el.dataset.textTip;
    tip.style.color      = '';
    tip.style.whiteSpace = 'nowrap';
    return true;
  });
