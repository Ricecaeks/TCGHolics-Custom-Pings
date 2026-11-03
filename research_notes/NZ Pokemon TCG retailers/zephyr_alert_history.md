# Zephyr alert history in the TCGHolics NZ Discord (primary source)

Collected on 2026-11-04 by reading the TCGHolics NZ Discord server through the owner's own browser session (read-only). Zephyr Monitors posted alerts there during a trial from about 14 October to 3 November 2026. The alerts carry the store name and site URL in each embed's author line, and Zephyr's own redirect links carry the domain as `s=<domain>`.

Method: server-wide Discord search (`before:<date>`) paged through about 235 result pages covering 14 Oct to 3 Nov, plus scrolling the newest messages in `#nz-shopify-feed` and `#pokemon-online-shops`. Search covered all channels, including the general `#nz-shopify-feed`. The first few hours of the trial (before about 14 Oct 14:20 UTC) were not reached because Discord's search rate-limited; the number of distinct stores had already stopped growing (47), so few or no stores are likely missing.

Zephyr's full site list is not public: its docs (help.zephyrmonitors.com/docs/start/sitelist) say the full list is shared only through its application form. Zephyr support told the owner on 2026-10-21 that there is "no definite list" and "any AU/NZ site is fair game". So the alert history below is the most complete record of what it actually pinged.

"alerts" counts alert cards seen (search pages overlap slightly, so treat as relative volume). "tcg" counts alerts whose product title matched card-game terms.

## Card-game stores Zephyr pinged (monitoring targets)

| Domain | Store name in alerts | Alerts | Card-game alerts | Example products |
|---|---|---|---|---|
| popstop.co.nz | Pop Stop | 845 | 613 | MTG TMNT Commander; Lorcana Hyperia City Illumineer's Trove |
| gamecorner.co.nz | Game Corner | 431 | 431 | Pokémon ME06 Delta Reign Booster Bundle/Box preorders; 30th Celebration Ultra-Premium Collection Day/Night preorders |
| farmers.co.nz | Farmers NZ [KW Ping] | 427 | 427 | Pokémon 30th Booster Bundle; ME2.5 Ascended Heroes Tin |
| animalkingdoms.co.nz | Animal Kingdoms Toy Store | 264 | 250 | Pokémon Battle Figure Sets (mostly toys, some TCG) |
| ocare.co.nz | OCARE NZ | 242 | 165 | One Piece EB-05, TS-03; Pokémon Delta Reign Booster Bundle, 30th Ultra Premium Day/Night |
| paperplus.co.nz | Paper Plus NZ | 168 | 151 | Lorcana decks; Pokémon products |
| mrtofu.store | Mr Tofu Card Store | 97 | 97 | Pokémon bundles; One Piece OP-18 preorder; MTG events |
| mightyape.co.nz | Mighty Ape | 99 | 94 | Pokémon Perfect Order 3-pack blister; Mega Zygarde ex Premium Collection |
| aniverse.co.nz | Aniverse | 73 | 72 | Pokémon Delta Reign ETB/booster preorders |
| jbhifi.co.nz | JB Hi-Fi NZ | 1339 | 67 | Yu-Gi-Oh tuckboxes (most JB alerts are non-TCG electronics) |
| metalife.co.nz | MetaLife | 116 | 60 | Riftbound Vendetta/Radiance; Pokémon 30th Battle Deck; Ascended Heroes |
| playx.co.nz | PLAYX | 86 | 59 | Pokémon 30th Knock Out Collection (limit 2); Delta Reign ETB; MTG Star Trek |
| hobbixchange.co.nz | HobbiXchange | 350 | 52 | Pokémon Pitch Black Booster Box; One Piece TS-03; MTG Fallout |
| kmart.co.nz | KMart NZ | 48 | 48 | Pokémon Surging Sparks, Phantasmal Flames |
| cardmasters.co.nz | Card Masters | 42 | 42 | Pokémon Ascended Heroes booster; Delta Reign preorder |
| kidzstuffonline.co.nz | Kidzstuffonline | 147 | 32 | Pokémon 30th Booster Bundle; Delta Reign ETB preorder |
| thegametree.co.nz | The Game Tree NZ | 78 | 32 | Delta Reign Booster Pack / Bundle (strict limits, release 6 Nov) |
| p-bandai.com | Premium Bandai NZ | 26 | 26 | Gundam Card Game premium goods |
| gameroost.co.nz | Game Roost | 75 | 22 | Pokémon Delta Reign Booster Bundle, Deck Crafter's Collection; One Piece EB05 |
| tcgcollectornz.com | TCG Collector NZ | 403 | 21 | Pokémon Deluxe Battle Deck; sports cards |
| thewarehouse.co.nz | The Warehouse NZ | 16 | 16 | Pokémon Chaos Rising sleeved booster; Pitch Black blisters |
| otakumart.co.nz | Otakumart.co.nz | 36 | 12 | MTG The Hobbit, Foundations; Pokémon |
| retrospace.co.nz | Retrospace NZ | 11 | 10 | Pokémon Pitch Black, Perfect Order boosters |
| collectorsguild.co.nz | Collectors Guild | 10 | 10 | Delta Reign Booster Bundle and Booster Box bundles (limit 1) |
| toytime.co.nz | Toy Time | 12 | 8 | Pokémon Delta Reign ETB and Booster Box preorders |
| hobbyzone.co.nz | Hobby Zone | 6 | 6 | Yu-Gi-Oh Maximum Gold, Cyber Strike |
| shuffleandcutgames.co.nz | Shuffle n Cut Hobbies & Games | 19 | 5 | MTG Star Trek boosters and Commander decks |

Note: the server also has a `#pokemon-center-nz` channel; no Pokémon Center alerts were found in the history captured.

## Non-card stores Zephyr also pinged (exclude)

Sneaker, streetwear and gift shops from Zephyr's general NZ Shopify feed, with no meaningful card-game product: jdsports.co.nz, stirlingsports.co.nz, loadednz.com, infinitedefinite.com, slickwillys.co.nz, fusionskateshop.com, stencil.co.nz, shopcasio.monacocorp.co.nz, pavement.co.nz, knowear.co, fallenfront.co.nz, shop.goodasgoldshop.com, whangamatasurfshop.co.nz, edit-store.com, culturekings.co.nz, area51store.co.nz (sneakers, not the hobby store), superette.co.nz, stirlingwomen.co.nz, embassy.co.nz, empireskate.co.nz (Pokémon-branded clothing only).

## Relevance to the bot

Already monitored by the TCGHolics bot: Farmers, Kmart, The Warehouse, JB Hi-Fi, Toyworld, Card Merchant, Iron Knight Gaming. Every other card-game store above is a new target. Their platform was not tested in this pass; the Zephyr feed that pinged most of them is labelled "Shopify" in its footers ("Shopify v20.4.4 | By TCGHolics NZ x Zephyr Monitors"), which suggests those stores run Shopify, but this was not confirmed per store. Mighty Ape, Farmers, Kmart, The Warehouse, Paper Plus and Premium Bandai are not Shopify.
