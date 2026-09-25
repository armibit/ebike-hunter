import sys
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from connectors.ridewill import RidewillConnector


def _make_connector():
    config = {
        "portals": {
            "ridewill": {
                "base_url": "https://www.ridewill.it",
                "category_id": "87",
                "type_id": "7",
                "max_pages": 1,
            }
        }
    }
    return RidewillConnector(config)


CARD_HTML = """
<div class="box-product">
  <a class="box-product__description" href="/p/it/scott-genius-eride-920/123456/">
    Scott Genius eRide 920 - Bosch CX Gen4 - 750Wh - 150mm - Taglia M
  </a>
  <span class="offer-price">4.500,00 &euro;</span>
</div>
"""

CARD_HTML_NO_PRICE = """
<div class="box-product">
  <a class="box-product__description" href="https://www.ridewill.it/p/it/trek-rail-9-7/654321/">
    Trek Rail 9.7 - TQ HPR50
  </a>
</div>
"""


def test_parse_card_extracts_fields_offline():
    connector = _make_connector()
    soup = BeautifulSoup(CARD_HTML, "lxml")
    card = soup.find("div", class_="box-product")

    listing = connector._parse_card(card)

    assert listing is not None
    assert listing["portal"] == "ridewill"
    assert listing["portal_id"] == "123456"
    assert listing["url"] == "https://www.ridewill.it/p/it/scott-genius-eride-920/123456/"
    assert "Scott Genius eRide 920" in listing["title"]
    assert listing["price_raw"] == 4500.0
    assert listing["currency"] == "EUR"


def test_parse_card_handles_absolute_url_and_missing_price():
    connector = _make_connector()
    soup = BeautifulSoup(CARD_HTML_NO_PRICE, "lxml")
    card = soup.find("div", class_="box-product")

    listing = connector._parse_card(card)

    assert listing is not None
    assert listing["portal_id"] == "654321"
    assert listing["url"] == "https://www.ridewill.it/p/it/trek-rail-9-7/654321/"
    assert listing["price_raw"] == 0.0


def test_parse_products_finds_all_cards_in_fragment():
    connector = _make_connector()
    fragment = CARD_HTML + CARD_HTML_NO_PRICE

    listings = connector._parse_products(fragment)

    assert len(listings) == 2
    portal_ids = {l["portal_id"] for l in listings}
    assert portal_ids == {"123456", "654321"}


if __name__ == "__main__":
    test_parse_card_extracts_fields_offline()
    test_parse_card_handles_absolute_url_and_missing_price()
    test_parse_products_finds_all_cards_in_fragment()
    print("\n✅ All Ridewill connector tests passed!")
