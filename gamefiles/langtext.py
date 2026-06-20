# ──────────────────────────────────────────────────────────────────────────
#  X4 LANGUAGE-FILE TEXT RESOLVER  (t/0001-l044.xml)
# ──────────────────────────────────────────────────────────────────────────
#
# Shared by the data generators (generate_data.py, generate_equipment.py).
# X4 display strings are not stored inline — they are "{page,id}" references
# into the language file, composed at runtime. This module turns those refs
# into the finished display text.
#
# t-file format notes:
#   - "{page,id}" references are the actual display text, composed at runtime.
#   - Leading "(...)" blocks are translator comments — they appear in the
#     RESOLVED value, not the initial ref, so we strip comments after every
#     resolution pass, not just once up front.
#   - "\(" and "\)" are escaped literal parentheses in the resolved text.
#
# The comment regex uses `(?:[^()\\]|\\.)*` so escaped parens like \(Gas\)
# inside a comment (e.g. "(Magnetar \(Gas\) Vanguard)") are treated as
# non-delimiter characters and the whole comment matches cleanly.
# ──────────────────────────────────────────────────────────────────────────

import re

from lxml import etree as ET

from gamefiles.catalog import CatalogIndex

_COMMENT_RE = re.compile(r'(?<!\\)\((?:[^()\\]|\\.)*\)')
_REF_RE = re.compile(r'\{\s*(\d+)\s*,\s*(\d+)\s*\}')


def clean_text(raw: str, texts: dict) -> str:
    """Strips translator comments, resolves {page,id} refs, unescapes parentheses and newlines.

    X4 t-file entries often look like:
        (Behemoth Vanguard){20101,11001} {20111,1101}
    The leading (...) is a translator comment; the refs ARE the actual text.
    The comment appears in the RESOLVED value (not the initial ref), so we must
    strip comments after each resolution pass, not just once up front.
    """
    for _ in range(4):  # 4 passes: enough for one level of ref nesting
        raw = _COMMENT_RE.sub("", raw).strip()   # strip comments from current value
        new = _REF_RE.sub(lambda m: texts.get(f"{m.group(1)}:{m.group(2)}", ""),
                          raw)
        if new == raw:
            break
        raw = new
    return raw.replace(r"\(", "(").replace(r"\)", ")").replace(r"\n", "\n").strip()


def load_texts(idx: CatalogIndex, page_ids: set[str]) -> dict:
    """{"page:id": raw text} for the requested pages of t/0001-l044.xml."""
    root = ET.fromstring(idx.read("t/0001-l044.xml"))
    texts = {}
    for page in root.findall("page"):
        if page.get("id") in page_ids:
            for t in page.findall("t"):
                texts[f"{page.get('id')}:{t.get('id')}"] = t.text or ""
    return texts
