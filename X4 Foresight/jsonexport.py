import json
import pathlib
from collections import Counter, defaultdict

def _build_fleet_summary(player_ships: list[dict]) -> dict:
    """
    Produces a pre-digested summary of the player fleet for the AI export.

    WHY INCLUDE A SUMMARY:
    The AI receives the full individual ship list for detailed reasoning,
    but also benefits from a compact overview it can reference quickly —
    total ships, breakdown by role and size, what ships are in each sector,
    and what orders the fleet is currently executing. This avoids the AI
    having to count and group hundreds of entries itself, and makes the
    prompt more token-efficient.
    """
    by_role   = Counter()
    by_size   = Counter()
    by_order  = Counter()
    by_sector = defaultdict(lambda: defaultdict(int))  # sector → role → count

    for s in player_ships:
        by_role[s["role"]]    += 1
        by_size[s["size"]]    += 1
        by_order[s["order"]]  += 1
        by_sector[s["sector"]][s["role"]] += 1

    return {
        "total":     len(player_ships),
        "by_role":   dict(by_role),
        "by_size":   dict(by_size),
        "by_order":  dict(by_order),
        # Convert nested defaultdicts to plain dicts for JSON serialisation
        "by_sector": {
            sector: dict(roles)
            for sector, roles in by_sector.items()
        },
    }


def _build_npc_summary(npc_ships: list[dict]) -> dict:
    """
    Produces a sector-level summary of NPC ship presence for the AI export.

    WHY SUMMARISE NPC SHIPS:
    At tiers 2 and 3, hundreds of NPC ships may be collected. Including
    every individual entry in the JSON would bloat the prompt significantly.
    We include both the full list (for completeness) and this summary so
    the AI can quickly assess threat levels per sector without parsing
    the entire list.
    """
    # Structure: sector → faction → role → count
    by_sector = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))

    for s in npc_ships:
        by_sector[s["sector"]][s["owner"]][s["role"]] += 1

    # Convert nested defaultdicts to plain dicts for JSON serialisation
    return {
        sector: {
            faction: dict(roles)
            for faction, roles in factions.items()
        }
        for sector, factions in by_sector.items()
    }


def export_json(data: dict):
    """
    Exports all extracted game data as a structured JSON file, saved in the
    same folder as the script that calls this function.

    STRUCTURE OF THE OUTPUT:
    The JSON is organised to be as useful as possible for an AI prompt:

      player_name, player_sector, player_credits
        — Basic identity and financial context.

      stations
        — Full list of player stations with sector, production, and code.

      reputation
        — All faction standings with base, booster, total, and tier label.

      ships.player_ships
        — Full detail on every player ship: code, name, size, role, sector,
          current order, hull origin, pilot name and skills, software.

      ships.fleet_summary
        — Pre-digested overview: totals by role, size, order, and sector.
          Lets the AI quickly answer "what miners do I have and where?"
          without counting individual entries.

      ships.npc_ships
        — Full NPC ship entries (tiers 2/3 only; empty list at tier 1).

      ships.npc_summary
        — Sector → faction → role counts for NPC presence.
          Empty dict at tier 1.

    WHY __file__ FOR THE OUTPUT PATH:
    Using pathlib.Path(__file__).parent ensures the JSON is always written
    next to jsonexport.py itself — i.e. in the script folder — regardless
    of the working directory the user runs the script from.
    """
    # Build ship summaries from the collected ship data.
    # We do this here rather than in ships.py so that jsonexport owns the
    # shape of the export and ships.py stays focused on scanning.
    ships_data   = data.get("ships", {})
    player_ships = ships_data.get("player_ships", [])
    npc_ships    = ships_data.get("npc_ships",    [])

    export = {
        "player_name":    data.get("player_name"),
        "player_sector":  data.get("player_sector"),
        "player_credits": data.get("player_credits"),
        "stations":       data.get("stations", []),
        "reputation":     data.get("reputation", []),
        "ships": {
            # Full individual ship records for detailed AI reasoning
            "player_ships":  player_ships,
            # Pre-digested fleet overview — role/size/order/sector counts
            "fleet_summary": _build_fleet_summary(player_ships),
            # NPC ships in monitored sectors (empty at tier 1)
            "npc_ships":     npc_ships,
            # Sector-level NPC presence summary (empty at tier 1)
            "npc_summary":   _build_npc_summary(npc_ships),
        },
    }

    out_path = pathlib.Path(__file__).parent / "x4_empire_state.json"
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(export, f, indent=2)

    print(f"\n[Export] Saved to: {out_path.name}")
    print("  Paste the contents of x4_empire_state.json into an AI prompt for advice.")