from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand, CommandError

from apps.pipeline.application.configuration import export_config_version
from data_pipeline.errors import DatasetIOError


class Command(BaseCommand):
    help = "Exporta una versión JSON compatible con sus validadores compartidos"

    def add_arguments(self, parser):
        parser.add_argument("--code", required=True)
        parser.add_argument("--config-version", required=True, type=int)
        parser.add_argument("--output", required=True)
        parser.add_argument("--overwrite", action="store_true")

    def handle(self, *args, **options):
        try:
            output = export_config_version(
                code=options["code"],
                version=options["config_version"],
                output=options["output"],
                overwrite=options["overwrite"],
            )
        except (ObjectDoesNotExist, DatasetIOError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(str(output)))
