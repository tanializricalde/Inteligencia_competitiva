import pytest
from django.core.exceptions import ValidationError

from apps.market.models import Provider
from apps.scraping.models import ScrapeSource


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url",
    ["http://127.0.0.1/plans", "http://169.254.169.254/latest", "file:///etc/passwd"],
)
def test_source_rejects_unsafe_urls(url):
    provider = Provider.objects.create(name="Provider", code="provider")
    source = ScrapeSource(
        provider=provider,
        name="Unsafe",
        target_url=url,
        adapter_key="example_httpx",
    )

    with pytest.raises(ValidationError):
        source.full_clean()
