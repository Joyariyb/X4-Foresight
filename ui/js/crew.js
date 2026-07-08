  // ── CREW TAB ──────────────────────────────────────────────────────────────
  let allCrewData      = [];
  let filteredCrewData = [];
  let crewRoleFilter   = 'all';

  // Hex values so we can do hex-alpha tricks like `${col}22` for badge backgrounds.
  const ROLE_COLOURS = {
    manager: '#a371f7',
    pilot:   '#d29922',
    service: '#3fb950',
    marine:  '#f85149',
  };

  const ROLE_PRIMARY = {
    manager: 'management',
    pilot:   'piloting',
    service: 'engineering',
    marine:  'boarding',
  };

  const ROLE_LABELS_CREW = {
    manager: 'Manager',
    pilot:   'Pilot',
    service: 'Service',
    marine:  'Marine',
  };

  const SKILL_NAMES = {
    piloting: 'Piloting', management: 'Management',
    engineering: 'Engineering', morale: 'Morale', boarding: 'Boarding',
  };

  // Primary skill shown first, rest follow in role-appropriate order.
  const SKILL_ORDER_BY_ROLE = {
    manager: ['management', 'morale', 'engineering', 'piloting', 'boarding'],
    pilot:   ['piloting',   'management', 'engineering', 'morale', 'boarding'],
    service: ['engineering','morale', 'management', 'piloting', 'boarding'],
    marine:  ['boarding',   'morale', 'engineering', 'management', 'piloting'],
  };

  function switchCrewRole(role, el) {
    crewRoleFilter = role;
    document.querySelectorAll('#crew-subtabs .fleet-subtab').forEach(t => t.classList.remove('active'));
    (el || document.querySelector(`#crew-subtabs [data-role="${role}"]`)).classList.add('active');
    // Clear file panel when switching roles — the previous selection no longer applies.
    document.getElementById('crew-file-empty').style.display = '';
    document.getElementById('crew-file-card').style.display  = 'none';
    renderCrewRoster();
  }

  // Crew column sort. crewSortKey starts null = keep the save-file order until
  // a header is clicked, so the roster looks the same as before this feature.
  let crewSortKey = null;
  let crewSortDir = 1;

  // Comparable value per crew member and sort key (same null-to-bottom contract
  // as the fleet tables' sortValue()).
  function crewSortValue(c, key) {
    if (key === 'skill') {
      // Sort by each member's PRIMARY skill — the one their roster row displays.
      const primaryKey = ROLE_PRIMARY[c.role] || 'piloting';
      return c.skills ? (c.skills[primaryKey] ?? null) : null;
    }
    if (key === 'assigned') return c.assigned_to ? c.assigned_to.toLowerCase() : null;
    if (key === 'sector')   return c.sector ? c.sector.toLowerCase() : null;
    return (c[key] || '').toString().toLowerCase();
  }

  function setCrewSort(key) {
    if (key === crewSortKey) {
      crewSortDir *= -1;
    } else {
      crewSortKey = key;
      // Skill defaults to descending — best crew first, like the player
      // table's pilot column.
      crewSortDir = key === 'skill' ? -1 : 1;
    }
    renderCrewRoster();
  }

  function renderCrewRoster() {
    filteredCrewData = crewRoleFilter === 'all'
      ? allCrewData
      : allCrewData.filter(c => c.role === crewRoleFilter);

    // Sort a COPY — when the filter is 'all', filteredCrewData aliases
    // allCrewData, and sorting that in place would silently reorder it,
    // breaking the data-crew-idx indexes stored in the fleet table's rows.
    if (crewSortKey) {
      filteredCrewData = [...filteredCrewData].sort((a, b) => {
        const av = crewSortValue(a, crewSortKey);
        const bv = crewSortValue(b, crewSortKey);
        // Nulls always sink to the bottom regardless of direction.
        if (av === null && bv === null) return 0;
        if (av === null) return 1;
        if (bv === null) return -1;
        if (av < bv) return -1 * crewSortDir;
        if (av > bv) return  1 * crewSortDir;
        return 0;
      });
    }
    updateSortHeaders('#crew-table', crewSortKey, crewSortDir);

    document.querySelector('#crew-table tbody').innerHTML = filteredCrewData.map((c, i) => {
      const primaryKey = ROLE_PRIMARY[c.role] || 'piloting';
      const primaryPts = c.skills ? (c.skills[primaryKey] ?? 0) : 0;
      const col        = ROLE_COLOURS[c.role]     || '#2dd4bf';
      const lbl        = ROLE_LABELS_CREW[c.role] || c.role;
      return `<tr class="crew-row" data-idx="${i}" onclick="showCrewFile(${i})" style="cursor:pointer">
        <td style="white-space:nowrap">${c.name}</td>
        <td><span class="badge" style="background:${col}22;color:${col};border-color:${col}44">${lbl}</span></td>
        <td><span style="letter-spacing:-1px">${skillStars(primaryPts)}</span></td>
        <td style="color:var(--text-secondary)">${c.assigned_to || '—'}</td>
        <td style="color:var(--text-brand)">${c.sector || '—'}</td>
      </tr>`;
    }).join('');
  }

  function showCrewFile(idx) {
    const c = filteredCrewData[idx];
    if (!c) return;

    // Highlight the selected row, clear any previous highlight.
    document.querySelectorAll('#crew-table .crew-row').forEach(r => r.classList.remove('crew-row-active'));
    const row = document.querySelector(`#crew-table .crew-row[data-idx="${idx}"]`);
    if (row) row.classList.add('crew-row-active');

    document.getElementById('crew-file-empty').style.display = 'none';
    const card = document.getElementById('crew-file-card');
    card.style.display = 'block';

    const col = ROLE_COLOURS[c.role]     || '#2dd4bf';
    const lbl = ROLE_LABELS_CREW[c.role] || c.role;

    // Skill rows — role-appropriate order, primary first.
    const skillOrder = SKILL_ORDER_BY_ROLE[c.role] || Object.keys(c.skills || {});
    const skillsHtml = skillOrder
      .filter(sk => c.skills && c.skills[sk] != null)
      .map(sk => {
        const pts = c.skills[sk];
        return `<div class="file-skill-row">
          <span class="file-skill-name">${SKILL_NAMES[sk] || sk}</span>
          <span class="file-skill-stars">${skillStars(pts)}</span>
          <span class="file-skill-pts">${pts} pts</span>
        </div>`;
      }).join('');

    // Profile metadata from macro parsing — only shown when available.
    const metaRows = [
      ['Faction',   c.faction],
      ['Gender',    c.gender],
      ['Ethnicity', c.ethnicity],
      ['Variant',   c.variant],
    ].filter(([, v]) => v);
    const metaHtml = metaRows.map(([lbl, val]) =>
      `<div class="file-meta-row">
        <span class="file-meta-label">${lbl}</span>
        <span class="file-meta-val">${val}</span>
      </div>`
    ).join('');

    // Assignment asset — show the ship/station's name (assigned_name, resolved in
    // populate.js), linked to its home tab. assigned_code is the routing handle,
    // kept as a secondary tag only when we have a distinct name to pair it with
    // (so a nameless asset reads "[ABC-123]", not "ABC-123 [ABC-123]"). Stations
    // route to the Stations tab; everything else to Naval.
    const assetName = c.assigned_name || c.assigned_code || 'Unassigned';
    const codeTag   = c.assigned_code && c.assigned_name
      ? `<span class="file-assign-code"> [${c.assigned_code}]</span>` : '';
    const assignHtml = c.assigned_code
      ? `<span class="file-assign-name crew-link" onclick="${
          c.assigned_type === 'station'
            ? `goToStation('${c.assigned_code}')`
            : `jumpToShip('${c.assigned_code}','player')`
        }">${assetName}${codeTag}</span>`
      : `<span class="file-assign-name">${assetName}</span>`;

    // Sector — link to its Sectors-tab card when we know the macro. goToSector
    // guards undiscovered sectors itself, so an unknown-space click is a no-op.
    const sectorHtml = c.sector_macro
      ? `<span class="file-assign-sector crew-link" onclick="goToSector('${c.sector_macro}')">${c.sector || '—'}</span>`
      : `<span class="file-assign-sector">${c.sector || '—'}</span>`;

    card.innerHTML = `
      <div class="file-header">
        <div class="file-name">${c.name}</div>
        <span class="badge" style="background:${col}22;color:${col};border-color:${col}44">${lbl}</span>
      </div>
      ${skillsHtml ? `<div class="file-section">
        <div class="file-sec-label">Skills</div>
        ${skillsHtml}
      </div>` : ''}
      <div class="file-section">
        <div class="file-meta-row">
          <span class="file-meta-label">Assignment</span>
          ${assignHtml}
        </div>
        <div class="file-meta-row">
          <span class="file-meta-label">Sector</span>
          ${sectorHtml}
        </div>
      </div>
      ${metaHtml ? `<div class="file-section">
        <div class="file-sec-label">Profile</div>
        ${metaHtml}
      </div>` : ''}
    `;
  }

  // Navigate from a fleet-table pilot name to that pilot's crew file.
  // Switches to the Crew tab, filters to Pilots, selects the row, and scrolls it into view.
  function jumpToCrew(allCrewIdx) {
    _navRecord();
    const crewNavTab = document.querySelector('.nav-tab[onclick*="\'crew\'"]');
    switchTab('crew', crewNavTab);
    _navAfterJump();
    switchCrewRole('pilot', document.querySelector('#crew-subtabs [data-role="pilot"]'));
    const filteredIdx = filteredCrewData.indexOf(allCrewData[allCrewIdx]);
    if (filteredIdx === -1) return;
    showCrewFile(filteredIdx);
    const row = document.querySelector(`#crew-table .crew-row[data-idx="${filteredIdx}"]`);
    if (row) row.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }

