from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.pipeline.application.orchestrator import PipelineOrchestrator
from apps.pipeline.infrastructure.core_executor import DjangoCorePipelineExecutor
from apps.pipeline.models import PipelineProfile, PipelineRun


class PipelineQueueUnavailable(RuntimeError):
    """Raised when no published active profile can execute a manual request."""


def enqueue_manual_pipeline(
    *, requested_by, profile_code: str = "nightly-market"
) -> tuple[PipelineRun, bool]:
    try:
        profile = PipelineProfile.objects.select_related("active_version").get(code=profile_code)
    except PipelineProfile.DoesNotExist as exc:
        raise PipelineQueueUnavailable(
            "El pipeline no está inicializado; ejecuta seed_market_pipeline."
        ) from exc
    if profile.active_version is None:
        raise PipelineQueueUnavailable("El perfil del pipeline no tiene una versión activa.")
    pending = PipelineRun.objects.filter(
        profile_version=profile.active_version,
        trigger_type=PipelineRun.TriggerType.MANUAL,
        status__in=(PipelineRun.Status.PENDING, PipelineRun.Status.RUNNING),
    ).first()
    if pending is not None:
        return pending, False
    return (
        PipelineRun.objects.create(
            profile_version=profile.active_version,
            trigger_type=PipelineRun.TriggerType.MANUAL,
            status=PipelineRun.Status.PENDING,
            requested_by=requested_by,
        ),
        True,
    )


@transaction.atomic
def claim_manual_pipeline() -> PipelineRun | None:
    run = (
        PipelineRun.objects.select_for_update()
        .select_related("profile_version")
        .filter(
            trigger_type=PipelineRun.TriggerType.MANUAL,
            status=PipelineRun.Status.PENDING,
        )
        .order_by("id")
        .first()
    )
    if run is None:
        return None
    run.status = PipelineRun.Status.RUNNING
    run.started_at = timezone.now()
    run.save(update_fields=("status", "started_at"))
    return run


def process_manual_pipeline() -> PipelineRun | None:
    run = claim_manual_pipeline()
    if run is None:
        return None
    try:
        return PipelineOrchestrator(DjangoCorePipelineExecutor()).execute(
            profile_version=run.profile_version,
            trigger_type=PipelineRun.TriggerType.MANUAL,
            pipeline_run=run,
        )
    except Exception as exc:
        run.status = PipelineRun.Status.FAILED
        run.finished_at = timezone.now()
        run.error_summary = f"{type(exc).__name__}: {exc}"[:2000]
        run.save(update_fields=("status", "finished_at", "error_summary"))
        return run
