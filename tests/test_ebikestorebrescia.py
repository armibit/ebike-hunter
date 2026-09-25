import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from connectors.ebikestorebrescia import EbikestorebresciaConnector


def _make_connector():
    config = {"portals": {"ebikestorebrescia": {"base_url": "https://ebikestore.shop"}}}
    return EbikestorebresciaConnector(config)


# Real PrestaShop card markup from /20-usato-certificato — price uses
# Italian formatting (dot thousands separator, comma decimal).
CARD_HTML = """
<article class="product-miniature js-product-miniature" data-id-product="4577" itemscope itemtype="http://schema.org/Product">
  <div class="innovatoryProduct-container item">
    <div class="innovatory-product-description">
      <h2 class="h2 productName" itemprop="name">
        <a href="https://ebikestore.shop/usato-certificato/4577-22221-haibike-alltrail-4-usato.html">Haibike AllTrail 4 (Usato)</a>
      </h2>
      <div class="innovatory-product-price-and-shipping">
        <span itemprop="price" class="price">2.049,18 &euro;</span>
      </div>
    </div>
  </div>
</article>
"""


def test_parse_card_extracts_title_id_and_price():
    connector = _make_connector()
    listings = connector._parse_listings(CARD_HTML)

    assert len(listings) == 1
    listing = listings[0]
    assert listing["portal"] == "ebikestorebrescia"
    assert listing["portal_id"] == "4577"
    assert listing["title"] == "Haibike AllTrail 4 (Usato)"
    assert listing["price_raw"] == 2049.18, "must parse Italian dot-thousands/comma-decimal price format"
    assert listing["currency"] == "EUR"


# Real product-page spec table — motor brand only appears here, never on
# the category-listing card.
DETAIL_HTML = """
<div id="description">
  <table>
    <tr><td>Marca</td><td>Haibike</td></tr>
    <tr><td>Motore</td><td>Yamaha PW-X3 85Nm</td></tr>
  </table>
</div>
"""


def test_extract_description_reads_description_tab():
    connector = _make_connector()
    description = connector._extract_description(DETAIL_HTML)

    assert "Yamaha PW-X3" in description, "must capture motor spec text so motor detection can match it"


if __name__ == "__main__":
    test_parse_card_extracts_title_id_and_price()
    test_extract_description_reads_description_tab()
    print("\n✅ All Ebikestore Brescia connector tests passed!")
