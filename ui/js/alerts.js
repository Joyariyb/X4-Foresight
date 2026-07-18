  // Core role: Derives the Alerts tab's tiles and the sidebar alert badge from advisor findings and raw scan health data.

  // Extracted from populate() so the derivation rules (which findings become
  // alerts, the red/amber thresholds) and the tile rendering live side by side
  // instead of 1,000 lines apart. populate() passes `waiting` in rather than
  // this file re-filtering it, so "what counts as a waiting ship" keeps a
  // single definition (the Overview's Waiting card uses the same list).
  function renderAlerts(data, waiting) {
    const stations = data.stations || [];

    // Hostile Presence / Force Build-Up — sourced from the Military advisor
    // findings (db/advisors/military.py) rather than a separate hull-origin
    // check, so the "is this actually a threat" force comparison (theirs vs.
    // the player's, per sector) lives in one place. 'Covered' verdicts mean
    // the player's present force there already wins that fight, so those are
    // excluded — only sectors where the hostiles are at least a threat.
    const militaryFindings = ((data.advisors || {}).findings || [])
      .filter(f => f.domain === "military");
    const hostilePresence = militaryFindings.filter(f =>
      f.type === "hostile_presence" && f.slots.verdict !== "Covered");
    const buildups = militaryFindings.filter(f => f.type === "buildup");
    const compositionGaps = militaryFindings.filter(f => f.type === "composition_gap");
    const outranged = militaryFindings.filter(f => f.type === "outranged");
    const damagedFleet = militaryFindings.filter(f => f.type === "damaged_fleet");

    // Storage Overflow — sourced from the Economic advisor's overflow_risk
    // findings (db/advisors/economy.py's overflow_risk_findings()), same
    // hand-off pattern as the military-sourced alerts above: this is the
    // single source of truth for "a station's about to cap out on a ware",
    // so no separate raw cargo-percentage check belongs here. The advisor's
    // own window (OVERFLOW_HOURS_THRESHOLD, 5h) is "worth mentioning";
    // Alerts narrows further to OVERFLOW_ALERT_HOURS since game hours track
    // real hours 1:1 here and this tab is for "needs attention now".
    const OVERFLOW_ALERT_HOURS = 1;
    const OVERFLOW_ALERT_RED_HOURS = 0.5;
    const storageOverflow = ((data.advisors || {}).findings || [])
      .filter(f => f.domain === "economy" && f.type === "overflow_risk"
        && f.slots.hours <= OVERFLOW_ALERT_HOURS);

    // Stranded Deliveries — sourced from the Trader advisor's stranded_delivery
    // findings (db/advisors/trader.py's stranded_delivery_findings()): a ship
    // has been holding pickup cargo past STRANDED_HOURS_THRESHOLD with no
    // delivery destination assigned. Single source of truth like the other
    // advisor-backed alerts above — no separate raw-order check here.
    const strandedDeliveries = ((data.advisors || {}).findings || [])
      .filter(f => f.domain === "trader" && f.type === "stranded_delivery");

    // Station Damaged / Under Attack — sourced straight from data.stations[]
    // (export/jsonexport.py's _stations(), the stations table's hull/shield_pct
    // columns), not an advisor finding: this is raw scan health data, no
    // trend or force-comparison reasoning behind it. Under Construction is
    // excluded since a new build's hull naturally starts below 100% and
    // that's not damage. Shields collapsed to near-zero (while the station
    // actually has a hull to protect) flags fire happening *right now*,
    // ahead of hull_pct dropping on the next scan.
    const STATION_HULL_RED_PCT = 60;
    const STATION_HULL_AMBER_PCT = 90;
    const STATION_SHIELD_NEAR_ZERO_PCT = 5;
    const damagedStationsRed = [];
    const damagedStationsAmber = [];
    stations.filter(s => s.status !== "Under Construction").forEach(s => {
      const underFire = s.hull_max > 0 && s.shield_pct != null && s.shield_pct <= STATION_SHIELD_NEAR_ZERO_PCT;
      if (underFire || (s.hull_pct != null && s.hull_pct < STATION_HULL_RED_PCT)) {
        damagedStationsRed.push(s);
      } else if (s.hull_pct != null && s.hull_pct < STATION_HULL_AMBER_PCT) {
        damagedStationsAmber.push(s);
      }
    });
    const stationDamageActive = damagedStationsRed.length > 0 || damagedStationsAmber.length > 0;

    // Production Stalling — read straight from data.stations[].production_runtimes
    // (export/jsonexport.py's _stations(), computed by production_analytics_from_modules()
    // in data/production.py), same raw-scan-data pattern as Station Damaged above:
    // no advisor finding backs this, it's a direct read of numbers the scanner
    // already computed. `minutes` (runtime_minutes) is null for wares with no
    // inputs (e.g. Energy Cells — never alerts) and 0 means the limiting input is
    // already out of stock. `time_to_cap_hours` is null unless the ware has a
    // positive surplus AND cargo data was available, and 0 means the bay is
    // already full with nowhere for output to go. Either already-halted case
    // renders red; landing within PRODUCTION_STALL_AMBER_HOURS of either limit
    // renders amber. This deliberately overlaps the Storage Overflow alert below
    // on the cap side (different, tighter threshold here) — Storage Overflow only
    // fires when the ware has NPC market value, so a valueless ware stalling out
    // would otherwise never surface.
    const PRODUCTION_STALL_AMBER_HOURS = 1.5;
    const stallsByStation = new Map(); // station code -> { red: [wareName...], amber: [...] }
    stations.forEach(s => {
      const runtimes = s.production_runtimes || {};
      Object.entries(runtimes).forEach(([wareName, r]) => {
        const minutesHalted = r.minutes === 0;
        const capHalted = r.time_to_cap_hours === 0;
        const minutesSoon = r.minutes != null && r.minutes > 0 && r.minutes <= PRODUCTION_STALL_AMBER_HOURS * 60;
        const capSoon = r.time_to_cap_hours != null && r.time_to_cap_hours > 0 && r.time_to_cap_hours <= PRODUCTION_STALL_AMBER_HOURS;
        if (!(minutesHalted || capHalted || minutesSoon || capSoon)) return;
        if (!stallsByStation.has(s.code)) stallsByStation.set(s.code, { red: [], amber: [] });
        stallsByStation.get(s.code)[(minutesHalted || capHalted) ? "red" : "amber"].push(wareName);
      });
    });

    // Input Starvation — read straight from data.stations[].input_rates
    // (export/jsonexport.py's _stations(), computed by input_rates_from_modules()
    // in data/production.py). Keyed by CONSUMED ware rather than produced ware
    // like Production Stalling above: this is the station's true combined draw
    // on each raw input across every production line sharing it, not just one
    // line's own consumption, so it also catches shared-input depletion that
    // Production Stalling's per-produced-ware runway can be optimistic about.
    // input_rates is {} on scans from before the station_input_rates table
    // existed, so this naturally no-ops on those rather than needing a
    // separate guard.
    const INPUT_STARVATION_RED_HOURS = 2;
    const INPUT_STARVATION_AMBER_HOURS = 6;
    const starvedByStation = new Map(); // station code -> { red: [wareName (Nh)...], amber: [...] }
    stations.forEach(s => {
      const rates = s.input_rates || {};
      Object.entries(rates).forEach(([wareName, r]) => {
        if (r.runtime_hours == null || r.runtime_hours >= INPUT_STARVATION_AMBER_HOURS) return;
        const sev = r.runtime_hours < INPUT_STARVATION_RED_HOURS ? "red" : "amber";
        if (!starvedByStation.has(s.code)) starvedByStation.set(s.code, { red: [], amber: [] });
        starvedByStation.get(s.code)[sev].push(`${wareName} (${r.runtime_hours.toFixed(1)}h)`);
      });
    });

    // Station Underfunded — read straight from data.stations[].account_amount vs
    // budget.total (export/jsonexport.py's _stations(); budget.total comes from
    // estimate_station_budget() in scanner/budget.py, roughly 2h of the station's
    // own input costs), same raw-scan-data pattern as Station Damaged/Production
    // Stalling/Input Starvation above — no advisor finding backs this. A station
    // with budget.total == 0 (nothing to restock, e.g. a pure-output shipyard)
    // can't be "underfunded" by this measure, so it's excluded rather than
    // flagged against a zero threshold. Below ~10% of budget means the account
    // can't cover even one more restock cycle.
    const STATION_UNDERFUNDED_PCT = 0.10;
    const underfundedStations = stations.filter(s => {
      const total = (s.budget || {}).total || 0;
      return total > 0 && s.account_amount != null && s.account_amount < total * STATION_UNDERFUNDED_PCT;
    });

    // Under-Equipped Ships — read straight from data.ships[] (export/jsonexport.py's
    // _ships(): `hardpoints` is the hull's slot layout {type: {size: count}} from
    // SHIP_STATS, `loadout` is what's actually fitted), same raw-scan-data pattern
    // as Station Damaged/Underfunded above — no advisor finding backs this, it's a
    // straight hardpoints-vs-loadout comparison. Restricted to MILITARY_ROLES: an
    // unarmed freighter is normal, an unarmed Frigate isn't. A ship still under
    // construction hasn't been fitted out yet by design, so it's excluded rather
    // than flagged. Each entry keeps its specific gap(s) (guns vs. shields) rather
    // than just the ship, since "no weapons" and "no shields" call for different
    // fixes and a ship can be missing both at once.
    const underEquipped = (data.ships || []).flatMap(s => {
      if (s.under_construction || !MILITARY_ROLES.has(s.role)) return [];
      const hp = s.hardpoints || {};
      const loadout = s.loadout || [];
      const hasGunHardpoints = !!(hp.weapon || hp.turret);
      const hasFittedGuns = loadout.some(e => e.slot === "weapon" || e.slot === "turret");
      const hasShieldHardpoints = !!hp.shield;
      const hasFittedShields = loadout.some(e => e.slot === "shield");
      const gaps = [];
      if (hasGunHardpoints && !hasFittedGuns) gaps.push("no weapons");
      if (hasShieldHardpoints && !hasFittedShields) gaps.push("no shields");
      return gaps.length > 0 ? [{ ship: s, gaps }] : [];
    });

    // Surplus Piling Up — a produced ware's net surplus (production_rate minus
    // consumption_rate, from station_production_analytics via _stations()) is
    // accumulating faster than the trade log shows it actually leaving the
    // station. No advisor finding backs this yet, same raw-scan-data pattern
    // as Production Stalling/Input Starvation above. Deliberately makes no
    // claim about WHY the surplus isn't clearing (price, distance, no
    // subordinate assigned, a paused offer, ...) — earlier versions of this
    // alert guessed "overpriced" or "no offer" and both were wrong often
    // enough (a station can sell plenty through a manually-run trade
    // subordinate with no posted offer at all) to be worse than no guess.
    //
    // data.station_trades only covers the delta since the previous scan, so
    // there's no absolute clock to turn "units sold" into a rate — the
    // widest time_ago_s across every trade in that delta approximates the
    // window's span, since every entry falls somewhere inside it. No trades
    // at all means no window to measure against, so the check no-ops rather
    // than guessing. production_rates is keyed by display name, not ware_id,
    // so this reuses the Production tab's own name→id slug conversion
    // (populate.js, "Energy Cells" → "energycells") to match against
    // station_trades, which is genuinely ware_id-keyed.
    const stationTrades = data.station_trades || [];
    const tradeWindowHours = stationTrades.length > 0
      ? Math.max(...stationTrades.map(t => t.time_ago_s || 0)) / 3600
      : 0;
    // Each entry keeps the raw made/sold rates rather than a pre-formatted
    // string — the tile only shows the ware name (coloured via WARE_COLOURS,
    // same as the Production tab), with the rates available on hover so a
    // station with several offending wares doesn't turn into a wall of text.
    const pileUpByStation = new Map(); // station code -> [{name, excess, sold}, ...]
    if (tradeWindowHours > 0) {
      stations.forEach(s => {
        const prodRates = s.production_rates || {};
        const consRates = s.consumption_rates || {};
        Object.entries(prodRates).forEach(([wareName, prodRate]) => {
          const surplusRate = (prodRate || 0) - (consRates[wareName] || 0);
          if (surplusRate <= 0) return;
          const wareId = wareName.toLowerCase().replace(/\s+/g, '');
          const soldUnits = stationTrades
            .filter(t => t.station_code === s.code && t.ware === wareId && t.direction === "Out")
            .reduce((sum, t) => sum + (t.amount || 0), 0);
          const soldRate = soldUnits / tradeWindowHours;
          if (soldRate >= surplusRate) return;
          if (!pileUpByStation.has(s.code)) pileUpByStation.set(s.code, []);
          pileUpByStation.get(s.code).push({ name: wareName, excess: surplusRate, sold: soldRate });
        });
      });
    }

    // No Logistics Assigned — a station with input_rates non-empty (it's
    // actively consuming wares) but assigned_fleet.traders === 0 (no
    // subordinate hauler on its books) is only really logistics-starved if
    // nothing else is quietly covering it — a manually-flown run, another
    // station's spare hauler, etc. So this also requires no inbound trade at
    // that station within NO_LOGISTICS_RECENT_HOURS of station_trades'
    // time_ago_s: long enough that a hauler already en route on a slow
    // cross-sector leg doesn't false-positive, short enough that a station
    // with nothing in that whole window really has no one covering it.
    // Deliberately distinct from the Trader/Logistics advisors
    // (db/advisors/trader.py, db/advisors/logistics.py) — neither checks
    // this consuming-station-with-no-hauler-and-no-recent-delivery case, so
    // this is a raw-scan-data check like Station Underfunded above, not a
    // duplicate of an advisor finding.
    const NO_LOGISTICS_RECENT_HOURS = 6;
    const noLogisticsStations = stations.flatMap(s => {
      const rates = s.input_rates || {};
      const wareNames = Object.keys(rates);
      if (wareNames.length === 0) return [];
      if (((s.assigned_fleet || {}).traders || 0) !== 0) return [];
      const hasRecentDelivery = stationTrades.some(t => t.station_code === s.code
        && t.direction === "In" && (t.time_ago_s || 0) <= NO_LOGISTICS_RECENT_HOURS * 3600);
      if (hasRecentDelivery) return [];
      // With no hauler at all, every input here is going unserved — but the
      // one(s) about to actually run dry are what the player needs to see
      // first, so sort soonest-to-deplete first rather than alphabetically.
      const wares = wareNames.sort((a, b) =>
        (rates[a].runtime_hours ?? Infinity) - (rates[b].runtime_hours ?? Infinity));
      return [{ code: s.code, wares }];
    });

    // The badge counts alert *categories*, not individual tiles — a fleet of
    // twenty idle ships is one problem to look at, not twenty.
    const alertCount = (hostilePresence.length > 0 ? 1 : 0)
      + (buildups.length > 0 ? 1 : 0) + (compositionGaps.length > 0 ? 1 : 0)
      + (outranged.length > 0 ? 1 : 0) + (waiting.length > 0 ? 1 : 0)
      + (damagedFleet.length > 0 ? 1 : 0) + (storageOverflow.length > 0 ? 1 : 0)
      + (strandedDeliveries.length > 0 ? 1 : 0) + (stationDamageActive ? 1 : 0)
      + (stallsByStation.size > 0 ? 1 : 0) + (starvedByStation.size > 0 ? 1 : 0)
      + (underfundedStations.length > 0 ? 1 : 0) + (underEquipped.length > 0 ? 1 : 0)
      + (pileUpByStation.size > 0 ? 1 : 0) + (noLogisticsStations.length > 0 ? 1 : 0);
    document.getElementById("nav-alerts").textContent = alertCount;

    const alertsList = document.getElementById("alerts-list");
    const alerts = [];

    // Alert tiles stay terse (sector + severity) rather than mirroring the
    // advisor's full finding text — the "Advise" button is the deep link to
    // that reasoning (AdvisorsFeed.jumpToFinding() switches to the Military
    // advisor tab, expands that exact card's evidence drawer, and scrolls it
    // into view).
    const adviseBtn = (f, view = "military") => `<button class="alert-advise" onclick="AdvisorsFeed.jumpToFinding('${f.id}','${view}')">Advise</button>`;

    // Station codes jump to the Stations tab via goToStation() (station-helpers.js) —
    // same .stn-link affordance the Fleet tab's homebase column uses.
    const stationLink = code => `<span class="stn-link" onclick="goToStation('${code}')">${code}</span>`;

    // Hostile Presence — one tile per (sector, hostile faction) where their
    // force is at least a match for the player's present defence there.
    // Undefended/Outmatched (we'd lose that fight) render red; Contested
    // (could go either way) renders amber.
    hostilePresence.forEach(f => {
      const cls = (f.slots.verdict === "Outmatched" || f.slots.verdict === "Undefended")
        ? "red" : "amber";
      const msg = `<div class="alert-title">${f.slots.sector_name}</div>
        <div class="alert-sub">${f.slots.verdict} · ${f.slots.faction_name}</div>
        <div class="alert-actions">${adviseBtn(f)}${AdvisorsFeed.counterIconHtml(f)}</div>`;
      alerts.push({ msg, cls, icon: "ti-alert-triangle" });
    });

    // Force Build-Up — sectors where hostile combat strength has risen every
    // tracked scan (staging, not a raid); see buildup_findings() for the
    // run-length/growth gates. Early-warning, so amber rather than red even
    // though nothing here has been filtered by "would we currently win".
    buildups.forEach(f => {
      const msg = `<div class="alert-title">${f.slots.sector_name}</div>
        <div class="alert-sub">Building up · ${f.slots.faction_name} (${f.slots.growth}×)</div>
        <div class="alert-actions">${adviseBtn(f)}</div>`;
      alerts.push({ msg, cls: "amber", icon: "ti-trending-up-2" });
    });

    // Composition Gap — sectors where the hostile force is mostly S/M strike
    // craft the defence's guns can't track (composition_gap_findings() in
    // military.py compares dps_anti_small to total DPS). Always amber: it's
    // a loadout mismatch to fix ahead of time, not a fight being lost now.
    compositionGaps.forEach(f => {
      const msg = `<div class="alert-title">${f.slots.sector_name}</div>
        <div class="alert-sub">${f.slots.small_count} strike craft, only ${f.slots.anti_small_pct}% of your DPS tracks them · ${f.slots.faction_name}</div>
        <div class="alert-actions">${adviseBtn(f)}</div>`;
      alerts.push({ msg, cls: "amber", icon: "ti-puzzle" });
    });

    // Outranged — sectors where hostile capital hulls (L/XL) out-reach the
    // whole defence (outranged_findings() in military.py). Standoff-bombardment
    // risk rather than a fight already being lost, so amber like the other
    // loadout-mismatch alerts.
    outranged.forEach(f => {
      const msg = `<div class="alert-title">${f.slots.sector_name}</div>
        <div class="alert-sub">${f.slots.capital_count} capital(s) reach ${f.slots.their_range_km} km vs your ${f.slots.our_range_km} km · ${f.slots.faction_name}</div>
        <div class="alert-actions">${adviseBtn(f)}</div>`;
      alerts.push({ msg, cls: "amber", icon: "ti-target-arrow" });
    });

    // Damaged Fleet — combat ships under DAMAGED_HULL_PCT (75%) hull, undocked
    // (damaged_fleet_findings() in military.py), so every finding here has
    // already taken 25%+ damage. Severity is relative damage (hull_pct), not
    // priority_score's absolute missing HP — "badly hurt" should mean the
    // ship itself is close to lost, not that it's expensive, so a fighter at
    // 30% hull reads the same urgency as a destroyer at 30% hull. 40% hull is
    // the halfway point of this alert's whole 0-75% range: below it the ship
    // has taken more damage than it has left (red), above it there's still
    // more hull than damage (amber).
    const DAMAGED_FLEET_RED_HULL_PCT = 40;
    damagedFleet.forEach(f => {
      const cls = f.slots.hull_pct < DAMAGED_FLEET_RED_HULL_PCT ? "red" : "amber";
      const msg = `<div class="alert-title">${f.slots.ship_name}</div>
        <div class="alert-sub">${f.slots.hull_pct}% hull · ${f.slots.role} · ${f.slots.sector_name}</div>
        <div class="alert-actions">${adviseBtn(f)}</div>`;
      alerts.push({ msg, cls, icon: "ti-heart-broken" });
    });

    // Station Damaged / Under Attack — buckets stations by severity rather
    // than one tile per station (there can be a lot of stations), same list
    // pattern as the idling-ships/idle-miners rows below. ti-building-broken
    // doesn't exist in the bundled Tabler set, so this falls back to the
    // same triangle icon as the other red/amber alerts above.
    if (damagedStationsRed.length > 0) {
      const codes = damagedStationsRed.slice(0,6).map(s=>stationLink(s.code)).join(", ");
      const more  = damagedStationsRed.length > 6 ? ` (+${damagedStationsRed.length-6} more)` : "";
      alerts.push({ msg:`<div class="alert-sub">${damagedStationsRed.length} station(s) under attack or critical hull: ${codes}${more}</div>`, cls:"red", icon:"ti-alert-triangle" });
    }
    if (damagedStationsAmber.length > 0) {
      const codes = damagedStationsAmber.slice(0,6).map(s=>stationLink(s.code)).join(", ");
      const more  = damagedStationsAmber.length > 6 ? ` (+${damagedStationsAmber.length-6} more)` : "";
      alerts.push({ msg:`<div class="alert-sub">${damagedStationsAmber.length} station(s) damaged: ${codes}${more}</div>`, cls:"amber", icon:"ti-alert-triangle" });
    }

    // Production Stalling — one row per station per severity, listing the
    // affected wares (a station can have one ware already halted and another
    // just stalling soon at the same time, so red/amber never mix in one row).
    stallsByStation.forEach((sev, code) => {
      if (sev.red.length > 0) {
        const wares = sev.red.slice(0,6).join(", ") + (sev.red.length > 6 ? ` (+${sev.red.length-6} more)` : "");
        alerts.push({ msg:`<div class="alert-title">${stationLink(code)}</div><div class="alert-sub">Stalled: ${wares}</div>`, cls:"red", icon:"ti-player-pause" });
      }
      if (sev.amber.length > 0) {
        const wares = sev.amber.slice(0,6).join(", ") + (sev.amber.length > 6 ? ` (+${sev.amber.length-6} more)` : "");
        alerts.push({ msg:`<div class="alert-title">${stationLink(code)}</div><div class="alert-sub">Stalling soon: ${wares}</div>`, cls:"amber", icon:"ti-player-pause" });
      }
    });

    // Input Starvation — one row per station per severity, listing the
    // starving wares with their own remaining hours (unlike Production
    // Stalling's plain ware list, since here the number itself is the point —
    // these thresholds are wide enough that "how soon" varies a lot within a row).
    starvedByStation.forEach((sev, code) => {
      if (sev.red.length > 0) {
        const wares = sev.red.slice(0,6).join(", ") + (sev.red.length > 6 ? ` (+${sev.red.length-6} more)` : "");
        alerts.push({ msg:`<div class="alert-title">${stationLink(code)}</div><div class="alert-sub">Starving: ${wares}</div>`, cls:"red", icon:"ti-gas-station-off" });
      }
      if (sev.amber.length > 0) {
        const wares = sev.amber.slice(0,6).join(", ") + (sev.amber.length > 6 ? ` (+${sev.amber.length-6} more)` : "");
        alerts.push({ msg:`<div class="alert-title">${stationLink(code)}</div><div class="alert-sub">Low input: ${wares}</div>`, cls:"amber", icon:"ti-gas-station-off" });
      }
    });

    // Station Underfunded — one row listing affected station codes with their
    // current balances, same bucketed-list pattern as Station Damaged above.
    // Amber only (no red split): a low account balance is a heads-up to
    // resupply credits, not damage or a fight already lost.
    if (underfundedStations.length > 0) {
      const codes = underfundedStations.slice(0,6)
        .map(s => `${stationLink(s.code)} (${fmtCredits(s.account_amount)})`).join(", ");
      const more  = underfundedStations.length > 6 ? ` (+${underfundedStations.length-6} more)` : "";
      alerts.push({ msg:`<div class="alert-sub">${underfundedStations.length} station(s) underfunded: ${codes}${more}</div>`, cls:"amber", icon:"ti-wallet-off" });
    }

    // No Logistics Assigned — one row listing every consuming station with no
    // dedicated hauler and no recent delivery, same bucketed-list pattern as
    // Station Underfunded above. Each station carries its own unserved wares
    // in parentheses (soonest-to-deplete first, same "(detail)" suffix
    // pattern as Under-Equipped Ships) so the row says WHAT needs a hauler,
    // not just where. Amber only: it's an unassigned-subordinate gap to fix,
    // not damage or a fight being lost.
    if (noLogisticsStations.length > 0) {
      const codes = noLogisticsStations.slice(0,6).map(({code, wares}) => {
        const shown = wares.slice(0,3).join(", ") + (wares.length > 3 ? ` +${wares.length-3}` : "");
        return `${stationLink(code)} (${shown})`;
      }).join(", ");
      const more = noLogisticsStations.length > 6 ? ` (+${noLogisticsStations.length-6} more)` : "";
      alerts.push({ msg:`<div class="alert-sub">${noLogisticsStations.length} station(s) with no logistics assigned: ${codes}${more}</div>`, cls:"amber", icon:"ti-truck-off" });
    }

    // Surplus Piling Up — one row per station listing every ware whose stock
    // is growing faster than the trade log shows it selling, same bucketed-
    // list pattern as Input Starvation above. Each ware renders as its
    // WARE_COLOURS-tinted name only (matching the Production tab) rather than
    // the made/sold rates inline — a station with several offending wares
    // turned into a wall of numbers, so those move to a data-text-tip hover
    // instead (see UI_STANDARDS.md §8: shared #hull-tip popover, never
    // title=). Amber only: a stockpile building up is a logistics gap to
    // look into, not damage or a fight being lost.
    const pileUpWareChip = w => {
      const col = WARE_COLOURS[w.name] || 'var(--text-secondary)';
      const tip = `${Math.round(w.excess)}/hr excess vs ${Math.round(w.sold)}/hr sold`;
      return `<span style="color:${col}" data-text-tip="${tip}">${w.name}</span>`;
    };
    pileUpByStation.forEach((wares, code) => {
      const list = wares.slice(0,6).map(pileUpWareChip).join(", ") + (wares.length > 6 ? ` (+${wares.length-6} more)` : "");
      alerts.push({ msg:`<div class="alert-title">${stationLink(code)}</div><div class="alert-sub">Surplus piling up: ${list}</div>`, cls:"amber", icon:"ti-building-warehouse" });
    });

    // Storage Overflow — stations about to cap out on a surplus ware within
    // OVERFLOW_ALERT_HOURS (1h). Terse tile per finding (station + the
    // at-risk ware), same as the military tiles above; the "Advise" button is
    // the deep link to the Economic advisor card with the full reasoning.
    // Under OVERFLOW_ALERT_RED_HOURS (30min) renders red — same red/amber
    // split idea as Damaged Fleet above, just on time-to-cap instead of hull.
    storageOverflow.forEach(f => {
      const cls = f.slots.hours <= OVERFLOW_ALERT_RED_HOURS ? "red" : "amber";
      const msg = `<div class="alert-title">${f.slots.station_name}</div>
        <div class="alert-sub">${f.slots.ware_name}</div>
        <div class="alert-actions">${adviseBtn(f, "economic")}</div>`;
      alerts.push({ msg, cls, icon: "ti-database-exclamation" });
    });

    // Ship codes are player ships (`waiting` is filtered from the player fleet
    // in populate()), so every code in these messages jumps to the Fleet tab via
    // jumpToShip() — same .ship-link affordance used on the Crew/Economy tabs.
    const shipLink = code => `<span class="ship-link" onclick="jumpToShip('${code}','player')">${code}</span>`;

    // Stranded Deliveries — one tile per ship+ware, same terse pattern as the
    // advisor-backed tiles above. Always amber: a missing delivery order is a
    // fix-it-when-convenient paperwork gap, not damage or hostile action.
    strandedDeliveries.forEach(f => {
      const msg = `<div class="alert-title">${shipLink(f.slots.ship_code)} · ${f.slots.ware_name}</div>
        <div class="alert-sub">Holding cargo ${f.slots.hours}h, no delivery destination</div>
        <div class="alert-actions">${adviseBtn(f, "trader")}</div>`;
      alerts.push({ msg, cls: "amber", icon: "ti-package-off" });
    });

    // Wrapped in a single <div>: bare text mixed with inline .ship-link spans
    // as DIRECT children of the flex-column .alert tile gets split into one
    // anonymous flex item per run, each picking up the tile's own gap — the
    // wrapper makes the whole message one flex item so it just wraps as a
    // normal paragraph instead.
    if (waiting.length > 0) {
      const codes = waiting.slice(0,6).map(s=>shipLink(s.code)).join(", ");
      const more  = waiting.length > 6 ? ` (+${waiting.length-6} more)` : "";
      alerts.push({ msg:`<div class="alert-sub">${waiting.length} ships idling (Waiting order): ${codes}${more}</div>`, cls:"amber", icon:"ti-clock" });
    }

    const idleMiners = waiting.filter(s => MINER_ROLES.has(s.role));
    if (idleMiners.length > 0) {
      alerts.push({ msg:`<div class="alert-sub">${idleMiners.length} idle miner(s): ${idleMiners.map(s=>shipLink(s.code)).join(", ")}</div>`, cls:"amber", icon:"ti-shovel" });
    }

    // Under-Equipped Ships — one row listing every offending ship code with its
    // specific gap(s) attached, same "name (detail)" suffix pattern as Input
    // Starvation's per-ware "(Nh)" above. Always amber: a missing loadout is a
    // fix-it gap, not damage or hostile action.
    if (underEquipped.length > 0) {
      const codes = underEquipped.slice(0,6)
        .map(u => `${shipLink(u.ship.code)} (${u.gaps.join(", ")})`).join(", ");
      const more  = underEquipped.length > 6 ? ` (+${underEquipped.length-6} more)` : "";
      alerts.push({ msg:`<div class="alert-sub">${underEquipped.length} ship(s) under-equipped: ${codes}${more}</div>`, cls:"amber", icon:"ti-sword-off" });
    }

    alertsList.innerHTML = alerts.length === 0
      ? `<div class="alert green"><i class="ti ti-circle-check"></i> No alerts detected.</div>`
      : alerts.map(a => `<div class="alert ${a.cls}"><i class="ti ${a.icon}"></i> ${a.msg}</div>`).join("");
  }
