import logging
from typing import Dict, List, Any
from .base import BaseConnector

logger = logging.getLogger(__name__)


class BuycycleConnector(BaseConnector):
    """
    Connector for Buycycle.com (certified used bikes).

    Stub: buycycle.com is a client-rendered Next.js app — the initial HTML
    carries no listing data and no inline __NEXT_DATA__/API keys, so any real
    search happens via requests the JS makes after load (confirmed: no
    static JSON endpoint or Algolia app id/key found anywhere in the
    server-rendered page or its script tags). Reverse-engineering that call
    needs a live browser network capture (devtools Network tab, or a
    Playwright session recording requests) to see the actual endpoint, auth
    header and query shape — nothing scriptable from a plain HTTP client.
    Skipped automatically; check manually via the dashboard link instead.

    To implement for real: open buycycle.com in a browser with devtools open,
    search/filter for e-MTBs, filter the Network tab to Fetch/XHR, and find
    the request that returns the listing results (likely to an Algolia
    *.algolia.net host, or an api.buycycle.com/graphql endpoint). Copy that
    request's URL, method, and headers (incl. any API key) here.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__("buycycle", config)
        self.base_url = config["portals"]["buycycle"]["base_url"]
        self.countries = config["portals"]["buycycle"].get("country_filter", ["CH", "IT"])

    def search(self, query: str = "e-mountainbike", **kwargs) -> List[Dict[str, Any]]:
        logger.info("Buycycle skipping (stub — no scriptable search endpoint found; needs a browser network capture, see class docstring)")
        return []

    def get_listing_details(self, listing_id: str, url: str) -> Dict[str, Any]:
        """Fetch detailed listing information."""
        return {}

    def search_all(self) -> List[Dict[str, Any]]:
        """Run configured search."""
        return self.search()
