import pytest

from apps.market.models import Provider
from apps.reviews.models import ReviewSource


@pytest.fixture
def sources(db):
    provider = Provider.objects.create(name="Fixture Provider", code="fixture-provider")
    other = Provider.objects.create(name="Other Provider", code="other-provider")
    common = {
        "platform": ReviewSource.Platform.GOOGLE_PLAY,
        "adapter_key": "fixture_app_reviews",
        "enabled": True,
        "request_delay_seconds": 0,
        "adapter_config": {"fixture_reviews": []},
    }
    return (
        ReviewSource.objects.create(
            provider=provider,
            name="App EC",
            source_url="https://fixture.example.test/app",
            **common,
        ),
        ReviewSource.objects.create(
            provider=provider,
            name="App PE",
            source_url="https://fixture.example.test/app-pe",
            **common,
        ),
        ReviewSource.objects.create(
            provider=other,
            name="App EC",
            source_url="https://other.example.test/app",
            **common,
        ),
    )
