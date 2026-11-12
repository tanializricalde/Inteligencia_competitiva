import fcntl
import os
import socket
from contextlib import contextmanager
from pathlib import Path
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from django.conf import settings
from django.utils import timezone

from apps.notifications.services import send_pending_notifications
from apps.pipeline.application.manual_queue import process_manual_pipeline
from apps.pipeline.application.orchestrator import PipelineOrchestrator
from apps.pipeline.infrastructure.core_executor import DjangoCorePipelineExecutor
from apps.pipeline.models import PipelineRun, ScheduledJob
from apps.reviews.application.services import process_pending_enrichments
from apps.scraping.models import SchedulerHeartbeat


@contextmanager
def scheduler_process_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.close()
        raise RuntimeError("Ya existe un scheduler activo en este host") from exc
    try:
        handle.write(str(os.getpid()))
        handle.flush()
        yield
    finally:
        fcntl.flock(handle, fcntl.LOCK_UN)
        handle.close()


def update_heartbeat() -> None:
    now = timezone.now()
    SchedulerHeartbeat.objects.update_or_create(
        name="primary",
        defaults={
            "process_id": os.getpid(),
            "hostname": socket.gethostname(),
            "last_seen_at": now,
            "started_at": now,
        },
    )


def run_scheduled_pipeline(job_id: int) -> None:
    job = ScheduledJob.objects.select_related("profile__active_version").get(
        pk=job_id, is_active=True
    )
    if (
        job.concurrency_policy == ScheduledJob.ConcurrencyPolicy.SKIP
        and PipelineRun.objects.filter(
            scheduled_job=job,
            status__in=(PipelineRun.Status.PENDING, PipelineRun.Status.RUNNING),
        ).exists()
    ):
        return
    if job.profile.active_version is None:
        raise RuntimeError(f"El job {job.code} no tiene versión de perfil activa")
    now = timezone.now()
    run = PipelineRun.objects.create(
        scheduled_job=job,
        profile_version=job.profile.active_version,
        trigger_type=PipelineRun.TriggerType.SCHEDULED,
        status=PipelineRun.Status.PENDING,
    )
    job.last_started_at = now
    job.save(update_fields=("last_started_at",))
    try:
        PipelineOrchestrator(DjangoCorePipelineExecutor()).execute(
            profile_version=job.profile.active_version,
            trigger_type=PipelineRun.TriggerType.SCHEDULED,
            pipeline_run=run,
        )
    finally:
        job.last_finished_at = timezone.now()
        job.save(update_fields=("last_finished_at",))


def process_manual_pipeline_queue() -> None:
    process_manual_pipeline()


def build_scheduler() -> BlockingScheduler:
    scheduler = BlockingScheduler(
        timezone=ZoneInfo(settings.TIME_ZONE),
        job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 300},
    )
    scheduler.add_job(update_heartbeat, "interval", seconds=15, id="heartbeat")
    scheduler.add_job(
        process_manual_pipeline_queue, "interval", seconds=5, id="manual-pipeline-requests"
    )
    scheduler.add_job(
        process_pending_enrichments,
        "interval",
        seconds=30,
        kwargs={"limit": 100},
        id="review-enrichment",
    )
    scheduler.add_job(send_pending_notifications, "interval", seconds=10, id="notifications")
    for job in ScheduledJob.objects.filter(is_active=True).order_by("code"):
        trigger = CronTrigger.from_crontab(job.cron_expression, timezone=ZoneInfo(job.timezone))
        scheduler.add_job(
            run_scheduled_pipeline,
            trigger,
            args=(job.id,),
            id=f"pipeline-{job.code}",
        )
        job.next_run_at = trigger.get_next_fire_time(None, timezone.now())
        job.save(update_fields=("next_run_at",))
    return scheduler


def default_lock_path() -> Path:
    database_name = Path(settings.DATABASES["default"]["NAME"])
    return database_name.parent / "scheduler.lock"
