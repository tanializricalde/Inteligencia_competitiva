"""Sequential, database-free scraper orchestration."""

from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime

from scraper_cli.config import CliConfig, ConfigError, ProviderConfig, selected_providers
from scraper_cli.schemas import map_plan, map_review
from scraping_core.adapters import (
    AnfibiusPlanScraper,
    GoogleMapsReviewsAdapter,
    HttpxPlanScraper,
    IdrixContablePlanScraper,
    PerseoPlanScraper,
    PlaywrightPlanScraper,
    SiigoPlanScraper,
)
from scraping_core.plans import PlanSourceDTO
from scraping_core.registry import get_plan_adapter, get_review_adapter
from scraping_core.reviews import ReviewSourceDTO, normalize_country_code


@dataclass(slots=True)
class RunResult:
    rows: list[dict] = field(default_factory=list)
    feature_rows: list[dict] = field(default_factory=list)
    attempted: int = 0
    succeeded: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def failed(self) -> int:
        return len(self.errors)

    @property
    def exit_code(self) -> int:
        if self.errors:
            return 4 if self.succeeded else 3
        return 4 if self.warnings else 0


def _sources(providers: tuple[ProviderConfig, ...], kind: str, names: list[str] | None):
    requested = set(names or [])
    found: set[str] = set()
    selected = []
    for provider in providers:
        sources = provider.plan_sources if kind == "plans" else provider.review_sources
        for source in sources:
            if not source.enabled:
                continue
            if requested and source.name not in requested:
                continue
            found.add(source.name)
            selected.append((provider, source))
    missing = sorted(requested - found)
    if missing:
        raise ConfigError(f"--source: fuente activa inexistente: {', '.join(missing)}")
    return selected


def _plan_adapter(key: str, config: CliConfig):
    defaults = config.defaults
    if key == "anfibius_plans":
        return AnfibiusPlanScraper(
            user_agent=defaults.user_agent,
            allow_private_hosts=defaults.allow_private_hosts,
            max_response_bytes=defaults.max_response_bytes,
        )
    if key == "example_httpx":
        return HttpxPlanScraper(
            user_agent=defaults.user_agent,
            max_response_bytes=defaults.max_response_bytes,
            allow_private_hosts=defaults.allow_private_hosts,
        )
    if key == "siigo_plans":
        return SiigoPlanScraper(
            user_agent=defaults.user_agent,
            max_response_bytes=defaults.max_response_bytes,
            allow_private_hosts=defaults.allow_private_hosts,
        )
    if key == "perseo_plans":
        return PerseoPlanScraper(
            user_agent=defaults.user_agent,
            max_response_bytes=defaults.max_response_bytes,
            allow_private_hosts=defaults.allow_private_hosts,
        )
    if key == "example_playwright":
        return PlaywrightPlanScraper(
            user_agent=defaults.user_agent,
            allow_private_hosts=defaults.allow_private_hosts,
        )
    if key == "idrixcontable_plans":
        return IdrixContablePlanScraper(
            user_agent=defaults.user_agent,
            allow_private_hosts=defaults.allow_private_hosts,
        )
    return get_plan_adapter(key)


def run_plans(
    config: CliConfig,
    *,
    provider_codes: list[str] | None = None,
    source_names: list[str] | None = None,
    limit: int | None = None,
    timeout: int | None = None,
    fail_fast: bool = False,
) -> RunResult:
    result = RunResult()
    maximum = limit or config.defaults.max_items
    ingested_at = datetime.now(UTC)
    providers = selected_providers(config, provider_codes)
    for provider, source in _sources(providers, "plans", source_names):
        result.attempted += 1
        try:
            dto = PlanSourceDTO(
                id=None,
                url=source.url,
                timeout_seconds=timeout
                or source.timeout_seconds
                or config.defaults.timeout_seconds,
                retry_limit=source.retry_limit,
                config=source.config,
            )
            plans = _plan_adapter(source.adapter_key, config).scrape(dto)[:maximum]
            for plan in plans:
                row, feature_rows = map_plan(
                    plan,
                    provider_code=provider.code,
                    provider_name=provider.name,
                    ingested_at=ingested_at,
                )
                result.rows.append(row)
                result.feature_rows.extend(feature_rows)
            result.succeeded += 1
        except Exception as exc:
            result.errors.append(f"{provider.code}/{source.name}: {type(exc).__name__}: {exc}")
            if fail_fast:
                break
    return result


def _review_adapter(key: str, config: CliConfig):
    if key == "google_maps_reviews":
        return GoogleMapsReviewsAdapter(
            user_agent=config.defaults.user_agent,
            allow_private_hosts=config.defaults.allow_private_hosts,
        )
    return get_review_adapter(key)


def run_reviews(
    config: CliConfig,
    *,
    provider_codes: list[str] | None = None,
    source_names: list[str] | None = None,
    limit: int | None = None,
    timeout: int | None = None,
    country: str | None = None,
    fail_fast: bool = False,
) -> RunResult:
    result = RunResult()
    if country is not None:
        try:
            country = normalize_country_code(country)
        except ValueError as exc:
            raise ConfigError(f"--country: {exc}") from exc
    maximum = limit or config.defaults.max_items
    ingested_at = datetime.now(UTC)
    providers = selected_providers(config, provider_codes)
    for provider, source in _sources(providers, "reviews", source_names):
        result.attempted += 1
        try:
            dto = ReviewSourceDTO(
                id=None,
                provider_code=provider.code,
                platform=source.platform,
                source_url=source.url,
                external_entity_id=source.app_id,
                country_code=country or source.country_code or config.defaults.country_code,
                timeout_seconds=timeout
                or source.timeout_seconds
                or config.defaults.timeout_seconds,
                retry_limit=source.retry_limit,
                request_delay_seconds=source.request_delay_seconds,
                max_items=maximum,
                adapter_config=source.config,
            )
            adapter = _review_adapter(source.adapter_key, config)
            checkpoint = None
            collected = 0
            source_warnings: list[str] = []
            last_batch = None
            for _page in range(source.max_pages):
                batch = adapter.scrape(dto, checkpoint)
                last_batch = batch
                source_warnings.extend(batch.warnings)
                for review in batch.reviews:
                    if collected >= maximum:
                        break
                    if review.app_id is None and source.app_id is not None:
                        review = replace(review, app_id=source.app_id)
                    result.rows.append(
                        map_review(
                            review,
                            provider_code=provider.code,
                            source_name=source.name,
                            ingested_at=ingested_at,
                        )
                    )
                    collected += 1
                if collected >= maximum or not batch.has_more:
                    break
                checkpoint = batch.next_checkpoint
                if checkpoint is None:
                    raise RuntimeError("El adapter indicó más páginas sin checkpoint")
                if source.request_delay_seconds:
                    time.sleep(source.request_delay_seconds)
            else:
                raise RuntimeError(f"Se alcanzó max_pages={source.max_pages}")
            total = last_batch.metadata.get("total_reviews") if last_batch is not None else None
            expected = min(maximum, total) if isinstance(total, int) else maximum
            completed_request = collected >= expected or (
                last_batch is not None
                and not last_batch.has_more
                and last_batch.metadata.get("partial") is False
            )
            if completed_request:
                source_warnings = [
                    warning
                    for warning in source_warnings
                    if not warning.startswith("Resultado parcial:")
                ]
            result.warnings.extend(
                f"{provider.code}/{source.name}: {warning}" for warning in source_warnings
            )
            result.succeeded += 1
        except Exception as exc:
            result.errors.append(f"{provider.code}/{source.name}: {type(exc).__name__}: {exc}")
            if fail_fast:
                break
    return result
