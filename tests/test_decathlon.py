import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from connectors.decathlon import DecathlonConnector


def _make_connector():
    config = {"portals": {"decathlon": {"base_url": "https://www.decathlon.ch/search"}}}
    return DecathlonConnector(config)


def test_search_returns_empty_without_network_call():
    # Documented stub (see class docstring): decathlon.ch is behind a
    # Cloudflare Turnstile challenge this connector can't pass, so search()
    # must return [] without ever touching the network.
    connector = _make_connector()
    assert connector.search() == []


def test_search_all_returns_empty_list():
    connector = _make_connector()
    assert connector.search_all() == []


def test_get_listing_details_returns_empty_dict():
    connector = _make_connector()
    assert connector.get_listing_details("123", "https://www.decathlon.ch/x") == {}


if __name__ == "__main__":
    test_search_returns_empty_without_network_call()
    test_search_all_returns_empty_list()
    test_get_listing_details_returns_empty_dict()
    print("\n✅ All Decathlon connector tests passed!")
