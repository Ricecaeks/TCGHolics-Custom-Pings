import json
import re
from collections import Counter

d = json.load(open("research_notes/warehouse-retest-r3098657.json", encoding="utf-8"))
print("keys:", list(d.keys()))
res = d.get("results", [])
print("regions returned:", len(res))
idre = re.compile(r'id="c-full-store-details-(\d+)"')
sre = re.compile(r"store-availability__([A-Z_]+)")
agg = {}
for r in res:
    if "body" not in r:
        continue
    for b in re.split(r'<div class="store panel">', r["body"])[1:]:
        i = idre.search(b)
        s = sre.search(b)
        if i and s:
            agg.setdefault(i.group(1), s.group(1))
print("total stores:", len(agg))
print("breakdown:", dict(Counter(agg.values())))
print("IN stores:", {k: v for k, v in agg.items() if v in ("IN_STOCK", "LOW_STOCK")})
