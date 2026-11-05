-- Which worker lanes each node claims jobs for (WORKER_LANES), so a retailer's rate limit is split only
-- between the nodes that actually fetch from it. NULL: a node from before lanes, which ran every lane.
ALTER TABLE nodes ADD COLUMN lanes text[];
