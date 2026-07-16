  // Core role: Station tab switcher, trader highlight, and budget stat display.

  // Which sub-view (breakdown/logs) each station's Economy slider panel shows.
  // Read by populate.js when it renders slider panel 1; defaults to breakdown.
  const economyViewByStation = {};

  // Opens/closes one station-card segment picker (Economy's Breakdown/Logs or
  // More's Production menu — both reuse the .econ-dd-menu shell). Takes the
  // menu element's id so one function serves every segment's dropdown.
  // Click-driven (not hover, unlike the topbar nav dropdown) so it doesn't
  // fire while the user is just passing the cursor over the tri-track.
  let openStationDropdown = null;

  function toggleStationDropdown(e, menuId) {
    e.stopPropagation();
    const menu = document.getElementById(menuId);
    if (!menu) return;
    const wasOpen = menu.classList.contains('open');
    closeAllStationDropdowns();
    if (!wasOpen) {
      menu.classList.add('open');
      openStationDropdown = menuId;
    }
  }

  function closeAllStationDropdowns() {
    document.querySelectorAll('.econ-dd-menu.open').forEach(m => m.classList.remove('open'));
    openStationDropdown = null;
  }

  // Swaps the visible sub-panel within an already-rendered Economy slider
  // panel (breakdown vs. logs) without touching the rest of the card's DOM.
  // Toggles the 'active' class (opacity swap in charts.css), not display:none —
  // display:none would tear down the Breakdown pie/chart's filter:drop-shadow
  // layers, and QtWebEngine repainting those from scratch on every switch is
  // what caused the visible lag (see the .econview-panel comment in charts.css).
  function setEconomyView(code, view) {
    economyViewByStation[code] = view;
    const card = document.getElementById('station-' + code);
    if (!card) return;
    card.querySelectorAll('.econview-panel').forEach(p => {
      p.classList.toggle('active', p.dataset.econview === view);
    });
  }

  // Picking Breakdown or Logs from the dropdown: swap the sub-panel, jump the
  // slider to the Economy panel, and close the picker.
  function selectEconomyView(code, view) {
    setEconomyView(code, view);
    setStationSlider(code, 1);
    closeAllStationDropdowns();
  }

  // Picking an option from the More dropdown: jump the slider to the More
  // panel and close the picker. `view` is unused while Production is the only
  // option — it exists so future options (mirroring setEconomyView) can swap
  // sub-panels without changing the populate.js call sites.
  function selectMoreView(code, view) {
    setStationSlider(code, 2);
    closeAllStationDropdowns();
  }

  document.addEventListener('click', (e) => {
    if (openStationDropdown && !e.target.closest('.econ-dd-wrap')) closeAllStationDropdowns();
  });

  // Switches the visible tab panel within a single station card.
  function switchStationTab(code, tab) {
    const card = document.getElementById('station-' + code);
    if (!card) return;
    card.querySelectorAll('.station-tab-btn').forEach(b => b.classList.remove('active'));
    card.querySelectorAll('.station-tab-panel').forEach(p => p.style.display = 'none');
    const btn = card.querySelector(`.station-tab-btn[data-tab="${tab}"]`);
    const pnl = card.querySelector(`.station-tab-panel[data-tab="${tab}"]`);
    if (btn) btn.classList.add('active');
    if (pnl) pnl.style.display = 'block';
  }

  // Switches to the Stations tab and scrolls to the card for `code`.
  // Called from .stn-link clicks in the fleet table so the user can jump
  // straight from a ship row to its home station.
  function goToStation(code) {
    _navRecord();
    switchTab('stations', document.getElementById('nav-stations'));
    _navAfterJump();
    const card = document.getElementById('station-' + code);
    if (card) card.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }

  // Jump from the universe Map to a sector's card on the Sectors tab. Records the
  // back trail (like goToStation) so the Back button returns to the map. Guarded
  // to discovered sectors only — you can't inspect fog-of-war space.
  function goToSector(macro) {
    const sec = _sectorInfoMap[macro];
    if (!sec || !sec.is_discovered) return;
    _navRecord();
    switchTab('sectors', document.getElementById('nav-universe'));
    _navAfterJump();
    renderSectorsList();
    showSectorDetail(macro);
    const row = document.querySelector(`#sectors-list .sector-row[data-macro="${macro}"]`);
    if (row) row.scrollIntoView({ block: 'nearest' });
  }

  // Moves the three-position slider thumb to pos (0=Left, 1=Mid, 2=Right) for
  // the given station card. Thumb position is driven purely by a data-pos CSS
  // attribute on the track element — no inline style writes on the thumb needed.
  function setStationSlider(code, pos) {
    const track = document.getElementById('tri-' + code);
    if (!track) return;
    track.dataset.pos = pos;
    track.querySelectorAll('.tri-opt').forEach((o, i) => {
      o.classList.toggle('active', i === pos);
    });
    // Swap the whole card body to the panel matching the slider position
    // (0 = Overview, 1 = Economy, 2 = placeholder).
    const card = document.getElementById('station-' + code);
    if (!card) return;
    card.querySelectorAll('.station-slider-panel').forEach(p => {
      p.style.display = (p.dataset.slider === String(pos)) ? 'block' : 'none';
    });
  }

  // Derives a 3-letter faction tag from the station's module list.
  // Falls back to 'GEN' when no recognised faction is found.
  function stationFactionTag(s) {
    const ABBR = { Argon:'ARG', Teladi:'TEL', Paranid:'PAR', Split:'ZYA', Terran:'TER', Boron:'BOR' };
    if (s.modules && s.modules.length > 0) {
      for (const m of s.modules) {
        if (m.faction && ABBR[m.faction]) return ABBR[m.faction];
      }
      if (s.modules[0].faction) return s.modules[0].faction.slice(0, 3).toUpperCase();
    }
    return 'GEN';
  }

  // Derives a human-readable station type from the number of production wares.
  // Switches to the Fleet tab, activates the correct faction subtab, and scrolls
  // to the row matching the given ship code, briefly flashing it in the faction's
  // colour so the user can spot it instantly.
  // faction defaults to 'player'; pass a faction id (e.g. 'civilian') for NPC ships.
  function jumpToShip(code, faction) {
    _navRecord();
    faction = faction || 'player';
    // Naval is now a dropdown (Ships / Designs); the active highlight lives on
    // the parent label, so resolve it by id rather than by the child's onclick.
    const fleetNavTab = document.getElementById('nav-naval');
    switchTab('fleet', fleetNavTab);
    _navAfterJump();
    switchFleetTab(faction, document.querySelector(`.fleet-subtab[data-faction="${faction}"]`));

    // Player ships live in #fleet-table; NPC ships live in their own per-faction table.
    const tableSelector = faction === 'player' ? '#fleet-table' : `#npc-table-${faction}`;
    const row = document.querySelector(`${tableSelector} tr[data-code="${code}"]`);
    if (!row) return;
    row.scrollIntoView({ block: 'center', behavior: 'smooth' });
    // Flash using the faction's theme colour so the highlight feels appropriate.
    const flashColor = faction === 'player'
      ? 'var(--color-primary-dim)'
      : hexToRgba(FACTION_COLOURS[faction] || '#6e7681', 0.18);
    row.style.transition = '';
    row.style.background = flashColor;
    requestAnimationFrame(() => {
      row.style.transition = 'background 1.5s';
      row.style.background = '';
    });
  }

  // Jump from a player ship's name (Fleet tab) to its Designs-tab card — the
  // inverse of the ship-code chips designCardHtml() puts under "used by N
  // ships", which call jumpToShip() the other way. Clears the Designs filters
  // first so the target card can't be hidden by whatever was left set from a
  // previous visit, then expands it if the user had it collapsed.
  function jumpToDesign(code) {
    const ship = (allPlayerShips || []).find(s => s.code === code);
    if (!ship) return;
    const sig = designSignature(ship);
    _navRecord();
    switchTab('designs', document.getElementById('nav-naval'));
    _navAfterJump();
    designsSetSizeFilter('all');
    designsSetFactionFilter('all');

    const card = document.querySelector(`#designs-grid [data-sig="${sig}"]`);
    if (!card) return;
    if (!card.open) {
      card.open = true;
      designsCollapsed.delete(sig);
      designsUpdateToggleAllBtn();
    }
    card.scrollIntoView({ block: 'center', behavior: 'smooth' });
    card.style.transition = '';
    card.style.background = 'var(--color-primary-dim)';
    requestAnimationFrame(() => {
      card.style.transition = 'background 1.5s';
      card.style.background = '';
    });
  }

  // Jump from a ship's Hull Type cell (Fleet tab) to that hull's page in the
  // Resource Library's Hull Inspector — same cross-tab pattern as
  // jumpToDesign(), but landing on the catalogued hull stats rather than the
  // ship's fitted-loadout design card. Guarded on HULL_CATALOG actually
  // having the macro (a few rare hulls like escape pods aren't catalogued).
  function jumpToHull(macro) {
    if (!macro || !HULL_CATALOG[macro]) return;
    _navRecord();
    switchTab('reslib', document.getElementById('nav-naval'));
    _navAfterJump();
    switchResLibCat('hull');
    reslibShowHullInspector(macro);
  }

  // Jump from an NPC ship's name (Naval → Ships faction tabs) to the Hull
  // Inspector, carrying the ship itself so the inspector shows the equipment
  // actually fitted on that spawn (NPC loadouts are randomized per spawn, so
  // two ships of the same hull can differ). Same cross-tab pattern as
  // jumpToHull(), which lands on the bare hull instead.
  function jumpToNpcHull(code, factionId) {
    const ship = (npcShipsCache[factionId] || []).find(s => s.code === code);
    if (!ship || !HULL_CATALOG[ship.macro]) return;
    _navRecord();
    switchTab('reslib', document.getElementById('nav-naval'));
    _navAfterJump();
    switchResLibCat('hull');
    reslibShowHullInspector(ship.macro, ship);
  }

  function stationTypeLabel(s) {
    const wares = s.production ? s.production.split(',').filter(w => w.trim()) : [];
    if (wares.length === 0) return 'Defence Platform';
    if (wares.length >= 4)  return 'Manufacturing Hub';
    return 'Production Station';
  }

