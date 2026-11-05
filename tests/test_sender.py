"""The outbox sender: a bad row can't wedge the queue, and a partly sent alert never pings twice."""

from types import SimpleNamespace

import aiohttp
import discord
import pytest

from tcgpings.context import Stats
from tcgpings.db import queries
from tcgpings.discord import sender
from tcgpings.discord.sender import send_batch
from tcgpings.models import Event, EventType


class FakeWebhook:
    """Records posts; `fail_on` is the 1-based post numbers that raise, each only once."""

    def __init__(self, fail_on=()):
        self.sent: list[dict] = []
        self.calls = 0
        self.fail_on = set(fail_on)

    async def send(self, **kw):
        self.calls += 1
        if self.calls in self.fail_on:
            raise aiohttp.ClientConnectionError("connection reset")
        self.sent.append(kw)


@pytest.fixture
def webhook(monkeypatch):
    hook = FakeWebhook()
    monkeypatch.setattr(sender.discord.Webhook, "from_url", lambda *a, **k: hook)
    return hook


def make_ctx(pool):
    return SimpleNamespace(pool=pool, node_name="nuc1", settings=SimpleNamespace(dry_run=False), stats=Stats())


def event(sku, users=()):
    extra = {"pings": [{"keywords": "30th", "users": list(users)}]} if users else {}
    return Event(type=EventType.RESTOCK, retailer_id="kmart", sku=sku, title=f"Pokemon 30th {sku}",
                 url="https://x", new_level="in", old_level="out", extra=extra)


async def enqueue(pool, route_id, ev):
    await queries.enqueue_alert(pool, ev.sku, route_id, ev.to_payload())
    return await pool.fetchval("SELECT id FROM alert_outbox WHERE dedupe_key = $1", ev.sku)


async def make_due(pool):
    await pool.execute("UPDATE alert_outbox SET next_attempt_at = now()")


async def test_a_row_that_cant_be_built_counts_its_attempt_and_the_rest_still_send(pool, webhook, monkeypatch):
    real_build = sender.build_embed

    def build(ev):
        if ev.sku == "bad":
            raise KeyError("store_name")
        return real_build(ev)

    monkeypatch.setattr(sender, "build_embed", build)
    ctx = make_ctx(pool)
    route = await queries.add_route(pool, 1, "https://discord.test/x")
    bad = await enqueue(pool, route, event("bad"))
    good = await enqueue(pool, route, event("good"))

    async with aiohttp.ClientSession() as session:
        assert await send_batch(ctx, session) == 2
        assert ctx.stats.alerts_sent == 1 and len(webhook.sent) == 1
        assert await pool.fetchval("SELECT sent_at IS NOT NULL FROM alert_outbox WHERE id = $1", good)
        row = await pool.fetchrow("SELECT * FROM alert_outbox WHERE id = $1", bad)
        assert row["sent_at"] is None and row["attempts"] == 1 and "KeyError" in row["last_error"]
        assert row["lease_owner"] is None

        # Retried with backoff, it dead-letters after 8 attempts instead of looping forever.
        for _ in range(10):
            await make_due(pool)
            await send_batch(ctx, session)
    assert await pool.fetchval("SELECT attempts FROM alert_outbox WHERE id = $1", bad) == 8
    assert (await queries.outbox_backlog(pool))["dead"] == 1


async def test_a_failed_overflow_message_is_retried_without_resending_the_first(pool, webhook):
    users = list(range(10**17, 10**17 + 150))  # too many tags for one message: embed + 1 overflow
    webhook.fail_on = {2}
    ctx = make_ctx(pool)
    route = await queries.add_route(pool, 1, "https://discord.test/x")
    alert = await enqueue(pool, route, event("big", users))

    async with aiohttp.ClientSession() as session:
        await send_batch(ctx, session)
        row = await pool.fetchrow("SELECT * FROM alert_outbox WHERE id = $1", alert)
        assert row["sent_at"] is None and row["attempts"] == 1 and row["sent_parts"] == 1
        assert len(webhook.sent) == 1 and isinstance(webhook.sent[0]["embed"], discord.Embed)

        await make_due(pool)
        await send_batch(ctx, session)
    assert await pool.fetchval("SELECT sent_at IS NOT NULL FROM alert_outbox WHERE id = $1", alert)
    assert len(webhook.sent) == 2 and "embed" not in webhook.sent[1]
    tagged = [u.id for message in webhook.sent for u in message["allowed_mentions"].users]
    assert tagged == users, "every member tagged exactly once"
    assert ctx.stats.alerts_sent == 1
