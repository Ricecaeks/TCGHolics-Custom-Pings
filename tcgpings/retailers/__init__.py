# Importing each adapter module registers it in base.REGISTRY.
from tcgpings.retailers import farmers, shopify  # noqa: F401
from tcgpings.retailers.base import REGISTRY, RetailerAdapter, build_adapter  # noqa: F401
