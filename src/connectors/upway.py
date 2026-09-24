import json
import logging
import re
from typing import Dict, List, Any, Optional
from bs4 import BeautifulSoup
from .base import BaseConnector

logger = logging.getLogger(__name__)


class UpwayConnector(BaseConnector):
    """Connector for Upway.ch (refurbished e-bikes)."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__("upway", config)
        self.base_url = config["portals"]["upway"]["base_url"]
        self.brands = config["portals"]["upway"].get("brands", ["cube", "lapierre", "ghost", "haibike"])

    def search(self, brand: str = "", limit: int = 50) -> List[Dict[str, Any]]:
        """Fetch e-bikes from Upway collections."""
        results = []

        if brand:
            url = f"{self.base_url}/collections/{brand.lower()}"
        else:
            url = f"{self.base_url}/collections"

        try:
            response = self.get(url)
            listings = self._parse_collection(response.text, brand)
            results.extend(listings[:limit])
        except Exception as e:
            logger.error("Error searching Upway brand %s: %s", brand, e)

        return results

    def _parse_collection(self, html: str, brand: str = "") -> List[Dict[str, Any]]:
        """Parse e-bike listings from Upway collection page."""
        listings = []
        soup = BeautifulSoup(html, "lxml")

        # Find product cards
        products = soup.find_all("div", class_=re.compile(r"product|item"))

        for product in products:
            try:
                listing = self._parse_product(product)
                if listing:
                    listings.append(listing)
            except Exception:
                logger.debug("Failed to parse Upway product", exc_info=True)
                continue

        return listings

    def _parse_product(self, product) -> Optional[Dict[str, Any]]:
        """Parse individual product from HTML."""
        try:
            # Product link
            link_tag = product.find("a", href=True)
            if not link_tag:
                return None

            url = link_tag["href"]
            if not url.startswith("http"):
                url = f"{self.base_url}{url}"

            # Extract ID from URL (e.g., /products/cube-reaction-rkXXXX)
            match = re.search(r"/products/([^/?]+)", url)
            if not match:
                return None
            product_id = match.group(1)

            # Title
            title_tag = product.find("h2") or product.find("h3") or product.find("span", class_=re.compile("title"))
            title = title_tag.get_text(strip=True) if title_tag else ""

            if not title:
                return None

            # Price
            price_tag = product.find(class_=re.compile("price")) or product.find(string=re.compile(r"CHF|€"))
            price_raw = 0.0
            if price_tag:
                price_text = price_tag.get_text(strip=True) if hasattr(price_tag, "get_text") else str(price_tag)
                price_match = re.search(r"([\d'.,]+)", price_text)
                if price_match:
                    price_str = price_match.group(1).replace("'", "").replace(",", ".")
                    try:
                        price_raw = float(price_str)
                    except ValueError:
                        pass

            # Currency (CHF or EUR)
            currency = "CHF" if "CHF" in str(product) else "EUR"

            # Location (assume Switzerland for Upway)
            location_raw = "Switzerland"

            # Condition/km (may not be visible in list view)
            description_raw = ""
            desc_tag = product.find(class_=re.compile("description|condition"))
            if desc_tag:
                description_raw = desc_tag.get_text(strip=True)

            return {
                "portal": "upway",
                "portal_id": product_id,
                "url": url,
                "title": title,
                "description_raw": description_raw,
                "price_raw": price_raw,
                "currency": currency,
                "location_raw": location_raw,
            }
        except Exception:
            return None

    def get_listing_details(self, listing_id: str, url: str) -> Dict[str, Any]:
        """Fetch detailed listing from product page."""
        try:
            response = self.get(url)
            soup = BeautifulSoup(response.text, "lxml")

            # Extract specs from product page
            description = ""
            desc_tag = soup.find(class_=re.compile("description|specs|details"))
            if desc_tag:
                description = desc_tag.get_text(strip=True)

            return {"description_raw": description}
        except Exception as e:
            logger.error("Error fetching Upway details %s: %s", listing_id, e)
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
                logger.error("[Upway] Error searching brand %s: %s", brand, e)

        return all_results
