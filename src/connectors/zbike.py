import logging
from typing import Dict, List, Any
from .base import BaseConnector

logger = logging.getLogger(__name__)


class ZbikeConnector(BaseConnector):
    """Connector for Z-Bike.ch (Ticino WooCommerce shop — 'usato' category).

    Uses the public WooCommerce Store REST API instead of HTML scraping.
    Note: the API's `category` filter needs the numeric category ID, not the
    slug (the slug silently returns an empty list) — 528 is "usato".
    Prices come back as integer strings scaled by currency_minor_unit
    (e.g. "140000" with minor_unit 2 == CHF 1'400.00).
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__("zbike", config)
        cfg = config["portals"]["zbike"]
        self.base_url = cfg["base_url"]
        self.category_id = str(cfg.get("category_id", "528"))

    def search(self, limit: int = 50) -> List[Dict[str, Any]]:
        results = []
        url = f"{self.base_url}/wp-json/wc/store/v1/products"

        try:
            response = self.get(url, params={"category": self.category_id, "per_page": limit})
            products = response.json()
        except Exception as e:
            logger.error("Error fetching Z-Bike products: %s", e)
            return results

        for product in products:
            try:
                listing = self._parse_product(product)
                if listing:
                    results.append(listing)
            except Exception:
                logger.debug("Failed to parse Z-Bike product", exc_info=True)
                continue

        return results

    def _parse_product(self, product: Dict[str, Any]) -> Dict[str, Any]:
        prices = product.get("prices", {})
        minor_unit = int(prices.get("currency_minor_unit", 2))
        price_raw = float(prices.get("price", 0) or 0) / (10 ** minor_unit)

        return {
            "portal": "zbike",
            "portal_id": str(product.get("id", "")),
            "url": product.get("permalink", ""),
            "title": product.get("name", ""),
            "description_raw": product.get("summary", "") or "",
            "price_raw": price_raw,
            "currency": prices.get("currency_code", "CHF"),
            "location_raw": "Mendrisio, Ticino",
        }

    def get_listing_details(self, listing_id: str, url: str) -> Dict[str, Any]:
        return {}

    def search_all(self) -> List[Dict[str, Any]]:
        results = self.search()
        logger.info("[Z-Bike] Found: %d results", len(results))
        return results
