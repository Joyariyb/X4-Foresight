  // Core role: Central hover tooltip dispatcher for all interactive elements (hulls, equipment, charts).
  // Elements stamp data-*-tip attributes; this routes to matching *TipHtml() builders. Centralizing here
  // lets charts focus on their data, not tooltip rendering.
  (function() {
    const tip = document.getElementById('hull-tip');

    function moduleTipHtml(groups) {
      return `<div style="min-width:18rem;max-width:26rem;padding:0.2rem 0">` +
        groups.map(g =>
          `<div style="margin-bottom:0.8rem">
             <div style="font-size:0.9rem;letter-spacing:0.12em;text-transform:uppercase;
                         color:var(--text-faint);margin-bottom:0.4rem;padding-bottom:0.3rem;
                         border-bottom:1px solid var(--border)">${g.category}</div>
             ${g.items.map(([name, count]) =>
               `<div style="display:flex;justify-content:space-between;align-items:baseline;
                            gap:1.2rem;padding:1px 0">
                  <span style="color:var(--text-dim);font-size:1.1rem;white-space:nowrap;
                               overflow:hidden;text-overflow:ellipsis">${name}</span>
                  <span style="color:var(--text-faint);font-size:1rem;flex-shrink:0">×${count}</span>
                </div>`
             ).join('')}
           </div>`
        ).join('') +
      `</div>`;
    }

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
            ? `<span style="color:var(--text-dim);font-size:1rem;margin-right:0.8rem">${FACTION[e.race]}</span>` : '';
          return `<div style="display:flex;justify-content:space-between;align-items:baseline;gap:1.2rem;padding:1px 0">
                    <span style="color:var(--text-dim);font-size:1.1rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${e.name}${mk}</span>
                    <span style="flex-shrink:0;white-space:nowrap">${fac}<span style="color:var(--text-faint);font-size:1rem">×${e.count}</span></span>
                  </div>`;
        }).join('');
        return `<div style="margin-bottom:0.8rem">
                  <div style="font-size:0.9rem;letter-spacing:0.12em;text-transform:uppercase;color:var(--text-faint);margin-bottom:0.4rem;padding-bottom:0.3rem;border-bottom:1px solid var(--border)">${label}</div>
                  ${rows}
                </div>`;
      }).join('');
      return `<div style="min-width:20rem;max-width:28rem;padding:0.2rem 0">${sections || '—'}</div>`;
    }

    function weaponTipHtml(e) {
      // Weapon/turret stats hover — Compatibility + Price up top (no header),
      // then three sections named exactly what the real in-game tooltip
      // calls them: Weapon Damage Rate, Projectile, Heat. Every formula here
      // (including the beam-weapon ×4 shield quirk and the burst/sustained
      // split) was reverse-engineered and validated against real in-game
      // tooltips this session — see gamefiles/generate_equipment.py.

      const fmt = n => Math.round(n).toLocaleString();
      const km  = n => (n / 1000).toFixed(1) + ' km';
      const sp  = n => n >= 1e8 ? '1c' : fmt(n) + ' m/s';

      // In-Game vs True Stats (weaponStatsMode, toggled from designs-builder.js)
      // — only applies to the handful of fields the real tooltip DERIVES
      // (damage rates, rate of fire, cooldown/overheat): the game TRUNCATES
      // these rather than rounding them (confirmed this session against
      // several Cerberus Sentinel weapons — e.g. the M Beam's cooldown is a
      // true 8.882s, the game shows "8.8", we used to show a rounded "8.9").
      // True Stats shows the same raw value to 3dp with no truncation, for
      // checking the maths against generate_equipment.py's formulas. Price/
      // storage/hull integrity/range/speed are plain XML values the game
      // never rounds, so they always use fmt() above regardless of mode.
      const isTrue = weaponStatsMode === 'true';
      const dmg = n => isTrue
        ? n.toLocaleString(undefined, { minimumFractionDigits: 3, maximumFractionDigits: 3 })
        : Math.floor(n).toLocaleString();
      const truncFixed = (n, dp) => {
        const f = Math.pow(10, dp);
        return isTrue ? n.toFixed(3) : (Math.floor(n * f) / f).toFixed(dp);
      };

      // Missile/Standard/Advanced — a hypothesis from 2 confirmed data points
      // this session (every Argon-branded item checked said Standard, every
      // race-less "gen_" weapon said Advanced), not proven across the whole
      // catalog. Easy to revisit here without touching the data pipeline.
      const compat = (e.class === 'missileturret' || e.class === 'missilelauncher')
        ? 'Missile' : (e.race ? 'Standard' : 'Advanced');

      const row = (label, value, color) => value == null ? '' :
        `<div style="display:flex;justify-content:space-between;align-items:baseline;gap:1.4rem;padding:1px 0">
           <span style="color:var(--text-dim);font-size:1.1rem">${label}</span>
           <span style="font-family:var(--font-mono);font-size:1.1rem;white-space:nowrap${color ? `;color:${color}` : ''}">${value}</span>
         </div>`;

      const section = (icon, color, title, rows) => !rows ? '' :
        `<div style="margin:0.8rem 0 0.2rem">
           <div style="display:flex;align-items:center;gap:0.5rem;font-size:0.9rem;letter-spacing:0.12em;text-transform:uppercase;color:${color};margin-bottom:0.4rem;padding-bottom:0.3rem;border-bottom:1px solid var(--border)">
             <i class="ti ${icon}" style="font-size:1.1rem"></i>${title}
           </div>
           ${rows}
         </div>`;

      // weapon-slot items (player-aimed weapons/launchers) always show the
      // Burst/Sustained split, even when they're numerically equal (no heat
      // throttling) -- confirmed against the Ion Blasters, which have no
      // bullet heat data at all yet still show both lines in-game. Turret-
      // slot items show a single "Weapon Damage" line instead.
      let dmgRows = '';
      if (e.damage_rate_burst != null) {
        if (e.slot === 'weapon') {
          dmgRows += row('Burst Weapon Damage', `${dmg(e.damage_rate_burst)} MW`, 'var(--red)');
          dmgRows += row('Sustained Weapon Damage', `${dmg(e.damage_rate_sustained)} MW`, 'var(--amber)');
        } else {
          dmgRows += row('Weapon Damage', `${dmg(e.damage_rate_burst)} MW`, 'var(--red)');
        }
      }

      let projRows = '';
      projRows += row('Shield Damage', e.damage_shield != null ? `${dmg(e.damage_shield)} MJ` : null);
      projRows += row('Hull Damage (Shielded)', e.damage_hull != null ? `${dmg(e.damage_hull_while_shielded || 0)} MJ` : null);
      projRows += row('Hull Damage', e.damage_hull != null ? `${dmg(e.damage_hull)} MJ` : null);
      projRows += row('Effective Range', e.range_m != null ? km(e.range_m) : null);
      projRows += row('Projectile Speed', e.projectile_speed_m_s != null ? sp(e.projectile_speed_m_s) : null);

      let heatRows = '';
      heatRows += row('Rate of Fire', e.reload_rate != null ? `${truncFixed(e.reload_rate, 2)} /s` : null);
      heatRows += row('Rotation Speed', e.rotation_speed != null ? `${e.rotation_speed}°/s` : null);
      heatRows += row('Max Hull Integrity', e.hull_max != null ? `${fmt(e.hull_max)} MJ` : null);
      if (e.time_to_overheat != null) {
        // Time to Overheat is genuinely ship-dependent -- confirmed against
        // real tooltips this session: a ship's <modifiers><weapon heat=X/>
        // multiplies heat generation, shortening it proportionally, while
        // Sustained Weapon Damage and Cooldown Duration are unaffected.
        // _shipHeatFactor rides along in the data-weapon-tip payload from
        // designs-builder.js (the currently selected hull's factor, 1 if none).
        const heatFactor = e._shipHeatFactor || 1;
        heatRows += row('Time to Overheat', `${truncFixed(e.time_to_overheat / heatFactor, 1)} s`);
        heatRows += row('Cooldown Duration', `${truncFixed(e.cooldown_duration, 1)} s`);
      }

      return `<div style="min-width:21.5rem;max-width:28rem;padding:0.2rem 0">
        <div style="font-size:1.3rem;font-weight:600;color:var(--text);margin-bottom:0.2rem">${e.name}${e.mk ? ` Mk${e.mk}` : ''}</div>
        ${row('Compatibility', compat)}
        ${row('Storage Capacity', e.storage_capacity != null ? fmt(e.storage_capacity) : null)}
        ${row('Price', e.price_min != null ? `${fmt(e.price_min)}–${fmt(e.price_max)} Cr` : (e.price != null ? `${fmt(e.price)} Cr` : null))}
        ${section('ti-bolt', 'var(--red)', 'Weapon Damage Rate', dmgRows)}
        ${section('ti-target', 'var(--teal)', 'Projectile', projRows)}
        ${section('ti-flame', 'var(--amber)', 'Heat', heatRows)}
      </div>`;
    }

    function shieldTipHtml(e) {
      // Shield stats hover — same Compatibility/Price-up-top, sectioned-rows
      // layout as weaponTipHtml, but for shield fields (see generate_equipment.py's
      // shield branch). hull_max and disruption_stability are both absent on
      // "integrated" shields (no separate hitpoints to disrupt), so a missing
      // disruption_stability genuinely means "not resistant", not "no data".
      const fmt = n => Math.round(n).toLocaleString();
      const compat = e.race ? 'Standard' : 'Advanced';

      const row = (label, value, color) => value == null ? '' :
        `<div style="display:flex;justify-content:space-between;align-items:baseline;gap:1.4rem;padding:1px 0">
           <span style="color:var(--text-dim);font-size:1.1rem">${label}</span>
           <span style="font-family:var(--font-mono);font-size:1.1rem;white-space:nowrap${color ? `;color:${color}` : ''}">${value}</span>
         </div>`;

      const section = (icon, color, title, rows) => !rows ? '' :
        `<div style="margin:0.8rem 0 0.2rem">
           <div style="display:flex;align-items:center;gap:0.5rem;font-size:0.9rem;letter-spacing:0.12em;text-transform:uppercase;color:${color};margin-bottom:0.4rem;padding-bottom:0.3rem;border-bottom:1px solid var(--border)">
             <i class="ti ${icon}" style="font-size:1.1rem"></i>${title}
           </div>
           ${rows}
         </div>`;

      let chargeRows = '';
      chargeRows += row('Shield Capacity', e.capacity != null ? `${fmt(e.capacity)} MJ` : null);
      chargeRows += row('Recharge Rate', e.recharge_rate != null ? `${fmt(e.recharge_rate)} MJ/s` : null);
      chargeRows += row('Recharge Delay', e.recharge_delay != null ? `${e.recharge_delay.toFixed(1)} s` : null);
      if (e.capacity != null && e.recharge_rate) {
        chargeRows += row('Time to Full Recharge', `${(e.capacity / e.recharge_rate).toFixed(1)} s`);
      }

      // Reuses the same .badge.allied/.badge.atwar pill the rest of the app
      // already uses for green/red status (e.g. faction relations) instead of
      // inventing a new colour pairing.
      const resistant = e.disruption_stability != null;
      const integRows = row('Hull Integrity', e.hull_max != null ? `${fmt(e.hull_max)} MJ` : null) +
        `<div style="margin-top:0.5rem"><span class="badge ${resistant ? 'allied' : 'atwar'}">
           ${resistant ? `Disruptor Resistant (${e.disruption_stability})` : 'Not Disruptor Resistant'}
         </span></div>`;

      return `<div style="min-width:21.5rem;max-width:28rem;padding:0.2rem 0">
        <div style="font-size:1.3rem;font-weight:600;color:var(--text);margin-bottom:0.2rem">${e.name}${e.mk ? ` Mk${e.mk}` : ''}</div>
        ${row('Compatibility', compat)}
        ${row('Price', e.price_min != null ? `${fmt(e.price_min)}–${fmt(e.price_max)} Cr` : (e.price != null ? `${fmt(e.price)} Cr` : null))}
        ${section('ti-shield', 'var(--teal)', 'Shield Output', chargeRows)}
        ${section('ti-lock', 'var(--amber)', 'Integrity', integRows)}
      </div>`;
    }

    function engineTipHtml(e) {
      // Engine stats hover — same layout family as weaponTipHtml/shieldTipHtml.
      // boost_thrust/travel_thrust are MULTIPLIERS on thrust_forward (X4's own
      // convention, e.g. "x6.9"), not absolute kN, so they're shown distinctly
      // from the raw kN thrust figures rather than re-using fmt()+unit.
      // hull_max is absent on "integrated" engines (S/M/XS — no separate hull
      // to damage; see generate_equipment.py's engine branch), same convention
      // as shieldTipHtml's Integrity section.
      const fmt = n => Math.round(n).toLocaleString();
      const compat = e.race ? 'Standard' : 'Advanced';

      const row = (label, value, color) => value == null ? '' :
        `<div style="display:flex;justify-content:space-between;align-items:baseline;gap:1.4rem;padding:1px 0">
           <span style="color:var(--text-dim);font-size:1.1rem">${label}</span>
           <span style="font-family:var(--font-mono);font-size:1.1rem;white-space:nowrap${color ? `;color:${color}` : ''}">${value}</span>
         </div>`;

      const section = (icon, color, title, rows) => !rows ? '' :
        `<div style="margin:0.8rem 0 0.2rem">
           <div style="display:flex;align-items:center;gap:0.5rem;font-size:0.9rem;letter-spacing:0.12em;text-transform:uppercase;color:${color};margin-bottom:0.4rem;padding-bottom:0.3rem;border-bottom:1px solid var(--border)">
             <i class="ti ${icon}" style="font-size:1.1rem"></i>${title}
           </div>
           ${rows}
         </div>`;

      let thrustRows = '';
      thrustRows += row('Forward Thrust', e.thrust_forward != null ? `${fmt(e.thrust_forward)} kN` : null);
      thrustRows += row('Reverse Thrust', e.thrust_reverse != null ? `${fmt(e.thrust_reverse)} kN` : null);

      let boostRows = '';
      boostRows += row('Boost Thrust', e.boost_thrust != null ? `×${e.boost_thrust.toFixed(1)}` : null);
      boostRows += row('Duration', e.boost_duration != null ? `${e.boost_duration.toFixed(1)} s` : null);
      boostRows += row('Recharge', e.boost_recharge != null ? `${e.boost_recharge.toFixed(1)} s` : null);

      let travelRows = '';
      travelRows += row('Travel Thrust', e.travel_thrust != null ? `×${e.travel_thrust.toFixed(1)}` : null);
      travelRows += row('Charge Time', e.travel_charge != null ? `${e.travel_charge.toFixed(1)} s` : null);

      const integRows = row('Hull Integrity', e.hull_max != null ? `${fmt(e.hull_max)} MJ` : null);

      return `<div style="min-width:21.5rem;max-width:28rem;padding:0.2rem 0">
        <div style="font-size:1.3rem;font-weight:600;color:var(--text);margin-bottom:0.2rem">${e.name}${e.mk ? ` Mk${e.mk}` : ''}</div>
        ${row('Compatibility', compat)}
        ${row('Price', e.price_min != null ? `${fmt(e.price_min)}–${fmt(e.price_max)} Cr` : (e.price != null ? `${fmt(e.price)} Cr` : null))}
        ${section('ti-engine', 'var(--teal)', 'Thrust', thrustRows)}
        ${section('ti-rocket', 'var(--red)', 'Boost', boostRows)}
        ${section('ti-clock', 'var(--amber)', 'Travel', travelRows)}
        ${section('ti-lock', 'var(--green)', 'Integrity', integRows)}
      </div>`;
    }

    function budgetTipHtml(d) {
      // Per-slice economy tooltip: ware name in its colour, share of budget, the
      // amount × price = value figures, and which rule set the value (basis).
      const fmt = n => Math.round(n).toLocaleString();
      const BASIS = {
        'manual storage cap':    'Manual storage cap',
        'auto: 2h production':   'Automatic · 2h production',
        'auto: 2h consumption':  'Automatic · 2h consumption',
        'trade (max price)':     'Trade ware · max price',
        'buy order (unverified)':'Buy order',
      };
      return `<div style="min-width:20rem;padding:0.2rem 0">
        <div style="display:flex;justify-content:space-between;align-items:baseline;gap:1.2rem;margin-bottom:0.5rem">
          <span style="color:${d.colour};font-size:1.1rem;letter-spacing:0.06em;text-transform:uppercase;white-space:nowrap">${d.ware}</span>
          <span style="color:${d.colour};font-family:var(--font-mono);font-size:1.2rem">${d.pct}%</span>
        </div>
        <div style="display:flex;justify-content:space-between;gap:1.2rem;padding:1px 0">
          <span style="color:var(--text-faint);font-size:1rem">Amount × Price</span>
          <span style="color:var(--text-dim);font-family:var(--font-mono);font-size:1rem">${fmt(d.amount)} × ${fmt(d.price)}</span>
        </div>
        <div style="display:flex;justify-content:space-between;gap:1.2rem;padding:1px 0">
          <span style="color:var(--text-faint);font-size:1rem">Value</span>
          <span style="color:var(--lime);font-family:var(--font-mono);font-size:1.1rem">${fmt(d.value)} Cr</span>
        </div>
        <div style="margin-top:0.5rem;padding-top:0.4rem;border-top:1px solid var(--border);font-size:1rem;color:var(--text-faint)">${BASIS[d.basis] || d.basis}</div>
      </div>`;
    }

    function cashflowTipHtml(d) {
      // Cash-flow hover: one hour's trade breakdown — the hour's net at top,
      // then a row per ware (sells ▲ green, buys ▼ red) with units and credits.
      const fmtU = n => Math.round(n).toLocaleString();
      const fmtC = n => (n < 0 ? '−' : '+') + Math.abs(Math.round(n)).toLocaleString();
      const span = d.hAgo === 0 ? 'Past hour' : `${d.hAgo}–${d.hAgo + 1}h ago`;
      const MAX = 8;
      const shown = d.rows.slice(0, MAX);
      const more  = d.rows.length - shown.length;
      return `<div style="min-width:23rem;padding:0.2rem 0">
        <div style="display:flex;justify-content:space-between;align-items:baseline;gap:1.2rem;margin-bottom:0.5rem;padding-bottom:0.4rem;border-bottom:1px solid var(--border)">
          <span style="color:var(--text-faint);font-size:1rem;letter-spacing:0.08em;text-transform:uppercase">${span}</span>
          <span style="color:${d.net >= 0 ? '#19e6c8' : '#ef5350'};font-family:var(--font-mono);font-size:1.1rem">${fmtC(d.net)} Cr</span>
        </div>` +
        shown.map(r => `
          <div style="display:flex;justify-content:space-between;align-items:baseline;gap:1.2rem;padding:1px 0">
            <span style="font-size:1rem;letter-spacing:0.04em;text-transform:uppercase;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:13rem;color:${r.colour}">
              <span style="color:${r.dir === 'sell' ? '#19e6c8' : '#ef5350'}">${r.dir === 'sell' ? '▲' : '▼'}</span> ${r.ware}
            </span>
            <span style="font-family:var(--font-mono);font-size:1rem;color:var(--text-dim);flex-shrink:0;white-space:nowrap">
              ${fmtU(r.units)}u · <span style="color:${r.cr >= 0 ? '#19e6c8' : '#ef5350'}">${fmtC(r.cr)}</span>
            </span>
          </div>`).join('') +
        (more > 0 ? `<div style="margin-top:0.4rem;font-size:1rem;color:var(--text-faint)">+${more} more ware${more > 1 ? 's' : ''}</div>` : '') +
      `</div>`;
    }

    function cashflowTradeTipHtml(d) {
      // By-Trade hover: one individual trade's full details + the running total.
      const fmtU = n => Math.round(n).toLocaleString();
      const fmtC = n => (n < 0 ? '−' : '+') + Math.abs(Math.round(n)).toLocaleString();
      const ago  = d.hAgo < 1 ? Math.round(d.hAgo * 60) + 'm ago'
                              : d.hAgo.toFixed(1).replace(/\.0$/, '') + 'h ago';
      // The trade has two "other side" fields: counterparty (the station the
      // goods went to / came from — the scanner resolves this for almost all
      // sells) and ship (the transport, resolved for most buys but often a
      // transient NPC buyer whose ID is a raw "[0x…]" hex on sells). Show the
      // station as the buyer/seller and the transport as the ship; fall back to
      // "Unknown" only when neither resolves.
      const isRawId = s => /^\[?0x[0-9a-f]+\]?$/i.test(String(s).trim());
      const shipResolved = d.ship && !isRawId(d.ship);
      const partyLabel   = d.dir === 'sell' ? 'Buyer' : 'Seller';
      const row = (label, value, colour) => `
        <div style="display:flex;justify-content:space-between;gap:1.2rem;padding:1px 0">
          <span style="color:var(--text-faint);font-size:1rem">${label}</span>
          <span style="color:${colour || 'var(--text-dim)'};font-family:var(--font-mono);font-size:1rem;text-align:right">${value}</span>
        </div>`;
      return `<div style="min-width:22rem;padding:0.2rem 0">
        <div style="display:flex;justify-content:space-between;align-items:baseline;gap:1.2rem;margin-bottom:0.5rem;padding-bottom:0.4rem;border-bottom:1px solid var(--border)">
          <span style="color:${d.colour};font-size:1.1rem;letter-spacing:0.05em;text-transform:uppercase;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:16rem">
            <span style="color:${d.dir === 'sell' ? '#19e6c8' : '#ef5350'}">${d.dir === 'sell' ? '▲ SOLD' : '▼ BOUGHT'}</span> ${d.ware}
          </span>
        </div>` +
        row('Amount × Price', `${fmtU(d.units)} × ${fmtU(d.priceEa)} Cr`) +
        row('Trade value', `${fmtC(d.total)} Cr`, d.total >= 0 ? '#19e6c8' : '#ef5350') +
        (d.counterparty ? row(partyLabel, d.counterparty) : '') +
        (shipResolved   ? row('Ship', d.ship) : '') +
        (!d.counterparty && !shipResolved ? row(partyLabel, 'Unknown') : '') +
        `<div style="margin-top:0.5rem;padding-top:0.4rem;border-top:1px solid var(--border);text-align:right;font-size:1rem;color:var(--text-faint)">${ago}</div>
      </div>`;
    }

    function wareChartTipHtml(d) {
      // By-Ware hover: the ware, its exact price, where that price sits in
      // the game's min–avg–max band, the quantity, and the trade's counterparty.
      // d.dir ('sell'|'buy') controls the direction label and counterparty role.
      const fmtU = n => Math.round(n).toLocaleString();
      const ago  = d.hAgo < 1
        ? Math.round(d.hAgo * 60) + 'm ago'
        : d.hAgo.toFixed(1).replace(/\.0$/, '') + 'h ago';

      // Express the price relative to the ware's average: +12% above or −5% below.
      const diff    = d.price - d.pAvg;
      const diffPct = d.pAvg > 0 ? Math.round(Math.abs(diff) / d.pAvg * 100) : 0;
      const diffCol = diff >= 0 ? '#19e6c8' : '#ef5350';
      const diffStr = diff === 0
        ? 'at avg'
        : `${diff > 0 ? '+' : '−'}${diffPct}% vs avg`;

      const isRawId = s => /^\[?0x[0-9a-f]+\]?$/i.test(String(s).trim());
      const shipResolved = d.ship && !isRawId(d.ship);

      const row = (label, value, colour) => `
        <div style="display:flex;justify-content:space-between;gap:1.2rem;padding:1px 0">
          <span style="color:var(--text-faint);font-size:1rem">${label}</span>
          <span style="color:${colour || 'var(--text-dim)'};font-family:var(--font-mono);font-size:1rem;text-align:right">${value}</span>
        </div>`;

      return `<div style="min-width:22rem;padding:0.2rem 0">
        <div style="display:flex;justify-content:space-between;align-items:baseline;gap:1.2rem;
                    margin-bottom:0.5rem;padding-bottom:0.4rem;border-bottom:1px solid var(--border)">
          <span style="color:${d.colour};font-size:1.1rem;letter-spacing:0.05em;text-transform:uppercase;
                       white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:18rem">
            <span style="color:${d.dir === 'buy' ? '#ef5350' : '#19e6c8'}">${d.dir === 'buy' ? '▼ BOUGHT' : '▲ SOLD'}</span> ${d.ware}
          </span>
        </div>` +
        row('Price',      `${fmtU(d.price)} Cr`) +
        row('vs Average', diffStr, diffCol) +
        row('Band',       `${fmtU(d.pMin)} – ${fmtU(d.pMax)} Cr`) +
        row('Amount',     `${fmtU(d.amount)} units`) +
        (d.counterparty ? row(d.dir === 'buy' ? 'Seller' : 'Buyer', d.counterparty) : '') +
        (shipResolved   ? row('Ship',  d.ship)         : '') +
        `<div style="margin-top:0.5rem;padding-top:0.4rem;border-top:1px solid var(--border);
                     text-align:right;font-size:1rem;color:var(--text-faint)">${ago}</div>
      </div>`;
    }

    function avgPriceTipHtml(d) {
      // Avg Price hover: the hour's mean price (big), how it moved vs the
      // previous traded hour (teal ▲ / red ▼), the min–max spread that hour as a
      // little band with a glowing marker at the average, and the trade count.
      const fmtU = n => Math.round(n).toLocaleString();
      const span = d.hAgo === 0 ? 'Past hour' : `${d.hAgo}–${d.hAgo + 1}h ago`;
      const dirLabel = d.dir === 'sell' ? '▲ SOLD' : '▼ BOUGHT';
      const dirCol   = d.dir === 'sell' ? '#19e6c8' : '#ef5350';

      // Delta vs the previous populated hour.
      let deltaHtml = `<span style="color:var(--text-faint);font-size:1rem">first hour</span>`;
      if (d.prevAvg != null && d.prevAvg > 0) {
        const diff = d.avg - d.prevAvg;
        const pct  = Math.abs(diff / d.prevAvg * 100);
        const flat = Math.abs(diff) < 0.005 * d.prevAvg;
        const c    = flat ? 'var(--text-faint)' : diff > 0 ? '#19e6c8' : '#ef5350';
        const ch   = flat ? '▬' : diff > 0 ? '▲' : '▼';
        deltaHtml  = `<span style="color:${c};font-family:var(--font-mono);font-size:1.1rem">${ch} ${pct.toFixed(1)}%</span>`;
      }

      // Marker position within the hour's min–max range (clamped).
      const range   = (d.max - d.min) || 1;
      const avgFrac = Math.max(0, Math.min(1, (d.avg - d.min) / range)) * 100;
      const spread  = d.max > d.min
        ? `<div style="display:flex;justify-content:space-between;font-size:0.9rem;color:var(--text-faint);font-family:var(--font-mono);margin-bottom:0.2rem">
             <span>${fmtU(d.min)}</span><span style="letter-spacing:0.12em">SPREAD</span><span>${fmtU(d.max)}</span>
           </div>
           <div style="position:relative;height:0.5rem;background:${d.colour}22;border-radius:0.3rem;margin-bottom:0.6rem;overflow:visible">
             <div style="position:absolute;inset:0;background:linear-gradient(90deg,${d.colour}33,${d.colour}66);border-radius:0.3rem"></div>
             <div style="position:absolute;left:${avgFrac.toFixed(1)}%;top:50%;width:0.7rem;height:0.7rem;border-radius:50%;background:${d.colour};transform:translate(-50%,-50%);box-shadow:0 0 0.5rem ${d.colour}"></div>
           </div>`
        : `<div style="font-size:0.9rem;color:var(--text-faint);font-family:var(--font-mono);margin-bottom:0.6rem">single trade · no spread</div>`;

      return `<div style="min-width:21rem;padding:0.2rem 0">
        <div style="display:flex;justify-content:space-between;align-items:baseline;gap:1.2rem;margin-bottom:0.6rem;padding-bottom:0.4rem;border-bottom:1px solid var(--border)">
          <span style="color:${d.colour};font-size:1.1rem;letter-spacing:0.05em;text-transform:uppercase;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:16rem">
            <span style="color:${dirCol}">${dirLabel}</span> ${d.ware}
          </span>
          <span style="color:var(--text-faint);font-size:1rem;letter-spacing:0.06em;white-space:nowrap">${span}</span>
        </div>
        <div style="display:flex;align-items:baseline;justify-content:space-between;gap:1rem;margin-bottom:0.7rem">
          <span style="font-family:var(--font-mono);font-size:1.8rem;color:${d.colour};line-height:1">${fmtU(d.avg)}<span style="font-size:1rem;color:var(--text-faint)"> cr avg</span></span>
          ${deltaHtml}
        </div>
        ${spread}
        <div style="display:flex;justify-content:space-between;gap:1.2rem">
          <span style="color:var(--text-faint);font-size:1rem">Trades this hour</span>
          <span style="color:var(--text-dim);font-family:var(--font-mono);font-size:1rem">${d.count}</span>
        </div>
      </div>`;
    }

    function storageTipHtml(types) {
      // Renders each storage type as a label + % row followed by a fill bar.
      // Label, percentage, and m³ text all use the category's fixed accent colour.
      // The Total row is preceded by a thin separator line.
      const fmtM3 = v => v >= 1e6 ? (v/1e6).toFixed(2)+'M' : v >= 1e3 ? (v/1e3).toFixed(1)+'K' : v;
      return `<div style="min-width:22rem;padding:0.2rem 0">` +
        types.map(t => {
          const barW = t.pct != null ? Math.min(t.pct, 100) : 0;
          const pctLabel = t.pct != null ? `${t.pct}%` : '—';
          const sub = (t.m3 != null && t.max != null)
            ? `<div style="margin-top:0.2rem;text-align:right;font-size:1rem;color:${t.color};opacity:0.75">${fmtM3(t.m3)} / ${fmtM3(t.max)} m³</div>`
            : '';
          const sep = t.isTotal
            ? `<div style="border-top:1px solid var(--border);margin:0.5rem 0 0.8rem"></div>`
            : '';
          return `${sep}<div style="margin-bottom:0.8rem">
            <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:0.3rem">
              <span style="font-size:1rem;letter-spacing:0.1em;text-transform:uppercase;color:${t.color}">${t.label}</span>
              <span style="color:${t.color};font-family:var(--font-mono);margin-left:1.2rem">${pctLabel}</span>
            </div>
            <div style="height:0.6rem;background:var(--border);border-radius:0.2rem;overflow:hidden">
              <div style="height:100%;width:${barW}%;background:${t.color};border-radius:0.2rem"></div>
            </div>
            ${sub}
          </div>`;
        }).join('') +
      `</div>`;
    }

    document.addEventListener('mousemove', function(e) {
      // Clear all chart highlight rings at the start of each move; whichever
      // chart the cursor is over will re-show its own ring below.
      document.querySelectorAll('.cf-detail-marker,.cf-ware-marker').forEach(m => { m.style.display = 'none'; });
      // Clear Avg Price bar highlight + readout line (reapplied below if hovered).
      document.querySelectorAll('.avg-bars rect.avg-hot').forEach(r => r.classList.remove('avg-hot'));
      document.querySelectorAll('.avg-hot-line').forEach(l => { l.style.opacity = '0'; });

      const el = e.target.closest('[data-hull-tip],[data-pilot-skills],[data-storage-tip],[data-modules-tip],[data-loadout-tip],[data-weapon-tip],[data-fleet-tip],[data-budget-tip],[data-cashflow-tip],[data-cfdetail],[data-cfware],[data-avgtip]');
      if (!el) { tip.style.display = 'none'; return; }

      if (el.dataset.cfdetail) {
        // By-Trade chart: find the trade nearest the cursor's x position and
        // show its details, with the highlight ring snapped to that point.
        const arr = cashflowDetailData[el.dataset.cfdetail];
        if (!arr || !arr.length) { tip.style.display = 'none'; return; }
        const r = el.getBoundingClientRect();
        const f = (e.clientX - r.left) / r.width;
        let best = arr[0], bd = Infinity;
        for (const p of arr) { const dd = Math.abs(p.fx - f); if (dd < bd) { bd = dd; best = p; } }
        tip.innerHTML = cashflowTradeTipHtml(best);
        tip.style.color = '';
        tip.style.whiteSpace = 'normal';
        const svg = el.closest('svg');
        const mk = svg && svg.querySelector('.cf-detail-marker');
        if (mk) { mk.setAttribute('cx', best.vbx); mk.setAttribute('cy', best.vby); mk.style.display = 'block'; }
      } else if (el.dataset.cfware) {
        // By-Ware chart: find the nearest visible trade dot by Euclidean distance
        // so the cursor naturally locks on to whichever ware line it is closest to.
        const sc  = el.dataset.cfware;
        const arr = wareChartData[sc];
        if (!arr || !arr.length) { tip.style.display = 'none'; return; }
        const r  = el.getBoundingClientRect();
        const fx = (e.clientX - r.left) / r.width;
        const fy = (e.clientY - r.top)  / r.height;
        let best = null, bd = Infinity;
        for (const p of arr) {
          // Skip points belonging to wares the user has toggled off.
          if (wareVisibility[sc] && wareVisibility[sc][p.ware] === false) continue;
          const dd = (p.fx - fx) ** 2 + (p.fy - fy) ** 2;
          if (dd < bd) { bd = dd; best = p; }
        }
        if (!best) { tip.style.display = 'none'; return; }
        tip.innerHTML = wareChartTipHtml(best);
        tip.style.color = '';
        tip.style.whiteSpace = 'normal';
        const svg = el.closest('svg');
        const mk  = svg && svg.querySelector('.cf-ware-marker');
        if (mk) {
          mk.setAttribute('cx', best.vbx);
          mk.setAttribute('cy', best.vby);
          mk.setAttribute('stroke', best.colour);
          mk.style.display = 'block';
        }
      } else if (el.dataset.cashflowTip) {
        // Cash-flow chart: one hour's per-ware trade breakdown
        tip.innerHTML = cashflowTipHtml(JSON.parse(decodeURIComponent(el.dataset.cashflowTip)));
        tip.style.color      = '';
        tip.style.whiteSpace = 'normal';
      } else if (el.dataset.avgtip) {
        // Avg Price chart: hour stats + highlight the bar and project a dashed
        // readout line from its top across to the price axis.
        const d = JSON.parse(decodeURIComponent(el.dataset.avgtip));
        tip.innerHTML       = avgPriceTipHtml(d);
        tip.style.color     = '';
        tip.style.whiteSpace = 'normal';
        const svg  = el.closest('svg');
        const bars = svg && svg.querySelector('.avg-bars');
        const bar  = bars && bars.children[+el.dataset.avgI];
        if (bar) {
          bar.classList.add('avg-hot');
          const y  = +bar.getAttribute('y');
          const cx = +bar.getAttribute('x') + (+bar.getAttribute('width')) / 2;
          const line = svg.querySelector('.avg-hot-line');
          if (line) {
            line.setAttribute('x1', 56); // ml — the price axis
            line.setAttribute('x2', cx.toFixed(1));
            line.setAttribute('y1', y.toFixed(1));
            line.setAttribute('y2', y.toFixed(1));
            line.setAttribute('stroke', d.colour);
            line.style.opacity = '1';
          }
        }
      } else if (el.dataset.budgetTip) {
        // Economy pie slice: ware share, figures, and basis
        tip.innerHTML = budgetTipHtml(JSON.parse(decodeURIComponent(el.dataset.budgetTip)));
        tip.style.color      = '';
        tip.style.whiteSpace = 'normal';
      } else if (el.dataset.pilotSkills) {
        // Pilot skills: name header + per-skill star rows.
        // data-pilot-name is the pilot's display name (moved off the row).
        tip.innerHTML = pilotTipHtml(JSON.parse(el.dataset.pilotSkills), el.dataset.pilotName || '');
        tip.style.color      = '';
        tip.style.whiteSpace = 'nowrap';
      } else if (el.dataset.storageTip) {
        // Storage breakdown: one bar row per container type
        tip.innerHTML = storageTipHtml(JSON.parse(decodeURIComponent(el.dataset.storageTip)));
        tip.style.color      = '';
        tip.style.whiteSpace = 'normal';
      } else if (el.dataset.modulesTip) {
        // Module list: grouped by category with counts
        tip.innerHTML = moduleTipHtml(JSON.parse(decodeURIComponent(el.dataset.modulesTip)));
        tip.style.color      = '';
        tip.style.whiteSpace = 'normal';
      } else if (el.dataset.loadoutTip) {
        // Ship equipment: grouped by slot with faction + counts
        tip.innerHTML = loadoutTipHtml(JSON.parse(decodeURIComponent(el.dataset.loadoutTip)));
        tip.style.color      = '';
        tip.style.whiteSpace = 'normal';
      } else if (el.dataset.weaponTip) {
        // Ship Builder weapon/turret/shield/engine row: full stat hover.
        // Shield/engine payloads route to their own *TipHtml — same
        // data-weapon-tip attribute, just a different field set per e.slot.
        const payload = JSON.parse(decodeURIComponent(el.dataset.weaponTip));
        tip.innerHTML = payload.slot === 'shield' ? shieldTipHtml(payload)
          : payload.slot === 'engine' ? engineTipHtml(payload)
          : weaponTipHtml(payload);
        tip.style.color      = '';
        tip.style.whiteSpace = 'normal';
      } else if (el.dataset.fleetTip) {
        // Assigned fleet breakdown: pre-rendered HTML encoded into the attribute
        tip.innerHTML = decodeURIComponent(el.dataset.fleetTip);
        tip.style.color      = '';
        tip.style.whiteSpace = 'normal';
      } else {
        // Hull bar: plain coloured text
        tip.textContent      = el.dataset.hullTip;
        tip.style.color      = el.dataset.hullColor || '';
        tip.style.whiteSpace = 'nowrap';
      }

      tip.style.display = 'block';
      const x = Math.min(e.clientX + 14, window.innerWidth - tip.offsetWidth - 8);
      const y = Math.max(e.clientY - 32, 8);
      tip.style.left = x + 'px';
      tip.style.top  = y + 'px';
    });
    document.addEventListener('mouseleave', function() { tip.style.display = 'none'; });

    // ── Scrubber zoom + pan drag handler ──────────────────────────────────────
    // Mousedown on the handle body starts a pan; on either edge grip starts a
    // resize.  mousemove / mouseup are on the document so drags that leave the
    // element are not interrupted.
    (function() {
      document.addEventListener('mousedown', function(e) {
        const resizeEl = e.target.closest('.cf-scrubber-resize[data-side]');
        const handleEl = !resizeEl && e.target.closest('.cf-scrubber-handle');
        const trackEl  = e.target.closest('[data-scrubber]');
        // Only act when the click was inside a known scrubber part.
        if (!trackEl || (!resizeEl && !handleEl)) return;

        const safeCode = trackEl.dataset.scrubber;
        if (!cfZoom[safeCode]) return;
        const { hours, offsetHours } = cfZoom[safeCode];

        cfScrubDrag = {
          safeCode,
          // 'pan' moves both edges; 'resize-left'/'resize-right' moves one edge.
          mode:       resizeEl ? (resizeEl.dataset.side === 'left' ? 'resize-left' : 'resize-right') : 'pan',
          startX:     e.clientX,
          startHours: hours,
          startOff:   offsetHours,
          trackW:     trackEl.getBoundingClientRect().width,
          _raf:       false,
        };
        e.preventDefault(); // prevent text selection during drag
      });

      document.addEventListener('mousemove', function(e) {
        if (!cfScrubDrag) return;
        const { safeCode, mode, startX, startHours, startOff, trackW } = cfScrubDrag;
        // Convert mouse delta (px) to hours using the track's current width.
        const dH = (e.clientX - startX) / trackW * CF_MAX_HOURS;

        let newH = startHours, newOff = startOff;
        if (mode === 'pan') {
          // Both edges shift by the same amount.
          // Dragging right → toward NOW → offset decreases.
          newOff = startOff - dH;
        } else if (mode === 'resize-left') {
          // Left edge moves, right edge (= offsetHours) is fixed.
          // Dragging right → window shrinks; left → grows.
          newH = startHours - dH;
        } else {
          // resize-right: right edge moves, left edge position is fixed.
          // Fixed left = startOff + startHours, so offset = leftFixed - newH.
          newH   = startHours  + dH;
          newOff = startOff    - dH;
        }

        // Clamp window width and offset so nothing goes out of range.
        newH   = Math.max(CF_MIN_HOURS, Math.min(CF_MAX_HOURS, newH));
        newOff = Math.max(0, Math.min(CF_MAX_HOURS - newH, newOff));
        cfZoom[safeCode] = { hours: newH, offsetHours: newOff };

        // Fast-path: update the handle geometry immediately so the track feels
        // responsive even before the full rAF chart rebuild completes.
        const track = document.querySelector(`[data-scrubber="${safeCode}"]`);
        if (track) {
          const handle = track.querySelector('.cf-scrubber-handle');
          if (handle) {
            handle.style.left  = ((CF_MAX_HOURS - newOff - newH) / CF_MAX_HOURS * 100).toFixed(2) + '%';
            handle.style.width = (newH / CF_MAX_HOURS * 100).toFixed(2) + '%';
          }
        }

        // Throttle chart rebuilds to one per animation frame so intermediate
        // mouse events don't pile up and cause jank.
        if (!cfScrubDrag._raf) {
          cfScrubDrag._raf = true;
          requestAnimationFrame(function() {
            if (cfScrubDrag) { cfScrubDrag._raf = false; rebuildCfChart(safeCode); }
          });
        }
      });

      document.addEventListener('mouseup', function() {
        if (cfScrubDrag) {
          // One final rebuild on release to guarantee the chart matches the
          // handle's resting position even if the last rAF fired early.
          rebuildCfChart(cfScrubDrag.safeCode);
          cfScrubDrag = null;
        }
      });
    })();
  })();
