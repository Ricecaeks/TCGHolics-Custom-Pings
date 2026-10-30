"""/setup layout planning and the create/reuse/skip logic, against fake Discord objects."""

import itertools

from tcgpings.discord import setup
from tcgpings.models import ANY_STORE, ONLINE

_ids = itertools.count(1000)


class FakeChannel:
    def __init__(self, name, category=None):
        self.id, self.name, self.category = next(_ids), name, category


class FakeCategory(FakeChannel):
    def __init__(self, guild, name):
        super().__init__(name)
        self.guild, self.channels = guild, []

    async def create_text_channel(self, name, topic=None, reason=None):
        ch = FakeChannel(name, self)
        self.channels.append(ch)
        self.guild.all.append(ch)
        return ch


class FakeGuild:
    def __init__(self):
        self.all = []

    @property
    def channels(self):
        return self.all

    @property
    def categories(self):
        return [c for c in self.all if isinstance(c, FakeCategory)]

    @property
    def text_channels(self):
        return [c for c in self.all if not isinstance(c, FakeCategory)]

    async def create_category(self, name, reason=None):
        cat = FakeCategory(self, name)
        self.all.append(cat)
        return cat


class Hook:
    url = "https://discord.com/api/webhooks/1/x"


def retailer(rid, name, adapter="shopify", config=None):
    return {"id": rid, "name": name, "adapter": adapter, "config": config or {}}


FARMERS = retailer("farmers", "Farmers", "farmers")
JB = retailer("jbhifi", "JB Hi-Fi", "jbhifi")
SHOP = retailer("card-merchant", "Card Merchant")


KMART = retailer("kmart", "Kmart", "kmart")


def test_plan_pairs_online_and_instore_channels():
    plans = setup.plan_layout([FARMERS, JB, KMART, SHOP])
    assert [p.name for p in plans] == ["Retailers", "Online Stores"]
    assert [(c.name, c.store_id) for c in plans[0].channels] == [
        ("farmers-online", ONLINE), ("farmers-instore", ANY_STORE),
        ("jbhifi-online", ONLINE), ("jbhifi-instore", ANY_STORE),
        ("kmart-online", ONLINE), ("kmart-instore", ANY_STORE),
    ]
    assert [(c.name, c.store_id) for c in plans[1].channels] == [("card-merchant", None)]


def test_plan_splits_categories_at_50_channels():
    shops = [retailer(f"shop-{i:02d}", f"Shop {i:02d}") for i in range(53)]
    plans = setup.plan_layout(shops)
    assert [(p.name, len(p.channels)) for p in plans] == [("Online Stores", 50), ("Online Stores 2", 3)]


def test_channel_prefix_override():
    r = retailer("iron-knight", "Iron Knight Gaming", config={"channel_prefix": "IKG"})
    assert setup.channel_prefix(r) == "ikg"


async def test_apply_creates_once_then_is_idempotent():
    guild, routes = FakeGuild(), []
    plans = setup.plan_layout([FARMERS, JB, SHOP])

    async def add_route(plan, channel, url):
        routes.append({"retailer_id": plan.retailer_id, "store_id": plan.store_id, "channel_id": channel.id})

    async def webhook_for(channel):
        return Hook()

    assert setup.pending_work(guild, plans, routes) == (5, 2, 0)
    first = await setup.apply_layout(guild, plans, routes, webhook_for, add_route)
    assert (first.created, first.routed, first.categories) == (5, 5, 2)
    assert {c.name for c in guild.categories} == {"Retailers", "Online Stores"}

    # An admin moves #farmers-instore elsewhere and renames it: setup leaves it alone.
    instore = next(c for c in guild.text_channels if c.name == "farmers-instore")
    instore.name, instore.category = "farmers-stores", None
    again = await setup.apply_layout(guild, plans, routes, webhook_for, add_route)
    assert (again.created, again.routed, again.kept) == (0, 0, 5)

    # A deleted channel is recreated; an unrouted channel with the planned name is reused.
    guild.all.remove(next(c for c in guild.text_channels if c.name == "jbhifi-instore"))
    routes[:] = [r for r in routes if not (r["retailer_id"] == "farmers" and r["store_id"] == ONLINE)]
    fixed = await setup.apply_layout(guild, plans, routes, webhook_for, add_route)
    assert (fixed.created, fixed.reused, fixed.kept) == (1, 1, 3)


async def test_full_category_overflows_to_numbered_one():
    guild = FakeGuild()
    cat = await guild.create_category("Retailers")
    for i in range(50):
        await cat.create_text_channel(f"other-{i}")
    plans = setup.plan_layout([FARMERS])

    async def noop(*a):
        return Hook()

    result = await setup.apply_layout(guild, plans, [], noop, noop)
    assert result.created == 2 and {c.name for c in guild.categories} == {"Retailers", "Retailers (2)"}


def test_server_limit():
    guild = FakeGuild()
    guild.all = [FakeChannel(f"c{i}") for i in range(498)]
    plans = setup.plan_layout([FARMERS])
    assert setup.over_limit(guild, plans, []) == 1  # 2 channels + 1 category on top of 498
    assert "501 / 500" in setup.describe_plan(plans, guild, [])
