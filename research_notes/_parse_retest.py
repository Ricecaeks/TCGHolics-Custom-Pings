import json, re
from collections import Counter
d = json.load(open("research_notes/warehouse-retest-r3098657.json", encoding="utf-8"))
j = json.loads(d["auckland"]["body"])
sh = j.get("stores", "")
pairs = re.findall(r'<h6 class="title mb-xs">\s*([^<]+?)\s*</h6>.*?store-availability__([A-Z_]+)', sh, re.S)
print("auckland stores:", len(pairs))
print("auckland counts:", dict(Counter(s for _, s in pairs)))
print("in stock:", [n for n, s in pairs if s == "IN_STOCK"])
w = d.get("westland", {})
print("westland status:", w.get("status"), "len:", w.get("len"))
if w.get("body"):
    try:
        jw = json.loads(w["body"])
    except json.JSONDecodeError:
        # truncated slice saved; still scan the raw text
        jw = {"stores": w["body"]}
    nw = re.findall(r'store-availability__([A-Z_]+)', jw.get("stores", ""))
    pairs_w = re.findall(r'<h6 class="title mb-xs">\s*([^<]+?)\s*</h6>.*?store-availability__([A-Z_]+)', jw.get("stores",""), re.S)
    print("westland stores:", len(pairs_w), "counts:", dict(Counter(s for _, s in pairs_w)))
    print("westland in stock:", [n for n, s in pairs_w if s == "IN_STOCK"])
