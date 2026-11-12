from apps.reviews.application.dtos import ReviewScrapeCheckpoint, ReviewSourceDTO
from apps.reviews.application.errors import ReviewConfigurationError
from apps.reviews.infrastructure.providers import (
    FixtureAppReviewsAdapter,
    FixtureLocationReviewsAdapter,
)


def source(config, platform="google_play"):
    return ReviewSourceDTO(
        id=1,
        provider_code="competidor",
        platform=platform,
        source_url="https://example.test/reviews",
        country_code="EC",
        adapter_config=config,
    )


def test_app_fixture_paginates_and_preserves_unicode_fields():
    config = {
        "page_size": 1,
        "fixture_reviews": [
            {
                "external_review_id": "uno",
                "published_at": "2026-09-20T14:30:00Z",
                "author_name": "José 🚀",
                "rating": 1,
                "review_text": 'Falla, dice "error"\ny se cierra 😞',
                "app_id": "com.example.app",
                "app_version": "3.2.1",
                "helpful_votes": 0,
            },
            {"external_review_id": "dos", "rating": 5, "review_text": None},
        ],
    }
    adapter = FixtureAppReviewsAdapter()
    first = adapter.scrape(source(config), None)
    second = adapter.scrape(source(config), first.next_checkpoint)

    assert first.has_more
    assert first.reviews[0].author_name == "José 🚀"
    assert first.reviews[0].app_id == "com.example.app"
    assert first.reviews[0].helpful_votes == 0
    assert second.reviews[0].external_review_id == "dos"
    assert not second.has_more


def test_location_fixture_never_projects_app_fields():
    config = {
        "fixture_reviews": [
            {"external_review_id": "map-1", "app_id": "ignored", "app_version": "ignored"}
        ]
    }
    batch = FixtureLocationReviewsAdapter().scrape(
        source(config, platform="google_maps"), ReviewScrapeCheckpoint({"offset": 0})
    )
    assert batch.reviews[0].app_id is None
    assert batch.reviews[0].app_version is None


def test_missing_fixture_contract_is_structure_error():
    adapter = FixtureAppReviewsAdapter()
    try:
        adapter.validate_config(source({}))
    except ReviewConfigurationError as exc:
        assert "fixture_reviews" in str(exc)
    else:
        raise AssertionError("La configuración inválida debió fallar")
