import contextlib
import http.server
import socketserver
import threading
from pathlib import Path

import pytest

from apps.reviews.infrastructure.providers import GoogleMapsReviewsProviderAdapter
from scraping_core.reviews import ReviewSourceDTO

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
def test_django_maps_adapter_renders_and_parses_fixture(settings):
    settings.SCRAPER_ALLOW_PRIVATE_HOSTS = True
    with fixture_server() as base_url:
        source = ReviewSourceDTO(
            id=None,
            provider_code="anfibius",
            platform="google_maps",
            source_url=f"{base_url}/maps_reviews_minimal.html",
            country_code="EC",
            timeout_seconds=3,
            adapter_config={"page_size": 8},
        )
        batch = GoogleMapsReviewsProviderAdapter().scrape(source, None)

    assert len(batch.reviews) == 8
    assert batch.reviews[0].author_name == "Angie Ocampo"
    assert batch.metadata["average_rating"] == 4.8
