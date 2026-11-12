from django.conf import settings
from django.core.exceptions import ValidationError

from apps.scraping.application.errors import UnsafeSourceUrlError
from apps.scraping.infrastructure.url_safety import validate_source_url


def validate_safe_source_url(value: str) -> None:
    try:
        validate_source_url(
            value, allow_private_hosts=getattr(settings, "SCRAPER_ALLOW_PRIVATE_HOSTS", False)
        )
    except UnsafeSourceUrlError as exc:
        raise ValidationError(str(exc)) from exc
