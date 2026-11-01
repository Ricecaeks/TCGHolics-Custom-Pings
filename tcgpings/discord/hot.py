"""Hot sets: news feeds suggest releases, staff approve them in Discord, and the bot searches and checks them faster."""

from __future__ import annotations

import logging

import discord
from discord import app_commands

from tcgpings.cluster.leadership import reconcile
from tcgpings.context import Context
from tcgpings.db import queries
from tcgpings.discord.commands import _ctx, _reply, is_staff, ping_keywords_problem
from tcgpings.net.http import FetchError, NetPolicy
from tcgpings.news import FEEDS, parse_feed, suggest_keyword

log = logging.getLogger(__name__)

NEWS_POLICY = NetPolicy("news", 6)
MAX_CARDS_PER_SCAN = 5
HOT_DAYS = 14


async def find_candidates(ctx: Context) -> int:
    """Save new release headlines. The first headline per keyword becomes a card; later ones are duplicates."""
    added = 0
    for source, url in FEEDS.items():
        try:
            page = (await ctx.http.get(NEWS_POLICY, url)).text
        except FetchError as exc:
            log.warning("news feed %s unavailable: %s", source, exc)
            continue
        for headline in parse_feed(page, source):
            keyword = suggest_keyword(headline.title)
            status = "duplicate" if await queries.keyword_known(ctx.pool, keyword) else "pending"
            added += await queries.add_hot_candidate(
                ctx.pool, headline.source, headline.title, headline.url, keyword, status
            ) and status == "pending"
    return added


def card(row) -> tuple[discord.Embed, discord.ui.View]:
    embed = discord.Embed(title=row["title"][:256], url=row["url"] or None, color=0xF97316, description=(
        f"Suggested keyword: `{row['keyword']}`\n"
        f"Approve to search every retailer for it and speed up store checks for {HOT_DAYS} days. You can edit it first."
    ))
    embed.set_author(name="🔥 Possible hot release")
    embed.set_footer(text=row["source"])
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(label="Approve", style=discord.ButtonStyle.success, custom_id=f"hot:approve:{row['id']}"))
    view.add_item(discord.ui.Button(label="Ignore", style=discord.ButtonStyle.secondary, custom_id=f"hot:ignore:{row['id']}"))
    return embed, view


async def post_cards(ctx: Context, channel) -> int:
    rows = await queries.unposted_candidates(ctx.pool, MAX_CARDS_PER_SCAN)
    for row in rows:
        embed, view = card(row)
        message = await channel.send(embed=embed, view=view, allowed_mentions=discord.AllowedMentions.none())
        await queries.set_candidate_message(ctx.pool, row["id"], message.id)
    return len(rows)


async def scan_news(ctx: Context, bot) -> None:
    channel_id = ctx.settings.log_channel_id
    channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
    added = await find_candidates(ctx)
    posted = await post_cards(ctx, channel)
    log.info("news scan: %d new releases, %d cards posted", added, posted)


class ApproveModal(discord.ui.Modal, title="Approve hot release"):
    keyword = discord.ui.TextInput(label="Keyword to search and check faster", max_length=60)

    def __init__(self, candidate_id: int, suggested: str) -> None:
        super().__init__()
        self.candidate_id = candidate_id
        self.keyword.default = suggested

    async def on_submit(self, interaction: discord.Interaction) -> None:
        ctx = _ctx(interaction)
        keyword = " ".join(str(self.keyword).split())
        if problem := ping_keywords_problem(keyword):
            return await _reply(interaction, problem)
        await queries.mark_hot(ctx.pool, keyword, HOT_DAYS, interaction.user.id)
        await queries.set_candidate_status(ctx.pool, self.candidate_id, "approved")
        await reconcile(ctx)
        await interaction.response.edit_message(
            content=f"✅ Approved by {interaction.user.mention}: searching for `{keyword}` for {HOT_DAYS} days.",
            view=None, allowed_mentions=discord.AllowedMentions.none(),
        )


async def on_button(interaction: discord.Interaction) -> None:
    """Handles card buttons by their id, so cards keep working after the bot restarts."""
    _, action, candidate_id = interaction.data["custom_id"].split(":")
    if not is_staff(interaction):
        return await _reply(interaction, "Only staff can decide on hot releases.")
    ctx = _ctx(interaction)
    row = await queries.get_candidate(ctx.pool, int(candidate_id))
    if row is None or row["status"] != "pending":
        return await interaction.response.edit_message(view=None)
    if action == "approve":
        return await interaction.response.send_modal(ApproveModal(row["id"], row["keyword"]))
    await queries.set_candidate_status(ctx.pool, row["id"], "ignored")
    await interaction.response.edit_message(
        content=f"Ignored by {interaction.user.mention}.", view=None, allowed_mentions=discord.AllowedMentions.none()
    )


@app_commands.guild_only()
@app_commands.default_permissions(manage_guild=True)
class HotGroup(app_commands.Group, name="hot", description="Sets to search for and check faster"):
    @app_commands.command(name="add", description="Search every retailer for a set and check it faster")
    @app_commands.describe(keyword="e.g. delta reign", days="How long to check it faster")
    async def add(
        self, interaction: discord.Interaction, keyword: str, days: app_commands.Range[int, 1, 60] = HOT_DAYS
    ) -> None:
        ctx = _ctx(interaction)
        keyword = " ".join(keyword.split())
        if problem := ping_keywords_problem(keyword):
            return await _reply(interaction, problem)
        await queries.mark_hot(ctx.pool, keyword, days, interaction.user.id)
        await reconcile(ctx)
        await _reply(interaction, f"🔥 `{keyword}` is hot for {days} days.")

    @app_commands.command(name="list", description="Show hot sets")
    async def list(self, interaction: discord.Interaction) -> None:
        rows = await queries.list_hot_watches(_ctx(interaction).pool)
        lines = [f"`{r['query']}` until <t:{int(r['hot_until'].timestamp())}:d>" for r in rows]
        await _reply(interaction, "\n".join(lines) or "No hot sets. Add one with `/hot add`.")

    @app_commands.command(name="remove", description="Stop checking a set faster (it's still searched for)")
    async def remove(self, interaction: discord.Interaction, keyword: str) -> None:
        ctx = _ctx(interaction)
        if not await queries.unmark_hot(ctx.pool, " ".join(keyword.split())):
            return await _reply(interaction, f"`{keyword}` isn't hot. Check `/hot list`.")
        await reconcile(ctx)
        await _reply(interaction, f"`{keyword}` is back to normal checks.")
