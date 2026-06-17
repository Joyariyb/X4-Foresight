  function loadFromJsonFile() {
    fetch('../x4_empire_state.json')
      .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(populate)
      .catch(e => {
        document.getElementById("loading").textContent =
          "No Qt bridge and could not load x4_empire_state.json: " + e;
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
      } catch(e) {
        document.getElementById("loading").textContent = "Error parsing data: " + e;
      }
    });
  }

  // Ask the Python backend to show the save-picker and run a fresh scan.
  // When the scan completes the picker and data are refreshed automatically.
  function requestNewScan() {
    if (!_bridge) return;
    _bridge.trigger_scan(function(jsonStr) {
      try {
        const result = JSON.parse(jsonStr);
        if (result.ok) {
          _bridge.list_scans(function(scansStr) {
            try { populateScanPicker(JSON.parse(scansStr)); } catch(e) {}
          });
          loadScan(-1);
        }
      } catch(e) {}
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
        <button class="scan-picker-del" title="Delete this scan" onclick="event.stopPropagation(); deleteScan(${s.scan_id})"><i class="ti ti-trash" style="font-size:13px"></i></button>
      `;
      row.addEventListener('click', () => {
        _currentScanId = s.scan_id;
        loadScan(s.scan_id);
        document.getElementById('scan-picker-menu').style.display = 'none';
      });
      menu.appendChild(row);
    });

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

  if (typeof qt !== 'undefined' && qt.webChannelTransport) {
    new QWebChannel(qt.webChannelTransport, function(channel) {
      _bridge = channel.objects.bridge;
      // Build the history picker, then render the latest scan.
      _bridge.list_scans(function(jsonStr) {
        try { populateScanPicker(JSON.parse(jsonStr)); } catch(e) { /* picker stays hidden */ }
      });
      loadScan(-1);
    });
  } else {
    // Plain-browser dev mode: no bridge, no history — fall back to the JSON file.
    loadFromJsonFile();
  }
