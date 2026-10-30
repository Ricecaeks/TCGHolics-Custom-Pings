from tcgpings.engine.diff import diff_state, new_product_event
from tcgpings.models import ONLINE, EventType, Level, Product, Stock


def product(**kw):
    base = dict(retailer_id="farmers", sku="123", title="Pokemon 30th Booster Bundle", url="https://x/123")
    return Product(**{**base, **kw})


def prev(level, qty=None, price=None):
    return {"level": level, "qty": qty, "price_cents": price}


def types(events):
    return [e.type for e in events]


def test_first_observation_is_silent_baseline():
    assert diff_state(product(), "westgate", "Westgate", None, Stock(Level.IN, 5), 4999) == []


def test_unknown_level_never_alerts():
    assert diff_state(product(), ONLINE, None, prev("out"), Stock(Level.UNKNOWN), None) == []


def test_restock_at_store():
    events = diff_state(product(), "westgate", "Westgate", prev("out", 0), Stock(Level.IN, 12), None)
    assert types(events) == [EventType.RESTOCK]
    e = events[0]
    assert (e.store_id, e.store_name, e.old_qty, e.new_qty) == ("westgate", "Westgate", 0, 12)


def test_low_counts_as_restock_from_out():
    assert types(diff_state(product(), "w", "W", prev("out"), Stock(Level.LOW), None)) == [EventType.RESTOCK]


def test_out_of_stock():
    assert types(diff_state(product(), "w", "W", prev("in", 3), Stock(Level.OUT, 0), None)) == [EventType.OUT_OF_STOCK]


def test_qty_increase_alerts_but_selling_down_is_quiet():
    assert types(diff_state(product(), "w", "W", prev("in", 4), Stock(Level.IN, 20), None)) == [EventType.QTY_CHANGE]
    assert diff_state(product(), "w", "W", prev("in", 12), Stock(Level.IN, 11), None) == []


def test_level_change_between_low_and_in():
    assert types(diff_state(product(), "w", "W", prev("in"), Stock(Level.LOW), None)) == [EventType.QTY_CHANGE]
    assert types(diff_state(product(), "w", "W", prev("low"), Stock(Level.IN), None)) == [EventType.QTY_CHANGE]


def test_price_change_online_only():
    events = diff_state(product(), ONLINE, None, prev("in", None, 4999), Stock(Level.IN), 3999)
    assert types(events) == [EventType.PRICE_CHANGE]
    assert (events[0].old_price, events[0].new_price) == (4999, 3999)
    assert diff_state(product(), "w", "W", prev("in", None, 4999), Stock(Level.IN), 3999) == []


def test_restock_with_price_change_gives_both():
    events = diff_state(product(), ONLINE, None, prev("out", None, 4999), Stock(Level.IN), 5499)
    assert types(events) == [EventType.RESTOCK, EventType.PRICE_CHANGE]


def test_missing_new_price_keeps_old():
    events = diff_state(product(), ONLINE, None, prev("out", None, 4999), Stock(Level.IN), None)
    assert types(events) == [EventType.RESTOCK]
    assert events[0].new_price == 4999


def test_new_product_event_carries_online_state():
    e = new_product_event(product(online=Stock(Level.IN), price_cents=6999, franchise="pokemon"))
    assert (e.type, e.store_id, e.new_level, e.new_price, e.franchise) == (
        EventType.NEW_PRODUCT, ONLINE, "in", 6999, "pokemon"
    )


def test_dedupe_key_depends_on_state_and_bucket():
    a = diff_state(product(), "w", "W", prev("out"), Stock(Level.IN, 5), None)[0]
    b = diff_state(product(), "w", "W", prev("out"), Stock(Level.IN, 6), None)[0]
    assert a.dedupe_key(1) != b.dedupe_key(1)
    assert a.dedupe_key(1) != a.dedupe_key(2)
    assert a.dedupe_key(1) == a.dedupe_key(1)
