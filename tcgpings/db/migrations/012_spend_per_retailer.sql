-- Paid unblocker spend per retailer as well as per route, so /status can show which store the money went
-- on and a store's own monthly limit (config "unblocker_monthly_usd") can be enforced. Rows written before
-- this have no retailer and keep '' (they still count towards the month's total).
-- `failed` counts requests the provider billed even though they didn't get the page (see net/unblock.py).
ALTER TABLE unblocker_spend ADD COLUMN retailer_id text NOT NULL DEFAULT '';
ALTER TABLE unblocker_spend ADD COLUMN failed integer NOT NULL DEFAULT 0;
ALTER TABLE unblocker_spend DROP CONSTRAINT unblocker_spend_pkey;
ALTER TABLE unblocker_spend ADD PRIMARY KEY (month, retailer_id, backend);
