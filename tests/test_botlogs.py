"""#bot-logs: lines are buffered, capped, redacted and packed into a few Discord messages."""

import logging
from types import SimpleNamespace

import pytest

from tcgpings.config import Settings
from tcgpings.db import queries
from tcgpings.discord import botlogs
from tcgpings.discord.botlogs import DiscordLogHandler, find_category, messages, redact


def _handler(**kw) -> DiscordLogHandler:
    h = DiscordLogHandler(logging.WARNING, **kw)
    h.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    return h


def _log(h, name, level, msg):
    if level >= h.level:  # as Logger.callHandlers does
        h.handle(logging.LogRecord(name, level, __file__, 1, msg, None, None))


def test_keeps_warnings_skips_info_and_its_own_lines():
    h = _handler()
    _log(h, "tcgpings.worker", logging.INFO, "routine")
    _log(h, "tcgpings.worker", logging.WARNING, "job failed")
    _log(h, "tcgpings.discord.botlogs", logging.WARNING, "could not post")  # would loop
    _log(h, "discord.webhook.async_", logging.WARNING, "rate limited")
    assert h.take() == (["WARNING tcgpings.worker: job failed"], 0)
    assert h.take() == ([], 0)


def test_buffer_is_capped_and_counts_the_rest():
    h = _handler(max_lines=2)
    for i in range(5):
        _log(h, "x", logging.ERROR, f"e{i}")
    lines, dropped = h.take()
    assert len(lines) == 2 and dropped == 3


def test_secrets_are_redacted():
    h = _handler(secrets=["sk-live-abcdefgh"])
    _log(h, "x", logging.ERROR, "GET https://api.scrapfly.io/scrape?key=scp-123&url=x failed; token sk-live-abcdefgh")
    _log(h, "x", logging.ERROR, "post https://discord.com/api/webhooks/123/AbC-def_9 failed")
    lines, _ = h.take()
    assert "scp-123" not in lines[0] and "key=***&url=x" in lines[0] and "sk-live" not in lines[0]
    assert lines[1].endswith("/api/webhooks/123/*** failed")


def test_secret_values_come_from_settings():
    s = Settings(_env_file=None, zyte_api_key="zyte-secret-1", proxy_urls="http://u:p@proxy1:8000, short")
    assert {"zyte-secret-1", "http://u:p@proxy1:8000"} <= set(botlogs.secret_values(s))
    assert redact("via http://u:p@proxy1:8000 and zyte-secret-1", botlogs.secret_values(s)) == "via *** and ***"


def test_messages_collapse_repeats_and_fit_discord():
    lines = ["WARNING a: same"] * 4 + [f"ERROR b: line {i} " + "x" * 200 for i in range(40)]
    out = messages(lines, dropped=5)
    assert len(out) == 3
    assert all(len(m) <= 2000 for m in out)
    assert out[0].startswith("```\nWARNING a: same  (×4)\n")
    assert out[-1].endswith("not posted; see the log file.")
    assert "```" not in out[0][3:-4]  # one code block per message


def test_messages_with_only_dropped_lines():
    assert messages([], dropped=7) == ["… 7 more line(s) not posted; see the log file."]


def test_find_category_prefers_exact_then_contains():
    guild = SimpleNamespace(categories=[SimpleNamespace(name="🛡️ Staff Area"), SimpleNamespace(name="STAFF")])
    assert find_category(guild, "Staff").name == "STAFF"
    guild.categories = guild.categories[:1]
    assert find_category(guild, "staff").name == "🛡️ Staff Area"
    guild.categories = []
    assert find_category(guild, "Staff") is None


@pytest.mark.asyncio
async def test_webhook_setting_round_trip(pool):
    assert await queries.get_setting(pool, botlogs.SETTING_KEY) is None
    await queries.set_setting(pool, botlogs.SETTING_KEY, "https://a")
    await queries.set_setting(pool, botlogs.SETTING_KEY, "https://b")
    assert await queries.get_setting(pool, botlogs.SETTING_KEY) == "https://b"


async def test_post_loop_waits_for_the_webhook_then_posts(pool, monkeypatch):
    import asyncio

    sent = []

    class FakeWebhook:
        async def send(self, **kw):
            sent.append(kw)

    monkeypatch.setattr(botlogs, "FLUSH_SECONDS", 0.01)
    monkeypatch.setattr(botlogs, "URL_REFRESH_SECONDS", 0)
    monkeypatch.setattr(botlogs.discord.Webhook, "from_url", lambda url, session: FakeWebhook())
    h = _handler()
    ctx = SimpleNamespace(pool=pool, node_name="nuc-http")
    _log(h, "tcgpings.worker", logging.ERROR, "boom")
    task = asyncio.create_task(botlogs.post_loop(ctx, h))
    await asyncio.sleep(0.1)
    assert sent == [] and h.lines, "no channel yet: lines stay buffered"
    await queries.set_setting(pool, botlogs.SETTING_KEY, "https://discord.com/api/webhooks/1/x")
    for _ in range(50):
        if sent:
            break
        await asyncio.sleep(0.02)
    task.cancel()
    assert sent[0]["content"] == "```\nERROR tcgpings.worker: boom\n```"
    assert sent[0]["username"] == "logs · nuc-http"


class FakeCategory:
    def __init__(self, name, overwrites=None):
        self.name, self.overwrites, self.created = name, overwrites or {}, []

    async def create_text_channel(self, name, **kw):
        self.created.append((name, kw))
        return SimpleNamespace(name=name)


async def test_ensure_channel_uses_the_staff_category_and_its_permissions():
    staff = FakeCategory("STAFF", {"everyone": "hidden"})
    guild = SimpleNamespace(text_channels=[], categories=[FakeCategory("Alerts"), staff], me="bot")
    s = Settings(_env_file=None)
    channel = await botlogs.ensure_channel(guild, s)
    assert channel.name == "bot-logs"
    (name, kw), = staff.created
    assert "overwrites" not in kw, "Discord syncs it to the category; sending overwrites can be refused"

    guild.text_channels = [SimpleNamespace(name="bot-logs", id=5)]  # already there (maybe moved): reused
    assert (await botlogs.ensure_channel(guild, s)).id == 5
    assert len(staff.created) == 1
