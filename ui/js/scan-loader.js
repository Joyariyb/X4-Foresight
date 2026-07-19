  function loadFromJsonFile() {
    fetch('../x4_empire_state.json')
      .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(data => {
        // write_export() embeds the static catalogs in the file because this
        // path has no bridge to fetch them from; adopt them before populate()
        // so the Resource Library and universe overlay aren't left empty.
        EQUIPMENT_CATALOG = data.equipment_catalog || EQUIPMENT_CATALOG;
        HULL_CATALOG      = data.hull_catalog      || HULL_CATALOG;
        SECTOR_CATALOG    = data.sector_catalog    || SECTOR_CATALOG;
        SOFTWARE_CATALOG  = data.software_catalog  || SOFTWARE_CATALOG;
        ITEM_CATALOG      = data.item_catalog      || ITEM_CATALOG;
        populate(data);
      })
      .catch(e => {
        document.getElementById("loading").textContent =
          "No Qt bridge and could not load x4_empire_state.json: " + e;
        // No data will ever arrive on this path — show the static galaxy
        // skeleton so the Universe tab isn't just blank.
        renderUniverseMap({});
      });
  }

  // The live bridge, once the QWebChannel handshake completes. The scan picker
  // reaches back through it to re-query the DB for a different scan_id.
  let _bridge = null;
  // Tracks which scan is currently rendered so the picker highlights it and the
  // button label stays correct after populate() reads data.meta.scan_id.
  let _currentScanId = null;

  // Fetch one scan's export from the DB (via the bridge) and render it. -1 asks
  // the bridge for the latest scan. Re-running populate() swaps the whole view;
  // its render paths clear their containers first, so this is safe to call on
  // every picker change without a page reload.
  function loadScan(scanId) {
    if (!_bridge) return;
    _bridge.get_empire_data(scanId, function(jsonStr) {
      try {
        populate(JSON.parse(jsonStr));
        refreshScanStatusCard();
      } catch(e) {
        document.getElementById("loading").textContent = "Error parsing data: " + e;
      }
    });
  }

  // Shows a copyable error dialog - native alert() text isn't reliably
  // selectable across browsers/OSes, which leaves error reports stuck
  // unreadable. Always also logs to console.error so DevTools is a fallback.
  function showScanErrorDialog(message) {
    console.error("New Scan failed:", message);

    const overlay = document.createElement("div");
    overlay.style.cssText =
      "position:fixed;inset:0;background:rgba(0,0,0,0.6);z-index:9999;" +
      "display:flex;align-items:center;justify-content:center;font-family:sans-serif";

    const box = document.createElement("div");
    box.style.cssText =
      "background:#161b22;border:1px solid #30363d;border-radius:8px;" +
      "min-width:360px;max-width:520px;color:#e6edf3;padding:16px";

    const title = document.createElement("div");
    title.textContent = "New Scan failed";
    title.style.cssText = "font-size:15px;font-weight:600;margin-bottom:12px";
    box.appendChild(title);

    const textarea = document.createElement("textarea");
    textarea.value = message;
    textarea.readOnly = true;
    textarea.style.cssText =
      "width:100%;height:120px;resize:vertical;box-sizing:border-box;" +
      "background:#0d1117;border:1px solid #30363d;border-radius:6px;" +
      "color:#e6edf3;font-family:monospace;font-size:12px;padding:8px";
    box.appendChild(textarea);

    const btnRow = document.createElement("div");
    btnRow.style.cssText = "margin-top:12px;display:flex;gap:8px;justify-content:flex-end";
    const btnStyle =
      "padding:6px 14px;background:#21262d;border:1px solid #30363d;" +
      "border-radius:6px;color:#e6edf3;cursor:pointer";

    const copyBtn = document.createElement("button");
    copyBtn.textContent = "Copy";
    copyBtn.style.cssText = btnStyle;
    copyBtn.onclick = () => {
      textarea.select();
      (navigator.clipboard ? navigator.clipboard.writeText(message) : Promise.reject())
        .catch(() => document.execCommand("copy"));
      copyBtn.textContent = "Copied!";
      setTimeout(() => { copyBtn.textContent = "Copy"; }, 1500);
    };
    btnRow.appendChild(copyBtn);

    const closeBtn = document.createElement("button");
    closeBtn.textContent = "Close";
    closeBtn.style.cssText = btnStyle;
    closeBtn.onclick = () => document.body.removeChild(overlay);
    btnRow.appendChild(closeBtn);

    box.appendChild(btnRow);
    overlay.appendChild(box);
    document.body.appendChild(overlay);
  }

  // Decides the scan status card's state from _currentScanId: hidden once a
  // scan is loaded, "Load save file first" while none is. Called after every
  // load attempt (success, failure, or cancel) - #scan-status-card only
  // exists in ui/web/index.html (desktop's ui.html has no equivalent yet),
  // so this is a no-op there.
  function refreshScanStatusCard() {
    const card = document.getElementById("scan-status-card");
    const bar = document.getElementById("scan-progress-bar");
    const idle = document.getElementById("scan-status-idle");
    if (!card) return;
    bar.style.display = "none";
    bar.querySelectorAll(".scan-progress-seg").forEach(seg => {
      seg.classList.remove("done", "active");
    });
    if (_currentScanId != null) {
      card.style.display = "none";
    } else {
      card.style.display = "";
      idle.style.display = "";
    }
  }

  // Swaps the card into its progress-bar state and lights up segments
  // 0..stage-1 as done, `stage` as active (mid-sweep animation, since
  // there's no finer-grained % within a stage). `stage` 4 is a synthetic
  // "all done" marker (there's no real 5th pipeline phase) used right before
  // the card hides, so the user sees a completed bar instead of segment 3
  // stuck mid-sweep.
  function updateScanProgress(stage) {
    const card = document.getElementById("scan-status-card");
    const bar = document.getElementById("scan-progress-bar");
    const idle = document.getElementById("scan-status-idle");
    if (!card) return;
    // New Scan is reachable from the sidebar on any tab, but #tab-overview
    // (and the card inside it) only renders while it's the active tab - jump
    // there on the first stage so the card is actually visible, regardless
    // of which tab the user was on when they clicked New Scan.
    if (stage === 0) switchTab("overview", document.getElementById("nav-overview"));
    card.style.display = "";
    idle.style.display = "none";
    bar.style.display = "";
    bar.querySelectorAll(".scan-progress-seg").forEach((seg, i) => {
      seg.classList.toggle("done", i < stage);
      seg.classList.toggle("active", i === stage);
    });
  }

  // Resolving trades/homebases and writing the DB are all fast compared to
  // the initial XML parse (which can run 80s+ on a large save) - without a
  // floor here, those three stages fire and resolve within the same paint
  // cycle and the bar visibly never seems to leave "Scanning Save" even
  // though the callbacks did fire. Routes every progress update through a
  // promise chain so each stage is guaranteed at least this long on screen.
  const SCAN_STAGE_MIN_DWELL_MS = 400;
  let _scanProgressQueue = Promise.resolve();

  function queueScanProgress(stage) {
    _scanProgressQueue = _scanProgressQueue.then(() => {
      updateScanProgress(stage);
      return new Promise(resolve => setTimeout(resolve, SCAN_STAGE_MIN_DWELL_MS));
    });
  }

  // Ask the Python backend to show the save-picker and run a fresh scan.
  // When the scan completes the picker and data are refreshed automatically.
  function requestNewScan() {
    if (!_bridge) return;
    // Registering the listener doesn't show the card by itself - it only
    // switches to the progress bar once the first progress callback actually
    // fires, which is after the user has picked a save file and the real
    // scan has started (not while the folder/file picker dialogs are still up).
    if (_bridge.on_progress) _bridge.on_progress(queueScanProgress);
    _bridge.trigger_scan(function(jsonStr) {
      // Wait for any already-queued stage animations to finish their dwell
      // time before reacting to the final result - otherwise a fast scan
      // could hide the card mid-animation.
      _scanProgressQueue.then(() => {
        try {
          const result = JSON.parse(jsonStr);
          if (result.ok) {
            updateScanProgress(4);   // brief "all done" confirmation
            if (typeof playScanComplete === "function") playScanComplete();
            _bridge.list_scans(function(scansStr) {
              try { populateScanPicker(JSON.parse(scansStr)); } catch(e) {}
            });
            setTimeout(() => loadScan(-1), SCAN_STAGE_MIN_DWELL_MS);
          } else {
            // Failed or cancelled - revert the card to whatever state already
            // matched _currentScanId before this attempt (hidden if a scan was
            // already loaded, idle text if not), then report a real error.
            refreshScanStatusCard();
            if (!result.cancelled) showScanErrorDialog(result.error);
          }
        } catch(e) {}
      });
    });
  }

  // Open/close the custom scan picker menu. Clicking outside auto-closes it.
  function toggleScanPicker(e) {
    e.stopPropagation();
    const menu = document.getElementById('scan-picker-menu');
    const open = menu.style.display !== 'none';
    menu.style.display = open ? 'none' : '';
    if (!open) document.addEventListener('click', _closeScanPicker, { once: true });
  }

  function _closeScanPicker() {
    document.getElementById('scan-picker-menu').style.display = 'none';
  }

  // Fill the top-bar picker from the scan history (newest first).
  // Shows whenever there is at least one scan so the user can always delete.
  function populateScanPicker(scans) {
    const field = document.getElementById('tb-scan-field');
    const menu  = document.getElementById('scan-picker-menu');
    const label = document.getElementById('scan-picker-label');
    if (!Array.isArray(scans) || scans.length === 0) { field.style.display = 'none'; return; }

    // Keep button label in sync with whatever scan is currently loaded.
    const current = scans.find(s => s.scan_id == _currentScanId) || scans[0];
    label.textContent = current.scan_id;

    menu.innerHTML = '';
    scans.forEach(s => {
      const save = (s.save_file || '').replace(/\.xml(\.gz)?$/, '');
      const when = (s.scanned_at || '').replace('T', ' ').slice(0, 16);
      const row = document.createElement('div');
      row.className = 'scan-picker-row' + (s.scan_id == _currentScanId ? ' active' : '');
      row.innerHTML = `
        <div class="scan-picker-info">
          <span class="scan-picker-num">#${s.scan_id}</span>
          <span class="scan-picker-detail">${save}${when ? '  ·  ' + when : ''}</span>
        </div>
        <button class="scan-picker-del" data-text-tip="Delete this scan" onclick="event.stopPropagation(); deleteScan(${s.scan_id})"><i class="ti ti-trash" style="font-size:13px"></i></button>
      `;
      row.addEventListener('click', () => {
        _currentScanId = s.scan_id;
        // Update the highlight immediately - loadScan()'s populate() callback
        // fixes the label but never touches these row elements, so without
        // this the previously-selected row stays highlighted until the menu
        // is next rebuilt (e.g. after a new scan or delete).
        menu.querySelectorAll('.scan-picker-row').forEach(r => r.classList.remove('active'));
        row.classList.add('active');
        loadScan(s.scan_id);
        document.getElementById('scan-picker-menu').style.display = 'none';
      });
      menu.appendChild(row);
    });

    const footer = document.createElement('div');
    footer.className = 'scan-picker-footer';
    footer.innerHTML = `<button class="scan-picker-delall">Delete All Scans</button>`;
    // Two-click confirm (no modal): first click arms it, second click within
    // 3s actually deletes. Clicking elsewhere/closing the menu disarms it
    // (the menu is rebuilt from scratch on every open, so a stale armed
    // state can never carry over between opens).
    const delAllBtn = footer.querySelector('.scan-picker-delall');
    let armed = false, armTimer = null;
    delAllBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      if (!armed) {
        armed = true;
        delAllBtn.textContent = 'Click again to confirm';
        delAllBtn.classList.add('armed');
        armTimer = setTimeout(() => {
          armed = false;
          delAllBtn.textContent = 'Delete All Scans';
          delAllBtn.classList.remove('armed');
        }, 3000);
        return;
      }
      clearTimeout(armTimer);
      deleteAllScans();
    });
    menu.appendChild(footer);

    field.style.display = '';
  }

  // Delete a scan from the DB then refresh the picker. If the deleted scan was
  // currently loaded, automatically loads the next newest remaining scan.
  function deleteScan(scanId) {
    if (!_bridge) return;
    _bridge.delete_scan(scanId, function() {
      _bridge.list_scans(function(jsonStr) {
        try {
          const scans = JSON.parse(jsonStr);
          if (scanId == _currentScanId) {
            if (scans.length > 0) {
              _currentScanId = scans[0].scan_id;
              loadScan(_currentScanId);
            } else {
              _currentScanId = null;
            }
          }
          populateScanPicker(scans);
        } catch(e) { /* silent */ }
      });
    });
  }

  // Delete every scan then refresh the picker. Called after the footer
  // button's two-click arm/confirm in populateScanPicker.
  function deleteAllScans() {
    if (!_bridge) return;
    _bridge.delete_all_scans(function() {
      _currentScanId = null;
      document.getElementById('scan-picker-menu').style.display = 'none';
      populateScanPicker([]);
      refreshScanStatusCard();
    });
  }

  // Equipment/hull/sector/software/item catalogs are static (shipped with the
  // program, not derived from any save) — fetched once via its own scan-
  // independent bridge call so Resource Library and the universe map's
  // interactive overlay work even before a scan has ever been run. Scan
  // payloads no longer carry this data (see populate.js), so this is the
  // sole writer of EQUIPMENT_CATALOG/HULL_CATALOG/SECTOR_CATALOG/SOFTWARE_CATALOG/ITEM_CATALOG.
  function loadResourceLibrary() {
    if (!_bridge) return;
    _bridge.get_resource_library(function(jsonStr) {
      try {
        const data = JSON.parse(jsonStr);
        EQUIPMENT_CATALOG = data.equipment_catalog || {};
        HULL_CATALOG = data.hull_catalog || {};
        SECTOR_CATALOG = data.sector_catalog || {};
        SOFTWARE_CATALOG = data.software_catalog || {};
        ITEM_CATALOG = data.item_catalog || {};
        // This callback races the list_scans one: if the empty-DB skeleton
        // map already rendered without the catalog, re-render so the static
        // sectors appear. Never rerun a render that had real scan data.
        if (_uLastMapData && !(_uLastMapData.sectors || []).length) {
          renderUniverseMap(_uLastMapData);
        }
      } catch(e) { /* Resource Library stays empty */ }
    });
  }

  // Shared list_scans callback for both bridge branches. When the DB is empty,
  // loadScan(-1) has nothing to render and populate() never runs — draw the
  // static galaxy skeleton so the Universe tab isn't blank (it opens on the
  // interactive overlay in that state; see universe-map.js).
  function initScanPicker(jsonStr) {
    let scans = null;
    try { scans = JSON.parse(jsonStr); } catch(e) { /* picker stays hidden */ }
    if (scans) populateScanPicker(scans);
    if (scans && !scans.length) renderUniverseMap({});
  }

  if (window._bridge) {
    // Web build (Pyodide + Web Worker): pyodide-bridge.js already set this
    // up before this script ran, with the same method shape a QWebChannel
    // bridge has — no handshake needed since both sides are already JS. Same
    // startup sequence as the QWebChannel branch below.
    _bridge = window._bridge;
    loadResourceLibrary();
    _bridge.list_scans(initScanPicker);
    loadScan(-1);
  } else if (typeof qt !== 'undefined' && qt.webChannelTransport) {
    new QWebChannel(qt.webChannelTransport, function(channel) {
      _bridge = channel.objects.bridge;
      loadResourceLibrary();
      // Build the history picker, then render the latest scan.
      _bridge.list_scans(initScanPicker);
      loadScan(-1);
    });
  } else {
    // Plain-browser dev mode: no bridge, no history — fall back to the JSON
    // file, which write_export() embeds the catalog into directly since
    // there's no bridge here to call get_resource_library() on.
    loadFromJsonFile();
  }
