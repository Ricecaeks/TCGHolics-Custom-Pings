"""Member keyword pings: validation, and how tags are sent to Discord."""

from types import SimpleNamespace

import discord
import pytest

from tcgpings.discord import sender
from tcgpings.discord.commands import allowed, ping_keywords_problem, spotted_event
from tcgpings.discord.embeds import build_embed
from tcgpings.discord.sender import MAX_CONTENT, deliver, ping_messages
from tcgpings.models import Event, EventType


@pytest.mark.parametrize("keywords", ["30th", "30th booster bundle, -sleeves", "+sylvia park", "op"])
def test_ping_keywords_allowed(keywords):
    assert ping_keywords_problem(keywords) is None


@pytest.mark.parametrize("keywords", ["-sleeves", ",", "a", "pokemon a", "x" * 101])
def test_ping_keywords_that_would_tag_on_everything_are_refused(keywords):
    assert ping_keywords_problem(keywords)


def test_ping_message_lists_each_keyword_with_its_members():
    assert ping_messages([{"keywords": "30th", "users": [1, 2]}, {"keywords": "albany", "users": [3]}]) == [
        ("Keyword Matched: **30th** - <@1> <@2>\nKeyword Matched: **albany** - <@3>", [1, 2, 3])]
    assert ping_messages(None) == []


def test_long_ping_lists_split_and_every_member_is_tagged_once():
    users = list(range(10**17, 10**17 + 300))
    messages = ping_messages([{"keywords": "30th", "users": users}])
    assert len(messages) > 1 and all(len(text) <= MAX_CONTENT for text, _ in messages)
    assert all(text.startswith("Keyword Matched: **30th** -") for text, _ in messages)
    assert [u for _, tagged in messages for u in tagged] == users


def test_member_keywords_cannot_mention_anyone():
    [(text, _)] = ping_messages([{"keywords": "@everyone <@&123> <@456>", "users": [1]}])
    assert "@everyone" not in text and "<@&123>" not in text and "<@456>" not in text


async def test_deliver_only_allows_the_tagged_members(monkeypatch):
    sent = []

    class FakeWebhook:
        async def send(self, **kw):
            sent.append(kw)

    monkeypatch.setattr(sender.discord.Webhook, "from_url", lambda *a, **k: FakeWebhook())
    users = list(range(10**17, 10**17 + 150))
    event = Event(type=EventType.RESTOCK, retailer_id="kmart", sku="x", title="Pokemon 30th", url="https://x",
                  new_level="in", old_level="out", extra={"pings": [{"keywords": "30th", "users": users}]})
    ctx = SimpleNamespace(settings=SimpleNamespace(dry_run=False))
    await deliver(ctx, None, event, "https://discord.test/x", None)
    assert isinstance(sent[0]["embed"], discord.Embed) and len(sent) == 2 and "embed" not in sent[1]
    for message in sent:
        allowed = message["allowed_mentions"]
        assert allowed.everyone is False and allowed.roles is False and len(allowed.users) <= 100


def test_spotted_alert_is_labelled_a_member_report_and_names_the_reporter():
    event = spotted_event("Pokemon 30th Booster Bundle", "warehouse", "The Warehouse", "Westgate", 42, "limit *2*")
    embed = build_embed(Event.from_payload(event.to_payload()))
    assert embed.author.name == "👀 Spotted in store · The Warehouse · Westgate"
    assert embed.url is None and embed.description is None
    fields = {f.name: f.value for f in embed.fields}
    assert fields["Reported by"] == "<@42>" and fields["Store"] == "Westgate" and fields["Game"] == "Pokémon"
    assert fields["Note"] == "Member report, not confirmed by the retailer. limit \\*2\\*"


def interaction(command_name, roles=(), trusted_role=7, parent=None):
    user = SimpleNamespace(roles=[SimpleNamespace(id=r) for r in roles])
    command = SimpleNamespace(name=command_name, root_parent=SimpleNamespace(name=parent) if parent else None)
    ctx = SimpleNamespace(settings=SimpleNamespace(trusted_role_id=trusted_role, staff_role_id=9))
    return SimpleNamespace(user=user, command=command, client=SimpleNamespace(ctx=ctx))


def test_who_can_use_what():
    assert allowed(interaction("add", parent="ping"))  # /ping is open to everyone
    assert not allowed(interaction("spotted"))
    assert not allowed(interaction("spotted", roles=[1]))
    assert allowed(interaction("spotted", roles=[7]))
    assert not allowed(interaction("spotted", roles=[0], trusted_role=0))  # no role configured
    assert not allowed(interaction("status", roles=[7]))  # trusted members aren't staff
