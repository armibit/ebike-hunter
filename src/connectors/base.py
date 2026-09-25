import logging
import time
import random
from curl_cffi import requests
from typing import Dict, List, Optional, Any
from abc import ABC, abstractmethod
from utils.console import status

logger = logging.getLogger(__name__)


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

    def get(self, url: str, params: Optional[Dict] = None, headers: Optional[Dict] = None) -> requests.Response:
        """Rate-limited GET request with retry on 429/5xx."""
        status.update(f"[{self.portal_name}] GET {url}")
        self._rate_limit()

        request_headers = self.session.headers.copy()
        if headers:
            request_headers.update(headers)

        try:
            response = self.session.get(url, params=params, headers=request_headers, timeout=15)
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 60))
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
            logger.error("HTTP error fetching %s: %s", url, e)
            raise
        except requests.exceptions.RequestException as e:
            logger.error("Request failed for %s: %s", url, e)
            raise

    def post(self, url: str, data: Optional[Dict] = None, headers: Optional[Dict] = None) -> requests.Response:
        """Rate-limited POST request with retry on 429."""
        status.update(f"[{self.portal_name}] POST {url}")
        self._rate_limit()

        request_headers = self.session.headers.copy()
        if headers:
            request_headers.update(headers)

        try:
            response = self.session.post(url, data=data, headers=request_headers, timeout=15)
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 60))
                logger.warning("Rate limited by %s — sleeping %ds", url, retry_after)
                time.sleep(retry_after)
                response = self.session.post(url, data=data, headers=request_headers, timeout=15)
            response.raise_for_status()
            return response
        except requests.exceptions.HTTPError as e:
            logger.error("HTTP error posting to %s: %s", url, e)
            raise
        except requests.exceptions.RequestException as e:
            logger.error("Request failed for %s: %s", url, e)
            raise

    @abstractmethod
    def search(self, query: str, **kwargs) -> List[Dict[str, Any]]:
        """Search for listings. Must be implemented by subclasses."""
        pass

    @abstractmethod
    def get_listing_details(self, listing_id: str, url: str) -> Dict[str, Any]:
        """Fetch detailed listing info. Must be implemented by subclasses."""
        pass
