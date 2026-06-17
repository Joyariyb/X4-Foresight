  function hexToRgba(hex, alpha) {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return `rgba(${r},${g},${b},${alpha})`;
  }

  function switchFleetTab(faction, el) {
    // Scoped to the Naval strip — .fleet-subtab is shared by the Crew and
    // Diplomacy strips, and an unscoped clear would wipe their active state.
    document.querySelectorAll('#fleet-subtabs .fleet-subtab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.fleet-panel').forEach(p => p.classList.remove('active'));
    (el || document.querySelector(`#fleet-subtabs [data-faction="${faction}"]`)).classList.add('active');
    document.getElementById('fleet-panel-' + faction).classList.add('active');
  }

  // The Diplomacy faction selector is a dropdown (built from the same
  // .fleet-subtab buttons that used to form the strip) plus a peer Matrix
  // toggle. diploSelection tracks the current choice for back-navigation.
  let diploSelection = 'player';

  function toggleDiploDropdown(e) {
    if (e) e.stopPropagation();   // don't let the outside-click handler close it
    document.getElementById('diplo-dd-menu').classList.toggle('open');
  }
  function closeDiploDropdown() {
    document.getElementById('diplo-dd-menu')?.classList.remove('open');
  }
  // Any click outside the dropdown dismisses the open menu.
  document.addEventListener('click', (e) => {
    if (!e.target.closest('#diplo-dd')) closeDiploDropdown();
  });

  function switchDiploTab(faction) {
    document.querySelectorAll('.diplo-panel').forEach(p => p.classList.remove('active'));
    document.getElementById('diplo-panel-' + faction)?.classList.add('active');
    diploSelection = faction;

    const trigger   = document.getElementById('diplo-dd-trigger');
    const matrixBtn = document.getElementById('diplo-matrix-btn');

    if (faction === 'matrix') {
      // Matrix is its own button. The trigger keeps showing the last faction
      // but drops its active ring so only one control reads as selected.
      matrixBtn?.classList.add('active');
      trigger.classList.remove('active');
    } else {
      // Mirror the chosen faction onto the trigger by copying straight from its
      // menu item — label (incl. any lock icon) and the three colour vars — so
      // the closed dropdown looks exactly like the old per-faction button.
      const item = document.querySelector(`#diplo-dd-menu [data-faction="${faction}"]`);
      if (item) {
        document.getElementById('diplo-dd-label').innerHTML = item.innerHTML;
        ['--tab-color', '--tab-bg', '--tab-border'].forEach(v =>
          trigger.style.setProperty(v, item.style.getPropertyValue(v)));
        document.querySelectorAll('#diplo-dd-menu .fleet-subtab').forEach(i => i.classList.remove('active'));
        item.classList.add('active');
      }
      trigger.dataset.faction = faction;
      trigger.classList.add('active');
      matrixBtn?.classList.remove('active');
    }
    closeDiploDropdown();
  }

  // Per-faction sort state and cached ship lists so setNpcSort() can re-render
  // without re-running populate().
  const npcSortState  = {};  // { factionId: { key, dir } }
  const npcShipsCache = {};  // { factionId: [...ships] }

  // Same toggle behaviour as the player table's setSort(): clicking the active
  // column reverses direction, clicking a new column starts ascending.
  function setNpcSort(factionId, key) {
    const state = npcSortState[factionId];
    if (key === state.key) {
      state.dir *= -1;
    } else {
      state.key = key;
      state.dir = 1;
    }
    renderNpcFleet(npcShipsCache[factionId], factionId);
  }

  function renderNpcFleet(ships, factionId) {
    const tbody = document.querySelector(`#npc-table-${factionId} tbody`);
    if (!tbody) return;
    const state  = npcSortState[factionId] || { key: 'role', dir: 1 };
    updateSortHeaders(`#npc-table-${factionId}`, state.key, state.dir);
    const sorted = [...ships].sort((a, b) => {
      const av = sortValue(a, state.key);
      const bv = sortValue(b, state.key);
      if (av === null && bv === null) return 0;
      if (av === null) return 1;
      if (bv === null) return -1;
      if (av < bv) return -1 * state.dir;
      if (av > bv) return  1 * state.dir;
      return 0;
    });
    tbody.innerHTML = sorted.map(s => {
      const sCol  = SIZE_COLOURS[s.size]   || 'var(--text-dim)';
      const oCol  = ORDER_COLOURS[s.order] || 'var(--text-dim)';
      const oIcon = ORDER_ICONS[s.order]   || 'ti-circle';
      return `<tr data-code="${s.code}">
        <td style="white-space:nowrap;height:34px">
          <span class="ship-name">${s.name || '—'}</span>
          <span class="mono" style="color:var(--yellow);font-size:11px;margin-left:8px">${s.code}</span>
        </td>
        <td class="mono" style="color:${sCol}">${s.size}</td>
        <td style="white-space:nowrap">${hullBadge(s.hull_origin)}<i class="ti ${ROLE_ICONS[s.role]||'ti-rocket'}" style="font-size:12px;vertical-align:-2px;margin-left:5px;margin-right:3px;color:var(--text-faint)"></i>${s.role}</td>
        <td><i class="ti ${oIcon}" style="font-size:12px;vertical-align:-2px;margin-right:4px;color:${oCol}"></i><span style="color:${oCol}">${s.order}</span></td>
        <td style="color:var(--text-dim)"><i class="ti ti-map-pin" style="font-size:12px;vertical-align:-2px;margin-right:4px;color:var(--text-faint)"></i>${s.sector}</td>
      </tr>`;
    }).join('');
  }

