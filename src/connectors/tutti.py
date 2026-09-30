import base64
import json
import logging
import re
import msgpack
from typing import Dict, List, Any, Optional
from .base import BaseConnector

logger = logging.getLogger(__name__)

# tutti.ch encodes search filters (term/category/location) into an opaque
# token used in its Next.js routing (/it/q/{slug}/{token}). Reverse-engineered
# 2026-09-25: token = "A" + urlsafe_b64(msgpack([term, category_id,
# [None, None, None, [["location", geo_id, None]]]])), no padding.
# (slug, geo_id) per canton — slug is cosmetic, geo_id drives the filter.
CANTON_GEO = {
    "ti": ("biciclette-ticino", "geo-canton-ticino"),
    "gr": ("biciclette-grigioni", "geo-canton-graubunden"),
}
BICYCLES_CATEGORY_ID = "bicycles"


class TuttiConnector(BaseConnector):
    """Connector for Tutti.ch (Ticino classifieds).

    Tutti.ch runs a Next.js frontend; listing data is embedded in
    `__NEXT_DATA__` under `props.pageProps.dehydratedState.queries`
    (React Query dehydrated state). A raw `?q=` query string param is
    ignored server-side — real search terms must be baked into the
    opaque `/it/q/{slug}/{token}` route token (see `_build_token`).
    Server-side term matching is loose/OR-style, so results are still
    filtered locally with an AND-of-words check on title/description.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__("tutti", config)
        self.base_url = config["portals"]["tutti_ch"]["base_url"]
        self.search_queries = config["portals"]["tutti_ch"]["search_queries"]
        self.cantons = config["portals"]["tutti_ch"].get("cantons", ["ti"])
        self.max_pages = config["portals"]["tutti_ch"].get("max_pages", 3)

    @staticmethod
    def _normalize(text: str) -> str:
        """Strip hyphens/spaces so 'e-bike' and 'ebike' (or 'e-mtb'/'emtb') match."""
        return re.sub(r"[^a-z0-9]+", "", text.lower())

    def _matches_keywords(self, listing: Dict[str, Any], keywords: List[str]) -> bool:
        """True if every keyword appears in the normalized title+description."""
        haystack = self._normalize(f"{listing['title']} {listing['description_raw']}")
        return all(k in haystack for k in keywords)

    @staticmethod
    def _build_token(term: Optional[str], geo_id: str) -> str:
        """Build the opaque tutti.ch search token for a term + canton geo filter."""
        payload = [term, BICYCLES_CATEGORY_ID, [None, None, None, [["location", geo_id, None]]]]
        packed = msgpack.packb(payload, use_bin_type=False)
        return "A" + base64.urlsafe_b64encode(packed).decode().rstrip("=")

    def search(self, query: str, canton: str = "ti", limit: int = 50) -> List[Dict[str, Any]]:
        """
        Run a real server-side search on Tutti.ch for a term + canton,
        filtered locally by keyword. Returns raw listing dicts.
        """
        if canton not in CANTON_GEO:
            logger.warning("[Tutti.ch] Unknown canton '%s', skipping", canton)
            return []

        slug, geo_id = CANTON_GEO[canton]
        token = self._build_token(query or None, geo_id)
        keywords = [self._normalize(w) for w in query.split()] if query else []
        results = []
        seen_ids = set()

        for page in range(1, self.max_pages + 1):
            url = f"{self.base_url}/it/q/{slug}/{token}"
            label = f"{self.base_url}/it/q/{slug} (q='{query or 'all'}', page {page})"
            try:
                response = self.get(url, params={"page": page}, label=label)
            except Exception as e:
                logger.exception("Error searching Tutti.ch: %s", e)
                break

            listings = self._parse_search_results(response.text, response.url)
            if not listings:
                break

            new_count = 0
            for listing in listings:
                if listing["portal_id"] in seen_ids:
                    continue
                seen_ids.add(listing["portal_id"])
                if not self._matches_keywords(listing, keywords):
                    continue
                results.append(listing)
                new_count += 1
                if len(results) >= limit:
                    return results

            logger.info(
                "[Tutti.ch] '%s' (%s) page %d/%d — %d new match(es), %d total so far",
                query, canton, page, self.max_pages, new_count, len(results),
            )

            if new_count == 0:
                break

        return results

    def _parse_search_results(self, html: str, url: str) -> List[Dict[str, Any]]:
        """Parse listings from __NEXT_DATA__ dehydratedState JSON."""
        data = self._extract_next_data(html)
        if data:
            return self._parse_next_data(data)
        logger.debug("No __NEXT_DATA__ found on %s", url)
        return []

    def _extract_next_data(self, html: str) -> Optional[Dict]:
        """Extract __NEXT_DATA__ JSON from page."""
        match = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.+?)</script>',
            html,
            re.DOTALL,
        )
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                logger.debug("Failed to decode __NEXT_DATA__ JSON")
        return None

    @staticmethod
    def _parse_price(formatted_price: str) -> float:
        """Parse Tutti formatted price like \"2'200.-\" or \"1 500.-\" into float."""
        if not formatted_price:
            return 0.0
        digits = re.sub(r"[^\d]", "", formatted_price)
        return float(digits) if digits else 0.0

    def _parse_next_data(self, data: Dict) -> List[Dict[str, Any]]:
        """Parse listing nodes from dehydratedState.queries."""
        listings = []

        try:
            queries = (
                data.get("props", {})
                .get("pageProps", {})
                .get("dehydratedState", {})
                .get("queries", [])
            )
            for query in queries:
                query_data = query.get("state", {}).get("data", {})
                if not isinstance(query_data, dict):
                    continue
                listings_payload = query_data.get("listings")
                if not isinstance(listings_payload, dict):
                    continue
                for edge in listings_payload.get("edges", []):
                    node = edge.get("node", {})
                    listing = self._parse_node(node)
                    if listing:
                        listings.append(listing)
        except Exception as e:
            logger.exception("Error parsing Next data: %s", e)

        return listings

    def _parse_node(self, node: Dict) -> Optional[Dict[str, Any]]:
        """Convert a single dehydratedState listing node to our raw format."""
        try:
            listing_id = node.get("listingID")
            if not listing_id:
                return None

            localization = node.get("localization", {}) or {}
            postcode = node.get("postcodeInformation", {}) or {}
            canton_info = postcode.get("canton", {}) or {}
            seo = node.get("seoInformation", {}) or {}
            seller = node.get("sellerInfo", {}) or {}

            slug = seo.get("itSlug") or seo.get("deSlug") or ""
            if slug:
                url = f"{self.base_url}/it/vi/{slug}/{listing_id}"
            else:
                url = f"{self.base_url}/it/vi/{listing_id}"

            location_parts = [
                p for p in (
                    f'{postcode.get("postcode", "")} {postcode.get("locationName", "")}'.strip(),
                    canton_info.get("name", ""),
                ) if p
            ]

            return {
                "portal": "tutti",
                "portal_id": str(listing_id),
                "url": url,
                "title": localization.get("title", "") or "",
                "description_raw": localization.get("body", "") or "",
                "price_raw": self._parse_price(node.get("formattedPrice", "")),
                "currency": "CHF",
                "location_raw": ", ".join(location_parts),
                "category": (node.get("primaryCategory", {}) or {}).get("categoryID", ""),
                "seller_name": seller.get("alias", ""),
                "timestamp": node.get("timestamp", ""),
                "image_url": ((node.get("thumbnail") or {}).get("normalRendition") or {}).get("src"),
            }
        except Exception:
            logger.debug("Failed to parse Tutti listing node", exc_info=True)
            return None

    def get_listing_details(self, listing_id: str, url: str) -> Dict[str, Any]:
        """Fetch detailed listing information."""
        try:
            response = self.get(url)
            data = self._extract_next_data(response.text)
            if data:
                # Detail page embeds the full listing body in dehydratedState
                queries = (
                    data.get("props", {})
                    .get("pageProps", {})
                    .get("dehydratedState", {})
                    .get("queries", [])
                )
                for query in queries:
                    query_data = query.get("state", {}).get("data", {})
                    if not isinstance(query_data, dict):
                        continue
                    listing = query_data.get("listing")
                    if isinstance(listing, dict):
                        localization = listing.get("localization", {}) or {}
                        return {"description_raw": localization.get("body", "") or ""}
            return {}
        except Exception as e:
            logger.warning("Error fetching details for %s: %s", listing_id, e)
            return {}

    def search_all(self) -> List[Dict[str, Any]]:
        """Run all configured search queries."""
        all_results = []

        for query in self.search_queries:
            for canton in self.cantons:
                results = self.search(query, canton=canton)
                all_results.extend(results)
                logger.info("[Tutti.ch] Query '%s' in %s: %d results", query, canton, len(results))

        return all_results
