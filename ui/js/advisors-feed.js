  // Core role: Advisor tabs (Economic + Military) — renders the export
  // `advisors` findings as a ranked briefing (summary strip, type filter,
  // priority-railed advice cards with expandable evidence drawers).
  //
  // §11 namespace file: populate() hands data in via setData(); the sidebar's
  // Advisors items call render(view) when a tab opens. One namespace serves
  // both tabs: compute_advisors() returns a single merged findings list, so
  // each view filters its own domain slice out of it rather than the export
  // splitting server-side — the card/drawer machinery is identical either
  // way. Layout classes live in css/advisors.css. Two looks are NEW to this
  // tab by design (it's a headline feature): the vertical priority rail on
  // each card (fill height = score relative to the view's top finding, so
  // rank is readable at a glance without comparing numbers) and the
  // click-to-expand evidence drawer (advice must be auditable — every card
  // can show the raw numbers it was derived from).
  window.AdvisorsFeed = (function () {

    // View → root element + which domains it shows. Economic keeps everything
    // that isn't military (economy + logistics predate the split and share a
    // tab); priority scores only compete WITHIN a view, so military's
    // threat-point units never fight economy's Cr/hr for rail height.
    const VIEWS = {
      economic: { root: 'advisors-root',          match: f => f.domain !== 'military' },
      military: { root: 'advisors-military-root', match: f => f.domain === 'military' },
    };

    // Finding type → presentation. `tone` picks the semantic colour trio via
    // an adv--<tone> modifier class in advisors.css — colours stay in CSS
    // where the tokens live, JS only chooses the meaning.
    const TYPE_META = {
      overflow_risk:      { label: 'Overflow Risk',      icon: 'ti-stack-2',      tone: 'warning'  },
      market_opportunity: { label: 'Market Opportunity', icon: 'ti-trending-up',  tone: 'positive' },
      pricing_gap:        { label: 'Pricing Gap',        icon: 'ti-scale',        tone: 'info'     },
      idle_hauler:        { label: 'Idle Hauler',        icon: 'ti-anchor',       tone: 'special'  },
      hostile_presence:   { label: 'Hostile Presence',   icon: 'ti-alert-triangle', tone: 'negative' },
      damaged_fleet:      { label: 'Damaged Ship',       icon: 'ti-tool',         tone: 'warning'  },
    };
    const FALLBACK_META = { label: 'Finding', icon: 'ti-clipboard-list', tone: 'info' };

    const DOMAIN_LABELS = { economy: 'Economy', logistics: 'Logistics', military: 'Military' };

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
      sector_macro:       'Sector',
      faction_id:         'Faction',
      reputation:         'Reputation',
      combat_count:       'Combat Ships',
      noncombat_count:    'Non-Combat Ships',
      defender_count:     'Your Combat Ships There',
      hull_hp:            'Hull HP',
      hull_max:           'Hull Max HP',
      shield_pct:         'Shield %',
    };

    let _findings = [];
    let _view     = 'economic';
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
    // Everything below renders one VIEW's slice of the merged findings list;
    // the full list stays untouched so switching tabs is a pure re-render.
    const _viewFindings = () => _findings.filter(VIEWS[_view].match);
    const _rows = vf => _filter === 'all'
      ? vf
      : vf.filter(f => f.type === _filter);

    // ── Briefing strip ────────────────────────────────────────────────
    // Headline totals derived from the findings' raw slots (bodies are
    // display strings — never re-parse those). Each cell only renders when
    // its rule produced something, so an empty domain doesn't show a dead 0 —
    // which is also what keeps the economy cells off the Military view and
    // vice versa.
    function _briefingHtml(vf) {
      const sum = (types, slot) => vf
        .filter(f => types.includes(f.type))
        .reduce((n, f) => n + (f.slots[slot] || 0), 0);
      const perHour  = sum(['overflow_risk', 'market_opportunity'], 'value_per_hour');
      const oneTime  = sum(['pricing_gap'], 'gain');
      const idleCap  = sum(['idle_hauler'], 'cargo_max');
      const hostile  = sum(['hostile_presence'], 'ship_count');
      const damaged  = vf.filter(f => f.type === 'damaged_fleet').length;
      const cells = [
        ['Findings', vf.length.toLocaleString()],
        perHour ? ['Cr/hr at Stake', perHour.toLocaleString()] : null,
        oneTime ? ['One-Time Gains Cr', oneTime.toLocaleString()] : null,
        idleCap ? ['Idle Capacity m³', idleCap.toLocaleString()] : null,
        hostile ? ['Hostile Ships Nearby', hostile.toLocaleString()] : null,
        damaged ? ['Ships Needing Repair', damaged.toLocaleString()] : null,
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
      // Rail fill is score relative to the view's TOP finding (not the
      // type-filtered subset), so a card's rail doesn't change when the
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

    function render(view) {
      // A view change resets the type filter and open drawers — the chips on
      // the other tab reference types this view's list doesn't contain, so a
      // carried-over filter would show a confusingly empty list.
      if (view && view !== _view) { _view = view; _filter = 'all'; _open = new Set(); }
      const root = document.getElementById(VIEWS[_view].root);
      if (!root) return;

      const vf = _viewFindings();
      if (!vf.length) {
        const sub = _view === 'military'
          ? "No hostile presence near your position and no combat ships in need of repair."
          : "Either the empire runs clean, or there's no production surplus / reachable NPC demand near your current sector yet.";
        root.innerHTML = `<div class="adv-empty">
            <i class="ti ti-clipboard-list"></i>
            <div>No findings this scan.</div>
            <div class="adv-empty-sub">${sub}</div>
          </div>`;
        return;
      }

      // Same shared rem-based chip the Events filter uses (see events.css for
      // why it's .station-tab-btn and not the chart cards' .cf-toggle-btn).
      const count = t => vf.filter(f => f.type === t).length;
      const chip = (key, label, n) =>
        `<button class="station-tab-btn ${_filter === key ? 'active' : ''}" onclick="AdvisorsFeed.setFilter('${key}')">${label}<span class="adv-filter-count">${n.toLocaleString()}</span></button>`;
      const chips = [chip('all', 'All', vf.length)]
        .concat(Object.keys(TYPE_META)
          .filter(t => count(t))
          .map(t => chip(t, TYPE_META[t].label, count(t))))
        .join('');
      // Right-justified in the same row as the type chips — one flex row,
      // help pushed to the far end via margin-left:auto (adv-help-btn in
      // advisors.css), rather than a second row that'd waste vertical space.
      const helpBtn = `<button class="adv-help-btn" onclick="AdvisorsFeed.openHelp()" title="What do these findings mean?"><i class="ti ti-help-circle"></i></button>`;

      // Findings arrive pre-sorted by priority; rank is the position in the
      // full VIEW list so #3 stays #3 when a filter hides #1 and #2. Rank and
      // rail are view-relative — military threat points and economy Cr/hr are
      // different units, so cross-domain comparison would be meaningless.
      const maxScore  = vf[0].priority_score || 1;
      const rankById  = new Map(vf.map((f, i) => [f.id, i + 1]));
      const cards = _rows(vf)
        .map(f => _cardHtml(f, rankById.get(f.id), maxScore))
        .join('');

      root.innerHTML = `
        ${_briefingHtml(vf)}
        <div class="adv-filter">${chips}${helpBtn}</div>
        <div class="adv-list">${cards}</div>`;
    }

    return { setData, setFilter, toggle, render, openHelp };
  })();
