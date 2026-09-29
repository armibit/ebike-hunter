import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from connectors.base import product_image
from connectors.buybestgear import BuybestgearConnector
from connectors.ecycles_shop import EcyclesShopConnector
from connectors.zbike import ZbikeConnector

from utils.config import load_config


def test_product_image_handles_absolute_relative_and_missing():
    assert product_image({"images": [{"src": "https://a/x.jpg"}]}) == "https://a/x.jpg"
    assert product_image({"images": [{"src": "//cdn.shopify.com/x.jpg"}]}) == "https://cdn.shopify.com/x.jpg"
    assert product_image({"images": []}) is None
    assert product_image({}) is None


def test_shop_parsers_fill_image_url():
    config = load_config()
    shopify = {"id": 1, "handle": "h", "title": "T", "variants": [{"price": "100"}],
               "images": [{"src": "https://cdn/x.jpg"}]}
    woo = {"id": 1, "name": "T", "permalink": "https://z/p", "prices": {"price": "100"},
           "images": [{"src": "https://z/x.jpg"}]}
    assert EcyclesShopConnector(config)._parse_product(shopify)["image_url"] == "https://cdn/x.jpg"
    assert BuybestgearConnector(config)._parse_product(shopify)["image_url"] == "https://cdn/x.jpg"
    assert ZbikeConnector(config)._parse_product(woo)["image_url"] == "https://z/x.jpg"


def test_card_shops_skip_logo_and_pick_product_image():
    from bs4 import BeautifulSoup
    from connectors.ridewill import RidewillConnector

    card = BeautifulSoup(
        '<div><img src="https://img.ridewill.it/public/imgmarche/medium/logo.webp">'
        '<img src="https://img.ridewill.it/public/imgprod2021/medium/bike.webp">'
        '<a class="box-product__description" href="/p/it/x/123/">Bike</a></div>', "lxml").div
    assert RidewillConnector(load_config())._parse_card(card)["image_url"].endswith("imgprod2021/medium/bike.webp")
