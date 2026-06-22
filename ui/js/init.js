  // Core role: Initializes responsive scale, event routing, and tab persistence.

  // Responsive HUD scale keyed off viewport width (1536px = scale 1.0).
  //   At 1920px fullscreen → scale 1.25  (25% larger)
  //   At 1280px             → scale 0.83 (17% smaller)
  //
  // Drives the scale via the <html> root font-size (the whole UI is built in
  // rem, see base.css) rather than CSS `zoom`. CSS zoom splits mouse-event
  // coordinates (clientX/Y, always physical px) from CSS positions
  // (style.left/top, zoomed px) in QtWebEngine specifically — that forced
  // every tooltip/flyout/pan handler to manually divide by the zoom factor.
  // Root font-size scaling doesn't touch the coordinate space at all, so none
  // of that compensation is needed: clientX lines up with style.left for
  // free, in both the desktop shell and the web build alike. It also means
  // window.innerWidth is unaffected by our own scaling (font-size doesn't
  // change the viewport), so there's no read-after-reset dance either.
  const SCALE_BASE_PX = 10; // root font-size at scale 1.0; rem values assume 1rem = 10px
  let _scaleRafPending = false;
  function updateScale() {
    if (_scaleRafPending) return;
    _scaleRafPending = true;
    requestAnimationFrame(() => {
      _scaleRafPending = false;
      const scale = Math.max(0.5, Math.min(2.0, window.innerWidth / 1536));
      document.documentElement.style.fontSize = (SCALE_BASE_PX * scale) + 'px';
    });
  }

  updateScale();
  window.addEventListener('resize', updateScale);
