import logging
import re
from typing import Dict, List, Any, Optional
from bs4 import BeautifulSoup
from .base import BaseConnector

logger = logging.getLogger(__name__)


class TcsVelocornerConnector(BaseConnector):
    """Connector for velocorner.ch (real TCS Velocorner marketplace).

    The previously configured domain (tcs.ch/velocorner) is only a marketing
    page with no listings — the actual marketplace lives on velocorner.ch,
    a server-rendered Next.js app (article.product-card cards, no JSON blob
    to parse). The "Mountainbike > Fully" category matches our full-suspension
    target and still runs ~200 pages mixing new+used stock, so we paginate
    up to max_pages and drop non-"used-" listings client-side (condition is
    encoded directly in the listing URL slug, e.g. /en/ebike/used-<slug>-id).
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__("tcs_velocorner", config)
        self.base_url = config["portals"]["tcs_velocorner"]["base_url"]
        self.category_path = config["portals"]["tcs_velocorner"].get(
            "category_path", "/en/buy-e-bike/mountainbike/fully"
        )
        self.max_pages = config["portals"]["tcs_velocorner"].get("max_pages", 10)

    def search(self, limit: int = 200) -> List[Dict[str, Any]]:
        """Search used full-suspension e-bikes on velocorner.ch, paginating via ?page=N."""
        results = []
        seen_ids = set()
        url = f"{self.base_url}{self.category_path}"

        for page in range(1, self.max_pages + 1):
            try:
                response = self.get(url, params={"page": page})
            except Exception as e:
                logger.error("Error searching TCS Velocorner: %s", e)
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
                "[TCS Velocorner] page %d/%d — %d new match(es), %d total so far",
                page, self.max_pages, new_count, len(results),
            )

            if new_count == 0:
                break

        return results

    def _parse_listings(self, html: str) -> List[Dict[str, Any]]:
        """Parse e-bike listings from HTML."""
        listings = []
        soup = BeautifulSoup(html, "lxml")

        items = soup.find_all("article", class_="product-card")

        for item in items:
            try:
                listing = self._parse_item(item)
                if listing:
                    listings.append(listing)
            except Exception:
                logger.debug("Failed to parse TCS Velocorner item", exc_info=True)
                continue

        return listings

    def _parse_item(self, item) -> Optional[Dict[str, Any]]:
        """Parse individual product card."""
        try:
            link_tag = item.select_one("a.product-card__content-header") or item.find("a", href=True)
            if not link_tag:
                return None

            url = link_tag["href"]
            if not url.startswith("http"):
                url = f"{self.base_url.rstrip('/')}{url}"

            # Condition lives in the URL slug prefix — skip "new-" listings,
            # this connector only targets the used/occasion market.
            slug = url.rstrip("/").split("/")[-1]
            if not slug.startswith("used-"):
                return None

            match = re.search(r"-(\d+)$", slug)
            product_id = match.group(1) if match else slug

            title = link_tag.get("title") or link_tag.get_text(strip=True)
            if not title:
                return None

            # Price: the card footer shows an optional struck-through MSRP
            # and a "you save" price above the real, final price — only the
            # last (largest-font) span in the footer is what you actually pay.
            price_raw = 0.0
            price_container = item.select_one("footer.product-card__content-footer > div")
            price_spans = price_container.find_all("span", recursive=False) if price_container else []
            price_span = price_spans[-1] if price_spans else None
            if price_span:
                price_text = price_span.get_text(strip=True)
                price_match = re.search(r"([\d'.,]+)", price_text)
                if price_match:
                    price_str = price_match.group(1).replace("'", "").replace(",", ".")
                    try:
                        price_raw = float(price_str)
                    except ValueError:
                        pass

            location_tag = item.select_one("span.product-card__location")
            location_raw = location_tag.get_text(strip=True) if location_tag else "Switzerland"

            return {
                "portal": "tcs_velocorner",
                "portal_id": product_id,
                "url": url,
                "title": title,
                "description_raw": "",
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
            desc_tag = soup.find(class_=re.compile("description|specs|details"))
            if desc_tag:
                description = desc_tag.get_text(strip=True)

            return {"description_raw": description}
        except Exception as e:
            logger.error("Error fetching TCS Velocorner details %s: %s", listing_id, e)
            return {}

    def search_all(self) -> List[Dict[str, Any]]:
        """Search all listings."""
        results = self.search()
        logger.info("[TCS Velocorner] Found: %d results", len(results))
        return results
