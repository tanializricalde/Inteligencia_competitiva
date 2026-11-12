from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.pipeline.application.configuration import publish_config_version


class Command(BaseCommand):
    help = "Publica una versión de configuración validada y la vuelve inmutable"

    def add_arguments(self, parser):
        parser.add_argument("--code", required=True)
        parser.add_argument("--config-version", required=True, type=int)

    def handle(self, *args, **options):
        try:
            item = publish_config_version(code=options["code"], version=options["config_version"])
        except (ValidationError, ObjectDoesNotExist) as exc:
            messages = exc.messages if isinstance(exc, ValidationError) else [str(exc)]
            raise CommandError("; ".join(messages)) from exc
        self.stdout.write(self.style.SUCCESS(f"Publicada: {item}"))
