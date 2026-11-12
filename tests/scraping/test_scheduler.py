from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.market.models import Provider
from apps.pipeline.models import PipelineProfile, PipelineProfileVersion, PipelineRun
from apps.scraping.application.services import ProcessManualRequests
from apps.scraping.models import (
    ManualScrapeRequest,
    SchedulerHeartbeat,
    ScrapeRun,
    ScrapeSource,
)


@pytest.mark.django_db
def test_scheduler_once_records_heartbeat(capsys):

    call_command("run_scheduler", "--once")

    heartbeat = SchedulerHeartbeat.objects.get(name="primary")
    assert heartbeat.last_seen_at is not None
    assert "Scheduler verificado" in capsys.readouterr().out


@pytest.mark.django_db
def test_scheduler_once_consumes_manual_pipeline(monkeypatch, django_user_model):
    profile = PipelineProfile.objects.create(code="manual-profile", name="Manual")
    version = PipelineProfileVersion.objects.create(profile=profile, version=1)
    user = django_user_model.objects.create_user("pipeline@example.test", "pass")
    run = PipelineRun.objects.create(
        profile_version=version,
        trigger_type=PipelineRun.TriggerType.MANUAL,
        requested_by=user,
    )

    class FakeOrchestrator:
        def __init__(self, _executor):
            pass

        def execute(self, *, pipeline_run, **_kwargs):
            pipeline_run.status = PipelineRun.Status.COMPLETED
            pipeline_run.finished_at = timezone.now()
            pipeline_run.save(update_fields=("status", "finished_at"))
            return pipeline_run

    monkeypatch.setattr(
        "apps.pipeline.application.manual_queue.PipelineOrchestrator", FakeOrchestrator
    )

    call_command("run_scheduler", "--once")

    run.refresh_from_db()
    assert run.status == PipelineRun.Status.COMPLETED


@pytest.mark.django_db
def test_expired_manual_request_is_recovered(django_user_model):
    user = django_user_model.objects.create_user("operator@example.test", "pass")
    request = ManualScrapeRequest.objects.create(requested_by=user)
    request.status = ManualScrapeRequest.Status.RUNNING
    request.lease_expires_at = timezone.now() - timedelta(minutes=1)
    request.save(update_fields=("status", "lease_expires_at"))

    assert ProcessManualRequests().recover_expired() == 1
    request.refresh_from_db()
    assert request.status == ManualScrapeRequest.Status.PENDING


@pytest.mark.django_db
def test_manual_scrape_worker_excludes_demo_sources(django_user_model):
    user = django_user_model.objects.create_user("demo-scrape@example.test", "pass")
    provider = Provider.objects.create(
        name="Demo aislado",
        code="demo_legacy_scrape",
        data_scope=Provider.DataScope.DEMO,
    )
    source = ScrapeSource.objects.create(
        provider=provider,
        name="Fuente no operativa",
        target_url="https://example.test/plans",
        adapter_key="example_httpx",
        is_active=True,
    )
    ManualScrapeRequest.objects.create(source=source, requested_by=user)

    class RecordingRunner:
        source_ids = None

        def execute(self, sources, *, origin):
            self.source_ids = list(sources.values_list("id", flat=True))
            return ScrapeRun.objects.create(origin=origin)

    runner = RecordingRunner()
    ProcessManualRequests(runner=runner).process_one()

    assert runner.source_ids == []
