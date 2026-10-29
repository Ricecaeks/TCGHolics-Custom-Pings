-- Retailers are adapter instances: e.g. id 'farmers' (adapter 'farmers') or
-- id 'cardshop' (adapter 'shopify', config {"domain": "cardshop.co.nz"}).
CREATE TABLE retailers (
    id                  text PRIMARY KEY,
    adapter             text NOT NULL,
    name                text NOT NULL,
    enabled             boolean NOT NULL DEFAULT true,
    proxy_policy        text NOT NULL DEFAULT 'direct' CHECK (proxy_policy IN ('direct', 'pool', 'sticky')),
    requests_per_minute integer NOT NULL DEFAULT 30,
    color               integer,
    config              jsonb NOT NULL DEFAULT '{}'
);

CREATE TABLE stores (
    retailer_id text NOT NULL REFERENCES retailers (id) ON DELETE CASCADE,
    store_id    text NOT NULL,
    name        text NOT NULL,
    slug        text NOT NULL,
    region      text,
    updated_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (retailer_id, store_id)
);

-- kind 'keyword': query is search text, retailer_id NULL means every retailer.
-- kind 'sku':     query is the retailer's product reference, retailer_id required.
-- store_ids NULL means every known store of the retailer.
CREATE TABLE watches (
    id               bigserial PRIMARY KEY,
    kind             text NOT NULL CHECK (kind IN ('keyword', 'sku')),
    query            text NOT NULL,
    retailer_id      text REFERENCES retailers (id) ON DELETE CASCADE,
    store_ids        text[],
    franchise        text,
    interval_seconds integer,
    enabled          boolean NOT NULL DEFAULT true,
    created_by       bigint,
    created_at       timestamptz NOT NULL DEFAULT now(),
    CHECK (kind = 'keyword' OR retailer_id IS NOT NULL)
);

CREATE TABLE products (
    retailer_id   text NOT NULL REFERENCES retailers (id) ON DELETE CASCADE,
    sku           text NOT NULL,
    title         text NOT NULL,
    url           text NOT NULL,
    image         text,
    franchise     text,
    ptype         text,
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (retailer_id, sku)
);

-- Latest known state only. store_id '' is the online state.
CREATE TABLE product_state (
    retailer_id text NOT NULL,
    sku         text NOT NULL,
    store_id    text NOT NULL DEFAULT '',
    level       text NOT NULL,
    qty         integer,
    price_cents integer,
    updated_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (retailer_id, sku, store_id),
    FOREIGN KEY (retailer_id, sku) REFERENCES products (retailer_id, sku) ON DELETE CASCADE
);

CREATE TABLE state_changes (
    id          bigserial PRIMARY KEY,
    retailer_id text NOT NULL,
    sku         text NOT NULL,
    store_id    text NOT NULL,
    old_level   text,
    new_level   text NOT NULL,
    old_qty     integer,
    new_qty     integer,
    old_price   integer,
    new_price   integer,
    changed_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX state_changes_changed_at ON state_changes (changed_at);
CREATE INDEX state_changes_product ON state_changes (retailer_id, sku, changed_at DESC);

-- NULL filters match anything. store_id '' matches only online events.
-- event_types NULL means the default set (everything except out_of_stock).
CREATE TABLE routes (
    id          bigserial PRIMARY KEY,
    retailer_id text REFERENCES retailers (id) ON DELETE CASCADE,
    store_id    text,
    franchise   text,
    event_types text[],
    channel_id  bigint NOT NULL,
    webhook_url text NOT NULL,
    role_id     bigint,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX routes_retailer ON routes (retailer_id);

CREATE TABLE jobs (
    id                   bigserial PRIMARY KEY,
    key                  text NOT NULL UNIQUE,
    kind                 text NOT NULL CHECK (kind IN ('watch_sku', 'watch_search', 'sync_stores')),
    retailer_id          text NOT NULL REFERENCES retailers (id) ON DELETE CASCADE,
    payload              jsonb NOT NULL DEFAULT '{}',
    interval_seconds     integer NOT NULL,
    -- Jobs created by a keyword watch for products it found; removed with the watch.
    watch_id             bigint REFERENCES watches (id) ON DELETE CASCADE,
    auto                 boolean NOT NULL DEFAULT false,
    enabled              boolean NOT NULL DEFAULT true,
    next_run_at          timestamptz NOT NULL DEFAULT now(),
    lease_owner          text,
    lease_until          timestamptz,
    runs                 integer NOT NULL DEFAULT 0,
    last_ok_at           timestamptz,
    last_error           text,
    last_error_at        timestamptz,
    consecutive_failures integer NOT NULL DEFAULT 0
);
CREATE INDEX jobs_due ON jobs (next_run_at) WHERE enabled;

CREATE TABLE alert_outbox (
    id              bigserial PRIMARY KEY,
    dedupe_key      text NOT NULL UNIQUE,
    route_id        bigint NOT NULL REFERENCES routes (id) ON DELETE CASCADE,
    payload         jsonb NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    attempts        integer NOT NULL DEFAULT 0,
    next_attempt_at timestamptz NOT NULL DEFAULT now(),
    lease_owner     text,
    lease_until     timestamptz,
    sent_at         timestamptz,
    last_error      text
);
CREATE INDEX alert_outbox_pending ON alert_outbox (next_attempt_at) WHERE sent_at IS NULL;
CREATE INDEX alert_outbox_sent_at ON alert_outbox (sent_at) WHERE sent_at IS NOT NULL;

CREATE TABLE nodes (
    name           text PRIMARY KEY,
    version        text NOT NULL,
    egress_ip      text,
    is_leader      boolean NOT NULL DEFAULT false,
    started_at     timestamptz NOT NULL DEFAULT now(),
    last_heartbeat timestamptz NOT NULL DEFAULT now(),
    jobs_ok        bigint NOT NULL DEFAULT 0,
    jobs_failed    bigint NOT NULL DEFAULT 0,
    alerts_sent    bigint NOT NULL DEFAULT 0
);

CREATE TABLE proxies (
    id             bigserial PRIMARY KEY,
    url            text NOT NULL UNIQUE,
    enabled        boolean NOT NULL DEFAULT true,
    cooldown_until timestamptz,
    fail_count     integer NOT NULL DEFAULT 0
);

-- Supabase exposes the public schema through its Data API. RLS with no policies
-- blocks the anon/authenticated roles; the app connects as the table owner.
ALTER TABLE retailers ENABLE ROW LEVEL SECURITY;
ALTER TABLE stores ENABLE ROW LEVEL SECURITY;
ALTER TABLE watches ENABLE ROW LEVEL SECURITY;
ALTER TABLE products ENABLE ROW LEVEL SECURITY;
ALTER TABLE product_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE state_changes ENABLE ROW LEVEL SECURITY;
ALTER TABLE routes ENABLE ROW LEVEL SECURITY;
ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE alert_outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE nodes ENABLE ROW LEVEL SECURITY;
ALTER TABLE proxies ENABLE ROW LEVEL SECURITY;
