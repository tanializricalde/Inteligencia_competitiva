import logging
from collections.abc import Callable, Iterable
from datetime import timedelta
from time import monotonic, sleep

from django.db import transaction
from django.utils import timezone

from apps.notifications.models import NotificationOutbox
from apps.notifications.services import enqueue_notification
from apps.reviews.application.dtos import (
    ReviewScrapeCheckpoint,
    ReviewSourceDTO,
    ScrapedReviewDTO,
)
from apps.reviews.application.errors import (
    ReviewSourceBusyError,
    ReviewValidationError,
)
from apps.reviews.domain import (
    ensure_utc,
    normalize_country_code,
    observation_hash,
    response_days,
    stable_review_id,
)
from apps.reviews.infrastructure.registry import get_review_adapter
from apps.reviews.models import (
    ManualReviewRequest,
    MarketReview,
    ReviewEnrichment,
    ReviewObservation,
    ReviewRun,
    ReviewSource,
    ReviewSourceResult,
)

logger = logging.getLogger(__name__)


class RunReviewScrapeUseCase:
    def __init__(
        self,
        adapter_resolver=get_review_adapter,
        clock=timezone.now,
        sleep_fn: Callable[[float], None] = sleep,
    ):
        self.adapter_resolver = adapter_resolver
        self.clock = clock
        self.sleep_fn = sleep_fn

    def execute(
        self,
        sources: Iterable[ReviewSource],
        origin: str = ReviewRun.Origin.SCHEDULED,
    ) -> ReviewRun:
        source_list = list(sources)
        run = ReviewRun.objects.create(
            origin=origin,
            status=ReviewRun.Status.RUNNING,
            started_at=self.clock(),
            total_sources=len(source_list),
        )
        totals = {"found": 0, "new": 0, "updated": 0, "responses": 0, "errors": 0}
        for source in source_list:
            outcome = self._execute_source(run, source)
            for key in totals:
                totals[key] += outcome[key]
        if totals["errors"] == 0:
            status = ReviewRun.Status.SUCCEEDED
        elif totals["errors"] == len(source_list):
            status = ReviewRun.Status.FAILED
        else:
            status = ReviewRun.Status.PARTIAL
        run.status = status
        run.finished_at = self.clock()
        run.total_reviews = totals["found"]
        run.total_new = totals["new"]
        run.total_updated = totals["updated"]
        run.total_responses = totals["responses"]
        run.total_errors = totals["errors"]
        run.summary = (
            f"{totals['found']} reseñas, {totals['new']} nuevas, "
            f"{totals['updated']} actualizadas, {totals['responses']} respuestas, "
            f"{totals['errors']} errores"
        )
        run.save(
            update_fields=(
                "status",
                "finished_at",
                "total_reviews",
                "total_new",
                "total_updated",
                "total_responses",
                "total_errors",
                "summary",
            )
        )
        if totals["new"] or totals["responses"]:
            enqueue_notification(
                NotificationOutbox.EventType.DATA_CHANGED,
                f"review-changes:run:{run.id}",
                "Novedades en reseñas",
                {"title": "Novedades en reseñas", "summary": run.summary, "run_id": run.id},
            )
        return run

    def _claim_source(self, source: ReviewSource) -> None:
        claimed = (
            ReviewSource.objects.filter(pk=source.pk)
            .exclude(state=ReviewSource.State.RUNNING)
            .update(state=ReviewSource.State.RUNNING)
        )
        if not claimed:
            raise ReviewSourceBusyError("La fuente ya tiene una ejecución activa")

    def _execute_source(self, run: ReviewRun, source: ReviewSource) -> dict[str, int]:
        result = ReviewSourceResult.objects.create(
            run=run,
            source=source,
            status=ReviewSourceResult.Status.RUNNING,
            started_at=self.clock(),
        )
        started = monotonic()
        previously_failed = source.consecutive_failures > 0
        counters = {"found": 0, "new": 0, "updated": 0, "responses": 0, "errors": 0}
        pages = warnings = known_streak = 0
        try:
            self._claim_source(source)
            adapter = self.adapter_resolver(source.adapter_key)
            dto = self._source_dto(source)
            adapter.validate_config(dto)
            checkpoint_data = dict(source.last_cursor)
            if "offset" in checkpoint_data:
                checkpoint_data["offset"] = max(
                    0, int(checkpoint_data["offset"]) - source.review_window
                )
            checkpoint = ReviewScrapeCheckpoint(checkpoint_data) if checkpoint_data else None
            while pages < source.max_pages and counters["found"] < source.max_reviews:
                batch = adapter.scrape(dto, checkpoint)
                remaining = source.max_reviews - counters["found"]
                selected = batch.reviews[:remaining]
                persisted = self._persist_batch(run, result, source, selected)
                counters["found"] += len(selected)
                counters["new"] += persisted["new"]
                counters["updated"] += persisted["updated"]
                counters["responses"] += persisted["responses"]
                known_streak = known_streak + persisted["known"] if persisted["known"] else 0
                pages += 1
                warnings += len(batch.warnings)
                next_cursor = batch.next_checkpoint.cursor if batch.next_checkpoint else {}
                source.last_cursor = next_cursor
                source.save(update_fields=("last_cursor", "updated_at"))
                if not batch.has_more or len(selected) < len(batch.reviews):
                    break
                if checkpoint and next_cursor == checkpoint.cursor:
                    raise ReviewValidationError("El adapter no avanzó el checkpoint")
                if known_streak >= source.review_window:
                    break
                checkpoint = batch.next_checkpoint
                if source.request_delay_seconds:
                    self.sleep_fn(float(source.request_delay_seconds))
        except Exception as exc:  # Adapter boundary: isolate one source from the remaining run.
            self._record_failure(source, result, exc, started, run)
            counters["errors"] = 1
            return counters

        now = self.clock()
        result.status = ReviewSourceResult.Status.SUCCEEDED
        result.finished_at = now
        result.duration_ms = int((monotonic() - started) * 1000)
        result.pages = pages
        result.found_count = counters["found"]
        result.new_count = counters["new"]
        result.updated_count = counters["updated"]
        result.new_response_count = counters["responses"]
        result.warning_count = warnings
        result.save(
            update_fields=(
                "status",
                "finished_at",
                "duration_ms",
                "pages",
                "found_count",
                "new_count",
                "updated_count",
                "new_response_count",
                "warning_count",
            )
        )
        source.state = ReviewSource.State.IDLE
        source.last_success_at = now
        source.last_error_type = ""
        source.last_error_message = ""
        source.consecutive_failures = 0
        source.save(
            update_fields=(
                "state",
                "last_success_at",
                "last_error_type",
                "last_error_message",
                "consecutive_failures",
                "updated_at",
            )
        )
        if previously_failed:
            enqueue_notification(
                NotificationOutbox.EventType.SCRAPE_RECOVERED,
                f"review-recovered:source:{source.id}:run:{run.id}",
                "Fuente de reseñas recuperada",
                {"title": "Fuente recuperada", "summary": source.name, "run_id": run.id},
            )
        logger.info(
            "review_source_complete provider_code=%s review_source_id=%s platform=%s "
            "adapter_key=%s run_id=%s pages=%s found=%s new=%s updated=%s responses=%s",
            source.provider.code,
            source.id,
            source.platform,
            source.adapter_key,
            run.id,
            pages,
            counters["found"],
            counters["new"],
            counters["updated"],
            counters["responses"],
        )
        return counters

    def _source_dto(self, source: ReviewSource) -> ReviewSourceDTO:
        return ReviewSourceDTO(
            id=source.id,
            provider_code=source.provider.code,
            platform=source.platform,
            source_url=source.source_url,
            external_entity_id=source.external_entity_id or None,
            country_code=source.country_code,
            timeout_seconds=source.timeout_seconds,
            retry_limit=source.retry_limit,
            request_delay_seconds=float(source.request_delay_seconds),
            adapter_config=source.adapter_config,
        )

    def _record_failure(self, source, result, exc, started, run) -> None:
        now = self.clock()
        error_type = getattr(exc, "error_type", type(exc).__name__)[:80]
        message = str(exc)[:500]
        result.status = ReviewSourceResult.Status.FAILED
        result.finished_at = now
        result.duration_ms = int((monotonic() - started) * 1000)
        result.error_type = error_type
        result.error_message = message
        result.save(
            update_fields=(
                "status",
                "finished_at",
                "duration_ms",
                "error_type",
                "error_message",
            )
        )
        source.state = ReviewSource.State.ERROR
        source.last_error_at = now
        source.last_error_type = error_type
        source.last_error_message = message
        source.consecutive_failures += 1
        source.save(
            update_fields=(
                "state",
                "last_error_at",
                "last_error_type",
                "last_error_message",
                "consecutive_failures",
                "updated_at",
            )
        )
        bucket = int(now.timestamp() // 3600)
        enqueue_notification(
            NotificationOutbox.EventType.SCRAPE_FAILED,
            f"review-failed:source:{source.id}:bucket:{bucket}",
            "Error en fuente de reseñas",
            {"title": "Error de reseñas", "summary": message, "run_id": run.id},
        )
        logger.warning(
            "review_source_failed provider_code=%s review_source_id=%s platform=%s "
            "adapter_key=%s run_id=%s error_type=%s",
            source.provider.code,
            source.id,
            source.platform,
            source.adapter_key,
            run.id,
            error_type,
        )

    @transaction.atomic
    def _persist_batch(
        self,
        run: ReviewRun,
        result: ReviewSourceResult,
        source: ReviewSource,
        scraped: list[ScrapedReviewDTO],
    ) -> dict[str, int]:
        counts = {"new": 0, "updated": 0, "responses": 0, "known": 0}
        observed_at = self.clock()
        for item in scraped:
            normalized = self._normalize_item(source, item)
            review_id, identity_hash = stable_review_id(
                f"{source.platform}:{source.id}",
                item.external_review_id,
                {
                    "entity": source.external_entity_id,
                    "published_at": normalized["published_at"],
                    "author_name": item.author_name,
                    "rating": item.rating,
                    "review_text": item.review_text,
                },
            )
            review, created = MarketReview.objects.get_or_create(
                source=source,
                identity_hash=identity_hash,
                defaults={
                    "external_review_id": item.external_review_id or "",
                    "review_id": review_id,
                    "first_seen_at": observed_at,
                    "last_seen_at": observed_at,
                },
            )
            previous = review.observations.order_by("-observed_at").first()
            content_hash = observation_hash(normalized)
            review.last_seen_at = observed_at
            review.is_visible = True
            review.save(update_fields=("last_seen_at", "is_visible", "updated_at"))
            if previous and previous.content_hash == content_hash:
                counts["known"] += 1
                continue
            observation = ReviewObservation(
                review=review,
                observed_at=observed_at,
                content_hash=content_hash,
                run=run,
                source_result=result,
                **normalized,
            )
            observation.full_clean()
            observation.save()
            ReviewEnrichment.objects.create(observation=observation)
            if created:
                counts["new"] += 1
            else:
                counts["updated"] += 1
                if (
                    previous
                    and previous.has_response is not True
                    and observation.has_response is True
                ):
                    counts["responses"] += 1
        return counts

    def _normalize_item(self, source: ReviewSource, item: ScrapedReviewDTO) -> dict:
        if item.platform != source.platform:
            raise ReviewValidationError("La plataforma del DTO no coincide con la fuente")
        if item.rating is not None and not 1 <= item.rating <= 5:
            raise ReviewValidationError("La calificación debe estar entre 1 y 5")
        if item.helpful_votes is not None and item.helpful_votes < 0:
            raise ReviewValidationError("Los votos útiles no pueden ser negativos")
        published = ensure_utc(item.published_at)
        response_at = ensure_utc(item.developer_response_at)
        response_days(published, response_at)
        country = normalize_country_code(item.country_code or source.country_code)
        response_known = item.response_known
        if item.developer_response_text is not None or response_at is not None:
            response_known = True
        return {
            "published_at": published,
            "author_name": item.author_name,
            "rating": item.rating,
            "review_text": item.review_text,
            "app_id": item.app_id,
            "app_version": item.app_version,
            "helpful_votes": item.helpful_votes,
            "developer_response_text": item.developer_response_text,
            "developer_response_at": response_at,
            "response_known": response_known,
            "raw_payload": item.raw_payload,
            # Country is a source/review fact; keep the normalized override in the
            # sanitized payload.
            # The canonical export prefers this value and falls back to ReviewSource.country_code.
            "country_code": country,
        }


class ProcessManualReviewRequests:
    lease_duration = timedelta(minutes=30)

    def __init__(self, runner: RunReviewScrapeUseCase | None = None, clock=timezone.now):
        self.runner = runner or RunReviewScrapeUseCase()
        self.clock = clock

    def recover_expired(self) -> int:
        recovered = ManualReviewRequest.objects.filter(
            status=ManualReviewRequest.Status.RUNNING, lease_expires_at__lt=self.clock()
        ).update(
            status=ManualReviewRequest.Status.PENDING,
            started_at=None,
            lease_expires_at=None,
            error_message="Recuperada tras expirar el lease",
        )
        ReviewSource.objects.filter(state=ReviewSource.State.RUNNING).update(
            state=ReviewSource.State.IDLE
        )
        return recovered

    def process_one(self) -> ManualReviewRequest | None:
        with transaction.atomic():
            request = (
                ManualReviewRequest.objects.select_for_update()
                .filter(status=ManualReviewRequest.Status.PENDING)
                .order_by("created_at")
                .first()
            )
            if request is None:
                return None
            request.status = ManualReviewRequest.Status.RUNNING
            request.started_at = self.clock()
            request.lease_expires_at = self.clock() + self.lease_duration
            request.save(update_fields=("status", "started_at", "lease_expires_at"))
        sources = ReviewSource.objects.filter(
            enabled=True, provider__data_scope="real"
        ).select_related("provider")
        if request.source_id:
            sources = sources.filter(pk=request.source_id)
        elif request.provider_id:
            sources = sources.filter(provider_id=request.provider_id)
        try:
            run = self.runner.execute(sources, origin=ReviewRun.Origin.MANUAL)
        except Exception as exc:  # final worker boundary; details remain in contextual logs
            request.status = ManualReviewRequest.Status.FAILED
            request.error_message = type(exc).__name__[:500]
        else:
            request.status = ManualReviewRequest.Status.COMPLETED
            request.run = run
        request.finished_at = self.clock()
        request.lease_expires_at = None
        request.save(
            update_fields=("status", "error_message", "run", "finished_at", "lease_expires_at")
        )
        return request


class RuleBasedSpanishAnalyzer:
    name = "rules-es"
    version = "1.0"

    def analyze(self, text: str) -> tuple[str | None, str | None, str]:
        normalized = text.casefold()
        category = None
        if any(word in normalized for word in ("error", "falla", "cierra", "lento")):
            category = "Errores técnicos"
        elif any(word in normalized for word in ("precio", "costo", "caro")):
            category = "Precio"
        positive = any(word in normalized for word in ("excelente", "bueno", "gracias"))
        negative = any(word in normalized for word in ("malo", "error", "falla", "cierra"))
        sentiment = (
            "Positivo" if positive and not negative else "Negativo" if negative else "Neutral"
        )
        return category, sentiment, "0.7000"


def process_pending_enrichments(limit: int = 100, analyzer=None) -> int:
    analyzer = analyzer or RuleBasedSpanishAnalyzer()
    pending = ReviewEnrichment.objects.select_related("observation").filter(
        status=ReviewEnrichment.Status.PENDING,
        analyzer=analyzer.name,
        analyzer_version=analyzer.version,
    )[:limit]
    completed = 0
    for enrichment in pending:
        enrichment.status = ReviewEnrichment.Status.PROCESSING
        enrichment.save(update_fields=("status",))
        try:
            text = enrichment.observation.review_text
            if text is None or text == "":
                enrichment.status = ReviewEnrichment.Status.NOT_APPLICABLE
            else:
                category, sentiment, confidence = analyzer.analyze(text)
                enrichment.category = category
                enrichment.sentiment = sentiment
                enrichment.confidence = confidence
                enrichment.status = ReviewEnrichment.Status.COMPLETED
                completed += 1
        except Exception as exc:
            enrichment.status = ReviewEnrichment.Status.FAILED
            enrichment.error_message = type(exc).__name__[:500]
        enrichment.processed_at = timezone.now()
        enrichment.save(
            update_fields=(
                "status",
                "category",
                "sentiment",
                "confidence",
                "processed_at",
                "error_message",
            )
        )
    return completed
