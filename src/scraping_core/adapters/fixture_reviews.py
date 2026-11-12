from datetime import datetime
from typing import Any

from scraping_core.errors import (
    ReviewConfigurationError,
    ReviewStructureChangedError,
    ReviewTransportError,
)
from scraping_core.reviews import (
    ReviewScrapeBatch,
    ReviewScrapeCheckpoint,
    ReviewSourceDTO,
    ScrapedReviewDTO,
    ensure_utc,
    normalize_country_code,
)


def _parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ReviewStructureChangedError("La fecha fixture debe ser ISO-8601")
    try:
        return ensure_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError as exc:
        raise ReviewStructureChangedError("Fecha ISO-8601 inválida en fixture") from exc


def _source_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ReviewStructureChangedError("Los textos fixture deben ser cadenas o null")
    return value


class BaseFixtureReviewsAdapter:
    adapter_key = "fixture_reviews"
    supports_app_fields = False

    def __init__(self) -> None:
        self.last_attempts = 0

    def validate_config(self, source: ReviewSourceDTO) -> None:
        rows = source.adapter_config.get("fixture_reviews")
        if not isinstance(rows, list):
            raise ReviewConfigurationError(
                "El adapter fixture requiere adapter_config.fixture_reviews como lista"
            )
        page_size = source.adapter_config.get("page_size", 50)
        if not isinstance(page_size, int) or not 1 <= page_size <= 200:
            raise ReviewConfigurationError("page_size debe estar entre 1 y 200")
        failures = source.adapter_config.get("simulate_transient_failures", 0)
        if not isinstance(failures, int) or failures < 0:
            raise ReviewConfigurationError("simulate_transient_failures debe ser no negativo")

    def scrape(
        self,
        source: ReviewSourceDTO,
        checkpoint: ReviewScrapeCheckpoint | None,
    ) -> ReviewScrapeBatch:
        self.validate_config(source)
        status = source.adapter_config.get("simulate_http_status")
        if isinstance(status, int) and 400 <= status < 500:
            self.last_attempts = 1
            raise ReviewTransportError(f"Respuesta HTTP no transitoria simulada: {status}")
        failures = source.adapter_config.get("simulate_transient_failures", 0)
        for attempt in range(1, source.retry_limit + 2):
            self.last_attempts = attempt
            if attempt <= failures:
                continue
            return self._read_page(source, checkpoint, attempt)
        raise ReviewTransportError("Se agotaron los reintentos transitorios simulados")

    def _read_page(
        self,
        source: ReviewSourceDTO,
        checkpoint: ReviewScrapeCheckpoint | None,
        attempts: int,
    ) -> ReviewScrapeBatch:
        rows = source.adapter_config["fixture_reviews"]
        offset = int((checkpoint.cursor if checkpoint else {}).get("offset", 0))
        page_size = source.adapter_config.get("page_size", 50)
        selected = rows[offset : offset + page_size]
        reviews = [self._to_dto(source, row) for row in selected]
        end = offset + len(selected)
        return ReviewScrapeBatch(
            reviews=reviews,
            next_checkpoint=ReviewScrapeCheckpoint({"offset": end}),
            has_more=end < len(rows),
            metadata={
                "offset": offset,
                "returned": len(reviews),
                "fixture": True,
                "attempts": attempts,
            },
        )

    def _to_dto(self, source: ReviewSourceDTO, row: Any) -> ScrapedReviewDTO:
        if not isinstance(row, dict):
            raise ReviewStructureChangedError("Cada reseña fixture debe ser un objeto")
        rating = row.get("rating")
        helpful_votes = row.get("helpful_votes")
        author_name = _source_text(row.get("author_name"))
        review_text = _source_text(row.get("review_text"))
        response_text = _source_text(row.get("developer_response_text"))
        return ScrapedReviewDTO(
            external_review_id=row.get("external_review_id"),
            app_id=row.get("app_id") if self.supports_app_fields else None,
            platform=source.platform,
            country_code=normalize_country_code(row.get("country_code") or source.country_code),
            published_at=_parse_datetime(row.get("published_at")),
            author_name=author_name,
            rating=int(rating) if rating is not None else None,
            review_text=review_text,
            app_version=row.get("app_version") if self.supports_app_fields else None,
            helpful_votes=int(helpful_votes) if helpful_votes is not None else None,
            developer_response_text=response_text,
            developer_response_at=_parse_datetime(row.get("developer_response_at")),
            source_url=source.source_url,
            raw_payload=dict(row),
            response_known=row.get("response_known", True),
        )


class FixtureAppReviewsAdapter(BaseFixtureReviewsAdapter):
    adapter_key = "fixture_app_reviews"
    supports_app_fields = True


class FixtureLocationReviewsAdapter(BaseFixtureReviewsAdapter):
    adapter_key = "fixture_location_reviews"
