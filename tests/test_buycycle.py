import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from connectors.buycycle import BuycycleConnector


def _make_connector():
    config = {"portals": {"buycycle": {"base_url": "https://buycycle.com", "country_filter": ["CH", "IT"]}}}
    return BuycycleConnector(config)


def test_search_returns_empty_without_network_call():
    # Documented stub (see class docstring): no scriptable search endpoint
    # was found for buycycle.com, so search() must return [] without ever
    # touching the network — it must not raise even though self.get()/post()
    # are never wired up to a real request.
    connector = _make_connector()
    assert connector.search("e-mountainbike") == []


def test_search_all_returns_empty_list():
    connector = _make_connector()
    assert connector.search_all() == []


def test_get_listing_details_returns_empty_dict():
    connector = _make_connector()
    assert connector.get_listing_details("123", "https://buycycle.com/x") == {}


if __name__ == "__main__":
    test_search_returns_empty_without_network_call()
    test_search_all_returns_empty_list()
    test_get_listing_details_returns_empty_dict()
    print("\n✅ All Buycycle connector tests passed!")
