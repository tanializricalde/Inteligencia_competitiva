from apps.scraping.infrastructure.providers.anfibius_plans import AnfibiusPlanProviderScraper
from apps.scraping.infrastructure.providers.example_httpx import ExampleHttpxProviderScraper
from apps.scraping.infrastructure.providers.example_playwright import (
    ExamplePlaywrightProviderScraper,
)
from apps.scraping.infrastructure.providers.idrixcontable_plans import (
    IdrixContablePlanProviderScraper,
)
from apps.scraping.infrastructure.providers.perseo_plans import PerseoPlanProviderScraper
from apps.scraping.infrastructure.providers.siigo_plans import SiigoPlanProviderScraper
from apps.scraping.infrastructure.registry import adapter_keys, register_adapter


def register_builtin_adapters() -> None:
    registered = set(adapter_keys())
    if AnfibiusPlanProviderScraper.adapter_key not in registered:
        register_adapter(AnfibiusPlanProviderScraper.adapter_key, AnfibiusPlanProviderScraper)
    if ExampleHttpxProviderScraper.adapter_key not in registered:
        register_adapter(ExampleHttpxProviderScraper.adapter_key, ExampleHttpxProviderScraper)
    if PerseoPlanProviderScraper.adapter_key not in registered:
        register_adapter(PerseoPlanProviderScraper.adapter_key, PerseoPlanProviderScraper)
    if SiigoPlanProviderScraper.adapter_key not in registered:
        register_adapter(SiigoPlanProviderScraper.adapter_key, SiigoPlanProviderScraper)
    if ExamplePlaywrightProviderScraper.adapter_key not in registered:
        register_adapter(
            ExamplePlaywrightProviderScraper.adapter_key, ExamplePlaywrightProviderScraper
        )
    if IdrixContablePlanProviderScraper.adapter_key not in registered:
        register_adapter(
            IdrixContablePlanProviderScraper.adapter_key,
            IdrixContablePlanProviderScraper,
        )
