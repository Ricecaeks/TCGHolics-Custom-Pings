"""Slash commands. Every command is restricted to the staff role (or server admins)."""

from __future__ import annotations

import logging
import time

import discord
from discord import app_commands

from tcgpings.classify import FRANCHISE_NAMES
from tcgpings.cluster.leadership import reconcile
from tcgpings.context import Context
from tcgpings.db import queries
from tcgpings.discord.embeds import sample_event
from tcgpings.models import ONLINE, EventType, slugify
from tcgpings.retailers import REGISTRY, build_adapter

log = logging.getLogger(__name__)

WEBHOOK_NAME = "TCGHolics Pings"
FRANCHISE_CHOICES = [app_commands.Choice(name=v, value=k) for k, v in FRANCHISE_NAMES.items()]
EVENT_NAMES = {e.value for e in EventType}
MAX_CHANNELS_PER_CATEGORY = 50


def _ctx(interaction: discord.Interaction) -> Context:
    return interaction.client.ctx  # type: ignore[attr-defined]


def is_staff(interaction: discord.Interaction) -> bool:
    member = interaction.user
    if not isinstance(member, discord.Member):
        return False
    if member.guild_permissions.administrator:
        return True
    role_id = _ctx(interaction).settings.staff_role_id
    return bool(role_id) and any(r.id == role_id for r in member.roles)


async def _reply(interaction: discord.Interaction, text: str) -> None:
    text = text if len(text) <= 1990 else text[:1980] + "\n…"
    if interaction.response.is_done():
        await interaction.followup.send(text, ephemeral=True)
    else:
        await interaction.response.send_message(text, ephemeral=True)


# --- autocomplete ----------------------------------------------------------------------


async def retailer_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    rows = await _ctx(interaction).adapters.all()
    current = current.lower()
    return [
        app_commands.Choice(name=f"{r['name']} ({r['id']})", value=r["id"])
        for r in rows
        if current in r["id"].lower() or current in r["name"].lower()
    ][:25]


async def store_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    retailer_id = getattr(interaction.namespace, "retailer", None)
    if not retailer_id:
        return []
    stores = await queries.list_stores(_ctx(interaction).pool, retailer_id)
    current = current.lower()
    choices = [app_commands.Choice(name="Online only", value="online")] if "online".startswith(current) else []
    choices += [
        app_commands.Choice(name=s["name"], value=s["store_id"])
        for s in stores
        if current in s["name"].lower() or current in s["slug"]
    ]
    return choices[:25]


async def _resolve_stores(ctx: Context, retailer_id: str, refs: str) -> tuple[list[str], list[str]]:
    found, missing = [], []
    for ref in (r.strip() for r in refs.split(",")):
        if not ref:
            continue
        store = await queries.resolve_store(ctx.pool, retailer_id, ref)
        (found.append(store["store_id"]) if store else missing.append(ref))
    return found, missing


def _describe_route(r) -> str:
    store = "online" if r["store_id"] == ONLINE else (r["store_id"] or "any store")
    events = ", ".join(r["event_types"]) if r["event_types"] else "default events"
    role = f" · <@&{r['role_id']}>" if r["role_id"] else ""
    return (
        f"**#{r['id']}** <#{r['channel_id']}> · {r['retailer_id'] or 'any retailer'} · {store}"
        f" · {r['franchise'] or 'any game'} · {events}{role}"
    )


async def _webhook_for(channel: discord.TextChannel, me: discord.abc.User) -> discord.Webhook:
    for hook in await channel.webhooks():
        if hook.name == WEBHOOK_NAME and hook.user and hook.user.id == me.id and hook.token:
            return hook
    return await channel.create_webhook(name=WEBHOOK_NAME, reason="TCGHolics Pings alert route")


# --- /watch ----------------------------------------------------------------------------


@app_commands.guild_only()
@app_commands.default_permissions(manage_guild=True)
class WatchGroup(app_commands.Group, name="watch", description="What to monitor"):
    @app_commands.command(name="add", description="Watch a keyword (e.g. 'pokemon 30th') or a product URL")
    @app_commands.describe(
        query="Keyword search, or a product URL / 'sku:<id>' for one specific product",
        retailer="Limit to one retailer (required for sku:)",
        stores="Comma-separated store names for store-level stock (default: all stores)",
        franchise="Only products from this game",
        interval="Seconds between checks (default 60 for products, 300 for keywords)",
    )
    @app_commands.choices(franchise=FRANCHISE_CHOICES)
    @app_commands.autocomplete(retailer=retailer_autocomplete)
    async def add(
        self,
        interaction: discord.Interaction,
        query: str,
        retailer: str | None = None,
        stores: str | None = None,
        franchise: app_commands.Choice[str] | None = None,
        interval: app_commands.Range[int, 30, 86_400] | None = None,
    ) -> None:
        ctx = _ctx(interaction)
        await interaction.response.defer(ephemeral=True, thinking=True)
        rows = await ctx.adapters.all()
        kind, ref = "keyword", query.strip()

        if ref.lower().startswith(("http://", "https://")):
            kind = "sku"
            if retailer is None:
                for row in rows:
                    if row["adapter"] in REGISTRY and build_adapter(row, ctx.http).matches_url(ref):
                        retailer = row["id"]
                        break
            if retailer is None:
                return await _reply(interaction, "Couldn't tell which retailer that URL belongs to; pass `retailer`.")
        elif ref.lower().startswith("sku:"):
            kind, ref = "sku", ref[4:].strip()
            if retailer is None:
                return await _reply(interaction, "`sku:` watches need a `retailer`.")

        if retailer is not None and retailer not in {r["id"] for r in rows}:
            return await _reply(interaction, f"Unknown retailer `{retailer}`.")
        if kind == "sku":
            ref = (await ctx.adapters.get(retailer)).parse_ref(ref)

        store_ids = None
        if stores:
            if retailer is None:
                return await _reply(interaction, "Pick a `retailer` to filter by store.")
            store_ids, missing = await _resolve_stores(ctx, retailer, stores)
            if missing:
                return await _reply(interaction, f"Unknown store(s): {', '.join(missing)}. Try `/stores {retailer}`.")

        watch_id = await queries.add_watch(
            ctx.pool, kind, ref, retailer, store_ids, franchise.value if franchise else None,
            interval, interaction.user.id,
        )
        jobs = await reconcile(ctx)
        scope = retailer or "all retailers"
        where = f"{len(store_ids)} store(s)" if store_ids else "all stores"
        await _reply(
            interaction,
            f"Watch **#{watch_id}** added: {kind} `{ref}` at {scope}, {where}. "
            f"{jobs} jobs scheduled. The first check is a silent baseline; changes after that alert.",
        )

    @app_commands.command(name="list", description="List watches")
    async def list(self, interaction: discord.Interaction) -> None:
        rows = await queries.list_watches(_ctx(interaction).pool)
        if not rows:
            return await _reply(interaction, "No watches yet. Add one with `/watch add`.")
        lines = [
            f"**#{w['id']}** {w['kind']} `{w['query']}` · {w['retailer_id'] or 'all retailers'}"
            f" · {len(w['store_ids']) if w['store_ids'] else 'all'} stores"
            f"{' · ' + FRANCHISE_NAMES.get(w['franchise'], w['franchise']) if w['franchise'] else ''}"
            f"{'' if w['enabled'] else ' · disabled'}"
            for w in rows
        ]
        await _reply(interaction, "\n".join(lines))

    @app_commands.command(name="remove", description="Remove a watch by id")
    async def remove(self, interaction: discord.Interaction, watch_id: int) -> None:
        ctx = _ctx(interaction)
        if not await queries.remove_watch(ctx.pool, watch_id):
            return await _reply(interaction, f"No watch #{watch_id}.")
        await reconcile(ctx)
        await _reply(interaction, f"Removed watch #{watch_id}.")


# --- /route ----------------------------------------------------------------------------


@app_commands.guild_only()
@app_commands.default_permissions(manage_guild=True)
class RouteGroup(app_commands.Group, name="route", description="Which alerts go to which channel"):
    @app_commands.command(name="set", description="Send matching alerts to this channel")
    @app_commands.describe(
        retailer="Only this retailer (default: any)",
        store="Only this store, or 'online' (default: any store and online)",
        franchise="Only this game (default: any)",
        events="Comma list of: new_product, restock, qty_change, price_change, out_of_stock "
               "(default: all except out_of_stock)",
        role="Role to ping with each alert",
    )
    @app_commands.choices(franchise=FRANCHISE_CHOICES)
    @app_commands.autocomplete(retailer=retailer_autocomplete, store=store_autocomplete)
    async def set(
        self,
        interaction: discord.Interaction,
        retailer: str | None = None,
        store: str | None = None,
        franchise: app_commands.Choice[str] | None = None,
        events: str | None = None,
        role: discord.Role | None = None,
    ) -> None:
        ctx = _ctx(interaction)
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            return await _reply(interaction, "Run this in a text channel.")
        if store and not retailer:
            return await _reply(interaction, "Pick a `retailer` to route a specific store.")
        if retailer and not await queries.get_retailer(ctx.pool, retailer):
            return await _reply(interaction, f"Unknown retailer `{retailer}`.")

        store_id = None
        if store:
            if store.lower() == "online":
                store_id = ONLINE
            else:
                found = await queries.resolve_store(ctx.pool, retailer, store)
                if not found:
                    return await _reply(interaction, f"Unknown store `{store}`. Try `/stores {retailer}`.")
                store_id = found["store_id"]

        event_types = None
        if events and events.strip().lower() != "all":
            event_types = [e.strip().lower() for e in events.split(",") if e.strip()]
            if bad := [e for e in event_types if e not in EVENT_NAMES]:
                return await _reply(interaction, f"Unknown event type(s): {', '.join(bad)}")

        await interaction.response.defer(ephemeral=True, thinking=True)
        hook = await _webhook_for(channel, interaction.client.user)
        route_id = await queries.add_route(
            ctx.pool, channel.id, hook.url, retailer, store_id,
            franchise.value if franchise else None, event_types, role.id if role else None,
        )
        ctx.routes.invalidate()
        await _reply(interaction, f"Route **#{route_id}** → {channel.mention}. Use `/test-alert` to check it.")

    @app_commands.command(name="list", description="List routes (this channel only by default)")
    async def list(self, interaction: discord.Interaction, everywhere: bool = False) -> None:
        rows = await queries.list_routes(_ctx(interaction).pool)
        if not everywhere:
            rows = [r for r in rows if r["channel_id"] == interaction.channel_id]
        if not rows:
            return await _reply(interaction, "No routes here. Add one with `/route set`.")
        await _reply(interaction, "\n".join(_describe_route(r) for r in rows))

    @app_commands.command(name="remove", description="Remove a route by id")
    async def remove(self, interaction: discord.Interaction, route_id: int) -> None:
        ctx = _ctx(interaction)
        if not await queries.remove_route(ctx.pool, route_id):
            return await _reply(interaction, f"No route #{route_id}.")
        ctx.routes.invalidate()
        await _reply(interaction, f"Removed route #{route_id}.")

    @app_commands.command(name="autocreate", description="Create one channel per store for a retailer, with routes")
    @app_commands.autocomplete(retailer=retailer_autocomplete)
    async def autocreate(self, interaction: discord.Interaction, retailer: str, role: discord.Role | None = None) -> None:
        ctx = _ctx(interaction)
        guild = interaction.guild
        row = await queries.get_retailer(ctx.pool, retailer)
        if row is None or guild is None:
            return await _reply(interaction, f"Unknown retailer `{retailer}`.")
        stores = await queries.list_stores(ctx.pool, retailer)
        if not stores:
            return await _reply(interaction, f"No stores known for `{retailer}` yet (store sync runs on startup).")
        await interaction.response.defer(ephemeral=True, thinking=True)

        existing = {r["channel_id"]: r for r in await queries.list_routes(ctx.pool)}
        prefix = slugify(row["name"])
        created = routed = 0
        for start in range(0, len(stores), MAX_CHANNELS_PER_CATEGORY):
            chunk = stores[start : start + MAX_CHANNELS_PER_CATEGORY]
            suffix = f" {start // MAX_CHANNELS_PER_CATEGORY + 1}" if len(stores) > MAX_CHANNELS_PER_CATEGORY else ""
            cat_name = f"{row['name']}{suffix}"
            category = discord.utils.get(guild.categories, name=cat_name) or await guild.create_category(cat_name)
            for s in chunk:
                name = f"{prefix}-{s['slug']}"[:100]
                channel = discord.utils.get(category.text_channels, name=name)
                if channel is None:
                    channel = await category.create_text_channel(name, topic=f"{row['name']} {s['name']} stock alerts")
                    created += 1
                route = existing.get(channel.id)
                if route and route["retailer_id"] == retailer and route["store_id"] == s["store_id"]:
                    continue
                hook = await _webhook_for(channel, interaction.client.user)
                await queries.add_route(ctx.pool, channel.id, hook.url, retailer, s["store_id"], role_id=role.id if role else None)
                routed += 1
        ctx.routes.invalidate()
        await _reply(interaction, f"{created} channels created, {routed} routes added for {row['name']}.")


# --- /retailer -------------------------------------------------------------------------


@app_commands.guild_only()
@app_commands.default_permissions(manage_guild=True)
class RetailerGroup(app_commands.Group, name="retailer", description="Retailers being monitored"):
    @app_commands.command(name="add-shopify", description="Monitor a Shopify-based card shop")
    @app_commands.describe(domain="Shop domain, e.g. cardshop.co.nz", name="Display name")
    async def add_shopify(self, interaction: discord.Interaction, domain: str, name: str) -> None:
        ctx = _ctx(interaction)
        domain = domain.strip().removeprefix("https://").removeprefix("http://").strip("/")
        retailer_id = slugify(name)
        await queries.upsert_retailer(ctx.pool, retailer_id, "shopify", name, {"domain": domain})
        await ctx.adapters.refresh(force=True)
        await _reply(interaction, f"Added **{name}** (`{retailer_id}`, {domain}). Now `/watch add` keywords for it.")

    @app_commands.command(name="list", description="List retailers")
    async def list(self, interaction: discord.Interaction) -> None:
        rows = await queries.list_retailers(_ctx(interaction).pool)
        lines = [
            f"`{r['id']}` **{r['name']}** · {r['adapter']} · {r['requests_per_minute']} req/min"
            f" · proxy {r['proxy_policy']}{'' if r['enabled'] else ' · **disabled**'}"
            for r in rows
        ]
        await _reply(interaction, "\n".join(lines) or "No retailers.")

    @app_commands.command(name="set", description="Tune a retailer")
    @app_commands.autocomplete(retailer=retailer_autocomplete)
    @app_commands.choices(proxy_policy=[app_commands.Choice(name=p, value=p) for p in ("direct", "pool", "sticky")])
    async def set(
        self,
        interaction: discord.Interaction,
        retailer: str,
        enabled: bool | None = None,
        proxy_policy: app_commands.Choice[str] | None = None,
        requests_per_minute: app_commands.Range[int, 1, 600] | None = None,
    ) -> None:
        ctx = _ctx(interaction)
        ok = await queries.update_retailer(
            ctx.pool, retailer, enabled=enabled,
            proxy_policy=proxy_policy.value if proxy_policy else None,
            requests_per_minute=requests_per_minute,
        )
        await ctx.adapters.refresh(force=True)
        await _reply(interaction, f"Updated `{retailer}`." if ok else f"Nothing changed for `{retailer}`.")


# --- single commands -------------------------------------------------------------------


@app_commands.command(name="stores", description="List a retailer's stores")
@app_commands.guild_only()
@app_commands.default_permissions(manage_guild=True)
@app_commands.autocomplete(retailer=retailer_autocomplete)
async def stores_cmd(interaction: discord.Interaction, retailer: str) -> None:
    rows = await queries.list_stores(_ctx(interaction).pool, retailer)
    if not rows:
        return await _reply(interaction, f"No stores known for `{retailer}`.")
    await _reply(interaction, f"**{len(rows)} stores**\n" + "\n".join(f"`{s['store_id']}` {s['name']}" for s in rows))


@app_commands.command(name="status", description="Cluster, retailer and alert health")
@app_commands.guild_only()
@app_commands.default_permissions(manage_guild=True)
async def status_cmd(interaction: discord.Interaction) -> None:
    ctx = _ctx(interaction)
    s = ctx.settings
    nodes = await queries.list_nodes(ctx.pool)
    lines = ["**Nodes**"]
    for n in nodes:
        alive = n["age"] < s.node_stale_seconds
        lines.append(
            f"{'🟢' if alive else '🔴'} `{n['name']}`{' 👑' if n['is_leader'] and alive else ''}"
            f" v{n['version']} · seen {int(n['age'])}s ago · jobs {n['jobs_ok']} ok / {n['jobs_failed']} failed"
            f" · {n['alerts_sent']} alerts"
        )
    lines.append("\n**Retailers**")
    now = time.time()
    for h in await queries.job_health(ctx.pool):
        last = f"{int(now - h['last_ok_at'].timestamp())}s ago" if h["last_ok_at"] else "never"
        icon = "🔴" if h["failing"] == h["jobs"] else ("🟡" if h["failing"] or h["overdue"] else "🟢")
        lines.append(
            f"{icon} `{h['retailer_id']}` · {h['jobs']} jobs · {h['failing']} failing"
            f" · {h['overdue']} overdue · last ok {last}"
        )
    backlog = await queries.outbox_backlog(ctx.pool)
    size = await queries.database_size_mb(ctx.pool)
    lines.append(
        f"\n**Alerts** {backlog['pending']} pending · {backlog['dead']} undeliverable"
        f"\n**Database** {size:.0f} MB / warn at {s.db_size_warn_mb} MB"
        f"\n**Proxies** {len(ctx.http.proxies.healthy())}/{len(ctx.http.proxies.urls)} healthy"
    )
    await _reply(interaction, "\n".join(lines))


@app_commands.command(name="test-alert", description="Send a sample alert through every route in this channel")
@app_commands.guild_only()
@app_commands.default_permissions(manage_guild=True)
async def test_alert_cmd(interaction: discord.Interaction) -> None:
    ctx = _ctx(interaction)
    routes = [r for r in await queries.list_routes(ctx.pool) if r["channel_id"] == interaction.channel_id]
    if not routes:
        return await _reply(interaction, "No routes in this channel. Add one with `/route set`.")
    event = sample_event()
    for r in routes:
        await queries.enqueue_alert(ctx.pool, f"test|{r['id']}|{time.time()}", r["id"], event.to_payload())
    await _reply(interaction, f"Queued a test alert for {len(routes)} route(s); it should appear within a few seconds.")


def register(tree: app_commands.CommandTree) -> None:
    for group in (WatchGroup(), RouteGroup(), RetailerGroup()):
        tree.add_command(group)
    for cmd in (stores_cmd, status_cmd, test_alert_cmd):
        tree.add_command(cmd)

    async def check(interaction: discord.Interaction) -> bool:
        if is_staff(interaction):
            return True
        await _reply(interaction, "Only TCGHolics staff can use these commands.")
        return False

    tree.interaction_check = check  # type: ignore[method-assign]

    @tree.error
    async def on_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        log.exception("command %s failed", interaction.command and interaction.command.qualified_name, exc_info=error)
        await _reply(interaction, f"Something went wrong: `{type(error).__name__}`. Check the node logs.")
