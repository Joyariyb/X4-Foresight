"""Temporary — dump raw XML attributes for player station elements. Delete after use."""
import gzip, pathlib, sys
from lxml import etree as ET

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

SAVE_FILE = pathlib.Path(r"C:\Users\lenovo\Documents\Egosoft\X4\53163675\save\save_006.xml.gz")
STATION_CLASSES = {"station", "factory", "headquarters", "complex"}

depth = 0
inside = False
station_depth = None

with gzip.open(SAVE_FILE, 'rb') as f:
    for event, elem in ET.iterparse(f, events=('start', 'end')):
        if event == 'start':
            depth += 1
            if elem.tag == 'component':
                cls   = elem.get('class', '')
                owner = elem.get('owner', '')
                if cls in STATION_CLASSES and owner == 'player' and not inside:
                    inside        = True
                    station_depth = depth
                    print(f"\n--- Station component ---")
                    for k, v in elem.attrib.items():
                        print(f"  {k} = {v!r}")
        elif event == 'end':
            if inside and depth == station_depth:
                inside        = False
                station_depth = None
            elem.clear()
            depth -= 1
