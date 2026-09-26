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


# Real detail-page markup (confirmed live, 2026-09-26, "2022 Focus THRON
# 6.8"): the seller's free-text description sits inside the page's own
# JSON-LD Product schema, wrapped in a top-level "@graph" array (not a bare
# Product object) — and a separate, unrelated <div id="product-
# characteristics"> holds the real structured spec table (motor, battery,
# frame size...), which was never part of any "description"-classed element
# at all (the old selector matched nothing, 0 hits, verified live).
DETAIL_PAGE_HTML = """
<html><body>
<script type="application/ld+json">
{"@context":"https://schema.org","@graph":[
  {"@type":"Product","name":"2022 Focus THRON 6.8",
   "description":"I bought the e-bike new in November 2022. Ridden about 1,700 km.",
   "offers":{"@type":"Offer","priceCurrency":"CHF","price":3200}}
]}
</script>
<div id="product-characteristics">
  <section><h2>Characteristics</h2>
  <ul>
    <li><span>Motor</span><span>Bosch</span></li>
    <li><span>Battery capacity</span><span>625 Wh</span></li>
    <li><span>Frame size</span><span>S-M</span></li>
    <li><span>Mileage</span><span>1900 km</span></li>
    <li><span>Suspension</span><span>Full suspension</span></li>
  </ul>
  </section>
</div>
</body></html>
"""


def test_get_listing_details_combines_json_ld_description_and_characteristics():
    connector = _make_connector()
    connector.get = lambda url, **kwargs: type("R", (), {"text": DETAIL_PAGE_HTML})()

    details = connector.get_listing_details("655543", "https://velocorner.ch/en/ebike/x")

    assert "1,700 km" in details["description_raw"]
    assert "Bosch" in details["description_raw"]
    assert "625 Wh" in details["description_raw"]
    assert "Full suspension" in details["description_raw"]


if __name__ == "__main__":
    test_parse_item_extracts_used_listing()
    test_parse_item_picks_final_price_not_struck_msrp()
    test_parse_listings_skips_new_listings()
    test_get_listing_details_combines_json_ld_description_and_characteristics()
    print("\n✅ All TCS Velocorner connector tests passed!")
