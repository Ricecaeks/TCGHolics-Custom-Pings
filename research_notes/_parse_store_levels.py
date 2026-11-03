import json, re
d = json.load(open("research_notes/warehouse-region-auckland.json", encoding="utf-8"))
j = json.loads(d["aukBody"]) if d.get("aukBody") else d
# d itself IS the saved script-output object; the payload is embedded in aukBody (truncated).
# Re-parse whatever store panels we have.
stores = re.findall(r'<h6 class="title mb-xs">([^<]+)</h6>.*?store-availability__([A-Z_]+)', d.get("aukBody",""), re.S)
from collections import Counter
c = Counter(s[1] for s in stores)
print("STORES_PARSED", len(stores))
print("STATUS_COUNTS", dict(c))
for name, status in stores:
    print(f"  {status:16} {name}")
