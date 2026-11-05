"""#bot-logs: every node's warnings and errors, posted to a staff channel.

The leader makes sure the channel exists (in the Staff category, with its permissions) and saves the
channel's webhook in `bot_settings`. Every node keeps its own log lines in a small buffer and posts them
through that webhook every 30 seconds, so a busy minute is a few messages, not hundreds. Lines that don't
fit are counted and left to the log file, so Discord's rate limits can never slow the bot down.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections import deque
from collections.abc import Sequence

import aiohttp
import discord

from tcgpings.config import Settings
from tcgpings.context import Context
from tcgpings.db import queries

log = logging.getLogger(__name__)

SETTING_KEY = "bot_logs_webhook"
FLUSH_SECONDS = 30
URL_REFRESH_SECONDS = 300
MAX_BUFFER = 300  # lines held between posts; past this they're counted, not kept
MAX_MESSAGES = 3  # per post round, per node
MAX_LINE = 1500
MAX_CONTENT = 1990  # Discord's limit is 2000
# Our own posting problems, and discord.py's webhook rate-limit notices, would feed back into the channel.
IGNORED = (__name__, "discord.webhook")


QUERY_SECRET = re.compile(r"\b(key|api_key|apikey|token|access_token)=[^&\s\"'<>]+", re.IGNORECASE)
WEBHOOK_TOKEN = re.compile(r"(/api(?:/v\d+)?/webhooks/\d+/)[\w-]+")


def redact(text: str, secrets: Sequence[str] = ()) -> str:
    """Hide keys and tokens an error message may carry (e.g. ScrapFly's `?key=` in a failed URL)."""
    for secret in secrets:
        text = text.replace(secret, "***")
    text = QUERY_SECRET.sub(r"\1=***", text)
    return WEBHOOK_TOKEN.sub(r"\1***", text)


def secret_values(settings: Settings) -> list[str]:
    names = ("discord_token", "alert_webhook_url", "zyte_api_key", "scrapfly_api_key", "scrapfly_api_key_kmart",
             "scrapfly_api_key_farmers", "scrapfly_api_key_warehouse", "database_url")
    values = [str(getattr(settings, n, "") or "") for n in names] + list(settings.proxies)
    return sorted({v for v in values if len(v) >= 8}, key=len, reverse=True)


class DiscordLogHandler(logging.Handler):
    """Buffers formatted log lines for `post_loop`; never blocks or touches the network."""

    def __init__(self, level: int | str = logging.WARNING, max_lines: int = MAX_BUFFER,
                 secrets: Sequence[str] = ()) -> None:
        super().__init__(level)
        self.max_lines = max_lines
        self.secrets = list(secrets)
        self.lines: deque[str] = deque()
        self.dropped = 0

    def emit(self, record: logging.LogRecord) -> None:
        if record.name.startswith(IGNORED):
            return
        try:
            line = redact(self.format(record), self.secrets)
        except Exception:
            self.handleError(record)
            return
        if len(self.lines) >= self.max_lines:
            self.dropped += 1
        else:
            self.lines.append(line)

    def take(self) -> tuple[list[str], int]:
        with self.lock:  # type: ignore[union-attr]  # emit runs under the same lock
            lines, dropped = list(self.lines), self.dropped
            self.lines.clear()
            self.dropped = 0
        return lines, dropped


def install(settings: Settings) -> DiscordLogHandler | None:
    if not settings.bot_logs_channel:
        return None
    handler = DiscordLogHandler(settings.bot_logs_level.upper(), secrets=secret_values(settings))
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    logging.getLogger().addHandler(handler)
    return handler


def messages(lines: Sequence[str], dropped: int, max_messages: int = MAX_MESSAGES) -> list[str]:
    """Pack lines into code-block messages. Repeats in a row become one line with a count."""
    collapsed: list[str] = []
    last, count = None, 0
    for line in [*lines, None]:
        if line == last:
            count += 1
            continue
        if last is not None:
            collapsed.append(last if count == 1 else f"{last}  (×{count})")
        last, count = line, 1
    collapsed = [c if len(c) <= MAX_LINE else c[:MAX_LINE] + " …" for c in collapsed]

    chunks: list[list[str]] = [[]]
    size = 0
    for line in collapsed:
        cost = len(line.replace("```", "'''")) + 1
        if chunks[-1] and size + cost > MAX_CONTENT - 100:  # room for the fences and the note
            chunks.append([])
            size = 0
        chunks[-1].append(line.replace("```", "'''"))
        size += cost
    chunks = [c for c in chunks if c]
    left = sum(len(c) for c in chunks[max_messages:]) + dropped
    out = ["```\n" + "\n".join(c) + "\n```" for c in chunks[:max_messages]]
    if left:
        note = f"… {left} more line(s) not posted; see the log file."
        if out:
            out[-1] += "\n" + note
        else:
            out.append(note)
    return out


async def post_loop(ctx: Context, handler: DiscordLogHandler) -> None:
    url: str | None = None
    checked = 0.0
    async with aiohttp.ClientSession() as session:
        while True:
            await asyncio.sleep(FLUSH_SECONDS)
            try:
                if url is None or time.monotonic() - checked > URL_REFRESH_SECONDS:
                    url = await queries.get_setting(ctx.pool, SETTING_KEY)
                    checked = time.monotonic()
                if not url:
                    continue  # no channel yet: keep buffering (capped) until the leader makes it
                lines, dropped = handler.take()
                if not lines and not dropped:
                    continue
                webhook = discord.Webhook.from_url(url, session=session)
                for content in messages(lines, dropped):
                    await webhook.send(content=content, username=f"logs · {ctx.node_name}"[:80],
                                       allowed_mentions=discord.AllowedMentions.none())
            except asyncio.CancelledError:
                raise
            except discord.NotFound:
                log.warning("bot logs webhook is gone; waiting for the leader to make a new one")
                url = None
            except Exception:
                log.exception("could not post to the bot logs channel")


# --- leader: make sure the channel and its webhook exist --------------------------------


def find_category(guild: discord.Guild, name: str) -> discord.CategoryChannel | None:
    wanted = name.lower()
    exact = [c for c in guild.categories if c.name.lower() == wanted]
    return (exact or [c for c in guild.categories if wanted in c.name.lower()] or [None])[0]


async def ensure_channel(guild: discord.Guild, settings: Settings) -> discord.TextChannel:
    channel = discord.utils.get(guild.text_channels, name=settings.bot_logs_channel)
    if channel is not None:
        return channel
    category = find_category(guild, settings.bot_logs_category)
    if category is None:  # private by default: staff and the bot only
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_webhooks=True),
        }
        role = guild.get_role(settings.staff_role_id) if settings.staff_role_id else None
        if role is not None:
            overwrites[role] = discord.PermissionOverwrite(view_channel=True)
        category = await guild.create_category(settings.bot_logs_category, overwrites=overwrites,
                                               reason="TCGHolics Pings bot logs")
    # No overwrites: Discord then syncs the channel to the category's permissions. Sending them ourselves
    # is refused (403) whenever a category rule covers a permission the bot doesn't hold.
    return await category.create_text_channel(
        settings.bot_logs_channel, reason="TCGHolics Pings bot logs",
        topic="The bot's warnings and errors from every node, every 30 seconds. Full logs are on the NUC.",
    )


async def bot_logs_setup_loop(ctx: Context, bot, every: float) -> None:
    from tcgpings.discord.commands import _webhook_for

    await bot.wait_until_ready()
    reported = ""
    while True:
        try:
            guild = bot.get_guild(ctx.settings.guild_id)
            if guild is not None:
                channel = await ensure_channel(guild, ctx.settings)
                url = (await _webhook_for(channel, bot.user)).url
                if url != await queries.get_setting(ctx.pool, SETTING_KEY):
                    await queries.set_setting(ctx.pool, SETTING_KEY, url)
                    log.info("bot logs post to #%s", channel.name)
                reported = ""
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.exception("bot logs channel setup failed")
            problem = f"⚠️ Can't set up #{ctx.settings.bot_logs_channel}: {exc}"
            if isinstance(exc, discord.Forbidden):
                problem += (f". The bot needs View Channels, Manage Channels and Manage Webhooks in the "
                            f"{ctx.settings.bot_logs_category} category.")
            if problem != reported:  # once per distinct problem, e.g. missing Manage Channels
                await bot.notify_staff(problem)
                reported = problem
        await asyncio.sleep(every)
