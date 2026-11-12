from apps.reviews.infrastructure.providers import (
    FixtureAppReviewsAdapter,
    FixtureLocationReviewsAdapter,
    GoogleMapsReviewsProviderAdapter,
)
from apps.reviews.infrastructure.registry import (
    register_review_adapter,
    review_adapter_keys,
)


def register_builtin_review_adapters() -> None:
    registered = set(review_adapter_keys())
    for adapter in (
        FixtureAppReviewsAdapter,
        FixtureLocationReviewsAdapter,
        GoogleMapsReviewsProviderAdapter,
    ):
        if adapter.adapter_key not in registered:
            register_review_adapter(adapter.adapter_key, adapter)
