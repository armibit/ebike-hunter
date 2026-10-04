import logging
import re
from typing import Dict, List, Any, Optional
from bs4 import BeautifulSoup
from .base import ListingGone, SHOP_SOLD_MARKERS, BaseConnector, card_image

logger = logging.getLogger(__name__)


class EbikelabConnector(BaseConnector):
    """Connector for Ebikelab.it (Como, Magento shop — 'usato' category)."""

    SOLD_MARKERS = SHOP_SOLD_MARKERS

    def __init__(self, config: Dict[str, Any]):
        super().__init__("ebikelab", config)
        cfg = config["portals"]["ebikelab"]
        self.base_url = cfg["base_url"]
        self.category_path = cfg.get("category_path", "/ebike/usato")
        self.max_pages = cfg.get("max_pages", 4)

    def search(self, limit: int = 50) -> List[Dict[str, Any]]:
        results = []
        url = f"{self.base_url}{self.category_path}"

        for page in range(1, self.max_pages + 1):
            try:
                response = self.get(url, params={"p": page})
            except Exception as e:
                logger.exception("Error fetching Ebikelab page %d: %s", page, e)
                break

            listings = self._parse_listings(response.text)
            if not listings:
                break
            results.extend(listings)

            if len(results) >= limit:
                return results[:limit]

        return results[:limit]

    def _parse_listings(self, html: str) -> List[Dict[str, Any]]:
        listings = []
        soup = BeautifulSoup(html, "lxml")

        for card in soup.find_all("li", class_="product-item"):
            try:
                listing = self._parse_card(card)
                if listing:
                    listings.append(listing)
            except Exception:
                logger.debug("Failed to parse Ebikelab card", exc_info=True)
                continue

        return listings

    def _parse_card(self, card) -> Optional[Dict[str, Any]]:
        link_tag = card.find("a", class_="product-item-link", href=True)
        if not link_tag:
            return None

        url = link_tag["href"]
        title = link_tag.get_text(strip=True)
        if not title:
            return None

        # URL key ends "...-p<product_id>-<variant_id>" — a plain trailing
        # "-digits-digits" pattern would grab the variant id instead, since
        # the hyphen right before the product id is followed by "p", not a digit.
        id_match = re.search(r"-p(\d+)-\d+/?$", url) or re.search(r"-(\d+)/?$", url)
        portal_id = id_match.group(1) if id_match else url.rstrip("/").split("/")[-1]

        price_raw = 0.0
        price_tag = card.find(attrs={"data-price-amount": True})
        if price_tag:
            try:
                price_raw = float(price_tag["data-price-amount"])
            except ValueError:
                pass

        return {
            "portal": "ebikelab",
            "portal_id": portal_id,
            "url": url,
            "title": title,
            "description_raw": "",
            "price_raw": price_raw,
            "currency": "EUR",
            "location_raw": "Como",
            "image_url": card_image(card, "ebikelab.it/media"),
        }

    def get_listing_details(self, listing_id: str, url: str) -> Dict[str, Any]:
        try:
            response = self.get(url)
            return {"description_raw": self._extract_description(response.text)}
        except ListingGone:
            return {}
        except Exception as e:
            logger.warning("Error fetching Ebikelab details %s: %s", listing_id, e)
            return {}

    def _extract_description(self, html: str) -> str:
        soup = BeautifulSoup(html, "lxml")
        desc_tag = soup.select_one("div.product.attribute.description") or soup.select_one("div#description")
        return desc_tag.get_text(" ", strip=True) if desc_tag else ""

    def search_all(self) -> List[Dict[str, Any]]:
        results = self.search()
        logger.info("[Ebikelab] Found: %d results", len(results))
        return results
