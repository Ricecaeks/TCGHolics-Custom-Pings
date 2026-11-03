PATH = "tcgpings/retailers/warehouse.py"
src = open(PATH, encoding="utf-8").read()

src = src.replace(
    "import re\nfrom urllib.parse import quote",
    "import re\nfrom importlib import resources\nfrom urllib.parse import quote",
    1,
)

src = src.replace(
    'GONE_AFTER_SCANS = 3  # listings can flicker, so a product must be missing this many scans in a row',
    'GONE_AFTER_SCANS = 3  # listings can flicker, so a product must be missing this many scans in a row\n'
    '# Match the site\'s own store-availability XHR when we re-fire its widget / region URLs.\n'
    'WIDGET_HEADERS = {"accept": "application/json", "x-requested-with": "fetch"}\n'
    '# A clean Chrome auto-solves the managed challenge; wait until the product DOM is present.\n'
    'PAGE_RESOLVED_JS = ("document.querySelectorAll(\'gep-container-store-availability\').length > 0"\n'
    '                    " && !/Just a moment/i.test(document.title)')',
    1,
)

old_bullet = (
    "  - Per-store stock: the store-availability call needs a signed per-product token, and hot\n"
    "    \u00e9okemon products sit behind a Cloudflare challenge. Left out deliberately.\n"
)
new_bullet = (
    "Per-store stock (2026-11-03, validated live in a clean genuine Chrome): hot Pokedex pages sit behind\n"
    "a Cloudflare *managed* challenge that auto-solves in a real browser (no checkbox). Store availability\n"
    "is two calls, each with a short-lived per-endpoint verify token:\n"
    "  1. Load the product page in the browser; its gep-container-store-availability element carries the\n"
    "     widget URL (/products/stores?pid=...&verify=T1).\n"
    "  2. Fire that URL **once** (repeats 403) -> a modal listing all 15 regions, each with its own\n"
    "     per-region token on /products/stores/region?productId=...&region=...&verify=T2.\n"
    "  3. Fire the per-region URLs (~47 KB of store-availability__IN_STOCK / __NOT_AVAILABLE panels each).\n"
    "     Store id is the c-full-store-details-<id> number, matching the bundled Stores-FindStores list\n"
    "     (tcgpings/retailers/data/warehouse_stores.json). store_stock runs this via the browser backend\n"
    "     and is gated on it being available.\n\n"
)
assert old_bullet in src, "per-store bullet not found"
src = src.replace(old_bullet, new_bullet, 1)

open(PATH, "w", encoding="utf-8", newline="").write(src)
print("part 1 done")
