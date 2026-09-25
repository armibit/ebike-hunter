import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from connectors.zbike import ZbikeConnector


def _make_connector():
    config = {"portals": {"zbike": {"base_url": "https://z-bike.ch", "category_id": "528"}}}
    return ZbikeConnector(config)


# Real WooCommerce Store API product object (category=528 "usato"). Price is
# an integer string scaled by currency_minor_unit, not a plain decimal.
PRODUCT = {
    "id": 129896,
    "name": "Kalkhoff Entice",
    "permalink": "https://z-bike.ch/shop/usato/kalkhoff-entice/",
    "summary": "<p>E-Bike usata Kalkhoff Entice</p>",
    "prices": {
        "price": "299000",
        "currency_minor_unit": 2,
        "currency_code": "CHF",
    },
}


def test_parse_product_scales_price_by_minor_unit():
    connector = _make_connector()
    listing = connector._parse_product(PRODUCT)

    assert listing["portal"] == "zbike"
    assert listing["portal_id"] == "129896"
    assert listing["title"] == "Kalkhoff Entice"
    assert listing["price_raw"] == 2990.0
    assert listing["currency"] == "CHF"
    assert listing["url"] == "https://z-bike.ch/shop/usato/kalkhoff-entice/"


if __name__ == "__main__":
    test_parse_product_scales_price_by_minor_unit()
    print("\n✅ All Z-Bike connector tests passed!")
