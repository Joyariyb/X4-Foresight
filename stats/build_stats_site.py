# Core role: Generates the static, search-indexable hull/weapon stats site under
# stats/ from resource_library_export() — pure static SHIP_STATS/EQUIPMENT_STATS
# data, no save file or DB involved. Run manually after regenerating
# data/ship_stats.py or data/equipment_stats.py: python stats/build_stats_site.py
#
# DESIGN: generate-and-commit, same pattern as gamefiles/generate_equipment.py —
# review the diff, then commit stats/ + sitemap.xml together.

import html
import pathlib
import sys
from datetime import date, datetime, timezone

# Allow running as a script from anywhere: put the repo root on sys.path.
REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from export.jsonexport import resource_library_export  # noqa: E402

SITE_URL = "https://joyariyb.github.io/X4-Foresight"
OUT_DIR = REPO / "stats"
SITEMAP_PATH = REPO / "sitemap.xml"

# ── Label tables, mirrored from ui/js/resource-library.js + designs-builder.js
# so this static site and the in-app Resource Library never show different
# wording for the same macro. Keep these two in sync by hand if the JS changes.
HULL_TYPE_LABELS = {
    'heavyfighter': 'Heavy Fighter', 'largeminer': 'Large Miner',
    'personalvehicle': 'Personal Vehicle', 'xsdrone': 'XS Drone',
    'smalldrone': 'Small Drone', 'distressdrone': 'Distress Drone',
    'escapepod': 'Escape Pod', 'lasertower': 'Laser Tower',
}
SIZE_WORD = {'xs': 'XS', 's': 'Small', 'm': 'Medium', 'l': 'Large', 'xl': 'Extra Large'}
RACE_FULL_NAMES = {
    'argon': 'Argon', 'paranid': 'Paranid', 'teladi': 'Teladi', 'split': 'Split',
    'terran': 'Terran', 'boron': 'Boron', 'xenon': 'Xenon', 'khaak': "Kha'ak",
    'pirate': 'Pirate', 'yaki': 'Yaki', 'generic': 'Generic',
}
SLOT_LABELS = {
    'weapon': 'Weapon', 'turret': 'Turret', 'shield': 'Shield',
    'engine': 'Engine', 'thruster': 'Thruster',
}
SLOT_LABELS_PLURAL = {
    'weapon': 'Weapons', 'turret': 'Turrets', 'shield': 'Shields',
    'engine': 'Engines', 'thruster': 'Thrusters',
}
# (field, display label, formatter) per slot — the stat block shown on each
# equipment detail page. Mirrors SLOT_STATS in ui/js/designs-builder.js, just
# with every field the catalog carries for that slot, not the compact card subset.
EQUIP_FIELDS = {
    'weapon': [
        ('damage_hull', 'Damage (Hull)', lambda v: f'{v:,}'),
        ('damage_shield', 'Damage (Shield)', lambda v: f'{v:,}'),
        ('damage_hull_while_shielded', 'Damage (Hull, while shielded)', lambda v: f'{v:,}'),
        ('reload_rate', 'Fire Rate', lambda v: f'{v}/s'),
        ('range_m', 'Range', lambda v: f'{v/1000:.1f} km'),
        ('projectile_speed_m_s', 'Projectile Speed', lambda v: f'{v:,} m/s'),
        ('ammo_clip', 'Ammo Clip', lambda v: f'{v:,}'),
        ('ammo_clip_reload_s', 'Clip Reload', lambda v: f'{v} s'),
        ('rotation_speed', 'Rotation Speed', lambda v: f'{v}'),
        ('rotation_accel', 'Rotation Accel', lambda v: f'{v}'),
        ('storage_capacity', 'Missile Storage', lambda v: f'{v:,}'),
        ('damage_rate_burst', 'DPS (Burst)', lambda v: f'{v:,.1f}'),
        ('damage_rate_sustained', 'DPS (Sustained)', lambda v: f'{v:,.1f}'),
        ('time_to_overheat', 'Time to Overheat', lambda v: f'{v} s'),
        ('cooldown_duration', 'Cooldown', lambda v: f'{v} s'),
        ('hull_max', 'Hit Points', lambda v: f'{v:,}'),
    ],
    'shield': [
        ('capacity', 'Capacity', lambda v: f'{v:,}'),
        ('recharge_rate', 'Recharge Rate', lambda v: f'{v:,}/s'),
        ('recharge_delay', 'Recharge Delay', lambda v: f'{v} s'),
        ('disruption_stability', 'Disruption Stability', lambda v: f'{v}'),
        ('hull_max', 'Hit Points', lambda v: f'{v:,}'),
    ],
    'engine': [
        ('thrust_forward', 'Forward Thrust', lambda v: f'{v:,} kN'),
        ('thrust_reverse', 'Reverse Thrust', lambda v: f'{v:,} kN'),
        ('travel_thrust', 'Travel Thrust Multiplier', lambda v: f'{v}x'),
        ('travel_charge', 'Travel Charge Time', lambda v: f'{v} s'),
        ('boost_thrust', 'Boost Thrust Multiplier', lambda v: f'{v}x'),
        ('boost_duration', 'Boost Duration', lambda v: f'{v} s'),
        ('boost_recharge', 'Boost Recharge', lambda v: f'{v} s'),
        ('hull_max', 'Hit Points', lambda v: f'{v:,}'),
    ],
    'thruster': [
        ('strafe', 'Strafe', lambda v: f'{v:,}'),
        ('pitch', 'Pitch', lambda v: f'{v:,}'),
        ('yaw', 'Yaw', lambda v: f'{v:,}'),
        ('roll', 'Roll', lambda v: f'{v:,}'),
    ],
}
EQUIP_FIELDS['turret'] = EQUIP_FIELDS['weapon']


def fmt_credits(n) -> str:
    if n is None:
        return '—'
    n = float(n)
    if n >= 1e6:
        return f'{n/1e6:.1f}M Cr'
    if n >= 1e3:
        return f'{n/1e3:.1f}k Cr'
    return f'{n:,.0f} Cr'


def hull_type_label(t: str) -> str:
    if not t:
        return 'Other'
    return HULL_TYPE_LABELS.get(t, ' '.join(w.capitalize() for w in t.split('_')))


def size_from_class(cls: str) -> str:
    return (cls or '').replace('ship_', '')


def race_label(r: str) -> str:
    r = (r or '').lower()
    return RACE_FULL_NAMES.get(r, r.capitalize() or 'Generic')


def esc(s) -> str:
    return html.escape(str(s)) if s is not None else ''


# ── Page shell ───────────────────────────────────────────────────────────────
# Mirrors index.html's <head> pattern (canonical, description, OG basics) so
# every generated page carries the same SEO scaffolding the root landing page
# already has — search engines shouldn't see a downgrade in metadata quality
# just because a page is generated rather than hand-written.

def page_shell(title: str, description: str, canonical_path: str, body: str) -> str:
    canonical = f'{SITE_URL}/{canonical_path}'
    # canonical_path is "stats/..." relative to repo root; depth below stats/
    # determines how many "../" the stylesheet link needs (0 for stats/index.html,
    # 1 for stats/hulls/index.html or stats/hulls/<macro>.html).
    depth = canonical_path.count('/') - 1
    css_href = '../' * depth + 'assets/stats.css'
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<link rel="canonical" href="{esc(canonical)}">
<meta name="robots" content="index, follow">
<meta property="og:type" content="website">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(description)}">
<meta property="og:url" content="{esc(canonical)}">
<link rel="stylesheet" href="{esc(css_href)}">
</head>
<body>
<div class="wrap">
{body}
</div>
</body>
</html>
'''


def breadcrumb(*crumbs: tuple[str, str]) -> str:
    # crumbs = [(label, href), ...], last one is the current page (no href)
    parts = []
    for i, (label, href) in enumerate(crumbs):
        if href:
            parts.append(f'<a href="{esc(href)}">{esc(label)}</a>')
        else:
            parts.append(f'<span>{esc(label)}</span>')
    return f'<nav class="crumbs">{" / ".join(parts)}</nav>'


def stat_row(label: str, value: str) -> str:
    return f'<div class="stat"><span class="stat-lbl">{esc(label)}</span><span class="stat-val">{esc(value)}</span></div>'


# ── Hull pages ───────────────────────────────────────────────────────────────

def hull_slug(macro: str) -> str:
    return macro


def build_hull_page(macro: str, h: dict) -> str:
    size = size_from_class(h.get('class'))
    type_label = hull_type_label(h.get('ship_type') or '')
    race = race_label(h.get('makerrace'))
    title = f'{h["name"]} — X4: Foundations Hull Stats | X4 Foresight'
    desc = (f'{h["name"]} ({SIZE_WORD.get(size, size.upper())} {type_label}) stats for X4: Foundations — '
            f'{h.get("max_hull", "?"):,} hull, {fmt_credits(h.get("price"))}, '
            f'{h.get("crew_capacity", "?")} crew.')

    cargo_tags = ' / '.join(w.capitalize() for w in (h.get('cargo_tags') or '').split() if w)

    hardpoints = h.get('hardpoints') or {}
    hp_rows = ''.join(
        stat_row(f'{SLOT_LABELS_PLURAL.get(slot, slot.capitalize())} ({size_from_class(cls) or size})', str(count))
        for slot, sizes in hardpoints.items()
        for cls, count in (sizes.items() if isinstance(sizes, dict) else [(size, sizes)])
    ) if isinstance(hardpoints, dict) else ''

    body = f'''
{breadcrumb(('X4 Foresight Stats', '../index.html'), ('Hulls', 'index.html'), (h["name"], None))}
<article>
<h1>{esc(h["name"])}</h1>
<p class="sub">{esc(SIZE_WORD.get(size, size.upper()))} {esc(type_label)} · {esc(race)}{' · Capture Only' if not h.get('purchasable', True) else ''}</p>
<div class="stats-grid">
{stat_row('Hull HP', f'{h.get("max_hull", 0):,}')}
{stat_row('Price', fmt_credits(h.get('price')))}
{stat_row('Crew Capacity', h.get('crew_capacity') if h.get('crew_capacity') is not None else '—')}
{stat_row('Cargo Capacity', f'{h.get("cargo_max"):,} m³' if h.get('cargo_max') is not None else '—')}
{stat_row('Missile Storage', h.get('missile_storage') if h.get('missile_storage') is not None else '—')}
{stat_row('Unit Storage', h.get('unit_storage') if h.get('unit_storage') is not None else '—')}
{stat_row('Weapon Heat Factor', h.get('weapon_heat_factor', 1.0))}
{stat_row('Cargo Types', cargo_tags) if cargo_tags else ''}
</div>
{f'<h2>Hardpoints</h2><div class="stats-grid">{hp_rows}</div>' if hp_rows else ''}
{f'<p class="desc">{esc(h["description"])}</p>' if h.get('description') else ''}
</article>
'''
    return page_shell(title, desc, f'stats/hulls/{macro}.html', body)


def build_hull_index(hulls: dict) -> str:
    rows = []
    for macro, h in sorted(hulls.items(), key=lambda kv: kv[1]['name']):
        size = size_from_class(h.get('class'))
        rows.append(
            f'<tr><td><a href="{esc(macro)}.html">{esc(h["name"])}</a></td>'
            f'<td>{esc(SIZE_WORD.get(size, size.upper()))}</td>'
            f'<td>{esc(hull_type_label(h.get("ship_type") or ""))}</td>'
            f'<td>{esc(race_label(h.get("makerrace")))}</td>'
            f'<td>{fmt_credits(h.get("price"))}</td></tr>'
        )
    body = f'''
{breadcrumb(('X4 Foresight Stats', '../index.html'), ('Hulls', None))}
<article>
<h1>X4: Foundations Hull Stats</h1>
<p class="sub">All {len(hulls)} player-flyable ship hulls in X4: Foundations, with hull HP, price, crew and cargo.</p>
<table class="listing">
<thead><tr><th>Name</th><th>Size</th><th>Type</th><th>Race</th><th>Price</th></tr></thead>
<tbody>
{''.join(rows)}
</tbody>
</table>
</article>
'''
    return page_shell(
        'X4: Foundations Hull Stats — All Ships | X4 Foresight',
        f'Browse hull stats for all {len(hulls)} player-flyable ships in X4: Foundations — hull HP, price, crew, cargo, and hardpoints.',
        'stats/hulls/index.html', body,
    )


# ── Equipment pages ──────────────────────────────────────────────────────────

def build_equipment_page(macro: str, e: dict) -> str:
    slot = e.get('slot', 'equipment')
    size = (e.get('size') or '').lower()
    race = race_label(e.get('race'))
    slot_label = SLOT_LABELS.get(slot, slot.capitalize())
    title = f'{e["name"]} — X4: Foundations {slot_label} Stats | X4 Foresight'
    mk = e.get('mk')
    desc = f'{e["name"]}{f" Mk{mk}" if mk else ""} ({SIZE_WORD.get(size, size.upper())} {slot_label}) stats for X4: Foundations — {fmt_credits(e.get("price"))}.'

    fields = EQUIP_FIELDS.get(slot, [])
    stat_rows = ''.join(
        stat_row(label, fmt(e[key])) for key, label, fmt in fields if e.get(key) is not None
    )

    body = f'''
{breadcrumb(('X4 Foresight Stats', '../index.html'), ('Equipment', 'index.html'), (e["name"], None))}
<article>
<h1>{esc(e["name"])}{f" Mk{mk}" if mk else ""}</h1>
<p class="sub">{esc(SIZE_WORD.get(size, size.upper()))} {esc(slot_label)} · {esc(race)}</p>
<div class="stats-grid">
{stat_row('Price', fmt_credits(e.get('price')))}
{stat_row('Price Range', f'{fmt_credits(e.get("price_min"))} – {fmt_credits(e.get("price_max"))}') if e.get('price_min') is not None else ''}
{stat_rows}
</div>
</article>
'''
    return page_shell(title, desc, f'stats/equipment/{macro}.html', body)


def build_equipment_index(equipment: dict) -> str:
    by_slot: dict[str, list] = {}
    for macro, e in equipment.items():
        by_slot.setdefault(e.get('slot', 'other'), []).append((macro, e))

    sections = []
    for slot in ('weapon', 'turret', 'shield', 'engine', 'thruster'):
        items = sorted(by_slot.get(slot, []), key=lambda kv: kv[1]['name'])
        if not items:
            continue
        rows = ''.join(
            f'<tr><td><a href="{esc(macro)}.html">{esc(e["name"])}</a></td>'
            f'<td>{esc(SIZE_WORD.get((e.get("size") or "").lower(), (e.get("size") or "").upper()))}</td>'
            f'<td>{esc(race_label(e.get("race")))}</td>'
            f'<td>{fmt_credits(e.get("price"))}</td></tr>'
            for macro, e in items
        )
        sections.append(f'''
<h2>{esc(SLOT_LABELS_PLURAL[slot])} ({len(items)})</h2>
<table class="listing">
<thead><tr><th>Name</th><th>Size</th><th>Race</th><th>Price</th></tr></thead>
<tbody>{rows}</tbody>
</table>
''')

    body = f'''
{breadcrumb(('X4 Foresight Stats', '../index.html'), ('Equipment', None))}
<article>
<h1>X4: Foundations Equipment Stats</h1>
<p class="sub">Weapons, turrets, shields, engines and thrusters — {len(equipment)} items total.</p>
<p class="note">Missile-class weapons (missile launchers/turrets) are not yet catalogued and are excluded from this list.</p>
{''.join(sections)}
</article>
'''
    return page_shell(
        'X4: Foundations Equipment Stats — Weapons, Shields, Engines | X4 Foresight',
        f'Browse stats for all {len(equipment)} X4: Foundations weapons, turrets, shields, engines and thrusters.',
        'stats/equipment/index.html', body,
    )


# ── Site hub ─────────────────────────────────────────────────────────────────

def build_site_index(hull_count: int, equip_count: int) -> str:
    body = f'''
<article>
<h1>X4: Foundations Hull &amp; Equipment Stats</h1>
<p class="sub">A reference for every player-flyable ship hull and every catalogued weapon, shield, engine and thruster in X4: Foundations.</p>
<div class="grid">
<a class="card" href="hulls/index.html"><h2>Ship Hulls</h2><p>{hull_count} hulls — hull HP, price, crew, cargo, hardpoints.</p></a>
<a class="card" href="equipment/index.html"><h2>Equipment</h2><p>{equip_count} items — weapons, turrets, shields, engines, thrusters.</p></a>
</div>
<p class="footnote">Generated from the same static game data used by <a href="../ui/web/index.html">X4 Foresight's dashboard</a>. Data is independent of any save file.</p>
</article>
'''
    return page_shell(
        'X4: Foundations Hull & Equipment Stats | X4 Foresight',
        f'Browse hull and equipment stats for X4: Foundations — {hull_count} ship hulls and {equip_count} weapons/shields/engines, sourced from the game files.',
        'stats/index.html', body,
    )


# ── Sitemap ──────────────────────────────────────────────────────────────────

def update_sitemap(paths: list[str]) -> None:
    today = date.today().isoformat()
    existing = SITEMAP_PATH.read_text(encoding='utf-8')
    # Keep the existing root <url> block; drop any previously generated
    # stats/ entries (marked by the STATS_START/STATS_END comment) before
    # writing the current set, so re-runs don't accumulate stale duplicates.
    start_marker = '<!-- STATS_START -->'
    end_marker = '<!-- STATS_END -->'
    base = existing.split(start_marker)[0].rstrip()
    if not base.endswith('</url>'):
        base = existing.split('</urlset>')[0].rstrip()
    entries = '\n'.join(
        f'  <url><loc>{SITE_URL}/{p}</loc><lastmod>{today}</lastmod>'
        f'<changefreq>monthly</changefreq><priority>0.6</priority></url>'
        for p in paths
    )
    new_sitemap = f'{base}\n{start_marker}\n{entries}\n{end_marker}\n</urlset>\n'
    SITEMAP_PATH.write_text(new_sitemap, encoding='utf-8')


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    data = resource_library_export()
    hulls = data['hull_catalog']
    equipment = data['equipment_catalog']

    (OUT_DIR / 'hulls').mkdir(parents=True, exist_ok=True)
    (OUT_DIR / 'equipment').mkdir(parents=True, exist_ok=True)

    sitemap_paths = ['stats/index.html', 'stats/hulls/index.html', 'stats/equipment/index.html']

    (OUT_DIR / 'index.html').write_text(build_site_index(len(hulls), len(equipment)), encoding='utf-8')
    (OUT_DIR / 'hulls' / 'index.html').write_text(build_hull_index(hulls), encoding='utf-8')
    (OUT_DIR / 'equipment' / 'index.html').write_text(build_equipment_index(equipment), encoding='utf-8')

    for macro, h in hulls.items():
        (OUT_DIR / 'hulls' / f'{macro}.html').write_text(build_hull_page(macro, h), encoding='utf-8')
        sitemap_paths.append(f'stats/hulls/{macro}.html')

    for macro, e in equipment.items():
        (OUT_DIR / 'equipment' / f'{macro}.html').write_text(build_equipment_page(macro, e), encoding='utf-8')
        sitemap_paths.append(f'stats/equipment/{macro}.html')

    update_sitemap(sitemap_paths)

    print(f'Generated {len(hulls)} hull pages, {len(equipment)} equipment pages, '
          f'3 index pages, and {len(sitemap_paths)} sitemap entries.')


if __name__ == '__main__':
    main()
