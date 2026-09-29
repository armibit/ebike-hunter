import html
import logging
import re
from typing import Dict, List, Any, Optional
from .base import BaseConnector, product_image, shopify_variants_available

logger = logging.getLogger(__name__)


class EcyclesShopConnector(BaseConnector):
    """Connector for Ecycles-shop.it (Milano, Shopify shop — 'usato' collection).

    Uses Shopify's public /products.json storefront endpoint, no HTML parsing needed.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__("ecycles_shop", config)
        cfg = config["portals"]["ecycles_shop"]
        self.base_url = cfg["base_url"]
        self.collection = cfg.get("collection", "usato")

    def search(self, limit: int = 50) -> List[Dict[str, Any]]:
        results = []
        url = f"{self.base_url}/collections/{self.collection}/products.json"

        try:
            response = self.get(url, params={"limit": limit})
            data = response.json()
        except Exception as e:
            logger.exception("Error fetching Ecycles-shop products: %s", e)
            return results

        for product in data.get("products", []):
            try:
                listing = self._parse_product(product)
                if listing:
                    results.append(listing)
            except Exception:
                logger.debug("Failed to parse Ecycles-shop product", exc_info=True)
                continue

        return results

    def _parse_product(self, product: Dict[str, Any]) -> Dict[str, Any]:
        variants = product.get("variants", [])
        price_raw = float(variants[0]["price"]) if variants and variants[0].get("price") else 0.0

        body_html = product.get("body_html", "") or ""
        description_raw = re.sub(r"<[^>]+>", " ", body_html)
        description_raw = html.unescape(description_raw)
        description_raw = re.sub(r"\s+", " ", description_raw).strip()

        return {
            "portal": "ecycles_shop",
            "portal_id": str(product.get("id", "")),
            "url": f"{self.base_url}/products/{product.get('handle', '')}",
            "title": product.get("title", ""),
            "description_raw": description_raw,
            "price_raw": price_raw,
            "currency": "EUR",
            "location_raw": "Milano",
            "image_url": product_image(product),
            # Sold-out one-off bikes stay in the collection feed.
            "is_available": shopify_variants_available(variants),
        }

    def check_availability(self, listing_id: str, url: str) -> Optional[bool]:
        return self.shopify_availability(url)

    def get_listing_details(self, listing_id: str, url: str) -> Dict[str, Any]:
        return {}

    def search_all(self) -> List[Dict[str, Any]]:
        results = self.search()
        logger.info("[Ecycles-shop] Found: %d results", len(results))
        return results
