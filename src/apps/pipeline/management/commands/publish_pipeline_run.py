from uuid import UUID

from django.core.management.base import BaseCommand, CommandError

from apps.pipeline.application.publication import PublicationError, publish_provider_run
from apps.pipeline.models import PipelineRun


class Command(BaseCommand):
    help = "Publica atómicamente los proveedores completos de una ejecución"

    def add_arguments(self, parser):
        parser.add_argument("run_id", type=UUID)
        parser.add_argument("--provider", action="append", default=[])

    def handle(self, *args, **options):
        try:
            run = PipelineRun.objects.get(pk=options["run_id"])
        except PipelineRun.DoesNotExist as exc:
            raise CommandError("PipelineRun inexistente") from exc
        provider_runs = run.provider_runs.select_related("provider").order_by("sequence")
        if options["provider"]:
            provider_runs = provider_runs.filter(provider__code__in=options["provider"])
        errors = []
        for provider_run in provider_runs:
            try:
                publish_provider_run(provider_run)
            except PublicationError as exc:
                errors.append(f"{provider_run.provider.code}: {exc}")
        if errors:
            raise CommandError("; ".join(errors))
        self.stdout.write(self.style.SUCCESS(f"Publicada: {run.id}"))
