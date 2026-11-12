from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.pipeline.models import PipelineRun, ProviderRun, StageRun


class PublicationError(ValueError):
    """Raised when a provider run is not complete enough to publish."""


@transaction.atomic
def publish_provider_run(provider_run: ProviderRun) -> ProviderRun:
    locked = (
        ProviderRun.objects.select_for_update()
        .select_related("pipeline_run", "provider")
        .get(pk=provider_run.pk)
    )
    if locked.provider.data_scope != "real":
        raise PublicationError("El pipeline operativo sólo puede publicar proveedores REAL")
    stages = list(locked.stage_runs.prefetch_related("source_runs__market_source"))
    required_stages = {StageRun.Stage.PLANS, StageRun.Stage.FEATURES, StageRun.Stage.REVIEWS}
    present = {stage.stage for stage in stages}
    if present != required_stages:
        missing = ", ".join(sorted(required_stages - present))
        raise PublicationError(f"Faltan etapas para publicar: {missing or 'etapas inesperadas'}")
    failed_stages = [stage.stage for stage in stages if stage.status != StageRun.Status.SUCCEEDED]
    if failed_stages:
        raise PublicationError(f"Las etapas no están completas: {', '.join(sorted(failed_stages))}")
    failed_sources = [
        source.market_source.code
        for stage in stages
        for source in stage.source_runs.all()
        if source.market_source.is_required and source.status != StageRun.Status.SUCCEEDED
    ]
    if failed_sources:
        raise PublicationError(
            f"Las fuentes requeridas no están completas: {', '.join(sorted(failed_sources))}"
        )
    if not locked.plan_snapshots.exists():
        raise PublicationError("No se puede publicar un proveedor sin snapshots de planes")

    published_at = timezone.now()
    locked.status = PipelineRun.Status.PUBLISHED
    locked.is_complete = True
    locked.published_at = published_at
    locked.finished_at = locked.finished_at or published_at
    locked.save(update_fields=("status", "is_complete", "published_at", "finished_at"))
    _refresh_pipeline_run(locked.pipeline_run)
    return locked


def _refresh_pipeline_run(pipeline_run: PipelineRun) -> None:
    provider_runs = list(pipeline_run.provider_runs.all())
    terminal = {
        PipelineRun.Status.PUBLISHED,
        PipelineRun.Status.FAILED,
        PipelineRun.Status.CANCELLED,
    }
    if not provider_runs or any(item.status not in terminal for item in provider_runs):
        return
    published = [item for item in provider_runs if item.status == PipelineRun.Status.PUBLISHED]
    if len(published) == len(provider_runs):
        status = PipelineRun.Status.PUBLISHED
        pipeline_run.published_at = max(item.published_at for item in published)
    elif published:
        status = PipelineRun.Status.PARTIAL
    else:
        status = PipelineRun.Status.FAILED
    pipeline_run.status = status
    pipeline_run.finished_at = pipeline_run.finished_at or timezone.now()
    pipeline_run.save(update_fields=("status", "published_at", "finished_at"))
