from __future__ import annotations
from ..entities import Gate


class GateHandler:
    """
    Extracts gate / accelerator endpoints from the save to build the galaxy map.

    Each gate is a small <component class="gate"> that lives inside exactly one
    sector's subtree, so — just like stations and ships — we read the sector from
    ctx.current_sector_macro rather than walking the component stack (the depth
    between a sector and a gate varies because zones push frames in between).

    Called twice per gate (the Scanner buffers gate components so the full subtree
    is in memory at close time, even though the subtree is tiny):
      on_start() — capture id / code / macro while the opening tag is processed,
                   plus the sector context that is correct only at this moment.
      on_end()   — walk the buffered <connections> block for the gate-pair link:
                   its own id (conn_id) and the partner endpoint it is wired to
                   (partner_conn_id). The galaxy-map builder pairs these across all
                   gates to produce one edge per sector-to-sector link.

    THE GATE-PAIR CONNECTION IS NOT ALWAYS NAMED "destination"
    A linked gate stores its pair connection under varying names: one endpoint
    typically names it "destination", the other names it after the route (e.g.
    "clustergate042to043"). So we cannot filter by name — we take the connection
    that carries a <connected> child. We DO exclude "highway*" connections though:
    accelerators that double as superhighway endpoints also carry highwayentry /
    highwayexit links, but superhighway movement is intra-cluster (0 jumps),
    modelled separately via shared cluster membership — counting it as a 1-jump
    gate edge would be wrong. After excluding highways, each connected gate has
    exactly one gate-pair link.

    WHY BUFFER SUCH A SMALL ELEMENT
    The connection ids we need are children, not attributes on the opening tag.
    Buffering lets on_end() read them with a simple find() instead of arming a
    streaming flag for the <connected> tag — which appears thousands of times
    elsewhere in the save (every component has a <connections> block) and would
    force a global dispatch hook for a tag we only care about inside gates.
    """

    def __init__(self) -> None:
        # Per-gate state set in on_start, consumed in on_end.
        self._object_id:    str = ''
        self._code:         str = ''
        self._macro:        str = ''
        self._sector_macro: str = ''

    # ── Dispatcher entry points ───────────────────────────────────────────────

    def on_start(self, elem, ctx) -> None:
        """Capture the gate's own attributes and its sector before buffering."""
        self._object_id    = elem.get('id',    '')
        self._code         = elem.get('code',  '')
        self._macro        = elem.get('macro', '')
        # Sector is only reliable from the running context — see class docstring.
        self._sector_macro = ctx.current_sector_macro

    def on_end(self, elem, ctx) -> None:
        """
        Build the Gate once the subtree is in memory.

        Reads the gate-pair connection (any name except highway*):
            <connections>
              <connection connection="destination" id="[conn_id]">
                <connected connection="[partner_conn_id]"/>
              </connection>
            </connections>

        A gate with no resolvable sector or no gate-pair link is skipped — it
        cannot contribute an edge to the graph.
        """
        if not self._object_id or not self._sector_macro:
            self._reset()
            return

        conn_id, partner_conn_id = self._read_gate_link(elem)
        if not conn_id or not partner_conn_id:
            # Disconnected or malformed gate — nothing to pair on. Skip.
            self._reset()
            return

        ctx.gates.append(Gate(
            scan_id         = ctx.scan_id,
            object_id       = self._object_id,
            code            = self._code,
            macro           = self._macro,
            gate_type       = self._classify(self._macro),
            sector_macro    = self._sector_macro,
            conn_id         = conn_id,
            partner_conn_id = partner_conn_id,
        ))

        self._reset()

    # ── Private helpers ────────────────────────────────────────────────────────

    def _read_gate_link(self, elem) -> tuple[str, str]:
        """
        Returns (own_connection_id, partner_connection_id) for the gate-pair
        connection, or ('', '') if the gate is not linked.

        Takes the first connection that has a <connected> child and is not a
        highway endpoint (see class docstring for why highways are excluded).
        """
        connections = elem.find('connections')
        if connections is None:
            return '', ''

        for conn in connections.findall('connection'):
            name = conn.get('connection', '')
            if 'highway' in name:
                continue
            connected = conn.find('connected')
            if connected is None:
                continue
            return conn.get('id', ''), connected.get('connection', '')

        return '', ''

    @staticmethod
    def _classify(macro: str) -> str:
        """
        Maps a gate macro to a coarse type label.

        Both types cost 1 jump, so this is purely informational (display / future
        weighting). Accelerator macros contain "accelerator"; everything else
        (anc_gate, ter_gate, anim variants) is a standard jump gate.
        """
        return 'accelerator' if 'accelerator' in macro.lower() else 'gate'

    def _reset(self) -> None:
        """Clear per-gate state ready for the next gate."""
        self._object_id    = ''
        self._code         = ''
        self._macro        = ''
        self._sector_macro = ''
