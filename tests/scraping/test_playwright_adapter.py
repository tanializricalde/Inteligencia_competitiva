import contextlib
import http.server
import socketserver
import threading
from pathlib import Path

import pytest

from apps.market.domain import Periodicity
from apps.scraping.application.dtos import ScrapeSourceDTO
from apps.scraping.application.errors import ScrapeTimeoutError
from apps.scraping.infrastructure.providers.example_playwright import (
    ExamplePlaywrightProviderScraper,
)
from scraping_core.adapters import IdrixContablePlanScraper
from scraping_core.plans import PlanSourceDTO

FIXTURES = Path(__file__).parents[1] / "fixtures" / "providers"


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, _format, *_args):
        return


@contextlib.contextmanager
def fixture_server():
    handler = lambda *args, **kwargs: QuietHandler(*args, directory=FIXTURES, **kwargs)  # noqa: E731
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_address[1]}"
        finally:
            server.shutdown()
            thread.join(timeout=2)


@pytest.mark.playwright
def test_javascript_render_and_normalization(settings):
    settings.SCRAPER_ALLOW_PRIVATE_HOSTS = True
    with fixture_server() as base_url:
        plans = ExamplePlaywrightProviderScraper().scrape(
            ScrapeSourceDTO(None, f"{base_url}/playwright_plans.html", timeout_seconds=3)
        )

    assert len(plans) == 2
    assert plans[0].normalized_name == "Básico"
    assert str(plans[0].price) == "49.90"
    assert plans[0].periodicity == Periodicity.MONTHLY


@pytest.mark.playwright
def test_timeout_waiting_for_selector(settings):
    settings.SCRAPER_ALLOW_PRIVATE_HOSTS = True
    with fixture_server() as base_url, pytest.raises(ScrapeTimeoutError):
        ExamplePlaywrightProviderScraper().scrape(
            ScrapeSourceDTO(None, f"{base_url}/empty_page.html", timeout_seconds=1)
        )


@pytest.mark.playwright
def test_idrix_waits_for_and_parses_the_accounting_panel():
    with fixture_server() as base_url:
        plans = IdrixContablePlanScraper(allow_private_hosts=True).scrape(
            PlanSourceDTO(
                None,
                f"{base_url}/idrixcontable_plans.html",
                timeout_seconds=3,
            )
        )

    assert [plan.original_name for plan in plans] == [
        "Plan Services",
        "Plan Pro",
        "Plan Full",
        "Plan Ultra",
    ]
