PARSERS = r'''
def load_stores() -> list[dict]:
    data = resources.files("tcgpings.retailers.data").joinpath("warehouse_stores.json").read_text(encoding="utf-8")
    return json.loads(data)["stores"]


_WIDGET_ELEM = re.compile(r'<gep-container-store-availability[^>]*?pid="([^"]+)"[^>]*?url="([^"]+)"', re.S)
_REGION_OPTION = re.compile(r'value="([A-Z]+-[A-Z]+)"\s+data-href="([^"]+)"')
_STORE_PANEL = re.compile(r'<div class="store panel">(.*?)(?=<div class="store panel"|$)', re.S)
_STORE_DETAIL_ID = re.compile(r'id="c-full-store-details-(\d+)"')
_STORE_STATUS = re.compile(r'store-availability__([A-Z_]+)')


def widget_store_url(page: str, sku: str) -> str | None:
    """The store-availability widget URL (with its verify token) for a product's own element."""
    urls = [html.unescape(url) for pid, url in _WIDGET_ELEM.findall(page) if pid == sku]
    return next((u for u in urls if "edit=" not in u), urls[0] if urls else None)


def parse_store_regions(widget: str) -> dict[str, str]:
    """Step-1 widget response -> {region_code: region_url}; 15 regions, each with its own verify token."""
    try:
        data = json.loads(widget)
    except ValueError:
        return {}
    tpl = data.get("modalTemplate") or ""
    return {code: html.unescape(href) for code, href in _REGION_OPTION.findall(tpl)}


def parse_store_levels(region: str) -> dict[str, Stock]:
    """Step-2 region response -> {store_id: Stock}; store_id is the c-full-store-details number."""
    try:
        data = json.loads(region)
    except ValueError:
        return {}
    out: dict[str, Stock] = {}
    for block in _STORE_PANEL.findall(data.get("stores") or ""):
        detail = _STORE_DETAIL_ID.search(block)
        status = _STORE_STATUS.search(block)
        if detail and status:
            out[detail.group(1)] = Stock(STOCK_STATUS.get(status.group(1), Level.OUT))
    return out
'''

STORE_METHOD = r'''    @property
    def store_stock_enabled(self) -> bool:
        return getattr(self.http, "browser", None) is not None

    async def store_stock(self, sku: str, store_ids: list[str]) -> dict[str, Stock]:
        """Per-store stock: load the product page in the browser (managed challenge auto-solves),
        fire its store-availability widget once, then the per-region URLs it returns."""
        browser = getattr(self.http, "browser", None)
        if browser is None:
            raise FetchError("warehouse per-store stock needs the browser backend")
        wanted = {s for s in store_ids if s != IN_STORES}
        regions = sorted({self._region_of[s] for s in wanted if s in self._region_of}) or sorted(
            {s["region_code"] for s in self._stores})
        if not regions:
            return {}
        page_url = f"{BASE}/p/x/{quote(sku)}.html"
        page = await browser.visit(self.policy, page_url, success_js=PAGE_RESOLVED_JS)
        widget_url = widget_store_url(page, sku)
        if not widget_url:
            raise FetchError(f"GET {page_url}: no store-availability widget for {sku}")
        widget_text = await browser.fetch_text(self.policy, BASE, widget_url, WIDGET_HEADERS)
        region_urls = parse_store_regions(widget_text)
        stock: dict[str, Stock] = {}
        for code in regions:
            url = region_urls.get(code)
            if not url:
                continue
            try:
                text = await browser.fetch_text(self.policy, BASE, url, WIDGET_HEADERS)
            except FetchError as exc:
                log.info("warehouse: region %s for %s failed: %s", code, sku, exc)
                continue
            stock.update(parse_store_levels(text))
        return {sid: stock[sid] for sid in wanted if sid in stock} if wanted else stock

'''
