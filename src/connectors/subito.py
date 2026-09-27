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
        self.max_pages = config["portals"]["subito_it"].get("max_pages", 4)

    def search(self, query: str, province: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Search Subito.it for listings, paginating via the `o` query param.
        A single page only surfaces ~30 results (plus a handful of repeated
        sponsored/pinned listings) — real result pools run well past that,
        so page 1 alone was silently dropping most matches.
        Returns list of raw listing dictionaries.
        """
        # Build search URL
        # Subito.it structure: /annunci-lombardia/vendita/biciclette?q=query
        search_url = f"{self.base_url}/annunci-lombardia/vendita/biciclette"
        base_params = {"q": query}
        if province:
            base_params["city"] = province

        results = []
        seen_ids = set()

        for page in range(1, self.max_pages + 1):
            params = {**base_params, "o": page}
            try:
                response = self.get(search_url, params=params, headers={"Referer": f"{self.base_url}/"})
            except Exception as e:
                logger.exception("Error searching Subito.it: %s", e)
                break

            listings = self._parse_search_results(response.text, response.url)
            if not listings:
                break

            new_count = 0
            for listing in listings:
                if listing["portal_id"] in seen_ids:
                    continue
                seen_ids.add(listing["portal_id"])
                results.append(listing)
                new_count += 1
                if len(results) >= limit:
                    return results

            logger.info(
                "[Subito.it] '%s' page %d/%d — %d new match(es), %d total so far",
                query, page, self.max_pages, new_count, len(results),
            )

            if new_count == 0:
                break

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

        # Method 2: Parse HTML listing cards. Real cards are exactly the
        # <article> tags — matching by a loose "item"/"card" class substring
        # also caught page-level wrapper <div>s (ListingContainer,
        # ItemListContainer) that ancestor every card, each returning the
        # first listing's link as if it were its own distinct result.
        cards = soup.find_all("article")

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

                        # Search-results pages carry one page-level Product
                        # schema summarizing ALL results (offers is an
                        # AggregateOffer with lowPrice/highPrice/offerCount,
                        # no single "price") — not a real listing. Skip it
                        # and fall through to per-card HTML parsing instead.
                        if offers.get("@type") == "AggregateOffer" or "price" not in offers:
                            continue

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

            # Extract title — real cards use an h3, not h2, and no
            # "*title*"-classed element exists as a fallback.
            title_tag = card.find(["h2", "h3"]) or card.find(class_=lambda c: c and "title" in c.lower())
            title = title_tag.get_text(strip=True) if title_tag else (link_tag.get("aria-label") or "")

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
        """Fetch detailed listing information.

        Prefers the detail page's own JSON-LD Product schema for the
        description: the clean, full text (confirmed against a live
        listing — includes the whole "Specifiche:" block, motor/battery/
        frame size and all), no HTML entities, and not tied to Subito's
        CSS module class names — which had already silently broken this
        once, looking for a `<div class="*description*">` when the real
        page now wraps the text in a `<p>` instead (a `find("div", ...)`
        never matches a `<p>` regardless of its class), and is ambiguous
        even for the right tag ("description-title", the heading right
        above it, also contains the substring "description"). Falls back
        to a tag-agnostic, exact-suffix class scrape only if JSON-LD is
        ever missing.
        """
        try:
            response = self.get(url)
            soup = BeautifulSoup(response.text, "lxml")

            description = self._extract_json_ld_description(soup)
            if not description:
                desc_tag = soup.find(class_=lambda c: c and re.search(r"description$", c.lower()))
                description = desc_tag.get_text(strip=True) if desc_tag else ""

            return {
                "description_raw": description
            }
        except Exception as e:
            logger.exception("Error fetching details for %s: %s", listing_id, e)
            return {}

    def _extract_json_ld_description(self, soup: BeautifulSoup) -> str:
        """The first JSON-LD Product schema's own description field, or ""."""
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
            except (json.JSONDecodeError, TypeError):
                continue
            items = data if isinstance(data, list) else [data]
            for item in items:
                if item.get("@type") == "Product" and item.get("description"):
                    return item["description"]
        return ""

    def search_all(self) -> List[Dict[str, Any]]:
        """Run all configured search queries."""
        all_results = []

        # Warm up the session on the homepage first so cookies are set before
        # hitting the search endpoint — reduces first-request bot-defense 403s.
        try:
            self.get(self.base_url)
        except Exception as e:
            logger.debug("Subito.it warm-up request failed (continuing anyway): %s", e)

        for query in self.search_queries:
            # Search without province filter first (all Lombardia)
            results = self.search(query)
            all_results.extend(results)
            logger.info("[Subito.it] Query '%s': %d results", query, len(results))

        return all_results
