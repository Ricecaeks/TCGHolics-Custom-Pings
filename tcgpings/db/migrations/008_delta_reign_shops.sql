-- NZ card shops that listed Delta Reign (6 Nov 2026) in the Zephyr alert history. All Shopify;
-- each one's /products.json and /search/suggest.json answered on 2026-11-04.
-- An operator's later edits (rate, colour, enabled) are kept.
INSERT INTO retailers (id, adapter, name, config) VALUES
    ('game-corner',      'shopify', 'Game Corner',      '{"domain": "gamecorner.co.nz"}'),
    ('ocare',            'shopify', 'OCARE',            '{"domain": "ocare.co.nz"}'),
    ('aniverse',         'shopify', 'Aniverse',         '{"domain": "aniverse.co.nz"}'),
    ('playx',            'shopify', 'PLAYX',            '{"domain": "playx.co.nz"}'),
    ('card-masters',     'shopify', 'Card Masters',     '{"domain": "cardmasters.co.nz"}'),
    ('kidzstuffonline',  'shopify', 'Kidzstuffonline',  '{"domain": "kidzstuffonline.co.nz"}'),
    ('the-game-tree',    'shopify', 'The Game Tree',    '{"domain": "thegametree.co.nz"}'),
    ('game-roost',       'shopify', 'Game Roost',       '{"domain": "gameroost.co.nz"}'),
    ('collectors-guild', 'shopify', 'Collectors Guild', '{"domain": "collectorsguild.co.nz"}'),
    ('toy-time',         'shopify', 'Toy Time',         '{"domain": "toytime.co.nz"}')
ON CONFLICT (id) DO NOTHING;
