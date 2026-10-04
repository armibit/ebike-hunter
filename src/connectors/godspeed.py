import logging
import re
from typing import Dict, List, Any, Optional
from bs4 import BeautifulSoup
from .base import ListingGone, SHOP_SOLD_MARKERS, BaseConnector, card_image

logger = logging.getLogger(__name__)


class GodspeedConnector(BaseConnector):
    """Connector for Godspeed.ch (Ticino Lightspeed/webshopapp shop — 'occasioni' page)."""

    SOLD_MARKERS = SHOP_SOLD_MARKERS

    def __init__(self, config: Dict[str, Any]):
        super().__init__("godspeed", config)
        cfg = config["portals"]["godspeed"]
        self.base_url = cfg["base_url"]
        self.category_path = cfg.get("category_path", "/it/e-bikes/occasioni/")

    def search(self, limit: int = 50) -> List[Dict[str, Any]]:
        results = []
        url = f"{self.base_url}{self.category_path}"

        try:
            response = self.get(url)
        except Exception as e:
            logger.exception("Error fetching Godspeed occasioni page: %s", e)
            return results

        listings = self._parse_listings(response.text)
        return listings[:limit]

    def _parse_listings(self, html: str) -> List[Dict[str, Any]]:
        listings = []
        soup = BeautifulSoup(html, "lxml")

        for card in soup.find_all("div", class_="prod-card"):
            try:
                listing = self._parse_card(card)
                if listing:
                    listings.append(listing)
            except Exception:
                logger.debug("Failed to parse Godspeed card", exc_info=True)
                continue

        return listings

    def _parse_card(self, card) -> Optional[Dict[str, Any]]:
        link_tag = card.find("a", class_="prod-card__img-link", href=True)
        if not link_tag:
            return None
        url = link_tag["href"]

        id_match = re.search(r"-(\d+)\.html", url)
        portal_id = id_match.group(1) if id_match else url.rstrip("/").split("/")[-1]

        title_tag = card.find(class_="product-card__title")
        title = title_tag.get_text(strip=True) if title_tag else (link_tag.get("aria-label") or "")

        brand_tag = card.find(class_="prod-card__brand")
        if brand_tag:
            brand = brand_tag.get_text(strip=True)
            if brand and not title.lower().startswith(brand.lower()):
                title = f"{brand} {title}"

        if not title:
            return None

        price_raw = 0.0
        price_tag = card.find(class_="prod-card__price")
        if price_tag:
            price_text = price_tag.get_text(strip=True).replace("CHF", "").strip()
            price_text = price_text.replace("’", "").replace("'", "")
            price_match = re.search(r"([\d.]+)", price_text)
            if price_match:
                price_raw = float(price_match.group(1))

        return {
            "portal": "godspeed",
            "portal_id": portal_id,
            "url": url,
            "title": title,
            "description_raw": "",
            "price_raw": price_raw,
            "currency": "CHF",
            "location_raw": "Lugano, Ticino",
            "image_url": card_image(card, "cdn.webshopapp.com"),
        }

    def get_listing_details(self, listing_id: str, url: str) -> Dict[str, Any]:
        try:
            response = self.get(url)
            return {"description_raw": self._extract_description(response.text)}
        except ListingGone:
            return {}
        except Exception as e:
            logger.warning("Error fetching Godspeed details %s: %s", listing_id, e)
            return {}

    def _extract_description(self, html: str) -> str:
        # Spec table (motor/battery/torque) lives in the first tab panel;
        # the second panel is unrelated review boilerplate.
        soup = BeautifulSoup(html, "lxml")
        panel = soup.select_one(".js-tabs__panel")
        return panel.get_text(" ", strip=True) if panel else ""

    def search_all(self) -> List[Dict[str, Any]]:
        results = self.search()
        logger.info("[Godspeed] Found: %d results", len(results))
        return results
