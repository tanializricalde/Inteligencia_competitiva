from decimal import Decimal
from pathlib import Path

import pytest

from apps.scraping.infrastructure.providers.idrixcontable_plans import (
    IdrixContablePlanProviderScraper,
)
from scraping_core.adapters import IdrixContablePlanScraper
from scraping_core.errors import StructureChangedError, SuspiciousEmptyResultError
from scraping_core.plans import Periodicity

FIXTURE = Path(__file__).parents[1] / "fixtures" / "providers" / "idrixcontable_plans.html"
SOURCE_URL = "https://idrixcontable.com/planes"


def test_idrix_parser_extracts_only_the_accounting_tab_with_variable_radix_id():
    plans = IdrixContablePlanScraper()._parse(FIXTURE.read_text(encoding="utf-8"), SOURCE_URL)

    assert [plan.original_name for plan in plans] == [
        "Plan Services",
        "Plan Pro",
        "Plan Full",
        "Plan Ultra",
    ]
    assert [plan.monthly_price for plan in plans] == [
        Decimal("24.99"),
        Decimal("34.99"),
        Decimal("49.99"),
        Decimal("99.99"),
    ]
    assert all(plan.product == "sistema-contable" for plan in plans)
    assert all(plan.currency == "USD" for plan in plans)
    assert all(plan.periodicity == Periodicity.MONTHLY for plan in plans)
    assert "Plan ajeno" not in {plan.original_name for plan in plans}

    services, _, full, ultra = plans
    assert services.raw_payload["implementation_price"] == "150.00"
    assert services.normalized_features["usuarios_2"]["value"] == 2
    assert services.normalized_features["usuarios_contador_1"]["value"] == 1
    assert services.normalized_features["facturacion_electronica"]["category"] == "Comunes"
    assert full.raw_payload["recommended"] is True
    assert ultra.raw_payload["target_segment"] == "Empresas de Productos y Servicios"


def test_django_idrix_wrapper_uses_the_shared_parser(settings, tmp_path):
    settings.SCRAPER_USER_AGENT = "Tests/1.0"
    settings.SCRAPER_ALLOW_PRIVATE_HOSTS = False
    settings.SCRAPER_EVIDENCE_DIR = tmp_path
    scraper = IdrixContablePlanProviderScraper()

    plans = scraper._parse(FIXTURE.read_text(encoding="utf-8"), SOURCE_URL)

    assert len(plans) == 4
    assert scraper.wait_selector == '[id$="-content-contable"] h3'


@pytest.mark.parametrize(
    "html, error",
    [
        ("<main><h3>Sin panel</h3></main>", StructureChangedError),
        ('<div id="radix-new-content-contable"></div>', SuspiciousEmptyResultError),
    ],
)
def test_idrix_structure_failures_are_typed(html, error):
    with pytest.raises(error):
        IdrixContablePlanScraper()._parse(html, SOURCE_URL)
