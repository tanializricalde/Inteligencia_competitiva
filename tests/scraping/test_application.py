from decimal import Decimal

import pytest

from apps.market.domain import Periodicity
from apps.market.models import DataChange, PlanSnapshot, Provider
from apps.notifications.models import NotificationOutbox, NotificationRecipient
from apps.scraping.application.dtos import ScrapedPlanDTO
from apps.scraping.application.errors import TransportError
from apps.scraping.application.services import RunScrapeUseCase
from apps.scraping.models import ScrapeRun, ScrapeSource


def scraped_plan(price="49.90", product="facturacion"):
    return ScrapedPlanDTO(
        external_id="basic",
        original_name="Básico",
        normalized_name="Básico",
        price=Decimal(price),
        currency="PEN",
        periodicity=Periodicity.MONTHLY,
        price_text=f"S/ {price}",
        original_features=["5 usuarios"],
        normalized_features={"users": {"state": "offered", "value": "5", "original": "5 usuarios"}},
        source_url="https://example.test/plans",
        raw_payload={"id": "basic"},
        product=product,
    )


class FakeScraper:
    adapter_key = "example_httpx"

    def __init__(self, plans):
        self.plans = plans

    def scrape(self, _source):
        return self.plans


class FailingScraper:
    adapter_key = "example_httpx"

    def scrape(self, _source):
        raise TransportError("connection refused token=redacted")


@pytest.fixture
def source(db):
    provider = Provider.objects.create(name="Proveedor", code="provider")
    return ScrapeSource.objects.create(
        provider=provider,
        name="Planes",
        target_url="https://example.test/plans",
        adapter_key="example_httpx",
    )


@pytest.fixture
def recipient(db):
    return NotificationRecipient.objects.create(name="Ops", email="ops@example.test")


@pytest.mark.django_db
def test_success_without_changes_does_not_duplicate_snapshot_or_email(source, recipient):
    resolver = lambda _key: FakeScraper([scraped_plan()])  # noqa: E731
    runner = RunScrapeUseCase(resolver)

    first = runner.execute([source])
    second = runner.execute([source])

    assert first.total_changes == 1
    assert second.total_changes == 0
    assert PlanSnapshot.objects.count() == 1
    assert NotificationOutbox.objects.filter(event_type="DATA_CHANGED").count() == 1


@pytest.mark.django_db
def test_changed_price_creates_snapshot_and_structured_diff(source, recipient):
    RunScrapeUseCase(lambda _key: FakeScraper([scraped_plan()])).execute([source])

    run = RunScrapeUseCase(lambda _key: FakeScraper([scraped_plan("59.90")])).execute([source])

    assert run.total_changes == 1
    assert PlanSnapshot.objects.count() == 2
    assert DataChange.objects.latest("id").diff["price"] == {
        "before": "49.90",
        "after": "59.90",
    }


@pytest.mark.django_db
def test_failure_preserves_previous_snapshot_and_enqueues_deduplicated_error(source, recipient):
    RunScrapeUseCase(lambda _key: FakeScraper([scraped_plan()])).execute([source])

    first = RunScrapeUseCase(lambda _key: FailingScraper()).execute([source])
    second = RunScrapeUseCase(lambda _key: FailingScraper()).execute([source])

    assert first.status == ScrapeRun.Status.FAILED
    assert second.status == ScrapeRun.Status.FAILED
    assert PlanSnapshot.objects.count() == 1
    assert NotificationOutbox.objects.filter(event_type="SCRAPE_FAILED").count() == 1


@pytest.mark.django_db
def test_recovery_after_error_enqueues_recovery(source, recipient):
    RunScrapeUseCase(lambda _key: FailingScraper()).execute([source])

    run = RunScrapeUseCase(lambda _key: FakeScraper([scraped_plan()])).execute([source])

    assert run.status == ScrapeRun.Status.SUCCEEDED
    assert NotificationOutbox.objects.filter(event_type="SCRAPE_RECOVERED").count() == 1


@pytest.mark.django_db
def test_mixed_sources_produce_partial_run(source):
    other = ScrapeSource.objects.create(
        provider=source.provider,
        name="Other",
        target_url="https://other.example.test/plans",
        adapter_key="example_playwright",
    )

    def resolver(key):
        return FakeScraper([scraped_plan()]) if key == "example_httpx" else FailingScraper()

    run = RunScrapeUseCase(resolver).execute([source, other])

    assert run.status == ScrapeRun.Status.PARTIAL
    assert run.total_errors == 1
