-- Routes the bot manages from tcgpings/discord/layout.json carry the layout channel's name; the bot adds,
-- changes and removes those itself. Routes made with /route set or /setup keep NULL and are left alone.
ALTER TABLE routes ADD COLUMN layout_channel text;
