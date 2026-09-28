import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from connectors.base import availability_from_page, shopify_variants_available
from connectors.ecycles_shop import EcyclesShopConnector
from connectors.registry import CONNECTOR_CLASSES, PORTALS, is_enabled, portal_country
from connectors.upway import UpwayConnector
from connectors.zbike import ZbikeConnector

URL = "https://www.subito.it/biciclette/ebike-cube-stereo-como-651643880.htm"


def test_removed_listing_by_status_code():
    assert availability_from_page(404, URL, URL, "") is False
    assert availability_from_page(410, URL, URL, "") is False
    # Blocked / rate limited / server error: no verdict, never "sold".
    assert availability_from_page(403, URL, URL, "") is None
    assert availability_from_page(503, URL, URL, "") is None
    print("✅ Availability: status codes")


def test_redirect_away_from_listing_means_removed():
    assert availability_from_page(200, URL, "https://www.subito.it/annunci-lombardia/vendita/biciclette/", "<html></html>") is False
    # Same id under a new slug is still the same listing.
    moved = "https://www.subito.it/biciclette/ebike-cube-stereo-hybrid-como-651643880.htm"
    assert availability_from_page(200, URL, moved, "<html></html>") is True
    # No id in the URL: a redirect to another slug (e.g. another language) is not proof of a sale.
    slug = "https://velomarkt.ch/de/cube-stereo"
    assert availability_from_page(200, slug, "https://velomarkt.ch/it/cube-stereo-hybrid", "<html></html>") is True
    print("✅ Availability: redirects")


def test_schema_org_availability():
    sold = '<script type="application/ld+json">{"offers": {"availability": "https://schema.org/OutOfStock"}}</script>'
    live = '<script type="application/ld+json">{"offers": {"availability": "http://schema.org/InStock"}}</script>'
    assert availability_from_page(200, URL, URL, sold) is False
    assert availability_from_page(200, URL, URL, live) is True
    print("✅ Availability: schema.org")


def test_sold_messages_but_not_seller_prose():
    expired = "<div class='banner'>Questo annuncio non è più disponibile</div>"
    assert availability_from_page(200, URL, URL, expired) is False
    german = "<p>Dieses Inserat ist nicht mehr verfügbar.</p>"
    assert availability_from_page(200, URL, URL, german) is False
    # A seller's own words must not switch the listing off.
    prose = "<p>Bici venduta con caricatore originale, esaurito il primo set di pastiglie.</p>"
    assert availability_from_page(200, URL, URL, prose) is True
    # ...unless the connector is a shop and opted into stock labels.
    shop_page = "<span class='stock'>Esaurito</span>"
    assert availability_from_page(200, URL, URL, shop_page, sold_markers=("esaurito",)) is False
    print("✅ Availability: sold messages")


def test_shopify_variant_flags():
    assert shopify_variants_available([{"available": False}, {"available": False}]) is False
    assert shopify_variants_available([{"available": False}, {"available": True}]) is True
    assert shopify_variants_available([{"price": "10"}]) is None
    assert shopify_variants_available([]) is None
    print("✅ Shopify variant flags")


def test_shop_feeds_carry_availability():
    config = {"portals": {
        "ecycles_shop": {"base_url": "https://ecycles-shop.it"},
        "upway": {"base_url": "https://upway.ch", "shop_domain": "x.myshopify.com", "brands": []},
        "zbike": {"base_url": "https://z-bike.ch"},
    }}
    sold_product = {"id": 1, "handle": "cube", "title": "Cube", "variants": [{"price": "2000", "available": False}]}
    assert EcyclesShopConnector(config)._parse_product(sold_product)["is_available"] is False
    assert UpwayConnector(config)._parse_product(sold_product)["is_available"] is False

    woo = {"id": 7, "name": "Trek Rail", "permalink": "https://z-bike.ch/p/7", "is_in_stock": False,
           "prices": {"price": "250000", "currency_minor_unit": 2, "currency_code": "CHF"}}
    assert ZbikeConnector(config)._parse_product(woo)["is_available"] is False
    print("✅ Shop feeds carry availability")


def test_shopify_check_uses_product_js():
    connector = EcyclesShopConnector({"portals": {"ecycles_shop": {"base_url": "https://ecycles-shop.it"}}})
    requested = []

    def fake_raw_get(url):
        requested.append(url)
        return SimpleNamespace(status_code=200, json=lambda: {"available": False})

    connector._raw_get = fake_raw_get
    assert connector.check_availability("1", "https://ecycles-shop.it/products/cube?variant=3") is False
    assert requested == ["https://ecycles-shop.it/products/cube.js"]

    connector._raw_get = lambda url: SimpleNamespace(status_code=404)
    assert connector.check_availability("1", "https://ecycles-shop.it/products/cube") is False
    connector._raw_get = lambda url: None
    assert connector.check_availability("1", "https://ecycles-shop.it/products/cube") is None
    print("✅ Shopify availability check")


def test_registry_covers_every_portal():
    assert set(CONNECTOR_CLASSES) == set(PORTALS)
    assert portal_country("subito") == "IT" and portal_country("tutti") == "CH"
    assert portal_country("nope") is None
    assert is_enabled("tutti", {"portals": {"tutti_ch": {"enabled": True}}})
    assert not is_enabled("tutti", {"portals": {}})
    print("✅ Connector registry")


if __name__ == "__main__":
    test_removed_listing_by_status_code()
    test_redirect_away_from_listing_means_removed()
    test_schema_org_availability()
    test_sold_messages_but_not_seller_prose()
    test_shopify_variant_flags()
    test_shop_feeds_carry_availability()
    test_shopify_check_uses_product_js()
    test_registry_covers_every_portal()
    print("\n✅ All availability tests passed!")
