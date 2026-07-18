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
    // trade_rank/trade_score/fight_rank/fight_score/ships_destroyed moved to
    // the Overview tab's Empire Snapshot cards — see populate.js.
    const STAT_LABELS = [
      ['think_rank',      'Think Rank'],
      ['think_score',     'Think Score'],
    ];

    let _events = {};   // {category: [rows]} straight from the export
    let _stats  = {};   // {stat_id: value}
    let _byId   = {};   // object_id → {label, row} for component= tooltip joins
    let _repByFaction = {};   // stripped faction name → reputation row
    let _knownSectors = new Set();          // discovered sector_name values
    let _assetsBySector = {};               // sector_name → {ships:[], stations:[]}
    let _filter = 'all';

    // reputation rows carry the tagged display name ("[TEL] Teladi Company");
    // event faction_name is the bare name resolved from the save's {page,id}
    // ref ("Teladi Company"). Strip the tag the same way trends.js's
    // _factionShort does, so an event's faction joins the reputation table.
    const _bareName = n => (n || '').replace(/^\[[^\]]+\]\s*/, '');

    function setData(events, stats, entities) {
      _events = events || {};
      _stats  = stats  || {};
      // Index every scanned entity by object_id so an event's component= link
      // resolves to the thing it points at. NPC ships go in first: if an id
      // ever appeared twice, the player-asset row is the one worth showing.
      const ent = entities || {};
      _byId = {};
      for (const s of ent.npcShips || []) _byId[s.object_id] = { label: 'NPC Ship',     row: s };
      for (const s of ent.ships    || []) _byId[s.object_id] = { label: 'Your Ship',    row: s };
      for (const s of ent.stations || []) _byId[s.object_id] = { label: 'Your Station', row: s };

      _repByFaction = {};
      for (const r of ent.rep || []) _repByFaction[_bareName(r.faction_name)] = r;

      _knownSectors = new Set((ent.sectors || []).map(s => s.sector_name).filter(Boolean));
      _assetsBySector = {};
      const bucket = name => _assetsBySector[name] || (_assetsBySector[name] = { ships: [], stations: [] });
      for (const s of ent.ships    || []) if (s.sector) bucket(s.sector).ships.push(s);
      for (const s of ent.stations || []) if (s.sector) bucket(s.sector).stations.push(s);
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

    // Absolute in-game clock (elapsed since save start), as "Day N · HH:MM".
    // The row/chip only ever show the "ago" tier, which is coarse and
    // relative to THIS scan — two events both reading "4h" could be minutes
    // or hours apart. game_time_s is a fixed reference every event shares, so
    // this is what actually lets you place two events on the same timeline.
    function _absTime(gameTimeS) {
      if (gameTimeS == null) return '';
      const day = Math.floor(gameTimeS / 86400) + 1;
      const rem = gameTimeS % 86400;
      const hh  = String(Math.floor(rem / 3600)).padStart(2, '0');
      const mm  = String(Math.floor((rem % 3600) / 60)).padStart(2, '0');
      return `Day ${day} · ${hh}:${mm}`;
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

    // Pulls a sector name out of event prose, when the game put one there.
    //
    // Reliable path: many alert-shaped events (SCA sightings, ship-under-attack,
    // ship-destroyed) carry a dedicated "Location: <sector>" line — trusted as
    // written since it's a clearly delimited field, no validation needed.
    //
    // Fallback path: 'news' war-update rows have no Location: line — the sector
    // is embedded in free prose ("Argon Federation mounting defence in True
    // Sight"). Restricted to category 'news' AND required to exactly match a
    // sector_name from the export's full discovered-galaxy list before it's
    // trusted — this is the fragile half of the extraction (a trailing "in
    // <words>" could just as easily be part of the sentence), so anything
    // that doesn't resolve to a real sector is dropped rather than guessed at.
    function _extractSector(e) {
      const text = e.text || '';
      const loc = text.match(/^Location: (.+)$/m);
      if (loc) return loc[1].trim();
      if (e.category === 'news') {
        const tail = text.match(/ in ([^.]+)$/);
        if (tail && _knownSectors.has(tail[1].trim())) return tail[1].trim();
      }
      return null;
    }

    // What of the player's is actually in that sector — the triage payoff:
    // "pirate sighted in Black Hole Sun IV" only matters if you have ships or
    // stations there. Renders even at zero, so a hover can also tell you
    // there's nothing to worry about.
    function _sectorTipSection(sectorName) {
      if (!sectorName) return '';
      const a = _assetsBySector[sectorName] || { ships: [], stations: [] };
      const parts = [
        a.ships.length    ? `${a.ships.length} ship${a.ships.length       !== 1 ? 's' : ''}`    : null,
        a.stations.length ? `${a.stations.length} station${a.stations.length !== 1 ? 's' : ''}` : null,
      ].filter(Boolean);
      const line = parts.length
        ? `<span style="color:var(--color-warning)">${parts.join(', ')} of yours here</span>`
        : `<span style="color:var(--text-secondary)">No assets of yours in this sector</span>`;
      return `<div style="margin-top:0.6rem;padding-top:0.4rem;border-top:1px solid var(--outline)">
          <div style="font-size:0.85rem;letter-spacing:0.12em;text-transform:uppercase;color:var(--text-brand);margin-bottom:0.2rem"><i class="ti ti-map-pin"></i> ${sectorName}</div>
          <div style="font-size:1.1rem">${line}</div>
        </div>`;
    }

    // What the event's component= link resolves to. The log line only says
    // something happened to an object — this answers "which one, and how does
    // it look now?" (current hull/shield from THIS scan, not event time).
    // Unresolvable ids (destroyed/despawned/unscanned) just render nothing.
    function _entityTipSection(id) {
      const hit = id ? _byId[id] : null;
      if (!hit) return '';
      const r = hit.row;
      const name = r.display_name || r.name || r.type_name || r.code || '?';
      const sub  = [
        r.code !== name ? r.code : null,
        r.owner_name || null,
        r.role || null,
        r.sector ? `<i class="ti ti-map-pin"></i> ${r.sector}` : null,
      ].filter(Boolean).join(' · ');
      // hullBar/shieldBar are the shared formatters the fleet table uses —
      // same thresholds and look. Their % normally shows via their own hover
      // tip, which can't fire inside this popover, so label each bar in text.
      // NPC rows carry no hull fields, so no bars.
      const barRow = (lbl, barHtml, pct) => `
        <div style="display:flex;align-items:center;gap:0.6rem">
          <span style="font-family:var(--font-label);font-size:0.85rem;letter-spacing:0.08em;text-transform:uppercase;color:var(--text-secondary);width:4.2rem">${lbl}</span>
          ${barHtml}
          <span style="font-family:var(--font-data);font-size:1rem;color:var(--text-secondary)">${pct != null ? Math.round(pct) + '%' : '—'}</span>
        </div>`;
      const bars = (r.hull_pct != null || r.shield_pct != null)
        ? `<div style="display:flex;flex-direction:column;gap:0.3rem;margin-top:0.4rem">
             ${barRow('Hull',   hullBar(r.hull_pct, r.hull_hp, r.hull_max),         r.hull_pct)}
             ${barRow('Shield', shieldBar(r.shield_pct, r.shield_hp, r.shield_max), r.shield_pct)}
           </div>` : '';
      return `<div style="margin-top:0.6rem;padding-top:0.4rem;border-top:1px solid var(--outline)">
          <div style="font-size:0.85rem;letter-spacing:0.12em;text-transform:uppercase;color:var(--text-brand);margin-bottom:0.3rem">${hit.label}</div>
          <div style="color:var(--text-primary)">${name}</div>
          ${sub ? `<div style="color:var(--text-secondary);font-size:1.1rem;margin-top:0.15rem">${sub}</div>` : ''}
          ${bars}
        </div>`;
    }

    // Faction line, upgraded with the faction's CURRENT standing (tier badge +
    // score + rep bar) when the export's reputation table has it — the event
    // text only ever shows the score AT EVENT TIME, so this is genuinely new:
    // "current reputation: 21" (then) next to "Friendly +24.3" (now). Falls
    // back to a plain name for factions the export has no rep row for (minor/
    // unranked factions).
    function _factionLine(factionName) {
      if (!factionName) return '';
      const r = _repByFaction[_bareName(factionName)];
      if (!r) return `<div style="margin-top:0.4rem;color:var(--text-brand);font-size:1.1rem">${factionName}</div>`;
      return `<div style="margin-top:0.4rem">
          <div style="display:flex;align-items:center;gap:0.6rem">
            <span style="color:var(--text-brand);font-size:1.1rem">${factionName}</span>
            ${tierBadge(r.tier)}
            <span class="mono" style="color:var(--text-secondary);font-size:1.05rem">${sign(r.value)} now</span>
          </div>
          <div style="margin-top:0.25rem">${repBar(r.value)}</div>
        </div>`;
    }

    // Full tooltip for one row: category header, then the complete event text
    // with its real line breaks — the feed row itself clamps to one line.
    // Same layout idiom as the trends/cashflow tips: bordered header, then body.
    function _tipHtml(e, m) {
      const head = `<div style="display:flex;justify-content:space-between;align-items:baseline;gap:1.6rem;margin-bottom:0.4rem;padding-bottom:0.4rem;border-bottom:1px solid var(--outline)">
          <span style="color:${m.colour};font-family:var(--font-label);font-size:1.1rem;letter-spacing:0.08em;text-transform:uppercase"><i class="ti ${m.icon}"></i> ${m.label}</span>
          <span style="text-align:right">
            <span style="display:block;color:var(--text-secondary);font-family:var(--font-data);font-size:1.05rem">${_ago(e.time_ago_s)} ago</span>
            <span style="display:block;color:var(--text-brand);font-family:var(--font-data);font-size:0.95rem">${_absTime(e.game_time_s)}</span>
          </span>
        </div>`;
      const title = e.title ? `<div style="color:var(--text-primary)">${e.title}</div>` : '';
      const text  = e.text && e.text !== e.title
        ? `<div style="color:var(--text-secondary);font-size:1.2rem;margin-top:0.2rem;white-space:pre-line">${e.text}</div>` : '';
      // max-width so a long single line wraps instead of spanning the screen.
      return `<div style="max-width:42rem">${head}${title}${text}${_factionLine(e.faction_name)}${_sectorTipSection(_extractSector(e))}${_entityTipSection(e.component_id)}</div>`;
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
