"""Toyworld NZ (www.toyworld.co.nz): a Shopify store, so everything comes from the generic adapter.

Its catalogue is mostly toys, so discovery reads only the card collections instead of the
store-wide feed. Toyworld's stores aren't exposed online (Shopify doesn't publish location
stock), so it's online stock only, with add-to-cart links.
"""

from __future__ import annotations

from tcgpings.retailers.base import register
from tcgpings.retailers.shopify import ShopifyAdapter


@register
class ToyworldAdapter(ShopifyAdapter):
    adapter_name = "toyworld"
    default_discover_interval = 5 * 60
    default_requests_per_minute = 12
    default_retailers = [
        ("toyworld", "Toyworld",
         {"domain": "www.toyworld.co.nz", "collections": ["trading-cards", "pokemon"], "catalogue_pages": 1},
         0x00A651)
    ]
