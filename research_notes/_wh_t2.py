import sys

sys.path.insert(0, "research_notes")
from _wh_snippets2 import PARSERS, STORE_METHOD

PATH = "tcgpings/retailers/warehouse.py"
src = open(PATH, encoding="utf-8").read()

# 1. class attributes
src = src.replace(
    "    supports_discovery = True\n    stock_in_listings = True\n",
    "    supports_discovery = True\n    stock_in_listings = True\n"
    "    supports_store_stock = True\n"
    "    store_stock_discovers_stores = True\n"
    "    store_stock_interval = 5 * 60\n",
    1,
)

# 2. __init__: load the store bundle
src = src.replace(
    "        self._in_stores: dict[str, Product] = {}\n        self._missing: dict[str, int] = {}\n",
    "        self._in_stores: dict[str, Product] = {}\n        self._missing: dict[str, int] = {}\n"
    "        self._stores = load_stores()\n"
    "        self._region_of = {s[\"store_id\"]: s[\"region_code\"] for s in self._stores}\n",
    1,
)

# 3. list_stores: real stores + the nationwide pseudo store
src = src.replace(
    "    async def list_stores(self) -> list[Store]:\n        return [Store(self.retailer_id, IN_STORES, IN_STORES_NAME)]\n",
    "    async def list_stores(self) -> list[Store]:\n"
    "        stores = [Store(self.retailer_id, s[\"store_id\"], s[\"name\"], s[\"region_code\"]) for s in self._stores]\n"
    "        stores.append(Store(self.retailer_id, IN_STORES, IN_STORES_NAME))\n"
    "        return stores\n",
    1,
)

# 4. store_label: real name when known
src = src.replace(
    "    def store_label(self, store_id: str) -> str:\n        return IN_STORES_NAME\n",
    "    def store_label(self, store_id: str) -> str:\n"
    "        name = next((s[\"name\"] for s in self._stores if s[\"store_id\"] == store_id), None)\n"
    "        return name or (IN_STORES_NAME if store_id == IN_STORES else f\"Store {store_id}\")\n",
    1,
)

# 5. parser helpers before the class
marker = "@register\nclass WarehouseAdapter(RetailerAdapter):"
assert marker in src, "class marker missing"
src = src.replace(marker, PARSERS.strip() + "\n\n\n" + marker, 1)

# 6. store_stock + store_stock_enabled before parse_ref
ref = "    def parse_ref(self, ref: str) -> str:\n"
assert ref in src, "parse_ref marker missing"
src = src.replace(ref, STORE_METHOD + ref, 1)

open(PATH, "w", encoding="utf-8", newline="").write(src)
print("part 2 done")
