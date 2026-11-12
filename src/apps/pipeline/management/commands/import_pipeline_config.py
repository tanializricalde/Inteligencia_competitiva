from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError

from apps.pipeline.application.configuration import import_config_version, load_config_document
from apps.pipeline.models import PipelineConfig


class Command(BaseCommand):
    help = "Importa una configuración como borrador; nunca la publica automáticamente"

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument("--code", required=True)
        parser.add_argument("--stage", required=True, choices=PipelineConfig.Stage.values)
        parser.add_argument("--config-version", required=True, type=int)

    def handle(self, *args, **options):
        try:
            item = import_config_version(
                code=options["code"],
                stage=options["stage"],
                version=options["config_version"],
                payload=load_config_document(options["path"]),
            )
        except (ValidationError, IntegrityError) as exc:
            messages = exc.messages if isinstance(exc, ValidationError) else [str(exc)]
            raise CommandError("; ".join(messages)) from exc
        self.stdout.write(self.style.SUCCESS(f"Importada como borrador: {item}"))
