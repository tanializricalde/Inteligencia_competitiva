from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from apps.scraping.application.dtos import ScrapeSourceDTO
from apps.scraping.infrastructure.providers.anfibius_plans import AnfibiusPlanProviderScraper
from apps.scraping.infrastructure.providers.perseo_plans import PerseoPlanProviderScraper
from scraping_core.adapters import AnfibiusPlanScraper, PerseoPlanScraper
from scraping_core.errors import StructureChangedError
from scraping_core.plans import Periodicity

FIXTURES = Path(__file__).parents[1] / "fixtures" / "providers"
ANFIBIUS_URL = (
    "https://anfibius.net/planes-de-facturacion-electronica-cual-elegir-segun-tu-empresa/"
)
PERSEO_URL = "https://tusistemacontable.com/"


def _html(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _client(html: str) -> httpx.Client:
    def response(request):
        return httpx.Response(
            200,
            text=html,
            headers={"content-type": "text/html; charset=utf-8"},
            request=request,
        )

    return httpx.Client(transport=httpx.MockTransport(response))


def test_anfibius_http_adapter_maps_editorial_plans_without_inventing_prices():
    scraper = AnfibiusPlanScraper(_client(_html("anfibius_plans.html")))

    plans = scraper.scrape(ScrapeSourceDTO(None, ANFIBIUS_URL))

    assert [plan.original_name for plan in plans] == [
        "Básico",
        "Estándar",
        "Premium / Corporativo",
    ]
    assert {plan.product for plan in plans} == {"facturacion-electronica"}
    assert all(plan.price is None for plan in plans)
    assert all(plan.periodicity == Periodicity.UNKNOWN for plan in plans)
    assert "almacenamiento_seguro" in plans[0].normalized_features


def test_django_anfibius_wrapper_uses_the_shared_http_parser(settings):
    settings.SCRAPER_USER_AGENT = "Tests/1.0"
    settings.SCRAPER_MAX_RESPONSE_BYTES = 100_000
    settings.SCRAPER_ALLOW_PRIVATE_HOSTS = False
    scraper = AnfibiusPlanProviderScraper(_client(_html("anfibius_plans.html")))

    plans = scraper.scrape(ScrapeSourceDTO(None, ANFIBIUS_URL))

    assert [plan.original_name for plan in plans] == [
        "Básico",
        "Estándar",
        "Premium / Corporativo",
    ]


def test_perseo_http_adapter_preserves_web_pc_and_prime_prices():
    scraper = PerseoPlanScraper(_client(_html("perseo_plans.html")))

    plans = scraper.scrape(ScrapeSourceDTO(None, PERSEO_URL))

    assert len(plans) == 3
    web, pc, prime = plans
    assert web.product == "perseo-web"
    assert web.monthly_price == Decimal("17.99")
    assert web.annual_total_price == Decimal("173.99")
    assert pc.product == "perseo-pc"
    assert pc.monthly_price == Decimal("58.00")
    assert pc.annual_total_price == Decimal("500.00")
    assert pc.raw_payload["one_time_price"] == "1400.00"
    assert prime.product == "perseo-prime"
    assert prime.periodicity == Periodicity.YEARLY
    assert prime.normalized_features["usuarios_4_aplicacion_movil_1"]["value"] == 4
    assert prime.annual_total_price == Decimal("750.00")
    assert prime.effective_monthly_price == Decimal("62.50")


def test_django_perseo_wrapper_uses_the_shared_parser(settings):
    settings.SCRAPER_USER_AGENT = "Tests/1.0"
    settings.SCRAPER_MAX_RESPONSE_BYTES = 100_000
    settings.SCRAPER_ALLOW_PRIVATE_HOSTS = False
    scraper = PerseoPlanProviderScraper(_client(_html("perseo_plans.html")))

    plans = scraper.scrape(ScrapeSourceDTO(None, PERSEO_URL))

    assert [plan.original_name for plan in plans] == ["FACTURACIÓN", "CONTROL", "NIVEL 1"]


@pytest.mark.parametrize("adapter", [AnfibiusPlanScraper(), PerseoPlanScraper()])
def test_legacy_pricing_structure_change_is_typed(adapter):
    with pytest.raises(StructureChangedError, match="tarjetas de precios"):
        adapter._parse("<main><h1>Sin planes</h1></main>", "https://example.test/plans")
