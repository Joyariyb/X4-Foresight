import xml.etree.ElementTree as ET
import os

def parse_player_data():
    # Hardcoded target to bypass the file name prompt bottleneck
    file_name = "save_001.xml"
    
    # Fail-safe check to ensure the unzipped XML file is present in the local directory
    if not os.path.isfile(file_name):
        print(f"Error: Could not find the file '{file_name}' in this folder.")
        print("Please make sure your unzipped save is named exactly 'save_001.xml' and is in the same directory as this script.")
        input("\nPress Enter to exit...")
        return

    print(f"\n[Scanning] Scanning full empire infrastructure from: {file_name}... Please wait.")
    player_cash = None
    player_name = None
    in_player_faction = False
    
    # A clean list array to hold our discovered station names safely without overwriting data
    station_names = []
    
    try:
        # Open the raw unzipped XML text stream using standard UTF-8 encoding
        with open(file_name, 'r', encoding='utf-8', errors='ignore') as f:
            # Initialize the incremental parser to stream data line-by-line and save RAM
            context = ET.iterparse(f, events=('start', 'end'))
            event, root = next(context)
            
            for event, elem in context:
                
                # === PHASE 1: TARGETING LOGIC FOR PLAYER PROFILE ===
                
                # Check for the main player profile block to grab the pilot's custom identity name
                if event == 'start' and elem.tag == 'player':
                    # PARAMETER GUARD: Only save the name if our variable is currently empty.
                    # This prevents later blank tags from overwriting "Val Selton".
                    if not player_name:
                        player_name = elem.get('name')
                
                # Identify the start of the explicit player faction wrapper block
                if event == 'start' and elem.tag == 'faction' and elem.get('id') == 'player':
                    in_player_faction = True
                
                # Extract the exact liquid money balance attribute nested safely inside our faction block
                if in_player_faction and event == 'start' and elem.tag == 'account':
                    if not player_cash:
                        player_cash = elem.get('amount') or elem.get('balance')
                
                # Turn off the faction tracking flag once the parser reaches the end of our faction block
                if event == 'end' and elem.tag == 'faction' and elem.get('id') == 'player':
                    in_player_faction = False
                
                # === PHASE 2: COMPREHENSIVE LOGIC FOR EMPIRE STATIONS ===
                
                # Match player-owned attributes directly on the 'start' event of a component tag
                if event == 'start' and elem.tag == 'component':
                    # Verify direct player ownership on the component tag itself
                    if elem.get('owner') == 'player':
                        comp_class = elem.get('class')
                        macro_attr = elem.get('macro', '') if elem.get('macro') else ''
                        
                        # Accept stations, factories, or headquarters complexes
                        if comp_class in ['station', 'factory', 'headquarters'] or 'station' in macro_attr:
                            
                            # PARAMETER FIX: Try standard name first, fallback to basename/code if unique/localized
                            name_attr = elem.get('name')
                            
                            if not name_attr:
                                base_name = elem.get('basename')
                                station_code = elem.get('code', 'UNKNOWN-ID')
                                
                                # If it's our explicit Player HQ macro, give it a clean display name
                                if "headquarters" in macro_attr:
                                    name_attr = f"Player Headquarters ({station_code})"
                                elif base_name:
                                    name_attr = f"Special Faction Station ({station_code})"
                                else:
                                    name_attr = f"Unnamed Asset Plot ({station_code})"
                            
                            # If a valid name string exists and isn't a duplicate, append it to our array
                            if name_attr and name_attr not in station_names:
                                station_names.append(name_attr)
                
                # Vital memory flush: flushes individual processed text lines to prevent RAM crashes
                elem.clear()
                
    except Exception as e:
        # Safety error handling fallback to catch any formatting anomalies inside the 700MB file
        print(f"Variable parsing error: {e}")
        input("\nPress Enter to exit...")
        return

    # === DISPLAY THE FINAL COMPILED DATA PAYLOAD ===
    print("\n" + "="*50)
    print("         EMPIRE DATA PIPELINE: V5.4 SUCCESS    ")
    print("="*50)
    print(f"PILOT IDENTITY:       {player_name if player_name else 'Unknown Pilot'}")
    
    if player_cash:
        try:
            print(f"ACTUAL PLAYER CAPITAL: {int(player_cash):,} Credits")
        except ValueError:
            print(f"ACTUAL PLAYER CAPITAL: {player_cash} Credits")
    else:
        print("Error: Player faction account node variable not found.")
        
    print("-"*50)
    print("FOUND EMPIRE STATIONS:")
    if station_names:
        for name in station_names:
            print(f" -> {name}")
    else:
        print(" -> No player stations detected in this save file.")
    print("="*50)
    input("\nPipeline clear. Press Enter to exit...")

if __name__ == "__main__":
    parse_player_data()
