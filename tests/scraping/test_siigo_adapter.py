from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from apps.market.domain import FeatureState, Periodicity
from apps.scraping.application.dtos import ScrapeSourceDTO
from apps.scraping.application.errors import StructureChangedError, SuspiciousEmptyResultError
from apps.scraping.infrastructure.providers.siigo_plans import SiigoPlanProviderScraper
from scraping_core.adapters import SiigoPlanScraper

FIXTURE = Path(__file__).parents[1] / "fixtures" / "providers" / "siigo_planes.html"
SOURCE_URL = "https://www.siigo.com/ec/planes/"


def _client(html: str) -> httpx.Client:
    def response(request):
        return httpx.Response(
            200,
            text=html,
            headers={"content-type": "text/html; charset=utf-8"},
            request=request,
        )

    return httpx.Client(transport=httpx.MockTransport(response))


def test_siigo_next_data_maps_prices_discounts_periods_and_features():
    scraper = SiigoPlanScraper(_client(FIXTURE.read_text(encoding="utf-8")))

    plans = scraper.scrape(ScrapeSourceDTO(None, SOURCE_URL))

    assert len(plans) == 1
    plan = plans[0]
    assert plan.external_id == "9700003000182"
    assert plan.original_name == "Sistema Contable Premium"
    assert plan.product == "accounting-suscripcion"
    assert plan.periodicity == Periodicity.CUSTOM
    assert plan.price == Decimal("567.00")
    assert plan.monthly_price == Decimal("54.00")
    assert plan.annual_total_price == Decimal("567.00")
    assert plan.effective_monthly_price == Decimal("47.25")
    assert plan.discount_percentage == Decimal("30.00")
    assert plan.price_after_discount == Decimal("567.00")
    assert plan.is_offer_active is True
    assert plan.promotion_text.startswith("Mensual: -20%")
    assert "Anual: -30%" in plan.promotion_text
    assert plan.currency == "USD"
    assert set(plan.raw_payload) == {"monthly", "annual"}
    assert plan.normalized_features["multiples_bodegas"]["state"] == (FeatureState.OFFERED)


def test_django_siigo_wrapper_uses_same_parser(settings):
    settings.SCRAPER_USER_AGENT = "Tests/1.0"
    settings.SCRAPER_MAX_RESPONSE_BYTES = 100_000
    settings.SCRAPER_ALLOW_PRIVATE_HOSTS = False
    scraper = SiigoPlanProviderScraper(_client(FIXTURE.read_text(encoding="utf-8")))

    plans = scraper.scrape(ScrapeSourceDTO(None, SOURCE_URL))

    assert [plan.original_name for plan in plans] == ["Sistema Contable Premium"]


def test_siigo_rejects_incompatible_monthly_and_annual_variants():
    html = FIXTURE.read_text(encoding="utf-8").replace(
        '"currency": "USD",\n                      "originalPrice": "810.00"',
        '"currency": "EUR",\n                      "originalPrice": "810.00"',
    )
    scraper = SiigoPlanScraper(_client(html))

    with pytest.raises(StructureChangedError, match="difieren en currency"):
        scraper.scrape(ScrapeSourceDTO(None, SOURCE_URL))


@pytest.mark.parametrize(
    "html, message",
    [
        ("<html></html>", "__NEXT_DATA__"),
        (
            '<script id="__NEXT_DATA__" type="application/json">{invalid}</script>',
            "JSON válido",
        ),
        (
            '<script id="__NEXT_DATA__" type="application/json">{"props": {}}</script>',
            "props.pageProps.products.products",
        ),
        (
            '<script id="__NEXT_DATA__" type="application/json">'
            '{"props":{"pageProps":{"products":{"products":{}}}}}'
            "</script>",
            "productos configurados",
        ),
    ],
)
def test_siigo_contract_failures_are_typed(html, message):
    scraper = SiigoPlanScraper(_client(html))
    expected = (
        SuspiciousEmptyResultError if message == "productos configurados" else StructureChangedError
    )

    with pytest.raises(expected, match=message):
        scraper.scrape(ScrapeSourceDTO(None, SOURCE_URL))
