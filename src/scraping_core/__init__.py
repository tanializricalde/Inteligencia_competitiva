"""Núcleo de scraping reutilizable, sin Django, ORM ni base de datos."""

from .plans import (
    FeatureState,
    FeatureValue,
    Periodicity,
    PlanScraper,
    PlanSourceDTO,
    ScrapedPlanDTO,
)
from .reviews import (
    ReviewScrapeBatch,
    ReviewScrapeCheckpoint,
    ReviewScraperAdapter,
    ReviewSourceDTO,
    ScrapedReviewDTO,
)

__all__ = [
    "FeatureState",
    "FeatureValue",
    "Periodicity",
    "PlanScraper",
    "PlanSourceDTO",
    "ReviewScrapeBatch",
    "ReviewScrapeCheckpoint",
    "ReviewScraperAdapter",
    "ReviewSourceDTO",
    "ScrapedPlanDTO",
    "ScrapedReviewDTO",
]
