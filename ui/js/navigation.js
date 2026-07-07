  // Core role: Cross-tab navigation with back-button history (pilot/ship/station links).

  // Navigation stack records where each jump came from (tab + sub-tab + scroll).
  const _navStack = [];
  let   _navGuard = false; // true while a jump/goBack drives switchTab, so the
                           // clear-on-manual-nav rule doesn't wipe the trail.

  function _navSnapshot() {
    const panel   = document.querySelector('.tab-panel.active');
    const content = document.getElementById('content');
    return {
      tab:          panel ? panel.id.replace(/^tab-/, '') : 'overview',
      scrollTop:    content ? content.scrollTop : 0,
      fleetFaction: document.querySelector('#fleet-subtabs .fleet-subtab.active')?.dataset.faction || null,
      crewRole:     document.querySelector('#crew-subtabs .fleet-subtab.active')?.dataset.role || null,
      diploFaction: diploSelection,
      helpTopic:    window.Help ? Help.currentTopic() : null,
    };
  }
  function _navRecord() {            // start of a jump: remember where we are now
    _navStack.push(_navSnapshot());
    if (_navStack.length > 25) _navStack.shift();
    _navGuard = true;
  }
  function _navAfterJump() {         // right after the jump's switchTab call
    _navGuard = false;
    _updateBackBtn();
  }
  function _updateBackBtn() {
    const btn = document.getElementById('nav-back-btn');
    if (btn) btn.style.display = _navStack.length ? '' : 'none';
  }
  function goBack() {
    const s = _navStack.pop();
    if (!s) return;
    _navGuard = true;
    // Match either a flat nav-tab or a dropdown child (Universe → Map/Sectors),
    // then resolve to the .nav-tab that should carry the active highlight.
    const navHit = document.querySelector(`.nav-tab[onclick*="'${s.tab}'"], .nav-dd-item[onclick*="'${s.tab}'"]`);
    const navTab = navHit ? navHit.closest('.nav-tab') : null;
    switchTab(s.tab, navTab);
    // Restore the sub-view too so you land exactly where you left.
    if (s.tab === 'fleet' && s.fleetFaction) switchFleetTab(s.fleetFaction);
    if (s.tab === 'crew'  && s.crewRole)     switchCrewRole(s.crewRole);
    if (s.tab === 'diplomacy' && s.diploFaction) switchDiploTab(s.diploFaction);
    if (s.tab === 'help') Help.open(s.helpTopic);
    // Its table is virtualized off the panel's real (post-switch) height, so
    // a plain switchTab() here would leave it blank the same way a first-ever
    // visit would — see renderNpcStationsVisibleRows() in npc-stations.js.
    if (s.tab === 'stations-npc') renderNpcStationsVisibleRows();
    _navGuard = false;
    const content = document.getElementById('content');
    // Scroll restores after the panel is laid out (it was display:none).
    requestAnimationFrame(() => { if (content) content.scrollTop = s.scrollTop; });
    _updateBackBtn();
  }

  function switchTab(name, clickedEl) {
    // A manual tab switch (not driven by a jump or goBack) ends the back trail.
    if (!_navGuard) { _navStack.length = 0; _updateBackBtn(); }
    document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
    document.querySelectorAll(".nav-tab").forEach(t => t.classList.remove("active"));
    document.getElementById("tab-" + name).classList.add("active");
    if (clickedEl) clickedEl.classList.add("active");
  }

