-- Small values the leader works out and every node reads, e.g. the #bot-logs webhook.
CREATE TABLE bot_settings (
    key        text PRIMARY KEY,
    value      text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE bot_settings ENABLE ROW LEVEL SECURITY;
