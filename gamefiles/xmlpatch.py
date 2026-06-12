# ════════════════════════════════════════════════════════════════════════════
#                       X4 XML DIFF-PATCH APPLIER
# ════════════════════════════════════════════════════════════════════════════
#
# DLC and patch XML files in X4 are often not full documents but *diffs*:
#
#   <diff>
#     <add sel="/wares">             ← XPath to the target node
#       <ware id="bogas" ...>...</ware>   ← children to append there
#     </add>
#     <replace sel="/wares/ware[@id='x']/@volume">12</replace>
#     <remove sel="/wares/ware[@id='y']"/>
#   </diff>
#
# This module applies such a diff to an already-parsed base document. It
# implements the subset of Egosoft's diff format the library files actually
# use (verified against all five DLC wares.xml files, which are 100% <add>
# operations) plus replace/remove for robustness with other libraries:
#
#   <add sel="NODE">        append the op's child elements to NODE
#       pos="prepend"       ...as first children instead
#       pos="before"/"after" ...as siblings before/after NODE
#   <add sel="NODE/@attr">  set attribute (value = op text)
#   <replace sel="NODE">    swap NODE for the op's child element
#   <replace sel="NODE/@attr">  overwrite attribute value
#   <remove sel="NODE">     delete NODE (or attribute for @attr selectors)
#
# Unsupported selectors fail SOFT (warning, op skipped): a future game patch
# using an exotic selector should degrade to slightly-stale data, not crash
# the scanner.
# ════════════════════════════════════════════════════════════════════════════

import re

# Detects selectors that target an attribute rather than an element,
# e.g. "/wares/ware[@id='x']/@volume" → element part + attribute name.
_ATTR_SEL_RE = re.compile(r'^(.*)/@([\w.-]+)$')


def apply_diff(base_root, diff_root, source: str = "?") -> int:
    """
    Applies an X4 <diff> document to a parsed base XML tree, in place.
    Returns the number of operations applied. `source` is only used to make
    warnings traceable to the DLC/patch file they came from.
    """
    applied = 0
    for op in diff_root:
        if not isinstance(op.tag, str):
            continue  # comments / processing instructions

        sel = op.get("sel", "")
        attr_match = _ATTR_SEL_RE.match(sel)
        node_sel = attr_match.group(1) if attr_match else sel

        # lxml's xpath() evaluates the selector against the base document.
        # X4 selectors are plain location paths with [@id='...'] predicates,
        # which lxml supports natively.
        try:
            targets = base_root.xpath(node_sel)
        except Exception:
            targets = []
        if not targets:
            print(f"[xmlpatch] {source}: no match for sel={sel!r} — skipped")
            continue
        target = targets[0]  # X4 diffs address a single node

        if op.tag == "add":
            if attr_match:
                target.set(attr_match.group(2), (op.text or "").strip())
            else:
                pos = op.get("pos", "")
                # Copy the op's children into the base tree. No deepcopy
                # needed: the diff tree is throwaway, so moving nodes is fine.
                children = list(op)
                if pos == "prepend":
                    for i, child in enumerate(children):
                        target.insert(i, child)
                elif pos in ("before", "after"):
                    parent = target.getparent()
                    base = parent.index(target) + (1 if pos == "after" else 0)
                    for i, child in enumerate(children):
                        parent.insert(base + i, child)
                else:  # default: append inside the target
                    target.extend(children)
            applied += 1

        elif op.tag == "replace":
            if attr_match:
                target.set(attr_match.group(2), (op.text or "").strip())
            else:
                parent = target.getparent()
                new_children = list(op)
                if parent is not None and new_children:
                    parent.replace(target, new_children[0])
            applied += 1

        elif op.tag == "remove":
            if attr_match:
                target.attrib.pop(attr_match.group(2), None)
            else:
                parent = target.getparent()
                if parent is not None:
                    parent.remove(target)
            applied += 1

        else:
            print(f"[xmlpatch] {source}: unknown op <{op.tag}> — skipped")

    return applied
