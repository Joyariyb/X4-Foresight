  // Core role: Single ordered dashboard script list shared by both shells (ui/ui.html and ui/web/index.html).
  //
  // Order is load order, and it matters: later files call functions the earlier
  // ones define (everything is classic-script global scope, not modules). Keeping
  // the list here makes adding a file a one-place change instead of the two
  // hand-synced <script> lists the shells used to carry — same reason body.html
  // is shared via shell-loader.js.

  // Everything that can load before the shell's bridge exists.
  const SHELL_SCRIPTS_CORE = [
    'js/constants.js',
    'js/topbar-responsive.js',
    'js/tip-registry.js',
    'js/economy-chart.js',
    'js/economy-logs.js',
    'js/cashflow-chart.js',
    'js/cashflow-hourly.js',
    'js/cashflow-ware.js',
    'js/cashflow-ship.js',
    'js/cashflow-avgprice.js',
    'js/trends.js',
    'js/formatters.js',
    'js/fleet.js',
    'js/hull-wireframes.js',
    'js/designs-builder.js',
    'js/resource-library.js',
    'js/hull-comparison.js',
    'js/equipment-comparison.js',
    'js/tooltips.js',
    'js/faction-tabs.js',
    'js/navigation.js',
    'js/help.js',
    'js/crew.js',
    'js/station-helpers.js',
    'js/production-flow.js',
    'js/events-feed.js',
    'js/missions-feed.js',
    'js/advisors-meta.js',
    'js/advisors-evidence.js',
    'js/advisors-feed.js',
    'js/alerts.js',
    'js/populate.js',
    'js/npc-stations.js',
    'js/npc-station-inspector.js',
    'js/universe-map.js',
    'js/sectors.js',
  ];

  // Loaded after the shell's bridge scripts: scan-loader.js runs its bridge
  // detection at load time, so the web shell's pyodide-bridge.js must already
  // have set window._bridge by the time this tail runs.
  const SHELL_SCRIPTS_TAIL = [
    'js/scan-sound.js',
    'js/scan-loader.js',
    'js/init.js',
  ];

  // prefix rebases the shared paths for shells that don't live in ui/ (the web
  // shell passes '../'); bridgeScripts are the shell's own extra files, inserted
  // at the one point in the order where a bridge is allowed to appear.
  function shellScripts(prefix, bridgeScripts) {
    return [
      ...SHELL_SCRIPTS_CORE.map(p => prefix + p),
      ...(bridgeScripts || []),
      ...SHELL_SCRIPTS_TAIL.map(p => prefix + p),
    ];
  }
