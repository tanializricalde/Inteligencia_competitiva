from django.core.management.base import BaseCommand

from apps.reviews.application.services import process_pending_enrichments


class Command(BaseCommand):
    help = "Procesa un lote de enriquecimientos de reseñas pendientes"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        completed = process_pending_enrichments(limit=max(1, min(options["limit"], 1000)))
        self.stdout.write(self.style.SUCCESS(f"Enriquecimientos completados: {completed}"))
