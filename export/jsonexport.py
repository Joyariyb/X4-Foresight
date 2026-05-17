import json
import pathlib
from collections import Counter, defaultdict

def _build_fleet_summary(player_ships: list[dict]) -> dict:
    """
    Produces a pre-digested summary of the player fleet for the AI export.
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

    By default, writes to the project root (two levels up from this file:
    export/ → project root). Pass output_dir to override.

    STRUCTURE OF THE OUTPUT:
      player_name, player_sector, player_credits
      stations, reputation
      ships.player_ships, ships.fleet_summary
      ships.npc_ships, ships.npc_summary
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
