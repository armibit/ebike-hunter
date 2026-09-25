import logging
from typing import Dict, List, Any
from .base import BaseConnector

logger = logging.getLogger(__name__)


class DecathlonConnector(BaseConnector):
    """
    Connector for Decathlon.ch e-bike 2nd hand marketplace.

    Stub: decathlon.ch is behind a Cloudflare Turnstile managed challenge that
    detects headless/automated browsers (confirmed via curl_cffi TLS
    impersonation and Playwright with stealth patches — both stuck on the
    "Just a moment..." interstitial). Bypassing it needs an undetected-browser
    fork or a paid CAPTCHA-solving service, disproportionate for this project.
    Skipped automatically; check manually via the dashboard link instead.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__("decathlon", config)
        self.base_url = config["portals"]["decathlon"]["base_url"]

    def search(self, limit: int = 50) -> List[Dict[str, Any]]:
        logger.info("Decathlon skipping (blocked by Cloudflare Turnstile — check manually)")
        return []

    def get_listing_details(self, listing_id: str, url: str) -> Dict[str, Any]:
        return {}

    def search_all(self) -> List[Dict[str, Any]]:
        return self.search()
