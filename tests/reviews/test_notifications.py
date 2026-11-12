import pytest
from tests.reviews.test_models_and_services import FailingAdapter, FakeAdapter, item

from apps.notifications.models import NotificationOutbox, NotificationRecipient
from apps.reviews.application.services import RunReviewScrapeUseCase


@pytest.mark.django_db
def test_new_reviews_are_grouped_in_one_outbox_event(sources):
    source = sources[0]
    NotificationRecipient.objects.create(name="Ops", email="ops@example.test")
    reviews = [item(), item(external_review_id="gp-2", review_text="Excelente")]
    RunReviewScrapeUseCase(lambda _key: FakeAdapter(reviews), sleep_fn=lambda _: None).execute(
        [source]
    )
    events = NotificationOutbox.objects.filter(event_type=NotificationOutbox.EventType.DATA_CHANGED)
    assert events.count() == 1
    assert "2 nuevas" in events.get().context["summary"]


@pytest.mark.django_db
def test_failures_use_cooldown_and_recovery_is_distinct(sources):
    source = sources[0]
    NotificationRecipient.objects.create(name="Ops", email="ops@example.test")
    failing = RunReviewScrapeUseCase(lambda _key: FailingAdapter([]), sleep_fn=lambda _: None)
    failing.execute([source])
    failing.execute([source])
    assert NotificationOutbox.objects.filter(event_type="SCRAPE_FAILED").count() == 1

    RunReviewScrapeUseCase(lambda _key: FakeAdapter([item()]), sleep_fn=lambda _: None).execute(
        [source]
    )
    assert NotificationOutbox.objects.filter(event_type="SCRAPE_RECOVERED").count() == 1
