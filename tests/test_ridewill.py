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


# Real detail-page markup (confirmed live, 2026-09-26): the product's own
# spec table lives in a tab at [data-tab-content="descrizione"] — but the
# SAME page also carries a "prodotti correlati" carousel further down whose
# cards reuse class="box-product__description" (the same class real search
# cards use for their title link, see CARD_HTML above). A loose
# class-substring search hits the carousel first and silently returns a
# different, unrelated product's text.
DETAIL_PAGE_HTML = """
<html><body>
<div class="tab-content tab-content--active" data-tab-content="descrizione">
  <div class="product-features">
    <div class="product-features__line">
      <div class="product-features__label">Taglia:</div>
      <div class="product-features__value"> L</div>
    </div>
    <div class="product-features__line">
      <div class="product-features__label">Motore:</div>
      <div class="product-features__value"> Bosch Performance CX Gen4</div>
    </div>
    <div class="product-features__line">
      <div class="product-features__label">Batteria (Wh):</div>
      <div class="product-features__value"> 750</div>
    </div>
  </div>
  Bici usata in ottime condizioni, Bosch Performance CX Gen4, 85 Nm, batteria 750 Wh.
</div>
<div class="related-products">
  <a class="box-product__description" href="/p/it/altro-modello/999999/">
    Hyperion 29'' 120mm 11v Bafang M410 630Wh Grigio Taglia S
  </a>
</div>
</body></html>
"""


def test_get_listing_details_reads_real_tab_not_related_products_carousel():
    connector = _make_connector()
    connector.get = lambda url, **kwargs: type("R", (), {"text": DETAIL_PAGE_HTML})()

    details = connector.get_listing_details("123456", "https://www.ridewill.it/p/it/x/123456/")

    assert "Bosch Performance CX Gen4" in details["description_raw"]
    assert "750" in details["description_raw"]
    # Must NOT have grabbed the unrelated related-product carousel entry.
    assert "Hyperion" not in details["description_raw"]
    assert "Bafang" not in details["description_raw"]


if __name__ == "__main__":
    test_parse_card_extracts_fields_offline()
    test_parse_card_handles_absolute_url_and_missing_price()
    test_parse_products_finds_all_cards_in_fragment()
    test_get_listing_details_reads_real_tab_not_related_products_carousel()
    print("\n✅ All Ridewill connector tests passed!")
