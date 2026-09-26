import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from connectors.velomarkt import VelomarktConnector


def _make_connector():
    config = {"portals": {"velomarkt": {"base_url": "https://www.velomarkt.ch"}}}
    return VelomarktConnector(config)


# Real card markup plus a nested "item-caption"/"item-name" structure that
# previously caused the old broad regex selector to match the same card
# multiple times at different nesting levels.
LISTING_HTML = """
<div class="bike-item bg-secondary-lighter">
  <div class="item">
    <div class="item-img"><a class="item-link" href="/en/veloboerse/ebike-scott-strike-920-xl-405027"><img src="x.jpg"></a></div>
    <div class="item-caption">
      <div class="item-name small d-flex">
        <div class="col-11 px-0"><div class="text-truncate">
          <a href="/en/veloboerse/ebike-scott-strike-920-xl-405027" title="eBike SCOTT Strike 920 XL kaufen in St. Gallen">eBike SCOTT Strike 920 XL</a>
        </div></div>
        <div class="col-1 px-0"><a class="item-mark" href="#"><svg></svg></a></div>
      </div>
      <div class="item-description d-flex">
        <div class="col-6 px-0">
          <div class="item-price small">CHF 1'970.-<span class="d-none d-md-inline">VB</span></div>
          <div class="item-location small text-truncate">9524 St. Gallen</div>
        </div>
      </div>
    </div>
  </div>
</div>
"""

TWO_LISTINGS_HTML = LISTING_HTML + LISTING_HTML.replace("405027", "406428").replace(
    "eBike SCOTT Strike 920 XL", "E-Rennrad Simplon Kairo Pmax"
).replace("1'970.-", "2'400.-")


def test_parse_listings_matches_exact_card_only():
    connector = _make_connector()
    listings = connector._parse_listings(LISTING_HTML)

    assert len(listings) == 1, "broad selector must not re-match nested item-* divs as separate cards"


def test_parse_item_extracts_title_price_and_id():
    connector = _make_connector()
    listings = connector._parse_listings(LISTING_HTML)

    listing = listings[0]
    assert listing["portal"] == "velomarkt"
    assert listing["portal_id"] == "405027"
    assert listing["url"] == "https://www.velomarkt.ch/en/veloboerse/ebike-scott-strike-920-xl-405027"
    assert listing["title"] == "eBike SCOTT Strike 920 XL"
    assert listing["price_raw"] == 1970.0
    assert listing["currency"] == "CHF"


def test_parse_listings_no_zero_price_duplicates():
    connector = _make_connector()
    listings = connector._parse_listings(TWO_LISTINGS_HTML)

    assert len(listings) == 2
    ids = {l["portal_id"] for l in listings}
    assert ids == {"405027", "406428"}
    assert all(l["price_raw"] > 0 for l in listings), "no listing should parse to a spurious 0.0 price"


# Real detail-page markup (confirmed live, 2026-09-26, "Specialized S-Works
# Turbo Levo 4"): a loose class_=re.compile("description|details") search
# on the full page hits the "Similar ads" sidebar first — every card there
# is literally class="item-description", but its text is just price + city
# ("CHF 4'999.- 8610 Zurich"), never the real product. The actual
# description sits three DOM levels below an <h2>Description</h2> heading,
# with no stable class/id of its own.
DETAIL_PAGE_HTML = """
<html><body>
<div class="similar-ads">
  <div class="item-description d-flex">CHF 4'999.- 8610 Zurich</div>
  <div class="item-description d-flex">CHF 3'999.- 8404 Zurich</div>
</div>
<div class="col-12 mb-3 mt-sm-3">
  <div class="d-flex align-items-center mb-3">
    <div><h2 class="text-uppercase h3 mb-0">Description</h2></div>
  </div>
  <p><strong>Specialized S-Works Turbo Levo 4 blue 850W 111Nm 9</strong></p>
  Specialized S-Works Turbo Levo 4 850W 111Nm 900Wh Akku<br>
  Verfügbare Grössen: S2 / S3 / S4 / S5<br>
</div>
</body></html>
"""


def test_get_listing_details_reads_real_description_not_similar_ads_sidebar():
    connector = _make_connector()
    connector.get = lambda url, **kwargs: type("R", (), {"text": DETAIL_PAGE_HTML})()

    details = connector.get_listing_details("408475", "https://velomarkt.ch/x")

    assert "900Wh" in details["description_raw"]
    assert "111Nm" in details["description_raw"]
    # Must NOT have grabbed a sidebar card's price/location text.
    assert "8610 Zurich" not in details["description_raw"]
    assert "8404 Zurich" not in details["description_raw"]


if __name__ == "__main__":
    test_parse_listings_matches_exact_card_only()
    test_parse_item_extracts_title_price_and_id()
    test_parse_listings_no_zero_price_duplicates()
    test_get_listing_details_reads_real_description_not_similar_ads_sidebar()
    print("\n✅ All Velomarkt connector tests passed!")
