# Importing each adapter module registers it in base.REGISTRY.
from tcgpings.retailers import (  # noqa: F401
    farmers, jbhifi, kmart, mightyape, paperplus, pokemoncenter, retrospace, shopify, toyworld, warehouse,
    whitcoulls,
)
from tcgpings.retailers.base import REGISTRY, RetailerAdapter, build_adapter  # noqa: F401
