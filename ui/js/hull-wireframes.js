  // Core role: Stylized SVG hull wireframes (one per size class) used by designs and resource library previews.
  //
  // Every size keeps the same teal frame + lime thrusters so the family reads
  // as related, then layers on the new structural elements that size actually
  // gains over the one below it (see SHIP_STATS in data/ship_stats.py):
  //   S  -- frame + thrusters only, no turrets at all.
  //   M  -- second wing pair (more weapon space) + turrets on the aft wingtips.
  //   L  -- distinct hull (no wings): twin engine pods on structural struts,
  //         dorsal turrets, flank hangar bays (L is the first size with
  //         unit_storage).
  //   XL -- distinct faceted/chamfered hull (no curves), a single spinal
  //         cannon up front, a row of large spinal weapon batteries, recessed
  //         hangar bays, and one big angular wing per side on a strut
  //         connector -- reflects XL's oversized weapon hardpoints and
  //         order-of-magnitude bigger unit_storage.
  const WIRE_SVG_BY_SIZE = {
    S: `<svg viewBox="0 0 140 64" style="filter:drop-shadow(0 0 4px rgba(88,166,255,0.55))" aria-hidden="true">
    <g fill="none" stroke="var(--teal)" stroke-width="1.1"><polygon points="70,5 80,26 76,54 70,60 64,54 60,26"/><line x1="70" y1="5" x2="70" y2="60"/><polygon points="60,30 41,38 44,49 60,45"/><polygon points="80,30 99,38 96,49 80,45"/></g>
    <g fill="none" stroke="var(--lime)" stroke-width="1.1"><line x1="66" y1="56" x2="66" y2="63"/><line x1="74" y1="56" x2="74" y2="63"/></g></svg>`,

    M: `<svg viewBox="0 0 170 115" style="filter:drop-shadow(0 0 4px rgba(88,166,255,0.55))" aria-hidden="true">
    <g fill="none" stroke="var(--teal)" stroke-width="1.1">
      <polygon points="85,10 96,30 92,55 96,80 90,95 85,100 80,95 74,80 78,55 74,30"/>
      <line x1="85" y1="10" x2="85" y2="100"/>
      <polygon points="74,35 50,42 53,53 74,49"/>
      <polygon points="96,35 120,42 117,53 96,49"/>
      <polygon points="78,72 60,77 62,85 78,82"/>
      <polygon points="92,72 110,77 108,85 92,82"/>
    </g>
    <g fill="none" stroke="var(--lime)" stroke-width="1.1">
      <line x1="81" y1="97" x2="81" y2="105"/>
      <line x1="89" y1="97" x2="89" y2="105"/>
    </g>
    <g stroke="var(--amber)" stroke-width="1.1">
      <circle cx="66" cy="80" r="2.6" fill="var(--amber)"/><line x1="66" y1="80" x2="57" y2="80"/>
      <circle cx="104" cy="80" r="2.6" fill="var(--amber)"/><line x1="104" y1="80" x2="113" y2="80"/>
    </g></svg>`,

    L: `<svg viewBox="0 0 158 145" style="filter:drop-shadow(0 0 5px rgba(88,166,255,0.55))" aria-hidden="true">
    <g fill="none" stroke="var(--teal)" stroke-width="1.1">
      <polygon points="75,10 83,10 89,18 89,38 91,65 100,95 83,115 75,115 58,95 67,65 69,38 69,18"/>
      <line x1="79" y1="10" x2="79" y2="115"/>
      <line x1="69" y1="20" x2="61" y2="15"/>
      <line x1="89" y1="20" x2="97" y2="15"/>
    </g>
    <g fill="none" stroke="var(--teal)" stroke-width="1.6">
      <line x1="100" y1="95" x2="122" y2="100"/>
      <line x1="100" y1="99" x2="122" y2="104"/>
      <line x1="58" y1="95" x2="36" y2="100"/>
      <line x1="58" y1="99" x2="36" y2="104"/>
    </g>
    <g fill="none" stroke="var(--teal)" stroke-width="1.1">
      <ellipse cx="130" cy="100" rx="11" ry="16"/>
      <ellipse cx="28" cy="100" rx="11" ry="16"/>
    </g>
    <g stroke="var(--amber)" stroke-width="1.1">
      <circle cx="79" cy="28" r="1.8" fill="var(--amber)"/><line x1="79" y1="28" x2="89" y2="28"/>
      <circle cx="79" cy="55" r="1.8" fill="var(--amber)"/><line x1="79" y1="55" x2="91" y2="55"/>
      <circle cx="130" cy="90" r="1.8" fill="var(--amber)"/><line x1="130" y1="90" x2="130" y2="80"/>
      <circle cx="28" cy="90" r="1.8" fill="var(--amber)"/><line x1="28" y1="90" x2="28" y2="80"/>
    </g>
    <g fill="none" stroke="var(--purple)" stroke-width="1.1">
      <rect x="96" y="68" width="10" height="24" rx="4"/><line x1="96" y1="80" x2="106" y2="80"/>
      <rect x="52" y="68" width="10" height="24" rx="4"/><line x1="52" y1="80" x2="62" y2="80"/>
    </g>
    <g fill="none" stroke="var(--lime)" stroke-width="1.1">
      <line x1="75" y1="117" x2="75" y2="129"/><line x1="77" y1="117" x2="77" y2="129"/>
      <line x1="81" y1="117" x2="81" y2="129"/><line x1="83" y1="117" x2="83" y2="129"/>
    </g></svg>`,

    XL: `<svg viewBox="0 0 210 215" style="filter:drop-shadow(0 0 6px rgba(88,166,255,0.55))" aria-hidden="true">
    <g fill="none" stroke="var(--teal)" stroke-width="1.1">
      <polygon points="81,30 129,30 135,36 135,62 144,78 144,132 160,156 160,189 154,195 56,195 50,189 50,156 66,132 66,78 75,62 75,36"/>
      <line x1="105" y1="30" x2="105" y2="195"/>
      <polygon points="160,158 180,161 180,175 160,178"/>
      <polygon points="50,158 30,161 30,175 50,178"/>
    </g>
    <g fill="none" stroke="var(--teal)" stroke-width="1.1">
      <polygon points="188,125 196,125 204,133 204,197 196,205 188,205 180,197 180,133"/>
      <polygon points="22,125 14,125 6,133 6,197 14,205 22,205 30,197 30,133"/>
    </g>
    <g fill="none" stroke="var(--red)" stroke-width="1.2">
      <rect x="98" y="18" width="14" height="14"/>
      <line x1="102" y1="18" x2="102" y2="0"/>
      <line x1="108" y1="18" x2="108" y2="0"/>
      <line x1="100" y1="0" x2="110" y2="0"/>
    </g>
    <g fill="none" stroke="var(--red)" stroke-width="1.3">
      <circle cx="105" cy="75" r="8"/>
      <circle cx="105" cy="115" r="8"/>
      <circle cx="105" cy="155" r="8"/>
    </g>
    <g stroke="var(--amber)" stroke-width="1.1">
      <circle cx="135" cy="45" r="1.8" fill="var(--amber)"/><line x1="135" y1="45" x2="143" y2="40"/>
      <circle cx="75" cy="45" r="1.8" fill="var(--amber)"/><line x1="75" y1="45" x2="67" y2="40"/>
    </g>
    <g fill="none" stroke="var(--purple)" stroke-width="1.1">
      <rect x="130" y="168" width="10" height="20" rx="4"/><line x1="130" y1="178" x2="140" y2="178"/>
      <rect x="70" y="168" width="10" height="20" rx="4"/><line x1="70" y1="178" x2="80" y2="178"/>
    </g>
    <g fill="none" stroke="var(--lime)" stroke-width="1.1">
      <line x1="88" y1="195" x2="88" y2="207"/><line x1="92" y1="195" x2="92" y2="207"/>
      <line x1="118" y1="195" x2="118" y2="207"/><line x1="122" y1="195" x2="122" y2="207"/>
    </g></svg>`,
  };
  const wireSvgFor = size => WIRE_SVG_BY_SIZE[(size || '').toUpperCase()] || WIRE_SVG_BY_SIZE.S;
