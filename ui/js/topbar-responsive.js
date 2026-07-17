  // Core role: Shrinks topbar nav-tab label text through a few steps before
  // falling back to icon-only, so the collapse feels gradual instead of an
  // abrupt jump from full text to icons.
  //
  // Real overflow (scrollWidth vs clientWidth), not a viewport breakpoint,
  // drives this: badge text (nav-trends-count, nav-ships, nav-alerts)
  // changes how much room the bar actually needs at a given window width, so
  // a hardcoded px threshold can't get it right in every case.
  (function() {
    const topbar = document.getElementById('topbar');
    if (!topbar) return;

    // Label font-size steps to try, largest (most readable) first, as
    // multipliers of the tab's normal font-size. Below the last step the
    // text would be too cramped to read comfortably, so instead of shrinking
    // further we drop to icon-only.
    const LABEL_SCALE_STEPS = [1, 0.88, 0.78, 0.7];

    function fits() {
      return topbar.scrollWidth <= topbar.clientWidth + 1; // +1: subpixel rounding guard
    }

    let queued = false;
    function updateCompact() {
      if (queued) return;
      queued = true;
      requestAnimationFrame(() => {
        queued = false;

        // Reset to the widest state before measuring -- once shrunk/compact,
        // the content already fits, so scrollWidth would never report an
        // overflow again and the bar could shrink but never grow back out.
        topbar.classList.remove('topbar-compact');
        topbar.classList.remove('topbar-scroll');

        let settled = false;
        for (const scale of LABEL_SCALE_STEPS) {
          topbar.style.setProperty('--nav-scale', scale);
          if (fits()) { settled = true; break; }
        }

        if (!settled) {
          // Even the smallest label text doesn't fit -- drop to icons.
          topbar.classList.add('topbar-compact');
          topbar.style.setProperty('--nav-scale', LABEL_SCALE_STEPS[0]);

          // .topbar-scroll turns on overflow-x, which (per a CSS quirk) also
          // clips the nav dropdown menus vertically -- see layout.css. Only
          // pay that cost in the rare case where icon-only mode itself still
          // doesn't fit; everywhere else, leave the dropdowns working.
          if (!fits()) topbar.classList.add('topbar-scroll');
        }
      });
    }

    // Window resizes change #topbar's own box size (it spans the shell width).
    new ResizeObserver(updateCompact).observe(topbar);
    // Badge counts and other topbar text update in place (same box size, new
    // content width) after the initial scan loads, which a ResizeObserver on
    // the topbar's own box won't catch on its own.
    new MutationObserver(updateCompact).observe(topbar, { childList: true, subtree: true, characterData: true });

    updateCompact();
  })();
