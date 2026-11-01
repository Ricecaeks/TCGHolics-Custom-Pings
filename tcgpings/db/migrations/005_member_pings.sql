-- Keywords members set for themselves with /ping add. Alerts matching them tag the member.
CREATE TABLE member_pings (
    id         bigserial PRIMARY KEY,
    user_id    bigint NOT NULL,
    keywords   text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX member_pings_unique ON member_pings (user_id, lower(keywords));
ALTER TABLE member_pings ENABLE ROW LEVEL SECURITY;

-- A channel that only gets alerts someone asked for, tagging those members (e.g. #custom-pings).
ALTER TABLE routes ADD COLUMN member_pings boolean NOT NULL DEFAULT false;
