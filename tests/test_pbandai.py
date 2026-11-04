"""Premium Bandai NZ: search API parsing (fixtures trimmed from the NZ "Card Games" category and the bulk endpoint
on 2026-11-05), stock and pre-order notes, paging, watches and the sealed filter."""

import copy

import pytest
from conftest import load_fixture

import tcgpings.retailers  # noqa: F401  (registers adapters)
from tcgpings.classify import is_sealed_product, is_single_card
from tcgpings.models import Level
from tcgpings.net.http import FetchError
from tcgpings.retailers.base import REGISTRY
from tcgpings.retailers.pbandai import (
    PBandaiAdapter,
    level_of,
    note_of,
    parse_row,
    parse_search,
)


def row():
    rid, name, config, color = PBandaiAdapter.default_retailers[0]
    return {"id": rid, "adapter": "pbandai", "name": name, "config": config, "requests_per_minute": 10,
            "proxy_policy": "direct", "color": color}


class Http:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    async def get_json(self, policy, url, params=None, headers=None):
        self.calls.append((url, dict(params or {}), dict(headers or {})))
        answer = self.responses(url, params) if callable(self.responses) else self.responses
        if isinstance(answer, Exception):
            raise answer
        return copy.deepcopy(answer)


def cards():
    return load_fixture("pbandai", "nz-card-games.json")


def first_row(**changes):
    data = cards()["productResults"]["products"][0]
    data.update(changes)
    return data


def test_registered_with_one_nz_row_on_plain_requests():
    assert REGISTRY["pbandai"] is PBandaiAdapter
    [(rid, name, config, _)] = PBandaiAdapter.default_retailers
    assert (rid, name) == ("pbandai-nz", "P-Bandai NZ")
    assert config == {"area": "nz", "category": "04-011"}  # no unblocker: the JSON API answers plain requests
    assert PBandaiAdapter.supports_discovery and not PBandaiAdapter.supports_search


def test_card_games_category():
    products, total = parse_search(cards(), "pbandai-nz")
    assert total == 39
    assert len(products) == 8
    p = products[0]
    assert p.sku == "N2898133002"
    assert p.title == "GUNDAM CARD GAME Premium Goods Set After War Gundam X [PB04]"
    assert p.url == "https://p-bandai.com/nz/item/N2898133002"
    assert p.image == "https://p-bandai.com/files/seller-products/NSP0461458001/FCUVcLVjRjJird2y64kt.jpg"
    assert p.price_cents == 16100
    # Its pre-order window is open (saleStatus On) but the allocation has sold out.
    assert p.online.level is Level.OUT
    assert p.note == "Pre-order"
    assert products[1].note == "Lottery (chance to buy)"
    assert all(q.online.level is Level.OUT for q in products)  # everything in the fixture is closed or sold out


def test_an_open_pre_order_is_in_stock_until_it_sells_out_or_closes():
    open_now = first_row(saleStatus="On", flags=["PRE_ORDER"])
    assert level_of(open_now) is Level.IN
    # saleEndExpectedDt 2026-11-09T14:59:59.999Z is 3:59 am on 10 Nov in NZ.
    assert note_of(open_now) == "Pre-order · closes 10 Nov"
    assert level_of(first_row(saleStatus="On", flags=["OUT_OF_STOCK"])) is Level.OUT
    assert level_of(first_row(saleStatus="End", flags=["PRE_ORDER_CLOSED"])) is Level.OUT
    assert level_of(first_row(saleStatus="On", displayStatus="Off", flags=["PRE_ORDER"])) is Level.OUT
    assert level_of(first_row(saleStatus="Mystery", flags=[])) is Level.UNKNOWN


def test_a_coming_pre_order_says_when_it_opens():
    waiting = first_row(saleStatus="Waiting", flags=["PRE_ORDER"])
    assert level_of(waiting) is Level.OUT
    assert note_of(waiting) == "Pre-order · opens 26 Oct, 3:00 pm"  # 02:00 UTC = 3 pm NZDT


def test_rows_without_a_code_or_name_are_skipped():
    assert parse_row(first_row(productCode=None), "pbandai-nz") is None
    assert parse_row(first_row(productName={"zh-HK": "x"}), "pbandai-nz") is None


def test_sealed_filter_keeps_sets_and_drops_playmats_and_untracked_games():
    sealed = [p.title for p in parse_search(cards(), "pbandai-nz")[0] if is_sealed_product(p.title)]
    assert "GUNDAM CARD GAME 1st Anniversary Set [April 2027 Delivery]" in sealed
    assert "ONE PIECE CARD GAME Premium Card Collection -Ace & Sabo & Luffy-" in sealed
    assert any(t.startswith("DRAGON BALL SUPER CARD GAME MASTERS") for t in sealed)
    assert not any("Playmat" in t for t in sealed)
    assert not any(t.startswith("DIGIMON") for t in sealed)  # not a game the bot tracks
    assert len(sealed) == 6


def test_a_delivery_note_in_brackets_is_not_a_single_card():
    assert not is_single_card("GUNDAM CARD GAME 1st Anniversary Set [April 2027 Delivery]")
    assert is_single_card("Stingcaster Mage [Reality Fracture]")


async def test_discover_reads_the_card_games_category_with_the_nz_header():
    http = Http(cards())
    products = await PBandaiAdapter(row(), http).discover()
    assert len(products) == 8
    [(url, params, headers)] = http.calls
    assert url == "https://p-bandai.com/api/search"
    assert params == {"_f_categories": "04-011", "sortType": "NewArrival", "limit": 100, "offset": 0}
    assert headers["X-G1-Area-Code"] == "nz"
    assert headers["Referer"] == "https://p-bandai.com/nz/"


async def test_discover_pages_a_bigger_category():
    def respond(url, params):
        data = cards()
        data["productResults"]["totalCount"] = 150
        for p in data["productResults"]["products"]:
            p["productCode"] += f"-{params['offset']}"
        return data

    http = Http(respond)
    products = await PBandaiAdapter(row(), http).discover()
    assert [c[1]["offset"] for c in http.calls] == [0, 100]
    assert len(products) == 16


async def test_an_unexpected_response_fails_the_run():
    with pytest.raises(FetchError):
        await PBandaiAdapter(row(), Http({"error": "nope"})).discover()


async def test_fetch_products_reads_the_bulk_endpoint():
    http = Http(load_fixture("pbandai", "nz-bulk.json"))
    products = await PBandaiAdapter(row(), http).fetch_products(["N2898133002", "N2542162006"])
    assert [p.sku for p in products] == ["N2898133002", "N2542162006"]
    [(url, params, _)] = http.calls
    assert url == "https://p-bandai.com/api/search/bulk"
    assert params == {"productCodes": "N2898133002,N2542162006", "limit": 2}


async def test_fetch_products_chunks_long_lists():
    http = Http([])
    await PBandaiAdapter(row(), http).fetch_products([f"N{i}" for i in range(120)])
    assert [c[1]["limit"] for c in http.calls] == [50, 50, 20]


def test_refs_and_urls():
    a = PBandaiAdapter(row(), Http([]))
    assert a.parse_ref("https://p-bandai.com/nz/item/N2898133002?redirect=no") == "N2898133002"
    assert a.parse_ref("N2898133002") == "N2898133002"
    assert a.matches_url("https://p-bandai.com/nz/item/N2898133002")
    assert not a.matches_url("https://p-bandai.com/au/item/N2898133002")
