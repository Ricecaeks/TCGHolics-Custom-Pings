import json, re
from collections import Counter
raw = open("research_notes/warehouse-region-auckland-full.json", encoding="utf-8").read()
obj = json.loads(raw)
body = obj.get("regionBody") or raw
stores = re.findall(r'<h6 class="title mb-xs">\s*([^<]+?)\s*</h6>.*?store-availability__([A-Z_]+)', body, re.S)
c = Counter(s[1] for s in stores)
print("regionStatus", obj.get("regionStatus"), "regionLen", obj.get("regionLen"))
print("STORES_PARSED", len(stores))
print("STATUS_COUNTS", dict(c))
for name, status in stores:
    print(f"  {status:18} {name}")
