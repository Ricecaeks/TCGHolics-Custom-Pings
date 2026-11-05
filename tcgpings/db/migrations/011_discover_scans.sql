-- How many products each discovery scan parsed, per retailer. A scan that suddenly finds nothing, or far
-- fewer than usual, means the site changed under the parser even though the job "succeeded".
CREATE TABLE discover_scans (
    id          bigserial PRIMARY KEY,
    retailer_id text NOT NULL REFERENCES retailers (id) ON DELETE CASCADE,
    scanned_at  timestamptz NOT NULL DEFAULT now(),
    products    integer NOT NULL,
    sealed      integer NOT NULL
);
CREATE INDEX discover_scans_recent ON discover_scans (retailer_id, id DESC);
ALTER TABLE discover_scans ENABLE ROW LEVEL SECURITY;

-- When a job was created, so a job that has never succeeded can still be called overdue.
ALTER TABLE jobs ADD COLUMN created_at timestamptz NOT NULL DEFAULT now();
