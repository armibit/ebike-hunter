import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from connectors.godspeed import GodspeedConnector


def _make_connector():
    config = {"portals": {"godspeed": {"base_url": "https://www.godspeed.ch"}}}
    return GodspeedConnector(config)


# Real .prod-card markup from /it/e-bikes/occasioni/ — price uses a curly
# apostrophe as thousands separator (CHF 4'599.00), and the visible title
# doesn't repeat the brand (brand lives in a separate .prod-card__brand span).
CARD_HTML = """
<div class="prod-card">
  <span class="prod-card__badge">-47%</span>
  <span class="prod-card__brand"> <strong>Rocky Mountain</strong></span>
  <div class="prod-card__img-wrapper">
    <a href="https://www.godspeed.ch/it/rocky-mountain-instinct-powerplay-alloy-130435844.html"
       class="prod-card__img-link" aria-label="Rocky Mountain Instinct Powerplay Alloy 70 blue/grey">
      <figure></figure>
    </a>
  </div>
  <div class="padding-sm text-center">
    <h1 class="text-base margin-bottom-xs">
      <a href="https://www.godspeed.ch/it/rocky-mountain-instinct-powerplay-alloy-130435844.html"
         class="product-card__title">Instinct Powerplay Alloy 70 blue/grey</a>
    </h1>
    <div class="margin-bottom-xs">
      <ins class="prod-card__price"> CHF 4&#039;599.00</ins>
      <del class="prod-card__old-price">CHF 8&#039;699.00</del>
    </div>
  </div>
</div>
"""


def test_parse_card_extracts_id_title_with_brand_and_price():
    connector = _make_connector()
    listings = connector._parse_listings(CARD_HTML)

    assert len(listings) == 1
    listing = listings[0]
    assert listing["portal"] == "godspeed"
    assert listing["portal_id"] == "130435844"
    assert listing["title"] == "Rocky Mountain Instinct Powerplay Alloy 70 blue/grey"
    assert listing["price_raw"] == 4599.0, "must use the discounted price (ins), and strip the ' thousands separator"
    assert listing["currency"] == "CHF"


# Real product-detail spec table from the first .js-tabs__panel — motor
# brand/torque only appear here, never on the listing card itself.
DETAIL_HTML = """
<section class="padding-top-lg max-width-lg js-tabs__panel">
  <div class="text-component margin-bottom-md">
    <table>
      <tr><td>Telaio</td><td>FORM Alluminio</td></tr>
      <tr><td>Sistema di trasmissione</td>
          <td>Dyname 4.0 Mountain Bike Drive | Potenza nominale 250w | 108Nm</td></tr>
      <tr><td>Batteria</td><td>720 Wh Litio-Ione integrata rimovibile</td></tr>
    </table>
  </div>
</section>
<section class="padding-top-lg max-width-lg js-tabs__panel">
  <p>0 stelle basate su 0 recensioni</p>
</section>
"""


def test_extract_description_uses_first_tab_panel_only():
    connector = _make_connector()
    description = connector._extract_description(DETAIL_HTML)

    assert "Dyname 4.0" in description, "must capture the motor spec row so motor detection can match it"
    assert "recensioni" not in description, "must not pull in the unrelated reviews panel"


if __name__ == "__main__":
    test_parse_card_extracts_id_title_with_brand_and_price()
    test_extract_description_uses_first_tab_panel_only()
    print("\n✅ All Godspeed connector tests passed!")
