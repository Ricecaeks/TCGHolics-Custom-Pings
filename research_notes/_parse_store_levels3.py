import json, re
from collections import Counter
raw = open("research_notes/warehouse-region-auckland-full.json", encoding="utf-8").read()
obj = json.loads(raw)
payload = json.loads(obj["regionBody"])   # regionBody is the region JSON text
stores_html = payload.get("stores", "")
print("action", payload.get("action"), "| region", payload.get("region"), "| stores_html_len", len(stores_html))
stores = re.findall(r'<h6 class="title mb-xs">\s*([^<]+?)\s*</h6>.*?store-availability__([A-Z_]+)', stores_html, re.S)
c = Counter(s[1] for s in stores)
print("STORES_PARSED", len(stores))
print("STATUS_COUNTS", dict(c))
for name, status in stores:
    print(f"  {status:18} {name}")
