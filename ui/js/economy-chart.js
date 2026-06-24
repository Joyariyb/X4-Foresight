  // Core role: Renders station budget as an interactive donut/pie chart with per-ware slices.
  function economyPieSvg(bud) {
    // Largest share first so the slices sweep from big to small clockwise.
    const lines = (bud.lines || []).filter(l => l.value > 0)
                    .slice().sort((a, b) => b.value - a.value);
    const total = lines.reduce((sum, l) => sum + l.value, 0);
    if (!lines.length || total <= 0) {
      return `<div style="padding:2.4rem 1.4rem;text-align:center;font-family:var(--font-mono);font-size:1.1rem;color:var(--text-faint)">No budget to chart</div>`;
    }

    const cx = 150, cy = 150, r = 92, labelR = r + 14;
    const lift = 7; // px a slice translates outward on hover (also sizes the sheen)
    const polar = (cxx, cyy, rad, deg) => {
      const a = (deg - 90) * Math.PI / 180; // -90 so 0° starts at the top
      return [cxx + rad * Math.cos(a), cyy + rad * Math.sin(a)];
    };

    let angle = 0;
    const slices = [];
    const labels = [];
    lines.forEach(ln => {
      const frac  = ln.value / total;
      const start = angle;
      const end   = angle + frac * 360;
      angle = end;
      const mid   = (start + end) / 2;
      const col   = WARE_COLOURS[ln.ware_name] || 'var(--text-dim)';

      // Slice path. A single full-circle ware would degenerate the arc, so draw
      // it as a complete circle instead of a zero-length wedge.
      let path;
      if (frac >= 0.999) {
        path = `M ${cx} ${cy - r} A ${r} ${r} 0 1 1 ${cx - 0.01} ${cy - r} Z`;
      } else {
        const [x1, y1] = polar(cx, cy, r, start);
        const [x2, y2] = polar(cx, cy, r, end);
        const largeArc = (end - start) > 180 ? 1 : 0;
        path = `M ${cx} ${cy} L ${x1.toFixed(2)} ${y1.toFixed(2)} A ${r} ${r} 0 ${largeArc} 1 ${x2.toFixed(2)} ${y2.toFixed(2)} Z`;
      }

      const pct = (frac * 100).toFixed(1);
      const tip = encodeURIComponent(JSON.stringify({
        ware: ln.ware_name, amount: ln.amount, price: ln.price,
        value: ln.value, basis: ln.basis, pct, colour: col,
      }));
      // Per-slice outward unit vector along the mid-angle, exposed as CSS vars so
      // the :hover rule can lift the slice toward the viewer for a 3D "pop".
      const [ux, uy] = polar(0, 0, 1, mid); // unit direction from centre
      slices.push(
        `<path class="pie-slice" d="${path}" fill="${col}" stroke="var(--bg-card)" stroke-width="1.5"
               style="--dx:${(ux*lift).toFixed(2)}px;--dy:${(uy*lift).toFixed(2)}px" data-budget-tip="${tip}"></path>`
      );

      // Radial label, rotated to the slice mid-angle and flipped on the left side.
      const [lx, ly] = polar(cx, cy, labelR, mid);
      const onLeft   = mid > 180;
      const rot      = onLeft ? mid + 180 : mid; // keep upright
      const anchor   = onLeft ? 'end' : 'start';
      // Hide labels for very thin slices to avoid overlap clutter.
      if (frac >= 0.03) {
        // Wrap multi-word ware names onto stacked lines (no abbreviation) so each
        // spoke stays short. Lines are vertically centred on the label anchor.
        const words = ln.ware_name.split(' ');
        const lh    = 12; // line height in SVG units, ~matches the 12px font
        const y0    = ly - ((words.length - 1) * lh) / 2;
        const tspans = words.map((w, i) =>
          `<tspan x="${lx.toFixed(2)}" y="${(y0 + i * lh).toFixed(2)}">${w}</tspan>`
        ).join('');
        labels.push(
          `<text class="pie-label" fill="${col}"
                 text-anchor="${anchor}" dominant-baseline="middle"
                 transform="rotate(${(rot - 90).toFixed(2)} ${lx.toFixed(2)} ${ly.toFixed(2)})">${tspans}</text>`
        );
      }
    });

    // Centre hole + total label make it a donut and give the figures a home.
    const hole = r * 0.5;
    // 3D effect, all purely visual (labels/hover/geometry unchanged):
    //  • pieDrop  — soft drop shadow under the ring so it lifts off the card
    //  • pieSheen — a spherical highlight→shadow overlay (light from top-left)
    //               laid over the slices so the ring reads as a curved surface
    //  • pieHole  — a dark inner-edge gradient on the centre hole, making the
    //               donut look like it has real thickness (recessed centre)
    return `
      <div style="display:flex;justify-content:center;padding:1rem 0.6rem 1.6rem">
        <svg viewBox="-55 -25 410 350" style="width:44rem;height:37.6rem" overflow="visible">
          <defs>
            <radialGradient id="pieSheen" cx="0.36" cy="0.30" r="0.75">
              <stop offset="0%"   stop-color="#fff" stop-opacity="0.42"/>
              <stop offset="42%"  stop-color="#fff" stop-opacity="0.06"/>
              <stop offset="62%"  stop-color="#000" stop-opacity="0"/>
              <stop offset="100%" stop-color="#000" stop-opacity="0.42"/>
            </radialGradient>
            <radialGradient id="pieHole" cx="0.5" cy="0.5" r="0.5">
              <stop offset="60%"  stop-color="#000" stop-opacity="0"/>
              <stop offset="100%" stop-color="#000" stop-opacity="0.55"/>
            </radialGradient>
          </defs>
          <g class="pie-ring">${slices.join('')}</g>
          <!-- Spherical sheen sits above the slices but ignores pointer events
               so slice hover/tooltip still works through it. Radius is r + the
               hover lift so a lifted slice's rim stays under the sheen (otherwise
               the protruding crescent escapes the rim shading and looks bright). -->
          <circle cx="${cx}" cy="${cy}" r="${r + lift}" fill="url(#pieSheen)" style="pointer-events:none"></circle>
          <circle cx="${cx}" cy="${cy}" r="${hole}" fill="var(--bg-card)"></circle>
          <!-- Inner-edge shadow gives the centre hole apparent depth. -->
          <circle cx="${cx}" cy="${cy}" r="${hole}" fill="url(#pieHole)" style="pointer-events:none"></circle>
          <text x="${cx}" y="${cy - 6}" text-anchor="middle" fill="var(--text-faint)"
                font-size="9" style="font-family:var(--font-mono);letter-spacing:0.12em;text-transform:uppercase">Budget</text>
          <text x="${cx}" y="${cy + 12}" text-anchor="middle" fill="var(--lime)"
                font-size="15" style="font-family:var(--font-mono)">${Math.round(bud.total).toLocaleString()}</text>
          ${labels.join('')}
        </svg>
      </div>`;
  }

