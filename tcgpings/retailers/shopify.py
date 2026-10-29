"""Generic Shopify storefront adapter. One `retailers` row per shop, config {"domain": "..."}.

Uses Shopify's public storefront JSON (no API key):
  /search/suggest.json?q=...         server-side search over the whole catalogue (top 10 matches)
  /products.json?limit=250&page=N    catalogue, most recently updated first: catches new listings
  /products/<handle>.js              single product, used for watched SKUs
Big singles shops have 10k+ products, so search reads only the first `catalogue_pages` pages
(default 2). Set it higher for small shops to scan everything.
Shopify doesn't expose inventory counts publicly, so stock is IN/OUT only. SKU = product handle.
"""

from __future__ import annotations

import asyncio
from urllib.parse import urlparse

from tcgpings.classify import franchise_of, matches_query
from tcgpings.models import Level, Product, Stock, to_cents
from tcgpings.net.http import FetchError
from tcgpings.retailers.base import RetailerAdapter, register


@register
class ShopifyAdapter(RetailerAdapter):
    adapter_name = "shopify"

    def __init__(self, retailer, http) -> None:
        super().__init__(retailer, http)
        domain = self.config.get("domain")
        if not domain:
            raise ValueError(f"shopify retailer {self.retailer_id} has no config.domain")
        self.domain = domain.removeprefix("https://").removeprefix("http://").strip("/")
        self.base = f"https://{self.domain}"
        self.catalogue_pages = int(self.config.get("catalogue_pages", 2))

    async def search(self, query: str) -> list[Product]:
        found: dict[str, Product] = {}
        try:
            data = await self.http.get_json(
                self.policy,
                f"{self.base}/search/suggest.json",
                params={"q": query, "resources[type]": "product", "resources[limit]": "10"},
            )
        except FetchError:
            data = {}  # some older themes disable predictive search; the catalogue scan still runs
        for raw in ((data.get("resources") or {}).get("results") or {}).get("products") or []:
            if matches_query(" ".join([raw.get("title", ""), raw.get("type", ""), *_tags(raw)]), query):
                found[raw["handle"]] = self.parse_suggest_product(raw)

        for page in range(1, self.catalogue_pages + 1):
            data = await self.http.get_json(
                self.policy, f"{self.base}/products.json", params={"limit": "250", "page": str(page)}
            )
            products = data.get("products") or []
            for raw in products:
                text = " ".join([raw.get("title", ""), raw.get("product_type", ""), *_tags(raw)])
                if matches_query(text, query):
                    found[raw["handle"]] = self.parse_catalogue_product(raw)
            if len(products) < 250:
                break
        return list(found.values())

    async def fetch_products(self, skus: list[str]) -> list[Product]:
        results = await asyncio.gather(*(self._fetch_one(sku) for sku in skus), return_exceptions=True)
        products = []
        for sku, result in zip(skus, results):
            if isinstance(result, FetchError) and "HTTP 404" in str(result):
                continue  # delisted; leave the last known state alone
            if isinstance(result, BaseException):
                raise result
            products.append(result)
        return products

    async def _fetch_one(self, handle: str) -> Product:
        data = await self.http.get_json(self.policy, f"{self.base}/products/{handle}.js")
        return self.parse_product_js(data)

    def parse_ref(self, ref: str) -> str:
        ref = ref.strip()
        if "/products/" in ref:
            return urlparse(ref).path.split("/products/", 1)[1].split("/")[0]
        return ref

    def matches_url(self, url: str) -> bool:
        return urlparse(url).netloc.removeprefix("www.") == self.domain.removeprefix("www.")

    def parse_catalogue_product(self, raw: dict) -> Product:
        variants = raw.get("variants") or []
        images = raw.get("images") or []
        available = any(v.get("available") for v in variants)
        prices = [p for p in (to_cents(v.get("price")) for v in variants) if p is not None]
        return Product(
            retailer_id=self.retailer_id,
            sku=raw["handle"],
            title=raw["title"],
            url=f"{self.base}/products/{raw['handle']}",
            image=images[0]["src"] if images else None,
            price_cents=min(prices) if prices else None,
            online=Stock(Level.IN if available else Level.OUT),
            # Singles are often titled just "Charizard ex (199/165)"; the game is in the type/tags.
            franchise=franchise_of(raw["title"]) or franchise_of(" ".join([raw.get("product_type", ""), *_tags(raw)])),
        )

    def parse_suggest_product(self, raw: dict) -> Product:
        image = raw.get("image") or (raw.get("featured_image") or {}).get("url")
        return Product(
            retailer_id=self.retailer_id,
            sku=raw["handle"],
            title=raw["title"],
            url=f"{self.base}/products/{raw['handle']}",
            image=image,
            price_cents=to_cents(raw.get("price_min") or raw.get("price")),
            online=Stock(Level.IN if raw.get("available") else Level.OUT),
            franchise=franchise_of(raw["title"]) or franchise_of(" ".join([raw.get("type", ""), *_tags(raw)])),
        )

    def parse_product_js(self, raw: dict) -> Product:
        # .js prices are already integer cents
        image = raw.get("featured_image")
        if image and image.startswith("//"):
            image = "https:" + image
        return Product(
            retailer_id=self.retailer_id,
            sku=raw["handle"],
            title=raw["title"],
            url=f"{self.base}/products/{raw['handle']}",
            image=image,
            price_cents=raw.get("price_min", raw.get("price")),
            online=Stock(Level.IN if raw.get("available") else Level.OUT),
        )


def _tags(raw: dict) -> list[str]:
    tags = raw.get("tags") or []
    return tags.split(",") if isinstance(tags, str) else tags
