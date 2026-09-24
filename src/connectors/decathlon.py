import logging
import re
from typing import Dict, List, Any, Optional
from bs4 import BeautifulSoup
from .base import BaseConnector

logger = logging.getLogger(__name__)


class DecathlonConnector(BaseConnector):
    """Connector for Decathlon.ch e-bike 2nd hand marketplace."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__("decathlon", config)
        self.base_url = config["portals"]["decathlon"]["base_url"]
        self.max_pages = config["portals"]["decathlon"].get("max_pages", 5)

    def search(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Fetch used e-bikes from Decathlon 2nd hand."""
        results = []

        for page_idx in range(self.max_pages):
            page_num = page_idx + 1
            # Pagination: ?from=40&size=40
            from_param = page_idx * 40
            url = f"{self.base_url}?from={from_param}&size=40"

            try:
                response = self.get(url)
                listings = self._parse_listings(response.text, url)
                results.extend(listings)

                if not listings:
                    break

                if len(results) >= limit:
                    return results[:limit]

            except Exception as e:
                logger.error("Error fetching Decathlon page %d: %s", page_num, e)
                break

        return results[:limit]

    def _parse_listings(self, html: str, url: str) -> List[Dict[str, Any]]:
        """Parse e-bike listings from HTML."""
        listings = []
        soup = BeautifulSoup(html, "lxml")

        # Find product items
        items = soup.find_all("div", class_=re.compile(r"product|item|article"))

        for item in items:
            try:
                listing = self._parse_item(item)
                if listing:
                    listings.append(listing)
            except Exception:
                logger.debug("Failed to parse Decathlon item", exc_info=True)
                continue

        return listings

    def _parse_item(self, item) -> Optional[Dict[str, Any]]:
        """Parse individual product item."""
        try:
            # Link
            link_tag = item.find("a", href=True)
            if not link_tag:
                return None

            url = link_tag["href"]
            if not url.startswith("http"):
                url = f"{self.base_url.rsplit('/', 1)[0]}{url}"

            # Extract product ID
            match = re.search(r"/product/(\d+)", url)
            product_id = match.group(1) if match else url.split("/")[-1]

            # Title
            title_tag = item.find("h2") or item.find("h3") or item.find(class_=re.compile("title"))
            title = title_tag.get_text(strip=True) if title_tag else ""

            if not title:
                return None

            # Price (CHF)
            price_tag = item.find(class_=re.compile("price")) or item.find(string=re.compile(r"CHF|Fr\."))
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

            # Description
            description_raw = ""
            desc_tag = item.find(class_=re.compile("description|condition|details"))
            if desc_tag:
                description_raw = desc_tag.get_text(strip=True)

            # Location (assume Decathlon store or Switzerland)
            location_raw = "Switzerland (Decathlon)"

            return {
                "portal": "decathlon",
                "portal_id": product_id,
                "url": url,
                "title": title,
                "description_raw": description_raw,
                "price_raw": price_raw,
                "currency": "CHF",
                "location_raw": location_raw,
            }
        except Exception:
            return None

    def get_listing_details(self, listing_id: str, url: str) -> Dict[str, Any]:
        """Fetch detailed listing."""
        try:
            response = self.get(url)
            soup = BeautifulSoup(response.text, "lxml")

            description = ""
            desc_tag = soup.find(class_=re.compile("description|specs"))
            if desc_tag:
                description = desc_tag.get_text(strip=True)

            return {"description_raw": description}
        except Exception as e:
            logger.error("Error fetching Decathlon details %s: %s", listing_id, e)
            return {}

    def search_all(self) -> List[Dict[str, Any]]:
        """Search all pages."""
        results = self.search()
        logger.info("[Decathlon] Found: %d results", len(results))
        return results
