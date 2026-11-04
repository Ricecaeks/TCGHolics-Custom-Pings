"""layout.json: parsing, planning what to link/create/rename, and syncing routes, against fakes."""

import itertools

from tcgpings.discord import layout
from tcgpings.models import ANY_STORE, ONLINE

_ids = itertools.count(5000)


class Channel:
    def __init__(self, name):
        self.id, self.name = next(_ids), name


class Guild:
    def __init__(self, *names):
        self.text_channels = [Channel(n) for n in names]


def retailer(rid, adapter):
    return {"id": rid, "adapter": adapter}


RETAILERS = [retailer("kmart", "kmart"), retailer("jbhifi", "jbhifi"), retailer("card-merchant", "shopify"),
             retailer("game-corner", "shopify"), retailer("retrospace", "retrospace")]

DATA = {"categories": [
    {"name": "STORE ALERTS", "channels": [
        {"name": "kmart-online", "was": ["kmart"], "routes": [{"retailer": "kmart", "store": "online"}]},
        {"name": "kmart-instore", "routes": [{"retailer": "kmart", "store": "instore"}]},
        {"name": "card-shop-sites", "routes": [{"adapter": "shopify"}, {"retailer": "retrospace"}]},
        {"name": "toyworld-online", "routes": [{"retailer": "toyworld", "store": "online"}]},
    ]},
    {"name": "POKÉMON ALERTS", "channels": [
        {"name": "pokemon-online-shops",
         "routes": [{"game": "pokemon", "store": "online", "events": ["restock", "new_product"]}]},
        {"name": "pokemon-store-restocks",
         "routes": [{"game": "pokemon", "store": "instore", "events": ["new_product", "restock", "spotted"]}]},
    ]},
]}


def route_row(rid, channel, spec, layout_channel, url="https://hook/1"):
    return {"id": rid, "channel_id": channel.id, "webhook_url": url, "layout_channel": layout_channel,
            "retailer_id": spec.retailer_id, "store_id": spec.store_id, "franchise": spec.franchise,
            "event_types": list(spec.event_types) if spec.event_types else None, "keywords": spec.keywords,
            "role_id": spec.role_id, "member_pings": False}


def specs():
    return {s.name: s for s in layout.parse(DATA, RETAILERS)[0]}


def test_the_shipped_layout_parses():
    data = layout.load_file()
    every = [retailer(r, a) for r, a in [("kmart", "kmart"), ("farmers", "farmers"), ("jbhifi", "jbhifi"),
                                         ("toyworld", "toyworld"), ("warehouse", "warehouse"),
                                         ("paperplus", "paperplus"), ("whitcoulls", "whitcoulls"),
                                         ("retrospace", "retrospace"), ("card-merchant", "shopify")]]
    parsed, problems = layout.parse(data, every)
    assert problems == []
    names = [s.name for s in parsed]
    assert len(names) == len(set(names))
    assert {"pokemon-online-shops", "pokemon-store-restocks", "kmart-online", "kmart-instore"} <= set(names)
    assert all(s.routes for s in parsed)


def test_parse_expands_adapters_and_skips_retailers_not_enabled():
    s = specs()
    assert [r.retailer_id for r in s["card-shop-sites"].routes] == ["card-merchant", "game-corner", "retrospace"]
    assert s["toyworld-online"].routes == []  # toyworld isn't in the enabled list
    [online] = s["pokemon-online-shops"].routes
    assert (online.retailer_id, online.store_id, online.franchise) == (None, ONLINE, "pokemon")
    assert online.event_types == ("new_product", "restock")
    assert s["pokemon-store-restocks"].routes[0].store_id == ANY_STORE


def test_parse_reports_typos():
    bad = {"categories": [{"name": "X", "channels": [
        {"name": "a", "routes": [{"game": "pokeman"}]},
        {"name": "b", "routes": [{"store": "shelf"}]},
        {"name": "c", "routes": [{"events": ["restocked"]}]},
    ]}]}
    parsed, problems = layout.parse(bad, RETAILERS)
    assert len(problems) == 3 and all(not s.routes for s in parsed)


def test_plan_links_existing_channels_and_reports_what_it_cant_do():
    guild = Guild("kmart", "card-shop-sites", "pokemon-online-shops", "pokemon-store-restocks")
    plan = layout.plan(guild, list(specs().values()), [], can_manage_channels=False)
    by = {c.spec.name: c for c in plan.changes}
    assert by["kmart-online"].action == "old_name" and by["kmart-online"].channel.name == "kmart"
    assert by["kmart-instore"].action == "blocked" and by["kmart-instore"].add == []
    assert by["pokemon-online-shops"].action == "ok" and len(by["pokemon-online-shops"].add) == 1
    assert len(by["card-shop-sites"].add) == 3
    assert any("Manage Channels" in p for p in plan.problems)
    assert plan.pending


def test_plan_creates_and_renames_with_manage_channels():
    guild = Guild("kmart")
    by = {c.spec.name: c for c in layout.plan(guild, list(specs().values()), [], can_manage_channels=True).changes}
    assert by["kmart-online"].action == "rename"
    assert by["kmart-instore"].action == "create" and len(by["kmart-instore"].add) == 1
    assert by["pokemon-online-shops"].action == "create"


def test_plan_is_quiet_once_everything_is_linked():
    guild = Guild("pokemon-online-shops")
    channel = guild.text_channels[0]
    s = specs()["pokemon-online-shops"]
    routes = [route_row(1, channel, s.routes[0], "pokemon-online-shops")]
    plan = layout.plan(guild, [s], routes, can_manage_channels=True)
    assert not plan.pending and plan.changes[0].add == [] and plan.changes[0].remove == []


def test_plan_replaces_changed_routes_and_drops_ones_left_out_of_the_file():
    guild = Guild("pokemon-online-shops")
    channel = guild.text_channels[0]
    s = specs()["pokemon-online-shops"]
    old = layout.RouteSpec(None, ONLINE, "pokemon", None)  # used to get every event type
    routes = [route_row(1, channel, old, "pokemon-online-shops"),
              route_row(2, channel, old, "a-channel-since-removed"),
              {**route_row(3, channel, old, None), "member_pings": False}]  # made by /route set: left alone
    plan = layout.plan(guild, [s], routes, can_manage_channels=True)
    [change] = plan.changes
    assert change.remove == [1] and change.add == s.routes
    assert change.webhook_url is None  # the only existing hook here belongs to a route being removed
    assert plan.orphans == [2]


def test_plan_moves_routes_off_a_deleted_channel():
    old_channel = Channel("pokemon-online-shops")
    guild = Guild("pokemon-online-shops")  # recreated: same name, new id
    s = specs()["pokemon-online-shops"]
    routes = [route_row(1, old_channel, s.routes[0], "pokemon-online-shops")]
    [change] = layout.plan(guild, [s], routes, can_manage_channels=True).changes
    assert change.remove == [1] and change.add == s.routes


async def test_apply_creates_renames_links_and_reuses_one_webhook_per_channel():
    guild = Guild("kmart", "card-shop-sites")
    plan = layout.plan(guild, list(specs().values()), [], can_manage_channels=True)
    calls = {"hooks": [], "created": [], "renamed": [], "routes": [], "removed": []}

    async def webhook_url(ch):
        calls["hooks"].append(ch.name)
        return f"https://hook/{ch.id}"

    async def create_channel(spec):
        calls["created"].append((spec.category, spec.name))
        return Channel(spec.name)

    async def rename(ch, name):
        calls["renamed"].append((ch.name, name))
        ch.name = name

    async def add_route(ch, url, spec, r):
        calls["routes"].append((ch.name, url.startswith("https://hook/"), spec.name, r.retailer_id))

    async def remove_route(rid):
        calls["removed"].append(rid)

    result = await layout.apply(plan, layout.Ops(webhook_url, create_channel, rename, add_route, remove_route))
    assert calls["renamed"] == [("kmart", "kmart-online")]
    assert ("STORE ALERTS", "kmart-instore") in calls["created"]
    assert calls["hooks"].count("card-shop-sites") == 1  # three routes, one webhook
    assert sum(1 for r in calls["routes"] if r[2] == "card-shop-sites") == 3
    assert result.created == 3 and result.renamed == 1 and result.routes_added == 7  # not toyworld: no routes
    assert "toyworld-online" not in {r[2] for r in calls["routes"]}


async def test_apply_reports_a_channel_it_cant_make_a_webhook_in():
    guild = Guild("pokemon-online-shops")
    plan = layout.plan(guild, [specs()["pokemon-online-shops"]], [], can_manage_channels=False)

    async def no_hook(ch):
        raise PermissionError("Missing Permissions")

    async def unused(*a):
        raise AssertionError("not expected")

    result = await layout.apply(plan, layout.Ops(no_hook, unused, unused, unused, unused))
    assert result.routes_added == 0 and "can't make a webhook" in result.problems[0]


def test_a_channel_with_nothing_to_route_is_not_created():
    plan = layout.plan(Guild(), [specs()["toyworld-online"]], [], can_manage_channels=True)
    assert plan.changes[0].action == "skip" and not plan.pending and plan.problems == []
