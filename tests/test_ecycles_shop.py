import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from connectors.ecycles_shop import EcyclesShopConnector


def _make_connector():
    config = {"portals": {"ecycles_shop": {"base_url": "https://ecycles-shop.it", "collection": "usato"}}}
    return EcyclesShopConnector(config)


# Real Shopify /collections/usato/products.json product object, including
# the body_html field (only field carrying spec details like battery Wh).
PRODUCT = {
    "id": 8928094126425,
    "title": "RIESE & MULLER SUPERCHARGER NUVINCI",
    "handle": "riese-muller-supercharger-nuvinci",
    "variants": [{"price": "2500.00"}],
    "body_html": "<p>Riese &amp; Muller Supercharger Nuvinci</p>\n<p>Doppia batteria totale 1000Wh</p>\n<!---->",
}


def test_parse_product_extracts_fields():
    connector = _make_connector()
    listing = connector._parse_product(PRODUCT)

    assert listing["portal"] == "ecycles_shop"
    assert listing["portal_id"] == "8928094126425"
    assert listing["title"] == "RIESE & MULLER SUPERCHARGER NUVINCI"
    assert listing["price_raw"] == 2500.0
    assert listing["currency"] == "EUR"
    assert listing["url"] == "https://ecycles-shop.it/products/riese-muller-supercharger-nuvinci"
    assert listing["description_raw"] == "Riese & Muller Supercharger Nuvinci Doppia batteria totale 1000Wh", \
        "must strip HTML tags from body_html so spec keywords are plain text"


if __name__ == "__main__":
    test_parse_product_extracts_fields()
    print("\n✅ All Ecycles-shop connector tests passed!")
