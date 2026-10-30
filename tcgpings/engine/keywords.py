"""Zephyr-style keyword filters, set per Discord route.

Syntax (case- and accent-insensitive):
    30th booster bundle, elite trainer box, ultra premium collection, -sleeves, -portfolio

- Commas (or new lines) separate alternatives: a title matching ANY of them passes.
- Words inside one alternative must ALL appear (any order), e.g. "30th booster bundle".
- A word or phrase starting with "-" excludes, e.g. "-sleeves", "-code card". Excludes win.
- Words match at the start of a word: "30th" matches "30th"; "bundle" matches "bundles".
- Common shorthands work both ways: etb, upc, bb, spc, pc, ex (see ALIASES).
- An empty filter (or only excludes) lets everything through except the excludes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

# Shorthand -> what it stands for. Titles containing the long form also match the shorthand.
ALIASES = {
    "etb": "elite trainer box",
    "upc": "ultra premium collection",
    "spc": "super premium collection",
    "bb": "booster bundle",
    "pkm": "pokemon",
    "ptcg": "pokemon",
    "mtg": "magic the gathering",
    "op": "one piece",
    "ygo": "yu gi oh",
}

_SEPARATORS = re.compile(r"[,\n;]+")
_NON_WORD = re.compile(r"[^a-z0-9]+")


def normalise(text: str) -> str:
    text = text.lower().replace("é", "e").replace("&", " and ").replace("'", "")
    return " " + _NON_WORD.sub(" ", text).strip() + " "


def _expand(title_norm: str) -> str:
    """Add shorthands for long forms present in the title (and long forms for shorthands)."""
    extra = []
    for short, long in ALIASES.items():
        if f" {long} " in title_norm:
            extra.append(short)
        elif f" {short} " in title_norm:
            extra.append(long)
    return title_norm + " ".join(extra) + " " if extra else title_norm


def _has(haystack: str, phrase: str) -> bool:
    """Phrase words appear consecutively, each matching from the start of a word."""
    words = phrase.split()
    if len(words) == 1:
        return f" {words[0]}" in haystack
    return re.search(r"\s" + r"\w*\s+".join(re.escape(w) for w in words), haystack) is not None


@dataclass(frozen=True)
class KeywordFilter:
    groups: tuple[tuple[str, ...], ...] = ()   # OR of (AND of words)
    excludes: tuple[str, ...] = ()             # phrases

    @classmethod
    def parse(cls, text: str | None) -> KeywordFilter:
        return _parse(text or "")

    @property
    def empty(self) -> bool:
        return not self.groups and not self.excludes

    def matches(self, title: str) -> bool:
        haystack = _expand(normalise(title))
        if any(_has(haystack, ex) for ex in self.excludes):
            return False
        if not self.groups:
            return True
        return any(all(f" {word}" in haystack for word in group) for group in self.groups)

    def describe(self) -> str:
        parts = [" + ".join(g) for g in self.groups] or ["everything"]
        text = " OR ".join(parts)
        if self.excludes:
            text += " — excluding " + ", ".join(self.excludes)
        return text


@lru_cache(maxsize=1024)
def _parse(text: str) -> KeywordFilter:
    groups: list[tuple[str, ...]] = []
    excludes: list[str] = []
    for raw in _SEPARATORS.split(text):
        raw = raw.strip()
        if not raw:
            continue
        if raw.startswith("-"):
            phrase = normalise(raw[1:]).strip()
            if phrase:
                excludes.append(phrase)
            continue
        words = []
        for token in raw.split():
            if token.startswith("-") and len(token) > 1:
                excludes.append(normalise(token[1:]).strip())
            else:
                words.extend(normalise(token.lstrip("+")).split())
        if words:
            groups.append(tuple(words))
    return KeywordFilter(tuple(groups), tuple(excludes))
