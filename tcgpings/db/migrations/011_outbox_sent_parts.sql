-- How many of an alert's Discord messages (embed first, then overflow ping messages) already went out,
-- so a retry after a later message failed only sends what's left instead of pinging people twice.
ALTER TABLE alert_outbox ADD COLUMN sent_parts integer NOT NULL DEFAULT 0;
