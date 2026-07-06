  // Core role: Economic Advisor tab — renders the export `advisors` findings
  // as a ranked briefing (summary strip, type filter, priority-railed advice
  // cards with expandable evidence drawers).
  //
  // §11 namespace file: populate() hands data in via setData(); the sidebar's
  // Advisors > Economic item calls render() when the tab opens. Layout classes
  // live in css/advisors.css. Two looks are NEW to this tab by design (it's a
  // headline feature): the vertical priority rail on each card (fill height =
  // score relative to the top finding, so rank is readable at a glance without
  // comparing numbers) and the click-to-expand evidence drawer (advice must be
  // auditable — every card can show the raw numbers it was derived from).
  window.AdvisorsFeed = (function () {

    // Finding type → presentation. `tone` picks the semantic colour trio via
    // an adv--<tone> modifier class in advisors.css — colours stay in CSS
    // where the tokens live, JS only chooses the meaning.
    const TYPE_META = {
      overflow_risk:      { label: 'Overflow Risk',      icon: 'ti-stack-2',      tone: 'warning'  },
      market_opportunity: { label: 'Market Opportunity', icon: 'ti-trending-up',  tone: 'positive' },
      pricing_gap:        { label: 'Pricing Gap',        icon: 'ti-scale',        tone: 'info'     },
      idle_hauler:        { label: 'Idle Hauler',        icon: 'ti-anchor',       tone: 'special'  },
    };
    const FALLBACK_META = { label: 'Finding', icon: 'ti-clipboard-list', tone: 'info' };

    const DOMAIN_LABELS = { economy: 'Economy', logistics: 'Logistics' };

    // Evidence keys → readable labels. Anything not listed falls back to the
    // raw key with underscores spaced — a new rule's evidence still renders.
    const EVIDENCE_LABELS = {
      station_id:         'Station',
      npc_station_id:     'NPC Station',
      ship_id:            'Ship',
      homebase_id:        'Home Station',
      code:               'Code',
      ware_id:            'Ware',
      surplus_rate:       'Surplus /hr',
      time_to_cap_hours:  'Hours to Cap',
      demand_depth:       'Unmet Demand',
      jumps:              'Jumps Away',
      amount:             'Stock Units',
      player_price_cents: 'Your Price (¢)',
      npc_price_cents:    'Their Price (¢)',
      cargo_m3:           'Cargo Load m³',
      cargo_max_m3:       'Cargo Cap m³',
    };

    let _findings = [];
    let _filter   = 'all';
    let _open     = new Set();   // finding ids with an expanded evidence drawer

    function setData(advisors) {
      _findings = (advisors && advisors.findings) || [];
      _filter   = 'all';
      _open     = new Set();     // stale drawers from the previous scan close
    }

    function setFilter(type) { _filter = type; render(); }

    function toggle(id) {
      _open.has(id) ? _open.delete(id) : _open.add(id);
      render();
    }

    // Opens the standalone Help tab explaining the 4 finding types. Recorded
    // as a jump (not a plain switchTab) so the Back button in the sidebar
    // returns here — same trail mechanism as the station/sector jump links.
    function openHelp() {
      _navRecord();
      switchTab('advisors-help', null);
      _navAfterJump();
    }

    const _meta = f => TYPE_META[f.type] || FALLBACK_META;
    const _rows = () => _filter === 'all'
      ? _findings
      : _findings.filter(f => f.type === _filter);

    // ── Briefing strip ────────────────────────────────────────────────
    // Headline totals derived from the findings' raw slots (bodies are
    // display strings — never re-parse those). Each cell only renders when
    // its rule produced something, so an empty domain doesn't show a dead 0.
    function _briefingHtml() {
      const sum = (types, slot) => _findings
        .filter(f => types.includes(f.type))
        .reduce((n, f) => n + (f.slots[slot] || 0), 0);
      const perHour  = sum(['overflow_risk', 'market_opportunity'], 'value_per_hour');
      const oneTime  = sum(['pricing_gap'], 'gain');
      const idleCap  = sum(['idle_hauler'], 'cargo_max');
      const cells = [
        ['Findings', _findings.length.toLocaleString()],
        perHour ? ['Cr/hr at Stake', perHour.toLocaleString()] : null,
        oneTime ? ['One-Time Gains Cr', oneTime.toLocaleString()] : null,
        idleCap ? ['Idle Capacity m³', idleCap.toLocaleString()] : null,
      ].filter(Boolean);
      return `<div class="adv-stats">${cells.map(([label, value]) => `
          <div class="adv-stat">
            <span class="adv-stat-label">${label}</span>
            <span class="adv-stat-value">${value}</span>
          </div>`).join('')}</div>`;
    }

    // ── Evidence drawer ───────────────────────────────────────────────
    function _evidenceHtml(f) {
      const rows = Object.entries(f.evidence).map(([k, v]) => {
        const label = EVIDENCE_LABELS[k] || k.replace(/_/g, ' ');
        const value = typeof v === 'number'
          ? (Number.isInteger(v) ? v.toLocaleString() : v.toLocaleString(undefined, { maximumFractionDigits: 2 }))
          : (v ?? '—');
        return `<div class="adv-ev-key">${label}</div><div class="adv-ev-val">${value}</div>`;
      }).join('');
      return `<div class="adv-drawer">
          <div class="adv-evidence">
            ${rows}
            <div class="adv-ev-key">Priority Score</div>
            <div class="adv-ev-val">${f.priority_score.toLocaleString()}</div>
          </div>
        </div>`;
    }

    // ── Cards ─────────────────────────────────────────────────────────
    function _cardHtml(f, rank, maxScore) {
      const m = _meta(f);
      // Rail fill is score relative to the TOP finding across ALL findings
      // (not the filtered view), so a card's rail doesn't change when the
      // filter does. Floored at 6% so even the weakest finding shows a tick.
      const pct  = Math.max(6, Math.round(f.priority_score / maxScore * 100));
      const open = _open.has(f.id);
      return `
        <div class="adv-card adv--${m.tone}${open ? ' open' : ''}">
          <div class="adv-rail"><div class="adv-rail-fill" style="height:${pct}%"></div></div>
          <div class="adv-card-main" onclick="AdvisorsFeed.toggle('${f.id}')">
            <div class="adv-card-head">
              <span class="adv-rank">${rank}</span>
              <i class="ti ${m.icon} adv-icon"></i>
              <span class="adv-type">${m.label}</span>
              <span class="adv-domain">${DOMAIN_LABELS[f.domain] || f.domain}</span>
              <i class="ti ti-chevron-down adv-chev"></i>
            </div>
            <div class="adv-card-body">${f.body}</div>
            ${_evidenceHtml(f)}
          </div>
        </div>`;
    }

    function render() {
      const root = document.getElementById('advisors-root');
      if (!root) return;

      if (!_findings.length) {
        root.innerHTML = `<div class="adv-empty">
            <i class="ti ti-clipboard-list"></i>
            <div>No findings this scan.</div>
            <div class="adv-empty-sub">Either the empire runs clean, or there's no
            production surplus / reachable NPC demand near your current sector yet.</div>
          </div>`;
        return;
      }

      // Same shared rem-based chip the Events filter uses (see events.css for
      // why it's .station-tab-btn and not the chart cards' .cf-toggle-btn).
      const count = t => _findings.filter(f => f.type === t).length;
      const chip = (key, label, n) =>
        `<button class="station-tab-btn ${_filter === key ? 'active' : ''}" onclick="AdvisorsFeed.setFilter('${key}')">${label}<span class="adv-filter-count">${n.toLocaleString()}</span></button>`;
      const chips = [chip('all', 'All', _findings.length)]
        .concat(Object.keys(TYPE_META)
          .filter(t => count(t))
          .map(t => chip(t, TYPE_META[t].label, count(t))))
        .join('');
      // Right-justified in the same row as the type chips — one flex row,
      // help pushed to the far end via margin-left:auto (adv-help-btn in
      // advisors.css), rather than a second row that'd waste vertical space.
      const helpBtn = `<button class="adv-help-btn" onclick="AdvisorsFeed.openHelp()" title="What do these findings mean?"><i class="ti ti-help-circle"></i></button>`;

      // Findings arrive pre-sorted by priority; rank is the position in the
      // FULL list so #3 stays #3 when a filter hides #1 and #2.
      const maxScore  = _findings[0].priority_score || 1;
      const rankById  = new Map(_findings.map((f, i) => [f.id, i + 1]));
      const cards = _rows()
        .map(f => _cardHtml(f, rankById.get(f.id), maxScore))
        .join('');

      root.innerHTML = `
        ${_briefingHtml()}
        <div class="adv-filter">${chips}${helpBtn}</div>
        <div class="adv-list">${cards}</div>`;
    }

    return { setData, setFilter, toggle, render, openHelp };
  })();
