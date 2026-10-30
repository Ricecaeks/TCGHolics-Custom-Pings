-- Circuit breakers for the fetch chain (net/chain.py): one row per retailer and route
-- (browser, scrapfly, zyte). A route is skipped while open_until is in the future.
CREATE TABLE fetch_breakers (
    retailer_id text NOT NULL REFERENCES retailers (id) ON DELETE CASCADE,
    backend     text NOT NULL,
    open_until  timestamptz,
    failures    integer NOT NULL DEFAULT 0,
    last_error  text,
    last_ok_at  timestamptz,
    updated_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (retailer_id, backend)
);

-- Paid unblocker spend per calendar month (UTC), checked against UNBLOCKER_MONTHLY_BUDGET_USD.
CREATE TABLE unblocker_spend (
    month    date NOT NULL,
    backend  text NOT NULL,
    requests integer NOT NULL DEFAULT 0,
    cost_usd double precision NOT NULL DEFAULT 0,
    PRIMARY KEY (month, backend)
);

ALTER TABLE fetch_breakers ENABLE ROW LEVEL SECURITY;
ALTER TABLE unblocker_spend ENABLE ROW LEVEL SECURITY;
