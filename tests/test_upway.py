import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from connectors.upway import UpwayConnector


def _make_connector():
    config = {
        "portals": {
            "upway": {
                "base_url": "https://upway.ch",
                "shop_domain": "upway-switzerland.myshopify.com",
                "brands": ["cube"],
            }
        }
    }
    return UpwayConnector(config)


# Representative Shopify products.json product: two variants (sizes), a
# machine-readable "key:value" facet tag that should be dropped, and a
# human-readable tag that should be kept since it carries motor/spec info
# the body text often omits.
PRODUCT = {
    "id": 8675309,
    "handle": "cube-stereo-hybrid-140-hpc",
    "title": "Cube Stereo Hybrid 140 HPC SLT 750",
    "body_html": "<p>Full suspension e-MTB, <strong>Bosch Performance Line CX</strong>, 750Wh.</p>",
    "tags": ["motor:bosch-cx", "Bosch Performance Line CX", "condition:refurbished"],
    "variants": [
        {"id": 1, "price": "3200.00"},
        {"id": 2, "price": "2990.00"},
    ],
}


def test_parse_product_extracts_core_fields():
    connector = _make_connector()
    listing = connector._parse_product(PRODUCT)

    assert listing["portal"] == "upway"
    assert listing["portal_id"] == "8675309"
    assert listing["url"] == "https://upway.ch/products/cube-stereo-hybrid-140-hpc"
    assert listing["title"] == "Cube Stereo Hybrid 140 HPC SLT 750"
    assert listing["currency"] == "CHF"


def test_parse_product_picks_lowest_variant_price():
    connector = _make_connector()
    listing = connector._parse_product(PRODUCT)

    assert listing["price_raw"] == 2990.0


def test_parse_product_drops_machine_readable_tags_keeps_readable():
    connector = _make_connector()
    listing = connector._parse_product(PRODUCT)

    assert "Bosch Performance Line CX" in listing["description_raw"]
    assert "motor:bosch-cx" not in listing["description_raw"]
    assert "condition:refurbished" not in listing["description_raw"]
    # body_html stripped to plain text
    assert "<p>" not in listing["description_raw"]
    assert "Full suspension e-MTB" in listing["description_raw"]


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
    test_parse_product_drops_machine_readable_tags_keeps_readable()
    test_parse_product_returns_none_without_handle_or_title()
    test_parse_product_defaults_price_to_zero_without_variants()
    print("\n✅ All Upway connector tests passed!")
