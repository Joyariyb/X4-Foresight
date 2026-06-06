"""
scanner/galaxy_map.py

Builds the galaxy graph from scan results and answers jump-distance queries.

This is a pure derivation step: it takes the Gate and Sector entities the scanner
already collected and produces a weighted adjacency graph, plus BFS helpers. No
file I/O, no DB — the caller (DB writer / exporter / display) decides what to do
with the result.

THE DISTANCE MODEL (verified against X4's in-game trade-range rules)
-------------------------------------------------------------------
A ship's "jumps" range counts gate and accelerator traversals; superhighways do
not count. In hex terms: a cluster is a "big hex", its sectors are "small hexes"
inside it. Crossing into a different big hex (cluster) via a gate/accelerator is
1 jump; moving between small hexes of the same big hex (a superhighway hop within
a cluster) is 0 jumps. So:

    gate / accelerator edge   -> cost 1   (built from paired Gate endpoints)
    same-cluster sector pair  -> cost 0   (superhighway, from shared cluster_macro)

Because costs are only 0 or 1, shortest paths are found with a 0-1 BFS (a deque
where 0-cost edges go to the front and 1-cost edges to the back) — correct and
faster than Dijkstra.
"""
from __future__ import annotations
from collections import deque
from typing import Iterable

from .entities import Gate, Sector

GATE_COST = 1          # a jump gate or orbital accelerator hop
SUPERHIGHWAY_COST = 0  # movement within a cluster (small hex -> small hex)

# adjacency: sector_macro -> list of (neighbour_macro, cost)
Graph = dict[str, list[tuple[str, int]]]


# ─────────────────────────────────────────────────────────────────────────────
#  GRAPH CONSTRUCTION
# ─────────────────────────────────────────────────────────────────────────────

def build_graph(gates: Iterable[Gate], sectors: Iterable[Sector]) -> Graph:
    """
    Build the weighted sector adjacency graph.

    Two edge sources:
      1. Gate pairs (cost 1). Each gate endpoint stores its own connection id and
         its partner's. We index conn_id -> sector across all gates, then for each
         gate emit an edge from its sector to the sector owning the partner conn
         id. Each link appears from both endpoints, so edges are deduped.
      2. Same-cluster pairs (cost 0). Sectors sharing a cluster_macro are within
         one big hex, reachable by superhighway without a jump. We add a 0-cost
         edge for every such pair that is not already directly gate-linked (the
         guard only matters for exotic modded intra-cluster gates; vanilla
         intra-cluster links are always superhighways).
    """
    sectors = list(sectors)
    graph: Graph = {s.sector_macro: [] for s in sectors}

    # ── 1. Gate edges (cost 1) ────────────────────────────────────────────────
    conn_to_sector = {g.conn_id: g.sector_macro for g in gates if g.conn_id}
    gate_pairs: set[frozenset[str]] = set()
    for g in gates:
        far = conn_to_sector.get(g.partner_conn_id)
        if far is None or far == g.sector_macro:
            # Partner endpoint not captured (inactive gate) or a self-loop — skip.
            continue
        pair = frozenset((g.sector_macro, far))
        if pair in gate_pairs:
            continue
        gate_pairs.add(pair)
        graph.setdefault(g.sector_macro, []).append((far, GATE_COST))
        graph.setdefault(far, []).append((g.sector_macro, GATE_COST))

    # ── 2. Same-cluster superhighway edges (cost 0) ───────────────────────────
    by_cluster: dict[str, list[str]] = {}
    for s in sectors:
        by_cluster.setdefault(s.cluster_macro, []).append(s.sector_macro)

    for members in by_cluster.values():
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                a, b = members[i], members[j]
                if frozenset((a, b)) in gate_pairs:
                    continue
                graph.setdefault(a, []).append((b, SUPERHIGHWAY_COST))
                graph.setdefault(b, []).append((a, SUPERHIGHWAY_COST))

    return graph


# ─────────────────────────────────────────────────────────────────────────────
#  DISTANCE QUERIES  (0-1 BFS)
# ─────────────────────────────────────────────────────────────────────────────

def distances_from(
    graph: Graph,
    sources: str | Iterable[str],
    max_jumps: int | None = None,
) -> dict[str, int]:
    """
    Shortest jump distance from one or more source sectors to every reachable
    sector, via 0-1 BFS.

    sources may be a single sector_macro or several (e.g. all sectors that hold
    player assets). With multiple sources the result is the distance to the
    NEAREST source — exactly what "within N jumps of any of my stations" needs.

    max_jumps, if given, prunes the result to sectors within that many jumps.
    """
    if isinstance(sources, str):
        sources = [sources]

    dist: dict[str, int] = {s: 0 for s in sources if s in graph}
    # Each deque item carries its distance so we can discard stale entries
    # (0-1 BFS may enqueue a node more than once before its distance settles).
    dq: deque[tuple[str, int]] = deque((s, 0) for s in dist)

    while dq:
        node, d = dq.popleft()
        if d > dist[node]:
            continue  # stale — a shorter path to this node was already settled
        for neighbour, cost in graph.get(node, ()):
            nd = d + cost
            if nd < dist.get(neighbour, 1 << 30):
                dist[neighbour] = nd
                if cost == SUPERHIGHWAY_COST:
                    dq.appendleft((neighbour, nd))   # 0-cost: explore first
                else:
                    dq.append((neighbour, nd))       # 1-cost: explore later

    if max_jumps is not None:
        return {s: d for s, d in dist.items() if d <= max_jumps}
    return dist


def edges(graph: Graph) -> list[tuple[str, str, int]]:
    """
    Flatten the adjacency graph into a deduped, canonical edge list for storage.

    The graph stores each undirected link twice (a→b and b→a); this returns each
    link once as (sector_a, sector_b, cost) with sector_a < sector_b, so it maps
    straight onto the sector_links table's primary key.
    """
    collapsed: dict[tuple[str, str], int] = {}
    for a, neighbours in graph.items():
        for b, cost in neighbours:
            key = (a, b) if a < b else (b, a)
            collapsed[key] = cost
    return [(a, b, cost) for (a, b), cost in collapsed.items()]


def jump_distance(graph: Graph, a: str, b: str) -> int | None:
    """
    Jumps between two sectors, or None if b is unreachable from a.

    Convenience wrapper over distances_from for one-off lookups; for many
    queries from the same origin, call distances_from once and reuse the dict.
    """
    if a == b:
        return 0
    return distances_from(graph, a).get(b)


# ─────────────────────────────────────────────────────────────────────────────
#  VALIDATION HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def connected_components(graph: Graph) -> list[set[str]]:
    """
    Returns the connected components of the graph, largest first.

    A healthy galaxy is essentially one component; small isolated components flag
    sectors with no built gate (special/story sectors) or a data gap worth a look.
    """
    seen: set[str] = set()
    components: list[set[str]] = []

    for start in graph:
        if start in seen:
            continue
        comp: set[str] = set()
        stack = [start]
        seen.add(start)
        while stack:
            node = stack.pop()
            comp.add(node)
            for neighbour, _ in graph.get(node, ()):
                if neighbour not in seen:
                    seen.add(neighbour)
                    stack.append(neighbour)
        components.append(comp)

    components.sort(key=len, reverse=True)
    return components
