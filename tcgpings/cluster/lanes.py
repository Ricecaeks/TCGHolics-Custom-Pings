"""Worker lanes: which kind of node runs a retailer's jobs.

Jobs that drive Chrome or the paid fetch chain take seconds each and need a browser and shared memory;
everything else is plain HTTP that finishes in well under a second. Giving them separate worker pools
(WORKER_LANES per node) stops the slow ones from holding every slot while fast stores wait behind them.

A retailer's lane comes from its adapter, unless its config sets "lane" (one of LANES) to override it.
claim_jobs works the lane out in SQL from the same lists, so keep the two in step (tests check this).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

HTTP = "http"
BROWSER = "browser"
LANES = (HTTP, BROWSER)
LANE_KEY = "lane"  # retailer config key that overrides the adapter's lane
LANE_DEFAULT = "default"  # /retailer set lane: value that removes the override

# Adapters that start Chrome (http.browser) or go through the fetch chain (http.chain.fetch_text, which
# tries our Chrome first, then the paid unblockers). The Warehouse adapter starts a Chrome session too.
BROWSER_ADAPTERS = frozenset({"farmers", "kmart", "mightyape", "pokemoncenter", "warehouse"})


def adapter_lane(adapter: str) -> str:
    return BROWSER if adapter in BROWSER_ADAPTERS else HTTP


def retailer_lane(retailer: Mapping[str, Any]) -> str:
    """A retailer row's lane: its config's "lane" when that names a known lane, else its adapter's."""
    lane = (retailer.get("config") or {}).get(LANE_KEY)
    return lane if lane in LANES else adapter_lane(retailer["adapter"])


def parse_lanes(value: str | Iterable[str] | None) -> list[str]:
    """WORKER_LANES as a list: "http,browser" -> ["http", "browser"]; "" or "none" -> [] (claims nothing)."""
    if value is None:
        return []
    items = value.split(",") if isinstance(value, str) else list(value)
    lanes = [i.strip().lower() for i in items if i.strip()]
    return [] if lanes == ["none"] else list(dict.fromkeys(lanes))
