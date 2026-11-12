import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol

OBSERVATION_HASH_VERSION = "review-observation-v1"
IDENTITY_HASH_VERSION = "review-identity-v1"


@dataclass(frozen=True, slots=True)
class ReviewSourceDTO:
    id: int | None
    provider_code: str
    platform: str
    source_url: str
    external_entity_id: str | None = None
    country_code: str | None = None
    timeout_seconds: int = 20
    retry_limit: int = 2
    request_delay_seconds: float = 0
    max_items: int | None = None
    adapter_config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ReviewScrapeCheckpoint:
    cursor: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ScrapedReviewDTO:
    external_review_id: str | None
    app_id: str | None
    platform: str
    country_code: str | None
    published_at: datetime | None
    author_name: str | None
    rating: int | None
    review_text: str | None
    app_version: str | None
    helpful_votes: int | None
    developer_response_text: str | None
    developer_response_at: datetime | None
    source_url: str
    raw_payload: dict[str, Any] | None = None
    response_known: bool | None = None


@dataclass(frozen=True, slots=True)
class ReviewScrapeBatch:
    reviews: list[ScrapedReviewDTO]
    next_checkpoint: ReviewScrapeCheckpoint | None = None
    has_more: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()


class ReviewScraperAdapter(Protocol):
    adapter_key: str

    def validate_config(self, source: ReviewSourceDTO) -> None: ...

    def scrape(
        self, source: ReviewSourceDTO, checkpoint: ReviewScrapeCheckpoint | None
    ) -> ReviewScrapeBatch: ...


def normalize_country_code(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    normalized = value.strip().upper()
    if len(normalized) != 2 or not normalized.isalpha() or not normalized.isascii():
        raise ValueError("El país debe ser un código ISO-2 de dos letras")
    return normalized


def ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Las fechas de reseñas deben incluir zona horaria")
    return value.astimezone(UTC)


def response_days(published_at: datetime | None, response_at: datetime | None) -> Decimal | None:
    if published_at is None or response_at is None:
        return None
    published = ensure_utc(published_at)
    response = ensure_utc(response_at)
    if response < published:
        raise ValueError("La respuesta no puede ser anterior al comentario")
    return Decimal(str((response - published).total_seconds() / 86400))


def stable_review_id(
    source_namespace: str, external_id: str | None, fields: dict[str, Any]
) -> tuple[str, str]:
    if external_id and external_id.strip():
        value = external_id.strip()
        digest = hashlib.sha256(f"{source_namespace}:{value}".encode()).hexdigest()
        return f"{source_namespace}:{value}"[:240], f"external:{digest}"
    canonical = json.dumps(
        {"version": IDENTITY_HASH_VERSION, "source": source_namespace, **fields},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    return f"hash-v1:{digest}", f"fallback:{digest}"


def observation_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        {"version": OBSERVATION_HASH_VERSION, **payload},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return f"v1:{hashlib.sha256(canonical.encode()).hexdigest()}"
