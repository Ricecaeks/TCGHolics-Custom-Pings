"""Fetch chain (browser -> ScrapFly -> Zyte): fallback, circuit breakers, spend cap, and the two unblocker clients."""

import base64
from datetime import datetime, time
from zoneinfo import ZoneInfo

import pytest

from tcgpings.cluster.worker import daily_check_due
from tcgpings.net.chain import BrowserBackend, Cooldowns, FetchChain, MemoryChainStore
from tcgpings.net.http import Blocked, FetchError, NetPolicy
from tcgpings.net.unblock import ProviderError, ScrapFlyBackend, ZyteBackend

POLICY = NetPolicy("farmers", requests_per_minute=6000)
URL = "https://www.farmers.co.nz/stock?SKU=1"
PAGE = "<div>" + "real page " * 3000 + "</div>"


class Route:
    def __init__(self, name, answers, paid=True, cost=0.01):
        self.name, self.paid, self.cost = name, paid, cost
        self.answers = list(answers)
        self.calls = 0

    async def fetch(self, policy, origin, url, headers):
        self.calls += 1
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(answer, Exception):
            raise answer
        return answer, self.cost


def chain(*routes, budget=1.0):
    return FetchChain(list(routes), MemoryChainStore(), budget_usd=budget, cooldowns=Cooldowns(86400, 3600))


async def test_browser_answers_for_free():
    browser, scrapfly = Route("browser", [PAGE], paid=False, cost=0), Route("scrapfly", [PAGE])
    c = chain(browser, scrapfly)
    assert await c.fetch_text(POLICY, "https://www.farmers.co.nz/", URL) == PAGE
    assert scrapfly.calls == 0 and await c.store.month_spend() == 0


async def test_blocked_browser_rests_and_unblocker_takes_over():
    browser = Route("browser", [Blocked("WAF_Deny_Page")], paid=False, cost=0)
    scrapfly = Route("scrapfly", [PAGE])
    c = chain(browser, scrapfly)
    assert await c.fetch_text(POLICY, "o", URL) == PAGE
    assert await c.store.is_open("farmers", "browser")
    assert await c.fetch_text(POLICY, "o", URL) == PAGE
    assert browser.calls == 1, "a resting route isn't tried again"
    assert await c.store.month_spend() == pytest.approx(0.02)


async def test_route_heals_after_its_rest():
    browser = Route("browser", [Blocked("denied"), PAGE], paid=False, cost=0)
    zyte = Route("zyte", [PAGE])
    c = chain(browser, zyte)
    await c.fetch_text(POLICY, "o", URL)
    c.store.open_until[("farmers", "browser")] = 0  # the 24 h rest is over
    await c.fetch_text(POLICY, "o", URL)
    assert browser.calls == 2 and zyte.calls == 1
    assert not await c.store.is_open("farmers", "browser")


async def test_retailer_404_is_an_answer_not_a_failure():
    browser = Route("browser", [FetchError("GET x: HTTP 404", 404)], paid=False)
    scrapfly = Route("scrapfly", [PAGE])
    with pytest.raises(FetchError, match="404"):
        await chain(browser, scrapfly).fetch_text(POLICY, "o", URL)
    assert scrapfly.calls == 0


async def test_network_errors_open_the_breaker_after_three():
    flaky = Route("scrapfly", [FetchError("timeout")])
    zyte = Route("zyte", [PAGE])
    c = chain(flaky, zyte)
    for _ in range(3):
        await c.fetch_text(POLICY, "o", URL)
    assert await c.store.is_open("farmers", "scrapfly")
    await c.fetch_text(POLICY, "o", URL)
    assert flaky.calls == 3 and zyte.calls == 4


async def test_provider_problem_rests_for_its_own_cooldown():
    broke = Route("scrapfly", [ProviderError("scrapfly: HTTP 402", cooldown=24 * 3600)])
    c = chain(broke, Route("zyte", [PAGE]))
    await c.fetch_text(POLICY, "o", URL)
    import time as _time

    assert c.store.open_until[("farmers", "scrapfly")] > _time.time() + 23 * 3600


async def test_monthly_budget_stops_paid_routes_but_not_the_browser():
    browser = Route("browser", [Blocked("denied")], paid=False, cost=0)
    scrapfly = Route("scrapfly", [PAGE], cost=0.6)
    c = chain(browser, scrapfly, budget=1.0)
    await c.fetch_text(POLICY, "o", URL)
    await c.fetch_text(POLICY, "o", URL)  # $1.20 spent now
    with pytest.raises(Blocked, match="over monthly budget"):
        await c.fetch_text(POLICY, "o", URL)
    assert scrapfly.calls == 2


async def test_budget_ratio():
    c = chain(Route("scrapfly", [PAGE], cost=0.5), budget=1.0)
    assert not await c.budget_low()
    await c.fetch_text(POLICY, "o", URL)
    assert not await c.budget_low()  # 50%
    await c.store.spend("farmers", "scrapfly", 0.3)
    assert await c.budget_low()  # 80%


async def test_unconfigured_routes_are_skipped():
    c = chain(Route("browser", [PAGE], paid=False))
    assert c.available(["browser", "scrapfly", "zyte"]) == ["browser"]
    with pytest.raises(FetchError, match="no fetch route"):
        await c.fetch_text(POLICY, "o", URL, order=["zyte"])


async def test_browser_crash_is_a_route_failure_and_the_next_route_answers():
    class CrashingFetcher:
        async def fetch_text(self, policy, origin, url, headers):
            raise RuntimeError("Target page, context or browser has been closed")

    zyte = Route("zyte", [PAGE])
    c = chain(BrowserBackend(CrashingFetcher()), zyte)
    assert await c.fetch_text(POLICY, "o", URL) == PAGE
    assert c.store.failures[("farmers", "browser")] == 1


# --- the unblocker clients, against fake HTTP sessions ------------------------------------


class FakeResponse:
    def __init__(self, status, text="", headers=None, data=None):
        self.status_code, self.text, self.headers, self._data = status, text, headers or {}, data

    def json(self):
        if self._data is None:
            raise ValueError("not json")
        return self._data


class FakeSession:
    def __init__(self, resp):
        self.resp, self.calls = resp, []

    async def get(self, url, params=None):
        self.calls.append((url, params))
        return self.resp

    async def post(self, url, json=None, auth=None, **kw):
        self.calls.append((url, json, auth, kw) if kw else (url, json, auth))
        return self.resp


async def test_scrapfly_request_and_cost():
    session = FakeSession(FakeResponse(200, PAGE, {"x-scrapfly-api-cost": "30"}))
    b = ScrapFlyBackend("scp-test", "nz", 0.00015, node_name="pc", session=session)
    text, cost = await b.fetch(POLICY, "o", URL, {"X-Requested-With": "XMLHttpRequest"})
    assert text == PAGE and cost == pytest.approx(0.0045)
    _, params = session.calls[0]
    assert params["url"] == URL and params["unblocker"] == "true" and params["country"] == "nz"
    assert params["proxified_response"] == "true" and params["session"] == "tcgpings-pc-farmers"
    assert params["headers[X-Requested-With]"] == "XMLHttpRequest" and "cost_budget" not in params


@pytest.mark.parametrize("status, error", [(422, Blocked), (402, ProviderError), (429, ProviderError)])
async def test_scrapfly_rejections(status, error):
    resp = FakeResponse(status, "{}", {"x-scrapfly-reject-code": "ERR::ASP::SHIELD_PROTECTION_FAILED"})
    with pytest.raises(error):
        await ScrapFlyBackend("k", session=FakeSession(resp)).fetch(POLICY, "o", URL, None)


async def test_scrapfly_passes_through_the_retailers_answer():
    b = ScrapFlyBackend("k", session=FakeSession(FakeResponse(404, "not found")))
    with pytest.raises(FetchError) as exc:
        await b.fetch(POLICY, "o", URL, None)
    assert exc.value.status == 404
    denied = ScrapFlyBackend("k", session=FakeSession(FakeResponse(200, "<html>WAF_Deny_Page</html>")))
    with pytest.raises(Blocked):
        await denied.fetch(POLICY, "o", URL, None)


async def test_zyte_request_and_decoding():
    body = base64.b64encode(PAGE.encode()).decode()
    session = FakeSession(FakeResponse(200, data={"statusCode": 200, "httpResponseBody": body}))
    b = ZyteBackend("zk", "nz", 0.00127, session=session)
    text, cost = await b.fetch(POLICY, "o", URL, {"Accept": "text/html"})
    assert text == PAGE and cost == pytest.approx(0.00127)
    url, sent, auth = session.calls[0]
    assert url == "https://api.zyte.com/v1/extract" and auth == ("zk", "")
    assert sent == {"url": URL, "httpResponseBody": True, "geolocation": "NZ",
                    "customHttpRequestHeaders": [{"name": "Accept", "value": "text/html"}]}


@pytest.mark.parametrize("status, error", [(520, Blocked), (401, ProviderError), (503, ProviderError)])
async def test_zyte_errors(status, error):
    resp = FakeResponse(status, data={"type": "/download/temporary-error"})
    with pytest.raises(error):
        await ZyteBackend("k", session=FakeSession(resp)).fetch(POLICY, "o", URL, None)


async def test_zyte_reports_the_retailers_status():
    body = base64.b64encode(b"gone").decode()
    b = ZyteBackend("k", session=FakeSession(FakeResponse(200, data={"statusCode": 404, "httpResponseBody": body})))
    with pytest.raises(FetchError) as exc:
        await b.fetch(POLICY, "o", URL, None)
    assert exc.value.status == 404


# --- once-a-day store checks ---------------------------------------------------------------

NZ = ZoneInfo("Pacific/Auckland")
AT = time(8, 30)


def test_daily_check_runs_once_after_the_morning_refresh():
    sku = "7044417"
    noon = datetime(2026, 10, 30, 12, 0, tzinfo=NZ)
    assert daily_check_due(None, noon, AT, sku), "never checked: check now"
    assert not daily_check_due(1800, noon, AT, sku), "checked at 11:30 today"
    assert daily_check_due(6 * 3600, noon, AT, sku), "last checked 6am, before today's refresh"
    early = datetime(2026, 10, 30, 7, 0, tzinfo=NZ)
    assert not daily_check_due(12 * 3600, early, AT, sku), "checked yesterday afternoon; today's refresh hasn't happened"
    assert daily_check_due(30 * 3600, early, AT, sku), "missed yesterday's slot entirely"


def test_daily_checks_spread_over_the_hour():
    from tcgpings.cluster.worker import DAILY_SPREAD_SECONDS

    at_830 = datetime(2026, 10, 30, 8, 30, tzinfo=NZ)
    due = [daily_check_due(3600, at_830.replace(minute=59), AT, str(sku)) for sku in range(7000000, 7000200)]
    assert 0 < sum(due) < len(due), "some products are due by 8:59, the rest later in the hour"
    assert DAILY_SPREAD_SECONDS == 3600


class PostRoute(Route):
    posts = True

    async def fetch(self, policy, origin, url, headers, body=None):
        self.body = body
        return await super().fetch(policy, origin, url, headers)


async def test_a_post_skips_the_browser_and_sends_the_body():
    browser, scrapfly = Route("browser", [PAGE], paid=False, cost=0), PostRoute("scrapfly", ['{"data": 1}'])
    assert await chain(browser, scrapfly).fetch_text(POLICY, "o", URL, body='{"q": 1}') == '{"data": 1}'
    assert browser.calls == 0 and scrapfly.body == '{"q": 1}'
    with pytest.raises(Blocked, match=r"^POST .*\(browser can't POST\)"):
        await chain(browser).fetch_text(POLICY, "o", URL, body="{}")


async def test_scrapfly_forwards_a_post_body():
    session = FakeSession(FakeResponse(200, '{"data": {}}', {"x-scrapfly-api-cost": "30"}))
    b = ScrapFlyBackend("k", session=session)
    text, _ = await b.fetch(POLICY, "o", URL, {"Content-Type": "application/json"}, body='{"q": 1}')
    url, _, _, kw = session.calls[0]
    assert text == '{"data": {}}' and kw["data"] == '{"q": 1}'
    assert kw["headers"] == {"Content-Type": "application/json"} and kw["params"]["url"] == URL
    assert kw["params"]["headers[Content-Type]"] == "application/json"


async def test_zyte_sends_a_post_body():
    body = base64.b64encode(b'{"data": {}}').decode()
    session = FakeSession(FakeResponse(200, data={"statusCode": 200, "httpResponseBody": body}))
    text, _ = await ZyteBackend("k", session=session).fetch(POLICY, "o", URL, None, body='{"q": 1}')
    _, request, _ = session.calls[0]
    assert text == '{"data": {}}'
    assert request["httpRequestMethod"] == "POST" and request["httpRequestText"] == '{"q": 1}'


async def test_scrapfly_uses_a_retailers_own_project_key():
    session = FakeSession(FakeResponse(200, PAGE))
    b = ScrapFlyBackend("shared", session=session, project_keys={"kmart": "kmart-project"})
    await b.fetch(NetPolicy("kmart", requests_per_minute=60), "o", URL, None)
    await b.fetch(POLICY, "o", URL, None)  # farmers has no project key of its own
    assert [params["key"] for _, params in session.calls] == ["kmart-project", "shared"]


async def test_a_route_past_its_own_cap_rests_while_the_others_carry_on():
    zyte, scrapfly = Route("zyte", [PAGE], cost=0.6), Route("scrapfly", [PAGE], cost=0.01)
    c = FetchChain([zyte, scrapfly], MemoryChainStore(), budget_usd=10.0, backend_budgets={"zyte": 1.0})
    await c.fetch_text(POLICY, "o", URL)
    await c.fetch_text(POLICY, "o", URL)  # Zyte has spent $1.20 of its $1.00 now
    await c.fetch_text(POLICY, "o", URL)
    assert (zyte.calls, scrapfly.calls) == (2, 1)


def test_daily_check_spread_is_per_adapter():
    from datetime import datetime, time, timedelta, timezone
    import zlib

    sku = next(s for s in (f"sku{i}" for i in range(100)) if zlib.crc32(s.encode()) % 14400 > 7200)
    at = time(8, 30)
    day = datetime(2026, 11, 6, tzinfo=timezone.utc)
    ten = day.replace(hour=10)  # 1.5 h after 8:30, before this SKU's slot in a 4-hour spread
    yesterday = 19 * 3600  # last checked yesterday at 15:00, after yesterday's slot either way
    assert daily_check_due(yesterday, ten, at, sku), "1-hour spread: its slot has passed"
    assert not daily_check_due(yesterday, ten, at, sku, spread=4 * 3600), "4-hour spread: still to come"
    assert daily_check_due(yesterday, ten + timedelta(hours=3), at, sku, spread=4 * 3600)


def test_price_refresh_is_weekly_per_product():
    from datetime import datetime, timedelta

    from tcgpings.cluster.worker import price_refresh_due

    monday = datetime(2026, 11, 2)
    days = [d for d in range(7) if price_refresh_due("7044417", monday + timedelta(days=d))]
    assert len(days) == 1


async def test_within_budget():
    store = MemoryChainStore()
    chain = FetchChain([PaidOk("scrapfly"), PaidOk("zyte"), BrowserBackend(None)], store, budget_usd=10.0,
                       backend_budgets={"scrapfly": 3.0})
    policy = NetPolicy("farmers", spend_limit_usd=5.0)
    assert await chain.within_budget("scrapfly", policy)
    assert not await chain.within_budget("browser") and not await chain.within_budget("nope")
    await store.spend("kmart", "scrapfly", 3.0)
    assert not await chain.within_budget("scrapfly")  # its own cap
    assert await chain.within_budget("zyte", policy)
    await store.spend("farmers", "zyte", 5.0)
    assert not await chain.within_budget("zyte", policy)  # the retailer's own limit
    assert await chain.within_budget("zyte")
    await store.spend("kmart", "zyte", 2.0)
    assert not await chain.within_budget("zyte")  # the month's total


class PaidOk:
    paid = True
    posts = True

    def __init__(self, name):
        self.name = name

    async def fetch(self, policy, origin, url, headers):
        return "ok", 0.0
