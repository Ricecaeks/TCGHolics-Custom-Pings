"""Discord gateway client. Runs on the leader node only; handles slash commands and staff notices."""

from __future__ import annotations

import asyncio
import logging

import discord
from discord import app_commands

from tcgpings.context import Context

log = logging.getLogger(__name__)


class TCGBot(discord.Client):
    def __init__(self, ctx: Context) -> None:
        super().__init__(intents=discord.Intents.default())
        self.ctx = ctx
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        from tcgpings.discord.commands import register

        register(self.tree)
        guild_id = self.ctx.settings.guild_id
        if guild_id:
            guild = discord.Object(id=guild_id)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
        else:
            synced = await self.tree.sync()  # global commands can take up to an hour to appear
        log.info("synced %d slash commands", len(synced))

    async def on_ready(self) -> None:
        log.info("discord bot connected as %s", self.user)

    async def notify_staff(self, text: str) -> None:
        channel_id = self.ctx.settings.log_channel_id
        if not channel_id:
            return
        try:
            await asyncio.wait_for(self.wait_until_ready(), 30)
            channel = self.get_channel(channel_id) or await self.fetch_channel(channel_id)
            await channel.send(text[:2000], allowed_mentions=discord.AllowedMentions.none())
        except Exception:
            log.exception("could not post to staff log channel")
