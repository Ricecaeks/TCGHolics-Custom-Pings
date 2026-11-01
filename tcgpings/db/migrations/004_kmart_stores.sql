-- Kmart's stores are now real stores rather than the North and South Islands.
DELETE FROM product_state WHERE retailer_id = 'kmart' AND store_id IN ('NI', 'SI');
