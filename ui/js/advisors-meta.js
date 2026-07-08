  // Core role: Static lookup tables for the Advisor tabs — view routing, finding
  // type presentation, and evidence-key labels. Pure data, no rendering; split
  // out of advisors-feed.js so that file's render logic isn't buried under the
  // per-rule label tables that grow every time a new advisor rule ships.
  window.AdvisorsMeta = (function () {

    // View → root element + which domains it shows. Economic keeps everything
    // that isn't military or trader (economy + logistics predate the split
    // and share a tab); priority scores only compete WITHIN a view, so
    // military's threat-point units never fight economy's Cr/hr for rail
    // height, and trader's own mixed units (Cr, Cr/hr, credits banked) never
    // fight either of the others.
    const VIEWS = {
      economic: { root: 'advisors-root',          match: f => f.domain !== 'military' && f.domain !== 'trader' },
      military: { root: 'advisors-military-root', match: f => f.domain === 'military' },
      trader:   { root: 'advisors-trader-root',   match: f => f.domain === 'trader' },
    };

    // Finding type → presentation. `tone` picks the semantic colour trio via
    // an adv--<tone> modifier class in advisors.css — colours stay in CSS
    // where the tokens live, JS only chooses the meaning.
    const TYPE_META = {
      overflow_risk:      { label: 'Overflow Risk',      icon: 'ti-stack-2',      tone: 'warning'  },
      market_opportunity: { label: 'Market Opportunity', icon: 'ti-trending-up',  tone: 'positive' },
      pricing_gap:        { label: 'Pricing Gap',        icon: 'ti-scale',        tone: 'info'     },
      idle_hauler:        { label: 'Idle Hauler',        icon: 'ti-anchor',       tone: 'special'  },
      hostile_presence:   { label: 'Hostile Presence',   icon: 'ti-alert-triangle', tone: 'negative' },
      composition_gap:    { label: 'Tracking Mismatch',  icon: 'ti-crosshair',    tone: 'warning'  },
      outranged:          { label: 'Outranged',          icon: 'ti-ruler-2',      tone: 'warning'  },
      buildup:            { label: 'Force Build-Up',     icon: 'ti-trending-up-2', tone: 'negative' },
      damaged_fleet:      { label: 'Damaged Ship',       icon: 'ti-tool',         tone: 'warning'  },
      station_siting:         { label: 'Station Siting',       icon: 'ti-building',         tone: 'special'  },
      galaxy_arbitrage:       { label: 'Galaxy Arbitrage',     icon: 'ti-arrows-exchange',   tone: 'positive' },
      stranded_delivery:      { label: 'Stranded Delivery',    icon: 'ti-alert-circle',      tone: 'warning'  },
      idle_trade_capital:     { label: 'Idle Trade Capital',   icon: 'ti-cash',              tone: 'info'     },
    };
    const FALLBACK_META = { label: 'Finding', icon: 'ti-clipboard-list', tone: 'info' };

    const DOMAIN_LABELS = { economy: 'Economy', logistics: 'Logistics', military: 'Military', trader: 'Trader' };

    // Evidence keys → readable labels. Anything not listed falls back to the
    // raw key with underscores spaced — a new rule's evidence still renders.
    const EVIDENCE_LABELS = {
      station_id:         'Station',
      npc_station_id:     'NPC Station',
      ship_id:            'Ship',
      homebase_id:        'Home Station',
      code:               'Code',
      ware_id:            'Ware',
      surplus_rate:       'Surplus /hr',
      time_to_cap_hours:  'Hours to Cap',
      demand_depth:       'Unmet Demand',
      jumps:              'Jumps Away',
      amount:             'Stock Units',
      player_price_cents: 'Your Price (¢)',
      npc_price_cents:    'Their Price (¢)',
      cargo_m3:           'Cargo Load m³',
      cargo_max_m3:       'Cargo Cap m³',
      sector_macro:       'Sector',
      faction_id:         'Faction',
      reputation:         'Reputation',
      combat_count:       'Combat Ships',
      noncombat_count:    'Non-Combat Ships',
      defender_count:     'Your Combat Ships There',
      hull_hp:            'Hull HP',
      hull_max:           'Hull Max HP',
      shield_pct:         'Shield %',
      unassessed_count:   'Ships Unassessed',
      their_dps:          'Their Damage /s',
      our_dps:            'Your Damage /s',
      their_ehp:          'Their Hull+Shield HP',
      our_ehp:            'Your Hull+Shield HP',
      ttk_they_break_us_s: 'They Break You In (s)',
      ttk_we_break_them_s: 'You Break Them In (s)',
      hostile_fleet_value_cr: 'Hostile Fleet Value Cr',
      small_count:        'Hostile Strike Craft',
      hostile_ship_count: 'Hostile Ships Total',
      our_anti_small_dps: 'Your Anti-Fighter Damage /s',
      their_range_m:      'Their Max Range (m)',
      our_range_m:        'Your Max Range (m)',
      capital_count:      'Hostile Capitals',
      overall_growth:     'Overall Strength Growth ×',
      firepower_from:     'Firepower Then (dmg/s)',
      firepower_to:       'Firepower Now (dmg/s)',
      firepower_growth:   'Firepower Growth ×',
      shield_from:        'Shield HP Then',
      shield_to:          'Shield HP Now',
      shield_growth:      'Shield Growth ×',
      hull_from:          'Hull HP Then',
      hull_to:            'Hull HP Now',
      hull_growth:        'Hull Growth ×',
      scans_rising:       'Scans Rising',
      anchor:             'Proximity Anchor',
      recharge_max:       'Reservoir Capacity',
      yield_level:        'Yield Level',
      sell_station_id:    'Sell Station',
      buy_station_id:     'Buy Station',
      sell_jumps:         'Jumps to Seller',
      buy_jumps:          'Jumps to Buyer',
      volume:             'Tradeable Units',
      sell_price_cents:   'Sell Price',
      buy_price_cents:    'Buy Price',
      time_ago_s:         'Seconds Since Pickup',
      value_estimate:     'Estimated Value Cr',
      player_credits:     'Credits Banked',
      trader_ships:       'Trading Ships',
      total_ships:        'Total Ships',
      ratio:              'Trading Ship Ratio',
      reputation_value:   'Reputation Value',
    };

    return { VIEWS, TYPE_META, FALLBACK_META, DOMAIN_LABELS, EVIDENCE_LABELS };
  })();
