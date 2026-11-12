from datetime import UTC, datetime

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.market.models import Provider
from apps.reviews.application.dtos import ReviewScrapeBatch, ScrapedReviewDTO
from apps.reviews.application.errors import ReviewTransportError
from apps.reviews.application.services import (
    ProcessManualReviewRequests,
    RunReviewScrapeUseCase,
    process_pending_enrichments,
)
from apps.reviews.models import (
    ManualReviewRequest,
    MarketReview,
    ReviewEnrichment,
    ReviewObservation,
    ReviewRun,
    ReviewSource,
)


class FakeAdapter:
    adapter_key = "fake"

    def __init__(self, reviews):
        self.reviews = reviews

    def validate_config(self, _source):
        return None

    def scrape(self, _source, _checkpoint):
        return ReviewScrapeBatch(self.reviews)


class FailingAdapter(FakeAdapter):
    def scrape(self, _source, _checkpoint):
        raise ReviewTransportError("timeout")


def item(**overrides):
    values = {
        "external_review_id": "gp-1",
        "app_id": "com.example",
        "platform": ReviewSource.Platform.GOOGLE_PLAY,
        "country_code": "ec",
        "published_at": datetime(2026, 9, 20, 14, 30, tzinfo=UTC),
        "author_name": "Ana",
        "rating": 1,
        "review_text": "La app se cierra con error",
        "app_version": "3.2.1",
        "helpful_votes": 0,
        "developer_response_text": None,
        "developer_response_at": None,
        "source_url": "https://example.test/app",
        "raw_payload": {"fixture": True},
        "response_known": False,
    }
    values.update(overrides)
    return ScrapedReviewDTO(**values)


@pytest.fixture
def providers(db):
    return (
        Provider.objects.create(name="Uno", code="uno"),
        Provider.objects.create(name="Dos", code="dos"),
    )


@pytest.fixture
def sources(providers):
    one, two = providers
    common = {
        "platform": ReviewSource.Platform.GOOGLE_PLAY,
        "adapter_key": "fixture_app_reviews",
        "enabled": True,
        "request_delay_seconds": 0,
        "adapter_config": {"fixture_reviews": []},
    }
    return (
        ReviewSource.objects.create(
            provider=one, name="App EC", source_url="https://one.example.test/app", **common
        ),
        ReviewSource.objects.create(
            provider=one,
            name="App PE",
            source_url="https://one.example.test/app-pe",
            **common,
        ),
        ReviewSource.objects.create(
            provider=two, name="App EC", source_url="https://two.example.test/app", **common
        ),
    )


@pytest.mark.django_db
def test_multiple_sources_and_shared_adapter_key_are_supported(sources):
    first, second, third = sources
    assert first.provider == second.provider
    assert first.adapter_key == third.adapter_key


@pytest.mark.django_db
def test_source_validates_country_rating_and_uniqueness(sources):
    first = sources[0]
    first.country_code = "ecu"
    with pytest.raises(ValidationError):
        first.full_clean()


@pytest.mark.django_db
def test_idempotency_and_new_observation_on_response(sources):
    source = sources[0]
    runner = RunReviewScrapeUseCase(lambda _key: FakeAdapter([item()]), sleep_fn=lambda _: None)
    first = runner.execute([source])
    second = runner.execute([source])
    answered = item(
        developer_response_text="Escríbenos a soporte",
        developer_response_at=datetime(2026, 9, 21, 9, 15, tzinfo=UTC),
        response_known=True,
    )
    third = RunReviewScrapeUseCase(
        lambda _key: FakeAdapter([answered]), sleep_fn=lambda _: None
    ).execute([source])

    assert first.total_new == 1
    assert second.total_updated == 0
    assert third.total_updated == 1
    assert third.total_responses == 1
    assert MarketReview.objects.count() == 1
    assert ReviewObservation.objects.count() == 2
    assert ReviewEnrichment.objects.filter(status="pending").count() == 2


@pytest.mark.django_db
def test_partial_failure_does_not_cancel_other_source(sources):
    good, bad, _ = sources

    def resolver(key):
        return FakeAdapter([item()]) if key == "good" else FailingAdapter([])

    good.adapter_key = "good"
    bad.adapter_key = "bad"
    good.save(update_fields=("adapter_key",))
    bad.save(update_fields=("adapter_key",))
    run = RunReviewScrapeUseCase(resolver, sleep_fn=lambda _: None).execute([good, bad])
    assert run.status == ReviewRun.Status.PARTIAL
    assert run.total_new == 1
    assert run.total_errors == 1


@pytest.mark.django_db
def test_pending_enrichment_is_deferred_and_deterministic(sources):
    source = sources[0]
    RunReviewScrapeUseCase(lambda _key: FakeAdapter([item()]), sleep_fn=lambda _: None).execute(
        [source]
    )
    enrichment = ReviewEnrichment.objects.get()
    assert enrichment.category is None and enrichment.sentiment is None
    assert process_pending_enrichments() == 1
    enrichment.refresh_from_db()
    assert enrichment.status == ReviewEnrichment.Status.COMPLETED
    assert enrichment.category == "Errores técnicos"
    assert enrichment.sentiment == "Negativo"


@pytest.mark.django_db
def test_manual_request_runs_only_provider_sources(sources, django_user_model):
    user = django_user_model.objects.create_user("ops@example.test", "password")
    request = ManualReviewRequest.objects.create(provider=sources[0].provider, requested_by=user)
    fake_runner = RunReviewScrapeUseCase(
        lambda _key: FakeAdapter([item()]), sleep_fn=lambda _: None
    )
    ProcessManualReviewRequests(runner=fake_runner).process_one()
    request.refresh_from_db()
    assert request.status == ManualReviewRequest.Status.COMPLETED
    assert request.run.total_sources == 2


@pytest.mark.django_db
def test_manual_review_worker_excludes_demo_sources(django_user_model):
    user = django_user_model.objects.create_user("demo-reviews@example.test", "password")
    provider = Provider.objects.create(
        name="Demo aislado",
        code="demo_legacy_reviews",
        data_scope=Provider.DataScope.DEMO,
    )
    source = ReviewSource.objects.create(
        provider=provider,
        name="Fuente demo no operativa",
        platform=ReviewSource.Platform.OTHER,
        adapter_key="fixture_app_reviews",
        source_url="https://example.test/reviews",
        enabled=True,
    )
    ManualReviewRequest.objects.create(source=source, requested_by=user)

    class RecordingRunner:
        source_ids = None

        def execute(self, sources, *, origin):
            self.source_ids = list(sources.values_list("id", flat=True))
            return ReviewRun.objects.create(origin=origin, started_at=timezone.now())

    runner = RecordingRunner()
    ProcessManualReviewRequests(runner=runner).process_one()

    assert runner.source_ids == []
