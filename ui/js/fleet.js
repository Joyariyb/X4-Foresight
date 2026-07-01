  // Core role: Displays and filters player fleet with sortable columns (role, pilot, health, etc.).

  let currentSortKey = 'role';
  let currentSortDir = 1;
  let allPlayerShips = []; // Cache to avoid re-running populate() on sort

  // Returns a comparable value for a given ship and sort key.
  // Numeric keys (size, health) return numbers so they sort correctly.
  // String keys return lowercase strings. Null/missing values are pushed
  // to the end of the list regardless of sort direction (handled in renderFleet).
  function sortValue(ship, key) {
    if (key === 'pilot')   return (ship.pilot && ship.pilot.skills && ship.pilot.skills.piloting != null) ? ship.pilot.skills.piloting : null;
    if (key === 'size')    return { S: 0, M: 1, L: 2, XL: 3 }[ship.size] ?? null;
    if (key === 'health')  return (ship.hull_pct !== null && ship.hull_pct !== undefined) ? ship.hull_pct : null;
    // Sort by absolute shield HP, not percentage: a 200k-HP shield should
    // outrank a 5k one even when both read "Full". Ships with no shield
    // generator have a null shield_hp; we map them to -1 (below 0 HP) rather
    // than null so they aren't pushed to the bottom — instead they lead an
    // ascending sort, i.e. "start from the ones with no shields".
    if (key === 'shield')  return (ship.shield_hp !== null && ship.shield_hp !== undefined) ? ship.shield_hp : -1;
    if (key === 'name')    return (ship.display_name || ship.name || '').toLowerCase();
    // Unassigned ships (null homebase_code) sort to the bottom — same null-push
    // logic as other keys, handled by the null checks in renderFleet's sort().
    if (key === 'station') return ship.homebase_code ? ship.homebase_code.toLowerCase() : null;
    return (ship[key] || '').toString().toLowerCase();
  }

  function renderFleet(ships, sortKey, sortDir) {
    const sorted = [...ships].sort((a, b) => {
      const av = sortValue(a, sortKey);
      const bv = sortValue(b, sortKey);

      // Always push null values to the bottom regardless of sort direction,
      // so ships with missing data don't jump to the top when reversing.
      if (av === null && bv === null) return 0;
      if (av === null) return 1;
      if (bv === null) return -1;

      if (av < bv) return -1 * sortDir;
      if (av > bv) return  1 * sortDir;
      return 0;
    });

    document.querySelector("#fleet-table tbody").innerHTML = sorted.map(s => {
      const oCol    = ORDER_COLOURS[s.order] || "var(--text-secondary)";
      const sCol    = SIZE_COLOURS[s.size]   || "var(--text-secondary)";
      const oIcon   = ORDER_ICONS[s.order]   || "ti-circle";
      const nameStr = s.display_name || s.name || "—";
      // Gate the Hull Type cell's click-through on the hull actually being
      // catalogued — a few rare hulls (escape pods, etc.) have no HULL_CATALOG entry.
      const hasHullPage = s.macro && HULL_CATALOG[s.macro];

      // ── Pilot cell ────────────────────────────────────────────────────────
      // The pilot's name is no longer shown as text in the row — it lives in
      // the tooltip that appears when hovering the skill stars, saving space
      // for the new Station column.
      let pilotEl;
      const hasPilot = s.pilot && s.pilot.name;
      if (!hasPilot) {
        // No crew assigned — dim italic placeholder so the column stays readable.
        pilotEl = `<span style="color:var(--text-secondary);font-style:italic;font-size:11px">Unassigned</span>`;
      } else {
        const pilotName = s.pilot.name;
        const plt = (s.pilot.skills && s.pilot.skills.piloting != null)
          ? s.pilot.skills.piloting : null;
        // plt === null means the pilot exists but has no recorded skill data —
        // show 5 empty stars (skillStars(0)) so the column is never blank.
        const starsHtml = `<span style="letter-spacing:-1px;vertical-align:middle;font-size:13px">${skillStars(plt !== null ? plt : 0)}</span>`;
        const skills    = s.pilot.skills || {};
        // Escape single-quotes so the JSON is safe inside a single-quoted attribute.
        const skillsAttr = JSON.stringify(skills).replace(/'/g, '&#39;');
        // Escape the pilot name for use inside an HTML attribute value.
        const nameAttr   = pilotName.replace(/&/g, '&amp;').replace(/"/g, '&quot;');
        const crewIdx    = allCrewData.findIndex(c => c.name === pilotName && c.role === 'pilot');
        if (crewIdx >= 0) {
          // Clickable stars — same crew-file navigation as the old pilot name link.
          // data-pilot-skills drives the hover tooltip; data-pilot-name is rendered
          // as a header inside that tooltip by pilotTipHtml().
          pilotEl = `<span class="crew-link" data-crew-idx="${crewIdx}"` +
                    ` data-pilot-skills='${skillsAttr}'` +
                    ` data-pilot-name="${nameAttr}">${starsHtml}</span>`;
        } else {
          // Pilot not in crew data — show stars with name-in-tooltip but no click.
          pilotEl = `<span data-pilot-skills='${skillsAttr}'` +
                    ` data-pilot-name="${nameAttr}" style="cursor:default">${starsHtml}</span>`;
        }
      }

      // ── Station cell ──────────────────────────────────────────────────────
      // homebase_code comes from the LEFT JOIN in _ships() and is the station's
      // display code (e.g. "TDD"). Clicking it switches to the Stations tab and
      // scrolls directly to that station's card.
      const stationEl = s.homebase_code
        ? `<span class="stn-link" data-stn-code="${s.homebase_code}">${s.homebase_code}</span>`
        : `<span style="color:var(--text-brand)">—</span>`;

      // Equipment loadout drives the hover tooltip on the ship name, and also
      // means there's a Designs-tab card for this ship to jump to. Both are
      // gated on the same condition, so deployables (whose only gear is an
      // unresolved internal part) get neither.
      const hasDesign = s.loadout && s.loadout.some(e => !e.name.endsWith('_macro'));
      const loadoutAttr = hasDesign
        ? ` data-loadout-tip="${encodeURIComponent(JSON.stringify(s.loadout))}" onclick="jumpToDesign('${s.code}')" style="cursor:pointer"`
        : '';

      return `<tr data-code="${s.code}">
        <td style="white-space:nowrap">
          <span class="ship-name"${loadoutAttr}>${nameStr}</span>
          <span class="mono" style="color:var(--color-highlight);font-size:11px;margin-left:8px">${s.code}</span>
        </td>
        <td class="mono" style="color:${sCol}">${s.size}</td>
        <td style="white-space:nowrap">${hasHullPage ? `<span class="hull-type-link" data-hull-macro="${s.macro}">` : ''}${hullBadge(s.hull_origin)}<i class="ti ${ROLE_ICONS[s.role]||'ti-rocket'}" style="font-size:12px;vertical-align:-2px;margin-left:5px;margin-right:3px;color:var(--text-brand)"></i>${s.role}${hasHullPage ? '</span>' : ''}</td>
        <td>
          <div style="display:flex;flex-direction:column;gap:3px">
            ${hullBar(s.hull_pct, s.hull_hp, s.max_hull)}
            ${shieldBar(s.shield_pct, s.shield_hp, s.shield_max)}
          </div>
        </td>
        <td><i class="ti ${oIcon}" style="font-size:12px;vertical-align:-2px;margin-right:4px;color:${oCol}"></i><span style="color:${oCol}">${s.order}</span></td>
        <td style="color:var(--text-secondary)">${s.sector_macro ? `<span class="sector-link" data-sector-macro="${s.sector_macro}">` : ''}<i class="ti ti-map-pin" style="font-size:12px;vertical-align:-2px;margin-right:4px;color:var(--text-brand)"></i>${s.sector}${s.sector_macro ? '</span>' : ''}</td>
        <td style="white-space:nowrap">${stationEl}</td>
        <td style="color:var(--text-brand);white-space:nowrap"><i class="ti ti-user" style="font-size:12px;vertical-align:-2px;margin-right:4px"></i>${pilotEl}</td>
      </tr>`;
    }).join("");
  }

  // Called when a column header is clicked.
  // Clicking the active column toggles direction; clicking a new column resets
  // direction to ascending, except health and pilot skill which default to
  // descending (highest first). Shields default to ascending so the ships with
  // no/low shields surface first (the no-shield sentinel of -1 sorts to the top).
  function setSort(key) {
    if (key === currentSortKey) {
      currentSortDir *= -1;
    } else {
      currentSortKey = key;
      currentSortDir = (key === 'health' || key === 'pilot') ? -1 : 1;
    }
    updateFleetSortHeaders();
    renderFleet(allPlayerShips, currentSortKey, currentSortDir);
  }

  // Highlights the active sort column and shows the direction arrow in its
  // header. Shared by the player fleet, NPC fleet and crew tables — pass the
  // table's selector plus that table's own sort state. activeKey may be null
  // (crew table before any header is clicked) — every header just shows plain.
  function updateSortHeaders(tableSelector, activeKey, dir) {
    // Match any [data-sort-key] element, not just <th>: the merged Hull/Shields
    // column carries its sort keys on inner <span>s. Both th's and those spans
    // are text-only, so the textContent rewrite below is safe for either.
    document.querySelectorAll(`${tableSelector} [data-sort-key]`).forEach(el => {
      const isActive = el.dataset.sortKey === activeKey;
      el.classList.toggle('sort-active', isActive);
      // Cache the original label text on first call so we can restore it cleanly.
      if (!el.dataset.label) el.dataset.label = el.textContent.trim();
      el.textContent = isActive
        ? `${el.dataset.label} ${dir === 1 ? '↑' : '↓'}`
        : el.dataset.label;
    });
  }

  function updateFleetSortHeaders() {
    updateSortHeaders('#fleet-table', currentSortKey, currentSortDir);
  }

  document.getElementById('fleet-table').addEventListener('click', function(e) {
    // Crew file navigation (pilot stars)
    const crewLink = e.target.closest('.crew-link');
    if (crewLink) {
      e.stopPropagation();
      const allIdx = parseInt(crewLink.dataset.crewIdx, 10);
      if (!isNaN(allIdx) && allIdx >= 0) jumpToCrew(allIdx);
      return;
    }
    // Station navigation (homebase code)
    const stnLink = e.target.closest('.stn-link');
    if (stnLink) {
      e.stopPropagation();
      const code = stnLink.dataset.stnCode;
      if (code) goToStation(code);
      return;
    }
    // Hull Inspector navigation (Hull Type cell)
    const hullLink = e.target.closest('.hull-type-link');
    if (hullLink) {
      e.stopPropagation();
      const macro = hullLink.dataset.hullMacro;
      if (macro) jumpToHull(macro);
      return;
    }
    // Sectors-tab navigation (Sector cell)
    const sectorLink = e.target.closest('.sector-link');
    if (sectorLink) {
      e.stopPropagation();
      const macro = sectorLink.dataset.sectorMacro;
      if (macro) goToSector(macro);
    }
  });


  // ── Tooltip content builders ───────────────────────────────
  // Moved out of tooltips.js (the dispatcher there is a shared engine): each
  // builder lives with the feature that stamps its matching data-* attribute.
  // The dispatcher still calls these by name — they are file-global here.

    function loadoutTipHtml(loadout) {
      // Same layout as moduleTipHtml, plus maker faction when available.
      const SLOT_ORDER = [
        ['weapon',   'Weapons'],
        ['turret',   'Turrets'],
        ['shield',   'Shields'],
        ['engine',   'Engine'],
        ['thruster', 'Thruster'],
      ];
      const FACTION = {
        argon:'Argon', paranid:'Paranid', teladi:'Teladi', split:'Split',
        terran:'Terran', boron:'Boron', xenon:'Xenon', khaak:"Kha'ak",
        pirate:'Pirate', yaki:'Yaki',
      };
      const sections = SLOT_ORDER.map(([slot, label]) => {
        // Skip unresolved internal parts (raw macros still end in "_macro"), so a
        // deployable's hidden engine never shows a raw id in the tooltip.
        const items = loadout.filter(e => e.slot === slot && !e.name.endsWith('_macro'));
        if (!items.length) return '';
        const rows = items.map(e => {
          const mk  = e.mk ? ` Mk${e.mk}` : '';
          const fac = FACTION[e.race]
            ? `<span style="color:var(--text-secondary);font-size:1rem;margin-right:0.8rem">${FACTION[e.race]}</span>` : '';
          return `<div style="display:flex;justify-content:space-between;align-items:baseline;gap:1.2rem;padding:1px 0">
                    <span style="color:var(--text-secondary);font-size:1.1rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${e.name}${mk}</span>
                    <span style="flex-shrink:0;white-space:nowrap">${fac}<span style="color:var(--text-brand);font-size:1rem">×${e.count}</span></span>
                  </div>`;
        }).join('');
        return `<div style="margin-bottom:0.8rem">
                  <div style="font-size:0.9rem;letter-spacing:0.12em;text-transform:uppercase;color:var(--text-brand);margin-bottom:0.4rem;padding-bottom:0.3rem;border-bottom:1px solid var(--outline)">${label}</div>
                  ${rows}
                </div>`;
      }).join('');
      return `<div style="min-width:20rem;max-width:28rem;padding:0.2rem 0">${sections || '—'}</div>`;
    }


  // ── Tooltip registration ──────────────────────────────────────────
  // Fleet rows stamp both of these: the ship-name equipment loadout and the
  // pilot-skills stars. pilotTipHtml lives in formatters.js (loaded earlier).
  registerTip('loadoutTip', (el, _e, tip) => {
    tip.innerHTML = loadoutTipHtml(JSON.parse(decodeURIComponent(el.dataset.loadoutTip)));
    tip.style.color      = '';
    tip.style.whiteSpace = 'normal';
    return true;
  });

  registerTip('pilotSkills', (el, _e, tip) => {
    // data-pilot-name is the pilot's display name (moved off the row).
    tip.innerHTML = pilotTipHtml(JSON.parse(el.dataset.pilotSkills), el.dataset.pilotName || '');
    tip.style.color      = '';
    tip.style.whiteSpace = 'nowrap';
    return true;
  });
