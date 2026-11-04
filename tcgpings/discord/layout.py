"""The server's alert channels, from layout.json: which channel gets which alerts.

The leader applies it every 10 minutes (and staff can run /layout apply):
- a channel that exists is linked: the bot makes (or reuses) its own webhook there and saves the routes,
- a missing channel is created in its category, or renamed from an old name in `was` (both need the
  bot's Manage Channels permission; without it an old-named channel is used as it is, and a missing one
  is reported),
- routes are kept in step with the file: changed ones are replaced, removed ones deleted.

Only routes the layout made (`routes.layout_channel` set) are touched. Routes made with /route set,
/route pings or /setup stay as they are. An alert posts once per matching route, so one restock can
reach #kmart-instore, #pokemon-store-restocks and #custom-pings together.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from importlib import resources
from typing import Any

from tcgpings.classify import FRANCHISES
from tcgpings.models import ANY_STORE, ONLINE, EventType

STORES = {"online": ONLINE, "instore": ANY_STORE, "in-store": ANY_STORE}
EVENTS = {e.value for e in EventType}


@dataclass(frozen=True)
class RouteSpec:
    retailer_id: str | None = None
    store_id: str | None = None
    franchise: str | None = None
    event_types: tuple[str, ...] | None = None
    keywords: str | None = None
    role_id: int | None = None
    in_stock_only: bool = False  # new listings only when they can be bought (not sold-out or unavailable ones)


@dataclass
class ChannelSpec:
    name: str
    category: str
    topic: str | None = None
    was: tuple[str, ...] = ()
    routes: list[RouteSpec] = field(default_factory=list)


@dataclass
class ChannelChange:
    spec: ChannelSpec
    channel: Any | None  # the channel to use; None when it must be created (or can't be)
    action: str  # "ok" | "create" | "rename" | "old_name" (rename needed, not allowed) | "blocked" | "skip"
    add: list[RouteSpec] = field(default_factory=list)
    remove: list[int] = field(default_factory=list)  # route ids
    webhook_url: str | None = None  # an existing layout route's webhook in this channel, reused for new routes


@dataclass
class LayoutPlan:
    changes: list[ChannelChange]
    orphans: list[int]  # layout routes whose channel left the file
    problems: list[str]

    @property
    def pending(self) -> bool:
        return bool(self.orphans) or any(c.action not in ("ok", "blocked", "old_name", "skip") or c.add or c.remove
                                         for c in self.changes)


@dataclass
class LayoutResult:
    created: int = 0
    renamed: int = 0
    routes_added: int = 0
    routes_removed: int = 0
    problems: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.created or self.renamed or self.routes_added or self.routes_removed)

    def summary(self) -> str:
        text = (f"{self.created} channels created, {self.renamed} renamed, {self.routes_added} routes linked, "
                f"{self.routes_removed} removed.")
        return text + "".join(f"\n⚠️ {p}" for p in self.problems)


def load_file() -> dict:
    return json.loads(resources.files("tcgpings.discord").joinpath("layout.json").read_text(encoding="utf-8"))


def parse(data: Mapping[str, Any], retailers: Sequence[Mapping[str, Any]]) -> tuple[list[ChannelSpec], list[str]]:
    """Layout JSON -> channel specs for the enabled retailers. Unknown names become problems, not errors."""
    by_id = {r["id"]: r for r in retailers}
    specs: list[ChannelSpec] = []
    problems: list[str] = []
    for category in data.get("categories", []):
        for ch in category.get("channels", []):
            spec = ChannelSpec(ch["name"], category["name"], ch.get("topic"), tuple(ch.get("was", ())))
            for raw in ch.get("routes", []):
                spec.routes += _route_specs(raw, spec.name, by_id, retailers, problems)
            specs.append(spec)
    return specs, problems


def _route_specs(raw: Mapping[str, Any], channel: str, by_id: Mapping[str, Any],
                 retailers: Sequence[Mapping[str, Any]], problems: list[str]) -> list[RouteSpec]:
    store = raw.get("store")
    if store is not None and store not in STORES:
        problems.append(f"#{channel}: unknown store `{store}` (use online or instore)")
        return []
    game = raw.get("game")
    if game is not None and game not in FRANCHISES:
        problems.append(f"#{channel}: unknown game `{game}`")
        return []
    events = raw.get("events")
    if events is not None and (bad := [e for e in events if e not in EVENTS]):
        problems.append(f"#{channel}: unknown event type {', '.join(bad)}")
        return []
    if raw.get("adapter"):
        retailer_ids = [r["id"] for r in retailers if r["adapter"] == raw["adapter"]]
    elif raw.get("retailer"):
        if raw["retailer"] not in by_id:
            return []  # not enabled (or not added yet): nothing to route
        retailer_ids = [raw["retailer"]]
    else:
        retailer_ids = [None]
    role = raw.get("role")
    return [RouteSpec(rid, STORES.get(store) if store else None, game, tuple(sorted(events)) if events else None,
                      raw.get("keywords") or None, int(role) if role else None, bool(raw.get("in_stock")))
            for rid in retailer_ids]


def route_spec(route: Mapping[str, Any]) -> RouteSpec:
    events = route["event_types"]
    return RouteSpec(route["retailer_id"], route["store_id"], route["franchise"],
                     tuple(sorted(events)) if events else None, route["keywords"] or None, route["role_id"],
                     bool(route.get("in_stock_only")))


def plan(guild: Any, specs: Sequence[ChannelSpec], routes: Sequence[Mapping[str, Any]],
         can_manage_channels: bool, problems: Sequence[str] = ()) -> LayoutPlan:
    """What applying the layout would do, without changing anything."""
    by_name = {c.name: c for c in guild.text_channels}
    by_id = {c.id: c for c in guild.text_channels}
    layout_routes = [r for r in routes if r["layout_channel"]]
    wanted = {s.name for s in specs}
    changes: list[ChannelChange] = []
    issues = list(problems)
    for spec in specs:
        mine = [r for r in layout_routes if r["layout_channel"] == spec.name]
        # A channel already linked keeps its alerts wherever staff have since renamed or moved it.
        linked = next((by_id[r["channel_id"]] for r in mine if r["channel_id"] in by_id), None)
        channel, action = linked or by_name.get(spec.name), "ok"
        old = None
        if channel is None and not spec.routes:
            action = "skip"  # nothing to send there (its retailer isn't enabled): don't make an empty channel
        elif channel is None:
            old = next((by_name[n] for n in spec.was if n in by_name), None)
            if old is None and can_manage_channels:
                action = "create"
            elif old is None:
                action = "blocked"
                issues.append(f"#{spec.name} doesn't exist and the bot can't create it: it needs Manage Channels")
        elif channel.name in spec.was:
            old = channel  # linked under its old name before the bot could rename it
        if old is not None:
            channel, action = old, "rename" if can_manage_channels else "old_name"
            if not can_manage_channels:
                issues.append(f"#{old.name} should be renamed #{spec.name}: the bot needs Manage Channels")
        if channel is None:
            changes.append(ChannelChange(spec, None, action, list(spec.routes) if action == "create" else [],
                                         [r["id"] for r in mine]))
            continue
        current = [r for r in mine if r["channel_id"] == channel.id]
        have = {route_spec(r) for r in current}
        add = [s for s in dict.fromkeys(spec.routes) if s not in have]
        remove = [r["id"] for r in mine if r["channel_id"] != channel.id or route_spec(r) not in spec.routes]
        hook = next((r["webhook_url"] for r in current if r["id"] not in remove), None)
        changes.append(ChannelChange(spec, channel, action, add, remove, hook))
    orphans = [r["id"] for r in layout_routes if r["layout_channel"] not in wanted]
    return LayoutPlan(changes, orphans, issues)


@dataclass
class Ops:
    """The Discord and database calls `apply` needs, so it can be tested with fakes."""
    webhook_url: Callable[[Any], Awaitable[str]]
    create_channel: Callable[[ChannelSpec], Awaitable[Any]]
    rename: Callable[[Any, str], Awaitable[None]]
    add_route: Callable[[Any, str, ChannelSpec, RouteSpec], Awaitable[None]]
    remove_route: Callable[[int], Awaitable[None]]


async def apply(layout: LayoutPlan, ops: Ops) -> LayoutResult:
    result = LayoutResult(problems=list(layout.problems))
    for route_id in layout.orphans:
        await ops.remove_route(route_id)
        result.routes_removed += 1
    for change in layout.changes:
        for route_id in change.remove:
            await ops.remove_route(route_id)
            result.routes_removed += 1
        channel = change.channel
        try:
            if change.action == "create":
                channel = await ops.create_channel(change.spec)
                result.created += 1
            elif change.action == "rename":
                await ops.rename(channel, change.spec.name)
                result.renamed += 1
        except Exception as exc:  # e.g. a permission overwrite on that category
            result.problems.append(f"#{change.spec.name}: {exc}")
            continue
        if channel is None or not change.add:
            continue
        try:
            url = change.webhook_url or await ops.webhook_url(channel)
        except Exception as exc:  # Missing Permissions in this channel
            result.problems.append(f"#{change.spec.name}: can't make a webhook ({exc})")
            continue
        for spec in change.add:
            await ops.add_route(channel, url, change.spec, spec)
            result.routes_added += 1
    return result


def describe(layout: LayoutPlan) -> str:
    lines = ["**Alert channel layout**"]
    for c in layout.changes:
        state = {"ok": "linked" if not c.add else "to link", "create": "to create", "rename": "to rename",
                 "old_name": "linked under its old name", "blocked": "missing",
                 "skip": "not needed yet"}[c.action]
        routes = len(c.spec.routes)
        extra = f" (+{len(c.add)} routes)" if c.add and c.action == "ok" else ""
        lines.append(f"#{c.spec.name}: {state}{extra}, {routes} route{'s' if routes != 1 else ''}")
    if layout.orphans:
        lines.append(f"{len(layout.orphans)} old layout routes to remove")
    lines += [f"⚠️ {p}" for p in layout.problems]
    return "\n".join(lines)
