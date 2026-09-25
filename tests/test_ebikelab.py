import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from connectors.ebikelab import EbikelabConnector


def _make_connector():
    config = {"portals": {"ebikelab": {"base_url": "https://ebikelab.it"}}}
    return EbikelabConnector(config)


# Real Magento card markup from /ebike/usato (li.item.product.product-item).
# The URL has no numeric ID segment before it — trailing "-p<id>-<variant>"
# is the only place an ID-like token appears.
CARD_HTML = """
<li class="item product product-item">
  <div class="product-item-info" id="product-item-info_23761" data-container="product-grid">
    <a href="https://ebikelab.it/giant-trance-x-adv-e-elite-2-usata-tg-l-12-mesi-di-garanzia-p260022-1689"
       class="product photo product-item-photo"><img class="product-image-photo" src="x.jpg"/></a>
    <div class="product details product-item-details">
      <strong class="product name product-item-name">
        <a class="product-item-link"
           href="https://ebikelab.it/giant-trance-x-adv-e-elite-2-usata-tg-l-12-mesi-di-garanzia-p260022-1689">
          GIANT TRANCE X Adv E+Elite 2 Usata tg.L 12 MESI DI GARANZIA
        </a>
      </strong>
      <div class="price-box price-final_price">
        <span class="price-container price-final_price tax weee">
          <span class="price-wrapper" data-price-amount="2499.0000" data-price-type="finalPrice">
            <span class="price">&euro;2.499,00</span>
          </span>
        </span>
      </div>
    </div>
  </div>
</li>
"""


def test_parse_card_extracts_title_id_and_price():
    connector = _make_connector()
    listings = connector._parse_listings(CARD_HTML)

    assert len(listings) == 1
    listing = listings[0]
    assert listing["portal"] == "ebikelab"
    assert listing["portal_id"] == "260022"
    assert listing["title"] == "GIANT TRANCE X Adv E+Elite 2 Usata tg.L 12 MESI DI GARANZIA"
    assert listing["price_raw"] == 2499.0
    assert listing["currency"] == "EUR"


# Real product-page description block — motor brand/torque only appear
# here, never on the category-listing card.
DETAIL_HTML = """
<div class="product attribute description">
  <div class="value" itemprop="description">
    Giant Trance X Advanced E+ Elite 2 &ndash; E-MTB Full Carbon Leggera con
    Motore SyncDrive Pro 85 Nm. La batteria EnergyPak 400.
  </div>
</div>
"""


def test_extract_description_reads_product_attribute_description():
    connector = _make_connector()
    description = connector._extract_description(DETAIL_HTML)

    assert "SyncDrive Pro 85 Nm" in description, "must capture motor spec text so motor detection can match it"


if __name__ == "__main__":
    test_parse_card_extracts_title_id_and_price()
    test_extract_description_reads_product_attribute_description()
    print("\n✅ All Ebikelab connector tests passed!")
