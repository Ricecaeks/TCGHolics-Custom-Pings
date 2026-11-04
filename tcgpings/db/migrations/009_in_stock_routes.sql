-- A route can skip new listings that can't be bought yet (sold out or unavailable when first seen); their
-- restock still alerts. Game channels like #pokemon-online-shops use it.
ALTER TABLE routes ADD COLUMN in_stock_only boolean NOT NULL DEFAULT false;
