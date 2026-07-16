  // Core role: Captains Log — renders station bulletin-board missions (export
  // `station_missions`, grouped by station) into the Missions tab.
  //
  // Same shape as events-feed.js: one namespace global, setData() hands data
  // in, the sidebar's Missions item calls render() when the tab opens. Layout
  // classes live in css/missions.css; each mission row stamps a
  // data-mission-tip with its full pre-rendered tooltip (UI_STANDARDS §8).
  window.MissionsFeed = (function () {

    // Icon + label per offer type= value seen in the savegame. 'other' is the
    // fallback for any type this table doesn't know about yet.
    const TYPE_META = {
      find:         { label: 'Find',         icon: 'ti-search' },
      repair:       { label: 'Repair',       icon: 'ti-tool' },
      transport:    { label: 'Transport',    icon: 'ti-truck' },
      deliver:      { label: 'Deliver',      icon: 'ti-package' },
      trade:        { label: 'Trade',        icon: 'ti-currency-dollar' },
      escort:       { label: 'Escort',       icon: 'ti-shield' },
      rescue:       { label: 'Rescue',       icon: 'ti-life-buoy' },
      destroy:      { label: 'Destroy',      icon: 'ti-bomb' },
      fight:        { label: 'Fight',        icon: 'ti-sword' },
      protect:      { label: 'Protect',      icon: 'ti-shield-check' },
      intelligence: { label: 'Intelligence', icon: 'ti-eye' },
      drop:         { label: 'Drop',         icon: 'ti-map-pin' },
      build:        { label: 'Build',        icon: 'ti-hammer' },
      board:        { label: 'Board',        icon: 'ti-anchor' },
      scan:         { label: 'Scan',         icon: 'ti-radar-2' },
      other:        { label: 'Mission',      icon: 'ti-flag' },
    };

    // Difficulty badge colour — green (easy) through red (hard), same trio
    // idiom as the rest of the UI (base.css --color-positive/warning/negative).
    const LEVEL_META = {
      veryeasy: { label: 'Very Easy', colour: 'var(--color-positive)' },
      easy:     { label: 'Easy',      colour: 'var(--color-positive)' },
      medium:   { label: 'Medium',    colour: 'var(--color-warning)' },
      hard:     { label: 'Hard',      colour: 'var(--color-negative)' },
      veryhard: { label: 'Very Hard', colour: 'var(--color-negative)' },
    };

    let _byStation = {};   // export's station_missions shape, straight from setData
    let _filter    = 'all';

    function setData(stationMissions) {
      _byStation = stationMissions || {};
    }

    function setFilter(type) { _filter = type; render(); }

    function _typeMeta(t) { return TYPE_META[t] || TYPE_META.other; }
    function _levelBadge(level) {
      const m = LEVEL_META[level];
      if (!m) return '';
      return `<span class="mission-level" style="color:${m.colour};border-color:${m.colour}">${m.label}</span>`;
    }

    function _reward(m) {
      const parts = [];
      if (m.reward_cr) parts.push(fmtCredits(m.reward_cr));
      if (m.reward_text) parts.push(m.reward_text.split('\n')[0]);
      return parts.join(' · ') || '—';
    }

    function _tipHtml(station, m) {
      const meta = _typeMeta(m.mission_type);
      const head = `<div style="display:flex;justify-content:space-between;align-items:baseline;gap:1.6rem;margin-bottom:0.4rem;padding-bottom:0.4rem;border-bottom:1px solid var(--outline)">
          <span style="color:var(--text-brand);font-family:var(--font-label);font-size:1.1rem;letter-spacing:0.08em;text-transform:uppercase"><i class="ti ${meta.icon}"></i> ${meta.label}</span>
          ${_levelBadge(m.level)}
        </div>`;
      const desc = m.description
        ? `<div style="color:var(--text-secondary);font-size:1.2rem;white-space:pre-line">${m.description}</div>` : '';
      const objectives = (m.objectives || []).length
        ? `<div style="margin-top:0.6rem;padding-top:0.4rem;border-top:1px solid var(--outline)">
             <div style="font-size:0.85rem;letter-spacing:0.12em;text-transform:uppercase;color:var(--text-brand);margin-bottom:0.3rem">Objectives</div>
             ${m.objectives.map(o => `<div style="color:var(--text-primary);font-size:1.15rem">${o.step}. ${o.text}</div>`).join('')}
           </div>` : '';
      const reward = `<div style="margin-top:0.6rem;color:var(--color-warning);font-family:var(--font-data)">${_reward(m)}</div>`;
      const dist = (m.distance_m != null)
        ? `<div style="color:var(--text-secondary);font-size:1.1rem">${Math.round(m.distance_m).toLocaleString()} m away</div>` : '';
      return `<div style="max-width:42rem">${head}${desc}${objectives}${reward}${dist}</div>`;
    }

    function _missionRowHtml(station, m) {
      const meta = _typeMeta(m.mission_type);
      const oneLine = (m.description || '').split('\n')[0];
      return `
        <div class="mission-row" data-mission-tip="${encodeURIComponent(_tipHtml(station, m))}">
          <i class="ti ${meta.icon} mission-icon"></i>
          <div class="mission-main">
            <div>${m.name}</div>
            <div class="mission-text">${oneLine}</div>
          </div>
          ${_levelBadge(m.level)}
          <span class="mission-reward">${_reward(m)}</span>
        </div>`;
    }

    function _stationCardHtml(station) {
      const missions = station.missions.filter(
        m => _filter === 'all' || m.mission_type === _filter);
      if (!missions.length) return '';
      return `
        <div class="mission-station-card">
          <div class="mission-station-header">
            <span class="mission-station-name">${station.station_name}</span>
            <span class="mission-station-sector"><i class="ti ti-map-pin"></i> ${station.sector_name || '—'}</span>
            <span class="mission-station-count">${missions.length.toLocaleString()}</span>
          </div>
          ${missions.map(m => _missionRowHtml(station, m)).join('')}
        </div>`;
    }

    function render() {
      const root = document.getElementById('missions-root');
      if (!root) return;

      const stations = Object.values(_byStation);
      const total = stations.reduce((n, s) => n + s.missions.length, 0);

      const typesPresent = new Set();
      stations.forEach(s => s.missions.forEach(m => typesPresent.add(m.mission_type)));
      const chip = (key, label, count) =>
        `<button class="station-tab-btn ${_filter === key ? 'active' : ''}" onclick="MissionsFeed.setFilter('${key}')">${label}<span class="events-filter-count">${count.toLocaleString()}</span></button>`;
      const chips = [chip('all', 'All', total)]
        .concat([...typesPresent].sort().map(t => {
          const n = stations.reduce((sum, s) => sum + s.missions.filter(m => m.mission_type === t).length, 0);
          return chip(t, _typeMeta(t).label, n);
        }))
        .join('');

      const cards = stations
        .sort((a, b) => (a.station_name || '').localeCompare(b.station_name || ''))
        .map(_stationCardHtml)
        .join('');

      root.innerHTML = `
        <div class="events-filter">${chips}</div>
        ${cards || `<div class="events-empty">No station missions in this scan${_filter !== 'all' ? ' for this type' : ''}.</div>`}`;
    }

    // ── Tooltip registration ──────────────────────────────────────────
    registerTip('missionTip', (el, _e, tip) => {
      tip.innerHTML = decodeURIComponent(el.dataset.missionTip);
      tip.style.color      = '';
      tip.style.whiteSpace = 'normal';
      return true;
    });

    return { setData, setFilter, render };
  })();
