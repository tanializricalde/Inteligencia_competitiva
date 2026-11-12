import httpx
from django.conf import settings

from scraping_core.adapters.legacy_pricing import PerseoPlanScraper


class PerseoPlanProviderScraper(PerseoPlanScraper):
    """Django wrapper that injects the application's HTTP limits."""

    def __init__(self, client: httpx.Client | None = None):
        super().__init__(
            client,
            user_agent=settings.SCRAPER_USER_AGENT,
            max_response_bytes=settings.SCRAPER_MAX_RESPONSE_BYTES,
            allow_private_hosts=settings.SCRAPER_ALLOW_PRIVATE_HOSTS,
        )
