import logging
import re
from typing import Dict, List, Any, Optional
from bs4 import BeautifulSoup
from .base import BaseConnector

logger = logging.getLogger(__name__)


class RidewillConnector(BaseConnector):
    """Connector for Ridewill.it (Italian bike shop — used/km0 e-bikes)."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__("ridewill", config)
        cfg = config["portals"]["ridewill"]
        self.base_url = cfg["base_url"]
        self.category_id = str(cfg.get("category_id", "87"))
        self.type_id = str(cfg.get("type_id", "7"))
        self.max_pages = cfg.get("max_pages", 3)

    def search(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Fetch used/km0 e-bikes via Ridewill's product-grid AJAX endpoint."""
        results = []
        url = f"{self.base_url}/ajax/LoadProducts"

        for page in range(1, self.max_pages + 1):
            payload = {
                "Tipo": "E-bike",
                "IdTipo": self.type_id,
                "idtipo": self.type_id,
                "IdCat1": self.category_id,
                "idcat1": self.category_id,
                "ForPage": 21,
                "ordinamento": "d",
                "page": page,
            }
            try:
                response = self.post(url, data=payload, headers={"X-Requested-With": "XMLHttpRequest"})
                data = response.json()
            except Exception as e:
                logger.exception("Error fetching Ridewill page %d: %s", page, e)
                break

            listings = self._parse_products(data.get("products", ""))
            if not listings:
                break
            results.extend(listings)

            if len(results) >= limit:
                return results[:limit]

        return results[:limit]

    def _parse_products(self, html: str) -> List[Dict[str, Any]]:
        """Parse product cards from the AJAX-returned HTML fragment."""
        listings = []
        soup = BeautifulSoup(html, "lxml")

        for card in soup.find_all("div", class_="box-product"):
            try:
                listing = self._parse_card(card)
                if listing:
                    listings.append(listing)
            except Exception:
                logger.debug("Failed to parse Ridewill card", exc_info=True)
                continue

        return listings

    def _parse_card(self, card) -> Optional[Dict[str, Any]]:
        link_tag = card.find("a", class_="box-product__description")
        if not link_tag:
            return None

        url = link_tag["href"]
        if not url.startswith("http"):
            url = f"{self.base_url}{url}"

        id_match = re.search(r"/(\d+)/?$", url)
        portal_id = id_match.group(1) if id_match else url.rstrip("/").split("/")[-1]

        title = link_tag.get_text(strip=True)
        if not title:
            return None

        price_raw = 0.0
        price_tag = card.find("span", class_="offer-price")
        if price_tag:
            price_str = price_tag.get_text(strip=True).replace("€", "").strip()
            price_str = price_str.replace(".", "").replace(",", ".")
            price_match = re.search(r"([\d.]+)", price_str)
            if price_match:
                price_raw = float(price_match.group(1))

        return {
            "portal": "ridewill",
            "portal_id": portal_id,
            "url": url,
            "title": title,
            "description_raw": "",
            "price_raw": price_raw,
            "currency": "EUR",
            "location_raw": "Italy",
        }

    def get_listing_details(self, listing_id: str, url: str) -> Dict[str, Any]:
        """Fetch full product page (title already carries most specs, this is a fallback).

        The old class_=re.compile("description|...") selector never actually
        matched this product's own text — verified live: the product page's
        "Descrizione" tab lives at `[data-tab-content="descrizione"]`, but a
        "prodotti correlati" (related products) carousel elsewhere on the
        same page uses `class="box-product__description"` on each of its
        cards, and a loose substring match hits those FIRST (document
        order), silently returning a *different, unrelated* product's name
        every time — not empty, so it was never obviously broken, just
        always wrong. The real description tab also has the actual spec
        table (Motore, Batteria (Wh), Escursione (mm)...), which the
        carousel cards never carried at all.
        """
        try:
            response = self.get(url)
            soup = BeautifulSoup(response.text, "lxml")
            desc_tag = soup.select_one('[data-tab-content="descrizione"]')
            if not desc_tag:
                desc_tag = soup.find(class_=re.compile("description|scheda|caratteristiche"))
            description = desc_tag.get_text(" ", strip=True) if desc_tag else ""
            return {"description_raw": description}
        except Exception as e:
            logger.exception("Error fetching Ridewill details %s: %s", listing_id, e)
            return {}

    def search_all(self) -> List[Dict[str, Any]]:
        results = self.search()
        logger.info("[Ridewill] Found: %d results", len(results))
        return results
