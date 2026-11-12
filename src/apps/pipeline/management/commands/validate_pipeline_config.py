from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.pipeline.application.configuration import (
    load_config_document,
    validate_config_document,
)
from apps.pipeline.models import PipelineConfig


class Command(BaseCommand):
    help = "Valida un JSON de configuración sin guardarlo"

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument("--stage", required=True, choices=PipelineConfig.Stage.values)

    def handle(self, *args, **options):
        try:
            payload = load_config_document(options["path"])
            version = validate_config_document(stage=options["stage"], payload=payload)
        except ValidationError as exc:
            raise CommandError("; ".join(exc.messages)) from exc
        self.stdout.write(self.style.SUCCESS(f"Configuración válida: {version.content_sha256}"))
