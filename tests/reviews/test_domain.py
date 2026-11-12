from datetime import UTC, datetime, timedelta

import pytest

from apps.reviews.domain import normalize_country_code, response_days, stable_review_id


def test_country_code_and_response_days_are_normalized():
    published = datetime(2026, 9, 20, tzinfo=UTC)
    assert normalize_country_code(" ec ") == "EC"
    assert response_days(published, published + timedelta(hours=18)) == pytest.approx(0.75)


@pytest.mark.parametrize("value", ["E", "ECU", "12", "éC"])
def test_invalid_country_code_is_rejected(value):
    with pytest.raises(ValueError):
        normalize_country_code(value)


def test_negative_response_time_is_rejected():
    published = datetime(2026, 9, 20, tzinfo=UTC)
    with pytest.raises(ValueError):
        response_days(published, published - timedelta(seconds=1))


def test_fallback_identity_is_deterministic_and_not_only_text():
    fields = {"author": "Ana", "published": "2026-09-20", "text": "Excelente"}
    first = stable_review_id("google_play:1", None, fields)
    second = stable_review_id("google_play:1", None, fields)
    other_source = stable_review_id("google_play:2", None, fields)
    assert first == second
    assert first != other_source
    assert first[0].startswith("hash-v1:")
