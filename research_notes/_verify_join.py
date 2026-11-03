import json, re
b = open("tests/fixtures/warehouse/region-auckland.json", encoding="utf-8").read()
j = json.loads(b)
# pairs of (detail_id, store_name, status)
blocks = re.findall(r'<div class="store panel">(.*?)(?=<div class="store panel"|$)', j["stores"], re.S)
region_ids = {}
for blk in blocks:
    did = (re.search(r'id="c-full-store-details-(\d+)"', blk) or [None, None])[1]
    name = (re.search(r'<h6 class="title mb-xs">\s*([^<]+?)\s*</h6>', blk) or [None, None])[1]
    region_ids[name] = did
bundle = {s["name"]: s["store_id"] for s in json.load(open("tcgpings/retailers/data/warehouse_stores.json", encoding="utf-8"))["stores"]}
mismatch = {n: (region_ids[n], bundle.get(n)) for n in region_ids if bundle.get(n) != region_ids[n]}
print("region store names:", len(region_ids))
print("bundle has these 22:", all(n in bundle for n in region_ids))
print("id mismatches:", mismatch if mismatch else "NONE")
