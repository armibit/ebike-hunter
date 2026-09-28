import logging
import re
from typing import Dict, List, Any, Optional
from bs4 import BeautifulSoup
from .base import BaseConnector, card_image

logger = logging.getLogger(__name__)


class VelomarktConnector(BaseConnector):
    """Connector for Velomarkt.ch (Swiss bike marketplace)."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__("velomarkt", config)
        self.base_url = config["portals"]["velomarkt"]["base_url"]
        self.max_pages = config["portals"]["velomarkt"].get("max_pages", 5)

    def search(self, category: str = "emtb", limit: int = 200) -> List[Dict[str, Any]]:
        """Search e-MTBs on Velomarkt, paginating via ?page=N.

        Page 1 alone only surfaces ~33 of up to ~500 listings (site's own
        pagination nav runs to page 16) — a single fetch was silently
        dropping the vast majority of results.
        """
        results = []
        seen_ids = set()

        # URL structure from bike/ project: /en/veloboerse/all-switzerland/ebikes-electric-bikes/emtb-electric-mtb
        url = f"{self.base_url}/en/veloboerse/all-switzerland/ebikes-electric-bikes/{category}"

        for page in range(1, self.max_pages + 1):
            try:
                response = self.get(url, params={"page": page})
            except Exception as e:
                logger.exception("Error searching Velomarkt: %s", e)
                break

            listings = self._parse_listings(response.text)
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
                "[Velomarkt] page %d/%d — %d new match(es), %d total so far",
                page, self.max_pages, new_count, len(results),
            )

            if new_count == 0:
                break

        return results

    def _parse_listings(self, html: str) -> List[Dict[str, Any]]:
        """Parse listings from HTML."""
        listings = []
        soup = BeautifulSoup(html, "lxml")

        # Find product cards. NOTE: must match the exact "bike-item" card
        # container, not a loose "item"/"ad" substring — Velomarkt nests
        # several unrelated divs (item-caption, item-description, item-name,
        # item-price...) inside each card, all of which also contain "item"
        # in their class name. A broad regex here previously matched every
        # nesting level as its own "card", producing ~4 duplicate, mis-scoped
        # entries per real listing and corrupting price via last-write-wins.
        items = soup.find_all("div", class_="bike-item")

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

            # Extract ID — Velomarkt slugs end in "-<numeric-id>", no separate
            # numeric path segment to match against.
            match = re.search(r"-(\d+)/?$", url)
            listing_id = match.group(1) if match else url.split("/")[-1]

            # Title — real markup has no h2/h3/"*title*" class; the name is
            # plain anchor text inside the "item-name" block.
            title_tag = item.find(class_="item-name")
            title = title_tag.get_text(strip=True) if title_tag else link_tag.get_text(strip=True)

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
                "image_url": card_image(item, "ik.imagekit.io"),
            }
        except Exception:
            return None

    def get_listing_details(self, listing_id: str, url: str) -> Dict[str, Any]:
        """Fetch detailed listing.

        A loose class_=re.compile("description|details") search on the full
        detail page hits the "Similar ads" sidebar first — verified live:
        22 matches for a real listing, every single one a sidebar card
        whose class is literally "item-description" but whose text is just
        "CHF 4'999.- 8610 Zurich" (price + city, no specs at all), never the
        real product. The actual description sits several DOM levels below
        an <h2>Description</h2> heading instead — no stable class/id on the
        real container, only that heading text to anchor on.
        """
        try:
            response = self.get(url)
            soup = BeautifulSoup(response.text, "lxml")

            description = self._description_section_text(soup)
            if not description:
                desc_tag = soup.find(class_=re.compile("description|details"))
                description = desc_tag.get_text(strip=True) if desc_tag else ""

            return {"description_raw": description}
        except Exception as e:
            logger.exception("Error fetching Velomarkt details %s: %s", listing_id, e)
            return {}

    @staticmethod
    def _description_section_text(soup: BeautifulSoup) -> str:
        for h2 in soup.find_all("h2"):
            if h2.get_text(strip=True) == "Description":
                container = h2
                for _ in range(3):
                    if container.parent:
                        container = container.parent
                return container.get_text(" ", strip=True)
        return ""

    def search_all(self) -> List[Dict[str, Any]]:
        """Search all e-MTBs."""
        results = self.search()
        logger.info("[Velomarkt] Found: %d results", len(results))
        return results
