import csv
import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from apps.market.models import DataChange, Plan, PlanSnapshot, Provider
from apps.scraping.application.services import RunScrapeUseCase
from apps.scraping.models import ScrapeSource
from scraper_cli.exporters import export_rows
from scraper_cli.schemas import PLAN_FIELDS, map_plan
from scraping_core.plans import (
    Periodicity,
    ScrapedPlanDTO,
    diff_payloads,
    stable_hash,
)


def _plan(
    product: str | None = "facturacion", *, external_id: str | None = "pro"
) -> ScrapedPlanDTO:
    return ScrapedPlanDTO(
        external_id=external_id,
        original_name="Profesional",
        normalized_name="Profesional",
        price=Decimal("49.90"),
        currency="PEN",
        periodicity=Periodicity.MONTHLY,
        price_text="S/ 49.90",
        original_features=[],
        normalized_features={},
        source_url="https://example.test/plans",
        raw_payload={},
        product=product,
    )


class _Scraper:
    adapter_key = "example_httpx"

    def __init__(self, plan: ScrapedPlanDTO):
        self.plan = plan

    def scrape(self, _source):
        return [self.plan]


def test_product_participates_in_hash_and_diff():
    before = {"name": "Profesional", "product": "facturacion", "features": {}}
    after = {"name": "Profesional", "product": "contabilidad", "features": {}}

    assert stable_hash(before).startswith("v2:")
    assert stable_hash(before) != stable_hash(after)
    assert diff_payloads(before, after)["product"] == {
        "before": "facturacion",
        "after": "contabilidad",
    }


@pytest.mark.django_db
def test_product_is_persisted_in_current_plan_snapshot_and_change():
    provider = Provider.objects.create(name="Proveedor", code="provider")
    source = ScrapeSource.objects.create(
        provider=provider,
        name="Planes",
        target_url="https://example.test/plans",
        adapter_key="example_httpx",
    )

    RunScrapeUseCase(lambda _key: _Scraper(_plan())).execute([source])

    plan = Plan.objects.get()
    snapshot = PlanSnapshot.objects.get()
    assert plan.product == "facturacion"
    assert snapshot.observed_product == "facturacion"

    RunScrapeUseCase(lambda _key: _Scraper(_plan("contabilidad"))).execute([source])

    plan.refresh_from_db()
    assert plan.product == "contabilidad"
    assert PlanSnapshot.objects.count() == 2
    assert DataChange.objects.latest("id").diff["product"] == {
        "before": "facturacion",
        "after": "contabilidad",
    }


def test_product_differentiates_generated_plan_ids():
    first, _ = map_plan(
        _plan(external_id=None),
        provider_code="provider",
        provider_name="Proveedor",
        ingested_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    second, _ = map_plan(
        _plan("contabilidad", external_id=None),
        provider_code="provider",
        provider_name="Proveedor",
        ingested_at=datetime(2026, 1, 2, tzinfo=UTC),
    )

    assert first["plan_id"] != second["plan_id"]


def test_product_is_exported_to_csv_and_json(tmp_path):
    row, _ = map_plan(
        _plan(),
        provider_code="provider",
        provider_name="Proveedor",
        ingested_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    csv_path = tmp_path / "plans.csv"
    json_path = tmp_path / "plans.json"

    export_rows([row], PLAN_FIELDS, output_format="csv", output=csv_path)
    export_rows([row], PLAN_FIELDS, output_format="json", output=json_path)

    with csv_path.open(encoding="utf-8", newline="") as stream:
        csv_row = next(csv.DictReader(stream))
    json_row = json.loads(json_path.read_text(encoding="utf-8"))[0]
    assert csv_row["producto"] == "facturacion"
    assert json_row["producto"] == "facturacion"
