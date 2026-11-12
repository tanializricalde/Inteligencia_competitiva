from uuid import UUID

from django.core.management.base import BaseCommand, CommandError

from apps.market.models import Provider
from apps.pipeline.application.orchestrator import PipelineOrchestrator
from apps.pipeline.infrastructure.core_executor import DjangoCorePipelineExecutor
from apps.pipeline.management.support import resolve_profile_version
from apps.pipeline.models import MarketSource, PipelineRun, StageRun


class Command(BaseCommand):
    help = "Ejecuta una sola etapa para diagnóstico; no publica datos"

    def add_arguments(self, parser):
        parser.add_argument("--profile", required=True)
        parser.add_argument("--provider", required=True)
        parser.add_argument("--stage", required=True, choices=StageRun.Stage.values)
        parser.add_argument("--resume-run", type=UUID)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        profile_version, _ = resolve_profile_version(profile_code=options["profile"])
        try:
            provider = Provider.objects.get(
                code=options["provider"],
                is_active=True,
                data_scope=Provider.DataScope.REAL,
            )
        except Provider.DoesNotExist as exc:
            raise CommandError("Proveedor activo inexistente") from exc
        sources = MarketSource.objects.filter(
            provider=provider,
            data_type=options["stage"],
            is_active=True,
        ).order_by("execution_order", "id")
        if options["dry_run"]:
            self.stdout.write(
                f"{options['stage']}:{provider.code}:" + ",".join(source.code for source in sources)
            )
            return
        run = None
        if options["resume_run"]:
            try:
                run = PipelineRun.objects.get(pk=options["resume_run"])
            except PipelineRun.DoesNotExist as exc:
                raise CommandError("PipelineRun inexistente") from exc
        elif options["stage"] != StageRun.Stage.PLANS:
            raise CommandError(
                "features/reviews requieren --resume-run con sus dependencias exitosas"
            )
        try:
            run, stage_run = PipelineOrchestrator(
                DjangoCorePipelineExecutor()
            ).execute_diagnostic_stage(
                profile_version=profile_version,
                provider=provider,
                stage=options["stage"],
                pipeline_run=run,
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS(f"{run.id} {stage_run.stage} status={stage_run.status}")
        )
