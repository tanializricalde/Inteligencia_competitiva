import logging
from collections.abc import Callable, Iterable
from datetime import timedelta
from time import monotonic

from django.db import transaction
from django.template.defaultfilters import slugify
from django.utils import timezone

from apps.market.domain.normalization import diff_payloads, may_retire, stable_hash
from apps.market.models import DataChange, Plan, PlanSnapshot
from apps.notifications.models import NotificationOutbox
from apps.notifications.services import enqueue_notification
from apps.scraping.application.dtos import ProviderScraper, ScrapedPlanDTO, ScrapeSourceDTO
from apps.scraping.application.errors import ScrapeError
from apps.scraping.infrastructure.registry import get_adapter
from apps.scraping.models import (
    ManualScrapeRequest,
    ScheduleConfig,
    ScrapeRun,
    ScrapeSource,
    ScrapeSourceResult,
)

logger = logging.getLogger(__name__)
Clock = Callable[[], object]


class RunScrapeUseCase:
    def __init__(
        self,
        adapter_resolver: Callable[[str], ProviderScraper] = get_adapter,
        clock=timezone.now,
    ):
        self.adapter_resolver = adapter_resolver
        self.clock = clock

    def execute(
        self,
        sources: Iterable[ScrapeSource],
        origin: str = ScrapeRun.Origin.SCHEDULED,
    ) -> ScrapeRun:
        source_list = list(sources)
        now = self.clock()
        run = ScrapeRun.objects.create(
            origin=origin,
            status=ScrapeRun.Status.RUNNING,
            started_at=now,
            total_sources=len(source_list),
        )
        changed = 0
        errors = 0
        plans_seen = 0
        for source in source_list:
            result_changed, result_plans, failed = self._execute_source(run, source)
            changed += result_changed
            plans_seen += result_plans
            errors += int(failed)
        if errors == 0:
            status = ScrapeRun.Status.SUCCEEDED
        elif errors == len(source_list):
            status = ScrapeRun.Status.FAILED
        else:
            status = ScrapeRun.Status.PARTIAL
        run.status = status
        run.finished_at = self.clock()
        run.total_plans = plans_seen
        run.total_changes = changed
        run.total_errors = errors
        run.summary = f"{plans_seen} planes, {changed} cambios, {errors} errores"
        run.save(
            update_fields=(
                "status",
                "finished_at",
                "total_plans",
                "total_changes",
                "total_errors",
                "summary",
            )
        )
        if changed:
            enqueue_notification(
                NotificationOutbox.EventType.DATA_CHANGED,
                f"changes:run:{run.id}",
                "Cambios detectados",
                {"title": "Cambios detectados", "summary": run.summary, "run_id": run.id},
            )
        return run

    def _execute_source(self, run: ScrapeRun, source: ScrapeSource) -> tuple[int, int, bool]:
        result = ScrapeSourceResult.objects.create(
            run=run, source=source, status=ScrapeSourceResult.Status.RUNNING
        )
        started = monotonic()
        previously_failed = source.consecutive_failures > 0
        try:
            scraper = self.adapter_resolver(source.adapter_key)
            plans = scraper.scrape(
                ScrapeSourceDTO(
                    source.id,
                    source.target_url,
                    source.timeout_seconds,
                    source.retry_limit,
                    source.config,
                )
            )
            changed = self._persist_plans(run, source, plans)
        except ScrapeError as exc:
            self._record_failure(source, result, exc, started, run)
            return 0, 0, True
        result.status = ScrapeSourceResult.Status.SUCCEEDED
        result.duration_ms = int((monotonic() - started) * 1000)
        result.plan_count = len(plans)
        result.save(update_fields=("status", "duration_ms", "plan_count"))
        source.last_success_at = self.clock()
        source.last_error_type = ""
        source.last_error_message = ""
        source.consecutive_failures = 0
        source.save(
            update_fields=(
                "last_success_at",
                "last_error_type",
                "last_error_message",
                "consecutive_failures",
            )
        )
        if previously_failed:
            enqueue_notification(
                NotificationOutbox.EventType.SCRAPE_RECOVERED,
                f"recovered:source:{source.id}:run:{run.id}",
                "Fuente recuperada",
                {"title": "Fuente recuperada", "summary": source.name, "run_id": run.id},
            )
        return changed, len(plans), False

    def _record_failure(self, source, result, exc, started, run) -> None:
        message = str(exc)[:500]
        result.status = ScrapeSourceResult.Status.FAILED
        result.duration_ms = int((monotonic() - started) * 1000)
        result.error_type = exc.error_type
        result.error_message = message
        result.save(update_fields=("status", "duration_ms", "error_type", "error_message"))
        source.last_error_at = self.clock()
        source.last_error_type = exc.error_type
        source.last_error_message = message
        source.consecutive_failures += 1
        source.save(
            update_fields=(
                "last_error_at",
                "last_error_type",
                "last_error_message",
                "consecutive_failures",
            )
        )
        cooldown = (
            ScheduleConfig.objects.values_list("error_cooldown_minutes", flat=True).first() or 60
        )
        bucket = int(self.clock().timestamp() // (cooldown * 60))
        enqueue_notification(
            NotificationOutbox.EventType.SCRAPE_FAILED,
            f"failed:source:{source.id}:bucket:{bucket}",
            "Error de scraping",
            {"title": "Error de scraping", "summary": message, "run_id": run.id},
        )

    @transaction.atomic
    def _persist_plans(
        self, run: ScrapeRun, source: ScrapeSource, scraped: list[ScrapedPlanDTO]
    ) -> int:
        changed = 0
        seen: set[int] = set()
        for item in scraped:
            key_source = item.external_id or (
                f"{item.product}-{item.normalized_name}" if item.product else item.normalized_name
            )
            key = slugify(key_source)[:180]
            plan, _ = Plan.objects.get_or_create(
                provider=source.provider,
                stable_key=key,
                defaults={
                    "external_id": item.external_id or "",
                    "name": item.normalized_name,
                    "product": item.product or "",
                },
            )
            seen.add(plan.id)
            payload = {
                "name": item.normalized_name,
                "product": item.product,
                "price": item.price,
                "currency": item.currency,
                "periodicity": item.periodicity,
                "features": item.normalized_features,
            }
            content_hash = stable_hash(payload)
            previous = plan.snapshots.order_by("-observed_at").first()
            if previous and previous.content_hash == content_hash:
                if plan.missing_successes or not plan.is_active:
                    plan.missing_successes = 0
                    plan.is_active = True
                    plan.save(update_fields=("missing_successes", "is_active"))
                continue
            snapshot = PlanSnapshot.objects.create(
                plan=plan,
                observed_at=self.clock(),
                observed_name=item.original_name,
                observed_product=item.product or "",
                amount=item.price,
                currency=item.currency,
                periodicity=item.periodicity,
                price_text=item.price_text,
                features=item.normalized_features,
                raw_data=item.raw_payload,
                content_hash=content_hash,
                run=run,
            )
            previous_payload = None
            if previous:
                previous_payload = {
                    "name": previous.observed_name,
                    "product": previous.observed_product or None,
                    "price": previous.amount,
                    "currency": previous.currency,
                    "periodicity": previous.periodicity,
                    "features": previous.features,
                }
            diff = diff_payloads(previous_payload, payload)
            kind = (
                DataChange.Kind.PLAN_ADDED
                if previous is None
                else DataChange.Kind.PRICE_CHANGED
                if "price" in diff
                else DataChange.Kind.DETAILS_CHANGED
            )
            DataChange.objects.create(
                kind=kind, previous_snapshot=previous, new_snapshot=snapshot, diff=diff
            )
            plan.name = item.normalized_name
            plan.product = item.product or ""
            plan.is_active = True
            plan.missing_successes = 0
            plan.save(update_fields=("name", "product", "is_active", "missing_successes"))
            changed += 1
        missing = Plan.objects.filter(provider=source.provider, is_active=True).exclude(id__in=seen)
        for plan in missing:
            plan.missing_successes += 1
            if may_retire(plan.missing_successes):
                plan.is_active = False
                DataChange.objects.create(
                    kind=DataChange.Kind.PLAN_RETIRED,
                    previous_snapshot=plan.snapshots.order_by("-observed_at").first(),
                    diff={"missing_successes": plan.missing_successes},
                )
                changed += 1
            plan.save(update_fields=("missing_successes", "is_active"))
        return changed


class ProcessManualRequests:
    lease_duration = timedelta(minutes=30)

    def __init__(self, runner: RunScrapeUseCase | None = None, clock=timezone.now):
        self.runner = runner or RunScrapeUseCase()
        self.clock = clock

    def recover_expired(self) -> int:
        return ManualScrapeRequest.objects.filter(
            status=ManualScrapeRequest.Status.RUNNING, lease_expires_at__lt=self.clock()
        ).update(
            status=ManualScrapeRequest.Status.PENDING,
            started_at=None,
            lease_expires_at=None,
            error_message="Recuperada tras expirar el lease",
        )

    def process_one(self) -> ManualScrapeRequest | None:
        with transaction.atomic():
            request = (
                ManualScrapeRequest.objects.select_for_update()
                .filter(status=ManualScrapeRequest.Status.PENDING)
                .order_by("created_at")
                .first()
            )
            if request is None:
                return None
            if (
                request.source_id
                and ManualScrapeRequest.objects.filter(
                    source_id=request.source_id,
                    status=ManualScrapeRequest.Status.RUNNING,
                    lease_expires_at__gte=self.clock(),
                )
                .exclude(pk=request.pk)
                .exists()
            ):
                return None
            request.status = ManualScrapeRequest.Status.RUNNING
            request.started_at = self.clock()
            request.lease_expires_at = self.clock() + self.lease_duration
            request.save(update_fields=("status", "started_at", "lease_expires_at"))
        sources = (
            ScrapeSource.objects.filter(
                pk=request.source_id, is_active=True, provider__data_scope="real"
            )
            if request.source_id
            else ScrapeSource.objects.filter(is_active=True, provider__data_scope="real")
        )
        try:
            run = self.runner.execute(sources, origin=ScrapeRun.Origin.MANUAL)
        except Exception as exc:
            request.status = ManualScrapeRequest.Status.FAILED
            request.error_message = type(exc).__name__
        else:
            request.status = ManualScrapeRequest.Status.COMPLETED
            request.run = run
        request.finished_at = self.clock()
        request.lease_expires_at = None
        request.save(
            update_fields=("status", "error_message", "run", "finished_at", "lease_expires_at")
        )
        return request
