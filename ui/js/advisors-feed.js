  // Core role: Advisor tabs (Economic + Military + Trader) — renders the export
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
    // that isn't military or trader (economy + logistics predate the split
    // and share a tab); priority scores only compete WITHIN a view, so
    // military's threat-point units never fight economy's Cr/hr for rail
    // height, and trader's own mixed units (Cr, Cr/hr, credits banked) never
    // fight either of the others.
    const VIEWS = {
      economic: { root: 'advisors-root',          match: f => f.domain !== 'military' && f.domain !== 'trader' },
      military: { root: 'advisors-military-root', match: f => f.domain === 'military' },
      trader:   { root: 'advisors-trader-root',   match: f => f.domain === 'trader' },
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
      composition_gap:    { label: 'Tracking Mismatch',  icon: 'ti-crosshair',    tone: 'warning'  },
      outranged:          { label: 'Outranged',          icon: 'ti-ruler-2',      tone: 'warning'  },
      buildup:            { label: 'Force Build-Up',     icon: 'ti-trending-up-2', tone: 'negative' },
      damaged_fleet:      { label: 'Damaged Ship',       icon: 'ti-tool',         tone: 'warning'  },
      station_siting:         { label: 'Station Siting',       icon: 'ti-building',         tone: 'special'  },
      galaxy_arbitrage:       { label: 'Galaxy Arbitrage',     icon: 'ti-arrows-exchange',   tone: 'positive' },
      stranded_delivery:      { label: 'Stranded Delivery',    icon: 'ti-alert-circle',      tone: 'warning'  },
      idle_trade_capital:     { label: 'Idle Trade Capital',   icon: 'ti-cash',              tone: 'info'     },
      reputation_locked_trade:{ label: 'Reputation Locked',    icon: 'ti-lock',              tone: 'negative' },
    };
    const FALLBACK_META = { label: 'Finding', icon: 'ti-clipboard-list', tone: 'info' };

    const DOMAIN_LABELS = { economy: 'Economy', logistics: 'Logistics', military: 'Military', trader: 'Trader' };

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
      unassessed_count:   'Ships Unassessed',
      their_dps:          'Their Damage /s',
      our_dps:            'Your Damage /s',
      their_ehp:          'Their Hull+Shield HP',
      our_ehp:            'Your Hull+Shield HP',
      ttk_they_break_us_s: 'They Break You In (s)',
      ttk_we_break_them_s: 'You Break Them In (s)',
      hostile_fleet_value_cr: 'Hostile Fleet Value Cr',
      small_count:        'Hostile Strike Craft',
      hostile_ship_count: 'Hostile Ships Total',
      our_anti_small_dps: 'Your Anti-Fighter Damage /s',
      their_range_m:      'Their Max Range (m)',
      our_range_m:        'Your Max Range (m)',
      capital_count:      'Hostile Capitals',
      overall_growth:     'Overall Strength Growth ×',
      firepower_from:     'Firepower Then (dmg/s)',
      firepower_to:       'Firepower Now (dmg/s)',
      firepower_growth:   'Firepower Growth ×',
      shield_from:        'Shield HP Then',
      shield_to:          'Shield HP Now',
      shield_growth:      'Shield Growth ×',
      hull_from:          'Hull HP Then',
      hull_to:            'Hull HP Now',
      hull_growth:        'Hull Growth ×',
      scans_rising:       'Scans Rising',
      anchor:             'Proximity Anchor',
      recharge_max:       'Reservoir Capacity',
      yield_level:        'Yield Level',
      avg_price:          'Average Price Cr',
      sell_station_id:    'Sell Station',
      buy_station_id:     'Buy Station',
      sell_jumps:         'Jumps to Seller',
      buy_jumps:          'Jumps to Buyer',
      volume:             'Tradeable Units',
      sell_price_cents:   'Sell Price (¢)',
      buy_price_cents:    'Buy Price (¢)',
      time_ago_s:         'Seconds Since Pickup',
      value_estimate:     'Estimated Value Cr',
      player_credits:     'Credits Banked',
      trader_ships:       'Trading Ships',
      total_ships:        'Total Ships',
      ratio:              'Trading Ship Ratio',
      reputation_value:   'Reputation Value',
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

    // Deep-links into the Help hub topic for the current view — economic,
    // military and trader each have their own explainer (the military one
    // also covers verdicts and counter advice, which the others don't have).
    // Recorded as a jump (not a plain Help.open) so the Back button in the
    // sidebar returns here — same trail mechanism as the station/sector links.
    const HELP_TOPIC = {
      military: 'help-advisors-military',
      trader:   'help-advisors-trader',
    };
    function openHelp() {
      _navRecord();
      Help.open(HELP_TOPIC[_view] || 'help-advisors-economic');
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
      // Sectors where the force comparison says the defence loses (or does
      // not exist) — the strongest single number on the military briefing.
      const losing   = vf.filter(f => f.type === 'hostile_presence'
        && (f.slots.verdict === 'Outmatched' || f.slots.verdict === 'Undefended')).length;
      const staging  = vf.filter(f => f.type === 'buildup').length;
      // Trader-only cells: siting count (a demand-note doesn't change the
      // count, just the card text), arbitrage/one-time Cr, stranded ships,
      // idle credits banked, and factions currently locked out of trade.
      const sitingCount = vf.filter(f => f.type === 'station_siting').length;
      const arbGain     = sum(['galaxy_arbitrage'], 'gain');
      const strandedCnt = vf.filter(f => f.type === 'stranded_delivery').length;
      const idleCredits = sum(['idle_trade_capital'], 'credits');
      const lockedCnt   = vf.filter(f => f.type === 'reputation_locked_trade').length;
      const cells = [
        ['Findings', vf.length.toLocaleString()],
        perHour ? ['Cr/hr at Stake', perHour.toLocaleString()] : null,
        oneTime ? ['One-Time Gains Cr', oneTime.toLocaleString()] : null,
        idleCap ? ['Idle Capacity m³', idleCap.toLocaleString()] : null,
        hostile ? ['Hostile Ships Nearby', hostile.toLocaleString()] : null,
        losing  ? ['Sectors Outmatched', losing.toLocaleString()] : null,
        staging ? ['Build-Ups Detected', staging.toLocaleString()] : null,
        damaged ? ['Ships Needing Repair', damaged.toLocaleString()] : null,
        sitingCount ? ['Siting Opportunities', sitingCount.toLocaleString()] : null,
        arbGain     ? ['Arbitrage Cr at Stake', arbGain.toLocaleString()] : null,
        strandedCnt ? ['Stranded Deliveries', strandedCnt.toLocaleString()] : null,
        idleCredits ? ['Idle Credits Cr', idleCredits.toLocaleString()] : null,
        lockedCnt   ? ['Factions Locked Out', lockedCnt.toLocaleString()] : null,
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
    // Counter-advice hover body, pre-rendered at stamp time (the trendTip
    // pattern from UI_STANDARDS §8). Rows come from the finding's optional
    // `counters` list — the rule already picked which archetypes apply, so
    // this only lays them out.
    function _counterTipHtml(f) {
      const rows = f.counters.map(c => `
        <div style="color:var(--color-warning);font-family:var(--font-label);font-size:1.1rem;letter-spacing:0.05em;text-transform:uppercase;margin-top:0.5rem">${c.threat}</div>
        <div style="color:var(--text-secondary)">${c.advice}</div>`).join('');
      return `<div style="min-width:22rem;max-width:30rem;padding:0.2rem 0">
          <div style="font-size:1.3rem;font-weight:600;color:var(--text-primary)">Counter Advice</div>
          ${rows}
        </div>`;
    }

    function _cardHtml(f, rank, maxScore) {
      const m = _meta(f);
      // Rail fill is score relative to the view's TOP finding (not the
      // type-filtered subset), so a card's rail doesn't change when the
      // filter does. Floored at 6% so even the weakest finding shows a tick.
      const pct  = Math.max(6, Math.round(f.priority_score / maxScore * 100));
      const open = _open.has(f.id);
      const counters = f.counters && f.counters.length
        ? `<i class="ti ti-swords adv-counter" data-adv-counter-tip="${encodeURIComponent(_counterTipHtml(f))}"></i>`
        : '';
      return `
        <div class="adv-card adv--${m.tone}${open ? ' open' : ''}">
          <div class="adv-rail"><div class="adv-rail-fill" style="height:${pct}%"></div></div>
          <div class="adv-card-main" onclick="AdvisorsFeed.toggle('${f.id}')">
            <div class="adv-card-head">
              <span class="adv-rank">${rank}</span>
              <i class="ti ${m.icon} adv-icon"></i>
              <span class="adv-type">${m.label}</span>
              ${counters}
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
        const EMPTY_SUB = {
          military: "No hostile presence near your position and no combat ships in need of repair.",
          trader:   "No unclaimed resource sectors, reachable arbitrage spread, stranded couriers, idle capital or reputation-locked trade found this scan.",
        };
        const sub = EMPTY_SUB[_view]
          || "Either the empire runs clean, or there's no production surplus / reachable NPC demand near your current sector yet.";
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
      // data-text-tip, not title= — the generic plain-text handler in
      // formatters.js routes it through the shared styled popover (§8).
      const helpBtn = `<button class="adv-help-btn" onclick="AdvisorsFeed.openHelp()" data-text-tip="What do these findings mean?"><i class="ti ti-help-circle"></i></button>`;

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

    // ── Tooltip registration ──────────────────────────────────────────
    // Counter-advice hover on the military cards' swords icon: pre-rendered
    // HTML, decoded here (trendTip pattern). Both style resets matter — the
    // shared #hull-tip defaults to nowrap/alert-colour, which multi-line
    // advice must override every show (another handler may have run since).
    registerTip('advCounterTip', (el, _e, tip) => {
      tip.innerHTML = decodeURIComponent(el.dataset.advCounterTip);
      tip.style.color      = '';
      tip.style.whiteSpace = 'normal';
      return true;
    });

    return { setData, setFilter, toggle, render, openHelp };
  })();
