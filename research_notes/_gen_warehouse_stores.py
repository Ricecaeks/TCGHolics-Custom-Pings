import json, pathlib, re

raw = json.load(open("research_notes/warehouse-findstores.json", encoding="utf-8"))
stores = raw["stores"]["stores"]

# Sanity: every region code we've seen in the widget must appear here
seen_regions = ["NZ-NTL","NZ-AUK","NZ-WKO","NZ-BOP","NZ-GIS","NZ-TKI","NZ-MWT","NZ-HKB","NZ-WGN","NZ-TAS","NZ-MBH","NZ-WTC","NZ-CAN","NZ-OTA","NZ-STL"]
present = {s["stateCode"] for s in stores}
missing = [r for r in seen_regions if r not in present]
print("total stores:", len(stores), "| missing regions:", missing)

out = {
    "_source": "https://www.thewarehouse.co.nz/on/demandware.store/Sites-twl-Site/default/Stores-FindStores?showMap=false&radius=2000&postalCode=0610 (captured 2026-11-03)",
    "_note": "store_id is the numeric ID from Stores-FindStores, matching the region payload's c-full-store-details-<id>. region_code is stateCode (NZ-AUK, etc.) and is the value used in /products/stores/region?region=...",
    "stores": [
        {
            "store_id": str(s["ID"]),
            "name": s["name"],
            "region": s.get("city") or "",
            "region_code": s["stateCode"],
            "address": s.get("fullAddress"),
            "phone": s.get("phone"),
        }
        for s in stores
    ]
}

path = pathlib.Path("tcgpings/retailers/data/warehouse_stores.json")
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
print("wrote", path, "with", len(out["stores"]), "stores")
