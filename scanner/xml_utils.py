from __future__ import annotations


def norm_id(raw: str) -> str:
    """
    Normalise an economy-log component id to bracketed-hex form '[0xNN]'.

    X4 writes object ids two different ways in trade-log rows:
      '[0x1234]' — bracketed hex   (persistent components still in the save)
      '853'      — plain decimal   (connection-wrapper ids and removed objects)

    Both index the same component-id space, so a single trade can reference the
    same object in either form depending on the row. We canonicalise to '[0xNN]'
    so lookups against the player-station / player-ship / npc-station id sets are
    consistent no matter which form a given row happened to use.
    """
    if not raw or raw.startswith('['):
        return raw
    try:
        return f'[{hex(int(raw))}]'
    except (ValueError, TypeError):
        return raw


def iter_station_components(root):
    """
    Yields every <component> element in root's subtree, skipping ship subtrees.

    Used by station and budget parsing to walk a station element's modules
    without accidentally including equipment from ships physically docked
    inside the station. The moment a ship_* class component is encountered,
    that ship and ALL of its children are skipped entirely — their cargo,
    crew, and modules belong to them, not to the parent station.

    Uses an explicit stack rather than recursion to handle the deep nesting
    typical of large player stations without hitting Python's recursion limit.
    """
    stack = list(root)
    while stack:
        node = stack.pop()
        if node.tag != 'component':
            # Non-component element — descend into its children
            stack.extend(node)
            continue
        if node.get('class', '').startswith('ship_'):
            # Ship component — skip entirely (don't yield, don't descend)
            continue
        yield node
        stack.extend(node)
