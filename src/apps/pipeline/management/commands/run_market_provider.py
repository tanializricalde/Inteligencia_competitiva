from django.core.management.base import CommandError

from apps.pipeline.management.commands.run_market_pipeline import Command as PipelineCommand


class Command(PipelineCommand):
    help = "Ejecuta el pipeline completo para uno o más proveedores explícitos"

    def handle(self, *args, **options):
        if not options["provider"]:
            raise CommandError("run_market_provider requiere al menos un --provider")
        return super().handle(*args, **options)
