"""Finds upcoming TCG releases in public news feeds, for staff to approve as hot sets.

Publishers' own sites aren't read: pokemon.com answers automated requests with a bot wall. Google
News carries those publishers' announcements alongside other coverage, and PokéBeach often has
reveals first. Every feed is plain RSS, so a headline is all the bot ever needs from them.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from urllib.parse import quote


def _google_news(query: str) -> str:
    return f"https://news.google.com/rss/search?q={quote(query + ' when:14d')}&hl=en-NZ&gl=NZ&ceid=NZ:en"


FEEDS = {
    "PokéBeach": "https://www.pokebeach.com/forums/forums/-/index.rss",
    "Pokémon news": _google_news('"Pokémon TCG" expansion OR collection OR preorder'),
    "Magic news": _google_news('"Magic: The Gathering" new set OR "play booster" OR preorder'),
    "Lorcana news": _google_news('"Disney Lorcana" new set OR expansion OR "booster"'),
    "One Piece news": _google_news('"One Piece Card Game" new set OR booster OR "starter deck"'),
    "Yu-Gi-Oh! news": _google_news('"Yu-Gi-Oh" TCG new set OR "booster" OR "structure deck"'),
    "Riftbound news": _google_news("Riftbound new set OR expansion OR booster"),
}

_ITEM = re.compile(r"<item\b.*?</item>", re.S)
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.S)
_LINK = re.compile(r"<link[^>]*>(.*?)</link>", re.S)
_RELEASE = re.compile(
    r"expansion|\bset\b|booster|elite trainer|\bcollection\b|starter deck|structure deck|battle deck|\bbox\b|"
    r"\btin\b|bundle|pre-?orders?|revealed|announced",
    re.I,
)
_NOT_A_RELEASE = re.compile(
    r"\bpocket\b|tcg live|video game|\bprices?\b|deals?\b|% off|cheapest|review|ranked|ranking|best\b|guide|how to|"
    r"pull rates?|thread|speculative|trademark|in order of|tournament results?|winners?|lawsuit|scalp|faq|decklists?|"
    r"opening|worth|top \d+|\bwhere to\b|auction|attic|\bsold\b|figure|down to|\bsales?\b|mcdonald|played|impressions|"
    r"deck tech|drawing|help with",
    re.I,
)
_QUOTED = re.compile(r"[“\"‘]([^”\"’]{3,50})[”\"’]")
_AFTER_SERIES = re.compile(r"(?:mega evolution|scarlet (?:&|and) violet)\s*[—–:-]+\s*([^—–:-]+)", re.I)
_GAME_PREFIX = re.compile(
    r"^(?:the\s+|new\s+)*(?:pok[eé]mon(?:\s+(?:tcg|trading card game))?|magic(?:: the gathering)?|disney lorcana|lorcana|"
    r"one piece(?: card game)?|yu-gi-oh!?(?: (?:tcg|trading card game))?|riftbound)\s*[:–—-]*\s*",
    re.I,
)
_TAIL = re.compile(
    r"\s+(?:expansion|set|product|preorders?|pre-orders?|revealed|announced|arrives|coming|drops?|are|is|now|for|on|"
    r"officially|starring|features?|info|showcase)\b.*$",
    re.I,
)


@dataclass(frozen=True)
class Headline:
    source: str
    title: str
    url: str


def parse_feed(text: str, source: str) -> list[Headline]:
    """RSS items that read like a card product release, once per title."""
    found: dict[str, Headline] = {}
    for item in _ITEM.findall(text):
        title = _text(_TITLE.search(item))
        title = re.sub(r"\s+-\s+[^-]{2,40}$", "", title)  # Google News appends " - Publisher"
        if title.islower() or not 12 <= len(title) <= 160 or not _RELEASE.search(title) or _NOT_A_RELEASE.search(title):
            continue
        found.setdefault(title.lower(), Headline(source, title, _text(_LINK.search(item))))
    return list(found.values())


def _text(match: re.Match | None) -> str:
    raw = match.group(1) if match else ""
    return " ".join(html.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", raw)).split())


def suggest_keyword(title: str) -> str:
    """A first guess at the keyword for a release. Staff can change it when approving."""
    guess = _QUOTED.search(title) or _AFTER_SERIES.search(title)
    keyword = guess.group(1) if guess else _GAME_PREFIX.sub("", title)
    keyword = _TAIL.sub("", keyword)
    return " ".join(re.sub(r"[^\w\s&'-]", " ", keyword).split()).lower()[:60]
