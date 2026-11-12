from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Protocol

from django.db import transaction
from django.utils import timezone

from apps.market.models import Provider
from apps.notifications.models import NotificationOutbox
from apps.notifications.services import enqueue_notification
from apps.pipeline.application.publication import publish_provider_run
from apps.pipeline.models import (
    MarketSource,
    PipelineProfileVersion,
    PipelineRun,
    ProviderRun,
    SourceRun,
    StageRun,
)


@dataclass(frozen=True, slots=True)
class SourceExecutionResult:
    rows_scraped: int = 0
    rows_cleaned: int = 0
    rows_normalized: int = 0
    content_sha256: str = ""
    metadata: dict | None = None


class PipelineSourceExecutor(Protocol):
    def execute(
        self, source: MarketSource, *, pipeline_run: PipelineRun
    ) -> SourceExecutionResult: ...

    def finalize_provider(self, provider_run: ProviderRun) -> None: ...


def provider_failure_summary(provider_run: ProviderRun) -> str:
    """Return the first concrete source failure, falling back to its stage."""
    stages = sorted(provider_run.stage_runs.all(), key=lambda item: (item.sequence, item.id))
    for stage_run in stages:
        failed_sources = sorted(
            (
                source
                for source in stage_run.source_runs.all()
                if source.status == StageRun.Status.FAILED
            ),
            key=lambda item: (item.sequence, item.id),
        )
        if failed_sources:
            source_run = failed_sources[0]
            detail = ": ".join(
                part for part in (source_run.error_type, source_run.error_message) if part
            ) or "Fallo sin detalle"
            return f"{stage_run.stage}/{source_run.market_source.code}: {detail}"[:2000]
    for stage_run in stages:
        if stage_run.status == StageRun.Status.FAILED:
            detail = ": ".join(
                part for part in (stage_run.error_type, stage_run.error_message) if part
            ) or "Fallo sin detalle"
            return f"{stage_run.stage}: {detail}"[:2000]
    return "Una etapa requerida no pudo completarse"


class PipelineOrchestrator:
    STAGES = (
        StageRun.Stage.PLANS,
        StageRun.Stage.FEATURES,
        StageRun.Stage.REVIEWS,
    )
    DATA_TYPE_BY_STAGE = {
        StageRun.Stage.PLANS: MarketSource.DataType.PLANS,
        StageRun.Stage.FEATURES: MarketSource.DataType.FEATURES,
        StageRun.Stage.REVIEWS: MarketSource.DataType.REVIEWS,
    }

    def __init__(
        self,
        executor: PipelineSourceExecutor,
        *,
        publisher: Callable[[ProviderRun], ProviderRun] = publish_provider_run,
        notifier: Callable[..., object | None] = enqueue_notification,
        sleeper: Callable[[float], None] = time.sleep,
        clock=timezone.now,
    ) -> None:
        self.executor = executor
        self.publisher = publisher
        self.notifier = notifier
        self.sleeper = sleeper
        self.clock = clock

    def execute(
        self,
        *,
        profile_version: PipelineProfileVersion,
        trigger_type: str,
        providers: Iterable[Provider] | None = None,
        pipeline_run: PipelineRun | None = None,
    ) -> PipelineRun:
        provider_list = list(
            providers
            if providers is not None
            else Provider.objects.filter(
                is_active=True, data_scope=Provider.DataScope.REAL
            ).order_by("execution_order", "id")
        )
        if any(provider.data_scope != Provider.DataScope.REAL for provider in provider_list):
            raise ValueError("El pipeline operativo sólo admite proveedores REAL")
        run = pipeline_run or PipelineRun.objects.create(
            profile_version=profile_version,
            trigger_type=trigger_type,
            status=PipelineRun.Status.RUNNING,
            started_at=self.clock(),
        )
        if run.profile_version_id != profile_version.id:
            raise ValueError("La reanudación debe usar la versión original del perfil")
        if run.status == PipelineRun.Status.PUBLISHED:
            return run
        if run.started_at is None:
            run.started_at = self.clock()
        run.status = PipelineRun.Status.RUNNING
        run.finished_at = None
        run.save(update_fields=("status", "started_at", "finished_at"))

        provider_runs = self._ensure_provider_runs(run, provider_list)
        for stage_sequence, stage in enumerate(self.STAGES, start=1):
            for provider_run in provider_runs:
                self._execute_stage(provider_run, stage, stage_sequence)

        for provider_run in provider_runs:
            if self._provider_stages_succeeded(provider_run):
                try:
                    self.executor.finalize_provider(provider_run)
                    self.publisher(provider_run)
                except Exception as exc:  # noqa: BLE001 - boundary records provider failure
                    self._fail_provider(provider_run, exc)
            elif provider_run.status not in {
                PipelineRun.Status.FAILED,
                PipelineRun.Status.CANCELLED,
            }:
                provider_run.status = PipelineRun.Status.FAILED
                provider_run.finished_at = self.clock()
                provider_run.error_summary = provider_failure_summary(provider_run)
                provider_run.save(update_fields=("status", "finished_at", "error_summary"))
        self._finish_run(run)
        self._notify_results(run, provider_runs)
        return run

    def execute_diagnostic_stage(
        self,
        *,
        profile_version: PipelineProfileVersion,
        provider: Provider,
        stage: str,
        pipeline_run: PipelineRun | None = None,
    ) -> tuple[PipelineRun, StageRun]:
        if stage not in self.STAGES:
            raise ValueError(f"Etapa inválida: {stage}")
        if provider.data_scope != Provider.DataScope.REAL:
            raise ValueError("El pipeline operativo sólo admite proveedores REAL")
        run = pipeline_run or PipelineRun.objects.create(
            profile_version=profile_version,
            trigger_type=PipelineRun.TriggerType.MANUAL,
            status=PipelineRun.Status.RUNNING,
            started_at=self.clock(),
        )
        if run.profile_version_id != profile_version.id:
            raise ValueError("La ejecución pertenece a otra versión del perfil")
        provider_run = self._ensure_provider_runs(run, [provider])[0]
        sequence = self.STAGES.index(stage) + 1
        self._execute_stage(provider_run, stage, sequence)
        stage_run = provider_run.stage_runs.get(stage=stage)
        run.status = (
            PipelineRun.Status.COMPLETED
            if stage_run.status == StageRun.Status.SUCCEEDED
            else PipelineRun.Status.FAILED
        )
        run.finished_at = self.clock()
        run.save(update_fields=("status", "finished_at"))
        return run, stage_run

    @transaction.atomic
    def _ensure_provider_runs(
        self, run: PipelineRun, providers: list[Provider]
    ) -> list[ProviderRun]:
        results = []
        for sequence, provider in enumerate(providers, start=1):
            provider_run, _ = ProviderRun.objects.get_or_create(
                pipeline_run=run,
                provider=provider,
                defaults={
                    "sequence": sequence,
                    "status": PipelineRun.Status.RUNNING,
                    "started_at": self.clock(),
                },
            )
            if provider_run.status != PipelineRun.Status.PUBLISHED:
                provider_run.status = PipelineRun.Status.RUNNING
                provider_run.finished_at = None
                provider_run.error_summary = ""
                provider_run.save(update_fields=("status", "finished_at", "error_summary"))
            results.append(provider_run)
        return results

    def _execute_stage(self, provider_run: ProviderRun, stage: str, stage_sequence: int) -> None:
        stage_run, _ = StageRun.objects.get_or_create(
            provider_run=provider_run,
            stage=stage,
            defaults={"sequence": stage_sequence},
        )
        if stage_run.status == StageRun.Status.SUCCEEDED:
            return
        if stage_sequence > 1:
            previous = provider_run.stage_runs.filter(sequence=stage_sequence - 1).first()
            if previous is None or previous.status != StageRun.Status.SUCCEEDED:
                self._skip_stage(
                    stage_run, f"Dependencia {self.STAGES[stage_sequence - 2]} fallida"
                )
                return
        stage_run.status = StageRun.Status.RUNNING
        stage_run.started_at = stage_run.started_at or self.clock()
        stage_run.finished_at = None
        stage_run.error_type = ""
        stage_run.error_message = ""
        stage_run.save(
            update_fields=(
                "status",
                "started_at",
                "finished_at",
                "error_type",
                "error_message",
            )
        )
        sources = MarketSource.objects.filter(
            provider=provider_run.provider,
            data_type=self.DATA_TYPE_BY_STAGE[stage],
            is_active=True,
        ).order_by("execution_order", "id")
        required_failed = False
        output_rows = 0
        for sequence, source in enumerate(sources, start=1):
            source_run, _ = SourceRun.objects.get_or_create(
                stage_run=stage_run,
                market_source=source,
                defaults={"sequence": sequence},
            )
            if source_run.status == StageRun.Status.SUCCEEDED:
                output_rows += source_run.rows_normalized
                continue
            succeeded = self._execute_source(provider_run.pipeline_run, source_run)
            output_rows += source_run.rows_normalized
            if not succeeded and source.is_required:
                required_failed = True
        stage_run.attempt_count = sum(stage_run.source_runs.values_list("attempt_count", flat=True))
        stage_run.output_row_count = output_rows
        stage_run.finished_at = self.clock()
        stage_run.status = StageRun.Status.FAILED if required_failed else StageRun.Status.SUCCEEDED
        if required_failed:
            stage_run.error_type = "RequiredSourceFailed"
            stage_run.error_message = "Una o más fuentes requeridas fallaron"
        stage_run.save(
            update_fields=(
                "status",
                "attempt_count",
                "output_row_count",
                "finished_at",
                "error_type",
                "error_message",
            )
        )

    def _execute_source(self, pipeline_run: PipelineRun, source_run: SourceRun) -> bool:
        settings = source_run.market_source.settings_json
        max_attempts = max(1, int(settings.get("max_attempts", 1)))
        backoff_seconds = max(0.0, float(settings.get("retry_backoff_seconds", 0)))
        source_run.status = StageRun.Status.RUNNING
        source_run.started_at = source_run.started_at or self.clock()
        source_run.error_type = ""
        source_run.error_message = ""
        source_run.save(update_fields=("status", "started_at", "error_type", "error_message"))
        # ``max_attempts`` applies to this invocation. A deliberate pipeline
        # resume must get a fresh retry budget while preserving the cumulative
        # counter for observability.
        for attempt_in_execution in range(1, max_attempts + 1):
            source_run.attempt_count += 1
            source_run.save(update_fields=("attempt_count",))
            try:
                result = self.executor.execute(
                    source_run.market_source,
                    pipeline_run=pipeline_run,
                )
            except Exception as exc:  # noqa: BLE001 - source isolation boundary
                source_run.error_type = type(exc).__name__
                source_run.error_message = str(exc)[:2000]
                source_run.save(update_fields=("error_type", "error_message"))
                if attempt_in_execution < max_attempts and backoff_seconds:
                    self.sleeper(backoff_seconds * attempt_in_execution)
                continue
            source_run.status = StageRun.Status.SUCCEEDED
            source_run.finished_at = self.clock()
            source_run.rows_scraped = result.rows_scraped
            source_run.rows_cleaned = result.rows_cleaned
            source_run.rows_normalized = result.rows_normalized
            source_run.content_sha256 = result.content_sha256
            source_run.metadata_json = result.metadata or {}
            source_run.save(
                update_fields=(
                    "status",
                    "finished_at",
                    "rows_scraped",
                    "rows_cleaned",
                    "rows_normalized",
                    "content_sha256",
                    "metadata_json",
                )
            )
            return True
        source_run.status = StageRun.Status.FAILED
        source_run.finished_at = self.clock()
        source_run.save(update_fields=("status", "finished_at"))
        return False

    def _skip_stage(self, stage_run: StageRun, reason: str) -> None:
        stage_run.status = StageRun.Status.SKIPPED
        stage_run.finished_at = self.clock()
        stage_run.error_type = "DependencyFailed"
        stage_run.error_message = reason
        stage_run.save(update_fields=("status", "finished_at", "error_type", "error_message"))

    def _provider_stages_succeeded(self, provider_run: ProviderRun) -> bool:
        statuses = dict(provider_run.stage_runs.values_list("stage", "status"))
        return all(statuses.get(stage) == StageRun.Status.SUCCEEDED for stage in self.STAGES)

    def _fail_provider(self, provider_run: ProviderRun, exc: Exception) -> None:
        provider_run.status = PipelineRun.Status.FAILED
        provider_run.finished_at = self.clock()
        provider_run.error_summary = f"{type(exc).__name__}: {exc}"[:2000]
        provider_run.save(update_fields=("status", "finished_at", "error_summary"))

    def _finish_run(self, run: PipelineRun) -> None:
        statuses = list(run.provider_runs.values_list("status", flat=True))
        published = statuses.count(PipelineRun.Status.PUBLISHED)
        if statuses and published == len(statuses):
            run.status = PipelineRun.Status.PUBLISHED
            run.published_at = self.clock()
        elif statuses and all(status == PipelineRun.Status.COMPLETED for status in statuses):
            run.status = PipelineRun.Status.COMPLETED
        elif published:
            run.status = PipelineRun.Status.PARTIAL
        else:
            run.status = PipelineRun.Status.FAILED
        run.finished_at = self.clock()
        run.save(update_fields=("status", "published_at", "finished_at"))

    def _notify_results(self, run: PipelineRun, provider_runs: list[ProviderRun]) -> None:
        for provider_run in provider_runs:
            provider_code = provider_run.provider.code
            context = {
                "run_id": str(run.id),
                "provider": provider_code,
            }
            if provider_run.status == PipelineRun.Status.PUBLISHED:
                self.notifier(
                    NotificationOutbox.EventType.DATA_CHANGED,
                    f"pipeline:published:{run.id}:{provider_code}",
                    "Datos publicados",
                    {
                        **context,
                        "title": "Datos publicados",
                        "summary": f"Se publicaron datos de {provider_run.provider.name}.",
                    },
                )
            elif provider_run.status == PipelineRun.Status.FAILED:
                summary = provider_run.error_summary or "Una fuente requerida no pudo completarse"
                self.notifier(
                    NotificationOutbox.EventType.SCRAPE_FAILED,
                    f"pipeline:failed:{run.id}:{provider_code}",
                    "Pipeline incompleto",
                    {
                        **context,
                        "title": "Pipeline incompleto",
                        "summary": f"{provider_run.provider.name}: {summary}",
                    },
                )
