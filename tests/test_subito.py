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


# Real detail-page markup (confirmed live, 2026-09-26, listing 659597935):
# the visible description sits in a <p> — not a <div>, which get_listing_
# details() used to require — whose CSS-module class ends in "description",
# right after an <h2> whose class ends in "description-title" (a substring-
# only match would grab that heading's "Descrizione" text instead). The
# page's own JSON-LD Product schema separately carries the same full text.
DETAIL_PAGE_HTML = """
<html><body>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Product","name":"CUBE Stereo Hybrid 140 HPC SLX 750",
 "description":"taglia M\\n\\nebike con 7000 km ma in ottimo stato\\n\\nSpecifiche:\\n\\nMotore Bosch Performance CX Gen4\\nCoppia massima 85 Nm\\nBatteria integrata Bosch PowerTube 750 Wh",
 "offers":{"@type":"Offer","priceCurrency":"EUR","price":2499}}
</script>
<h2 class="headline-6 index-module__IqE8Fa__description-title">Descrizione</h2>
<p class="body-text book index-module__IqE8Fa__description">taglia M

ebike con 7000 km ma in ottimo stato

Specifiche:

Motore Bosch Performance CX Gen4
Coppia massima 85 Nm
Batteria integrata Bosch PowerTube 750 Wh</p>
</body></html>
"""

# Same page but with the JSON-LD script removed, to exercise the CSS-class
# fallback path on its own.
DETAIL_PAGE_HTML_NO_JSON_LD = """
<html><body>
<h2 class="headline-6 index-module__IqE8Fa__description-title">Descrizione</h2>
<p class="body-text book index-module__IqE8Fa__description">taglia M

Specifiche: Motore Bosch Performance CX Gen4, Coppia massima 85 Nm</p>
</body></html>
"""


def test_get_listing_details_reads_full_description_from_json_ld():
    connector = _make_connector()
    connector.get = lambda url, **kwargs: type("R", (), {"text": DETAIL_PAGE_HTML})()

    details = connector.get_listing_details("659597935", "https://www.subito.it/x")

    assert "Motore Bosch Performance CX Gen4" in details["description_raw"]
    assert "Coppia massima 85 Nm" in details["description_raw"]
    assert "Batteria integrata Bosch PowerTube 750 Wh" in details["description_raw"]


def test_get_listing_details_falls_back_to_description_class_not_title():
    connector = _make_connector()
    connector.get = lambda url, **kwargs: type("R", (), {"text": DETAIL_PAGE_HTML_NO_JSON_LD})()

    details = connector.get_listing_details("659597935", "https://www.subito.it/x")

    assert "Motore Bosch Performance CX Gen4" in details["description_raw"]
    # Must not have grabbed the "description-title" heading instead.
    assert details["description_raw"].strip() != "Descrizione"


def test_search_all_covers_every_search_path_once_per_listing():
    # search_paths lets the scan reach beyond Lombardia (e.g. the Verbano,
    # 30–50 km from Lugano); a listing surfacing under two queries or paths
    # is only processed once.
    connector = SubitoConnector({"portals": {"subito_it": {
        "base_url": "https://www.subito.it",
        "search_queries": ["ebike full", "turbo levo"],
        "search_paths": ["/annunci-lombardia/vendita/biciclette",
                         "/annunci-piemonte/vendita/biciclette/verbano-cusio-ossola"],
    }}})
    requested_urls = []

    def fake_get(url, params=None, **kwargs):
        requested_urls.append(url)
        return type("R", (), {"text": "", "url": url})()

    connector.get = fake_get
    calls = []

    def fake_search(query, search_path):
        calls.append((search_path, query))
        # "shared" shows up under every query and path; the other id is per path.
        return [{"portal_id": "shared"}, {"portal_id": search_path.rsplit("/", 1)[-1]}]

    connector.search = fake_search
    results = connector.search_all()

    assert len(calls) == 4
    assert {path for path, _ in calls} == set(connector.search_paths)
    assert sorted(r["portal_id"] for r in results) == ["biciclette", "shared", "verbano-cusio-ossola"]


def test_search_uses_configured_path():
    connector = _make_connector()
    urls = []
    connector.get = lambda url, params=None, **kwargs: urls.append(url) or type("R", (), {"text": "", "url": url})()

    connector.search("ebike", search_path="/annunci-piemonte/vendita/biciclette/verbano-cusio-ossola/")

    assert urls == ["https://www.subito.it/annunci-piemonte/vendita/biciclette/verbano-cusio-ossola"]


def test_default_search_path_is_lombardia():
    assert _make_connector().search_paths == ["/annunci-lombardia/vendita/biciclette"]


def test_gone_listing_410_logs_warning_without_traceback(caplog):
    from curl_cffi.requests.exceptions import HTTPError

    connector = _make_connector()
    resp = type("R", (), {"status_code": 410, "headers": {}})()
    connector.session = type("S", (), {"headers": {}, "get": lambda self, *a, **k: resp})()
    resp.raise_for_status = lambda: (_ for _ in ()).throw(HTTPError("HTTP Error 410: ", 0, resp))
    connector._rate_limit = lambda: None

    assert connector.get_listing_details("1", "https://www.subito.it/x") == {}
    assert all(r.levelname != "ERROR" and not r.exc_info for r in caplog.records)


if __name__ == "__main__":
    test_aggregate_offer_json_ld_is_skipped_not_treated_as_listing()
    test_wrapper_div_is_not_matched_as_a_card()
    test_parse_card_extracts_title_via_h3_and_real_price()
    test_get_listing_details_reads_full_description_from_json_ld()
    test_get_listing_details_falls_back_to_description_class_not_title()
    test_search_all_covers_every_search_path_once_per_listing()
    test_search_uses_configured_path()
    test_default_search_path_is_lombardia()
    print("\n✅ All Subito connector tests passed!")
