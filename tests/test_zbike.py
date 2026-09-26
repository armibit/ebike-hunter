import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from connectors.zbike import ZbikeConnector


def _make_connector():
    config = {"portals": {"zbike": {"base_url": "https://z-bike.ch", "category_id": "528"}}}
    return ZbikeConnector(config)


# Real WooCommerce Store API product object (category=528 "usato", confirmed
# live 2026-09-26). Price is an integer string scaled by currency_minor_unit,
# not a plain decimal. Note: there is no "summary" field anywhere in the real
# API response — only "short_description" (usually empty on this shop) and
# "description" (the actual write-up, HTML-wrapped).
PRODUCT = {
    "id": 129896,
    "name": "Kalkhoff Entice",
    "permalink": "https://z-bike.ch/shop/usato/kalkhoff-entice/",
    "short_description": "",
    "description": (
        "Straordinaria e-bike all-road Kalkhoff Entice taglia S/M, praticamente nuova "
        "con solo 1 km all’attivo. Equipaggiata con il potente motore Bosch CX da 85 Nm, "
        "una capiente batteria da 750 Wh per autonomie lunghissime.</p>"
    ),
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


def test_parse_product_reads_real_description_field_not_summary():
    # Regression: "summary" isn't a real field in this API — description_raw
    # was silently "" for every single Z-Bike listing, forever (no detail-
    # page fallback exists for this connector either).
    connector = _make_connector()
    listing = connector._parse_product(PRODUCT)

    assert "Bosch CX" in listing["description_raw"]
    assert "85 Nm" in listing["description_raw"]
    assert "750 Wh" in listing["description_raw"]
    # Stray HTML tags must be cleaned up.
    assert "</p>" not in listing["description_raw"]


def test_parse_product_falls_back_to_short_description_when_description_empty():
    connector = _make_connector()
    product = {**PRODUCT, "description": "", "short_description": "<p>Bici in ottimo stato</p>"}
    listing = connector._parse_product(product)
    assert listing["description_raw"] == "Bici in ottimo stato"


if __name__ == "__main__":
    test_parse_product_scales_price_by_minor_unit()
    test_parse_product_reads_real_description_field_not_summary()
    test_parse_product_falls_back_to_short_description_when_description_empty()
    print("\n✅ All Z-Bike connector tests passed!")
