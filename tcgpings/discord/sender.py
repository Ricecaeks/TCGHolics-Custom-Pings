"""Every node: drain the alert outbox to Discord webhooks.

Webhooks don't need the bot's gateway connection, so all nodes can send; SKIP LOCKED
leasing keeps two nodes from sending the same row.
"""

from __future__ import annotations

import asyncio
import logging

import aiohttp
import discord

from tcgpings.context import Context
from tcgpings.db import queries
from tcgpings.discord.embeds import build_embed
from tcgpings.models import Event

log = logging.getLogger(__name__)

POLL_SECONDS = 2
BATCH = 10
MAX_CONTENT = 1900  # Discord's limit is 2000


async def sender_loop(ctx: Context) -> None:
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                sent = await send_batch(ctx, session)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("outbox send failed")
                sent = 0
            if sent < BATCH:
                await asyncio.sleep(POLL_SECONDS)


async def send_batch(ctx: Context, session: aiohttp.ClientSession) -> int:
    rows = await queries.claim_alerts(ctx.pool, ctx.node_name, BATCH)
    for row in rows:
        event = Event.from_payload(row["payload"])
        try:
            await deliver(ctx, session, event, row["webhook_url"], row["role_id"])
        except discord.NotFound:
            await queries.mark_alert_failed(ctx.pool, row["id"], "webhook deleted", 3600)
            log.error("webhook for channel %s no longer exists; re-run /route set there", row["channel_id"])
            continue
        except (discord.HTTPException, aiohttp.ClientError, asyncio.TimeoutError) as exc:
            delay = min(10 * 2 ** row["attempts"], 1800)
            await queries.mark_alert_failed(ctx.pool, row["id"], str(exc), delay)
            log.warning("alert %s failed (attempt %d): %s", row["id"], row["attempts"] + 1, exc)
            continue
        await queries.mark_alert_sent(ctx.pool, row["id"])
        ctx.stats.alerts_sent += 1
    return len(rows)


def ping_messages(pings: list[dict] | None) -> list[tuple[str, list[int]]]:
    """Each matched keyword's line tagging its members, split to fit Discord's message limit.

    Returns (text, users tagged in that text). Keywords are members' own text, so they can't mention anyone.
    """
    messages: list[tuple[str, list[int]]] = []
    text, users = "", []

    def flush() -> None:
        nonlocal text, users
        if text:
            messages.append((text, users))
        text, users = "", []

    for ping in pings or []:
        keywords = discord.utils.escape_markdown(ping["keywords"]).replace("@", "@​")
        line = f"Keyword Matched: **{keywords}** -"
        if len(text) + len(line) + 30 > MAX_CONTENT:
            flush()
        text += ("\n" if text else "") + line
        for user_id in ping["users"]:
            mention = f" <@{user_id}>"
            if len(text) + len(mention) > MAX_CONTENT:
                flush()
                text = line
            text += mention
            users.append(user_id)
    flush()
    return messages


async def deliver(
    ctx: Context, session: aiohttp.ClientSession, event: Event, webhook_url: str, role_id: int | None
) -> None:
    embed = build_embed(event)
    role = f"<@&{role_id}>" if role_id else None
    messages = ping_messages(event.extra.get("pings"))
    first, tagged = messages[0] if messages else (None, [])
    content = "\n".join(filter(None, [role, first])) or None
    if ctx.settings.dry_run:
        fields = ", ".join(f"{f.name}={f.value}" for f in embed.fields)
        log.info("[dry-run] %s | %s | %s | %s %s", embed.author.name, embed.title, embed.description, fields, content or "")
        return
    webhook = discord.Webhook.from_url(webhook_url, session=session)
    await webhook.send(content=content, embed=embed, allowed_mentions=_mentions(tagged, role_id))
    for text, users in messages[1:]:
        await webhook.send(content=text, allowed_mentions=_mentions(users))


def _mentions(users: list[int], role_id: int | None = None) -> discord.AllowedMentions:
    return discord.AllowedMentions(
        everyone=False,
        roles=[discord.Object(role_id)] if role_id else False,
        users=[discord.Object(u) for u in users] or False,
    )
