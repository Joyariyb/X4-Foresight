  // Core role: Tooltip dispatch engine. Owns the single #hull-tip element, routes
  // each hover to the handler a feature registered in TIP_HANDLERS (see
  // tip-registry.js), runs the registered reset hooks, and positions/clamps the
  // tip. Content builders and chart-marker geometry live with their features.
  (function() {
    const tip = document.getElementById('hull-tip');

    // '[data-hull-tip],[data-weapon-tip],…' derived from the registered keys
    // (camelCase dataset key -> kebab data-* attribute). Built lazily on the first
    // hover so every feature script has finished registering by then.
    let TIP_SELECTOR = null;
    const attrFor = key => '[data-' + key.replace(/[A-Z]/g, c => '-' + c.toLowerCase()) + ']';

    document.addEventListener('mousemove', function(e) {
      // Let features clear highlight state painted on the previous move (chart
      // markers, bar highlights) before we re-show whichever tip is hovered now.
      for (const reset of TIP_RESETS) reset();

      if (TIP_SELECTOR === null) TIP_SELECTOR = Object.keys(TIP_HANDLERS).map(attrFor).join(',');
      const el = TIP_SELECTOR ? e.target.closest(TIP_SELECTOR) : null;
      if (!el) { tip.style.display = 'none'; return; }

      // Each interactive element carries exactly one tip attribute; find it and
      // hand off to its registered handler, which fills `tip` (+ any side effects)
      // and returns true to show or false to stay hidden.
      let shown = false;
      for (const key in TIP_HANDLERS) {
        if (el.dataset[key] !== undefined) { shown = TIP_HANDLERS[key](el, e, tip); break; }
      }
      if (!shown) { tip.style.display = 'none'; return; }

      tip.style.display = 'block';
      const x = Math.min(e.clientX + 14, window.innerWidth  - tip.offsetWidth  - 8);
      // Clamp top (≥8) and bottom (≤innerHeight−height−8) so the tip never slides
      // under the viewport edge when the cursor is near the bottom.
      const y = Math.min(Math.max(e.clientY - 32, 8), window.innerHeight - tip.offsetHeight - 8);
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
