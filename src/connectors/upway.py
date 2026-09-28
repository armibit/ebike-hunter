import logging
import re
from typing import Dict, List, Any, Optional
from bs4 import BeautifulSoup
from .base import BaseConnector, shopify_variants_available

logger = logging.getLogger(__name__)


class UpwayConnector(BaseConnector):
    """Connector for Upway.ch (refurbished e-bikes).

    upway.ch is a Shopify Hydrogen storefront (headless React Router app) —
    its collection pages only server-render the first ~24 products and load
    the rest through a client-side promise that never issues a plain,
    replayable HTTP request, so scraping the rendered HTML caps out at 24
    per brand regardless of pagination. The underlying shop still exposes
    Shopify's classic JSON endpoint on its *.myshopify.com domain though
    (confirmed live: upway-switzerland.myshopify.com), which returns the
    full, structured product list per collection in one request.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__("upway", config)
        self.base_url = config["portals"]["upway"]["base_url"]
        self.shop_domain = config["portals"]["upway"].get(
            "shop_domain", "upway-switzerland.myshopify.com"
        )
        self.brands = config["portals"]["upway"].get("brands", ["cube", "lapierre", "ghost", "haibike"])
        self.max_pages = config["portals"]["upway"].get("max_pages", 5)

    def search(self, brand: str = "", limit: int = 500) -> List[Dict[str, Any]]:
        """Fetch e-bikes from an Upway collection via Shopify's JSON endpoint, paginating."""
        results = []
        seen_ids = set()
        collection = brand.lower() if brand else "all"
        url = f"https://{self.shop_domain}/collections/{collection}/products.json"

        for page in range(1, self.max_pages + 1):
            try:
                response = self.get(url, params={"limit": 250, "page": page})
                data = response.json()
            except Exception as e:
                logger.exception("Error searching Upway brand %s: %s", brand, e)
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
                "[Upway] %s page %d/%d — %d new match(es), %d total so far",
                collection, page, self.max_pages, new_count, len(results),
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

            return {
                "portal": "upway",
                "portal_id": str(product.get("id") or handle),
                "url": f"{self.base_url}/products/{handle}",
                "title": title,
                # Left empty on purpose. products.json's body_html is only
                # the marketing blurb ("Warum wir es lieben") — the actual
                # battery/motor/frame spec table (Batteriekapazität,
                # Drehmoment Motor, Herstellergröße...) is server-rendered
                # on the product page itself and never appears anywhere in
                # this JSON feed. Leaving this empty makes run.py's own
                # "still missing a description" check call
                # get_listing_details() below for every listing, which
                # fetches that page and supplies the real specs.
                "description_raw": "",
                "price_raw": price_raw,
                "currency": "CHF",
                "location_raw": "Switzerland",
                # Sold-out one-off bikes stay in the collection feed.
                "is_available": shopify_variants_available(variants),
                "image_url": ((product.get("images") or [{}])[0] or {}).get("src"),
            }
        except Exception:
            logger.debug("Failed to parse Upway product", exc_info=True)
            return None

    @staticmethod
    def _section_text(soup: BeautifulSoup, heading: str) -> str:
        """Text of the section under an <h2> with this exact heading —
        Upway renders each spec/blurb block as <h2>Heading</h2> followed by
        a sibling <div> inside a shared wrapper <div>, so two levels up from
        the heading covers the whole block, heading included."""
        for h2 in soup.find_all("h2"):
            if h2.get_text(strip=True) == heading:
                container = h2.find_parent("div")
                if container and container.parent:
                    container = container.parent
                return container.get_text(" ", strip=True)
        return ""

    def check_availability(self, listing_id: str, url: str) -> Optional[bool]:
        return self.shopify_availability(url)

    def get_listing_details(self, listing_id: str, url: str) -> Dict[str, Any]:
        """Fetch the product page for the structured spec table and the
        marketing blurb — both server-rendered HTML, no JS execution
        needed (confirmed: present in a plain GET's response body), but
        absent from products.json entirely."""
        try:
            response = self.get(url)
            soup = BeautifulSoup(response.text, "lxml")
            parts = [
                self._section_text(soup, "Warum wir es lieben"),
                self._section_text(soup, "Spezifikationen"),
            ]
            description_raw = " ".join(p for p in parts if p)
            return {"description_raw": description_raw} if description_raw else {}
        except Exception as e:
            logger.exception("Error fetching Upway details %s: %s", listing_id, e)
            return {}

    def search_all(self) -> List[Dict[str, Any]]:
        """Search all configured brands."""
        all_results = []

        for brand in self.brands:
            try:
                results = self.search(brand)
                all_results.extend(results)
                logger.info("[Upway] Brand '%s': %d results", brand, len(results))
            except Exception as e:
                logger.exception("[Upway] Error searching brand %s: %s", brand, e)

        return all_results
