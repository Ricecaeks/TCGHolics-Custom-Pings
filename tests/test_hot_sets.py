"""Hot sets: reading feeds, suggesting keywords, staff decisions, and faster checks."""

from types import SimpleNamespace

import pytest

from tcgpings.cluster.leadership import apply_hot_intervals
from tcgpings.db import queries
from tcgpings.discord import hot
from tcgpings.models import Product
from tcgpings.news import parse_feed, suggest_keyword

FEED = """<rss><channel>
<item><title>&#8220;Aura Seeker&#8221; Set Starring Mega Lucario Z ex Officially Revealed!</title><link>https://x/aura</link></item>
<item><title><![CDATA[Pok\u00e9mon TCG Drops New Mega Evolution\u2014Delta Reign Expansion Info - Bleeding Cool News]]></title><link>https://x/delta</link></item>
<item><title>Pok\u00e9mon TCG Pocket: Dual Fusion Expansion Coming Soon - Pokemon.com</title><link>https://x/pocket</link></item>
<item><title>Dad Sells Forgotten Pok\u00e9mon Card Collection From The Attic</title><link>https://x/attic</link></item>
<item><title>mew ex box</title><link>https://x/forum</link></item>
<item><title>Dhelmise/Dusknoir</title><link>https://x/deck</link></item>
</channel></rss>"""


def test_feed_keeps_releases_and_drops_everything_else():
    titles = [h.title for h in parse_feed(FEED, "test")]
    assert titles == ["“Aura Seeker” Set Starring Mega Lucario Z ex Officially Revealed!",
                      "Pokémon TCG Drops New Mega Evolution—Delta Reign Expansion Info"]


@pytest.mark.parametrize("title, keyword", [
    ("“Aura Seeker” Set Starring Mega Lucario Z ex Officially Revealed!", "aura seeker"),
    ("Pokémon TCG Drops New Mega Evolution—Delta Reign Expansion Info", "delta reign"),
    ("Pokémon TCG: Mega Rayquaza ex Premium Tournament Collection", "mega rayquaza ex premium tournament collection"),
])
def test_keyword_suggestions(title, keyword):
    assert suggest_keyword(title) == keyword


class FakeHttp:
    async def get(self, policy, url, **kw):
        return SimpleNamespace(text=FEED)


class FakeChannel:
    def __init__(self):
        self.sent = []

    async def send(self, **kw):
        self.sent.append(kw)
        return SimpleNamespace(id=1000 + len(self.sent))


async def test_each_release_gets_one_card_however_many_feeds_report_it(pool, monkeypatch):
    monkeypatch.setattr(hot, "FEEDS", {"feed a": "https://a", "feed b": "https://b"})
    ctx = SimpleNamespace(pool=pool, http=FakeHttp())
    assert await hot.find_candidates(ctx) == 2
    assert await hot.find_candidates(ctx) == 0
    channel = FakeChannel()
    assert await hot.post_cards(ctx, channel) == 2
    assert await hot.post_cards(ctx, channel) == 0
    assert [c["custom_id"] for c in channel.sent[0]["view"].to_components()[0]["components"]][0].startswith("hot:approve:")


async def test_a_keyword_already_searched_is_not_suggested(pool, monkeypatch):
    monkeypatch.setattr(hot, "FEEDS", {"feed": "https://a"})
    await queries.add_watch(pool, "keyword", "Delta Reign", None, None, None, None)
    ctx = SimpleNamespace(pool=pool, http=FakeHttp())
    assert await hot.find_candidates(ctx) == 1
    assert [r["keyword"] for r in await queries.unposted_candidates(pool, 10)] == ["aura seeker"]


async def test_marking_hot_reuses_a_watch_and_expires(pool):
    await queries.add_watch(pool, "keyword", "delta reign", None, None, None, None)
    await queries.mark_hot(pool, "Delta Reign", 14)
    await queries.mark_hot(pool, "aura seeker", 14, 42)
    assert sorted(r["query"] for r in await queries.list_hot_watches(pool)) == ["aura seeker", "delta reign"]
    assert await pool.fetchval("SELECT count(*) FROM watches") == 2
    assert await queries.unmark_hot(pool, "aura seeker")
    assert not await queries.unmark_hot(pool, "aura seeker")
    await pool.execute("UPDATE watches SET hot_until = now() - interval '1 day'")
    assert await queries.list_hot_watches(pool) == []


async def test_hot_products_get_faster_checks_and_return_to_normal(pool):
    from tcgpings.retailers.toyworld import ToyworldAdapter as T

    await queries.upsert_retailer(pool, "toyworld", "toyworld", "Toyworld", {"domain": "x"})
    for sku, title in (("hot", "Pokemon Delta Reign Booster Bundle"), ("cold", "Lorcana Azurite Sea Booster")):
        await queries.upsert_product(pool, Product("toyworld", sku, title, f"https://x/{sku}"))
        await queries.add_discovery_job(pool, f"sku:toyworld:{sku}", "toyworld", sku, T.default_sku_interval)
    await queries.mark_hot(pool, "delta reign", 14)
    ctx = SimpleNamespace(pool=pool)

    async def intervals():
        return {r["payload"]["sku"]: r["interval_seconds"] for r in await pool.fetch("SELECT * FROM jobs WHERE kind = 'watch_sku'")}

    await apply_hot_intervals(ctx)
    assert await intervals() == {"hot": T.hot_sku_interval, "cold": T.default_sku_interval}
    await queries.unmark_hot(pool, "delta reign")
    await apply_hot_intervals(ctx)
    assert await intervals() == {"hot": T.default_sku_interval, "cold": T.default_sku_interval}
