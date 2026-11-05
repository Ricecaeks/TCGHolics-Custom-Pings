"""Paid unblocker spend per store: billed failures, the store's own limit, the effective cap and /status."""

import base64

import pytest
from test_chain import PAGE, URL, FakeResponse, FakeSession, Route

from tcgpings.discord.commands import spend_lines
from tcgpings.net.chain import BrowserBackend, Cooldowns, FetchChain, MemoryChainStore
from tcgpings.net.http import Blocked, FetchError, NetPolicy, Queued
from tcgpings.net.unblock import ScrapFlyBackend, ZyteBackend

FARMERS = NetPolicy("farmers", requests_per_minute=6000)
PC_NZ = NetPolicy("pokemoncenter-nz", requests_per_minute=6000)


def billed(exc, usd):
    exc.cost_usd = usd
    return exc


def chain(*routes, budget=100.0, **kw):
    return FetchChain(list(routes), MemoryChainStore(), budget_usd=budget, cooldowns=Cooldowns(86400, 3600), **kw)


async def test_spend_is_kept_per_store_and_route():
    scrapfly = Route("scrapfly", [PAGE], cost=0.02)
    c = chain(scrapfly)
    await c.fetch_text(FARMERS, "o", URL)
    await c.fetch_text(FARMERS, "o", URL)
    await c.fetch_text(PC_NZ, "o", URL)
    assert c.store.spent == {("farmers", "scrapfly"): pytest.approx(0.04), ("pokemoncenter-nz", "scrapfly"): 0.02}
    assert await c.store.retailer_spend("farmers") == pytest.approx(0.04)
    assert await c.store.month_spend() == pytest.approx(0.06)


@pytest.mark.parametrize("error", [
    Blocked("HTTP 403 (blocked)"),
    FetchError("scrapfly: HTTP 500 ERR::SCRAPE::BAD_UPSTREAM_RESPONSE"),
])
async def test_a_failure_the_provider_billed_is_counted(error):
    scrapfly, zyte = Route("scrapfly", [billed(error, 0.005)]), Route("zyte", [PAGE], cost=0.00127)
    c = chain(scrapfly, zyte)
    assert await c.fetch_text(FARMERS, "o", URL) == PAGE
    assert c.store.spent[("farmers", "scrapfly")] == 0.005
    assert c.store.failed == {("farmers", "scrapfly"): 1}
    assert await c.store.month_spend() == pytest.approx(0.00627)


async def test_a_billed_retailer_answer_is_counted_before_it_is_raised():
    zyte = Route("zyte", [billed(FetchError("HTTP 404", 404), 0.00127)])
    c = chain(zyte)
    with pytest.raises(FetchError, match="404"):
        await c.fetch_text(FARMERS, "o", URL)
    assert c.store.failed == {("farmers", "zyte"): 1} and await c.store.month_spend() == 0.00127


async def test_a_free_failure_costs_nothing():
    c = chain(Route("scrapfly", [Blocked("ERR::ASP::SHIELD_PROTECTION_FAILED")]))
    with pytest.raises(Blocked):
        await c.fetch_text(FARMERS, "o", URL)
    assert c.store.spent == {} and c.store.failed == {}


async def test_a_store_past_its_own_limit_stops_using_paid_routes_but_others_carry_on():
    browser = Route("browser", [Blocked("denied")], paid=False, cost=0)
    scrapfly = Route("scrapfly", [PAGE], cost=0.6)
    c = chain(browser, scrapfly)
    limited = NetPolicy("farmers", requests_per_minute=6000, spend_limit_usd=1.0)
    await c.fetch_text(limited, "o", URL)
    await c.fetch_text(limited, "o", URL)  # farmers has spent $1.20 of its $1.00 now
    with pytest.raises(Blocked, match="farmers over its own monthly limit"):
        await c.fetch_text(limited, "o", URL)
    assert scrapfly.calls == 2
    assert await c.fetch_text(PC_NZ, "o", URL) == PAGE  # another store still gets through
    c.store.open_until.clear()
    browser.answers = [PAGE]
    assert await c.fetch_text(limited, "o", URL) == PAGE, "the free route still serves a capped store"


async def test_budget_runs_low_for_one_store_at_its_own_limit():
    c = chain(Route("scrapfly", [PAGE], cost=0.5), budget=100.0)
    limited = NetPolicy("farmers", requests_per_minute=6000, spend_limit_usd=1.0)
    await c.fetch_text(limited, "o", URL)
    assert not await c.budget_low(limited) and not await c.budget_low()
    await c.fetch_text(limited, "o", URL)
    assert await c.budget_low(limited), "100% of farmers' own $1"
    assert not await c.budget_low(), "1% of the $100 total"
    assert not await c.budget_low(PC_NZ)


def test_the_cap_is_the_total_or_the_paid_routes_own_caps_if_lower():
    browser = BrowserBackend(None)
    scrapfly, zyte = Route("scrapfly", [PAGE]), Route("zyte", [PAGE])
    assert chain(browser, scrapfly, zyte, backend_budgets={"scrapfly": 30.0, "zyte": 30.0}).cap_usd() == 60.0
    assert chain(browser, scrapfly, zyte, backend_budgets={"scrapfly": 80.0, "zyte": 30.0}).cap_usd() == 100.0
    assert chain(scrapfly, zyte, backend_budgets={"scrapfly": 30.0}).cap_usd() == 100.0, "zyte has no cap of its own"
    assert chain(scrapfly, budget=0, backend_budgets={"scrapfly": 30.0}).cap_usd() == 0, "no total budget = no cap"


async def test_budget_used_is_measured_against_the_effective_cap():
    c = chain(Route("scrapfly", [PAGE], cost=24.0), Route("zyte", [PAGE]),
              backend_budgets={"scrapfly": 30.0, "zyte": 30.0})
    await c.fetch_text(FARMERS, "o", URL)
    await c.fetch_text(FARMERS, "o", URL)
    assert await c.budget_used() == pytest.approx(0.8) and await c.budget_low()


# --- the two clients report what a failure cost -------------------------------------------------


async def test_scrapfly_failure_carries_its_billed_credits():
    resp = FakeResponse(200, "", {"x-scrapfly-reject-code": "ERR::SCRAPE::BAD_UPSTREAM_RESPONSE",
                                  "x-scrapfly-api-cost": "30"})
    with pytest.raises(FetchError) as caught:
        await ScrapFlyBackend("k", session=FakeSession(resp)).fetch(FARMERS, "o", URL, None)
    assert caught.value.cost_usd == pytest.approx(30 * 0.00015)


async def test_scrapfly_retailer_404_carries_its_billed_credits():
    resp = FakeResponse(404, "not found", {"x-scrapfly-api-cost": "25"})
    with pytest.raises(FetchError) as caught:
        await ScrapFlyBackend("k", session=FakeSession(resp)).fetch(FARMERS, "o", URL, None)
    assert caught.value.status == 404 and caught.value.cost_usd == pytest.approx(25 * 0.00015)


async def test_scrapfly_failure_without_a_cost_is_free():
    resp = FakeResponse(422, "{}", {"x-scrapfly-reject-code": "ERR::ASP::SHIELD_PROTECTION_FAILED"})
    with pytest.raises(Blocked) as caught:
        await ScrapFlyBackend("k", session=FakeSession(resp)).fetch(FARMERS, "o", URL, None)
    assert caught.value.cost_usd == 0


@pytest.mark.parametrize(("status", "body", "error"), [
    (404, "not found", FetchError),
    (403, "denied", Blocked),
    (200, "<h1>You are now in line</h1>", Queued),
])
async def test_zyte_bills_every_answer_it_brings_back(status, body, error):
    data = {"statusCode": status, "httpResponseBody": base64.b64encode(body.encode()).decode()}
    zyte = ZyteBackend("k", usd_per_request=0.002, session=FakeSession(FakeResponse(200, data=data)))
    with pytest.raises(error) as caught:
        await zyte.fetch(FARMERS, "o", URL, None, detect_queue=True)
    assert caught.value.cost_usd == 0.002


async def test_zyte_ban_is_free():
    zyte = ZyteBackend("k", session=FakeSession(FakeResponse(520, data={"type": "/download/temporary-error"})))
    with pytest.raises(Blocked) as caught:
        await zyte.fetch(FARMERS, "o", URL, None)
    assert caught.value.cost_usd == 0


async def test_billed_zyte_404_reaches_the_monthly_total_through_the_chain():
    data = {"statusCode": 404, "httpResponseBody": base64.b64encode(b"gone").decode()}
    zyte = ZyteBackend("k", usd_per_request=0.002, session=FakeSession(FakeResponse(200, data=data)))
    c = chain(zyte)
    with pytest.raises(FetchError, match="404"):
        await c.fetch_text(FARMERS, "o", URL)
    assert await c.store.retailer_spend("farmers") == 0.002


# --- /status ---------------------------------------------------------------------------------


def row(retailer_id, backend, requests, cost, failed=0):
    return {"retailer_id": retailer_id, "backend": backend, "requests": requests, "failed": failed, "cost_usd": cost}


def test_status_lists_each_stores_spend_against_the_cap():
    rows = [row("farmers", "scrapfly", 900, 8.0, failed=3), row("farmers", "zyte", 12, 0.2),
            row("pokemoncenter-nz", "scrapfly", 300, 4.5), row("", "scrapfly", 50, 0.3)]
    lines = spend_lines(rows, {"farmers": 10.0, "hobbylords": 5.0}, budget=100.0, cap=60.0)
    assert lines == [
        "**Unblocker spend** $13.00 / $100.00 cap this month (the routes' own caps stop it at $60.00)",
        "• 🟡 `farmers` $8.20 / $10.00 limit · scrapfly 900 req, zyte 12 req · 3 billed failures",
        "• `pokemoncenter-nz` $4.50 · scrapfly 300 req",
        "• earlier (no store recorded) $0.30 · scrapfly 50 req",
        "• `hobbylords` $0.00 / $5.00 limit",
    ]


def test_status_flags_a_store_at_its_limit_and_handles_no_spend():
    assert spend_lines([row("farmers", "scrapfly", 10, 5.0)], {"farmers": 5.0}, 100.0, 100.0)[1].startswith("• 🔴")
    assert spend_lines([], {}, 100.0, 100.0) == ["**Unblocker spend** $0.00 / $100.00 cap this month: nothing yet"]
    assert spend_lines([], {}, 0, 0) == ["**Unblocker spend** $0.00 this month (no cap): nothing yet"]


# --- staff alerts --------------------------------------------------------------------------------


async def test_staff_hear_when_a_store_hits_its_limit_and_the_cap_is_the_routes_own(pool, tmp_path):
    from test_cluster import make_ctx

    from tcgpings.cluster.leadership import fetch_chain_issues
    from tcgpings.db import queries
    from tcgpings.net.chain import DbChainStore

    ctx = make_ctx(pool, "nuc1", tmp_path)
    ctx.http.chain = FetchChain([Route("scrapfly", [PAGE]), Route("zyte", [PAGE])], DbChainStore(pool),
                                budget_usd=100.0, backend_budgets={"scrapfly": 30.0, "zyte": 30.0})
    for rid in ("farmers", "pokemoncenter-nz"):
        await queries.upsert_retailer(pool, rid, "shopify", rid, {"domain": "x"})
    await queries.set_retailer_config(pool, "farmers", "unblocker_monthly_usd", 10.0)
    await queries.add_spend(pool, "farmers", "scrapfly", 10.0)
    await queries.add_spend(pool, "pokemoncenter-nz", "zyte", 40.0)
    issues = await fetch_chain_issues(ctx)
    assert "$50.00 of $60.00" in issues["budget:low"]
    assert "**farmers** has used its own unblocker limit ($10.00 of $10.00)" in issues["budget:farmers"]
    assert "budget:pokemoncenter-nz" not in issues
