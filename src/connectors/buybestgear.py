import logging
import re
from typing import Dict, List, Any, Optional
from bs4 import BeautifulSoup
from .base import BaseConnector, product_image, shopify_variants_available

logger = logging.getLogger(__name__)


class BuybestgearConnector(BaseConnector):
    """Connector for Buybestgear.com (Shopify storefront).

    Unlike every other portal here, Buybestgear sells brand-new e-bikes
    from budget/direct-to-consumer brands (Lankeleisi, Vakole, CMACEWHEEL,
    Dukawey...) rather than used/private-sale listings — added on request
    as a source of cheap new stock, not because it fits the "used
    classifieds" pattern of the rest of this project. The usual budget
    hard filter (hardware_requirements/hard_max_price in config.yaml)
    already keeps out anything over budget, same as every other portal.

    Unlike upway.py, no separate detail-page fetch is needed here:
    products.json's body_html already contains the real spec prose
    (motor torque, battery Wh) written out — confirmed against the live
    product page for the Lankeleisi MG600 Pro.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__("buybestgear", config)
        self.base_url = config["portals"]["buybestgear"]["base_url"]
        self.collection = config["portals"]["buybestgear"].get("collection", "full-suspension-e-bikes")
        self.max_pages = config["portals"]["buybestgear"].get("max_pages", 5)

    def search(self, limit: int = 500) -> List[Dict[str, Any]]:
        """Fetch e-bikes from a Buybestgear collection via Shopify's JSON endpoint, paginating."""
        results = []
        seen_ids = set()
        url = f"{self.base_url}/collections/{self.collection}/products.json"

        for page in range(1, self.max_pages + 1):
            try:
                response = self.get(url, params={"limit": 250, "page": page})
                data = response.json()
            except Exception as e:
                logger.exception("Error searching Buybestgear: %s", e)
                break

            products = data.get("products", [])
            if not products:
                break

            new_count = 0
            for product in products:
                listing = self._parse_product(product)
                if not listing or listing["portal_id"] in seen_ids:
                    continue
                seen_ids.add(listing["portal_id"])
                results.append(listing)
                new_count += 1
                if len(results) >= limit:
                    return results

            logger.info(
                "[Buybestgear] page %d/%d — %d new match(es), %d total so far",
                page, self.max_pages, new_count, len(results),
            )

            if len(products) < 250 or new_count == 0:
                break

        return results

    def _parse_product(self, product: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Convert a Shopify products.json product into our raw listing format."""
        try:
            handle = product.get("handle")
            title = product.get("title", "")
            if not handle or not title:
                return None

            variants = product.get("variants", [])
            price_raw = 0.0
            if variants:
                try:
                    price_raw = min(float(v["price"]) for v in variants if v.get("price"))
                except ValueError:
                    pass

            body_text = BeautifulSoup(product.get("body_html", "") or "", "lxml").get_text(" ", strip=True)
            # Human-readable tags carry a few extra hints (e.g. "full suspension",
            # "torque sensor") — skip machine-readable "key:value"/bucketed facet
            # tags like "50-60nm" or "600-800wh", which are ranges, not real values.
            readable_tags = [t for t in product.get("tags", []) if ":" not in t and not re.match(r"^[\d]", t)]
            description_raw = " ".join([body_text] + readable_tags)

            return {
                "portal": "buybestgear",
                "portal_id": str(product.get("id") or handle),
                "url": f"{self.base_url}/products/{handle}",
                "title": title,
                "description_raw": description_raw,
                "price_raw": price_raw,
                # Confirmed against the live storefront (banner pricing, no CHF
                # symbol anywhere on-page) — the shop's base currency is EUR.
                "currency": "EUR",
                "location_raw": "Europe",
                "image_url": product_image(product),
                "is_available": shopify_variants_available(variants),
            }
        except Exception:
            logger.debug("Failed to parse Buybestgear product", exc_info=True)
            return None

    def check_availability(self, listing_id: str, url: str) -> Optional[bool]:
        return self.shopify_availability(url)

    def get_listing_details(self, listing_id: str, url: str) -> Dict[str, Any]:
        """No-op — see class docstring: body_html already has the real specs."""
        return {}

    def search_all(self) -> List[Dict[str, Any]]:
        """Search the configured collection (full-suspension e-bikes by default)."""
        results = self.search()
        logger.info("[Buybestgear] Found: %d results", len(results))
        return results
