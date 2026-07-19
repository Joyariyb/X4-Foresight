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

    // View routing, finding-type presentation, and evidence-key labels live
    // in advisors-meta.js (window.AdvisorsMeta) — pure lookup tables shared
    // with advisors-evidence.js, kept out of this file's render logic.
    const { VIEWS, TYPE_META, FALLBACK_META, DOMAIN_LABELS } = window.AdvisorsMeta;

    let _findings = [];
    let _view     = 'economic';
    let _filter   = 'all';
    let _open     = new Set();   // finding ids with an expanded evidence drawer

    function setData(advisors) {
      _findings = (advisors && advisors.findings) || [];
      _filter   = 'all';
      _open     = new Set();     // stale drawers from the previous scan close
      AdvisorsEvidence.resetView();
    }

    function setFilter(type) { _filter = type; render(); }

    function toggle(id) {
      _open.has(id) ? _open.delete(id) : _open.add(id);
      render();
    }

    // Delegates to advisors-evidence.js's own drawer-view state (its private
    // Details/Buyers map) — kept as a method on this namespace so the
    // evidence drawer's onclick string doesn't need to know that split.
    function setEvidenceView(id, view) {
      AdvisorsEvidence.setView(id, view);
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
      miner:    'help-advisors-miner',
    };
    function openHelp() {
      _navRecord();
      Help.open(HELP_TOPIC[_view] || 'help-advisors-economic');
      _navAfterJump();
    }

    // Which sidebar item switchTab() flashes active for each view — mirrors
    // the onclick on each sb-* item in body.html (sb-military/-traders/
    // -economic), since jumpToFinding() below is a second entry point into
    // the same tab switch.
    const VIEW_NAV = { economic: 'sb-economic', military: 'sb-military', trader: 'sb-traders', miner: 'sb-miners' };

    // Jump straight to one advisor card from elsewhere in the UI (currently:
    // the Alerts tab's "Advise" button on its Hostile Presence/Force Build-Up
    // tiles) — switches to that finding's view, expands its evidence drawer,
    // and scrolls/flashes it into view. Same scroll+flash affordance as
    // jumpToShip() (station-helpers.js).
    function jumpToFinding(id, view) {
      _navRecord();
      switchTab(`advisors-${view}`, document.getElementById(VIEW_NAV[view]));
      _navAfterJump();
      _view = view;
      _filter = 'all';
      _open = new Set([id]);
      AdvisorsEvidence.resetView();
      render();
      requestAnimationFrame(() => {
        const card = document.querySelector(`.adv-card[data-finding-id="${id}"]`);
        if (!card) return;
        card.scrollIntoView({ block: 'center', behavior: 'smooth' });
        card.style.transition = '';
        card.style.background = 'var(--color-negative-dim)';
        requestAnimationFrame(() => {
          card.style.transition = 'background 1.5s';
          card.style.background = '';
        });
      });
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
      // and idle credits banked.
      const sitingCount = vf.filter(f => f.type === 'station_siting').length;
      const arbGain     = sum(['galaxy_arbitrage'], 'gain');
      const strandedCnt = vf.filter(f => f.type === 'stranded_delivery').length;
      const idleCredits = sum(['idle_trade_capital'], 'credits');
      // Miner-only cell: how many stations are starving for a mineable input.
      const starving    = vf.filter(f => f.type === 'mining_supply_gap').length;
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
        starving ? ['Stations Starving', starving.toLocaleString()] : null,
      ].filter(Boolean);
      return `<div class="adv-stats">${cells.map(([label, value]) => `
          <div class="adv-stat">
            <span class="adv-stat-label">${label}</span>
            <span class="adv-stat-value">${value}</span>
          </div>`).join('')}</div>`;
    }

    // ── Cards ─────────────────────────────────────────────────────────
    // Evidence grid, pricing gauge, and the siting Details/Buyers panel live
    // in advisors-evidence.js (window.AdvisorsEvidence) — its own private
    // state (which siting card is on which tab) and lookup tables.

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

    // Exported so other tabs (currently: the Alerts tab's Hostile Presence
    // tiles) can stamp the exact same icon/colour/tooltip instead of a
    // second hand-rolled copy — '' when the finding has no counters (e.g.
    // every buildup finding, which never sets f.counters).
    function counterIconHtml(f) {
      return f.counters && f.counters.length
        ? `<i class="ti ti-swords adv-counter" data-adv-counter-tip="${encodeURIComponent(_counterTipHtml(f))}"></i>`
        : '';
    }

    function _cardHtml(f, rank, maxScore) {
      const m = _meta(f);
      // Rail fill is score relative to the view's TOP finding (not the
      // type-filtered subset), so a card's rail doesn't change when the
      // filter does. Floored at 6% so even the weakest finding shows a tick.
      const pct  = Math.max(6, Math.round(f.priority_score / maxScore * 100));
      const open = _open.has(f.id);
      const counters = counterIconHtml(f);
      return `
        <div class="adv-card adv--${m.tone}${open ? ' open' : ''}" data-finding-id="${f.id}">
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
            ${AdvisorsEvidence.render(f)}
          </div>
        </div>`;
    }

    function render(view) {
      // A view change resets the type filter and open drawers — the chips on
      // the other tab reference types this view's list doesn't contain, so a
      // carried-over filter would show a confusingly empty list.
      if (view && view !== _view) { _view = view; _filter = 'all'; _open = new Set(); AdvisorsEvidence.resetView(); }
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

    return { setData, setFilter, toggle, setEvidenceView, render, openHelp, jumpToFinding, counterIconHtml };
  })();
