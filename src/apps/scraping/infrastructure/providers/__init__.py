from apps.scraping.infrastructure.providers.anfibius_plans import AnfibiusPlanProviderScraper
from apps.scraping.infrastructure.providers.example_httpx import ExampleHttpxProviderScraper
from apps.scraping.infrastructure.providers.idrixcontable_plans import (
    IdrixContablePlanProviderScraper,
)
from apps.scraping.infrastructure.providers.perseo_plans import PerseoPlanProviderScraper
from apps.scraping.infrastructure.providers.siigo_plans import SiigoPlanProviderScraper

__all__ = [
    "AnfibiusPlanProviderScraper",
    "ExampleHttpxProviderScraper",
    "IdrixContablePlanProviderScraper",
    "PerseoPlanProviderScraper",
    "SiigoPlanProviderScraper",
]
