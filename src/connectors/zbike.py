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
        self.max_pages = cfg.get("max_pages", 10)

    def search(self, limit: int = 200) -> List[Dict[str, Any]]:
        results = []
        seen_ids = set()
        url = f"{self.base_url}/wp-json/wc/store/v1/products"

        for page in range(1, self.max_pages + 1):
            try:
                response = self.get(url, params={"category": self.category_id, "per_page": 50, "page": page})
                products = response.json()
            except Exception as e:
                logger.error("Error fetching Z-Bike products (page %d): %s", page, e)
                break

            if not products:
                break

            new_count = 0
            for product in products:
                try:
                    listing = self._parse_product(product)
                except Exception:
                    logger.debug("Failed to parse Z-Bike product", exc_info=True)
                    continue
                if not listing or listing["portal_id"] in seen_ids:
                    continue
                seen_ids.add(listing["portal_id"])
                results.append(listing)
                new_count += 1
                if len(results) >= limit:
                    return results

            total_pages = int(response.headers.get("X-WP-TotalPages", page) or page)
            logger.info(
                "[Z-Bike] page %d/%d — %d new match(es), %d total so far",
                page, total_pages, new_count, len(results),
            )

            if page >= total_pages or new_count == 0:
                break

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
