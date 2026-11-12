import httpx
import pytest

from scraping_core.adapters import HttpxPlanScraper
from scraping_core.errors import HttpResponseError, UnsafeSourceUrlError
from scraping_core.plans import PlanSourceDTO
from scraping_core.security import validate_source_url


@pytest.mark.parametrize(
    "url",
    ("http://127.0.0.1/plans", "http://169.254.169.254/latest", "http://localhost/plans"),
)
def test_core_rejects_private_and_local_destinations(url):
    with pytest.raises(UnsafeSourceUrlError):
        validate_source_url(url)


def test_http_adapter_does_not_follow_redirects():
    def redirect(request):
        return httpx.Response(
            302, headers={"location": "http://127.0.0.1/private"}, request=request
        )

    adapter = HttpxPlanScraper(httpx.Client(transport=httpx.MockTransport(redirect)))
    source = PlanSourceDTO(None, "https://example.test/plans")

    with pytest.raises(HttpResponseError, match="redirecciones"):
        adapter.scrape(source)
