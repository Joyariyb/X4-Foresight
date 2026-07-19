  // Core role: Advisor card evidence drawer — the raw-numbers grid, pricing
  // gauge, and station siting's Details/Buyers panel behind each advice
  // card's click-to-expand. Split out of advisors-feed.js because this is
  // the one sub-feature with its own private state (which siting card is on
  // which tab) and lookup tables (station-id evidence keys), self-contained
  // enough to own its own file as new rules keep adding evidence shapes.
  window.AdvisorsEvidence = (function () {
    const { EVIDENCE_LABELS } = window.AdvisorsMeta;

    // Evidence keys that reference a PLAYER station: id key -> {name slot,
    // evidence key holding its `code`}. Player stations live on the Stations
    // tab keyed by code (station-helpers.js goToStation), same as the
    // fleet table's home-station links.
    const PLAYER_STATION_KEYS = {
      station_id:  { nameSlot: 'station_name', codeKey: 'code' },
      homebase_id: { nameSlot: 'station_name', codeKey: 'station_code' },
      // idle_miner's recommended redirect target (see _needy_stations_by_transport
      // in miner.py) — same link pattern, just a different id/code/name triple.
      target_station_id: { nameSlot: 'target_station_name', codeKey: 'target_station_code' },
    };
    // Evidence keys that reference an NPC station: id key -> readable-name
    // slot. The raw value IS the object_id goToNpcStation() (npc-station-
    // inspector.js) navigates by, so no separate code lookup is needed.
    const NPC_STATION_KEYS = {
      npc_station_id: 'npc_name',
      sell_station_id: 'sell_name',
      buy_station_id: 'buy_name',
    };
    // Keys that exist purely to feed the avg-price gauge below, never shown
    // as their own flat row. `code`/`station_code` are NOT listed here —
    // military's damaged_fleet also carries a bare `code` (the ship's own
    // tag, unrelated to any station link), so hiding those two is done per-
    // finding in render(), scoped to whichever PLAYER_STATION_KEYS a
    // finding's evidence actually uses.
    const HIDDEN_EVIDENCE_KEYS = new Set([
      'avg_price', 'price', 'player_price_cents', 'npc_price_cents',
    ]);

    // station_siting drawers only: finding id -> 'details' | 'buyers'. Absent
    // entries default to 'details' rather than storing it explicitly for
    // every card, so non-siting types never touch this map at all.
    let _view = new Map();

    function resetView() { _view = new Map(); }
    function setView(id, view) { _view.set(id, view); }

    // One row of the evidence grid. `sector_macro` and the station-id keys
    // above get special treatment: every rule that emits one also emits a
    // matching readable-name slot, so the drawer can show that name and jump
    // straight to the referenced card instead of dead-ending on an internal
    // id string. `ware_id` similarly swaps in the finding's own `ware_name`
    // slot rather than the raw macro-ish ware id.
    function _evidenceRowHtml(f, k, v) {
      if (k === 'sector_macro') {
        const name = f.slots.sector_name || v;
        return `<div class="adv-ev-key">Sector</div>
          <div class="adv-ev-val"><span class="adv-sector-link" onclick="event.stopPropagation(); goToSector('${v}')"><i class="ti ti-map-pin"></i>${name}</span></div>`;
      }
      // The nearest-deposit sector (miner rules: mining_supply_gap, mine_vs_buy,
      // mineral_demand). Raw `v` is the sector macro; every rule that emits it
      // also emits a resolved `deposit_sector_name` slot, so we show that name
      // and jump to the sector rather than dead-ending on the macro string —
      // same goToSector() jump as `sector_macro` above.
      if (k === 'deposit_sector') {
        const name  = f.slots.deposit_sector_name || v;
        const label = EVIDENCE_LABELS[k] || 'Deposit';
        return `<div class="adv-ev-key">${label}</div>
          <div class="adv-ev-val"><span class="adv-sector-link" onclick="event.stopPropagation(); goToSector('${v}')"><i class="ti ti-map-pin"></i>${name}</span></div>`;
      }
      // mining_oversupply's delivering miners — a list of {code, name}, each a
      // clickable jump to the Fleet tab (jumpToShip by code, same as the
      // ship_id row below). These are the ships to reassign off a full bay, so
      // the drawer links every one rather than just stating a count.
      if (k === 'delivering_miner_ships' && Array.isArray(v)) {
        const label = EVIDENCE_LABELS[k] || 'Delivering Miners';
        const links = v.map(m => m.code
          ? `<span class="adv-ship-link" onclick="event.stopPropagation(); jumpToShip('${m.code}')"><i class="ti ti-rocket"></i>${m.name} (${m.code})</span>`
          : `<span>${m.name}</span>`).join('');
        return `<div class="adv-ev-key">${label}</div>
          <div class="adv-ev-val"><div class="adv-miner-list">${links}</div></div>`;
      }
      if (PLAYER_STATION_KEYS[k]) {
        const { nameSlot, codeKey } = PLAYER_STATION_KEYS[k];
        const name  = f.slots[nameSlot] || v;
        const code  = f.evidence[codeKey];
        const label = EVIDENCE_LABELS[k] || 'Station';
        const val = code
          ? `<span class="adv-station-link" onclick="event.stopPropagation(); goToStation('${code}')"><i class="ti ti-building-factory-2"></i>${name}</span>`
          : name;
        return `<div class="adv-ev-key">${label}</div><div class="adv-ev-val">${val}</div>`;
      }
      if (NPC_STATION_KEYS[k]) {
        const name  = f.slots[NPC_STATION_KEYS[k]] || v;
        const label = EVIDENCE_LABELS[k] || 'Station';
        return `<div class="adv-ev-key">${label}</div>
          <div class="adv-ev-val"><span class="adv-station-link" onclick="event.stopPropagation(); goToNpcStation('${v}')"><i class="ti ti-building-factory-2"></i>${name}</span></div>`;
      }
      if (k === 'ware_id') {
        return `<div class="adv-ev-key">Ware</div><div class="adv-ev-val">${f.slots.ware_name || v}</div>`;
      }
      if (k === 'ship_id' && f.slots.ship_name) {
        // ship_id findings (damaged_fleet, stranded_delivery) are always
        // player ships — the ships table has no NPC rows — so jumpToShip's
        // faction arg is left at its 'player' default, same as jumpToDesign's
        // fleet-tab jumps.
        const code = f.evidence.code;
        const val = code
          ? `<span class="adv-ship-link" onclick="event.stopPropagation(); jumpToShip('${code}')"><i class="ti ti-rocket"></i>${f.slots.ship_name}</span>`
          : f.slots.ship_name;
        return `<div class="adv-ev-key">Ship</div><div class="adv-ev-val">${val}</div>`;
      }
      // sell_price_cents/buy_price_cents (galaxy_arbitrage) are stored in cents
      // like every other *_cents evidence key — convert to Cr/unit here rather
      // than showing the raw cent count, which reads 100x too large.
      if (k === 'sell_price_cents' || k === 'buy_price_cents') {
        const label = EVIDENCE_LABELS[k] || k.replace(/_/g, ' ');
        const cr = (v || 0) / 100;
        return `<div class="adv-ev-key">${label}</div><div class="adv-ev-val">${cr.toLocaleString(undefined, { maximumFractionDigits: 1 })} Cr/unit</div>`;
      }
      const label = EVIDENCE_LABELS[k] || k.replace(/_/g, ' ');
      const value = typeof v === 'number'
        ? (Number.isInteger(v) ? v.toLocaleString() : v.toLocaleString(undefined, { maximumFractionDigits: 2 }))
        : (v ?? '—');
      return `<div class="adv-ev-key">${label}</div><div class="adv-ev-val">${value}</div>`;
    }

    // Inline vs-average price visual — one more key/value row in the SAME
    // .adv-evidence grid as the rest of the drawer (not a boxed block of its
    // own), keyed "Pricing" so the row reads name-left/bar-right like every
    // other evidence row. Same gradient-track-with-glowing-dot instrument as
    // _buyerTipHtml below and cashflow-chart.js's avgPriceTipHtml (the
    // Stations > Economy > Breakdown chart's hover), just static instead of a
    // tooltip. One dot per marker, so pricing_gap can plot "Your Price" and
    // "Their Price" on the same track — their above/below-average colours
    // alone make the gap visible. Capped at half the value column's width
    // (.adv-pricing-gauge in advisors.css) rather than stretching full width.
    // Picks its markers from whichever price shape a finding's evidence
    // carries — pricing_gap has both sides of the gap, market_opportunity
    // just the one reachable price. Findings with no avg_price (overflow_risk,
    // idle_hauler, ...) render nothing.
    function _pricingRowHtml(f) {
      const ev = f.evidence;
      if (!ev.avg_price) return '';
      const avgPrice = ev.avg_price;
      const markers = (ev.player_price_cents != null && ev.npc_price_cents != null)
        ? [{ label: 'Your Price', price: ev.player_price_cents / 100 },
           { label: 'Their Price', price: ev.npc_price_cents / 100 }]
        : (ev.price != null ? [{ label: 'Their Price', price: ev.price }] : null);
      if (!markers) return '';

      const dots = markers.map(m => {
        const diff  = (m.price - avgPrice) / avgPrice * 100;
        const above = diff >= 0;
        const col   = above ? CHART_ACCENT : CHART_LOSS;
        // Clamped to ±50% so an extreme outlier price doesn't run its dot off the track.
        const pct = (50 + Math.max(-50, Math.min(50, diff))).toFixed(1);
        return { ...m, diff, above, col, pct };
      });
      const dotsHtml = dots.map(d => `<div class="adv-pricing-dot" style="left:${d.pct}%;background:${d.col};box-shadow:0 0 0.5rem ${d.col}"></div>`).join('');
      const legend = dots.map(d => `<span style="color:${d.col}">${d.label} ${d.price.toLocaleString()} Cr ${d.above ? '▲' : '▼'}${Math.abs(d.diff).toFixed(1)}%</span>`).join('')
        + `<span>Avg ${avgPrice.toLocaleString()} Cr</span>`;

      return `<div class="adv-ev-key">Pricing</div>
        <div class="adv-ev-val">
          <div class="adv-pricing-gauge">
            <div class="adv-pricing-track" style="background:linear-gradient(90deg,${CHART_LOSS}33,var(--outline) 50%,${CHART_ACCENT}33)">
              <div class="adv-pricing-mid"></div>
              ${dotsHtml}
            </div>
            <div class="adv-pricing-legend">${legend}</div>
          </div>
        </div>`;
    }

    // Buyer-row hover: how this station's buy price compares to the ware's
    // galaxy-average sell price (evidence.avg_price) — same skeleton as
    // cashflow-chart.js's avgPriceTipHtml (header + big figure w/ delta +
    // glowing gauge + reference rows), reused here so a siting card's hover
    // popovers read as siblings of the Economy tab's, not a lesser cousin.
    function _buyerTipHtml(b, avgPrice) {
      const diff  = avgPrice > 0 ? (b.price - avgPrice) / avgPrice * 100 : 0;
      const above = diff >= 0;
      const col   = above ? CHART_ACCENT : CHART_LOSS;
      const label = above ? '▲ ABOVE AVG' : '▼ BELOW AVG';
      // Gauge centred on the galaxy average, marker clamped to ±50% so an
      // extreme outlier price doesn't run the glow dot off the track.
      const clamped = Math.max(-50, Math.min(50, diff));
      const markerPct = (50 + clamped).toFixed(1);
      const gauge = avgPrice > 0
        ? `<div style="position:relative;height:0.5rem;background:linear-gradient(90deg,${CHART_LOSS}33,var(--outline) 50%,${CHART_ACCENT}33);border-radius:0.3rem;margin-bottom:0.6rem;overflow:visible">
             <div style="position:absolute;left:50%;top:-0.2rem;bottom:-0.2rem;width:1px;background:var(--text-brand)"></div>
             <div style="position:absolute;left:${markerPct}%;top:50%;width:0.7rem;height:0.7rem;border-radius:50%;background:${col};transform:translate(-50%,-50%);box-shadow:0 0 0.5rem ${col}"></div>
           </div>`
        : '';
      return `<div style="min-width:20rem;padding:0.2rem 0">
        <div style="display:flex;justify-content:space-between;align-items:baseline;gap:1.2rem;margin-bottom:0.6rem;padding-bottom:0.4rem;border-bottom:1px solid var(--outline)">
          <span style="color:var(--text-primary);font-size:1.1rem;letter-spacing:0.05em;text-transform:uppercase;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:16rem">${b.station_name}</span>
        </div>
        <div style="display:flex;align-items:baseline;justify-content:space-between;gap:1rem;margin-bottom:0.6rem">
          <span style="font-family:var(--font-data);font-size:1.8rem;color:${col};line-height:1">${b.price.toLocaleString()}<span style="font-size:1rem;color:var(--text-brand)"> cr/unit</span></span>
          ${avgPrice > 0 ? `<span style="color:${col};font-family:var(--font-data);font-size:1.1rem;white-space:nowrap">${label} ${Math.abs(diff).toFixed(1)}%</span>` : ''}
        </div>
        ${gauge}
        <div style="display:flex;justify-content:space-between;gap:1.2rem;padding:1px 0">
          <span style="color:var(--text-brand);font-size:1rem">Galaxy Average</span>
          <span style="color:var(--text-secondary);font-family:var(--font-data);font-size:1rem">${avgPrice > 0 ? avgPrice.toLocaleString() + ' Cr' : '—'}</span>
        </div>
        <div style="display:flex;justify-content:space-between;gap:1.2rem;padding:1px 0">
          <span style="color:var(--text-brand);font-size:1rem">Amount Wanted</span>
          <span style="color:var(--text-secondary);font-family:var(--font-data);font-size:1rem">${b.amount.toLocaleString()} units</span>
        </div>
      </div>`;
    }

    // Station siting's Buyers panel: one row per reachable NPC buy offer
    // behind that card's demand_depth figure — what they want and what
    // they're paying, so the aggregate number is auditable down to the
    // station that contributed it. Hovering a row pops the price-vs-average
    // gauge above instead of cramming it into the row itself. Clicking jumps
    // to that station's NPC inspector, same goToNpcStation() cross-tab jump
    // NPC_STATION_KEYS evidence rows use — a no-op if the buyer is outside
    // NPC_TRADE_RANGE_MAX_JUMPS of the player (see goToNpcStation's comment).
    function _buyersHtml(buyers, avgPrice) {
      if (!buyers || !buyers.length) {
        return `<div class="adv-ev-empty">No reachable buyers for this ware yet.</div>`;
      }
      const rows = buyers.map(b => `
          <div class="adv-buyer-row" data-buyer-tip="${encodeURIComponent(_buyerTipHtml(b, avgPrice))}" onclick="event.stopPropagation(); goToNpcStation('${b.station_id}')">
            <span class="adv-buyer-name">${b.station_name}</span>
            <span class="adv-buyer-amount">${b.amount.toLocaleString()} wanted</span>
            <span class="adv-buyer-price">${b.price.toLocaleString()} Cr/unit</span>
          </div>`).join('');
      return `<div class="adv-buyers">${rows}</div>`;
    }

    function render(f) {
      const isSiting = f.type === 'station_siting';
      // Siting is the only type with a Details/Buyers toggle — every other
      // finding renders its plain evidence grid as before.
      if (!isSiting) {
        // Station-link plumbing (the `code`/`station_code` a PLAYER_STATION_KEYS
        // row consumes) is only hidden when this finding actually carries the
        // matching station_id/homebase_id key — damaged_fleet's bare `code`
        // (a ship tag, no station link involved) is untouched by this.
        const codeKeys = Object.keys(f.evidence)
          .filter(k => PLAYER_STATION_KEYS[k])
          .map(k => PLAYER_STATION_KEYS[k].codeKey);
        const rows = Object.entries(f.evidence)
          .filter(([k]) => !HIDDEN_EVIDENCE_KEYS.has(k) && !codeKeys.includes(k))
          .map(([k, v]) => _evidenceRowHtml(f, k, v)).join('');
        return `<div class="adv-drawer">
            <div class="adv-evidence">${rows}${_pricingRowHtml(f)}</div>
          </div>`;
      }

      const view = _view.get(f.id) || 'details';
      const tab = (key, label) => `<button class="station-tab-btn ${view === key ? 'active' : ''}" `
        + `onclick="event.stopPropagation(); AdvisorsFeed.setEvidenceView('${f.id}', '${key}')">${label}</button>`;
      const tabs = `<div class="adv-ev-tabs">${tab('details', 'Details')}${tab('buyers', 'Buyers')}</div>`;

      if (view === 'buyers') {
        return `<div class="adv-drawer">${tabs}${_buyersHtml(f.evidence.buyers, f.evidence.avg_price)}</div>`;
      }
      // Details view: raw evidence grid, minus the buyer list (its own tab)
      // and avg_price (kept in evidence only to feed each buyer row's hover
      // gauge — see _buyerTipHtml — never shown as a flat Details row).
      const rows = Object.entries(f.evidence)
        .filter(([k]) => k !== 'buyers' && k !== 'avg_price')
        .map(([k, v]) => _evidenceRowHtml(f, k, v)).join('');
      return `<div class="adv-drawer">${tabs}
          <div class="adv-evidence">${rows}</div>
        </div>`;
    }

    // Buyer-row hover on station siting's Buyers panel: pre-rendered HTML,
    // decoded here (trendTip pattern from UI_STANDARDS §8). Both style resets
    // matter — the shared #hull-tip defaults to nowrap/alert-colour, which
    // multi-line content must override every show (another handler may have
    // run since).
    registerTip('buyerTip', (el, _e, tip) => {
      tip.innerHTML = decodeURIComponent(el.dataset.buyerTip);
      tip.style.color      = '';
      tip.style.whiteSpace = 'normal';
      return true;
    });

    return { render, setView, resetView };
  })();
