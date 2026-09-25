import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from connectors.tutti import TuttiConnector


def _make_connector():
    config = {
        "portals": {
            "tutti_ch": {
                "base_url": "https://www.tutti.ch",
                "search_queries": [],
                "cantons": ["ti"],
                "max_pages": 1,
            }
        }
    }
    return TuttiConnector(config)


def test_normalize_strips_hyphens_and_case():
    connector = _make_connector()
    assert connector._normalize("E-Bike") == connector._normalize("ebike") == "ebike"
    assert connector._normalize("E-MTB Full") == "emtbfull"


def test_hyphenated_query_matches_unhyphenated_title():
    connector = _make_connector()
    listing = {"title": "Bergamont E-Bike Trailster", "description_raw": ""}
    keywords = [connector._normalize(w) for w in "ebike".split()]
    assert connector._matches_keywords(listing, keywords) is True


def test_unhyphenated_query_matches_hyphenated_title():
    connector = _make_connector()
    listing = {"title": "Trek Rail 9.7 E-MTB full suspension", "description_raw": ""}
    keywords = [connector._normalize(w) for w in "emtb full".split()]
    assert connector._matches_keywords(listing, keywords) is True


def test_missing_keyword_does_not_match():
    connector = _make_connector()
    listing = {"title": "Trek E-MTB Rail 9.7", "description_raw": "biammortizzata"}
    keywords = [connector._normalize(w) for w in "e-mtb full".split()]
    assert connector._matches_keywords(listing, keywords) is False


if __name__ == "__main__":
    test_normalize_strips_hyphens_and_case()
    test_hyphenated_query_matches_unhyphenated_title()
    test_unhyphenated_query_matches_hyphenated_title()
    test_missing_keyword_does_not_match()
    print("\n✅ All Tutti connector tests passed!")
