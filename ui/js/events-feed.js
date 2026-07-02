  // Core role: Captains Log — renders the player event feed (export `events` +
  // `player_stats`) into the Events tab, with category filter chips.
  //
  // First file written under UI_STANDARDS §11: one namespace global, internals
  // private to the IIFE. populate() hands data in via setData(); the sidebar's
  // Events item calls render() when the tab opens.
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
          <div style="display:flex;flex-direction:column;gap:0.2rem">
            <span style="font-family:var(--font-label);color:var(--text-label);text-transform:uppercase;letter-spacing:0.08em;font-size:1.1rem">${label}</span>
            <span class="mono" style="font-size:1.6rem">${_stats[id].toLocaleString()}</span>
          </div>`).join('');
      if (!cells) return '';
      return `<div style="display:flex;gap:2.4rem;flex-wrap:wrap;padding:1rem 1.2rem;border:1px solid var(--outline);border-radius:var(--radius-md);background:var(--surface-1);margin-bottom:1.2rem">${cells}</div>`;
    }

    function render() {
      const root = document.getElementById('events-root');
      if (!root) return;

      const total = Object.values(_events).reduce((n, l) => n + l.length, 0);
      const chip = (key, label, count) =>
        `<button class="cf-toggle-btn ${_filter === key ? 'active' : ''}" onclick="EventsFeed.setFilter('${key}')">${label} <span class="mono">${count.toLocaleString()}</span></button>`;
      const chips = [chip('all', 'All', total)]
        .concat(Object.keys(CATEGORY_META)
          .filter(c => (_events[c] || []).length)
          .map(c => chip(c, CATEGORY_META[c].label, _events[c].length)))
        .join('');

      const rows = _rows().map(e => {
        const m = CATEGORY_META[e.category] || CATEGORY_META.uncategorised;
        return `
          <div style="display:flex;gap:1rem;align-items:center;padding:0.55rem 1rem;border-bottom:1px solid var(--outline)">
            <i class="ti ${m.icon}" style="color:${m.colour};font-size:1.5rem;flex:none"></i>
            <div style="flex:1;min-width:0">
              <div>${e.title || e.text}</div>
              ${e.text && e.title && e.text !== e.title
                ? `<div style="color:var(--text-secondary);font-size:1.2rem;margin-top:0.1rem">${e.text}</div>` : ''}
            </div>
            ${e.faction_name ? `<span style="color:var(--text-brand);flex:none;font-size:1.2rem">${e.faction_name}</span>` : ''}
            <span class="mono" style="color:var(--text-secondary);flex:none;min-width:6rem;text-align:right">${_ago(e.time_ago_s)}</span>
          </div>`;
      }).join('');

      root.innerHTML = `
        ${_statsStripHtml()}
        <div style="display:flex;gap:0.6rem;flex-wrap:wrap;margin-bottom:1rem">${chips}</div>
        ${rows || `<div style="color:var(--text-secondary);padding:2rem 1rem">No events in this scan${_filter !== 'all' ? ' for this category' : ''}.</div>`}`;
    }

    return { setData, setFilter, render };
  })();
