  // Core role: Captains Log — renders the player event feed (export `events` +
  // `player_stats`) into the Events tab, with category filter chips.
  //
  // First file written under UI_STANDARDS §11: one namespace global, internals
  // private to the IIFE. populate() hands data in via setData(); the sidebar's
  // Events item calls render() when the tab opens. Layout classes live in
  // css/events.css; each row also stamps a data-event-tip with its full
  // pre-rendered tooltip (UI_STANDARDS §8).
  window.EventsFeed = (function () {

    // Display order = triage order: what needs action first.
    const CATEGORY_META = {
      alerts:        { label: 'Alerts',    icon: 'ti-alert-triangle', colour: 'var(--color-negative)' },
      upkeep:        { label: 'Upkeep',    icon: 'ti-tool',           colour: 'var(--color-primary)'  },
      missions:      { label: 'Missions',  icon: 'ti-flag',           colour: 'var(--color-special)'  },
      diplomacy:     { label: 'Diplomacy', icon: 'ti-world',          colour: 'var(--color-positive)' },
      news:          { label: 'News',      icon: 'ti-news',           colour: 'var(--text-secondary)' },
      tips:          { label: 'Tips',      icon: 'ti-bulb',           colour: 'var(--color-warning)'  },
      uncategorised: { label: 'Other',     icon: 'ti-notes',          colour: 'var(--text-secondary)' },
    };

    // Career-stat ids worth surfacing, with friendly labels. Whitelisted so a
    // save quirk dumping unexpected <stat> ids can't clutter the strip.
    const STAT_LABELS = [
      ['trade_rank',      'Trade Rank'],
      ['trade_score',     'Trade Score'],
      ['fight_rank',      'Fight Rank'],
      ['fight_score',     'Fight Score'],
      ['think_rank',      'Think Rank'],
      ['think_score',     'Think Score'],
      ['ships_destroyed', 'Ships Destroyed'],
    ];

    let _events = {};   // {category: [rows]} straight from the export
    let _stats  = {};   // {stat_id: value}
    let _filter = 'all';

    function setData(events, stats) {
      _events = events || {};
      _stats  = stats  || {};
    }

    function setFilter(cat) { _filter = cat; render(); }

    // Same tiering as economy-logs' _tradeLogAgo, plus a days tier — event
    // history reaches far further back than the trade log window.
    function _ago(s) {
      s = Math.floor(s);
      if (s < 60)    return s + 's';
      if (s < 3600)  return Math.floor(s / 60) + 'm';
      if (s < 86400) return Math.floor(s / 3600) + 'h ' + String(Math.floor((s % 3600) / 60)).padStart(2, '0') + 'm';
      return Math.floor(s / 86400) + 'd ' + Math.floor((s % 86400) / 3600) + 'h';
    }

    function _rows() {
      if (_filter !== 'all')
        return (_events[_filter] || []).map(e => ({ ...e, category: _filter }));
      const all = [];
      for (const cat of Object.keys(_events))
        for (const e of _events[cat]) all.push({ ...e, category: cat });
      all.sort((a, b) => a.time_ago_s - b.time_ago_s);   // smallest ago = newest first
      return all;
    }

    function _statsStripHtml() {
      const cells = STAT_LABELS
        .filter(([id]) => _stats[id] != null)
        .map(([id, label]) => `
          <div class="events-stat">
            <span class="events-stat-label">${label}</span>
            <span class="events-stat-value">${_stats[id].toLocaleString()}</span>
          </div>`).join('');
      if (!cells) return '';
      return `<div class="events-stats">${cells}</div>`;
    }

    // Full tooltip for one row: category header, then the complete event text
    // with its real line breaks — the feed row itself clamps to one line.
    // Same layout idiom as the trends/cashflow tips: bordered header, then body.
    function _tipHtml(e, m) {
      const head = `<div style="display:flex;justify-content:space-between;align-items:baseline;gap:1.6rem;margin-bottom:0.4rem;padding-bottom:0.4rem;border-bottom:1px solid var(--outline)">
          <span style="color:${m.colour};font-family:var(--font-label);font-size:1.1rem;letter-spacing:0.08em;text-transform:uppercase"><i class="ti ${m.icon}"></i> ${m.label}</span>
          <span style="color:var(--text-secondary);font-family:var(--font-data);font-size:1.05rem">${_ago(e.time_ago_s)} ago</span>
        </div>`;
      const title = e.title ? `<div style="color:var(--text-primary)">${e.title}</div>` : '';
      const text  = e.text && e.text !== e.title
        ? `<div style="color:var(--text-secondary);font-size:1.2rem;margin-top:0.2rem;white-space:pre-line">${e.text}</div>` : '';
      const faction = e.faction_name
        ? `<div style="margin-top:0.4rem;color:var(--text-brand);font-size:1.1rem">${e.faction_name}</div>` : '';
      // max-width so a long single line wraps instead of spanning the screen.
      return `<div style="max-width:42rem">${head}${title}${text}${faction}</div>`;
    }

    function render() {
      const root = document.getElementById('events-root');
      if (!root) return;

      const total = Object.values(_events).reduce((n, l) => n + l.length, 0);
      // .station-tab-btn is the shared rem-based tab chip — see events.css for
      // why it's this and not the chart cards' cqw-sized .cf-toggle-btn.
      const chip = (key, label, count) =>
        `<button class="station-tab-btn ${_filter === key ? 'active' : ''}" onclick="EventsFeed.setFilter('${key}')">${label}<span class="events-filter-count">${count.toLocaleString()}</span></button>`;
      const chips = [chip('all', 'All', total)]
        .concat(Object.keys(CATEGORY_META)
          .filter(c => (_events[c] || []).length)
          .map(c => chip(c, CATEGORY_META[c].label, _events[c].length)))
        .join('');

      const rows = _rows().map(e => {
        const m = CATEGORY_META[e.category] || CATEGORY_META.uncategorised;
        // The row shows one line ("·" between the event's lines); the hover
        // tip carries the full multi-line text.
        const oneLine = (e.text || '').split('\n').join(' · ');
        return `
          <div class="event-row" data-event-tip="${encodeURIComponent(_tipHtml(e, m))}">
            <i class="ti ${m.icon} event-icon" style="color:${m.colour}"></i>
            <div class="event-main">
              <div>${e.title || oneLine}</div>
              ${e.text && e.title && e.text !== e.title
                ? `<div class="event-text">${oneLine}</div>` : ''}
            </div>
            ${e.faction_name ? `<span class="event-faction">${e.faction_name}</span>` : ''}
            <span class="event-ago">${_ago(e.time_ago_s)}</span>
          </div>`;
      }).join('');

      root.innerHTML = `
        ${_statsStripHtml()}
        <div class="events-filter">${chips}</div>
        ${rows || `<div class="events-empty">No events in this scan${_filter !== 'all' ? ' for this category' : ''}.</div>`}`;
    }

    // ── Tooltip registration ──────────────────────────────────────────
    // Rows carry pre-rendered HTML, encoded at stamp time — the trendTip /
    // fleetTip pattern. Colour reset + normal wrapping because #hull-tip
    // defaults to nowrap alert-coloured single-line text.
    registerTip('eventTip', (el, _e, tip) => {
      tip.innerHTML = decodeURIComponent(el.dataset.eventTip);
      tip.style.color      = '';
      tip.style.whiteSpace = 'normal';
      return true;
    });

    return { setData, setFilter, render };
  })();
