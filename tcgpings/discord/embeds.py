from __future__ import annotations

from datetime import datetime, timezone

import discord

from tcgpings.classify import FRANCHISE_NAMES
from tcgpings.models import Event, EventType, Level, Stock, format_price

TITLES = {
    EventType.NEW_PRODUCT: "🆕 New listing",
    EventType.RESTOCK: "✅ Restock",
    EventType.OUT_OF_STOCK: "❌ Out of stock",
    EventType.QTY_CHANGE: "📦 Stock change",
    EventType.PRICE_CHANGE: "💲 Price change",
}

COLORS = {
    EventType.NEW_PRODUCT: 0x3B82F6,
    EventType.RESTOCK: 0x22C55E,
    EventType.OUT_OF_STOCK: 0xEF4444,
    EventType.QTY_CHANGE: 0xF59E0B,
    EventType.PRICE_CHANGE: 0xA855F7,
}


def _stock(level: str | None, qty: int | None) -> str:
    if level is None:
        return "—"
    return Stock(Level(level), qty).describe()


def build_embed(event: Event) -> discord.Embed:
    retailer = event.extra.get("retailer_name") or event.retailer_id
    where = event.store_name or "Online"
    embed = discord.Embed(
        title=event.title[:256],
        url=event.url,
        color=COLORS[event.type],
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_author(name=f"{TITLES[event.type]} · {retailer} · {where}")
    if event.image:
        embed.set_thumbnail(url=event.image)

    if event.type is EventType.NEW_PRODUCT:
        embed.add_field(name="Stock", value=_stock(event.new_level, event.new_qty))
    else:
        old, new = _stock(event.old_level, event.old_qty), _stock(event.new_level, event.new_qty)
        embed.add_field(name="Stock", value=new if old == new else f"{old} → **{new}**")

    if event.type is EventType.PRICE_CHANGE:
        embed.add_field(name="Price", value=f"{format_price(event.old_price)} → **{format_price(event.new_price)}**")
    elif event.new_price is not None:
        embed.add_field(name="Price", value=format_price(event.new_price))

    embed.add_field(name="Store", value=where)
    if event.franchise:
        embed.add_field(name="Game", value=FRANCHISE_NAMES.get(event.franchise, event.franchise))
    embed.add_field(name="Links", value=f"[Product]({event.url})", inline=False)
    embed.set_footer(text=f"TCGHolics Pings · {event.sku}")
    return embed


def sample_event(retailer_id: str = "test", store_name: str | None = "Westgate") -> Event:
    return Event(
        type=EventType.RESTOCK,
        retailer_id=retailer_id,
        sku="test-sku",
        title="Pokémon TCG: 30th Celebration Booster Bundle (test alert)",
        url="https://tcgholics.co.nz",
        store_id="test",
        store_name=store_name,
        franchise="pokemon",
        old_level="out",
        new_level="in",
        new_qty=12,
        new_price=4999,
        extra={"retailer_name": "Test Retailer"},
    )
