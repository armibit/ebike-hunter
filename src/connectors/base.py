import logging
import re
import time
import random
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit
from bs4 import BeautifulSoup
from curl_cffi import requests
from typing import Dict, List, Optional, Any
from abc import ABC, abstractmethod
from utils.console import status

logger = logging.getLogger(__name__)


MAX_RETRY_AFTER_SECONDS = 300


def _retry_after_seconds(value: Optional[str], default: int = 60) -> int:
    """Retry-After may be delta-seconds or an HTTP date (RFC 9110). Capped so
    one portal can't park its scan thread for hours."""
    if not value:
        return default
    try:
        seconds = int(value)
    except ValueError:
        try:
            when = parsedate_to_datetime(value)
            seconds = int((when - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError):
            return default
    return max(0, min(seconds, MAX_RETRY_AFTER_SECONDS))


# Page-level messages portals show on a sold/expired/removed listing, in the
# languages our portals use. Deliberately whole sentences, not single words
# like "venduto": a seller's own description can say "venduto con
# caricatore" on a bike that is very much still for sale.
GENERIC_SOLD_MARKERS = (
    "annuncio non è più disponibile", "annuncio non più disponibile", "annuncio scaduto",
    "l'annuncio è scaduto", "questo annuncio è stato rimosso", "questo annuncio è stato venduto",
    "inserat ist nicht mehr verfügbar", "anzeige ist nicht mehr verfügbar",
    "dieses inserat ist nicht mehr aktiv", "artikel wurde verkauft",
    "annonce n'est plus disponible", "cette annonce a expiré",
    "listing is no longer available", "this item has been sold",
)

# Stock labels a webshop prints on a sold-out product page. Only for shop
# connectors: on a private seller's page they'd be too easy to hit in prose.
SHOP_SOLD_MARKERS = ("esaurito", "prodotto non disponibile", "out of stock", "sold out", "ausverkauft", "épuisé")

_JSON_LD_AVAILABILITY =re.compile(r'"availability"\s*:\s*"(?:https?://schema\.org/)?(\w+)"', re.IGNORECASE)
_SOLD_AVAILABILITY = {"outofstock", "soldout", "discontinued"}


def shopify_variants_available(variants: List[Dict[str, Any]]) -> Optional[bool]:
    """From a products.json product's variants: False when every variant is
    sold out, True when any is available, None when the feed doesn't say."""
    flags = [v.get("available") for v in variants or [] if "available" in v]
    if not flags:
        return None
    return any(flags)


def _listing_key(url: str) -> Optional[str]:
    """What must survive a redirect for it to still be this listing: the
    numeric id in the last path segment. None when there's no id — a bare
    slug can legitimately change (another language, a renamed product), so
    a redirect alone proves nothing there."""
    segment = urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1].lower()
    digits = re.findall(r"\d{5,}", segment)
    return max(digits, key=len) if digits else None


def availability_from_page(status_code: int, requested_url: str, final_url: str, html: str,
                           sold_markers=GENERIC_SOLD_MARKERS) -> Optional[bool]:
    """True = still for sale, False = sold/removed, None = can't tell (keep
    the listing as is). Signals, strongest first: 404/410; a redirect that
    lost the listing's id (portals bounce removed ads to search/home); a
    schema.org availability of OutOfStock/SoldOut; a sold/expired message."""
    if status_code in (404, 410):
        return False
    if status_code >= 400:
        return None  # blocked, rate limited, server error: no verdict
    key = _listing_key(requested_url)
    if key and key not in final_url.lower():
        return False
    availabilities = {a.lower() for a in _JSON_LD_AVAILABILITY.findall(html or "")}
    if availabilities and availabilities <= _SOLD_AVAILABILITY:
        return False
    text = BeautifulSoup(html or "", "lxml").get_text(" ", strip=True).lower().replace("’", "'")
    if any(marker in text for marker in sold_markers):
        return False
    return True


class BaseConnector(ABC):
    """Base connector with anti-bot headers and rate limiting.

    Uses curl_cffi instead of plain `requests` so outgoing traffic carries a
    real Chrome TLS/JA3 fingerprint — several portals (e.g. Subito.it) block
    plain `requests` purely on that fingerprint regardless of headers sent.
    """

    def __init__(self, portal_name: str, config: Dict[str, Any]):
        self.portal_name = portal_name
        self.config = config
        self.session = requests.Session(impersonate="chrome124")
        self.last_request_time = 0
        self.min_delay = 2.0  # Minimum 2 seconds between requests

        # curl_cffi's impersonate= already sets a matching User-Agent/
        # Accept-Encoding (incl. brotli, decoded natively) for the
        # impersonated browser — only add the headers it doesn't cover.
        self.session.headers.update({
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7,de-CH;q=0.6",
            "DNT": "1",
            "Upgrade-Insecure-Requests": "1",
        })

    def _rate_limit(self):
        """Enforce rate limiting with jitter."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_delay:
            jitter = random.uniform(0.5, 1.5)
            sleep_time = (self.min_delay - elapsed) + jitter
            time.sleep(sleep_time)
        self.last_request_time = time.time()

    def get(self, url: str, params: Optional[Dict] = None, headers: Optional[Dict] = None, label: Optional[str] = None) -> requests.Response:
        """Rate-limited GET request with one retry on 429 and on 403.

        `label` overrides the URL shown on the live status line — some
        portals (e.g. tutti.ch) encode search filters into an opaque path
        token that's meaningless to read at a glance.
        """
        status.update(self.portal_name, f"[{self.portal_name}] GET {label or url}")
        self._rate_limit()

        request_headers = self.session.headers.copy()
        if headers:
            request_headers.update(headers)

        try:
            response = self.session.get(url, params=params, headers=request_headers, timeout=15)
            if response.status_code == 429:
                retry_after = _retry_after_seconds(response.headers.get("Retry-After"))
                logger.warning("Rate limited by %s — sleeping %ds", url, retry_after)
                time.sleep(retry_after)
                response = self.session.get(url, params=params, headers=request_headers, timeout=15)
            elif response.status_code == 403:
                # Some sites (e.g. Akamai-fronted) intermittently block the first
                # request of a session but pass once cookies are set — one retry
                # after a short delay clears this without a real browser engine.
                logger.warning("403 from %s — retrying once after backoff", url)
                time.sleep(random.uniform(3.0, 6.0))
                response = self.session.get(url, params=params, headers=request_headers, timeout=15)
            response.raise_for_status()
            return response
        except requests.exceptions.HTTPError as e:
            logger.exception("HTTP error fetching %s: %s", url, e)
            raise
        except requests.exceptions.RequestException as e:
            logger.exception("Request failed for %s: %s", url, e)
            raise

    def post(self, url: str, data: Optional[Dict] = None, headers: Optional[Dict] = None) -> requests.Response:
        """Rate-limited POST request with retry on 429."""
        status.update(self.portal_name, f"[{self.portal_name}] POST {url}")
        self._rate_limit()

        request_headers = self.session.headers.copy()
        if headers:
            request_headers.update(headers)

        try:
            response = self.session.post(url, data=data, headers=request_headers, timeout=15)
            if response.status_code == 429:
                retry_after = _retry_after_seconds(response.headers.get("Retry-After"))
                logger.warning("Rate limited by %s — sleeping %ds", url, retry_after)
                time.sleep(retry_after)
                response = self.session.post(url, data=data, headers=request_headers, timeout=15)
            response.raise_for_status()
            return response
        except requests.exceptions.HTTPError as e:
            logger.exception("HTTP error posting to %s: %s", url, e)
            raise
        except requests.exceptions.RequestException as e:
            logger.exception("Request failed for %s: %s", url, e)
            raise

    # Extra sold/out-of-stock phrases specific to one portal (subclasses).
    SOLD_MARKERS: tuple = ()

    def _raw_get(self, url: str) -> Optional[requests.Response]:
        """Rate-limited GET that hands back 4xx responses instead of raising
        (a 404 is the answer we want here) — None on a network error."""
        status.update(self.portal_name, f"[{self.portal_name}] check {url}")
        self._rate_limit()
        try:
            return self.session.get(url, headers=self.session.headers.copy(), timeout=15, allow_redirects=True)
        except requests.exceptions.RequestException as e:
            logger.debug("Availability check failed for %s: %s", url, e)
            return None

    def check_availability(self, listing_id: str, url: str) -> Optional[bool]:
        """Is this listing still for sale? True / False (sold, expired,
        removed) / None (couldn't tell — leave it as it is). Works for any
        portal from the page itself (see availability_from_page); portals
        with a cleaner signal (Shopify's product JSON) override it."""
        response = self._raw_get(url)
        if response is None:
            return None
        return availability_from_page(
            response.status_code, url, str(response.url), response.text,
            GENERIC_SOLD_MARKERS + tuple(self.SOLD_MARKERS),
        )

    def shopify_availability(self, url: str) -> Optional[bool]:
        """Shopify's /products/<handle>.js: "available" is false once every
        variant is sold out; a removed product answers 404."""
        response = self._raw_get(url.split("?")[0].rstrip("/") + ".js")
        if response is None:
            return None
        if response.status_code in (404, 410):
            return False
        if response.status_code >= 400:
            return None
        try:
            available = response.json().get("available")
        except ValueError:
            return None
        return bool(available) if available is not None else None

    @abstractmethod
    def search(self, query: str, **kwargs) -> List[Dict[str, Any]]:
        """Search for listings. Must be implemented by subclasses."""
        pass

    @abstractmethod
    def get_listing_details(self, listing_id: str, url: str) -> Dict[str, Any]:
        """Fetch detailed listing info. Must be implemented by subclasses."""
        pass
