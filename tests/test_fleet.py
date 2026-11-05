"""The NUC fleet: worker lanes, the per-retailer in-flight cap, leader eligibility, rate-limit shares per
lane, per-node log and health files, and queue-lag tracking."""

import asyncio
import logging

import pytest
from test_cluster import make_ctx

from tcgpings.app import node_tasks
from tcgpings.cluster import lanes
from tcgpings.cluster.heartbeat import beat, limiter_shares
from tcgpings.cluster.leadership import QUEUE_LAG_WARN_SECONDS, collect_issues, queue_lag_issue
from tcgpings.cluster.worker import Worker
from tcgpings.config import Settings, safe_name
from tcgpings.db import queries
from tcgpings.discord.commands import queue_line
from tcgpings.logfile import file_handler, log_file_name
from tcgpings.net.ratelimit import DIRECT, RateLimiter
from tcgpings.retailers import REGISTRY


async def _retailer(pool, rid, adapter, jobs, config=None, ago=600):
    """A retailer with `jobs` due watch_sku jobs, the first `ago` seconds overdue and each later one a
    second less."""
    await queries.upsert_retailer(pool, rid, adapter, rid, config or {})
    for i in range(jobs):
        await pool.execute(
            "INSERT INTO jobs (key, kind, retailer_id, payload, interval_seconds, next_run_at)"
            " VALUES ($1, 'watch_sku', $2, '{}', 60, now() - make_interval(secs => $3))",
            f"sku:{rid}:{i}", rid, float(ago - i),
        )


def _by_retailer(jobs) -> dict[str, int]:
    out: dict[str, int] = {}
    for j in jobs:
        out[j["retailer_id"]] = out.get(j["retailer_id"], 0) + 1
    return out


# --- lanes -----------------------------------------------------------------------------


def test_every_adapter_has_a_lane():
    browser = {name for name in REGISTRY if lanes.adapter_lane(name) == lanes.BROWSER}
    assert browser >= {"farmers", "kmart", "mightyape", "pokemoncenter"}
    assert lanes.adapter_lane("warehouse") == lanes.BROWSER  # by name: its adapter starts Chrome
    for name in ("shopify", "jbhifi", "paperplus", "pbandai", "retrospace", "toyworld", "whitcoulls"):
        assert lanes.adapter_lane(name) == lanes.HTTP, name
    assert lanes.retailer_lane({"adapter": "shopify", "config": {"lane": "browser"}}) == lanes.BROWSER
    assert lanes.retailer_lane({"adapter": "farmers", "config": {"lane": "chrome"}}) == lanes.BROWSER, \
        "an unknown lane is ignored"


def test_parse_lanes():
    assert lanes.parse_lanes("http,browser") == ["http", "browser"]
    assert lanes.parse_lanes(" HTTP , http ") == ["http"]
    assert lanes.parse_lanes("") == [] and lanes.parse_lanes("none") == [] and lanes.parse_lanes(None) == []


def test_worker_lanes_setting(monkeypatch):
    monkeypatch.delenv("WORKER_LANES", raising=False)
    assert Settings(_env_file=None).lanes == ["http", "browser"]
    monkeypatch.setenv("WORKER_LANES", "browser")
    assert Settings(_env_file=None).lanes == ["browser"]
    monkeypatch.setenv("WORKER_LANES", "")  # compose's `WORKER_LANES: ""`: claims nothing, not the default
    assert Settings(_env_file=None).lanes == []
    assert Settings(_env_file=None, worker_lanes="http").lanes == ["http"]


async def test_claim_jobs_only_takes_the_nodes_lanes(pool):
    await _retailer(pool, "shop", "shopify", 2)
    await _retailer(pool, "farmers", "farmers", 2)
    await _retailer(pool, "slow-shop", "shopify", 2, config={"lane": "browser"})

    assert await queries.claim_jobs(pool, "control", 50, 60, worker_lanes=[]) == []
    http = await queries.claim_jobs(pool, "nuc-http", 50, 60, worker_lanes=["http"])
    assert _by_retailer(http) == {"shop": 2}
    browser = await queries.claim_jobs(pool, "nuc-browser", 50, 60, worker_lanes=["browser"])
    assert _by_retailer(browser) == {"farmers": 2, "slow-shop": 2}

    # The SQL lane agrees with lanes.retailer_lane for every row.
    for r in await queries.list_retailers(pool):
        claimed = {j["retailer_id"] for j in (http if lanes.retailer_lane(r) == lanes.HTTP else browser)}
        assert r["id"] in claimed


async def test_claim_jobs_without_lanes_takes_everything(pool):
    await _retailer(pool, "shop", "shopify", 1)
    await _retailer(pool, "farmers", "farmers", 1)
    assert _by_retailer(await queries.claim_jobs(pool, "old", 50, 60)) == {"shop": 1, "farmers": 1}


# --- fair scheduling -------------------------------------------------------------------


async def test_in_flight_cap_per_retailer(pool):
    await _retailer(pool, "slow", "shopify", 10, ago=900)
    await _retailer(pool, "quick", "shopify", 2, ago=60)

    first = await queries.claim_jobs(pool, "a", 50, 60, ["http"], max_per_retailer=3)
    assert _by_retailer(first) == {"slow": 3, "quick": 2}, "one claim never takes more than the cap"
    # Most overdue first: slow's oldest three.
    assert sorted(j["key"] for j in first if j["retailer_id"] == "slow") == ["sku:slow:0", "sku:slow:1", "sku:slow:2"]

    # Another node: slow already has 3 running anywhere, so nothing more of it.
    assert await queries.claim_jobs(pool, "b", 50, 60, ["http"], max_per_retailer=3) == []

    # One finishes: exactly one more slot opens, for the next most overdue.
    job = next(j for j in first if j["retailer_id"] == "slow")
    await queries.finish_job(pool, job["id"], "a")
    [nxt] = await queries.claim_jobs(pool, "b", 50, 60, ["http"], max_per_retailer=3)
    assert nxt["key"] == "sku:slow:3"


async def test_expired_leases_dont_count_against_the_cap(pool):
    await _retailer(pool, "slow", "shopify", 5)
    await queries.claim_jobs(pool, "dead-node", 3, 60, ["http"], max_per_retailer=3)
    await pool.execute("UPDATE jobs SET lease_until = now() - interval '1 second' WHERE lease_owner = 'dead-node'")
    assert len(await queries.claim_jobs(pool, "b", 50, 60, ["http"], max_per_retailer=3)) == 3


async def test_most_overdue_goes_first_across_retailers(pool):
    await _retailer(pool, "late", "shopify", 1, ago=1200)
    await _retailer(pool, "later", "shopify", 1, ago=1800)
    await _retailer(pool, "fresh", "shopify", 1, ago=5)
    claimed = await queries.claim_jobs(pool, "a", 2, 60, ["http"], max_per_retailer=3)
    assert {j["retailer_id"] for j in claimed} == {"later", "late"}


async def test_worker_without_lanes_claims_nothing(pool, tmp_path):
    ctx = make_ctx(pool, "control", tmp_path)
    ctx.settings.worker_lanes = ""
    await _retailer(pool, "shop", "shopify", 2)
    worker = Worker(ctx)
    task = asyncio.create_task(worker.run())
    await asyncio.sleep(0.2)
    await worker.stop()
    await asyncio.wait_for(task, 2)
    assert await pool.fetchval("SELECT count(*) FROM jobs WHERE lease_owner IS NOT NULL") == 0


# --- leader eligibility ----------------------------------------------------------------


@pytest.mark.parametrize("eligible", [True, False])
def test_leader_eligibility(tmp_path, eligible):
    ctx = make_ctx(None, "n", tmp_path)
    ctx.settings.leader_eligible = eligible
    tasks = node_tasks(ctx, Worker(ctx))
    try:
        names = [name for _, name in tasks]
        assert names[:3] == ["heartbeat", "worker", "sender"], "every node beats, works and sends"
        assert ("elector" in names) is eligible
    finally:
        for coro, _ in tasks:
            coro.close()


# --- rate-limit shares per lane --------------------------------------------------------


def _node(name, lanes_, ip="1.2.3.4"):
    return {"name": name, "lanes": lanes_, "egress_ip": ip}


def test_limiter_shares_count_only_nodes_in_the_retailers_lane():
    live = [_node("nuc-control", []), _node("nuc-http", ["http"]), _node("nuc-http-2", ["http"]),
            _node("nuc-browser", ["browser"]), _node("cloud", ["http"], ip="9.9.9.9")]
    retailers = [{"id": "shop", "adapter": "shopify", "config": {}},
                 {"id": "farmers", "adapter": "farmers", "config": {}},
                 {"id": "moved", "adapter": "shopify", "config": {"lane": "browser"}}]
    default, shares = limiter_shares(live, retailers, "1.2.3.4")
    assert shares == {"shop": (2, 3), "farmers": (1, 1), "moved": (1, 1)}
    assert default == (3, 4), "nodes without lanes fetch nothing, so they never take a share"

    # A node from before lanes (NULL) ran every lane.
    _, shares = limiter_shares([_node("old", None), _node("nuc-browser", ["browser"])], retailers, "1.2.3.4")
    assert shares["shop"] == (1, 1) and shares["farmers"] == (2, 2)


def test_rate_limiter_uses_the_retailers_share():
    limiter = RateLimiter()
    limiter.set_shares(3, 4, retailers={"shop": (2, 3), "farmers": (1, 1)})
    assert limiter.interval(DIRECT, 60, "farmers") == pytest.approx(1.0)
    assert limiter.interval(DIRECT, 60, "shop") == pytest.approx(2.0)
    assert limiter.interval("browser", 60, "shop") == pytest.approx(3.0)
    assert limiter.interval(DIRECT, 60, "unknown") == pytest.approx(3.0), "falls back to the defaults"
    assert limiter.interval(DIRECT, 60) == pytest.approx(3.0)


async def test_heartbeat_records_lanes_and_sets_shares(pool, tmp_path):
    await _retailer(pool, "shop", "shopify", 0)
    await _retailer(pool, "farmers", "farmers", 0)
    nodes = []
    for name, worker_lanes in (("nuc-control", ""), ("nuc-http", "http"), ("nuc-browser", "browser")):
        ctx = make_ctx(pool, name, tmp_path)
        ctx.settings.worker_lanes = worker_lanes
        ctx.egress_ip = "1.2.3.4"
        nodes.append(ctx)
    for ctx in nodes:
        await beat(ctx)
    await beat(nodes[1])  # sees all three now
    rows = {r["name"]: r["lanes"] for r in await queries.list_nodes(pool)}
    assert rows == {"nuc-control": [], "nuc-http": ["http"], "nuc-browser": ["browser"]}
    limiter = nodes[1].http.limiter
    assert limiter.share(DIRECT, "shop") == 1, "three containers on one IP, but only one fetches from shop"
    assert limiter.share(DIRECT, "farmers") == 1


# --- per-node files --------------------------------------------------------------------


def test_log_file_is_per_node(tmp_path):
    assert log_file_name("nuc-http") == "bot-nuc-http.log"
    assert log_file_name("weird/name with spaces") == "bot-weird_name_with_spaces.log"
    assert safe_name("..") == "node"
    a = file_handler(str(tmp_path), 25, 7, "nuc-http")
    b = file_handler(str(tmp_path), 25, 7, "nuc-browser")
    a.emit(logging.LogRecord("t", logging.INFO, __file__, 1, "from http", None, None))
    b.emit(logging.LogRecord("t", logging.INFO, __file__, 1, "from browser", None, None))
    a.close()
    b.close()
    assert (tmp_path / "bot-nuc-http.log").read_text().strip() == "from http"
    assert (tmp_path / "bot-nuc-browser.log").read_text().strip() == "from browser"


def test_health_file_is_per_node(tmp_path):
    a = Settings(_env_file=None, data_dir=str(tmp_path), node_name="nuc-http")
    b = Settings(_env_file=None, data_dir=str(tmp_path), node_name="nuc-browser")
    assert a.health_file != b.health_file
    assert a.health_file.name == "heartbeat-nuc-http"


# --- queue lag -------------------------------------------------------------------------


async def test_queue_lag(pool):
    lag = await queries.queue_lag(pool)
    assert (lag["overdue"], lag["worst_seconds"]) == (0, 0)

    await _retailer(pool, "shop", "shopify", 3, ago=900)  # 900, 899, 898 s late
    await _retailer(pool, "fresh", "shopify", 1, ago=30)  # due, but not 2 min late
    await _retailer(pool, "off", "shopify", 1, ago=5000)
    await queries.update_retailer(pool, "off", enabled=False)
    # Paused: not counted (a real pause also moves next_run_at a day on; this one stays due).
    await pool.execute("UPDATE jobs SET paused_at = now() WHERE key = 'sku:shop:0'")
    lag = await queries.queue_lag(pool)
    assert lag["overdue"] == 2 and 898 <= lag["worst_seconds"] < 905

    # A running job isn't waiting.
    await pool.execute("UPDATE jobs SET lease_owner = 'a', lease_until = now() + interval '1 minute'"
                       " WHERE key = 'sku:shop:1'")
    lag = await queries.queue_lag(pool)
    assert lag["overdue"] == 1 and 897 <= lag["worst_seconds"] < 904


def test_queue_lag_issue_and_status_line():
    assert queue_lag_issue({"overdue": 0, "worst_seconds": 0}) == {}
    assert queue_lag_issue({"overdue": 40, "worst_seconds": QUEUE_LAG_WARN_SECONDS - 1}) == {}
    [(key, text)] = queue_lag_issue({"overdue": 40, "worst_seconds": 25 * 60}).items()
    assert key == "queue:lag" and "40 due jobs" in text and "25 min" in text
    assert "🟢" in queue_line({"overdue": 0, "worst_seconds": 30})
    assert "🟡 3 jobs" in queue_line({"overdue": 3, "worst_seconds": 200})
    assert "🔴 40 jobs" in queue_line({"overdue": 40, "worst_seconds": 25 * 60})


async def test_queue_lag_is_a_leader_health_issue(pool, tmp_path):
    ctx = make_ctx(pool, "nuc-control", tmp_path)
    await _retailer(pool, "shop", "shopify", 1, ago=QUEUE_LAG_WARN_SECONDS - 60)
    assert "queue:lag" not in await collect_issues(ctx)
    await pool.execute("UPDATE jobs SET next_run_at = now() - make_interval(secs => $1)",
                       float(QUEUE_LAG_WARN_SECONDS + 60))
    assert "queue:lag" in await collect_issues(ctx)
    await pool.execute("UPDATE jobs SET next_run_at = now() + interval '1 minute'")  # caught up: resolved
    assert "queue:lag" not in await collect_issues(ctx)
