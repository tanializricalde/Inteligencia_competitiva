from django.core.management.base import BaseCommand, CommandError

from apps.reviews.application.services import RunReviewScrapeUseCase
from apps.reviews.models import ReviewRun, ReviewSource


class Command(BaseCommand):
    help = "Ejecuta fuentes de reseñas activas de forma secuencial"

    def add_arguments(self, parser):
        scope = parser.add_mutually_exclusive_group(required=True)
        scope.add_argument("--all", action="store_true", help="Todas las fuentes activas")
        scope.add_argument("--source", type=int, help="ID de una fuente")
        scope.add_argument("--provider", help="Código estable de un competidor")

    def handle(self, *args, **options):
        sources = ReviewSource.objects.filter(
            enabled=True, provider__data_scope="real"
        ).select_related("provider")
        if options["source"]:
            sources = sources.filter(pk=options["source"])
        elif options["provider"]:
            sources = sources.filter(provider__code=options["provider"])
        if not sources.exists():
            raise CommandError("No hay fuentes activas para el alcance indicado")
        run = RunReviewScrapeUseCase().execute(sources, origin=ReviewRun.Origin.MANUAL)
        self.stdout.write(self.style.SUCCESS(f"ReviewRun #{run.id}: {run.summary}"))
