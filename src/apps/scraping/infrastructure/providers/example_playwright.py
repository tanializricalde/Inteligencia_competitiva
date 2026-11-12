from pathlib import Path

from django.conf import settings
from playwright.sync_api import sync_playwright

from scraping_core.adapters.plans_playwright import PlaywrightPlanScraper


class ExamplePlaywrightProviderScraper(PlaywrightPlanScraper):
    adapter_key = "example_playwright"

    def __init__(self, playwright_factory=sync_playwright, evidence_dir: Path | None = None):
        super().__init__(
            playwright_factory,
            evidence_dir=evidence_dir or Path(settings.SCRAPER_EVIDENCE_DIR),
            user_agent=settings.SCRAPER_USER_AGENT,
            allow_private_hosts=settings.SCRAPER_ALLOW_PRIVATE_HOSTS,
        )
