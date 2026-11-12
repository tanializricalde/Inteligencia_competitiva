from pathlib import Path

import pytest

from apps.reviews.infrastructure.providers import GoogleMapsReviewsProviderAdapter
from apps.reviews.infrastructure.registry import get_review_adapter as get_django_adapter
from scraping_core.adapters import GoogleMapsReviewsAdapter
from scraping_core.errors import ReviewConfigurationError, ReviewStructureChangedError
from scraping_core.registry import get_review_adapter
from scraping_core.reviews import ReviewSourceDTO

FIXTURE = Path(__file__).parents[1] / "fixtures" / "providers" / "maps_reviews_minimal.html"
RESPONSE_FIXTURE = (
    Path(__file__).parents[1] / "fixtures" / "providers" / "maps_review_response_cards.html"
)
SOURCE_URL = "https://www.google.com/maps/place/Anfibius+Ecuador/"


def source(**overrides):
    values = {
        "id": None,
        "provider_code": "anfibius",
        "platform": "google_maps",
        "source_url": SOURCE_URL,
        "country_code": "EC",
        "adapter_config": {},
    }
    values.update(overrides)
    return ReviewSourceDTO(**values)


def test_maps_fixture_extracts_cards_summary_and_verifiable_raw_fields():
    reviews, metadata, warnings = GoogleMapsReviewsAdapter()._parse_html(
        FIXTURE.read_text(encoding="utf-8"), source()
    )

    assert len(reviews) == 8
    first = reviews[0]
    assert first.external_review_id.startswith("Ci9DQUlR")
    assert first.author_name == "Angie Ocampo"
    assert first.rating == 5
    assert first.country_code == "EC"
    assert first.published_at is None
    assert first.helpful_votes is None
    assert first.developer_response_text is None
    assert first.response_known is True
    assert first.raw_payload == {
        "author_url": (
            "https://www.google.com/maps/contrib/105911604622496548536/reviews?hl=en-GB"
        ),
        "author_id": "105911604622496548536",
        "author_avatar_url": (
            "https://lh3.googleusercontent.com/a/ACg8ocI8sLOV_oxGNhcu3pJhIvbWo0x3X-q-"
            "Fc_tQ4SoJK4Fab92lg=w36-h36-p-rp-mo-br100"
        ),
        "author_review_count": 1,
        "author_stats_text": "1 review",
        "relative_date": "a year ago",
        "displayed_language": "en",
        "is_translation": True,
        "original_text": None,
        "original_language": None,
        "likes": None,
        "owner_response": None,
        "sentiment": None,
    }
    assert "best experiences" in first.review_text
    assert metadata == {
        "average_rating": 4.8,
        "total_reviews": 50,
        "rating_distribution": [
            {"rating": 5, "review_count": 43},
            {"rating": 4, "review_count": 5},
            {"rating": 3, "review_count": 2},
            {"rating": 2, "review_count": 0},
            {"rating": 1, "review_count": 0},
        ],
    }
    assert warnings == ()


def test_maps_owner_response_is_not_counted_as_an_additional_review():
    reviews, _metadata, warnings = GoogleMapsReviewsAdapter()._parse_html(
        RESPONSE_FIXTURE.read_text(encoding="utf-8"), source()
    )

    assert len(reviews) == 2
    assert [review.external_review_id for review in reviews] == [
        "review-with-response",
        "review-without-response",
    ]
    with_response, without_response = reviews
    assert with_response.review_text == "Normal"
    assert with_response.developer_response_text == "Thank you for sharing your rating with us."
    assert with_response.developer_response_at is None
    assert with_response.response_known is True
    assert with_response.raw_payload["owner_response"] == {
        "relative_date": "a year ago",
        "displayed_language": "en",
        "is_translation": True,
    }
    assert without_response.review_text == "The advice was excellent."
    assert without_response.developer_response_text is None
    assert without_response.response_known is True
    assert without_response.raw_payload["owner_response"] is None
    assert warnings == ()


def test_maps_flattens_line_separators_inside_review_and_response_text():
    html = RESPONSE_FIXTURE.read_text(encoding="utf-8")
    html = html.replace("Normal", "Primera línea\nSegunda línea", 1).replace(
        "Thank you for sharing your rating with us.",
        "Primera respuesta\r\nSegunda respuesta",
        1,
    )

    reviews, _metadata, _warnings = GoogleMapsReviewsAdapter()._parse_html(html, source())

    assert reviews[0].review_text == "Primera línea Segunda línea"
    assert reviews[0].developer_response_text == "Primera respuesta Segunda respuesta"
    assert "\n" not in reviews[0].review_text
    assert "\r" not in reviews[0].developer_response_text


def test_maps_adapter_rejects_wrong_platform_unknown_config_and_missing_cards():
    adapter = GoogleMapsReviewsAdapter()

    with pytest.raises(ReviewConfigurationError, match="platform='google_maps'"):
        adapter.validate_config(source(platform="other"))
    with pytest.raises(ReviewConfigurationError, match="desconocida"):
        adapter.validate_config(source(adapter_config={"cookies": "forbidden"}))
    with pytest.raises(ReviewConfigurationError, match="scroll_distance_min"):
        adapter.validate_config(
            source(adapter_config={"scroll_distance_min": 1500, "scroll_distance_max": 500})
        )
    with pytest.raises(ReviewStructureChangedError, match="data-review-id"):
        adapter._parse_html("<html><body></body></html>", source())


def test_maps_adapter_is_registered_in_core_and_django(settings):
    settings.SCRAPER_USER_AGENT = "Tests/1.0"
    settings.SCRAPER_ALLOW_PRIVATE_HOSTS = False

    assert isinstance(get_review_adapter("google_maps_reviews"), GoogleMapsReviewsAdapter)
    assert isinstance(get_django_adapter("google_maps_reviews"), GoogleMapsReviewsProviderAdapter)
