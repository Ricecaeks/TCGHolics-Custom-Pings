"""/setup: build every retailer's alert channels, webhooks and routes in one go.

Layout:
    category "Retailers"       #farmers-online    (online: new listings, online stock, price)
                               #farmers-instore   (every store's stock, one alert per product listing the stores)
                               #kmart-online, #kmart-instore, #jbhifi-online, ...
    category "Online Stores"   #card-merchant, #toyworld, ...   (retailers without stores: one channel each)
A category past 50 channels (Discord's cap) continues in "Retailers 2". A channel for a single store
is still possible by hand: `/route set retailer:farmers store:Northwest` in that channel.

Re-running is safe: a route that already points at a channel that still exists is left alone,
wherever an admin has since moved or renamed that channel. A channel with the planned name is reused
instead of creating a duplicate. The leader also runs this on its own (`auto_setup`), so a newly
enabled retailer gets its channels without anyone typing /setup.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from tcgpings.models import ANY_STORE, ONLINE, slugify
from tcgpings.retailers import REGISTRY

MAX_CHANNELS_PER_CATEGORY = 50
MAX_GUILD_CHANNELS = 500  # categories count towards this too
RETAILERS = "Retailers"
ONLINE_STORES = "Online Stores"


@dataclass
class ChannelPlan:
    name: str
    topic: str
    retailer_id: str
    store_id: str | None  # ONLINE for "<prefix>-online", ANY_STORE for "<prefix>-instore", None for a whole retailer


@dataclass
class CategoryPlan:
    name: str
    channels: list[ChannelPlan] = field(default_factory=list)


@dataclass
class SetupResult:
    created: int = 0
    reused: int = 0
    kept: int = 0
    routed: int = 0
    categories: int = 0

    def summary(self) -> str:
        return (f"{self.created} channels created, {self.reused} existing channels reused, "
                f"{self.kept} already set up, {self.routed} routes added, {self.categories} categories created.")


def channel_prefix(retailer: Any) -> str:
    """`jbhifi`, `farmers`, `card-merchant`: the retailer id unless its config sets `channel_prefix`."""
    return slugify((retailer["config"] or {}).get("channel_prefix") or retailer["id"])


def has_stores(retailer: Any) -> bool:
    adapter = REGISTRY.get(retailer["adapter"])
    return bool(adapter and (adapter.supports_store_stock or adapter.stock_in_listings))


def _chunk(name: str, channels: list[ChannelPlan]) -> list[CategoryPlan]:
    size = MAX_CHANNELS_PER_CATEGORY
    if len(channels) <= size:
        return [CategoryPlan(name, channels)]
    return [CategoryPlan(name if i == 0 else f"{name} {i // size + 1}", channels[i : i + size])
            for i in range(0, len(channels), size)]


def plan_layout(retailers: list[Any]) -> list[CategoryPlan]:
    """Categories and channels for these retailers."""
    paired: list[ChannelPlan] = []
    shops: list[ChannelPlan] = []
    for r in retailers:
        prefix = channel_prefix(r)
        if not has_stores(r):
            shops.append(ChannelPlan(prefix[:100], f"{r['name']} TCG alerts", r["id"], None))
            continue
        paired.append(ChannelPlan(f"{prefix}-online"[:100],
                                  f"{r['name']} online: new listings, stock and price changes", r["id"], ONLINE))
        paired.append(ChannelPlan(f"{prefix}-instore"[:100], f"{r['name']} in-store stock, every store",
                                  r["id"], ANY_STORE))
    plans: list[CategoryPlan] = []
    if paired:
        plans += _chunk(RETAILERS, paired)
    if shops:
        plans += _chunk(ONLINE_STORES, shops)
    return plans


def _route_key(retailer_id: str | None, store_id: str | None) -> tuple:
    return (retailer_id, store_id)


def pending_work(guild: Any, plans: list[CategoryPlan], routes: list[Any]) -> tuple[int, int, int]:
    """(channels to create, categories to create, channels already set up) if `apply_layout` ran now."""
    live = {c.id for c in guild.channels}
    routed = {_route_key(r["retailer_id"], r["store_id"]) for r in routes if r["channel_id"] in live}
    names = {c.name for c in guild.text_channels}
    cats = {c.name for c in guild.categories}
    new_channels = new_categories = done = 0
    for plan in plans:
        needed = 0
        for ch in plan.channels:
            if _route_key(ch.retailer_id, ch.store_id) in routed:
                done += 1
            elif ch.name not in names:
                needed += 1
        new_channels += needed
        new_categories += bool(needed) and plan.name not in cats
    return new_channels, new_categories, done


async def _category_with_room(guild: Any, name: str, full: set[str], result: SetupResult) -> tuple[Any, int]:
    """The category called `name`, or `name (2)`, `name (3)`... when admins have since filled it up."""
    for candidate in [name] + [f"{name} ({i})" for i in range(2, 10)]:
        if candidate in full:
            continue
        category = next((c for c in guild.categories if c.name == candidate), None)
        if category is None:
            result.categories += 1
            return await guild.create_category(candidate, reason="TCGHolics Pings /setup"), MAX_CHANNELS_PER_CATEGORY
        room = MAX_CHANNELS_PER_CATEGORY - len(category.channels)
        if room > 0:
            return category, room
    raise RuntimeError(f"every '{name}' category is full")


async def apply_layout(
    guild: Any,
    plans: list[CategoryPlan],
    routes: list[Any],
    webhook_for: Callable[[Any], Awaitable[Any]],
    add_route: Callable[[ChannelPlan, Any, str], Awaitable[Any]],
    progress: Callable[[str], Awaitable[None]] | None = None,
) -> SetupResult:
    """Create what's missing. `webhook_for(channel)` returns a webhook; `add_route(plan, channel, url)` stores it."""
    result = SetupResult()
    live = {c.id for c in guild.channels}
    routed = {_route_key(r["retailer_id"], r["store_id"]) for r in routes if r["channel_id"] in live}
    for plan in plans:
        category, room, full = None, 0, set()
        for ch in plan.channels:
            if _route_key(ch.retailer_id, ch.store_id) in routed:
                result.kept += 1
                continue
            channel = next((c for c in guild.text_channels if c.name == ch.name), None)
            if channel is None:
                if room <= 0:
                    if category is not None:
                        full.add(category.name)
                    category, room = await _category_with_room(guild, plan.name, full, result)
                channel = await category.create_text_channel(ch.name, topic=ch.topic, reason="TCGHolics Pings /setup")
                room -= 1
                result.created += 1
            else:
                result.reused += 1
            hook = await webhook_for(channel)
            await add_route(ch, channel, hook.url)
            routed.add(_route_key(ch.retailer_id, ch.store_id))
            result.routed += 1
            if progress and result.routed % 10 == 0:
                await progress(f"Working… {result.routed} channels routed so far (at `#{ch.name}`).")
    return result


def describe_plan(plans: list[CategoryPlan], guild: Any, routes: list[Any]) -> str:
    new_channels, new_categories, done = pending_work(guild, plans, routes)
    total = len(guild.channels) + new_channels + new_categories
    lines = ["**Planned layout**"]
    for p in plans:
        sample = ", ".join(f"#{c.name}" for c in p.channels[:3])
        more = f", … (+{len(p.channels) - 3})" if len(p.channels) > 3 else ""
        lines.append(f"📁 **{p.name}** · {len(p.channels)} channels: {sample}{more}")
    lines.append(
        f"\n{new_channels} channels and {new_categories} categories to create, {done} already set up. "
        f"The server would have **{total} / {MAX_GUILD_CHANNELS}** channels."
    )
    return "\n".join(lines)


def over_limit(guild: Any, plans: list[CategoryPlan], routes: list[Any]) -> int:
    """How many channels past Discord's server cap this would go (0 = fits)."""
    new_channels, new_categories, _ = pending_work(guild, plans, routes)
    return max(0, len(guild.channels) + new_channels + new_categories - MAX_GUILD_CHANNELS)
