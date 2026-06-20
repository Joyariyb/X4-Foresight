  // Core role: Initializes responsive zoom, event routing, and tab persistence.

  // Responsive zoom scaled to viewport width (1536px = zoom 1.0).
  //   At 1920px fullscreen → zoom 1.25  (25% larger)
  //   At 1280px             → zoom 0.83 (17% smaller)
  //
  // Zoom is reset to 1 before reading innerWidth because QtWebEngine does NOT
  // divide innerWidth by the current zoom value — reading it while zoomed would
  // compound the zoom on every resize event and cause runaway scaling.
  // Both writes happen inside a single requestAnimationFrame callback so they
  // are batched within one frame and produce no visible flicker or lag.
  let _zoomRafPending = false;
  function updateZoom() {
    if (_zoomRafPending) return;
    _zoomRafPending = true;
    requestAnimationFrame(() => {
      _zoomRafPending = false;
      document.documentElement.style.zoom = 1;
      const zoom = Math.max(0.5, Math.min(2.0, window.innerWidth / 1536));
      document.documentElement.style.zoom = zoom;
    });
  }

  updateZoom();
  window.addEventListener('resize', updateZoom);
