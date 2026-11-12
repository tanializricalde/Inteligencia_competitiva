from collections.abc import Callable

from scraping_core.adapters import (
    AnfibiusPlanScraper,
    FixtureAppReviewsAdapter,
    FixtureLocationReviewsAdapter,
    FixturePlanScraper,
    GoogleMapsReviewsAdapter,
    HttpxPlanScraper,
    IdrixContablePlanScraper,
    PerseoPlanScraper,
    PlaywrightPlanScraper,
    SiigoPlanScraper,
)
from scraping_core.plans import PlanScraper
from scraping_core.reviews import ReviewScraperAdapter

PlanFactory = Callable[[], PlanScraper]
ReviewFactory = Callable[[], ReviewScraperAdapter]

PLAN_ADAPTERS: dict[str, PlanFactory] = {
    "anfibius_plans": AnfibiusPlanScraper,
    "example_httpx": HttpxPlanScraper,
    "example_playwright": PlaywrightPlanScraper,
    "fixture_plans": FixturePlanScraper,
    "idrixcontable_plans": IdrixContablePlanScraper,
    "perseo_plans": PerseoPlanScraper,
    "siigo_plans": SiigoPlanScraper,
}

REVIEW_ADAPTERS: dict[str, ReviewFactory] = {
    "fixture_app_reviews": FixtureAppReviewsAdapter,
    "fixture_location_reviews": FixtureLocationReviewsAdapter,
    "google_maps_reviews": GoogleMapsReviewsAdapter,
}


def get_plan_adapter(key: str) -> PlanScraper:
    try:
        return PLAN_ADAPTERS[key]()
    except KeyError as exc:
        raise ValueError(f"Adapter de planes no registrado: {key!r}") from exc


def get_review_adapter(key: str) -> ReviewScraperAdapter:
    try:
        return REVIEW_ADAPTERS[key]()
    except KeyError as exc:
        raise ValueError(f"Adapter de reseñas no registrado: {key!r}") from exc
