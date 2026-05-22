"""
GENERATE STATION NAMES — One-time utility script
=================================================
Reads wares.xml and the language file to produce a hardcoded
WARE_FACTORY_NAMES lookup, written to data/station_names.py.

Run from the project root:
    python tools/generate_station_names.py

REQUIRED INPUTS:
    XML Library/libraries/wares.xml   — ware defs with group + factoryname refs
    0001-l044.xml                     — language file containing page 20201

OUTPUT:
    data/station_names.py             — WARE_FACTORY_NAMES: ware_id → factory name

HOW IT WORKS:
    Each economy ware in wares.xml carries two text refs on page 20201:
        name="{20201,N}"        → display name        e.g. "Hull Parts"
        factoryname="{20201,M}" → individual factory   e.g. "Hull Part Factory"

    When a station produces only ONE unique ware type, X4 uses the individual
    factoryname (e.g. "Microchip Factory", "Solar Power Plant").
    When it produces multiple ware types it falls back to the group name on
    page 20215 (e.g. "High Tech Factory", "Energy Complex").

    This generator extracts all individual factory names so station_naming.py
    can implement the single/multi-product rule correctly.
"""

import pathlib
import re
import xml.etree.ElementTree as ET

# ── Paths ─────────────────────────────────────────────────────────────────────
# __file__ is tools/generate_station_names.py, so .parent.parent = project root.
ROOT      = pathlib.Path(__file__).parent.parent
WARES_XML = ROOT / "XML Library" / "libraries" / "wares.xml"
LANG_XML  = ROOT / "0001-l044.xml"
OUTPUT    = ROOT / "data" / "station_names.py"

# ── Constants ─────────────────────────────────────────────────────────────────

# Matches "{page,id}" language file references such as "{20201,104}".
_REF_RE = re.compile(r'^\{(\d+),(\d+)\}$')

# Preferred group ordering for the output dict.
# Matches WARE_GROUP_PRIORITY in data/wares.py (lower index = higher priority).
# Groups not listed here will still be included — they sort after the known ones.
_GROUP_ORDER = [
    'hightech', 'shiptech', 'refined', 'minerals', 'gases',
    'pharma', 'pharmaceutical', 'agricultural', 'food', 'ice', 'energy', 'water',
]

# Section header comments in the generated file.
_GROUP_LABELS: dict[str, str] = {
    'hightech':       'High Tech Goods (wares.xml group="hightech")',
    'shiptech':       'Ship Technology (wares.xml group="shiptech")',
    'refined':        'Refined Goods   (wares.xml group="refined")',
    'minerals':       'Minerals        (wares.xml group="minerals")',
    'gases':          'Gases           (wares.xml group="gases")',
    'pharma':         'Pharmaceutical Goods (wares.xml group="pharma")',
    'pharmaceutical': 'Pharmaceutical Goods (wares.xml group="pharmaceutical")',
    'agricultural':   'Agricultural Goods   (wares.xml group="agricultural")',
    'food':           'Food            (wares.xml group="food")',
    'ice':            'Ice             (wares.xml group="ice")',
    'energy':         'Energy          (wares.xml group="energy")',
    'water':          'Water           (wares.xml group="water")',
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_page(lang_path: pathlib.Path, page_id: str) -> dict[str, str]:
    """Parses one page from the language file. Returns {textId: text}."""
    texts = {}
    tree  = ET.parse(lang_path)
    root  = tree.getroot()
    for page in root.findall('page'):
        if page.get('id') == page_id:
            for t in page.findall('t'):
                tid  = t.get('id', '')
                text = (t.text or '').strip()
                if text:
                    texts[tid] = text
            break
    return texts


def resolve(ref: str, texts: dict[str, str]) -> tuple[str, str, str]:
    """
    Parses a '{page,id}' ref and looks up its text.

    Returns (page_id, text_id, resolved_text).
    If the ref can't be parsed all three values are empty strings.
    """
    m = _REF_RE.match(ref or '')
    if not m:
        return '', '', ''
    page_id = m.group(1)
    text_id = m.group(2)
    text    = texts.get(text_id, f'<missing text_id={text_id}>')
    return page_id, text_id, text


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:

    # 1. Load language page 20201 ─────────────────────────────────────────────
    print(f"Loading {LANG_XML.name} page 20201...")
    p20201 = load_page(LANG_XML, '20201')
    print(f"  {len(p20201)} entries loaded.\n")

    # 2. Parse wares.xml ───────────────────────────────────────────────────────
    print(f"Parsing {WARES_XML}...")
    tree = ET.parse(str(WARES_XML))
    root = tree.getroot()

    rows: list[dict] = []
    skipped_page  = 0   # factoryname ref not on page 20201
    skipped_none  = 0   # no factoryname attribute at all

    for ware in root.findall('ware'):
        factory_ref = ware.get('factoryname', '')
        if not factory_ref:
            skipped_none += 1
            continue

        name_ref = ware.get('name', '')

        n_page, n_tid, n_text = resolve(name_ref,    p20201)
        f_page, f_tid, f_text = resolve(factory_ref, p20201)

        # Only keep production economy wares — both refs must be on page 20201.
        # Equipment, ship parts, and software wares use other pages.
        if n_page != '20201' or f_page != '20201':
            skipped_page += 1
            continue

        rows.append({
            'ware_id':      ware.get('id', ''),
            'group':        ware.get('group', 'unknown'),
            'name_tid':     n_tid,
            'name_text':    n_text,
            'factory_tid':  f_tid,
            'factory_text': f_text,
        })

    print(f"  {len(rows)} production wares found with factoryname on page 20201.")
    print(f"  {skipped_none} wares had no factoryname (equipment, ships, etc.).")
    print(f"  {skipped_page} wares had factoryname on a non-20201 page (skipped).\n")

    # Sort by preferred group order, then alphabetically within each group.
    group_rank = {g: i for i, g in enumerate(_GROUP_ORDER)}
    rows.sort(key=lambda r: (group_rank.get(r['group'], 99), r['ware_id']))

    # 3. Print console table ───────────────────────────────────────────────────
    col_w = max(len(r['ware_id'])   for r in rows)
    grp_w = max(len(r['group'])     for r in rows)
    ntx_w = max(len(r['name_text']) for r in rows)

    header = (
        f"{'ware_id':<{col_w}}  {'group':<{grp_w}}  "
        f"{'name_id':>7}  {'display name':<{ntx_w}}  "
        f"{'fact_id':>7}  factory name"
    )
    print(header)
    print("-" * len(header))
    for r in rows:
        print(
            f"{r['ware_id']:<{col_w}}  {r['group']:<{grp_w}}  "
            f"{r['name_tid']:>7}  {r['name_text']:<{ntx_w}}  "
            f"{r['factory_tid']:>7}  {r['factory_text']}"
        )

    # Report any group values not in _GROUP_ORDER so we can add them
    unknown_groups = {r['group'] for r in rows if r['group'] not in group_rank}
    if unknown_groups:
        print(f"\n[Warning] Unknown groups (not in _GROUP_ORDER): {sorted(unknown_groups)}")
        print("  Add these to _GROUP_ORDER and _GROUP_LABELS if needed.")

    # 4. Write data/station_names.py ──────────────────────────────────────────
    lines = [
        '# ─────────────────────────────────────────────────────────────────────────────',
        '#  INDIVIDUAL WARE FACTORY NAMES',
        '#  Generated by tools/generate_station_names.py — do not edit by hand.',
        '#',
        '#  Source files:',
        '#    XML Library/libraries/wares.xml    — factoryname="{20201,N}" per <ware>',
        '#    0001-l044.xml  page 20201          — text for each N',
        '#',
        '#  HOW THIS IS USED:',
        '#    scanner/station_naming.py applies the single/multi-product naming rule:',
        '#      • 1 unique ware produced → WARE_FACTORY_NAMES[ware_id].name  (this dict)',
        '#      • 2+ unique wares        → group name from data/wares.py WARE_GROUPS',
        '#        which resolves to the page 20215 group factory name.',
        '#',
        '#  The .text_id field stores the page 20201 textId so callers can build or',
        '#  match "{20201,N}" references found in save file attributes, e.g.:',
        '#      ref = f"{20201,{WARE_FACTORY_NAMES[ware_id].text_id}}"',
        '#',
        '#  To regenerate after installing DLC or updating the language file:',
        '#      python tools/generate_station_names.py',
        '# ─────────────────────────────────────────────────────────────────────────────',
        '',
        'from typing import NamedTuple',
        '',
        '',
        'class FactoryEntry(NamedTuple):',
        '    """Factory name and its page 20201 text ID from 0001-l044.xml."""',
        '    name:    str  # display string, e.g. "Hull Part Factory"',
        '    text_id: int  # page 20201 text ID — matches "{20201,N}" refs in save files',
        '',
        '',
        'WARE_FACTORY_NAMES: dict[str, FactoryEntry] = {',
    ]

    current_group: str | None = None
    for r in rows:
        # Print a section comment whenever the group changes
        if r['group'] != current_group:
            current_group = r['group']
            if len(lines) > 1 and lines[-1] != '':
                lines.append('')
            label = _GROUP_LABELS.get(current_group, f'(wares.xml group="{current_group}")')
            lines.append(f'    # {label}')

        # FactoryEntry(name, text_id) — display name textId annotated in the comment
        lines.append(
            f'    "{r["ware_id"]}": FactoryEntry("{r["factory_text"]}", {r["factory_tid"]}),'
            f'  # display: "{r["name_text"]}" (id {r["name_tid"]})'
        )

    lines += ['', '}', '']

    OUTPUT.write_text('\n'.join(lines), encoding='utf-8')
    print(f"\nWrote {len(rows)} entries -> {OUTPUT.relative_to(ROOT)}")


if __name__ == '__main__':
    main()
