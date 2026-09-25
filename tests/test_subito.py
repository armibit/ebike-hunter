import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from connectors.subito import SubitoConnector


def _make_connector():
    config = {
        "portals": {
            "subito_it": {
                "base_url": "https://www.subito.it",
                "search_queries": [],
                "provinces": ["como"],
            }
        }
    }
    return SubitoConnector(config)


# Real search-results pages carry a page-level Product/AggregateOffer schema
# (summarizing ALL results) alongside real per-listing <article> cards.
PAGE_LEVEL_AGGREGATE_JSON_LD = """
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Product","name":"ebike full",
 "offers":{"@type":"AggregateOffer","lowPrice":1,"highPrice":8499,"priceCurrency":"EUR","offerCount":503}}
</script>
"""

CARD_HTML = """
<article class="index-module_card__-KRtM index-module_responsive__W6Gqj">
  <a class="index-module_link__iSNLk" aria-label="Ebike Haibike Sduro Full seven LT 7.0"
     href="https://www.subito.it/biciclette/ebike-haibike-sduro-full-seven-lt-7-0-milano-651643880.htm">
    <h3>Ebike Haibike Sduro Full seven LT 7.0</h3>
  </a>
  <span>1.650 &euro;</span>
  <span class="caption small book index-module_location__vLPWy">Milano (MI)</span>
</article>
"""

# A wrapper div matching a loose "item"/"card" class substring — must NOT be
# treated as its own card (it ancestors every real card and would otherwise
# resolve to the first listing's link as a spurious duplicate "result").
WRAPPER_DIV = '<div class="ItemListContainer-module__jGGCSW__grid">'

PAGE_HTML = f"<html><body>{PAGE_LEVEL_AGGREGATE_JSON_LD}{WRAPPER_DIV}{CARD_HTML}</div></body></html>"


def test_aggregate_offer_json_ld_is_skipped_not_treated_as_listing():
    connector = _make_connector()

    listings = connector._parse_search_results(PAGE_HTML, "https://www.subito.it/x")

    assert len(listings) == 1
    assert "651643880" in listings[0]["portal_id"]


def test_wrapper_div_is_not_matched_as_a_card():
    connector = _make_connector()

    listings = connector._parse_search_results(PAGE_HTML, "https://www.subito.it/x")

    assert len(listings) == 1, "a page-level wrapper div must not be parsed as its own listing"


def test_parse_card_extracts_title_via_h3_and_real_price():
    connector = _make_connector()
    listings = connector._parse_search_results(PAGE_HTML, "https://www.subito.it/x")

    listing = listings[0]
    assert listing["title"] == "Ebike Haibike Sduro Full seven LT 7.0"
    assert listing["price_raw"] == 1650.0
    assert listing["currency"] == "EUR"


if __name__ == "__main__":
    test_aggregate_offer_json_ld_is_skipped_not_treated_as_listing()
    test_wrapper_div_is_not_matched_as_a_card()
    test_parse_card_extracts_title_via_h3_and_real_price()
    print("\n✅ All Subito connector tests passed!")
