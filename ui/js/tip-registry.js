  // Core role: Tooltip handler registry — feature files register one handler per
  // data-* key; the dispatch engine in tooltips.js consumes these maps to route and
  // reset hovers. Loaded before every feature script (and the dispatcher) so the
  // registrations already exist when the dispatcher first runs.
  //
  // Why a registry: the dispatcher used to be a ~14-branch if/else that hard-coded
  // every feature's builder and chart-marker geometry. Registering per feature keeps
  // each tooltip's logic next to the code that stamps its attribute, and leaves
  // tooltips.js as a small, feature-agnostic engine.

  // datasetKey (camelCase, e.g. 'weaponTip' for [data-weapon-tip]) -> handler.
  // A handler is (el, event, tip) => boolean: it fills `tip` (innerHTML/textContent,
  // colour, whiteSpace) plus any side effects, and returns true to show + position
  // the tip, or false to leave it hidden (used by the chart handlers when the cursor
  // isn't near a data point).
  const TIP_HANDLERS = {};
  function registerTip(key, handler) { TIP_HANDLERS[key] = handler; }

  // Reset callbacks run at the start of every mousemove, before dispatch, so a
  // feature can clear highlight state it painted on the previous move (e.g. chart
  // markers) regardless of what is hovered now.
  const TIP_RESETS = [];
  function onTipReset(fn) { TIP_RESETS.push(fn); }

  // Same idea, for the draggable time-window scrubber (.cf-scrubber-track) shared
  // by the cash-flow chart and the economy logs panel — both want the exact same
  // slider look/drag behaviour but keep their own per-station zoom state and
  // rebuild logic. The generic drag handler in tooltips.js reads this map; it
  // never touches a feature's zoom store directly.
  //
  // kind: 'cf' | 'logs' -> { zoom, minHours, maxHours, onChange }
  //   zoom      { [safeCode]: { hours, offsetHours } } — mutated in place by drag
  //   minHours  number, or (safeCode) => number — narrowest allowed window
  //   maxHours  number, or (safeCode) => number — full width of the track (== the
  //             window's total time span, may differ per station for logs)
  //   onChange  (safeCode) => void — re-renders that feature after a drag step
  const SCRUBBER_KINDS = {};
  function registerScrubber(kind, def) { SCRUBBER_KINDS[kind] = def; }
