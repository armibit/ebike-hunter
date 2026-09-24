import logging
import re
from typing import Dict, List, Any, Optional
from bs4 import BeautifulSoup
from .base import BaseConnector

logger = logging.getLogger(__name__)


class VelomarktConnector(BaseConnector):
    """Connector for Velomarkt.ch (Swiss bike marketplace)."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__("velomarkt", config)
        self.base_url = config["portals"]["velomarkt"]["base_url"]

    def search(self, category: str = "emtb", limit: int = 50) -> List[Dict[str, Any]]:
        """Search e-MTBs on Velomarkt."""
        results = []

        # URL structure from bike/ project: /en/veloboerse/all-switzerland/ebikes-electric-bikes/emtb-electric-mtb
        url = f"{self.base_url}/en/veloboerse/all-switzerland/ebikes-electric-bikes/{category}"

        try:
            response = self.get(url)
            listings = self._parse_listings(response.text)
            results.extend(listings[:limit])
        except Exception as e:
            logger.error("Error searching Velomarkt: %s", e)

        return results

    def _parse_listings(self, html: str) -> List[Dict[str, Any]]:
        """Parse listings from HTML."""
        listings = []
        soup = BeautifulSoup(html, "lxml")

        # Find product cards/items
        items = soup.find_all("div", class_=re.compile(r"product|item|listing|ad"))

        for item in items:
            try:
                listing = self._parse_item(item)
                if listing:
                    listings.append(listing)
            except Exception:
                logger.debug("Failed to parse Velomarkt item", exc_info=True)
                continue

        return listings

    def _parse_item(self, item) -> Optional[Dict[str, Any]]:
        """Parse individual listing."""
        try:
            # Link
            link_tag = item.find("a", href=True)
            if not link_tag:
                return None

            url = link_tag["href"]
            if not url.startswith("http"):
                url = f"https://www.velomarkt.ch{url}"

            # Extract ID
            match = re.search(r"/(\d+)(?:/|$|\?)", url)
            listing_id = match.group(1) if match else url.split("/")[-1]

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

            # Location
            location_tag = item.find(class_=re.compile("location|city|region"))
            location_raw = location_tag.get_text(strip=True) if location_tag else "Switzerland"

            # Description
            description_raw = ""
            desc_tag = item.find(class_=re.compile("description|details"))
            if desc_tag:
                description_raw = desc_tag.get_text(strip=True)

            return {
                "portal": "velomarkt",
                "portal_id": listing_id,
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
            desc_tag = soup.find(class_=re.compile("description|details"))
            if desc_tag:
                description = desc_tag.get_text(strip=True)

            return {"description_raw": description}
        except Exception as e:
            logger.error("Error fetching Velomarkt details %s: %s", listing_id, e)
            return {}

    def search_all(self) -> List[Dict[str, Any]]:
        """Search all e-MTBs."""
        results = self.search()
        logger.info("[Velomarkt] Found: %d results", len(results))
        return results
