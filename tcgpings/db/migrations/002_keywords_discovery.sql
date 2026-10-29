-- Zephyr-style keyword filters per route, e.g. "30th booster bundle, elite trainer box, -sleeves".
ALTER TABLE routes ADD COLUMN keywords text;

-- Direct add-to-cart link where the retailer supports one (Shopify cart permalinks).
ALTER TABLE products ADD COLUMN atc_url text;

-- Retailer-wide discovery of the TCG range (new listings, online stock), independent of watches.
ALTER TABLE jobs DROP CONSTRAINT jobs_kind_check;
ALTER TABLE jobs ADD CONSTRAINT jobs_kind_check
    CHECK (kind IN ('watch_sku', 'watch_search', 'sync_stores', 'discover'));
