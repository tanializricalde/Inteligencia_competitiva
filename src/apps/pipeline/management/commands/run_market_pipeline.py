from uuid import UUID

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.market.models import Provider
from apps.pipeline.application.orchestrator import PipelineOrchestrator
from apps.pipeline.infrastructure.core_executor import DjangoCorePipelineExecutor
from apps.pipeline.management.support import resolve_profile_version
from apps.pipeline.models import MarketSource, PipelineRun, ProviderRun


def _complete_without_publishing(provider_run: ProviderRun) -> ProviderRun:
    provider_run.status = PipelineRun.Status.COMPLETED
    provider_run.is_complete = True
    provider_run.finished_at = timezone.now()
    provider_run.save(update_fields=("status", "is_complete", "finished_at"))
    return provider_run


class Command(BaseCommand):
    help = "Ejecuta secuencialmente planes, características y reseñas"

    def add_arguments(self, parser):
        parser.add_argument("--profile")
        parser.add_argument("--scheduled-job")
        parser.add_argument("--provider", action="append", default=[])
        parser.add_argument("--resume-run", type=UUID)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--no-publish", action="store_true")

    def handle(self, *args, **options):
        profile_version, job = resolve_profile_version(
            profile_code=options["profile"],
            scheduled_job_code=options["scheduled_job"],
        )
        providers = Provider.objects.filter(
            is_active=True, data_scope=Provider.DataScope.REAL
        ).order_by("execution_order", "id")
        if options["provider"]:
            providers = providers.filter(code__in=options["provider"])
            found = set(providers.values_list("code", flat=True))
            missing = sorted(set(options["provider"]) - found)
            if missing:
                raise CommandError(f"Proveedores activos inexistentes: {', '.join(missing)}")
        providers = list(providers)
        if options["dry_run"]:
            for stage in ("plans", "features", "reviews"):
                for provider in providers:
                    sources = MarketSource.objects.filter(
                        provider=provider, data_type=stage, is_active=True
                    ).order_by("execution_order", "id")
                    self.stdout.write(
                        f"{stage}:{provider.code}:" + ",".join(item.code for item in sources)
                    )
            self.stdout.write(self.style.SUCCESS("Configuración y orden válidos; sin escrituras"))
            return
        run = None
        if options["resume_run"]:
            try:
                run = PipelineRun.objects.get(pk=options["resume_run"])
            except PipelineRun.DoesNotExist as exc:
                raise CommandError("PipelineRun inexistente") from exc
        elif job is not None:
            run = PipelineRun.objects.create(
                scheduled_job=job,
                profile_version=profile_version,
                trigger_type=PipelineRun.TriggerType.SCHEDULED,
                status=PipelineRun.Status.PENDING,
            )
        publisher = _complete_without_publishing if options["no_publish"] else None
        kwargs = {"publisher": publisher} if publisher else {}
        result = PipelineOrchestrator(DjangoCorePipelineExecutor(), **kwargs).execute(
            profile_version=profile_version,
            trigger_type=(
                PipelineRun.TriggerType.RETRY
                if options["resume_run"]
                else PipelineRun.TriggerType.SCHEDULED
                if job
                else PipelineRun.TriggerType.MANUAL
            ),
            providers=providers,
            pipeline_run=run,
        )
        self.stdout.write(self.style.SUCCESS(f"{result.id} status={result.status}"))
