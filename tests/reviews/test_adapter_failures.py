import pytest

from apps.reviews.application.dtos import ReviewSourceDTO
from apps.reviews.application.errors import ReviewTransportError
from apps.reviews.infrastructure.providers import FixtureAppReviewsAdapter


def source(config, retry_limit=2):
    return ReviewSourceDTO(
        id=1,
        provider_code="competidor",
        platform="google_play",
        source_url="https://example.test/reviews",
        retry_limit=retry_limit,
        adapter_config={"fixture_reviews": [], **config},
    )


def test_transient_failure_retries_within_limit():
    adapter = FixtureAppReviewsAdapter()
    batch = adapter.scrape(source({"simulate_transient_failures": 2}), None)
    assert batch.metadata["attempts"] == 3
    assert adapter.last_attempts == 3


def test_transient_failure_stops_after_retry_limit():
    adapter = FixtureAppReviewsAdapter()
    with pytest.raises(ReviewTransportError):
        adapter.scrape(source({"simulate_transient_failures": 2}, retry_limit=1), None)
    assert adapter.last_attempts == 2


def test_simulated_4xx_is_not_retried():
    adapter = FixtureAppReviewsAdapter()
    with pytest.raises(ReviewTransportError):
        adapter.scrape(source({"simulate_http_status": 404}, retry_limit=5), None)
    assert adapter.last_attempts == 1


def test_fixture_text_and_raw_payload_are_preserved_verbatim():
    adapter = FixtureAppReviewsAdapter()
    batch = adapter.scrape(
        source(
            {
                "fixture_reviews": [
                    {
                        "external_review_id": "html-1",
                        "review_text": "  <p>Hola <strong>mundo</strong></p>  ",
                        "developer_response_text": "<div>Gracias</div>",
                    }
                ]
            }
        ),
        None,
    )
    assert batch.reviews[0].review_text == "  <p>Hola <strong>mundo</strong></p>  "
    assert batch.reviews[0].developer_response_text == "<div>Gracias</div>"
    assert batch.reviews[0].raw_payload["review_text"] == batch.reviews[0].review_text
