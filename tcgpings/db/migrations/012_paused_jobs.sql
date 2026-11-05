-- Product checks that only ever get 403 (blocked) or 404 (delisted) are paused instead of retried every
-- few minutes: they held worker slots and kept the whole job queue behind. A paused check is retried
-- once a day and resumes on its own when that retry works.
ALTER TABLE jobs ADD COLUMN dead_failures integer NOT NULL DEFAULT 0;  -- 403/404 failures in a row
ALTER TABLE jobs ADD COLUMN paused_at timestamptz;
ALTER TABLE jobs ADD COLUMN paused_reason text;
ALTER TABLE jobs ADD COLUMN pause_reported boolean NOT NULL DEFAULT false;  -- posted to the staff log yet

-- Start the count from what's already known, so checks that have been dead for days pause on their next run.
UPDATE jobs SET dead_failures = consecutive_failures
WHERE kind = 'watch_sku' AND consecutive_failures > 0 AND last_error ~ '\mHTTP (403|404)\M';
