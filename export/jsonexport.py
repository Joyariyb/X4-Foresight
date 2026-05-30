import json
import math
import pathlib
from collections import Counter, defaultdict


def _build_fleet_summary(player_ships: list[dict]) -> dict:
    """Pre-digests player fleet into role/size/order/sector counts for AI export."""
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
    """Summarises NPC presence as sector → faction → role counts for AI export."""
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


def _build_station_trades(data: dict) -> list[dict]:
    """Returns completed commercial station trades — player station on one side, NPC on the other."""
    history = data.get("trade_history", [])

    def _is_internal(t):
        if t["player_is_buyer"] and t["player_is_seller"]:
            return True
        if t["player_is_buyer"] and t.get("player_ship_is_seller", False):
            return True
        return False

    result = []
    for t in history:
        if not (t["player_is_buyer"] or t["player_is_seller"] or t.get("_homebase_seller_id")):
            continue
        if _is_internal(t) or t.get("_courier_pickup"):
            continue

        station_code = (
            t.get("_homebase_seller_code") or
            (t["buyer_code"]  if t["player_is_buyer"]  else None) or
            (t["seller_code"] if t["player_is_seller"] else None)
        )
        direction = "In" if t["player_is_buyer"] else "Out"
        result.append({
            "station_code":      station_code,
            "direction":         direction,
            "ware":              t["ware"],
            "ware_name":         t["ware_name"],
            "amount":            t["amount"],
            "price_cr":          t["price_cr"],
            "total_cr":          math.floor(t["total_cr"]),
            "time_ago_s":        round(t["time_ago_s"]),
            "counterparty":      t.get("counterparty_station"),
            "ship_code":         t.get("seller_code") if t["player_is_buyer"] else t.get("buyer_code"),
        })

    return result


def _build_in_progress_deliveries(data: dict) -> list[dict]:
    """Returns deliveries where cargo is physically in transit at save time."""
    delivery_dest_index: dict = data.get("delivery_dest_index", {})
    trades = data.get("trades", [])
    if not delivery_dest_index or not trades:
        return []

    trade_by_ship = {t["ship_id"]: t for t in trades if t.get("ship_id")}

    result = []
    for ship_id, dest_id in delivery_dest_index.items():
        t = trade_by_ship.get(ship_id)
        if t:
            result.append({
                "ship_id":    ship_id,
                "ship_code":  t.get("ship_code", ""),
                "dest_id":    dest_id,
                "ware":       t.get("ware", ""),
                "ware_name":  t.get("ware_name", ""),
                "amount":     t.get("amount", 0),
                "price_cr":   t.get("price_cr", 0.0),
                "total_cr":   math.floor(t.get("total_cr", 0.0)),
            })
    return result


def export_json(data: dict, output_dir: pathlib.Path | None = None):
    """Writes x4_empire_state.json to the project root (or output_dir if given)."""
    ships_data   = data.get("ships", {})
    player_ships = ships_data.get("player_ships", [])
    npc_ships    = ships_data.get("npc_ships",    [])

    export = {
        "player_name":             data.get("player_name"),
        "player_sector":           data.get("player_sector"),
        "player_credits":          data.get("player_credits"),
        "stations":                data.get("stations", []),
        "reputation":              data.get("reputation", []),
        "crew":                    data.get("crew", []),
        "station_trades":          _build_station_trades(data),
        "in_progress_deliveries":  _build_in_progress_deliveries(data),
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