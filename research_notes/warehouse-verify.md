can’t put together a package for getting past The Warehouse’s bot protection, whether I build it or another agent does. The barrier is a Cloudflare human check plus signed per-product tokens, so reading that store data means defeating an access control the site put up on purpose. That’s the same line regardless of which tool runs it, and handing the steps to another model is still me providing them.

This isn’t a Zyte limit. Zyte would just be the delivery route, and its own terms bar breaching a site’s authentication. The block is The Warehouse’s intent that this data not be read by bots.

A few honest technical facts, which aren’t a how-to:

It’s genuinely locked, not just awkward. The store-availability call needs a verify token that’s minted into each product page, and the hot Pokémon product pages sit behind an interactive Cloudflare challenge. There’s no fixed trick; their protection changes, which is exactly why it’s a wall and not a speed bump.
The other Discord isn’t doing the impossible. Far more likely they have manual reporters, a paid feed, or staff contacts than a working automated bypass. That’s worth knowing before anyone spends days on this.

What I’ll gladly build or hand over in full detail:

The legitimate Warehouse paths: the public listing fields, the nationwide in-store signal I just shipped, and exactly how the adapter works.
The retailers where store stock is already open: Kmart’s gateway, Toyworld’s Stock In Store, and JB Hi-Fi’s store IDs. All documented in the repo, no bypass involved.
A draft to The Warehouse asking for a sanctioned stock feed. If they say yes, the per-store alerts you want become easy and legal.

If you want the real route to Warehouse per-store alerts, it’s that request or a licensed feed, and I’ll help with either straight away.