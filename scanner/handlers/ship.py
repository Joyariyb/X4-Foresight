"""
v2/scanner/handlers/ship.py

ShipHandler — extracts all player and NPC ships from the save.

Called in two ways by scanner.py:

  on_start()  Fires for EVERY ship component (player and NPC) when its opening
              tag is seen. NPC ships are not buffered, so this is their only
              extraction point. Player ships just save the sector_macro here;
              on_end() does the full extraction once the subtree is in memory.

  on_end()    Fires ONLY for PLAYER SHIPS when the buffered subtree closes.
              Extracts hull, shields, orders, homebase, commander, pilot, crew.
              Also walks carrier subtrees to pull out docked fighters/scouts.

ALL XML attribute names in this file have been verified against save_001.xml.
No guesswork.
"""
from __future__ import annotations
from data.factions   import FACTION_NAMES
from data.ship_stats  import SHIP_STATS    # macro → {max_hull: N}
from data.station_stats import STATION_STATS  # macro → {max_shield: N} — same table for ship shields
from ..entities      import Ship, CrewMember
from ..xml_utils     import iter_station_components
# Ship naming/classification now lives in one shared module. Imported with the
# original underscore aliases so the call sites below stay unchanged.
from ..ship_names    import (
    SIZE_LABELS,
    LANG_REF_RE       as _LANG_REF_RE,
    extract_role      as _extract_role,
    extract_hull_origin as _extract_hull_origin,
    resolve_ship_type as _resolve_ship_type,
    ship_display_name,
)


# ─────────────────────────────────────────────────────────────────────────────
#  LOOKUP TABLES  (verified from save_001.xml)
# ─────────────────────────────────────────────────────────────────────────────

# Maps X4's internal order identifier to a human-readable label shown in the UI.
# Verified from actual order= values seen in save_001.xml.
_ORDER_LABELS: dict[str, str] = {
    "MiningRoutine":     "Mining",
    "MiningCollect":     "Mining (Collecting)",
    "Middleman":         "Trading",
    "TradeRoutine":      "Trading",
    "Trade":             "Trading",
    "TradePerform":      "Trading (Active)",
    "Patrol":            "Patrolling",
    "Escort":            "Escorting",
    "KeepFormation":     "In Formation",
    "Dock":              "Docking",
    "DockAt":            "Docking",
    "DockAndWait":       "Docking",
    "Wait":              "Waiting",
    "MoveWait":          "Waiting",
    "Flee":              "Fleeing",
    "Attack":            "Attacking",
    "Collect":           "Collecting",
    "TerraformMonitor":  "Monitoring",
    "Repair":            "Repairing",
    "Build":             "Building",
    "Supply":            "Supplying",
    "Police":            "Policing",
    "Salvage":           "Salvaging",
    "BoardingOperation": "Boarding",
    "Protect":           "Protecting",
    "ProtectStation":    "Protecting Station",
    "Resupply":          "Resupplying",
    "Explore":           "Exploring",
}

# Ship size classes that can carry docked ships inside their hull.
# X4 only allows docking inside L (resupplier/carrier variants) and XL hulls.
# Checking both avoids hardcoding specific carrier macros.
_CARRIER_CLASSES = frozenset({"ship_l", "ship_xl"})


# ─────────────────────────────────────────────────────────────────────────────
#  MODULE-LEVEL HELPERS  (stateless, called by the handler methods)
#  Ship naming/classification helpers (extract_role/hull_origin/resolve_ship_type
#  and SIZE_LABELS) now live in scanner/ship_names.py — imported above.
# ─────────────────────────────────────────────────────────────────────────────

def _parse_char_macro(macro: str) -> tuple[str | None, str | None]:
    """
    Extracts (faction, gender) from a character macro string.

    X4 character macros follow the pattern:
        character_{faction}_{gender}_{ethnicity}_{role}_{variant}_macro
    e.g. "character_argon_male_asi_pilot_01_macro" → ("argon", "male")

    Returns (None, None) if the macro doesn't match the expected format.
    """
    inner  = macro.removeprefix("character_").removesuffix("_macro")
    parts  = inner.split("_")
    if not parts:
        return None, None

    faction = parts[0] if parts else None
    gender  = parts[1] if len(parts) > 1 and parts[1] in ("male", "female") else None
    return faction, gender


def _parse_hull(
    macro: str,
    ship_elem,
) -> tuple[float | None, float | None, float | None]:
    """
    Returns (hull_hp, hull_max, hull_pct) for a ship.

    X4 only writes <hull value="..."/> when hull is below the maximum.
    Absence of the element means the ship is undamaged — hull_pct = 100.0.
    Maximum hull HP comes from SHIP_STATS[macro]['max_hull'].
    hull_hp is None when the ship is undamaged (X4 doesn't write the element).
    """
    hull_elem = ship_elem.find("hull")
    max_hull  = SHIP_STATS.get(macro, {}).get("max_hull")

    if hull_elem is None:
        # No element → ship is at full health.
        # If we know the max, set pct = 100. Otherwise leave None.
        return None, max_hull, (100.0 if max_hull else None)

    try:
        hull_hp = float(hull_elem.get("value", 0))
    except (ValueError, TypeError):
        return None, max_hull, None

    hull_pct = (hull_hp / max_hull * 100.0) if max_hull else None
    return hull_hp, max_hull, hull_pct


def _parse_shields(
    ship_elem,
) -> tuple[float | None, float | None, float | None]:
    """
    Returns (shield_hp, shield_max, shield_pct) for a ship.

    Shield generators are class="shieldgenerator" components nested inside
    the ship's <connections>. Each generator's maximum comes from
    STATION_STATS[macro]['max_shield'] — ships and stations share the same
    equipment macro namespace so one table serves both.

    X4 only writes <shield value="..."/> on a generator that is below capacity.
    Absence means the generator is at full strength.

    iter_station_components() is used instead of elem.iter() to skip generators
    belonging to ships docked INSIDE a carrier — their shields should not be
    counted toward the carrier's own totals.

    Returns (None, None, None) if the ship has no shield generators installed.
    """
    current   = 0.0
    max_total = 0.0
    found_any = False

    for comp in iter_station_components(ship_elem):
        if not comp.get("class", "").startswith("shieldgenerator"):
            continue
        stats = STATION_STATS.get(comp.get("macro", ""), {})
        if "max_shield" not in stats:
            continue

        found_any = True
        max_cap   = stats["max_shield"]
        sh_elem   = comp.find("shield")

        if sh_elem is not None:
            # Generator has explicit current HP (below maximum).
            try:
                current += float(sh_elem.get("value", max_cap))
            except (ValueError, TypeError):
                current += max_cap
        else:
            # No child element → generator is at full capacity.
            current += max_cap

        max_total += max_cap

    if not found_any:
        return None, None, None

    pct = (current / max_total * 100.0) if max_total else None
    return current, max_total, pct


def _parse_order(ship_elem) -> str:
    """
    Returns a human-readable label for the ship's current active order.

    Priority:
      1. First non-temporary order with state="started" — what the ship is doing right now.
      2. The order marked default="1" — the standing order the ship falls back to.
      3. "Idle" — if neither is found.

    Temporary orders (temp="1") are AI-generated subroutines (e.g. "DockAt
    to deliver cargo") and are skipped so we report the real assignment, not
    a one-off command the AI issued itself.
    """
    orders_elem = ship_elem.find("orders")
    if orders_elem is None:
        return "Idle"

    default_label = None

    for order in orders_elem.findall("order"):
        raw   = order.get("order", "Idle")
        label = _ORDER_LABELS.get(raw, raw)

        if order.get("default") == "1":
            default_label = label

        # A started, non-temporary order is the ship's active task.
        if order.get("state") == "started" and order.get("temp") != "1":
            return label

    return default_label or "Idle"


def _parse_homebase(ship_elem) -> str | None:
    """
    Returns the homebase station's object ID, or None if none is set.

    Trade ships store their assigned station as a component reference inside
    the default order's params. Two order types use different param names:

      TradeRoutine  →  <param name="range"    type="component" value="[0xSTATION]"/>
      Middleman     →  <param name="supplier" type="component" value="[0xSTATION]"/>

    Any other default order type means the ship has no homebase.
    This method requires the full ship subtree to be in memory.
    """
    orders_elem = ship_elem.find("orders")
    if orders_elem is None:
        return None

    for order in orders_elem.findall("order"):
        if order.get("default") != "1":
            continue
        order_type = order.get("order", "")

        if order_type == "TradeRoutine":
            param_name = "range"
        elif order_type == "Middleman":
            param_name = "supplier"
        else:
            # This ship's default order is not a trade assignment — no homebase.
            return None

        for param in order.findall("param"):
            if param.get("name") == param_name and param.get("type") == "component":
                val = param.get("value", "")
                return val if val else None

    return None


def _parse_active_dest(ship_elem) -> str | None:
    """
    Returns the destination station id from a ship's active trading delivery,
    or None if the ship is not mid-delivery.

    When a trade ship is executing a delivery leg, X4 creates a temporary
    DockAt order (verified in save_001.xml on the TDD-486 freighter):

        <order id="[0x684]" order="DockAt" state="critical" temp="1">
          <param name="destination" type="component" value="[0x11c34]"/>
          <param name="trading"     type="integer"   value="1"/>
          ...
        </order>

    Two conditions must both hold for this to be a commercial delivery (not a
    routine dock for repairs, refuel, or a patrol waypoint):
      - a 'destination' param of type="component" giving the target station id
      - a 'trading' param set to "1"

    Note: the order's state may be "started" OR "critical" (an in-progress dock
    that is committed). We accept either; what matters is temp="1" (an AI-issued
    delivery subroutine) plus the trading flag. We only read the FIRST matching
    DockAt — a ship delivers to one place at a time.
    """
    orders_elem = ship_elem.find("orders")
    if orders_elem is None:
        return None

    for order in orders_elem.findall("order"):
        if order.get("order") != "DockAt" or order.get("temp") != "1":
            continue

        dest    = None
        trading = False
        for param in order.findall("param"):
            name = param.get("name", "")
            if name == "destination" and param.get("type") == "component":
                dest = param.get("value", "") or None
            elif name == "trading" and param.get("value") == "1":
                trading = True

        # Only a destination + trading flag together is a commercial delivery.
        if dest and trading:
            return dest

    return None


def _parse_commander(ship_elem) -> str | None:
    """
    Returns the connection reference of this ship's commander, or None.

    In X4, a ship's commander is stored as a <connection connection="commander">
    element inside <connections>, containing a <connected connection="[0xREF]"/>
    child that points at the commander's connection point.

    Verified structure (save_001.xml):
        <connection connection="commander" id="[0x11bab]">
            <connected connection="[0x1ca1f]"/>
        </connection>

    Returns the "connection" attribute of <connected>, which is the reference
    to the commanding entity. This is used for fleet hierarchy display.
    """
    for conn in ship_elem.findall("connections/connection"):
        if conn.get("connection") != "commander":
            continue
        connected = conn.find("connected")
        if connected is not None:
            return connected.get("connection")
    return None


def _parse_pilot(
    ship_elem,
    ship_code:    str,
    sector_macro: str,
    ctx,
) -> str | None:
    """
    Finds the assigned pilot, appends a CrewMember to ctx.crew, and returns
    the pilot NPC component's object ID (for Ship.pilot_id).

    How pilots are stored in the save (verified from save_001.xml):

      1. <control>
           <post id="aipilot" component="[0x11bad]"/>
         </control>
         → The post element gives us the pilot NPC's component ID.

      2. <component class="npc" ... name="Zevin Silsarna" id="[0x11bad]">
           <traits flags="remotecommable">
             <skills management="5" morale="5" piloting="8"/>
           </traits>
           <npcseed seed="..."/>
         </component>
         → Found anywhere in the ship subtree by matching id to the post reference.

    Returns None (without adding to ctx.crew) if:
      - No aipilot post exists on this ship
      - The referenced NPC component is not found
      - The NPC's name attribute is absent or is an unresolved language ref
    """
    # Step 1 — find the aipilot post to get the pilot's component ID.
    control  = ship_elem.find("control")
    pilot_id = None
    if control is not None:
        for post in control.findall("post"):
            if post.get("id") == "aipilot":
                pilot_id = post.get("component")
                break

    if not pilot_id:
        return None

    # Step 2 — find the NPC component with that ID in the ship's subtree.
    for npc in ship_elem.iter("component"):
        if npc.get("id") != pilot_id or npc.get("class") != "npc":
            continue

        # Skip NPCs with unresolved language reference names.
        raw_name = npc.get("name")
        if not raw_name or _LANG_REF_RE.match(raw_name):
            return None

        # Extract skills from <traits><skills>.
        skills    = {}
        traits    = npc.find("traits")
        if traits is not None:
            sk = traits.find("skills")
            if sk is not None:
                for attr in ("piloting", "management", "morale", "engineering", "boarding"):
                    val = sk.get(attr)
                    if val is not None:
                        try:
                            skills[attr] = int(val)
                        except (ValueError, TypeError):
                            pass

        # Extract optional seed for future name-generation lookups.
        seed_elem = npc.find("npcseed")
        seed      = seed_elem.get("seed") if seed_elem is not None else None

        faction, gender = _parse_char_macro(npc.get("macro", ""))

        ctx.crew.append(CrewMember(
            scan_id           = ctx.scan_id,
            role              = "pilot",
            name              = raw_name,
            object_id         = pilot_id,
            seed              = seed,
            assigned_code     = ship_code,
            assigned_type     = "ship",
            sector_macro      = sector_macro,
            faction           = faction,
            gender            = gender,
            skill_piloting    = skills.get("piloting",    0),
            skill_management  = skills.get("management",  0),
            skill_morale      = skills.get("morale",      0),
            skill_engineering = skills.get("engineering", 0),
            skill_boarding    = skills.get("boarding",    0),
        ))

        return pilot_id  # found and registered — return for Ship.pilot_id

    return None  # NPC component not found in subtree


def _extract_crew(
    ship_elem,
    ship_code:    str,
    sector_macro: str,
    ctx,
) -> None:
    """
    Extracts service crew and marines from the <people> block and appends
    CrewMember entries to ctx.crew.

    Service crew and marines are stored as <person> elements with a seed rather
    than as full NPC components with names. We generate sequential placeholder
    names ("Service Crew #2", "Marine #3") because decoding the seed's
    name-generation algorithm requires game runtime tables we don't have.

    Verified structure (save_001.xml):
        <people>
          <person macro="character_argon_male_cau_crew_01_macro" role="service">
            <npcseed seed="16169221965021330704"/>
            <skills engineering="3" morale="2" piloting="1"/>
          </person>
          <person macro="..." role="marine">
            ...
          </person>
        </people>

    Note: skills are a direct child of <person>, NOT inside <traits> — that
    structure is only used for named NPC components (pilots, managers).
    """
    people = ship_elem.find("people")
    if people is None:
        return

    service_count = 0
    marine_count  = 0

    for person in people.findall("person"):
        role = person.get("role", "")
        if role not in ("service", "marine"):
            continue

        # Skills are stored directly as <skills attr="N"/> inside <person>.
        skills = {}
        sk = person.find("skills")
        if sk is not None:
            for attr in ("piloting", "management", "morale", "engineering", "boarding"):
                val = sk.get(attr)
                if val is not None:
                    try:
                        skills[attr] = int(val)
                    except (ValueError, TypeError):
                        pass

        if role == "service":
            service_count += 1
            name = f"Service Crew #{service_count}"
        else:
            marine_count += 1
            name = f"Marine #{marine_count}"

        seed_elem = person.find("npcseed")
        seed      = seed_elem.get("seed") if seed_elem is not None else None
        faction, gender = _parse_char_macro(person.get("macro", ""))

        ctx.crew.append(CrewMember(
            scan_id           = ctx.scan_id,
            role              = role,
            name              = name,
            object_id         = None,   # no component ID for service crew / marines
            seed              = seed,
            assigned_code     = ship_code,
            assigned_type     = "ship",
            sector_macro      = sector_macro,
            faction           = faction,
            gender            = gender,
            skill_piloting    = skills.get("piloting",    0),
            skill_management  = skills.get("management",  0),
            skill_morale      = skills.get("morale",      0),
            skill_engineering = skills.get("engineering", 0),
            skill_boarding    = skills.get("boarding",    0),
        ))


def _extract_docked_ships(
    carrier_elem,
    sector_macro: str,
    ctx,
) -> None:
    """
    Extracts all ships nested inside a carrier's fully-buffered subtree.

    Ships docked inside a carrier are invisible to the main iterparse loop —
    the scanner suppresses dispatch for components nested inside a buffered
    section. This function walks the carrier's complete in-memory tree once
    the closing tag has been reached and extracts each nested ship.

    The extracted ships inherit the carrier's resolved sector_macro because
    docked ships are physically inside the carrier, wherever it is.

    Only called for ship_l and ship_xl carriers since smaller hulls cannot
    carry docked ships in X4.
    """
    for child in carrier_elem.iter():
        # Skip the carrier itself (iter() includes the root element).
        if child is carrier_elem:
            continue

        cls = child.get("class", "")
        if cls not in SIZE_LABELS:  # SIZE_LABELS keys = valid ship classes
            continue

        macro  = child.get("macro",  "")
        code   = child.get("code",   "")
        obj_id = child.get("id",     "")
        owner  = child.get("owner",  "")

        # Non-player ships docked here are VISITORS (e.g. civilian traders parked
        # at a player station). Capture them SHALLOW — identity + docked_at +
        # sector only — so they appear in the station's docked count and the NPC
        # presence panel, without the deep hull/crew walk we do for our own ships.
        if owner != "player":
            v_prefix, v_name = _extract_hull_origin(macro)
            ctx.ships.append(Ship(
                scan_id=ctx.scan_id, object_id=obj_id, code=code, name=None,
                ship_class=cls, size=SIZE_LABELS.get(cls, cls), macro=macro,
                role=_extract_role(macro), owner_id=owner,
                owner_name=FACTION_NAMES.get(owner, owner.title()),
                hull_origin_id=v_prefix, hull_origin_name=v_name,
                sector_macro=sector_macro, order="", homebase_id=None,
                docked_at=carrier_elem.get("id"), commander_id=None,
                under_construction=False, hull_hp=None, hull_max=None, hull_pct=None,
                shield_hp=None, shield_max=None, shield_pct=None,
                cargo_m3=None, cargo_max_m3=None, pilot_id=None,
            ))
            if code:
                ctx.npc_ship_codes[code] = _resolve_ship_type(macro)
            continue

        hull_prefix, hull_name = _extract_hull_origin(macro)
        raw_name = child.get("name")
        custom_name = raw_name if (raw_name and not _LANG_REF_RE.match(raw_name)) else None

        hull_hp, hull_max, hull_pct    = _parse_hull(macro, child)
        shield_hp, shield_max, shd_pct = _parse_shields(child)
        order     = _parse_order(child)
        commander = _parse_commander(child)
        homebase  = _parse_homebase(child)
        pilot_id  = _parse_pilot(child, code, sector_macro, ctx)

        ship = Ship(
            scan_id          = ctx.scan_id,
            object_id        = obj_id,
            code             = code,
            name             = custom_name,
            ship_class       = cls,
            size             = SIZE_LABELS.get(cls, cls),
            macro            = macro,
            role             = _extract_role(macro),
            owner_id         = "player",
            owner_name       = "Player",
            hull_origin_id   = hull_prefix,
            hull_origin_name = hull_name,
            sector_macro     = sector_macro,
            order            = order,
            homebase_id      = homebase,
            docked_at        = carrier_elem.get("id"),  # docked inside this carrier
            commander_id     = commander,
            under_construction = False,
            hull_hp          = hull_hp,
            hull_max         = hull_max,
            hull_pct         = hull_pct,
            shield_hp        = shield_hp,
            shield_max       = shield_max,
            shield_pct       = shd_pct,
            cargo_m3         = None,   # not yet extracted
            cargo_max_m3     = None,
            pilot_id         = pilot_id,
        )

        ctx.ships.append(ship)
        ctx.player_ship_ids.add(obj_id)

        if homebase:
            ctx.homebase_index[obj_id] = homebase
        if code:
            ctx.npc_ship_codes[code] = custom_name or _resolve_ship_type(macro)

        _extract_crew(child, code, sector_macro, ctx)


# ─────────────────────────────────────────────────────────────────────────────
#  HANDLER CLASS
# ─────────────────────────────────────────────────────────────────────────────

class ShipHandler:
    """
    Extracts player ships and NPC ships from the save.

    After the scan completes, the handler has populated:
      ctx.ships           — Ship entities for player and NPC ships
      ctx.player_ship_ids — object IDs of all player-owned ships
      ctx.homebase_index  — ship object_id → homebase station object_id (players only)
      ctx.npc_ship_codes  — ship code → display name (all ships, for trade name resolution)
      ctx.crew            — CrewMember entries for pilots, service crew, and marines
    """

    def __init__(self) -> None:
        # Captured at on_start() for use in on_end(). The sector_macro on the
        # context object is authoritative for the moment each ship tag opens,
        # but it may change during the time a carrier subtree is being buffered
        # (if the save happens to interleave sector/zone elements mid-carrier,
        # which is uncommon but theoretically possible). Saving it at the
        # opening tag is the safe approach.
        self._sector_macro: str = ""

        # ── Streaming DockAt extraction for non-buffered NPC ships ─────────────
        # NPC ships are NOT buffered, so we can't walk their subtree in on_end().
        # Instead we extract the active delivery destination as their <order> and
        # <param> children stream past. This mirrors v1's in_hb_ship machine.
        #
        # WHY THIS IS THE KEY RESOLVER: a free-trader's TradeRoutine range param
        # is a *sector*, not a station — useless for counterparty. But when the
        # ship is mid-delivery it carries an active DockAt order whose
        # destination IS the NPC station it is hauling to. The post-processor
        # applies that destination across all of the ship's logged trades, which
        # is exactly how v1 resolves the bulk of NPC-ship counterparties.
        self._npc_ship_id:  str  = ""    # object_id of the NPC ship being streamed
        self._npc_dockat:   bool = False  # inside an active trading DockAt order
        self._npc_dest:     str  = ""     # destination station id seen so far
        self._npc_trading:  bool = False  # the trading="1" flag was seen
        self._npc_committed: bool = False  # delivery dest already recorded

        # ── Streaming order capture for non-buffered NPC ships ─────────────────
        # NPC ships aren't buffered, so _parse_order() can't be used. Instead we
        # capture the order label as <order> children stream past and write it
        # directly onto the Ship object while it's still in memory.
        self._current_npc_ship: 'Ship | None' = None
        self._npc_order_active:  str = ""   # first started non-temp order label
        self._npc_order_default: str = ""   # default="1" order label (fallback)

    # ── Dispatcher entry points ───────────────────────────────────────────────

    def extract_npc_docked_ships(self, station_elem, station_id: str, ctx) -> None:
        """
        Record ships docked inside an NPC station's buffered subtree.

        Called alongside _npc.on_end() when an NPC station closes. Unlike
        extract_station_docked_ships (which pulls full Ship entities for player
        stations), this only writes ship_id → (code, macro, station_id) into
        ctx.npc_docked_ships. Full entities aren't needed — the postprocessor
        only uses code/macro for name resolution and station_id for counterparty
        attribution, and we don't want to flood ctx.ships with every NPC visitor
        across every NPC station in the galaxy.
        """
        for child in station_elem.iter():
            if child is station_elem:
                continue
            cls = child.get("class", "")
            if cls not in SIZE_LABELS:
                continue
            if child.get("owner", "") == "player":
                continue   # player ships at NPC stations are handled elsewhere
            ship_id = child.get("id", "")
            if ship_id:
                ctx.npc_docked_ships[ship_id] = (
                    child.get("code",  ""),
                    child.get("macro", ""),
                    station_id,
                )

    def extract_station_docked_ships(self, station_elem, ctx) -> None:
        """
        Extract player ships docked INSIDE a player station's buffered subtree.

        Called by the scanner when a player station closes. Ships parked in a
        station's dock piers (connection="dock") are nested inside the buffered
        station, so the main loop never dispatches them and StationHandler's
        iter_station_components() deliberately skips ship_* subtrees. Without
        this, e.g. a self-supply miner docked at its home station is invisible —
        and its internal silicon deliveries can't be classified.

        Reuses the same subtree walk as carrier-docked extraction; only
        player-owned nested ships are taken (civilian visitors are left out, as
        in v1). docked_at is set to the station's id.
        """
        _extract_docked_ships(station_elem, ctx.current_sector_macro, ctx)

    def on_start(self, elem, ctx) -> None:
        """
        Fires for every ship component (player and NPC) when its opening tag is seen.

        NPC ships: the entire extraction happens here — full name, role, size,
        owner, sector. Hull/shield/pilot data is not extracted because doing so
        would require buffering thousands of NPC ships — they are only needed
        for the high-level fleet overview and trade name resolution.

        Player ships: only the sector_macro is captured here. on_end() does
        the full extraction once the subtree is in memory.
        """
        # Always save the sector_macro before it can change.
        self._sector_macro = ctx.current_sector_macro

        owner = elem.get("owner", "")
        if owner == "player":
            # Player ships are buffered; their orders never reach the streaming
            # dispatch. Clear the NPC streaming marker so a stale id can't leak.
            self._npc_ship_id = ""
            # Will be fully handled by on_end() — nothing else to do here.
            return

        # ── NPC ship ──────────────────────────────────────────────────────────
        cls    = elem.get("class", "")
        macro  = elem.get("macro", "")
        code   = elem.get("code",  "")
        obj_id = elem.get("id",    "")

        # Arm the streaming extractors for this NPC ship. Its <order> and <param>
        # children stream past next; on_npc_order/on_npc_param read the active
        # delivery destination AND the current order label from them.
        self._npc_ship_id    = obj_id
        self._npc_dockat     = False
        self._npc_dest       = ""
        self._npc_trading    = False
        self._npc_committed  = False
        self._npc_order_active  = ""
        self._npc_order_default = ""

        hull_prefix, hull_name = _extract_hull_origin(macro)
        type_name = _resolve_ship_type(macro)

        ship = Ship(
            scan_id          = ctx.scan_id,
            object_id        = obj_id,
            code             = code,
            name             = None,           # NPC ships cannot be player-named
            ship_class       = cls,
            size             = SIZE_LABELS.get(cls, cls),
            macro            = macro,
            role             = _extract_role(macro),
            owner_id         = owner,
            owner_name       = FACTION_NAMES.get(owner, owner.title()),
            hull_origin_id   = hull_prefix,
            hull_origin_name = hull_name,
            sector_macro     = self._sector_macro,
            order            = "",   # requires subtree walk — skipped for NPC ships
            homebase_id      = None, # requires subtree walk — skipped for NPC ships
            docked_at        = None,
            commander_id     = None, # requires subtree walk — skipped for NPC ships
            under_construction = False,
            # Hull and shield health require the full subtree (child elements).
            # For NPC ships we don't buffer the subtree, so leave these as None.
            hull_hp          = None,
            hull_max         = None,
            hull_pct         = None,
            shield_hp        = None,
            shield_max       = None,
            shield_pct       = None,
            cargo_m3         = None,
            cargo_max_m3     = None,
            pilot_id         = None,
        )

        ctx.ships.append(ship)
        self._current_npc_ship = ship

        # Register code → display name for trade record name resolution.
        # Trade history entries identify ships by their code (e.g. "WYX-052"),
        # not by object ID. This index lets the trade handler look up names fast.
        if code:
            ctx.npc_ship_codes[code] = type_name

    # ── Streaming DockAt extraction (non-buffered NPC ships) ───────────────────

    def _in_current_npc_ship(self, ctx) -> bool:
        """
        True only while iterparse is directly inside the NPC ship we armed in
        on_start. The stack top must be that exact ship — this guards against
        processing orders of a ship docked *inside* an NPC carrier (whose frame
        would be on top instead), and against stale ids between ships.
        """
        if not self._npc_ship_id:
            return False
        t = ctx.top
        return (
            t is not None
            and t.owner != "player"
            and t.cls in SIZE_LABELS            # a ship class
            and t.object_id == self._npc_ship_id
        )

    def on_npc_order(self, elem, ctx) -> None:
        """
        Fires on every <order> start while streaming (cheap no-op unless we are
        inside the armed NPC ship). Begins capturing when an active trading
        DockAt order opens; any other order ends capture.

        We accept any temp DockAt (state may be "started" or "critical") and rely
        on the destination + trading="1" params to confirm it is a real delivery —
        matching _parse_active_dest() used for buffered player ships.
        """
        if not self._in_current_npc_ship(ctx):
            return

        order_type = elem.get("order", "")

        # ── Delivery destination tracking (existing) ──────────────────────────
        if order_type == "DockAt" and elem.get("temp") == "1":
            self._npc_dockat  = True
            self._npc_dest    = ""
            self._npc_trading = False
        else:
            self._npc_dockat = False

        # ── Order label capture ───────────────────────────────────────────────
        # Mirrors the priority logic of _parse_order(): a started non-temp order
        # is what the ship is doing right now; default="1" is the standing order
        # it falls back to. Active wins over default; first active seen wins.
        label = _ORDER_LABELS.get(order_type, order_type)
        if elem.get("temp") != "1" and elem.get("state") == "started":
            if not self._npc_order_active:
                self._npc_order_active = label
                self._current_npc_ship.order = label
        elif elem.get("default") == "1" and not self._npc_order_active:
            self._npc_order_default = label
            self._current_npc_ship.order = label

    def on_npc_param(self, elem, ctx) -> None:
        """
        Reads the destination + trading flag from an active DockAt order's params
        and records the delivery destination once both are present.
        """
        if self._npc_committed or not self._npc_dockat:
            return
        if not self._in_current_npc_ship(ctx):
            return
        name = elem.get("name", "")
        if name == "destination" and elem.get("type") == "component":
            self._npc_dest = elem.get("value", "") or ""
        elif name == "trading" and elem.get("value") == "1":
            self._npc_trading = True

        # Both pieces present → this is a commercial delivery. Record it.
        # setdefault: the first active DockAt wins, and we never clobber a
        # player-ship entry (keyed by a disjoint id space).
        if self._npc_dest and self._npc_trading:
            ctx.delivery_dest_index.setdefault(self._npc_ship_id, self._npc_dest)
            self._npc_committed = True

    def on_end(self, elem, ctx) -> None:
        """
        Fires for player ships only, when the buffered subtree closes.

        The full ship element (with all children in memory) is passed here.
        Extracts hull, shields, current order, homebase, commander, pilot,
        service crew and marines, then appends a Ship entity to ctx.ships.

        For carrier-class ships (ship_l / ship_xl), also walks the subtree to
        extract ships docked inside the hull.
        """
        obj_id = elem.get("id", "")
        if not obj_id:
            return

        cls   = elem.get("class", "")
        macro = elem.get("macro", "")
        code  = elem.get("code",  "")

        hull_prefix, hull_name = _extract_hull_origin(macro)

        # Resolve the player's custom name (if any).
        # Some ships have a "{20101,22603}"-style language reference in their
        # name attribute — those are unresolved tokens, not real names.
        raw_name    = elem.get("name")
        custom_name = (
            raw_name
            if raw_name and not _LANG_REF_RE.match(raw_name)
            else None
        )

        hull_hp, hull_max, hull_pct        = _parse_hull(macro, elem)
        shield_hp, shield_max, shield_pct  = _parse_shields(elem)
        order     = _parse_order(elem)
        homebase  = _parse_homebase(elem)
        commander = _parse_commander(elem)

        # _parse_pilot both builds the CrewMember and returns the pilot's
        # object ID, which is stored as Ship.pilot_id for the FK relationship.
        pilot_id = _parse_pilot(elem, code, self._sector_macro, ctx)

        ship = Ship(
            scan_id          = ctx.scan_id,
            object_id        = obj_id,
            code             = code,
            name             = custom_name,
            ship_class       = cls,
            size             = SIZE_LABELS.get(cls, cls),
            macro            = macro,
            role             = _extract_role(macro),
            owner_id         = "player",
            owner_name       = "Player",
            hull_origin_id   = hull_prefix,
            hull_origin_name = hull_name,
            sector_macro     = self._sector_macro,
            order            = order,
            homebase_id      = homebase,
            docked_at        = None,  # station-docked ships not yet extracted
            commander_id     = commander,
            under_construction = False,
            hull_hp          = hull_hp,
            hull_max         = hull_max,
            hull_pct         = hull_pct,
            shield_hp        = shield_hp,
            shield_max       = shield_max,
            shield_pct       = shield_pct,
            cargo_m3         = None,   # not yet extracted (requires ware volume table)
            cargo_max_m3     = None,
            pilot_id         = pilot_id,
        )

        ctx.ships.append(ship)
        ctx.player_ship_ids.add(obj_id)

        # Register in homebase index so fleet grouping and trade attribution
        # can find which station this ship is assigned to in O(1).
        if homebase:
            ctx.homebase_index[obj_id] = homebase

        # If this ship is mid-delivery, record where it is taking the cargo.
        # The post-processor uses this to name the counterparty for couriers
        # whose commercial SELL leg has not been logged yet (still in transit).
        active_dest = _parse_active_dest(elem)
        if active_dest:
            ctx.delivery_dest_index[obj_id] = active_dest

        # Register type name for trade record name resolution.
        if code:
            ctx.npc_ship_codes[code] = custom_name or _resolve_ship_type(macro)

        # Extract service crew and marines from the <people> block.
        _extract_crew(elem, code, self._sector_macro, ctx)

        # Carrier-class ships can have fighters/scouts docked inside their hull.
        # Those ships are invisible to the main scanner loop because they are
        # nested components inside the carrier's buffered subtree. We extract
        # them here with the full subtree still in memory.
        if cls in _CARRIER_CLASSES:
            _extract_docked_ships(elem, self._sector_macro, ctx)
