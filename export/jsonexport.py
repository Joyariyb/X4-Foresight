import json
import pathlib
from collections import Counter, defaultdict


def _build_fleet_summary(player_ships: list[dict]) -> dict:
    """
    Produces a pre-digested summary of the player fleet for the AI export.

    WHAT THIS RETURNS:
      A dictionary containing the following keys with their data type and meaning:
        - "total": int - Total number of ships in the fleet
        - "by_role": dict[str, int] - Count of ships by role (e.g., Fighter: 15)
        - "by_size": dict[str, int] - Count of ships by size class (e.g., Light: 8)
        - "by_order": dict[str, int] - Count of ships by order status (e.g., Active: 20)
        - "by_sector": dict[str, dict[str, int]] - Ships grouped by sector → role matrix
          Example: {"Sector 120": {"Fighter": 5, "Corvette": 3}, ...}

    USAGE CONTEXT:
      Used for fleet composition analysis and resource planning. Helps the AI understand
      the overall strength and distribution of player forces across the empire.

    EXAMPLE OUTPUT STRUCTURE:
      {
        "total": 20,
        "by_role": {"Fighter": 15, "Corvette": 5},
        "by_size": {"Light": 8, "Medium": 12},
        "by_order": {"Active": 18, "Maintenance": 2},
        "by_sector": {
          "Sector 100": {"Fighter": 3, "Corvette": 2},
          "Sector 120": {"Fighter": 5, "Corvette": 3},
          ...
        }
      }

    Args:
        player_ships: List of ship dictionaries with 'role', 'size', 'order', and 'sector' keys.

    Returns:
        dict: A structured summary dictionary suitable for AI consumption.
    """
    by_role   = Counter()
    by_size   = Counter()
    by_order  = Counter()
    by_sector = defaultdict(lambda: defaultdict(int))

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
        "by_sector": {
            sector: dict(roles)
            for sector, roles in by_sector.items()
        },
    }


def _build_npc_summary(npc_ships: list[dict]) -> dict:
    """
    Produces a sector-level summary of NPC ship presence for the AI export.

    STRUCTURE OF THE OUTPUT:
      Returns a 3D nested dictionary structured as:
        sector → faction → role count

      Each level is automatically created via nested defaultdicts to handle
      any combination of sectors, factions, and roles that appear in the data.

    HOW TO READ THE OUTPUT:
      Example: {"Sector 120": {"Rebels": {"Fighter": 3, "Bomber": 1}}}
        - Sector 120 contains Rebel forces
        - Rebels have 3 Fighters and 1 Bomber in that sector

    USAGE CONTEXT:
      Used for threat assessment for different regions. Helps the AI understand
      enemy deployments without listing every single NPC ship individually.

    Args:
        npc_ships: List of ship dictionaries with 'sector', 'owner' (faction), and 'role' keys.

    Returns:
        dict: A nested dictionary with structure:
              {sector: {faction: {role: count}, ...}, ...}
    """
    by_sector = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))

    for s in npc_ships:
        by_sector[s["sector"]][s["owner"]][s["role"]] += 1

    return {
        sector: {
            faction: dict(roles)
            for faction, roles in factions.items()
        }
        for sector, factions in by_sector.items()
    }


def export_json(data: dict, output_dir: pathlib.Path | None = None):
    """
    Exports all extracted game data as a structured JSON file.

    The exported data includes raw ship lists plus pre-computed summaries
    of fleet composition and NPC threats. This is designed for feeding into
    AI systems that need to analyze the player's empire state at a glance.

    DEFAULT OUTPUT LOCATION:
      By default, writes to the project root directory (two levels up from this file:
      export/ → project root). You can pass an output_dir argument to override.

    STRUCTURE OF THE OUTPUT:
      {
        "player_name":     str or None,
        "player_sector":   str or None,
        "player_credits":  int or None,
        "stations":        list[dict],
        "reputation":      list[dict],
        "crew":            list[dict],
        "ships": {
          "player_ships":  list[dict] (raw player fleet),
          "fleet_summary": dict       (summary from _build_fleet_summary()),
          "npc_ships":     list[dict] (raw NPC fleet),
          "npc_summary":   dict       (summary from _build_npc_summary()),
        },
      }

    EXAMPLE OUTPUT (when called with sample data):
      [Export] Saved to: C:/Projects/X4Foresight/x4_empire_state.json
      Paste the contents of x4_empire_state.json into an AI prompt for advice.

    Args:
        data: Dictionary containing keys: "player_name", "player_sector", 
              "player_credits", "stations", "reputation", "crew", and "ships".
        output_dir: Optional pathlib.Path to override default output location.

    Returns:
        None (writes file directly and prints confirmation message).
    """
    ships_data   = data.get("ships", {})
    player_ships = ships_data.get("player_ships", [])
    npc_ships    = ships_data.get("npc_ships",    [])

    export = {
        "player_name":    data.get("player_name"),
        "player_sector":  data.get("player_sector"),
        "player_credits": data.get("player_credits"),
        "stations":       data.get("stations", []),
        "reputation":     data.get("reputation", []),
        "crew":           data.get("crew", []),
        "ships": {
            "player_ships":  player_ships,
            "fleet_summary": _build_fleet_summary(player_ships),
            "npc_ships":     npc_ships,
            "npc_summary":   _build_npc_summary(npc_ships),
        },
    }

    # Output goes to the project root by default (parent of the export/ package)
    if output_dir is None:
        output_dir = pathlib.Path(__file__).parent.parent

    out_path = output_dir / "x4_empire_state.json"
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(export, f, indent=2)

    print(f"\n[Export] Saved to: {out_path}")
    print("  Paste the contents of x4_empire_state.json into an AI prompt for advice.")