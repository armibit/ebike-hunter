import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from connectors.buybestgear import BuybestgearConnector


def _make_connector():
    config = {
        "portals": {
            "buybestgear": {
                "base_url": "https://www.buybestgear.com",
                "collection": "full-suspension-e-bikes",
            }
        }
    }
    return BuybestgearConnector(config)


# Representative Shopify products.json product for this store — real body_html
# prose (unlike Upway, this store's marketing text does state the real motor
# torque/battery capacity), a mix of readable and bucketed/range facet tags,
# and two color variants at the same price.
PRODUCT = {
    "id": 7985452099,
    "handle": "lankeleisi-mg600-pro-29-full-suspension-e-mtb",
    "title": "Lankeleisi MG600 Pro 29\" Trails E-Mountain Bike 150/130 mm Full Suspension 960Wh EMTB",
    "body_html": "<p>Maximum Torque 65 N·m Controller 18A. Battery 48V 20Ah (960Wh) Samsung Cell.</p>",
    "tags": ["full suspension", "torque sensor", "60-70nm", "900-1000wh", "e-mtb", "in-stock"],
    "variants": [
        {"id": 1, "title": "Gray", "price": "1799.00"},
        {"id": 2, "title": "Orange", "price": "1799.00"},
    ],
}


def test_parse_product_extracts_core_fields():
    connector = _make_connector()
    listing = connector._parse_product(PRODUCT)

    assert listing["portal"] == "buybestgear"
    assert listing["portal_id"] == "7985452099"
    assert listing["url"] == "https://www.buybestgear.com/products/lankeleisi-mg600-pro-29-full-suspension-e-mtb"
    assert listing["title"].startswith("Lankeleisi MG600 Pro")
    assert listing["currency"] == "EUR"


def test_parse_product_picks_lowest_variant_price():
    connector = _make_connector()
    listing = connector._parse_product(PRODUCT)
    assert listing["price_raw"] == 1799.0


def test_parse_product_description_keeps_real_specs():
    connector = _make_connector()
    listing = connector._parse_product(PRODUCT)

    assert "65" in listing["description_raw"]
    assert "960Wh" in listing["description_raw"]
    assert "full suspension" in listing["description_raw"]
    # body_html stripped to plain text
    assert "<p>" not in listing["description_raw"]


def test_parse_product_drops_bucketed_range_tags():
    # "60-70nm"/"900-1000wh" are coarse facet buckets, not real values — the
    # real numbers already come from body_html, so these must not leak in
    # and risk the parser reading the wrong (bucket-boundary) number.
    connector = _make_connector()
    listing = connector._parse_product(PRODUCT)

    assert "60-70nm" not in listing["description_raw"]
    assert "900-1000wh" not in listing["description_raw"]


def test_get_listing_details_is_a_noop():
    # Unlike Upway, body_html already has the real specs — no extra fetch needed.
    connector = _make_connector()
    assert connector.get_listing_details("7985452099", "https://www.buybestgear.com/products/x") == {}


def test_parse_product_returns_none_without_handle_or_title():
    connector = _make_connector()
    assert connector._parse_product({"title": "No handle"}) is None
    assert connector._parse_product({"handle": "no-title"}) is None


def test_parse_product_defaults_price_to_zero_without_variants():
    connector = _make_connector()
    listing = connector._parse_product({"handle": "x", "title": "X", "variants": []})
    assert listing["price_raw"] == 0.0


if __name__ == "__main__":
    test_parse_product_extracts_core_fields()
    test_parse_product_picks_lowest_variant_price()
    test_parse_product_description_keeps_real_specs()
    test_parse_product_drops_bucketed_range_tags()
    test_get_listing_details_is_a_noop()
    test_parse_product_returns_none_without_handle_or_title()
    test_parse_product_defaults_price_to_zero_without_variants()
    print("\n✅ All Buybestgear connector tests passed!")
