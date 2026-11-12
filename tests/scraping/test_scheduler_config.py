import pytest

from apps.pipeline.models import PipelineProfile, PipelineProfileVersion, ScheduledJob
from apps.scraping.infrastructure.scheduler import build_scheduler


@pytest.mark.django_db
def test_scheduler_uses_django_timezone_and_persists_next_run(settings):
    settings.TIME_ZONE = "America/Lima"
    profile = PipelineProfile.objects.create(code="nightly", name="Nocturno")
    version = PipelineProfileVersion.objects.create(
        profile=profile,
        version=1,
        status=PipelineProfileVersion.Status.PUBLISHED,
    )
    profile.active_version = version
    profile.save(update_fields=("active_version",))
    job = ScheduledJob.objects.create(
        code="nightly",
        name="Nocturno",
        profile=profile,
        cron_expression="30 7 * * *",
        timezone="America/Lima",
    )

    scheduler = build_scheduler()

    job.refresh_from_db()
    assert str(scheduler.timezone) == "America/Lima"
    assert scheduler.get_job("pipeline-nightly") is not None
    assert scheduler.get_job("daily-scrape") is None
    assert scheduler.get_job("manual-requests") is None
    assert scheduler.get_job("manual-review-requests") is None
    assert scheduler.get_job("manual-pipeline-requests") is not None
    assert job.next_run_at is not None
