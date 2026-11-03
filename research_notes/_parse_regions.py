import json, re, urllib.parse as u
d = json.load(open("research_notes/warehouse-store-call-1.json", encoding="utf-8"))
b = d["fullBody"]
j = json.loads(b)
tpl = j.get("modalTemplate", "")
m = re.findall(r'value="([A-Z]+-[A-Z]+)"\s+data-href="([^"]+)"', tpl)
print("REGIONS_IN_MODAL", len(m))
for r, href in m:
    print(r, u.unquote(href))
