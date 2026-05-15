import json
import pathlib

def export_json(data: dict):
    """
    Exports all extracted data as a structured JSON file,
    saved in the same folder as the script that calls this function.
    """
    # __file__ here refers to jsonexport.py itself,
    # so we use its parent folder as the output location
    out_path = pathlib.Path(__file__).parent / "x4_empire_state.json"
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    print(f"\n[Export] Saved to: {out_path.name}")
    print("  Paste the contents of x4_empire_state.json into an AI prompt for advice.")