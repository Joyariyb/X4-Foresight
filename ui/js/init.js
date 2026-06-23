  // Core role: Applies the user's manual HUD zoom on load.

  // We used to scale the root font-size by window width (outerWidth / 1536), so
  // the whole rem-based UI grew with the monitor. That zoomed instead of
  // adapting: a 4K screen just got a giant 2x copy of the 1536px design (19rem
  // sidebar -> 38rem, cards stretched huge and sparse) rather than using the
  // extra room. Responsive behaviour now lives in CSS instead — a max-width cap
  // on #shell plus media-query breakpoints (see layout.css) — and the root font
  // stays the fixed 10px set in base.css, so 1rem == 10px everywhere and the
  // design renders at its intended density on every screen.
  //
  // The only thing left here is an *optional, user-driven* zoom: a single
  // multiplier the user picks for accessibility ("make the HUD bigger"),
  // decoupled from window width. It's applied once on load by overriding the
  // root font-size. Because we touch font-size and not CSS `zoom`, mouse-event
  // coordinates (clientX/Y) still line up 1:1 with CSS positions (style.left/
  // top) — the QtWebEngine zoom coordinate-split that the old code worried about
  // never applies. Default is 1.0 (the plain 10px base) when nothing is stored.
  const SCALE_BASE_PX = 10; // root font-size at zoom 1.0; rem values assume 1rem = 10px
  function applyUserZoom() {
    const stored = parseFloat(localStorage.getItem('x4-ui-zoom'));
    // Clamp to a sane range and ignore garbage/missing values.
    const zoom = (Number.isFinite(stored)) ? Math.max(0.5, Math.min(2.0, stored)) : 1.0;
    document.documentElement.style.fontSize = (SCALE_BASE_PX * zoom) + 'px';
  }

  applyUserZoom();
