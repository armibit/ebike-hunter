import json
import logging
import re
from typing import Dict, List, Any, Optional
from bs4 import BeautifulSoup
from .base import BaseConnector

logger = logging.getLogger(__name__)


class SubitoConnector(BaseConnector):
    """Connector for Subito.it (Lombardia classifieds)."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__("subito", config)
        self.base_url = config["portals"]["subito_it"]["base_url"]
        self.search_queries = config["portals"]["subito_it"]["search_queries"]
        self.provinces = config["portals"]["subito_it"].get("provinces", ["como", "varese"])

    def search(self, query: str, province: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Search Subito.it for listings.
        Returns list of raw listing dictionaries.
        """
        results = []

        # Build search URL
        # Subito.it structure: /annunci-lombardia/vendita/biciclette?q=query
        search_url = f"{self.base_url}/annunci-lombardia/vendita/biciclette"
        params = {"q": query}

        if province:
            params["city"] = province

        try:
            response = self.get(search_url, params=params)
            listings = self._parse_search_results(response.text, response.url)
            results.extend(listings)
        except Exception as e:
            logger.error("Error searching Subito.it: %s", e)

        return results

    def _parse_search_results(self, html: str, url: str) -> List[Dict[str, Any]]:
        """Parse search results from HTML and JSON-LD."""
        listings = []

        soup = BeautifulSoup(html, "lxml")

        # Method 1: Try JSON-LD structured data
        json_ld_listings = self._extract_json_ld(soup)
        if json_ld_listings:
            listings.extend(json_ld_listings)
            return listings

        # Method 2: Parse HTML listing cards
        cards = soup.find_all("div", class_=lambda c: c and ("item" in c.lower() or "card" in c.lower()))

        for card in cards[:50]:
            try:
                listing = self._parse_card(card)
                if listing:
                    listings.append(listing)
            except Exception:
                logger.debug("Failed to parse listing card", exc_info=True)
                continue

        return listings

    def _extract_json_ld(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extract Product schema from JSON-LD."""
        listings = []

        json_ld_scripts = soup.find_all("script", type="application/ld+json")

        for script in json_ld_scripts:
            try:
                data = json.loads(script.string)

                # Handle both single object and array
                items = data if isinstance(data, list) else [data]

                for item in items:
                    if item.get("@type") == "Product":
                        offers = item.get("offers", {})

                        listing = {
                            "portal": "subito",
                            "portal_id": item.get("sku", "") or item.get("productID", ""),
                            "url": item.get("url", ""),
                            "title": item.get("name", ""),
                            "description_raw": item.get("description", ""),
                            "price_raw": float(offers.get("price", 0) or 0),
                            "currency": offers.get("priceCurrency", "EUR"),
                            "location_raw": self._extract_location_from_item(item),
                        }
                        listings.append(listing)
            except (json.JSONDecodeError, KeyError):
                continue

        return listings

    def _extract_location_from_item(self, item: Dict) -> str:
        """Extract location from JSON-LD item."""
        # Try various location fields
        location = ""
        if "location" in item:
            loc = item["location"]
            if isinstance(loc, dict):
                location = loc.get("name", "") or loc.get("address", {}).get("addressLocality", "")
            else:
                location = str(loc)
        return location

    def _parse_card(self, card) -> Optional[Dict[str, Any]]:
        """Parse individual listing card from HTML."""
        try:
            # Extract link
            link_tag = card.find("a", href=True)
            if not link_tag:
                return None

            url = link_tag["href"]
            if not url.startswith("http"):
                url = f"{self.base_url}{url}"

            # Extract ID from URL
            id_match = re.search(r'/(\d+)\.htm', url)
            portal_id = id_match.group(1) if id_match else url.split("/")[-1].replace(".htm", "")

            # Extract title
            title_tag = card.find("h2") or card.find(class_=lambda c: c and "title" in c.lower())
            title = title_tag.get_text(strip=True) if title_tag else ""

            # Extract price
            price_tag = card.find(string=re.compile(r'€|EUR'))
            price_raw = 0.0
            if price_tag:
                price_str = str(price_tag).replace(".", "").replace(",", ".")
                price_match = re.search(r'([\d.]+)', price_str)
                if price_match:
                    price_raw = float(price_match.group(1))

            # Extract location
            location_tag = card.find(class_=lambda c: c and ("location" in c.lower() or "city" in c.lower()))
            location_raw = location_tag.get_text(strip=True) if location_tag else ""

            return {
                "portal": "subito",
                "portal_id": portal_id,
                "url": url,
                "title": title,
                "description_raw": "",
                "price_raw": price_raw,
                "currency": "EUR",
                "location_raw": location_raw,
            }
        except Exception:
            return None

    def get_listing_details(self, listing_id: str, url: str) -> Dict[str, Any]:
        """Fetch detailed listing information."""
        try:
            response = self.get(url)
            soup = BeautifulSoup(response.text, "lxml")

            # Extract description
            desc_tag = soup.find("div", class_=lambda c: c and "description" in c.lower())
            description = desc_tag.get_text(strip=True) if desc_tag else ""

            return {
                "description_raw": description
            }
        except Exception as e:
            logger.error("Error fetching details for %s: %s", listing_id, e)
            return {}

    def search_all(self) -> List[Dict[str, Any]]:
        """Run all configured search queries."""
        all_results = []

        for query in self.search_queries:
            # Search without province filter first (all Lombardia)
            results = self.search(query)
            all_results.extend(results)
            logger.info("[Subito.it] Query '%s': %d results", query, len(results))

        return all_results
