from dataclasses import dataclass, field
from uuid import uuid4

import pytest

from apps.market.models import Provider
from apps.notifications.models import NotificationOutbox, NotificationRecipient
from apps.pipeline.application.orchestrator import (
    PipelineOrchestrator,
    SourceExecutionResult,
)
from apps.pipeline.models import (
    MarketSource,
    PipelineProfile,
    PipelineProfileVersion,
    PipelineRun,
    ProviderRun,
    StageRun,
)


@dataclass
class RecordingExecutor:
    failures: dict[str, int] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)
    finalized: list[str] = field(default_factory=list)
    active: int = 0
    max_active: int = 0

    def execute(self, source, *, pipeline_run):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        self.calls.append(source.code)
        try:
            remaining = self.failures.get(source.code, 0)
            if remaining:
                self.failures[source.code] = remaining - 1
                raise RuntimeError(f"fallo {source.code}")
            return SourceExecutionResult(
                rows_scraped=1,
                rows_cleaned=1,
                rows_normalized=1,
                content_sha256="a" * 64,
            )
        finally:
            self.active -= 1

    def finalize_provider(self, provider_run):
        self.finalized.append(provider_run.provider.code)


def _publisher(provider_run):
    provider_run.status = PipelineRun.Status.PUBLISHED
    provider_run.is_complete = True
    provider_run.save(update_fields=("status", "is_complete"))
    return provider_run


@pytest.mark.django_db
def test_orchestrator_uses_global_stage_barriers_and_one_source_at_a_time():
    profile_version = _profile_version()
    provider_a = Provider.objects.create(code="provider-a", name="A", execution_order=1)
    provider_b = Provider.objects.create(code="provider-b", name="B", execution_order=2)
    _source(provider_a, "plans-provider_a", "plans")
    _source(provider_b, "plans-provider_b", "plans")
    _source(provider_a, "features-provider_a", "features")
    _source(provider_b, "features-provider_b", "features")
    _source(provider_a, "reviews-provider_a-source_1", "reviews", order=1)
    _source(provider_a, "reviews-provider_a-source_2", "reviews", order=2)
    _source(provider_b, "reviews-provider_b-source_1", "reviews")
    executor = RecordingExecutor()

    run = PipelineOrchestrator(executor, publisher=_publisher).execute(
        profile_version=profile_version,
        trigger_type=PipelineRun.TriggerType.MANUAL,
        providers=(provider_a, provider_b),
    )

    assert executor.calls == [
        "plans-provider_a",
        "plans-provider_b",
        "features-provider_a",
        "features-provider_b",
        "reviews-provider_a-source_1",
        "reviews-provider_a-source_2",
        "reviews-provider_b-source_1",
    ]
    assert executor.max_active == 1
    assert executor.finalized == ["provider-a", "provider-b"]
    assert run.status == PipelineRun.Status.PUBLISHED


@pytest.mark.django_db
def test_failure_is_isolated_dependencies_skip_and_retry_is_per_source():
    profile_version = _profile_version()
    provider_a = Provider.objects.create(code="retry-provider", name="Retry", execution_order=1)
    provider_b = Provider.objects.create(code="failed-provider", name="Failed", execution_order=2)
    _source(
        provider_a,
        "retry-plans",
        "plans",
        settings={"max_attempts": 2, "retry_backoff_seconds": 0},
    )
    _source(provider_b, "failed-plans", "plans")
    _source(provider_a, "retry-features", "features")
    _source(provider_b, "failed-features", "features")
    _source(provider_a, "retry-reviews", "reviews")
    _source(provider_b, "failed-reviews", "reviews")
    executor = RecordingExecutor(failures={"retry-plans": 1, "failed-plans": 1})

    run = PipelineOrchestrator(executor, publisher=_publisher).execute(
        profile_version=profile_version,
        trigger_type=PipelineRun.TriggerType.MANUAL,
        providers=(provider_a, provider_b),
    )

    assert executor.calls == [
        "retry-plans",
        "retry-plans",
        "failed-plans",
        "retry-features",
        "retry-reviews",
    ]
    failed_run = run.provider_runs.get(provider=provider_b)
    assert list(failed_run.stage_runs.values_list("status", flat=True)) == [
        StageRun.Status.FAILED,
        StageRun.Status.SKIPPED,
        StageRun.Status.SKIPPED,
    ]
    assert failed_run.error_summary == (
        "plans/failed-plans: RuntimeError: fallo failed-plans"
    )
    assert run.status == PipelineRun.Status.PARTIAL


@pytest.mark.django_db
def test_retry_clears_stale_provider_error_after_source_recovers():
    profile_version = _profile_version()
    provider = Provider.objects.create(code="recovered-provider", name="Recovered")
    for stage in ("plans", "features", "reviews"):
        _source(provider, f"recovered-{stage}", stage)
    executor = RecordingExecutor(failures={"recovered-plans": 1})
    orchestrator = PipelineOrchestrator(executor, publisher=_publisher)

    run = orchestrator.execute(
        profile_version=profile_version,
        trigger_type=PipelineRun.TriggerType.MANUAL,
        providers=(provider,),
    )
    failed = run.provider_runs.get(provider=provider)
    assert failed.error_summary

    resumed = orchestrator.execute(
        profile_version=profile_version,
        trigger_type=PipelineRun.TriggerType.RETRY,
        providers=(provider,),
        pipeline_run=run,
    )

    recovered = resumed.provider_runs.get(provider=provider)
    assert recovered.status == PipelineRun.Status.PUBLISHED
    assert recovered.error_summary == ""


@pytest.mark.django_db
def test_resume_does_not_repeat_successful_sources():
    profile_version = _profile_version()
    provider = Provider.objects.create(code="resume-provider", name="Resume")
    _source(provider, "resume-plans", "plans")
    _source(provider, "resume-features", "features")
    _source(provider, "resume-reviews", "reviews")
    executor = RecordingExecutor()
    orchestrator = PipelineOrchestrator(executor, publisher=_publisher)
    run = orchestrator.execute(
        profile_version=profile_version,
        trigger_type=PipelineRun.TriggerType.MANUAL,
        providers=(provider,),
    )
    first_calls = list(executor.calls)

    resumed = orchestrator.execute(
        profile_version=profile_version,
        trigger_type=PipelineRun.TriggerType.RETRY,
        providers=(provider,),
        pipeline_run=run,
    )

    assert resumed == run
    assert executor.calls == first_calls


@pytest.mark.django_db
def test_orchestrator_enqueues_idempotent_publication_and_failure_notifications():
    NotificationRecipient.objects.create(name="Operaciones", email="ops@example.test")
    profile_version = _profile_version()
    published_provider = Provider.objects.create(code="notified-ok", name="Publicable")
    failed_provider = Provider.objects.create(code="notified-failed", name="Fallido")
    for stage in ("plans", "features", "reviews"):
        _source(published_provider, f"ok-{stage}", stage)
        _source(failed_provider, f"failed-{stage}", stage)
    executor = RecordingExecutor(failures={"failed-plans": 1})
    orchestrator = PipelineOrchestrator(executor, publisher=_publisher)

    run = orchestrator.execute(
        profile_version=profile_version,
        trigger_type=PipelineRun.TriggerType.MANUAL,
        providers=(published_provider, failed_provider),
    )
    orchestrator.execute(
        profile_version=profile_version,
        trigger_type=PipelineRun.TriggerType.RETRY,
        providers=(published_provider, failed_provider),
        pipeline_run=run,
    )

    assert (
        NotificationOutbox.objects.filter(
            event_type=NotificationOutbox.EventType.DATA_CHANGED
        ).count()
        == 2
    )
    assert (
        NotificationOutbox.objects.filter(
            event_type=NotificationOutbox.EventType.SCRAPE_FAILED
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_orchestrator_rejects_demo_provider_before_creating_work_or_notifications():
    profile_version = _profile_version()
    provider = Provider.objects.create(
        code="demo-rejected",
        name="Demo rechazado",
        data_scope=Provider.DataScope.DEMO,
    )
    recipient_count = NotificationOutbox.objects.count()

    with pytest.raises(ValueError, match="sólo admite proveedores REAL"):
        PipelineOrchestrator(RecordingExecutor(), publisher=_publisher).execute(
            profile_version=profile_version,
            trigger_type=PipelineRun.TriggerType.MANUAL,
            providers=(provider,),
        )

    assert not ProviderRun.objects.filter(provider=provider).exists()
    assert NotificationOutbox.objects.count() == recipient_count


def _profile_version() -> PipelineProfileVersion:
    profile = PipelineProfile.objects.create(code=f"profile-{uuid4()}", name="Perfil")
    return PipelineProfileVersion.objects.create(profile=profile, version=1)


def _source(
    provider: Provider,
    code: str,
    data_type: str,
    *,
    order: int = 1,
    settings: dict | None = None,
) -> MarketSource:
    return MarketSource.objects.create(
        provider=provider,
        code=code,
        name=code,
        data_type=data_type,
        adapter_key="fixture",
        url="https://example.test/data",
        execution_order=order,
        settings_json=settings or {},
    )
