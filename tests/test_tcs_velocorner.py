import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from connectors.tcs_velocorner import TcsVelocornerConnector


def _make_connector():
    config = {
        "portals": {
            "tcs_velocorner": {
                "base_url": "https://velocorner.ch",
                "category_path": "/en/buy-e-bike/mountainbike/fully",
            }
        }
    }
    return TcsVelocornerConnector(config)


# Real product-card layout: an optional struck-through MSRP span followed by
# the real, final-price span in the same footer div — only the used/occasion
# listing (slug starting "used-") should be kept; a "new-" one must be
# dropped, since this connector only targets the used market.
USED_CARD_HTML = """
<article class="product-card">
  <a class="product-card__content-header" href="/en/ebike/used-cube-stereo-hybrid-140-88421" title="Cube Stereo Hybrid 140">Cube Stereo Hybrid 140</a>
  <span class="product-card__location">Zürich</span>
  <footer class="product-card__content-footer">
    <div>
      <span>CHF 3'200.-</span>
      <span>CHF 2'450.-</span>
    </div>
  </footer>
</article>
"""

NEW_CARD_HTML = """
<article class="product-card">
  <a class="product-card__content-header" href="/en/ebike/new-cube-stereo-hybrid-140-99001" title="Cube Stereo Hybrid 140 (new)">Cube Stereo Hybrid 140 (new)</a>
  <footer class="product-card__content-footer">
    <div><span>CHF 4'500.-</span></div>
  </footer>
</article>
"""


def test_parse_item_extracts_used_listing():
    connector = _make_connector()
    listing = connector._parse_listings(USED_CARD_HTML)

    assert len(listing) == 1
    item = listing[0]
    assert item["portal"] == "tcs_velocorner"
    assert item["portal_id"] == "88421"
    assert item["url"] == "https://velocorner.ch/en/ebike/used-cube-stereo-hybrid-140-88421"
    assert item["title"] == "Cube Stereo Hybrid 140"
    assert item["location_raw"] == "Zürich"
    assert item["currency"] == "CHF"


def test_parse_item_picks_final_price_not_struck_msrp():
    connector = _make_connector()
    listing = connector._parse_listings(USED_CARD_HTML)

    assert listing[0]["price_raw"] == 2450.0


def test_parse_listings_skips_new_listings():
    connector = _make_connector()
    listing = connector._parse_listings(NEW_CARD_HTML)

    assert listing == [], "a 'new-' slug must be dropped — this connector only targets used bikes"


if __name__ == "__main__":
    test_parse_item_extracts_used_listing()
    test_parse_item_picks_final_price_not_struck_msrp()
    test_parse_listings_skips_new_listings()
    print("\n✅ All TCS Velocorner connector tests passed!")
