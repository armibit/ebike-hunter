import logging
import re
from typing import Dict, List, Any, Optional
from bs4 import BeautifulSoup
from .base import SHOP_SOLD_MARKERS, BaseConnector

logger = logging.getLogger(__name__)


class EbikestorebresciaConnector(BaseConnector):
    """Connector for Ebikestore Brescia ('usato certificato' category).

    The shop the ebikestorebrescia.it content site links out to actually runs
    on a separate PrestaShop domain (ebikestore.shop) — that's where real
    inventory and prices live, so this connector talks to that domain directly.
    """

    SOLD_MARKERS = SHOP_SOLD_MARKERS

    def __init__(self, config: Dict[str, Any]):
        super().__init__("ebikestorebrescia", config)
        cfg = config["portals"]["ebikestorebrescia"]
        self.base_url = cfg["base_url"]
        self.category_path = cfg.get("category_path", "/20-usato-certificato")

    def search(self, limit: int = 50) -> List[Dict[str, Any]]:
        results = []
        url = f"{self.base_url}{self.category_path}"

        try:
            response = self.get(url)
        except Exception as e:
            logger.exception("Error fetching Ebikestore Brescia category page: %s", e)
            return results

        listings = self._parse_listings(response.text)
        return listings[:limit]

    def _parse_listings(self, html: str) -> List[Dict[str, Any]]:
        listings = []
        soup = BeautifulSoup(html, "lxml")

        for card in soup.find_all("article", class_="product-miniature"):
            try:
                listing = self._parse_card(card)
                if listing:
                    listings.append(listing)
            except Exception:
                logger.debug("Failed to parse Ebikestore Brescia card", exc_info=True)
                continue

        return listings

    def _parse_card(self, card) -> Optional[Dict[str, Any]]:
        title_tag = card.find(class_="productName")
        link_tag = title_tag.find("a", href=True) if title_tag else None
        if not link_tag:
            return None

        url = link_tag["href"]
        title = link_tag.get_text(strip=True)
        if not title:
            return None

        portal_id = card.get("data-id-product") or url.rstrip("/").split("/")[-1]

        price_raw = 0.0
        price_tag = card.find(attrs={"itemprop": "price"})
        if price_tag:
            price_text = price_tag.get_text(strip=True).replace("€", "").strip()
            price_text = price_text.replace(".", "").replace(",", ".")
            price_match = re.search(r"([\d.]+)", price_text)
            if price_match:
                price_raw = float(price_match.group(1))

        return {
            "portal": "ebikestorebrescia",
            "portal_id": str(portal_id),
            "url": url,
            "title": title,
            "description_raw": "",
            "price_raw": price_raw,
            "currency": "EUR",
            "location_raw": "Brescia",
        }

    def get_listing_details(self, listing_id: str, url: str) -> Dict[str, Any]:
        try:
            response = self.get(url)
            return {"description_raw": self._extract_description(response.text)}
        except Exception as e:
            logger.exception("Error fetching Ebikestore Brescia details %s: %s", listing_id, e)
            return {}

    def _extract_description(self, html: str) -> str:
        soup = BeautifulSoup(html, "lxml")
        desc_tag = soup.select_one("div#description")
        return desc_tag.get_text(" ", strip=True) if desc_tag else ""

    def search_all(self) -> List[Dict[str, Any]]:
        results = self.search()
        logger.info("[Ebikestore Brescia] Found: %d results", len(results))
        return results
