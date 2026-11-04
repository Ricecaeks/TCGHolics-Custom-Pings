-- When a product was announced as a new listing. Its first in-store reading within a day of that alerts
-- (a new drop that's in-store only), where other first readings stay a silent baseline.
ALTER TABLE products ADD COLUMN announced_at timestamptz;
