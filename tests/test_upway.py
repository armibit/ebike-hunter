import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bs4 import BeautifulSoup
from connectors.upway import UpwayConnector


def _make_connector():
    config = {
        "portals": {
            "upway": {
                "base_url": "https://upway.ch",
                "shop_domain": "upway-switzerland.myshopify.com",
                "brands": ["cube"],
            }
        }
    }
    return UpwayConnector(config)


# Representative Shopify products.json product: two variants (sizes), a
# machine-readable "key:value" facet tag that should be dropped, and a
# human-readable tag that should be kept since it carries motor/spec info
# the body text often omits.
PRODUCT = {
    "id": 8675309,
    "handle": "cube-stereo-hybrid-140-hpc",
    "title": "Cube Stereo Hybrid 140 HPC SLT 750",
    "body_html": "<p>Full suspension e-MTB, <strong>Bosch Performance Line CX</strong>, 750Wh.</p>",
    "tags": ["motor:bosch-cx", "Bosch Performance Line CX", "condition:refurbished"],
    "variants": [
        {"id": 1, "price": "3200.00"},
        {"id": 2, "price": "2990.00"},
    ],
}


def test_parse_product_extracts_core_fields():
    connector = _make_connector()
    listing = connector._parse_product(PRODUCT)

    assert listing["portal"] == "upway"
    assert listing["portal_id"] == "8675309"
    assert listing["url"] == "https://upway.ch/products/cube-stereo-hybrid-140-hpc"
    assert listing["title"] == "Cube Stereo Hybrid 140 HPC SLT 750"
    assert listing["currency"] == "CHF"


def test_parse_product_picks_lowest_variant_price():
    connector = _make_connector()
    listing = connector._parse_product(PRODUCT)

    assert listing["price_raw"] == 2990.0


def test_parse_product_leaves_description_empty_to_force_detail_fetch():
    # products.json's body_html/tags never carry the battery/motor/frame
    # spec table at all (it's server-rendered on the product page only) —
    # description_raw MUST be left empty here so run.py's own "still
    # missing a description" check calls get_listing_details() for every
    # Upway listing, which is the only place that data actually comes from.
    connector = _make_connector()
    listing = connector._parse_product(PRODUCT)
    assert listing["description_raw"] == ""


# Minimal reproduction of Upway's real product-page markup: an <h2> heading
# followed by a sibling <div> holding the content, both inside a shared
# wrapper <div> — real spec values (battery Wh, motor torque Nm, brand)
# confirmed against the live page for https://upway.ch/products/
# cube-touring-hybrid-pro-625-rk3cn0.
PRODUCT_PAGE_HTML = """
<div class="px-5 py-12">
  <div class="max-w-[1440px]">
    <div>
      <h2>Warum wir es lieben</h2>
      <div>Dieses vielseitige Trekking E-Bike vereint Komfort und Sicherheit.</div>
    </div>
  </div>
</div>
<div class="px-5 py-12 bg-secondary-lighter">
  <div class="max-w-[1440px]">
    <div>
      <h2>Spezifikationen</h2>
      <div class="flex flex-wrap">
        <div>
          <h3>Elektrisch</h3>
          <div>
            <h4>Batterie</h4>
            <p><span>Batteriekapazität<!-- -->:</span> <!-- -->625 Wh</p>
          </div>
          <div>
            <h4>Motor</h4>
            <p><span>Marke<!-- -->:</span> <!-- -->Bosch</p>
            <p><span>Modell<!-- -->:</span> <!-- -->Performance Line</p>
            <p><span>Drehmoment Motor<!-- -->:</span> <!-- -->75 Nm</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>
"""


def test_section_text_extracts_spec_table_with_real_values():
    soup = BeautifulSoup(PRODUCT_PAGE_HTML, "lxml")
    text = UpwayConnector._section_text(soup, "Spezifikationen")

    assert "625 Wh" in text
    assert "75 Nm" in text
    assert "Bosch" in text
    assert "Performance Line" in text
    # HTML comments (React hydration markers) must not leak into the text
    assert "<!--" not in text


def test_section_text_extracts_marketing_blurb():
    soup = BeautifulSoup(PRODUCT_PAGE_HTML, "lxml")
    text = UpwayConnector._section_text(soup, "Warum wir es lieben")
    assert "Trekking E-Bike" in text


def test_section_text_returns_empty_for_missing_heading():
    soup = BeautifulSoup(PRODUCT_PAGE_HTML, "lxml")
    assert UpwayConnector._section_text(soup, "Does Not Exist") == ""


def test_get_listing_details_combines_blurb_and_spec_table():
    connector = _make_connector()

    class FakeResponse:
        text = PRODUCT_PAGE_HTML

    connector.get = lambda url, **kwargs: FakeResponse()

    details = connector.get_listing_details("8675309", "https://upway.ch/products/x")

    assert "625 Wh" in details["description_raw"]
    assert "75 Nm" in details["description_raw"]
    assert "Trekking E-Bike" in details["description_raw"]


def test_get_listing_details_returns_empty_dict_on_request_failure():
    connector = _make_connector()

    def _raise(url, **kwargs):
        raise ConnectionError("boom")

    connector.get = _raise

    assert connector.get_listing_details("8675309", "https://upway.ch/products/x") == {}


def test_parse_product_returns_none_without_handle_or_title():
    connector = _make_connector()
    assert connector._parse_product({"title": "No handle"}) is None
    assert connector._parse_product({"handle": "no-title"}) is None


def test_parse_product_defaults_price_to_zero_without_variants():
    connector = _make_connector()
    listing = connector._parse_product({"handle": "x", "title": "X", "variants": []})
    assert listing["price_raw"] == 0.0


if __name__ == "__main__":
    test_parse_product_extracts_core_fields()
    test_parse_product_picks_lowest_variant_price()
    test_parse_product_leaves_description_empty_to_force_detail_fetch()
    test_parse_product_returns_none_without_handle_or_title()
    test_parse_product_defaults_price_to_zero_without_variants()
    test_section_text_extracts_spec_table_with_real_values()
    test_section_text_extracts_marketing_blurb()
    test_section_text_returns_empty_for_missing_heading()
    test_get_listing_details_combines_blurb_and_spec_table()
    test_get_listing_details_returns_empty_dict_on_request_failure()
    print("\n✅ All Upway connector tests passed!")
