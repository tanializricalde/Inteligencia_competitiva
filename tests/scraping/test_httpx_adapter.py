from pathlib import Path

import httpx
import pytest

from apps.market.domain import Periodicity
from apps.scraping.application.dtos import ScrapeSourceDTO
from apps.scraping.application.errors import (
    HttpResponseError,
    NormalizationError,
    ScrapeTimeoutError,
    StructureChangedError,
    SuspiciousEmptyResultError,
)
from apps.scraping.infrastructure.providers.example_httpx import ExampleHttpxProviderScraper

FIXTURE = Path(__file__).parents[1] / "fixtures" / "providers" / "httpx_plans.html"


def source(retries=2):
    return ScrapeSourceDTO(None, "https://example.test/plans", retry_limit=retries)


def client_with(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def html_response(request, html, status=200):
    return httpx.Response(status, text=html, headers={"content-type": "text/html"}, request=request)


def test_successful_scrape_uses_normalized_contract():
    html = FIXTURE.read_text()
    adapter = ExampleHttpxProviderScraper(client_with(lambda request: html_response(request, html)))

    plans = adapter.scrape(source())

    assert len(plans) == 2
    assert plans[0].normalized_name == "Básico"
    assert str(plans[0].price) == "49.90"
    assert plans[0].periodicity == Periodicity.MONTHLY
    assert plans[0].product == "facturacion"


def test_timeout_retries_then_raises():
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("late", request=request)

    with pytest.raises(ScrapeTimeoutError):
        ExampleHttpxProviderScraper(client_with(handler)).scrape(source(retries=1))
    assert calls == 2


def test_500_is_retried():
    html = FIXTURE.read_text()
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return html_response(request, "error", 500) if calls == 1 else html_response(request, html)

    assert len(ExampleHttpxProviderScraper(client_with(handler)).scrape(source(retries=1))) == 2
    assert calls == 2


def test_404_is_not_retried():
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return html_response(request, "missing", 404)

    with pytest.raises(HttpResponseError):
        ExampleHttpxProviderScraper(client_with(handler)).scrape(source())
    assert calls == 1


def test_changed_html_raises_structure_error():
    adapter = ExampleHttpxProviderScraper(
        client_with(lambda request: html_response(request, "<main>changed</main>"))
    )
    with pytest.raises(StructureChangedError):
        adapter.scrape(source())


def test_invalid_price_raises_normalization_error():
    html = """<section data-plans-root><article class='plan-card'><h2 class='plan-name'>X</h2><span class='plan-price'>consultar</span></article></section>"""  # noqa: E501
    adapter = ExampleHttpxProviderScraper(client_with(lambda request: html_response(request, html)))
    with pytest.raises(NormalizationError):
        adapter.scrape(source())


def test_empty_result_is_suspicious():
    adapter = ExampleHttpxProviderScraper(
        client_with(lambda request: html_response(request, "<section data-plans-root></section>"))
    )
    with pytest.raises(SuspiciousEmptyResultError):
        adapter.scrape(source())
