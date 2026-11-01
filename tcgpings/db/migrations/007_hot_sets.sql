-- Hot sets get faster store checks until this time. Staff approve them from news cards or /hot add.
ALTER TABLE watches ADD COLUMN hot_until timestamptz;
UPDATE watches SET hot_until = now() + interval '14 days'
WHERE query IN ('pokemon 30th', 'delta reign', 'focused fighters', 'heavy hitters', 'unova', 'ultra premium collection');

-- Release headlines found in news feeds, and what staff decided about them.
CREATE TABLE hot_candidates (
    id         bigserial PRIMARY KEY,
    source     text NOT NULL,
    title      text NOT NULL,
    url        text NOT NULL,
    keyword    text NOT NULL,
    status     text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'ignored', 'duplicate')),
    message_id bigint,
    seen_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source, title)
);
ALTER TABLE hot_candidates ENABLE ROW LEVEL SECURITY;
