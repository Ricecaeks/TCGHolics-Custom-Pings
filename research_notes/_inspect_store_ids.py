import json, re
from collections import Counter
body = open("tests/fixtures/warehouse/region-auckland.json", encoding="utf-8").read()
j = json.loads(body)
sh = j.get("stores", "")
# find every store block
blocks = re.findall(r'<div class="store panel">(.*?)(?=<div class="store panel"|$)', sh, re.S)
print("store blocks:", len(blocks))
for b in blocks:
    name = (re.search(r'<h6 class="title mb-xs">\s*([^<]+?)\s*</h6>', b) or [None,None])[1]
    status = (re.search(r'store-availability__([A-Z_]+)', b) or [None,None])[1]
    # look for any numeric ids on the panel
    ids = re.findall(r'data-(?:store|storeId|store-id)=[\\"\']?([A-Za-z0-9_-]+)', b)
    detail_id = (re.search(r'id="c-full-store-details-(\d+)"', b) or [None,None])[1]
    href = (re.search(r'href="(/stores/[^"]+)"', b) or [None,None])[1]
    print(f"  {status:15} {name!r:30} detail_id={detail_id} data_ids={ids} href={href}")
